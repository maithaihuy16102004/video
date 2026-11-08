"""English Prompt Synthesizer adhering strictly to Phase 9.

Structure:
1. SUBJECT / ENVIRONMENT
2. HISTORICAL CONTEXT
3. CURRENT STORY MOMENT
4. CAMERA
5. COMPOSITION
6. PERSPECTIVE
7. DEPTH
8. CHARACTER RESERVED AREA
9. ENVIRONMENTAL STORYTELLING
10. SECONDARY ACTION
11. LIGHTING
12. ATMOSPHERE
13. STYLE
14. HISTORICAL CONSTRAINTS
15. NEGATIVE CONSTRAINTS

Strict rules:
- Synthesized in pure ENGLISH.
- Vietnamese narration preserved in blueprint metadata, NOT injected into Gemini image prompt.
- No quality spam ('masterpiece', '8K', 'award winning').
- Clear visual instructions.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .blueprint import SceneBlueprint


class EnglishPromptSynthesizer:
    """Synthesizes structured English concept briefs for Gemini Image API."""

    STYLE_BLOCK = (
        "Style: Premium editorial 2D historical illustration. "
        "Matte finish, controlled graphic linework, stylized architectural silhouettes, "
        "atmospheric depth planes, historically grounded realism compatible with 2D stickman character actors. "
        "Explicitly prohibited: photorealism, 3D CGI rendering, anime, real human photography, glossy video game art."
    )

    def build_prompt_package(self, bp: SceneBlueprint) -> tuple[str, str, str]:
        """Returns (positive_prompt, negative_prompt, prompt_sha256)."""
        lines: list[str] = []

        # 1. SUBJECT / ENVIRONMENT
        lines.append(f"SUBJECT / ENVIRONMENT:\nEmpty historical set plate: {bp.history.location_id.replace('_', ' ').title()}.")

        # 2. HISTORICAL CONTEXT
        lines.append(
            f"HISTORICAL CONTEXT:\nYear {bp.history.year}, {bp.history.country}. "
            f"Event Context: {bp.history.event_context}. "
            f"Political & Military Context: {bp.history.political_military_context}."
        )

        # 3. CURRENT STORY MOMENT
        lines.append(
            f"CURRENT STORY MOMENT:\n{bp.story.current_beat}. "
            f"Previous Action: {bp.story.previous_beat}. "
            f"Upcoming Action: {bp.story.next_beat}. "
            f"Emotional Tone: {bp.story.emotion}."
        )

        # 4. CAMERA
        lines.append(
            f"CAMERA:\nShot Size: {bp.camera.shot_size}. "
            f"Camera Height: {bp.camera.height}. "
            f"Pitch: {bp.camera.pitch:+.1f} degrees (vertical tilt). "
            f"Yaw: {bp.camera.yaw:+.1f} degrees (horizontal pan). "
            f"Lens: {bp.camera.lens_feel}. "
            f"Horizon Line: positioned at {bp.camera.horizon_y * 100:.1f}% from top of canvas."
        )

        # 5. COMPOSITION
        lines.append(
            f"COMPOSITION:\nVisual hierarchy centers on environmental depth. "
            f"Framing guides attention toward the future protagonist position. "
            f"Foreground occlusion factor: {bp.composition.foreground_occlusion:.2f}."
        )

        # 6. PERSPECTIVE
        lines.append(
            f"PERSPECTIVE:\nSystem: {bp.perspective.type}. "
            f"Primary Vanishing Point at [x={bp.perspective.primary_vp[0]:.2f}, y={bp.perspective.primary_vp[1]:.2f}]. "
            f"Depth Axis: {bp.perspective.depth_axis}."
        )

        # 7. DEPTH
        lines.append(
            "DEPTH PLAN (4-TIER ARCHITECTURE):\n"
            f"- Foreground: {', '.join(bp.environment.foreground)}.\n"
            f"- Midground: {', '.join(bp.environment.midground)}.\n"
            f"- Background: {', '.join(bp.environment.background)}.\n"
            f"- Far Background: {', '.join(bp.environment.far_background)}."
        )

        # 8. CHARACTER RESERVED AREA
        rz = bp.composition.character_reserved_zone
        if rz.width > 0.0 and rz.height > 0.0:
            lines.append(
                f"CHARACTER RESERVED AREA:\n"
                f"Normalized Bounding Box [x={rz.x:.2f}, y={rz.y:.2f}, width={rz.width:.2f}, height={rz.height:.2f}]. "
                "CRITICAL MANDATE: Keep this area completely clear of high-contrast clutter, vertical posts, "
                "doorway edges, bright lanterns, or human faces. The scene must lead eyes toward this area, "
                "but DO NOT paint any protagonist actor or stickman in this zone. Leave it ready for compositing."
            )
        else:
            lines.append("CHARACTER RESERVED AREA:\nPanoramic environmental view. No protagonist overlay.")

        # 9. ENVIRONMENTAL STORYTELLING
        lines.append("ENVIRONMENTAL STORYTELLING:\n" + "\n".join(f"- {item}" for item in bp.environment.storytelling_details))

        # 10. SECONDARY ACTION
        if bp.environment.secondary_actions:
            lines.append("SECONDARY ACTION:\n" + "\n".join(f"- {item}" for item in bp.environment.secondary_actions))
        else:
            lines.append("SECONDARY ACTION:\nStill environmental atmosphere with no active crowd.")

        # 11. LIGHTING
        lines.append(
            f"LIGHTING:\nKey Direction: {bp.lighting.key_direction} (intensity {bp.lighting.key_intensity:.2f}). "
            f"Ambient Level: {bp.lighting.ambient_level:.2f}. "
            f"Shadow Direction: {bp.lighting.shadow_direction}. "
            f"Color Temperature: {bp.lighting.color_temperature}."
        )

        # 12. ATMOSPHERE
        lines.append(
            f"ATMOSPHERE:\nHaze: {bp.atmosphere.haze}. "
            f"Weather: {bp.atmosphere.weather}. "
            f"Time of Day: {bp.atmosphere.time_of_day}. "
            f"Volumetric Rays: {'Present' if bp.atmosphere.volumetric_light else 'None'}."
        )

        # 13. STYLE
        lines.append(f"STYLE:\n{self.STYLE_BLOCK}")

        # 14. HISTORICAL CONSTRAINTS
        lines.append("HISTORICAL CONSTRAINTS:\n" + "\n".join(f"- {c}" for c in bp.history.historical_constraints))

        # 15. NEGATIVE CONSTRAINTS
        neg_parts = [
            "human protagonist", "main character", "stickman", "stick figure", "human in foreground",
            "modern elements", "asphalt roads", "cars", "plastic", "electrical pylons", "neon signs",
            "photorealistic human face", "3D CGI render", "glossy videogame graphics", "anime style",
            "text", "subtitles", "watermark", "logo", "borders", "flat PowerPoint stage backdrop"
        ]
        neg_parts.extend(bp.negative_constraints)
        negative_prompt = ", ".join(dict.fromkeys(neg_parts))

        lines.append(f"NEGATIVE CONSTRAINTS:\n{negative_prompt}")

        positive_prompt = "\n\n".join(lines)
        prompt_sha256 = hashlib.sha256(positive_prompt.encode("utf-8")).hexdigest()

        return positive_prompt, negative_prompt, prompt_sha256
