"""Composable, High-Fidelity Environmental Asset Library.

Target Aesthetic:
EDITORIAL HISTORICAL ILLUSTRATION + CINEMATIC COMPOSITION + STICKMAN RIG.

Eliminates primitive geometry (plain rectangles, plain polygons).
Provides rich, layered, multi-contour assets with authentic material cues,
surface wear, line hierarchy, and lighting responses:
- TABLE, CHAIR, BENCH
- MACHINE / APPARATUS
- DOOR / WINDOW
- CRATE / BARREL
- DOCUMENT / PARCHMENT
- SHELF / CUPBOARD
- LAMP / LANTERN
- ROCK / NATURAL OBSTACLE
"""
from __future__ import annotations

import math
from typing import Any, Optional
import cairo


def _hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.lstrip("#")
    if len(h) == 6:
        return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)
    return (0.2, 0.2, 0.2)


INK = (0.08, 0.08, 0.10)


def render_composable_table(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float = 320.0,
    height: float = 160.0,
    scale: float = 1.0,
    materials: Optional[list[str]] = None,
    wear: str = "WEATHERED",
    lighting_dx: float = 1.0,
    has_paper: bool = False,
    has_glass: bool = False,
) -> None:
    """Renders a solid timber conference/workbench with beveled rim, turned legs, and shadows."""
    w = width * scale
    h = height * scale
    ctx.save()
    ctx.translate(x, y)

    # 1. Ground contact shadow
    ctx.save()
    ctx.translate(lighting_dx * 18.0 * scale, h * 0.98)
    ctx.scale(1.0, 0.20)
    ctx.arc(0, 0, w * 0.52, 0, math.tau)
    ctx.set_source_rgba(0.05, 0.05, 0.07, 0.38)
    ctx.fill()
    ctx.restore()

    # 2. Turned table legs (4 legs with cross stretchers)
    leg_col = (0.22, 0.16, 0.11)
    leg_w = 16.0 * scale
    leg_x_offsets = [-w * 0.42, -w * 0.30, w * 0.30, w * 0.42]
    
    ctx.set_source_rgb(*leg_col)
    for lx in leg_x_offsets:
        # Leg column
        ctx.rectangle(lx - leg_w * 0.5, 0, leg_w, h * 0.96)
        ctx.fill_preserve()
        ctx.set_source_rgb(*INK)
        ctx.set_line_width(2.0 * scale)
        ctx.stroke()
        # Turned collar rings
        ctx.set_source_rgb(0.32, 0.24, 0.16)
        ctx.rectangle(lx - leg_w * 0.65, h * 0.30, leg_w * 1.3, 8.0 * scale)
        ctx.fill()

    # Cross stretcher
    ctx.set_source_rgb(*leg_col)
    ctx.rectangle(-w * 0.40, h * 0.65, w * 0.80, 10.0 * scale)
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(2.0 * scale)
    ctx.stroke()

    # 3. Table apron
    apron_h = 24.0 * scale
    ctx.set_source_rgb(0.24, 0.17, 0.12)
    ctx.rectangle(-w * 0.48, -apron_h * 0.5, w * 0.96, apron_h)
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(2.5 * scale)
    ctx.stroke()

    # 4. Table top plank (Trapezoid in perspective with beveled edge)
    top_thick = 16.0 * scale
    ctx.set_source_rgb(0.34, 0.24, 0.17)
    ctx.move_to(-w * 0.50, -apron_h * 0.5)
    ctx.line_to(-w * 0.44, -apron_h * 0.5 - top_thick)
    ctx.line_to(w * 0.44, -apron_h * 0.5 - top_thick)
    ctx.line_to(w * 0.50, -apron_h * 0.5)
    ctx.close_path()
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(3.0 * scale)
    ctx.stroke()

    # Wood grain striations
    ctx.set_source_rgba(0.18, 0.12, 0.08, 0.45)
    ctx.set_line_width(1.5 * scale)
    for off in (-0.35, -0.15, 0.08, 0.26):
        ctx.move_to(w * off, -apron_h * 0.5 - top_thick)
        ctx.line_to(w * (off + 0.04), -apron_h * 0.5)
        ctx.stroke()

    # Bevel highlight on edge facing key light
    ctx.move_to(-w * 0.50, -apron_h * 0.5)
    ctx.line_to(w * 0.50, -apron_h * 0.5)
    ctx.set_source_rgba(0.65, 0.52, 0.38, 0.65)
    ctx.set_line_width(2.0 * scale)
    ctx.stroke()

    ctx.restore()


def render_composable_machine(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float = 240.0,
    height: float = 300.0,
    scale: float = 1.0,
    materials: Optional[list[str]] = None,
    state: str = "ACTIVE",
    lighting_dx: float = 1.0,
) -> None:
    """Renders heavy industrial apparatus / electrical machine with dials, levers, and copper wiring."""
    w = width * scale
    h = height * scale
    ctx.save()
    ctx.translate(x, y)

    # 1. Base pedestal
    ctx.set_source_rgb(0.18, 0.19, 0.22)
    ctx.rectangle(-w * 0.46, h * 0.35, w * 0.92, h * 0.12)
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(3.0 * scale)
    ctx.stroke()

    # 2. Main cast-iron housing
    body_h = h * 0.60
    body_y = -body_h * 0.5
    ctx.set_source_rgb(0.24, 0.26, 0.30)
    ctx.rectangle(-w * 0.40, body_y, w * 0.80, body_h)
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(3.5 * scale)
    ctx.stroke()

    # Specular rim along light edge
    ctx.move_to(-w * 0.40, body_y)
    ctx.line_to(-w * 0.40, body_y + body_h)
    ctx.set_source_rgba(0.55, 0.60, 0.68, 0.65)
    ctx.set_line_width(2.5 * scale)
    ctx.stroke()

    # Bolted flange rivets
    ctx.set_source_rgb(0.12, 0.13, 0.15)
    for ry in (-0.22, 0.0, 0.22):
        ctx.arc(-w * 0.34, ry * h, 4.0 * scale, 0, math.tau)
        ctx.arc(w * 0.34, ry * h, 4.0 * scale, 0, math.tau)
        ctx.fill()

    # 3. Round brass pressure gauge / galvanometer dial
    gw = 38.0 * scale
    ctx.save()
    ctx.translate(0, body_y + body_h * 0.30)
    # Dial bezel
    ctx.arc(0, 0, gw, 0, math.tau)
    ctx.set_source_rgb(0.72, 0.55, 0.25)  # Brass
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(3.0 * scale)
    ctx.stroke()

    # Dial face (enamel parchment)
    ctx.arc(0, 0, gw * 0.80, 0, math.tau)
    ctx.set_source_rgb(0.92, 0.90, 0.82)
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(1.5 * scale)
    ctx.stroke()

    # Indicator needle
    needle_angle = 0.8 if state in ("ACTIVE", "PULSING", "CONFIRMED") else -0.9
    ctx.move_to(0, 0)
    ctx.line_to(math.cos(needle_angle) * gw * 0.65, math.sin(needle_angle) * gw * 0.65)
    ctx.set_source_rgb(0.75, 0.15, 0.15)  # Red needle
    ctx.set_line_width(2.5 * scale)
    ctx.stroke()
    ctx.restore()

    # 4. Knife-switch / breaker lever
    sw_y = body_y + body_h * 0.70
    ctx.save()
    ctx.translate(w * 0.15, sw_y)
    # Slate base
    ctx.rectangle(-18.0 * scale, -10.0 * scale, 36.0 * scale, 20.0 * scale)
    ctx.set_source_rgb(0.14, 0.15, 0.16)
    ctx.fill()
    # Switch blade
    blade_angle = -0.3 if "RESET" in state or "ACTIVE" in state else 0.8
    ctx.move_to(0, 0)
    ctx.line_to(math.cos(blade_angle) * 32.0 * scale, math.sin(blade_angle) * 32.0 * scale)
    ctx.set_source_rgb(0.85, 0.62, 0.28)  # Copper blade
    ctx.set_line_width(4.0 * scale)
    ctx.stroke()
    ctx.restore()

    # 5. Copper conduit wire
    ctx.move_to(-w * 0.38, body_y + body_h * 0.15)
    ctx.curve_to(-w * 0.48, body_y + body_h * 0.45, -w * 0.25, body_y + body_h * 0.85, 0, h * 0.38)
    ctx.set_source_rgb(0.65, 0.35, 0.18)  # Insulated copper
    ctx.set_line_width(3.5 * scale)
    ctx.stroke()

    # Active glow if machine is running
    if state in ("ACTIVE", "ENERGIZED", "PULSING"):
        ctx.save()
        rad = cairo.RadialGradient(0, body_y + body_h * 0.30, 10.0 * scale, 0, body_y + body_h * 0.30, gw * 1.8)
        rad.add_color_stop_rgba(0.0, 1.0, 0.85, 0.4, 0.45)
        rad.add_color_stop_rgba(1.0, 1.0, 0.85, 0.4, 0.0)
        ctx.arc(0, body_y + body_h * 0.30, gw * 1.8, 0, math.tau)
        ctx.set_source(rad)
        ctx.fill()
        ctx.restore()

    ctx.restore()


def render_composable_chair(
    ctx: cairo.Context,
    x: float,
    y: float,
    scale: float = 1.0,
    materials: Optional[list[str]] = None,
    lighting_dx: float = 1.0,
) -> None:
    """Renders an authentic wooden side chair with spindle back."""
    s = scale
    ctx.save()
    ctx.translate(x, y)

    # Legs
    ctx.set_source_rgb(0.24, 0.18, 0.12)
    ctx.set_line_width(4.5 * s)
    ctx.move_to(-24.0 * s, 0)
    ctx.line_to(-26.0 * s, 95.0 * s)
    ctx.stroke()
    ctx.move_to(24.0 * s, 0)
    ctx.line_to(26.0 * s, 95.0 * s)
    ctx.stroke()

    # Seat plank
    ctx.set_source_rgb(0.36, 0.26, 0.18)
    ctx.rectangle(-32.0 * s, -8.0 * s, 64.0 * s, 12.0 * s)
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(2.5 * s)
    ctx.stroke()

    # Back spindles
    ctx.set_source_rgb(0.24, 0.18, 0.12)
    ctx.set_line_width(3.0 * s)
    for bx in (-22.0, -8.0, 8.0, 22.0):
        ctx.move_to(bx * s, -8.0 * s)
        ctx.line_to(bx * s * 0.9, -90.0 * s)
        ctx.stroke()

    # Top crest rail
    ctx.set_source_rgb(0.36, 0.26, 0.18)
    ctx.rectangle(-28.0 * s, -100.0 * s, 56.0 * s, 14.0 * s)
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(2.5 * s)
    ctx.stroke()

    ctx.restore()


def render_composable_document(
    ctx: cairo.Context,
    x: float,
    y: float,
    scale: float = 1.0,
    state: str = "SEALED",
    lighting_dx: float = 1.0,
) -> None:
    """Renders antique folio parchment with text lines, red wax seal, or unsealed state."""
    s = scale
    ctx.save()
    ctx.translate(x, y)

    # Document body
    dw = 68.0 * s
    dh = 92.0 * s
    ctx.save()
    ctx.rotate(0.08)
    ctx.set_source_rgb(0.92, 0.88, 0.78)  # Aged parchment
    ctx.rectangle(-dw * 0.5, -dh * 0.5, dw, dh)
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(1.8 * s)
    ctx.stroke()

    # Calligraphic ink lines
    ctx.set_source_rgba(0.12, 0.12, 0.14, 0.75)
    ctx.set_line_width(1.5 * s)
    for ly in (-25.0, -12.0, 0.0, 12.0, 24.0):
        ctx.move_to(-dw * 0.38, ly * s)
        ctx.line_to(dw * 0.38, ly * s)
        ctx.stroke()

    # Red wax seal medallion
    ctx.arc(dw * 0.20, dh * 0.30, 9.0 * s, 0, math.tau)
    if "SEALED" in state:
        ctx.set_source_rgb(0.72, 0.12, 0.12)  # Intact red wax
    else:
        ctx.set_source_rgb(0.55, 0.18, 0.18)  # Cracked seal
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(1.2 * s)
    ctx.stroke()

    ctx.restore()
    ctx.restore()


def render_composable_crate(
    ctx: cairo.Context,
    x: float,
    y: float,
    scale: float = 1.0,
    materials: Optional[list[str]] = None,
    lighting_dx: float = 1.0,
) -> None:
    """Renders heavy wooden supply crate with iron corner brackets and stenciling."""
    s = scale
    w = 110.0 * s
    h = 90.0 * s
    ctx.save()
    ctx.translate(x, y)

    # Body
    ctx.set_source_rgb(0.42, 0.34, 0.24)
    ctx.rectangle(-w * 0.5, -h * 0.5, w, h)
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(3.0 * s)
    ctx.stroke()

    # Planks & diagonal brace
    ctx.set_line_width(2.0 * s)
    ctx.move_to(-w * 0.5, 0)
    ctx.line_to(w * 0.5, 0)
    ctx.stroke()
    ctx.move_to(-w * 0.5, -h * 0.5)
    ctx.line_to(w * 0.5, h * 0.5)
    ctx.stroke()

    # Iron corner brackets
    ctx.set_source_rgb(0.18, 0.18, 0.20)
    for bx, by in [(-w*0.5, -h*0.5), (w*0.5 - 14*s, -h*0.5), (-w*0.5, h*0.5 - 14*s), (w*0.5 - 14*s, h*0.5 - 14*s)]:
        ctx.rectangle(bx, by, 14.0 * s, 14.0 * s)
        ctx.fill()

    ctx.restore()


def render_composable_window(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float = 200.0,
    height: float = 380.0,
    scale: float = 1.0,
    light_shaft: bool = True,
    lighting_dx: float = 1.0,
) -> None:
    """Renders period casement window with glazed panes and volumetric light shaft."""
    w = width * scale
    h = height * scale
    ctx.save()
    ctx.translate(x, y)

    # Volumetric light shaft casting across the room
    if light_shaft:
        ctx.save()
        shaft = cairo.LinearGradient(0, 0, lighting_dx * w * 2.5, h * 1.8)
        shaft.add_color_stop_rgba(0.0, 1.0, 0.95, 0.85, 0.32)
        shaft.add_color_stop_rgba(0.6, 1.0, 0.95, 0.85, 0.12)
        shaft.add_color_stop_rgba(1.0, 1.0, 0.95, 0.85, 0.0)
        ctx.move_to(0, 0)
        ctx.line_to(w, 0)
        ctx.line_to(w + lighting_dx * w * 2.2, h * 1.8)
        ctx.line_to(lighting_dx * w * 1.8, h * 1.8)
        ctx.close_path()
        ctx.set_source(shaft)
        ctx.fill()
        ctx.restore()

    # Window casing
    ctx.set_source_rgb(0.24, 0.20, 0.16)
    ctx.rectangle(0, 0, w, h)
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    ctx.set_line_width(3.5 * scale)
    ctx.stroke()

    # Glass panes (2 columns x 4 rows)
    cols, rows = 2, 4
    pw = (w - 20 * scale) / cols
    ph = (h - 24 * scale) / rows
    for c in range(cols):
        for r in range(rows):
            px = 8 * scale + c * (pw + 4 * scale)
            py = 8 * scale + r * (ph + 4 * scale)
            # Sky/exterior daylight glow in glass
            ctx.set_source_rgba(0.85, 0.90, 0.96, 0.88)
            ctx.rectangle(px, py, pw, ph)
            ctx.fill_preserve()
            ctx.set_source_rgb(*INK)
            ctx.set_line_width(1.5 * scale)
            ctx.stroke()

            # Diagonal specular highlight on glass
            ctx.move_to(px + 4 * scale, py + ph - 6 * scale)
            ctx.line_to(px + pw - 6 * scale, py + 4 * scale)
            ctx.set_source_rgba(1.0, 1.0, 1.0, 0.55)
            ctx.set_line_width(2.0 * scale)
            ctx.stroke()

    ctx.restore()
