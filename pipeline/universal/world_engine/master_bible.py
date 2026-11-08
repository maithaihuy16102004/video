"""Universal Location Master Bible & Architectural Geometry Compiler.

Implements the PROJECT-WIDE Location Art Direction Contract:
- A LOCATION IS NOT: BACKGROUND COLOR + WINDOW + TABLE + RANDOM PROPS.
- A LOCATION IS A PHYSICAL PLACE WITH:
  ARCHITECTURE, GEOGRAPHY, HISTORY, FUNCTION, MATERIALS, LANDMARKS,
  HUMAN TRACES, TECHNOLOGY, WEATHER, MOTIVATED LIGHT SOURCES, SPATIAL MEMORY.
- COMPOSABLE ARCHITECTURE: Built from generic architectural primitives:
  WALL, ARCH, COLUMN, BEAM, STAIR, WINDOW, DOOR, ROOF, CORRIDOR, BALCONY,
  PLATFORM, FENCE, TRENCH_EDGE, ROAD, PATH, TERRAIN, MACHINE_STRUCTURE.
- LOCATION TOPOLOGY: Genuine differences in boundaries, verticality, depth direction,
  openings, circulation, and landmark silhouettes.
- BACKGROUND TEMPLATE DETECTOR: Mathematical structural fingerprinting ensuring
  no two locations share the same room template.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ArchitecturalPrimitiveType(str, Enum):
    WALL = "WALL"
    ARCH = "ARCH"
    COLUMN = "COLUMN"
    BEAM = "BEAM"
    STAIR = "STAIR"
    WINDOW = "WINDOW"
    DOOR = "DOOR"
    ROOF = "ROOF"
    CORRIDOR = "CORRIDOR"
    BALCONY = "BALCONY"
    PLATFORM = "PLATFORM"
    FENCE = "FENCE"
    TRENCH_EDGE = "TRENCH_EDGE"
    ROAD = "ROAD"
    PATH = "PATH"
    TERRAIN = "TERRAIN"
    MACHINE_STRUCTURE = "MACHINE_STRUCTURE"


class ArchitecturalElement(BaseModel):
    """One executable piece of architecture placed into the scene space."""
    element_id: str
    primitive: ArchitecturalPrimitiveType
    # 2D/3D screen space bounding polygon in 1920x1080 coordinates
    polygon: list[tuple[float, float]]
    material: str = "STONE"            # STONE, BRICK, TIMBER, MUD, PLASTER, STEEL, GLASS
    depth_layer: str = "MIDGROUND"     # BACKGROUND, MIDGROUND, FOREGROUND, OVERHEAD
    elevation_z: float = 0.0           # Floor elevation relative to ground baseline
    opening_cutouts: list[list[tuple[float, float]]] = Field(default_factory=list)
    color_fill: str = "#4a453e"
    color_stroke: str = "#221e1a"
    stroke_width: float = 3.0
    irregularity: float = 0.2          # Hand-hewn / erosion roughness


class LandmarkProfile(BaseModel):
    """Major physical landmark that alters WORLD GEOMETRY, not just dressing."""
    landmark_id: str
    canonical_name: str
    dominant_silhouette: str           # e.g. "VAULTED_CATHEDRAL_NAVE", "ZIGZAG_EARTHEN_PARAPET", "TOWERING_GOTHIC_SPHERES"
    architectural_massing: str
    roofline: str
    signature_feature: str
    scale_multiplier: float = 1.0
    geometry_polygon: list[tuple[float, float]]
    dominant_depth_pos: tuple[float, float] = (960.0, 480.0)
    materials: list[str] = Field(default_factory=list)


class LocationTopology(BaseModel):
    """The fundamental physical layout, circulation, and boundary geometry."""
    boundary_polygon: list[tuple[float, float]]
    ground_contour: list[tuple[float, float]] # Points defining terrain / floor line
    horizon_y: float = 580.0                  # Screen horizon (trench = 420, room = 620, street = 540)
    vanishing_point: tuple[float, float] = (960.0, 580.0)
    dominant_depth_axis: str = "CENTRAL_RECEDING" # CENTRAL_RECEDING, DIAGONAL_LEFT, DIAGONAL_RIGHT, HORIZONTAL_CROSSING
    vertical_levels: list[float] = Field(default_factory=lambda: [0.0]) # Sunken vs raised floor heights
    circulation_corridor: list[tuple[float, float]] = Field(default_factory=list)
    blocked_zones: list[list[tuple[float, float]]] = Field(default_factory=list)
    enclosure_type: str = "INTERIOR"          # INTERIOR, EXTERIOR_OPEN, EXTERIOR_CONFINED, ENCLOSED_TRENCH


class MotivatedLightSource(BaseModel):
    """Motivated light source dictating shadow direction and color temperature."""
    source_id: str
    source_type: str                  # LANTERN, WINDOW_DAYLIGHT, BLAST_FLASH, CANDLE, CHANDELIER, SKY_DIFFUSE
    position: tuple[float, float]
    color_hex: str = "#f5d49e"
    intensity: float = 0.8
    falloff_radius_px: float = 750.0
    direction_vector: tuple[float, float] = (0.5, 0.85)


class HumanTracesDNA(BaseModel):
    """Tangible artifacts left by human presence, work, and habitation."""
    wear_patterns: list[str] = Field(default_factory=list) # e.g. ["FOOT_TRAFFIC_PATH", "SMOKE_STAINED_CEILING"]
    accumulated_debris: list[str] = Field(default_factory=list) # e.g. ["DISPATCH_PAPERS", "SPENT_SHELL_CASINGS"]
    personal_artifacts: list[str] = Field(default_factory=list) # e.g. ["KEROSENE_CAN", "WOODEN_CRATES"]
    damage_state: str = "INTACT"       # INTACT, WEATHERED_EROSION, ARTILLERY_SHATTERED, RECENT_BURST


class LocationMasterBible(BaseModel):
    """Single Source of Truth for a location across the entire narrative."""
    location_id: str
    canonical_name: str
    location_type: str                 # TRENCH_DUGOUT, URBAN_STREET, MILITARY_HOSPITAL, BEER_HALL, MOON_BASE
    country_region: str = ""
    era_date: str = ""
    primary_function: str = ""
    construction_system: str = ""      # EARTH_AND_TIMBER_REVETMENT, MASONRY_ASHLAR, INSTITUTIONAL_BRICK, HEAVY_TIMBER_POST_BEAM
    dominant_materials: list[str] = Field(default_factory=list)
    topology: LocationTopology
    architectural_elements: list[ArchitecturalElement] = Field(default_factory=list)
    landmark: Optional[LandmarkProfile] = None
    light_sources: list[MotivatedLightSource] = Field(default_factory=list)
    human_traces: HumanTracesDNA = Field(default_factory=HumanTracesDNA)
    prop_vocabulary: list[str] = Field(default_factory=list)
    color_palette: dict[str, str] = Field(default_factory=dict)
    historical_confidence: str = "HISTORICALLY_SUPPORTED" # SCRIPT_EXPLICIT, HISTORICALLY_SUPPORTED, PLAUSIBLE_RECONSTRUCTION


class StructuralFingerprint(BaseModel):
    """Mathematical signature used to detect template reuse or generic staging."""
    location_id: str
    horizon_normalized: float
    vanishing_point_normalized: tuple[float, float]
    boundary_area_ratio: float
    depth_axis_type: str
    architecture_mass_count: int
    dominant_verticality_score: float  # Tall vertical facade vs low sunken dugout
    openings_count: int
    ground_slope_deg: float


class BackgroundTemplateDetector:
    """Ensures that different locations do NOT share the same stage template."""

    @staticmethod
    def extract_fingerprint(loc: LocationMasterBible) -> StructuralFingerprint:
        topo = loc.topology
        horiz = topo.horizon_y / 1080.0
        vp = (topo.vanishing_point[0] / 1920.0, topo.vanishing_point[1] / 1080.0)

        # Ground slope
        gc = topo.ground_contour
        dx = gc[-1][0] - gc[0][0] if len(gc) >= 2 else 1920.0
        dy = gc[-1][1] - gc[0][1] if len(gc) >= 2 else 0.0
        slope = math.degrees(math.atan2(dy, dx if dx != 0 else 1.0))

        # Verticality score
        if loc.location_type in ("URBAN_STREET", "CATHEDRAL", "SKYSCRAPER"):
            vert = 0.9
        elif loc.location_type in ("MILITARY_HOSPITAL", "CLINIC"):
            vert = 0.55
        elif loc.location_type in ("BEER_HALL", "BANQUET"):
            vert = 0.4
        else: # Sunken trench
            vert = 0.15

        return StructuralFingerprint(
            location_id=loc.location_id,
            horizon_normalized=round(horiz, 3),
            vanishing_point_normalized=(round(vp[0], 3), round(vp[1], 3)),
            boundary_area_ratio=round(len(loc.architectural_elements) / 10.0, 2),
            depth_axis_type=topo.dominant_depth_axis,
            architecture_mass_count=len(loc.architectural_elements),
            dominant_verticality_score=vert,
            openings_count=sum(len(e.opening_cutouts) for e in loc.architectural_elements),
            ground_slope_deg=round(slope, 1),
        )

    @classmethod
    def audit_diversity(cls, locations: list[LocationMasterBible]) -> dict[str, Any]:
        """Audits a collection of locations to guarantee genuine architectural diversity."""
        fingerprints = {loc.location_id: cls.extract_fingerprint(loc) for loc in locations}
        pairs = []
        template_leakage_found = False

        loc_ids = list(fingerprints.keys())
        for i in range(len(loc_ids)):
            for j in range(i + 1, len(loc_ids)):
                id_a, id_b = loc_ids[i], loc_ids[j]
                fa, fb = fingerprints[id_a], fingerprints[id_b]

                # Distance metrics
                dh = abs(fa.horizon_normalized - fb.horizon_normalized)
                dv = abs(fa.dominant_verticality_score - fb.dominant_verticality_score)
                same_axis = (fa.depth_axis_type == fb.depth_axis_type)

                # Similarity score between 0 (completely different) and 1 (identical template)
                sim = 1.0 - (dh * 0.4 + dv * 0.4 + (0.0 if same_axis else 0.2))
                sim = max(0.0, min(1.0, sim))

                is_leakage = sim > 0.85
                if is_leakage:
                    template_leakage_found = True

                pairs.append({
                    "pair": f"{id_a} vs {id_b}",
                    "similarity_score": round(sim, 3),
                    "horizon_delta": round(dh, 3),
                    "verticality_delta": round(dv, 3),
                    "different_axis": not same_axis,
                    "template_leakage": is_leakage,
                })

        return {
            "status": "FAIL_TEMPLATE_LEAKAGE" if template_leakage_found else "PASS_GENUINE_ARCHITECTURAL_DIVERSITY",
            "total_locations": len(locations),
            "pairwise_comparisons": pairs,
            "fingerprints": {k: v.model_dump() for k, v in fingerprints.items()}
        }
