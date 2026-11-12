"""Gemini API client for the planners (provider seam).

The credential lives ONLY in the registered ``custom.gemini``
connection. This module never reads, logs, stores, or prints any key
material. Credential resolution order for generate_json():

1. An explicitly passed ``api_key`` (constructor/injectable: tests on
   other machines, callers that already hold a key). Used only for the
   direct HTTPS call, never written anywhere.
2. The connector helper subprocess (this VM's path): the helper
   resolves the credential itself via an hsurr: surrogate and calls
   only generativelanguage.googleapis.com. Helper path defaults to
   ``~/workspace/custom-connectors/custom.gemini/bin/gemini.py`` and
   is overridable via the constructor (unit tests inject a fake
   helper returning canned JSON -- no live calls in the test suite).
3. The ``GEMINI_API_KEY`` environment variable, if set (the Windows
   path). Reading a user-set env var is allowed; this module never
   writes one.
4. Otherwise ``NoGeminiAvailable`` is raised; the planner catches it
   and falls back with a label.

Retry policy: one retry on timeout/503. HTTP 429 raises
RateLimitedError immediately with NO retry -- the caller must stop
and surface the error (the planner falls back, labelled).

Responses are checked before use: finishReason must be "STOP" and
usageMetadata token counts are returned with the text. Prompts and
raw responses are never logged.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODELS = ("gemini-3.5-flash-lite", "gemini-flash-lite-latest")
DEFAULT_HELPER_PATH = (
    Path.home() / "workspace" / "custom-connectors" / "custom.gemini"
    / "bin" / "gemini.py"
)
REQUEST_TIMEOUT = 60


class GeminiError(RuntimeError):
    """Any Gemini failure that is not a missing credential."""


class NoGeminiAvailable(GeminiError):
    """No credential path resolved (no key, no helper, no env var)."""


class RateLimitedError(GeminiError):
    """HTTP 429. Callers must NOT retry; fall back and surface it."""


def _parse_response(payload, model: str) -> tuple[str, dict]:
    """Extract (text, usage) from a generateContent payload.

    finishReason must be "STOP" before the text is trusted.
    """
    if not isinstance(payload, dict):
        raise GeminiError(f"Gemini {model} returned a non-object payload")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeminiError(
            f"Gemini {model} returned no candidates: "
            f"{str(payload)[:200]}")
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    finish_reason = first.get("finishReason")
    if finish_reason != "STOP":
        raise GeminiError(
            f"Gemini {model} finishReason={finish_reason!r} "
            "(text is not trustworthy unless STOP)")
    try:
        text = first["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiError(
            f"Gemini {model} returned no text: {str(payload)[:200]}") from exc
    usage_meta = payload.get("usageMetadata") or {}
    usage = {
        "prompt_tokens": int(usage_meta.get("promptTokenCount") or 0),
        "candidates_tokens": int(usage_meta.get("candidatesTokenCount") or 0),
        "total_tokens": int(usage_meta.get("totalTokenCount") or 0),
    }
    return text, usage


class GeminiClient:
    """One Gemini caller with the credential resolution above."""

    def __init__(self, *, api_key: str | None = None,
                 helper_path=None, timeout: int = REQUEST_TIMEOUT):
        self._api_key = api_key or None
        self._helper_explicit = helper_path is not None
        self._helper_path = (Path(helper_path) if helper_path is not None
                             else DEFAULT_HELPER_PATH)
        self.timeout = timeout

    # -- availability -------------------------------------------------

    def helper_available(self) -> bool:
        try:
            return self._helper_path.is_file()
        except OSError:
            return False

    def available(self) -> bool:
        """True when some credential path exists (no network call)."""
        return bool(self._api_key) or self.helper_available() \
            or bool(os.environ.get("GEMINI_API_KEY"))

    # -- main entry ---------------------------------------------------

    def generate_json(self, prompt: str, *, model: str = DEFAULT_MODEL,
                      max_tokens: int = 4096,
                      timeout: int | None = None) -> tuple[str, dict, str]:
        """Generate JSON text. Returns (text, usage, model_used).

        ``usage`` is {prompt_tokens, candidates_tokens, total_tokens}.
        Raises NoGeminiAvailable, RateLimitedError, or GeminiError.
        """
        effective_timeout = self.timeout if timeout is None else timeout
        if self._api_key:
            return self._generate_direct(
                prompt, model, self._api_key, max_tokens, effective_timeout)
        if self.helper_available():
            return self._generate_via_helper(
                prompt, model, max_tokens, effective_timeout)
        if self._helper_explicit:
            raise GeminiError(
                f"Gemini helper not found at {self._helper_path}")
        env_key = os.environ.get("GEMINI_API_KEY", "")
        if env_key:
            return self._generate_direct(
                prompt, model, env_key, max_tokens, effective_timeout)
        raise NoGeminiAvailable(
            "no Gemini credential: no explicit key, no connector "
            f"helper at {self._helper_path}, GEMINI_API_KEY not set")

    # -- transports ---------------------------------------------------

    def _generate_direct(self, prompt: str, model: str, api_key: str,
                         max_tokens: int, timeout: int):
        url = f"{GEMINI_API_URL}/{model}:generateContent"
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }).encode("utf-8")
        last_error = ""
        for attempt in (1, 2):
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json",
                         "x-goog-api-key": api_key},
                method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                if exc.code == 429:
                    raise RateLimitedError(
                        f"Gemini API HTTP 429 (model {model}): {detail}"
                    ) from exc
                last_error = f"Gemini API HTTP {exc.code}: {detail}"
                if exc.code == 503 and attempt == 1:
                    time.sleep(5)
                    continue
                raise GeminiError(last_error) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = f"Gemini API unreachable: {exc}"
                if attempt == 1:
                    time.sleep(2)
                    continue
                raise GeminiError(last_error) from exc
            text, usage = _parse_response(payload, model)
            return text, usage, model
        raise GeminiError(last_error or f"Gemini {model} call failed")

    def _generate_via_helper(self, prompt: str, model: str,
                             max_tokens: int, timeout: int):
        argv = [
            sys.executable, str(self._helper_path), "generate",
            "--model", model, "--prompt", prompt, "--json",
            "--max-tokens", str(max_tokens),
        ]
        last_error = ""
        for attempt in (1, 2):
            try:
                proc = subprocess.run(
                    argv, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                # First call after setup can time out on the egress
                # handshake; one retry, then it works in ~1s.
                last_error = f"Gemini helper timed out: {exc}"
                if attempt == 1:
                    continue
                raise GeminiError(last_error) from exc
            if proc.returncode != 0:
                detail = (proc.stderr or "").strip()[:300]
                if "429" in detail:
                    raise RateLimitedError(
                        f"Gemini API HTTP 429 (model {model}): {detail}")
                last_error = (f"Gemini helper failed (exit "
                              f"{proc.returncode}): {detail}")
                if "503" in detail and attempt == 1:
                    time.sleep(2)
                    continue
                raise GeminiError(last_error)
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                raise GeminiError(
                    "Gemini helper returned non-JSON output: "
                    f"{proc.stdout[:200]}") from exc
            text, usage = _parse_response(payload, model)
            return text, usage, model
        raise GeminiError(last_error or f"Gemini {model} call failed")
