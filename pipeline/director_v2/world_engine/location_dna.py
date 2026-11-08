"""Location Visual DNA System.

Separates generic environmental architectural rules, materials, and atmospheric behaviors
from specific narrative data.

Fields:
- architectural_language: e.g. "PRUSSIAN_CLASSICAL", "WESTERN_FRONT_ENTRENCHMENT", "BAVARIAN_RUSTIC", "NEOCLASSICAL"
- dominant_materials: list of MaterialType (e.g. WOOD, STONE, MUD)
- secondary_materials: list of MaterialType (e.g. METAL, FABRIC, GLASS)
- palette: primary ambient, shadow, accent colors
- light_behavior: e.g. "VOLUMETRIC_WINDOW_SHAFTS", "OVERCAST_DIFFUSED", "WARM_INTERIOR_POOLS"
- prop_vocabulary: list of authentic prop identifiers
- wear_level: 0.0 (pristine) to 1.0 (war-torn / ruined)
- density: "SPARSE", "BALANCED", "DENSE" (Locked baseline: BALANCED)
- depth_pattern: e.g. "DEEP_CORRIDOR", "TRANSVERSE_ZIGZAG", "STREET_CANYON", "OPEN_PLAZA"
- foreground_vocabulary: framing elements suited for NEAR_FG and FG
- atmospheric_behavior: fog, rain, dust, smoke, light shafts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ArchitecturalStyle(str, Enum):
    PRUSSIAN_NEOCLASSICAL = "PRUSSIAN_NEOCLASSICAL"
    BAVARIAN_RUSTIC = "BAVARIAN_RUSTIC"
    WESTERN_FRONT_ENTRENCHMENT = "WESTERN_FRONT_ENTRENCHMENT"
    EUROPEAN_MUNICIPAL = "EUROPEAN_MUNICIPAL"
    INDUSTRIAL_BRICK = "INDUSTRIAL_BRICK"


@dataclass
class LocationVisualDNA:
    dna_id: str
    architectural_language: str
    dominant_materials: list[str]
    secondary_materials: list[str]
    palette: dict[str, tuple[float, float, float]]
    light_behavior: str
    prop_vocabulary: list[str]
    wear_level: float = 0.35
    density: str = "BALANCED"  # LOCKED baseline: BALANCED
    depth_pattern: str = "DEEP_CORRIDOR"
    foreground_vocabulary: list[str] = field(default_factory=list)
    atmospheric_behavior: dict[str, Any] = field(default_factory=dict)
    interaction_affordances: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dna_id": self.dna_id,
            "architectural_language": self.architectural_language,
            "dominant_materials": self.dominant_materials,
            "secondary_materials": self.secondary_materials,
            "palette": {k: list(v) for k, v in self.palette.items()},
            "light_behavior": self.light_behavior,
            "prop_vocabulary": self.prop_vocabulary,
            "wear_level": self.wear_level,
            "density": self.density,
            "depth_pattern": self.depth_pattern,
            "foreground_vocabulary": self.foreground_vocabulary,
            "atmospheric_behavior": self.atmospheric_behavior,
            "interaction_affordances": self.interaction_affordances,
        }


# ==============================================================================
# BUILT-IN HISTORICAL DNA CATALOG (GENERIC TEMPLATES)
# ==============================================================================

DNA_CATALOG: dict[str, LocationVisualDNA] = {
    # 1. Military Hospital / Convalescence Ward
    "MILITARY_HOSPITAL": LocationVisualDNA(
        dna_id="MILITARY_HOSPITAL",
        architectural_language="PRUSSIAN_NEOCLASSICAL_HOSPITAL",
        dominant_materials=["PLASTER", "WOOD", "GLASS"],
        secondary_materials=["METAL", "FABRIC", "PAPER"],
        palette={
            "ambient_top": (0.88, 0.91, 0.94),
            "ambient_bot": (0.48, 0.44, 0.38),
            "wood_wainscot": (0.34, 0.28, 0.22),
            "metal_enamel": (0.92, 0.94, 0.96),
            "shadow_tint": (0.16, 0.18, 0.24),
            "accent_light": (1.0, 0.96, 0.82),
        },
        light_behavior="VOLUMETRIC_WINDOW_SHAFTS",
        prop_vocabulary=[
            "cast_iron_hospital_bed",
            "prussian_casement_window",
            "bedside_medicine_table",
            "apothecary_carbolic_bottles",
            "medical_chart_clipboard",
            "pendulum_wall_clock",
            "enamel_wash_basin",
            "rolled_gauze_bandages",
        ],
        wear_level=0.30,
        density="BALANCED",
        depth_pattern="DEEP_CORRIDOR",
        foreground_vocabulary=["doctor_shoulder_silhouette", "bedpost_foreground", "doorframe_jamb"],
        atmospheric_behavior={"dust_motes": True, "sunbeam_intensity": 0.28, "fog_density": 0.0},
        interaction_affordances=["LIE_ON_BED", "SIT_ON_BED", "STAND_BESIDE", "INSPECT_CHART"],
    ),

    # 2. Traditional Bavarian Tavern / Beer Hall
    "BEER_HALL": LocationVisualDNA(
        dna_id="BEER_HALL",
        architectural_language="BAVARIAN_RUSTIC_TIMBER",
        dominant_materials=["WOOD", "STONE", "METAL"],
        secondary_materials=["GLASS", "FABRIC", "LEATHER"],
        palette={
            "ambient_top": (0.42, 0.28, 0.16),
            "ambient_bot": (0.28, 0.18, 0.10),
            "wood_beams": (0.22, 0.14, 0.08),
            "brass_glow": (0.98, 0.78, 0.32),
            "shadow_tint": (0.12, 0.08, 0.06),
            "accent_light": (1.0, 0.88, 0.50),
        },
        light_behavior="WARM_INTERIOR_POOLS",
        prop_vocabulary=[
            "heavy_oak_tavern_table",
            "tavern_bench",
            "earthenware_keferloher_steins",
            "stacked_oak_beer_barrels",
            "hanging_brass_chandelier",
            "pewter_pitcher",
            "wall_mounted_gas_sconce",
            "bavarian_diamond_bunting",
        ],
        wear_level=0.45,
        density="BALANCED",
        depth_pattern="DEEP_CORRIDOR",
        foreground_vocabulary=["foreground_table_edge", "crowd_silhouette", "timber_support_pillar"],
        atmospheric_behavior={"tobacco_haze": True, "warm_vignette": 0.48, "fog_density": 0.0},
        interaction_affordances=["SIT_AT_TABLE", "LEAN_ON_TABLE", "HOLD_STEIN", "STAND_ORATE"],
    ),

    # 3. WWI Western Front Trench System
    "WWI_TRENCH": LocationVisualDNA(
        dna_id="WWI_TRENCH",
        architectural_language="WESTERN_FRONT_ENTRENCHMENT",
        dominant_materials=["MUD", "WOOD", "EARTH"],
        secondary_materials=["METAL", "FABRIC"],
        palette={
            "ambient_top": (0.35, 0.38, 0.42),
            "ambient_bot": (0.22, 0.18, 0.14),
            "wet_mud": (0.18, 0.14, 0.10),
            "pine_timber": (0.38, 0.30, 0.22),
            "sandbag_burlap": (0.58, 0.52, 0.40),
            "shadow_tint": (0.08, 0.08, 0.10),
            "accent_light": (0.80, 0.82, 0.85),
        },
        light_behavior="OVERCAST_DIFFUSED",
        prop_vocabulary=[
            "trench_timber_revetment",
            "stacked_burlap_sandbags",
            "mud_duckboard_walkway",
            "concertina_barbed_wire",
            "artillery_blast_crater",
            "ammo_crate_stack",
            "spent_brass_cartridge_casings",
            "shattered_tree_stumps",
            "trench_periscope",
        ],
        wear_level=0.85,
        density="BALANCED",
        depth_pattern="TRANSVERSE_ZIGZAG",
        foreground_vocabulary=["trench_revetment_corner", "sandbag_parapet_edge", "barbed_wire_post"],
        atmospheric_behavior={"rain_drizzle": True, "smoke_plumes": True, "ground_mist": 0.25},
        interaction_affordances=["CROUCH_DUCKBOARD", "LEAN_REVERTMENT", "PEEK_PARAPET", "TAKE_COVER"],
    ),

    # 4. European Neoclassical Street / City Square
    "EUROPEAN_STREET": LocationVisualDNA(
        dna_id="EUROPEAN_STREET",
        architectural_language="NEOCLASSICAL_MUNICIPAL",
        dominant_materials=["STONE", "BRICK", "METAL"],
        secondary_materials=["GLASS", "WOOD", "PAPER"],
        palette={
            "ambient_top": (0.45, 0.65, 0.85),
            "ambient_bot": (0.42, 0.40, 0.38),
            "stone_facade": (0.78, 0.75, 0.70),
            "cobblestone": (0.44, 0.42, 0.40),
            "shadow_tint": (0.14, 0.16, 0.22),
            "accent_light": (1.0, 0.95, 0.80),
        },
        light_behavior="DIRECT_SUN_LONG_SHADOWS",
        prop_vocabulary=[
            "monumental_corinthian_column",
            "arched_colonnade_loggia",
            "neoclassical_townhouse_facade",
            "perspective_cobblestone_plane",
            "ornate_gas_streetlamp",
            "scattered_news_broadsheets",
            "rally_civic_banners",
            "distant_church_spires",
        ],
        wear_level=0.25,
        density="BALANCED",
        depth_pattern="STREET_CANYON",
        foreground_vocabulary=["column_plinth_foreground", "streetlamp_post", "curb_sidewalk"],
        atmospheric_behavior={"morning_sun_flare": True, "fog_density": 0.0},
        interaction_affordances=["ORATE_PLAZA", "STAND_COLUMN", "READ_BROADSHEET", "WALK_STREET"],
    ),
}


def get_location_dna(location_id: str) -> LocationVisualDNA:
    """Resolve LocationVisualDNA from location_id or return closest matching template."""
    loc = location_id.lower()
    if any(k in loc for k in ["hospital", "lazarett", "pasewalk", "ward", "clinic"]):
        return DNA_CATALOG["MILITARY_HOSPITAL"]
    elif any(k in loc for k in ["hall", "beer", "tavern", "cellar", "buergerbraukeller"]):
        return DNA_CATALOG["BEER_HALL"]
    elif any(k in loc for k in ["trench", "somme", "front", "ypres", "flanders", "verdun"]):
        return DNA_CATALOG["WWI_TRENCH"]
    else:
        return DNA_CATALOG["EUROPEAN_STREET"]
