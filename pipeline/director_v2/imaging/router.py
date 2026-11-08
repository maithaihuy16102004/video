"""Routing logic for Fast / Main / Hero image model tiers."""
from __future__ import annotations

from ..config import ProjectConfig
from ..schemas.core import ImageTier


class ImageRouter:
    def __init__(self, config: ProjectConfig):
        self.config = config

    def select_model(self, tier: ImageTier, retry_count: int = 0) -> str:
        """Selects model for a tier.

        In MASTER quality, if an asset fails QC on retry, it can be escalated to HERO model.
        """
        if self.config.quality.value == "MASTER" and retry_count > 0:
            return self.config.models.hero_image_model
        return self.config.models.image_model(tier)
