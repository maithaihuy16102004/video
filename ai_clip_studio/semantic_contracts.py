"""Semantic production contracts — the single source of truth for story
semantics in AI Clip Studio (Mai's SEMANTIC PRODUCTION ENGINE UPGRADE,
2026-11-12).

Interfaces first: subagents A2 and B2 IMPORT this module and build
against it. They never edit it. ATLAS owns it.

Principle: the immutable STUDIO SCRIPT V1 snapshot is the authoritative
source of story intent; the canonical scene graph is the authoritative
compiled representation; the unified production timeline is the
authoritative source of timing. Downstream modules decide PRESENTATION,
never story meaning. A keyword cue must never override a higher-authority
semantic instruction (the proven Hitler scene-1 contamination: "cúi đầu"
-> bend_pick).
"""

from __future__ import annotations

from dataclasses import dataclass, field, FrozenInstanceError
from enum import IntEnum, Enum
from typing import Any


# ---------------------------------------------------------------------------
# 1. Action resolution authority order (directive §4)
# ---------------------------------------------------------------------------

class ActionAuthority(IntEnum):
    """Lower number wins. Generic keyword cues are PLANNER_SUGGESTION
    at best and must never override a higher-authority instruction."""

    EXPLICIT_DIRECTIVE = 1      # Structured STUDIO SCRIPT V1 directive
    CONTEXTUAL_DESCRIPTION = 2  # Explicit contextual action description
    COMPILED_EVENT = 3          # Canonical compiled action event
    SUPPORTING_ACTION = 4       # Safe supporting action (implied)
    PLANNER_SUGGESTION = 5      # Optional planner suggestion / keyword cue


class ActionOrigin(str, Enum):
    EXPLICIT_SCRIPT_ACTION = "EXPLICIT_SCRIPT_ACTION"
    SAFE_SUPPORTING_ACTION = "SAFE_SUPPORTING_ACTION"
    PLANNER_INFERRED_ACTION = "PLANNER_INFERRED_ACTION"
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
    UNAUTHORIZED_STORY_CHANGE = "UNAUTHORIZED_STORY_CHANGE"


class AuthorizationStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    INFERRED = "INFERRED"            # Planner-inferred, needs provenance
    CONFLICT = "CONFLICT"            # Contradicts a higher authority
    REJECTED = "REJECTED"            # Unauthorized story change: fail


# ---------------------------------------------------------------------------
# 2. Semantic action record (directive §3 — the 16 resolution fields)
# ---------------------------------------------------------------------------

INTERACTION_HANDS = frozenset({"LEFT", "RIGHT", "BOTH", "NONE"})

# Normative semantic action vocabulary. Every entry must have a compiler
# mapping (A2 extends the compiler's verb table; a test in A2's suite
# asserts totality). The seven Mai-specified distinctions are the
# regression seed (see EXAMPLE_RESOLUTIONS).
SEMANTIC_ACTION_TYPES = frozenset({
    "HEAD_TILT_DOWN", "BEND_PICK", "TAKE_FROM_POCKET",
    "PICK_FROM_GROUND", "PICK_FROM_SURFACE", "CROUCH",
    "RECEIVE_PROP", "HAMMER_STRIKE",
    # Established compiler verbs, kept as semantic types:
    "WALK", "RUN", "STOP", "TURN", "LOOK_AT", "GIVE", "TAKE",
    "OPEN", "CLOSE", "PUT_AWAY", "TAKE_OUT", "SIT", "STAND",
    "WAVE", "SHRUG", "NOD", "BREATHE", "WRITE", "SIGN",
    "HAND_OVER", "HOLD", "CARRY", "BOARD", "REACT",
    # Release destinations (regression matrix, 2026-11-12): the
    # transition table already used RELEASE_PROP; the vocabulary
    # now names it, plus PLACE_ON_SURFACE -- a put-down is neither
    # a pocketing (PUT_AWAY) nor a drop (RELEASE_PROP).
    "RELEASE_PROP", "PLACE_ON_SURFACE",
})


@dataclass(frozen=True)
class SemanticAction:
    """One resolved action. Frozen: resolution output is immutable;
    downstream modules consume it, never rewrite it."""

    actor_id: str
    action_type: str
    target_id: str | None
    source_location: str | None
    destination_location: str | None
    body_part: str | None
    interaction_hand: str
    object_state_before: str | None
    object_state_after: str | None
    spatial_relationship: str | None
    action_intent: str | None
    source_scene_id: str
    source_shot_id: str | None
    source_directive_id: str | None
    source_text: str
    confidence: float
    provenance: str  # e.g. "directive:SC01_SH02" / "phrase-rule:take_from_pocket"
    action_origin: ActionOrigin = ActionOrigin.EXPLICIT_SCRIPT_ACTION
    authority: ActionAuthority = ActionAuthority.EXPLICIT_DIRECTIVE
    authorization_status: AuthorizationStatus = AuthorizationStatus.AUTHORIZED

    def __post_init__(self) -> None:
        if self.action_type not in SEMANTIC_ACTION_TYPES:
            raise ValueError(f"unknown semantic action type: {self.action_type!r}")
        if self.interaction_hand not in INTERACTION_HANDS:
            raise ValueError(f"bad interaction_hand: {self.interaction_hand!r}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence out of [0,1]: {self.confidence!r}")
        if not self.source_text.strip():
            raise ValueError("source_text is required (every action traces to text)")
        if not self.source_scene_id:
            raise ValueError("source_scene_id is required")


# Normative examples (directive §2/§3). The parser MUST resolve each
# input to the expected type; the "wrong" column is the regression that
# must never recur. A2's tests assert all rows + Vietnamese paraphrases.
EXAMPLE_RESOLUTIONS: tuple[dict[str, Any], ...] = (
    {"phrase": "Cúi đầu suy nghĩ", "expected": "HEAD_TILT_DOWN",
     "wrong": "BEND_PICK", "body_part": "head"},
    {"phrase": "Cúi xuống nhặt chiếc ví trên đường",
     "expected": "BEND_PICK", "wrong": "HEAD_TILT_DOWN",
     "source_location": "ground"},
    {"phrase": "Lấy ví từ túi áo", "expected": "TAKE_FROM_POCKET",
     "wrong": "PICK_FROM_GROUND", "source_location": "pocket"},
    {"phrase": "Lấy bút trên bàn", "expected": "PICK_FROM_SURFACE",
     "wrong": "TAKE_FROM_POCKET", "source_location": "surface"},
    {"phrase": "Cúi người tránh tiếng pháo", "expected": "CROUCH",
     "wrong": "PICK_FROM_GROUND", "body_part": "torso"},
    {"phrase": "Nhận tia sét bằng tay phải", "expected": "RECEIVE_PROP",
     "wrong": "SPAWN_PROP", "interaction_hand": "RIGHT"},
    {"phrase": "Cyclops đập búa", "expected": "HAMMER_STRIKE",
     "wrong": "GENERIC_ATTACK"},
    {"phrase": "An đánh rơi chìa khóa", "expected": "RELEASE_PROP",
     "wrong": "PUT_AWAY", "body_part": "hand"},
    {"phrase": "Hitler đặt bút xuống", "expected": "PLACE_ON_SURFACE",
     "wrong": "PUT_AWAY", "body_part": "hand"},
)


# ---------------------------------------------------------------------------
# 3. Prop states (directive §7) — independent dimensions
# ---------------------------------------------------------------------------

class PropLocation(str, Enum):
    IN_POCKET = "IN_POCKET"
    ON_SURFACE = "ON_SURFACE"
    ON_GROUND = "ON_GROUND"
    HELD_LEFT = "HELD_LEFT"
    HELD_RIGHT = "HELD_RIGHT"
    HELD_BOTH = "HELD_BOTH"
    IN_TRANSIT = "IN_TRANSIT"  # Between hands during transfer only


class PropContainer(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PropLifecycle(str, Enum):
    PRESENT = "PRESENT"
    RELEASED = "RELEASED"
    DESTROYED = "DESTROYED"


# Allowed location transitions: (from, action_type) -> to. Anything not
# listed is forbidden and must fail loudly, never silently restage.
# A prop renders on the ground ONLY while its location is ON_GROUND.
PROP_TRANSITIONS: dict[tuple[str, str], str] = {
    ("IN_POCKET", "TAKE_FROM_POCKET"): "HELD_RIGHT",
    ("IN_POCKET", "TAKE_OUT"): "HELD_RIGHT",
    ("ON_SURFACE", "PICK_FROM_SURFACE"): "HELD_RIGHT",
    ("ON_GROUND", "BEND_PICK"): "HELD_RIGHT",
    ("ON_GROUND", "PICK_FROM_GROUND"): "HELD_RIGHT",
    ("HELD_LEFT", "PUT_AWAY"): "IN_POCKET",
    ("HELD_RIGHT", "PUT_AWAY"): "IN_POCKET",
    ("HELD_BOTH", "PUT_AWAY"): "IN_POCKET",
    ("HELD_LEFT", "RELEASE_PROP"): "ON_GROUND",
    ("HELD_RIGHT", "RELEASE_PROP"): "ON_GROUND",
    ("HELD_LEFT", "PLACE_ON_SURFACE"): "ON_SURFACE",
    ("HELD_RIGHT", "PLACE_ON_SURFACE"): "ON_SURFACE",
    ("HELD_BOTH", "PLACE_ON_SURFACE"): "ON_SURFACE",
    ("HELD_LEFT", "HAND_OVER"): "IN_TRANSIT",
    ("HELD_RIGHT", "HAND_OVER"): "IN_TRANSIT",
    ("HELD_BOTH", "HAND_OVER"): "IN_TRANSIT",
    ("IN_TRANSIT", "RECEIVE_PROP"): "HELD_RIGHT",
    ("HELD_LEFT", "GIVE"): "IN_TRANSIT",
    ("HELD_RIGHT", "GIVE"): "IN_TRANSIT",
}


def prop_transition_allowed(from_state: str, action_type: str) -> bool:
    return (from_state, action_type) in PROP_TRANSITIONS


def prop_may_rest_on_ground(location: str) -> bool:
    """The contamination fix as a contract rule: ground placement
    requires an explicit ON_GROUND state. Nothing else stages a prop
    on the ground."""
    return location == PropLocation.ON_GROUND.value


# ---------------------------------------------------------------------------
# 4. State scopes (directive §6)
# ---------------------------------------------------------------------------

class StateScope(str, Enum):
    PROJECT = "PROJECT"
    SCENE = "SCENE"
    SHOT = "SHOT"
    EVENT = "EVENT"
    CHARACTER = "CHARACTER"
    PROP = "PROP"


# Inheritance chain for scoped attributes (nearest scope wins):
# SHOT -> SCENE -> PROJECT. EVENT/CHARACTER/PROP scopes attach to their
# entity and never leak sideways. Scene change resets SHOT scope;
# project change resets everything below PROJECT.
SCOPE_INHERITANCE: tuple[StateScope, ...] = (
    StateScope.SHOT, StateScope.SCENE, StateScope.PROJECT,
)


def resolve_scoped_attribute(values: dict[StateScope, Any]) -> Any:
    """Nearest-scope-wins lookup. Scene-specific attributes (rain,
    lighting, costume) set at SCENE scope never propagate to other
    scenes: each scene resolves its own chain."""
    for scope in SCOPE_INHERITANCE:
        if scope in values and values[scope] is not None:
            return values[scope]
    return None


# ---------------------------------------------------------------------------
# 5. Unified production timeline (directive §9)
# ---------------------------------------------------------------------------

TRACKS = frozenset({
    "narration", "dialogue", "actions", "prop_interactions",
    "expressions", "shots", "camera_cuts", "lighting", "vfx",
    "sfx", "ambience", "music", "subtitles", "end_cards",
})


@dataclass(frozen=True)
class TimelineInterval:
    """One immutable interval on one track. Integer frame indices and
    integer audio sample indices are authoritative; seconds are derived
    and must never accumulate drift (recompute from indices)."""

    track: str
    interval_id: str
    start_frame: int
    end_frame: int
    start_sample: int
    end_sample: int
    fps: int = 24
    sample_rate: int = 48000

    def __post_init__(self) -> None:
        if self.track not in TRACKS:
            raise ValueError(f"unknown track: {self.track!r}")
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must exceed start_frame")
        if self.end_sample <= self.start_sample:
            raise ValueError("end_sample must exceed start_sample")
        if self.start_frame < 0 or self.start_sample < 0:
            raise ValueError("negative interval start")

    @property
    def start_sec(self) -> float:
        return self.start_frame / self.fps

    @property
    def end_sec(self) -> float:
        return self.end_frame / self.fps

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame


class FrozenSchedule:
    """The frozen production schedule. After freeze(), any mutation
    attempt raises: downstream modules must not mutate spoken-line
    placement (or any interval) once the schedule is frozen. A
    scheduling conflict requires an explicit rebuild, never a silent
    overwrite."""

    def __init__(self) -> None:
        self._intervals: list[TimelineInterval] = []
        self._frozen = False

    def add(self, interval: TimelineInterval) -> None:
        if self._frozen:
            raise FrozenInstanceError("schedule is frozen; rebuild explicitly")
        self._intervals.append(interval)

    def freeze(self) -> None:
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    def intervals(self, track: str | None = None) -> tuple[TimelineInterval, ...]:
        if track is None:
            return tuple(self._intervals)
        return tuple(i for i in self._intervals if i.track == track)

    def narration_complete(self, expected_ids: list[str]) -> bool:
        """Every spoken line rendered exactly once: the narration track
        carries each expected interval id exactly once."""
        seen = [i.interval_id for i in self.intervals("narration")]
        seen += [i.interval_id for i in self.intervals("dialogue")]
        return sorted(seen) == sorted(expected_ids) and len(seen) == len(set(seen))


# ---------------------------------------------------------------------------
# 6. Conflict detection (directive §4)
# ---------------------------------------------------------------------------

CONFLICT_LEVELS = (
    "parser", "cues", "compiled_events", "shot_staging", "renderer_events",
)


@dataclass(frozen=True)
class ConflictRecord:
    """A semantic disagreement between two levels. An unresolved
    MANDATORY conflict fails semantic preflight — the pipeline must
    not render a story it cannot agree on."""

    level_a: str
    level_b: str
    entity_id: str  # stable canonical id (action / prop / character)
    description: str
    mandatory: bool
    winner_authority: ActionAuthority | None = None  # None = unresolved

    def __post_init__(self) -> None:
        if self.level_a not in CONFLICT_LEVELS or self.level_b not in CONFLICT_LEVELS:
            raise ValueError("unknown conflict level")
        if self.level_a == self.level_b:
            raise ValueError("conflict levels must differ")

    @property
    def fails_preflight(self) -> bool:
        return self.mandatory and self.winner_authority is None


def resolve_conflict(record: ConflictRecord,
                     authority_a: ActionAuthority,
                     authority_b: ActionAuthority) -> ConflictRecord:
    """Higher authority (lower number) wins. Equal authority with
    disagreement stays unresolved -> preflight failure if mandatory."""
    if authority_a == authority_b:
        return record
    winner = authority_a if authority_a < authority_b else authority_b
    return ConflictRecord(
        level_a=record.level_a, level_b=record.level_b,
        entity_id=record.entity_id, description=record.description,
        mandatory=record.mandatory, winner_authority=winner,
    )


__all__ = [
    "ActionAuthority", "ActionOrigin", "AuthorizationStatus",
    "SemanticAction", "SEMANTIC_ACTION_TYPES", "EXAMPLE_RESOLUTIONS",
    "INTERACTION_HANDS",
    "PropLocation", "PropContainer", "PropLifecycle",
    "PROP_TRANSITIONS", "prop_transition_allowed",
    "prop_may_rest_on_ground",
    "StateScope", "SCOPE_INHERITANCE", "resolve_scoped_attribute",
    "TRACKS", "TimelineInterval", "FrozenSchedule",
    "CONFLICT_LEVELS", "ConflictRecord", "resolve_conflict",
]
