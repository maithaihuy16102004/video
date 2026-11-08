"""Gemini implementation of ReasoningProvider (text-only, JSON mode, free-quota usage).

* API key from GEMINI_API_KEY via env_secrets (never logged / serialised).
* No image endpoints are ever called from here.
* Errors are redacted before surfacing.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .provider import ReasoningUnavailable

_PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
from env_secrets import get_gemini_api_key, redact  # noqa: E402


class GeminiReasoningProvider:
    name = "gemini"

    def __init__(self, model: str, timeout: int = 120, max_transport_retries: int = 2):
        self.model = model
        self.timeout = timeout
        self.max_transport_retries = max_transport_retries

    def complete_json(self, stage: str, system: str, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        key = get_gemini_api_key(required=False)
        if not key:
            raise ReasoningUnavailable("GEMINI_API_KEY not configured")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_err = ""
        for attempt in range(self.max_transport_retries + 1):
            req = urllib.request.Request(url, data=body, method="POST",
                                         headers={"Content-Type": "application/json", "x-goog-api-key": key})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                text = raw["candidates"][0]["content"]["parts"][0]["text"].strip()
                text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
                return json.loads(text)
            except urllib.error.HTTPError as err:
                detail = err.read().decode("utf-8", errors="replace")[-300:]
                last_err = redact(f"HTTP {err.code}: {detail}")
                if err.code in (401, 403):
                    raise ReasoningUnavailable(last_err) from None
                if err.code == 429:          # free quota exhausted: do not hammer / bypass
                    raise ReasoningUnavailable("QUOTA_EXHAUSTED " + last_err) from None
            except json.JSONDecodeError as err:
                last_err = f"INVALID_JSON: {err}"
            except Exception as err:  # network
                last_err = redact(f"TRANSPORT: {err}")
            time.sleep(1.5 * (attempt + 1))
        raise ReasoningUnavailable(last_err)
