"""Round 9 headroom residual: the camera fit and the standing box
must cover top accessories (bun/hat/crown/horns), not just the
head circle. Linh's bun clipped above the staging canvas in shot
#3 (head circle top at 27 px cleared the 12 px fit margin while
the bun top sat at -8 px) because neither the fit nor the box
knew the bun existed.
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.product_renderer import (
    _fit_radius_scale, _render_shot, _top_accessory_frac,
    char_metrics)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _delivered_shot(index):
    text = (EXAMPLES / "loop_test_01_fire_stone.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    timeline = json.loads(
        (JOBS / "req_3ee64748a857" / "timeline.json").read_text(
            encoding="utf-8"))
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
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    shot = dict(shots[index])
    shot["index"] = index
    shot["start_sec"] = starts[id(shots[index])]
    return package, shot


class TestTopAccessoryFrac(unittest.TestCase):
    def test_values_from_draw_geometry(self):
        self.assertEqual(_top_accessory_frac({"hat": "cap"}), 0.75)
        self.assertEqual(
            _top_accessory_frac({"hair_style": "tied"}), 0.34)
        self.assertEqual(
            _top_accessory_frac({"hair_style": "tuft"}), 0.22)
        self.assertEqual(
            _top_accessory_frac({"horns": "crown"}), 0.34)
        self.assertEqual(
            _top_accessory_frac(
                {"visual_profile": {"horns": "antlers"}}), 0.24)
        self.assertEqual(_top_accessory_frac({"hat": "none"}), 0.0)
        self.assertEqual(_top_accessory_frac({}), 0.0)

    def test_max_of_worn_accessories(self):
        self.assertEqual(_top_accessory_frac(
            {"hat": "bowler", "hair_style": "tied"}), 0.75)

    def test_object_form(self):
        char = SimpleNamespace(hat="none", hair_style="tied",
                               horns="none")
        self.assertEqual(_top_accessory_frac(char), 0.34)


class TestFitCoversAccessories(unittest.TestCase):
    def test_bun_overflow_pulls_back_where_head_fits(self):
        # Geometry where the head circle clears the 12 px margin
        # but the bun (0.34r above it) does not: the legacy fit
        # returns 1.0, the accessory-aware fit pulls back.
        cam = viewpoint_for_shot("medium_close_up", "eye_level",
                                 subject_pos=(0.0, 1.2, 0.0))
        found = None
        for scale in (1.0, 1.1, 1.2, 1.3, 1.4, 1.5):
            _gx, gy, h = char_metrics(cam, 0.0, 0.0,
                                      base_scale=scale)
            head_top = gy - h
            bun_top = gy - h * (1.0 + 0.17 * 0.34)
            if head_top >= 12.0 and bun_top < 12.0:
                found = scale
                break
        self.assertIsNotNone(
            found, "no scale separates head fit from bun fit")
        legacy = _fit_radius_scale(
            "medium_close_up", "eye_level", 0.0, 0.0, None, 0,
            [(0.0, 0.0)], [found])
        fitted = _fit_radius_scale(
            "medium_close_up", "eye_level", 0.0, 0.0, None, 0,
            [(0.0, 0.0)], [found], top_fracs=[0.34])
        self.assertEqual(legacy, 1.0)
        self.assertGreater(fitted, 1.0)
        # The fitted camera clears the bun top (within the fit's
        # iteration slack: it converges to worst <= 1.0001, so
        # the top lands within ~0.06 px of the margin).
        cam2 = viewpoint_for_shot(
            "medium_close_up", "eye_level",
            subject_pos=(0.0, 1.2, 0.0), radius_scale=fitted)
        _gx, gy, h = char_metrics(cam2, 0.0, 0.0, base_scale=found)
        self.assertGreaterEqual(gy - h * (1.0 + 0.17 * 0.34), 11.9)

    def test_no_fracs_reproduces_legacy_fit(self):
        legacy = _fit_radius_scale(
            "medium", "eye_level", 0.0, 0.0, None, 0,
            [(0.0, 0.0)], [1.8])
        fitted = _fit_radius_scale(
            "medium", "eye_level", 0.0, 0.0, None, 0,
            [(0.0, 0.0)], [1.8], top_fracs=[0.0])
        self.assertEqual(legacy, fitted)


class TestShot3BunClearsStaging(unittest.TestCase):
    """Delivered shot #3: every frame's bun top clears the staging
    top (the R8 residual was -8 px in 89/91 frames)."""

    @classmethod
    def setUpClass(cls):
        package, shot = _delivered_shot(3)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = _render_shot(
            {"shot": shot, "package": package,
             "out_dir": cls.tmp.name, "still_only": False})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_bun_top_above_fit_margin_every_frame(self):
        worst = float("inf")
        for e in self.result["grip_telemetry"]:
            h = e["hands"].get("Linh")
            if not h:
                continue
            _hx, hy = h["head"]
            worst = min(worst, hy - 1.34 * h["head_r"])
        self.assertLess(worst, float("inf"))
        self.assertGreaterEqual(worst, 12.0)


if __name__ == "__main__":
    unittest.main()
