"""General Cinematic Environment Engine (Master World Renderer).

Implements the unified Track B target pipeline:
SceneBlueprint
  ↓
LocationVisualDNA
  ↓
Cinematic Composition & Asymmetry
  ↓
Perspective Layout (1-Point, 2-Point, Deep Corridor, Ground Level, High Angle)
  ↓
Environment Asset Resolver
  ↓
Illustrated SVG Assets & Controlled Irregularity
  ↓
Material System (Wood, Metal, Stone, Plaster, Fabric, Glass, Paper, Mud, Earth)
  ↓
Environmental Storytelling (Used, Damaged, Wet, Scattered, Tilted)
  ↓
5-Point Lighting (Key, Fill, Rim, Shadow Zones, Atmospheric)
  ↓
Multi-Plane Depth (NEAR_FG, FG, MG, BG, FAR_BG)
  ↓
Environment Render Layers
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any
import cairo

from .location_dna import LocationVisualDNA, get_location_dna
from .materials import MaterialSystem, MaterialType
from .composition import CinematicCompositionEngine, DepthPlane
from .lighting import WorldLightingEngine
from .storytelling import EnvironmentalStorytelling
from .svg_assets import IllustratedAssetResolver
from .rough_path import ControlledIrregularityEngine
from ..scene_builder.blueprint import SceneBlueprint


class GeneralWorldEngine:
    """Master cinematic environment engine rendering multi-plane illustrated worlds."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height
        self.composition = CinematicCompositionEngine(width, height)
        self.assets = IllustratedAssetResolver()

    def render_environment_only(self, bp: SceneBlueprint) -> cairo.ImageSurface:
        """Renders complete 5-plane environment without actor layers."""
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        ctx = cairo.Context(surf)

        dna = get_location_dna(bp.history.location_id)
        lighting = WorldLightingEngine(bp.lighting, bp.atmosphere)
        story_mods = EnvironmentalStorytelling.resolve_prop_modifiers(bp)

        # 1. FAR_BG Plane (Sky, horizon silhouette, distant landmarks)
        self._render_far_bg(ctx, bp, dna, lighting)

        # 2. BG Plane (Back walls, distant architecture, parapets)
        self._render_bg(ctx, bp, dna, lighting, story_mods)

        # 3. MG Plane (Walkways, floorboards, primary illustrated furniture & props)
        self._render_mg(ctx, bp, dna, lighting, story_mods)

        # 4. FG Plane (Foreground framing structures, camera-near occluders)
        self._render_fg(ctx, bp, dna, lighting, story_mods)

        # 5. NEAR_FG Plane & FX (Edge silhouettes, smoke, rain, volumetric light, vignette)
        self._render_near_fg_and_fx(ctx, bp, dna, lighting)

        return surf

    def render_composite_with_actor(
        self,
        bp: SceneBlueprint,
        actor_render_callback: Any | None = None,
    ) -> cairo.ImageSurface:
        """Renders full cinematic composite: Environment + Actor + Lighting + Foreground Occluders."""
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        ctx = cairo.Context(surf)

        dna = get_location_dna(bp.history.location_id)
        lighting = WorldLightingEngine(bp.lighting, bp.atmosphere)
        story_mods = EnvironmentalStorytelling.resolve_prop_modifiers(bp)

        # 1. Background planes
        self._render_far_bg(ctx, bp, dna, lighting)
        self._render_bg(ctx, bp, dna, lighting, story_mods)
        self._render_mg(ctx, bp, dna, lighting, story_mods)

        # 2. Actor Staging Handshake (Consumed separately from Track A / Actor Rig)
        if actor_render_callback:
            actor_render_callback(ctx, bp)

        # 3. Foreground Framing (Occludes actor partially when camera is positioned inside environment)
        self._render_fg(ctx, bp, dna, lighting, story_mods)

        # 4. Near foreground & Atmospheric FX
        self._render_near_fg_and_fx(ctx, bp, dna, lighting)

        # 5. Story Focus Contrast Shaping
        focus_x = bp.character.approximate_position[0] * self.width
        focus_y = bp.camera.horizon_y * self.height + 150.0
        lighting.apply_story_focus_contrast(ctx, self.width, self.height, focus_x, focus_y)

        return surf

    # ==========================================================================
    # INTERNAL MULTI-PLANE RENDER STAGES
    # ==========================================================================

    def _render_far_bg(
        self,
        ctx: cairo.Context,
        bp: SceneBlueprint,
        dna: LocationVisualDNA,
        lighting: WorldLightingEngine,
    ) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h
        p = dna.palette

        # Atmospheric base sky/wall gradient
        sky_grad = cairo.LinearGradient(0, 0, 0, horizon_px)
        sky_grad.add_color_stop_rgb(0.0, *p["ambient_top"])
        sky_grad.add_color_stop_rgb(1.0, *p["ambient_bot"])
        ctx.rectangle(0, 0, w, horizon_px)
        ctx.set_source(sky_grad)
        ctx.fill()

        # Specific Far Background elements based on DNA
        if dna.dna_id == "WWI_TRENCH":
            # Distant shattered battlefield horizon ridge
            ctx.save()
            ctx.move_to(0, horizon_px)
            ctx.line_to(w * 0.22, horizon_px - 38)
            ctx.line_to(w * 0.45, horizon_px - 22)
            ctx.line_to(w * 0.72, horizon_px - 48)
            ctx.line_to(w, horizon_px - 16)
            ctx.line_to(w, horizon_px)
            ctx.close_path()
            ctx.set_source_rgb(0.20, 0.18, 0.16)
            ctx.fill()

            # Shattered tree silhouettes on horizon
            ctx.set_source_rgb(0.12, 0.10, 0.10)
            ctx.set_line_width(3.2)
            for tx in [w * 0.14, w * 0.36, w * 0.68, w * 0.86]:
                ctx.move_to(tx, horizon_px - 12)
                ctx.line_to(tx - 5, horizon_px - 72)
                ctx.line_to(tx + 4, horizon_px - 80)
                ctx.stroke()

            # Distant barbed wire on horizon crest
            barb_asset = self.assets.get("barbed_wire_concertina_01")
            if barb_asset:
                pts = [
                    (w * 0.05, horizon_px - 18),
                    (w * 0.35, horizon_px - 24),
                    (w * 0.65, horizon_px - 20),
                    (w * 0.95, horizon_px - 26),
                ]
                barb_asset.render_func(ctx, pts, post_count=5, scale=0.7, lighting_dx=lighting.key_dx)
            ctx.restore()

        elif dna.dna_id == "BEER_HALL":
            # Deep atmospheric interior haze gradient
            lighting.apply_directional_ambient_pass(ctx, w, h, horizon_px)

    def _render_bg(
        self,
        ctx: cairo.Context,
        bp: SceneBlueprint,
        dna: LocationVisualDNA,
        lighting: WorldLightingEngine,
        story_mods: list[Any],
    ) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h
        vp_x, vp_y = self.composition.compute_asymmetric_vanishing_point(bp)

        if dna.dna_id == "MILITARY_HOSPITAL":
            # Plaster wall with wainscoting dado
            dado_h = horizon_px * 0.38
            dado_y = horizon_px - dado_h

            # Distressed plaster upper wall
            ctx.rectangle(0, 0, w, dado_y)
            ctx.set_source_rgb(0.92, 0.93, 0.94)
            ctx.fill()
            MaterialSystem.apply_stone_stipple(ctx, 0, 0, w, dado_y, seed=701, count=60)

            # Enameled clinical wainscoting dado
            ctx.rectangle(0, dado_y, w, dado_h)
            ctx.set_source_rgb(0.55, 0.60, 0.64)  # Sanitized gray-blue enamel
            ctx.fill()

            # Chair rail molding
            ctx.rectangle(0, dado_y - 6, w, 12)
            ctx.set_source_rgb(0.38, 0.42, 0.46)
            ctx.fill()

            # 2 Illustrated Prussian Casement Windows
            win_asset = self.assets.get("prussian_casement_window_01")
            if win_asset:
                # Main illuminating window with sunbeam
                win_asset.render_func(
                    ctx, x=w * 0.10, y=h * 0.06, width=240, height=480,
                    scale=1.0, light_shaft=True, lighting_dx=lighting.key_dx
                )
                # Distant background window
                win_asset.render_func(
                    ctx, x=w * 0.38, y=h * 0.10, width=180, height=390,
                    scale=0.9, light_shaft=False, lighting_dx=lighting.key_dx
                )

        elif dna.dna_id == "BEER_HALL":
            # Dark paneled wainscoting
            ctx.rectangle(0, horizon_px * 0.45, w, horizon_px * 0.55)
            ctx.set_source_rgb(0.28, 0.18, 0.10)
            ctx.fill()

            # Vaulted timber ceiling beams converging to vanishing point
            ctx.save()
            ctx.set_source_rgb(0.18, 0.10, 0.06)
            ctx.set_line_width(22.0)
            beam_count = 7
            for i in range(beam_count + 1):
                tx = i * (w / beam_count)
                ctx.move_to(vp_x, vp_y * 0.35)
                ctx.line_to(tx, 0)
                ctx.stroke()
            ctx.restore()

            # Stacked oak beer barrels against back wall
            barrel_asset = self.assets.get("beer_barrel_stack_01")
            if barrel_asset:
                barrel_asset.render_func(ctx, x=w * 0.70, y=horizon_px + 8, scale=1.1, stack_count=4, lighting_dx=lighting.key_dx)

        elif dna.dna_id == "WWI_TRENCH":
            # Parapet sandbag fortification across trench crest
            sandbag_asset = self.assets.get("sandbag_fortification_01")
            if sandbag_asset:
                sandbag_y = max(0.0, horizon_px - 105.0)
                sandbag_asset.render_func(ctx, 0, sandbag_y, w, 120.0, scale=1.0, layers=5, bags_per_layer=14, lighting_dx=lighting.key_dx)

    def _render_mg(
        self,
        ctx: cairo.Context,
        bp: SceneBlueprint,
        dna: LocationVisualDNA,
        lighting: WorldLightingEngine,
        story_mods: list[Any],
    ) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h
        vp_x, vp_y = self.composition.compute_asymmetric_vanishing_point(bp)

        if dna.dna_id == "MILITARY_HOSPITAL":
            # Perspective floorboards converging to vanishing point
            floor_h = h - horizon_px
            ctx.rectangle(0, horizon_px, w, floor_h)
            ctx.set_source_rgb(0.56, 0.52, 0.46)
            ctx.fill()

            # Floor plank joints
            planks = 18
            ctx.set_source_rgba(0.08, 0.06, 0.05, 0.45)
            ctx.set_line_width(2.0)
            for i in range(planks + 1):
                tx = i * (w / planks)
                ctx.move_to(vp_x, vp_y)
                ctx.line_to(tx, h)
                ctx.stroke()

            # Distant hospital bed
            bed_asset = self.assets.get("hospital_bed_iron_01")
            if bed_asset:
                bed_asset.render_func(ctx, x=w * 0.46, y=horizon_px + 35, scale=0.72, variant="EMPTY", lighting_dx=lighting.key_dx)

            # Midground Hospital Bed (Focal bed)
            rx = bp.composition.character_reserved_zone.x * w
            if bed_asset:
                bed_asset.render_func(ctx, x=rx - 120, y=h * 0.60, scale=1.18, variant="OCCUPIED_BANDAGE", lighting_dx=lighting.key_dx)

            # Bedside clinical medicine table
            med_asset = self.assets.get("medicine_table_enamel_01")
            if med_asset:
                med_asset.render_func(ctx, x=rx + 265, y=h * 0.63, scale=1.1, lighting_dx=lighting.key_dx)

        elif dna.dna_id == "BEER_HALL":
            # Floorboards
            ctx.rectangle(0, horizon_px, w, h - horizon_px)
            ctx.set_source_rgb(0.40, 0.28, 0.18)
            ctx.fill()

            # Hanging brass chandeliers with amber halos
            chan_asset = self.assets.get("brass_chandelier_01")
            if chan_asset:
                chan_asset.render_func(ctx, x=w * 0.25, y=h * 0.22, scale=1.3, lighting_dx=lighting.key_dx)
                chan_asset.render_func(ctx, x=w * 0.75, y=h * 0.22, scale=1.3, lighting_dx=lighting.key_dx)

            # Midground heavy oak tavern tables with Keferloher steins
            table_asset = self.assets.get("tavern_table_oak_01")
            if table_asset:
                table_asset.render_func(ctx, x=w * 0.12, y=h * 0.56, width=380, height=160, scale=1.0, stein_count=4, lighting_dx=lighting.key_dx)
                table_asset.render_func(ctx, x=w * 0.54, y=h * 0.56, width=380, height=160, scale=1.0, stein_count=4, lighting_dx=lighting.key_dx)

        elif dna.dna_id == "WWI_TRENCH":
            # Mud floor and duckboard corridor converging into vanishing point
            cam_h = bp.camera.height.upper()
            slat_count = 34 if "GROUND" in cam_h else 28
            w_near = 780.0 if "GROUND" in cam_h else 480.0

            # Mud base
            ctx.rectangle(0, horizon_px, w, h - horizon_px)
            ctx.set_source_rgb(0.24, 0.19, 0.14)
            ctx.fill()

            # Wet mud squelch texture
            MaterialSystem.apply_mud_squelch(ctx, 0, horizon_px, w, h - horizon_px, seed=808)

            # Timber revetment on right bank
            revet_asset = self.assets.get("trench_timber_revetment_01")
            if revet_asset:
                revet_asset.render_func(ctx, x=w * 0.60, y=horizon_px * 0.85, width=w * 0.40, height=h - horizon_px * 0.85, scale=1.0, damage=0.35, lighting_dx=lighting.key_dx)

            # Duckboard wooden slats converging into distance
            wood_col = (0.40, 0.32, 0.22)
            ctx.save()
            for i in range(slat_count):
                t = (i / slat_count) ** 1.75
                sy = horizon_px + (1.0 - t) * (h - horizon_px)
                sw = 75.0 + t * (w_near - 75.0)
                sh = max(4.0, t * 16.0)
                cx = vp_x + t * (w * 0.48 - vp_x)
                sx = cx - sw * 0.5

                # Slat shadow in mud
                ctx.rectangle(sx + 4, sy + sh, sw, sh * 0.5)
                ctx.set_source_rgba(0.04, 0.04, 0.04, 0.60)
                ctx.fill()

                # Slat wood plank
                ControlledIrregularityEngine.draw_irregular_rect(
                    ctx, sx, sy, sw, sh, roughness=0.6,
                    fill_color=(wood_col[0] * (0.8 + t * 0.3), wood_col[1] * (0.8 + t * 0.3), wood_col[2] * (0.8 + t * 0.3)),
                    stroke_color=(0.08, 0.08, 0.10),
                    stroke_width=max(1.2, t * 2.2),
                )
            ctx.restore()

            # Ammo crate stack against revetment
            crate_asset = self.assets.get("ammo_crate_stack_01")
            if crate_asset:
                crate_asset.render_func(ctx, x=w * 0.66, y=h * 0.88, scale=1.1, crate_count=3, lighting_dx=lighting.key_dx)

            # Wet puddle in trench floor
            puddle_x = w * 0.28
            puddle_y = h * 0.84
            ctx.save()
            ctx.translate(puddle_x, puddle_y)
            ctx.scale(1.0, 0.28)
            ctx.arc(0, 0, 95.0, 0, math.tau)
            p_grad = cairo.RadialGradient(0, -25, 10, 0, 0, 95)
            p_grad.add_color_stop_rgb(0.0, 0.70, 0.74, 0.82)
            p_grad.add_color_stop_rgb(0.7, 0.55, 0.60, 0.68)
            p_grad.add_color_stop_rgb(1.0, 0.18, 0.14, 0.10)
            ctx.set_source(p_grad)
            ctx.fill_preserve()
            ctx.set_source_rgb(0.08, 0.08, 0.10)
            ctx.set_line_width(2.0)
            ctx.stroke()
            ctx.restore()

    def _render_fg(
        self,
        ctx: cairo.Context,
        bp: SceneBlueprint,
        dna: LocationVisualDNA,
        lighting: WorldLightingEngine,
        story_mods: list[Any],
    ) -> None:
        w, h = self.width, self.height
        shot_size = bp.camera.shot_size.upper()

        # 1. Hospital OTS Foreground Doctor Silhouette
        if dna.dna_id == "MILITARY_HOSPITAL" and "OTS" in shot_size:
            ctx.save()
            doc_x = w * 0.18
            doc_y = h * 0.68
            # Dark clinical lab coat silhouette
            ctx.move_to(-30, h + 20)
            ctx.line_to(-30, doc_y + 110)
            ctx.curve_to(doc_x - 95, doc_y + 40, doc_x - 35, doc_y - 20, doc_x, doc_y)
            # Head & collar
            ctx.arc(doc_x + 10, doc_y - 68, 46, math.pi * 0.8, math.pi * 1.8)
            ctx.curve_to(doc_x + 90, doc_y + 35, doc_x + 135, doc_y + 120, doc_x + 160, h + 20)
            ctx.close_path()

            # Deep rich charcoal coat with subtle texture
            ctx.set_source_rgb(0.12, 0.14, 0.16)
            ctx.fill_preserve()
            ctx.set_source_rgb(0.06, 0.07, 0.09)
            ctx.set_line_width(3.5)
            ctx.stroke()

            # Delicate secondary rim light highlight on edge facing the window
            lighting.apply_rim_light_to_path(
                ctx,
                [(doc_x + 10, doc_y - 114), (doc_x + 48, doc_y - 68), (doc_x + 65, doc_y), (doc_x + 135, doc_y + 120)],
                stroke_width=2.5,
            )
            ctx.restore()

        # 2. Beer Hall Foreground Cropped Table
        elif dna.dna_id == "BEER_HALL":
            table_asset = self.assets.get("tavern_table_oak_01")
            if table_asset:
                # Foreground table bleeding off right bottom edge
                table_asset.render_func(ctx, x=w * 0.64, y=h * 0.80, width=440, height=200, scale=1.2, stein_count=3, lighting_dx=lighting.key_dx)

        # 3. Trench Foreground Framing Timber Post
        elif dna.dna_id == "WWI_TRENCH":
            # Rough split-log post in left corner bleeding off-canvas
            ctx.save()
            ControlledIrregularityEngine.draw_irregular_rect(
                ctx, -35, h * 0.32, 115, h * 0.72,
                roughness=0.9,
                fill_color=(0.24, 0.18, 0.12),
                stroke_color=(0.06, 0.06, 0.08),
                stroke_width=3.5,
            )
            MaterialSystem.apply_wood_grain(ctx, -35, h * 0.32, 115, h * 0.72, seed=909, density=6)

            # Barb wire cluster on corner post
            ctx.arc(60, h * 0.52, 12, 0, math.tau)
            ctx.set_source_rgb(0.20, 0.22, 0.24)
            ctx.set_line_width(2.5)
            ctx.stroke()
            ctx.restore()

    def _render_near_fg_and_fx(
        self,
        ctx: cairo.Context,
        bp: SceneBlueprint,
        dna: LocationVisualDNA,
        lighting: WorldLightingEngine,
    ) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h

        if dna.dna_id == "WWI_TRENCH":
            # Rising smoke plumes from battlefield
            ctx.save()
            for i in range(8):
                t = i / 8.0
                py = horizon_px - t * 290
                px = w * 0.82 + t * 48 + math.sin(i * 1.8) * 18.0
                r = 20.0 + t * 48.0
                ctx.arc(px, py, r, 0, math.tau)
                ctx.set_source_rgba(0.32, 0.34, 0.38, 0.30 * (1.0 - t * 0.75))
                ctx.fill()
            ctx.restore()

            # Rain drizzle streaks and splashes
            ctx.save()
            ctx.set_source_rgba(0.85, 0.90, 0.98, 0.26)
            ctx.set_line_width(1.2)
            for i in range(240):
                rx = ((i * 47) % int(w + 200)) - 100
                ry = (i * 31) % int(h)
                ctx.move_to(rx, ry)
                ctx.line_to(rx - 15, ry + 24)
                ctx.stroke()
            ctx.restore()

        # Vignette to reinforce cinematic focus
        vignette_intensity = 0.35 if dna.dna_id == "MILITARY_HOSPITAL" else 0.48
        ctx.save()
        max_r = math.hypot(w * 0.5, h * 0.5)
        v_grad = cairo.RadialGradient(w * 0.5, h * 0.5, max_r * 0.45, w * 0.5, h * 0.5, max_r)
        v_grad.add_color_stop_rgba(0.0, 0.0, 0.0, 0.0, 0.0)
        v_grad.add_color_stop_rgba(0.7, 0.0, 0.0, 0.0, vignette_intensity * 0.4)
        v_grad.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, vignette_intensity)
        ctx.rectangle(0, 0, w, h)
        ctx.set_source(v_grad)
        ctx.fill()
        ctx.restore()
