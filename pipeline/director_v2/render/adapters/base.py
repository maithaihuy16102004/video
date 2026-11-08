"""Protocol for renderer adapters."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ...schemas.manifest import RenderManifest


class RendererAdapter(Protocol):
    def prepare_render_spec(self, manifest: RenderManifest, output_dir: Path) -> Path:
        """Translates RenderManifest into renderer-specific specification file."""
        ...
