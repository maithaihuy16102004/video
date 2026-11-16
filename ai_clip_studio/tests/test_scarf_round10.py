"""Round 10 (R10-5 / tester R9-D3): the scarf band must wrap
the neck. The old axis-aligned bar at 1.08r left a hairline gap
under the chin, stayed horizontal when the head leaned, and
stuck out 0.62r on each side of a ~0.3r neck -- a hovering plank
in closeups. The band now centres at 0.98r, spans 0.40r each
way, and rotates perpendicular to the head->shoulder axis, so
both ends stay tucked under the chin at any lean.
"""

import math
import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import (
    draw_character_v4, make_character_instance)
from ai_clip_studio.animation.primitives import standing

SCARF = (242, 194, 48)


def _render(lean, view="front"):
    ch = make_character_instance("lustig", height=560)
    ch.scarf_color = "#F2C230"
    img = Image.new("RGB", (600, 700), (255, 255, 255))
    d = ImageDraw.Draw(img, "RGBA")
    standing(ch, 300, 620, facing=1)
    if lean:
        ch.set_pose(torso_lean=lean)
    joints = draw_character_v4(d, ch, expression="neutral",
                               view=view)
    arr = np.asarray(img).astype(int)
    dist = np.abs(arr - np.array(SCARF)).sum(axis=2)
    mask = dist < 30
    return ch, joints, mask, arr


def _ends_touch_disc(ch, joints, mask):
    """Both ends of the scarf (split by the neck axis) have
    pixels within 3px of the head disc -- no floating end."""
    hx, hy = joints["head"]
    sx, sy = joints["shoulder"]
    ax, ay = sx - hx, sy - hy
    al = math.hypot(ax, ay) or 1.0
    px, py = -ay / al, ax / al
    ys, xs = np.nonzero(mask)
    cx, cy = xs.mean(), ys.mean()
    ok = {1: False, -1: False}
    for x, y in zip(xs, ys):
        side = 1 if (x - cx) * px + (y - cy) * py >= 0 else -1
        if math.hypot(x - hx, y - hy) <= ch.head_r + 3:
            ok[side] = True
    return ok


class TestScarfWrapsNeck(unittest.TestCase):
    def test_upright_band_narrow_and_touching(self):
        ch, joints, mask, _arr = _render(0.0)
        ys, xs = np.nonzero(mask)
        self.assertGreater(len(xs), 50)
        # Not a plank: the old bar spanned 1.24r.
        self.assertLess(xs.max() - xs.min(), 0.95 * ch.head_r)
        ok = _ends_touch_disc(ch, joints, mask)
        self.assertTrue(ok[1], "right end floats")
        self.assertTrue(ok[-1], "left end floats")

    def test_leaned_band_tilts_and_stays_attached(self):
        # Profile: the lean tilts the head->shoulder axis, so
        # the band tilts with it (the round-10 behaviour).
        ch, joints, mask, _arr = _render(0.35, view="profile")
        ys, xs = np.nonzero(mask)
        self.assertGreater(len(xs), 50)
        ok = _ends_touch_disc(ch, joints, mask)
        self.assertTrue(ok[1], "right end floats under lean")
        self.assertTrue(ok[-1], "left end floats under lean")
        # The band tilts with the lean: its long axis (PCA)
        # rotates away from horizontal.
        pts = np.stack([xs - xs.mean(), ys - ys.mean()], axis=1)
        cov = np.cov(pts.T)
        _w, vec = np.linalg.eigh(cov)
        angle = abs(math.atan2(vec[1, 1], vec[0, 1]))
        self.assertGreater(angle, 0.12)

    def test_front_lean_band_stays_attached_and_level(self):
        # Round 19 (front-view lean): the drawn head/shoulder
        # re-centre on the hip, so the band stays level and
        # wrapped around the DRAWN neck. The returned joints
        # are the unprojected rig map -- the disc centre is
        # measured from the drawn face pixels instead.
        ch, _joints, mask, arr = _render(0.35, view="front")
        ys, xs = np.nonzero(mask)
        self.assertGreater(len(xs), 50)
        face = np.array([247, 243, 232])
        fmask = (np.abs(arr - face).sum(axis=2) < 40)
        fys, fxs = np.nonzero(fmask)
        hx, hy = fxs.mean(), fys.mean()
        for x, y in zip(xs, ys):
            self.assertLessEqual(math.hypot(x - hx, y - hy),
                                 ch.head_r + 30.0)
        # Both ends tuck under the chin: scarf pixels flank
        # the disc centre within the disc radius.
        self.assertLess(xs.min(), hx)
        self.assertGreater(xs.max(), hx)
        self.assertLess(xs.max() - xs.min(), 0.95 * ch.head_r)
        # Level: the band's long axis stays horizontal.
        pts = np.stack([xs - xs.mean(), ys - ys.mean()], axis=1)
        cov = np.cov(pts.T)
        _w, vec = np.linalg.eigh(cov)
        angle = abs(math.atan2(vec[1, 1], vec[0, 1]))
        self.assertLess(angle, 0.12)


if __name__ == "__main__":
    unittest.main()
