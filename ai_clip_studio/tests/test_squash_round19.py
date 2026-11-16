"""Round 19 animation gap 4: squash/stretch.

A ``squash`` pose channel projected in drawn space (heights
above the ground line scale by (1 - sq), widths by (1 + 0.6*sq)
around the hip); the head stays a rigid circle. Default 0 is
the exact previous drawing. First consumer: hammer_strike
(anticipation stretch, impact squash, overshoot, settle).
"""
import math
import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import draw_character_v4
from ai_clip_studio.animation.primitives import (
    HAMMER_CYCLE_STRIKE_U,
    _HAMMER_SQUASH,
    hammer_strike,
)
from ai_clip_studio.animation.rig import Stickman


def _render(squash):
    img = Image.new("RGB", (500, 800), (120, 130, 150))
    draw = ImageDraw.Draw(img, "RGBA")
    char = Stickman(height=560)
    # A standing split: the feet sit apart, so the width
    # factor has spread to scale (the FK default stacks both
    # feet under the hip, where the factor is invisible).
    char.set_pose(root_x=250, root_y=560, squash=squash,
                  thigh_l=0.25, thigh_r=-0.25)
    draw_character_v4(draw, char, view="profile")
    return np.asarray(img).astype(int)


def _ink_bbox(arr):
    dark = (arr.sum(axis=2) < 300)
    ys, xs = np.nonzero(dark)
    return xs.min(), xs.max(), ys.min(), ys.max()


def _foot_span(arr):
    # Dark-pixel x-span in the bottom 15 rows (the feet):
    # projected points, so the width factor moves them.
    dark = (arr.sum(axis=2) < 300)
    ys, _ = np.nonzero(dark)
    ground = ys.max()
    band = dark[ground - 15:ground + 1, :]
    _, xs = np.nonzero(band)
    return xs.max() - xs.min()


class TestSquashProjection(unittest.TestCase):
    def test_squash_compresses_vertically_and_widens(self):
        _, _, y0, y1 = _ink_bbox(_render(0.0))
        _, _, sy0, sy1 = _ink_bbox(_render(0.08))
        h0, h1 = y1 - y0, sy1 - sy0
        # Feet stay planted: the bottom edge does not move.
        self.assertEqual(y1, sy1)
        # Height compresses by ~8% (the head rides down; the
        # rigid head disc keeps its own diameter, so the
        # total-height ratio is slightly above 0.92).
        self.assertLess(h1, h0)
        self.assertGreater(h1 / h0, 0.88)
        # The body widens: measured at sq=0.30, where the
        # 18% width factor clears pixel noise (the projection
        # is linear in sq; the torso polygon's own width is
        # drawn from the projected spine, so the foot span --
        # projected points -- carries the width term).
        self.assertGreater(_foot_span(_render(0.30)),
                           _foot_span(_render(0.0)))

    def test_stretch_extends_and_narrows(self):
        _, _, y0, y1 = _ink_bbox(_render(0.0))
        _, _, sy0, sy1 = _ink_bbox(_render(-0.08))
        self.assertEqual(y1, sy1)
        self.assertGreater(sy1 - sy0, y1 - y0)
        self.assertLess(_foot_span(_render(-0.30)),
                        _foot_span(_render(0.0)))

    def test_head_disc_diameter_unchanged(self):
        face = np.array([247, 243, 232])
        diams = []
        for sq in (0.0, 0.08, -0.08):
            arr = _render(sq)
            mask = (np.abs(arr - face).sum(axis=2) < 40)
            ys, xs = np.nonzero(mask)
            # The face disc is the topmost large face region.
            top = ys.min()
            sel = xs[ys < top + 200]
            diams.append(sel.max() - sel.min())
        self.assertEqual(diams[0], diams[1])
        self.assertEqual(diams[0], diams[2])


class TestHammerSquashEnvelope(unittest.TestCase):
    def test_envelope_shape_and_continuity(self):
        char = Stickman(height=560)
        char.set_pose(root_x=250, root_y=560)
        fn = hammer_strike(char, (350, 500), 0.9, cycles=1)
        samples = []
        for i in range(23):
            fn(i / 24.0)
            samples.append(char.pose["squash"])
        # Raise/hold: rigid.
        self.assertTrue(all(v == 0.0 for v in samples[:10]))
        # Downswing: anticipation stretch (negative).
        self.assertLess(min(samples[10:14]), 0.0)
        # Contact is at u=0.60 -> t=0.54 -> sample 13; the
        # squash peaks just after contact.
        peak = max(samples)
        self.assertAlmostEqual(peak, _HAMMER_SQUASH, delta=0.01)
        peak_i = samples.index(peak)
        self.assertIn(peak_i, (14, 15, 16))
        # Overshoot stretch late in the recover.
        self.assertLess(min(samples[18:]), 0.0)
        # Settles to zero at the cycle end.
        self.assertAlmostEqual(samples[-1], 0.0, delta=0.01)
        # Continuous: no single-frame jumps to full squash.
        # The impact rise is intentionally fast (~2 frames),
        # so the bound is the rise slope, not zero.
        for a, b in zip(samples, samples[1:]):
            self.assertLess(abs(b - a), 0.06)


if __name__ == "__main__":
    unittest.main()
