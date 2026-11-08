"""Render manifest — the only input Phase 2 renderers (Motion Canvas / PyCairo) need."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from .core import DV2Model, LayerRole, NormRect, SafeArea


class RigPlacement(DV2Model):
    character_id: str
    state_id: Optional[str] = None
    costume_id: Optional[str] = None
    rig_id: str = "stickman_v1"
    x: float
    y: float
    scale: float
    orientation: str
    head_direction: str
    eyeline: str
    action_verb: str
    pose_family: str
    weight_distribution: str
    color_identity: str = "#3a3a3a"


class RenderLayer(DV2Model):
    role: LayerRole
    z: int
    source: str                              # generated | reuse | rig | procedural | none
    requirement_id: Optional[str] = None
    asset_path: Optional[str] = None
    asset_status: Optional[str] = None
    crop: Optional[NormRect] = None
    parallax: float
    matte: str = "none"
    description: str = ""
    procedural_hint: str = ""                # fallback drawing hint (draft renderer / missing asset)
    rigs: list[RigPlacement] = Field(default_factory=list)


class CameraKey(DV2Model):
    zoom: float = 1.0
    pan_x: float = 0.0                       # normalized frame widths
    pan_y: float = 0.0                       # normalized frame heights
    roll_deg: float = 0.0


class CameraTrack(DV2Model):
    motion: str
    start: CameraKey
    end: CameraKey
    easing: str = "easeInOutCubic"
    shake: float = 0.0
    reason: str = ""


class AudioCue(DV2Model):
    kind: str                                # narration | dialogue | sfx | music_hint
    text: str = ""
    speaker: Optional[str] = None
    voice: Optional[str] = None
    start_sec: float = 0.0
    duration_sec: Optional[float] = None


class RenderShot(DV2Model):
    shot_id: str
    scene_id: str
    start_sec: float
    duration_sec: float
    start_frame: int
    frame_count: int
    shot_type: str
    camera_height: str = "EYE_LEVEL"
    camera_pitch: float = 0.0
    camera_yaw: float = 0.0
    lens_feel: str = "35mm"
    depth_axis: str = "Z_INTO_SCREEN"
    perspective_type: str
    horizon_y: float
    vanishing_point_primary: dict
    vanishing_point_secondary: Optional[dict] = None
    layers: list[RenderLayer]
    camera: CameraTrack
    lighting: dict
    atmosphere: str
    transition_in: str
    transition_out: str
    audio: list[AudioCue] = Field(default_factory=list)
    location_id: str
    year: Optional[int] = None


class RenderOutput(DV2Model):
    width: int
    height: int
    fps: int
    aspect_ratio: str
    safe_area: SafeArea
    reframe_policy: str


class RenderManifest(DV2Model):
    manifest_version: str = "dv2.render.1"
    project_id: str
    quality: str
    output: RenderOutput
    total_duration_sec: float
    total_frames: int
    renderer_hint: str                       # pycairo_draft | motion_canvas
    shots: list[RenderShot]
