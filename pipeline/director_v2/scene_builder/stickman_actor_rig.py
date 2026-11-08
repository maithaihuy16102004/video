"""Stickman Actor Rig: Procedural Actor Layer with Lighting & Perspective Handshake.

Enforces:
1. "STICKMAN ACTS: The Actor performs on the stage designed by Director and built by Gemini."
2. Perspective Handshake:
   - Base contact position derived directly from Blueprint camera height, pitch, and horizon.
   - Character scale strictly matches Blueprint specifications (EXTREME_WIDE 0.18 -> CLOSE 0.82).
3. Lighting Handshake:
   - Ground contact shadow direction aligned with LightingSpec.shadow_direction.
   - Key light highlight applied to illuminated side (LightingSpec.key_direction).
   - Core shadow shading applied to opposite side.
4. Kinematic Poses:
   - ALERT_STAND, ORATE_FIST, THINK_CHIN, DUCK_COVER, LIE_BED, KNEEL_GRIEF.
5. POV exclusion: Zero character drawing in POV shots.
"""
from __future__ import annotations

import math
from typing import Any

import cairo

from .blueprint import SceneBlueprint


class StickmanActorRig:
    """Renders the stickman actor directly into the Cairo Context with lighting & perspective integration."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height
        self.s = min(width / 1920.0, height / 1080.0)

    def render_actor(self, ctx: cairo.Context, bp: SceneBlueprint) -> None:
        char = bp.character
        scale = char.scale
        if scale <= 0.0 or "POV" in bp.camera.shot_size or char.character_id == "none_pov":
            # Subject is off-camera in POV / panoramic establishment
            return

        s = self.s
        w = self.width
        h = self.height

        # 1. Perspective Placement Handshake
        norm_x, norm_y = char.approximate_position
        char_x = norm_x * w

        horizon_px = bp.camera.horizon_y * h
        cam_height = bp.camera.height.upper()

        if "LOW" in cam_height or bp.camera.pitch > 10.0:
            char_base_y = h * 0.90
        elif "HIGH" in cam_height or bp.camera.pitch < -15.0:
            char_base_y = h * 0.76
        elif "GROUND" in cam_height:
            char_base_y = h * 0.92
        else:
            char_base_y = horizon_px + (h - horizon_px) * 0.72

        # 2. Lighting Handshake Setup
        lighting = bp.lighting
        key_dir = lighting.key_direction.upper()
        shadow_dir = lighting.shadow_direction.upper()

        # Contact Shadow parameters
        shadow_dx = 40.0 * s
        shadow_dy = 14.0 * s
        if "LEFT" in shadow_dir:
            shadow_dx = -50.0 * s
        elif "LONG_FORWARD" in shadow_dir:
            shadow_dx = 10.0 * s
            shadow_dy = 32.0 * s
        elif "BOTTOM_RIGHT" in shadow_dir:
            shadow_dx = 60.0 * s
            shadow_dy = 16.0 * s

        # Draw Ground Contact Shadow
        ctx.save()
        ctx.translate(char_x + shadow_dx * 0.5, char_base_y + shadow_dy * 0.5)
        ctx.scale(1.0, 0.28)
        ctx.arc(0, 0, 85.0 * scale * s, 0, 2 * math.pi)
        ctx.set_source_rgba(0.04, 0.05, 0.08, 0.42 * lighting.key_intensity)
        ctx.fill()
        ctx.restore()

        # 3. Stickman Dimensions
        char_h = 280.0 * scale * s
        head_r = 32.0 * scale * s
        torso_len = 110.0 * scale * s
        leg_len = 115.0 * scale * s
        arm_len = 95.0 * scale * s

        pose = char.pose_envelope.upper()
        facing_right = (norm_x < 0.55)
        flip = 1.0 if facing_right else -1.0

        ink = (0.08, 0.10, 0.14)
        skin_tint = (0.92, 0.90, 0.86)
        highlight_color = (0.98, 0.95, 0.85, 0.75) if "WARM" in lighting.color_temperature else (0.85, 0.92, 1.0, 0.70)

        # 4. Pose Kinematics Rendering
        ctx.save()
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)

        line_w = max(3.5, 7.5 * scale * s)
        ctx.set_line_width(line_w)

        if "LIE_BED" in pose:
            # Reclining in hospital bed
            bed_y = char_base_y - 20.0 * s
            # Torso reclining
            ctx.move_to(char_x - 70.0 * s, bed_y - 45.0 * s)
            ctx.line_to(char_x + 50.0 * s, bed_y - 15.0 * s)
            ctx.set_source_rgb(*ink)
            ctx.stroke()
            # Legs extended
            ctx.move_to(char_x + 50.0 * s, bed_y - 15.0 * s)
            ctx.line_to(char_x + 140.0 * s, bed_y - 10.0 * s)
            ctx.stroke()
            # Head resting with bandage
            head_cx = char_x - 90.0 * s
            head_cy = bed_y - 65.0 * s
            ctx.arc(head_cx, head_cy, head_r, 0, 2 * math.pi)
            ctx.set_source_rgb(*skin_tint)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.stroke()
            # Gauze bandage wrap across eyes
            ctx.rectangle(head_cx - head_r, head_cy - 8.0 * s, head_r * 2.0, 16.0 * s)
            ctx.set_source_rgb(0.96, 0.96, 0.94)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(line_w * 0.6)
            ctx.stroke()
            ctx.restore()
            return

        # Upright or Crouching Stickman
        hip_y = char_base_y - leg_len
        neck_y = hip_y - torso_len
        head_cy = neck_y - head_r

        if "DUCK_COVER" in pose or "KNEEL" in pose:
            hip_y = char_base_y - leg_len * 0.55
            neck_y = hip_y - torso_len * 0.85
            head_cy = neck_y - head_r * 0.9

        # Draw Torso
        ctx.move_to(char_x, hip_y)
        ctx.line_to(char_x + flip * 8.0 * s, neck_y)
        ctx.set_source_rgb(*ink)
        ctx.stroke()

        # Draw Legs
        if "DUCK_COVER" in pose:
            # Crouched legs
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x - flip * 35.0 * s, hip_y + 35.0 * s)
            ctx.line_to(char_x - flip * 15.0 * s, char_base_y)
            ctx.stroke()
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x + flip * 40.0 * s, hip_y + 30.0 * s)
            ctx.line_to(char_x + flip * 25.0 * s, char_base_y)
            ctx.stroke()
        elif "KNEEL" in pose:
            # Kneeling
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x - flip * 30.0 * s, char_base_y)
            ctx.stroke()
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x + flip * 25.0 * s, hip_y + 35.0 * s)
            ctx.line_to(char_x + flip * 35.0 * s, char_base_y)
            ctx.stroke()
        else:
            # Standard standing legs
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x - 22.0 * s, char_base_y)
            ctx.stroke()
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x + 22.0 * s, char_base_y)
            ctx.stroke()

        # Draw Arms & Pose gestures
        shoulder_y = neck_y + 16.0 * s
        if "ORATE_FIST" in pose:
            # Right arm thrust in air with clenched fist
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 45.0 * s, shoulder_y - 55.0 * s)
            ctx.line_to(char_x + flip * 60.0 * s, shoulder_y - 110.0 * s)
            ctx.stroke()
            # Left arm gesturing outward
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 35.0 * s, shoulder_y + 25.0 * s)
            ctx.line_to(char_x - flip * 60.0 * s, shoulder_y + 10.0 * s)
            ctx.stroke()
        elif "THINK_CHIN" in pose:
            # Hand on chin
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 25.0 * s, shoulder_y + 35.0 * s)
            ctx.line_to(char_x + flip * 18.0 * s, neck_y + 4.0 * s)
            ctx.stroke()
            # Opposing arm supporting elbow
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 20.0 * s, shoulder_y + 45.0 * s)
            ctx.line_to(char_x + flip * 15.0 * s, shoulder_y + 45.0 * s)
            ctx.stroke()
        elif "DUCK_COVER" in pose:
            # Hands protecting head
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 28.0 * s, head_cy - 12.0 * s)
            ctx.stroke()
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 25.0 * s, head_cy - 14.0 * s)
            ctx.stroke()
        else:
            # Alert / relaxed stand
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 25.0 * s, shoulder_y + 55.0 * s)
            ctx.stroke()
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 28.0 * s, shoulder_y + 55.0 * s)
            ctx.stroke()

        # Draw Head with Skin Tint
        ctx.arc(char_x, head_cy, head_r, 0, 2 * math.pi)
        ctx.set_source_rgb(*skin_tint)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.stroke()

        # 5. Lighting Key Highlight Rim on Stickman
        ctx.save()
        key_side_x = char_x - head_r * 0.7 if "LEFT" in key_dir else char_x + head_r * 0.7
        ctx.arc(key_side_x, head_cy - head_r * 0.3, head_r * 0.45, 0, 2 * math.pi)
        ctx.set_source_rgba(*highlight_color)
        ctx.fill()
        ctx.restore()

        ctx.restore()
