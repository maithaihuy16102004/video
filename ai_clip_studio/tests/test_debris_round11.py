"""Round 11 (R11-4): strike debris. The burst streaks vanish
mid-flight; debris fragments fly ballistic arcs, land on the
floor, stick, and cool as glow dots for 44 frames. Same
determinism contract as the burst: a pure function of (element,
strike_index, age).
"""

import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.environment_v2 import (
    _DEBRIS_GROUND_Y, _DEBRIS_LIFETIME, _draw_sparks,
    debris_positions)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera

EL = {"center": (0.6, 0.95, -3.2), "size": (1.0, 1.0, 1.0),
      "extra": {"spark_seed": 20261112}}


class TestDebrisPositions(unittest.TestCase):
    def test_empty_outside_lifetime(self):
        for age in (-1, _DEBRIS_LIFETIME, 100):
            self.assertEqual(debris_positions(EL, age, 0), [])

    def test_count_and_determinism(self):
        a = debris_positions(EL, 10, 0)
        b = debris_positions(EL, 10, 0)
        self.assertEqual(len(a), 6)
        self.assertEqual(a, b)

    def test_strike_index_changes_pattern(self):
        a = debris_positions(EL, 10, 0)
        b = debris_positions(EL, 10, 1)
        self.assertNotEqual(a, b)

    def test_flies_then_lands_and_sticks(self):
        early = debris_positions(EL, 0, 0)
        self.assertTrue(all(not landed for _, _, landed in early))
        for age in (30, 43):
            late = debris_positions(EL, age, 0)
            self.assertTrue(all(landed for _, _, landed in late))
            for (pos, _, _), in ((p,) for p in late):
                self.assertAlmostEqual(pos[1], _DEBRIS_GROUND_Y)
        at30 = [pos for pos, _, _ in debris_positions(EL, 30, 0)]
        at43 = [pos for pos, _, _ in debris_positions(EL, 43, 0)]
        self.assertEqual(at30, at43)

    def test_arc_rises_then_falls(self):
        for i in range(6):
            y0 = debris_positions(EL, 0, 0)[i][0][1]
            y3 = debris_positions(EL, 3, 0)[i][0][1]
            y4 = debris_positions(EL, 4, 0)[i][0][1]
            y10 = debris_positions(EL, 10, 0)[i][0][1]
            self.assertGreater(y3, y0)
            self.assertLess(y10, y4)

    def test_landing_bounded(self):
        ox, _, oz = EL["center"]
        for pos, _, _ in debris_positions(EL, 30, 0):
            self.assertLess(abs(pos[0] - ox), 1.0)
            self.assertLess(abs(pos[2] - oz), 1.0)

    def test_cool_frac_spans_lifetime(self):
        self.assertEqual(debris_positions(EL, 0, 0)[0][1], 0.0)
        self.assertAlmostEqual(
            debris_positions(EL, 43, 0)[0][1], 43 / _DEBRIS_LIFETIME)


class TestDebrisDrawing(unittest.TestCase):
    CAM = PerspectiveCamera(position=(0.0, 2.0, 4.8),
                            target=(0.0, 1.2, -3.0), fov_deg=46.0,
                            aspect=16.0 / 9.0)

    def _render(self, extra):
        img = Image.new("RGB", (960, 540), (40, 36, 32))
        draw = ImageDraw.Draw(img)
        el = dict(EL, extra=dict(EL["extra"], **extra))
        _draw_sparks(img, draw, el, self.CAM, None, 960, 540,
                     spark_frame=0)
        return np.asarray(img).astype(float)

    def _diff(self, extra):
        # Pixel difference vs the debris-free render: the ambient
        # streaks are identical (same seed/frame), so the diff
        # isolates exactly what the debris drew (dots + glows).
        base = self._render({})
        return int((np.abs(self._render(extra) - base).sum(axis=2)
                    > 30).sum())

    def test_landed_debris_adds_warm_pixels(self):
        self.assertGreater(self._diff({"debris_age_frames": 25,
                                       "debris_strike_index": 0}),
                           300)

    def test_flying_debris_adds_warm_pixels(self):
        self.assertGreater(self._diff({"debris_age_frames": 5,
                                       "debris_strike_index": 0}),
                           100)

    def test_cooled_debris_fades(self):
        hot = self._diff({"debris_age_frames": 20,
                          "debris_strike_index": 0})
        cold = self._diff({"debris_age_frames": 43,
                           "debris_strike_index": 0})
        self.assertGreater(hot, cold)


if __name__ == "__main__":
    unittest.main()
