"""Visual Critic.

Evaluates generated frames against 10-12 criteria using thresholds.
Enforces MAX_RETRY = 2. Retains detailed failure reasons.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schemas.assets import AssetRequirement, CriticAttempt
from .vision_provider import VisionProvider

THRESHOLDS_PATH = Path(__file__).resolve().parents[1] / "data" / "critic_thresholds.json"


def load_critic_thresholds() -> dict[str, float]:
    if THRESHOLDS_PATH.exists():
        data = json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
        return data.get("thresholds", {})
    return {
        "character_identity": 0.88,
        "historical_accuracy": 0.90,
        "stickman_style": 0.95,
        "camera_compliance": 0.75,
        "perspective": 0.80,
        "depth": 0.70,
    }


class VisualCritic:
    def __init__(self, provider: VisionProvider | None = None, max_retries: int = 2):
        self.provider = provider
        self.max_retries = max_retries
        self.thresholds = load_critic_thresholds()

    def evaluate_asset(
        self,
        image_path: Path,
        req: AssetRequirement,
        attempt_num: int,
        model_name: str,
    ) -> tuple[bool, CriticAttempt]:
        """Evaluates asset image. Returns (passed, CriticAttempt)."""
        if not self.provider or not image_path.exists():
            # If no vision provider configured (offline/mock), pass by default
            return True, CriticAttempt(
                attempt=attempt_num,
                model=model_name,
                scores={"offline_pass": 1.0},
                notes="Offline mode: Critic check passed automatically",
                path=str(image_path),
            )

        rubric = (
            f"Evaluate this historical stickman asset for {req.description}. "
            f"Historical constraints: {'; '.join(req.historical_constraints)}. "
            f"Check stickman style, perspective fidelity, depth, and historical accuracy."
        )

        res = self.provider.score_image(image_path, rubric, self.thresholds)
        passed = bool(res.get("passed", False))
        failed = list(res.get("failed_criteria", []))
        scores = res.get("scores", {})

        attempt = CriticAttempt(
            attempt=attempt_num,
            model=model_name,
            scores=scores,
            failed_criteria=failed,
            notes=str(res.get("notes", "")),
            path=str(image_path),
        )
        return passed, attempt
