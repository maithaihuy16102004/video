"""Insert two-pass tests: object_insert shots anchor from the prop's
telemetry median, not its frame-0 rest position (Zeus shot 62 framed
legs while the bolt travelled to Zeus's hand — the frame-0 anchor).
"""
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import (
    GLOW_SCREEN_RADIUS_CAP,
    _insert_anchor_from_telemetry,
    _insert_anchor_subjects,
    _render_shot,
    _screen_glow_record,
    plan_shots,
)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _zeus_package_and_shots():
    text = (EXAMPLES / "zeus_ep01_fall_of_cronus.studio.md").read_text(
        encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(40)])
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


class TestInsertAnchorFromTelemetry(unittest.TestCase):
    def _entry(self, draws):
        return {"t": 0.0, "frame": 0, "hands": {}, "draws": draws}

    def test_median_of_travelling_prop(self):
        tel = [self._entry([{"kind": "bolt", "x": float(x),
                              "y": 100.0}]) for x in (100, 200, 300)]
        x, y, kind, n = _insert_anchor_from_telemetry(tel)
        self.assertEqual((x, y, kind, n), (200.0, 100.0, "bolt", 3))

    def test_even_count_averages_middle_pair(self):
        tel = [self._entry([{"kind": "stone", "x": float(x),
                              "y": 0.0}]) for x in (0, 100, 200, 300)]
        x, _y, _k, n = _insert_anchor_from_telemetry(tel)
        self.assertEqual((x, n), (150.0, 4))

    def test_dominant_kind_wins(self):
        tel = [self._entry([{"kind": "bolt", "x": 50.0, "y": 50.0}]),
               self._entry([{"kind": "stone", "x": 0.0, "y": 0.0},
                            {"kind": "stone", "x": 10.0, "y": 10.0}])]
        _x, _y, kind, n = _insert_anchor_from_telemetry(tel)
        self.assertEqual((kind, n), ("stone", 2))

    def test_no_draws_returns_none(self):
        self.assertIsNone(_insert_anchor_from_telemetry([]))
        self.assertIsNone(_insert_anchor_from_telemetry(
            [self._entry([])]))
        self.assertIsNone(_insert_anchor_from_telemetry(
            [self._entry([{"kind": "bolt"}])]))

    def test_subjects_fallback_without_draws(self):
        boxes = [{"cx": 960, "head_y": 100, "foot_y": 900,
                  "half_w": 200}]
        subjects, anchor = _insert_anchor_subjects([], boxes)
        self.assertEqual(subjects, boxes)
        self.assertEqual(anchor["source"],
                         "standing_boxes_fallback")
        self.assertEqual(anchor["n_draws"], 0)

    def test_subjects_from_median(self):
        tel = [self._entry([{"kind": "bolt", "x": 500.0,
                              "y": 300.0}])]
        subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertEqual(subjects, [{"cx": 500.0, "head_y": 210.0,
                                     "foot_y": 390.0,
                                     "half_w": 170}])
        self.assertEqual(anchor["source"], "telemetry_median")


class TestScreenGlowRecord(unittest.TestCase):
    def _record(self, radius=240.0, pos=(928.566, 527.082)):
        return {"prop_id": "p", "intensity": 1.0,
                "color": (255, 210, 90), "radius": radius,
                "source_position": pos, "state": "GRASPED",
                "holder": "Zeus"}

    def test_centre_moves_through_crop(self):
        out = _screen_glow_record(
            self._record(), [646, 368, 1211, 686], (1920, 1080))
        self.assertAlmostEqual(out["source_position"][0], 960.0,
                               delta=2.0)
        self.assertAlmostEqual(out["source_position"][1], 540.0,
                               delta=2.0)

    def test_radius_capped_at_zoom(self):
        out = _screen_glow_record(
            self._record(), [646, 368, 1211, 686], (1920, 1080))
        self.assertEqual(out["radius"], GLOW_SCREEN_RADIUS_CAP)

    def test_small_radius_uncapped_at_unit_zoom(self):
        out = _screen_glow_record(
            self._record(radius=100.0), [0, 0, 1920, 1080],
            (1920, 1080))
        self.assertEqual(out["radius"], 100.0)
        self.assertEqual(out["source_position"],
                         (928.566, 527.082))

    def test_input_record_untouched(self):
        rec = self._record()
        _screen_glow_record(rec, [646, 368, 1211, 686], (1920, 1080))
        self.assertEqual(rec["radius"], 240.0)
        self.assertEqual(rec["source_position"], (928.566, 527.082))


class TestInsertTwoPassRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.shots = _zeus_package_and_shots()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name)
        cls.results = {}
        # Shot 44: SC08_SH02 handover insert (bolt travels giver ->
        # receiver). Shot 10: insert with no prop events (fallback).
        # Shot 0: control (non-insert, behaviour unchanged).
        for idx in (44, 10, 0):
            s = cls.shots[idx]
            cls.results[idx] = _render_shot({
                "shot": s, "package": cls.package,
                "out_dir": str(cls.out / f"shot_{idx:02d}"),
            })
            cls.results[idx]["_out_dir"] = cls.out / f"shot_{idx:02d}"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_handover_insert_anchors_from_telemetry_median(self):
        r = self.results[44]
        self.assertEqual(r["shot_type"], "object_insert")
        self.assertTrue(r["insert_two_pass"])
        anchor = r["insert_anchor"]
        self.assertEqual(anchor["source"], "telemetry_median")
        self.assertEqual(anchor["kind"], "bolt")
        self.assertGreater(anchor["n_draws"], 10)
        # The frozen crop rect contains the median anchor point.
        x0, y0, x1, y1 = r["crop_anchor"]["crop_rect"]
        self.assertLessEqual(x0, anchor["x"])
        self.assertLessEqual(anchor["x"], x1)
        self.assertLessEqual(y0, anchor["y"])
        self.assertLessEqual(anchor["y"], y1)
        # The prop travelled: the median is far from the first
        # draw (frame-0 rest), so the anchor is NOT the frame-0
        # position the old path froze from.
        first = None
        for entry in r["grip_telemetry"]:
            for d in entry["draws"]:
                if d["kind"] == "bolt":
                    first = (d["x"], d["y"])
                    break
            if first:
                break
        self.assertIsNotNone(first)
        dist = math.hypot(anchor["x"] - first[0],
                          anchor["y"] - first[1])
        self.assertGreater(dist, 50.0)
        # Pass 2 preserved the frame size on disk.
        frames = sorted(r["_out_dir"].rglob("f*.png"))
        self.assertEqual(len(frames), r["n_frames"])
        for p in (frames[0], frames[len(frames) // 2]):
            with Image.open(p) as im:
                self.assertEqual(im.size, (1920, 1080))

    def test_insert_without_prop_events_still_two_pass(self):
        # Shot 10 has no prop EVENTS, but the renderer still draws
        # a prop (rest/cue path), so the median branch runs. The
        # no-draw fallback is pinned at the helper level above.
        r = self.results[10]
        self.assertEqual(r["shot_type"], "object_insert")
        self.assertTrue(r["insert_two_pass"])
        self.assertIsNotNone(r["crop_anchor"])
        self.assertGreater(r["n_frames"], 0)

    def test_deferred_glow_stays_local(self):
        # The pre-crop halo washed the whole insert frame (annulus
        # brightness 76.4); the deferred screen-space halo must
        # leave the far region at the bare-background level while
        # the bolt region still glows.
        r = self.results[44]
        frames = sorted(r["_out_dir"].rglob("f*.png"))
        arr = np.asarray(
            Image.open(frames[len(frames) // 2]).convert("RGB")
        ).astype(float)
        annulus = arr[150:350, 1450:1750].mean()
        self.assertLess(annulus, 65.0)
        bolt_box = arr[440:640, 860:1060].mean()
        self.assertGreater(bolt_box, 100.0)

    def test_telemetry_hands_carry_hip(self):
        # Pass-2 glow re-derivation reads the same joints the
        # state machine read, including the hip (pocket rests).
        for entry in self.results[44]["grip_telemetry"]:
            for hands in entry["hands"].values():
                self.assertIn("hip", hands)
                self.assertEqual(len(hands["hip"]), 2)

    def test_non_insert_shot_unchanged(self):
        r = self.results[0]
        self.assertNotEqual(r["shot_type"], "object_insert")
        self.assertFalse(r["insert_two_pass"])
        self.assertIsNone(r["insert_anchor"])
        self.assertIsNotNone(r["crop_anchor"])


if __name__ == "__main__":
    unittest.main()
