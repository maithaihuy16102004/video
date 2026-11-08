"""Universal Sound Opportunity Detector.

Detects points in the story event graph where sound naturally belongs or silence is required.
Enforces the fundamental principles:
- SOUND MUST FOLLOW EVENT.
- SILENCE IS A VALID SOUND DECISION.
- VOICE HAS PRIORITY.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .sfx_types import MixPriority, PrimaryFamily, SFXClassification, SoundOpportunity, ToneState


@dataclass
class StoryEvent:
    """Universal representation of a story event from the Scene Event Graph."""
    event_id: str
    time_seconds: float
    duration_seconds: float
    description: str
    category: str                   # "physical_action", "editorial_beat", "environment", "emotional_pivot"
    actor_id: Optional[str] = None
    target_id: Optional[str] = None
    tone: ToneState = ToneState.NEUTRAL
    intensity: float = 0.5          # 0.0 to 1.0
    is_diegetic: bool = True
    suggested_family: Optional[PrimaryFamily] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NarrationSegment:
    """Represents an active spoken dialogue or voiceover window."""
    segment_id: str
    start_seconds: float
    end_seconds: float
    speaker: str
    text: str
    criticality: float = 0.8        # 1.0 = historical fact, 0.5 = conversational filler


class SoundOpportunityDetector:
    """Analyzes story events and narration windows to discover legitimate sound opportunities."""

    def __init__(self):
        self._opportunity_counter = 0

    def detect_opportunities(
        self,
        events: list[StoryEvent],
        narration: list[NarrationSegment],
        overall_tone: ToneState = ToneState.NEUTRAL,
    ) -> list[SoundOpportunity]:
        opportunities: list[SoundOpportunity] = []

        for event in events:
            # Check overlap with narration
            is_voice_active = False
            voice_crit = 0.0
            for seg in narration:
                if seg.start_seconds <= event.time_seconds <= seg.end_seconds:
                    is_voice_active = True
                    voice_crit = max(voice_crit, seg.criticality)
                elif abs(event.time_seconds - seg.start_seconds) < 0.2:
                    is_voice_active = True
                    voice_crit = max(voice_crit, seg.criticality)

            opp = self._analyze_single_event(event, is_voice_active, voice_crit, overall_tone)
            if opp:
                opportunities.append(opp)

        return opportunities

    def _analyze_single_event(
        self,
        event: StoryEvent,
        voice_active: bool,
        voice_criticality: float,
        overall_tone: ToneState,
    ) -> Optional[SoundOpportunity]:
        self._opportunity_counter += 1
        opp_id = f"opp_{self._opportunity_counter:03d}_{event.event_id}"

        desc_lower = event.description.lower()
        effective_tone = event.tone if event.tone != ToneState.NEUTRAL else overall_tone

        # 1. Silence Gate: Check if event demands deliberate silence
        # (e.g. death announcement, traumatic shock, solemn realization)
        if event.category == "emotional_pivot" or any(term in desc_lower for term in ["silence", "tĩnh lặng", "surrender", "đầu hàng", "trầm mặc", "shocked", "bàng hoàng", "blinded", "mù lòa"]):
            return SoundOpportunity(
                opportunity_id=opp_id,
                event_id=event.event_id,
                time_anchor_seconds=event.time_seconds,
                duration_window_seconds=max(event.duration_seconds, 1.5),
                physical_event_description=event.description,
                sound_intent="deliberate_silence_for_emotional_gravity",
                tone=effective_tone,
                intensity=event.intensity,
                priority=MixPriority.P0_CRITICAL_PHYSICAL,
                diegetic=True,
                allowed_families=[],
                forbidden_families=list(PrimaryFamily),
                silence_preferred=True,
                silence_reason="Solemn emotional shock: silence communicates deeper historical weight than any sound effect.",
                narration_active=voice_active,
                narration_criticality=voice_criticality,
                reason="Silence is a valid sound decision here to honor the emotional pivot.",
            )

        # 2. Physical Events
        if event.is_diegetic or event.category in ("physical_action", "environment"):
            allowed: list[PrimaryFamily] = []
            forbidden: list[PrimaryFamily] = [
                PrimaryFamily.MEME_REACTION,
                PrimaryFamily.SPOKEN_REACTION,
                PrimaryFamily.UI,
            ]
            intent = "physical_reconstruction"
            priority = MixPriority.P1_IMPORTANT_ACTION

            if any(term in desc_lower for term in ["door", "cửa", "slam", "đóng sầm"]):
                allowed = [PrimaryFamily.DOOR, PrimaryFamily.IMPACT]
                intent = "door_closure_or_slam"
                priority = MixPriority.P1_IMPORTANT_ACTION
            elif any(term in desc_lower for term in ["punch", "strike", "đấm", "tác động vật lý"]):
                allowed = [PrimaryFamily.PUNCH, PrimaryFamily.HIT, PrimaryFamily.IMPACT]
                intent = "physical_punch_or_blow"
                priority = MixPriority.P0_CRITICAL_PHYSICAL
            elif any(term in desc_lower for term in ["metal", "pipe", "thanh sắt", "kim loại", "drop", "rơi"]):
                allowed = [PrimaryFamily.METAL_IMPACT, PrimaryFamily.DROP, PrimaryFamily.IMPACT]
                intent = "metal_object_drop_or_impact"
                priority = MixPriority.P1_IMPORTANT_ACTION
            elif any(term in desc_lower for term in ["paper", "giấy", "hồ sơ", "document", "đơn", "stamp"]):
                allowed = [PrimaryFamily.PAPER, PrimaryFamily.OBJECT_MOVE]
                intent = "paper_handling_or_signing"
                priority = MixPriority.P1_IMPORTANT_ACTION
            elif any(term in desc_lower for term in ["cloth", "pocket", "vải", "túi áo"]):
                allowed = [PrimaryFamily.CLOTH, PrimaryFamily.OBJECT_MOVE]
                intent = "coat_pocket_foley"
                priority = MixPriority.P2_ENVIRONMENT_FOLEY
            elif any(term in desc_lower for term in ["crowd", "cheer", "đám đông", "reo hò"]):
                allowed = [PrimaryFamily.CROWD, PrimaryFamily.ENVIRONMENT]
                intent = "crowd_ambience_foley"
                priority = MixPriority.P2_ENVIRONMENT_FOLEY
            elif any(term in desc_lower for term in ["footstep", "bước chân", "march", "hành quân"]):
                allowed = [PrimaryFamily.FOOTSTEP, PrimaryFamily.RUN]
                intent = "soldier_footsteps_in_mud_or_street"
                priority = MixPriority.P2_ENVIRONMENT_FOLEY
            elif any(term in desc_lower for term in ["explosion", "nổ", "pháo", "artillery", "shrapnel"]):
                allowed = [PrimaryFamily.IMPACT, PrimaryFamily.DRAMATIC_STING]
                intent = "artillery_shell_explosion"
                priority = MixPriority.P0_CRITICAL_PHYSICAL
            elif event.suggested_family:
                allowed = [event.suggested_family]
            else:
                allowed = [PrimaryFamily.IMPACT, PrimaryFamily.OBJECT_MOVE]

            # In serious tone, strictly forbid comedic/meme families
            if effective_tone in (ToneState.SERIOUS, ToneState.DARK):
                forbidden.extend([PrimaryFamily.COMEDY, PrimaryFamily.MUSICAL_STING])

            return SoundOpportunity(
                opportunity_id=opp_id,
                event_id=event.event_id,
                time_anchor_seconds=event.time_seconds,
                duration_window_seconds=max(event.duration_seconds, 0.4),
                physical_event_description=event.description,
                sound_intent=intent,
                tone=effective_tone,
                intensity=event.intensity,
                priority=priority,
                diegetic=True,
                allowed_families=allowed,
                forbidden_families=forbidden,
                silence_preferred=False,
                narration_active=voice_active,
                narration_criticality=voice_criticality,
                reason=f"Physical action '{event.description}' naturally produces acoustic vibration in world.",
            )

        # 3. Editorial Beats (Accents, Irony, Reveals)
        else:
            allowed = []
            forbidden = []
            intent = "editorial_punctuation"
            priority = MixPriority.P3_EDITORIAL_ACCENT

            if effective_tone in (ToneState.SERIOUS, ToneState.DARK):
                # Serious scenes only allow restrained dramatic stings or tension drones
                allowed = [PrimaryFamily.DRAMATIC_STING, PrimaryFamily.TENSION]
                forbidden = [
                    PrimaryFamily.COMEDY,
                    PrimaryFamily.MEME_REACTION,
                    PrimaryFamily.SPOKEN_REACTION,
                ]
                intent = "serious_dramatic_punctuation"
            elif effective_tone == ToneState.DRY_COMEDY:
                # Dry comedy allows ironic musical stings, subtle comedic clicks/crickets, or dry reveal
                allowed = [PrimaryFamily.COMEDY, PrimaryFamily.REVEAL, PrimaryFamily.MUSICAL_STING]
                forbidden = [PrimaryFamily.SPOKEN_REACTION] if voice_active else []
                intent = "dry_irony_punctuation"
            else:
                allowed = [PrimaryFamily.COMEDY, PrimaryFamily.SURPRISE, PrimaryFamily.REACTION]
                intent = "comedic_accent"

            return SoundOpportunity(
                opportunity_id=opp_id,
                event_id=event.event_id,
                time_anchor_seconds=event.time_seconds,
                duration_window_seconds=max(event.duration_seconds, 0.5),
                physical_event_description=event.description,
                sound_intent=intent,
                tone=effective_tone,
                intensity=event.intensity,
                priority=priority,
                diegetic=False,
                allowed_families=allowed,
                forbidden_families=forbidden,
                silence_preferred=False,
                narration_active=voice_active,
                narration_criticality=voice_criticality,
                reason=f"Editorial beat '{event.description}' punctuates narrative subtext for audience.",
            )
