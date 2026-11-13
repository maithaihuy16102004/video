"""Tests for Zeus Test F acting (Subagent A, Cinematic Engine Upgrade,
2026-11-12): Cyclops character (single eye, massive build, scale),
hammer-strike work primitive, lightning-bolt prop + energy glow,
mixed-height handover, walk approach, and the general "awe"
expression.

Fixtures are synthetic except one read-only integration test that
parses Mai's Zeus script (never modified) and asserts the forge
scene's own sentences compile to the new verb / handover.
"""
from __future__ import annotations

import math
import os
import unittest

from PIL import Image, ImageDraw

from ai_clip_studio.action_compiler import (
    ACTION_TYPES,
    FORBIDDEN_SEMANTIC_COMPILATIONS,
    SEMANTIC_TO_COMPILER_VERB,
    UnauthorizedStoryChange,
    check_cue_authorization,
    compile_actions,
    detect_conflicts,
)
from ai_clip_studio.semantic_contracts import (
    SEMANTIC_ACTION_TYPES,
    ActionAuthority,
    ActionOrigin,
    AuthorizationStatus,
)
from ai_clip_studio.animation import primitives as P
from ai_clip_studio.animation.character_art import (
    STYLE_LOCK,
    draw_character_v4,
    make_character,
    make_character_from_data,
)
from ai_clip_studio.animation.locomotion import (
    check_facing_vs_travel,
    measure_locomotion,
)
from ai_clip_studio.animation.primitives import (
    HAMMER_CYCLE_SEC,
    HAMMER_CYCLE_STRIKE_U,
    hammer_head_position,
    hammer_strike,
    hammer_strike_times,
)
from ai_clip_studio.animation.rig import (
    BODY_WIDTH_SCALE,
    HEAD_RATIO,
    Stickman,
    check_foot_contact,
)
from ai_clip_studio.animation.silhouette import distinguishable
from ai_clip_studio.expression_library import (
    EXTENDED_EXPRESSIONS,
    interpret,
    interpret_detailed,
    interpret_params,
    params_at,
    schedule_transitions,
    validate_transitions,
)
from ai_clip_studio.prop_system import (
    PropStateMachine,
    bolt_polygon_vertices,
    bolt_shape_spec,
    verify_chain,
)
from ai_clip_studio.qa_measurements import (
    SILHOUETTE_IOU_MAX,
    silhouette_iou,
    silhouette_mask,
)

AGENT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
ZEUS_SCRIPT = os.path.join(
    AGENT_ROOT, "examples", "zeus_ep01_fall_of_cronus.studio.md")

GROUND_Y = 920.0
FPS = 24


def _cyclops_data(height=756):
    """Character data shaped like the script's Cyclops trait block
    (SPECIES one-eyed giant, BODY_TYPE large muscular, blacksmith
    apron): the general trait path carries these fields, and the
    engine honours them -- no Cyclops values live in engine code."""
    return {
        "template": "male",
        "name": "cyclops",
        "height": height,
        "body_variant": "massive",
        "eye_count": 1,
        "hair_style": "short",
        "moustache_style": "full",
        "hat": "none",
        "suit": "#5A4632",
    }


def _zeus_data(height=560):
    return {
        "template": "male",
        "name": "zeus",
        "height": height,
        "body_variant": "standard",
        "eye_count": 2,
        "hair_style": "short",
        "moustache_style": "none",
        "hat": "none",
        "suit": "#2E4A6B",
    }


def _cronus_data(height=972):
    return {
        "template": "male",
        "name": "cronus",
        "height": height,
        "body_variant": "standard",
        "eye_count": 2,
        "hair_style": "long",
        "moustache_style": "full",
        "hat": "none",
        "suit": "#3A3A3A",
    }


def _scanline_runs(img, y, x0, x1, threshold=400):
    """Dark-pixel runs on one scanline: [(start_x, end_x), ...]."""
    px = img.load()
    runs = []
    in_run = False
    start = x0
    for x in range(int(x0), int(x1) + 1):
        r, g, b = px[x, int(y)][:3]
        dark = (r + g + b) < threshold
        if dark and not in_run:
            start, in_run = x, True
        elif not dark and in_run:
            runs.append((start, x - 1))
            in_run = False
    if in_run:
        runs.append((start, int(x1)))
    return runs


def _point_in_polygon(point, polygon):
    """Ray-casting point-in-polygon (boundary counts as inside)."""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if min(y1, y2) < y <= max(y1, y2):
            xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x <= xin:
                inside = not inside
    return inside


def _polygon_area(vertices):
    area = 0.0
    for i, (x1, y1) in enumerate(vertices):
        x2, y2 = vertices[(i + 1) % len(vertices)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _has_reflex_vertex(vertices):
    """True when consecutive edge turns change sign (non-convex)."""
    signs = set()
    n = len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        x3, y3 = vertices[(i + 2) % n]
        cross = (x2 - x1) * (y3 - y2) - (y2 - y1) * (x3 - x2)
        if abs(cross) > 1e-9:
            signs.add(1 if cross > 0 else -1)
    return len(signs) > 1


class TestBoltGeometry(unittest.TestCase):
    def test_bolt_is_not_a_box(self):
        spec = bolt_shape_spec(170)
        verts = spec["vertices"]
        # A box has 4 vertices; the bolt is a jagged polygon.
        self.assertGreaterEqual(len(verts), 6)
        # A box is convex; the bolt has reflex (inward) vertices.
        self.assertTrue(_has_reflex_vertex(verts))
        # A box's vertices sit on its bbox corners only; the bolt's
        # spine zigzags, so interior vertices leave the bbox edges.
        x0, y0, x1, y1 = spec["bbox"]
        corners = {(x0, y0), (x1, y0), (x1, y1), (x0, y1)}
        off_corner = [v for v in verts if v not in corners]
        self.assertGreaterEqual(len(off_corner), 4)

    def test_bolt_polygon_is_valid(self):
        spec = bolt_shape_spec(170)
        verts = spec["vertices"]
        self.assertGreater(_polygon_area(verts), 0.0)
        # No duplicated consecutive vertices (tips deduped).
        for i, v in enumerate(verts):
            self.assertNotEqual(v, verts[(i + 1) % len(verts)])
        # Deterministic: same inputs, same vertices.
        again = bolt_shape_spec(170)
        self.assertEqual(spec["vertices"], again["vertices"])

    def test_bolt_scales_with_length(self):
        small = bolt_shape_spec(100)
        big = bolt_shape_spec(200)
        h_small = small["bbox"][3] - small["bbox"][1]
        h_big = big["bbox"][3] - big["bbox"][1]
        self.assertAlmostEqual(h_big, 2.0 * h_small, places=6)

    def test_bolt_grip_point_is_on_the_shaft(self):
        # The holding hand wraps the shaft AT the grip point, so the
        # grip point must lie inside the bolt polygon.
        spec = bolt_shape_spec(170)
        self.assertTrue(_point_in_polygon(spec["grip"],
                                          spec["vertices"]))

    def test_bolt_world_transform(self):
        spec = bolt_shape_spec(170)
        placed = bolt_polygon_vertices(spec, 100.0, 200.0)
        self.assertEqual(len(placed), len(spec["vertices"]))
        # Angle 0: pure translation of the local vertices.
        for (lx, ly), (wx, wy) in zip(spec["vertices"], placed):
            self.assertAlmostEqual(wx, 100.0 + lx, places=6)
            self.assertAlmostEqual(wy, 200.0 + ly, places=6)
        # Angle 90: the grip stays at (x, y); the bolt rotates.
        rotated = bolt_polygon_vertices(spec, 100.0, 200.0,
                                        angle_deg=90.0)
        for (lx, ly), (wx, wy) in zip(spec["vertices"], rotated):
            self.assertAlmostEqual(wx, 100.0 - ly, places=6)
            self.assertAlmostEqual(wy, 200.0 + lx, places=6)

    def test_bolt_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            bolt_shape_spec(0)
        with self.assertRaises(ValueError):
            bolt_shape_spec(170, width=0)
        with self.assertRaises(ValueError):
            bolt_shape_spec(170, segments=1)


class TestCyclopsCharacter(unittest.TestCase):
    def test_eye_count_validation(self):
        self.assertEqual(Stickman(eye_count=1).eye_count, 1)
        self.assertEqual(Stickman().eye_count, 2)
        with self.assertRaises(ValueError):
            Stickman(eye_count=3)
        with self.assertRaises(ValueError):
            Stickman(eye_count=0)

    def test_massive_variant_scales_widths_together(self):
        self.assertEqual(BODY_WIDTH_SCALE["massive"], 1.30)
        char = make_character("male", body_variant="massive")
        self.assertEqual(char.width_scale, 1.30)
        from ai_clip_studio.animation.character_art import limb_width
        std = make_character("male", body_variant="standard")
        self.assertAlmostEqual(
            limb_width(char) / limb_width(std), 1.30, places=6)

    def test_head_ratio_locked_at_scale(self):
        # Scale changes height, never the head ratio (D3 lock).
        for height in (560, 756, 972):
            char = make_character_from_data(_cyclops_data(height))
            self.assertAlmostEqual(2.0 * char.head_r / char.H,
                                   HEAD_RATIO, places=9)
            self.assertEqual(char.H, height)

    def test_trait_data_path_builds_cyclops(self):
        char = make_character_from_data(_cyclops_data())
        self.assertEqual(char.eye_count, 1)
        self.assertEqual(char.body_variant, "massive")
        self.assertEqual(char.width_scale, 1.30)

    def test_single_eye_draws_one_centred_eye(self):
        # Pixel assertion: on the eye scanline, inside the head, a
        # two-eyed face has TWO ink runs and a one-eyed face has ONE
        # run centred on the face centre. The single eye sits on the
        # forehead (SINGLE_EYE_DY_FRAC above the centre line).
        from ai_clip_studio.animation.character_art import (
            SINGLE_EYE_DY_FRAC,
        )
        for eye_count, want_runs in ((2, 2), (1, 1)):
            char = make_character("male", height=560,
                                  eye_count=eye_count,
                                  hat="none", moustache_style="none",
                                  hair_style="short")
            P.standing(char, 280, 500, facing=1)
            img = Image.new("RGB", (560, 560), (255, 255, 255))
            draw = ImageDraw.Draw(img)
            draw_character_v4(draw, char, expression="neutral",
                              view="front")
            head = char.joints()["head"]
            r = char.head_r
            eye_dy = STYLE_LOCK["eye_dy_frac_of_r"]
            if eye_count == 1:
                eye_dy += SINGLE_EYE_DY_FRAC
            eye_y = head[1] + eye_dy * r
            runs = _scanline_runs(img, eye_y,
                                  head[0] - 0.5 * r, head[0] + 0.5 * r)
            self.assertEqual(len(runs), want_runs,
                             f"eye_count={eye_count}: runs={runs}")
            if eye_count == 1:
                centre = (runs[0][0] + runs[0][1]) / 2.0
                self.assertLess(abs(centre - head[0]), 0.05 * r)

    def test_silhouette_gate_distinguishes_cyclops(self):
        cyclops = make_character_from_data(_cyclops_data())
        zeus = make_character_from_data(_zeus_data())
        cronus = make_character_from_data(_cronus_data())
        for other in (zeus, cronus):
            result = distinguishable(cyclops, other)
            self.assertTrue(result["distinguishable"], result)
            self.assertIn("eye_count", result["differing"])
        # The eye alone is not the whole story: at identical height
        # and build, one eye still differs from two.
        same = make_character("male", height=560,
                              body_variant="standard", eye_count=1,
                              hat="none", moustache_style="none")
        two = make_character("male", height=560,
                             body_variant="standard", eye_count=2,
                             hat="none", moustache_style="none")
        result = distinguishable(same, two)
        self.assertEqual(result["differing"], ["eye_count"])

    def test_rendered_silhouette_iou_below_max(self):
        # Pixel-level IoU (half scale for speed; proportions are
        # scale-invariant). Same canvas, same ground, same pose.
        chars = {
            "zeus": make_character_from_data(_zeus_data(280)),
            "cyclops": make_character_from_data(_cyclops_data(378)),
            "cronus": make_character_from_data(_cronus_data(486)),
        }
        masks = {}
        for name, char in chars.items():
            P.standing(char, 160, 520, facing=1)
            img = Image.new("RGB", (320, 560), (255, 255, 255))
            draw = ImageDraw.Draw(img)
            draw_character_v4(draw, char, expression="neutral",
                              view="front")
            mask = silhouette_mask(img)
            ink = sum(sum(1 for v in row if v) for row in mask)
            self.assertGreater(ink, 1000, f"{name} rendered blank")
            masks[name] = mask
        for a, b in (("cyclops", "zeus"), ("cyclops", "cronus")):
            iou = silhouette_iou(masks[a], masks[b])
            self.assertLess(iou, SILHOUETTE_IOU_MAX,
                            f"{a} vs {b}: IoU {iou}")
            self.assertGreater(iou, 0.0)


class TestHammerStrike(unittest.TestCase):
    def _run_strike(self, strike_point, duration=3.6, cycles=4,
                    height=756, root_x=700.0):
        char = make_character_from_data(_cyclops_data(height))
        P.standing(char, root_x, GROUND_Y, facing=1)
        fn = hammer_strike(char, strike_point, duration,
                           GROUND_Y, cycles=cycles)
        frames = []
        for fi in range(int(duration * FPS) + 1):
            t = fi / FPS
            fn(t)
            joints = char.joints()
            frames.append((t, joints))
        return char, frames

    def test_head_contacts_surface_at_strike_moments(self):
        strike = (850.0, 700.0)
        char = make_character_from_data(_cyclops_data())
        P.standing(char, 700.0, GROUND_Y, facing=1)
        fn = hammer_strike(char, strike, 3.6, GROUND_Y, cycles=4)
        # Drive the primitive through a monotonic timeline that
        # includes the EXACT strike times (they fall between frames):
        # contact is defined at the strike moment, not at the nearest
        # frame. Frame-sampled error is asserted separately below.
        times = hammer_strike_times(3.6, 4)
        probe = sorted({fi / FPS for fi in range(int(3.6 * FPS) + 1)}
                       | set(times))
        at_strike = {}
        frame_samples = []
        for t in probe:
            fn(t)
            joints = char.joints()
            frame_samples.append((t, joints))
            if t in times:
                at_strike[t] = joints
        self.assertEqual(len(at_strike), 4)
        for strike_t, joints in at_strike.items():
            head = hammer_head_position(joints["hand_r"],
                                        joints["facing"], char.H)
            dist = math.hypot(head[0] - strike[0],
                              head[1] - strike[1])
            self.assertLess(dist, 1.0,
                            f"t={strike_t}: head {head} vs {strike}")
        # Nearest-frame sampling (what a 24 fps QA pass sees) stays
        # far inside the 12 px tool_head tolerance.
        for strike_t in times:
            nearest = min(frame_samples,
                          key=lambda f: abs(f[0] - strike_t))
            joints = nearest[1]
            head = hammer_head_position(joints["hand_r"],
                                        joints["facing"], char.H)
            dist = math.hypot(head[0] - strike[0],
                              head[1] - strike[1])
            self.assertLess(dist, 3.0, f"t={strike_t}: {dist}px")

    def test_head_geometry(self):
        hand = (800.0, 600.0)
        head = hammer_head_position(hand, 1, 560.0)
        dist = math.hypot(head[0] - hand[0], head[1] - hand[1])
        self.assertAlmostEqual(dist, 0.16 * 560.0, places=6)
        # Forward-down: ahead of the hand and below it.
        self.assertGreater(head[0], hand[0])
        self.assertGreater(head[1], hand[1])
        # Facing left mirrors the forward component.
        head_l = hammer_head_position(hand, -1, 560.0)
        self.assertLess(head_l[0], hand[0])
        self.assertAlmostEqual(head_l[1], head[1], places=6)

    def test_grip_angle_phases(self):
        from ai_clip_studio.animation.primitives import (
            HAMMER_CARRY_ANGLE_RAD,
            HAMMER_GRIP_ANGLE_RAD,
            hammer_grip_angle,
        )
        # Rest / cycle boundaries: the strike angle (hammer hangs).
        self.assertAlmostEqual(hammer_grip_angle(0.0),
                               HAMMER_GRIP_ANGLE_RAD)
        self.assertAlmostEqual(hammer_grip_angle(1.0),
                               HAMMER_GRIP_ANGLE_RAD)
        # Raise / hold: the carry angle (cocked up-back).
        self.assertAlmostEqual(hammer_grip_angle(0.40),
                               HAMMER_CARRY_ANGLE_RAD)
        # Strike moment: EXACTLY the strike angle (contact exact).
        self.assertAlmostEqual(
            hammer_grip_angle(HAMMER_CYCLE_STRIKE_U),
            HAMMER_GRIP_ANGLE_RAD)
        # Recovery: back at the strike angle.
        self.assertAlmostEqual(hammer_grip_angle(0.80),
                               HAMMER_GRIP_ANGLE_RAD)
        # The carry angle puts the head up-back of the hand.
        head = hammer_head_position((800.0, 600.0), 1, 560.0,
                                    HAMMER_CARRY_ANGLE_RAD)
        self.assertLess(head[0], 800.0)
        self.assertLess(head[1], 600.0)

    def test_head_stays_above_surface_between_strikes(self):
        strike = (850.0, 700.0)
        char, frames = self._run_strike(strike)
        # The no-penetration rule applies while the head is OVER the
        # anvil's strike span (+/-40 px around the strike point): at
        # rest the hammer hangs beside the body, below the anvil-top
        # plane but nowhere near the anvil -- that is correct, not a
        # penetration.
        for t, joints in frames:
            head = hammer_head_position(joints["hand_r"],
                                        joints["facing"], char.H)
            if abs(head[0] - strike[0]) <= 40.0:
                self.assertLessEqual(head[1], strike[1] + 1.0,
                                     f"t={t}: head {head}")

    def test_feet_stay_planted(self):
        char, frames = self._run_strike((850.0, 700.0))
        first = frames[0][1]
        for t, joints in frames:
            for foot in ("foot_l", "foot_r"):
                dx = abs(joints[foot][0] - first[foot][0])
                dy = abs(joints[foot][1] - first[foot][1])
                self.assertLess(dx, 1.0, f"t={t} {foot} slid x")
                self.assertLess(dy, 1.0, f"t={t} {foot} moved y")
        for _t, joints in frames:
            self.assertEqual(check_foot_contact(joints, GROUND_Y), [])

    def test_out_of_reach_strike_misses_honestly(self):
        # A strike point beyond arm reach must MISS (measured), never
        # be faked closer: the IK clamp stops the hand short.
        strike = (1400.0, 700.0)
        char, frames = self._run_strike(strike, duration=0.9,
                                        cycles=1)
        strike_t = hammer_strike_times(0.9, 1)[0]
        nearest = min(frames, key=lambda f: abs(f[0] - strike_t))
        head = hammer_head_position(nearest[1]["hand_r"],
                                    nearest[1]["facing"], char.H)
        dist = math.hypot(head[0] - strike[0], head[1] - strike[1])
        self.assertGreater(dist, 5.0)

    def test_default_cycles_follow_duration(self):
        char = make_character_from_data(_cyclops_data())
        P.standing(char, 700, GROUND_Y, facing=1)
        fn = hammer_strike(char, (850.0, 700.0), 1.8, GROUND_Y)
        # 1.8 s / 0.9 s per cycle = 2 cycles: strikes at 0.54, 1.44.
        fn(0.54)
        joints = char.joints()
        head = hammer_head_position(joints["hand_r"], joints["facing"],
                                    char.H)
        self.assertLess(math.hypot(head[0] - 850.0,
                                   head[1] - 700.0), 1.0)
        fn(1.44)
        joints = char.joints()
        head = hammer_head_position(joints["hand_r"], joints["facing"],
                                    char.H)
        self.assertLess(math.hypot(head[0] - 850.0,
                                   head[1] - 700.0), 1.0)

    def test_hammer_strike_in_registry_and_compile(self):
        self.assertIn("hammer_strike", P.PRIMITIVES)
        self.assertIn("hammer_strike", P.PRIMITIVE_COMPLETION)
        chars = {"smith": make_character_from_data(_cyclops_data())}
        P.standing(chars["smith"], 700, GROUND_Y, facing=1)
        timeline = P.compile_actions(
            [{"type": "hammer_strike", "char": "smith", "start": 0.0,
              "duration": 0.9, "target": (850.0, 700.0),
              "ground_y": GROUND_Y, "cycles": 1}],
            chars, fps=FPS)
        self.assertGreater(len(timeline), 0)


class TestHandoverAndBolt(unittest.TestCase):
    def _handover_run(self, giver_h=756, receiver_h=560,
                      gap=170.0, duration=1.5):
        giver = make_character_from_data(_cyclops_data(giver_h))
        receiver = make_character_from_data(_zeus_data(receiver_h))
        giver_x, receiver_x = 780.0, 780.0 + gap
        P.standing(giver, giver_x, GROUND_Y, facing=1)
        P.standing(receiver, receiver_x, GROUND_Y, facing=-1)
        prop = {"x": giver_x, "y": GROUND_Y - 200.0}
        fn = P.hand_over(giver, receiver, prop, duration)
        samples = []
        for fi in range(int(duration * FPS) + 1):
            t = fi / FPS
            fn(t)
            samples.append((t, {"CHAR_A": giver.joints(),
                                "CHAR_B": receiver.joints()}))
        return giver, receiver, prop, samples

    def test_mixed_height_handover_gap(self):
        _g, _r, _p, samples = self._handover_run()
        _t, joints = samples[-1]
        gap = math.hypot(
            joints["CHAR_A"]["hand_r"][0]
            - joints["CHAR_B"]["hand_l"][0],
            joints["CHAR_A"]["hand_r"][1]
            - joints["CHAR_B"]["hand_l"][1])
        # TEST E standard: hands meet (sub-pixel to a few px).
        self.assertLess(gap, 5.0, f"handover gap {gap}px")

    def test_thin_lens_handover_gap(self):
        # The Test F proof-B staging: 320 px apart, facing each
        # other from opposite sides, the reach circles overlap by
        # only ~20 px, so the meeting-point projection must iterate
        # to convergence -- two passes left a 21.9 px residual on
        # the proof render.
        _g, _r, _p, samples = self._handover_run(gap=320.0)
        _t, joints = samples[-1]
        gap = math.hypot(
            joints["CHAR_A"]["hand_r"][0]
            - joints["CHAR_B"]["hand_l"][0],
            joints["CHAR_A"]["hand_r"][1]
            - joints["CHAR_B"]["hand_l"][1])
        self.assertLess(gap, 5.0, f"handover gap {gap}px")

    def test_equal_height_handover_gap_unchanged(self):
        _g, _r, _p, samples = self._handover_run(giver_h=560,
                                                 receiver_h=560,
                                                 gap=300.0)
        _t, joints = samples[-1]
        gap = math.hypot(
            joints["CHAR_A"]["hand_r"][0]
            - joints["CHAR_B"]["hand_l"][0],
            joints["CHAR_A"]["hand_r"][1]
            - joints["CHAR_B"]["hand_l"][1])
        self.assertLess(gap, 5.0, f"handover gap {gap}px")

    def test_bolt_chain_verifies_clean(self):
        giver, receiver, _prop, samples = self._handover_run()
        events = [{
            # The giver grasps the bolt before the handover: a
            # HAND_OVER without a preceding grasp is a chain-order
            # violation by design (check_chain_order).
            "action_id": "P0", "action_type": "PICK_UP",
            "actor_id": "CHAR_A", "prop_id": "prop_bolt",
            "start_time": -1.0, "end_time": 0.0,
            "required_pose": {"primitive": "pick_up",
                              "params": {"hand": "r"}},
            "contact_points": [],
        }, {
            "action_id": "H1", "action_type": "HAND_OVER",
            "actor_id": "CHAR_A", "target_id": "CHAR_B",
            "prop_id": "prop_bolt", "start_time": 0.0,
            "end_time": 1.5,
            "required_pose": {"primitive": "hand_over",
                              "params": {"hand": "r"}},
            "contact_points": [
                {"joint": "hand_r", "target_kind": "character_hand",
                 "target_id": "CHAR_B", "tolerance_px": 20.0},
                {"joint": "hand_r", "target_kind": "prop",
                 "target_id": "prop_bolt", "tolerance_px": 15.0}],
        }]
        psm = PropStateMachine(
            [{"id": "prop_bolt", "kind": "bolt"}],
            events,
            staging={"prop_bolt": (780.0, GROUND_Y - 200.0)},
            ground_y=GROUND_Y)
        series = []
        for t, joints in samples:
            joints = {aid: dict(j) for aid, j in joints.items()}
            joints["CHAR_A"]["_H"] = float(giver.H)
            joints["CHAR_B"]["_H"] = float(receiver.H)
            series.append({
                "t": t, "joints": joints,
                "transforms": {"prop_bolt": psm.transform_at(
                    "prop_bolt", t, joints)}})
        report = verify_chain(psm, series, events, ground_y=GROUND_Y)
        self.assertEqual(report["violations"], [])
        for pid, jump in report["teleports"].items():
            self.assertFalse(jump["teleport"], pid)
        for entries in report["contact"].values():
            for entry in entries:
                self.assertTrue(entry["satisfied"], entry)
        # At the end the bolt sits exactly at the receiver's hand.
        last = series[-1]
        px, py = last["transforms"]["prop_bolt"][:2]
        hand = last["joints"]["CHAR_B"]["hand_l"]
        self.assertLess(math.hypot(px - hand[0], py - hand[1]), 1.0)


class TestEnergyGlow(unittest.TestCase):
    def _psm(self):
        events = [
            {"action_id": "P1", "action_type": "PICK_UP",
             "actor_id": "CHAR_A", "prop_id": "prop_bolt",
             "start_time": 0.0, "end_time": 1.0,
             "required_pose": {"primitive": "pick_up",
                               "params": {"hand": "r"}}},
            {"action_id": "H1", "action_type": "HAND_OVER",
             "actor_id": "CHAR_A", "target_id": "CHAR_B",
             "prop_id": "prop_bolt", "start_time": 1.0,
             "end_time": 2.5,
             "required_pose": {"primitive": "hand_over",
                               "params": {"hand": "r"}}},
        ]
        return PropStateMachine(
            [{"id": "prop_bolt", "kind": "bolt",
              "energy": {"color": (120, 180, 255), "radius_px": 260.0}},
             {"id": "prop_rock", "kind": "generic"}],
            events,
            staging={"prop_bolt": (500.0, 700.0),
                     "prop_rock": (300.0, 800.0)},
            ground_y=GROUND_Y)

    def _joints(self):
        return {
            "CHAR_A": {"hand_r": (500.0, 700.0), "hand_l": (460.0, 700.0),
                       "hip": (480.0, 600.0), "facing": 1},
            "CHAR_B": {"hand_r": (640.0, 700.0), "hand_l": (600.0, 700.0),
                       "hip": (620.0, 600.0), "facing": -1},
        }

    def test_no_glow_without_energy_or_hold(self):
        psm = self._psm()
        joints = self._joints()
        # A prop with no energy spec never glows.
        self.assertIsNone(psm.energy_glow_at("prop_rock", 1.5, joints))
        # Before the grasp the bolt is not held: no record.
        self.assertIsNone(psm.energy_glow_at("prop_bolt", 0.1, joints))

    def test_glow_ramps_and_holds(self):
        psm = self._psm()
        joints = self._joints()
        # Grasp at 0.45 (PICK_UP_GRASP_U); ramp 0.4 s -> full at 0.85.
        mid = psm.energy_glow_at("prop_bolt", 0.65, joints)
        self.assertIsNotNone(mid)
        self.assertGreater(mid["intensity"], 0.0)
        self.assertLess(mid["intensity"], 1.0)
        full = psm.energy_glow_at("prop_bolt", 1.0, joints)
        self.assertAlmostEqual(full["intensity"], 1.0)
        self.assertEqual(full["color"], (120, 180, 255))
        self.assertAlmostEqual(full["radius"], 260.0)
        self.assertEqual(full["prop_id"], "prop_bolt")
        self.assertEqual(full["holder"], "CHAR_A")

    def test_glow_survives_handover_without_reramp(self):
        psm = self._psm()
        joints = self._joints()
        during = psm.energy_glow_at("prop_bolt", 1.2, joints)
        self.assertAlmostEqual(during["intensity"], 1.0)
        after = psm.energy_glow_at("prop_bolt", 2.5, joints)
        self.assertAlmostEqual(after["intensity"], 1.0)
        self.assertEqual(after["holder"], "CHAR_B")

    def test_glow_source_follows_prop(self):
        psm = self._psm()
        joints = self._joints()
        record = psm.energy_glow_at("prop_bolt", 1.0, joints)
        x, y, _a, _s, _h = psm.transform_at("prop_bolt", 1.0, joints)
        sx, sy = record["source_position"]
        # Source is the bolt-centre offset from the grip point: near
        # the prop, shifted toward the bolt's middle (up the shaft).
        self.assertLess(math.hypot(sx - x, sy - y), 120.0)
        self.assertLess(sy, y)


class TestWalkApproach(unittest.TestCase):
    def test_zeus_approach_walk_is_clean(self):
        # Phase A methodology: steady-state window only (the
        # anticipation crouch + settle are asymmetric by design and
        # excluded), canonical duration for the distance.
        from ai_clip_studio.animation.locomotion import (
            duration_for_distance,
            sample_primitive,
        )
        zeus = make_character_from_data(_zeus_data())
        P.standing(zeus, 300, GROUND_Y, facing=1)
        duration = duration_for_distance(1120.0, 560.0, "canonical")
        fn = P.walk_to(zeus, 300, 1420, duration, GROUND_Y,
                       profile="canonical")
        frames = sample_primitive(fn, zeus, duration, FPS)
        travel = [f for f in frames
                  if 0.2 <= f["_t"] <= duration - 0.25]
        report = measure_locomotion(travel, FPS, 560.0, GROUND_Y)
        # Canonical cadence: 80 steps/min +/- 25%.
        self.assertGreater(report.cadence, 60)
        self.assertLess(report.cadence, 100)
        # Planted-foot drift under 0.01 heights (~5.6 px).
        self.assertLess(report.foot_sliding, 0.01)
        self.assertGreater(report.left_right_symmetry, 0.95)
        violations = check_facing_vs_travel(travel, FPS, min_run=3)
        self.assertEqual(violations, [])


class TestAweExpression(unittest.TestCase):
    def test_awe_label_and_recipe(self):
        self.assertEqual(EXTENDED_EXPRESSIONS["awe"]["base"],
                         "surprised")
        self.assertEqual(EXTENDED_EXPRESSIONS["awe"]["blend"],
                         ("happy", 0.35))
        detail = interpret_detailed("awe")
        self.assertEqual(detail["label"], "awe")
        self.assertEqual(detail["source"], "extended")
        self.assertEqual(detail["expression"], "surprised")

    def test_awe_keywords(self):
        for text in ("awe", "awestruck", "ngỡ ngàng", "trầm trồ",
                     "thán phục", "filled with awe"):
            self.assertEqual(interpret_detailed(text)["label"], "awe",
                             text)
        # Surprised-family words still resolve to surprised, never
        # to awe (base families win ties by design).
        self.assertEqual(interpret("kinh ngạc"), "surprised")
        self.assertEqual(interpret("astonished"), "surprised")

    def test_awe_params_between_surprised_and_happy(self):
        from ai_clip_studio.animation.character_art import EXPRESSIONS
        awe = interpret_params("awe")
        surprised = EXPRESSIONS["surprised"]
        happy = EXPRESSIONS["happy"]
        for key in ("eye_h", "eye_w", "mouth_open", "mouth_curve",
                    "brow_in", "brow_out", "mouth_w"):
            lo = min(surprised[key], happy[key])
            hi = max(surprised[key], happy[key])
            self.assertGreaterEqual(awe[key], lo, key)
            self.assertLessEqual(awe[key], hi, key)
        # Awe keeps the wide eyes + open mouth of surprise.
        self.assertGreater(awe["eye_h"], 1.0)
        self.assertGreater(awe["mouth_open"], 0.5)

    def test_awe_negation(self):
        detail = interpret_detailed("không ngỡ ngàng")
        self.assertEqual(detail["expression"], "neutral")
        self.assertTrue(detail["negated"])

    def test_awe_transition_interpolates_and_validates(self):
        # Extended labels resolve to param dicts (interpret_params);
        # keyframes carry the resolved dict -- expression_at only
        # knows the 8 base names. The interpolation itself runs
        # through the standard params_at path.
        awe_params = interpret_params("awe")
        keyframes = [(0.0, "neutral"), (1.2, awe_params)]
        eye_hs = [params_at(keyframes, t)["eye_h"]
                  for t in (0.0, 0.3, 0.6, 0.9, 1.2)]
        # Monotonic rise from neutral toward awe (no jumps).
        for a, b in zip(eye_hs, eye_hs[1:]):
            self.assertLessEqual(a, b + 1e-9)
        self.assertLess(eye_hs[0], eye_hs[-1])
        _kf, transitions, _warn = schedule_transitions(
            [(1.2, "neutral", "awe", "cut")], cut_times=(1.2,))
        self.assertEqual(
            validate_transitions(transitions, cut_times=(1.2,)), [])


class TestHammerStrikeCompiler(unittest.TestCase):
    def _package(self, actions, meta=None):
        scene = {
            "id": "SC01",
            "location_id": "LOC_FORGE",
            "shots": [{
                "id": "SC01_SH01", "camera": "MEDIUM",
                "action": " ".join(actions), "expression": "",
            }],
            "v1_scene": {
                "id": "SC01",
                "shots": [{
                    "id": "SC01_SH01", "camera": "MEDIUM",
                    "expression": "",
                    "fields": {"ACTION": list(actions)},
                }],
            },
        }
        pkg = {
            "characters": [
                {"id": "CHAR_SMITH", "name": "Smith",
                 "template": "male", "voice_id": "V_Smith"},
            ],
            "props": [
                {"id": "prop_hammer", "name": "hammer",
                 "kind": "hammer", "owner": ""},
                {"id": "prop_anvil", "name": "anvil",
                 "kind": "anvil", "owner": ""},
            ],
            "scenes": [scene],
        }
        if meta:
            pkg["v1_meta"] = meta
        return pkg

    def test_hammer_sentence_compiles(self):
        events, _unsupported = compile_actions(
            self._package(["Smith nâng búa."]), None)
        kinds = [e["action_type"] for e in events]
        self.assertIn("HAMMER_STRIKE", kinds)
        event = next(e for e in events
                     if e["action_type"] == "HAMMER_STRIKE")
        self.assertEqual(event["required_pose"]["primitive"],
                         "hammer_strike")

    def test_forge_entry_is_not_hammering(self):
        # "Entering the forge" names the place, not the tool: it must
        # compile to locomotion, never to HAMMER_STRIKE.
        events, _unsupported = compile_actions(
            self._package(["Smith bước vào lò rèn."]), None)
        kinds = [e["action_type"] for e in events]
        self.assertNotIn("HAMMER_STRIKE", kinds)
        self.assertIn("WALK", kinds)

    def test_zeus_forge_scene_compiles(self):
        # Read-only: Mai's script is an input, never modified.
        from ai_clip_studio.studio_script_v1 import (
            parse_studio_script_v1,
        )
        from ai_clip_studio.studio_script_v1_adapter import (
            adapt_document,
        )
        with open(ZEUS_SCRIPT, encoding="utf-8") as fh:
            text = fh.read()
        pkg = adapt_document(parse_studio_script_v1(text))
        events, _unsupported = compile_actions(pkg, None)
        by_shot = {}
        for event in events:
            by_shot.setdefault(event.get("shot_id"), []).append(
                event["action_type"])
        self.assertIn("HAMMER_STRIKE", by_shot.get("SC08_SH01", []))
        self.assertIn("HAND_OVER", by_shot.get("SC08_SH02", []))


# ---------------------------------------------------------------------------
# A2 extension (Semantic Production Engine Upgrade, 2026-11-12):
# compiler provenance, conflict detection, mapping totality, right-hand
# handover, crouch/receive primitives, new compiler verbs, and the
# cross-language prop-mention bridge.
# ---------------------------------------------------------------------------


def _a2_package(actions, props=None):
    """Synthetic single-shot package with scene numbers (required
    for semantic resolution -- the compiler never invents ids)."""
    return {
        "characters": [
            {"id": "CHAR_ANA", "name": "Ana", "gender": "female",
             "template": "female", "voice_id": "V_A",
             "costume": "red coat"},
            {"id": "CHAR_BEN", "name": "Ben", "gender": "male",
             "template": "male", "voice_id": "V_B",
             "costume": "blue uniform"},
        ],
        "props": props or [{"id": "prop_wallet", "name": "wallet",
                            "kind": "wallet", "owner": ""}],
        "scenes": [{
            "id": "SC01", "number": 1, "location_id": "LOC_X",
            "shots": [{"id": "SC01_SH01", "camera": "MEDIUM",
                       "action": " ".join(actions),
                       "expression": ""}],
            "v1_scene": {
                "id": "SC01", "number": 1,
                "shots": [{"id": "SC01_SH01", "camera": "MEDIUM",
                           "expression": "",
                           "fields": {"ACTION": list(actions)}}]},
        }],
    }


class TestCompilerProvenance(unittest.TestCase):
    PROVENANCE_FIELDS = (
        "source_script_hash", "source_scene_id", "source_shot_id",
        "source_directive_id", "action_origin", "inference_reason",
        "authorization_status",
    )

    def test_every_event_carries_provenance(self):
        pkg = _a2_package([
            "Ana đi bộ qua phố.", "Ana hơi cúi đầu.",
            "Ana dừng lại.", "Ana lấy ví từ túi áo.",
            "Ana mở ví bằng hai tay.", "Ana nhìn vào ví.",
            "Ana đóng ví.", "Ana cất ví vào túi.",
        ])
        events, unsupported = compile_actions(pkg, {})
        self.assertEqual(unsupported, [])
        self.assertEqual(len(events), 8)
        for event in events:
            for field in self.PROVENANCE_FIELDS:
                self.assertIn(field, event, field)
            self.assertIn(event["action_origin"],
                          {o.value for o in ActionOrigin})
            self.assertIn(event["authorization_status"],
                          {s.value for s in AuthorizationStatus})
            self.assertEqual(event["action_origin"],
                             "EXPLICIT_SCRIPT_ACTION")
            self.assertEqual(event["authorization_status"],
                             "AUTHORIZED")
            self.assertTrue(event["inference_reason"])

    def test_semantic_types_on_sc01_shape_package(self):
        pkg = _a2_package([
            "Ana đi bộ qua phố.", "Ana hơi cúi đầu.",
            "Ana dừng lại.", "Ana lấy ví từ túi áo.",
            "Ana mở ví bằng hai tay.", "Ana nhìn vào ví.",
            "Ana đóng ví.", "Ana cất ví vào túi.",
        ])
        events, _ = compile_actions(pkg, {})
        self.assertEqual(
            [e["semantic_action_type"] for e in events],
            ["WALK", "HEAD_TILT_DOWN", "STOP", "TAKE_FROM_POCKET",
             "OPEN", "LOOK_AT", "CLOSE", "PUT_AWAY"])

    def test_unsupported_entries_rejected_not_authorized(self):
        pkg = _a2_package(["Ana quỳ xuống."])
        events, unsupported = compile_actions(pkg, {})
        self.assertEqual(events, [])
        self.assertEqual(len(unsupported), 1)
        self.assertEqual(unsupported[0]["action_origin"],
                         "UNSUPPORTED_ACTION")
        self.assertEqual(unsupported[0]["authorization_status"],
                         "REJECTED")
        self.assertIsNone(unsupported[0]["semantic_action_type"])

    def test_gait_note_is_supporting_not_explicit(self):
        pkg = _a2_package(["Ana đi bộ, chuyển động theo bước chân."])
        events, _ = compile_actions(pkg, {})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action_origin"],
                         "SAFE_SUPPORTING_ACTION")
        self.assertIsNone(events[0]["semantic_action_type"])


class TestConflictDetection(unittest.TestCase):
    def _pocket_event(self, action_id="SC01_SH01_ACT01"):
        return {
            "action_id": action_id, "action_type": "TAKE_OUT",
            "semantic_action_type": "TAKE_FROM_POCKET",
            "shot_id": "SC01_SH01", "scene_number": 1,
            "directive_text": "Lấy ví từ túi áo",
            "required_pose": {"primitive": "take_out",
                              "params": {"pocket": True}},
        }

    def test_r1_stale_cue_resolves_to_compiled_event(self):
        records = detect_conflicts(
            cue_records=[{"cue": "bend_pick",
                          "source_shot_id": "SC01_SH01"}],
            compiled_events=[self._pocket_event()])
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec.level_a, "cues")
        self.assertEqual(rec.level_b, "compiled_events")
        self.assertTrue(rec.mandatory)
        self.assertEqual(rec.winner_authority,
                         ActionAuthority.COMPILED_EVENT)
        self.assertFalse(rec.fails_preflight)

    def test_r1_escapes_when_genuine_pickup_directed(self):
        events = [self._pocket_event(), {
            "action_id": "SC01_SH01_ACT02", "action_type": "KNEEL_PICK",
            "semantic_action_type": "BEND_PICK",
            "shot_id": "SC01_SH01", "scene_number": 1,
            "directive_text": "Cúi xuống nhặt ví",
            "required_pose": {"primitive": "kneel_pick",
                              "params": {}},
        }]
        records = detect_conflicts(
            cue_records=[{"cue": "bend_pick",
                          "source_shot_id": "SC01_SH01"}],
            compiled_events=events)
        self.assertEqual(records, [])

    def test_r1_fires_on_pocket_param_without_semantic_type(self):
        event = self._pocket_event()
        event["semantic_action_type"] = None
        records = detect_conflicts(
            cue_records=[{"cue": "bend_pick",
                          "source_shot_id": "SC01_SH01"}],
            compiled_events=[event])
        self.assertEqual(len(records), 1)

    def test_r1_unbound_cue_is_skipped_never_guessed(self):
        records = detect_conflicts(
            cue_records=[{"cue": "bend_pick"}],
            compiled_events=[self._pocket_event()])
        self.assertEqual(records, [])

    def test_r2_rain_vs_no_rain_resolves_to_parser(self):
        records = detect_conflicts(
            cue_records=[{"cue": "rain",
                          "source_shot_id": "SC01_SH01"}],
            compiled_events=[],
            unsupported=[{
                "directive_text": "Trời quang, không mưa.",
                "shot_id": "SC01_SH01", "scene_number": 1,
            }])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].level_b, "parser")
        self.assertEqual(records[0].winner_authority,
                         ActionAuthority.EXPLICIT_DIRECTIVE)
        self.assertFalse(records[0].fails_preflight)

    def test_r3_forbidden_pair_resolves_to_parser(self):
        records = detect_conflicts(
            semantic_actions=[{
                "action_type": "TAKE_FROM_POCKET",
                "source_directive_id": "SC01_SH01_ACT01",
                "source_text": "Lấy ví từ túi áo",
            }],
            compiled_events=[{
                "action_id": "SC01_SH01_ACT01",
                "action_type": "KNEEL_PICK",
                "shot_id": "SC01_SH01", "scene_number": 1,
            }])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].level_a, "parser")
        self.assertEqual(records[0].winner_authority,
                         ActionAuthority.EXPLICIT_DIRECTIVE)

    def test_r3_specialization_never_flags(self):
        # BEND_PICK compiling to KNEEL_PICK is a specialization,
        # not a contradiction.
        records = detect_conflicts(
            semantic_actions=[{
                "action_type": "BEND_PICK",
                "source_directive_id": "SC01_SH01_ACT01",
                "source_text": "Cúi xuống nhặt ví",
            }],
            compiled_events=[{
                "action_id": "SC01_SH01_ACT01",
                "action_type": "KNEEL_PICK",
                "shot_id": "SC01_SH01", "scene_number": 1,
            }])
        self.assertEqual(records, [])

    def test_r4_ground_staging_vs_pocket_location(self):
        records = detect_conflicts(
            staging_records=[{"rest": "ground",
                              "prop_id": "prop_wallet"}],
            prop_locations={"prop_wallet": "IN_POCKET"})
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].level_a, "shot_staging")
        self.assertEqual(records[0].winner_authority,
                         ActionAuthority.COMPILED_EVENT)
        self.assertFalse(records[0].fails_preflight)

    def test_r4_skips_unknown_and_on_ground(self):
        self.assertEqual(detect_conflicts(
            staging_records=[{"rest": "ground",
                              "prop_id": "prop_wallet"}],
            prop_locations={}), [])
        self.assertEqual(detect_conflicts(
            staging_records=[{"rest": "ground",
                              "prop_id": "prop_wallet"}],
            prop_locations={"prop_wallet": "ON_GROUND"}), [])

    def test_r5_primitive_substitution_unresolved(self):
        records = detect_conflicts(
            compiled_events=[{
                "action_id": "SC01_SH01_ACT01",
                "action_type": "KNEEL_PICK",
                "required_pose": {"primitive": "kneel_pick"},
            }],
            renderer_events=[{"action_id": "SC01_SH01_ACT01",
                              "primitive": "walk_to"}])
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0].winner_authority)
        self.assertTrue(records[0].fails_preflight)

    def test_r5_matching_primitive_is_clean(self):
        self.assertEqual(detect_conflicts(
            compiled_events=[{
                "action_id": "SC01_SH01_ACT01",
                "action_type": "KNEEL_PICK",
                "required_pose": {"primitive": "kneel_pick"},
            }],
            renderer_events=[{"action_id": "SC01_SH01_ACT01",
                              "primitive": "kneel_pick"}]), [])

    def test_check_cue_authorization_returns_resolved(self):
        records = check_cue_authorization(
            [self._pocket_event()],
            [{"cue": "bend_pick", "source_shot_id": "SC01_SH01"}])
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0].fails_preflight)

    def test_unauthorized_story_change_is_value_error(self):
        self.assertTrue(issubclass(UnauthorizedStoryChange,
                                   ValueError))


class TestMappingTotality(unittest.TestCase):
    def test_every_semantic_type_maps_to_a_compiler_verb(self):
        self.assertEqual(set(SEMANTIC_TO_COMPILER_VERB),
                         set(SEMANTIC_ACTION_TYPES))
        self.assertEqual(len(SEMANTIC_ACTION_TYPES), 34)

    def test_every_mapped_verb_exists(self):
        for sem_type, verb in SEMANTIC_TO_COMPILER_VERB.items():
            with self.subTest(sem_type=sem_type):
                self.assertIn(verb, ACTION_TYPES)

    def test_mapping_never_produces_a_forbidden_verb(self):
        for sem_type, verb in SEMANTIC_TO_COMPILER_VERB.items():
            forbidden = FORBIDDEN_SEMANTIC_COMPILATIONS.get(
                sem_type, frozenset())
            self.assertNotIn(verb, forbidden, sem_type)


class TestReceiverHand(unittest.TestCase):
    def _handover_gap(self, receive_hand, gap=170.0):
        giver = make_character_from_data(_cyclops_data(756))
        receiver = make_character_from_data(_zeus_data(560))
        P.standing(giver, 780.0, GROUND_Y, facing=1)
        P.standing(receiver, 780.0 + gap, GROUND_Y, facing=-1)
        prop = {"x": 780.0, "y": GROUND_Y - 200.0}
        fn = P.hand_over(giver, receiver, prop, 1.5,
                         receive_hand=receive_hand)
        for fi in range(int(1.5 * FPS) + 1):
            fn(fi / FPS)
        gj, rj = giver.joints(), receiver.joints()
        rh = rj["hand_" + receive_hand]
        return math.hypot(gj["hand_r"][0] - rh[0],
                          gj["hand_r"][1] - rh[1])

    def test_right_hand_handover_gap(self):
        self.assertLess(self._handover_gap("r"), 5.0)

    def test_right_hand_thin_lens_gap(self):
        self.assertLess(self._handover_gap("r", gap=320.0), 5.0)

    def test_default_hand_is_still_left(self):
        self.assertLess(self._handover_gap("l"), 5.0)

    def test_invalid_receive_hand_raises(self):
        giver = make_character_from_data(_cyclops_data(756))
        receiver = make_character_from_data(_zeus_data(560))
        with self.assertRaises(ValueError):
            P.hand_over(giver, receiver, {"x": 0, "y": 0}, 1.0,
                        receive_hand="x")

    def test_psm_transfer_uses_receiver_right_hand(self):
        props = [{"id": "prop_bolt", "name": "bolt", "kind": "bolt",
                  "owner": ""}]
        events = [
            {"action_id": "A1", "action_type": "HOLD",
             "actor_id": "CHAR_A", "prop_id": "prop_bolt",
             "start_time": 0.0, "end_time": 1.0,
             "shot_id": "SC01_SH01", "scene_number": 1,
             "required_pose": {"primitive": "hold",
                               "params": {"hand": "r"}},
             "semantic_action_type": "HOLD"},
            {"action_id": "A2", "action_type": "HAND_OVER",
             "actor_id": "CHAR_A", "target_id": "CHAR_B",
             "prop_id": "prop_bolt",
             "start_time": 1.0, "end_time": 2.5,
             "shot_id": "SC01_SH01", "scene_number": 1,
             "required_pose": {"primitive": "hand_over",
                               "params": {"receive_hand": "r"}},
             "semantic_action_type": "GIVE"},
        ]
        psm = PropStateMachine(props, events, staging={})
        joints = {"CHAR_A": {"hand_r": (100.0, 500.0),
                             "hand_l": (90.0, 500.0)},
                  "CHAR_B": {"hand_r": (300.0, 500.0),
                             "hand_l": (310.0, 500.0)}}
        x, y, _angle, state, hand = psm.transform_at(
            "prop_bolt", 2.5, joints)
        self.assertEqual(state, "ATTACHED_TO_HAND")
        self.assertEqual(hand, "r")
        self.assertEqual((x, y), (300.0, 500.0))

    def test_compiler_emits_receive_hand_params(self):
        pkg = _a2_package([
            "Ana đưa chiếc ví cho Ben.",
            "Ben nhận bằng tay phải.",
        ])
        events, _ = compile_actions(pkg, {})
        self.assertEqual(events[0]["action_type"], "HAND_OVER")
        self.assertEqual(
            events[0]["required_pose"]["params"]["receive_hand"], "r")
        self.assertEqual(events[1]["action_type"], "RECEIVE_PROP")
        self.assertEqual(
            events[1]["required_pose"]["params"]["hand"], "r")
        self.assertTrue(any(
            c.get("target_hand") == "r"
            for c in events[0]["contact_points"]))


class TestCrouchAndReceiveProp(unittest.TestCase):
    def test_crouch_drops_hips_feet_planted_returns_exact(self):
        char = Stickman(height=560)
        P.standing(char, 500, GROUND_Y, facing=1)
        start = char.joints()
        fn = P.crouch(char, 2.0, GROUND_Y)
        fn(0.0)
        hip0 = char.joints()["hip"]
        fn(1.0)
        mid = char.joints()
        self.assertAlmostEqual(mid["hip"][1] - hip0[1], 72.1,
                               delta=0.5)
        for foot in ("foot_l", "foot_r"):
            self.assertAlmostEqual(
                math.hypot(mid[foot][0] - start[foot][0],
                           mid[foot][1] - start[foot][1]),
                0.0, delta=0.01)
        self.assertAlmostEqual(mid["hip"][0] - hip0[0], 0.0,
                               delta=0.01)
        fn(2.0)
        end = char.joints()
        self.assertAlmostEqual(
            math.hypot(end["hip"][0] - hip0[0],
                       end["hip"][1] - hip0[1]),
            0.0, delta=0.01)

    def test_receive_prop_reaches_then_pulls_in(self):
        char = Stickman(height=560)
        P.standing(char, 500, GROUND_Y, facing=1)
        fn = P.receive_prop(char, (580.0, 580.0), 1.5, hand="r")
        fn(0.9)  # RECEIVE_REACH_U: full reach
        mid = char.joints()
        self.assertLess(
            math.hypot(mid["hand_r"][0] - 580.0,
                       mid["hand_r"][1] - 580.0), 1.0)
        fn(1.5)
        end = char.joints()
        pull = math.hypot(end["hand_r"][0] - 580.0,
                          end["hand_r"][1] - 580.0)
        self.assertGreater(pull, 5.0)
        self.assertLess(pull, 40.0)

    def test_primitives_in_registry_dispatch_and_completion(self):
        self.assertIn("crouch", P.PRIMITIVES)
        self.assertIn("receive_prop", P.PRIMITIVES)
        self.assertIn("crouch", P.PRIMITIVE_COMPLETION)
        self.assertIn("receive_prop", P.PRIMITIVE_COMPLETION)
        chars = {"A": Stickman(height=560)}
        P.standing(chars["A"], 500, GROUND_Y, facing=1)
        timeline = P.compile_actions([
            {"type": "crouch", "char": "A", "start": 0.0,
             "duration": 2.0, "ground_y": GROUND_Y},
            {"type": "receive_prop", "char": "A", "start": 2.0,
             "duration": 1.0, "target": (580.0, 580.0),
             "hand": "r"},
        ], chars, fps=FPS)
        self.assertEqual(len(timeline), 73)  # 3s at 24fps + 1


class TestNewCompilerVerbs(unittest.TestCase):
    def test_crouch_receive_open_close_board(self):
        cases = (
            ("Ana cúi người tránh tiếng pháo.", "CROUCH", "CROUCH"),
            ("Ana nhận chiếc ví bằng tay phải.", "RECEIVE_PROP",
             "RECEIVE_PROP"),
            ("Ana mở cửa ra.", "OPEN", "OPEN"),
            ("Ana đóng nắp hộp lại.", "CLOSE", "CLOSE"),
            ("Ana bước lên xe buýt.", "BOARD", "BOARD"),
        )
        for text, verb, sem in cases:
            with self.subTest(text=text):
                events, unsupported = compile_actions(
                    _a2_package([text]), {})
                self.assertEqual(unsupported, [])
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["action_type"], verb)
                self.assertEqual(events[0]["semantic_action_type"],
                                 sem)

    def test_bare_kneel_is_not_a_pickup(self):
        events, unsupported = compile_actions(
            _a2_package(["Ana quỳ xuống."]), {})
        self.assertEqual(events, [])
        self.assertEqual(unsupported[0]["category"], "UNCLEAR")

    def test_kneel_pickup_still_fires(self):
        events, _ = compile_actions(
            _a2_package(["Ana quỳ xuống nhặt chiếc ví."]), {})
        self.assertEqual(events[0]["action_type"], "KNEEL_PICK")
        self.assertEqual(events[0]["semantic_action_type"],
                         "BEND_PICK")

    def test_take_fallback_and_exclusions(self):
        events, _ = compile_actions(
            _a2_package(["Ana lấy bút trên bàn."]), {})
        self.assertEqual(events[0]["action_type"], "PICK_UP")
        self.assertEqual(events[0]["semantic_action_type"],
                         "PICK_FROM_SURFACE")
        events, unsupported = compile_actions(
            _a2_package(["Ana lấy làm tiếc."]), {})
        self.assertEqual(events, [])
        self.assertEqual(unsupported[0]["category"], "UNCLEAR")

    def test_phenomenon_subject_is_environment(self):
        events, unsupported = compile_actions(
            _a2_package(["Điện chạy nhẹ quanh cánh tay."]), {})
        self.assertEqual(events, [])
        self.assertEqual(unsupported[0]["category"], "ENVIRONMENT")

    def test_split_take_from_pocket(self):
        events, _ = compile_actions(
            _a2_package(["Ana rút điện thoại từ túi quần."]), {})
        self.assertEqual(events[0]["action_type"], "TAKE_OUT")
        self.assertEqual(events[0]["semantic_action_type"],
                         "TAKE_FROM_POCKET")


class TestMentionBridge(unittest.TestCase):
    ZEUS_PROPS = [
        {"id": "prop_lightning", "name": "PROP_LIGHTNING",
         "kind": "generic",
         "description": "Divine lightning bolt Electric blue and "
                        "golden white"},
        {"id": "prop_forge_hammer", "name": "PROP_FORGE_HAMMER",
         "kind": "generic",
         "description": "Giant blacksmith hammer"},
        {"id": "prop_trident", "name": "PROP_TRIDENT",
         "kind": "generic", "description": "Divine trident"},
    ]

    def test_english_described_props_match_vietnamese_mentions(self):
        pkg = _a2_package([
            "Ana nâng búa.",
            "Ana đưa tia sét cho Ben.",
            "Ana cầm đinh ba.",
        ], props=self.ZEUS_PROPS)
        events, _ = compile_actions(pkg, {})
        by_text = {e["directive_text"]: e for e in events}
        self.assertEqual(
            by_text["Ana nâng búa"]["prop_id"],
            "prop_forge_hammer")
        self.assertEqual(
            by_text["Ana nâng búa"]["action_type"],
            "HAMMER_STRIKE")
        self.assertEqual(
            by_text["Ana đưa tia sét cho Ben"]["prop_id"],
            "prop_lightning")
        self.assertEqual(
            by_text["Ana cầm đinh ba"]["prop_id"], "prop_trident")

    def test_receive_inherits_shot_handover_prop(self):
        pkg = _a2_package([
            "Ana đưa tia sét cho Ben.",
            "Ben nhận bằng tay phải.",
        ], props=self.ZEUS_PROPS)
        events, _ = compile_actions(pkg, {})
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["action_type"], "RECEIVE_PROP")
        self.assertEqual(events[1]["prop_id"], "prop_lightning")
        self.assertTrue(any(
            "handover prop" in note for note in events[1]["notes"]))




if __name__ == "__main__":
    unittest.main()
