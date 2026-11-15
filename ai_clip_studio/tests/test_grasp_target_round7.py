"""Round-7 grasp clamp: a two-hand pick_up at an unreachable rest
must not collapse both hands onto the reach circle (R6 shot #7 read
one-handed for its whole span). _grasp_target pulls the grasp point
inside arm reach along the same ray; reachable targets return
unchanged.

Frame evidence: probe render of Loop-01 shot #7 under
acceptance_loop/round7_probe_shot7/ (hand separation 88 px through
the lift window after the fix).
"""
import math
import unittest

from ai_clip_studio.product_renderer import _grasp_target


class _FakeChar:
    def __init__(self, head_r=95.0, u_arm=90.0, l_arm=90.0):
        self.head_r = head_r
        self.u_arm = u_arm
        self.l_arm = l_arm


def _ctx(head=(500.0, 300.0), hip=(500.0, 650.0), char=None):
    return {
        "char": char or _FakeChar(),
        "name": "Linh",
        "joints0": {"Linh": {"head": head, "hip": hip}},
    }


class TestGraspTarget(unittest.TestCase):
    def test_reachable_target_unchanged(self):
        # Shoulder = head + spine_unit * head_r = (500, 395);
        # reach = 180. A target 100 px away returns identical.
        target = (560.0, 470.0)
        self.assertEqual(_grasp_target(_ctx(), target, 44.0), target)

    def test_beyond_reach_pulled_in_along_ray(self):
        # Target 320 px from the shoulder, flank 44: the pull-in
        # limit is 0.95*180 - 44 = 127 px from the shoulder, along
        # the shoulder->target ray.
        ctx = _ctx()
        target = (500.0, 395.0 + 320.0)
        got = _grasp_target(ctx, target, 44.0)
        shoulder = (500.0, 395.0)
        dist = math.hypot(got[0] - shoulder[0], got[1] - shoulder[1])
        self.assertAlmostEqual(dist, 0.95 * 180.0 - 44.0, places=6)
        self.assertAlmostEqual(got[0], 500.0, places=6)
        self.assertGreater(got[1], shoulder[1])

    def test_flank_zero_pulls_to_reach_margin(self):
        target = (500.0, 395.0 + 400.0)
        got = _grasp_target(_ctx(), target, 0.0)
        dist = math.hypot(got[0] - 500.0, got[1] - 395.0)
        self.assertAlmostEqual(dist, 0.95 * 180.0, places=6)

    def test_huge_flank_floors_at_45_percent_reach(self):
        # limit = 0.95*180 - 200 < 0.45*180: the pull floors at
        # 45% of reach instead of collapsing onto the shoulder.
        target = (500.0, 395.0 + 400.0)
        got = _grasp_target(_ctx(), target, 200.0)
        dist = math.hypot(got[0] - 500.0, got[1] - 395.0)
        self.assertAlmostEqual(dist, 0.45 * 180.0, places=6)

    def test_missing_joints_returns_target(self):
        ctx = {"char": _FakeChar(), "name": "Linh", "joints0": {}}
        target = (900.0, 100.0)
        self.assertEqual(_grasp_target(ctx, target, 44.0), target)

    def test_broken_ctx_returns_target(self):
        self.assertEqual(_grasp_target({}, (1.0, 2.0), 44.0), (1.0, 2.0))
        self.assertEqual(_grasp_target(None, (1.0, 2.0), 44.0), (1.0, 2.0))


if __name__ == "__main__":
    unittest.main()
