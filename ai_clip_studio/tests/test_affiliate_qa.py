"""Tests: video QA on real rendered files (measured numbers only)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from ai_clip_studio.affiliate.video.capabilities import run_command
from ai_clip_studio.affiliate.video.qa import (
    blockiness, check_faststart, content_retention, detect_black,
    laplacian_variance, qa_export)

FIXTURES = Path.home() / "workspace/acceptance_loop/affiliate_fixtures"
FIXTURE = FIXTURES / "fixture.mp4"


def _check(report, name: str):
    for check in report.checks:
        if check.name == name:
            return check
    raise AssertionError(f"no check named {name!r}")


def _make_clip(path: Path, source: str, faststart: bool) -> None:
    argv = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source,
            "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p"]
    if faststart:
        argv += ["-movflags", "+faststart"]
    argv += ["-y", str(path)]
    proc = run_command(argv, timeout=120.0)
    assert proc.returncode == 0, proc.stderr


class TestQAOnFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert FIXTURE.is_file(), "run generate_fixture.py first"
        cls.report = qa_export(FIXTURE, "TIKTOK_REELS", 1280, 720,
                               expected_fps=30.0)

    def test_exact_checks_pass(self) -> None:
        self.assertEqual(_check(self.report, "valid_mp4").status, "PASS")
        self.assertEqual(_check(self.report, "resolution").status, "PASS")
        self.assertEqual(_check(self.report, "aspect_ratio").status, "PASS")
        self.assertEqual(_check(self.report, "fps").status, "PASS")
        self.assertEqual(_check(self.report, "faststart").status, "PASS")
        self.assertEqual(_check(self.report, "black_frames").status, "PASS")

    def test_audio_specs_measured(self) -> None:
        check = _check(self.report, "audio_specs")
        self.assertEqual(check.measured["codec"], "aac")
        self.assertEqual(check.measured["sample_rate"], 48000)
        self.assertIn(check.status, ("PASS", "FAIL"))

    def test_freeze_report_is_measured_not_hidden(self) -> None:
        # The fixture is intentionally static in 2 of 3 scenes, so
        # freezedetect must report segments with real numbers.
        check = _check(self.report, "frozen_frames")
        self.assertGreaterEqual(check.measured["segments"], 1)
        self.assertGreater(check.measured["total_sec"], 0.0)
        self.assertIn(check.status, ("PENDING", "FAIL"))

    def test_pending_checks_carry_numbers(self) -> None:
        sharp = _check(self.report, "sharpness")
        self.assertEqual(sharp.status, "PENDING")
        self.assertGreater(sharp.measured, 0.0)
        block = _check(self.report, "compression_blockiness")
        self.assertEqual(block.status, "PENDING")
        self.assertIsInstance(block.measured, float)

    def test_retention_pending_without_source(self) -> None:
        self.assertEqual(_check(self.report, "content_retention").status,
                         "PENDING")


class TestQAFailures(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="aff_qa_test_")
        cls.work = Path(cls.tmp.name)
        cls.black = cls.work / "black.mp4"
        _make_clip(cls.black, "color=black:size=1280x720:rate=30:duration=2",
                   faststart=False)
        cls.plain = cls.work / "plain.mp4"
        _make_clip(cls.plain, "testsrc2=size=640x360:rate=30:duration=1",
                   faststart=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_wrong_resolution_fails(self) -> None:
        report = qa_export(FIXTURE, "TIKTOK_REELS", 1080, 1920)
        self.assertEqual(_check(report, "resolution").status, "FAIL")
        self.assertEqual(_check(report, "aspect_ratio").status, "FAIL")

    def test_black_clip_fails_black_check(self) -> None:
        segments = detect_black(self.black)
        self.assertGreaterEqual(len(segments), 1)
        self.assertAlmostEqual(sum(d for _, _, d in segments), 2.0,
                               delta=0.3)
        report = qa_export(self.black, "TIKTOK_REELS", 1280, 720)
        self.assertEqual(_check(report, "black_frames").status, "FAIL")

    def test_non_video_fails_valid_check(self) -> None:
        report = qa_export(FIXTURES / "fixture_manifest.json",
                           "TIKTOK_REELS", 1080, 1920)
        self.assertEqual(len(report.checks), 1)
        self.assertEqual(report.checks[0].name, "valid_mp4")
        self.assertEqual(report.checks[0].status, "FAIL")

    def test_faststart_detection(self) -> None:
        ok, _ = check_faststart(FIXTURE)
        self.assertTrue(ok)
        ok, _ = check_faststart(self.plain)
        self.assertFalse(ok)

    def test_content_retention_same_file(self) -> None:
        result = content_retention(FIXTURE, FIXTURE, "blur_fill")
        self.assertLess(result["mean_abs_diff"], 0.05)

    def test_content_retention_different_video(self) -> None:
        result = content_retention(FIXTURE, self.black, "blur_fill")
        self.assertGreater(result["mean_abs_diff"], 0.3)


class TestNumpyMetrics(unittest.TestCase):
    def test_flat_frame_zero(self) -> None:
        flat = np.full((64, 64), 128.0, dtype=np.float32)
        self.assertEqual(laplacian_variance(flat), 0.0)
        self.assertEqual(blockiness(flat), 0.0)

    def test_textured_frame_positive(self) -> None:
        rng = np.random.default_rng(7)
        noise = rng.random((64, 64), dtype=np.float32) * 255.0
        self.assertGreater(laplacian_variance(noise), 0.0)


if __name__ == "__main__":
    unittest.main()
