"""Animation v8 tests -- gesture smoothness + landmarks + identity
(2026-11-11).

Mai's verdict on motion test v7: much improved, but the GESTURES are
still not smooth ("cac cu chi chua duoc muot"), and the SCENE must have
distinctive REAL-WORLD things (e.g. the Great Wall) while characters
need signature real-world traits (e.g. a moustache). The v8 rubric
(acceptance_loop/audit_animation_v8/rubric_v8.py) scores v7 at 0% on
E (smoothness) and ~20% on F (distinctiveness). These tests pin the
v8 engine fixes that close those items:

  * anticipation hop: the run's anticipation lifted BOTH feet 44 px
    for a 12 px sideways step (a hop, not a step) -- the knee velocity
    oscillated 31 -> 8 -> 34 -> 4 px/frame. Anticipation steps now
    lift PROPORTIONALLY to the step distance (<= 8 px for a 12 px
    step);
  * settle gather: the run's 0.165 s settle drove the foot to
    42 px/frame and jerked the knee 45.7 px/frame^2. The settle is
    longer (0.25 s / 20%) with a proportional gather lift;
  * kneel rise: the v7 rise lifted the hand only 60 px, leaving it
    298 px from the waist hold, so the next segment's 0.2 s blend
    sprinted the hand 66 px/frame (IK clamp dead zone + catch-up).
    The rise now carries the hand to the WAIST hold;
  * blend elbow flip: apply_snapshot invented an IK target from the
    FK hand position when NEITHER snapshot had one, so a free arm
    went IK during the blend and its elbow snapped 60 px at the blend
    end (IK elbow branch != FK elbow branch). Both-None now stays
    None (FK);
  * wave rise: the v7 rise was a PERFECTLY straight line (0.1 px
    deviation from the chord) and ignored facing, so Lan (facing
    left) waved BEHIND her back. The rise is now a Bezier arc
    (forward + up) in the facing direction;
  * head secondary motion: the v7 head was rigid on the torso (0
    frames of lag). The head now dips back in anticipation and
    overshoots forward in the settle (head_sway_x);
  * standing(): the old standing forced the canonical split, so the
    handover blend crossed the feet 196 px (59 px/frame). standing()
    now KEEPS a planted split;
  * landmarks: Great Wall (8 wall segments + 3 watchtowers), Eiffel
    Tower (3 platforms + lattice), Vietnamese street features
    (power lines, motorbike, shop signs) -- all in the shared engine;
  * identity: moustache styles (toothbrush / handlebar / full),
    side-part hair, uniform costume, and the "officer" test instance
    (toothbrush + side part + uniform) whose silhouette is distinct
    from Lustig's (bowler + full moustache + plain suit).

They assert on the RIG / rendered pixels, not on a video, so they run
in milliseconds.
"""
import itertools
import math
import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import (
    CHARACTER_INSTANCES, draw_character_v4, make_character_instance)
from ai_clip_studio.animation.landmarks import (
    LANDMARKS, landmark_boxes, landmark_features)
from ai_clip_studio.animation.primitives import (
    apply_snapshot, kneel_pick, run_to, snapshot, standing, walk_to, wave)
from ai_clip_studio.animation.rig import (
    MOUSTACHE_STYLES, plant_feet)

GY = 900
H = 783


def _run(fn, c, dur, fps=24):
    rows = []
    for fi in range(int(dur * fps) + 1):
        fn(fi / fps)
        rows.append((fi / fps, c.joints(), dict(c.pose)))
    return rows


def _vel(rows, key, who=None):
    """Per-frame speed (px/frame) of joint `key` along `rows`."""
    out = []
    for (_, a, _), (_, b, _) in zip(rows, rows[1:]):
        pa, pb = a[key], b[key]
        out.append(math.hypot(pb[0] - pa[0], pb[1] - pa[1]))
    return out


def _jerk(vs):
    return [abs(b - a) for a, b in zip(vs, vs[1:])]


def _char(name="minh", height=H):
    return make_character_instance(name, height=height)


def _stand(c, x=500):
    standing(c, x, GY, facing=1)
    return c


class TestAnticipationHop(unittest.TestCase):
    """E1/E2: the run's anticipation must STEP, not hop."""

    def test_run_anticipation_foot_lift_small(self):
        c = _stand(_char(), 500)
        # walk split -> run split: feet start at the walk's stand
        # split (+/-0.125H), the run wants +/-0.14H -- a 12 px step.
        fn = run_to(c, 500, 848, 1.1, GY)
        rows = _run(fn, c, 0.17)  # anticipation only (t_ant = 0.165)
        for _, J, _ in rows:
            for side in ("l", "r"):
                lift = GY - J[f"foot_{side}"][1]
                self.assertLessEqual(
                    lift, 12.0,
                    f"anticipation foot_{side} lifts {lift:.1f}px "
                    f"(v7: 44px hop for a 12px step)")

    def test_run_anticipation_knee_jerk_bounded(self):
        c = _stand(_char(), 500)
        fn = run_to(c, 500, 848, 1.1, GY)
        rows = _run(fn, c, 0.17)
        for side in ("l", "r"):
            vs = _vel(rows, f"knee_{side}")
            self.assertLessEqual(
                max(_jerk(vs), default=0.0), 20.0,
                f"anticipation knee_{side} jerk "
                f"{max(_jerk(vs), default=0.0):.1f} (v7: ~30)")


class TestSettleGather(unittest.TestCase):
    """E7: the run's settle must not sprint the feet."""

    def test_run_settle_foot_velocity_bounded(self):
        c = _stand(_char(), 500)
        fn = run_to(c, 500, 848, 1.1, GY)
        rows = _run(fn, c, 1.1)
        # last 0.25 s = settle (v8: t_set = 0.25 s)
        tail = rows[-7:]
        for side in ("l", "r"):
            vs = _vel(tail, f"foot_{side}")
            self.assertLessEqual(
                max(vs, default=0.0), 30.0,
                f"settle foot_{side} velocity {max(vs, default=0.0):.1f} "
                f"(v7: 42.5 px/frame)")


class TestKneelRiseToWaist(unittest.TestCase):
    """E3/E4: the kneel rise must end at the waist hold."""

    def test_kneel_ends_at_waist_hold(self):
        c = _stand(_char(), 918)
        fn = kneel_pick(c, (1001, GY - 6), 1.4, GY)
        rows = _run(fn, c, 1.4)
        _, J, _ = rows[-1]
        s = H / 560.0
        waist = (918 + 40 * s, GY - (c.u_leg + c.l_leg) * 0.93 - 60 * s)
        hx, hy = J["hand_r"]
        self.assertLessEqual(
            math.hypot(hx - waist[0], hy - waist[1]), 15.0,
            f"kneel-end hand ({hx:.0f},{hy:.0f}) vs waist hold "
            f"({waist[0]:.0f},{waist[1]:.0f}) (v7: 298px away)")

    def test_kneel_rise_hand_jerk_bounded(self):
        c = _stand(_char(), 918)
        fn = kneel_pick(c, (1001, GY - 6), 1.4, GY)
        rows = _run(fn, c, 1.4)
        # rise phase: last 35% of the kneel
        rise = rows[int(len(rows) * 0.65):]
        vs = _vel(rise, "hand_r")
        self.assertLessEqual(
            max(_jerk(vs), default=0.0), 25.0,
            f"kneel-rise hand jerk {max(_jerk(vs), default=0.0):.1f}")


class TestBlendTarget(unittest.TestCase):
    """E5: a free limb must stay FK through a blend (no elbow flip)."""

    def test_blend_with_no_targets_keeps_fk_arms(self):
        c = _stand(_char(), 500)
        # both snapshots have NO hand targets (free arms, as in a
        # walk->walk blend): the blended pose must not invent one.
        snap_a = snapshot(c)
        c.set_pose(arm_l=0.25, arm_r=-0.25, elbow_l=0.5, elbow_r=0.25)
        snap_b = snapshot(c)
        apply_snapshot(c, snap_a, snap_b, 0.5)
        self.assertIsNone(c.hand_target_l)
        self.assertIsNone(c.hand_target_r)

    def test_blend_end_elbow_no_snap(self):
        # Reproduce the v7 walk_hold boundary: kneel-end snapshot
        # blended into walk_hold-start, then the plain walk_hold pose.
        # The left elbow must not jump when the blend ends.
        c = _stand(_char(), 918)
        bend = kneel_pick(c, (1001, GY - 6), 1.4, GY)
        bend(1.4)
        snap_prev = snapshot(c)
        walk = walk_to(c, 918, 1113, 1.1, GY)
        # The render loop captures the new segment's snapshot at the
        # blend's CURRENT lt (0.19), not at lt=0.0 -- capturing at 0.0
        # would inject a lean snap (0 -> 0.12) that the real loop
        # never has, and mask the branch-flip this test is for.
        walk(0.19)
        c.hand_target_r = (c.pose["root_x"] + 40 * H / 560.0,
                           c.pose["root_y"] - 60 * H / 560.0)
        snap_cur = snapshot(c)
        apply_snapshot(c, snap_prev, snap_cur, 0.99)
        elbow_blend_end = c.joints()["elbow_l"]
        walk(0.23)  # first frame past the 0.2 s blend
        c.hand_target_r = (c.pose["root_x"] + 40 * H / 560.0,
                           c.pose["root_y"] - 60 * H / 560.0)
        elbow_after = c.joints()["elbow_l"]
        jump = math.hypot(elbow_after[0] - elbow_blend_end[0],
                          elbow_after[1] - elbow_blend_end[1])
        self.assertLessEqual(
            jump, 30.0,
            f"elbow_l jumps {jump:.1f}px at the blend end (v7: 60px)")


class TestWaveArc(unittest.TestCase):
    """E8: the wave rise must be an ARC in the FACING direction."""

    def _hand_path(self, facing):
        c = _stand(_char(), 500)
        c.set_pose(facing=facing)
        fn = wave(c, 1.1)
        rows = []
        for fi in range(18):  # rise = first 0.7 s
            fn(fi / 24.0)
            rows.append(c.joints()["hand_r"])
        return rows

    def test_wave_rise_is_an_arc(self):
        pts = self._hand_path(1)
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1.0
        dev = max(abs((x - x0) * dy - (y - y0) * dx) / L for x, y in pts)
        self.assertGreaterEqual(
            dev, 10.0,
            f"wave rise deviates {dev:.1f}px from the chord "
            f"(v7: 0.1px -- a straight robot line)")

    def test_wave_rises_forward_for_facing_left(self):
        pts = self._hand_path(-1)
        # Lan faces left: the risen hand must be LEFT of the root
        # (forward), not right (behind her back, as in v7).
        self.assertLess(pts[-1][0], 500.0,
                        f"facing-left wave ends at x={pts[-1][0]:.0f}, "
                        f"right of the root (v7: behind her back)")

    def test_wave_eases_in_and_settles_out(self):
        """E10 (v8.1): the wave must ease IN (start velocity a small
        fraction of the peak -- the 40 px Bezier bulge lunged at 0.68
        of peak) and ease OUT (the sway damps over the last 0.3 s so
        the hand settles at the raised position instead of stopping
        mid-swing at 0.82 of peak)."""
        c = _stand(_char(), 500)
        fn = wave(c, 1.1)
        pts = []
        for fi in range(27):  # full 1.1 s wave
            fn(fi / 24.0)
            pts.append(c.joints()["hand_r"])
        vs = [math.hypot(b[0] - a[0], b[1] - a[1])
              for a, b in zip(pts, pts[1:])]
        peak = max(vs)
        start_ratio = (sum(vs[:3]) / 3) / peak
        end_ratio = (sum(vs[-3:]) / 3) / peak
        self.assertLessEqual(start_ratio, 0.60,
                             f"wave starts at {start_ratio:.2f} of peak")
        self.assertLessEqual(end_ratio, 0.60,
                             f"wave ends at {end_ratio:.2f} of peak")
        # the hand settles at the raised position (not mid-sway)
        end = pts[-1]
        rise_end = pts[16]
        self.assertLess(math.hypot(end[0] - rise_end[0],
                                   end[1] - rise_end[1]), 15.0,
                        "hand does not settle at the raised position")


class TestHeadSecondaryMotion(unittest.TestCase):
    """E9: the head must lag the torso (anticipation + follow-through)."""

    def test_head_dips_back_in_anticipation(self):
        c = _stand(_char(), 500)
        fn = walk_to(c, 500, 700, 2.1, GY)
        fn(0.10)  # mid-anticipation
        self.assertLess(c.pose.get("head_sway_x", 0.0), -2.0,
                        "head does not dip back in anticipation (v7: 0)")

    def test_head_overshoots_in_settle(self):
        c = _stand(_char(), 500)
        fn = walk_to(c, 500, 700, 2.1, GY)
        fn(2.1 - 0.125)  # mid-settle
        self.assertGreater(c.pose.get("head_sway_x", 0.0), 2.0,
                           "head does not overshoot in the settle (v7: 0)")


class TestStandingKeepsSplit(unittest.TestCase):
    """E6: standing() must keep a planted split, not force canonical."""

    def test_standing_keeps_swapped_split(self):
        c = _stand(_char(), 500)
        # simulate a walk end with SWAPPED feet (foot_l ahead)
        c.foot_target_l = (598, GY)
        c.foot_target_r = (402, GY)
        standing(c, 500, GY, facing=1)
        self.assertAlmostEqual(c.foot_target_l[0], 598.0, delta=1.0)
        self.assertAlmostEqual(c.foot_target_r[0], 402.0, delta=1.0)

    def test_standing_uses_canonical_when_unposed(self):
        c = _char()
        c.foot_target_l = None
        c.foot_target_r = None
        standing(c, 500, GY, facing=1)
        self.assertIsNotNone(c.foot_target_l)
        self.assertAlmostEqual(c.foot_target_l[0],
                               500 - 0.125 * H, delta=1.0)
        self.assertAlmostEqual(c.foot_target_r[0],
                               500 + 0.125 * H, delta=1.0)


class TestLandmarks(unittest.TestCase):
    """F1/F2/F10: the landmark library is real, parametric data."""

    def test_registry_has_three_landmarks(self):
        self.assertEqual(set(LANDMARKS),
                         {"great_wall", "eiffel_tower", "rainy_street"})

    def test_great_wall_has_segments_and_towers(self):
        boxes = landmark_boxes("great_wall")
        walls = [b for b in boxes if b["name"].startswith("wall_")]
        towers = [b for b in boxes
                  if b["name"].startswith("watchtower_")
                  and "roof" not in b["name"]]
        self.assertGreaterEqual(len(walls), 5)
        self.assertGreaterEqual(len(towers), 2)
        # the wall snakes: its segments span in y (elevation) and z
        ys = [b["center"][1] for b in walls]
        self.assertGreater(max(ys) - min(ys), 0.5)

    def test_eiffel_has_three_platforms_and_legs(self):
        boxes = landmark_boxes("eiffel_tower")
        plats = [b for b in boxes if b["name"].startswith("platform_")]
        legs = [b for b in boxes if b["name"].startswith("leg")]
        self.assertEqual(len(plats), 3)
        self.assertGreaterEqual(len(legs), 4)
        # platforms shrink with height (tapered tower)
        ordered = sorted(plats, key=lambda b: b["center"][1])
        self.assertGreater(ordered[0]["size"][0], ordered[-1]["size"][0])

    def test_rainy_street_features_are_engine_level(self):
        feats = landmark_features("rainy_street")
        for f in ("power_lines", "motorbike", "shop_signs"):
            self.assertIn(f, feats)

    def test_unknown_landmark_raises(self):
        with self.assertRaises(KeyError):
            landmark_boxes("colosseum")


class TestIdentityTraits(unittest.TestCase):
    """F7/F8/F9: signature traits are template data, and the officer
    is distinct from Lustig in silhouette."""

    def test_moustache_styles_exist(self):
        for s in ("toothbrush", "handlebar", "full", "none"):
            self.assertIn(s, MOUSTACHE_STYLES)

    def test_all_moustache_styles_render_distinctly(self):
        # Each style draws a different dark-pixel count in the
        # moustache band (mouth-centred, profile view).
        from ai_clip_studio.animation.character_art import STYLE_LOCK
        from ai_clip_studio.animation.primitives import standing as _st
        counts = {}
        for style in ("toothbrush", "handlebar", "full"):
            ch = make_character_instance(
                "lustig", height=560, moustache_style=style)
            img = Image.new("RGB", (600, 700), (255, 255, 255))
            d = ImageDraw.Draw(img, "RGBA")
            _st(ch, 300, 620, facing=1)
            J = draw_character_v4(d, ch, expression="neutral",
                                  view="profile")
            arr = np.asarray(img).sum(axis=2) < 400
            hx, hy = J["head"]
            r = ch.head_r
            my = hy + STYLE_LOCK["mouth_dy_frac_of_r"] * r
            band = arr[int(my - 0.32 * r):int(my - 0.06 * r),
                       int(hx - 0.5 * r):int(hx + 0.5 * r)]
            counts[style] = int(band.sum())
        self.assertEqual(len(set(counts.values())), 3,
                         f"moustache styles render identically: {counts}")

    def test_officer_has_the_three_signature_traits(self):
        spec = CHARACTER_INSTANCES["officer"]
        self.assertEqual(spec["moustache_style"], "toothbrush")
        self.assertEqual(spec["hair_style"], "side_part")
        self.assertEqual(spec["costume"], "uniform")

    def test_officer_silhouette_distinct_from_lustig(self):
        def _mask(name):
            ch = make_character_instance(name, height=560)
            img = Image.new("RGB", (600, 700), (255, 255, 255))
            d = ImageDraw.Draw(img, "RGBA")
            standing(ch, 300, 620, facing=1)
            J = draw_character_v4(d, ch, expression="neutral",
                                  view="front")
            arr = np.asarray(img).astype(int)
            dark = arr.sum(axis=2) < 400
            r, g, b = (int(ch.suit[i:i + 2], 16) for i in (1, 3, 5))
            suit = ((np.abs(arr[:, :, 0] - r) < 12)
                    & (np.abs(arr[:, :, 1] - g) < 12)
                    & (np.abs(arr[:, :, 2] - b) < 12))
            return dark | suit

        mo, ml = _mask("officer"), _mask("lustig")
        iou = float((mo & ml).sum() / (mo | ml).sum())
        self.assertLessEqual(
            iou, 0.78,
            f"officer-lustig silhouette IoU {iou:.3f} (v7: no officer)")

    def test_side_part_is_asymmetric(self):
        # The side-part cap is deeper on the facing side: dark pixels
        # in the cap-edge band, +x vs -x, ratio > 1.05 (a symmetric
        # short cap is ~1.00).
        def _ratio(name):
            ch = make_character_instance(name, height=560)
            img = Image.new("RGB", (600, 700), (255, 255, 255))
            d = ImageDraw.Draw(img, "RGBA")
            standing(ch, 300, 620, facing=1)
            J = draw_character_v4(d, ch, expression="neutral",
                                  view="profile")
            arr = np.asarray(img).sum(axis=2) < 400
            hx, hy = J["head"]
            r = ch.head_r
            band = arr[int(hy - 0.85 * r):int(hy - 0.45 * r),
                       int(hx - r):int(hx + r)]
            mid = band.shape[1] // 2
            return (band[:, mid:].sum()
                    / max(band[:, :mid].sum(), 1))

        self.assertGreater(_ratio("officer"), 1.05)
        self.assertLess(abs(_ratio("minh") - 1.0), 0.05)


if __name__ == "__main__":
    unittest.main()
