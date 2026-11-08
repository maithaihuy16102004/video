"""Generic Illustrated Stickman Character Renderer.

Implements the PROJECT-WIDE character art direction:
- Large illustrated head with recognizable hair silhouette (HairStyleDNA).
- Simple expressive face (FaceDNA) driven by Emotion & Eyeline.
- Simple clothing mass (CostumeDNA) with strong ink outlines and authentic palettes.
- Thin expressive stick arms and legs with organic joints and simple hands.
- Highly readable silhouette from wide to close-up shots.
- Data-driven recognition: Same renderer, different CharacterDNA & ResolvedCharacter.
- Supports detail levels: HERO, SUPPORT, BACKGROUND.
- Supports orientations: FRONT, BACK, PROFILE_L/R, 3/4_L/R, 3/4_BACK_L/R.
"""
from __future__ import annotations

import math
from typing import Any, Optional
import cairo

from ..schemas import (
    ActorBlock,
    CharacterDNA,
    CostumeDNA,
    FaceDNA,
    HairStyleDNA,
    ResolvedCharacter,
)
from .acting_vocabulary import PerformanceKinematics


def hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.lstrip("#")
    if len(h) == 6:
        return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)
    elif len(h) == 3:
        return (int(h[0]*2, 16) / 255.0, int(h[1]*2, 16) / 255.0, int(h[2]*2, 16) / 255.0)
    return (0.2, 0.2, 0.2)


class IllustratedStickmanRenderer:
    """Master renderer for illustrated stickmen characters."""

    def __init__(self, ink_color: tuple[float, float, float] = (0.08, 0.08, 0.10)) -> None:
        self.ink = ink_color

    def render_character(
        self,
        ctx: cairo.Context,
        char: ResolvedCharacter,
        actor: ActorBlock,
        screen_x: float,
        ground_y: float,
        scale: float = 1.0,
        lighting_dx: float = 1.0,
    ) -> None:
        """Renders one complete illustrated stickman onto the cairo context."""
        ctx.save()

        # Orientation setup
        orient = actor.orientation.upper()
        is_back = "BACK" in orient
        is_profile = "PROFILE" in orient
        is_three_quarter = "THREE_QUARTER" in orient
        flip_x = -1.0 if ("LEFT" in orient or (is_profile and "LEFT" in orient)) else 1.0

        # Detail level scaling
        is_hero = actor.detail_level == "HERO"
        is_bg = actor.detail_level == "BACKGROUND"

        # Scaling calculations
        s = scale * (char.body.height or 1.0)
        head_s = s * (char.body.head_scale or 1.0) * 1.25  # Large illustrated head

        # Kinematic root and anchors with Performance Kinematics
        pose = PerformanceKinematics.get_action_pose(
            action=actor.action,
            performance_intent=getattr(actor, "performance_intent", ""),
            spine_bias=getattr(actor, "spine_curve", 0.0),
            head_angle_bias=getattr(actor, "head_angle_deg", 0.0),
        )

        hip_drop = pose.get("hip_drop", 0.0) * s
        hip_y = ground_y - (120.0 - hip_drop) * s
        shoulder_y = ground_y - (250.0 - hip_drop) * s
        neck_y = shoulder_y - 25.0 * s

        spine_shift_x = pose.get("spine_tilt", 0.0) * 28.0 * s * flip_x
        shoulder_x = screen_x + spine_shift_x * 0.7
        neck_x = screen_x + spine_shift_x
        head_center_x = neck_x
        head_center_y = neck_y - 55.0 * head_s

        # Ground contact shadow
        self._render_contact_shadow(ctx, screen_x, ground_y, s, lighting_dx)

        # 1. Legs (Thin stick legs with boots/shoes, stride scaled by action)
        self._render_legs(ctx, char, actor, screen_x, hip_y, ground_y, s, flip_x, is_back, pose)

        # 2. Torso / Clothing Mass (Upper garment & outerwear silhouette with spine slant)
        self._render_clothing_mass(ctx, char, actor, screen_x, shoulder_x, shoulder_y, hip_y, s, flip_x, is_back, is_profile)

        # 3. Arms (Stick arms with action pose & simple hands)
        self._render_arms(ctx, char, actor, shoulder_x, shoulder_y, s, flip_x, is_back, is_profile, pose)

        # 4. Head & Face (Illustrated head, facial features, hair, headwear with head tilt)
        self._render_head_and_hair(
            ctx, char, actor, head_center_x, head_center_y, head_s, flip_x, is_back, is_profile, is_hero, is_bg,
            head_tilt=pose.get("head_tilt", 0.0)
        )

        ctx.restore()

    def _render_contact_shadow(
        self,
        ctx: cairo.Context,
        x: float,
        ground_y: float,
        s: float,
        lighting_dx: float,
    ) -> None:
        ctx.save()
        ctx.translate(x + lighting_dx * 12.0 * s, ground_y)
        ctx.scale(1.0, 0.22)
        ctx.arc(0, 0, 48.0 * s, 0, math.tau)
        ctx.set_source_rgba(0.06, 0.06, 0.08, 0.35)
        ctx.fill()
        ctx.restore()

    def _render_legs(
        self,
        ctx: cairo.Context,
        char: ResolvedCharacter,
        actor: ActorBlock,
        x: float,
        hip_y: float,
        ground_y: float,
        s: float,
        flip_x: float,
        is_back: bool,
        pose: Optional[dict[str, Any]] = None,
    ) -> None:
        pose = pose or {}
        ctx.save()
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)

        leg_color = hex_to_rgb(char.costume.palette.get("secondary", "#2a2d34"))
        boot_color = hex_to_rgb(char.costume.palette.get("trim", "#141518"))

        # Stance stride / crouch scaled by performance kinematics
        stride = 28.0 * s * pose.get("stride_scale", 1.0)
        if actor.action in ("WALK", "RUN"):
            stride = 48.0 * s if actor.action == "RUN" else 36.0 * s

        l_foot_x = x - stride * flip_x
        r_foot_x = x + stride * flip_x
        l_foot_y = ground_y
        r_foot_y = ground_y

        # Knee bending with crouch drop compensation
        hip_drop = pose.get("hip_drop", 0.0) * s
        knee_bend_out = 1.0 + (hip_drop / (35.0 * s + 0.001)) * 0.4
        l_knee_x = x - (stride * 0.5 * knee_bend_out) * flip_x
        l_knee_y = hip_y + (ground_y - hip_y) * (0.58 if hip_drop > 0 else 0.52)
        r_knee_x = x + (stride * 0.5 * knee_bend_out) * flip_x
        r_knee_y = hip_y + (ground_y - hip_y) * (0.58 if hip_drop > 0 else 0.52)

        # Draw left leg
        ctx.set_source_rgb(*leg_color)
        ctx.set_line_width(7.5 * s)
        ctx.move_to(x - 12.0 * s * flip_x, hip_y)
        ctx.line_to(l_knee_x, l_knee_y)
        ctx.line_to(l_foot_x, l_foot_y)
        ctx.stroke()

        # Draw right leg
        ctx.move_to(x + 12.0 * s * flip_x, hip_y)
        ctx.line_to(r_knee_x, r_knee_y)
        ctx.line_to(r_foot_x, r_foot_y)
        ctx.stroke()

        # Boots / Shoes (Simple illustrated mass)
        ctx.set_source_rgb(*boot_color)
        for fx, fy in [(l_foot_x, l_foot_y), (r_foot_x, r_foot_y)]:
            ctx.save()
            ctx.translate(fx, fy - 6.0 * s)
            ctx.scale(flip_x, 1.0)
            ctx.rectangle(-8.0 * s, 0, 24.0 * s, 8.0 * s)
            ctx.fill_preserve()
            ctx.set_source_rgb(*self.ink)
            ctx.set_line_width(2.0 * s)
            ctx.stroke()
            ctx.restore()

        ctx.restore()

    def _render_clothing_mass(
        self,
        ctx: cairo.Context,
        char: ResolvedCharacter,
        actor: ActorBlock,
        x: float,
        shoulder_x: float,
        shoulder_y: float,
        hip_y: float,
        s: float,
        flip_x: float,
        is_back: bool,
        is_profile: bool,
    ) -> None:
        ctx.save()
        c_palette = char.costume.palette
        primary_color = hex_to_rgb(c_palette.get("primary", "#455060"))
        accent_color = hex_to_rgb(c_palette.get("accent", "#a68852"))

        # Torso bounding trapezoid with spine slant
        top_w = 46.0 * s * (char.body.shoulder_width or 1.0)
        bot_w = 36.0 * s

        ctx.move_to(shoulder_x - top_w * 0.5, shoulder_y)
        ctx.curve_to(shoulder_x - top_w * 0.55, shoulder_y + 40.0 * s, x - bot_w * 0.55, hip_y - 20.0 * s, x - bot_w * 0.5, hip_y)
        ctx.line_to(x + bot_w * 0.5, hip_y)
        ctx.curve_to(x + bot_w * 0.55, hip_y - 20.0 * s, shoulder_x + top_w * 0.55, shoulder_y + 40.0 * s, shoulder_x + top_w * 0.5, shoulder_y)
        ctx.close_path()

        # Fill clothing mass
        ctx.set_source_rgb(*primary_color)
        ctx.fill_preserve()
        ctx.set_source_rgb(*self.ink)
        ctx.set_line_width(4.5 * s)
        ctx.stroke()

        # Collar / Lapel / Belt details
        if not is_back:
            # Collar V-shape or lapel
            ctx.move_to(shoulder_x - 16.0 * s, shoulder_y)
            ctx.line_to(shoulder_x, shoulder_y + 35.0 * s)
            ctx.line_to(shoulder_x + 16.0 * s, shoulder_y)
            ctx.set_source_rgb(*accent_color)
            ctx.set_line_width(2.5 * s)
            ctx.stroke()

            # Belt at waist
            belt_y = hip_y - 15.0 * s
            ctx.rectangle(x - bot_w * 0.52, belt_y, bot_w * 1.04, 10.0 * s)
            ctx.set_source_rgb(*self.ink)
            ctx.fill()

            # Belt buckle
            ctx.rectangle(x - 6.0 * s, belt_y - 1.0 * s, 12.0 * s, 12.0 * s)
            ctx.set_source_rgb(*accent_color)
            ctx.fill_preserve()
            ctx.set_source_rgb(*self.ink)
            ctx.set_line_width(1.5 * s)
            ctx.stroke()

        ctx.restore()

    def _render_arms(
        self,
        ctx: cairo.Context,
        char: ResolvedCharacter,
        actor: ActorBlock,
        shoulder_x: float,
        shoulder_y: float,
        s: float,
        flip_x: float,
        is_back: bool,
        is_profile: bool,
        pose: Optional[dict[str, Any]] = None,
    ) -> None:
        pose = pose or {}
        ctx.save()
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)

        arm_color = hex_to_rgb(char.costume.palette.get("primary", "#455060"))
        skin_color = hex_to_rgb(char.face.skin_tone or "#ead6be")

        # Kinematic arm endpoints computed from semantic action & intent
        l_e = pose.get("l_elbow", [-28.0, 55.0])
        l_h = pose.get("l_hand", [-35.0, 110.0])
        r_e = pose.get("r_elbow", [28.0, 55.0])
        r_h = pose.get("r_hand", [35.0, 110.0])

        l_elbow_x = shoulder_x + l_e[0] * s * flip_x
        l_elbow_y = shoulder_y + l_e[1] * s
        l_hand_x = shoulder_x + l_h[0] * s * flip_x
        l_hand_y = shoulder_y + l_h[1] * s

        r_elbow_x = shoulder_x + r_e[0] * s * flip_x
        r_elbow_y = shoulder_y + r_e[1] * s
        r_hand_x = shoulder_x + r_h[0] * s * flip_x
        r_hand_y = shoulder_y + r_h[1] * s

        # Draw left arm
        ctx.set_source_rgb(*arm_color)
        ctx.set_line_width(6.5 * s)
        ctx.move_to(shoulder_x - 22.0 * s * flip_x, shoulder_y + 8.0 * s)
        ctx.line_to(l_elbow_x, l_elbow_y)
        ctx.line_to(l_hand_x, l_hand_y)
        ctx.stroke()

        # Draw right arm
        ctx.move_to(shoulder_x + 22.0 * s * flip_x, shoulder_y + 8.0 * s)
        ctx.line_to(r_elbow_x, r_elbow_y)
        ctx.line_to(r_hand_x, r_hand_y)
        ctx.stroke()

        # Hands
        ctx.set_source_rgb(*skin_color)
        for hx, hy, side in [(l_hand_x, l_hand_y, -1.0), (r_hand_x, r_hand_y, 1.0)]:
            ctx.save()
            ctx.translate(hx, hy)
            ctx.scale(flip_x * side, 1.0)
            ctx.arc(0, 0, 7.0 * s, 0, math.tau)
            ctx.fill_preserve()
            ctx.set_source_rgb(*self.ink)
            ctx.set_line_width(1.8 * s)
            ctx.stroke()
            # Simple thumb contour
            ctx.move_to(4.0 * s, 0)
            ctx.line_to(8.0 * s, -3.0 * s)
            ctx.stroke()
            ctx.restore()

        ctx.restore()

    def _render_head_and_hair(
        self,
        ctx: cairo.Context,
        char: ResolvedCharacter,
        actor: ActorBlock,
        cx: float,
        cy: float,
        s: float,
        flip_x: float,
        is_back: bool,
        is_profile: bool,
        is_hero: bool,
        is_bg: bool,
        head_tilt: float = 0.0,
    ) -> None:
        ctx.save()
        if abs(head_tilt) > 0.1:
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(head_tilt * flip_x))
            ctx.translate(-cx, -cy)

        skin_color = hex_to_rgb(char.face.skin_tone or "#ead6be")
        hair_color = hex_to_rgb(char.hair.color or "#2c2420")

        # Head dimensions
        hw = 38.0 * s * (char.face.head_width or 1.0)
        hh = 45.0 * s * (char.face.head_height or 1.0)

        # 1. Base head ellipse (Illustrated skin mass)
        ctx.save()
        ctx.translate(cx, cy)
        ctx.scale(1.0, hh / hw)
        ctx.arc(0, 0, hw, 0, math.tau)
        ctx.set_source_rgb(*skin_color)
        ctx.fill_preserve()
        ctx.set_source_rgb(*self.ink)
        ctx.set_line_width(4.0 * s)
        ctx.stroke()
        ctx.restore()

        # 2. Facial Features (unless viewing from BACK)
        if not is_back and not is_bg:
            self._render_face_features(ctx, char, actor, cx, cy, s, flip_x, is_profile, is_hero)

        # 3. Hair Style Silhouette (Parametric Bézier curves matching HairStyleDNA)
        self._render_hair_silhouette(ctx, char.hair, cx, cy, hw, hh, s, flip_x, is_back, is_profile, hair_color)

        # 4. Headwear (if present in costume)
        if char.costume.headwear and char.costume.headwear != "NONE":
            self._render_headwear(ctx, char.costume.headwear, char.costume.palette, cx, cy, hw, hh, s, flip_x)

        # 5. Distinctive Anchors (Eye bandage, spectacles, mustache)
        if not is_back:
            self._render_anchors_and_details(ctx, char, cx, cy, hw, hh, s, flip_x)

        ctx.restore()

    def _render_face_features(
        self,
        ctx: cairo.Context,
        char: ResolvedCharacter,
        actor: ActorBlock,
        cx: float,
        cy: float,
        s: float,
        flip_x: float,
        is_profile: bool,
        is_hero: bool,
    ) -> None:
        ctx.save()
        ctx.set_source_rgb(*self.ink)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)

        emotion = actor.emotion.upper()
        face = char.face

        # Center offsets for profile / 3/4
        face_shift = 12.0 * s * flip_x if is_profile else (6.0 * s * flip_x)

        # Eyes
        eye_spacing = 14.0 * s * (face.eye_spacing or 1.0)
        l_eye_x = cx + face_shift - eye_spacing * 0.5
        r_eye_x = cx + face_shift + eye_spacing * 0.5
        eye_y = cy - 2.0 * s

        if is_profile:
            # Single eye visible
            p_eye_x = cx + 14.0 * s * flip_x
            ctx.arc(p_eye_x, eye_y, 4.0 * s, 0, math.tau)
            ctx.fill()
        else:
            # Both eyes
            ctx.arc(l_eye_x, eye_y, 3.5 * s, 0, math.tau)
            ctx.fill()
            ctx.arc(r_eye_x, eye_y, 3.5 * s, 0, math.tau)
            ctx.fill()

        # Eyebrows (Driven by emotion)
        brow_y = eye_y - 8.0 * s
        brow_slant = 0.0
        if emotion in ("ANGRY", "DETERMINED"):
            brow_slant = 4.0 * s
        elif emotion in ("AFRAID", "SAD", "EXHAUSTED"):
            brow_slant = -3.5 * s

        ctx.set_line_width(2.8 * s)
        if not is_profile:
            # Left brow
            ctx.move_to(l_eye_x - 6.0 * s, brow_y - brow_slant * 0.5)
            ctx.line_to(l_eye_x + 6.0 * s, brow_y + brow_slant * 0.5)
            ctx.stroke()
            # Right brow
            ctx.move_to(r_eye_x - 6.0 * s, brow_y + brow_slant * 0.5)
            ctx.line_to(r_eye_x + 6.0 * s, brow_y - brow_slant * 0.5)
            ctx.stroke()
        else:
            ctx.move_to(cx + 8.0 * s * flip_x, brow_y - brow_slant)
            ctx.line_to(cx + 20.0 * s * flip_x, brow_y + brow_slant)
            ctx.stroke()

        # Nose (Simple expressive stroke)
        nose_x = cx + face_shift
        nose_y = eye_y + 10.0 * s
        ctx.set_line_width(2.2 * s)
        ctx.move_to(nose_x, eye_y + 4.0 * s)
        ctx.line_to(nose_x + 4.0 * s * flip_x, nose_y)
        ctx.line_to(nose_x - 1.0 * s * flip_x, nose_y + 2.0 * s)
        ctx.stroke()

        # Mouth (Expressive curve based on emotion)
        mouth_y = cy + 22.0 * s
        mouth_w = 9.0 * s
        ctx.set_line_width(2.5 * s)
        if emotion in ("HAPPY", "AMUSED", "RELIEVED"):
            # Smile arc
            ctx.arc(cx + face_shift, mouth_y - 4.0 * s, mouth_w, 0.2 * math.pi, 0.8 * math.pi)
            ctx.stroke()
        elif emotion in ("SAD", "EXHAUSTED", "AFRAID"):
            # Frown arc
            ctx.arc(cx + face_shift, mouth_y + 8.0 * s, mouth_w, 1.2 * math.pi, 1.8 * math.pi)
            ctx.stroke()
        elif emotion in ("ARGUE", "SPEAK"):
            # Open talking mouth
            ctx.rectangle(cx + face_shift - 5.0 * s, mouth_y - 2.0 * s, 10.0 * s, 7.0 * s)
            ctx.fill()
        else:
            # Neutral line
            ctx.move_to(cx + face_shift - mouth_w, mouth_y)
            ctx.line_to(cx + face_shift + mouth_w, mouth_y)
            ctx.stroke()

        ctx.restore()

    def _render_hair_silhouette(
        self,
        ctx: cairo.Context,
        hair: HairStyleDNA,
        cx: float,
        cy: float,
        hw: float,
        hh: float,
        s: float,
        flip_x: float,
        is_back: bool,
        is_profile: bool,
        hair_color: tuple[float, float, float],
    ) -> None:
        shape = hair.shape.upper()
        if shape == "BALD":
            return

        ctx.save()
        ctx.set_source_rgb(*hair_color)

        # Hair contour covering top and back of head
        top_y = cy - hh * 1.15
        left_x = cx - hw * 1.08
        right_x = cx + hw * 1.08

        ctx.move_to(left_x, cy - 2.0 * s)
        ctx.curve_to(left_x - 6.0 * s, cy - hh * 0.7, cx - hw * 0.6, top_y, cx, top_y)
        ctx.curve_to(cx + hw * 0.6, top_y, right_x + 6.0 * s, cy - hh * 0.7, right_x, cy - 2.0 * s)

        # Front fringe / hairline style
        if is_back:
            # Covers lower nape
            ctx.curve_to(cx + hw * 0.8, cy + hh * 0.4, cx - hw * 0.8, cy + hh * 0.4, left_x, cy - 2.0 * s)
        elif shape in ("SWEPT_SIDE", "FLAT_COMB"):
            # Strong recognizable side-parted comb
            part_dir = 1.0 if hair.part == "RIGHT" else -1.0
            ctx.curve_to(cx + 25.0 * s * part_dir, cy - hh * 0.35, cx - 10.0 * s * part_dir, cy - hh * 0.65, left_x, cy - 2.0 * s)
        elif shape == "CURLY":
            # Bumpy organic wave
            ctx.curve_to(cx + 15.0 * s, cy - hh * 0.4, cx - 15.0 * s, cy - hh * 0.4, left_x, cy - 2.0 * s)
        else:
            # Clean forehead hairline
            ctx.curve_to(cx + hw * 0.4, cy - hh * 0.5, cx - hw * 0.4, cy - hh * 0.5, left_x, cy - 2.0 * s)

        ctx.close_path()
        ctx.fill_preserve()
        ctx.set_source_rgb(*self.ink)
        ctx.set_line_width(3.5 * s)
        ctx.stroke()

        # Sideburns
        ctx.rectangle(left_x + 2.0 * s, cy - 4.0 * s, 6.0 * s, 14.0 * s)
        ctx.rectangle(right_x - 8.0 * s, cy - 4.0 * s, 6.0 * s, 14.0 * s)
        ctx.set_source_rgb(*hair_color)
        ctx.fill()

        ctx.restore()

    def _render_headwear(
        self,
        ctx: cairo.Context,
        headwear: str,
        palette: dict[str, str],
        cx: float,
        cy: float,
        hw: float,
        hh: float,
        s: float,
        flip_x: float,
    ) -> None:
        ctx.save()
        color = hex_to_rgb(palette.get("secondary", "#2a2d34"))
        accent = hex_to_rgb(palette.get("accent", "#a68852"))

        hw_type = headwear.upper()
        hat_y = cy - hh * 0.65

        if hw_type in ("PEAKED_CAP", "FIELD_CAP"):
            # Cap band & crown
            ctx.rectangle(cx - hw * 1.1, hat_y, hw * 2.2, 18.0 * s)
            ctx.curve_to(cx - hw * 0.9, hat_y - 25.0 * s, cx + hw * 0.9, hat_y - 25.0 * s, cx + hw * 1.1, hat_y)
            ctx.set_source_rgb(*color)
            ctx.fill_preserve()
            ctx.set_source_rgb(*self.ink)
            ctx.set_line_width(3.0 * s)
            ctx.stroke()

            # Visor peak
            ctx.move_to(cx - hw * 0.8, hat_y + 16.0 * s)
            ctx.curve_to(cx, hat_y + 26.0 * s, cx + hw * 1.2 * flip_x, hat_y + 26.0 * s, cx + hw * 1.35 * flip_x, hat_y + 18.0 * s)
            ctx.set_source_rgb(0.08, 0.08, 0.10)
            ctx.set_line_width(4.5 * s)
            ctx.stroke()

        elif hw_type in ("STEEL_HELMET", "SPIKED_HELMET"):
            # Curved dome helmet
            ctx.arc(cx, hat_y + 5.0 * s, hw * 1.15, math.pi, math.tau)
            ctx.set_source_rgb(0.32, 0.35, 0.38)
            ctx.fill_preserve()
            ctx.set_source_rgb(*self.ink)
            ctx.set_line_width(3.5 * s)
            ctx.stroke()

        elif hw_type == "BANDAGE_WRAP":
            # Medical head bandage
            ctx.rectangle(cx - hw * 1.05, hat_y - 8.0 * s, hw * 2.1, 28.0 * s)
            ctx.set_source_rgb(0.92, 0.93, 0.95)
            ctx.fill_preserve()
            ctx.set_source_rgb(*self.ink)
            ctx.set_line_width(2.5 * s)
            ctx.stroke()

        ctx.restore()

    def _render_anchors_and_details(
        self,
        ctx: cairo.Context,
        char: ResolvedCharacter,
        cx: float,
        cy: float,
        hw: float,
        hh: float,
        s: float,
        flip_x: float,
    ) -> None:
        ctx.save()
        face = char.face
        conditions = char.conditions

        # 1. Mustache / Facial hair
        if face.facial_hair and face.facial_hair != "NONE":
            fh = face.facial_hair.upper()
            m_color = hex_to_rgb(face.facial_hair_color or char.hair.color or "#221a14")
            ctx.set_source_rgb(*m_color)

            if "TOOTHBRUSH" in fh or "SMALL" in fh:
                # Small neat center mustache
                ctx.rectangle(cx - 7.0 * s, cy + 8.0 * s, 14.0 * s, 7.5 * s)
                ctx.fill_preserve()
                ctx.set_source_rgb(*self.ink)
                ctx.set_line_width(1.5 * s)
                ctx.stroke()
            elif "THICK" in fh or "HANDLEBAR" in fh:
                # Wide mustache
                ctx.rectangle(cx - 15.0 * s, cy + 8.0 * s, 30.0 * s, 9.0 * s)
                ctx.fill()

        # 2. Eye Bandage condition (Medical convalescent context)
        if "EYE_BANDAGE" in conditions or "HEAD_BANDAGE" in conditions:
            ctx.save()
            ctx.set_source_rgb(0.94, 0.95, 0.96)
            ctx.rectangle(cx - hw * 0.95, cy - 14.0 * s, hw * 1.9, 24.0 * s)
            ctx.fill_preserve()
            ctx.set_source_rgb(*self.ink)
            ctx.set_line_width(2.5 * s)
            ctx.stroke()
            # Fold lines
            ctx.move_to(cx - hw * 0.9, cy - 2.0 * s)
            ctx.line_to(cx + hw * 0.9, cy - 2.0 * s)
            ctx.stroke()
            ctx.restore()

        # 3. Spectacles
        if "SPECTACLES_ROUND" in face.distinctive_anchors:
            ctx.set_source_rgb(*self.ink)
            ctx.set_line_width(2.0 * s)
            ctx.arc(cx - 14.0 * s, cy - 2.0 * s, 7.0 * s, 0, math.tau)
            ctx.stroke()
            ctx.arc(cx + 14.0 * s, cy - 2.0 * s, 7.0 * s, 0, math.tau)
            ctx.stroke()
            ctx.move_to(cx - 7.0 * s, cy - 2.0 * s)
            ctx.line_to(cx + 7.0 * s, cy - 2.0 * s)
            ctx.stroke()

        ctx.restore()
