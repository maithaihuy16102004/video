"""Round 19 animation gap 2: front-view lean.

The rig's x-axis is the sagittal plane, so in front view a
forward lean must not slide the upper body sideways: the
head drops and the torso compresses vertically. Profile /
three-quarter / back drawings keep the exact previous
geometry (the lean's x-shift stays in those views).
"""
import unittest

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from ai_clip_studio.animation.character_art import (
    STYLE_LOCK,
    draw_character_v4,
)
from ai_clip_studio.animation.rig import Stickman

FACE = np.array([247, 243, 232])


def _render(view, lean):
    img = Image.new("RGB", (500, 700), (120, 130, 150))
    draw = ImageDraw.Draw(img, "RGBA")
    char = Stickman(height=560)
    char.set_pose(root_x=250, root_y=560, torso_lean=lean)
    draw_character_v4(draw, char, view=view)
    return np.asarray(img).astype(int)


def _disc_centre(arr):
    mask = (np.abs(arr - FACE).sum(axis=2) < 40)
    lab, n = ndi.label(mask)
    best = None
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        if len(xs) < 2000:
            continue
        if best is None or len(xs) > best[0]:
            best = (len(xs), xs.mean(), ys.mean())
    return best[1], best[2]


class TestFrontViewLean(unittest.TestCase):
    def test_front_lean_stays_centred_and_drops(self):
        cx0, cy0 = _disc_centre(_render("front", 0.0))
        cx1, cy1 = _disc_centre(_render("front", 0.40))
        self.assertAlmostEqual(cx0, 250.0, delta=3.0)
        self.assertAlmostEqual(cx1, 250.0, delta=3.0)
        # The head drops: cos(0.40) foreshortening over the
        # spine + neck + head stack (~18 px at H=560).
        self.assertGreater(cy1 - cy0, 10.0)

    def test_profile_lean_shift_unchanged(self):
        cx0, _ = _disc_centre(_render("profile", 0.0))
        cx1, _ = _disc_centre(_render("profile", 0.40))
        # Relative shift only: the profile face-fill centroid
        # sits off the hip axis by the face/hat geometry.
        self.assertGreater(cx1 - cx0, 60.0)

    def test_three_quarter_lean_shift_unchanged(self):
        cx0, _ = _disc_centre(_render("three_quarter", 0.0))
        cx1, _ = _disc_centre(_render("three_quarter", 0.40))
        self.assertGreater(cx1 - cx0, 40.0)

    def test_back_lean_shift_unchanged(self):
        cx0, _ = _disc_centre(_render("back", 0.0))
        cx1, _ = _disc_centre(_render("back", 0.40))
        self.assertGreater(cx1 - cx0, 60.0)

    def test_head_ratio_preserved_in_front_lean(self):
        # The face-fill mask measures the INNER diameter:
        # 2*head_r - 2*outline_width. The invariant is that
        # the lean changes neither the size nor the ratio.
        from ai_clip_studio.animation.character_art import (
            outline_width,
        )
        char = Stickman(height=560)
        expected = 2 * char.head_r - 2 * outline_width(char)
        for lean in (0.0, 0.40):
            arr = _render("front", lean)
            mask = (np.abs(arr - FACE).sum(axis=2) < 40)
            lab, n = ndi.label(mask)
            best = None
            for k in range(1, n + 1):
                ys, xs = np.nonzero(lab == k)
                if len(xs) < 2000:
                    continue
                if best is None or len(xs) > best[0]:
                    best = (len(xs), xs, ys)
            _, xs, _ = best
            self.assertAlmostEqual(xs.max() - xs.min(), expected,
                                   delta=4.0)


if __name__ == "__main__":
    unittest.main()
