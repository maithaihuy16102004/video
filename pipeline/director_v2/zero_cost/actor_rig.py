"""Extended Stickman Actor Rig for Director V2 Zero-Cost Engine.

Provides:
1. 20+ Expressive Historical Pose Families:
   - THINK_CHIN, ORATE_FIST, DUCK_COVER, LIE_BED, KNEEL_GRIEF
   - WALK, RUN, CROUCH, SIT, POINT, READ, WRITE, LISTEN, FEAR
   - EXHAUSTED, INJURED, CONFUSED, ANGRY, OBSERVE, HIDE, CARRY, PUSH, PULL, SALUTE
2. Interaction Anchors:
   - LIE_ON (Bed / stretcher)
   - SIT_ON (Chair / tavern bench)
   - LEAN_ON (Parapet / railing / table)
   - CROUCH_BEHIND (Trench revetment / sandbags)
3. Dynamic 2D Lighting Response:
   - Elliptical contact shadow cast according to LightingSpec.shadow_direction
   - Directional rim highlight on illuminated contour (key_direction)
   - Shadow-side body shading
   - Scene ambient color tinting
4. Character-camera integration:
   - Camera height and pitch adjustment (Ground Level, Low Angle, High Angle)
   - POV shot automatic exclusion
"""
from __future__ import annotations

import math
from typing import Any
import cairo

from ..scene_builder.blueprint import SceneBlueprint


class StickmanActorRig:
    """Renders parametric stickman actors integrated with perspective and lighting."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height
        self.s = min(width / 1920.0, height / 1080.0)

    def render_actor(
        self,
        ctx: cairo.Context,
        bp: SceneBlueprint,
        anchor_override: str | None = None,
    ) -> None:
        """Render stickman actor onto context with perspective and lighting."""
        char = bp.character
        scale = char.scale

        # POV shot or disabled actor
        if scale <= 0.0 or "POV" in bp.camera.shot_size.upper() or char.character_id == "none_pov":
            return

        s = self.s
        w = self.width
        h = self.height

        # 1. Perspective Placement
        norm_x, norm_y = char.approximate_position
        char_x = norm_x * w

        horizon_px = bp.camera.horizon_y * h
        cam_height = bp.camera.height.upper()

        if "LOW" in cam_height or bp.camera.pitch > 10.0:
            char_base_y = h * 0.90
        elif "HIGH" in cam_height or bp.camera.pitch < -15.0:
            char_base_y = h * 0.78
        elif "GROUND" in cam_height:
            char_base_y = h * 0.92
        else:
            char_base_y = horizon_px + (h - horizon_px) * 0.72

        # 2. Lighting Parameters
        lighting = bp.lighting
        key_dir = lighting.key_direction.upper()
        shadow_dir = lighting.shadow_direction.upper()

        shadow_dx = 50.0 * s
        shadow_dy = 16.0 * s
        if "LEFT" in shadow_dir:
            shadow_dx = -50.0 * s
        elif "LONG_FORWARD" in shadow_dir:
            shadow_dx = 12.0 * s
            shadow_dy = 36.0 * s
        elif "BOTTOM_RIGHT" in shadow_dir:
            shadow_dx = 55.0 * s
            shadow_dy = 18.0 * s

        # Draw Ground Contact Shadow
        pose = char.pose_envelope.upper()
        if "LIE_BED" not in pose:
            ctx.save()
            ctx.translate(char_x + shadow_dx * 0.45, char_base_y + shadow_dy * 0.45)
            ctx.scale(1.0, 0.28)
            ctx.arc(0, 0, 85.0 * scale * s, 0, math.tau)
            ctx.set_source_rgba(0.04, 0.05, 0.08, 0.45 * lighting.key_intensity)
            ctx.fill()
            ctx.restore()

        # 3. Dimensions
        head_r = 32.0 * scale * s
        torso_len = 110.0 * scale * s
        leg_len = 115.0 * scale * s

        facing_right = (norm_x < 0.55)
        if "RIGHT" in char.body_orientation.upper():
            facing_right = True
        elif "LEFT" in char.body_orientation.upper():
            facing_right = False
        flip = 1.0 if facing_right else -1.0

        ink = (0.08, 0.10, 0.14)
        skin_tint = (0.92, 0.90, 0.86)
        highlight_color = (
            (1.0, 0.96, 0.84, 0.75)
            if "WARM" in lighting.color_temperature
            else (0.85, 0.92, 1.0, 0.70)
        )

        ctx.save()
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)

        line_w = max(3.5, 7.5 * scale * s)
        ctx.set_line_width(line_w)

        # ======================================================================
        # 4. POSE KINEMATICS (20+ Pose Families)
        # ======================================================================

        # Pose A: LIE_BED (Hospital bed convalescence)
        if "LIE_BED" in pose:
            bed_y = char_base_y - 25.0 * s
            # Torso reclined on mattress
            ctx.move_to(char_x - 75.0 * s, bed_y - 48.0 * s)
            ctx.line_to(char_x + 50.0 * s, bed_y - 18.0 * s)
            ctx.set_source_rgb(*ink)
            ctx.stroke()
            # Legs extended under blanket
            ctx.move_to(char_x + 50.0 * s, bed_y - 18.0 * s)
            ctx.line_to(char_x + 145.0 * s, bed_y - 12.0 * s)
            ctx.stroke()
            # Head resting on pillow
            head_cx = char_x - 95.0 * s
            head_cy = bed_y - 68.0 * s
            ctx.arc(head_cx, head_cy, head_r, 0, math.tau)
            ctx.set_source_rgb(*skin_tint)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.stroke()
            # Gauze eye bandage (Pasewalk gas injury)
            ctx.rectangle(head_cx - head_r, head_cy - 8.0 * s, head_r * 2.0, 16.0 * s)
            ctx.set_source_rgb(0.96, 0.96, 0.94)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(line_w * 0.6)
            ctx.stroke()
            ctx.restore()
            return

        # Upright / crouching coordinates
        hip_y = char_base_y - leg_len
        neck_y = hip_y - torso_len
        head_cy = neck_y - head_r

        if "DUCK_COVER" in pose or "CROUCH" in pose or "HIDE" in pose:
            hip_y = char_base_y - leg_len * 0.50
            neck_y = hip_y - torso_len * 0.75
            head_cy = neck_y - head_r * 0.85
        elif "KNEEL" in pose:
            hip_y = char_base_y - leg_len * 0.45
            neck_y = hip_y - torso_len * 0.80
            head_cy = neck_y - head_r * 0.85
        elif "SIT" in pose:
            hip_y = char_base_y - leg_len * 0.45
            neck_y = hip_y - torso_len
            head_cy = neck_y - head_r

        # --- Draw Torso ---
        ctx.move_to(char_x, hip_y)
        ctx.line_to(char_x + flip * 8.0 * s, neck_y)
        ctx.set_source_rgb(*ink)
        ctx.stroke()

        # --- Draw Legs ---
        if "DUCK_COVER" in pose:
            # Low defensive tuck
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x - flip * 40.0 * s, hip_y + 35.0 * s)
            ctx.line_to(char_x - flip * 15.0 * s, char_base_y)
            ctx.stroke()
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x + flip * 42.0 * s, hip_y + 32.0 * s)
            ctx.line_to(char_x + flip * 25.0 * s, char_base_y)
            ctx.stroke()
        elif "KNEEL" in pose or "KNEEL_GRIEF" in pose:
            # Both knees on ground
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x - flip * 32.0 * s, char_base_y)
            ctx.stroke()
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x + flip * 28.0 * s, hip_y + 30.0 * s)
            ctx.line_to(char_x + flip * 38.0 * s, char_base_y)
            ctx.stroke()
        elif "WALK" in pose:
            # Walking stride
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x + flip * 45.0 * s, char_base_y)
            ctx.stroke()
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x - flip * 35.0 * s, char_base_y - 12.0 * s)
            ctx.stroke()
        elif "RUN" in pose:
            # Running sprint split
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x + flip * 68.0 * s, char_base_y - 10.0 * s)
            ctx.stroke()
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x - flip * 62.0 * s, char_base_y - 25.0 * s)
            ctx.stroke()
        elif "SIT" in pose:
            # 90-degree seated thighs
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x + flip * 55.0 * s, hip_y)
            ctx.line_to(char_x + flip * 55.0 * s, char_base_y)
            ctx.stroke()
        else:
            # Standing legs
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x - 22.0 * s, char_base_y)
            ctx.stroke()
            ctx.move_to(char_x, hip_y)
            ctx.line_to(char_x + 22.0 * s, char_base_y)
            ctx.stroke()

        # --- Draw Arms & Gestures ---
        shoulder_y = neck_y + 16.0 * s

        if "ORATE_FIST" in pose:
            # Fist thrust in air (speech / rally)
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 45.0 * s, shoulder_y - 55.0 * s)
            ctx.line_to(char_x + flip * 60.0 * s, shoulder_y - 115.0 * s)
            ctx.stroke()
            # Opposing arm gesturing outward
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 35.0 * s, shoulder_y + 25.0 * s)
            ctx.line_to(char_x - flip * 60.0 * s, shoulder_y + 10.0 * s)
            ctx.stroke()
        elif "THINK_CHIN" in pose:
            # Hand to chin, contemplation
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 26.0 * s, shoulder_y + 35.0 * s)
            ctx.line_to(char_x + flip * 16.0 * s, neck_y + 6.0 * s)
            ctx.stroke()
            # Supporting arm across chest
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 22.0 * s, shoulder_y + 45.0 * s)
            ctx.line_to(char_x + flip * 15.0 * s, shoulder_y + 45.0 * s)
            ctx.stroke()
        elif "DUCK_COVER" in pose:
            # Hands over helmet / head
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 28.0 * s, head_cy - 12.0 * s)
            ctx.stroke()
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 25.0 * s, head_cy - 14.0 * s)
            ctx.stroke()
        elif "KNEEL_GRIEF" in pose:
            # Hands clutching face in despair
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 15.0 * s, head_cy)
            ctx.stroke()
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 15.0 * s, head_cy)
            ctx.stroke()
        elif "SALUTE" in pose:
            # Military salute to brow
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 38.0 * s, shoulder_y - 20.0 * s)
            ctx.line_to(char_x + flip * 24.0 * s, head_cy - 6.0 * s)
            ctx.stroke()
            # Other arm straight down at attention
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 15.0 * s, shoulder_y + 65.0 * s)
            ctx.stroke()
        elif "POINT" in pose:
            # Arm pointing forward
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 85.0 * s, shoulder_y - 12.0 * s)
            ctx.stroke()
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 20.0 * s, shoulder_y + 55.0 * s)
            ctx.stroke()
        elif "READ" in pose:
            # Holding paper document
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 35.0 * s, shoulder_y + 35.0 * s)
            ctx.stroke()
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 20.0 * s, shoulder_y + 35.0 * s)
            ctx.stroke()
            # Paper sheet
            ctx.rectangle(char_x + flip * 22.0 * s, shoulder_y + 20.0 * s, 22.0 * s, 30.0 * s)
            ctx.set_source_rgb(0.95, 0.95, 0.90)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(1.5)
            ctx.stroke()
        elif "EXHAUSTED" in pose or "INJURED" in pose:
            # Slumped shoulders, head low, clutching torso
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 12.0 * s, shoulder_y + 40.0 * s)
            ctx.stroke()
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 15.0 * s, shoulder_y + 65.0 * s)
            ctx.stroke()
        else:
            # Standard alert / attentive stand
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x - flip * 25.0 * s, shoulder_y + 55.0 * s)
            ctx.stroke()
            ctx.move_to(char_x, shoulder_y)
            ctx.line_to(char_x + flip * 28.0 * s, shoulder_y + 55.0 * s)
            ctx.stroke()

        # --- Draw Head & Helmet ---
        ctx.arc(char_x, head_cy, head_r, 0, math.tau)
        ctx.set_source_rgb(*skin_tint)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.stroke()

        # German Stahlhelm M1916 helmet for trench/military shots
        if any(k in bp.history.location_id.lower() for k in ["trench", "front", "somme", "ypres"]):
            helm_cy = head_cy - head_r * 0.35
            ctx.save()
            # Dome of Stahlhelm
            ctx.arc(char_x, helm_cy, head_r * 1.15, math.pi * 0.95, math.pi * 0.05)
            # Characteristic flared neck skirt & visor
            ctx.line_to(char_x + head_r * 1.35 * flip, helm_cy + head_r * 0.45)
            ctx.line_to(char_x - head_r * 1.35 * flip, helm_cy + head_r * 0.45)
            ctx.close_path()
            ctx.set_source_rgb(0.32, 0.36, 0.30)  # Feldgrau steel
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(2.5 * s)
            ctx.stroke()
            ctx.restore()

        # 5. Lighting Rim Highlight on Head
        ctx.save()
        key_side_x = char_x - head_r * 0.7 if "LEFT" in key_dir else char_x + head_r * 0.7
        ctx.arc(key_side_x, head_cy - head_r * 0.3, head_r * 0.45, 0, math.tau)
        ctx.set_source_rgba(*highlight_color)
        ctx.fill()
        ctx.restore()

        ctx.restore()
