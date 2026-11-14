"""Tests for the Ricks-style parity scorecard.

The scorecard must be able to FAIL a render: every test here pins a way
a real render falls short, so a green suite means the score is a real
measurement rather than a participation trophy.
"""
import unittest

import numpy as np

from ai_clip_studio import ricks_parity as rp


class BandScoreTest(unittest.TestCase):
    def test_inside_band_is_full_marks(self):
        self.assertEqual(rp.band_score(4.5, 3.0, 6.5, 4.5), 100.0)
        self.assertGreaterEqual(rp.band_score(3.2, 3.0, 6.5, 4.5), 90.0)

    def test_outside_band_decays_to_zero(self):
        # A full band-width of overshoot is worth nothing; just outside
        # the band still earns partial credit.
        self.assertLess(rp.band_score(9.5, 3.0, 6.5), 20.0)
        self.assertEqual(rp.band_score(3.0 - 3.5, 3.0, 6.5), 0.0)
        self.assertLess(rp.band_score(0.5, 3.0, 6.5), 30.0)

    def test_ideal_off_centre_still_prefers_the_centre(self):
        self.assertGreater(rp.band_score(4.5, 3.0, 6.5, 4.5),
                           rp.band_score(6.0, 3.0, 6.5, 4.5))

    def test_empty_band_is_a_bug(self):
        with self.assertRaises(ValueError):
            rp.band_score(1.0, 2.0, 2.0)


class DimensionTest(unittest.TestCase):
    def _dim(self, name, score):
        return rp.Dimension(name, score, None, None, 0.1)

    def test_failing_lists_only_low_scores(self):
        report = rp.ParityReport(video="x.mp4", dimensions=[
            self._dim("format", 100.0), self._dim("pacing", 55.0),
            self._dim("captions", None),
        ])
        self.assertEqual([d.name for d in report.failing()], ["pacing"])

    def test_unmeasured_dimension_is_not_a_failure(self):
        report = rp.ParityReport(video="x.mp4", dimensions=[
            self._dim("format", 100.0), self._dim("captions", None),
        ])
        self.assertEqual(report.failing(), [])


class PacingTest(unittest.TestCase):
    def test_shot_lengths_are_scored_from_frames(self):
        shots = [{"id": 0, "a": 0, "b": 108}, {"id": 1, "a": 108, "b": 216}]
        dim = rp._score_pacing(shots, 24.0)
        self.assertEqual(dim.measured["durations_sec"], [4.5, 4.5])
        self.assertEqual(dim.score, 100.0)

    def test_a_long_talking_head_shot_is_penalised(self):
        shots = [{"id": 0, "a": 0, "b": 240}]
        dim = rp._score_pacing(shots, 24.0)
        self.assertLess(dim.score, 60.0)
        self.assertIn("outside", dim.detail)


class MotionTest(unittest.TestCase):
    def _frames(self, n, moving):
        base = np.full((n, 180, 320, 3), 200, dtype=np.uint8)
        if moving:
            for i in range(n):
                base[i, 40:80, i % 40:i % 40 + 40] = 20
        return base

    def test_static_frames_score_low(self):
        frames = self._frames(30, moving=False)
        shots = [{"id": 0, "a": 0, "b": 30}]
        report = rp.analyze_frames(frames, 24.0, shots=shots)
        dim = rp._score_motion(shots, report, frames)
        self.assertLess(dim.score, 50.0)

    def test_moving_frames_score_higher_than_static(self):
        shots = [{"id": 0, "a": 0, "b": 30}]
        moving = self._frames(30, moving=True)
        static = self._frames(30, moving=False)
        s_moving = rp._score_motion(
            shots, rp.analyze_frames(moving, 24.0, shots=shots), moving)
        s_static = rp._score_motion(
            shots, rp.analyze_frames(static, 24.0, shots=shots), static)
        self.assertGreater(s_moving.score, s_static.score)


class PlanDimensionsTest(unittest.TestCase):
    def test_no_plan_means_unmeasured_not_perfect(self):
        dim = rp._score_framing(None)
        self.assertIsNone(dim.score)
        self.assertIn("plan", dim.detail)

    def test_reusing_a_wide_later_is_not_a_defect(self):
        # The channel returns to a wide repeatedly in one short; only an
        # ADJACENT repeat is the framing defect.
        seq = ["establishing", "medium", "close_up", "medium",
               "establishing", "close_up", "establishing", "medium",
               "close_up"]
        dim = rp._score_framing({"shots": [{"index": i, "framing": f}
                                            for i, f in enumerate(seq)]})
        self.assertEqual(dim.score, 100.0)
        self.assertEqual(dim.measured["adjacent_repeats"], 0)

    def test_single_framing_for_the_whole_episode_is_penalised(self):
        dim = rp._score_framing({"shots": [{"index": i, "framing": "wide"}
                                            for i in range(5)]})
        self.assertLess(dim.score, 40.0)

    def test_repeated_adjacent_framing_costs_points(self):
        plan = {"shots": [{"index": i, "framing": "wide"} for i in range(4)]}
        dim = rp._score_framing(plan)
        self.assertLess(dim.score, 90.0)
        self.assertIn("repeated", dim.detail)

    def test_caption_over_two_lines_fails(self):
        plan = {"captions": [{"font_px": 64, "lines": 3, "max_chars": 40, "y_frac": 0.82},
                             {"font_px": 64, "lines": 2, "max_chars": 40, "y_frac": 0.82}]}
        dim = rp._score_captions(plan)
        self.assertEqual(dim.score, 50.0)

    def test_character_outside_safe_area_fails(self):
        plan = {"shots": [{
            "index": 0,
            "characters": [{"name": "A", "head_ratio": 0.34,
                            "bbox": [0, 10, 400, 900]}],
        }]}
        dim = rp._score_characters(plan)
        self.assertEqual(dim.score, 0.0)

    def test_compliant_character_shot_passes(self):
        plan = {"shots": [{
            "index": 0,
            "characters": [{"name": "A", "head_ratio": 0.34,
                            "bbox": [300, 200, 900, 900]}],
        }]}
        dim = rp._score_characters(plan)
        self.assertEqual(dim.score, 100.0)


class OverallTest(unittest.TestCase):
    def test_pass_requires_90_overall_and_no_dimension_below_85(self):
        dims = [rp.Dimension("a", 95.0, None, None, 0.5),
                rp.Dimension("b", 95.0, None, None, 0.5)]
        measured = [d for d in dims if d.score is not None]
        overall = sum(d.score * d.weight for d in measured) / sum(d.weight for d in measured)
        self.assertGreaterEqual(overall, 90.0)

        dims[1].score = 50.0
        self.assertTrue(any(d.score < 85.0 for d in dims))


if __name__ == "__main__":
    unittest.main()
