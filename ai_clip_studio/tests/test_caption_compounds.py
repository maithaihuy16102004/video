"""Caption compounds + timing (round-2 system 7).

The tester caught 9 compound splits ACROSS TIME (phrase tiling)
and 5 at line wrap on the Zeus/Ep1 re-renders, plus a ~1.7-2.7 s
record-vs-render timing divergence. The tiling and the wrap share
one glue mechanism, and the segment assignment now uses the same
character-proportional time model as phrase_windows.
"""

import re
import unittest
from pathlib import Path

from ai_clip_studio.product_renderer import (
    _split_line_phrases, _split_voice_spans)
from ai_clip_studio.subtitles import (
    MAX_CHARS, _glue_units, _wrap_lines, phrase_windows,
    split_subtitle)

EXAMPLES = Path(__file__).parent.parent.parent / "examples"

# The 9 Zeus time-splits + the Ep1 time-split + the 5 wrap splits,
# as (line, compound) pairs. Each compound must survive in ONE
# phrase and on ONE wrapped line.
TIME_CASES = [
    ("Và trước khi trở thành vua của các vị thần, tôi suýt trở thành món ăn thứ sáu của cha mình.",
     "vị thần"),
    ("Ông từng lật đổ cha mình để giành quyền lực, rồi nghe một lời tiên tri rằng một ngày nào đó con trai ông cũng sẽ làm điều tương tự.",
     "quyền lực"),
    ("Ông từng lật đổ cha mình để giành quyền lực, rồi nghe một lời tiên tri rằng một ngày nào đó con trai ông cũng sẽ làm điều tương tự.",
     "tương tự"),
    ("Vị vua quyền lực nhất thế giới vừa bị đánh bại bởi một hòn đá.",
     "đánh bại"),
    ("Lần lượt năm anh chị em của tôi được giải thoát khỏi bụng cha.",
     "giải thoát"),
    ("Hãy tưởng tượng họ phải mất bao lâu để mặc áo mỗi sáng.",
     "mặc áo"),
    ("Họ trao cho chúng tôi những vũ khí mà không vị thần bình thường nào có thể tạo ra.",
     "tạo ra"),
    ("Khi những người khổng lồ trăm tay tham chiến, cán cân sức mạnh bắt đầu thay đổi.",
     "tham chiến"),
    ("Và thời đại của các vị thần Olympus bắt đầu từ đó.",
     "bắt đầu"),
    ("Nếu ai đó tưởng tượng những đoàn quân hùng dũng tiến qua đồng cỏ, cờ tung bay, nhạc nền hoành tráng thì hãy xóa hình ảnh đó đi.",
     "hùng dũng"),
]

WRAP_CASES = [
    ("cha bạn chưa từng nuốt sống năm anh chị em của bạn", "anh chị em"),
    ("Trung đoàn Bộ binh Dự bị Bavaria số 16 của tôi", "số 16"),
    ("Khi Thế chiến thứ nhất bùng nổ, tôi đang sống ở Munich. Dù là công dân Áo, tôi vẫn nộp đơn.",
     "công dân"),
    ("Nếu ai đó tưởng tượng những đoàn quân hùng dũng tiến qua đồng cỏ rộng lớn",
     "đoàn quân"),
    ("một con quái vật khổng lồ sở hữu một sức mạnh khủng khiếp không thể tưởng tượng được",
     "sở hữu"),
]


class TestGlueUnits(unittest.TestCase):
    def test_compound_bigram_glues(self):
        self.assertIn("quyền lực",
                      _glue_units("giành quyền lực".split()))

    def test_three_gram_wins_longest_match(self):
        units = _glue_units("năm anh chị em của bạn".split())
        self.assertIn("anh chị em", units)
        self.assertNotIn("chị em", units)

    def test_digits_glue_left(self):
        self.assertIn("số 16",
                      _glue_units("Bavaria số 16 của".split()))
        self.assertIn("năm 1914",
                      _glue_units("Cuối năm 1914 tôi".split()))
        self.assertIn("thứ 16",
                      _glue_units("trung đoàn thứ 16".split()))

    def test_prefix_glues_right(self):
        self.assertIn("thứ sáu",
                      _glue_units("món ăn thứ sáu".split()))
        self.assertIn("con dê",
                      _glue_units("nuôi bằng sữa con dê".split()))
        self.assertIn("chiếc ví",
                      _glue_units("mang theo chiếc ví".split()))

    def test_compound_ending_in_prefix_word_does_not_glue(self):
        # "trẻ con" ends in "con" but is a compound, not a prefix.
        self.assertEqual(_glue_units("trẻ con đi học".split()),
                         ["trẻ con", "đi", "học"])

    def test_join_reproduces_words(self):
        words = "Vị vua quyền lực nhất thế giới vừa bị đánh bại".split()
        self.assertEqual(" ".join(_glue_units(words)), " ".join(words))


class TestCompoundProtection(unittest.TestCase):
    def test_time_splits_closed(self):
        for line, compound in TIME_CASES:
            phrases = split_subtitle(line)
            self.assertTrue(any(compound in p for p in phrases),
                            f"{compound!r} split in {phrases}")

    def test_wrap_splits_closed(self):
        for phrase, compound in WRAP_CASES:
            lines = _wrap_lines(phrase)
            self.assertTrue(any(compound in ln for ln in lines),
                            f"{compound!r} split in {lines}")

    def test_no_compound_splits_in_real_scripts(self):
        strip = ",;:.!?…—-“”‘’\"'«»"
        from ai_clip_studio.subtitles import _COMPOUND_NGRAMS
        for name in ("zeus_ep01_fall_of_cronus.studio.md",
                     "hitler_ep01_munich_1914.studio.md"):
            text = (EXAMPLES / name).read_text(encoding="utf-8")
            for t in re.findall(r"^TEXT:\s*(.+)$", text, flags=re.M):
                phrases = split_subtitle(t)
                toks = [w.strip(strip).lower() for w in t.split()]
                for n in (3, 2):
                    for j in range(len(toks) - n + 1):
                        if tuple(toks[j:j + n]) in _COMPOUND_NGRAMS:
                            surf = " ".join(
                                w.strip(strip)
                                for w in t.split()[j:j + n])
                            self.assertTrue(
                                any(surf in p.replace("“", "").replace(
                                    "”", "") for p in phrases),
                                f"{surf!r} split in {phrases}")

    def test_phrases_stay_short(self):
        self.assertEqual(MAX_CHARS, 30)
        for name in ("zeus_ep01_fall_of_cronus.studio.md",
                     "hitler_ep01_munich_1914.studio.md"):
            text = (EXAMPLES / name).read_text(encoding="utf-8")
            for t in re.findall(r"^TEXT:\s*(.+)$", text, flags=re.M):
                for p in split_subtitle(t):
                    # +8: the fragment-merge allowance (a merged
                    # fragment may extend a phrase past MAX_CHARS
                    # by its own length); the wrap bound below is
                    # the binding display constraint.
                    self.assertLessEqual(len(p), MAX_CHARS + 8, p)
                    self.assertLessEqual(len(_wrap_lines(p)), 2, p)


class TestFragmentMerge(unittest.TestCase):
    def test_short_fragment_joins_a_neighbour(self):
        phrases = split_subtitle(
            "Một cách giải quyết vấn đề rất… châu Âu năm 1914.")
        self.assertNotIn("rất…", phrases)
        self.assertTrue(any("rất…" in p for p in phrases))
        for p in phrases:
            self.assertGreater(len(p.strip(",;:.!?…—-“”‘’\"'«» ")), 5)

    def test_lone_quote_joins_a_neighbour(self):
        phrases = split_subtitle("Tôi là Zeus, vua của các vị thần.”")
        self.assertNotIn("”", phrases)

    def test_lone_short_line_unchanged(self):
        self.assertEqual(split_subtitle("À."), ["À."])

    def test_merge_is_lossless(self):
        line = ("Và đúng lúc tôi đang không biết đời mình sẽ đi đâu… "
                "cả châu Âu quyết định lao vào một cuộc chiến tranh "
                "khổng lồ.")
        self.assertEqual(" ".join(split_subtitle(line)),
                         " ".join(line.split()))

    def test_phrase_windows_enforce_one_frame_minimum(self):
        # Adversarial: a 1 s line whose char-proportional windows
        # would fall below one frame. Every window must span at
        # least one frame (0.042 s rounded) and the line exactly.
        phrases = ["Một cụm từ khá dài ở đây.", "Ngắn.", "rất…",
                   "Một cụm từ khá dài khác nữa."]
        wins = phrase_windows(0.0, 1.0, phrases)
        self.assertAlmostEqual(wins[0]["start"], 0.0)
        self.assertAlmostEqual(wins[-1]["end"], 1.0)
        for w in wins:
            self.assertGreaterEqual(w["end"] - w["start"], 0.042, w)
        self.assertEqual(" ".join(w["phrase"] for w in wins),
                         " ".join(phrases))

    def test_no_subframe_windows_on_real_scripts_at_stub_speed(self):
        # The regression: with 1 s stub lines, Ep1 line 2 produced
        # a 0.026 s window the unified timeline rejected
        # (end_frame must exceed start_frame).
        for name in ("zeus_ep01_fall_of_cronus.studio.md",
                     "hitler_ep01_munich_1914.studio.md"):
            text = (EXAMPLES / name).read_text(encoding="utf-8")
            for t in re.findall(r"^TEXT:\s*(.+)$", text, flags=re.M):
                for w in phrase_windows(0.0, 1.0, split_subtitle(t)):
                    self.assertGreaterEqual(w["end"] - w["start"],
                                            0.042, w)


class TestSegmentTimingModel(unittest.TestCase):
    LINE8 = ("Về sau tôi mới hiểu… ‘Trước Giáng sinh’ là lời nói dối "
             "ngây thơ nhất lịch sử. Cuối năm 1914, Trung đoàn Bộ binh "
             "Dự bị Bavaria số 16 của tôi được đưa tới Mặt trận "
             "phía Tây.")

    def test_assignment_uses_char_proportional_midpoints(self):
        spans = _split_voice_spans(10.608, 4)
        self.assertEqual(
            _split_line_phrases(self.LINE8, spans),
            ["Về sau tôi mới hiểu… ‘Trước Giáng sinh’ là lời",
             "nói dối ngây thơ nhất lịch sử. Cuối năm 1914,",
             "Trung đoàn Bộ binh Dự bị",
             "Bavaria số 16 của tôi được đưa tới Mặt trận phía Tây."])

    def test_record_and_burned_phrases_agree(self):
        # E-S2 regression: the record (line-level windows) and the
        # render (per-segment re-split windows) must show the same
        # phrases, with boundaries within 1 s (was 1.7-2.7 s).
        start, dur = 52.22, 10.608
        spans = _split_voice_spans(dur, 4)
        segs = _split_line_phrases(self.LINE8, spans)
        rec = phrase_windows(start, start + dur,
                             split_subtitle(self.LINE8))
        burned = []
        cur = start
        for span, txt in zip(spans, segs):
            burned.extend(phrase_windows(cur, cur + span,
                                         split_subtitle(txt)))
            cur += span
        self.assertEqual([w["phrase"] for w in rec],
                         [w["phrase"] for w in burned])
        for w in rec[:-1]:
            nearest = min(abs(w["end"] - b["end"])
                          for b in burned[:-1])
            self.assertLess(nearest, 1.0, w)


if __name__ == "__main__":
    unittest.main()
