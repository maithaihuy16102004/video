"""RicksClips loop round 1 -- face: always-on thick brows, toothbrush
moustache geometry, one-eye trait wiring (script -> renderer), and the
curved back-of-head hairline.

Fixtures use unseen names; no engine branch may depend on a story or a
character name. The Zeus pin asserts the real Cyclops fix end to end.
"""
from __future__ import annotations

import os
import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import (
    STYLE_LOCK,
    draw_character_v4,
    make_character,
)
from ai_clip_studio.animation.primitives import standing
from ai_clip_studio.product_renderer import map_character
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.trait_derivation import (
    derive_render_traits,
    validate_trait_blocks,
)

INK = np.array((0x17, 0x20, 0x33))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def _traits(name="", role="", appearance="", costume="", traits=(),
            voice="", fields=None):
    return derive_render_traits(
        name, role, appearance, costume, list(traits), voice,
        fields=fields, height_px=540)


def _script(char_blocks, body, primary="CHAR_TWO"):
    header = [
        "STUDIO SCRIPT V1",
        "PROJECT",
        "STORYTELLING_MODE: FIRST_PERSON_ROLEPLAY",
        f"PRIMARY_CHARACTER: {primary}",
        "EXTERNAL_NARRATOR: NONE",
    ]
    header += char_blocks
    header += ["", "SCENE: SC01", "TITLE: Canh gac"]
    return "\n".join(header) + "\n" + body


def _render_face(char, expression="neutral", view="front"):
    img = Image.new("RGB", (1200, 1000), (245, 242, 235))
    standing(char, 600, 900, facing=1)
    joints = draw_character_v4(
        ImageDraw.Draw(img, "RGBA"), char,
        expression=expression, view=view)
    return img, joints


def _ink_mask(img):
    arr = np.asarray(img).astype(int)
    return np.all(np.abs(arr[:, :, :3] - INK) < 12, axis=2)


class TestEyeCountDerivation(unittest.TestCase):
    def test_explicit_eyes_field_one_eye(self):
        self.assertEqual(
            _traits(fields={"EYES": "một mắt"})["eye_count"], 1)
        self.assertEqual(
            _traits(fields={"EYES": "one eye"})["eye_count"], 1)

    def test_explicit_eyes_field_wins_over_scan(self):
        # EYES says nothing about one eye: two eyes, even though the
        # name would match the scan (the Amalthea shape).
        self.assertEqual(
            _traits(name="Cyclopes",
                    fields={"EYES": "Large expressive eyes"})["eye_count"],
            2)

    def test_species_word_cyclops_is_one_eyed(self):
        self.assertEqual(_traits(name="Cyclopes")["eye_count"], 1)
        self.assertEqual(
            _traits(role="a cyclops blacksmith")["eye_count"], 1)

    def test_scan_phrases(self):
        self.assertEqual(
            _traits(appearance="người khổng lồ một mắt")["eye_count"], 1)
        self.assertEqual(
            _traits(appearance="mot mat")["eye_count"], 1)
        self.assertEqual(
            _traits(appearance="độc nhãn")["eye_count"], 1)
        self.assertEqual(
            _traits(appearance="single eye in the middle")["eye_count"], 1)

    def test_negatives_stay_two_eyed(self):
        self.assertEqual(_traits(appearance="mắt to tròn")["eye_count"], 2)
        self.assertEqual(
            _traits(appearance="hai mắt sáng")["eye_count"], 2)
        self.assertEqual(_traits(name="Zeus", role="thần")["eye_count"], 2)
        self.assertEqual(_traits()["eye_count"], 2)

    def test_validator_accepts_one_or_two_only(self):
        blocks, dropped = validate_trait_blocks({"characters": [{
            "name": "A", "identity_id": "A",
            "render_traits": {"template": "male", "eye_count": 1}}]})
        self.assertEqual(
            blocks["characters"][0]["render_traits"]["eye_count"], 1)
        self.assertEqual(dropped, [])
        blocks, dropped = validate_trait_blocks({"characters": [{
            "name": "B", "identity_id": "B",
            "render_traits": {"template": "male", "eye_count": 3}}]})
        self.assertNotIn(
            "eye_count", blocks["characters"][0]["render_traits"])
        self.assertTrue(any("eye_count" in d for d in dropped))


class TestEyeCountWiring(unittest.TestCase):
    def test_adapter_carries_eye_count(self):
        text = _script(
            ["CHARACTER: CHAR_ONE", "NAME: Mot", "EYES: một mắt",
             "ROLE: Người gác đền",
             "CHARACTER: CHAR_CYC", "NAME: Cyclopes",
             "ROLE: Thợ rèn khổng lồ",
             "CHARACTER: CHAR_TWO", "NAME: Hai", "ROLE: Người dân",
             "EYES: Large expressive eyes"],
            "SHOT: SH01\nCAMERA: medium\n"
            "NARRATION:\nSPEAKER: CHAR_TWO\nLINE_ID: T_01\n"
            "TEXT: “Tôi đã tới.”\n")
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, doc.validation_errors)
        package = adapt_document(doc)
        by_name = {c["name"]: c for c in package["characters"]}
        self.assertEqual(by_name["Mot"]["eye_count"], 1)
        self.assertEqual(by_name["Cyclopes"]["eye_count"], 1)
        self.assertEqual(by_name["Hai"]["eye_count"], 2)

    def test_map_character_passes_eye_count(self):
        one = map_character(
            {"name": "X", "template": "male", "eye_count": 1}, 0)
        self.assertEqual(one.eye_count, 1)
        two = map_character({"name": "Y", "template": "male"}, 1)
        self.assertEqual(two.eye_count, 2)
        with self.assertRaises(ValueError):
            map_character(
                {"name": "Z", "template": "male", "eye_count": 3}, 2)

    def test_zeus_cyclops_is_one_eyed(self):
        path = os.path.join(
            ROOT, "examples", "zeus_ep01_fall_of_cronus.studio.md")
        with open(path, encoding="utf-8") as handle:
            doc = parse_studio_script_v1(handle.read())
        package = adapt_document(doc)
        by_id = {c["id"]: c for c in package["characters"]}
        self.assertEqual(by_id["CHAR_CYCLOPS"]["eye_count"], 1)
        for cid, char in by_id.items():
            if cid != "CHAR_CYCLOPS":
                self.assertEqual(char["eye_count"], 2, cid)


class TestBrowsAlwaysDrawn(unittest.TestCase):
    def test_neutral_brows_are_thick_and_present(self):
        char = make_character("male", name="T", height=774)
        img, joints = _render_face(char, "neutral", "front")
        hx, hy = joints["head"]
        r = char.head_r
        y0, y1 = int(hy - 0.60 * r), int(hy - 0.38 * r)
        x0, x1 = int(hx - 0.6 * r), int(hx + 0.6 * r)
        n = int(_ink_mask(img)[y0:y1, x0:x1].sum())
        # Two short thick brows: hundreds of px at H=774; a thin
        # v4 line or a missing brow is an order of magnitude less.
        self.assertGreater(n, 100, f"neutral brow ink too thin: {n}px")

    # The F4 clamp (no brow ink above the hairline) is already covered
    # for every expression/view/facing by
    # test_testc_phase2.test_no_brow_above_the_hairline; it is not
    # duplicated here.


class TestToothbrushMoustache(unittest.TestCase):
    def test_block_sits_on_the_mouth_line_wider_than_tall(self):
        char = make_character("male", name="T", height=774,
                              moustache_style="toothbrush")
        img, joints = _render_face(char, "neutral", "front")
        hx, hy = joints["head"]
        r = char.head_r
        my = hy + STYLE_LOCK["mouth_dy_frac_of_r"] * r
        # Band above the mouth line only (the mouth line itself is
        # excluded), restricted to the centre column: the eyes reach
        # into the band's top rows at the sides, the moustache is the
        # only ink at the centre.
        y0, y1 = int(my - 0.20 * r), int(my - 0.01 * r)
        x0, x1 = int(hx - 0.15 * r), int(hx + 0.15 * r)
        mask = _ink_mask(img)[y0:y1, x0:x1]
        ys, xs = np.nonzero(mask)
        self.assertGreater(len(xs), 0, "no moustache ink above the mouth")
        top = y0 + int(ys.min())
        bottom = y0 + int(ys.max())
        width = int(xs.max() - xs.min() + 1)
        height = int(ys.max() - ys.min() + 1)
        self.assertGreater(width, height, "moustache taller than wide")
        # Top near the mouth (old geometry floated at my-0.30r) and
        # bottom touching the mouth line (old bottom: my-0.08r).
        self.assertGreaterEqual(top, my - 0.20 * r)
        self.assertLessEqual(top, my - 0.10 * r)
        self.assertGreater(bottom, my - 0.05 * r)
        # Nothing above the block: the old tall bar reached my-0.30r.
        above = _ink_mask(img)[int(my - 0.32 * r):int(my - 0.22 * r),
                               x0:x1]
        self.assertEqual(int(above.sum()), 0, "ink floating above block")


class TestBackOfHead(unittest.TestCase):
    def test_curved_nape_hairline_not_a_disc(self):
        char = make_character("male", name="T", height=774)
        img, joints = _render_face(char, "neutral", "back")
        hx, hy = joints["head"]
        r = char.head_r
        mask = _ink_mask(img)

        def frac(cx, cy, half=4):
            x0, x1 = int(cx - half), int(cx + half + 1)
            y0, y1 = int(cy - half), int(cy + half + 1)
            return float(mask[y0:y1, x0:x1].mean())

        # Sides below the hairline stay light (the old flat pieslice
        # filled them: the solid-disc read).
        for sgn in (-1, 1):
            self.assertLess(frac(hx + sgn * 0.75 * r, hy - 0.05 * r),
                            0.2, "back-of-head side filled like a disc")
        # Hair is still present at the crown.
        self.assertGreater(frac(hx, hy - 0.5 * r), 0.8,
                           "back-of-head lost its hair")


if __name__ == "__main__":
    unittest.main()
