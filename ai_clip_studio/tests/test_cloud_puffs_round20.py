"""Round 20 (polish): wide sky clouds get a broken-up top edge.

Wide clouds (aspect > 2) read as flat ellipses when their top
bumps scale by ry alone. They now get five bumps whose height
floors at a fraction of rx; round clouds keep the historical
layout exactly.
"""
import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.environment_v2 import _draw_cloud_blob

BG = (60, 50, 40)


def _top_roughness(rx, ry):
    img = Image.new("RGB", (400, 200), BG)
    _draw_cloud_blob(ImageDraw.Draw(img), 200, 100, rx, ry,
                     (220, 220, 215), (20, 34, 43))
    a = np.asarray(img).astype(int)
    mask = np.abs(a - np.array(BG)).sum(axis=2) > 30
    tops = []
    for x in range(200 - rx, 200 + rx):
        col = np.nonzero(mask[:, x])[0]
        if len(col):
            tops.append(col.min())
    tops = np.array(tops)
    return float(tops.max() - tops.min())


class TestCloudPuffs(unittest.TestCase):
    def test_wide_cloud_top_edge_is_broken(self):
        # Measured 12 px: five bumps break the top edge; the
        # old ry-scaled layout measured ~2-3 px (flat).
        self.assertGreater(_top_roughness(97, 20), 8.0)

    def test_round_cloud_keeps_puffy_edge(self):
        self.assertGreater(_top_roughness(50, 50), 10.0)


if __name__ == "__main__":
    unittest.main()
