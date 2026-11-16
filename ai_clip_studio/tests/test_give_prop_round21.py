"""Round 21 (F1 instrumentation): the R20 give_to prop-tracking
fix verified on a real render's internal state.

Loop 02 timeline shot #18 (SC05_SH01) holds the HAND_OVER event
(An -> Ba Tu). give_to executes via the hand_over wrapper on
every frame of the window. The prop state machine shadows the
prop dict on DELIVERED pixels (TRANSFERRED lerps the live
hands), so this test instruments the render: inside each
give_to call it reads the prop position plus both drawn hands
at the same instant. The prop must ride the hand-to-hand
segment (the designed below-hand offset only) and travel
giver -> receiver monotonically. This is instrumentation
evidence, NOT a pixel claim -- the pixel path does not exist
by architecture (R18 gate + machine shadowing).
"""
import math
import tempfile
import unittest
from unittest import mock

import ai_clip_studio.animation.primitives as prim
import ai_clip_studio.product_renderer as pr


class TestGivePropRenderRound21(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ai_clip_studio.product_renderer import _render_shot
        from ai_clip_studio.tests.test_cue_coverage_round18 import (
            _delivered_shot)
        package, shot = _delivered_shot(18, job="req_9525d57a99ee")
        cls.tmp = tempfile.TemporaryDirectory()
        calls = []
        orig = prim.give_to

        def spy(giver, receiver, prop, duration, **kw):
            base = orig(giver, receiver, prop, duration, **kw)
            rh = kw.get("receive_hand", "l")

            def fn(t):
                out = base(t)
                gj = giver.joints()
                rj = receiver.joints()
                calls.append({
                    "t": float(t), "dur": float(duration),
                    "prop": (float(prop["x"]), float(prop["y"])),
                    "giver_hand": gj["hand_r"],
                    "recv_hand": (rj["hand_l"] if rh in ("l", "both")
                                  else rj["hand_r"]),
                })
                return out

            return fn

        with mock.patch.object(prim, "give_to", side_effect=spy):
            with mock.patch.object(pr, "give_to", side_effect=spy):
                _render_shot({"shot": shot, "package": package,
                              "out_dir": cls.tmp.name,
                              "still_only": False})
        cls.calls = [c for c in calls if 0.0 < c["t"] < c["dur"]]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def _seg(p, a, b):
        ax, ay = a
        bx, by = b
        px, py = p
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 == 0:
            return math.hypot(px - ax, py - ay), 0.0
        s = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        return math.hypot(px - (ax + s * dx), py - (ay + s * dy)), s

    def test_prop_tracks_drawn_hands(self):
        # Measured: 35 in-window calls, worst distance 12.3 px
        # (the designed below-hand offset), progress 0 -> 1.
        self.assertGreaterEqual(len(self.calls), 20)
        prog = []
        for c in self.calls:
            d, s = self._seg(c["prop"], c["giver_hand"],
                             c["recv_hand"])
            self.assertLess(d, 20.0)
            prog.append(s)
        self.assertLess(prog[0], 0.1)
        self.assertGreater(prog[-1], 0.9)
        for i in range(len(prog) - 1):
            self.assertGreaterEqual(prog[i + 1], prog[i] - 0.05)


if __name__ == "__main__":
    unittest.main()
