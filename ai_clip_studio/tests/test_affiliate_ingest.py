"""Tests: ingest gate — authorization enforced in code, pre-network.

No test in this file touches the network: the downloader is a fake
that copies the local synthetic fixture. The gate tests assert the
fake is NEVER called for refused requests.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.affiliate.video.ingest import (
    IngestRefused, IngestRequest, ingest_source, load_ingest_record,
    store_filename, validate_ingest_request)
from ai_clip_studio.affiliate.video.probe import sha256_file

FIXTURES = Path.home() / "workspace/acceptance_loop/affiliate_fixtures"
FIXTURE = FIXTURES / "fixture.mp4"
EXAMPLE_URL = "https://example.com/videos/product-demo.mp4"


def _request(**overrides) -> IngestRequest:
    kwargs = {
        "source_url": EXAMPLE_URL,
        "authorization_type": "SELLER_AUTHORIZED",
        "commercial_rights_confirmed": True,
    }
    kwargs.update(overrides)
    return IngestRequest(**kwargs)


class _FakeDownloader:
    """Copies the local fixture; records every invocation."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, url: str, target: Path) -> Path:
        self.calls.append(url)
        shutil.copyfile(FIXTURE, target)
        return target


class TestGate(unittest.TestCase):
    def test_unknown_refused_and_downloader_not_called(self) -> None:
        fake = _FakeDownloader()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(IngestRefused):
                ingest_source(_request(authorization_type="UNKNOWN"),
                              tmp, downloader=fake)
        self.assertEqual(fake.calls, [])

    def test_unconfirmed_refused_and_downloader_not_called(self) -> None:
        fake = _FakeDownloader()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(IngestRefused):
                ingest_source(_request(commercial_rights_confirmed=False),
                              tmp, downloader=fake)
        self.assertEqual(fake.calls, [])

    def test_bad_urls_refused(self) -> None:
        for bad in ("", "not a url", "ftp://example.com/v.mp4",
                    "https:///no-host.mp4",
                    "https://user:pass@example.com/v.mp4"):
            reasons = validate_ingest_request(_request(source_url=bad))
            self.assertTrue(reasons, f"expected refusal for {bad!r}")

    def test_synthetic_fixture_marker_refused_for_urls(self) -> None:
        reasons = validate_ingest_request(
            _request(authorization_type="SYNTHETIC_FIXTURE"))
        self.assertTrue(any("SYNTHETIC_FIXTURE" in r for r in reasons))

    def test_valid_request_passes_gate(self) -> None:
        self.assertEqual(validate_ingest_request(_request()), [])

    def test_no_downloader_refuses_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(IngestRefused) as ctx:
                ingest_source(_request(), tmp, downloader=None)
        self.assertIn("no download was attempted", str(ctx.exception))


class TestIngestFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert FIXTURE.is_file(), "run generate_fixture.py first"
        cls.tmp = tempfile.TemporaryDirectory(prefix="aff_ing_test_")
        cls.store = Path(cls.tmp.name) / "store"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_fake_download_stores_immutable_copy(self) -> None:
        fake = _FakeDownloader()
        record = ingest_source(_request(), self.store, downloader=fake,
                               downloader_name="fake-test")
        self.assertEqual(fake.calls, [EXAMPLE_URL])
        self.assertEqual(record.sha256, sha256_file(FIXTURE))
        self.assertEqual(record.local_path,
                         str(self.store / store_filename(record.sha256,
                                                         "mp4")))
        self.assertEqual(record.probe["resolution"], "1280x720")
        self.assertFalse(record.reused_existing)
        manifest = load_ingest_record(record.manifest_path)
        self.assertEqual(manifest["source_url"], EXAMPLE_URL)
        self.assertEqual(manifest["gate"]["decision"], "allowed")
        self.assertEqual(manifest["authorization_type"],
                         "SELLER_AUTHORIZED")

    def test_second_ingest_reuses_file_without_overwrite(self) -> None:
        fake = _FakeDownloader()
        first = ingest_source(_request(), self.store, downloader=fake,
                              downloader_name="fake-test")
        before = Path(first.local_path).read_bytes()
        manifest_before = Path(first.manifest_path).read_text()
        second = ingest_source(_request(), self.store, downloader=fake,
                               downloader_name="fake-test")
        self.assertTrue(second.reused_existing)
        self.assertEqual(second.local_path, first.local_path)
        self.assertEqual(Path(second.local_path).read_bytes(), before)
        self.assertEqual(Path(second.manifest_path).read_text(),
                         manifest_before)

    def test_store_collision_refuses_to_overwrite(self) -> None:
        checksum = sha256_file(FIXTURE)
        # Pre-plant a DIFFERENT file at the checksum-derived name.
        planted = self.store / store_filename(checksum, "mp4")
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_bytes(b"not the fixture")
        with tempfile.TemporaryDirectory() as tmp2:
            other_store = Path(tmp2) / "store"
            other_store.mkdir()
            shutil.copyfile(planted,
                            other_store / store_filename(checksum, "mp4"))
            with self.assertRaises(IngestRefused):
                ingest_source(_request(), other_store,
                              downloader=_FakeDownloader())

    def test_downloader_producing_no_file_refused(self) -> None:
        def _noop(url: str, target: Path) -> Path:
            return target  # never writes anything
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(IngestRefused):
                ingest_source(_request(), tmp, downloader=_noop)

    def test_downloader_producing_non_video_refused(self) -> None:
        def _junk(url: str, target: Path) -> Path:
            target.write_bytes(b"this is not a video")
            return target
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(IngestRefused):
                ingest_source(_request(), tmp, downloader=_junk)


if __name__ == "__main__":
    unittest.main()
