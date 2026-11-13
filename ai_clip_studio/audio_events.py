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

STUDIO SCRIPT V1 cue wiring (Phase B Stage 3): ``resolve_v1_cues``
turns the preserved ``v1_audio_cues`` (old dialect: flat cues with
LINE_ID/action-text TRIGGERs; new dialect: structured SFX sub-blocks
inside SHOT blocks with cue_id/event/trigger/intensity/duration)
into timed synthesis jobs using ONLY the measured timeline clock.
Trigger times are recomputed here; planner timestamps are never
trusted. Every synthesis is labelled with its lavfi method in the
audio plan so no synthesised sound is mistaken for a recorded
effect. Cues with no honest synthesis are reported unmapped, never
given a substitute sound. Memes are never auto-rendered.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Visual event -> SFX. The key is the animation event the engine
# emits (foot_contact, door_contact, ...), never a clock time.
EVENT_SFX_MAP: dict[str, dict[str, Any]] = {
    "foot_contact":   {"sfx": "FOOTSTEP",       "category": "foley", "gain_db": -18.0},
    "hammer_contact": {"sfx": "METAL_STRIKE",   "category": "foley", "gain_db": -12.0},
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
    # V1 cue provenance (Stage 3): set only for events resolved from
    # a scripted V1 cue. All optional; existing callers are unaffected.
    end_seconds: float | None = None
    cue_name: str | None = None
    cue_id: str | None = None
    scene: int | None = None
    synthesis: str | None = None  # lavfi method label, when synthesised

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "event_type": self.event_type, "at_seconds": self.at_seconds,
            "sfx": self.sfx, "category": self.category,
            "gain_db": self.gain_db, "source": self.source,
            "meme_id": self.meme_id,
        }
        if self.end_seconds is not None:
            d["end_seconds"] = self.end_seconds
        if self.cue_name is not None:
            d["cue_name"] = self.cue_name
        if self.cue_id is not None:
            d["cue_id"] = self.cue_id
        if self.scene is not None:
            d["scene"] = self.scene
        if self.synthesis is not None:
            d["synthesis"] = self.synthesis
        return d


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


# ---------------------------------------------------------------------------
# STUDIO SCRIPT V1 cue wiring (Phase B Stage 3)
# ---------------------------------------------------------------------------
# Pure functions only: no subprocess, no file I/O. The mixer in
# product_flow.py turns the jobs returned here into real stems.
#
# Cue shapes consumed (defensively, via _cue_get with fallbacks):
#   Old dialect (parser to_dict / adapter v1_audio_cues): cue_type,
#     name, trigger, priority, mode, intensity, gain_db, scene_number,
#     shot_id, line, source_key.
#   New dialect (structured SFX sub-blocks inside SHOT blocks): cue_id
#     (SFX_001), event (human name), trigger (SNAKE_CASE event token
#     such as PROP_WALLET_OPEN), cue_type_text / type (TYPE text such
#     as "Soft leather rustle"), intensity (LOW/MODERATE/HIGH),
#     duration ("0.4s") or duration_mode (ACTION_DURATION).
#   Trait blocks (SPEC section 15.4, emitted by the planner agent):
#     package["trait_blocks"]["audio"] — SFX events carrying an engine
#     "event" plus music events. Planner timestamps in trait data are
#     NEVER trusted; every time is recomputed from the measured clock.
#
# Trigger resolution rules (see resolve_v1_cues docstring for the full
# contract): LINE_ID -> that line's measured start; SNAKE_CASE event
# token -> the owning shot's start; action text -> the matching shot's
# start, else the scene start (recorded fallback); scene-level
# AMBIENCE/BGM -> the scene span. Unresolvable triggers are recorded
# as V1E022 review requirements, never placed at invented times.

#: SPEC section 5.6 GLOBAL_AUDIO defaults (dB).
SPEC_AUDIO_DEFAULTS: dict[str, float] = {
    "narration_gain_db": 0.0,
    "dialogue_gain_db": 0.0,
    "ambience_gain_db": -18.0,
    "foley_gain_db": -12.0,
    "sfx_gain_db": -6.0,
    "bgm_gain_db": -18.0,
    "bgm_ducking_db": -6.0,
    "master_limit_db": -1.0,
}

#: INTENSITY ladder (dB offset added to the synthesis base gain).
#: MODERATE (new dialect) == MEDIUM (old dialect). HIGH is capped by
#: the mixer's measured restraint loop, never by raising the voice.
INTENSITY_OFFSETS: dict[str, float] = {
    "LOW": -6.0,
    "VERY_LOW": -12.0,
    "VERY LOW": -12.0,
    "MODERATE": 0.0,
    "MEDIUM": 0.0,
    "HIGH": 3.0,
}


def intensity_offset(intensity: str | None) -> float:
    """dB offset for an INTENSITY label; unknown/empty -> 0 dB."""
    if not intensity:
        return 0.0
    return INTENSITY_OFFSETS.get(str(intensity).strip().upper(), 0.0)


#: Synthesis kinds. Each spec renders ONE segment wav with ffmpeg
#: lavfi; ``{dur}`` / ``{fade_st}`` / ``{fade_d}`` / ``{edge}`` are
#: filled in by the mixer. ``method`` is the honesty label recorded
#: in audio_plan.json for every rendered segment. There are no SFX
#: asset files in this pipeline: everything here is synthesised
#: noise/tones, and the label says so. Sounds with no honest
#: synthesis (bells, fanfare, crowd roar, bugle, shouting, ...) have
#: NO entry here and are reported unmapped, never substituted.
SYNTHESIS_MAP: dict[str, dict[str, Any]] = {
    "knock": {
        "duration_default": 0.4, "category": "foley",
        "base_gain_db": -12.0,
        "method": "synthesised: white-noise burst (bandpass 700 Hz) "
                  "+ 140 Hz thump (ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=white:duration={dur}",
                   "sine=frequency=140:duration={dur}"],
        "filter": "[0:a]bandpass=f=700:width_type=h:width=500,"
                  "afade=t=out:st={fade_st}:d={fade_d},volume=0.9[n];"
                  "[1:a]afade=t=out:st=0:d={fade_d},volume=0.7[t];"
                  "[n][t]amix=inputs=2:normalize=0[out]",
    },
    "metal_strike": {
        "duration_default": 0.7, "category": "foley",
        "base_gain_db": -12.0,
        "method": "synthesised: hammer-on-anvil ring (four "
                  "inharmonic partials 587/1244/2093/3520 Hz decaying "
                  "across the strike + a 50 ms bandpassed noise "
                  "transient, ffmpeg lavfi)",
        "inputs": ["sine=frequency=587:duration={dur}",
                   "sine=frequency=1244:duration={dur}",
                   "sine=frequency=2093:duration={dur}",
                   "sine=frequency=3520:duration={dur}",
                   "anoisesrc=color=white:duration={dur}"],
        "filter": "[0:a]afade=t=out:st=0:d={dur},volume=0.9[p0];"
                  "[1:a]afade=t=out:st=0:d={dur},volume=0.55[p1];"
                  "[2:a]afade=t=out:st=0:d={dur},volume=0.35[p2];"
                  "[3:a]afade=t=out:st=0:d={dur},volume=0.22[p3];"
                  "[4:a]bandpass=f=3200:width_type=h:width=2000,"
                  "afade=t=out:st=0:d=0.05,volume=0.5[n];"
                  "[p0][p1][p2][p3][n]amix=inputs=5:normalize=0[out]",
    },
    "door_open": {
        "duration_default": 0.8, "category": "foley",
        "base_gain_db": -12.0,
        "method": "synthesised: pink-noise swell (bandpass 350 Hz, "
                  "soft door-movement noise, ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=pink:duration={dur}"],
        "filter": "[0:a]bandpass=f=350:width_type=h:width=300,"
                  "afade=t=in:st=0:d=0.25,"
                  "afade=t=out:st={fade_st}:d={fade_d},volume=0.5[out]",
    },
    "paper_rustle": {
        "duration_default": 0.6, "category": "foley",
        "base_gain_db": -14.0,
        "method": "synthesised: white-noise rustle (highpass 1800 Hz, "
                  "bandpass 4500 Hz, ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=white:duration={dur}"],
        "filter": "[0:a]highpass=f=1800,"
                  "bandpass=f=4500:width_type=h:width=2500,"
                  "afade=t=in:st=0:d=0.05,"
                  "afade=t=out:st={fade_st}:d={fade_d},volume=0.7[out]",
    },
    "soft_rustle": {
        "duration_default": 0.4, "category": "foley",
        "base_gain_db": -16.0,
        "method": "synthesised: soft cloth/leather rustle "
                  "(bandpass 2500 Hz noise, ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=white:duration={dur}"],
        "filter": "[0:a]bandpass=f=2500:width_type=h:width=1800,"
                  "afade=t=in:st=0:d=0.05,"
                  "afade=t=out:st={fade_st}:d={fade_d},volume=0.5[out]",
    },
    "writing_scratch": {
        "duration_default": 1.0, "category": "foley",
        "base_gain_db": -18.0,
        "method": "synthesised: soft writing scratch (highpassed "
                  "noise with 6 Hz tremolo, ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=white:duration={dur}"],
        "filter": "[0:a]highpass=f=2500,tremolo=f=6:d=0.6,"
                  "afade=t=in:st=0:d=0.05,"
                  "afade=t=out:st={fade_st}:d={fade_d},volume=0.35[out]",
    },
    "impact": {
        "duration_default": 0.35, "category": "foley",
        "base_gain_db": -10.0,
        "method": "synthesised: impact burst (bandpass 500 Hz noise) "
                  "+ 90 Hz thump (ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=white:duration={dur}",
                   "sine=frequency=90:duration={dur}"],
        "filter": "[0:a]bandpass=f=500:width_type=h:width=400,"
                  "afade=t=out:st={fade_st}:d={fade_d},volume=0.9[n];"
                  "[1:a]afade=t=out:st=0:d={fade_d},volume=0.8[t];"
                  "[n][t]amix=inputs=2:normalize=0[out]",
    },
    "footstep": {
        "duration_default": 0.18, "category": "foley",
        "base_gain_db": -18.0,
        "method": "synthesised: single soft footstep (85 Hz thump + "
                  "lowpassed noise, ffmpeg lavfi)",
        "inputs": ["sine=frequency=85:duration={dur}",
                   "anoisesrc=color=white:duration={dur}"],
        "filter": "[0:a]afade=t=out:st=0:d={fade_d},volume=0.8[t];"
                  "[1:a]lowpass=f=300,"
                  "afade=t=out:st=0:d={fade_d},volume=0.4[n];"
                  "[t][n]amix=inputs=2:normalize=0[out]",
    },
    "march_bed": {
        "duration_default": 2.0, "category": "foley",
        "base_gain_db": -20.0,
        "method": "synthesised: soft collective footsteps (lowpassed "
                  "noise + 70 Hz pulse at 1.8 Hz march cadence, "
                  "ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=pink:duration={dur}",
                   "sine=frequency=70:duration={dur}"],
        "filter": "[0:a]lowpass=f=250,tremolo=f=1.8:d=0.7,"
                  "volume=0.5[n];"
                  "[1:a]tremolo=f=1.8:d=0.7,volume=0.25[t];"
                  "[n][t]amix=inputs=2:normalize=0,"
                  "afade=t=in:st=0:d={edge},"
                  "afade=t=out:st={fade_st}:d={fade_d}[out]",
    },
    "mud_squelch": {
        "duration_default": 0.5, "category": "foley",
        "base_gain_db": -14.0,
        "method": "synthesised: wet foot-in-mud impact approximation "
                  "(lowpassed noise burst with slow attack + 70 Hz "
                  "thump, ffmpeg lavfi) — not a recorded squelch",
        "inputs": ["anoisesrc=color=white:duration={dur}",
                   "sine=frequency=70:duration={dur}"],
        "filter": "[0:a]lowpass=f=350,afade=t=in:st=0:d=0.15,"
                  "afade=t=out:st={fade_st}:d={fade_d},volume=0.8[n];"
                  "[1:a]afade=t=in:st=0:d=0.1,"
                  "afade=t=out:st=0:d={fade_d},volume=0.6[t];"
                  "[n][t]amix=inputs=2:normalize=0[out]",
    },
    "artillery_rumble": {
        "duration_default": 1.5, "category": "foley",
        "base_gain_db": -16.0,
        "method": "synthesised: muffled distant rumble (brown noise, "
                  "lowpass 180 Hz + 45 Hz tone, ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=brown:duration={dur}",
                   "sine=frequency=45:duration={dur}"],
        "filter": "[0:a]lowpass=f=180,afade=t=in:st=0:d=0.2,"
                  "afade=t=out:st={fade_st}:d={fade_d},volume=0.7[n];"
                  "[1:a]afade=t=in:st=0:d=0.2,"
                  "afade=t=out:st=0:d={fade_d},volume=0.5[t];"
                  "[n][t]amix=inputs=2:normalize=0[out]",
    },
    "rain_bed": {
        "duration_default": 10.0, "category": "ambience",
        "base_gain_db": -20.0,
        "method": "synthesised: rain bed (pink noise, lowpass 800 Hz, "
                  "ffmpeg lavfi) — same chain as the pipeline rain bed",
        "inputs": ["anoisesrc=color=pink:duration={dur}"],
        "filter": "[0:a]lowpass=f=800,volume=0.10[out]",
    },
    "crowd_bed": {
        "duration_default": 10.0, "category": "ambience",
        "base_gain_db": -22.0,
        "method": "synthesised: crowd-murmur bed (bandpass 500 Hz "
                  "noise with slow tremolo, ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=pink:duration={dur}"],
        "filter": "[0:a]bandpass=f=500:width_type=h:width=600,"
                  "tremolo=f=0.7:d=0.4,volume=0.18[out]",
    },
    "street_bed": {
        "duration_default": 10.0, "category": "ambience",
        "base_gain_db": -20.0,
        "method": "synthesised: distant street-activity bed "
                  "(bandpass 700 Hz noise with slow tremolo, "
                  "ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=pink:duration={dur}"],
        "filter": "[0:a]bandpass=f=700:width_type=h:width=1000,"
                  "tremolo=f=0.4:d=0.3,volume=0.16[out]",
    },
    "wind_bed": {
        "duration_default": 10.0, "category": "ambience",
        "base_gain_db": -22.0,
        "method": "synthesised: wind bed (pink noise, lowpass 400 Hz "
                  "with slow tremolo, ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=pink:duration={dur}"],
        "filter": "[0:a]lowpass=f=400,tremolo=f=0.3:d=0.5,"
                  "volume=0.15[out]",
    },
    "room_tone": {
        "duration_default": 10.0, "category": "ambience",
        "base_gain_db": -26.0,
        "method": "synthesised: quiet room tone (pink noise, lowpass "
                  "300 Hz at very low level, ffmpeg lavfi)",
        "inputs": ["anoisesrc=color=pink:duration={dur}"],
        "filter": "[0:a]lowpass=f=300,volume=0.06[out]",
    },
    "music_pad": {
        "duration_default": 10.0, "category": "music",
        "base_gain_db": -18.0,
        "method": "synthesised: generic soft sine pad (220/277/330 "
                  "Hz) — NOT the scripted piece; no recorded music "
                  "exists in this pipeline (ffmpeg lavfi)",
        "inputs": ["sine=frequency=220:duration={dur}",
                   "sine=frequency=277.18:duration={dur}",
                   "sine=frequency=329.63:duration={dur}"],
        "filter": "[0:a]volume=0.08,afade=t=in:st=0:d={edge}[a];"
                  "[1:a]volume=0.06,afade=t=in:st=0:d={edge}[b];"
                  "[2:a]volume=0.05,afade=t=in:st=0:d={edge}[c];"
                  "[a][b][c]amix=inputs=3:normalize=0,"
                  "afade=t=out:st={fade_st}:d={fade_d}[out]",
    },
}

#: Engine event -> synthesis kind. character_reaction is deliberately
#: absent: memes are never synthesised (see resolve_meme guards).
ENGINE_EVENT_SYNTH: dict[str, str] = {
    "door_contact": "knock",
    "door_rotation": "door_open",
    "paper_movement": "paper_rustle",
    "object_impact": "impact",
    "foot_contact": "footstep",
    "hammer_contact": "metal_strike",
    "rain_start": "rain_bed",
    "crowd murmur": "crowd_bed",
}

#: Synthesis kinds that fill a span (ambience beds) rather than a
#: point in time. An SFX cue mapping to one of these renders as a
#: bed from its trigger time to the end of its scene.
BED_KINDS = frozenset(
    {"rain_bed", "crowd_bed", "street_bed", "wind_bed", "room_tone"})

#: Kinds an AMBIENCE cue part may fill a scene span with: the bed
#: kinds, plus span-capable textures (collective footsteps, distant
#: rumble). Point-only kinds (knock, impact, paper, ...) cannot fill
#: an ambience span and are reported as unrendered parts.
_AMBIENCE_SPAN_KINDS = BED_KINDS | {"march_bed", "artillery_rumble"}

#: Bus short name -> GLOBAL_AUDIO gain key.
_BUS_GAIN_KEY = {
    "narration": "narration_gain_db",
    "dialogue": "dialogue_gain_db",
    "ambience": "ambience_gain_db",
    "foley": "foley_gain_db",
    "sfx": "sfx_gain_db",
    "bgm": "bgm_gain_db",
}


def _normalize_text(text: str) -> str:
    """Lowercase, accent-stripped, punctuation-free text for keyword
    and trigger matching. Vietnamese đ/Đ map to d before NFKD (they
    have no decomposition and would otherwise vanish)."""
    s = (text or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return " ".join(s.split())


def _keyword_hit(norm_text: str, tokens: set[str], keyword: str) -> bool:
    if " " in keyword:
        return re.search(r"\b" + re.escape(keyword) + r"\b",
                         norm_text) is not None
    return keyword in tokens


#: Cue-name/TYPE keyword table: (synthesis kind, engine event,
#: keywords). First match wins, in order — specific rules (paper,
#: writing, march) precede generic ones (rustle, impact). Matching
#: runs on accent-stripped text with word boundaries, so "paper"
#: never matches "paperboy". Anything matching nothing here is
#: UNMAPPED (bells, fanfare, sirens, bugle, shouting, cheering,
#: crowd roar, carriage, ...): no entry, no substitute sound.
_CUE_KEYWORDS: tuple[tuple[str, str | None, tuple[str, ...]], ...] = (
    ("knock", "door_contact",
     ("door knock", "knock", "knocking", "go cua")),
    ("door_open", "door_rotation",
     ("door open", "door opening", "mo cua", "cua mo")),
    ("paper_rustle", "paper_movement",
     ("paper rustle", "rustling paper", "paper", "giay")),
    ("writing_scratch", None,
     ("writing", "scratch", "pen", "viet")),
    ("march_bed", None,
     ("marching", "march", "collective footsteps", "group footsteps",
      "hanh quan")),
    ("footstep", "foot_contact",
     ("footsteps", "footstep", "buoc chan", "buoc di", "stamp",
      "boots")),
    ("mud_squelch", None, ("mud", "squelch", "bun")),
    ("artillery_rumble", None,
     ("artillery", "rumble", "phao", "distant boom", "boom")),
    ("rain_bed", "rain_start", ("rain", "mua")),
    ("crowd_bed", "crowd murmur", ("murmur", "murmuring")),
    ("wind_bed", None, ("wind", "gio")),
    ("room_tone", None, ("room tone", "room", "indoor", "attic")),
    ("street_bed", None, ("street", "city", "activity", "soldiers")),
    ("soft_rustle", None, ("rustle", "leather")),
    ("metal_strike", "hammer_contact",
     ("metal strike", "hammer strike", "hammer", "hammers",
      "hammering", "anvil", "clang", "clanging", "metal clang",
      "forge strike", "cai de", "bua", "dap bua", "go bua",
      "tieng bua", "kim loai", "metal")),
    ("impact", "object_impact",
     ("set down", "dropping", "drop", "drops", "roi", "dat xuong",
      "pickup", "pick up", "impact", "thud")),
)


def _match_part(part_text: str) -> tuple[str, str | None] | None:
    """Match one (compound-split) cue-name part to a synthesis kind,
    or None when no honest synthesis exists for it."""
    norm = _normalize_text(part_text)
    tokens = set(norm.split())
    for kind, engine_event, keywords in _CUE_KEYWORDS:
        if any(_keyword_hit(norm, tokens, kw) for kw in keywords):
            return (kind, engine_event)
    return None


_COMPOUND_SPLIT_RE = re.compile(
    r"\s+(?:and|và)\s+|\s*;\s*|\s*&\s*", re.IGNORECASE)


def _split_compound(text: str) -> list[str]:
    """Split a compound cue name ("X and Y") into parts. Each part is
    mapped independently: mapped parts render, unmapped parts are
    reported (partial mapping), never substituted."""
    parts = [p.strip() for p in _COMPOUND_SPLIT_RE.split(text or "")]
    return [p for p in parts if p]


def _cue_get(cue: Any, *keys: str, default: Any = None) -> Any:
    """Read a cue field from a dict or a dataclass/object, trying
    each key in order. Cue shapes differ between dialects; every
    read in the resolver goes through here."""
    for key in keys:
        if isinstance(cue, dict):
            if key in cue and cue[key] is not None:
                return cue[key]
        else:
            value = getattr(cue, key, None)
            if value is not None:
                return value
    return default


_TIME_KEYS = ("at_seconds", "start", "start_sec", "start_seconds",
              "time", "timestamp")


def _verbatim_cue(cue: Any) -> tuple[dict[str, Any], bool]:
    """Echo a cue's declared fields verbatim for the report, EXCLUDING
    any timestamp keys (planner times are never trusted). Returns
    (fields, had_planner_timestamp)."""
    fields: dict[str, Any] = {}
    for key in ("cue_type", "name", "event", "trigger", "priority",
                "mode", "intensity", "gain_db", "scene_number",
                "scene", "shot_id", "shot", "line", "source_key",
                "cue_id", "id", "cue_type_text", "type", "type_text",
                "duration", "duration_seconds", "duration_mode"):
        value = _cue_get(cue, key, default=None)
        if value is not None:
            fields[key] = value
    had_time = False
    if isinstance(cue, dict):
        had_time = any(k in cue for k in _TIME_KEYS)
    else:
        had_time = any(getattr(cue, k, None) is not None
                       for k in _TIME_KEYS)
    return fields, had_time


_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*s?\s*$",
                          re.IGNORECASE)


def parse_cue_duration(cue: Any) -> tuple[float | None, str | None,
                                          str | None]:
    """Parse a cue's DURATION / DURATION_MODE.

    Returns (seconds, mode, note): seconds is None for
    ACTION_DURATION (the span comes from the owning shot) and for
    absent/unparsable values (note explains; the synthesis default
    is used and the fallback is recorded)."""
    mode_raw = _cue_get(cue, "duration_mode", "DURATION_MODE",
                        default="") or ""
    mode = str(mode_raw).strip().upper() or None
    raw = _cue_get(cue, "duration", "duration_seconds", "DURATION",
                   default=None)
    if isinstance(raw, str) and raw.strip().upper() == "ACTION_DURATION":
        return None, "ACTION_DURATION", None
    if raw is None:
        return None, mode, None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw), mode, None
    match = _DURATION_RE.match(str(raw))
    if match:
        return float(match.group(1)), mode, None
    return None, mode, (f"unparsable DURATION {raw!r}; "
                        "synthesis default duration used")


def resolve_mix_gains(package: dict | None) -> dict[str, Any]:
    """Mix gains from the package's GLOBAL_AUDIO block (SPEC 5.6).

    Non-numeric values (the new dialect's prose "12–18 dB below
    speech") fall back to the SPEC default with a warning. Packages
    without a GLOBAL_AUDIO block use engine defaults: ducking is
    DUCKING_DB and no master limiter is applied (the old behaviour
    for free-form scripts)."""
    package = package or {}
    raw = package.get("v1_global_audio")
    if not isinstance(raw, dict):
        raw = package.get("global_audio")
    if not isinstance(raw, dict):
        raw = {}
    has_v1 = ("v1_global_audio" in package
              or "global_audio" in package)
    gains: dict[str, float] = {}
    warnings: list[str] = []
    for key, default in SPEC_AUDIO_DEFAULTS.items():
        value = raw.get(key)
        if value is None:
            gains[key] = default
        elif isinstance(value, bool):
            gains[key] = default
            warnings.append(f"GLOBAL_AUDIO {key}={value!r} is not a "
                            f"number; SPEC default {default} dB used")
        else:
            try:
                gains[key] = float(value)
            except (TypeError, ValueError):
                gains[key] = default
                warnings.append(
                    f"GLOBAL_AUDIO {key}={value!r} is not numeric; "
                    f"SPEC default {default} dB used")
    return {
        "bus_gains": gains,
        "ducking_db": gains["bgm_ducking_db"] if has_v1 else DUCKING_DB,
        "master_limit_db": gains["master_limit_db"] if has_v1 else None,
        "source": "v1_global_audio" if has_v1 else "engine_defaults",
        "warnings": warnings,
    }


def _bus_offset(gains: dict[str, Any], bus: str) -> float:
    """How far this script's bus gain sits from the SPEC default.
    The synthesis base gains already encode the default mix, so only
    the DIFFERENCE is applied — a script at SPEC defaults mixes
    exactly at the base gains."""
    key = _BUS_GAIN_KEY[bus]
    return (gains["bus_gains"][key] - SPEC_AUDIO_DEFAULTS[key])


def _trait_key(item: dict) -> tuple[Any, str, str] | None:
    name = item.get("name") or item.get("event") or ""
    cue_type = str(item.get("cue_type") or "").strip().upper()
    if not cue_type:
        cue_type = "SFX" if item.get("event") else "BGM"
    scene = item.get("scene_number", item.get("scene"))
    if scene is None or not name:
        return None
    return (scene, cue_type, _normalize_text(str(name)))


def extract_trait_audio(package: dict | None) -> dict[str, Any]:
    """Extract SPEC section 15.4 trait-block audio, if present.

    Accepts package["trait_blocks"]["audio"] as a list of events, or
    a dict with events/sfx/music lists plus unmapped_cues. Returns
    the mapped events keyed by (scene, cue_type, name) and by
    (scene, line), plus the raw unmapped list. Any timestamp keys in
    trait data are noted (planner_timestamps_ignored) and never used.
    """
    result: dict[str, Any] = {
        "present": False, "mapped": {}, "by_line": {},
        "unmapped": [], "planner_timestamps_ignored": False,
        "raw_count": 0,
    }
    trait_blocks = (package or {}).get("trait_blocks")
    if not isinstance(trait_blocks, dict) or "audio" not in trait_blocks:
        return result
    result["present"] = True
    audio = trait_blocks["audio"]
    items: list[Any] = []
    unmapped_raw: list[Any] = []
    if isinstance(audio, list):
        items = audio
    elif isinstance(audio, dict):
        for key in ("events", "sfx", "music", "audio_events"):
            value = audio.get(key)
            if isinstance(value, list):
                items.extend(value)
        raw_unmapped = audio.get("unmapped_cues")
        if isinstance(raw_unmapped, list):
            unmapped_raw.extend(raw_unmapped)
    top_unmapped = trait_blocks.get("unmapped_cues")
    if isinstance(top_unmapped, list):
        unmapped_raw.extend(top_unmapped)
    for item in items:
        if not isinstance(item, dict):
            continue
        result["raw_count"] += 1
        if any(k in item for k in _TIME_KEYS):
            result["planner_timestamps_ignored"] = True
        key = _trait_key(item)
        if key is not None:
            result["mapped"][key] = item
        scene = item.get("scene_number", item.get("scene"))
        line = item.get("line")
        if scene is not None and line is not None:
            result["by_line"][(scene, line)] = item
    result["unmapped"] = unmapped_raw
    return result


def _trait_unmapped_match(cue_key: tuple[Any, str, str] | None,
                          cue_name_norm: str,
                          unmapped_raw: list[Any]) -> bool:
    for entry in unmapped_raw:
        if isinstance(entry, str):
            if _normalize_text(entry) == cue_name_norm:
                return True
        elif isinstance(entry, dict):
            if _trait_key(entry) == cue_key:
                return True
            entry_name = entry.get("name") or entry.get("event") or ""
            if (entry_name and _normalize_text(str(entry_name))
                    == cue_name_norm
                    and entry.get("scene_number",
                                  entry.get("scene")) in
                    (None, cue_key[0] if cue_key else None)):
                return True
    return False


def scene_none_flags(package: dict | None) -> dict[Any, dict[str, bool]]:
    """Explicit NONE flags per scene (SPEC section 10.2).

    PRIMARY source: scene["v1_scene"]["sfx_none" / "ambience_none" /
    "bgm_none" / "meme_none"] booleans, emitted by the parser and
    preserved verbatim by the adapter. Fallbacks: the same keys on
    the package scene itself, SCREAMING variants, and "NONE" string
    values on SFX/AMBIENCE/BGM/MEME keys. Absent flags mean "nothing
    scripted", not NONE — both produce no sound, but only explicit
    NONE is reported as a prohibition (it also forbids pipeline
    defaults such as the rain bed inside that scene).

    NOTE (new dialect): the parser collapses shot-level NONE lines
    to this scene flag and emits no per-shot flag, so a True flag
    coexisting with real cues of the same kind means shot-scoped
    NONE, not scene-wide NONE. resolve_v1_cues applies that
    coexistence rule; this function returns the raw flags."""
    flags: dict[Any, dict[str, bool]] = {}

    def _flag(scene: dict, v1_scene: dict, *keys: str) -> bool:
        for source in (v1_scene, scene):
            for key in keys:
                value = source.get(key)
                if isinstance(value, bool) and value:
                    return True
                if (isinstance(value, str)
                        and value.strip().upper() == "NONE"):
                    return True
        none_dict = v1_scene.get("none")
        if isinstance(none_dict, dict):
            for key in keys:
                if none_dict.get(key) is True:
                    return True
        return False

    for scene in (package or {}).get("scenes", []) or []:
        if not isinstance(scene, dict):
            continue
        number = scene.get("number")
        if number is None:
            continue
        v1_scene = scene.get("v1_scene")
        if not isinstance(v1_scene, dict):
            v1_scene = {}
        flags[number] = {
            "sfx": _flag(scene, v1_scene, "sfx_none", "SFX_NONE", "SFX"),
            "ambience": _flag(scene, v1_scene, "ambience_none",
                              "AMBIENCE_NONE", "AMBIENCE"),
            "bgm": _flag(scene, v1_scene, "bgm_none", "BGM_NONE",
                         "BGM", "MUSIC"),
            "meme": _flag(scene, v1_scene, "meme_none", "MEME_NONE",
                          "MEME"),
        }
    return flags


def shot_none_flags(package: dict | None) -> dict[str, dict[str, bool]]:
    """Shot-level NONE flags (new dialect: ``SFX: NONE`` inside a
    SHOT block), keyed by V1 shot id. Sources: boolean *_none keys
    or "NONE" strings on the v1_scene shot entries, in dict or
    nested ``audio`` form."""
    flags: dict[str, dict[str, bool]] = {}
    for scene in (package or {}).get("scenes", []) or []:
        if not isinstance(scene, dict):
            continue
        v1_scene = scene.get("v1_scene")
        if not isinstance(v1_scene, dict):
            continue
        for entry in v1_scene.get("shots", []) or []:
            if not isinstance(entry, dict):
                continue
            shot_id = entry.get("id") or entry.get("shot_id")
            if not shot_id:
                continue
            audio = entry.get("audio")
            if not isinstance(audio, dict):
                audio = {}
            def _is_none(*keys: str) -> bool:
                for source in (entry, audio):
                    for key in keys:
                        value = source.get(key)
                        if value is True:
                            return True
                        if (isinstance(value, str)
                                and value.strip().upper() == "NONE"):
                            return True
                return False
            flags[str(shot_id)] = {
                "sfx": _is_none("sfx_none", "SFX_NONE", "SFX"),
                "ambience": _is_none("ambience_none", "AMBIENCE_NONE",
                                     "AMBIENCE"),
                "bgm": _is_none("bgm_none", "BGM_NONE", "BGM", "MUSIC"),
                "meme": _is_none("meme_none", "MEME_NONE", "MEME"),
            }
    return flags


def v1_shot_index(package: dict | None) -> dict[str, dict]:
    """V1 SHOT entries keyed by shot id (for owning-shot anchoring
    and shot-trigger LINE_ID linkage)."""
    index: dict[str, dict] = {}
    for scene in (package or {}).get("scenes", []) or []:
        if not isinstance(scene, dict):
            continue
        v1_scene = scene.get("v1_scene")
        if not isinstance(v1_scene, dict):
            continue
        for entry in v1_scene.get("shots", []) or []:
            if not isinstance(entry, dict):
                continue
            shot_id = entry.get("id") or entry.get("shot_id")
            if shot_id:
                index[str(shot_id)] = entry
    return index


def line_id_map(package: dict | None) -> dict[str, int]:
    """LINE_ID -> global 1-based line ordinal, in document order
    (the same order the TTS stage flattens lines into timeline
    entries, so ordinal N is timeline_entries[N-1])."""
    mapping: dict[str, int] = {}
    ordinal = 0
    for scene in (package or {}).get("scenes", []) or []:
        if not isinstance(scene, dict):
            continue
        v1_scene = scene.get("v1_scene")
        lines: list[Any] = []
        if isinstance(v1_scene, dict):
            lines = v1_scene.get("spoken_lines", []) or []
        for spoken in lines:
            if not isinstance(spoken, dict):
                continue
            line_id = spoken.get("line_id")
            if not line_id:
                continue
            ordinal += 1
            mapping.setdefault(str(line_id), ordinal)
    return mapping


def build_shot_clock(shots: list[dict] | None) -> dict[str, Any]:
    """The measured shot clock: walk the re-timed shots in order,
    accumulating durations. This reproduces stage 8's clock exactly
    (action shots advance the clock; line shots start at the clock
    and advance it by their full duration including the pause beat).
    Returns shot spans, scene spans and line-start times. No planner
    or estimated time enters here: shot durations are the measured
    ones from the audio-timeline stage.

    End-card shots (kind "end_card") still advance the clock and
    appear in shot_spans, but they do NOT extend their scene's span:
    scene-level beds must end before the card, which carries BGM:
    NONE + SFX: NONE (silence under the card by construction; the
    mix pads to the total length)."""
    spans: list[dict[str, Any]] = []
    scene_spans: dict[Any, tuple[float, float]] = {}
    line_starts: dict[Any, float] = {}
    clock = 0.0
    for index, shot in enumerate(shots or []):
        try:
            duration = float(shot.get("duration") or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        start = round(clock, 3)
        end = round(clock + duration, 3)
        spans.append({"shot": shot, "index": index, "start": start,
                      "end": end, "duration": duration})
        scene_no = shot.get("scene")
        if scene_no is not None and shot.get("kind") != "end_card":
            if scene_no in scene_spans:
                scene_spans[scene_no] = (scene_spans[scene_no][0], end)
            else:
                scene_spans[scene_no] = (start, end)
        line_index = shot.get("line_index")
        if line_index is not None and line_index not in line_starts:
            line_starts[line_index] = start
        clock += duration
    return {"shot_spans": spans, "scene_spans": scene_spans,
            "line_starts": line_starts,
            "total_shot_sec": round(clock, 3)}


_STOPWORDS = frozenset({
    "khi", "ngay", "sau", "truoc", "va", "cua", "tren", "duoi", "vao",
    "ra", "voi", "cho", "tu", "den", "dang", "da", "se", "mot", "cai",
    "thi", "la", "o", "tai", "ve", "nhu", "ma", "roi", "nay", "do",
    "kia", "cung", "lai", "con", "chi", "moi", "neu", "de", "duoc",
    "bi", "trong", "khong", "rat", "the", "a", "an",
})


def _content_words(trigger: str) -> list[str]:
    return [w for w in _normalize_text(trigger).split()
            if w not in _STOPWORDS and len(w) >= 2]


def _overlap_count(words: list[str], text: str) -> int:
    tokens = set(_normalize_text(text).split())
    return sum(1 for w in words if w in tokens)


def _shot_matches_trigger(shot: dict, content: list[str]) -> bool:
    """Does this shot's own action text (or action cues) match the
    trigger's content words? Needs all words when the trigger has
    1-2 content words, else at least 2 — word-boundary matching on
    accent-stripped tokens."""
    if not content:
        return False
    needed = min(2, len(content))
    action_text = shot.get("action_text") or ""
    if _overlap_count(content, action_text) >= needed:
        return True
    cues = shot.get("action_cues") or shot.get("cues") or []
    return any(w in cues for w in content)


_SNAKE_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]*_[A-Z0-9_]+$")
_LINE_ID_SPLIT_RE = re.compile(r"[\s\u2014\u2013\-]+")

# Phase G: SNAKE_CASE SFX triggers -> compiled action types. A cue
# whose trigger names one of these actions anchors to the action
# event's measured contact moment instead of the owning shot's
# start. Tokens with no action verb (DOOR_*, LIGHTNING_*, ...) are
# deliberately absent: the compiler has no such verbs, so those
# cues keep the existing recorded-fallback behaviour and are never
# given an invented semantic time.
TRIGGER_ACTION_MAP = {
    "PROP_WALLET_OPEN": "OPEN_WALLET",
    "WALLET_OPEN": "OPEN_WALLET",
    "PROP_WALLET_CLOSE": "CLOSE_WALLET",
    "WALLET_CLOSE": "CLOSE_WALLET",
    "PROP_PEN_WRITE": "WRITE",
    "PEN_WRITE": "WRITE",
    "PROP_PEN_SIGN": "SIGN",
    "PEN_SIGN": "SIGN",
    "PROP_HANDOVER": "HAND_OVER",
    "HANDOVER": "HAND_OVER",
    "PROP_PICK_UP": "PICK_UP",
    "PICK_UP": "PICK_UP",
    "PROP_TAKE_OUT": "TAKE_OUT",
    "TAKE_OUT": "TAKE_OUT",
    "PROP_PUT_AWAY": "PUT_AWAY",
    "PUT_AWAY": "PUT_AWAY",
    "PROP_GRASP": "PICK_UP",
    "GRASP": "PICK_UP",
    "PROP_RELEASE": "RELEASE",
    "RELEASE": "RELEASE",
    "PROP_HOLD_PEN": "HOLD_PEN",
    "HOLD_PEN": "HOLD_PEN",
    "PROP_BEND_PICK": "BEND_PICK",
    "BEND_PICK": "BEND_PICK",
    "PROP_KNEEL_PICK": "KNEEL_PICK",
    "KNEEL_PICK": "KNEEL_PICK",
    "PROP_RECEIVE_PROP": "RECEIVE_PROP",
    "PROP_RECEIVE": "RECEIVE_PROP",
    "RECEIVE_PROP": "RECEIVE_PROP",
    "PROP_HAMMER_STRIKE": "HAMMER_STRIKE",
    "HAMMER_STRIKE": "HAMMER_STRIKE",
    "HAMMER_CONTACT": "HAMMER_STRIKE",
    "HAMMER_METAL_CONTACT": "HAMMER_STRIKE",
}


def _anchor_fraction(action_type: str) -> float:
    """Contact moment within an action event, as a fraction of its
    duration. Grasp/transfer/release fractions are the SHARED
    constants from animation/primitives.py (single source of truth
    with prop_system.py); everything else anchors at the event
    start (the motion — and its sound — begins there)."""
    from .animation.primitives import (
        HAND_OVER_TRANSFER_U,
        KNEEL_PICK_GRASP_U,
        PICK_UP_GRASP_U,
        PUT_AWAY_RELEASE_U,
        RECEIVE_REACH_U,
    )
    if action_type in ("PICK_UP", "TAKE_OUT", "HOLD"):
        return float(PICK_UP_GRASP_U)
    if action_type in ("BEND_PICK", "KNEEL_PICK"):
        # Ground pickups grasp at the kneel fraction (shared with
        # the prop state machine), not the standing pick-up
        # fraction: the hand arrives with the kneel, later in the
        # event.
        return float(KNEEL_PICK_GRASP_U)
    if action_type == "RECEIVE_PROP":
        return float(RECEIVE_REACH_U)
    if action_type == "HOLD_PEN":
        return 0.40  # matches the HOLD_PEN grasp in prop_system.py
    if action_type in ("PUT_AWAY", "RELEASE"):
        return float(PUT_AWAY_RELEASE_U)
    if action_type == "HAND_OVER":
        return float(HAND_OVER_TRANSFER_U)
    return 0.0


def _line_ids_from_shot_entry(entry: dict) -> list[str]:
    """LINE_IDs a V1 SHOT entry is anchored to: explicit id lists
    (spoken_line_ids, trigger_line_id), or tokens inside its
    TRIGGER field (``EP01_FP_01 — "quote"``). Only tokens
    containing a digit are considered."""
    found: list[str] = []
    for key in ("spoken_line_ids", "line_ids", "trigger_line_ids",
                "trigger_line_id", "line_id"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            found.append(value)
        elif isinstance(value, list):
            found.extend(str(v) for v in value if v)
    trigger = entry.get("trigger")
    if isinstance(trigger, str):
        for token in _LINE_ID_SPLIT_RE.split(trigger):
            token = token.strip("\"“”'()[],.")
            if token and any(c.isdigit() for c in token):
                found.append(token)
    deduped: list[str] = []
    for token in found:
        if token not in deduped:
            deduped.append(token)
    return deduped


def audio_event_to_synth_job(event: AudioEvent, gains: dict[str, Any],
                             *, total_sec: float
                             ) -> tuple[str | None, dict | None, str]:
    """Map a legacy planned AudioEvent to a synthesis job.

    Returns (kind, job, reason): kind is "segment" (foley point),
    "bed" (ambience span, for rain_start), or None when the event
    must not render (memes, unknown engine events). Bed jobs span
    from the event time to the end of the timeline ("rain starts"
    means rain continues)."""
    if event.category == "memes" or event.sfx == "CONTEXTUAL_MEME":
        return None, None, ("meme event; memes are never "
                            "auto-rendered (no catalog insertion)")
    synth_kind = ENGINE_EVENT_SYNTH.get(event.event_type)
    if synth_kind is None:
        return None, None, (f"engine event {event.event_type!r} has "
                            "no synthesis mapping — no sound invented")
    spec = SYNTHESIS_MAP[synth_kind]
    if synth_kind in BED_KINDS:
        gain = round(event.gain_db
                     + _bus_offset(gains, "ambience"), 2)
        return ("bed", {
            "stem": "ambience", "synth_kind": synth_kind,
            "start": round(event.at_seconds, 3),
            "end": round(total_sec, 3), "gain_db": gain,
            "method": spec["method"], "cue_name": event.sfx,
            "cue_id": None, "scene": event.scene,
            "shot_id": None,
            "fade_down": False, "source": "legacy_event",
        }, "")
    gain = round(event.gain_db + _bus_offset(gains, "foley"), 2)
    duration = spec["duration_default"]
    return ("segment", {
        "event_type": event.event_type,
        "at_seconds": round(event.at_seconds, 3),
        "end_seconds": round(event.at_seconds + duration, 3),
        "duration": duration, "sfx": event.sfx,
        "category": "foley", "gain_db": gain,
        "synth_kind": synth_kind, "method": spec["method"],
        "cue_name": event.sfx, "cue_id": None, "scene": event.scene,
        "shot_id": None,
        "source": "legacy_event",
    }, "")


def resolve_v1_cues(cues: list[Any] | None, *, package: dict | None,
                    shots: list[dict] | None,
                    timeline_entries: list[dict] | None,
                    rainy_scenes: Any = None,
                    script_text: str = "",
                    compiled_events: list[dict] | None = None
                    ) -> dict[str, Any]:
    """Resolve V1 audio cues against the measured timeline clock.

    TRIGGER RESOLUTION (measured times only; planner timestamps are
    ignored wherever they appear):
    * LINE_ID trigger -> that line's measured start time (via the
      LINE_ID -> ordinal map and the timeline entries' starts).
    * SNAKE_CASE event token (new dialect, e.g. PROP_WALLET_OPEN) ->
      the compiled action event's contact moment when
      ``compiled_events`` is supplied and the token names an action
      verb (Phase G semantic anchor); otherwise the owning shot's
      start: the plan shot carrying the V1 shot id, else the V1
      shot entry's LINE_ID anchor (shot TRIGGER), else the scene
      start as a RECORDED fallback.
    * Action-text trigger (old dialect) -> the start of the shot
      whose action text / cues match (word-boundary, accent
      stripped); else the scene start as a RECORDED fallback when
      at least one content word matches the scene's action text.
    * Scene-level AMBIENCE (MODE: LOOP/ONCE) and BGM -> the scene's
      start..end span from the shot clock.
    * A trigger that matches nothing, names an unknown LINE_ID, or
      is absent with no owning-shot anchor is UNRESOLVABLE: the cue
      is recorded unrendered with a V1E022 reason, never placed at
      an invented time, never silently dropped.
    * Shot starts only: intra-line offsets are unavailable (the
      shot TRIGGER quote positions inside a line are not timed);
      this is recorded as a limitation in the report.

    MAPPING: trait-block engine events win when present (SPEC 15.4);
    otherwise cue-name/TYPE keywords map to honest syntheses. A
    planner "unmapped" listing is advisory only (it means "no engine
    SFX event in the planner's vocabulary") and never vetoes
    audio-stage mapping. BGM cues always render as a
    clearly-labelled generic sine pad (never reusing SFX event
    names). MEME cues and VFX cues never render audio. Explicit
    NONE suppresses that kind only when the scene carries no real
    cues of the kind (scene-wide NONE); a scene flag coexisting
    with real cues is shot-scoped NONE collapsed to scene level by
    the parser (no per-shot flag exists in the package), so the
    cues render for their own shots and the coexistence is
    recorded. Shot-level flags suppress their own shot's cues when
    the package carries them.

    DURATION: a parsed DURATION sets the segment length;
    DURATION_MODE: ACTION_DURATION spans the owning shot; otherwise
    the synthesis default is used. INTENSITY applies the documented
    ladder (LOW -6, MODERATE/MEDIUM 0, HIGH +3 dB).

    Returns a JSON-serializable report: per-cue decisions (verbatim
    cue fields, mapping, trigger, render status, reasons), timed
    ``segments`` (foley) and ``beds`` (ambience/music) for the
    mixer (every job carries ``cue_id``/``shot_id``/``scene``
    provenance so NONE-shot attribution is auditable), unmapped/unresolved/NONE lists, scene NONE spans, and
    the resolved mix gains. ``script_text`` is accepted for the
    meme-guard context and recorded in the report header; meme
    decisions do not depend on it (memes never render here).
    """
    package = package or {}
    cues = list(cues or [])
    clock = build_shot_clock(shots)
    shot_spans = clock["shot_spans"]
    scene_spans = clock["scene_spans"]
    entry_starts: dict[Any, tuple[float, float]] = {}
    for entry in timeline_entries or []:
        line_index = entry.get("line_index")
        if line_index is not None and entry.get("start") is not None:
            try:
                entry_starts[line_index] = (
                    float(entry["start"]),
                    float(entry.get("end", entry["start"])))
            except (TypeError, ValueError):
                continue

    def _line_start(ordinal: Any) -> float | None:
        if ordinal in entry_starts:
            return entry_starts[ordinal][0]
        value = clock["line_starts"].get(ordinal)
        return float(value) if value is not None else None

    line_ids = line_id_map(package)
    none_flags = scene_none_flags(package)
    shot_none = shot_none_flags(package)
    v1_shots = v1_shot_index(package)
    traits = extract_trait_audio(package)
    gains = resolve_mix_gains(package)
    scene_action_text = {
        s.get("number"): (s.get("action_text") or "")
        for s in package.get("scenes", []) or []
        if isinstance(s, dict)}
    shots_by_scene: dict[Any, list[dict[str, Any]]] = {}
    for span in shot_spans:
        shots_by_scene.setdefault(span["shot"].get("scene"),
                                  []).append(span)
    v1_meta = package.get("v1_meta")
    meme_policy = (v1_meta.get("meme_policy")
                   if isinstance(v1_meta, dict) else None)

    def _owning_shot(shot_id: str | None) -> dict[str, Any] | None:
        """Owning shot anchor: (start, end|None, method, note)."""
        if not shot_id:
            return None
        for span in shot_spans:
            shot = span["shot"]
            if shot_id in (shot.get("v1_shot_id"), shot.get("shot_id"),
                           shot.get("id")):
                return {"start": span["start"], "end": span["end"],
                        "method": "owning_shot_start",
                        "note": "plan shot carries the V1 shot id"}
        entry = v1_shots.get(shot_id)
        if entry is not None:
            for line_id in _line_ids_from_shot_entry(entry):
                ordinal = line_ids.get(line_id) or line_ids.get(
                    line_id.upper())
                if ordinal is not None:
                    start = _line_start(ordinal)
                    if start is not None:
                        return {"start": start, "end": None,
                                "method": "owning_shot_line_anchor",
                                "note": f"V1 shot anchored to line "
                                        f"{line_id} via shot TRIGGER"}
        return None

    # Phase G semantic anchors: compiled action events indexed by
    # action type. Times come from the compiler's measured spans on
    # the same shot clock build_shot_clock reproduces, so an event
    # time is directly comparable to shot/line times.
    _events_by_type: dict[str, list[dict[str, Any]]] = {}
    for _ev in compiled_events or []:
        if not isinstance(_ev, dict):
            continue
        _atype = _ev.get("action_type")
        try:
            _start = float(_ev.get("start_time"))
            _end = float(_ev.get("end_time"))
        except (TypeError, ValueError):
            continue
        if _atype and _end >= _start:
            _events_by_type.setdefault(str(_atype), []).append(_ev)

    def _semantic_anchor(trigger: str, shot_id: str | None,
                         scene_no: Any) -> dict[str, Any] | None:
        """SNAKE_CASE trigger -> compiled action event contact
        moment, or None when the token names no action verb or no
        event of that type exists in the cue's shot/scene (the
        caller then falls through to the existing shot/scene
        behaviour — never an invented time)."""
        action_type = TRIGGER_ACTION_MAP.get(trigger)
        if action_type is None:
            return None
        candidates = _events_by_type.get(action_type, [])
        if not candidates:
            return None
        scene_prefix = None
        if shot_id:
            for ev in candidates:
                if str(ev.get("action_id", "")).startswith(
                        str(shot_id) + "_"):
                    chosen = ev
                    break
            else:
                chosen = None
            if chosen is None:
                scene_prefix = str(shot_id).rsplit("_", 1)[0] + "_"
        else:
            chosen = None
        if chosen is None and scene_prefix:
            for ev in candidates:
                if str(ev.get("action_id", "")).startswith(
                        scene_prefix):
                    chosen = ev
                    break
        if chosen is None:
            return None
        start = float(chosen["start_time"])
        end = float(chosen["end_time"])
        if action_type == "HAMMER_STRIKE":
            # One SFX hit per strike: the event renders N strike
            # cycles, and the sound must hit at every contact, not
            # once at the event start. The cycle count is the
            # primitive's own default (hammer_cycles), so audio
            # and animation agree on the strike moments.
            from .animation.primitives import (
                hammer_cycles, hammer_strike_times)
            cycles = hammer_cycles(end - start)
            strikes = [round(start + t, 3) for t in hammer_strike_times(
                end - start, cycles)]
            return {"status": "resolved", "method": "action_event",
                    "start": strikes[0], "anchor_end": round(end, 3),
                    "anchor_event_id": str(chosen.get("action_id")),
                    "strike_times": strikes,
                    "note": f"TRIGGER {trigger} -> "
                            f"{chosen.get('action_id')} "
                            f"(HAMMER_STRIKE) {cycles} strike(s) at "
                            f"{strikes} within {start:.2f}-{end:.2f}s"}
        frac = _anchor_fraction(action_type)
        at = start + frac * (end - start)
        return {"status": "resolved", "method": "action_event",
                "start": round(at, 3), "anchor_end": round(end, 3),
                "anchor_event_id": str(chosen.get("action_id")),
                "note": f"TRIGGER {trigger} -> {chosen.get('action_id')} "
                        f"({action_type}) contact moment "
                        f"u={frac} within {start:.2f}-{end:.2f}s"}

    def _resolve_sfx_trigger(trigger: str, scene_no: Any,
                             shot_id: str | None,
                             structured: bool) -> dict[str, Any]:
        # 1. LINE_ID (exact, or the first token of a longer trigger).
        if trigger:
            first = _LINE_ID_SPLIT_RE.split(trigger, maxsplit=1)[0]
            for candidate in (trigger, first):
                ordinal = line_ids.get(candidate) or line_ids.get(
                    candidate.upper())
                if ordinal is not None:
                    start = _line_start(ordinal)
                    if start is not None:
                        return {"status": "resolved",
                                "method": "line_id", "start": start,
                                "anchor_end": None,
                                "note": f"LINE_ID {candidate} -> "
                                        f"line {ordinal} start"}
                    return {"status": "unresolved", "method": None,
                            "start": None, "anchor_end": None,
                            "reason": f"LINE_ID {candidate} has no "
                                      "measured start time (V1E022)"}
        # 2. SNAKE_CASE event token -> semantic action anchor, else
        # owning shot start.
        if trigger and _SNAKE_TOKEN_RE.fullmatch(trigger):
            anchor = _semantic_anchor(trigger, shot_id, scene_no)
            if anchor is not None:
                return anchor
            own = _owning_shot(shot_id)
            if own is not None:
                return {"status": "resolved", "method": own["method"],
                        "start": own["start"],
                        "anchor_end": own["end"], "note": own["note"]}
            span = scene_spans.get(scene_no)
            if span is not None:
                return {"status": "fallback",
                        "method": "scene_start_fallback",
                        "start": span[0], "anchor_end": None,
                        "note": f"owning shot {shot_id} not locatable "
                                "in the shot clock; scene start used "
                                "(recorded fallback)"}
            return {"status": "unresolved", "method": None,
                    "start": None, "anchor_end": None,
                    "reason": f"event trigger {trigger} has no "
                              f"locatable owning shot and scene "
                              f"{scene_no} has no span (V1E022)"}
        # 3. Action-text trigger -> matching shot, else scene start.
        if trigger:
            content = _content_words(trigger)
            if content:
                for span in shots_by_scene.get(scene_no, []):
                    if _shot_matches_trigger(span["shot"], content):
                        return {"status": "resolved",
                                "method": "action_text_shot",
                                "start": span["start"],
                                "anchor_end": span["end"],
                                "note": "trigger words match the "
                                        "shot's action text"}
                combined = scene_action_text.get(scene_no, "") + " " + \
                    " ".join(str(sp["shot"].get("action_text") or "")
                            for sp in shots_by_scene.get(scene_no, []))
                if _overlap_count(content, combined) >= 1:
                    span = scene_spans.get(scene_no)
                    if span is not None:
                        return {"status": "fallback",
                                "method": "scene_start_fallback",
                                "start": span[0], "anchor_end": None,
                                "note": "trigger words match the "
                                        "scene action text but no "
                                        "single shot; scene start "
                                        "used (recorded fallback)"}
            return {"status": "unresolved", "method": None,
                    "start": None, "anchor_end": None,
                    "reason": f"action-text trigger {trigger!r} "
                              f"matches nothing in scene {scene_no} "
                              "action text (V1E022)"}
        # 4. Empty trigger: structured cues may anchor to the shot.
        if structured and shot_id:
            own = _owning_shot(shot_id)
            if own is not None:
                return {"status": "resolved", "method": own["method"],
                        "start": own["start"],
                        "anchor_end": own["end"],
                        "note": "no TRIGGER; anchored to the owning "
                                "shot (structured cue)"}
        return {"status": "unresolved", "method": None, "start": None,
                "anchor_end": None,
                "reason": "no TRIGGER and no owning-shot anchor "
                          "(V1E022)"}

    reports: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    beds: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    none_suppressed: list[dict[str, Any]] = []
    warnings: list[str] = list(gains["warnings"])
    if traits["planner_timestamps_ignored"]:
        warnings.append("trait_blocks audio carried planner "
                        "timestamps; all were ignored and times "
                        "recomputed from the measured clock")
    seen_segments: set[tuple[str, float]] = set()
    seen_beds: set[tuple[str, str, Any, float, float]] = set()
    counts: dict[str, dict[str, int]] = {}

    # Kinds actually cued per scene. The parser collapses shot-level
    # NONE lines to the scene flag (no per-shot flag exists in the
    # package), so a scene flag coexisting with real cues of that
    # kind means shot-scoped NONE: the cues render for their own
    # shots, and the NONE shots simply contribute no cues. Only a
    # flag with NO cues of that kind in the scene is scene-wide
    # (and only then does it yield a NONE span). Valid old-dialect
    # scripts never have both (V1E024), so this changes nothing
    # for them.
    _KIND_BY_TYPE = {"SFX": "sfx", "AMBIENCE": "ambience",
                     "BGM": "bgm", "MUSIC": "bgm", "MEME": "meme"}
    kinds_per_scene: dict[Any, set[str]] = {}
    for _precue in cues:
        _ct = str(_cue_get(_precue, "cue_type", default="") or ""
                  ).strip().upper()
        if not _ct:
            _structured = (
                _cue_get(_precue, "cue_id", default=None) is not None
                or _cue_get(_precue, "event", default=None) is not None)
            _ct = "SFX" if (_structured or _cue_get(
                _precue, "name", default="")) else ""
        _kk = _KIND_BY_TYPE.get(_ct)
        _sc = _cue_get(_precue, "scene_number", "scene", default=None)
        try:
            _sc = int(_sc) if _sc is not None else None
        except (TypeError, ValueError):
            _sc = None
        if _kk is not None and _sc is not None:
            kinds_per_scene.setdefault(_sc, set()).add(_kk)
    coexistence_warned: set[tuple[Any, str]] = set()

    for cue in cues:
        verbatim, had_time = _verbatim_cue(cue)
        if had_time:
            warnings.append("cue carried a planner timestamp key; "
                            "ignored, time recomputed from the clock")
        cue_type = str(_cue_get(cue, "cue_type", default="") or ""
                       ).strip().upper()
        name = str(_cue_get(cue, "name", "event", default="") or "")
        type_text = str(_cue_get(cue, "cue_type_text", "type",
                                 "type_text", "sfx_type",
                                 default="") or "")
        trigger = str(_cue_get(cue, "trigger", default="") or ""
                      ).strip()
        scene_raw = _cue_get(cue, "scene_number", "scene", default=None)
        try:
            scene_no = int(scene_raw) if scene_raw is not None else None
        except (TypeError, ValueError):
            scene_no = None
        shot_id_raw = _cue_get(cue, "shot_id", "shot", "shot_ref",
                               default=None)
        shot_id = str(shot_id_raw) if shot_id_raw else None
        cue_id_raw = _cue_get(cue, "cue_id", "id", default=None)
        cue_id = str(cue_id_raw) if cue_id_raw else None
        structured = (
            cue_id is not None
            or _cue_get(cue, "event", default=None) is not None
            or _cue_get(cue, "duration_mode", "DURATION_MODE",
                        default=None) is not None
            or _cue_get(cue, "duration", "duration_seconds",
                        default=None) is not None)
        if not cue_type:
            cue_type = "SFX" if (structured or name) else ""
        kind_key = {"SFX": "sfx", "AMBIENCE": "ambience",
                    "BGM": "bgm", "MUSIC": "bgm",
                    "MEME": "meme"}.get(cue_type)
        report: dict[str, Any] = {
            "cue": verbatim, "cue_type": cue_type, "name": name,
            "scene_number": scene_no, "shot_id": shot_id,
            "cue_id": cue_id, "mapping": None, "trigger": None,
            "render": "unrendered", "reasons": [],
        }
        counts.setdefault(cue_type or "UNKNOWN",
                          {"total": 0, "rendered": 0, "unrendered": 0})
        counts[cue_type or "UNKNOWN"]["total"] += 1
        # Notes that ride on every outcome of this cue (e.g. the
        # NONE-coexistence note below).
        prefix_notes: list[str] = []

        def _finish(status: str, reasons: list[str]) -> None:
            report["render"] = status
            report["reasons"] = prefix_notes + reasons
            counts[cue_type or "UNKNOWN"][status] += 1
            reports.append(report)

        if cue_type == "VFX":
            _finish("unrendered",
                    ["VFX cue — visual effect, no audio rendering"])
            continue
        if kind_key is None:
            _finish("unrendered",
                    [f"unknown cue_type {cue_type!r} — no audio "
                     "mapping; cue preserved, nothing invented"])
            continue
        # Explicit NONE (scene level, then shot level for SFX). A
        # scene flag suppresses a cue only when the scene carries NO
        # real cues of that kind; when real cues coexist, the flag
        # is shot-scoped NONE collapsed to scene level (see
        # kinds_per_scene above) and the cues render.
        scene_flags = none_flags.get(scene_no, {}) \
            if scene_no is not None else {}
        if scene_flags.get(kind_key):
            if kind_key not in kinds_per_scene.get(scene_no, set()):
                reason = (f"scene {scene_no} declares {cue_type}: "
                          "NONE — explicit prohibition, no sound of "
                          "this kind")
                report["mapping"] = {"status": "suppressed",
                                     "reason": reason}
                none_suppressed.append({"cue": verbatim,
                                        "reason": reason})
                _finish("unrendered", [reason])
                continue
            note = (f"scene {scene_no} {cue_type}: NONE flag coexists "
                    "with real cues (shot-scoped NONE collapsed to "
                    "scene level by the parser); cue renders for its "
                    "own shot")
            prefix_notes.append(note)
            if (scene_no, kind_key) not in coexistence_warned:
                coexistence_warned.add((scene_no, kind_key))
                warnings.append(note)
        if (kind_key == "sfx" and shot_id
                and shot_none.get(shot_id, {}).get("sfx")):
            reason = (f"shot {shot_id} declares SFX: NONE — explicit "
                      "prohibition for this shot")
            report["mapping"] = {"status": "suppressed",
                                 "reason": reason}
            none_suppressed.append({"cue": verbatim, "reason": reason})
            _finish("unrendered", [reason])
            continue
        # Memes are never auto-rendered (existing guards stay).
        if cue_type == "MEME":
            reason = ("meme cue — never auto-rendered in this "
                      "pipeline (no catalog insertion; MEME_NOTE "
                      "cues are data only)")
            report["mapping"] = {"status": "never_rendered",
                                 "reason": reason}
            _finish("unrendered", [reason])
            continue

        # ---- mapping ---------------------------------------------
        intensity_raw = _cue_get(cue, "intensity", "INTENSITY",
                                 default=None)
        intensity_raw = str(intensity_raw) if intensity_raw else ""
        trait_item = None
        # Advisory only: the planner's unmapped list means "no
        # engine SFX event in the planner's vocabulary" — it is NOT
        # a verdict on renderability (the audio stage's own keyword
        # + synthesis mapping is broader, and ambience cues are
        # explicitly owned by the ambience bus). A listing never
        # vetoes audio-stage mapping; it is recorded as a note.
        trait_listed_unmapped = False
        cue_key = (scene_no, cue_type, _normalize_text(name)) \
            if scene_no is not None and name else None
        if traits["present"] and cue_key is not None:
            trait_item = traits["mapped"].get(cue_key)
            if trait_item is None:
                line_no = _cue_get(cue, "line", default=None)
                if line_no is not None:
                    trait_item = traits["by_line"].get(
                        (scene_no, line_no))
            trait_listed_unmapped = _trait_unmapped_match(
                cue_key, _normalize_text(name), traits["unmapped"])
        mapping: dict[str, Any] = {"status": "unmapped", "parts": [],
                                   "unmapped_parts": [],
                                   "source": None}
        if kind_key == "bgm":
            mapping = {"status": "mapped",
                       "source": ("trait_blocks" if trait_item
                                  is not None else "bgm_pad"),
                       "parts": [{"synth_kind": "music_pad",
                                  "engine_event": None,
                                  "part_text": name}],
                       "unmapped_parts": []}
        elif trait_item is not None and trait_item.get("event"):
            engine_event = str(trait_item["event"])
            if engine_event == "character_reaction":
                mapping["status"] = "unmapped"
                mapping["source"] = "trait_blocks"
                mapping["reason"] = ("trait maps to "
                                     "character_reaction (meme); "
                                     "memes are never auto-rendered")
            elif engine_event in ENGINE_EVENT_SYNTH:
                mapping = {"status": "mapped",
                           "source": "trait_blocks",
                           "parts": [{"synth_kind":
                                      ENGINE_EVENT_SYNTH[engine_event],
                                      "engine_event": engine_event,
                                      "part_text": name}],
                           "unmapped_parts": []}
            else:
                mapping["status"] = "unmapped"
                mapping["source"] = "trait_blocks"
                mapping["reason"] = (f"trait engine event "
                                     f"{engine_event!r} has no "
                                     "synthesis mapping")
        else:
            match_text = (name + " " + type_text).strip()
            parts = _split_compound(match_text)
            mapped_parts: list[dict[str, Any]] = []
            unmapped_parts: list[str] = []
            for part in parts:
                hit = _match_part(part)
                if hit is None:
                    unmapped_parts.append(part)
                else:
                    mapped_parts.append(
                        {"synth_kind": hit[0],
                         "engine_event": hit[1], "part_text": part})
            if mapped_parts:
                mapping = {"status": "mapped", "source": "keyword",
                           "parts": mapped_parts,
                           "unmapped_parts": unmapped_parts}
                if unmapped_parts:
                    mapping["partial"] = True
            else:
                mapping["status"] = "unmapped"
                mapping["source"] = "keyword"
                mapping["unmapped_parts"] = unmapped_parts
                mapping["reason"] = (
                    "no honest synthesis mapping for cue name/TYPE "
                    f"{match_text!r} — recorded unmapped, no "
                    "substitute sound")
        report["mapping"] = mapping

        # ---- timing ----------------------------------------------
        if kind_key in ("ambience", "bgm"):
            span = scene_spans.get(scene_no)
            if span is None:
                timing: dict[str, Any] = {
                    "status": "unresolved", "method": None,
                    "start": None, "end": None,
                    "reason": f"scene {scene_no} has no span in the "
                              "shot clock (V1E022)"}
            else:
                timing = {"status": "resolved", "method": "scene_span",
                          "start": span[0], "end": span[1],
                          "note": "scene-level cue spans the scene"}
        else:
            timing = _resolve_sfx_trigger(trigger, scene_no, shot_id,
                                          structured)
            timing.setdefault("end", None)
        report["trigger"] = timing

        # ---- render decision -------------------------------------
        reasons: list[str] = []
        if trait_listed_unmapped:
            if mapping["status"] == "mapped":
                reasons.append("planner trait data lists this cue "
                               "as unmapped (no engine SFX event "
                               "mapping); audio-stage mapping applied "
                               "instead")
            else:
                reasons.append("planner trait data also lists this "
                               "cue as unmapped (no engine SFX event "
                               "mapping); audio-stage mapping found "
                               "nothing either")
        if mapping["status"] != "mapped":
            reasons.append(mapping.get(
                "reason", "cue is unmapped"))
            unmapped.append({"cue": verbatim,
                             "reason": mapping.get("reason", "")})
        if timing["status"] == "unresolved":
            reasons.append(timing.get("reason", "unresolvable "
                                      "trigger (V1E022)"))
            unresolved.append({"cue": verbatim,
                               "reason": timing.get("reason", "")})
        if timing["status"] == "fallback":
            reasons.append("recorded fallback: " + timing.get(
                "note", "scene start used"))
        if mapping.get("partial"):
            reasons.append("partial mapping: unrendered parts: "
                           + "; ".join(mapping["unmapped_parts"]))
        if mapping["status"] != "mapped" \
                or timing["status"] == "unresolved":
            _finish("unrendered", reasons)
            continue

        # ---- build mixer jobs ------------------------------------
        # dedupe_covered: every job this cue would produce already
        # exists in the mix (identical event, or the global rain
        # bed). The sound IS present, so the cue counts as rendered
        # with a note — not as unrendered.
        produced = 0
        dedupe_covered = False
        if kind_key == "bgm":
            spec = SYNTHESIS_MAP["music_pad"]
            name_norm = _normalize_text(name)
            fade_down = ("fade down" in name_norm
                         or "fade to" in name_norm
                         or "near silence" in name_norm)
            extra = -6.0 if ("very low" in name_norm
                             or "near silence" in name_norm) else 0.0
            gain = round(spec["base_gain_db"]
                         + _bus_offset(gains, "bgm")
                         + intensity_offset(intensity_raw) + extra, 2)
            bed_key = ("music", "music_pad", scene_no,
                       round(timing["start"], 1),
                       round(timing["end"], 1))
            if bed_key in seen_beds:
                dedupe_covered = True
            else:
                seen_beds.add(bed_key)
                beds.append({
                    "stem": "music", "synth_kind": "music_pad",
                    "start": timing["start"], "end": timing["end"],
                    "gain_db": gain, "method": spec["method"],
                    "cue_name": name, "cue_id": cue_id,
                    "scene": scene_no, "shot_id": shot_id,
                    "fade_down": fade_down,
                    "source": mapping["source"]})
                produced += 1
        elif kind_key == "ambience":
            for part in mapping["parts"]:
                kind = part["synth_kind"]
                if kind == "footstep":
                    # Footsteps inside an ambience line are a soft
                    # collective bed over the scene, not point events.
                    kind = "march_bed"
                if kind not in _AMBIENCE_SPAN_KINDS:
                    reasons.append(
                        f"part {part['part_text']!r} maps to point "
                        f"sound {kind}, which cannot fill an ambience "
                        "span — part not rendered")
                    continue
                if (scene_no in (rainy_scenes or ())
                        and kind == "rain_bed"):
                    reasons.append("rain bed deduped against the "
                                   "scene rain bed (not doubled)")
                    dedupe_covered = True
                    continue
                spec = SYNTHESIS_MAP[kind]
                gain = round(spec["base_gain_db"]
                             + _bus_offset(gains, "ambience")
                             + intensity_offset(intensity_raw), 2)
                bed_key = ("ambience", kind, scene_no,
                           round(timing["start"], 1),
                           round(timing["end"], 1))
                if bed_key in seen_beds:
                    dedupe_covered = True
                    continue
                seen_beds.add(bed_key)
                beds.append({
                    "stem": "ambience", "synth_kind": kind,
                    "start": timing["start"], "end": timing["end"],
                    "gain_db": gain, "method": spec["method"],
                    "cue_name": name, "cue_id": cue_id,
                    "scene": scene_no, "shot_id": shot_id,
                    "fade_down": False,
                    "source": mapping["source"]})
                produced += 1
        else:  # SFX
            dur_raw, dur_mode, dur_note = parse_cue_duration(cue)
            if dur_note:
                reasons.append(dur_note)
            # A hammer anchor carries every strike time: one
            # segment per strike (the dedupe key keeps strikes
            # distinct). Every other anchor is a single start.
            starts = timing.get("strike_times") or [timing["start"]]
            for start in starts:
                for part in mapping["parts"]:
                    kind = part["synth_kind"]
                    engine_event = part["engine_event"]
                    spec = SYNTHESIS_MAP[kind]
                    if kind in BED_KINDS:
                        if (scene_no in (rainy_scenes or ())
                                and kind == "rain_bed"):
                            reasons.append(
                                "rain bed deduped against the "
                                "scene rain bed (not doubled)")
                            dedupe_covered = True
                            continue
                        span = scene_spans.get(scene_no)
                        end = span[1] if span is not None else \
                            start + spec["duration_default"]
                        gain = round(
                            spec["base_gain_db"]
                            + _bus_offset(gains, "ambience")
                            + intensity_offset(intensity_raw), 2)
                        bed_key = ("ambience", kind, scene_no,
                                   round(start, 1), round(end, 1))
                        if bed_key in seen_beds:
                            dedupe_covered = True
                            continue
                        seen_beds.add(bed_key)
                        beds.append({
                            "stem": "ambience", "synth_kind": kind,
                            "start": start, "end": end, "gain_db": gain,
                            "method": spec["method"], "cue_name": name,
                            "cue_id": cue_id, "scene": scene_no,
                            "shot_id": shot_id, "fade_down": False,
                            "source": mapping["source"]})
                        produced += 1
                        continue
                    if dur_mode == "ACTION_DURATION":
                        anchor_end = timing.get("anchor_end")
                        if anchor_end is not None and anchor_end > start:
                            duration = round(anchor_end - start, 3)
                        else:
                            duration = spec["duration_default"]
                            reasons.append(
                                "DURATION_MODE: ACTION_DURATION without "
                                "a locatable owning shot; synthesis "
                                "default duration used")
                    elif dur_raw is not None:
                        duration = max(0.05, dur_raw)
                    else:
                        duration = spec["duration_default"]
                    if engine_event is not None:
                        base_gain = EVENT_SFX_MAP[engine_event]["gain_db"]
                    else:
                        base_gain = spec["base_gain_db"]
                    gain = round(base_gain + _bus_offset(gains, "sfx")
                                 + intensity_offset(intensity_raw), 2)
                    seg_key = (kind, round(start, 1))
                    if seg_key in seen_segments:
                        dedupe_covered = True
                        continue
                    seen_segments.add(seg_key)
                    sfx_label = (EVENT_SFX_MAP[engine_event]["sfx"]
                                 if engine_event is not None
                                 else kind.upper())
                    segments.append({
                        "event_type": engine_event or kind,
                        "at_seconds": round(start, 3),
                        "end_seconds": round(start + duration, 3),
                        "duration": round(duration, 3),
                        "sfx": sfx_label, "category": "foley",
                        "gain_db": gain, "synth_kind": kind,
                        "method": spec["method"], "cue_name": name,
                        "cue_id": cue_id, "scene": scene_no,
                        "shot_id": shot_id,
                        "anchor_method": timing.get("method"),
                        "anchor_event_id": timing.get("anchor_event_id"),
                        "source": ("v1_cue+trait"
                                   if mapping["source"] == "trait_blocks"
                                   else "v1_cue")})
                    produced += 1
        if produced == 0 and not dedupe_covered:
            reasons.append("no mixer job produced")
            _finish("unrendered", reasons)
            continue
        if produced == 0 and dedupe_covered:
            reasons.append("covered by an identical sound already "
                           "in the mix (deduplicated, not doubled)")
        if timing["status"] == "fallback":
            reasons.append("rendered at a recorded fallback time "
                           "(see trigger note)")
        _finish("rendered", reasons)

    none_spans: dict[str, list[list[float]]] = {"sfx": [], "ambience": [],
                                                "bgm": [], "meme": []}
    for _scene_no, _flags in none_flags.items():
        _span = scene_spans.get(_scene_no)
        if _span is None:
            continue
        for _kind_key in none_spans:
            # Scene-wide only: a flag coexisting with real cues of
            # the kind is shot-scoped (see kinds_per_scene above)
            # and must not mute the cued sounds.
            if _flags.get(_kind_key) and _kind_key not in \
                    kinds_per_scene.get(_scene_no, set()):
                none_spans[_kind_key].append([_span[0], _span[1]])

    # End-card silence (Stage 3 integration): the card declares
    # BGM: NONE + SFX: NONE and the shot clock already excludes
    # end-card shots from scene spans — but full-length beds (the
    # rain bed) are placed at 0.0 over the whole mix, so without an
    # explicit mute span they leak under the silent card. Mute
    # every stem under end-card shots when the card declares NONE
    # for both BGM and SFX; a card that declares music is left
    # alone.
    _end_card = package.get("v1_end_card") \
        if isinstance(package, dict) else None
    if isinstance(_end_card, dict):
        _ec_fields = _end_card.get("fields") \
            if isinstance(_end_card.get("fields"), dict) else {}
        _ec_bgm = str(_end_card.get("bgm") or _ec_fields.get("BGM")
                      or "").strip().upper()
        _ec_sfx = str(_end_card.get("sfx") or _ec_fields.get("SFX")
                      or "").strip().upper()
        if _ec_bgm == "NONE" and _ec_sfx == "NONE":
            for _span in shot_spans:
                if _span["shot"].get("kind") == "end_card":
                    for _kind_key in none_spans:
                        none_spans[_kind_key].append(
                            [_span["start"], _span["end"]])

    rendered = sum(1 for r in reports if r["render"] == "rendered")
    return {
        "source": ("v1_audio_cues+trait_blocks"
                   if traits["present"] else "v1_audio_cues"),
        "trait_blocks_present": traits["present"],
        "trait_raw_count": traits["raw_count"],
        "planner_timestamps_ignored":
            traits["planner_timestamps_ignored"],
        "meme_policy": meme_policy,
        "total_cues": len(reports),
        "rendered_cues": rendered,
        "unrendered_cues": len(reports) - rendered,
        "counts_by_type": counts,
        "cues": reports,
        "segments": segments,
        "beds": beds,
        "unmapped_cues": unmapped,
        "unresolved_triggers": unresolved,
        "none_suppressed": none_suppressed,
        "none_spans": none_spans,
        "mix_gains": gains,
        "warnings": warnings,
        "limitations": [
            "Shot starts only: intra-line offsets are unavailable; "
            "a shot TRIGGER quote inside a line anchors to the "
            "line/shot start, never to a position inside the line.",
            "Shot-level SFX: NONE suppresses V1 cues of that shot; "
            "legacy action-cue events are scene-scoped and only "
            "scene-level NONE filters them.",
        ],
        "script_text_chars": len(script_text or ""),
    }
