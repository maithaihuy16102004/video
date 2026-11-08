"""Universal Semantic SFX Catalog.

Indexes and retrieves SFXSemanticProfile instances.
Provides multi-criteria search, tone-safe filtering, and audit inspection.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from .sfx_types import (
    ApprovalState,
    AudioAnalysisProfile,
    CatalogMode,
    MixPriority,
    PrimaryFamily,
    SFXClassification,
    SFXMetadata,
    SFXSemanticProfile,
    TimingAnchor,
    ToneState,
)


class SFXCatalog:
    """Indexed catalog of semantic sound effect profiles."""

    def __init__(self):
        self._profiles: dict[str, SFXSemanticProfile] = {}
        self._metadata: dict[str, SFXMetadata] = {}
        self._audio: dict[str, AudioAnalysisProfile] = {}
        self._by_family: dict[PrimaryFamily, list[str]] = {}
        self._by_classification: dict[SFXClassification, list[str]] = {}

    def register(
        self,
        profile: SFXSemanticProfile,
        metadata: Optional[SFXMetadata] = None,
        audio: Optional[AudioAnalysisProfile] = None,
    ) -> None:
        """Register a semantic profile and its associated metadata/audio characteristics."""
        sfx_id = profile.sfx_id
        self._profiles[sfx_id] = profile
        if metadata:
            self._metadata[sfx_id] = metadata
        if audio:
            self._audio[sfx_id] = audio

        # Inverted index by family
        fam = profile.primary_family
        if fam not in self._by_family:
            self._by_family[fam] = []
        if sfx_id not in self._by_family[fam]:
            self._by_family[fam].append(sfx_id)

        # Inverted index by classification
        cls_ = profile.classification
        if cls_ not in self._by_classification:
            self._by_classification[cls_] = []
        if sfx_id not in self._by_classification[cls_]:
            self._by_classification[cls_].append(sfx_id)

    def get_profile(self, sfx_id: str) -> Optional[SFXSemanticProfile]:
        return self._profiles.get(sfx_id)

    def get_metadata(self, sfx_id: str) -> Optional[SFXMetadata]:
        return self._metadata.get(sfx_id)

    def get_audio(self, sfx_id: str) -> Optional[AudioAnalysisProfile]:
        return self._audio.get(sfx_id)

    def list_all(self) -> list[SFXSemanticProfile]:
        return list(self._profiles.values())

    def search_candidates(
        self,
        intent: str,
        tone: ToneState,
        classification: Optional[SFXClassification] = None,
        allowed_families: Optional[list[PrimaryFamily]] = None,
        forbidden_families: Optional[list[PrimaryFamily]] = None,
        allow_meme: bool = True,
        max_comedy: float = 1.0,
        avoid_voice: bool = False,
        top_k: int = 8,
    ) -> list[SFXSemanticProfile]:
        """Multi-factor semantic sound search with strict tone gating and historical safety."""
        intent_lower = intent.lower()
        intent_tokens = set(re.findall(r"\w+", intent_lower))
        candidates: list[tuple[float, SFXSemanticProfile]] = []

        allowed_fams_set = set(allowed_families) if allowed_families else None
        forbidden_fams_set = set(forbidden_families) if forbidden_families else set()

        for sfx_id, prof in self._profiles.items():
            # 1. Approval Gate
            if prof.approval_state == ApprovalState.REJECTED:
                continue

            # 2. Strict Tone & Meme Gates
            if tone in (ToneState.SERIOUS, ToneState.DARK):
                # Serious/Dark scene strictly forbids meme sounds or high-comedy sounds
                if prof.meme_strength > 0.05:
                    continue
                if prof.comedy_level > 0.2:
                    continue
                if prof.seriousness_compatibility < 0.4:
                    continue

            if not allow_meme and prof.meme_strength > 0.1:
                continue

            if prof.comedy_level > max_comedy:
                continue

            # 3. Voice Gate (Narration Protection)
            if avoid_voice and prof.contains_voice:
                continue

            # 4. Family Constraints
            if prof.primary_family in forbidden_fams_set:
                continue
            if allowed_fams_set and prof.primary_family not in allowed_fams_set:
                # If primary family not in allowed, check secondary families
                sec_match = any(sec in [f.value for f in allowed_fams_set] for sec in prof.secondary_families)
                if not sec_match:
                    continue

            # 5. Classification Constraint
            if classification and prof.classification != classification:
                # If strict classification specified, drop non-matching unless HYBRID
                if prof.classification != SFXClassification.HYBRID:
                    continue

            # 6. Scoring Engine
            score = 0.0

            # Semantic keyword overlap
            searchable_text = (
                f"{prof.canonical_name} {prof.physical_event} {prof.editorial_intent} "
                f"{' '.join(prof.best_use_cases)} {' '.join(prof.secondary_families)} "
                f"{prof.classification.value} {prof.primary_family.value}"
            ).lower()
            prof_tokens = set(re.findall(r"\w+", searchable_text))
            overlap = intent_tokens.intersection(prof_tokens)
            score += len(overlap) * 3.0

            # Substring match in canonical name or physical event
            for token in intent_tokens:
                if len(token) >= 3 and token in searchable_text:
                    score += 2.0

            # Family affinity
            if allowed_fams_set and prof.primary_family in allowed_fams_set:
                score += 5.0

            # Tone alignment bonus
            if tone == ToneState.SERIOUS:
                score += prof.seriousness_compatibility * 4.0
                score += prof.historical_scene_compatibility * 3.0
            elif tone in (ToneState.DRY_COMEDY, ToneState.COMEDY):
                if "comedy" in intent_lower or "irony" in intent_lower or "awkward" in intent_lower:
                    score += prof.comedy_level * 4.0

            # Quality / confidence
            score += prof.confidence

            # Small tie-breaker for approved assets
            if prof.approval_state == ApprovalState.APPROVED:
                score += 1.0

            candidates.append((score, prof))

        # Sort descending by score
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in candidates[:top_k]]

    def to_audit_dict(self) -> dict[str, Any]:
        """Produces comprehensive catalog audit structure."""
        items = []
        for sfx_id, prof in self._profiles.items():
            meta = self._metadata.get(sfx_id)
            audio = self._audio.get(sfx_id)
            items.append({
                "sfx_id": sfx_id,
                "canonical_name": prof.canonical_name,
                "classification": prof.classification.value,
                "primary_family": prof.primary_family.value,
                "secondary_families": prof.secondary_families,
                "physical_event": prof.physical_event,
                "editorial_intent": prof.editorial_intent,
                "emotion": prof.emotion,
                "energy": prof.energy,
                "intensity": prof.intensity,
                "comedy_level": prof.comedy_level,
                "seriousness_compatibility": prof.seriousness_compatibility,
                "historical_scene_compatibility": prof.historical_scene_compatibility,
                "contains_voice": prof.contains_voice,
                "contains_music": prof.contains_music,
                "meme_strength": prof.meme_strength,
                "timing_anchor": prof.timing_anchor.value,
                "default_mix_priority": prof.default_mix_priority.value,
                "approval_state": prof.approval_state.value,
                "source_url": meta.source_url if meta else "",
                "duration_seconds": audio.duration_seconds if audio else 1.0,
                "peak_dbfs": audio.peak_dbfs if audio else 0.0,
            })
        return {
            "total_sounds": len(self._profiles),
            "by_classification": {k.value: len(v) for k, v in self._by_classification.items()},
            "by_family": {k.value: len(v) for k, v in self._by_family.items()},
            "catalog": items,
        }
