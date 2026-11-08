"""Stage 1 output: structured understanding of the pasted script."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from .core import DV2Model


class DialogueLine(DV2Model):
    speaker: str
    text: str


class Beat(DV2Model):
    """Smallest narrative unit the director plans around (1+ sentences)."""

    beat_id: str
    index: int
    text: str
    year: Optional[int] = None
    location_name: Optional[str] = None
    characters: list[str] = Field(default_factory=list)
    story_beat: str = "exposition"          # arrival, reveal, conflict, decision, aftermath...
    emotion: str = "neutral"
    intensity: float = Field(default=0.4, ge=0.0, le=1.0)
    historical_importance: str = "low"       # low | medium | high
    tone: str = "neutral"
    events: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    dialogue: list[DialogueLine] = Field(default_factory=list)
    est_duration_sec: float = Field(default=3.0, gt=0.0)


class CharacterMention(DV2Model):
    name: str
    aliases: list[str] = Field(default_factory=list)
    role: str = "supporting"                 # protagonist | antagonist | supporting | crowd
    description: str = ""
    first_beat: int = 0
    mentions: int = 1


class LocationMention(DV2Model):
    name: str
    years: list[int] = Field(default_factory=list)
    description: str = ""
    first_beat: int = 0


class ScriptAnalysis(DV2Model):
    title: str = "Untitled episode"
    language: str = "vi"
    narration_mode: str = "first_person"     # first_person | third_person | dialogue
    beats: list[Beat]
    characters: list[CharacterMention] = Field(default_factory=list)
    locations: list[LocationMention] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    total_est_duration_sec: float = 0.0
