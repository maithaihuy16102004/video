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
- camera_planner: CameraPlanner.safe_frame / apply_camera_safe
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
    EXPRESSION_NAMES, LEGACY_MOOD_TO_EXPRESSION, VIEWS,
    draw_character_v4, make_character, make_character_instance,
    resolve_view,
)
from .animation.landmarks import landmark_boxes
from .animation.scene_packages import register_scene_package
from .animation.primitives import (
    give_to, idle, kneel_pick, nod, run_to, standing, walk_to, wave,
)
from .animation.rig import check_bone_lengths, lerp, smoothstep
from .camera_planner import (
    ANGLES, CAMERA_MOVEMENT, FULL_BODY_SHOT_TYPES,
    SHOT_TYPES as CAMERA_SHOT_TYPES, SHOT_SCALE as CAMERA_SHOT_SCALE,
    CameraPlanner, normalize_movement, resolve_viewpoint_angle,
    viewpoint_for_shot,
)
from .renderer25d.camera import PerspectiveCamera
from .renderer25d.render import render_boxes_layer, render_frame
from .renderer25d.scene import Box3D, CharacterAnchor, Scene25D
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
# INK outline). Unknown kinds render as "generic". The adapter's kind
# set is asserted equal to this constant by a sync test — keep the
# name PROP_KINDS and keep this the single source of truth.
PROP_KINDS = frozenset({
    "wallet", "umbrella", "newspaper", "letter", "ticket", "cup",
    "bag", "key", "book", "flower", "pen", "generic",
})

# Generic keyword -> prop kind, for packages whose prop entries carry
# no explicit kind (name/description text only). Word-boundary
# matching, Vietnamese + English, no story values.
_PROP_KIND_KEYWORDS = (
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
    "board": ["lên xe", "bước lên", "lên"],
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


def char_metrics(cam, world_x: float, world_z: float = WORLD_Z):
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
    """
    gx, gy, _, _ = cam.project((world_x, 0.0, world_z), W, H)
    _, _, s_shot, _ = cam.project((world_x, 1.2, world_z), 1, H)
    _, _, s_base, _ = CAM.project((world_x, 1.2, world_z), 1, H)
    if s_base and s_shot:
        height_px = int(round(CHAR_H * s_shot / s_base))
    else:
        height_px = CHAR_H
    return int(round(gx)), int(round(gy)), height_px


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


def build_scene_ex(location_keyword: str, setting: str, mood: str,
                   time_of_day: str, location_data=None,
                   location_text: str = "") -> tuple:
    """Location -> (boxes, sky_top, sky_bottom, rainy, ground_color).

    Stage 3 / F5 dispatch:
    * ``location_data`` (a §15.3 trait block) -> compose_location:
      the world is composed FROM the trait data.
    * else ``location_text`` (inline text) -> compose_inline: the
      generic keyword vocabulary reads the text.
    * else the legacy keyword path (landmarks / generic street),
      behaviour unchanged except that shop signage is data-driven.
    A composed trait-block environment is registered in the
    scene-package registry under its location id.
    """
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


def plan_shots(package: dict, timeline: list[dict]) -> list[dict]:
    """Package + measured line durations -> ordered shot list.

    One action shot PER MOVEMENT CUE per scene (walk, then kneel, then
    give, then board — each with its own actor resolved from the action
    text), then one shot per spoken line. The action shots' durations
    split the scene's action_lead_sec proportionally (last shot absorbs
    rounding) — never clamped — so the video length matches the
    timeline total and TechnicalGate.timeline_sync (tolerance 0.6 s)
    passes. A line shot's duration is its voice duration + the 0.35 s
    beat, so the video length matches the timeline total (voice +
    pauses + action leads + tail) exactly.
    Shot type precedence: a shot DIRECTIVE (package["shot_directives"])
    referencing the line (or the scene, for action leads) wins over
    Gemini's shot plan, which wins over the cue-based defaults. Every
    shot carries "camera_movement" (CAMERA_MOVEMENT enum, default
    STATIC), "camera_angle" (ANGLES vocabulary or None — the renderer
    falls back to the shot type's default angle), "ots_subject" /
    "ots_counterpart" (over-the-shoulder framing info from the
    directive, else None), "v1_location" + "location_text" (the
    scene's location data, or a directive location_override's
    resolved block), "costume_overrides" ({name: garment} for the
    scene), "prop_kind" + "prop_holder" (+ "props" / "prop_holders"),
    and line shots carry the line's "expression" when present.
    The prop holder is tracked across the shot list (bend_pick -> the
    picker holds it, give -> the receiver holds it, put_away -> hidden)
    per prop id when the package declares props, else as the single
    legacy holder — so the prop is drawn at the right hand in dialogue
    shots. A scene with an explicit empty visible cast renders
    location-only (no characters, no crash). An end-card shot is
    appended when the package carries v1_end_card with a duration, and
    end_hold_sec extends the last content shot.
    """
    durations = {e["line_index"]: e["duration"] for e in timeline}
    gemini_shots = {(s.get("scene"), s.get("line_index")): s.get("shot_type")
                    for s in package.get("gemini_shots", [])}
    # Shot directives (Stage 3 / F9): indexed by (scene, line_index)
    # for line shots and by scene for action leads (line_index None).
    directives_by_line: dict = {}
    directives_by_scene: dict = {}
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
            "location_keyword": loc.get("location_keyword", "street"),
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
        scene_directive = scene_directives[0] if scene_directives \
            else None
        # shot_reverse_shot alternation within this scene: consecutive
        # SRS line shots alternate sides (srs_side 0/1).
        srs_counter = 0
        if lead > 0.3:
            movement = [c for c in cues if c in MOVEMENT_CUES]
            if not movement:
                # No visible movement, but the timeline budgets this
                # time — hold an idle beat so video == timeline.
                lead_shots = [(None, round(lead, 2))]
            else:
                weights = [ACTION_LEAD_SECONDS.get(c, 1.0)
                           for c in movement]
                total_w = sum(weights)
                lead_shots = []
                acc = 0.0
                for j, cue in enumerate(movement):
                    if j == len(movement) - 1:
                        dur = round(max(0.5, lead - acc), 2)
                    else:
                        dur = round(lead * weights[j] / total_w, 2)
                        acc += dur
                    lead_shots.append((cue, dur))
            for cue, dur in lead_shots:
                actor = action_actor(scene.get("action_text", ""),
                                     [cue] if cue else cues, char_names) \
                    if cue else None
                _transfer_holder(cue, actor)
                if scene_directive and scene_directive["shot_type"]:
                    st = scene_directive["shot_type"]
                else:
                    st = "tracking" if cue in (
                        "walk", "walk_fast", "run", "board") else \
                        "object_insert" if cue in ("give", "take") \
                        else "medium"
                movement_v = (scene_directive["camera_movement"]
                              if scene_directive else scene_movement)
                angle_v = (scene_directive.get("camera_angle")
                           if scene_directive else None) or scene_angle
                entry = {
                    "scene": number, "kind": "action", "speaker": None,
                    "text": "", "line_index": None,
                    "duration": dur,
                    "action_cues": [cue] if cue else cues,
                    "scene_cues": cues,
                    "actor": actor,
                    "action_text": scene.get("action_text", ""),
                    "visible": list(visible),
                    "shot_type": st,
                    "camera_movement": movement_v,
                    "camera_angle": angle_v,
                    "ots_subject": (scene_directive.get("subject")
                                    if scene_directive else None),
                    "ots_counterpart": (scene_directive.get("counterpart")
                                        if scene_directive else None),
                    "staging_mode": (scene_directive.get("staging_mode")
                                     if scene_directive else None),
                    "occluder_side": (scene_directive.get("occluder_side")
                                      if scene_directive else None),
                    "occluder_style": (scene_directive.get("occluder_style")
                                       if scene_directive else None),
                    "character_view": (scene_directive.get("character_view")
                                       if scene_directive else None),
                    "split_screen": (scene_directive.get("split_screen")
                                     if scene_directive else None),
                    "insert_card": (scene_directive.get("insert_card")
                                    if scene_directive else None),
                    "expression": None,
                    "costume_overrides": dict(scene_costumes),
                }
                entry.update(_prop_fields())
                if scene_directive and scene_directive.get("subject"):
                    entry["directive_subject"] = \
                        scene_directive["subject"]
                if scene_directive and scene_directive.get("shot_id"):
                    entry["directive_shot_id"] = \
                        scene_directive["shot_id"]
                _apply_location(entry, scene_directive)
                shots.append(entry)
        for line in scene.get("lines", []):
            line_no += 1
            directive = directives_by_line.get((number, line_no))
            if directive and directive["shot_type"]:
                st = directive["shot_type"]
            else:
                st = gemini_shots.get((number, line_no))
                if st not in SHOT_SCALE:
                    if line_no == 1 and number == 1:
                        st = "establishing"
                    elif any(c in cues
                             for c in ("bend_pick", "give", "take")):
                        st = "object_insert"
                    elif resolve_expression(line.get("expression"),
                                            line["text"]) != "neutral":
                        st = "close_up"
                    else:
                        st = "medium"
            movement_v = directive["camera_movement"] if directive \
                else scene_movement
            angle_v = (directive.get("camera_angle")
                       if directive else None) or scene_angle
            entry = {
                "scene": number, "kind": line.get("kind", "narration"),
                "speaker": line.get("speaker"), "text": line.get("text", ""),
                "line_index": line_no,
                # Voice + the 0.35 s beat: the shot holds the pose a
                # beat after the line ends, so the video length equals
                # the timeline total (voice + pauses + leads + tail).
                "duration": round(
                    max(durations.get(line_no, 4.0), 0.8)
                    + PAUSE_AFTER_SEC, 2),
                "voice_duration": round(
                    max(durations.get(line_no, 4.0), 0.8), 2),
                "action_cues": cues,
                "scene_cues": cues,
                "visible": list(visible),
                "shot_type": st,
                "camera_movement": movement_v,
                "camera_angle": angle_v,
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
                entry["srs_side"] = srs_counter % 2
                srs_counter += 1
            entry.update(_prop_fields())
            if directive and directive.get("subject"):
                entry["directive_subject"] = directive["subject"]
            if directive and directive.get("shot_id"):
                entry["directive_shot_id"] = directive["shot_id"]
            _apply_location(entry, directive)
            shots.append(entry)
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
                "voice_duration": 0.0,
                "action_cues": [], "scene_cues": [],
                "actor": None, "action_text": "",
                "visible": [], "shot_type": "establishing",
                "camera_movement": "STATIC",
                "camera_angle": None,
                "ots_subject": None, "ots_counterpart": None,
                "expression": None,
                "costume_overrides": {},
                "prop_holder": None, "prop_kind": None,
                "props": [], "prop_holders": {},
                "location_keyword": "street", "setting": "",
                "mood": "warm", "time_of_day": "day",
                "v1_location": None, "location_text": "",
                "end_card_text": end_card.get("text", "") or "",
                "end_card_secondary":
                    end_card.get("secondary_text")
                    or end_card.get("secondary") or "",
            })
    return shots
def _font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def _draw_prop(draw, x, y, kind="wallet", w=76, h=50):
    """Draw one prop at (x, y) in the character line language (INK
    outline, flat fill). F7: one distinct simple shape per PROP_KINDS
    entry; unknown kinds render as "generic". The wallet shape is the
    original one, unchanged, so existing wallet shots are identical.
    ``w``/``h`` are the wallet-scale footprint; other kinds scale
    from the same footprint so every prop reads at the same size."""
    kind = str(kind or "wallet").strip().lower()
    if kind not in PROP_KINDS:
        kind = "generic"
    ink = INK_RGB
    if kind == "wallet":
        draw.rounded_rectangle(
            [x - w / 2, y - h / 2, x + w / 2, y + h / 2],
            radius=9, fill=PROP_FILL, outline=ink, width=3)
        draw.line([(x - w / 2 + 8, y), (x + w / 2 - 8, y)],
                  fill=ink, width=3)
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
        # A pen held diagonally: barrel + nib + clip.
        draw.line([(x - w / 2 + 6, y + h / 3), (x + w / 2 - 14, y - h / 3)],
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
    shot_cam = viewpoint_for_shot(
        shot["shot_type"], _angle,
        subject_pos=(_target_x, 1.2, _target_z),
        counterpart_x=_counterpart_x, srs_side=shot.get("srs_side", 0))
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
                shot_cam, _lx, world_zs[_ots_listener])
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
    metrics = {n: char_metrics(shot_cam, world_xs[n], world_zs[n])
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
    boxes, sky_top, sky_bottom, rainy, ground_color = build_scene_ex(
        shot.get("location_keyword", "street"), shot.get("setting", ""),
        shot.get("mood", "warm"), shot.get("time_of_day", "day"),
        location_data=shot.get("v1_location"),
        location_text=shot.get("location_text", ""))
    # F6: the bus shows when EITHER cue list names it -- and "board"
    # implies a bus even when the cues forget it, because the board
    # shot must show the bus being boarded. (The old condition used
    # `scene_cues or action_cues`, so a "bus"/"board" in action_cues
    # was ignored whenever scene_cues was non-empty.)
    _cues_all = list(shot.get("scene_cues") or []) + \
        list(shot.get("action_cues") or [])
    _has_bus = "bus" in _cues_all or "board" in _cues_all
    if _has_bus:
        # The bus, arriving from the right: body + lit windows + door
        # at BUS_DOOR_X. A plain box would read as a building; the
        # windows + wheels + door make it a bus -- and the F6 2D
        # overlay (_draw_bus_details, on the static background)
        # adds the wheels, lights, sign and stripe the 3D boxes
        # cannot show (the kerb occludes the 3D wheels).
        boxes += [
            Box3D(center=BUS_BODY_CENTER, size=BUS_BODY_SIZE,
                  color=(40, 90, 130), name="bus_body"),
            Box3D(center=(2.0, 1.4, -2.95), size=(0.6, 0.5, 0.08),
                  color=(255, 220, 130), name="bus_window_1"),
            Box3D(center=(2.8, 1.4, -2.95), size=(0.6, 0.5, 0.08),
                  color=(255, 220, 130), name="bus_window_2"),
            Box3D(center=(3.4, 1.4, -2.95), size=(0.6, 0.5, 0.08),
                  color=(255, 220, 130), name="bus_window_3"),
            Box3D(center=(BUS_DOOR_X, 0.9, -2.95), size=(0.5, 1.4, 0.08),
                  color=(20, 40, 60), name="bus_door"),
            Box3D(center=(BUS_WHEEL_X[0], 0.15, -2.95),
                  size=(0.4, 0.3, 0.1),
                  color=(20, 20, 24), name="bus_wheel_1"),
            Box3D(center=(BUS_WHEEL_X[1], 0.15, -2.95),
                  size=(0.4, 0.3, 0.1),
                  color=(20, 20, 24), name="bus_wheel_2"),
        ]
    # ---- static background, rendered ONCE per shot --------------------
    # render_frame() runs a full-frame GaussianBlur contact shadow for
    # EVERY box (~30) and character on EVERY call — ~10-15 s per frame
    # at 1920x1080. The camera is static within a shot and the boxes
    # never move, so the background (sky, ground, boxes, box shadows)
    # is rendered once and reused; only the characters, rain, prop and
    # subtitles change per frame. The lamp glow is baked into the
    # background too (static). Character contact shadows use a small
    # pre-blurred tile pasted at the feet each frame (the reference
    # has no blob shadow at all, so a soft ellipse is more than
    # enough). This is a renderer-side optimisation only — the frames
    # are pixel-identical in content to the per-frame render.
    bg_scene = Scene25D(boxes=boxes, characters=[], camera=shot_cam,
                        sky_top=sky_top, sky_bottom=sky_bottom,
                        ground_color=ground_color,
                        ground_extent=30.0)
    bg_img = render_frame(bg_scene, W, H)
    if rainy:
        _lx, _ly, _, _ = shot_cam.project((4.0, 0.0, -1.5), W, H)
        _hx2, _hy2, _, _ = shot_cam.project((4.0, 3.3, -1.5), W, H)
        _lamp_glow(bg_img, (int(_lx), int(_ly)), (int(_hx2), int(_hy2)))
    if _has_bus:
        # F6: bus details on the static background, once per shot,
        # projected with the shot camera so they track the bus at
        # any viewpoint.
        _draw_bus_details(bg_img, shot_cam)
    # Foreground occlusion layer (Stage 3 / Fix 3): boxes standing
    # in front of the character plane, rendered boxes-only with the
    # same projection/shading, composited AFTER the characters each
    # frame (before rain/prop/subtitles) so a foreground crate
    # genuinely occludes the feet behind it. The background keeps
    # the full scene (so foreground boxes' contact shadows stay
    # under the characters, where they belong); the layer redraws
    # the same pixels over the characters.
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
    shadow_tile = Image.new("RGBA", (320, 48), (0, 0, 0, 0))
    _td = ImageDraw.Draw(shadow_tile)
    _td.ellipse([20, 8, 300, 40], fill=(0, 0, 0, 110))
    shadow_tile = shadow_tile.filter(ImageFilter.GaussianBlur(6))
    cues = list(shot.get("action_cues") or [])
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
    for n, ch in chars.items():
        facing = 1
        if n == actor and other is not None:
            facing = 1 if staging[other] > staging[n] else -1
        elif n != actor and actor is not None:
            facing = 1 if staging[actor] > staging[n] else -1
        standing(ch, staging[n], ground_ys[n], facing=facing)
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

    def _build_frame(t, fi, expr_overrides):
        """One full frame: static background + contact shadows +
        rig characters + foreground boxes + rain/puddle + prop.
        Pure given the poses (the pose closures run once per frame
        in the loop, before the build): calling it twice with
        different expression overrides yields the two split-screen
        viewports of the SAME moment. Returns (image, joints,
        prop_xy)."""
        img = bg_img.copy()
        for n in names:
            fx = int(chars[n].pose["root_x"])
            img.paste(shadow_tile, (fx - 160, ground_ys[n] - 24),
                      shadow_tile)
        d = ImageDraw.Draw(img, "RGBA")
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
            if expr is None:
                expr = resolve_expression(shot.get("expression"),
                                          shot.get("text", "")) \
                    if n == shot.get("speaker") else "neutral"
            # F9: the over-the-shoulder foreground listener is drawn
            # from behind (back of the head, no face — the art system
            # renders view "back" with hair, never a face); everyone
            # else keeps the pose-derived view (shot-level default).
            _view = "back" if n == _ots_listener \
                else resolve_view(ch, default=_shot_view)
            joints_now[n] = draw_character_v4(
                d, ch, expression=expr, view=_view)
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
        if has_prop and joints_now:
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
        # prop position for the camera (object_insert frames the prop).
        _prop_xy = (wx, wy) if wx is not None else None
        return img, joints_now, _prop_xy

    violations: list[str] = []
    max_jump = 0.0
    prev_joints = None
    foot_slide = 0.0
    frames_written = []
    still_path = None
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
        img, joints_now, _prop_xy = _build_frame(t, fi, _split_left)
        # ---- 2D camera crop (safe_frame) ------------------------------
        # The subject box MUST be the DRAWN extent, not the joint:
        # J["head"] is the head-joint (centre of the head circle) but
        # the engine's validate_framing treats head_y as the TOP of
        # the subject, and the drawn head extends head_r (~133 px)
        # above the joint. Passing the joint made safe_frame think
        # the subject fit at 1.6x/2.6x/3.4x when the real head was
        # cut at the top of the frame (v9: bend_pick, reaction,
        # give/take and board shots all cut heads). Same for half_w:
        # the big round head is wider than the body when the arms
        # hang at the sides.
        #
        # The box ALSO depends on the shot type — a close_up frames
        # the FACE, an object_insert frames the PROP, a medium frames
        # the whole body. Passing the full body as the subject for
        # every type forced safe_frame to 1.0x everywhere (v10: all
        # 21 shots wide, no shot language at all). So:
        #   close_up  -> subject = speaker's head (+neck)
        #   reaction  -> subjects = every visible head
        #   object_insert -> subject = the prop box
        #   medium / tracking / establishing -> full bodies
        # Other characters are passed as `others` for close_up /
        # insert: safe_frame keeps them fully in or fully out.
        def _full_box(n):
            # F2: the box is the STANDING extent, anchored at the
            # ground -- not the current pose's head top. A kneel or
            # crouch shrinks the pose box, and safe_frame climbs the
            # scale ladder mid-shot (1.0x -> 1.6x as the character
            # kneels), inflating the head to 358 px = 33% of the
            # frame. The standing box is pose-independent, so the
            # scale stays constant across the shot. The anchor is
            # this character's shot-camera ground line and height
            # (char_metrics): at the default camera they are exactly
            # GROUND_Y / CHAR_H, i.e. 72.5% of the frame height
            # (under the 75% cap) and the head is 24.6% (under 26%).
            # The horizontal extent still follows the pose (hand /
            # foot spread), so a wide stance still frames correctly.
            J = joints_now[n]
            _hr = float(getattr(chars[n], "head_r", 133.0))
            return {
                "cx": J["head"][0],
                "head_y": ground_ys[n] - char_heights[n],
                "foot_y": ground_ys[n],
                "half_w": max(
                    abs(J["hand_l"][0] - J["hand_r"][0]) / 2 + 40,
                    _hr + 20,
                    max(abs(J["foot_l"][0] - J["head"][0]),
                        abs(J["foot_r"][0] - J["head"][0])) + 20),
            }

        def _head_box(n):
            J = joints_now[n]
            _hr = float(getattr(chars[n], "head_r", 133.0))
            return {
                "cx": J["head"][0],
                "head_y": J["head"][1] - _hr,
                "foot_y": J["head"][1] + 1.8 * _hr,
                "half_w": _hr + 30,
            }

        def _tight_head_box(n):
            # extreme_close_up: a tighter head/detail box than the
            # close_up head box (the face fills the frame).
            J = joints_now[n]
            _hr = float(getattr(chars[n], "head_r", 133.0))
            return {
                "cx": J["head"][0],
                "head_y": J["head"][1] - 0.7 * _hr,
                "foot_y": J["head"][1] + 1.1 * _hr,
                "half_w": 0.8 * _hr + 15,
            }

        def _mcu_box(n):
            # medium_close_up (channel study R1): head + upper torso
            # (chest-up), anchored at the head joint with fixed
            # head-radius multiples, so the box SIZE is
            # pose-independent and the applied scale stays constant
            # within the shot (the standing-box principle, applied
            # to the chest-up framing).
            J = joints_now[n]
            _hr = float(getattr(chars[n], "head_r", 133.0))
            return {
                "cx": J["head"][0],
                "head_y": J["head"][1] - _hr,
                "foot_y": J["head"][1] + 2.8 * _hr,
                "half_w": _hr + 40,
            }

        _st = shot["shot_type"]
        _full = {n: _full_box(n) for n in names}
        # F2: full-body shot types never zoom above 1.0x (belt and
        # braces with the standing-extent box above: even if the box
        # computation changes later, a full body can never be
        # inflated mid-shot). Head/prop framings keep their scales:
        # the zoom is the point of a close_up / reaction / insert.
        _max_scale = None
        _lead = actor if actor in joints_now else (names[0] if names
                                                   else None)
        if not names:
            # Empty-cast shot: nothing to frame — the full frame.
            subjects, others = [], []
            _max_scale = 1.0
        elif _st == "close_up":
            subjects = [_head_box(_lead)]
            others = [_full[n] for n in names if n != _lead]
        elif _st == "medium_close_up":
            # Chest-up on the lead; other heads must be fully in or
            # fully out (never half-cut at the crop edge).
            subjects = [_mcu_box(_lead)]
            others = [_head_box(n) for n in names if n != _lead]
        elif _st == "extreme_close_up":
            subjects = [_tight_head_box(_lead)]
            others = [_head_box(n) for n in names if n != _lead]
        elif _st == "shot_reverse_shot":
            # Reverse angle: a close_up on the current speaker. The
            # alternation between speakers is REAL viewpoint
            # geometry: plan_shots records srs_side and the shot
            # camera sits on alternating sides of the axis (see
            # viewpoint_for_shot), so the eye-line match comes from
            # the camera, not from a crop offset.
            subjects = [_head_box(_lead)]
            others = [_head_box(n) for n in names if n != _lead]
        elif _st == "over_the_shoulder":
            # Two-subject framing from behind the listener: both
            # characters framed, focus biased to the speaker. The
            # listener is staged closer to the shot camera (see
            # world_zs above) and drawn from behind (view "back"),
            # so perspective scale + the back of the head make them
            # read as a foreground shoulder. No blur/depth treatment
            # is applied to the foreground shoulder — the 2D crop
            # renderer cannot do it honestly, and a fake blur would
            # be a false effect (Stage 3 limitation, reported, not
            # faked).
            subjects = [_full[n] for n in names]
            others = []
            _max_scale = 1.0
        elif _st == "reaction":
            subjects = [_head_box(n) for n in names]
            others = []
        elif _st == "object_insert" and _prop_xy is not None:
            _px, _py = _prop_xy
            subjects = [{"cx": _px, "head_y": _py - 90,
                         "foot_y": _py + 90, "half_w": 170}]
            # Others are HEAD boxes only, not full bodies: the hands
            # holding the prop BELONG in the insert (that is the
            # shot), but a head must never be half-cut at its edge.
            # Full-body others made safe_frame zoom out to 1.0x every
            # time (the reaching hands overlap any tight crop).
            others = [_head_box(n) for n in names]
        else:
            subjects = [_full[n] for n in names]
            others = []
            _max_scale = 1.0
        focus = None
        if _st == "object_insert" and _prop_xy is not None:
            focus = _prop_xy
        elif actor is not None and actor in joints_now:
            focus = (joints_now[actor]["head"][0],
                     joints_now[actor]["head"][1])
        shot_dict = {"shot_type": shot["shot_type"],
                     "camera": {"scale": CAMERA_SHOT_SCALE.get(
                         shot["shot_type"],
                         SHOT_SCALE.get(shot["shot_type"], 1.6))},
                     "focus_target": actor}
        safe_shot, safe_focus, notes = CameraPlanner.safe_frame(
            shot_dict, focus, subjects, others, max_scale=_max_scale)
        # ---- 2D framing crop (safe_frame) ------------------------------
        # The crop is FRAMING (shot scale), not the camera angle: the
        # angle is the shot camera (viewpoint_for_shot) that rendered
        # the background and projected the characters. The camera is
        # FIXED within the shot (RicksClips rule, channel study R9);
        # no time-varying crop is applied — a crop-zoom is not a
        # camera move. A requested camera_movement is recorded on
        # the shot report with a limitation (see the return below);
        # camera_at() in camera_planner.py holds the tested
        # camera-path geometry for tooling use only.
        if safe_shot["camera"]["scale"] == 1.0:
            # Full-frame crop: skip the LANCZOS round-trip resize
            # (same pixels, ~0.3 s saved).
            pass
        else:
            # Use the safe focus as-is. safe_frame already centres
            # the crop on the subjects with headroom AND keeps every
            # `other` fully in or fully out.
            img = CameraPlanner.apply_camera(img, safe_shot, safe_focus)
        if _split is not None:
            # Split-screen (R10c): the right viewport is the same
            # moment with the right-side expressions, cropped with
            # the SAME parameters (expressions never move joints, so
            # the crop is identical); the composite takes the left
            # half from the first build and the right half from the
            # second, with a centre seam.
            img2, _, _ = _build_frame(t, fi, _split_right)
            if safe_shot["camera"]["scale"] != 1.0:
                img2 = CameraPlanner.apply_camera(img2, safe_shot,
                                                  safe_focus)
            img = _split_composite(img, img2)
        if _occluder is not None:
            # Foreground occlusion shape (layered-depth staging):
            # the closest layer, composited after the split-screen
            # composite, before subtitles.
            img.paste(_occluder, (0, 0), _occluder)
        # ---- subtitles last, always at fixed 64 px --------------------
        if windows:
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
    if _angle == "dutch":
        _camera_limitation = (
            "dutch angle: frame tilt not applied (rotation overscan "
            "would break the F2 head-size cap); the shot renders "
            "with eye-level viewpoint geometry. Audit follow-up "
            "owns the tilt.")
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
        "camera_position": tuple(shot_cam.position),
        "camera_target": tuple(shot_cam.target),
        "camera_limitation": _camera_limitation,
        "frames": frames_written,
        "still": str(still_path) if still_path else None,
        "violations": violations,
        "max_jump_px_per_frame": round(max_jump, 1),
        "location_keyword": shot.get("location_keyword", "street"),
        "rainy": rainy,
    }


def render_storyboard_stills(package: dict, timeline: list[dict],
                             out_dir: Path) -> list[dict]:
    """One still per shot (mid-shot pose) for the storyboard preview
    step [4]. Same render path as the video, one frame per shot."""
    shots = plan_shots(package, timeline)
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


def render_product_video(package: dict, timeline: list[dict],
                         out_dir: Path, *, workers: int = 4) -> dict:
    """Render the full video frames from the package + timeline.
    Returns the frame list, shot reports and motion report. The MP4
    mux (frames + mixed audio) is the FFmpeg stage in product_flow.

    Frame counts come from a CUMULATIVE clock (shot i gets
    round(end*FPS) - round(start*FPS)), so the total is exactly
    round(total_duration*FPS) — per-shot rounding used to lose frames
    and fail TechnicalGate.frames_rendered_real. The audio tail is
    rendered as held copies of the final frame, so the video length
    equals the mix length and the fade-out is heard."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = plan_shots(package, timeline)
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
    motion_report = {
        "renderer": "product code renderer (renderer25d + PIL, "
                    "frame-by-frame, 24fps)",
        "width": W, "height": H, "fps": FPS,
        "total_frames": len(frames),
        "duration_sec": round(total_duration, 2),
        "shots": results,
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
        "violations": violations,
    }
