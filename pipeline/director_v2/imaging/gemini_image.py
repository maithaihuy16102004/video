"""Gemini Image Provider using official REST endpoints and x-goog-api-key."""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..secret_store import get_gemini_api_key, redact
from .provider import ImageProvider, ImageRequest, ImageResult


class GeminiImageProvider(ImageProvider):
    def __init__(self, api_key: str | None = None):
        self._key = api_key
        self.call_count = 0

    def _get_key(self) -> str:
        return self._key or get_gemini_api_key(required=True)

    def generate_image(self, request: ImageRequest) -> ImageResult:
        key = self._get_key()
        self.call_count += 1
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{request.model}:generateContent"

        parts: list[dict[str, Any]] = [{"text": request.prompt}]

        # Add image references inline if provided
        for ref in request.reference_images:
            if ref.exists():
                b64 = base64.b64encode(ref.read_bytes()).decode("ascii")
                parts.append({"inlineData": {"mimeType": "image/png", "data": b64}})

        payload: dict[str, Any] = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
            },
        }

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
            with urllib.request.urlopen(req, timeout=120) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))

            candidates = res_json.get("candidates", [])
            if not candidates:
                return ImageResult(ok=False, model_used=request.model, error="No candidate returned from Gemini")

            # Extract image bytes
            candidate_parts = candidates[0].get("content", {}).get("parts", [])
            img_bytes = None
            for p in candidate_parts:
                inline = p.get("inlineData")
                if inline and inline.get("data"):
                    img_bytes = base64.b64decode(inline["data"])
                    break

            if not img_bytes:
                return ImageResult(ok=False, model_used=request.model, error="No image bytes found in response parts")

            out_path = request.output_path
            if out_path:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(img_bytes)

            return ImageResult(
                ok=True,
                path=out_path,
                bytes_data=img_bytes,
                model_used=request.model,
            )
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")[-400:]
            return ImageResult(ok=False, model_used=request.model, error=redact(f"HTTP {err.code}: {body}"))
        except Exception as exc:
            return ImageResult(ok=False, model_used=request.model, error=redact(str(exc)))
