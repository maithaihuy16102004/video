"""Tests for ai_clip_studio.map_registry — the historical-map gate.

The real registry (assets/maps/) is the fixture: the OHM dataset must
resolve with a matching checksum, the rejected dataset must be
refused, and tampering / unknown ids / uncovered years must fail
loudly. A synthetic registry in a temp dir covers the tamper case
without touching the real files.
"""

import copy
import hashlib
import json
import unittest
from pathlib import Path

from ai_clip_studio.map_registry import (
    REGISTRY_PATH, RegistryError, resolve_dataset, resolve_for_year,
)


class TestRealRegistry(unittest.TestCase):
    def test_ohm_resolves(self):
        rec = resolve_dataset("ohm_1914_europe")
        self.assertTrue(Path(rec["geometry_path"]).exists())
        self.assertIn("OpenHistoricalMap", rec["attribution"])
        self.assertIn("CC BY 4.0", rec["attribution"])
        self.assertEqual(rec["valid_from"], "1914-07-28")

    def test_ohm_geometry_loads(self):
        rec = resolve_dataset("ohm_1914_europe")
        data = json.loads(Path(rec["geometry_path"]).read_text())
        self.assertEqual(data["type"], "FeatureCollection")
        self.assertEqual(len(data["features"]), 35)
        names = [f["properties"]["NAME"] for f in data["features"]]
        self.assertIn("German Reich", names)
        self.assertIn("Ottoman Empire", names)

    def test_rejected_dataset_refused(self):
        with self.assertRaises(RegistryError):
            resolve_dataset("historical-basemaps_world_1914")

    def test_unknown_dataset_refused(self):
        with self.assertRaises(RegistryError):
            resolve_dataset("no_such_dataset")

    def test_resolve_for_1914(self):
        rec = resolve_for_year(1914)
        self.assertEqual(rec["dataset_id"], "ohm_1914_europe")

    def test_resolve_for_uncovered_year_refused(self):
        with self.assertRaises(RegistryError):
            resolve_for_year(1939)


class TestTamperDetection(unittest.TestCase):
    def test_checksum_mismatch_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            geo = base / "g.geojson"
            geo.write_text('{"type":"FeatureCollection","features":[]}')
            digest = hashlib.sha256(geo.read_bytes()).hexdigest()
            reg = {"datasets": [{
                "dataset_id": "d1", "verification_status": "VERIFIED",
                "path": "g.geojson", "geometry_checksum": digest,
                "geographic_region": "Europe",
                "valid_from": "1914-01-01", "valid_to": "1914-12-31",
            }]}
            reg_path = base / "registry.json"
            reg_path.write_text(json.dumps(reg))
            self.assertEqual(resolve_dataset("d1", reg_path)["dataset_id"],
                             "d1")
            geo.write_text('{"type":"FeatureCollection","features":[1]}')
            with self.assertRaises(RegistryError):
                resolve_dataset("d1", reg_path)

    def test_unverified_status_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            geo = base / "g.geojson"
            geo.write_text('{"type":"FeatureCollection","features":[]}')
            digest = hashlib.sha256(geo.read_bytes()).hexdigest()
            reg = {"datasets": [{
                "dataset_id": "d2", "verification_status": "UNDER_REVIEW",
                "path": "g.geojson", "geometry_checksum": digest,
                "geographic_region": "Europe",
                "valid_from": "1914-01-01", "valid_to": "1914-12-31",
            }]}
            reg_path = base / "registry.json"
            reg_path.write_text(json.dumps(reg))
            with self.assertRaises(RegistryError):
                resolve_dataset("d2", reg_path)


if __name__ == "__main__":
    unittest.main()
