"""Shared contracts for the Cinematic Engine Upgrade.

ATLAS-OWNED — defined before parallel implementation per Mai's
directive (2026-11-12 17:01). Subagents A (motion/acting) and B
(environment/cinematography) import from this module and MUST NOT
modify it. Interface questions go back to ATLAS; no unilateral
contract changes, no duplicated definitions elsewhere.

Architecture mapping (directive names -> existing modules; do NOT
create competing implementations):

* Semantic Story Compiler -> studio_script_v1.py + adapter +
  action_compiler.py (existing; no new compiler module).
* Story Beats + Audio Timeline -> product_flow.py timeline (single,
  audio-driven; ATLAS-owned).
* Cinematic Shot Planner -> plan_shots in product_renderer.py
  (refactored in place by ATLAS; no second planner).
* Unified Scene Timeline -> the one timeline above, consumed by
  Renderer25D and the Motion Canvas emitter (motioncanvas_spec.py).
* Locomotion Engine -> animation/rig.py + animation/primitives.py
  (Subagent A), driven by GaitProfile below.
* Camera Director -> camera_planner.py (Subagent B), driven by
  CameraMode / CameraDirective below.

Measurement rule (Phase A/F): locomotion and proportion metrics are
reported in NORMALIZED character-space units (fractions of character
height), never raw pixels, unless a test explicitly states pixels.
Step length and stride length are DIFFERENT measurements and must
never be mixed: step = one footfall, stride = the full two-step
cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "LocomotionState",
    "GaitProfile",
    "CANONICAL_GAIT",
    "LocomotionMetrics",
    "CameraMode",
    "DEFAULT_CAMERA_MODE",
    "CameraDirective",
    "CameraValidation",
    "TRANSFORM_TOLERANCE",
    "MICRO_ANIMATIONS",
    "ExpressionTransition",
    "REQUIRED_LOCATION_TRAITS",
    "BBOX_KINDS",
]


# ------------------------------------------------------------------
# Locomotion (Phase A; Subagent A implements, ATLAS integrates)
# ------------------------------------------------------------------

class LocomotionState(Enum):
    IDLE = "idle"
    START_WALK = "start_walk"
    WALK = "walk"
    STOP_WALK = "stop_walk"
    TURN = "turn"
    START_RUN = "start_run"
    RUN = "run"
    STOP_RUN = "stop_run"
    TERRAIN_ADAPTATION = "terrain_adaptation"


@dataclass(frozen=True)
class GaitProfile:
    """One shared canonical engine, parameterized per character (D1).

    All lengths in character heights; cadence in steps/minute.
    ``step_length`` is ONE step (reference target 0.25-0.33);
    ``stride_length`` is the FULL two-step cycle (for a symmetric
    gait, stride == 2 * step; asymmetric gaits may differ, and both
    values must still be reported separately). ``movement_speed``
    is heights/second; None derives it from cadence * step_length.
    ``head_stability`` 1.0 = head almost level (reference);
    ``fatigue`` 0.0 = fresh. ``posture``, ``arm_pose``,
    ``terrain_response`` and ``locomotion_style`` are open strings
    with the documented values below; profiles may add values only
    through ATLAS.
    """

    step_length: float = 0.29
    stride_length: float = 0.58
    cadence: float = 80.0
    movement_speed: float | None = None
    body_mass: float = 1.0
    posture: str = "upright"  # upright | stooped | military | regal
    head_stability: float = 1.0  # 0..1
    arm_pose: str = "task"  # task | swing | carrying | restrained
    fatigue: float = 0.0  # 0..1
    terrain_response: str = "flat"  # flat | mud | slope | stairs | sand
    locomotion_style: str = "canonical"

    def __post_init__(self):
        if not 0.05 <= self.step_length <= 0.60:
            raise ValueError(f"step_length out of range: {self.step_length}")
        if not 0.10 <= self.stride_length <= 1.20:
            raise ValueError(
                f"stride_length out of range: {self.stride_length}")
        if self.stride_length < self.step_length:
            raise ValueError("stride_length must be >= step_length")
        if not 30.0 <= self.cadence <= 220.0:
            raise ValueError(f"cadence out of range: {self.cadence}")
        if not 0.0 <= self.head_stability <= 1.0:
            raise ValueError(
                f"head_stability out of range: {self.head_stability}")
        if not 0.0 <= self.fatigue <= 1.0:
            raise ValueError(f"fatigue out of range: {self.fatigue}")
        if self.body_mass <= 0:
            raise ValueError(f"body_mass must be positive: {self.body_mass}")

    @property
    def effective_speed(self) -> float:
        """Heights/second: explicit speed, else cadence * step."""
        if self.movement_speed is not None:
            return self.movement_speed
        return (self.cadence / 60.0) * self.step_length


#: Reference calibration (RicksClips measurements as initial targets,
#: not universal laws): step 0.25-0.33 H, cadence 70-90/min, head level.
CANONICAL_GAIT = GaitProfile()


@dataclass
class LocomotionMetrics:
    """The 8 required Phase A metrics, normalized units."""

    step_length: float  # heights, one step
    stride_length: float  # heights, full cycle (kept separate!)
    cadence: float  # steps/minute, measured
    head_vertical_displacement: float  # heights, peak-to-peak
    foot_sliding: float  # heights, planted-foot drift per stance
    stance_duration: float  # seconds, mean single-support time
    joint_angle_continuity: float  # max deg/frame jump, 0 = smooth
    root_movement: float  # heights travelled by the root
    left_right_symmetry: float  # 0..1, 1 = perfectly symmetric

    def as_dict(self) -> dict:
        return {
            "step_length": self.step_length,
            "stride_length": self.stride_length,
            "cadence": self.cadence,
            "head_vertical_displacement": self.head_vertical_displacement,
            "foot_sliding": self.foot_sliding,
            "stance_duration": self.stance_duration,
            "joint_angle_continuity": self.joint_angle_continuity,
            "root_movement": self.root_movement,
            "left_right_symmetry": self.left_right_symmetry,
        }


# ------------------------------------------------------------------
# Camera (Phase C; Subagent B implements, ATLAS integrates)
# ------------------------------------------------------------------

class CameraMode(Enum):
    STATIC_ANCHORED = "static_anchored"
    SCRIPTED_PAN = "scripted_pan"
    SCRIPTED_DOLLY = "scripted_dolly"
    SCRIPTED_TRACKING = "scripted_tracking"
    SCRIPTED_REVEAL = "scripted_reveal"
    SCRIPTED_SHAKE = "scripted_shake"


DEFAULT_CAMERA_MODE = CameraMode.STATIC_ANCHORED

#: Numerical tolerance for "constant within a static shot".
TRANSFORM_TOLERANCE = 1e-6


@dataclass(frozen=True)
class CameraDirective:
    """One camera decision. Every movement must be traceable to an
    explicit directive or planner decision via ``source``.

    ``anchor`` is "scene", a character id, or an object id — the
    framing anchor. It is NEVER an implicit head-follow: the default
    path must not track the head. For STATIC_ANCHORED, start and end
    transforms must be equal when both are given.
    """

    mode: CameraMode = DEFAULT_CAMERA_MODE
    anchor: str = "scene"
    source: str = ""  # directive id or planner decision id; required
    start_transform: tuple | None = None
    end_transform: tuple | None = None
    duration_s: float = 0.0

    def __post_init__(self):
        if not self.source:
            raise ValueError("CameraDirective requires a traceable source")
        if (self.mode is CameraMode.STATIC_ANCHORED
                and self.start_transform is not None
                and self.end_transform is not None
                and self.start_transform != self.end_transform):
            raise ValueError(
                "STATIC_ANCHORED requires equal start/end transforms")


@dataclass
class CameraValidation:
    """Full camera state for validation (Phase C/F)."""

    position: tuple
    orientation: tuple
    projection_matrix: tuple
    fov_deg: float
    crop_rect: tuple | None
    target_anchor: str
    start_transform: tuple
    end_transform: tuple

    def is_static(self, tol: float = TRANSFORM_TOLERANCE) -> bool:
        """True when start/end transforms agree within tolerance."""
        if len(self.start_transform) != len(self.end_transform):
            return False
        return all(abs(a - b) <= tol for a, b in
                   zip(self.start_transform, self.end_transform))


# ------------------------------------------------------------------
# Expression (Phase D; Subagent A implements)
# ------------------------------------------------------------------

#: Micro-animation permitted WITHIN a shot (Phase D). Major
#: expression changes align with cuts or narrative beats instead.
MICRO_ANIMATIONS = frozenset({
    "blink", "lipsync", "eye_movement", "eyebrow_motion",
    "breathing", "small_head_movement", "natural_reaction",
})


@dataclass(frozen=True)
class ExpressionTransition:
    """A semantic expression change. ``align`` is "cut", "beat", or
    "micro" (micro-animation only — never a major change)."""

    from_state: str
    to_state: str
    align: str = "cut"

    def __post_init__(self):
        if self.align not in ("cut", "beat", "micro"):
            raise ValueError(f"unknown expression alignment: {self.align}")


# ------------------------------------------------------------------
# Environment (Phase E; Subagent B implements)
# ------------------------------------------------------------------

#: Structured location-trait fields every location must provide
#: (directive SS8). Landmark selection reads THESE fields, never
#: keywords alone.
REQUIRED_LOCATION_TRAITS = (
    "identity",  # geographic or fictional identity
    "period",  # time period
    "architecture",  # architectural language
    "materials",  # surface materials
    "conditions",  # environmental conditions
    "landmarks",  # recognizable landmarks
    "foreground",  # foreground elements
    "midground",  # midground staging
    "background",  # background depth
    "lighting",  # lighting conditions
    "negative_constraints",  # what must NOT appear
)


# ------------------------------------------------------------------
# Measurement (Phase F; ATLAS audits)
# ------------------------------------------------------------------

#: Bounding-box kinds that must be measured separately. A head-size
#: report must state which kind it measured; mixing them (e.g. hair
#: or costume inside a "head" box) invalidates the measurement.
BBOX_KINDS = ("head", "hair", "full_character", "costume")
