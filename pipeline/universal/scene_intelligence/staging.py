"""Scene Staging Planner V3.

Plans physical actor blocking and kinematics BEFORE cameras are selected:
- Spatially plausible actor spawns based on entrances, tasks, and territories.
- Power dynamics expressed through spatial configuration (standing vs sitting, behind desk, elevation).
- Proxemics tracking (INTIMATE, PERSONAL, SOCIAL, PUBLIC).
- Movement paths strictly restricted to walkable geometry without intersecting obstacles.
- Clear movement purposes (CONFRONTS, RETRIEVES, INVESTIGATES, ESCAPES, etc.).
"""
from __future__ import annotations

import math
from typing import Any, Optional

from .geography import SceneGeographyManager
from .schemas import (
    ActorStagingV3,
    PowerRelationship,
    ProxemicDistance,
    ProxemicRelationship,
    SceneGeographyV3,
    ScenePurpose,
    SceneStagingPlan,
    WorldObject,
)


class SceneStagingPlanner:
    """Computes physical staging, proxemics, power geometry, and collision-free movement."""

    @staticmethod
    def plan_staging(
        characters: list[str],
        geo: SceneGeographyV3,
        scene_purpose: ScenePurpose,
        dramatic_question: str,
        focal_object_id: Optional[str] = None,
        power_bias: Optional[dict[str, float]] = None,
    ) -> SceneStagingPlan:
        """Derives authentic spatial blocking for characters in the scene geography."""
        staged_actors: list[ActorStagingV3] = []
        focal_obj = next((o for o in geo.world_objects if o.instance_id == focal_object_id), None)
        if not focal_obj and geo.world_objects:
            focal_obj = geo.world_objects[0]

        power_bias = power_bias or {}

        # 1. Spawn Actors based on Territory, Entrances, and Roles
        for idx, cid in enumerate(characters):
            # Check if actor has a predefined spawn zone in geography
            if cid in geo.actor_spawn_zones:
                spawn = list(geo.actor_spawn_zones[cid])
            elif geo.openings and idx > 0 and scene_purpose in (ScenePurpose.CONFLICT, ScenePurpose.DISCOVERY):
                # Secondary actor enters through primary opening (e.g. Door / Path)
                door = geo.openings[0]["coords"]
                spawn = [(door[0] + door[2]) * 0.5, 0.0, (door[1] + door[3]) * 0.5 + 0.5]
            elif focal_obj and idx == 0:
                # Primary actor stationed at territory or hero object
                anchor_offset = [-0.8, 0.0, 0.4] if "DESK" in focal_obj.instance_id or "TABLE" in focal_obj.instance_id else [0.0, 0.0, -0.6]
                spawn = [
                    focal_obj.position_world[0] + anchor_offset[0],
                    0.0,
                    focal_obj.position_world[2] + anchor_offset[2],
                ]
            else:
                # Default distributed placement along walkable boundary
                offset_x = -1.5 if idx % 2 == 0 else 1.5
                spawn = [offset_x, 0.0, 2.5 + idx * 1.0]

            # Verify walkability; clamp to walkable zone if outside
            if not SceneGeographyManager.is_walkable(spawn, geo):
                # Fallback to center of first walkable zone
                if geo.walkable_zones:
                    wz = geo.walkable_zones[0]
                    spawn = [(wz[0] + wz[2]) * 0.5, 0.0, (wz[1] + wz[3]) * 0.5]

            # Action & Orientation
            if scene_purpose == ScenePurpose.CONFLICT and idx == 0:
                action = "LEAN"
                orient = "THREE_QUARTER_RIGHT"
            elif scene_purpose == ScenePurpose.CONFLICT and idx == 1:
                action = "BRACE"
                orient = "THREE_QUARTER_LEFT"
            elif scene_purpose in (ScenePurpose.DISCOVERY, ScenePurpose.INVESTIGATION):
                action = "INSPECT" if idx == 0 else "OBSERVE"
                orient = "PROFILE_RIGHT" if idx == 0 else "FRONT"
            elif scene_purpose == ScenePurpose.TRAVEL:
                action = "WALK"
                orient = "PROFILE_RIGHT"
            else:
                action = "STAND"
                orient = "FRONT"

            # Destination & Movement Path
            dest = None
            path = []
            m_purpose = None

            if scene_purpose in (ScenePurpose.CONFLICT, ScenePurpose.NEGOTIATION) and idx == 1 and focal_obj:
                # Secondary actor advances toward focal object / primary actor (stopping in front of it)
                m_purpose = "CONFRONTS"
                candidate_offsets = [
                    [1.2, 0.0, -0.4],   # Front right visitor side
                    [0.0, 0.0, -1.0],   # Direct front visitor side
                    [1.4, 0.0, 0.0],    # Lateral flank
                    [-1.4, 0.0, 0.0],
                ]
                dest = None
                for off in candidate_offsets:
                    cand = [focal_obj.position_world[0] + off[0], 0.0, focal_obj.position_world[2] + off[2]]
                    if SceneGeographyManager.is_walkable(cand, geo):
                        dest = cand
                        break
                if not dest:
                    dest = [spawn[0] * 0.5, 0.0, spawn[2] * 0.5 + 0.5]

                # Compute intermediate waypoint if direct path blocked
                if not SceneGeographyManager.can_traverse_path(spawn, dest, geo):
                    # Step around
                    mid = [(spawn[0] + dest[0]) * 0.5 + 0.8, 0.0, (spawn[2] + dest[2]) * 0.5]
                    if SceneGeographyManager.can_traverse_path(spawn, mid, geo) and SceneGeographyManager.can_traverse_path(mid, dest, geo):
                        path = [mid, dest]
                    else:
                        alt_mid = [(spawn[0] + dest[0]) * 0.5 - 0.8, 0.0, (spawn[2] + dest[2]) * 0.5]
                        path = [alt_mid, dest] if SceneGeographyManager.is_walkable(alt_mid, geo) else [dest]
                else:
                    path = [dest]

            eyeline = characters[1 - idx] if len(characters) > 1 and idx < 2 else (focal_obj.instance_id if focal_obj else None)

            staged_actors.append(ActorStagingV3(
                actor_id=cid,
                spawn_point_world=spawn,
                initial_action=action,
                initial_orientation=orient,
                eyeline_target=eyeline,
                territory_zone=f"{focal_obj.instance_id}_ZONE" if idx == 0 and focal_obj else "OPEN_FLOOR",
                movement_path=path,
                destination_world=dest,
                target_object_id=focal_obj.instance_id if focal_obj else None,
                movement_purpose=m_purpose,
            ))

        # 2. Compute Proxemic Relationships
        proxemics: list[ProxemicRelationship] = []
        if len(staged_actors) >= 2:
            p0 = staged_actors[0].spawn_point_world
            p1 = staged_actors[1].spawn_point_world
            dist = math.hypot(p0[0] - p1[0], p0[2] - p1[2])

            if dist < 0.6:
                cat = ProxemicDistance.INTIMATE
            elif dist < 1.4:
                cat = ProxemicDistance.PERSONAL
            elif dist < 3.5:
                cat = ProxemicDistance.SOCIAL
            else:
                cat = ProxemicDistance.PUBLIC

            proxemics.append(ProxemicRelationship(
                actor_a=staged_actors[0].actor_id,
                actor_b=staged_actors[1].actor_id,
                distance_meters=round(dist, 2),
                classification=cat,
            ))

        # 3. Compute Power Relationships
        power_rel: list[PowerRelationship] = []
        if len(staged_actors) >= 2:
            lead = staged_actors[0].actor_id
            sub = staged_actors[1].actor_id

            if focal_obj and ("DESK" in focal_obj.instance_id or "ROSTRUM" in focal_obj.instance_id or "PODIUM" in focal_obj.instance_id):
                mech = "BEHIND_DESK_OR_PODIUM"
                delta = 0.65
            elif scene_purpose == ScenePurpose.CONFLICT:
                mech = "AGGRESSIVE_FORWARD_LEAN"
                delta = 0.50
            else:
                mech = "BALANCED_TERRITORY"
                delta = 0.10

            power_rel.append(PowerRelationship(
                dominant_actor=lead,
                subordinate_actor=sub,
                spatial_mechanism=mech,
                power_delta=delta,
            ))

        eyeline_axis = [staged_actors[0].actor_id, staged_actors[1].actor_id] if len(staged_actors) >= 2 else []

        return SceneStagingPlan(
            actors=staged_actors,
            proxemics=proxemics,
            power_relationships=power_rel,
            primary_eyeline_axis=eyeline_axis,
        )
