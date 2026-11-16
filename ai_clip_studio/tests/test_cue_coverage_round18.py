"""R18-1 (R17-D1): a scene-leaked cue must not stage a prop-affecting
legacy pose in a split shot whose event belongs to another span.

Loop 02 shot #15 carries the "give" cue from the SC05_SH01
handover, but no HAND_OVER event covers its span. Before the fix,
the legacy give_fn staged a phantom handover: the key sat frozen
at the unreachable meeting point (~1293, 419) while An's hand
never contacted it. Now the shot idles and the R17-2 holder
fallback keeps the key in An's hand. Free-form packages (no
compiled actions) keep the legacy staging: cues are their only
motion source.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import _render_shot
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
import ai_clip_studio.product_renderer as pr

AGENT = Path(__file__).resolve().parent.parent.parent
EXAMPLES = AGENT / "examples"
JOBS = AGENT / "jobs"


def _delivered_shot(index, job="req_7107b941a959", compiled=True):
    text = (EXAMPLES / "loop_test_02_brass_key.studio.md").read_text(
        encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    timeline = json.loads(
        (JOBS / job / "timeline.json").read_text(encoding="utf-8"))
    shots = timeline["shots"]
    starts = {}
    clock = 0.0
    for s in shots:
        starts[id(s)] = clock
        clock += float(s["duration"])
    spans = {}
    for s in shots:
        did = s.get("directive_shot_id")
        if did:
            st = starts[id(s)]
            span = spans.setdefault(str(did), [st, st])
            span[1] = max(span[1], st + float(s["duration"]))
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    if compiled:
        package["compiled_actions"] = {
            "events": events, "unsupported": unsupported,
            "spans_supplied": True, "compile_error": None,
        }
    shot = dict(shots[index])
    shot["index"] = index
    shot["start_sec"] = starts[id(shots[index])]
    return package, shot


def _key_draws(package, shot):
    draws = []
    orig = pr._draw_prop

    def spy(d, x, y, *a, **k):
        if k.get("kind") == "key":
            draws.append((float(x), float(y)))
        return orig(d, x, y, *a, **k)

    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(pr, "_draw_prop", spy):
            res = _render_shot({"shot": shot, "package": package,
                                "out_dir": tmp, "still_only": False})
    return draws, res


class TestCueCoverage(unittest.TestCase):
    def test_shot15_key_in_hand_not_at_meeting_point(self):
        package, shot = _delivered_shot(15)
        draws, res = _key_draws(package, shot)
        self.assertGreater(len(draws), 30)
        # Not frozen at the old meeting point (1293, 419).
        for x, y in draws:
            self.assertGreater(
                ((x - 1293.0) ** 2 + (y - 419.0) ** 2) ** 0.5, 100.0)
        # Follows the hand: the draw tracks the live joints, so
        # the position varies across the shot (idle sway).
        xs = [d[0] for d in draws]
        self.assertGreater(max(xs) - min(xs), 2.0)
        # Final frame: exactly at the holder's hand + (10, 14).
        hx, hy = res["joints_last_frame"]["An"]["hand_r"]
        lx, ly = draws[-1]
        self.assertAlmostEqual(lx, hx + 10, delta=1.0)
        self.assertAlmostEqual(ly, hy + 14, delta=1.0)

    def test_handover_shot_still_machine_owned(self):
        # Shot #18 carries the HAND_OVER event: the gate must not
        # change it -- the state machine owns the prop.
        package, shot = _delivered_shot(18)
        with tempfile.TemporaryDirectory() as tmp:
            res = _render_shot({"shot": shot, "package": package,
                                "out_dir": tmp, "still_only": True})
        self.assertIsNotNone(res.get("prop_machine"))

    def test_freeform_package_keeps_legacy_give(self):
        # No compiled actions at all: the give cue stages the
        # legacy handover (the meeting-point draw returns).
        package, shot = _delivered_shot(15, compiled=False)
        draws, _res = _key_draws(package, shot)
        self.assertGreater(len(draws), 30)
        near_mid = [d for d in draws
                    if ((d[0] - 1293.0) ** 2
                        + (d[1] - 419.0) ** 2) ** 0.5 < 60.0]
        self.assertGreater(len(near_mid), 0)


if __name__ == "__main__":
    unittest.main()
