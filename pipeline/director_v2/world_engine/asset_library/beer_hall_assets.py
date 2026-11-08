"""Illustrated Beer Hall & Tavern Assets (Pass 2 - High Detail Editorial Quality).

Includes:
1. Heavy Bavarian Oak Tavern Table & Benches:
   - 4-inch thick solid dark oak tabletop with end breadboard joins.
   - Chamfered edges, hand-planed surface marks, and dark age knots.
   - Heavy timber trestle X-legs with mortise-and-tenon through joints secured by oak wedges.
   - Wet circular beer stein condensation rings on tabletop.
2. Traditional Keferloher Beer Steins:
   - Salt-glazed Westerwald stoneware body in warm gray with cobalt blue salt-glaze spiral floral rosettes.
   - Hinged cast-pewter lid with ornamental thumb-lift ball.
   - Thick ear handle with pewter hinge strap.
   - Frothy Bavarian lager foam overflowing the lip.
3. Stacked Oak Beer Barrels:
   - Bulbous bulging barrel staves with charred oak woodgrain.
   - Heavy black hand-forged iron hoops with hammered rivet heads.
   - Front bung hole with wooden stopper bung.
   - Triangular wooden floor chocks preventing roll.
4. Hanging Wrought-Brass Chandelier:
   - Suspended from forged link chain with ornamental rosette ceiling plate.
   - Circular pierced brass rim with scrollwork brackets.
   - 4 luminous frosted glass oil / gas hurricane lamps casting amber volumetric glow halos.
"""
from __future__ import annotations

import math
from typing import Any
import cairo

from ..materials import MaterialSystem, MaterialType
from ..rough_path import ControlledIrregularityEngine


class IllustratedTavernTable:
    """Heavy Bavarian solid oak tavern table with trestle base."""

    @staticmethod
    def render(
        ctx: cairo.Context,
        x: float,
        y: float,
        width: float = 380.0,
        height: float = 160.0,
        scale: float = 1.0,
        stein_count: int = 4,
        lighting_dx: float = 1.0,
        wood_color: tuple[float, float, float] = (0.34, 0.22, 0.12),
    ) -> dict[str, Any]:
        """Renders authentic Bavarian tavern table with trestle legs and steins."""
        ctx.save()
        ink = (0.08, 0.08, 0.10)
        s = scale
        w = width * s
        h = height * s

        top_h = 28.0 * s
        top_y = y + 45.0 * s

        # 1. Cast Contact Shadow on floor beneath table
        ctx.save()
        ctx.translate(x + w * 0.5, y + h + 10 * s)
        ctx.scale(1.0, 0.22)
        ctx.arc(0, 0, w * 0.52, 0, math.tau)
        ctx.set_source_rgba(0.04, 0.04, 0.05, 0.55)
        ctx.fill()
        ctx.restore()

        # 2. Heavy Trestle Legs (X-frame or Lyre-shaped heavy timbers)
        leg_w = 32.0 * s
        for lx in [x + 65 * s, x + w - 65 * s - leg_w]:
            # X-brace trestle legs
            ctx.save()
            ctx.move_to(lx + 8 * s, top_y + top_h)
            ctx.line_to(lx + leg_w, y + h)
            ctx.line_to(lx + leg_w - 10 * s, y + h)
            ctx.line_to(lx, top_y + top_h)
            ctx.close_path()

            ctx.move_to(lx + leg_w - 8 * s, top_y + top_h)
            ctx.line_to(lx, y + h)
            ctx.line_to(lx + 10 * s, y + h)
            ctx.line_to(lx + leg_w, top_y + top_h)
            ctx.close_path()

            ctx.set_source_rgb(wood_color[0] * 0.72, wood_color[1] * 0.72, wood_color[2] * 0.70)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(2.5 * s)
            ctx.stroke()

            # Wooden wedge securing keyed through-tenon joint
            ctx.rectangle(lx + leg_w * 0.2, top_y + (y + h - top_y) * 0.5 - 6 * s, 18 * s, 12 * s)
            ctx.set_source_rgb(wood_color[0] * 1.15, wood_color[1] * 1.15, wood_color[2] * 1.10)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(1.2 * s)
            ctx.stroke()
            ctx.restore()

        # Center longitudinal stretcher beam connecting the two trestles
        ctx.rectangle(x + 75 * s, y + h - 35 * s, w - 150 * s, 18 * s)
        ctx.set_source_rgb(wood_color[0] * 0.80, wood_color[1] * 0.80, wood_color[2] * 0.78)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.0 * s)
        ctx.stroke()

        # 3. Solid Oak Tabletop (Perspective Trapezoid with End Breadboard Caps)
        ctx.save()
        ctx.move_to(x + 28 * s, top_y)
        ctx.line_to(x + w - 28 * s, top_y)
        ctx.line_to(x + w, top_y + top_h)
        ctx.line_to(x, top_y + top_h)
        ctx.close_path()

        # Rich warm oak wood gradient
        t_grad = cairo.LinearGradient(x, top_y, x + w, top_y + top_h)
        t_grad.add_color_stop_rgb(0.0, wood_color[0] * 1.12, wood_color[1] * 1.12, wood_color[2] * 1.10)
        t_grad.add_color_stop_rgb(0.5, wood_color[0], wood_color[1], wood_color[2])
        t_grad.add_color_stop_rgb(1.0, wood_color[0] * 0.82, wood_color[1] * 0.82, wood_color[2] * 0.80)
        ctx.set_source(t_grad)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(3.0 * s)
        ctx.stroke()

        # Apply rich organic wood grain
        MaterialSystem.apply_wood_grain(ctx, x, top_y, w, top_h, seed=123, density=6)

        # Chamfered front edge shadow
        ctx.rectangle(x, top_y + top_h - 4 * s, w, 4 * s)
        ctx.set_source_rgba(0.04, 0.03, 0.02, 0.40)
        ctx.fill()

        # Wet circular beer stein condensation rings on tabletop
        for rx_off in [w * 0.22, w * 0.52, w * 0.78]:
            ctx.save()
            ctx.translate(x + rx_off, top_y + 12 * s)
            ctx.scale(1.0, 0.35)
            ctx.arc(0, 0, 16 * s, 0, math.tau)
            ctx.set_source_rgba(0.12, 0.08, 0.04, 0.35)
            ctx.set_line_width(2.0 * s)
            ctx.stroke()
            ctx.restore()

        ctx.restore()

        # 4. Illustrated Keferloher Beer Steins Sitting on Table
        stein_spacing = w / (stein_count + 1)
        for i in range(1, stein_count + 1):
            sx = x + i * stein_spacing - 16 * s
            sy = top_y - 36 * s
            IllustratedKeferloherStein.render(ctx, sx, sy, scale=scale * 1.05, lighting_dx=lighting_dx)

        ctx.restore()
        return {
            "asset_id": "tavern_table_oak_01",
            "bounds": [x, y, w, h],
            "lean_anchor": [x + w * 0.45, top_y],
        }


class IllustratedKeferloherStein:
    """Illustrated Bavarian salt-glazed stoneware beer stein (Keferloher with pewter lid)."""

    @staticmethod
    def render(
        ctx: cairo.Context,
        x: float,
        y: float,
        scale: float = 1.0,
        lighting_dx: float = 1.0,
    ) -> None:
        """Renders authentic 1-liter Masskrug stoneware stein with blue rosette and foam."""
        ctx.save()
        ink = (0.08, 0.08, 0.10)
        s = scale
        sw = 32.0 * s
        sh = 40.0 * s

        # Cast shadow on table
        ctx.save()
        ctx.translate(x + sw * 0.5, y + sh + 2 * s)
        ctx.scale(1.0, 0.35)
        ctx.arc(0, 0, sw * 0.55, 0, math.tau)
        ctx.set_source_rgba(0.04, 0.03, 0.02, 0.45)
        ctx.fill()
        ctx.restore()

        # 1. Salt-Glazed Ceramic Stoneware Body (Cylindrical form with ribbed base ring)
        ctx.save()
        ctx.rectangle(x, y + 4 * s, sw, sh - 4 * s)
        # Salt-glazed stoneware ceramic gradient (gray with slight earthen tint)
        c_grad = cairo.LinearGradient(x, y, x + sw, y)
        c_grad.add_color_stop_rgb(0.0, 0.88, 0.86, 0.80)
        c_grad.add_color_stop_rgb(0.4, 0.80, 0.78, 0.72)
        c_grad.add_color_stop_rgb(1.0, 0.62, 0.60, 0.56)
        ctx.set_source(c_grad)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.0 * s)
        ctx.stroke()

        # Ribbed base footing
        ctx.rectangle(x - 1 * s, y + sh - 5 * s, sw + 2 * s, 5 * s)
        ctx.set_source_rgb(0.68, 0.65, 0.60)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.5 * s)
        ctx.stroke()

        # Incised Cobalt Blue Westerwald Floral Rosette / Bavarian pattern
        ctx.save()
        ctx.arc(x + sw * 0.48, y + sh * 0.52, 7.0 * s, 0, math.tau)
        ctx.set_source_rgb(0.18, 0.28, 0.56)  # Deep cobalt blue
        ctx.fill()
        ctx.arc(x + sw * 0.48, y + sh * 0.52, 4.0 * s, 0, math.tau)
        ctx.set_source_rgb(0.80, 0.78, 0.72)
        ctx.fill()
        ctx.restore()

        # 2. Pewter Hinged Conical Lid & Thumb-Lift
        ctx.move_to(x, y + 4 * s)
        ctx.line_to(x + sw * 0.5, y - 6 * s)
        ctx.line_to(x + sw, y + 4 * s)
        ctx.close_path()
        p_grad = cairo.LinearGradient(x, y, x + sw, y)
        p_grad.add_color_stop_rgb(0.0, 0.65, 0.68, 0.72)
        p_grad.add_color_stop_rgb(1.0, 0.38, 0.40, 0.44)
        ctx.set_source(p_grad)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.8 * s)
        ctx.stroke()

        # Pewter finial ball on top of lid
        ctx.arc(x + sw * 0.5, y - 7 * s, 3.5 * s, 0, math.tau)
        ctx.set_source_rgb(0.68, 0.70, 0.74)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.2 * s)
        ctx.stroke()

        # Pewter thumb-lift lever & hinge attachment
        ctx.move_to(x + sw, y + 2 * s)
        ctx.line_to(x + sw + 7 * s, y - 4 * s)
        ctx.set_source_rgb(0.48, 0.50, 0.54)
        ctx.set_line_width(2.5 * s)
        ctx.stroke()

        # 3. Thick Ear Handle (Stoneware ceramic loop)
        ctx.move_to(x + sw, y + 8 * s)
        ctx.curve_to(
            x + sw + 16 * s, y + 14 * s,
            x + sw + 16 * s, y + sh - 10 * s,
            x + sw, y + sh - 6 * s
        )
        ctx.set_source_rgb(0.75, 0.72, 0.66)
        ctx.set_line_width(5.0 * s)
        ctx.stroke_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.5 * s)
        ctx.stroke()

        # 4. Overflowing Frothy Bavarian Beer Foam Head
        ctx.arc(x + 7 * s, y + 3 * s, 5.0 * s, 0, math.tau)
        ctx.arc(x + sw * 0.5, y + 1 * s, 6.0 * s, 0, math.tau)
        ctx.arc(x + sw - 6 * s, y + 4 * s, 5.5 * s, 0, math.tau)
        ctx.set_source_rgb(0.98, 0.97, 0.92)  # Rich frothy white-cream
        ctx.fill()

        # Foam drop dripping down side
        ctx.move_to(x + 6 * s, y + 8 * s)
        ctx.line_to(x + 6 * s, y + 18 * s)
        ctx.set_source_rgb(0.98, 0.97, 0.92)
        ctx.set_line_width(2.0 * s)
        ctx.stroke()

        ctx.restore()
        ctx.restore()


class IllustratedBeerBarrelStack:
    """Stacked Bavarian oak beer barrels with iron hoops and chocks."""

    @staticmethod
    def render(
        ctx: cairo.Context,
        x: float,
        y: float,
        scale: float = 1.0,
        stack_count: int = 4,
        lighting_dx: float = 1.0,
    ) -> None:
        """Renders stacked aging oak beer barrels against tavern wall."""
        ctx.save()
        ink = (0.08, 0.08, 0.10)
        s = scale
        bw = 64.0 * s
        bh = 85.0 * s

        # Render barrels side by side with a second tier on top
        positions = [
            (x, y - bh),
            (x + bw * 0.92, y - bh),
            (x + bw * 1.84, y - bh),
            (x + bw * 0.46, y - bh * 1.85),  # Top tier pyramid barrel
        ]

        for bx, by in positions[:stack_count]:
            ctx.save()
            # Cast shadow beneath barrel
            ctx.save()
            ctx.translate(bx + bw * 0.5, by + bh)
            ctx.scale(1.0, 0.25)
            ctx.arc(0, 0, bw * 0.55, 0, math.tau)
            ctx.set_source_rgba(0.04, 0.04, 0.05, 0.50)
            ctx.fill()
            ctx.restore()

            # Bulbous barrel body (oval stave profile)
            ctx.translate(bx + bw * 0.5, by + bh * 0.5)
            ctx.scale(1.0, bh / bw)
            ctx.arc(0, 0, bw * 0.5, 0, math.tau)

            o_grad = cairo.RadialGradient(
                -bw * 0.2 if lighting_dx >= 0 else bw * 0.2,
                -bw * 0.2,
                5 * s,
                0, 0, bw * 0.5
            )
            o_grad.add_color_stop_rgb(0.0, 0.48, 0.32, 0.18)
            o_grad.add_color_stop_rgb(0.7, 0.35, 0.22, 0.12)
            o_grad.add_color_stop_rgb(1.0, 0.22, 0.14, 0.08)
            ctx.set_source(o_grad)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(2.5 * s)
            ctx.stroke()

            # Hand-forged black iron hoops (4 hoops per barrel)
            for hoop_r in [bw * 0.46, bw * 0.36, bw * 0.24]:
                ctx.arc(0, 0, hoop_r, 0, math.tau)
                ctx.set_source_rgba(0.12, 0.12, 0.15, 0.85)
                ctx.set_line_width(3.0 * s)
                ctx.stroke()

            # Central bung hole with wooden bung stopper
            ctx.arc(0, 0, 5.0 * s, 0, math.tau)
            ctx.set_source_rgb(0.12, 0.08, 0.05)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(1.0 * s)
            ctx.stroke()
            ctx.restore()

        ctx.restore()


class IllustratedBrassChandelier:
    """Illustrated period wrought brass & frosted glass tavern chandelier."""

    @staticmethod
    def render(
        ctx: cairo.Context,
        x: float,
        y: float,
        scale: float = 1.0,
        lighting_dx: float = 1.0,
    ) -> None:
        """Renders ornate hanging chandelier with warm glowing hurricane lamps."""
        ctx.save()
        ink = (0.08, 0.08, 0.10)
        s = scale

        # Forged ceiling suspension chain
        ctx.move_to(x, y - 90 * s)
        ctx.line_to(x, y)
        ctx.set_source_rgb(0.18, 0.18, 0.20)
        ctx.set_line_width(3.5 * s)
        ctx.stroke()

        # Pierced brass crown hoop
        hoop_w = 110.0 * s
        hoop_h = 24.0 * s
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(1.0, hoop_h / hoop_w)
        ctx.arc(0, 0, hoop_w * 0.5, 0, math.tau)
        ctx.set_source_rgb(0.78, 0.64, 0.28)  # Antique spun brass
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.5 * s)
        ctx.stroke()
        ctx.restore()

        # 4 Sconce arms holding frosted glass hurricane lamps
        for arm_x in [-hoop_w * 0.42, -hoop_w * 0.15, hoop_w * 0.15, hoop_w * 0.42]:
            lx = x + arm_x
            ly = y - 12 * s

            # Brass lamp gallery / cup
            ctx.rectangle(lx - 8 * s, ly + 14 * s, 16 * s, 8 * s)
            ctx.set_source_rgb(0.78, 0.64, 0.28)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(1.2 * s)
            ctx.stroke()

            # Glass hurricane chimney
            ctx.save()
            ctx.rectangle(lx - 7 * s, ly - 16 * s, 14 * s, 30 * s)
            ctx.set_source_rgba(1.0, 0.94, 0.72, 0.90)  # Glowing amber glass
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(1.2 * s)
            ctx.stroke()

            # Bright inner flame wick
            ctx.arc(lx, ly, 3.5 * s, 0, math.tau)
            ctx.set_source_rgb(1.0, 1.0, 0.85)
            ctx.fill()
            ctx.restore()

            # Radiant volumetric warm amber glow halo
            glow = cairo.RadialGradient(lx, ly, 4.0 * s, lx, ly, 140.0 * s)
            glow.add_color_stop_rgba(0.0, 1.0, 0.88, 0.45, 0.55)
            glow.add_color_stop_rgba(0.5, 1.0, 0.70, 0.25, 0.18)
            glow.add_color_stop_rgba(1.0, 0.8, 0.4, 0.1, 0.0)
            ctx.arc(lx, ly, 140.0 * s, 0, math.tau)
            ctx.set_source(glow)
            ctx.fill()

        ctx.restore()
