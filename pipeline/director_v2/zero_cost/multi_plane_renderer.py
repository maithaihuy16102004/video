"""Cinematic Environment Renderer (Multi-Plane Layering & True Perspective).

Translates SceneBlueprint into high-fidelity procedural 2D plates:
1. Multi-plane decomposition: FAR_BG, BG, MG, FG, FX.
2. True perspective convergence (horizon_y, vanishing points, depth axis).
3. Lighting and atmosphere handshake.
4. Generates both standalone environment plates and independent parallax layer assets.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import cairo

from .location_kits import get_location_kit, BaseLocationKit
from .lighting_engine import CinematicLightingEngine
from ..scene_builder.blueprint import SceneBlueprint


class CinematicEnvironmentRenderer:
    """Zero-Cost procedural environment renderer powered by parametric primitives."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height

    def render_environment_plate(self, bp: SceneBlueprint) -> cairo.ImageSurface:
        """Render complete multi-plane environment plate without character rig."""
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        ctx = cairo.Context(surf)

        kit: BaseLocationKit = get_location_kit(bp.history.location_id, self.width, self.height)
        lighting = CinematicLightingEngine(bp.lighting, bp.atmosphere)

        # 1. FAR_BG: Sky and distant horizon landmarks
        kit.render_far_bg(ctx, bp, lighting)

        # 2. BG: Main background architecture and back walls
        kit.render_bg(ctx, bp, lighting)

        # 3. MG: Midground floor, platforms, and primary set pieces
        kit.render_mg(ctx, bp, lighting)

        # 4. FG: Controlled foreground occluders (depth through occlusion)
        kit.render_fg_occluders(ctx, bp, lighting)

        # 5. FX: Atmosphere, volumetric beams, smoke, rain, vignette
        kit.render_fx(ctx, bp, lighting)

        return surf

    def render_scene_layers(self, bp: SceneBlueprint) -> dict[str, cairo.ImageSurface]:
        """Render isolated layer surfaces for Motion Canvas parallax export."""
        layers: dict[str, cairo.ImageSurface] = {}
        kit: BaseLocationKit = get_location_kit(bp.history.location_id, self.width, self.height)
        lighting = CinematicLightingEngine(bp.lighting, bp.atmosphere)

        for layer_name in ["FAR_BG", "BG", "MG", "FG", "FX"]:
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
            ctx = cairo.Context(surf)

            if layer_name == "FAR_BG":
                kit.render_far_bg(ctx, bp, lighting)
            elif layer_name == "BG":
                kit.render_bg(ctx, bp, lighting)
            elif layer_name == "MG":
                kit.render_mg(ctx, bp, lighting)
            elif layer_name == "FG":
                kit.render_fg_occluders(ctx, bp, lighting)
            elif layer_name == "FX":
                kit.render_fx(ctx, bp, lighting)

            layers[layer_name] = surf

        return layers

    def save_environment_plate(self, bp: SceneBlueprint, output_path: Path) -> Path:
        """Render and save environment plate to PNG file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        surf = self.render_environment_plate(bp)
        surf.write_to_png(str(output_path))
        return output_path
