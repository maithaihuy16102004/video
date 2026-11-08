"""Semantic Foreground Modeling and Identity.

Eliminates anonymous decorative "dark rectangle" occluders.
Every foreground element is a physically motivated, named scene asset possessing:
- asset_instance_id
- semantic_identity
- world_position & depth
- physical material
- foreground_reason (why the camera sees it)
- physical bounding box and rendering affordance
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import Field

from ..schemas import UModel


class ForegroundReason(str, Enum):
    BEHIND_FURNITURE = "BEHIND_FURNITURE"       # e.g. edge of tavern table or desk
    BEHIND_ACTOR = "BEHIND_ACTOR"               # OTS over-the-shoulder framing
    THROUGH_DOORWAY = "THROUGH_DOORWAY"         # door jamb / arch framing
    INSIDE_TERRAIN = "INSIDE_TERRAIN"           # earthwork revetment corner, boulder, parapet
    BESIDE_MACHINERY = "BESIDE_MACHINERY"       # industrial apparatus casing, workbench edge
    INSIDE_CROWD = "INSIDE_CROWD"               # silhouette of foreground listener
    NONE = "NONE"


class ForegroundElement(UModel):
    """Physically grounded foreground framing element."""
    asset_instance_id: str
    semantic_identity: str
    material: str = "WOOD"
    depth: float = 0.08                         # distance in front of focal plane
    screen_rect: list[float] = Field(default_factory=lambda: [0.0, 0.3, 0.15, 1.0])  # x0, y0, x1, y1
    foreground_reason: str = ForegroundReason.NONE.value
    is_occluder: bool = True
    alpha: float = 0.95
    edge_side: str = "LEFT"                     # LEFT | RIGHT | BOTTOM | ARCH


def resolve_semantic_foreground(
    location_enclosure: str,
    location_id: str,
    camera_shot: str,
    shot_purpose: str,
    primary_actor_id: Optional[str] = None,
) -> Optional[ForegroundElement]:
    """Deterministically resolves an authentic, physically plausible foreground element."""
    shot_upper = camera_shot.upper()
    loc_low = location_id.lower()

    # 1. Over-The-Shoulder shot -> Foreground actor silhouette
    if "OTS" in shot_upper and primary_actor_id:
        return ForegroundElement(
            asset_instance_id=f"fg_actor_shoulder_{primary_actor_id}",
            semantic_identity=f"Foreground shoulder & coat silhouette of {primary_actor_id}",
            material="FABRIC",
            depth=0.06,
            screen_rect=[-0.05, 0.40, 0.26, 1.05],
            foreground_reason=ForegroundReason.BEHIND_ACTOR.value,
            edge_side="LEFT",
        )

    # 2. Exterior rugged terrain / natural obstacle
    if location_enclosure.upper() == "EXTERIOR" or "pass" in loc_low or "mountain" in loc_low or "ridge" in loc_low:
        if "GROUND" in shot_upper or "LOW" in shot_upper or shot_purpose in ("ACTION", "TENSION", "LOCATION"):
            return ForegroundElement(
                asset_instance_id="fg_terrain_revetment_corner",
                semantic_identity="Split timber revetment post and weathered obstacle framing",
                material="WOOD",
                depth=0.08,
                screen_rect=[-0.04, 0.30, 0.16, 1.05],
                foreground_reason=ForegroundReason.INSIDE_TERRAIN.value,
                edge_side="LEFT",
            )

    # 3. Interior Table / Desk / Conference Chamber
    if any(k in loc_low for k in ("office", "cabinet", "meeting", "chamber", "boardroom", "table", "tavern")):
        if "DEEP" in shot_upper or shot_purpose in ("REACTION", "INFORMATION", "OBJECT_INFORMATION", "TENSION"):
            return ForegroundElement(
                asset_instance_id="fg_table_corner_01",
                semantic_identity="Edge of solid oak conference table and foreground glassware",
                material="WOOD",
                depth=0.10,
                screen_rect=[0.68, 0.72, 1.05, 1.05],
                foreground_reason=ForegroundReason.BEHIND_FURNITURE.value,
                edge_side="RIGHT",
            )

    # 4. Interior Workshop / Production Facility / Apparatus / Kitchen
    if any(k in loc_low for k in ("bakery", "workshop", "lab", "kitchen", "station", "facility")):
        if shot_purpose in ("OBJECT_INFORMATION", "ACTION", "REVEAL", "EFFECT"):
            return ForegroundElement(
                asset_instance_id="fg_apparatus_workbench_flange",
                semantic_identity="Beveled brass workbench upright and insulated conductor wire",
                material="METAL",
                depth=0.07,
                screen_rect=[-0.03, 0.28, 0.14, 1.05],
                foreground_reason=ForegroundReason.BESIDE_MACHINERY.value,
                edge_side="LEFT",
            )

    # 5. Interior Recovery Quarters / Dormitory / Clinic
    if any(k in loc_low for k in ("ward", "clinic", "dormitory", "infirmary", "bedroom")):
        if "CLOSE" in shot_upper or "OTS" in shot_upper:
            return ForegroundElement(
                asset_instance_id="fg_cast_iron_bedpost",
                semantic_identity="Cast-iron vintage bedpost finial with enamel finish",
                material="METAL",
                depth=0.07,
                screen_rect=[0.82, 0.25, 0.98, 1.05],
                foreground_reason=ForegroundReason.BEHIND_FURNITURE.value,
                edge_side="RIGHT",
            )

    # 6. Doorway entrance / Hallway threshold
    if location_enclosure.upper() == "INTERIOR" and shot_purpose in ("LOCATION", "ARRIVAL"):
        return ForegroundElement(
            asset_instance_id="fg_doorway_jamb_arch",
            semantic_identity="Molded timber doorway jamb framing the interior room",
            material="WOOD",
            depth=0.05,
            screen_rect=[-0.04, 0.0, 0.12, 1.05],
            foreground_reason=ForegroundReason.THROUGH_DOORWAY.value,
            edge_side="LEFT",
        )

    return None
