"""Project-level pipeline configuration (data, not code).

Loaded from a JSON file per project; every field has a generic default.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .vocab import RenderMode, StorytellingMode


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_name: str = "untitled_project"
    reasoning_provider: str = "gemini"          # gemini | offline
    reasoning_model: str = "gemini-3.5-flash-lite"
    allow_offline_fallback: bool = True          # use deterministic offline reasoning if provider unavailable
    reasoning_max_repairs: int = 1               # structured re-ask attempts after validation failure
    render_mode: str = RenderMode.DRAFT_VISUAL.value
    character_style: str = "ILLUSTRATED_STICKMAN"
    aspect_ratio: str = "16:9"
    width: int = 1920
    height: int = 1080
    language: Optional[str] = None               # None = auto
    storytelling_mode: str = StorytellingMode.FIRST_PERSON_ROLEPLAY.value
    storyteller_character_id: Optional[str] = None   # for FIRST_PERSON_CHARACTER
    historical_validation: bool = True
    comedy_level: float = 0.5                    # 0..1
    target_duration_sec: Optional[float] = None
    zero_cost_only: bool = True
    seed: int = 1234
    vitality: str = "BALANCED"
    similarity_window: int = 4
    stage_view_window: int = 5
    stage_view_max_in_window: int = 1
    max_shots_per_beat: int = 2
    retention_max_static_sec: float = 8.0

    @field_validator("render_mode")
    @classmethod
    def _rm(cls, v: str) -> str:
        return RenderMode.coerce(v, RenderMode.DRAFT_VISUAL).value

    @field_validator("storytelling_mode")
    @classmethod
    def _sm(cls, v: str) -> str:
        return StorytellingMode.coerce(v, StorytellingMode.FIRST_PERSON_ROLEPLAY).value

    @field_validator("zero_cost_only")
    @classmethod
    def _zc(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Current project policy requires zero_cost_only=True")
        return v

    @classmethod
    def load(cls, path: Path | str | None, **overrides) -> "PipelineConfig":
        data: dict = {}
        if path and Path(path).exists():
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        data.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**data)

    def cache_fingerprint(self) -> dict:
        """Fields that influence reasoning output (used in reasoning cache keys)."""
        return {
            "provider": self.reasoning_provider, "model": self.reasoning_model,
            "language": self.language, "storytelling_mode": self.storytelling_mode,
            "storyteller": self.storyteller_character_id, "comedy_level": self.comedy_level,
            "historical_validation": self.historical_validation,
        }
