"""Phase 1 tests — translation fallback, script generation, approval.

Covers the honesty rules:
- Without a Gemini key, DIRECT/NATURAL translation is NOT fabricated:
  segments stay untranslated and flagged for human review.
- AFFILIATE_COPYWRITING fallback builds copy from verified facts only.
- Script approval is required before TTS and cleared by any edit.
- Testimonial wording is flagged unless explicitly confirmed.
- Footage-fit conflicts are reported, never auto-resolved by
  truncation or acceleration.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from ai_clip_studio.affiliate.schema import ProductInfo
from ai_clip_studio.affiliate.script_gen import (
    approve_script,
    check_testimonial_claims,
    clear_approval_on_edit,
    footage_fit_report,
    generate_script,
    script_estimated_total,
)
from ai_clip_studio.affiliate.translation import (
    digit_sequences,
    translate_ocr_tracks,
    translate_segments,
)

PRODUCT = ProductInfo(
    product_name="Hộp đựng đồ nhà bếp",
    product_category="Nhà bếp",
    product_features=["nhựa PP", "nắp kín"],
    product_benefits=["giữ đồ khô ráo"],
    call_to_action="Xem thông tin sản phẩm ở giỏ hàng nhé.",
    brand_name="NhaBep",
)

SEGMENTS = [
    {"start": 0.0, "end": 2.5, "text": "这个产品非常好用"},
    {"start": 2.5, "end": 5.0, "text": "大家可以看一下"},
]


class TestTranslationFallback(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("GEMINI_API_KEY", None)

    def tearDown(self):
        self._env.stop()

    def test_direct_translation_not_fabricated_without_key(self):
        record = translate_segments(SEGMENTS, PRODUCT,
                                    mode="DIRECT_TRANSLATION")
        self.assertEqual(record.engine, "fallback")
        self.assertEqual(record.translated_segments, [])
        self.assertTrue(record.needs_human_review)
        self.assertEqual(len(record.original_segments), 2)
        self.assertEqual(record.original_segments[0]["text"],
                         "这个产品非常好用")

    def test_natural_localization_not_fabricated_without_key(self):
        record = translate_segments(SEGMENTS, PRODUCT,
                                    mode="NATURAL_LOCALIZATION")
        self.assertEqual(record.engine, "fallback")
        self.assertTrue(record.needs_human_review)

    def test_copywriting_fallback_uses_facts_only(self):
        record = translate_segments(
            SEGMENTS, PRODUCT, mode="AFFILIATE_COPYWRITING",
            visible_demonstration="mở hộp, xếp đồ vào")
        self.assertEqual(record.engine, "fallback")
        self.assertEqual(len(record.rewritten_segments), 2)
        joined = " ".join(s["text"] for s in record.rewritten_segments)
        self.assertIn("Hộp đựng đồ nhà bếp", joined)
        self.assertNotIn("giảm giá", joined)
        self.assertNotIn("100%", joined)

    def test_original_translation_rewrite_stay_separate(self):
        record = translate_segments(
            SEGMENTS, PRODUCT, mode="AFFILIATE_COPYWRITING")
        self.assertEqual(record.translated_segments, [])
        self.assertTrue(record.rewritten_segments)
        self.assertTrue(record.original_segments)

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            translate_segments(SEGMENTS, PRODUCT, mode="BOGUS")

    def test_digit_sequences(self):
        self.assertEqual(digit_sequences("Model X200, 500ml, giá 129.000"),
                         ["200", "500", "129.000"])

    def test_ocr_track_translation_preserves_protection(self):
        tracks = [
            {"text_id": "T1", "original_text": "你好",
             "start_time": 0, "end_time": 1,
             "text_classification": "SUBTITLE"},
            {"text_id": "T2", "original_text": "@creator",
             "start_time": 0, "end_time": 1,
             "text_classification": "CREATOR_ATTRIBUTION"},
        ]
        out = translate_ocr_tracks(tracks, PRODUCT)
        self.assertTrue(out[0]["replace_allowed"])
        self.assertFalse(out[1]["replace_allowed"])
        self.assertEqual(out[1]["translation_engine"], "fallback")


class TestScriptGeneration(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("GEMINI_API_KEY", None)

    def tearDown(self):
        self._env.stop()

    def test_fallback_script_structure(self):
        script = generate_script(PRODUCT, variant="problem_solution",
                                 target_seconds=30.0,
                                 visible_demonstration="mở hộp, xếp đồ")
        self.assertEqual(script.engine, "fallback")
        sections = [s.section for s in script.segments]
        self.assertEqual(sections[0], "HOOK")
        self.assertEqual(sections[-1], "CALL_TO_ACTION")
        self.assertIn("PROBLEM", sections)
        self.assertFalse(script.approved)

    def test_all_variants_generate(self):
        for variant in ("natural_review", "demonstration", "problem_solution"):
            script = generate_script(PRODUCT, variant=variant,
                                     target_seconds=15.0)
            self.assertTrue(script.segments)
            self.assertTrue(all(s.text.strip() for s in script.segments))

    def test_fallback_copy_uses_product_facts(self):
        script = generate_script(PRODUCT, variant="natural_review",
                                 target_seconds=30.0)
        joined = " ".join(s.text for s in script.segments)
        self.assertIn("Hộp đựng đồ nhà bếp", joined)
        self.assertIn("nhựa PP", joined)

    def test_no_testimonial_in_fallback_copy(self):
        script = generate_script(PRODUCT, variant="natural_review",
                                 target_seconds=30.0)
        for seg in script.segments:
            self.assertEqual(check_testimonial_claims(seg.text), [])

    def test_approval_lifecycle(self):
        script = generate_script(PRODUCT, variant="natural_review",
                                 target_seconds=30.0)
        approve_script(script, approved_by="Mai", note="ok")
        self.assertTrue(script.approved)
        self.assertEqual(script.approved_by, "Mai")
        self.assertTrue(script.approved_at)
        clear_approval_on_edit(script)
        self.assertFalse(script.approved)
        self.assertEqual(script.approved_by, "")

    def test_unknown_variant_rejected(self):
        with self.assertRaises(ValueError):
            generate_script(PRODUCT, variant="bogus", target_seconds=30.0)

    def test_footage_fit_reports_overflow(self):
        script = generate_script(PRODUCT, variant="problem_solution",
                                 target_seconds=60.0)
        report = footage_fit_report(script, footage_seconds=5.0)
        self.assertFalse(report["fits"])
        self.assertGreater(report["overflow_sec"], 0)
        self.assertIn("shorten_script_with_approval", report["options"])
        self.assertIn("report_unresolved_conflict", report["options"])

    def test_footage_fit_passes_when_room(self):
        script = generate_script(PRODUCT, variant="natural_review",
                                 target_seconds=15.0)
        report = footage_fit_report(script, footage_seconds=300.0)
        self.assertTrue(report["fits"])

    def test_testimonial_checker(self):
        self.assertTrue(check_testimonial_claims("Mình đã dùng thử rồi"))
        self.assertEqual(check_testimonial_claims(
            "Sản phẩm có nắp kín, giữ đồ khô ráo."), [])

    def test_estimated_total_positive(self):
        script = generate_script(PRODUCT, variant="natural_review",
                                 target_seconds=30.0)
        self.assertGreater(script_estimated_total(script), 0)


if __name__ == "__main__":
    unittest.main()
