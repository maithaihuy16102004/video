"""Event-driven audio engine (Master Prompt §7).

SFX attach to actual visual events, never to arbitrary timestamps.
Meme rules: resolve through stable catalog IDs, never insert randomly,
never interrupt important dialogue, never insert a comedic sound into
a scene of severe suffering, death or a historical atrocity, never
substitute a missing meme with unrelated audio.

Upstream status (see AUDIT.md): strong foundations exist —
`pipeline/meme_resolver.py` (`MemeSoundResolver`, catalog of 188
memes in `assets/memes/catalog.json`), `pipeline/universal/sfx/`
(`sound_director.py`, `sound_registry.py`, `opportunity_detector.py`,
`semantic_tagger.py`, `repetition_guard.py`) and
`pipeline/universal/v5_audio_director.py` (stems + ducking).
What was missing: one small, testable map from visual event to SFX
with the meme guard rules in one place, plus the stem list the
pipeline must export. This module is that map; it delegates meme
resolution to the upstream catalog when a catalog path is given.

Stems every production must export:
    dialogue.wav, narration.wav, foley.wav, ambience.wav,
    music.wav, memes.wav, master_mix.wav
Mixing: dialogue priority, ducking -14 dB under speech.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Visual event -> SFX. The key is the animation event the engine
# emits (foot_contact, door_contact, ...), never a clock time.
EVENT_SFX_MAP: dict[str, dict[str, Any]] = {
    "foot_contact":   {"sfx": "FOOTSTEP",       "category": "foley", "gain_db": -18.0},
    "door_contact":   {"sfx": "DOOR_KNOCK",     "category": "foley", "gain_db": -12.0},
    "door_rotation":  {"sfx": "DOOR_OPEN",      "category": "foley", "gain_db": -12.0},
    "paper_movement": {"sfx": "PAPER_RUSTLE",   "category": "foley", "gain_db": -14.0},
    "object_impact":  {"sfx": "IMPACT",         "category": "foley", "gain_db": -10.0},
    "rain_start":     {"sfx": "RAIN_AMBIENCE",  "category": "ambience", "gain_db": -20.0},
    "crowd murmur":   {"sfx": "CROWD_AMBIENCE", "category": "ambience", "gain_db": -22.0},
    "character_reaction": {"sfx": "CONTEXTUAL_MEME", "category": "memes", "gain_db": -12.0},
}

# Keywords that mark a scene as serious: no comedic meme may be
# inserted, however funny the tag looks.
SERIOUS_KEYWORDS = (
    "chết", "tử vong", "đau thương", "thảm sát", "chiến tranh",
    "đói", "bệnh nặng", "tang lễ", "mộ", "tù đày", "tra tấn",
    "death", "killed", "massacre", "funeral",
)

STEMS = (
    "dialogue.wav", "narration.wav", "foley.wav", "ambience.wav",
    "music.wav", "memes.wav", "master_mix.wav",
)

DUCKING_DB = -14.0  # music/ambience duck under speech


@dataclass
class AudioEvent:
    event_type: str
    at_seconds: float
    sfx: str
    category: str
    gain_db: float
    source: str = "event_map"  # event_map | meme_catalog | synthesised
    meme_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type, "at_seconds": self.at_seconds,
            "sfx": self.sfx, "category": self.category,
            "gain_db": self.gain_db, "source": self.source,
            "meme_id": self.meme_id,
        }


@dataclass
class AudioEventPlan:
    events: list[AudioEvent] = field(default_factory=list)
    stems: tuple[str, ...] = STEMS
    ducking_db: float = DUCKING_DB
    blocked_memes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [e.to_dict() for e in self.events],
            "stems": list(self.stems),
            "ducking_db": self.ducking_db,
            "blocked_memes": self.blocked_memes,
        }


def is_serious_scene(script_text: str) -> bool:
    text = script_text.lower()
    return any(k in text for k in SERIOUS_KEYWORDS)


def resolve_meme(
    tag: str,
    *,
    script_text: str,
    dialogue_active: bool = False,
    catalog: dict | None = None,
) -> dict[str, Any] | None:
    """Resolve one meme tag through the catalog, or refuse it.

    Returns None (with a reason) when the meme must not be inserted.
    Never substitutes a missing meme with unrelated audio.
    """
    if is_serious_scene(script_text):
        return {"inserted": False, "reason": "serious scene — no comedic meme"}
    if dialogue_active:
        return {"inserted": False, "reason": "would interrupt important dialogue"}
    if catalog is None:
        return {"inserted": False, "reason": "no meme catalog available"}
    memes = catalog.get("memes", [])
    for meme in memes:
        if tag.lower() in (meme.get("slug", ""), meme.get("id", ""), meme.get("title", "").lower()):
            return {"inserted": True, "meme_id": meme.get("id"),
                    "filename": meme.get("filename"), "gain_db": -12.0}
    return {"inserted": False, "reason": f"meme {tag!r} not in catalog — no substitute"}


def load_meme_catalog(catalog_path: Path) -> dict:
    with open(catalog_path, encoding="utf-8") as f:
        return json.load(f)


def plan_audio_events(
    visual_events: list[dict[str, Any]],
    *,
    script_text: str = "",
    meme_catalog: dict | None = None,
    dialogue_windows: list[tuple[float, float]] | None = None,
) -> AudioEventPlan:
    """Turn animation events into a timed SFX plan.

    visual_events: [{"event": "foot_contact", "at_seconds": 1.2}, ...]
    Unknown events are dropped with a note — never invented as a
    different sound, never placed at an arbitrary time.
    """
    plan = AudioEventPlan()
    dialogue_windows = dialogue_windows or []
    for ev in visual_events:
        event_type = ev.get("event", "")
        at = float(ev.get("at_seconds", 0.0))
        spec = EVENT_SFX_MAP.get(event_type)
        if spec is None:
            plan.blocked_memes.append({
                "event": event_type, "reason": "unknown visual event — no SFX invented",
            })
            continue
        if spec["sfx"] == "CONTEXTUAL_MEME":
            tag = ev.get("meme_tag", "")
            dialogue_active = any(a <= at <= b for a, b in dialogue_windows)
            result = resolve_meme(tag, script_text=script_text,
                                  dialogue_active=dialogue_active,
                                  catalog=meme_catalog)
            if not result.get("inserted"):
                plan.blocked_memes.append({
                    "event": event_type, "meme_tag": tag,
                    "reason": result.get("reason"),
                })
                continue
            plan.events.append(AudioEvent(
                event_type, at, spec["sfx"], spec["category"], spec["gain_db"],
                source="meme_catalog", meme_id=result.get("meme_id"),
            ))
        else:
            plan.events.append(AudioEvent(
                event_type, at, spec["sfx"], spec["category"], spec["gain_db"],
            ))
    return plan
