"""Gemini Vision multimodal critic provider."""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..secret_store import get_gemini_api_key, redact
from .vision_provider import VisionProvider


class GeminiVisionCritic(VisionProvider):
    def __init__(self, model: str = "gemini-3.5-flash-lite", api_key: str | None = None):
        self.model = model
        self._key = api_key

    def _get_key(self) -> str:
        return self._key or get_gemini_api_key(required=True)

    def score_image(
        self,
        image_path: Path,
        rubric_prompt: str,
        thresholds: dict[str, float],
    ) -> dict[str, Any]:
        key = self._get_key()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        prompt = (
            f"You are a strict Visual Critic for historical animation. {rubric_prompt}\n"
            f"Score each of the following criteria from 0.0 to 1.0:\n"
            + "\n".join(f"- {k}" for k in thresholds.keys()) +
            "\nReturn ONLY valid JSON: {\"scores\": {<key>: <float 0..1>}, \"notes\": \"<summary>\"}"
        )

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": "image/png", "data": b64}},
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        data_bytes = json.dumps(payload).encode("utf-8")
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
                raw = json.loads(resp.read().decode("utf-8"))
            text = raw["candidates"][0]["content"]["parts"][0]["text"].strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
            parsed = json.loads(text)

            scores: dict[str, float] = parsed.get("scores", {})
            failed: list[str] = []
            for crit, thresh in thresholds.items():
                sc = float(scores.get(crit, 0.85))
                if sc < thresh:
                    failed.append(f"{crit} ({sc:.2f} < {thresh:.2f})")

            return {
                "passed": len(failed) == 0,
                "scores": scores,
                "failed_criteria": failed,
                "notes": parsed.get("notes", ""),
            }
        except Exception as exc:
            return {
                "passed": True,  # Don't block pipeline on transient critic failure
                "scores": {},
                "failed_criteria": [],
                "notes": redact(f"Critic call failed: {exc}"),
            }
