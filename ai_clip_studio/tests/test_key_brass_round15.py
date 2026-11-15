"""Round 15 (L02-D10): the key prop is brass, not an ink outline.

The unfilled dark key read as a facial smudge near pale faces
(L02-D4). The bow is brass-filled, the shaft and teeth carry a
brass core with an ink edge.
"""
import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.product_renderer import _draw_prop

BRASS = np.array((203, 160, 72), dtype=float)


class TestKeyBrassRound15(unittest.TestCase):
    def test_key_has_brass_fill(self):
        img = Image.new("RGB", (200, 120), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        _draw_prop(draw, 100, 60, kind="key")
        arr = np.asarray(img).astype(float)
        dist = np.linalg.norm(arr - BRASS, axis=2)
        self.assertGreater(int((dist < 12).sum()), 200)

    def test_key_keeps_ink_outline(self):
        img = Image.new("RGB", (200, 120), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        _draw_prop(draw, 100, 60, kind="key")
        arr = np.asarray(img).astype(float)
        dark = (arr.sum(axis=2) < 150).sum()
        self.assertGreater(int(dark), 50)


if __name__ == "__main__":
    unittest.main()
