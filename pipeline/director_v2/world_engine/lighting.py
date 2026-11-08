"""5-Point Cinematic World Lighting Engine.

Structure:
1. KEY: Primary directional light defining form, surface orientation, and specular highlights.
2. FILL: Ambient bounce lighting preventing crushed unreadable blacks.
3. RIM / SECONDARY: Edge separation stroke creating depth between overlapping silhouette planes.
4. SHADOW ZONES: Ambient occlusion pockets (under furniture, under revetments, bed bases).
5. ATMOSPHERIC LIGHT: Volumetric light cones, sunbeams, and luminous fog halos.

Focus & Contrast:
- Highest local contrast supports story focus (character reserved zone / narrative interaction).
- Distant and peripheral regions have reduced contrast and lower visual competition.
"""
from __future__ import annotations

import math
from typing import Any
import cairo

from ..scene_builder.blueprint import SceneBlueprint, LightingSpec, AtmosphereSpec


class WorldLightingEngine:
    """Manages 5-point lighting, focal contrast control, and atmospheric illumination."""

    def __init__(self, lighting: LightingSpec, atmosphere: AtmosphereSpec) -> None:
        self.lighting = lighting
        self.atmosphere = atmosphere
        self._setup_lighting_vectors()

    def _setup_lighting_vectors(self) -> None:
        k_dir = self.lighting.key_direction.upper()
        if "LEFT" in k_dir:
            self.key_dx = 1.0
            self.key_dy = 0.4
        elif "RIGHT" in k_dir:
            self.key_dx = -1.0
            self.key_dy = 0.4
        elif "OVERHEAD" in k_dir:
            self.key_dx = 0.0
            self.key_dy = 1.0
        else:
            self.key_dx = 0.5
            self.key_dy = 0.5

        # Ambient & color temperature
        ct = self.lighting.color_temperature.upper()
        if "WARM" in ct:
            self.key_color = (1.0, 0.94, 0.82)
            self.fill_color = (0.35, 0.28, 0.22)
            self.rim_color = (1.0, 0.90, 0.70, 0.65)
            self.shadow_color = (0.08, 0.06, 0.05)
        elif "COLD" in ct or "DUSK" in ct:
            self.key_color = (0.88, 0.94, 1.0)
            self.fill_color = (0.20, 0.24, 0.32)
            self.rim_color = (0.85, 0.92, 1.0, 0.60)
            self.shadow_color = (0.06, 0.07, 0.10)
        else:  # OVERCAST / SULLEN
            self.key_color = (0.92, 0.92, 0.92)
            self.fill_color = (0.28, 0.28, 0.30)
            self.rim_color = (0.90, 0.92, 0.95, 0.45)
            self.shadow_color = (0.08, 0.08, 0.09)

    def apply_directional_ambient_pass(
        self,
        ctx: cairo.Context,
        width: int,
        height: int,
        horizon_y_px: float,
    ) -> None:
        """Applies aerial perspective depth gradient (distant objects fade slightly into sky tint)."""
        ctx.save()
        grad = cairo.LinearGradient(0, 0, 0, horizon_y_px)
        grad.add_color_stop_rgba(0.0, self.key_color[0], self.key_color[1], self.key_color[2], 0.0)
        grad.add_color_stop_rgba(1.0, self.key_color[0], self.key_color[1], self.key_color[2], 0.12)
        ctx.rectangle(0, 0, width, horizon_y_px)
        ctx.set_source(grad)
        ctx.fill()
        ctx.restore()

    def apply_rim_light_to_path(
        self,
        ctx: cairo.Context,
        pts: list[tuple[float, float]],
        stroke_width: float = 2.0,
    ) -> None:
        """Strokes illuminated edge of an object with secondary rim light for plane separation."""
        if len(pts) < 2:
            return
        ctx.save()
        ctx.set_source_rgba(*self.rim_color)
        ctx.set_line_width(stroke_width)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.move_to(*pts[0])
        for pt in pts[1:]:
            ctx.line_to(*pt)
        ctx.stroke()
        ctx.restore()

    def apply_shadow_zone(
        self,
        ctx: cairo.Context,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        intensity: float = 1.0,
    ) -> None:
        """Renders ambient occlusion deep shadow zone beneath furniture or revetments."""
        ctx.save()
        ctx.translate(cx, cy)
        ctx.scale(1.0, ry / max(1.0, rx))
        ctx.arc(0, 0, rx, 0, math.tau)

        alpha = 0.55 * self.lighting.key_intensity * intensity
        ctx.set_source_rgba(self.shadow_color[0], self.shadow_color[1], self.shadow_color[2], alpha)
        ctx.fill()
        ctx.restore()

    def apply_story_focus_contrast(
        self,
        ctx: cairo.Context,
        width: int,
        height: int,
        focus_x: float,
        focus_y: float,
        focus_radius: float = 450.0,
    ) -> None:
        """Directs viewer attention towards story focus by gently darkening periphery."""
        ctx.save()
        max_r = math.hypot(width, height)
        grad = cairo.RadialGradient(focus_x, focus_y, focus_radius * 0.5, focus_x, focus_y, max_r * 0.75)
        grad.add_color_stop_rgba(0.0, 0.0, 0.0, 0.0, 0.0)
        grad.add_color_stop_rgba(0.5, 0.0, 0.0, 0.0, 0.15)
        grad.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.42)

        ctx.rectangle(0, 0, width, height)
        ctx.set_source(grad)
        ctx.fill()
        ctx.restore()
