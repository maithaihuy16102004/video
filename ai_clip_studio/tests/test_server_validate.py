"""Handler-level tests for the :8788 V1 validate + review UI (server.py).

Covers POST /api/production/validate (valid V1 fixture, invalid V1
422 with line-numbered errors, free-form note), the structured-422
surfacing of V1AdapterError on analyze/preflight/draft (never a bare
500), the synchronous draft refusal for invalid V1, the UI HTML
(V1 validate step + review + artifacts list), the artifacts endpoint
the job view consumes, and the GENERIC review walk for the newer
FIRST_PERSON_ROLEPLAY dialect (storytelling_mode, primary_character,
external_narrator, end card, QA expected counts, OUTPUT block).

No draft jobs are run: no rendering, no TTS, no Drive. The server
under test runs on an ephemeral port with a /tmp jobs dir.

Dialect note: the FIRST_PERSON_ROLEPLAY dialect of
examples/hitler_ep01_munich_1914.studio.md needs the parser extension
(a concurrent parser agent owns studio_script_v1.py, which is
read-only here). The two tests that exercise that file through the
HTTP endpoint SKIP with an explicit reason until the parser
recognises the dialect; the generic-walk test below them uses a
synthetic to_dict() shape and runs regardless, proving the review
code surfaces new-dialect fields without knowing their names.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_clip_studio import server as server_module  # noqa: E402
from ai_clip_studio.server import (  # noqa: E402
    Handler, _build_v1_review,
)
from ai_clip_studio.studio_script_v1 import detect_format  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = Path.home() / "workspace" / "video-upstream" / "fixtures" / \
    "episode01_hitler_1914_munich" / "script.txt"
NEW_SCRIPT = REPO_ROOT / "examples" / "hitler_ep01_munich_1914.studio.md"

INVALID_V1 = (
    "# STUDIO SCRIPT V1\n"
    "PROJECT: X\n"
    "SCENE 01: Test\n"
    "LOCATION: Somewhere\n"
)
DUP_CHAR_V1 = (
    "# STUDIO SCRIPT V1\n"
    "PROJECT: X\n"
    "CHARACTER: An\n"
    "CHARACTER: An\n"
    "SCENE 01: Test\n"
    "LOCATION: Somewhere\n"
    "AN: Xin chao.\n"
)
FREEFORM = "Một hôm trời mưa, An đi bộ trên phố và nhặt được chiếc ví cũ."


def _new_script_text() -> str:
    return NEW_SCRIPT.read_text(encoding="utf-8")


_NEW_DIALECT_RECOGNIZED = (
    NEW_SCRIPT.exists()
    and detect_format(_new_script_text()) == "studio_v1"
)


class _ScratchServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="v1_validate_ui_")
        cls._jobs_dir = Path(cls._tmp.name)
        cls._orig_jobs_root = server_module._jobs_root
        server_module._jobs_root = lambda: cls._jobs_dir  # noqa: E731
        cls._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls._port = cls._httpd.server_address[1]
        cls._thread = threading.Thread(
            target=cls._httpd.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._httpd.shutdown()
        cls._httpd.server_close()
        cls._thread.join(timeout=5)
        server_module._jobs_root = cls._orig_jobs_root
        server_module.JOBS.clear()
        server_module.ANALYSES.clear()
        cls._tmp.cleanup()

    def _request(self, method: str, path: str,
                 payload: dict | None = None) -> tuple[int, object]:
        conn = http.client.HTTPConnection("127.0.0.1", self._port, timeout=10)
        body = (json.dumps(payload, ensure_ascii=False).encode("utf-8")
                if payload else None)
        headers = {"Content-Type": "application/json"} if body else {}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        try:
            return resp.status, json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return resp.status, raw.decode("utf-8", errors="replace")

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        status, data = self._request("POST", path, payload)
        assert isinstance(data, dict), f"expected JSON object, got {data!r:.200}"
        return status, data


class TestHealthAndUI(_ScratchServer):
    def test_health(self) -> None:
        status, data = self._request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")

    def test_ui_contains_v1_validate_step_and_review(self) -> None:
        status, html = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIsInstance(html, str)
        for needle in (
            "Kiểm tra kịch bản V1",
            'id="btnValidate"',
            "validateScript",
            "renderValidation",
            "EXTERNAL_NARRATOR",
            "Chế độ kể chuyện",
            "End card",
            "QA (số lượng kỳ vọng)",
            "OUTPUT (xuất bản",
            "Thông tin khác",
            'id="draftGate"',
            'id="artifacts"',
            "loadArtifacts",
            "</html>",
        ):
            self.assertIn(needle, html, f"UI HTML missing: {needle}")


class TestValidateEndpoint(_ScratchServer):
    def test_validate_fixture_valid_with_review(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        status, data = self._post("/api/production/validate", {"script": text})
        self.assertEqual(status, 200)
        self.assertEqual(data["format"], "studio_script_v1")
        self.assertTrue(data["valid"])
        self.assertEqual(
            data["snapshot_hash"],
            hashlib.sha256(text.encode("utf-8")).hexdigest())
        self.assertEqual(data["errors"], [])
        summary = data["summary"]
        self.assertEqual(summary["characters"], 4)
        self.assertEqual(summary["scenes"], 8)
        self.assertEqual(summary["spoken_lines"], 10)
        review = data["review"]
        names = [c["name"] for c in review["characters"]]
        self.assertIn("Adolf Hitler", names)
        self.assertIn("Bà Chủ Nhà", names)
        for char in review["characters"]:
            for key in ("name", "role", "appearance", "traits",
                        "costume", "voice"):
                self.assertIn(key, char)
        self.assertEqual(len(review["scenes"]), 8)
        scene0 = review["scenes"][0]
        for key in ("number", "title", "location_text", "time_of_day",
                    "mood", "lines", "action_cues", "shots", "audio_cues"):
            self.assertIn(key, scene0, f"scene review missing {key}")
        cue_total = sum(len(v) for v in review["audio_cues"].values())
        self.assertEqual(cue_total, 27)
        self.assertIn("narrator_check", review)
        self.assertEqual(review["meta"]["project"],
                         "HITLER_EP01_MUNICH_1914")

    def test_validate_invalid_v1_422_line_numbered(self) -> None:
        status, data = self._post(
            "/api/production/validate", {"script": INVALID_V1})
        self.assertEqual(status, 422)
        self.assertEqual(data["format"], "studio_script_v1")
        self.assertFalse(data["valid"])
        self.assertTrue(data["errors"])
        for err in data["errors"]:
            self.assertIsInstance(err["line"], int)
            self.assertTrue(err["code"])
            self.assertTrue(err["message"])
        self.assertIn("V1E023", [e["code"] for e in data["errors"]])
        # The partial review is still returned for context.
        self.assertIn("review", data)

    def test_validate_duplicate_character_reports_source_line(self) -> None:
        status, data = self._post(
            "/api/production/validate", {"script": DUP_CHAR_V1})
        self.assertEqual(status, 422)
        dup = [e for e in data["errors"] if e["code"] == "V1E001"]
        self.assertTrue(dup, data["errors"])
        self.assertEqual(dup[0]["line"], 4)

    def test_validate_freeform_not_rejected(self) -> None:
        status, data = self._post(
            "/api/production/validate", {"script": FREEFORM})
        self.assertEqual(status, 200)
        self.assertEqual(data["format"], "freeform")
        self.assertTrue(data["valid"])
        self.assertTrue(data["note"])
        self.assertEqual(
            data["snapshot_hash"],
            hashlib.sha256(FREEFORM.encode("utf-8")).hexdigest())

    def test_validate_too_short(self) -> None:
        status, _ = self._post("/api/production/validate", {"script": "ngắn"})
        self.assertEqual(status, 400)


class TestV1ErrorSurfacing(_ScratchServer):
    def test_analyze_invalid_v1_is_422_not_500(self) -> None:
        status, data = self._post(
            "/api/production/analyze", {"script": INVALID_V1})
        self.assertEqual(status, 422)
        self.assertTrue(data["errors"])
        self.assertIn("V1E023", [e["code"] for e in data["errors"]])

    def test_preflight_invalid_v1_is_422_not_500(self) -> None:
        status, data = self._post(
            "/api/production/preflight", {"script": INVALID_V1})
        self.assertEqual(status, 422)
        self.assertTrue(data["errors"])

    def test_draft_invalid_v1_refused_without_queueing(self) -> None:
        before = set(self._jobs_dir.iterdir())
        status, data = self._post(
            "/api/production/draft", {"script": INVALID_V1})
        self.assertEqual(status, 422)
        self.assertTrue(data["errors"])
        self.assertEqual(set(self._jobs_dir.iterdir()), before)


class TestArtifactsEndpoint(_ScratchServer):
    def test_artifacts_lists_job_files(self) -> None:
        job_dir = self._jobs_dir / "job-test-artifacts"
        job_dir.mkdir()
        (job_dir / "job.json").write_text(
            json.dumps({"job_id": "job-test-artifacts", "status": "done"}),
            encoding="utf-8")
        (job_dir / "script.txt").write_text("script", encoding="utf-8")
        (job_dir / "QA_REPORT.md").write_text("# QA", encoding="utf-8")
        status, data = self._request(
            "GET", "/api/production/jobs/job-test-artifacts/artifacts")
        self.assertEqual(status, 200)
        names = [Path(p).name for p in data["artifacts"]]
        self.assertIn("script.txt", names)
        self.assertIn("QA_REPORT.md", names)
        self.assertIn("job.json", names)


@unittest.skipUnless(
    _NEW_DIALECT_RECOGNIZED,
    "parser extension for the FIRST_PERSON_ROLEPLAY dialect has not "
    "landed yet (studio_script_v1.py is owned by the parser agent); "
    "this test activates once detect_format() recognises the new file")
class TestNewDialectEndpoint(_ScratchServer):
    def test_new_script_validates_clean(self) -> None:
        text = _new_script_text()
        status, data = self._post("/api/production/validate", {"script": text})
        self.assertEqual(status, 200, data.get("errors"))
        self.assertTrue(data["valid"])
        summary = data["summary"]
        self.assertEqual(summary["scenes"], 6)
        self.assertEqual(summary["shots"], 17)
        self.assertEqual(summary["spoken_lines"], 9)
        self.assertEqual(summary["external_narrator_lines"], 0)
        check = data["review"]["narrator_check"]
        self.assertEqual(check["storytelling_mode"], "FIRST_PERSON_ROLEPLAY")
        self.assertEqual(check["primary_character"], "CHAR_HITLER")
        self.assertEqual(check["external_narrator"], "NONE")
        self.assertEqual(check["external_narrator_lines"], 0)
        review = data["review"]
        self.assertTrue((review["end_card"] or {}).get("text"))
        self.assertTrue(review["qa"])
        self.assertTrue(review["output"])
        self.assertIn("HITLER_EP01_MUNICH_1914",
                      json.dumps(review["output"], ensure_ascii=False))
        self.assertEqual(len(review["props"]), 4)

    def test_first_person_narrator_line_reports_v1e025(self) -> None:
        # Assumption (documented): in the new dialect a spoken line
        # whose SPEAKER is a narrator in a FIRST_PERSON_ROLEPLAY doc
        # is the V1E025 trigger. The mutation below changes only the
        # first speaker label of the real authoritative script, in
        # memory only — the file itself is never edited.
        text = _new_script_text()
        self.assertIn("SPEAKER: CHAR_HITLER", text)
        mutated = text.replace("SPEAKER: CHAR_HITLER",
                               "SPEAKER: NARRATOR", 1)
        self.assertIn("SPEAKER: NARRATOR", mutated)
        self.assertNotEqual(mutated, text)
        status, data = self._post(
            "/api/production/validate", {"script": mutated})
        self.assertEqual(status, 422)
        codes = [e["code"] for e in data["errors"]]
        self.assertIn("V1E025", codes)
        err = [e for e in data["errors"] if e["code"] == "V1E025"][0]
        self.assertIsInstance(err["line"], int)
        self.assertGreater(err["line"], 0)
        self.assertTrue(err["message"])


class TestGenericReviewWalk(unittest.TestCase):
    """The review builder surfaces whatever the parser produces,
    without knowing dialect field names. Proved with a synthetic
    to_dict() shape modelled on the new dialect's blocks — this
    test does not depend on the parser extension landing."""

    class _FakeDoc:
        def to_dict(self) -> dict:
            return {
                "format": "studio_script_v1",
                "snapshot_hash": "abc",
                "is_valid": True,
                "meta": {
                    "project_id": "HITLER_EP01_MUNICH_1914",
                    "storytelling_mode": "FIRST_PERSON_ROLEPLAY",
                    "primary_character": "CHAR_HITLER",
                    "external_narrator": "NONE",
                    "future_meta_field": "must still display",
                },
                "characters": [{
                    "name": "CHAR_HITLER", "role": "lead",
                    "appearance": "moustache", "traits": ["t"],
                    "costume": "coat", "voice": "AUTO",
                    "future_char_field": "kept",
                }],
                "locations": [],
                "props": [{"name": "PROP_WALLET", "description": "wallet"}],
                "scenes": [{
                    "number": 1, "title": "T", "location_text": "L",
                    "time_of_day": "day", "mood": "m",
                    "actions": ["Hitler đi bộ."],
                    "shots": [{"id": "SH01", "type": "wide",
                               "future_shot_field": "kept"}],
                    "spoken_lines": [
                        {"line_id": "L1", "speaker": "CHAR_HITLER",
                         "kind": "narration", "text": "Tôi đi."},
                        {"line_id": "L2", "speaker": "Narrator",
                         "kind": "narration", "text": "Outside voice."},
                    ],
                    "audio_cues": [{"cue_type": "SFX", "name": "steps"}],
                    "vfx_cues": [],
                    "future_scene_field": "kept",
                }],
                "global_audio": {"bgm_gain_db": -18.0},
                "constraints": ["no narrator"],
                "qa": {"min_score": 8.0, "expected_scenes": 6,
                       "expected_external_narrator_lines": 0},
                "output": {"format": "MP4",
                           "drive_project_folder": "HITLER_EP01_MUNICH_1914",
                           "export_draft": True},
                "end_card": {"text": "Disclaimer.", "duration": 3.0,
                             "secondary_text": "Ep 1"},
                "unsupported_fields": [],
                "validation_errors": [],
                "warnings": [],
                "future_top_level_block": {"anything": "goes here"},
            }

    def test_new_dialect_fields_surfaced_generically(self) -> None:
        review = _build_v1_review(self._FakeDoc())
        check = review["narrator_check"]
        self.assertEqual(check["storytelling_mode"], "FIRST_PERSON_ROLEPLAY")
        self.assertEqual(check["primary_character"], "CHAR_HITLER")
        self.assertEqual(check["external_narrator"], "NONE")
        self.assertEqual(check["external_narrator_lines"], 1)
        self.assertEqual(check["spoken_lines"], 2)
        # Unknown fields at every level survive the walk verbatim.
        self.assertEqual(review["meta"]["future_meta_field"],
                         "must still display")
        self.assertEqual(review["characters"][0]["future_char_field"], "kept")
        self.assertEqual(review["scenes"][0]["future_scene_field"], "kept")
        self.assertEqual(
            review["scenes"][0]["shots"][0]["future_shot_field"], "kept")
        self.assertEqual(review["future_top_level_block"],
                         {"anything": "goes here"})
        # End card / QA / OUTPUT blocks pass through whole.
        self.assertEqual(review["end_card"]["secondary_text"], "Ep 1")
        self.assertEqual(review["qa"]["expected_scenes"], 6)
        self.assertEqual(review["output"]["drive_project_folder"],
                         "HITLER_EP01_MUNICH_1914")
        # Derived fields are added, not substituted for parser output.
        self.assertIn("walk", review["scenes"][0]["action_cues"])
        self.assertEqual(review["scenes"][0]["lines"],
                         review["scenes"][0]["spoken_lines"])
        self.assertEqual(len(review["audio_cues"]["SFX"]), 1)


if __name__ == "__main__":
    unittest.main()
