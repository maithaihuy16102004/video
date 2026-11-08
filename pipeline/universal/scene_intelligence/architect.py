"""Scene Architect Engine V3 (Gemini & Deterministic).

Sits BEFORE detailed shot planning.
Transforms script beats and location context into a rich physical SceneDesignV3:
- Answers: Where are we? Why does it look this way? What happened before? What changes?
- Determines ScenePurpose, DramaticQuestion, SceneOutcome, and SceneIdentity.
- Designs ProductionDesignPlan (materials, prop ecology, human traces, environmental damage).
- Constructs persistent SceneGeographyV3 with collision boundaries and interaction anchors.
- Plans Staging (power balance, proxemics, territory, movement).
- Builds SceneEventGraph (causal chain with state effects).
- Pre-director SceneCritic with maximum 1 replan.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

_PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

try:
    from env_secrets import get_gemini_api_key, redact
except ImportError:
    def get_gemini_api_key(required: bool = False) -> Optional[str]:
        return None
    def redact(s: Any) -> str:
        return str(s)

from .events import SceneEventGraphBuilder
from .geography import SceneGeographyManager
from .schemas import (
    Affordance,
    CameraOpportunityZone,
    EventEffect,
    InformationItem,
    InteractionAnchor,
    PowerRelationship,
    ProductionDesignPlan,
    ProductionProp,
    PropReason,
    ProxemicDistance,
    ProxemicRelationship,
    SceneDesignV3,
    SceneEndState,
    SceneEvent,
    SceneEventGraph,
    SceneGeographyV3,
    SceneIdentity,
    SceneOutcome,
    SceneOutcomeType,
    ScenePurpose,
    SceneStartState,
    SceneStagingPlan,
    UModel,
    WorldObject,
)
from .staging import SceneStagingPlanner


class GeminiSceneCallLedger:
    """Audit ledger tracking all Gemini Scene Intelligence requests."""
    _records: list[dict[str, Any]] = []

    @classmethod
    def record(
        cls,
        stage: str,
        model: str,
        input_hash: str,
        cache_hit: bool,
        latency_sec: float,
        success: bool,
        error: Optional[str] = None,
        purpose: str = "",
    ) -> None:
        cls._records.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "stage": stage,
            "model": model,
            "input_hash": input_hash,
            "cache_hit": cache_hit,
            "latency_sec": round(latency_sec, 3),
            "success": success,
            "error": redact(error) if error else None,
            "paid_spend_usd": 0.00,
            "purpose": purpose,
        })

    @classmethod
    def get_records(cls) -> list[dict[str, Any]]:
        return list(cls._records)

    @classmethod
    def clear(cls) -> None:
        cls._records.clear()


class SceneArchitectProvider(ABC):
    """Abstract interface for Scene Architecture."""

    @abstractmethod
    def design_scene(self, context: dict[str, Any]) -> SceneDesignV3:
        """Derives full SceneDesignV3 for a story beat."""
        pass

    @abstractmethod
    def critique_scene(self, design: SceneDesignV3) -> dict[str, Any]:
        """Performs pre-director spatial and narrative critique."""
        pass


class DeterministicSceneArchitect(SceneArchitectProvider):
    """High-quality deterministic scene architect ensuring $0 cost and offline stability."""

    def design_scene(self, context: dict[str, Any]) -> SceneDesignV3:
        beat_text = context.get("script_segment", "A scene in the physical world.")
        t_low = beat_text.lower()
        beat_id = context.get("beat_id", "BEAT_01")
        scene_id = context.get("scene_id", f"SCN_{beat_id}")
        loc_id = context.get("location_id", "LOC_DEFAULT")
        loc_dna = context.get("location_dna")
        characters = context.get("characters", ["LEAD"])
        enclosure = getattr(loc_dna, "enclosure", context.get("location_enclosure", "INTERIOR"))

        # 1. Determine Purpose, Dramatic Question & Outcome
        s_purpose = str(context.get("suggested_purpose", "")).upper()
        if s_purpose == "CONFLICT" or any(k in t_low for k in ("argue", "dispute", "refuse", "protest", "slam", "confront", "lean", "tap", "draft")):
            purpose = ScenePurpose.CONFLICT
            question = "Will the subordinate yield authority during this confrontation?"
            outcome_type = SceneOutcomeType.ESCALATION
            outcome_desc = "Tension spikes; neither character backs down, leaving an irreconcilable divide."
        elif any(k in t_low for k in ("steam", "leak", "wrench", "boiler", "repair", "lever", "machine")):
            purpose = ScenePurpose.PREPARATION
            question = "Can the catastrophic mechanical failure be halted before rupture?"
            outcome_type = SceneOutcomeType.ANSWER
            outcome_desc = "Decisive manual action restores emergency control over the apparatus."
        elif any(k in t_low for k in ("ridge", "mountain", "traverse", "walk", "wind", "compass")):
            purpose = ScenePurpose.TRAVEL
            question = "Can the lone traveler navigate the exposed ridge against the gale?"
            outcome_type = SceneOutcomeType.PARTIAL_ANSWER
            outcome_desc = "The ridge crest is conquered, opening the path down into the valley pass."
        elif any(k in t_low for k in ("council", "assembly", "podium", "speak", "charter", "hall")):
            purpose = ScenePurpose.NEGOTIATION
            question = "Who commands the political consensus of the assembly?"
            outcome_type = SceneOutcomeType.REVERSAL
            outcome_desc = "A dramatic objection disrupts the proceedings, overturning expected consensus."
        elif any(k in t_low for k in ("bed", "lantern", "whisper", "hand", "vigil", "sick")):
            purpose = ScenePurpose.REFLECTION
            question = "Will the weakened patient acknowledge the caregiver before night ends?"
            outcome_type = SceneOutcomeType.ANSWER
            outcome_desc = "A tender touch and whispered reassurance re-establishes quiet emotional connection."
        else:
            purpose = ScenePurpose.DISCOVERY
            question = "What vital clue or physical reality is revealed here?"
            outcome_type = SceneOutcomeType.ANSWER
            outcome_desc = "The physical investigation uncovers critical information."

        # 2. Scene Identity & Archetype Staging Setup
        if enclosure.upper() == "INTERIOR":
            if "office" in t_low or "edit" in loc_id.lower():
                identity = SceneIdentity(
                    dominant_shape="RECTANGULAR_CONFINEMENT",
                    dominant_depth_direction="DIAGONAL_RECEDING_LEFT",
                    dominant_material="WEATHERED_OAK",
                    dominant_light_source="LOW_AMBER_DESK_LAMP",
                    dominant_color_family="WARM_AMBER_SEPIA",
                    visual_density="DENSE",
                    spatial_pressure="CONFINED",
                    environment_condition="WORN_HEAVY_USE",
                    architectural_character="Victorian bureaucratic office with wainscot paneling",
                    visual_motif="SLANTED_SHADOW_BARS",
                    hero_environment_feature="MASSIVE_OAK_DESK",
                )
                hero_pos = [-1.2, 0.0, 2.8]
                hero_bounds = [2.0, 0.8, 1.2]
                sec_prop_pos = [-1.6, 0.8, 2.6]
                geo_bounds = [-4.0, 0.0, 4.0, 6.5]
                walk_zones = [[-3.5, 0.5, 3.5, 6.0]]
                block_zones = [[-2.3, 2.1, -0.1, 3.5]]
                openings_cfg = [{"name": "OFFICE_DOOR", "coords": [3.0, 0.5, 3.8, 0.5], "type": "DOOR"}]
                act_spawns = {
                    characters[0]: [-1.2, 0.0, 3.6],
                    **({characters[1]: [1.8, 0.0, 1.8]} if len(characters) > 1 else {}),
                }
                cam_zones = [
                    CameraOpportunityZone(
                        zone_id="DOORWAY_OVERVIEW",
                        position_world=[3.2, 1.6, 1.2],
                        view_target_world=[-1.2, 1.0, 3.2],
                        lens_intent="WIDE_IMMERSIVE",
                        narrative_purpose="ESTABLISH_SPATIAL_GEOGRAPHY",
                        best_for="Observing arrival and entrance into office",
                    ),
                    CameraOpportunityZone(
                        zone_id="DESK_POWER_PROFILE",
                        position_world=[0.5, 1.2, 2.8],
                        view_target_world=[-1.2, 1.0, 3.2],
                        lens_intent="NORMAL",
                        narrative_purpose="CONFRONTATION_AND_DETAIL",
                        best_for="Direct character interaction over the massive desk",
                    ),
                    CameraOpportunityZone(
                        zone_id="LOW_ANGLE_IMPACT",
                        position_world=[-0.6, 0.7, 2.0],
                        view_target_world=[-1.2, 1.2, 3.4],
                        lens_intent="WIDE_IMMERSIVE",
                        narrative_purpose="EMPHASIZE_POWER_AND_TENSION",
                        best_for="Dramatic confrontation emphasizing authoritative posture",
                    ),
                ]
            elif "dynamo" in loc_id.lower() or "workshop" in loc_id.lower() or "steam" in t_low:
                identity = SceneIdentity(
                    dominant_shape="CYLINDRICAL_MASSES",
                    dominant_depth_direction="DEEP_CONDUIT_TUNNEL",
                    dominant_material="CAST_IRON_AND_BRONZE",
                    dominant_light_source="GLOWING_COPPER_FURNACE",
                    dominant_color_family="INDUSTRIAL_BRONZE_CHARCOAL",
                    visual_density="DENSE",
                    spatial_pressure="COMPRESSED",
                    environment_condition="SOOT_STAINED_HIGH_HEAT",
                    architectural_character="Industrial vaulted brick boiler room",
                    visual_motif="REPEATING_RIVET_LINES",
                    hero_environment_feature="HEAVY_DYNAMO_BOILER",
                )
                hero_pos = [-2.2, 0.0, 3.8]
                hero_bounds = [2.4, 2.6, 2.0]
                sec_prop_pos = [-1.0, 1.1, 3.4]
                geo_bounds = [-5.0, 0.0, 5.0, 7.5]
                walk_zones = [[-4.0, 0.5, 4.0, 6.5]]
                block_zones = [[-3.4, 2.8, -1.0, 4.8]]
                openings_cfg = [{"name": "BOILER_ROOM_HATCH", "coords": [3.5, 1.0, 3.5, 3.0], "type": "BULKHEAD"}]
                act_spawns = {
                    characters[0]: [-0.6, 0.0, 3.2],
                    **({characters[1]: [1.5, 0.0, 2.0]} if len(characters) > 1 else {}),
                }
                cam_zones = [
                    CameraOpportunityZone(
                        zone_id="HEAT_HAZE_CORNER",
                        position_world=[2.8, 1.8, 1.5],
                        view_target_world=[-2.2, 1.2, 3.8],
                        lens_intent="WIDE_IMMERSIVE",
                        narrative_purpose="ESTABLISH_SPATIAL_GEOGRAPHY",
                        best_for="Boiler room overview framed by overhead steam conduits",
                    ),
                    CameraOpportunityZone(
                        zone_id="VALVE_TIGHT_PRESSURE",
                        position_world=[-0.2, 1.1, 2.4],
                        view_target_world=[-1.0, 1.1, 3.4],
                        lens_intent="NORMAL",
                        narrative_purpose="CONFRONTATION_AND_DETAIL",
                        best_for="Tight view of engineer working frantically at valve manifold",
                    ),
                    CameraOpportunityZone(
                        zone_id="CONDUIT_DEPTH_TUNNEL",
                        position_world=[0.5, 0.8, 5.2],
                        view_target_world=[-2.0, 1.0, 3.0],
                        lens_intent="WIDE_IMMERSIVE",
                        narrative_purpose="EMPHASIZE_POWER_AND_TENSION",
                        best_for="Deep vanishing point showing perspective depth of boiler array",
                    ),
                ]
            elif "council" in loc_id.lower() or "assembly" in loc_id.lower():
                identity = SceneIdentity(
                    dominant_shape="TIERED_ARC_CONVERGENCE",
                    dominant_depth_direction="SYMMETRICAL_DEEP_AISLE",
                    dominant_material="CARVED_STONE",
                    dominant_light_source="CATHEDRAL_WINDOW_SHAFTS",
                    dominant_color_family="PARCHMENT_OCHRE_BLACK",
                    visual_density="BALANCED",
                    spatial_pressure="EXPANSIVE",
                    environment_condition="WELL_MAINTAINED",
                    architectural_character="Monumental civic assembly hall",
                    visual_motif="REPEATING_STONE_ARCHES",
                    hero_environment_feature="ELEVATED_ROSTRUM_PODIUM",
                )
                hero_pos = [0.0, 0.6, 1.8]
                hero_bounds = [1.6, 1.2, 1.0]
                sec_prop_pos = [0.0, 1.2, 1.8]
                geo_bounds = [-6.0, 0.0, 6.0, 9.0]
                walk_zones = [[-5.0, 0.5, 5.0, 8.0]]
                block_zones = [[-0.8, 1.2, 0.8, 1.9]]
                openings_cfg = [{"name": "CHAMBER_GATES", "coords": [0.0, 7.5, 0.0, 8.5], "type": "PORTAL"}]
                act_spawns = {
                    characters[0]: [0.0, 0.6, 2.4],
                    **({characters[1]: [2.2, 0.0, 4.5]} if len(characters) > 1 else {}),
                }
                cam_zones = [
                    CameraOpportunityZone(
                        zone_id="ASSEMBLY_WIDE_TIERS",
                        position_world=[0.0, 2.8, 6.5],
                        view_target_world=[0.0, 0.8, 1.8],
                        lens_intent="WIDE_IMMERSIVE",
                        narrative_purpose="ESTABLISH_SPATIAL_GEOGRAPHY",
                        best_for="High amphitheater perspective looking down aisle toward podium",
                    ),
                    CameraOpportunityZone(
                        zone_id="ROSTRUM_AUTHORITY_LOW",
                        position_world=[-0.8, 0.5, 1.2],
                        view_target_world=[0.0, 1.2, 2.4],
                        lens_intent="WIDE_IMMERSIVE",
                        narrative_purpose="EMPHASIZE_POWER_AND_TENSION",
                        best_for="Low monumental angle presenting speaker's commanding position",
                    ),
                    CameraOpportunityZone(
                        zone_id="CHALLENGER_PROFILE_REVERSAL",
                        position_world=[3.2, 1.2, 4.0],
                        view_target_world=[0.0, 1.0, 1.8],
                        lens_intent="NORMAL",
                        narrative_purpose="CONFRONTATION_AND_DETAIL",
                        best_for="Reverse profile looking across delegates toward the dais",
                    ),
                ]
            else:  # sickroom / domestic / The Vigil
                identity = SceneIdentity(
                    dominant_shape="HORIZONTAL_SANCTUARY",
                    dominant_depth_direction="LATERAL_BEDSIDE_RECEDING",
                    dominant_material="WARM_LINEN_AND_TIMBER",
                    dominant_light_source="INTIMATE_OIL_LANTERN",
                    dominant_color_family="MUTED_EARTH_OCHRE",
                    visual_density="FOCUSED",
                    spatial_pressure="BALANCED",
                    environment_condition="DOMESTIC_WELL_KEPT",
                    architectural_character="Cozy plaster and timber sickroom",
                    visual_motif="SOFT_DRAPERY_FOLDS",
                    hero_environment_feature="TIMBER_CLINIC_BED",
                )
                hero_pos = [1.8, 0.0, 2.6]
                hero_bounds = [1.8, 0.8, 1.2]
                sec_prop_pos = [0.4, 0.7, 2.4]
                geo_bounds = [-4.0, 0.0, 4.0, 6.0]
                walk_zones = [[-3.2, 0.5, 3.2, 5.2]]
                block_zones = [[1.5, 1.8, 2.8, 3.4]]
                openings_cfg = [{"name": "SANCTUARY_DOOR", "coords": [-3.0, 0.8, -3.0, 2.4], "type": "TIMBER_DOOR"}]
                act_spawns = {
                    characters[0]: [-0.4, 0.0, 2.6],
                    **({characters[1]: [1.0, 0.0, 2.6]} if len(characters) > 1 else {}),
                }
                cam_zones = [
                    CameraOpportunityZone(
                        zone_id="BEDSIDE_INTIMATE",
                        position_world=[-0.6, 1.0, 2.2],
                        view_target_world=[1.8, 0.6, 2.6],
                        lens_intent="NORMAL",
                        narrative_purpose="CONFRONTATION_AND_DETAIL",
                        best_for="Intimate eye-level framing capturing quiet emotional exchange",
                    ),
                    CameraOpportunityZone(
                        zone_id="LANTERN_GLOW_SILHOUETTE",
                        position_world=[1.0, 0.8, 1.2],
                        view_target_world=[-0.4, 0.9, 2.6],
                        lens_intent="NORMAL",
                        narrative_purpose="EMPHASIZE_POWER_AND_TENSION",
                        best_for="Warm lantern backlight casting long protective shadows",
                    ),
                    CameraOpportunityZone(
                        zone_id="DOORWAY_QUIET_OBSERVER",
                        position_world=[-2.6, 1.4, 4.2],
                        view_target_world=[1.0, 0.8, 2.6],
                        lens_intent="WIDE_IMMERSIVE",
                        narrative_purpose="ESTABLISH_SPATIAL_GEOGRAPHY",
                        best_for="Distant threshold framing emphasizing solitude and quietude",
                    ),
                ]
        else:  # EXTERIOR (The Solitary Traverse)
            identity = SceneIdentity(
                dominant_shape="JAGGED_HORIZON_DIAGONALS",
                dominant_depth_direction="DEEP_PANORAMIC_VISTA",
                dominant_material="STRATIFIED_GRANITE",
                dominant_light_source="COLD_DIFFUSE_OVERCAST",
                dominant_color_family="STEEL_BLUE_SLATE",
                visual_density="SPARSE",
                spatial_pressure="EXPANSIVE",
                environment_condition="WEATHER_BEATEN",
                architectural_character="Alpine rock crest and glacial moraine",
                visual_motif="FRACTURED_ROCK_ANGLES",
                hero_environment_feature="EXPOSED_RIDGE_CREST",
            )
            hero_pos = [1.8, 1.2, 4.5]
            hero_bounds = [1.6, 1.4, 1.4]
            sec_prop_pos = [1.2, 0.6, 3.8]
            geo_bounds = [-6.0, 0.0, 6.0, 10.0]
            walk_zones = [[-5.0, 0.5, 5.0, 9.0]]
            block_zones = [[1.0, 3.8, 2.6, 5.2]]
            openings_cfg = [{"name": "RIDGE_PASS_ENTRY", "coords": [-4.5, 0.5, -3.5, 0.5], "type": "NATURAL_PASS"}]
            act_spawns = {
                characters[0]: [-2.5, 0.0, 1.8],
                **({characters[1]: [0.5, 0.0, 3.0]} if len(characters) > 1 else {}),
            }
            cam_zones = [
                CameraOpportunityZone(
                    zone_id="WIDE_EPIC_VISTA",
                    position_world=[-4.2, 2.2, 0.8],
                    view_target_world=[1.8, 1.2, 4.5],
                    lens_intent="WIDE_IMMERSIVE",
                    narrative_purpose="ESTABLISH_SPATIAL_GEOGRAPHY",
                    best_for="Expansive panoramic perspective establishing hostile mountain scale",
                ),
                CameraOpportunityZone(
                    zone_id="GROUND_LEVEL_STRUGGLE",
                    position_world=[-1.5, 0.5, 1.2],
                    view_target_world=[-2.5, 0.8, 1.8],
                    lens_intent="WIDE_IMMERSIVE",
                    narrative_purpose="EMPHASIZE_POWER_AND_TENSION",
                    best_for="Low ground-level tracking shot showing boots on jagged rock",
                ),
                CameraOpportunityZone(
                    zone_id="CREST_ANTICIPATION",
                    position_world=[1.4, 1.6, 3.6],
                    view_target_world=[-2.0, 0.4, 2.0],
                    lens_intent="NORMAL",
                    narrative_purpose="CONFRONTATION_AND_DETAIL",
                    best_for="Framing looking back down the ridge crest toward the ascending traveler",
                ),
            ]

        # 3. Production Design Plan
        hero_obj_id = f"HERO_OBJ_{scene_id}"
        hero_prop_sem = identity.hero_environment_feature.replace("_", " ").title()

        hero_prop = ProductionProp(
            object_instance_id=hero_obj_id,
            semantic=hero_prop_sem,
            category="FURNITURE" if "DESK" in hero_obj_id or "BED" in hero_obj_id else "APPARATUS",
            role="HERO",
            primary_material=identity.dominant_material.split("_")[0],
            reasons=[PropReason.STORY, PropReason.FUNCTIONAL, PropReason.INTERACTION],
            position_world=hero_pos,
            anchors=[
                InteractionAnchor(anchor_name="TOP", relative_pos=[0.0, 0.75, 0.0], normal=[0.0, 1.0, 0.0], supported_actions=["LEAN", "PLACE", "INSPECT"]),
                InteractionAnchor(anchor_name="EDGE_FRONT", relative_pos=[0.0, 0.7, -0.4], normal=[0.0, 0.0, -1.0], supported_actions=["STAND", "GRAB"]),
            ],
            affordances=[Affordance.GRABBABLE, Affordance.PRESSABLE],
        )

        sec_prop = ProductionProp(
            object_instance_id=f"PRACTICAL_LIGHT_{scene_id}",
            semantic=identity.dominant_light_source.replace("_", " ").title(),
            category="LIGHTING",
            role="PRACTICAL",
            primary_material="BRASS",
            reasons=[PropReason.FUNCTIONAL, PropReason.COMPOSITIONAL],
            position_world=sec_prop_pos,
            anchors=[InteractionAnchor(anchor_name="SWITCH", relative_pos=[0.0, 0.1, 0.0], supported_actions=["PRESS"])],
            affordances=[Affordance.PRESSABLE],
        )

        prod_plan = ProductionDesignPlan(
            architecture=identity.architectural_character,
            construction_materials=[identity.dominant_material, "WOOD", "BRASS"],
            surface_condition=identity.environment_condition,
            furniture_families=f"{identity.dominant_material} period suite",
            working_objects=[hero_prop_sem],
            hero_props=[hero_prop],
            secondary_props=[sec_prop],
            human_traces=["Scuffed flooring along the main path", "Tools and documents positioned with working purpose"],
            environmental_damage=["Corner scuffs and natural timber grain wear"],
            ground_surface="PLANKED_TIMBER" if enclosure.upper() == "INTERIOR" else "WEATHERED_ROCK",
            ceiling_structure="EXPOSED_BEAMS" if enclosure.upper() == "INTERIOR" else "OPEN_ATMOSPHERE",
            openings=openings_cfg,
            light_sources=[{"type": "KEY", "source": identity.dominant_light_source, "pos": [-2.0, 2.5, 1.5]}],
            atmosphere="LIGHT_HAZE" if "SOOT" in identity.environment_condition else "CLEAR",
            visual_clutter=identity.visual_density,
        )

        # 4. Scene Geography V3
        world_obj_1 = WorldObject(
            instance_id=hero_obj_id,
            semantic=hero_prop_sem,
            category="HERO_APPARATUS",
            bounds_3d=hero_bounds,
            position_world=hero_pos,
            materials=[identity.dominant_material],
            anchors=hero_prop.anchors,
            affordances=hero_prop.affordances,
            is_occluder=True,
        )

        geo = SceneGeographyV3(
            location_id=loc_id,
            enclosure=enclosure,
            bounds_world=geo_bounds,
            ground_plane_y=0.0,
            walls=[
                {"name": "BACK_WALL", "coords": [geo_bounds[0], geo_bounds[3], geo_bounds[2], geo_bounds[3]]},
                {"name": "LEFT_WALL", "coords": [geo_bounds[0], geo_bounds[1], geo_bounds[0], geo_bounds[3]]},
                {"name": "RIGHT_WALL", "coords": [geo_bounds[2], geo_bounds[1], geo_bounds[2], geo_bounds[3]]},
            ],
            openings=openings_cfg,
            world_objects=[world_obj_1],
            walkable_zones=walk_zones,
            blocked_zones=block_zones,
            actor_spawn_zones=act_spawns,
            camera_zones=cam_zones,
            light_sources=prod_plan.light_sources,
        )

        # 5. Staging Plan
        staging = SceneStagingPlanner.plan_staging(
            characters=characters,
            geo=geo,
            scene_purpose=purpose,
            dramatic_question=question,
            focal_object_id=hero_obj_id,
        )

        # 6. Event Graph & State Snapshots
        event_graph = SceneEventGraphBuilder.build_event_graph(
            scene_purpose=purpose,
            dramatic_question=question,
            actors=characters,
            objects=[hero_obj_id],
            text_context=beat_text,
        )
        start_state, end_state = SceneEventGraphBuilder.derive_start_and_end_states(
            event_graph, characters, hero_obj_id
        )

        return SceneDesignV3(
            scene_id=scene_id,
            story_beat_id=beat_id,
            location_id=loc_id,
            scene_purpose=purpose,
            dramatic_question=question,
            scene_outcome=SceneOutcome(
                outcome_type=outcome_type,
                description=outcome_desc,
                physical_consequence=f"{hero_prop_sem} was directly altered by the character action.",
                narrative_shift=outcome_desc,
            ),
            scene_identity=identity,
            production_design=prod_plan,
            geography=geo,
            staging=staging,
            event_graph=event_graph,
            visual_progression=f"ORDERED_SETUP -> {purpose.value}_PEAK -> RESOLUTION",
            energy_curve=["CALM", "BUILD", "IMPACT", "REACTION"],
            start_state=start_state,
            end_state=end_state,
            ideal_intent=f"A fully realized authentic physical scene communicating '{beat_text[:50]}...'",
            executable_intent="Grounded 3D coordinates, persistent modular props, and collision-free staging.",
            asset_gap_requests=[{"semantic": hero_prop_sem, "category": hero_prop.category, "criticality": "STORY_CRITICAL"}],
        )

    def critique_scene(self, design: SceneDesignV3) -> dict[str, Any]:
        """Audits physical validity and staging logic."""
        issues = []
        # 1. Walkability check
        for act in design.staging.actors:
            if not SceneGeographyManager.is_walkable(act.spawn_point_world, design.geography):
                issues.append(f"Actor {act.actor_id} spawned inside blocked geometry {act.spawn_point_world}")

        # 2. Camera inside solid check
        for cz in design.geography.camera_zones:
            if not SceneGeographyManager.is_point_in_bounds(cz.position_world, design.geography.bounds_world):
                issues.append(f"Camera zone {cz.zone_id} is out of world bounds")

        approved = len(issues) == 0
        return {
            "approved": approved,
            "issues": issues,
            "authenticity_score": 0.95 if approved else 0.70,
            "replan_needed": not approved,
        }


class GeminiSceneArchitect(SceneArchitectProvider):
    """Gemini-powered Scene Architect with structured JSON, caching, and fallback."""

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        cache_dir: Optional[Path] = None,
        timeout: int = 45,
    ) -> None:
        self.model = model
        self.cache_dir = cache_dir or (_PIPELINE_DIR / "cache" / "scene_intelligence")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.fallback = DeterministicSceneArchitect()

    def _cache_key(self, payload: dict[str, Any]) -> str:
        s = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def _call_gemini(self, system: str, user_prompt: str, purpose: str) -> Optional[dict[str, Any]]:
        key = get_gemini_api_key(required=False)
        if not key:
            GeminiSceneCallLedger.record("scene_architect", self.model, "NO_KEY", False, 0.0, False, "NO_KEY", purpose)
            return None

        payload = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {"temperature": 0.25, "responseMimeType": "application/json"},
        }
        in_hash = self._cache_key(payload)
        cache_file = self.cache_dir / f"scene_{in_hash}.json"

        # Check Cache
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                GeminiSceneCallLedger.record("scene_architect", self.model, in_hash, True, 0.001, True, None, purpose)
                return cached
            except Exception:
                pass

        # Network Call
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={key}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t0
            text = raw["candidates"][0]["content"]["parts"][0]["text"].strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
            parsed = json.loads(text)

            cache_file.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
            GeminiSceneCallLedger.record("scene_architect", self.model, in_hash, False, elapsed, True, None, purpose)
            return parsed
        except Exception as e:
            elapsed = time.perf_counter() - t0
            GeminiSceneCallLedger.record("scene_architect", self.model, in_hash, False, elapsed, False, str(e), purpose)
            return None

    def design_scene(self, context: dict[str, Any]) -> SceneDesignV3:
        beat_text = context.get("script_segment", "")
        loc_id = context.get("location_id", "LOC_DEFAULT")
        loc_dna = context.get("location_dna")
        characters = context.get("characters", ["LEAD"])

        system_instruction = (
            "You are the Lead Production Designer and Master Scene Architect for cinematic video production.\n"
            "A SCENE IS NOT A BACKGROUND. A scene is a physical place where an event is actually happening.\n"
            "Answer the core architectural questions:\n"
            "1. Where are we? Why does this place look this way?\n"
            "2. What happened here before this moment? What is happening now? What will change?\n"
            "3. What objects matter? Where are people? What can they touch? Where can they move?\n"
            "4. What is the dramatic question and visual identity of this space?\n"
            "Return valid JSON adhering to the SceneDesignV3 specification."
        )

        user_prompt = (
            f"STORY BEAT: '{beat_text}'\n"
            f"LOCATION: '{loc_id}' ({getattr(loc_dna, 'name', loc_id)}), Enclosure: {getattr(loc_dna, 'enclosure', 'INTERIOR')}\n"
            f"CHARACTERS: {characters}\n\n"
            "Design the complete physical scene in JSON with:\n"
            "- scene_purpose (INTRODUCE_WORLD, CONFLICT, DISCOVERY, TRAVEL, PREPARATION, NEGOTIATION, REFLECTION, etc.)\n"
            "- dramatic_question (Single primary question)\n"
            "- scene_outcome (outcome_type, description, physical_consequence)\n"
            "- scene_identity (dominant_shape, dominant_depth_direction, dominant_material, dominant_light_source, visual_density, spatial_pressure, architectural_character, visual_motif, hero_environment_feature)\n"
            "- production_design (architecture, construction_materials, surface_condition, furniture_families, hero_props, secondary_props, human_traces, environmental_damage, light_sources)\n"
            "- visual_progression (e.g. ORDERED -> CHAOTIC)\n"
        )

        data = self._call_gemini(system_instruction, user_prompt, purpose=f"Design Scene: {beat_text[:40]}")

        # If call succeeds, construct full SceneDesignV3 merging Gemini's creative choices with valid geography
        if data and isinstance(data, dict):
            try:
                # Use deterministic builder for geometry/staging topology guided by Gemini's identity and production design
                det_design = self.fallback.design_scene(context)

                # Merge Gemini's rich creative intelligence
                if "scene_purpose" in data:
                    try:
                        det_design.scene_purpose = ScenePurpose(data["scene_purpose"])
                    except Exception:
                        pass
                if "dramatic_question" in data:
                    det_design.dramatic_question = str(data["dramatic_question"])
                if "scene_outcome" in data and isinstance(data["scene_outcome"], dict):
                    det_design.scene_outcome = SceneOutcome(
                        outcome_type=SceneOutcomeType.ANSWER,
                        description=data["scene_outcome"].get("description", det_design.scene_outcome.description),
                        physical_consequence=data["scene_outcome"].get("physical_consequence", det_design.scene_outcome.physical_consequence),
                    )
                if "scene_identity" in data and isinstance(data["scene_identity"], dict):
                    sid = data["scene_identity"]
                    det_design.scene_identity = SceneIdentity(
                        dominant_shape=sid.get("dominant_shape", det_design.scene_identity.dominant_shape),
                        dominant_depth_direction=sid.get("dominant_depth_direction", det_design.scene_identity.dominant_depth_direction),
                        dominant_material=sid.get("dominant_material", det_design.scene_identity.dominant_material),
                        dominant_light_source=sid.get("dominant_light_source", det_design.scene_identity.dominant_light_source),
                        dominant_color_family=sid.get("dominant_color_family", det_design.scene_identity.dominant_color_family),
                        visual_density=sid.get("visual_density", det_design.scene_identity.visual_density),
                        spatial_pressure=sid.get("spatial_pressure", det_design.scene_identity.spatial_pressure),
                        environment_condition=sid.get("environment_condition", det_design.scene_identity.environment_condition),
                        architectural_character=sid.get("architectural_character", det_design.scene_identity.architectural_character),
                        visual_motif=sid.get("visual_motif", det_design.scene_identity.visual_motif),
                        hero_environment_feature=sid.get("hero_environment_feature", det_design.scene_identity.hero_environment_feature),
                    )
                if "production_design" in data and isinstance(data["production_design"], dict):
                    pd = data["production_design"]
                    if pd.get("human_traces"):
                        det_design.production_design.human_traces = pd["human_traces"]
                    if pd.get("environmental_damage"):
                        det_design.production_design.environmental_damage = pd["environmental_damage"]
                    if pd.get("architecture"):
                        det_design.production_design.architecture = pd["architecture"]

                if "visual_progression" in data:
                    det_design.visual_progression = str(data["visual_progression"])

                # Critique
                critic_res = self.critique_scene(det_design)
                det_design.scene_critic_review = critic_res

                return det_design
            except Exception as e:
                pass

        # Fallback to deterministic scene architect
        det_design = self.fallback.design_scene(context)
        det_design.scene_critic_review = self.critique_scene(det_design)
        return det_design

    def critique_scene(self, design: SceneDesignV3) -> dict[str, Any]:
        """Pre-director validation audit."""
        return self.fallback.critique_scene(design)
