"""Round 17 (L02-D7): the legacy prop path keeps a held prop in the
holder's hand in EVERY shot kind.

Shots with no compiled events have no state machine, so the legacy
cue path drew the shot's prop. Its action-kind branch dropped the
prop on the ground even when the shot declared a holder and the
event history said it was held: the key lay on the ground by An's
foot (#11) and floated at the frame corner (#17). Event history
wins over the plan_shots holder.
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import compile_actions
import ai_clip_studio.product_renderer as pr
from ai_clip_studio.product_renderer import _render_shot
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent
JOB = AGENT / "jobs" / "req_b0fe5da148b7"  # R16 Loop 02


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


def _key_draw_and_joints(package, shot):
    draws = []
    orig = pr._draw_prop

    def spy(draw, x, y, kind="wallet", w=None, h=None, **kw):
        draws.append((kind, float(x), float(y)))
        return orig(draw, x, y, kind=kind, w=w, h=h, **kw)

    pr._draw_prop = spy
    try:
        with tempfile.TemporaryDirectory() as tmp:
            rep = _render_shot({"shot": shot, "package": package,
                                "out_dir": tmp, "still_only": True})
    finally:
        pr._draw_prop = orig
    keys = [(x, y) for k, x, y in draws if k == "key"]
    return keys, rep["joints_last_frame"]


class TestLegacyHold(unittest.TestCase):
    def test_key_in_ans_hand_shot_11(self):
        package, shots = _delivered_shots()
        keys, joints = _key_draw_and_joints(package, shots[11])
        self.assertEqual(len(keys), 1)
        hx, hy = joints["An"]["hand_r"]
        dist = math.hypot(keys[0][0] - hx, keys[0][1] - hy)
        # The legacy hand offset is (10, 14) -> 17.2 px. Pre-fix
        # the key sat on the ground, hundreds of px from the hand.
        self.assertLess(dist, 60.0)

    def test_key_follows_event_history_not_plan_shot_17(self):
        package, shots = _delivered_shots()
        # The shot plan names Ba Tu as holder, but the handover
        # event has not happened yet: An still holds the key.
        self.assertEqual(shots[17].get("prop_holder"), "Bà Tư")
        keys, joints = _key_draw_and_joints(package, shots[17])
        self.assertEqual(len(keys), 1)
        hx, hy = joints["An"]["hand_r"]
        self.assertLess(math.hypot(keys[0][0] - hx, keys[0][1] - hy),
                        60.0)
        bx, by = joints["Bà Tư"]["hand_r"]
        self.assertGreater(
            math.hypot(keys[0][0] - bx, keys[0][1] - by), 200.0)


if __name__ == "__main__":
    unittest.main()
