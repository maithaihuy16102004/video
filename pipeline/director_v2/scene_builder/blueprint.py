"""Scene Blueprint: The Architectural Contract between Director V2 and Gemini Scene Builder.

Principles:
- DIRECTOR DESIGNS: Story, camera, composition, horizon, perspective, reserved zone, historical boundaries.
- GEMINI BUILDS: Visual realization of the environment, textures, storytelling details, depth planes.
- CRITIC INSPECTS: Quality control and compliance against the Blueprint.
- STICKMAN ACTS: Vector stickman placed in the reserved zone with matching lighting & perspective.
- MOTION CANVAS SHOOTS: Animation, camera motion, micro-animations, and parallax.

Creative Freedom Categorization:
- LOCKED: Camera, horizon, perspective, character reserved zone, historical year, location ID, shot purpose.
- GUIDED: Environment props, background population, weather details, damage, furniture, secondary action.
- FREE: Micro texture, small debris, surface variation, minor atmospheric nuances.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StorySpec:
    narration: str
    previous_beat: str
    current_beat: str
    next_beat: str
    purpose: str
    emotion: str


@dataclass
class HistorySpec:
    year: int
    location_id: str
    country: str = "Germany"
    date: str = ""
    event_context: str = ""
    political_military_context: str = ""
    available_technology: list[str] = field(default_factory=list)
    appropriate_architecture: list[str] = field(default_factory=list)
    appropriate_transport: list[str] = field(default_factory=list)
    appropriate_props: list[str] = field(default_factory=list)
    historical_constraints: list[str] = field(default_factory=list)


@dataclass
class CameraSpec:
    shot_size: str          # EXTREME_WIDE, WIDE, MEDIUM, CLOSE, LOW_ANGLE, HIGH_ANGLE, GROUND_LEVEL, OTS, POV, DEEP_PERSPECTIVE
    height: str             # GROUND_LEVEL, LOW_ANGLE, EYE_LEVEL, HIGH_ANGLE, BIRDS_EYE
    yaw: float              # Degrees (-45 to +45)
    pitch: float            # Degrees (-45 to +45)
    lens_feel: str          # WIDE_24MM, NORMAL_50MM, TELE_85MM
    horizon_y: float        # Normalized 0.0 - 1.0 from top of frame


@dataclass
class PerspectiveSpec:
    type: str               # ONE_POINT, TWO_POINT, THREE_POINT, TELE_COMPRESSION
    primary_vp: list[float] # [x, y]
    secondary_vp: list[float] # [x, y]
    depth_axis: str         # CENTER_BACK, RIGHT_BACK, LEFT_BACK, ZIG_ZAG


@dataclass
class ReservedZone:
    x: float                # Center or left anchor
    y: float                # Top or base anchor
    width: float            # Normalized 0.0 - 1.0
    height: float           # Normalized 0.0 - 1.0

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class CompositionSpec:
    visual_focus: str       # PROTAGONIST, ENVIRONMENT, SECONDARY_ACTION
    character_reserved_zone: ReservedZone
    negative_space_zone: dict[str, float] = field(default_factory=dict)
    foreground_occlusion: float = 0.0
    eyeline: str = "HORIZON"


@dataclass
class EnvironmentSpec:
    foreground: list[str] = field(default_factory=list)
    midground: list[str] = field(default_factory=list)
    background: list[str] = field(default_factory=list)
    far_background: list[str] = field(default_factory=list)
    storytelling_details: list[str] = field(default_factory=list)  # 1-3 key narrative props
    secondary_actions: list[str] = field(default_factory=list)     # Distant atmospheric movement


@dataclass
class LightingSpec:
    key_direction: str      # LEFT_HIGH, RIGHT_HIGH, FRONT_LOW, OVERHEAD, BACKLIT
    key_intensity: float    # 0.0 - 1.0
    ambient_level: float    # 0.0 - 1.0
    shadow_direction: str   # BOTTOM_RIGHT, BOTTOM_LEFT, BEHIND, LONG_FORWARD
    color_temperature: str  # WARM_INDOOR, COLD_DUSK, SULLEN_OVERCAST, GOLDEN_HOUR
    rim_opportunity: bool = False
    practical_lights: list[str] = field(default_factory=list)


@dataclass
class AtmosphereSpec:
    haze: str               # NONE, LIGHT_MIST, HEAVY_FOG, SMOKE_DUST
    weather: str            # DRY, DRIZZLE, MUDDY_FREEZE, COLD_SUN
    time_of_day: str        # DAWN, MORNING, MIDDAY, DUSK, NIGHT
    volumetric_light: bool = False


@dataclass
class ContinuitySpec:
    location_dna_ref: str   # Location ID or Master ID
    recurring_features: list[str] = field(default_factory=list)
    lighting_consistency_key: str = ""


@dataclass
class CharacterSpec:
    character_id: str
    approximate_position: list[float]  # [x, y]
    scale: float                       # 0.15 - 0.90
    body_orientation: str              # FRONT_THREE_QUARTER, PROFILE_RIGHT, PROFILE_LEFT, BACK
    pose_envelope: str                 # ALERT_STAND, ORATE_FIST, THINK_CHIN, DUCK_COVER, LIE_BED, KNEEL_GRIEF
    action: str = "observe"


@dataclass
class BackgroundActor:
    actor_id: str
    action: str
    depth_plane: str
    position: list[float]
    scale: float
    orientation: str = "PROFILE_RIGHT"
    interaction_target: str = ""


@dataclass
class StoryPropState:
    prop_id: str
    state: str
    depth_plane: str
    position: list[float]


@dataclass
class SceneVitalityPlan:
    activity_level: str = "LOW_ACTIVITY"
    richness_budget: str = "MINIMAL"
    primary_action: str = ""
    secondary_actions: list[str] = field(default_factory=list)
    background_actions: list[str] = field(default_factory=list)
    foreground_event: str = ""
    environmental_motion: list[str] = field(default_factory=list)
    depth_events: dict[str, list[str]] = field(default_factory=dict)
    reaction_beats: list[str] = field(default_factory=list)
    visual_eye_path: list[str] = field(default_factory=list)
    quiet_zones: list[dict[str, float]] = field(default_factory=list)
    asymmetry_bias: float = 0.5
    background_actors: list[BackgroundActor] = field(default_factory=list)
    storytelling_props: list[StoryPropState] = field(default_factory=list)
    primary_light_reason: str = ""
    secondary_light: str = ""
    shadow_zone: str = ""


@dataclass
class CreativeFreedom:
    locked: list[str] = field(default_factory=lambda: [
        "camera_height", "camera_pitch", "camera_yaw", "horizon_y",
        "perspective_type", "primary_vp", "depth_axis",
        "character_reserved_zone", "historical_year", "location_id",
        "shot_purpose", "main_lighting_direction"
    ])
    guided: list[str] = field(default_factory=lambda: [
        "environment_props", "background_population", "weather_nuance",
        "trench_damage", "furniture_arrangement", "secondary_action"
    ])
    free: list[str] = field(default_factory=lambda: [
        "micro_texture", "small_debris", "surface_wear",
        "puddle_shape", "atmospheric_drift"
    ])


@dataclass
class SceneBlueprint:
    scene_id: str
    shot_id: str
    story: StorySpec
    history: HistorySpec
    camera: CameraSpec
    perspective: PerspectiveSpec
    composition: CompositionSpec
    environment: EnvironmentSpec
    lighting: LightingSpec
    atmosphere: AtmosphereSpec
    continuity: ContinuitySpec
    character: CharacterSpec
    vitality: SceneVitalityPlan | None = None
    negative_constraints: list[str] = field(default_factory=list)
    creative_freedom: CreativeFreedom = field(default_factory=CreativeFreedom)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save_to_file(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path
