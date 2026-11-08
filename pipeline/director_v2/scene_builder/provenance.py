"""Generation Provenance and Response Validation for Gemini Scene Builder.

Enforces:
1. Strict GenerationMode tracking:
   REAL_API, CACHE, REUSED_MASTER, PROCEDURAL_FALLBACK, MOCK, TEST_FIXTURE.
2. Cryptographic and structural validation of image bytes (SHA-256, format, dimensions, size).
3. Zero secret leakage.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from PIL import Image


class GenerationMode(str, Enum):
    REAL_API = "REAL_API"
    CACHE = "CACHE"
    REUSED_MASTER = "REUSED_MASTER"
    PROCEDURAL_FALLBACK = "PROCEDURAL_FALLBACK"
    MOCK = "MOCK"
    TEST_FIXTURE = "TEST_FIXTURE"
    PROCEDURAL = "PROCEDURAL"
    LOCAL_ASSET = "LOCAL_ASSET"
    FREE_INFERENCE = "FREE_INFERENCE"
    MANUAL_ASSET = "MANUAL_ASSET"


@dataclass
class GenerationProvenance:
    provider: str
    model_id: str
    generation_mode: GenerationMode
    api_request_id: Optional[str]
    generated_at: str
    prompt_hash: str
    image_sha256: Optional[str]
    image_width: int
    image_height: int
    image_format: str
    file_size_bytes: int
    fallback_used: bool
    fallback_reason: Optional[str]
    cache_hit: bool
    source_asset_id: Optional[str]
    error_details: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["generation_mode"] = self.generation_mode.value
        return d

    @classmethod
    def create(
        cls,
        provider: str,
        model_id: str,
        generation_mode: GenerationMode,
        prompt: str,
        output_path: Path,
        fallback_used: bool = False,
        fallback_reason: Optional[str] = None,
        cache_hit: bool = False,
        source_asset_id: Optional[str] = None,
        error_details: Optional[dict[str, Any]] = None,
    ) -> GenerationProvenance:
        import datetime
        p_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        file_bytes = output_path.read_bytes() if output_path.exists() else b""
        img_sha = hashlib.sha256(file_bytes).hexdigest() if file_bytes else None

        img_w, img_h, img_fmt = 1920, 1080, "PNG"
        if file_bytes:
            try:
                with Image.open(io.BytesIO(file_bytes)) as im:
                    img_w, img_h = im.size
                    img_fmt = im.format or "PNG"
            except Exception:
                pass

        return cls(
            provider=provider,
            model_id=model_id,
            generation_mode=generation_mode,
            api_request_id=None,
            generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            prompt_hash=p_hash,
            image_sha256=img_sha,
            image_width=img_w,
            image_height=img_h,
            image_format=img_fmt,
            file_size_bytes=len(file_bytes),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            cache_hit=cache_hit,
            source_asset_id=source_asset_id,
            error_details=error_details,
        )


class ImageResponseValidator:
    """Validates real image bytes returned from generative APIs."""

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def validate_image_bytes(image_bytes: bytes, min_bytes: int = 1024) -> tuple[bool, str, dict[str, Any]]:
        """Validates that bytes represent a valid, non-corrupt image."""
        if not image_bytes:
            return False, "EMPTY_BYTE_STREAM: Received 0 bytes from provider", {}

        if len(image_bytes) < min_bytes:
            return False, f"INSUFFICIENT_SIZE: Byte length ({len(image_bytes)}) is below minimum threshold ({min_bytes})", {}

        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                img.verify()
            # Reopen to check properties (verify closes or invalidates some attributes)
            with Image.open(io.BytesIO(image_bytes)) as img:
                fmt = img.format or "UNKNOWN"
                w, h = img.size
                mode = img.mode

            if fmt not in ("PNG", "JPEG", "WEBP"):
                return False, f"INVALID_FORMAT: Expected PNG, JPEG or WEBP but found {fmt}", {}

            metadata = {
                "format": fmt,
                "width": w,
                "height": h,
                "mode": mode,
                "size_bytes": len(image_bytes),
                "sha256": hashlib.sha256(image_bytes).hexdigest(),
            }
            return True, "VALID_IMAGE", metadata
        except Exception as exc:
            return False, f"CORRUPT_IMAGE_STREAM: PIL failed to decode image bytes: {exc}", {}
