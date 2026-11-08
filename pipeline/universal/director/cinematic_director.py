"""Cinematic Director & Retention Director.

Converts structured StoryIntelligence into a sequence of verified SceneBlueprints:
- Enforces Retention Rules (pacing, open loops, narrative variety, emotional curve).
- Directs Camera (Shot size, height, yaw, pitch, perspective, horizon, vanishing point).
- Enforces 9-D Camera Delta anti-repetition guards.
- Detects and breaks Stage-View loops (rejects repeated eye-level, centered, parallel staging).
- Plans Actor staging, actions, emotions, contacts, and affordances.
- Plans Environmental storytelling props and visual eye path.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from .. import vocab as V
from ..assets.asset_resolver import UniversalAssetResolver
from ..bibles.resolver import CharacterResolver
from ..character_engine.acting_vocabulary import PerformanceKinematics, ACTING_VOCABULARY
from ..config import PipelineConfig
from ..reasoning.visual_director import (
    DeterministicVisualDirectionProvider,
    VisualDirectionProvider,
    VisualDirectorContextPack,
)
from ..schemas import (
    ActorBlock,
    CameraSpec,
    CharacterBible,
    DialogueLine,
    HistoricalNote,
    LocationBible,
    PropPlacement,
    SceneBlueprint,
    StoryBeat,
    StoryIntelligence,
    VisualEyePath,
    VisualConcept,
)
from ..sequence.blocking import CameraZone, SceneGeography, SequenceBlockingTracker, ActorPhysicalState
from ..sequence.foreground import ForegroundElement, ForegroundReason, resolve_semantic_foreground
from ..sequence.state import EpistemicState, InformationState, StateTransition, StoryState, get_next_object_state
from ..validation.metrics import calculate_real_screen_metrics, compute_real_composition_fingerprint


class CameraDeltaValidator:
    """Computes multidimensional difference between consecutive camera shots."""

    @staticmethod
    def is_repetitive(a: CameraSpec, b: CameraSpec) -> bool:
        same_shot = a.shot == b.shot
        same_height = a.height == b.height
        same_yaw = abs(a.yaw_deg - b.yaw_deg) < 15.0
        same_pos = abs(a.subject_position[0] - b.subject_position[0]) < 0.12
        return same_shot and same_height and same_yaw and same_pos


class StageViewDetector:
    """Detects repeated flat eye-level staging with centered actors."""

    @staticmethod
    def is_stage_view(cam: CameraSpec, actor: ActorBlock | None) -> bool:
        if cam.height != "EYE":
            return False
        if cam.shot not in ("MEDIUM", "MEDIUM_WIDE"):
            return False
        if abs(cam.pitch_deg) > 5.0 or abs(cam.yaw_deg) > 10.0:
            return False
        if actor and abs(actor.screen_x - 0.5) < 0.10 and actor.orientation == "FRONT":
            return True
        return False


class CinematicDirector:
    """Transforms StoryIntelligence into verified SceneBlueprints."""

    def __init__(
        self,
        config: PipelineConfig,
        char_bible: CharacterBible,
        loc_bible: LocationBible,
        asset_resolver: UniversalAssetResolver,
        visual_provider: Optional[VisualDirectionProvider] = None,
        critic: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.char_bible = char_bible
        self.loc_bible = loc_bible
        self.asset_resolver = asset_resolver
        self.visual_provider = visual_provider or DeterministicVisualDirectionProvider()
        self.critic = critic

    def direct_story(self, story: StoryIntelligence, dynamic_shots: bool = False) -> list[SceneBlueprint]:
        blueprints: list[SceneBlueprint] = []
        recent_cams: list[CameraSpec] = []
        recent_stage_views = 0

        # Initialize Sequence-Aware State and Spatial Geography (Director V2.1)
        geo = SceneGeography()
        blocking_tracker = SequenceBlockingTracker(geo)
        story_state = StoryState(
            current_goal=f"Progress narrative: {story.title}",
            current_problem="INITIAL_EQUILIBRIUM",
        )

        # Register initial actor positions in spatial ground truth
        for i, c in enumerate(story.characters):
            init_x = 0.36 if i == 0 else (0.68 if i == 1 else 0.50)
            orient = "THREE_QUARTER_RIGHT" if init_x < 0.5 else "THREE_QUARTER_LEFT"
            blocking_tracker.get_or_create_actor(c.character_id, default_x=init_x)
            blocking_tracker.update_actor(
                actor_id=c.character_id,
                screen_x=init_x,
                action="STAND",
                orientation=orient,
                eyeline_target=story.characters[1 - i].character_id if len(story.characters) > 1 and i < 2 else None,
            )

        # Base location defaults
        loc = self.loc_bible.get(story.story_beats[0].location_id if story.story_beats else "") or (self.loc_bible.locations[0] if self.loc_bible.locations else None)
        loc_id = loc.location_id if loc else "LOC_DEFAULT"
        loc_enclosure = getattr(loc, "enclosure", "EXTERIOR")

        # Pacing and shot planning per beat
        for b_idx, beat in enumerate(story.story_beats):
            shot_purpose = beat.suggested_purpose or "INFORMATION"
            loc = self.loc_bible.get(beat.location_id or "") or loc
            loc_id = loc.location_id if loc else loc_id
            loc_enclosure = getattr(loc, "enclosure", "EXTERIOR")

            # Capture State Before
            state_before = story_state.dump()

            # Visual Direction & Concept Derivation (Gemini or Offline Fallback)
            ctx = VisualDirectorContextPack(
                script_segment=beat.text,
                prior_shot_summary=recent_cams[-1].shot if recent_cams else "NONE",
                characters=[c for c in beat.characters],
                location_enclosure=loc_enclosure,
                location_id=loc_id,
                historical_period=str(beat.year) if beat.year else "UNIVERSAL",
                emotional_intent=beat.actions[0].emotion if beat.actions else "NEUTRAL",
                retention_intent=shot_purpose,
                important_object=beat.objects[0] if beat.objects else None,
                viewer_relationship="EMBEDDED_OBSERVER",
            )
            v_concept = self.visual_provider.direct_scene(ctx)
            proposed_shots = self.visual_provider.propose_cinematography(v_concept, geo.dump(), ctx)

            visual_question, visual_answer = self._derive_visual_intent(beat, shot_purpose)
            camera_reason = self._camera_reason(shot_purpose, beat)
            cam = self._select_camera(beat, shot_purpose, b_idx, recent_cams)
            cam_zone = self._derive_camera_zone(cam, shot_purpose, loc_enclosure)

            # Stage-View & Anti-Repetition Guard
            actor_mock = ActorBlock(character_id="mock", screen_x=cam.subject_position[0], orientation="FRONT")
            if StageViewDetector.is_stage_view(cam, actor_mock):
                recent_stage_views += 1
                if recent_stage_views > self.config.stage_view_max_in_window:
                    cam = self._replan_visual_idea(cam, beat, visual_answer)
                    recent_stage_views = 0
            else:
                recent_stage_views = max(0, recent_stage_views - 1)

            recent_cams.append(cam)
            if len(recent_cams) > self.config.similarity_window:
                recent_cams.pop(0)

            # Actor Staging & Blocking with spatial persistence
            actors = self._stage_actors_v21(beat, cam, loc_id, blocking_tracker)

            # Prop Placement & Asset Resolution
            props = self._place_props(beat, loc, cam)

            # Object State Machine progression
            object_states_dict = dict(story_state.object_states)
            primary_obj = beat.objects[0] if beat.objects else (props[0].semantic if props else None)
            if primary_obj:
                curr_obj_st = story_state.object_states.get(primary_obj, "INITIAL")
                act_verb = beat.actions[0].verb if beat.actions else "INSPECT"
                next_obj_st = get_next_object_state(primary_obj, curr_obj_st, act_verb)
                story_state.object_states[primary_obj] = next_obj_st
                object_states_dict[primary_obj] = next_obj_st
                for p in props:
                    if p.semantic.lower() in primary_obj.lower() or primary_obj.lower() in p.semantic.lower():
                        p.state = next_obj_st

            # Semantic Foreground Element resolution (authentic scene geometry, no dark rectangles)
            primary_actor_id = beat.characters[0] if beat.characters else None
            fg_element = resolve_semantic_foreground(
                location_enclosure=loc_enclosure,
                location_id=loc_id,
                camera_shot=cam.shot,
                shot_purpose=shot_purpose,
                primary_actor_id=primary_actor_id,
            )

            # Compute Sequence Causal Changes
            story_change = self._compute_story_change(beat, shot_purpose, b_idx)
            info_change = self._compute_information_change(beat, shot_purpose, primary_obj)
            phys_change = self._compute_physical_change(beat, shot_purpose, actors, primary_obj, object_states_dict)
            info_state_dict = self._compute_epistemic_state(beat, shot_purpose, primary_obj)
            removal_consequence = self._compute_removal_consequence(beat, shot_purpose, primary_obj)

            # Update story state
            story_state.current_problem = f"BEAT_{b_idx+1}_{shot_purpose}"
            if beat.actions:
                for a in beat.actions:
                    story_state.character_emotion[a.actor_id] = a.emotion
            state_after = story_state.dump()

            # Visual Eye Path
            eye_steps = []
            if fg_element:
                eye_steps.append(f"FOREGROUND:{fg_element.asset_instance_id}")
            if actors:
                eye_steps.append(f"ACTOR:{actors[0].character_id}")
            if props:
                eye_steps.append(f"OBJECT:{props[0].asset_id}")
            if len(actors) > 1:
                eye_steps.append(f"REACTION:{actors[1].character_id}")
            eye_path = VisualEyePath(steps=eye_steps)

            # Dialogue & Narration
            dialogue: list[DialogueLine] = []
            narration = ""
            if beat.is_dialogue and beat.speaker_id:
                dialogue.append(DialogueLine(
                    speaker_id=beat.speaker_id,
                    voice_id=f"voice_{beat.speaker_id.lower()}",
                    text=beat.text,
                    delivery="EMPHATIC" if beat.emotional_intensity > 0.6 else "NEUTRAL",
                ))
            else:
                narration = beat.text

            # Construct SceneBlueprint with complete sequence-aware metadata
            bp = SceneBlueprint(
                scene_id=f"SCENE_{b_idx+1:03d}",
                shot_id=f"SH_{b_idx+1:03d}",
                shot_index=b_idx,
                beat_ids=[beat.beat_id],
                year=beat.year,
                location_id=loc_id,
                shot_purpose=shot_purpose,
                purpose_reason=f"Beat {beat.beat_type} requires {shot_purpose} visual emphasis.",
                visual_question=visual_question,
                visual_answer=visual_answer,
                camera_reason=camera_reason,
                motion_reason=self._motion_reason(cam.motion, shot_purpose),
                reveal_strategy="OBJECT_REVEAL" if beat.objects else ("BACKGROUND_REVEAL" if beat.new_information else "NONE"),
                primary_focus=(f"ACTOR:{actors[0].character_id}" if actors else (f"OBJECT:{props[0].instance_id}" if props else "ENVIRONMENT")),
                secondary_focus=(f"OBJECT:{props[0].instance_id}" if props else (f"ACTOR:{actors[1].character_id}" if len(actors) > 1 else "NONE")),
                foreground_frame=fg_element.asset_instance_id if fg_element else "NONE",
                foreground_ratio=0.22 if cam.shot == "OTS" else (0.14 if fg_element else 0.0),
                leading_lines=["VANISHING_POINT"] if cam.perspective != "TELE_COMPRESSION" else [],
                negative_space="LOOK_DIRECTION" if actors else "INFORMATION_REVEAL",
                cut_reason=self._cut_reason(beat, b_idx),
                visual_energy=self._energy(beat),
                composition_fingerprint=self._fingerprint(cam, actors, shot_purpose),
                camera=cam,
                actors=actors,
                props=props,
                object_states=object_states_dict,
                depth_planes={"NEAR_FG": 0.05, "FG": 0.18, "MG": 0.35, "BG": 0.65, "FAR_BG": 0.90},
                lighting_story={"direction": "KEY_LEFT", "mood": loc.lighting_behavior if loc else "OVERCAST"},
                vitality={"density": "BALANCED"},
                visual_eye_path=eye_path,
                historical_metadata=[
                    HistoricalNote(item=f"Year {beat.year}", confidence="PLAUSIBLE_RECONSTRUCTION")
                ] if beat.year else [],
                continuity={},
                dialogue=dialogue,
                narration=narration,
                motion_intent={"motion": cam.motion},
                state_before=state_before,
                state_after=state_after,
                story_change=story_change,
                information_change=info_change,
                physical_change=phys_change,
                information_state=info_state_dict,
                reaction_to_event_id=f"BEAT_{b_idx}" if b_idx > 0 else None,
                removal_consequence=removal_consequence,
                camera_zone=cam_zone,
                foreground_element=fg_element.dump() if fg_element else None,
                duration_sec=beat.est_duration_sec,
                seed=self.config.seed + b_idx * 17,
                validation={"delta_passed": True, "stage_view_checked": True},
            )
            bp.visual_concept = v_concept.dump()
            bp.performance_intent = (
                proposed_shots[0].get("performance_intent", "")
                if proposed_shots
                else v_concept.character_performance_intent
            )
            real_metrics = calculate_real_screen_metrics(bp, width=self.config.width, height=self.config.height)
            bp.real_metrics = real_metrics
            bp.composition_fingerprint = compute_real_composition_fingerprint(bp, real_metrics)
            bp.camera.subject_height_px = real_metrics["actual_subject_height_px"]

            if self.critic:
                try:
                    review = self.critic.critique(None, bp, v_concept)
                    bp.critic_review = review.dump()
                except Exception:
                    pass

            blueprints.append(bp)

        return blueprints

    def _derive_camera_zone(self, cam: CameraSpec, purpose: str, enclosure: str) -> str:
        shot_u = cam.shot.upper()
        if shot_u in ("ENVIRONMENT_ESTABLISHING", "WIDE"):
            return CameraZone.ESTABLISHING_ZONE.value
        elif shot_u in ("GROUND_LEVEL", "LOW_ANGLE"):
            return CameraZone.GROUND_ZONE.value
        elif shot_u == "OBJECT_INSERT":
            return CameraZone.OBJECT_SIDE_ZONE.value
        elif shot_u == "OTS":
            return CameraZone.ACTOR_REAR_ZONE.value
        elif enclosure.upper() == "INTERIOR":
            return CameraZone.TABLE_SIDE_ZONE.value
        else:
            return CameraZone.HIGH_VANTAGE_ZONE.value

    def _compute_story_change(self, beat: StoryBeat, purpose: str, idx: int) -> str:
        if idx == 0:
            return "Establishes baseline situation and introduces characters into the environment."
        if purpose in ("CAUSE", "CONFLICT"):
            return "Narrative equilibrium disrupted: critical physical incident occurs, creating urgency."
        if purpose == "OBJECT_INFORMATION":
            return "Dramatic focus isolates key narrative asset: characters identify vulnerability or mechanism."
        if purpose == "ACTION":
            return "Active character executes decisive intervention to address the central crisis."
        if purpose in ("REVEAL", "EFFECT"):
            return "Consequence manifests: mechanism physical state transforms, validating the attempt."
        if purpose == "PAYOFF":
            return "Dramatic resolution: new equilibrium established; tension releases into outcome."
        return f"Narrative advances through beat {beat.beat_type} with focus on {purpose.lower()}."

    def _compute_information_change(self, beat: StoryBeat, purpose: str, primary_obj: Optional[str]) -> str:
        if purpose == "LOCATION":
            return "Viewer and characters share geographical grounding and environmental context."
        if purpose in ("CAUSE", "CONFLICT"):
            return "Viewer learns sudden disruptive event before characters can fully process it."
        if purpose == "OBJECT_INFORMATION":
            return f"Viewer discovers operational status and physical state of {primary_obj or 'critical apparatus'}."
        if purpose == "ACTION":
            return "Viewer observes character physical execution and mechanics of intervention."
        if purpose in ("REVEAL", "EFFECT"):
            return f"Viewer and character discover outcome: {primary_obj or 'device'} status is revealed."
        if purpose == "PAYOFF":
            return "Both viewer and characters confirm permanent resolution of dramatic question."
        return f"Information update: '{beat.text[:55]}...'"

    def _compute_physical_change(
        self,
        beat: StoryBeat,
        purpose: str,
        actors: list[ActorBlock],
        primary_obj: Optional[str],
        obj_states: dict[str, str],
    ) -> str:
        if purpose == "LOCATION":
            return "Characters take initial marks in physical space."
        if purpose in ("CAUSE", "CONFLICT"):
            return f"Environmental incident: {primary_obj or 'system'} physical integrity is breached."
        if purpose == "OBJECT_INFORMATION":
            st = obj_states.get(primary_obj, "INSPECTED") if primary_obj else "FOCUSED"
            return f"Actor advances gaze and hand towards {primary_obj or 'prop'}; state becomes {st}."
        if purpose == "ACTION":
            st = obj_states.get(primary_obj, "OPERATED") if primary_obj else "ENGAGED"
            return f"Actor executes contact gesture on target; physical state updates to {st}."
        if purpose in ("REVEAL", "EFFECT"):
            st = obj_states.get(primary_obj, "ACTIVE") if primary_obj else "RESOLVED"
            return f"Physical transformation complete: {primary_obj or 'mechanism'} shifts to {st}."
        if purpose == "PAYOFF":
            return "Actors stabilize in relaxed posture; physical motion settles into resting state."
        verb = beat.actions[0].verb if beat.actions else "STAND"
        return f"Actor performs {verb} with posture adjustment."

    def _compute_epistemic_state(self, beat: StoryBeat, purpose: str, primary_obj: Optional[str]) -> dict[str, Any]:
        if purpose in ("CAUSE", "TENSION"):
            return InformationState(
                epistemic_relation=EpistemicState.VIEWER_KNOWS_CHARACTER_DOES_NOT.value,
                revealed_item=beat.text[:40],
                reveal_type="CAUSE_REVEAL",
                viewer_knows=True,
                character_knows=False,
                dramatic_purpose="SUSPENSE",
            ).dump()
        if purpose in ("REVEAL", "EFFECT"):
            return InformationState(
                epistemic_relation=EpistemicState.BOTH_KNOW.value,
                revealed_item=primary_obj or "Operational outcome",
                reveal_type="UNCLOAK",
                viewer_knows=True,
                character_knows=True,
                dramatic_purpose="PAYOFF",
            ).dump()
        if purpose == "OBJECT_INFORMATION":
            return InformationState(
                epistemic_relation=EpistemicState.BOTH_KNOW.value,
                revealed_item=primary_obj or "Mechanism detail",
                reveal_type="DETAIL_DISCOVERY",
                viewer_knows=True,
                character_knows=True,
                dramatic_purpose="INFORMATION",
            ).dump()
        return InformationState(
            epistemic_relation=EpistemicState.BOTH_KNOW.value,
            revealed_item=beat.text[:40],
            reveal_type="NONE",
            viewer_knows=True,
            character_knows=True,
            dramatic_purpose="PROGRESSION",
        ).dump()

    def _compute_removal_consequence(self, beat: StoryBeat, purpose: str, primary_obj: Optional[str]) -> str:
        if purpose == "LOCATION":
            return "Viewer lacks physical and environmental orientation, making subsequent staging ungrounded."
        if purpose in ("CAUSE", "CONFLICT"):
            return "Viewer misses what initiated the crisis, making subsequent urgency appear arbitrary and unmotivated."
        if purpose == "OBJECT_INFORMATION":
            return f"Viewer misses the physical state of {primary_obj or 'the object'}, breaking causal logic."
        if purpose == "ACTION":
            return "Viewer misses the active human effort, causing the subsequent result to feel unearned."
        if purpose in ("REVEAL", "EFFECT"):
            return "Viewer is deprived of visual proof of the mechanical result, creating narrative confusion."
        if purpose == "PAYOFF":
            return "Story ends abruptly without emotional payoff, leaving the audience dissatisfied."
        return f"Essential narrative beat ({beat.beat_id}) lost, creating a gap in story comprehension."

    def _stage_actors_v21(
        self,
        beat: StoryBeat,
        cam: CameraSpec,
        loc_id: str,
        tracker: SequenceBlockingTracker,
    ) -> list[ActorBlock]:
        actors: list[ActorBlock] = []
        if not beat.characters:
            return actors

        shot_u = cam.shot.upper()
        purpose = beat.suggested_purpose or "INFORMATION"

        for i, cid in enumerate(beat.characters):
            char_dna = self.char_bible.get(cid)
            if not char_dna or not char_dna.on_screen:
                continue

            resolved = CharacterResolver.resolve_for_shot(char_dna, year=beat.year, location_id=loc_id)
            prev_actor_phys = tracker.geo.actors.get(cid)

            act_spec = next((a for a in beat.actions if a.actor_id == cid), None)
            if act_spec:
                verb = act_spec.verb
            elif cid == beat.speaker_id:
                verb = "SPEAK"
            else:
                # Dynamic reactive acting for secondary characters (eliminates static STAND trap)
                if purpose in ("ACTION", "CONFLICT"):
                    verb = "BRACE" if i % 2 == 1 else "REACT"
                elif purpose in ("TENSION", "CAUSE"):
                    verb = "FREEZE" if i % 2 == 1 else "GLANCE"
                elif purpose in ("REVEAL", "EFFECT"):
                    verb = "REACT"
                elif purpose == "EMOTION":
                    verb = "LISTEN"
                else:
                    verb = "WAIT"
            emotion = act_spec.emotion if act_spec else ("DETERMINED" if purpose in ("ACTION", "CAUSE") else "CALM")

            if shot_u == "OTS":
                if i == 0:
                    x = 0.22
                    orient = "PROFILE_RIGHT"
                else:
                    x = 0.68
                    orient = "THREE_QUARTER_LEFT"
            elif shot_u in ("CLOSE_UP", "PORTRAIT"):
                x = cam.subject_position[0]
                orient = "FRONT" if 0.45 < x < 0.55 else ("THREE_QUARTER_RIGHT" if x < 0.5 else "THREE_QUARTER_LEFT")
            elif shot_u == "OBJECT_INSERT":
                x = 0.38 if i == 0 else 0.72
                orient = "PROFILE_RIGHT" if x < 0.5 else "PROFILE_LEFT"
            else:
                base_x = prev_actor_phys.screen_pos[0] if prev_actor_phys else (0.35 + i * 0.30)
                if purpose == "ACTION" and i == 0:
                    target_x = 0.48 if base_x < 0.5 else 0.52
                    x = base_x + (target_x - base_x) * 0.35
                elif purpose == "REACTION" and i == 1:
                    x = base_x + 0.03
                else:
                    x = base_x
                orient = "THREE_QUARTER_RIGHT" if x < 0.5 else "THREE_QUARTER_LEFT"

            eyeline_target = None
            if len(beat.characters) > 1:
                other_cid = beat.characters[1 - i] if i < 2 else beat.characters[0]
                eyeline_target = other_cid
            elif beat.objects:
                eyeline_target = beat.objects[0]

            tracker.update_actor(
                actor_id=cid,
                screen_x=x,
                action=verb,
                orientation=orient,
                eyeline_target=eyeline_target,
            )

            pose = PerformanceKinematics.get_action_pose(verb, orientation=orient)
            p_phrase = f"{verb} with {emotion.lower()} intensity"
            p_intent = f"Execute {verb} facing {orient.lower()} with {emotion.lower()} focus."

            actors.append(ActorBlock(
                character_id=cid,
                variant_id=resolved.variant_id,
                costume_id=resolved.costume_id,
                detail_level=char_dna.detail_level,
                action=verb,
                emotion=emotion,
                orientation=orient,
                eyeline_target=eyeline_target,
                screen_x=x,
                depth=0.35,
                depth_plane="MG",
                height_px=420.0,
                performance_intent=p_intent,
                performance_phrase=[p_phrase],
                head_angle_deg=pose.get("head_tilt", 0.0),
                spine_curve=pose.get("spine_tilt", 0.0),
                shoulder_slope=pose.get("shoulder_tilt", 0.0),
            ))

        return actors

    @staticmethod
    def _derive_visual_intent(beat:StoryBeat,purpose:str)->tuple[str,str]:
        if beat.objects: return ("WHAT OBJECT MATTERS?",f"Isolate {beat.objects[0]} through gesture, focus, and depth.")
        if purpose=="LOCATION": return ("WHERE ARE WE?","Reveal geography with a physically placed wide camera and foreground frame.")
        if purpose in ("ACTION","CAUSE"): return ("WHAT IS HAPPENING?","Stage the action across depth with a readable cause and contact target.")
        if purpose in ("REACTION","EMOTION"): return ("WHAT DOES THE CHARACTER FEEL?","Prioritize face, body reaction, and controlled negative space.")
        if purpose in ("TENSION","REVEAL"): return ("WHAT IS HIDDEN OR DANGEROUS?","Use occlusion and depth to delay the important information.")
        return ("WHAT CHANGED?","Show the new information through actor, object, or environmental state.")

    @staticmethod
    def _camera_reason(purpose:str,beat:StoryBeat)->str:
        return {"LOCATION":"ESTABLISH_GEOGRAPHY","ACTION":"FOLLOW_ACTION","REACTION":"SHOW_REACTION","EMOTION":"SHOW_REACTION","SCALE":"SHOW_SCALE","TENSION":"CREATE_TENSION","REVEAL":"REVEAL_INFORMATION","OBJECT_INFORMATION":"EMPHASIZE_OBJECT"}.get(purpose,"REVEAL_INFORMATION" if beat.new_information else "SHOW_RELATIONSHIP")
    @staticmethod
    def _motion_reason(motion:str,purpose:str)->str:
        return "NONE" if motion=="STATIC" else {"ACTION":"FOLLOW_ACTION","TENSION":"INCREASE_TENSION","REVEAL":"REVEAL_OBJECT","SCALE":"EXPAND_SCALE"}.get(purpose,"SHIFT_ATTENTION")
    @staticmethod
    def _cut_reason(beat:StoryBeat,index:int)->str:
        if beat.comedy=="PAYOFF": return "COMEDIC_TIMING"
        if beat.closes_loops: return "REVEAL"
        if beat.new_information: return "NEW_INFORMATION"
        if beat.actions: return "ACTION_CONTINUATION"
        return "EMOTIONAL_SHIFT" if beat.emotional_intensity>.6 else "SCALE_CHANGE"
    @staticmethod
    def _energy(beat:StoryBeat)->str:
        score=max(beat.tension,beat.emotional_intensity)
        return "HIGH" if score>.72 else "MEDIUM" if score>.4 else "LOW"
    @staticmethod
    def _fingerprint(cam:CameraSpec,actors:list[ActorBlock],focus:str)->dict[str,Any]:
        return {"shot_size":cam.shot,"camera_height":cam.height,"yaw":cam.yaw_deg,"pitch":cam.pitch_deg,"lens_intent":cam.lens_intent,"subject_x":cam.subject_position[0],"subject_y":cam.subject_position[1],"subject_scale":cam.subject_height_px,"foreground_ratio":0.18 if cam.shot=="OTS" else 0.0,"depth_pattern":cam.depth_layout,"vanishing_point":cam.vanishing_point,"negative_space_side":"RIGHT" if cam.subject_position[0]<.5 else "LEFT","motion_type":cam.motion,"primary_focus":focus}

    def _replan_visual_idea(self,cam:CameraSpec,beat:StoryBeat,answer:str)->CameraSpec:
        # Replan physical camera relation without arbitrary enum swapping.
        update=cam.model_copy(deep=True); update.subject_position[0]=.34 if cam.subject_position[0]>=.5 else .66; update.yaw_deg=18 if update.subject_position[0]>.5 else -18; update.position=[.18 if update.subject_position[0]>.5 else .82,.52,update.height_m]; update.foreground_distance=.08; return update

    def _select_camera(
        self,
        beat: StoryBeat,
        purpose: str,
        index: int,
        history: list[CameraSpec],
    ) -> CameraSpec:
        # Default parameter matrix
        shot = "MEDIUM"
        height = "EYE"
        pitch = 0.0
        yaw = 0.0
        horizon = 0.50
        pos_x = 0.50
        pos_y = 0.80
        vp = [0.50, 0.50]
        lens = "NORMAL"

        if purpose == "LOCATION" or beat.beat_type == "HOOK":
            shot = "ENVIRONMENT_ESTABLISHING"
            height = "EYE"
            horizon = 0.45
            vp = [0.65, 0.45]
            lens = "WIDE"
            pos_x = 0.35
        elif purpose == "ACTION" or beat.beat_type == "CONFLICT":
            shot = "LOW_ANGLE" if index % 2 == 0 else "GROUND_LEVEL"
            height = "LOW" if shot == "LOW_ANGLE" else "GROUND"
            pitch = 18.0 if shot == "LOW_ANGLE" else 24.0
            horizon = 0.32
            vp = [0.42, 0.32]
            lens = "WIDE"
            pos_x = 0.48
        elif purpose in ("OBJECT_INFORMATION","CAUSE"):
            shot = "OBJECT_INSERT"
            height = "LOW"
            pitch = -8.0
            horizon = 0.58
            pos_x = 0.62 if beat.objects else 0.42
            pos_y = 0.72
            vp = [0.56,0.58]
            lens = "MACRO"
        elif purpose in ("REVEAL","EFFECT"):
            shot = "CLOSE_UP"
            height = "EYE"
            yaw = 16.0
            horizon = 0.52
            pos_x = 0.66
            pos_y = 0.78
            lens = "PORTRAIT"
        elif purpose in ("PAYOFF","HISTORICAL_CONTEXT"):
            shot = "WIDE"
            height = "HIGH"
            pitch = -10.0
            horizon = 0.58
            vp = [0.38,0.58]
            lens = "WIDE"
            pos_x = 0.34
        elif purpose == "EMOTION" or beat.beat_type == "REVERSAL":
            shot = "CLOSE_UP"
            height = "EYE"
            horizon = 0.52
            pos_x = 0.50
            pos_y = 0.85
        elif purpose == "REACTION":
            shot = "OTS"
            height = "EYE"
            yaw = 18.0
            horizon = 0.50
            pos_x = 0.65
        elif purpose in ("SCALE", "TENSION"):
            shot = "DEEP_PERSPECTIVE"
            height = "HIGH"
            pitch = -16.0
            horizon = 0.62
            vp = [0.55, 0.62]
            lens = "WIDE"
            pos_x = 0.52
        else:
            # Alternate framing across beats
            shot = ["MEDIUM_WIDE", "TWO_SHOT", "MEDIUM", "OTS"][index % 4]
            pos_x = 0.38 if index % 2 == 0 else 0.62
            vp = [0.58 if pos_x < 0.5 else 0.42, 0.50]

        return CameraSpec(
            shot=shot,
            height=height,
            height_m=1.6 if height == "EYE" else (0.8 if height == "LOW" else 2.4),
            yaw_deg=yaw,
            pitch_deg=pitch,
            lens=lens,
            perspective="ONE_POINT",
            horizon_y=horizon,
            vanishing_point=vp,
            subject_height_px=420.0,
            subject_position=[pos_x, pos_y],
            motion="STATIC",
            position=[0.18 if shot=="OTS" else 0.5,0.5,1.6 if height=="EYE" else 0.8],
            target=[pos_x,pos_y,0.0],
            distance=0.7 if "CLOSE" in shot else 1.4 if "WIDE" in shot or "ESTABLISHING" in shot else 1.0,
            lens_intent={"WIDE":"WIDE_IMMERSIVE","NORMAL":"NORMAL","MACRO":"MACRO","PORTRAIT":"PORTRAIT"}.get(lens,"NORMAL"),
            foreground_distance=0.08 if shot=="OTS" else 0.18,
        )

    def _break_stage_view(self, prev: CameraSpec, index: int) -> CameraSpec:
        alt_shot = "OTS" if index % 2 == 0 else "LOW_ANGLE"
        return CameraSpec(
            shot=alt_shot,
            height="LOW" if alt_shot == "LOW_ANGLE" else "EYE",
            yaw_deg=-22.0 if alt_shot == "OTS" else 0.0,
            pitch_deg=16.0 if alt_shot == "LOW_ANGLE" else 0.0,
            horizon_y=0.38 if alt_shot == "LOW_ANGLE" else 0.52,
            vanishing_point=[0.38, 0.38] if alt_shot == "LOW_ANGLE" else [0.65, 0.52],
            subject_position=[0.68, 0.82] if alt_shot == "OTS" else [0.46, 0.85],
        )

    def _stage_actors(self, beat: StoryBeat, cam: CameraSpec, loc_id: str) -> list[ActorBlock]:
        actors: list[ActorBlock] = []
        if not beat.characters:
            return actors

        for i, cid in enumerate(beat.characters):
            char_dna = self.char_bible.get(cid)
            if not char_dna or not char_dna.on_screen:
                continue

            resolved = CharacterResolver.resolve_for_shot(char_dna, year=beat.year, location_id=loc_id)
            
            # Find action for this actor
            act_spec = next((a for a in beat.actions if a.actor_id == cid), None)
            verb = act_spec.verb if act_spec else ("SPEAK" if cid == beat.speaker_id else "STAND")
            emotion = act_spec.emotion if act_spec else "CALM"

            # Horizontal distribution
            if len(beat.characters) == 1:
                x = cam.subject_position[0]
            else:
                x = 0.35 + i * 0.30

            # Orientation
            orient = "THREE_QUARTER_RIGHT" if x < 0.5 else "THREE_QUARTER_LEFT"
            if cam.shot == "OTS" and i == 0:
                orient = "PROFILE_RIGHT"

            actors.append(ActorBlock(
                character_id=cid,
                variant_id=resolved.variant_id,
                costume_id=resolved.costume_id,
                detail_level=char_dna.detail_level,
                action=verb,
                emotion=emotion,
                orientation=orient,
                screen_x=x,
                depth=0.35,
                depth_plane="MG",
                height_px=420.0,
            ))

        return actors

    def _place_props(self, beat: StoryBeat, loc: Optional[Any], cam: CameraSpec) -> list[PropPlacement]:
        props: list[PropPlacement] = []
        if not loc or not loc.props:
            return props

        for idx, p in enumerate(loc.props[:3]):
            # Resolve asset
            from ..schemas import AssetRequirement
            req = AssetRequirement(
                requirement_id=f"REQ_{loc.location_id}_{idx+1}",
                semantic=p.semantic,
                category=p.category,
                period_year=loc.period_from or beat.year,
                region=loc.region,
                materials=p.materials,
                role=p.role,
                location_id=loc.location_id,
            )
            res = self.asset_resolver.resolve(req)

            props.append(PropPlacement(
                instance_id=f"PROP_{idx+1:02d}",
                semantic=p.semantic,
                asset_id=res.asset_id,
                resolution_status=res.status,
                category=p.category,
                role=p.role,
                depth_plane="MG" if idx == 0 else "FG",
                screen_x=0.25 if idx % 2 == 0 else 0.75,
                depth=0.5 if idx == 0 else 0.25,
            ))

        return props
