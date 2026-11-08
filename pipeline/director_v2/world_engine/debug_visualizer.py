"""Visual Debuggers for Material System & Multi-Plane Depth Architecture.

Produces:
1. `scene_material_debug_sheet.png`:
   - Renders material swatch samples, edge styles, line densities, specular highlights, and surface marks.
2. `scene_depth_debug_sheet.png`:
   - Visualizes NEAR_FG, FG, MG, BG, FAR_BG plane layering, perspective converging guide lines, and occlusion orders.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any
import cairo

from .materials import MaterialSystem, MaterialType, MATERIAL_REGISTRY
from .composition import CinematicCompositionEngine, DepthPlane
from ..scene_builder.blueprint import SceneBlueprint


class VisualDebugSheets:
    """Generates comprehensive diagnostic debug sheets for Track B inspection."""

    @staticmethod
    def generate_material_debug_sheet(output_path: Path, width: int = 1920, height: int = 1080) -> Path:
        """Renders all registered materials with their specific edge treatments and textures."""
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surf)

        # Dark background
        ctx.rectangle(0, 0, width, height)
        ctx.set_source_rgb(0.05, 0.06, 0.08)
        ctx.fill()

        # Header
        ctx.select_font_face("Impact", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(48.0)
        ctx.set_source_rgb(0.98, 0.78, 0.25)
        ctx.move_to(60, 80)
        ctx.show_text("TRACK B — MATERIAL REGISTRY & SHADER DIAGNOSTIC SHEET")

        ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        ctx.set_font_size(20.0)
        ctx.set_source_rgb(0.65, 0.72, 0.82)
        ctx.move_to(60, 115)
        ctx.show_text("VISUAL DIFFERENTIATION • TACTILE EDGE TREATMENT • DETERMINISTIC SURFACE TEXTURE • SPECULAR GLEAM")

        # Grid of Material Swatches (3 rows x 4 columns)
        cols = 4
        swatch_w = 390.0
        swatch_h = 240.0
        start_x = 60.0
        start_y = 150.0

        materials = list(MATERIAL_REGISTRY.values())

        for idx, mat in enumerate(materials):
            r_idx = idx // cols
            c_idx = idx % cols
            x = start_x + c_idx * (swatch_w + 35.0)
            y = start_y + r_idx * (swatch_h + 35.0)

            # Swatch container card
            ctx.rectangle(x, y, swatch_w, swatch_h)
            ctx.set_source_rgb(0.10, 0.12, 0.15)
            ctx.fill_preserve()
            ctx.set_source_rgb(0.20, 0.24, 0.30)
            ctx.set_line_width(1.5)
            ctx.stroke()

            # Material preview block
            block_x = x + 15
            block_y = y + 15
            block_w = swatch_w - 30
            block_h = 120

            # Base material fill
            ctx.rectangle(block_x, block_y, block_w, block_h)
            ctx.set_source_rgb(*mat.base_color)
            ctx.fill_preserve()
            ctx.set_source_rgb(*mat.stroke_color)
            ctx.set_line_width(mat.stroke_width)
            ctx.stroke()

            # Apply specific material shader
            if mat.mat_type == MaterialType.WOOD:
                MaterialSystem.apply_wood_grain(ctx, block_x, block_y, block_w, block_h, seed=12)
            elif mat.mat_type == MaterialType.METAL:
                MaterialSystem.apply_metal_specular(ctx, block_x, block_y, block_w, block_h, light_dx=1.0)
            elif mat.mat_type == MaterialType.STONE:
                MaterialSystem.apply_stone_stipple(ctx, block_x, block_y, block_w, block_h, seed=45, count=50)
            elif mat.mat_type == MaterialType.FABRIC:
                MaterialSystem.apply_fabric_weave(ctx, block_x, block_y, block_w, block_h, step=12.0)
            elif mat.mat_type == MaterialType.GLASS:
                MaterialSystem.apply_glass_reflection(ctx, block_x, block_y, block_w, block_h)
            elif mat.mat_type == MaterialType.MUD:
                MaterialSystem.apply_mud_squelch(ctx, block_x, block_y, block_w, block_h, seed=88)
            elif mat.mat_type == MaterialType.PLASTER:
                MaterialSystem.apply_stone_stipple(ctx, block_x, block_y, block_w, block_h, seed=99, count=25)

            # Material Title & Metadata
            ctx.select_font_face("Impact", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            ctx.set_font_size(24.0)
            ctx.set_source_rgb(0.96, 0.94, 0.88)
            ctx.move_to(x + 18, y + 168)
            ctx.show_text(mat.mat_type.value)

            ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            ctx.set_font_size(14.0)
            ctx.set_source_rgb(0.98, 0.78, 0.32)
            ctx.move_to(x + 18, y + 192)
            ctx.show_text(f"Edge: {mat.edge_style} | Specular: {mat.specular_intensity*100:.0f}%")

            ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            ctx.set_font_size(12.0)
            ctx.set_source_rgb(0.70, 0.74, 0.80)
            ctx.move_to(x + 18, y + 214)
            # Truncate description to fit card width
            desc = mat.description[:55] + "..." if len(mat.description) > 55 else mat.description
            ctx.show_text(desc)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        surf.write_to_png(str(output_path))
        return output_path

    @staticmethod
    def generate_depth_debug_sheet(
        output_path: Path,
        blueprints: list[SceneBlueprint],
        width: int = 1920,
        height: int = 1080,
    ) -> Path:
        """Visualizes multi-plane depth layering, vanishing perspective rays, and occlusion zones."""
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surf)

        # Dark background
        ctx.rectangle(0, 0, width, height)
        ctx.set_source_rgb(0.04, 0.05, 0.07)
        ctx.fill()

        # Header
        ctx.select_font_face("Impact", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(48.0)
        ctx.set_source_rgb(0.35, 0.78, 0.98)
        ctx.move_to(60, 80)
        ctx.show_text("TRACK B — MULTI-PLANE DEPTH & OCCLUSION ARCHITECTURE")

        ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        ctx.set_font_size(20.0)
        ctx.set_source_rgb(0.65, 0.72, 0.82)
        ctx.move_to(60, 115)
        ctx.show_text("LAYER HIERARCHY: NEAR_FG -> FG -> MG -> BG -> FAR_BG • PERSPECTIVE CONVERGENCE • OCCLUSION ORDER")

        # 3 Side-by-Side Wireframe Previews (Hospital, Beer Hall, Trench)
        card_w = 560.0
        card_h = 780.0
        start_x = 60.0
        start_y = 160.0

        for idx, bp in enumerate(blueprints[:3]):
            cx = start_x + idx * (card_w + 40.0)
            cy = start_y

            # Outer box
            ctx.rectangle(cx, cy, card_w, card_h)
            ctx.set_source_rgb(0.08, 0.10, 0.14)
            ctx.fill_preserve()
            ctx.set_source_rgb(0.20, 0.28, 0.38)
            ctx.set_line_width(2.0)
            ctx.stroke()

            # Scene Title
            ctx.select_font_face("Impact", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            ctx.set_font_size(24.0)
            ctx.set_source_rgb(0.95, 0.95, 0.98)
            ctx.move_to(cx + 20, cy + 40)
            ctx.show_text(f"{idx+1}. {bp.history.location_id.upper()}")

            # Horizon line & Vanishing Point
            h_norm = bp.camera.horizon_y
            h_y = cy + 60.0 + h_norm * (card_h - 100.0)
            vp_x = cx + bp.perspective.primary_vp[0] * card_w
            vp_y = h_y

            # Horizon indicator
            ctx.move_to(cx, h_y)
            ctx.line_to(cx + card_w, h_y)
            ctx.set_source_rgba(0.98, 0.75, 0.25, 0.65)
            ctx.set_line_width(2.0)
            ctx.stroke()

            # Vanishing point dot
            ctx.arc(vp_x, vp_y, 6.0, 0, math.tau)
            ctx.set_source_rgb(1.0, 0.3, 0.3)
            ctx.fill()

            # Perspective converging rays
            ctx.set_source_rgba(0.25, 0.55, 0.85, 0.35)
            ctx.set_line_width(1.2)
            for ray_i in range(8):
                ray_target_x = cx + ray_i * (card_w / 7.0)
                ctx.move_to(vp_x, vp_y)
                ctx.line_to(ray_target_x, cy + card_h)
                ctx.stroke()

            # Depth Planes Color Bands
            planes = [
                ("FAR_BG", 0.0, h_y - cy - 60, (0.2, 0.3, 0.5, 0.25)),
                ("BG", h_y - cy - 60, 140.0, (0.3, 0.5, 0.3, 0.25)),
                ("MG", h_y - cy - 60 + 140.0, 200.0, (0.8, 0.6, 0.2, 0.25)),
                ("FG", cy + card_h - (cy + 60.0 + 380.0), 120.0, (0.8, 0.3, 0.3, 0.25)),
                ("NEAR_FG", 0.0, 0.0, (0.5, 0.2, 0.8, 0.45)),
            ]

            # Foreground Framing Occlusion Box
            if "OTS" in bp.camera.shot_size.upper():
                # Left Third OTS
                ctx.rectangle(cx + 20, cy + card_h * 0.45, card_w * 0.35, card_h * 0.52)
                ctx.set_source_rgba(0.85, 0.35, 0.35, 0.45)
                ctx.fill_preserve()
                ctx.set_source_rgb(0.95, 0.45, 0.45)
                ctx.set_line_width(2.0)
                ctx.stroke()
                ctx.move_to(cx + 35, cy + card_h * 0.75)
                ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                ctx.set_font_size(16.0)
                ctx.show_text("NEAR_FG (OTS)")

            elif "GROUND" in bp.camera.shot_size.upper():
                # Left Corner Post
                ctx.rectangle(cx + 10, cy + card_h * 0.40, card_w * 0.25, card_h * 0.58)
                ctx.set_source_rgba(0.85, 0.35, 0.35, 0.45)
                ctx.fill_preserve()
                ctx.set_source_rgb(0.95, 0.45, 0.45)
                ctx.set_line_width(2.0)
                ctx.stroke()
                ctx.move_to(cx + 20, cy + card_h * 0.70)
                ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                ctx.set_font_size(15.0)
                ctx.show_text("FG (POST)")

            elif "DEEP" in bp.camera.shot_size.upper():
                # Right bottom table edge
                ctx.rectangle(cx + card_w * 0.55, cy + card_h * 0.72, card_w * 0.42, card_h * 0.25)
                ctx.set_source_rgba(0.85, 0.35, 0.35, 0.45)
                ctx.fill_preserve()
                ctx.set_source_rgb(0.95, 0.45, 0.45)
                ctx.set_line_width(2.0)
                ctx.stroke()
                ctx.move_to(cx + card_w * 0.60, cy + card_h * 0.85)
                ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                ctx.set_font_size(15.0)
                ctx.show_text("FG (TABLE)")

            # Legend block at bottom of card
            ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            ctx.set_font_size(14.0)
            ctx.set_source_rgb(0.75, 0.80, 0.88)
            ctx.move_to(cx + 20, cy + card_h - 40)
            ctx.show_text(f"VP: [{bp.perspective.primary_vp[0]:.2f}, {bp.perspective.primary_vp[1]:.2f}] | Horizon: {h_norm*100:.0f}%")
            ctx.move_to(cx + 20, cy + card_h - 18)
            ctx.show_text(f"Depth Axis: {bp.perspective.depth_axis} | Shot: {bp.camera.shot_size}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        surf.write_to_png(str(output_path))
        return output_path
