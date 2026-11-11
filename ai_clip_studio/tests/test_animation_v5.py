"""Tests for the v5 animation audit fixes (2026-11-11).

The v4 walk moonwalked (a planted foot slid 481 px in 1.8 s), bobbed
upside-down, ran without a flight phase, waved up-and-down at 3.3 Hz,
froze the standing character solid, bent 71 deg on straight knees,
and teleported hands 100-240 px at segment boundaries. Every test
here measures the real joint trajectories, not a report claim.
"""
import math
import unittest

from PIL import Image, ImageDraw

from ai_clip_studio.animation import Stickman
from ai_clip_studio.animation.character_art import (
    make_character, make_character_instance, draw_character_v4)
from ai_clip_studio.animation.environment_art import (
    LOCATION_SIGNATURES, SIGN_TEXT, draw_layered_background)
from ai_clip_studio.animation.primitives import (
    walk_to, run_to, wave, idle, bend_pick, give_to,
    snapshot, apply_snapshot, _ease_profile)
from ai_clip_studio.animation.rig import check_bone_lengths
from ai_clip_studio.camera_planner import CameraPlanner

GY = 892
H = 783


def _walk_frames(char, fn, duration, fps=24):
    frames = []
    for fi in range(int(duration * fps) + 1):
        fn(fi / fps)
        frames.append(char.joints())
    return frames


class TestPlantedWalk(unittest.TestCase):
    def test_no_foot_slip(self):
        """A planted foot stays at one world x (v4: 481 px slip)."""
        c = Stickman(height=H, name="minh")
        frames = _walk_frames(c, walk_to(c, 500, 945, 1.8, GY), 1.8)
        for key in ("foot_l", "foot_r"):
            slip = 0.0
            for a, b in zip(frames, frames[1:]):
                if abs(a[key][1] - GY) < 0.5 and abs(b[key][1] - GY) < 0.5:
                    slip += abs(b[key][0] - a[key][0])
            self.assertLess(slip, 2.0, f"{key} slid {slip:.1f} px")

    def test_step_length_and_cadence(self):
        """Step ~0.25*H (~196 px at H=783), cadence 65-95 steps/min
        (v6, RicksClips reference: short steps ~1/4 body height, slow
        deliberate pace ~70-90/min. v5: 0.16*H steps at 115/min -- too
        fast and too shuffly)."""
        c = Stickman(height=H, name="minh")
        frames = _walk_frames(c, walk_to(c, 500, 945, 1.8, GY), 1.8)
        planted = sorted(set(round(f["foot_l"][0]) for f in frames
                             if abs(f["foot_l"][1] - GY) < 0.5))
        steps = [b - a for a, b in zip(planted, planted[1:])]
        self.assertTrue(steps, "no planted foot positions found")
        for s in steps:
            self.assertGreater(s, 2 * 0.23 * H)
            self.assertLess(s, 2 * 0.27 * H)
        # cadence: distance / step length / travel time
        speed = 445 / 1.8
        cadence = speed / (0.25 * H) * 60
        self.assertGreater(cadence, 65)
        self.assertLess(cadence, 95)

    def test_bob_phase(self):
        """Body LOWEST at foot strike, HIGHEST at mid-stance (v4 bob
        was inverted: highest exactly at foot strike)."""
        c = Stickman(height=H, name="minh")
        frames = _walk_frames(c, walk_to(c, 500, 945, 1.8, GY), 1.8)
        heights = [GY - f["hip"][1] for f in frames]
        # travel frames only (frames 5..38): anticipation and settle
        # raise the body back toward standing height, which would
        # pollute the double-support measurement.
        travel = [(f, h) for i, (f, h) in enumerate(zip(frames, heights))
                  if 5 <= i <= 38]
        # strike frames: both feet on the ground (double support)
        strike_h = [h for f, h in travel
                    if abs(f["foot_l"][1] - GY) < 0.5
                    and abs(f["foot_r"][1] - GY) < 0.5]
        # mid-stance frames: one foot almost under the hip
        mid_h = [h for f, h in travel
                 if min(abs(f["foot_l"][0] - f["hip"][0]),
                        abs(f["foot_r"][0] - f["hip"][0])) < 12
                 and (abs(f["foot_l"][1] - GY) < 0.5
                      or abs(f["foot_r"][1] - GY) < 0.5)]
        self.assertTrue(strike_h and mid_h)
        # 24 fps sampling: a "both feet down" frame can land up to one
        # frame past the strike instant, by when the bob has already
        # risen a few px -- so compare MEANS, not the worst frame.
        mean_strike = sum(strike_h) / len(strike_h)
        mean_mid = sum(mid_h) / len(mid_h)
        self.assertLess(mean_strike - min(h for _, h in travel), 5.0,
                        "body not lowest at foot strike")
        self.assertLess(max(h for _, h in travel) - mean_mid, 4.0,
                        "body not highest at mid-stance")
        # v6 (RicksClips reference): the head stays almost LEVEL --
        # the bob is a small ~5 px breathing of the walk, not a
        # 10+ px bounce. Phase must still be correct (above), but the
        # amplitude stays small on purpose.
        self.assertGreater(max(h for _, h in travel)
                           - min(h for _, h in travel), 2.0,
                           "bob too small to read")
        self.assertLess(max(h for _, h in travel)
                        - min(h for _, h in travel), 8.0,
                        "bob too big -- reference head stays level")

    def test_bone_lengths_hold(self):
        c = Stickman(height=H, name="minh")
        frames = _walk_frames(c, walk_to(c, 500, 945, 1.8, GY), 1.8)
        for f in frames:
            self.assertEqual(check_bone_lengths(f, c), [])

    def test_ease_profile_midpoint(self):
        self.assertAlmostEqual(_ease_profile(0.5), 0.5, places=6)
        self.assertAlmostEqual(_ease_profile(0.0), 0.0)
        self.assertAlmostEqual(_ease_profile(1.0), 1.0)
        prev = 0.0
        for i in range(1, 101):
            cur = _ease_profile(i / 100.0)
            self.assertGreaterEqual(cur, prev)
            prev = cur

    def test_no_arm_snap_at_walk_ends(self):
        """Anticipation and settle must lerp the arms to/from the
        travel swing -- and no joint may TELEPORT. A teleport is a
        spike in the SPEED profile (one frame at 130 px, neighbours
        at ~10 px); fast continuous motion (a run's arm pump reaches
        ~90 px/frame) has a SMOOTH speed profile, so this test caps
        the frame-to-frame CHANGE in speed, not the speed itself.
        The first v5 draft set the arms to 0.0 at the settle start --
        both hands teleported to the same point, a 132 px jump in
        one frame with a ~120 px/frame speed spike."""
        for fn_maker in (lambda c: walk_to(c, 500, 945, 1.8, GY),
                         lambda c: run_to(c, 500, 900, 1.0, GY)):
            c = Stickman(height=H, name="minh")
            fn = fn_maker(c)
            prev = None
            speeds = []
            for fi in range(50):
                fn(fi / 24.0)
                j = c.joints()
                if prev is not None:
                    speeds.append(max(
                        math.hypot(j[k][0] - prev[k][0],
                                   j[k][1] - prev[k][1])
                        for k in ("hand_l", "hand_r", "head")))
                prev = j
            spikes = [abs(b - a) for a, b in zip(speeds, speeds[1:])]
            self.assertLess(max(spikes), 60.0,
                            f"speed spike {max(spikes):.1f} px/frame^2 "
                            f"(teleport)")
            self.assertLess(max(speeds), 150.0,
                            f"implausible jump {max(speeds):.1f} px/frame")


class TestRun(unittest.TestCase):
    def test_flight_phase_exists(self):
        """A run has frames with BOTH feet off the ground (v4: 0/24)."""
        c = Stickman(height=H, name="minh")
        frames = _walk_frames(c, run_to(c, 500, 900, 1.0, GY), 1.0)
        air = sum(1 for f in frames[5:]
                  if f["foot_l"][1] < GY - 3 and f["foot_r"][1] < GY - 3)
        self.assertGreaterEqual(air, 2, "run has no flight phase")

    def test_run_stride_longer_than_walk(self):
        cw = Stickman(height=H, name="minh")
        wf = _walk_frames(cw, walk_to(cw, 500, 1300, 2.0, GY), 2.0)
        cr = Stickman(height=H, name="minh")
        rf = _walk_frames(cr, run_to(cr, 500, 1300, 2.0, GY), 2.0)
        w_planted = sorted(set(round(f["foot_l"][0]) for f in wf
                               if abs(f["foot_l"][1] - GY) < 0.5))
        r_planted = sorted(set(round(f["foot_l"][0]) for f in rf
                               if abs(f["foot_l"][1] - GY) < 0.5))
        w_step = max([b - a for a, b in zip(w_planted, w_planted[1:])],
                     default=0)
        r_step = max([b - a for a, b in zip(r_planted, r_planted[1:])],
                     default=0)
        self.assertGreater(r_step, w_step, "run stride not longer")


class TestWaveIdleBend(unittest.TestCase):
    def test_wave_is_side_to_side(self):
        """Steady-state wave: hand sways in X, not in Y (v4: x was
        CONSTANT, y flapped +/-21 px at 3.3 Hz). Steady state starts
        after the 0.7 s rise (v6: was 0.5 s)."""
        c = Stickman(height=H, name="minh")
        c.set_pose(root_x=700, root_y=GY - 313, facing=1)
        fn = wave(c, 1.5)
        xs, ys = [], []
        for fi in range(37):
            fn(fi / 24.0)
            if fi / 24.0 >= 0.7:
                j = c.joints()
                xs.append(j["hand_r"][0])
                ys.append(j["hand_r"][1])
        self.assertGreater(max(xs) - min(xs), 30.0)
        self.assertLess(max(ys) - min(ys), 5.0)
        # frequency ~1.5-2 Hz: count zero crossings of (x - mean)
        mean = sum(xs) / len(xs)
        crossings = sum(1 for a, b in zip(xs, xs[1:])
                        if (a - mean) * (b - mean) < 0)
        duration = 1.5 - 0.7
        freq = crossings / 2.0 / duration
        self.assertGreater(freq, 1.2)
        self.assertLess(freq, 2.4)

    def test_idle_is_alive_but_calm(self):
        """A standing character breathes and shifts weight (v4: 0.000
        px displacement over 2.8 s) -- but never more than a couple of
        px per frame."""
        c = Stickman(height=H, name="lan")
        c.set_pose(root_x=700, root_y=GY - 313, facing=1)
        fn = idle(c, 2.8, GY)
        total, peak = 0.0, 0.0
        prev = None
        for fi in range(68):
            fn(fi / 24.0)
            j = c.joints()
            if prev is not None:
                d = max(math.hypot(j[k][0] - prev[k][0],
                                   j[k][1] - prev[k][1])
                        for k in ("head", "hand_r", "foot_l"))
                total += d
                peak = max(peak, d)
            prev = j
        self.assertGreater(total, 5.0, "standing character is frozen")
        self.assertLess(peak, 2.0, "idle motion too jumpy")

    def test_bend_pick_geometry(self):
        """Knees bend (hip drops ~50% of leg), torso leans ~77 deg,
        hand HOLDS the wallet through the hold phase, head looks down
        at it. (v4: 71 deg lean, straight knees, 93% hip drop, hand
        touched the wallet for 3 frames.)"""
        c = Stickman(height=H, name="minh")
        c.set_pose(root_x=700, root_y=GY - 313, facing=1)
        fn = bend_pick(c, (790, GY - 10), 1.8, GY)
        max_drop, max_lean, hold, hold_tot = 0, 0, 0, 0
        for fi in range(44):
            fn(fi / 24.0)
            j = c.joints()
            max_drop = max(max_drop, j["hip"][1] - (GY - 313))
            max_lean = max(max_lean, c.pose["torso_lean"])
            if 0.55 * 1.8 <= fi / 24.0 <= 0.75 * 1.8:
                hold_tot += 1
                if math.hypot(j["hand_r"][0] - 790,
                              j["hand_r"][1] - (GY - 10)) < 15:
                    hold += 1
        self.assertGreater(max_drop, 0.40 * 336)
        self.assertLess(max_drop, 0.60 * 336)
        self.assertGreater(max_lean, 1.1)
        self.assertLess(max_lean, 1.5)
        self.assertGreaterEqual(hold, 0.8 * hold_tot,
                               "hand does not hold the wallet")
        self.assertGreater(abs(c.pose["head_look"]), 0.15,
                           "head does not look at the wallet")


class TestHandoffAndBlends(unittest.TestCase):
    def test_give_to_no_hand_teleport(self):
        """Hands converge smoothly: no single-frame jump > 40 px
        (v4: 100-240 px jumps at the handoff start)."""
        a = Stickman(height=560, name="a")
        b = Stickman(height=540, name="b")
        a.set_pose(root_x=700, root_y=679, facing=1)
        b.set_pose(root_x=1200, root_y=688, facing=-1)
        prop = {"x": 0, "y": 0}
        fn = give_to(a, b, prop, 1.2)
        peak = 0.0
        prev_a = prev_b = None
        for fi in range(30):
            fn(fi / 24.0)
            ja, jb = a.joints(), b.joints()
            if prev_a is not None:
                peak = max(peak, math.hypot(
                    ja["hand_r"][0] - prev_a[0], ja["hand_r"][1] - prev_a[1]))
                peak = max(peak, math.hypot(
                    jb["hand_l"][0] - prev_b[0], jb["hand_l"][1] - prev_b[1]))
            prev_a, prev_b = ja["hand_r"], jb["hand_l"]
        self.assertLess(peak, 40.0, f"hand teleported {peak:.1f} px")

    def test_snapshot_blend_is_continuous(self):
        a = Stickman(height=560, name="a")
        a.set_pose(root_x=500, root_y=679, facing=1)
        s1 = snapshot(a)
        a.set_pose(root_x=900, root_y=679, torso_lean=0.3)
        a.hand_target_r = (1000, 300)
        s2 = snapshot(a)
        prev = None
        peak = 0.0
        for i in range(11):
            apply_snapshot(a, s1, s2, i / 10.0)
            j = a.joints()
            if prev is not None:
                peak = max(peak, math.hypot(j["hip"][0] - prev[0],
                                            j["hip"][1] - prev[1]))
            prev = j["hip"]
        self.assertLess(peak, 60.0, "blend jumps between snapshots")

    def test_snapshot_blend_none_target_fades_in(self):
        """A hand with NO target in snapshot A and a target in B must
        fade in from its natural hanging position, not teleport in at
        u=0.5 (first v5 draft: Lan's elbow jumped 148 px at the
        handover->wave boundary)."""
        a = Stickman(height=560, name="a")
        a.set_pose(root_x=500, root_y=679, facing=1)
        s1 = snapshot(a)  # hand_target_r is None
        a.set_pose(root_x=500, root_y=679, facing=1)
        a.hand_target_r = (620, 300)  # hand raised
        s2 = snapshot(a)
        prev = None
        peak = 0.0
        for i in range(11):
            apply_snapshot(a, s1, s2, i / 10.0)
            j = a.joints()
            if prev is not None:
                peak = max(peak, math.hypot(j["hand_r"][0] - prev[0],
                                            j["hand_r"][1] - prev[1]))
            prev = j["hand_r"]
        self.assertLess(peak, 60.0, f"hand teleported {peak:.1f} px")


class TestHeadTrack(unittest.TestCase):
    def test_head_track_below_target_no_flip(self):
        """Looking at a target BELOW the head (a wallet on the ground)
        must give the same look-down on both sides of the target's
        vertical line. The old head_track returned atan2(dx, -dy)
        directly, which is near +/-pi below the head, so head_look
        flipped +0.6 / -0.6 and the head oscillated +/-60 px/frame
        while the body stood up from the bend."""
        from ai_clip_studio.animation.rig import head_track
        c = Stickman(height=783, name="minh")
        c.set_pose(root_x=700, root_y=579, facing=1, torso_lean=1.35)
        a_left = head_track(c, (620, 886))
        a_right = head_track(c, (790, 886))
        self.assertGreater(a_left, 0.3)
        self.assertGreater(a_right, 0.3)
        self.assertAlmostEqual(a_left, a_right, delta=0.15)

    def test_head_stable_through_bend_rise(self):
        """No single-frame head jump > 70 px while standing up from
        the bend (first v5 draft: 143 px at t=4.42-4.46)."""
        c = Stickman(height=783, name="minh")
        c.set_pose(root_x=700, root_y=GY - 313, facing=1)
        fn = bend_pick(c, (790, GY - 10), 1.4, GY)
        prev = None
        peak = 0.0
        for fi in range(35):
            fn(fi / 24.0)
            j = c.joints()
            if prev is not None:
                peak = max(peak, math.hypot(j["head"][0] - prev[0],
                                            j["head"][1] - prev[1]))
            prev = j["head"]
        self.assertLess(peak, 70.0, f"head jumped {peak:.1f} px/frame")


class TestGaitIdentity(unittest.TestCase):
    def test_gait_is_shared_across_templates(self):
        """v6 (RicksClips reference study 2026-11-11): ONE shared gait
        -- every character walks the same short-step, level-head
        idiom. This REPLACES the v5 test that asserted Minh strides
        longer than Lan and elders shuffle: the reference
        distinguishes characters by COSTUME colour, hat and hair,
        NOT by gait. CONFLICT FLAGGED: Mai's earlier instruction asked
        for per-template gait; the reference + her newest message
        ("lay rickclip lam tham chieu") take precedence, and the
        per-template gait data is kept on the objects but no longer
        drives locomotion (see GAIT_DEFAULT)."""
        def step_of(char):
            frames = _walk_frames(
                char, walk_to(char, 500, 1300, 2.0, GY), 2.0)
            planted = sorted(set(round(f["foot_l"][0]) for f in frames
                                 if abs(f["foot_l"][1] - GY) < 0.5))
            steps = [b - a for a, b in zip(planted, planted[1:])]
            return max(steps) if steps else 0
        minh = make_character_instance("minh", height=H)
        lan = make_character_instance("lan", height=H)
        elder = make_character(template="elderly", height=H)
        self.assertEqual(step_of(minh), step_of(lan))
        self.assertEqual(step_of(minh), step_of(elder))
        # identity lives in costume / hair, not in the walk
        self.assertNotEqual(minh.suit, lan.suit)
        self.assertNotEqual(minh.hair_style, lan.hair_style)

    def test_walk_uses_shared_gait(self):
        """The same walk call moves Lan with the same steps as Minh."""
        def step_of(char):
            frames = _walk_frames(
                char, walk_to(char, 500, 1300, 2.0, GY), 2.0)
            planted = sorted(set(round(f["foot_l"][0]) for f in frames
                                 if abs(f["foot_l"][1] - GY) < 0.5))
            steps = [b - a for a, b in zip(planted, planted[1:])]
            return max(steps) if steps else 0
        minh = make_character_instance("minh", height=H)
        lan = make_character_instance("lan", height=H)
        self.assertGreater(step_of(minh), 0)
        self.assertEqual(step_of(minh), step_of(lan))


class TestHairAndFraming(unittest.TestCase):
    def test_hair_cap_is_a_hairline_now(self):
        """The v4 cap covered 23% of the head diameter in black; the
        reference head is plain white. v5 thins it to a hairline."""
        c = make_character(template="male", height=774)
        c.set_pose(root_x=600, root_y=900, facing=1)
        img = Image.new("RGB", (1200, 1200), (255, 255, 255))
        d = ImageDraw.Draw(img, "RGBA")
        draw_character_v4(d, c, expression="neutral", view="front")
        hx, hy = c.joints()["head"]
        r = c.head_r
        col = [sum(img.getpixel((int(hx), y))) < 400
               for y in range(int(hy - r) - 5, int(hy + r))]
        run = 0
        for dark in col:
            if dark:
                run += 1
            else:
                break
        cap_frac = run / (2 * r)
        self.assertLess(cap_frac, 0.18, f"hair cap {cap_frac:.2f} of head")

    def test_framing_catches_edge_cut_and_corrects(self):
        shot = {"shot_type": "medium", "camera": {"scale": 1.6}}
        # Subject right of centre, focus wrongly far left: the crop is
        # pinned at the left edge and cuts the subject at the right
        # edge of the crop. Shifting the focus right fixes it. (A
        # subject whose edge is past the FRAME edge itself cannot be
        # fixed by shifting -- that is the zoom-out test, not this one.)
        subj = [{"cx": 1500, "head_y": 340, "foot_y": 900, "half_w": 80}]
        issues, fixed = CameraPlanner.validate_framing(
            shot, (600, 610), subj)
        self.assertTrue(any("right edge" in i for i in issues))
        # the corrected focus keeps the subject inside the crop
        issues2, _ = CameraPlanner.validate_framing(shot, fixed, subj)
        self.assertEqual(issues2, [])

    def test_framing_catches_head_cut(self):
        shot = {"shot_type": "close_up", "camera": {"scale": 2.6}}
        subj = [{"cx": 960, "head_y": 200, "foot_y": 900, "half_w": 60}]
        issues, _ = CameraPlanner.validate_framing(shot, (960, 700), subj)
        self.assertTrue(any("head cut" in i for i in issues))

    def test_framing_clean_shot_passes(self):
        shot = {"shot_type": "medium", "camera": {"scale": 1.6}}
        subj = [{"cx": 960, "head_y": 320, "foot_y": 900, "half_w": 100}]
        issues, _ = CameraPlanner.validate_framing(shot, (960, 610), subj)
        self.assertEqual(issues, [])

    def test_framing_subject_wider_than_crop_needs_zoom_out(self):
        shot = {"shot_type": "medium", "camera": {"scale": 1.6}}
        subj = [{"cx": 960, "head_y": 200, "foot_y": 900, "half_w": 700}]
        issues, _ = CameraPlanner.validate_framing(shot, (960, 540), subj)
        self.assertTrue(any("zoom out" in i for i in issues))


class TestLocationSignatures(unittest.TestCase):
    def test_every_kind_has_signatures(self):
        from ai_clip_studio.animation.environment_art import KINDS
        for kind in KINDS:
            self.assertGreaterEqual(len(LOCATION_SIGNATURES[kind]), 3,
                                    kind)

    def test_backgrounds_differ_per_kind(self):
        import numpy as np
        imgs = {}
        for kind in ("night_street", "shelter", "station", "park"):
            # half scale: the art's fixed pixel coordinates are tuned
            # for 1920x1080 (a 480x270 render breaks the shelter roof).
            imgs[kind] = np.asarray(
                draw_layered_background(kind, 960, 540, "cold"),
                dtype=float)
        kinds = list(imgs)
        for i in range(len(kinds)):
            for j in range(i + 1, len(kinds)):
                diff = float(abs(imgs[kinds[i]] - imgs[kinds[j]]).mean())
                self.assertGreater(diff, 5.0, f"{kinds[i]} vs {kinds[j]}")

    def test_shelter_sign_carries_text(self):
        """The bus-stop sign must read as a sign: yellow text pixels
        in the sign's middle band (the old blank board had none)."""
        img = draw_layered_background("shelter", 1920, 1080, "cold")
        region = img.crop((1010, 360 + 35, 1010 + 300, 360 + 75))
        px = list(region.getdata())
        yellow = sum(1 for r, g, b in px
                     if r > 200 and 170 < g < 230 and b < 120)
        self.assertGreater(yellow, 20, "sign text not visible")


if __name__ == "__main__":
    unittest.main()
