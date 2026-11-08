"""Asset requirements, cache entries and the reuse plan."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field

from .core import DV2Model, ImageTier, LayerRole, NormRect


class AssetKind(str, Enum):
    CHARACTER_MASTER = "CHARACTER_MASTER"      # reference sheet (MASTER quality only)
    LOCATION_MASTER = "LOCATION_MASTER"        # reference for every plate of a location
    ENVIRONMENT_PLATE = "ENVIRONMENT_PLATE"    # FAR_BG/BG/MG plate serving N shots
    FOREGROUND_ELEMENT = "FOREGROUND_ELEMENT"  # FG occluder, isolated on chroma
    PROP = "PROP"                              # complex historical prop, isolated on chroma
    FX_ELEMENT = "FX_ELEMENT"                  # special atmospheric element


class AssetStatus(str, Enum):
    PLANNED = "PLANNED"                  # missing; would be generated
    SKIPPED_DRY_RUN = "SKIPPED_DRY_RUN"  # missing; dry-run so not generated
    SKIPPED_DRAFT = "SKIPPED_DRAFT"      # DRAFT quality renders procedurally
    CACHED = "CACHED"                    # found in cache, no API call
    GENERATED = "GENERATED"              # generated and passed QC
    FAILED_QC = "FAILED_QC"              # retries exhausted; best attempt kept
    ERROR = "ERROR"                      # provider error


class AssetRequirement(DV2Model):
    requirement_id: str
    kind: AssetKind
    layer_roles: list[LayerRole] = Field(default_factory=list)
    subject_id: str                          # location_id / prop_id / character_id
    semantic_key: str                        # model-independent identity, used for reuse
    description: str = ""
    shot_ids: list[str] = Field(default_factory=list)
    tier: ImageTier = ImageTier.MAIN
    aspect_ratio: str = "16:9"
    image_size: str = "1K"
    reference_requirement_ids: list[str] = Field(default_factory=list)
    matte: str = "none"
    camera_height_bucket: str = ""
    perspective_family: str = ""
    lighting_key: str = ""
    historical_constraints: list[str] = Field(default_factory=list)
    prompt: str = ""
    cache_key: str = ""


class CriticAttempt(DV2Model):
    attempt: int
    model: str
    scores: dict[str, Optional[float]] = Field(default_factory=dict)
    failed_criteria: list[str] = Field(default_factory=list)
    notes: str = ""
    path: Optional[str] = None


class Asset(DV2Model):
    requirement_id: str
    status: AssetStatus
    path: Optional[str] = None
    model: Optional[str] = None
    tier: Optional[ImageTier] = None
    cache_key: str = ""
    cache_hit: bool = False
    attempts: list[CriticAttempt] = Field(default_factory=list)
    cost_usd: Optional[float] = None
    error: Optional[str] = None


class AssetManifest(DV2Model):
    requirements: list[AssetRequirement]
    assets: list[Asset] = Field(default_factory=list)


class ReuseOp(str, Enum):
    DIRECT = "DIRECT"
    CROP = "CROP"
    REFRAME = "REFRAME"
    PARALLAX = "PARALLAX"
    RELIGHT = "RELIGHT"
    MIRROR = "MIRROR"
    BLUR_DEPTH = "BLUR_DEPTH"


class ReuseEntry(DV2Model):
    shot_id: str
    layer_role: LayerRole
    requirement_id: str
    ops: list[ReuseOp] = Field(default_factory=list)
    crop: Optional[NormRect] = None
    is_first_use: bool = False
    reason: str = ""


class ReusePlan(DV2Model):
    entries: list[ReuseEntry]
    shot_count: int
    unique_image_requirements: int
    generated_layer_slots: int
    reuse_ratio: float                       # generated layer slots served per unique image
