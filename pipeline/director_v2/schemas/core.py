"""Shared primitives: enums, normalized geometry, base model."""
from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DV2Model(BaseModel):
    """Base model: tolerant of extra keys from LLMs, strict on declared types."""

    model_config = ConfigDict(extra="ignore", use_enum_values=False, populate_by_name=True)

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def norm_enum_token(value: Any) -> Any:
    """'three-quarter back' -> 'THREE_QUARTER_BACK' so LLM output maps onto enums."""
    if isinstance(value, str):
        return re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
    return value


class AspectRatio(str, Enum):
    LANDSCAPE_16_9 = "16:9"
    PORTRAIT_9_16 = "9:16"


class QualityTier(str, Enum):
    DRAFT_FAST = "DRAFT_FAST"
    DRAFT_VISUAL = "DRAFT_VISUAL"
    DRAFT = "DRAFT"  # Legacy alias for DRAFT_FAST
    STANDARD = "STANDARD"
    MASTER = "MASTER"


class ImageTier(str, Enum):
    FAST = "FAST"
    MAIN = "MAIN"
    HERO = "HERO"


class LayerRole(str, Enum):
    FAR_BG = "FAR_BG"
    BG = "BG"
    MG = "MG"
    CHARACTER = "CHARACTER"
    FG = "FG"
    FX = "FX"


LAYER_ORDER: list[LayerRole] = [
    LayerRole.FAR_BG, LayerRole.BG, LayerRole.MG, LayerRole.CHARACTER, LayerRole.FG, LayerRole.FX,
]

# Parallax factors relative to camera motion (FG moves 100%, FAR_BG 10%).
DEFAULT_PARALLAX: dict[LayerRole, float] = {
    LayerRole.FAR_BG: 0.10,
    LayerRole.BG: 0.25,
    LayerRole.MG: 0.50,
    LayerRole.CHARACTER: 0.70,
    LayerRole.FG: 1.00,
    LayerRole.FX: 1.10,
}


class NormPoint(DV2Model):
    """Point in normalized frame space. 0..1 is on-screen; values outside allow off-frame anchors."""

    x: float = Field(ge=-1.0, le=2.0)
    y: float = Field(ge=-1.0, le=2.0)


class NormRect(DV2Model):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)


class SafeArea(DV2Model):
    """Fractions of frame reserved at each edge (title/action safe)."""

    top: float = 0.05
    bottom: float = 0.05
    left: float = 0.05
    right: float = 0.05
