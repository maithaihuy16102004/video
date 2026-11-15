"""RicksClips loop round 1 -- D3 map framing alternation + ECU-exit
locomotion widening."""
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.map_renderer import render_map
from ai_clip_studio.product_renderer import (
    _map_spec_from_shot,
    _render_shot,
    _shot_action_events,
    _shot_has_locomotion,
    plan_shots,
)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

SVG = [
    {"region": "Bigland",
     "d": "M 0 0 L 40 0 L 40 25 L 0 25 Z"},
    {"region": "Smallia",
     "d": "M 10 10 L 16 10 L 16 14 L 10 14 Z"},
]


def _package_and_shots(script_name, n_lines):
    text = (EXAMPLES / script_name).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(n_lines)])
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


class TestHighlightFraming(unittest.TestCase):
    def _render(self, framing, highlight):
        return render_map({
            "mode": "supplied", "size": (480, 270),
            "svg_paths": SVG, "framing": framing,
            "highlight": highlight})

    def test_highlights_framing_is_tighter(self):
        hl = [{"region": "Smallia"}]
        _, auto_rep = self._render("auto", hl)
        _, tight_rep = self._render("highlights", hl)
        self.assertEqual(tight_rep["framing_mode"], "highlights")
        auto = auto_rep["framing"]
        tight = tight_rep["framing"]
        self.assertLess(tight["lon_max"] - tight["lon_min"],
                        auto["lon_max"] - auto["lon_min"])
        self.assertLess(tight["lat_max"] - tight["lat_min"],
                        auto["lat_max"] - auto["lat_min"])
        self.assertIn("smallia", tight_rep["highlight_matched"])

    def test_highlights_fallback_without_match(self):
        _, rep = self._render("highlights", [{"region": "Nowhere"}])
        _, auto_rep = self._render("auto", [{"region": "Nowhere"}])
        self.assertEqual(rep["framing_mode"], "auto")
        self.assertEqual(rep["framing"], auto_rep["framing"])

    def test_explicit_framing_untouched(self):
        bounds = {"lon_min": -2, "lon_max": 12,
                  "lat_min": -2, "lat_max": 10}
        _, rep = self._render(bounds, [{"region": "Smallia"}])
        self.assertEqual(rep["framing_mode"], "explicit")
        self.assertEqual(rep["framing"], bounds)

    def test_highlights_window_derives_from_base(self):
        base = {"lon_min": -12, "lon_max": 40,
                "lat_min": 35, "lat_max": 60}
        _, rep = render_map({
            "mode": "supplied", "size": (480, 270),
            "svg_paths": SVG, "framing": "highlights",
            "base_framing": base,
            "highlight": [{"region": "Smallia"}]})
        self.assertEqual(rep["framing_mode"], "highlights")
        framing = rep["framing"]
        self.assertAlmostEqual(
            framing["lon_max"] - framing["lon_min"], 52 * 0.6)
        self.assertAlmostEqual(
            framing["lat_max"] - framing["lat_min"], 25 * 0.6)
        self.assertGreaterEqual(framing["lon_min"], base["lon_min"])
        self.assertLessEqual(framing["lon_max"], base["lon_max"])
        self.assertGreaterEqual(framing["lat_min"], base["lat_min"])
        self.assertLessEqual(framing["lat_max"], base["lat_max"])


class TestMapSpecOverride(unittest.TestCase):
    def test_highlights_mode_reaches_the_spec(self):
        shot = {"map_framing": "highlights",
                "v1_location": {"id": "LOC_MAP", "period": "1914",
                                "features": ["Đức", "Pháp"]}}
        spec = _map_spec_from_shot(shot, {})
        self.assertEqual(spec["framing"], "highlights")
        base = spec["base_framing"]
        self.assertEqual(base["lon_max"] - base["lon_min"], 52)
        self.assertEqual(base["lat_max"] - base["lat_min"], 25)

    def test_full_mode_keeps_registry_framing(self):
        shot = {"map_framing": "full",
                "v1_location": {"id": "LOC_MAP", "period": "1914",
                                "features": ["Đức", "Pháp"]}}
        spec = _map_spec_from_shot(shot, {})
        self.assertIsInstance(spec.get("framing"), dict)


class TestPlannerAlternation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.shots = _package_and_shots(
            "hitler_ep01_munich_1914.studio.md", 9)

    def test_runs_alternate_and_close_ups_are_tight(self):
        runs = []
        current = []
        for shot in self.shots:
            if "map_framing" in shot:
                current.append(shot)
            elif current:
                runs.append(current)
                current = []
        if current:
            runs.append(current)
        self.assertTrue(any(len(r) >= 2 for r in runs),
                        "fixture has no multi-shot map run")
        for run in runs:
            for a, b in zip(run, run[1:]):
                self.assertNotEqual(a["map_framing"], b["map_framing"],
                                    "adjacent map shots share a framing")
            for shot in run:
                self.assertEqual(shot["map_framing_source"],
                                 "planner:alternation")
                if shot["shot_type"] in ("close_up", "extreme_close_up",
                                         "graphic_insert"):
                    self.assertEqual(shot["map_framing"], "highlights")

    def test_non_map_shots_carry_no_framing(self):
        for shot in self.shots:
            traits = shot.get("v1_location") or {}
            if traits.get("type") != "Historical animated map":
                self.assertNotIn("map_framing", shot)


class TestLocomotionPredicate(unittest.TestCase):
    def test_verbs(self):
        for verb in ("WALK", "WALK_MUD", "RUN", "MARCH", "BOARD",
                     "CLIMB"):
            self.assertTrue(_shot_has_locomotion(
                [{"action_type": verb}], {}), verb)
        for verb in ("LOOK_AT", "TAKE_OUT", "IDLE", "SIT_DOWN"):
            self.assertFalse(_shot_has_locomotion(
                [{"action_type": verb}], {}), verb)

    def test_cue_fallback(self):
        self.assertTrue(_shot_has_locomotion(
            [], {"action_cues": ["walk", "look"]}))
        self.assertFalse(_shot_has_locomotion(
            [], {"action_cues": ["look"]}))
        self.assertFalse(_shot_has_locomotion(
            [{"action_type": "LOOK_AT"}], {"action_cues": ["walk"]}))


class TestLocomotionWideningRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.shots = _package_and_shots(
            "zeus_ep01_fall_of_cronus.studio.md", 40)

    def _shot_with(self, locomotion):
        for shot in self.shots:
            _, events, _, _, _, _ = _shot_action_events(
                self.package, shot, float(shot["duration"]))
            if _shot_has_locomotion(events, shot) == locomotion:
                found = dict(shot)
                found["shot_type"] = "extreme_close_up"
                return found
        self.fail(f"no shot with locomotion={locomotion}")

    def _render(self, shot):
        with tempfile.TemporaryDirectory() as tmp:
            return _render_shot({"shot": shot, "package": self.package,
                                 "out_dir": tmp, "still_only": True})

    def test_walking_ecu_widens_to_full_frame(self):
        report = self._render(self._shot_with(True))
        self.assertTrue(report["locomotion_widened"])
        self.assertEqual(report["applied_scale"], 1.0)

    def test_still_ecu_keeps_tight_crop(self):
        report = self._render(self._shot_with(False))
        self.assertFalse(report["locomotion_widened"])
        self.assertGreater(report["applied_scale"], 1.0)


if __name__ == "__main__":
    unittest.main()
