"""Stage 3 engine tests: moustache (trait-driven, never name-driven).

Brief task 1: (a) "Bavarian" text -> NO moustache (the "ria" substring
trap); (b) explicit moustache trait (incl. Hitler's 1914-photo trait
text from Ep1 v2) -> moustache IS drawn; (c) explicit female traits
-> female template, never a silent male default.

Run: python3 -m unittest ai_clip_studio.tests.test_engine_stage3_moustache
from ~/workspace/video-16x9-v2/
"""
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.animation.character_art import (
    STYLE_LOCK, draw_character_v4)
from ai_clip_studio.animation.primitives import standing
from ai_clip_studio.product_renderer import map_character

# The 1914-photo trait text carried by Ep1 v2 for CHAR_HITLER.
PHOTO_TRAIT = ("Period-appropriate moustache based on verified 1914 "
               "photographs")


def _band_dark(char_dict):
    """Render a portrait and count dark pixels in the moustache band
    (mouth line minus 0.32r..0.05r, face-centre x window). The same
    band is compared across portraits, so the measure is relative:
    a drawn moustache roughly triples the count vs the bare face."""
    ch = map_character(char_dict, 0)
    img = Image.new("RGB", (700, 900), (240, 240, 235))
    standing(ch, 350, 820, facing=1)
    d = ImageDraw.Draw(img, "RGBA")
    joints = draw_character_v4(d, ch, expression="neutral",
                               view="profile")
    arr = np.asarray(img).astype(int)
    r = ch.head_r
    hx, hy = joints["head"]
    my = hy + STYLE_LOCK["mouth_dy_frac_of_r"] * r
    x0, x1 = int(hx - 0.1 * r), int(hx + 0.75 * r)
    y0, y1 = int(my - 0.32 * r), int(my - 0.05 * r)
    patch = arr[y0:y1, x0:x1]
    return ch, int((patch.sum(axis=2) < 200).sum())


class TestMoustacheTraits(unittest.TestCase):
    def test_bavarian_text_yields_no_moustache(self):
        ch = map_character({
            "name": "Soldier",
            "description": "Bavarian soldier, 1914 uniform",
            "costume_text": "Quân phục Bavaria năm 1914"}, 0)
        self.assertFalse(ch.moustache,
                         "Bavarian/Bavaria must not trigger the 'ria' word")

    def test_explicit_full_trait_draws_moustache(self):
        ch = map_character({
            "name": "Adolf Hitler", "description": "Protagonist",
            "moustache_style": "full"}, 0)
        self.assertTrue(ch.moustache)
        self.assertEqual(ch.moustache_style, "full")

    def test_photo_trait_text_draws_moustache(self):
        ch = map_character({
            "name": "Adolf Hitler", "description": "Protagonist",
            "traits": [PHOTO_TRAIT]}, 0)
        self.assertTrue(
            ch.moustache,
            "the 1914-photo trait text must yield a moustache via "
            "the word-boundary fallback")

    def test_explicit_none_overrides_trait_text(self):
        ch = map_character({
            "name": "Adolf Hitler", "description": "Protagonist",
            "moustache_style": "none", "traits": [PHOTO_TRAIT]}, 0)
        self.assertFalse(ch.moustache,
                         "explicit 'none' beats the trait text")

    def test_explicit_moustache_styles_preserved(self):
        for style in ("toothbrush", "handlebar"):
            # Non-registry name: registry instances (minh/lan/lustig/
            # officer) keep their locked traits by design.
            ch = map_character({
                "name": "Colonel", "description": "officer",
                "moustache_style": style}, 0)
            self.assertTrue(ch.moustache)
            self.assertEqual(ch.moustache_style, style)

    def test_explicit_female_template(self):
        ch = map_character({
            "name": "An", "description": "student",
            "gender": "female"}, 0)
        self.assertEqual(ch.template, "female")
        self.assertFalse(ch.moustache)

    def test_female_markers_never_silent_male_default(self):
        ch = map_character({
            "name": "Bà Cụ", "description": "bà lão bán vé số",
            "voice_hint": "giọng nữ già"}, 0)
        self.assertNotEqual(ch.template, "male")
        self.assertFalse(ch.moustache)

    def test_moustache_drawn_at_render_level(self):
        # Render-level: the explicit trait must put dark pixels in
        # the moustache band; the Bavarian text must not.
        _, bare = _band_dark({
            "name": "Soldier",
            "description": "Bavarian soldier, 1914 uniform",
            "costume_text": "Quân phục Bavaria năm 1914"})
        _, drawn = _band_dark({
            "name": "Adolf Hitler", "description": "Protagonist",
            "moustache_style": "full"})
        self.assertGreater(drawn, 2 * bare,
                           f"moustache band: drawn={drawn} bare={bare}")


if __name__ == "__main__":
    unittest.main()
