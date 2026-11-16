"""Round 17 (R16-D1): bystander-head exclusion for the deferred
insert/ECU crop. The subject box is small (180x120 floor) but the
ECU crop at the 3.4x scale cap is 565x318, so a bystander staged
near the insert point lands inside the crop. The pass-2 crop rect
shifts away from intruding non-subject head discs, keeping the
prop anchor inside with margin.
"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from ai_clip_studio.action_compiler import compile_actions
import ai_clip_studio.product_renderer as pr
from ai_clip_studio.product_renderer import (
    _render_shot, _exclude_heads_from_crop, _median_bystander_heads)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent
JOB = AGENT / "jobs" / "req_b0fe5da148b7"  # R16 Loop 02
FACE = np.array([247, 243, 232], dtype=np.int16)


def _entry(heads, draws=()):
    return {"hands": {n: {"head": [hx, hy], "head_r": hr}
                      for n, hx, hy, hr in heads},
            "draws": list(draws)}


class TestCropExclusionUnits(unittest.TestCase):
    def test_no_intrusion_no_shift(self):
        rect, rec = _exclude_heads_from_crop(
            [853.0, 264.0, 1418.0, 582.0], (1125.0, 481.0),
            [("Far", 300.0, 300.0, 100.0)], 40.0, 1920.0, 1080.0)
        self.assertIsNone(rec)
        self.assertEqual(rect, [853.0, 264.0, 1418.0, 582.0])

    def test_intruding_head_cleared_prop_kept(self):
        rect, rec = _exclude_heads_from_crop(
            [853.0, 264.0, 1418.0, 582.0], (1125.0, 481.0),
            [("Bà Tư", 1370.0, 323.0, 133.0)], 40.0, 1920.0, 1080.0)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["cleared"], ["Bà Tư"])
        self.assertEqual(rec["remaining"], [])
        # Same size, in frame, prop inside with margin.
        self.assertAlmostEqual(rect[2] - rect[0], 565.0)
        self.assertAlmostEqual(rect[3] - rect[1], 318.0)
        self.assertGreaterEqual(rect[0], 0.0)
        self.assertLessEqual(rect[2], 1920.0)
        self.assertGreaterEqual(rect[1], 0.0)
        self.assertLessEqual(rect[3], 1080.0)
        self.assertLessEqual(rect[0], 1125.0 - 40.0)
        self.assertGreaterEqual(rect[2], 1125.0 + 40.0)
        self.assertLessEqual(rect[1], 481.0 - 40.0)
        self.assertGreaterEqual(rect[3], 481.0 + 40.0)
        # Head disc outside the shifted rect.
        nx = min(max(1370.0, rect[0]), rect[2])
        ny = min(max(323.0, rect[1]), rect[3])
        self.assertGreater(((1370.0 - nx) ** 2
                            + (323.0 - ny) ** 2) ** 0.5, 133.0)

    def test_slack_exhaustion_keeps_prop_inside(self):
        # Head dead-centre on the prop: no shift can clear it
        # without pushing the prop out; the prop must win.
        rect, rec = _exclude_heads_from_crop(
            [853.0, 264.0, 1418.0, 582.0], (1125.0, 481.0),
            [("OnTop", 1125.0, 481.0, 133.0)], 40.0, 1920.0, 1080.0)
        self.assertLessEqual(rect[0], 1125.0 - 40.0)
        self.assertGreaterEqual(rect[2], 1125.0 + 40.0)
        if rec is not None:
            self.assertEqual(rec["remaining"], ["OnTop"])

    def test_bystander_medians_exclude_holders(self):
        tel = [_entry([("An", 900.0, 300.0, 133.0),
                       ("Bà Tư", 1370.0, 323.0, 133.0)],
                      draws=[{"holder": "An", "kind": "key"}]),
               _entry([("An", 910.0, 310.0, 133.0),
                       ("Bà Tư", 1372.0, 325.0, 133.0)],
                      draws=[{"holder": "An", "kind": "key"}])]
        heads = _median_bystander_heads(tel)
        self.assertEqual([h[0] for h in heads], ["Bà Tư"])
        self.assertAlmostEqual(heads[0][1], 1371.0)
        self.assertAlmostEqual(heads[0][2], 324.0)
        self.assertAlmostEqual(heads[0][3], 133.0)


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


class TestEcuExclusionDelivered(unittest.TestCase):
    def test_ba_tu_cleared_from_ecu_frames(self):
        package, shots = _delivered_shots()
        with tempfile.TemporaryDirectory() as tmp:
            rep = _render_shot({"shot": shots[21], "package": package,
                                "out_dir": tmp, "still_only": False})
            excl = rep["insert_anchor"].get("bystander_crop_exclusion")
            self.assertIsNotNone(excl)
            self.assertIn("Bà Tư", excl["cleared"])
            frames = sorted(Path(tmp).glob("shot_021/f*.png"))
            self.assertGreater(len(frames), 20)
            for path in (frames[0], frames[len(frames) // 2],
                         frames[-1]):
                arr = np.asarray(
                    Image.open(path).convert("RGB")).astype(np.int16)
                corner = arr[0:405, 1588:1920]
                face = (np.abs(corner - FACE).sum(axis=2) < 40).mean()
                # R16: 75-97K px of face in this corner (23-30%).
                self.assertLess(face, 0.02, path.name)


if __name__ == "__main__":
    unittest.main()
