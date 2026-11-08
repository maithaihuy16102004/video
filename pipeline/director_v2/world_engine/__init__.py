"""Track B — Cinematic Scene / Environment / Visual World Engine.

General, non-story-specific environment engine responsible for:
- Location Visual DNA
- Cinematic Composition & Asymmetry
- Perspective Layout & Multi-Plane Depth (NEAR_FG, FG, MG, BG, FAR_BG)
- Illustrated SVG Asset Architecture & Reusable Library
- Material System (WOOD, METAL, STONE, PLASTER, FABRIC, GLASS, PAPER, MUD, BRICK, EARTH, LEATHER)
- Deterministic, material-aware textures
- Controlled irregularity & architectural line treatment
- Environmental Storytelling (states: USED, DAMAGED, WET, SCATTERED, OPEN)
- Dynamic 5-point Lighting (Key, Fill, Rim, Shadow Zones, Atmospheric)
"""
from __future__ import annotations

from .location_dna import LocationVisualDNA, get_location_dna
from .materials import MaterialSystem, MaterialType, MaterialProperty
from .rough_path import ControlledIrregularityEngine
from .composition import CinematicCompositionEngine
from .lighting import WorldLightingEngine
from .storytelling import EnvironmentalStorytelling
from .svg_assets import IllustratedAssetResolver, EnvironmentAsset
from .scene_world_renderer import GeneralWorldEngine
