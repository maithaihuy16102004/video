"""Phase 1 tests — affiliate API handlers + store + source intake.

Uses a fake handler object (same _send/_send_file/_send_html surface
as the product server's Handler) so the mount-ready routing is tested
without starting a server and without touching server.py.
"""
from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.affiliate import affiliate_api
from ai_clip_studio.affiliate.store import AffiliateStore

FIXTURES = Path.home() / "workspace" / "acceptance_loop" / "affiliate_fixtures"


class FakeHandler:
    def __init__(self):
        self.sent = []
        self.files = []
        self.html = None

    def _send(self, payload, status=200):
        self.sent.append((status, payload))
        return payload

    def _send_file(self, path, content_type):
        self.files.append((Path(path), content_type))

    def _send_html(self, text):
        self.html = text

    @property
    def last(self):
        return self.sent[-1]


class AffiliateApiTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._store = AffiliateStore(Path(self._tmp.name) / "store")
        self._orig_store = affiliate_api.STORE
        affiliate_api.STORE = self._store
        self.handler = FakeHandler()

    def tearDown(self):
        affiliate_api.STORE = self._orig_store
        self._tmp.cleanup()

    def _create(self, with_source=False):
        body = {
            "project_name": "test-01",
            "product": {"product_name": "Hộp đựng đồ"},
            "authorization": {"authorization_type": "USER_OWNED",
                              "commercial_rights_confirmed": True},
        }
        if with_source:
            video = FIXTURES / "synthetic_product_demo.mp4"
            body["source"] = {
                "file_name": "synthetic_product_demo.mp4",
                "data_base64": base64.b64encode(video.read_bytes()).decode(),
            }
        handled = affiliate_api.handle_affiliate_post(
            self.handler, "/api/affiliate/projects", body)
        self.assertTrue(handled)
        return self.handler.last


class TestHealthAndVoices(AffiliateApiTestCase):
    def test_health(self):
        self.assertTrue(affiliate_api.handle_affiliate_get(
            self.handler, "/api/affiliate/health"))
        status, payload = self.handler.last
        self.assertEqual(status, 200)
        self.assertEqual(payload["schema"], "AFFILIATE_PROJECT_V1")

    def test_voices_lists_real_presets(self):
        self.assertTrue(affiliate_api.handle_affiliate_get(
            self.handler, "/api/affiliate/voices"))
        _, payload = self.handler.last
        self.assertIn("female_review", payload["presets"])
        self.assertIn("male_review", payload["presets"])

    def test_ui_served(self):
        self.assertTrue(affiliate_api.handle_affiliate_get(
            self.handler, "/affiliate"))
        self.assertIn("AI Affiliate Studio", self.handler.html)
        self.assertIn("bản quyền", self.handler.html)

    def test_unknown_route_not_handled(self):
        self.assertFalse(affiliate_api.handle_affiliate_get(
            self.handler, "/api/production/jobs/xyz"))
        self.assertFalse(affiliate_api.handle_affiliate_post(
            self.handler, "/api/production/draft", {}))


class TestProjectLifecycle(AffiliateApiTestCase):
    def test_create_project_minimal(self):
        status, payload = self._create()
        self.assertEqual(status, 201)
        self.assertTrue(payload["project_id"].startswith("aff_"))
        self.assertEqual(payload["product"]["product_name"], "Hộp đựng đồ")

    def test_create_requires_product_name(self):
        handled = affiliate_api.handle_affiliate_post(
            self.handler, "/api/affiliate/projects",
            {"product": {"product_name": ""},
             "authorization": {"authorization_type": "USER_OWNED",
                               "commercial_rights_confirmed": True}})
        self.assertTrue(handled)
        self.assertEqual(self.handler.last[0], 400)

    def test_create_with_inline_source_probes_and_checksums(self):
        status, payload = self._create(with_source=True)
        self.assertEqual(status, 201, payload)
        source = payload["source_video"]
        self.assertEqual(source["file_name"], "synthetic_product_demo.mp4")
        self.assertEqual(source["resolution"], "720x1280")
        self.assertEqual(source["orientation"], "vertical")
        self.assertTrue(source["has_audio"])
        self.assertEqual(len(source["sha256"]), 64)
        self.assertAlmostEqual(source["duration_sec"], 10.0, places=0)

    def test_chunked_upload_assembles(self):
        status, payload = self._create()
        project_id = payload["project_id"]
        video = FIXTURES / "synthetic_product_demo.mp4"
        raw = video.read_bytes()
        half = len(raw) // 2
        for index, chunk in enumerate((raw[:half], raw[half:])):
            handled = affiliate_api.handle_affiliate_post(
                self.handler,
                f"/api/affiliate/projects/{project_id}/upload-chunk",
                {"chunk_index": index,
                 "data_base64": base64.b64encode(chunk).decode()})
            self.assertTrue(handled)
        handled = affiliate_api.handle_affiliate_post(
            self.handler,
            f"/api/affiliate/projects/{project_id}/upload-complete",
            {"file_name": "synthetic_product_demo.mp4", "total_chunks": 2})
        self.assertTrue(handled)
        status, payload = self.handler.last
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["source_video"]["file_size_bytes"], len(raw))

    def test_chunked_upload_missing_chunk_rejected(self):
        status, payload = self._create()
        project_id = payload["project_id"]
        affiliate_api.handle_affiliate_post(
            self.handler,
            f"/api/affiliate/projects/{project_id}/upload-chunk",
            {"chunk_index": 0, "data_base64": base64.b64encode(b"abc").decode()})
        affiliate_api.handle_affiliate_post(
            self.handler,
            f"/api/affiliate/projects/{project_id}/upload-complete",
            {"file_name": "x.mp4", "total_chunks": 2})
        self.assertEqual(self.handler.last[0], 400)

    def test_get_and_history(self):
        _, payload = self._create()
        project_id = payload["project_id"]
        self.assertTrue(affiliate_api.handle_affiliate_get(
            self.handler, f"/api/affiliate/projects/{project_id}"))
        self.assertEqual(self.handler.last[1]["project_id"], project_id)
        self.assertTrue(affiliate_api.handle_affiliate_get(
            self.handler, "/api/affiliate/projects"))
        self.assertEqual(len(self.handler.last[1]["projects"]), 1)

    def test_unknown_project_404(self):
        self.assertTrue(affiliate_api.handle_affiliate_get(
            self.handler, "/api/affiliate/projects/aff_nope"))
        self.assertEqual(self.handler.last[0], 404)

    def test_ingest_analysis_and_ocr(self):
        _, payload = self._create()
        project_id = payload["project_id"]
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/analysis",
            {"scenes": [{"scene_id": "S1", "start_time": 0, "end_time": 5,
                         "visual_description": "mở hộp"}],
             "engine": "fallback"})
        self.assertEqual(self.handler.last[0], 200)
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/ocr-tracks",
            {"tracks": [{"text_id": "T1", "original_text": "你好",
                         "start_time": 0, "end_time": 1,
                         "text_classification": "SUBTITLE"}]})
        self.assertEqual(self.handler.last[0], 200)
        project = self._store.get(project_id)
        self.assertEqual(len(project.video_analysis.scenes), 1)
        self.assertEqual(len(project.ocr_tracks), 1)

    def test_edits_mirror_gate_reported(self):
        _, payload = self._create()
        project_id = payload["project_id"]
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/edits",
            {"operations": [{"operation": "hflip"}]})
        _, response = self.handler.last
        codes = [i["code"] for i in response["gate_issues"]]
        self.assertIn("AFF021", codes)

    def test_export_is_honest_501_in_phase1(self):
        _, payload = self._create(with_source=True)
        project_id = payload["project_id"]
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/export", {})
        status, response = self.handler.last
        self.assertEqual(status, 501)
        self.assertIn("Phase 1", response["error"])

    def test_export_refused_403_when_authorization_unknown(self):
        body = {
            "project_name": "unconfirmed",
            "product": {"product_name": "Hộp đựng đồ"},
            "authorization": {"authorization_type": "UNKNOWN",
                              "commercial_rights_confirmed": False},
            "source_url": "https://example.com/share/video/123",
        }
        affiliate_api.handle_affiliate_post(
            self.handler, "/api/affiliate/projects", body)
        self.assertEqual(self.handler.last[0], 201)
        project_id = self.handler.last[1]["project_id"]
        # The link was recorded as provenance; no file was fetched.
        source = self.handler.last[1]["source_video"]
        self.assertEqual(source["source_url"],
                         "https://example.com/share/video/123")
        self.assertEqual(source["sha256"], "")
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/export", {})
        status, response = self.handler.last
        self.assertEqual(status, 403)
        self.assertTrue(any("UNKNOWN" in r for r in response["reasons"]))

    def test_create_rejects_bad_source_url(self):
        affiliate_api.handle_affiliate_post(
            self.handler, "/api/affiliate/projects",
            {"project_name": "bad-url",
             "product": {"product_name": "X"},
             "authorization": {"authorization_type": "USER_OWNED",
                               "commercial_rights_confirmed": True},
             "source_url": "ftp://example.com/x"})
        self.assertEqual(self.handler.last[0], 400)

    def test_script_generate_approve_flow(self):
        _, payload = self._create()
        project_id = payload["project_id"]
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/script",
            {"variant": "demonstration", "target_seconds": 30,
             "visible_demonstration": "mở hộp, xếp đồ"})
        self.assertEqual(self.handler.last[0], 200)
        script = self.handler.last[1]["script"]
        self.assertFalse(script["approved"])
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/script/approve",
            {"approved_by": "Mai"})
        self.assertTrue(self.handler.last[1]["approved"])
        # Editing clears approval.
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/script/edit",
            {"segments": [{"segment_id": "SEG01", "section": "HOOK",
                           "text": "Câu mới."}]})
        self.assertFalse(self.handler.last[1]["approved"])

    def test_voice_requires_approval(self):
        _, payload = self._create()
        project_id = payload["project_id"]
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/script",
            {"variant": "demonstration", "target_seconds": 30})
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/voice",
            {"preset": "female_review"})
        self.assertEqual(self.handler.last[0], 409)

    def test_translate_without_key_flags_review(self):
        _, payload = self._create()
        project_id = payload["project_id"]
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/translate",
            {"mode": "NATURAL_LOCALIZATION"})
        _, response = self.handler.last
        self.assertEqual(response["translation"]["engine"], "fallback")

    def test_marketing_and_qa_endpoints(self):
        _, payload = self._create()
        project_id = payload["project_id"]
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/marketing", {})
        self.assertEqual(self.handler.last[0], 200)
        self.assertIn("package", self.handler.last[1])
        affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/qa", {})
        self.assertEqual(self.handler.last[0], 200)
        self.assertIn("verdict", self.handler.last[1]["qa"])

    def test_file_serving_path_safety(self):
        _, payload = self._create()
        project_id = payload["project_id"]
        affiliate_api.handle_affiliate_get(
            self.handler,
            f"/api/affiliate/projects/{project_id}/files/../../secret.txt")
        self.assertIn(self.handler.last[0], (400, 404))


class TestStore(unittest.TestCase):
    def test_stage_transitions_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AffiliateStore(Path(tmp))
            from ai_clip_studio.affiliate.schema import AffiliateProject
            project = AffiliateProject(project_id=store.new_project_id())
            store.create(project)
            store.set_stage(project.project_id, "upload", "done", "ok")
            loaded = store.get(project.project_id)
            stages = {s["stage"]: s["status"] for s in loaded.stages}
            self.assertEqual(stages["upload"], "done")
            self.assertEqual(len(store.list_projects()), 1)
            with self.assertRaises(ValueError):
                store.set_stage(project.project_id, "bogus", "done")
            with self.assertRaises(ValueError):
                store.set_stage(project.project_id, "upload", "bogus")


if __name__ == "__main__":
    unittest.main()
