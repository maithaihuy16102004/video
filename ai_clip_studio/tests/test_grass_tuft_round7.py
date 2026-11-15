"""Round-7 grass-tuft tests.

The tuft must read as grass (five blades of varied height/lean,
not the 3-blade "v") and must draw only on grass-bearing ground
(packed_earth / forest_floor) -- never on cave rock, stone,
wood, sand, asphalt or mud.
"""

import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import (
    draw_character_v4, _GRASS_GROUND_KINDS)
from ai_clip_studio.animation.rig import Stickman

W, H = 1920, 1080


def _standing_char():
    ch = Stickman(height=560, name="test_char", hat=None,
                  moustache=False)
    ch.suit = "#172033"
    ch.skin = "#F0C8A0"
    ch.set_pose(root_x=960, root_y=920 - 241, facing=1,
                thigh_l=0.1, thigh_r=-0.1, knee_l=0.15,
                knee_r=0.15, arm_l=0.1, arm_r=0.1,
                elbow_l=0.2, elbow_r=0.2, bob=0.0,
                torso_lean=0.0, head_look=0.0)
    return ch


def _tuft_pixels(ground_kind):
    img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    d = ImageDraw.Draw(img, "RGBA")
    joints = draw_character_v4(
        d, _standing_char(), view="profile",
        ground_kind=ground_kind)
    ground_y = max(joints["foot_l"][1], joints["foot_r"][1])
    foot_lx = min(joints["foot_l"][0], joints["foot_r"][0])
    # The tuft root sits 0.045H left of the foot's drawn left
    # edge (foot joint x - 0.06H half foot width); the blades
    # fan +/-0.03H and rise up to 0.07H. The zone stays clear
    # of the foot itself (left edge at -0.06H).
    x0 = int(foot_lx - 0.145 * 560)
    x1 = int(foot_lx - 0.065 * 560)
    y0 = int(ground_y - 0.075 * 560)
    y1 = int(ground_y + 2)
    arr = np.asarray(img)[y0:y1, x0:x1, :3].astype(int)
    dark = (arr.sum(axis=2) < 200).sum()
    return int(dark)


class TestGrassTuft(unittest.TestCase):
    def test_tuft_draws_on_grass_ground(self):
        for kind in sorted(_GRASS_GROUND_KINDS):
            with self.subTest(kind=kind):
                self.assertGreater(_tuft_pixels(kind), 50, kind)

    def test_tuft_draws_by_default(self):
        # Standalone callers (no ground kind) keep the
        # reference look -- the previous drawing exactly.
        self.assertGreater(_tuft_pixels(None), 50)

    def test_no_tuft_on_stone_wood_sand_cave(self):
        for kind in ("cave_rock", "dark_stone", "pale_stone",
                     "cobblestone", "wood_floor", "sand",
                     "asphalt", "mud", "neutral"):
            with self.subTest(kind=kind):
                self.assertEqual(_tuft_pixels(kind), 0, kind)

    def test_tuft_is_wider_than_the_old_v(self):
        # Five blades fan +/-0.03H: the ink spans at least
        # 0.05H horizontally, not the old 3-blade 0.028H span.
        img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
        d = ImageDraw.Draw(img, "RGBA")
        joints = draw_character_v4(
            d, _standing_char(), view="profile",
            ground_kind="packed_earth")
        ground_y = max(joints["foot_l"][1], joints["foot_r"][1])
        foot_lx = min(joints["foot_l"][0], joints["foot_r"][0])
        x0 = int(foot_lx - 0.145 * 560)
        x1 = int(foot_lx - 0.065 * 560)
        y0 = int(ground_y - 0.075 * 560)
        arr = np.asarray(img)[y0:int(ground_y) + 2, x0:x1, :3]
        dark = (arr.sum(axis=2) < 200)
        xs = np.where(dark.any(axis=0))[0]
        self.assertGreater(xs.max() - xs.min(), 0.05 * 560)


if __name__ == "__main__":
    unittest.main()
