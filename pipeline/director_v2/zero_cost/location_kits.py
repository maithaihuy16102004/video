"""Generic Location Kit System for Zero-Cost Procedural Visuals.

Provides generic visual vocabularies configured by SceneBlueprint:
- WWI_TRENCH_KIT
- MILITARY_HOSPITAL_KIT
- EARLY_1900S_EUROPEAN_STREET_KIT
- BEER_HALL_KIT

Each kit separates rendering into multi-plane depth passes:
- FAR_BG (Sky, distant horizon landmarks)
- BG (Main back walls, distant structures)
- MG (Walkways, floor, midground furniture & props)
- FG (Foreground framing occluders)
- FX (Atmospheric lighting, smoke, rain, volumetric shafts)
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any
import cairo

from .primitives import (
    draw_stone_column,
    draw_arched_loggia,
    draw_building_facade,
    draw_prussian_window,
    draw_timber_wall,
    draw_cobblestone_plane,
    draw_mud_duckboard_corridor,
    draw_puddle_reflection,
    draw_distressed_wood_floor,
    draw_sandbag_revetment,
    draw_barbed_wire_entanglement,
    draw_artillery_crater,
    draw_ammo_crate_stack,
    draw_hospital_bed,
    draw_tavern_table_and_steins,
    draw_hanging_brass_lantern,
    draw_wainscoting_wall,
    draw_light_shaft,
    draw_smoke_plumes,
    draw_ground_fog,
    draw_rain_and_drizzle,
    draw_vignette,
)
from .lighting_engine import CinematicLightingEngine
from ..scene_builder.blueprint import SceneBlueprint


class BaseLocationKit(ABC):
    """Base class for generic procedural location kits."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height
        self.s = min(width / 1920.0, height / 1080.0)

    @abstractmethod
    def render_far_bg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        pass

    @abstractmethod
    def render_bg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        pass

    @abstractmethod
    def render_mg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        pass

    @abstractmethod
    def render_fg_occluders(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        pass

    @abstractmethod
    def render_fx(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        pass


# ==============================================================================
# 1. WWI TRENCH LOCATION KIT
# ==============================================================================

class WWITrenchKit(BaseLocationKit):
    """Renders authentic Western Front trenches (Somme / Ypres / Verdun)."""

    def render_far_bg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h

        # Sullen overcast battlefield sky
        sky_colors = ((0.24, 0.28, 0.34), (0.64, 0.58, 0.52))
        ground_colors = ((0.32, 0.25, 0.18), (0.16, 0.12, 0.08))
        lighting.apply_sky_ground_base(ctx, w, h, horizon_px, sky_colors, ground_colors)

        # Distant no-man's-land shell-churned ridge & ruined trees
        ctx.save()
        ctx.move_to(0, horizon_px)
        ctx.line_to(w * 0.18, horizon_px - 32 * self.s)
        ctx.line_to(w * 0.42, horizon_px - 18 * self.s)
        ctx.line_to(w * 0.68, horizon_px - 44 * self.s)
        ctx.line_to(w, horizon_px - 12 * self.s)
        ctx.line_to(w, horizon_px)
        ctx.close_path()
        ctx.set_source_rgb(0.20, 0.18, 0.16)
        ctx.fill()

        # Shattered splintered tree trunks on horizon
        for tx in [w * 0.15, w * 0.38, w * 0.72, w * 0.88]:
            ctx.move_to(tx, horizon_px - 10 * self.s)
            ctx.line_to(tx - 4 * self.s, horizon_px - 65 * self.s)
            ctx.line_to(tx + 6 * self.s, horizon_px - 72 * self.s)
            ctx.set_source_rgb(0.12, 0.10, 0.10)
            ctx.set_line_width(3.0 * self.s)
            ctx.stroke()
        ctx.restore()

        # Distant barbed wire entanglements on horizon
        wire_pts = [
            (w * 0.05, horizon_px - 15 * self.s),
            (w * 0.35, horizon_px - 22 * self.s),
            (w * 0.65, horizon_px - 18 * self.s),
            (w * 0.95, horizon_px - 25 * self.s),
        ]
        draw_barbed_wire_entanglement(ctx, wire_pts, post_count=5, lighting_dx=lighting.get_lighting_dx())

    def render_bg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h

        # Parapet sandbag revetment across trench crest
        sandbag_y = max(0.0, horizon_px - 95.0 * self.s)
        draw_sandbag_revetment(
            ctx, 0, sandbag_y, w, 110.0 * self.s,
            layers=5, bags_per_layer=12, damage=0.3,
            lighting_dx=lighting.get_lighting_dx()
        )

        # Distant artillery crater in no-man's-land behind parapet
        draw_artillery_crater(
            ctx, w * 0.78, sandbag_y + 20 * self.s, 110.0 * self.s, 32.0 * self.s,
            mud_lip=14.0 * self.s, water_filled=True, lighting_dx=lighting.get_lighting_dx()
        )

    def render_mg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h
        vp_x = bp.perspective.primary_vp[0] * w
        vp_y = bp.perspective.primary_vp[1] * h

        # 1. Timber revetment wall on the right or left side depending on depth axis
        if "RIGHT" in bp.perspective.depth_axis or bp.perspective.primary_vp[0] > 0.5:
            # Trench timber wall on right bank
            draw_timber_wall(
                ctx, w * 0.62, horizon_px * 0.85, w * 0.38, h - horizon_px * 0.85,
                planks=9, damage=0.25, lighting_dx=lighting.get_lighting_dx()
            )
            # Ammo crates stacked against right wall
            draw_ammo_crate_stack(
                ctx, w * 0.68, h * 0.88, scale=1.1 * self.s, crate_count=3,
                lighting_dx=lighting.get_lighting_dx()
            )
        else:
            # Trench timber wall on left bank
            draw_timber_wall(
                ctx, 0, horizon_px * 0.85, w * 0.38, h - horizon_px * 0.85,
                planks=9, damage=0.25, lighting_dx=lighting.get_lighting_dx()
            )
            draw_ammo_crate_stack(
                ctx, w * 0.12, h * 0.88, scale=1.1 * self.s, crate_count=3,
                lighting_dx=lighting.get_lighting_dx()
            )

        # 2. Mud duckboard corridor converging into primary vanishing point
        cam_h = bp.camera.height.upper()
        if "HIGH" in cam_h:
            # High angle view: zig-zag traverse seen from above
            draw_mud_duckboard_corridor(
                ctx, x1=w * 0.5, y1=h, x2=vp_x, y2=vp_y,
                vp_x=vp_x, vp_y=vp_y, width_near=520.0 * self.s, width_far=85.0 * self.s,
                slat_count=32, lighting_dx=lighting.get_lighting_dx()
            )
        elif "GROUND" in cam_h:
            # Ground level deep perspective: camera sits right on the mud duckboard
            draw_mud_duckboard_corridor(
                ctx, x1=w * 0.45, y1=h, x2=vp_x, y2=vp_y,
                vp_x=vp_x, vp_y=vp_y, width_near=750.0 * self.s, width_far=65.0 * self.s,
                slat_count=36, lighting_dx=lighting.get_lighting_dx()
            )
        else:
            draw_mud_duckboard_corridor(
                ctx, x1=w * 0.48, y1=h, x2=vp_x, y2=vp_y,
                vp_x=vp_x, vp_y=vp_y, width_near=460.0 * self.s, width_far=70.0 * self.s,
                slat_count=26, lighting_dx=lighting.get_lighting_dx()
            )

        # 3. Muddy trench water puddle in foreground
        draw_puddle_reflection(
            ctx, w * 0.28, h * 0.84, 85.0 * self.s, 24.0 * self.s,
            sky_color=(0.60, 0.65, 0.72)
        )

    def render_fg_occluders(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height

        # Foreground timber post / sandbag corner framing the edge (depth through occlusion)
        if bp.composition.foreground_occlusion > 0.1:
            ctx.save()
            # Foreground rough post in left corner
            ctx.rectangle(-20 * self.s, h * 0.35, 110 * self.s, h * 0.68)
            ctx.set_source_rgb(0.24, 0.18, 0.12)
            ctx.fill_preserve()
            ctx.set_source_rgb(0.06, 0.06, 0.08)
            ctx.set_line_width(3.0 * self.s)
            ctx.stroke()
            ctx.restore()

    def render_fx(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height

        # Artillery smoke plumes on horizon
        draw_smoke_plumes(
            ctx, w * 0.82, bp.camera.horizon_y * h, height=280.0 * self.s,
            plume_count=8, drift_dx=45.0 * self.s
        )

        # Low-lying trench ground fog / mist
        draw_ground_fog(ctx, h * 0.65, h * 0.35, w, color_rgba=(0.72, 0.76, 0.80, 0.28))

        # Rain drizzle if weather indicates
        if "DRIZZLE" in bp.atmosphere.weather.upper() or "RAIN" in bp.atmosphere.weather.upper() or True:
            draw_rain_and_drizzle(ctx, w, h, density=220, wind_dx=-16.0 * self.s, splash_y=h * 0.82)

        # Vignette
        draw_vignette(ctx, w, h, intensity=0.45)


# ==============================================================================
# 2. MILITARY HOSPITAL LOCATION KIT
# ==============================================================================

class MilitaryHospitalKit(BaseLocationKit):
    """Renders Pasewalk / military convalescence hospital wards."""

    def render_far_bg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h

        # Calm, clinical plaster wall tone with cold daylight
        wall_grad = cairo.LinearGradient(0, 0, 0, horizon_px)
        wall_grad.add_color_stop_rgb(0.0, 0.88, 0.90, 0.92)
        wall_grad.add_color_stop_rgb(1.0, 0.80, 0.82, 0.85)
        ctx.rectangle(0, 0, w, horizon_px)
        ctx.set_source(wall_grad)
        ctx.fill()

    def render_bg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h

        # Wainscoting dado along hospital back wall
        draw_wainscoting_wall(
            ctx, 0, 0, w, horizon_px,
            dado_fraction=0.35,
            wood_color=(0.58, 0.62, 0.65),  # Sanitized grayish-blue enamel hospital dado
            plaster_color=(0.92, 0.93, 0.94),
            lighting_dx=lighting.get_lighting_dx()
        )

        # Tall Prussian arched casement windows along side/back wall
        # Window 1 (Main light source casting sunbeam across ward)
        draw_prussian_window(
            ctx, x=w * 0.12, y=h * 0.08, width=220.0 * self.s, height=440.0 * self.s,
            arched=True, light_shaft=True, lighting_dx=lighting.get_lighting_dx(),
            wall_color=(0.92, 0.93, 0.94)
        )
        # Window 2 (Distant window)
        draw_prussian_window(
            ctx, x=w * 0.38, y=h * 0.12, width=170.0 * self.s, height=360.0 * self.s,
            arched=True, light_shaft=False, lighting_dx=lighting.get_lighting_dx(),
            wall_color=(0.92, 0.93, 0.94)
        )

        # Hospital pendulum wall clock
        clock_x = w * 0.84
        clock_y = h * 0.16
        ctx.save()
        ctx.rectangle(clock_x - 18 * self.s, clock_y - 25 * self.s, 36 * self.s, 85 * self.s)
        ctx.set_source_rgb(0.32, 0.22, 0.15)
        ctx.fill_preserve()
        ctx.set_source_rgb(0.1, 0.1, 0.12)
        ctx.set_line_width(2.0 * self.s)
        ctx.stroke()
        # Clock face
        ctx.arc(clock_x, clock_y, 14 * self.s, 0, math.tau)
        ctx.set_source_rgb(0.98, 0.97, 0.92)
        ctx.fill_preserve()
        ctx.stroke()
        ctx.restore()

    def render_mg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h
        vp_x = bp.perspective.primary_vp[0] * w
        vp_y = bp.perspective.primary_vp[1] * h

        # 1. Distressed perspective wooden floorboards
        draw_distressed_wood_floor(
            ctx, 0, horizon_px, w, h - horizon_px,
            vp_x=vp_x, vp_y=vp_y, planks=18,
            lighting_dx=lighting.get_lighting_dx(),
            floor_color=(0.58, 0.54, 0.48)
        )

        # 2. Rows of cast-iron hospital beds receding into perspective
        # Distant bed 1
        draw_hospital_bed(
            ctx, x=w * 0.48, y=horizon_px + 30 * self.s, width=180.0, height=95.0,
            scale=0.75 * self.s, lighting_dx=lighting.get_lighting_dx()
        )
        # Midground bed 2 (The protagonist's bed, aligned with reserved zone)
        rx = bp.composition.character_reserved_zone.x * w
        draw_hospital_bed(
            ctx, x=rx - 110.0 * self.s, y=h * 0.62, width=320.0, height=160.0,
            scale=1.15 * self.s, lighting_dx=lighting.get_lighting_dx()
        )

        # Bedside medical table with carbolic acid bottles & chart
        tab_x = rx + 240.0 * self.s
        tab_y = h * 0.66
        ctx.save()
        # White enamel table
        ctx.rectangle(tab_x, tab_y, 65 * self.s, 95 * self.s)
        ctx.set_source_rgb(0.92, 0.94, 0.96)
        ctx.fill_preserve()
        ctx.set_source_rgb(0.12, 0.14, 0.16)
        ctx.set_line_width(2.0 * self.s)
        ctx.stroke()
        # Brown apothecary medicine bottle
        ctx.rectangle(tab_x + 12 * self.s, tab_y - 24 * self.s, 14 * self.s, 24 * self.s)
        ctx.set_source_rgb(0.38, 0.22, 0.12)
        ctx.fill_preserve()
        ctx.stroke()
        # Clear glass cup
        ctx.rectangle(tab_x + 36 * self.s, tab_y - 18 * self.s, 12 * self.s, 18 * self.s)
        ctx.set_source_rgba(0.85, 0.92, 0.98, 0.85)
        ctx.fill_preserve()
        ctx.stroke()
        ctx.restore()

    def render_fg_occluders(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height

        # Over-The-Shoulder (OTS): Doctor / Orderly foreground silhouette framing the left third
        if "OTS" in bp.camera.shot_size.upper():
            ctx.save()
            # Head and broad shoulder back silhouette
            doc_x = w * 0.18
            doc_y = h * 0.68
            # Dark clinical lab coat silhouette
            ctx.move_to(-20, h + 20)
            ctx.line_to(-20, doc_y + 110 * self.s)
            ctx.curve_to(
                doc_x - 90 * self.s, doc_y + 40 * self.s,
                doc_x - 30 * self.s, doc_y - 20 * self.s,
                doc_x, doc_y
            )
            # Neck & back of head
            ctx.arc(doc_x + 10 * self.s, doc_y - 65 * self.s, 44 * self.s, math.pi * 0.8, math.pi * 1.8)
            # Right shoulder sloping down
            ctx.curve_to(
                doc_x + 85 * self.s, doc_y + 35 * self.s,
                doc_x + 130 * self.s, doc_y + 120 * self.s,
                doc_x + 150 * self.s, h + 20
            )
            ctx.close_path()

            # Deep dark charcoal doctor coat silhouette with subtle rim light on right edge
            ctx.set_source_rgb(0.12, 0.14, 0.17)
            ctx.fill_preserve()
            ctx.set_source_rgb(0.06, 0.07, 0.09)
            ctx.set_line_width(3.5 * self.s)
            ctx.stroke()

            # Soft rim light on doctor silhouette edge facing the window
            ctx.save()
            ctx.set_source_rgba(0.95, 0.97, 1.0, 0.35)
            ctx.set_line_width(2.5 * self.s)
            ctx.arc(doc_x + 10 * self.s, doc_y - 65 * self.s, 44 * self.s, math.pi * 0.8, math.pi * 1.4)
            ctx.stroke()
            ctx.restore()

            ctx.restore()

    def render_fx(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        # Subtle vignette to frame the clinical isolation
        draw_vignette(ctx, w, h, intensity=0.35)


# ==============================================================================
# 3. EARLY-1900S EUROPEAN STREET LOCATION KIT
# ==============================================================================

class Early1900sEuropeanStreetKit(BaseLocationKit):
    """Renders Munich Odeonsplatz / Berlin Unter den Linden / Vienna Ringstrasse."""

    def render_far_bg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h

        # Golden morning mobilization sky
        sky_colors = ((0.32, 0.54, 0.78), (0.96, 0.88, 0.72))
        ground_colors = ((0.48, 0.44, 0.40), (0.28, 0.25, 0.22))
        lighting.apply_sky_ground_base(ctx, w, h, horizon_px, sky_colors, ground_colors)

        # Distant Frauenkirche twin domed towers on horizon
        for tx, th in [(w * 0.68, 280 * self.s), (w * 0.75, 270 * self.s)]:
            tw = 65 * self.s
            ty = horizon_px - th
            ctx.rectangle(tx, ty, tw, th)
            ctx.set_source_rgb(0.68, 0.60, 0.52)
            ctx.fill_preserve()
            ctx.set_source_rgb(0.12, 0.12, 0.15)
            ctx.set_line_width(2.0 * self.s)
            ctx.stroke()
            # Green copper onion dome
            ctx.arc(tx + tw / 2.0, ty, tw * 0.52, math.pi, 0)
            ctx.set_source_rgb(0.28, 0.52, 0.44)
            ctx.fill_preserve()
            ctx.stroke()

    def render_bg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h

        # Neoclassical building facades (Odeonsplatz townhouses)
        draw_building_facade(
            ctx, x=w * 0.02, y=horizon_px - 440 * self.s, width=w * 0.44, height=450 * self.s,
            stories=3, bays=4, style="NEOCLASSICAL", lighting_dx=lighting.get_lighting_dx(),
            facade_color=(0.82, 0.78, 0.70)
        )

        # Feldherrnhalle classical arched loggia on the right
        draw_arched_loggia(
            ctx, x=w * 0.48, y=horizon_px - 480 * self.s, width=w * 0.50, height=490 * self.s,
            arch_count=2, depth_px=45.0 * self.s, lighting_dx=lighting.get_lighting_dx(),
            wall_color=(0.76, 0.72, 0.66)
        )

    def render_mg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h
        vp_x = bp.perspective.primary_vp[0] * w
        vp_y = bp.perspective.primary_vp[1] * h

        # 1. Perspective cobblestone plaza with Bavarian radial fan arches
        draw_cobblestone_plane(
            ctx, 0, horizon_px, w, h - horizon_px,
            horizon_y=bp.camera.horizon_y, vp_x=vp_x, vp_y=vp_y,
            density=28, wetness=0.4, lighting_dx=lighting.get_lighting_dx(),
            stone_color=(0.46, 0.43, 0.40)
        )

        # 2. Ornate wrought-iron gas street lamp
        lamp_x = w * 0.28
        lamp_y = h * 0.88
        ctx.save()
        # Lamp pole
        ctx.move_to(lamp_x, lamp_y)
        ctx.line_to(lamp_x, lamp_y - 280 * self.s)
        ctx.set_source_rgb(0.14, 0.15, 0.18)
        ctx.set_line_width(7.0 * self.s)
        ctx.stroke()
        # Ornate scroll brackets
        ctx.arc(lamp_x - 18 * self.s, lamp_y - 250 * self.s, 16 * self.s, 0, math.pi)
        ctx.stroke()
        # Hexagonal glass lantern head
        ctx.rectangle(lamp_x - 18 * self.s, lamp_y - 320 * self.s, 36 * self.s, 44 * self.s)
        ctx.set_source_rgb(0.98, 0.94, 0.75)
        ctx.fill_preserve()
        ctx.set_source_rgb(0.12, 0.12, 0.15)
        ctx.set_line_width(2.5 * self.s)
        ctx.stroke()
        ctx.restore()

        # 3. Bavarian blue and white mobilization rally banners hanging from loggia
        for bx in [w * 0.58, w * 0.78]:
            ctx.save()
            ctx.rectangle(bx, horizon_px - 220 * self.s, 44 * self.s, 140 * self.s)
            ctx.set_source_rgb(0.24, 0.52, 0.85)  # Bavarian royal blue
            ctx.fill_preserve()
            ctx.set_source_rgb(0.10, 0.10, 0.12)
            ctx.set_line_width(2.0 * self.s)
            ctx.stroke()
            # White diamond lozenge pattern
            ctx.move_to(bx + 22 * self.s, horizon_px - 200 * self.s)
            ctx.line_to(bx + 40 * self.s, horizon_px - 170 * self.s)
            ctx.line_to(bx + 22 * self.s, horizon_px - 140 * self.s)
            ctx.line_to(bx + 4 * self.s, horizon_px - 170 * self.s)
            ctx.close_path()
            ctx.set_source_rgb(0.96, 0.96, 0.98)
            ctx.fill()
            ctx.restore()

        # 4. War mobilization newspaper broadsheets (Extrablatt) scattered on cobblestones
        for px, py in [(w * 0.42, h * 0.82), (w * 0.62, h * 0.76)]:
            ctx.save()
            ctx.translate(px, py)
            ctx.rotate(0.22)
            ctx.rectangle(-22 * self.s, -14 * self.s, 44 * self.s, 28 * self.s)
            ctx.set_source_rgb(0.92, 0.90, 0.82)
            ctx.fill_preserve()
            ctx.set_source_rgb(0.12, 0.12, 0.14)
            ctx.set_line_width(1.2 * self.s)
            ctx.stroke()
            # Headline rule lines
            ctx.move_to(-16 * self.s, -6 * self.s)
            ctx.line_to(16 * self.s, -6 * self.s)
            ctx.stroke()
            ctx.restore()

    def render_fg_occluders(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height

        # Low-Angle Shot framing: Monumental Corinthian column plinth in the right foreground
        if "LOW" in bp.camera.height.upper() or bp.camera.pitch > 10.0:
            draw_stone_column(
                ctx, x=w * 0.86, y=h * 0.05, width=160.0 * self.s, height=h * 0.95,
                style="CORINTHIAN", lighting_dx=lighting.get_lighting_dx(),
                stone_color=(0.74, 0.70, 0.64)
            )

    def render_fx(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        # Radiant morning sunlight flare
        draw_vignette(ctx, w, h, intensity=0.32)


# ==============================================================================
# 4. BEER HALL / TAVERN LOCATION KIT
# ==============================================================================

class BeerHallKit(BaseLocationKit):
    """Renders Bürgerbräukeller / Hofbräuhaus Bavarian taverns."""

    def render_far_bg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h

        # Warm amber tavern interior glow
        bg_grad = cairo.LinearGradient(0, 0, 0, horizon_px)
        bg_grad.add_color_stop_rgb(0.0, 0.38, 0.24, 0.14)
        bg_grad.add_color_stop_rgb(1.0, 0.52, 0.35, 0.20)
        ctx.rectangle(0, 0, w, horizon_px)
        ctx.set_source(bg_grad)
        ctx.fill()

    def render_bg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h
        vp_x = bp.perspective.primary_vp[0] * w
        vp_y = bp.perspective.primary_vp[1] * h

        # 1. Dark paneled wainscoting along tavern back wall
        draw_wainscoting_wall(
            ctx, 0, 0, w, horizon_px,
            dado_fraction=0.45,
            wood_color=(0.32, 0.20, 0.12),
            plaster_color=(0.82, 0.74, 0.62),
            lighting_dx=lighting.get_lighting_dx()
        )

        # 2. Heavy vaulted ceiling timber beams converging to primary vanishing point
        beam_count = 6
        for i in range(beam_count + 1):
            target_x = i * (w / beam_count)
            ctx.move_to(vp_x, vp_y * 0.4)
            ctx.line_to(target_x, 0)
            ctx.set_source_rgb(0.22, 0.14, 0.08)
            ctx.set_line_width(18.0 * self.s)
            ctx.stroke()

        # 3. Stacked oak beer barrels against back wall
        barrel_y = horizon_px - 8.0 * self.s
        for b_idx in range(4):
            bx = w * 0.72 + b_idx * 55.0 * self.s
            bw = 48.0 * self.s
            bh = 65.0 * self.s
            ctx.save()
            # Oak barrel oval body
            ctx.translate(bx + bw / 2.0, barrel_y - bh / 2.0)
            ctx.scale(1.0, bh / bw)
            ctx.arc(0, 0, bw / 2.0, 0, math.tau)
            ctx.set_source_rgb(0.38, 0.26, 0.16)
            ctx.fill_preserve()
            ctx.set_source_rgb(0.1, 0.08, 0.06)
            ctx.set_line_width(2.0 * self.s)
            ctx.stroke()
            # Iron hoops
            ctx.arc(0, 0, bw * 0.42, 0, math.tau)
            ctx.stroke()
            ctx.restore()

    def render_mg(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        horizon_px = bp.camera.horizon_y * h
        vp_x = bp.perspective.primary_vp[0] * w
        vp_y = bp.perspective.primary_vp[1] * h

        # 1. Dark tavern plank floorboards
        draw_distressed_wood_floor(
            ctx, 0, horizon_px, w, h - horizon_px,
            vp_x=vp_x, vp_y=vp_y, planks=16,
            lighting_dx=lighting.get_lighting_dx(),
            floor_color=(0.42, 0.30, 0.20)
        )

        # 2. Hanging brass tavern chandeliers / lanterns with warm golden halos
        draw_hanging_brass_lantern(
            ctx, x=w * 0.25, y=h * 0.22, scale=1.3 * self.s,
            is_lit=True, glow_radius=180.0 * self.s, lighting_dx=lighting.get_lighting_dx()
        )
        draw_hanging_brass_lantern(
            ctx, x=w * 0.75, y=h * 0.22, scale=1.3 * self.s,
            is_lit=True, glow_radius=180.0 * self.s, lighting_dx=lighting.get_lighting_dx()
        )

        # 3. Long heavy oak tavern tables with beer steins
        # Midground table
        draw_tavern_table_and_steins(
            ctx, x=w * 0.15, y=h * 0.58, width=340.0 * self.s, height=140.0 * self.s,
            steins_count=4, lighting_dx=lighting.get_lighting_dx()
        )
        draw_tavern_table_and_steins(
            ctx, x=w * 0.55, y=h * 0.58, width=340.0 * self.s, height=140.0 * self.s,
            steins_count=4, lighting_dx=lighting.get_lighting_dx()
        )

    def render_fg_occluders(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height

        # Foreground crowd silhouettes / table edge framing bottom of screen
        ctx.save()
        # Foreground table edge on right corner
        draw_tavern_table_and_steins(
            ctx, x=w * 0.65, y=h * 0.82, width=420.0 * self.s, height=180.0 * self.s,
            steins_count=3, lighting_dx=lighting.get_lighting_dx()
        )
        ctx.restore()

    def render_fx(self, ctx: cairo.Context, bp: SceneBlueprint, lighting: CinematicLightingEngine) -> None:
        w, h = self.width, self.height
        # Warm golden tavern interior haze and rich vignette
        draw_vignette(ctx, w, h, intensity=0.48)


# ==============================================================================
# LOCATION KIT RESOLVER FACTORY
# ==============================================================================

def get_location_kit(location_id: str, width: int = 1920, height: int = 1080) -> BaseLocationKit:
    """Factory function resolving the appropriate generic LocationKit for a given location_id."""
    loc = location_id.lower()
    if any(k in loc for k in ["trench", "somme", "front", "ypres", "flanders"]):
        return WWITrenchKit(width, height)
    elif any(k in loc for k in ["hospital", "lazarett", "pasewalk", "ward", "clinic"]):
        return MilitaryHospitalKit(width, height)
    elif any(k in loc for k in ["hall", "beer", "tavern", "cellar", "buergerbraukeller"]):
        return BeerHallKit(width, height)
    else:
        # Default to early-1900s European street / architecture kit
        return Early1900sEuropeanStreetKit(width, height)
