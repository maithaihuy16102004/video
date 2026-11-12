"""Tests: affiliate source probing (ffprobe + SHA-256)."""
from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from ai_clip_studio.affiliate.video.models import export_gate_check
from ai_clip_studio.affiliate.video.probe import (
    ProbeError, container_supported, probe_source, sha256_file,
    verify_checksum)

FIXTURES = Path.home() / "workspace/acceptance_loop/affiliate_fixtures"
FIXTURE = FIXTURES / "fixture.mp4"


class TestProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert FIXTURE.is_file(), (
            "fixture missing — run "
            "acceptance_loop/affiliate_fixtures/generate_fixture.py")

    def test_probe_fixture_metadata(self) -> None:
        info = probe_source(FIXTURE)
        self.assertEqual(info.width, 1280)
        self.assertEqual(info.height, 720)
        self.assertEqual(info.fps, 30.0)
        self.assertAlmostEqual(info.duration_sec, 9.0, places=1)
        self.assertEqual(info.video_codec, "h264")
        self.assertEqual(info.audio_codec, "aac")
        self.assertTrue(info.has_audio)
        self.assertEqual(info.container, "mp4")
        self.assertEqual(info.orientation, "horizontal")
        self.assertEqual(info.aspect_ratio, "16:9")
        self.assertEqual(info.resolution, "1280x720")
        self.assertRegex(info.sha256, r"^[0-9a-f]{64}$")
        self.assertGreater(info.file_size_bytes, 10_000)

    def test_sha256_matches_hashlib(self) -> None:
        expected = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(sha256_file(FIXTURE), expected)
        self.assertTrue(verify_checksum(FIXTURE, expected))
        self.assertFalse(verify_checksum(FIXTURE, "0" * 64))

    def test_probe_is_readonly(self) -> None:
        before = sha256_file(FIXTURE)
        probe_source(FIXTURE)
        self.assertEqual(sha256_file(FIXTURE), before)

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(ProbeError):
            probe_source(FIXTURES / "does_not_exist.mp4")

    def test_non_video_raises(self) -> None:
        with self.assertRaises(ProbeError):
            probe_source(FIXTURES / "fixture_manifest.json")

    def test_container_supported(self) -> None:
        info = probe_source(FIXTURE)
        ok, reason = container_supported(info)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_schema_dict_shape(self) -> None:
        info = probe_source(FIXTURE)
        data = info.to_source_video_dict()
        self.assertEqual(data["file_name"], "fixture.mp4")
        self.assertEqual(data["resolution"], "1280x720")
        self.assertEqual(data["fps"], 30.0)
        self.assertEqual(data["orientation"], "horizontal")
        self.assertEqual(data["aspect_ratio"], "16:9")
        self.assertEqual(data["sha256"], info.sha256)
        # The schema validator must accept the probe output.
        from ai_clip_studio.affiliate.schema import validate_project
        issues = validate_project({
            "project_id": "probe-test",
            "source_video": data,
        })
        self.assertEqual(issues, [])

    def test_export_gate(self) -> None:
        allowed, _ = export_gate_check("USER_OWNED", True)
        self.assertTrue(allowed)
        allowed, reasons = export_gate_check("UNKNOWN", True)
        self.assertFalse(allowed)
        self.assertTrue(any("UNKNOWN" in r for r in reasons))
        allowed, _ = export_gate_check("LICENSED", False)
        self.assertFalse(allowed)
        allowed, _ = export_gate_check("BOGUS", True)
        self.assertFalse(allowed)
        allowed, _ = export_gate_check("SYNTHETIC_FIXTURE", True)
        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
