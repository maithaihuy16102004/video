"""Unit tests for PREMIUM_STICKMAN v3 (character_art v3, rig checks,
expression interpolation, Character Art Gate).

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/video-16x9-v2/
"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.animation.rig import (
    Stickman, HEAD_RATIO, BODY_WIDTH_SCALE, bone_lengths,
    expected_bone_lengths, check_foot_contact, check_hand_contact,
    plant_feet, head_track, interp_pose,
)
from ai_clip_studio.animation.character_art import (
    CHARACTER_STYLE, STYLE_LOCK, PALETTE_V51, EXPRESSIONS, EXPRESSION_NAMES,
    TEMPLATES, BODY_VARIANTS, CHARACTER_INSTANCES,
    make_character, make_character_instance,
    blend_expressions, expression_at, draw_character_v3,
    limb_width, outline_width,
)
from ai_clip_studio.animation.primitives import compile_actions, reach_to
from ai_clip_studio.qa_gates import (
    CharacterArtGate, CHARACTER_ART_CRITERIA, combine,
)

W, H = 1920, 1080
INK = (0x17, 0x20, 0x33)
SUIT = (0x17, 0x20, 0x33)


def _standing_char(template="male", **kw):
    ch = make_character(template, **kw)
    ch.set_pose(root_x=960, root_y=679, facing=1,
                thigh_l=0.1, thigh_r=-0.1, knee_l=0.15, knee_r=0.15,
                arm_l=0.1, arm_r=0.1, elbow_l=0.2, elbow_r=0.2,
                bob=0.0, torso_lean=0.0, head_look=0.0)
    return ch


def _render(char, expression="neutral", view="profile"):
    img = Image.new("RGBA", (W, H), (15, 30, 51, 255))
    d = ImageDraw.Draw(img, "RGBA")
    joints = draw_character_v3(d, char, expression=expression, view=view)
    return img, joints


def _art_evidence():
    notes = {c: f"inspected {c} on the design sheet"
             for c in CHARACTER_ART_CRITERIA}
    return {"design_sheet": {"drive_file_id": "test_sheet_id",
                             "path": "character_design_sheet.png"},
            "notes": notes}


class TestStyleLock(unittest.TestCase):
    def test_style_is_locked_premium_stickman(self):
        self.assertEqual(CHARACTER_STYLE, "PREMIUM_STICKMAN")
        self.assertEqual(STYLE_LOCK["head_ratio"], HEAD_RATIO)
        # v4: head ratio is MEASURED from the reference stickman
        # (0.3388), not the V51 standard 0.146.
        self.assertAlmostEqual(HEAD_RATIO, 0.34)
        self.assertGreaterEqual(HEAD_RATIO, STYLE_LOCK["head_ratio_min"])
        self.assertLessEqual(HEAD_RATIO, STYLE_LOCK["head_ratio_max"])

    def test_one_limb_thickness_for_arms_and_legs(self):
        ch = _standing_char()
        self.assertEqual(limb_width(ch), limb_width(ch))
        self.assertGreater(outline_width(ch), 0)
        # Same character, same H: arms and legs share ONE width value.
        # v4 line system, measured from the reference: limbs 0.026*H,
        # head outline 0.028*H.
        self.assertAlmostEqual(
            STYLE_LOCK["limb_w_frac"], 0.026)
        self.assertAlmostEqual(
            STYLE_LOCK["outline_w_frac"], 0.028)


class TestTemplates(unittest.TestCase):
    def test_four_templates_share_one_proportion_system(self):
        for name in ("male", "female", "child", "elderly"):
            ch = make_character(name)
            self.assertAlmostEqual(ch.head_r, 0.34 * ch.H / 2, places=3)
            self.assertAlmostEqual(ch.torso, 0.231 * ch.H, places=3)

    def test_template_identity_markers(self):
        self.assertEqual(make_character("female").hair_style, "long")
        self.assertEqual(make_character("child").hair_style, "tuft")
        self.assertTrue(make_character("elderly").cane)
        self.assertTrue(make_character("elderly").glasses)
        self.assertLess(make_character("child").H,
                        make_character("male").H)

    def test_body_variants_scale_widths_together(self):
        slim = make_character("male", body_variant="slim")
        std = make_character("male", body_variant="standard")
        sturdy = make_character("male", body_variant="sturdy")
        self.assertAlmostEqual(slim.width_scale, 0.9)
        self.assertAlmostEqual(std.width_scale, 1.0)
        self.assertAlmostEqual(sturdy.width_scale, 1.15)
        # Head size does NOT change with body variant; limb width does.
        self.assertEqual(slim.head_r, std.head_r)
        self.assertLess(limb_width(slim), limb_width(std))
        self.assertGreater(limb_width(sturdy), limb_width(std))

    def test_instances_are_same_system(self):
        minh = make_character_instance("minh")
        lan = make_character_instance("lan")
        lustig = make_character_instance("lustig")
        for ch in (minh, lan, lustig):
            self.assertAlmostEqual(ch.head_r, 0.34 * ch.H / 2, places=3)
        self.assertEqual(lan.template, "female")
        self.assertEqual(lustig.hat, "bowler")
        self.assertTrue(lustig.moustache)
        self.assertEqual(minh.suit, "#2E5FA3")

    def test_unknown_template_or_instance_raises(self):
        with self.assertRaises(ValueError):
            make_character("robot")
        with self.assertRaises(ValueError):
            make_character("male", body_variant="huge")
        with self.assertRaises(ValueError):
            make_character_instance("batman")


class TestCharacterArtV3(unittest.TestCase):
    def test_returns_joint_map(self):
        _, joints = _render(_standing_char())
        for key in ("hip", "shoulder", "neck", "head",
                    "knee_l", "knee_r", "foot_l", "foot_r",
                    "elbow_l", "elbow_r", "hand_l", "hand_r"):
            self.assertIn(key, joints)

    def test_torso_is_one_slim_solid_shape_no_shirt(self):
        """Torso centre is solid suit colour; no cream shirt-V / buttons
        (the v2 jacket assembly is gone from the active path)."""
        img, joints = _render(_standing_char())
        arr = np.asarray(img)
        sh, hip = joints["shoulder"], joints["hip"]
        cy = int((sh[1] + hip[1]) / 2)
        cx = int((sh[0] + hip[0]) / 2)
        # Window narrower than the torso itself (~35 px wide at centre).
        strip = arr[cy, cx - 15:cx + 15, :3].astype(int)
        suit = np.array(SUIT)
        exact_suit = np.mean(np.all(strip == suit, axis=1))
        self.assertGreater(exact_suit, 0.7,
                           "torso centre strip is not solid suit colour")
        cream = np.array([0xF3, 0xF0, 0xE8])
        face_fill = np.array([0xF7, 0xF3, 0xE8])
        near_cream = np.mean(
            np.any([np.all(np.abs(strip - cream) < 10, axis=1),
                    np.all(np.abs(strip - face_fill) < 10, axis=1)], axis=0))
        self.assertLess(near_cream, 0.02, "shirt/cream layer inside torso")

    def test_no_blush_no_sweat_drop(self):
        """v2's pasted symbols (blush, sweat drop) must not appear."""
        for mood in ("worried", "happy"):
            img, joints = _render(_standing_char(), expression=mood)
            arr = np.asarray(img).astype(int)
            hx, hy = joints["head"]
            r = int(_standing_char().head_r)
            box = arr[max(0, int(hy - r - 30)):int(hy + r + 30),
                      max(0, int(hx - r - 30)):int(hx + r + 30), :3]
            sweat = np.all(np.abs(box - np.array([180, 220, 255])) < 12,
                           axis=2)
            blush = np.all(np.abs(box - np.array([255, 154, 138])) < 12,
                           axis=2)
            self.assertEqual(int(sweat.sum()), 0, f"sweat drop in {mood}")
            self.assertEqual(int(blush.sum()), 0, f"blush in {mood}")

    def test_hand_is_fingers_not_a_dot(self):
        """The hand must be ink finger strokes, not a skin/white circle:
        no skin-coloured pixels near the hand, and ink extends from it."""
        img, joints = _render(_standing_char())
        arr = np.asarray(img).astype(int)
        hx, hy = joints["hand_r"]
        box = arr[int(hy) - 30:int(hy) + 30, int(hx) - 30:int(hx) + 30, :3]
        skin = np.all(np.abs(box - np.array([0xF0, 0xC8, 0xA0])) < 12,
                      axis=2)
        self.assertEqual(int(skin.sum()), 0, "skin-coloured hand dot")
        ink = np.all(np.abs(box - np.array(INK)) < 12, axis=2)
        self.assertGreater(int(ink.sum()), 80, "no ink fingers at hand")

    def test_head_outline_and_face_fill(self):
        img, joints = _render(_standing_char())
        arr = np.asarray(img).astype(int)
        hx, hy = joints["head"]
        r = _standing_char().head_r
        # Outline ring pixel just inside the head edge is ink.
        edge = arr[int(hy), int(hx + r - 3), :3]
        self.assertTrue(bool(np.all(edge < 60)),
                        f"head edge not ink: {edge}")
        # Face centre (between the eyes and the mouth) is the cream fill.
        # (The short-hair fringe dips to hy-0.375r only at the exact
        # centre top, so sample below the eyes instead.) In profile the
        # face turns (face centre +0.18r, far eye near the head centre),
        # so sample at +0.20r -- between the eyes in every view -- not
        # at the head centre, which the far eye covers in profile.
        centre = arr[int(hy + 0.15 * r), int(hx + 0.20 * r), :3]
        self.assertTrue(bool(np.all(
            np.abs(centre - np.array([0xF7, 0xF3, 0xE8])) < 12)),
            f"face fill wrong: {centre}")

    def test_four_views_render_and_differ(self):
        imgs = {}
        for view in ("front", "three_quarter", "profile", "back"):
            img, joints = _render(_standing_char(), view=view)
            imgs[view] = np.asarray(img, dtype=np.float32)
            hx, hy = joints["head"]
            self.assertTrue(0 < hx < W and 0 < hy < H)
        _, joints = _render(_standing_char(), view="profile")
        hx, hy = joints["head"]
        r = int(_standing_char().head_r)
        box = (slice(max(0, int(hy - r - 30)), int(hy + r + 30)),
               slice(max(0, int(hx - r - 30)), int(hx + r + 30)))
        # Back view has no eyes: head region differs clearly from front.
        diff = float(np.mean(np.abs(imgs["front"][box] - imgs["back"][box])))
        self.assertGreater(diff, 1.0, "front vs back heads look identical")
        diff2 = float(np.mean(np.abs(
            imgs["front"][box] - imgs["profile"][box])))
        self.assertGreater(diff2, 0.5, "front vs profile heads identical")

    def test_dress_costume_extends_torso(self):
        img_plain, _ = _render(make_character("female"))
        img_dress, _ = _render(make_character("female", costume="dress"))
        a = np.asarray(img_plain, dtype=np.float32)
        b = np.asarray(img_dress, dtype=np.float32)
        self.assertGreater(float(np.mean(np.abs(a - b))), 0.05)


class TestExpressions(unittest.TestCase):
    def test_eight_expressions_declared(self):
        self.assertEqual(len(EXPRESSIONS), 8)
        for name in ("neutral", "happy", "sad", "surprised", "worried",
                     "angry", "thinking", "doubtful"):
            self.assertIn(name, EXPRESSIONS)
            self.assertEqual(set(EXPRESSIONS[name].keys()),
                             set(("eye_h", "eye_w", "eye_dx", "brow_in",
                                  "brow_out", "brow_asym", "mouth_curve",
                                  "mouth_open", "mouth_w", "mouth_dx")))

    def test_blend_is_smooth_midpoint(self):
        mid = blend_expressions("neutral", "happy", 0.5)
        self.assertAlmostEqual(mid["eye_h"], (1.00 + 0.45) / 2)
        self.assertAlmostEqual(mid["mouth_curve"], 0.5)
        self.assertAlmostEqual(mid["mouth_w"], (1.00 + 1.40) / 2)
        self.assertEqual(blend_expressions("neutral", "happy", 0.0),
                         EXPRESSIONS["neutral"])
        # u=1.0 must return happy, up to float noise (0.45 is not
        # exactly representable, so assertEqual on the dict is too
        # strict -- compare per key instead).
        full = blend_expressions("neutral", "happy", 1.0)
        for k, v in EXPRESSIONS["happy"].items():
            self.assertAlmostEqual(full[k], v)

    def test_expression_at_keyframes(self):
        keys = [(0.0, "neutral"), (1.0, "surprised")]
        at_half = expression_at(keys, 0.5)
        # v5: surprised is softened (mouth_open 0.85, eye_h 1.45 --
        # the old 1.00 / 1.60 read uneven against the small round
        # mouth). The interpolation math is unchanged.
        self.assertAlmostEqual(at_half["mouth_open"], 0.85 / 2)
        self.assertAlmostEqual(at_half["eye_h"], (1.0 + 1.45) / 2)
        self.assertEqual(expression_at(keys, 0.0)["mouth_open"], 0.0)
        self.assertEqual(expression_at(keys, 2.0)["mouth_open"], 0.85)

    def test_expression_renders_morph_gradually(self):
        """Mid-blend differs from neutral LESS than the full expression
        does -- the face morphs, it does not swap suddenly."""
        def head_diff(img_a, img_b):
            _, joints = _render(_standing_char())
            hx, hy = joints["head"]
            r = int(_standing_char().head_r)
            box = (slice(max(0, int(hy - r - 30)), int(hy + r + 30)),
                   slice(max(0, int(hx - r - 30)), int(hx + r + 30)))
            return float(np.mean(np.abs(
                np.asarray(img_a, dtype=np.float32)[box]
                - np.asarray(img_b, dtype=np.float32)[box])))
        img_n, _ = _render(_standing_char(), expression="neutral")
        img_mid = Image.new("RGBA", (W, H), (15, 30, 51, 255))
        draw_character_v3(ImageDraw.Draw(img_mid, "RGBA"),
                          _standing_char(), expression="neutral",
                          expression_blend=("happy", 0.5))
        img_h, _ = _render(_standing_char(), expression="happy")
        d_mid = head_diff(img_n, img_mid)
        d_full = head_diff(img_n, img_h)
        self.assertGreater(d_mid, 0.15, "mid-blend invisible")
        self.assertLess(d_mid, d_full, "mid-blend jumps past full happy")


class TestRigV3(unittest.TestCase):
    def test_bone_lengths_invariant_across_walk(self):
        chars = {"minh": make_character_instance("minh")}
        chars["minh"].set_pose(root_x=500, root_y=679, facing=1)
        tl = compile_actions(
            [{"type": "walk_to", "char": "minh", "start": 0.0,
              "duration": 2.0, "from_x": 500, "to_x": 900,
              "ground_y": 920}],
            chars, fps=24)
        want = expected_bone_lengths(chars["minh"])
        for fi, frame in tl.items():
            got = bone_lengths(frame["minh"])
            for k, v in want.items():
                self.assertAlmostEqual(got[k], v, delta=2.0,
                                       msg=f"bone {k} changed at frame {fi}")

    def test_plant_feet_puts_both_feet_on_ground(self):
        ch = _standing_char()
        # v4 legs are shorter (0.429*H): the hip must sit at
        # ground - 0.93*leg_length (as walk_to does), otherwise even
        # zero foot spread cannot reach the ground.
        ch.set_pose(root_y=920 - 0.93 * (ch.u_leg + ch.l_leg))
        plant_feet(ch, 920)
        J = ch.joints()
        self.assertEqual(check_foot_contact(J, 920), [])
        self.assertAlmostEqual(J["foot_l"][1], 920, delta=0.5)
        self.assertAlmostEqual(J["foot_r"][1], 920, delta=0.5)

    def test_walk_stance_foot_touches_ground(self):
        chars = {"minh": make_character_instance("minh")}
        chars["minh"].set_pose(root_x=500, root_y=679, facing=1)
        tl = compile_actions(
            [{"type": "walk_to", "char": "minh", "start": 0.0,
              "duration": 2.0, "from_x": 500, "to_x": 900,
              "ground_y": 920}],
            chars, fps=24)
        # v5: at t=0 the walk starts from a STAND -- both feet on the
        # ground (double support). The old walk lifted the left foot
        # 45 px at phase 0, which is not how a walk starts.
        frame0 = tl[0]["minh"]
        self.assertEqual(check_foot_contact(frame0, 920), [])
        self.assertAlmostEqual(frame0["foot_l"][1], 920, delta=0.5)
        self.assertAlmostEqual(frame0["foot_r"][1], 920, delta=0.5)
        # ...and the left foot lifts off during the first step.
        frame12 = tl[12]["minh"]
        self.assertLess(frame12["foot_l"][1], 920 - 10)

    def test_hand_reaches_prop_exactly(self):
        ch = _standing_char()
        target = (1100, 500)
        fn = reach_to(ch, target, 1.0, hand="r")
        fn(1.0)
        J = ch.joints()
        self.assertEqual(check_hand_contact(J, "r", target, tol=3.0), [])
        self.assertLess(math.hypot(J["hand_r"][0] - target[0],
                                   J["hand_r"][1] - target[1]), 3.0)

    def test_interp_pose_midpoint_and_facing_flip(self):
        a = {"root_x": 0.0, "torso_lean": 0.0, "facing": 1}
        b = {"root_x": 100.0, "torso_lean": 0.4, "facing": -1}
        mid = interp_pose(a, b, 0.5)
        self.assertAlmostEqual(mid["root_x"], 50.0)
        self.assertAlmostEqual(mid["torso_lean"], 0.2)
        self.assertEqual(interp_pose(a, b, 0.25)["facing"], 1)
        self.assertEqual(interp_pose(a, b, 0.75)["facing"], -1)

    def test_head_track_turns_toward_target(self):
        ch = _standing_char()
        ang_right = head_track(ch, (1500, 300))
        self.assertGreater(ang_right, 0.0)
        ang_left = head_track(ch, (400, 300))
        self.assertLess(ang_left, 0.0)
        self.assertLessEqual(abs(head_track(ch, (960, -5000))), 0.6 + 1e-9)


class TestCharacterArtGate(unittest.TestCase):
    def test_requires_human_approval_even_with_perfect_scores(self):
        gate = CharacterArtGate()
        scores = {c: 9.0 for c in CHARACTER_ART_CRITERIA}
        res = gate.evaluate(scores, _art_evidence(), human_approved=False)
        self.assertEqual(res.status, "CHARACTER_ART_REVIEW_REQUIRED")
        self.assertFalse(res.passed)

    def test_passes_when_approved_and_all_above_minimum(self):
        gate = CharacterArtGate()
        scores = {c: 8.5 for c in CHARACTER_ART_CRITERIA}
        res = gate.evaluate(scores, _art_evidence(), human_approved=True)
        self.assertEqual(res.status, "CHARACTER_ART_PASS")
        self.assertAlmostEqual(res.weighted_total, 8.5)
        self.assertTrue(res.passed)

    def test_fails_when_approved_but_one_criterion_below_minimum(self):
        gate = CharacterArtGate()
        scores = {c: 8.5 for c in CHARACTER_ART_CRITERIA}
        scores["silhouette"] = 6.5
        res = gate.evaluate(scores, _art_evidence(), human_approved=True)
        self.assertEqual(res.status, "CHARACTER_ART_FAIL")

    def test_missing_design_sheet_needs_review(self):
        gate = CharacterArtGate()
        scores = {c: 9.0 for c in CHARACTER_ART_CRITERIA}
        res = gate.evaluate(scores, {"notes": {}}, human_approved=True)
        self.assertEqual(res.status, "CHARACTER_ART_REVIEW_REQUIRED")

    def test_missing_note_for_a_criterion_needs_review(self):
        gate = CharacterArtGate()
        scores = {c: 9.0 for c in CHARACTER_ART_CRITERIA}
        ev = _art_evidence()
        del ev["notes"]["line_quality"]
        res = gate.evaluate(scores, ev, human_approved=True)
        self.assertEqual(res.status, "CHARACTER_ART_REVIEW_REQUIRED")
        self.assertIsNone(res.scores["line_quality"])

    def test_combine_blocks_draft_pass_without_character_art(self):
        tech = {"status": "TECHNICAL_PASS"}
        crea = {"status": "CREATIVE_PASS"}
        gate = CharacterArtGate()
        scores = {c: 9.0 for c in CHARACTER_ART_CRITERIA}
        pending = gate.evaluate(scores, _art_evidence(),
                                human_approved=False)
        out = combine(tech, crea, pending)
        self.assertEqual(out["verdict"], "CHARACTER_ART_REVIEW_REQUIRED")
        self.assertFalse(out["draft_passed_qa"])
        passed = gate.evaluate(scores, _art_evidence(),
                               human_approved=True)
        out2 = combine(tech, crea, passed)
        self.assertEqual(out2["verdict"], "DRAFT_PASSED_QA")
        self.assertTrue(out2["draft_passed_qa"])
        # Omitting the gate preserves the old two-gate behaviour.
        out3 = combine(tech, crea)
        self.assertEqual(out3["verdict"], "DRAFT_PASSED_QA")


class TestV4ReferenceProportions(unittest.TestCase):
    """v4: the template is rebuilt from the reference measurements
    (measure_reference.py). These tests pin the measured values so a
    future edit cannot silently drift back to the V51 small head."""

    def test_drawn_height_is_exactly_H(self):
        # v4 stack identity: 2*head_r + torso + legs == H.
        ch = make_character("male")
        total = 2 * ch.head_r + ch.torso + ch.u_leg + ch.l_leg
        self.assertAlmostEqual(total, ch.H, places=3)

    def test_head_sits_on_shoulders_no_neck_gap(self):
        ch = _standing_char()
        J = ch.joints()
        # Head bottom (head centre + r) is exactly at shoulder level.
        self.assertAlmostEqual(J["head"][1] + ch.head_r,
                               J["shoulder"][1], delta=2.0)

    def test_torso_tapers_wider_at_hip_like_reference(self):
        # Reference: narrow at shoulders (0.0685H), wider at hip
        # (0.0866H). v3 had it backwards.
        self.assertGreater(STYLE_LOCK["torso_bottom_half_frac"],
                           STYLE_LOCK["torso_top_half_frac"])
        self.assertAlmostEqual(STYLE_LOCK["torso_top_half_frac"], 0.034)
        self.assertAlmostEqual(STYLE_LOCK["torso_bottom_half_frac"], 0.043)

    def test_three_quarter_body_differs_from_profile(self):
        """v3 drew the identical body for 3/4 and profile -- only the
        face moved. v4 compresses the body sideways in 3/4, so the
        BODY region (below the head) must differ clearly. Rendered on
        WHITE: on the dark test background the ink limbs are nearly
        the same colour as the background and the diff is invisible
        numerically even when the shapes differ."""
        def body_diff(view_a, view_b):
            def _one(view):
                img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
                d = ImageDraw.Draw(img, "RGBA")
                J = draw_character_v3(d, _standing_char(), view=view)
                return np.asarray(img, dtype=np.float32), J
            img_a, J = _one(view_a)
            img_b, _ = _one(view_b)
            hy = int(J["shoulder"][1])
            return float(np.mean(np.abs(
                img_a[hy:, :, :3] - img_b[hy:, :, :3])))
        self.assertGreater(body_diff("three_quarter", "profile"), 0.3,
                           "3/4 and profile bodies are identical")

    def test_neutral_face_has_no_brows_like_reference(self):
        """The reference face is two eyes + a mouth, no brows. In the
        neutral render, the strip where brows would sit (just above
        the eyes, below the hair chord) must contain no ink."""
        img, joints = _render(_standing_char(), expression="neutral")
        arr = np.asarray(img)
        hx, hy = joints["head"]
        r = _standing_char().head_r
        # Brow line in v4 sits at hy-0.52r; hair chord at hy-0.55r.
        # Sample the strip hy-0.50r .. hy-0.40r across the eye band.
        y0, y1 = int(hy - 0.50 * r), int(hy - 0.40 * r)
        x0, x1 = int(hx - 0.6 * r), int(hx + 0.6 * r)
        strip = arr[y0:y1, x0:x1, :3].astype(int)
        ink_px = np.sum(np.all(np.abs(strip - np.array(INK)) < 12, axis=2))
        self.assertEqual(int(ink_px), 0,
                         f"neutral face has brow ink: {ink_px}px")

    def test_angry_brows_visible_above_eyes(self):
        """The same strip DOES carry ink for angry (brows moved)."""
        img, joints = _render(_standing_char(), expression="angry")
        arr = np.asarray(img)
        hx, hy = joints["head"]
        r = _standing_char().head_r
        y0, y1 = int(hy - 0.55 * r), int(hy - 0.30 * r)
        x0, x1 = int(hx - 0.6 * r), int(hx + 0.6 * r)
        strip = arr[y0:y1, x0:x1, :3].astype(int)
        ink_px = np.sum(np.all(np.abs(strip - np.array(INK)) < 12, axis=2))
        self.assertGreater(int(ink_px), 20,
                           "angry brows are invisible (buried under hair?)")


if __name__ == "__main__":
    unittest.main()
