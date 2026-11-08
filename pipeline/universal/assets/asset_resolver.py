"""Universal Asset Resolver and Asset Gap Tracker.

Matches semantic object requirements to registered illustrated assets without requiring
engine rewrites. If an exact asset is missing, provides a compatible fallback and logs
an entry into ``asset_gap_report.json``.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ..schemas import AssetRequirement, AssetResolution


@dataclass
class AssetGapEntry:
    requirement_id: str
    semantic: str
    category: str
    period_year: Optional[int]
    region: str
    available_exact: bool
    fallback_used: str
    confidence: str  # HIGH | MEDIUM | LOW
    reason: str


class AssetGapTracker:
    def __init__(self) -> None:
        self.gaps: list[AssetGapEntry] = []

    def log(self, entry: AssetGapEntry) -> None:
        key=(entry.semantic.lower().strip(),entry.period_year,entry.region.upper(),entry.category.upper())
        if any((g.semantic.lower().strip(),g.period_year,g.region.upper(),g.category.upper())==key for g in self.gaps):
            return
        self.gaps.append(entry)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requirements": len(self.gaps),
            "exact_matches": sum(1 for g in self.gaps if g.available_exact),
            "fallback_matches": sum(1 for g in self.gaps if not g.available_exact),
            "gaps": [asdict(g) for g in self.gaps],
        }

    def write_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path


@dataclass
class RegisteredAsset:
    asset_id: str
    name: str
    category: str
    keywords: list[str]
    period_range: tuple[int, int]
    region: str
    materials: list[str]
    affordances: list[str]
    anchors: dict[str, list[float]]
    render_func: Optional[Callable[..., Any]] = None


class UniversalAssetResolver:
    """Matches semantic requirements to registered illustrated assets."""

    def __init__(self) -> None:
        self._registry: dict[str, RegisteredAsset] = {}
        self.gap_tracker = AssetGapTracker()
        self._register_default_catalog()

    def register(self, asset: RegisteredAsset) -> None:
        self._registry[asset.asset_id] = asset

    def _register_default_catalog(self) -> None:
        # Import Track B assets if available
        try:
            from ...director_v2.world_engine.svg_assets import IllustratedAssetResolver as TrackBResolver
            track_b = TrackBResolver()
            for a in track_b._assets.values():
                kw = [w.lower() for w in a.name.split()] + [a.category.lower(), a.material.value.lower()]
                self.register(RegisteredAsset(
                    asset_id=a.asset_id,
                    name=a.name,
                    category=a.category,
                    keywords=kw,
                    period_range=a.era_range,
                    region=a.region,
                    materials=[a.material.value],
                    affordances=a.interaction_affordances,
                    anchors={"lie_anchor": [0.635, 0.713], "lean_anchor": [0.641, 0.718], "grip_anchor": [0.760, 0.667]},
                    render_func=a.render_func,
                ))
        except Exception:
            pass

        from .composable_assets import (
            render_composable_chair,
            render_composable_crate,
            render_composable_document,
            render_composable_machine,
            render_composable_table,
            render_composable_window,
        )

        # Register generic universal baseline assets
        generic_defaults = [
            RegisteredAsset("generic_table_wood_01", "Generic Wooden Table", "TABLE", ["table", "desk", "wood"], (1600, 2026), "GLOBAL", ["WOOD"], ["LEAN", "PLACE"], {"lean_anchor": [0.5, 0.7]}, render_func=render_composable_table),
            RegisteredAsset("generic_bench_wood_01", "Generic Wooden Bench", "BENCH", ["bench", "seat", "chair"], (1600, 2026), "GLOBAL", ["WOOD"], ["SIT"], {"sit_anchor": [0.5, 0.7]}, render_func=render_composable_table),
            RegisteredAsset("generic_chair_wood_01", "Generic Wooden Chair", "CHAIR", ["chair", "seat"], (1600, 2026), "GLOBAL", ["WOOD"], ["SIT"], {"sit_anchor": [0.5, 0.7]}, render_func=render_composable_chair),
            RegisteredAsset("generic_bed_metal_01", "Generic Metal Clinic Bed", "BED", ["bed", "cot"], (1850, 2026), "GLOBAL", ["METAL"], ["LIE", "SIT"], {"lie_anchor": [0.6, 0.7]}),
            RegisteredAsset("generic_crate_wood_01", "Generic Wooden Supply Crate", "CRATE", ["crate", "box", "ammo"], (1800, 2026), "GLOBAL", ["WOOD"], ["CARRY", "PUSH"], {"carry_anchor": [0.5, 0.6]}, render_func=render_composable_crate),
            RegisteredAsset("generic_barrel_wood_01", "Generic Wooden Barrel", "BARREL", ["barrel", "cask"], (1600, 2026), "GLOBAL", ["WOOD"], ["SIT"], {"sit_anchor": [0.5, 0.7]}, render_func=render_composable_crate),
            RegisteredAsset("generic_lamp_lantern_01", "Generic Lantern / Chandelier", "LAMP", ["lamp", "lantern", "chandelier"], (1700, 2026), "GLOBAL", ["METAL", "GLASS"], [], {}),
            RegisteredAsset("generic_window_casement_01", "Generic Casement Window", "WINDOW", ["window", "casement"], (1700, 2026), "GLOBAL", ["GLASS", "WOOD"], [], {}, render_func=render_composable_window),
            RegisteredAsset("generic_post_timber_01", "Generic Timber Post", "POST", ["post", "timber", "pillar", "column"], (1600, 2026), "GLOBAL", ["WOOD"], [], {}),
            RegisteredAsset("generic_sandbags_01", "Generic Sandbag Wall", "SANDBAGS", ["sandbag", "parapet"], (1800, 2026), "GLOBAL", ["FABRIC"], ["PEEK", "COVER"], {}),
            RegisteredAsset("generic_apparatus_01", "Generic Scientific / Electrical Apparatus", "APPARATUS", ["machine", "apparatus", "lab", "coil", "device", "switch", "timer", "telegraph", "insulator"], (1850, 1950), "GLOBAL", ["METAL", "GLASS", "BRASS"], ["OPERATE"], {}, render_func=render_composable_machine),
            RegisteredAsset("generic_document_01", "Generic Sealed / Open Document", "PAPER", ["document", "paper", "folio", "letter", "seal", "decree", "treaty"], (1600, 2026), "GLOBAL", ["PAPER"], ["READ", "SIGN"], {}, render_func=render_composable_document),
        ]
        for gd in generic_defaults:
            if gd.asset_id not in self._registry:
                self.register(gd)

    def resolve(self, req: AssetRequirement) -> AssetResolution:
        sem_low = req.semantic.lower()
        req_cat = req.category.upper()

        best_asset: Optional[RegisteredAsset] = None
        best_score = -1.0
        exact_match = False

        compatible=self._compatible_categories(req_cat)
        for a in self._registry.values():
            if a.category.upper() not in compatible:
                continue
            score = 0.0
            # Category match
            if a.category.upper() == req_cat:
                score += 4.0
            else:
                score += 1.5
            # Keyword matches
            for kw in a.keywords:
                if kw in sem_low:
                    score += 2.5
            # Material matches
            for m in req.materials:
                if m.upper() in [x.upper() for x in a.materials]:
                    score += 1.5
            # Era match
            if req.period_year:
                if a.period_range[0] <= req.period_year <= a.period_range[1]:
                    score += 2.0

            if score > best_score:
                best_score = score
                best_asset = a

        semantic_hits=sum(1 for kw in best_asset.keywords if kw in sem_low) if best_asset else 0
        if best_asset and best_score >= 6.0 and semantic_hits:
            exact_match = True
            status = "MATCH"
            confidence = "HIGH"
            reason = f"High affinity score ({best_score:.1f}) across category, era, and semantic keywords."
        elif best_asset and best_score >= 4.0 and semantic_hits:
            status = "COMPATIBLE_FALLBACK"
            confidence = "MEDIUM"
            reason = f"Compatible semantic fallback found with score {best_score:.1f}."
        else:
            best_asset = None
            status = "ASSET_GAP"
            confidence = "LOW"
            reason = "No semantically and categorically compatible asset; explicit gap returned."

        # Log to gap report
        self.gap_tracker.log(AssetGapEntry(
            requirement_id=req.requirement_id,
            semantic=req.semantic,
            category=req.category,
            period_year=req.period_year,
            region=req.region,
            available_exact=exact_match,
            fallback_used=best_asset.asset_id if best_asset else "MISSING_ASSET",
            confidence=confidence,
            reason=reason,
        ))

        return AssetResolution(
            requirement_id=req.requirement_id,
            semantic=req.semantic,
            status=status,
            asset_id=best_asset.asset_id if best_asset else "MISSING_ASSET",
            score=best_score,
            confidence=confidence,
            reasons=[reason],
        )

    @staticmethod
    def _compatible_categories(category: str) -> set[str]:
        families=[
            {"CHAIR","BENCH","SEAT"},{"TABLE","DESK"},{"BED","COT"},
            {"CRATE","BOX","CONTAINER"},{"LAMP","LANTERN","CHANDELIER"},
            {"WIRE","BARBED_WIRE","CABLE"},{"DEBRIS","RUBBLE"},{"WEAPON","RIFLE","PISTOL"},
            {"VEHICLE","CAR","TRUCK","TRAIN"},{"POST","PILLAR","COLUMN"},
            {"APPARATUS","MACHINE","DEVICE"},{"WINDOW","OPENING"},{"SANDBAGS","BARRIER"},
            {"BARREL","CASK"},
        ]
        for family in families:
            if category in family: return family
        return {category}
