"""Data-driven product renderer (shared engine).

Renders ANY scene package produced by the product pipeline — no
per-story code, no story names, no hardcoded character/scene/shot
lists. The package (characters, scenes, shots, action cues) drives
everything: character identity is mapped from the package's
description/voice_hint fields, the location from the scene's
``location_keyword``/setting text, the shots from the package's
shots + the camera planner, and the motion from the action cues.

Engine pieces consumed through their public APIs only (the v8
animation agent owns the engine files; this module never edits
them):
- animation.character_art: make_character / make_character_instance /
  draw_character_v4 / resolve_view
- animation.primitives: walk_to / run_to / kneel_pick / give_to /
  wave / idle / nod / standing / snapshot / apply_snapshot
- animation.rig: plant_feet, check_bone_lengths, smoothstep, lerp
- animation.landmarks: landmark_boxes (great_wall, eiffel_tower)
- renderer25d: Scene25D / Box3D / CharacterAnchor /
  PerspectiveCamera / render_frame
- camera_planner: anchor_focus_for_shot / apply_camera_anchored
  (D2 frozen crop, one per shot from standing boxes) +
  static_directive_for_shot / validation_for_camera
- subtitles: split_subtitle / phrase_windows / draw_phrase

Renderer: frame-by-frame PIL renderer (the code renderer). Motion
Canvas / Three.js is NOT used here: on this VM Chrome cannot launch
(detect_chrome() returns None — Hatch WebGL policy), so the product
falls back to this renderer and says so in every report. On Mai's
Windows machine the Motion Canvas path can be re-enabled by
implementing render_fn there; the frame output contract (PNG frames
+ motion report) is the same.

Frame pipeline per shot (CUT between shots, per the RicksClips
reference — locomotion inserts are cut, never blended):
  pose characters with the shot's primitives -> render_frame
  (2.5D scene: sky, ground, boxes far-to-near, contact shadows,
  character anchors) -> rain overlay if the scene is rainy ->
  prop drawn at the real hand/prop position -> 2D camera crop
  (safe_frame) -> subtitles drawn last at fixed 64 px.
Shots render in parallel (multiprocessing, one worker per shot;
shots are independent because every boundary is a cut). If the
pool fails, rendering falls back to sequential and logs the reason.
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import random
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .animation.character_art import (
    EXPRESSION_NAMES, EXPRESSIONS, LEGACY_MOOD_TO_EXPRESSION, VIEWS,
    draw_character_v4, draw_grip_fingers, make_character,
    make_character_instance, resolve_view,
)
from .animation.landmarks import landmark_boxes
from .animation.locomotion import footfall_times
from .animation.scene_packages import register_scene_package
from .animation.primitives import (
    PRIMITIVES, bend_pick, breathe, carry_bag, close_wallet, cover_face,
    give_to, hand_over, head_tilt, hold_pen, idle, kneel_pick, look_at_point,
    nod, open_wallet, pen_tip_position, pick_up, point_at, put_away,
    raise_hand, reach_to,
    react_event, run_to, shrug, sign_document, sit_at_desk, sit_down,
    stand_from_chair, stand_up, standing, turn_to, walk_mud, walk_to, wave,
    write_on_paper,
)
from .animation.rig import (
    EAR_SHAPES, FACE_MARKING_STYLES, HORN_SHAPES, TAIL_SHAPES,
    check_bone_lengths, lerp, smoothstep,
)
from .expression_library import (
    blink_envelope, gaze_for_target, interpret as interpret_expression,
    interpret_params as interpret_expression_params,
    speech_mouth_envelope,
)
from .camera_planner import (
    ANGLES, CAMERA_MOVEMENT, FULL_BODY_SHOT_TYPES,
    SHOT_TYPES as CAMERA_SHOT_TYPES, SHOT_SCALE as CAMERA_SHOT_SCALE,
    CameraPlanner, anchor_focus_for_shot, apply_camera_anchored,
    build_camera_accounting, normalize_movement,
    resolve_viewpoint_angle, static_directive_for_shot,
    validation_for_camera, viewpoint_for_shot,
)
from .renderer25d.camera import PerspectiveCamera
from .renderer25d.render import render_boxes_layer, render_frame
from .renderer25d.scene import Box3D, CharacterAnchor, Scene25D
from .lighting import (MATERIAL_CATALOG, light_for, paint_energy_glow,
                       shadow_ellipse_spec)
from .environment_v2 import (
    build_environment, fit_foreground_to_frustum, render_environment,
    select_archetype, to_box_dicts,
)
from .map_renderer import MapSpecError, render_map
from .prop_system import (
    PropStateMachine, SemanticPropTracker, geometry_for_prop)
from .semantic_contracts import PropLocation
from .planner_fallback import ACTION_LEAD_SECONDS
from .subtitles import draw_phrase, phrase_windows, split_subtitle

W, H = 1920, 1080
FPS = 24
WORLD_Z = 0.5
CAM = PerspectiveCamera(position=(0.0, 2.0, 4.8), target=(0.0, 1.2, 0.0))
ANCHOR_HEIGHT = 2.7
_fx, GROUND_Y, _, _ = CAM.project((0.0, 0.0, WORLD_Z), W, H)
_hx, _hy, _, _ = CAM.project((0.0, ANCHOR_HEIGHT, WORLD_Z), W, H)
CHAR_H = int(round(GROUND_Y - _hy))  # ~783 px on screen
GROUND_Y = int(round(GROUND_Y))

# Deterministic staging slots (world x) by character index.
STAGING_X = (-1.6, 1.2, 2.6, -3.0, 0.0)
PALETTE = ("#2E5FA3", "#47BD75", "#D9A441", "#7A4A2B", "#6B5B95")
RAIN_COLOR = (205, 215, 235)
RAIN_N = 44
PROP_FILL = (138, 90, 43)
INK_RGB = (20, 34, 43)

SHOT_SCALE = {
    "establishing": 1.0, "medium": 1.6, "close_up": 2.6,
    "reaction": 2.6, "object_insert": 3.4, "tracking": 1.6,
    "medium_close_up": 1.6, "graphic_insert": 1.0,
}

# F7 (Stage 3): the general prop vocabulary. Every drawable prop kind
# has a distinct simple 2D shape in _draw_prop (same line language,
# INK outline): the original 12 keep their hand-drawn shapes
# (pixel-pinned), the 13 geometry kinds draw from the semantic
# geometry specs (prop_system.geometry_for_prop). Unknown kinds
# render as "generic". The adapter's kind set is asserted equal to
# this constant by a sync test — keep the name PROP_KINDS and keep
# this the single source of truth.
PROP_KINDS = frozenset({
    "wallet", "umbrella", "newspaper", "letter", "ticket", "cup",
    "bag", "key", "book", "flower", "pen", "generic",
    "bolt", "hammer", "trident", "helmet", "sword", "staff",
    "shield", "crown", "ring", "hat", "chain", "stone", "boulder",
})

# Kinds drawn from semantic geometry specs (wiring item 7). The 7
# kinds with BOTH a legacy shape and a geometry builder (wallet,
# letter, pen, bag, cup, key, book) keep their legacy shapes here;
# the geometry builders serve the 3D path and proofs.
_GEOMETRY_PROP_KINDS = frozenset({
    "bolt", "hammer", "trident", "helmet", "sword", "staff",
    "shield", "crown", "ring", "hat", "chain", "stone", "boulder",
})

# Generic keyword -> prop kind, for packages whose prop entries carry
# no explicit kind (name/description text only). Word-boundary
# matching, Vietnamese + English, no story values.
_PROP_KIND_KEYWORDS = (
    # Mythological / restraint kinds first (same order + vocabulary
    # as trait_derivation.PROP_KEYWORDS, so both inferences agree):
    # helmet before hat, boulder before stone.
    (("tia chớp", "tia sét", "lightning bolt", "lightning",
      "bolt", "sét"), "bolt"),
    (("búa", "hammer", "mallet"), "hammer"),
    (("đinh ba", "trident"), "trident"),
    (("mũ tàng hình", "mũ sắt", "mũ giáp", "helmet"), "helmet"),
    (("kiếm", "sword"), "sword"),
    (("khiên", "shield"), "shield"),
    (("vương miện", "crown"), "crown"),
    (("nhẫn", "ring"), "ring"),
    (("quyền trượng", "gậy", "scepter", "staff"), "staff"),
    (("dây xích", "xích", "chain", "shackle"), "chain"),
    (("tảng đá", "boulder", "mountain rock", "giant rock"),
     "boulder"),
    (("hòn đá", "viên đá", "đá", "stone", "rock", "pebble"),
     "stone"),
    (("mũ", "nón", "hat", "cap"), "hat"),
    (("wallet", "ví", "bóp"), "wallet"),
    (("umbrella", "ô dù", "cây dù", "dù"), "umbrella"),
    (("newspaper", "báo", "tờ báo", "xấp báo"), "newspaper"),
    (("letter", "thư", "lá thư", "đơn", "tờ đơn", "document",
      "envelope", "phong bì"), "letter"),
    (("ticket", "vé"), "ticket"),
    (("cup", "cốc", "ly", "tách"), "cup"),
    (("bag", "túi", "cặp", "balo", "ba lô", "valise",
      "suitcase"), "bag"),
    (("key", "chìa", "chìa khóa"), "key"),
    (("book", "sách", "quyển sách", "cuốn sách"), "book"),
    (("flower", "hoa", "bó hoa"), "flower"),
    (("pen", "bút", "cây bút", "ngòi bút"), "pen"),
)


def infer_prop_kind(prop: dict) -> str:
    """A prop entry's drawable kind: its explicit ``kind`` when it is
    in PROP_KINDS, else a keyword inference from its name/description,
    else "generic". Never raises on missing fields."""
    kind = str((prop or {}).get("kind", "") or "").strip().lower()
    if kind in PROP_KINDS:
        return kind
    text = " ".join(str((prop or {}).get(k, "") or "")
                    for k in ("name", "description", "type")).lower()
    # IDs use underscores ("PROP_WALLET"); word boundaries treat "_"
    # as a word character, so normalise them to spaces first.
    text = text.replace("_", " ")
    for keywords, want in _PROP_KIND_KEYWORDS:
        if _has_any_word(text, keywords):
            return want
    return "generic"


def _parse_seconds(value, default=None):
    """A duration value -> float seconds, or ``default``. Accepts
    numbers and numeric strings ("3", "3s", "1.0s"). The adapter owns
    duration parsing; this is tolerance, not a second parser."""
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if text.endswith("s"):
        text = text[:-1].strip()
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _normalize_camera_movement(value) -> str:
    """A directive/scene camera-movement value -> a CAMERA_MOVEMENT
    enum string. Enum spellings normalise directly; generic English
    movement phrases ("slow lateral tracking", "subtle dolly-in",
    "static cinematic framing") map to the closest enum member;
    anything else degrades to STATIC, never a crash."""
    norm = normalize_movement(value)
    if norm != "STATIC" or str(value or "").strip().lower() in (
            "static",):
        return norm
    text = re.sub(r"\s+",
                  " ", str(value or "").lower().replace("-", " ")
                  .replace("_", " ")).strip()
    for phrase, want in (
            ("pan left", "PAN_LEFT"), ("pan right", "PAN_RIGHT"),
            ("tilt up", "TILT_UP"), ("tilt down", "TILT_DOWN"),
            ("dolly in", "DOLLY_IN"), ("push in", "DOLLY_IN"),
            ("zoom in", "DOLLY_IN"), ("dolly out", "DOLLY_OUT"),
            ("pull back", "DOLLY_OUT"), ("zoom out", "DOLLY_OUT"),
            ("tracking", "TRACKING"), ("lateral", "TRACKING"),
            ("follow", "TRACKING"), ("crane up", "CRANE_UP"),
            ("crane down", "CRANE_DOWN"), ("handheld", "HANDHELD"),
            ("shake", "HANDHELD"), ("vibration", "HANDHELD"),
            ("zoom", "DOLLY_IN"), ("static", "STATIC")):
        if phrase in text:
            return want
    return "STATIC"


def _normalize_camera_angle(value):
    """A directive/scene camera-angle value -> an ANGLES vocabulary
    string, or None when absent/invalid (the renderer then falls back
    to the shot type's default angle). Never raises."""
    if not isinstance(value, str):
        return None
    angle = value.strip().lower().replace("-", "_").replace(" ", "_")
    return angle if angle in ANGLES else None


# Staging modes (Stage 3 / channel study R5): how characters share
# the frame. "layered_depth" stages depth layers + a foreground
# occlusion shape instead of shot-reverse-shot cutting; anything
# else (including absent) is the standard staging. Only the
# validated value is carried onto shots.
STAGING_MODES = ("layered_depth",)
OCCLUDER_SIDES = ("left", "right")
OCCLUDER_STYLES = ("solid", "blurred")


def _normalize_staging_mode(value):
    """A directive staging-mode value -> "layered_depth" or None."""
    if not isinstance(value, str):
        return None
    mode = value.strip().lower().replace("-", "_").replace(" ", "_")
    return mode if mode in STAGING_MODES else None


def _normalize_occluder_side(value):
    """A directive foreground-occluder side -> "left"/"right"/None."""
    if not isinstance(value, str):
        return None
    side = value.strip().lower()
    return side if side in OCCLUDER_SIDES else None


def _normalize_occluder_style(value):
    """A directive foreground-occluder style -> "solid"/"blurred"/None."""
    if not isinstance(value, str):
        return None
    style = value.strip().lower()
    return style if style in OCCLUDER_STYLES else None


def _normalize_character_view(value):
    """A directive character-view value -> a VIEWS string or None
    (the renderer then uses the default profile view, with turns
    still animating through front/three-quarter)."""
    if not isinstance(value, str):
        return None
    view = value.strip().lower().replace("-", "_").replace(" ", "_")
    return view if view in VIEWS else None


def _normalize_expression_name(value):
    """An expression label -> a canonical EXPRESSION_NAMES member
    (legacy mood spellings mapped), or None when invalid."""
    if not isinstance(value, str):
        return None
    name = value.strip().lower().replace("-", "_").replace(" ", "_")
    name = LEGACY_MOOD_TO_EXPRESSION.get(name, name)
    return name if name in EXPRESSION_NAMES else None


def _normalize_split_side(value):
    """One split-screen side spec -> {"expression": ...} /
    {"expressions": {name: ...}} with valid expression names only,
    or None when the side carries no usable override."""
    if not isinstance(value, dict):
        return None
    out = {}
    expr = _normalize_expression_name(value.get("expression"))
    if expr is not None:
        out["expression"] = expr
    exps = value.get("expressions")
    if isinstance(exps, dict):
        per_char = {}
        for name, label in exps.items():
            norm = _normalize_expression_name(label)
            if norm is not None:
                per_char[str(name)] = norm
        if per_char:
            out["expressions"] = per_char
    return out or None


def _normalize_split_screen(value):
    """A directive split-screen spec -> {"left": side, "right": side}
    with at least one usable expression override, or None. The two
    viewports share one camera/staging; only the face expression
    differs per side (the before/after mirror, channel study R10c)."""
    if not isinstance(value, dict):
        return None
    left = _normalize_split_side(value.get("left"))
    right = _normalize_split_side(value.get("right"))
    if left is None and right is None:
        return None
    out = {}
    if left is not None:
        out["left"] = left
    if right is not None:
        out["right"] = right
    return out


def _normalize_clock_time(value):
    """A "HH:MM" clock value -> (hour, minute), or None."""
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return (hour, minute)
    return None


def _normalize_insert_card(value):
    """A directive graphic-insert card spec -> a validated dict with
    only known keys (title, subtitle, lines, prop_kind, tally_count,
    clock_time, style), or None when the value is not a dict. An
    empty dict is valid: the card renders with the shot text as its
    title. Unknown/invalid fields are dropped, never a crash."""
    if not isinstance(value, dict):
        return None
    out = {}
    for key in ("title", "subtitle"):
        if value.get(key) is not None:
            out[key] = str(value[key])
    lines = value.get("lines")
    if isinstance(lines, (list, tuple)):
        kept = [str(line) for line in lines
                if str(line).strip()][:6]
        if kept:
            out["lines"] = kept
    kind = str(value.get("prop_kind") or "").strip().lower()
    if kind in PROP_KINDS:
        out["prop_kind"] = kind
    tally = value.get("tally_count")
    if isinstance(tally, bool):
        pass
    elif isinstance(tally, (int, float)):
        count = int(tally)
        if 0 < count <= 99:
            out["tally_count"] = count
    clock = _normalize_clock_time(value.get("clock_time"))
    if clock is not None:
        out["clock_time"] = "%02d:%02d" % clock
    style = str(value.get("style") or "").strip().lower()
    if style in ("paper", "dark"):
        out["style"] = style
    return out


def _location_block_index(package: dict) -> dict:
    """Location id -> trait block, from the package's location trait
    blocks (package["trait_blocks"]["locations"] first, then
    v1_locations). Keys: location_id, id, and normalised name."""
    index: dict[str, dict] = {}
    sources = []
    trait_blocks = package.get("trait_blocks")
    if isinstance(trait_blocks, dict):
        sources.append(trait_blocks.get("locations") or [])
    sources.append(package.get("v1_locations") or [])
    for source in sources:
        if not isinstance(source, (list, tuple)):
            continue
        for block in source:
            if not isinstance(block, dict):
                continue
            for key in (block.get("location_id"), block.get("id")):
                if key and str(key) not in index:
                    index[str(key)] = block
            name = block.get("name")
            if name:
                norm = " ".join(str(name).strip().lower().split())
                index.setdefault(norm, block)
    return index


def _resolve_location_block(package: dict, loc_id) -> dict | None:
    if loc_id is None:
        return None
    index = _location_block_index(package)
    if str(loc_id) in index:
        return index[str(loc_id)]
    norm = " ".join(str(loc_id).strip().lower().split())
    return index.get(norm)


def _block_location_text(block: dict) -> str:
    """Display/location text for a trait block: its name, else its
    inline text, else its render_traits setting."""
    if not isinstance(block, dict):
        return ""
    for key in ("name", "location_text"):
        if block.get(key):
            return str(block[key])
    traits = block.get("render_traits")
    if isinstance(traits, dict) and traits.get("setting"):
        return str(traits["setting"])
    return ""


def _block_location_fields(block: dict, fallback: dict) -> dict:
    """Shot location fields from a trait block: render_traits
    time_of_day/mood/location_keyword win, else the block's own
    fields, else the scene's fields (``fallback``)."""
    out = dict(fallback)
    if not isinstance(block, dict):
        return out
    traits = block.get("render_traits")
    if isinstance(traits, dict):
        for key in ("location_keyword", "mood", "time_of_day"):
            if traits.get(key):
                out[key] = traits[key]
    for key in ("mood", "time_of_day"):
        if block.get(key):
            out[key] = block[key]
    return out


def _raw_location_record(package: dict, loc_id) -> dict | None:
    """The raw preserved V1 location record for an id (package
    ["v1_locations"]), or None. The trait block is the renderer's
    primary source; the raw record only SUPPLEMENTS it with fields
    the trait-block builder does not carry (notably ``type``)."""
    if loc_id is None:
        return None
    for rec in package.get("v1_locations") or []:
        if not isinstance(rec, dict):
            continue
        if str(rec.get("id") or "") == str(loc_id) or \
                str(rec.get("location_id") or "") == str(loc_id):
            return rec
    return None


def _enrich_location_block(package: dict, block):
    """A trait block supplemented with its raw V1 record's type/fields
    text (a COPY — the package's block is never mutated). Returns the
    block unchanged when there is nothing to add. General: any
    location whose raw record carries a TYPE/MAP_STYLE the trait
    block lacks gets it; blocks that already carry the data are
    untouched. The adapter owning the trait-block shape should carry
    ``type`` itself (contract gap, reported); until then the renderer
    reads the preserved V1 data the package already ships."""
    if not isinstance(block, dict):
        return block
    loc_id = block.get("location_id") or block.get("id")
    raw = _raw_location_record(package, loc_id)
    if raw is None:
        return block
    extra: dict = {}
    if not block.get("type") and raw.get("type"):
        extra["type"] = raw["type"]
    raw_fields = raw.get("fields")
    if isinstance(raw_fields, dict):
        fields = dict(block.get("fields") or {})
        changed = False
        for key in ("TYPE", "MAP_STYLE", "LOCATION_TYPE"):
            if key not in fields and raw_fields.get(key):
                fields[key] = raw_fields[key]
                changed = True
        if changed:
            extra["fields"] = fields
    if not extra:
        return block
    enriched = dict(block)
    enriched.update(extra)
    return enriched


def _scene_costume_overrides(scene: dict, package: dict,
                             number: int) -> dict:
    """Per-shot costume overrides for a scene: {name: garment}.
    Sources: the scene's "costume_overrides" (or "costumes") dict,
    merged with per-character "costume_overrides" keyed by scene
    number. Only garment-enum values pass through; the engine never
    interprets raw costume words (the adapter maps them)."""
    overrides: dict[str, str] = {}
    for char in package.get("characters", []) or []:
        if not isinstance(char, dict):
            continue
        per_scene = char.get("costume_overrides")
        if isinstance(per_scene, dict):
            garment = per_scene.get(number, per_scene.get(str(number)))
            if isinstance(garment, str):
                garment = garment.strip().lower()
                if garment in VALID_GARMENTS:
                    overrides[str(char.get("name", ""))] = garment
    for key in ("costume_overrides", "costumes"):
        mapping = scene.get(key)
        if isinstance(mapping, dict):
            for name, garment in mapping.items():
                if isinstance(garment, str):
                    garment = garment.strip().lower()
                    if garment in VALID_GARMENTS:
                        overrides[str(name)] = garment
    return overrides


def _scene_visible_override(scene: dict, char_names: list[str]):
    """A scene's explicit visible-cast list, or None when the scene
    carries no override (the first-appearance rule applies). An
    explicit EMPTY list means an empty-cast scene (location-only
    render). Accepted keys: "visible_characters", "scene_cast", and
    a list-of-names "characters" key."""
    for key in ("visible_characters", "scene_cast"):
        value = scene.get(key)
        if isinstance(value, list):
            wanted = {str(v) for v in value}
            return [n for n in char_names if n in wanted]
    value = scene.get("characters")
    if isinstance(value, list) and all(
            isinstance(v, str) for v in value):
        wanted = set(value)
        return [n for n in char_names if n in wanted]
    return None

EMOTION_WORDS = (
    ("vui", "happy"), ("hạnh phúc", "happy"), ("cười", "happy"),
    ("buồn", "sad"), ("khóc", "sad"), ("ngạc nhiên", "surprised"),
    ("ủa", "surprised"), ("ôi", "surprised"), ("lo", "worried"),
    ("sợ", "worried"), ("hoảng", "worried"), ("tức", "angry"),
    ("giận", "angry"),
    # Stage 3: "sững" (frozen / stunned) was missing from the
    # vocabulary, so a stunned line rendered neutral.
    ("sững", "surprised"), ("sững người", "surprised"),
    ("sững sờ", "surprised"), ("đơ người", "surprised"),
)

# F4 (TEST C Phase 2): emotion words match on WORD BOUNDARIES, not
# substrings. The old substring match fired "surprised" on nearly
# every gentle line because "của" contains "ủa" -- so "Bà ơi, bà cầm
# ô của cháu đi." showed a shocked face. A word matches only as a
# standalone word/phrase ("ủa" alone, never inside "của").
EMOTION_PATTERNS = tuple(
    (re.compile(r"\b" + re.escape(word) + r"\b"), expr)
    for word, expr in EMOTION_WORDS)


def _has_word(text: str, word: str) -> bool:
    """Word-boundary match (Stage 3 / Fix 1 discipline): ``word`` must
    appear as a standalone word or phrase, never inside another word.
    This is the same rule as EMOTION_PATTERNS, shared by the
    template / moustache / glasses / body inference below: substring
    matching misfired on "Bavarian" ("ria" inside it -> moustache),
    on "bàn" ("bà" inside it -> female) and on "tôi" ("to" inside
    it -> sturdy)."""
    return re.search(r"\b" + re.escape(word) + r"\b", text or "") is not None


def _has_any_word(text: str, words) -> bool:
    return any(_has_word(text, w) for w in words)


# Valid character templates (the face/rig system's vocabulary).
VALID_TEMPLATES = ("male", "female", "child", "elderly")
# Valid garment values for per-scene costume overrides (Stage 3).
VALID_GARMENTS = ("none", "dress", "uniform")
# Valid moustache styles (the face system's vocabulary).
VALID_MOUSTACHE_STYLES = ("toothbrush", "handlebar", "full")

# Word-boundary markers for the template inference fallback (used
# ONLY when no valid explicit template is provided). Order matters:
# child and elderly are checked before gender, because "bà lão"
# (elderly woman) contains a female marker but the age marker is the
# stronger identity signal.
_TEMPLATE_MARKERS = {
    "child": ("trẻ", "bé", "con nít", "trẻ em", "em bé", "child",
              "kid"),
    "elderly": ("già", "lão", "ông lão", "bà lão", "cao tuổi",
                "elderly"),
    "female": ("nữ", "gái", "cô", "bà", "chị", "mẹ", "dì", "female",
               "phụ nữ", "woman"),
}
_BODY_MARKERS = {
    "sturdy": ("to", "vạm vỡ", "mập", "to lớn", "đô con", "sturdy",
               "heavyset"),
    "slim": ("gầy", "mảnh", "mảnh khảnh", "ốm", "slim", "thin"),
}
# Word-boundary moustache keywords for the text-scan FALLBACK (used
# only when no explicit moustache trait data exists). "ria" alone is
# a word for moustache; "ria mép" is the full phrase. Never a
# substring: "Bavarian" must not match.
_MOUSTACHE_WORDS = ("râu", "ria", "ria mép", "râu mép", "moustache",
                    "mustache", "mép ria")
# Eyewear phrases for the glasses fallback (Stage 3 additional fix):
# bare "kính" is NOT enough -- "kính trọng" (respected) and "kính
# thưa" (respectful address) are not eyewear. Only eyewear phrases
# (or an explicit glasses=True trait) add glasses.
_GLASSES_PHRASES = ("đeo kính", "kính mắt", "kính râm", "kính cận",
                    "kính lão", "kính đen", "mắt kính", "gọng kính",
                    "kính gọng", "glasses", "spectacles", "eyeglasses")


def resolve_expression(expression, text: str) -> str:
    """The face-system expression for a spoken line.

    A line's explicit ``expression`` (face-system name) wins when
    present and valid; legacy mood names map through the face
    system's own LEGACY_MOOD_TO_EXPRESSION; anything else (missing,
    invalid, unknown) falls back to expression_for(text) — never a
    crash, never a silent substitution of a different expression.
    """
    if expression:
        name = str(expression).strip().lower()
        name = LEGACY_MOOD_TO_EXPRESSION.get(name, name)
        if name in EXPRESSION_NAMES:
            return name
    return expression_for(text or "")

# Generic location keywords -> sign label (only when the setting
# actually names the place; otherwise the sign stays blank).
SIGN_LABELS = (
    ("trạm xe buýt", "TRẠM XE BUÝT"), ("xe buýt", "TRẠM XE BUÝT"),
    ("quán cà phê", "CÀ PHÊ"), ("cà phê", "CÀ PHÊ"),
    ("phở", "PHỞ"), ("bánh mì", "BÁNH MÌ"),
)


# Bus door (world x) — characters board here when the scene's cues
# include "board".
BUS_DOOR_X = 1.6

# Bus body (world coords) -- shared by the 3D boxes and the F6 2D
# detail overlay, so both always agree on where the bus is.
BUS_BODY_CENTER = (2.6, 1.0, -3.5)
BUS_BODY_SIZE = (2.6, 1.9, 1.0)
BUS_WHEEL_X = (1.9, 3.3)

# Generic movement-verb map (Vietnamese) for finding WHO performs an
# action: the character named nearest before the verb in the scene's
# action text. No story names here — only verbs and the package's own
# character names.
VERB_FOR_CUE = {
    "run": ["chạy"], "walk": ["đi", "bước"],
    "walk_fast": ["đi", "bước", "chạy"],
    "board": ["lên xe buýt", "lên xe", "bước lên xe"],
    "give": ["đưa"], "bend_pick": ["nhặt", "cúi"],
    "wave": ["vẫy", "chào"], "take": ["lấy", "nhận"],
    "open": ["mở"], "search": ["tìm", "kiểm tra"],
    "put_away": ["cất", "bỏ"],
    "sit": ["ngồi"], "stand": ["đứng"], "turn_back": ["quay"],
}


def action_actor(action_text: str, cues: list[str],
                 names: list[str]) -> str | None:
    """Which character performs the scene's movement cue, from the
    action text: the name nearest before the movement verb. Falls back
    to the first name mentioned, then None."""
    text = action_text or ""
    for cue in cues:
        for verb in VERB_FOR_CUE.get(cue, []):
            idx = text.lower().find(verb)
            if idx < 0:
                continue
            before = text[:idx]
            best, best_pos = None, -1
            for n in names:
                pos = before.rfind(n)
                if pos > best_pos:
                    best, best_pos = n, pos
            if best:
                return best
    for n in names:
        if n in text:
            return n
    return None


def sx(world_x: float, cam=None, z: float = WORLD_Z) -> int:
    """World x -> screen x under ``cam`` (default: the legacy CAM)."""
    cam = cam or CAM
    x, _, _, _ = cam.project((world_x, 0.0, z), W, H)
    return int(round(x))


def ws(screen_x: float, cam=None, z: float = WORLD_Z) -> float:
    """Screen x -> world x under ``cam`` (default: the legacy CAM)."""
    cam = cam or CAM
    lo, hi = -6.0, 7.0
    for _ in range(28):
        mid = (lo + hi) / 2.0
        mx, _, _, _ = cam.project((mid, 0.0, z), W, H)
        if mx < screen_x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# Over-the-shoulder foreground depth: the listener stands this much
# closer to the camera (world z) than the character plane, so the
# perspective scale makes them read as a foreground shoulder while
# their feet stay in frame (measured: +0.9 -> ~1.2x height, feet at
# y~1027; +1.6 pushed the feet below the frame).
OTS_FOREGROUND_Z_OFFSET = 0.9


def char_metrics(cam, world_x: float, world_z: float = WORLD_Z,
                 base_scale: float = 1.0):
    """Per-character screen metrics under a shot camera.

    Returns (screen_x, ground_y, height_px): the feet position from
    projecting the ground point, and the drawn height from the
    PERSPECTIVE SCALE at the subject point (eye height), relative to
    the legacy camera — so the same subject at the same camera
    distance keeps the same height across angles (no head-size pump),
    a closer foreground figure is genuinely larger, and the default
    camera reproduces (sx, GROUND_Y, CHAR_H) exactly. The height is
    deliberately NOT the vertical-anchor extent: from a high angle
    that foreshortens to a fraction of the character (birds_eye
    measured 189 px), which reads as a shrunken person, not a
    viewpoint change. Characters are billboards: scale by depth,
    feet on the projected ground line.

    ``base_scale`` (scale-variant rule): a per-character body scale
    from the package (``scale_ratio``; 1.8 for a Titan declared at
    HEIGHT_RATIO 1.8). The drawn height multiplies by it, so the
    character is genuinely taller while its head RATIO stays locked
    (the rig scales all proportions from height). Default 1.0 keeps
    every existing render identical; non-positive/non-finite values
    fall back to 1.0.
    """
    try:
        scale = float(base_scale)
    except (TypeError, ValueError):
        scale = 1.0
    if not (scale > 0) or scale != scale or scale in (float("inf"),
                                                      float("-inf")):
        scale = 1.0
    gx, gy, _, _ = cam.project((world_x, 0.0, world_z), W, H)
    _, _, s_shot, _ = cam.project((world_x, 1.2, world_z), 1, H)
    _, _, s_base, _ = CAM.project((world_x, 1.2, world_z), 1, H)
    if s_base and s_shot:
        height_px = int(round(CHAR_H * scale * s_shot / s_base))
    else:
        height_px = int(round(CHAR_H * scale))
    return int(round(gx)), int(round(gy)), height_px


# Top margin a standing box must clear for the head to stay in frame
# (the fit loop below only ever engages for scaled-up subjects).
_FIT_TOP_MARGIN_PX = 12.0
_FIT_MAX_RADIUS_SCALE = 3.0


def _fit_radius_scale(shot_type, angle, target_x, target_z,
                      counterpart_x, srs_side, positions, scales):
    """Camera radius multiplier so scaled-up subjects fit the frame.

    ``positions``/``scales`` are parallel lists of (world_x, world_z)
    and per-character body scales for the shot's visible characters.
    Returns 1.0 when no subject is scaled up (every unscaled shot is
    untouched) or when every standing box already clears the top
    margin. Otherwise iterates: drawn height is ~1/radius, so each
    pass multiplies the radius by the worst overflow ratio; the
    ground line shifts with radius too, so up to eight passes are
    allowed (a 1.8x subject at the standard radius converges in six).
    The radius is capped at 3.0x — beyond that the shot is reported
    with the residual overflow, never silently re-scaled.
    """
    if not positions or max(scales, default=1.0) <= 1.0:
        return 1.0
    radius_scale = 1.0
    for _ in range(8):
        cam = viewpoint_for_shot(
            shot_type, angle,
            subject_pos=(target_x, 1.2, target_z),
            counterpart_x=counterpart_x, srs_side=srs_side,
            radius_scale=radius_scale)
        worst = 1.0
        for (x, z), s in zip(positions, scales):
            _gx, gy, h = char_metrics(cam, x, z, base_scale=s)
            head_y = gy - h
            if head_y < _FIT_TOP_MARGIN_PX:
                worst = max(worst, h / max(1.0, gy - _FIT_TOP_MARGIN_PX))
        if worst <= 1.0001:
            return radius_scale
        radius_scale = min(_FIT_MAX_RADIUS_SCALE, radius_scale * worst)
        if radius_scale >= _FIT_MAX_RADIUS_SCALE:
            return radius_scale
    return radius_scale


def expression_for(text: str) -> str:
    low = text.lower()
    for pattern, expr in EMOTION_PATTERNS:
        if pattern.search(low):
            return expr
    return "neutral"


def _character_scan_text(char: dict, include_name: bool = False) -> str:
    """The text the keyword fallbacks scan: the package's own fields
    (description, voice_hint, appearance, costume text, trait list),
    lowercased. The name is included only for template inference (an
    honorific in the name is identity evidence); it is NEVER scanned
    for moustache/glasses (a name must not put a moustache on a face).
    """
    parts = [str(char.get("description", "") or ""),
             str(char.get("voice_hint", "") or ""),
             str(char.get("appearance", "") or ""),
             str(char.get("costume_text", "") or ""),
             str(char.get("costume", "") or "")
             if isinstance(char.get("costume"), str) else ""]
    traits = char.get("traits")
    if isinstance(traits, (list, tuple)):
        parts.extend(str(t) for t in traits)
    elif isinstance(traits, str):
        parts.append(traits)
    if include_name:
        parts.append(str(char.get("name", "") or ""))
    return " ".join(p for p in parts if p).lower()


def infer_template(char: dict) -> str:
    """Template inference fallback: the generic inference that runs
    ONLY when no valid explicit template is provided (Stage 3 Fix 1).
    An explicit valid template is never overridden. Markers match on
    word boundaries over the name + description + voice_hint +
    appearance + costume + traits."""
    text = _character_scan_text(char, include_name=True)
    if _has_any_word(text, _TEMPLATE_MARKERS["child"]):
        return "child"
    if _has_any_word(text, _TEMPLATE_MARKERS["elderly"]):
        return "elderly"
    gender = str(char.get("gender", "") or "").strip().lower()
    if gender in ("female", "nữ", "f", "woman"):
        return "female"
    if _has_any_word(text, _TEMPLATE_MARKERS["female"]):
        return "female"
    return "male"


def map_character(char: dict, index: int, costume_override=None,
                height_px=None):
    """Package character dict -> Stickman. The engine ships a small
    registry of locked instances (make_character_instance); any name
    in that registry is used as-is, and EVERY other name is built
    generically from the package's own fields (template / voice_hint /
    description keywords) — no story names, no per-story branches in
    this pipeline. The registry lookup is a name lookup, not story
    logic: removing it would only change the exact suit colours of
    those instances, never the flow.

    Stage 3 / Fix 1 precedence (explicit trait data beats text):
    * template: an explicit valid template ("male"|"female"|"child"|
      "elderly") is used as-is; the generic inference runs ONLY when
      no valid explicit template is provided. (The old code defaulted
      ``template = char.get("template") or "male"`` and then checked
      ``if template not in (...)``, so the inference block NEVER ran
      and every template-less character silently rendered male.)
    * moustache: explicit trait data first — ``moustache_style`` in
      ("toothbrush"|"handlebar"|"full") or ``moustache`` True/False
      decides, including "none"/False meaning NO moustache. Only when
      NO explicit moustache trait exists does the word-boundary text
      scan run (free-form packages). Substring matching is gone:
      "Bavarian" never yields a moustache.
    * glasses: explicit ``glasses`` bool decides; otherwise only
      eyewear phrases ("đeo kính", "kính mắt", ...) add glasses —
      bare "kính" ("kính trọng", "kính thưa") does not.
    * costume_override (Stage 3, per-scene garment): when a valid
      garment ("none"|"dress"|"uniform") is given it replaces the
      character's own costume for this shot only.
    """
    name = str(char.get("name", f"char{index}"))
    key = name.strip().lower()
    # height_px (Stage 3 / F9): the shot camera's perspective scale
    # for this character (char_metrics). Default CHAR_H is the legacy
    # fixed-camera height — callers that pass no camera (character
    # design, legacy tests) are unchanged.
    height = int(height_px) if height_px else CHAR_H
    try:
        return make_character_instance(key, height=height)
    except (ValueError, KeyError):
        pass  # not a locked instance — build generically below
    desc = _character_scan_text(char)
    explicit_template = char.get("template")
    if explicit_template in VALID_TEMPLATES:
        template = explicit_template
    else:
        template = infer_template(char)
    body = char.get("body_variant") or "standard"
    if body not in ("slim", "standard", "sturdy"):
        # Word-boundary body markers (same discipline as the template
        # fix: substring "to" misfired on "tôi", "toàn", ...).
        body = "sturdy" if _has_any_word(desc, _BODY_MARKERS["sturdy"]) \
            else "slim" if _has_any_word(desc, _BODY_MARKERS["slim"]) \
            else "standard"
    kwargs = {
        "template": template,
        "name": name,
        "suit": char.get("jacket_color") or PALETTE[index % len(PALETTE)],
        "body_variant": body,
        "height": height,
    }
    if costume_override in VALID_GARMENTS:
        kwargs["costume"] = costume_override
    elif char.get("costume") in ("dress", "uniform"):
        kwargs["costume"] = char["costume"]
    if char.get("hair_style") in ("short", "long", "tuft", "side_part"):
        kwargs["hair_style"] = char["hair_style"]
    if char.get("hat") in ("bowler", "none"):
        kwargs["hat"] = char["hat"]
    # Moustache: explicit trait data first, text scan only as fallback.
    moustache_style = char.get("moustache_style")
    moustache_flag = char.get("moustache")
    if moustache_style in VALID_MOUSTACHE_STYLES:
        kwargs["moustache"] = True
        kwargs["moustache_style"] = moustache_style
    elif moustache_style == "none" or moustache_flag is False:
        kwargs["moustache"] = False
    elif moustache_flag is True:
        kwargs["moustache"] = True
    elif _has_any_word(desc, _MOUSTACHE_WORDS):
        kwargs["moustache"] = True
        if _has_word(desc, "toothbrush"):
            kwargs["moustache_style"] = "toothbrush"
        elif _has_word(desc, "handlebar"):
            kwargs["moustache_style"] = "handlebar"
    # Glasses: explicit bool first, eyewear phrases as fallback.
    glasses_flag = char.get("glasses")
    if glasses_flag is True:
        kwargs["glasses"] = True
    elif glasses_flag is False:
        kwargs["glasses"] = False
    elif _has_any_word(desc, _GLASSES_PHRASES):
        kwargs["glasses"] = True
    # Species features (generic visual profile): explicit contract data
    # first, then flat trait fields. A value outside the drawing
    # vocabulary is skipped here (the validator already noted the drop)
    # and the rig default "none" applies -- no invented feature.
    profile = char.get("visual_profile")
    if not isinstance(profile, dict):
        profile = {}
    for key, allowed in (("ears", EAR_SHAPES), ("tail", TAIL_SHAPES),
                         ("horns", HORN_SHAPES),
                         ("face_markings", FACE_MARKING_STYLES)):
        value = profile.get(key)
        if value is None:
            value = char.get(key)
        if value in allowed and value != "none":
            kwargs[key] = value
    return make_character(**kwargs)


# ---------------------------------------------------------------------------
# F5 (Stage 3): location composition from DATA.
#
# A location is composed from the script's own data, never substituted:
#  * trait-block path (location_data, SPEC §15.3): FEATURES +
#    FOREGROUND / MIDGROUND / BACKGROUND + LIGHTING + WEATHER +
#    PALETTE + FORBIDDEN compose the world through the generic
#    keyword->feature vocabulary below. FORBIDDEN entries suppress
#    the features they name.
#  * inline-text path (location_text, SPEC §11.4): the same generic
#    keyword vocabulary reads the free text (room / street /
#    newsstand / intersection / bell tower / square / barracks /
#    map / trench / rural route + time of day + mood + weather).
#  * legacy path (neither): the v7 generic street, behaviour
#    unchanged — EXCEPT shop signage, which is now data-driven (a
#    sign appears only when the setting text names that shop).
#
# Honest limits of the box vocabulary: people/crowds, smoke and
# accurate map geography are NOT box features — a feature entry that
# names them is reported as unused (see compose_* coverage), never
# faked with a wrong box. Interiors are a back wall + furniture in
# the same 2.5D world, not an enclosed room.
# ---------------------------------------------------------------------------

_SKY_DAY_WARM = ((135, 180, 220), (200, 220, 240))
_SKY_DAY_COLD = ((90, 120, 160), (170, 190, 210))
_SKY_NIGHT = ((28, 42, 72), (130, 142, 165))
_SKY_SUNSET = ((215, 140, 80), (240, 195, 145))
_SKY_OVERCAST = ((148, 158, 172), (198, 204, 210))
_SKY_INTERIOR_WARM = ((196, 178, 150), (216, 198, 168))
_SKY_INTERIOR_COLD = ((170, 175, 180), (195, 200, 205))
_SKY_MAP = ((232, 218, 178), (242, 232, 200))

_COLOR_NAMES = {
    "mud brown": (95, 80, 60), "dark olive": (80, 85, 55),
    "muted brown": (120, 95, 70), "gray blue": (110, 125, 145),
    "cream": (240, 230, 205), "gray": (140, 140, 140),
    "grey": (140, 140, 140), "brown": (120, 85, 55),
    "olive": (110, 110, 70), "blue": (80, 110, 160),
    "green": (90, 130, 80), "red": (160, 70, 60),
    "yellow": (220, 190, 90), "black": (40, 40, 40),
    "white": (235, 235, 235), "beige": (215, 195, 165),
    "khaki": (180, 165, 120), "orange": (210, 130, 70),
    "pink": (220, 170, 175), "purple": (120, 100, 150),
}


def _parse_color(value):
    """A palette entry -> RGB, or None. Accepts #RRGGBB, an RGB
    tuple/list, or a generic colour name (exact or contained)."""
    if value is None:
        return None
    if isinstance(value, (tuple, list)) and len(value) == 3:
        try:
            return tuple(int(max(0, min(255, v))) for v in value)
        except (TypeError, ValueError):
            return None
    text = str(value).strip().lower()
    m = re.fullmatch(r"#?([0-9a-f]{6})", text)
    if m:
        hx = m.group(1)
        return tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))
    for name in sorted(_COLOR_NAMES, key=len, reverse=True):
        if name in text:
            return _COLOR_NAMES[name]
    return None


def _box(name, cx, cy, cz, sx_, sy_, sz_, color, label=""):
    return Box3D(center=(cx, cy, cz), size=(sx_, sy_, sz_),
                 color=tuple(color), name=name, label=label)


def _pick(colors, i, default):
    return colors[i % len(colors)] if colors else default


# Generic keyword -> feature vocabulary. Keywords match on word
# boundaries (see _has_word); a feature is a box-building recipe,
# never a story value. Layer defaults: background z in [-14, -10],
# midground z in [-4, -1], foreground z in [0.8, 1.6].
_FEATURE_KEYWORDS = (
    (("bản đồ", "map", "atlas"), "map_panel"),
    (("chiến hào", "trench", "hào chiến"), "trench"),
    (("văn phòng", "office", "nội thất", "phòng", "interior",
      "room"), "interior"),
    (("doanh trại", "barracks", "trại lính", "quân doanh"), "barracks"),
    (("quảng trường", "square", "plaza"), "square"),
    (("tháp chuông", "nhà thờ", "church", "cathedral",
      "bell tower"), "tower"),
    (("quầy báo", "sạp báo", "newsstand", "kiosk"), "stall"),
    (("ngã tư", "ngã ba", "intersection", "crossroads"), "crossing"),
    (("đường đất", "đồng quê", "countryside", "rural", "đồng ruộng",
      "cánh đồng", "tuyến hành quân", "nông thôn"), "rural"),
    (("phố", "street", "đường phố", "vỉa hè", "con phố",
      "góc phố"), "street"),
    (("cây", "tree"), "tree"),
    (("cột đèn", "đèn đường", "lamp", "street light"), "lamp"),
    (("ghế", "bench"), "bench"),
    (("bàn gỗ", "bàn làm việc", "bàn viết", "cái bàn", "desk",
      "table"), "desk"),
    (("tủ", "cabinet", "shelf", "kệ"), "cabinet"),
    (("cờ", "flag", "banner"), "flag"),
    (("bao cát", "sandbag"), "sandbags"),
    (("hàng rào", "fence"), "fence"),
    (("thùng gỗ", "thùng", "crate", "barrel"), "crate"),
    (("sông", "river", "suối", "stream"), "river"),
    (("cầu", "bridge"), "bridge"),
    (("biển hiệu", "signboard", "bảng hiệu"), "sign"),
    (("cửa sổ", "window"), "window"),
    (("vũng nước", "vũng", "puddle"), "puddle"),
    (("bùn", "mud"), "mud"),
    (("ván gỗ", "ván", "plank"), "planks"),
    (("tường", "wall"), "wall"),
    (("mái nhà", "mái", "roof"), "roofs"),
    (("cổng", "gate", "arch"), "gate"),
)

# Primary-kind priority: the first kind whose keywords hit decides
# the environment's base layout; other hits add extra features.
_KIND_PRIORITY = ("map_panel", "trench", "interior", "barracks",
                  "square", "tower", "stall", "crossing", "rural",
                  "street")

_NIGHT_WORDS = ("đêm", "tối", "khuya", "ban đêm", "nửa đêm", "night")
_SUNSET_WORDS = ("hoàng hôn", "chiều tà", "sunset", "dusk")
_RAIN_WORDS = ("mưa", "rain")
_COLD_WORDS = ("lạnh", "lẽo", "buốt", "u ám", "âm u", "cold",
               "overcast", "nhiều mây", "u ám")


def _features_in(text: str):
    """Feature keys named by a text, in vocabulary order."""
    low = (text or "").lower()
    return [key for keywords, key in _FEATURE_KEYWORDS
            if _has_any_word(low, keywords)]


def _feature_boxes(key: str, colors, label: str = "") -> list[Box3D]:
    """Boxes for one feature key. Positions are fixed world slots;
    colours cycle the location palette when one is given."""
    b1 = _pick(colors, 0, (74, 88, 118))
    b2 = _pick(colors, 1, (66, 80, 110))
    b3 = _pick(colors, 2, (80, 94, 124))
    if key == "street":
        out = [
            _box("building_left", -4.5, 1.5, -12.0, 2.4, 3.0, 1.5, b1),
            _box("building_center", -0.5, 2.0, -14.0, 3.2, 4.0, 1.5, b2),
            _box("building_right", 4.8, 1.3, -11.0, 2.2, 2.6, 1.5, b3),
        ]
        for wx, wy, wz in ((-5.2, 1.6, -11.15), (-3.8, 2.4, -11.15),
                           (-1.5, 2.0, -13.15), (0.5, 3.0, -13.15),
                           (4.2, 1.5, -10.15), (5.4, 1.5, -10.15)):
            out.append(_box("window", wx, wy, wz, 0.5, 0.7, 0.1,
                            (255, 200, 90)))
        out.append(_box("kerb", 0.0, 0.08, -1.2, 14.0, 0.16, 0.6,
                        (150, 148, 140)))
        out.append(_box("path_fg", 0.0, 0.05, 1.0, 14.0, 0.1, 0.4,
                        (96, 90, 82)))
        return out
    if key == "interior":
        return [
            _box("back_wall", 0.0, 2.0, -6.0, 14.0, 4.0, 0.4,
                 _pick(colors, 0, (190, 172, 142))),
            _box("wall_window_l", -3.6, 2.6, -5.75, 1.2, 1.6, 0.1,
                 (230, 225, 190)),
            _box("wall_window_r", 3.6, 2.6, -5.75, 1.2, 1.6, 0.1,
                 (230, 225, 190)),
            _box("wall_door", 5.6, 1.1, -5.75, 1.0, 2.2, 0.1,
                 (110, 80, 55)),
            _box("rug_fg", 0.0, 0.05, 1.0, 8.0, 0.1, 2.0,
                 _pick(colors, 1, (140, 60, 55))),
        ]
    if key == "map_panel":
        out = [
            _box("map_frame", 0.0, 2.2, -5.2, 11.0, 5.2, 0.3,
                 (90, 65, 40)),
            _box("map_paper", 0.0, 2.2, -5.0, 10.4, 4.7, 0.2,
                 (238, 226, 190)),
        ]
        # Abstract region patches on the paper (NOT accurate
        # geography — the box vocabulary cannot draw borders; the
        # patches read as a period map board, labelled only from
        # location data when labels are supplied).
        region_colors = [(150, 170, 150), (170, 150, 120),
                         (140, 160, 180), (180, 160, 140),
                         (160, 150, 170), (150, 165, 155)]
        slots = [(-3.4, 3.1, 3.0, 1.6), (-0.2, 3.2, 2.8, 1.7),
                 (3.0, 3.0, 3.0, 1.5), (-3.2, 1.3, 2.8, 1.4),
                 (-0.1, 1.2, 3.0, 1.5), (3.1, 1.3, 2.8, 1.4)]
        labels = [s.strip() for s in label.split("|")] if label else []
        for i, (rx, ry, rw, rh) in enumerate(slots):
            out.append(_box(f"map_region_{i + 1}", rx, ry, -4.85,
                            rw, rh, 0.1,
                            _pick(colors, i, region_colors[i]),
                            label=labels[i][:24] if i < len(labels)
                            else ""))
        out.append(_box("map_table", 0.0, 0.05, 1.0, 12.0, 0.1, 1.0,
                        (105, 82, 58)))
        return out
    if key == "trench":
        out = [
            _box("trench_wall_l", -4.2, 0.7, -2.0, 4.5, 1.4, 0.8,
                 (105, 88, 62)),
            _box("trench_wall_r", 4.2, 0.7, -2.0, 4.5, 1.4, 0.8,
                 (100, 84, 60)),
            _box("trench_back", 0.0, 0.9, -8.0, 12.0, 1.8, 0.8,
                 (95, 80, 58)),
            _box("broken_tree", -5.2, 1.0, -6.0, 0.25, 2.0, 0.25,
                 (70, 55, 40)),
            _box("broken_branch", -4.9, 1.9, -6.0, 0.7, 0.15, 0.15,
                 (70, 55, 40)),
        ]
        for i, sx_ in enumerate((-2.6, -1.7, -0.8, 0.8, 1.7, 2.6)):
            out.append(_box(f"sandbag_fg_{i}", sx_, 0.2, 1.3, 0.8, 0.4,
                            0.4, (165, 150, 110)))
        return out
    if key == "barracks":
        return [
            _box("barracks_l", -4.2, 1.0, -11.0, 5.0, 2.0, 1.5,
                 _pick(colors, 0, (130, 95, 75))),
            _box("barracks_r", 4.2, 1.0, -11.0, 5.0, 2.0, 1.5,
                 _pick(colors, 1, (125, 90, 70))),
            _box("barracks_window_1", -5.2, 1.2, -10.2, 0.6, 0.8, 0.1,
                 (230, 220, 180)),
            _box("barracks_window_2", -3.2, 1.2, -10.2, 0.6, 0.8, 0.1,
                 (230, 220, 180)),
            _box("barracks_window_3", 3.2, 1.2, -10.2, 0.6, 0.8, 0.1,
                 (230, 220, 180)),
            _box("barracks_window_4", 5.2, 1.2, -10.2, 0.6, 0.8, 0.1,
                 (230, 220, 180)),
            _box("parade_ground", 0.0, 0.05, 1.0, 14.0, 0.1, 0.6,
                 (130, 120, 100)),
        ]
    if key == "square":
        return [
            _box("square_building_l", -5.0, 1.5, -12.0, 3.0, 3.0, 1.5, b1),
            _box("square_building_r", 5.0, 1.5, -12.0, 3.0, 3.0, 1.5, b3),
            _box("monument_base", 0.0, 0.4, -8.0, 1.6, 0.8, 1.2,
                 (150, 145, 135)),
            _box("monument_top", 0.0, 1.5, -8.0, 0.7, 1.4, 0.7,
                 (170, 165, 155)),
            _box("square_paving", 0.0, 0.05, 1.0, 14.0, 0.1, 0.6,
                 (140, 135, 125)),
        ]
    if key == "tower":
        return [
            _box("tower_l", -2.6, 2.6, -12.0, 1.3, 5.2, 1.3,
                 _pick(colors, 0, (150, 140, 125))),
            _box("tower_r", 2.6, 2.6, -12.0, 1.3, 5.2, 1.3,
                 _pick(colors, 1, (145, 135, 120))),
            _box("spire_l", -2.6, 5.7, -12.0, 0.6, 1.0, 0.6,
                 (90, 110, 120)),
            _box("spire_r", 2.6, 5.7, -12.0, 0.6, 1.0, 0.6,
                 (90, 110, 120)),
            _box("tower_window_l", -2.6, 3.6, -11.3, 0.4, 0.9, 0.1,
                 (255, 210, 120)),
            _box("tower_window_r", 2.6, 3.6, -11.3, 0.4, 0.9, 0.1,
                 (255, 210, 120)),
            _box("church_nave", 0.0, 1.2, -12.5, 3.4, 2.4, 1.5,
                 _pick(colors, 2, (155, 145, 130))),
        ]
    if key == "stall":
        return [
            _box("stall_counter", -1.5, 0.55, -2.5, 2.2, 1.1, 0.8,
                 (120, 85, 55)),
            _box("stall_roof", -1.5, 2.2, -2.5, 2.6, 0.15, 1.2,
                 (150, 60, 55)),
            _box("stall_post_l", -2.6, 1.3, -2.5, 0.12, 2.0, 0.12,
                 (60, 45, 35)),
            _box("stall_post_r", -0.4, 1.3, -2.5, 0.12, 2.0, 0.12,
                 (60, 45, 35)),
            _box("paper_stack_1", -2.0, 1.25, -2.5, 0.5, 0.3, 0.4,
                 (240, 235, 220)),
            _box("paper_stack_2", -1.2, 1.25, -2.5, 0.5, 0.3, 0.4,
                 (235, 230, 215)),
            _box("stall_sign", -1.5, 1.85, -2.1, 1.4, 0.4, 0.08,
                 (40, 60, 90), label=label),
        ]
    if key == "crossing":
        out = _feature_boxes("street", colors)
        out += [
            _box("crossing_lamp_l", -4.0, 1.6, -1.5, 0.14, 3.2, 0.14,
                 (30, 32, 40)),
            _box("crossing_lamp_r", 4.0, 1.6, -1.5, 0.14, 3.2, 0.14,
                 (30, 32, 40)),
            _box("crossing_strip", 0.0, 0.06, 0.2, 3.0, 0.08, 2.5,
                 (180, 178, 170)),
        ]
        return out
    if key == "rural":
        return [
            _box("field_l", -5.0, 0.15, -9.0, 6.0, 0.3, 4.0,
                 _pick(colors, 0, (130, 140, 85))),
            _box("field_r", 5.0, 0.15, -9.0, 6.0, 0.3, 4.0,
                 _pick(colors, 1, (150, 140, 90))),
            _box("treeline", 0.0, 0.8, -13.0, 12.0, 1.6, 0.6,
                 (95, 105, 80)),
            _box("dirt_road", 0.0, 0.06, 0.5, 3.2, 0.1, 6.0,
                 (140, 120, 90)),
            _box("rural_tree", -4.6, 1.2, -4.0, 0.25, 2.4, 0.25,
                 (80, 60, 45)),
            _box("rural_tree_top", -4.6, 2.7, -4.0, 1.1, 0.9, 0.9,
                 (110, 125, 85)),
        ]
    if key == "tree":
        return [
            _box("tree_trunk", -4.8, 1.0, -3.5, 0.25, 2.0, 0.25,
                 (80, 60, 45)),
            _box("tree_top", -4.8, 2.4, -3.5, 1.3, 1.1, 1.1,
                 (95, 130, 75)),
        ]
    if key == "lamp":
        return [
            _box("lamp_post", 4.0, 1.6, -1.5, 0.14, 3.2, 0.14,
                 (30, 32, 40)),
            _box("lamp_head", 4.0, 3.3, -1.5, 0.55, 0.22, 0.55,
                 (255, 211, 78)),
        ]
    if key == "bench":
        return [_box("bench", 2.6, 0.22, -2.5, 1.9, 0.45, 0.6,
                     (122, 74, 43))]
    if key == "desk":
        return [
            _box("desk_top", 0.6, 0.75, -2.0, 2.4, 0.12, 1.0,
                 (130, 95, 60)),
            _box("desk_leg_l", -0.4, 0.35, -2.0, 0.12, 0.7, 0.9,
                 (110, 80, 50)),
            _box("desk_leg_r", 1.6, 0.35, -2.0, 0.12, 0.7, 0.9,
                 (110, 80, 50)),
            _box("desk_papers", 0.4, 0.85, -2.0, 0.7, 0.08, 0.5,
                 (242, 238, 224)),
            _box("desk_chair", 0.6, 0.45, -1.0, 0.6, 0.9, 0.6,
                 (100, 72, 45)),
        ]
    if key == "cabinet":
        return [
            _box("cabinet_l", -4.4, 1.1, -5.5, 1.4, 2.2, 0.6,
                 (115, 85, 58)),
            _box("cabinet_r", 4.4, 1.1, -5.5, 1.4, 2.2, 0.6,
                 (115, 85, 58)),
        ]
    if key == "flag":
        return [
            _box("flag_pole", 3.8, 1.8, -3.0, 0.1, 3.6, 0.1,
                 (50, 50, 55)),
            _box("flag_cloth", 4.35, 3.1, -3.0, 1.0, 0.6, 0.06,
                 _pick(colors, 0, (170, 60, 55))),
        ]
    if key == "sandbags":
        return [_box(f"sandbag_{i}", sx_, 0.2, -1.0, 0.8, 0.4, 0.4,
                     (165, 150, 110))
                for i, sx_ in enumerate((-3.2, -2.3, 2.3, 3.2))]
    if key == "fence":
        return [
            _box("fence_rail", 0.0, 0.55, -3.5, 8.0, 0.12, 0.12,
                 (110, 85, 60)),
            _box("fence_post_l", -3.8, 0.35, -3.5, 0.14, 0.7, 0.14,
                 (95, 72, 50)),
            _box("fence_post_r", 3.8, 0.35, -3.5, 0.14, 0.7, 0.14,
                 (95, 72, 50)),
        ]
    if key == "crate":
        return [_box("crate_fg", 2.2, 0.25, 1.5, 0.5, 0.5, 0.5,
                     (139, 94, 52)),
                _box("crate_fg_2", -3.6, 0.2, 1.4, 0.4, 0.4, 0.4,
                     (130, 88, 50))]
    if key == "river":
        return [_box("river", 0.0, 0.06, -6.0, 14.0, 0.1, 2.5,
                     (90, 130, 165))]
    if key == "bridge":
        return [
            _box("bridge_deck", 0.0, 0.5, -4.0, 7.0, 0.25, 1.4,
                 (120, 100, 80)),
            _box("bridge_rail", 0.0, 0.95, -3.4, 7.0, 0.1, 0.1,
                 (90, 75, 60)),
        ]
    if key == "sign":
        return [
            _box("sign_post", 0.2, 1.3, -2.0, 0.1, 2.6, 0.1,
                 (30, 32, 40)),
            _box("sign", 0.2, 2.7, -2.0, 1.0, 0.6, 0.08,
                 (23, 32, 51), label=label),
        ]
    if key == "window":
        return [_box("extra_window", -2.0, 2.2, -5.8, 1.0, 1.3, 0.1,
                     (235, 228, 195))]
    if key == "puddle":
        return [_box("puddle_slab", -1.8, 0.06, 0.6, 2.2, 0.08, 1.0,
                     (70, 95, 125))]
    if key == "mud":
        return [_box("mud_patch", 1.6, 0.06, 0.8, 3.0, 0.08, 1.6,
                     (88, 72, 52))]
    if key == "planks":
        return [_box("planks", 0.0, 0.08, 0.4, 3.4, 0.1, 1.2,
                     (140, 115, 80))]
    if key == "wall":
        return [_box("side_wall", -5.8, 1.5, -4.0, 0.4, 3.0, 6.0,
                     _pick(colors, 0, (160, 150, 135)))]
    if key == "roofs":
        return [
            _box("roof_l", -4.5, 3.3, -12.0, 2.6, 0.6, 1.7,
                 _pick(colors, 0, (140, 70, 60))),
            _box("roof_r", 4.8, 3.0, -11.0, 2.4, 0.6, 1.7,
                 _pick(colors, 1, (135, 68, 58))),
        ]
    if key == "gate":
        return [
            _box("gate_post_l", -2.2, 1.4, -6.0, 0.5, 2.8, 0.5,
                 (140, 130, 115)),
            _box("gate_post_r", 2.2, 1.4, -6.0, 0.5, 2.8, 0.5,
                 (140, 130, 115)),
            _box("gate_top", 0.0, 3.0, -6.0, 5.0, 0.5, 0.6,
                 (130, 120, 105)),
        ]
    return []


def _sky_and_ground(kind: str, time_of_day: str, mood: str,
                    weather_text: str, rainy: bool):
    """Sky ramp + ground colour for a composed environment. Night
    comes ONLY from time_of_day (rain no longer forces a night sky —
    a rainy day stays a day); interiors and maps have their own
    ramps."""
    low = (weather_text or "").lower()
    night = time_of_day == "night" or _has_any_word(low, _NIGHT_WORDS)
    sunset = _has_any_word(low, _SUNSET_WORDS)
    cold = mood == "cold" or _has_any_word(low, _COLD_WORDS)
    if kind == "interior":
        sky = _SKY_INTERIOR_COLD if cold else _SKY_INTERIOR_WARM
        return sky[0], sky[1], (118, 94, 64)
    if kind == "map_panel":
        return _SKY_MAP[0], _SKY_MAP[1], (105, 82, 58)
    if kind == "trench":
        ground = (80, 68, 52) if rainy else (92, 78, 58)
        if night:
            return _SKY_NIGHT[0], _SKY_NIGHT[1], ground
        return _SKY_OVERCAST[0], _SKY_OVERCAST[1], ground
    if night:
        return _SKY_NIGHT[0], _SKY_NIGHT[1], (78, 72, 66)
    if sunset:
        return _SKY_SUNSET[0], _SKY_SUNSET[1], (96, 92, 84)
    if rainy or cold:
        return _SKY_OVERCAST[0], _SKY_OVERCAST[1], (96, 92, 84)
    sky = _SKY_DAY_COLD if cold else _SKY_DAY_WARM
    return sky[0], sky[1], (96, 92, 84)


def _compose_from_features(feature_keys, colors, *, sign_label="",
                           map_labels=""):
    """Feature keys -> boxes, de-duplicated, kind layout first."""
    boxes: list[Box3D] = []
    seen: set[str] = set()
    ordered = [k for k in _KIND_PRIORITY if k in feature_keys] + \
              [k for k in feature_keys if k not in _KIND_PRIORITY]
    for key in ordered:
        if key in seen:
            continue
        seen.add(key)
        label = ""
        if key == "sign":
            label = sign_label
        elif key == "map_panel":
            label = map_labels
        elif key == "stall":
            label = sign_label
        boxes.extend(_feature_boxes(key, colors, label=label))
    return boxes


def _generic_neutral_boxes(colors) -> list[Box3D]:
    """Fallback when no feature vocabulary hits: neutral layered
    boxes tinted by the location palette — distinct per palette, but
    honestly generic. Never a substituted street."""
    return [
        _box("facade_l", -4.5, 1.4, -12.0, 2.6, 2.8, 1.5,
             _pick(colors, 0, (120, 120, 120))),
        _box("facade_c", 0.0, 1.8, -13.5, 3.4, 3.6, 1.5,
             _pick(colors, 1, (110, 110, 110))),
        _box("facade_r", 4.6, 1.4, -12.0, 2.6, 2.8, 1.5,
             _pick(colors, 2, (125, 125, 125))),
        _box("mid_block", 1.8, 0.5, -2.5, 1.6, 1.0, 0.8,
             _pick(colors, 0, (105, 100, 92))),
        _box("edge_fg", -3.6, 0.3, 1.4, 0.5, 0.6, 0.5,
             _pick(colors, 1, (100, 95, 88))),
        _box("path_fg", 0.0, 0.05, 1.0, 14.0, 0.1, 0.4, (96, 90, 82)),
    ]


def _trait_text(block: dict, *keys) -> str:
    parts = []
    for key in keys:
        value = block.get(key)
        if isinstance(value, (list, tuple)):
            parts.extend(str(v) for v in value)
        elif value:
            parts.append(str(value))
    return " ".join(parts)


def _block_type_text(block: dict) -> str:
    """Type/style text carried by a location block: the block's own
    ``type`` / ``location_type`` / ``map_style`` fields plus a
    verbatim ``fields`` dict's TYPE / MAP_STYLE / LOCATION_TYPE
    values. A location whose TYPE says "map" must compose as a map
    even when its feature list names only regions — the type is
    script data carried by the package, never a substitution. (The
    trait-block builder does not carry ``type``; plan_shots
    supplements blocks from the preserved raw V1 record — see
    _enrich_location_block — and blocks that already carry the data
    work without it.)"""
    parts = []
    for key in ("type", "location_type", "map_style"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    fields = block.get("fields")
    if isinstance(fields, dict):
        for key in ("TYPE", "MAP_STYLE", "LOCATION_TYPE"):
            value = fields.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value)
    return " ".join(parts)


# Map-region label filter: feature entries that DESCRIBE the map
# (borders, boundaries) are not region names and must not label a
# region patch. Generic map vocabulary, never story values.
_MAP_LABEL_SKIP = ("biên giới", "border", "ranh giới", "boundary")


def compose_location(location_data: dict, *, mood: str = "warm",
                     time_of_day: str = "day") -> dict:
    """Compose an environment FROM a §15.3 location trait block.

    Returns {boxes, sky_top, sky_bottom, rainy, ground_color, kind,
    used_features, unused_features, forbidden_applied}. Layer texts
    (foreground/midground/background) and FEATURES are scanned with
    the generic vocabulary; FORBIDDEN entries suppress features they
    name; PALETTE tints the boxes; LIGHTING/WEATHER set sky/rain.
    Tolerant of missing keys and of the new-dialect field spellings
    (distinctive_features / color_palette). Never raises on data.
    """
    block = dict(location_data or {})
    render_traits = block.get("render_traits") or {}
    if not isinstance(render_traits, dict):
        render_traits = {}
    features = block.get("features")
    if features is None:
        features = block.get("distinctive_features") or []
    if isinstance(features, str):
        features = [features]
    palette = block.get("palette")
    if palette is None:
        palette = block.get("color_palette") or []
    if isinstance(palette, str):
        palette = [p.strip() for p in palette.split(",")]
    colors = [c for c in (_parse_color(p) for p in (palette or []))
              if c is not None]
    forbidden = block.get("forbidden") or []
    if isinstance(forbidden, str):
        forbidden = [forbidden]
    forbidden_texts = [str(f).lower() for f in forbidden]
    layer_text = _trait_text(
        block, "foreground", "midground", "background")
    all_text = " ".join([
        _trait_text(block, "name", "geography", "architecture",
                    "lighting", "weather", "period"),
        _block_type_text(block),
        layer_text,
        " ".join(str(f) for f in features),
        _trait_text(render_traits, "setting"),
    ])
    feature_keys = _features_in(all_text)
    # FORBIDDEN suppresses a feature when a forbidden entry names
    # one of the feature's keywords.
    forbidden_applied = []
    kept = []
    for key in feature_keys:
        keywords = next((kw for kw, k in _FEATURE_KEYWORDS if k == key),
                        ())
        if any(any(kw in ftext for kw in keywords)
               for ftext in forbidden_texts):
            forbidden_applied.append(key)
            continue
        kept.append(key)
    feature_keys = kept
    kind = next((k for k in _KIND_PRIORITY if k in feature_keys),
                "generic")
    tod = render_traits.get("time_of_day") or time_of_day or "day"
    mood_v = render_traits.get("mood") or mood or "warm"
    weather_text = _trait_text(block, "weather", "lighting")
    rainy = _has_any_word(
        (weather_text + " " + all_text).lower(), _RAIN_WORDS)
    sky_top, sky_bottom, ground = _sky_and_ground(
        kind, str(tod).lower(), str(mood_v).lower(), weather_text, rainy)
    # Map labels and sign labels come ONLY from location data. Map
    # region labels skip description entries (borders are not region
    # names) and strip trailing periods, so a region is labelled with
    # a place name from the script's own feature list.
    if kind == "map_panel":
        label_entries = [str(f).strip().rstrip(".")
                         for f in features
                         if not _has_any_word(
                             str(f).lower(), _MAP_LABEL_SKIP)]
        map_labels = "|".join(label_entries[:6])
    else:
        map_labels = ""
    sign_label = ""
    for needle, text in SIGN_LABELS:
        if needle in all_text.lower():
            sign_label = text
            break
    if feature_keys:
        boxes = _compose_from_features(
            feature_keys, colors, sign_label=sign_label,
            map_labels=map_labels)
    else:
        boxes = _generic_neutral_boxes(colors)
    used, unused = [], []
    for entry in features:
        entry_text = str(entry)
        hits = _features_in(entry_text)
        weather_hit = _has_any_word(entry_text.lower(),
                                    _RAIN_WORDS + _NIGHT_WORDS)
        if hits or weather_hit:
            used.append(entry_text)
        else:
            unused.append(entry_text)
    return {
        "boxes": boxes, "sky_top": sky_top, "sky_bottom": sky_bottom,
        "rainy": rainy, "ground_color": ground, "kind": kind,
        "used_features": used, "unused_features": unused,
        "forbidden_applied": forbidden_applied,
    }


def compose_inline(location_text: str, *, mood: str = "warm",
                   time_of_day: str = "day",
                   setting: str = "") -> dict:
    """Compose an environment from inline location text (SPEC §11.4)
    through the same generic vocabulary as compose_location. Returns
    the same dict shape (used/unused refer to the text as one entry).
    """
    text = " ".join(p for p in (location_text or "", setting or "")
                    if p)
    feature_keys = _features_in(text)
    kind = next((k for k in _KIND_PRIORITY if k in feature_keys),
                "generic")
    rainy = _has_any_word(text.lower(), _RAIN_WORDS)
    sky_top, sky_bottom, ground = _sky_and_ground(
        kind, str(time_of_day).lower(), str(mood).lower(), text, rainy)
    sign_label = ""
    for needle, text_label in SIGN_LABELS:
        if needle in text.lower():
            sign_label = text_label
            break
    if feature_keys:
        boxes = _compose_from_features(
            feature_keys, [], sign_label=sign_label)
    else:
        boxes = _generic_neutral_boxes([])
    return {
        "boxes": boxes, "sky_top": sky_top, "sky_bottom": sky_bottom,
        "rainy": rainy, "ground_color": ground, "kind": kind,
        "used_features": [text] if feature_keys else [],
        "unused_features": [] if feature_keys else [text],
        "forbidden_applied": [],
    }


def _register_composed_package(location_data: dict, composed: dict):
    """Register a composed environment in the scene-package registry
    under its location id (never a story name), so the same location
    reuses the same package. Best-effort: never raises."""
    try:
        loc_id = (location_data or {}).get("location_id") \
            or (location_data or {}).get("id")
        if not loc_id or not isinstance(loc_id, str):
            return
        if loc_id == "rainy_street_night":
            return
        boxes = list(composed["boxes"])
        sky_top = composed["sky_top"]
        sky_bottom = composed["sky_bottom"]
        ground = composed["ground_color"]

        def _builder(camera, characters, **options):
            return Scene25D(
                boxes=list(boxes), characters=list(characters),
                camera=camera,
                sky_top=options.get("sky_top", sky_top),
                sky_bottom=options.get("sky_bottom", sky_bottom),
                ground_color=options.get("ground_color", ground),
                ground_extent=options.get("ground_extent", 30.0))

        register_scene_package(loc_id, _builder)
    except Exception:  # noqa: BLE001 - registration is best-effort
        pass


def _boxes_from_landmark(name: str) -> list[Box3D]:
    out = []
    for b in landmark_boxes(name):
        out.append(Box3D(center=tuple(b["center"]), size=tuple(b["size"]),
                         color=tuple(b["color"]),
                         name=b.get("name", "box"),
                         label=b.get("label", "")))
    return out


def _shot_location_kind(shot: dict):
    """The composed environment kind for a shot: map-type trait
    blocks -> "map_panel" (environment_v2 MAP detection), other
    trait blocks -> compose_location's kind, inline text ->
    compose_inline, else None for the legacy keyword path. Pure:
    safe to call before the scene build (the build re-composes).
    Used for camera decisions that depend on the environment's
    orientation — a map board faces the camera."""
    location_data = shot.get("v1_location")
    if location_data is not None:
        # W2: map detection via the environment engine's archetype
        # selection (a map TYPE always defers to map_renderer);
        # anything else keeps the compose_location kind.
        if isinstance(location_data, dict):
            arch, _, _ = select_archetype(location_data)
            if arch == "MAP":
                return "map_panel"
        return compose_location(
            location_data, mood=shot.get("mood", "warm"),
            time_of_day=shot.get("time_of_day", "day"))["kind"]
    location_text = shot.get("location_text", "")
    if (location_text or "").strip():
        return compose_inline(
            location_text, mood=shot.get("mood", "warm"),
            time_of_day=shot.get("time_of_day", "day"),
            setting=shot.get("setting", ""))["kind"]
    return None


def _bus_extra_elements() -> list[dict]:
    """The F6 bus as environment-v2 box elements (MG layer).

    Same geometry/colours as the legacy bus Box3Ds in _render_shot,
    expressed as environment elements so the environment renderer
    draws the bus with the same shading/shadows as the location.
    """
    specs = [
        ("bus_body", BUS_BODY_CENTER, BUS_BODY_SIZE, (40, 90, 130)),
        ("bus_window_1", (2.0, 1.4, -2.95), (0.6, 0.5, 0.08),
         (255, 220, 130)),
        ("bus_window_2", (2.8, 1.4, -2.95), (0.6, 0.5, 0.08),
         (255, 220, 130)),
        ("bus_window_3", (3.4, 1.4, -2.95), (0.6, 0.5, 0.08),
         (255, 220, 130)),
        ("bus_door", (BUS_DOOR_X, 0.9, -2.95), (0.5, 1.4, 0.08),
         (20, 40, 60)),
        ("bus_wheel_1", (BUS_WHEEL_X[0], 0.15, -2.95),
         (0.4, 0.3, 0.1), (20, 20, 24)),
        ("bus_wheel_2", (BUS_WHEEL_X[1], 0.15, -2.95),
         (0.4, 0.3, 0.1), (20, 20, 24)),
    ]
    return [{"id": name, "kind": "bus_part", "layer": "MG",
             "geometry": "box", "center": tuple(map(float, center)),
             "size": tuple(map(float, size)), "color": color,
             "material": "painted_metal", "attachment": None,
             "label": "", "extra": {}}
            for name, center, size, color in specs]


# Map country aliases (general gazetteer data, never story content):
# (match phrases in a LOCATION feature, dataset NAME candidates,
# Vietnamese label). A feature matches only when its normalised
# text EQUALS a match phrase — a country list item, never a
# sentence that merely mentions a country ("Anh hùng" must not
# highlight England). Candidates are tried in order: the first
# gets the label, the rest are colour-only, so a historical
# dataset's single "Austria-Hungary" feature and a modern
# dataset's "Austria"+"Hungary" pair both highlight correctly.
# Unmatched candidates are reported by map_renderer, never silent.
_MAP_COUNTRY_ALIASES = (
    # Candidates include the OHM 1914 period NAMEs (registry dataset
    # ohm_1914_europe) so highlight matching is exact against the
    # verified geometry; the short names stay for other datasets.
    (("đế quốc đức", "nước đức", "germany"),
     ("germany", "german reich"), "Đức"),
    (("đế quốc áo-hung", "áo-hung", "austria-hungary"),
     ("austria-hungary", "austria", "hungary"), "Áo-Hung"),
    (("pháp", "france"), ("france", "french republic"), "Pháp"),
    (("đế quốc nga", "nước nga", "russia"),
     ("russia", "russian empire"), "Nga"),
    (("anh", "england", "united kingdom", "great britain"),
     ("united kingdom", "great britain", "england",
      "united kingdom of great britain and ireland"), "Anh"),
    (("bỉ", "belgium"), ("belgium",), "Bỉ"),
    (("serbia", "xéc-bi-a"), ("serbia", "kingdom of serbia"), "Serbia"),
    (("ý", "italy"), ("italy",), "Ý"),
    (("tây ban nha", "spain"), ("spain",), "Tây Ban Nha"),
    (("bồ đào nha", "portugal"), ("portugal",), "Bồ Đào Nha"),
    (("hà lan", "netherlands", "holland"),
     ("netherlands", "kingdom of the netherlands"), "Hà Lan"),
    (("thổ nhĩ kỳ", "ottoman", "turkey", "ottoman empire"),
     ("turkey", "ottoman empire"), "Thổ Nhĩ Kỳ"),
    (("hy lạp", "greece"), ("greece", "kingdom of greece"), "Hy Lạp"),
    (("đan mạch", "denmark"), ("denmark",), "Đan Mạch"),
    (("na uy", "norway"), ("norway",), "Na Uy"),
    (("thụy điển", "sweden"), ("sweden",), "Thụy Điển"),
    (("thụy sĩ", "switzerland"), ("switzerland",), "Thụy Sĩ"),
    (("ba lan", "poland"), ("poland",), "Ba Lan"),
    (("séc", "bohemia", "czech"), ("czech republic", "czechia",
                                  "bohemia"), "Séc"),
    (("rumani", "romania"), ("romania", "kingdom of romania"), "Rumani"),
    (("bungari", "bulgaria"),
     ("bulgaria", "tsardom of bulgaria"), "Bungari"),
    (("hoa kỳ", "mỹ", "united states", "america"),
     ("united states of america", "united states"), "Hoa Kỳ"),
)


def _normalise_feature_text(text: str) -> str:
    """Lowercase, punctuation stripped, whitespace collapsed."""
    out = []
    for ch in str(text).lower():
        out.append(ch if (ch.isalnum() or ch in (" ", "-")) else " ")
    return " ".join("".join(out).split())


def _map_highlight_entries(traits: dict) -> list[dict]:
    """Highlight entries for the countries a map LOCATION names.

    Only exact feature matches (see _MAP_COUNTRY_ALIASES). Returns
    [] when the location names no known country — the map still
    renders, with no highlights, and the report says so.
    """
    features = traits.get("features") or []
    if isinstance(features, str):
        features = [features]
    normalised = {_normalise_feature_text(f) for f in features}
    entries = []
    seen_labels = set()
    for phrases, candidates, label in _MAP_COUNTRY_ALIASES:
        if label in seen_labels:
            continue
        if not any(p in normalised for p in phrases):
            continue
        seen_labels.add(label)
        for i, candidate in enumerate(candidates):
            entries.append({"region": candidate,
                            "label": label})
    return entries


def _map_spec_from_shot(shot: dict, package: dict) -> dict:
    """A map_renderer spec from the shot's trait block + map config.

    Mode defaults to "historical" (year from the trait block's
    period). The dataset comes from ``package["map_config"]``
    (dataset_path / dataset_ref / provenance) — with no dataset
    configured, render_map raises MissingHistoricalMapData naming
    the candidates: the pipeline refuses to render modern borders
    as historical. "modern" mode is allowed only when explicitly
    configured AND the location's FORBIDDEN list does not ban
    modern borders, or when an explicit recorded override
    (override_forbidden + override_note) is supplied. Routes come
    only from explicit data (map_config["route"] or the shot's
    map_route) — never mined from text, never invented.
    """
    traits = shot.get("v1_location") or {}
    cfg = package.get("map_config") or {}
    mode = str(cfg.get("mode", "historical")).lower()
    loc_id = traits.get("id") or traits.get("location_id") or "?"
    forbidden = [str(f) for f in (traits.get("forbidden") or [])]
    forbids_modern = [f for f in forbidden
                      if any(w in f.lower()
                             for w in ("modern", "hiện đại"))]
    if mode == "modern" and forbids_modern and not (
            cfg.get("override_forbidden") and cfg.get("override_note")):
        raise MapSpecError(
            f"Map location {loc_id} forbids modern borders "
            f"(FORBIDDEN: {forbids_modern[0]!r}) but map mode "
            "'modern' was requested. Render historical mode with a "
            "verified dataset, or record an explicit override "
            "(map_config override_forbidden + override_note). "
            "Refusing to render modern boundaries against the "
            "script's own constraint.")
    spec = {"mode": mode,
            "year": traits.get("period") or cfg.get("year") or "",
            "size": (W, H),
            "highlight": _map_highlight_entries(traits)}
    if mode == "historical":
        if cfg.get("dataset_path"):
            spec["dataset_path"] = cfg["dataset_path"]
        if cfg.get("dataset_ref"):
            spec["dataset_ref"] = cfg["dataset_ref"]
        if cfg.get("provenance"):
            spec["provenance"] = cfg["provenance"]
        if not spec.get("dataset_path") and not spec.get("dataset_ref"):
            # No explicit dataset configured: consult the historical
            # dataset registry (assets/maps/). Only a VERIFIED entry
            # with a matching checksum is admitted; anything else
            # leaves the spec unset so render_map raises the
            # MissingHistoricalMapData gate as before. A registry
            # refusal for a reason OTHER than "no verified dataset"
            # (tamper, missing file) fails loudly here instead of
            # being hidden behind the generic gate message.
            from ai_clip_studio.map_registry import (
                RegistryError, resolve_for_year)
            try:
                year = int(str(spec.get("year") or "")[:4])
            except ValueError:
                year = None
            if year is not None:
                try:
                    rec = resolve_for_year(year)
                except RegistryError as exc:
                    if "no VERIFIED" not in str(exc):
                        raise MapSpecError(str(exc)) from exc
                else:
                    spec["dataset_path"] = rec["geometry_path"]
                    spec["provenance"] = rec["provenance"]
                    if rec.get("attribution"):
                        spec["attribution"] = rec["attribution"]
                    # The registry dataset's recommended framing keeps
                    # the map on the verified region instead of the
                    # relations' full unclipped geometry (e.g. the
                    # Russian Empire to +/-180). Explicit shot framing
                    # always wins.
                    if rec.get("recommended_framing") and not cfg.get(
                            "framing"):
                        spec["framing"] = rec["recommended_framing"]
    route = cfg.get("route") or shot.get("map_route")
    if route:
        route = dict(route)
        # A static shot background shows the complete schematic
        # route unless the route carries its own progress.
        route.setdefault("progress_t", 1.0)
        spec["route"] = route
    return spec


def _render_map_background(shot: dict, package: dict):
    """Full-frame map background + report for a map shot (W2b).

    Raises MissingHistoricalMapData / MapSpecError from the spec
    builder or render_map — a map shot without a usable dataset
    fails the job loudly, with the decision named in the error.
    """
    spec = _map_spec_from_shot(shot, package)
    img, report = render_map(spec)
    cfg = package.get("map_config") or {}
    if cfg.get("override_forbidden"):
        report["forbidden_override"] = {
            "note": cfg.get("override_note", "")}
    return img, report


def build_scene_ex_with_package(
        location_keyword: str, setting: str, mood: str,
        time_of_day: str, location_data=None, location_text: str = "",
        extra_elements=None) -> tuple:
    """build_scene_ex + the EnvironmentPackage + is_map flag.

    Returns ``(boxes, sky_top, sky_bottom, rainy, ground_color,
    env_pkg, is_map)``. Dict trait blocks build through
    environment_v2 (visual recovery W2): the returned ``boxes``
    are the box-geometry elements (for the legacy Scene25D path
    and the registry); the full package — gable prisms, blobs,
    layers, light, provenance — rides in ``env_pkg`` for the
    environment renderer. Map-type trait blocks return an empty
    box list, the ``map_deferred`` package and ``is_map=True``:
    the caller renders the background via map_renderer. Non-dict
    trait data and the inline/keyword paths delegate to
    build_scene_ex unchanged (env_pkg None, is_map False).
    """
    if isinstance(location_data, dict):
        env_pkg = build_environment(
            location_data, time_of_day=time_of_day,
            style={"mood": mood,
                   "extra_elements": list(extra_elements or [])})
        if env_pkg.get("kind") == "map_deferred":
            light = light_for(time_of_day, mood)
            return ([], light["sky_top"], light["sky_bottom"], False,
                    (122, 112, 96), env_pkg, True)
        boxes = [Box3D(**d) for d in to_box_dicts(env_pkg)]
        light = env_pkg.get("light") or {}
        sky_top = tuple(light.get("sky_top", (135, 180, 220)))
        sky_bottom = tuple(light.get("sky_bottom", (200, 220, 240)))
        ground_color = tuple(
            env_pkg.get("ground", {}).get("color", (96, 92, 84)))
        weather = str(location_data.get("weather") or "")
        setting_low = (setting or "").lower()
        rainy = (location_keyword == "rainy_street"
                 or any(w in weather.lower() for w in ("rain", "mưa"))
                 or "mưa" in setting_low or "rain" in setting_low)
        _register_composed_package(location_data, {
            "boxes": boxes, "sky_top": sky_top,
            "sky_bottom": sky_bottom, "rainy": rainy,
            "ground_color": ground_color, "kind": "environment_v2",
            "archetype": env_pkg.get("archetype")})
        return (boxes, sky_top, sky_bottom, rainy, ground_color,
                env_pkg, False)
    boxes, sky_top, sky_bottom, rainy, ground_color = build_scene_ex(
        location_keyword, setting, mood, time_of_day,
        location_data=location_data, location_text=location_text)
    return (boxes, sky_top, sky_bottom, rainy, ground_color, None,
            False)


def build_scene_ex(location_keyword: str, setting: str, mood: str,
                   time_of_day: str, location_data=None,
                   location_text: str = "") -> tuple:
    """Location -> (boxes, sky_top, sky_bottom, rainy, ground_color).

    Dispatch (visual recovery W2 supersedes the Stage 3 / F5
    dispatch for rendering):
    * ``location_data`` (a §15.3 trait block, dict) ->
      environment_v2 via build_scene_ex_with_package: the world is
      composed FROM the trait data (archetype-selected semantic
      environments; map types defer to map_renderer).
    * non-dict ``location_data`` -> compose_location (legacy).
    * else ``location_text`` (inline text) -> compose_inline: the
      generic keyword vocabulary reads the text.
    * else the legacy keyword path (landmarks / generic street),
      behaviour unchanged except that shop signage is data-driven.
    A composed trait-block environment is registered in the
    scene-package registry under its location id.
    """
    if isinstance(location_data, dict):
        (boxes, sky_top, sky_bottom, rainy, ground_color, _pkg,
         _is_map) = build_scene_ex_with_package(
             location_keyword, setting, mood, time_of_day,
             location_data=location_data, location_text=location_text)
        return boxes, sky_top, sky_bottom, rainy, ground_color
    if location_data is not None:
        composed = compose_location(
            location_data, mood=mood, time_of_day=time_of_day)
        _register_composed_package(location_data, composed)
        return (composed["boxes"], composed["sky_top"],
                composed["sky_bottom"], composed["rainy"],
                composed["ground_color"])
    if (location_text or "").strip():
        composed = compose_inline(
            location_text, mood=mood, time_of_day=time_of_day,
            setting=setting)
        return (composed["boxes"], composed["sky_top"],
                composed["sky_bottom"], composed["rainy"],
                composed["ground_color"])
    setting_low = (setting or "").lower()
    rainy = (location_keyword == "rainy_street" or "mưa" in setting_low
             or "rain" in setting_low)
    night = time_of_day == "night" or rainy
    if night:
        sky = ((28, 42, 72), (130, 142, 165))
        ground = (78, 72, 66)
    elif mood == "cold":
        sky = ((90, 120, 160), (170, 190, 210))
        ground = (90, 88, 84)
    else:
        sky = ((135, 180, 220), (200, 220, 240))
        ground = (96, 92, 84)
    boxes: list[Box3D] = []
    if location_keyword == "great_wall":
        boxes += _boxes_from_landmark("great_wall")
        boxes.append(Box3D(center=(0.0, 0.05, 1.0), size=(14.0, 0.1, 0.4),
                           color=(120, 110, 96), name="path_fg"))
    elif location_keyword == "eiffel_tower":
        boxes += _boxes_from_landmark("eiffel_tower")
        for cx, cw in ((-4.5, 2.4), (4.8, 2.2)):
            boxes.append(Box3D(center=(cx, 1.2, -11.0), size=(cw, 2.4, 1.5),
                               color=(96, 88, 110), name="paris_roof"))
        boxes.append(Box3D(center=(0.0, 0.05, 1.0), size=(14.0, 0.1, 0.4),
                           color=(120, 110, 96), name="path_fg"))
    else:
        # Generic street corner (the v7 proven layout): background
        # buildings with lit windows, midground lamp/bench/sign,
        # foreground crate + railing + path.
        boxes += [
            Box3D(center=(-4.5, 1.5, -12.0), size=(2.4, 3.0, 1.5),
                  color=(74, 88, 118), name="building_left"),
            Box3D(center=(-0.5, 2.0, -14.0), size=(3.2, 4.0, 1.5),
                  color=(66, 80, 110), name="building_center"),
            Box3D(center=(4.8, 1.3, -11.0), size=(2.2, 2.6, 1.5),
                  color=(80, 94, 124), name="building_right"),
        ]
        for wx, wy, wz in ((-5.2, 1.6, -11.15), (-3.8, 2.4, -11.15),
                           (-1.5, 2.0, -13.15), (0.5, 3.0, -13.15),
                           (4.2, 1.5, -10.15), (5.4, 1.5, -10.15)):
            boxes.append(Box3D(center=(wx, wy, wz), size=(0.5, 0.7, 0.1),
                               color=(255, 200, 90), name="window"))
        label = ""
        for needle, text in SIGN_LABELS:
            if needle in setting_low:
                label = text
                break
        # Shop signage is DATA-DRIVEN (Stage 3): a shop sign appears
        # only when the setting text names that shop. The old code
        # unconditionally painted PHỞ + CÀ PHÊ signs on every generic
        # street — a location substitution (a Munich scene must never
        # show them). The bus-stop label stays on the sign board
        # only, never as a shop sign.
        shop_slots = [
            (-4.5, 2.3, -11.15, (90, 30, 30), "shop_sign_1"),
            (4.8, 2.1, -10.15, (30, 60, 90), "shop_sign_2"),
        ]
        seen_shop_labels: set[str] = set()
        for needle, text in SIGN_LABELS:
            if text == "TRẠM XE BUÝT" or text in seen_shop_labels:
                continue
            if needle in setting_low and shop_slots:
                seen_shop_labels.add(text)
                scx, scy, scz, scol, sname = shop_slots.pop(0)
                boxes.append(Box3D(
                    center=(scx, scy, scz), size=(1.3, 0.5, 0.08),
                    color=scol, name=sname, label=text))
        boxes += [
            Box3D(center=(4.0, 1.6, -1.5), size=(0.14, 3.2, 0.14),
                  color=(30, 32, 40), name="lamp_post"),
            Box3D(center=(4.0, 3.3, -1.5), size=(0.55, 0.22, 0.55),
                  color=(255, 211, 78), name="lamp_head"),
            Box3D(center=(2.6, 0.22, -2.5), size=(1.9, 0.45, 0.6),
                  color=(122, 74, 43), name="bench"),
            Box3D(center=(0.2, 1.3, -2.0), size=(0.1, 2.6, 0.1),
                  color=(30, 32, 40), name="sign_post"),
            Box3D(center=(0.2, 2.7, -2.0), size=(1.0, 0.6, 0.08),
                  color=(23, 32, 51), name="sign", label=label),
            Box3D(center=(0.2, 3.15, -2.0), size=(2.4, 0.12, 1.2),
                  color=(120, 40, 40), name="awning"),
            Box3D(center=(0.0, 0.08, -1.2), size=(14.0, 0.16, 0.6),
                  color=(150, 148, 140), name="kerb"),
            Box3D(center=(2.2, 0.25, 1.5), size=(0.5, 0.5, 0.5),
                  color=(139, 94, 52), name="crate_fg"),
            Box3D(center=(0.0, 0.05, 1.0), size=(14.0, 0.1, 0.4),
                  color=(96, 90, 82), name="path_fg"),
            Box3D(center=(-3.4, 0.5, 1.2), size=(1.8, 0.1, 0.1),
                  color=(40, 42, 50), name="railing_fg"),
        ]
    return boxes, sky[0], sky[1], rainy, ground


def build_scene(location_keyword: str, setting: str, mood: str,
                time_of_day: str, location_data=None,
                location_text: str = "") -> tuple:
    """Location -> (boxes, sky_top, sky_bottom, rainy). The 4-tuple
    contract build_scene_ex extends with the ground colour; see
    build_scene_ex for the Stage 3 / F5 dispatch rules."""
    boxes, sky_top, sky_bottom, rainy, _ground = build_scene_ex(
        location_keyword, setting, mood, time_of_day,
        location_data=location_data, location_text=location_text)
    return boxes, sky_top, sky_bottom, rainy


def split_foreground_boxes(boxes, plane_z: float = WORLD_Z):
    """Partition boxes by depth vs the character plane (Stage 3 /
    Fix 3): (background_boxes, foreground_boxes). A box whose centre
    stands in front of the character plane (z > plane_z) is
    foreground — EXCEPT flat ground slabs (path/kerb), which always
    stay in the background: a slab lying on the ground must never
    swallow the feet standing on it. Only genuinely-in-front boxes
    occlude characters."""
    bg, fg = [], []
    for box in boxes:
        if box.center[2] > plane_z and not box.is_flat_ground_slab():
            fg.append(box)
        else:
            bg.append(box)
    return bg, fg


# Cues that get their own action shot (one visible movement each).
# put_away has no movement primitive (idle) but it is a real beat:
# the prop disappears into a pocket/bag after it.
MOVEMENT_CUES = ("walk", "walk_fast", "run", "bend_pick", "give", "wave",
                 "turn_back", "board", "sit", "stand", "take", "search",
                 "put_away")
# Beat after each spoken line (same value as TimelineLine.pause_after_sec):
# the speaker holds the pose a beat before the cut. The line shot's
# duration is voice + this beat, so the video length matches the
# timeline total (voice + pauses + action leads + tail) exactly.
PAUSE_AFTER_SEC = 0.35


# --- Shot Planner V2 helpers (Cinematic Engine Upgrade, Phase B) ---

# Locomotion cues: the character travels across the frame during the
# shot. Head framings must not be paired with these by default — with
# the frozen D2 crop the head walks out of the frame (TEST C f23).
LOCOMOTION_CUES = ("walk", "walk_fast", "run", "board")

# Head framings: the crop anchors on the head.
HEAD_FRAMING_TYPES = frozenset({
    "close_up", "extreme_close_up", "reaction", "medium_close_up",
    "shot_reverse_shot",
})

# Shot duration policy (directive §5): default target 2-5 s per shot;
# a voice longer than SHOT_SPLIT_VOICE_SEC splits into segments
# targeting ~3 s each; any shot longer than SHOT_WARN_SEC warns
# unless justified (environmental reveal / explicit script reason).
SHOT_SPLIT_VOICE_SEC = 6.0
SHOT_WARN_SEC = 6.0
SHOT_TARGET_SEC = 3.0
SHOT_MAX_SEGMENT_SEC = 5.0


# --- Shot Planner rewire (Semantic Engine Upgrade, directive §10) ---
# The planner is a PRESENTATION layer: it consumes the canonical
# scene graph (compiled events + provenance) and the measured line
# durations, and never invents an action. Lead-shot durations come
# from the compiled event spans of each directive (see
# _directive_event_span). Cue filtering is NOT the planner's job:
# the stage-2b semantic pass discards losing cues from the package
# before planning, and the planner stages only what survives. (An
# earlier planner-level drop rule false-dropped legitimate staged
# actions -- sit/stand/take/open/run/board -- whose verbs the
# compiler does not emit; single authority wins.)


def _graph_shot_events(scene_graph: dict | None
                       ) -> dict[str, list[dict]]:
    """Directive shot id -> compiled event nodes, from the canonical
    scene graph. Empty when no graph was supplied (legacy planning)."""
    if not scene_graph:
        return {}
    events = scene_graph.get("events") or {}
    by_shot: dict[str, list[dict]] = {}
    for shot_id, shot in (scene_graph.get("shots") or {}).items():
        nodes = [events[eid] for eid in shot.get("event_ids", [])
                 if eid in events]
        if nodes:
            by_shot[str(shot_id)] = nodes
    return by_shot


def _directive_event_span(nodes: list[dict]) -> float:
    """How long a directive's compiled events take to perform.

    The early compile chains events sequentially as a binding
    convenience, which is NOT a duration model: repeated sentences
    describing one sustained action (four WALK_MUD events for one
    trudge through the mud) must not quadruple the shot, and
    different actors act concurrently. Rule: group by actor; within
    one actor, collapse consecutive runs of the same verb into one
    sustained performance (the run's longest single event); chain
    different verbs; take the max across actors.
    """
    by_actor: dict[str, list[dict]] = {}
    for node in nodes:
        key = str(node.get("actor_id") or node.get("action_id"))
        by_actor.setdefault(key, []).append(node)
    best = 0.0
    for actor_nodes in by_actor.values():
        total = 0.0
        run_verb: str | None = None
        run_best = 0.0
        for node in actor_nodes:
            verb = str(node.get("verb", ""))
            dur = max(0.0, float(node.get("end_time") or 0.0)
                      - float(node.get("start_time") or 0.0))
            if verb == run_verb:
                run_best = max(run_best, dur)
            else:
                total += run_best
                run_verb = verb
                run_best = dur
        total += run_best
        best = max(best, total)
    return best
SHOT_MIN_SEGMENT_SEC = 2.0

# Requested camera movement -> CameraMode (cinematic_contracts).
# CRANE_UP/CRANE_DOWN have no CameraMode: they stay recorded as
# requested and execute static (see _camera_mode_for note).
_CAMERA_MODE_BY_MOVEMENT = {
    "STATIC": "static_anchored",
    "PAN_LEFT": "scripted_pan", "PAN_RIGHT": "scripted_pan",
    "TILT_UP": "scripted_pan", "TILT_DOWN": "scripted_pan",
    "DOLLY_IN": "scripted_dolly", "DOLLY_OUT": "scripted_dolly",
    "TRACKING": "scripted_tracking",
    "HANDHELD": "scripted_shake",
}


def _camera_mode_for(movement: str) -> tuple:
    """Requested movement -> (CameraMode value, note or None).

    The mode records INTENT; execution is always static until the
    scripted renderer lands (§5.3), which the plan records
    separately as camera_mode_execution="static" — the request and
    the execution are never conflated."""
    mode = _CAMERA_MODE_BY_MOVEMENT.get(movement)
    if mode is not None:
        return mode, None
    return "static_anchored", (
        f"movement {movement} has no CameraMode; recorded as "
        "requested, executed static")


# Opening-hook type by shot type (directive §5 hook policy). Types
# absent here (medium, tracking, over_the_shoulder) carry no hook
# quality and the opening shot warns instead of being silently
# re-templated.
_HOOK_TYPE_BY_SHOT = {
    "object_insert": "object_insert",
    "close_up": "character_reaction",
    "extreme_close_up": "character_reaction",
    "medium_close_up": "character_reaction",
    "reaction": "character_reaction",
    "shot_reverse_shot": "character_reaction",
    "establishing": "environmental_reveal",
    "graphic_insert": "suspenseful_detail",
}


def _split_voice_spans(voice: float, n: int) -> list:
    """Split a voice duration into n near-equal spans (2 dp, the last
    absorbs rounding) summing to round(voice, 2)."""
    total = round(voice, 2)
    if n <= 1:
        return [total]
    base = round(total / n, 2)
    spans = [base] * (n - 1)
    spans.append(round(total - base * (n - 1), 2))
    return spans


def _segment_count(voice: float) -> int:
    """Segments for a long voice: target ~3 s each, every segment in
    [2, 5] s. A 12 s line -> 4 segments (the §5 example)."""
    n = round(voice / SHOT_TARGET_SEC)
    lo = math.ceil(voice / SHOT_MAX_SEGMENT_SEC)
    hi = max(lo, math.floor(voice / SHOT_MIN_SEGMENT_SEC))
    return max(lo, min(n, hi))


def _split_line_phrases(text: str, spans: list) -> list:
    """Partition a line's subtitle phrases across voice spans so each
    segment's text covers exactly its own time slice. Phrases are
    assigned by midpoint against the even time share each phrase
    occupies (matching how phrase_windows lays them out). Every
    phrase appears exactly once, in order; a span with no phrase
    midpoint gets an empty string — text is never invented."""
    phrases = split_subtitle(text) if (text or "").strip() else []
    if not phrases:
        return [""] * len(spans)
    total = sum(spans)
    bounds = []
    cursor = 0.0
    for span in spans:
        cursor += span
        bounds.append(cursor)
    out: list = []
    idx = 0
    for end in bounds:
        take = []
        while idx < len(phrases):
            mid = (idx + 0.5) / len(phrases) * total
            if mid < end:
                take.append(phrases[idx])
                idx += 1
            else:
                break
        out.append(" ".join(take))
    while idx < len(phrases):
        out[-1] = (out[-1] + " " + phrases[idx]).strip()
        idx += 1
    return out


def _progression_type(seg_idx, seg_count, cues, visible_count,
                      expression_non_neutral, prev_type, has_prop):
    """Shot type for a split segment after the first: visual variety
    across one uninterrupted line (establishing/action/insert/
    reaction grammar). Never repeats the previous segment's type
    when an alternative fits."""
    if seg_idx == seg_count - 1:
        want = "reaction" if visible_count > 1 else (
            "close_up" if expression_non_neutral else "medium")
    elif seg_idx == 1:
        if any(c in cues for c in ("give", "take", "bend_pick")):
            want = "object_insert"
        elif any(c in cues for c in LOCOMOTION_CUES):
            want = "tracking"
        else:
            want = "medium"
    else:
        want = "object_insert" if has_prop else "medium"
    if want == prev_type:
        want = "medium" if prev_type != "medium" else "close_up"
    return want


def _viewpoint_signature(shot: dict) -> tuple:
    """Plan-level viewpoint identity (cf. camera_planner's
    validate_camera_sequence, which compares azimuth/elevation/
    radius): angle + subject + SRS side + OTS counterpart +
    establishing radius class, scoped to one scene (a location
    change is always a new viewpoint context). Crop scale is
    deliberately excluded: same camera, different crop is a
    legitimate framing change by cut and is reported, not flagged
    as redundant, by the caller."""
    return (
        shot["scene"],
        shot.get("camera_angle"),
        shot.get("directive_subject") or shot.get("actor")
        or shot.get("speaker"),
        shot.get("ots_counterpart"),
        shot.get("srs_side")
        if shot["shot_type"] == "shot_reverse_shot" else None,
        shot["shot_type"] == "establishing",
        shot["shot_type"] == "over_the_shoulder",
    )


def plan_shots(package: dict, timeline: list[dict],
               scene_graph: dict | None = None) -> list[dict]:
    """Package + measured line durations -> ordered shot list.

    Shot Planner V2 (Cinematic Engine Upgrade, Phase B), rewired to
    the canonical scene graph (Semantic Engine Upgrade, §10). The
    shot list is built from the script's own structure: every SHOT
    directive shapes exactly one shot (scene-level directives in
    script order over the action lead; line-linked directives over
    their line), and every spoken line is covered exactly once.
    Durations are separated and recorded per shot: voice span,
    narrative beat (0.35 s after each line), action-lead share, and
    the shot total — see ``duration_breakdown``. One continuous
    audio timeline: a long narration line MAY span several shots
    (voice > 6 s splits into 2-5 s segments, each carrying its own
    voice span + subtitle phrases, the narration never duplicated,
    restarted, truncated or rewritten); one shot covers one line
    (multi-line shots are permitted by the format but the planner
    does not merge lines on its own).

    Shot duration policy: default target 2-5 s; shots over 6 s
    carry ``duration_warning`` unless justified (an establishing
    environmental reveal, or an explicit script justification).
    Hook policy: the opening shot carries ``hook_type`` from its
    framing (object insert / character reaction / environmental
    reveal / suspenseful detail); a non-hook opening warns rather
    than being silently re-templated. Reveal policy: when the
    package declares a twist (the last spoken line, verbatim), the
    shot covering it carries ``is_reveal_shot``; no twist is ever
    invented. Pairing rule: a head framing on a locomotion segment
    carries ``pairing_warning`` (the frozen D2 crop would let the
    head exit the frame) — the directive still wins, loudly.
    Consecutive shots resolving to the same viewpoint carry
    ``repeated_framing_warning`` on the later shot (a location
    change always breaks the comparison). Camera: ``camera_movement``
    keeps the REQUESTED movement; ``camera_mode`` records the
    CameraMode intent + source, and ``camera_mode_execution`` is
    "static" until scripted execution lands — request and execution
    are never conflated. Every shot also carries ``cut_before``
    (True except the first shot) and, for locomotion shots,
    ``locomotion_direction`` (+1/-1 toward the other character).

    Total duration is preserved exactly: the sum of shot durations
    equals voice + pauses + action leads + end hold + end card, so
    TechnicalGate.timeline_sync (tolerance 0.6 s) passes. The prop
    holder is tracked across the shot list (bend_pick -> the picker
    holds it, give -> the receiver holds it, put_away -> hidden)
    per prop id when the package declares props, else as the single
    legacy holder. A scene with an explicit empty visible cast
    renders location-only. An end-card shot is appended when the
    package carries v1_end_card with a duration, and end_hold_sec
    extends the last content shot.

    When ``scene_graph`` is supplied (the pipeline's early compile),
    the planner consumes it: lead-shot durations come from the
    compiled event spans of each directive (actor-grouped, sustained
    actions collapsed -- see _directive_event_span), and every shot
    carries ``event_ids`` + ``duration_source``. A lead shot whose
    event span exceeds 6 s carries ``duration_justification``
    instead of a warning: the 2-5 s guideline is not mechanical.
    Cue filtering is not the planner's job (stage 2b owns it).
    Without a graph, planning is exactly the legacy cue-driven
    behaviour (``cue_validation`` "legacy").
    """
    durations = {e["line_index"]: e["duration"] for e in timeline}
    graph_events = _graph_shot_events(scene_graph)
    gemini_shots = {(s.get("scene"), s.get("line_index")): s.get("shot_type")
                    for s in package.get("gemini_shots", [])}
    # Shot directives (Stage 3 / F9): indexed by (scene, line_index)
    # for line shots and by scene for action leads (line_index None).
    directives_by_line: dict = {}
    directives_by_scene: dict = {}
    directive_collisions: dict = {}
    # Twist line (reveal policy): the package's verbatim twist text
    # is the last spoken line. The reveal flag lands on the shot(s)
    # covering that line — and only when the text matches verbatim,
    # so a twist is never invented or misattributed.
    twist_text = str(package.get("twist") or "").strip()
    total_lines = sum(len(sc.get("lines", []))
                      for sc in package["scenes"])
    for d in package.get("shot_directives", []) or []:
        if not isinstance(d, dict):
            continue
        scene_no = d.get("scene", d.get("scene_number"))
        line_idx = d.get("line_index", d.get("line"))
        shot_type = d.get("shot_type", d.get("type"))
        entry = {
            "shot_type": shot_type if shot_type in CAMERA_SHOT_TYPES
            else None,
            "camera_movement": _normalize_camera_movement(
                d.get("camera_movement")),
            "camera_angle": _normalize_camera_angle(
                d.get("camera_angle")),
            "subject": d.get("subject"),
            "counterpart": d.get("counterpart") or d.get("listener")
            or d.get("ots_counterpart"),
            "shot_id": d.get("shot_id"),
            # SRS side from the directive (adapter alternates per
            # shot); None means "no directive value" — plan_shots
            # falls back to its per-scene counter below.
            "srs_side": d.get("srs_side"),
            "location_override": d.get("location_override"),
            # Channel-study vocabulary (Stage 3): staging mode,
            # foreground occluder, shot-level character view,
            # split-screen sides, graphic-insert card spec. All
            # validated; invalid values degrade to None (standard
            # rendering), never a crash.
            "staging_mode": _normalize_staging_mode(
                d.get("staging_mode") or d.get("staging")),
            "occluder_side": _normalize_occluder_side(
                d.get("occluder_side")),
            "occluder_style": _normalize_occluder_style(
                d.get("occluder_style")),
            "character_view": _normalize_character_view(
                d.get("character_view")),
            "split_screen": _normalize_split_screen(
                d.get("split_screen")),
            "insert_card": _normalize_insert_card(
                d.get("insert_card")),
        }
        if line_idx is None:
            directives_by_scene.setdefault(scene_no, []).append(entry)
        elif (scene_no, line_idx) in directives_by_line:
            # Two directives for one line: the first wins, the rest
            # are recorded (never silently overwritten) and surfaced
            # on the line's shot as directive_collision_warning.
            directive_collisions.setdefault(
                (scene_no, line_idx), []).append(
                    entry.get("shot_id") or "UNKNOWN")
        else:
            directives_by_line[(scene_no, line_idx)] = entry
    # Prop registry (Stage 3 / F7): id -> kind/owner.
    prop_entries = [p for p in (package.get("props") or [])
                    if isinstance(p, dict) and p.get("id")]
    prop_kinds = {str(p["id"]): infer_prop_kind(p) for p in prop_entries}
    prop_owners = {str(p["id"]): p.get("owner") for p in prop_entries}
    holders: dict[str, object] = {
        pid: owner for pid, owner in prop_owners.items() if owner}
    legacy_holder = None
    shots: list[dict] = []
    line_no = 0
    char_names = [str(c["name"]) for c in package["characters"]]
    # First appearance: a character is visible only from the first
    # scene where they speak or act (a character who runs in during
    # scene 2 must not be standing in scene 1). Once introduced they
    # stay visible. Names with no appearance default to scene 1.
    first_scene: dict[str, int] = {}
    for _sc in package["scenes"]:
        _num = _sc["number"]
        for _line in _sc.get("lines", []):
            _sp = _line.get("speaker")
            if _sp and _sp != "narrator" and _sp in char_names:
                first_scene.setdefault(_sp, _num)
        for _cue in _sc.get("action_cues") or []:
            _actor = action_actor(_sc.get("action_text", ""), [_cue],
                                  char_names)
            if _actor:
                first_scene.setdefault(_actor, _num)
    for _name in char_names:
        first_scene.setdefault(_name, 1)
    for scene in package["scenes"]:
        number = scene["number"]
        loc = scene.get("location", {}) or {}
        setting = loc.get("setting") or scene.get("setting", "")
        lead = float(scene.get("action_lead_sec") or 0.0)
        cues = list(scene.get("action_cues") or [])
        visible_override = _scene_visible_override(scene, char_names)
        visible = visible_override if visible_override is not None \
            else [n for n in char_names if first_scene[n] <= number]
        scene_location = {
            # §5.2: no invented default. An absent keyword is unknown
            # (""), never "street": the false default polluted every
            # location report and could hijack environment selection.
            "location_keyword": loc.get("location_keyword", ""),
            "setting": setting, "mood": loc.get("mood", "warm"),
            "time_of_day": loc.get("time_of_day", "day"),
        }
        scene_v1_location = _enrich_location_block(
            package,
            loc.get("v1_location") or scene.get("v1_location"))
        scene_location_text = scene.get("location_text") \
            or loc.get("location_text") or ""
        scene_movement = _normalize_camera_movement(
            scene.get("camera_movement")) \
            if scene.get("camera_movement") else "STATIC"
        scene_angle = _normalize_camera_angle(scene.get("camera_angle"))
        scene_costumes = _scene_costume_overrides(scene, package, number)
        # Scene props: prop ids in the scene (strings or dicts).
        scene_prop_ids: list[str] = []
        for _p in scene.get("props") or []:
            if isinstance(_p, dict) and _p.get("id"):
                scene_prop_ids.append(str(_p["id"]))
            elif isinstance(_p, str):
                scene_prop_ids.append(_p)
        active_prop = scene_prop_ids[0] if scene_prop_ids else None
        active_kind = None
        if active_prop is not None:
            active_kind = prop_kinds.get(
                active_prop,
                infer_prop_kind({"name": active_prop}))

        def _prop_fields():
            if active_prop is not None:
                return {
                    "prop_holder": holders.get(active_prop),
                    "prop_kind": active_kind,
                    "props": list(scene_prop_ids),
                    "prop_holders": dict(holders),
                }
            has_prop_cue = any(c in cues
                               for c in ("bend_pick", "give", "take"))
            return {
                "prop_holder": legacy_holder,
                "prop_kind": "wallet" if has_prop_cue else None,
                "props": list(scene_prop_ids),
                "prop_holders": dict(holders),
            }

        def _apply_location(entry, directive):
            """Apply a directive's location_override to a shot's
            location fields (resolved against the package's trait
            blocks); an unresolvable id keeps the scene location and
            is recorded, never a crash."""
            loc_fields = dict(scene_location)
            v1_location = scene_v1_location
            location_text = scene_location_text
            override = (directive or {}).get("location_override")
            if override:
                block = _resolve_location_block(package, override)
                if block is not None:
                    v1_location = _enrich_location_block(package, block)
                    location_text = _block_location_text(block)
                    loc_fields = _block_location_fields(
                        block, scene_location)
                    loc_fields["setting"] = location_text
                else:
                    entry["location_override_unresolved"] = override
            entry.update(loc_fields)
            entry["v1_location"] = v1_location
            entry["location_text"] = location_text
            return entry

        def _transfer_holder(cue, actor_name):
            """Update the tracked holder for a cue, on the active
            prop when the scene declares props, else the legacy
            single holder."""
            nonlocal legacy_holder
            if cue == "bend_pick":
                new_holder = actor_name
            elif cue == "give" and actor_name is not None:
                new_holder = next(
                    (n for n in char_names if n != actor_name), None)
            elif cue == "take":
                new_holder = actor_name
            elif cue == "put_away":
                new_holder = None
            else:
                return
            if active_prop is not None:
                holders[active_prop] = new_holder
            else:
                legacy_holder = new_holder

        scene_directives = directives_by_scene.get(number, [])
        graph_lead = bool(
            graph_events and any(
                graph_events.get(str(d.get("shot_id")))
                for d in scene_directives))
        # shot_reverse_shot alternation within this scene: consecutive
        # SRS line shots alternate sides (srs_side 0/1).
        srs_counter = 0
        if lead > 0.3 or graph_lead:
            # Planner V2: one segment per movement cue AND one per
            # scene-level directive, in script order — every
            # directive shapes exactly one shot. (The old code used
            # only scene_directives[0] for every lead shot, silently
            # dropping the rest: Ep1 SC01_SH03, SC03_SH03, SC06_SH03,
            # SC06_SH04 never rendered.)
            movement = [c for c in cues if c in MOVEMENT_CUES]
            if not movement and not scene_directives:
                # No visible movement, but the timeline budgets this
                # time — hold an idle beat so video == timeline.
                lead_shots = [(None, None, round(max(lead, 0.5), 2),
                               "idle_hold")]
            else:
                n_seg = max(len(movement) if movement else 1,
                            len(scene_directives))
                # Graph mode: a directive's lead duration is its
                # compiled event span (estimated spans from the early
                # compile), floored at 0.5 s. Directives without
                # events share the remaining cue budget by weight.
                span_dur: dict[int, float] = {}
                if graph_events:
                    for i in range(n_seg):
                        dir_i = scene_directives[i] \
                            if i < len(scene_directives) else None
                        nodes = graph_events.get(
                            str(dir_i.get("shot_id"))) \
                            if dir_i else None
                        if nodes:
                            span_dur[i] = round(
                                max(0.5, _directive_event_span(nodes)),
                                2)
                weights = []
                for i in range(n_seg):
                    cue_i = movement[i] if i < len(movement) else None
                    weights.append(
                        ACTION_LEAD_SECONDS.get(cue_i, 1.0)
                        if cue_i else 1.0)
                total_w = sum(weights)
                remaining = max(
                    0.0, lead - sum(span_dur.values())) \
                    if span_dur else lead
                rest_w = sum(weights[i] for i in range(n_seg)
                             if i not in span_dur) or 1.0
                lead_shots = []
                acc = 0.0
                for i in range(n_seg):
                    cue_i = movement[i] \
                        if i < len(movement) else None
                    dir_i = scene_directives[i] \
                        if i < len(scene_directives) else None
                    if i in span_dur:
                        dur = span_dur[i]
                        source = "events"
                    elif not graph_events:
                        if i == n_seg - 1:
                            dur = round(max(0.5, lead - acc), 2)
                        else:
                            dur = round(lead * weights[i] / total_w, 2)
                            acc += dur
                        source = "cue_weight"
                    elif i == max(j for j in range(n_seg)
                                  if j not in span_dur):
                        dur = round(max(0.5, remaining - acc), 2)
                        source = "cue_weight_fallback"
                    else:
                        dur = round(remaining * weights[i] / rest_w, 2)
                        dur = max(dur, 0.5)
                        acc += dur
                        source = "cue_weight_fallback"
                    lead_shots.append((cue_i, dir_i, dur, source))
            for seg_idx, (cue, seg_directive, dur, dur_source) in \
                    enumerate(lead_shots):
                seg_event_ids: list[str] = []
                if seg_directive and seg_directive.get("shot_id"):
                    seg_event_ids = [
                        str(n.get("action_id"))
                        for n in graph_events.get(
                            str(seg_directive["shot_id"]), [])]
                actor = action_actor(scene.get("action_text", ""),
                                     [cue] if cue else cues, char_names) \
                    if cue else None
                _transfer_holder(cue, actor)
                if seg_directive and seg_directive["shot_type"]:
                    st = seg_directive["shot_type"]
                    st_source = "directive"
                else:
                    st = "tracking" if cue in (
                        "walk", "walk_fast", "run", "board") else \
                        "object_insert" if cue in ("give", "take") \
                        else "medium"
                    st_source = "default"
                movement_v = (seg_directive["camera_movement"]
                              if seg_directive else scene_movement)
                angle_v = (seg_directive.get("camera_angle")
                           if seg_directive else None) or scene_angle
                mode_v, mode_note = _camera_mode_for(movement_v)
                if mode_v != "static_anchored":
                    mode_note = (
                        (mode_note + " " if mode_note else "")
                        + "scripted movement requested; the renderer "
                        "executes static until scripted execution "
                        "lands (§5.3)")
                if cue in LOCOMOTION_CUES:
                    # Direction toward the other visible character
                    # (staging order mirrors the renderer); +1 when
                    # the actor is alone. The actor falls back to
                    # the first visible character when action_actor
                    # could not resolve a name (first-person text).
                    # Recorded for A-S4: direction changes happen
                    # only at cuts between shots.
                    _actor = actor or (visible[0] if visible else None)
                    if _actor is None:
                        _dir = None
                    else:
                        _a_idx = visible.index(_actor) \
                            if _actor in visible else 0
                        _others = [n for n in visible if n != _actor]
                        if _others:
                            _o_idx = visible.index(_others[0])
                            _dir = 1 if STAGING_X[
                                _o_idx % len(STAGING_X)] > STAGING_X[
                                _a_idx % len(STAGING_X)] else -1
                        else:
                            _dir = 1
                else:
                    _dir = None
                pairing = None
                if st in HEAD_FRAMING_TYPES \
                        and cue in LOCOMOTION_CUES:
                    pairing = (
                        f"head framing {st} paired with locomotion "
                        f"cue {cue}: with the frozen crop the head "
                        "may exit the frame; directive kept as "
                        "written — verify the pairing")
                entry = {
                    "scene": number, "kind": "action", "speaker": None,
                    "text": "", "line_index": None,
                    "duration": dur,
                    "duration_breakdown": {
                        "voice_sec": 0.0, "beat_sec": 0.0,
                        "action_lead_sec": dur, "total_sec": dur},
                    "duration_source": dur_source,
                    "duration_justification": (
                        f"compiled event span {dur:.2f}s"
                        if dur_source == "events"
                        and dur > SHOT_WARN_SEC else None),
                    "event_ids": seg_event_ids,
                    "cue_validation": ("graph" if graph_events
                                       else "legacy"),
                    "dropped_cues": [],
                    "action_cues": [cue] if cue else cues,
                    "scene_cues": cues,
                    "actor": actor,
                    "action_text": scene.get("action_text", ""),
                    "visible": list(visible),
                    "shot_type": st,
                    "shot_type_source": st_source,
                    "camera_movement": movement_v,
                    "camera_angle": angle_v,
                    "camera_mode": mode_v,
                    "camera_mode_source": (
                        f"directive:{seg_directive['shot_id']}"
                        if seg_directive
                        and seg_directive.get("shot_id")
                        else "scene"
                        if scene.get("camera_movement")
                        else "planner:default"),
                    "camera_mode_execution": "static",
                    "camera_mode_note": mode_note,
                    "locomotion_direction": _dir,
                    "pairing_warning": pairing,
                    "duration_warning": (
                        f"shot {dur:.2f}s exceeds the 6s default; no "
                        "justification recorded"
                        if dur > SHOT_WARN_SEC
                        and st != "establishing"
                        and dur_source != "events" else None),
                    "lead_segment_index": seg_idx,
                    "lead_segment_count": len(lead_shots),
                    "is_reveal_shot": False,
                    "reveal_type": None,
                    "ots_subject": (seg_directive.get("subject")
                                    if seg_directive else None),
                    "ots_counterpart": (seg_directive.get("counterpart")
                                        if seg_directive else None),
                    "staging_mode": (seg_directive.get("staging_mode")
                                     if seg_directive else None),
                    "occluder_side": (seg_directive.get("occluder_side")
                                      if seg_directive else None),
                    "occluder_style": (seg_directive.get("occluder_style")
                                       if seg_directive else None),
                    "character_view": (seg_directive.get("character_view")
                                       if seg_directive else None),
                    "split_screen": (seg_directive.get("split_screen")
                                     if seg_directive else None),
                    "insert_card": (seg_directive.get("insert_card")
                                    if seg_directive else None),
                    "expression": None,
                    "costume_overrides": dict(scene_costumes),
                }
                entry.update(_prop_fields())
                if seg_directive and seg_directive.get("subject"):
                    entry["directive_subject"] = \
                        seg_directive["subject"]
                if seg_directive and seg_directive.get("shot_id"):
                    entry["directive_shot_id"] = \
                        seg_directive["shot_id"]
                _apply_location(entry, seg_directive)
                shots.append(entry)
        for line in scene.get("lines", []):
            line_no += 1
            directive = directives_by_line.get((number, line_no))
            expr_non_neutral = resolve_expression(
                line.get("expression"), line.get("text", "")) \
                != "neutral"
            # Primary shot type (first segment): directive wins over
            # Gemini's shot plan, which wins over cue defaults.
            if directive and directive["shot_type"]:
                st0 = directive["shot_type"]
                st0_source = "directive"
            else:
                st0 = gemini_shots.get((number, line_no))
                if st0 in SHOT_SCALE:
                    st0_source = "gemini"
                elif line_no == 1 and number == 1:
                    st0 = "establishing"
                    st0_source = "default"
                elif any(c in cues
                         for c in ("bend_pick", "give", "take")):
                    st0 = "object_insert"
                    st0_source = "default"
                elif expr_non_neutral:
                    st0 = "close_up"
                    st0_source = "default"
                else:
                    st0 = "medium"
                    st0_source = "default"
            movement_v = directive["camera_movement"] if directive \
                else scene_movement
            angle_v = (directive.get("camera_angle")
                       if directive else None) or scene_angle
            mode_v, mode_note = _camera_mode_for(movement_v)
            if mode_v != "static_anchored":
                mode_note = (
                    (mode_note + " " if mode_note else "")
                    + "scripted movement requested; the renderer "
                    "executes static until scripted execution "
                    "lands (§5.3)")
            # Voice + the 0.35 s beat: the shot holds the pose a beat
            # after the line ends, so the video length equals the
            # timeline total. A voice over 6 s splits into 2-5 s
            # segments over ONE uninterrupted narration: each segment
            # carries its own voice span + subtitle phrases, the
            # narration is never duplicated or restarted.
            voice = round(max(durations.get(line_no, 4.0), 0.8), 2)
            total = round(voice + PAUSE_AFTER_SEC, 2)
            if voice > SHOT_SPLIT_VOICE_SEC:
                n_seg = _segment_count(voice)
                spans = _split_voice_spans(voice, n_seg)
                seg_texts = _split_line_phrases(
                    line.get("text", ""), spans)
            else:
                n_seg = 1
                spans = [voice]
                seg_texts = [line.get("text", "")]
            seg_durs = [round(s, 2) for s in spans]
            seg_durs[-1] = round(seg_durs[-1] + PAUSE_AFTER_SEC, 2)
            drift = round(total - sum(seg_durs), 2)
            if drift:
                seg_durs[-1] = round(seg_durs[-1] + drift, 2)
            # Graph mode: the line shot cross-references the compiled
            # events of its directive (presentation, not ownership:
            # the unified timeline carries each event once, by time).
            # Cue filtering stays with the stage-2b semantic pass.
            line_event_ids: list[str] = []
            if directive and directive.get("shot_id"):
                line_event_ids = [
                    str(n.get("action_id"))
                    for n in graph_events.get(
                        str(directive["shot_id"]), [])]
            is_twist_line = bool(twist_text) \
                and line_no == total_lines \
                and line.get("text", "").strip() == twist_text
            offset = 0.0
            prev_type = None
            for seg_idx in range(n_seg):
                span = spans[seg_idx]
                if seg_idx == 0:
                    st, st_source = st0, st0_source
                else:
                    st = _progression_type(
                        seg_idx, n_seg, cues, len(visible),
                        expr_non_neutral, prev_type,
                        active_prop is not None)
                    st_source = "progression"
                prev_type = st
                seg_dur = seg_durs[seg_idx]
                is_last = seg_idx == n_seg - 1
                entry = {
                    "scene": number,
                    "kind": line.get("kind", "narration"),
                    "speaker": line.get("speaker"),
                    "text": seg_texts[seg_idx],
                    "line_index": line_no,
                    "duration": seg_dur,
                    "duration_breakdown": {
                        "voice_sec": span,
                        "beat_sec": PAUSE_AFTER_SEC if is_last else 0.0,
                        "action_lead_sec": 0.0,
                        "total_sec": seg_dur},
                    "duration_source": "voice",
                    "duration_justification": None,
                    "event_ids": line_event_ids,
                    "cue_validation": ("graph" if graph_events
                                       else "legacy"),
                    "dropped_cues": [],
                    "voice_duration": span,
                    "voice_offset_sec": offset,
                    "segment_index": seg_idx,
                    "segment_count": n_seg,
                    "action_cues": cues,
                    "scene_cues": cues,
                    "visible": list(visible),
                    "shot_type": st,
                    "shot_type_source": st_source,
                    "camera_movement": movement_v,
                    "camera_angle": angle_v,
                    "camera_mode": mode_v,
                    "camera_mode_source": (
                        f"directive:{directive['shot_id']}"
                        if directive and directive.get("shot_id")
                        else "scene"
                        if scene.get("camera_movement")
                        else "planner:default"),
                    "camera_mode_execution": "static",
                    "camera_mode_note": mode_note,
                    "locomotion_direction": None,
                    "pairing_warning": None,
                    "duration_warning": (
                        f"shot {seg_dur:.2f}s exceeds the 6s default; "
                        "no justification recorded"
                        if seg_dur > SHOT_WARN_SEC
                        and st != "establishing" else None),
                    "is_reveal_shot": is_twist_line and is_last,
                    "reveal_type": "twist"
                    if is_twist_line and is_last else None,
                    "ots_subject": (directive.get("subject")
                                    if directive else None),
                    "ots_counterpart": (directive.get("counterpart")
                                        if directive else None),
                    "staging_mode": (directive.get("staging_mode")
                                     if directive else None),
                    "occluder_side": (directive.get("occluder_side")
                                      if directive else None),
                    "occluder_style": (directive.get("occluder_style")
                                       if directive else None),
                    "character_view": (directive.get("character_view")
                                       if directive else None),
                    "split_screen": (directive.get("split_screen")
                                     if directive else None),
                    "insert_card": (directive.get("insert_card")
                                    if directive else None),
                    "expression": line.get("expression"),
                    "costume_overrides": dict(scene_costumes),
                }
                if st == "shot_reverse_shot":
                    # Directive value wins (the V1 adapter alternates
                    # srs_side per SRS shot in the scene); shots with
                    # no directive value keep the per-scene counter.
                    _ds = directive.get("srs_side") \
                        if directive else None
                    entry["srs_side"] = (1 if _ds else 0) \
                        if _ds is not None else srs_counter % 2
                    srs_counter += 1
                entry.update(_prop_fields())
                if directive and directive.get("subject"):
                    entry["directive_subject"] = directive["subject"]
                if directive and directive.get("shot_id"):
                    entry["directive_shot_id"] = directive["shot_id"]
                if seg_idx == 0 and (number, line_no) \
                        in directive_collisions:
                    entry["directive_collision_warning"] = (
                        "dropped duplicate directive(s) for this "
                        f"line: {directive_collisions[(number, line_no)]}")
                _apply_location(entry, directive)
                shots.append(entry)
                offset = round(offset + span, 2)
    # Boarding is permanent within the video: once a character boards
    # the bus, later shots stage them at the bus door.
    boarded: dict[str, float] = {}
    for s in shots:
        if s["kind"] == "action" and "board" in (s.get("action_cues") or []) \
                and s.get("actor"):
            boarded[s["actor"]] = BUS_DOOR_X
        elif boarded:
            s["staging_override"] = dict(boarded)
    # END_HOLD (Stage 3): end_hold_sec extends the LAST CONTENT shot
    # (the final image holds before the end card / fade). Applied
    # before the end card is appended, so it never extends the card.
    hold = _parse_seconds(package.get("end_hold_sec"))
    if hold and hold > 0 and shots:
        shots[-1]["duration"] = round(
            float(shots[-1]["duration"]) + hold, 2)
        shots[-1]["end_hold_sec"] = hold
    # END CARD (Stage 3): a final black-frame shot when the package
    # carries v1_end_card with a duration. The adapter owns duration
    # parsing; a float is consumed, a missing/invalid duration means
    # no card (never invented).
    end_card = package.get("v1_end_card") or package.get("end_card")
    if isinstance(end_card, dict):
        card_dur = _parse_seconds(end_card.get("duration"))
        if card_dur and card_dur > 0:
            last_scene = package["scenes"][-1]["number"] \
                if package.get("scenes") else 0
            shots.append({
                "scene": last_scene, "kind": "end_card",
                "speaker": None, "text": "",
                "line_index": None, "duration": round(card_dur, 2),
                "duration_breakdown": {
                    "voice_sec": 0.0, "beat_sec": 0.0,
                    "action_lead_sec": 0.0,
                    "total_sec": round(card_dur, 2)},
                "duration_source": "end_card",
                "duration_justification": None,
                "event_ids": [],
                "cue_validation": ("graph" if graph_events
                                   else "legacy"),
                "dropped_cues": [],
                "voice_duration": 0.0,
                "action_cues": [], "scene_cues": [],
                "actor": None, "action_text": "",
                "visible": [], "shot_type": "establishing",
                "shot_type_source": "default",
                "camera_movement": "STATIC",
                "camera_angle": None,
                "camera_mode": "static_anchored",
                "camera_mode_source": "planner:default",
                "camera_mode_execution": "static",
                "camera_mode_note": None,
                "locomotion_direction": None,
                "pairing_warning": None,
                "duration_warning": None,
                "is_reveal_shot": False,
                "reveal_type": None,
                "ots_subject": None, "ots_counterpart": None,
                "expression": None,
                "costume_overrides": {},
                "prop_holder": None, "prop_kind": None,
                "props": [], "prop_holders": {},
                "location_keyword": "", "setting": "",
                "mood": "warm", "time_of_day": "day",
                "v1_location": None, "location_text": "",
                "end_card_text": end_card.get("text", "") or "",
                "end_card_secondary":
                    end_card.get("secondary_text")
                    or end_card.get("secondary") or "",
            })
    # W4: every shot carries its start time on the cumulative clock
    # (the same clock render_product_video uses for frame counts), so
    # the renderer can clip compiled action events (global times) to
    # each shot. Assigned here — the single planning point, after the
    # end card — so the flow, the renderer and the storyboard stills
    # all agree. Planner V2 post-pass: cut boundaries (every boundary
    # is a cut — direction changes are legal only here), the opening
    # hook record, and repeated-framing warnings for consecutive
    # shots resolving to the same viewpoint.
    _clock = 0.0
    _prev_sig = None
    _prev_type = None
    for _i, _s in enumerate(shots):
        _s["start_sec"] = round(_clock, 3)
        _clock += float(_s["duration"])
        _s["cut_before"] = _i > 0
        _s["is_hook_shot"] = _i == 0 and _s["kind"] != "end_card"
        _s["hook_type"] = _HOOK_TYPE_BY_SHOT.get(_s["shot_type"]) \
            if _s["is_hook_shot"] else None
        _s["hook_warning"] = (
            "opening shot has no hook framing; the first shot "
            f"({ _s['shot_type']}) was kept as planned — verify the "
            "opening hook"
            if _s["is_hook_shot"] and _s["hook_type"] is None else None)
        _sig = _viewpoint_signature(_s)
        _same_scale = _prev_type is not None and SHOT_SCALE.get(
            _s["shot_type"]) == SHOT_SCALE.get(_prev_type)
        _s["repeated_framing_warning"] = (
            "same viewpoint as the previous shot"
            + (" and the same crop scale: the cut changes nothing"
               if _same_scale else
               " (crop scale differs: a framing change by cut)")
            + " — verify intent"
            if _prev_sig is not None and _sig == _prev_sig else None)
        _prev_sig, _prev_type = _sig, _s["shot_type"]
    return shots
def _font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


# Geometry-spec slot -> fill colour. Catalog slots resolve to the
# B2 material catalog's base colours (single source of truth for
# material appearance); decorative slots the catalog does not name
# (trim lines, the bolt's emissive core, jewels) map to fixed
# line-language fills. A test pins every slot of every geometry
# kind to this table, so an unmapped slot fails loudly in tests
# instead of silently inventing a colour at render time.
_GEOMETRY_SLOT_FILLS = {
    "leather": MATERIAL_CATALOG["leather"]["base_color"],
    "steel": MATERIAL_CATALOG["steel"]["base_color"],
    "paper": MATERIAL_CATALOG["paper"]["base_color"],
    "wood": MATERIAL_CATALOG["wood"]["base_color"],
    "stone": MATERIAL_CATALOG["stone"]["base_color"],
    "cloth": MATERIAL_CATALOG["cloth"]["base_color"],
    "bronze": MATERIAL_CATALOG["bronze"]["base_color"],
    "metal": MATERIAL_CATALOG["steel"]["base_color"],
    "shaft": MATERIAL_CATALOG["wood"]["base_color"],
    "fabric": MATERIAL_CATALOG["cloth"]["base_color"],
    "trim": INK_RGB,
    "core": MATERIAL_CATALOG["gold-emissive"]["base_color"],
    "emissive": MATERIAL_CATALOG["gold-emissive"]["emissive_color"],
    "jewel": (196, 58, 74),
}


def _draw_geometry_prop(draw, x, y, kind, w=76, h=50):
    """Draw a geometry kind from its semantic spec (wiring item 7).

    The spec is built at natural size, uniformly scaled to the
    (w, h) footprint, and translated so the spec's grip contact
    point lands on (x, y) -- the PSM transform origin. Polygons
    get an INK outline; polylines draw as an outlined stroke (ink
    under, slot fill over). H-relative builders (hammer) build
    from an explicit length: only proportions survive the
    footprint scaling, so the absolute length is immaterial.
    """
    spec = geometry_for_prop(
        {"kind": kind, "length_px": 200.0, "size_px": 170.0})
    x0, y0, x1, y1 = spec["bbox"]
    bw, bh = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    scale = min(float(w) / bw, float(h) / bh)
    gx, gy = spec["contact_points"]["grip"]
    # Outline width scales with the footprint (the polyline branch
    # below already does this): a fixed 3px outline at a 0.25x scale
    # overwhelmed thin filled geometry — the bolt measured 392 ink
    # vs 48 gold pixels at the default 76x50 footprint and read as a
    # dark blob. At scale >= ~0.83 the width stays 3 (unchanged).
    _outline_w = max(1, round(3 * scale))

    def _map(pt):
        return (x + (pt[0] - gx) * scale, y + (pt[1] - gy) * scale)

    for part in spec["parts"]:
        fill = _GEOMETRY_SLOT_FILLS[part["slot"]]
        op = part["op"]
        if op == "polygon":
            draw.polygon([_map(p) for p in part["points"]],
                         fill=fill, outline=INK_RGB, width=_outline_w)
        elif op == "rect":
            rx0, ry0, rx1, ry1 = part["bbox"]
            ax, ay = _map((rx0, ry0))
            bx, by = _map((rx1, ry1))
            draw.rectangle([ax, ay, bx, by], fill=fill,
                           outline=INK_RGB, width=_outline_w)
        elif op == "polyline":
            pts = [_map(p) for p in part["points"]]
            if part.get("close") and len(pts) > 1:
                pts = pts + [pts[0]]
            width = max(2, int(part.get("width", 3) * scale))
            draw.line(pts, fill=INK_RGB, width=width + 2,
                      joint="curve")
            draw.line(pts, fill=fill, width=width, joint="curve")
        else:  # pragma: no cover - builders only emit these ops
            raise ValueError(f"unknown geometry part op {op!r}")


def _draw_prop(draw, x, y, kind="wallet", w=76, h=50, open_u=0.0,
               tip=None):
    """Draw one prop at (x, y) in the character line language (INK
    outline, flat fill). F7: one distinct simple shape per PROP_KINDS
    entry; unknown kinds render as "generic". The wallet shape is the
    original one, unchanged, so existing wallet shots are identical.
    ``w``/``h`` are the wallet-scale footprint; other kinds scale
    from the same footprint so every prop reads at the same size.
    ``open_u`` (W4, wallet only): 0 = closed (pixel-identical to the
    original), 1 = fully open — an inner flap panel extends to the
    right, so OPEN_WALLET reads on screen. ``tip`` (W4, pen only):
    the pen tip position — a held pen is drawn as a barrel from the
    hand (x, y) to its tip; without it the rest shape is drawn."""
    kind = str(kind or "wallet").strip().lower()
    if kind not in PROP_KINDS:
        kind = "generic"
    if kind in _GEOMETRY_PROP_KINDS:
        _draw_geometry_prop(draw, x, y, kind, w, h)
        return
    ink = INK_RGB
    if kind == "wallet":
        draw.rounded_rectangle(
            [x - w / 2, y - h / 2, x + w / 2, y + h / 2],
            radius=9, fill=PROP_FILL, outline=ink, width=3)
        draw.line([(x - w / 2 + 8, y), (x + w / 2 - 8, y)],
                  fill=ink, width=3)
        if open_u > 0.05:
            flap_w = (w * 0.55) * min(1.0, float(open_u))
            # PIL rounded_rectangle requires width >= 2*radius + 2
            # and height >= 2*radius + 2: a barely-open wallet
            # (open_u ~0.06 -> flap_w ~2 px) crashed the Ep1 render
            # with "x1 must be greater than or equal to x0". Clamp
            # the radius to the flap box and skip the flap below
            # 3 px (invisible at that width).
            if flap_w >= 3.0:
                flap_h = h - 8.0
                flap_r = min(6.0, max(0.0, (flap_w - 2.0) / 2.0),
                             max(0.0, (flap_h - 2.0) / 2.0))
                draw.rounded_rectangle(
                    [x + w / 2 - 4, y - h / 2 + 4,
                     x + w / 2 - 4 + flap_w, y + h / 2 - 4],
                    radius=flap_r, fill=(226, 200, 150),
                    outline=ink, width=3)
                draw.line([(x + w / 2 + 2, y - h / 2 + 12),
                           (x + w / 2 - 4 + flap_w - 6,
                            y - h / 2 + 12)],
                          fill=(120, 90, 50), width=2)
    elif kind == "umbrella":
        # Canopy arc + shaft + crook handle.
        draw.pieslice([x - w / 2, y - h / 2, x + w / 2, y + h / 2],
                      start=180, end=360, fill=(60, 90, 140),
                      outline=ink, width=3)
        draw.line([(x, y), (x, y + h * 0.9)], fill=ink, width=3)
        draw.arc([x - 8, y + h * 0.9 - 10, x + 8, y + h * 0.9 + 10],
                 start=0, end=180, fill=ink, width=3)
        draw.line([(x, y - h / 2), (x, y - h / 2 - 8)], fill=ink, width=3)
    elif kind == "newspaper":
        draw.rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2],
                       fill=(238, 232, 210), outline=ink, width=3)
        draw.rectangle([x - w / 2 + 6, y - h / 2 + 6, x + w / 2 - 6,
                        y - h / 2 + 14], fill=ink)
        for i, yy in enumerate((-6, 2, 10, 18)):
            draw.line([(x - w / 2 + 6, y + yy),
                       (x + w / 2 - 6, y + yy)], fill=(90, 90, 90),
                      width=2)
    elif kind == "letter":
        # Envelope: cream rect + V flap to the centre.
        draw.rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2],
                       fill=(245, 238, 214), outline=ink, width=3)
        draw.line([(x - w / 2, y - h / 2), (x, y + 4)], fill=ink, width=2)
        draw.line([(x + w / 2, y - h / 2), (x, y + 4)], fill=ink, width=2)
        draw.line([(x - w / 2 + 8, y + h / 2 - 8),
                   (x + w / 2 - 8, y + h / 2 - 8)], fill=(150, 140, 110),
                  width=2)
    elif kind == "ticket":
        draw.rounded_rectangle(
            [x - w / 2, y - h / 3, x + w / 2, y + h / 3],
            radius=6, fill=(250, 240, 190), outline=ink, width=3)
        for yy in range(int(y - h / 3) + 4, int(y + h / 3) - 2, 6):
            draw.line([(x + w / 4, yy), (x + w / 4, yy + 3)],
                      fill=ink, width=2)
        draw.ellipse([x - w / 2 + 6, y - 7, x - w / 2 + 20, y + 7],
                     outline=ink, width=2)
    elif kind == "cup":
        draw.polygon([(x - w / 3, y - h / 2), (x + w / 3, y - h / 2),
                      (x + w / 4, y + h / 2), (x - w / 4, y + h / 2)],
                     fill=(220, 225, 230), outline=ink, width=3)
        draw.arc([x + w / 3 - 4, y - h / 4, x + w / 2 + 6, y + h / 4],
                 start=270, end=90, fill=ink, width=3)
        draw.line([(x - w / 3, y - h / 2), (x + w / 3, y - h / 2)],
                  fill=ink, width=3)
    elif kind == "bag":
        draw.rounded_rectangle(
            [x - w / 2, y - h / 3, x + w / 2, y + h / 2],
            radius=8, fill=(150, 130, 90), outline=ink, width=3)
        draw.arc([x - w / 4, y - h / 2 - 6, x + w / 4, y + h / 6],
                 start=180, end=360, fill=ink, width=3)
        draw.line([(x - w / 2, y), (x + w / 2, y)], fill=ink, width=2)
        draw.line([(x - w / 4, y - h / 3), (x - w / 4, y + h / 2)],
                  fill=ink, width=2)
    elif kind == "key":
        draw.ellipse([x - w / 2, y - 12, x - w / 2 + 26, y + 12],
                     outline=ink, width=3)
        draw.line([(x - w / 2 + 24, y), (x + w / 2, y)], fill=ink, width=4)
        draw.line([(x + w / 2 - 12, y), (x + w / 2 - 12, y + 12)],
                  fill=ink, width=3)
        draw.line([(x + w / 2 - 4, y), (x + w / 2 - 4, y + 9)],
                  fill=ink, width=3)
    elif kind == "book":
        draw.rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2],
                       fill=(140, 50, 50), outline=ink, width=3)
        draw.line([(x - w / 2 + 10, y - h / 2),
                   (x - w / 2 + 10, y + h / 2)], fill=ink, width=3)
        for yy in (-10, 0, 10):
            draw.line([(x - w / 2 + 18, y + yy),
                       (x + w / 2 - 8, y + yy)],
                      fill=(240, 235, 220), width=2)
    elif kind == "flower":
        draw.line([(x, y + h / 2), (x, y - h / 4)], fill=(60, 130, 60),
                  width=3)
        for dx, dy in ((-12, -14), (12, -14), (0, -22), (-10, 2), (10, 2)):
            draw.ellipse([x + dx - 8, y + dy - 8, x + dx + 8, y + dy + 8],
                         fill=(220, 90, 120), outline=ink, width=2)
        draw.ellipse([x - 6, y - 12, x + 6, y], fill=(250, 210, 80),
                     outline=ink, width=2)
    elif kind == "pen":
        if tip is not None:
            # Held pen (W4): the barrel runs from the gripping hand
            # (x, y) to the tip, which the write/sign primitives
            # keep ON the paper (see pen_tip_position). Drawing
            # the nib-up rest shape here would float the pen at
            # the hand with its tip pointing at the face.
            tx, ty = float(tip[0]), float(tip[1])
            draw.line([(x, y), (tx, ty)], fill=(40, 40, 60), width=7)
            _dx, _dy = tx - x, ty - y
            _len = math.hypot(_dx, _dy) or 1.0
            _ux, _uy = _dx / _len, _dy / _len
            _px, _py = -_uy, _ux
            draw.polygon([(tx, ty),
                          (tx - _ux * 14 + _px * 6,
                           ty - _uy * 14 + _py * 6),
                          (tx - _ux * 14 - _px * 6,
                           ty - _uy * 14 - _py * 6)],
                         fill=(200, 200, 210), outline=ink)
        else:
            # A pen at rest, diagonally: barrel + nib + clip.
            draw.line([(x - w / 2 + 6, y + h / 3),
                       (x + w / 2 - 14, y - h / 3)],
                      fill=(40, 40, 60), width=7)
            draw.polygon([(x + w / 2 - 14, y - h / 3),
                          (x + w / 2 + 4, y - h / 3 - 8),
                          (x + w / 2 - 6, y - h / 3 + 8)],
                         fill=(200, 200, 210), outline=ink)
            draw.line([(x - w / 4, y + h / 6), (x - w / 4 + 12, y - 2)],
                      fill=ink, width=2)
    else:  # generic
        draw.rounded_rectangle(
            [x - w / 3, y - h / 3, x + w / 3, y + h / 3],
            radius=8, fill=(190, 185, 170), outline=ink, width=3)
        draw.line([(x - w / 3, y - h / 3), (x + w / 3, y + h / 3)],
                  fill=ink, width=2)
        draw.line([(x + w / 3, y - h / 3), (x - w / 3, y + h / 3)],
                  fill=ink, width=2)


def _draw_puddle(draw, x, ground_y):
    """A rain puddle on the ground: reflective ellipse with a pale rim.
    The wallet lies BESIDE it — the character kneels at its edge
    without stepping in it (mandatory moment 1: avoids splashing)."""
    draw.ellipse([x - 120, ground_y - 4, x + 120, ground_y + 28],
                 fill=(52, 74, 110), outline=(140, 165, 200), width=2)
    draw.arc([x - 90, ground_y + 2, x + 90, ground_y + 22],
             start=200, end=340, fill=(180, 200, 230), width=2)


def _draw_rain(draw, fi: int):
    for i in range(RAIN_N):
        x0 = (i * 173 + 53) % 1920
        y0 = (i * 251 + fi * 19) % 1150 - 35
        draw.line([(x0, y0), (x0 - 4, y0 + 20)], fill=RAIN_COLOR, width=2)
    for i in range(RAIN_N):
        x0 = (i * 173 + 53) % 1920
        y0 = (i * 251 + fi * 19) % 1150 - 35
        draw.line([(x0, y0), (x0 - 4, y0 + 20)], fill=RAIN_COLOR, width=2)


def _lamp_glow(img, lamp_base_xy, lamp_head_xy):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    bx, by = lamp_base_xy
    for rx, ry, alpha in ((200, 42, 60), (140, 30, 80), (80, 18, 110)):
        od.ellipse([bx - rx, by - ry, bx + rx, by + ry],
                   fill=(255, 190, 80, alpha))
    hx, hy = lamp_head_xy
    for rx, ry, alpha in ((70, 46, 45), (40, 28, 70)):
        od.ellipse([hx - rx, hy - ry, hx + rx, hy + ry],
                   fill=(255, 211, 78, alpha))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay)
              .convert("RGB"), (0, 0))


def _draw_bus_details(img, cam=None):
    """F6 (TEST C Phase 2): 2D bus details over the projected bus
    body -- wheels, headlight + glow, taillight, destination sign,
    door outline, side stripe. The 3D boxes alone read as a building:
    the kerb occludes the 3D wheels, the door is a dark slab, and
    there are no lights. Every position is derived by projecting the
    bus box corners projected with the shot camera, so
    the details track the bus at any viewpoint -- no hardcoded pixels. Drawn on the static
    background (before the characters), so a boarding character
    occludes the bus correctly. The wheels straddle the body's
    bottom edge and may overlap the bench/kerb in front of the bus
    -- a small depth trade-off for a bus that reads as a bus at a
    glance (the alternative, 3D-only wheels, is invisible)."""
    _cam = cam or CAM
    cx, cy, cz = BUS_BODY_CENTER
    sx_, sy_, sz_ = BUS_BODY_SIZE
    zf = cz + sz_ / 2.0  # front face, facing the camera
    pts = [_cam.project((cx + dx * sx_ / 2.0, cy + dy * sy_ / 2.0, zf),
                       W, H)
           for dx in (-1, 1) for dy in (-1, 1)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    w, h = right - left, bottom - top
    d = ImageDraw.Draw(img, "RGBA")
    # Side stripe: a light band at window-sill level, breaking the
    # "blue block" read and lengthening the body.
    stripe_y = top + 0.52 * h
    d.rectangle([left, stripe_y, right, stripe_y + 0.055 * h],
                fill=(220, 230, 240, 255))
    # Door outline at BUS_DOOR_X (the 3D door slab is nearly
    # invisible against the body): light frame + centre split.
    dx0, _, _, _ = _cam.project((BUS_DOOR_X - 0.25, 0.2, zf), W, H)
    dx1, _, _, _ = _cam.project((BUS_DOOR_X + 0.25, 0.2, zf), W, H)
    _, dy0, _, _ = _cam.project((BUS_DOOR_X, 1.6, zf), W, H)
    _, dy1, _, _ = _cam.project((BUS_DOOR_X, 0.2, zf), W, H)
    d.rectangle([dx0, dy0, dx1, dy1],
                outline=(220, 230, 240, 255), width=3)
    d.line([((dx0 + dx1) / 2, dy0), ((dx0 + dx1) / 2, dy1)],
           fill=(220, 230, 240, 255), width=2)
    # Wheels: dark circles + light hubcaps, straddling the bottom
    # edge so they read as wheels under the body skirt.
    for wx in BUS_WHEEL_X:
        wcx, _, _, _ = _cam.project((wx, 0.15, zf), W, H)
        wr = 0.085 * h
        wcy = bottom - 0.02 * h
        d.ellipse([wcx - wr, wcy - wr, wcx + wr, wcy + wr],
                  fill=(15, 15, 18, 255),
                  outline=(200, 205, 215, 255), width=2)
        d.ellipse([wcx - wr * 0.4, wcy - wr * 0.4,
                   wcx + wr * 0.4, wcy + wr * 0.4],
                  fill=(200, 205, 215, 255))
    # Headlight (front = left end) with a soft glow, and a red
    # taillight at the rear end.
    hlx, hly = left + 0.045 * w, bottom - 0.10 * h
    hr_ = 0.045 * h
    for _r, _a in ((hr_ * 2.6, 45), (hr_ * 1.7, 80)):
        d.ellipse([hlx - _r, hly - _r, hlx + _r, hly + _r],
                  fill=(255, 240, 180, _a))
    d.ellipse([hlx - hr_, hly - hr_, hlx + hr_, hly + hr_],
              fill=(255, 244, 200, 255))
    tlx = right - 0.05 * w
    d.ellipse([tlx - hr_ * 0.8, hly - hr_ * 0.8,
               tlx + hr_ * 0.8, hly + hr_ * 0.8],
              fill=(255, 80, 70, 255))
    # Destination sign: a lit amber bar at the top-front with a
    # generic route number (no story content -- every bus has one).
    sign_w, sign_h = 0.22 * w, 0.075 * h
    sx0, sy0 = left + 0.05 * w, top + 0.06 * h
    d.rectangle([sx0, sy0, sx0 + sign_w, sy0 + sign_h],
                fill=(255, 200, 90, 255))
    fnt = _font(max(8, int(sign_h * 0.72)), bold=True)
    d.text((sx0 + sign_w / 2, sy0 + sign_h / 2), "01", font=fnt,
           fill=(30, 30, 30, 255), anchor="mm")


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    """Greedy word wrap by pixel width (for the end card)."""
    words = str(text or "").split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _render_end_card_image(text: str, secondary: str) -> Image.Image:
    """End-card frame (Stage 3): black frame + centred main text +
    centred secondary text. No characters, no subtitles, no effects.
    An empty text still yields a plain black frame (never a crash)."""
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    main_font = _font(56, bold=True)
    lines = _wrap_text(d, text, main_font, W - 240)
    line_h = 72
    total_h = len(lines) * line_h
    y = H // 2 - total_h // 2 - 20
    for line in lines:
        d.text((W // 2, y), line, font=main_font, fill=(255, 255, 255),
               anchor="ma")
        y += line_h
    if (secondary or "").strip():
        sec_font = _font(40)
        sec_lines = _wrap_text(d, secondary, sec_font, W - 320)
        y = H // 2 + total_h // 2 + 24
        for line in sec_lines:
            d.text((W // 2, y), line, font=sec_font,
                   fill=(200, 200, 200), anchor="ma")
            y += 52
    return img


def _draw_clock_face(draw, cx, cy, radius, hour, minute, ink,
                     face_fill):
    """A flat clock face (graphic-insert time card): circle + ticks
    + hands at (hour, minute). No text, no branding."""
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                 fill=face_fill, outline=ink, width=8)
    for tick in range(12):
        ang = math.radians(tick * 30.0)
        outer = (cx + radius * 0.92 * math.sin(ang),
                 cy - radius * 0.92 * math.cos(ang))
        inner = (cx + radius * 0.78 * math.sin(ang),
                 cy - radius * 0.78 * math.cos(ang))
        draw.line([inner, outer], fill=ink, width=6)
    min_ang = math.radians(minute * 6.0)
    hour_ang = math.radians((hour % 12 + minute / 60.0) * 30.0)
    draw.line([(cx, cy),
               (cx + radius * 0.72 * math.sin(min_ang),
                cy - radius * 0.72 * math.cos(min_ang))],
              fill=ink, width=7)
    draw.line([(cx, cy),
               (cx + radius * 0.48 * math.sin(hour_ang),
                cy - radius * 0.48 * math.cos(hour_ang))],
              fill=ink, width=9)
    draw.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=ink)


def _draw_tally(draw, cx, cy, count, ink, width_per=26, height=64):
    """Tally marks in groups of five (four vertical + diagonal)."""
    groups = (count + 4) // 5
    total_w = groups * (4 * width_per + 18) - 18
    x0 = cx - total_w / 2.0
    remaining = count
    for g in range(groups):
        n = min(5, remaining)
        gx = x0 + g * (4 * width_per + 18)
        for i in range(min(n, 4)):
            x = gx + i * width_per
            draw.line([(x, cy - height / 2), (x, cy + height / 2)],
                      fill=ink, width=6)
        if n == 5:
            draw.line([(gx - 6, cy + height / 2 - 8),
                       (gx + 3 * width_per + 6, cy - height / 2 + 8)],
                      fill=ink, width=6)
        remaining -= n


def _render_graphic_card_image(shot: dict) -> Image.Image:
    """A flat, straight-on graphic insert card (channel study R2/R6):
    a full-frame 2D card from the shot's insert_card spec — title,
    subtitle, lines, an optional clock face (time insert), an
    optional large prop drawing, optional tally marks. A card is a
    RENDERING, not a crop of the scene: the shot has no camera, no
    characters and no subtitle overlay (the card text IS the
    on-screen text). Never crashes on a missing/empty spec: the
    shot text becomes the title, and an empty spec yields a plain
    card."""
    card = shot.get("insert_card") or {}
    if card.get("style") == "dark":
        bg, ink, soft = (18, 24, 32), (240, 238, 228), (170, 175, 185)
        clock_face = (30, 40, 54)
    else:
        bg, ink, soft = (240, 235, 220), (20, 34, 43), (90, 95, 100)
        clock_face = (250, 247, 238)
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    title = (card.get("title") or "").strip() \
        or (shot.get("text") or "").strip()
    title_font = _font(88, bold=True)
    title_lines = _wrap_text(d, title, title_font, W - 320)[:2]
    y = 150
    for line in title_lines:
        d.text((W // 2, y), line, font=title_font, fill=ink, anchor="ma")
        y += 108
    subtitle = (card.get("subtitle") or "").strip()
    if subtitle:
        sub_font = _font(48)
        for line in _wrap_text(d, subtitle, sub_font, W - 400)[:1]:
            d.text((W // 2, y), line, font=sub_font, fill=soft,
                   anchor="ma")
            y += 62
    # Middle zone: clock face (time insert) else a large prop.
    clock = _normalize_clock_time(card.get("clock_time"))
    prop_kind = card.get("prop_kind")
    mid_cy = 600
    if clock is not None:
        _draw_clock_face(d, W // 2, mid_cy, 150, clock[0], clock[1],
                         ink, clock_face)
        d.text((W // 2, mid_cy + 175), "%02d:%02d" % clock,
               font=_font(44, bold=True), fill=ink, anchor="ma")
    elif prop_kind:
        _draw_prop(d, W // 2, mid_cy, kind=prop_kind, w=300, h=200)
    # Lines + tally below the middle zone.
    line_font = _font(46)
    ly = 810
    for line in (card.get("lines") or [])[:3]:
        d.text((W // 2, ly), str(line), font=line_font, fill=ink,
               anchor="ma")
        ly += 56
    tally = card.get("tally_count")
    if isinstance(tally, (int, float)) and not isinstance(tally, bool) \
            and int(tally) > 0:
        _draw_tally(d, W // 2, 1010, int(tally), ink)
    return img


def _render_occlusion_layer(side=None, style=None) -> Image.Image:
    """Foreground occlusion layer (channel study R5/R10a): a dark
    silhouette shape at one frame edge, solid or blurred. Screen
    space — the renderer is a 2D layered renderer, and the
    reference channel's occlusion is a flat foreground layer, not
    3D geometry. The shape is a generic edge band with a gently
    irregular inner edge, never a copied silhouette. Composited
    after the characters (and after the split-screen composite),
    before the crop."""
    side = side if side in ("left", "right") else "left"
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    edge = [0, 300, 600, 900, H]
    inner = [330, 295, 350, 305, 340]
    if side == "left":
        pts = [(0, 0)] + list(zip(inner, edge)) + [(0, H)]
    else:
        pts = [(W, 0)] + list(zip([W - v for v in inner], edge)) \
            + [(W, H)]
    d.polygon(pts, fill=(14, 20, 28, 255))
    if (style or "solid") == "blurred":
        layer = layer.filter(ImageFilter.GaussianBlur(24))
    return layer


def _split_composite(left_img, right_img, seam_px=4):
    """Two viewports side by side + a centre seam (channel study
    R10c): the left half of ``left_img`` and the right half of
    ``right_img``. Both images are full frames of the same moment
    (same camera, same crop); only the face expressions differ."""
    out = left_img.copy()
    half = W // 2
    out.paste(right_img.crop((half, 0, W, H)), (half, 0))
    d = ImageDraw.Draw(out)
    d.rectangle([half - seam_px // 2, 0,
                 half + seam_px // 2 - 1, H], fill=(20, 28, 36))
    return out


def _character_shadow_footprint(ch):
    """(half_width_px, half_depth_px) of the feet on the ground.

    From the live joints (stance varies with pose) plus the drawn
    foot size (feet are 0.12*H wide x 0.05*H tall, centred on the
    foot joints). Feeds the W1 ratio-capped shadow contract.
    """
    joints = ch.joints()
    fx = [joints["foot_l"][0], joints["foot_r"][0]]
    half_w = (max(fx) - min(fx)) / 2.0 + 0.06 * ch.H
    half_d = 0.025 * ch.H
    return half_w, half_d


def _draw_character_shadow(img, ch, cam, ground_pos, light):
    """Ratio-capped contact shadow under one character (W1).

    Geometry comes from lighting.shadow_ellipse_spec: the shadow can
    never outgrow the feet, stays a thin strip (depth-capped), and
    follows the light offset. No-op when the character is behind the
    camera (spec is None).
    """
    half_w, half_d = _character_shadow_footprint(ch)
    spec = shadow_ellipse_spec(ground_pos, 0.0, 0.35, light, cam,
                               img.size, half_w,
                               footprint_half_depth_px=half_d)
    if spec is None:
        return
    cx, cy = spec["center_px"]
    rx, ry = spec["rx_px"], spec["ry_px"]
    pad = 8
    layer = Image.new("RGBA", (int(rx * 2 + pad * 2), int(ry * 2 + pad * 2)),
                      (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(
        [pad, pad, pad + 2 * rx, pad + 2 * ry],
        fill=(0, 0, 0, int(255 * spec["alpha"])))
    layer = layer.filter(ImageFilter.GaussianBlur(4))
    img.paste(layer, (int(cx - rx - pad), int(cy - ry - pad)), layer)


# ---------------------------------------------------------------------------
# W4: compiled-action execution (Visual Quality Recovery P1/P2/P5).
# The action compiler turns V1 ACTION directives into timed events with
# semantic params; these helpers translate them into staged primitive
# closures + a per-shot prop state machine. Shots without compiled
# events keep the legacy cue path byte-for-byte.
# ---------------------------------------------------------------------------

def _furniture_anchors(env_pkg, cam, size, staging_x, ground_y, char_h,
                       facing):
    """Pixel-space desk/paper/chair anchors for sit/write/sign.

    From the environment package's furniture elements (projected with
    the shot camera) when present; staging-derived fallbacks otherwise
    (legacy scenes without an environment package). Returns
    {"desk": {"x", "top_y"} | None, "paper": {"x","y","w","h"},
    "chair": {"x", "seat_y"}, "source": "environment"|"fallback"}.
    The paper rect's "y" is its TOP edge (the hold_pen/write_on_paper
    contract)."""
    anchors = {"desk": None, "paper": None, "chair": None,
               "source": "fallback"}
    if env_pkg is not None:
        elements = {e.get("kind"): e for e in
                    (env_pkg.get("elements") or [])
                    if isinstance(e, dict)}
        by_id = {e.get("id"): e for e in
                 (env_pkg.get("elements") or [])
                 if isinstance(e, dict)}
        w, h = size

        def _project(element):
            if element is None:
                return None
            px, py, _s, vis = cam.project(element["center"], w, h)
            return (px, py) if vis else None

        def _project_top(element):
            # Project the element's top face centre (seat top / desk
            # top), not its centre: the sit/write poses anchor to
            # surfaces, and a centre-anchored seat floats the sitter
            # half a seat-height above the drawn chair.
            if element is None:
                return None
            cx, cy, cz = element["center"]
            top = (cx, cy + float(element["size"][1]) / 2.0, cz)
            px, py, _s, vis = cam.project(top, w, h)
            return (px, py) if vis else None

        def _projected_width(element):
            cx, cy, cz = element["center"]
            half = float(element["size"][0]) / 2.0
            ax, _ay, _s, vis_a = cam.project((cx - half, cy, cz), w, h)
            bx, _by, _s2, vis_b = cam.project((cx + half, cy, cz), w, h)
            if not (vis_a and vis_b):
                return None
            return abs(bx - ax)

        # ID-preferred lookup: kind-keyed maps collapse duplicates
        # (the interior has two paper_stack elements — the desk
        # paper and the cabinet papers — and three chair elements);
        # the writing paper is the desk one and the seat is the
        # seat, never the cabinet papers or the chair back.
        desk_el = elements.get("desk")
        paper_el = by_id.get("desk_paper") \
            or elements.get("paper_stack")
        chair_el = by_id.get("chair_seat") or elements.get("chair")
        desk_xy = _project_top(desk_el)
        paper_xy = _project(paper_el)
        chair_xy = _project_top(chair_el)
        if desk_xy is not None:
            anchors["desk"] = {"x": desk_xy[0], "top_y": desk_xy[1]}
        if paper_xy is not None:
            pw = _projected_width(paper_el) or 0.30 * char_h
            ph = pw * 0.66
            anchors["paper"] = {"x": paper_xy[0] - pw / 2.0,
                                "y": paper_xy[1] - ph / 2.0,
                                "w": pw, "h": ph}
            anchors["source"] = "environment"
        if chair_xy is not None:
            anchors["chair"] = {"x": chair_xy[0],
                                "seat_y": chair_xy[1]}
            anchors["source"] = "environment"
    if anchors["chair"] is None:
        anchors["chair"] = {"x": staging_x,
                            "seat_y": ground_y - 0.42 * char_h}
    if anchors["paper"] is None:
        pw, ph = 0.30 * char_h, 0.20 * char_h
        cx = staging_x + facing * 0.30 * char_h
        cy = ground_y - 0.52 * char_h
        anchors["paper"] = {"x": cx - pw / 2.0, "y": cy - ph / 2.0,
                            "w": pw, "h": ph}
    if anchors["desk"] is None:
        paper = anchors["paper"]
        anchors["desk"] = {"x": paper["x"] + paper["w"] / 2.0,
                           "top_y": paper["y"] + paper["h"] / 2.0}
    # Sanity: the desk top must sit above the seat in screen coords.
    if anchors["desk"]["top_y"] >= anchors["chair"]["seat_y"]:
        anchors["desk"]["top_y"] = anchors["chair"]["seat_y"] - 0.15 * char_h
    return anchors


def _shot_action_events(package, shot, duration):
    """Compiled events clipped to this shot, grouped per actor name.

    Returns (per_actor, shot_events, face_keyframes, blink_times,
    id_to_name, name_to_id). ``per_actor`` maps a character NAME to
    [(local_start, local_end, event)] with global times clipped to
    [start_sec, start_sec + duration]. Events naming an undeclared
    actor, an off-screen actor, or no actor are skipped (never an
    invented actor) but stay in ``shot_events`` for the P9 audit.
    face_keyframes maps NAME -> [(start, end, expression)] for
    face_only events (BLINK excluded: blinks go to ``blink_times``).
    """
    compiled = package.get("compiled_actions") or {}
    all_events = compiled.get("events") or []
    id_to_name = {}
    name_to_id = {}
    for c in package.get("characters") or []:
        name = str(c.get("name") or "")
        cid = c.get("id")
        if name and cid:
            id_to_name[str(cid)] = name
            name_to_id[name] = str(cid)
    empty = ({}, [], {}, {}, id_to_name, name_to_id)
    did = shot.get("directive_shot_id")
    if not did or not all_events:
        return empty
    t0 = float(shot.get("start_sec", 0.0))
    t1 = t0 + float(duration)
    per_actor: dict[str, list] = {}
    shot_events = []
    face_keyframes: dict[str, list] = {}
    blink_times: dict[str, list] = {}
    for event in all_events:
        if event.get("shot_id") != did:
            continue
        start = max(float(event.get("start_time", 0.0)), t0)
        end = min(float(event.get("end_time", start)), t1)
        if end <= start:
            continue
        shot_events.append(event)
        actor_id = event.get("actor_id")
        name = id_to_name.get(str(actor_id)) if actor_id else None
        if name is None:
            continue
        local = (start - t0, end - t0, event)
        primitive = ((event.get("required_pose") or {}).get("primitive"))
        if primitive == "face_only":
            params = ((event.get("required_pose") or {}).get("params")
                      or {})
            if event.get("action_type") == "BLINK":
                blink_times.setdefault(name, []).append(start - t0)
            else:
                expr = params.get("expression")
                if expr in EXPRESSION_NAMES:
                    face_keyframes.setdefault(name, []).append(
                        (start - t0, end - t0, expr))
            continue
        per_actor.setdefault(name, []).append(local)
    for windows in per_actor.values():
        windows.sort(key=lambda w: (w[0], w[1]))
    return (per_actor, shot_events, face_keyframes, blink_times,
            id_to_name, name_to_id)


def _event_time_trusted(event: dict) -> bool:
    """True when an event's times come from a span that drives a
    rendered shot. Events from unrendered directives carry phantom
    sequential times from t=0 (span_source "estimated") and must
    never feed cross-shot memory (prop holders, seated state).
    Events predating the flag (no span_source key) are trusted for
    backward compatibility with standalone compiler probes."""
    return event.get("span_source", "supplied") == "supplied"


def _incoming_holder(all_events, pid, t0):
    """The character holding ``pid`` at time ``t0`` from the full
    compiled event history (the cross-shot prop memory plan_shots
    cannot see: cue-based holder tracking knows nothing about
    event-driven handovers). Latest prop-affecting event ending at
    or before ``t0`` wins; PUT_AWAY/RELEASE clears the holder."""
    holder = None
    ordered = sorted(
        (e for e in all_events if isinstance(e, dict)
         and e.get("prop_id") == pid and _event_time_trusted(e)),
        key=lambda e: float(e.get("end_time", 0.0)))
    for event in ordered:
        if float(event.get("end_time", 0.0)) > t0 + 1e-9:
            break
        action = event.get("action_type")
        if action == "HAND_OVER":
            holder = event.get("target_id")
        elif action in ("PICK_UP", "TAKE_OUT", "HOLD", "HOLD_PEN"):
            holder = event.get("actor_id")
        elif action in ("PUT_AWAY", "RELEASE"):
            holder = None
    return holder


def _effective_cues(shot: dict, package: dict) -> list:
    """Shot cues minus cues that lost a semantic conflict.

    product_flow's early semantic pass discards losing cues from
    the scene lists and records them on
    ``package["discarded_cues"]`` ({cue, scene, removed, ...}).
    The renderer honors that record here, at the single place
    shot cues enter _render_shot, so a losing cue can never
    select a pose, draw a puddle, or stage a prop on the ground
    -- even for packages rendered without re-planning. A record
    with removed=False, a different scene, or a missing
    discarded_cues key changes nothing.
    """
    cues = list(shot.get("action_cues") or [])
    records = package.get("discarded_cues") or []
    scene = shot.get("scene")
    try:
        scene_no = int(scene)
    except (TypeError, ValueError):
        return cues
    lost = set()
    for rec in records:
        if not isinstance(rec, dict) or not rec.get("removed"):
            continue
        try:
            rec_scene = int(rec.get("scene"))
        except (TypeError, ValueError):
            continue
        if rec_scene == scene_no and rec.get("cue"):
            lost.add(rec["cue"])
    if not lost:
        return cues
    return [c for c in cues if c not in lost]


def _assign_prop_rests(pids, prop_dicts, first_actor_for_pid,
                       default_actor, anchors, joints0, ground_ys,
                       staging, name_to_id, tracker=None,
                       fallback_ground_y=0.0, events=None):
    """Per-shot prop rest positions + rest kinds.

    Rest kinds: "surface" (desk paper), "pocket" (hidden until
    manipulated), "ground" (visible on the ground line). The ground
    rule (directive §7): a prop rests on the ground when its
    semantic initial location is ON_GROUND -- the tracker's
    transition-table resolution from the compiled events, never a
    keyword guess -- OR when the shot drops it (a RELEASE event
    with semantic type RELEASE_PROP): the prop's WORLD_STATIC spans
    in that shot are on the ground, wherever it started. Everything
    else keeps the kind-based rule (desk props on the paper, the
    rest in pockets), so inferred IN_POCKET locations never
    override deliberate surface staging.
    Returns (rests, rest_kinds, pocket_anchors).
    """
    dropped = {str(e.get("prop_id")) for e in (events or [])
               if isinstance(e, dict)
               and e.get("action_type") == "RELEASE"
               and e.get("semantic_action_type") == "RELEASE_PROP"}
    rests: dict[str, tuple] = {}
    rest_kinds: dict[str, str] = {}
    pocket_anchors: dict[str, str | None] = {}
    for pid in pids:
        kind = infer_prop_kind(prop_dicts[pid])
        actor_name = first_actor_for_pid.get(pid) or default_actor
        initial = None
        if tracker is not None:
            try:
                initial = tracker.initial_location(pid)
            except KeyError:
                initial = None
        initial = getattr(initial, "value", initial)
        if initial == PropLocation.ON_GROUND.value or pid in dropped:
            rest_kinds[pid] = "ground"
            if actor_name in staging and actor_name in ground_ys:
                rests[pid] = (staging[actor_name] + 220.0,
                              ground_ys[actor_name])
            else:
                rests[pid] = (W // 2, fallback_ground_y)
            pocket_anchors[pid] = None
        elif kind in ("letter", "pen", "newspaper", "book", "ticket") \
                and actor_name in anchors:
            rest_kinds[pid] = "surface"
            paper = anchors[actor_name]["paper"]
            if kind == "pen":
                rests[pid] = (paper["x"] + 0.8 * paper["w"],
                              paper["y"] + 0.2 * paper["h"])
            else:
                rests[pid] = (paper["x"] + paper["w"] / 2.0,
                              paper["y"] + paper["h"] / 2.0)
            pocket_anchors[pid] = None
        else:
            rest_kinds[pid] = "pocket"
            anchor = actor_name if actor_name in joints0 else None
            pocket_anchors[pid] = name_to_id.get(anchor) \
                if anchor else None
            rests[pid] = joints0[anchor]["hip"] if anchor \
                else (0.0, 0.0)
    return rests, rest_kinds, pocket_anchors


def _build_shot_prop_machine(package, shot, shot_events, rests,
                             rest_kinds, pocket_anchors, id_to_name,
                             name_to_id, visible_names, t0):
    """Per-shot PropStateMachine + drawing metadata.

    ``rests`` maps prop id -> (x, y) rest position; ``rest_kinds``
    maps prop id -> "pocket"|"surface"; ``pocket_anchors`` maps prop
    id -> owner character id for pocket rests. Incoming holds (from
    the full event history, or plan_shots holder tracking when there
    is no history) seed a HOLD event at the shot start so a prop
    grasped earlier stays in hand. Returns (machine, pids,
    prop_kinds, rest_kinds, diagnostics) or (None, [], {}, {}, [])
    when the shot has no compiled events or no props.
    """
    compiled = package.get("compiled_actions") or {}
    all_events = compiled.get("events") or []
    prop_dicts = {}
    for p in package.get("props") or []:
        if isinstance(p, dict) and p.get("id"):
            prop_dicts[str(p["id"])] = p
    pids: list[str] = []
    for pid in [str(p) for p in (shot.get("props") or [])]:
        if pid in prop_dicts and pid not in pids:
            pids.append(pid)
    for event in shot_events:
        pid = event.get("prop_id")
        if pid and str(pid) in prop_dicts and str(pid) not in pids:
            pids.append(str(pid))
    if not pids or not shot_events:
        return None, [], {}, {}, []
    staging = {}
    for pid in pids:
        rx, ry = rests.get(pid, (0.0, 0.0))
        kind = rest_kinds.get(pid, "pocket")
        staging[pid] = {"x": rx, "y": ry, "angle": 0.0, "kind": kind,
                        "anchor_id": pocket_anchors.get(pid),
                        "offset": (0.0, 0.0)}
    grasped_in_shot = {str(e.get("prop_id")) for e in shot_events
                       if e.get("action_type") in (
                           "PICK_UP", "TAKE_OUT", "HOLD", "HOLD_PEN")}
    machine_events = list(shot_events)
    holders = shot.get("prop_holders") or {}
    for pid in pids:
        if pid in grasped_in_shot:
            continue
        holder_id = _incoming_holder(all_events, pid, t0)
        if holder_id is None:
            holder_name = holders.get(pid)
            if holder_name is None and shot.get("props") \
                    and pid == str(shot["props"][0]):
                holder_name = shot.get("prop_holder")
            holder_id = name_to_id.get(str(holder_name)) \
                if holder_name else None
        if holder_id is None:
            continue
        if id_to_name.get(str(holder_id)) not in visible_names:
            continue
        machine_events.append({
            "action_id": f"SEED_HOLD_{pid}",
            "action_type": "HOLD", "actor_id": str(holder_id),
            "prop_id": pid, "start_time": t0 - 0.01,
            "end_time": t0 + 0.01,
            "required_pose": {"primitive": "pick_up",
                              "params": {"hand": "r"}},
        })
    props = [prop_dicts[pid] for pid in pids]
    machine = PropStateMachine(props, machine_events, staging,
                               ground_y=None)
    prop_kinds = {pid: infer_prop_kind(prop_dicts[pid]) for pid in pids}
    return (machine, pids, prop_kinds,
            {pid: rest_kinds.get(pid, "pocket") for pid in pids},
            list(machine.diagnostics))


def _sequence_fns(windows, overlays, idle_fn, blocks=()):
    """One fn(t) running ``windows`` [(start, end, fn)] in order.

    Before the first window the first fn holds its start pose; gaps
    hold the previous window's end pose; after the last window the
    last fn holds its end pose. ``overlays`` [(start, end, fn)] run
    after the base fn while active (hand-only overlays like
    carry_bag). ``blocks`` [(start, end)] are windows owned by
    ANOTHER character's pair fn (a handover): the base fn is skipped
    there so it cannot overwrite the pair fn's pose. With no windows
    and no block, ``idle_fn`` runs.
    """
    ordered = sorted(windows, key=lambda w: (w[0], w[1]))
    overlay_list = sorted(overlays, key=lambda w: (w[0], w[1]))
    block_list = sorted(blocks)

    def fn(t):
        blocked = any(start <= t < end for start, end in block_list)
        if not blocked:
            if ordered:
                chosen = None
                for i, (start, end, active_fn) in enumerate(ordered):
                    if t < start:
                        if i == 0:
                            chosen = (active_fn, 0.0)
                        else:
                            pstart, pend, pfn = ordered[i - 1]
                            chosen = (pfn, pend - pstart)
                        break
                    if t < end:
                        chosen = (active_fn, t - start)
                        break
                if chosen is None:
                    start, end, active_fn = ordered[-1]
                    chosen = (active_fn, end - start)
                chosen[0](chosen[1])
            elif idle_fn is not None:
                idle_fn(t)
        for start, end, overlay_fn in overlay_list:
            if start <= t < end:
                overlay_fn(t - start)
        return None

    return fn


def _event_fn(primitive, params, event, ctx, window_dur):
    """One compiled event -> a primitive closure (W4).

    ``ctx`` carries the staged geometry (staging x, ground y,
    furniture anchors, prop rest positions, the standing-joints
    snapshot, the mutable root-x tracker ``pos``). Returns None for
    ``face_only`` (expression path), ``hand_over`` (pair fn, built by
    the caller) and unknown primitives — the caller records those
    windows loudly instead of silently idling them. Movers update
    ``ctx["pos"]["x"]`` so chained events start where the previous
    one ended.
    """
    char = ctx["char"]
    hand = params.get("hand", "r")
    if hand == "both":
        hand = "r"
    ground_y = ctx["ground_y"]
    dur = max(0.05, float(window_dur))

    def _target():
        pid = event.get("prop_id")
        if pid and str(pid) in ctx["rests"]:
            return ctx["rests"][str(pid)]
        for cp in event.get("contact_points") or []:
            tid = cp.get("target_id")
            if tid and str(tid) in ctx["rests"]:
                return ctx["rests"][str(tid)]
            if tid and str(tid) in ctx["id_to_name"]:
                nm = ctx["id_to_name"][str(tid)]
                if nm in ctx["joints0"]:
                    return ctx["joints0"][nm]["head"]
        tid = event.get("target_id")
        if tid and str(tid) in ctx["id_to_name"]:
            nm = ctx["id_to_name"][str(tid)]
            if nm in ctx["joints0"]:
                return ctx["joints0"][nm]["head"]
        if ctx["other_name"] in ctx["joints0"]:
            return ctx["joints0"][ctx["other_name"]]["head"]
        head = ctx["joints0"][ctx["name"]]["head"]
        return (head[0] + ctx["facing"] * 300.0, head[1])

    def _hip():
        return ctx["joints0"][ctx["name"]]["hip"]

    if primitive == "walk_to":
        from_x = ctx["pos"]["x"]
        to_x = from_x + 320.0 * ctx["direction"]
        ctx["pos"]["x"] = to_x
        return walk_to(char, from_x, to_x, dur, ground_y)
    if primitive == "run_to":
        from_x = ctx["pos"]["x"]
        to_x = from_x + 380.0 * ctx["direction"]
        ctx["pos"]["x"] = to_x
        return run_to(char, from_x, to_x, dur, ground_y)
    if primitive == "walk_mud":
        from_x = ctx["pos"]["x"]
        to_x = from_x + 300.0 * ctx["direction"]
        ctx["pos"]["x"] = to_x
        return walk_mud(char, from_x, to_x, dur, ground_y)
    if primitive == "idle":
        return idle(char, dur, ground_y)
    if primitive == "turn_to":
        if ctx["other_name"] in ctx["joints0"]:
            other_x = ctx["joints0"][ctx["other_name"]]["hip"][0]
            new_facing = 1 if other_x > ctx["pos"]["x"] else -1
        else:
            new_facing = -ctx["facing"]
        return turn_to(char, new_facing, dur)
    if primitive == "sit_down":
        return sit_down(char, dur, ground_y)
    if primitive == "stand_up":
        return stand_up(char, dur, ground_y)
    if primitive == "sit_at_desk":
        ctx["pos"]["x"] = ctx["chair_x"]
        return sit_at_desk(char, ctx["chair_x"], ctx["seat_y"], dur,
                           ground_y, desk=ctx["desk"])
    if primitive == "stand_from_chair":
        return stand_from_chair(char, dur, ground_y,
                                chair_x=ctx["pos"]["x"])
    if primitive == "bend_pick":
        return bend_pick(char, _target(), dur, ground_y, hand=hand)
    if primitive == "kneel_pick":
        return kneel_pick(char, _target(), dur, ground_y, hand=hand)
    if primitive == "pick_up":
        if params.get("pocket"):
            target, source = _hip(), "pocket"
        else:
            target, source = _target(), "ground"
        return pick_up(char, target, dur, ground_y, hand=hand,
                       source=source)
    if primitive == "put_away":
        return put_away(char, _hip(), dur, hand=hand, prop=ctx["prop"])
    if primitive == "open_wallet":
        return open_wallet(char, dur, prop=ctx["prop"])
    if primitive == "close_wallet":
        return close_wallet(char, dur, prop=ctx["prop"])
    if primitive == "hold_pen":
        pen_pos = _target()
        return hold_pen(char, pen_pos, ctx["paper"], dur, hand=hand)
    if primitive == "write_on_paper":
        words = max(3, round(dur * 1.5))
        return write_on_paper(char, ctx["paper"], dur, hand=hand,
                              words=words)
    if primitive == "sign_document":
        return sign_document(char, ctx["paper"], dur, hand=hand)
    if primitive == "carry_bag":
        return carry_bag(char, dur, hand=hand, bag=ctx["prop"])
    if primitive == "reach_to":
        return reach_to(char, _target(), dur, hand=hand)
    if primitive == "point_at":
        return point_at(char, _target(), dur)
    if primitive == "raise_hand":
        return raise_hand(char, dur, hand=hand)
    if primitive == "wave":
        return wave(char, dur)
    if primitive == "nod":
        return nod(char, dur)
    if primitive == "shrug":
        return shrug(char, dur)
    if primitive == "cover_face":
        return cover_face(char, dur)
    if primitive == "look_at_point":
        return look_at_point(char, _target(), dur)
    if primitive == "head_tilt":
        return head_tilt(char, dur)
    if primitive == "breathe":
        return breathe(char, dur, breaths=max(1, round(dur / 1.5)))
    if primitive == "react_event":
        return react_event(char, dur,
                           kind=params.get("kind", "startle"))
    return None


def _shot_has_bus(shot: dict, package: dict) -> bool:
    """Whether this shot stages a bus boarding.

    Shot-level evidence only: the shot's own action cues naming
    bus/board, or one of its compiled events being a BOARD. The
    scene-level cue union must never summon the bus -- one
    sentence's cue would paint a bus behind every shot of the
    scene (the Zeus re-render's Olympus: a "board" cue in scene
    10's union drew a modern bus in all 12 shots). "board"
    implies a bus even when the cues forget "bus", because the
    board shot must show the bus being boarded.
    """
    action_cues = list(shot.get("action_cues") or [])
    if "bus" in action_cues or "board" in action_cues:
        return True
    event_ids = set(shot.get("event_ids") or [])
    if event_ids:
        for event in (package.get("compiled_actions") or {}).get(
                "events", []):
            if event.get("action_id") in event_ids \
                    and event.get("action_type") == "BOARD":
                return True
    return False


def _insert_anchor_from_telemetry(telemetry: list[dict]):
    """Median staging-plane position of the dominant prop's draws.

    The two-pass object_insert anchor: props travel during a shot
    (ground -> hand, giver -> receiver), so the frame-0 rest
    position mis-frames the shot. The median draw position over
    the whole shot sits mid-travel for transfers and at the hold
    point for held props. The dominant prop (most draws) is the
    insert's subject. Returns (x, y, kind, n_draws) or None when
    no prop draw carries coordinates.
    """
    _by_kind: dict[str, list[tuple[float, float]]] = {}
    for _entry in telemetry:
        for _draw in _entry.get("draws") or []:
            _x, _y = _draw.get("x"), _draw.get("y")
            if not isinstance(_x, (int, float)):
                continue
            if not isinstance(_y, (int, float)):
                continue
            _by_kind.setdefault(str(_draw.get("kind") or "prop"),
                                []).append((float(_x), float(_y)))
    if not _by_kind:
        return None
    _kind, _pts = max(_by_kind.items(), key=lambda kv: len(kv[1]))
    _xs = sorted(p[0] for p in _pts)
    _ys = sorted(p[1] for p in _pts)
    _n = len(_pts)
    _mx = (_xs[_n // 2] if _n % 2
           else (_xs[_n // 2 - 1] + _xs[_n // 2]) / 2.0)
    _my = (_ys[_n // 2] if _n % 2
           else (_ys[_n // 2 - 1] + _ys[_n // 2]) / 2.0)
    return (_mx, _my, _kind, _n)


def _insert_anchor_subjects(telemetry: list[dict],
                            standing_boxes: list[dict]):
    """(subjects, anchor record) for the insert pass-2 freeze.

    Telemetry median when a prop was drawn; the full-body
    standing boxes (the frame-0 path's no-prop fallback) when no
    prop draw carries coordinates.
    """
    _median = _insert_anchor_from_telemetry(telemetry)
    if _median is not None:
        _ax, _ay, _akind, _an = _median
        return ([{"cx": _ax, "head_y": _ay - 90,
                  "foot_y": _ay + 90, "half_w": 170}],
                {"source": "telemetry_median", "kind": _akind,
                 "x": _ax, "y": _ay, "n_draws": _an})
    return (list(standing_boxes),
            {"source": "standing_boxes_fallback", "kind": None,
             "x": None, "y": None, "n_draws": 0})


# Screen-space cap for deferred (insert) glow halos: 1.25x the
# default 240px staging radius. A pre-crop halo is magnified by the
# crop zoom (240px became an 816px wash at the 3.4x handover zoom),
# so the deferred path repaints the halo after the crop with the
# radius capped — the halo stays local on screen at any zoom.
GLOW_SCREEN_RADIUS_CAP = 300.0


def _screen_glow_record(record: dict, crop_rect, frame_size):
    """A staging-space glow record mapped to screen space.

    The centre moves through the crop rect + resize; the radius
    scales by the crop zoom but is capped at
    GLOW_SCREEN_RADIUS_CAP. Crop rects are aspect-matched to the
    frame, so one zoom factor applies to the radius. Returns a
    copy; the input record is untouched.
    """
    x0, y0, x1, y1 = (float(v) for v in crop_rect)
    fw, fh = (float(v) for v in frame_size)
    zx = fw / max(x1 - x0, 1.0)
    zy = fh / max(y1 - y0, 1.0)
    cx, cy = (float(v) for v in record["source_position"])
    out = dict(record)
    out["source_position"] = ((cx - x0) * zx, (cy - y0) * zy)
    out["radius"] = min(float(record["radius"]) * zx,
                        GLOW_SCREEN_RADIUS_CAP)
    return out


def _render_shot(args: dict) -> dict:
    """One shot -> PNG frames (+ optional single still). Top-level so
    multiprocessing can pickle it. Pure in the shot: every boundary
    is a CUT, so no state crosses shots."""
    shot = args["shot"]
    package = args["package"]
    out_dir = Path(args["out_dir"])
    still_only = args.get("still_only", False)
    shot_dir = out_dir / f"shot_{shot['index']:03d}"
    shot_dir.mkdir(parents=True, exist_ok=True)
    duration = float(shot["duration"])
    # Frame count from the cumulative clock when the planner supplies
    # it (render_product_video) — exact total, no per-shot rounding
    # drift. Stills render exactly one frame.
    n_frames = 1 if still_only else int(
        shot.get("n_frames") or max(1, int(round(duration * FPS))))
    # ---- end card: black frame + centred text, nothing else --------
    if shot.get("kind") == "end_card":
        card = package.get("v1_end_card") or package.get("end_card") \
            or {}
        main_text = shot.get("end_card_text") \
            or (card.get("text", "") if isinstance(card, dict) else "")
        secondary_text = shot.get("end_card_secondary") \
            or (card.get("secondary_text") or card.get("secondary") or ""
                if isinstance(card, dict) else "")
        card_img = _render_end_card_image(main_text, secondary_text)
        if still_only:
            still_path = shot_dir / "still.png"
            card_img.save(still_path, compress_level=1)
            return {
                "index": shot["index"], "scene": shot["scene"],
                "kind": "end_card", "speaker": None,
                "shot_type": shot["shot_type"], "duration": duration,
                "n_frames": 0, "applied_scale": 1.0, "frames": [],
                "still": str(still_path), "violations": [],
                "max_jump_px_per_frame": 0.0,
                "camera_movement": "STATIC",
                "location_keyword": shot.get("location_keyword", "street"),
                "rainy": False,
            }
        frames_written = []
        for fi in range(n_frames):
            path = shot_dir / f"f{fi:04d}.png"
            card_img.save(path, compress_level=1)
            frames_written.append(str(path))
        return {
            "index": shot["index"], "scene": shot["scene"],
            "kind": "end_card", "speaker": None,
            "shot_type": shot["shot_type"], "duration": duration,
            "n_frames": len(frames_written), "applied_scale": 1.0,
            "frames": frames_written, "still": None,
            "violations": [], "max_jump_px_per_frame": 0.0,
            "camera_movement": "STATIC",
            "location_keyword": shot.get("location_keyword", "street"),
            "rainy": False,
        }
    # ---- graphic insert: flat card, no camera, no cast --------------
    # A graphic_insert shot renders its card image for every frame
    # (the card is static by design — a flat insert has no camera
    # to move). No characters, no scene, no subtitle overlay (the
    # card text is the on-screen text); the SRT track still carries
    # the line. Same return shape as the end card.
    if shot["shot_type"] == "graphic_insert":
        card_img = _render_graphic_card_image(shot)
        if still_only:
            still_path = shot_dir / "still.png"
            card_img.save(still_path, compress_level=1)
            return {
                "index": shot["index"], "scene": shot["scene"],
                "kind": shot["kind"], "speaker": shot.get("speaker"),
                "shot_type": shot["shot_type"], "duration": duration,
                "n_frames": 0, "applied_scale": 1.0, "frames": [],
                "still": str(still_path), "violations": [],
                "max_jump_px_per_frame": 0.0,
                "camera_movement": "STATIC",
                "location_keyword": shot.get("location_keyword", "street"),
                "rainy": False,
                "insert_card": shot.get("insert_card") or {},
            }
        frames_written = []
        for fi in range(n_frames):
            path = shot_dir / f"f{fi:04d}.png"
            card_img.save(path, compress_level=1)
            frames_written.append(str(path))
        return {
            "index": shot["index"], "scene": shot["scene"],
            "kind": shot["kind"], "speaker": shot.get("speaker"),
            "shot_type": shot["shot_type"], "duration": duration,
            "n_frames": len(frames_written), "applied_scale": 1.0,
            "frames": frames_written, "still": None,
            "violations": [], "max_jump_px_per_frame": 0.0,
            "camera_movement": "STATIC",
            "location_keyword": shot.get("location_keyword", "street"),
            "rainy": False,
            "insert_card": shot.get("insert_card") or {},
        }
    # ---- visible cast (names first: characters are built AFTER the
    # shot camera resolves, because their drawn height comes from
    # the camera's perspective scale — see char_metrics) ------------
    _visible = shot.get("visible")
    if _visible is None:
        _visible = [str(c["name"]) for c in package["characters"]]
    _costume_overrides = shot.get("costume_overrides") or {}
    _char_by_name = {str(c["name"]): (i, c)
                     for i, c in enumerate(package["characters"])}
    names = [n for n in _char_by_name if n in _visible]
    speaker = shot.get("speaker")
    actor = None
    if shot["kind"] == "action" and shot.get("actor") in names:
        # The action lead's actor comes from the scene's action text
        # (who runs / boards / gives) — not from the speaker.
        actor = shot["actor"]
    elif speaker and speaker != "narrator" and speaker in names:
        actor = speaker
    elif names:
        actor = names[0]
    other = next((n for n in names if n != actor), None)
    # ---- world staging ---------------------------------------------
    world_xs = {n: STAGING_X[i % len(STAGING_X)]
                for i, n in enumerate(names)}
    # Boarded characters stay at the bus door in later shots.
    for _n, _wx in (shot.get("staging_override") or {}).items():
        if _n in world_xs:
            world_xs[_n] = float(_wx)
    world_zs = {n: WORLD_Z for n in names}
    _ots_subject = shot.get("ots_subject")
    _ots_counterpart = shot.get("ots_counterpart")
    _ots_listener = None
    if shot["shot_type"] == "over_the_shoulder":
        # OTS staging: the listener stands closer to the camera than
        # the character plane, so perspective scale makes them read
        # as a foreground shoulder; the speaker stays on the plane.
        # The listener is ALSO drawn from behind (view "back" in the
        # frame loop): the camera sits behind their shoulder, so a
        # profile face would read as a second subject facing the
        # viewer instead of a foreground shoulder.
        _listener = _ots_counterpart if _ots_counterpart in names \
            else other
        if _listener is not None:
            _ots_listener = _listener
            world_zs[_listener] = WORLD_Z + OTS_FOREGROUND_Z_OFFSET
    # Layered-depth staging (channel study R5): the subject stays on
    # the character plane, everyone else stands a step BEHIND it, so
    # perspective scale + ground-line separation read as depth
    # layers instead of a flat line-up. The OTS listener keeps its
    # foreground offset (a foreground shoulder is not a depth
    # layer). The foreground occlusion shape is built after the
    # background and composited per frame (see _occluder below).
    _staging_mode = shot.get("staging_mode")
    if _staging_mode == "layered_depth":
        for _n in names:
            if _n != actor and _n != _ots_listener:
                world_zs[_n] = WORLD_Z - 0.6
    # ---- W4 early: compiled events + furniture staging --------------
    # The events must be known BEFORE the camera resolves: a
    # sitting/writing actor is staged AT the furniture (the chair
    # world position from the environment package), not on the
    # character plane — the desk sits ~1.7 units behind the plane,
    # so a plane-staged actor writes at head height in the air.
    # The environment build is camera-independent, so the furniture
    # lookup rebuilds the same deterministic package the scene
    # build uses later. Seated state is also computed here: it
    # carries across the CUT boundary within a scene (sit in one
    # shot, still seated in the next), from the compiled events.
    (_per_actor, _shot_events, _face_keyframes, _blink_times,
     _id_to_name, _name_to_id) = _shot_action_events(
         package, shot, duration)
    _t0 = float(shot.get("start_sec", 0.0))
    _furniture_staging: dict[str, tuple] = {}
    _seated_at_start: dict[str, bool] = {}
    _compiled_all = (package.get("compiled_actions") or {}).get(
        "events") or []
    if _compiled_all and actor is not None:
        _furn_prims = {"sit_at_desk", "write_on_paper",
                       "sign_document", "hold_pen"}
        _actor_cid = _name_to_id.get(actor)
        _needs_furniture = any(
            (e.get("required_pose") or {}).get("primitive")
            in _furn_prims
            for _s, _e, e in _per_actor.get(actor, []))
        _scene_no = shot.get("scene")
        _seated = False
        for _ev in sorted(
                _compiled_all,
                key=lambda e: float(e.get("start_time", 0.0))):
            if float(_ev.get("end_time", 0.0)) > _t0:
                break
            if not _event_time_trusted(_ev):
                continue
            _sid = str(_ev.get("shot_id") or "")
            _m = re.match(r"SC(\d+)_", _sid)
            if _m is None or int(_m.group(1)) != _scene_no:
                continue
            if str(_ev.get("actor_id")) != str(_actor_cid):
                continue
            _prim = (_ev.get("required_pose") or {}).get("primitive")
            if _prim == "sit_at_desk":
                _seated = True
            elif _prim == "stand_from_chair":
                _seated = False
        _seated_at_start[actor] = _seated
        if not _seated and _needs_furniture and isinstance(
                shot.get("v1_location"), dict):
            # Scene-state inference: a shot depicting write/sign
            # work in a scene where sitting is scripted for this
            # actor is a CUT INTO the ongoing action — the actor
            # is already seated, even when the SIT event itself
            # plays in a later shot of the scene (lead shots
            # precede the line shot in the clock). The shot that
            # carries the SIT event itself still animates the sit
            # (it has a SIT event in _per_actor, so _has_sit in
            # the override block suppresses the hold prefix).
            _has_sit_here = any(
                ((e.get("required_pose") or {}).get("primitive")
                 == "sit_at_desk")
                for _s, _e, e in _per_actor.get(actor, []))
            if not _has_sit_here:
                for _ev in _compiled_all:
                    if not _event_time_trusted(_ev):
                        continue
                    _sid = str(_ev.get("shot_id") or "")
                    _m = re.match(r"SC(\d+)_", _sid)
                    if _m is None or int(_m.group(1)) != _scene_no:
                        continue
                    if str(_ev.get("actor_id")) != str(_actor_cid):
                        continue
                    if ((_ev.get("required_pose") or {}).get(
                            "primitive") == "sit_at_desk"):
                        _seated = True
                        _seated_at_start[actor] = True
                        break
        if (_needs_furniture or _seated) and isinstance(
                shot.get("v1_location"), dict):
            _furn_pkg = None
            try:
                _furn_pkg = build_environment(
                    shot["v1_location"],
                    time_of_day=shot.get("time_of_day", "day"),
                    style={"mood": shot.get("mood", "warm")})
            except Exception:
                _furn_pkg = None
            if _furn_pkg is not None:
                _chair_el = None
                for _el in _furn_pkg.get("elements") or []:
                    if _el.get("kind") != "chair":
                        continue
                    if _el.get("id") == "chair_seat":
                        _chair_el = _el
                        break
                    if _chair_el is None:
                        _chair_el = _el
                if _chair_el is not None:
                    _cx, _cy, _cz = _chair_el["center"]
                    world_xs[actor] = float(_cx)
                    world_zs[actor] = float(_cz)
                    _furniture_staging[actor] = (float(_cx), float(_cz))
    # ---- shot viewpoint (Stage 3 / F9, P0 camera redirect) --------
    # Every shot resolves its OWN PerspectiveCamera from shot_type +
    # camera_angle + subject/staging, and that camera — not the
    # module-global CAM — drives the background, the horizon, the bus
    # details and every character projection in this shot. The camera
    # is FIXED within the shot; the angle changes BY CUT. CAM remains
    # only as the default for legacy callers (and the scale anchor
    # for char_metrics).
    _angle = resolve_viewpoint_angle(shot["shot_type"],
                                     shot.get("camera_angle"))
    # Map-board frontal rule (Stage 3 / F5 x F9): a map_panel
    # environment is a VERTICAL board facing the camera. A steep
    # requested angle (birds_eye/high_angle) looks down at the
    # ground and shows the board edge-on — the probe's birds_eye
    # map still was 95% ground with the board cut at the top edge.
    # Map shots therefore render with a frontal (eye_level)
    # viewpoint so the map stays legible; the requested angle is
    # recorded on the report (camera_angle_requested), never
    # silently dropped. Shot-type azimuth (OTS/SRS) still applies:
    # only the elevation is clamped.
    _angle_requested = _angle
    _map_frontal = False
    if _shot_location_kind(shot) == "map_panel" \
            and _angle != "eye_level":
        _angle = "eye_level"
        _map_frontal = True
    if shot["shot_type"] == "over_the_shoulder" \
            and _ots_subject in names:
        _subject_name = _ots_subject
    else:
        _subject_name = actor
    if names and _subject_name in world_xs and shot["shot_type"] in (
            "close_up", "extreme_close_up", "reaction",
            "shot_reverse_shot", "over_the_shoulder", "object_insert"):
        _target_x = world_xs[_subject_name]
        _target_z = world_zs[_subject_name]
    elif names:
        _target_x = sum(world_xs[n] for n in names) / len(names)
        _target_z = 0.0
    else:
        # Empty-cast shot: location-only, camera on the origin.
        _target_x, _target_z = 0.0, 0.0
    _counterpart_x = world_xs[_ots_counterpart] \
        if _ots_counterpart in world_xs \
        else (world_xs[other] if other in world_xs else None)
    # Per-character body scales (scale-variant rule): the package
    # carries scale_ratio on cast entries; default 1.0. Invalid
    # values fall back to 1.0 (char_metrics guards too).
    char_scales = {}
    for n in names:
        _entry = _char_by_name.get(n)
        _ratio = _entry[1].get("scale_ratio") if _entry else None
        try:
            _ratio = float(_ratio)
        except (TypeError, ValueError):
            _ratio = 1.0
        char_scales[n] = _ratio if _ratio > 0 else 1.0
    # Dolly out for scaled-up subjects whose standing box would
    # overflow the frame top (a 1.8x body at the standard radius
    # clips its head even in a wide shot). Unscaled shots get 1.0
    # and are pixel-identical to before.
    _radius_scale = _fit_radius_scale(
        shot["shot_type"], _angle, _target_x, _target_z,
        _counterpart_x, shot.get("srs_side", 0),
        [(world_xs[n], world_zs[n]) for n in names],
        [char_scales[n] for n in names])
    shot_cam = viewpoint_for_shot(
        shot["shot_type"], _angle,
        subject_pos=(_target_x, 1.2, _target_z),
        counterpart_x=_counterpart_x, srs_side=shot.get("srs_side", 0),
        radius_scale=_radius_scale)
    # OTS foreground fit (Stage 3 / F9): the shoulder azimuth swings
    # the listener toward the frame edge, and the unadjusted staging
    # slot put their head ~60% out of frame (F9 probe). Pull the
    # listener's world x toward the subject in steps until the head
    # circle fits horizontally (40 px margin absorbs the head-joint
    # offset from the staging point). Only the horizontal head fit
    # is constrained: the listener is a partial foreground figure,
    # so feet below the frame are the OTS language, not a defect.
    # The listener never crosses the subject (stops 0.4 short), so
    # the azimuth side computed above stays valid.
    if _ots_listener is not None and actor in world_xs:
        _subj_x = world_xs[actor]
        _lx = world_xs[_ots_listener]
        _side = 1.0 if _lx >= _subj_x else -1.0
        for _step in range(12):
            _gx, _gy, _gh = char_metrics(
                shot_cam, _lx, world_zs[_ots_listener],
                base_scale=char_scales[_ots_listener])
            _hr = 0.34 * _gh / 2.0
            if 40.0 + _hr <= _gx <= W - 40.0 - _hr:
                break
            _next = _lx - _side * 0.2
            if (_side > 0.0 and _next < _subj_x + 0.4) or \
                    (_side < 0.0 and _next > _subj_x - 0.4):
                _lx = _subj_x + _side * 0.4
                break
            _lx = _next
        world_xs[_ots_listener] = _lx
    metrics = {n: char_metrics(shot_cam, world_xs[n], world_zs[n],
                              base_scale=char_scales[n])
               for n in names}
    staging = {n: metrics[n][0] for n in names}
    ground_ys = {n: metrics[n][1] for n in names}
    char_heights = {n: metrics[n][2] for n in names}
    _, shot_ground_y, _ = char_metrics(shot_cam, _target_x, WORLD_Z)
    chars: dict[str, object] = {}
    for n in names:
        _i, _c = _char_by_name[n]
        chars[n] = map_character(
            _c, _i, costume_override=_costume_overrides.get(n),
            height_px=char_heights[n])
    # F6: the bus shows only when this shot stages a boarding
    # (_shot_has_bus: shot-level cues or a compiled BOARD event).
    # The check runs BEFORE the scene build: the environment path
    # takes the bus as extra elements, the legacy path as appended
    # Box3Ds.
    _has_bus = _shot_has_bus(shot, package)
    (boxes, sky_top, sky_bottom, rainy, ground_color, _env_pkg,
     _is_map) = build_scene_ex_with_package(
         shot.get("location_keyword", "street"), shot.get("setting", ""),
         shot.get("mood", "warm"), shot.get("time_of_day", "day"),
         location_data=shot.get("v1_location"),
         location_text=shot.get("location_text", ""),
         extra_elements=_bus_extra_elements() if _has_bus else None)
    _map_report = None
    _env_archetype = None
    # ---- static background, rendered ONCE per shot --------------------
    # render_frame() runs a full-frame GaussianBlur contact shadow for
    # EVERY box (~30) and character on EVERY call — ~10-15 s per frame
    # at 1920x1080. The camera is static within a shot and the boxes
    # never move, so the background (sky, ground, boxes, box shadows)
    # is rendered once and reused; only the characters, rain, prop and
    # subtitles change per frame. The lamp glow is baked into the
    # background too (static). This is a renderer-side optimisation
    # only — the frames are pixel-identical in content to the
    # per-frame render.
    if _is_map:
        # W2b: the map IS the background (real polygons, never a
        # rectangular card). Fails loudly without a usable dataset.
        bg_scene = Scene25D(boxes=[], characters=[], camera=shot_cam,
                            sky_top=sky_top, sky_bottom=sky_bottom,
                            ground_color=ground_color,
                            ground_extent=30.0)
        bg_img, _map_report = _render_map_background(shot, package)
        fg_layer = None
        _env_archetype = "MAP"
    elif _env_pkg is not None:
        # W2: semantic environment, two passes — BG+MG behind the
        # characters, FG occluders composited over them. Foreground
        # elements are frustum-fitted against the widest shot
        # camera so staging is stable across shots of the location.
        _env_archetype = _env_pkg.get("archetype")
        bg_scene = Scene25D(boxes=boxes, characters=[], camera=shot_cam,
                            sky_top=sky_top, sky_bottom=sky_bottom,
                            ground_color=ground_color,
                            ground_extent=30.0)
        _ref_cam = viewpoint_for_shot(
            "establishing", "eye_level", subject_pos=(0.0, 1.2, 0.0))
        _env_fitted = fit_foreground_to_frustum(
            _env_pkg, _ref_cam, (W, H))
        bg_img = render_environment(
            _env_fitted, shot_cam, (W, H), draw_layers=("BG", "MG"))
        fg_layer = None
        if _env_fitted.get("layers", {}).get("FG"):
            _fg = render_environment(
                _env_fitted, shot_cam, (W, H), draw_layers=("FG",),
                transparent=True)
            fg_layer = _fg if _fg.getbbox() else None
        if rainy:
            _lx, _ly, _, _ = shot_cam.project((4.0, 0.0, -1.5), W, H)
            _hx2, _hy2, _, _ = shot_cam.project((4.0, 3.3, -1.5), W, H)
            _lamp_glow(bg_img, (int(_lx), int(_ly)),
                       (int(_hx2), int(_hy2)))
        if _has_bus:
            # F6: bus details on the static background, once per
            # shot, projected with the shot camera so they track
            # the bus at any viewpoint.
            _draw_bus_details(bg_img, shot_cam)
    else:
        # Legacy Scene25D path (keyword/inline locations, no trait
        # block): bus boxes appended, boxes rendered with the shot
        # camera, foreground boxes split into the occlusion layer.
        if _has_bus:
            # The bus, arriving from the right: body + lit windows
            # + door at BUS_DOOR_X. A plain box would read as a
            # building; the windows + wheels + door make it a bus
            # -- and the F6 2D overlay (_draw_bus_details, on the
            # static background) adds the wheels, lights, sign and
            # stripe the 3D boxes cannot show (the kerb occludes
            # the 3D wheels).
            boxes += [
                Box3D(center=BUS_BODY_CENTER, size=BUS_BODY_SIZE,
                      color=(40, 90, 130), name="bus_body"),
                Box3D(center=(2.0, 1.4, -2.95), size=(0.6, 0.5, 0.08),
                      color=(255, 220, 130), name="bus_window_1"),
                Box3D(center=(2.8, 1.4, -2.95), size=(0.6, 0.5, 0.08),
                      color=(255, 220, 130), name="bus_window_2"),
                Box3D(center=(3.4, 1.4, -2.95), size=(0.6, 0.5, 0.08),
                      color=(255, 220, 130), name="bus_window_3"),
                Box3D(center=(BUS_DOOR_X, 0.9, -2.95),
                      size=(0.5, 1.4, 0.08),
                      color=(20, 40, 60), name="bus_door"),
                Box3D(center=(BUS_WHEEL_X[0], 0.15, -2.95),
                      size=(0.4, 0.3, 0.1),
                      color=(20, 20, 24), name="bus_wheel_1"),
                Box3D(center=(BUS_WHEEL_X[1], 0.15, -2.95),
                      size=(0.4, 0.3, 0.1),
                      color=(20, 20, 24), name="bus_wheel_2"),
            ]
        bg_scene = Scene25D(boxes=boxes, characters=[], camera=shot_cam,
                            sky_top=sky_top, sky_bottom=sky_bottom,
                            ground_color=ground_color,
                            ground_extent=30.0)
        bg_img = render_frame(bg_scene, W, H)
        if rainy:
            _lx, _ly, _, _ = shot_cam.project((4.0, 0.0, -1.5), W, H)
            _hx2, _hy2, _, _ = shot_cam.project((4.0, 3.3, -1.5), W, H)
            _lamp_glow(bg_img, (int(_lx), int(_ly)),
                       (int(_hx2), int(_hy2)))
        if _has_bus:
            # F6: bus details on the static background, once per
            # shot, projected with the shot camera so they track
            # the bus at any viewpoint.
            _draw_bus_details(bg_img, shot_cam)
        # Foreground occlusion layer (Stage 3 / Fix 3): boxes
        # standing in front of the character plane, rendered
        # boxes-only with the same projection/shading, composited
        # AFTER the characters each frame (before rain/prop/
        # subtitles) so a foreground crate genuinely occludes the
        # feet behind it. The background keeps the full scene (so
        # foreground boxes' contact shadows stay under the
        # characters, where they belong); the layer redraws the
        # same pixels over the characters.
        _bg_boxes, _fg_boxes = split_foreground_boxes(boxes)
        fg_layer = render_boxes_layer(bg_scene, W, H, boxes=_fg_boxes) \
            if _fg_boxes else None
    # Foreground occlusion shape for layered-depth staging (R5/R10a):
    # built once per shot (static within the shot, like the camera),
    # composited per frame after the characters and the split-screen
    # composite, before the crop.
    _occluder = None
    if _staging_mode == "layered_depth":
        _occluder = _render_occlusion_layer(
            shot.get("occluder_side"), shot.get("occluder_style"))
    # W1: character contact shadows are drawn per character in
    # _build_frame from the live foot positions (ratio-capped); the
    # old fixed 320x48 tile is gone.
    # Losing cues never reach staging: filter the recorded discards
    # for this shot's scene before any cue is read (poses, puddle,
    # legacy prop branch).
    cues = _effective_cues(shot, package)
    # A prop is drawn when the cues manipulate one (bend_pick/give/
    # take, as before) OR when the scene declares props and one is
    # currently held (F7: a held letter stays visible in dialogue
    # shots of its scene even without a manipulation cue).
    has_prop = any(c in cues for c in ("bend_pick", "give", "take")) \
        or bool(shot.get("props")) and bool(shot.get("prop_holder"))
    # A kneel lunges ~250 px behind the root: keep the actor far
    # enough from the frame edge that the whole body (jacket, back
    # leg) stays in frame. v11: Minh knelt at the left staging slot
    # and his jacket was cut at x=0. The prop follows (ax+220).
    # Guarded for empty-cast shots (no actor, no staging).
    if "bend_pick" in cues and actor is not None and actor in staging:
        staging[actor] = min(max(staging[actor], 380), W - 380)
    # ---- facing: speaker faces the listener, narrator faces right --
    facings: dict[str, int] = {}
    for n, ch in chars.items():
        facing = 1
        if n == actor and other is not None:
            facing = 1 if staging[other] > staging[n] else -1
        elif n != actor and actor is not None:
            facing = 1 if staging[actor] > staging[n] else -1
        facings[n] = facing
        standing(ch, staging[n], ground_ys[n], facing=facing)
    # ---- W4: compiled action events + prop machine -------------------
    # Poses are staged BEFORE the pose fns run: the standing joints
    # snapshot gives hips/heads for pocket rests and gaze targets.
    # (_per_actor/_shot_events/_face_keyframes/_blink_times/_t0 and
    # the id maps were computed in the early W4 block above, before
    # the camera, so furniture staging could use them.)
    joints0 = {n: chars[n].joints() for n in names}
    _direction = 1
    if actor is not None and other is not None:
        _direction = 1 if staging[other] > staging[actor] else -1
    _anchors = {n: _furniture_anchors(
        _env_pkg, shot_cam, (W, H), staging[n], ground_ys[n],
        chars[n].H, facings[n]) for n in names}
    # Prop rest positions: surface props (letter/pen/...) rest on the
    # paper; everything else rests in its owner's pocket (hidden
    # until manipulated — never on the ground by default, P2). A
    # prop whose semantic initial location is ON_GROUND rests on
    # the ground line instead (ground rule, §7).
    _prop_dicts = {str(p["id"]): p for p in package.get("props") or []
                   if isinstance(p, dict) and p.get("id")}
    _first_actor_for_pid: dict[str, str] = {}
    for _e in _shot_events:
        _pid = _e.get("prop_id")
        if _pid and str(_pid) not in _first_actor_for_pid:
            _nm = _id_to_name.get(str(_e.get("actor_id")))
            if _nm in joints0:
                _first_actor_for_pid[str(_pid)] = _nm
    _pids_all: list[str] = []
    for _pid in [str(p) for p in (shot.get("props") or [])]:
        if _pid in _prop_dicts and _pid not in _pids_all:
            _pids_all.append(_pid)
    for _e in _shot_events:
        _pid = _e.get("prop_id")
        if _pid and str(_pid) in _prop_dicts \
                and str(_pid) not in _pids_all:
            _pids_all.append(str(_pid))
    _tracker = SemanticPropTracker(
        [_prop_dicts[_pid] for _pid in _pids_all], _shot_events) \
        if _pids_all else None
    (_rests, _rest_kinds, _pocket_anchors) = _assign_prop_rests(
        _pids_all, _prop_dicts, _first_actor_for_pid, actor, _anchors,
        joints0, ground_ys, staging, _name_to_id, tracker=_tracker,
        fallback_ground_y=shot_ground_y, events=_shot_events)
    (_prop_machine, _machine_pids, _machine_kinds,
     _machine_rest_kinds, _prop_diagnostics) = _build_shot_prop_machine(
         package, shot, _shot_events, _rests, _rest_kinds,
         _pocket_anchors, _id_to_name, _name_to_id, set(names), _t0)
    # ---- pose functions for this shot -------------------------------
    fns: dict[str, object] = {}
    prop = {"x": 0, "y": 0}
    give_fn = None
    if shot["kind"] == "action" and actor is not None:
        ax = staging[actor]
        # Locomotion goes TOWARD the other character (Lan runs TO
        # Minh; Minh walks TO the station), not blindly right.
        direction = 1
        if other is not None:
            direction = 1 if staging[other] > ax else -1
        if "board" in cues:
            # Lan boards: walk to the bus door.
            fns[actor] = walk_to(chars[actor], ax, sx(BUS_DOOR_X, shot_cam),
                                 duration, ground_ys[actor])
        elif "run" in cues:
            fns[actor] = run_to(chars[actor], ax, ax + 380 * direction,
                                duration, ground_ys[actor])
        elif any(c in cues for c in ("walk", "walk_fast")):
            fns[actor] = walk_to(chars[actor], ax, ax + 320 * direction,
                                 duration, ground_ys[actor])
        elif "bend_pick" in cues:
            prop_x, prop_y = ax + 220, ground_ys[actor] - 6
            prop.update(x=prop_x, y=prop_y)
            fns[actor] = kneel_pick(chars[actor], (prop_x, prop_y), duration, ground_ys[actor])
        elif "give" in cues and other is not None:
            standing(chars[actor], ax, ground_ys[actor],
                     facing=1 if staging[other] > ax else -1)
            standing(chars[other], staging[other], ground_ys[other],
                     facing=1 if ax > staging[other] else -1)
            give_fn = give_to(chars[actor], chars[other], prop, duration)
            fns[actor] = give_fn
        elif "wave" in cues:
            fns[actor] = wave(chars[actor], duration)
        else:
            fns[actor] = idle(chars[actor], duration, ground_ys[actor])
    # ---- pre-warm every closure at its start pose -------------------
    for n, fn in list(fns.items()):
        try:
            fn(0.0)
        except Exception:
            pass
    if give_fn is not None:
        give_fn(0.0)
    for n, ch in chars.items():
        if n not in fns:
            fns[n] = idle(ch, 99.0, ground_ys[n])
            fns[n](0.0)
    # ---- W4: compiled events override cue/idle fns ------------------
    # Each actor with events gets a sequenced fn (windows in time
    # order, overlays for carry_bag, blocks for handover receivers so
    # the pair fn owns the receiver's pose). Windows whose primitive
    # cannot be built fall back to idle AND are recorded loudly in
    # the shot report (never a silent substitution).
    _dispatch_fallback: list[str] = []
    _pair_blocks: dict[str, list] = {}
    _pair_windows: dict[str, list] = {}
    if _per_actor:
        for _name, _wins in _per_actor.items():
            if _name not in chars:
                continue
            _ctx = {
                "name": _name, "char": chars[_name],
                "other_name": other,
                "other_char": chars.get(other) if other else None,
                "staging_x": staging[_name],
                "ground_y": ground_ys[_name],
                "direction": _direction, "facing": facings[_name],
                "prop": prop, "paper": _anchors[_name]["paper"],
                "desk": _anchors[_name]["desk"],
                "chair_x": _anchors[_name]["chair"]["x"],
                "seat_y": _anchors[_name]["chair"]["seat_y"],
                "rests": _rests, "pos": {"x": staging[_name]},
                "joints0": joints0, "id_to_name": _id_to_name,
                "name_to_id": _name_to_id,
            }
            _base_windows = []
            _overlays = []
            _has_sit = any(
                ((_ev.get("required_pose") or {}).get("primitive")
                 == "sit_at_desk")
                for _ws, _we, _ev in _wins)
            if _seated_at_start.get(_name) and not _has_sit:
                # Seated state carried across the CUT: seat the
                # character in the first instant of the shot (a
                # 1 ms hold window at the sit completion pose) so
                # the following windows (write/sign/...) act on a
                # seated body instead of a standing one. The
                # pre-warm at t=0 runs this window, so stills
                # render seated too.
                _ctx["pos"]["x"] = _ctx["chair_x"]
                _sit_dur = 0.5
                _sit_fn = sit_at_desk(
                    chars[_name], _ctx["chair_x"], _ctx["seat_y"],
                    _sit_dur, ground_ys[_name], desk=_ctx["desk"])
                _base_windows.append((
                    0.0, 0.001,
                    lambda _t, _f=_sit_fn, _d=_sit_dur: _f(_d)))
            for _start, _end, _event in _wins:
                _pose = _event.get("required_pose") or {}
                _prim = _pose.get("primitive")
                _params = _pose.get("params") or {}
                _dur = max(0.05, _end - _start)
                if _prim == "hand_over":
                    _recv = _id_to_name.get(str(_event.get("target_id"))) \
                        if _event.get("target_id") else None
                    if _recv not in chars:
                        _recv = other if other in chars else None
                    if _recv is None:
                        _dispatch_fallback.append(
                            str(_event.get("action_id")))
                        _base_windows.append((
                            _start, _end,
                            idle(chars[_name], _dur, ground_ys[_name])))
                        continue
                    _pair_fn = hand_over(chars[_name], chars[_recv],
                                         prop, _dur)
                    _base_windows.append((_start, _end, _pair_fn))
                    _pair_blocks.setdefault(_recv, []).append(
                        (_start, _end))
                    continue
                _fn = _event_fn(_prim, _params, _event, _ctx, _dur)
                if _fn is None:
                    _dispatch_fallback.append(
                        str(_event.get("action_id")))
                    _fn = idle(chars[_name], _dur, ground_ys[_name])
                    _base_windows.append((_start, _end, _fn))
                elif _prim == "carry_bag":
                    _overlays.append((_start, _end, _fn))
                else:
                    _base_windows.append((_start, _end, _fn))
            _pair_windows[_name] = (_base_windows, _overlays)
        _override_names = set(_pair_windows) | set(_pair_blocks)
        for _name in _override_names:
            if _name not in chars:
                continue
            _base_windows, _overlays = _pair_windows.get(
                _name, ([], []))
            _base_fn = fns.get(_name)
            fns[_name] = _sequence_fns(
                _base_windows, _overlays, _base_fn,
                blocks=_pair_blocks.get(_name, ()))
            try:
                fns[_name](0.0)
            except Exception:
                pass
        if actor in _per_actor:
            # The event fn owns the actor: the legacy give_fn must not
            # override it in the frame loop.
            give_fn = None
    talk_nod = None
    if shot["kind"] in ("narration", "dialogue") and actor is not None:
        talk_nod = nod(chars[actor], duration, freq=1.1, amp=0.08)
        talk_nod(0.0)
    # ---- subtitles for this shot ------------------------------------
    phrases = split_subtitle(shot.get("text", "")) if shot.get("text") else []
    # Windows span the VOICE only, not the 0.35 s beat after it.
    windows = phrase_windows(
        0.0, shot.get("voice_duration", duration), phrases) if phrases else []
    # ---- frame loop ---------------------------------------------------
    # Shot-level character view (channel study R1: frontal hero):
    # the directive's character_view is the default view for every
    # character in this shot; turns still animate through
    # front/three-quarter via resolve_view, and the OTS listener
    # still renders from behind.
    _shot_view = shot.get("character_view") \
        if shot.get("character_view") in VIEWS else "profile"
    # Split-screen spec (channel study R10c): per-side expression
    # overrides; the two viewports share one camera/staging. A side
    # without an override renders the normal expressions.
    _split = shot.get("split_screen") \
        if isinstance(shot.get("split_screen"), dict) else None
    _split_left = (_split or {}).get("left") \
        if isinstance((_split or {}).get("left"), dict) else None
    _split_right = (_split or {}).get("right") \
        if isinstance((_split or {}).get("right"), dict) else None

    def _gaze_target_for(event, joints_map):
        """Gaze target (x, y) for a LOOK_AT event: its prop rest, its
        contact target, or the target character's head. None when the
        target cannot be resolved (eyes stay forward)."""
        pid = event.get("prop_id")
        if pid and str(pid) in _rests:
            return _rests[str(pid)]
        for cp in event.get("contact_points") or []:
            tid = cp.get("target_id")
            if tid and str(tid) in _rests:
                return _rests[str(tid)]
            if tid and str(tid) in _id_to_name:
                nm = _id_to_name[str(tid)]
                if nm in joints_map:
                    return joints_map[nm]["head"]
        tid = event.get("target_id")
        if tid and str(tid) in _id_to_name:
            nm = _id_to_name[str(tid)]
            if nm in joints_map:
                return joints_map[nm]["head"]
        return None

    # Last built frame's prop draws, for the shot report (P9/tests).
    _prop_draws_last: list = []

    def _build_frame(t, fi, expr_overrides, *, paint_glow=True):
        # paint_glow=False defers the energy halo to the pass-2
        # re-frame (deferred inserts): a halo painted pre-crop is
        # magnified by the crop zoom into a wash.
        """One full frame: static background + contact shadows +
        rig characters + foreground boxes + rain/puddle + prop.
        Pure given the poses (the pose closures run once per frame
        in the loop, before the build): calling it twice with
        different expression overrides yields the two split-screen
        viewports of the SAME moment. Returns (image, joints,
        prop_xy, telemetry_draws) -- the last is the per-frame prop
        draw list for the grip telemetry (sprint section 10)."""
        img = bg_img.copy()
        _grip_matches: list[dict] = []
        for n in names:
            # W1: ratio-capped contact shadow from the live feet.
            _draw_character_shadow(
                img, chars[n], shot_cam,
                (world_xs[n], 0.0, world_zs[n]), bg_scene.lights.key)
        d = ImageDraw.Draw(img, "RGBA")
        # Poses are set: the live joints give heads (gaze targets),
        # hips (pocket rests) and hands (prop attachment) for this
        # exact frame.
        joints_pre = {n: chars[n].joints() for n in names}
        # Joints keyed by both display name and character id: the
        # state machine resolves holders by id, the frame loop by
        # name. Built once, shared by the machine draws and the
        # energy-glow pass below.
        _joints_by_key: dict = {}
        for _n, _j in joints_pre.items():
            _joints_by_key[_n] = _j
            _cid = _name_to_id.get(_n)
            if _cid:
                _joints_by_key[_cid] = _j
        # W4: prop transforms from the state machine (global time),
        # computed once per frame and reused for grips + drawing.
        _machine_draws: list[tuple] = []
        _machine_meta: dict[str, dict] = {}
        _grips: dict[str, dict] = {}
        if _prop_machine is not None and joints_pre:
            for _pid in _machine_pids:
                (_mx, _my, _mang, _mstate, _mhand) = \
                    _prop_machine.transform_at(_pid, _t0 + t,
                                               _joints_by_key)
                if _mstate == "WORLD_STATIC" and \
                        _machine_rest_kinds.get(_pid) == "pocket":
                    continue  # in the pocket: not visible (P2)
                if _mstate == "WORLD_STATIC" and \
                        _machine_rest_kinds.get(_pid) == "ground" \
                        and not _prop_machine.ground_rest_allowed(
                            _pid, _t0 + t):
                    # Ground rest needs a DEFINITIVE ON_GROUND
                    # semantic location at this instant; without
                    # it the prop must not sit on the ground.
                    continue
                _detail = _prop_machine.detail_at(_pid, _t0 + t)
                _holder_name = _id_to_name.get(
                    str(_detail.get("holder"))) \
                    if _detail.get("holder") else None
                if _machine_kinds[_pid] == "bag" and _mstate in (
                        "GRASPED", "ATTACHED_TO_HAND", "IN_USE") \
                        and _holder_name in chars:
                    # A carried bag hangs below the holding hand.
                    _my += 68.0 * chars[_holder_name].H / 560.0
                _machine_draws.append(
                    (_pid, _mx, _my, _machine_kinds[_pid],
                     float(_detail.get("open_u", 0.0)), _mstate,
                     pen_tip_position(
                         (_mx, _my),
                         chars[_holder_name].pose.get(
                             "facing", facings.get(_holder_name, 1)),
                         chars[_holder_name].H)
                     if _machine_kinds[_pid] == "pen" and _mstate in (
                         "GRASPED", "ATTACHED_TO_HAND", "IN_USE")
                     and _holder_name in chars else None))
                if _holder_name in names and _mstate in (
                        "GRASPED", "ATTACHED_TO_HAND", "IN_USE") \
                        and _mhand in ("l", "r"):
                    _grips.setdefault(_holder_name, {})[_mhand] = "grip"
                _machine_meta[_pid] = {
                    "holder": _holder_name, "hand": _mhand,
                    "angle": float(_mang)}
        # W4 depth order: props at rest on a surface (the desk, the
        # paper) sit BEHIND the characters; held/moving props draw
        # in front. A letter on the desk must not paint over the
        # seated writer's legs.
        _prop_draws_last[:] = [(d[0], d[5]) for d in _machine_draws]
        _behind_draws = [d for d in _machine_draws
                         if d[5] == "WORLD_STATIC"]
        _front_draws = [d for d in _machine_draws
                        if d[5] != "WORLD_STATIC"]
        for (_pid, _dx, _dy, _dkind, _open_u, _st, _tip) \
                in _behind_draws:
            _draw_prop(d, _dx, _dy, kind=_dkind, open_u=_open_u,
                       tip=_tip)
        joints_now: dict[str, dict] = {}
        for n in names:
            ch = chars[n]
            # Expression: a split-screen side override wins for
            # that viewport (per-character, else whole-side); else
            # the line's explicit expression wins for the speaker
            # when present and valid (Stage 3); everyone else is
            # neutral, and an invalid expression falls back to the
            # text-derived one (see resolve_expression).
            expr = None
            if expr_overrides:
                _per = expr_overrides.get("expressions") or {}
                if n in _per:
                    expr = _per[n]
                elif expr_overrides.get("expression"):
                    expr = expr_overrides["expression"]
            _expr_params = None
            if expr is None:
                # W4: face_only keyframes win within their windows.
                _kf = None
                for (_s, _e, _face) in _face_keyframes.get(n, []):
                    if _s <= t < _e:
                        _kf = _face
                        break
                if _kf is not None:
                    expr = _kf
                elif n == shot.get("speaker"):
                    # W4: negation-aware interpretation of the V1
                    # label; falls back to the legacy resolution
                    # when nothing matches.
                    _label = shot.get("expression")
                    _interp = interpret_expression(_label) \
                        if _label else None
                    if _interp in EXPRESSION_NAMES:
                        expr = _interp
                    else:
                        expr = resolve_expression(
                            _label, shot.get("text", ""))
                else:
                    expr = "neutral"
                # Param-dict path ONLY when W4 adds information
                # (extended-label blend, an active blink, or
                # lip-sync above the base mouth): otherwise the
                # legacy name path renders pixel-identically.
                _base_params = dict(
                    EXPRESSIONS.get(expr) or EXPRESSIONS["neutral"])
                _params = None
                if _kf is None and n == shot.get("speaker") \
                        and shot.get("expression"):
                    _cand = interpret_expression_params(
                        shot.get("expression"))
                    if _cand is not None and _cand != _base_params:
                        _params = dict(_cand)
                _blink_mult = 1.0
                _blinks = _blink_times.get(n) or []
                if _blinks:
                    _blink_mult = blink_envelope(t, _blinks)
                _mouth = 0.0
                if n == shot.get("speaker") and shot["kind"] in (
                        "narration", "dialogue"):
                    _mouth = speech_mouth_envelope(
                        t, [{"start": 0.0, "end": float(
                            shot.get("voice_duration", duration))}])
                if _params is not None or _blink_mult < 1.0 \
                        or _mouth > _base_params.get("mouth_open", 0.0):
                    if _params is None:
                        _params = dict(_base_params)
                    if _blink_mult < 1.0:
                        _params["eye_h"] = _params.get(
                            "eye_h", 1.0) * _blink_mult
                    if _mouth > _params.get("mouth_open", 0.0):
                        _params["mouth_open"] = _mouth
                    _expr_params = _params
            # W4 gaze: LOOK_AT events aim the eyes at their target;
            # in dialogue the speaker and listener look at each
            # other. The OTS listener (back view) has no face.
            _gaze = None
            if n != _ots_listener:
                _head = joints_pre[n]["head"]
                _target = None
                for (_s, _e, _event) in _per_actor.get(n, []):
                    if _s <= t < _e and \
                            _event.get("action_type") == "LOOK_AT":
                        _target = _gaze_target_for(
                            _event, joints_pre)
                        break
                if _target is None and shot["kind"] == "dialogue" \
                        and other is not None and other in joints_pre \
                        and n != other:
                    _target = joints_pre[other]["head"]
                if _target is not None:
                    _gaze = gaze_for_target(_head, _target)
            # F9: the over-the-shoulder foreground listener is drawn
            # from behind (back of the head, no face — the art system
            # renders view "back" with hair, never a face); everyone
            # else keeps the pose-derived view (shot-level default).
            _view = "back" if n == _ots_listener \
                else resolve_view(ch, default=_shot_view)
            joints_now[n] = draw_character_v4(
                d, ch,
                expression=(_expr_params
                            if _expr_params is not None else expr),
                view=_view, gaze=_gaze,
                hand_grips=_grips.get(n))
        if fg_layer is not None:
            # Foreground boxes occlude the characters behind them.
            img.paste(fg_layer, (0, 0), fg_layer)
            d = ImageDraw.Draw(img, "RGBA")
        if rainy:
            _draw_rain(d, fi)
        # Puddle beside the wallet (bend_pick scenes): the wallet lies
        # at its edge and the character kneels beside it, never in it.
        # The ground line is the shot camera's (per-actor when an
        # actor exists, else the shot ground line).
        _prop_ground_y = ground_ys[actor] if actor in ground_ys \
            else shot_ground_y
        if "bend_pick" in cues and prop.get("x"):
            _draw_puddle(d, prop["x"], _prop_ground_y)
        # prop: at the actor's hand once picked up / at the handover
        # midpoint during give, on the ground before that. In dialogue
        # shots the current holder (tracked in plan_shots) holds it.
        # Empty-cast shots have no hands: the prop is skipped.
        wx, wy = None, None
        _home_x = staging[actor] + 220 if actor in staging else W // 2
        # Energy glow (item 10): held energy-carrying props emit
        # a halo from the lighting stage, painted after the
        # characters and before the props themselves, so the prop
        # stays crisp on top of its own light and the halo tints
        # the surroundings. No record (not held, no energy spec)
        # means no glow; radius 0 paints nothing. The record's
        # positions are staging-plane pixels, the space this
        # frame is built in, so no bridge is needed here.
        if paint_glow and _prop_machine is not None and joints_pre:
            for _pid in _machine_pids:
                _glow = _prop_machine.energy_glow_at(
                    _pid, _t0 + t, _joints_by_key)
                if _glow is not None and _glow["radius"] > 0:
                    paint_energy_glow(img, _glow)
        if _prop_machine is not None:
            # W4: held/moving props draw at their state-machine
            # transform (hand-attached, in use, or in transfer).
            # At-rest props were drawn behind the characters
            # above; pocket rests never reach _machine_draws.
            if _front_draws:
                d = ImageDraw.Draw(img, "RGBA")
                for (_pid, _dx, _dy, _dkind, _open_u, _st, _tip) \
                        in _front_draws:
                    _draw_prop(d, _dx, _dy, kind=_dkind, open_u=_open_u,
                               tip=_tip)
                # Hands over props (finger wrap): the prop painted
                # over the gripping fingers; repaint the grip fan
                # from the prop's grip point along the forearm
                # direction so the hand reads as wrapped around
                # it. Matched by hand position (the PSM transform
                # is the hand position for held states). The
                # over-the-shoulder listener is skipped: its limbs
                # draw from behind.
                for (_pid, _dx, _dy, _dkind, _open_u, _st, _tip) \
                        in _front_draws:
                    for _holder, _hands in _grips.items():
                        if _holder == _ots_listener \
                                or _holder not in joints_now \
                                or _holder not in chars:
                            continue
                        for _side, _mode in _hands.items():
                            if _mode != "grip":
                                continue
                            _jn = joints_now[_holder]
                            _hand_key = "hand_" + _side
                            _elbow_key = "elbow_" + _side
                            if _hand_key not in _jn \
                                    or _elbow_key not in _jn:
                                continue
                            _hx, _hy = _jn[_hand_key]
                            if abs(_hx - _dx) > 30 \
                                    or abs(_hy - _dy) > 30:
                                continue
                            _ex, _ey = _jn[_elbow_key]
                            draw_grip_fingers(
                                d, (_dx, _dy), (_hx - _ex, _hy - _ey),
                                chars[_holder], INK_RGB)
                            _grip_matches.append({
                                "pid": _pid, "holder": _holder,
                                "hand": _side})
                wx, wy = _front_draws[0][1], _front_draws[0][2]
            elif _behind_draws:
                wx, wy = _behind_draws[0][1], _behind_draws[0][2]
        elif has_prop and joints_now:
            d = ImageDraw.Draw(img, "RGBA")
            if give_fn is not None:
                wx, wy = prop["x"], prop["y"]
            elif "bend_pick" in cues and actor in joints_now \
                    and t >= 0.5 * duration:
                hx, hy = joints_now[actor]["hand_r"]
                wx, wy = hx + 10, hy + 14
            elif "take" in cues and other is not None \
                    and other in joints_now:
                hx, hy = joints_now[other]["hand_r"]
                wx, wy = hx + 10, hy + 14
            elif shot["kind"] != "action":
                holder = shot.get("prop_holder")
                if holder in joints_now:
                    hx, hy = joints_now[holder]["hand_r"]
                    wx, wy = hx + 10, hy + 14
                else:
                    wx, wy = prop["x"] or _home_x, _prop_ground_y - 6
            else:
                wx, wy = prop["x"] or _home_x, _prop_ground_y - 6
            _draw_prop(d, wx, wy,
                       kind=shot.get("prop_kind") or "wallet")
        # Grip telemetry draws (sprint section 10): every prop draw
        # this frame, with its state-machine holder/hand/angle and
        # whether the grip fan was repainted over it. The frame
        # loop pairs these with the live hand joints.
        _telemetry_draws: list[dict] = []
        if _prop_machine is not None:
            for (_pid, _dx, _dy, _dkind, _open_u, _st, _tip) \
                    in _machine_draws:
                _meta = _machine_meta.get(_pid, {})
                _telemetry_draws.append({
                    "pid": _pid, "kind": _dkind, "state": _st,
                    "holder": _meta.get("holder"),
                    "hand": _meta.get("hand"),
                    "x": float(_dx), "y": float(_dy),
                    "angle": _meta.get("angle"),
                    "open_u": float(_open_u),
                    "grip_repaint": any(
                        m["pid"] == _pid for m in _grip_matches),
                })
        elif has_prop and joints_now and wx is not None:
            _telemetry_draws.append({
                "pid": None,
                "kind": shot.get("prop_kind") or "wallet",
                "state": "legacy", "holder": None, "hand": None,
                "x": float(wx), "y": float(wy), "angle": None,
                "open_u": 0.0, "grip_repaint": False,
            })
        # prop position for the camera (object_insert frames the prop).
        _prop_xy = (wx, wy) if wx is not None else None
        return img, joints_now, _prop_xy, _telemetry_draws

    violations: list[str] = []
    max_jump = 0.0
    prev_joints = None
    foot_slide = 0.0
    # Phase G: per-character foot positions per frame, for footfall
    # times (footstep SFX anchors). Recorded for every frame; the
    # report computes strikes only from multi-frame renders (a still
    # carries no motion), and the foley stage requires >= 3 strikes
    # per character before placing any footstep sound.
    _footfall_frames: dict[str, list[dict]] = {n: [] for n in names}
    # Grip telemetry (sprint section 10): one record per built
    # frame for prop-machine / legacy-prop shots.
    _grip_telemetry: list[dict] = []
    frames_written = []
    still_path = None
    if still_only:
        # W4: a still must equal the video frame at the same time.
        # Pose fns are stateful (a sit's end pose persists into the
        # following write window), so step through the shot at
        # frame rate up to the still time instead of sampling
        # t=duration/2 cold after only the t=0 pre-warm. Pose fns
        # are pure math; the stepping costs nothing measurable.
        _still_t = duration / 2.0
        _steps = max(1, int(round(_still_t * FPS)))
        for _si in range(_steps):
            _st = _si / FPS
            for n, fn in fns.items():
                if n == actor and give_fn is not None:
                    give_fn(_st)
                else:
                    fn(_st)
            if talk_nod is not None:
                talk_nod(_st)
    # ---- D2 frozen crop anchor (Phase C checkpoint) ------------------
    # ONE crop per shot, computed here from STANDING boxes and frozen
    # for every frame (directive D2: head-tracking crop OFF by
    # default; framing anchored to the scene). Standing boxes use
    # the final staging x, the standing vertical extent (ground_y /
    # char_height) and head_r — pose-independent by construction,
    # so a kneel, bend or turn can never move the crop mid-shot.
    # Box proportions match the old per-frame helpers exactly; only
    # the sampling moment changes (standing pose instead of the
    # live frame). object_insert defers to the first built frame:
    # the prop position is only known once a frame exists. KNOWN
    # LIMITATION (proven 2026-11-13): the frozen crop anchors on
    # the prop's frame-0 rest position, so a prop that travels
    # during the shot (ground -> hand, handover) leaves the crop
    # by mid-shot and the frame fills with legs. A mid-shot probe
    # frame was tried and REVERTED: frame construction is
    # stateful -- give_to latches hand starts on its first call,
    # so the probe read GRASPED at (1640, 622) while the
    # sequential loop read ATTACHED_TO_HAND at (948, 540) at the
    # same clock time, and the probe perturbs the latch. The real
    # fix is a two-pass render (build, anchor from telemetry,
    # re-crop) or a standing-hand anchor; both are RicksClips-loop
    # work, not a silent skip.
    def _standing_box(_n, _kind):
        _hr = float(getattr(chars[_n], "head_r", 133.0))
        _cx = float(staging[_n])
        _top = float(ground_ys[_n] - char_heights[_n])
        _hc = _top + _hr  # standing head centre (B §5.1 formula)
        if _kind == "full":
            return {"cx": _cx, "head_y": _top,
                    "foot_y": float(ground_ys[_n]),
                    "half_w": max(_hr + 20,
                                  0.15 * float(char_heights[_n]))}
        if _kind == "tight":
            return {"cx": _cx, "head_y": _hc - 0.7 * _hr,
                    "foot_y": _hc + 1.1 * _hr,
                    "half_w": 0.8 * _hr + 15}
        if _kind == "mcu":
            return {"cx": _cx, "head_y": _hc - _hr,
                    "foot_y": _hc + 2.8 * _hr, "half_w": _hr + 40}
        return {"cx": _cx, "head_y": _hc - _hr,
                "foot_y": _hc + 1.8 * _hr, "half_w": _hr + 30}

    _anchor_st = shot["shot_type"]
    _anchor_lead = (actor if actor in names else
                    (names[0] if names else None))
    _anchor_max_scale = None
    if not names:
        # Empty-cast shot: nothing to frame — the full frame.
        _anchor_subjects, _anchor_others = [], []
        _anchor_max_scale = 1.0
    elif _anchor_st == "close_up":
        _anchor_subjects = [_standing_box(_anchor_lead, "head")]
        _anchor_others = [_standing_box(n, "full")
                          for n in names if n != _anchor_lead]
    elif _anchor_st == "medium_close_up":
        _anchor_subjects = [_standing_box(_anchor_lead, "mcu")]
        _anchor_others = [_standing_box(n, "head")
                          for n in names if n != _anchor_lead]
    elif _anchor_st == "extreme_close_up":
        _anchor_subjects = [_standing_box(_anchor_lead, "tight")]
        _anchor_others = [_standing_box(n, "head")
                          for n in names if n != _anchor_lead]
    elif _anchor_st == "shot_reverse_shot":
        _anchor_subjects = [_standing_box(_anchor_lead, "head")]
        _anchor_others = [_standing_box(n, "head")
                          for n in names if n != _anchor_lead]
    elif _anchor_st == "over_the_shoulder":
        _anchor_subjects = [_standing_box(n, "full") for n in names]
        _anchor_others = []
        _anchor_max_scale = 1.0
    elif _anchor_st == "reaction":
        _anchor_subjects = [_standing_box(n, "head") for n in names]
        _anchor_others = []
    elif _anchor_st == "object_insert":
        # Deferred: multi-frame inserts freeze in pass 2 from
        # telemetry (see _defer_framing below); stills and
        # split-screen freeze from the first frame in the loop.
        _anchor_subjects = None
        _anchor_others = [_standing_box(n, "head") for n in names]
    else:
        _anchor_subjects = [_standing_box(n, "full") for n in names]
        _anchor_others = []
        _anchor_max_scale = 1.0

    def _freeze_anchor(_subjects, _others):
        _shot_dict = {"shot_type": shot["shot_type"],
                      "camera": {"scale": CAMERA_SHOT_SCALE.get(
                          shot["shot_type"],
                          SHOT_SCALE.get(shot["shot_type"], 1.6))},
                      "focus_target": actor}
        return anchor_focus_for_shot(_shot_dict, _subjects, _others,
                                     W, H, max_scale=_anchor_max_scale)

    _frozen = None
    _crop_notes: list = []
    if _anchor_subjects is not None:
        (_safe_shot_a, _safe_focus_a, _crop_notes,
         _frozen_crop_a) = _freeze_anchor(_anchor_subjects,
                                          _anchor_others)
        _frozen = (_safe_shot_a, _safe_focus_a, _frozen_crop_a)
    # Insert two-pass (RicksClips loop, 2026-11-13): object_insert
    # shots anchor from the prop's telemetry median, not its
    # frame-0 rest position (which framed legs while the prop
    # travelled — proven on the Zeus handover, shot 62). Pass 1
    # renders full frames + telemetry; pass 2 (after the loop)
    # freezes the crop from the median and re-frames the saved
    # frames. Stills anchor from their own mid-shot frame already;
    # split-screen keeps the frame-0 path (the composite needs
    # one frozen crop at build time). The camera stays FIXED
    # within the shot: one rect, chosen from measured data.
    _defer_framing = (
        shot["shot_type"] == "object_insert"
        and not still_only
        and _split is None
        and (_prop_machine is not None or has_prop))
    _insert_anchor: dict | None = None
    for fi in range(n_frames):
        t = (duration / 2.0) if still_only else fi / FPS
        for n, fn in fns.items():
            if n == actor and give_fn is not None:
                give_fn(t)
            else:
                fn(t)
        if talk_nod is not None:
            talk_nod(t)
        # Per frame: build the full frame (background, characters,
        # foreground, rain, prop); the split-screen second viewport
        # is built after the crop parameters resolve below.
        img, joints_now, _prop_xy, _telemetry_draws = _build_frame(
            t, fi, _split_left, paint_glow=not _defer_framing)
        for _n in names:
            _J = joints_now[_n]
            _footfall_frames[_n].append({
                "foot_l": tuple(_J["foot_l"]),
                "foot_r": tuple(_J["foot_r"]), "_t": float(t)})
        # ---- grip telemetry (sprint section 10) --------------------
        # Per-frame hand joints + prop draws in staging-plane
        # pixels, for the whole-sequence contact audit. Recorded
        # for shots with a prop machine or a legacy prop draw; the
        # crop below is framing on the image, never on these
        # coordinates, so distances stay comparable within a shot
        # and normalization by hand size handles scale across shots.
        if _prop_machine is not None or has_prop:
            _grip_telemetry.append({
                "t": round(float(_t0 + t), 4), "frame": int(fi),
                "hands": {
                    n: {"hand_l": [float(v) for v in
                                   joints_now[n]["hand_l"]],
                        "hand_r": [float(v) for v in
                                   joints_now[n]["hand_r"]],
                        "elbow_l": [float(v) for v in
                                    joints_now[n]["elbow_l"]],
                        "elbow_r": [float(v) for v in
                                    joints_now[n]["elbow_r"]],
                        # Hip: the pass-2 glow re-derivation needs
                        # the same joints the state machine read.
                        "hip": [float(v) for v in
                                joints_now[n]["hip"]],
                        "head_r": float(getattr(
                            chars[n], "head_r", 0.0)),
                        "H": float(chars[n].H)}
                    for n in names},
                "draws": _telemetry_draws})
        # ---- D2 frozen framing crop ---------------------------------
        # The crop is FRAMING (shot scale), not the camera angle: the
        # angle is the shot camera (viewpoint_for_shot) that rendered
        # the background and projected the characters. The camera is
        # FIXED within the shot (RicksClips rule, channel study R9);
        # the crop is computed ONCE per shot from STANDING boxes
        # (see the frozen anchor above) and applied identically to
        # every frame. Recomputing it per frame from live joints
        # made head framings track the head and drag the background
        # (TEST C close-up sky MAD 44.92); a crop-zoom is not a
        # camera move. A requested camera_movement is recorded on
        # the shot report with a limitation (see the return below);
        # camera_at() in camera_planner.py holds the tested
        # camera-path geometry for tooling use only.
        if _frozen is None and not _defer_framing:
            # object_insert (stills / split-screen only — the
            # multi-frame path defers to pass 2): the prop
            # position is only known once a frame is built.
            # Anchor from THIS first frame's prop position (or
            # the full-body boxes when no prop is drawn), then
            # freeze for the whole shot.
            if _prop_xy is not None:
                _px, _py = _prop_xy
                _subjects0 = [{"cx": _px, "head_y": _py - 90,
                               "foot_y": _py + 90, "half_w": 170}]
                # No "others": safe_frame's never-half-cut rule
                # for other characters would drag the crop off
                # the prop. The insert's composition rule is
                # centered_object -- the object defines the
                # frame; a holder's head at the crop edge is the
                # lesser defect versus a missing object.
                _others0 = []
            else:
                _subjects0 = [_standing_box(n, "full") for n in names]
                _others0 = []
            (_safe_shot0, _safe_focus0, _crop_notes,
             _frozen_crop0) = _freeze_anchor(_subjects0, _others0)
            _frozen = (_safe_shot0, _safe_focus0, _frozen_crop0)
        if _defer_framing:
            # Pass 1: no crop yet — the full staging frame is
            # saved and re-framed by pass 2 from telemetry.
            safe_shot = {"camera": {"scale": 1.0}}
            safe_focus = None
            _frozen_crop = None
        else:
            safe_shot, safe_focus, _frozen_crop = _frozen
        if safe_shot["camera"]["scale"] == 1.0:
            # Full-frame crop: skip the LANCZOS round-trip resize
            # (same pixels, ~0.3 s saved).
            pass
        else:
            # The frozen rect is applied as recorded — never
            # recomputed from a live focus.
            img = apply_camera_anchored(img, _frozen_crop)
        if _split is not None:
            # Split-screen (R10c): the right viewport is the same
            # moment with the right-side expressions, cropped with
            # the SAME frozen parameters (expressions never move
            # joints, so the crop is identical); the composite takes
            # the left half from the first build and the right half
            # from the second, with a centre seam.
            img2, _, _, _ = _build_frame(t, fi, _split_right)
            if safe_shot["camera"]["scale"] != 1.0:
                img2 = apply_camera_anchored(img2, _frozen_crop)
            img = _split_composite(img, img2)
        if _occluder is not None and not _defer_framing:
            # Foreground occlusion shape (layered-depth staging):
            # the closest layer, composited after the split-screen
            # composite, before subtitles. Pass 2 re-applies it
            # after the deferred crop.
            img.paste(_occluder, (0, 0), _occluder)
        # ---- subtitles last, always at fixed 64 px --------------------
        if windows and not _defer_framing:
            d = ImageDraw.Draw(img, "RGBA")
            for w in windows:
                if w["start"] <= t < w["end"] or (
                        t >= duration - 1 / FPS and w is windows[-1]):
                    draw_phrase(d, w["phrase"])
                    break
        if still_only:
            still_path = shot_dir / "still.png"
            img.save(still_path, compress_level=1)
            frames_written = []
            # The still breaks before the per-frame validation
            # below, but the shot report's joints_last_frame must
            # still carry this frame's joints (W4 tests + P9).
            prev_joints = {n: dict(J) for n, J in joints_now.items()}
            break
        path = shot_dir / f"f{fi:04d}.png"
        img.save(path, compress_level=1)
        frames_written.append(str(path))
        # ---- per-frame rig validation ---------------------------------
        for n, ch in chars.items():
            J = joints_now[n]
            violations += [f"{n}: {v}" for v in
                           check_bone_lengths(J, ch, tol=2.0)]
            for side in ("l", "r"):
                fy = J[f"foot_{side}"][1]
                if fy > ground_ys[n] + 3:
                    violations.append(
                        f"{n}: foot_{side} sinks {fy - ground_ys[n]:.1f}px")
        if prev_joints is not None:
            for n in names:
                for joint in ("head", "hip", "foot_l", "foot_r",
                              "hand_l", "hand_r"):
                    a = prev_joints[n][joint]
                    b = joints_now[n][joint]
                    jump = math.hypot(b[0] - a[0], b[1] - a[1])
                    max_jump = max(max_jump, jump)
        prev_joints = {n: dict(J) for n, J in joints_now.items()}
    if _defer_framing:
        # ---- pass 2: freeze from telemetry, re-frame the frames --
        # The frames on disk are full staging frames; the crop,
        # occluder and subtitles are image-level ops, so pass 2
        # never rebuilds a frame (frame construction is stateful
        # — see the give_to latch — and must run once, in order).
        _subjects2, _insert_anchor = _insert_anchor_subjects(
            _grip_telemetry,
            [_standing_box(n, "full") for n in names])
        (_safe_shot2, _safe_focus2, _notes2,
         _frozen_crop2) = _freeze_anchor(_subjects2, [])
        _frozen = (_safe_shot2, _safe_focus2, _frozen_crop2)
        safe_shot, safe_focus, _frozen_crop = _frozen
        _crop_notes.extend(_notes2)
        _crop_notes.append(
            "insert two-pass: crop frozen from "
            f"{_insert_anchor['source']} "
            f"(kind={_insert_anchor['kind']}, "
            f"n_draws={_insert_anchor['n_draws']})")
        for _fi2, _path2 in enumerate(frames_written):
            _t2 = _fi2 / FPS
            _img2 = Image.open(_path2)
            if safe_shot["camera"]["scale"] != 1.0:
                _img2 = apply_camera_anchored(_img2, _frozen_crop)
            if _prop_machine is not None and \
                    _fi2 < len(_grip_telemetry):
                # Deferred glow: pass 1 skipped it (see
                # paint_glow). Re-derive the exact record from
                # this frame's telemetry hands — the same joint
                # inputs _build_frame used, keyed by name and id —
                # and paint it in screen space with a capped
                # radius, before the occluder (the closest layer
                # covers the glow, as in the non-deferred order).
                _entry2 = _grip_telemetry[_fi2]
                _joints2: dict = {}
                for _n2, _h2 in _entry2["hands"].items():
                    _joints2[_n2] = _h2
                    _cid2 = _name_to_id.get(_n2)
                    if _cid2:
                        _joints2[_cid2] = _h2
                for _pid2 in _machine_pids:
                    _glow2 = _prop_machine.energy_glow_at(
                        _pid2, _t0 + _fi2 / FPS, _joints2)
                    if _glow2 is not None and _glow2["radius"] > 0:
                        paint_energy_glow(
                            _img2,
                            _screen_glow_record(
                                _glow2, _frozen_crop["crop_rect"],
                                _img2.size))
            if _occluder is not None:
                _img2.paste(_occluder, (0, 0), _occluder)
            if windows:
                _d2 = ImageDraw.Draw(_img2, "RGBA")
                for _w2 in windows:
                    if _w2["start"] <= _t2 < _w2["end"] or (
                            _t2 >= duration - 1 / FPS
                            and _w2 is windows[-1]):
                        draw_phrase(_d2, _w2["phrase"])
                        break
            _img2.save(_path2, compress_level=1)
    # Camera report (Stage 3 / F9): the executed viewpoint + the
    # movement semantics. A requested non-STATIC movement renders
    # with a FIXED camera and a recorded limitation — never a
    # silent crop-zoom presented as a camera move. A dutch angle
    # renders with eye-level geometry and a recorded limitation
    # (the frame tilt is not applied: the rotation overscan needed
    # to fill the corners would break the F2 head-size cap).
    _movement_req = normalize_movement(shot.get("camera_movement"))
    _movement_limitation = None
    if _movement_req != "STATIC":
        _movement_limitation = (
            f"camera_movement {_movement_req} requested but not "
            "executed: the camera is fixed within the shot by design "
            "(RicksClips rule, confirmed by the channel study R9); "
            "framing changes only by hard cut. Within-shot "
            "camera-position movement is intentionally not executed "
            "(camera_at() geometry in camera_planner.py is retained "
            "for tooling). No crop-zoom substitute was applied.")
    _camera_limitation = None
    if _map_frontal:
        _camera_limitation = (
            "map location: the board faces the camera (frontal "
            "eye_level viewpoint) so the map stays legible; "
            f"requested angle {_angle_requested} recorded as "
            "camera_angle_requested.")
    elif _angle == "dutch":
        _camera_limitation = (
            "dutch angle: frame tilt not applied (rotation overscan "
            "would break the F2 head-size cap); the shot renders "
            "with eye-level viewpoint geometry. Audit follow-up "
            "owns the tilt.")
    # Frozen-crop record (D2): the executed camera directive +
    # validation for this shot. The directive is STATIC_ANCHORED
    # (the renderer executes a fixed camera; a requested movement
    # is recorded above as a limitation, never executed).
    _crop_rect = None
    if _frozen is not None and float(_frozen[0]["camera"]["scale"]) > 1.0:
        _crop_rect = tuple(int(v) for v in _frozen[2]["crop_rect"])
    _directive = static_directive_for_shot(
        f"shot_{shot['index']:03d}", shot_cam, duration,
        source=f"render:static:shot_{shot['index']:03d}")
    _validation = validation_for_camera(shot_cam, crop_rect=_crop_rect)
    # Phase G footfalls: strike times per character, shot-relative.
    # Multi-frame renders only; a still (or a <3-frame shot) has no
    # motion to strike on. Times are the renderer's own joint data —
    # the same frames the viewer sees — never estimates.
    _footfalls: list[dict] = []
    if n_frames >= 3:
        for _n in names:
            _frames = _footfall_frames.get(_n) or []
            if len(_frames) >= 3:
                for _fall in footfall_times(_frames, FPS,
                                             ground_ys[_n]):
                    _footfalls.append({**_fall, "character": _n})
        _footfalls.sort(key=lambda f: (f["t"], f["character"]))
    return {
        "index": shot["index"], "scene": shot["scene"],
        "kind": shot["kind"], "speaker": shot.get("speaker"),
        "shot_type": shot["shot_type"], "duration": duration,
        "n_frames": len(frames_written),
        "applied_scale": float(safe_shot["camera"]["scale"]),
        "camera_movement": shot.get("camera_movement", "STATIC"),
        "camera_movement_requested": _movement_req,
        "camera_movement_executed": "STATIC",
        "movement_limitation": _movement_limitation,
        "camera_angle": _angle,
        "camera_angle_requested": _angle_requested,
        "camera_position": tuple(shot_cam.position),
        "camera_target": tuple(shot_cam.target),
        "camera_radius_scale": _radius_scale,
        "camera_limitation": _camera_limitation,
        "crop_anchor": _frozen[2] if _frozen is not None else None,
        "crop_frozen": _frozen is not None,
        "crop_notes": list(_crop_notes),
        "insert_two_pass": _defer_framing,
        "insert_anchor": _insert_anchor,
        "camera_directive": {
            "mode": _directive.mode.value,
            "anchor": _directive.anchor,
            "source": _directive.source,
            "start_transform": [float(v)
                                for v in _directive.start_transform],
            "end_transform": [float(v)
                              for v in _directive.end_transform],
            "duration_s": float(_directive.duration_s),
        },
        "camera_validation": {
            "position": [float(v) for v in _validation.position],
            "orientation": [float(v) for v in _validation.orientation],
            "projection_matrix": [float(v)
                                  for v in _validation.projection_matrix],
            "fov_deg": float(_validation.fov_deg),
            "crop_rect": ([int(v) for v in _validation.crop_rect]
                          if _validation.crop_rect is not None else None),
            "target_anchor": _validation.target_anchor,
            "start_transform": [float(v)
                                for v in _validation.start_transform],
            "end_transform": [float(v)
                              for v in _validation.end_transform],
            "is_static": bool(_validation.is_static()),
        },
        "frames": frames_written,
        "still": str(still_path) if still_path else None,
        "violations": violations,
        "max_jump_px_per_frame": round(max_jump, 1),
        "location_keyword": shot.get("location_keyword", "street"),
        "rainy": rainy,
        "environment_archetype": _env_archetype,
        "environment_provenance": (
            _env_pkg.get("provenance") if _env_pkg is not None else None),
        "map_report": _map_report,
        "action_event_ids": [str(e.get("action_id"))
                             for e in _shot_events],
        "action_dispatch_fallback": list(_dispatch_fallback),
        "prop_machine": _prop_machine is not None,
        "prop_diagnostics": list(_prop_diagnostics),
        "prop_rest_kinds": dict(_rest_kinds),
        "furniture_staging": dict(_furniture_staging),
        "seated_at_start": dict(_seated_at_start),
        # Last built frame's prop draws (pid, state) and joints:
        # for stills this IS the frame; for videos it is the final
        # frame. P9 consumes the event ids + diagnostics for the
        # full trace; these ground the visual state.
        "prop_draws": list(_prop_draws_last),
        "grip_telemetry": _grip_telemetry,
        "joints_last_frame": {
            n: {k: (tuple(v) if isinstance(v, (list, tuple)) else v)
                for k, v in J.items()}
            for n, J in (prev_joints or {}).items()},
        "footfalls": _footfalls,
        "footfall_frames": {n: len(f)
                            for n, f in _footfall_frames.items()},
    }


def render_storyboard_stills(package: dict, timeline: list[dict],
                             out_dir: Path,
                             shots: list[dict] | None = None) -> list[dict]:
    """One still per shot (mid-shot pose) for the storyboard preview
    step [4]. Same render path as the video, one frame per shot.
    ``shots``: the frozen plan -- see render_product_video. The
    stills must show the shots the video renders, never a divergent
    re-plan."""
    if shots is None:
        shots = plan_shots(package, timeline)
    else:
        shots = [dict(s) for s in shots]
    for i, s in enumerate(shots):
        s["index"] = i
    jobs = [{"shot": s, "package": package, "out_dir": str(out_dir),
             "still_only": True} for s in shots]
    results = [_render_shot(j) for j in jobs]
    return sorted(results, key=lambda r: r["index"])


# Audio-tail frames: the mixed audio is padded 0.5 s past the last shot
# (fade-out). The video must cover that tail too, or the fade is cut off
# at full volume — an abrupt ending. The tail holds the final frame.
TAIL_SEC = 0.5


def _base_staging(package: dict) -> dict:
    """Base character staging for camera planning: slot x positions
    (STAGING_X) on the subject plane (WORLD_Z), feet at y=0. This is
    the PLAN staging; _render_shot may adjust it per shot (OTS fit,
    boarded overrides) — the executed pose recorded per shot is the
    ground truth, and the accounting reports the delta."""
    positions = {}
    for i, char in enumerate(package.get("characters") or []):
        name = str(char.get("name") or "")
        if not name:
            continue
        x = STAGING_X[i] if i < len(STAGING_X) else 0.0
        positions[name] = (x, 0.0, WORLD_Z)
    return {"character_positions": positions}


def camera_accounting(package: dict, shots: list[dict],
                      executed: dict | None = None) -> dict:
    """P6 camera accounting for a planned shot list (W3).

    Joins every ``shot_directives`` entry to the shots it drove,
    fills frame ranges from the cumulative clock, and (when
    ``executed`` maps shot index -> _render_shot result) compares
    planned vs executed camera poses. Pure: no rendering.
    """
    return build_camera_accounting(
        package.get("shot_directives") or [], shots,
        staging=_base_staging(package), fps=FPS, executed=executed)


def render_product_video(package: dict, timeline: list[dict],
                         out_dir: Path, *, workers: int = 4,
                         shots: list[dict] | None = None) -> dict:
    """Render the full video frames from the package + timeline.
    Returns the frame list, shot reports and motion report. The MP4
    mux (frames + mixed audio) is the FFmpeg stage in product_flow.

    Frame counts come from a CUMULATIVE clock (shot i gets
    round(end*FPS) - round(start*FPS)), so the total is exactly
    round(total_duration*FPS) — per-shot rounding used to lose frames
    and fail TechnicalGate.frames_rendered_real. The audio tail is
    rendered as held copies of the final frame, so the video length
    equals the mix length and the fade-out is heard.

    ``shots``: the FROZEN shot plan (stage 7, persisted as
    timeline.json). When given, it is rendered VERBATIM -- the
    renderer must never re-plan: the internal re-plan (no scene
    graph, different package state) diverged from the frozen
    timeline by 5.2 s on Ep1, so the mux's ``-t`` cut the final
    line's audio and the verifier could not find it. When None
    (tests, standalone callers), the plan is built here.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if shots is None:
        shots = plan_shots(package, timeline)
    else:
        shots = [dict(s) for s in shots]
    for i, s in enumerate(shots):
        s["index"] = i
    # Cumulative-clock frame counts (exact total, no rounding drift).
    _cum = 0.0
    for s in shots:
        _start = round(_cum * FPS)
        _cum += float(s["duration"])
        s["n_frames"] = max(1, round(_cum * FPS) - _start)
    jobs = [{"shot": s, "package": package, "out_dir": str(out_dir)}
            for s in shots]
    results: list[dict] = []
    pool_error = None
    if workers > 1 and len(jobs) > 1:
        try:
            ctx = mp.get_context("fork")
            with ctx.Pool(processes=min(workers, len(jobs))) as pool:
                results = pool.map(_render_shot, jobs)
        except Exception as exc:  # noqa: BLE001 - fall back to sequential
            pool_error = str(exc)[:200]
            results = []
    if not results:
        results = [_render_shot(j) for j in jobs]
    results.sort(key=lambda r: r["index"])
    frames: list[str] = []
    for r in results:
        frames.extend(r["frames"])
    # Audio tail: hold the final frame so the video covers the mix.
    tail_frames = int(round(TAIL_SEC * FPS))
    if frames and tail_frames > 0:
        frames.extend([frames[-1]] * tail_frames)
    total_duration = len(frames) / FPS
    violations = [v for r in results for v in r["violations"]]
    # W3: camera accounting with executed poses (the plan-time join
    # plus the per-shot camera each _render_shot actually used).
    accounting = camera_accounting(
        package, shots,
        executed={r["index"]: r for r in results})
    motion_report = {
        "renderer": "product code renderer (renderer25d + PIL, "
                    "frame-by-frame, 24fps)",
        "width": W, "height": H, "fps": FPS,
        "total_frames": len(frames),
        "duration_sec": round(total_duration, 2),
        "shots": results,
        "camera_accounting": accounting,
        "total_violation_frames": len(violations),
        "violations": violations[:50],
        "pool_error": pool_error,
    }
    report_path = out_dir / "motion_report.json"
    report_path.write_text(json.dumps(motion_report, indent=2,
                                      ensure_ascii=False), encoding="utf-8")
    return {
        "frames": frames, "n_frames": len(frames),
        "duration_sec": round(total_duration, 2),
        "shots": results, "motion_report_path": str(report_path),
        "violations": violations, "camera_accounting": accounting,
    }
