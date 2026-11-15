"""Round 13 (R13-4): the gaze arcs case. The tester found no
hold signature on Linh's #14 happy arcs by two pixel methods
while the ovals demonstrated dwell (R11-D1 narrowed to the
arcs): a symmetric arc translated by a few pixels looks
identical to the unshifted one. The arc is now a sheared
polyline -- its apex moves with the gaze relative to its ends,
so the shape leans toward the look direction. Pinned on drawn
faces: apex-vs-ends differential, zero at gaze 0, ~8.5 px at
gaze 0.12.
"""

import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import (
    EXPRESSIONS, _draw_face)
from ai_clip_studio.animation.rig import Stickman


def _apex_ends(gaze, size=400):
    char = Stickman(height=560.0, template="default")
    img = Image.new("RGB", (size, size), (250, 248, 240))
    draw = ImageDraw.Draw(img)
    _draw_face(draw, char, size / 2, size / 2, "front", 0.0,
               dict(EXPRESSIONS["happy"]), (20, 30, 60), {},
               gaze=gaze)
    arr = np.asarray(img).astype(int)
    r = char.head_r
    # Right eye only (x > centre): apex = topmost dark row's
    # x-centre, ends = bottom row's x-centre, in the eye band.
    band = arr[int(size / 2 - 0.30 * r):size // 2, size // 2:]
    dark = band.sum(axis=2) < 250
    rows = np.nonzero(dark.any(axis=1))[0]
    apex_x = float(np.nonzero(dark[rows[0]])[0].mean())
    ends_x = float(np.nonzero(dark[rows[-1]])[0].mean())
    return apex_x, ends_x


class TestArcShear(unittest.TestCase):
    def test_zero_gaze_symmetric(self):
        apex, ends = _apex_ends((0.0, 0.0))
        self.assertAlmostEqual(apex, ends, delta=1.0)

    def test_gaze_leans_apex_past_ends(self):
        apex, ends = _apex_ends((0.12, 0.0))
        # Measured 8.5 px; pin below it with margin.
        self.assertGreater(apex - ends, 5.0)

    def test_negative_gaze_leans_other_way(self):
        apex, ends = _apex_ends((-0.12, 0.0))
        self.assertLess(apex - ends, -5.0)


if __name__ == "__main__":
    unittest.main()
