"""Vertical slice: probe -> analyze -> regions -> replace -> transform
-> export (9:16) -> QA, on the synthetic fixture.

OCR regions are supplied manually here (system python has no OCR
backend); the real-engine OCR path is proven separately by the venv
proof run. The watermark region is deliberately NOT replaced: the
slice asserts it survives into the export.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from ai_clip_studio.affiliate.video.analysis import analyze_source
from ai_clip_studio.affiliate.video.export import export_video
from ai_clip_studio.affiliate.video.models import (
    BBox, ReplacementMode, ReplacementSpec, TextClassification,
    TextRegion, TransformOp)
from ai_clip_studio.affiliate.video.ocr import approve_removal
from ai_clip_studio.affiliate.video.probe import probe_source
from ai_clip_studio.affiliate.video.qa import qa_export

FIXTURES = Path.home() / "workspace/acceptance_loop/affiliate_fixtures"
FIXTURE = FIXTURES / "fixture.mp4"


class TestVerticalSlice(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert FIXTURE.is_file(), "run generate_fixture.py first"
        cls.tmp = tempfile.TemporaryDirectory(prefix="aff_slice_test_")
        cls.work = Path(cls.tmp.name)

        # 1. Probe.
        cls.info = probe_source(FIXTURE)
        # 2. Analyze.
        cls.analysis = analyze_source(FIXTURE, sample_fps=1.0)
        # 3. Regions (manual stand-ins for OCR output on this env).
        subtitle = TextRegion(
            text_id="txt-sub-1", track_id="track-sub-1",
            original_text="这款收纳盒非常实用", start_time=0.0, end_time=3.0,
            bbox=BBox(440, 620, 400, 50), frame_size=(1280, 720),
            classification=TextClassification.SUBTITLE,
            classification_reason="bottom band, scene 1")
        approve_removal(subtitle, "SYNTHETIC_FIXTURE", True, "slice-test")
        watermark = TextRegion(
            text_id="txt-wm-1", track_id="track-wm-1",
            original_text="SYNTHETIC 样品", start_time=0.0, end_time=9.0,
            bbox=BBox(1092, 16, 180, 30), frame_size=(1280, 720),
            classification=TextClassification.WATERMARK,
            classification_reason="persistent top-right graphic",
            needs_review=True, review_reasons=["persistent corner"])
        cls.watermark = watermark
        # 4-5. Replace the subtitle only; brighten slightly.
        replacements = [ReplacementSpec(
            region=subtitle, mode=ReplacementMode.SMART_OVERLAY,
            vietnamese_text="Hộp đựng này rất tiện lợi",
            approved=True, approval_note="slice test")]
        transforms = [TransformOp(operation="brightness",
                                  parameters={"value": 0.05},
                                  purpose="slight lift for reels")]
        # 6. Export.
        cls.result = export_video(
            FIXTURE, cls.work / "slice_tiktok.mp4", "TIKTOK_REELS",
            "SYNTHETIC_FIXTURE", True, transforms=transforms,
            replacements=replacements)
        # 7. QA.
        cls.qa = qa_export(cls.result.output_path, "TIKTOK_REELS",
                           1080, 1920, expected_fps=30.0,
                           source_path=FIXTURE,
                           reframe_strategy="blur_fill")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_probe_and_analysis(self) -> None:
        self.assertEqual(self.info.resolution, "1280x720")
        self.assertEqual(len(self.analysis.scenes), 3)
        self.assertTrue(any(w.region == "top_right"
                            for w in self.analysis.watermark_candidates))

    def test_export_specs(self) -> None:
        self.assertEqual((self.result.width, self.result.height),
                         (1080, 1920))
        self.assertEqual(self.result.fps, 30.0)
        self.assertTrue(self.result.fps_preserved)
        self.assertFalse(self.result.upscaled)
        self.assertEqual(self.result.replacements_applied,
                         ["SMART_OVERLAY:txt-sub-1"])
        self.assertEqual(self.result.transforms_applied, ["brightness"])

    def test_qa_exact_checks(self) -> None:
        checks = {c.name: c for c in self.qa.checks}
        self.assertEqual(checks["valid_mp4"].status, "PASS")
        self.assertEqual(checks["resolution"].status, "PASS")
        self.assertEqual(checks["aspect_ratio"].status, "PASS")
        self.assertEqual(checks["fps"].status, "PASS")
        self.assertEqual(checks["faststart"].status, "PASS")
        self.assertEqual(checks["black_frames"].status, "PASS")
        self.assertEqual(checks["content_retention"].status, "PASS")

    def test_watermark_survives_in_export(self) -> None:
        from ai_clip_studio.affiliate.video.analysis import extract_frame_at
        frame = extract_frame_at(self.result.output_path, 1.5,
                                 self.work / "export_frame.jpg")
        img = np.asarray(Image.open(frame).convert("L"), dtype=np.float32)
        # blur_fill: foreground scaled to width 1080 (x0.84375), centered
        # vertically: top = (1920 - 608) / 2 = 656.
        region = img[656 + 13:656 + 40, 920:1075]
        self.assertGreater(float(np.std(region)), 5.0,
                           "watermark area looks flat — watermark lost?")

    def test_watermark_was_never_approved_for_removal(self) -> None:
        self.assertFalse(self.watermark.removal_approved)


if __name__ == "__main__":
    unittest.main()
