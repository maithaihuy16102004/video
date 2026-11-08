"""Generic Image Provider abstraction.

No Gemini-specific logic is allowed in this interface so other backends
(e.g., fal.ai, ComfyUI, local diffusion) can be added seamlessly in the future.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ImageRequest:
    requirement_id: str
    prompt: str
    model: str
    aspect_ratio: str = "16:9"
    image_size: str = "1K"
    reference_images: list[Path] = field(default_factory=list)
    negative_prompt: str = ""
    seed: int | None = None
    output_path: Path | None = None


@dataclass
class ImageResult:
    ok: bool
    path: Path | None = None
    bytes_data: bytes | None = None
    model_used: str = ""
    cost_usd: float | None = None
    error: str | None = None


class ImageProvider(Protocol):
    """Protocol implemented by image generation backends."""

    def generate_image(self, request: ImageRequest) -> ImageResult:
        ...
