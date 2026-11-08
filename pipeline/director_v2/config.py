"""Project configuration and model routing. All model IDs come from env/config, never business logic."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field, model_validator

from .schemas.core import AspectRatio, DV2Model, ImageTier, QualityTier, SafeArea
from .secret_store import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
REPO_ROOT = PACKAGE_DIR.parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "output" / "director_v2"


class ModelRouting(DV2Model):
    text_model: str = "gemini-3.5-flash-lite"
    vision_model: str = "gemini-3.5-flash-lite"
    fast_image_model: str = "gemini-3.1-flash-lite-image"
    main_image_model: str = "gemini-3.1-flash-image"
    hero_image_model: str = "gemini-3-pro-image"

    def image_model(self, tier: ImageTier) -> str:
        return {
            ImageTier.FAST: self.fast_image_model,
            ImageTier.MAIN: self.main_image_model,
            ImageTier.HERO: self.hero_image_model,
        }[tier]

    @classmethod
    def from_env(cls) -> "ModelRouting":
        load_dotenv()
        base = cls()
        env = {
            "text_model": os.getenv("DV2_TEXT_MODEL"),
            "vision_model": os.getenv("DV2_VISION_MODEL"),
            "fast_image_model": os.getenv("FAST_IMAGE_MODEL"),
            "main_image_model": os.getenv("MAIN_IMAGE_MODEL"),
            "hero_image_model": os.getenv("HERO_IMAGE_MODEL"),
        }
        return base.model_copy(update={k: v.strip() for k, v in env.items() if v and v.strip()})


class ProjectConfig(DV2Model):
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE_16_9
    width: int = 1920
    height: int = 1080
    fps: int = 24
    safe_area: SafeArea = Field(default_factory=SafeArea)
    reframe_policy: str = "rule_of_thirds"   # center_subject | rule_of_thirds | manual
    quality: QualityTier = QualityTier.STANDARD
    style_id: str = "premium_cinematic_historical_stickman"
    language: Optional[str] = None           # auto-detect when None

    target_duration_sec: Optional[float] = None   # None = derive from narration
    words_per_second: float = 2.6
    min_shot_sec: float = 1.2
    max_shot_sec: float = 6.0

    similarity_threshold: float = 0.72
    similarity_window: int = 6
    stage_view_window: int = 5
    stage_view_max_in_window: int = 1        # >=2 in window -> violation
    max_replan_attempts: int = 12

    max_critic_retries: int = 2
    image_size: str = "1K"
    plate_overscan_aspect: str = "21:9"      # wider plates allow pan/reframe without regeneration

    models: ModelRouting = Field(default_factory=ModelRouting.from_env)

    @model_validator(mode="after")
    def _check_dims(self):
        if self.fps not in (24, 25, 30, 60):
            raise ValueError("fps must be one of 24, 25, 30, 60")
        landscape = self.width >= self.height
        if (self.aspect_ratio == AspectRatio.LANDSCAPE_16_9) != landscape:
            raise ValueError("width/height do not match aspect_ratio")
        return self

    @classmethod
    def for_aspect(cls, aspect: str = "16:9", **kw) -> "ProjectConfig":
        if aspect == "9:16":
            kw.setdefault("width", 1080)
            kw.setdefault("height", 1920)
            kw.setdefault("plate_overscan_aspect", "9:16")
            return cls(aspect_ratio=AspectRatio.PORTRAIT_9_16, **kw)
        return cls(aspect_ratio=AspectRatio.LANDSCAPE_16_9, **kw)
