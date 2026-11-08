"""Research-first strategy gates for short-form video drafts.

This module does not predict virality. It prevents weak, unsourced ideas from
entering the expensive rendering stage and produces controlled test variants.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


FORMAT_FAMILIES = {
    "contrarian_proof",
    "process_reveal",
    "problem_mechanism_payoff",
    "ranked_discovery",
    "myth_vs_evidence",
    "before_after_transformation",
}


@dataclass(frozen=True)
class HookScore:
    specificity: int
    novelty: int
    audience_relevance: int
    evidence_strength: int
    visualizability: int
    honesty: int

    @property
    def total(self) -> int:
        return sum(asdict(self).values())

    @property
    def passes(self) -> bool:
        return self.total >= 21 and self.honesty >= 3 and self.evidence_strength >= 3


def score_hook(**criteria: int) -> HookScore:
    required = {"specificity", "novelty", "audience_relevance", "evidence_strength", "visualizability", "honesty"}
    missing = required - criteria.keys()
    if missing:
        raise ValueError("Thiếu tiêu chí hook: " + ", ".join(sorted(missing)))
    normalized = {name: max(0, min(5, int(criteria[name]))) for name in required}
    return HookScore(**normalized)


def validate_research_brief(brief: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_text = ["audience_job", "pain_or_tension", "novel_claim", "share_trigger", "save_trigger", "format_family"]
    for key in required_text:
        if not str(brief.get(key, "")).strip():
            errors.append(f"Thiếu {key}.")
    if brief.get("format_family") not in FORMAT_FAMILIES:
        errors.append("format_family không nằm trong bộ format đã kiểm duyệt.")
    proof_items = brief.get("proof_items") or []
    if len(proof_items) < 3:
        errors.append("Cần tối thiểu 3 bằng chứng độc lập.")
    for index, proof in enumerate(proof_items, 1):
        if not isinstance(proof, dict) or not str(proof.get("source_url", "")).startswith(("http://", "https://")):
            errors.append(f"Bằng chứng {index} thiếu source_url hợp lệ.")
        if not str((proof or {}).get("claim", "")).strip():
            errors.append(f"Bằng chứng {index} thiếu claim.")
    if any(flag in {"social_proof", "financial", "medical", "legal"} for flag in brief.get("risk_flags", [])):
        if not brief.get("human_review_required", False):
            errors.append("Nội dung rủi ro cao phải bật human_review_required.")
    return errors


def build_variant_matrix(hooks: list[str], durations: tuple[int, ...] = (40, 52), modes: tuple[str, ...] = ("motion", "commentary")) -> list[dict[str, Any]]:
    """Create controlled variants; callers should change one axis per test batch."""
    matrix = []
    for hook_index, hook in enumerate(hooks[:3], 1):
        for duration in durations[:2]:
            for mode in modes[:2]:
                matrix.append({"id": f"h{hook_index}-{duration}-{mode}", "hook": hook, "target_duration": duration, "presentation_mode": mode})
    return matrix[:6]
