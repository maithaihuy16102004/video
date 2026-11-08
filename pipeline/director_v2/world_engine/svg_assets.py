"""Illustrated SVG Asset Architecture and Resolver.

Manages reusable, high-fidelity illustrated environmental assets:
- Exposes complete metadata: asset type, period range, material, orientation, variants, depth suitability, interaction affordances.
- Bridges parametric rendering with genuine SVG asset catalogs.
- Avoids primitive geometry (boxes, plain circles) in favor of rich silhouettes and material cues.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .materials import MaterialType
from .asset_library.hospital_assets import (
    IllustratedHospitalBed,
    IllustratedPrussianWindow,
    IllustratedMedicineTable,
)
from .asset_library.beer_hall_assets import (
    IllustratedTavernTable,
    IllustratedKeferloherStein,
    IllustratedBeerBarrelStack,
    IllustratedBrassChandelier,
)
from .asset_library.trench_assets import (
    IllustratedTrenchRevetment,
    IllustratedSandbagFortification,
    IllustratedAmmoCrateStack,
    IllustratedBarbedWire,
)


@dataclass
class EnvironmentAsset:
    asset_id: str
    name: str
    category: str  # "FURNITURE", "ARCHITECTURE", "MILITARY", "PROP", "LIGHTING"
    era_range: tuple[int, int]
    region: str
    material: MaterialType
    orientation: str  # "FRONT", "SIDE", "THREE_QUARTER"
    variants: list[str]
    depth_suitability: list[str]  # "NEAR_FG", "FG", "MG", "BG", "FAR_BG"
    interaction_affordances: list[str]  # e.g. ["lie_anchor", "sit_anchor", "lean_anchor"]
    render_func: Callable[..., Any]
    svg_data: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "category": self.category,
            "era_range": list(self.era_range),
            "region": self.region,
            "material": self.material.value,
            "orientation": self.orientation,
            "variants": self.variants,
            "depth_suitability": self.depth_suitability,
            "interaction_affordances": self.interaction_affordances,
        }


class IllustratedAssetResolver:
    """Central registry and resolver for all illustrated environment assets."""

    def __init__(self) -> None:
        self._assets: dict[str, EnvironmentAsset] = {}
        self._register_default_assets()

    def _register_default_assets(self) -> None:
        # 1. Hospital Assets
        self.register(EnvironmentAsset(
            asset_id="hospital_bed_iron_01",
            name="Edwardian Cast-Iron Hospital Bed",
            category="FURNITURE",
            era_range=(1890, 1935),
            region="CENTRAL_EUROPE",
            material=MaterialType.METAL,
            orientation="SIDE",
            variants=["DEFAULT", "EMPTY", "OCCUPIED_BANDAGE", "DAMAGED"],
            depth_suitability=["MG", "FG"],
            interaction_affordances=["lie_anchor", "sit_anchor"],
            render_func=IllustratedHospitalBed.render,
        ))
        self.register(EnvironmentAsset(
            asset_id="prussian_casement_window_01",
            name="Tall Prussian Arched Casement Window",
            category="ARCHITECTURE",
            era_range=(1880, 1940),
            region="PRUSSIA_GERMANY",
            material=MaterialType.GLASS,
            orientation="FRONT",
            variants=["DEFAULT", "CLOSED", "OPEN_CRACK", "DAMAGED"],
            depth_suitability=["BG", "FAR_BG"],
            interaction_affordances=["window_look_anchor"],
            render_func=IllustratedPrussianWindow.render,
        ))
        self.register(EnvironmentAsset(
            asset_id="medicine_table_enamel_01",
            name="Bedside Enamel Medicine Table & Apothecary Bottles",
            category="PROP",
            era_range=(1900, 1930),
            region="UNIVERSAL_EUROPE",
            material=MaterialType.METAL,
            orientation="FRONT",
            variants=["DEFAULT", "ORGANIZED", "USED_OPEN"],
            depth_suitability=["MG", "FG"],
            interaction_affordances=["hand_anchor"],
            render_func=IllustratedMedicineTable.render,
        ))

        # 2. Beer Hall Assets
        self.register(EnvironmentAsset(
            asset_id="tavern_table_oak_01",
            name="Heavy Bavarian Solid Oak Tavern Table",
            category="FURNITURE",
            era_range=(1850, 1945),
            region="BAVARIA",
            material=MaterialType.WOOD,
            orientation="THREE_QUARTER",
            variants=["DEFAULT", "EMPTY", "USED_STEINS", "STAINED"],
            depth_suitability=["MG", "FG", "NEAR_FG"],
            interaction_affordances=["lean_anchor", "sit_anchor"],
            render_func=IllustratedTavernTable.render,
        ))
        self.register(EnvironmentAsset(
            asset_id="beer_steins_keferloher_01",
            name="Salt-Glazed Keferloher Beer Steins with Pewter Lids",
            category="PROP",
            era_range=(1870, 1940),
            region="BAVARIA",
            material=MaterialType.STONE,
            orientation="FRONT",
            variants=["DEFAULT", "CLOSED_FOAM", "OPEN_DRINKING"],
            depth_suitability=["MG", "FG"],
            interaction_affordances=["hold_anchor"],
            render_func=IllustratedKeferloherStein.render,
        ))
        self.register(EnvironmentAsset(
            asset_id="beer_barrel_stack_01",
            name="Stacked Bavarian Oak Beer Barrels with Iron Hoops",
            category="PROP",
            era_range=(1800, 1945),
            region="BAVARIA",
            material=MaterialType.WOOD,
            orientation="FRONT",
            variants=["DEFAULT", "PYRAMID_4", "SINGLE_BARREL"],
            depth_suitability=["BG", "MG"],
            interaction_affordances=["sit_barrel_anchor"],
            render_func=IllustratedBeerBarrelStack.render,
        ))
        self.register(EnvironmentAsset(
            asset_id="brass_chandelier_01",
            name="Wrought Brass Hanging Chandelier with Amber Hurricane Lamps",
            category="LIGHTING",
            era_range=(1880, 1930),
            region="CENTRAL_EUROPE",
            material=MaterialType.METAL,
            orientation="FRONT",
            variants=["DEFAULT", "LIT", "UNLIT"],
            depth_suitability=["BG", "MG", "FG"],
            interaction_affordances=[],
            render_func=IllustratedBrassChandelier.render,
        ))

        # 3. Trench Assets
        self.register(EnvironmentAsset(
            asset_id="trench_timber_revetment_01",
            name="Split Pine Timber Trench Revetment with Spikes",
            category="ARCHITECTURE",
            era_range=(1914, 1918),
            region="WESTERN_FRONT",
            material=MaterialType.WOOD,
            orientation="SIDE",
            variants=["DEFAULT", "INTACT", "BOMBARDED_DAMAGED"],
            depth_suitability=["BG", "MG", "FG"],
            interaction_affordances=["lean_revetment_anchor"],
            render_func=IllustratedTrenchRevetment.render,
        ))
        self.register(EnvironmentAsset(
            asset_id="sandbag_fortification_01",
            name="Stacked Burlap Sandbag Parapet Wall",
            category="MILITARY",
            era_range=(1914, 1945),
            region="UNIVERSAL_MILITARY",
            material=MaterialType.FABRIC,
            orientation="FRONT",
            variants=["DEFAULT", "INTACT", "RUPTURED"],
            depth_suitability=["BG", "MG", "FG", "NEAR_FG"],
            interaction_affordances=["peek_anchor", "cover_anchor"],
            render_func=IllustratedSandbagFortification.render,
        ))
        self.register(EnvironmentAsset(
            asset_id="barbed_wire_concertina_01",
            name="Concertina Razor Wire & Wooden Pickets",
            category="MILITARY",
            era_range=(1914, 1945),
            region="WESTERN_FRONT",
            material=MaterialType.METAL,
            orientation="FRONT",
            variants=["DEFAULT", "MULTI_STRAND"],
            depth_suitability=["FAR_BG", "BG", "MG"],
            interaction_affordances=[],
            render_func=IllustratedBarbedWire.render,
        ))
        self.register(EnvironmentAsset(
            asset_id="ammo_crate_stack_01",
            name="German Military 7.92mm Ammunition Packing Cases",
            category="PROP",
            era_range=(1914, 1918),
            region="GERMANY_MILITARY",
            material=MaterialType.WOOD,
            orientation="FRONT",
            variants=["DEFAULT", "CLOSED_STACK", "OPEN_TILTED"],
            depth_suitability=["MG", "FG"],
            interaction_affordances=["carry_anchor", "sit_crate_anchor"],
            render_func=IllustratedAmmoCrateStack.render,
        ))

    def register(self, asset: EnvironmentAsset) -> None:
        self._assets[asset.asset_id] = asset

    def get(self, asset_id: str) -> EnvironmentAsset | None:
        return self._assets.get(asset_id)

    def list_manifest(self) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self._assets.values()]

    def export_manifest_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.list_manifest(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path
