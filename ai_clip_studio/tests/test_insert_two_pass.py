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
        # Hero prop grammar: the box is sized from the prop
        # footprint (bolt 76x156 x 1.5 margin -> 180x234, the
        # round-6 aspect-preserving footprint), not the old
        # fixed +-170/+-90 box. No hand telemetry here, so the
        # box is prop-only.
        tel = [self._entry([{"kind": "bolt", "x": 500.0,
                              "y": 300.0}])]
        subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertEqual(subjects, [{"cx": 500.0, "head_y": 183.0,
                                     "foot_y": 417.0,
                                     "half_w": 90.0}])
        self.assertEqual(anchor["source"], "telemetry_median")
        self.assertEqual(anchor["prop_w"], 76.0)
        self.assertEqual(anchor["prop_h"], 156.0)
        self.assertFalse(anchor["hands_included"])
        self.assertFalse(anchor["pair_anchored"])


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
        # Round 7: the pacing merge shifts plan indices, so the
        # three shots are resolved by identity, not fixed
        # positions. Handover: SC08_SH02 (bolt travels giver ->
        # receiver). Fallback: the earliest directive-less
        # insert with no prop events in its span. Control: the
        # first non-insert shot.
        clock = 0.0
        spans = []
        for s in cls.shots:
            spans.append((clock, clock + float(s["duration"])))
            clock += float(s["duration"])
        events = cls.package["compiled_actions"]["events"]

        def _has_prop_event(i):
            a, b = spans[i]
            return any(e.get("prop_id") and e["start_time"] < b
                       and e["end_time"] > a for e in events)

        handover = next(
            i for i, s in enumerate(cls.shots)
            if s.get("directive_shot_id") == "SC08_SH02")
        fallback = next(
            i for i, s in enumerate(cls.shots)
            if s["shot_type"] == "object_insert"
            and s.get("directive_shot_id") is None
            and not _has_prop_event(i))
        control = next(
            i for i, s in enumerate(cls.shots)
            if s["shot_type"] != "object_insert")
        for role, idx in (("handover", handover),
                          ("fallback", fallback),
                          ("control", control)):
            s = cls.shots[idx]
            cls.results[role] = _render_shot({
                "shot": s, "package": cls.package,
                "out_dir": str(cls.out / f"shot_{idx:02d}"),
            })
            cls.results[role]["_out_dir"] = cls.out / f"shot_{idx:02d}"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_handover_insert_anchors_from_telemetry_median(self):
        r = self.results["handover"]
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
        # The fallback insert has no prop EVENTS, but the renderer
        # still draws
        # a prop (rest/cue path), so the median branch runs. The
        # no-draw fallback is pinned at the helper level above.
        r = self.results["fallback"]
        self.assertEqual(r["shot_type"], "object_insert")
        self.assertTrue(r["insert_two_pass"])
        self.assertIsNotNone(r["crop_anchor"])
        self.assertGreater(r["n_frames"], 0)

    def test_deferred_glow_stays_local(self):
        # The pre-crop halo washed the whole insert frame (annulus
        # brightness 76.4); the deferred screen-space halo must
        # leave the far region at the bare-background level while
        # the bolt region still glows. Regions are derived from
        # the frame's own geometry (the mapped anchor + the
        # farthest corner), not fixed pixels: the meeting-point
        # fix moved the crop, and the old fixed annulus now
        # catches Zeus's chin (240.7 -- face, not glow). The glow
        # signal is WARMTH (R-B): the yellow halo is warm near
        # the bolt (24.1) and absent at the far corner (-0.1);
        # mean brightness does not discriminate (the dark grip
        # blob drags the bolt box down to the background level).
        r = self.results["handover"]
        frames = sorted(r["_out_dir"].rglob("f*.png"))
        arr = np.asarray(
            Image.open(frames[len(frames) // 2]).convert("RGB")
        ).astype(float)
        anchor = r["insert_anchor"]
        x0, y0, x1, _y1 = r["crop_anchor"]["crop_rect"]
        sc = 1920.0 / (x1 - x0)
        ax = int((anchor["x"] - x0) * sc)
        ay = int((anchor["y"] - y0) * sc)
        bolt_box = arr[ay - 100:ay + 100, ax - 100:ax + 100]
        bolt_warm = (bolt_box[:, :, 0] - bolt_box[:, :, 2]).mean()
        self.assertGreater(bolt_warm, 15.0)
        corners = {
            "TL": (slice(40, 240), slice(40, 340)),
            "TR": (slice(40, 240), slice(1540, 1840)),
            "BL": (slice(800, 1000), slice(40, 340)),
            "BR": (slice(800, 1000), slice(1540, 1840)),
        }
        centres = {"TL": (190, 140), "TR": (1690, 140),
                   "BL": (190, 900), "BR": (1690, 900)}
        far_name = max(
            corners,
            key=lambda k: (centres[k][0] - ax) ** 2
            + (centres[k][1] - ay) ** 2)
        far_box = arr[corners[far_name]]
        # The far region must carry no halo: the deferred glow is
        # yellow (255, 200, 90) and a pre-crop wash would paint the
        # whole frame with it. Warmth/brightness no longer
        # discriminate here -- the far corner contains forge brick
        # (warm, dark) and, since the distinct-palette system, a
        # warm pink jacket -- so the assertion counts glow-coloured
        # pixels directly instead of the corner's mean warmth.
        glow = np.abs(far_box - np.array([255.0, 200.0, 90.0])).sum(
            axis=2)
        self.assertLess(int((glow < 60).sum()),
                        0.005 * far_box.shape[0] * far_box.shape[1])

    def test_telemetry_hands_carry_hip(self):
        # Pass-2 glow re-derivation reads the same joints the
        # state machine read, including the hip (pocket rests).
        for entry in self.results["handover"]["grip_telemetry"]:
            for hands in entry["hands"].values():
                self.assertIn("hip", hands)
                self.assertEqual(len(hands["hip"]), 2)

    def test_non_insert_shot_unchanged(self):
        r = self.results["control"]
        self.assertNotEqual(r["shot_type"], "object_insert")
        self.assertFalse(r["insert_two_pass"])
        self.assertIsNone(r["insert_anchor"])
        self.assertIsNotNone(r["crop_anchor"])


if __name__ == "__main__":
    unittest.main()
