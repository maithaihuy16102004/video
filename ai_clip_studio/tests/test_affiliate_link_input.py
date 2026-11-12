"""Tests: link-paste input (link_input.py).

No test in this file touches the network: downloaders are fakes that
copy the local synthetic fixture or raise structured DownloadFailure
values. The gate tests assert the fake is NEVER called for refused
requests. Projects live in an isolated temporary AffiliateStore.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio.affiliate.link_input import (
    handle_link_post,
    handle_link_submit,
    match_link_fetch_path,
    render_link_paste_section,
    validate_link_url,
)
from ai_clip_studio.affiliate.providers import (
    REASON_AUTH_REQUIRED,
    REASON_COOKIES_REQUIRED,
    REASON_NETWORK_ERROR,
    REASON_NOT_AVAILABLE,
    REASON_NOT_FOUND,
    REASON_UNSUPPORTED_URL,
    DownloadFailure,
    FakeDownloader,
    FailingDownloader,
)
from ai_clip_studio.affiliate.schema import (
    AffiliateProject,
    ProductInfo,
    SourceAuthorization,
)
from ai_clip_studio.affiliate.store import AffiliateStore
from ai_clip_studio.affiliate.video.probe import sha256_file

FIXTURES = Path.home() / "workspace/acceptance_loop/affiliate_fixtures"
FIXTURE = FIXTURES / "fixture.mp4"
EXAMPLE_URL = "https://example.com/videos/product-demo.mp4"
DOUYIN_URL = "https://www.douyin.com/video/7698375090295314417"


class _FakeIngestDownloader:
    """Ingest-callable fake: copies the fixture; records calls."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, url: str, target: Path) -> Path:
        self.calls.append(url)
        shutil.copyfile(FIXTURE, target)
        return target


class _FailingIngestDownloader:
    """Ingest-callable fake that always raises one DownloadFailure."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        self.calls: list[str] = []

    def __call__(self, url: str, target: Path) -> Path:
        self.calls.append(url)
        raise DownloadFailure(self.reason, f"fake {self.reason}")


class _FakeHandler:
    """Same _send surface as affiliate_api's FakeHandler in tests."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, dict]] = []

    def _send(self, payload, status=200):
        self.sent.append((status, payload))
        return payload


class LinkInputTestCase(unittest.TestCase):
    def setUp(self) -> None:
        assert FIXTURE.is_file(), "run generate_fixture.py first"
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self.store = AffiliateStore(self._root / "store")
        self.ingest_dir = self._root / "ingest"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _project(self, auth_type: str = "SELLER_AUTHORIZED",
                 confirmed: bool = True) -> str:
        project = AffiliateProject(
            project_id=self.store.new_project_id(),
            project_name="link-test",
            product=ProductInfo(product_name="Hộp đựng đồ"),
            authorization=SourceAuthorization(
                authorization_type=auth_type,
                commercial_rights_confirmed=confirmed))
        self.store.create(project)
        return project.project_id

    def _submit(self, project_id: str, downloader=None, **body_kw):
        body = {"source_url": EXAMPLE_URL}
        body.update(body_kw)
        return handle_link_submit(project_id, body,
                                  store_dir=self.ingest_dir,
                                  downloader=downloader,
                                  store=self.store)


class TestGateFirst(LinkInputTestCase):
    def test_unknown_refused_403_before_any_downloader_call(self) -> None:
        project_id = self._project(auth_type="UNKNOWN", confirmed=True)
        fake = _FakeIngestDownloader()
        status, payload = self._submit(project_id, fake)
        self.assertEqual(status, 403)
        self.assertEqual(payload["status"], "GATE_REFUSED")
        self.assertIn("reasons", payload)
        self.assertEqual(fake.calls, [])

    def test_unconfirmed_refused_403_before_any_downloader_call(self) -> None:
        project_id = self._project(confirmed=False)
        fake = _FakeIngestDownloader()
        status, _ = self._submit(project_id, fake)
        self.assertEqual(status, 403)
        self.assertEqual(fake.calls, [])

    def test_gate_refusal_via_submitted_authorization(self) -> None:
        # Stored auth is fine, but the submitted declaration is
        # UNKNOWN/unconfirmed: the submitted declaration governs.
        project_id = self._project()
        fake = _FakeIngestDownloader()
        status, _ = self._submit(
            project_id, fake,
            authorization={"authorization_type": "UNKNOWN",
                           "commercial_rights_confirmed": False})
        self.assertEqual(status, 403)
        self.assertEqual(fake.calls, [])

    def test_no_authorization_record_refused(self) -> None:
        project = AffiliateProject(
            project_id=self.store.new_project_id(),
            project_name="no-auth",
            product=ProductInfo(product_name="Hộp đựng đồ"),
            authorization=None)
        self.store.create(project)
        fake = _FakeIngestDownloader()
        status, _ = self._submit(project.project_id, fake)
        self.assertEqual(status, 403)
        self.assertEqual(fake.calls, [])

    def test_invalid_authorization_type_is_400(self) -> None:
        project_id = self._project()
        fake = _FakeIngestDownloader()
        status, _ = self._submit(
            project_id, fake,
            authorization={"authorization_type": "BOGUS",
                           "commercial_rights_confirmed": True})
        self.assertEqual(status, 400)
        self.assertEqual(fake.calls, [])


class TestSuccessfulFetch(LinkInputTestCase):
    def test_seller_authorized_calls_downloader_and_records_source(self) -> None:
        project_id = self._project()
        fake = _FakeIngestDownloader()
        status, payload = self._submit(project_id, fake)
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["status"], "FETCHED")
        self.assertEqual(fake.calls, [EXAMPLE_URL])
        source = payload["source_video"]
        self.assertEqual(source["sha256"], sha256_file(FIXTURE))
        self.assertEqual(source["resolution"], "1280x720")
        # Regression: the probe sees temp file "download.bin", but the
        # recorded container must be schema vocabulary (AFF022).
        self.assertEqual(source["container"], "mp4")
        self.assertEqual(source["source_url"], EXAMPLE_URL)
        self.assertTrue(Path(source["stored_path"]).is_file())
        self.assertEqual(payload["ingest"]["gate"]["decision"], "allowed")
        self.assertEqual(payload["next_stage"], "transcription")
        # Persisted on the project, stage marked done with real detail.
        project = self.store.get(project_id)
        assert project is not None and project.source_video is not None
        self.assertEqual(project.source_video.sha256, sha256_file(FIXTURE))
        stages = {s["stage"]: s for s in project.stages}
        self.assertEqual(stages["upload"]["status"], "done")

    def test_fetch_style_provider_downloader_works(self) -> None:
        project_id = self._project()
        fake = FakeDownloader(FIXTURE)
        status, payload = self._submit(project_id, fake)
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["status"], "FETCHED")
        self.assertEqual(fake.calls, [EXAMPLE_URL])

    def test_submitted_authorization_overrides_and_persists(self) -> None:
        project_id = self._project(auth_type="UNKNOWN", confirmed=False)
        fake = _FakeIngestDownloader()
        status, _ = self._submit(
            project_id, fake,
            authorization={"authorization_type": "SELLER_AUTHORIZED",
                           "commercial_rights_confirmed": True,
                           "rights_note": "người bán cho phép"})
        self.assertEqual(status, 200)
        project = self.store.get(project_id)
        assert project is not None and project.authorization is not None
        self.assertEqual(project.authorization.authorization_type,
                         "SELLER_AUTHORIZED")
        self.assertTrue(project.authorization.commercial_rights_confirmed)

    def test_stored_authorization_used_when_body_has_none(self) -> None:
        project_id = self._project()
        fake = _FakeIngestDownloader()
        status, _ = self._submit(project_id, fake)
        self.assertEqual(status, 200)
        self.assertEqual(fake.calls, [EXAMPLE_URL])

    def test_default_downloader_resolved_from_registry_after_gate(self) -> None:
        # The default path resolves via providers.get_provider; patch
        # it to a fake so no real network access is attempted.
        project_id = self._project()
        fake = FakeDownloader(FIXTURE)
        with mock.patch(
                "ai_clip_studio.affiliate.link_input.get_provider",
                return_value=fake) as patched:
            status, _ = self._submit(project_id, None)
        self.assertEqual(status, 200)
        patched.assert_called_once_with("downloader")
        self.assertEqual(fake.calls, [EXAMPLE_URL])

    def test_douyin_url_shape_accepted_by_validation(self) -> None:
        self.assertEqual(validate_link_url(DOUYIN_URL), [])


class TestUrlValidation(LinkInputTestCase):
    def test_rejects_empty_and_non_http_urls(self) -> None:
        for bad in ("", "   ", "not a url", "ftp://example.com/v.mp4",
                    "https:///no-host.mp4",
                    "https://user:pass@example.com/v.mp4"):
            self.assertTrue(validate_link_url(bad), f"expected refusal: {bad!r}")

    def test_handler_returns_400_without_calling_downloader(self) -> None:
        project_id = self._project()
        fake = _FakeIngestDownloader()
        for bad in ("", "not a url", "ftp://example.com/v.mp4"):
            status, payload = self._submit(project_id, fake,
                                           source_url=bad)
            self.assertEqual(status, 400, bad)
            self.assertIn("reasons", payload)
        self.assertEqual(fake.calls, [])

    def test_unknown_project_is_404(self) -> None:
        fake = _FakeIngestDownloader()
        status, payload = self._submit("aff_does_not_exist", fake)
        self.assertEqual(status, 404)
        self.assertIn("project not found", payload["error"])
        self.assertEqual(fake.calls, [])


class TestFailureMapping(LinkInputTestCase):
    def test_each_reason_maps_to_honest_status_no_file_claimed(self) -> None:
        cases = [
            (REASON_UNSUPPORTED_URL, "FETCH_UNSUPPORTED", 502),
            (REASON_COOKIES_REQUIRED, "FETCH_BLOCKED", 502),
            (REASON_AUTH_REQUIRED, "FETCH_BLOCKED", 502),
            (REASON_NETWORK_ERROR, "FETCH_FAILED", 502),
            (REASON_NOT_FOUND, "FETCH_NOT_FOUND", 502),
            (REASON_NOT_AVAILABLE, "DOWNLOADER_UNAVAILABLE", 503),
        ]
        for reason, expected_status, expected_http in cases:
            with self.subTest(reason=reason):
                project_id = self._project()
                fake = _FailingIngestDownloader(reason)
                status, payload = self._submit(project_id, fake)
                self.assertEqual(status, expected_http, payload)
                self.assertEqual(payload["status"], expected_status)
                self.assertEqual(payload["reason"], reason)
                self.assertIn("message_vi", payload)
                self.assertTrue(payload["message_vi"])
                self.assertIn("tải file", payload["fallback_vi"])
                self.assertIsNone(payload["source_video"])
                self.assertFalse(payload["file_claimed"])
                self.assertEqual(fake.calls, [EXAMPLE_URL])
                project = self.store.get(project_id)
                assert project is not None
                self.assertIsNone(project.source_video)
                stages = {s["stage"]: s for s in project.stages}
                self.assertEqual(stages["upload"]["status"], "failed")

    def test_fetch_style_failing_downloader_maps_the_same(self) -> None:
        project_id = self._project()
        failing = FailingDownloader(REASON_COOKIES_REQUIRED,
                                    "Fresh cookies are needed")
        status, payload = self._submit(project_id, failing)
        self.assertEqual(status, 502)
        self.assertEqual(payload["status"], "FETCH_BLOCKED")
        self.assertIsNone(payload["source_video"])
        self.assertFalse(payload["file_claimed"])

    def test_non_video_download_is_fetch_invalid_422(self) -> None:
        def _junk(url: str, target: Path) -> Path:
            target.write_bytes(b"this is not a video")
            return target
        project_id = self._project()
        status, payload = self._submit(project_id, _junk)
        self.assertEqual(status, 422)
        self.assertEqual(payload["status"], "FETCH_INVALID")
        self.assertIsNone(payload["source_video"])
        self.assertFalse(payload["file_claimed"])


class TestHtmlFragment(unittest.TestCase):
    def test_fragment_contains_all_required_elements(self) -> None:
        html = render_link_paste_section()
        self.assertIn('id="linkPasteUrl"', html)
        self.assertIn("douyin.com", html.lower())
        self.assertIn('id="linkAuthType"', html)
        for value in ("USER_OWNED", "LICENSED", "SELLER_AUTHORIZED",
                      "UNKNOWN"):
            self.assertIn(f'value="{value}"', html)
        self.assertIn('id="linkRightsConfirmed"', html)
        self.assertIn("Dán link và tải video", html)
        self.assertIn("hoặc tải file lên", html.lower())
        self.assertIn("link-fetch", html)
        self.assertIn("STAGE-2 INSERTION POINT", html)
        self.assertIn('id="linkFetchOut"', html)


class TestMountHelpers(unittest.TestCase):
    def test_match_link_fetch_path(self) -> None:
        self.assertEqual(
            match_link_fetch_path("/api/affiliate/projects/aff_abc/link-fetch"),
            "aff_abc")
        self.assertIsNone(match_link_fetch_path(
            "/api/affiliate/projects/aff_abc/export"))
        self.assertIsNone(match_link_fetch_path("/api/affiliate/projects"))

    def test_handle_link_post_wrapper_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = AffiliateStore(root / "store")
            project = AffiliateProject(
                project_id=store.new_project_id(),
                project_name="wrap",
                product=ProductInfo(product_name="Hộp đựng đồ"),
                authorization=SourceAuthorization(
                    authorization_type="SELLER_AUTHORIZED",
                    commercial_rights_confirmed=True))
            store.create(project)
            handler = _FakeHandler()
            handled = handle_link_post(
                handler, project.project_id,
                {"source_url": EXAMPLE_URL},
                store_dir=root / "ingest",
                downloader=_FakeIngestDownloader(), store=store)
            self.assertTrue(handled)
            self.assertEqual(len(handler.sent), 1)
            status, payload = handler.sent[0]
            self.assertEqual(status, 200)
            self.assertEqual(payload["status"], "FETCHED")


if __name__ == "__main__":
    unittest.main()
