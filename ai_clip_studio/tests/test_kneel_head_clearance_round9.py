"""Round 9 (R8-D1): the kneeled head dives toward the grasp point, so a
held prop's edge pressed into the actor's cheek (delivered shot #0,
f12-23, stone centre 3-12 px inside the head disc). The kneel_pick /
bend_pick hand targets are now guarded out of the own-head disc by
the prop's half-extent + margin, reach-aware (the R8-1 hammer
geometry with a prop-sized clearance).

The trigger is the PULLED grasp point (product_renderer._grasp_target
pulls a far ground rest in toward the shoulder, so the grasp happens
mid-air near the face), NOT a ground target: with a target on the
ground the kneeled head stays 120+ px clear and the guard is a no-op
(verified by scan). The unit stagings below therefore use raised
targets that reproduce the pulled-point geometry.
"""

import math
import unittest

from ai_clip_studio.animation import primitives as P
from ai_clip_studio.animation.rig import Stickman

GY = 1000.0


def _rig(h=600.0, root_x=500.0):
    c = Stickman(height=h, template="default")
    c.set_pose(root_x=root_x,
               root_y=GY - (c.u_leg + c.l_leg) * 0.93, facing=1)
    return c


def _hold_state(fn_name, target, flank=None, guard=True):
    """Run the primitive to the hold (u=0.55) and return
    (head, hand_r, head_r, shoulder, reach)."""
    c = _rig()
    orig = P._clear_own_head
    if not guard:
        P._clear_own_head = lambda pos, *a, **k: pos
    try:
        fn = getattr(P, fn_name)(c, target, 1.2, GY, hand="r",
                                 flank_px=flank)
        fn(0.66)
        J = c.joints()
        return (J["head"], J["hand_r"], c.head_r, J["shoulder"],
                0.98 * (c.u_arm + c.l_arm))
    finally:
        P._clear_own_head = orig


class TestKneelPickHeadClearance(unittest.TestCase):
    # Raised target reproducing the pulled-point geometry: unguarded,
    # the hand lands 45 px INSIDE the head disc at the hold.
    TARGET = (700.0, 800.0)
    FLANK = 34.0

    def test_unguarded_hand_enters_disc(self):
        head, hand, hr, _, _ = _hold_state(
            "kneel_pick", self.TARGET, flank=self.FLANK, guard=False)
        dist = math.hypot(hand[0] - head[0], hand[1] - head[1])
        self.assertLess(dist - hr, 0.0,
                        "staging must reproduce R8-D1 unguarded")

    def test_guarded_hand_clears_disc_by_prop_margin(self):
        head, hand, hr, _, _ = _hold_state(
            "kneel_pick", self.TARGET, flank=self.FLANK, guard=True)
        dist = math.hypot(hand[0] - head[0], hand[1] - head[1])
        # Clearance = head_r + flank_px + _s(char, 8) at H=600:
        # 102 + 34 + 8.57 = 144.6 -> dist - head_r == 42.6.
        self.assertAlmostEqual(dist - hr, 42.6, delta=2.0)
        self.assertGreater(dist - hr, self.FLANK,
                           "prop edge (half-extent ~= flank) clears")

    def test_guarded_hand_stays_near_prop_and_in_reach(self):
        head, hand, hr, shoulder, reach = _hold_state(
            "kneel_pick", self.TARGET, flank=self.FLANK, guard=True)
        to_target = math.hypot(hand[0] - self.TARGET[0],
                               hand[1] - self.TARGET[1])
        self.assertLess(to_target, 100.0,
                        "guard moves the hand, it must stay at the prop")
        to_shoulder = math.hypot(hand[0] - shoulder[0],
                                 hand[1] - shoulder[1])
        self.assertLessEqual(to_shoulder, reach)

    def test_guard_is_noop_for_ground_target(self):
        # Ground targets keep the head 120+ px clear: the guard must
        # not move the hand at all (bit-identical hold position).
        _, off, _, _, _ = _hold_state("kneel_pick", (560.0, 994.0),
                                      flank=self.FLANK, guard=False)
        _, on, _, _, _ = _hold_state("kneel_pick", (560.0, 994.0),
                                     flank=self.FLANK, guard=True)
        self.assertEqual(off, on)


class TestBendPickHeadClearance(unittest.TestCase):
    def test_guarded_hand_clears_disc(self):
        # The 77 deg stoop dives the head at a raised target too.
        head, hand, hr, _, _ = _hold_state(
            "bend_pick", (700.0, 800.0), flank=34.0, guard=False)
        off = math.hypot(hand[0] - head[0], hand[1] - head[1]) - hr
        head, hand, hr, _, _ = _hold_state(
            "bend_pick", (700.0, 800.0), flank=34.0, guard=True)
        on = math.hypot(hand[0] - head[0], hand[1] - head[1]) - hr
        self.assertLess(off, 42.6, "staging must engage the guard")
        self.assertAlmostEqual(on, 42.6, delta=2.0)


class TestDeliveredShot0Clearance(unittest.TestCase):
    """Delivered-plan probe: shot #0 (KNEEL_PICK) with the current
    code -- the audit must report zero self-head intrusions and the
    stone must stay clear of the head disc through the grasp span."""

    @classmethod
    def setUpClass(cls):
        import json
        import os
        import subprocess
        import sys
        probe = os.path.expanduser(
            "~/workspace/acceptance_loop/r8_delivered_probe.py")
        out = subprocess.run(
            [sys.executable, probe, "0"],
            cwd=os.path.expanduser("~/workspace/agent"),
            capture_output=True, text=True, timeout=300)
        assert out.returncode == 0, out.stderr[-2000:]
        res_path = os.path.expanduser(
            "~/workspace/acceptance_loop/r8_delivered_shot0/result.json")
        with open(res_path) as fh:
            cls.res = json.load(fh)

    def test_no_self_head_intrusions(self):
        self.assertEqual(self.res.get("head_intrusion_count"), 0)

    def test_stone_clears_head_disc_through_grasp(self):
        worst = None
        for e in self.res["grip_telemetry"]:
            fi = e["frame"]
            if not (8 <= fi <= 28):
                continue
            h = e["hands"]["Linh"]
            hx, hy = h["head"]
            for d in e["draws"]:
                if d.get("pid") != "viên_đá_lửa":
                    continue
                dist = math.hypot(d["x"] - hx, d["y"] - hy)
                gap = dist - h["head_r"]
                if worst is None or gap < worst[1]:
                    worst = (fi, gap)
        self.assertIsNotNone(worst)
        # Stone half-extent is below flank_px (34); a 30 px centre
        # gap keeps the drawn edge out of the disc.
        self.assertGreater(worst[1], 30.0, f"worst frame {worst[0]}")

    def test_stone_still_grasped_in_hand(self):
        held = [e for e in self.res["grip_telemetry"]
                if any(d.get("pid") == "viên_đá_lửa"
                       and d.get("state") in ("GRASPED",
                                              "ATTACHED_TO_HAND")
                       for d in e["draws"])]
        self.assertTrue(held, "stone must reach the hand")
        for e in held:
            h = e["hands"]["Linh"]
            for d in e["draws"]:
                if d.get("pid") != "viên_đá_lửa":
                    continue
                hand = h["hand_r"]
                self.assertLess(
                    math.hypot(d["x"] - hand[0], d["y"] - hand[1]),
                    5.0, "prop must follow the hand, no detachment")


if __name__ == "__main__":
    unittest.main()
