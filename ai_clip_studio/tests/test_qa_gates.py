"""Unit tests for ai_clip_studio.qa_gates (stdlib unittest, no network).

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/agent/

Technical tests encode small real videos with ffmpeg (testsrc + sine
tone) so ffprobe / astats measure real files, not fixtures.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.qa_gates import (
    CreativeGate,
    TechnicalGate,
    combine,
    probe_video,
    rescore_old,
)

V3_QA = Path.home() / "workspace/acceptance_loop/test_chiec_vi_trong_mua/out/chiec_vi_qa.json"
V4_QA = Path.home() / "workspace/acceptance_loop/v4/out/eiffel_16x9_v4_evaluation.json"


def make_video(path: Path, width=1920, height=1080, fps=24, duration=2.0,
               codec="libx264", silent=False) -> None:
    """Encode a real mp4: testsrc video + sine tone (or silence)."""
    audio = "anullsrc=r=48000:cl=stereo" if silent else "sine=frequency=440:duration=3"
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i",
        f"testsrc=duration={duration}:size={width}x{height}:rate={fps}",
        "-f", "lavfi", "-i", audio,
        "-c:v", codec, "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-t", str(duration), "-shortest",
        str(path),
    ]
    subprocess.run(cmd, check=True, timeout=120)


def make_motion_report(path: Path, total_frames: int, fps: int = 24) -> None:
    path.write_text(json.dumps(
        {"fps": fps, "total_frames": total_frames,
         "total_duration_sec": total_frames / fps}), encoding="utf-8")


def valid_evidence(pronunciation_verified=True):
    """Complete, rule-compliant evidence for all 10 creative criteria."""
    insp = lambda note: {"frame_inspections": [
        {"frame": 100, "timestamp_sec": 4.2, "note": note},
        {"frame": 500, "timestamp_sec": 20.8, "note": note + " (second angle)"},
    ]}
    return {
        "character_art": insp("volumes, face, expression, layered costume inspected"),
        "environment_art": insp("foreground/midground/background, lighting, depth inspected"),
        "cinematography": {
            "shot_list": [
                {"shot_id": "SH01", "shot_type": "WIDE",
                 "narrative_purpose": "establishing the street"},
                {"shot_id": "SH02", "shot_type": "MEDIUM",
                 "narrative_purpose": "escalation: the handoff"},
                {"shot_id": "SH03", "shot_type": "CLOSE_UP",
                 "narrative_purpose": "reaction: fear on the face"},
                {"shot_id": "SH04", "shot_type": "INSERT",
                 "narrative_purpose": "insert: the wallet"},
                {"shot_id": "SH05", "shot_type": "REACTION",
                 "narrative_purpose": "reaction: the twist lands"},
            ],
            "contact_sheet": "out/contact.png",
        },
        "animation_quality": insp("walk cycle, gesture and hand-off inspected frame by frame"),
        "acting_expressions": insp("facial expression changes across the beat inspected"),
        "visual_storytelling": {"beats": {
            "hook": "0.0s: hook line",
            "twist": "12.9s: nobody reported the crime",
            "payoff": "17.1s: he returns to sell it again"}},
        "composition": insp("rule of thirds, safe title, headroom inspected"),
        "lighting": insp("key/fill, shadows, night contrast inspected"),
        "audio_experience": {
            "pronunciation_verified": pronunciation_verified,
            "method": ("faster-whisper transcription vs script, WER 0.02"
                       if pronunciation_verified else "timing+RMS only"),
            "sfx_events": [{"event": "door bell", "at_sec": 4.85, "rms": 0.087}],
            "voice_lines": [{"line": "He sold the Eiffel Tower twice.",
                             "start": 0.0, "end": 3.2}],
        },
        "subtitle_readability": {"font_sizes_px": [64, 64, 64], "max_lines": 2},
    }


def all_scores(value=8.5, **overrides):
    from ai_clip_studio.qa_gates import CREATIVE_CRITERIA
    scores = {c: value for c in CREATIVE_CRITERIA}
    scores.update(overrides)
    return scores


class TestTechnicalGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        make_video(cls.d / "good.mp4")                       # 1920x1080 24fps h264, tone
        make_video(cls.d / "small.mp4", width=1280, height=720)
        make_video(cls.d / "fast.mp4", fps=30)
        make_video(cls.d / "mpeg4.mp4", codec="mpeg4")
        make_video(cls.d / "silent.mp4", silent=True)
        make_motion_report(cls.d / "motion.json", total_frames=48)
        make_motion_report(cls.d / "motion_wrong.json", total_frames=10)
        cls.hash = "a" * 64

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _base_kwargs(self, **overrides):
        kw = dict(
            video_path=self.d / "good.mp4",
            timeline_duration_sec=2.0,
            dialogue_windows=[
                {"line": "line one", "start": 0.2, "end": 1.0},
                {"line": "line two", "start": 1.2, "end": 1.8},
            ],
            expected_script_hash=self.hash,
            actual_script_hash=self.hash,
            motion_report_path=self.d / "motion.json",
            pipeline_errors=[],
        )
        kw.update(overrides)
        return kw

    def test_technical_pass_all_checks_real_ffprobe(self):
        # Dialogue windows carry no precomputed RMS: the gate measures
        # real RMS with ffmpeg astats on the tone audio.
        result = TechnicalGate().run(**self._base_kwargs())
        self.assertEqual(result.status, "TECHNICAL_PASS")
        self.assertEqual(result.failed_checks(), [])
        for name in TechnicalGate.CHECKS:
            self.assertIn(name, result.checks)
            self.assertTrue(result.checks[name].passed, name)

    def test_technical_fail_wrong_resolution(self):
        result = TechnicalGate().run(**self._base_kwargs(
            video_path=self.d / "small.mp4"))
        self.assertEqual(result.status, "TECHNICAL_FAIL")
        self.assertFalse(result.checks["resolution_1920x1080"].passed)
        self.assertIn("1280x720", result.checks["resolution_1920x1080"].detail)

    def test_technical_fail_wrong_fps(self):
        result = TechnicalGate().run(**self._base_kwargs(
            video_path=self.d / "fast.mp4",
            timeline_duration_sec=2.0,
            motion_report_path=self.d / "motion.json"))
        self.assertEqual(result.status, "TECHNICAL_FAIL")
        self.assertFalse(result.checks["fps_24"].passed)

    def test_technical_fail_wrong_codec(self):
        result = TechnicalGate().run(**self._base_kwargs(
            video_path=self.d / "mpeg4.mp4"))
        self.assertEqual(result.status, "TECHNICAL_FAIL")
        self.assertFalse(result.checks["codec_h264"].passed)
        self.assertIn("mpeg4", result.checks["codec_h264"].detail)

    def test_technical_fail_missing_file(self):
        result = TechnicalGate().run(**self._base_kwargs(
            video_path=self.d / "does_not_exist.mp4"))
        self.assertEqual(result.status, "TECHNICAL_FAIL")
        self.assertFalse(result.checks["video_valid"].passed)

    def test_technical_fail_timeline_mismatch(self):
        result = TechnicalGate().run(**self._base_kwargs(
            timeline_duration_sec=5.0))
        self.assertEqual(result.status, "TECHNICAL_FAIL")
        self.assertFalse(result.checks["timeline_sync"].passed)

    def test_technical_fail_audio_cut_silent_window(self):
        result = TechnicalGate().run(**self._base_kwargs(
            video_path=self.d / "silent.mp4"))
        self.assertEqual(result.status, "TECHNICAL_FAIL")
        self.assertFalse(result.checks["audio_not_cut"].passed)
        self.assertIn("RMS", result.checks["audio_not_cut"].detail)

    def test_technical_fail_final_line_beyond_timeline(self):
        result = TechnicalGate().run(**self._base_kwargs(
            dialogue_windows=[{"line": "last", "start": 0.2, "end": 2.5,
                               "rms": 0.1}]))
        self.assertEqual(result.status, "TECHNICAL_FAIL")
        self.assertFalse(result.checks["audio_not_cut"].passed)

    def test_technical_fail_script_hash_mismatch(self):
        result = TechnicalGate().run(**self._base_kwargs(
            actual_script_hash="b" * 64))
        self.assertEqual(result.status, "TECHNICAL_FAIL")
        self.assertFalse(result.checks["script_hash_match"].passed)

    def test_technical_fail_frames_mismatch(self):
        result = TechnicalGate().run(**self._base_kwargs(
            motion_report_path=self.d / "motion_wrong.json"))
        self.assertEqual(result.status, "TECHNICAL_FAIL")
        self.assertFalse(result.checks["frames_rendered_real"].passed)

    def test_technical_fail_pipeline_errors(self):
        result = TechnicalGate().run(**self._base_kwargs(
            pipeline_errors=["GEMINI_STORY_PLANNING failed"]))
        self.assertEqual(result.status, "TECHNICAL_FAIL")
        self.assertFalse(result.checks["pipeline_no_errors"].passed)

    def test_probe_video_raises_for_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            probe_video(self.d / "nope.mp4")


class TestCreativeGate(unittest.TestCase):
    def test_missing_evidence_requires_review(self):
        result = CreativeGate().evaluate(all_scores(9.0), {})
        self.assertEqual(result.status, "CREATIVE_REVIEW_REQUIRED")
        self.assertIsNone(result.weighted_total)
        self.assertTrue(all(v is None for v in result.scores.values()))

    def test_partial_evidence_requires_review(self):
        evidence = valid_evidence()
        del evidence["lighting"]  # one criterion without evidence
        result = CreativeGate().evaluate(all_scores(9.0), evidence)
        self.assertEqual(result.status, "CREATIVE_REVIEW_REQUIRED")
        self.assertIsNone(result.scores["lighting"])
        self.assertIsNotNone(result.scores["character_art"])

    def test_forbidden_ffprobe_evidence_rejected_for_cinematography(self):
        evidence = valid_evidence()
        evidence["cinematography"] = {
            "method": "ffprobe + RMS + SRT check",
            "resolution": "1920x1080",
            "shot_list": [{"shot_id": "SH01", "shot_type": "WIDE",
                           "narrative_purpose": "establishing"}],
            "contact_sheet": "out/contact.png",
        }
        result = CreativeGate().evaluate(all_scores(9.0), evidence)
        self.assertEqual(result.status, "CREATIVE_REVIEW_REQUIRED")
        self.assertIsNone(result.scores["cinematography"])

    def test_one_criterion_below_min_fails(self):
        result = CreativeGate().evaluate(
            all_scores(8.5, lighting=6.0), valid_evidence())
        self.assertEqual(result.status, "CREATIVE_FAIL")
        self.assertIsNotNone(result.weighted_total)
        self.assertGreaterEqual(result.weighted_total, 8.0)
        self.assertIn("lighting", result.reasons["_gate"])

    def test_voice_unverified_capped_at_7(self):
        evidence = valid_evidence(pronunciation_verified=False)
        result = CreativeGate().evaluate(
            all_scores(8.5, audio_experience=10.0), evidence)
        self.assertEqual(result.scores["audio_experience"], 7.0)
        self.assertEqual(result.capped["audio_experience"], 7.0)
        self.assertIn("pronunciation_verified: False",
                      result.reasons["audio_experience"])

    def test_voice_verified_keeps_score(self):
        result = CreativeGate().evaluate(
            all_scores(8.5, audio_experience=9.0),
            valid_evidence(pronunciation_verified=True))
        self.assertEqual(result.scores["audio_experience"], 9.0)
        self.assertNotIn("audio_experience", result.capped)

    def test_creative_pass_all_good(self):
        result = CreativeGate().evaluate(all_scores(8.5), valid_evidence())
        self.assertEqual(result.status, "CREATIVE_PASS")
        self.assertEqual(result.weighted_total, 8.5)

    def test_subtitle_nonuniform_font_flagged(self):
        evidence = valid_evidence()
        evidence["subtitle_readability"] = {
            "font_sizes_px": [64, 64, 36], "max_lines": 2}
        result = CreativeGate().evaluate(all_scores(8.5), evidence)
        self.assertIn("NOT uniform", result.reasons["subtitle_readability"])

    def test_audio_evidence_without_pronunciation_declaration_rejected(self):
        evidence = valid_evidence()
        del evidence["audio_experience"]["pronunciation_verified"]
        result = CreativeGate().evaluate(all_scores(9.0), evidence)
        self.assertEqual(result.status, "CREATIVE_REVIEW_REQUIRED")
        self.assertIsNone(result.scores["audio_experience"])


class TestCombine(unittest.TestCase):
    def test_four_verdicts(self):
        tech_pass = {"status": "TECHNICAL_PASS"}
        tech_fail = {"status": "TECHNICAL_FAIL"}
        cases = [
            (tech_pass, {"status": "CREATIVE_PASS"}, "DRAFT_PASSED_QA"),
            (tech_pass, {"status": "CREATIVE_FAIL"},
             "TECHNICAL_PASS_CREATIVE_FAIL"),
            (tech_pass, {"status": "CREATIVE_REVIEW_REQUIRED"},
             "CREATIVE_REVIEW_REQUIRED"),
            (tech_fail, {"status": "CREATIVE_PASS"}, "TECHNICAL_FAIL"),
            (tech_fail, {"status": "CREATIVE_REVIEW_REQUIRED"},
             "TECHNICAL_FAIL"),
        ]
        for tech, crea, expected in cases:
            with self.subTest(tech=tech, crea=crea):
                out = combine(tech, crea)
                self.assertEqual(out["verdict"], expected)
                self.assertEqual(out["draft_passed_qa"],
                                 expected == "DRAFT_PASSED_QA")


class TestRescoreOld(unittest.TestCase):
    def _evidence_single_wide_shot(self):
        return {
            "shot_list": [{"shot_id": "SH01", "shot_type": "WIDE",
                           "narrative_purpose": "whole scene in one wide"}],
            "pronunciation_verified": False,
            "method": "timing+RMS only",
            "subtitle_readability": {"font_sizes_px": [60, 64, 36],
                                     "max_lines": 2},
        }

    def test_rescore_v3_lowers_camera_and_voice(self):
        result = rescore_old(V3_QA, self._evidence_single_wide_shot())
        self.assertEqual(result["old_weighted_total"], 8.7)
        cam = result["new_scores"]["cinematography"]
        self.assertEqual(cam["old_score"], 10.0)
        self.assertEqual(cam["new_score"], 4.0)
        self.assertIn("1 distinct shot type", cam["reason"])
        voice = result["new_scores"]["audio_experience"]
        self.assertEqual(voice["old_score"], 10.0)
        self.assertEqual(voice["new_score"], 7.0)
        self.assertIn("timing+RMS only", voice["reason"])
        # No old category ever measured composition / acting, so the
        # re-score cannot pass — human review is required.
        self.assertEqual(result["verdict"], "CREATIVE_REVIEW_REQUIRED")
        self.assertIn("composition", result["missing_evidence_criteria"])
        self.assertIn("acting_expressions",
                      result["missing_evidence_criteria"])

    def test_rescore_v4_lowers_camera_and_voice(self):
        result = rescore_old(V4_QA, self._evidence_single_wide_shot())
        self.assertEqual(result["old_weighted_total"], 8.75)
        self.assertEqual(result["new_scores"]["cinematography"]["old_score"], 10.0)
        self.assertEqual(result["new_scores"]["cinematography"]["new_score"], 4.0)
        self.assertEqual(result["new_scores"]["audio_experience"]["new_score"], 7.0)
        self.assertEqual(result["verdict"], "CREATIVE_REVIEW_REQUIRED")

    def test_rescore_subtitle_shrunk_final_line_capped(self):
        result = rescore_old(V3_QA, self._evidence_single_wide_shot())
        sub = result["new_scores"]["subtitle_readability"]
        self.assertEqual(sub["old_score"], 9.0)
        self.assertEqual(sub["new_score"], 7.0)
        self.assertIn("36px", sub["reason"])


if __name__ == "__main__":
    unittest.main()
