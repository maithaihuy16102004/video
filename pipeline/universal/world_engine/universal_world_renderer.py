"""Universal Cinematic World Renderer.

Renders ANY environment dynamically from LocationDNA + SceneBlueprint + UniversalAssetResolver.
No per-location hard-coded render functions.
All architectural forms, floorings, ceilings, wall treatments, horizons, and prop placements
are driven strictly by DATA.
"""
from __future__ import annotations

import inspect
import math
from typing import Any, Optional
import cairo

from ...director_v2.world_engine.materials import MaterialSystem
from ...director_v2.world_engine.rough_path import ControlledIrregularityEngine
from ...director_v2.world_engine.lighting import WorldLightingEngine
from ..assets.asset_resolver import UniversalAssetResolver
from ..character_engine.illustrated_stickman_renderer import hex_to_rgb
from ..schemas import LocationDNA, PropPlacement, ResolvedCharacter, SceneBlueprint


def _safe_render_prop(reg, ctx, x, y, scale, lighting_dx, state="ACTIVE"):
    """Invokes asset render function with inspected keyword support."""
    if not reg or not reg.render_func:
        return
    try:
        sig = inspect.signature(reg.render_func)
        kwargs = {}
        if "scale" in sig.parameters:
            kwargs["scale"] = scale
        if "lighting_dx" in sig.parameters:
            kwargs["lighting_dx"] = lighting_dx
        if "state" in sig.parameters:
            kwargs["state"] = state
        reg.render_func(ctx, x=x, y=y, **kwargs)
    except Exception:
        try:
            reg.render_func(ctx, x=x, y=y, scale=scale, lighting_dx=lighting_dx)
        except Exception:
            pass


class UniversalWorldRenderer:
    """Master renderer for data-driven, multi-plane cinematic environments."""

    def __init__(
        self,
        asset_resolver: Optional[UniversalAssetResolver] = None,
        width: int = 1920,
        height: int = 1080,
    ) -> None:
        self.width = width
        self.height = height
        self.assets = asset_resolver or UniversalAssetResolver()

    def render_environment(
        self,
        ctx: cairo.Context,
        loc: LocationDNA,
        bp: SceneBlueprint,
        lighting: WorldLightingEngine,
    ) -> None:
        """Renders complete multi-plane environment without actors."""
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h
        vp_x = bp.camera.vanishing_point[0] * w
        vp_y = bp.camera.vanishing_point[1] * h

        # 1. FAR_BG Plane: Sky / Ceiling / Horizon Silhouette
        self._render_far_bg(ctx, loc, bp, horizon_px, vp_x, vp_y)

        # 2. BG Plane: Walls, Openings, Distant Architecture
        self._render_bg(ctx, loc, bp, horizon_px, vp_x, vp_y, lighting)

        # 3. MG Plane: Floor, Depth Paths, Midground Props
        self._render_mg(ctx, loc, bp, horizon_px, vp_x, vp_y, lighting)

        # 4. FG Plane: Foreground Props & Edge Frames
        self._render_fg(ctx, loc, bp, horizon_px, vp_x, vp_y, lighting)

        # 5. NEAR_FG Plane & Atmospheric Effects
        self._render_near_fg(ctx, loc, bp, horizon_px, lighting)

    def _render_far_bg(
        self,
        ctx: cairo.Context,
        loc: LocationDNA,
        bp: SceneBlueprint,
        horizon_px: float,
        vp_x: float,
        vp_y: float,
    ) -> None:
        w, h = self.width, self.height
        palette = loc.palette

        sky_top = hex_to_rgb(palette.get("sky_top", "#7a9cb8"))
        sky_bot = hex_to_rgb(palette.get("sky_bottom", "#c4d2de"))

        # Base atmospheric gradient
        sky_grad = cairo.LinearGradient(0, 0, 0, horizon_px)
        sky_grad.add_color_stop_rgb(0.0, *sky_top)
        sky_grad.add_color_stop_rgb(1.0, *sky_bot)
        ctx.rectangle(0, 0, w, horizon_px)
        ctx.set_source(sky_grad)
        ctx.fill()

        # Horizon feature
        feat = loc.horizon_feature.upper()
        if feat == "RUINED_RIDGE":
            ctx.save()
            ctx.move_to(0, horizon_px)
            ctx.line_to(w * 0.25, horizon_px - 35)
            ctx.line_to(w * 0.52, horizon_px - 18)
            ctx.line_to(w * 0.78, horizon_px - 44)
            ctx.line_to(w, horizon_px - 12)
            ctx.line_to(w, horizon_px)
            ctx.close_path()
            ctx.set_source_rgb(0.18, 0.16, 0.14)
            ctx.fill()
            ctx.restore()
        elif feat == "CITY_SKYLINE":
            ctx.save()
            ctx.set_source_rgb(0.24, 0.26, 0.30)
            for i in range(16):
                bx = i * (w / 16.0)
                bw = (w / 16.0) * 0.85
                bh = 20.0 + ((i * 37) % 45)
                ctx.rectangle(bx, horizon_px - bh, bw, bh)
                ctx.fill()
            ctx.restore()
        elif feat == "HILLS":
            ctx.save()
            ctx.move_to(0, horizon_px)
            ctx.curve_to(w * 0.3, horizon_px - 60, w * 0.7, horizon_px - 40, w, horizon_px)
            ctx.line_to(w, horizon_px)
            ctx.close_path()
            ctx.set_source_rgb(0.32, 0.36, 0.30)
            ctx.fill()
            ctx.restore()

    def _render_bg(
        self,
        ctx: cairo.Context,
        loc: LocationDNA,
        bp: SceneBlueprint,
        horizon_px: float,
        vp_x: float,
        vp_y: float,
        lighting: WorldLightingEngine,
    ) -> None:
        w, h = self.width, self.height
        is_interior = loc.enclosure.upper() == "INTERIOR"
        palette = loc.palette

        wall_col = hex_to_rgb(palette.get("wall", "#8c7e6c"))
        accent_col = hex_to_rgb(palette.get("accent", "#c69248"))

        # Ceiling beams / vaults for interior
        ceiling = loc.ceiling.upper()
        if ceiling in ("BEAMED", "VAULTED"):
            ctx.save()
            ctx.set_source_rgb(0.18, 0.12, 0.08)
            ctx.set_line_width(18.0)
            beams = 6
            for i in range(beams + 1):
                bx = i * (w / beams)
                ctx.move_to(vp_x, vp_y * 0.35)
                ctx.line_to(bx, 0)
                ctx.stroke()
            ctx.restore()

        # Wall treatment
        wt = loc.wall_treatment.upper()
        if wt == "WAINSCOT" and is_interior:
            dado_h = horizon_px * 0.40
            dado_y = horizon_px - dado_h

            # Upper plaster
            ctx.rectangle(0, 0, w, dado_y)
            ctx.set_source_rgb(*wall_col)
            ctx.fill()
            MaterialSystem.apply_stone_stipple(ctx, 0, 0, w, dado_y, seed=101, count=40)

            # Lower wood / panel wainscot
            ctx.rectangle(0, dado_y, w, dado_h)
            ctx.set_source_rgb(wall_col[0] * 0.6, wall_col[1] * 0.6, wall_col[2] * 0.6)
            ctx.fill()

            # Molding rail
            ctx.rectangle(0, dado_y - 4, w, 8)
            ctx.set_source_rgb(*accent_col)
            ctx.fill()

        elif wt == "TIMBER_REVETMENT":
            # Timber revetment wall on one flank
            revet_w = w * 0.38
            ctx.rectangle(w - revet_w, horizon_px * 0.8, revet_w, h)
            ctx.set_source_rgb(0.32, 0.24, 0.16)
            ctx.fill()
            MaterialSystem.apply_wood_grain(ctx, w - revet_w, horizon_px * 0.8, revet_w, h, seed=404)

        elif wt == "BRICK":
            ctx.rectangle(0, 0, w, horizon_px)
            ctx.set_source_rgb(0.55, 0.32, 0.24)
            ctx.fill()
            MaterialSystem.apply_stone_stipple(ctx, 0, 0, w, horizon_px, seed=202, count=60)

        # Openings (Windows)
        openings = loc.openings.upper()
        if openings == "WINDOWS_TALL":
            win_reg = self.assets._registry.get("prussian_casement_window_01")
            if win_reg and win_reg.render_func:
                win_reg.render_func(ctx, x=w * 0.12, y=h * 0.08, width=220, height=440, scale=1.0, light_shaft=True, lighting_dx=lighting.key_dx)
                win_reg.render_func(ctx, x=w * 0.40, y=h * 0.12, width=170, height=360, scale=0.85, light_shaft=False, lighting_dx=lighting.key_dx)

    def _render_mg(
        self,
        ctx: cairo.Context,
        loc: LocationDNA,
        bp: SceneBlueprint,
        horizon_px: float,
        vp_x: float,
        vp_y: float,
        lighting: WorldLightingEngine,
    ) -> None:
        w, h = self.width, self.height
        palette = loc.palette
        floor_col = hex_to_rgb(palette.get("floor", "#4a3c2c"))

        # Base floor rectangle
        ctx.rectangle(0, horizon_px, w, h - horizon_px)
        ctx.set_source_rgb(*floor_col)
        ctx.fill()

        # Floor features
        ff = loc.floor_feature.upper()
        if ff == "PLANKS":
            planks = 16
            ctx.set_source_rgba(0.08, 0.08, 0.10, 0.40)
            ctx.set_line_width(2.0)
            for i in range(planks + 1):
                tx = i * (w / planks)
                ctx.move_to(vp_x, vp_y)
                ctx.line_to(tx, h)
                ctx.stroke()
        elif ff == "COBBLES":
            MaterialSystem.apply_stone_stipple(ctx, 0, horizon_px, w, h - horizon_px, seed=303, count=120)
        elif ff == "DUCKBOARD_PATH":
            MaterialSystem.apply_mud_squelch(ctx, 0, horizon_px, w, h - horizon_px, seed=505)
            # Slat path
            for i in range(24):
                t = (i / 24.0) ** 1.6
                sy = horizon_px + (1.0 - t) * (h - horizon_px)
                sw = 80.0 + t * 450.0
                sh = max(4.0, t * 15.0)
                cx = vp_x + t * (w * 0.5 - vp_x)
                ControlledIrregularityEngine.draw_irregular_rect(
                    ctx, cx - sw * 0.5, sy, sw, sh,
                    roughness=0.6,
                    fill_color=(0.38, 0.30, 0.20),
                    stroke_color=(0.08, 0.08, 0.10),
                    stroke_width=1.5,
                )

        # Midground Props from Blueprint with safe keyword dispatch & state awareness
        for p in bp.props:
            if p.depth_plane in ("MG", "BG"):
                reg = self.assets._registry.get(p.asset_id)
                px = p.screen_x * w
                py = horizon_px + (h - horizon_px) * p.depth
                _safe_render_prop(reg, ctx, x=px, y=py, scale=0.9, lighting_dx=lighting.key_dx, state=getattr(p, "state", "ACTIVE"))

    def _render_fg(
        self,
        ctx: cairo.Context,
        loc: LocationDNA,
        bp: SceneBlueprint,
        horizon_px: float,
        vp_x: float,
        vp_y: float,
        lighting: WorldLightingEngine,
    ) -> None:
        w, h = self.width, self.height

        # Render foreground props from blueprint with authentic materials and state
        for p in bp.props:
            if p.depth_plane == "FG":
                reg = self.assets._registry.get(p.asset_id)
                px = p.screen_x * w
                py = horizon_px + (h - horizon_px) * p.depth
                _safe_render_prop(reg, ctx, x=px, y=py, scale=1.15, lighting_dx=lighting.key_dx, state=getattr(p, "state", "ACTIVE"))

        # Foreground edge framing post if indicated
        if loc.foreground_vocabulary and not bp.foreground_element:
            ctx.save()
            ControlledIrregularityEngine.draw_irregular_rect(
                ctx, -25, h * 0.35, 95, h * 0.70,
                roughness=0.8,
                fill_color=(0.20, 0.16, 0.12),
                stroke_color=(0.06, 0.06, 0.08),
                stroke_width=3.0,
            )
            MaterialSystem.apply_wood_grain(ctx, -25, h * 0.35, 95, h * 0.70, seed=606, density=5)
            ctx.restore()

    def _render_near_fg(
        self,
        ctx: cairo.Context,
        loc: LocationDNA,
        bp: SceneBlueprint,
        horizon_px: float,
        lighting: WorldLightingEngine,
    ) -> None:
        w, h = self.width, self.height
        weather = loc.weather.upper()
        atmo = str(loc.atmosphere).upper()

        # Rain
        if weather == "RAIN" or "RAIN" in atmo:
            ctx.save()
            ctx.set_source_rgba(0.85, 0.90, 0.98, 0.22)
            ctx.set_line_width(1.2)
            for i in range(180):
                rx = (i * 53) % w
                ry = (i * 37) % h
                ctx.move_to(rx, ry)
                ctx.line_to(rx - 12, ry + 22)
                ctx.stroke()
            ctx.restore()

        # Atmospheric dust motes / steam / embers
        if any(k in atmo for k in ("DUST", "FOG", "MIST", "STEAM", "EMBERS", "SMOKE")):
            ctx.save()
            for i in range(45):
                dx = (i * 97 + 31) % w
                dy = (i * 73 + 19) % h
                rad = 1.5 + (i % 3) * 0.8
                alpha = 0.15 + (i % 5) * 0.06
                if "EMBERS" in atmo:
                    ctx.set_source_rgba(0.95, 0.55, 0.18, alpha)
                elif "STEAM" in atmo or "FOG" in atmo:
                    ctx.set_source_rgba(0.90, 0.92, 0.95, alpha * 0.6)
                else:
                    ctx.set_source_rgba(0.95, 0.92, 0.82, alpha)
                ctx.arc(dx, dy, rad, 0, math.tau)
                ctx.fill()
            ctx.restore()

        # Vignette
        ctx.save()
        max_r = math.hypot(w * 0.5, h * 0.5)
        v_grad = cairo.RadialGradient(w * 0.5, h * 0.5, max_r * 0.48, w * 0.5, h * 0.5, max_r)
        v_grad.add_color_stop_rgba(0.0, 0.0, 0.0, 0.0, 0.0)
        v_grad.add_color_stop_rgba(0.7, 0.0, 0.0, 0.0, 0.18)
        v_grad.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.42)
        ctx.rectangle(0, 0, w, h)
        ctx.set_source(v_grad)
        ctx.fill()
        ctx.restore()
