"""STUDIO SCRIPT V1 -> scene-package adapter (Phase B).

ONE pipeline, two parsers: free-form scripts keep the existing
deterministic/Gemini path in gemini_planner.py; scripts in STUDIO
SCRIPT V1 format are parsed by studio_script_v1.py and mapped here
to the SAME package shape resolve_plan() returns, so product_flow.py,
plan_shots, the TTS stage and the :8788 server consume them
unchanged. The wiring is a single early return at the top of
resolve_plan() (see gemini_planner.py); this module holds all of the
mapping so the wiring stays a one-line route.

Mapping rules (all generic; nothing here names a story, a character,
or a location from any particular script):

* Speakers: the parser canonicalises narrator speech to ``"Narrator"``;
  the pipeline sentinel is lowercase ``"narrator"`` (voice selection,
  character visibility, speaker matching), so the adapter normalises
  it. CHARACTER blocks whose name is a narrator alias (the parser's
  own NARRATOR_ALIASES) are excluded from the visible cast -- a
  narrator must never be drawn standing in a scene -- and their data
  is preserved under ``v1_narrator``.
* Characters: description = ROLE + APPEARANCE (verbatim), which feeds
  the engine's generic template/body inference in map_character().
  jacket_color reuses the generic colour-word map from
  planner_fallback; height_px reuses its deterministic alternation.
  voice_hint is derived ONLY from explicit evidence in the script's
  own text (an explicit "giong nam"/"giong nu" phrase, or a
  word-boundary Vietnamese honorific in the name/role/appearance);
  otherwise it is "" and the pipeline's default voice applies. The
  raw V1 VOICE string is NEVER passed as a voice_hint: the voice
  resolvers match substrings ("nam"/"nu"), so a raw voice id could
  misfire. V1 voice/voice_style/traits/costume/costume_changes/
  head_ratio/identity_id are preserved verbatim on the entry.
* Scenes: setting = the scene's inline location text, or the resolved
  LOCATION block's name when no inline text exists. action_text joins
  the scene ACTION lines and the SHOT action lines; action_cues come
  from the SAME generic extract_action_cues() the free-form path
  uses, and are additionally filtered against the supported-cue set
  (the pipeline raises on an unknown cue, so the filter is a guard;
  anything dropped is recorded in ``v1_dropped_cues``, never silently
  discarded). action_lead_sec reuses the deterministic planner's
  formula (ACTION_LEAD_SECONDS weights, rain/bus excluded, the
  bus-arrival rule) so V1 and free-form lead-ins size identically.
* Location dict: location_keyword is derived generically from the
  location text against the renderer's landmark vocabulary (great
  wall / eiffel tower / rainy street); anything else is ``"street"``,
  which is the renderer's generic fallback -- the same default the
  free-form path gets when it emits no location dict at all. The
  TRUE location data (inline text + the full structured LOCATION
  block) is carried in ``v1_scene``/``v1_locations`` for the F5
  scene-package work; this module never claims the generic street
  IS the scripted location. time_of_day (day/night) and mood
  (warm/cold) are derived by generic word scans over the script's
  own TIME_OF_DAY/MOOD text.
* Shots: the package ``shots`` list mirrors the deterministic
  planner's shape (one action shot per scene + one per spoken line;
  plan_shots rebuilds shots and ignores this list, but the server
  preflight requires it non-empty). V1 SHOT blocks map to
  ``gemini_shots`` ONLY when their type is one plan_shots honours
  (SHOT_SCALE) and they reference real spoken lines (LINE_ID ->
  global line ordinal, the key plan_shots looks up); every other
  shot stays in the ``v1_scene`` passthrough and is noted in
  ``v1_shot_notes`` with the reason.
* Audio: ``audio_events`` is []. V1 cues carry triggers, not
  timestamps, and inventing SFX timestamps is forbidden -- the full
  cue list (SFX/AMBIENCE/BGM/MEME/VFX, verbatim, with triggers and
  priorities) is preserved in ``v1_audio_cues`` and per scene in
  ``v1_scene``. The product flow has no SFX/music channel today
  (voice + optional rain bed only); wiring cues to timestamps is
  Stage 3 work, not something this adapter fakes.
* hook/twist: first/last spoken-line text, verbatim (the same rule
  _ensure_hook_twist applies on the free-form path; the server
  preflight requires both).
* Everything else the parser produces is preserved under ``v1_*``
  keys (meta, characters, locations, props, constraints, qa,
  output, global_audio, end_card, unsupported fields) so the
  adapter discards nothing the script declared.

Refusal: a document with validation errors is refused with a
V1AdapterError listing every error with its line number and code
-- invalid scripts never reach the renderer. A document with no
spoken lines is likewise refused (nothing to narrate).

The mapping is pure and deterministic: the same document always
produces the same package (the server plans at least twice per
production -- analyze/preflight and draft -- and both must agree).
"""
from __future__ import annotations

import re

from .planner_fallback import (
    ACTION_LEAD_SECONDS,
    CHARACTER_HEIGHTS,
    _jacket_color,
)
from .studio_script_v1 import (
    NARRATOR_ALIASES,
    NARRATOR_SPEAKER,
    StudioScriptV1Document,
    detect_format,
    parse_studio_script_v1,
)
from .vi_script_parser import extract_action_cues

# Planner label for V1-routed plans. Distinct from "gemini" (a real
# Gemini call produced enrichment) and "fallback" (the free-form local
# planner): a V1 plan is a deterministic parse + this adapter, with no
# Gemini enrichment yet (SPEC section 15 is Stage 3 work).
ADAPTER_LABEL = "v1"

# Mirror of product_flow.SUPPORTED_CUES. It is duplicated (not
# imported) because product_flow imports gemini_planner, which imports
# this module -- importing product_flow here would be a cycle. A test
# asserts the two sets stay identical.
SUPPORTED_CUES = frozenset({
    "walk", "walk_fast", "run", "stop", "bend_pick", "give", "take",
    "open", "put_away", "take_out", "wave", "turn_back", "smile",
    "look", "search", "board", "sit", "stand", "rain", "bus",
})

# Mirror of product_renderer.SHOT_SCALE keys: the shot types plan_shots
# honours from gemini_shots. Duplicated for the same reason (the
# renderer is heavy and must not be imported by the parser layer); a
# test asserts the two stay identical.
HONOURED_SHOT_TYPES = frozenset({
    "establishing", "medium", "close_up",
    "reaction", "object_insert", "tracking",
})

# Word-boundary Vietnamese honorifics used ONLY to derive the
# pipeline's voice_hint ("giong nam" / "giong nu") from the script's
# own character text. Tight on purpose: bare "anh"/"nam" are NOT
# scanned (they misfire on names), and an explicit "giong nam"/"giong
# nu" phrase in VOICE_STYLE wins over everything.
_FEMALE_MARKERS = ("bà", "cô", "chị", "mẹ", "dì", "nữ", "gái")
_MALE_MARKERS = ("ông", "chàng", "cậu", "anh trai", "bác trai")

# Landmark vocabulary shared with the renderer's build_scene(). These
# are the engine's landmark libraries, not story data.
_GREAT_WALL_MARKERS = ("vạn lý trường thành", "great wall", "trường thành")
_EIFFEL_MARKERS = ("eiffel",)
_RAINY_STREET_MARKERS = ("phố mưa", "rainy street")

_NIGHT_MARKERS = ("đêm", "tối", "khuya", "nửa đêm", "ban đêm", "night")
_COLD_MARKERS = ("lạnh", "lẽo", "giá lạnh", "buốt", "u ám", "âm u", "cold")

# The deterministic planner's bus-arrival rule, reused verbatim so V1
# and free-form lead-ins behave identically.
_BUS_ARRIVAL_RE = re.compile(r"tiến|xe buýt[^.]{0,20}dừng")


class V1AdapterError(ValueError):
    """Raised when a V1 document cannot be adapted (invalid, or no
    spoken lines). Carries the parser's validation errors when the
    document itself is invalid."""

    def __init__(self, message: str, errors=None):
        super().__init__(message)
        self.errors = list(errors or [])


def _normalize_name(name: str) -> str:
    # Mirrors studio_script_v1._normalize_name exactly (casefold +
    # whitespace collapse) so narrator-alias detection agrees with
    # the parser.
    return " ".join(name.strip().casefold().split())


def _is_narrator_character(name: str) -> bool:
    return _normalize_name(name) in NARRATOR_ALIASES


def _has_word(text: str, word: str) -> bool:
    return re.search(r"\b" + re.escape(word) + r"\b", text) is not None


def _voice_hint(name: str, role: str, appearance: str,
                voice_style: str) -> str:
    """Pipeline voice_hint from the script's own character text.

    Returns exactly "giọng nam", "giọng nữ", or "" (default voice).
    Never returns the raw V1 VOICE string (see module docstring).
    """
    combined = " ".join(
        p for p in (name, role, appearance, voice_style) if p).lower()
    if "giọng nữ" in combined:
        return "giọng nữ"
    if "giọng nam" in combined:
        return "giọng nam"
    female = any(_has_word(combined, w) for w in _FEMALE_MARKERS)
    male = any(_has_word(combined, w) for w in _MALE_MARKERS)
    if female and not male:
        return "giọng nữ"
    if male and not female:
        return "giọng nam"
    return ""


def _location_keyword(scan_text: str) -> str:
    """Renderer location keyword from location text (generic).

    ``"street"`` is the renderer's generic fallback, not a claim
    about the scripted location; true location data travels in the
    ``v1_*`` keys.
    """
    low = (scan_text or "").lower()
    if any(m in low for m in _GREAT_WALL_MARKERS):
        return "great_wall"
    if any(m in low for m in _EIFFEL_MARKERS):
        return "eiffel_tower"
    if any(m in low for m in _RAINY_STREET_MARKERS):
        return "rainy_street"
    return "street"


def _time_of_day(text: str) -> str:
    low = (text or "").lower()
    return "night" if any(_has_word(low, w) for w in _NIGHT_MARKERS) else "day"


def _mood(text: str) -> str:
    low = (text or "").lower()
    return "cold" if any(_has_word(low, w) for w in _COLD_MARKERS) else "warm"


def _action_lead_sec(cues: list[str], action_text: str) -> float:
    # The deterministic planner's formula (planner_fallback.py),
    # reused so V1 lead-ins size identically to free-form ones.
    lead = sum(ACTION_LEAD_SECONDS.get(c, 0.0)
               for c in cues if c not in ("rain", "bus"))
    if "bus" in cues and _BUS_ARRIVAL_RE.search(action_text or ""):
        lead += ACTION_LEAD_SECONDS["bus"]
    return round(lead, 2)


def _resolve_location(locations: list[dict], ref: str | None) -> dict | None:
    """Resolve a scene's location_ref to a declared LOCATION block.

    Exact id match first (the parser's get_location rule), then a
    normalized id/name match for refs written as names. Returns None
    when the scene uses inline location text only.
    """
    if not ref:
        return None
    for loc in locations:
        if loc.get("id") == ref:
            return loc
    norm = _normalize_name(ref)
    for loc in locations:
        if (_normalize_name(str(loc.get("id", ""))) == norm
                or _normalize_name(str(loc.get("name", ""))) == norm):
            return loc
    return None


def adapt_document(doc: StudioScriptV1Document) -> dict:
    """Map a parsed STUDIO SCRIPT V1 document to a scene package.

    Raises V1AdapterError when the document is invalid or has no
    spoken lines. Pure and deterministic.
    """
    data = doc.to_dict()
    errors = data.get("validation_errors") or []
    if errors:
        detail = "\n".join(
            f"line {e['line']} [{e['code']}]: {e['message']}"
            for e in errors)
        raise V1AdapterError(
            "STUDIO SCRIPT V1 document is invalid; refusing to render:\n"
            + detail, errors=errors)

    scenes_data = data["scenes"]
    all_lines = [ln for sc in scenes_data for ln in sc["spoken_lines"]]
    if not all_lines:
        raise V1AdapterError(
            "STUDIO SCRIPT V1 document has no spoken lines; "
            "nothing to narrate")

    # Global 1-based line ordinals in document order -- the key
    # plan_shots uses to look up gemini_shots entries.
    line_index: dict[str, int] = {}
    for ordinal, ln in enumerate(all_lines, 1):
        line_index[ln["line_id"]] = ordinal

    # --- Characters: visible cast + preserved narrator data --------
    declared = data["characters"]
    cast: list[dict] = []
    narrator_entries: list[dict] = []
    for char in declared:
        if _is_narrator_character(char["name"]):
            narrator_entries.append(char)
            continue
        description = " ".join(
            p for p in (char["role"], char["appearance"]) if p).strip()
        cast.append({
            "name": char["name"],
            "description": description,
            "voice_hint": _voice_hint(
                char["name"], char["role"], char["appearance"],
                char["voice_style"]),
            "jacket_color": _jacket_color(" ".join(
                p for p in (char["role"], char["appearance"],
                            char["costume"]) if p)),
            "height_px": CHARACTER_HEIGHTS[
                len(cast) % len(CHARACTER_HEIGHTS)],
            # Preserved V1 trait data (verbatim; the engine consumes
            # what it understands today and Stage 3/F8 consumes the
            # rest -- nothing is dropped).
            "voice": char["voice"],
            "voice_style": char["voice_style"],
            "appearance": char["appearance"],
            "role": char["role"],
            "traits": list(char["traits"]),
            "costume_text": char["costume"],
            "costume_changes": list(char["costume_changes"]),
            "head_ratio": char["head_ratio"],
            "identity_id": char["identity_id"],
        })
    # Speakers that appear in lines but not in the roster still get a
    # character entry (the deterministic planner's rule). Unreachable
    # for valid V1 documents -- the parser rejects undeclared speakers
    # (V1E015) -- but kept so a valid package never loses a speaker.
    cast_names = {c["name"] for c in cast}
    for ln in all_lines:
        speaker = ln["speaker"]
        if speaker != NARRATOR_SPEAKER and speaker not in cast_names:
            cast_names.add(speaker)
            cast.append({
                "name": speaker, "description": "",
                "voice_hint": "", "jacket_color": _jacket_color(""),
                "height_px": 540,
                "voice": "AUTO", "voice_style": "",
                "appearance": "", "role": "", "traits": [],
                "costume_text": "", "costume_changes": [],
                "head_ratio": 0.34, "identity_id": "",
            })

    # --- Scenes ----------------------------------------------------
    locations = data["locations"]
    package_scenes: list[dict] = []
    setting_strings: list[str] = []
    shots: list[dict] = []
    gemini_shots: list[dict] = []
    shot_notes: list[str] = []
    dropped_cues: list[dict] = []
    audio_cues: list[dict] = []

    for sc in scenes_data:
        number = sc["number"]
        loc_block = _resolve_location(locations, sc["location_ref"])
        setting = sc["location_text"] or (
            loc_block["name"] if loc_block else "")
        setting_strings.append(setting)
        action_text = " ".join(
            p for p in list(sc["actions"]) + [
                sh["action"] for sh in sc["shots"]] if p).strip()
        raw_cues = extract_action_cues(action_text)
        cues = [c for c in raw_cues if c in SUPPORTED_CUES]
        dropped = [c for c in raw_cues if c not in SUPPORTED_CUES]
        if dropped:
            dropped_cues.append({"scene": number, "cues": dropped})
        lead = _action_lead_sec(cues, action_text)
        lines = [{
            "speaker": ("narrator" if ln["speaker"] == NARRATOR_SPEAKER
                        else ln["speaker"]),
            "kind": ln["kind"],
            "text": ln["text"],
        } for ln in sc["spoken_lines"]]
        scan_text = " ".join(
            p for p in [setting,
                        loc_block["name"] if loc_block else "",
                        loc_block["geography"] if loc_block else "",
                        loc_block["architecture"] if loc_block else "",
                        " ".join(loc_block["features"])
                        if loc_block else ""] if p)
        package_scenes.append({
            "number": number,
            "title": sc["title"],
            "setting": setting,
            "action_text": action_text,
            # V1 has no single audio/animation free-text field; the
            # structured cues and camera directives are preserved in
            # v1_scene below. Both fields are emitted-but-unread
            # downstream (see PIPELINE_INTERFACE_SPEC).
            "audio_text": "",
            "animation_reqs": "",
            "action_cues": cues,
            "action_lead_sec": lead,
            "lines": lines,
            "location": {
                "location_keyword": _location_keyword(scan_text),
                "setting": setting,
                "mood": _mood(sc["mood"]),
                "time_of_day": _time_of_day(sc["time_of_day"]),
            },
            # Full verbatim scene data: nothing declared in the
            # script is discarded (LOCATION ref, VISUAL, EXPRESSION,
            # CAMERA, transitions, *_NONE flags, SHOT blocks, cues).
            "v1_scene": sc,
        })
        shots.append({
            "shot_id": f"S{number}A", "scene": number,
            "kind": "action", "speaker": None, "text": "",
            "action_cues": cues, "estimated_sec": lead,
        })
        for ordinal, ln in enumerate(sc["spoken_lines"], 1):
            shots.append({
                "shot_id": f"S{number}L{ordinal}", "scene": number,
                "kind": ln["kind"],
                "speaker": ("narrator"
                            if ln["speaker"] == NARRATOR_SPEAKER
                            else ln["speaker"]),
                "text": ln["text"],
                "action_cues": cues, "estimated_sec": 4.0,
            })
        audio_cues.extend(sc["audio_cues"])
        audio_cues.extend(sc["vfx_cues"])
        for sh in sc["shots"]:
            shot_type = sh["type"]
            if shot_type not in HONOURED_SHOT_TYPES:
                shot_notes.append(
                    f"scene {number} shot {sh['id']}: type "
                    f"{shot_type!r} is not honoured by plan_shots "
                    f"(kept in v1_scene; default shot rules apply)")
                continue
            if not sh["spoken_line_ids"]:
                shot_notes.append(
                    f"scene {number} shot {sh['id']}: no spoken lines "
                    f"attached (kept in v1_scene)")
                continue
            for line_id in sh["spoken_line_ids"]:
                ordinal = line_index.get(line_id)
                if ordinal is None:
                    shot_notes.append(
                        f"scene {number} shot {sh['id']}: unknown "
                        f"LINE_ID {line_id!r} (kept in v1_scene)")
                    continue
                gemini_shots.append({
                    "scene": number,
                    "line_index": ordinal,
                    "shot_type": shot_type,
                })

    hook = all_lines[0]["text"]
    twist = all_lines[-1]["text"]

    return {
        "characters": cast,
        "locations": setting_strings,
        "scenes": package_scenes,
        "shots": shots,
        # No estimated SFX timestamps: V1 cues carry triggers, and
        # inventing timestamps is forbidden. Full cues are preserved
        # in v1_audio_cues / per-scene v1_scene.
        "audio_events": [],
        "hook": hook,
        "twist": twist,
        "gemini_shots": gemini_shots,
        # --- Preserved V1 data (namespaced; never discarded) -------
        "v1_format": "studio_script_v1",
        "v1_snapshot_hash": data["snapshot_hash"],
        "v1_meta": data["meta"],
        "v1_characters": declared,
        "v1_locations": locations,
        "v1_props": data["props"],
        "v1_constraints": data["constraints"],
        "v1_qa": data["qa"],
        "v1_output": data["output"],
        "v1_global_audio": data["global_audio"],
        "v1_end_card": data["end_card"],
        "v1_narrator": narrator_entries,
        "v1_audio_cues": audio_cues,
        "v1_unsupported_fields": data["unsupported_fields"],
        "v1_dropped_cues": dropped_cues,
        "v1_shot_notes": shot_notes,
    }


def resolve_v1_plan(script_text: str) -> tuple[dict, str, str]:
    """Parse a STUDIO SCRIPT V1 script and adapt it to a scene package.

    Returns the same 3-tuple as gemini_planner.resolve_plan:
    (package, planner_label, planner_detail). The label is "v1" --
    never "gemini" (no Gemini call ran) and never "fallback" (this is
    not the free-form local planner).

    Raises V1AdapterError when the text is not a V1 document, when
    the document is invalid, or when it has no spoken lines.
    """
    if detect_format(script_text) != "studio_v1":
        raise V1AdapterError(
            "not a STUDIO SCRIPT V1 document: expected the "
            "'# STUDIO SCRIPT V1' marker or a PROJECT: + SCENE n: "
            "structure")
    doc = parse_studio_script_v1(script_text)
    package = adapt_document(doc)
    n_lines = sum(len(s["lines"]) for s in package["scenes"])
    detail = (
        f"STUDIO SCRIPT V1: {len(package['scenes'])} scenes, "
        f"{len(package['characters'])} characters, {n_lines} spoken "
        f"lines; deterministic V1 adapter, no Gemini enrichment")
    return package, ADAPTER_LABEL, detail
