"""Animation v6 tests -- the backwards-walk audit (2026-11-11).

Mai reported the character "walks backwards" in every motion test.
The v5 audit measured foot slide / cadence / bob / flight but NEVER
checked facing-vs-travel, so the real bug shipped: the FACE pointed
the right way (facing=+1 while moving right, 0 backwards frames) but
the LIMBS moved in reverse --

  * knees bent BACKWARD: the IK knee used bend=f, which puts the knee
    60-110 px BEHIND the hip->foot line in every walk frame (a knee
    must be ON the line when planted, AHEAD of it when swinging);
  * arms swung IPSILATERALLY: the arm on the same side as the forward
    leg swung forward (37/51 walk frames), where a real walk is
    contralateral (opposite arm forward).

These tests would have caught both. They assert on the RIG (joint
positions), not on a video, so they run in milliseconds.
"""
import math
import unittest

from ai_clip_studio.animation.character_art import (
    make_character_instance, resolve_view)
from ai_clip_studio.animation.primitives import (
    walk_to, run_to, turn_to, wave, kneel_pick, bend_pick)
from ai_clip_studio.animation.rig import smoothstep

GY = 900
H = 783


def _knee_forward_offset(J, side, facing):
    """Signed distance of the knee from the hip->foot line, in the
    facing direction (+ = knee ahead of the line = correct)."""
    hx, hy = J["hip"]
    fx, fy = J[f"foot_{side}"]
    kx, ky = J[f"knee_{side}"]
    if abs(fy - hy) < 1e-6:
        return 0.0
    line_x = hx + (fx - hx) * (ky - hy) / (fy - hy)
    return (kx - line_x) * facing


def _sample_walk(fn, dur, fps=24):
    rows = []
    for fi in range(int(dur * fps) + 1):
        fn(fi / fps)
        rows.append(None)  # placeholder, replaced by caller
    return rows


class TestFacingFollowsTravel(unittest.TestCase):
    """The test the v5 audit never ran: facing must equal the sign of
    the travel velocity on every travelling frame."""

    def _facing_vs_travel(self, fn, char, dur, fps=24):
        prev_x, bad, travelling = None, [], 0
        for fi in range(int(dur * fps) + 1):
            fn(fi / fps)
            x = char.pose["root_x"]
            f = char.pose["facing"]
            if prev_x is not None and abs(x - prev_x) > 0.5:
                travelling += 1
                if (x - prev_x > 0) != (f > 0):
                    bad.append((fi, round(x - prev_x, 1), f))
            prev_x = x
        return travelling, bad

    def test_walk_right_faces_right(self):
        c = make_character_instance("minh", height=H)
        fn = walk_to(c, 125, 570, 2.1, GY)
        travelling, bad = self._facing_vs_travel(fn, c, 2.1)
        self.assertGreater(travelling, 20)
        self.assertEqual(bad, [], f"backwards frames: {bad[:5]}")

    def test_walk_left_faces_left(self):
        c = make_character_instance("minh", height=H)
        fn = walk_to(c, 570, 125, 2.1, GY)
        travelling, bad = self._facing_vs_travel(fn, c, 2.1)
        self.assertGreater(travelling, 20)
        self.assertEqual(bad, [], f"backwards frames: {bad[:5]}")

    def test_run_right_faces_right(self):
        c = make_character_instance("minh", height=H)
        fn = run_to(c, 570, 918, 1.1, GY)
        travelling, bad = self._facing_vs_travel(fn, c, 1.1)
        self.assertGreater(travelling, 10)
        self.assertEqual(bad, [], f"backwards frames: {bad[:5]}")

    def test_walk_left_then_right_faces_each_way(self):
        c = make_character_instance("minh", height=H)
        fn1 = walk_to(c, 570, 125, 1.5, GY)
        _, bad1 = self._facing_vs_travel(fn1, c, 1.5)
        fn2 = walk_to(c, 125, 570, 1.5, GY)
        _, bad2 = self._facing_vs_travel(fn2, c, 1.5)
        self.assertEqual(bad1, [])
        self.assertEqual(bad2, [])


class TestKneesBendForward(unittest.TestCase):
    """A knee must sit ON the hip->foot line when the leg is planted
    straight, and AHEAD of it when the leg swings. Behind the line =
    the leg bends backwards (flamingo / walking in reverse)."""

    def test_walk_knees_never_behind_line(self):
        c = make_character_instance("minh", height=H)
        fn = walk_to(c, 125, 570, 2.1, GY)
        worst = 0.0
        for fi in range(int(2.1 * 24) + 1):
            fn(fi / 24)
            J = c.joints()
            f = J["facing"]
            for side in ("l", "r"):
                off = _knee_forward_offset(J, side, f)
                worst = min(worst, off)
        self.assertGreaterEqual(
            worst, -15.0,
            f"a knee sat {worst:.1f}px BEHIND the hip->foot line")

    def test_run_knees_never_behind_line(self):
        c = make_character_instance("minh", height=H)
        fn = run_to(c, 570, 918, 1.1, GY)
        worst = 0.0
        for fi in range(int(1.1 * 24) + 1):
            fn(fi / 24)
            J = c.joints()
            f = J["facing"]
            for side in ("l", "r"):
                worst = min(worst, _knee_forward_offset(J, side, f))
        self.assertGreaterEqual(
            worst, -15.0,
            f"a knee sat {worst:.1f}px BEHIND the hip->foot line")

    def test_planted_straight_leg_knee_on_line(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=500, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        c.foot_target_l = (500 - 60, GY)
        c.foot_target_r = (500 + 60, GY)
        J = c.joints()
        for side in ("l", "r"):
            off = _knee_forward_offset(J, side, 1)
            self.assertGreaterEqual(off, -15.0)
            self.assertLessEqual(off, 60.0)


class TestArmsContralateral(unittest.TestCase):
    """A real walk is contralateral: the arm opposite the forward leg
    swings forward. Same-side (ipsilateral) swing is the other half
    of the backwards-walk look."""

    def _count(self, fn, char, dur, fps=24):
        contra = ipsi = 0
        for fi in range(int(dur * fps) + 1):
            fn(fi / fps)
            J = char.joints()
            hip_x, sh_x = J["hip"][0], J["shoulder"][0]
            if abs(J["foot_r"][0] - J["foot_l"][0]) < 15:
                continue
            if abs(J["hand_r"][0] - J["hand_l"][0]) < 15:
                continue
            lead = "r" if J["foot_r"][0] > J["foot_l"][0] else "l"
            fwd = "r" if J["hand_r"][0] > J["hand_l"][0] else "l"
            if lead != fwd:
                contra += 1
            else:
                ipsi += 1
        return contra, ipsi

    def test_walk_arms_contralateral(self):
        c = make_character_instance("minh", height=H)
        fn = walk_to(c, 125, 570, 2.1, GY)
        contra, ipsi = self._count(fn, c, 2.1)
        self.assertGreater(contra, 0)
        self.assertLess(ipsi, contra,
                        f"arms swing same-side: contra={contra} ipsi={ipsi}")

    def test_run_arms_contralateral(self):
        c = make_character_instance("minh", height=H)
        fn = run_to(c, 570, 918, 1.1, GY)
        contra, ipsi = self._count(fn, c, 1.1)
        self.assertGreater(contra, 0)
        self.assertLess(ipsi, contra,
                        f"arms swing same-side: contra={contra} ipsi={ipsi}")


class TestVisibleTurn(unittest.TestCase):
    """Turning must be a visible rotation through front view, never an
    instant facing flip."""

    def test_turn_to_flips_at_midpoint_not_at_start(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(facing=1)
        fn = turn_to(c, -1, duration=0.4)
        fn(0.0)
        self.assertEqual(c.pose["facing"], 1)
        self.assertEqual(c.pose["turn_u"], 0.0)
        fn(0.1)
        self.assertEqual(c.pose["facing"], 1)
        self.assertGreater(c.pose["turn_u"], 0.0)
        self.assertLess(c.pose["turn_u"], 0.5)
        fn(0.2)
        self.assertEqual(c.pose["facing"], -1)
        fn(0.4)
        self.assertEqual(c.pose["facing"], -1)
        self.assertEqual(c.pose["turn_u"], 1.0)

    def test_turn_to_noop_when_already_facing(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(facing=-1)
        fn = turn_to(c, -1, duration=0.4)
        fn(0.2)
        self.assertEqual(c.pose["facing"], -1)
        self.assertEqual(c.pose["turn_u"], 0.0)

    def test_resolve_view_front_at_mid_turn(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(turn_u=0.0)
        self.assertEqual(resolve_view(c), "profile")
        c.set_pose(turn_u=0.5)
        self.assertEqual(resolve_view(c), "front")
        c.set_pose(turn_u=0.25)
        self.assertEqual(resolve_view(c), "three_quarter")
        c.set_pose(turn_u=1.0)
        self.assertEqual(resolve_view(c), "profile")

    def test_walk_auto_turns_when_facing_wrong_way(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=125, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=-1)
        fn = walk_to(c, 125, 570, 2.1, GY)
        fn(0.0)
        self.assertEqual(c.pose["facing"], -1,
                         "walk must not snap facing at t=0")
        fn(0.1)  # mid-anticipation: turn in progress, root not moving
        self.assertGreater(c.pose["turn_u"], 0.0)
        self.assertEqual(c.pose["root_x"], 125)
        fn(0.25)  # past anticipation: turn complete, facing travel
        self.assertEqual(c.pose["facing"], 1)
        self.assertEqual(c.pose["turn_u"], 0.0)


class TestKneelPick(unittest.TestCase):
    """The kneeling pickup: back knee ON the ground, torso ~52 deg
    (not the 77 deg near-horizontal stoop), hand on the prop."""

    def _run(self, fn, c, dur, fps=24):
        rows = []
        for fi in range(int(dur * fps) + 1):
            fn(fi / fps)
            rows.append((fi / fps, c.joints(),
                         dict(c.pose)))
        return rows

    def test_kneel_back_knee_on_ground(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=918, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        fn = kneel_pick(c, (1001, GY - 6), 1.4, GY)
        rows = self._run(fn, c, 1.4)
        # at full kneel (hold phase, u in 0.5..0.65) the back knee
        # (left leg, opposite the reaching right hand) touches ground
        worst = None
        for t, J, _ in rows:
            if 0.7 <= t <= 0.91:
                gap = GY - J["knee_l"][1]
                worst = gap if worst is None else max(worst, gap)
        self.assertIsNotNone(worst)
        self.assertLessEqual(worst, 20.0,
                             f"back knee floats {worst:.1f}px above ground")

    def test_kneel_lean_under_70_degrees(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=918, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        fn = kneel_pick(c, (1001, GY - 6), 1.4, GY)
        rows = self._run(fn, c, 1.4)
        leans = []
        for _, J, _ in rows:
            dx = J["shoulder"][0] - J["hip"][0]
            dy = J["hip"][1] - J["shoulder"][1]
            leans.append(math.degrees(math.atan2(dx, dy)))
        self.assertLess(max(leans), 70.0,
                        f"kneel leans {max(leans):.1f} deg (stoop was 77)")
        self.assertGreater(max(leans), 55.0,
                           "kneel too upright to reach the ground prop")

    def test_kneel_hand_reaches_and_holds(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=918, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        fn = kneel_pick(c, (1001, GY - 6), 1.4, GY)
        rows = self._run(fn, c, 1.4)
        hold = 0
        for _, J, _ in rows:
            hx, hy = J["hand_r"]
            if math.hypot(hx - 1001, hy - (GY - 6)) < 15:
                hold += 1
        self.assertGreaterEqual(hold, 9,
                                f"hand held the wallet only {hold} frames")


class TestWaveElbowEased(unittest.TestCase):
    """v5: the elbow swung 87.8 px in one frame on the wave rise.
    The 0.7 s rise must keep it under 70 px/frame."""

    def test_wave_elbow_max_step(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=1113, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        fn = wave(c, 1.1)
        prev = None
        worst = 0.0
        for fi in range(int(1.1 * 24) + 1):
            fn(fi / 24)
            J = c.joints()
            if prev is not None:
                d = math.hypot(J["elbow_r"][0] - prev[0],
                               J["elbow_r"][1] - prev[1])
                worst = max(worst, d)
            prev = J["elbow_r"]
        self.assertLess(worst, 70.0,
                        f"wave elbow still swings {worst:.1f}px/frame")


class TestStalePrewarmCapture(unittest.TestCase):
    """v6: a primitive pre-warmed in one pose and run later, after
    another segment moved the character, must re-capture its start
    state instead of teleporting the hand from the stale capture.
    (The v6 render pre-warmed wave() in the standing pose, ran it
    after the handover, and the hand jumped 94 px in one frame.)"""

    def test_wave_recaptures_after_prewarm_in_wrong_pose(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=1113, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        fn = wave(c, 1.1)
        fn(0.0)  # pre-warm in the standing pose
        # another segment moves the hand far away (handover midpoint)
        c.hand_target_r = (1300, 400)
        # NOTE: prev starts at the MOVED hand, not None -- the jump
        # that matters is from the hand's position when the primitive
        # takes over to where the primitive puts it on frame 1. (The
        # first version of this test left prev=None on frame 0 and so
        # passed while the guard it was testing was broken.)
        prev = c.joints()["hand_r"]
        worst = 0.0
        for fi in range(int(1.1 * 24) + 1):
            fn(fi / 24)
            J = c.joints()
            worst = max(worst, math.hypot(
                J["hand_r"][0] - prev[0], J["hand_r"][1] - prev[1]))
            prev = J["hand_r"]
        self.assertLess(worst, 70.0,
                        f"wave hand jumped {worst:.1f}px/frame after stale pre-warm")


class TestBendPickStillWorks(unittest.TestCase):
    """The old stoop still exists (callers may use it); the knee fix
    must not break its hand contact."""

    def test_bend_pick_hand_holds(self):
        c = make_character_instance("minh", height=H)
        c.set_pose(root_x=918, root_y=GY - (c.u_leg + c.l_leg) * 0.93,
                   facing=1)
        fn = bend_pick(c, (1001, GY - 6), 1.4, GY)
        hold = 0
        for fi in range(int(1.4 * 24) + 1):
            fn(fi / 24)
            J = c.joints()
            if math.hypot(J["hand_r"][0] - 1001,
                          J["hand_r"][1] - (GY - 6)) < 15:
                hold += 1
        self.assertGreaterEqual(hold, 9)


if __name__ == "__main__":
    unittest.main()
