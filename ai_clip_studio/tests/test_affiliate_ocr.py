"""Tests: OCR tracking, classification, review queue, approvals.

All tests use the StubOCREngine (canned detections) or pure
functions, so they run without any OCR backend installed. Real-engine
behavior is proven separately by the venv proof run.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from ai_clip_studio.affiliate.video.models import (
    BBox, TextClassification, TextRegion)
from ai_clip_studio.affiliate.video.ocr import (
    OCRDetection, StubOCREngine, approve_removal, classify_text_region,
    get_ocr_engine, manual_text_region, ocr_unavailable_report,
    review_queue, text_similarity, track_detections)

FRAME = (1280, 720)


def _det(text: str, x: float, y: float, w: float, h: float,
         conf: float = 0.9) -> OCRDetection:
    return OCRDetection(text=text, confidence=conf,
                        polygon=[(x, y), (x + w, y),
                                 (x + w, y + h), (x, y + h)])


def _region(classification: TextClassification) -> TextRegion:
    return TextRegion(
        text_id="txt-001", track_id="track-001", original_text="测试",
        start_time=0.0, end_time=3.0, bbox=BBox(100, 600, 400, 50),
        frame_size=FRAME, classification=classification,
        classification_reason="test")


class TestTextSimilarity(unittest.TestCase):
    def test_identical_and_contained(self) -> None:
        self.assertEqual(text_similarity("你好世界", "你好世界"), 1.0)
        self.assertGreaterEqual(text_similarity("你好", "你好世界"), 0.8)

    def test_different_text_low(self) -> None:
        self.assertLess(text_similarity("你好世界", "限时优惠"), 0.5)


class TestTracking(unittest.TestCase):
    def test_stable_subtitle_becomes_one_track(self) -> None:
        detections = {
            0.0: [_det("这款收纳盒非常实用", 440, 620, 400, 50)],
            1.0: [_det("这款收纳盒非常实用", 442, 620, 398, 50)],
            2.0: [_det("这款收纳盒非常实用", 440, 621, 400, 49)],
        }
        result = track_detections(detections, FRAME)
        self.assertEqual(len(result.regions), 1)
        region = result.regions[0]
        self.assertEqual(region.original_text, "这款收纳盒非常实用")
        self.assertEqual(region.start_time, 0.0)
        self.assertEqual(region.end_time, 3.0)
        self.assertEqual(region.classification, TextClassification.SUBTITLE)
        self.assertEqual(result.dropped_flicker, [])

    def test_flicker_dropped_and_audited(self) -> None:
        detections = {
            0.0: [_det("稳定的", 440, 620, 200, 50, conf=0.95)],
            1.0: [_det("稳定的", 440, 620, 200, 50, conf=0.95),
                  _det("闪", 100, 100, 40, 30, conf=0.2)],
            2.0: [_det("稳定的", 440, 620, 200, 50, conf=0.95)],
        }
        result = track_detections(detections, FRAME)
        self.assertEqual(len(result.regions), 1)
        self.assertEqual(len(result.dropped_flicker), 1)
        self.assertEqual(result.dropped_flicker[0]["text"], "闪")

    def test_moving_text_tracks_with_gap(self) -> None:
        detections = {
            0.0: [_det("限时优惠", 900, 100, 200, 60)],
            1.0: [],
            2.0: [_det("限时优惠", 800, 100, 200, 60)],
        }
        result = track_detections(detections, FRAME, iou_threshold=0.1)
        self.assertEqual(len(result.regions), 1)

    def test_stub_engine_feeds_tracking(self) -> None:
        engine = StubOCREngine({
            "a.jpg": [_det("你好", 100, 600, 120, 40)],
            "b.jpg": [_det("你好", 100, 600, 120, 40)],
        })
        by_time = {0.0: engine.recognize("a.jpg"),
                   1.0: engine.recognize("b.jpg")}
        result = track_detections(by_time, FRAME)
        self.assertEqual(len(result.regions), 1)
        self.assertEqual(result.regions[0].original_text, "你好")


class TestClassification(unittest.TestCase):
    def test_persistent_corner_is_watermark(self) -> None:
        cls, reason, review = classify_text_region(
            BBox(1000, 10, 200, 30), FRAME, 9.0, 1.0, "SYNTHETIC 样品")
        self.assertEqual(cls, TextClassification.WATERMARK)
        self.assertTrue(review)
        self.assertIn("corner", reason)

    def test_corner_account_marker_is_attribution(self) -> None:
        cls, _, review = classify_text_region(
            BBox(1000, 10, 200, 30), FRAME, 9.0, 1.0, "@creator123")
        self.assertEqual(cls, TextClassification.CREATOR_ATTRIBUTION)
        self.assertTrue(review)

    def test_bottom_band_is_subtitle(self) -> None:
        cls, _, review = classify_text_region(
            BBox(400, 620, 480, 50), FRAME, 3.0, 0.3, "这款很好")
        self.assertEqual(cls, TextClassification.SUBTITLE)
        self.assertFalse(review)

    def test_small_center_text_is_label(self) -> None:
        cls, _, review = classify_text_region(
            BBox(530, 430, 220, 40), FRAME, 3.0, 0.3, "净含量：500ml")
        self.assertEqual(cls, TextClassification.PRODUCT_LABEL)
        self.assertTrue(review)

    def test_entering_promo_at_right_edge_is_promo(self) -> None:
        # Regression: measured RapidOCR box of the sliding promo's
        # first fragment (fixture proof run) — must not read as a
        # product label.
        cls, _, review = classify_text_region(
            BBox(1020, 121, 254, 67), FRAME, 1.0, 0.1, "限时优惠")
        self.assertEqual(cls, TextClassification.PROMOTIONAL_OVERLAY)
        self.assertTrue(review)

    def test_unmatched_is_unknown(self) -> None:
        cls, _, review = classify_text_region(
            BBox(500, 300, 300, 60), FRAME, 2.0, 0.2, "中间文字")
        self.assertEqual(cls, TextClassification.UNKNOWN)
        self.assertTrue(review)


class TestApprovalGate(unittest.TestCase):
    def test_unknown_authorization_refused(self) -> None:
        with self.assertRaises(ValueError):
            approve_removal(_region(TextClassification.SUBTITLE),
                            "UNKNOWN", True, "tester")

    def test_unconfirmed_refused(self) -> None:
        with self.assertRaises(ValueError):
            approve_removal(_region(TextClassification.SUBTITLE),
                            "USER_OWNED", False, "tester")

    def test_protected_needs_ownership_ack(self) -> None:
        with self.assertRaises(ValueError):
            approve_removal(_region(TextClassification.WATERMARK),
                            "USER_OWNED", True, "tester")
        region = approve_removal(_region(TextClassification.WATERMARK),
                                 "USER_OWNED", True, "tester",
                                 acknowledge_ownership_risk=True)
        self.assertTrue(region.removal_approved)
        self.assertEqual(region.removal_approval["approved_by"], "tester")

    def test_subtitle_approval_ok(self) -> None:
        region = approve_removal(_region(TextClassification.SUBTITLE),
                                 "LICENSED", True, "tester")
        self.assertTrue(region.removal_approved)

    def test_classification_alone_approves_nothing(self) -> None:
        region = _region(TextClassification.SUBTITLE)
        self.assertFalse(region.removal_approved)
        self.assertIsNone(region.removal_approval)


class TestManualAndQueue(unittest.TestCase):
    def test_manual_region_validation(self) -> None:
        region = manual_text_region(
            "m-1", "手动文字", 1.0, 2.0, BBox(10, 10, 100, 30), FRAME)
        self.assertEqual(region.source, "manual")
        self.assertFalse(region.needs_review)
        with self.assertRaises(ValueError):
            manual_text_region("m-2", "", 1.0, 2.0,
                               BBox(10, 10, 100, 30), FRAME)
        with self.assertRaises(ValueError):
            manual_text_region("m-3", "x", 2.0, 1.0,
                               BBox(10, 10, 100, 30), FRAME)
        with self.assertRaises(ValueError):
            manual_text_region("m-4", "x", 0.0, 1.0,
                               BBox(1200, 10, 200, 30), FRAME)

    def test_review_queue_prioritizes_watermarks(self) -> None:
        regions = [
            _region(TextClassification.WATERMARK),
            _region(TextClassification.SUBTITLE),
        ]
        regions[0].needs_review = True
        regions[0].review_reasons = ["persistent corner graphic"]
        regions[1].needs_review = True
        regions[1].review_reasons = ["low confidence"]
        queue = review_queue(regions)
        self.assertEqual(len(queue), 2)
        self.assertEqual(queue[0]["review_priority"], "high")
        self.assertEqual(queue[1]["review_priority"], "normal")

    def test_ocr_track_dict_is_schema_shaped(self) -> None:
        region = _region(TextClassification.SUBTITLE)
        data = region.to_ocr_track_dict()
        self.assertEqual(data["text_classification"], "SUBTITLE")
        box = data["bounding_box"]
        self.assertTrue(all(0.0 <= v <= 1.0 for v in box))
        from ai_clip_studio.affiliate.schema import validate_project
        issues = validate_project({
            "project_id": "ocr-test",
            "ocr_tracks": [data],
        })
        self.assertEqual(issues, [])

    def test_unavailable_report_shape(self) -> None:
        report = ocr_unavailable_report()
        self.assertFalse(report["ocr_available"])
        self.assertIn("fallback", report)
        self.assertIsInstance(report["backends"], list)

    def test_get_engine_reports_status(self) -> None:
        # On system python no engine is installed: must return None +
        # a status dict, never raise and never fake an engine.
        engine, status = get_ocr_engine()
        if engine is None:
            self.assertFalse(status["available"])
            self.assertTrue(status["attempts"])
        else:  # pragma: no cover - env with an engine installed
            self.assertTrue(status["available"])
            self.assertIn("recognize", dir(engine))


if __name__ == "__main__":
    unittest.main()
