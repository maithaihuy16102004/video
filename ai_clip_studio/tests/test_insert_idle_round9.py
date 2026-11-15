"""Round 9 (R2-C4): in insert shots, reach-without-grasp gestures
(present_prop, reach_to, point_at, raise_hand, wave) resolve to idle.
The frozen crop amputated them into a disembodied frozen claw: the
EMIT event's present_prop reach pinned at the reach limit inside the
5x insert crop, the hand never touching anything. Prop-carrying
primitives (hand_over, pick_up, shield, hammer_strike) are NOT
suppressed -- the prop follows the hand, so the hand IS the subject
(guarded by test_insert_two_pass's handover insert). The event still
fires effects: bursts read events, not primitives.
"""

import json
import os
import subprocess
import sys
import unittest

PROBE = os.path.expanduser(
    "~/workspace/acceptance_loop/r8_delivered_probe.py")
AGENT = os.path.expanduser("~/workspace/agent")
ACC = os.path.expanduser("~/workspace/acceptance_loop")


def _probe(idx):
    out = subprocess.run(
        [sys.executable, PROBE, str(idx)],
        cwd=AGENT, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    with open(f"{ACC}/r8_delivered_shot{idx}/result.json") as fh:
        return json.load(fh)


class TestInsertIdleGestures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r4 = _probe(4)

    def test_emit_event_recorded_as_insert_idle(self):
        self.assertEqual(self.r4.get("insert_idle_windows"),
                         ["SC02_SH03_ACT01"])

    def test_no_hand_inside_insert_crop(self):
        ca = self.r4["crop_anchor"]
        x0, y0, x1, y1 = ca["crop_rect"]
        sx, sy = 1920 / (x1 - x0), 1080 / (y1 - y0)
        for e in self.r4["grip_telemetry"]:
            for _n, h in e["hands"].items():
                for part in ("hand_l", "hand_r"):
                    px, py = h[part]
                    cx, cy = (px - x0) * sx, (py - y0) * sy
                    self.assertTrue(
                        cx < -50 or cx > 1970 or cy < -50 or cy > 1130,
                        f"frame {e['frame']}: {_n}.{part} inside crop "
                        f"at ({cx:.0f},{cy:.0f})")

    def test_insert_still_two_pass_with_stone_and_glow(self):
        self.assertTrue(self.r4["insert_two_pass"])
        for e in self.r4["grip_telemetry"]:
            stones = [d for d in e["draws"]
                      if d.get("pid") == "viên_đá_lửa"]
            self.assertTrue(stones, f"frame {e['frame']}: stone missing")
            self.assertEqual(stones[0]["state"], "WORLD_STATIC")


class TestNonInsertUnaffected(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r3 = _probe(3)

    def test_strike_shot_has_no_insert_idle_windows(self):
        # Shot #3 is a medium_close_up with an EMIT (present_prop)
        # event: the gesture must NOT be suppressed outside inserts.
        self.assertEqual(self.r3.get("insert_idle_windows"), [])


if __name__ == "__main__":
    unittest.main()
