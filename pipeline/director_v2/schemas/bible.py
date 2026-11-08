"""Asset / continuity bibles. Generated per episode from the script — never hard-coded."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from .core import DV2Model


class CharacterState(DV2Model):
    """A continuity state (era/costume/injury) valid for a span of beats."""

    state_id: str
    label: str
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    beat_from: int = 0
    beat_to: Optional[int] = None
    age: Optional[int] = None
    costume_id: Optional[str] = None
    injury: str = "NONE"
    carried_prop_ids: list[str] = Field(default_factory=list)
    notes: str = ""


class CharacterProportions(DV2Model):
    head_ratio: float = 0.22                 # head height / body height
    height_scale: float = 1.0                # relative to cast average
    body_type: str = "average"               # slim | average | stocky
    shoulder_width: float = 1.0
    limb_thickness: float = 1.0


class Character(DV2Model):
    id: str                                  # CHAR_001
    name: str
    aliases: list[str] = Field(default_factory=list)
    role: str = "supporting"
    identity: str = ""
    proportions: CharacterProportions = Field(default_factory=CharacterProportions)
    face_anchors: list[str] = Field(default_factory=list)
    hair: str = "short"
    facial_hair: str = "none"
    posture: str = "upright"
    color_identity: str = "#3a3a3a"
    accent_color: str = "#b03a2e"
    voice: dict = Field(default_factory=dict)
    states: list[CharacterState] = Field(default_factory=list)
    rig_id: str = "stickman_v1"              # identity is rendered by the rig, not by image models
    master_ref_asset_id: Optional[str] = None


class LocationVariant(DV2Model):
    variant_id: str
    label: str
    year: Optional[int] = None
    changes: str = ""
    lighting: str = ""


class Location(DV2Model):
    id: str                                  # LOC_MUNICH_1913
    name: str
    year: Optional[int] = None
    era: str = ""
    kind: str = "exterior"                   # exterior | interior
    description: str = ""
    architecture: str = ""
    palette: list[str] = Field(default_factory=list)
    foreground_elements: list[str] = Field(default_factory=list)
    midground_elements: list[str] = Field(default_factory=list)
    background_elements: list[str] = Field(default_factory=list)
    far_background_elements: list[str] = Field(default_factory=list)
    default_lighting: str = "UPPER_LEFT"
    default_atmosphere: str = "clear"
    variants: list[LocationVariant] = Field(default_factory=list)
    master_ref_asset_id: Optional[str] = None


class Costume(DV2Model):
    id: str
    name: str
    era: str = ""
    description: str = ""
    colors: list[str] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)


class Prop(DV2Model):
    id: str
    name: str
    era: str = ""
    description: str = ""
    complexity: str = "simple"               # simple (rig/procedural) | complex (image provider)
    held: bool = False


class TimelineEvent(DV2Model):
    beat_index: int
    year: Optional[int] = None
    location_id: Optional[str] = None
    event: str = ""
    flashback: bool = False


class StylePreset(DV2Model):
    id: str
    name: str
    description: str
    palette: list[str] = Field(default_factory=list)
    line_style: str = ""
    character_style: str = ""
    environment_style: str = ""
    negative: list[str] = Field(default_factory=list)


class ProjectBible(DV2Model):
    project_id: str
    title: str
    language: str = "vi"
    style: StylePreset
    years: list[int] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    historical_constraints: list[str] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    costumes: list[Costume] = Field(default_factory=list)
    props: list[Prop] = Field(default_factory=list)
    continuity_warnings: list[str] = Field(default_factory=list)
