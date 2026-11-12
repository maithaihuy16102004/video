"""Unit tests for ai_clip_studio.look_targets (stdlib unittest, no network).

Run from ~/workspace/video-16x9-v2/:
    python3 -m unittest ai_clip_studio.tests.test_look_targets -v

Tests verify the frozen constants are sane (monotone curves, in-range
values), the Hermite curve math matches its endpoints, the fps conversions,
and the frame measurement helpers on synthetic frames.
"""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_clip_studio import look_targets as lt


class TestGradeCurve(unittest.TestCase):
    def test_knots_match_params(self):
        for params in (lt.GRADE_DAY, lt.GRADE_GOLDEN, lt.GRADE_DAY_GENTLE, lt.GRADE_GOLDEN_GENTLE):
            self.assertEqual(len(params.ky), len(lt.KX))
            self.assertEqual(len(params.sat), 3)
            # Curve knots strictly increasing (monotone grade).
            self.assertTrue(all(b > a for a, b in zip(params.ky, params.ky[1:])))

    def test_curve_endpoints(self):
        for params in (lt.GRADE_DAY, lt.GRADE_GOLDEN):
            self.assertAlmostEqual(lt.grade_curve(0.0, params), params.ky[0], places=9)
            self.assertAlmostEqual(lt.grade_curve(1.0, params), 1.0, places=9)

    def test_curve_passes_through_knots(self):
        for params in (lt.GRADE_DAY, lt.GRADE_GOLDEN_GENTLE):
            for x, y in zip(lt.KX, params.ky):
                self.assertAlmostEqual(lt.grade_curve(x, params), y, places=6)

    def test_curve_monotone_on_dense_samples(self):
        xs = np.linspace(0, 1, 101)
        for params in (lt.GRADE_DAY, lt.GRADE_GOLDEN, lt.GRADE_DAY_GENTLE, lt.GRADE_GOLDEN_GENTLE):
            ys = [lt.grade_curve(float(x), params) for x in xs]
            self.assertTrue(all(b >= a - 1e-9 for a, b in zip(ys, ys[1:])))

    def test_curve_clamps_out_of_range(self):
        self.assertEqual(lt.grade_curve(-0.5, lt.GRADE_DAY), lt.grade_curve(0.0, lt.GRADE_DAY))
        self.assertEqual(lt.grade_curve(1.5, lt.GRADE_DAY), lt.grade_curve(1.0, lt.GRADE_DAY))

    def test_tangents_finite_and_positive(self):
        for params in (lt.GRADE_DAY, lt.GRADE_GOLDEN):
            m = lt.mono_tangents(params.ky)
            self.assertEqual(len(m), len(lt.KX))
            self.assertTrue(all(np.isfinite(v) and v >= 0 for v in m))

    def test_vignette_ranges(self):
        for params in (lt.GRADE_DAY, lt.GRADE_GOLDEN, lt.GRADE_DAY_GENTLE, lt.GRADE_GOLDEN_GENTLE):
            k, r0 = params.vig
            self.assertGreater(k, 0)
            self.assertLess(k, 1)
            self.assertGreater(r0, 0)
            self.assertLess(r0, 1)


class TestLightDepthInkConstants(unittest.TestCase):
    def test_sky_stops(self):
        for sky in (lt.SKY_DAY, lt.SKY_GOLDEN):
            self.assertEqual(len(sky["elevations_deg"]), 5)
            self.assertEqual(len(sky["colors"]), 5)
            self.assertTrue(all(c.startswith("#") and len(c) == 7 for c in sky["colors"]))
            self.assertTrue(all(b > a for a, b in zip(sky["elevations_deg"], sky["elevations_deg"][1:])))

    def test_fog_ranges(self):
        for fog in (lt.FOG_DAY, lt.FOG_GOLDEN):
            self.assertLess(fog["near_m"], fog["far_m"])
            self.assertTrue(fog["color"].startswith("#"))

    def test_dof_table(self):
        self.assertGreater(lt.DOF_CINF["close_up"], lt.DOF_CINF["wide"])
        self.assertEqual(lt.DOF_CINF["aerial"], 0.0)
        self.assertGreater(lt.DOF_CINF["foreground"], lt.DOF_CINF["close_up"])

    def test_headroom_ordering(self):
        h = lt.HEADROOM_Y
        self.assertLess(h["close_up"], h["medium"])
        self.assertLess(h["medium"], h["full_shot"])
        self.assertLess(h["full_shot"], h["wide"])
        self.assertTrue(0 < lt.HORIZON_Y < 1)
        self.assertTrue(0 < lt.CAMERA_HEIGHT_RATIO < 1)

    def test_ink_widths(self):
        self.assertGreater(lt.INK["width_near_px"], lt.INK["width_far_px"])
        self.assertLess(lt.INK["angle_lo_deg"], lt.INK["angle_hi_deg"])
        self.assertLess(lt.INK["dist_near_m"], lt.INK["dist_far_m"])

    def test_shadow_ratios_ordered(self):
        for lo, hi in lt.SHADOW_RATIOS.values():
            self.assertLess(lo, hi)

    def test_light_presets_complete(self):
        for preset in (lt.LIGHT_DAY, lt.LIGHT_GOLDEN):
            for key in ("lit", "shade", "lift", "char_tint", "side_tint"):
                self.assertEqual(len(preset[key]), 3)
            self.assertTrue(0 < preset["char_shade"] < 1)


class TestTiming(unittest.TestCase):
    def test_frames_for_seconds(self):
        self.assertEqual(lt.frames_for_seconds(0.4, 24.0), 10)
        self.assertEqual(lt.frames_for_seconds(0.4, 30.0), 12)
        self.assertEqual(lt.frames_for_seconds(0.0, 24.0), 1)

    def test_blink_pattern_at_source_fps(self):
        self.assertEqual(lt.blink_lid_frames(30.0), (0.5, 1.0, 1.0, 0.5))

    def test_blink_pattern_at_24fps_keeps_duration(self):
        # 4 frames at 30 fps = 133 ms -> 3 frames at 24 fps (125 ms).
        pattern = lt.blink_lid_frames(24.0)
        self.assertEqual(len(pattern), 3)
        self.assertEqual(pattern[0], 0.5)  # starts half-closed
        self.assertEqual(pattern[-1], 0.5)  # ends half-closed
        self.assertIn(1.0, pattern)  # fully shut in the middle

    def test_blink_gap_range(self):
        lo, hi = lt.TIMING["blink_gap_seconds"]
        self.assertLess(lo, hi)
        self.assertGreater(lo, 0)

    def test_timing_values_present(self):
        for key in ("reaction_lead_frames_at_30fps", "walk_step_frames_at_30fps",
                    "walk_bob_frac_height", "walk_lean_deg", "impact_shake_frames"):
            self.assertIn(key, lt.TIMING)


class TestMeasurement(unittest.TestCase):
    def test_white_frame_stats(self):
        stats = lt.frame_luma_stats(np.full((8, 8, 3), 255, dtype=np.uint8))
        self.assertAlmostEqual(stats["mean"], 1.0, places=6)
        self.assertAlmostEqual(stats["sat_mean"], 0.0, places=6)

    def test_black_frame_stats(self):
        stats = lt.frame_luma_stats(np.zeros((8, 8, 3), dtype=np.uint8))
        self.assertEqual(stats["mean"], 0.0)
        self.assertEqual(stats["p98"], 0.0)

    def test_mid_grey_matches_day_target_shape(self):
        stats = lt.frame_luma_stats(np.full((8, 8, 3), 128, dtype=np.uint8))
        comp = lt.compare_luma_to_target(stats, "day")
        self.assertIn("median_y", comp)
        self.assertAlmostEqual(comp["median_y"]["target"], 0.571)
        self.assertAlmostEqual(comp["median_y"]["delta"],
                               comp["median_y"]["measured"] - 0.571, places=9)

    def test_golden_target_has_median_only(self):
        stats = lt.frame_luma_stats(np.full((8, 8, 3), 128, dtype=np.uint8))
        comp = lt.compare_luma_to_target(stats, "golden")
        self.assertEqual(set(comp), {"median_y"})

    def test_rejects_bad_shape(self):
        with self.assertRaises(ValueError):
            lt.frame_luma_stats(np.zeros((8, 8), dtype=np.uint8))


if __name__ == "__main__":
    unittest.main()
