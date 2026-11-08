"""Illustrated Trench & Battlefield Assets (Pass 2 - High Detail Editorial Quality).

Includes:
1. Rough Pine Timber Trench Revetment & Hurdle:
   - Split bark-on pine logs with chiseled axe tool marks.
   - Heavy horizontal woven hurdles (Faschinen) retaining earthen parapet.
   - Blackened forged iron spikes driven through upright bracing pilings.
   - Concussion split gouges and bullet strikes from hostile sniper fire.
2. Stacked Burlap Sandbag Fortification:
   - Heavy coarse burlap texture with visible stitching seams and tied "ear" corners.
   - Realistic gravitational sag and weight compression between layers.
   - Color gradation: damp earth-soaked lower bags vs sun-bleached upper bags.
3. Concertina Barbed Wire Entanglement:
   - Split chestnut/pine picket stakes driven into chalk/mud with barbed wire catenaries.
   - Multi-strand concertina spiral coils with 4-point galvanized steel barbs.
4. Heavy Artillery Blast Crater:
   - Torn raised ejecta lip of disturbed subsoil and mud.
   - Radial explosion scorch lines and deep shadowed bowl.
   - Oily stagnant puddle reflection with surface tension ripples.
5. Military Packing Case & Ammo Crate Stack:
   - Feldgrau military painted pine crates with blackened steel corner brackets.
   - Heavy hemp rope carry handles.
   - Authentic Imperial German stencil markings ("7.92mm Mauser S-Patronen", "Stielhandgranaten 15").
"""
from __future__ import annotations

import math
from typing import Any
import cairo

from ..materials import MaterialSystem, MaterialType
from ..rough_path import ControlledIrregularityEngine


class IllustratedTrenchRevetment:
    """Illustrated split pine timber revetment wall holding trench banks."""

    @staticmethod
    def render(
        ctx: cairo.Context,
        x: float,
        y: float,
        width: float,
        height: float,
        scale: float = 1.0,
        plank_count: int = 8,
        damage: float = 0.3,
        lighting_dx: float = 1.0,
        wood_color: tuple[float, float, float] = (0.36, 0.26, 0.16),
    ) -> None:
        """Renders heavy timber revetment with wood grain, bark edges, iron spikes, and shell damage."""
        ctx.save()
        ink = (0.06, 0.06, 0.08)
        s = scale
        plank_h = height / plank_count

        # 1. Horizontal retaining timber planks
        for p in range(plank_count):
            py = y + p * plank_h
            var = math.sin(p * 2.7) * 0.06
            p_col = (
                max(0.12, min(0.65, wood_color[0] + var)),
                max(0.10, min(0.55, wood_color[1] + var)),
                max(0.08, min(0.45, wood_color[2] + var)),
            )

            # Planks with slight organic line irregularity
            ControlledIrregularityEngine.draw_irregular_rect(
                ctx, x, py, width, plank_h,
                roughness=0.6,
                fill_color=p_col,
                stroke_color=ink,
                stroke_width=2.2 * s,
            )

            # Apply tactile wood grain
            MaterialSystem.apply_wood_grain(ctx, x, py, width, plank_h, seed=200 + p * 13, density=4)

            # Iron spike fasteners driven into timber
            for bx in [x + width * 0.25, x + width * 0.5, x + width * 0.75]:
                ctx.arc(bx, py + plank_h * 0.5, 3.5 * s, 0, math.tau)
                ctx.set_source_rgb(0.10, 0.10, 0.12)
                ctx.fill_preserve()
                ctx.set_source_rgb(*ink)
                ctx.set_line_width(1.0 * s)
                ctx.stroke()

            # Concussion splinter / bullet gouge if damage > 0.15
            if damage > 0.15 and (p % 3 == 1):
                gx = x + width * ((p * 0.33) % 0.75 + 0.15)
                ctx.save()
                ctx.move_to(gx - 12 * s, py + plank_h * 0.5)
                ctx.line_to(gx + 12 * s, py + plank_h * 0.45)
                ctx.line_to(gx + 4 * s, py + plank_h * 0.7)
                ctx.close_path()
                ctx.set_source_rgb(0.14, 0.10, 0.06)  # Deep splinter shadow
                ctx.fill()
                ctx.restore()

        # 2. Vertical Bracing Upright Piles (Split tree trunks)
        pile_w = 36.0 * s
        pile_count = max(2, int(width / (260.0 * s)))
        for i in range(pile_count):
            px = x + (i + 0.5) * (width / pile_count) - pile_w * 0.5
            ControlledIrregularityEngine.draw_irregular_rect(
                ctx, px, y - 6 * s, pile_w, height + 12 * s,
                roughness=0.8,
                fill_color=(wood_color[0] * 0.85, wood_color[1] * 0.85, wood_color[2] * 0.82),
                stroke_color=ink,
                stroke_width=3.0 * s,
            )
            # Bark stipple texture on upright log
            MaterialSystem.apply_stone_stipple(ctx, px, y, pile_w, height, seed=330 + i * 29, count=25)

        ctx.restore()


class IllustratedSandbagFortification:
    """Stacked burlap sandbags with realistic sag, seams, and earth fill."""

    @staticmethod
    def render(
        ctx: cairo.Context,
        x: float,
        y: float,
        width: float,
        height: float,
        scale: float = 1.0,
        layers: int = 5,
        bags_per_layer: int = 8,
        lighting_dx: float = 1.0,
        burlap_color: tuple[float, float, float] = (0.58, 0.52, 0.40),
    ) -> None:
        """Renders stacked sandbag parapet with individual burlap bags and tied ear corners."""
        ctx.save()
        ink = (0.08, 0.08, 0.10)
        s = scale
        layer_h = height / layers

        for l_idx in range(layers):
            ly = y + height - (l_idx + 1) * layer_h
            stagger = (l_idx % 2) * (width / bags_per_layer * 0.5)
            bag_w = (width / bags_per_layer) * 1.08

            # Damp bottom layers are darker, top sun-bleached layers are lighter
            tier_mult = 0.82 + (l_idx / layers) * 0.32
            tier_col = (
                burlap_color[0] * tier_mult,
                burlap_color[1] * tier_mult,
                burlap_color[2] * tier_mult,
            )

            for b_idx in range(-1, bags_per_layer + 1):
                bx = x + b_idx * (width / bags_per_layer) + stagger

                ctx.save()
                # Pillow rounded burlap outline
                r = 8.0 * s
                ctx.new_sub_path()
                ctx.arc(bx + bag_w - 4 * s - r, ly + 2 * s + r, r, -math.pi / 2, 0)
                ctx.arc(bx + bag_w - 4 * s - r, ly + layer_h - 2 * s - r, r, 0, math.pi / 2)
                ctx.arc(bx + 4 * s + r, ly + layer_h - 2 * s - r, r, math.pi / 2, math.pi)
                ctx.arc(bx + 4 * s + r, ly + 2 * s + r, r, math.pi, 3 * math.pi / 2)
                ctx.close_path()

                # Shading gradient across sandbag
                b_grad = cairo.LinearGradient(bx, ly, bx + bag_w, ly + layer_h)
                if lighting_dx >= 0:
                    b_grad.add_color_stop_rgb(0.0, tier_col[0] * 1.10, tier_col[1] * 1.10, tier_col[2] * 1.08)
                    b_grad.add_color_stop_rgb(1.0, tier_col[0] * 0.78, tier_col[1] * 0.75, tier_col[2] * 0.68)
                else:
                    b_grad.add_color_stop_rgb(0.0, tier_col[0] * 0.78, tier_col[1] * 0.75, tier_col[2] * 0.68)
                    b_grad.add_color_stop_rgb(1.0, tier_col[0] * 1.10, tier_col[1] * 1.10, tier_col[2] * 1.08)

                ctx.set_source(b_grad)
                ctx.fill_preserve()
                ctx.set_source_rgb(*ink)
                ctx.set_line_width(2.2 * s)
                ctx.stroke()

                # Tied burlap "ear" knot at bag corners
                ctx.arc(bx + 5 * s, ly + layer_h * 0.5, 3.8 * s, 0, math.tau)
                ctx.set_source_rgb(*ink)
                ctx.fill()

                # Center seam stitching line
                ctx.move_to(bx + bag_w * 0.25, ly + layer_h * 0.5)
                ctx.line_to(bx + bag_w * 0.75, ly + layer_h * 0.5)
                ctx.set_source_rgba(0.1, 0.1, 0.12, 0.35)
                ctx.set_line_width(1.2 * s)
                ctx.stroke()

                # Coarse burlap fabric weave stipple
                MaterialSystem.apply_stone_stipple(ctx, bx + 6 * s, ly + 4 * s, bag_w - 12 * s, layer_h - 8 * s, seed=400 + l_idx * 19 + b_idx, count=8)
                ctx.restore()

        ctx.restore()


class IllustratedAmmoCrateStack:
    """Stacked German military ammunition packing cases with authentic stencils."""

    @staticmethod
    def render(
        ctx: cairo.Context,
        x: float,
        y: float,
        scale: float = 1.0,
        crate_count: int = 3,
        lighting_dx: float = 1.0,
    ) -> None:
        """Renders stacked Feldgrau military ammo crates with metal brackets and rope handles."""
        ctx.save()
        ink = (0.08, 0.08, 0.10)
        s = scale
        crate_w = 140.0 * s
        crate_h = 70.0 * s

        for c in range(crate_count):
            cy = y - (c + 1) * crate_h
            cx = x + (c % 2) * 14.0 * s

            # 1. Main Feldgrau Wood Box Body
            ctx.rectangle(cx, cy, crate_w, crate_h)
            ctx.set_source_rgb(0.32, 0.36, 0.30)  # Feldgrau military green
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(2.8 * s)
            ctx.stroke()

            # Wood grain on box faces
            MaterialSystem.apply_wood_grain(ctx, cx, cy, crate_w, crate_h, seed=500 + c * 37, density=3)

            # 2. Blackened Steel Corner Reinforcing Brackets & Rivets
            strap_w = 18.0 * s
            for bx in [cx, cx + crate_w - strap_w]:
                for by in [cy, cy + crate_h - strap_w]:
                    ctx.rectangle(bx, by, strap_w, strap_w)
                    ctx.set_source_rgb(0.18, 0.18, 0.20)
                    ctx.fill_preserve()
                    ctx.set_source_rgb(*ink)
                    ctx.set_line_width(1.2 * s)
                    ctx.stroke()
                    # Rivet dot
                    ctx.arc(bx + strap_w * 0.5, by + strap_w * 0.5, 2.0 * s, 0, math.tau)
                    ctx.set_source_rgb(0.70, 0.70, 0.75)
                    ctx.fill()

            # 3. Painted Military Identification Stencils
            ctx.save()
            ctx.select_font_face("Impact", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            ctx.set_font_size(12.0 * s)
            ctx.set_source_rgb(0.92, 0.90, 0.82)
            ctx.move_to(cx + 25 * s, cy + crate_h * 0.54)
            ctx.show_text("7.92mm MG08" if c == 0 else "Stielhandgranaten" if c == 1 else "HE-1916")
            ctx.restore()

            # 4. Heavy Braided Hemp Rope Carry Handle on end
            ctx.move_to(cx - 10 * s, cy + crate_h * 0.35)
            ctx.curve_to(
                cx - 22 * s, cy + crate_h * 0.45,
                cx - 22 * s, cy + crate_h * 0.75,
                cx - 10 * s, cy + crate_h * 0.85
            )
            ctx.set_source_rgb(0.55, 0.48, 0.36)  # Twisted hemp rope
            ctx.set_line_width(4.5 * s)
            ctx.stroke()

        ctx.restore()


class IllustratedBarbedWire:
    """Illustrated concertina wire entanglement and picket posts."""

    @staticmethod
    def render(
        ctx: cairo.Context,
        pts: list[tuple[float, float]],
        post_count: int = 4,
        scale: float = 1.0,
        lighting_dx: float = 1.0,
    ) -> None:
        """Renders sharp wooden picket stakes with concertina spirals and 4-point razor barbs."""
        if len(pts) < 2:
            return
        ctx.save()
        ink = (0.10, 0.10, 0.12)
        s = scale

        p0, p1 = pts[0], pts[-1]

        # 1. Wooden Picket Stakes (Angle stakes driven into trench parapet)
        for i in range(post_count):
            t = i / max(1, post_count - 1)
            px = p0[0] + t * (p1[0] - p0[0])
            py = p0[1] + t * (p1[1] - p0[1])

            ctx.save()
            angle = math.sin(i * 1.9) * 0.16
            ctx.translate(px, py)
            ctx.rotate(angle)

            # Timber stake
            ControlledIrregularityEngine.draw_irregular_rect(
                ctx, -8 * s, -95 * s, 16 * s, 105 * s,
                roughness=0.8,
                fill_color=(0.34, 0.26, 0.18),
                stroke_color=ink,
                stroke_width=2.2 * s,
            )

            # Chiseled pointed top
            ctx.move_to(-8 * s, -95 * s)
            ctx.line_to(0, -108 * s)
            ctx.line_to(8 * s, -95 * s)
            ctx.close_path()
            ctx.set_source_rgb(0.40, 0.32, 0.22)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(1.8 * s)
            ctx.stroke()
            ctx.restore()

        # 2. Main galvanized steel wire strands with catenary sag
        for strand_y in [-80.0 * s, -50.0 * s, -20.0 * s]:
            ctx.move_to(p0[0], p0[1] + strand_y)
            for i in range(1, len(pts)):
                pt = pts[i]
                prev = pts[i - 1]
                cx = (prev[0] + pt[0]) * 0.5
                cy = (prev[1] + pt[1]) * 0.5 + strand_y + 14.0 * s
                p0_x, p0_y = prev[0], prev[1] + strand_y
                p2_x, p2_y = pt[0], pt[1] + strand_y
                cp1_x = p0_x + 2.0 / 3.0 * (cx - p0_x)
                cp1_y = p0_y + 2.0 / 3.0 * (cy - p0_y)
                cp2_x = p2_x + 2.0 / 3.0 * (cx - p2_x)
                cp2_y = p2_y + 2.0 / 3.0 * (cy - p2_y)
                ctx.curve_to(cp1_x, cp1_y, cp2_x, cp2_y, p2_x, p2_y)

            ctx.set_source_rgb(0.24, 0.26, 0.28)
            ctx.set_line_width(2.2 * s)
            ctx.stroke()

        # 3. Concertina Circular Wire Spirals & Sharp Barbs
        coil_count = 20
        for c in range(coil_count):
            t = c / coil_count
            cx = p0[0] + t * (p1[0] - p0[0])
            cy = p0[1] + t * (p1[1] - p0[1]) - 48.0 * s
            cr = 32.0 * s

            ctx.save()
            ctx.translate(cx, cy)
            ctx.scale(0.55, 1.0)
            ctx.arc(0, 0, cr, 0, math.tau)
            ctx.set_source_rgba(0.26, 0.28, 0.32, 0.85)
            ctx.set_line_width(1.8 * s)
            ctx.stroke()

            # 4-point razor barbs on wire
            for b_deg in [0, 90, 180, 270]:
                brad = math.radians(b_deg)
                bx = cr * math.cos(brad)
                by = cr * math.sin(brad)
                ctx.move_to(bx - 5 * s, by - 5 * s)
                ctx.line_to(bx + 5 * s, by + 5 * s)
                ctx.move_to(bx + 5 * s, by - 5 * s)
                ctx.line_to(bx - 5 * s, by + 5 * s)
                ctx.set_source_rgb(0.12, 0.12, 0.15)
                ctx.set_line_width(1.5 * s)
                ctx.stroke()
            ctx.restore()

        ctx.restore()
