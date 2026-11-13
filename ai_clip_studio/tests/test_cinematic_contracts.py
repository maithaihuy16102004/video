"""Tests for ai_clip_studio.cinematic_contracts (ATLAS-owned).

Locks the shared interfaces Subagents A and B code against: gait
profile defaults/ranges, step-vs-stride separation, camera mode
defaults and traceability, static-transform constancy, expression
alignment, and the location-trait contract.
"""

import unittest

from ai_clip_studio.cinematic_contracts import (
    BBOX_KINDS,
    CANONICAL_GAIT,
    MICRO_ANIMATIONS,
    REQUIRED_LOCATION_TRAITS,
    CameraDirective,
    CameraMode,
    CameraValidation,
    DEFAULT_CAMERA_MODE,
    ExpressionTransition,
    GaitProfile,
    LocomotionMetrics,
    LocomotionState,
)


class TestGaitProfile(unittest.TestCase):
    def test_canonical_defaults_match_reference_targets(self):
        self.assertGreaterEqual(CANONICAL_GAIT.step_length, 0.25)
        self.assertLessEqual(CANONICAL_GAIT.step_length, 0.33)
        self.assertGreaterEqual(CANONICAL_GAIT.cadence, 70.0)
        self.assertLessEqual(CANONICAL_GAIT.cadence, 90.0)
        self.assertEqual(CANONICAL_GAIT.head_stability, 1.0)
        self.assertEqual(CANONICAL_GAIT.locomotion_style, "canonical")

    def test_stride_is_full_cycle_not_one_step(self):
        # Symmetric canonical gait: stride == 2 * step, but the two
        # fields stay independent measurements.
        self.assertAlmostEqual(CANONICAL_GAIT.stride_length,
                               2 * CANONICAL_GAIT.step_length)
        limp = GaitProfile(step_length=0.29, stride_length=0.52,
                           locomotion_style="limp")
        self.assertNotAlmostEqual(limp.stride_length,
                                  2 * limp.step_length)

    def test_effective_speed_derived_from_cadence_and_step(self):
        g = GaitProfile(step_length=0.30, cadence=60.0)
        self.assertAlmostEqual(g.effective_speed, 0.30)
        g2 = GaitProfile(step_length=0.30, cadence=60.0,
                         movement_speed=0.5)
        self.assertAlmostEqual(g2.effective_speed, 0.5)

    def test_validation_rejects_bad_values(self):
        for kwargs in ({"step_length": 0.01}, {"step_length": 0.9},
                       {"cadence": 20.0}, {"cadence": 300.0},
                       {"head_stability": 1.5}, {"fatigue": -0.1},
                       {"body_mass": 0.0},
                       {"step_length": 0.30, "stride_length": 0.20}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    GaitProfile(**kwargs)

    def test_profiles_differ_without_breaking_schema(self):
        elder = GaitProfile(step_length=0.20, stride_length=0.40,
                            cadence=60.0, posture="stooped",
                            head_stability=0.8,
                            locomotion_style="elderly")
        soldier = GaitProfile(step_length=0.33, stride_length=0.66,
                              cadence=90.0, posture="military",
                              locomotion_style="soldier")
        self.assertNotEqual(elder, soldier)
        self.assertNotEqual(elder, CANONICAL_GAIT)

    def test_locomotion_states_complete(self):
        names = {s.name for s in LocomotionState}
        self.assertEqual(names, {"IDLE", "START_WALK", "WALK",
                                 "STOP_WALK", "TURN", "START_RUN",
                                 "RUN", "STOP_RUN",
                                 "TERRAIN_ADAPTATION"})

    def test_metrics_keep_step_and_stride_separate(self):
        m = LocomotionMetrics(
            step_length=0.29, stride_length=0.58, cadence=80.0,
            head_vertical_displacement=0.02, foot_sliding=0.001,
            stance_duration=0.4, joint_angle_continuity=2.0,
            root_movement=1.16, left_right_symmetry=0.98)
        d = m.as_dict()
        self.assertEqual(d["step_length"], 0.29)
        self.assertEqual(d["stride_length"], 0.58)


class TestCameraContracts(unittest.TestCase):
    def test_default_mode_is_static_anchored(self):
        self.assertIs(DEFAULT_CAMERA_MODE, CameraMode.STATIC_ANCHORED)
        d = CameraDirective(source="plan_shots:SC01_SH01")
        self.assertIs(d.mode, CameraMode.STATIC_ANCHORED)
        self.assertEqual(d.anchor, "scene")

    def test_directive_requires_traceable_source(self):
        with self.assertRaises(ValueError):
            CameraDirective(source="")

    def test_static_requires_equal_transforms(self):
        with self.assertRaises(ValueError):
            CameraDirective(mode=CameraMode.STATIC_ANCHORED,
                            source="test",
                            start_transform=(0, 2.0, 4.8),
                            end_transform=(0, 2.0, 4.0))
        ok = CameraDirective(mode=CameraMode.STATIC_ANCHORED,
                             source="test",
                             start_transform=(0, 2.0, 4.8),
                             end_transform=(0, 2.0, 4.8))
        self.assertEqual(ok.start_transform, ok.end_transform)

    def test_scripted_modes_allow_movement(self):
        d = CameraDirective(mode=CameraMode.SCRIPTED_DOLLY,
                            anchor="CHAR_A", source="script:CAMERA_01",
                            start_transform=(0, 2.0, 6.0),
                            end_transform=(0, 2.0, 4.0))
        self.assertIs(d.mode, CameraMode.SCRIPTED_DOLLY)

    def test_validation_static_check(self):
        v = CameraValidation(
            position=(0, 2.0, 4.8), orientation=(0, 0, 0),
            projection_matrix=(1, 0, 0, 0), fov_deg=46.0,
            crop_rect=None, target_anchor="scene",
            start_transform=(0, 2.0, 4.8), end_transform=(0, 2.0, 4.8))
        self.assertTrue(v.is_static())
        v2 = CameraValidation(
            position=(0, 2.0, 4.8), orientation=(0, 0, 0),
            projection_matrix=(1, 0, 0, 0), fov_deg=46.0,
            crop_rect=None, target_anchor="scene",
            start_transform=(0, 2.0, 4.8), end_transform=(0, 2.0, 4.0))
        self.assertFalse(v2.is_static())


class TestExpressionAndEnvironmentContracts(unittest.TestCase):
    def test_micro_animations_set(self):
        self.assertIn("blink", MICRO_ANIMATIONS)
        self.assertIn("lipsync", MICRO_ANIMATIONS)
        self.assertIn("breathing", MICRO_ANIMATIONS)

    def test_expression_transition_alignment(self):
        t = ExpressionTransition("neutral", "fear", align="cut")
        self.assertEqual(t.align, "cut")
        with self.assertRaises(ValueError):
            ExpressionTransition("neutral", "fear", align="morph")

    def test_required_location_traits(self):
        self.assertIn("landmarks", REQUIRED_LOCATION_TRAITS)
        self.assertIn("negative_constraints", REQUIRED_LOCATION_TRAITS)
        self.assertEqual(len(REQUIRED_LOCATION_TRAITS), 11)

    def test_bbox_kinds_separate(self):
        self.assertEqual(BBOX_KINDS, ("head", "hair", "full_character",
                                      "costume"))


if __name__ == "__main__":
    unittest.main()
