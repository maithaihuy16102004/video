"""Unit tests for the language gate (§5) and the 9:16 framing (§8).

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/agent/
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.framing_9x16 import (
    VERTICAL_SIZE, vertical_camera_for_shot, vertical_crop_for_shot)
from ai_clip_studio.language_gate import (
    check_production_language, english_score, resolve_voice)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera

VI_LINE = "Bên trong chiếc ví có một tấm ảnh đã cũ."
VI_LINE_2 = "May quá. Tôi cũng đang tìm người đánh rơi nó."
EN_LINE = "He sold the Eiffel Tower twice, and nobody stopped him."


class TestLanguageGate(unittest.TestCase):
    def test_vietnamese_lines_score_low(self):
        self.assertLess(english_score(VI_LINE), 0.3)
        self.assertLess(english_score(VI_LINE_2), 0.3)

    def test_english_lines_score_high(self):
        self.assertGreaterEqual(english_score(EN_LINE), 0.6)
        self.assertGreaterEqual(
            english_score("Nobody reported the crime, because the victim "
                          "was too embarrassed."), 0.6)

    def test_vietnamese_production_with_vietnamese_captions_passes(self):
        result = check_production_language(
            "vi-VN", [VI_LINE, VI_LINE_2], [VI_LINE])
        self.assertTrue(result["ok"])
        self.assertEqual(result["violations"], [])

    def test_eiffel_v5_english_subtitles_fail(self):
        # The real v5 defect: 5 English caption lines in a vi-VN
        # production. The gate must FAIL, not "pass with a warning".
        captions = [
            "He sold the Eiffel Tower twice, and nobody stopped him.",
            "One dealer believed him, paid the bribe, and handed over the money.",
            "Lustig took the cash and left Paris on the very next train.",
            "Nobody reported the crime, because the victim was too embarrassed.",
            "So Lustig came back to Paris and tried to sell the tower a second time.",
        ]
        result = check_production_language("vi-VN", captions)
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["violations"]), 5)

    def test_unsupported_language_is_rejected_not_fallback(self):
        result = check_production_language("en-US", [EN_LINE])
        self.assertFalse(result["ok"])

    def test_resolve_voice_refuses_english_instead_of_fallback(self):
        self.assertEqual(resolve_voice("vi-VN", "narrator"),
                         "avocado_v2:MAI_01")
        self.assertEqual(resolve_voice("vi-VN", "speaker_a", "giọng nam"),
                         "avocado_v2:ronan")
        self.assertEqual(resolve_voice("vi-VN", "speaker_b", "giọng nữ"),
                         "avocado_v2:paloma")
        with self.assertRaises(ValueError):
            resolve_voice("en-US", "narrator")


class TestFraming9x16(unittest.TestCase):
    def test_vertical_crop_is_608x1080_and_keeps_focus(self):
        crop = vertical_crop_for_shot({"shot_type": "medium"}, (960, 540))
        left, top, right, bottom = crop["crop"]
        self.assertEqual((right - left, bottom - top), VERTICAL_SIZE)
        self.assertEqual((left, top), (656, 0))
        self.assertTrue(crop["focus_kept"])

    def test_vertical_crop_clamps_at_frame_edge(self):
        crop = vertical_crop_for_shot({"shot_type": "close_up"}, (100, 540))
        left, _, right, _ = crop["crop"]
        self.assertEqual(left, 0)
        self.assertEqual(right, 608)
        self.assertFalse(crop["focus_kept"])

    def test_vertical_camera_is_9x16_and_dollies_closer(self):
        cam = PerspectiveCamera()
        out = vertical_camera_for_shot({"shot_type": "close_up"}, cam)
        self.assertAlmostEqual(out["camera"].aspect, 9 / 16, places=6)
        self.assertEqual(out["size"], VERTICAL_SIZE)
        # camera moved towards the target
        import math
        d0 = math.dist(cam.position, cam.target)
        d1 = math.dist(out["camera"].position, out["camera"].target)
        self.assertLess(d1, d0)
        self.assertAlmostEqual(d1 / d0, 1 - 0.45, places=6)

    def test_establishing_vertical_warns_about_lost_sides(self):
        out = vertical_camera_for_shot({"shot_type": "establishing"},
                                       PerspectiveCamera())
        self.assertIn("loses the sides", out["reframe_note"])
        crop = vertical_crop_for_shot({"shot_type": "establishing"},
                                      (960, 540))
        self.assertIn("loses its sides", crop["reframe_note"])


if __name__ == "__main__":
    unittest.main()
