"""Unit tests for ai_clip_studio.subtitles (stdlib unittest).

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/video-16x9-v2/
"""
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.subtitles import (
    FONT_PX, MAX_CHARS, check_phone_legibility, draw_phrase,
    get_font, phrase_windows, split_subtitle,
)

# Exactly 132 characters -- the length of the old renderer's failing
# final line (which the 64->32 px ladder still cut short).
LONG_LINE = ("Cô gái mỉm cười, cảm ơn anh rồi bước lên xe buýt, mang theo "
             "chiếc ví và một buổi chiều mưa lạnh bỗng trở nên ấm áp hơn "
             "rất nhiều đó.")


class TestSubtitles(unittest.TestCase):
    def test_long_line_is_132_chars(self):
        self.assertEqual(len(LONG_LINE), 132)

    def test_long_line_splits_into_at_least_three_phrases(self):
        phrases = split_subtitle(LONG_LINE)
        self.assertGreaterEqual(len(phrases), 3)

    def test_every_phrase_within_max_chars(self):
        phrases = split_subtitle(LONG_LINE)
        for p in phrases:
            self.assertLessEqual(len(p), MAX_CHARS, f"phrase too long: {p!r}")
            self.assertLessEqual(len(p), 42)

    def test_no_word_is_cut(self):
        phrases = split_subtitle(LONG_LINE)
        # joining the phrases reproduces the line exactly (spaces norm.)
        self.assertEqual(" ".join(phrases), " ".join(LONG_LINE.split()))
        # every phrase is a run of whole original words
        words = LONG_LINE.split()
        for p in phrases:
            for w in p.split():
                self.assertIn(w, words)

    def test_split_prefers_punctuation_breaks(self):
        phrases = split_subtitle("Xin chào, tôi tên là Lan, tôi đến từ Hà Nội.")
        # the first phrase should end at a comma, not mid-clause
        self.assertTrue(phrases[0].rstrip().endswith(",")
                        or len(phrases) == 1)

    def test_short_line_unchanged(self):
        self.assertEqual(split_subtitle("Xin chào."), ["Xin chào."])

    def test_empty_line(self):
        self.assertEqual(split_subtitle(""), [])
        self.assertEqual(split_subtitle("   "), [])

    def test_font_is_fixed_64(self):
        self.assertEqual(FONT_PX, 64)
        self.assertEqual(get_font().size, 64)
        self.assertEqual(get_font(64).size, 64)

    def test_draw_phrase_uses_fixed_font(self):
        img = Image.new("RGB", (1920, 1080), (15, 30, 51))
        d = ImageDraw.Draw(img)
        _, _, size = draw_phrase(d, "Xin chào buổi sáng.", font_px=64)
        self.assertEqual(size, 64)
        # white caption pixels actually drawn near the bottom
        arr = np.asarray(img)
        self.assertGreater(float(np.mean(arr[900:, :, :] > 200)), 0.0)

    def test_phrase_windows_span_the_line(self):
        phrases = split_subtitle(LONG_LINE)
        wins = phrase_windows(10.0, 22.0, phrases)
        self.assertEqual(len(wins), len(phrases))
        self.assertAlmostEqual(wins[0]["start"], 10.0)
        self.assertAlmostEqual(wins[-1]["end"], 22.0)
        for a, b in zip(wins, wins[1:]):
            self.assertAlmostEqual(a["end"], b["start"], places=2)
        self.assertEqual([w["phrase"] for w in wins], phrases)

    def test_phrase_windows_proportional_to_length(self):
        wins = phrase_windows(0.0, 10.0, ["Ngắn.", "Một cụm dài hơn nhiều."])
        short = wins[0]["end"] - wins[0]["start"]
        long_ = wins[1]["end"] - wins[1]["start"]
        self.assertGreater(long_, short)

    def test_phrase_windows_empty(self):
        self.assertEqual(phrase_windows(0.0, 5.0, []), [])

    def test_phone_legibility_fixed_64_passes(self):
        res = check_phone_legibility(1280, font_px=64)
        self.assertTrue(res["passes"])
        self.assertGreaterEqual(res["ratio"], 0.03)
        self.assertAlmostEqual(res["ratio"], 64 / 1080, places=3)
        self.assertAlmostEqual(res["downscaled_font_px"], 64 * 720 / 1080,
                               places=1)

    def test_phone_legibility_small_font_fails(self):
        res = check_phone_legibility(1280, font_px=20)
        self.assertFalse(res["passes"])
        self.assertLess(res["ratio"], 0.03)


if __name__ == "__main__":
    unittest.main()
