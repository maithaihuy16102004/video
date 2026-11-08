"""Sequence-Aware Story State, Information State, and State Transitions.

Implements the fundamental Director V2.1 principle:
STORY STATE A -> ACTION -> INFORMATION CHANGE -> REACTION -> PHYSICAL CHANGE -> STORY STATE B.

Every transition tracks three types of change:
1. STORY_CHANGE (dramatic goal, problem, tension, relationship)
2. INFORMATION_CHANGE (what character knows vs what viewer knows; epistemic reveal)
3. PHYSICAL_CHANGE (object state, character position/orientation, environment state)

Camera change alone is never considered a sufficient justification for a cut.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import Field

from ..schemas import UModel


class EpistemicState(str, Enum):
    VIEWER_KNOWS_CHARACTER_DOES_NOT = "VIEWER_KNOWS_CHARACTER_DOES_NOT"
    CHARACTER_KNOWS_VIEWER_DOES_NOT = "CHARACTER_KNOWS_VIEWER_DOES_NOT"
    BOTH_KNOW = "BOTH_KNOW"
    NEITHER_KNOWS = "NEITHER_KNOWS"


class StoryState(UModel):
    """Rich narrative state across a sequence of shots."""
    current_goal: str = ""
    current_problem: str = ""
    known_information: list[str] = Field(default_factory=list)
    unknown_information: list[str] = Field(default_factory=list)
    character_attention: dict[str, str] = Field(default_factory=dict)     # actor_id -> target_id/object
    character_emotion: dict[str, str] = Field(default_factory=dict)       # actor_id -> emotion
    object_states: dict[str, str] = Field(default_factory=dict)           # prop_id -> state (e.g. CLOSED, ACTIVE, READ)
    relationship_state: dict[str, str] = Field(default_factory=dict)     # pair -> relation
    environment_event: str = "NONE"                                       # active event ID
    immediate_threat: str = "NONE"
    pending_reveal: str = "NONE"


class InformationState(UModel):
    """Tracks narrative divergence between viewer awareness and character awareness."""
    epistemic_relation: str = EpistemicState.BOTH_KNOW.value
    revealed_item: str = ""
    reveal_type: str = "NONE"          # NONE | UNCLOAK | DETAIL_DISCOVERY | REACTION_CONFIRMATION | CAUSE_REVEAL
    viewer_knows: bool = True
    character_knows: bool = True
    dramatic_purpose: str = "INFORMATION"  # SUSPENSE | DRAMATIC_IRONY | SURPRISE | PAYOFF | COMEDY


class StateTransition(UModel):
    """Explicit measurement of what changed between Shot N and Shot N+1."""
    shot_id: str
    from_shot_id: Optional[str] = None
    story_change: str = "NONE"
    information_change: str = "NONE"
    physical_change: str = "NONE"
    reaction_to_event_id: Optional[str] = None
    removal_consequence: str = ""
    is_meaningful: bool = True
    redundant_coverage: bool = False
    cut_motivation: str = "STORY_ACTION"


# -----------------------------------------------------------------------------
# GENERIC OBJECT STATE MACHINES
# -----------------------------------------------------------------------------

GENERIC_OBJECT_STATE_MACHINES: dict[str, list[str]] = {
    "DOCUMENT": ["SEALED", "OPENING", "OPEN", "READ", "HANDED_OVER", "DROPPED"],
    "LETTER": ["SEALED", "OPENING", "OPEN", "READ", "HANDED_OVER", "DROPPED"],
    "DOOR": ["CLOSED", "UNLATCHING", "OPENING", "AJAR", "FULLY_OPEN"],
    "MACHINE": ["OFF", "ADJUSTED", "ENERGIZED", "ACTIVE", "SPARKING", "FAILED"],
    "APPARATUS": ["OFF", "ADJUSTED", "ENERGIZED", "ACTIVE", "SPARKING", "FAILED"],
    "TELEGRAPH": ["IDLE", "CONNECTING", "RECEIVING", "PULSING", "CONFIRMED"],
    "OVEN": ["COLD", "CHECKED", "SWITCH_TRIPPED", "RESET", "WARMING", "BAKING"],
    "SWITCH": ["OFF", "TRIPPED", "REACHED", "RESET", "ENGAGED"],
    "CRATE": ["CLOSED_STACK", "UNLATCHED", "OPEN_TILTED", "EMPTY"],
    "WEAPON": ["HOLSTERED", "DRAWN", "AIMED", "DISCHARGED", "LOWERED"],
    "GLASS": ["FULL", "LIFTED", "DRINKING", "EMPTY", "SLAPPED_ON_TABLE"],
}


def _resolve_object_category(raw_name: str) -> str:
    """Maps arbitrary prop/object names to canonical state machine categories."""
    upper = raw_name.upper()
    if any(k in upper for k in ("DOC", "LETTER", "PAPER", "DECREE", "TREATY", "DISPATCH", "SEAL")):
        return "DOCUMENT"
    if any(k in upper for k in ("SWITCH", "BREAKER", "LEVER", "BUTTON")):
        return "SWITCH"
    if any(k in upper for k in ("OVEN", "HEARTH", "STOVE", "FURNACE")):
        return "OVEN"
    if any(k in upper for k in ("TELEGRAPH", "SIGNAL", "WIRE", "CABLE", "INSULATOR", "NEEDLE")):
        return "TELEGRAPH"
    if any(k in upper for k in ("DOOR", "GATE", "PORTAL", "HATCH")):
        return "DOOR"
    if any(k in upper for k in ("WEAPON", "RIFLE", "PISTOL", "SWORD")):
        return "WEAPON"
    if any(k in upper for k in ("GLASS", "BOTTLE", "CUP", "MUG", "CARAFE")):
        return "GLASS"
    if any(k in upper for k in ("MACHINE", "ENGINE", "MOTOR", "DEVICE", "APPARATUS")):
        return "APPARATUS"
    return "APPARATUS"


def get_next_object_state(category: str, current_state: str, action: str) -> str:
    """Deterministically advances object state based on character action and narrative progression."""
    canonical_cat = _resolve_object_category(category)
    states = GENERIC_OBJECT_STATE_MACHINES.get(canonical_cat, ["STATIC", "INTERACTED", "ACTIVE", "RESOLVED"])

    act = action.upper()
    if act in ("OPEN", "UNLATCH", "UNSEAL"):
        for s in ("OPENING", "OPEN", "UNSEALED", "UNLATCHED"):
            if s in states: return s
    elif act in ("READ", "INSPECT", "POINT", "OBSERVE", "EXAMINE", "CHECK"):
        for s in ("READ", "CHECKED", "INSPECTED", "IDENTIFIED", "CONNECTING", "CONFIRMED"):
            if s in states: return s
        return "INSPECTED" if "INSPECTED" in states else states[min(1, len(states) - 1)]
    elif act in ("OPERATE", "ADJUST", "SWITCH", "RESET", "REPAIR", "ENGAGE", "TOUCH", "REACH"):
        for s in ("RESET", "ACTIVE", "ENERGIZED", "PULSING", "ADJUSTED", "RECEIVING"):
            if s in states: return s
        return "ACTIVE" if "ACTIVE" in states else states[min(2, len(states) - 1)]
    elif act in ("HAND_OVER", "GIVE", "TRANSFER", "DELIVER"):
        for s in ("HANDED_OVER", "TRANSFERRED", "DELIVERED_SEALED", "CONFIRMED"):
            if s in states: return s
        return "HANDED_OVER" if "HANDED_OVER" in states else "MOVED"
    elif act in ("DROP", "FALL", "SNAP", "BREAK", "TRIP"):
        for s in ("SWITCH_TRIPPED", "TRIPPED", "DROPPED", "FAILED", "SPARKING"):
            if s in states: return s
        return "TRIPPED" if "TRIPPED" in states else "MOVED"

    # Sequential progression
    if current_state in states:
        idx = states.index(current_state)
        if idx + 1 < len(states):
            return states[idx + 1]
        return current_state
    
    # If starting from INITIAL or unknown state, pick first sensible state
    return states[1] if len(states) > 1 else states[0]
