"""Tests for the structured Vietnamese script parser (shared engine)."""
import unittest

from ai_clip_studio.vi_script_parser import (
    extract_action_cues, is_structured_vi_script, parse_vi_script,
)

REAL_SCRIPT = "/home/hatch/workspace/acceptance_loop/test_chiec_vi_trong_mua/script.txt"

OTHER_SCRIPT = """# KỊCH BẢN — CƠN MƯA ĐẦU MÙA

Nhân vật:
- Hùng: Nam sinh viên, giọng nam trẻ.
- Mai: Nữ sinh viên, giọng nữ trẻ.

## CẢNH 01 — SÂN TRƯỜNG

Bối cảnh: Sân trường buổi chiều, mưa phùn.

Hành động: Hùng chạy nhanh qua sân trường rồi dừng lại dưới mái hiên.

Người dẫn chuyện: "Chiều mưa, Hùng chạy vội về ký túc xá."

Hùng: "Mưa to quá, không về được rồi!"

Âm thanh: Mưa phùn, tiếng bước chân chạy.

## CẢNH 02 — MÁI HIÊN

Bối cảnh: Mái hiên ký túc xá.

Hành động: Mai bước đến, giơ tay chào Hùng.

Mai: "Anh cũng bị kẹt mưa à?"

Hùng: "Ừ, đứng đây chờ mưa ngớt vậy."
"""


class TestViScriptParser(unittest.TestCase):
    def test_parse_real_script(self):
        text = open(REAL_SCRIPT, encoding="utf-8").read()
        self.assertTrue(is_structured_vi_script(text))
        parsed = parse_vi_script(text)
        self.assertEqual(len(parsed.scenes), 4)
        self.assertEqual([s.number for s in parsed.scenes], [1, 2, 3, 4])
        # 10 spoken lines only: 4 narrator + 3 Minh + 3 Lan
        self.assertEqual(len(parsed.lines), 10)
        speakers = [l.speaker for l in parsed.lines]
        self.assertEqual(speakers.count("narrator"), 4)
        self.assertEqual(speakers.count("Minh"), 3)
        self.assertEqual(speakers.count("Lan"), 3)
        # no metadata / header / description is spoken
        joined = " ".join(l.text for l in parsed.lines)
        for forbidden in ("KỊCH BẢN", "Nhân vật", "Bối cảnh", "Yêu cầu",
                          "Premium", "16:9", "Hành động"):
            self.assertNotIn(forbidden, joined)
        # first + last lines are the script's own words
        self.assertTrue(parsed.lines[0].text.startswith("Đêm mưa, Minh vội"))
        self.assertTrue(parsed.lines[-1].text.startswith("Chuyến xe cuối"))
        # characters with voice hints
        names = {c["name"]: c for c in parsed.characters}
        self.assertIn("Minh", names)
        self.assertIn("Lan", names)
        self.assertEqual(names["Minh"]["voice_hint"], "giọng nam")
        self.assertEqual(names["Lan"]["voice_hint"], "giọng nữ")

    def test_action_cues_from_real_script(self):
        text = open(REAL_SCRIPT, encoding="utf-8").read()
        parsed = parse_vi_script(text)
        cues1 = parsed.scenes[0].action_cues
        for cue in ("walk_fast", "stop", "bend_pick", "look"):
            self.assertIn(cue, cues1)
        cues2 = parsed.scenes[1].action_cues
        self.assertIn("run", cues2)
        self.assertIn("open", cues2)
        self.assertIn("search", cues2)
        cues4 = parsed.scenes[3].action_cues
        self.assertIn("bus", cues4)
        self.assertIn("board", cues4)
        self.assertIn("wave", cues4)

    def test_board_cue_requires_a_vehicle(self):
        # Zeus SC10: "Zeus bước lên bậc thang Olympus" (steps)
        # matched bare "bước lên" and drew a modern bus behind
        # every Olympus shot. Boarding needs the vehicle named.
        self.assertNotIn(
            "board",
            extract_action_cues("Zeus bước lên bậc thang Olympus."))
        self.assertIn(
            "board",
            extract_action_cues("Lan bước lên xe buýt."))
        self.assertIn(
            "board", extract_action_cues("Lan bước lên xe."))

    def test_bus_cue_requires_a_bus_word(self):
        self.assertNotIn(
            "bus", extract_action_cues("Một chiếc xe ngựa kéo qua."))
        self.assertIn(
            "bus", extract_action_cues("Một chiếc xe buýt đến."))

    def test_parse_other_script_not_hardcoded(self):
        parsed = parse_vi_script(OTHER_SCRIPT)
        self.assertEqual(len(parsed.scenes), 2)
        self.assertEqual(len(parsed.lines), 4)
        self.assertEqual([l.speaker for l in parsed.lines],
                         ["narrator", "Hùng", "Mai", "Hùng"])
        self.assertIn("run", parsed.scenes[0].action_cues)
        self.assertIn("wave", parsed.scenes[1].action_cues)

    def test_unstructured_text_raises(self):
        with self.assertRaises(ValueError):
            parse_vi_script("Lan: Chào buổi sáng.\nMinh: Tôi mở cửa.")
        self.assertFalse(is_structured_vi_script("Lan: Chào buổi sáng."))

    def test_extract_action_cues_generic(self):
        cues = extract_action_cues("Cô ấy chạy đến rồi dừng lại và cúi xuống nhặt đồ.")
        self.assertEqual(cues[:3], ["run", "stop", "bend_pick"])


if __name__ == "__main__":
    unittest.main()
