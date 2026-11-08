"""Cinematic 2D Lighting Engine.

Translates LightingSpec and AtmosphereSpec into 2D drawing directives:
- Key light vector and horizontal direction (dx)
- Directional cast and contact shadow geometry
- Ambient environment color tinting (Warm, Cold Dusk, Overcast, Golden Hour)
- Volumetric practical light sources (lanterns, casement window beams, explosions)
- Subtle cinematic edge vignette and depth atmospheric gradient
"""
from __future__ import annotations

import math
from typing import Any
import cairo

from ..scene_builder.blueprint import LightingSpec, AtmosphereSpec


class CinematicLightingEngine:
    """Manages scene-wide color temperature, key light vectors, shadows, and atmospheric illumination."""

    def __init__(self, lighting: LightingSpec, atmosphere: AtmosphereSpec) -> None:
        self.lighting = lighting
        self.atmosphere = atmosphere
        self._init_properties()

    def _init_properties(self) -> None:
        k_dir = self.lighting.key_direction.upper()
        if "LEFT" in k_dir:
            self.key_dx = 1.0  # Light shines towards right
        elif "RIGHT" in k_dir:
            self.key_dx = -1.0  # Light shines towards left
        else:
            self.key_dx = 0.5

        # Shadow direction vector
        s_dir = self.lighting.shadow_direction.upper()
        if "BOTTOM_RIGHT" in s_dir or "RIGHT" in s_dir:
            self.shadow_dx = 55.0
            self.shadow_dy = 18.0
        elif "BOTTOM_LEFT" in s_dir or "LEFT" in s_dir:
            self.shadow_dx = -55.0
            self.shadow_dy = 18.0
        elif "LONG_FORWARD" in s_dir:
            self.shadow_dx = 15.0
            self.shadow_dy = 42.0
        else:
            self.shadow_dx = 30.0
            self.shadow_dy = 14.0

        # Color temperature RGB tints
        ct = self.lighting.color_temperature.upper()
        if "WARM" in ct or "GOLDEN" in ct:
            self.ambient_tint = (1.05, 0.96, 0.85)
            self.shadow_tint = (0.22, 0.16, 0.14)
            self.rim_color = (1.0, 0.94, 0.82, 0.75)
        elif "COLD" in ct or "DUSK" in ct or "NIGHT" in ct:
            self.ambient_tint = (0.86, 0.90, 1.02)
            self.shadow_tint = (0.12, 0.14, 0.20)
            self.rim_color = (0.85, 0.92, 1.0, 0.70)
        elif "SULLEN" in ct or "OVERCAST" in ct:
            self.ambient_tint = (0.92, 0.92, 0.90)
            self.shadow_tint = (0.15, 0.15, 0.16)
            self.rim_color = (0.95, 0.95, 0.95, 0.50)
        else:
            self.ambient_tint = (1.0, 1.0, 1.0)
            self.shadow_tint = (0.18, 0.18, 0.20)
            self.rim_color = (1.0, 1.0, 1.0, 0.60)

    def get_lighting_dx(self) -> float:
        """Returns horizontal light vector (+1.0 for left-to-right, -1.0 for right-to-left)."""
        return self.key_dx

    def get_shadow_offset(self, scale: float = 1.0) -> tuple[float, float]:
        """Returns (dx, dy) shadow displacement."""
        return (self.shadow_dx * scale, self.shadow_dy * scale)

    def apply_contact_shadow(
        self,
        ctx: cairo.Context,
        cx: float,
        ground_y: float,
        rx: float,
        ry: float,
        intensity: float = 1.0,
    ) -> None:
        """Draw an elliptical ground contact shadow cast by an actor or prop."""
        ctx.save()
        sdx, sdy = self.get_shadow_offset(1.0)
        ctx.translate(cx + sdx * 0.45, ground_y + sdy * 0.45)
        ctx.scale(1.0, ry / max(1.0, rx))
        ctx.arc(0, 0, rx, 0, math.tau)

        alpha = 0.45 * self.lighting.key_intensity * intensity
        ctx.set_source_rgba(self.shadow_tint[0], self.shadow_tint[1], self.shadow_tint[2], alpha)
        ctx.fill()
        ctx.restore()

    def apply_sky_ground_base(
        self,
        ctx: cairo.Context,
        width: int,
        height: int,
        horizon_y_px: float,
        sky_colors: tuple[tuple[float, float, float], tuple[float, float, float]],
        ground_colors: tuple[tuple[float, float, float], tuple[float, float, float]],
    ) -> None:
        """Render base atmospheric linear gradients for sky and ground planes."""
        ctx.save()

        # Sky gradient (top to horizon)
        sky_grad = cairo.LinearGradient(0, 0, 0, horizon_y_px)
        s_top, s_bot = sky_colors
        sky_grad.add_color_stop_rgb(
            0.0,
            s_top[0] * self.ambient_tint[0],
            s_top[1] * self.ambient_tint[1],
            s_top[2] * self.ambient_tint[2],
        )
        sky_grad.add_color_stop_rgb(
            1.0,
            s_bot[0] * self.ambient_tint[0],
            s_bot[1] * self.ambient_tint[1],
            s_bot[2] * self.ambient_tint[2],
        )
        ctx.rectangle(0, 0, width, horizon_y_px)
        ctx.set_source(sky_grad)
        ctx.fill()

        # Ground gradient (horizon to bottom)
        g_grad = cairo.LinearGradient(0, horizon_y_px, 0, height)
        g_top, g_bot = ground_colors
        g_grad.add_color_stop_rgb(0.0, *g_top)
        g_grad.add_color_stop_rgb(1.0, *g_bot)
        ctx.rectangle(0, horizon_y_px, width, height - horizon_y_px)
        ctx.set_source(g_grad)
        ctx.fill()

        ctx.restore()
