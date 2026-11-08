"""Prompt Synthesizer: Translates SceneBlueprint into structured Gemini Concept Prompts.

Enforces:
1. Controlled Creative Freedom:
   - LOCKED: Camera geometry, horizon, perspective, reserved zone, historical period, shot purpose.
   - GUIDED: Architecture DNA, storytelling props, depth planes, lighting, secondary action.
   - FREE: Surface wear, micro debris, texture nuances.
2. Character Reserved Zone:
   - Explicit normalized bounding box coordinates.
   - Clear visual staging instruction to prevent clutter behind the protagonist.
3. 17-Tier Prompt Hierarchy.
4. Critic Correction Prompt Synthesis for the QC loop.
"""
from __future__ import annotations

from typing import Any

from .blueprint import SceneBlueprint


GLOBAL_STYLE_PROMPT = (
    "MASTERWORK CINEMATIC HISTORICAL CONCEPT ART ENVIRONMENT PLATE. "
    "Style: Premium editorial 2D illustration, stylized clean linework, strong graphic shapes, "
    "cinematic atmospheric depth, historically grounded matte finish, compatible with simple 2D stickman actors. "
    "STRICTLY FORBIDDEN: Photorealism, 3D CGI render, anime, real human photography, fantasy neon."
)


class PromptSynthesizer:
    """Synthesizes structured concept artist briefs for Gemini."""

    def build_prompt_package(self, bp: SceneBlueprint) -> tuple[str, str]:
        """Returns (positive_prompt, negative_prompt)."""
        lines: list[str] = []

        # 1. Global Style Header
        lines.append(f"=== GLOBAL VISUAL STYLE ===\n{GLOBAL_STYLE_PROMPT}\n")

        # 2. Historical & Narrative Anchor
        lines.append("=== NARRATIVE & HISTORICAL ANCHOR ===")
        lines.append(f"Scene & Shot ID: {bp.scene_id} / {bp.shot_id}")
        lines.append(f"Historical Year & Era: {bp.history.year} ({bp.history.country})")
        lines.append(f"Location: {bp.history.location_id}")
        lines.append(f"Event Context: {bp.history.event_context}")
        lines.append(f"Narration / Story Beat: \"{bp.story.narration}\"")
        lines.append(f"Shot Purpose: {bp.story.purpose} | Emotional Tone: {bp.story.emotion}\n")

        # 3. LOCKED PARAMETERS (Do NOT deviate)
        lines.append("=== [LOCKED] CAMERA & PERSPECTIVE SYSTEM (STRICTLY BINDING) ===")
        lines.append(f"Shot Size: {bp.camera.shot_size}")
        lines.append(f"Camera Height: {bp.camera.height} | Lens Feel: {bp.camera.lens_feel}")
        lines.append(f"Pitch Angle: {bp.camera.pitch:+.1f}° | Yaw Angle: {bp.camera.yaw:+.1f}°")
        lines.append(f"Horizon Position: {bp.camera.horizon_y * 100:.1f}% from top of canvas")
        lines.append(f"Perspective System: {bp.perspective.type}")
        lines.append(f"Primary Vanishing Point: x={bp.perspective.primary_vp[0]:.2f}, y={bp.perspective.primary_vp[1]:.2f}")
        lines.append(f"Depth Axis: {bp.perspective.depth_axis}\n")

        # 4. CHARACTER RESERVED SPACE (Spatial Handshake)
        rz = bp.composition.character_reserved_zone
        lines.append("=== [LOCKED] CHARACTER RESERVED ZONE (SPATIAL HANDSHAKE) ===")
        if rz.width > 0.0 and rz.height > 0.0:
            lines.append(
                f"RESERVED BOUNDING BOX: x={rz.x:.2f}, y={rz.y:.2f}, width={rz.width:.2f}, height={rz.height:.2f}. "
                "CRITICAL INSTRUCTION: Keep this region clear of high-contrast visual clutter, doorways, poles, "
                "lamps, or bright windows. Architectural lines, floorboards, or trench corridors should lead the viewer's "
                "eye TOWARDS this zone, but DO NOT draw any human protagonist or stickman actor in this space. "
                "The protagonist will be composited into this exact zone later."
            )
        else:
            lines.append("POV / Empty Subject Shot: Open environmental viewing zone across center frame.")
        lines.append("")

        # 5. GUIDED PARAMETERS: 4-Tier Depth Architecture
        lines.append("=== [GUIDED] 4-TIER DEPTH ARCHITECTURE ===")
        lines.append(f"- FOREGROUND: {', '.join(bp.environment.foreground)}")
        lines.append(f"- MIDGROUND: {', '.join(bp.environment.midground)}")
        lines.append(f"- BACKGROUND: {', '.join(bp.environment.background)}")
        lines.append(f"- FAR_BACKGROUND: {', '.join(bp.environment.far_background)}\n")

        # 6. GUIDED PARAMETERS: Storytelling Details & Secondary Action
        lines.append("=== [GUIDED] ENVIRONMENTAL STORYTELLING DETAILS (MAX 3 GROUNDED ITEMS) ===")
        for item in bp.environment.storytelling_details:
            lines.append(f"* {item}")
        if bp.environment.secondary_actions:
            lines.append("=== [GUIDED] SECONDARY AMBIENT ACTION ===")
            for act in bp.environment.secondary_actions:
                lines.append(f"* {act}")
        lines.append("")

        # 7. GUIDED PARAMETERS: Lighting & Atmosphere Handshake
        lines.append("=== [GUIDED] LIGHTING & ATMOSPHERE SPECIFICATION ===")
        lines.append(f"Key Light Direction: {bp.lighting.key_direction} (Intensity: {bp.lighting.key_intensity:.2f})")
        lines.append(f"Ambient Light Level: {bp.lighting.ambient_level:.2f}")
        lines.append(f"Shadow Direction: {bp.lighting.shadow_direction}")
        lines.append(f"Color Temperature: {bp.lighting.color_temperature}")
        if bp.lighting.practical_lights:
            lines.append(f"Practical Light Sources: {', '.join(bp.lighting.practical_lights)}")
        lines.append(f"Atmospheric Haze: {bp.atmosphere.haze} | Weather: {bp.atmosphere.weather} | Time: {bp.atmosphere.time_of_day}\n")

        # 8. FREE PARAMETERS
        lines.append("=== [FREE] TEXTURE & MICRO-SURFACE FREEDOM ===")
        lines.append("The artist has full creative freedom on realistic surface wear, weathered wood grain, mud splatters, "
                     "cobblestone variations, paint flaking, and atmospheric dust motes.\n")

        # 9. Strict Historical & Negative Constraints
        lines.append("=== MANDATORY HISTORICAL BOUNDARIES ===")
        for hc in bp.history.historical_constraints:
            lines.append(f"- {hc}")

        pos_prompt = "\n".join(lines)

        # Assemble Negative Prompt
        neg_parts = [
            "human protagonist", "main character", "stickman", "stick figure", "actor in foreground",
            "modern elements", "asphalt", "cars", "plastic", "electrical pylons", "neon signs",
            "photorealistic human face", "3D render", "CGI glossy", "anime style",
            "text", "watermark", "logo", "subtitles", "white border", "flat PowerPoint stage backdrop"
        ]
        neg_parts.extend(bp.negative_constraints)
        neg_prompt = ", ".join(dict.fromkeys(neg_parts))

        return pos_prompt, neg_prompt

    def build_critic_correction_prompt(
        self,
        bp: SceneBlueprint,
        original_prompt: str,
        critic_issues: list[dict[str, Any]],
    ) -> str:
        """Appends explicit QC corrections onto the prompt for a targeted Gemini retry."""
        correction_lines = [
            original_prompt,
            "\n" + "=" * 60,
            "=== VISUAL CRITIC QC CORRECTION ORDER (MANDATORY FIX) ===",
        ]
        for idx, issue in enumerate(critic_issues, 1):
            category = issue.get("category", "CRITIC_ISSUE")
            problem = issue.get("problem", "Discrepancy with Scene Blueprint")
            fix = issue.get("fix", "Adjust to match Blueprint specification exactly")
            correction_lines.append(f"ISSUE #{idx} [{category}]:")
            correction_lines.append(f"  PROBLEM: {problem}")
            correction_lines.append(f"  REQUIRED FIX: {fix}\n")

        correction_lines.append(
            "DO NOT REINVENT THE ENTIRE LOCATION. Preserve the established Location Visual DNA, "
            "materials, and lighting while strictly correcting the issues listed above."
        )
        return "\n".join(correction_lines)
