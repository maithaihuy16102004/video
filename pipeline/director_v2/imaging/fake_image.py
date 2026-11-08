"""Fake image provider for offline unit and integration tests.

Generates a valid 1920x1080 solid PNG without making external network calls.
"""
from __future__ import annotations

import io
from pathlib import Path
from PIL import Image

from .provider import ImageProvider, ImageRequest, ImageResult


class FakeImageProvider(ImageProvider):
    def __init__(self, color: tuple[int, int, int] = (45, 52, 64)):
        self.color = color
        self.call_count = 0

    def generate_image(self, request: ImageRequest) -> ImageResult:
        self.call_count += 1
        img = Image.new("RGB", (320, 180), color=self.color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        out_path = request.output_path
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)

        return ImageResult(
            ok=True,
            path=out_path,
            bytes_data=data,
            model_used=request.model,
            cost_usd=0.0,
        )
