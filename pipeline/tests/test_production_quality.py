import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from production_quality import enrich_scene_plan, evaluate_render_metrics, normalize_topic_key, select_preset, validate_plan


class ProductionQualityTests(unittest.TestCase):
    def test_vietnamese_topic_normalization(self):
        self.assertEqual(normalize_topic_key("Trí tuệ nhân tạo AGI"), "tri_tue_nhan_tao_agi")

    def test_vietnamese_topic_routes_to_ai_preset(self):
        presets = {"tri_tue_nhan_tao": {"category": "AI"}, "tai_chinh_ca_nhan": {"category": "Finance"}}
        key, preset = select_preset("Trí tuệ nhân tạo AGI", presets)
        self.assertEqual(key, "tri_tue_nhan_tao")
        self.assertEqual(preset["category"], "AI")

    def test_single_generic_token_does_not_misroute(self):
        presets = {"tri_tue_nhan_tao": {"category": "AI"}}
        key, preset = select_preset("Trí tưởng tượng trong nghệ thuật", presets)
        self.assertIsNone(key)
        self.assertIsNone(preset)

    def test_enriched_plan_passes_visual_quality_gate(self):
        config = {"scenes": [
            {"headline": "Hook", "spoken": "Một câu mở đầu cụ thể."},
            {"headline": "Evidence", "spoken": "Một luận điểm có hình minh họa."},
            {"headline": "CTA", "spoken": "Một kết luận rõ ràng."},
        ]}
        report = validate_plan(enrich_scene_plan(config, "AGI"))
        self.assertTrue(report.passed)
        self.assertEqual(report.metrics["visual_beat_count"], 9)
        self.assertEqual(report.metrics["structured_visual_beat_count"], 9)
        self.assertGreaterEqual(report.metrics["minimum_hold_seconds"], 0.5)

    def test_rejects_decorative_prompts_without_motion_arc(self):
        config = {"scenes": [
            {"spoken": "A", "edit_plan": {"visual_prompts": ["a", "b", "c"], "max_visual_beat_seconds": 3}},
            {"spoken": "B", "edit_plan": {"visual_prompts": ["a", "b", "c"], "max_visual_beat_seconds": 3}},
            {"spoken": "C", "edit_plan": {"visual_prompts": ["a", "b", "c"], "max_visual_beat_seconds": 3}},
        ]}
        report = validate_plan(config)
        self.assertFalse(report.passed)
        self.assertTrue(any("motion arc" in error for error in report.errors))

    def test_render_gate_checks_vertical_video_and_loudness(self):
        probe = {"streams": [
            {"codec_type": "video", "width": 1080, "height": 1920, "r_frame_rate": "30/1"},
            {"codec_type": "audio", "sample_rate": "48000", "channels": 2},
        ], "format": {"duration": "42.0"}}
        report = evaluate_render_metrics(probe, {"input_i": "-14.1", "input_tp": "-1.5", "input_lra": "2.4"})
        self.assertTrue(report.passed)
        self.assertEqual(report.metrics["width"], 1080)


if __name__ == "__main__":
    unittest.main()
