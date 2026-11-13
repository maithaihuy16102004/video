"""Tests for the canonical locomotion engine (Phase A).

The planning/measurement loop must close: a walk planned with
duration_for_distance for a profile must MEASURE that profile's
step, stride and cadence on its travel portion. Measurements run
on the travel slice (anticipation/settle excluded): the settle's
foot gather would otherwise add a spurious strike and shorten the
stride, and the standstill would dilute the cadence.
"""
from __future__ import annotations

import math
import unittest

from ai_clip_studio.animation import primitives as P
from ai_clip_studio.animation.locomotion import (
    GAIT_PRESETS,
    check_facing_continuity,
    check_facing_vs_travel,
    duration_for_distance,
    footfall_times,
    measure_locomotion,
    plan_locomotion,
    profile_to_gait,
    resolve_gait_profile,
    sample_primitive,
    state_at,
)
from ai_clip_studio.animation.rig import (
    GAIT_DEFAULT,
    GAIT_RUN,
    Stickman,
    walk_pose,
)
from ai_clip_studio.cinematic_contracts import (
    CANONICAL_GAIT,
    GaitProfile,
    LocomotionState,
)

H = 560.0
GROUND_Y = 920.0


def _travel_frames(char, fn, duration, fps=24.0):
    frames = sample_primitive(fn, char, duration, fps)
    return [f for f in frames if 0.2 <= f["_t"] <= duration - 0.25]


class TestStepStrideSeparation(unittest.TestCase):
    def test_gait_dicts_carry_step_and_stride(self):
        self.assertEqual(GAIT_DEFAULT["step_length_frac"], 0.25)
        self.assertEqual(GAIT_DEFAULT["stride_length_frac"], 0.50)
        self.assertEqual(GAIT_DEFAULT["stride_frac"], 0.25)
        self.assertEqual(GAIT_RUN["step_length_frac"], 0.28)
        self.assertEqual(GAIT_RUN["stride_length_frac"], 0.56)

    def test_profile_to_gait_keeps_step_stride_separate(self):
        gait = profile_to_gait(CANONICAL_GAIT)
        self.assertAlmostEqual(gait["step_length_frac"], 0.29)
        self.assertAlmostEqual(gait["stride_length_frac"], 0.58)
        # The legacy alias always equals the STEP length.
        self.assertEqual(gait["stride_frac"], gait["step_length_frac"])

    def test_profile_rejects_stride_shorter_than_step(self):
        with self.assertRaises(ValueError):
            GaitProfile(step_length=0.30, stride_length=0.20)


class TestGaitPresets(unittest.TestCase):
    def test_presets_are_profiles(self):
        for name, profile in GAIT_PRESETS.items():
            self.assertIsInstance(profile, GaitProfile, name)

    def test_civilian_is_canonical(self):
        self.assertEqual(GAIT_PRESETS["civilian"], CANONICAL_GAIT)

    def test_presets_differ_by_parameters_only(self):
        elderly = GAIT_PRESETS["elderly"]
        soldier = GAIT_PRESETS["soldier"]
        giant = GAIT_PRESETS["giant"]
        self.assertLess(elderly.step_length, CANONICAL_GAIT.step_length)
        self.assertLess(elderly.cadence, CANONICAL_GAIT.cadence)
        self.assertEqual(elderly.posture, "stooped")
        self.assertGreater(soldier.cadence, CANONICAL_GAIT.cadence)
        self.assertEqual(soldier.posture, "military")
        self.assertGreater(giant.body_mass, CANONICAL_GAIT.body_mass)
        self.assertLess(giant.cadence, CANONICAL_GAIT.cadence)

    def test_resolve_gait_profile(self):
        self.assertEqual(resolve_gait_profile(None), CANONICAL_GAIT)
        self.assertEqual(resolve_gait_profile("elderly"),
                         GAIT_PRESETS["elderly"])
        profile = GaitProfile(step_length=0.26, stride_length=0.52)
        self.assertIs(resolve_gait_profile(profile), profile)
        with self.assertRaises(KeyError):
            resolve_gait_profile("no_such_preset")
        with self.assertRaises(TypeError):
            resolve_gait_profile(42)

    def test_duration_for_distance_uses_effective_speed(self):
        # Canonical: 80 steps/min * 0.29 H/step = 0.3867 H/s.
        # 2 H at cruising speed + anticipation/settle allowance.
        dur = duration_for_distance(2 * H, H, CANONICAL_GAIT)
        travel = 2.0 / CANONICAL_GAIT.effective_speed / 0.85
        self.assertAlmostEqual(dur, travel + 0.45, places=3)

    def test_mud_profile_uses_mud_gait(self):
        gait = profile_to_gait(
            GaitProfile(terrain_response="mud"), terrain="mud")
        self.assertEqual(gait["overlap"], 0.35)
        self.assertLessEqual(gait["step_length_frac"], 0.15)

    def test_unimplemented_terrain_falls_back_visibly(self):
        gait = profile_to_gait(GaitProfile(terrain_response="stairs"))
        self.assertEqual(gait["terrain_response"], "stairs")
        self.assertEqual(gait["overlap"], GAIT_DEFAULT["overlap"])


class TestWalkPose(unittest.TestCase):
    def test_legacy_output_unchanged(self):
        phase = 0.7
        pose = walk_pose(phase)
        s, c = math.sin(phase), math.cos(phase)
        self.assertAlmostEqual(pose["thigh_l"], 0.5 * s)
        self.assertAlmostEqual(pose["thigh_r"], -0.5 * s)
        self.assertAlmostEqual(pose["knee_l"], max(0.0, -0.9 * c) + 0.15)
        self.assertAlmostEqual(pose["arm_l"], -0.45 * s)
        self.assertAlmostEqual(pose["bob"], 10.0 * abs(s))
        self.assertEqual(pose["torso_lean"], 0.08)

    def test_profile_drives_thigh_from_step(self):
        # Thigh amplitude = asin(half-step / leg): a shorter step
        # swings less. Phase pi/2 -> sin = 1.
        canonical = walk_pose(math.pi / 2, profile="canonical")
        elderly = walk_pose(math.pi / 2, profile="elderly")
        self.assertGreater(canonical["thigh_l"], elderly["thigh_l"])
        self.assertGreater(elderly["thigh_l"], 0.0)

    def test_profile_arm_modes(self):
        phase = math.pi / 2
        swing = walk_pose(phase, profile="canonical")
        restrained = walk_pose(phase, profile="elderly")
        self.assertGreater(abs(swing["arm_l"]), abs(restrained["arm_l"]))
        carrying = walk_pose(phase, profile=GaitProfile(arm_pose="carrying"))
        self.assertEqual(carrying["arm_l"], carrying["arm_r"])
        self.assertEqual(carrying["elbow_l"], 0.90)

    def test_head_stability_scales_bob(self):
        phase = math.pi / 2
        stable = walk_pose(phase, profile=GaitProfile(head_stability=1.0))
        loose = walk_pose(phase, profile=GaitProfile(head_stability=0.0))
        self.assertLess(stable["bob"], loose["bob"])

    def test_posture_drives_lean(self):
        stooped = walk_pose(0.0, profile="elderly")
        upright = walk_pose(0.0, profile="canonical")
        self.assertGreater(stooped["torso_lean"], upright["torso_lean"])


class TestStateMachine(unittest.TestCase):
    def test_valid_walk_turn_walk_plan(self):
        plan = plan_locomotion([
            {"state": "IDLE", "duration": 1.0},
            {"state": "START_WALK", "duration": 0.3, "direction": 1},
            {"state": "WALK", "duration": 3.0, "direction": 1},
            {"state": "STOP_WALK", "duration": 0.3},
            {"state": "TURN", "duration": 0.35},
            {"state": "START_WALK", "duration": 0.3, "direction": -1},
            {"state": "WALK", "duration": 3.0, "direction": -1},
            {"state": "STOP_WALK", "duration": 0.3},
            {"state": "IDLE", "duration": 1.0},
        ])
        self.assertEqual(plan[0]["start"], 0.0)
        self.assertAlmostEqual(plan[-1]["end"], 9.55)
        self.assertEqual(state_at(plan, 0.5), LocomotionState.IDLE)
        self.assertEqual(state_at(plan, 2.0), LocomotionState.WALK)
        self.assertEqual(state_at(plan, 4.7), LocomotionState.TURN)

    def test_illegal_transition_rejected(self):
        with self.assertRaises(ValueError):
            plan_locomotion([
                {"state": "IDLE", "duration": 1.0},
                {"state": "START_WALK", "duration": 0.3, "direction": 1},
                {"state": "WALK", "duration": 1.0, "direction": 1},
                {"state": "TURN", "duration": 0.35},
            ])

    def test_run_must_stop_before_turn(self):
        with self.assertRaises(ValueError):
            plan_locomotion([
                {"state": "IDLE", "duration": 1.0},
                {"state": "START_RUN", "duration": 0.3, "direction": 1},
                {"state": "RUN", "duration": 1.0, "direction": 1},
                {"state": "TURN", "duration": 0.35},
            ])

    def test_direction_change_without_turn_rejected(self):
        with self.assertRaises(ValueError):
            plan_locomotion([
                {"state": "IDLE", "duration": 1.0},
                {"state": "START_WALK", "duration": 0.3, "direction": 1},
                {"state": "WALK", "duration": 1.0, "direction": 1},
                {"state": "STOP_WALK", "duration": 0.3},
                {"state": "START_WALK", "duration": 0.3, "direction": -1},
                {"state": "WALK", "duration": 1.0, "direction": -1},
            ])

    def test_direction_change_with_cut_allowed(self):
        plan = plan_locomotion([
            {"state": "WALK", "duration": 1.0, "direction": 1,
             "cut_before": True},
            {"state": "STOP_WALK", "duration": 0.3},
            {"state": "START_WALK", "duration": 0.3, "direction": -1,
             "cut_before": True},
            {"state": "WALK", "duration": 1.0, "direction": -1},
        ])
        self.assertEqual(len(plan), 4)

    def test_plan_cannot_start_mid_walk_without_cut(self):
        with self.assertRaises(ValueError):
            plan_locomotion([{"state": "WALK", "duration": 1.0,
                              "direction": 1}])

    def test_terrain_adaptation_transitions(self):
        plan = plan_locomotion([
            {"state": "IDLE", "duration": 0.5},
            {"state": "START_WALK", "duration": 0.3, "direction": 1},
            {"state": "WALK", "duration": 1.0, "direction": 1},
            {"state": "TERRAIN_ADAPTATION", "duration": 1.0,
             "direction": 1},
            {"state": "WALK", "duration": 1.0, "direction": 1},
            {"state": "STOP_WALK", "duration": 0.3},
            {"state": "IDLE", "duration": 0.5},
        ])
        self.assertEqual(state_at(plan, 2.5),
                         LocomotionState.TERRAIN_ADAPTATION)


class TestFacingGuards(unittest.TestCase):
    def test_visible_turn_passes_continuity(self):
        char = Stickman(height=560)
        char.set_pose(facing=1)
        fn = P.turn_to(char, -1, duration=0.35)
        frames = sample_primitive(fn, char, 0.35, 24.0)
        self.assertEqual(check_facing_continuity(frames), [])

    def test_instant_flip_is_flagged(self):
        frames = [
            {"_t": 0.0, "_facing": 1, "_turn_u": 0.0},
            {"_t": 0.042, "_facing": -1, "_turn_u": 0.0},
        ]
        bad = check_facing_continuity(frames)
        self.assertEqual(len(bad), 1)

    def test_flip_at_a_cut_is_allowed(self):
        frames = [
            {"_t": 0.0, "_facing": 1, "_turn_u": 0.0},
            {"_t": 0.042, "_facing": -1, "_turn_u": 0.0},
        ]
        self.assertEqual(check_facing_continuity(frames, cut_times=[0.02]),
                         [])

    def test_walk_facing_matches_travel(self):
        char = Stickman(height=560)
        dur = duration_for_distance(2 * H, H, "canonical")
        fn = P.walk_to(char, 300, 1420, dur, GROUND_Y, profile="canonical")
        frames = sample_primitive(fn, char, dur, 24.0)
        self.assertEqual(check_facing_continuity(frames), [])
        self.assertEqual(check_facing_vs_travel(frames), [])

    def test_backwards_walk_is_flagged(self):
        frames = [
            {"_t": i * 0.042, "_facing": -1, "_turn_u": 0.0,
             "hip": (100.0 + 10.0 * i, 700.0)}
            for i in range(5)
        ]
        self.assertEqual(len(check_facing_vs_travel(frames)), 1)

    def test_single_frame_hip_shift_is_not_flagged(self):
        # The anticipation crouch dips the hip back for one frame;
        # that is postural, not backwards travel.
        frames = [
            {"_t": 0.0, "_facing": 1, "_turn_u": 0.0,
             "hip": (100.0, 700.0)},
            {"_t": 0.042, "_facing": 1, "_turn_u": 0.0,
             "hip": (97.0, 700.0)},
            {"_t": 0.084, "_facing": 1, "_turn_u": 0.0,
             "hip": (100.0, 700.0)},
            {"_t": 0.126, "_facing": 1, "_turn_u": 0.0,
             "hip": (110.0, 700.0)},
        ]
        self.assertEqual(check_facing_vs_travel(frames), [])

    def test_mid_turn_travel_is_exempt(self):
        frames = [
            {"_t": 0.0, "_facing": -1, "_turn_u": 0.0,
             "hip": (100.0, 700.0)},
            {"_t": 0.042, "_facing": -1, "_turn_u": 0.5,
             "hip": (110.0, 700.0)},
        ]
        self.assertEqual(check_facing_vs_travel(frames), [])


class TestMeasurement(unittest.TestCase):
    def _measure(self, name, distance_heights=2.0):
        profile = resolve_gait_profile(name)
        dur = duration_for_distance(distance_heights * H, H, profile)
        char = Stickman(height=560)
        fn = P.walk_to(char, 300, 300 + distance_heights * H, dur,
                       GROUND_Y, profile=name)
        travel = _travel_frames(char, fn, dur)
        return profile, measure_locomotion(travel, 24.0, H, GROUND_Y)

    def test_canonical_walk_closes_the_loop(self):
        profile, m = self._measure("canonical")
        self.assertAlmostEqual(m.step_length, profile.step_length,
                               delta=0.01)
        self.assertAlmostEqual(m.stride_length, profile.stride_length,
                               delta=0.02)
        self.assertAlmostEqual(m.cadence, profile.cadence, delta=8.0)
        self.assertLess(m.head_vertical_displacement, 0.01)
        self.assertLess(m.foot_sliding, 0.01)
        self.assertGreater(m.left_right_symmetry, 0.95)
        # The swing phase legitimately reaches ~14 deg/frame (a
        # smooth ramp, not a pop); the bound catches pops (the v7
        # settle jerk was ~45 deg/frame-equivalent).
        self.assertLess(m.joint_angle_continuity, 25.0)
        self.assertAlmostEqual(m.root_movement, 2.0, delta=0.01)
        self.assertGreater(m.stance_duration, 0.2)

    def test_elderly_walk_closes_the_loop(self):
        profile, m = self._measure("elderly")
        self.assertAlmostEqual(m.step_length, profile.step_length,
                               delta=0.01)
        self.assertAlmostEqual(m.cadence, profile.cadence, delta=6.0)
        self.assertLess(m.head_vertical_displacement, 0.01)

    def test_soldier_walk_closes_the_loop(self):
        profile, m = self._measure("soldier")
        self.assertAlmostEqual(m.step_length, profile.step_length,
                               delta=0.01)
        self.assertAlmostEqual(m.cadence, profile.cadence, delta=10.0)

    def test_giant_walk_closes_the_loop(self):
        profile, m = self._measure("giant")
        self.assertAlmostEqual(m.step_length, profile.step_length,
                               delta=0.01)
        self.assertAlmostEqual(m.cadence, profile.cadence, delta=6.0)

    def test_variants_do_not_move_identically(self):
        _, canonical = self._measure("canonical")
        _, elderly = self._measure("elderly")
        _, soldier = self._measure("soldier")
        self.assertLess(elderly.cadence, canonical.cadence)
        self.assertGreater(soldier.cadence, canonical.cadence)
        self.assertLess(elderly.step_length, canonical.step_length)

    def test_step_in_reference_band(self):
        # RicksClips reference: steps ~1/4-1/3 H.
        _, m = self._measure("canonical")
        self.assertGreaterEqual(m.step_length, 0.25)
        self.assertLessEqual(m.step_length, 0.33)

    def test_short_walk_cadence_uses_steady_interval(self):
        # A 2.5-step walk has only 2 positive intervals (two strikes
        # coincide at the sample start); the cadence must come from
        # the steady interval, not from a span that counts the
        # simultaneous pair as a step.
        profile = resolve_gait_profile("canonical")
        dur = duration_for_distance(400, H, profile)
        char = Stickman(height=560)
        fn = P.walk_to(char, 560, 960, dur, GROUND_Y, profile="canonical")
        travel = _travel_frames(char, fn, dur)
        m = measure_locomotion(travel, 24.0, H, GROUND_Y)
        self.assertAlmostEqual(m.cadence, profile.cadence, delta=8.0)
        self.assertAlmostEqual(m.step_length, profile.step_length,
                               delta=0.01)

    def test_measure_requires_footfalls(self):
        char = Stickman(height=560)
        P.standing(char, 500, GROUND_Y)
        frames = [{"_t": i / 24.0, "head": (500.0, 400.0),
                   "hip": (500.0, 700.0),
                   "foot_l": (430.0, GROUND_Y),
                   "foot_r": (570.0, GROUND_Y),
                   "knee_l": (430.0, 800.0),
                   "knee_r": (570.0, 800.0)} for i in range(24)]
        with self.assertRaises(ValueError):
            measure_locomotion(frames, 24.0, H, GROUND_Y)

    def test_footfall_times_for_audio_sync(self):
        profile = resolve_gait_profile("canonical")
        dur = duration_for_distance(2 * H, H, profile)
        char = Stickman(height=560)
        fn = P.walk_to(char, 300, 1420, dur, GROUND_Y, profile="canonical")
        frames = sample_primitive(fn, char, dur, 24.0)
        falls = footfall_times(frames, 24.0, GROUND_Y)
        self.assertGreaterEqual(len(falls), 4)
        times = [f["t"] for f in falls]
        self.assertEqual(times, sorted(times))
        feet = {f["foot"] for f in falls}
        self.assertEqual(feet, {"l", "r"})


class TestProfilePrimitives(unittest.TestCase):
    def test_character_carried_profile_is_used(self):
        char = Stickman(height=560, gait_profile="elderly")
        profile = resolve_gait_profile("elderly")
        dur = duration_for_distance(2 * H, H, profile)
        fn = P.walk_to(char, 300, 1420, dur, GROUND_Y)
        travel = _travel_frames(char, fn, dur)
        m = measure_locomotion(travel, 24.0, H, GROUND_Y)
        self.assertAlmostEqual(m.step_length, 0.22, delta=0.01)

    def test_explicit_profile_beats_carried_profile(self):
        char = Stickman(height=560, gait_profile="elderly")
        profile = resolve_gait_profile("soldier")
        dur = duration_for_distance(2 * H, H, profile)
        fn = P.walk_to(char, 300, 1420, dur, GROUND_Y, profile="soldier")
        travel = _travel_frames(char, fn, dur)
        m = measure_locomotion(travel, 24.0, H, GROUND_Y)
        self.assertAlmostEqual(m.step_length, 0.30, delta=0.01)

    def test_task_arm_pose_reduces_swing(self):
        def arm_range(profile):
            char = Stickman(height=560)
            dur = duration_for_distance(2 * H, H, profile)
            fn = P.walk_to(char, 300, 1420, dur, GROUND_Y, profile=profile)
            frames = _travel_frames(char, fn, dur)
            # Hand position RELATIVE to the hip: the absolute x range
            # is dominated by the 1120 px of travel.
            rel = [f["hand_l"][0] - f["hip"][0] for f in frames]
            return max(rel) - min(rel)
        swing = arm_range(GaitProfile(arm_pose="swing"))
        task = arm_range(GaitProfile(arm_pose="task"))
        self.assertLess(task, swing)

    def test_head_stability_damps_travel_bob(self):
        def head_p2p(head_stability):
            profile = GaitProfile(head_stability=head_stability)
            char = Stickman(height=560)
            dur = duration_for_distance(2 * H, H, profile)
            fn = P.walk_to(char, 300, 1420, dur, GROUND_Y, profile=profile)
            travel = _travel_frames(char, fn, dur)
            ys = [f["head"][1] for f in travel]
            return max(ys) - min(ys)
        self.assertLess(head_p2p(1.0), head_p2p(0.0))

    def test_mud_profile_delegates_to_mud(self):
        char = Stickman(height=560)
        profile = GaitProfile(terrain_response="mud")
        fn = P.walk_to(char, 300, 700, 3.0, GROUND_Y, profile=profile)
        frames = sample_primitive(fn, char, 3.0, 24.0)
        sunk = [f for f in frames
                if f["foot_l"][1] > GROUND_Y + 1.0
                or f["foot_r"][1] > GROUND_Y + 1.0]
        self.assertGreater(len(sunk), 0)

    def test_run_profile_has_flight_phase(self):
        char = Stickman(height=560)
        fn = P.run_to(char, 300, 900, 2.0, GROUND_Y, profile="canonical")
        frames = sample_primitive(fn, char, 2.0, 24.0)
        airborne = [f for f in frames
                    if f["foot_l"][1] < GROUND_Y - 2.0
                    and f["foot_r"][1] < GROUND_Y - 2.0]
        self.assertGreater(len(airborne), 0)

    def test_seated_idle_keeps_seat_and_targets(self):
        char = Stickman(height=560)
        P.standing(char, 500, GROUND_Y)
        sit = P.sit_at_desk(char, 500, GROUND_Y - 150.0, 1.0, GROUND_Y)
        sit(1.0)
        foot_l, foot_r = char.foot_target_l, char.foot_target_r
        hand_r = char.hand_target_r
        idle = P.seated_idle(char, 2.0)
        bobs = []
        for i in range(49):
            idle(i / 24.0)
            bobs.append(char.pose["bob"])
        self.assertEqual(char.foot_target_l, foot_l)
        self.assertEqual(char.foot_target_r, foot_r)
        self.assertEqual(char.hand_target_r, hand_r)
        self.assertGreater(max(bobs) - min(bobs), 0.0)
        # Still seated: the hip stays well below standing height.
        self.assertGreater(char.joints()["hip"][1], GROUND_Y - 260.0)


if __name__ == "__main__":
    unittest.main()
