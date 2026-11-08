"""Builds structured visual prompts according to the Master Prompt Contract.

Contract:
  GLOBAL STYLE
  + ASSET REQUIREMENT DESCRIPTION
  + PERSPECTIVE & CAMERA CONSTRAINTS
  + HISTORICAL CONSTRAINTS
  + NEGATIVE CONSTRAINTS
"""
from __future__ import annotations

from typing import Any

from ..schemas.assets import AssetRequirement
from ..schemas.bible import ProjectBible, StylePreset


def build_image_prompt(
    req: AssetRequirement,
    style: StylePreset,
    bible: ProjectBible,
) -> tuple[str, str]:
    """Builds (positive_prompt, negative_prompt) for an AssetRequirement."""
    parts: list[str] = []

    # 1. Global style
    parts.append(f"Visual Style: {style.name}. {style.description}")
    parts.append(f"Art direction: {style.environment_style}")

    # 2. Requirement core description
    parts.append(f"Scene asset: {req.description}")

    # 3. Geometry & lighting
    if req.perspective_family:
        parts.append(f"Perspective: {req.perspective_family}, camera height: {req.camera_height_bucket}.")
    if req.lighting_key:
        parts.append(f"Lighting direction: {req.lighting_key}.")

    # 4. Matte / layer isolation
    if req.matte == "chroma_green":
        parts.append("Foreground element isolated against pure chroma key solid background. No character in frame.")

    # 5. Historical constraints
    if req.historical_constraints:
        parts.append("Historical fidelity: " + "; ".join(req.historical_constraints[:3]))

    positive = "\n".join(parts)
    negative = ", ".join(style.negative)
    return positive, negative
