"""Tests: export profiles, reframe, authorization gate, single pass."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.affiliate.video.export import (
    ExportRefusedError, export_profile_for, export_video, validate_profile)
from ai_clip_studio.affiliate.video.models import (
    EXPORT_PRESETS, BBox, ReplacementMode, ReplacementSpec, TextRegion,
    TransformOp)
from ai_clip_studio.affiliate.video.probe import probe_source
from ai_clip_studio.affiliate.video.qa import check_faststart

FIXTURES = Path.home() / "workspace/acceptance_loop/affiliate_fixtures"
FIXTURE = FIXTURES / "fixture.mp4"


class TestProfiles(unittest.TestCase):
    def test_presets_match_schema_values(self) -> None:
        tiktok = export_profile_for("TIKTOK_REELS")
        self.assertEqual((tiktok.width, tiktok.height), (1080, 1920))
        self.assertEqual(tiktok.crf, 18)
        self.assertEqual(tiktok.audio_sample_rate, 48000)
        self.assertEqual(tiktok.audio_bitrate_kbps, 192)
        self.assertEqual(tiktok.pixel_format, "yuv420p")
        self.assertEqual(tiktok.color_space, "bt709")
        self.assertTrue(tiktok.faststart)
        schema = tiktok.to_schema_dict()
        self.assertEqual(schema["resolution"], "1080x1920")
        self.assertEqual(schema["aspect_ratio"], "9:16")

    def test_unknown_profile(self) -> None:
        with self.assertRaises(ExportRefusedError):
            export_profile_for("NOPE")

    def test_profile_validation(self) -> None:
        bad = EXPORT_PRESETS["TIKTOK_REELS"]
        from dataclasses import replace
        with self.assertRaises(ExportRefusedError):
            validate_profile(replace(bad, crf=99))
        with self.assertRaises(ExportRefusedError):
            validate_profile(replace(bad, fps=29))
        with self.assertRaises(ExportRefusedError):
            validate_profile(replace(bad, audio_bitrate_kbps=64))


class TestExportGate(unittest.TestCase):
    def test_unknown_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ExportRefusedError):
                export_video(FIXTURE, Path(tmp) / "o.mp4", "TIKTOK_REELS",
                             "UNKNOWN", True)

    def test_unconfirmed_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ExportRefusedError):
                export_video(FIXTURE, Path(tmp) / "o.mp4", "TIKTOK_REELS",
                             "USER_OWNED", False)

    def test_reorder_plus_replacements_refused(self) -> None:
        region = TextRegion(
            text_id="txt-001", track_id="track-001", original_text="x",
            start_time=0.0, end_time=3.0, bbox=BBox(0, 600, 400, 50),
            frame_size=(1280, 720))
        spec = ReplacementSpec(region=region, mode=ReplacementMode.LOCAL_BLUR,
                               approved=True, approval_note="ok")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ExportRefusedError):
                export_video(
                    FIXTURE, Path(tmp) / "o.mp4", "TIKTOK_REELS",
                    "SYNTHETIC_FIXTURE", True,
                    transforms=[TransformOp(
                        operation="scene_reorder",
                        parameters={"segments": [[0.0, 3.0]]},
                        purpose="test")],
                    replacements=[spec])


class TestExportRenders(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert FIXTURE.is_file(), "run generate_fixture.py first"
        cls.tmp = tempfile.TemporaryDirectory(prefix="aff_exp_test_")
        cls.work = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_tiktok_export_specs(self) -> None:
        result = export_video(FIXTURE, self.work / "tiktok.mp4",
                              "TIKTOK_REELS", "SYNTHETIC_FIXTURE", True)
        self.assertEqual((result.width, result.height), (1080, 1920))
        self.assertEqual(result.video_codec, "h264")
        self.assertEqual(result.audio_codec, "aac")
        self.assertEqual(result.fps, 30.0)  # source fps preserved
        self.assertTrue(result.fps_preserved)
        self.assertFalse(result.upscaled)
        self.assertAlmostEqual(result.duration_sec, 9.0, places=1)
        self.assertRegex(result.sha256, r"^[0-9a-f]{64}$")
        fast_ok, _ = check_faststart(result.output_path)
        self.assertTrue(fast_ok)
        self.assertGreater(result.encode_seconds, 0)

    def test_crop_center_export(self) -> None:
        from dataclasses import replace
        profile = replace(EXPORT_PRESETS["FACEBOOK_REELS"],
                          reframe_strategy="crop_center")
        result = export_video(FIXTURE, self.work / "fb_crop.mp4", profile,
                              "SYNTHETIC_FIXTURE", True)
        self.assertEqual((result.width, result.height), (1080, 1920))

    def test_export_with_transform_and_replacement(self) -> None:
        region = TextRegion(
            text_id="txt-001", track_id="track-001",
            original_text="这款收纳盒非常实用",
            start_time=0.0, end_time=3.0, bbox=BBox(440, 620, 400, 50),
            frame_size=(1280, 720))
        spec = ReplacementSpec(region=region, mode=ReplacementMode.LOCAL_BLUR,
                               approved=True, approval_note="ok")
        result = export_video(
            FIXTURE, self.work / "combo.mp4", "TIKTOK_REELS",
            "SYNTHETIC_FIXTURE", True,
            transforms=[TransformOp(operation="brightness",
                                    parameters={"value": 0.05},
                                    purpose="slight lift")],
            replacements=[spec])
        self.assertEqual(result.transforms_applied, ["brightness"])
        self.assertEqual(result.replacements_applied,
                         ["LOCAL_BLUR:txt-001"])
        info = probe_source(result.output_path)
        self.assertEqual((info.width, info.height), (1080, 1920))

    def test_tiny_source_reports_upscale(self) -> None:
        from ai_clip_studio.affiliate.video.capabilities import run_command
        tiny = self.work / "tiny.mp4"
        proc = run_command(["ffmpeg", "-v", "error", "-f", "lavfi",
                            "-i", "testsrc2=size=320x240:rate=30:duration=2",
                            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                            "-c:v", "libx264", "-crf", "23",
                            "-pix_fmt", "yuv420p", "-c:a", "aac",
                            "-shortest", "-y", str(tiny)], timeout=120.0)
        self.assertEqual(proc.returncode, 0)
        result = export_video(tiny, self.work / "tiny_out.mp4",
                              "TIKTOK_REELS", "SYNTHETIC_FIXTURE", True)
        self.assertTrue(result.upscaled)
        self.assertTrue(any("upscaled" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
