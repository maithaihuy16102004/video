"""Gemini structured text provider using official responseSchema and x-goog-api-key header."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Type, TypeVar
from pydantic import BaseModel

from ..secret_store import get_gemini_api_key, redact

T = TypeVar("T", bound=BaseModel)


class GeminiTextProvider:
    def __init__(self, model: str = "gemini-3.5-flash-lite", api_key: str | None = None):
        self.model = model
        self._key = api_key

    def _get_key(self) -> str:
        return self._key or get_gemini_api_key(required=True)

    def generate_structured(
        self,
        schema: Type[T],
        system_instruction: str,
        prompt: str,
        temperature: float = 0.2,
    ) -> T:
        key = self._get_key()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

        # Prepare payload with JSON schema enforcement
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        # Try to supply responseSchema if supported
        try:
            json_schema = schema.model_json_schema()
            # Clean unsupported OpenAPI keywords for Gemini API
            for k in ("title", "$defs", "definitions"):
                json_schema.pop(k, None)
            payload["generationConfig"]["responseSchema"] = json_schema
        except Exception:
            pass

        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw_resp = json.loads(resp.read().decode("utf-8"))
            candidate = raw_resp["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Strip Markdown code blocks if returned
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.I).strip()
            parsed_dict = json.loads(candidate)
            return schema.model_validate(parsed_dict)
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="replace")[-500:]
            clean_err = redact(f"Gemini API HTTP {err.code}: {err_body}")
            raise RuntimeError(clean_err) from None
        except Exception as exc:
            clean_exc = redact(f"Gemini generation error: {exc}")
            raise RuntimeError(clean_exc) from None
