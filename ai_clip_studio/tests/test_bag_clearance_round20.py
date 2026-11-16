"""Round 20 (R19-D2): held props stay visible over worn bags.

Loop 02 #11 f48: An's swinging hand carries the key to the
dead centre of her worn letter bag's rect; the bag draws
after the props, so the key reads 0 brass px. Held-prop DRAW
positions push radially out of every worn-bag rect (the
_clear_head precedent, generalized to rects).
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

import ai_clip_studio.product_renderer as pr
from ai_clip_studio.product_renderer import (
    _clear_rect_radial,
    _clear_worn_bags,
    _render_shot,
)
from ai_clip_studio.tests.test_cue_coverage_round18 import (
    _delivered_shot,
)

RECT = (100.0, 100.0, 200.0, 160.0)  # centre (150, 130)


class TestClearRectRadial(unittest.TestCase):
    def test_outside_untouched(self):
        self.assertEqual(_clear_rect_radial((50, 130), RECT), (50, 130))
        self.assertEqual(
            _clear_rect_radial((207, 130), RECT), (207, 130))

    def test_inside_pushes_to_boundary_plus_margin(self):
        # Dead centre-ish, slightly below: pushed down out
        # the bottom edge + 6 px margin.
        x, y = _clear_rect_radial((150, 140), RECT)
        self.assertAlmostEqual(x, 150.0)
        self.assertAlmostEqual(y, 160.0 + 6.0)
        # Left-of-centre: pushed out the left edge.
        x, y = _clear_rect_radial((120, 130), RECT)
        self.assertAlmostEqual(x, 100.0 - 6.0)
        self.assertAlmostEqual(y, 130.0)

    def test_exact_centre_falls_back_down(self):
        x, y = _clear_rect_radial((150, 130), RECT)
        self.assertAlmostEqual(x, 150.0)
        self.assertAlmostEqual(y, 166.0)

    def test_pushed_points_stay_in_margin_band(self):
        # Every pushed point lands outside the rect and at
        # most one margin (6 px) from it: the prop slides
        # along the bag's edge, never teleports away.
        import math
        for gx in range(94, 207, 3):
            for gy in range(94, 167, 3):
                x, y = _clear_rect_radial((gx, gy), RECT)
                self.assertFalse(
                    RECT[0] <= x <= RECT[2]
                    and RECT[1] <= y <= RECT[3],
                    f"({gx}, {gy}) -> ({x}, {y}) inside rect")
                dx = max(RECT[0] - x, 0.0, x - RECT[2])
                dy = max(RECT[1] - y, 0.0, y - RECT[3])
                self.assertLessEqual(math.hypot(dx, dy), 6.0 + 1e-6)

    def test_continuous_away_from_centre(self):
        # On paths that stay clear of the centre the pushed
        # point slides smoothly (measured max 1.8 px per
        # 1 px input step); the threshold is 5.
        for y in (110, 150):
            prev = _clear_rect_radial((100, y), RECT)
            for x in range(101, 201):
                cur = _clear_rect_radial((x, y), RECT)
                jump = ((cur[0] - prev[0]) ** 2
                        + (cur[1] - prev[1]) ** 2) ** 0.5
                self.assertLess(jump, 5.0,
                                f"y={y} x={x} {prev} -> {cur}")
                prev = cur

    def test_centreline_flip_is_documented(self):
        # Exactly ON the centreline the exit side flips at
        # the centre (the _clear_head precedent: radial
        # pushes are continuous except at the exact centre,
        # where the fallback fires). Real hand paths are
        # floats and never ride the exact centreline.
        x, y = _clear_rect_radial((149, 130), RECT)
        self.assertAlmostEqual((x, y), (94.0, 130.0))
        x, y = _clear_rect_radial((151, 130), RECT)
        self.assertAlmostEqual((x, y), (206.0, 130.0))

    def test_margin_band_pushes_out(self):
        # Inside the margin band but outside the rect: pushed
        # to the boundary + margin (== ~itself at the band edge).
        x, y = _clear_rect_radial((103, 130), RECT)
        self.assertAlmostEqual(x, 94.0)
        self.assertAlmostEqual(y, 130.0)


class TestClearWornBags(unittest.TestCase):
    def test_sequential_rects(self):
        rects = [RECT, (300.0, 100.0, 400.0, 160.0)]
        x, y = _clear_worn_bags((150, 130), rects)
        self.assertAlmostEqual((x, y), (150.0, 166.0))
        x, y = _clear_worn_bags((350, 130), rects)
        self.assertAlmostEqual((x, y), (350.0, 166.0))

    def test_no_rects_untouched(self):
        self.assertEqual(_clear_worn_bags((150, 130), []), (150.0, 130.0))


class TestKeyVisibleOverBag(unittest.TestCase):
    def test_shot11_key_never_inside_bag_rect(self):
        package, shot = _delivered_shot(11, job="req_db6a67ff9ca3")
        draws = []
        orig = pr._draw_prop

        def spy(d, x, y, *a, **k):
            if k.get("kind") in ("key", "bag"):
                draws.append((k.get("kind"), float(x), float(y),
                              k.get("w"), k.get("h")))
            return orig(d, x, y, *a, **k)

        with mock.patch.object(pr, "_draw_prop", spy):
            with tempfile.TemporaryDirectory() as tmp:
                _render_shot({"shot": shot, "package": package,
                              "out_dir": tmp, "still_only": False})
                frame48 = Path(tmp) / "shot_011" / "f0048.png"
                arr = np.asarray(
                    Image.open(frame48).convert("RGB")).astype(int)
        keys = [d for d in draws if d[0] == "key"]
        bags = [d for d in draws if d[0] == "bag"]
        self.assertEqual(len(keys), len(bags))
        self.assertGreater(len(keys), 50)
        for (__, kx, ky, _w, _h), (__, bx, by, bw, bh) in zip(
                keys, bags):
            # Drawn bag rect incl. the handle arc (same
            # geometry as the clearance rect).
            left, top = bx - bw / 2.0, by - bh / 2.0 - 6.0
            right, bottom = bx + bw / 2.0, by + bh / 2.0
            self.assertFalse(
                left <= kx <= right and top <= ky <= bottom,
                f"key centre ({kx}, {ky}) inside bag rect")
        # Delivered evidence: brass reads at f48 (R19: 0 px).
        brass = np.array([203, 160, 72])
        mask = (np.abs(arr - brass).sum(axis=2) < 40)
        self.assertGreater(int(mask.sum()), 100)


if __name__ == "__main__":
    unittest.main()
