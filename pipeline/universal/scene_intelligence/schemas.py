"""Universal Scene Intelligence V3 Schemas.

A scene is not a background:
A scene is Space + People + Objects + Events + Information + Time + Light + Cause and Effect.

Defines the complete data contract for Scene Architects, Spatial Geography,
Physical Staging, Event Graphs, and Production Design.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class UModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    def dump(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# ==============================================================================
# 1. SCENE PURPOSE, DRAMATIC QUESTION & OUTCOME
# ==============================================================================

class ScenePurpose(str, Enum):
    INTRODUCE_WORLD = "INTRODUCE_WORLD"
    INTRODUCE_CHARACTER = "INTRODUCE_CHARACTER"
    DISCOVERY = "DISCOVERY"
    CONFLICT = "CONFLICT"
    NEGOTIATION = "NEGOTIATION"
    ESCAPE = "ESCAPE"
    TRAVEL = "TRAVEL"
    INVESTIGATION = "INVESTIGATION"
    PREPARATION = "PREPARATION"
    CONSEQUENCE = "CONSEQUENCE"
    REFLECTION = "REFLECTION"
    REVELATION = "REVELATION"
    TRANSITION = "TRANSITION"
    CLIMAX = "CLIMAX"
    AFTERMATH = "AFTERMATH"


class SceneOutcomeType(str, Enum):
    ANSWER = "ANSWER"
    PARTIAL_ANSWER = "PARTIAL_ANSWER"
    NEW_QUESTION = "NEW_QUESTION"
    REVERSAL = "REVERSAL"
    FAILURE = "FAILURE"
    ESCALATION = "ESCALATION"


class SceneOutcome(UModel):
    outcome_type: SceneOutcomeType = SceneOutcomeType.ANSWER
    description: str = ""
    physical_consequence: str = ""
    narrative_shift: str = ""


# ==============================================================================
# 2. SCENE IDENTITY
# ==============================================================================

class SceneIdentity(UModel):
    """The distinctive visual DNA of a specific scene instance."""
    dominant_shape: str = "HORIZONTAL_EXPANSE"       # HORIZONTAL_EXPANSE, VERTICAL_CAGE, ANGULAR_FRACTURE, etc.
    dominant_depth_direction: str = "DEEP_CENTRAL"   # DIAGONAL_RECEDING_LEFT, DEEP_CENTRAL, LATERAL_CROSSING, etc.
    dominant_material: str = "WOOD"                  # WEATHERED_OAK, CAST_IRON, JAGGED_GRANITE, CARVED_STONE, etc.
    dominant_light_source: str = "NATURAL_WINDOW"    # LOW_AMBER_DESK_LAMP, HARSH_OVERCAST, OIL_LANTERN, etc.
    dominant_color_family: str = "MUTED_AUTHENTIC"   # WARM_AMBER_SEPIA, STEEL_BLUE_SLATE, BRONZE_CHARCOAL, etc.
    visual_density: str = "BALANCED"                 # SPARSE, FOCUSED, DENSE, CLAUSTROPHOBIC
    spatial_pressure: str = "BALANCED"               # EXPANSIVE, BALANCED, CONFINED, COMPRESSED
    environment_condition: str = "WORN_HEAVY_USE"    # PRISTINE, MAINTAINED, WORN_HEAVY_USE, WEATHER_BEATEN, etc.
    architectural_character: str = ""                # VICTORIAN_BUREAUCRATIC, ALPINE_WILDERNESS, etc.
    visual_motif: str = ""                           # SLANTED_SHADOW_BARS, REPEATING_RIVET_LINES, etc.
    hero_environment_feature: str = ""               # MASSIVE_OAK_DESK, EXPOSED_RIDGE_CREST, BOILER_DRUM, etc.


# ==============================================================================
# 3. PRODUCTION DESIGN PLAN & PROP ECOLOGY
# ==============================================================================

class PropReason(str, Enum):
    FUNCTIONAL = "FUNCTIONAL"
    STORY = "STORY"
    CHARACTER = "CHARACTER"
    HISTORICAL = "HISTORICAL"
    COMPOSITIONAL = "COMPOSITIONAL"
    INTERACTION = "INTERACTION"


class Affordance(str, Enum):
    OPENABLE = "OPENABLE"
    SITTABLE = "SITTABLE"
    GRABBABLE = "GRABBABLE"
    READABLE = "READABLE"
    PRESSABLE = "PRESSABLE"
    PULLABLE = "PULLABLE"
    PUSHABLE = "PUSHABLE"
    CLIMBABLE = "CLIMBABLE"
    HIDE_BEHIND = "HIDE_BEHIND"
    LOOK_THROUGH = "LOOK_THROUGH"


class InteractionAnchor(UModel):
    anchor_name: str                                 # e.g. TOP, HANDLE, LEVER, SEAT, EDGE_FRONT
    relative_pos: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])  # relative to object origin
    normal: list[float] = Field(default_factory=lambda: [0.0, 1.0, 0.0])
    supported_actions: list[str] = Field(default_factory=list)  # e.g. ["LEAN", "SIT", "GRAB", "PULL"]


class ProductionProp(UModel):
    object_instance_id: str                          # e.g. TABLE_OAK_01, BOILER_MACHINE_01
    semantic: str
    category: str                                    # FURNITURE, APPARATUS, MACHINE, LIGHTING, DOCUMENT
    role: str                                        # HERO, SUPPORT, PRACTICAL, BACKGROUND
    primary_material: str                            # WOOD, METAL, STONE, GLASS, BRASS, FABRIC, PAPER
    reasons: list[PropReason] = Field(default_factory=lambda: [PropReason.FUNCTIONAL])
    placement_anchor: str = "GROUND"
    position_world: list[float] = Field(default_factory=lambda: [0.0, 0.0, 2.0])
    state: str = "INITIAL"
    anchors: list[InteractionAnchor] = Field(default_factory=list)
    affordances: list[Affordance] = Field(default_factory=list)


class ProductionDesignPlan(UModel):
    """Complete physical and material specification of the environment."""
    architecture: str = ""
    construction_materials: list[str] = Field(default_factory=list)
    surface_condition: str = "WEATHERED_PATINA"
    furniture_families: str = ""
    working_objects: list[str] = Field(default_factory=list)
    hero_props: list[ProductionProp] = Field(default_factory=list)
    secondary_props: list[ProductionProp] = Field(default_factory=list)
    human_traces: list[str] = Field(default_factory=list)
    environmental_damage: list[str] = Field(default_factory=list)
    signage_if_needed: Optional[str] = None
    fabric_elements: list[str] = Field(default_factory=list)
    ground_surface: str = "WOODEN_PLANKS"
    ceiling_structure: str = "EXPOSED_TIMBER_BEAMS"
    openings: list[dict[str, Any]] = Field(default_factory=list)
    light_sources: list[dict[str, Any]] = Field(default_factory=list)
    background_activity: Optional[str] = None
    atmosphere: str = "CLEAR"
    visual_clutter: str = "MODERATE"
    period_constraints: str = "AUTHENTIC_HISTORICAL"


# ==============================================================================
# 4. SCENE GEOGRAPHY V3 (WORLD COORDINATES & PERSISTENCE)
# ==============================================================================

class WorldObject(UModel):
    """A physical persistent object located in 3D world space."""
    instance_id: str
    semantic: str
    category: str
    bounds_3d: list[float] = Field(default_factory=lambda: [1.0, 0.8, 1.0])  # width(x), height(y), depth(z)
    position_world: list[float] = Field(default_factory=lambda: [0.0, 0.0, 2.0])  # [x, y, z]
    orientation_deg: float = 0.0
    materials: list[str] = Field(default_factory=lambda: ["WOOD"])
    state: str = "INITIAL"
    anchors: list[InteractionAnchor] = Field(default_factory=list)
    affordances: list[Affordance] = Field(default_factory=list)
    is_occluder: bool = False
    is_climbable: bool = False


class CameraOpportunityZone(UModel):
    """A physically placed vantage point where camera can naturally exist."""
    zone_id: str                                     # e.g. DOORWAY_ZONE, TABLE_SIDE_ZONE, GROUND_ZONE
    position_world: list[float]                      # [x, y, z]
    view_target_world: list[float]                   # [x, y, z]
    height_m: float = 1.6
    lens_intent: str = "NORMAL"                      # WIDE_IMMERSIVE, NORMAL, TELE_COMPRESSION, MACRO
    narrative_purpose: str = "OBSERVATION"
    best_for: str = "Showing character interaction"


class SceneGeographyV3(UModel):
    """World-space coordinates and spatial topology for the entire scene."""
    location_id: str
    enclosure: str = "INTERIOR"                      # INTERIOR, EXTERIOR, SEMI_ENCLOSED
    bounds_world: list[float] = Field(default_factory=lambda: [-5.0, 0.0, 5.0, 10.0])  # [min_x, min_z, max_x, max_z]
    ground_plane_y: float = 0.0
    walls: list[dict[str, Any]] = Field(default_factory=list)
    openings: list[dict[str, Any]] = Field(default_factory=list)  # doors, windows, gates, arches
    architectural_features: list[dict[str, Any]] = Field(default_factory=list)
    world_objects: list[WorldObject] = Field(default_factory=list)
    walkable_zones: list[list[float]] = Field(default_factory=list)  # list of [x0, z0, x1, z1] rects
    blocked_zones: list[list[float]] = Field(default_factory=list)   # geometry impossible to walk through
    actor_spawn_zones: dict[str, list[float]] = Field(default_factory=dict)
    camera_zones: list[CameraOpportunityZone] = Field(default_factory=list)
    light_sources: list[dict[str, Any]] = Field(default_factory=list)
    occlusion_zones: list[dict[str, Any]] = Field(default_factory=list)
    background_activity_zones: list[dict[str, Any]] = Field(default_factory=list)


# ==============================================================================
# 5. SCENE STAGING V3 (PROXEMICS, POWER, TERRITORY & MOVEMENT)
# ==============================================================================

class ProxemicDistance(str, Enum):
    INTIMATE = "INTIMATE"       # < 0.5m (touching, whispering, physical struggle)
    PERSONAL = "PERSONAL"       # 0.5m - 1.2m (close conversation, private exchange)
    SOCIAL = "SOCIAL"           # 1.2m - 3.5m (formal desk interaction, group discussion)
    PUBLIC = "PUBLIC"           # > 3.5m (orator to audience, distant observer)


class ProxemicRelationship(UModel):
    actor_a: str
    actor_b: str
    distance_meters: float = 2.0
    classification: ProxemicDistance = ProxemicDistance.SOCIAL


class PowerRelationship(UModel):
    dominant_actor: str
    subordinate_actor: str
    spatial_mechanism: str                           # ELEVATED_ROSTRUM, BEHIND_DESK, ADVANCING_THREAT, CORNERED
    power_delta: float = 0.5                         # 0.0 balanced .. 1.0 total subjugation


class ActorStagingV3(UModel):
    actor_id: str
    spawn_point_world: list[float]                   # [x, y, z]
    initial_action: str = "STAND"
    initial_orientation: str = "FRONT"
    eyeline_target: Optional[str] = None
    territory_zone: Optional[str] = None             # e.g. "BEHIND_DESK", "BED_VICINITY"
    movement_path: list[list[float]] = Field(default_factory=list)  # waypoints in world space
    destination_world: Optional[list[float]] = None
    target_object_id: Optional[str] = None
    interaction_anchor: Optional[str] = None
    movement_purpose: Optional[str] = None           # APPROACHES, AVOIDS, CONFRONTS, ESCAPES, etc.


class SceneStagingPlan(UModel):
    actors: list[ActorStagingV3] = Field(default_factory=list)
    proxemics: list[ProxemicRelationship] = Field(default_factory=list)
    power_relationships: list[PowerRelationship] = Field(default_factory=list)
    primary_eyeline_axis: list[str] = Field(default_factory=list)  # [actor_a, actor_b]


# ==============================================================================
# 6. SCENE EVENT GRAPH & INFORMATION FLOW
# ==============================================================================

class EventEffect(UModel):
    target_type: str                                 # CHARACTER, OBJECT, ENVIRONMENT, INFORMATION, RELATIONSHIP, LIGHTING
    target_id: str
    property_changed: str
    old_value: Any
    new_value: Any


class SceneEvent(UModel):
    event_id: str                                    # e.g. EVT_01, EVT_02
    description: str
    initiating_actor_id: Optional[str] = None
    target_object_id: Optional[str] = None
    causal_trigger_id: Optional[str] = None          # which event provoked this
    effects: list[EventEffect] = Field(default_factory=list)


class InformationItem(UModel):
    item_id: str
    description: str
    physical_location: str                           # e.g. "INSIDE_DISPATCH_FOLDER", "ON_PRESSURE_GAUGE"
    viewer_knows: bool = True
    character_knowledge: dict[str, bool] = Field(default_factory=dict)  # char_id -> bool
    reveal_trigger: str = ""                         # e.g. "ACTOR_A_OPENS_FOLDER", "STEAM_CLEARS"


class SceneEventGraph(UModel):
    events: list[SceneEvent] = Field(default_factory=list)
    information_map: list[InformationItem] = Field(default_factory=list)
    reveal_opportunities: list[str] = Field(default_factory=list)


# ==============================================================================
# 7. SCENE START & END SNAPSHOTS
# ==============================================================================

class SceneStartState(UModel):
    actors: dict[str, dict[str, Any]] = Field(default_factory=dict)
    object_states: dict[str, str] = Field(default_factory=dict)
    lighting_state: str = "INITIAL"
    information_equilibrium: str = "STABLE"
    power_balance: str = "CONTESTED"


class SceneEndState(UModel):
    actors: dict[str, dict[str, Any]] = Field(default_factory=dict)
    object_states: dict[str, str] = Field(default_factory=dict)
    lighting_state: str = "MODIFIED"
    information_equilibrium: str = "DISRUPTED_OR_RESOLVED"
    power_balance: str = "DECIDED"
    physical_changes_summary: str = ""


# ==============================================================================
# 8. SCENE DESIGN V3 (MASTER CONTAINER)
# ==============================================================================

class SceneDesignV3(UModel):
    """The master intelligence defining the physical scene before cameras arrive."""
    scene_id: str
    story_beat_id: str
    location_id: str
    scene_purpose: ScenePurpose
    dramatic_question: str
    scene_outcome: SceneOutcome
    scene_identity: SceneIdentity
    production_design: ProductionDesignPlan
    geography: SceneGeographyV3
    staging: SceneStagingPlan
    event_graph: SceneEventGraph
    visual_progression: str                          # e.g. ORDERED -> CHAOTIC, EMPTY -> CROWDED, etc.
    energy_curve: list[str] = Field(default_factory=lambda: ["CALM", "BUILD", "IMPACT", "REACTION"])
    start_state: SceneStartState = Field(default_factory=SceneStartState)
    end_state: SceneEndState = Field(default_factory=SceneEndState)
    ideal_intent: str = ""
    executable_intent: str = ""
    asset_gap_requests: list[dict[str, Any]] = Field(default_factory=list)
    scene_critic_review: Optional[dict[str, Any]] = None
