"""Universal data contracts.  Story knowledge lives in instances, never in code.

StoryIntelligence  <- reasoning provider (Gemini / offline)
CharacterBible     <- bibles stage (character DNA, age variants, costumes, voices)
LocationBible      <- bibles stage (location DNA, prop vocabulary)
SceneBlueprint     <- cinematic director; the ONLY thing renderers consume
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class UModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    def dump(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# =============================================================== story intelligence
class Period(UModel):
    start_year: Optional[int] = None
    end_year: Optional[int] = None


class TimelineEvent(UModel):
    event_id: str
    year: Optional[int] = None
    month: Optional[int] = None
    description: str = ""
    location_id: Optional[str] = None
    confidence: str = "UNCERTAIN"


class CharacterMention(UModel):
    character_id: str
    name: str
    role: str = "SUPPORTING"
    aliases: list[str] = Field(default_factory=list)
    is_narrator: bool = False
    on_screen: bool = True
    speaking: bool = False
    historical_person: bool = False
    birth_year: Optional[int] = None
    description: str = ""


class LocationMention(UModel):
    location_id: str
    name: str
    year: Optional[int] = None
    region: str = ""
    description: str = ""
    enclosure: str = "EXTERIOR"


class BeatAction(UModel):
    actor_id: str
    verb: str = "STAND"
    target: Optional[str] = None          # character_id or object semantic
    emotion: str = "CALM"


class StoryBeat(UModel):
    beat_id: str
    index: int
    text: str
    speaker_id: Optional[str] = None
    is_dialogue: bool = False
    location_id: Optional[str] = None
    year: Optional[int] = None
    characters: list[str] = Field(default_factory=list)
    actions: list[BeatAction] = Field(default_factory=list)
    beat_type: str = "EXPOSITION"
    suggested_purpose: str = "INFORMATION"
    emotional_intensity: float = 0.4
    tension: float = 0.3
    new_information: bool = True
    comedy: str = "NONE"                  # NONE | SETUP | PAYOFF
    opens_loops: list[str] = Field(default_factory=list)
    closes_loops: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    visual_opportunities: list[str] = Field(default_factory=list)
    weather: Optional[str] = None
    est_duration_sec: float = 3.0


class Relationship(UModel):
    a: str
    b: str
    type: str = "KNOWS"


class StoryObject(UModel):
    object_id: str
    semantic: str
    category: str = ""
    materials: list[str] = Field(default_factory=list)
    period_year: Optional[int] = None


class HistoricalEntity(UModel):
    entity: str
    category: str = "EVENT"
    year: Optional[int] = None
    claim: str = ""
    confidence: str = "UNCERTAIN"
    needs_verification: bool = True


class OpenLoop(UModel):
    loop_id: str
    question: str
    opened_beat: Optional[str] = None
    closed_beat: Optional[str] = None


class ResearchRequirement(UModel):
    item: str
    category: str = "EVENT"
    question: str = ""
    confidence: str = "UNCERTAIN"


class StoryIntelligence(UModel):
    title: str = "Untitled"
    language: str = "en"
    genre: str = ""
    period: Period = Field(default_factory=Period)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    characters: list[CharacterMention] = Field(default_factory=list)
    locations: list[LocationMention] = Field(default_factory=list)
    story_beats: list[StoryBeat] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    objects: list[StoryObject] = Field(default_factory=list)
    historical_entities: list[HistoricalEntity] = Field(default_factory=list)
    emotional_curve: list[float] = Field(default_factory=list)
    open_loops: list[OpenLoop] = Field(default_factory=list)
    comedy_opportunities: list[str] = Field(default_factory=list)
    tension_points: list[str] = Field(default_factory=list)
    cliffhanger: str = ""
    research_requirements: list[ResearchRequirement] = Field(default_factory=list)
    reasoning_source: str = "UNKNOWN"


# =============================================================== character DNA
class HairStyleDNA(UModel):
    shape: str = "CROPPED"
    hairline: str = "MEDIUM"
    part: str = "NONE"
    length: str = "SHORT"
    fringe: str = "NONE"
    volume: float = 0.5
    roughness: float = 0.25
    strand_clusters: int = 4
    color: str = "#3a2a1e"


class FaceDNA(UModel):
    head_width: float = 1.0
    head_height: float = 1.0
    jaw_shape: str = "ROUND"
    eye_spacing: float = 1.0
    eye_shape: str = "DOT"
    brow_shape: str = "FLAT"
    nose_style: str = "BUTTON"
    mouth_style: str = "LINE"
    ear_style: str = "NORMAL"
    facial_hair: str = "NONE"
    facial_hair_color: Optional[str] = None
    skin_tone: str = "#e9c9a6"
    distinctive_anchors: list[str] = Field(default_factory=list)


class BodyDNA(UModel):
    height: float = 1.0
    build: str = "AVERAGE"
    shoulder_width: float = 1.0
    posture: str = "UPRIGHT"
    head_scale: float = 1.0


class CostumeDNA(UModel):
    headwear: str = "NONE"
    upper_garment: str = "SHIRT"
    outerwear: str = "NONE"
    lower_garment: str = "TROUSERS"
    footwear: str = "SHOES"
    equipment: list[str] = Field(default_factory=list)
    accessories: list[str] = Field(default_factory=list)
    insignia: list[str] = Field(default_factory=list)
    condition: str = "CLEAN"
    palette: dict[str, str] = Field(default_factory=lambda: {
        "primary": "#5b6470", "secondary": "#3b3f46", "accent": "#b08d57", "trim": "#2a2a2a"})


class CostumeVariant(UModel):
    costume_id: str
    label: str = ""
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    location_ids: list[str] = Field(default_factory=list)
    contexts: list[str] = Field(default_factory=list)       # e.g. ["MILITARY", "HOSPITAL", "CIVILIAN", "RAIN"]
    costume: CostumeDNA = Field(default_factory=CostumeDNA)
    historical_confidence: str = "PLAUSIBLE_RECONSTRUCTION"


class CharacterVariant(UModel):
    variant_id: str
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    age: Optional[int] = None
    hair: Optional[HairStyleDNA] = None
    face: Optional[FaceDNA] = None
    body: Optional[BodyDNA] = None
    conditions: list[str] = Field(default_factory=list)
    default_costume_id: Optional[str] = None


class PerformanceDNA(UModel):
    gesture_scale: float = 1.0
    posture_bias: float = 0.0
    movement_energy: float = 1.0
    personal_space: float = 1.0
    reaction_scale: float = 1.0
    dominant_hand: str = "RIGHT"
    confidence_bias: float = 0.0


class CharacterDNA(UModel):
    character_id: str
    name: str
    role: str = "SUPPORTING"
    detail_level: str = "SUPPORT"
    on_screen: bool = True
    is_narrator: bool = False
    historical_person: bool = False
    birth_year: Optional[int] = None
    visual_identity: str = ""
    hair: HairStyleDNA = Field(default_factory=HairStyleDNA)
    face: FaceDNA = Field(default_factory=FaceDNA)
    body: BodyDNA = Field(default_factory=BodyDNA)
    costumes: list[CostumeVariant] = Field(default_factory=list)
    variants: list[CharacterVariant] = Field(default_factory=list)
    performance: PerformanceDNA = Field(default_factory=PerformanceDNA)
    voice_id: str = ""
    continuity_rules: list[str] = Field(default_factory=list)
    historical_confidence: str = "UNCERTAIN"
    proposal_source: str = "UNKNOWN"     # REASONING | FALLBACK_PROPOSAL


class CharacterBible(UModel):
    characters: list[CharacterDNA] = Field(default_factory=list)

    def get(self, cid: str) -> Optional[CharacterDNA]:
        return next((c for c in self.characters if c.character_id == cid), None)


class ResolvedCharacter(UModel):
    """Character appearance after age/costume resolution for one shot."""
    character_id: str
    variant_id: str
    costume_id: str
    age: Optional[int] = None
    hair: HairStyleDNA
    face: FaceDNA
    body: BodyDNA
    costume: CostumeDNA
    conditions: list[str] = Field(default_factory=list)
    performance: PerformanceDNA = Field(default_factory=PerformanceDNA)


# =============================================================== location DNA
class PropSpec(UModel):
    semantic: str
    category: str = "DEBRIS"
    role: str = "DRESSING"
    materials: list[str] = Field(default_factory=list)
    count: int = 1
    affordances: list[str] = Field(default_factory=list)


class LocationDNA(UModel):
    location_id: str
    name: str
    period_from: Optional[int] = None
    period_to: Optional[int] = None
    region: str = ""
    architecture: str = ""
    enclosure: str = "EXTERIOR"
    ceiling: str = "SKY"
    wall_treatment: str = "PLAIN"
    floor_feature: str = "BARE"
    openings: str = "NONE"
    horizon_feature: str = "NONE"
    materials: list[str] = Field(default_factory=lambda: ["STONE"])
    palette: dict[str, str] = Field(default_factory=lambda: {
        "sky_top": "#9fb4c8", "sky_bottom": "#d9d2c0", "wall": "#b9ae98", "floor": "#7d6a52",
        "accent": "#c79b52", "shadow": "#2b2a30"})
    lighting_behavior: str = "OVERCAST"
    weather: str = "CLEAR"
    atmosphere: list[str] = Field(default_factory=list)
    wear: float = 0.3
    density: str = "BALANCED"
    props: list[PropSpec] = Field(default_factory=list)
    foreground_vocabulary: list[PropSpec] = Field(default_factory=list)
    background_activity: list[str] = Field(default_factory=list)
    historical_constraints: list[str] = Field(default_factory=list)
    reusable_masters: list[str] = Field(default_factory=list)
    historical_confidence: str = "UNCERTAIN"
    proposal_source: str = "UNKNOWN"


class LocationBible(UModel):
    locations: list[LocationDNA] = Field(default_factory=list)

    def get(self, lid: str) -> Optional[LocationDNA]:
        return next((l for l in self.locations if l.location_id == lid), None)


class BiblesProposal(UModel):
    """Raw reasoning output for the bibles stage (validated before use)."""
    characters: list[CharacterDNA] = Field(default_factory=list)
    locations: list[LocationDNA] = Field(default_factory=list)


# =============================================================== assets
class AssetRequirement(UModel):
    requirement_id: str
    semantic: str
    category: str
    period_year: Optional[int] = None
    region: str = ""
    materials: list[str] = Field(default_factory=list)
    role: str = "DRESSING"
    location_id: str = ""


class AssetResolution(UModel):
    requirement_id: str
    semantic: str
    status: str                    # MATCH | COMPATIBLE_FALLBACK | GENERIC_CATEGORY
    asset_id: str
    score: float
    confidence: str                # HIGH | MEDIUM | LOW
    reasons: list[str] = Field(default_factory=list)


# =============================================================== blueprint
class CameraSpec(UModel):
    shot: str = "MEDIUM"
    height: str = "EYE"
    height_m: float = 1.6
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    lens: str = "NORMAL"
    perspective: str = "ONE_POINT"
    horizon_y: float = 0.5
    vanishing_point: list[float] = Field(default_factory=lambda: [0.5, 0.5])
    vanishing_point_secondary: Optional[list[float]] = None
    depth_layout: str = "LAYERED"
    subject_height_px: float = 420.0
    subject_position: list[float] = Field(default_factory=lambda: [0.5, 0.8])
    motion: str = "STATIC"
    position: list[float] = Field(default_factory=lambda: [0.5, 0.5, 1.6])
    target: list[float] = Field(default_factory=lambda: [0.5, 0.5, 0.0])
    distance: float = 1.0
    lens_intent: str = "NORMAL"
    foreground_distance: float = 0.15


class ActorBlock(UModel):
    character_id: str
    variant_id: str = ""
    costume_id: str = ""
    detail_level: str = "SUPPORT"
    action: str = "STAND"
    emotion: str = "CALM"
    intensity: str = "NORMAL"
    body_weight: str = "CENTERED"
    orientation: str = "FRONT"
    eyeline_target: Optional[str] = None
    contact_target: Optional[str] = None         # "<prop_instance_id>.<anchor>"
    screen_x: float = 0.5
    depth: float = 0.3                            # 0 near camera .. 1 far
    depth_plane: str = "MG"
    height_px: float = 420.0
    silhouette: bool = False
    performance_intent: str = ""
    head_angle_deg: float = 0.0
    spine_curve: float = 0.0                     # -1.0 leaning back .. +1.0 forward
    shoulder_slope: float = 0.0
    hand_target: Optional[str] = None
    performance_phrase: list[str] = Field(default_factory=list)


class VisualConcept(UModel):
    """Creative scene visual direction generated by Gemini."""
    story_function: str = ""
    emotional_target: str = ""
    visual_metaphor: str = ""
    primary_visual_idea: str = ""
    viewer_position_concept: str = ""
    dominant_subject: str = ""
    important_object: str = ""
    hidden_information: str = ""
    reveal_information: str = ""
    environment_storytelling: str = ""
    character_performance_intent: str = ""
    lighting_story: dict[str, Any] = Field(default_factory=dict)
    depth_story: dict[str, Any] = Field(default_factory=dict)
    color_story: dict[str, Any] = Field(default_factory=dict)
    visual_contrast: str = ""
    shot_sequence_strategy: str = ""


class LocationMasterPlan(UModel):
    """World-space production master plan for consistent spatial layout."""
    location_id: str
    name: str
    enclosure: str = "INTERIOR"
    why_this_place_looks_this_way: str = ""
    architecture_style: str = ""
    materials: list[str] = Field(default_factory=list)
    spatial_layout: dict[str, Any] = Field(default_factory=dict)
    interaction_surfaces: list[dict[str, Any]] = Field(default_factory=list)
    walkable_zones: list[list[float]] = Field(default_factory=list)
    occluders: list[dict[str, Any]] = Field(default_factory=list)
    light_sources: list[dict[str, Any]] = Field(default_factory=list)
    camera_accessible_zones: list[str] = Field(default_factory=list)
    hero_props: list[str] = Field(default_factory=list)
    environmental_wear: str = "WEATHERED"
    human_traces: str = ""


class PropPlacement(UModel):
    instance_id: str
    semantic: str
    asset_id: str
    resolution_status: str
    category: str
    role: str
    depth_plane: str
    screen_x: float
    depth: float
    state: str = "STATIC"
    mount: str = "FLOOR"


class VisualEyePath(UModel):
    steps: list[str] = Field(default_factory=list)   # e.g. ["ACTOR:x", "OBJECT:y", "REACTION:z"]


class HistoricalNote(UModel):
    item: str
    confidence: str
    note: str = ""


class DialogueLine(UModel):
    speaker_id: str
    voice_id: str
    text: str
    delivery: str = "NEUTRAL"


class SceneBlueprint(UModel):
    scene_id: str
    shot_id: str
    shot_index: int
    beat_ids: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    location_id: str
    shot_purpose: str
    purpose_reason: str = ""
    visual_question: str = ""
    visual_answer: str = ""
    camera_reason: str = ""
    motion_reason: str = ""
    reveal_strategy: str = "NONE"
    primary_focus: str = ""
    secondary_focus: str = ""
    foreground_frame: str = "NONE"
    foreground_ratio: float = 0.0
    leading_lines: list[str] = Field(default_factory=list)
    negative_space: str = "NONE"
    cut_reason: str = "NEW_INFORMATION"
    visual_energy: str = "MEDIUM"
    composition_fingerprint: dict[str, Any] = Field(default_factory=dict)
    camera: CameraSpec
    actors: list[ActorBlock] = Field(default_factory=list)
    props: list[PropPlacement] = Field(default_factory=list)
    object_states: dict[str, str] = Field(default_factory=dict)
    depth_planes: dict[str, float] = Field(default_factory=lambda: {
        "NEAR_FG": 0.04, "FG": 0.15, "MG": 0.35, "BG": 0.65, "FAR_BG": 0.92})
    lighting_story: dict[str, Any] = Field(default_factory=dict)
    vitality: dict[str, Any] = Field(default_factory=dict)
    visual_eye_path: VisualEyePath = Field(default_factory=VisualEyePath)
    historical_metadata: list[HistoricalNote] = Field(default_factory=list)
    continuity: dict[str, Any] = Field(default_factory=dict)
    dialogue: list[DialogueLine] = Field(default_factory=list)
    narration: str = ""
    motion_intent: dict[str, Any] = Field(default_factory=dict)
    state_before: Optional[dict[str, Any]] = None
    state_after: Optional[dict[str, Any]] = None
    story_change: str = "NONE"
    information_change: str = "NONE"
    physical_change: str = "NONE"
    information_state: Optional[dict[str, Any]] = None
    reaction_to_event_id: Optional[str] = None
    removal_consequence: str = ""
    camera_zone: str = "TABLE_SIDE_ZONE"
    foreground_element: Optional[dict[str, Any]] = None
    visual_concept: Optional[dict[str, Any]] = None
    performance_intent: str = ""
    production_design: Optional[dict[str, Any]] = None
    scene_design_v3: Optional[dict[str, Any]] = None
    real_metrics: Optional[dict[str, Any]] = None
    critic_review: Optional[dict[str, Any]] = None
    duration_sec: float = 3.0
    seed: int = 0
    validation: dict[str, Any] = Field(default_factory=dict)
