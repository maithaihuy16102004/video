"""History-aware visual similarity guard.

Enforces:
  IF visual_similarity_score > threshold (0.72) AND NOT intentional_repetition:
      REJECT_SHOT -> REDIRECT_CAMERA
"""
from __future__ import annotations

from typing import Any

from ..schemas.plan import Shot
from .camera_delta import compute_shot_similarity


class SimilarityCheckResult:
    def __init__(
        self,
        passed: bool,
        max_similarity: float,
        most_similar_shot_id: str | None = None,
        most_similar_index: int | None = None,
        scores: list[tuple[str, float]] | None = None,
    ):
        self.passed = passed
        self.max_similarity = max_similarity
        self.most_similar_shot_id = most_similar_shot_id
        self.most_similar_index = most_similar_index
        self.scores = scores or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "max_similarity": self.max_similarity,
            "most_similar_shot_id": self.most_similar_shot_id,
            "most_similar_index": self.most_similar_index,
            "scores": self.scores,
        }


def check_shot_similarity(
    candidate: Shot | dict[str, Any],
    history_shots: list[Shot | dict[str, Any]],
    threshold: float = 0.72,
    window_size: int = 6,
) -> SimilarityCheckResult:
    """Checks candidate shot against up to `window_size` previous shots."""
    if not history_shots:
        return SimilarityCheckResult(passed=True, max_similarity=0.0)

    window = history_shots[-window_size:]
    scores: list[tuple[str, float]] = []
    max_sim = 0.0
    most_similar_id: str | None = None
    most_similar_idx: int | None = None

    for offset, prev in enumerate(window):
        sim = compute_shot_similarity(candidate, prev)
        pid = (
            prev.get("shot_id") if isinstance(prev, dict) else getattr(prev, "shot_id", f"SHOT_{offset}")
        )
        scores.append((str(pid), sim))
        if sim > max_sim:
            max_sim = sim
            most_similar_id = str(pid)
            most_similar_idx = len(history_shots) - len(window) + offset

    # If flagged as intentional repetition, it passes despite high similarity
    intentional = bool(
        candidate.get("intentional_repetition")
        if isinstance(candidate, dict)
        else getattr(candidate, "intentional_repetition", False)
    )
    passed = (max_sim <= threshold) or intentional
    return SimilarityCheckResult(
        passed=passed,
        max_similarity=max_sim,
        most_similar_shot_id=most_similar_id,
        most_similar_index=most_similar_idx,
        scores=scores,
    )
