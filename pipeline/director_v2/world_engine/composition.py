"""Cinematic Composition Engine for Track B Visual World.

Core Principles:
1. Controlled Asymmetry: Avoids mechanical centering of architecture, windows, doors, and props.
2. Foreground Framing: Places camera-near objects (NEAR_FG and FG) that bleed out of frame, making the viewer feel physically inside the environment.
3. Partial Cropping: Objects exit the frame naturally instead of looking like an isolated furniture catalog.
4. Meaningful Depth Overlap: Ensures overlapping silhouette layers between NEAR_FG, FG, MG, BG, and FAR_BG.
5. Visual Triangle & Eye Path: Directs eye motion towards the narrative focal zone defined in SceneBlueprint.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..scene_builder.blueprint import SceneBlueprint, CameraSpec, CompositionSpec


class DepthPlane(str, Enum):
    NEAR_FG = "NEAR_FG"   # Ultra close to lens, blurred or silhouette bleed
    FG = "FG"             # Foreground framing structures (doorframe, pillar, table)
    MG = "MG"             # Main action & interaction stage
    BG = "BG"             # Room back walls, revetments, mid-distance structures
    FAR_BG = "FAR_BG"     # Sky, horizon landscape, distant city silhouettes


@dataclass
class CompositionalLayer:
    plane: DepthPlane
    depth_z: float  # 0.0 (camera lens) to 1.0 (infinity horizon)
    contrast_multiplier: float  # 1.2 at focal plane -> 0.45 at far background
    detail_density: float       # High at MG/FG -> Simplified at FAR_BG
    atmospheric_tint: float     # 0.0 (near) to 0.55 (far)
    elements: list[str] = field(default_factory=list)


class CinematicCompositionEngine:
    """Solves asymmetric staging, foreground framing, and depth overlapping hierarchy."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height

    def create_depth_hierarchy(self, bp: SceneBlueprint) -> dict[DepthPlane, CompositionalLayer]:
        """Builds depth planes with perspective-appropriate contrast and detail falloff."""
        return {
            DepthPlane.NEAR_FG: CompositionalLayer(
                plane=DepthPlane.NEAR_FG,
                depth_z=0.08,
                contrast_multiplier=0.85,  # Darkened foreground silhouette
                detail_density=0.60,       # Broader shapes, less noisy detail
                atmospheric_tint=0.0,
            ),
            DepthPlane.FG: CompositionalLayer(
                plane=DepthPlane.FG,
                depth_z=0.25,
                contrast_multiplier=1.15,
                detail_density=0.90,
                atmospheric_tint=0.05,
            ),
            DepthPlane.MG: CompositionalLayer(
                plane=DepthPlane.MG,
                depth_z=0.50,
                contrast_multiplier=1.30,  # HIGHEST CONTRAST: Story & interaction stage
                detail_density=1.00,       # Highest detail
                atmospheric_tint=0.15,
            ),
            DepthPlane.BG: CompositionalLayer(
                plane=DepthPlane.BG,
                depth_z=0.75,
                contrast_multiplier=0.80,
                detail_density=0.70,
                atmospheric_tint=0.35,
            ),
            DepthPlane.FAR_BG: CompositionalLayer(
                plane=DepthPlane.FAR_BG,
                depth_z=0.95,
                contrast_multiplier=0.55,
                detail_density=0.40,       # Atmospheric silhouette
                atmospheric_tint=0.55,
            ),
        }

    def compute_asymmetric_vanishing_point(self, bp: SceneBlueprint) -> tuple[float, float]:
        """Calculates vanishing point with controlled cinematic asymmetry (Rule of Thirds)."""
        w, h = self.width, self.height
        raw_vp = bp.perspective.primary_vp
        vp_x = raw_vp[0] * w
        vp_y = raw_vp[1] * h

        # If perfectly dead-center (0.50, 0.50), apply subtle cinematic offset to avoid boring symmetry
        if abs(raw_vp[0] - 0.50) < 0.02 and "DEEP" not in bp.camera.shot_size.upper():
            # Offset towards the side of dominant negative space
            vp_x = (0.38 if bp.character.approximate_position[0] > 0.5 else 0.62) * w

        return vp_x, vp_y

    def get_foreground_framing_rect(self, bp: SceneBlueprint) -> tuple[float, float, float, float] | None:
        """Determines camera-near foreground framing bounds that bleed off-canvas."""
        w, h = self.width, self.height
        char_x = bp.character.approximate_position[0]
        shot_size = bp.camera.shot_size.upper()

        if "OTS" in shot_size:
            # Framing in left third bleeding off left edge
            return (-40.0, h * 0.35, w * 0.38, h * 0.70)
        elif "LOW_ANGLE" in shot_size:
            # Monumental column plinth bleeding off right edge
            return (w * 0.82, -20.0, w * 0.25, h + 40.0)
        elif "GROUND_LEVEL" in shot_size:
            # Trench revetment timber post bleeding off corner
            return (-30.0, h * 0.40, w * 0.22, h * 0.65)
        elif "DEEP_PERSPECTIVE" in shot_size:
            # Table edge bleeding off bottom right
            return (w * 0.62, h * 0.78, w * 0.45, h * 0.30)
        elif bp.composition.foreground_occlusion > 0.15:
            # Generic asymmetric framing
            side_x = -30.0 if char_x > 0.5 else w * 0.80
            return (side_x, h * 0.20, w * 0.25, h * 0.85)
        return None
