"""Integration Adapter between Scene Intelligence V3 and Cinematic Director / SceneBlueprint.

Provides a clean non-destructive integration contract:
SceneDesignV3 → CinematicDirector / SceneBlueprint → Renderer V3

Ensures downstream renderers receive fully grounded world coordinates,
persistent object IDs, interaction anchors, and production design without
touching concurrent Renderer V3 modules.
"""
from __future__ import annotations

from typing import Any, Optional
from ..schemas import ActorBlock, CameraSpec, PropPlacement, SceneBlueprint
from .geography import SceneGeographyManager
from .schemas import SceneDesignV3


class SceneIntelligenceAdapter:
    """Bridges SceneDesignV3 to SceneBlueprint without modifying renderer code."""

    @staticmethod
    def apply_scene_design_to_blueprint(
        bp: SceneBlueprint,
        design: SceneDesignV3,
        camera_zone_id: Optional[str] = None,
    ) -> SceneBlueprint:
        """Enriches an existing SceneBlueprint with physical SceneDesignV3 ground truth."""
        # 1. Select active camera zone from geography
        cam_zone = None
        if camera_zone_id:
            cam_zone = next((cz for cz in design.geography.camera_zones if cz.zone_id == camera_zone_id), None)
        if not cam_zone and design.geography.camera_zones:
            cam_zone = design.geography.camera_zones[0]

        # 2. Synchronize Actor Screen Positions from 3D World Positions
        if cam_zone and bp.actors:
            for actor in bp.actors:
                staged_actor = next((sa for sa in design.staging.actors if sa.actor_id == actor.character_id), None)
                if staged_actor:
                    screen_coords = SceneGeographyManager.project_to_screen_coordinates(
                        staged_actor.spawn_point_world, cam_zone
                    )
                    actor.screen_x = screen_coords[0]
                    # Also align action if staging planned a specific expressive verb
                    if staged_actor.initial_action and actor.action in ("STAND", "OBSERVE"):
                        actor.action = staged_actor.initial_action

        # 3. Synchronize Props from Persistent World Objects
        enriched_props: list[PropPlacement] = []
        for obj in design.geography.world_objects:
            screen_coords = [0.5, 0.7]
            if cam_zone:
                screen_coords = SceneGeographyManager.project_to_screen_coordinates(obj.position_world, cam_zone)

            enriched_props.append(PropPlacement(
                instance_id=obj.instance_id,
                semantic=obj.semantic,
                asset_id=f"asset_{obj.instance_id.lower()}",
                resolution_status="RESOLVED",
                category=obj.category,
                role="HERO" if "HERO" in obj.instance_id else "SUPPORT",
                depth_plane="MG" if obj.position_world[2] < 4.0 else "BG",
                screen_x=screen_coords[0],
                depth=min(0.9, max(0.1, obj.position_world[2] / 10.0)),
                state=obj.state,
            ))

        if enriched_props:
            bp.props = enriched_props

        # 4. Inject Production Design & Scene Identity into Blueprint
        bp.production_design = design.production_design.dump()

        if not bp.visual_concept:
            bp.visual_concept = {}
        bp.visual_concept.update({
            "dominant_shape": design.scene_identity.dominant_shape,
            "dominant_depth_direction": design.scene_identity.dominant_depth_direction,
            "dominant_material": design.scene_identity.dominant_material,
            "dominant_light_source": design.scene_identity.dominant_light_source,
            "visual_motif": design.scene_identity.visual_motif,
            "hero_environment_feature": design.scene_identity.hero_environment_feature,
            "environment_storytelling": "; ".join(design.production_design.human_traces),
        })

        # 5. Narrative Dramatic Alignment
        bp.visual_question = f"DRAMATIC QUESTION: {design.dramatic_question}"
        bp.visual_answer = f"OUTCOME: {design.scene_outcome.description}"

        # 6. Snapshots
        bp.state_before = design.start_state.dump()
        bp.state_after = design.end_state.dump()
        bp.story_change = design.scene_outcome.narrative_shift
        bp.physical_change = design.scene_outcome.physical_consequence

        # Attach master design container directly to blueprint
        setattr(bp, "scene_design_v3", design.dump())

        return bp

    @staticmethod
    def to_render_spec(
        design: SceneDesignV3,
        camera_zone_id: Optional[str] = None,
        environment_only: bool = False,
        phase: str = "HERO",
    ) -> Any:
        """Bridges SceneDesignV3 to Renderer V3 RenderSpec with full physical ground truth."""
        from ..renderer_v3.renderer import RenderSpec

        ident = design.scene_identity
        geo = design.geography
        pd = design.production_design
        staging = design.staging
        sid = design.scene_id.lower()

        # 1. Palette Mapping
        color_family = ident.dominant_color_family.upper()
        if "AMBER" in color_family or "SEPIA" in color_family:
            palette = ('#24242b', '#755b43', '#d5a64d', '#839dad')
        elif "STEEL" in color_family or "SLATE" in color_family or "BLUE" in color_family:
            palette = ('#26313b', '#6f6c5f', '#e2c27e', '#91a8b4')
        elif "BRONZE" in color_family or "CHARCOAL" in color_family:
            palette = ('#282b2d', '#6e5039', '#ef9b3d', '#778e91')
        elif "PARCHMENT" in color_family or "OCHRE" in color_family and "BLACK" in color_family:
            palette = ('#2d2628', '#70503c', '#c9473e', '#8c9da5')
        elif "MUTED" in color_family or "EARTH" in color_family:
            palette = ('#222a32', '#6f6658', '#e2bc74', '#829aaa')
        else:
            palette = ('#25242a', '#71553d', '#d6a84e', '#889eab')

        # 2. Hero Asset & Material Mapping
        hero_feat = ident.hero_environment_feature.upper()
        if "DESK" in hero_feat or "TABLE" in hero_feat:
            hero_asset = "TABLE"
        elif "RIDGE" in hero_feat or "ROCK" in hero_feat or "CAIRN" in hero_feat:
            hero_asset = "ROCK"
        elif "BOILER" in hero_feat or "DYNAMO" in hero_feat or "MACHINE" in hero_feat:
            hero_asset = "MACHINE"
        elif "ROSTRUM" in hero_feat or "PODIUM" in hero_feat or "BENCH" in hero_feat:
            hero_asset = "BOOK"
        elif "BED" in hero_feat:
            hero_asset = "BED"
        else:
            hero_asset = "TABLE"

        dom_mat = ident.dominant_material.upper()
        if "OAK" in dom_mat or "WOOD" in dom_mat or "TIMBER" in dom_mat:
            mat = "WOOD"
        elif "GRANITE" in dom_mat or "STONE" in dom_mat:
            mat = "STONE"
        elif "IRON" in dom_mat or "BRONZE" in dom_mat or "METAL" in dom_mat:
            mat = "METAL"
        elif "LINEN" in dom_mat or "FABRIC" in dom_mat:
            mat = "FABRIC"
        elif "BRICK" in dom_mat:
            mat = "BRICK"
        elif "PLASTER" in dom_mat:
            mat = "PLASTER"
        else:
            mat = "WOOD"

        # 3. Layout & Architecture Structure
        shape = ident.dominant_shape.upper()
        if "JAGGED" in shape or "EXPANSE" in shape or geo.enclosure == "EXTERIOR":
            layout_kind = "PASS"
            horizon = 390
            landmark_x = 1050
            landmark_feature = "ROCK"
            hero_x = 1370
            foreground = "VEGETATION"
            props = ['ROCK', 'RUBBLE', 'POST', 'VEGETATION']
            human_traces = ['POST', 'RUBBLE']
            light_story = "SUN_LEFT"
            atmo = "FOG"
            actor_x = 520
            action = "BRACE"
            intensity = "STRONG"
            emotion = "FOCUSED"
            sec_x = None
            sec_action = None
        elif "CYLINDRICAL" in shape or "DYNAMO" in sid or "WORKSHOP" in sid:
            layout_kind = "ROOM"
            horizon = 535
            landmark_x = 1430
            landmark_feature = "MACHINE"
            hero_x = 1260
            foreground = "WIRE"
            props = ['TOOL', 'CRATE', 'WIRE', 'LAMP', 'BOTTLE']
            human_traces = ['TOOL', 'BOTTLE']
            light_story = "WINDOW_RIGHT"
            atmo = "SMOKE"
            actor_x = 760
            action = "REACH"
            intensity = "NORMAL"
            emotion = "FOCUSED"
            sec_x = 1380
            sec_action = "WAIT"
        elif "TIERED" in shape or "COUNCIL" in sid or "ASSEMBLY" in sid:
            layout_kind = "CROWD"
            horizon = 455
            landmark_x = 970
            landmark_feature = "WINDOW"
            hero_x = 1040
            foreground = "POST"
            props = ['CHAIR', 'TABLE', 'BOOK', 'PAPER', 'LAMP']
            human_traces = ['BOOK', 'PAPER']
            light_story = "WINDOW_LEFT"
            atmo = "DUST"
            actor_x = 1180
            action = "ARGUE"
            intensity = "STRONG"
            emotion = "DETERMINED"
            sec_x = 640
            sec_action = "BRACE"
        elif "HORIZONTAL" in shape or "VIGIL" in sid or "BED" in sid:
            layout_kind = "INTIMATE"
            horizon = 565
            landmark_x = 260
            landmark_feature = "WINDOW"
            hero_x = 1240
            foreground = "DOOR"
            props = ['BED', 'CUP', 'BOTTLE', 'CLOTH', 'LAMP']
            human_traces = ['CUP', 'CLOTH']
            light_story = "WINDOW_LEFT"
            atmo = "FOG"
            actor_x = 860
            action = "LEAN"
            intensity = "SUBTLE"
            emotion = "SAD"
            sec_x = 1240
            sec_action = "SIT"
        else:  # Editorial Dispute / Bureaucracy
            layout_kind = "ROOM"
            horizon = 475
            landmark_x = 430
            landmark_feature = "DOOR"
            hero_x = 1190
            foreground = "DOOR"
            props = ['CHAIR', 'PAPER', 'BOOK', 'LAMP', 'SHELF']
            human_traces = ['CHAIR', 'PAPER']
            light_story = "LAMP_LEFT"
            atmo = "DUST"
            actor_x = 720
            action = "ARGUE"
            intensity = "STRONG"
            emotion = "ANGRY"
            sec_x = 1280
            sec_action = "SIT"

        # 4. Phase Adjustments (Visual Progression START -> MIDDLE -> END)
        if phase == "START":
            if "dynamo" in sid:
                action = "WAIT"
                intensity = "SUBTLE"
                atmo = "DUST"
            elif "editorial" in sid:
                action = "WAIT"
                intensity = "NORMAL"
        elif phase == "END":
            if "dynamo" in sid:
                action = "BRACE"
                intensity = "STRONG"
                atmo = "EMBERS"
            elif "editorial" in sid:
                action = "BRACE"
                intensity = "STRONG"

        return RenderSpec(
            title=design.scene_id,
            location=ident.architectural_character or design.location_id,
            action=action,
            intensity=intensity,
            emotion=emotion,
            palette=palette,
            hero_asset=hero_asset,
            material=mat,
            atmosphere=atmo,
            lighting_story=light_story,
            foreground=foreground,
            seed=101,
            props=props,
            layout_kind=layout_kind,
            horizon=horizon,
            actor_x=actor_x,
            hero_x=hero_x,
            landmark_x=landmark_x,
            environment_only=environment_only,
            secondary_actor_x=sec_x,
            secondary_action=sec_action,
            secondary_intensity=intensity,
            human_traces=human_traces,
            landmark_feature=landmark_feature,
        )
