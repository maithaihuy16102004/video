"""Round 7 item 10: head-clearance separation (R6-D4).

A neighbour's hat brim crossing a head edge reads as a layering
defect. The renderer separates adjacent standing boxes until the
gap reaches 0.2x the smaller head radius, unless the pair is an
interaction pair (supposed to stand close) or both members are
anchored.
"""

import json
import os
import tempfile
import unittest

from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import _render_shot, plan_shots

_EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "..",
                        "examples", "loop_test_01_fire_stone.studio.md")
_JOB = os.path.join(os.path.dirname(__file__), "..", "..", "jobs",
                    "req_ca4d2c6d1959", "timeline.json")


def _package_and_shot(index):
    with open(_EXAMPLE, encoding="utf-8") as fh:
        doc = parse_studio_script_v1(fh.read())
    package = adapt_document(doc)
    with open(_JOB, encoding="utf-8") as fh:
        timeline = json.load(fh)
    shots = plan_shots(package, timeline["lines"])
    shot = dict(shots[index])
    shot["index"] = index
    spans = {}
    cursor = 0.0
    for s in shots:
        sid = s.get("directive_shot_id")
        if sid:
            spans.setdefault(sid, [cursor, cursor + s["duration"]])
            spans[sid][1] = cursor + s["duration"]
        cursor += s["duration"]
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    return package, shot


class TestHeadClearanceRound7(unittest.TestCase):
    def test_overlapping_staging_is_separated(self):
        # Shot 2 (reaction, SC01_SH01): no staging anchors and no
        # interaction pair, so the head-clearance pass itself is
        # the separator. (Shot 11 was the original probe, but
        # round-8 place staging + the sightline pass now separate
        # that pair first and anchor all three characters; see
        # test_placement_shot_pair_separated_by_sightline.)
        package, shot = _package_and_shot(2)
        # Force Linh and Be Nam onto nearly the same world x.
        shot["staging_override"] = {"Linh": 0.0, "Bé Nam": 0.1}
        with tempfile.TemporaryDirectory() as tmp:
            res = _render_shot({"shot": shot, "package": package,
                                "out_dir": tmp, "still_only": False})
        moved = res["head_clearance"]["moved"]
        self.assertTrue(moved, "separation pass must move a character")
        # Frame-0 heads must clear by >= 0.2x the smaller head
        # radius (15 px tolerance for pose sway at frame 0).
        tele = res["grip_telemetry"][0]["hands"]
        heads = {}
        for name in ("Linh", "Bé Nam"):
            hx, hy = tele[name]["head"]
            heads[name] = (hx, tele[name]["head_r"])
        (n1, (x1, r1)), (n2, (x2, r2)) = sorted(
            heads.items(), key=lambda kv: kv[1][0])
        gap = (x2 - r2 - 20.0) - (x1 + r1 + 20.0)
        need = 0.2 * min(r1, r2)
        self.assertGreaterEqual(
            gap, need - 15.0,
            f"{n1}/{n2} head gap {gap:.1f} < {need:.1f}")

    def test_placement_shot_pair_separated_by_sightline(self):
        # Shot 11 (SC04_SH01): Linh places on the table, so she
        # is place-staged and the sightline pass moves Ong Ba and
        # Be Nam -- all three are anchored before the
        # head-clearance pass runs, so it moves nobody. The
        # outcome must still hold: the forced-overlap pair's
        # frame-0 heads clear, via the earlier passes.
        package, shot = _package_and_shot(11)
        shot["staging_override"] = {"Linh": 0.0, "Bé Nam": 0.1}
        with tempfile.TemporaryDirectory() as tmp:
            res = _render_shot({"shot": shot, "package": package,
                                "out_dir": tmp, "still_only": False})
        self.assertIn("Linh", res["place_staging"])
        self.assertIn("Bé Nam",
                      res["support_sightline"]["moved"])
        self.assertEqual(res["head_clearance"]["moved"], {})
        tele = res["grip_telemetry"][0]["hands"]
        heads = {}
        for name in ("Linh", "Bé Nam"):
            hx, hy = tele[name]["head"]
            heads[name] = (hx, tele[name]["head_r"])
        (n1, (x1, r1)), (n2, (x2, r2)) = sorted(
            heads.items(), key=lambda kv: kv[1][0])
        gap = (x2 - r2 - 20.0) - (x1 + r1 + 20.0)
        need = 0.2 * min(r1, r2)
        self.assertGreaterEqual(
            gap, need - 15.0,
            f"{n1}/{n2} head gap {gap:.1f} < {need:.1f}")

    def test_interaction_pair_is_exempt(self):
        # Shot 7 is the shield shot: Ong Ba's SHIELD event targets
        # Be Nam, so the pair is supposed to stand close and the
        # separation pass must leave them alone.
        package, shot = _package_and_shot(7)
        with tempfile.TemporaryDirectory() as tmp:
            res = _render_shot({"shot": shot, "package": package,
                                "out_dir": tmp, "still_only": False})
        moved = res["head_clearance"]["moved"]
        self.assertNotIn("Ông Ba", moved)
        self.assertNotIn("Bé Nam", moved)


if __name__ == "__main__":
    unittest.main()
