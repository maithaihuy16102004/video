"""W2 wiring tests: environment_v2 in the render path, new archetypes,
foreground frustum fit, and the map routing + mode gating.

Run from ~/workspace/agent/:
  python3 -m unittest ai_clip_studio.tests.test_environment_w2 -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import (
    build_environment, fit_foreground_to_frustum, render_environment,
    select_archetype)
from ai_clip_studio.map_renderer import (
    MapSpecError, MissingHistoricalMapData, render_map)
from ai_clip_studio.product_renderer import (
    _map_highlight_entries, _map_spec_from_shot, _render_shot,
    build_scene_ex, build_scene_ex_with_package, plan_shots)


def _ep1_package():
    from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
    from ai_clip_studio.studio_script_v1_adapter import adapt_document
    root = Path(__file__).resolve().parents[2]
    text = (root / "examples"
            / "hitler_ep01_munich_1914.studio.md").read_text(
                encoding="utf-8")
    return adapt_document(parse_studio_script_v1(text))


class TestNewArchetypes(unittest.TestCase):
    def test_ep1_locations_select_correct_archetypes(self):
        package = _ep1_package()
        expected = {
            "LOC_MUNICH_STREET": "EUROPEAN_STREET_1900",
            "LOC_EUROPE_MAP": "MAP",
            "LOC_RECRUITMENT_OFFICE": "INTERIOR_GENERIC",
            "LOC_BAVARIA_BARRACKS": "BARRACKS",
            "LOC_FLANDERS_ROUTE": "COUNTRYSIDE_ROAD",
            "LOC_YPRES_TRENCH": "TRENCH",
        }
        for loc in package["v1_locations"]:
            arch, _, _ = select_archetype(loc)
            self.assertEqual(arch, expected[loc["id"]], loc["id"])
            env = build_environment(loc, time_of_day="day")
            self.assertEqual(env["validation"], [], loc["id"])
            self.assertEqual(env["period_errors"], [], loc["id"])

    def test_interior_has_desk_chair_cabinet_for_office_traits(self):
        package = _ep1_package()
        loc = next(l for l in package["v1_locations"]
                   if l["id"] == "LOC_RECRUITMENT_OFFICE")
        env = build_environment(loc, time_of_day="day")
        kinds = {e["kind"] for e in env["elements"]}
        self.assertIn("desk", kinds)
        self.assertIn("chair", kinds)
        self.assertIn("cabinet", kinds)
        self.assertIn("window", kinds)

    def test_interior_gates_furniture_on_trait_text(self):
        bare = {"id": "LOC_BARE", "name": "Empty room",
                "features": ["Nội thất trống.", "Tường trắng."],
                "period": "1914"}
        env = build_environment(bare, time_of_day="day")
        self.assertEqual(env["archetype"], "INTERIOR_GENERIC")
        kinds = {e["kind"] for e in env["elements"]}
        self.assertNotIn("desk", kinds)
        self.assertNotIn("cabinet", kinds)
        self.assertIn("window", kinds)

    def test_countryside_is_not_a_trench(self):
        traits = {"id": "LOC_ROAD", "name": "Country road",
                  "features": ["Đường đất.", "Đồng quê châu Âu.",
                               "Cây trụi lá.", "Binh lính hành quân."],
                  "period": "1914"}
        env = build_environment(traits, time_of_day="day")
        self.assertEqual(env["archetype"], "COUNTRYSIDE_ROAD")
        kinds = {e["kind"] for e in env["elements"]}
        self.assertIn("road", kinds)
        self.assertNotIn("sandbag", kinds)

    def test_trench_smoke_is_small_high_and_faint(self):
        traits = {"id": "LOC_T", "name": "Trench",
                  "features": ["Chiến hào.", "Bao cát.", "Khói pháo ở xa."],
                  "period": "1914"}
        env = build_environment(traits, time_of_day="day")
        smokes = [e for e in env["elements"] if e["kind"] == "smoke"]
        self.assertTrue(smokes)
        for el in smokes:
            self.assertGreaterEqual(el["center"][1], 2.5)
            self.assertLessEqual(el["size"][0], 3.0)


class TestForegroundFrustumFit(unittest.TestCase):
    def test_all_archetype_fg_elements_in_frame_after_fit(self):
        cam = viewpoint_for_shot(
            "establishing", "eye_level", subject_pos=(0.0, 1.2, 0.0))
        package = _ep1_package()
        for loc in package["v1_locations"]:
            env = build_environment(loc, time_of_day="day")
            if env.get("kind") == "map_deferred":
                continue
            fitted = fit_foreground_to_frustum(env, cam, (1920, 1080))
            for el in fitted["elements"]:
                if el.get("layer") != "FG":
                    continue
                px, py, _, vis = cam.project(el["center"], 1920, 1080)
                self.assertTrue(vis, f"{loc['id']} {el['id']} visible")
                self.assertGreaterEqual(px, 0, el["id"])
                self.assertLessEqual(px, 1920, el["id"])

    def test_fit_does_not_mutate_and_keeps_in_frame_elements(self):
        package = _ep1_package()
        loc = next(l for l in package["v1_locations"]
                   if l["id"] == "LOC_YPRES_TRENCH")
        env = build_environment(loc, time_of_day="day")
        before = {e["id"]: e["center"] for e in env["elements"]}
        cam = viewpoint_for_shot(
            "establishing", "eye_level", subject_pos=(0.0, 1.2, 0.0))
        fitted = fit_foreground_to_frustum(env, cam, (1920, 1080))
        after = {e["id"]: e["center"] for e in env["elements"]}
        self.assertEqual(before, after, "input package must not mutate")
        fitted_centers = {e["id"]: e["center"]
                          for e in fitted["elements"]}
        # sandFG3 (x=2.6) is inside the establishing frustum: untouched.
        self.assertEqual(fitted_centers["sandFG3"], before["sandFG3"])
        # Non-FG elements are never moved.
        for e in fitted["elements"]:
            if e.get("layer") != "FG":
                self.assertEqual(e["center"], before[e["id"]])


class TestLayeredEnvironmentRender(unittest.TestCase):
    def _package_with_centred_fg_box(self):
        return {
            "archetype": "GENERIC_NEUTRAL", "kind": "environment",
            "layers": {"FG": ["fg_box"], "MG": [], "BG": ["bg_box"]},
            "elements": [
                {"id": "bg_box", "kind": "distant_mass", "layer": "BG",
                 "geometry": "box", "center": (0.0, 1.0, -10.0),
                 "size": (4.0, 2.0, 1.0), "color": (100, 100, 100),
                 "material": "silhouette", "attachment": None,
                 "label": "", "extra": {}},
                {"id": "fg_box", "kind": "crate", "layer": "FG",
                 "geometry": "box", "center": (0.0, 0.5, 1.5),
                 "size": (1.0, 1.0, 1.0), "color": (200, 30, 30),
                 "material": "wood", "attachment": None,
                 "label": "", "extra": {}},
            ],
            "palette": {}, "light": {},
            "ground": {"kind": "neutral", "color": (120, 118, 112)},
            "provenance": {}, "validation": [], "period_errors": [],
        }

    def test_transparent_fg_pass_carries_only_fg(self):
        from ai_clip_studio.renderer25d.camera import PerspectiveCamera
        pkg = self._package_with_centred_fg_box()
        cam = PerspectiveCamera(position=(0.0, 2.0, 4.8),
                                target=(0.0, 1.2, 0.0),
                                fov_deg=46.0, aspect=16 / 9)
        fg = render_environment(pkg, cam, (480, 270), draw_layers=("FG",),
                                transparent=True)
        self.assertEqual(fg.mode, "RGBA")
        self.assertIsNotNone(fg.getchannel("A").getbbox())
        bg = render_environment(pkg, cam, (480, 270),
                                draw_layers=("BG", "MG"))
        full = render_environment(pkg, cam, (480, 270))
        # The FG box centre pixel: reddish (shaded box face) in the
        # full render, ground/sky (not reddish) in the BG+MG pass.
        cx, cy, _, _ = cam.project((0.0, 0.5, 1.5), 480, 270)
        full_px = full.getpixel((int(cx), int(cy)))
        self.assertGreater(full_px[0], 100)
        self.assertGreater(full_px[0], full_px[1])
        bg_px = bg.getpixel((int(cx), int(cy)))
        self.assertLessEqual(bg_px[0], bg_px[1] + 20)


class TestSceneBuildDispatch(unittest.TestCase):
    def test_trait_block_returns_package_and_archetype(self):
        package = _ep1_package()
        loc = package["v1_locations"][0]
        (boxes, sky_top, sky_bottom, rainy, ground, env_pkg,
         is_map) = build_scene_ex_with_package(
             "street", "", "warm", "day", location_data=loc)
        self.assertFalse(is_map)
        self.assertIsNotNone(env_pkg)
        self.assertEqual(env_pkg["archetype"], "EUROPEAN_STREET_1900")
        self.assertTrue(boxes)
        self.assertTrue(all(hasattr(b, "center") for b in boxes))

    def test_map_block_defers_with_empty_boxes(self):
        package = _ep1_package()
        loc = next(l for l in package["v1_locations"]
                   if l["id"] == "LOC_EUROPE_MAP")
        (boxes, _st, _sb, _r, _g, env_pkg,
         is_map) = build_scene_ex_with_package(
             "map", "", "warm", "day", location_data=loc)
        self.assertTrue(is_map)
        self.assertEqual(boxes, [])
        self.assertEqual(env_pkg["kind"], "map_deferred")

    def test_keyword_path_has_no_package(self):
        (boxes, _st, _sb, _r, _g, env_pkg,
         is_map) = build_scene_ex_with_package(
             "street", "Munich street", "warm", "day")
        self.assertFalse(is_map)
        self.assertIsNone(env_pkg)
        self.assertTrue(boxes)

    def test_build_scene_ex_delegates_trait_blocks(self):
        package = _ep1_package()
        loc = package["v1_locations"][0]
        boxes, _, _, _, _ = build_scene_ex(
            "street", "", "warm", "day", location_data=loc)
        names = {b.name for b in boxes}
        self.assertTrue(any(n.endswith("_wall") for n in names),
                        f"environment boxes expected, got {names}")


class TestMapSpecGating(unittest.TestCase):
    def _map_shot(self):
        package = _ep1_package()
        loc = next(l for l in package["v1_locations"]
                   if l["id"] == "LOC_EUROPE_MAP")
        return {"v1_location": loc}, package

    def test_default_spec_is_historical_with_highlights(self):
        shot, package = self._map_shot()
        spec = _map_spec_from_shot(shot, package)
        self.assertEqual(spec["mode"], "historical")
        self.assertEqual(spec["year"], "1914")
        labels = {e["label"] for e in spec["highlight"] if e["label"]}
        self.assertEqual(labels, {"Đức", "Áo-Hung", "Pháp", "Nga",
                                  "Anh", "Bỉ", "Serbia"})
        regions = {e["region"] for e in spec["highlight"]}
        self.assertIn("austria-hungary", regions)
        self.assertIn("austria", regions)
        self.assertIn("hungary", regions)

    def test_border_description_is_not_a_country(self):
        traits = {"features": ["Biên giới lịch sử chính xác.",
                               "Anh hùng dân tộc."]}
        self.assertEqual(_map_highlight_entries(traits), [])

    def test_modern_mode_refused_when_forbidden(self):
        shot, package = self._map_shot()
        package = dict(package)
        package["map_config"] = {"mode": "modern"}
        with self.assertRaises(MapSpecError) as cm:
            _map_spec_from_shot(shot, package)
        self.assertIn("forbids modern borders", str(cm.exception))

    def test_modern_mode_allowed_with_recorded_override(self):
        shot, package = self._map_shot()
        package = dict(package)
        package["map_config"] = {"mode": "modern",
                                 "override_forbidden": True,
                                 "override_note": "Mai approved 2026-11-12"}
        spec = _map_spec_from_shot(shot, package)
        self.assertEqual(spec["mode"], "modern")

    def test_historical_1914_resolves_verified_dataset(self):
        # 2026-11-12: the OHM 1914 extract is VERIFIED in the registry,
        # so a 1914 map shot resolves without explicit configuration.
        shot, package = self._map_shot()
        spec = _map_spec_from_shot(shot, package)
        self.assertTrue(spec["dataset_path"].endswith(
            "assets/maps/historical/europe_1914/boundaries.geojson"))
        self.assertEqual(spec["provenance"]["dataset"],
                         "ohm_1914_europe")
        self.assertIn("OpenHistoricalMap", spec["attribution"])
        _img, rep = render_map(spec)
        self.assertEqual(rep["regions_count"], 35)
        self.assertIn("OpenHistoricalMap", rep["attribution"])

    def test_historical_uncovered_year_fails_loudly(self):
        # No VERIFIED dataset covers 1939: the gate still fails
        # loudly, naming the known candidates. (Before 2026-11-12
        # this test used 1914; the OHM verdict opened 1914.)
        shot, package = self._map_shot()
        loc = dict(shot["v1_location"])
        loc["period"] = "1939"
        shot = {"v1_location": loc}
        spec = _map_spec_from_shot(shot, package)
        with self.assertRaises(MissingHistoricalMapData) as cm:
            render_map(spec)
        self.assertIn("CShapes", str(cm.exception))
        self.assertIn("historical-basemaps", str(cm.exception))

    def test_russia_label_drawn_and_clamp_reported(self):
        spec = {"mode": "modern", "size": (960, 540),
                "highlight": [{"region": "russia", "label": "Nga"},
                              {"region": "atlantis", "label": "Atlantis"}]}
        _img, rep = render_map(spec)
        self.assertIn("Nga", rep["labels_drawn"])
        x, y = rep["label_positions"]["Nga"]
        self.assertGreaterEqual(x, 0)
        self.assertLess(x, 960)
        self.assertIn("Nga", rep["labels_clamped"])
        self.assertIn("russia", rep["highlight_matched"])
        self.assertIn("atlantis", rep["highlight_unmatched"])


class TestRenderShotEnvironmentPath(unittest.TestCase):
    def test_still_carries_archetype(self):
        package = _ep1_package()
        shots = plan_shots(
            package,
            [{"line_index": i + 1, "duration": 3.0} for i in range(9)])
        for i, s in enumerate(shots):
            s["index"] = i
        first = next(s for s in shots if s.get("scene") == 1)
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot({"shot": first, "package": package,
                                   "out_dir": tmp, "still_only": True})
            self.assertEqual(result["environment_archetype"],
                             "EUROPEAN_STREET_1900")
            self.assertIsNotNone(result["environment_provenance"])
            self.assertTrue(Path(result["still"]).exists())

    def test_map_shot_renders_with_verified_dataset(self):
        # 2026-11-12: the OHM 1914 extract is VERIFIED, so the Ep1
        # scene-2 map shot renders instead of failing at the gate.
        package = _ep1_package()
        shots = plan_shots(
            package,
            [{"line_index": i + 1, "duration": 3.0} for i in range(9)])
        for i, s in enumerate(shots):
            s["index"] = i
        map_shot = next(s for s in shots if s.get("scene") == 2)
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot({"shot": map_shot, "package": package,
                                   "out_dir": tmp, "still_only": True})
            self.assertTrue(Path(result["still"]).exists())


if __name__ == "__main__":
    unittest.main()
