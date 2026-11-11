"""Unit tests for ai_clip_studio.animation.character_art (stdlib unittest).

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/video-16x9-v2/
"""
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.animation.character_art import (
    draw_character_v2, PALETTE_V51, MOODS,
)

W, H = 1920, 1080


def _standing_char():
    ch = Stickman(height=560, name="test_char", hat=None, moustache=False)
    ch.suit = "#172033"
    ch.skin = "#F0C8A0"
    ch.set_pose(root_x=960, root_y=920 - 241, facing=1,
                thigh_l=0.1, thigh_r=-0.1, knee_l=0.15, knee_r=0.15,
                arm_l=0.1, arm_r=0.1, elbow_l=0.2, elbow_r=0.2,
                bob=0.0, torso_lean=0.0, head_look=0.0)
    return ch


def _render(mood):
    img = Image.new("RGBA", (W, H), (15, 30, 51, 255))
    d = ImageDraw.Draw(img, "RGBA")
    joints = draw_character_v2(d, _standing_char(), mood=mood)
    return img, joints


class TestCharacterArt(unittest.TestCase):
    def test_returns_joint_map(self):
        _, joints = _render("neutral")
        for key in ("hip", "shoulder", "neck", "head",
                    "knee_l", "knee_r", "foot_l", "foot_r",
                    "elbow_l", "elbow_r", "hand_l", "hand_r"):
            self.assertIn(key, joints)

    def test_head_ratio_is_v4_measured(self):
        # v4: head ratio is MEASURED from the reference stickman
        # (0.3388), not the V51 standard 0.146.
        ch = _standing_char()
        self.assertAlmostEqual(ch.head_r, 0.34 * ch.H / 2, places=3)

    def test_moods_are_declared(self):
        for m in ("neutral", "worried", "smile", "speak", "relief"):
            self.assertIn(m, MOODS)

    def test_four_moods_differ_clearly_in_pixels(self):
        """Head region must differ between moods -- the expression is
        really drawn, not a single arc swapped cosmetically."""
        imgs = {}
        for mood in ("neutral", "worried", "smile", "speak", "relief"):
            img, joints = _render(mood)
            imgs[mood] = np.asarray(img, dtype=np.float32)
            # head region around the joint, generous box
            hx, hy = joints["head"]
            self.assertTrue(0 < hx < W and 0 < hy < H)
        # crop the head box from the neutral render to locate it
        _, joints = _render("neutral")
        hx, hy = joints["head"]
        r = int(_standing_char().head_r)
        box = (slice(max(0, int(hy - r - 30)), int(hy + r + 30)),
               slice(max(0, int(hx - r - 30)), int(hx + r + 30)))
        moods = ["neutral", "worried", "smile", "speak", "relief"]
        for i, m1 in enumerate(moods):
            for m2 in moods[i + 1:]:
                diff = float(np.mean(np.abs(imgs[m1][box] - imgs[m2][box])))
                # v4: the head is ~2.3x bigger (r 95 vs 41), so the same
                # mouth/eye change dilutes to a smaller mean over the
                # generous head box. 0.2 still means a clearly visible
                # difference (identical renders score 0.0).
                self.assertGreater(
                    diff, 0.2,
                    f"moods {m1} vs {m2} differ by only {diff:.3f} "
                    "in the head region")

    def test_torso_is_a_structured_block_not_a_line(self):
        """The jacket polygon must fill the spine area with suit colour
        (the old renderer only drew an 18px line + a 6px shirt line)."""
        img, joints = _render("neutral")
        arr = np.asarray(img)
        sh, hip = joints["shoulder"], joints["hip"]
        cx, cy = int((sh[0] + hip[0]) / 2), int((sh[1] + hip[1]) / 2)
        # sample a small patch around the torso centre: mostly suit
        patch = arr[cy - 10:cy + 10, cx - 30:cx + 30].reshape(-1, 4)[:, :3]
        suit = np.array([0x17, 0x20, 0x33])
        near_suit = np.mean(np.all(np.abs(patch.astype(int) - suit) < 30,
                                   axis=1))
        self.assertGreater(near_suit, 0.4,
                           "torso centre is not mostly jacket colour")
        # ...and the shirt V / buttons add non-suit pixels nearby
        cream = np.array([0xF3, 0xF0, 0xE8])
        near_cream = np.mean(np.all(np.abs(patch.astype(int) - cream) < 30,
                                    axis=1))
        self.assertGreater(near_cream, 0.01,
                           "no shirt/inner layer visible in the torso")

    def test_ground_shadow_present(self):
        img, joints = _render("neutral")
        arr = np.asarray(img, dtype=np.float32)
        feet_y = max(joints["foot_l"][1], joints["foot_r"][1])
        feet_x = int((joints["foot_l"][0] + joints["foot_r"][0]) / 2)
        # shadow ellipse sits just under the feet: darker than the
        # plain background (15,30,51) in that row
        row = arr[int(feet_y) + 2, feet_x - 100:feet_x + 100, :3]
        self.assertLess(float(np.mean(row)), 40.0)

    def test_palette_v51_colours_present(self):
        for key in ("yellow", "red", "cream", "dark", "green"):
            self.assertIn(key, PALETTE_V51)
        self.assertEqual(PALETTE_V51["yellow"], "#FFD34E")
        self.assertEqual(PALETTE_V51["red"], "#FF6B5E")
        self.assertEqual(PALETTE_V51["cream"], "#F3F0E8")
        self.assertEqual(PALETTE_V51["dark"], "#172033")
        self.assertEqual(PALETTE_V51["green"], "#47BD75")

    def test_unknown_mood_falls_back_to_neutral(self):
        img_a, _ = _render("not_a_mood")
        img_b, _ = _render("neutral")
        diff = float(np.mean(np.abs(
            np.asarray(img_a, dtype=np.float32)
            - np.asarray(img_b, dtype=np.float32))))
        self.assertEqual(diff, 0.0)

    def test_hat_none_draws_no_bowler(self):
        # The Eiffel rig uses hat="none" for the dealer; the string
        # "none" is truthy, so it must be treated as no hat, otherwise
        # every character gets a bowler.
        img, joints = _render("neutral")
        ch = _standing_char()
        ch.hat = "none"
        img_none = Image.new("RGBA", (W, H), (15, 30, 51, 255))
        draw_character_v2(ImageDraw.Draw(img_none, "RGBA"), ch,
                          mood="neutral")
        ch2 = _standing_char()
        ch2.hat = "bowler"
        img_bowler = Image.new("RGBA", (W, H), (15, 30, 51, 255))
        draw_character_v2(ImageDraw.Draw(img_bowler, "RGBA"), ch2,
                          mood="neutral")
        a = np.asarray(img_none, dtype=np.float32)
        b = np.asarray(img_bowler, dtype=np.float32)
        self.assertEqual(
            float(np.mean(np.abs(a - np.asarray(img, dtype=np.float32)))),
            0.0)
        self.assertGreater(float(np.mean(np.abs(b - a))), 0.0)


if __name__ == "__main__":
    unittest.main()
