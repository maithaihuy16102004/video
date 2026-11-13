"""STUDIO SCRIPT V1 parser — universal script format for AI Clip Studio.

Port and extension of the upstream V5.1 parser
(``video-upstream/pipeline/studio_script_v1_parser.py``), rewritten as a
stdlib-only module with no per-story code: no story, character, or
location names are hardcoded anywhere in this module.

Canonical grammar (see ``docs/studio_script_v1.schema.json`` and the
standing directive in ``docs/DIRECTIVE_STUDIO_SCRIPT_V1.md``):

- Line-based, UTF-8. ``#`` comment lines and blank lines are ignored.
- ``KEY: value`` lines; block headers ``BLOCK:``, ``BLOCK <id>:``,
  ``SCENE <n>: <title>``, ``SHOT <id>:``. Keys are case-insensitive;
  values preserve Unicode/Vietnamese verbatim.
- The FIRST_PERSON_ROLEPLAY dialect (Stage 3) adds bare block headers
  (``PROJECT``, ``VISUAL_STYLE``, ``GLOBAL_AUDIO``, ``QA``, ``OUTPUT``,
  ``END_CARD``, ``GLOBAL_NEGATIVE_CONSTRAINTS``), ``SCENE: <id>`` and
  ``SHOT: <id>`` headers, ``⸻`` separator lines, an ``END STUDIO SCRIPT
  V1`` terminator, bullet lists, structured ``NARRATION:`` / ``DIALOGUE:``
  sub-blocks, and structured ``SFX:`` sub-blocks. Both dialects are
  accepted by this one parser; documents using new-dialect markers use
  the permissive rules of SPEC §3.3 (verbatim TRANSITION, TYPE optional
  when CAMERA is present, ``3s`` END_CARD durations), while legacy
  documents keep the strict Phase A rules.
- Every parsed node records its source line number. Unknown keys are
  recorded in ``unsupported_fields`` with line numbers — never silently
  discarded.
- ``parse()`` never raises on invalid content: it returns the document
  with ``validation_errors`` (each with line, code, message) and
  ``warnings``. ``parse(text, strict=True)`` raises
  :class:`StudioScriptV1Error` on the first error.
- Spoken text is NEVER rewritten. Production tags inside spoken text are
  validation errors (upstream Rule 2).
- ``snapshot_hash`` is the SHA-256 hex of the exact raw input text.

Head-ratio lock (Mai-approved): the default is 0.34 and the valid range
is 0.33-0.35 inclusive. The upstream default of 0.42 is NEVER inherited;
a script requesting a head ratio outside the locked range is a
validation error.

Deliberate differences from the upstream parser:

- No meme resolution (no file lookup, no ``meme_resolver`` dependency):
  MEME lines are recorded as data only.
- No estimated durations from word counts: the directive requires an
  audio-driven timeline, so no duration is ever estimated here.
- No voice-id assignment: VOICE values are kept verbatim (``AUTO`` by
  default); voice selection belongs to the TTS stage.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEAD_RATIO_DEFAULT = 0.34
HEAD_RATIO_MIN = 0.33
HEAD_RATIO_MAX = 0.35

# Shot vocabulary. MUST match camera_planner.SHOT_TYPES exactly (that
# module imports PIL, so the vocabulary is duplicated here to keep this
# module stdlib-only; keep the two in sync).
SHOT_TYPES = (
    "establishing",
    "medium",
    "close_up",
    "extreme_close_up",
    "over_the_shoulder",
    "reaction",
    "object_insert",
    "tracking",
    "shot_reverse_shot",
    # Stage 3 / channel-study vocabulary (R1/R6), mirroring
    # camera_planner.SHOT_TYPES exactly (sync test).
    "medium_close_up",
    "graphic_insert",
)

TRANSITIONS = (
    "CUT",
    "DISSOLVE",
    "FADE",
    "FADE_TO_BLACK",
    "MATCH_CUT",
    "WIPE",
)

CAMERA_MOVEMENTS = (
    "STATIC",
    "PAN_LEFT",
    "PAN_RIGHT",
    "TILT_UP",
    "TILT_DOWN",
    "DOLLY_IN",
    "DOLLY_OUT",
    "TRACKING",
    "CRANE_UP",
    "CRANE_DOWN",
    "HANDHELD",
)

ASPECT_RATIOS = ("16:9", "9:16")
MEME_POLICIES = ("CONTEXTUAL", "NONE", "ALWAYS")
PRIORITIES = ("REQUIRED", "OPTIONAL")
AMBIENCE_MODES = ("LOOP", "ONCE")
INTENSITIES = ("LOW", "MEDIUM", "HIGH")
RESOLUTIONS = ("1920x1080", "1280x720")
FRAME_RATES = (24, 25, 30)
AUDIO_BUSES = ("narration", "dialogue", "ambience", "foley", "sfx", "bgm")

# Speaker labels that always mean the narrator (normalized: casefolded,
# whitespace collapsed). Checked before declared-character matching, so a
# CHARACTER block that names the narrator does not change spoken lines.
NARRATOR_ALIASES = frozenset({
    "narrator",
    "người kể chuyện",
    "người dẫn chuyện",
    "dẫn chuyện",
})

NARRATOR_SPEAKER = "Narrator"

# Production tags that must never appear inside spoken text (upstream
# Rule 2). Matched case-insensitively, tag followed by a colon.
PRODUCTION_TAGS_IN_SPEECH = (
    "LOCATION:",
    "ACTION:",
    "CAMERA:",
    "SFX:",
    "GAIN_DB:",
)

HEADER_KEYS = (
    "PROJECT",
    "LANGUAGE",
    "GENRE",
    "STYLE",
    "VISUAL_STYLE",
    "ASPECT_RATIO",
    "TARGET_DURATION",
    "TONE",
    "MEME_POLICY",
    "MEME_MAX_PER_MINUTE",
)

CHARACTER_KEYS = (
    "ROLE",
    "APPEARANCE",
    "TRAITS",
    "COSTUME",
    "COSTUME_CHANGE",
    "VOICE",
    "VOICE_STYLE",
    "HEAD_RATIO",
    "IDENTITY_ID",
    # New-dialect CHARACTER vocabulary (SPEC §5.1).
    "NAME",
    "AGE",
    "GENDER",
    "NATIONALITY",
    "YEAR",
    "BODY_TYPE",
    "FACE_SHAPE",
    "HAIR",
    "MOUSTACHE",
    "EYEBROWS",
    "EYES",
    "SKIN_TONE",
    "DEFAULT_EXPRESSION",
    "PERSONALITY_PRESENTATION",
    "FACIAL_FEATURES",
    "COSTUME_CIVILIAN",
    "COSTUME_MILITARY",
    "VOICE_ENGINE",
    "VOICE_ID",
    "VOICE_SPEED",
    "VOICE_TONE",
    "ANIMATION_CAPABILITIES",
    "ANIMATION",
    "COUNT",
    "IDENTITY_LOCK",
    # Further trait keys (same general pattern: per-character
    # distinctive traits supplied by the script / sketcher).
    "AGE_VARIANTS",
    "BEARD",
    "BODY_COLOR",
    "COSTUME_ADULT",
    "COSTUME_CHILD",
    "COSTUME_KING",
    "HORNS",
    "NAMES",
    "RIG_REQUIREMENT",
    "SIGNATURE_PROP",
    "SPECIES",
    "NARRATION_VOICE",
    "PROPS",
    "DISTINCTIVE_FEATURES",
)

LOCATION_KEYS = (
    "NAME",
    "PERIOD",
    "GEOGRAPHY",
    "ARCHITECTURE",
    "FEATURES",
    "FOREGROUND",
    "MIDGROUND",
    "BACKGROUND",
    "LIGHTING",
    "WEATHER",
    "PALETTE",
    "FORBIDDEN",
    # New-dialect LOCATION vocabulary (SPEC §5.2).
    "HISTORICAL_REFERENCE",
    "HISTORICAL_STATUS",
    "YEAR",
    "TIME_OF_DAY",
    "TYPE",
    "DISTINCTIVE_FEATURES",
    "COLOR_PALETTE",
    "AMBIENCE",
    "MAP_STYLE",
    "LABEL_LANGUAGE",
    "ANIMATION",
    "REFERENCE_RESEARCH",
)

PROP_KEYS = (
    "DESCRIPTION",
    "OWNER",
    "SCENES",
    "INTERACTION",
    # New-dialect PROP vocabulary (SPEC §5.3).
    "NAME",
    "TYPE",
    "COLOR",
    "MATERIAL",
    "VFX",
)

SHOT_KEYS = (
    "TYPE",
    "CAMERA",
    "CAMERA_MOVEMENT",
    "SUBJECT",
    "DURATION",
    "ACTION",
    "EXPRESSION",
    "VFX",
    # New-dialect SHOT vocabulary (SPEC §5.5).
    "LOCATION_OVERRIDE",
    "TRIGGER",
    "COMPOSITION",
    "POST_DIALOGUE_PAUSE",
    "END_HOLD",
    "FLASH_SAFETY",
)

SCENE_KEYS = (
    "LOCATION",
    "TIME_OF_DAY",
    "MOOD",
    "DURATION",
    "VISUAL",
    "TRANSITION",
    "ACTION",
    "EXPRESSION",
    "CAMERA",
    "CAMERA_MOVEMENT",
    "VOICE_NOTE",
    "MEME_NOTE",
    "NARRATION",
    "DIALOGUE",
    "SFX",
    "AMBIENCE",
    "BGM",
    "MUSIC",
    "MEME",
    "VFX",
    # New-dialect SCENE vocabulary (SPEC §5.4).
    "TITLE",
    "CHARACTERS",
    "COSTUME",
    "STORY_PURPOSE",
    "HISTORICAL_PROVENANCE",
    "LOCATION_OVERRIDE",
)

GLOBAL_AUDIO_KEYS = (
    "NARRATION_GAIN_DB",
    "DIALOGUE_GAIN_DB",
    "AMBIENCE_GAIN_DB",
    "FOLEY_GAIN_DB",
    "SFX_GAIN_DB",
    "BGM_GAIN_DB",
    "BGM_DUCKING_DB",
    "MASTER_LIMIT_DB",
    # New-dialect GLOBAL_AUDIO vocabulary (SPEC §5.6). BGM_DUCKING is
    # free text ("12–18 dB below speech"), distinct from BGM_DUCKING_DB.
    "TTS_ENGINE",
    "LANGUAGE",
    "TTS_SPEED",
    "VOICE_FALLBACK",
    "VOICE_PRIORITY",
    "BGM_DUCKING",
    "SFX_DENSITY",
    "SFX_TRIGGER_MODE",
    "AMBIENCE_MODE",
    "SUBTITLE_LANGUAGE",
    "SUBTITLE_SYNC",
    "SUBTITLE_STYLE",
    "AUDIO_TRUNCATION",
    "UNNATURAL_AUDIO_SPEEDUP",
    "MEME_SOUND",
    "AUTOMATIC_TRANSITION_WHOOSH",
    "PRONUNCIATION_POLICY",
    "PRONUNCIATION_REVIEW",
)

QA_KEYS = (
    "MIN_SCORE",
    "REQUIRE_TECHNICAL",
    "REQUIRE_CREATIVE_REVIEW",
    "LANGUAGE_GATE",
    "MAX_HARD_FAILS",
    # New-dialect QA vocabulary (SPEC §5.8). EXPECTED_* / *_CHECK keys
    # are also accepted by pattern (see _is_qa_key).
    "MIN_OVERALL_SCORE",
    "MIN_CATEGORY_SCORE",
    "TARGET_VISUAL_SCORE",
    "HARD_FAIL_COUNT",
    "EXPECTED_SCENES",
    "EXPECTED_SHOTS",
    "EXPECTED_SPOKEN_LINES",
    "EXPECTED_NARRATION_LINES",
    "EXPECTED_DIALOGUE_LINES",
    "EXPECTED_EXTERNAL_NARRATOR_LINES",
    "EXPECTED_EXPLICIT_SFX_EVENTS",
    "FAILED_QA_POLICY",
    "HUMAN_VISUAL_REVIEW",
    "VOICE_LISTENING_REVIEW",
    "MP4_VALIDATION",
    "UNSUPPORTED_ANIMATION_POLICY",
)

OUTPUT_KEYS = (
    "RESOLUTION",
    "FPS",
    "FORMAT",
    "DRAFT_FOLDER",
    "MASTER",
    # New-dialect OUTPUT vocabulary (SPEC §5.9). EXPORT_* keys are
    # also accepted by pattern (see _is_output_key).
    "VIDEO_FORMAT",
    "VIDEO_CODEC",
    "AUDIO_CODEC",
    "PIXEL_FORMAT",
    "UPLOAD_GOOGLE_DRIVE",
    "DRIVE_ROOT_ID",
    "DRIVE_PROJECT_FOLDER",
    "DRIVE_SUBFOLDERS",
    "MASTER_APPROVAL",
)

END_CARD_KEYS = (
    "TEXT",
    "DURATION",
    "STYLE",
    # New-dialect END_CARD vocabulary (SPEC §5.10).
    "BACKGROUND",
    "SECONDARY_TEXT",
    "TEXT_LANGUAGE",
    "BGM",
    "SFX",
)

# New-dialect PROJECT block vocabulary (SPEC §4.1). Header keys
# (HEADER_KEYS) are also accepted inside a PROJECT block.
PROJECT_KEYS = (
    "PROJECT_ID",
    "TITLE",
    "EPISODE",
    "GENRE",
    "LANGUAGE",
    "STORYTELLING_MODE",
    "PRIMARY_CHARACTER",
    "EXTERNAL_NARRATOR",
    "PLATFORM",
    "ASPECT_RATIO",
    "RESOLUTION",
    "FPS",
    "DURATION_MODE",
    "TARGET_DURATION",
    "HISTORICAL_PERIOD",
    "CONTENT_PURPOSE",
    "HISTORICAL_DISCLAIMER",
    "MYTHOLOGY_DISCLAIMER",
    "MYTHOLOGY_SOURCE",
    "SERIES",
    "TONE",
    "STYLE",
    "VISUAL_STYLE",
    "MEME_POLICY",
    "MEME_MAX_PER_MINUTE",
    "PROJECT",
)

# New-dialect VISUAL_STYLE block vocabulary (SPEC §4.2).
VISUAL_STYLE_KEYS = (
    "STYLE",
    "QUALITY_REFERENCE",
    "VISUAL_TARGET_SCORE",
    "DESIGN_POLICY",
    "HEAD_RATIO",
    "BODY_STYLE",
    "OUTLINE",
    "SHADING",
    "LIGHTING",
    "BACKGROUND",
    "DEPTH",
    "ANIMATION",
    "FACIAL_ANIMATION",
    "LIP_SYNC",
    "EYE_TRACKING",
    "CAMERA_STYLE",
    "COLOR_PROGRESSION",
    "STATIC_SLIDESHOW",
    "PREGENERATED_AI_VIDEO",
    "COMEDY_STYLE",
    "CHARACTER_AGE_PROGRESSION",
    "CHARACTER_SCALE_VARIATION",
    "BACKGROUND_STYLE",
    "CAMERA_ONLY_ANIMATION",
    "GRAPHIC_GORE",
)

# Bare block headers (no colon) recognised by the new dialect
# (SPEC §2.3). The colon forms remain valid for every block.
BARE_BLOCK_HEADERS = (
    "PROJECT",
    "VISUAL_STYLE",
    "GLOBAL_AUDIO",
    "GLOBAL_NEGATIVE_CONSTRAINTS",
    "QA",
    "OUTPUT",
    "END_CARD",
)

# No upstream header defaults are inherited (SPEC §4): PROJECT, GENRE,
# STYLE / VISUAL_STYLE, and TONE absent means "unspecified", stored as
# None in the parsed document. LANGUAGE, ASPECT_RATIO, TARGET_DURATION,
# MEME_POLICY, and MEME_MAX_PER_MINUTE keep the defaults in §4.

_SCENE_RE = re.compile(r"^SCENE\s+(\d+)\s*:\s*(.*)$", re.IGNORECASE)
_SCENE_ID_RE = re.compile(r"^SCENE\s*:\s*([A-Za-z][A-Za-z0-9_]*)\s*$", re.IGNORECASE)
_SHOT_RE = re.compile(r"^SHOT\s+(.+?)\s*:\s*$", re.IGNORECASE)
_SHOT_COLON_RE = re.compile(r"^SHOT\s*:\s*([A-Za-z0-9_][A-Za-z0-9_\-]*)\s*$", re.IGNORECASE)
_KEY_VALUE_RE = re.compile(r"^([A-Za-zÀ-ỹ0-9_][A-Za-zÀ-ỹ0-9_ .'\-]*?)\s*:\s*(.*)$")
_BULLET_RE = re.compile(r"^[*\-]\s+(.+)$")
_SEPARATOR_RE = re.compile(r"^[⸻]+$")
_BARE_MARKER_RE = re.compile(r"^STUDIO\s+SCRIPT\s+V1$", re.IGNORECASE)
_TERMINATOR_RE = re.compile(r"^END\s+STUDIO\s+SCRIPT\s+V1\s*:?$", re.IGNORECASE)
# TARGET_DURATION ranges: "85–100 seconds", "85-100", "85 – 100 s".
_RANGE_DURATION_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*[–—\-]\s*(\d+(?:\.\d+)?)\s*(seconds?|s)?$",
    re.IGNORECASE)
# Durations with an optional unit suffix: "0.6s", "3", "1.5 sec".
_SECONDS_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(seconds?|secs?|s)?$", re.IGNORECASE)
_LINE_ID_RE = re.compile(r"^\[(L\d+)\]\s*:?\s*(.*)$", re.IGNORECASE)
_COSTUME_CHANGE_RE = re.compile(r"^SCENE\s+(\d+)\s*:\s*(.+)$", re.IGNORECASE)
# Plain decimal seconds only: no unit suffix is defined, so "12s" /
# "30s" are invalid (SPEC §4, V1E012).
_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)$")
# A bracket that looks like a malformed explicit LINE_ID, checked only
# after the valid LINE_ID form has failed to match: "[LX]", "[L]",
# "[L12x]", or "[L001:" (missing closing bracket). Bracketed free text
# that does not start with "L" (e.g. "[tiếng chuông]") is not an id.
_MALFORMED_LINE_ID_RE = re.compile(r"^\[\s*L[^\]]*\]|^\[L\d+\s*:", re.IGNORECASE)
_MARKER_RE = re.compile(r"^#\s*STUDIO\s+SCRIPT\s+V1\b", re.IGNORECASE)
_PROJECT_RE = re.compile(r"^PROJECT\s*:", re.IGNORECASE)


class StudioScriptV1Error(Exception):
    """Raised by strict parsing on the first validation error."""

    def __init__(self, issue: "ValidationIssue") -> None:
        self.issue = issue
        super().__init__(f"line {issue.line}: [{issue.code}] {issue.message}")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    line: int  # 1-based source line; 0 = document-level issue
    code: str
    message: str


@dataclass
class UnsupportedField:
    key: str
    value: str
    line: int
    context: str  # e.g. "document", "character:<name>", "scene:3", "shot:SH01"


@dataclass
class ScriptCharacter:
    name: str
    role: str = ""
    appearance: str = ""
    traits: List[str] = field(default_factory=list)
    costume: str = ""
    costume_changes: List[Dict[str, Any]] = field(default_factory=list)
    # Each costume change: {"scene_number": int, "outfit": str, "line": int}
    voice: str = "AUTO"
    voice_style: str = ""
    head_ratio: float = HEAD_RATIO_DEFAULT
    identity_id: str = ""  # defaults to the block id at finalization
    line: int = 0
    # New dialect: "id" is the CHARACTER block id (the header remainder);
    # "name" is the display NAME when given, else the id. In the legacy
    # dialect id == name. "fields" holds EVERYTHING in the block
    # verbatim: all KEY: values plus bullet lists keyed by key name.
    id: str = ""
    is_extra: bool = False
    fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScriptLocation:
    id: str
    name: str = ""
    period: str = ""
    geography: str = ""
    architecture: str = ""
    features: List[str] = field(default_factory=list)
    # Foreground/midground/background are free text in the legacy
    # dialect and bullet lists in the new dialect; either shape is
    # stored verbatim.
    foreground: Any = ""
    midground: Any = ""
    background: Any = ""
    lighting: str = ""
    weather: str = ""
    palette: List[str] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)
    line: int = 0
    type: str = ""
    fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScriptProp:
    name: str
    description: str = ""
    owner: str = ""
    scenes: List[int] = field(default_factory=list)
    all_scenes: bool = False
    interactions: List[str] = field(default_factory=list)
    line: int = 0
    id: str = ""
    type: str = ""
    fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScriptSpokenLine:
    line_id: str
    speaker: str
    text: str
    kind: str  # "narration" | "dialogue"
    voice_note: str = ""
    scene_number: int = 0
    shot_id: Optional[str] = None
    line: int = 0
    speaker_id: str = ""  # CHARACTER block id, or "" for the narrator
    lip_sync: Optional[str] = None


@dataclass
class ScriptAudioCue:
    cue_type: str  # "SFX" | "AMBIENCE" | "BGM" | "MEME" | "VFX"
    name: str
    trigger: str = ""
    priority: str = ""
    mode: str = ""
    intensity: str = ""
    gain_db: Optional[float] = None
    scene_number: int = 0
    shot_id: Optional[str] = None
    line: int = 0
    source_key: str = ""  # original key as written, e.g. "MUSIC" for a BGM cue
    # Structured SFX sub-block fields (SPEC §6.6); empty for pipe-form cues.
    cue_id: str = ""
    event: str = ""
    cue_type_text: str = ""
    duration: str = ""  # verbatim, e.g. "0.4s"
    duration_mode: str = ""
    duration_seconds: Optional[float] = None


@dataclass
class StudioScriptShot:
    id: str
    line: int = 0
    type: str = ""  # normalized lower_snake SHOT_TYPES value; "" if missing/invalid
    type_raw: str = ""  # TYPE value exactly as written
    camera: str = ""
    camera_movement: Optional[str] = "STATIC"  # enum, or None for prose text
    camera_movement_text: str = ""  # CAMERA_MOVEMENT value verbatim
    subject: str = ""
    duration: str = "AUTO"
    duration_seconds: Optional[float] = None
    action: str = ""
    expression: str = ""
    vfx: List[str] = field(default_factory=list)
    voice_note: str = ""
    spoken_line_ids: List[str] = field(default_factory=list)
    location_override: Optional[str] = None
    trigger: str = ""  # TRIGGER value verbatim
    trigger_line_id: Optional[str] = None  # parsed LINE_ID ref, if any
    post_dialogue_pause: Optional[float] = None
    post_dialogue_pause_raw: str = ""
    end_hold: Optional[float] = None
    end_hold_raw: str = ""
    fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StudioScriptScene:
    number: int
    title: str = ""
    line: int = 0
    location_ref: Optional[str] = None  # LOCATION block id, when exact match
    location_text: str = ""  # inline free text when no LOCATION id matches
    time_of_day: str = ""
    mood: str = ""
    duration: str = "AUTO"
    duration_seconds: Optional[float] = None
    visual: str = ""
    actions: List[str] = field(default_factory=list)
    expressions: List[Dict[str, Any]] = field(default_factory=list)
    # Each expression: {"character": str|None, "expression": str, "line": int}
    camera: str = ""
    camera_movement: Optional[str] = "STATIC"  # enum, or None for prose text
    camera_movement_text: str = ""
    voice_note: str = ""
    meme_note: str = ""
    transition: str = "CUT"
    sfx_none: bool = False
    ambience_none: bool = False
    bgm_none: bool = False
    meme_none: bool = False
    shots: List[StudioScriptShot] = field(default_factory=list)
    spoken_lines: List[ScriptSpokenLine] = field(default_factory=list)
    audio_cues: List[ScriptAudioCue] = field(default_factory=list)
    vfx_cues: List[ScriptAudioCue] = field(default_factory=list)
    # New dialect: declared scene id ("SC01"), "" in the legacy dialect.
    id: str = ""
    characters: List[str] = field(default_factory=list)
    costume: str = ""
    fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GlobalAudio:
    narration_gain_db: float = 0.0
    dialogue_gain_db: float = 0.0
    ambience_gain_db: float = -18.0
    foley_gain_db: float = -12.0
    sfx_gain_db: float = -6.0
    bgm_gain_db: float = -18.0
    bgm_ducking_db: float = -6.0
    master_limit_db: float = -1.0
    buses: List[str] = field(default_factory=lambda: list(AUDIO_BUSES))
    # New-dialect GLOBAL_AUDIO fields verbatim (TTS_ENGINE, LANGUAGE, ...).
    fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QAConfig:
    min_score: float = 8.0
    require_technical: bool = True
    require_creative_review: bool = True
    language_gate: bool = True
    max_hard_fails: int = 0
    # New-dialect QA fields verbatim, plus parsed EXPECTED_* counts.
    fields: Dict[str, Any] = field(default_factory=dict)
    expected_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class OutputConfig:
    resolution: str = "1920x1080"
    fps: int = 24
    format: str = "MP4"
    draft_folder: str = "drive:drafts"
    master: str = "MANUAL_ONLY"
    # New-dialect OUTPUT fields verbatim (VIDEO_CODEC, EXPORT_*, DRIVE_*).
    fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EndCard:
    text: str = ""
    duration: float = 3.0
    style: str = ""
    line: int = 0
    background: str = ""
    secondary_text: str = ""
    text_language: str = ""
    bgm: str = ""
    sfx: str = ""
    duration_raw: str = ""
    duration_sec: float = 3.0  # parsed seconds; kept in sync with duration
    fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StudioScriptV1Document:
    # Absent PROJECT / GENRE / VISUAL_STYLE / TONE means "unspecified"
    # (SPEC §4): stored as None, never filled with upstream defaults.
    project: Optional[str] = None
    language: str = "vi-VN"
    genre: Optional[str] = None
    # STYLE and VISUAL_STYLE both map to this single field (SPEC §4
    # alias rule); there is no separate "style" field.
    visual_style: Optional[str] = None
    aspect_ratio: str = "16:9"
    target_duration: str = "AUTO"
    tone: Optional[str] = None
    meme_policy: str = "CONTEXTUAL"
    meme_max_per_minute: int = 2
    # First-person prerequisite rule (SPEC §1.2 principle 10, §16):
    # None when the document does not declare them (legacy dialect).
    storytelling_mode: Optional[str] = None
    primary_character: Optional[str] = None
    external_narrator: Optional[str] = None
    project_id: Optional[str] = None
    title: Optional[str] = None
    project_fields: Dict[str, Any] = field(default_factory=dict)
    visual_style_fields: Dict[str, Any] = field(default_factory=dict)
    target_duration_min: Optional[float] = None
    target_duration_max: Optional[float] = None
    # Source lines of the first-person declarations (for V1E018/V1E025).
    primary_character_line: int = 0
    external_narrator_line: int = 0
    characters: List[ScriptCharacter] = field(default_factory=list)
    locations: List[ScriptLocation] = field(default_factory=list)
    props: List[ScriptProp] = field(default_factory=list)
    scenes: List[StudioScriptScene] = field(default_factory=list)
    global_audio: GlobalAudio = field(default_factory=GlobalAudio)
    constraints: List[str] = field(default_factory=list)
    qa: QAConfig = field(default_factory=QAConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    end_card: Optional[EndCard] = None
    unsupported_fields: List[UnsupportedField] = field(default_factory=list)
    validation_errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    snapshot_hash: str = ""
    source_text: str = field(default="", repr=False)

    @property
    def is_valid(self) -> bool:
        return not self.validation_errors

    @property
    def spoken_lines(self) -> List[ScriptSpokenLine]:
        out: List[ScriptSpokenLine] = []
        for scene in self.scenes:
            out.extend(scene.spoken_lines)
        return out

    @property
    def audio_cues(self) -> List[ScriptAudioCue]:
        out: List[ScriptAudioCue] = []
        for scene in self.scenes:
            out.extend(scene.audio_cues)
        return out

    def get_character(self, name: str) -> Optional[ScriptCharacter]:
        """Case-insensitive lookup by declared character name OR block id."""
        wanted = _normalize_name(name)
        for char in self.characters:
            if _normalize_name(char.name) == wanted:
                return char
        for char in self.characters:
            if char.id and _normalize_name(char.id) == wanted:
                return char
        return None

    def get_location(self, location_id: str) -> Optional[ScriptLocation]:
        for loc in self.locations:
            if loc.id == location_id:
                return loc
        return None

    def to_dict(self) -> Dict[str, Any]:
        scenes_data = [asdict(s) for s in self.scenes]
        # Shots with no declared TYPE carry type=None (SPEC §5.5): the
        # new dialect allows CAMERA-only shots. Shots with an invalid
        # TYPE keep type "" with type_raw set (the document is invalid).
        for scene_data in scenes_data:
            for shot_data in scene_data["shots"]:
                if not shot_data["type"] and not shot_data["type_raw"]:
                    shot_data["type"] = None
        return {
            "format": "studio_script_v1",
            "snapshot_hash": self.snapshot_hash,
            "is_valid": self.is_valid,
            "meta": {
                "project": self.project,
                "language": self.language,
                "genre": self.genre,
                "visual_style": self.visual_style,
                "aspect_ratio": self.aspect_ratio,
                "target_duration": self.target_duration,
                "tone": self.tone,
                "meme_policy": self.meme_policy,
                "meme_max_per_minute": self.meme_max_per_minute,
                "storytelling_mode": self.storytelling_mode,
                "primary_character": self.primary_character,
                "external_narrator": self.external_narrator,
                "project_id": self.project_id,
                "title": self.title,
                "project_fields": dict(self.project_fields),
                "visual_style_fields": dict(self.visual_style_fields),
                "target_duration_min": self.target_duration_min,
                "target_duration_max": self.target_duration_max,
            },
            "characters": [asdict(c) for c in self.characters],
            "locations": [asdict(loc) for loc in self.locations],
            "props": [asdict(p) for p in self.props],
            "scenes": scenes_data,
            "global_audio": asdict(self.global_audio),
            "constraints": list(self.constraints),
            "qa": asdict(self.qa),
            "output": asdict(self.output),
            "end_card": asdict(self.end_card) if self.end_card else None,
            "unsupported_fields": [asdict(u) for u in self.unsupported_fields],
            "validation_errors": [asdict(e) for e in self.validation_errors],
            "warnings": [asdict(w) for w in self.warnings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    return " ".join(name.strip().casefold().split())


def _is_narrator_label(label: str) -> bool:
    return _normalize_name(label) in NARRATOR_ALIASES


def _split_list(value: str, sep: str = ";") -> List[str]:
    return [part.strip() for part in value.split(sep) if part.strip()]


def _normalize_enum_token(value: str) -> str:
    return re.sub(r"[\s\-]+", "_", value.strip()).upper()


def _normalize_shot_type(value: str) -> str:
    return re.sub(r"[\s\-]+", "_", value.strip()).lower()


def _parse_duration(
    value: str, line: int, errors: List[ValidationIssue], where: str
) -> tuple[str, Optional[float]]:
    """Return (verbatim duration string, seconds or None for AUTO).

    Accepts AUTO (case-insensitive) or a plain non-negative number of
    seconds. No unit suffix is defined: "12s" is V1E012 (SPEC §4).
    """
    raw = value.strip()
    if raw.upper() == "AUTO":
        return "AUTO", None
    m = _DURATION_RE.match(raw)
    if m:
        seconds = float(m.group(1))
        if seconds >= 0:
            return raw, seconds
    errors.append(ValidationIssue(
        line, "V1E012",
        f"{where}: DURATION must be AUTO or a plain non-negative number "
        f"of seconds (no unit suffix), got {raw!r}."))
    return raw, None


def _parse_target_duration(
    value: str, line: int, errors: List[ValidationIssue]
) -> tuple[str, Optional[float], Optional[float]]:
    """Parse TARGET_DURATION (SPEC §4): AUTO, a plain non-negative
    number, or a range such as "85–100 seconds" (en dash, em dash, or
    hyphen; optional "seconds"/"s" suffix). Returns (verbatim, min,
    max): min == max for a plain number, both None for AUTO. Anything
    else (including "30s") is V1E012."""
    raw = value.strip()
    if raw.upper() == "AUTO":
        return raw, None, None
    m = _DURATION_RE.match(raw)
    if m:
        seconds = float(m.group(1))
        if seconds >= 0:
            return raw, seconds, seconds
    m = _RANGE_DURATION_RE.match(raw)
    if m:
        low, high = float(m.group(1)), float(m.group(2))
        if low >= 0 and high >= low:
            return raw, low, high
    errors.append(ValidationIssue(
        line, "V1E012",
        "TARGET_DURATION must be AUTO, a plain non-negative number of "
        f"seconds, or a range such as '85–100 seconds', got {raw!r}."))
    return raw, None, None


def _parse_seconds(value: str) -> Optional[float]:
    """Parse a seconds value with an optional unit suffix ("0.6s", "3",
    "1.5 sec"). Returns None when unparseable; never raises."""
    m = _SECONDS_RE.match(value.strip())
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _strip_one_quote_layer(text: str) -> str:
    """Strip ONE layer of matching surrounding quotes (curly “ ”, ‘ ’,
    or straight " " / ' ') from spoken TEXT: values. Inner text is
    verbatim; unmatched or single-sided quotes are left alone."""
    stripped = text.strip()
    pairs = (("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'"))
    for opener, closer in pairs:
        if (len(stripped) >= 2 and stripped.startswith(opener)
                and stripped.endswith(closer)):
            return stripped[len(opener):len(stripped) - len(closer)]
    return stripped


def _parse_trigger_line_id(trigger: str) -> Optional[str]:
    """Parse the LINE_ID ref from a shot TRIGGER such as
    ``EP01_FP_01 — "Tiền…"``: the token before the first dash, when it
    looks like an id (no spaces). Returns None when there is no ref."""
    head = re.split(r"\s*[–—-]\s*", trigger.strip(), maxsplit=1)[0].strip()
    if head and " " not in head and "\t" not in head:
        return head
    return None


def _classify_camera_movement(value: str) -> tuple[Optional[str], bool]:
    """Classify a CAMERA_MOVEMENT value (SPEC §5.5/§6.5).

    Returns (enum_or_None, is_valid): an enum value (normalised) when
    the value matches the enum; None + valid when the value is prose
    (lowercase letters or spaces — descriptive movement text, kept
    verbatim in camera_movement_text); None + invalid when the value
    is an UPPER_SNAKE token that is not in the enum (a failed enum
    attempt, V1E007).
    """
    movement = _normalize_enum_token(value)
    if movement in CAMERA_MOVEMENTS:
        return movement, True
    raw = value.strip()
    if any(ch.islower() for ch in raw) or " " in raw:
        return None, True
    return None, False


def _split_csv(value: str) -> List[str]:
    """Split on commas and semicolons (new-dialect list fields)."""
    return [part.strip() for part in re.split(r"[,;]", value) if part.strip()]


def _is_character_key(key: str) -> bool:
    """CHARACTER vocabulary: the CHARACTER_KEYS table plus the
    COSTUME_* pattern (per-variant costume lists) and the
    HEIGHT_RATIO* pattern (scale-ratio traits), SPEC §5.1."""
    return (key in CHARACTER_KEYS or key.startswith("COSTUME_")
            or key.startswith("HEIGHT_RATIO"))


def _is_qa_key(key: str) -> bool:
    """QA vocabulary: the QA_KEYS table plus the MIN_*/TARGET_*/
    EXPECTED_* prefixes and *_CHECK/*_REVIEW suffixes (SPEC §5.8)."""
    return (key in QA_KEYS or key.startswith(("MIN_", "TARGET_", "EXPECTED_"))
            or key.endswith(("_CHECK", "_REVIEW")))


def _is_output_key(key: str) -> bool:
    """OUTPUT vocabulary: the OUTPUT_KEYS table plus EXPORT_* (SPEC §5.9)."""
    return key in OUTPUT_KEYS or key.startswith("EXPORT_")


def _uses_new_dialect(text: str) -> bool:
    """True when the document uses new-dialect markers (SPEC §3.3):
    a bare ``STUDIO SCRIPT V1`` line, a bare block header, a
    ``SCENE: <id>`` / ``SHOT: <id>`` header, or the ``END STUDIO SCRIPT
    V1`` terminator. New-dialect documents use the permissive rules
    (verbatim TRANSITION, TYPE optional with CAMERA, ``3s`` END_CARD
    durations); legacy documents keep the strict Phase A rules."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _BARE_MARKER_RE.match(line) or _TERMINATOR_RE.match(line):
            return True
        if line.upper() in BARE_BLOCK_HEADERS:
            return True
        if _SCENE_ID_RE.match(line) or _SHOT_COLON_RE.match(line):
            return True
    return False


def _parse_float(
    value: str, line: int, errors: List[ValidationIssue], code: str, where: str
) -> Optional[float]:
    try:
        return float(value.strip())
    except ValueError:
        errors.append(ValidationIssue(
            line, code, f"{where}: expected a number, got {value.strip()!r}."))
        return None


def _parse_bool(
    value: str, line: int, errors: List[ValidationIssue], where: str
) -> Optional[bool]:
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    errors.append(ValidationIssue(
        line, "V1E011",
        f"{where}: expected true/false, got {value.strip()!r}."))
    return None


def _parse_pipe_params(value: str) -> tuple[str, Dict[str, str], List[str], List[str]]:
    """Split ``Name | KEY: value | KEY: value`` into name, params, raw
    keys, and duplicate subkeys.

    The first segment is the name (verbatim). Later segments must be
    ``KEY: value``; the raw key list preserves order for diagnostics.
    A subkey appearing twice on one line is a duplicate (V1E006, SPEC
    §6): the FIRST value wins and the duplicate key is reported in the
    fourth return value, in order of repeat appearance.
    """
    segments = [seg.strip() for seg in value.split("|")]
    name = segments[0] if segments else ""
    params: Dict[str, str] = {}
    raw_keys: List[str] = []
    duplicates: List[str] = []
    for seg in segments[1:]:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", seg)
        if m:
            key = m.group(1).upper()
            raw_keys.append(key)
            if key in params:
                duplicates.append(key)
            else:
                params[key] = m.group(2).strip()
        elif seg:
            raw_keys.append(seg)
            params.setdefault("__unparsed__", seg)
    return name, params, raw_keys, duplicates


def detect_format(text: str) -> str:
    """Return "studio_v1" or "freeform" for the given script text.

    Studio V1 is detected by a ``# STUDIO SCRIPT V1`` marker line, by
    a ``PROJECT:`` header together with at least one ``SCENE <n>:``
    header, or by any new-dialect marker: a bare ``STUDIO SCRIPT V1``
    line, a bare ``PROJECT`` header, or a ``SCENE: <id>`` / ``SHOT:
    <id>`` header (SPEC §3.1). Anything else is free-form.
    """
    has_marker = False
    has_project = False
    has_scene = False
    for raw in text.splitlines():
        line = raw.strip()
        if _MARKER_RE.match(line) or _BARE_MARKER_RE.match(line):
            has_marker = True
        elif _PROJECT_RE.match(line):
            has_project = True
        elif _SCENE_RE.match(line):
            has_scene = True
        elif line.upper() == "PROJECT":
            return "studio_v1"
        elif _SCENE_ID_RE.match(line) or _SHOT_COLON_RE.match(line):
            return "studio_v1"
        if has_marker or (has_project and has_scene):
            return "studio_v1"
    return "freeform"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class StudioScriptV1Parser:
    """Line-based parser for STUDIO SCRIPT V1 documents.

    ``parse()`` never raises on invalid content (unless ``strict=True``);
    problems are collected in ``validation_errors`` / ``warnings`` on the
    returned document, each with a source line number and error code.
    """

    def parse(self, text: str, strict: bool = False) -> StudioScriptV1Document:
        doc = StudioScriptV1Document()
        doc.source_text = text
        doc.snapshot_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        errors = doc.validation_errors
        warnings = doc.warnings
        unsupported = doc.unsupported_fields

        # Per-parse state.
        context: Optional[str] = None  # character|location|prop|global_audio|constraints|qa|output|end_card|scene
        context_obj: Any = None
        current_scene: Optional[StudioScriptScene] = None
        current_shot: Optional[StudioScriptShot] = None
        current_voice_note = ""
        # STYLE / VISUAL_STYLE alias state (SPEC §4): (value, line) of the
        # first occurrence of each key, or None when absent.
        style_value: Optional[tuple[str, int]] = None
        visual_style_value: Optional[tuple[str, int]] = None
        seen_characters: Dict[str, int] = {}  # normalized name -> first line
        seen_locations: Dict[str, int] = {}  # normalized id -> first line
        seen_props: Dict[str, int] = {}  # normalized name -> first line
        seen_scenes: Dict[int, int] = {}  # scene number -> first line
        seen_scene_ids: Dict[str, int] = {}  # normalized scene id -> first line
        seen_headers: Dict[str, int] = {}  # header key -> first line
        seen_singletons: Dict[str, int] = {}  # singleton block -> first line
        # New-dialect detection is document-wide (SPEC §3.3): one
        # permissive/strict rule set applies to the whole document.
        is_new_dialect = _uses_new_dialect(text)
        terminated = False  # set by the END STUDIO SCRIPT V1 terminator
        # Pending new-dialect sub-blocks / bullet lists, flushed when
        # the next non-continuation line arrives (SPEC §§2.8, 6.1, 6.6).
        pending_spoken: Optional[Dict[str, Any]] = None
        pending_sfx: Optional[Dict[str, Any]] = None
        pending_holder: List[Optional[Dict[str, Any]]] = [None]
        # NONE-directive scope records for V1E024 (SPEC §10.2):
        # (scene_number, shot_id or None, cue_type, line).
        none_records: List[tuple] = []
        # Single-valued fields already seen in the current block, reset
        # on every block open (V1E006): key -> first line. Repeatable
        # fields (COSTUME_CHANGE for different scenes, ACTION, SFX, ...)
        # are never added here.
        block_seen: Dict[str, int] = {}
        # COSTUME_CHANGE scene numbers already used in the current
        # CHARACTER block (V1E006 on a repeat for the same scene).
        costume_scenes: set = set()
        # Single-valued scene/shot fields, keyed by id(scene)/id(shot)
        # (V1E006): field key -> first line. Scene TRANSITION values are
        # tracked separately because the same value in both positions
        # is allowed (§5.4).
        scene_seen: Dict[int, Dict[str, int]] = {}
        shot_seen: Dict[int, Dict[str, int]] = {}
        scene_transition: Dict[int, tuple[str, int]] = {}
        # Real (non-NONE) AMBIENCE / BGM / MEME cue counts per scene
        # (at most one per scene, V1E006, SPEC §§6.7-6.9). NONE lines do
        # not count here; NONE + real cues is V1E024 instead.
        scene_cue_counts: Dict[int, Dict[str, int]] = {}
        used_line_ids: Dict[str, int] = {}  # LINE_ID -> first line
        line_counter = [0]  # next auto LINE_ID number (mutable in closure)

        def error(line: int, code: str, message: str) -> None:
            errors.append(ValidationIssue(line, code, message))

        def dup_field(line: int, where: str, key: str, first_line: int) -> None:
            """Report a V1E006 duplicate; the FIRST value is kept."""
            error(line, "V1E006",
                  f"{where}: {key} appears more than once "
                  f"(first at line {first_line}); single-valued fields "
                  f"must appear at most once.")

        def note_unsupported(key: str, value: str, line: int) -> None:
            if context == "scene" and current_scene is not None:
                ctx = f"scene:{current_scene.number}"
                if current_shot is not None:
                    ctx = f"shot:{current_shot.id}"
            elif context == "character" and context_obj is not None:
                ctx = f"character:{context_obj.name}"
            elif context == "location" and context_obj is not None:
                ctx = f"location:{context_obj.id}"
            elif context == "prop" and context_obj is not None:
                ctx = f"prop:{context_obj.name}"
            elif context:
                ctx = context
            else:
                ctx = "document"
            unsupported.append(UnsupportedField(key, value, line, ctx))

        def next_line_id(explicit: Optional[str], line: int) -> str:
            if explicit:
                # SPEC §7.1: L-ids canonicalise (L2 -> L002); other
                # explicit ids (EP01_FP_01, ...) are kept verbatim.
                # Dedup is case-insensitive; the returned id is the
                # canonical form for L-ids and verbatim otherwise.
                m_canonical = re.match(r"^L(\d+)$", explicit, re.IGNORECASE)
                if m_canonical:
                    candidate = f"L{int(m_canonical.group(1)):03d}"
                else:
                    candidate = explicit
                dedup_key = candidate.upper()
                if dedup_key in used_line_ids:
                    error(line, "V1E005",
                          f"LINE_ID {candidate} was already used at line {used_line_ids[dedup_key]}.")
                else:
                    used_line_ids[dedup_key] = line
                return candidate
            while True:
                line_counter[0] += 1
                candidate = f"L{line_counter[0]:03d}"
                if candidate not in used_line_ids:
                    used_line_ids[candidate] = line
                    return candidate

        def add_spoken(speaker_label: str, text_value: str, kind_hint: str,
                       explicit_id: Optional[str], line: int,
                       lip_sync: Optional[str] = None) -> None:
            """Record a spoken line. Speaker resolution happens in the
            post-pass so characters declared after a scene still resolve."""
            nonlocal current_voice_note
            assert current_scene is not None
            line_id = next_line_id(explicit_id, line)
            if _is_narrator_label(speaker_label):
                speaker = NARRATOR_SPEAKER
                kind = "narration"
            else:
                speaker = speaker_label.strip()
                kind = kind_hint
            spoken = ScriptSpokenLine(
                line_id=line_id,
                speaker=speaker,
                text=text_value,
                kind=kind,
                voice_note=current_voice_note,
                scene_number=current_scene.number,
                shot_id=current_shot.id if current_shot else None,
                line=line,
                lip_sync=lip_sync,
            )
            # Production tags inside spoken text (upstream Rule 2).
            upper_text = text_value.upper()
            found = [tag for tag in PRODUCTION_TAGS_IN_SPEECH if tag in upper_text]
            if found:
                error(line, "V1E016",
                      f"Spoken line {line_id} contains production tag(s) "
                      f"{', '.join(found)}; production directives must never be spoken.")
            current_scene.spoken_lines.append(spoken)
            if current_shot is not None:
                current_shot.spoken_line_ids.append(line_id)

        def close_scene() -> None:
            nonlocal current_scene, current_shot, current_voice_note
            current_scene = None
            current_shot = None
            current_voice_note = ""
            pending_holder[0] = None

        def open_block(new_context: str, obj: Any) -> None:
            nonlocal context, context_obj, block_seen, costume_scenes
            close_scene()
            context = new_context
            context_obj = obj
            block_seen = {}
            costume_scenes = set()

        def record_field(fields: Dict[str, Any], key: str, value: str) -> None:
            """Record a verbatim field value. A repeated key accumulates
            a list (repeatable fields); single-valued keys are guarded
            by V1E006 before this is called, so repeats here are the
            repeatable forms (COSTUME_CHANGE, scene ACTION, ...)."""
            if key not in fields:
                fields[key] = value
            elif isinstance(fields[key], list):
                fields[key].append(value)
            else:
                fields[key] = [fields[key], value]

        def record_bullet(fields: Dict[str, Any], key: str, bullet: str) -> None:
            """Attach a bullet to a fields dict under ``key``. An
            empty-value key becomes a list; a key with an inline value
            becomes [inline, *bullets]; nothing is ever dropped."""
            if key not in fields or fields[key] == "":
                fields[key] = [bullet]
            elif isinstance(fields[key], list):
                fields[key].append(bullet)
            else:
                fields[key] = [fields[key], bullet]

        def flush_spoken() -> None:
            """Emit a pending NARRATION:/DIALOGUE: sub-block (SPEC §6.1).
            Missing TEXT is V1E019; a DIALOGUE sub-block without a
            SPEAKER is V1E019; a NARRATION sub-block without a SPEAKER
            is a narrator line (V1E025 in first-person documents, at
            finalization)."""
            nonlocal pending_spoken
            sub = pending_spoken
            pending_spoken = None
            if sub is None:
                return
            scene = sub["scene"]
            if scene is None:
                return
            text_value = sub.get("text")
            if text_value is None:
                error(sub["header_line"], "V1E019",
                      f"{sub['kind_key']}: sub-block has no TEXT: line.")
                return
            speaker = sub.get("speaker")
            if speaker is None and sub["kind_key"] == "DIALOGUE":
                error(sub["header_line"], "V1E019",
                      "DIALOGUE: sub-block has no SPEAKER: line.")
                return
            label = speaker if speaker is not None else NARRATOR_SPEAKER
            # add_spoken uses the live scene/shot globals; the sub-block
            # is flushed before any context change, so they still match.
            add_spoken(label, _strip_one_quote_layer(text_value),
                       sub["kind"], sub.get("line_id"),
                       sub.get("text_line", sub["header_line"]),
                       lip_sync=sub.get("lip_sync"))

        def flush_sfx() -> None:
            """Emit a pending structured SFX: sub-block (SPEC §6.6) as
            one audio cue. An empty sub-block contributes no cue."""
            nonlocal pending_sfx
            sub = pending_sfx
            pending_sfx = None
            if sub is None:
                return
            fields = sub["subfields"]
            if not fields:
                return
            duration_raw = fields.get("DURATION", "")
            scene = sub["scene"]
            cue = ScriptAudioCue(
                cue_type="SFX",
                name=fields.get("EVENT", fields.get("ID", "")),
                trigger=fields.get("TRIGGER", ""),
                priority=fields.get("PRIORITY", ""),
                intensity=fields.get("INTENSITY", ""),
                scene_number=scene.number,
                shot_id=sub["shot_id"],
                line=sub["header_line"],
                source_key="SFX",
                cue_id=fields.get("ID", ""),
                event=fields.get("EVENT", ""),
                cue_type_text=fields.get("TYPE", ""),
                duration=duration_raw,
                duration_mode=fields.get("DURATION_MODE", ""),
                duration_seconds=_parse_seconds(duration_raw) if duration_raw else None,
            )
            scene.audio_cues.append(cue)

        def attach_bullet(bullet_text: str, lineno: int) -> None:
            """Route one bullet line (SPEC §2.8). SFX sub-block bullets
            parse as sub-fields; other bullets attach to the preceding
            KEY: field (list value) or block list; bullets with no
            attachable context become unsupported_fields entries."""
            if pending_sfx is not None:
                m_sub = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$",
                                 bullet_text)
                if m_sub:
                    subkey = m_sub.group(1).upper()
                    subvalue = m_sub.group(2).strip()
                    if subkey in pending_sfx["subfields"]:
                        error(lineno, "V1E006",
                              f"SFX: subkey {subkey} appears more than once "
                              f"in one SFX sub-block; a subkey must appear "
                              f"at most once.")
                    else:
                        pending_sfx["subfields"][subkey] = subvalue
                else:
                    note_unsupported("SFX", bullet_text, lineno)
                return
            target = pending_holder[0]
            if target is not None:
                record_bullet(target["fields"], target["key"], bullet_text)
                kind = target["kind"]
                if kind == "scene_action":
                    target["scene"].actions.append(bullet_text)
                elif kind == "shot_action":
                    shot = target["shot"]
                    items = target["fields"][target["key"]]
                    shot.action = " ".join(items)
                elif kind == "shot_vfx":
                    target["shot"].vfx.append(bullet_text)
                elif kind == "scene_vfx":
                    scene = target["scene"]
                    scene.vfx_cues.append(ScriptAudioCue(
                        cue_type="VFX", name=bullet_text,
                        scene_number=scene.number,
                        shot_id=None, line=lineno, source_key="VFX"))
                elif kind == "location_list":
                    loc = target["location"]
                    key = target["key"]
                    if key in ("FEATURES", "DISTINCTIVE_FEATURES"):
                        loc.features.append(bullet_text)
                    elif key in ("PALETTE", "COLOR_PALETTE"):
                        loc.palette.extend(_split_csv(bullet_text))
                    elif key == "FORBIDDEN":
                        loc.forbidden.append(bullet_text)
                    elif key in ("FOREGROUND", "MIDGROUND", "BACKGROUND"):
                        attr = key.lower()
                        current = getattr(loc, attr)
                        if current == "":
                            setattr(loc, attr, [bullet_text])
                        elif isinstance(current, list):
                            current.append(bullet_text)
                        else:
                            setattr(loc, attr, [current, bullet_text])
                elif kind == "character_traits":
                    target["character"].traits.append(bullet_text)
                elif kind == "prop_interactions":
                    target["prop"].interactions.extend(
                        _split_csv(bullet_text))
                return
            if context == "constraints":
                doc.constraints.append(bullet_text)
                return
            note_unsupported("BULLET", bullet_text, lineno)

        def check_dup_subkeys(cue_key: str, duplicates: List[str], line: int) -> None:
            for subkey in duplicates:
                error(line, "V1E006",
                      f"{cue_key}: subkey {subkey} appears more than once "
                      f"on one line; a subkey must appear at most once.")

        def check_none_segments(cue_key: str, name: str, raw_keys: List[str],
                                line: int) -> bool:
            """True when this is a NONE directive. A NONE line carrying
            pipe segments is V1E021 (SPEC §6.6); the NONE flag is still
            recorded. TRIGGER values are recorded verbatim at parse time:
            V1E022 is raised at the timeline stage, never here."""
            if name.upper() != "NONE":
                return False
            if raw_keys:
                error(line, "V1E021",
                      f"{cue_key}: NONE must not carry pipe segments "
                      f"(got {', '.join(raw_keys)}); write '{cue_key}: NONE' alone.")
            return True

        def check_single_cue(cue_key: str, scene: StudioScriptScene, line: int) -> None:
            """At most one real AMBIENCE / BGM / MEME cue per SCOPE
            (V1E006, SPEC §§6.7-6.9): one per scene for scene-level
            lines, one per shot for shot-level lines. Cues in
            different shots of one scene do not conflict. The cue is
            still recorded."""
            scope = (id(scene), current_shot.id if current_shot else None)
            counts = scene_cue_counts.setdefault(scope, {})
            counts[cue_key] = counts.get(cue_key, 0) + 1
            if counts[cue_key] > 1:
                where = (f"SHOT {current_shot.id} in SCENE {scene.number}"
                         if current_shot is not None
                         else f"SCENE {scene.number}")
                error(line, "V1E006",
                      f"{where}: at most one {cue_key} line per "
                      f"{'shot' if current_shot is not None else 'scene'} "
                      f"(BGM and MUSIC share one slot); this is "
                      f"the {counts[cue_key]}th.")

        # -- cue parsers (scene context) -----------------------------------

        def add_sfx(value: str, line: int) -> None:
            assert current_scene is not None
            name, params, raw_keys, duplicates = _parse_pipe_params(value)
            check_dup_subkeys("SFX", duplicates, line)
            if check_none_segments("SFX", name, raw_keys, line):
                current_scene.sfx_none = True
                none_records.append((current_scene.number,
                                     current_shot.id if current_shot else None,
                                     "SFX", line))
                return
            priority = params.get("PRIORITY", "REQUIRED")
            priority_norm = _normalize_enum_token(priority)
            if priority_norm not in PRIORITIES:
                error(line, "V1E007",
                      f"SFX priority must be one of {', '.join(PRIORITIES)}, got {priority!r}.")
                priority_norm = "REQUIRED"
            cue = ScriptAudioCue(
                cue_type="SFX", name=name, trigger=params.get("TRIGGER", ""),
                priority=priority_norm, scene_number=current_scene.number,
                shot_id=current_shot.id if current_shot else None,
                line=line, source_key="SFX")
            for key in params:
                if key not in ("TRIGGER", "PRIORITY"):
                    note_unsupported(f"SFX.{key}", params[key], line)
            current_scene.audio_cues.append(cue)

        def add_ambience(value: str, line: int) -> None:
            assert current_scene is not None
            name, params, raw_keys, duplicates = _parse_pipe_params(value)
            check_dup_subkeys("AMBIENCE", duplicates, line)
            if check_none_segments("AMBIENCE", name, raw_keys, line):
                current_scene.ambience_none = True
                none_records.append((current_scene.number,
                                     current_shot.id if current_shot else None,
                                     "AMBIENCE", line))
                return
            check_single_cue("AMBIENCE", current_scene, line)
            mode = _normalize_enum_token(params.get("MODE", "LOOP"))
            if mode not in AMBIENCE_MODES:
                error(line, "V1E007",
                      f"AMBIENCE MODE must be one of {', '.join(AMBIENCE_MODES)}, got {params.get('MODE')!r}.")
                mode = "LOOP"
            cue = ScriptAudioCue(
                cue_type="AMBIENCE", name=name, mode=mode,
                scene_number=current_scene.number,
                shot_id=current_shot.id if current_shot else None,
                line=line, source_key="AMBIENCE")
            for key in params:
                if key != "MODE":
                    note_unsupported(f"AMBIENCE.{key}", params[key], line)
            current_scene.audio_cues.append(cue)

        def add_bgm(value: str, line: int, source_key: str) -> None:
            assert current_scene is not None
            name, params, raw_keys, duplicates = _parse_pipe_params(value)
            check_dup_subkeys(source_key, duplicates, line)
            if check_none_segments(source_key, name, raw_keys, line):
                current_scene.bgm_none = True
                none_records.append((current_scene.number,
                                     current_shot.id if current_shot else None,
                                     "BGM", line))
                return
            check_single_cue("BGM", current_scene, line)
            intensity = _normalize_enum_token(params.get("INTENSITY", "MEDIUM"))
            if intensity not in INTENSITIES:
                error(line, "V1E007",
                      f"BGM INTENSITY must be one of {', '.join(INTENSITIES)}, got {params.get('INTENSITY')!r}.")
                intensity = "MEDIUM"
            cue = ScriptAudioCue(
                cue_type="BGM", name=name, intensity=intensity,
                scene_number=current_scene.number,
                shot_id=current_shot.id if current_shot else None,
                line=line, source_key=source_key)
            for key in params:
                if key != "INTENSITY":
                    note_unsupported(f"BGM.{key}", params[key], line)
            current_scene.audio_cues.append(cue)

        def add_meme(value: str, line: int) -> None:
            assert current_scene is not None
            name, params, raw_keys, duplicates = _parse_pipe_params(value)
            check_dup_subkeys("MEME", duplicates, line)
            if check_none_segments("MEME", name, raw_keys, line):
                current_scene.meme_none = True
                none_records.append((current_scene.number,
                                     current_shot.id if current_shot else None,
                                     "MEME", line))
                return
            check_single_cue("MEME", current_scene, line)
            priority = _normalize_enum_token(params.get("PRIORITY", "OPTIONAL"))
            if priority not in PRIORITIES:
                error(line, "V1E007",
                      f"MEME priority must be one of {', '.join(PRIORITIES)}, got {params.get('PRIORITY')!r}.")
                priority = "OPTIONAL"
            gain_db: Optional[float] = None
            if "GAIN_DB" in params:
                gain_db = _parse_float(params["GAIN_DB"], line, errors,
                                       "V1E008", "MEME GAIN_DB")
            cue = ScriptAudioCue(
                cue_type="MEME", name=name, trigger=params.get("TRIGGER", ""),
                priority=priority, gain_db=gain_db,
                scene_number=current_scene.number,
                shot_id=current_shot.id if current_shot else None,
                line=line, source_key="MEME")
            for key in params:
                if key not in ("TRIGGER", "PRIORITY", "GAIN_DB"):
                    note_unsupported(f"MEME.{key}", params[key], line)
            current_scene.audio_cues.append(cue)

        def add_vfx(value: str, line: int) -> None:
            assert current_scene is not None
            name_part, params, _raw_keys, duplicates = _parse_pipe_params(value)
            check_dup_subkeys("VFX", duplicates, line)
            trigger = params.get("TRIGGER", "")
            for key in params:
                if key != "TRIGGER":
                    note_unsupported(f"VFX.{key}", params[key], line)
            names = _split_list(name_part, ";")
            # One VFX cue name may carry TRIGGER; multiple ";"-separated
            # names combined with one TRIGGER is V1E019 (SPEC §6.10).
            if trigger and len(names) > 1:
                error(line, "V1E019",
                      f"VFX: {len(names)} names ({', '.join(names)}) combined "
                      f"with one TRIGGER; a TRIGGER applies to a single "
                      f"named effect — use one VFX line per triggered effect.")
            for name in names:
                current_scene.vfx_cues.append(ScriptAudioCue(
                    cue_type="VFX", name=name, trigger=trigger,
                    scene_number=current_scene.number,
                    shot_id=current_shot.id if current_shot else None,
                    line=line, source_key="VFX"))

        # -- main line loop -------------------------------------------------

        for lineno, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip().lstrip("\ufeff")
            if not line or line.startswith("#"):
                continue

            upper = line.upper()

            # Terminator (SPEC §2.3): END STUDIO SCRIPT V1 ends the
            # document. Non-blank, non-comment content after it is a
            # validation error (V1E019) and is not parsed.
            if _TERMINATOR_RE.match(line):
                flush_spoken()
                flush_sfx()
                terminated = True
                close_scene()
                context = None
                context_obj = None
                continue
            if terminated:
                error(lineno, "V1E019",
                      f"Content after 'END STUDIO SCRIPT V1' is not allowed: {line!r}.")
                continue

            # Bare format marker and ⸻ separator lines (SPEC §§2.3,
            # 2.8): skipped, never content and never errors. A
            # separator flushes pending sub-blocks and bullet lists.
            if _BARE_MARKER_RE.match(line):
                continue
            if _SEPARATOR_RE.match(line):
                flush_spoken()
                flush_sfx()
                pending_holder[0] = None
                continue

            # Pending sub-block continuations (SPEC §§2.8, 6.1, 6.6).
            # A bullet line continues a pending SFX sub-block or bullet
            # list; a SPEAKER:/LINE_ID:/TEXT:/LIP_SYNC: line continues
            # a pending spoken sub-block. Any other line flushes both.
            m_bullet = _BULLET_RE.match(line)
            m_sub_cont = None
            if pending_spoken is not None and context == "scene":
                m_sub_cont = re.match(
                    r"^(SPEAKER|LINE_ID|TEXT|LIP_SYNC)\s*:\s*(.*)$",
                    line, re.IGNORECASE)
            if m_bullet:
                if pending_spoken is not None:
                    flush_spoken()
                attach_bullet(m_bullet.group(1).strip(), lineno)
                continue
            if m_sub_cont is not None:
                subkey = m_sub_cont.group(1).upper()
                subvalue = m_sub_cont.group(2).strip()
                if subkey == "SPEAKER":
                    pending_spoken["speaker"] = subvalue
                elif subkey == "LINE_ID":
                    pending_spoken["line_id"] = subvalue
                elif subkey == "TEXT":
                    pending_spoken["text"] = subvalue
                    pending_spoken["text_line"] = lineno
                elif subkey == "LIP_SYNC":
                    pending_spoken["lip_sync"] = subvalue
                continue
            flush_spoken()
            flush_sfx()
            # A non-bullet line ends any pending bullet list, unless
            # the line itself opens one (handled by the dispatch below).
            pending_holder[0] = None

            # Legacy terminators: accepted and ignored.
            if upper.rstrip(":") in ("END_SCENE", "END_SCRIPT"):
                if upper.rstrip(":") == "END_SCENE":
                    close_scene()
                    context = None
                    context_obj = None
                else:
                    close_scene()
                    context = None
                    context_obj = None
                continue

            # SCENE headers: legacy "SCENE <n>: <title>" and new-dialect
            # "SCENE: <id>" (SPEC §5.4). Valid headers are recognised
            # before the malformed-header checks below.
            m_scene = _SCENE_RE.match(line)
            m_scene_id = None if m_scene else _SCENE_ID_RE.match(line)
            if m_scene or m_scene_id:
                if m_scene:
                    number = int(m_scene.group(1))
                    scene_id = ""
                    scene_title = m_scene.group(2).strip()
                    if number in seen_scenes:
                        error(lineno, "V1E003",
                              f"SCENE {number} was already declared at line {seen_scenes[number]}.")
                    else:
                        seen_scenes[number] = lineno
                else:
                    scene_id = m_scene_id.group(1)
                    # New-dialect scene number: 1-based ordinal.
                    number = (max(seen_scenes) + 1) if seen_scenes else 1
                    scene_title = ""
                    norm_id = _normalize_name(scene_id)
                    if norm_id in seen_scene_ids:
                        error(lineno, "V1E003",
                              f"SCENE {scene_id!r} was already declared at line {seen_scene_ids[norm_id]}.")
                    else:
                        seen_scene_ids[norm_id] = lineno
                    seen_scenes[number] = lineno
                current_scene = StudioScriptScene(
                    number=number, title=scene_title, line=lineno, id=scene_id)
                doc.scenes.append(current_scene)
                current_shot = None
                current_voice_note = ""
                context = "scene"
                context_obj = current_scene
                continue

            # Malformed SCENE / SHOT header attempts (V1E019, SPEC §§2.3,
            # 8.2): a SCENE header without a number or id, or a SHOT
            # header without an id.
            if re.match(r"^SCENE\s*:", line, re.IGNORECASE):
                error(lineno, "V1E019",
                      f"Malformed SCENE header {line!r}: expected 'SCENE <n>: <title>' or 'SCENE: <id>'.")
                continue
            if re.match(r"^SCENE\s+\S", line, re.IGNORECASE):
                error(lineno, "V1E019",
                      f"Malformed SCENE header {line!r}: expected 'SCENE <n>: <title>' or 'SCENE: <id>'.")
                continue
            if re.match(r"^SHOT\s*:\s*$", line, re.IGNORECASE):
                error(lineno, "V1E019",
                      "SHOT header is missing its id: expected 'SHOT <id>:' or 'SHOT: <id>'.")
                continue

            # SHOT headers: legacy "SHOT <id>:" and new-dialect
            # "SHOT: <id>" (SPEC §5.5), inside a scene only.
            m_shot = _SHOT_RE.match(line) if upper.startswith("SHOT") else None
            m_shot_colon = None if m_shot else _SHOT_COLON_RE.match(line)
            if m_shot or m_shot_colon:
                shot_id = (m_shot.group(1).strip() if m_shot
                           else m_shot_colon.group(1).strip())
                if current_scene is None:
                    error(lineno, "V1E019",
                          f"SHOT {shot_id} appears outside any SCENE.")
                    continue
                if any(s.id == shot_id for s in current_scene.shots):
                    error(lineno, "V1E004",
                          f"SHOT {shot_id} is declared more than once in SCENE {current_scene.number}.")
                current_shot = StudioScriptShot(id=shot_id, line=lineno)
                current_scene.shots.append(current_shot)
                continue
            if re.match(r"^SHOT\s*:\s*\S", line, re.IGNORECASE):
                error(lineno, "V1E019",
                      f"Malformed SHOT header {line!r}: expected 'SHOT <id>:' or 'SHOT: <id>'.")
                continue

            # Spoken / SFX sub-block openers (SPEC §§6.1, 6.6): an empty
            # NARRATION:/DIALOGUE: line or an empty SFX: line inside a
            # scene opens a sub-block instead of erroring.
            if context == "scene" and current_scene is not None:
                m_spoken_open = re.match(
                    r"^(NARRATION|DIALOGUE)\s*:\s*$", line, re.IGNORECASE)
                if m_spoken_open:
                    kind_key = m_spoken_open.group(1).upper()
                    pending_spoken = {
                        "kind_key": kind_key,
                        "kind": "narration" if kind_key == "NARRATION" else "dialogue",
                        "header_line": lineno,
                        "scene": current_scene,
                        "speaker": None,
                        "line_id": None,
                        "text": None,
                        "text_line": lineno,
                        "lip_sync": None,
                    }
                    continue
                if re.match(r"^SFX\s*:\s*$", line, re.IGNORECASE):
                    pending_sfx = {
                        "header_line": lineno,
                        "scene": current_scene,
                        "shot_id": current_shot.id if current_shot else None,
                        "subfields": {},
                    }
                    continue

            # Bare block headers (SPEC §2.3): PROJECT, VISUAL_STYLE,
            # GLOBAL_AUDIO, GLOBAL_NEGATIVE_CONSTRAINTS, QA, OUTPUT,
            # END_CARD without a colon. The colon forms remain valid.
            if upper in BARE_BLOCK_HEADERS:
                block = upper
                if block in seen_singletons:
                    error(lineno, "V1E006",
                          f"{block} block appears more than once "
                          f"(first at line {seen_singletons[block]}); "
                          f"at most one {block} block per document.")
                else:
                    seen_singletons[block] = lineno
                if block == "PROJECT":
                    open_block("project", None)
                elif block == "VISUAL_STYLE":
                    open_block("visual_style", None)
                elif block == "GLOBAL_AUDIO":
                    open_block("global_audio", doc.global_audio)
                elif block == "GLOBAL_NEGATIVE_CONSTRAINTS":
                    open_block("constraints", None)
                elif block == "QA":
                    open_block("qa", doc.qa)
                elif block == "OUTPUT":
                    open_block("output", doc.output)
                elif block == "END_CARD":
                    card = EndCard(line=lineno)
                    doc.end_card = card
                    open_block("end_card", card)
                continue

            # Empty PROJECT: / VISUAL_STYLE: headers open the block
            # form (SPEC §§4.1–4.2); non-empty values stay header keys.
            m_empty_block = re.match(
                r"^(PROJECT|VISUAL_STYLE)\s*:\s*$", line, re.IGNORECASE)
            if m_empty_block:
                block = m_empty_block.group(1).upper()
                if block in seen_singletons:
                    error(lineno, "V1E006",
                          f"{block} block appears more than once "
                          f"(first at line {seen_singletons[block]}); "
                          f"at most one {block} block per document.")
                else:
                    seen_singletons[block] = lineno
                if block == "PROJECT":
                    open_block("project", None)
                else:
                    open_block("visual_style", None)
                continue

            # Block headers that are never scene fields.
            m_block = re.match(
                r"^(CHARACTER|LOCATION|PROP|GLOBAL_AUDIO|GLOBAL_NEGATIVE_CONSTRAINTS|QA|OUTPUT|END_CARD)\s*:\s*(.*)$",
                line, re.IGNORECASE)
            if m_block:
                block = m_block.group(1).upper()
                rest = m_block.group(2).strip()
                # LOCATION: inside a scene is a scene field, not a block.
                if block == "LOCATION" and context == "scene" and current_scene is not None:
                    pass  # fall through to scene-field handling below
                else:
                    if block in ("CHARACTER", "LOCATION", "PROP") and not rest:
                        error(lineno, "V1E019",
                              f"{block} header is missing its name/id: "
                              f"expected '{block}: <name>'.")
                        continue
                    if block in ("GLOBAL_AUDIO", "GLOBAL_NEGATIVE_CONSTRAINTS",
                                 "QA", "OUTPUT", "END_CARD"):
                        if block in seen_singletons:
                            error(lineno, "V1E006",
                                  f"{block} block appears more than once "
                                  f"(first at line {seen_singletons[block]}); "
                                  f"at most one {block} block per document.")
                        else:
                            seen_singletons[block] = lineno
                    if block == "CHARACTER":
                        char = ScriptCharacter(name=rest, line=lineno, id=rest)
                        norm = _normalize_name(rest)
                        if norm in seen_characters:
                            error(lineno, "V1E001",
                                  f"CHARACTER {rest!r} was already declared at line {seen_characters[norm]}.")
                        else:
                            seen_characters[norm] = lineno
                        doc.characters.append(char)
                        open_block("character", char)
                    elif block == "LOCATION":
                        loc = ScriptLocation(id=rest, line=lineno)
                        norm = _normalize_name(rest)
                        if norm in seen_locations:
                            error(lineno, "V1E002",
                                  f"LOCATION {rest!r} was already declared at line {seen_locations[norm]}.")
                        else:
                            seen_locations[norm] = lineno
                        doc.locations.append(loc)
                        open_block("location", loc)
                    elif block == "PROP":
                        prop = ScriptProp(name=rest, line=lineno, id=rest)
                        norm = _normalize_name(rest)
                        if norm in seen_props:
                            error(lineno, "V1E001",
                                  f"PROP {rest!r} was already declared at line {seen_props[norm]}.")
                        else:
                            seen_props[norm] = lineno
                        doc.props.append(prop)
                        open_block("prop", prop)
                    elif block == "GLOBAL_AUDIO":
                        open_block("global_audio", doc.global_audio)
                    elif block == "GLOBAL_NEGATIVE_CONSTRAINTS":
                        open_block("constraints", None)
                    elif block == "QA":
                        open_block("qa", doc.qa)
                    elif block == "OUTPUT":
                        open_block("output", doc.output)
                    elif block == "END_CARD":
                        card = EndCard(line=lineno)
                        doc.end_card = card
                        open_block("end_card", card)
                    continue

            # Header keys (only outside any block/scene).
            m_header = re.match(
                r"^(PROJECT|LANGUAGE|GENRE|STYLE|VISUAL_STYLE|ASPECT_RATIO|TARGET_DURATION|TONE|MEME_POLICY|MEME_MAX_PER_MINUTE)\s*:\s*(.*)$",
                line, re.IGNORECASE)
            if m_header and context is None:
                key = m_header.group(1).upper()
                value = m_header.group(2).strip()
                if key in seen_headers:
                    dup_field(lineno, "Header", key, seen_headers[key])
                    continue
                seen_headers[key] = lineno
                if key == "PROJECT":
                    doc.project = value
                elif key == "LANGUAGE":
                    doc.language = value
                elif key == "GENRE":
                    doc.genre = value
                elif key in ("STYLE", "VISUAL_STYLE"):
                    # SPEC §4 alias rule: both keys map to the single
                    # field visual_style. VISUAL_STYLE wins on a
                    # conflict; the STYLE loser is recorded under §8.3
                    # with its line number. Equal values: no loser.
                    if key == "STYLE":
                        style_value = (value, lineno)
                        if visual_style_value is None:
                            doc.visual_style = value
                        elif visual_style_value[0] != value:
                            note_unsupported("STYLE", value, lineno)
                    else:
                        visual_style_value = (value, lineno)
                        if style_value is not None and style_value[0] != value:
                            doc.visual_style = value
                            note_unsupported("STYLE", style_value[0], style_value[1])
                        else:
                            doc.visual_style = value
                elif key == "ASPECT_RATIO":
                    if value not in ASPECT_RATIOS:
                        error(lineno, "V1E007",
                              f"ASPECT_RATIO must be one of {', '.join(ASPECT_RATIOS)}, got {value!r}.")
                    else:
                        doc.aspect_ratio = value
                elif key == "TARGET_DURATION":
                    (doc.target_duration, doc.target_duration_min,
                     doc.target_duration_max) = _parse_target_duration(
                        value, lineno, errors)
                elif key == "TONE":
                    doc.tone = value
                elif key == "MEME_POLICY":
                    policy = value.upper()
                    if policy not in MEME_POLICIES:
                        error(lineno, "V1E007",
                              f"MEME_POLICY must be one of {', '.join(MEME_POLICIES)}, got {value!r}.")
                    else:
                        doc.meme_policy = policy
                elif key == "MEME_MAX_PER_MINUTE":
                    try:
                        parsed = int(value)
                        if parsed < 0:
                            raise ValueError
                        doc.meme_max_per_minute = parsed
                    except ValueError:
                        error(lineno, "V1E008",
                              f"MEME_MAX_PER_MINUTE must be a non-negative integer, got {value!r}.")
                continue

            # -- context-specific field handling ---------------------------

            if context == "character" and isinstance(context_obj, ScriptCharacter):
                char = context_obj
                m_field = _KEY_VALUE_RE.match(line)
                field_key = (m_field.group(1).strip().upper()
                             if m_field else "")
                if m_field and _is_character_key(field_key):
                    key = field_key
                    value = m_field.group(2).strip()
                    # COSTUME_CHANGE is repeatable (different scenes);
                    # every other CHARACTER field is single-valued.
                    # Duplicate detection is per-block-context (SPEC
                    # §8.2): the same key in another block is legal.
                    if key != "COSTUME_CHANGE":
                        if key in block_seen:
                            dup_field(lineno, f"CHARACTER {char.name!r}", key,
                                      block_seen[key])
                            continue
                        block_seen[key] = lineno
                    record_field(char.fields, key, value)
                    if key == "NAME":
                        if value:
                            char.name = value
                    elif key == "ROLE":
                        char.role = value
                    elif key == "APPEARANCE":
                        char.appearance = value
                    elif key == "TRAITS":
                        char.traits = _split_list(value)
                    elif key == "COSTUME":
                        char.costume = value
                    elif key == "COSTUME_CHANGE":
                        m_cc = _COSTUME_CHANGE_RE.match(value)
                        if m_cc:
                            scene_no = int(m_cc.group(1))
                            if scene_no in costume_scenes:
                                error(lineno, "V1E006",
                                      f"COSTUME_CHANGE for {char.name!r} repeats "
                                      f"SCENE {scene_no}; at most one costume "
                                      f"change per scene per character.")
                            else:
                                costume_scenes.add(scene_no)
                                char.costume_changes.append({
                                    "scene_number": scene_no,
                                    "outfit": m_cc.group(2).strip(),
                                    "line": lineno,
                                })
                        else:
                            error(lineno, "V1E019",
                                  f"COSTUME_CHANGE must use the form 'SCENE <n>: <outfit>', got {value!r}.")
                    elif key == "VOICE":
                        char.voice = value
                    elif key == "VOICE_STYLE":
                        char.voice_style = value
                    elif key == "HEAD_RATIO":
                        parsed = _parse_float(value, lineno, errors,
                                              "V1E008", "HEAD_RATIO")
                        if parsed is not None:
                            char.head_ratio = parsed
                            if not (HEAD_RATIO_MIN <= parsed <= HEAD_RATIO_MAX):
                                error(lineno, "V1E009",
                                      f"HEAD_RATIO {parsed} is outside the locked range "
                                      f"{HEAD_RATIO_MIN}-{HEAD_RATIO_MAX} (default {HEAD_RATIO_DEFAULT}).")
                    elif key == "IDENTITY_ID":
                        char.identity_id = value
                    if not value:
                        # An empty-valued key opens a bullet list (§2.8).
                        pending_holder[0] = {
                            "kind": ("character_traits"
                                     if key == "TRAITS" else "fields"),
                            "key": key, "fields": char.fields,
                            "character": char,
                        }
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "location" and isinstance(context_obj, ScriptLocation):
                loc = context_obj
                m_field = _KEY_VALUE_RE.match(line)
                field_key = (m_field.group(1).strip().upper()
                             if m_field else "")
                if m_field and field_key in LOCATION_KEYS:
                    key = field_key
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, f"LOCATION {loc.id!r}", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
                    record_field(loc.fields, key, value)
                    if key == "NAME":
                        loc.name = value
                    elif key == "PERIOD":
                        loc.period = value
                    elif key == "GEOGRAPHY":
                        loc.geography = value
                    elif key == "ARCHITECTURE":
                        loc.architecture = value
                    elif key == "FEATURES":
                        loc.features = _split_list(value)
                    elif key == "DISTINCTIVE_FEATURES":
                        if value:
                            loc.features = _split_list(value)
                    elif key == "FOREGROUND":
                        if value:
                            loc.foreground = value
                    elif key == "MIDGROUND":
                        if value:
                            loc.midground = value
                    elif key == "BACKGROUND":
                        if value:
                            loc.background = value
                    elif key == "LIGHTING":
                        loc.lighting = value
                    elif key == "WEATHER":
                        loc.weather = value
                    elif key == "PALETTE":
                        loc.palette = _split_list(value)
                    elif key == "COLOR_PALETTE":
                        if value:
                            loc.palette = _split_csv(value)
                    elif key == "FORBIDDEN":
                        loc.forbidden = _split_list(value)
                    elif key == "TYPE":
                        loc.type = value
                    if not value:
                        pending_holder[0] = {
                            "kind": ("location_list" if key in (
                                "FEATURES", "DISTINCTIVE_FEATURES", "PALETTE",
                                "COLOR_PALETTE", "FORBIDDEN", "FOREGROUND",
                                "MIDGROUND", "BACKGROUND") else "fields"),
                            "key": key, "fields": loc.fields,
                            "location": loc,
                        }
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "prop" and isinstance(context_obj, ScriptProp):
                prop = context_obj
                m_field = _KEY_VALUE_RE.match(line)
                field_key = (m_field.group(1).strip().upper()
                             if m_field else "")
                if m_field and field_key in PROP_KEYS:
                    key = field_key
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, f"PROP {prop.name!r}", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
                    record_field(prop.fields, key, value)
                    if key == "NAME":
                        prop.name = value
                    elif key == "DESCRIPTION":
                        prop.description = value
                    elif key == "OWNER":
                        prop.owner = value
                    elif key == "SCENES":
                        if value.upper() == "ALL":
                            prop.all_scenes = True
                            prop.scenes = []
                        else:
                            parsed_scenes: List[int] = []
                            bad = False
                            for part in value.split(","):
                                part = part.strip()
                                if not part:
                                    continue
                                try:
                                    parsed_scenes.append(int(part))
                                except ValueError:
                                    bad = True
                            if bad:
                                error(lineno, "V1E019",
                                      f"PROP SCENES must be ALL or a comma list of scene numbers, got {value!r}.")
                            else:
                                prop.scenes = parsed_scenes
                    elif key == "INTERACTION":
                        prop.interactions = _split_csv(value)
                    elif key == "TYPE":
                        prop.type = value
                    if not value:
                        pending_holder[0] = {
                            "kind": ("prop_interactions"
                                     if key == "INTERACTION" else "fields"),
                            "key": key, "fields": prop.fields,
                            "prop": prop,
                        }
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "global_audio":
                m_field = _KEY_VALUE_RE.match(line)
                field_key = (m_field.group(1).strip().upper()
                             if m_field else "")
                if m_field and field_key in GLOBAL_AUDIO_KEYS:
                    ukey = field_key
                    value = m_field.group(2).strip()
                    if ukey in block_seen:
                        dup_field(lineno, "GLOBAL_AUDIO", ukey, block_seen[ukey])
                        continue
                    block_seen[ukey] = lineno
                    record_field(doc.global_audio.fields, ukey, value)
                    if ukey in ("NARRATION_GAIN_DB", "DIALOGUE_GAIN_DB",
                                "AMBIENCE_GAIN_DB", "FOLEY_GAIN_DB",
                                "SFX_GAIN_DB", "BGM_GAIN_DB",
                                "BGM_DUCKING_DB", "MASTER_LIMIT_DB"):
                        key = ukey.lower()
                        parsed = _parse_float(value, lineno, errors,
                                              "V1E008", f"GLOBAL_AUDIO {ukey}")
                        if parsed is not None:
                            setattr(doc.global_audio, key, parsed)
                    if not value:
                        pending_holder[0] = {
                            "kind": "fields", "key": ukey,
                            "fields": doc.global_audio.fields,
                        }
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "constraints":
                if line.startswith("- "):
                    doc.constraints.append(line[2:].strip())
                    continue
                m_no = re.match(r"^NO\s*:\s*(.+)$", line, re.IGNORECASE)
                if m_no:
                    doc.constraints.append(m_no.group(1).strip())
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "project":
                m_field = _KEY_VALUE_RE.match(line)
                field_key = (m_field.group(1).strip().upper()
                             if m_field else "")
                if m_field and field_key in PROJECT_KEYS:
                    key = field_key
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, "PROJECT", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
                    record_field(doc.project_fields, key, value)
                    if key == "PROJECT_ID":
                        doc.project_id = value
                        doc.project = value
                    elif key == "PROJECT":
                        doc.project = value
                    elif key == "TITLE":
                        doc.title = value
                    elif key == "GENRE":
                        doc.genre = value
                    elif key == "LANGUAGE":
                        doc.language = value
                    elif key == "TONE":
                        doc.tone = value
                    elif key == "STORYTELLING_MODE":
                        doc.storytelling_mode = value
                    elif key == "PRIMARY_CHARACTER":
                        doc.primary_character = value
                        doc.primary_character_line = lineno
                    elif key == "EXTERNAL_NARRATOR":
                        doc.external_narrator = value
                        doc.external_narrator_line = lineno
                    elif key in ("STYLE", "VISUAL_STYLE"):
                        doc.visual_style = value
                    elif key == "ASPECT_RATIO":
                        if value not in ASPECT_RATIOS:
                            error(lineno, "V1E007",
                                  f"ASPECT_RATIO must be one of {', '.join(ASPECT_RATIOS)}, got {value!r}.")
                        else:
                            doc.aspect_ratio = value
                    elif key == "TARGET_DURATION":
                        (doc.target_duration, doc.target_duration_min,
                         doc.target_duration_max) = _parse_target_duration(
                            value, lineno, errors)
                    elif key == "MEME_POLICY":
                        policy = value.upper()
                        if policy not in MEME_POLICIES:
                            error(lineno, "V1E007",
                                  f"MEME_POLICY must be one of {', '.join(MEME_POLICIES)}, got {value!r}.")
                        else:
                            doc.meme_policy = policy
                    elif key == "MEME_MAX_PER_MINUTE":
                        try:
                            parsed = int(value)
                            if parsed < 0:
                                raise ValueError
                            doc.meme_max_per_minute = parsed
                        except ValueError:
                            error(lineno, "V1E008",
                                  f"MEME_MAX_PER_MINUTE must be a non-negative integer, got {value!r}.")
                    if not value:
                        pending_holder[0] = {
                            "kind": "fields", "key": key,
                            "fields": doc.project_fields,
                        }
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "visual_style":
                m_field = _KEY_VALUE_RE.match(line)
                field_key = (m_field.group(1).strip().upper()
                             if m_field else "")
                if m_field and field_key in VISUAL_STYLE_KEYS:
                    key = field_key
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, "VISUAL_STYLE", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
                    record_field(doc.visual_style_fields, key, value)
                    if key == "STYLE":
                        doc.visual_style = value
                    elif key == "HEAD_RATIO":
                        parsed = _parse_float(value, lineno, errors,
                                              "V1E008", "HEAD_RATIO")
                        if parsed is not None and not (
                                HEAD_RATIO_MIN <= parsed <= HEAD_RATIO_MAX):
                            error(lineno, "V1E009",
                                  f"HEAD_RATIO {parsed} is outside the locked range "
                                  f"{HEAD_RATIO_MIN}-{HEAD_RATIO_MAX} (default {HEAD_RATIO_DEFAULT}).")
                    if not value:
                        pending_holder[0] = {
                            "kind": "fields", "key": key,
                            "fields": doc.visual_style_fields,
                        }
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "qa":
                m_field = _KEY_VALUE_RE.match(line)
                field_key = (m_field.group(1).strip().upper()
                             if m_field else "")
                if m_field and _is_qa_key(field_key):
                    key = field_key
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, "QA", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
                    record_field(doc.qa.fields, key, value)
                    if key == "MIN_SCORE":
                        parsed = _parse_float(value, lineno, errors, "V1E008", "QA MIN_SCORE")
                        if parsed is not None:
                            if 0.0 <= parsed <= 10.0:
                                doc.qa.min_score = parsed
                            else:
                                error(lineno, "V1E010",
                                      f"QA MIN_SCORE must be between 0 and 10, got {parsed}.")
                    elif key == "MIN_OVERALL_SCORE":
                        head = value.split("/")[0].strip()
                        parsed = _parse_float(head, lineno, errors,
                                              "V1E008", "QA MIN_OVERALL_SCORE")
                        if parsed is not None:
                            if 0.0 <= parsed <= 10.0:
                                doc.qa.min_score = parsed
                            else:
                                error(lineno, "V1E010",
                                      f"QA MIN_OVERALL_SCORE must be between 0 and 10, got {parsed}.")
                    elif key == "MAX_HARD_FAILS":
                        try:
                            parsed_int = int(value)
                            if parsed_int < 0:
                                raise ValueError
                            doc.qa.max_hard_fails = parsed_int
                        except ValueError:
                            error(lineno, "V1E008",
                                  f"QA MAX_HARD_FAILS must be a non-negative integer, got {value!r}.")
                    elif key == "HARD_FAIL_COUNT":
                        try:
                            parsed_int = int(value)
                            if parsed_int < 0:
                                raise ValueError
                            doc.qa.max_hard_fails = parsed_int
                        except ValueError:
                            error(lineno, "V1E008",
                                  f"QA HARD_FAIL_COUNT must be a non-negative integer, got {value!r}.")
                    elif key in ("REQUIRE_TECHNICAL", "REQUIRE_CREATIVE_REVIEW",
                                 "LANGUAGE_GATE"):
                        parsed_bool = _parse_bool(value, lineno, errors, f"QA {key}")
                        if parsed_bool is not None:
                            setattr(doc.qa, key.lower(), parsed_bool)
                    elif key.startswith("EXPECTED_"):
                        try:
                            doc.qa.expected_counts[key.lower()] = int(value)
                        except ValueError:
                            error(lineno, "V1E008",
                                  f"QA {key} must be an integer, got {value!r}.")
                    if not value:
                        pending_holder[0] = {
                            "kind": "fields", "key": key,
                            "fields": doc.qa.fields,
                        }
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "output":
                m_field = _KEY_VALUE_RE.match(line)
                field_key = (m_field.group(1).strip().upper()
                             if m_field else "")
                if m_field and _is_output_key(field_key):
                    key = field_key
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, "OUTPUT", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
                    record_field(doc.output.fields, key, value)
                    if key == "RESOLUTION":
                        if value in RESOLUTIONS:
                            doc.output.resolution = value
                        else:
                            error(lineno, "V1E007",
                                  f"OUTPUT RESOLUTION must be one of {', '.join(RESOLUTIONS)}, got {value!r}.")
                    elif key == "FPS":
                        try:
                            fps = int(value)
                        except ValueError:
                            fps = -1
                        if fps in FRAME_RATES:
                            doc.output.fps = fps
                        else:
                            error(lineno, "V1E007",
                                  f"OUTPUT FPS must be one of {', '.join(str(f) for f in FRAME_RATES)}, got {value!r}.")
                    elif key in ("FORMAT", "VIDEO_FORMAT"):
                        if value.upper() == "MP4":
                            doc.output.format = "MP4"
                        else:
                            error(lineno, "V1E007",
                                  f"OUTPUT {key} must be MP4, got {value!r}.")
                    elif key == "DRAFT_FOLDER":
                        doc.output.draft_folder = value
                    elif key == "MASTER":
                        if value.upper() == "MANUAL_ONLY":
                            doc.output.master = "MANUAL_ONLY"
                        else:
                            error(lineno, "V1E017",
                                  "OUTPUT MASTER must be MANUAL_ONLY: a Master is never automatic.")
                    if not value:
                        pending_holder[0] = {
                            "kind": "fields", "key": key,
                            "fields": doc.output.fields,
                        }
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "end_card" and isinstance(context_obj, EndCard):
                card = context_obj
                m_field = _KEY_VALUE_RE.match(line)
                field_key = (m_field.group(1).strip().upper()
                             if m_field else "")
                if m_field and field_key in END_CARD_KEYS:
                    key = field_key
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, "END_CARD", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
                    record_field(card.fields, key, value)
                    if key == "TEXT":
                        card.text = value
                    elif key == "STYLE":
                        card.style = value
                    elif key == "BACKGROUND":
                        card.background = value
                    elif key == "SECONDARY_TEXT":
                        card.secondary_text = value
                    elif key == "TEXT_LANGUAGE":
                        card.text_language = value
                    elif key == "BGM":
                        card.bgm = value
                    elif key == "SFX":
                        card.sfx = value
                    elif key == "DURATION":
                        # END_CARD DURATION rejects AUTO and requires a
                        # positive number of seconds (SPEC §5.10). The
                        # new dialect accepts a unit suffix ("3s");
                        # legacy documents keep the plain-number rule.
                        card.duration_raw = value
                        if value.upper() == "AUTO":
                            error(lineno, "V1E012",
                                  "END_CARD DURATION does not accept AUTO; "
                                  "it requires a positive number of seconds.")
                        elif is_new_dialect:
                            seconds = _parse_seconds(value)
                            if seconds is not None and seconds > 0:
                                card.duration = seconds
                                card.duration_sec = seconds
                            else:
                                error(lineno, "V1E012",
                                      f"END_CARD DURATION must be a positive "
                                      f"number of seconds (no AUTO), got {value!r}.")
                        else:
                            m_dur = _DURATION_RE.match(value)
                            if m_dur and float(m_dur.group(1)) > 0:
                                card.duration = float(m_dur.group(1))
                                card.duration_sec = card.duration
                            else:
                                error(lineno, "V1E012",
                                      f"END_CARD DURATION must be a positive "
                                      f"plain number of seconds (no unit "
                                      f"suffix, no AUTO), got {value!r}.")
                    if not value:
                        pending_holder[0] = {
                            "kind": "fields", "key": key,
                            "fields": card.fields,
                        }
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            # -- scene content ----------------------------------------------
            if context == "scene" and current_scene is not None:
                scene = current_scene
                handled = self._handle_scene_line(
                    line, lineno, scene, current_shot, add_spoken,
                    add_sfx, add_ambience, add_bgm, add_meme, add_vfx,
                    note_unsupported, error, errors,
                    {"scene_seen": scene_seen, "shot_seen": shot_seen,
                     "scene_transition": scene_transition,
                     "is_new_dialect": is_new_dialect,
                     "pending_holder": pending_holder,
                     "record_field": record_field},
                    lambda: current_voice_note,
                    lambda v: None,
                )
                if handled == "voice_note":
                    # VOICE_NOTE value is the remainder after the key.
                    current_voice_note = line.split(":", 1)[1].strip()
                    scene.voice_note = current_voice_note
                    if current_shot is not None:
                        current_shot.voice_note = current_voice_note
                elif handled == "shot_field":
                    pass
                elif handled is False:
                    # Bare speaker line or free text.
                    bare = self._handle_bare_line(
                        line, lineno, scene, current_shot, add_spoken,
                        note_unsupported)
                    if not bare:
                        note_unsupported(*_split_key_value(line), lineno)
                continue

            # Outside any block: unknown key — record, never discard.
            note_unsupported(*_split_key_value(line), lineno)

        # -- post-parse validation ------------------------------------------
        flush_spoken()
        flush_sfx()
        self._finalize(doc, seen_scenes, {
            "is_new_dialect": is_new_dialect,
            "none_records": none_records,
        })

        if strict and doc.validation_errors:
            raise StudioScriptV1Error(doc.validation_errors[0])
        return doc

    # -- scene-line handling -------------------------------------------------

    def _handle_scene_line(self, line, lineno, scene, shot, add_spoken,
                           add_sfx, add_ambience, add_bgm, add_meme, add_vfx,
                           note_unsupported, error, errors, dup_state,
                           _get_voice_note, _set_voice_note):
        """Handle one line inside a SCENE. Returns "voice_note" when the
        line was VOICE_NOTE (caller updates the running note), "shot_field"
        / True when handled, False when the line needs bare-line handling.

        ``dup_state`` carries the per-scene/per-shot single-valued-field
        tracking (V1E006); the FIRST value of a duplicated field is kept.
        """
        def dup_check(seen: Dict[str, int], where: str, field: str) -> bool:
            """True when ``field`` was already seen (error reported)."""
            if field in seen:
                error(lineno, "V1E006",
                      f"{where}: {field} appears more than once "
                      f"(first at line {seen[field]}); single-valued "
                      f"fields must appear at most once.")
                return True
            seen[field] = lineno
            return False

        scene_fields = dup_state["scene_seen"].setdefault(id(scene), {})
        shot_fields = (dup_state["shot_seen"].setdefault(id(shot), {})
                       if shot is not None else {})
        is_new_dialect = dup_state.get("is_new_dialect", False)
        pending_holder = dup_state.get("pending_holder")
        record_field = dup_state.get("record_field")

        def _record(target_fields, key, value):
            if record_field is not None:
                record_field(target_fields, key, value)

        def _set_pending(kind, key, target_fields, **extra):
            if pending_holder is not None:
                pending = {"kind": kind, "key": key,
                           "fields": target_fields}
                pending.update(extra)
                pending_holder[0] = pending

        # NARRATION [Lnn]: / DIALOGUE [Lnn]: — explicit LINE_ID before
        # the colon (the bracket form is not a KEY: value line). Any
        # other bracket right after the key is a malformed LINE_ID.
        m_bracket = re.match(
            r"^(NARRATION|DIALOGUE)\s*\[(L\d+)\]\s*:\s*(.*)$", line, re.IGNORECASE)
        if m_bracket:
            self._spoken_line(m_bracket.group(1).upper(), m_bracket.group(2),
                              m_bracket.group(3).strip(), lineno, add_spoken, error)
            return True
        if re.match(r"^(NARRATION|DIALOGUE)\s*\[", line, re.IGNORECASE):
            error(lineno, "V1E019",
                  f"Malformed explicit LINE_ID in {line!r}: expected "
                  f"[Lnn] with digits, e.g. [L001].")
            return True

        m_key = _KEY_VALUE_RE.match(line)
        if not m_key:
            return False
        key = m_key.group(1).strip().upper()
        value = m_key.group(2).strip()

        # NARRATION / DIALOGUE with optional explicit [Lnn] after the colon.
        # (Empty NARRATION:/DIALOGUE: lines open sub-blocks and are
        # intercepted by the main loop before reaching here.)
        if key in ("NARRATION", "DIALOGUE"):
            explicit_id = None
            rest = value
            m_id = _LINE_ID_RE.match(value)
            if m_id:
                explicit_id = m_id.group(1)
                rest = m_id.group(2).strip()
            elif _MALFORMED_LINE_ID_RE.match(value):
                error(lineno, "V1E019",
                      f"Malformed explicit LINE_ID in {value!r}: expected "
                      f"[Lnn] with digits, e.g. [L001].")
                return True
            self._spoken_line(key, explicit_id, rest, lineno, add_spoken, error)
            return True

        # Shot fields take precedence over scene fields while inside a shot.
        # TRANSITION is the exception (§2.5): it always attaches to the
        # enclosing SCENE, even in SHOT context. Scene-only keys
        # (LOCATION / TIME_OF_DAY / MOOD / VISUAL) in SHOT context are
        # recorded under §8.3, not applied to the scene. A piped VFX
        # line (``VFX: name | TRIGGER: ...``) is a content cue, not the
        # shot's ;-separated VFX field, so it falls through below.
        if (shot is not None and key in SHOT_KEYS
                and not (key == "VFX" and "|" in value)):
            if dup_check(shot_fields, f"SHOT {shot.id}", key):
                return "shot_field"
            _record(shot.fields, key, value)
            if key == "TYPE":
                shot.type_raw = value
                normalized = _normalize_shot_type(value)
                if normalized in SHOT_TYPES:
                    shot.type = normalized
                else:
                    error(lineno, "V1E014",
                          f"SHOT TYPE must be one of {', '.join(SHOT_TYPES)}, got {value!r}.")
            elif key == "CAMERA":
                # CAMERA is descriptive free text, never validated
                # against the TYPE enum (SPEC §5.5).
                shot.camera = value
            elif key == "CAMERA_MOVEMENT":
                movement, valid = _classify_camera_movement(value)
                shot.camera_movement_text = value
                if valid:
                    shot.camera_movement = movement
                else:
                    error(lineno, "V1E007",
                          f"CAMERA_MOVEMENT must be one of {', '.join(CAMERA_MOVEMENTS)} "
                          f"or descriptive prose, got {value!r}.")
            elif key == "SUBJECT":
                shot.subject = value
            elif key == "DURATION":
                shot.duration, shot.duration_seconds = _parse_duration(
                    value, lineno, errors, f"SHOT {shot.id}")
            elif key == "ACTION":
                if value:
                    shot.action = value
                else:
                    _set_pending("shot_action", key, shot.fields, shot=shot)
            elif key == "EXPRESSION":
                shot.expression = value
            elif key == "VFX":
                if value:
                    shot.vfx = _split_list(value)
                else:
                    _set_pending("shot_vfx", key, shot.fields, shot=shot)
            elif key == "LOCATION_OVERRIDE":
                shot.location_override = value
            elif key == "TRIGGER":
                shot.trigger = value
                shot.trigger_line_id = _parse_trigger_line_id(value)
            elif key == "COMPOSITION":
                pass  # fields capture only
            elif key in ("POST_DIALOGUE_PAUSE", "END_HOLD"):
                seconds = _parse_seconds(value) if value else None
                raw_attr = ("post_dialogue_pause_raw" if key == "POST_DIALOGUE_PAUSE"
                            else "end_hold_raw")
                setattr(shot, raw_attr, value)
                if seconds is None:
                    error(lineno, "V1E012",
                          f"SHOT {shot.id} {key} must be a number of seconds "
                          f"(e.g. '0.6s'), got {value!r}.")
                else:
                    attr = ("post_dialogue_pause" if key == "POST_DIALOGUE_PAUSE"
                            else "end_hold")
                    setattr(shot, attr, seconds)
            return "shot_field"

        if shot is not None and key in ("LOCATION", "TIME_OF_DAY", "MOOD", "VISUAL"):
            note_unsupported(key, value, lineno)
            return True

        if key == "LOCATION":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            scene.location_text = value
            return True
        if key == "TITLE":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            scene.title = value
            return True
        if key == "CHARACTERS":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            if value.upper() == "NONE":
                scene.characters = []
            else:
                scene.characters = [part.strip() for part in value.split(",")
                                    if part.strip()]
            return True
        if key == "COSTUME":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            scene.costume = value
            return True
        if key in ("STORY_PURPOSE", "HISTORICAL_PROVENANCE"):
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            return True
        if key == "LOCATION_OVERRIDE":
            # No shot context: record verbatim on the scene; the
            # shot-level form is the defined one (SPEC §5.5).
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            return True
        if key in ("TRIGGER", "COMPOSITION", "POST_DIALOGUE_PAUSE", "END_HOLD"):
            # Shot fields written outside any shot: preserved verbatim
            # on the scene; they take effect only inside a SHOT.
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            return True
        if key == "TIME_OF_DAY":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            scene.time_of_day = value
            return True
        if key == "MOOD":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            scene.mood = value
            return True
        if key == "DURATION":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            scene.duration, scene.duration_seconds = _parse_duration(
                value, lineno, errors, f"SCENE {scene.number}")
            return True
        if key == "VISUAL":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            scene.visual = value
            return True
        if key == "TRANSITION":
            # Same field in both positions (§5.4): the same value twice
            # is allowed; different values are V1E006 (first wins).
            # New dialect: TRANSITION is preserved verbatim with no
            # enum validation. Legacy dialect: the enum is enforced.
            if is_new_dialect:
                transition = value
            else:
                transition = _normalize_enum_token(value)
                if transition not in TRANSITIONS:
                    error(lineno, "V1E007",
                          f"TRANSITION must be one of {', '.join(TRANSITIONS)}, got {value!r}.")
                    return True
            _record(scene.fields, key, value)
            seen_transition = dup_state["scene_transition"].get(id(scene))
            if seen_transition is not None:
                if seen_transition[0] != transition:
                    error(lineno, "V1E006",
                          f"SCENE {scene.number}: TRANSITION appears with "
                          f"different values ({seen_transition[0]} at line "
                          f"{seen_transition[1]} and {transition} here); "
                          f"the field and content-line positions must agree.")
                return True
            dup_state["scene_transition"][id(scene)] = (transition, lineno)
            scene.transition = transition
            return True
        if key == "ACTION":
            _record(scene.fields, key, value)
            if value:
                scene.actions.append(value)
            else:
                _set_pending("scene_action", key, scene.fields, scene=scene)
            return True
        if key == "EXPRESSION":
            _record(scene.fields, key, value)
            m_expr = re.match(r"^(.+?)\s*:\s*(.+)$", value)
            if m_expr:
                scene.expressions.append({
                    "character": m_expr.group(1).strip(),
                    "expression": m_expr.group(2).strip(),
                    "line": lineno,
                })
            else:
                scene.expressions.append({
                    "character": None, "expression": value, "line": lineno,
                })
            return True
        if key == "CAMERA":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            scene.camera = value
            return True
        if key == "CAMERA_MOVEMENT":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            movement, valid = _classify_camera_movement(value)
            scene.camera_movement_text = value
            if valid:
                scene.camera_movement = movement
            else:
                error(lineno, "V1E007",
                      f"CAMERA_MOVEMENT must be one of {', '.join(CAMERA_MOVEMENTS)} "
                      f"or descriptive prose, got {value!r}.")
            return True
        if key == "VOICE_NOTE":
            _record(scene.fields, key, value)
            if shot is not None:
                _record(shot.fields, key, value)
            return "voice_note"
        if key == "MEME_NOTE":
            # Supported legacy scene field (§6.13): kept as data, never
            # spoken, never discarded. Single-valued per scene.
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            _record(scene.fields, key, value)
            scene.meme_note = value
            return True
        if key == "LIP_SYNC":
            # Shot/scene-level LIP_SYNC: applies to the most recent
            # spoken line in this shot (or scene) that has no lip_sync
            # yet — the form used when LIP_SYNC: follows a spoken
            # sub-block instead of sitting inside it (SPEC §6.1). It
            # is also preserved verbatim in the shot/scene fields.
            if shot is not None:
                _record(shot.fields, key, value)
            else:
                _record(scene.fields, key, value)
            target = None
            if shot is not None and shot.spoken_line_ids:
                wanted = shot.spoken_line_ids[-1]
                for spoken in scene.spoken_lines:
                    if spoken.line_id == wanted:
                        target = spoken
            elif scene.spoken_lines:
                target = scene.spoken_lines[-1]
            if target is not None and target.lip_sync is None:
                target.lip_sync = value
            return True
        if key == "SFX":
            add_sfx(value, lineno)
            return True
        if key == "AMBIENCE":
            add_ambience(value, lineno)
            return True
        if key in ("BGM", "MUSIC"):
            add_bgm(value, lineno, key)
            return True
        if key == "MEME":
            add_meme(value, lineno)
            return True
        if key == "VFX":
            if value:
                add_vfx(value, lineno)
            else:
                _record(scene.fields, key, value)
                _set_pending("scene_vfx", key, scene.fields, scene=scene)
            return True
        if key in SCENE_KEYS:
            return True  # known key handled above; unreachable guard
        return False

    def _spoken_line(self, key, explicit_id, rest, lineno, add_spoken, error) -> None:
        """Record a NARRATION / DIALOGUE line after its key and LINE_ID
        have been stripped. ``rest`` is the remaining text."""
        if key == "NARRATION":
            if not rest:
                error(lineno, "V1E019", "NARRATION line has no text.")
                return
            add_spoken(NARRATOR_SPEAKER, rest, "narration", explicit_id, lineno)
            return
        # DIALOGUE: <Speaker>: <text>
        m_speaker = re.match(r"^(.+?)\s*:\s*(.+)$", rest)
        if not m_speaker:
            error(lineno, "V1E019",
                  f"DIALOGUE must use the form 'DIALOGUE: <Speaker>: <text>', got {rest!r}.")
            return
        add_spoken(m_speaker.group(1), m_speaker.group(2).strip(),
                   "dialogue", explicit_id, lineno)

    def _handle_bare_line(self, line, lineno, scene, shot, add_spoken,
                          note_unsupported) -> bool:
        """Legacy bare ``<SPEAKER>: <text>`` dialogue inside a scene.

        A single all-caps token (``FOO:``) is treated as an unknown field,
        not a speaker; anything that looks like a name (multi-word, title
        case, or matching a declared character / narrator alias) is a
        spoken line whose speaker is validated in the post-pass.
        """
        m_key = _KEY_VALUE_RE.match(line)
        if not m_key:
            return False
        raw_key = m_key.group(1).strip()
        value = m_key.group(2).strip()
        key_upper = raw_key.upper()
        if key_upper in SCENE_KEYS or key_upper in HEADER_KEYS:
            return False
        single_token = " " not in raw_key
        if single_token and raw_key == raw_key.upper() and "_" in raw_key:
            return False  # UNKNOWN_FIELD: style key, not a speaker
        if single_token and raw_key == raw_key.upper():
            # Single all-caps token: a speaker only if it matches a known
            # narrator alias (checked at post-pass time via label) — but
            # "NARRATOR" itself is such a label. Anything else all-caps
            # and single-token is an unknown field key.
            if not _is_narrator_label(raw_key):
                return False
        if not value:
            return False
        kind = "narration" if _is_narrator_label(raw_key) else "dialogue"
        add_spoken(raw_key, value, kind, None, lineno)
        return True

    # -- post-parse validation ----------------------------------------------

    def _finalize(self, doc: StudioScriptV1Document,
                  seen_scenes: Dict[int, int],
                  final_state: Dict[str, Any]) -> None:
        errors = doc.validation_errors
        warnings = doc.warnings
        is_new_dialect = final_state.get("is_new_dialect", False)
        none_records = final_state.get("none_records", [])

        def error(line: int, code: str, message: str) -> None:
            errors.append(ValidationIssue(line, code, message))

        # Character final mappings (SPEC §5.1): identity defaults to
        # the block id; voice resolves VOICE_ID > VOICE, voice_style
        # resolves VOICE_TONE > VOICE_STYLE; extras are VOICE: NONE
        # or ROLE "Background extras".
        for char in doc.characters:
            if not char.id:
                char.id = char.name
            if not char.identity_id:
                char.identity_id = char.id
            voice_id = char.fields.get("VOICE_ID")
            if isinstance(voice_id, str) and voice_id:
                char.voice = voice_id
            elif isinstance(char.fields.get("VOICE"), str) and char.fields["VOICE"]:
                char.voice = char.fields["VOICE"]
            voice_tone = char.fields.get("VOICE_TONE")
            if isinstance(voice_tone, str) and voice_tone:
                char.voice_style = voice_tone
            # 2026-11-12 (A2 wiring item 5): VOICE:NONE means "does
            # not speak", NOT "background extra". The old rule marked
            # every silent character an extra, which excluded the
            # Cyclopes (who hammer, carry and hand over the bolt)
            # from the visible cast. Only an explicit background-
            # extras role marks a character an extra.
            char.is_extra = (
                _normalize_name(char.role) == "background extras")
        # Duplicate IDENTITY_ID detection (V1E001, SPEC §5.1). Two
        # blocks with the same id already reported V1E001 at the
        # header, so only distinct blocks sharing an id are reported.
        seen_identity_ids: Dict[str, ScriptCharacter] = {}
        for char in doc.characters:
            norm_id = _normalize_name(char.identity_id)
            first = seen_identity_ids.get(norm_id)
            if first is None:
                seen_identity_ids[norm_id] = char
            elif first.id != char.id:
                error(char.line, "V1E001",
                      f"IDENTITY_ID {char.identity_id!r} for {char.name!r} "
                      f"duplicates the identity of {first.name!r} "
                      f"(declared at line {first.line}); identities must "
                      f"be unique across characters.")

        # Location alias mappings (SPEC §5.2): PERIOD falls back to
        # YEAR / HISTORICAL_PERIOD, GEOGRAPHY to HISTORICAL_REFERENCE,
        # when the legacy keys are absent.
        for loc in doc.locations:
            if "PERIOD" not in loc.fields:
                year = loc.fields.get("YEAR")
                if isinstance(year, str) and year:
                    loc.period = year
                else:
                    hist = loc.fields.get("HISTORICAL_PERIOD")
                    if isinstance(hist, str):
                        loc.period = hist
            if "GEOGRAPHY" not in loc.fields:
                ref = loc.fields.get("HISTORICAL_REFERENCE")
                if isinstance(ref, str):
                    loc.geography = ref

        # First-person prerequisite rule (SPEC §16): the document
        # declares first-person mode when STORYTELLING_MODE starts
        # with FIRST_PERSON, EXTERNAL_NARRATOR is NONE, or a
        # PRIMARY_CHARACTER is present.
        mode = (doc.storytelling_mode or "").strip()
        ext = (doc.external_narrator or "").strip()
        primary = (doc.primary_character or "").strip()
        first_person = (
            mode.upper().startswith("FIRST_PERSON")
            or ext.upper() == "NONE"
            or (bool(primary) and primary.upper() != "NONE"))
        if doc.external_narrator is not None and ext.upper() != "NONE":
            error(doc.external_narrator_line, "V1E025",
                  "Prerequisite rule: all scripts are first-person; an "
                  f"external narrator is forbidden, but EXTERNAL_NARRATOR "
                  f"declares {ext!r} (it must be NONE).")
        if primary and primary.upper() != "NONE":
            if doc.get_character(primary) is None:
                error(doc.primary_character_line, "V1E018",
                      f"PRIMARY_CHARACTER {primary!r} does not match a "
                      f"declared CHARACTER.")

        # Scene LOCATION references: a value matching a declared LOCATION
        # id under §2.4 normalisation is a reference (stored as the
        # declared id); anything else stays inline free text (§11.4).
        location_ids = {_normalize_name(loc.id): loc.id for loc in doc.locations}
        location_names = {_normalize_name(loc.name): loc.id
                          for loc in doc.locations if loc.name}
        for scene in doc.scenes:
            if scene.location_text:
                matched = location_ids.get(_normalize_name(scene.location_text))
                if matched is not None:
                    scene.location_ref = matched
                    scene.location_text = ""

        # Speaker resolution (characters may be declared after scenes).
        # Resolved speakers use the display NAME; speaker_id is the
        # CHARACTER block id. In first-person documents, any spoken
        # line whose speaker is an external narrator is V1E025.
        for scene in doc.scenes:
            for spoken in scene.spoken_lines:
                if spoken.speaker == NARRATOR_SPEAKER:
                    if first_person:
                        error(spoken.line, "V1E025",
                              "Prerequisite rule: all scripts are "
                              "first-person; an external narrator is "
                              "forbidden, but this spoken line has no "
                              "SPEAKER resolving to a declared CHARACTER.")
                    continue
                char = doc.get_character(spoken.speaker)
                if char is not None:
                    spoken.speaker = char.name
                    spoken.speaker_id = char.id
                else:
                    error(spoken.line, "V1E015",
                          f"Speaker {spoken.speaker!r} in SCENE {scene.number} "
                          f"is not a declared CHARACTER.")
        if not first_person and any(
                ln.speaker == NARRATOR_SPEAKER for ln in doc.spoken_lines):
            # Legacy documents keep the narrator, with one warning
            # noting the prerequisite rule (SPEC §16).
            warnings.append(ValidationIssue(
                0, "V1E025",
                "Prerequisite rule: all scripts are first-person; an "
                "external narrator is forbidden in new scripts. This "
                "legacy document does not declare first-person mode, "
                "so its narrator lines are allowed, but new scripts "
                "MUST declare STORYTELLING_MODE / PRIMARY_CHARACTER / "
                "EXTERNAL_NARRATOR: NONE and give every spoken line a "
                "SPEAKER resolving to a declared CHARACTER."))

        # TRIGGERs are recorded verbatim at parse time. Resolution
        # against the speech/animation timeline is V1E022, raised at
        # the timeline stage — never a parse-time error (SPEC §8.2).
        # (No trigger check here by design.)

        # COSTUME_CHANGE scene numbers must exist.
        for char in doc.characters:
            for change in char.costume_changes:
                if change["scene_number"] not in seen_scenes:
                    error(change["line"], "V1E018",
                          f"COSTUME_CHANGE for {char.name!r} references SCENE "
                          f"{change['scene_number']}, which does not exist.")

        # SHOT TYPE rules (SPEC §5.5): in legacy documents TYPE is
        # required; in new-dialect documents TYPE is optional when
        # CAMERA is present (type None) and required otherwise.
        # SUBJECT must resolve (V1E018, an error per SPEC §8.2).
        # LOCATION_OVERRIDE must resolve to a declared LOCATION id.
        prop_names = {_normalize_name(p.name) for p in doc.props}
        prop_ids = {_normalize_name(p.id) for p in doc.props if p.id}
        for scene in doc.scenes:
            for shot in scene.shots:
                if not shot.type and not shot.type_raw:
                    if not (is_new_dialect and shot.camera):
                        error(shot.line, "V1E013",
                              f"SHOT {shot.id} in SCENE {scene.number} has no TYPE; "
                              f"TYPE is required and must be one of {', '.join(SHOT_TYPES)}.")
                if shot.subject:
                    subject_norm = _normalize_name(shot.subject)
                    if (_is_narrator_label(shot.subject)
                            or doc.get_character(shot.subject) is not None
                            or subject_norm in prop_names
                            or subject_norm in prop_ids):
                        pass
                    else:
                        error(shot.line, "V1E018",
                              f"SHOT {shot.id} SUBJECT {shot.subject!r} does not match "
                              f"a declared CHARACTER or PROP.")
                if shot.location_override:
                    override_norm = _normalize_name(shot.location_override)
                    if (override_norm not in location_ids
                            and override_norm not in location_names):
                        error(shot.line, "V1E018",
                              f"SHOT {shot.id} LOCATION_OVERRIDE "
                              f"{shot.location_override!r} does not match "
                              f"a declared LOCATION.")
                # SHOT EXPRESSION character prefix must resolve (§§5.5, 6.4).
                if shot.expression:
                    m_expr = re.match(r"^(.+?)\s*:\s*(.+)$", shot.expression)
                    if m_expr:
                        prefix = m_expr.group(1).strip()
                        if (not _is_narrator_label(prefix)
                                and doc.get_character(prefix) is None):
                            error(shot.line, "V1E018",
                                  f"SHOT {shot.id} EXPRESSION character prefix "
                                  f"{prefix!r} does not match a declared "
                                  f"CHARACTER or narrator alias.")
            # Scene EXPRESSION character prefixes must resolve (§6.4).
            for expr in scene.expressions:
                prefix = expr["character"]
                if prefix is not None and (not _is_narrator_label(prefix)
                                           and doc.get_character(prefix) is None):
                    error(expr["line"], "V1E018",
                          f"EXPRESSION character prefix {prefix!r} in SCENE "
                          f"{scene.number} does not match a declared "
                          f"CHARACTER or narrator alias.")

        # PROP OWNER must resolve, and PROP SCENES entries must exist
        # (V1E018, an error per SPEC §8.2 — not a warning).
        for prop in doc.props:
            if not prop.id:
                prop.id = prop.name
            if prop.owner and prop.owner.upper() != "NONE":
                if doc.get_character(prop.owner) is None:
                    error(prop.line, "V1E018",
                          f"PROP {prop.name!r} OWNER {prop.owner!r} does not match "
                          f"a declared CHARACTER.")
            if not prop.all_scenes:
                for scene_no in prop.scenes:
                    if scene_no not in seen_scenes:
                        error(prop.line, "V1E018",
                              f"PROP {prop.name!r} SCENES entry {scene_no} "
                              f"does not match any declared SCENE.")

        # NONE directives coexisting with real cues of the same type at
        # the SAME scope (V1E024, SPEC §10.2): a scene-level NONE
        # forbids cues anywhere in the scene; a shot-level NONE forbids
        # cues only in that shot. Cues in other shots are unaffected.
        for scene in doc.scenes:
            cues_by_scope: Dict[tuple, bool] = {}
            for cue in scene.audio_cues:
                cues_by_scope[(cue.shot_id, cue.cue_type)] = True
                cues_by_scope[(None, cue.cue_type)] = True
            for (none_scene, none_shot, cue_type, _none_line) in none_records:
                if none_scene != scene.number:
                    continue
                if none_shot is None:
                    conflict = any(
                        cue.cue_type == cue_type for cue in scene.audio_cues)
                    scope = f"SCENE {scene.number}"
                else:
                    conflict = any(
                        cue.cue_type == cue_type and cue.shot_id == none_shot
                        for cue in scene.audio_cues)
                    scope = f"SHOT {none_shot} in SCENE {scene.number}"
                if conflict:
                    error(scene.line, "V1E024",
                          f"{scope} declares {cue_type}: NONE but also has "
                          f"{cue_type} cues.")

        # Document-level requirements.
        if not doc.scenes:
            error(0, "V1E020", "A STUDIO SCRIPT V1 document must contain at least one SCENE.")
        if not doc.spoken_lines:
            error(0, "V1E023",
                  "A STUDIO SCRIPT V1 document must contain at least one spoken line.")

        # Keep issues in document order (stable for equal lines).
        errors.sort(key=lambda issue: issue.line)
        warnings.sort(key=lambda issue: issue.line)


def _split_key_value(line: str) -> tuple[str, str]:
    """Split a leftover line into (key, value) for unsupported_fields."""
    m = _KEY_VALUE_RE.match(line)
    if m:
        return m.group(1).strip().upper(), m.group(2).strip()
    return "FREE_TEXT", line


def parse_studio_script_v1(text: str, strict: bool = False) -> StudioScriptV1Document:
    """Parse a STUDIO SCRIPT V1 document.

    Never raises on invalid content unless ``strict=True``, in which case
    :class:`StudioScriptV1Error` is raised on the first validation error.
    """
    return StudioScriptV1Parser().parse(text, strict=strict)
