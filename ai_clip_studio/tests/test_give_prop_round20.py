"""Round 20 (R18-F1): in give_to the prop travels from the
giver's DRAWN hand to the receiver's DRAWN hand (lerped by u),
instead of sitting at the meeting point from u=0 while the
hands are still travelling to it. (The state-machine
TRANSFERRED path already lerps between the live hands; this
mirrors that rule for the legacy primitive.)
"""
import math
import unittest

from ai_clip_studio.animation.primitives import Stickman, give_to


def _pair():
    # A-S7-realistic staging: partners within combined arm
    # reach (250 px apart; reaches ~158 + ~152 px).
    a = Stickman(height=560, name="a")
    b = Stickman(height=540, name="b")
    a.set_pose(root_x=700, root_y=679, facing=1)
    b.set_pose(root_x=950, root_y=688, facing=-1)
    return a, b


class TestGivePropFollowsHands(unittest.TestCase):
    def test_prop_travels_hand_to_hand(self):
        a, b = _pair()
        prop = {"x": 0, "y": 0}
        fn = give_to(a, b, prop, 1.2)
        prev = None
        peak_step = 0.0
        for fi in range(30):
            fn(fi / 24.0)
            gh = a.joints()["hand_r"]
            rh = b.joints()["hand_l"]
            # The prop sits ON the segment between the drawn
            # hands (+10 scaled px below it): at the giver's
            # hand when u=0, at the receiver's when u=1.
            seg = math.hypot(rh[0] - gh[0], rh[1] - gh[1])
            d1 = math.hypot(prop["x"] - gh[0],
                            prop["y"] - (gh[1] + 10.0))
            d2 = math.hypot(prop["x"] - rh[0],
                            prop["y"] - (rh[1] + 10.0))
            self.assertLess(abs((d1 + d2) - seg), 5.0,
                            f"frame {fi}: prop off the hand segment")
            if prev is not None:
                peak_step = max(peak_step, math.hypot(
                    prop["x"] - prev[0], prop["y"] - prev[1]))
            prev = (prop["x"], prop["y"])
        self.assertLess(peak_step, 40.0,
                        f"prop teleported {peak_step:.1f} px")

    def test_prop_endpoints_are_the_hands(self):
        a, b = _pair()
        prop = {"x": 0, "y": 0}
        fn = give_to(a, b, prop, 1.2)
        fn(0.0)
        gh = a.joints()["hand_r"]
        self.assertAlmostEqual(prop["x"], gh[0], delta=5.0)
        self.assertAlmostEqual(prop["y"], gh[1] + 10.0, delta=5.0)
        start = (prop["x"], prop["y"])
        fn(1.2)
        rh = b.joints()["hand_l"]
        self.assertAlmostEqual(prop["x"], rh[0], delta=5.0)
        self.assertAlmostEqual(prop["y"], rh[1] + 10.0, delta=5.0)
        self.assertGreater(prop["x"] - start[0], 100.0)

    def test_beyond_reach_still_travels(self):
        # Staging beyond combined reach (A-S7 violated): no
        # meeting point exists, but the prop must still travel
        # from the giver's drawn hand to the receiver's drawn
        # hand instead of parking at an unreachable target.
        a = Stickman(height=560, name="a")
        b = Stickman(height=540, name="b")
        a.set_pose(root_x=700, root_y=679, facing=1)
        b.set_pose(root_x=1200, root_y=688, facing=-1)
        prop = {"x": 0, "y": 0}
        fn = give_to(a, b, prop, 1.2)
        fn(0.0)
        gh = a.joints()["hand_r"]
        self.assertAlmostEqual(prop["x"], gh[0], delta=5.0)
        fn(1.2)
        rh = b.joints()["hand_l"]
        self.assertAlmostEqual(prop["x"], rh[0], delta=5.0)
        self.assertAlmostEqual(prop["y"], rh[1] + 10.0, delta=5.0)


if __name__ == "__main__":
    unittest.main()
