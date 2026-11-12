"""Tests: affiliate video analysis against fixture ground truth."""
from __future__ import annotations

import unittest
from pathlib import Path

from ai_clip_studio.affiliate.video.analysis import (
    analyze_source, detect_scene_cuts, detect_silence)
from ai_clip_studio.affiliate.video.probe import probe_source

FIXTURES = Path.home() / "workspace/acceptance_loop/affiliate_fixtures"
FIXTURE = FIXTURES / "fixture.mp4"


class TestSceneAndSilence(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert FIXTURE.is_file(), "run generate_fixture.py first"
        cls.info = probe_source(FIXTURE)

    def test_scene_cuts_match_ground_truth(self) -> None:
        cuts = detect_scene_cuts(FIXTURE, self.info.duration_sec)
        self.assertEqual(len(cuts), 3)
        for measured, expected in zip(cuts, [0.0, 3.0, 6.0]):
            self.assertAlmostEqual(measured, expected, delta=0.2)

    def test_silence_matches_ground_truth(self) -> None:
        silences = detect_silence(FIXTURE, self.info.duration_sec)
        self.assertEqual(len(silences), 1)
        seg = silences[0]
        self.assertAlmostEqual(seg.start_time, 3.0, delta=0.3)
        self.assertAlmostEqual(seg.end_time, 6.0, delta=0.3)
        self.assertEqual(seg.kind, "silence")


class TestAnalyzeSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert FIXTURE.is_file(), "run generate_fixture.py first"
        cls.report = analyze_source(FIXTURE, sample_fps=2.0)

    def test_three_scenes(self) -> None:
        self.assertEqual(len(self.report.scenes), 3)
        for scene, (start, end) in zip(
                self.report.scenes, [(0.0, 3.0), (3.0, 6.0), (6.0, 9.0)]):
            self.assertAlmostEqual(scene.start_time, start, delta=0.2)
            self.assertAlmostEqual(scene.end_time, end, delta=0.2)

    def test_moving_scene_has_more_motion(self) -> None:
        scenes = self.report.scenes
        # Scene 2 slides the product; scenes 1 and 3 are static.
        self.assertGreater(scenes[1].motion_intensity,
                           scenes[0].motion_intensity)
        self.assertGreater(scenes[1].motion_intensity,
                           scenes[2].motion_intensity)
        self.assertEqual(scenes[0].motion_label, "low")

    def test_motion_summary_label(self) -> None:
        self.assertIn(self.report.motion_summary["label"],
                      ("low", "medium", "high"))
        self.assertGreater(self.report.motion_summary["samples"], 0)

    def test_watermark_candidate_top_right(self) -> None:
        cands = [w for w in self.report.watermark_candidates
                 if w.region == "top_right"]
        self.assertGreaterEqual(len(cands), 1)
        self.assertGreaterEqual(cands[0].persistence, 0.5)

    def test_text_candidates_found(self) -> None:
        # Subtitle bands in scenes 1 and 3 + promo in scene 2.
        self.assertGreaterEqual(len(self.report.text_candidates), 1)
        for cand in self.report.text_candidates:
            self.assertEqual(cand.source, "candidate")
            self.assertTrue(cand.needs_review)

    def test_faces_status_is_honest(self) -> None:
        # System python has no cv2: status must say unavailable, and
        # no faces may be fabricated.
        self.assertIn(self.report.faces_status, ("ok", "unavailable"))
        if self.report.faces_status == "unavailable":
            self.assertEqual(self.report.faces, [])
            self.assertIn("cv2", self.report.faces_status_detail)

    def test_hands_status_is_unavailable(self) -> None:
        self.assertEqual(self.report.hands_status, "unavailable")
        self.assertIn("hand", self.report.hands_status_detail.lower())

    def test_audio_segments_cover_duration(self) -> None:
        segments = self.report.audio_segments
        self.assertTrue(any(s.kind == "silence" for s in segments))
        self.assertTrue(any(s.kind == "non_silence" for s in segments))
        total = sum(s.end_time - s.start_time for s in segments)
        self.assertAlmostEqual(total, 9.0, delta=0.5)

    def test_schema_dict_validates(self) -> None:
        from ai_clip_studio.affiliate.schema import validate_project
        data = self.report.to_video_analysis_dict()
        issues = validate_project({
            "project_id": "analysis-test",
            "video_analysis": data,
        })
        self.assertEqual(issues, [])
        self.assertEqual(len(data["scenes"]), 3)
        self.assertEqual(data["engine"], self.report.engine)


if __name__ == "__main__":
    unittest.main()
