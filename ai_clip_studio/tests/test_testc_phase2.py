"""TEST C Phase 2 regression tests (F1-F4, F6, F10).

Every test asserts a MEASUREMENT from the real rig / renderer / real
rendered pixels -- pose angles, head/frame ratios, hand gaps, face
geometry, bus feature pixels, run flight phase -- never a constant
copied from the implementation. Baselines are the Phase 1
measurements (BAO_CAO_TEST_C.md) and the pre-fix values recorded in
the Phase 2 report.
"""
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import (
    EXPRESSIONS, STYLE_LOCK, _face_eye_xs, _separate_close_hands,
    draw_character_v4, make_character_instance)
from ai_clip_studio.animation.primitives import (
    kneel_pick, plant_feet, run_to, standing, walk_to)
from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.camera_planner import CameraPlanner

H = 783.0
GY = 892.0


def _run(fn, c, dur, fps=24):
    rows = []
    for fi in range(int(dur * fps) + 1):
        fn(fi / fps)
        rows.append((fi / fps, c.joints(), dict(c.pose)))
    return rows


def _angle(a, b, c):
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    d = math.hypot(*v1) * math.hypot(*v2)
    if d == 0:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0]
                                                     + v1[1] * v2[1]) / d))))


def _seg_dist(p1, p2, p3, p4):
    def _pt_seg(p, a, b):
        ax, ay = a
        bx, by = b
        px, py = p
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx
                                                   + (py - ay) * dy) / l2))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
    return min(_pt_seg(p1, p3, p4), _pt_seg(p2, p3, p4),
               _pt_seg(p3, p1, p2), _pt_seg(p4, p1, p2))


def _lean(J):
    return math.degrees(math.atan2(J["shoulder"][0] - J["hip"][0],
                                   J["hip"][1] - J["shoulder"][1]))


class TestKneelF1(unittest.TestCase):
    """F1: the kneel reads as a person bending to pick something up,
    not a knot. Phase 1 baseline: lean 52.7 deg, shins 42.5 px apart,
    front knee 75.9 deg, head top 50.9% of standing height."""

    def _kneel_rows(self, rx, tx):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=rx, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        fn = kneel_pick(c, (tx, GY - 6), 1.4, GY)
        return c, _run(fn, c, 1.4)

    def _hold(self, rows):
        return [J for t, J, _ in rows if 0.7 <= t <= 0.91]

    def test_kneel_lean_near_47_degrees(self):
        _, rows = self._kneel_rows(918, 1001)
        leans = [_lean(J) for _, J, _ in rows]
        self.assertGreater(max(leans), 45.0,
                           f"kneel too upright: {max(leans):.1f} deg")
        self.assertLess(max(leans), 50.0,
                        f"kneel still bows: {max(leans):.1f} deg "
                        f"(Phase 1: 52.7)")

    def test_kneel_shins_separated(self):
        _, rows = self._kneel_rows(918, 1001)
        gaps = [_seg_dist(J["knee_l"], J["foot_l"],
                          J["knee_r"], J["foot_r"])
                for J in self._hold(rows)]
        self.assertGreaterEqual(min(gaps), 65.0,
                                f"shins still knotted: min gap "
                                f"{min(gaps):.1f}px (Phase 1: 42.5)")

    def test_kneel_front_knee_open(self):
        _, rows = self._kneel_rows(918, 1001)
        angs = [_angle(J["hip"], J["knee_r"], J["foot_r"])
                for J in self._hold(rows)]
        self.assertGreaterEqual(min(angs), 90.0,
                                f"front knee still folded: "
                                f"{min(angs):.1f} deg (Phase 1: 75.9)")

    def test_kneel_back_knee_on_ground_folded(self):
        # The back knee stays folded (~33 deg): a kneel's shin lies
        # flat on the ground, and the knee-on-ground + reach
        # constraints pin the fold (see kneel_pick docstring: 0/144
        # grid combos reach 55 deg). Pin the honest geometry so a
        # future change cannot silently sink the knee or unfold it
        # into a stoop.
        _, rows = self._kneel_rows(918, 1001)
        for J in self._hold(rows):
            gap = GY - J["knee_l"][1]
            self.assertGreaterEqual(gap, -2.0,
                                    f"back knee below ground: {gap:.1f}")
            self.assertLessEqual(gap, 20.0,
                                 f"back knee floats: {gap:.1f}")
            ang = _angle(J["hip"], J["knee_l"], J["foot_l"])
            self.assertGreaterEqual(ang, 25.0,
                                    f"back knee over-folded: {ang:.1f}")
            self.assertLessEqual(ang, 45.0,
                                  f"back knee unfolded: {ang:.1f}")

    def test_kneel_reaches_distant_prop_by_stepping_in(self):
        # Product staging: the prop is 220 px ahead of the root. The
        # kneel steps forward (adaptive root shift) so the hand still
        # lands exactly on the prop at the lower lean.
        c, rows = self._kneel_rows(900, 1120)
        for J in self._hold(rows):
            err = math.hypot(J["hand_r"][0] - 1120,
                             J["hand_r"][1] - (GY - 6))
            self.assertLessEqual(err, 5.0,
                                 f"hand misses the prop by {err:.1f}px")
        hold_roots = [p["root_x"] for t, _, p in rows if 0.7 <= t <= 0.91]
        self.assertGreater(min(hold_roots), 900 + 30,
                           "root did not step toward the prop")
        # ... and returns to its start on the rise.
        _, _, last_pose = rows[-1]
        self.assertAlmostEqual(last_pose["root_x"], 900, delta=1.0)

    def test_kneel_head_stays_high(self):
        c, rows = self._kneel_rows(918, 1001)
        fracs = [(GY - (J["head"][1] - c.head_r)) / H
                 for J in self._hold(rows)]
        self.assertGreaterEqual(min(fracs), 0.54,
                                f"head top only {min(fracs):.3f} of "
                                f"standing (Phase 1: 0.509)")


class TestZoomCapF2(unittest.TestCase):
    """F2: full-body action shots never inflate mid-shot. Phase 1:
    heads inflated to 358 px = 33% of frame height by a 1.0x -> 1.6x
    zoom pump as the character kneeled."""

    def test_max_scale_caps_the_ladder(self):
        shot = {"shot_type": "medium",
                "camera": {"scale": 3.4}}
        focus = (960, 540)
        # A tiny subject fits at every scale -- without a cap the
        # ladder stays at the planned 3.4x.
        subjects = [{"cx": 960, "head_y": 500, "foot_y": 580,
                     "half_w": 40}]
        capped, _, _ = CameraPlanner.safe_frame(
            shot, focus, subjects, max_scale=1.0)
        self.assertEqual(capped["camera"]["scale"], 1.0)
        free, _, _ = CameraPlanner.safe_frame(shot, focus, subjects)
        self.assertEqual(free["camera"]["scale"], 3.4)

    def test_standing_box_gives_constant_scale_across_kneel(self):
        # The F2 rule: the full-body subject box is the STANDING
        # extent (ground-anchored), so a kneel hold and a standing
        # pose produce the same box height and the same scale.
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=918, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        fn = kneel_pick(c, (1001, GY - 6), 1.4, GY)
        scales = []
        for fi in range(int(1.4 * 24) + 1):
            fn(fi / 24)
            J = c.joints()
            box = {"cx": J["head"][0], "head_y": GY - H,
                   "foot_y": GY, "half_w": 160}
            shot = {"shot_type": "medium",
                    "camera": {"scale": 1.6}}
            safe, _, _ = CameraPlanner.safe_frame(
                shot, (J["head"][0], J["head"][1]), [box],
                max_scale=1.0)
            scales.append(safe["camera"]["scale"])
        self.assertTrue(all(s == 1.0 for s in scales),
                        f"scale pumped mid-kneel: {sorted(set(scales))}")

    def test_kneel_shot_head_never_inflates(self):
        # Real render path: a short kneel shot, every frame. The
        # cream face blob's width must stay at the 1.0x size in
        # EVERY frame (no 1.6x pump at the hold) and under the 26%
        # head cap (the full head is the cream + the outline ring).
        from ai_clip_studio.product_renderer import _render_shot
        from ai_clip_studio.product_flow import plan_shots
        from ai_clip_studio.tests.test_product_flow import TestShotPlanSync
        pkg = TestShotPlanSync()._pkg()
        timeline = TestShotPlanSync()._timeline()
        shots = plan_shots(pkg, timeline)
        bend = next(s for s in shots if s["kind"] == "action"
                    and s.get("action_cues") == ["bend_pick"])
        with tempfile.TemporaryDirectory() as tmp:
            res = _render_shot(
                {"shot": dict(bend, index=1, duration=0.5),
                 "package": pkg, "out_dir": Path(tmp)})
            widths = []
            for fpath in res["frames"]:
                arr = np.asarray(Image.open(fpath).convert("RGB")
                                 ).astype(int)
                cream = ((arr[:, :, 0] > 235) & (arr[:, :, 1] > 230)
                         & (arr[:, :, 2] > 215))
                ys, xs = np.nonzero(cream)
                widths.append(int(xs.max() - xs.min()))
        self.assertGreater(len(widths), 5, "too few frames rendered")
        self.assertLessEqual(max(widths), 240,
                             f"head inflated to {max(widths)}px cream "
                             f"width (1.0x is ~222px, 1.6x is ~355px)")
        self.assertLessEqual(max(widths) - min(widths), 15,
                             f"head size pumped across the shot: "
                             f"{min(widths)}..{max(widths)}px")


class TestHandSeparationF3(unittest.TestCase):
    """F3: hands stay distinct, fingers readable. Phase 1 baseline:
    hand_gap_min 0.0 px, 3x55 px fingers interleaving into a
    6-finger scribble."""

    def test_coincident_hands_separate(self):
        hl, el, scale, fan, fw = _separate_close_hands(
            (500.0, 600.0), (500.0, 600.0), (480.0, 500.0), 1, H)
        gap = math.hypot(hl[0] - 500.0, hl[1] - 600.0)
        self.assertAlmostEqual(gap, 0.045 * H, delta=1.0)
        self.assertEqual(scale, 0.6)
        self.assertEqual(fan, 1.0)
        self.assertEqual(fw, 0.7)
        # Pushed backward (opposite facing) + up, never forward.
        self.assertLess(hl[0], 500.0)
        self.assertLess(hl[1], 600.0)
        # Elbow is never moved (the upper arm stays hidden behind the
        # near arm; the forearms form a V from the shared elbow).
        self.assertEqual(el, (480.0, 500.0))

    def test_close_hands_ahead_still_separate(self):
        # Far hand 20 px AHEAD of the near hand: the biased push must
        # still leave two distinct wrists (no pop, no merge).
        hl, _, scale, _fan, _fw = _separate_close_hands(
            (520.0, 600.0), (500.0, 600.0), (500.0, 500.0), 1, H)
        gap = math.hypot(hl[0] - 500.0, hl[1] - 600.0)
        self.assertGreaterEqual(gap, 15.0)
        self.assertEqual(scale, 0.6)

    def test_far_apart_hands_untouched(self):
        hl, el, scale, fan, fw = _separate_close_hands(
            (600.0, 600.0), (500.0, 600.0), (580.0, 500.0), 1, H)
        self.assertEqual(hl, (600.0, 600.0))
        self.assertEqual(el, (580.0, 500.0))
        self.assertEqual(scale, 1.0)
        self.assertEqual(fan, 1.0)
        self.assertEqual(fw, 1.0)

    def test_separation_is_continuous_across_crossing(self):
        # As the far hand sweeps through the near hand, the DRAWN
        # position must move smoothly -- no >2*sep pop at the
        # crossing (the biased push direction never flips).
        prev = None
        worst = 0.0
        for dx in range(-40, 41, 2):
            hl, _, _, _, _ = _separate_close_hands(
                (500.0 + dx, 600.0), (500.0, 600.0),
                (480.0 + dx, 500.0), 1, H)
            if prev is not None:
                worst = max(worst, math.hypot(hl[0] - prev[0],
                                              hl[1] - prev[1]))
            prev = hl
        self.assertLessEqual(worst, 6.0,
                             f"far hand pops {worst:.1f}px per 2px step")

    def test_walk_cycle_drawn_hands_never_coincide(self):
        # Across a full walk cycle the DRAWN far hand (after
        # separation) is never within 10 px of the near hand.
        c = make_character_instance("minh", height=H)
        fn = walk_to(c, 125, 570, 2.1, GY)
        worst = 1e9
        for fi in range(int(2.1 * 24) + 1):
            fn(fi / 24)
            J = c.joints()
            hl, _, _, _, _ = _separate_close_hands(
                J["hand_l"], J["hand_r"], J["elbow_l"],
                J["facing"], H)
            worst = min(worst, math.hypot(hl[0] - J["hand_r"][0],
                                          hl[1] - J["hand_r"][1]))
        self.assertGreaterEqual(worst, 10.0,
                                f"drawn hands coincide: gap {worst:.1f}")


class TestFaceF4(unittest.TestCase):
    """F4: no stray brows on the hair, no mouth/eye overlap, no
    expression misfires. Phase 1: mouth overlapped the far eye by
    0.13r, brows at 0.74-0.78r above head centre, gentle lines
    showing shocked faces."""

    def _render_face(self, expression, view, facing):
        ch = make_character_instance("minh", height=560)
        standing(ch, 300, 620, facing=facing)
        img = Image.new("RGB", (600, 700), (255, 255, 255))
        d = ImageDraw.Draw(img, "RGBA")
        J = draw_character_v4(d, ch, expression=expression, view=view)
        return np.asarray(img).astype(int), J, ch.head_r

    def test_no_brow_above_the_hairline(self):
        # The strip between the hairline and the brow band must be
        # empty: at |x-hx| <= 0.30r the hairline is at -0.82r or
        # higher and the head outline is above -0.95r, so any ink in
        # [-0.80r, -0.55r] is a stray brow. The old surprised brows
        # (-0.74..-0.78r) landed exactly here.
        for expr in EXPRESSIONS:
            for view in ("profile", "three_quarter", "front"):
                for facing in (1, -1):
                    arr, J, r = self._render_face(expr, view, facing)
                    hx, hy = J["head"]
                    dark = arr.sum(axis=2) < 400
                    x0, x1 = int(hx - 0.30 * r), int(hx + 0.30 * r)
                    # Strip ends at -0.58r: the clamped brow line sits
                    # at -0.55r and its top edge must stay out.
                    y0, y1 = int(hy - 0.80 * r), int(hy - 0.58 * r)
                    n = int(dark[y0:y1, x0:x1].sum())
                    # <=5 px is anti-aliasing noise from the hairline /
                    # outline edge; a real stray brow is a 20+ px line.
                    self.assertLessEqual(
                        n, 5,
                        f"stray brow ink ({n}px) for {expr}/{view}/"
                        f"facing {facing}")

    def test_brows_present_except_neutral(self):
        # The fix must clamp brows, not delete them: every expression
        # that moves the brows still shows brow ink in the brow band.
        for expr in EXPRESSIONS:
            arr, J, r = self._render_face(expr, "profile", 1)
            hx, hy = J["head"]
            dark = arr.sum(axis=2) < 400
            x0, x1 = int(hx - 0.6 * r), int(hx + 0.6 * r)
            # Band between the hairline (-0.72r) and the tallest eye
            # top (-0.341r for surprised): brows live here, nothing
            # else does (eyes stay below -0.341r, hair above -0.72r).
            y0, y1 = int(hy - 0.60 * r), int(hy - 0.38 * r)
            n = int(dark[y0:y1, x0:x1].sum())
            if expr == "neutral":
                # <=3 px is anti-aliasing noise; a real brow is 20+ px.
                self.assertLessEqual(n, 3,
                                     f"neutral grew brows ({n}px)")
            else:
                self.assertGreater(n, 5, f"{expr} lost its brows")

    def test_surprised_mouth_clears_the_eyes(self):
        # Mouth top must sit below the far eye's bottom with a clear
        # gap, in every view/facing. The old mouth overlapped the
        # far eye by 0.13r.
        for view, face_dx in (("profile", 1.0), ("three_quarter", 0.5),
                              ("front", 0.0)):
            for facing in (1, -1):
                arr, J, r = self._render_face("surprised", view, facing)
                hx, hy = J["head"]
                dark = arr.sum(axis=2) < 400
                ex_near, ex_far, fc = _face_eye_xs(hx, r, facing, face_dx)
                # Eye bottom: the LOWEST ink in either eye's centre
                # column, within the eye band only (the mouth sits
                # under one eye in profile, so an open-ended column
                # would measure the mouth, not the eye). The tallest
                # eye bottom is +0.341r (surprised); the band ends
                # at +0.36r, above the fixed mouth top (+0.391r).
                eye_bottom = None
                for ex in (ex_near, ex_far):
                    exi = int(round(ex))
                    col = dark[int(hy - 0.5 * r):int(hy + 0.36 * r),
                               exi - 1:exi + 2]
                    rows = np.nonzero(col.any(axis=1))[0]
                    bot = hy - 0.5 * r + rows.max()
                    eye_bottom = bot if eye_bottom is None \
                        else max(eye_bottom, bot)
                # Mouth top: highest ink in the mouth's column, offset
                # 0.04r toward the face centre so the column stays
                # inside the "O" but clear of the eye it used to
                # touch (in profile the mouth sits under the forward
                # eye; the centre column grazes the eye's edge when
                # facing left).
                mx = hx + fc + facing * face_dx * 0.10 * r
                mx = int(round(mx - facing * 0.04 * r))
                band = dark[int(hy + 0.1 * r):int(hy + 0.9 * r),
                            mx - 1:mx + 2]
                mouth_rows = np.nonzero(band.any(axis=1))[0]
                mouth_top = hy + 0.1 * r + mouth_rows.min()
                gap = (mouth_top - eye_bottom) / r
                self.assertGreaterEqual(
                    gap, 0.03,
                    f"mouth/eye gap {gap:.3f}r for surprised/{view}/"
                    f"facing {facing} (old code: -0.13r)")

    def test_expression_keywords_use_word_boundaries(self):
        from ai_clip_studio.product_renderer import expression_for
        cases = [
            ("Bà ơi, bà cầm ô của cháu đi.", "neutral"),
            ("Cái ví của Lan.", "neutral"),
            ("Xin lỗi cô.", "neutral"),
            ("Ủa, sao lại thế?", "surprised"),
            ("Ôi trời ơi!", "surprised"),
            ("Ngạc nhiên chưa!", "surprised"),
            ("Con lo quá.", "worried"),
            ("Mẹ vui lắm.", "happy"),
            ("Cháu cười tươi.", "happy"),
            ("Cô ấy khóc.", "sad"),
            ("Anh ấy tức giận.", "angry"),
        ]
        for text, want in cases:
            self.assertEqual(expression_for(text), want, repr(text))


class TestBusF6(unittest.TestCase):
    """F6: the bus reads as a bus -- wheels, door, lights, sign,
    stripe -- and a 'board' cue implies a bus even when the scene
    cues forget it."""

    def test_bus_overlay_draws_all_features(self):
        from ai_clip_studio.product_renderer import (
            BUS_BODY_CENTER, BUS_BODY_SIZE, BUS_DOOR_X, BUS_WHEEL_X,
            CAM, H as PH, W as PW, _draw_bus_details)
        img = Image.new("RGB", (PW, PH), (10, 12, 18))
        _draw_bus_details(img)
        arr = np.asarray(img).astype(int)
        cx, cy, cz = BUS_BODY_CENTER
        sx_, sy_, sz_ = BUS_BODY_SIZE
        zf = cz + sz_ / 2.0
        pts = [CAM.project((cx + dx * sx_ / 2.0, cy + dy * sy_ / 2.0,
                            zf), PW, PH)
               for dx in (-1, 1) for dy in (-1, 1)]
        left = min(p[0] for p in pts)
        right = max(p[0] for p in pts)
        top = min(p[1] for p in pts)
        bottom = max(p[1] for p in pts)
        w, h = right - left, bottom - top
        # Wheels: dark discs with light hubs at the projected spots.
        for wx in BUS_WHEEL_X:
            wcx, _, _, _ = CAM.project((wx, 0.15, zf), PW, PH)
            wcy = bottom - 0.02 * h
            x0, x1 = int(wcx - 12), int(wcx + 12)
            y0, y1 = int(wcy - 12), int(wcy + 12)
            patch = arr[y0:y1, x0:x1]
            self.assertGreater(int((patch.sum(axis=2) < 60).sum()), 50,
                               f"no dark wheel at x={wcx:.0f}")
            self.assertGreater(int((patch.sum(axis=2) > 550).sum()), 10,
                               f"no light hubcap at x={wcx:.0f}")
        # Headlight: bright pixels at the front-bottom corner.
        hlx, hly = left + 0.045 * w, bottom - 0.10 * h
        patch = arr[int(hly - 10):int(hly + 10),
                    int(hlx - 10):int(hlx + 10)]
        self.assertGreater(int((patch.sum(axis=2) > 650).sum()), 20,
                           "no bright headlight")
        # Destination sign: amber pixels in the sign bar.
        sx0, sy0 = left + 0.05 * w, top + 0.06 * h
        patch = arr[int(sy0):int(sy0 + 0.075 * h),
                    int(sx0):int(sx0 + 0.22 * w)]
        amber = ((patch[:, :, 0] > 200) & (patch[:, :, 1] > 150)
                 & (patch[:, :, 2] < 130))
        self.assertGreater(int(amber.sum()), 200, "no amber sign bar")
        # Stripe: light pixels along the sill band.
        sy = int(top + 0.52 * h)
        band = arr[sy:sy + 8, int(left + w * 0.3):int(left + w * 0.7)]
        self.assertGreater(int((band.sum(axis=2) > 650).sum()), 100,
                           "no light side stripe")
        # Door outline: light pixels on the door frame's left edge.
        dx0, _, _, _ = CAM.project((BUS_DOOR_X - 0.25, 0.2, zf), PW, PH)
        _, dy0, _, _ = CAM.project((BUS_DOOR_X, 1.6, zf), PW, PH)
        _, dy1, _, _ = CAM.project((BUS_DOOR_X, 0.2, zf), PW, PH)
        edge = arr[int(dy0) + 5:int(dy1) - 5,
                   int(dx0) - 2:int(dx0) + 3]
        self.assertGreater(int((edge.sum(axis=2) > 650).sum()), 20,
                           "no door outline")

    def test_board_cue_implies_bus_in_render(self):
        # The fixture's scene 3 has "board" but no "bus" in any cue
        # list: the rendered board still must show the bus WITH its
        # F6 overlay details. Asserted on the overlay's exact colours
        # (the 3D body colour is shading-dependent): the light stripe
        # on the body's clear right portion, the right wheel's light
        # hubcap, and the bright headlight. The board shot is a
        # tracking shot at 1.0x (F2 cap), so full-frame projected
        # coordinates apply directly — projected with the SHOT
        # camera from the render report (Stage 3 / F9: every shot
        # resolves its own viewpoint; the legacy fixed CAM no longer
        # renders anything).
        from ai_clip_studio.camera_planner import PerspectiveCamera
        from ai_clip_studio.product_renderer import (
            BUS_BODY_CENTER, BUS_BODY_SIZE, BUS_WHEEL_X,
            H as PH, W as PW, _render_shot)
        from ai_clip_studio.product_flow import plan_shots
        from ai_clip_studio.tests.test_product_flow import TestShotPlanSync
        pkg = TestShotPlanSync()._pkg()
        shots = plan_shots(pkg, TestShotPlanSync()._timeline())
        board = next(s for s in shots if s["kind"] == "action"
                     and s.get("action_cues") == ["board"])
        self.assertNotIn("bus", list(board.get("scene_cues") or [])
                         + list(board.get("action_cues") or []))
        with tempfile.TemporaryDirectory() as tmp:
            rep = _render_shot({"shot": dict(board, index=2),
                                "package": pkg,
                                "out_dir": Path(tmp), "still_only": True})
            arr = np.asarray(Image.open(
                Path(tmp) / "shot_002" / "still.png").convert("RGB")
            ).astype(int)
        self.assertEqual(rep["applied_scale"], 1.0,
                         "board still must be uncropped for direct "
                         "projection")
        CAM = PerspectiveCamera(position=rep["camera_position"],
                                target=rep["camera_target"])
        cx, cy, cz = BUS_BODY_CENTER
        sx_, sy_, sz_ = BUS_BODY_SIZE
        zf = cz + sz_ / 2.0
        pts = [CAM.project((cx + dx * sx_ / 2.0, cy + dy * sy_ / 2.0,
                            zf), PW, PH)
               for dx in (-1, 1) for dy in (-1, 1)]
        left = min(p[0] for p in pts)
        right = max(p[0] for p in pts)
        top = min(p[1] for p in pts)
        bottom = max(p[1] for p in pts)
        w, h = right - left, bottom - top
        # Stripe on the clear right portion (left of it Lan stands).
        sy = int(top + 0.52 * h)
        band = arr[sy:sy + 8, int(left + 0.75 * w):int(left + 0.95 * w)]
        self.assertGreater(int((band.sum(axis=2) > 650).sum()), 100,
                           "no bus stripe in the board still")
        # Right wheel hubcap.
        wcx, _, _, _ = CAM.project((BUS_WHEEL_X[1], 0.15, zf), PW, PH)
        wcy = bottom - 0.02 * h
        patch = arr[int(wcy) - 12:int(wcy) + 12,
                    int(wcx) - 12:int(wcx) + 12]
        self.assertGreater(int((patch.sum(axis=2) > 550).sum()), 10,
                           "no wheel hubcap in the board still")
        # Headlight.
        hlx, hly = left + 0.045 * w, bottom - 0.10 * h
        patch = arr[int(hly) - 10:int(hly) + 10,
                    int(hlx) - 10:int(hlx) + 10]
        self.assertGreater(int((patch.sum(axis=2) > 650).sum()), 20,
                           "no headlight in the board still")


class TestRunF10(unittest.TestCase):
    """F10: the run reads as a run in a still frame. Walk baselines
    (same measurement): lean 6.9 deg, flight 0%, arm 22.1 deg,
    swing-knee tuck 105.9 deg."""

    def _gait_rows(self, fn, dur):
        c = Stickman(height=H, name="minh")
        c.set_pose(root_x=500, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        plant_feet(c, GY)
        return _run(fn(c), c, dur)

    def test_run_leans_forward(self):
        rows = self._gait_rows(lambda c: run_to(c, 500, 1300, 1.5, GY),
                               1.5)
        mid = [J for _, J, _ in rows[6:-6]]
        leans = [_lean(J) for J in mid]
        self.assertGreaterEqual(max(leans), 18.0,
                                f"run stays upright: {max(leans):.1f} "
                                f"deg (walk: 6.9)")

    def test_run_has_real_flight_phase(self):
        rows = self._gait_rows(lambda c: run_to(c, 500, 1300, 1.5, GY),
                               1.5)
        mid = [J for _, J, _ in rows[6:-6]]
        air = sum(1 for J in mid
                  if J["foot_l"][1] < GY - 3 and J["foot_r"][1] < GY - 3)
        self.assertGreaterEqual(air / len(mid), 0.15,
                                f"flight fraction {air / len(mid):.2f} "
                                f"(walk: 0.00)")

    def test_run_arm_drive(self):
        rows = self._gait_rows(lambda c: run_to(c, 500, 1300, 1.5, GY),
                               1.5)
        mid = [J for _, J, _ in rows[6:-6]]
        worst = 0.0
        for J in mid:
            for s in ("l", "r"):
                dx = J[f"hand_{s}"][0] - J["shoulder"][0]
                dy = J[f"hand_{s}"][1] - J["shoulder"][1]
                worst = max(worst, abs(math.degrees(
                    math.atan2(dx, dy))))
        self.assertGreaterEqual(worst, 35.0,
                                f"arm drive only {worst:.1f} deg "
                                f"(walk: 22.1)")

    def test_run_swing_knee_tucks(self):
        rows = self._gait_rows(lambda c: run_to(c, 500, 1300, 1.5, GY),
                               1.5)
        mid = [J for _, J, _ in rows[6:-6]]
        tucks = []
        for J in mid:
            for s in ("l", "r"):
                if J[f"foot_{s}"][1] < GY - 3:
                    tucks.append(_angle(J["hip"], J[f"knee_{s}"],
                                        J[f"foot_{s}"]))
        self.assertTrue(tucks, "no airborne swing frames found")
        self.assertLessEqual(min(tucks), 100.0,
                             f"swing knee never tucks: min "
                             f"{min(tucks):.1f} deg (walk: 105.9)")


if __name__ == "__main__":
    unittest.main()
