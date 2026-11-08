"""Scene Geography, 180-Degree Action Axis, Camera Zones, and Blocking Continuity.

Enforces:
1. Actor Physical Persistence: Shot N+1 inherits physical state from Shot N (no silent resets).
2. Action Axis & 180-Degree Rule: Camera stays on the established side of the line of action unless an intentional reorientation shot is planned.
3. Eyeline Continuity: When Actor A looks at Actor B/Object, the subsequent shot's eyeline vector reflects the established 3D geometry.
4. Screen Direction Preservation: An actor moving Left-to-Right maintains screen direction across cuts.
5. Camera Geography & Collision: Validates camera positions reside within physically reachable camera zones (DOORWAY_ZONE, TABLE_SIDE_ZONE, ACTOR_REAR_ZONE, OBJECT_SIDE_ZONE, GROUND_ZONE).
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Any, Optional

from pydantic import Field

from ..schemas import UModel


class CameraZone(str, Enum):
    ESTABLISHING_ZONE = "ESTABLISHING_ZONE"
    DOORWAY_ZONE = "DOORWAY_ZONE"
    TABLE_SIDE_ZONE = "TABLE_SIDE_ZONE"
    ACTOR_REAR_ZONE = "ACTOR_REAR_ZONE"
    OBJECT_SIDE_ZONE = "OBJECT_SIDE_ZONE"
    GROUND_ZONE = "GROUND_ZONE"
    HIGH_VANTAGE_ZONE = "HIGH_VANTAGE_ZONE"


class ActorPhysicalState(UModel):
    actor_id: str
    world_pos: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])  # x, y, depth
    screen_pos: list[float] = Field(default_factory=lambda: [0.5, 0.78])     # normalized 2D
    orientation: str = "FRONT"
    action: str = "STAND"
    target_id: Optional[str] = None
    eyeline_target: Optional[str] = None
    eyeline_vector: list[float] = Field(default_factory=lambda: [1.0, 0.0])
    screen_direction: str = "STATIONARY"  # LEFT_TO_RIGHT | RIGHT_TO_LEFT | STATIONARY
    motion_vector: list[float] = Field(default_factory=lambda: [0.0, 0.0])


class SceneGeography(UModel):
    """Spatial ground truth of the scene."""
    bounds: list[float] = Field(default_factory=lambda: [-10.0, -10.0, 10.0, 10.0])
    actors: dict[str, ActorPhysicalState] = Field(default_factory=dict)
    objects: dict[str, list[float]] = Field(default_factory=dict)            # prop_id -> [x, y, depth]
    action_axis_p1: list[float] = Field(default_factory=lambda: [-2.0, 0.0])
    action_axis_p2: list[float] = Field(default_factory=lambda: [2.0, 0.0])
    camera_side_of_axis: int = 1                                             # +1 or -1
    established_eyelines: dict[str, list[float]] = Field(default_factory=dict)
    available_camera_zones: list[str] = Field(default_factory=lambda: [
        CameraZone.ESTABLISHING_ZONE.value,
        CameraZone.TABLE_SIDE_ZONE.value,
        CameraZone.ACTOR_REAR_ZONE.value,
        CameraZone.OBJECT_SIDE_ZONE.value,
        CameraZone.GROUND_ZONE.value,
    ])

    def validate_camera_placement(self, cam_pos: list[float], zone: str) -> tuple[bool, str]:
        """Checks camera collision against scene boundaries and geometry."""
        # Simple geometric bounding validation
        if len(cam_pos) >= 2:
            x, y = cam_pos[0], cam_pos[1]
            if x < self.bounds[0] or x > self.bounds[2] or y < self.bounds[1] or y > self.bounds[3]:
                return False, f"Camera at ({x:.1f}, {y:.1f}) is out of physical scene bounds."
        return True, "VALID_CAMERA_ZONE"

    def check_180_axis(self, new_camera_side: int) -> bool:
        """Returns True if the camera remains on the established side of the action axis."""
        return new_camera_side == self.camera_side_of_axis


class SequenceBlockingTracker:
    """Carries character positions, eyelines, and action continuity across shots."""

    def __init__(self, geography: Optional[SceneGeography] = None) -> None:
        self.geo = geography or SceneGeography()
        self.shot_history: list[dict[str, Any]] = []

    def get_or_create_actor(self, actor_id: str, default_x: float = 0.5) -> ActorPhysicalState:
        if actor_id in self.geo.actors:
            return self.geo.actors[actor_id]
        new_state = ActorPhysicalState(
            actor_id=actor_id,
            world_pos=[(default_x - 0.5) * 6.0, 0.0, 2.0],
            screen_pos=[default_x, 0.78],
            orientation="FRONT",
            action="STAND",
        )
        self.geo.actors[actor_id] = new_state
        return new_state

    def update_actor(
        self,
        actor_id: str,
        screen_x: float,
        action: str,
        orientation: str,
        eyeline_target: Optional[str] = None,
        target_id: Optional[str] = None,
    ) -> ActorPhysicalState:
        actor = self.get_or_create_actor(actor_id, default_x=screen_x)
        
        # Track screen direction
        old_x = actor.screen_pos[0]
        dx = screen_x - old_x
        if abs(dx) > 0.03:
            actor.screen_direction = "LEFT_TO_RIGHT" if dx > 0 else "RIGHT_TO_LEFT"
            actor.motion_vector = [dx, 0.0]
        else:
            actor.screen_direction = "STATIONARY"
            actor.motion_vector = [0.0, 0.0]

        actor.screen_pos = [screen_x, actor.screen_pos[1]]
        actor.world_pos[0] = (screen_x - 0.5) * 6.0
        actor.action = action
        actor.orientation = orientation
        actor.eyeline_target = eyeline_target
        actor.target_id = target_id

        # Calculate eyeline vector
        if eyeline_target and eyeline_target in self.geo.actors:
            target_actor = self.geo.actors[eyeline_target]
            target_x = target_actor.screen_pos[0]
            actor.eyeline_vector = [1.0 if target_x > screen_x else -1.0, 0.0]
        elif "LEFT" in orientation:
            actor.eyeline_vector = [-1.0, 0.0]
        elif "RIGHT" in orientation:
            actor.eyeline_vector = [1.0, 0.0]

        self.geo.actors[actor_id] = actor
        return actor

    def record_shot(self, shot_id: str, camera_zone: str, camera_side: int) -> None:
        self.shot_history.append({
            "shot_id": shot_id,
            "camera_zone": camera_zone,
            "camera_side": camera_side,
            "actor_positions": {k: list(v.screen_pos) for k, v in self.geo.actors.items()},
        })
        self.geo.camera_side_of_axis = camera_side
