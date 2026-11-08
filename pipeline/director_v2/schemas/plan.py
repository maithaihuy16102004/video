"""Retention, scene and shot plans. The Shot is the contract every renderer executes."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, field_validator

from .core import DV2Model, LayerRole, NormPoint, NormRect, norm_enum_token


class RetentionRole(str, Enum):
    HOOK = "HOOK"
    SETUP = "SETUP"
    QUESTION = "QUESTION"
    ESCALATION = "ESCALATION"
    PAYOFF = "PAYOFF"
    NEW_QUESTION = "NEW_QUESTION"
    CONFLICT = "CONFLICT"
    REACTION = "REACTION"
    RESOLUTION = "RESOLUTION"
    CLIFFHANGER = "CLIFFHANGER"


class ShotPurpose(str, Enum):
    ESTABLISH = "ESTABLISH"
    REVEAL = "REVEAL"
    DETAIL = "DETAIL"
    ACTION = "ACTION"
    DIALOGUE = "DIALOGUE"
    REACTION = "REACTION"
    EMPHASIS = "EMPHASIS"
    TRANSITION = "TRANSITION"
    INFORMATION = "INFORMATION"
    HOLD = "HOLD"


class ShotType(str, Enum):
    EXTREME_WIDE = "EXTREME_WIDE"
    WIDE = "WIDE"
    MEDIUM_WIDE = "MEDIUM_WIDE"
    MEDIUM = "MEDIUM"
    MEDIUM_CLOSE = "MEDIUM_CLOSE"
    CLOSE_UP = "CLOSE_UP"
    EXTREME_CLOSE = "EXTREME_CLOSE"
    OVER_THE_SHOULDER = "OVER_THE_SHOULDER"
    POV = "POV"
    INSERT = "INSERT"
    TWO_SHOT = "TWO_SHOT"


# Ordinal framing scale used to measure "how much did the framing change".
SHOT_SIZE_ORDINAL: dict[ShotType, float] = {
    ShotType.EXTREME_WIDE: 0.0,
    ShotType.WIDE: 1.0,
    ShotType.MEDIUM_WIDE: 2.0,
    ShotType.TWO_SHOT: 2.5,
    ShotType.MEDIUM: 3.0,
    ShotType.OVER_THE_SHOULDER: 3.5,
    ShotType.POV: 3.5,
    ShotType.MEDIUM_CLOSE: 4.0,
    ShotType.CLOSE_UP: 5.0,
    ShotType.INSERT: 5.5,
    ShotType.EXTREME_CLOSE: 6.0,
}


class CameraHeight(str, Enum):
    GROUND = "GROUND"
    LOW = "LOW"
    EYE_LEVEL = "EYE_LEVEL"
    HIGH = "HIGH"
    OVERHEAD = "OVERHEAD"


CAMERA_HEIGHT_ORDINAL: dict[CameraHeight, float] = {
    CameraHeight.GROUND: 0.0, CameraHeight.LOW: 1.0, CameraHeight.EYE_LEVEL: 2.0,
    CameraHeight.HIGH: 3.0, CameraHeight.OVERHEAD: 4.0,
}


class PerspectiveType(str, Enum):
    FLAT = "FLAT"
    ONE_POINT = "ONE_POINT"
    TWO_POINT = "TWO_POINT"
    THREE_POINT = "THREE_POINT"
    DEEP_DIAGONAL = "DEEP_DIAGONAL"
    WORM_EYE = "WORM_EYE"
    BIRD_EYE = "BIRD_EYE"


class BodyOrientation(str, Enum):
    FRONT = "FRONT"
    THREE_QUARTER_FRONT_LEFT = "THREE_QUARTER_FRONT_LEFT"
    THREE_QUARTER_FRONT_RIGHT = "THREE_QUARTER_FRONT_RIGHT"
    PROFILE_LEFT = "PROFILE_LEFT"
    PROFILE_RIGHT = "PROFILE_RIGHT"
    THREE_QUARTER_BACK_LEFT = "THREE_QUARTER_BACK_LEFT"
    THREE_QUARTER_BACK_RIGHT = "THREE_QUARTER_BACK_RIGHT"
    BACK = "BACK"
    POV_HANDS = "POV_HANDS"
    NONE = "NONE"


# Facing angle in degrees (0 = facing camera, 180 = facing away). Used for orientation delta.
ORIENTATION_ANGLE: dict[BodyOrientation, Optional[float]] = {
    BodyOrientation.FRONT: 0.0,
    BodyOrientation.THREE_QUARTER_FRONT_LEFT: -45.0,
    BodyOrientation.THREE_QUARTER_FRONT_RIGHT: 45.0,
    BodyOrientation.PROFILE_LEFT: -90.0,
    BodyOrientation.PROFILE_RIGHT: 90.0,
    BodyOrientation.THREE_QUARTER_BACK_LEFT: -135.0,
    BodyOrientation.THREE_QUARTER_BACK_RIGHT: 135.0,
    BodyOrientation.BACK: 180.0,
    BodyOrientation.POV_HANDS: None,
    BodyOrientation.NONE: None,
}


class CameraMotion(str, Enum):
    STATIC = "STATIC"
    SLOW_PUSH = "SLOW_PUSH"
    SLOW_PULL = "SLOW_PULL"
    PAN_LEFT = "PAN_LEFT"
    PAN_RIGHT = "PAN_RIGHT"
    TILT_UP = "TILT_UP"
    TILT_DOWN = "TILT_DOWN"
    TRACK_LEFT = "TRACK_LEFT"
    TRACK_RIGHT = "TRACK_RIGHT"
    CRANE_UP = "CRANE_UP"
    CRANE_DOWN = "CRANE_DOWN"
    ORBIT_LEFT = "ORBIT_LEFT"
    ORBIT_RIGHT = "ORBIT_RIGHT"
    HANDHELD = "HANDHELD"
    SHAKE_IMPACT = "SHAKE_IMPACT"
    RACK_FOCUS = "RACK_FOCUS"


class LightDirection(str, Enum):
    UPPER_LEFT = "UPPER_LEFT"
    UPPER_RIGHT = "UPPER_RIGHT"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    TOP = "TOP"
    FRONT = "FRONT"
    BACK = "BACK"
    BOTTOM = "BOTTOM"


class Transition(str, Enum):
    CUT = "CUT"
    MATCH_CUT = "MATCH_CUT"
    SMASH_CUT = "SMASH_CUT"
    DISSOLVE = "DISSOLVE"
    WHIP_PAN = "WHIP_PAN"
    FADE_BLACK = "FADE_BLACK"
    FADE_IN = "FADE_IN"
    L_CUT = "L_CUT"
    J_CUT = "J_CUT"
    WIPE = "WIPE"


class RetentionSegment(DV2Model):
    segment_id: str
    role: RetentionRole
    beat_ids: list[str]
    target_duration_sec: float
    shot_durations: list[float]
    intensity: float = 0.4
    reason: str = ""


class Scene(DV2Model):
    scene_id: str
    index: int
    location_id: str
    year: Optional[int] = None
    beat_ids: list[str]
    retention_roles: list[RetentionRole] = Field(default_factory=list)
    narration: str = ""
    summary: str = ""
    emotional_tone: str = "neutral"
    character_ids: list[str] = Field(default_factory=list)
    start_sec: float = 0.0
    duration_sec: float = 0.0
    screen_direction: str = "LEFT_TO_RIGHT"   # 180-degree rule anchor for the scene


class ScenePlan(DV2Model):
    retention: list[RetentionSegment]
    scenes: list[Scene]
    total_duration_sec: float


class LayerIntent(DV2Model):
    role: LayerRole
    description: str = ""
    source: str = "generated"                # generated | reuse | rig | procedural | none
    requirement_id: Optional[str] = None
    parallax: float = 0.5
    crop: Optional[NormRect] = None
    matte: str = "none"                      # none | chroma_green | segment


class Shot(DV2Model):
    # identity / story
    shot_id: str
    scene_id: str
    beat_id: str
    index: int
    start_sec: float = 0.0
    duration: float = Field(gt=0.0)
    shot_purpose: ShotPurpose
    story_beat: str = "exposition"
    retention_role: RetentionRole = RetentionRole.SETUP
    emotional_tone: str = "neutral"
    narration_text: str = ""
    is_signature: bool = False
    intentional_repetition: bool = False
    continuity_required: bool = False

    # camera
    shot_type: ShotType
    camera_height: CameraHeight
    camera_yaw: float = Field(default=0.0, ge=-180.0, le=180.0)
    camera_pitch: float = Field(default=0.0, ge=-90.0, le=90.0)
    lens_feel: str = "35mm"
    camera_motion: CameraMotion = CameraMotion.STATIC
    camera_motion_reason: str = ""
    look_at_target: str = "subject"
    archetype_id: Optional[str] = None

    # perspective
    perspective_type: PerspectiveType
    horizon_y: float = Field(default=0.5, ge=-1.0, le=2.0)
    vanishing_point_primary: NormPoint
    vanishing_point_secondary: Optional[NormPoint] = None

    # subject / acting
    subject_x: float = Field(default=0.5, ge=-0.5, le=1.5)
    subject_y: float = Field(default=0.75, ge=-0.5, le=2.0)
    subject_scale: float = Field(default=0.5, gt=0.0, le=4.0)
    body_orientation: BodyOrientation = BodyOrientation.THREE_QUARTER_FRONT_RIGHT
    head_direction: str = "FORWARD"
    eyeline: str = "OFF_SCREEN_RIGHT"
    action_verb: str = "stand"
    pose_family: str = "POSE_NEUTRAL_STAND"
    weight_distribution: str = "CENTER_50_50"

    # depth
    foreground: str = ""
    midground: str = ""
    background: str = ""
    far_background: str = ""
    foreground_occlusion: float = Field(default=0.0, ge=0.0, le=1.0)
    background_action: str = ""
    secondary_action: str = ""

    # lighting
    key_light_direction: LightDirection = LightDirection.UPPER_LEFT
    key_light_intensity: float = Field(default=0.7, ge=0.0, le=1.0)
    fill: float = Field(default=0.35, ge=0.0, le=1.0)
    rim_light: bool = False
    shadow_softness: float = Field(default=0.5, ge=0.0, le=1.0)
    atmosphere: str = "clear"

    # continuity / references
    character_ids: list[str] = Field(default_factory=list)
    location_id: str
    costume_state_ids: list[str] = Field(default_factory=list)
    prop_ids: list[str] = Field(default_factory=list)
    continuity_from_previous: str = ""
    historical_constraints: list[str] = Field(default_factory=list)

    # assets
    asset_requirements: list[str] = Field(default_factory=list)
    reusable_asset_ids: list[str] = Field(default_factory=list)
    layers: list[LayerIntent] = Field(default_factory=list)

    # edit
    transition_in: Transition = Transition.CUT
    transition_out: Transition = Transition.CUT

    # validation trace
    visual_similarity_score: float = 0.0
    most_similar_shot_id: Optional[str] = None
    is_stage_view: bool = False
    validator_action: str = "PENDING"
    replan_history: list[str] = Field(default_factory=list)

    @field_validator(
        "shot_purpose", "retention_role", "shot_type", "camera_height", "camera_motion",
        "perspective_type", "body_orientation", "key_light_direction", "transition_in",
        "transition_out", mode="before",
    )
    @classmethod
    def _norm_enums(cls, v):
        return norm_enum_token(v)


class ShotPlan(DV2Model):
    shots: list[Shot]
    total_duration_sec: float
