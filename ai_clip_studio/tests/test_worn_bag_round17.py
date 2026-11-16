"""Round 17 (L02-D3): worn-bag presentation.

A bag the owner possesses but no event stages was pocket-hidden by
the machine -- invisible for whole shots. It now draws worn (strap
+ bag at the hip) whenever the machine/legacy path did not draw it
this frame. Possession follows _worn_bag_owner: CARRY counts as
possession, and a CARRY-first bag is worn from the start.
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import compile_actions
import ai_clip_studio.product_renderer as pr
from ai_clip_studio.product_renderer import (
    _render_shot, _worn_bag_owner)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent
JOB = AGENT / "jobs" / "req_b0fe5da148b7"  # R16 Loop 02
NAMES = {"CHAR_AN": "An", "CHAR_BA_TU": "Bà Tư"}
BAG = "túi_thư"


def _ev(action, actor, start, end, target=None, trusted=True):
    e = {"action_type": action, "actor_id": actor, "prop_id": BAG,
         "start_time": start, "end_time": end}
    if target is not None:
        e["target_id"] = target
    if not trusted:
        e["span_source"] = "estimated"
    return e


class TestWornBagOwner(unittest.TestCase):
    def test_no_events(self):
        self.assertIsNone(_worn_bag_owner([], BAG, 5.0, NAMES))

    def test_carry_default_before_end(self):
        evs = [_ev("CARRY", "CHAR_AN", 5.1, 6.1)]
        self.assertEqual(_worn_bag_owner(evs, BAG, 2.5, NAMES), "An")

    def test_carry_owner_after_end(self):
        evs = [_ev("CARRY", "CHAR_AN", 5.1, 6.1)]
        self.assertEqual(_worn_bag_owner(evs, BAG, 60.0, NAMES), "An")

    def test_pickup_first_has_no_default(self):
        evs = [_ev("PICK_UP", "CHAR_AN", 5.1, 6.1)]
        self.assertIsNone(_worn_bag_owner(evs, BAG, 2.5, NAMES))
        self.assertEqual(_worn_bag_owner(evs, BAG, 7.0, NAMES), "An")

    def test_handover_transfers(self):
        evs = [_ev("CARRY", "CHAR_AN", 5.1, 6.1),
               _ev("HAND_OVER", "CHAR_AN", 58.0, 59.0,
                   target="CHAR_BA_TU")]
        self.assertEqual(_worn_bag_owner(evs, BAG, 10.0, NAMES), "An")
        self.assertEqual(_worn_bag_owner(evs, BAG, 60.0, NAMES),
                         "Bà Tư")

    def test_release_clears(self):
        evs = [_ev("CARRY", "CHAR_AN", 5.1, 6.1),
               _ev("RELEASE", "CHAR_AN", 20.0, 21.0)]
        self.assertEqual(_worn_bag_owner(evs, BAG, 10.0, NAMES), "An")
        self.assertIsNone(_worn_bag_owner(evs, BAG, 22.0, NAMES))

    def test_untrusted_events_ignored(self):
        evs = [_ev("CARRY", "CHAR_AN", 5.1, 6.1, trusted=False)]
        self.assertIsNone(_worn_bag_owner(evs, BAG, 2.5, NAMES))

    def test_other_props_ignored(self):
        evs = [_ev("CARRY", "CHAR_AN", 5.1, 6.1)]
        evs[0]["prop_id"] = "other"
        self.assertIsNone(_worn_bag_owner(evs, BAG, 2.5, NAMES))


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


def _bag_draws(package, shot, still_only=True):
    draws = []
    orig = pr._draw_prop

    def spy(draw, x, y, kind="wallet", w=None, h=None, **kw):
        draws.append((kind, float(x), float(y)))
        return orig(draw, x, y, kind=kind, w=w, h=h, **kw)

    pr._draw_prop = spy
    try:
        with tempfile.TemporaryDirectory() as tmp:
            rep = _render_shot({"shot": shot, "package": package,
                                "out_dir": tmp,
                                "still_only": still_only})
            n = len(list(Path(tmp).glob("shot_*/f*.png")))
    finally:
        pr._draw_prop = orig
    bags = [(x, y) for k, x, y in draws if k == "bag"]
    return bags, rep["joints_last_frame"], n


class TestWornBagDraws(unittest.TestCase):
    def test_bag_worn_at_hip_shot_0(self):
        package, shots = _delivered_shots()
        bags, joints, _ = _bag_draws(package, shots[0])
        self.assertEqual(len(bags), 1)
        hx, hy = joints["An"]["hip"]
        self.assertLess(math.hypot(bags[0][0] - hx, bags[0][1] - hy),
                        150.0)

    def test_bag_worn_shot_18(self):
        package, shots = _delivered_shots()
        bags, joints, _ = _bag_draws(package, shots[18])
        self.assertEqual(len(bags), 1)
        hx, hy = joints["An"]["hip"]
        self.assertLess(math.hypot(bags[0][0] - hx, bags[0][1] - hy),
                        200.0)

    def test_no_bag_in_birds_eye_shot_6(self):
        package, shots = _delivered_shots()
        bags, _j, _n = _bag_draws(package, shots[6])
        self.assertEqual(bags, [])

    def test_exactly_one_bag_per_frame_shot_1(self):
        package, shots = _delivered_shots()
        bags, _j, n = _bag_draws(package, shots[1], still_only=False)
        self.assertEqual(len(bags), n)


if __name__ == "__main__":
    unittest.main()
