"""Controlled Irregularity Engine (Selective Editorial Hand-Drawn Line Treatment).

Inspired by Rough.js principles:
- Replaces rigid, mechanical, ruler-straight vector lines with subtle, organic, human hand-drawn contours.
- Provides controlled line bowing, corner overshoots, and architectural shading hatches.
- Strictly selective: avoids turned-into-Excalidraw scribble mess. Preserves crisp architectural silhouettes while injecting warmth and authenticity.
"""
from __future__ import annotations

import math
import random
from typing import Sequence
import cairo


class ControlledIrregularityEngine:
    """Provides deterministic, subtle hand-drawn path styling for PyCairo."""

    @staticmethod
    def draw_hand_line(
        ctx: cairo.Context,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        roughness: float = 0.8,
        bowing: float = 0.6,
        seed: int = 42,
    ) -> None:
        """Draw a line with subtle hand-drawn human wobble and slight catenary/pen bowing."""
        rng = random.Random(seed)
        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        if dist < 4.0:
            ctx.move_to(x1, y1)
            ctx.line_to(x2, y2)
            ctx.stroke()
            return

        segments = max(2, int(dist / 45.0))
        pts = [(x1, y1)]

        nx = -dy / dist
        ny = dx / dist

        # Middle bowing
        bow = (rng.uniform(-1.0, 1.0) * bowing) * min(4.0, dist * 0.015)

        for i in range(1, segments):
            t = i / segments
            # Parabolic bow curve
            parabola = 4.0 * t * (1.0 - t)
            jitter = rng.uniform(-1.0, 1.0) * roughness * 1.2
            offset = bow * parabola + jitter
            px = x1 + t * dx + nx * offset
            py = y1 + t * dy + ny * offset
            pts.append((px, py))

        pts.append((x2, y2))

        # Render as smooth cubic spline or multi-segment stroke
        ctx.move_to(*pts[0])
        for i in range(1, len(pts)):
            ctx.line_to(*pts[i])
        ctx.stroke()

    @staticmethod
    def draw_irregular_rect(
        ctx: cairo.Context,
        x: float,
        y: float,
        w: float,
        h: float,
        roughness: float = 0.7,
        seed: int = 55,
        fill_color: tuple[float, float, float] | None = None,
        stroke_color: tuple[float, float, float] = (0.1, 0.1, 0.12),
        stroke_width: float = 2.0,
    ) -> None:
        """Draw a rectangle with subtly irregular hand-drawn edges and softened corners."""
        rng = random.Random(seed)
        corners = [
            (x + rng.uniform(-0.8, 0.8), y + rng.uniform(-0.8, 0.8)),
            (x + w + rng.uniform(-0.8, 0.8), y + rng.uniform(-0.8, 0.8)),
            (x + w + rng.uniform(-0.8, 0.8), y + h + rng.uniform(-0.8, 0.8)),
            (x + rng.uniform(-0.8, 0.8), y + h + rng.uniform(-0.8, 0.8)),
        ]

        # Fill if requested
        if fill_color:
            ctx.save()
            ctx.move_to(*corners[0])
            for pt in corners[1:]:
                ctx.line_to(*pt)
            ctx.close_path()
            ctx.set_source_rgb(*fill_color)
            ctx.fill()
            ctx.restore()

        # Stroke perimeter with hand lines
        ctx.save()
        ctx.set_source_rgb(*stroke_color)
        ctx.set_line_width(stroke_width)
        for i in range(4):
            c1 = corners[i]
            c2 = corners[(i + 1) % 4]
            ControlledIrregularityEngine.draw_hand_line(
                ctx, c1[0], c1[1], c2[0], c2[1],
                roughness=roughness, seed=seed + i * 17
            )
        ctx.restore()

    @staticmethod
    def draw_architectural_hatch(
        ctx: cairo.Context,
        pts: Sequence[tuple[float, float]],
        angle_rad: float = math.pi / 4.0,
        spacing: float = 14.0,
        roughness: float = 0.6,
        color_rgba: tuple[float, float, float, float] = (0.1, 0.1, 0.12, 0.15),
        seed: int = 88,
    ) -> None:
        """Draw controlled architectural shading hatch lines inside an arbitrary polygon."""
        if len(pts) < 3:
            return

        ctx.save()
        ctx.move_to(*pts[0])
        for pt in pts[1:]:
            ctx.line_to(*pt)
        ctx.close_path()
        ctx.clip()

        min_x = min(p[0] for p in pts)
        max_x = max(p[0] for p in pts)
        min_y = min(p[1] for p in pts)
        max_y = max(p[1] for p in pts)

        w = max_x - min_x
        h = max_y - min_y
        diag = math.hypot(w, h)
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0

        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        num = int(diag / max(4.0, spacing))
        rng = random.Random(seed)

        ctx.set_source_rgba(*color_rgba)
        ctx.set_line_width(1.2)

        for i in range(-num, num):
            offset = i * spacing + rng.uniform(-1.0, 1.0)
            x1 = cx + offset * cos_a - diag * sin_a
            y1 = cy + offset * sin_a + diag * cos_a
            x2 = cx + offset * cos_a + diag * sin_a
            y2 = cy + offset * sin_a - diag * cos_a
            ControlledIrregularityEngine.draw_hand_line(
                ctx, x1, y1, x2, y2, roughness=roughness, seed=seed + i * 31
            )

        ctx.restore()
