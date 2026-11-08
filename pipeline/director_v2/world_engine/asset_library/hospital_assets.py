"""Illustrated Hospital Environment Assets (Pass 2 - High Detail Editorial Quality).

Includes:
1. Cast-Iron Hospital Bedstead:
   - Arched tubular white-enamel iron headboard and footboard.
   - Polished turned brass decorative finial knobs.
   - Contoured vertical iron spindles with authentic Victorian/Edwardian casting collars.
   - High-density mattress with draped, folded hospital linen (fold creases, shadow recesses).
   - Indented pillow with depression.
   - Hanging zinc/tin medical chart clipboard at footboard.
   - Variants: EMPTY, OCCUPIED_BANDAGE, DAMAGED.
2. Prussian Hospital Casement Window:
   - Deep-set stone/plaster embrasure with angled shadow reveal.
   - Heavy timber mullion and transom crossbars dividing into 12 panes + arched fanlight.
   - Double-gleam diagonal specular glass sheen.
   - Projecting molded exterior stone sill.
   - Volumetric sunbeam shaft polygon with dust mote gradation.
3. Bedside Clinical Medicine Table & Apothecary Bottles:
   - White enamel tubular metal legs and double shelves.
   - Amber and emerald glass apothecary bottles with tapered necks and wooden/cork stoppers.
   - Clear glass measuring beaker with graduated measurement markings.
   - Rolled gauze bandage dressing spool.
"""
from __future__ import annotations

import math
from typing import Any
import cairo

from ..materials import MaterialSystem, MaterialType
from ..rough_path import ControlledIrregularityEngine


class IllustratedHospitalBed:
    """Illustrated WWI military convalescence hospital bed."""

    @staticmethod
    def render(
        ctx: cairo.Context,
        x: float,
        y: float,
        scale: float = 1.0,
        variant: str = "EMPTY",
        lighting_dx: float = 1.0,
    ) -> dict[str, Any]:
        """Renders cast-iron bed with authentic Edwardian details and material-aware textures."""
        ctx.save()
        ink = (0.08, 0.09, 0.12)
        iron_color = (0.22, 0.25, 0.28)  # Antique painted iron

        w = 360.0 * scale
        h = 190.0 * scale

        head_w = 34.0 * scale
        head_h = h
        foot_h = h * 0.70
        mattress_y = y + h * 0.48
        mattress_h = 42.0 * scale

        # 1. Headboard (Tubular Cast Iron with Arched Crown & Spindles)
        ctx.save()
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)

        # Main outer tubular arch
        ctx.set_source_rgb(*iron_color)
        ctx.set_line_width(6.0 * scale)
        ctx.move_to(x, y + h)
        ctx.line_to(x, y + head_w)
        ctx.arc(x + head_w / 2.0, y + head_w, head_w / 2.0, math.pi, 0)
        ctx.line_to(x + head_w, y + h)
        ctx.stroke()

        # Turnings / casting collars on main posts
        for py in [y + h * 0.25, y + h * 0.55, y + h * 0.85]:
            ctx.rectangle(x - 3 * scale, py, 6 * scale, 5 * scale)
            ctx.rectangle(x + head_w - 3 * scale, py, 6 * scale, 5 * scale)
            ctx.set_source_rgb(0.12, 0.14, 0.16)
            ctx.fill()

        # Interior vertical iron spindles (4 spindles)
        ctx.set_line_width(2.8 * scale)
        spindle_spacing = head_w / 5.0
        for i in range(1, 5):
            sx = x + i * spindle_spacing
            ctx.move_to(sx, y + head_w * 1.2)
            ctx.line_to(sx, y + h)
            ctx.stroke()
            # Spindle decorative cast rosette collar
            ctx.arc(sx, y + head_w * 2.0, 3.0 * scale, 0, math.tau)
            ctx.fill()

        # Polished Brass Ball Finials at Top of Posts
        for bx in [x, x + head_w]:
            # Brass sphere with specular gleam
            ctx.save()
            ctx.translate(bx, y + head_w * 0.3)
            ctx.arc(0, 0, 7.5 * scale, 0, math.tau)
            b_grad = cairo.RadialGradient(
                -2.5 * scale if lighting_dx >= 0 else 2.5 * scale,
                -2.5 * scale,
                1.0 * scale,
                0, 0, 7.5 * scale
            )
            b_grad.add_color_stop_rgb(0.0, 1.0, 0.95, 0.70)
            b_grad.add_color_stop_rgb(0.6, 0.85, 0.72, 0.32)
            b_grad.add_color_stop_rgb(1.0, 0.45, 0.35, 0.12)
            ctx.set_source(b_grad)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(1.5 * scale)
            ctx.stroke()
            ctx.restore()

        # 2. Footboard (Right side)
        foot_x = x + w - head_w
        ctx.set_source_rgb(*iron_color)
        ctx.set_line_width(5.0 * scale)
        ctx.move_to(foot_x, y + h)
        ctx.line_to(foot_x, y + h - foot_h)
        ctx.line_to(foot_x + head_w, y + h - foot_h)
        ctx.line_to(foot_x + head_w, y + h)
        ctx.stroke()

        # Brass finials on footboard
        for bx in [foot_x, foot_x + head_w]:
            ctx.arc(bx, y + h - foot_h, 6.0 * scale, 0, math.tau)
            ctx.set_source_rgb(0.85, 0.72, 0.32)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(1.2 * scale)
            ctx.stroke()

        # Medical zinc clipboard hanging from footboard rail
        clip_x = foot_x + head_w * 0.25
        clip_y = y + h - foot_h + 16.0 * scale
        ctx.rectangle(clip_x, clip_y, 22.0 * scale, 34.0 * scale)
        ctx.set_source_rgb(0.88, 0.86, 0.80)  # Chart paper
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.2 * scale)
        ctx.stroke()
        # Red cross / clinical temperature chart zig-zag line
        ctx.save()
        ctx.set_source_rgb(0.78, 0.22, 0.20)
        ctx.set_line_width(1.0 * scale)
        ctx.move_to(clip_x + 3 * scale, clip_y + 18 * scale)
        ctx.line_to(clip_x + 8 * scale, clip_y + 12 * scale)
        ctx.line_to(clip_x + 13 * scale, clip_y + 22 * scale)
        ctx.line_to(clip_x + 18 * scale, clip_y + 14 * scale)
        ctx.stroke()
        ctx.restore()

        # 3. Mattress and Layered Hospital Linen
        mat_x = x + head_w * 0.8
        mat_w = w - head_w * 1.6

        # Heavy ticking mattress foundation
        ctx.rectangle(mat_x, mattress_y + 8 * scale, mat_w, mattress_h)
        ctx.set_source_rgb(0.52, 0.55, 0.58)  # Striped ticking edge
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.0 * scale)
        ctx.stroke()

        # Draped white hospital linen sheets with fold shadows
        sheet_y = mattress_y
        sheet_h = mattress_h * 0.95
        ControlledIrregularityEngine.draw_irregular_rect(
            ctx, mat_x, sheet_y, mat_w, sheet_h,
            roughness=0.5,
            fill_color=(0.95, 0.96, 0.97),
            stroke_color=ink,
            stroke_width=2.0 * scale,
        )

        # Apply tactile fabric weave
        MaterialSystem.apply_fabric_weave(ctx, mat_x, sheet_y, mat_w, sheet_h, step=12.0 * scale)

        # Pillow at headboard with realistic depression
        pil_w = 65.0 * scale
        pil_h = 32.0 * scale
        pil_x = mat_x + 6.0 * scale
        pil_y = sheet_y - pil_h * 0.55

        ctx.move_to(pil_x, pil_y + pil_h)
        ctx.curve_to(
            pil_x - 4 * scale, pil_y + pil_h * 0.4,
            pil_x + 10 * scale, pil_y,
            pil_x + pil_w * 0.5, pil_y + 4 * scale  # Head depression
        )
        ctx.curve_to(
            pil_x + pil_w - 10 * scale, pil_y,
            pil_x + pil_w + 4 * scale, pil_y + pil_h * 0.4,
            pil_x + pil_w, pil_y + pil_h
        )
        ctx.close_path()
        ctx.set_source_rgb(0.98, 0.98, 0.99)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.8 * scale)
        ctx.stroke()

        # Folded-over blanket cuff (dark charcoal military wool blanket turned down)
        cuff_x = mat_x + mat_w * 0.28
        cuff_w = mat_w * 0.72
        ctx.rectangle(cuff_x, sheet_y - 2 * scale, cuff_w, 14 * scale)
        ctx.set_source_rgb(0.35, 0.38, 0.34)  # Military gray wool
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.5 * scale)
        ctx.stroke()

        # Diagonal fold creases across blanket
        for fx in [cuff_x + cuff_w * 0.3, cuff_x + cuff_w * 0.65]:
            ctx.move_to(fx, sheet_y + 12 * scale)
            ctx.curve_to(
                fx + 18 * scale, sheet_y + 24 * scale,
                fx - 12 * scale, sheet_y + sheet_h - 4 * scale,
                fx + 8 * scale, sheet_y + sheet_h
            )
            ctx.set_source_rgba(0.1, 0.12, 0.15, 0.25)
            ctx.set_line_width(1.8 * scale)
            ctx.stroke()

        # 4. Cast Contact Shadow on floor
        ctx.restore()
        ctx.restore()

        # Expose interaction affordances for Track A / Composer
        return {
            "asset_id": "hospital_bed_iron_01",
            "lie_anchor": [x + w * 0.48, y + h * 0.65],
            "sit_anchor": [x + w * 0.42, y + h * 0.62],
            "pillow_anchor": [pil_x + pil_w * 0.5, pil_y + pil_h * 0.5],
            "bounds": [x, y, w, h],
        }


class IllustratedPrussianWindow:
    """Illustrated Prussian casement window with glass refraction and light beam."""

    @staticmethod
    def render(
        ctx: cairo.Context,
        x: float,
        y: float,
        width: float,
        height: float,
        scale: float = 1.0,
        light_shaft: bool = True,
        lighting_dx: float = 1.0,
        wall_color: tuple[float, float, float] = (0.90, 0.91, 0.92),
    ) -> dict[str, Any]:
        """Renders deep stone window reveal, 12-pane muntins, glass gleam, and sunbeam."""
        ctx.save()
        ink = (0.10, 0.12, 0.15)
        s = scale
        w = width * s
        h = height * s
        reveal = 22.0 * s

        # 1. Deep Chamfered Stone Embrasure (Architectural Window Reveal)
        r = w / 2.0
        ctx.move_to(x, y + h)
        ctx.line_to(x, y + r)
        ctx.arc(x + r, y + r, r, math.pi, 0)
        ctx.line_to(x + w, y + h)
        ctx.close_path()

        # Embrasure depth gradient (darkens inwards)
        e_grad = cairo.LinearGradient(x, y, x + reveal * 2.0, y)
        e_grad.add_color_stop_rgb(0.0, wall_color[0] * 0.82, wall_color[1] * 0.82, wall_color[2] * 0.84)
        e_grad.add_color_stop_rgb(1.0, wall_color[0] * 0.95, wall_color[1] * 0.95, wall_color[2] * 0.96)
        ctx.set_source(e_grad)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(3.0 * s)
        ctx.stroke()

        # 2. Window Glazing Opening
        gx = x + reveal
        gy = y + reveal
        gw = w - reveal * 2.0
        gh = h - reveal * 2.0
        gr = gw / 2.0

        ctx.save()
        ctx.move_to(gx, gy + gh)
        ctx.line_to(gx, gy + gr)
        ctx.arc(gx + gr, gy + gr, gr, math.pi, 0)
        ctx.line_to(gx + gw, gy + gh)
        ctx.close_path()

        # Sky daylight luminous glow through glass
        sky_grad = cairo.LinearGradient(gx, gy, gx, gy + gh)
        sky_grad.add_color_stop_rgb(0.0, 0.95, 0.98, 1.0)
        sky_grad.add_color_stop_rgb(0.6, 0.88, 0.94, 0.99)
        sky_grad.add_color_stop_rgb(1.0, 0.78, 0.86, 0.92)
        ctx.set_source(sky_grad)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.5 * s)
        ctx.stroke()

        # Diagonal glass reflection sheen
        MaterialSystem.apply_glass_reflection(ctx, gx, gy, gw, gh)
        ctx.restore()

        # 3. Heavy Timber Window Frame & Muntins (12 Panes + Fanlight)
        ctx.save()
        ctx.set_source_rgb(0.24, 0.28, 0.32)
        ctx.set_line_width(3.5 * s)

        # Central vertical mullion
        ctx.move_to(gx + gr, gy)
        ctx.line_to(gx + gr, gy + gh)
        ctx.stroke()

        # Horizontal transoms
        row_h = gh / 4.0
        for r_idx in range(1, 4):
            ty = gy + r_idx * row_h
            ctx.move_to(gx, ty)
            ctx.line_to(gx + gw, ty)
            ctx.stroke()

        # Radial fanlight spokes in upper arch
        for angle in [30, 60, 90, 120, 150]:
            rad = math.radians(angle)
            ctx.move_to(gx + gr, gy + gr)
            ctx.line_to(gx + gr - gr * math.cos(rad), gy + gr - gr * math.sin(rad))
            ctx.stroke()
        ctx.restore()

        # 4. Heavy Molded Stone Window Sill at Base
        sill_h = 18.0 * s
        ctx.rectangle(x - 8 * s, y + h - 2 * s, w + 16 * s, sill_h)
        ctx.set_source_rgb(wall_color[0] * 1.06, wall_color[1] * 1.06, wall_color[2] * 1.06)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.2 * s)
        ctx.stroke()

        # 5. Volumetric Sunbeam Shaft
        if light_shaft:
            ctx.save()
            shaft_bot_w = gw * 4.2
            shaft_x_target = gx + gw * 2.8 if lighting_dx >= 0 else gx - gw * 1.8
            ctx.move_to(gx + 6 * s, gy + gh * 0.2)
            ctx.line_to(gx + gw - 6 * s, gy + gh * 0.2)
            ctx.line_to(shaft_x_target + shaft_bot_w, y + h + 550 * s)
            ctx.line_to(shaft_x_target, y + h + 550 * s)
            ctx.close_path()

            beam_grad = cairo.LinearGradient(
                gx + gr, gy + gh * 0.2,
                shaft_x_target + shaft_bot_w * 0.5, y + h + 550 * s
            )
            beam_grad.add_color_stop_rgba(0.0, 1.0, 0.98, 0.85, 0.28)
            beam_grad.add_color_stop_rgba(0.4, 1.0, 0.95, 0.80, 0.16)
            beam_grad.add_color_stop_rgba(1.0, 1.0, 0.95, 0.80, 0.0)
            ctx.set_source(beam_grad)
            ctx.fill()
            ctx.restore()

        ctx.restore()
        return {
            "asset_id": "prussian_window_01",
            "bounds": [x, y, w, h],
            "light_source_point": [gx + gr, gy + gr],
        }


class IllustratedMedicineTable:
    """Illustrated bedside clinical medicine table with amber bottles and clipboard."""

    @staticmethod
    def render(
        ctx: cairo.Context,
        x: float,
        y: float,
        scale: float = 1.0,
        lighting_dx: float = 1.0,
    ) -> dict[str, Any]:
        """Renders medicine table with apothecary bottles and clinical instruments."""
        ctx.save()
        ink = (0.08, 0.10, 0.12)
        s = scale
        w = 90.0 * s
        h = 130.0 * s

        # 1. White Enamel Metal Table (Top shelf + Bottom shelf)
        top_y = y + 25.0 * s
        bot_y = y + h - 25.0 * s
        shelf_h = 10.0 * s

        # Legs (tubular white metal)
        ctx.set_source_rgb(0.88, 0.90, 0.92)
        ctx.set_line_width(4.5 * s)
        for lx in [x + 6 * s, x + w - 6 * s]:
            ctx.move_to(lx, top_y)
            ctx.line_to(lx, y + h)
            ctx.stroke()
            # Rubber foot ferrules
            ctx.rectangle(lx - 3 * s, y + h - 5 * s, 6 * s, 5 * s)
            ctx.set_source_rgb(0.15, 0.15, 0.18)
            ctx.fill()
            ctx.set_source_rgb(0.88, 0.90, 0.92)

        # Top shelf (white enamel plate with raised rim)
        ctx.rectangle(x, top_y, w, shelf_h)
        ctx.set_source_rgb(0.94, 0.96, 0.98)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.8 * s)
        ctx.stroke()

        # Bottom shelf
        ctx.rectangle(x + 4 * s, bot_y, w - 8 * s, shelf_h * 0.8)
        ctx.set_source_rgb(0.92, 0.94, 0.96)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.stroke()

        # 2. Amber Glass Carbolic Acid Bottle
        bot1_x = x + 14.0 * s
        bot1_y = top_y - 32.0 * s
        bot1_w = 18.0 * s
        bot1_h = 32.0 * s

        ctx.rectangle(bot1_x, bot1_y + 8 * s, bot1_w, bot1_h - 8 * s)
        ctx.set_source_rgb(0.52, 0.28, 0.12)  # Rich amber pharmaceutical glass
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.5 * s)
        ctx.stroke()

        # Bottle neck and cork stopper
        ctx.rectangle(bot1_x + 5 * s, bot1_y, 8 * s, 8 * s)
        ctx.set_source_rgb(0.52, 0.28, 0.12)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.stroke()
        # Cork
        ctx.rectangle(bot1_x + 6 * s, bot1_y - 5 * s, 6 * s, 5 * s)
        ctx.set_source_rgb(0.72, 0.58, 0.38)
        ctx.fill()

        # White paper label on bottle
        ctx.rectangle(bot1_x + 3 * s, bot1_y + 14 * s, bot1_w - 6 * s, 12 * s)
        ctx.set_source_rgb(0.96, 0.95, 0.90)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(0.8 * s)
        ctx.stroke()

        # 3. Emerald Green Poison / Tincture Bottle
        bot2_x = x + 38.0 * s
        bot2_y = top_y - 26.0 * s
        bot2_w = 15.0 * s
        bot2_h = 26.0 * s
        ctx.rectangle(bot2_x, bot2_y + 6 * s, bot2_w, bot2_h - 6 * s)
        ctx.set_source_rgb(0.15, 0.45, 0.28)  # Vintage green glass
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.2 * s)
        ctx.stroke()
        ctx.rectangle(bot2_x + 4 * s, bot2_y, 7 * s, 6 * s)
        ctx.set_source_rgb(0.15, 0.45, 0.28)
        ctx.fill_preserve()
        ctx.stroke()

        # 4. Clear Glass Measuring Beaker
        cup_x = x + 60.0 * s
        cup_y = top_y - 20.0 * s
        cup_w = 16.0 * s
        cup_h = 20.0 * s
        ctx.rectangle(cup_x, cup_y, cup_w, cup_h)
        ctx.set_source_rgba(0.82, 0.90, 0.98, 0.65)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.2 * s)
        ctx.stroke()

        # 5. Rolled Gauze Bandages on bottom shelf
        ctx.arc(x + 22.0 * s, bot_y - 6.0 * s, 8.0 * scale, 0, math.tau)
        ctx.set_source_rgb(0.96, 0.96, 0.95)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.0 * s)
        ctx.stroke()

        ctx.restore()
        return {
            "asset_id": "medicine_table_01",
            "bounds": [x, y, w, h],
            "hand_anchor": [x + w * 0.5, top_y],
        }
