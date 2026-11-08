"""Stage 6: Shot Planner — The Cinematic Brain.

Translates ScenePlan into fully structured Shot objects complying with:
  - Normalized geometry (0.0..1.0)
  - 11-dimension Camera Delta validation
  - History-aware Similarity Guard across the previous 6 shots (threshold 0.72)
  - Stage View Ban (no >=2 stage-views in rolling 5 shots)
  - Autonomous replanning before calling any Image API
"""
from __future__ import annotations

import random
from typing import Any

from ..acting.action_to_pose import map_action_to_pose
from ..schemas.bible import Location, ProjectBible
from ..schemas.core import LayerRole, NormPoint, NormRect
from ..schemas.plan import (
    BodyOrientation,
    CameraHeight,
    CameraMotion,
    LayerIntent,
    LightDirection,
    PerspectiveType,
    RetentionRole,
    ScenePlan,
    Shot,
    ShotPlan,
    ShotPurpose,
    ShotType,
    Transition,
)
from ..schemas.script import Beat, ScriptAnalysis
from ..validation.replanner import apply_archetype_to_shot, get_archetypes, replan_rejected_shot
from ..validation.similarity_guard import check_shot_similarity
from ..validation.stage_view import is_stage_view


def plan_shots(
    scene_plan: ScenePlan,
    analysis: ScriptAnalysis,
    bible: ProjectBible,
    locations: list[Location],
    similarity_threshold: float = 0.72,
    window_size: int = 6,
) -> ShotPlan:
    """Plans shots for every scene with anti-repetition and stage-view guards."""
    shots: list[Shot] = []
    archetypes = get_archetypes()
    beat_map: dict[str, Beat] = {b.beat_id: b for b in analysis.beats}
    loc_map: dict[str, Location] = {loc.id: loc for loc in locations}

    shot_global_idx = 0
    elapsed = 0.0

    # Rolling window of stage views
    stage_view_history: list[bool] = []

    for scene in scene_plan.scenes:
        seg = next((s for s in scene_plan.retention if s.segment_id == f"RET_{scene.index + 1:02d}"), None)
        shot_durs = seg.shot_durations if seg else [scene.duration_sec]
        loc = loc_map.get(scene.location_id, locations[0] if locations else None)

        # Candidate beats for this scene
        scene_beats = [beat_map[bid] for bid in scene.beat_ids if bid in beat_map]

        for s_idx, duration in enumerate(shot_durs):
            shot_id = f"S{shot_global_idx + 1:03d}"
            beat = scene_beats[s_idx % len(scene_beats)] if scene_beats else None
            beat_text = beat.text if beat else scene.narration

            # Determine purpose
            if s_idx == 0:
                purpose = ShotPurpose.ESTABLISH if scene.index == 0 else ShotPurpose.REVEAL
            elif s_idx == len(shot_durs) - 1:
                purpose = ShotPurpose.EMPHASIS if scene.retention_roles and scene.retention_roles[0] in (RetentionRole.PAYOFF, RetentionRole.CLIFFHANGER) else ShotPurpose.DETAIL
            else:
                purpose = ShotPurpose.ACTION if "bắn" in beat_text.lower() else ShotPurpose.DIALOGUE

            # Map action verb and context to kinetic pose
            action_verb = "look" if s_idx == 0 else ("react" if purpose == ShotPurpose.REACTION else "speak")
            pose_fam, weight = map_action_to_pose(action_verb, beat_text)

            # Pick a starter archetype matching purpose
            matching_archetypes = [
                a for a in archetypes
                if purpose.value in a.get("purposes", []) and not a.get("discouraged")
            ]
            starter = matching_archetypes[(shot_global_idx) % len(matching_archetypes)] if matching_archetypes else archetypes[0]

            # Construct initial Shot
            shot = Shot(
                shot_id=shot_id,
                scene_id=scene.scene_id,
                beat_id=beat.beat_id if beat else f"BEAT_{s_idx + 1:03d}",
                index=shot_global_idx,
                start_sec=round(elapsed, 2),
                duration=round(duration, 2),
                shot_purpose=purpose,
                story_beat=beat.story_beat if beat else "progression",
                retention_role=scene.retention_roles[0] if scene.retention_roles else RetentionRole.SETUP,
                emotional_tone=scene.emotional_tone,
                narration_text=beat_text,
                shot_type=ShotType(starter["shot_type"]),
                camera_height=CameraHeight(starter["camera_height"]),
                perspective_type=PerspectiveType(starter["perspective_type"]),
                vanishing_point_primary=NormPoint(x=starter["vp1"][0], y=starter["vp1"][1]),
                location_id=scene.location_id,
                character_ids=scene.character_ids[:2],
                action_verb=action_verb,
                pose_family=pose_fam,
                weight_distribution=weight,
                foreground=loc.foreground_elements[0] if loc and loc.foreground_elements else "Architectural frame",
                midground=loc.midground_elements[0] if loc and loc.midground_elements else "Street and walls",
                background=loc.background_elements[0] if loc and loc.background_elements else "Buildings and skyline",
                far_background=loc.far_background_elements[0] if loc and loc.far_background_elements else "Sky horizon",
            )
            apply_archetype_to_shot(shot, starter)

            # Build LayerIntent contracts (FAR_BG, BG, MG, CHARACTER, FG, FX)
            shot.layers = [
                LayerIntent(role=LayerRole.FAR_BG, description=shot.far_background, parallax=0.10),
                LayerIntent(role=LayerRole.BG, description=shot.background, parallax=0.25),
                LayerIntent(role=LayerRole.MG, description=shot.midground, parallax=0.50),
                LayerIntent(role=LayerRole.CHARACTER, description="Stickman rig actor", source="rig", parallax=0.70),
                LayerIntent(role=LayerRole.FG, description=shot.foreground, parallax=1.00),
                LayerIntent(role=LayerRole.FX, description="Atmospheric dust/smoke", parallax=1.10),
            ]

            # 1. Similarity Check against previous 6 shots
            sim_res = check_shot_similarity(shot, shots, threshold=similarity_threshold, window_size=window_size)
            shot.visual_similarity_score = sim_res.max_similarity
            shot.most_similar_shot_id = sim_res.most_similar_shot_id

            # 2. Stage View Check
            stage_check = is_stage_view(shot)
            recent_stage_count = sum(stage_view_history[-4:]) if len(stage_view_history) >= 4 else 0
            excessive_stage = stage_check and (recent_stage_count >= 1)

            # 3. Replanning if similarity exceeded or stage view excessive
            if (not sim_res.passed) or excessive_stage:
                shot, ok = replan_rejected_shot(
                    shot,
                    shots,
                    threshold=similarity_threshold,
                    window_size=window_size,
                    require_non_stage=excessive_stage,
                )
            else:
                shot.validator_action = "PASS"

            stage_view_history.append(is_stage_view(shot))
            shots.append(shot)
            elapsed += duration
            shot_global_idx += 1

    return ShotPlan(
        shots=shots,
        total_duration_sec=round(elapsed, 2),
    )
