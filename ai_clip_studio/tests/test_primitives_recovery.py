"""Tests for the recovery primitives in animation/primitives.py.

Every test runs the REAL rig (Stickman.joints) and asserts on
measured joint geometry: knee angles, foot contact, pen-tip contact,
bone lengths. No mocked joints.
"""
from __future__ import annotations

import math
import unittest

from ai_clip_studio.animation import primitives as P
from ai_clip_studio.animation.rig import (
    Stickman,
    check_bone_lengths,
    check_foot_contact,
)

GROUND_Y = 1000.0
# Paper staged INSIDE the arm's reach annulus: in front of the seated
# character (chair_x 960, shoulder ~979,692), on the desk (top 760),
# with the writing line 50-150 px from the shoulder. A hand target
# closer than |upper_arm - lower_arm| (~13 px) or farther than the
# full reach (~158 px) breaks the rig's IK (ik_2bone has no
# too-close clamp -- a rig.py hardening item, outside this module's
# ownership, flagged in the handoff). Staging must respect the
# annulus; the primitives assume it.
PAPER = {"x": 1040.0, "y": 770.0, "w": 120.0, "h": 70.0}


def _char(x=960.0, name="ana"):
    char = Stickman(height=560, name=name, moustache_style="none")
    P.standing(char, x, GROUND_Y)
    return char


def _knee_angle(joints, side):
    """Interior knee angle (degrees) from hip/knee/foot positions."""
    hip = joints["hip"]
    knee = joints["knee_" + side]
    foot = joints["foot_" + side]
    v1 = (hip[0] - knee[0], hip[1] - knee[1])
    v2 = (foot[0] - knee[0], foot[1] - knee[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag = math.hypot(*v1) * math.hypot(*v2)
    if mag < 1e-9:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / mag))))


def _pen_tip(joints, char, hand="r"):
    return P.pen_tip_position(joints["hand_" + hand],
                              joints["facing"], char.H)


class TestSitAndStand(unittest.TestCase):
    def test_sit_at_desk_completion(self):
        char = _char()
        fn = P.sit_at_desk(char, chair_x=960.0, seat_y=820.0,
                           duration=1.0, ground_y=GROUND_Y,
                           desk={"x": 960.0, "top_y": 760.0})
        joints = P.pose_at_completion(fn, char, 1.0)
        # Hips at chair height.
        self.assertAlmostEqual(joints["hip"][1], 820.0, places=3)
        # Knees ~90 degrees (geometry allows a band; both legs).
        for side in ("l", "r"):
            angle = _knee_angle(joints, side)
            self.assertTrue(70.0 <= angle <= 110.0,
                            f"knee_{side}={angle:.1f} deg")
        # Feet planted on the ground.
        self.assertEqual(check_foot_contact(joints, GROUND_Y, tol=3.0), [])
        # Right hand on the desk top.
        self.assertAlmostEqual(joints["hand_r"][1], 760.0, places=3)
        # Bones intact.
        self.assertEqual(check_bone_lengths(joints, char), [])

    def test_sit_without_desk_hands_on_knees(self):
        char = _char()
        fn = P.sit_at_desk(char, chair_x=960.0, seat_y=820.0,
                           duration=1.0, ground_y=GROUND_Y)
        joints = P.pose_at_completion(fn, char, 1.0)
        self.assertAlmostEqual(joints["hip"][1], 820.0, places=3)
        self.assertEqual(check_foot_contact(joints, GROUND_Y, tol=3.0), [])

    def test_stand_from_chair_returns_to_standing(self):
        char = _char()
        P.pose_at_completion(
            P.sit_at_desk(char, 960.0, 820.0, 1.0, GROUND_Y), char, 1.0)
        joints = P.pose_at_completion(
            P.stand_from_chair(char, 1.0, GROUND_Y, chair_x=960.0),
            char, 1.0)
        reference = _char()
        ref_joints = reference.joints()
        for key in ("hip", "shoulder", "head", "foot_l", "foot_r"):
            self.assertAlmostEqual(joints[key][0], ref_joints[key][0],
                                   places=3)
            self.assertAlmostEqual(joints[key][1], ref_joints[key][1],
                                   places=3)


class TestPickUpAndPutAway(unittest.TestCase):
    def test_pick_up_ends_at_waist_hold(self):
        char = _char()
        fn = P.pick_up(char, (1000.0, GROUND_Y), 1.0, GROUND_Y,
                       hand="r", source="ground")
        joints = P.pose_at_completion(fn, char, 1.0)
        hold = P._waist_hold(char, GROUND_Y)
        self.assertAlmostEqual(joints["hand_r"][0], hold[0], places=3)
        self.assertAlmostEqual(joints["hand_r"][1], hold[1], places=3)
        self.assertEqual(check_bone_lengths(joints, char), [])

    def test_put_away_prop_reaches_pocket_continuously(self):
        char = _char()
        prop = {"x": 0.0, "y": 0.0}
        pocket = (930.0, 830.0)
        fn = P.put_away(char, pocket, 1.0, hand="r", prop=prop)
        prev = None
        max_jump = 0.0
        for i in range(25):
            fn(i / 24.0)
            pos = (prop["x"], prop["y"])
            if prev is not None:
                max_jump = max(max_jump, math.hypot(
                    pos[0] - prev[0], pos[1] - prev[1]))
            prev = pos
        self.assertEqual((prop["x"], prop["y"]), pocket)
        self.assertTrue(prop["released"])
        # No teleport: 24 steps over ~1 s, hand-speed bound.
        self.assertLess(max_jump, 50.0)


class TestWallet(unittest.TestCase):
    def test_open_close_wallet_open_u(self):
        char = _char()
        prop = {"open_u": 0.0}
        P.pose_at_completion(P.open_wallet(char, 1.0, prop=prop),
                             char, 1.0)
        self.assertEqual(prop["open_u"], 1.0)
        P.pose_at_completion(P.close_wallet(char, 1.0, prop=prop),
                             char, 1.0)
        self.assertEqual(prop["open_u"], 0.0)

    def test_open_wallet_hands_together(self):
        char = _char()
        joints = P.pose_at_completion(P.open_wallet(char, 1.0), char, 1.0)
        gap = math.hypot(joints["hand_l"][0] - joints["hand_r"][0],
                         joints["hand_l"][1] - joints["hand_r"][1])
        self.assertLess(gap, 60.0)
        self.assertEqual(check_bone_lengths(joints, char), [])


class TestWriting(unittest.TestCase):
    def _seated(self):
        char = _char()
        P.pose_at_completion(
            P.sit_at_desk(char, 960.0, 820.0, 1.0, GROUND_Y,
                          desk={"x": 960.0, "top_y": 760.0}),
            char, 1.0)
        return char

    def test_hold_pen_hovers_over_paper(self):
        char = self._seated()
        joints = P.pose_at_completion(
            P.hold_pen(char, (1080.0, 760.0), PAPER, 1.0), char, 1.0)
        tip = _pen_tip(joints, char)
        line_y = PAPER["y"] + 0.30 * PAPER["h"]
        self.assertAlmostEqual(tip[1], line_y - 12.0, places=3)
        self.assertTrue(PAPER["x"] <= tip[0] <= PAPER["x"] + PAPER["w"])

    def test_write_tip_stays_on_paper(self):
        char = self._seated()
        fn = P.write_on_paper(char, PAPER, 2.0, words=6)
        max_outside = 0.0
        for i in range(49):
            fn(2.0 * i / 48.0)
            joints = char.joints()
            tip = _pen_tip(joints, char)
            dx = max(PAPER["x"] - tip[0], 0.0,
                     tip[0] - (PAPER["x"] + PAPER["w"]))
            dy = max(PAPER["y"] - tip[1], 0.0,
                     tip[1] - (PAPER["y"] + PAPER["h"]))
            max_outside = max(max_outside, math.hypot(dx, dy))
            self.assertEqual(check_bone_lengths(joints, char), [])
        # The tip never leaves the paper rect (blend-in included).
        self.assertEqual(max_outside, 0.0)

    def test_sign_lifts_pen(self):
        char = self._seated()
        fn = P.sign_document(char, PAPER, 1.5)
        fn(1.5)
        joints = char.joints()
        tip = _pen_tip(joints, char)
        base_y = PAPER["y"] + 0.60 * PAPER["h"]
        self.assertAlmostEqual(tip[1], base_y - 30.0, places=1)


class TestHandOver(unittest.TestCase):
    def test_holder_switches_at_transfer_u(self):
        giver = _char(x=900.0, name="giver")
        receiver = _char(x=1050.0, name="receiver")
        receiver.pose["facing"] = -1
        prop = {"x": 0.0, "y": 0.0}
        fn = P.hand_over(giver, receiver, prop, 1.0)
        fn(0.3)
        self.assertEqual(prop["holder"], "giver")
        fn(0.9)
        self.assertEqual(prop["holder"], "receiver")
        joints = receiver.joints()
        self.assertAlmostEqual(prop["x"], joints["hand_l"][0],
                               delta=60.0)
        self.assertAlmostEqual(prop["y"], joints["hand_l"][1],
                               delta=60.0)


class TestWalkMudAndCarry(unittest.TestCase):
    def test_walk_mud_sinks_and_arrives(self):
        char = _char(x=800.0)
        fn = P.walk_mud(char, 800.0, 1100.0, 3.0, GROUND_Y)
        sunk_frames = 0
        for i in range(73):
            fn(3.0 * i / 72.0)
            joints = char.joints()
            if (joints["foot_l"][1] > GROUND_Y + 1.0
                    or joints["foot_r"][1] > GROUND_Y + 1.0):
                sunk_frames += 1
            self.assertEqual(check_bone_lengths(joints, char), [])
        self.assertGreater(sunk_frames, 0)
        joints = char.joints()
        self.assertAlmostEqual(joints["hip"][0], 1100.0, delta=30.0)

    def test_walk_mud_planted_feet_do_not_slide(self):
        char = _char(x=800.0)
        fn = P.walk_mud(char, 800.0, 1100.0, 3.0, GROUND_Y)
        # A planted foot keeps its x through one stance: measure the
        # x-range of each continuous on-ground segment. The shared
        # _locomote core lets the IK reach-clamp drag a planted foot
        # a few px as the hip advances (measured 3-4 px/stance);
        # that is not a sliding target, and the bound documents it.
        # One pass collects both feet (the primitive is stateful).
        samples = []
        for i in range(73):
            fn(3.0 * i / 72.0)
            joints = char.joints()
            samples.append((joints["foot_l"], joints["foot_r"]))
        for side_index, side in enumerate(("l", "r")):
            segments = []
            current = []
            for feet in samples:
                foot = feet[side_index]
                if foot[1] >= GROUND_Y - 2.0:
                    current.append(foot[0])
                elif current:
                    segments.append(current)
                    current = []
            if current:
                segments.append(current)
            self.assertGreater(len(segments), 0)
            for segment in segments:
                self.assertLess(max(segment) - min(segment), 6.0,
                                f"foot_{side} slides within a stance")

    def test_carry_bag_hangs_below_hand(self):
        char = _char()
        bag = {"x": 0.0, "y": 0.0}
        joints = P.pose_at_completion(
            P.carry_bag(char, 1.0, hand="r", bag=bag), char, 1.0)
        self.assertGreater(bag["y"], joints["hand_r"][1])


class TestLookReactAndSmall(unittest.TestCase):
    def test_look_at_point_orients_head(self):
        char = _char()
        P.pose_at_completion(P.look_at_point(char, (1400.0, 700.0), 1.0),
                             char, 1.0)
        self.assertGreater(char.pose["head_look"], 0.0)
        self.assertLessEqual(char.pose["head_look"], 0.6)

    def test_react_kinds(self):
        for kind in ("startle", "flinch", "duck"):
            char = _char()
            joints = P.pose_at_completion(
                P.react_event(char, 1.0, kind=kind), char, 1.0)
            self.assertGreater(char.pose["torso_lean"], 0.0, kind)
            self.assertEqual(check_bone_lengths(joints, char), [], kind)

    def test_raise_hand_above_shoulder(self):
        char = _char()
        joints = P.pose_at_completion(P.raise_hand(char, 1.0), char, 1.0)
        self.assertLess(joints["hand_r"][1], joints["shoulder"][1])

    def test_head_tilt_holds_angle(self):
        char = _char()
        P.pose_at_completion(P.head_tilt(char, 1.0, head_look=0.30),
                             char, 1.0)
        self.assertAlmostEqual(char.pose["head_look"], 0.30, places=3)

    def test_breathe_returns_to_incoming_pose(self):
        char = _char()
        before = char.joints()
        fn = P.breathe(char, 2.0, breaths=2)
        fn(2.0)
        after = char.joints()
        for key in ("hip", "shoulder", "head", "foot_l", "foot_r"):
            self.assertAlmostEqual(after[key][0], before[key][0],
                                   places=3)
            self.assertAlmostEqual(after[key][1], before[key][1],
                                   places=3)


class TestRegistryAndDispatch(unittest.TestCase):
    def test_all_recovery_primitives_registered(self):
        for name in ("sit_at_desk", "stand_from_chair", "pick_up",
                     "open_wallet", "close_wallet", "hold_pen",
                     "write_on_paper", "sign_document", "hand_over",
                     "walk_mud", "carry_bag", "look_at_point",
                     "react_event", "raise_hand", "head_tilt",
                     "breathe", "put_away"):
            self.assertIn(name, P.PRIMITIVES)
            self.assertIn(name, P.PRIMITIVE_COMPLETION)

    def test_compile_actions_dispatches_new_types(self):
        chars = {"ana": _char(), "ben": _char(x=1050.0, name="ben")}
        timeline = P.compile_actions([
            {"type": "sit_at_desk", "char": "ana", "start": 0.0,
             "duration": 1.0, "chair_x": 960.0, "seat_y": 820.0,
             "ground_y": GROUND_Y},
            {"type": "write_on_paper", "char": "ana", "start": 1.0,
             "duration": 1.0, "paper": PAPER},
            {"type": "hand_over", "char": "ana", "other": "ben",
             "start": 2.0, "duration": 1.0,
             "prop": {"x": 0.0, "y": 0.0}},
        ], chars, fps=24)
        self.assertGreater(len(timeline), 48)
        last = timeline[max(timeline)]
        self.assertIn("ana", last)
        self.assertIn("ben", last)

    def test_compile_actions_rejects_unknown(self):
        with self.assertRaises(ValueError):
            P.compile_actions(
                [{"type": "teleport", "char": "ana", "start": 0.0,
                  "duration": 1.0}], {"ana": _char()})

    def test_composed_sequence_keeps_bones_and_is_deterministic(self):
        def run():
            char = _char()
            sequence = [
                P.sit_at_desk(char, 960.0, 820.0, 1.0, GROUND_Y,
                              desk={"x": 960.0, "top_y": 760.0}),
                P.hold_pen(char, (1080.0, 760.0), PAPER, 1.0),
                P.write_on_paper(char, PAPER, 1.0),
                P.sign_document(char, PAPER, 1.0),
                P.stand_from_chair(char, 1.0, GROUND_Y, chair_x=960.0),
            ]
            frames = []
            for fn in sequence:
                for i in range(13):
                    fn(i / 12.0)
                    joints = char.joints()
                    self.assertEqual(check_bone_lengths(joints, char), [])
                    frames.append((joints["hip"], joints["hand_r"]))
            return frames
        first = run()
        second = run()
        self.assertEqual(first, second)


class TestIkTooCloseClamp(unittest.TestCase):
    """W4 rig hardening: a target closer than |l1-l2| must fold the
    chain, never stretch bone 1 (the old code put the middle joint
    past l1 on the anchor->target line with zero fold height)."""

    def test_too_close_target_keeps_bone1_exact_with_real_fold(self):
        import math
        from ai_clip_studio.animation.rig import ik_2bone
        mx, my = ik_2bone(0.0, 0.0, 5.0, 0.0, 100.0, 90.0)
        self.assertAlmostEqual(math.hypot(mx, my), 100.0, places=6)
        # Real fold: the middle joint leaves the anchor->target line.
        self.assertGreater(abs(my), 1.0)

    def test_normal_and_far_targets_unchanged(self):
        import math
        from ai_clip_studio.animation.rig import ik_2bone
        mx, my = ik_2bone(0.0, 0.0, 150.0, 0.0, 100.0, 90.0)
        self.assertAlmostEqual(math.hypot(mx, my), 100.0, places=6)
        self.assertAlmostEqual(math.hypot(mx - 150.0, my), 90.0, places=6)
        mx, my = ik_2bone(0.0, 0.0, 300.0, 0.0, 100.0, 90.0)
        self.assertAlmostEqual(math.hypot(mx, my), 100.0, places=6)


if __name__ == "__main__":
    unittest.main()
