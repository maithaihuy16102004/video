"""Comprehensive Semantic Acting Vocabulary & Performance Kinematics.

Expands stickman acting beyond the repetitive OBSERVE / POINT / REACH / STAND trap.
Supports 40+ generic semantic actions, multi-stage performance phrases, and expressive
body kinematics (head angle, spine curve, shoulder slope, weight distribution, hand targets).
"""
from __future__ import annotations

import math
from typing import Any, Optional


SEMANTIC_ACTIONS = [
    "APPROACH", "RETREAT", "LEAN", "BRACE", "CROUCH", "KNEEL", "SIT", "RISE",
    "TURN_HEAD", "TURN_BODY", "GLANCE", "AVOID_GAZE", "FREEZE", "FLINCH",
    "GRAB", "PULL", "PUSH", "OPEN", "CLOSE", "HAND_OVER", "TAKE",
    "INSPECT", "WRITE", "READ", "LIFT", "DROP", "CARRY", "RUN", "WALK",
    "STEP_ASIDE", "BLOCK", "INTERRUPT", "WHISPER", "ARGUE", "WAIT",
    "LISTEN", "REACT", "CELEBRATE", "EXHALE", "COLLAPSE", "POINT", "REACH",
    "STAND", "SPEAK", "OBSERVE"
]
ACTING_VOCABULARY = SEMANTIC_ACTIONS


class PerformanceKinematics:
    """Calculates posture, spine curvature, and limb placement for semantic actions."""

    @staticmethod
    def get_action_pose(
        action: str,
        performance_intent: str = "",
        spine_bias: float = 0.0,
        head_angle_bias: float = 0.0,
        orientation: str = "FRONT",
    ) -> dict[str, Any]:
        act = action.upper().strip()
        intent = performance_intent.lower()

        # Default neutral posture
        hip_drop = 0.0       # pixels dropped from standing ground
        stride_scale = 1.0   # foot separation multiplier
        spine_tilt = spine_bias  # -1.0 leaning back, +1.0 leaning forward
        head_tilt = head_angle_bias  # degrees
        shoulder_tilt = 0.0

        # Arm default offsets (relative to shoulder)
        # [l_elbow_x, l_elbow_y, l_hand_x, l_hand_y, r_elbow_x, r_elbow_y, r_hand_x, r_hand_y]
        l_e = [-28.0, 55.0]
        l_h = [-35.0, 110.0]
        r_e = [28.0, 55.0]
        r_h = [35.0, 110.0]

        # 1. Stance & Body Weight Actions
        if act == "CROUCH":
            hip_drop = 45.0
            stride_scale = 1.4
            spine_tilt = 0.35
            head_tilt = 10.0
            l_h = [-20.0, 60.0]
            r_h = [20.0, 60.0]
        elif act == "KNEEL":
            hip_drop = 65.0
            stride_scale = 0.8
            spine_tilt = 0.15
            l_h = [-15.0, 50.0]
            r_h = [15.0, 50.0]
        elif act == "SIT":
            hip_drop = 50.0
            stride_scale = 0.9
            spine_tilt = -0.1
            l_e = [-25.0, 40.0]
            l_h = [-15.0, 55.0]
            r_e = [25.0, 40.0]
            r_h = [15.0, 55.0]
        elif act in ("BRACE", "RETREAT"):
            stride_scale = 1.6
            spine_tilt = -0.35
            head_tilt = -8.0
            l_e = [-35.0, 30.0]
            l_h = [-50.0, 40.0]
            r_e = [35.0, 30.0]
            r_h = [50.0, 40.0]
        elif act in ("LEAN", "APPROACH"):
            spine_tilt = 0.35
            head_tilt = 12.0
            stride_scale = 1.2
        elif act == "COLLAPSE":
            hip_drop = 75.0
            spine_tilt = 0.65
            head_tilt = 35.0
            l_h = [-20.0, 80.0]
            r_h = [20.0, 80.0]

        # 2. Dramatic Expressive Actions
        elif act in ("FREEZE", "FLINCH"):
            stride_scale = 0.7
            spine_tilt = -0.25
            head_tilt = -15.0
            l_e = [-20.0, 25.0]
            l_h = [-10.0, 10.0]  # Hands up guarding chest
            r_e = [20.0, 25.0]
            r_h = [10.0, 10.0]
        elif act in ("GRAB", "PULL"):
            spine_tilt = -0.30
            stride_scale = 1.5
            r_e = [45.0, 30.0]
            r_h = [70.0, 45.0]
            l_e = [25.0, 35.0]
            l_h = [55.0, 50.0]
        elif act in ("PUSH", "BLOCK"):
            spine_tilt = 0.40
            stride_scale = 1.5
            r_e = [40.0, 15.0]
            r_h = [85.0, 10.0]  # Hands pushed out forward
            l_e = [25.0, 20.0]
            l_h = [75.0, 15.0]
        elif act in ("HAND_OVER", "TAKE", "OPEN"):
            spine_tilt = 0.15
            r_e = [35.0, 40.0]
            r_h = [65.0, 45.0]  # Outstretched offering/receiving hand
            l_e = [-25.0, 50.0]
            l_h = [-30.0, 95.0]
        elif act in ("READ", "INSPECT"):
            spine_tilt = 0.20
            head_tilt = 22.0  # Head angled down looking at item
            r_e = [22.0, 40.0]
            r_h = [18.0, 25.0]  # Both hands holding book/sheet up
            l_e = [-22.0, 40.0]
            l_h = [-18.0, 25.0]
        elif act == "WHISPER":
            spine_tilt = 0.30
            head_tilt = 12.0
            r_e = [25.0, 20.0]
            r_h = [15.0, -10.0]  # Cupping mouth
            l_e = [-25.0, 55.0]
            l_h = [-35.0, 105.0]
        elif act == "CELEBRATE":
            spine_tilt = -0.15
            head_tilt = -20.0  # Head looking up
            r_e = [45.0, -20.0]
            r_h = [65.0, -75.0]  # Both arms raised in V-shape
            l_e = [-45.0, -20.0]
            l_h = [-65.0, -75.0]
        elif act in ("WAIT", "LISTEN"):
            head_tilt = 14.0  # Tilted listening head
            l_e = [-20.0, 60.0]
            l_h = [5.0, 85.0]   # Hands clasped
            r_e = [20.0, 60.0]
            r_h = [-5.0, 85.0]
        elif act == "ARGUE":
            spine_tilt = 0.25
            r_e = [45.0, 30.0]
            r_h = [75.0, 15.0]  # Emphatic point/chop
            l_e = [-35.0, 40.0]
            l_h = [-45.0, 35.0]
        elif act == "EXHALE":
            spine_tilt = 0.15
            head_tilt = 15.0
            shoulder_tilt = 0.15  # Drooped shoulders
            l_h = [-30.0, 115.0]
            r_h = [30.0, 115.0]

        # Contextual Performance Intent Tweaks
        if "hesitate" in intent or "reluctan" in intent:
            r_h[0] *= 0.65  # Hand pulled back hesitantly
            spine_tilt -= 0.15
        elif "assert" in intent or "control" in intent or "firm" in intent:
            spine_tilt += 0.20
            stride_scale *= 1.2
        elif "nervous" in intent or "fear" in intent:
            head_tilt -= 8.0
            stride_scale *= 0.85

        return {
            "hip_drop": hip_drop,
            "stride_scale": stride_scale,
            "spine_tilt": spine_tilt,
            "head_tilt": head_tilt,
            "shoulder_tilt": shoulder_tilt,
            "l_elbow": l_e,
            "l_hand": l_h,
            "r_elbow": r_e,
            "r_hand": r_h,
        }
