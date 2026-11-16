"""Round 17 (R16-O1): held-prop head clearance. A small prop centred
on a hand raised beside a face drew across the eye/cheek. The draw
position now pushes radially out of every head disc it intrudes
(the audit's predicate); the hand never moves.
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import (
    _render_shot, _clear_head)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent
JOB = AGENT / "jobs" / "req_b0fe5da148b7"  # R16 Loop 02


class TestClearHead(unittest.TestCase):
    def test_clear_point_untouched(self):
        self.assertEqual(
            _clear_head((500.0, 300.0), (300.0, 300.0), 133.0, 783.0),
            (500.0, 300.0))

    def test_intruding_point_pushed_to_edge(self):
        out = _clear_head((350.0, 300.0), (300.0, 300.0), 133.0, 783.0)
        # Target: head_r + 0.05H + 8 = 180.15, along +x.
        self.assertAlmostEqual(out[0], 300.0 + 180.15, places=1)
        self.assertAlmostEqual(out[1], 300.0, places=1)

    def test_diagonal_push_keeps_direction(self):
        out = _clear_head((330.0, 330.0), (300.0, 300.0), 133.0, 783.0)
        self.assertAlmostEqual(
            math.hypot(out[0] - 300.0, out[1] - 300.0), 180.15,
            places=1)
        self.assertGreater(out[0], 300.0)
        self.assertGreater(out[1], 300.0)

    def test_centre_pushes_along_facing(self):
        out = _clear_head((300.0, 300.0), (300.0, 300.0), 133.0,
                          783.0, facing=-1)
        self.assertAlmostEqual(out[0], 300.0 - 180.15, places=1)
        self.assertAlmostEqual(out[1], 300.0, places=1)

    def test_zero_head_r_untouched(self):
        self.assertEqual(
            _clear_head((300.0, 300.0), (300.0, 300.0), 0.0, 783.0),
            (300.0, 300.0))


def _delivered_shots():
    text = (AGENT / "examples" / "loop_test_02_brass_key.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    timeline = json.loads((JOB / "timeline.json").read_text(
        encoding="utf-8"))
    shots = timeline["shots"]
    starts, _t = {}, 0.0
    for s in shots:
        starts[id(s)] = _t
        _t += float(s["duration"])
    spans = {}
    for s in shots:
        sid = s.get("directive_shot_id")
        if sid:
            st, en = starts[id(s)], starts[id(s)] + float(s["duration"])
            spans[sid] = [min(spans[sid][0], st), max(spans[sid][1], en)] \
                if sid in spans else [st, en]
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    out = []
    for i, s in enumerate(shots):
        shot = dict(s)
        shot["index"] = i
        shot["start_sec"] = starts[id(s)]
        out.append(shot)
    return package, out


class TestHeadClearanceDelivered(unittest.TestCase):
    def test_no_intrusions_in_o1_shots(self):
        # R16 delivered frames: key across Ba Tu's eye (#19 f55)
        # and An's temple (#4 f40). The audit reads the shifted
        # telemetry positions, so zero means the drawn key clears
        # every head disc in every frame of both shots.
        package, shots = _delivered_shots()
        for idx in (4, 19):
            with tempfile.TemporaryDirectory() as tmp:
                rep = _render_shot({"shot": shots[idx],
                                    "package": package,
                                    "out_dir": tmp,
                                    "still_only": False})
            self.assertEqual(rep["head_intrusion_count"], 0,
                             f"shot #{idx}")


if __name__ == "__main__":
    unittest.main()
