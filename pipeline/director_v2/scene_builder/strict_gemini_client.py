"""Strict Gemini Image API Client implementing Phase 3, 4, 5, 26.

Rules:
- FAIL LOUDLY: ALLOW_PROCEDURAL_FALLBACK = False. Never silently pretend a fallback is Gemini.
- Zero secret exposure: Checks GEMINI_API_KEY as AVAILABLE / MISSING only.
- Strict payload validation (SHA-256, PIL format decode, dimensions, min bytes).
- Model routing from environment/config.
"""
from __future__ import annotations

import base64
import datetime
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

from ..secret_store import get_gemini_api_key, redact
from .provenance import GenerationMode, GenerationProvenance, ImageResponseValidator


@dataclass
class StrictGenerationResult:
    ok: bool
    status: str                         # "SUCCESS" or "GEMINI_GENERATION_FAILED"
    generation_mode: GenerationMode
    provenance: GenerationProvenance
    image_path: Optional[Path]
    error_summary: Optional[str] = None


class StrictGeminiClient:
    """Executes real Gemini Image API calls with strict validation and loud failure."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        allow_procedural_fallback: bool = False,
    ) -> None:
        self.allow_procedural_fallback = allow_procedural_fallback
        self._configured_model = model_id or os.getenv("MAIN_IMAGE_MODEL", "gemini-3.1-flash-image")
        self.total_api_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0

    @property
    def key_status(self) -> str:
        """Returns only AVAILABLE or MISSING. Never returns key value."""
        try:
            k = get_gemini_api_key(required=False)
            return "AVAILABLE" if k and len(k) > 10 else "MISSING"
        except Exception:
            return "MISSING"

    @property
    def active_model(self) -> str:
        return self._configured_model

    def generate_scene_image(
        self,
        scene_id: str,
        prompt: str,
        negative_prompt: str,
        prompt_hash: str,
        output_image_path: Path,
        retry_count: int = 0,
    ) -> StrictGenerationResult:
        """Calls real Gemini API. If failed and fallback disallowed, fails loudly."""
        self.total_api_calls += 1
        output_image_path.parent.mkdir(parents=True, exist_ok=True)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if self.key_status != "AVAILABLE":
            self.failed_calls += 1
            prov = GenerationProvenance(
                provider="gemini",
                model_id=self._configured_model,
                generation_mode=GenerationMode.REAL_API,
                api_request_id=None,
                generated_at=now_iso,
                prompt_hash=prompt_hash,
                image_sha256=None,
                image_width=0,
                image_height=0,
                image_format="NONE",
                file_size_bytes=0,
                fallback_used=False,
                fallback_reason="MISSING_API_KEY",
                cache_hit=False,
                source_asset_id=None,
                error_details={"category": "CONFIG_ERROR", "message": "GEMINI_API_KEY is not set or empty."},
            )
            self._render_diagnostic_failure_plate(output_image_path, prov, "GEMINI_API_KEY_MISSING")
            return StrictGenerationResult(
                ok=False,
                status="GEMINI_GENERATION_FAILED",
                generation_mode=GenerationMode.REAL_API,
                provenance=prov,
                image_path=output_image_path,
                error_summary="GEMINI_API_KEY is missing",
            )

        api_key = get_gemini_api_key(required=True)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._configured_model}:generateContent"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
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
                "x-goog-api-key": api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                raw_response = resp.read().decode("utf-8")
                api_req_id = resp.headers.get("x-request-id") or resp.headers.get("x-goog-request-id")

            res_json = json.loads(raw_response)
            candidates = res_json.get("candidates", [])
            if not candidates:
                raise ValueError("API returned response with 0 candidates")

            # Extract image bytes
            parts = candidates[0].get("content", {}).get("parts", [])
            image_bytes = None
            for p in parts:
                inline = p.get("inlineData")
                if inline and inline.get("data"):
                    image_bytes = base64.b64decode(inline["data"])
                    break

            if not image_bytes:
                raise ValueError("Candidate response contains no inlineData image payload")

            # Strict validation (PHASE 5)
            valid, msg, meta = ImageResponseValidator.validate_image_bytes(image_bytes)
            if not valid:
                raise ValueError(f"Corrupt image payload: {msg}")

            # Write genuine image bytes to disk
            output_image_path.write_bytes(image_bytes)
            self.successful_calls += 1

            prov = GenerationProvenance(
                provider="gemini",
                model_id=self._configured_model,
                generation_mode=GenerationMode.REAL_API,
                api_request_id=api_req_id,
                generated_at=now_iso,
                prompt_hash=prompt_hash,
                image_sha256=meta["sha256"],
                image_width=meta["width"],
                image_height=meta["height"],
                image_format=meta["format"],
                file_size_bytes=meta["size_bytes"],
                fallback_used=False,
                fallback_reason=None,
                cache_hit=False,
                source_asset_id=scene_id,
                error_details=None,
            )

            return StrictGenerationResult(
                ok=True,
                status="SUCCESS",
                generation_mode=GenerationMode.REAL_API,
                provenance=prov,
                image_path=output_image_path,
                error_summary=None,
            )

        except urllib.error.HTTPError as err:
            self.failed_calls += 1
            body = err.read().decode("utf-8", errors="replace")
            clean_error = redact(f"HTTP {err.code}: {body[:250]}")

            error_cat = "RESOURCE_EXHAUSTED_QUOTA_LIMIT" if err.code == 429 else f"HTTP_{err.code}"
            prov = GenerationProvenance(
                provider="gemini",
                model_id=self._configured_model,
                generation_mode=GenerationMode.REAL_API,
                api_request_id=None,
                generated_at=now_iso,
                prompt_hash=prompt_hash,
                image_sha256=None,
                image_width=1920,
                image_height=1080,
                image_format="DIAGNOSTIC_FAILURE_CARD",
                file_size_bytes=0,
                fallback_used=False,
                fallback_reason="ALLOW_PROCEDURAL_FALLBACK_IS_FALSE",
                cache_hit=False,
                source_asset_id=scene_id,
                error_details={
                    "error_category": error_cat,
                    "http_code": err.code,
                    "message": clean_error,
                    "retry_count": retry_count,
                    "fallback_state": "DISALLOWED_FAIL_LOUDLY",
                },
            )

            # Renders explicit diagnostic failure card onto output path so user sees true status
            self._render_diagnostic_failure_plate(output_image_path, prov, clean_error)

            return StrictGenerationResult(
                ok=False,
                status="GEMINI_GENERATION_FAILED",
                generation_mode=GenerationMode.REAL_API,
                provenance=prov,
                image_path=output_image_path,
                error_summary=clean_error,
            )

        except Exception as exc:
            self.failed_calls += 1
            clean_error = redact(str(exc))
            prov = GenerationProvenance(
                provider="gemini",
                model_id=self._configured_model,
                generation_mode=GenerationMode.REAL_API,
                api_request_id=None,
                generated_at=now_iso,
                prompt_hash=prompt_hash,
                image_sha256=None,
                image_width=1920,
                image_height=1080,
                image_format="DIAGNOSTIC_FAILURE_CARD",
                file_size_bytes=0,
                fallback_used=False,
                fallback_reason="ALLOW_PROCEDURAL_FALLBACK_IS_FALSE",
                cache_hit=False,
                source_asset_id=scene_id,
                error_details={
                    "error_category": "UNEXPECTED_EXCEPTION",
                    "message": clean_error,
                    "retry_count": retry_count,
                    "fallback_state": "DISALLOWED_FAIL_LOUDLY",
                },
            )
            self._render_diagnostic_failure_plate(output_image_path, prov, clean_error)
            return StrictGenerationResult(
                ok=False,
                status="GEMINI_GENERATION_FAILED",
                generation_mode=GenerationMode.REAL_API,
                provenance=prov,
                image_path=output_image_path,
                error_summary=clean_error,
            )

    def _render_diagnostic_failure_plate(
        self,
        output_path: Path,
        prov: GenerationProvenance,
        error_msg: str,
    ) -> Path:
        """Renders an unambiguous diagnostic card. DOES NOT pretend to be an artwork."""
        img = Image.new("RGB", (1920, 1080), color=(28, 12, 16))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()

        # Danger Banner
        draw.rectangle([60, 60, 1860, 160], fill=(180, 25, 35))
        draw.text((90, 85), "[CRITICAL] REAL GEMINI IMAGE GENERATION FAILED", fill=(255, 255, 255), font=font)
        draw.text((90, 115), "Policy: ALLOW_PROCEDURAL_FALLBACK = False. Procedural substitution strictly rejected.", fill=(255, 220, 220), font=font)

        # Technical Details Box
        draw.rectangle([60, 190, 1860, 980], fill=(20, 22, 28), outline=(180, 50, 60), width=3)

        lines = [
            f"Provider:              {prov.provider.upper()}",
            f"Configured Model ID:   {prov.model_id}",
            f"API Key Status:        {self.key_status} (Never printed or serialized)",
            f"Generation Mode:       {prov.generation_mode.value}",
            f"Fallback State:        DISALLOWED (No silent vector substitution)",
            f"Execution Timestamp:   {prov.generated_at}",
            "",
            "API ERROR DETAILS:",
            f"Error Category:        {prov.error_details.get('error_category', 'UNKNOWN') if prov.error_details else 'N/A'}",
            f"Raw API Error:         {error_msg}",
            "",
            "WHY THIS HAPPENED:",
            "- Google AI Studio Free Tier projects currently have limit: 0 requests/day for image generation endpoints",
            "  (gemini-2.5-flash-image, gemini-3.1-flash-image, gemini-3-pro-image).",
            "- To generate real Gemini pixels, the Google Cloud / AI Studio project must have Pay-As-You-Go billing enabled.",
            "",
            "AUTHENTICITY GUARANTEE:",
            "- The system refuses to paint fake vector geometry and label it as 'Gemini'.",
            "- The pipeline fails loudly and records provenance truthfully.",
        ]

        y = 220
        for l in lines:
            color = (255, 120, 120) if "ERROR" in l or "FAILED" in l else (220, 225, 235)
            draw.text((90, y), l, fill=color, font=font)
            y += 28

        img.save(str(output_path), "PNG")
        prov.file_size_bytes = output_path.stat().st_size
        return output_path
