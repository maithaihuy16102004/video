"""Animation v7 tests -- the 90% rubric round (2026-11-11).

Mai's verdict on motion test v6: still not satisfied, keep fixing
against the RicksClips reference until the work scores >= 90% on
camera angles, character, animation and effects. The v7 rubric
(acceptance_loop/audit_animation_v7/rubric_v7.py) scores v6 at 68.1%
overall (A 55.6 / B 75.0 / C 75.0 / D 66.7). These tests pin the v7
engine fixes that close the failing rubric items:

  * kneel: lean 63 -> 53 deg, head 35% -> 42% of standing height, and
    the back knee no longer clips 30 px BELOW the ground (the v7 hip
    0.55*u_leg coupled with the v6 back-foot tuck 0.30*l_leg put the
    knee through the floor; the tuck is now 0.16*l_leg);
  * settle gather: a walk's settle STEPS the feet (lifted) into the
    canonical standing split instead of freezing them mid-stride, so
    the next segment's blend does not slide them along the ground;
  * canonical stand split: plant_feet / idle / walk all use
    +/-0.125H (was 0.06H / +/-45 px / +/-0.125H -- three different
    spreads, one slide per blend);
  * kneel feet travel on lift arcs, never along the ground;
  * safe_frame: the camera planner can no longer repeat the v4/v5
    framing defects (3.4x inserts slicing heads, reactions that do
    not fit) -- it zooms out a step instead of shipping a head-cut;
  * Box3D labels: a sign box renders readable text;
  * character identity: Lan is slim with a dress, Minh is sturdy.

They assert on the RIG / the planner / rendered pixels, not on a
video, so they run in milliseconds.
"""
import math
import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import (
    CHARACTER_INSTANCES, draw_character_v4, make_character_instance)
from ai_clip_studio.animation.primitives import (
    idle, kneel_pick, run_to, walk_to)
from ai_clip_studio.animation.rig import (
    STAND_SPLIT_FRAC, plant_feet)
from ai_clip_studio.camera_planner import CameraPlanner, validate_framing
from ai_clip_studio.renderer25d.camera import PerspectiveCamera
from ai_clip_studio.renderer25d.render import render_frame
from ai_clip_studio.renderer25d.scene import Box3D, Scene25D

GY = 900
H = 783


def _run(fn, c, dur, fps=24):
    rows = []
    for fi in range(int(dur * fps) + 1):
        fn(fi / fps)
        rows.append((fi / fps, c.joints(), dict(c.pose)))
    return rows


def _standing_head_height(c):
    return GY - c.joints()["head"][1]


class TestKneelV7(unittest.TestCase):
    """v7 kneel: 53 deg lean, head ~42% of standing, knee on the ground
    (never below it), hand still holds the wallet 9 frames."""

    def _kneel_rows(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=918, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        fn = kneel_pick(c, (1001, GY - 6), 1.4, GY)
        return c, _run(fn, c, 1.4)

    def test_kneel_lean_at_most_55_degrees(self):
        _, rows = self._kneel_rows()
        leans = []
        for _, J, _ in rows:
            dx = J["shoulder"][0] - J["hip"][0]
            dy = J["hip"][1] - J["shoulder"][1]
            leans.append(math.degrees(math.atan2(dx, dy)))
        self.assertLessEqual(max(leans), 55.0,
                             f"kneel still bows: {max(leans):.1f} deg")
        self.assertGreater(max(leans), 45.0,
                           "kneel too upright to reach the ground prop")

    def test_kneel_head_stays_high(self):
        c, rows = self._kneel_rows()
        stand_h = _standing_head_height(c)
        # at full kneel (hold phase, u 0.5..0.65 -> t 0.7..0.91 s)
        fracs = [(GY - J["head"][1]) / stand_h
                 for t, J, _ in rows if 0.7 <= t <= 0.91]
        self.assertGreaterEqual(min(fracs), 0.40,
                                f"head only {min(fracs):.3f} of standing "
                                f"(v6 was 0.346, rig cap is ~0.42)")

    def test_kneel_back_knee_never_below_ground(self):
        _, rows = self._kneel_rows()
        gaps = [GY - J["knee_l"][1] for _, J, _ in rows]
        self.assertGreaterEqual(min(gaps), -2.0,
                                f"back knee clips {min(gaps):.1f}px below "
                                f"the ground (v7 hip + v6 tuck did -30)")
        hold_gaps = [GY - J["knee_l"][1]
                     for t, J, _ in rows if 0.7 <= t <= 0.91]
        self.assertLessEqual(max(hold_gaps), 20.0,
                             "back knee floats above the ground at hold")
        self.assertGreaterEqual(min(hold_gaps), -2.0,
                                "back knee below ground at hold")

    def test_kneel_hand_still_holds(self):
        _, rows = self._kneel_rows()
        hold = sum(
            1 for _, J, _ in rows
            if math.hypot(J["hand_r"][0] - 1001,
                          J["hand_r"][1] - (GY - 6)) < 15)
        self.assertGreaterEqual(hold, 9,
                                f"hand held the wallet only {hold} frames")


class TestCanonicalStandSplit(unittest.TestCase):
    """One standing split everywhere: +/-0.125H (STAND_SPLIT_FRAC)."""

    def test_plant_feet_spread(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=500, root_y=GY - (c.u_leg + c.l_leg) * 0.93)
        plant_feet(c, GY)
        self.assertAlmostEqual(c.foot_target_l[0],
                               500 - STAND_SPLIT_FRAC * H, delta=1.0)
        self.assertAlmostEqual(c.foot_target_r[0],
                               500 + STAND_SPLIT_FRAC * H, delta=1.0)
        self.assertEqual(c.foot_target_l[1], GY)
        self.assertEqual(c.foot_target_r[1], GY)

    def test_idle_feet_use_canonical_split(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=500, root_y=GY - (c.u_leg + c.l_leg) * 0.93)
        fn = idle(c, 1.0, GY)
        fn(0.0)
        self.assertAlmostEqual(c.foot_target_l[0],
                               500 - STAND_SPLIT_FRAC * H, delta=1.0)
        self.assertAlmostEqual(c.foot_target_r[0],
                               500 + STAND_SPLIT_FRAC * H, delta=1.0)

    def test_walk_ends_in_canonical_split(self):
        # the walk's settle gathers the feet to +/-step/2, and the v6
        # step is 0.25H -- the same +/-0.125H as the canonical split.
        c = make_character_instance("minh", height=H)
        fn = walk_to(c, 125, 570, 2.1, GY)
        rows = _run(fn, c, 2.1)
        _, J, _ = rows[-1]
        self.assertAlmostEqual(J["foot_l"][0], 570 - 0.125 * H, delta=3.0)
        self.assertAlmostEqual(J["foot_r"][0], 570 + 0.125 * H, delta=3.0)


class TestSettleGather(unittest.TestCase):
    """The settle must STEP the feet into the standing split (lifted),
    not freeze them mid-stride (v6) and not slide them (v5)."""

    def test_settle_feet_lifted_while_moving(self):
        # Same definition as the rubric's slip(): horizontal movement
        # counts as a slide only while the foot is planted (within
        # 0.5 px of the ground on BOTH frames). A foot peeling off on
        # a lift arc is airborne, not sliding -- the arc starts at
        # ~1.4 px up while moving ~3 px, which is a step, not a slide.
        c = make_character_instance("minh", height=H)
        fn = walk_to(c, 125, 570, 2.1, GY)
        prev = None
        slide = {"foot_l": 0.0, "foot_r": 0.0}
        for fi in range(int(2.1 * 24) + 1):
            t = fi / 24
            fn(t)
            J = c.joints()
            if t > 2.1 - 0.2 and prev is not None:
                for side in ("foot_l", "foot_r"):
                    if (abs(prev[side][1] - GY) < 0.5
                            and abs(J[side][1] - GY) < 0.5):
                        slide[side] += abs(J[side][0] - prev[side][0])
            prev = {k: v for k, v in J.items()}
        self.assertLessEqual(slide["foot_l"], 2.0,
                             f"settle slides left foot {slide['foot_l']:.1f}px")
        self.assertLessEqual(slide["foot_r"], 2.0,
                             f"settle slides right foot {slide['foot_r']:.1f}px")

    def test_kneel_feet_lifted_while_moving(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=918, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        fn = kneel_pick(c, (1001, GY - 6), 1.4, GY)
        prev = None
        slide = {"foot_l": 0.0, "foot_r": 0.0}
        for fi in range(int(1.4 * 24) + 1):
            fn(fi / 24)
            J = c.joints()
            if prev is not None:
                for side in ("foot_l", "foot_r"):
                    if (abs(prev[side][1] - GY) < 0.5
                            and abs(J[side][1] - GY) < 0.5):
                        slide[side] += abs(J[side][0] - prev[side][0])
            prev = {k: v for k, v in J.items()}
        # v6 kneel lerped the feet along the ground: ~125 px of slide.
        # v7 lift arcs must keep the planted slide under 5 px total.
        self.assertLessEqual(slide["foot_l"], 5.0,
                             f"kneel slides left foot {slide['foot_l']:.1f}px")
        self.assertLessEqual(slide["foot_r"], 5.0,
                             f"kneel slides right foot {slide['foot_r']:.1f}px")


class TestAnticipationStep(unittest.TestCase):
    """v7: after a CUT the incoming feet may sit at a different split
    than the new gait's stand split (walk +/-0.125H vs run +/-0.14H =
    12 px). The anticipation must STEP them there on a lift arc, not
    slide them along the ground (v6 set the targets directly)."""

    def test_run_after_walk_cut_does_not_slide(self):
        from ai_clip_studio.animation.primitives import run_to
        c = make_character_instance("minh", height=H)
        walk_fn = walk_to(c, 125, 570, 2.1, GY)
        _run(walk_fn, c, 2.1)
        # the cut: the run starts from the walk's end pose, no blend.
        run_fn = run_to(c, 570, 918, 1.1, GY)
        prev = None
        slide = {"foot_l": 0.0, "foot_r": 0.0}
        for fi in range(int(1.1 * 24) + 1):
            run_fn(fi / 24)
            J = c.joints()
            if prev is not None:
                for side in ("foot_l", "foot_r"):
                    if (abs(prev[side][1] - GY) < 0.5
                            and abs(J[side][1] - GY) < 0.5):
                        slide[side] += abs(J[side][0] - prev[side][0])
            prev = {k: v for k, v in J.items()}
        self.assertLessEqual(slide["foot_l"], 5.0,
                             f"run anticipation slides left foot "
                             f"{slide['foot_l']:.1f}px after the cut")
        self.assertLessEqual(slide["foot_r"], 5.0,
                             f"run anticipation slides right foot "
                             f"{slide['foot_r']:.1f}px after the cut")


class TestSafeFrame(unittest.TestCase):
    """The camera planner must not repeat the v4/v5 framing defects:
    a 3.4x insert slicing a head, a reaction that does not fit."""

    def test_insert_with_head_at_edge_gets_reframed(self):
        # object at (1000, 900); a character stands beside it, head
        # at the crop edge -- the v4 defect (wallet insert slicing
        # Minh's head). safe_frame must return a crop with the
        # subject fitting and the other fully in or out.
        shot = {"shot_type": "object_insert",
                "camera": {"scale": 3.4, "focus_target": "object"}}
        focus = (1000, 900)
        subjects = [{"cx": 1000, "head_y": 870, "foot_y": 930,
                     "half_w": 60}]
        others = [{"cx": 950, "head_y": 360, "foot_y": 920,
                   "half_w": 55}]
        safe, sfocus, _ = CameraPlanner.safe_frame(
            shot, focus, subjects, others)
        issues, _ = validate_framing(safe, sfocus, subjects)
        self.assertEqual(issues, [], f"safe insert still bad: {issues}")
        # the other is fully in or fully out of the safe crop
        from ai_clip_studio.camera_planner import _crop_rect, _other_status
        rect = _crop_rect(float(safe["camera"]["scale"]), sfocus,
                          1920, 1080)
        self.assertIn(_other_status(others[0], rect), ("in", "out"))

    def test_reaction_that_does_not_fit_zooms_out(self):
        # two subjects 800 px apart cannot fit a 2.6x reaction crop
        shot = {"shot_type": "reaction",
                "camera": {"scale": 2.6, "focus_target": "subject_head"}}
        focus = (960, 500)
        subjects = [{"cx": 500, "head_y": 360, "foot_y": 920,
                     "half_w": 55},
                    {"cx": 1300, "head_y": 360, "foot_y": 920,
                     "half_w": 55}]
        safe, sfocus, _ = CameraPlanner.safe_frame(
            shot, focus, subjects, [])
        issues, _ = validate_framing(safe, sfocus, subjects)
        self.assertEqual(issues, [], f"safe reaction still bad: {issues}")
        self.assertLess(float(safe["camera"]["scale"]), 2.6,
                        "reaction that cannot fit must zoom out, not "
                        "ship a 'do not fit' crop")
        self.assertEqual(safe["shot_type"], "reaction",
                         "shot type is kept; only the scale changes")

    def test_safe_frame_keeps_a_good_shot_unchanged(self):
        shot = {"shot_type": "medium",
                "camera": {"scale": 1.6, "focus_target": "subject_full"}}
        focus = (960, 600)
        subjects = [{"cx": 960, "head_y": 360, "foot_y": 920,
                     "half_w": 55}]
        safe, sfocus, _ = CameraPlanner.safe_frame(
            shot, focus, subjects, [])
        self.assertEqual(float(safe["camera"]["scale"]), 1.6)

    def test_apply_camera_safe_returns_full_size_image(self):
        from PIL import Image as _Image
        img = _Image.new("RGB", (1920, 1080), (200, 200, 200))
        shot = {"shot_type": "object_insert",
                "camera": {"scale": 3.4, "focus_target": "object"}}
        subjects = [{"cx": 1000, "head_y": 870, "foot_y": 930,
                     "half_w": 60}]
        others = [{"cx": 950, "head_y": 360, "foot_y": 920,
                   "half_w": 55}]
        out, safe, _, notes = CameraPlanner.apply_camera_safe(
            img, shot, (1000, 900), subjects, others)
        self.assertEqual(out.size, (1920, 1080))
        self.assertIn("safe_frame", safe)


class TestBoxLabel(unittest.TestCase):
    """A labelled Box3D renders readable text on its front face."""

    def test_label_draws_yellow_text(self):
        scene = Scene25D(
            camera=PerspectiveCamera(position=(0, 1.5, 6.0),
                                     target=(0, 1.0, 0)),
            boxes=[
                Box3D(center=(0, 1.0, -2.0), size=(2.0, 0.8, 0.2),
                      color=(30, 30, 40), name="sign",
                      label="TRẠM XE BUÝT"),
            ])
        img = render_frame(scene)
        arr = np.asarray(img)
        yellow = ((arr[:, :, 0] > 200) & (arr[:, :, 1] > 150)
                  & (arr[:, :, 2] < 100)).sum()
        self.assertGreater(int(yellow), 100,
                           "labelled sign renders no yellow text pixels")

    def test_unlabelled_box_draws_no_text(self):
        scene = Scene25D(
            camera=PerspectiveCamera(position=(0, 1.5, 6.0),
                                     target=(0, 1.0, 0)),
            boxes=[
                Box3D(center=(0, 1.0, -2.0), size=(2.0, 0.8, 0.2),
                      color=(30, 30, 40), name="sign"),
            ])
        img = render_frame(scene)
        arr = np.asarray(img)
        yellow = ((arr[:, :, 0] > 200) & (arr[:, :, 1] > 150)
                  & (arr[:, :, 2] < 100)).sum()
        self.assertEqual(int(yellow), 0)


class TestCharacterIdentityV7(unittest.TestCase):
    """Identity is costume / body / hat / hair (the reference way),
    not gait: Lan slim + dress, Minh sturdy."""

    def test_lan_is_slim_with_dress(self):
        self.assertEqual(CHARACTER_INSTANCES["lan"].get("costume"),
                         "dress")
        self.assertEqual(CHARACTER_INSTANCES["lan"].get("body_variant"),
                         "slim")

    def test_minh_is_sturdy(self):
        self.assertEqual(CHARACTER_INSTANCES["minh"].get("body_variant"),
                         "sturdy")

    def test_lan_dress_renders_below_hip(self):
        # draw Lan in profile; suit-coloured pixels below the hip are
        # the dress (v6: 37 px of noise; v7: thousands).
        ch = make_character_instance("lan", height=560)
        img = Image.new("RGB", (1000, 1200), (255, 255, 255))
        d = ImageDraw.Draw(img, "RGBA")
        ch.set_pose(root_x=500, root_y=900, facing=1, thigh_l=0.05,
                    thigh_r=-0.05, knee_l=0.1, knee_r=0.1, arm_l=0.05,
                    arm_r=0.05, elbow_l=0.15, elbow_r=0.15, bob=0.0,
                    torso_lean=0.0)
        ch.hand_target_l = None
        ch.hand_target_r = None
        J = draw_character_v4(d, ch, expression="neutral", view="profile")
        arr = np.asarray(img)
        suit = np.array([int(ch.suit[i:i + 2], 16) for i in (1, 3, 5)])
        mask = (np.abs(arr.astype(int) - suit) < 12).all(axis=2)
        hip_y = int(J["hip"][1])
        below = mask[hip_y + 20:, :].sum()
        self.assertGreater(int(below), 500,
                           f"Lan dress renders only {below} suit px "
                           f"below the hip")


class TestAnticipationStaleCapture(unittest.TestCase):
    """_locomote anticipation: the re-capture must not trust a stale
    pre-warm pose, and must fire on the first real frame even when
    t_ant is short (rubric C12 234 px + a 327 px cut teleport, found
    by the first v7 render).

    The render pre-warms every segment, so when the walk's first real
    frame runs, the rig still sits in the LAST pre-warm pose
    (standing at the handover x, feet ~1000 px from the walk's stand
    split). The old `a < 0.05` re-capture trusted that pose and swung
    a foot 234 px in one frame. And for the 1.1 s run t_ant is only
    0.165 s, so at the first run frame (lt = 0.025) a = 0.062 and NO
    re-capture happened at all -- the run stepped from the stale
    pre-warm capture (feet at the walk's start x) and the IK clamp
    dragged a foot to (285, 747), a 327 px teleport across the cut.
    """

    def _stand(self, c, x):
        c.set_pose(root_x=x,
                   root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1, thigh_l=0.08, thigh_r=-0.08,
                   knee_l=0.12, knee_r=0.12, arm_l=0.08, arm_r=0.08,
                   elbow_l=0.15, elbow_r=0.15, bob=0.0,
                   torso_lean=0.0, head_look=0.0)
        c.hand_target_l = None
        c.hand_target_r = None
        plant_feet(c, GY)

    def test_walk_start_ignores_stale_prewarm_pose(self):
        # Rig left standing at the handover x (the last pre-warm
        # pose), then the walk's first real frame at its own start x.
        c = make_character_instance("minh", height=H)
        self._stand(c, 1113)
        fn = walk_to(c, 125, 570, 2.1, GY)
        fn(0.0)
        J = c.joints()
        # Feet at the walk's stand split, not at the stale pose.
        self.assertAlmostEqual(J["foot_l"][0], 125 - 0.25 * H / 2,
                               delta=5)
        self.assertAlmostEqual(J["foot_r"][0], 125 + 0.25 * H / 2,
                               delta=5)
        self.assertAlmostEqual(J["foot_l"][1], GY, delta=5)
        # No big swing during the anticipation (0-0.25 s).
        rows = _run(fn, c, 0.25)
        worst = 0.0
        for (_, a, _), (_, b, _) in zip(rows, rows[1:]):
            for k in ("foot_l", "foot_r"):
                worst = max(worst, math.hypot(
                    b[k][0] - a[k][0], b[k][1] - a[k][1]))
        self.assertLessEqual(worst, 70,
                             f"foot swung {worst:.1f}px in one frame "
                             f"during the walk anticipation")

    def test_run_first_frame_after_cut_does_not_teleport(self):
        # Faithful render sequence: pre-warm (walk + run at the walk
        # start, then the rig moved to the run end by later pre-warms),
        # walk the whole segment, then the run's first real frame at
        # lt = 0.025 (the cut falls at 2.1 s = frame 50.4, so the run
        # is never called at lt = 0.0 during the real render).
        c = make_character_instance("minh", height=H)
        self._stand(c, 125)
        walk_fn = walk_to(c, 125, 570, 2.1, GY)
        run_fn = run_to(c, 570, 918, 1.1, GY)
        walk_fn(0.0)   # pre-warm
        run_fn(0.0)    # pre-warm (stale capture: feet at walk start)
        self._stand(c, 918)  # later pre-warms move the rig away
        last = None
        for fi in range(int(2.1 * 24) + 1):
            walk_fn(fi / 24)
            last = c.joints()
        run_fn(0.025)
        now = c.joints()
        for k in ("foot_l", "foot_r"):
            d = math.hypot(now[k][0] - last[k][0],
                           now[k][1] - last[k][1])
            self.assertLessEqual(d, 70,
                                 f"{k} jumped {d:.1f}px across the "
                                 f"walk->run cut (rubric C14)")

    def test_run_accepts_real_previous_segment_feet(self):
        # The guard must not reject a genuine previous-segment foot:
        # after the walk settles, the run's anticipation steps the
        # feet only the ~12 px to the run's wider stand split.
        c = make_character_instance("minh", height=H)
        self._stand(c, 125)
        walk_fn = walk_to(c, 125, 570, 2.1, GY)
        run_fn = run_to(c, 570, 918, 1.1, GY)
        walk_fn(0.0)
        run_fn(0.0)
        for fi in range(int(2.1 * 24) + 1):
            walk_fn(fi / 24)
        last = c.joints()
        run_fn(0.0)
        now = c.joints()
        for k in ("foot_l", "foot_r"):
            d = math.hypot(now[k][0] - last[k][0],
                           now[k][1] - last[k][1])
            self.assertLessEqual(d, 15,
                                 f"{k} moved {d:.1f}px at the run "
                                 f"start (expected ~12px step)")

    def test_run_first_stride_starts_from_the_plant(self):
        # _foot_state: for a run (negative overlap) the steady-state
        # lift point of the first cycle is < 0, so at the travel
        # start (s = 0) the left foot was already 23% through its
        # swing -- 62 px ahead of the stand split, and the knee
        # popped 77 px in one frame at the anticipation->travel
        # boundary (rubric C12, v6: 84.5 px). The foot was planted
        # during the anticipation, so the first swing must start at
        # the plant, and the knee must not pop at the boundary.
        c = make_character_instance("minh", height=H)
        self._stand(c, 570)
        fn = run_to(c, 570, 918, 1.1, GY)
        rows = _run(fn, c, 1.1)
        # At the travel start the left foot is at the stand split.
        # The anticipation lasts 0.165 s; the first travel frame is
        # the first row with t >= 0.165.
        travel = [(t, J) for t, J, _ in rows if t >= 0.165]
        t0, J0 = travel[0]
        self.assertAlmostEqual(J0["foot_l"][0], 570 - 0.28 * H / 2,
                               delta=5)
        self.assertAlmostEqual(J0["foot_l"][1], GY, delta=5)
        # No knee pop at the anticipation->travel boundary.
        worst = 0.0
        for (_, a, _), (_, b, _) in zip(rows, rows[1:]):
            worst = max(worst, math.hypot(
                b["knee_l"][0] - a["knee_l"][0],
                b["knee_l"][1] - a["knee_l"][1]))
        self.assertLessEqual(worst, 70,
                             f"knee_l jumped {worst:.1f}px in one "
                             f"frame during the run")

    def test_settle_gathers_to_nearest_split_no_crossing(self):
        # The settle gathers the feet into the canonical split. When
        # the travel covers an ODD number of steps (the walk_hold
        # covers ~1 step), the feet end SWAPPED (foot_l ahead,
        # foot_r behind); gathering foot_l to the behind mark would
        # make the feet CROSS (196 px in 4 frames, a 72 px/frame pop,
        # rubric C12). The settle must gather each foot to its
        # NEAREST split position -- the feet are already in a valid
        # split, just swapped.
        c = make_character_instance("minh", height=H)
        self._stand(c, 918)
        fn = walk_to(c, 918, 1113, 1.1, GY)
        rows = _run(fn, c, 1.1)
        worst = 0.0
        for (_, a, _), (_, b, _) in zip(rows, rows[1:]):
            for k in ("foot_l", "foot_r"):
                worst = max(worst, math.hypot(
                    b[k][0] - a[k][0], b[k][1] - a[k][1]))
        self.assertLessEqual(worst, 70,
                             f"a foot jumped {worst:.1f}px in one "
                             f"frame during the walk_hold settle")
        # And the feet end in a split (one ahead, one behind).
        _, J, _ = rows[-1]
        self.assertGreater(abs(J["foot_l"][0] - J["foot_r"][0]), 100)


if __name__ == "__main__":
    unittest.main()
