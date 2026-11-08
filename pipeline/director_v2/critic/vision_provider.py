"""Protocol for multimodal vision critics."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class VisionProvider(Protocol):
    def score_image(
        self,
        image_path: Path,
        rubric_prompt: str,
        thresholds: dict[str, float],
    ) -> dict[str, Any]:
        """Returns dict containing scores [0.0..1.0], passed (bool), and failed_criteria (list[str])."""
        ...
