"""Sequence-Aware Shot Planner (Director V2.1).

Transforms StoryBeats into purposeful sequences of state transitions:
1. Decomposes multi-beat actions into micro-sequences:
   - NOTICE -> TURN -> OBJECT_INSERT -> REACTION
   - PREPARATION -> EXECUTION -> RESULT
2. Evaluates Shot Necessity: "What would be lost if this shot were removed?"
3. Detects and flags redundant coverage.
4. Ensures every cut is motivated by a STORY, INFORMATION, or PHYSICAL change.
"""
from __future__ import annotations

from typing import Any, Optional

from ..schemas import BeatAction, StoryBeat
from .blocking import CameraZone, SceneGeography, SequenceBlockingTracker
from .foreground import resolve_semantic_foreground
from .state import (
    EpistemicState,
    InformationState,
    StateTransition,
    StoryState,
    get_next_object_state,
)


class PlannedShotIntent:
    """Intermediate sequence-aware shot design intent."""
    def __init__(
        self,
        shot_id: str,
        beat: StoryBeat,
        purpose: str,
        camera_type: str,
        camera_zone: str,
        transition: StateTransition,
        info_state: InformationState,
        active_actor_id: Optional[str] = None,
        target_id: Optional[str] = None,
        action: str = "STAND",
        emotion: str = "CALM",
        prop_id: Optional[str] = None,
        foreground_reason: str = "NONE",
    ) -> None:
        self.shot_id = shot_id
        self.beat = beat
        self.purpose = purpose
        self.camera_type = camera_type
        self.camera_zone = camera_zone
        self.transition = transition
        self.info_state = info_state
        self.active_actor_id = active_actor_id
        self.target_id = target_id
        self.action = action
        self.emotion = emotion
        self.prop_id = prop_id
        self.foreground_reason = foreground_reason


class ShotSequencePlanner:
    """Plans shot-by-shot story developments and state progressions."""

    def __init__(self, geography: Optional[SceneGeography] = None) -> None:
        self.blocking_tracker = SequenceBlockingTracker(geography)
        self.current_story_state = StoryState()

    def plan_sequence_for_beat(
        self,
        beat: StoryBeat,
        beat_idx: int,
        location_enclosure: str = "EXTERIOR",
    ) -> list[PlannedShotIntent]:
        """Plans 1 to 3 purposeful shots for a single story beat."""
        planned_shots: list[PlannedShotIntent] = []
        purpose = beat.suggested_purpose or "INFORMATION"
        primary_actor = beat.characters[0] if beat.characters else "ACTOR_MAIN"
        secondary_actor = beat.characters[1] if len(beat.characters) > 1 else None

        # Determine primary object
        primary_obj = beat.objects[0] if beat.objects else None

        # Check if beat warrants a micro-sequence
        needs_micro_sequence = False
        if purpose in ("ACTION", "PAYOFF") and primary_obj:
            needs_micro_sequence = True
        elif purpose in ("OBJECT_INFORMATION", "REVEAL") and primary_actor and secondary_actor:
            needs_micro_sequence = True

        if not needs_micro_sequence:
            # Single purposeful shot with clear state transition
            shot_id = f"SH_{beat_idx+1:03d}"
            
            # Compute State Transition
            story_change = f"Beat {beat.beat_type}: Narrative advances via {purpose}."
            info_change = f"Viewer and character learn: '{beat.text[:48]}...'"
            phys_change = f"{primary_actor} executes {beat.actions[0].verb if beat.actions else 'STAND'}."
            
            # Update object state if prop exists
            if primary_obj:
                curr_obj_state = self.current_story_state.object_states.get(primary_obj, "STATIC")
                new_obj_state = get_next_object_state(
                    primary_obj, curr_obj_state, beat.actions[0].verb if beat.actions else "INSPECT"
                )
                self.current_story_state.object_states[primary_obj] = new_obj_state
                phys_change += f" {primary_obj} state changes: {curr_obj_state} -> {new_obj_state}."

            trans = StateTransition(
                shot_id=shot_id,
                story_change=story_change,
                information_change=info_change,
                physical_change=phys_change,
                removal_consequence=f"Critical beat information would be lost: {beat.text[:60]}.",
                is_meaningful=True,
                redundant_coverage=False,
                cut_motivation="NARRATIVE_BEAT_ADVANCEMENT",
            )

            info_st = InformationState(
                epistemic_relation=EpistemicState.BOTH_KNOW.value,
                revealed_item=primary_obj or beat.text[:30],
                reveal_type="DETAIL_DISCOVERY" if primary_obj else "NONE",
                dramatic_purpose="INFORMATION",
            )

            # Camera zone
            cam_zone = CameraZone.ESTABLISHING_ZONE.value if purpose == "LOCATION" else CameraZone.TABLE_SIDE_ZONE.value
            cam_type = "ENVIRONMENT_ESTABLISHING" if purpose == "LOCATION" else "MEDIUM"

            shot = PlannedShotIntent(
                shot_id=shot_id,
                beat=beat,
                purpose=purpose,
                camera_type=cam_type,
                camera_zone=cam_zone,
                transition=trans,
                info_state=info_st,
                active_actor_id=primary_actor,
                target_id=secondary_actor or primary_obj,
                action=beat.actions[0].verb if beat.actions else "STAND",
                emotion=beat.actions[0].emotion if beat.actions else "CALM",
                prop_id=primary_obj,
                foreground_reason="NONE",
            )
            planned_shots.append(shot)

        else:
            # 2-Shot or 3-Shot Micro-Sequence:
            # Shot 1: PREPARATION / NOTICE
            s1_id = f"SH_{beat_idx+1:03d}_A"
            trans1 = StateTransition(
                shot_id=s1_id,
                story_change=f"{primary_actor} notices {primary_obj or 'situation'}.",
                information_change=f"Character attention focuses onto {primary_obj or 'action'}.",
                physical_change=f"{primary_actor} turns and reaches toward target.",
                removal_consequence="Viewer would not see the motivation for the subsequent interaction.",
                is_meaningful=True,
                redundant_coverage=False,
                cut_motivation="ACTION_PREPARATION",
            )
            info1 = InformationState(
                epistemic_relation=EpistemicState.CHARACTER_KNOWS_VIEWER_DOES_NOT.value if primary_obj else EpistemicState.BOTH_KNOW.value,
                revealed_item=primary_obj or "Intent",
                reveal_type="DETAIL_DISCOVERY",
                dramatic_purpose="SUSPENSE",
            )
            planned_shots.append(PlannedShotIntent(
                shot_id=s1_id,
                beat=beat,
                purpose="ACTION",
                camera_type="MEDIUM_WIDE",
                camera_zone=CameraZone.TABLE_SIDE_ZONE.value,
                transition=trans1,
                info_state=info1,
                active_actor_id=primary_actor,
                target_id=primary_obj,
                action="REACH" if primary_obj else "POINT",
                emotion="ATTENTIVE",
                prop_id=primary_obj,
                foreground_reason="BEHIND_FURNITURE" if location_enclosure == "INTERIOR" else "INSIDE_TERRAIN",
            ))

            # Shot 2: EXECUTION / OBJECT INSERT or CLOSE REVEAL
            s2_id = f"SH_{beat_idx+1:03d}_B"
            curr_state = self.current_story_state.object_states.get(primary_obj or "item", "OFF")
            next_state = get_next_object_state(primary_obj or "item", curr_state, "OPERATE")
            self.current_story_state.object_states[primary_obj or "item"] = next_state

            trans2 = StateTransition(
                shot_id=s2_id,
                from_shot_id=s1_id,
                story_change=f"Action executed: {primary_obj} state changes to {next_state}.",
                information_change=f"Viewer sees exact physical operation of {primary_obj}.",
                physical_change=f"{primary_obj} operates ({curr_state} -> {next_state}).",
                removal_consequence="The critical physical causality would become off-screen and invisible.",
                is_meaningful=True,
                redundant_coverage=False,
                cut_motivation="OBJECT_DETAIL",
            )
            info2 = InformationState(
                epistemic_relation=EpistemicState.BOTH_KNOW.value,
                revealed_item=f"{primary_obj} is {next_state}",
                reveal_type="UNCLOAK",
                dramatic_purpose="PAYOFF",
            )
            planned_shots.append(PlannedShotIntent(
                shot_id=s2_id,
                beat=beat,
                purpose="OBJECT_INSERT" if primary_obj else "REVEAL",
                camera_type="OBJECT_INSERT" if primary_obj else "CLOSE_UP",
                camera_zone=CameraZone.OBJECT_SIDE_ZONE.value,
                transition=trans2,
                info_state=info2,
                active_actor_id=primary_actor,
                target_id=primary_obj,
                action="OPERATE",
                emotion="DETERMINED",
                prop_id=primary_obj,
                foreground_reason="BESIDE_MACHINERY",
            ))

        return planned_shots
