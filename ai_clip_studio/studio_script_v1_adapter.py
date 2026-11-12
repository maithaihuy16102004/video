"""STUDIO SCRIPT V1 -> scene-package adapter (Phase B).

ONE pipeline, two parsers: free-form scripts keep the existing
deterministic/Gemini path in gemini_planner.py; scripts in STUDIO
SCRIPT V1 format are parsed by studio_script_v1.py and mapped here
to the SAME package shape resolve_plan() returns, so product_flow.py,
plan_shots, the TTS stage and the :8788 server consume them
unchanged. The wiring is a single early return at the top of
resolve_plan() (see gemini_planner.py); this module holds all of the
mapping so the wiring stays a one-line route.

Two dialects: the parser's to_dict() shape comes in the original
grammar and a newer first-person dialect (block ids, display names,
verbatim ``fields`` dicts, scene/shot ids, structured cues). This
adapter codes against BOTH with .get fallbacks, so documents parsed
by either shape adapt identically where they overlap. Nothing here
names a story, a character, or a location from any particular script.

Mapping rules (all generic):

* Speakers: the parser canonicalises narrator speech to ``"Narrator"``;
  the pipeline sentinel is lowercase ``"narrator"`` (voice selection,
  character visibility, speaker matching), so the adapter normalises
  it -- EXCEPT in first-person mode (see below), where narration
  keeps its character speaker and no sentinel is ever emitted.
  CHARACTER blocks whose name is a narrator alias (the parser's own
  NARRATOR_ALIASES) are excluded from the visible cast in legacy
  documents only -- a narrator must never be drawn standing in a
  scene -- and their data is preserved under ``v1_narrator``.
* First-person rule (standing prerequisite): when the document
  declares first-person mode (a FIRST_PERSON_* storytelling mode, an
  explicit NONE external narrator, or a primary character), EVERY
  spoken line keeps its character speaker (display name); narration
  uses the speaking character's voice; no narrator CHARACTER is
  excluded; the narrator-alias exclusion does not apply. Detection
  reads the document-level storytelling_mode / primary_character /
  external_narrator fields (top level or meta), defensively.
* Characters: description = ROLE + APPEARANCE (verbatim). Render
  traits come from trait_derivation.derive_render_traits (single
  source of truth, word-boundary rules throughout): the section 15.2
  ``render_traits`` object is emitted per character AND its values
  are copied to the top-level keys map_character consumes (template,
  body_variant, costume, hair_style, hat, moustache_style, glasses).
  jacket_color reuses the generic colour-word map; height_px reuses
  the deterministic alternation. voice_hint is derived ONLY from
  explicit evidence (an explicit "giong nam"/"giong nu" phrase, the
  structured GENDER field, or a word-boundary honorific); the raw
  VOICE string / VOICE_ID is NEVER passed as a voice_hint. The
  voice id is preserved verbatim as ``voice_id``. V1 voice/
  voice_style/traits/costume/costume_changes/head_ratio/identity_id
  are preserved verbatim on the entry. Elderly traits flow through
  the derivation (age words -> elderly template).
* Extras: characters flagged as extras (or, when the parser flag is
  absent, whose role names background extras) are EXCLUDED from the
  visible cast like the narrator exclusion, recorded in ``v1_notes``
  and ``v1_extras``; they stay in ``v1_characters`` and trait blocks.
* Scenes: setting = the scene's inline location text, or the resolved
  LOCATION block's name when no inline text exists. action_text joins
  the scene ACTION lines and the SHOT action lines; action_cues come
  from the SAME generic extract_action_cues() the free-form path
  uses, filtered against the supported-cue set (dropped cues are
  recorded in ``v1_dropped_cues``). action_lead_sec reuses the
  deterministic planner's formula. Each scene gains ``scene_id``,
  ``location_text`` (inline text or ""), ``costume`` (raw scene
  costume label or "") plus ``costume_garment`` (the generic
  CIVILIAN->none / MILITARY->uniform mapping), ``props`` (relevant
  prop ids, see below) and ``visible_characters`` (display names of
  the non-extra characters present: the scene's declared character
  list in the newer dialect, the scene's non-narrator speakers in
  the legacy dialect).
* Location dict: location_keyword/mood/time_of_day derive via
  trait_derivation (same generic rules as before). The scene's
  ``location`` gains ``v1_location``: the section 15.3 trait block
  for the scene's resolved LOCATION, or None for inline-only scenes.
  The TRUE location data is carried in ``v1_scene``/``v1_locations``
  and the trait blocks; this module never claims the generic street
  IS the scripted location.
* Shots: the package ``shots`` list mirrors the deterministic
  planner's shape. V1 SHOT blocks map to ``gemini_shots`` ONLY when
  their effective type is one plan_shots honours and they reference
  real spoken lines; every other shot stays in the ``v1_scene``
  passthrough and is noted in ``v1_shot_notes``. The effective type
  is the SHOT TYPE when present, else the generic camera-text
  mapping (trait_derivation.map_camera_text_to_shot_type); the
  effective camera movement is the camera_movement_text mapping
  when free movement text is present (a parser-default STATIC is
  indistinguishable from an explicit one), else the SHOT
  CAMERA_MOVEMENT enum. ``shot_directives`` carries one directive
  per SHOT block plus one scene-default directive per scene with
  explicit camera info (shot_type "medium": scene defaults never
  infer a type from prose); directives preserve the verbatim camera
  / movement text plus location_override and trigger. Engine
  precedence: directive > gemini_shots > defaults. Every directive
  also carries ``camera_angle`` (C9, PROVISIONAL pending
  reconciliation with the independent camera audit's fix spec):
  explicit angle words in the CAMERA text win, else the default
  angle for the shot type (establishing/object_insert -> high_angle,
  over_the_shoulder -> over_shoulder, else eye_level). Consecutive
  shot_reverse_shot directives in a scene alternate ``srs_side``
  (False/True/...); other directives carry None. When a shot names
  two characters, the directive carries ``subject`` + ``counterpart``
  (first named = foreground/shoulder side, second = target); a
  single-character shoulder shot keeps subject only. Angles are
  labels only: no camera positions, targets, or FOV are emitted --
  all viewpoint geometry is engine-owned.
* Expressions: V1 EXPRESSION lines map to face-system expression
  names (trait_derivation.map_expression_text, including the
  "sững" family -> "surprised") and attach as ``line["expression"]``
  to the spoken lines they govern: scene expressions attach to the
  scene's lines (character-prefixed ones only to that character's
  lines; bare ones to all lines in the scene); shot expressions
  attach to the shot's lines and override scene expressions.
  Lines without an expression keep no "expression" key (the engine
  falls back to its text scan). Unmappable expressions are reported
  in trait_blocks["unmapped"], never dropped silently.
* Props: package["props"] = [{id, name, kind, owner, description,
  fields}] with kind from derive_prop_kind (the newer dialect's
  TYPE/COLOR/MATERIAL fields feed the derivation). Scene "props"
  lists relevant prop ids: an explicit SCENES restriction wins; an
  ALL-scenes prop appears everywhere; otherwise a prop is relevant
  when its owner is present in the scene or its kind keywords / name
  are mentioned in the scene text. With no PROP blocks, props = []
  and cue-based prop behaviour is untouched.
* Audio: ``audio_events`` is []. V1 cues carry triggers, not
  timestamps, and inventing SFX timestamps is forbidden -- the full
  cue list is preserved in ``v1_audio_cues`` and per scene in
  ``v1_scene``, and the section 15.4 blocks (sfx/music/unmapped
  cues, no timestamps) live in ``trait_blocks``.
* Trait blocks: package["trait_blocks"] is the section 15 envelope
  built by the shared builder: one character block per DECLARED
  character (including narrator/extra entries), one location block
  per DECLARED location, audio blocks from scripted cues only, and
  special-action directives derived from scripted ACTION text
  (unsupported actions reported in "unmapped", never replaced by
  camera moves). Costume changes in trait blocks combine the
  verbatim COSTUME_CHANGE entries with per-scene outfits derived
  from the character's COSTUME_CIVILIAN / COSTUME_MILITARY lists.
* End card / pauses: ``v1_end_card`` gains ``duration_sec``
  (preferring the parser's value, falling back to parsing the
  duration text, e.g. "3s" -> 3.0). ``end_hold_sec`` comes from
  END_HOLD (0.0 when absent). Every spoken line gains
  ``pause_after_sec`` from POST_DIALOGUE_PAUSE (line, then shot,
  then scene scope; default 0.35).
* hook/twist: first/last spoken-line text, verbatim.
* Everything else the parser produces is preserved under ``v1_*``
  keys so the adapter discards nothing the script declared.

Gemini enrichment (optional, Stage 3): resolve_v1_plan(...,
enrich_with_gemini=True) calls real Gemini for section 15 trait
data, validates it, and overlays it onto the deterministic package
(ground truth = the parsed document; invented content is dropped
with notes). The enrichment is cached in-memory keyed by
snapshot_hash within the process -- success and failure alike -- so
the server's analyze + draft plans always agree. Without the flag,
the plan is deterministic and labelled "v1". Enrichment never
overwrites verbatim hook/twist lines.

Refusal: a document with validation errors is refused with a
V1AdapterError listing every error with its line number and code.
A document with no spoken lines is likewise refused.
"""
from __future__ import annotations

import copy
import json
import re

from .gemini_client import (
    GeminiClient,
    GeminiError,
    NoGeminiAvailable,
    RateLimitedError,
)
from .planner_fallback import ACTION_LEAD_SECONDS, CHARACTER_HEIGHTS
from .studio_script_v1 import (
    NARRATOR_ALIASES,
    NARRATOR_SPEAKER,
    StudioScriptV1Document,
    detect_format,
    parse_studio_script_v1,
)
from .trait_derivation import (
    CAMERA_MOVEMENTS,
    HEAD_RATIO_LOCKED,
    PROP_KEYWORDS,
    SHOT_TYPES,
    build_action_directive,
    build_character_trait_block,
    build_location_trait_block,
    build_trait_blocks,
    derive_action_directives,
    derive_audio_blocks,
    derive_location_traits,
    derive_prop_kind,
    derive_render_traits,
    derive_voice_hint,
    map_camera_movement_text,
    map_camera_text_to_shot_type,
    map_camera_angle,
    map_expression_text,
    map_scene_costume_to_garment,
    moustache_style_from_fields,
    parse_duration_seconds,
    validate_trait_blocks,
)
from .vi_script_parser import extract_action_cues

# Planner label for V1-routed plans. Distinct from "gemini" (a real
# Gemini call produced enrichment) and "fallback" (the free-form local
# planner).
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
    # Stage 3 / channel-study vocabulary (R1/R6): honoured by
    # plan_shots (SHOT_SCALE carries both). Sync test: this set
    # must equal the renderer's SHOT_SCALE keys exactly.
    "medium_close_up", "graphic_insert",
})

# The deterministic planner's bus-arrival rule, reused verbatim so V1
# and free-form lead-ins behave identically.
_BUS_ARRIVAL_RE = re.compile(r"tiến|xe buýt[^.]{0,20}dừng")

# Default pause after a spoken line when no POST_DIALOGUE_PAUSE is
# declared (the value the audio timeline has always used).
DEFAULT_PAUSE_AFTER_SEC = 0.35

# Gemini models tried for V1 enrichment, in order (same chain as the
# free-form planner; defined here to avoid importing gemini_planner,
# which imports this module).
_ENRICHMENT_MODELS = ("gemini-3.5-flash-lite", "gemini-flash-lite-latest")
_ENRICHMENT_MAX_TOKENS = 8192

# In-memory enrichment cache keyed by snapshot_hash: {"failed": bool,
# "package"/"label"/"detail"} on success, {"failed": True, "reason"}
# on failure. Bounded; see _cache_enrichment.
_ENRICHMENT_CACHE: dict[str, dict] = {}
_ENRICHMENT_CACHE_MAX = 32


class V1AdapterError(ValueError):
    """Raised when a V1 document cannot be adapted (invalid, or no
    spoken lines). Carries the parser's validation errors when the
    document itself is invalid."""

    def __init__(self, message: str, errors=None):
        super().__init__(message)
        self.errors = list(errors or [])


def _clear_enrichment_cache() -> None:
    """Drop all cached enrichments (tests only)."""
    _ENRICHMENT_CACHE.clear()


def _cache_enrichment(snapshot_hash: str, value: dict) -> None:
    _ENRICHMENT_CACHE[snapshot_hash] = value
    while len(_ENRICHMENT_CACHE) > _ENRICHMENT_CACHE_MAX:
        _ENRICHMENT_CACHE.pop(next(iter(_ENRICHMENT_CACHE)))


def _normalize_name(name: str) -> str:
    # Mirrors studio_script_v1._normalize_name exactly (casefold +
    # whitespace collapse) so narrator-alias detection agrees with
    # the parser.
    return " ".join(str(name or "").strip().casefold().split())


def _norm_text(text: str) -> str:
    return " ".join(str(text or "").lower().replace("_", " ").replace(
        "-", " ").split())


def _has_word(text: str, word: str) -> bool:
    return re.search(r"\b" + re.escape(word) + r"\b", text or "") is not None


def _is_narrator_character(name: str) -> bool:
    return _normalize_name(name) in NARRATOR_ALIASES


def _field_value(fields, key: str):
    """Case-insensitive lookup in a verbatim fields dict."""
    if not isinstance(fields, dict):
        return None
    wanted = key.strip().casefold()
    for k, v in fields.items():
        if str(k).strip().casefold() == wanted:
            return v
    return None


def _field_text(fields, key: str) -> str:
    value = _field_value(fields, key)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return str(value)


def _text_value(value) -> str:
    """Free-text field that may arrive as a string or a bullet list."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return str(value)


def _voice_hint(name: str, role: str, appearance: str,
                voice_style: str) -> str:
    """Pipeline voice_hint from the script's own character text.

    Thin wrapper over the shared derivation (same tight rules: never
    the raw VOICE string). Kept for existing callers/tests.
    """
    return derive_voice_hint(name, role, appearance, voice_style)


def _location_keyword(scan_text: str) -> str:
    """Renderer location keyword from location text (generic)."""
    return derive_location_traits(inline_text=scan_text or "")[
        "location_keyword"]


def _time_of_day(text: str) -> str:
    return derive_location_traits(time_of_day_text=text or "")[
        "time_of_day"]


def _mood(text: str) -> str:
    return derive_location_traits(mood_text=text or "")["mood"]


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


# --- First-person / dialect helpers -----------------------------------

def _detect_first_person(data: dict) -> dict:
    """Detect first-person mode from document-level declarations.

    Checks the top-level keys and the meta dict (both placements are
    tolerated while the parser contract settles). Enabled when the
    storytelling mode starts with FIRST_PERSON, when the external
    narrator is explicitly NONE, or when a primary character is
    declared.
    """
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    mode = str(data.get("storytelling_mode") or meta.get("storytelling_mode")
               or "")
    primary = str(data.get("primary_character")
                  or meta.get("primary_character") or "")
    external = data.get("external_narrator", meta.get("external_narrator"))
    external_text = "" if external is None else str(external)
    enabled = (mode.strip().upper().startswith("FIRST_PERSON")
               or external_text.strip().upper() == "NONE"
               or bool(primary.strip()))
    return {
        "enabled": enabled,
        "storytelling_mode": mode or None,
        "primary_character": primary or None,
        "external_narrator": external_text or None,
    }


def _is_extra_character(char: dict, fields: dict) -> bool:
    """True when the character is a background extra.

    The parser's explicit flag wins; when absent, a role naming
    background extras is the fallback signal.
    """
    flag = char.get("is_extra")
    if flag is not None:
        return bool(flag)
    if _field_value(fields, "IS_EXTRA") is not None:
        return bool(_field_value(fields, "IS_EXTRA"))
    role = (char.get("role") or "").lower()
    return "background extra" in role or role.strip() == "extras" \
        or "quần chúng" in role


def _character_voice_id(char: dict, fields: dict) -> str:
    """Verbatim voice id for the VieNeu path (never a voice_hint)."""
    for candidate in (char.get("voice_id"),
                      _field_value(fields, "VOICE_ID"),
                      _field_value(fields, "VOICE")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    voice = str(char.get("voice") or "").strip()
    if voice and voice.upper() not in ("AUTO", "NONE"):
        return voice
    return ""


def _package_speaker(speaker: str, first_person: dict,
                     primary_display: str) -> str:
    """Map a parsed speaker to the pipeline speaker name.

    Legacy: the parser's Narrator becomes the "narrator" sentinel.
    First-person: narration keeps its character speaker; a narrator
    alias resolves to the primary character; the sentinel is never
    emitted.
    """
    if first_person["enabled"]:
        if speaker == NARRATOR_SPEAKER \
                or _normalize_name(speaker) in NARRATOR_ALIASES:
            return primary_display or speaker
        return speaker
    return "narrator" if speaker == NARRATOR_SPEAKER else speaker


# --- Shot helpers -------------------------------------------------------

def _shot_action_text(shot: dict) -> str:
    text = _text_value(shot.get("action"))
    if text:
        return text
    fields = shot.get("fields") if isinstance(shot.get("fields"), dict) else {}
    return _field_text(fields, "ACTION")


def _shot_expression_text(shot: dict) -> str:
    text = _text_value(shot.get("expression"))
    if text:
        return text
    fields = shot.get("fields") if isinstance(shot.get("fields"), dict) else {}
    return _field_text(fields, "EXPRESSION")


def _shot_line_ids(shot: dict, scene_lines: list[dict]) -> list[str]:
    """Spoken-line ids belonging to a shot.

    The parser's spoken_line_ids win; otherwise lines whose shot_id
    matches the shot id. Returns ids in scene order.
    """
    ids = list(shot.get("spoken_line_ids") or [])
    if ids:
        return ids
    shot_id = shot.get("id")
    if not shot_id:
        return []
    return [ln.get("line_id") for ln in scene_lines
            if ln.get("shot_id") == shot_id and ln.get("line_id")]


def _effective_shot_type(shot: dict) -> tuple[str, str | None]:
    """Shot type: the SHOT TYPE when valid, else camera-text mapping."""
    raw_type = str(shot.get("type") or "").strip()
    if raw_type in SHOT_TYPES:
        return raw_type, None
    shot_type, note = map_camera_text_to_shot_type(
        _text_value(shot.get("camera")))
    if raw_type:
        return shot_type, (
            f"type {raw_type!r} is not a known shot type; camera text "
            f"mapping applied ({shot_type})")
    return shot_type, note


def _effective_camera_movement(shot: dict) -> tuple[str, str | None]:
    """Camera movement: free movement text wins when present (a
    parser-default STATIC is indistinguishable from an explicit
    one), else the CAMERA_MOVEMENT enum."""
    move_text = _text_value(shot.get("camera_movement_text"))
    if move_text:
        return map_camera_movement_text(move_text)
    enum_value = str(shot.get("camera_movement") or "STATIC").strip()
    if enum_value in CAMERA_MOVEMENTS:
        return enum_value, None
    return map_camera_movement_text(enum_value)


_SUBJECT_SPLIT_RE = re.compile(
    r"\s*(?:[,;+&]|\band\b|\bvà\b)\s*", re.IGNORECASE)


def _subject_counterpart(shot: dict, shot_speakers: list[str],
                         shot_type: str, char_display: dict
                         ) -> tuple[str, str | None, str | None]:
    """Subject + counterpart for a shot directive.

    Returns (subject, counterpart, note). The SUBJECT field is
    authoritative and carried verbatim when it names one character
    (or a prop, or anything else). When it names two or more
    characters, the first named is the subject and the second is the
    counterpart; further names are ignored with a note. When the
    SUBJECT field is empty on an over-the-shoulder shot, the shot's
    first two distinct speakers (line order) supply subject +
    counterpart; when it names exactly one character on such a shot,
    the first other speaker supplies the counterpart. ASSUMPTION
    (documented): first named = foreground / shoulder side, second
    named = target. For non-shoulder shots the counterpart is
    simply the second named character, with no staging assumption.
    No camera geometry is emitted: angles are labels only.
    """
    raw_subject = _text_value(shot.get("subject"))
    tokens = ([t.strip() for t in _SUBJECT_SPLIT_RE.split(raw_subject)
               if t.strip()] if raw_subject else [])
    named = []
    for token in tokens:
        display = char_display.get(_normalize_name(token))
        if display is not None and display not in [d for _t, d in named]:
            named.append((token, display))
    note = None
    if len(named) >= 2:
        if len(named) > 2:
            note = (f"subject names {len(named)} characters; only the "
                    "first two are carried (subject + counterpart)")
        return named[0][0], named[1][0], note
    if raw_subject:
        counterpart = None
        if len(named) == 1 and shot_type == "over_the_shoulder":
            for speaker in shot_speakers:
                if speaker == "narrator":
                    continue
                if _normalize_name(speaker) != _normalize_name(named[0][1]):
                    counterpart = speaker
                    break
        return raw_subject, counterpart, None
    if shot_type == "over_the_shoulder":
        distinct = []
        for speaker in shot_speakers:
            if speaker != "narrator" and speaker not in distinct:
                distinct.append(speaker)
        if len(distinct) >= 2:
            return distinct[0], distinct[1], None
        if len(distinct) == 1:
            return distinct[0], None, None
    return "", None, None


def _parse_expression_prefix(text: str, char_keys: dict):
    """Split "Character: expression" when the prefix resolves.

    Returns (character_key_or_None, expression_text). Mirrors the
    parser's rule: a prefix that resolves to a declared character
    (or a narrator alias) is a character prefix; otherwise the whole
    string is the expression text.
    """
    match = re.match(r"^(.+?)\s*:\s*(.+)$", text.strip())
    if not match:
        return None, text.strip()
    prefix, rest = match.group(1).strip(), match.group(2).strip()
    norm = _normalize_name(prefix)
    if norm in char_keys or norm in NARRATOR_ALIASES:
        return norm, rest
    return None, text.strip()


# --- Pause / end-card helpers -------------------------------------------

def _line_pause(line: dict, shot: dict | None, scene: dict) -> float:
    """Pause after a spoken line: line, then shot, then scene scope,
    defaulting to DEFAULT_PAUSE_AFTER_SEC. Never raises."""
    candidates = []
    for source in (line, shot, scene):
        if not isinstance(source, dict):
            continue
        candidates.append(source.get("pause_after_sec"))
        candidates.append(source.get("post_dialogue_pause"))
        fields = source.get("fields")
        if isinstance(fields, dict):
            candidates.append(_field_value(fields, "POST_DIALOGUE_PAUSE"))
            candidates.append(_field_value(fields, "PAUSE_AFTER_SEC"))
    for candidate in candidates:
        parsed = parse_duration_seconds(candidate, default=None)
        if parsed is not None:
            return parsed
    return DEFAULT_PAUSE_AFTER_SEC


def _end_hold_sec(data: dict, scenes_data: list[dict]) -> float:
    """END_HOLD in seconds: end-card fields, then scene fields (last
    scene wins), then document/meta. 0.0 when absent."""
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    end_card = data.get("end_card")
    candidates = []
    if isinstance(end_card, dict):
        candidates.append(end_card.get("end_hold_sec"))
        candidates.append(end_card.get("end_hold"))
        fields = end_card.get("fields")
        if isinstance(fields, dict):
            candidates.append(_field_value(fields, "END_HOLD"))
    for scene in scenes_data:
        if isinstance(scene, dict):
            candidates.append(scene.get("end_hold"))
            fields = scene.get("fields")
            if isinstance(fields, dict):
                candidates.append(_field_value(fields, "END_HOLD"))
    candidates.append(meta.get("end_hold"))
    candidates.append(data.get("end_hold"))
    for candidate in reversed(candidates):
        parsed = parse_duration_seconds(candidate, default=None)
        if parsed is not None:
            return parsed
    return 0.0


def _end_card_with_duration(end_card) -> dict | None:
    """Copy of the end card with duration_sec filled in.

    Prefers the parser's duration_sec; falls back to parsing the
    duration text ("3s" -> 3.0). None stays None (no card specified).
    """
    if end_card is None:
        return None
    if not isinstance(end_card, dict):
        return end_card
    card = dict(end_card)
    if card.get("duration_sec") is None:
        parsed = parse_duration_seconds(card.get("duration"), default=None)
        card["duration_sec"] = parsed
    return card


# --- Prop helpers ---------------------------------------------------------

def _prop_id(name: str, taken: set[str]) -> str:
    """Stable prop id: slug of the (unique) prop name, suffixed on
    collision."""
    slug = re.sub(r"[^\w]+", "_", str(name or "").strip().casefold(),
                  flags=re.UNICODE).strip("_")
    if not slug:
        slug = "prop"
    candidate = slug
    suffix = 2
    while candidate in taken:
        candidate = f"{slug}_{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def _prop_relevant(prop_raw: dict, kind: str, scene_number: int,
                   scene_person_norms: set[str],
                   scene_text_norm: str, char_map: dict) -> bool:
    """Whether a prop belongs in a scene (documented rule).

    An explicit SCENES restriction wins; ALL means every scene.
    Otherwise the prop is relevant when its owner is present in the
    scene or its kind keywords / name are mentioned in the scene
    text (actions, visual, shot actions/triggers, spoken lines).
    """
    scenes = prop_raw.get("scenes") or []
    if prop_raw.get("all_scenes"):
        return True
    if scenes:
        try:
            wanted = {int(s) for s in scenes}
        except (TypeError, ValueError):
            wanted = set()
        return scene_number in wanted
    owner = str(prop_raw.get("owner") or "").strip()
    if owner and owner.upper() != "NONE":
        owner_key = _normalize_name(owner)
        resolved = char_map.get(owner_key)
        owner_norm = _normalize_name(resolved) if resolved else owner_key
        if owner_norm in scene_person_norms or owner_key in scene_person_norms:
            return True
    keywords = PROP_KEYWORDS.get(kind, ())
    if keywords and any(_has_word(scene_text_norm, k) for k in keywords):
        return True
    name_norm = _norm_text(prop_raw.get("name") or "")
    if name_norm and name_norm in scene_text_norm:
        return True
    tokens = name_norm.split()
    if tokens and len(tokens[-1]) > 2 \
            and _has_word(scene_text_norm, tokens[-1]):
        return True
    return False


# --- Main adaptation ------------------------------------------------------

def _adapt_document(doc) -> tuple[dict, dict]:
    """Adapt + return (package, context). Context carries the lookup
    maps the Gemini enrichment overlay needs."""
    data = doc.to_dict()
    errors = data.get("validation_errors") or []
    if errors:
        detail = "\n".join(
            f"line {e['line']} [{e['code']}]: {e['message']}"
            for e in errors)
        raise V1AdapterError(
            "STUDIO SCRIPT V1 document is invalid; refusing to render:\n"
            + detail, errors=errors)

    scenes_data = data.get("scenes") or []
    all_lines = [ln for sc in scenes_data
                 for ln in (sc.get("spoken_lines") or [])]
    if not all_lines:
        raise V1AdapterError(
            "STUDIO SCRIPT V1 document has no spoken lines; "
            "nothing to narrate")

    first_person = _detect_first_person(data)
    declared = data.get("characters") or []
    locations = data.get("locations") or []
    props_data = data.get("props") or []

    # Character lookup: normalised name / identity_id / block id ->
    # display name. Built before the cast loop (primary resolution).
    char_display: dict[str, str] = {}
    char_identity: dict[str, str] = {}
    for char in declared:
        display = char.get("name", "")
        identity = char.get("identity_id") or display
        for key in (char.get("name"), char.get("identity_id"),
                    char.get("id")):
            if key:
                char_display[_normalize_name(str(key))] = display
                char_identity[_normalize_name(str(key))] = identity
    primary_display = ""
    if first_person["primary_character"]:
        primary_display = char_display.get(
            _normalize_name(first_person["primary_character"]),
            first_person["primary_character"])

    # Global 1-based line ordinals in document order -- the key
    # plan_shots uses to look up gemini_shots entries.
    line_index: dict[str, int] = {}
    for ordinal, ln in enumerate(all_lines, 1):
        line_id = ln.get("line_id") or f"L{ordinal:03d}"
        line_index[line_id] = ordinal

    # --- Characters: visible cast + preserved narrator/extra data --
    cast: list[dict] = []
    narrator_entries: list[dict] = []
    extra_entries: list[dict] = []
    v1_notes: list[str] = []
    # Per-declared-character trait context, in declaration order:
    # {char, fields, render_traits, voice_id, in_cast}
    trait_context: list[dict] = []
    for char in declared:
        name = char.get("name", "")
        fields = char.get("fields") if isinstance(
            char.get("fields"), dict) else {}
        role = char.get("role", "") or ""
        appearance = char.get("appearance", "") or ""
        voice_style = char.get("voice_style", "") or ""
        costume_text = char.get("costume", "") or ""
        trait_list = list(char.get("traits") or [])
        gender = _field_text(fields, "GENDER")
        is_narrator = (not first_person["enabled"]
                       and _is_narrator_character(name))
        is_extra = _is_extra_character(char, fields)
        height = CHARACTER_HEIGHTS[len(cast) % len(CHARACTER_HEIGHTS)] \
            if not (is_narrator or is_extra) else 540
        render_traits = derive_render_traits(
            name, role, appearance, costume_text, trait_list,
            voice_style, fields=fields, gender=gender, height_px=height)
        voice_id = _character_voice_id(char, fields)
        _style, moustache_note = moustache_style_from_fields(fields)
        if moustache_note:
            v1_notes.append(f"character {name!r}: {moustache_note}")
        context = {"char": char, "fields": fields,
                   "render_traits": render_traits, "voice_id": voice_id,
                   "in_cast": not (is_narrator or is_extra)}
        trait_context.append(context)
        if is_narrator:
            narrator_entries.append(char)
            continue
        if is_extra:
            extra_entries.append(char)
            v1_notes.append(
                f"extra character {name!r} excluded from the visible "
                "cast (kept in v1_characters and trait blocks)")
            continue
        description = " ".join(p for p in (role, appearance) if p).strip()
        cast.append({
            "name": name,
            "description": description,
            "voice_hint": render_traits["voice_hint"],
            "jacket_color": render_traits["jacket_color"],
            "height_px": render_traits["height_px"],
            "voice": char.get("voice", "AUTO"),
            "voice_style": voice_style,
            "appearance": appearance,
            "role": role,
            "traits": trait_list,
            "costume_text": costume_text,
            "costume_changes": list(char.get("costume_changes") or []),
            "head_ratio": char.get("head_ratio", HEAD_RATIO_LOCKED),
            "identity_id": char.get("identity_id") or name,
            "id": char.get("id") or char.get("identity_id") or name,
            "voice_id": voice_id,
            "render_traits": render_traits,
            "template": render_traits["template"],
            "body_variant": render_traits["body_variant"],
            "costume": render_traits["costume"],
            "hair_style": render_traits["hair_style"],
            "hat": render_traits["hat"],
            "moustache_style": render_traits["moustache_style"],
            "glasses": render_traits["glasses"],
        })
    # Speakers that appear in lines but not in the roster still get a
    # character entry (the deterministic planner's rule). Unreachable
    # for valid V1 documents -- the parser rejects undeclared speakers
    # -- but kept so a valid package never loses a speaker.
    cast_names = {c["name"] for c in cast}
    for ln in all_lines:
        speaker = ln.get("speaker", "")
        if first_person["enabled"]:
            speaker = _package_speaker(speaker, first_person,
                                       primary_display)
        if speaker != NARRATOR_SPEAKER and speaker not in cast_names \
                and speaker != "narrator":
            cast_names.add(speaker)
            traits = derive_render_traits(speaker, "", "", "", [], "")
            cast.append({
                "name": speaker, "description": "",
                "voice_hint": "", "jacket_color": traits["jacket_color"],
                "height_px": 540,
                "voice": "AUTO", "voice_style": "",
                "appearance": "", "role": "", "traits": [],
                "costume_text": "", "costume_changes": [],
                "head_ratio": HEAD_RATIO_LOCKED, "identity_id": speaker,
                "id": speaker, "voice_id": "",
                "render_traits": traits,
                "template": traits["template"],
                "body_variant": traits["body_variant"],
                "costume": traits["costume"],
                "hair_style": traits["hair_style"],
                "hat": traits["hat"],
                "moustache_style": traits["moustache_style"],
                "glasses": traits["glasses"],
            })

    # --- Scenes ----------------------------------------------------
    package_scenes: list[dict] = []
    setting_strings: list[str] = []
    shots: list[dict] = []
    gemini_shots: list[dict] = []
    shot_directives: list[dict] = []
    shot_notes: list[str] = []
    dropped_cues: list[dict] = []
    audio_cues: list[dict] = []
    trait_audio_cues: list[dict] = []
    scene_loc_index: list[int | None] = []
    expression_unmapped: list[dict] = []
    action_items: list[dict] = []
    scene_texts_norm: list[str] = []
    scene_person_norms: list[set[str]] = []

    for scene_pos, sc in enumerate(scenes_data):
        number = sc.get("number") or (scene_pos + 1)
        loc_block = _resolve_location(locations, sc.get("location_ref"))
        loc_idx = None
        if loc_block is not None:
            for i, loc in enumerate(locations):
                if loc is loc_block:
                    loc_idx = i
                    break
        scene_loc_index.append(loc_idx)
        setting = sc.get("location_text") or (
            loc_block["name"] if loc_block else "") or ""
        setting_strings.append(setting)
        scene_shots = sc.get("shots") or []
        action_text = " ".join(
            p for p in list(sc.get("actions") or []) + [
                _shot_action_text(sh) for sh in scene_shots] if p).strip()
        raw_cues = extract_action_cues(action_text)
        cues = [c for c in raw_cues if c in SUPPORTED_CUES]
        dropped = [c for c in raw_cues if c not in SUPPORTED_CUES]
        if dropped:
            dropped_cues.append({"scene": number, "cues": dropped})
        lead = _action_lead_sec(cues, action_text)
        spoken = sc.get("spoken_lines") or []
        shot_by_id = {sh.get("id"): sh for sh in scene_shots if sh.get("id")}

        # Expression attachment map for this scene (line_id -> name).
        expr_by_line: dict[str, str] = {}
        for entry in (sc.get("expressions") or []):
            if isinstance(entry, str):
                entry = {"character": None, "expression": entry, "line": 0}
            expr_text = str(entry.get("expression", "") or "")
            expr_name = map_expression_text(expr_text)
            if expr_name is None:
                expression_unmapped.append({
                    "kind": "expression", "expression_text": expr_text,
                    "character": entry.get("character"),
                    "scene_number": number, "shot_id": None,
                    "source_line": entry.get("line"),
                    "reason": ("no face-system expression mapping for "
                               "this expression text"),
                })
                continue
            targets = _expression_targets(
                entry.get("character"), spoken, char_display,
                first_person, primary_display)
            if not targets:
                expression_unmapped.append({
                    "kind": "expression", "expression_text": expr_text,
                    "character": entry.get("character"),
                    "scene_number": number, "shot_id": None,
                    "source_line": entry.get("line"),
                    "reason": ("expression character has no spoken "
                               "lines in this scene"),
                })
                continue
            for line_id in targets:
                expr_by_line.setdefault(line_id, expr_name)
        for sh in scene_shots:
            expr_text = _shot_expression_text(sh)
            if not expr_text:
                continue
            char_key, expr_part = _parse_expression_prefix(
                expr_text, char_display)
            expr_name = map_expression_text(expr_part)
            if expr_name is None:
                expression_unmapped.append({
                    "kind": "expression", "expression_text": expr_text,
                    "character": None, "scene_number": number,
                    "shot_id": sh.get("id"),
                    "source_line": sh.get("line"),
                    "reason": ("no face-system expression mapping for "
                               "this expression text"),
                })
                continue
            shot_ids = _shot_line_ids(sh, spoken)
            if char_key is not None:
                wanted = char_display.get(char_key)
                if wanted is None and char_key in NARRATOR_ALIASES:
                    wanted = ("narrator" if not first_person["enabled"]
                              else primary_display)
                targets = [lid for lid in shot_ids
                           if _line_speaker_matches(
                               lid, spoken, wanted, first_person,
                               primary_display)]
            else:
                targets = shot_ids
            if not targets:
                expression_unmapped.append({
                    "kind": "expression", "expression_text": expr_text,
                    "character": None, "scene_number": number,
                    "shot_id": sh.get("id"),
                    "source_line": sh.get("line"),
                    "reason": ("expression has no spoken lines in "
                               "this shot"),
                })
                continue
            for line_id in targets:
                expr_by_line[line_id] = expr_name  # shot wins

        lines = []
        ordinal_counter = sum(
            len(sc.get("spoken_lines") or []) for sc in scenes_data[:scene_pos])
        for ln in spoken:
            ordinal_counter += 1
            line_id = ln.get("line_id") or f"L{ordinal_counter:03d}"
            if line_id not in line_index:
                line_index[line_id] = ordinal_counter
            speaker = _package_speaker(
                ln.get("speaker", ""), first_person, primary_display)
            shot = shot_by_id.get(ln.get("shot_id")) if ln.get("shot_id") else None
            entry = {
                "speaker": speaker,
                "kind": ln.get("kind", ""),
                "text": ln.get("text", ""),
                "line_id": line_id,
                "pause_after_sec": _line_pause(ln, shot, sc),
            }
            if ln.get("speaker_id"):
                entry["speaker_id"] = ln["speaker_id"]
            if ln.get("lip_sync"):
                entry["lip_sync"] = ln["lip_sync"]
            if line_id in expr_by_line:
                entry["expression"] = expr_by_line[line_id]
            lines.append(entry)

        loc_fields = loc_block.get("fields") if isinstance(
            loc_block, dict) and isinstance(loc_block.get("fields"), dict) \
            else {}
        time_text = sc.get("time_of_day") or _field_text(
            loc_fields, "TIME_OF_DAY") or ""
        mood_text = sc.get("mood") or ""
        loc_traits = derive_location_traits(
            name=_text_value(loc_block.get("name")) if loc_block else "",
            geography=_text_value(loc_block.get("geography"))
            if loc_block else "",
            architecture=_text_value(loc_block.get("architecture"))
            if loc_block else "",
            features=loc_block.get("features") if loc_block else None,
            inline_text=setting,
            time_of_day_text=time_text, mood_text=mood_text)
        scene_costume = sc.get("costume") or ""
        package_scenes.append({
            "number": number,
            "scene_id": sc.get("id") or "",
            "title": sc.get("title") or "",
            "setting": setting,
            "location_text": sc.get("location_text") or "",
            "action_text": action_text,
            "audio_text": "",
            "animation_reqs": "",
            "action_cues": cues,
            "action_lead_sec": lead,
            "lines": lines,
            "location": {
                "location_keyword": loc_traits["location_keyword"],
                "setting": loc_traits["setting"],
                "mood": loc_traits["mood"],
                "time_of_day": loc_traits["time_of_day"],
                "v1_location": None,  # filled after trait blocks
            },
            "costume": scene_costume,
            "costume_garment": map_scene_costume_to_garment(scene_costume),
            "props": [],  # filled after props are built
            "visible_characters": [],  # filled below
            "v1_scene": sc,
        })
        # Visible characters for the scene.
        if sc.get("characters") is not None:
            raw_list = sc.get("characters")
            if isinstance(raw_list, str):
                raw_list = [p.strip() for p in raw_list.split(",") if p.strip()]
            visible = []
            seen_notes: set[str] = set()
            for ref in (raw_list or []):
                display = char_display.get(_normalize_name(str(ref)))
                if display is None:
                    if str(ref) not in seen_notes:
                        seen_notes.add(str(ref))
                        v1_notes.append(
                            f"scene {number}: character reference "
                            f"{str(ref)!r} did not resolve to a declared "
                            "character; excluded from visible_characters")
                    continue
                if display in cast_names and display not in visible:
                    visible.append(display)
            package_scenes[-1]["visible_characters"] = visible
        else:
            visible = []
            for ln in lines:
                if ln["speaker"] != "narrator" \
                        and ln["speaker"] not in visible:
                    visible.append(ln["speaker"])
            package_scenes[-1]["visible_characters"] = visible

        # Mention-scan text + person set for prop relevance.
        mention_parts = list(sc.get("actions") or [])
        mention_parts.append(sc.get("visual") or "")
        for sh in scene_shots:
            mention_parts.append(_shot_action_text(sh))
            mention_parts.append(_text_value(sh.get("trigger")))
        mention_parts.extend(ln.get("text", "") for ln in spoken)
        scene_texts_norm.append(_norm_text(" ".join(mention_parts)))
        persons = {_normalize_name(n)
                   for n in package_scenes[-1]["visible_characters"]}
        persons |= {_normalize_name(ln["speaker"]) for ln in lines}
        persons |= {_normalize_name(char_display.get(
            _normalize_name(ln.get("speaker_id", "")), ""))
            for ln in spoken if ln.get("speaker_id")}
        persons.discard("")
        scene_person_norms.append(persons)

        shots.append({
            "shot_id": f"S{number}A", "scene": number,
            "kind": "action", "speaker": None, "text": "",
            "action_cues": cues, "estimated_sec": lead,
        })
        for ordinal, ln in enumerate(spoken, 1):
            shots.append({
                "shot_id": f"S{number}L{ordinal}", "scene": number,
                "kind": ln.get("kind", ""),
                "speaker": _package_speaker(
                    ln.get("speaker", ""), first_person, primary_display),
                "text": ln.get("text", ""),
                "action_cues": cues, "estimated_sec": 4.0,
            })
        audio_cues.extend(sc.get("audio_cues") or [])
        audio_cues.extend(sc.get("vfx_cues") or [])
        trait_audio_cues.extend(sc.get("audio_cues") or [])

        # Action items for section 15.5 directives.
        for action_text_item in (sc.get("actions") or []):
            action_items.append({
                "text": action_text_item, "scene_number": number,
                "shot_id": None, "source_line": None})
        for sh in scene_shots:
            shot_action = _shot_action_text(sh)
            if shot_action:
                action_items.append({
                    "text": shot_action, "scene_number": number,
                    "shot_id": sh.get("id"), "source_line": sh.get("line")})

        # SHOT blocks -> gemini_shots + shot_directives.
        speaker_by_id = {ln["line_id"]: ln["speaker"] for ln in lines}
        srs_count = 0  # shot_reverse_shot ordinal within this scene
        for sh in scene_shots:
            shot_id = sh.get("id") or ""
            eff_type, type_note = _effective_shot_type(sh)
            if type_note:
                shot_notes.append(
                    f"scene {number} shot {shot_id}: {type_note}")
            eff_move, move_note = _effective_camera_movement(sh)
            if move_note:
                shot_notes.append(
                    f"scene {number} shot {shot_id}: {move_note}")
            shot_line_ids = _shot_line_ids(sh, spoken)
            shot_speakers = [speaker_by_id[lid] for lid in shot_line_ids
                             if lid in speaker_by_id]
            subject, counterpart, subject_note = _subject_counterpart(
                sh, shot_speakers, eff_type, char_display)
            if subject_note:
                shot_notes.append(
                    f"scene {number} shot {shot_id}: {subject_note}")
            if eff_type not in HONOURED_SHOT_TYPES:
                shot_notes.append(
                    f"scene {number} shot {shot_id}: type "
                    f"{eff_type!r} is not honoured by plan_shots "
                    f"(kept in v1_scene; default shot rules apply)")
            elif not shot_line_ids:
                shot_notes.append(
                    f"scene {number} shot {shot_id}: no spoken lines "
                    f"attached (kept in v1_scene)")
            else:
                for line_id in shot_line_ids:
                    ordinal = line_index.get(line_id)
                    if ordinal is None:
                        shot_notes.append(
                            f"scene {number} shot {shot_id}: unknown "
                            f"LINE_ID {line_id!r} (kept in v1_scene)")
                        continue
                    gemini_shots.append({
                        "scene": number,
                        "line_index": ordinal,
                        "shot_type": eff_type,
                    })
            if eff_type == "shot_reverse_shot":
                # Consecutive reverse shots in a scene alternate
                # viewpoints: False, True, False, ... by SRS order.
                srs_side: bool | None = (srs_count % 2 == 1)
                srs_count += 1
            else:
                srs_side = None
            first_ordinal = line_index.get(shot_line_ids[0]) \
                if shot_line_ids else None
            camera_text = _text_value(sh.get("camera"))
            shot_directives.append({
                "scene": number,
                "line_index": first_ordinal,
                "shot_type": eff_type,
                "camera_angle": map_camera_angle(camera_text, eff_type),
                "camera_movement": eff_move,
                "subject": subject,
                "counterpart": counterpart,
                "srs_side": srs_side,
                "shot_id": shot_id,
                "camera": camera_text,
                "camera_movement_text": _text_value(
                    sh.get("camera_movement_text")),
                "location_override": sh.get("location_override"),
                "trigger": sh.get("trigger") or None,
            })
        # Scene-default directive (only with explicit camera info).
        scene_camera = _text_value(sc.get("camera"))
        scene_move_raw = str(sc.get("camera_movement") or "STATIC").strip()
        if scene_camera or scene_move_raw != "STATIC":
            if scene_move_raw in CAMERA_MOVEMENTS:
                scene_move = scene_move_raw
            else:
                scene_move, _note = map_camera_movement_text(scene_move_raw)
            shot_directives.append({
                "scene": number,
                "line_index": None,
                "shot_type": "medium",
                "camera_angle": map_camera_angle(scene_camera, "medium"),
                "camera_movement": scene_move,
                "subject": "",
                "counterpart": None,
                "srs_side": None,
                "shot_id": None,
                "camera": scene_camera,
                "camera_movement_text": "",
                "location_override": None,
                "trigger": None,
            })

    # --- Props -------------------------------------------------------
    taken_ids: set[str] = set()
    package_props: list[dict] = []
    for prop in props_data:
        fields = prop.get("fields") if isinstance(
            prop.get("fields"), dict) else {}
        description = prop.get("description") or " ".join(p for p in (
            _field_text(fields, "TYPE"), _field_text(fields, "COLOR"),
            _field_text(fields, "MATERIAL")) if p)
        kind = derive_prop_kind(
            prop.get("name", ""),
            " ".join(p for p in (description,
                                 _field_text(fields, "TYPE")) if p))
        package_props.append({
            "id": _prop_id(prop.get("name", ""), taken_ids),
            "name": prop.get("name", ""),
            "kind": kind,
            "owner": prop.get("owner") or "",
            "description": description,
            "fields": dict(fields),
        })
    for pos, scene in enumerate(package_scenes):
        scene_number = scene["number"]
        relevant = []
        for entry, raw in zip(package_props, props_data):
            if _prop_relevant(raw, entry["kind"], scene_number,
                              scene_person_norms[pos],
                              scene_texts_norm[pos], char_display):
                relevant.append(entry["id"])
        scene["props"] = relevant

    # --- Trait blocks (SPEC section 15) ------------------------------
    dropped_notes: list[str] = []
    char_map: dict[str, str] = {}
    for char in declared:
        identity = char.get("identity_id") or char.get("name", "")
        for key in (char.get("name"), char.get("identity_id"),
                    char.get("id")):
            if key:
                char_map[_norm_text(str(key))] = identity
    directives, action_unmapped = derive_action_directives(
        action_items, char_map)
    sfx_events, music_events, unmapped_cues, audio_dropped = \
        derive_audio_blocks(trait_audio_cues)
    dropped_notes.extend(audio_dropped)

    character_blocks = []
    for context in trait_context:
        char = context["char"]
        fields = context["fields"]
        name = char.get("name", "")
        identity = char.get("identity_id") or name
        costume_changes = [dict(c)
                           for c in (char.get("costume_changes") or [])]
        covered = {c.get("scene_number") for c in costume_changes}
        for pos, sc in enumerate(scenes_data):
            scene_number = package_scenes[pos]["number"]
            if scene_number in covered:
                continue
            scene_costume = str(sc.get("costume") or "").strip().upper()
            outfit_list = None
            if scene_costume in ("CIVILIAN", "CIVIL"):
                outfit_list = _field_value(fields, "COSTUME_CIVILIAN")
            elif scene_costume in ("MILITARY",):
                outfit_list = _field_value(fields, "COSTUME_MILITARY")
            if outfit_list is None:
                continue
            outfit = _text_value(outfit_list)
            if not outfit:
                continue
            costume_changes.append({
                "scene_number": scene_number,
                "outfit": outfit,
                "line": sc.get("line") or 0,
            })
            covered.add(scene_number)
        character_blocks.append(build_character_trait_block(
            identity_id=identity, name=name,
            role=char.get("role", "") or "",
            appearance=char.get("appearance", "") or "",
            traits=char.get("traits") or [],
            costume=char.get("costume", "") or "",
            costume_changes=costume_changes,
            voice=char.get("voice", "AUTO"),
            voice_style=char.get("voice_style", "") or "",
            voice_id=context["voice_id"],
            head_ratio=char.get("head_ratio", HEAD_RATIO_LOCKED),
            render_traits=context["render_traits"],
            actions=[d for d in directives
                     if d.get("char") == identity],
            dropped_notes=dropped_notes))

    location_blocks = []
    for loc_pos, loc in enumerate(locations):
        referencing = [pos for pos, idx in enumerate(scene_loc_index)
                       if idx == loc_pos]
        first_scene = scenes_data[referencing[0]] if referencing else None
        loc_fields = loc.get("fields") if isinstance(
            loc.get("fields"), dict) else {}
        time_text = ""
        mood_text = ""
        setting_text = ""
        if first_scene is not None:
            time_text = first_scene.get("time_of_day") or ""
            mood_text = first_scene.get("mood") or ""
            setting_text = package_scenes[referencing[0]]["setting"]
        if not time_text:
            time_text = _field_text(loc_fields, "TIME_OF_DAY")
        if not mood_text:
            mood_text = _field_text(loc_fields, "MOOD")
        traits = derive_location_traits(
            name=_text_value(loc.get("name")),
            geography=_text_value(loc.get("geography")),
            architecture=_text_value(loc.get("architecture")),
            features=loc.get("features"),
            inline_text=setting_text or _text_value(loc.get("name")),
            time_of_day_text=time_text, mood_text=mood_text)
        location_blocks.append(build_location_trait_block(
            location_id=loc.get("id") or loc.get("name") or f"location_{loc_pos}",
            scene_numbers=[package_scenes[pos]["number"]
                           for pos in referencing],
            name=_text_value(loc.get("name")),
            period=_text_value(loc.get("period")),
            geography=_text_value(loc.get("geography")),
            architecture=_text_value(loc.get("architecture")),
            features=loc.get("features") or [],
            foreground=_text_value(loc.get("foreground")),
            midground=_text_value(loc.get("midground")),
            background=_text_value(loc.get("background")),
            lighting=_text_value(loc.get("lighting")),
            weather=_text_value(loc.get("weather")),
            palette=loc.get("palette") or [],
            forbidden=loc.get("forbidden") or [],
            render_traits=traits))
    for pos, scene in enumerate(package_scenes):
        idx = scene_loc_index[pos]
        scene["location"]["v1_location"] = (
            location_blocks[idx] if idx is not None else None)

    trait_blocks = build_trait_blocks(
        snapshot_hash=data.get("snapshot_hash") or "",
        planner=ADAPTER_LABEL, model=None, usage=None,
        reason="deterministic V1 adapter; no Gemini enrichment",
        characters=character_blocks, locations=location_blocks,
        sfx=sfx_events, music=music_events,
        unmapped_cues=unmapped_cues, actions=directives,
        unmapped=action_unmapped + expression_unmapped,
        dropped=dropped_notes)

    hook = all_lines[0].get("text", "")
    twist = all_lines[-1].get("text", "")

    package = {
        "characters": cast,
        "locations": setting_strings,
        "scenes": package_scenes,
        "shots": shots,
        # No estimated SFX timestamps: V1 cues carry triggers, and
        # inventing timestamps is forbidden. Full cues are preserved
        # in v1_audio_cues / per-scene v1_scene; section 15.4 blocks
        # live in trait_blocks.
        "audio_events": [],
        "hook": hook,
        "twist": twist,
        "gemini_shots": gemini_shots,
        "props": package_props,
        "shot_directives": shot_directives,
        "trait_blocks": trait_blocks,
        "end_hold_sec": _end_hold_sec(data, scenes_data),
        # --- Preserved V1 data (namespaced; never discarded) -------
        "v1_format": "studio_script_v1",
        "v1_snapshot_hash": data.get("snapshot_hash") or "",
        "v1_meta": data.get("meta") or {},
        "v1_characters": declared,
        "v1_locations": locations,
        "v1_props": props_data,
        "v1_constraints": data.get("constraints") or [],
        "v1_qa": data.get("qa") or {},
        "v1_output": data.get("output") or {},
        "v1_global_audio": data.get("global_audio") or {},
        "v1_end_card": _end_card_with_duration(data.get("end_card")),
        "v1_narrator": narrator_entries,
        "v1_extras": extra_entries,
        "v1_first_person": first_person,
        "v1_notes": v1_notes,
        "v1_audio_cues": audio_cues,
        "v1_unsupported_fields": data.get("unsupported_fields") or [],
        "v1_dropped_cues": dropped_cues,
        "v1_shot_notes": shot_notes,
    }
    context = {
        "data": data,
        "declared": declared,
        "locations": locations,
        "scene_loc_index": scene_loc_index,
        "char_display": char_display,
        "char_identity": char_identity,
        "line_index": line_index,
        "real_scenes": {s["number"] for s in package_scenes},
        "cast_by_name": {c["name"]: c for c in cast},
        "trait_block_by_identity": {
            b["identity_id"]: b for b in character_blocks},
        "trait_block_by_location": {
            b["location_id"]: b for b in location_blocks},
    }
    return package, context


def _expression_targets(character, spoken: list[dict], char_display: dict,
                        first_person: dict, primary_display: str) -> list[str]:
    """Line ids in a scene governed by a scene-level expression.

    Bare expressions (character None) govern all lines; prefixed ones
    govern only the named character's lines.
    """
    if character is None:
        return [ln.get("line_id") for ln in spoken if ln.get("line_id")]
    norm = _normalize_name(str(character))
    wanted = char_display.get(norm)
    if wanted is None and norm in NARRATOR_ALIASES:
        wanted = "narrator" if not first_person["enabled"] else primary_display
    if wanted is None:
        wanted = str(character)
    targets = []
    for ln in spoken:
        speaker = _package_speaker(
            ln.get("speaker", ""), first_person, primary_display)
        if speaker == wanted or _normalize_name(
                ln.get("speaker", "")) == norm:
            targets.append(ln.get("line_id"))
    return [t for t in targets if t]


def _line_speaker_matches(line_id: str, spoken: list[dict], wanted,
                          first_person: dict, primary_display: str) -> bool:
    for ln in spoken:
        if ln.get("line_id") == line_id:
            speaker = _package_speaker(
                ln.get("speaker", ""), first_person, primary_display)
            return speaker == wanted
    return False


def adapt_document(doc: StudioScriptV1Document) -> dict:
    """Map a parsed STUDIO SCRIPT V1 document to a scene package.

    Raises V1AdapterError when the document is invalid or has no
    spoken lines. Pure and deterministic.
    """
    package, _context = _adapt_document(doc)
    return package


# --- Gemini enrichment (optional, cached) ------------------------------

def _v1_gemini_prompt(data: dict) -> str:
    """Enrichment prompt: the parsed document is ground truth; the
    model returns section 15 trait shapes only."""
    chars = "\n".join(
        f"- {c.get('identity_id') or c.get('name')}: {c.get('name')} | "
        f"role: {c.get('role', '')} | appearance: {c.get('appearance', '')} | "
        f"traits: {'; '.join(c.get('traits') or [])} | "
        f"costume: {c.get('costume', '')}"
        for c in (data.get("characters") or []))
    locs = "\n".join(
        f"- {loc.get('id')}: {loc.get('name', '')} | "
        f"features: {'; '.join(loc.get('features') or [])} | "
        f"foreground: {loc.get('foreground', '')} | "
        f"midground: {loc.get('midground', '')} | "
        f"background: {loc.get('background', '')}"
        for loc in (data.get("locations") or []))
    scenes = "\n".join(
        f"- scene {sc.get('number')}: {sc.get('title', '')} | "
        f"location: {sc.get('location_text') or sc.get('location_ref') or ''} | "
        f"time: {sc.get('time_of_day', '')} | mood: {sc.get('mood', '')}"
        for sc in (data.get("scenes") or []))
    lines = []
    for sc in (data.get("scenes") or []):
        for ln in (sc.get("spoken_lines") or []):
            lines.append(
                f"{ln.get('line_id')}. [{ln.get('speaker')}|"
                f"{ln.get('kind')}] {ln.get('text')}")
    cues = []
    for sc in (data.get("scenes") or []):
        for cue in (sc.get("audio_cues") or []):
            cues.append(
                f"- scene {cue.get('scene_number')} {cue.get('cue_type')}: "
                f"{cue.get('name')} (trigger: {cue.get('trigger', '')})")
    return (
        "Bạn là họa sĩ phác thảo đặc trưng cho công cụ làm video hoạt hình "
        "(người que đầu to, nét đậm, 16:9). Kịch bản đã phân tích dưới đây là "
        "GROUND TRUTH. Chỉ trả về JSON hợp lệ, không giải thích, không markdown, "
        "theo đúng schema này:\n"
        '{"characters": [{"name": "tên nhân vật đúng như danh sách", '
        '"identity_id": "id đúng như danh sách", '
        '"render_traits": {"description": "mô tả ngắn gọn", '
        '"voice_hint": "giọng nam" hoặc "giọng nữ" hoặc "giọng kể", '
        '"template": "male" hoặc "female" hoặc "child" hoặc "elderly", '
        '"body_variant": "slim" hoặc "standard" hoặc "sturdy", '
        '"costume": "none" hoặc "dress" hoặc "uniform", '
        '"hair_style": "short" hoặc "long" hoặc "tuft" hoặc "side_part" hoặc "none", '
        '"hat": "none" hoặc "bowler", '
        '"moustache_style": "none" hoặc "toothbrush" hoặc "handlebar" hoặc "full", '
        '"glasses": true/false, "jacket_color": "#RRGGBB"}}], '
        '"locations": [{"location_id": "id đúng như danh sách", '
        '"render_traits": {"setting": "mô tả ngắn gọn", '
        '"location_keyword": "great_wall" hoặc "eiffel_tower" hoặc "rainy_street" '
        'hoặc "street" hoặc "generic", "mood": "warm" hoặc "cold", '
        '"time_of_day": "day" hoặc "night"}}], '
        '"shots": [{"scene": 1, "line_index": 1, '
        '"shot_type": "establishing" hoặc "medium" hoặc "close_up" hoặc '
        '"extreme_close_up" hoặc "over_the_shoulder" hoặc "reaction" hoặc '
        '"object_insert" hoặc "tracking" hoặc "shot_reverse_shot" hoặc '
        '"medium_close_up" hoặc "graphic_insert", '
        '"purpose": "ngắn gọn"}], '
        '"sfx": [{"event": "rain_start" hoặc "foot_contact" hoặc "door_contact" '
        'hoặc "door_rotation" hoặc "paper_movement" hoặc "object_impact" hoặc '
        '"character_reaction", "scene": 1, "note": "ngắn gọn"}], '
        '"music": [{"name": "tên nhạc", "scene": 1, '
        '"intensity": "LOW" hoặc "MEDIUM" hoặc "HIGH", "note": "ngắn gọn"}], '
        '"actions": [{"type": "walk_to" hoặc "run_to" hoặc "turn_to" hoặc '
        '"look_at" hoặc "point_at" hoặc "wave" hoặc "reach_to" hoặc "give_to" '
        'hoặc "shrug" hoặc "cover_face" hoặc "nod" hoặc "sit_down" hoặc '
        '"stand_up" hoặc "idle" hoặc "bend_pick" hoặc "kneel_pick", '
        '"char": "identity_id của nhân vật", "scene": 1, '
        '"note": "ngắn gọn"}]}.\n'
        "QUY TẮC: chỉ dùng nhân vật, địa điểm, cảnh và cue có trong tài liệu "
        "dưới đây, không bịa thêm. head_ratio luôn là 0.34, không bao giờ trả "
        "về giá trị khác. KHÔNG đưa thời gian ước tính. Nhạc KHÔNG dùng tên "
        "sự kiện SFX. Hành động CHỈ dùng 16 tên nguyên thủy đã liệt kê.\n\n"
        f"NHÂN VẬT:\n{chars}\n\nĐỊA ĐIỂM:\n{locs}\n\nCẢNH:\n{scenes}\n\n"
        f"LỜI THOẠI:\n" + "\n".join(lines) + "\n\nCUE ÂM THANH:\n"
        + "\n".join(cues) + "\n"
    )


def _parse_enrichment_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    enrichment = json.loads(text)
    if not isinstance(enrichment, dict):
        raise ValueError("Gemini returned non-object JSON")
    return enrichment


def _apply_enrichment(package: dict, cleaned: dict, model: str,
                      usage: dict | None, context: dict,
                      dropped: list[str]) -> None:
    """Overlay validated Gemini enrichment onto a V1 package.

    Ground truth = the parsed document. Model characters/locations
    that do not match declared identities are dropped with notes;
    model SFX/music entries only enrich scripted cues in the same
    scene (unmatched entries are dropped, never invented as new
    cues); model actions replace the deterministic directives only
    when at least one survives validation. Verbatim hook/twist lines
    are never overwritten.
    """
    trait_blocks = package["trait_blocks"]
    char_display = context["char_display"]
    char_identity = context["char_identity"]
    real_scenes = context["real_scenes"]

    # Characters: overlay render traits on trait blocks + cast.
    for g in cleaned["characters"]:
        key = _normalize_name(g.get("identity_id") or g["name"])
        identity = char_identity.get(key) or char_identity.get(
            _normalize_name(g["name"]))
        if identity is None:
            dropped.append(
                f"character {g['name']!r} is not declared in the "
                "script; dropped")
            continue
        block = context["trait_block_by_identity"].get(identity)
        if block is None:
            dropped.append(
                f"character {g['name']!r} has no trait block; dropped")
            continue
        merged = dict(block["render_traits"])
        merged.update(g["render_traits"])
        block["render_traits"] = merged
        display = char_display.get(key) or g["name"]
        cast_entry = context["cast_by_name"].get(display)
        if cast_entry is not None:
            cast_entry["render_traits"] = dict(merged)
            cast_entry["description"] = merged["description"]
            cast_entry["voice_hint"] = merged["voice_hint"]
            cast_entry["jacket_color"] = merged["jacket_color"]
            for trait_key in ("template", "body_variant", "costume",
                              "hair_style", "hat", "moustache_style",
                              "glasses"):
                cast_entry[trait_key] = merged[trait_key]

    # Locations: overlay render traits on trait blocks + scene dicts.
    scene_loc_index = context["scene_loc_index"]
    for loc in cleaned["locations"]:
        block = None
        if loc.get("location_id"):
            block = context["trait_block_by_location"].get(
                loc["location_id"])
            if block is None:
                for candidate in trait_blocks["locations"]:
                    if _normalize_name(candidate["location_id"]) == \
                            _normalize_name(loc["location_id"]):
                        block = candidate
                        break
        scene_no = loc.get("scene")
        if block is None and scene_no in real_scenes:
            for pos, scene in enumerate(package["scenes"]):
                if scene["number"] == scene_no \
                        and scene_loc_index[pos] is not None:
                    block = trait_blocks["locations"][scene_loc_index[pos]]
                    break
        if block is None:
            dropped.append(
                "location enrichment names no declared location or "
                "real scene; dropped")
            continue
        merged = dict(block["render_traits"])
        merged.update(loc["render_traits"])
        block["render_traits"] = merged
        for scene_no in block["scene_numbers"]:
            for scene in package["scenes"]:
                if scene["number"] == scene_no:
                    for trait_key in ("setting", "location_keyword",
                                      "mood", "time_of_day"):
                        scene["location"][trait_key] = merged[trait_key]

    # Shots: append model shots not already covered by SHOT blocks.
    covered = {(s["scene"], s["line_index"])
               for s in package["gemini_shots"]}
    n_lines = sum(len(s["lines"]) for s in package["scenes"])
    for shot in cleaned["shots"]:
        if not 1 <= shot["line_index"] <= n_lines:
            dropped.append(
                f"shot for line_index {shot['line_index']} is not a "
                "real line; dropped")
            continue
        if shot["scene"] not in real_scenes:
            dropped.append(
                f"shot for scene {shot['scene']} is not a real scene; "
                "dropped")
            continue
        if (shot["scene"], shot["line_index"]) in covered:
            continue
        covered.add((shot["scene"], shot["line_index"]))
        package["gemini_shots"].append(shot)

    # Audio: model events enrich scripted cues in the same scene.
    audio = trait_blocks["audio"]
    unmapped = list(audio["unmapped_cues"])
    sfx_events = list(audio["sfx"])
    for entry in cleaned["sfx"]:
        target = None
        for cue in unmapped:
            if cue["cue_type"] == "SFX" \
                    and cue["scene_number"] == entry["scene"]:
                target = cue
                break
        if target is None:
            dropped.append(
                f"sfx event {entry['event']!r} for scene "
                f"{entry['scene']} matches no unmapped scripted SFX "
                "cue; dropped")
            continue
        unmapped.remove(target)
        sfx_events.append({
            "cue_type": "SFX", "name": target["name"],
            "trigger": target.get("trigger", ""),
            "priority": "REQUIRED",
            "scene_number": target["scene_number"],
            "shot_id": target.get("shot_id"), "line": target.get("line", 0),
            "source_key": "SFX", "event": entry["event"],
            "note": f"Gemini-mapped: {entry.get('note', '')}".strip(),
        })
    sfx_events.sort(key=lambda e: (e["scene_number"], e["line"]))
    music_events = list(audio["music"])
    for entry in cleaned["music"]:
        target = None
        for event in music_events:
            if event["scene_number"] == entry["scene"] \
                    and not event.get("_gemini_enriched"):
                target = event
                break
        if target is None:
            dropped.append(
                f"music event {entry['name']!r} for scene "
                f"{entry['scene']} matches no scripted BGM cue; "
                "dropped")
            continue
        if entry.get("intensity"):
            target["intensity"] = entry["intensity"]
        if entry.get("note"):
            target["note"] = entry["note"]
        target["_gemini_enriched"] = True
    for event in music_events:
        event.pop("_gemini_enriched", None)
    audio["sfx"] = sfx_events
    audio["music"] = music_events
    audio["unmapped_cues"] = unmapped

    # Actions: model directives replace deterministic ones when any
    # survive; per-character actions partition by identity.
    model_actions = list(cleaned["actions"])
    for g in cleaned["characters"]:
        key = _normalize_name(g.get("identity_id") or g["name"])
        identity = char_identity.get(key) or char_identity.get(
            _normalize_name(g["name"]))
        for directive in (g.get("actions") or []):
            directive = dict(directive)
            directive.setdefault("char", identity)
            model_actions.append(directive)
    kept_actions = []
    for directive in model_actions:
        char = directive.get("char")
        if char is not None:
            identity = char_identity.get(_normalize_name(str(char)))
            if identity is None and char not in char_display.values():
                dropped.append(
                    f"action for character {char!r} is not declared "
                    "in the script; dropped")
                continue
            directive = dict(directive)
            directive["char"] = identity or char
        kept_actions.append(build_action_directive(
            type=directive["type"],
            char=directive.get("char"),
            duration=directive.get("duration", 1.5),
            scene_number=directive.get("scene_number"),
            shot_id=directive.get("shot_id"),
            source_line=directive.get("source_line"),
            action_text=directive.get("action_text", ""),
            **{k: v for k, v in directive.items()
               if k in ("other", "start", "from_x", "to_x", "ground_y",
                        "target", "angle_keys", "facing", "freq", "amp",
                        "hand", "note")}))
    if kept_actions:
        trait_blocks["actions"] = kept_actions
        for block in trait_blocks["characters"]:
            block["actions"] = [
                a for a in kept_actions
                if a.get("char") == block["identity_id"]]

    trait_blocks["planner"] = "gemini"
    trait_blocks["model"] = model
    trait_blocks["usage"] = usage
    trait_blocks["reason"] = None
    trait_blocks["dropped"] = list(trait_blocks.get("dropped", [])) + dropped


def resolve_v1_plan(script_text: str, *, enrich_with_gemini: bool = False,
                    gemini_client: GeminiClient | None = None
                    ) -> tuple[dict, str, str]:
    """Parse a STUDIO SCRIPT V1 script and adapt it to a scene package.

    Returns the same 3-tuple as gemini_planner.resolve_plan:
    (package, planner_label, planner_detail). The default label is
    "v1" -- never "gemini" (no Gemini call ran) and never "fallback"
    (this is not the free-form local planner).

    With ``enrich_with_gemini=True`` a real Gemini call enriches the
    trait blocks (label "gemini" on success; "v1" with the failure
    recorded in trait_blocks["reason"] when the call fails). The
    result is cached per snapshot hash within the process, so repeat
    plans of the same script agree exactly. ``gemini_client`` injects
    the client (tests use a fake helper; production uses the
    connector helper / env key default).

    Raises V1AdapterError when the text is not a V1 document, when
    the document is invalid, or when it has no spoken lines.
    """
    if detect_format(script_text) != "studio_v1":
        raise V1AdapterError(
            "not a STUDIO SCRIPT V1 document: expected the "
            "'# STUDIO SCRIPT V1' marker or a PROJECT: + SCENE n: "
            "structure")
    doc = parse_studio_script_v1(script_text)
    package, context = _adapt_document(doc)
    n_lines = sum(len(s["lines"]) for s in package["scenes"])
    base_detail = (
        f"STUDIO SCRIPT V1: {len(package['scenes'])} scenes, "
        f"{len(package['characters'])} characters, {n_lines} spoken "
        f"lines; deterministic V1 adapter, no Gemini enrichment")
    if not enrich_with_gemini:
        return package, ADAPTER_LABEL, base_detail
    snapshot = package["v1_snapshot_hash"]
    cached = _ENRICHMENT_CACHE.get(snapshot)
    if cached is not None:
        if cached["failed"]:
            package["trait_blocks"]["reason"] = cached["reason"]
            return package, ADAPTER_LABEL, (
                base_detail + "; Gemini enrichment failed: "
                + cached["short_reason"])
        return (copy.deepcopy(cached["package"]), cached["label"],
                cached["detail"])
    client = gemini_client or GeminiClient()
    prompt = _v1_gemini_prompt(context["data"])
    last_error = ""
    for model in _ENRICHMENT_MODELS:
        try:
            raw, usage, used = client.generate_json(
                prompt, model=model, max_tokens=_ENRICHMENT_MAX_TOKENS)
            enrichment = _parse_enrichment_json(raw)
            cleaned, dropped = validate_trait_blocks(enrichment)
            _apply_enrichment(package, cleaned, used, usage, context,
                              dropped)
            tokens = (usage or {}).get("total_tokens") or 0
            token_note = f", {tokens} tokens" if tokens else ""
            detail = (
                f"STUDIO SCRIPT V1: {len(package['scenes'])} scenes, "
                f"{len(package['characters'])} characters, {n_lines} "
                f"spoken lines; Gemini {used} enrichment{token_note}")
            _cache_enrichment(snapshot, {
                "failed": False, "package": copy.deepcopy(package),
                "label": "gemini", "detail": detail})
            return package, "gemini", detail
        except RateLimitedError as exc:
            last_error = str(exc)[:200]
            break
        except NoGeminiAvailable as exc:
            last_error = str(exc)[:200]
            break
        except (GeminiError, ValueError) as exc:
            last_error = str(exc)[:200]
            continue
    reason = (f"Gemini enrichment failed ({last_error}); deterministic "
              "derivation used")
    package["trait_blocks"]["reason"] = reason
    _cache_enrichment(snapshot, {
        "failed": True, "reason": reason, "short_reason": last_error})
    return package, ADAPTER_LABEL, (
        base_detail + f"; Gemini enrichment failed: {last_error}")
