"""Round 11 (R11-2): surface richness toward photographic. The R10
tester verdict: walls/floors read as flat painted fills with
repetitive patterns at full-frame distance. These tests pin the
large-scale tonal structure the texture painters and the hill
blob now carry: brick course weathering, plaster light falloff,
grass row striping, rock facet contrast, and shaded distant hills.
"""

import json
import math
import random
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.environment_v2 import (
    _draw_hill_blob, build_environment, render_environment)
from ai_clip_studio.paint_textures import (
    paint_brick, paint_grass, paint_plaster, paint_rock, paint_stone)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera

AGENT = Path(__file__).resolve().parents[2]
JOB = AGENT / "jobs" / "req_f28d511157dc"


def _lum(img):
    return np.asarray(img.convert("RGB")).astype(float).mean(axis=2)


class TestBrickWeathering(unittest.TestCase):
    def test_row_bands_vary(self):
        lum = _lum(paint_brick(3.0, 2.8, (170, 80, 55), 11))
        h = lum.shape[0]
        n_rows = int(2.8 / 0.065)
        bh = h / n_rows
        means = [lum[int(i * bh):int((i + 1) * bh)].mean()
                 for i in range(n_rows)]
        self.assertGreater(float(np.std(means)), 4.0)

    def test_mean_stays_near_base(self):
        img = paint_brick(3.0, 2.8, (170, 80, 55), 11)
        mean = np.asarray(img).reshape(-1, 3).mean(axis=0)
        for i, base in enumerate((170, 80, 55)):
            self.assertLess(abs(mean[i] - base), 35)

    def test_deterministic(self):
        a = paint_brick(3.0, 2.8, (170, 80, 55), 11)
        b = paint_brick(3.0, 2.8, (170, 80, 55), 11)
        self.assertEqual(a.tobytes(), b.tobytes())


class TestPlasterFalloff(unittest.TestCase):
    def test_top_brighter_than_lower_wall(self):
        lum = _lum(paint_plaster(3.0, 2.8, (210, 190, 160), 11))
        h = lum.shape[0]
        top = lum[:max(1, int(h * 0.05))].mean()
        lower = lum[int(h * 0.60):int(h * 0.75)].mean()
        self.assertGreater(float(top - lower), 4.0)

    def test_mean_stays_near_base(self):
        img = paint_plaster(3.0, 2.8, (210, 190, 160), 11)
        mean = np.asarray(img).reshape(-1, 3).mean(axis=0)
        for i, base in enumerate((210, 190, 160)):
            self.assertLess(abs(mean[i] - base), 35)


class TestGrassRows(unittest.TestCase):
    def test_alternating_bands(self):
        lum = _lum(paint_grass(3.0, 3.0, (90, 130, 60), 11))
        h = lum.shape[0]
        band_h = max(8, h // 12)
        n = h // band_h
        even = [lum[i * band_h:(i + 1) * band_h].mean()
                for i in range(0, n, 2)]
        odd = [lum[i * band_h:(i + 1) * band_h].mean()
               for i in range(1, n, 2)]
        # Round 11: > 2.5. Round 13: stronger modulation, 8.2
        # measured -- pin below it with margin.
        self.assertGreater(float(np.mean(even) - np.mean(odd)), 5.0)

    def test_tufts_planted_on_row_centres(self):
        # Round 13: row-centre strips carry the planted tufts,
        # so their local variance exceeds the between-row strips
        # (3.95 vs 2.88 measured).
        lum = _lum(paint_grass(3.0, 3.0, (90, 130, 60), 11))
        h = lum.shape[0]
        band_h = max(8, h // 12)
        centres = [lum[b * band_h + band_h // 2 - 2:
                       b * band_h + band_h // 2 + 3].std()
                   for b in range(1, h // band_h, 2)]
        betweens = [lum[b * band_h + band_h // 2 - 2:
                        b * band_h + band_h // 2 + 3].std()
                    for b in range(0, h // band_h, 2)]
        self.assertGreater(float(np.mean(centres)),
                           float(np.mean(betweens)) + 0.5)

    def test_deterministic(self):
        a = paint_grass(3.0, 3.0, (90, 130, 60), 11)
        b = paint_grass(3.0, 3.0, (90, 130, 60), 11)
        self.assertEqual(a.tobytes(), b.tobytes())


class TestRockContrast(unittest.TestCase):
    def test_facet_std(self):
        self.assertGreater(float(_lum(
            paint_rock(4.0, 3.0, (74, 66, 60), 7)).std()), 6.5)


class TestStoneWeathering(unittest.TestCase):
    def test_strip_bands_vary(self):
        lum = _lum(paint_stone(3.0, 2.8, (150, 145, 135), 11))
        h = lum.shape[0]
        strips = [lum[i * h // 8:(i + 1) * h // 8].mean()
                  for i in range(8)]
        self.assertGreater(float(np.std(strips)), 3.0)

    def test_deterministic(self):
        a = paint_stone(3.0, 2.8, (150, 145, 135), 11)
        b = paint_stone(3.0, 2.8, (150, 145, 135), 11)
        self.assertEqual(a.tobytes(), b.tobytes())


class TestHillBlob(unittest.TestCase):
    def _hill_image(self):
        img = Image.new("RGB", (400, 200), (140, 170, 210))
        draw = ImageDraw.Draw(img)
        _draw_hill_blob(draw, 200, 100, 150, 70, (96, 110, 88),
                        (50, 60, 45), random.Random(7))
        return np.asarray(img).astype(float)

    def test_cap_brighter_base_darker(self):
        arr = self._hill_image()
        cap = arr[45, 200].mean()      # near the ridge, lit
        mid = arr[100, 120].mean()     # mid-slope, left of the flank
        base = arr[165, 200].mean()    # near the base, shaded
        self.assertGreater(float(cap - mid), 8.0)
        self.assertGreater(float(mid - base), 5.0)

    def test_silhouette_contained(self):
        arr = self._hill_image()
        # Corners stay sky: no streak or slice escapes the ellipse.
        for (yy, xx) in ((5, 5), (5, 394), (194, 5), (194, 394)):
            self.assertEqual(tuple(arr[yy, xx]), (140.0, 170.0, 210.0))

    def test_hills_shaded_in_env_render(self):
        timeline = json.loads((JOB / "timeline.json").read_text(
            encoding="utf-8"))
        shot1 = timeline["shots"][1]
        env = build_environment(shot1["v1_location"],
                                time_of_day="morning",
                                style={"mood": "warm"})
        target = (0.0, 1.2, 0.0)
        el = math.radians(15.0)
        cam = PerspectiveCamera(
            position=(0.0, 1.2 + 7.5 * math.sin(el),
                      7.5 * math.cos(el)),
            target=target, fov_deg=46.0, aspect=16.0 / 9.0)
        img = render_environment(env, cam, (1920, 1080))
        arr = np.asarray(img.convert("RGB")).astype(float)
        hills = [e for e in env["elements"]
                 if e.get("kind") == "distant_hill"]
        # Round 10: 3 near hills. Round 12: + 4 far ridge hills
        # (sky_ridge_), same painter, deeper haze.
        self.assertEqual(len(hills), 7)
        self.assertEqual(sum(1 for e in hills
                             if e["id"].startswith("sky_hill_")), 3)
        self.assertEqual(sum(1 for e in hills
                             if e["id"].startswith("sky_ridge_")), 4)
        # The gradient is a property of the hill painter, not of
        # visibility: round-12 skyline silhouettes legitimately
        # occlude one near hill's cap point in the full render.
        # Sample each hill in isolation (all other elements
        # excluded) so occlusion cannot fake a flat gradient.
        all_ids = {e["id"] for e in env["elements"]}
        for hill in hills:
            solo = np.asarray(render_environment(
                env, cam, (1920, 1080),
                exclude_ids=all_ids - {hill["id"]}).convert(
                "RGB")).astype(float)
            x, y, scale, vis = cam.project(hill["center"], 1920, 1080)
            self.assertTrue(vis)
            ry = hill["size"][1] / 2 * scale
            cx, cy = int(x), int(y)
            if (hill.get("extra") or {}).get("ridge"):
                # Round 14: the peaked ridge painter is two-tone
                # (bright cap, darker base), not a dome gradient,
                # and the centre column may sit in a valley -- a
                # cap sample at -0.7ry can land on sky. Sample
                # inside the silhouette on both sides of the cap
                # boundary instead: -0.5ry is always under the
                # ridgeline (valleys stay >= 0.55ry) and +0.5ry
                # is always base tone.
                cap = solo[max(0, cy - int(0.5 * ry)), cx].mean()
                mid = solo[cy + int(0.5 * ry), cx].mean()
            else:
                cap = solo[max(0, cy - int(0.7 * ry)), cx].mean()
                mid = solo[cy, cx].mean()
            self.assertGreater(float(cap - mid), 3.0)


if __name__ == "__main__":
    unittest.main()
