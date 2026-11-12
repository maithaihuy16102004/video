"""Tests: text replacement engine (gates, filters, masks, renders)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from ai_clip_studio.affiliate.video.models import (
    DEFAULT_TEXT_HANDLING, BBox, MaskSpec, ReplacementMode, ReplacementSpec,
    TextClassification, TextRegion)
from ai_clip_studio.affiliate.video.ocr import approve_removal
from ai_clip_studio.affiliate.video.probe import probe_source
from ai_clip_studio.affiliate.video.text_replace import (
    ReplacementRefused, apply_replacements, build_replacement_filters,
    mask_to_replacement, preview_before_after, render_mask_preview,
    replacement_subtitle_slots, segment_track, validate_replacement)

FIXTURES = Path.home() / "workspace/acceptance_loop/affiliate_fixtures"
FIXTURE = FIXTURES / "fixture.mp4"
FRAME = (1280, 720)


def _region(cls: TextClassification = TextClassification.SUBTITLE,
            needs_review: bool = False) -> TextRegion:
    return TextRegion(
        text_id="txt-001", track_id="track-001", original_text="这款很好",
        start_time=0.0, end_time=3.0, bbox=BBox(440, 620, 400, 50),
        frame_size=FRAME, classification=cls,
        classification_reason="test", needs_review=needs_review,
        review_reasons=["test review"] if needs_review else [])


def _spec(region: TextRegion, mode: ReplacementMode,
          approved: bool = True, text: str = "Hộp này rất tiện lợi",
          note: str = "reviewed") -> ReplacementSpec:
    return ReplacementSpec(region=region, mode=mode, vietnamese_text=text,
                           approved=approved, approval_note=note)


class TestGates(unittest.TestCase):
    def test_unapproved_refused(self) -> None:
        with self.assertRaises(ReplacementRefused):
            validate_replacement(_spec(_region(), ReplacementMode.LOCAL_BLUR,
                                       approved=False),
                                 "USER_OWNED", True)

    def test_unknown_authorization_refused(self) -> None:
        with self.assertRaises(ReplacementRefused):
            validate_replacement(_spec(_region(), ReplacementMode.LOCAL_BLUR),
                                 "UNKNOWN", True)

    def test_protected_without_removal_approval_refused(self) -> None:
        region = _region(TextClassification.WATERMARK)
        with self.assertRaises(ReplacementRefused):
            validate_replacement(_spec(region, ReplacementMode.LOCAL_BLUR),
                                 "USER_OWNED", True)
        approve_removal(region, "USER_OWNED", True, "tester",
                        acknowledge_ownership_risk=True)
        validate_replacement(_spec(region, ReplacementMode.LOCAL_BLUR),
                             "USER_OWNED", True)  # must not raise

    def test_needs_review_requires_note(self) -> None:
        region = _region(needs_review=True)
        with self.assertRaises(ReplacementRefused):
            validate_replacement(_spec(region, ReplacementMode.LOCAL_BLUR,
                                       note=""),
                                 "USER_OWNED", True)

    def test_overlay_without_text_refused(self) -> None:
        with self.assertRaises(ReplacementRefused):
            validate_replacement(_spec(_region(),
                                       ReplacementMode.SMART_OVERLAY,
                                       text=""),
                                 "USER_OWNED", True)

    def test_crop_without_product_visible_refused(self) -> None:
        spec = _spec(_region(), ReplacementMode.CROP_AND_REFRAME)
        spec.product_fully_visible = False
        with self.assertRaises(ReplacementRefused):
            validate_replacement(spec, "USER_OWNED", True)

    def test_crop_mixed_with_other_modes_refused(self) -> None:
        region = _region()
        region.bbox = BBox(0, 620, 1280, 80)
        specs = [_spec(region, ReplacementMode.CROP_AND_REFRAME),
                 _spec(region, ReplacementMode.LOCAL_BLUR)]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ReplacementRefused):
                build_replacement_filters(specs, FRAME, tmp,
                                          authorization_type="USER_OWNED",
                                          commercial_rights_confirmed=True)


class TestFilterBuilding(unittest.TestCase):
    def test_blur_filter_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            filt, label, log = build_replacement_filters(
                [_spec(_region(), ReplacementMode.LOCAL_BLUR)], FRAME, tmp,
                authorization_type="USER_OWNED",
                commercial_rights_confirmed=True)
        self.assertIn("boxblur", filt)
        self.assertIn("overlay=", filt)
        self.assertIn("between(t,0.000,3.000)", filt)
        self.assertTrue(label.startswith("rep"))
        self.assertEqual(len(log), 1)

    def test_overlay_filter_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            filt, _, _ = build_replacement_filters(
                [_spec(_region(), ReplacementMode.SMART_OVERLAY)], FRAME,
                tmp, authorization_type="USER_OWNED",
                commercial_rights_confirmed=True)
            textfiles = list(Path(tmp).glob("overlay_*.txt"))
            self.assertEqual(len(textfiles), 1)
            text_content = textfiles[0].read_text(encoding="utf-8")
        self.assertIn("drawbox", filt)
        self.assertIn("drawtext", filt)
        self.assertIn("expansion=none", filt)
        self.assertEqual(text_content, "Hộp này rất tiện lợi")

    def test_empty_specs_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            filt, label, log = build_replacement_filters(
                [], FRAME, tmp, authorization_type="USER_OWNED",
                commercial_rights_confirmed=True)
        self.assertEqual(filt, "")
        self.assertEqual(label, "0:v")
        self.assertEqual(log, [])

    def test_mask_to_replacement(self) -> None:
        mask = MaskSpec(mask_id="m1", shape="rect",
                        bbox=BBox(440, 620, 400, 50), start_time=0.0,
                        end_time=3.0, track_id="track-001", mode="blur",
                        approved=True, purpose="localize subtitle")
        spec = mask_to_replacement(mask, _region())
        self.assertEqual(spec.mode, ReplacementMode.LOCAL_BLUR)
        self.assertTrue(spec.approved)

    def test_segment_track(self) -> None:
        samples = [(0.0, BBox(900, 100, 200, 60)),
                   (0.5, BBox(850, 100, 200, 60)),
                   (1.0, BBox(800, 100, 200, 60)),
                   (1.5, BBox(750, 100, 200, 60))]
        segments = segment_track(samples, segment_sec=1.0)
        self.assertEqual(len(segments), 2)
        self.assertAlmostEqual(segments[0][0], 0.0)
        self.assertAlmostEqual(segments[1][0], 1.0)


class TestMaskPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert FIXTURE.is_file(), "run generate_fixture.py first"

    def test_preview_files_exist(self) -> None:
        masks = [MaskSpec(mask_id="m1", shape="rect",
                          bbox=BBox(440, 620, 400, 50), start_time=0.0,
                          end_time=3.0, mode="blur")]
        with tempfile.TemporaryDirectory() as tmp:
            result = preview_before_after(FIXTURE, 1.5, masks, tmp)
            self.assertTrue(Path(result["before"]).is_file())
            self.assertTrue(Path(result["after_preview"]).is_file())
            img = Image.open(result["after_preview"])
            self.assertEqual(img.size, (1280, 720))


class TestApplyReplacements(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert FIXTURE.is_file(), "run generate_fixture.py first"
        cls.tmp = tempfile.TemporaryDirectory(prefix="aff_rep_test_")
        cls.work = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_blur_render_changes_region_only(self) -> None:
        out, log = apply_replacements(
            FIXTURE, [_spec(_region(), ReplacementMode.LOCAL_BLUR)],
            self.work / "blurred.mp4", FRAME, "SYNTHETIC_FIXTURE", True)
        info = probe_source(out)
        self.assertEqual((info.width, info.height), (1280, 720))
        self.assertEqual(len(log), 1)
        # The blurred region differs from the source; a far corner does not.
        from ai_clip_studio.affiliate.video.analysis import extract_frame_at
        src_frame = extract_frame_at(FIXTURE, 1.5, self.work / "s.jpg")
        out_frame = extract_frame_at(out, 1.5, self.work / "o.jpg")
        s = np.asarray(Image.open(src_frame).convert("L"), dtype=np.float32)
        o = np.asarray(Image.open(out_frame).convert("L"), dtype=np.float32)
        region_diff = float(np.mean(np.abs(
            s[620:670, 440:840] - o[620:670, 440:840])))
        # Flat background far from the edit: re-encode noise only.
        flat_diff = float(np.mean(np.abs(s[100:180, 900:1200]
                                         - o[100:180, 900:1200])))
        self.assertGreater(region_diff, 5.0)
        self.assertLess(flat_diff, 2.0)

    def test_overlay_render(self) -> None:
        out, _ = apply_replacements(
            FIXTURE, [_spec(_region(), ReplacementMode.SMART_OVERLAY)],
            self.work / "overlaid.mp4", FRAME, "SYNTHETIC_FIXTURE", True)
        info = probe_source(out)
        self.assertEqual((info.width, info.height), (1280, 720))
        self.assertAlmostEqual(info.duration_sec, 9.0, places=1)


class TestSubtitleSlots(unittest.TestCase):
    """Blur-and-subtitle default handling (Mai 2026-11-12 09:37)."""

    def test_default_handling_constant(self) -> None:
        self.assertEqual(DEFAULT_TEXT_HANDLING, "blur_and_subtitle")

    def test_subtitle_blur_produces_slot(self) -> None:
        region = _region(TextClassification.SUBTITLE)
        slots, skipped = replacement_subtitle_slots(
            [_spec(region, ReplacementMode.LOCAL_BLUR)],
            "USER_OWNED", True)
        self.assertEqual(len(slots), 1)
        self.assertEqual(skipped, [])
        slot = slots[0]
        self.assertEqual(slot.slot_id, "slot-txt-001")
        self.assertEqual(slot.start_time, 0.0)
        self.assertEqual(slot.end_time, 3.0)
        self.assertEqual(slot.bbox, region.bbox)
        self.assertEqual(slot.original_text, "这款很好")
        self.assertTrue(all(0.0 <= v <= 1.0
                            for v in slot.normalized_bbox))
        data = slot.to_dict()
        self.assertEqual(data["handling"], "blur_and_subtitle")
        self.assertEqual(data["classification"], "SUBTITLE")
        self.assertEqual(data["frame_size"], [1280, 720])
        self.assertNotIn("vietnamese_text", data)
        self.assertNotIn("translated_text", data)

    def test_promo_blur_produces_slot(self) -> None:
        region = _region(TextClassification.PROMOTIONAL_OVERLAY)
        slots, _ = replacement_subtitle_slots(
            [_spec(region, ReplacementMode.LOCAL_BLUR)],
            "USER_OWNED", True)
        self.assertEqual(len(slots), 1)

    def test_overlay_mode_skipped_with_audit(self) -> None:
        slots, skipped = replacement_subtitle_slots(
            [_spec(_region(), ReplacementMode.SMART_OVERLAY)],
            "USER_OWNED", True)
        self.assertEqual(slots, [])
        self.assertEqual(len(skipped), 1)
        self.assertIn("not LOCAL_BLUR", skipped[0]["reason"])

    def test_protected_label_skipped_by_default(self) -> None:
        region = _region(TextClassification.PRODUCT_LABEL)
        approve_removal(region, "USER_OWNED", True, "tester",
                        acknowledge_ownership_risk=True)
        slots, skipped = replacement_subtitle_slots(
            [_spec(region, ReplacementMode.LOCAL_BLUR)],
            "USER_OWNED", True)
        self.assertEqual(slots, [])
        self.assertIn("protected", skipped[0]["reason"])

    def test_protected_label_slot_with_explicit_override(self) -> None:
        region = _region(TextClassification.PRODUCT_LABEL)
        approve_removal(region, "USER_OWNED", True, "tester",
                        acknowledge_ownership_risk=True)
        slots, skipped = replacement_subtitle_slots(
            [_spec(region, ReplacementMode.LOCAL_BLUR)],
            "USER_OWNED", True, allow_protected=True)
        self.assertEqual(len(slots), 1)
        self.assertEqual(skipped, [])

    def test_unapproved_spec_raises(self) -> None:
        with self.assertRaises(ReplacementRefused):
            replacement_subtitle_slots(
                [_spec(_region(), ReplacementMode.LOCAL_BLUR,
                       approved=False)],
                "USER_OWNED", True)

    def test_unknown_authorization_raises(self) -> None:
        with self.assertRaises(ReplacementRefused):
            replacement_subtitle_slots(
                [_spec(_region(), ReplacementMode.LOCAL_BLUR)],
                "UNKNOWN", True)


if __name__ == "__main__":
    unittest.main()
