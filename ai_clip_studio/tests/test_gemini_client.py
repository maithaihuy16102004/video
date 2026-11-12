"""Tests for ai_clip_studio.gemini_client (provider seam).

All tests use a fake helper script or mocked HTTP -- no live calls in
the test suite. The one live verification call is recorded separately
in the Stage 3 report, never here.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio.gemini_client import (
    GeminiClient,
    GeminiError,
    NoGeminiAvailable,
    RateLimitedError,
    _parse_response,
)

CANNED_TEXT = '{"ok": true}'
CANNED_PAYLOAD = {
    "candidates": [{
        "content": {"parts": [{"text": CANNED_TEXT}]},
        "finishReason": "STOP",
    }],
    "usageMetadata": {
        "promptTokenCount": 12,
        "candidatesTokenCount": 5,
        "totalTokenCount": 17,
    },
}

FAKE_HELPER = """#!/usr/bin/env python3
import json, sys
print(json.dumps(%r))
""" % (CANNED_PAYLOAD,)


def _write_helper(tmpdir: Path, source: str) -> Path:
    path = tmpdir / "fake_gemini.py"
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


class TestParseResponse(unittest.TestCase):
    def test_stop_returns_text_and_usage(self):
        text, usage = _parse_response(CANNED_PAYLOAD, "m")
        self.assertEqual(text, CANNED_TEXT)
        self.assertEqual(usage, {"prompt_tokens": 12,
                                 "candidates_tokens": 5,
                                 "total_tokens": 17})

    def test_non_stop_finish_reason_rejected(self):
        payload = {"candidates": [{
            "content": {"parts": [{"text": "partial"}]},
            "finishReason": "MAX_TOKENS"}]}
        with self.assertRaises(GeminiError):
            _parse_response(payload, "m")

    def test_no_candidates_rejected(self):
        with self.assertRaises(GeminiError):
            _parse_response({"candidates": []}, "m")


class TestHelperTransport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__import__("tempfile").mkdtemp())

    def test_fake_helper_success(self):
        helper = _write_helper(self.tmp, FAKE_HELPER)
        client = GeminiClient(helper_path=str(helper))
        text, usage, model = client.generate_json(
            "hello", model="gemini-test", max_tokens=10)
        self.assertEqual(text, CANNED_TEXT)
        self.assertEqual(usage["total_tokens"], 17)
        self.assertEqual(model, "gemini-test")

    def test_helper_argv_carries_prompt_model_and_json_flag(self):
        recorder = self.tmp / "argv.json"
        source = (
            "import json, sys\n"
            f"open({str(recorder)!r}, 'w').write(json.dumps(sys.argv))\n"
            "print(json.dumps(%r))\n" % (CANNED_PAYLOAD,)
        )
        helper = _write_helper(self.tmp, source)
        client = GeminiClient(helper_path=str(helper))
        client.generate_json("PROMPT_TEXT", model="m1", max_tokens=99)
        argv = json.loads(recorder.read_text(encoding="utf-8"))
        self.assertIn("generate", argv)
        self.assertIn("m1", argv)
        self.assertIn("--json", argv)
        self.assertIn("PROMPT_TEXT", argv)
        self.assertIn("99", argv)

    def test_helper_429_raises_without_retry(self):
        calls = self.tmp / "calls.txt"
        source = (
            "import sys\n"
            f"open({str(calls)!r}, 'a').write('x')\n"
            "print('HTTP 429: quota exceeded', file=sys.stderr)\n"
            "sys.exit(1)\n"
        )
        helper = _write_helper(self.tmp, source)
        client = GeminiClient(helper_path=str(helper))
        with self.assertRaises(RateLimitedError):
            client.generate_json("hi", model="m")
        self.assertEqual(calls.read_text(encoding="utf-8"), "x")

    def test_helper_timeout_retried_once_then_errors(self):
        source = "import time\ntime.sleep(30)\n"
        helper = _write_helper(self.tmp, source)
        client = GeminiClient(helper_path=str(helper), timeout=1)
        with self.assertRaises(GeminiError):
            client.generate_json("hi", model="m", timeout=1)

    def test_helper_503_retried_once(self):
        state = self.tmp / "state.txt"
        source = (
            "import json, sys\n"
            f"from pathlib import Path\n"
            f"p = Path({str(state)!r})\n"
            "n = int(p.read_text()) if p.exists() else 0\n"
            "p.write_text(str(n + 1))\n"
            "import sys as s\n"
            "if n == 0:\n"
            "    print('HTTP 503: overloaded', file=s.stderr); s.exit(1)\n"
            "print(json.dumps(%r))\n" % (CANNED_PAYLOAD,)
        )
        helper = _write_helper(self.tmp, source)
        client = GeminiClient(helper_path=str(helper))
        with mock.patch("ai_clip_studio.gemini_client.time.sleep"):
            text, _, _ = client.generate_json("hi", model="m")
        self.assertEqual(text, CANNED_TEXT)
        self.assertEqual(state.read_text(encoding="utf-8"), "2")

    def test_explicit_missing_helper_is_an_error(self):
        client = GeminiClient(
            helper_path=str(self.tmp / "does-not-exist.py"))
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(GeminiError):
                client.generate_json("hi", model="m")

    def test_no_credential_raises_no_gemini_available(self):
        with mock.patch(
                "ai_clip_studio.gemini_client.DEFAULT_HELPER_PATH",
                self.tmp / "absent.py"):
            with mock.patch.dict(os.environ, {}, clear=True):
                client = GeminiClient()
                self.assertFalse(client.available())
                with self.assertRaises(NoGeminiAvailable):
                    client.generate_json("hi", model="m")


class TestDirectTransport(unittest.TestCase):
    def _mock_response(self, payload):
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps(payload).encode("utf-8")
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    def test_explicit_key_uses_direct_call(self):
        client = GeminiClient(api_key="KEY-FOR-TEST-ONLY")
        with mock.patch("ai_clip_studio.gemini_client.urllib.request.urlopen",
                        return_value=self._mock_response(CANNED_PAYLOAD)) as m:
            text, usage, model = client.generate_json("hi", model="m2")
        self.assertEqual(text, CANNED_TEXT)
        self.assertEqual(usage["prompt_tokens"], 12)
        request = m.call_args[0][0]
        self.assertIn("m2:generateContent", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"),
                         "KEY-FOR-TEST-ONLY")

    def test_direct_429_raises_without_retry(self):
        import urllib.error
        err = urllib.error.HTTPError(
            "http://x", 429, "Too Many Requests", {}, None)
        err.read = lambda: b"quota"
        client = GeminiClient(api_key="KEY-FOR-TEST-ONLY")
        with mock.patch("ai_clip_studio.gemini_client.urllib.request.urlopen",
                        side_effect=err) as m:
            with self.assertRaises(RateLimitedError):
                client.generate_json("hi", model="m")
        self.assertEqual(m.call_count, 1)

    def test_direct_503_retried_once(self):
        import urllib.error
        err = urllib.error.HTTPError(
            "http://x", 503, "Unavailable", {}, None)
        err.read = lambda: b"overloaded"
        client = GeminiClient(api_key="KEY-FOR-TEST-ONLY")
        with mock.patch("ai_clip_studio.gemini_client.urllib.request.urlopen",
                        side_effect=[err,
                                     self._mock_response(CANNED_PAYLOAD)]):
            with mock.patch("ai_clip_studio.gemini_client.time.sleep"):
                text, _, _ = client.generate_json("hi", model="m")
        self.assertEqual(text, CANNED_TEXT)

    def test_env_key_used_when_no_helper(self):
        with mock.patch(
                "ai_clip_studio.gemini_client.DEFAULT_HELPER_PATH",
                Path("/nonexistent/gemini.py")):
            with mock.patch.dict(os.environ,
                                 {"GEMINI_API_KEY": "ENV-KEY-TEST"}):
                client = GeminiClient()
                with mock.patch(
                        "ai_clip_studio.gemini_client.urllib.request.urlopen",
                        return_value=self._mock_response(
                            CANNED_PAYLOAD)) as m:
                    client.generate_json("hi", model="m")
                request = m.call_args[0][0]
                self.assertEqual(request.get_header("X-goog-api-key"),
                                 "ENV-KEY-TEST")

    def test_explicit_key_wins_over_helper(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        helper = _write_helper(tmp, FAKE_HELPER)
        client = GeminiClient(api_key="KEY-FOR-TEST-ONLY",
                              helper_path=str(helper))
        with mock.patch("ai_clip_studio.gemini_client.urllib.request.urlopen",
                        return_value=self._mock_response(CANNED_PAYLOAD)):
            with mock.patch(
                    "ai_clip_studio.gemini_client.subprocess.run",
                    side_effect=AssertionError("helper must not run")):
                text, _, _ = client.generate_json("hi", model="m")
        self.assertEqual(text, CANNED_TEXT)


if __name__ == "__main__":
    unittest.main()
