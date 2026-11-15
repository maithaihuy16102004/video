"""Round 9 subtitle residuals: no displayed phrase may exceed 30
chars. Three phrases in the R8 draft did (31/31/34): the fragment
merge joined a dangling fragment into a neighbour that was already
near the cap, and the sub-frame window merge joined display text
the same way. The fragment merge now leaves a fragment standalone
when neither neighbour fits, and sub-frame windows stretch to one
frame by moving the shared boundary instead of joining text.
"""

import unittest

from ai_clip_studio.subtitles import (
    MAX_CHARS, phrase_windows, split_subtitle)

LINES = [
    "Trong hang sâu, nơi ánh đuốc không bao giờ tắt.",
    "Hóa ra viên đá lửa huyền thoại… chỉ là một hòn bi ve bị "
    "nung nóng.",
    "Ông Ba nói viên đá phải trở về bệ đá giữa hang, nơi ánh "
    "đuốc không bao giờ tắt.",
]


class TestNoPhraseExceedsMaxChars(unittest.TestCase):
    def test_r8_overlong_lines_split_within_cap(self):
        for line in LINES:
            phrases = split_subtitle(line)
            for p in phrases:
                self.assertLessEqual(len(p), MAX_CHARS, p)
            self.assertEqual(" ".join(phrases),
                             " ".join(line.split()))

    def test_windows_never_join_past_cap(self):
        for line in LINES:
            wins = phrase_windows(0.0, 3.0, split_subtitle(line))
            for w in wins:
                self.assertLessEqual(len(w["phrase"]), MAX_CHARS,
                                     w["phrase"])
                self.assertGreaterEqual(w["end"] - w["start"], 0.042)

    def test_fragment_with_no_fitting_neighbour_stays_alone(self):
        # "tắt." (4) cannot join the 26-char phrase without
        # exceeding 30; it must survive as its own phrase.
        phrases = split_subtitle(LINES[0])
        self.assertIn("tắt.", phrases)

    def test_subframe_window_stretches_without_joining(self):
        # A tiny fragment in a short line: the old code joined it
        # into the neighbour's display text; now its window
        # stretches and the phrases stay separate.
        phrases = ["Một cụm từ khá dài ở đây.", "x.", "Ngắn."]
        wins = phrase_windows(0.0, 0.15, phrases)
        self.assertEqual([w["phrase"] for w in wins], phrases)
        for w in wins:
            self.assertGreaterEqual(w["end"] - w["start"], 0.042)
        self.assertAlmostEqual(wins[0]["start"], 0.0)
        self.assertAlmostEqual(wins[-1]["end"], 0.15)


if __name__ == "__main__":
    unittest.main()
