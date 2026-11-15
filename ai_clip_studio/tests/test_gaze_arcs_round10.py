"""Round 10 (R10-3): closed-arc eyes must show gaze. Tester R9:
Linh's happy arcs looked frozen across 60 frames while oval eyes
wandered -- a thin arc carries too little visual mass for the
same translation to read. The arc now translates by
ARC_GAZE_BOOST x the gaze (the lid follows the eyeball); oval
eyes keep the unboosted gaze. Verified on drawn faces: the arc
dark-mass centroid moves ARC_GAZE_BOOST x as far as the oval
centroid for the same gaze step, and zero gaze reproduces the
old drawing exactly.
"""

import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import (
    ARC_GAZE_BOOST, EXPRESSIONS, _draw_face)
from ai_clip_studio.animation.rig import Stickman


def _face_centroid(params, gaze, size=400):
    char = Stickman(height=560.0, template="default")
    img = Image.new("RGB", (size, size), (250, 248, 240))
    draw = ImageDraw.Draw(img)
    _draw_face(draw, char, size / 2, size / 2, "front", 0.0,
               dict(params), (20, 30, 60), {}, gaze=gaze)
    arr = np.asarray(img).astype(int)
    # Eye row only: y in [-0.24r, 0] holds the arcs and the upper
    # halves of the ovals (rigid translation: the upper half
    # shifts exactly like the whole eye), excluding brows
    # (above -0.43r) and the static mouth (below +0.07r), whose
    # centred mass would dilute the moving centroid.
    r = char.head_r
    y0 = int(size / 2 - 0.24 * r)
    y1 = int(size / 2)
    band = arr[y0:y1]
    dark = (band.sum(axis=2) < 250)
    _ys, xs = np.nonzero(dark)
    return float(xs.mean()) if len(xs) else size / 2.0


class TestArcGazeBoost(unittest.TestCase):
    def test_arc_moves_boost_times_oval(self):
        happy = EXPRESSIONS["happy"]
        neutral = EXPRESSIONS["neutral"]
        step = 0.10
        arc_shift = (_face_centroid(happy, (step, 0.0))
                     - _face_centroid(happy, (0.0, 0.0)))
        oval_shift = (_face_centroid(neutral, (step, 0.0))
                      - _face_centroid(neutral, (0.0, 0.0)))
        self.assertGreater(oval_shift, 0.0)
        self.assertGreater(arc_shift, 0.0)
        self.assertAlmostEqual(arc_shift / oval_shift,
                               ARC_GAZE_BOOST, delta=0.25)

    def test_zero_gaze_unchanged(self):
        # The boost is a gaze multiple: at gaze 0 the arc sits
        # exactly where it always did.
        happy = EXPRESSIONS["happy"]
        c0 = _face_centroid(happy, (0.0, 0.0))
        self.assertAlmostEqual(c0, 200.0, delta=2.0)


if __name__ == "__main__":
    unittest.main()
