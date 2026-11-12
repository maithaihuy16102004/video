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
)

PROP_KEYS = ("DESCRIPTION", "OWNER", "SCENES", "INTERACTION")

SHOT_KEYS = (
    "TYPE",
    "CAMERA",
    "CAMERA_MOVEMENT",
    "SUBJECT",
    "DURATION",
    "ACTION",
    "EXPRESSION",
    "VFX",
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
)

QA_KEYS = (
    "MIN_SCORE",
    "REQUIRE_TECHNICAL",
    "REQUIRE_CREATIVE_REVIEW",
    "LANGUAGE_GATE",
    "MAX_HARD_FAILS",
)

OUTPUT_KEYS = ("RESOLUTION", "FPS", "FORMAT", "DRAFT_FOLDER", "MASTER")

END_CARD_KEYS = ("TEXT", "DURATION", "STYLE")

# No upstream header defaults are inherited (SPEC §4): PROJECT, GENRE,
# STYLE / VISUAL_STYLE, and TONE absent means "unspecified", stored as
# None in the parsed document. LANGUAGE, ASPECT_RATIO, TARGET_DURATION,
# MEME_POLICY, and MEME_MAX_PER_MINUTE keep the defaults in §4.

_SCENE_RE = re.compile(r"^SCENE\s+(\d+)\s*:\s*(.*)$", re.IGNORECASE)
_SHOT_RE = re.compile(r"^SHOT\s+(.+?)\s*:\s*$", re.IGNORECASE)
_KEY_VALUE_RE = re.compile(r"^([A-Za-zÀ-ỹ0-9_][A-Za-zÀ-ỹ0-9_ .'\-]*?)\s*:\s*(.*)$")
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
    identity_id: str = ""  # defaults to name at finalization
    line: int = 0


@dataclass
class ScriptLocation:
    id: str
    name: str = ""
    period: str = ""
    geography: str = ""
    architecture: str = ""
    features: List[str] = field(default_factory=list)
    foreground: str = ""
    midground: str = ""
    background: str = ""
    lighting: str = ""
    weather: str = ""
    palette: List[str] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)
    line: int = 0


@dataclass
class ScriptProp:
    name: str
    description: str = ""
    owner: str = ""
    scenes: List[int] = field(default_factory=list)
    all_scenes: bool = False
    interactions: List[str] = field(default_factory=list)
    line: int = 0


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


@dataclass
class StudioScriptShot:
    id: str
    line: int = 0
    type: str = ""  # normalized lower_snake SHOT_TYPES value; "" if missing/invalid
    type_raw: str = ""  # TYPE value exactly as written
    camera: str = ""
    camera_movement: str = "STATIC"
    subject: str = ""
    duration: str = "AUTO"
    duration_seconds: Optional[float] = None
    action: str = ""
    expression: str = ""
    vfx: List[str] = field(default_factory=list)
    voice_note: str = ""
    spoken_line_ids: List[str] = field(default_factory=list)


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
    camera_movement: str = "STATIC"
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


@dataclass
class QAConfig:
    min_score: float = 8.0
    require_technical: bool = True
    require_creative_review: bool = True
    language_gate: bool = True
    max_hard_fails: int = 0


@dataclass
class OutputConfig:
    resolution: str = "1920x1080"
    fps: int = 24
    format: str = "MP4"
    draft_folder: str = "drive:drafts"
    master: str = "MANUAL_ONLY"


@dataclass
class EndCard:
    text: str = ""
    duration: float = 3.0
    style: str = ""
    line: int = 0


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
        """Case-insensitive lookup by declared character name."""
        wanted = _normalize_name(name)
        for char in self.characters:
            if _normalize_name(char.name) == wanted:
                return char
        return None

    def get_location(self, location_id: str) -> Optional[ScriptLocation]:
        for loc in self.locations:
            if loc.id == location_id:
                return loc
        return None

    def to_dict(self) -> Dict[str, Any]:
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
            },
            "characters": [asdict(c) for c in self.characters],
            "locations": [asdict(loc) for loc in self.locations],
            "props": [asdict(p) for p in self.props],
            "scenes": [asdict(s) for s in self.scenes],
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

    Studio V1 is detected by a ``# STUDIO SCRIPT V1`` marker line, or by
    a ``PROJECT:`` header together with at least one ``SCENE <n>:``
    header. Anything else is free-form.
    """
    has_marker = False
    has_project = False
    has_scene = False
    for raw in text.splitlines():
        line = raw.strip()
        if _MARKER_RE.match(line):
            has_marker = True
        elif _PROJECT_RE.match(line):
            has_project = True
        elif _SCENE_RE.match(line):
            has_scene = True
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
        seen_headers: Dict[str, int] = {}  # header key -> first line
        seen_singletons: Dict[str, int] = {}  # singleton block -> first line
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
                candidate = explicit.upper()
                # SPEC §7.1: canonical form is L + 3-digit zero-pad
                # ([L2] becomes L002); normalise before dedup so [L2]
                # and [L002] correctly collide as V1E005.
                m_canonical = re.match(r"^L(\d+)$", candidate)
                if m_canonical:
                    candidate = f"L{int(m_canonical.group(1)):03d}"
                if candidate in used_line_ids:
                    error(line, "V1E005",
                          f"LINE_ID {candidate} was already used at line {used_line_ids[candidate]}.")
                else:
                    used_line_ids[candidate] = line
                return candidate
            while True:
                line_counter[0] += 1
                candidate = f"L{line_counter[0]:03d}"
                if candidate not in used_line_ids:
                    used_line_ids[candidate] = line
                    return candidate

        def add_spoken(speaker_label: str, text_value: str, kind_hint: str,
                       explicit_id: Optional[str], line: int) -> None:
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

        def open_block(new_context: str, obj: Any) -> None:
            nonlocal context, context_obj, block_seen, costume_scenes
            close_scene()
            context = new_context
            context_obj = obj
            block_seen = {}
            costume_scenes = set()

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
            """At most one real AMBIENCE / BGM / MEME cue per scene
            (V1E006, SPEC §§6.7-6.9). The cue is still recorded."""
            counts = scene_cue_counts.setdefault(id(scene), {})
            counts[cue_key] = counts.get(cue_key, 0) + 1
            if counts[cue_key] > 1:
                error(line, "V1E006",
                      f"SCENE {scene.number}: at most one {cue_key} line per "
                      f"scene (BGM and MUSIC share one slot); this is "
                      f"the {counts[cue_key]}th.")

        # -- cue parsers (scene context) -----------------------------------

        def add_sfx(value: str, line: int) -> None:
            assert current_scene is not None
            name, params, raw_keys, duplicates = _parse_pipe_params(value)
            check_dup_subkeys("SFX", duplicates, line)
            if check_none_segments("SFX", name, raw_keys, line):
                current_scene.sfx_none = True
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

            # Malformed SCENE / SHOT header attempts (V1E019, SPEC §§2.3,
            # 8.2): a SCENE header without a number, or a SHOT header
            # without an id. Valid headers are handled below.
            if re.match(r"^SCENE\s*:", line, re.IGNORECASE) and not _SCENE_RE.match(line):
                error(lineno, "V1E019",
                      f"Malformed SCENE header {line!r}: expected 'SCENE <n>: <title>'.")
                continue
            if re.match(r"^SCENE\s+\S", line, re.IGNORECASE) and not _SCENE_RE.match(line):
                error(lineno, "V1E019",
                      f"Malformed SCENE header {line!r}: expected 'SCENE <n>: <title>'.")
                continue
            if re.match(r"^SHOT\s*:\s*$", line, re.IGNORECASE):
                error(lineno, "V1E019",
                      "SHOT header is missing its id: expected 'SHOT <id>:'.")
                continue

            # SCENE header (closes any open block).
            m_scene = _SCENE_RE.match(line)
            if m_scene:
                number = int(m_scene.group(1))
                if number in seen_scenes:
                    error(lineno, "V1E003",
                          f"SCENE {number} was already declared at line {seen_scenes[number]}.")
                else:
                    seen_scenes[number] = lineno
                current_scene = StudioScriptScene(
                    number=number, title=m_scene.group(2).strip(), line=lineno)
                doc.scenes.append(current_scene)
                current_shot = None
                current_voice_note = ""
                context = "scene"
                context_obj = current_scene
                continue

            # SHOT header (inside a scene only).
            m_shot = _SHOT_RE.match(line)
            if m_shot and upper.startswith("SHOT"):
                shot_id = m_shot.group(1).strip()
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
                        char = ScriptCharacter(name=rest, line=lineno)
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
                        prop = ScriptProp(name=rest, line=lineno)
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
                    if value.upper() == "AUTO":
                        doc.target_duration = "AUTO"
                    else:
                        m_dur = _DURATION_RE.match(value)
                        if m_dur and float(m_dur.group(1)) >= 0:
                            doc.target_duration = value
                        else:
                            error(lineno, "V1E012",
                                  f"TARGET_DURATION must be AUTO or a plain "
                                  f"non-negative number of seconds (no unit "
                                  f"suffix), got {value!r}.")
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
                m_field = re.match(
                    r"^(ROLE|APPEARANCE|TRAITS|COSTUME|COSTUME_CHANGE|VOICE|VOICE_STYLE|HEAD_RATIO|IDENTITY_ID)\s*:\s*(.*)$",
                    line, re.IGNORECASE)
                if m_field:
                    key = m_field.group(1).upper()
                    value = m_field.group(2).strip()
                    # COSTUME_CHANGE is repeatable (different scenes);
                    # every other CHARACTER field is single-valued.
                    if key != "COSTUME_CHANGE":
                        if key in block_seen:
                            dup_field(lineno, f"CHARACTER {char.name!r}", key,
                                      block_seen[key])
                            continue
                        block_seen[key] = lineno
                    if key == "ROLE":
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
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "location" and isinstance(context_obj, ScriptLocation):
                loc = context_obj
                m_field = re.match(
                    r"^(NAME|PERIOD|GEOGRAPHY|ARCHITECTURE|FEATURES|FOREGROUND|MIDGROUND|BACKGROUND|LIGHTING|WEATHER|PALETTE|FORBIDDEN)\s*:\s*(.*)$",
                    line, re.IGNORECASE)
                if m_field:
                    key = m_field.group(1).upper()
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, f"LOCATION {loc.id!r}", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
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
                    elif key == "FOREGROUND":
                        loc.foreground = value
                    elif key == "MIDGROUND":
                        loc.midground = value
                    elif key == "BACKGROUND":
                        loc.background = value
                    elif key == "LIGHTING":
                        loc.lighting = value
                    elif key == "WEATHER":
                        loc.weather = value
                    elif key == "PALETTE":
                        loc.palette = _split_list(value)
                    elif key == "FORBIDDEN":
                        loc.forbidden = _split_list(value)
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "prop" and isinstance(context_obj, ScriptProp):
                prop = context_obj
                m_field = re.match(
                    r"^(DESCRIPTION|OWNER|SCENES|INTERACTION)\s*:\s*(.*)$",
                    line, re.IGNORECASE)
                if m_field:
                    key = m_field.group(1).upper()
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, f"PROP {prop.name!r}", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
                    if key == "DESCRIPTION":
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
                        prop.interactions = _split_list(value)
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "global_audio":
                m_field = re.match(
                    r"^(NARRATION_GAIN_DB|DIALOGUE_GAIN_DB|AMBIENCE_GAIN_DB|FOLEY_GAIN_DB|SFX_GAIN_DB|BGM_GAIN_DB|BGM_DUCKING_DB|MASTER_LIMIT_DB)\s*:\s*(.*)$",
                    line, re.IGNORECASE)
                if m_field:
                    ukey = m_field.group(1).upper()
                    if ukey in block_seen:
                        dup_field(lineno, "GLOBAL_AUDIO", ukey, block_seen[ukey])
                        continue
                    block_seen[ukey] = lineno
                    key = m_field.group(1).lower()
                    parsed = _parse_float(m_field.group(2), lineno, errors,
                                          "V1E008", f"GLOBAL_AUDIO {key.upper()}")
                    if parsed is not None:
                        setattr(doc.global_audio, key, parsed)
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

            if context == "qa":
                m_field = re.match(
                    r"^(MIN_SCORE|REQUIRE_TECHNICAL|REQUIRE_CREATIVE_REVIEW|LANGUAGE_GATE|MAX_HARD_FAILS)\s*:\s*(.*)$",
                    line, re.IGNORECASE)
                if m_field:
                    key = m_field.group(1).upper()
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, "QA", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
                    if key == "MIN_SCORE":
                        parsed = _parse_float(value, lineno, errors, "V1E008", "QA MIN_SCORE")
                        if parsed is not None:
                            if 0.0 <= parsed <= 10.0:
                                doc.qa.min_score = parsed
                            else:
                                error(lineno, "V1E010",
                                      f"QA MIN_SCORE must be between 0 and 10, got {parsed}.")
                    elif key == "MAX_HARD_FAILS":
                        try:
                            parsed_int = int(value)
                            if parsed_int < 0:
                                raise ValueError
                            doc.qa.max_hard_fails = parsed_int
                        except ValueError:
                            error(lineno, "V1E008",
                                  f"QA MAX_HARD_FAILS must be a non-negative integer, got {value!r}.")
                    else:
                        parsed_bool = _parse_bool(value, lineno, errors, f"QA {key}")
                        if parsed_bool is not None:
                            setattr(doc.qa, key.lower(), parsed_bool)
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "output":
                m_field = re.match(
                    r"^(RESOLUTION|FPS|FORMAT|DRAFT_FOLDER|MASTER)\s*:\s*(.*)$",
                    line, re.IGNORECASE)
                if m_field:
                    key = m_field.group(1).upper()
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, "OUTPUT", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
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
                    elif key == "FORMAT":
                        if value.upper() == "MP4":
                            doc.output.format = "MP4"
                        else:
                            error(lineno, "V1E007",
                                  f"OUTPUT FORMAT must be MP4, got {value!r}.")
                    elif key == "DRAFT_FOLDER":
                        doc.output.draft_folder = value
                    elif key == "MASTER":
                        if value.upper() == "MANUAL_ONLY":
                            doc.output.master = "MANUAL_ONLY"
                        else:
                            error(lineno, "V1E017",
                                  "OUTPUT MASTER must be MANUAL_ONLY: a Master is never automatic.")
                    continue
                note_unsupported(*_split_key_value(line), lineno)
                continue

            if context == "end_card" and isinstance(context_obj, EndCard):
                card = context_obj
                m_field = re.match(r"^(TEXT|DURATION|STYLE)\s*:\s*(.*)$", line, re.IGNORECASE)
                if m_field:
                    key = m_field.group(1).upper()
                    value = m_field.group(2).strip()
                    if key in block_seen:
                        dup_field(lineno, "END_CARD", key, block_seen[key])
                        continue
                    block_seen[key] = lineno
                    if key == "TEXT":
                        card.text = value
                    elif key == "STYLE":
                        card.style = value
                    elif key == "DURATION":
                        # END_CARD DURATION rejects AUTO and unit suffixes
                        # and requires a positive plain number (SPEC §5.10).
                        if value.upper() == "AUTO":
                            error(lineno, "V1E012",
                                  "END_CARD DURATION does not accept AUTO; "
                                  "it requires a positive number of seconds.")
                        else:
                            m_dur = _DURATION_RE.match(value)
                            if m_dur and float(m_dur.group(1)) > 0:
                                card.duration = float(m_dur.group(1))
                            else:
                                error(lineno, "V1E012",
                                      f"END_CARD DURATION must be a positive "
                                      f"plain number of seconds (no unit "
                                      f"suffix, no AUTO), got {value!r}.")
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
                     "scene_transition": scene_transition},
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
        self._finalize(doc, seen_scenes)

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
            if key == "TYPE":
                shot.type_raw = value
                normalized = _normalize_shot_type(value)
                if normalized in SHOT_TYPES:
                    shot.type = normalized
                else:
                    error(lineno, "V1E014",
                          f"SHOT TYPE must be one of {', '.join(SHOT_TYPES)}, got {value!r}.")
            elif key == "CAMERA":
                shot.camera = value
            elif key == "CAMERA_MOVEMENT":
                movement = _normalize_enum_token(value)
                if movement in CAMERA_MOVEMENTS:
                    shot.camera_movement = movement
                else:
                    error(lineno, "V1E007",
                          f"CAMERA_MOVEMENT must be one of {', '.join(CAMERA_MOVEMENTS)}, got {value!r}.")
            elif key == "SUBJECT":
                shot.subject = value
            elif key == "DURATION":
                shot.duration, shot.duration_seconds = _parse_duration(
                    value, lineno, errors, f"SHOT {shot.id}")
            elif key == "ACTION":
                shot.action = value
            elif key == "EXPRESSION":
                shot.expression = value
            elif key == "VFX":
                shot.vfx = _split_list(value)
            return "shot_field"

        if shot is not None and key in ("LOCATION", "TIME_OF_DAY", "MOOD", "VISUAL"):
            note_unsupported(key, value, lineno)
            return True

        if key == "LOCATION":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            scene.location_text = value
            return True
        if key == "TIME_OF_DAY":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            scene.time_of_day = value
            return True
        if key == "MOOD":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            scene.mood = value
            return True
        if key == "DURATION":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            scene.duration, scene.duration_seconds = _parse_duration(
                value, lineno, errors, f"SCENE {scene.number}")
            return True
        if key == "VISUAL":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            scene.visual = value
            return True
        if key == "TRANSITION":
            # Same field in both positions (§5.4): the same value twice
            # is allowed; different values are V1E006 (first wins).
            transition = _normalize_enum_token(value)
            if transition not in TRANSITIONS:
                error(lineno, "V1E007",
                      f"TRANSITION must be one of {', '.join(TRANSITIONS)}, got {value!r}.")
                return True
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
            scene.actions.append(value)
            return True
        if key == "EXPRESSION":
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
            scene.camera = value
            return True
        if key == "CAMERA_MOVEMENT":
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            movement = _normalize_enum_token(value)
            if movement in CAMERA_MOVEMENTS:
                scene.camera_movement = movement
            else:
                error(lineno, "V1E007",
                      f"CAMERA_MOVEMENT must be one of {', '.join(CAMERA_MOVEMENTS)}, got {value!r}.")
            return True
        if key == "VOICE_NOTE":
            return "voice_note"
        if key == "MEME_NOTE":
            # Supported legacy scene field (§6.13): kept as data, never
            # spoken, never discarded. Single-valued per scene.
            if dup_check(scene_fields, f"SCENE {scene.number}", key):
                return True
            scene.meme_note = value
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
            add_vfx(value, lineno)
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

    def _finalize(self, doc: StudioScriptV1Document, seen_scenes: Dict[int, int]) -> None:
        errors = doc.validation_errors
        warnings = doc.warnings

        def error(line: int, code: str, message: str) -> None:
            errors.append(ValidationIssue(line, code, message))

        # Identity defaults, then duplicate IDENTITY_ID detection (V1E001,
        # SPEC §5.1). Two blocks with the same NAME already reported
        # V1E001 at the header, so only distinct names sharing an id
        # are reported here.
        for char in doc.characters:
            if not char.identity_id:
                char.identity_id = char.name
        seen_identity_ids: Dict[str, ScriptCharacter] = {}
        for char in doc.characters:
            norm_id = _normalize_name(char.identity_id)
            first = seen_identity_ids.get(norm_id)
            if first is None:
                seen_identity_ids[norm_id] = char
            elif _normalize_name(first.name) != _normalize_name(char.name):
                error(char.line, "V1E001",
                      f"IDENTITY_ID {char.identity_id!r} for {char.name!r} "
                      f"duplicates the identity of {first.name!r} "
                      f"(declared at line {first.line}); identities must "
                      f"be unique across characters.")

        # Scene LOCATION references: a value matching a declared LOCATION
        # id under §2.4 normalisation is a reference (stored as the
        # declared id); anything else stays inline free text (§11.4).
        location_ids = {_normalize_name(loc.id): loc.id for loc in doc.locations}
        for scene in doc.scenes:
            if scene.location_text:
                matched = location_ids.get(_normalize_name(scene.location_text))
                if matched is not None:
                    scene.location_ref = matched
                    scene.location_text = ""

        # Speaker resolution (characters may be declared after scenes).
        for scene in doc.scenes:
            for spoken in scene.spoken_lines:
                if spoken.speaker == NARRATOR_SPEAKER:
                    continue
                char = doc.get_character(spoken.speaker)
                if char is not None:
                    spoken.speaker = char.name
                else:
                    error(spoken.line, "V1E015",
                          f"Speaker {spoken.speaker!r} in SCENE {scene.number} "
                          f"is not a declared CHARACTER.")

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

        # SHOT TYPE is required; SUBJECT must resolve (V1E018, an error
        # per SPEC §8.2 — not a warning).
        prop_names = {_normalize_name(p.name) for p in doc.props}
        for scene in doc.scenes:
            for shot in scene.shots:
                if not shot.type and not shot.type_raw:
                    error(shot.line, "V1E013",
                          f"SHOT {shot.id} in SCENE {scene.number} has no TYPE; "
                          f"TYPE is required and must be one of {', '.join(SHOT_TYPES)}.")
                if shot.subject:
                    subject_norm = _normalize_name(shot.subject)
                    if (_is_narrator_label(shot.subject)
                            or doc.get_character(shot.subject) is not None
                            or subject_norm in prop_names):
                        pass
                    else:
                        error(shot.line, "V1E018",
                              f"SHOT {shot.id} SUBJECT {shot.subject!r} does not match "
                              f"a declared CHARACTER or PROP.")
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

        # NONE directives coexisting with real cues of the same type
        # (V1E024, an error: an explicit NONE forbids those cues).
        for scene in doc.scenes:
            types_present = {cue.cue_type for cue in scene.audio_cues}
            if scene.sfx_none and "SFX" in types_present:
                error(scene.line, "V1E024",
                      f"SCENE {scene.number} declares SFX: NONE but also has SFX cues.")
            if scene.ambience_none and "AMBIENCE" in types_present:
                error(scene.line, "V1E024",
                      f"SCENE {scene.number} declares AMBIENCE: NONE but also has AMBIENCE cues.")
            if scene.bgm_none and "BGM" in types_present:
                error(scene.line, "V1E024",
                      f"SCENE {scene.number} declares BGM: NONE but also has BGM cues.")
            if scene.meme_none and "MEME" in types_present:
                error(scene.line, "V1E024",
                      f"SCENE {scene.number} declares MEME: NONE but also has MEME cues.")

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
