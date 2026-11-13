"""Stage 3 engine tests: dark daytime + depth overlap.

Brief tasks 2-3. Dark daytime: a day scene must render daylight
(sky-band luminance, no black rows at steep angles); flat ground
slabs must be classified as slabs (they cast no contact shadow).
Depth: foreground boxes must occlude characters, but flat ground
slabs must never swallow feet (they stay in the background layer).

Run: python3 -m unittest ai_clip_studio.tests.test_engine_stage3_dark_depth
from ~/workspace/agent/
"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.product_renderer import (
    CAM, H, W, build_scene_ex, split_foreground_boxes)
from ai_clip_studio.renderer25d import render as render_mod
from ai_clip_studio.renderer25d.scene import Box3D, Scene25D


def _render_day_scene():
    boxes, sky_top, sky_bottom, rainy, ground = build_scene_ex(
        "street", "Munich street, morning", "warm", "day")
    scene = Scene25D(boxes=boxes, characters=[], camera=CAM,
                     sky_top=sky_top, sky_bottom=sky_bottom,
                     ground_color=ground, ground_extent=30.0)
    return render_mod.render_frame(scene, W, H), sky_top


class TestDarkDaytime(unittest.TestCase):
    def test_day_street_sky_is_daylight(self):
        img, sky_top = _render_day_scene()
        arr = np.asarray(img).astype(float)
        band = arr[10:300, :, :]
        lum = band.mean(axis=2)
        # Measured 163.4 on the fixed renderer; the old (slab-shadow)
        # behaviour measured 38.6.
        self.assertGreater(lum.mean(), 100.0,
                           f"sky-band luminance {lum.mean():.1f}")
        # Top rows only: tall buildings intrude into the lower sky
        # band (their shaded side faces are legitimately dark).
        top = arr[10:70, :, :].mean(axis=2)
        self.assertLess(float((top < 30).mean()), 0.01)
        top_px = tuple(int(v) for v in arr[20, 960])
        self.assertTrue(all(abs(a - b) <= 12 for a, b in
                            zip(top_px, sky_top)),
                        f"top pixel {top_px} vs sky_top {sky_top}")

    def test_flat_ground_slab_classification(self):
        slab = Box3D(center=(0.0, 0.05, 1.0), size=(14.0, 0.1, 0.4),
                     color=(120, 110, 96), name="path_fg")
        self.assertTrue(slab.is_flat_ground_slab())
        crate = Box3D(center=(2.0, 0.4, 1.2), size=(0.9, 0.8, 0.9),
                      color=(140, 110, 70), name="crate_fg")
        self.assertFalse(crate.is_flat_ground_slab())

    def test_no_black_gap_rows_at_steep_angles(self):
        boxes, sky_top, sky_bottom, _rainy, ground = build_scene_ex(
            "street", "Munich street, morning", "warm", "day")
        for angle in ("low_angle", "high_angle", "birds_eye"):
            cam = viewpoint_for_shot(
                "medium", angle, subject_pos=(0.0, 1.2, 0.0))
            scene = Scene25D(boxes=boxes, characters=[], camera=cam,
                             sky_top=sky_top, sky_bottom=sky_bottom,
                             ground_color=ground, ground_extent=30.0)
            arr = np.asarray(render_mod.render_frame(scene, W, H)
                             ).astype(float)
            lum = arr.mean(axis=2)
            black_rows = [y for y in range(0, 650)
                          if float((lum[y] < 30).mean()) > 0.9]
            self.assertEqual(black_rows, [],
                             f"{angle}: black gap rows {black_rows[:5]}")


class TestDepthOverlap(unittest.TestCase):
    def test_split_keeps_slabs_in_background(self):
        slab = Box3D(center=(0.0, 0.05, 1.0), size=(14.0, 0.1, 0.4),
                     color=(120, 110, 96), name="path_fg")
        crate = Box3D(center=(2.0, 0.4, 1.2), size=(0.9, 0.8, 0.9),
                      color=(140, 110, 70), name="crate_fg")
        back = Box3D(center=(0.0, 1.5, -10.0), size=(3.0, 3.0, 1.0),
                     color=(100, 100, 100), name="facade")
        bg, fg = split_foreground_boxes([slab, crate, back])
        self.assertIn(slab, bg, "flat slab must not swallow feet")
        self.assertIn(back, bg)
        self.assertEqual(fg, [crate],
                         "only genuinely-in-front boxes occlude")

    def test_foreground_layer_has_no_slab_band_alpha(self):
        # The foreground layer (rendered over the characters) must
        # carry no pixels in the ground-slab band: slabs stay in the
        # background layer, so legs/feet are never covered by them.
        boxes, sky_top, sky_bottom, _rainy, ground = build_scene_ex(
            "street", "Munich street, morning", "warm", "day")
        bg, fg = split_foreground_boxes(boxes)
        self.assertTrue(bg and fg)
        scene = Scene25D(boxes=boxes, characters=[], camera=CAM,
                         sky_top=sky_top, sky_bottom=sky_bottom,
                         ground_color=ground, ground_extent=30.0)
        layer = render_mod.render_boxes_layer(scene, W, H, boxes=fg)
        alpha = np.asarray(layer)[:, :, 3]
        # Slab band: the ground strip where feet stand, centre
        # columns (away from the edge foreground boxes).
        band = alpha[880:920, 700:1200]
        self.assertEqual(int((band > 0).sum()), 0,
                         "foreground layer must not cover the slab band")


if __name__ == "__main__":
    unittest.main()
