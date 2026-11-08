"""Universal Semantic Sound Effect System: Type Definitions and Data Contracts.

Epistemological Foundations:
1. SOUND MUST FOLLOW EVENT. EVENT MUST NOT BE INVENTED TO JUSTIFY SOUND.
2. SFX IS NOT DECORATION: Every SFX must answer: What physical event? What editorial purpose? What emotional change? Why now?
3. SILENCE IS A VALID SOUND DECISION.
4. VOICE HAS PRIORITY: Narration/dialogue must remain intelligible at all times.
5. PHYSICAL VS EDITORIAL SEPARATION: Physical exists inside the story world; Editorial is added for viewer interpretation.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class SFXClassification(str, Enum):
    PHYSICAL = "PHYSICAL"          # Diegetic: Occurs inside the story world (door close, footstep, shell blast)
    EDITORIAL = "EDITORIAL"        # Non-diegetic: Editor accent for comedic, ironic, or dramatic interpretation
    AMBIENT = "AMBIENT"            # Environmental soundscape (distant artillery, rain, crowd murmur, room tone)
    REACTION = "REACTION"          # Immediate human/audience response (gasp, cheer, awkward silence beat)
    MUSICAL = "MUSICAL"            # Rhythmic or harmonic sting/cue (record scratch, dramatic chord, sad violin)
    HYBRID = "HYBRID"              # Blends physical action with editorial exaggeration (cartoon punch, dramatic boom)


class PrimaryFamily(str, Enum):
    IMPACT = "IMPACT"
    HIT = "HIT"
    SLAP = "SLAP"
    PUNCH = "PUNCH"
    METAL_IMPACT = "METAL_IMPACT"
    DROP = "DROP"
    FALL = "FALL"
    BREAK = "BREAK"
    CRACK = "CRACK"
    FOOTSTEP = "FOOTSTEP"
    RUN = "RUN"
    DOOR = "DOOR"
    OBJECT_MOVE = "OBJECT_MOVE"
    MECHANICAL = "MECHANICAL"
    PAPER = "PAPER"
    CLOTH = "CLOTH"
    WEAPON_EVENT = "WEAPON_EVENT"
    VEHICLE = "VEHICLE"
    ENVIRONMENT = "ENVIRONMENT"
    CROWD = "CROWD"
    REACTION = "REACTION"
    COMEDY = "COMEDY"
    SURPRISE = "SURPRISE"
    FAILURE = "FAILURE"
    REVEAL = "REVEAL"
    TENSION = "TENSION"
    DRAMATIC_STING = "DRAMATIC_STING"
    TRANSITION = "TRANSITION"
    UI = "UI"
    MUSICAL_STING = "MUSICAL_STING"
    MEME_REACTION = "MEME_REACTION"
    SPOKEN_REACTION = "SPOKEN_REACTION"


class ToneState(str, Enum):
    SERIOUS = "SERIOUS"            # Death, tragedy, sacrifice, historical explanation: ZERO meme sounds
    DARK = "DARK"                  # Gritty trench mud, shell shock, suffering: physical/somber only
    TENSE = "TENSE"                # Approaching danger, silent suspense: physical ticks, breathing, silence
    NEUTRAL = "NEUTRAL"            # Factual exposition: subtle clean physical foley, minimal editorial
    DRY_COMEDY = "DRY_COMEDY"      # Irony, deadpan satire, bureaucratic absurdity: controlled comedic accents
    COMEDY = "COMEDY"              # Lighthearted, slapstick: expressive comedic stings (still anti-spam)


class TimingAnchor(str, Enum):
    ON_CONTACT = "ON_CONTACT"      # Synchronized exactly with physical impact/touch
    PRE_CONTACT = "PRE_CONTACT"    # Swish/windup right before contact
    POST_CONTACT = "POST_CONTACT"  # Echo, rubble settling, reaction
    ON_REVEAL = "ON_REVEAL"        # Synchronized with visual appearance / cut
    ON_REACTION = "ON_REACTION"    # Synchronized with character facial expression
    ON_CUT = "ON_CUT"              # Hard cut transition hit
    ACTION_START = "ACTION_START"  # Movement initiates
    ACTION_END = "ACTION_END"      # Movement completes


class MixPriority(str, Enum):
    P0_CRITICAL_PHYSICAL = "P0"    # Cannot be muted (core physical story beat: gunshot, explosion, collapse)
    P1_IMPORTANT_ACTION = "P1"     # Important character action (door slam, table strike, key object drop)
    P2_ENVIRONMENT_FOLEY = "P2"    # Texture / body foley (footsteps, paper rustle, fabric, distant rumble)
    P3_EDITORIAL_ACCENT = "P3"     # Editorial punctuation (dramatic sting, comedic chime, reveal hit)
    P4_OPTIONAL_EMBELLISHMENT = "P4" # Optional meme/humorous tag (dropped first if mix is crowded or voice active)


class ApprovalState(str, Enum):
    UNREVIEWED = "UNREVIEWED"      # Ingested metadata, awaiting semantic validation
    APPROVED = "APPROVED"          # Fully validated, rights-cleared/locally usable for production
    REJECTED = "REJECTED"          # Unusable (poor audio, copyright risk, offensive, corrupted)
    RESTRICTED = "RESTRICTED"      # Usable only under strict editorial conditions (e.g. parody tone only)


class CatalogMode(str, Enum):
    METADATA_ONLY = "METADATA_ONLY"        # Indexed from external library; audio not downloaded
    REFERENCE_ONLY = "REFERENCE_ONLY"      # Audio referenced/streamed; not bundled in repo
    LOCAL_APPROVED_ASSET = "LOCAL_APPROVED"# Downloaded, validated, normalized, and cached locally


@dataclass
class AudioAnalysisProfile:
    """Deterministic, measurable audio characteristics (handled by AudioAnalyzer, NOT Gemini)."""
    duration_seconds: float
    sample_rate: int = 48000
    channels: int = 2
    peak_dbfs: float = 0.0
    rms_dbfs: float = -18.0
    silence_leading_ms: float = 0.0
    silence_trailing_ms: float = 0.0
    attack_ms: float = 10.0
    decay_ms: float = 200.0
    spectral_centroid_hz: float = 2500.0  # Brightness proxy
    dynamic_range_db: float = 18.0
    is_percussive: bool = True


@dataclass
class SFXMetadata:
    """Raw ingestion entry from external or local source."""
    source_id: str
    source_name: str
    source_url: str
    display_name: str
    source_category: str = "general"
    source_language: str = "unknown"
    catalog_mode: CatalogMode = CatalogMode.METADATA_ONLY
    local_path: Optional[str] = None
    ingested_at: str = "2026-11-08T13:30:00+07:00"


@dataclass
class SFXSemanticProfile:
    """Deep semantic understanding produced by Gemini & verified in catalog."""
    sfx_id: str
    canonical_name: str
    classification: SFXClassification
    primary_family: PrimaryFamily
    secondary_families: list[str] = field(default_factory=list)
    
    # Story & Physical Grounding
    physical_event: str = ""
    editorial_intent: str = ""
    emotion: str = "neutral"
    energy: float = 0.5            # 0.0 to 1.0
    intensity: float = 0.5         # 0.0 to 1.0
    attack_type: str = "sharp"     # "sharp", "gradual", "swelling", "impact"
    duration_class: str = "short"  # "micro" (<0.3s), "short" (0.3-1.5s), "medium" (1.5-4s), "long" (>4s)
    
    # Tone & Historical Safety Gates
    comedy_level: float = 0.0      # 0.0 (serious) to 1.0 (pure slapstick/meme)
    seriousness_compatibility: float = 0.5  # Can it be used in serious scenes? (0.0 forbidden, 1.0 fully safe)
    historical_scene_compatibility: float = 0.5 # 1.0 for authentic period physical, 0.1 for anachronistic meme
    
    # Voice & Spoken Content Flags
    spoken_content: str = ""
    language: str = "none"         # "vi", "en", "none", etc.
    contains_music: bool = False
    contains_voice: bool = False
    
    # Meme & Intrusiveness Controls
    meme_strength: float = 0.0     # 0.0 (generic foley) to 1.0 (iconic viral meme)
    intrusiveness: float = 0.5     # How much it dominates mix / distracts from narration
    
    # Production Rules
    best_use_cases: list[str] = field(default_factory=list)
    bad_use_cases: list[str] = field(default_factory=list)
    timing_anchor: TimingAnchor = TimingAnchor.ON_CONTACT
    default_mix_priority: MixPriority = MixPriority.P2_ENVIRONMENT_FOLEY
    approval_state: ApprovalState = ApprovalState.APPROVED
    confidence: float = 0.95


@dataclass
class SoundOpportunity:
    """Identified point in the narrative where sound naturally belongs or silence is desired."""
    opportunity_id: str
    event_id: str
    time_anchor_seconds: float
    duration_window_seconds: float
    physical_event_description: str
    sound_intent: str
    tone: ToneState
    intensity: float               # 0.0 to 1.0
    priority: MixPriority
    diegetic: bool                 # True = in-world physical, False = editorial accent
    allowed_families: list[PrimaryFamily] = field(default_factory=list)
    forbidden_families: list[PrimaryFamily] = field(default_factory=list)
    silence_preferred: bool = False
    silence_reason: str = ""
    narration_active: bool = False
    narration_criticality: float = 0.0 # 1.0 = vital historical fact, don't mask!
    reason: str = ""


@dataclass
class SFXCue:
    """Frame-accurate, mixed audio cue on the project audio timeline."""
    cue_id: str
    event_id: str
    sfx_id: str
    canonical_name: str
    classification: SFXClassification
    primary_family: PrimaryFamily
    start_time_seconds: float
    start_frame: int
    duration_seconds: float
    trim_start: float = 0.0
    trim_end: float = 0.0
    gain_db: float = 0.0
    fade_in_ms: float = 10.0
    fade_out_ms: float = 25.0
    pan: float = 0.0               # -1.0 left, 0.0 center, 1.0 right
    priority: MixPriority = MixPriority.P2_ENVIRONMENT_FOLEY
    ducking_applied_db: float = 0.0
    timing_anchor: TimingAnchor = TimingAnchor.ON_CONTACT
    editorial_reason: str = ""
    confidence: float = 0.95
    source_url: str = ""
    local_file_path: Optional[str] = None


@dataclass
class SFXSelectionResult:
    opportunity_id: str
    selected_cue: Optional[SFXCue]
    candidates_retrieved: list[str]
    gemini_ranked_order: list[str]
    selection_rationale: str
    rejection_reasons: dict[str, str] = field(default_factory=dict)
    is_silence: bool = False
