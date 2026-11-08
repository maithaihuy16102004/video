"""Universal Sound Director.

The brain of the SFX system.
Translates SoundOpportunities into frame-accurate, tone-safe SFXCues.
Enforces:
- WHAT PHYSICAL EVENT?
- WHAT EDITORIAL PURPOSE?
- WHAT EMOTIONAL CHANGE?
- WHY NOW?
- VOICE-AWARE DUCKING.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Optional

_PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
_ROOT_DIR = Path(__file__).resolve().parents[3]
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from pipeline.env_secrets import get_gemini_api_key

from .catalog import SFXCatalog
from .repetition_guard import SFXRepetitionGuard
from .sfx_types import (
    ApprovalState,
    MixPriority,
    PrimaryFamily,
    SFXClassification,
    SFXCue,
    SFXSelectionResult,
    SFXSemanticProfile,
    SoundOpportunity,
    TimingAnchor,
    ToneState,
)


class UniversalSoundDirector:
    """Intelligent audio director orchestrating semantic sound selection and timeline placement."""

    def __init__(
        self,
        catalog: SFXCatalog,
        repetition_guard: Optional[SFXRepetitionGuard] = None,
        fps: int = 30,
        enable_gemini: bool = True,
    ):
        self.catalog = catalog
        self.guard = repetition_guard or SFXRepetitionGuard()
        self.fps = fps
        self.enable_gemini = enable_gemini
        self.api_key = get_gemini_api_key() if enable_gemini else None

        self.selection_results: list[SFXSelectionResult] = []
        self.gemini_audit_records: list[dict[str, Any]] = []

    def direct_opportunity(self, opp: SoundOpportunity) -> SFXSelectionResult:
        """Evaluates a sound opportunity, selects optimal SFX, and constructs the SFXCue."""
        # 1. Deliberate Silence Check
        if opp.silence_preferred:
            result = SFXSelectionResult(
                opportunity_id=opp.opportunity_id,
                selected_cue=None,
                candidates_retrieved=[],
                gemini_ranked_order=[],
                selection_rationale=f"DELIBERATE SILENCE: {opp.silence_reason}",
                rejection_reasons={"all_sfx": "Muted to protect emotional gravity and historical weight."},
                is_silence=True,
            )
            self.selection_results.append(result)
            return result

        # 2. Candidate Retrieval from Catalog
        # Voice protection: if narration is active and critical, strictly avoid spoken meme sounds
        avoid_voice = opp.narration_active
        allow_meme = opp.tone not in (ToneState.SERIOUS, ToneState.DARK)

        candidates = self.catalog.search_candidates(
            intent=opp.sound_intent,
            tone=opp.tone,
            allowed_families=opp.allowed_families if opp.allowed_families else None,
            forbidden_families=opp.forbidden_families if opp.forbidden_families else None,
            allow_meme=allow_meme,
            max_comedy=0.2 if opp.tone in (ToneState.SERIOUS, ToneState.DARK) else 1.0,
            avoid_voice=avoid_voice,
            top_k=6,
        )

        cand_ids = [c.sfx_id for c in candidates]

        if not candidates:
            # No viable candidate found that satisfies tone and family filters
            result = SFXSelectionResult(
                opportunity_id=opp.opportunity_id,
                selected_cue=None,
                candidates_retrieved=[],
                gemini_ranked_order=[],
                selection_rationale="No sound candidate passed tone safety and family gates; falling back to silence.",
                rejection_reasons={"catalog": "No matching approved sound without violating tone gates."},
                is_silence=True,
            )
            self.selection_results.append(result)
            return result

        # 3. Candidate Ranking (Gemini or Deterministic Fallback)
        ranked_candidates = self._rank_candidates(opp, candidates)
        ranked_ids = [c.sfx_id for c in ranked_candidates]

        # 4. Filter against Repetition Guard & Voice Collisions
        selected_prof: Optional[SFXSemanticProfile] = None
        rejections: dict[str, str] = {}

        for prof in ranked_candidates:
            # Check repetition & cooldown guard
            allowed, violation = self.guard.check_candidate(prof, opp.time_anchor_seconds)
            if not allowed and violation:
                rejections[prof.sfx_id] = f"{violation.rule_violated}: {violation.detail}"
                continue

            # Check spoken collision
            if opp.narration_active and prof.contains_voice:
                rejections[prof.sfx_id] = "VOICE_COLLISION: Sound contains spoken words while narration is speaking."
                continue

            # Check serious tone safety
            if opp.tone in (ToneState.SERIOUS, ToneState.DARK) and prof.meme_strength > 0.05:
                rejections[prof.sfx_id] = "TONE_SAFETY: Meme sound prohibited in serious historical scene."
                continue

            selected_prof = prof
            break

        if not selected_prof:
            # All candidates rejected by guard or collision
            result = SFXSelectionResult(
                opportunity_id=opp.opportunity_id,
                selected_cue=None,
                candidates_retrieved=cand_ids,
                gemini_ranked_order=ranked_ids,
                selection_rationale="All candidates rejected by repetition cooldown or voice collision guard; preserved silence.",
                rejection_reasons=rejections,
                is_silence=True,
            )
            self.selection_results.append(result)
            return result

        # 5. Build Frame-Accurate Cue & Calculate Voice-Aware Mixing
        cue = self._construct_cue(opp, selected_prof)
        self.guard.record_cue(cue)

        rationale = (
            f"Selected '{selected_prof.canonical_name}' for event '{opp.physical_event_description}'. "
            f"Editorial purpose: {selected_prof.editorial_intent or 'Support physical impact'}. "
            f"Tone '{opp.tone.value}' respected. Gain: {cue.gain_db:.1f} dB (Ducking: {cue.ducking_applied_db:.1f} dB)."
        )

        result = SFXSelectionResult(
            opportunity_id=opp.opportunity_id,
            selected_cue=cue,
            candidates_retrieved=cand_ids,
            gemini_ranked_order=ranked_ids,
            selection_rationale=rationale,
            rejection_reasons=rejections,
            is_silence=False,
        )
        self.selection_results.append(result)
        return result

    def _rank_candidates(
        self,
        opp: SoundOpportunity,
        candidates: list[SFXSemanticProfile],
    ) -> list[SFXSemanticProfile]:
        """Ranks candidates according to narrative fit and tone safety."""
        # Score-based deterministic ranking
        def score_candidate(p: SFXSemanticProfile) -> float:
            s = 0.0
            # Diegetic matching: if event is diegetic, favor physical classification
            if opp.diegetic:
                if p.classification == SFXClassification.PHYSICAL:
                    s += 10.0
                elif p.classification == SFXClassification.HYBRID:
                    s += 5.0
                elif p.classification == SFXClassification.EDITORIAL:
                    s -= 8.0
            else:
                if p.classification in (SFXClassification.EDITORIAL, SFXClassification.MUSICAL):
                    s += 10.0
                elif p.classification == SFXClassification.HYBRID:
                    s += 5.0

            # Tone alignment
            if opp.tone == ToneState.SERIOUS:
                s += p.seriousness_compatibility * 8.0
                s += p.historical_scene_compatibility * 6.0
                s -= p.comedy_level * 15.0
            elif opp.tone == ToneState.DRY_COMEDY:
                # Dry comedy favors restrained irony (comedy_level ~ 0.3 - 0.7)
                s += (1.0 - abs(p.comedy_level - 0.5)) * 6.0
            elif opp.tone == ToneState.COMEDY:
                s += p.comedy_level * 8.0

            # Direct primary family match bonus
            if opp.allowed_families and p.primary_family == opp.allowed_families[0]:
                s += 25.0

            # Energy alignment
            s += (1.0 - abs(p.energy - opp.intensity)) * 4.0

            # Intrusiveness penalty if voice is active
            if opp.narration_active:
                s -= p.intrusiveness * 5.0

            return s

        ranked = sorted(candidates, key=score_candidate, reverse=True)

        self.gemini_audit_records.append({
            "opportunity_id": opp.opportunity_id,
            "event": opp.physical_event_description,
            "tone": opp.tone.value,
            "candidates_evaluated": [c.sfx_id for c in candidates],
            "top_choice": ranked[0].sfx_id if ranked else None,
            "decision_method": "deterministic_semantic_scoring",
        })

        return ranked

    def _construct_cue(
        self,
        opp: SoundOpportunity,
        prof: SFXSemanticProfile,
    ) -> SFXCue:
        """Constructs an SFXCue with precise timing and voice-aware ducking."""
        audio_profile = self.catalog.get_audio(prof.sfx_id)
        metadata = self.catalog.get_metadata(prof.sfx_id)

        duration = audio_profile.duration_seconds if audio_profile else 1.2
        attack_offset = (audio_profile.attack_ms / 1000.0) if audio_profile else 0.02

        # Timing Anchor alignment
        if prof.timing_anchor == TimingAnchor.ON_CONTACT:
            start_time = max(0.0, opp.time_anchor_seconds - attack_offset)
        elif prof.timing_anchor == TimingAnchor.PRE_CONTACT:
            start_time = max(0.0, opp.time_anchor_seconds - 0.2)
        elif prof.timing_anchor == TimingAnchor.ON_REVEAL:
            start_time = opp.time_anchor_seconds
        else:
            start_time = opp.time_anchor_seconds

        start_frame = round(start_time * self.fps)

        # Base Gain calculation based on priority and intensity
        # P0: 0 dB, P1: -3 dB, P2: -8 dB, P3: -6 dB, P4: -12 dB
        priority_gain_map = {
            MixPriority.P0_CRITICAL_PHYSICAL: 0.0,
            MixPriority.P1_IMPORTANT_ACTION: -3.0,
            MixPriority.P2_ENVIRONMENT_FOLEY: -8.0,
            MixPriority.P3_EDITORIAL_ACCENT: -6.0,
            MixPriority.P4_OPTIONAL_EMBELLISHMENT: -12.0,
        }
        base_gain = priority_gain_map.get(opp.priority, -6.0)

        # Scale with opportunity intensity
        intensity_mod = (opp.intensity - 0.5) * 4.0  # -2 dB to +2 dB
        gain = base_gain + intensity_mod

        # Voice-Aware Ducking: If narration is active, apply ducking
        ducking_applied = 0.0
        if opp.narration_active:
            if opp.priority == MixPriority.P0_CRITICAL_PHYSICAL:
                # Critical physical sounds still punch through, duck slightly
                ducking_applied = -4.0
            elif opp.priority == MixPriority.P1_IMPORTANT_ACTION:
                ducking_applied = -8.0
            elif opp.priority in (MixPriority.P2_ENVIRONMENT_FOLEY, MixPriority.P3_EDITORIAL_ACCENT):
                ducking_applied = -12.0
            else:
                ducking_applied = -16.0

        final_gain = max(-36.0, min(3.0, gain + ducking_applied))

        cue_id = f"cue_{opp.opportunity_id}_{prof.sfx_id}"

        editorial_reason = (
            f"Physical Event: {opp.physical_event_description}. "
            f"Editorial Purpose: {prof.editorial_intent or 'Reconstruct physical scene reality'}. "
            f"Emotional Change: Intensity {opp.intensity:.1f}, Tone {opp.tone.value}. "
            f"Why Now: Synchronized with {prof.timing_anchor.value} at t={opp.time_anchor_seconds:.2f}s."
        )

        return SFXCue(
            cue_id=cue_id,
            event_id=opp.event_id,
            sfx_id=prof.sfx_id,
            canonical_name=prof.canonical_name,
            classification=prof.classification,
            primary_family=prof.primary_family,
            start_time_seconds=round(start_time, 3),
            start_frame=start_frame,
            duration_seconds=round(duration, 3),
            gain_db=round(final_gain, 1),
            ducking_applied_db=round(ducking_applied, 1),
            timing_anchor=prof.timing_anchor,
            priority=opp.priority,
            editorial_reason=editorial_reason,
            confidence=prof.confidence,
            source_url=metadata.source_url if metadata else "",
            local_file_path=metadata.local_path if metadata else None,
        )

    def to_audit_dict(self) -> dict[str, Any]:
        """Outputs complete selection audit ledger."""
        cues = []
        silences = []
        for res in self.selection_results:
            if res.selected_cue:
                c = res.selected_cue
                cues.append({
                    "cue_id": c.cue_id,
                    "event_id": c.event_id,
                    "sfx_id": c.sfx_id,
                    "canonical_name": c.canonical_name,
                    "classification": c.classification.value,
                    "primary_family": c.primary_family.value,
                    "start_time_seconds": c.start_time_seconds,
                    "start_frame": c.start_frame,
                    "duration_seconds": c.duration_seconds,
                    "gain_db": c.gain_db,
                    "ducking_applied_db": c.ducking_applied_db,
                    "editorial_reason": c.editorial_reason,
                    "rejection_reasons": res.rejection_reasons,
                })
            else:
                silences.append({
                    "opportunity_id": res.opportunity_id,
                    "is_silence": True,
                    "rationale": res.selection_rationale,
                    "rejection_reasons": res.rejection_reasons,
                })

        return {
            "total_opportunities_evaluated": len(self.selection_results),
            "total_cues_placed": len(cues),
            "total_silence_decisions": len(silences),
            "placed_cues": cues,
            "silence_decisions": silences,
            "director_decisions": self.gemini_audit_records,
        }
