"""Unit tests for ai_clip_studio.map_renderer (stdlib unittest).

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/agent/
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.map_renderer import (
    DATASETS,
    MODERN_BOUNDARY_NOTE,
    MapSpecError,
    MissingHistoricalMapData,
    _project,
    _route_points_up_to,
    load_dataset,
    parse_svg_paths,
    render_map,
)

EUROPE_FRAMING = {"lon_min": -12, "lon_max": 45,
                  "lat_min": 34, "lat_max": 72}


class TestModernMode(unittest.TestCase):
    def test_modern_renders_real_polygons(self):
        img, rep = render_map({"mode": "modern", "size": (480, 270),
                               "framing": EUROPE_FRAMING})
        self.assertEqual(img.size, (480, 270))
        self.assertGreater(rep["regions_count"], 40)
        self.assertIn("Germany", rep["regions_drawn"])
        self.assertIn("France", rep["regions_drawn"])
        self.assertFalse(rep["rectangular_cards"])

    def test_modern_boundary_note_everywhere(self):
        _, rep = render_map({"mode": "modern", "size": (480, 270),
                             "framing": EUROPE_FRAMING})
        self.assertEqual(rep["boundary_note"], MODERN_BOUNDARY_NOTE)
        self.assertIn("Public domain", rep["dataset"]["license"])
        self.assertIn("Natural Earth", rep["dataset"]["dataset"])

    def test_highlight_and_labels(self):
        _, rep = render_map({
            "mode": "modern", "size": (480, 270),
            "framing": EUROPE_FRAMING,
            "highlight": [{"region": "Germany", "color": (232, 180, 90)}],
            "labels": [{"text": "Đức", "region": "Germany"},
                       {"text": "Paris", "lon": 2.35, "lat": 48.86}]})
        self.assertIn("Đức", rep["labels_drawn"])
        self.assertIn("Paris", rep["labels_drawn"])
        # No duplicate default label for an explicitly labelled region.
        self.assertNotIn("Germany", rep["labels_drawn"])

    def test_dataset_registry_has_provenance(self):
        entry = DATASETS["natural_earth_110m_europe"]
        self.assertEqual(entry["status"], "embedded")
        self.assertEqual(entry["coverage"], "modern")
        data = load_dataset("natural_earth_110m_europe")
        self.assertEqual(len(data["features"]), 51)
        self.assertIn("provenance", data)


class TestHistoricalMode(unittest.TestCase):
    def test_missing_dataset_fails_loudly(self):
        with self.assertRaises(MissingHistoricalMapData) as ctx:
            render_map({"mode": "historical", "year": 1914})
        message = str(ctx.exception)
        self.assertIn("CShapes", message)
        self.assertIn("historical-basemaps", message)
        self.assertIn("CC BY-NC-SA", message)

    def test_supplied_dataset_renders_with_provenance(self):
        geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"NAME": "Test Empire"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [0, 0], [10, 0], [10, 8], [0, 8], [0, 0]]]},
            }],
        }
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as fh:
            json.dump(geojson, fh)
            path = fh.name
        img, rep = render_map({
            "mode": "historical", "year": 1914, "dataset_path": path,
            "provenance": {"dataset": "Test fixture",
                           "source_url": "fixture",
                           "license": "fixture-only"},
            "size": (480, 270),
            "framing": {"lon_min": -2, "lon_max": 12,
                        "lat_min": -2, "lat_max": 10}})
        self.assertIn("Test Empire", rep["regions_drawn"])
        self.assertEqual(rep["dataset"]["license"], "fixture-only")
        self.assertIn("1914", rep["boundary_note"])

    def test_unverified_historical_dataset_flagged(self):
        geojson = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {"NAME": "X"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [0, 0], [5, 0], [5, 5], [0, 5], [0, 0]]]},
        }]}
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as fh:
            json.dump(geojson, fh)
            path = fh.name
        _, rep = render_map({
            "mode": "historical", "year": 1914, "dataset_path": path,
            "size": (320, 180),
            "framing": {"lon_min": -1, "lon_max": 6,
                        "lat_min": -1, "lat_max": 6}})
        self.assertIn("unverified", rep["dataset"]["license"])


class TestSuppliedMode(unittest.TestCase):
    def test_svg_paths_render(self):
        img, rep = render_map({
            "mode": "supplied", "size": (480, 270),
            "svg_paths": [{"region": "Testland",
                           "d": "M 0 0 L 10 0 L 10 8 L 0 8 Z"}],
            "framing": {"lon_min": -2, "lon_max": 12,
                        "lat_min": -2, "lat_max": 10}})
        self.assertIn("Testland", rep["regions_drawn"])

    def test_svg_unsupported_command_rejected(self):
        with self.assertRaises(MapSpecError):
            parse_svg_paths([{"region": "X",
                              "d": "M 0 0 C 1 1 2 2 3 3 Z"}])

    def test_svg_degenerate_polygon_rejected(self):
        with self.assertRaises(MapSpecError):
            parse_svg_paths([{"region": "X", "d": "M 0 0 L 1 1 Z"}])

    def test_supplied_needs_geometry(self):
        with self.assertRaises(MapSpecError):
            render_map({"mode": "supplied"})

    def test_unknown_mode_rejected(self):
        with self.assertRaises(MapSpecError):
            render_map({"mode": "3d"})

    def test_bad_framing_rejected(self):
        with self.assertRaises(MapSpecError):
            render_map({"mode": "modern", "framing": {"lon_min": 0}})


class TestRouteAndProjection(unittest.TestCase):
    def test_route_progress_from_timeline_sync(self):
        _, rep = render_map({
            "mode": "modern", "size": (480, 270),
            "framing": EUROPE_FRAMING,
            "route": {"points": [[0, 50], [10, 50]],
                      "timeline_sync": {"t": 3.0, "duration": 12.0}}})
        self.assertEqual(rep["route"]["progress_t"], 0.25)
        self.assertTrue(rep["route"]["schematic"])

    def test_route_progress_clamped(self):
        _, rep = render_map({
            "mode": "modern", "size": (480, 270),
            "framing": EUROPE_FRAMING,
            "route": {"points": [[0, 50], [10, 50]],
                      "progress_t": 2.5}})
        self.assertEqual(rep["route"]["progress_t"], 1.0)

    def test_route_subpolyline(self):
        pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
        start = _route_points_up_to(pts, 0.0)
        self.assertEqual(start, [pts[0]])
        half = _route_points_up_to(pts, 0.5)
        self.assertEqual(half[-1], (10.0, 0.0))
        full = _route_points_up_to(pts, 1.0)
        self.assertEqual(full, pts)

    def test_projection_monotonic_and_centred(self):
        size = (1920, 1080)
        x0, _ = _project(-12, 50, EUROPE_FRAMING, size)
        x1, _ = _project(45, 50, EUROPE_FRAMING, size)
        self.assertLess(x0, x1)
        _, y_south = _project(0, 34, EUROPE_FRAMING, size)
        _, y_north = _project(0, 72, EUROPE_FRAMING, size)
        self.assertGreater(y_south, y_north)  # north is up
        # The map is centred: equal margins left/right.
        self.assertAlmostEqual(x0, size[0] - x1, delta=2.0)


if __name__ == "__main__":
    unittest.main()
