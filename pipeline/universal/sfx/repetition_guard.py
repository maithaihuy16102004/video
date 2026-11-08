"""SFX Repetition Guard.

Guarantees sound design discipline by preventing repetitive stingers, meme spam,
and acoustic clutter. Enforces cooldown windows and density thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .sfx_types import PrimaryFamily, SFXClassification, SFXCue, SFXSemanticProfile


@dataclass
class GuardViolation:
    time_seconds: float
    sfx_id: str
    canonical_name: str
    rule_violated: str
    detail: str
    action_taken: str              # "REJECTED_TRY_ALTERNATIVE", "MUTED_TO_SILENCE"


class SFXRepetitionGuard:
    """Monitors recent audio cues to enforce cooldowns, semantic diversity, and density bounds."""

    def __init__(
        self,
        exact_repeat_cooldown_seconds: float = 45.0,
        family_repeat_cooldown_seconds: float = 4.0,
        meme_cooldown_seconds: float = 60.0,
        max_sfx_per_10s: int = 3,
        max_editorial_per_30s: int = 2,
    ):
        self.exact_repeat_cooldown = exact_repeat_cooldown_seconds
        self.family_repeat_cooldown = family_repeat_cooldown_seconds
        self.meme_cooldown = meme_cooldown_seconds
        self.max_sfx_per_10s = max_sfx_per_10s
        self.max_editorial_per_30s = max_editorial_per_30s

        self.history: list[SFXCue] = []
        self.violations: list[GuardViolation] = []

    def check_candidate(
        self,
        profile: SFXSemanticProfile,
        intended_time: float,
    ) -> tuple[bool, Optional[GuardViolation]]:
        """Validates candidate against history. Returns (is_allowed, violation_if_any)."""
        # 1. Exact SFX repeat check
        for past in self.history:
            if past.sfx_id == profile.sfx_id:
                dt = abs(intended_time - past.start_time_seconds)
                if dt < self.exact_repeat_cooldown:
                    v = GuardViolation(
                        time_seconds=intended_time,
                        sfx_id=profile.sfx_id,
                        canonical_name=profile.canonical_name,
                        rule_violated="EXACT_REPEAT_COOLDOWN",
                        detail=f"SFX '{profile.canonical_name}' was already used at t={past.start_time_seconds:.2f}s (dt={dt:.2f}s < {self.exact_repeat_cooldown}s)",
                        action_taken="REJECTED_TRY_ALTERNATIVE",
                    )
                    self.violations.append(v)
                    return False, v

        # 2. Meme cooldown check
        if profile.meme_strength > 0.3:
            for past in self.history:
                # If past item was also a meme
                dt = abs(intended_time - past.start_time_seconds)
                if dt < self.meme_cooldown:
                    # Check past profile classification / meme nature
                    if past.classification == SFXClassification.EDITORIAL and past.primary_family in (
                        PrimaryFamily.MEME_REACTION,
                        PrimaryFamily.SPOKEN_REACTION,
                        PrimaryFamily.COMEDY,
                    ):
                        v = GuardViolation(
                            time_seconds=intended_time,
                            sfx_id=profile.sfx_id,
                            canonical_name=profile.canonical_name,
                            rule_violated="MEME_COOLDOWN",
                            detail=f"Meme sting '{profile.canonical_name}' blocked; previous stinger fired at t={past.start_time_seconds:.2f}s (dt={dt:.2f}s < {self.meme_cooldown}s)",
                            action_taken="REJECTED_TRY_ALTERNATIVE",
                        )
                        self.violations.append(v)
                        return False, v

        # 3. Density check: SFX per 10s
        sfx_in_window = [
            p for p in self.history if abs(intended_time - p.start_time_seconds) <= 10.0
        ]
        if len(sfx_in_window) >= self.max_sfx_per_10s:
            v = GuardViolation(
                time_seconds=intended_time,
                sfx_id=profile.sfx_id,
                canonical_name=profile.canonical_name,
                rule_violated="DENSITY_LIMIT_10S",
                detail=f"Density limit exceeded ({len(sfx_in_window)} SFX within 10s >= limit {self.max_sfx_per_10s})",
                action_taken="MUTED_TO_SILENCE",
            )
            self.violations.append(v)
            return False, v

        # 4. Density check: Editorial per 30s
        if profile.classification == SFXClassification.EDITORIAL:
            editorial_in_30s = [
                p for p in self.history
                if p.classification == SFXClassification.EDITORIAL and abs(intended_time - p.start_time_seconds) <= 30.0
            ]
            if len(editorial_in_30s) >= self.max_editorial_per_30s:
                v = GuardViolation(
                    time_seconds=intended_time,
                    sfx_id=profile.sfx_id,
                    canonical_name=profile.canonical_name,
                    rule_violated="EDITORIAL_DENSITY_LIMIT_30S",
                    detail=f"Editorial density exceeded ({len(editorial_in_30s)} editorial hits within 30s >= limit {self.max_editorial_per_30s})",
                    action_taken="MUTED_TO_SILENCE",
                )
                self.violations.append(v)
                return False, v

        return True, None

    def record_cue(self, cue: SFXCue) -> None:
        """Records an accepted cue into the timeline history."""
        self.history.append(cue)

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "total_cues_recorded": len(self.history),
            "total_violations_prevented": len(self.violations),
            "cooldown_rules": {
                "exact_repeat_cooldown_seconds": self.exact_repeat_cooldown,
                "family_repeat_cooldown_seconds": self.family_repeat_cooldown,
                "meme_cooldown_seconds": self.meme_cooldown,
                "max_sfx_per_10s": self.max_sfx_per_10s,
                "max_editorial_per_30s": self.max_editorial_per_30s,
            },
            "violations_log": [
                {
                    "time_seconds": round(v.time_seconds, 2),
                    "sfx_id": v.sfx_id,
                    "canonical_name": v.canonical_name,
                    "rule_violated": v.rule_violated,
                    "detail": v.detail,
                    "action_taken": v.action_taken,
                }
                for v in self.violations
            ],
        }
