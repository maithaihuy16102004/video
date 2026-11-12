"""Deterministic fallback planner (shared engine).

Used ONLY when Gemini is unavailable (no GEMINI_API_KEY / pydantic on
this VM). Builds a production scene package from the REAL segmentation
(vi_script_parser + segment_script) — never from a hardcoded story.
The orchestrator records this as "fallback planner (injected)", never
as Gemini output.

Package shape (what the orchestrator's stage 5 expects):
  characters: [{name, description, voice_hint, jacket_color, height_px}]
  locations:  [setting strings, one per scene]
  scenes:     [{number, title, setting, action_text, audio_text,
                action_cues, lines: [{speaker, kind, text}]}]
  shots:      one shot per spoken line + one action lead-in shot per scene
  audio_events: [{event, scene, at_seconds (estimated)}]

Jacket colours come from a generic Vietnamese colour-word map applied
to the character description — no per-story values.
"""
from __future__ import annotations

import re

from .trait_derivation import (
    build_character_trait_block,
    build_location_trait_block,
    build_trait_blocks,
    derive_action_directives,
    derive_location_traits,
    derive_render_traits,
    map_action_cue_to_primitive,
    snapshot_hash_for_text,
)
from .vi_script_parser import parse_vi_script

COLOR_WORDS: list[tuple[str, str]] = [
    ("xanh đậm", "#1d3a5f"), ("xanh dương", "#2b5ea7"), ("xanh lá", "#2e7d4f"),
    ("màu be", "#c9b18c"), ("be", "#c9b18c"), ("nâu", "#7a4a2b"),
    ("đen", "#222222"), ("đỏ", "#b03a2e"), ("vàng", "#d9a441"),
    ("trắng", "#f3f0e8"), ("xám", "#6b7280"), ("hồng", "#d98a9e"),
]

# Estimated seconds of pure action before the line that follows it.
# Generic per-cue constants; the real timeline is rebuilt from measured
# TTS durations by the renderer, these only size the action lead-ins.
ACTION_LEAD_SECONDS: dict[str, float] = {
    "walk": 1.6, "walk_fast": 1.6, "run": 1.2, "stop": 0.6,
    "bend_pick": 1.2, "give": 1.5, "take": 1.0, "open": 0.8,
    "put_away": 1.0, "take_out": 1.0, "wave": 1.2, "turn_back": 0.8,
    "smile": 0.6, "look": 0.8, "search": 1.5, "board": 2.0,
    "sit": 0.8, "stand": 0.8, "rain": 0.0, "bus": 3.5,
}

CHARACTER_HEIGHTS = (560, 540, 560, 540)  # alternate, deterministic


def _jacket_color(description: str) -> str:
    low = description.lower()
    for word, color in COLOR_WORDS:
        if word in low:
            return color
    return "#3a4a5f"


def deterministic_planner(script_text: str) -> dict:
    """Build a scene package from a structured Vietnamese script."""
    parsed = parse_vi_script(script_text)
    characters = []
    for i, c in enumerate(parsed.characters):
        characters.append({
            "name": c["name"],
            "description": c["description"],
            "voice_hint": c["voice_hint"],
            "jacket_color": _jacket_color(c["description"]),
            "height_px": CHARACTER_HEIGHTS[i % len(CHARACTER_HEIGHTS)],
        })
    # Speakers that appear in dialogue but not in the character list
    # still get a character entry (deterministic fallback colour).
    for spoken in parsed.lines:
        if spoken.speaker != "narrator" and spoken.speaker not in {
                c["name"] for c in characters}:
            characters.append({
                "name": spoken.speaker, "description": "",
                "voice_hint": "", "jacket_color": "#3a4a5f",
                "height_px": 540,
            })
    locations = [s.setting for s in parsed.scenes]
    scenes = []
    shots = []
    audio_events = []
    clock = 0.0
    for scene in parsed.scenes:
        # Action lead: movement cues only. "bus"/"rain" are ambience, not
        # lead time — except a bus that actually ARRIVES in this scene
        # ("tiến đến", "dừng"), which needs ~4 s on screen.
        lead = sum(ACTION_LEAD_SECONDS.get(c, 0.0)
                   for c in scene.action_cues
                   if c not in ("rain", "bus"))
        if "bus" in scene.action_cues and re.search(
                r"tiến|xe buýt[^.]{0,20}dừng", scene.action_text):
            lead += ACTION_LEAD_SECONDS["bus"]
        scenes.append({
            "number": scene.number, "title": scene.title,
            "setting": scene.setting, "action_text": scene.action_text,
            "audio_text": scene.audio_text,
            "animation_reqs": scene.animation_reqs,
            "action_cues": scene.action_cues,
            "action_lead_sec": round(lead, 2),
            "lines": [{"speaker": l.speaker, "kind": l.kind, "text": l.text}
                      for l in scene.lines],
        })
        shots.append({
            "shot_id": f"S{scene.number}A", "scene": scene.number,
            "kind": "action", "speaker": None, "text": "",
            "action_cues": scene.action_cues,
            "estimated_sec": round(lead, 2),
        })
        clock += lead
        for line in scene.lines:
            shots.append({
                "shot_id": f"S{scene.number}L{len(shots)}", "scene": scene.number,
                "kind": line.kind, "speaker": line.speaker, "text": line.text,
                "action_cues": scene.action_cues,
                "estimated_sec": 4.0,
            })
            clock += 4.0
        for cue in scene.action_cues:
            audio_events.append({"event": cue, "scene": scene.number,
                                 "at_seconds": round(clock, 2)})
    package = {
        "characters": characters,
        "locations": locations,
        "scenes": scenes,
        "shots": shots,
        "audio_events": audio_events,
    }
    package["trait_blocks"] = _fallback_trait_blocks(
        script_text, characters, parsed)
    return package


def _fallback_trait_blocks(script_text: str, characters: list[dict],
                           parsed) -> dict:
    """Section 15 trait blocks, deterministic derivation only.

    Same envelope shape as the Gemini route (shape parity is
    structural: one shared builder). Audio is empty: a cue-less
    free-form script has no scripted cues, and the package's
    estimated audio_events timestamps must never be presented as
    section 15.4 events.
    """
    char_map = {" ".join(c["name"].strip().casefold().split()): c["name"]
                for c in characters}
    directives, unmapped = derive_action_directives(
        [{"text": s.action_text, "scene_number": s.number,
          "shot_id": None, "source_line": None}
         for s in parsed.scenes],
        char_map)
    # Cue-tag fallback: when a scene's action prose yields no
    # directive at all, its cue tags still map (where a primitive
    # exists); unmappable cues are reported, never substituted.
    covered_scenes = {d["scene_number"] for d in directives}
    for scene in parsed.scenes:
        if scene.number in covered_scenes:
            continue
        for cue in scene.action_cues:
            primitive = map_action_cue_to_primitive(cue)
            if primitive is None:
                unmapped.append({
                    "kind": "action_cue", "action_text": cue,
                    "scene_number": scene.number, "shot_id": None,
                    "source_line": None,
                    "reason": ("no PRIMITIVES mapping for this "
                               "action cue"),
                })
            else:
                directives.append({
                    "type": primitive, "char": None, "start": None,
                    "duration": 1.5, "scene_number": scene.number,
                    "shot_id": None, "source_line": None,
                    "action_text": cue,
                })
    blocks = []
    for char in characters:
        traits = derive_render_traits(
            char["name"], "", char["description"], "", [],
            char["voice_hint"], height_px=char["height_px"])
        traits["jacket_color"] = char["jacket_color"]
        if char["voice_hint"]:
            traits["voice_hint"] = char["voice_hint"]
        blocks.append(build_character_trait_block(
            identity_id=char["name"], name=char["name"],
            appearance=char["description"],
            voice_style=char["voice_hint"],
            render_traits=traits,
            actions=[d for d in directives
                     if d.get("char") == char["name"]]))
    location_blocks = []
    for scene in parsed.scenes:
        block = build_location_trait_block(
            location_id=f"scene_{scene.number}",
            scene_numbers=[scene.number], name=scene.setting)
        block["render_traits"] = derive_location_traits(
            inline_text=scene.setting)
        location_blocks.append(block)
    return build_trait_blocks(
        snapshot_hash=snapshot_hash_for_text(script_text),
        planner="fallback", model=None, usage=None,
        reason="deterministic local planner (no Gemini call ran)",
        characters=blocks, locations=location_blocks,
        sfx=[], music=[], unmapped_cues=[],
        actions=directives, unmapped=unmapped, dropped=[])
