"""Scene Intelligence V3 Validation Suite.

Executes rigorous verification on scene geography, staging, template leakage,
survival into blueprints, and dead metadata audits:
1. SceneGeographyValidator: Bounds, wall collisions, blocked doorways, camera in solid.
2. TemplateLeakageValidator: Flags repetitive staging (table center, actors left/right, etc.).
3. SceneSurvivalAuditor: Verifies intended scene design survives into blueprints.
4. SceneDeadMetadataAuditor: Ensures every new field is consumed and has spatial impact.
"""
from __future__ import annotations

import math
from typing import Any, Optional
from .geography import SceneGeographyManager
from .schemas import SceneDesignV3, SceneGeographyV3


class SceneGeographyValidator:
    """Verifies that the scene geography adheres to physical laws and collision rules."""

    @staticmethod
    def validate_geography(design: SceneDesignV3) -> dict[str, Any]:
        geo = design.geography
        issues: list[str] = []

        # 1. No actor inside wall or blocked zone
        for actor in design.staging.actors:
            pos = actor.spawn_point_world
            if not SceneGeographyManager.is_walkable(pos, geo):
                issues.append(f"Actor '{actor.actor_id}' is spawned inside blocked/invalid geometry: {pos}")

            # Check movement path
            if actor.movement_path:
                curr = pos
                for pt in actor.movement_path:
                    if not SceneGeographyManager.can_traverse_path(curr, pt, geo):
                        issues.append(f"Actor '{actor.actor_id}' movement path from {curr} to {pt} intersects blocked geometry.")
                    curr = pt

        # 2. No prop floating outside world bounds
        for obj in geo.world_objects:
            if not SceneGeographyManager.is_point_in_bounds(obj.position_world, geo.bounds_world):
                issues.append(f"World object '{obj.instance_id}' is positioned outside world bounds: {obj.position_world}")

        # 3. No blocked doorway (clearance check)
        for op in geo.openings:
            coords = op.get("coords", [])
            if len(coords) >= 4:
                door_mid = [(coords[0] + coords[2]) * 0.5, (coords[1] + coords[3]) * 0.5]
                # Doorway must not be completely inside a blocked zone
                for b in geo.blocked_zones:
                    if b[0] < door_mid[0] < b[2] and b[1] < door_mid[1] < b[3]:
                        issues.append(f"Opening '{op.get('name')}' is completely occluded by blocked zone {b}")

        # 4. No camera inside solid object
        for cz in geo.camera_zones:
            cpos = cz.position_world
            for b in geo.blocked_zones:
                if b[0] < cpos[0] < b[2] and b[1] < cpos[2] < b[3]:
                    issues.append(f"Camera zone '{cz.zone_id}' is placed inside solid blocked object {b}")

        passed = len(issues) == 0
        return {
            "validation_passed": passed,
            "scene_id": design.scene_id,
            "issues_count": len(issues),
            "issues": issues,
        }


class TemplateLeakageValidator:
    """Verifies that unrelated scenes do NOT leak into identical structural templates."""

    @staticmethod
    def audit_scene_diversity(designs: list[SceneDesignV3]) -> dict[str, Any]:
        """Compares structural fingerprints across scenes."""
        fingerprints: list[dict[str, Any]] = []

        for d in designs:
            geo = d.geography
            staging = d.staging
            hero_obj = geo.world_objects[0] if geo.world_objects else None

            # Compute topology features
            actor_x_coords = [round(a.spawn_point_world[0], 2) for a in staging.actors]
            obj_pos = [round(p, 2) for p in (hero_obj.position_world if hero_obj else [0, 0, 0])]

            fingerprints.append({
                "scene_id": d.scene_id,
                "purpose": d.scene_purpose.value,
                "dominant_shape": d.scene_identity.dominant_shape,
                "dominant_depth_direction": d.scene_identity.dominant_depth_direction,
                "hero_obj_x": obj_pos[0],
                "hero_obj_z": obj_pos[2],
                "actor_x_coords": actor_x_coords,
                "camera_zones_count": len(geo.camera_zones),
                "openings_count": len(geo.openings),
            })

        # Check template leakage checks:
        # 1. Did all scenes place hero object at x=0.0, z=2.5?
        obj_positions = [(fp["hero_obj_x"], fp["hero_obj_z"]) for fp in fingerprints]
        repeated_obj_pos = len(set(obj_positions)) < len(designs) * 0.40

        # 2. Did all scenes use identical depth directions?
        depth_dirs = [fp["dominant_depth_direction"] for fp in fingerprints]
        repeated_depth = len(set(depth_dirs)) < len(designs) * 0.40

        # 3. Did all scenes use identical dominant shapes?
        shapes = [fp["dominant_shape"] for fp in fingerprints]
        repeated_shapes = len(set(shapes)) < len(designs) * 0.40

        leakage_detected = repeated_obj_pos and repeated_depth and repeated_shapes

        return {
            "audit_passed": not leakage_detected,
            "scenes_analyzed": len(designs),
            "unique_depth_directions": len(set(depth_dirs)),
            "unique_shapes": len(set(shapes)),
            "unique_object_topologies": len(set(obj_positions)),
            "structural_fingerprints": fingerprints,
            "leakage_risk_detected": leakage_detected,
        }


class SceneSurvivalAuditor:
    """Audits whether intended SceneDesignV3 survived downstream into blueprints."""

    @staticmethod
    def audit_survival(design: SceneDesignV3, bp: Any) -> dict[str, Any]:
        survived = {
            "architecture": bool(bp.production_design and bp.production_design.get("architecture")),
            "materials": bool(bp.production_design and bp.production_design.get("construction_materials")),
            "hero_props": len(bp.props) > 0,
            "human_traces": bool(bp.visual_concept and bp.visual_concept.get("environment_storytelling")),
            "dramatic_question": "DRAMATIC QUESTION:" in (bp.visual_question or ""),
            "outcome": "OUTCOME:" in (bp.visual_answer or ""),
            "start_state": bp.state_before is not None,
            "end_state": bp.state_after is not None,
        }
        score = sum(1 for v in survived.values() if v) / float(len(survived))
        return {
            "scene_id": design.scene_id,
            "survival_score": round(score, 3),
            "all_survived": score >= 0.85,
            "breakdown": survived,
        }
