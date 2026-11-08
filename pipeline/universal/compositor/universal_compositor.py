"""Universal Compositor.

Integrates the UniversalWorldRenderer + IllustratedStickmanRenderer + Lighting Engine
into final composite editorial illustration frames.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import cairo

from ...director_v2.world_engine.lighting import WorldLightingEngine
from ...director_v2.scene_builder.blueprint import AtmosphereSpec, LightingSpec
from ..bibles.resolver import CharacterResolver
from ..character_engine.illustrated_stickman_renderer import IllustratedStickmanRenderer
from ..schemas import CharacterBible, LocationBible, LocationDNA, SceneBlueprint
from ..world_engine.universal_world_renderer import UniversalWorldRenderer


class UniversalCompositor:
    """Combines World + Illustrated Stickman Characters into full frames."""

    def __init__(
        self,
        world_renderer: Optional[UniversalWorldRenderer] = None,
        char_renderer: Optional[IllustratedStickmanRenderer] = None,
        width: int = 1920,
        height: int = 1080,
    ) -> None:
        self.width = width
        self.height = height
        self.world_renderer = world_renderer or UniversalWorldRenderer(width=width, height=height)
        self.char_renderer = char_renderer or IllustratedStickmanRenderer()

    def render_blueprint(
        self,
        bp: SceneBlueprint,
        loc: LocationDNA,
        char_bible: CharacterBible,
        output_path: Optional[Path] = None,
    ) -> cairo.ImageSurface:
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        ctx = cairo.Context(surf)

        # Setup 5-point lighting from blueprint
        light_spec = LightingSpec(
            key_direction="LEFT_HIGH" if "LEFT" in bp.lighting_story.get("direction", "KEY_LEFT") else "RIGHT_HIGH",
            key_intensity=0.85,
            ambient_level=0.55,
            shadow_direction="BOTTOM_RIGHT" if "LEFT" in bp.lighting_story.get("direction", "KEY_LEFT") else "BOTTOM_LEFT",
            color_temperature="WARM_INDOOR" if loc.enclosure.upper() == "INTERIOR" else "SULLEN_OVERCAST",
            rim_opportunity=True,
        )
        atmo_spec = AtmosphereSpec(
            haze="LIGHT_MIST" if loc.weather.upper() == "RAIN" else "NONE",
            weather="DRIZZLE" if loc.weather.upper() == "RAIN" else "DRY",
            time_of_day="MIDDAY",
            volumetric_light=loc.enclosure.upper() == "INTERIOR",
        )
        lighting = WorldLightingEngine(light_spec, atmo_spec)

        # 1. Render World (Background + Midground)
        self.world_renderer.render_environment(ctx, loc, bp, lighting)

        # 2. Render Staged Stickman Characters
        horizon_px = bp.camera.horizon_y * self.height
        ground_y = horizon_px + (self.height - horizon_px) * 0.78
        lighting_dx = lighting.key_dx

        for actor in bp.actors:
            char_dna = char_bible.get(actor.character_id)
            if not char_dna:
                continue

            resolved = CharacterResolver.resolve_for_shot(char_dna, year=bp.year, location_id=bp.location_id)
            screen_x = actor.screen_x * self.width
            actor_ground_y = ground_y

            # Scale calculation
            shot_upper = bp.camera.shot.upper()
            scale = 1.0
            if "CLOSE" in shot_upper:
                scale = 1.65
                actor_ground_y = self.height * 0.95
            elif "WIDE" in shot_upper:
                scale = 0.72
            elif "GROUND" in shot_upper or "LOW" in shot_upper:
                scale = 1.25
                actor_ground_y = self.height * 0.90

            self.char_renderer.render_character(
                ctx=ctx,
                char=resolved,
                actor=actor,
                screen_x=screen_x,
                ground_y=actor_ground_y,
                scale=scale,
                lighting_dx=lighting_dx,
            )

        # 2b. Blueprint-owned semantic foreground element (authentic materials, not anonymous boxes)
        if bp.foreground_element:
            self._render_semantic_foreground(ctx, bp.foreground_element, lighting_dx)

        # 3. Apply Story Focus Contrast Shaping based on causal intent
        if bp.primary_focus.startswith("OBJECT:") and bp.props:
            focus_x = bp.props[0].screen_x * self.width
            focus_y = (bp.camera.horizon_y + 0.22) * self.height
        elif bp.primary_focus.startswith("ACTOR:") and bp.actors:
            focus_x = bp.actors[0].screen_x * self.width
            focus_y = (bp.camera.horizon_y + 0.16) * self.height
        else:
            focus_x = bp.camera.subject_position[0] * self.width
            focus_y = ground_y - 120.0

        focus_r = 380.0 if bp.reveal_strategy != "NONE" or bp.visual_energy == "HIGH" else 460.0
        lighting.apply_story_focus_contrast(ctx, self.width, self.height, focus_x, focus_y, focus_radius=focus_r)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            surf.write_to_png(str(output_path))

        return surf

    def _render_semantic_foreground(
        self,
        ctx: cairo.Context,
        fg_dict: dict,
        lighting_dx: float,
    ) -> None:
        """Renders authentic, physically grounded foreground elements based on material and depth."""
        material = str(fg_dict.get("material", "WOOD")).upper()
        reason = str(fg_dict.get("foreground_reason", "NONE")).upper()
        edge = str(fg_dict.get("edge_side", "LEFT")).upper()
        alpha = float(fg_dict.get("alpha", 0.95))

        ctx.save()

        if reason == "BEHIND_ACTOR" or material == "FABRIC":
            # Over-the-shoulder actor silhouette with authentic woolen coat curvature and rim light
            ctx.set_source_rgba(0.10, 0.11, 0.13, alpha)
            ctx.move_to(-40.0, self.height + 20.0)
            ctx.line_to(-40.0, self.height * 0.45)
            ctx.curve_to(
                self.width * 0.08, self.height * 0.44,
                self.width * 0.16, self.height * 0.52,
                self.width * 0.22, self.height * 0.65,
            )
            ctx.curve_to(
                self.width * 0.25, self.height * 0.75,
                self.width * 0.28, self.height * 0.88,
                self.width * 0.32, self.height + 20.0,
            )
            ctx.close_path()
            ctx.fill_preserve()

            # Rim lighting along actor shoulder contour
            ctx.set_source_rgba(0.55, 0.52, 0.46, 0.40)
            ctx.set_line_width(4.5)
            ctx.stroke()

            # Coat collar seam detail
            ctx.move_to(self.width * 0.08, self.height * 0.46)
            ctx.curve_to(
                self.width * 0.14, self.height * 0.58,
                self.width * 0.18, self.height * 0.70,
                self.width * 0.20, self.height * 0.82,
            )
            ctx.set_source_rgba(0.06, 0.07, 0.08, 0.70)
            ctx.set_line_width(3.0)
            ctx.stroke()

        elif material == "WOOD" and edge == "RIGHT":
            # Foreground table edge with beveled oak rim and glassware silhouette
            tx0 = self.width * 0.65
            ty0 = self.height + 10.0
            tx1 = self.width * 0.76
            ty1 = self.height * 0.72
            tx2 = self.width + 20.0
            ty2 = self.height * 0.72
            tx3 = self.width + 20.0
            ty3 = self.height + 10.0

            # Table top surface
            ctx.set_source_rgba(0.18, 0.13, 0.10, alpha)
            ctx.move_to(tx0, ty0)
            ctx.line_to(tx1, ty1)
            ctx.line_to(tx2, ty2)
            ctx.line_to(tx3, ty3)
            ctx.close_path()
            ctx.fill()

            # Table top bevel highlight
            ctx.move_to(tx0, ty0)
            ctx.line_to(tx1, ty1)
            ctx.line_to(tx2, ty2)
            ctx.set_source_rgba(0.38, 0.28, 0.20, 0.75)
            ctx.set_line_width(3.5)
            ctx.stroke()

            # Glassware silhouette on table
            gx = self.width * 0.84
            gy = self.height * 0.72
            ctx.set_source_rgba(0.24, 0.28, 0.32, 0.65)
            ctx.rectangle(gx - 18, gy - 75, 36, 75)
            ctx.fill()
            # Specular streak on glassware
            ctx.move_to(gx - 10, gy - 70)
            ctx.line_to(gx - 10, gy - 5)
            ctx.set_source_rgba(0.85, 0.90, 0.95, 0.55)
            ctx.set_line_width(2.5)
            ctx.stroke()

        elif material == "WOOD":
            # Split timber revetment post / doorway jamb on left edge
            pw = self.width * 0.14
            ctx.set_source_rgba(0.16, 0.13, 0.10, alpha)
            ctx.rectangle(-15.0, self.height * 0.18, pw + 15.0, self.height * 0.85)
            ctx.fill()

            # Beveled post edge
            ctx.move_to(pw, self.height * 0.18)
            ctx.line_to(pw, self.height)
            ctx.set_source_rgba(0.28, 0.22, 0.16, 0.65)
            ctx.set_line_width(3.0)
            ctx.stroke()

            # Woodgrain striations
            for offset in (0.28, 0.55, 0.78):
                ctx.move_to(pw * offset, self.height * 0.20)
                ctx.line_to(pw * offset, self.height)
                ctx.set_source_rgba(0.10, 0.08, 0.06, 0.50)
                ctx.set_line_width(2.0)
                ctx.stroke()

            # Iron wire / bracket band
            for by in (self.height * 0.42, self.height * 0.76):
                ctx.set_source_rgba(0.28, 0.30, 0.32, 0.80)
                ctx.rectangle(-10.0, by, pw + 12.0, 14.0)
                ctx.fill()

        elif material == "METAL" and edge == "RIGHT":
            # Turned metal bedpost upright with spherical finial
            px = self.width * 0.88
            pw = 32.0
            # Pillar column
            ctx.set_source_rgba(0.14, 0.15, 0.17, alpha)
            ctx.rectangle(px - pw * 0.5, self.height * 0.30, pw, self.height * 0.75)
            ctx.fill()

            # Spherical finial on top
            ctx.arc(px, self.height * 0.28, 28.0, 0, 6.28318)
            ctx.fill()

            # Metallic specular highlight
            ctx.move_to(px - 6.0, self.height * 0.30)
            ctx.line_to(px - 6.0, self.height)
            ctx.set_source_rgba(0.48, 0.50, 0.54, 0.60)
            ctx.set_line_width(3.0)
            ctx.stroke()

        elif material == "METAL":
            # Industrial machinery upright flange with conductor wire
            mw = self.width * 0.12
            ctx.set_source_rgba(0.15, 0.16, 0.18, alpha)
            ctx.rectangle(-10.0, self.height * 0.22, mw + 10.0, self.height * 0.80)
            ctx.fill()

            # Specular edge on upright
            ctx.move_to(mw, self.height * 0.22)
            ctx.line_to(mw, self.height)
            ctx.set_source_rgba(0.45, 0.48, 0.52, 0.65)
            ctx.set_line_width(3.5)
            ctx.stroke()

            # Bolt heads
            ctx.set_source_rgba(0.28, 0.30, 0.34, 0.90)
            for by in (self.height * 0.35, self.height * 0.55, self.height * 0.75, self.height * 0.92):
                ctx.arc(mw * 0.55, by, 7.0, 0, 6.28318)
                ctx.fill()

            # Copper insulated conductor wire
            ctx.move_to(mw * 0.30, self.height * 0.24)
            ctx.curve_to(mw * 0.40, self.height * 0.50, mw * 0.20, self.height * 0.70, mw * 0.35, self.height)
            ctx.set_source_rgba(0.55, 0.32, 0.18, 0.85)
            ctx.set_line_width(4.0)
            ctx.stroke()

        ctx.restore()
