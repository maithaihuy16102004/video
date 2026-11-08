"""Universal Voice System Data Contracts and Type Definitions.

Architectural Principles:
1. NEVER SPEED UP GENERATED VOICE TO FORCE IT INTO A VIDEO SLOT.
2. VOICE DEFINES REQUIRED SPEAKING TIME. VIDEO TIMELINE ADAPTS TO NATURAL SPEECH.
3. TTS MUST SPEAK APPROVED SCRIPT TEXT (ZERO METADATA, ZERO REWRITES).
4. ONE RECURRING CHARACTER = ONE STABLE VOICE IDENTITY.
5. NARRATOR != CHARACTER.
6. VOICE_ID != EMOTION (Same voice performs different emotions).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class LineType(str, Enum):
    NARRATION = "NARRATION"
    DIALOGUE = "DIALOGUE"
    INNER_MONOLOGUE = "INNER_MONOLOGUE"
    REACTION = "REACTION"
    OPTIONAL_ADLIB = "OPTIONAL_ADLIB"


class StorytellingMode(str, Enum):
    FIRST_PERSON_ROLEPLAY = "FIRST_PERSON_ROLEPLAY"          # DEFAULT: Protagonist tells their own story
    THIRD_PERSON_DOCUMENTARY = "THIRD_PERSON_DOCUMENTARY"    # External documentary narrator
    MULTI_POV = "MULTI_POV"                                  # Shifting POV
    OTHER = "OTHER"


class POVKnowledgeType(str, Enum):
    DIRECT_EXPERIENCE = "DIRECT_EXPERIENCE"
    OBSERVATION = "OBSERVATION"
    ACTION = "ACTION"
    REACTION = "REACTION"
    INNER_THOUGHT = "INNER_THOUGHT"
    MEMORY = "MEMORY"
    RETROSPECTIVE_CONTEXT = "RETROSPECTIVE_CONTEXT"
    LATER_KNOWLEDGE = "LATER_KNOWLEDGE"
    UNCERTAIN_RECONSTRUCTION = "UNCERTAIN_RECONSTRUCTION"


class ProvenanceType(str, Enum):
    DOCUMENTED = "DOCUMENTED"
    CONTEXT_SUPPORTED = "CONTEXT_SUPPORTED"
    PLAUSIBLE_RECONSTRUCTION = "PLAUSIBLE_RECONSTRUCTION"
    DRAMATIZED_RECONSTRUCTION = "DRAMATIZED_RECONSTRUCTION"
    UNKNOWN = "UNKNOWN"


@dataclass
class POVCharacterState:
    """State tracking for the primary storyteller / POV character."""
    primary_pov_character_id: str
    storytelling_mode: StorytellingMode = StorytellingMode.FIRST_PERSON_ROLEPLAY
    knowledge_state: str = "immediate"
    current_age: str = "25"
    current_time: str = "1914"
    current_location: str = "Munich"
    current_emotional_state: str = "alienated, expectant"
    memory_context: str = "bohemian civilian life"
    information_available_to_character: list[str] = field(default_factory=list)


class EmotionState(str, Enum):
    NEUTRAL = "NEUTRAL"
    CALM = "CALM"
    CONFIDENT = "CONFIDENT"
    TENSE = "TENSE"
    ANGRY = "ANGRY"
    AFRAID = "AFRAID"
    SAD = "SAD"
    EXHAUSTED = "EXHAUSTED"
    SURPRISED = "SURPRISED"
    DRY_COMEDY = "DRY_COMEDY"
    SERIOUS = "SERIOUS"


class DeliveryStyle(str, Enum):
    NATURAL = "NATURAL"
    STORYTELLING = "STORYTELLING"
    DOCUMENTARY = "DOCUMENTARY"
    INTIMATE = "INTIMATE"
    URGENT = "URGENT"
    FORMAL = "FORMAL"
    DEADPAN = "DEADPAN"


@dataclass
class SpokenLine:
    """Canonical ground truth representation of an approved spoken script line."""
    script_line_id: str
    speaker_id: str
    character_id: Optional[str]
    exact_spoken_text: str
    line_type: LineType = LineType.NARRATION
    tone: str = "NEUTRAL"
    emotion: EmotionState = EmotionState.NEUTRAL
    story_beat_id: Optional[str] = None
    line_number: int = 1
    pov_character_id: Optional[str] = None
    knowledge_type: POVKnowledgeType = POVKnowledgeType.DIRECT_EXPERIENCE
    provenance: ProvenanceType = ProvenanceType.CONTEXT_SUPPORTED
    camera_shot_suggestion: str = "MEDIUM"
    camera_is_pov: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EpisodeScriptTruth:
    """Canonical repository of approved spoken text for an episode."""
    episode_id: str
    title: str
    lines: list[SpokenLine]
    version: str = "2026.11-APPROVED"
    adlib_enabled: bool = False


@dataclass
class VietNeuVoiceInfo:
    """Inspection record of an installed VietNeu-TTS voice."""
    voice_id: str
    display_name: str
    gender: str                  # "male", "female", "neutral"
    region: str                  # "Bắc", "Nam", "Trung", "none"
    style_description: str
    engine_mode: str             # "v3nano", "v3turbo", etc.
    native_sample_rate: int = 24000
    is_installed: bool = True


@dataclass
class SpeakerRegistryEntry:
    """Persistent binding between a character / narrator and a specific VietNeu voice."""
    speaker_id: str
    character_id: Optional[str]
    voice_id: str
    voice_source: str = "VietNeu-TTS"
    gender_presentation: str = "male"
    apparent_age_range: str = "20-30"
    role_type: str = "historical_protagonist"
    personality_profile: str = "intense, ambitious, alienated"
    baseline_energy: float = 0.6
    baseline_tempo: float = 1.0     # 1.0 = native natural speed (STRICTLY NO SPEEDUP)
    baseline_pitch_character: str = "neutral"
    baseline_weight: float = 0.5
    baseline_formality: float = 0.5
    accent_region: str = "Bắc"
    allowed_emotional_range: list[EmotionState] = field(default_factory=list)
    is_narrator: bool = False
    locked_by_human: bool = False
    notes: str = ""


@dataclass
class VoiceCastingProfile:
    """Gemini-derived or rule-based casting requirements for a speaker."""
    character_id: str
    role: str
    age_impression: str
    energy: float
    authority: float
    warmth: float
    roughness: float
    formality: float
    tempo: float
    emotional_range: str
    comedic_dryness: float
    tension: float
    confidence: float
    recommended_voice_id: str
    candidate_rankings: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""


@dataclass
class VoicePerformancePlan:
    """Per-line performance instructions. NOTE: VOICE_ID stays constant; performance changes."""
    script_line_id: str
    speaker_id: str
    emotion: EmotionState
    emotion_intensity: float       # 0.0 to 1.0
    intent: str
    energy: float                  # 0.0 to 1.0
    pause_profile: str             # "short_end", "breath_pause", "dramatic_hold"
    emphasis_targets: list[str] = field(default_factory=list)
    delivery_style: DeliveryStyle = DeliveryStyle.NATURAL
    context_before: str = ""
    context_after: str = ""


@dataclass
class ExactTTSInput:
    """Immutable trace of text fed into the VietNeu-TTS engine."""
    script_line_id: str
    speaker_id: str
    character_id: Optional[str]
    original_text: str
    normalized_spoken_text: str
    voice_id: str
    prosody_plan_hash: str
    validated_no_metadata: bool = True
    input_hash: str = ""


@dataclass
class AudioValidationResult:
    """Comprehensive acoustic validation of synthesized speech waveform."""
    audio_path: str
    native_duration_seconds: float
    final_duration_seconds: float
    speed_ratio: float             # STRICT REQUIREMENT: speed_ratio == 1.0 (NO SPEEDUP)
    sample_rate: int
    channels: int
    peak_dbfs: float
    rms_dbfs: float
    silence_leading_ms: float
    silence_trailing_ms: float
    clipping_detected: bool
    is_valid: bool
    validation_notes: list[str] = field(default_factory=list)


@dataclass
class TimelineSpeechSlot:
    """Slot on the audio/video timeline where native speech defines visual length."""
    slot_id: str
    script_line_id: str
    speaker_id: str
    voice_id: str
    start_time_seconds: float
    native_duration_seconds: float
    end_time_seconds: float
    allocated_visual_duration_seconds: float
    visual_expanded: bool
    breathing_room_seconds: float = 0.35


@dataclass
class AudioTimeline:
    """Master chronological audio timeline where voice defines the temporal backbone."""
    timeline_id: str
    slots: list[TimelineSpeechSlot] = field(default_factory=list)
    total_duration_seconds: float = 0.0
