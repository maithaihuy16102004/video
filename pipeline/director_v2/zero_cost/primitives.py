"""Parametric Procedural Environment Primitives for PyCairo.

Provides reusable, high-fidelity visual building blocks for:
- Architecture (columns, loggias, facades, casement windows, timber revetments)
- Terrain (perspective cobblestones, mud duckboards, puddles, perspective floorboards)
- Military (sandbag walls, barbed wire entanglements, artillery craters, ammo crates)
- Interior (cast-iron hospital beds, tavern tables & steins, brass lanterns, wainscoting)
- Atmosphere (volumetric light shafts, smoke plumes, ground mist, rain streaks, lens vignette)

All primitives accept lighting, perspective vanishing points, scale, and wear parameters.
"""
from __future__ import annotations

import math
import random
from typing import Sequence
import cairo


# ==============================================================================
# 0. MATH & UTILITY HELPERS
# ==============================================================================

def rounded_rect(ctx: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    """Draw a rectangle with rounded corners."""
    r = min(r, w / 2.0, h / 2.0)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


def draw_linear_shaded_rect(
    ctx: cairo.Context,
    x: float,
    y: float,
    w: float,
    h: float,
    color_left: tuple[float, float, float],
    color_right: tuple[float, float, float],
) -> None:
    """Draw a rectangle filled with a horizontal linear gradient."""
    grad = cairo.LinearGradient(x, y, x + w, y)
    grad.add_color_stop_rgb(0.0, *color_left)
    grad.add_color_stop_rgb(1.0, *color_right)
    ctx.rectangle(x, y, w, h)
    ctx.set_source(grad)
    ctx.fill()


def apply_surface_hatch(
    ctx: cairo.Context,
    x: float,
    y: float,
    w: float,
    h: float,
    spacing: float = 12.0,
    angle_rad: float = math.pi / 4,
    color_rgba: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.08),
) -> None:
    """Apply architectural cross-hatch or angle hatch for tactile illustrated texture."""
    ctx.save()
    ctx.rectangle(x, y, w, h)
    ctx.clip()
    ctx.set_source_rgba(*color_rgba)
    ctx.set_line_width(1.0)

    diag = math.hypot(w, h)
    num_lines = int(diag / max(4.0, spacing))
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    cx, cy = x + w / 2.0, y + h / 2.0
    for i in range(-num_lines, num_lines):
        offset = i * spacing
        x1 = cx + offset * cos_a - diag * sin_a
        y1 = cy + offset * sin_a + diag * cos_a
        x2 = cx + offset * cos_a + diag * sin_a
        y2 = cy + offset * sin_a - diag * cos_a
        ctx.move_to(x1, y1)
        ctx.line_to(x2, y2)
        ctx.stroke()
    ctx.restore()


# ==============================================================================
# 1. ARCHITECTURAL PRIMITIVES
# ==============================================================================

def draw_stone_column(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float,
    height: float,
    style: str = "CORINTHIAN",
    lighting_dx: float = 1.0,
    stone_color: tuple[float, float, float] = (0.80, 0.78, 0.74),
) -> None:
    """Draw a monumental stone column with capital, fluting, base, and cylindrical shading."""
    ctx.save()
    ink = (0.12, 0.13, 0.16)

    # 1. Plinth / Base (bottom 10% of height)
    base_h = height * 0.09
    base_y = y + height - base_h
    base_w = width * 1.35
    base_x = x - (base_w - width) / 2.0

    # Base steps
    step1_h = base_h * 0.45
    step2_h = base_h * 0.55
    ctx.rectangle(base_x - 8, base_y + step1_h, base_w + 16, step2_h)
    ctx.set_source_rgb(stone_color[0] * 0.85, stone_color[1] * 0.85, stone_color[2] * 0.85)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.5)
    ctx.stroke()

    ctx.rectangle(base_x, base_y, base_w, step1_h)
    ctx.set_source_rgb(*stone_color)
    ctx.fill_preserve()
    ctx.stroke()

    # 2. Capital (top 12% of height)
    cap_h = height * 0.12
    cap_w = width * 1.45
    cap_x = x - (cap_w - width) / 2.0

    # Abacus top slab
    abacus_h = cap_h * 0.28
    ctx.rectangle(cap_x, y, cap_w, abacus_h)
    ctx.set_source_rgb(stone_color[0] * 0.95, stone_color[1] * 0.95, stone_color[2] * 0.95)
    ctx.fill_preserve()
    ctx.stroke()

    # Volutes / Foliage capital bell
    ctx.move_to(cap_x + 6, y + abacus_h)
    ctx.curve_to(
        cap_x - 4, y + cap_h * 0.7,
        x, y + cap_h,
        x + width * 0.15, y + cap_h
    )
    ctx.line_to(x + width * 0.85, y + cap_h)
    ctx.curve_to(
        x + width, y + cap_h,
        cap_x + cap_w + 4, y + cap_h * 0.7,
        cap_x + cap_w - 6, y + abacus_h
    )
    ctx.close_path()
    ctx.set_source_rgb(stone_color[0] * 0.90, stone_color[1] * 0.90, stone_color[2] * 0.88)
    ctx.fill_preserve()
    ctx.stroke()

    # Capital volute curls
    ctx.arc(cap_x + 16, y + abacus_h + 12, 10, 0, math.tau)
    ctx.arc(cap_x + cap_w - 16, y + abacus_h + 12, 10, 0, math.tau)
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.0)
    ctx.stroke()

    # 3. Shaft (middle section)
    shaft_y = y + cap_h
    shaft_h = base_y - shaft_y

    # Cylindrical lighting gradient
    grad = cairo.LinearGradient(x, shaft_y, x + width, shaft_y)
    if lighting_dx >= 0:  # Key light from left
        grad.add_color_stop_rgb(0.0, stone_color[0] * 1.05, stone_color[1] * 1.05, stone_color[2] * 1.05)
        grad.add_color_stop_rgb(0.35, stone_color[0] * 0.98, stone_color[1] * 0.98, stone_color[2] * 0.98)
        grad.add_color_stop_rgb(1.0, stone_color[0] * 0.65, stone_color[1] * 0.65, stone_color[2] * 0.68)
    else:  # Key light from right
        grad.add_color_stop_rgb(0.0, stone_color[0] * 0.65, stone_color[1] * 0.65, stone_color[2] * 0.68)
        grad.add_color_stop_rgb(0.65, stone_color[0] * 0.98, stone_color[1] * 0.98, stone_color[2] * 0.98)
        grad.add_color_stop_rgb(1.0, stone_color[0] * 1.05, stone_color[1] * 1.05, stone_color[2] * 1.05)

    ctx.rectangle(x, shaft_y, width, shaft_h)
    ctx.set_source(grad)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.5)
    ctx.stroke()

    # Fluting lines (vertical flutes across column body)
    flute_count = 6
    flute_spacing = width / (flute_count + 1)
    for i in range(1, flute_count + 1):
        fx = x + i * flute_spacing
        ctx.move_to(fx, shaft_y + 8)
        ctx.line_to(fx, shaft_y + shaft_h - 8)
        # Shadow fluting line
        ctx.set_source_rgba(0.1, 0.12, 0.15, 0.35)
        ctx.set_line_width(1.8)
        ctx.stroke()
        # Highlight edge line
        ctx.move_to(fx + (1.2 if lighting_dx >= 0 else -1.2), shaft_y + 8)
        ctx.line_to(fx + (1.2 if lighting_dx >= 0 else -1.2), shaft_y + shaft_h - 8)
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.25)
        ctx.set_line_width(1.0)
        ctx.stroke()

    ctx.restore()


def draw_arched_loggia(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float,
    height: float,
    arch_count: int = 3,
    depth_px: float = 35.0,
    lighting_dx: float = 1.0,
    wall_color: tuple[float, float, float] = (0.78, 0.74, 0.70),
) -> None:
    """Draw a classical vaulted arched loggia (Feldherrnhalle / Prussian colonnade style)."""
    ctx.save()
    ink = (0.10, 0.12, 0.15)
    span_w = width / arch_count
    pier_w = span_w * 0.22
    opening_w = span_w - pier_w

    # Outer architrave / lintel beam
    lintel_h = height * 0.15
    ctx.rectangle(x, y, width, lintel_h)
    ctx.set_source_rgb(wall_color[0] * 1.02, wall_color[1] * 1.02, wall_color[2] * 1.02)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(3.0)
    ctx.stroke()

    # Dentil cornice details along lintel
    dentil_w = 12.0
    dentil_spacing = 18.0
    for dx in range(int(x + 10), int(x + width - 10), int(dentil_spacing)):
        ctx.rectangle(dx, y + lintel_h - 8, dentil_w, 6)
        ctx.set_source_rgb(wall_color[0] * 0.85, wall_color[1] * 0.85, wall_color[2] * 0.85)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.0)
        ctx.stroke()

    # Arches and piers
    arch_y = y + lintel_h
    arch_h = height - lintel_h

    for i in range(arch_count):
        ax = x + i * span_w + pier_w * 0.5
        spring_y = arch_y + arch_h * 0.42
        r = opening_w / 2.0

        # Interior shadow depth behind arch
        ctx.save()
        ctx.move_to(ax, arch_y + arch_h)
        ctx.line_to(ax, spring_y)
        ctx.arc(ax + r, spring_y, r, math.pi, 0)
        ctx.line_to(ax + opening_w, arch_y + arch_h)
        ctx.close_path()
        # Interior dark vault
        inner_grad = cairo.LinearGradient(ax, spring_y - r, ax, arch_y + arch_h)
        inner_grad.add_color_stop_rgb(0.0, 0.16, 0.18, 0.22)
        inner_grad.add_color_stop_rgb(1.0, 0.28, 0.26, 0.24)
        ctx.set_source(inner_grad)
        ctx.fill()
        ctx.restore()

        # Arch soffit inner depth extrusion
        ctx.save()
        ctx.arc(ax + r, spring_y, r, math.pi, 0)
        ctx.arc_negative(ax + r + depth_px * 0.4, spring_y, r * 0.94, 0, math.pi)
        ctx.close_path()
        ctx.set_source_rgba(0.08, 0.08, 0.10, 0.45)
        ctx.fill()
        ctx.restore()

        # Front arch outline & voussoirs (wedge-shaped arch stones)
        ctx.arc(ax + r, spring_y, r, math.pi, 0)
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(3.5)
        ctx.stroke()

        # Keystone at top of arch
        ctx.rectangle(ax + r - 12, spring_y - r - 8, 24, 20)
        ctx.set_source_rgb(wall_color[0] * 1.05, wall_color[1] * 1.05, wall_color[2] * 1.05)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.0)
        ctx.stroke()

    # Piers between arches
    for i in range(arch_count + 1):
        px = x + i * span_w - pier_w * 0.5
        if i == 0:
            px = x
            pw = pier_w * 0.5
        elif i == arch_count:
            pw = pier_w * 0.5
        else:
            pw = pier_w

        draw_stone_column(
            ctx, px, arch_y, pw, arch_h,
            style="DORIC", lighting_dx=lighting_dx, stone_color=wall_color
        )

    ctx.restore()


def draw_building_facade(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float,
    height: float,
    stories: int = 3,
    bays: int = 4,
    style: str = "NEOCLASSICAL",
    lighting_dx: float = 1.0,
    facade_color: tuple[float, float, float] = (0.75, 0.72, 0.68),
) -> None:
    """Draw a multi-story historical European building facade with window rhythms and cornices."""
    ctx.save()
    ink = (0.10, 0.12, 0.15)

    # Base wall with directional shading
    grad = cairo.LinearGradient(x, y, x + width, y)
    if lighting_dx >= 0:
        grad.add_color_stop_rgb(0.0, facade_color[0] * 1.05, facade_color[1] * 1.05, facade_color[2] * 1.02)
        grad.add_color_stop_rgb(1.0, facade_color[0] * 0.85, facade_color[1] * 0.85, facade_color[2] * 0.88)
    else:
        grad.add_color_stop_rgb(0.0, facade_color[0] * 0.85, facade_color[1] * 0.85, facade_color[2] * 0.88)
        grad.add_color_stop_rgb(1.0, facade_color[0] * 1.05, facade_color[1] * 1.05, facade_color[2] * 1.02)

    ctx.rectangle(x, y, width, height)
    ctx.set_source(grad)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(3.0)
    ctx.stroke()

    # Mansard roof or attic parapet
    roof_h = height * 0.16
    ctx.move_to(x - 6, y)
    ctx.line_to(x + 18, y - roof_h)
    ctx.line_to(x + width - 18, y - roof_h)
    ctx.line_to(x + width + 6, y)
    ctx.close_path()
    ctx.set_source_rgb(0.28, 0.32, 0.38)  # Slate zinc roof
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.5)
    ctx.stroke()

    # Dormer windows in roof
    dormer_w = width / (bays + 1) * 0.65
    for b in range(1, bays + 1):
        dx = x + b * (width / (bays + 1)) - dormer_w / 2.0
        ctx.rectangle(dx, y - roof_h * 0.85, dormer_w, roof_h * 0.7)
        ctx.set_source_rgb(0.18, 0.20, 0.25)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.0)
        ctx.stroke()
        # Dormer triangular pediment
        ctx.move_to(dx - 3, y - roof_h * 0.85)
        ctx.line_to(dx + dormer_w / 2.0, y - roof_h * 1.08)
        ctx.line_to(dx + dormer_w + 3, y - roof_h * 0.85)
        ctx.close_path()
        ctx.set_source_rgb(facade_color[0], facade_color[1], facade_color[2])
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.stroke()

    # Floor-separating cornices / string courses
    story_h = height / stories
    for s in range(1, stories):
        cy = y + s * story_h
        ctx.rectangle(x - 4, cy - 6, width + 8, 12)
        ctx.set_source_rgb(facade_color[0] * 1.10, facade_color[1] * 1.10, facade_color[2] * 1.10)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.0)
        ctx.stroke()

    # Windows on each story
    win_w = width / (bays + 1) * 0.52
    win_h = story_h * 0.58
    for s in range(stories):
        sy = y + s * story_h + story_h * 0.22
        for b in range(1, bays + 1):
            wx = x + b * (width / (bays + 1)) - win_w / 2.0
            is_arched = (s == 0 and style == "NEOCLASSICAL")

            # Window deep recess
            ctx.rectangle(wx, sy, win_w, win_h)
            ctx.set_source_rgb(0.14, 0.16, 0.20)  # Dark glass interior
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(2.0)
            ctx.stroke()

            # Window panes crossbars
            ctx.move_to(wx + win_w / 2.0, sy)
            ctx.line_to(wx + win_w / 2.0, sy + win_h)
            ctx.move_to(wx, sy + win_h * 0.45)
            ctx.line_to(wx + win_w, sy + win_h * 0.45)
            ctx.set_source_rgb(0.85, 0.85, 0.88)
            ctx.set_line_width(1.5)
            ctx.stroke()

            # Glass diagonal light reflection
            ctx.save()
            ctx.rectangle(wx + 2, sy + 2, win_w - 4, win_h - 4)
            ctx.clip()
            ctx.move_to(wx, sy + win_h * 0.7)
            ctx.line_to(wx + win_w * 0.7, sy)
            ctx.line_to(wx + win_w, sy)
            ctx.line_to(wx, sy + win_h)
            ctx.close_path()
            ctx.set_source_rgba(1.0, 1.0, 1.0, 0.15)
            ctx.fill()
            ctx.restore()

            # Window sills and pediments
            ctx.rectangle(wx - 4, sy + win_h, win_w + 8, 6)
            ctx.set_source_rgb(facade_color[0] * 1.15, facade_color[1] * 1.15, facade_color[2] * 1.15)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(1.5)
            ctx.stroke()

            if s == 1:  # Piano nobile decorative pediments
                ctx.move_to(wx - 4, sy)
                ctx.line_to(wx + win_w / 2.0, sy - 14)
                ctx.line_to(wx + win_w + 4, sy)
                ctx.close_path()
                ctx.set_source_rgb(facade_color[0] * 1.08, facade_color[1] * 1.08, facade_color[2] * 1.08)
                ctx.fill_preserve()
                ctx.set_source_rgb(*ink)
                ctx.stroke()

    ctx.restore()


def draw_prussian_window(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float,
    height: float,
    arched: bool = True,
    light_shaft: bool = True,
    lighting_dx: float = 1.0,
    wall_color: tuple[float, float, float] = (0.84, 0.86, 0.88),
) -> None:
    """Draw a large tall Prussian hospital casement window with deep embrasure and optional sunbeam."""
    ctx.save()
    ink = (0.12, 0.14, 0.18)
    frame_inset = 18.0

    # Deep stone/plaster window embrasure (angled inner reveal)
    ctx.save()
    if arched:
        r = width / 2.0
        ctx.move_to(x, y + height)
        ctx.line_to(x, y + r)
        ctx.arc(x + r, y + r, r, math.pi, 0)
        ctx.line_to(x + width, y + height)
        ctx.close_path()
    else:
        ctx.rectangle(x, y, width, height)

    ctx.set_source_rgb(wall_color[0] * 0.90, wall_color[1] * 0.90, wall_color[2] * 0.92)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(3.0)
    ctx.stroke()
    ctx.restore()

    # Inner window glass pane area
    gx = x + frame_inset
    gy = y + frame_inset
    gw = width - frame_inset * 2.0
    gh = height - frame_inset * 2.0
    gr = gw / 2.0

    ctx.save()
    if arched:
        ctx.move_to(gx, gy + gh)
        ctx.line_to(gx, gy + gr)
        ctx.arc(gx + gr, gy + gr, gr, math.pi, 0)
        ctx.line_to(gx + gw, gy + gh)
        ctx.close_path()
    else:
        ctx.rectangle(gx, gy, gw, gh)

    # Sky glow through glass
    sky_grad = cairo.LinearGradient(gx, gy, gx, gy + gh)
    sky_grad.add_color_stop_rgb(0.0, 0.92, 0.96, 1.0)
    sky_grad.add_color_stop_rgb(0.7, 0.85, 0.92, 0.98)
    sky_grad.add_color_stop_rgb(1.0, 0.78, 0.86, 0.92)
    ctx.set_source(sky_grad)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.5)
    ctx.stroke()
    ctx.restore()

    # Window crossbars & muntins
    ctx.save()
    ctx.set_source_rgb(0.24, 0.28, 0.32)
    ctx.set_line_width(3.0)

    # Vertical mullion
    ctx.move_to(gx + gw / 2.0, gy)
    ctx.line_to(gx + gw / 2.0, gy + gh)
    ctx.stroke()

    # Horizontal transoms (3 rows of panes)
    row_h = gh / 4.0
    for r_idx in range(1, 4):
        ty = gy + r_idx * row_h
        ctx.move_to(gx, ty)
        ctx.line_to(gx + gw, ty)
        ctx.stroke()

    # Radial fanlight in arch head
    if arched:
        for angle_deg in [30, 60, 90, 120, 150]:
            rad = math.radians(angle_deg)
            ctx.move_to(gx + gr, gy + gr)
            ctx.line_to(gx + gr - gr * math.cos(rad), gy + gr - gr * math.sin(rad))
            ctx.stroke()
    ctx.restore()

    # Heavy projecting stone sill at base
    sill_h = 16.0
    ctx.rectangle(x - 8, y + height - 4, width + 16, sill_h)
    ctx.set_source_rgb(wall_color[0] * 1.08, wall_color[1] * 1.08, wall_color[2] * 1.08)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.0)
    ctx.stroke()

    # Volumetric light shaft casting across the room
    if light_shaft:
        draw_light_shaft(
            ctx,
            top_x1=gx + 5,
            top_x2=gx + gw - 5,
            bot_x1=gx - gw * 1.8 if lighting_dx >= 0 else gx + gw * 0.8,
            bot_x2=gx + gw * 2.8 if lighting_dx >= 0 else gx - gw * 0.2,
            y_top=gy + gh * 0.2,
            y_bot=y + height + 520,
            color_rgba=(1.0, 0.98, 0.82, 0.18),
        )

    ctx.restore()


def draw_timber_wall(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float,
    height: float,
    planks: int = 7,
    damage: float = 0.2,
    lighting_dx: float = 1.0,
    wood_color: tuple[float, float, float] = (0.38, 0.28, 0.18),
) -> None:
    """Draw a rough wooden trench revetment wall made of heavy pine timbers, planks, and iron spikes."""
    ctx.save()
    ink = (0.08, 0.09, 0.12)
    plank_h = height / planks

    for p in range(planks):
        py = y + p * plank_h
        # Color variation per plank
        var = (math.sin(p * 2.3) * 0.08)
        p_col = (
            max(0.1, min(0.9, wood_color[0] + var)),
            max(0.1, min(0.9, wood_color[1] + var)),
            max(0.08, min(0.9, wood_color[2] + var)),
        )

        ctx.rectangle(x, py, width, plank_h)
        ctx.set_source_rgb(*p_col)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.2)
        ctx.stroke()

        # Wood grain lines
        ctx.save()
        ctx.set_source_rgba(0.06, 0.05, 0.04, 0.35)
        ctx.set_line_width(1.0)
        for g in range(3):
            gy = py + plank_h * (0.25 + g * 0.25)
            ctx.move_to(x, gy)
            for seg in range(1, 10):
                sx = x + seg * (width / 10.0)
                sy = gy + math.sin(seg * 1.5 + p) * 2.5
                ctx.line_to(sx, sy)
            ctx.stroke()
        ctx.restore()

        # Iron spikes / bolt heads fastening timber
        bolt_spacing = width / 5.0
        for b in range(1, 5):
            bx = x + b * bolt_spacing
            by = py + plank_h * 0.5
            ctx.arc(bx, by, 3.5, 0, math.tau)
            ctx.set_source_rgb(0.12, 0.12, 0.14)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(1.0)
            ctx.stroke()

        # Battle damage / bullet gouges if damage > 0
        if damage > 0.15 and p % 2 == 1:
            gouge_x = x + width * ((p * 0.37) % 0.8 + 0.1)
            ctx.arc(gouge_x, py + plank_h * 0.45, 6.0, 0, math.tau)
            ctx.set_source_rgb(0.08, 0.06, 0.05)
            ctx.fill()

    # Vertical bracing upright posts
    post_count = max(2, int(width / 320.0))
    post_w = 34.0
    for i in range(post_count):
        px = x + (i + 0.5) * (width / post_count) - post_w / 2.0
        ctx.rectangle(px, y - 5, post_w, height + 10)
        ctx.set_source_rgb(wood_color[0] * 0.82, wood_color[1] * 0.82, wood_color[2] * 0.80)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(3.0)
        ctx.stroke()

    ctx.restore()


# ==============================================================================
# 2. TERRAIN & GROUND PRIMITIVES
# ==============================================================================

def draw_cobblestone_plane(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float,
    height: float,
    horizon_y: float,
    vp_x: float,
    vp_y: float,
    density: int = 24,
    wetness: float = 0.5,
    lighting_dx: float = 1.0,
    stone_color: tuple[float, float, float] = (0.42, 0.40, 0.38),
) -> None:
    """Draw a street cobblestone surface converging down from horizon with true perspective fan lines."""
    ctx.save()
    ink = (0.10, 0.10, 0.12)

    # Base ground plane with perspective depth gradient
    grad = cairo.LinearGradient(0, y, 0, y + height)
    grad.add_color_stop_rgb(0.0, stone_color[0] * 0.75, stone_color[1] * 0.75, stone_color[2] * 0.75)
    grad.add_color_stop_rgb(1.0, stone_color[0] * 1.15, stone_color[1] * 1.12, stone_color[2] * 1.10)
    ctx.rectangle(x, y, width, height)
    ctx.set_source(grad)
    ctx.fill()

    # Perspective converging street guide lines toward vanishing point
    line_count = 32
    ctx.set_line_width(1.2)
    for i in range(-line_count // 2, line_count // 2 + 1):
        ground_x = vp_x + i * (width / 14.0)
        ctx.move_to(vp_x, vp_y)
        ctx.line_to(ground_x, y + height)
        ctx.set_source_rgba(0.08, 0.08, 0.10, 0.22)
        ctx.stroke()

    # Horizontal row arcs (Bavarian fan pattern cobblestone arches)
    row_count = density
    for r in range(1, row_count + 1):
        # Quadratic spacing for perspective depth falloff
        t = (r / row_count) ** 1.85
        row_y = y + t * height
        row_h = (t * 26.0) + 4.0
        line_w = max(0.8, t * 2.2)

        ctx.set_line_width(line_w)
        ctx.set_source_rgba(0.08, 0.08, 0.10, 0.45)
        ctx.move_to(x, row_y)
        ctx.line_to(x + width, row_y)
        ctx.stroke()

        # Individual cobblestone blocks along row
        stone_w = max(8.0, t * 38.0)
        st_count = int(width / stone_w)
        for s in range(st_count):
            sx = x + s * stone_w + (math.sin(r * 4.3 + s) * stone_w * 0.25)
            # Stone top highlight
            if wetness > 0.2 and t > 0.3:
                ctx.save()
                ctx.rectangle(sx + 2, row_y - row_h + 2, stone_w - 4, row_h * 0.4)
                ctx.set_source_rgba(1.0, 1.0, 1.0, 0.15 * wetness * t)
                ctx.fill()
                ctx.restore()

    # Wet rain puddles reflecting sky in street hollows
    if wetness > 0.3:
        for px, py, prx, pry in [
            (x + width * 0.25, y + height * 0.72, 75.0, 22.0),
            (x + width * 0.68, y + height * 0.85, 110.0, 28.0),
            (x + width * 0.45, y + height * 0.55, 45.0, 12.0),
        ]:
            draw_puddle_reflection(ctx, px, py, prx, pry, sky_color=(0.70, 0.74, 0.82))

    ctx.restore()


def draw_mud_duckboard_corridor(
    ctx: cairo.Context,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    vp_x: float,
    vp_y: float,
    width_near: float = 380.0,
    width_far: float = 55.0,
    slat_count: int = 28,
    lighting_dx: float = 1.0,
) -> None:
    """Draw a WWI trench duckboard walkway (wooden slats) converging deeply into distance through mud."""
    ctx.save()
    ink = (0.06, 0.06, 0.08)

    # Mud corridor bed polygon
    ctx.move_to(x1 - width_near * 0.65, y1)
    ctx.line_to(x2 - width_far * 0.75, y2)
    ctx.line_to(x2 + width_far * 0.75, y2)
    ctx.line_to(x1 + width_near * 0.65, y1)
    ctx.close_path()

    mud_grad = cairo.LinearGradient(0, y2, 0, y1)
    mud_grad.add_color_stop_rgb(0.0, 0.22, 0.18, 0.13)
    mud_grad.add_color_stop_rgb(1.0, 0.34, 0.27, 0.20)
    ctx.set_source(mud_grad)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(3.0)
    ctx.stroke()

    # Duckboard slats laid across the walkway
    wood_col = (0.42, 0.34, 0.24)
    for i in range(slat_count):
        # Perspective interpolation from far (y2) to near (y1)
        t = (i / slat_count) ** 1.75
        sy = y2 + t * (y1 - y2)
        sw = width_far + t * (width_near - width_far)
        sh = max(3.0, t * 14.0)

        cx = x2 + t * (x1 - x2)
        sx = cx - sw / 2.0

        # Slat shadow into mud below
        ctx.rectangle(sx + 3, sy + sh, sw, sh * 0.5)
        ctx.set_source_rgba(0.04, 0.04, 0.04, 0.60)
        ctx.fill()

        # Wooden slat top
        ctx.rectangle(sx, sy, sw, sh)
        ctx.set_source_rgb(wood_col[0] * (0.8 + t * 0.3), wood_col[1] * (0.8 + t * 0.3), wood_col[2] * (0.8 + t * 0.3))
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(max(1.0, t * 2.2))
        ctx.stroke()

        # Center longitudinal wooden runner stringers
        if i == 0:
            pass

    # Longitudinal side timbers (stringers holding slats)
    for side in [-1.0, 1.0]:
        ctx.move_to(x2 + side * width_far * 0.42, y2)
        ctx.line_to(x1 + side * width_near * 0.42, y1)
        ctx.set_source_rgba(0.05, 0.05, 0.05, 0.55)
        ctx.set_line_width(max(2.0, width_near * 0.025))
        ctx.stroke()

    ctx.restore()


def draw_puddle_reflection(
    ctx: cairo.Context,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    sky_color: tuple[float, float, float] = (0.65, 0.70, 0.78),
) -> None:
    """Draw a stagnant muddy puddle reflecting the sky with ripple rings and greasy oil sheen."""
    ctx.save()
    ink = (0.08, 0.08, 0.10)

    # Muddy rim depression
    ctx.save()
    ctx.translate(cx, cy)
    ctx.scale(1.0, ry / rx)
    ctx.arc(0, 0, rx + 6.0, 0, math.tau)
    ctx.set_source_rgb(0.18, 0.14, 0.10)  # Dark saturated wet mud
    ctx.fill()
    ctx.restore()

    # Water reflection surface
    ctx.save()
    ctx.translate(cx, cy)
    ctx.scale(1.0, ry / rx)
    ctx.arc(0, 0, rx, 0, math.tau)

    grad = cairo.RadialGradient(0, -rx * 0.3, rx * 0.1, 0, 0, rx)
    grad.add_color_stop_rgb(0.0, sky_color[0] * 1.1, sky_color[1] * 1.1, sky_color[2] * 1.1)
    grad.add_color_stop_rgb(0.7, sky_color[0], sky_color[1], sky_color[2])
    grad.add_color_stop_rgb(1.0, 0.22, 0.20, 0.18)
    ctx.set_source(grad)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(1.5)
    ctx.stroke()

    # Ripple ring
    ctx.arc(0, 0, rx * 0.55, 0, math.tau)
    ctx.set_source_rgba(1.0, 1.0, 1.0, 0.30)
    ctx.set_line_width(1.0)
    ctx.stroke()
    ctx.restore()

    ctx.restore()


def draw_distressed_wood_floor(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float,
    height: float,
    vp_x: float,
    vp_y: float,
    planks: int = 14,
    lighting_dx: float = 1.0,
    floor_color: tuple[float, float, float] = (0.52, 0.44, 0.36),
) -> None:
    """Draw interior wooden hospital or tavern floorboards converging toward vanishing point."""
    ctx.save()
    ink = (0.12, 0.10, 0.08)

    # Floor base fill
    ctx.rectangle(x, y, width, height)
    ctx.set_source_rgb(*floor_color)
    ctx.fill()

    # Perspective plank joints converging to vp_x, vp_y
    for i in range(planks + 1):
        target_x = x + i * (width / planks)
        ctx.move_to(vp_x, vp_y)
        ctx.line_to(target_x, y + height)
        ctx.set_source_rgba(0.08, 0.06, 0.04, 0.45)
        ctx.set_line_width(2.0)
        ctx.stroke()

    # Staggered butt joints across floor
    for p in range(planks):
        st_x = x + p * (width / planks)
        for row in range(4):
            by = y + height * (0.2 + row * 0.22 + (p % 3) * 0.06)
            bw = width / planks
            ctx.move_to(st_x, by)
            ctx.line_to(st_x + bw, by)
            ctx.set_source_rgba(0.06, 0.05, 0.04, 0.35)
            ctx.set_line_width(1.5)
            ctx.stroke()

    ctx.restore()


# ==============================================================================
# 3. MILITARY PRIMITIVES
# ==============================================================================

def draw_sandbag_revetment(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float,
    height: float,
    layers: int = 5,
    bags_per_layer: int = 7,
    damage: float = 0.1,
    lighting_dx: float = 1.0,
    bag_color: tuple[float, float, float] = (0.62, 0.56, 0.44),
) -> None:
    """Draw a defensive parapet of stacked burlap sandbags with seams, tied ear corners, and sagging curves."""
    ctx.save()
    ink = (0.08, 0.08, 0.10)
    layer_h = height / layers

    for l_idx in range(layers):
        ly = y + height - (l_idx + 1) * layer_h
        # Stagger alternating layers by half a bag width (running bond pattern)
        stagger = (l_idx % 2) * (width / bags_per_layer * 0.5)
        bag_w = (width / bags_per_layer) * 1.08

        for b_idx in range(-1, bags_per_layer + 1):
            bx = x + b_idx * (width / bags_per_layer) + stagger
            # Individual burlap sandbag with pillow curve
            ctx.save()
            rounded_rect(ctx, bx + 2, ly + 2, bag_w - 4, layer_h - 2, 7.0)

            # Sandbag shading
            b_grad = cairo.LinearGradient(bx, ly, bx + bag_w, ly + layer_h)
            if lighting_dx >= 0:
                b_grad.add_color_stop_rgb(0.0, bag_color[0] * 1.08, bag_color[1] * 1.08, bag_color[2] * 1.05)
                b_grad.add_color_stop_rgb(1.0, bag_color[0] * 0.75, bag_color[1] * 0.72, bag_color[2] * 0.65)
            else:
                b_grad.add_color_stop_rgb(0.0, bag_color[0] * 0.75, bag_color[1] * 0.72, bag_color[2] * 0.65)
                b_grad.add_color_stop_rgb(1.0, bag_color[0] * 1.08, bag_color[1] * 1.08, bag_color[2] * 1.05)

            ctx.set_source(b_grad)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(2.2)
            ctx.stroke()

            # Sandbag tied end ears
            ctx.arc(bx + 4, ly + layer_h * 0.5, 3.5, 0, math.tau)
            ctx.set_source_rgb(*ink)
            ctx.fill()

            # Center seam crease
            ctx.move_to(bx + bag_w * 0.25, ly + layer_h * 0.5)
            ctx.line_to(bx + bag_w * 0.75, ly + layer_h * 0.5)
            ctx.set_source_rgba(0.1, 0.1, 0.1, 0.3)
            ctx.set_line_width(1.0)
            ctx.stroke()

            ctx.restore()

    ctx.restore()


def draw_barbed_wire_entanglement(
    ctx: cairo.Context,
    pts: Sequence[tuple[float, float]],
    post_count: int = 4,
    lighting_dx: float = 1.0,
) -> None:
    """Draw a concertina barbed wire entanglement with wooden picket stakes and spiraling wire coils."""
    ctx.save()
    ink = (0.12, 0.12, 0.14)

    if len(pts) < 2:
        ctx.restore()
        return

    # 1. Wooden picket posts (angled stakes driven into ground)
    p0 = pts[0]
    p1 = pts[-1]
    for i in range(post_count):
        t = i / max(1, post_count - 1)
        px = p0[0] + t * (p1[0] - p0[0])
        py = p0[1] + t * (p1[1] - p0[1])

        # Angled rough timber stake
        ctx.save()
        angle = (math.sin(i * 1.7) * 0.18)
        ctx.translate(px, py)
        ctx.rotate(angle)
        ctx.rectangle(-7.0, -85.0, 14.0, 95.0)
        ctx.set_source_rgb(0.32, 0.26, 0.20)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.0)
        ctx.stroke()
        # Chiseled pointed top
        ctx.move_to(-7.0, -85.0)
        ctx.line_to(0, -96.0)
        ctx.line_to(7.0, -85.0)
        ctx.close_path()
        ctx.set_source_rgb(0.38, 0.30, 0.22)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.stroke()
        ctx.restore()

    # 2. Main galvanized steel wire strands
    for strand_y in [-70.0, -45.0, -20.0]:
        ctx.move_to(p0[0], p0[1] + strand_y)
        for i in range(1, len(pts)):
            pt = pts[i]
            prev = pts[i - 1]
            cx = (prev[0] + pt[0]) / 2.0
            cy = (prev[1] + pt[1]) / 2.0 + strand_y + 12.0  # Wire catenary sag
            p0_x, p0_y = prev[0], prev[1] + strand_y
            p2_x, p2_y = pt[0], pt[1] + strand_y
            cp1_x = p0_x + 2.0 / 3.0 * (cx - p0_x)
            cp1_y = p0_y + 2.0 / 3.0 * (cy - p0_y)
            cp2_x = p2_x + 2.0 / 3.0 * (cx - p2_x)
            cp2_y = p2_y + 2.0 / 3.0 * (cy - p2_y)
            ctx.curve_to(cp1_x, cp1_y, cp2_x, cp2_y, p2_x, p2_y)
        ctx.set_source_rgb(0.20, 0.22, 0.25)
        ctx.set_line_width(2.0)
        ctx.stroke()

    # 3. Concertina circular wire coils between posts
    coil_count = 18
    for c in range(coil_count):
        t = c / coil_count
        cx = p0[0] + t * (p1[0] - p0[0])
        cy = p0[1] + t * (p1[1] - p0[1]) - 45.0
        r = 30.0

        ctx.save()
        ctx.translate(cx, cy)
        ctx.scale(0.55, 1.0)
        ctx.arc(0, 0, r, 0, math.tau)
        ctx.set_source_rgba(0.25, 0.26, 0.28, 0.85)
        ctx.set_line_width(1.8)
        ctx.stroke()

        # Sharp barbed spikes on coil
        for b_deg in [0, 90, 180, 270]:
            brad = math.radians(b_deg)
            bx = r * math.cos(brad)
            by = r * math.sin(brad)
            ctx.move_to(bx - 4, by - 4)
            ctx.line_to(bx + 4, by + 4)
            ctx.move_to(bx + 4, by - 4)
            ctx.line_to(bx - 4, by + 4)
            ctx.set_source_rgb(0.1, 0.1, 0.12)
            ctx.set_line_width(1.5)
            ctx.stroke()
        ctx.restore()

    ctx.restore()


def draw_artillery_crater(
    ctx: cairo.Context,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    mud_lip: float = 16.0,
    water_filled: bool = True,
    lighting_dx: float = 1.0,
) -> None:
    """Draw a massive high-explosive artillery shell blast crater with raised earthen rim and water."""
    ctx.save()
    ink = (0.06, 0.06, 0.08)

    # 1. Raised earthen blast lip (outer ejecta ring)
    ctx.save()
    ctx.translate(cx, cy)
    ctx.scale(1.0, ry / rx)
    ctx.arc(0, 0, rx + mud_lip, 0, math.tau)

    lip_grad = cairo.RadialGradient(0, 0, rx, 0, 0, rx + mud_lip)
    lip_grad.add_color_stop_rgb(0.0, 0.35, 0.28, 0.20)
    lip_grad.add_color_stop_rgb(1.0, 0.26, 0.20, 0.14)
    ctx.set_source(lip_grad)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.5)
    ctx.stroke()
    ctx.restore()

    # 2. Deep shadow bowl of the crater
    ctx.save()
    ctx.translate(cx, cy)
    ctx.scale(1.0, ry / rx)
    ctx.arc(0, 0, rx, 0, math.tau)

    bowl_grad = cairo.RadialGradient(
        -rx * 0.3 if lighting_dx >= 0 else rx * 0.3,
        -ry * 0.3,
        rx * 0.1,
        0, 0, rx
    )
    bowl_grad.add_color_stop_rgb(0.0, 0.18, 0.15, 0.12)
    bowl_grad.add_color_stop_rgb(0.85, 0.08, 0.06, 0.04)
    bowl_grad.add_color_stop_rgb(1.0, 0.04, 0.03, 0.02)
    ctx.set_source(bowl_grad)
    ctx.fill()
    ctx.restore()

    # 3. Water pool standing at bottom of crater
    if water_filled:
        draw_puddle_reflection(ctx, cx, cy + ry * 0.2, rx * 0.65, ry * 0.55, sky_color=(0.58, 0.62, 0.68))

    ctx.restore()


def draw_ammo_crate_stack(
    ctx: cairo.Context,
    x: float,
    y: float,
    scale: float = 1.0,
    crate_count: int = 3,
    lighting_dx: float = 1.0,
) -> None:
    """Draw a stack of olive-drab / field-gray stenciled German/Allied wooden ammo crates."""
    ctx.save()
    ink = (0.08, 0.09, 0.10)
    crate_w = 110.0 * scale
    crate_h = 55.0 * scale

    for c in range(crate_count):
        cy = y - (c + 1) * crate_h
        cx = x + (c % 2) * 12.0 * scale

        # Wooden box body
        ctx.rectangle(cx, cy, crate_w, crate_h)
        ctx.set_source_rgb(0.34, 0.38, 0.32)  # Feldgrau military green
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.5 * scale)
        ctx.stroke()

        # Steel corner reinforcing brackets
        for bx in [cx, cx + crate_w - 14 * scale]:
            for by in [cy, cy + crate_h - 14 * scale]:
                ctx.rectangle(bx, by, 14 * scale, 14 * scale)
                ctx.set_source_rgb(0.18, 0.18, 0.20)
                ctx.fill_preserve()
                ctx.set_source_rgb(*ink)
                ctx.set_line_width(1.0 * scale)
                ctx.stroke()

        # Military stencil markings
        ctx.save()
        ctx.select_font_face("Impact", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(10.0 * scale)
        ctx.set_source_rgb(0.92, 0.90, 0.82)
        ctx.move_to(cx + 22 * scale, cy + crate_h * 0.58)
        ctx.show_text("7.92mm MG08" if c == 0 else "HE-1916")
        ctx.restore()

        # Heavy rope carry handle
        ctx.move_to(cx - 8 * scale, cy + crate_h * 0.4)
        ctx.curve_to(
            cx - 16 * scale, cy + crate_h * 0.5,
            cx - 16 * scale, cy + crate_h * 0.7,
            cx - 8 * scale, cy + crate_h * 0.8
        )
        ctx.set_source_rgb(0.48, 0.42, 0.32)
        ctx.set_line_width(3.0 * scale)
        ctx.stroke()

    ctx.restore()


# ==============================================================================
# 4. INTERIOR PRIMITIVES
# ==============================================================================

def draw_hospital_bed(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float = 240.0,
    height: float = 130.0,
    scale: float = 1.0,
    lighting_dx: float = 1.0,
    iron_color: tuple[float, float, float] = (0.16, 0.18, 0.22),
) -> None:
    """Draw an authentic WWI military hospital bedstead (white enamel iron tubes, mattress, linen)."""
    ctx.save()
    ink = (0.08, 0.10, 0.12)
    s = scale
    w = width * s
    h = height * s

    headboard_w = 28.0 * s
    headboard_h = h
    footboard_h = h * 0.68
    mattress_y = y + h * 0.52
    mattress_h = 32.0 * s

    # 1. Cast-iron Headboard (left end)
    head_x = x
    ctx.set_source_rgb(*iron_color)
    ctx.set_line_width(4.5 * s)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)

    # Outer arch
    ctx.move_to(head_x, y + h)
    ctx.line_to(head_x, y + headboard_w)
    ctx.arc(head_x + headboard_w / 2.0, y + headboard_w, headboard_w / 2.0, math.pi, 0)
    ctx.line_to(head_x + headboard_w, y + h)
    ctx.stroke()

    # Brass decorative finials / knobs
    for kx in [head_x, head_x + headboard_w]:
        ctx.arc(kx, y + headboard_w * 0.4, 5.5 * s, 0, math.tau)
        ctx.set_source_rgb(0.85, 0.72, 0.32)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.5 * s)
        ctx.stroke()

    # 2. Footboard (right end)
    foot_x = x + w - headboard_w
    ctx.set_source_rgb(*iron_color)
    ctx.set_line_width(4.0 * s)
    ctx.move_to(foot_x, y + h)
    ctx.line_to(foot_x, y + h - footboard_h)
    ctx.line_to(foot_x + headboard_w, y + h - footboard_h)
    ctx.line_to(foot_x + headboard_w, y + h)
    ctx.stroke()

    # 3. Mattress and Hospital Linen
    mat_x = head_x + headboard_w * 0.8
    mat_w = w - headboard_w * 1.6
    rounded_rect(ctx, mat_x, mattress_y, mat_w, mattress_h, 6.0 * s)
    # Crisp white-gray hospital linen with fold shading
    lin_grad = cairo.LinearGradient(mat_x, mattress_y, mat_x + mat_w, mattress_y + mattress_h)
    lin_grad.add_color_stop_rgb(0.0, 0.96, 0.97, 0.98)
    lin_grad.add_color_stop_rgb(0.65, 0.88, 0.90, 0.93)
    lin_grad.add_color_stop_rgb(1.0, 0.78, 0.80, 0.84)
    ctx.set_source(lin_grad)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.0 * s)
    ctx.stroke()

    # Pillow at head of bed
    pil_w = 48.0 * s
    pil_h = 24.0 * s
    rounded_rect(ctx, mat_x + 4 * s, mattress_y - pil_h * 0.6, pil_w, pil_h, 8.0 * s)
    ctx.set_source_rgb(0.98, 0.98, 0.99)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(1.8 * s)
    ctx.stroke()

    # Blanket fold turned down at chest level
    ctx.move_to(mat_x + mat_w * 0.32, mattress_y + 4 * s)
    ctx.line_to(mat_x + mat_w * 0.32, mattress_y + mattress_h - 2 * s)
    ctx.set_source_rgba(0.2, 0.25, 0.3, 0.35)
    ctx.set_line_width(2.0 * s)
    ctx.stroke()

    # Metal clinical chart clipboard hanging at foot of bed
    ctx.rectangle(foot_x + headboard_w * 0.2, y + h - footboard_h + 12 * s, 16.0 * s, 24.0 * s)
    ctx.set_source_rgb(0.92, 0.90, 0.82)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(1.2 * s)
    ctx.stroke()

    ctx.restore()


def draw_tavern_table_and_steins(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float = 320.0,
    height: float = 140.0,
    steins_count: int = 3,
    lighting_dx: float = 1.0,
    wood_color: tuple[float, float, float] = (0.35, 0.22, 0.12),
) -> None:
    """Draw a heavy Bavarian tavern table with trestle legs, bench, and earthenware beer steins."""
    ctx.save()
    ink = (0.08, 0.08, 0.10)

    # 1. Table Top (heavy solid oak plank)
    top_h = 24.0
    top_y = y + 42.0

    # Table top perspective trapezoid
    ctx.move_to(x + 25, top_y)
    ctx.line_to(x + width - 25, top_y)
    ctx.line_to(x + width, top_y + top_h)
    ctx.line_to(x, top_y + top_h)
    ctx.close_path()

    t_grad = cairo.LinearGradient(x, top_y, x + width, top_y + top_h)
    t_grad.add_color_stop_rgb(0.0, wood_color[0] * 1.15, wood_color[1] * 1.15, wood_color[2] * 1.15)
    t_grad.add_color_stop_rgb(1.0, wood_color[0] * 0.85, wood_color[1] * 0.85, wood_color[2] * 0.85)
    ctx.set_source(t_grad)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(3.0)
    ctx.stroke()

    # 2. Heavy Trestle X-legs
    leg_w = 26.0
    for lx in [x + 55, x + width - 55 - leg_w]:
        ctx.move_to(lx, top_y + top_h)
        ctx.line_to(lx + leg_w, y + height)
        ctx.line_to(lx, y + height)
        ctx.line_to(lx + leg_w, top_y + top_h)
        ctx.close_path()
        ctx.set_source_rgb(wood_color[0] * 0.72, wood_color[1] * 0.72, wood_color[2] * 0.70)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.5)
        ctx.stroke()

    # 3. Traditional Bavarian Stoneware Beer Steins (Keferloher with pewter lids)
    stein_spacing = width / (steins_count + 1)
    for s in range(1, steins_count + 1):
        sx = x + s * stein_spacing - 14.0
        sy = top_y - 32.0
        sw = 28.0
        sh = 34.0

        # Stoneware ceramic body
        ctx.rectangle(sx, sy, sw, sh)
        ctx.set_source_rgb(0.82, 0.80, 0.74)  # Salt-glazed stoneware gray
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(2.0)
        ctx.stroke()

        # Blue salt-glaze cobalt decoration band
        ctx.rectangle(sx, sy + 8, sw, 8)
        ctx.set_source_rgb(0.18, 0.28, 0.52)
        ctx.fill()

        # Pewter hinged lid
        ctx.arc(sx + sw / 2.0, sy, sw * 0.52, math.pi, 0)
        ctx.set_source_rgb(0.55, 0.56, 0.58)
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.5)
        ctx.stroke()

        # Thumb-lift lever & ear handle
        ctx.move_to(sx + sw, sy + 6)
        ctx.curve_to(sx + sw + 14, sy + 12, sx + sw + 14, sy + sh - 8, sx + sw, sy + sh - 4)
        ctx.set_source_rgb(0.55, 0.56, 0.58)
        ctx.set_line_width(3.0)
        ctx.stroke()

        # Frothy beer head overflowing
        ctx.arc(sx + 6, sy + 2, 5.0, 0, math.tau)
        ctx.arc(sx + sw - 6, sy + 4, 6.0, 0, math.tau)
        ctx.set_source_rgb(0.98, 0.97, 0.90)
        ctx.fill()

    ctx.restore()


def draw_hanging_brass_lantern(
    ctx: cairo.Context,
    x: float,
    y: float,
    scale: float = 1.0,
    is_lit: bool = True,
    glow_radius: float = 140.0,
    lighting_dx: float = 1.0,
) -> None:
    """Draw a period brass/iron hanging lantern with warm volumetric candle/gas glow."""
    ctx.save()
    ink = (0.08, 0.08, 0.10)
    s = scale

    # Chain / bracket hanging from ceiling
    ctx.move_to(x, y - 60.0 * s)
    ctx.line_to(x, y)
    ctx.set_source_rgb(0.18, 0.18, 0.20)
    ctx.set_line_width(3.0 * s)
    ctx.stroke()

    # Lantern cap / roof
    cap_w = 44.0 * s
    cap_h = 16.0 * s
    ctx.move_to(x - cap_w / 2.0, y)
    ctx.line_to(x, y - cap_h)
    ctx.line_to(x + cap_w / 2.0, y)
    ctx.close_path()
    ctx.set_source_rgb(0.72, 0.58, 0.26)  # Polished antique brass
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.0 * s)
    ctx.stroke()

    # Glass cage body
    body_w = 36.0 * s
    body_h = 52.0 * s
    ctx.rectangle(x - body_w / 2.0, y, body_w, body_h)
    if is_lit:
        ctx.set_source_rgb(1.0, 0.92, 0.65)  # Warm luminous glass
    else:
        ctx.set_source_rgb(0.85, 0.88, 0.90)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.5 * s)
    ctx.stroke()

    # Brass corner struts
    for cx in [-body_w / 2.0, body_w / 2.0]:
        ctx.move_to(x + cx, y)
        ctx.line_to(x + cx, y + body_h)
        ctx.stroke()

    # Lantern base & finial
    ctx.rectangle(x - cap_w * 0.45, y + body_h, cap_w * 0.9, 10.0 * s)
    ctx.set_source_rgb(0.72, 0.58, 0.26)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.stroke()

    # Volumetric warm glow halo
    if is_lit:
        glow = cairo.RadialGradient(x, y + body_h / 2.0, 5.0 * s, x, y + body_h / 2.0, glow_radius * s)
        glow.add_color_stop_rgba(0.0, 1.0, 0.88, 0.45, 0.65)
        glow.add_color_stop_rgba(0.4, 1.0, 0.75, 0.30, 0.25)
        glow.add_color_stop_rgba(1.0, 0.9, 0.6, 0.1, 0.0)
        ctx.arc(x, y + body_h / 2.0, glow_radius * s, 0, math.tau)
        ctx.set_source(glow)
        ctx.fill()

    ctx.restore()


def draw_wainscoting_wall(
    ctx: cairo.Context,
    x: float,
    y: float,
    width: float,
    height: float,
    dado_fraction: float = 0.40,
    wood_color: tuple[float, float, float] = (0.34, 0.24, 0.16),
    plaster_color: tuple[float, float, float] = (0.84, 0.82, 0.78),
    lighting_dx: float = 1.0,
) -> None:
    """Draw a classic period wall with distressed plaster top and wood wainscot paneling bottom."""
    ctx.save()
    ink = (0.10, 0.10, 0.12)
    dado_y = y + height * (1.0 - dado_fraction)
    dado_h = height * dado_fraction

    # 1. Distressed Plaster Upper Wall
    p_grad = cairo.LinearGradient(x, y, x + width, dado_y)
    p_grad.add_color_stop_rgb(0.0, plaster_color[0] * 1.05, plaster_color[1] * 1.05, plaster_color[2] * 1.02)
    p_grad.add_color_stop_rgb(1.0, plaster_color[0] * 0.88, plaster_color[1] * 0.88, plaster_color[2] * 0.90)
    ctx.rectangle(x, y, width, dado_y - y)
    ctx.set_source(p_grad)
    ctx.fill()

    # Subtle wall distress / cracks
    apply_surface_hatch(ctx, x, y, width, dado_y - y, spacing=24.0, color_rgba=(0.0, 0.0, 0.0, 0.04))

    # 2. Wainscoting Dado Lower Wall
    w_grad = cairo.LinearGradient(x, dado_y, x + width, y + height)
    w_grad.add_color_stop_rgb(0.0, wood_color[0] * 1.08, wood_color[1] * 1.08, wood_color[2] * 1.05)
    w_grad.add_color_stop_rgb(1.0, wood_color[0] * 0.82, wood_color[1] * 0.80, wood_color[2] * 0.78)
    ctx.rectangle(x, dado_y, width, dado_h)
    ctx.set_source(w_grad)
    ctx.fill()

    # Dado Chair Rail (molded projecting top rail)
    rail_h = 16.0
    ctx.rectangle(x, dado_y - rail_h / 2.0, width, rail_h)
    ctx.set_source_rgb(wood_color[0] * 1.20, wood_color[1] * 1.20, wood_color[2] * 1.20)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.0)
    ctx.stroke()

    # Baseboard at floor
    base_h = 22.0
    ctx.rectangle(x, y + height - base_h, width, base_h)
    ctx.set_source_rgb(wood_color[0] * 0.70, wood_color[1] * 0.70, wood_color[2] * 0.70)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(2.0)
    ctx.stroke()

    # Wainscot vertical panels
    panel_count = max(4, int(width / 160.0))
    panel_w = width / panel_count
    for p in range(panel_count):
        px = x + p * panel_w + 12.0
        py = dado_y + rail_h / 2.0 + 12.0
        pw = panel_w - 24.0
        ph = dado_h - rail_h / 2.0 - base_h - 24.0

        ctx.rectangle(px, py, pw, ph)
        ctx.set_source_rgba(0.0, 0.0, 0.0, 0.18)  # Recessed shadow
        ctx.fill_preserve()
        ctx.set_source_rgb(*ink)
        ctx.set_line_width(1.5)
        ctx.stroke()

    ctx.restore()


# ==============================================================================
# 5. ATMOSPHERIC & FX PRIMITIVES
# ==============================================================================

def draw_light_shaft(
    ctx: cairo.Context,
    top_x1: float,
    top_x2: float,
    bot_x1: float,
    bot_x2: float,
    y_top: float,
    y_bot: float,
    color_rgba: tuple[float, float, float, float] = (1.0, 0.98, 0.82, 0.22),
) -> None:
    """Draw a cinematic volumetric light beam or dust shaft across the scene."""
    ctx.save()
    ctx.move_to(top_x1, y_top)
    ctx.line_to(top_x2, y_top)
    ctx.line_to(bot_x2, y_bot)
    ctx.line_to(bot_x1, y_bot)
    ctx.close_path()

    grad = cairo.LinearGradient(
        (top_x1 + top_x2) / 2.0, y_top,
        (bot_x1 + bot_x2) / 2.0, y_bot
    )
    grad.add_color_stop_rgba(0.0, color_rgba[0], color_rgba[1], color_rgba[2], color_rgba[3])
    grad.add_color_stop_rgba(0.5, color_rgba[0], color_rgba[1], color_rgba[2], color_rgba[3] * 0.6)
    grad.add_color_stop_rgba(1.0, color_rgba[0], color_rgba[1], color_rgba[2], 0.0)

    ctx.set_source(grad)
    ctx.fill()
    ctx.restore()


def draw_smoke_plumes(
    ctx: cairo.Context,
    x: float,
    y: float,
    height: float = 240.0,
    plume_count: int = 7,
    drift_dx: float = 35.0,
    color_rgba: tuple[float, float, float, float] = (0.32, 0.34, 0.38, 0.35),
) -> None:
    """Draw heavy battlefield artillery smoke plumes rising and drifting with the wind."""
    ctx.save()
    for i in range(plume_count):
        t = i / plume_count
        py = y - t * height
        px = x + t * drift_dx + math.sin(i * 1.8) * 18.0
        r = 18.0 + t * 45.0

        ctx.arc(px, py, r, 0, math.tau)
        alpha = color_rgba[3] * (1.0 - t * 0.75)
        ctx.set_source_rgba(color_rgba[0], color_rgba[1], color_rgba[2], alpha)
        ctx.fill()
    ctx.restore()


def draw_ground_fog(
    ctx: cairo.Context,
    y_start: float,
    height: float,
    width: float,
    color_rgba: tuple[float, float, float, float] = (0.75, 0.78, 0.82, 0.35),
) -> None:
    """Draw a low-lying ground mist or toxic gas cloud rolling across the floor."""
    ctx.save()
    grad = cairo.LinearGradient(0, y_start, 0, y_start + height)
    grad.add_color_stop_rgba(0.0, color_rgba[0], color_rgba[1], color_rgba[2], 0.0)
    grad.add_color_stop_rgba(0.3, color_rgba[0], color_rgba[1], color_rgba[2], color_rgba[3] * 0.5)
    grad.add_color_stop_rgba(0.7, color_rgba[0], color_rgba[1], color_rgba[2], color_rgba[3])
    grad.add_color_stop_rgba(1.0, color_rgba[0], color_rgba[1], color_rgba[2], color_rgba[3] * 0.8)

    ctx.rectangle(0, y_start, width, height)
    ctx.set_source(grad)
    ctx.fill()
    ctx.restore()


def draw_rain_and_drizzle(
    ctx: cairo.Context,
    width: float,
    height: float,
    density: int = 160,
    wind_dx: float = -14.0,
    splash_y: float = 850.0,
) -> None:
    """Draw angled rain streaks and contact splash ripples on the ground."""
    ctx.save()
    ctx.set_source_rgba(0.85, 0.90, 0.98, 0.28)
    ctx.set_line_width(1.2)

    # Deterministic pseudo-random rain streaks
    for i in range(density):
        rx = ((i * 47) % int(width + 200)) - 100
        ry = (i * 31) % int(height)
        streak_len = 22.0 + (i % 15)

        ctx.move_to(rx, ry)
        ctx.line_to(rx + wind_dx, ry + streak_len)
        ctx.stroke()

        # Contact splash at ground level
        if ry + streak_len > splash_y and (i % 4 == 0):
            ctx.arc(rx + wind_dx, ry + streak_len, 3.5, 0, math.tau)
            ctx.stroke()

    ctx.restore()


def draw_vignette(
    ctx: cairo.Context,
    width: float,
    height: float,
    intensity: float = 0.40,
) -> None:
    """Draw a subtle cinematic edge-darkening vignette."""
    ctx.save()
    cx = width / 2.0
    cy = height / 2.0
    max_r = math.hypot(cx, cy)

    grad = cairo.RadialGradient(cx, cy, max_r * 0.45, cx, cy, max_r)
    grad.add_color_stop_rgba(0.0, 0.0, 0.0, 0.0, 0.0)
    grad.add_color_stop_rgba(0.7, 0.0, 0.0, 0.0, intensity * 0.45)
    grad.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, intensity)

    ctx.rectangle(0, 0, width, height)
    ctx.set_source(grad)
    ctx.fill()
    ctx.restore()
