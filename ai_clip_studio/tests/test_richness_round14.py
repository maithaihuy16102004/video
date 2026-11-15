"""Round 14: richness continued -- peaked ridge, flat-bottomed
clouds, FG branch placement, stronger field rows.
"""
import json
import random
import unittest

from PIL import Image, ImageDraw

from ai_clip_studio.environment_v2 import (
    _draw_cloud_blob,
    _draw_hill_blob,
    _scale_color,
    build_environment,
)
from ai_clip_studio.paint_textures import paint_grass


def _top_series(img):
    px = img.load()
    tops = []
    for x in range(30, 370, 2):
        for y in range(200):
            if px[x, y] != (255, 255, 255):
                tops.append(y)
                break
        else:
            tops.append(200)
    return tops


def _count_peaks(tops, w=10, drop=5):
    """Prominent local maxima of a silhouette top edge: the
    window minimum, dropping >= ``drop`` px toward both window
    edges, deduped within one window. Separates the peaked
    ridge (2-4) from the dome (0) across seeds."""
    n = 0
    last = -99
    for i in range(w, len(tops) - w):
        win = tops[i - w:i + w + 1]
        if (tops[i] == min(win)
                and tops[i] <= tops[i - w] - drop
                and tops[i] <= tops[i + w] - drop
                and i - last > w):
            n += 1
            last = i
    return n


class TestRidgePeaksRound14(unittest.TestCase):
    def test_peaked_silhouette_has_peaks_and_valleys(self):
        for seed in (7, 11, 3):
            img = Image.new("RGB", (400, 200), (255, 255, 255))
            draw = ImageDraw.Draw(img)
            _draw_hill_blob(draw, 200, 120, 180, 80,
                            (100, 110, 90), (0, 0, 0),
                            random.Random(seed), peaked=True)
            self.assertGreaterEqual(
                _count_peaks(_top_series(img)), 2, f"seed {seed}")

    def test_dome_silhouette_stays_unimodal(self):
        for seed in (7, 11, 3):
            img = Image.new("RGB", (400, 200), (255, 255, 255))
            draw = ImageDraw.Draw(img)
            _draw_hill_blob(draw, 200, 120, 180, 80,
                            (100, 110, 90), (0, 0, 0),
                            random.Random(seed), peaked=False)
            self.assertLessEqual(
                _count_peaks(_top_series(img)), 1, f"seed {seed}")

    def test_ridge_flag_on_far_row_only(self):
        timeline = json.load(open(
            "/home/hatch/workspace/agent/jobs/req_e07ea01471d1/"
            "timeline.json"))
        env = build_environment(
            timeline["shots"][1]["v1_location"],
            time_of_day="morning", style={"mood": "warm"})
        for el in env["elements"]:
            if el["id"].startswith("sky_ridge_"):
                self.assertTrue((el.get("extra") or {}).get("ridge"))
            if el["id"].startswith("sky_hill_"):
                self.assertFalse(
                    (el.get("extra") or {}).get("ridge", False))


class TestCloudFlatBottomRound14(unittest.TestCase):
    def test_shade_band_base_is_straight(self):
        colour = (240, 240, 245)
        shade = _scale_color(colour, 0.72)
        img = Image.new("RGB", (400, 200), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        _draw_cloud_blob(draw, 200, 100, 150, 50, colour, None)
        px = img.load()
        bottoms = []
        for x in range(140, 261, 4):
            ys = [y for y in range(200) if px[x, y] == shade]
            if ys:
                bottoms.append(max(ys))
        self.assertGreater(len(bottoms), 10)
        self.assertLessEqual(max(bottoms) - min(bottoms), 2)


class TestFgBranchRound14(unittest.TestCase):
    def test_branches_protrude_inward_below_canopy(self):
        timeline = json.load(open(
            "/home/hatch/workspace/agent/jobs/req_e07ea01471d1/"
            "timeline.json"))
        env = build_environment(
            timeline["shots"][1]["v1_location"],
            time_of_day="morning", style={"mood": "warm"})
        by_id = {e["id"]: e for e in env["elements"]}
        for side in ("L", "R"):
            core = by_id[f"fg_foliage_{side}"]
            branch = by_id[f"fg_foliage_{side}_branch"]
            self.assertEqual(branch["material"], "silhouette")
            self.assertEqual(branch["size"][0], 2.8)
            # Below the canopy centre, closer to frame centre.
            self.assertLess(branch["center"][1], core["center"][1])
            self.assertLess(abs(branch["center"][0]),
                            abs(core["center"][0]))


class TestFieldRowsRound14(unittest.TestCase):
    def test_row_contrast_stronger_than_round13(self):
        # Round 13 measured 8.2 (pin: > 5.0). The round-14 alpha
        # (16 -> 24) must measure stronger, not just pass.
        import numpy as np
        lum = np.asarray(
            paint_grass(3.0, 3.0, (90, 130, 60), 11).convert("L"),
            dtype=float)
        h = lum.shape[0]
        band_h = max(8, h // 12)
        n = h // band_h
        even = [lum[i * band_h:(i + 1) * band_h].mean()
                for i in range(0, n, 2)]
        odd = [lum[i * band_h:(i + 1) * band_h].mean()
               for i in range(1, n, 2)]
        self.assertGreater(float(np.mean(even) - np.mean(odd)), 8.2)


if __name__ == "__main__":
    unittest.main()
