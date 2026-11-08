"""Material System for Track B Cinematic Environment Engine.

Provides distinct visual behavior, edge treatments, textures, and highlight responses for:
WOOD, METAL, STONE, PLASTER, FABRIC, GLASS, PAPER, MUD, BRICK, EARTH, LEATHER.

Features:
- Differentiates materials through tactile line density, surface marks, and highlights.
- Deterministic, material-aware textures (no global uniform dirty noise).
- Integrates with Cairo paths and PIL image shaders.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable
import cairo


class MaterialType(str, Enum):
    WOOD = "WOOD"
    METAL = "METAL"
    STONE = "STONE"
    PLASTER = "PLASTER"
    FABRIC = "FABRIC"
    GLASS = "GLASS"
    PAPER = "PAPER"
    MUD = "MUD"
    BRICK = "BRICK"
    EARTH = "EARTH"
    LEATHER = "LEATHER"


@dataclass
class MaterialProperty:
    mat_type: MaterialType
    base_color: tuple[float, float, float]
    stroke_color: tuple[float, float, float]
    stroke_width: float
    edge_style: str  # "SHARP", "CHISELED", "ROUGH_ORGANIC", "SOFT_ROUNDED", "DECKLE"
    specular_intensity: float  # 0.0 (matte) to 1.0 (mirror-like)
    surface_marks: str  # "GRAIN", "RIVETS", "STIPPLE", "CRACKS", "WEAVE", "SHEEN", "SQUELCH"
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mat_type": self.mat_type.value,
            "base_color": list(self.base_color),
            "stroke_color": list(self.stroke_color),
            "stroke_width": self.stroke_width,
            "edge_style": self.edge_style,
            "specular_intensity": self.specular_intensity,
            "surface_marks": self.surface_marks,
            "description": self.description,
        }


MATERIAL_REGISTRY: dict[MaterialType, MaterialProperty] = {
    MaterialType.WOOD: MaterialProperty(
        mat_type=MaterialType.WOOD,
        base_color=(0.38, 0.28, 0.18),
        stroke_color=(0.10, 0.08, 0.06),
        stroke_width=2.5,
        edge_style="ROUGH_ORGANIC",
        specular_intensity=0.20,
        surface_marks="GRAIN",
        description="Warm fibrous grain lines, longitudinal splits, knots, organic soft edge.",
    ),
    MaterialType.METAL: MaterialProperty(
        mat_type=MaterialType.METAL,
        base_color=(0.28, 0.32, 0.36),
        stroke_color=(0.08, 0.09, 0.12),
        stroke_width=2.0,
        edge_style="SHARP",
        specular_intensity=0.85,
        surface_marks="RIVETS",
        description="Crisp industrial contours, specular reflection gleams, rivets, cold hue.",
    ),
    MaterialType.STONE: MaterialProperty(
        mat_type=MaterialType.STONE,
        base_color=(0.76, 0.74, 0.70),
        stroke_color=(0.14, 0.14, 0.16),
        stroke_width=2.8,
        edge_style="CHISELED",
        specular_intensity=0.10,
        surface_marks="STIPPLE",
        description="Chiseled ashlar blocks, mortar relief, subtle mineral stipple texture.",
    ),
    MaterialType.PLASTER: MaterialProperty(
        mat_type=MaterialType.PLASTER,
        base_color=(0.88, 0.87, 0.84),
        stroke_color=(0.20, 0.20, 0.22),
        stroke_width=1.5,
        edge_style="SOFT_ROUNDED",
        specular_intensity=0.05,
        surface_marks="CRACKS",
        description="Fine hairline settling cracks, chalky matte wash, subtle trowel marks.",
    ),
    MaterialType.FABRIC: MaterialProperty(
        mat_type=MaterialType.FABRIC,
        base_color=(0.94, 0.94, 0.92),
        stroke_color=(0.18, 0.18, 0.20),
        stroke_width=1.8,
        edge_style="SOFT_ROUNDED",
        specular_intensity=0.08,
        surface_marks="WEAVE",
        description="Cross-weave tactile texture, draped fold lines, soft matte falloff.",
    ),
    MaterialType.GLASS: MaterialProperty(
        mat_type=MaterialType.GLASS,
        base_color=(0.82, 0.90, 0.96),
        stroke_color=(0.12, 0.15, 0.20),
        stroke_width=2.2,
        edge_style="SHARP",
        specular_intensity=0.95,
        surface_marks="SHEEN",
        description="Translucent gradient, diagonal specular reflections, prismatic edge refraction.",
    ),
    MaterialType.PAPER: MaterialProperty(
        mat_type=MaterialType.PAPER,
        base_color=(0.94, 0.91, 0.82),
        stroke_color=(0.14, 0.14, 0.15),
        stroke_width=1.2,
        edge_style="DECKLE",
        specular_intensity=0.05,
        surface_marks="FIBER",
        description="Aged rag paper, deckle fibrous edge, subtle fold creases, printer ink rules.",
    ),
    MaterialType.MUD: MaterialProperty(
        mat_type=MaterialType.MUD,
        base_color=(0.22, 0.18, 0.13),
        stroke_color=(0.06, 0.05, 0.04),
        stroke_width=3.2,
        edge_style="ROUGH_ORGANIC",
        specular_intensity=0.65,
        surface_marks="SQUELCH",
        description="High-moisture specular sheen pools, heavy wet clods, visceral organic contours.",
    ),
    MaterialType.BRICK: MaterialProperty(
        mat_type=MaterialType.BRICK,
        base_color=(0.58, 0.32, 0.24),
        stroke_color=(0.12, 0.10, 0.08),
        stroke_width=2.2,
        edge_style="CHISELED",
        specular_intensity=0.15,
        surface_marks="MORTAR",
        description="Running bond mortar coursing, kiln tone variation, weathered clay edges.",
    ),
    MaterialType.EARTH: MaterialProperty(
        mat_type=MaterialType.EARTH,
        base_color=(0.34, 0.28, 0.20),
        stroke_color=(0.08, 0.07, 0.06),
        stroke_width=2.8,
        edge_style="ROUGH_ORGANIC",
        specular_intensity=0.12,
        surface_marks="STRATA",
        description="Crumbled subsoil strata, embedded gravel pebble stipple, earthen lip crest.",
    ),
    MaterialType.LEATHER: MaterialProperty(
        mat_type=MaterialType.LEATHER,
        base_color=(0.32, 0.20, 0.14),
        stroke_color=(0.08, 0.06, 0.05),
        stroke_width=1.8,
        edge_style="SOFT_ROUNDED",
        specular_intensity=0.40,
        surface_marks="STITCH",
        description="Burnished oil patina, wax-threaded perimeter stitching dashes, supple creases.",
    ),
}


class MaterialSystem:
    """Applies material-aware shaders, surface marks, and edge styling onto Cairo contexts."""

    @staticmethod
    def get_material(mat: MaterialType | str) -> MaterialProperty:
        if isinstance(mat, str):
            mat = MaterialType(mat.upper())
        return MATERIAL_REGISTRY.get(mat, MATERIAL_REGISTRY[MaterialType.WOOD])

    @staticmethod
    def apply_wood_grain(
        ctx: cairo.Context,
        x: float,
        y: float,
        w: float,
        h: float,
        seed: int = 42,
        density: int = 5,
        tint: tuple[float, float, float] | None = None,
    ) -> None:
        """Render deterministic wood grain lines and knots."""
        ctx.save()
        ctx.rectangle(x, y, w, h)
        ctx.clip()
        rng = random.Random(seed)

        # Grain stroke color
        ctx.set_source_rgba(0.06, 0.04, 0.03, 0.32)
        ctx.set_line_width(1.2)

        for i in range(density):
            gy = y + (i + 0.5) * (h / density)
            ctx.move_to(x, gy)
            step_x = max(20.0, w / 8.0)
            cur_x = x
            while cur_x < x + w:
                cur_x += step_x
                dy = rng.uniform(-4.0, 4.0)
                ctx.line_to(min(x + w, cur_x), gy + dy)
            ctx.stroke()

        # Rare knot
        if rng.random() > 0.4:
            kx = x + rng.uniform(0.2, 0.8) * w
            ky = y + rng.uniform(0.2, 0.8) * h
            ctx.save()
            ctx.translate(kx, ky)
            ctx.scale(1.0, 0.45)
            ctx.arc(0, 0, 8.0, 0, math.tau)
            ctx.set_source_rgba(0.08, 0.05, 0.04, 0.45)
            ctx.fill()
            ctx.arc(0, 0, 14.0, 0, math.tau)
            ctx.set_source_rgba(0.08, 0.05, 0.04, 0.25)
            ctx.set_line_width(1.5)
            ctx.stroke()
            ctx.restore()

        ctx.restore()

    @staticmethod
    def apply_metal_specular(
        ctx: cairo.Context,
        x: float,
        y: float,
        w: float,
        h: float,
        light_dx: float = 1.0,
    ) -> None:
        """Render sharp metallic specular gleam along illuminated edge."""
        ctx.save()
        ctx.rectangle(x, y, w, h)
        ctx.clip()

        # Narrow high-contrast specular band
        grad = cairo.LinearGradient(x, y, x + w, y)
        spec_pos = 0.25 if light_dx >= 0 else 0.75
        grad.add_color_stop_rgba(max(0.0, spec_pos - 0.15), 1.0, 1.0, 1.0, 0.0)
        grad.add_color_stop_rgba(spec_pos, 1.0, 1.0, 1.0, 0.65)
        grad.add_color_stop_rgba(min(1.0, spec_pos + 0.15), 1.0, 1.0, 1.0, 0.0)

        ctx.rectangle(x, y, w, h)
        ctx.set_source(grad)
        ctx.fill()

        # Sharp rim edge highlight
        edge_x = x if light_dx >= 0 else x + w
        ctx.move_to(edge_x, y)
        ctx.line_to(edge_x, y + h)
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.75)
        ctx.set_line_width(1.5)
        ctx.stroke()

        ctx.restore()

    @staticmethod
    def apply_stone_stipple(
        ctx: cairo.Context,
        x: float,
        y: float,
        w: float,
        h: float,
        seed: int = 101,
        count: int = 40,
    ) -> None:
        """Render mineral stipple marks on cut stone."""
        ctx.save()
        ctx.rectangle(x, y, w, h)
        ctx.clip()
        rng = random.Random(seed)

        for _ in range(count):
            px = x + rng.uniform(2.0, w - 2.0)
            py = y + rng.uniform(2.0, h - 2.0)
            r = rng.uniform(0.8, 2.2)
            alpha = rng.uniform(0.12, 0.28)
            is_dark = rng.random() > 0.4
            if is_dark:
                ctx.set_source_rgba(0.1, 0.1, 0.12, alpha)
            else:
                ctx.set_source_rgba(1.0, 1.0, 1.0, alpha)
            ctx.arc(px, py, r, 0, math.tau)
            ctx.fill()

        ctx.restore()

    @staticmethod
    def apply_fabric_weave(
        ctx: cairo.Context,
        x: float,
        y: float,
        w: float,
        h: float,
        step: float = 14.0,
    ) -> None:
        """Render diagonal cross-weave tactile texture for bedding and canvas."""
        ctx.save()
        ctx.rectangle(x, y, w, h)
        ctx.clip()

        ctx.set_source_rgba(0.2, 0.25, 0.35, 0.08)
        ctx.set_line_width(1.0)

        # Angled hatch
        diag = math.hypot(w, h)
        num = int(diag / step)
        for i in range(-num, num):
            offset = i * step
            ctx.move_to(x + offset, y)
            ctx.line_to(x + offset + h, y + h)
            ctx.stroke()

        ctx.restore()

    @staticmethod
    def apply_glass_reflection(
        ctx: cairo.Context,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        """Render crisp diagonal window reflection sheen."""
        ctx.save()
        ctx.rectangle(x, y, w, h)
        ctx.clip()

        # Two diagonal reflection gleams
        ctx.move_to(x, y + h * 0.45)
        ctx.line_to(x + w * 0.45, y)
        ctx.line_to(x + w * 0.65, y)
        ctx.line_to(x, y + h * 0.65)
        ctx.close_path()
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.22)
        ctx.fill()

        ctx.move_to(x + w * 0.2, y + h)
        ctx.line_to(x + w, y + h * 0.2)
        ctx.line_to(x + w, y + h * 0.35)
        ctx.line_to(x + w * 0.35, y + h)
        ctx.close_path()
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.15)
        ctx.fill()

        ctx.restore()

    @staticmethod
    def apply_mud_squelch(
        ctx: cairo.Context,
        x: float,
        y: float,
        w: float,
        h: float,
        seed: int = 777,
    ) -> None:
        """Render wet organic mud surface tension, glossy ripples, and clods."""
        ctx.save()
        ctx.rectangle(x, y, w, h)
        ctx.clip()
        rng = random.Random(seed)

        # Liquid gloss specular puddle patches
        for _ in range(5):
            px = x + rng.uniform(0.1, 0.9) * w
            py = y + rng.uniform(0.1, 0.9) * h
            rx = rng.uniform(15.0, 45.0)
            ry = rx * rng.uniform(0.25, 0.45)

            ctx.save()
            ctx.translate(px, py)
            ctx.scale(1.0, ry / rx)
            ctx.arc(0, 0, rx, 0, math.tau)
            # Wet specular sheen gradient
            s_grad = cairo.RadialGradient(0, -ry * 0.4, 2.0, 0, 0, rx)
            s_grad.add_color_stop_rgba(0.0, 0.95, 0.98, 1.0, 0.45)
            s_grad.add_color_stop_rgba(0.7, 0.50, 0.55, 0.65, 0.20)
            s_grad.add_color_stop_rgba(1.0, 0.15, 0.12, 0.08, 0.0)
            ctx.set_source(s_grad)
            ctx.fill()
            ctx.restore()

        ctx.restore()
