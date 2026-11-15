"""Round 10 (R10-6): the glow lands on the floor. A radial halo
alone reads as a flat 2D sticker; the light pool -- a squashed
floor-plane ellipse centred on the ground line below the source,
wider and dimmer than the halo -- is what makes the glow read as
3D light. Unit pins on the painter; the rendered check lives on
shot #3 (forge EMIT) in the probe below.
"""

import unittest

import numpy as np
from PIL import Image

from ai_clip_studio.lighting import paint_energy_glow, paint_light_pool


def _record(radius=100.0, intensity=1.0):
    return {"prop_id": "p1", "intensity": intensity,
            "color": (255, 200, 80), "radius": radius,
            "source_position": (400.0, 300.0),
            "position_space": "pixels", "state": "IN_USE",
            "holder": "Linh"}


class TestLightPool(unittest.TestCase):
    def test_pool_is_a_floor_ellipse(self):
        img = Image.new("RGB", (800, 600), (40, 40, 40))
        paint_light_pool(img, _record(), ground_y=450.0)
        arr = np.asarray(img).astype(int)
        warm = (arr[:, :, 0] > 90) & (arr[:, :, 0] - arr[:, :, 2] > 40)
        ys, xs = np.nonzero(warm)
        self.assertGreater(len(xs), 1000)
        # Centred on the ground line, wider than tall.
        self.assertAlmostEqual(ys.mean(), 450.0, delta=15.0)
        self.assertAlmostEqual(xs.mean(), 400.0, delta=15.0)
        self.assertGreater((xs.max() - xs.min()),
                           2.0 * (ys.max() - ys.min()))
        # The pool reaches below the source (the floor), and its
        # top stays well above the source point.
        self.assertGreater(ys.max(), 450.0)
        self.assertLess(ys.min(), 450.0)

    def test_pool_dimmer_than_halo(self):
        halo = Image.new("RGB", (800, 600), (40, 40, 40))
        paint_energy_glow(halo, _record())
        pool = Image.new("RGB", (800, 600), (40, 40, 40))
        paint_light_pool(pool, _record(), ground_y=300.0)
        ha = np.asarray(halo).astype(int)
        pa = np.asarray(pool).astype(int)
        self.assertGreater(ha[300, 400, 0], pa[300, 400, 0])

    def test_zero_radius_paints_nothing(self):
        img = Image.new("RGB", (800, 600), (40, 40, 40))
        paint_light_pool(img, _record(radius=0.0), ground_y=450.0)
        arr = np.asarray(img)
        self.assertTrue((arr == 40).all())

    def test_world_space_raises(self):
        rec = _record()
        rec["source_position"] = (0.5, 1.2, -3.0)
        rec["position_space"] = "world"
        with self.assertRaises(ValueError):
            paint_light_pool(Image.new("RGB", (800, 600)),
                             rec, ground_y=450.0)


if __name__ == "__main__":
    unittest.main()
