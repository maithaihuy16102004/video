"""Scene Event Graph & Information Flow Engine.

Represents narrative events as a strictly causal graph:
- Ordered events with causal parent references.
- Mandatory EventEffect on characters, objects, environment, or information state.
- Spatial mapping of hidden information and reveal mechanisms.
- Epistemic tracking (Viewer Knows vs Character A / B Knows).
"""
from __future__ import annotations

from typing import Any, Optional
from .schemas import (
    EventEffect,
    InformationItem,
    SceneEndState,
    SceneEvent,
    SceneEventGraph,
    ScenePurpose,
    SceneStartState,
)


class SceneEventGraphBuilder:
    """Builds and validates causal event sequences and information flow."""

    @staticmethod
    def build_event_graph(
        scene_purpose: ScenePurpose,
        dramatic_question: str,
        actors: list[str],
        objects: list[str],
        text_context: str = "",
    ) -> SceneEventGraph:
        """Derives a causal event graph where every event produces a tangible state change."""
        events: list[SceneEvent] = []
        info_items: list[InformationItem] = []
        reveals: list[str] = []

        lead = actors[0] if actors else "LEAD"
        partner = actors[1] if len(actors) > 1 else None
        hero_obj = objects[0] if objects else "PRIMARY_OBJECT"

        # Event 1: Initial disruption or arrival
        e1 = SceneEvent(
            event_id="EVT_01",
            description=f"{lead} initiates scene focus regarding {hero_obj}.",
            initiating_actor_id=lead,
            target_object_id=hero_obj,
            causal_trigger_id=None,
            effects=[
                EventEffect(
                    target_type="CHARACTER",
                    target_id=lead,
                    property_changed="attention",
                    old_value="GENERAL",
                    new_value="FOCUSED_ON_OBJECT",
                ),
                EventEffect(
                    target_type="OBJECT",
                    target_id=hero_obj,
                    property_changed="focus_state",
                    old_value="DORMANT",
                    new_value="TARGETED",
                ),
            ],
        )
        events.append(e1)

        # Event 2: Action or confrontation
        e2_desc = f"{partner} reacts and challenges the situation." if partner else f"{lead} performs decisive physical intervention on {hero_obj}."
        e2 = SceneEvent(
            event_id="EVT_02",
            description=e2_desc,
            initiating_actor_id=partner or lead,
            target_object_id=hero_obj,
            causal_trigger_id="EVT_01",
            effects=[
                EventEffect(
                    target_type="BLOCKING",
                    target_id=partner or lead,
                    property_changed="spatial_proximity",
                    old_value="DISTANT",
                    new_value="CLOSE_ENGAGEMENT",
                ),
                EventEffect(
                    target_type="RELATIONSHIP",
                    target_id=f"{lead}_{partner}" if partner else lead,
                    property_changed="tension",
                    old_value="MODERATE",
                    new_value="HIGH_PEAK",
                ),
                EventEffect(
                    target_type="OBJECT",
                    target_id=hero_obj,
                    property_changed="physical_state",
                    old_value="INITIAL",
                    new_value="ENGAGED_OR_OPERATED",
                ),
            ],
        )
        events.append(e2)

        # Event 3: Consequence / Outcome
        e3 = SceneEvent(
            event_id="EVT_03",
            description=f"Physical state of {hero_obj} transforms, answering the dramatic question: '{dramatic_question}'.",
            initiating_actor_id=lead,
            target_object_id=hero_obj,
            causal_trigger_id="EVT_02",
            effects=[
                EventEffect(
                    target_type="OBJECT",
                    target_id=hero_obj,
                    property_changed="physical_state",
                    old_value="ENGAGED_OR_OPERATED",
                    new_value="RESOLVED_OR_REVEALED",
                ),
                EventEffect(
                    target_type="INFORMATION",
                    target_id="SCENE_DRAMATIC_QUESTION",
                    property_changed="epistemic_status",
                    old_value="UNRESOLVED",
                    new_value="RESOLVED",
                ),
                EventEffect(
                    target_type="ENVIRONMENT",
                    target_id="SCENE_ATMOSPHERE",
                    property_changed="ambient_state",
                    old_value="TENSE",
                    new_value="EQUILIBRIUM_SHIFTED",
                ),
            ],
        )
        events.append(e3)

        # Information mapping
        info_items.append(InformationItem(
            item_id="INFO_01_HERO_STATE",
            description=f"Operational condition and physical state of {hero_obj}",
            physical_location=f"ON_SURFACE_OF_{hero_obj}",
            viewer_knows=True,
            character_knowledge={lead: True, **({partner: False} if partner else {})},
            reveal_trigger="LEAD_APPROACHES_AND_INSPECTS",
        ))

        reveals.append("CHARACTER_MOVEMENT_CLEARS_FOREGROUND")
        reveals.append("CLOSE_INSPECTION_REVEALS_DETAIL")

        return SceneEventGraph(
            events=events,
            information_map=info_items,
            reveal_opportunities=reveals,
        )

    @staticmethod
    def derive_start_and_end_states(graph: SceneEventGraph, actors: list[str], hero_obj: str) -> tuple[SceneStartState, SceneEndState]:
        """Computes snapshot differences between scene entrance and scene exit."""
        start_objs = {hero_obj: "INITIAL"}
        end_objs = {hero_obj: "RESOLVED"}

        start_actors = {a: {"action": "ENTER_OR_STAND", "tension": "LOW"} for a in actors}
        end_actors = {a: {"action": "STABILIZED_OR_EXIT", "tension": "RELEASED"} for a in actors}

        start = SceneStartState(
            actors=start_actors,
            object_states=start_objs,
            lighting_state="INITIAL_EQUILIBRIUM",
            information_equilibrium="QUESTION_OPEN",
            power_balance="CONTESTED",
        )
        end = SceneEndState(
            actors=end_actors,
            object_states=end_objs,
            lighting_state="SHIFTED",
            information_equilibrium="QUESTION_RESOLVED",
            power_balance="ESTABLISHED",
            physical_changes_summary=f"{hero_obj} state altered; characters advanced through conflict.",
        )
        return start, end
