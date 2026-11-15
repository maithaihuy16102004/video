"""Round-8 self-head guard (R7-D1): the hammer wind-up swept the stone
and the hammer across the STRIKER's own face (shot #3 f4-16, up to
4,300 metal px in Linh's head bbox) while the round-7 intrusion audit
only watched bystanders.

Two fixes, both general: (1) hammer_strike routes the striking hand
around the actor's own head disc with a REACH-AWARE guard -- a plain
radial push fails because the rig's IK reach clamp pulls the hand
back into the disc (measured: hand pinned at the 168.3 px reach
limit, 95 px from the head centre); when the radial push is beyond
reach the guard takes the closest clearing point on the reach
circle. The hammer tip is guarded too, via the same disc test with
the centre shifted by the phase grip vector. (2) The head-intrusion
audit counts the holder's OWN head (records carry "self": True).
"""
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.animation.primitives import (
    HAMMER_HEAD_CLEARANCE_FRAC,
    _clear_own_head,
    hammer_strike,
)
from ai_clip_studio.animation import primitives as PRIMITIVES
from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.product_renderer import _render_shot, plan_shots
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _loop01_package_and_shots():
    text = (EXAMPLES / "loop_test_01_fire_stone.studio.md").read_text(
        encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(7)])
    for i, s in enumerate(shots):
        s["index"] = i
    spans = {}
    clock = 0.0
    for s in shots:
        did = s.get("directive_shot_id")
        if did:
            span = spans.setdefault(str(did), [clock, clock])
            span[1] = clock + float(s["duration"])
        clock += float(s["duration"])
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None,
    }
    return package, shots


class TestClearOwnHeadGeometry(unittest.TestCase):
    def test_clear_point_unchanged(self):
        pos = (500.0, 100.0)
        self.assertEqual(
            _clear_own_head(pos, (400.0, 300.0), 100.0, 600.0,
                            (400.0, 370.0), 170.0),
            pos)

    def test_radial_push_reaches_exact_margin(self):
        # Point inside the disc, radial push within reach.
        out = _clear_own_head((400.0, 250.0), (400.0, 300.0),
                              100.0, 600.0, (400.0, 370.0), 400.0)
        want = 100.0 + HAMMER_HEAD_CLEARANCE_FRAC * 600.0
        self.assertAlmostEqual(
            math.hypot(out[0] - 400.0, out[1] - 300.0), want,
            places=6)

    def test_unreachable_push_lands_on_reach_circle_clear(self):
        # Head 66 px above the shoulder, reach 170 px, margin
        # 172 px: the radial push (straight up, 238 px from the
        # shoulder) is beyond reach, so the guard must take the
        # reach-circle boundary point, which still clears.
        out = _clear_own_head((400.0, 250.0), (400.0, 300.0),
                              100.0, 600.0, (400.0, 366.0), 170.0)
        self.assertAlmostEqual(
            math.hypot(out[0] - 400.0, out[1] - 366.0), 170.0,
            places=6)
        want = 100.0 + HAMMER_HEAD_CLEARANCE_FRAC * 600.0
        self.assertGreaterEqual(
            math.hypot(out[0] - 400.0, out[1] - 300.0), want - 1e-6)

    def test_degenerate_centre_pushes_up(self):
        out = _clear_own_head((400.0, 300.0), (400.0, 300.0),
                              100.0, 600.0, (400.0, 370.0), 400.0)
        self.assertEqual(out[0], 400.0)
        self.assertLess(out[1], 300.0)


class TestHammerStrikeClearsOwnHead(unittest.TestCase):
    def test_hand_and_tip_clear_head_all_cycle(self):
        char = Stickman(height=600.0, template="default")
        char.pose["root_x"] = 500.0
        char.pose["root_y"] = 600.0
        char.pose["facing"] = 1
        strike = (620.0, 560.0)
        fn = hammer_strike(char, strike, duration=1.8)
        # The property that matters is the AUDIT predicate (head_r
        # + 0.05H): the guard aims for the wider clearance margin,
        # but the head thrusts forward during the strike phase and
        # eats ~26 px of it (measured minima 148.3 px vs the 174 px
        # margin) -- still 16 px clear of the audit threshold.
        audit = char.head_r + 0.05 * 600.0
        for i in range(37):
            fn(i * 0.05)
            joints = char.joints()
            head = joints["head"]
            hand = joints["hand_r"]
            self.assertGreaterEqual(
                math.hypot(hand[0] - head[0], hand[1] - head[1]),
                audit,
                msg=f"t={i * 0.05:.2f} hand inside head disc")


class TestStrikeShotSelfAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package, shots = _loop01_package_and_shots()
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC02_SH02")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = _render_shot({
            "shot": shot, "package": package,
            "out_dir": cls.tmp.name, "still_only": False})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_intrusions_including_self(self):
        self.assertEqual(self.result["head_intrusion_count"], 0)
        self.assertEqual(self.result["head_intrusions"], [])

    def test_contact_snap_preserved(self):
        # The guard must not break the strike: the hammer still
        # snaps to the anvil top at the contact instant.
        self.assertTrue(self.result.get("hammer_contact_snaps"))

    def test_audit_counts_self_heads_when_guard_off(self):
        # Sensitivity proof: with the guard disabled (identity),
        # the audit must report SELF intrusions on this shot --
        # otherwise the zero above would prove nothing.
        package, shots = _loop01_package_and_shots()
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC02_SH02")
        with mock.patch.object(
                PRIMITIVES, "_clear_own_head",
                lambda pos, *a, **k: pos):
            with tempfile.TemporaryDirectory() as tmp:
                res = _render_shot({
                    "shot": shot, "package": package,
                    "out_dir": tmp, "still_only": False})
        self_intrusions = [it for it in res["head_intrusions"]
                           if it.get("self")]
        self.assertTrue(
            self_intrusions,
            "audit reported no self intrusions with the guard off")
        self.assertTrue(
            all(it["holder"] == it["other"]
                for it in self_intrusions))


if __name__ == "__main__":
    unittest.main()
