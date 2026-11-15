"""Round-7 brow-slant tests.

The F4 forehead clamp must preserve the brow slant when an
upward gaze lifts both brow ends together: the old per-end
clamp pinned both ends to the hairline and flattened raised
brows to 0.0 deg (tester R6: child brow 0.0 deg in #3/#7/#12,
present in #15). The brow is measured from rendered pixels
(the same way the tester measures it).
"""

import math
import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import (
    draw_character_v4)
from ai_clip_studio.animation.rig import Stickman


def _brow_angle(expression, gaze):
    ch = Stickman(height=700, name="test_char", hat=None,
                  moustache=False)
    ch.suit = "#172033"
    ch.skin = "#F0C8A0"
    ch.set_pose(root_x=960, root_y=900 - 300, facing=1,
                thigh_l=0.1, thigh_r=-0.1, knee_l=0.15,
                knee_r=0.15, arm_l=0.1, arm_r=0.1,
                elbow_l=0.2, elbow_r=0.2, bob=0.0,
                torso_lean=0.0, head_look=0.0)
    img = Image.new("RGBA", (1920, 1080), (255, 255, 255, 255))
    d = ImageDraw.Draw(img, "RGBA")
    joints = draw_character_v4(d, ch, expression=expression,
                               view="front", gaze=gaze)
    hx, hy = joints["head"]
    r = ch.head_r
    # Brow band: the left brow spans the left eye centre
    # (hx-0.315r) +/-0.11r; the band hugs it so the eye's top
    # edge and the head outline stay out of the fit. The angle
    # comes from the brow's TOP EDGE per column: with an upward
    # gaze the eye rises to nearly touch the brow, so a fit over
    # all dark pixels would swallow the eye and read flat.
    ex = hx - 0.315 * r
    x0, x1 = int(ex - 0.13 * r), int(ex + 0.13 * r)
    y0, y1 = int(hy - 0.60 * r), int(hy - 0.10 * r)
    arr = np.asarray(img)[y0:y1, x0:x1, :3].astype(int)
    dark = arr.sum(axis=2) < 200
    tops = []
    for x in range(dark.shape[1]):
        col = np.where(dark[:, x])[0]
        if len(col):
            tops.append((x, int(col.min())))
    med = float(np.median([t for _, t in tops]))
    edge = [(x, t) for x, t in tops if abs(t - med) <= 12]
    xs = np.array([e[0] for e in edge], dtype=float)
    ys = np.array([e[1] for e in edge], dtype=float)
    slope = float(np.polyfit(xs, ys, 1)[0])
    return math.degrees(math.atan(slope))


class TestBrowSlant(unittest.TestCase):
    def test_surprised_slant_survives_upward_gaze(self):
        level = _brow_angle("surprised", (0.0, 0.0))
        up = _brow_angle("surprised", (0.0, -0.10))
        self.assertGreater(abs(level), 5.0, level)
        self.assertGreater(abs(up), 5.0, up)
        self.assertAlmostEqual(level, up, delta=3.0)

    def test_neutral_stays_flat(self):
        angle = _brow_angle("neutral", (0.0, 0.0))
        self.assertAlmostEqual(angle, 0.0, delta=2.0)

    def test_angry_slants_hard(self):
        angle = _brow_angle("angry", (0.0, 0.0))
        self.assertGreater(abs(angle), 15.0, angle)


if __name__ == "__main__":
    unittest.main()
