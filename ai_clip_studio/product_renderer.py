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
import zlib
import multiprocessing as mp
import random
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .animation.character_art import (
    EXPRESSION_NAMES, EXPRESSIONS, LEGACY_MOOD_TO_EXPRESSION, TEMPLATES,
    VIEWS,
    draw_character_v4, draw_grip_fingers, make_character,
    make_character_instance, resolve_view,
)
from .animation.landmarks import landmark_boxes
from .animation.locomotion import footfall_times
from .animation.scene_packages import register_scene_package
from .animation.primitives import (
    HAMMER_CYCLE_HOLD_U, HAMMER_CYCLE_SEC, HAMMER_CYCLE_STRIKE_U,
    PRIMITIVES, bend_pick, breathe, carry_bag, close_wallet, cover_face,
    crouch, give_to, hammer_cycles, hammer_grip_angle,
    hammer_head_position, hammer_strike, hammer_strike_times,
    hand_over, head_tilt, hold_pen, idle, insert_key,
    kneel_pick, look_at_point,
    nod, open_wallet, pen_tip_position, pick_up, place_on_surface,
    point_at, present_prop,
    put_away,
    raise_hand, reach_to,
    react_event, receive_prop, run_to, shield, shrug, sign_document,
    sit_at_desk, sit_down,
    stand_from_chair, stand_up, standing, turn_to, walk_mud, walk_to, wave,
    write_on_paper,
)
from .animation.rig import (
    EAR_SHAPES, FACE_MARKING_STYLES, HORN_SHAPES, TAIL_SHAPES,
    check_bone_lengths, lerp, smoothstep,
)
from .expression_library import (
    blend as blend_expressions_lib,
    blink_envelope, blink_times_for, gaze_for_target, gaze_wander,
    interpret as interpret_expression,
    interpret_params as interpret_expression_params,
    speech_mouth_envelope,
)
from .camera_planner import (
    ANGLES, CAMERA_MOVEMENT, FULL_BODY_SHOT_TYPES,
    SHOT_TYPES as CAMERA_SHOT_TYPES, SHOT_SCALE as CAMERA_SHOT_SCALE,
    CameraPlanner, anchor_focus_for_shot, apply_camera_anchored,
    apply_gain, apply_micro_dolly, dolly_rect,
    measured_exposure_gain, normalize_movement,
    build_camera_accounting,
    resolve_viewpoint_angle, static_directive_for_shot,
    validation_for_camera, viewpoint_for_shot,
    ESTABLISHING_MAX_ELEV_DEG, elevation_for_angle,
)
from .renderer25d.camera import PerspectiveCamera
from .renderer25d.render import render_boxes_layer, render_frame
from .renderer25d.scene import Box3D, CharacterAnchor, Scene25D
from .lighting import (MATERIAL_CATALOG, cast_shadow_spec, light_for,
                       paint_energy_glow,
                       paint_energy_glow_excluding, paint_light_pool,
                       rig_for, shadow_ellipse_spec)
from .effects import (
    BURST_TYPES, REACTION_GLOW_COLOR, REACTION_GLOW_RADIUS_PX,
    REACTION_PAINT_FLOOR, burst_color_radius, burst_envelope,
    burst_record, crack_lines, names_set_piece, strike_reaction)
from .environment_v2 import (
    _DEBRIS_LIFETIME, _ENCLOSED_ARCHETYPES, _FLICKER_KINDS,
    _SMOKE_KINDS, _SPARK_BURST_LIFETIME,
    _draw_flames, _draw_smoke, _draw_sparks,
    build_environment,
    clear_foreground_from_subjects,
    fit_foreground_to_frustum,
    render_environment, select_archetype, to_box_dicts,
)
from .map_renderer import MapSpecError, render_map
from .prop_system import (
    PropStateMachine, SemanticPropTracker, geometry_for_prop,
    geometry_footprint)
from .semantic_contracts import PropLocation
from .planner_fallback import ACTION_LEAD_SECONDS
from .subtitles import (
    caption_metrics, draw_phrase, phrase_windows, split_subtitle,
)

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
    "reaction": 2.6, "object_insert": 5.0, "tracking": 1.6,
    "medium_close_up": 1.6, "graphic_insert": 1.0,
}

# Map-shot subtitle lift (RicksClips loop round 1, D4): map_renderer
# burns the CC BY attribution at H-104 (22 px font) and the boundary
# note at H-40, while subtitles end at H-40 by default -- so they
# cover both. Map shots lift the subtitle block 80 px: its bottom
# clears the attribution band by 16 px.
_MAP_SUBTITLE_LIFT_PX = 80.0

# Anchor tiers (RicksClips loop round 1, D1): a head-only anchor
# crops hand actions out of the frame (the Ep1 opening: a 2.6x
# close_up showed only a giant head while the wallet action played
# below the crop). Shots staging hand-level interactions anchor
# head -> waist; shots staging ground-level actions anchor the full
# body. The safe_frame ladder steps the scale down until the anchor
# fits; the shot TYPE is unchanged. Compiled verbs decide; legacy
# cue names are the fallback when the shot has no compiled events.
_ANCHOR_HAND_VERBS = frozenset((
    "TAKE_OUT", "TAKE_FROM_POCKET", "TAKE", "OPEN", "CLOSE",
    "OPEN_WALLET", "CLOSE_WALLET", "GIVE", "HAND_OVER",
    "RECEIVE_PROP", "HOLD", "HOLD_PEN", "CARRY", "PUT_AWAY",
    "RELEASE", "RELEASE_PROP", "PLACE_ON_SURFACE", "HAMMER_STRIKE",
    "POINT", "RAISE_HAND", "SIGN", "WRITE", "REACH", "GRAB",
    "PUSH", "PULL", "WAVE"))
_ANCHOR_GROUND_VERBS = frozenset((
    "PICK_FROM_GROUND", "BEND_PICK", "PICK_UP", "KNEEL_PICK",
    "KNEEL", "CROUCH", "DROP"))
_ANCHOR_HAND_CUES = frozenset((
    "give", "take", "put_away", "hold", "carry", "open", "close",
    "receive", "hand_over", "point", "hammer", "write", "sign",
    "raise_hand", "wave", "reach", "grab", "push", "pull"))
_ANCHOR_GROUND_CUES = frozenset((
    "bend_pick", "pick_up", "kneel", "kneel_pick", "crouch",
    "drop"))

# Locomotion widening (RicksClips loop round 1, ECU-exit): a moving
# subject + a frozen head-tight crop walks out of the frame (Zeus
# shot 51: extreme_close_up on a walk, the last ~1.5 s empty).
# Locomotion shots in head-anchored framings widen to the full body
# at full frame; the shot TYPE is unchanged. Same authority rule
# as the anchor tiers: compiled verbs decide, cues are the
# fallback when the shot has no compiled events.
_LOCOMOTION_VERBS = frozenset((
    "WALK", "WALK_MUD", "WALK_FAST", "RUN", "MARCH", "BOARD",
    "CLIMB"))
_LOCOMOTION_CUES = frozenset((
    "walk", "walk_fast", "run", "march", "board", "climb"))
_LOCOMOTION_WIDENED_TYPES = frozenset((
    "extreme_close_up", "close_up", "reaction",
    "shot_reverse_shot", "medium_close_up"))

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
    "lock",
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
    # Lock AFTER key: first-match wins, so "chìa khóa" (a key)
    # must claim before bare "khóa" (a lock) is ever checked.
    (("ổ khóa", "ổ khoá", "padlock", "lock", "khóa"), "lock"),
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


def _map_rect_point(pt, rect, out_size):
    """Map a point from a source rect into the rect's output frame size.

    Used to report character boxes in FINAL frame coordinates after the
    frozen crop and the micro-dolly, using the same rects the renderer
    applied (never a re-derivation).
    """
    x0, y0, x1, y1 = rect
    sx = out_size[0] / max(1e-6, float(x1) - float(x0))
    sy = out_size[1] / max(1e-6, float(y1) - float(y0))
    return ((float(pt[0]) - float(x0)) * sx,
            (float(pt[1]) - float(y0)) * sy)


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


# Round-7 bystander clearance (R6-D1): hand-action sweep separation.
# A character performing a hand action sweeps their hands plus any
# held prop through a screen-space disc around the shoulder. When a
# bystander stands inside that disc, the prop draws over their face:
# in the R6 draft the hammer parked on the watcher's face for 1.7 s
# because the striker stood behind the bystander and the presenting
# hand rose through the bystander's head. The clearance pass in
# _render_shot pushes non-participant, non-anchored bystanders
# laterally until their head disc clears every acting character's
# sweep disc, or the frame margin blocks the push (recorded, never
# silent). Co-participants of the action (a handover's receiver, a
# strike's target) are exempt: the action needs them close.
_HAND_SWEEP_PRIMITIVES = frozenset({
    "hammer_strike", "present_prop", "reach_to", "give_to",
    "hand_over", "receive_prop", "point_at", "raise_hand",
    "bend_pick", "kneel_pick", "pick_up", "put_away",
})
# Sweep disc: centred on the shoulder, radius = hand reach + handle
# + head size, all in fractions of the actor's drawn height H.
_SWEEP_CENTRE_FRAC = 0.72
_SWEEP_RADIUS_FRAC = 0.60
# Head disc: the head occupies the top 0.34 of H (head_ratio lock).
_HEAD_CENTRE_FRAC = 0.83
_HEAD_RADIUS_FRAC = 0.17
# Extra clearance between a sweep disc and a head disc, in H.
_SWEEP_MARGIN_FRAC = 0.05


def _sweep_disc(gx: float, gy: float, gh: float):
    """Screen-space hand-sweep disc for a character at (gx, gy, gh)."""
    return (gx, gy - _SWEEP_CENTRE_FRAC * gh, _SWEEP_RADIUS_FRAC * gh)


def _head_disc(gx: float, gy: float, gh: float):
    """Screen-space head disc for a character at (gx, gy, gh)."""
    return (gx, gy - _HEAD_CENTRE_FRAC * gh, _HEAD_RADIUS_FRAC * gh)


def _discs_clear(a, b, margin: float = 0.0) -> bool:
    """True when two (cx, cy, r) discs are separated by >= margin."""
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy >= (a[2] + b[2] + margin) ** 2


def _prop_intrudes_head(point, head, head_r: float, H: float) -> bool:
    """True when a held prop's drawn ``point`` lands inside a head
    disc (centre ``head``, radius ``head_r``) plus a 0.05H margin.
    The head-intrusion audit's predicate, factored out so the
    threshold is pinned by unit tests."""
    if head_r <= 0:
        return False
    return (math.hypot(point[0] - head[0], point[1] - head[1])
            < head_r + 0.05 * float(H))


def _clear_head(prop_xy, head_xy, head_r: float, H: float,
                facing: int = 1):
    """Push a drawn prop point out of a head disc.

    Round 17 (R16-O1): the correction for the head-intrusion
    audit's predicate (_prop_intrudes_head). A point inside the
    disc + 0.05H margin moves radially outward to the disc edge
    + margin + 8px; a point already clear is untouched. A point
    exactly at the head centre pushes along ``facing``. The push
    is continuous in the prop position, so no pops.
    """
    if head_r <= 0:
        return prop_xy
    _dx, _dy = prop_xy[0] - head_xy[0], prop_xy[1] - head_xy[1]
    _dist = math.hypot(_dx, _dy)
    _target = head_r + 0.05 * float(H) + 8.0
    if _dist >= _target:
        return prop_xy
    if _dist <= 0.0:
        return (head_xy[0] + facing * _target, head_xy[1])
    _s = _target / _dist
    return (head_xy[0] + _dx * _s, head_xy[1] + _dy * _s)


def _clear_rect_radial(point, rect, margin: float = 6.0):
    """Push a drawn prop point radially out of a rect.

    Round 20 (R19-D2): the _clear_head rule generalized to
    rects. ``rect`` is (left, top, right, bottom). A point
    inside the margin-expanded rect moves along the ray from
    the rect centre to the rect boundary + margin; a point
    already clear is untouched. Continuous in the prop
    position except exactly at the centre (falls back to
    straight down), so no pops.
    """
    x, y = float(point[0]), float(point[1])
    left, top, right, bottom = (float(v) for v in rect)
    if not (left - margin <= x <= right + margin
            and top - margin <= y <= bottom + margin):
        return (x, y)
    cx, cy = (left + right) / 2.0, (top + bottom) / 2.0
    hw, hh = (right - left) / 2.0, (bottom - top) / 2.0
    dx, dy = x - cx, y - cy
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        dx, dy, dist = 0.0, 1.0, 1.0
    ux, uy = dx / dist, dy / dist
    sx = hw / abs(ux) if abs(ux) > 1e-9 else float("inf")
    sy = hh / abs(uy) if abs(uy) > 1e-9 else float("inf")
    s = min(sx, sy) + margin
    return (cx + ux * s, cy + uy * s)


def _clear_worn_bags(point, rects, margin: float = 6.0):
    """Push a held-prop draw point out of every worn-bag
    rect, radially, in order (bag rects rarely overlap)."""
    x, y = float(point[0]), float(point[1])
    for rect in rects:
        x, y = _clear_rect_radial((x, y), rect, margin)
    return (x, y)


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
                      counterpart_x, srs_side, positions, scales,
                      top_fracs=None, elevation_deg=None):
    """Camera radius multiplier so subjects fit the frame top.

    ``elevation_deg`` (round 11): an explicit executed elevation
    passed through to viewpoint_for_shot, so the fit measures the
    camera that will actually render (a capped establishing
    elevation fits differently from the steep requested one).
    None (default) uses the angle table, exactly as before.

    ``positions``/``scales`` are parallel lists of (world_x, world_z)
    and per-character body scales for the shot's visible characters.
    ``top_fracs`` (optional, parallel) carries each character's top
    accessory extent as a fraction of the head radius above the head
    circle (see ``_top_accessory_frac``): the fit protects the drawn
    SILHOUETTE top, not just the head circle -- without it Linh's
    bun clipped above the staging canvas in shot #3 (head circle
    top at 27 px cleared the 12 px margin while the bun top sat at
    -8 px). ``None`` (default) fits the head circle exactly as
    before. Returns 1.0 when every silhouette top already clears
    the top margin. Otherwise iterates: drawn height is ~1/radius,
    so each pass multiplies the radius by the worst overflow ratio;
    the ground line shifts with radius too, so up to eight passes
    are allowed (a 1.8x subject at the standard radius converges
    in six). The radius is capped at 3.0x — beyond that the shot
    is reported with the residual overflow, never silently
    re-scaled.

    Round 7: the fit is no longer gated on scaled-up subjects. An
    unscaled subject at a close camera overflows the top exactly the
    same way (R6 shot #5: Linh's head cut for the whole shot), and
    the gate left every unscaled shot unprotected. The first pass
    still returns 1.0 immediately when nothing overflows, so fitting
    shots are untouched.
    """
    if not positions:
        return 1.0
    fracs = list(top_fracs) if top_fracs is not None \
        else [0.0] * len(positions)
    radius_scale = 1.0
    for _ in range(8):
        cam = viewpoint_for_shot(
            shot_type, angle,
            subject_pos=(target_x, 1.2, target_z),
            counterpart_x=counterpart_x, srs_side=srs_side,
            radius_scale=radius_scale, elevation_deg=elevation_deg)
        worst = 1.0
        for (x, z), s, frac in zip(positions, scales, fracs):
            _gx, gy, h = char_metrics(cam, x, z, base_scale=s)
            # Silhouette height: the body plus the accessories
            # above the head circle (head_r = 0.17 * h).
            sil_h = h * (1.0 + 0.17 * float(frac))
            if gy - sil_h < _FIT_TOP_MARGIN_PX:
                worst = max(
                    worst,
                    sil_h / max(1.0, gy - _FIT_TOP_MARGIN_PX))
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
    # R17-D13: the template heights (male 560 / female 540 /
    # child 400 / elderly 520) never reached the render -- the
    # uniform perspective height replaced them, so every adult
    # rendered at 783px. The rendered height composes the
    # perspective height with the template ratio and the
    # script-derived stature (BODY_TYPE "small" -> 0.85). The
    # head ratio stays 0.34: the head scales WITH the height.
    # Locked registry instances above keep their locked heights.
    _tmpl_h = TEMPLATES[template]["height"] / TEMPLATES["male"]["height"]
    try:
        _stature = float(char.get("stature") or 1.0)
    except (TypeError, ValueError):
        _stature = 1.0
    height = int(round(height * _tmpl_h * _stature))
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
    if char.get("hair_style") in ("short", "long", "tuft", "side_part",
                                     "tied"):
        kwargs["hair_style"] = char["hair_style"]
    if char.get("hat") in ("bowler", "cap", "straw", "none"):
        kwargs["hat"] = char["hat"]
    # Worn traits (round-3 system 3): colours pass through only when
    # the script named them (None = the art's ink default); the beard
    # style passes only when valid, never a guessed value.
    for _tkey in ("hair_color", "hat_color", "scarf_color", "beard_color",
                    "apron_color"):
        if char.get(_tkey):
            kwargs[_tkey] = char[_tkey]
    if char.get("beard_style") in ("none", "full"):
        kwargs["beard_style"] = char["beard_style"]
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
    # Eye count (general face trait): explicit contract data only --
    # a value outside {1, 2} fails loudly, never silently defaults.
    if "eye_count" in char:
        _eye_count = char["eye_count"]
        if isinstance(_eye_count, bool) or _eye_count not in (1, 2):
            raise ValueError(
                f"unknown eye_count for {name!r}: {_eye_count!r} "
                "(expected 1 or 2)")
        kwargs["eye_count"] = int(_eye_count)
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
    # D3: a planner-assigned tight framing ("highlights") wins
    # over the registry default framing; the default is kept as
    # base_framing so the tight window derives from it.
    if shot.get("map_framing") == "highlights":
        if spec.get("framing"):
            spec["base_framing"] = spec.pop("framing")
        spec["framing"] = "highlights"
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
    assigned by the midpoint of the CHARACTER-PROPORTIONAL window
    each phrase occupies -- the same time model ``phrase_windows``
    lays out (weights = max(1, len(phrase))), so the segment texts,
    the burned subtitles and subtitles.json all agree on which
    words are spoken in which slice. (An earlier version assigned
    by equal-share midpoints, which disagreed with the char-
    proportional record by up to ~2.7 s at phrase boundaries.)
    Every phrase appears exactly once, in order; a span with no
    phrase midpoint gets an empty string -- text is never invented."""
    phrases = split_subtitle(text) if (text or "").strip() else []
    if not phrases:
        return [""] * len(spans)
    total = sum(spans)
    weights = [max(1, len(p)) for p in phrases]
    wsum = float(sum(weights))
    bounds = []
    cursor = 0.0
    for span in spans:
        cursor += span
        bounds.append(cursor)
    mids = []
    acc = 0.0
    for w in weights:
        mids.append((acc + w / 2.0) / wsum * total)
        acc += w
    out: list = []
    idx = 0
    for end in bounds:
        take = []
        while idx < len(phrases):
            if mids[idx] < end:
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


# Pacing merge (round 7): a synthesized shot shorter than this
# merges into its predecessor when the pair is mergeable (same
# scene/location/cast/speaker/kind, no directive on the short
# shot, no insert, different lines). The reference holds ~5-6 s
# per shot; the planner's one-shot-per-line split produced
# 1.2-1.8 s fragments that cut too fast to read.
PACING_MERGE_MAX_SHORT_SEC = 2.5
PACING_MERGE_MAX_TOTAL_SEC = 6.5

_INSERT_SHOT_TYPES = frozenset(
    {"object_insert", "graphic_insert"})

# Round 9 (R2-C4): reach-without-grasp gestures. In an insert the
# frozen crop amputates these into a disembodied frozen claw (EMIT ->
# present_prop pinned at the reach limit inside the 5x crop, the hand
# never touching anything). They resolve to idle in insert shots.
# Prop-carrying primitives (hand_over, pick_up, put_away, shield,
# hammer_strike, ...) are NOT in this set: the prop follows the hand,
# so the hand IS the insert's subject (the handover insert's bolt).
_INSERT_IDLE_PRIMITIVES = frozenset(
    {"present_prop", "reach_to", "point_at", "raise_hand", "wave"})

# Round 16 (L02-D2): primitives whose execution centres on a
# prop at the hands -- an extreme close-up on one of these
# frames the hands + prop (telemetry-deferred, like an insert),
# never the face. CARRY is excluded on purpose: a carried bag
# hangs at the hip, and a hip-centred ECU is unproven -- the
# face framing stays for carries until a script proves
# otherwise. "put_away" stays: the hand + prop mid-transfer
# is the subject even as the prop leaves the hands.
_PROP_ACTION_PRIMITIVES = frozenset({
    "pick_up", "hold_pen", "insert_key", "open_wallet",
    "close_wallet", "write_on_paper", "sign_document",
    "hand_over", "receive_prop", "present_prop", "bend_pick",
    "kneel_pick", "put_away",
})


def _merge_short_shots(shots):
    """Merge short synthesized shots into their predecessor.

    Returns a new list; the input is untouched. A merge keeps
    the predecessor's framing/camera, sums the durations and
    breakdowns, unions the event ids, and records the merge on
    the surviving entry (``pacing_merge``) -- never silent.
    Total duration is preserved exactly (the sum is the sum).
    Dialogue is never merged: different speakers or kinds keep
    their cuts, and segments of one line keep their framing
    progression.
    """
    merged: list[dict] = []
    for shot in shots:
        if not merged:
            merged.append(dict(shot))
            continue
        prev = merged[-1]
        dur = float(shot.get("duration", 0.0))
        prev_dur = float(prev.get("duration", 0.0))
        # Segments of one line share a non-None line_index and
        # keep their framing progression; action-lead shots
        # carry line_index None and are distinct beats.
        same_line = (shot.get("line_index") is not None
                     and shot.get("line_index")
                     == prev.get("line_index"))
        mergeable = (
            dur < PACING_MERGE_MAX_SHORT_SEC
            and not shot.get("directive_shot_id")
            and shot.get("shot_type") not in _INSERT_SHOT_TYPES
            and prev.get("shot_type") not in _INSERT_SHOT_TYPES
            and shot.get("scene") == prev.get("scene")
            and shot.get("v1_location") == prev.get("v1_location")
            and set(shot.get("visible") or [])
            == set(prev.get("visible") or [])
            and shot.get("speaker") == prev.get("speaker")
            and shot.get("kind") == prev.get("kind")
            and not same_line
            and prev_dur + dur <= PACING_MERGE_MAX_TOTAL_SEC)
        if not mergeable:
            merged.append(dict(shot))
            continue
        new = dict(prev)
        new["duration"] = round(prev_dur + dur, 2)
        prev_bd = dict(prev.get("duration_breakdown") or {})
        shot_bd = dict(shot.get("duration_breakdown") or {})
        new["duration_breakdown"] = {
            "voice_sec": round(
                float(prev_bd.get("voice_sec", 0.0))
                + float(shot_bd.get("voice_sec", 0.0)), 2),
            "beat_sec": round(
                float(prev_bd.get("beat_sec", 0.0))
                + float(shot_bd.get("beat_sec", 0.0)), 2),
            "action_lead_sec": round(
                float(prev_bd.get("action_lead_sec", 0.0))
                + float(shot_bd.get("action_lead_sec", 0.0)), 2),
            "total_sec": new["duration"],
        }
        new["voice_duration"] = round(
            float(prev.get("voice_duration", 0.0))
            + float(shot.get("voice_duration", 0.0)), 2)
        new["text"] = " ".join(
            t for t in (str(prev.get("text") or "").strip(),
                        str(shot.get("text") or "").strip()) if t)
        seen = set()
        new["event_ids"] = [
            e for e in list(prev.get("event_ids") or [])
            + list(shot.get("event_ids") or [])
            if not (e in seen or seen.add(e))]
        for _cue_key in ("action_cues", "scene_cues",
                         "dropped_cues"):
            _seen_cues = set()
            new[_cue_key] = [
                c for c in list(prev.get(_cue_key) or [])
                + list(shot.get(_cue_key) or [])
                if not (c in _seen_cues or _seen_cues.add(c))]
        if shot.get("is_reveal_shot"):
            new["is_reveal_shot"] = True
            new["reveal_type"] = shot.get("reveal_type")
        new["segment_index"] = 0
        new["segment_count"] = 1
        new["pacing_merge"] = list(
            prev.get("pacing_merge") or []) + [round(dur, 2)]
        merged[-1] = new
    return merged


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
    restarted, truncated or rewritten); one shot covers one line,
    except the pacing merge (round 7): a short (< 2.5 s)
    synthesized shot with no directive merges into its
    predecessor when the pair shares scene/location/cast/
    speaker/kind and the total stays <= 6.5 s, so the cut rhythm
    approaches the reference ~5-6 s without dropping or
    duplicating any line.

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
        # Round-6 shield staging: a character NAMED in a scene's
        # action text is present in that scene's action -- the
        # protected figure of a SHIELD beat ("che chắn cho Bé Nam")
        # neither speaks nor acts, so the speaker/actor rules above
        # left them invisible until their first speaking scene and
        # the shield beat staged with nobody to protect. Names match
        # longest-first with matched spans blanked, so "Bé Nam"
        # never also introduces a shorter "Nam". Spoken lines are
        # NOT scanned: being talked about is not being present.
        _atext = str(_sc.get("action_text", "") or "")
        _scan = _atext
        for _nm in sorted(char_names, key=len, reverse=True):
            _m = re.search(r"(?<!\w)" + re.escape(_nm) + r"(?!\w)",
                           _scan)
            if _m:
                first_scene.setdefault(_nm, _num)
                _scan = (_scan[:_m.start()] + " " * (_m.end()
                         - _m.start()) + _scan[_m.end():])
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
                # Round 10 (R9-D1): a progression segment is a NEW
                # shot by cut, not the directive's shot. It keeps
                # the directive's elevation-only angle (a high_angle
                # reaction stays high), but never inherits
                # over_shoulder: that angle names an azimuth (28
                # deg OTS), which blocks the viewpoint flip and
                # froze shot #9's camera across rounds while every
                # other eligible shot moved. Fall back to the scene
                # angle, or None when the scene angle is
                # over_shoulder too (the flip then applies).
                seg_angle = angle_v
                if seg_idx > 0 and seg_angle == "over_shoulder":
                    seg_angle = scene_angle \
                        if scene_angle != "over_shoulder" else None
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
                    "camera_angle": seg_angle,
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
    # Pacing merge (round 7): short synthesized fragments merge
    # into their predecessor (same scene/location/cast/speaker/
    # kind) so the cut rhythm approaches the reference ~5-6 s.
    # Runs before END_HOLD so the hold still extends the last
    # content shot, and before the end card is appended.
    shots = _merge_short_shots(shots)
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
    _map_run_key = None
    _map_run_idx = 0
    # Round-9 viewpoint alternation (F9): per-scene flip counter
    # + used sides per staging signature (see the post-pass
    # block below).
    _az_scene = None
    _az_flip = 0
    _az_used: dict[tuple, set] = {}
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
        # D3: consecutive map shots of one location alternate
        # full/tight framings by cut (close_up map shots are
        # always tight -- a close_up showing the full map is a
        # lie). Highlights themselves never change: only the
        # framing varies, a presentation choice.
        _loc = _s.get("v1_location")
        _is_map = (isinstance(_loc, dict)
                   and select_archetype(_loc)[0] == "MAP")
        if _is_map:
            _key = _loc.get("id") or _loc.get("location_id") or ""
            if _key != _map_run_key:
                _map_run_key, _map_run_idx = _key, 0
            if _s["shot_type"] in ("close_up", "extreme_close_up",
                                   "graphic_insert"):
                _s["map_framing"] = "highlights"
            elif _map_run_idx % 2 == 1:
                _s["map_framing"] = "highlights"
            else:
                _s["map_framing"] = "full"
            _s["map_framing_source"] = "planner:alternation"
            _map_run_idx += 1
        else:
            _map_run_key, _map_run_idx = None, 0
        # Round-9 viewpoint alternation (F9): EVERY eligible shot
        # gets a real viewpoint side. Round 6 only flipped REPEAT
        # occurrences of a staging signature, so a plan with
        # all-distinct signatures (Loop-01: all 17 shots) rendered
        # every shot from azimuth 0 -- the zoom-only defect: the
        # same frontal axis at different crop scales, the
        # background's left-right parallax never shifting. Within
        # a scene, eligible shots alternate +1/-1 (18-degree 3/4
        # views, both on the camera side of the 180-degree line,
        # fixed within the shot, changing BY CUT). A repeat of a
        # staging signature escalates to an unused side (+2/-2)
        # so no two same-signature shots in a scene share a
        # viewpoint (the round-6 repeat protection, kept). First
        # occurrences are NOT pixel-identical to before -- that
        # is the point of the fix. Exemptions unchanged:
        # end card, establishing (geography anchors), inserts
        # (subject centred), OTS/SRS (own azimuth logic). A
        # scripted camera_angle does NOT exempt a shot: the flip
        # changes azimuth only and preserves the resolved angle's
        # elevation exactly. EXCEPTION (round 10, R9-D1):
        # over_shoulder DOES name an azimuth (28 deg OTS), and the
        # resolver's OTS branch blocks the flip -- so progression
        # segments never inherit it (see the segment loop above);
        # only a shot whose own directive/type is OTS keeps it.
        if (_s["kind"] != "end_card"
                and _s["shot_type"] not in (
                    "establishing", "object_insert",
                    "over_the_shoulder", "shot_reverse_shot",
                    "graphic_insert")):
            _loc_key = ""
            if isinstance(_loc, dict):
                _loc_key = str(_loc.get("id")
                               or _loc.get("location_id") or "")
            # "tracking" executes STATIC (camera fixed within
            # the shot, same 1.6 crop scale as medium), so a
            # tracking shot and a medium shot stage identically
            # -- group them in one signature.
            _sig_type = ("medium" if _s["shot_type"] == "tracking"
                         else _s["shot_type"])
            _staging_sig = (
                _s["scene"], _sig_type,
                tuple(_s.get("visible") or ()), _loc_key)
            if _s["scene"] != _az_scene:
                _az_scene, _az_flip = _s["scene"], 0
                _az_used = {}
            _base = 1 if _az_flip % 2 == 0 else -1
            _az_flip += 1
            _used = _az_used.setdefault(_staging_sig, set())
            _side = _base
            if _side in _used:
                for _cand in (_base, -_base, 2, -2):
                    if _cand not in _used:
                        _side = _cand
                        break
            _used.add(_side)
            _s["viewpoint_azimuth_side"] = _side
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
    _paint_geometry_spec(draw, spec, x, y, scale)


def _paint_geometry_spec(draw, spec, x, y, scale):
    """Paint a geometry spec with its grip contact point on (x, y).

    Shared by the footprint-scaled draw and the articulated draws
    (a held hammer built at screen size paints at scale 1.0, so its
    strike face lands exactly on the computed head position).
    """
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


def _draw_prop(draw, x, y, kind="wallet", w=None, h=None, open_u=0.0,
               tip=None):
    """Draw one prop at (x, y) in the character line language (INK
    outline, flat fill). F7: one distinct simple shape per PROP_KINDS
    entry; unknown kinds render as "generic". The wallet shape is the
    original one, unchanged, so existing wallet shots are identical.
    ``w``/``h`` default to the kind's footprint (geometry_footprint:
    long-handled props draw tall, everything else 76x50); explicit
    values (the insert card) always win.
    ``open_u`` (W4, wallet only): 0 = closed (pixel-identical to the
    original), 1 = fully open — an inner flap panel extends to the
    right, so OPEN_WALLET reads on screen. ``tip`` (W4, pen only):
    the pen tip position — a held pen is drawn as a barrel from the
    hand (x, y) to its tip; without it the rest shape is drawn."""
    kind = str(kind or "wallet").strip().lower()
    if kind not in PROP_KINDS:
        kind = "generic"
    if w is None or h is None:
        _fw, _fh = geometry_footprint(kind)
        if w is None:
            w = _fw
        if h is None:
            h = _fh
    if kind == "hammer" and tip is not None:
        # Round-5 hammer contact: a held hammer draws articulated
        # -- the handle runs from the grip (x, y) to the striking
        # face (tip), built at screen size from the grip vector
        # itself, so the drawn head lands ON the computed head
        # position (the point the primitive aims at and the audit
        # measures). The tip already encodes the character's
        # facing, so the spec builds with facing=1 and the vector
        # angle; the head polygon is symmetric about the handle
        # axis. A degenerate tip falls through to the footprint
        # draw. Mirrors the pen's tip draw.
        _tx, _ty = float(tip[0]), float(tip[1])
        _dx, _dy = _tx - float(x), _ty - float(y)
        _length = math.hypot(_dx, _dy)
        if _length >= 1.0:
            _angle = math.atan2(_dy, _dx)
            _spec = geometry_for_prop(
                {"kind": "hammer", "length_px": _length},
                grip_angle_rad=_angle, facing=1)
            _paint_geometry_spec(draw, _spec, x, y, 1.0)
            return
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
        # Round 15 (L02-D10): a brass key, not an ink outline.
        # The unfilled dark shape read as a facial smudge near
        # pale faces (L02-D4). Brass fill + ink outline; the
        # shaft and teeth get a brass core with an ink edge.
        brass = (203, 160, 72)
        draw.ellipse([x - w / 2, y - 12, x - w / 2 + 26, y + 12],
                     fill=brass, outline=ink, width=3)
        for _ln, _wd in ((((x - w / 2 + 24, y), (x + w / 2, y)), 4),
                         (((x + w / 2 - 12, y),
                           (x + w / 2 - 12, y + 12)), 3),
                         (((x + w / 2 - 4, y),
                           (x + w / 2 - 4, y + 9)), 3)):
            draw.line(_ln, fill=ink, width=_wd + 2)
            draw.line(_ln, fill=brass, width=_wd)
    elif kind == "lock":
        # Round 16 (L02-D2): a padlock -- brass body, keyhole,
        # and a shackle arc that pivots on its left hinge by
        # open_u (the wallet open_u precedent): 0 = closed
        # half-ring, 1 = swung open. Drawn relative to w/h so
        # it fits any footprint.
        brass = (203, 160, 72)
        _bw, _bh = 0.62 * w, 0.52 * h
        _bcx, _bcy = x, y + 0.16 * h
        draw.rounded_rectangle(
            [_bcx - _bw / 2, _bcy - _bh / 2,
             _bcx + _bw / 2, _bcy + _bh / 2],
            radius=8, fill=brass, outline=ink, width=3)
        _kr = max(2.0, 0.06 * h)
        draw.ellipse([_bcx - _kr, _bcy - _kr - 0.06 * h,
                      _bcx + _kr, _bcy + _kr - 0.06 * h],
                     fill=ink)
        draw.polygon([(_bcx - _kr * 0.7, _bcy - 0.02 * h),
                      (_bcx + _kr * 0.7, _bcy - 0.02 * h),
                      (_bcx + _kr, _bcy + 0.14 * h),
                      (_bcx - _kr, _bcy + 0.14 * h)], fill=ink)
        # Shackle: a half-ring arc above the body, rotated
        # around its left foot (the hinge) by -55 deg * open_u
        # so the right foot lifts clear of the body.
        _hx, _hy = _bcx - _bw / 2, _bcy - _bh / 2
        _sr = _bw / 2
        _th = -math.radians(55.0) * max(0.0, min(1.0, open_u))
        _ct, _st = math.cos(_th), math.sin(_th)
        _pts = []
        for _i in range(17):
            _a = math.pi * _i / 16.0
            _px = _bcx + _sr * math.cos(_a)
            _py = _hy - _sr * math.sin(_a)
            _dx, _dy = _px - _hx, _py - _hy
            _pts.append((_hx + _dx * _ct - _dy * _st,
                         _hy + _dx * _st + _dy * _ct))
        draw.line(_pts, fill=ink, width=5, joint="curve")
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


# Distance from a simple (legacy-shape) prop's transform origin to
# its lowest drawn pixel, as a fraction of the footprint height --
# read off the _draw_prop branches above. "key" is a fixed 12 px
# (teeth); "umbrella" is the shaft + crook below the origin.
_SIMPLE_PROP_BOTTOM = {
    "wallet": 0.5, "newspaper": 0.5, "letter": 0.5, "cup": 0.5,
    "bag": 0.5, "book": 0.5, "flower": 0.5,
    "ticket": 1.0 / 3.0, "generic": 1.0 / 3.0, "pen": 1.0 / 3.0,
}


def prop_bottom_offset(kind, w=None, h=None):
    """Pixels from a prop's transform origin down to its lowest
    drawn pixel at the (w, h) footprint (defaults: the kind's
    footprint). Simple kinds draw centred on the origin (table
    above); geometry kinds draw with the spec's grip contact
    point on the origin, so the offset is the scaled
    grip-to-bottom distance -- the same construction
    ``_draw_geometry_prop`` uses. ``test_prop_support_rest``
    measures every kind's drawn bottom against this function, so
    the two can never drift apart silently. Outline/line width
    (~1-3 px) is not included: the snap puts the fill bottom on
    the support top and the outline overlap reads as contact.
    """
    kind = str(kind or "wallet").strip().lower()
    if kind not in PROP_KINDS:
        kind = "generic"
    if w is None or h is None:
        _fw, _fh = geometry_footprint(kind)
        if w is None:
            w = _fw
        if h is None:
            h = _fh
    if kind in _GEOMETRY_PROP_KINDS:
        spec = geometry_for_prop(
            {"kind": kind, "length_px": 200.0, "size_px": 170.0})
        x0, y0, x1, y1 = spec["bbox"]
        bw, bh = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
        scale = min(float(w) / bw, float(h) / bh)
        _gx, gy = spec["contact_points"]["grip"]
        return (y1 - gy) * scale
    if kind == "umbrella":
        return 0.9 * float(h) + 10.0
    if kind == "key":
        return 12.0
    return _SIMPLE_PROP_BOTTOM.get(kind, 0.5) * float(h)


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


def _draw_character_shadow(img, ch, cam, ground_pos, light,
                           cast=False):
    """Ratio-capped contact shadow under one character (W1).

    Geometry comes from lighting.shadow_ellipse_spec: the shadow can
    never outgrow the feet, stays a thin strip (depth-capped), and
    follows the light offset. No-op when the character is behind the
    camera (spec is None).

    Round 13: with ``cast`` (outdoor shots only -- the caller
    gates on the archetype), a tapered cast quad stretches from
    the feet along the light's ground direction, drawn under the
    contact ellipse. Indoors the sun is not the light, so no
    cast shadow is drawn.
    """
    half_w, half_d = _character_shadow_footprint(ch)
    if cast:
        _, _, pscale, vis = cam.project(ground_pos, *img.size)
        if vis and pscale > 0:
            spec = cast_shadow_spec(
                ground_pos, ch.H / pscale, half_w / pscale,
                light, cam, img.size)
            if spec is not None:
                pts = spec["polygon_px"]
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                pad = 10
                x0, y0 = int(min(xs)) - pad, int(min(ys)) - pad
                x1, y1 = int(max(xs)) + pad, int(max(ys)) + pad
                layer = Image.new(
                    "RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
                ImageDraw.Draw(layer).polygon(
                    [(x - x0, y - y0) for x, y in pts],
                    fill=(0, 0, 0, int(255 * spec["alpha"])))
                layer = layer.filter(ImageFilter.GaussianBlur(6))
                img.paste(layer, (x0, y0), layer)
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
    """Pixel-space desk/paper/chair/anvil anchors for sit/write/sign/
    strike.

    From the environment package's furniture elements (projected with
    the shot camera) when present; staging-derived fallbacks otherwise
    (legacy scenes without an environment package). Returns
    {"desk": {"x", "top_y"} | None, "paper": {"x","y","w","h"},
    "chair": {"x", "seat_y"}, "anvil": {"x", "top_y"},
    "source": "environment"|"fallback"}.
    The paper rect's "y" is its TOP edge (the hold_pen/write_on_paper
    contract)."""
    anchors = {"desk": None, "paper": None, "chair": None,
               "anvil": None, "source": "fallback"}
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
        # The strike surface: the anvil top (ID-preferred; the kind
        # map collapses base/body/top). hammer_strike anchors here.
        anvil_el = by_id.get("anvil_top") or elements.get("anvil")
        anvil_xy = _project_top(anvil_el)
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
        if anvil_xy is not None:
            anchors["anvil"] = {"x": anvil_xy[0],
                                "top_y": anvil_xy[1]}
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
    if anchors["anvil"] is None:
        # No staged anvil: a strike surface in front of the striker
        # at anvil height. The strike still reads; it never invents
        # an anvil drawing, only the contact point.
        anchors["anvil"] = {
            "x": staging_x + facing * 0.30 * char_h,
            "top_y": ground_y - 0.45 * char_h}
    # Sanity: the desk top must sit above the seat in screen coords.
    if anchors["desk"]["top_y"] >= anchors["chair"]["seat_y"]:
        anchors["desk"]["top_y"] = anchors["chair"]["seat_y"] - 0.15 * char_h
    return anchors


def _reactive_element_anchors(env_pkg, cam, size):
    """Screen anchors for the set-piece reaction (round-2 system 5).

    The furnace mouth (projected element centre -- the glow wash
    centre) and the sparks element (drawn per-frame by the
    reaction overlay with a boosted count/frame). Elements that
    are absent or off-camera yield None: the reaction paints
    nothing it cannot anchor, and never invents a set-piece.
    """
    anchors = {"furnace": None, "sparks_el": None, "sparks_xy": None}
    if env_pkg is None:
        return anchors
    elements = [e for e in (env_pkg.get("elements") or [])
                if isinstance(e, dict)]
    furnace_el = next(
        (e for e in elements if e.get("id") == "furnace"), None)
    if furnace_el is None:
        furnace_el = next(
            (e for e in elements if e.get("kind") == "furnace"), None)
    sparks_el = next(
        (e for e in elements if e.get("kind") == "sparks"), None)
    w, h = size

    def _project(element):
        px, py, _s, vis = cam.project(element["center"], w, h)
        return (px, py) if vis else None

    if furnace_el is not None:
        anchors["furnace"] = _project(furnace_el)
    if sparks_el is not None:
        anchors["sparks_el"] = sparks_el
        anchors["sparks_xy"] = _project(sparks_el)
    return anchors


def _support_anchors(env_pkg, cam, size):
    """Pixel-space top surfaces a prop can rest on, projected with
    the shot camera (the same top-face-centre contract as
    ``_furniture_anchors._project_top``). Returns a list of
    {\"id\", \"kind\", \"support\", \"x\", \"top_y\", \"width\"} where
    \"support\" is the ``destination_support`` name that selects
    the element. Selection is structural, never positional:
    \"top\" elements (desk_top, bench_top, anvil_top) are picked
    by kind + the \"on_top\" attachment relation -- their legs
    share the kind and must never be selected; freestanding
    bodies (statue_pedestal, altar, cabinet) offer their own top
    face whatever they stand on. Elements whose top projects
    invisible are skipped: a prop must never rest on an
    off-screen support. No support is ever invented -- an empty
    list means the environment has no rest surface.
    """
    if env_pkg is None or cam is None:
        return []
    w, h = size
    anchors = []
    for el in (env_pkg.get("elements") or []):
        if not isinstance(el, dict):
            continue
        kind = el.get("kind")
        rel = (el.get("attachment") or {}).get("relation")
        support = None
        if kind in ("desk", "workbench", "anvil") and rel == "on_top":
            support = "anvil" if kind == "anvil" else "table"
        elif kind == "statue_pedestal":
            support = "pedestal"
        elif kind == "altar":
            support = "altar"
        elif kind == "cabinet":
            support = "cabinet"
        if support is None:
            continue
        try:
            cx, cy, cz = (float(v) for v in el["center"])
            sx, sy, _sz = (float(v) for v in el["size"])
        except (KeyError, TypeError, ValueError):
            continue
        px, py, _s, vis = cam.project((cx, cy + sy / 2.0, cz), w, h)
        if not vis:
            continue
        ax, _ay, _s2, vis_a = cam.project((cx - sx / 2.0, cy, cz), w, h)
        bx, _by, _s3, vis_b = cam.project((cx + sx / 2.0, cy, cz), w, h)
        width = abs(bx - ax) if (vis_a and vis_b) else 0.0
        anchors.append({"id": el.get("id"), "kind": kind,
                        "support": support, "x": float(px),
                        "top_y": float(py), "width": float(width)})
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
    # Round-4 "hon" (ambient life, 2026-11-14): every declared
    # character blinks on a deterministic ambient schedule whether
    # or not the script writes a BLINK sentence. Before this, blinks
    # came ONLY from scripted BLINK events, so ordinary scripts
    # rendered zero blinks and every character stared -- the NPC
    # look. Scripted blinks are kept verbatim; ambient blinks that
    # would land within 0.4 s of a scripted one are suppressed so
    # the two never stack into one long dip.
    def _ambient_blinks(scripted):
        # Round-5 fix (R4-L1): the seed must distinguish RENDERED
        # shots, not just directive ids -- segmentation-split shots
        # share a directive id and blinked in lockstep. start_sec is
        # unique per rendered shot; the shot index disambiguates
        # further when present.
        seed_base = "{}:{}:{}".format(
            did, shot.get("index", ""), shot.get("start_sec", 0.0))
        out = {}
        for _c in package.get("characters") or []:
            _nm = str(_c.get("name") or "")
            if not _nm:
                continue
            _seed = zlib.crc32(
                f"{seed_base}:{_nm}".encode("utf-8")) & 0x7FFFFFFF
            _times = blink_times_for(float(duration), seed=_seed)
            _kept = sorted(scripted.get(_nm) or [])
            for _t in _times:
                if all(abs(_t - _s) > 0.4 for _s in _kept):
                    _kept.append(_t)
            out[_nm] = sorted(_kept)
        return out

    did = shot.get("directive_shot_id")
    if not did or not all_events:
        return ({}, [], {}, _ambient_blinks({}),
                id_to_name, name_to_id)
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
    blink_times = _ambient_blinks(blink_times)
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


def _worn_bag_owner(all_events, pid, t, id_to_name):
    """Owner NAME possessing a bag at time ``t``, or None.

    Round 17 (L02-D3): possession for the worn-bag presentation.
    Like _incoming_holder, but CARRY counts: carrying/wearing a
    bag IS possessing it, while the grasp-hold tracking behind
    the state machine only follows hand grasps. A bag the owner
    puts down (PUT_AWAY/RELEASE/PLACE) stops being worn; a
    handover transfers possession to the receiver. When the
    earliest event for the bag is a CARRY/HOLD (an ongoing state
    the script describes, not an acquisition), the carrier owns
    it from the start -- before any event has ended, the default
    governs; once events have ended, the walk governs. A bag
    first acquired by PICK_UP/TAKE_OUT has no default owner.
    """
    evs = sorted(
        (e for e in all_events if isinstance(e, dict)
         and e.get("prop_id") == pid and _event_time_trusted(e)),
        key=lambda e: float(e.get("start_time", 0.0)))
    if not evs:
        return None
    default = None
    if evs[0].get("action_type") in ("CARRY", "HOLD", "HOLD_PEN"):
        default = id_to_name.get(str(evs[0].get("actor_id")))
    owner = None
    any_ended = False
    for event in sorted(
            evs, key=lambda e: float(e.get("end_time", 0.0))):
        if float(event.get("end_time", 0.0)) > t + 1e-9:
            break
        any_ended = True
        action = event.get("action_type")
        if action == "HAND_OVER":
            owner = event.get("target_id")
        elif action in ("PICK_UP", "TAKE_OUT", "HOLD", "HOLD_PEN",
                        "CARRY"):
            owner = event.get("actor_id")
        elif action in ("PUT_AWAY", "RELEASE", "PLACE"):
            owner = None
    if any_ended:
        return id_to_name.get(str(owner)) if owner is not None             else None
    return default


# Round 16 (L02-D8): POSE_HELD body poses that persist across the
# segment/cut boundary within a scene. ONLY primitives whose
# completion pose is itself the held state belong here:
# - sit_down: ends seated (root lowered, knees bent) -- the Loop 02
#   defect (An's sit vanished in the next segment of the same
#   directive shot, because _shot_action_events clips the sit event
#   out of every segment after its span ends).
# Deliberately EXCLUDED:
# - crouch: returns to standing by the end of its duration, so its
#   completion pose IS standing; persisting it would be a no-op.
# - shield: a reactive within-event hold ("holds to the end of the
#   duration"); a guard frozen across later shots reads wrong once
#   the threat moment passes. Within-shot hold is unchanged.
# - sit_at_desk: owned by the _seated_at_start mechanism (furniture
#   staging); a later sit_at_desk CLEARS a floor sit here.
# - gestures (reach/point/raise/wave/nod/turn): ambiguous across a
#   cut; left for a future defect with frame evidence.
_HELD_POSE_PRIMITIVES = frozenset({"sit_down"})
_HELD_POSE_CLEARING_PRIMITIVES = frozenset({
    "stand_up", "stand_from_chair", "walk_to", "run_to", "walk_mud",
    "sit_at_desk"})


def _lock_events_at_start(all_events, scene_no, t0, id_to_name):
    """Last INSERT_KEY event per character at time ``t0``.

    Same cross-shot memory shape as ``_held_poses_at_start``:
    events ending at or before ``t0``, trusted times only, same
    scene only (the SC number of the event's shot_id must equal
    ``scene_no``), in end-time order. A lock opened in an
    earlier segment/shot of the scene stays staged (and open)
    in later segments -- there is no lock-closing verb yet, so
    nothing clears it. Returns {character NAME: event}.
    """
    opened: dict[str, dict] = {}
    try:
        scene_no = int(scene_no)
    except (TypeError, ValueError):
        return opened
    ordered = sorted(
        (e for e in (all_events or []) if isinstance(e, dict)
         and _event_time_trusted(e)),
        key=lambda e: float(e.get("end_time", 0.0)))
    for event in ordered:
        if float(event.get("end_time", 0.0)) > float(t0) + 1e-9:
            break
        sid = str(event.get("shot_id") or "")
        m = re.match(r"SC(\d+)_", sid)
        if m is None or int(m.group(1)) != scene_no:
            continue
        name = id_to_name.get(str(event.get("actor_id"))) \
            if event.get("actor_id") else None
        if name is None:
            continue
        prim = (event.get("required_pose") or {}).get("primitive")
        if prim == "insert_key":
            opened[name] = event
    return opened


def _held_poses_at_start(all_events, scene_no, t0, id_to_name):
    """Last POSE_HELD body pose per character at time ``t0``.

    Same cross-shot memory shape as ``_incoming_holder`` and the
    ``_seated_at_start`` scan: events ending at or before ``t0``,
    trusted times only, same scene only (the SC number of the
    event's shot_id must equal ``scene_no``), in end-time order.
    A held-primitive event sets the character's held pose; a
    clearing-primitive event (stand/walk/sit-at-desk) clears it;
    anything else leaves it alone (a gesture while seated does not
    stand the character up). Returns {character NAME: event}.
    """
    held: dict[str, dict] = {}
    try:
        scene_no = int(scene_no)
    except (TypeError, ValueError):
        return held
    ordered = sorted(
        (e for e in (all_events or []) if isinstance(e, dict)
         and _event_time_trusted(e)),
        key=lambda e: float(e.get("end_time", 0.0)))
    for event in ordered:
        if float(event.get("end_time", 0.0)) > float(t0) + 1e-9:
            break
        sid = str(event.get("shot_id") or "")
        m = re.match(r"SC(\d+)_", sid)
        if m is None or int(m.group(1)) != scene_no:
            continue
        name = id_to_name.get(str(event.get("actor_id"))) \
            if event.get("actor_id") else None
        if name is None:
            continue
        prim = (event.get("required_pose") or {}).get("primitive")
        if prim in _HELD_POSE_CLEARING_PRIMITIVES:
            held.pop(name, None)
        elif prim in _HELD_POSE_PRIMITIVES and \
                (event.get("completion_state") or {}).get("state") \
                == "POSE_HELD":
            held[name] = event
    return held


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
                       fallback_ground_y=0.0, events=None,
                       support_anchors=None, support_records=None):
    """Per-shot prop rest positions + rest kinds.

    Rest kinds: "surface" (desk paper), "pocket" (hidden until
    manipulated), "ground" (visible on the ground line),
    "support" (bottom on a support surface's top edge -- a
    pedestal, desk, workbench, anvil, altar, or cabinet the
    environment actually contains). A placement event naming a
    support (``destination_support``) or a take event naming the
    support it lifts from (``source_support`` -- the prop's home)
    rests the prop on the nearest matching support anchor; when
    one shot names both, the placement wins (the prop's end
    state). Precedence: a drop in the shot (RELEASE_PROP) always
    rests the prop on the ground; a support-naming event
    overrides an ON_GROUND initial location (the prop was picked
    up and staged); otherwise the ground rule (directive §7)
    applies -- a prop rests on the ground when its semantic
    initial location is ON_GROUND, the tracker's
    transition-table resolution from the compiled events, never
    a keyword guess. The snap is geometric: the rest point is
    the support's projected top edge minus the prop's drawn
    bottom offset, so the prop's bottom pixels sit ON the
    surface, never floating above it or sunk into it. A named
    support the environment does not have is recorded in
    ``support_records`` as "missing:<name>" and falls through to
    the ground/kind rules -- the engine never invents a support.
    Returns (rests, rest_kinds, pocket_anchors).
    """
    dropped = {str(e.get("prop_id")) for e in (events or [])
               if isinstance(e, dict)
               and e.get("action_type") == "RELEASE"
               and e.get("semantic_action_type") == "RELEASE_PROP"}
    # Support assignment (before the per-prop loop: props sharing
    # one support spread across its width instead of stacking).
    # Naming runs even with no anchors, so a named-but-absent
    # support is always recorded as missing.
    support_positions: dict[str, tuple] = {}
    support_for_pid: dict[str, dict] = {}
    named: dict[str, str] = {}
    for e in (events or []):
        if not isinstance(e, dict):
            continue
        pid = e.get("prop_id")
        if pid is None:
            continue
        if e.get("source_support"):
            named[str(pid)] = e["source_support"]
    for e in (events or []):
        if not isinstance(e, dict):
            continue
        pid = e.get("prop_id")
        if pid is None:
            continue
        if e.get("destination_support"):
            named[str(pid)] = e["destination_support"]
    for pid in pids:
        name = named.get(str(pid))
        if not name:
            continue
        cands = [a for a in (support_anchors or [])
                 if a.get("support") == name]
        if not cands:
            if support_records is not None:
                support_records[str(pid)] = f"missing:{name}"
            continue
        actor_name = first_actor_for_pid.get(pid) or default_actor
        ax = staging.get(actor_name, W // 2)
        if not isinstance(ax, (int, float)):
            ax = W // 2
        support_for_pid[str(pid)] = min(
            cands, key=lambda a: abs(float(a["x"]) - float(ax)))
    groups: dict[str, list] = {}
    for key, anchor in support_for_pid.items():
        groups.setdefault(str(anchor.get("id")), []).append(key)
    for members in groups.values():
        members.sort()
        anchor = support_for_pid[members[0]]
        n = len(members)
        width = float(anchor.get("width") or 0.0)
        for i, key in enumerate(members):
            pid = next(p for p in pids if str(p) == key)
            kind = infer_prop_kind(prop_dicts[pid])
            fw, _fh = geometry_footprint(kind)
            if n == 1:
                x = float(anchor["x"])
            else:
                step = min(float(fw) + 16.0,
                           0.6 * width / (n - 1)) if width > 0 \
                    else float(fw) + 16.0
                x = float(anchor["x"]) + (i - (n - 1) / 2.0) * step
                if width > 0:
                    x = max(float(anchor["x"]) - 0.3 * width,
                            min(float(anchor["x"]) + 0.3 * width, x))
            support_positions[key] = (
                x, float(anchor["top_y"]) - prop_bottom_offset(kind))
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
        if pid in dropped or (initial == PropLocation.ON_GROUND.value
                              and str(pid) not in support_positions):
            rest_kinds[pid] = "ground"
            if actor_name in staging and actor_name in ground_ys:
                rests[pid] = (staging[actor_name] + 220.0,
                              ground_ys[actor_name])
            else:
                rests[pid] = (W // 2, fallback_ground_y)
            pocket_anchors[pid] = None
        elif str(pid) in support_positions:
            rest_kinds[pid] = "support"
            rests[pid] = support_positions[str(pid)]
            pocket_anchors[pid] = None
            if support_records is not None:
                support_records[str(pid)] = str(
                    support_for_pid[str(pid)].get("id"))
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
    grasped earlier stays in hand. An adapter-declared OWNER (ID
    form) seeds a HOLD only for a declared SIGNATURE_PROP that no
    compiled event ever stages: owner-held signature props must be
    visible, while a pocket prop must never appear in hand before
    its take-out shot. Returns (machine, pids, prop_kinds,
    rest_kinds, diagnostics) or (None, [], {}, {}, []) when the shot
    has no compiled events or no props.
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
    # Round 16 (L02-D2): a grasp/use event starting at (or
    # spanning) the shot start governs the prop from frame 0 --
    # the seeded hold's ATTACHED marker (t0 + 0.006) would
    # otherwise shadow the event's first marker (at t0) for the
    # whole window and draw the prop at the PREVIOUS holder's
    # hand (the ECU key drew at Ba Tu's hand while An's hand
    # drove empty to the lock). Transfers/releases keep the
    # seed: their markers interpolate from the incoming hold,
    # and their current behaviour is tested. Mid-shot uses keep
    # the seed for the pre-event frames (the seed window ends
    # before the event starts, so no shadowing there).
    _USE_AT_START_TYPES = (
        "BEND_PICK", "KNEEL_PICK", "SHIELD", "OPEN_WALLET",
        "CLOSE_WALLET", "OPEN", "CLOSE", "WRITE", "SIGN",
        "HAMMER_STRIKE", "INSERT_KEY")
    used_at_start = {
        str(e.get("prop_id")) for e in shot_events
        if e.get("action_type") in _USE_AT_START_TYPES
        and float(e.get("start_time", t0 + 1.0)) <= t0 + 0.01}
    # A shot event naming the prop's home rest -- a resting
    # sentence ("Viên đá nằm trên đe") or a take from a support
    # -- overrides the incoming hold for this shot: the script
    # places the prop ON the support, so it rests there until
    # taken, instead of staying in hand from the shot start
    # (round-7 insert discipline: the R6 insert showed the
    # stone held against a leg because the seeded HOLD won
    # over the anvil rest).
    resting_pids = {str(e.get("prop_id")) for e in shot_events
                    if e.get("source_support")}
    machine_events = list(shot_events)
    holders = shot.get("prop_holders") or {}
    # Declared signature props (adapter: SIGNATURE_PROP field) by
    # character id, and every prop id any compiled event stages.
    signature_by_char: dict[str, str] = {}
    for _c in package.get("characters") or []:
        if not isinstance(_c, dict):
            continue
        _sig = str(_c.get("signature_prop") or "").strip()
        _cid = _c.get("id") or _c.get("identity_id")
        if _sig and _cid:
            signature_by_char[str(_cid)] = _sig
    event_pids = {str(e.get("prop_id")) for e in all_events
                  if isinstance(e, dict) and e.get("prop_id")}
    for pid in pids:
        if (pid in grasped_in_shot or pid in resting_pids
                or pid in used_at_start):
            continue
        holder_id = _incoming_holder(all_events, pid, t0)
        if holder_id is None:
            holder_name = holders.get(pid)
            if holder_name is None and shot.get("props") \
                    and pid == str(shot["props"][0]):
                holder_name = shot.get("prop_holder")
            if holder_name:
                holder_str = str(holder_name)
                if holder_str in id_to_name:
                    # Adapter-declared owner (ID form). The old code
                    # looked the ID up in name_to_id and always got
                    # None, so owner-held signature props were never
                    # seeded and never drawn. Seed ONLY a declared
                    # signature prop that no compiled event stages.
                    if pid in event_pids:
                        continue
                    _sig = signature_by_char.get(holder_str)
                    _pname = str(prop_dicts[pid].get("name") or "")
                    if _sig is None or _sig.strip().lower() not in (
                            pid.lower(), _pname.lower()):
                        continue
                    holder_id = holder_str
                else:
                    holder_id = name_to_id.get(holder_str)
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


# Primitives that accept hand="both" (both hands converge on the
# target, flanking it): the grasp/transfer/carry family. Every other
# primitive collapses "both" to "r" in _event_fn.
_BOTH_HAND_PRIMITIVES = frozenset({
    "pick_up", "bend_pick", "kneel_pick", "put_away", "carry_bag",
    "receive_prop", "present_prop"})


def _walk_direction(ctx, event):
    """Walk direction for a locomotion event: the shot's direction
    (toward the other character), flipped when the compiler marked
    the event a retreat ("lùi lại một bước" steps AWAY). The facing
    is untouched: a retreating character backs away while still
    facing the other character, which is the astonished step-back.
    """
    direction = ctx["direction"]
    params = (event.get("required_pose") or {}).get("params") or {}
    if params.get("retreat"):
        return -direction
    return direction


_LOCOMOTION_STEP_PX = {"walk_to": 320.0, "run_to": 380.0,
                       "walk_mud": 300.0}


def _swept_x_for_actor(windows, start_x, direction):
    """Min/max root x a character occupies during a shot.

    Replays the locomotion resolution of _event_fn in window
    order: each walk_to/run_to/walk_mud advances the root by its
    step size along the shot direction (flipped for retreat
    events, matching _walk_direction). Non-locomotion windows
    leave the root alone. The framing path (_walk_path_box,
    round 8) and the FG clearance (round 17, L02-D11) share
    this replay so neither can drift from the rendered path:
    a foreground cleared against the static staging box is
    re-covered the moment a runner leaves that box (Loop 02
    shot #3: An ran 380 px right, straight behind the FG
    trunk the clearer had parked beside her staging mark).
    """
    _pos = float(start_x)
    _lo = _hi = _pos
    for _s, _e, _ev in windows:
        _rp = _ev.get("required_pose") or {}
        _step = _LOCOMOTION_STEP_PX.get(_rp.get("primitive"))
        if _step is None:
            continue
        _d = direction
        if ((_rp.get("params") or {}).get("retreat")):
            _d = -_d
        _pos += _step * _d
        _lo = min(_lo, _pos)
        _hi = max(_hi, _pos)
    return _lo, _hi


_HEAD_LEAN_ALLOWANCE_FRAC = 0.09


# Round 20 (R19-D1): dressing elements worth keeping visible
# when the head-separation pass moves a character. Small
# midground/background dressing (a lamp, a hanging pot, a
# stove pipe) can hide entirely behind one head disc; walls,
# floors and furniture are excluded by the width filter or by
# sitting below the head discs. Sky/atmosphere kinds are never
# protected: a head in front of a cloud is correct staging.
_DRESSING_LAYERS = frozenset({"MG", "BG"})
_DRESSING_SKIP_KINDS = frozenset({
    "cloud", "smoke", "steam",
    # Distant backdrop (z ~ -20): horizon houses/towers.
    "distant_house", "house_roof", "house_chimney",
    "house_window", "distant_tower", "tower_spire",
    "tower_window"})
# Wall trim is architecture, not dressing: characters SHOULD
# stand in front of it. An element is trim when it or any
# attachment ancestor is one of these kinds (a window's
# mullions inherit trim-ness from the window, the hanging
# pots from the wall -- the pots are a known follow-up for a
# builder-set keep_visible flag).
_DRESSING_TRIM_KINDS = frozenset(
    {"room_wall", "wall", "window", "pilaster", "mullion",
     "facade"})
_DRESSING_MAX_WIDTH_FRAC = 0.15
_DRESSING_MIN_AREA_PX2 = 1000.0
_DRESSING_RECT_MARGIN = 1.2


def _dressing_rects(pkg, camera, W, H):
    """Projected rects of small dressing elements, in staging
    pixels: {"id", "cx", "cy", "left", "right", "top",
    "bottom"}. Skipped: other layers, sky kinds, wall trim
    (self or any attachment ancestor), off-frame elements,
    elements wider than 15% of the frame, and specks under
    1000 px^2 of projected area."""
    elements = pkg.get("elements") or []
    by_id = {el.get("id"): el for el in elements}

    def _is_trim(el):
        seen = set()
        cur = el
        for _ in range(6):
            if cur is None or id(cur) in seen:
                return False
            seen.add(id(cur))
            if cur.get("kind") in _DRESSING_TRIM_KINDS:
                return True
            att = cur.get("attachment") or {}
            parent = att.get("parent")
            cur = by_id.get(parent) if parent else None
        return False

    rects = []
    for el in elements:
        if el.get("layer") not in _DRESSING_LAYERS:
            continue
        if el.get("kind") in _DRESSING_SKIP_KINDS:
            continue
        if _is_trim(el):
            continue
        try:
            x, y, scale, vis = camera.project(el["center"], W, H)
        except Exception:
            continue
        if not vis:
            continue
        size = el.get("size") or (0.0, 0.0, 0.0)
        w_px = float(size[0]) * scale
        h_px = float(size[1]) * scale
        if w_px >= _DRESSING_MAX_WIDTH_FRAC * W:
            continue
        if w_px * h_px < _DRESSING_MIN_AREA_PX2:
            continue
        hw = w_px / 2.0 * _DRESSING_RECT_MARGIN
        hh = h_px / 2.0 * _DRESSING_RECT_MARGIN
        rects.append({"id": el.get("id", ""), "cx": x, "cy": y,
                      "left": x - hw, "right": x + hw,
                      "top": y - hh, "bottom": y + hh})
    return rects


def _drawn_height_factor(char: dict) -> float:
    """Drawn height / char_metrics height for one character.

    Mirrors map_character's height composition (R17-D13):
    generic characters render at perspective height x
    template ratio x stature; locked registry instances keep
    the conservative factor 1.0 (their heights are locked,
    and no loop script uses a registry name)."""
    key = str(char.get("name", "")).strip().lower()
    try:
        make_character_instance(key, height=CHAR_H)
        return 1.0
    except (ValueError, KeyError):
        pass
    template = char.get("template")
    if template not in VALID_TEMPLATES:
        template = infer_template(char)
    try:
        stature = float(char.get("stature") or 1.0)
    except (TypeError, ValueError):
        stature = 1.0
    return (TEMPLATES[template]["height"]
            / TEMPLATES["male"]["height"] * stature)


def _swept_head_range(windows, start_x, direction, gh,
                      legacy_end=None):
    """Swept head-centre x-range (lo, hi) for one character.

    Round 19 (R18-D1): the R6-D4 head-clearance pass separated
    STATIC standing boxes, but locomotion carries the head up
    to 380 px from the staging mark (Loop 02 #17: a 320 px
    legacy walk; #19: a 380 px compiled run -- both into the
    neighbour's face). Compiled windows replay through
    _swept_x_for_actor; legacy_end is the absolute end x of a
    legacy cue walk/run (no compiled motion in the span).
    Whenever the character travels, both ends grow by the
    gait-lean allowance: the head leads the root by up to
    sin(0.40) x torso during a run.
    """
    lo, hi = _swept_x_for_actor(windows, start_x, direction)
    if legacy_end is not None:
        lo = min(lo, legacy_end)
        hi = max(hi, legacy_end)
    if hi > lo:
        allow = _HEAD_LEAN_ALLOWANCE_FRAC * gh
        lo -= allow
        hi += allow
    return lo, hi


def _grasp_target(ctx, target, flank_px):
    """Grasp point for pick_up/bend_pick/kneel_pick, pulled inside
    the actor's arm reach when the prop's rest is beyond it.

    A two-hand grasp at an unreachable rest collapses: both flanked
    targets clamp to the reach circle along nearly the same ray, so
    the hands land ~11 px apart and the lift reads one-handed for
    its whole span (R6 shot #7: the stone rested on the anvil ~320
    px from the shoulder, arm reach ~155 px). Pulling the grasp
    point in along the same ray keeps the flanked targets
    reachable, so both hands arrive at the prop's edges; the prop
    state machine's APPROACHING state already glides the prop from
    its rest to the hands, so no pop appears. Reachable targets
    return unchanged (pixel-identical for ordinary pickups).
    """
    try:
        char = ctx["char"]
        joints = (ctx.get("joints0") or {}).get(ctx["name"]) or {}
        head = joints.get("head")
        hip = joints.get("hip")
        if head is None or hip is None:
            return target
        dx, dy = float(hip[0]) - float(head[0]), float(hip[1]) - float(head[1])
        spine = math.hypot(dx, dy)
        if spine <= 0:
            return target
        head_r = float(getattr(char, "head_r", 0.0) or 0.0)
        sh_x = float(head[0]) + dx / spine * head_r
        sh_y = float(head[1]) + dy / spine * head_r
        reach = float(char.u_arm) + float(char.l_arm)
        if reach <= 0:
            return target
        tx, ty = float(target[0]), float(target[1])
        rx, ry = tx - sh_x, ty - sh_y
        dist = math.hypot(rx, ry)
        flank = abs(float(flank_px)) if flank_px is not None else 0.0
        limit = 0.95 * reach - flank
        if dist <= max(limit, 0.45 * reach):
            return target
        pull = max(0.45 * reach, limit)
        return (sh_x + rx / dist * pull, sh_y + ry / dist * pull)
    except (KeyError, TypeError, ValueError, AttributeError):
        return target


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
    if hand == "both" and primitive not in _BOTH_HAND_PRIMITIVES:
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
        to_x = from_x + _LOCOMOTION_STEP_PX["walk_to"] * _walk_direction(ctx, event)
        ctx["pos"]["x"] = to_x
        return walk_to(char, from_x, to_x, dur, ground_y)
    if primitive == "run_to":
        from_x = ctx["pos"]["x"]
        to_x = from_x + _LOCOMOTION_STEP_PX["run_to"] * _walk_direction(ctx, event)
        ctx["pos"]["x"] = to_x
        return run_to(char, from_x, to_x, dur, ground_y)
    if primitive == "walk_mud":
        from_x = ctx["pos"]["x"]
        to_x = from_x + _LOCOMOTION_STEP_PX["walk_mud"] * _walk_direction(ctx, event)
        ctx["pos"]["x"] = to_x
        return walk_mud(char, from_x, to_x, dur, ground_y)
    if primitive == "idle":
        return idle(char, dur, ground_y,
                    gaze_seed=ctx.get("gaze_seed"))
    if primitive == "turn_to":
        if ctx["other_name"] in ctx["joints0"]:
            other_x = ctx["joints0"][ctx["other_name"]]["hip"][0]
            new_facing = 1 if other_x > ctx["pos"]["x"] else -1
        else:
            new_facing = -ctx["facing"]
        return turn_to(char, new_facing, dur)
    if primitive == "insert_key":
        # Round 16 (L02-D2): the hand drives the key INTO the
        # staged lock, not toward the key's own rest -- the
        # generic _target() would return the key rest, and the
        # key is already in the hand. The lock anchor is solved
        # reachable by _render_shot; without one (unit probes)
        # fall back to the generic target.
        _lock = ctx.get("lock_anchor")
        return insert_key(char, _lock if _lock else _target(),
                          dur, hand=hand)
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
    # Round-6 grip readability: the compiler's flank_px (half the
    # prop's drawn footprint + margin) reaches the flank-aware
    # primitives; absent, they keep the legacy +-12 px flank.
    _flank = params.get("flank_px")
    if primitive == "bend_pick":
        return bend_pick(char, _grasp_target(ctx, _target(), _flank),
                         dur, ground_y, hand=hand,
                         flank_px=_flank)
    if primitive == "kneel_pick":
        return kneel_pick(char, _grasp_target(ctx, _target(), _flank),
                          dur, ground_y, hand=hand,
                          flank_px=_flank)
    if primitive == "pick_up":
        if params.get("pocket"):
            target, source = _hip(), "pocket"
        else:
            target, source = _grasp_target(
                ctx, _target(), _flank), "ground"
        return pick_up(char, target, dur, ground_y, hand=hand,
                       source=source, flank_px=_flank)
    if primitive == "put_away":
        # Round-8 (R2-V1): a RELEASE onto a named surface is a
        # placement, not a pocketing -- the hand reaches to the
        # support top instead of the hip (delivered R7 shot #10:
        # Linh's hand went to her hip while the stone flew 700 px
        # to the pedestal). PUT_AWAY (pocket) keeps the hip; a
        # RELEASE whose support is not in the shot's anchors
        # falls back to the hip rather than inventing a target.
        if str(event.get("action_type", "")).upper() == "RELEASE":
            _sup = event.get("destination_support")
            _tops = ctx.get("supports") or {}
            if _sup and str(_sup) in _tops:
                _t = _tops[str(_sup)]
                return place_on_surface(
                    char, (float(_t["x"]), float(_t["top_y"])), dur,
                    hand=hand, prop=ctx["prop"])
        return put_away(char, _hip(), dur, hand=hand, prop=ctx["prop"])
    if primitive == "receive_prop":
        # The pair animation (hand_over) placed the hand at the
        # meeting point; target=None tells receive_prop the hand is
        # already there, so only the securing pull-in moves. (This
        # primitive was dead in the product path before: RECEIVE_PROP
        # windows fell back to idle and the receiver's hand froze at
        # the meeting point for the rest of the shot.)
        return receive_prop(char, None, dur, hand=hand)
    if primitive == "shield":
        # Was dead in the product path (no branch -> idle fallback):
        # SHIELD events rendered as standing still. The guard pose
        # is a held pose; the threat/target stays the script's.
        return shield(char, dur)
    if primitive == "crouch":
        # Was dead in the product path (no branch -> idle fallback).
        return crouch(char, dur, ground_y)
    if primitive == "hammer_strike":
        # Was dead in the product path (no branch -> idle fallback):
        # every forging strike rendered as standing still. The strike
        # point is the anvil surface from staging (environment-
        # projected top, or the in-front fallback); the primitive
        # guarantees hammer-head contact up to IK reach and misses
        # honestly outside it.
        _anvil = ctx.get("anvil") or {}
        _hip0 = _hip()
        _sx = _anvil.get("x", _hip0[0] + ctx["facing"] * 0.30 * char.H)
        _sy = _anvil.get("top_y", ground_y - 0.45 * char.H)
        return hammer_strike(char, (_sx, _sy), dur, ground_y,
                             hand=hand)
    if primitive == "present_prop":
        # Light-payoff pose: the prop is presented steady at chest
        # height while the renderer paints the burst on it. hand
        # "both" passes through (flanked hold); single hands present
        # one-handed.
        return present_prop(char, dur, hand=hand, flank_px=_flank)
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


# Hero prop insert grammar (RicksClips loop round 2): an
# object_insert frames the PROP, with the holder hand(s) as
# context — never the face. The subject box is sized from the
# prop's own footprint (geometry_footprint: the size _draw_prop
# actually draws), not from a fixed +-170/+-90 box that drowned
# small props and ballooned when the hand median split from the
# prop median. Hands join only inside a bounded expansion toward
# the hand median (at most one prop-box half-extent per edge), so
# a far hand can never shrink the prop by dragging the crop
# wide. The box floor keeps tiny props framing cleanly.
_INSERT_PROP_MARGIN = 1.5
_INSERT_MIN_BOX_W = 180.0
_INSERT_MIN_BOX_H = 110.0
_INSERT_HAND_HALF = 60.0


def _insert_subject_box(cx, cy, kind, hand_xy=None,
                        frame_w=1920.0, frame_h=1080.0):
    """(pseudo standing box, record fields) for one insert subject.

    The box is centred on the prop position, sized from the
    prop footprint x _INSERT_PROP_MARGIN with a floor, and
    expanded toward ``hand_xy`` by at most one prop-box
    half-extent per edge. The face is never part of this box:
    callers pass prop + hand positions only. A centre outside
    the frame (a prop staged half off-frame) is clamped to the
    frame edge: the crop can only show the visible part, and
    the record reports the clamped centre in ``cx``/``cy``.
    """
    cx = min(max(float(cx), 0.0), float(frame_w))
    cy = min(max(float(cy), 0.0), float(frame_h))
    if hand_xy is not None:
        hand_xy = (min(max(float(hand_xy[0]), 0.0), float(frame_w)),
                   min(max(float(hand_xy[1]), 0.0), float(frame_h)))
    _fw, _fh = geometry_footprint(kind)
    _bw = max(float(_fw) * _INSERT_PROP_MARGIN, _INSERT_MIN_BOX_W)
    _bh = max(float(_fh) * _INSERT_PROP_MARGIN, _INSERT_MIN_BOX_H)
    _x0, _x1 = float(cx) - _bw / 2.0, float(cx) + _bw / 2.0
    _y0, _y1 = float(cy) - _bh / 2.0, float(cy) + _bh / 2.0
    _hand_included = False
    if hand_xy is not None:
        _hx, _hy = float(hand_xy[0]), float(hand_xy[1])
        _x0 = max(min(_x0, _hx - _INSERT_HAND_HALF),
                  float(cx) - _bw)
        _x1 = min(max(_x1, _hx + _INSERT_HAND_HALF),
                  float(cx) + _bw)
        _y0 = max(min(_y0, _hy - _INSERT_HAND_HALF),
                  float(cy) - _bh)
        _y1 = min(max(_y1, _hy + _INSERT_HAND_HALF),
                  float(cy) + _bh)
        _hand_included = True
    _box = {"cx": (_x0 + _x1) / 2.0, "head_y": _y0,
            "foot_y": _y1, "half_w": (_x1 - _x0) / 2.0}
    _fields = {"prop_w": float(_fw), "prop_h": float(_fh),
               "box_w": _x1 - _x0, "box_h": _y1 - _y0,
               "hands_included": _hand_included,
               "cx": float(cx), "cy": float(cy)}
    return _box, _fields


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


def _median_bystander_heads(telemetry: list[dict]):
    """Median (name, head_x, head_y, head_r) for characters who
    never hold a drawn prop in ``telemetry``.

    Round 17 (R16-D1): the crop-level bystander exclusion needs
    every non-subject head. Holders (any draw's holder) are the
    shot's subjects -- their faces are the insert's context, and
    the holder lean already handles them. Heads come from the
    telemetry "hands" entries, which carry all characters' joints.
    """
    _holders = set()
    _heads: dict[str, list[tuple[float, float]]] = {}
    _head_rs: dict[str, list[float]] = {}
    for _entry in telemetry or []:
        for _draw in _entry.get("draws") or []:
            if _draw.get("holder"):
                _holders.add(_draw.get("holder"))
        for _nm, _jn in ((_entry.get("hands") or {}).items()):
            _hp = _jn.get("head")
            if _hp is not None:
                _heads.setdefault(_nm, []).append(
                    (float(_hp[0]), float(_hp[1])))
            _hr = _jn.get("head_r")
            if isinstance(_hr, (int, float)) and _hr > 0:
                _head_rs.setdefault(_nm, []).append(float(_hr))

    def _med(_pts):
        _xs = sorted(q[0] for q in _pts)
        _ys = sorted(q[1] for q in _pts)
        _n = len(_pts)
        return ((_xs[_n // 2] if _n % 2
                 else (_xs[_n // 2 - 1] + _xs[_n // 2]) / 2.0),
                (_ys[_n // 2] if _n % 2
                 else (_ys[_n // 2 - 1] + _ys[_n // 2]) / 2.0))

    _out = []
    for _nm, _pts in _heads.items():
        if _nm in _holders:
            continue
        _hx, _hy = _med(_pts)
        _hrs = sorted(_head_rs.get(_nm, []))
        _hr = _hrs[len(_hrs) // 2] if _hrs else 120.0
        _out.append((_nm, _hx, _hy, _hr))
    return _out


def _exclude_heads_from_crop(crop_rect, prop_xy, heads, margin,
                             frame_w, frame_h):
    """Shift ``crop_rect`` (same size) away from intruding head
    discs. The prop anchor stays inside the rect with ``margin``,
    and the rect stays inside the frame. Heads are processed
    nearest-first; each disc is pushed out in up to 4 steps, and
    the shift stops at the first head the slack cannot clear.
    Returns (new_rect, record) or (crop_rect, None) when nothing
    intrudes or no shift is possible. The shift is computed once
    from median positions, so the crop stays frozen in the shot.
    """
    _x0, _y0, _x1, _y1 = (float(v) for v in crop_rect)
    _w, _h = _x1 - _x0, _y1 - _y0
    _px, _py = float(prop_xy[0]), float(prop_xy[1])
    _shifts = []
    _cleared = []
    _remaining = []
    _step = max(24.0, 0.2 * min(_w, _h))
    for _nm, _hx, _hy, _hr in sorted(
            heads, key=lambda hd: math.hypot(
                hd[1] - _px, hd[2] - _py)):
        _done = False
        for _attempt in range(4):
            _nx = min(max(_hx, _x0), _x1)
            _ny = min(max(_hy, _y0), _y1)
            if math.hypot(_hx - _nx, _hy - _ny) >= _hr:
                _done = True
                break
            _dx, _dy = _px - _hx, _py - _hy
            _dist = math.hypot(_dx, _dy)
            if _dist <= 0.0:
                break
            _sx = _dx / _dist * _step
            _sy = _dy / _dist * _step
            # Clamp: prop inside with margin, rect inside frame.
            _sx = max(_px + margin - _x1,
                      min(_px - margin - _x0, _sx))
            _sx = max(-_x0, min(frame_w - _x1, _sx))
            _sy = max(_py + margin - _y1,
                      min(_py - margin - _y0, _sy))
            _sy = max(-_y0, min(frame_h - _y1, _sy))
            if _sx == 0.0 and _sy == 0.0:
                break
            _x0 += _sx
            _x1 += _sx
            _y0 += _sy
            _y1 += _sy
            _shifts.append({"name": _nm, "shift_x": round(_sx, 1),
                            "shift_y": round(_sy, 1)})
        if not _done:
            # The final shift may have cleared the disc; the loop
            # only checks at the top of each attempt.
            _nx = min(max(_hx, _x0), _x1)
            _ny = min(max(_hy, _y0), _y1)
            _done = math.hypot(_hx - _nx, _hy - _ny) >= _hr
        (_cleared if _done else _remaining).append(_nm)
    if not _shifts:
        return list(crop_rect), None
    _record = {"shifts": _shifts, "cleared": _cleared,
               "remaining": _remaining,
               "crop_rect": [round(_x0, 1), round(_y0, 1),
                             round(_x1, 1), round(_y1, 1)]}
    return [_x0, _y0, _x1, _y1], _record


def _deferred_insert_shot(shot, shot_events):
    """True when the shot's crop defers to the prop + hands.

    Round 21 (R20-D1): object_insert shots and extreme
    close-ups on a prop-manipulation event frame the PROP +
    HANDS (telemetry pass 2 / frame-0 insert box), never the
    room -- the anchor branches leave subjects unset for
    exactly these shots (see _defer_framing). Staging moves
    in such a shot decouple the holder's hands from a
    world-static prop, so the dressing loop must not run
    here. The ECU branch below is the single definition of
    the prop-action test; _ecu_prop_action calls this helper.
    """
    st = shot.get("shot_type")
    if st == "object_insert":
        return True
    if st != "extreme_close_up":
        return False
    return any(
        ((_ev.get("required_pose") or {}).get("primitive")
         in _PROP_ACTION_PRIMITIVES)
        and _ev.get("prop_id")
        for _ev in shot_events)


def _insert_anchor_subjects(telemetry: list[dict],
                            standing_boxes: list[dict],
                            frame_w=1920.0, frame_h=1080.0):
    """(subjects, anchor record) for the insert pass-2 freeze.

    Telemetry median when a prop was drawn; the full-body
    standing boxes (the frame-0 path's no-prop fallback) when no
    prop draw carries coordinates.

    Hero prop grammar (RicksClips loop round 2): the anchor is
    PROP-LED. The subject box comes from _insert_subject_box
    (prop footprint, bounded hand expansion) -- never from a
    standing box, so the face can never define an insert frame.
    The anchor centre comes from prop/hand PAIRS: frames where
    the dominant prop is held (a draw with a holder + hand).
    Pair medians sit at the hold/interaction phase for
    travelling props, where the old independent medians split
    (prop low, hand high) and ballooned the union box until
    safe_frame stepped the scale down and the prop shrank.
    Holderless props (resting, no hand) fall back to the median
    of all draws of the dominant kind.
    """
    _median = _insert_anchor_from_telemetry(telemetry)
    if _median is not None:
        _ax, _ay, _akind, _an = _median
        _pairs: list[tuple[tuple[float, float],
                           tuple[float, float]]] = []
        _heads: list[tuple[float, float]] = []
        _head_rs: list[float] = []
        for _entry in telemetry or []:
            _h = _entry.get("hands") or {}
            for _draw in _entry.get("draws") or []:
                if _draw.get("kind") != _akind:
                    continue
                _dx, _dy = _draw.get("x"), _draw.get("y")
                if not isinstance(_dx, (int, float)):
                    continue
                if not isinstance(_dy, (int, float)):
                    continue
                _holder = _draw.get("holder")
                _hand = _draw.get("hand")
                _joints = _h.get(_holder) if _holder else None
                if not _joints or _hand not in ("l", "r", "both"):
                    continue
                if _hand == "both":
                    _pl = _joints.get("hand_l")
                    _pr = _joints.get("hand_r")
                    if _pl is None or _pr is None:
                        continue
                    _pt = ((_pl[0] + _pr[0]) / 2.0,
                           (_pl[1] + _pr[1]) / 2.0)
                else:
                    _pt = _joints.get("hand_" + _hand)
                if _pt is not None:
                    _pairs.append(((float(_dx), float(_dy)),
                                   (float(_pt[0]), float(_pt[1]))))
                    _hp = _joints.get("head")
                    if _hp is not None:
                        _heads.append((float(_hp[0]),
                                       float(_hp[1])))
                    _hr = _joints.get("head_r")
                    if isinstance(_hr, (int, float)) and _hr > 0:
                        _head_rs.append(float(_hr))

        def _median_pt(_pts):
            _xs = sorted(p[0] for p in _pts)
            _ys = sorted(p[1] for p in _pts)
            _n = len(_pts)
            return ((_xs[_n // 2] if _n % 2
                     else (_xs[_n // 2 - 1] + _xs[_n // 2]) / 2.0),
                    (_ys[_n // 2] if _n % 2
                     else (_ys[_n // 2 - 1] + _ys[_n // 2]) / 2.0))

        _hand_xy = None
        _pair_anchored = False
        if _pairs:
            _ax, _ay = _median_pt([p[0] for p in _pairs])
            _hand_xy = _median_pt([p[1] for p in _pairs])
            _pair_anchored = True
        _raw_x, _raw_y = _ax, _ay
        _box, _fields = _insert_subject_box(
            _ax, _ay, _akind, _hand_xy, frame_w, frame_h)
        # Head lean: when the holder's head sits close to the
        # prop (a bowed writing pose), a prop-centred crop is
        # dominated by the face -- the exact defect Mai flagged.
        # Translate the framing box AWAY from the head so the
        # crop leans toward the prop + hands and the head slides
        # toward (or out of) the frame edge. The shift is capped
        # per axis so the prop always stays inside the box with
        # margin; the anchor point (the prop) does not move.
        _lean = None
        if _heads and _pair_anchored:
            _hx, _hy = _median_pt(_heads)
            _hr = (sorted(_head_rs)[len(_head_rs) // 2]
                   if _head_rs else 120.0)
            _dxh, _dyh = _ax - _hx, _ay - _hy
            _dist = math.hypot(_dxh, _dyh)
            if 0.0 < _dist < 2.0 * _hr:
                _hw = _fields["box_w"] / 2.0
                _hh = _fields["box_h"] / 2.0
                _mag = 0.75 * min(_hw, _hh)
                _cap_x = max(0.0, _hw
                             - _fields["prop_w"] / 2.0 - 8.0)
                _cap_y = max(0.0, _hh
                             - _fields["prop_h"] / 2.0 - 8.0)
                _sx = max(-_cap_x, min(
                    _cap_x, _dxh / _dist * _mag))
                _sy = max(-_cap_y, min(
                    _cap_y, _dyh / _dist * _mag))
                if _sx != 0.0 or _sy != 0.0:
                    _box = {"cx": _box["cx"] + _sx,
                            "head_y": _box["head_y"] + _sy,
                            "foot_y": _box["foot_y"] + _sy,
                            "half_w": _box["half_w"]}
                    _lean = {"head_x": _hx, "head_y": _hy,
                             "head_r": _hr,
                             "shift_x": _sx, "shift_y": _sy}
        _record = {"source": "telemetry_median", "kind": _akind,
                   "x": _fields["cx"], "y": _fields["cy"],
                   "n_draws": _an,
                   "n_hands": len(_pairs),
                   "pair_anchored": _pair_anchored,
                   "n_pairs": len(_pairs)}
        if (_fields["cx"], _fields["cy"]) != (_raw_x, _raw_y):
            _record.update({"clamped_to_frame": True,
                            "raw_x": _raw_x, "raw_y": _raw_y})
        if _lean is not None:
            _record["lean"] = _lean
        _record.update(_fields)
        if _hand_xy is not None:
            _record.update({"hand_x": _hand_xy[0],
                            "hand_y": _hand_xy[1]})
        return ([_box], _record)
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


# Radius (staging px) around a glow source that stays lit even
# where a character's limbs pass: the glowing prop itself must
# read, and the flesh touching it catches the light. Beyond the
# hole the limb-segment exclusions keep the cast unwashed.
GLOW_SOURCE_HOLE_STAGING_PX = 46.0


def _glow_exclusion_boxes(joints_by_name, names, crop_rect,
                          frame_size):
    """Screen-space rects covering the cast's posed limbs.

    Round-7: the static standing box (round 6, R2-F1) covered
    the whole insert crop whenever the holder stood AT the prop,
    erasing the prop's own halo. The posed joints follow the
    actual limbs, so the glow spills around the cast instead of
    over them -- and the prop between the limbs stays lit.
    Segments: torso (head->hip, shirt half-width), arms
    (shoulder->elbow->hand), legs (hip->knee->foot), plus the
    head disc. Margins derive from the body scale in the
    telemetry (limb width 0.026*H, shirt half-width ~0.05*H).
    Joints missing from a frame's telemetry skip that segment.
    """
    x0, y0, _x1, _y1 = (float(v) for v in crop_rect)
    fw, fh = (float(v) for v in frame_size)
    zx = fw / max(_x1 - x0, 1.0)
    zy = fh / max(_y1 - y0, 1.0)
    boxes = []
    for name in names:
        joints = joints_by_name.get(name)
        if not isinstance(joints, dict):
            continue
        h = float(joints.get("H") or 0.0)
        limb_m = 0.013 * h + 4.0
        torso_m = 0.05 * h + 4.0
        segments = [
            ("head", "hip", torso_m),
            ("shoulder", "elbow_l", limb_m),
            ("elbow_l", "hand_l", limb_m),
            ("shoulder", "elbow_r", limb_m),
            ("elbow_r", "hand_r", limb_m),
            ("hip", "knee_l", limb_m),
            ("knee_l", "foot_l", limb_m),
            ("hip", "knee_r", limb_m),
            ("knee_r", "foot_r", limb_m),
        ]
        for a_key, b_key, margin in segments:
            a = joints.get(a_key)
            b = joints.get(b_key)
            if a is None or b is None:
                continue
            ax, ay = float(a[0]), float(a[1])
            bx, by = float(b[0]), float(b[1])
            boxes.append((
                (min(ax, bx) - margin - x0) * zx,
                (min(ay, by) - margin - y0) * zy,
                (max(ax, bx) + margin - x0) * zx,
                (max(ay, by) + margin - y0) * zy))
        head = joints.get("head")
        head_r = float(joints.get("head_r") or 0.0)
        if head is not None and head_r > 0:
            hx, hy = float(head[0]), float(head[1])
            boxes.append((
                (hx - head_r - x0) * zx,
                (hy - head_r - y0) * zy,
                (hx + head_r - x0) * zx,
                (hy + head_r - y0) * zy))
    return boxes


def _anchor_tier_for_shot(shot_events, shot) -> str:
    """Framing anchor tier: "head" (face only), "head_hands"
    (head -> waist, hand-level interactions stay in frame), or
    "full" (ground-level actions: the whole body + ground contact
    stay in frame). Ground wins over hand. Compiled verbs are
    authoritative; cue names are consulted only when the shot has
    no compiled events in its span (a discarded cue stages nothing
    and must not widen the frame)."""
    verbs = {str(e.get("action_type", "")).upper()
             for e in shot_events or []}
    if verbs & _ANCHOR_GROUND_VERBS:
        return "full"
    if verbs & _ANCHOR_HAND_VERBS:
        return "head_hands"
    if verbs:
        return "head"
    cues = {str(c).lower() for c in (shot.get("action_cues") or [])}
    if cues & _ANCHOR_GROUND_CUES:
        return "full"
    if cues & _ANCHOR_HAND_CUES:
        return "head_hands"
    return "head"


def _shot_has_locomotion(shot_events, shot) -> bool:
    """True when the shot stages horizontal travel (walk/run/march/
    board/climb). Compiled verbs decide; cue names are consulted
    only when the shot has no compiled events in its span."""
    verbs = {str(e.get("action_type", "")).upper()
             for e in shot_events or []}
    if verbs:
        return bool(verbs & _LOCOMOTION_VERBS)
    cues = {str(c).lower() for c in (shot.get("action_cues") or [])}
    return bool(cues & _LOCOMOTION_CUES)


# Top-accessory extents above the head circle, as fractions of the
# head radius, measured from the draw code (character_art): the hat
# dome tops at hy-1.75r, the tied bun at hy-1.34r, a crown at
# top-0.34r, antlers at top-0.24r, a tuft at hy-1.22r, small/curved
# horns at top-0.18r/0.14r. The hair cap follows the head circle
# exactly (0). A character's margin is the max of what they wear.
_TOP_ACCESSORY_FRAC = {
    "hat": 0.75,
    "tied": 0.34,
    "crown": 0.34,
    "antlers": 0.24,
    "tuft": 0.22,
    "horns_small": 0.18,
    "horns_curved": 0.14,
}


def _trait_value(char, key):
    """One trait value from a character dict OR a Stickman: dicts
    read ``.get`` (falling back to ``visual_profile`` for horns /
    ears / tails, the way ``map_character`` resolves them),
    objects read ``getattr`` with the same fallback."""
    if isinstance(char, dict):
        value = char.get(key)
        if value is None:
            profile = char.get("visual_profile")
            if isinstance(profile, dict):
                value = profile.get(key)
        return value
    value = getattr(char, key, None)
    if value is None:
        profile = getattr(char, "visual_profile", None)
        if isinstance(profile, dict):
            value = profile.get(key)
    return value


def _top_accessory_frac(char) -> float:
    """Fraction of the head radius a character's top accessories
    extend above the head circle (0 when nothing sticks up).

    Round 9 (R8 residual): the standing box topped exactly at the
    head circle, so Linh's bun (~0.34r) nearly touched the frame
    top in shot #3 (~5 px headroom) and Bé Nam's hat dome (0.75r)
    could clip in tight framings. The framing box must cover the
    drawn silhouette, not just the head circle. Accepts a package
    character dict or a Stickman (the camera fit runs before the
    Stickmen are built)."""
    frac = 0.0
    hat = _trait_value(char, "hat")
    if hat and hat != "none":
        frac = max(frac, _TOP_ACCESSORY_FRAC["hat"])
    hair = _trait_value(char, "hair_style")
    if hair in ("tied", "tuft"):
        frac = max(frac, _TOP_ACCESSORY_FRAC[hair])
    horns = _trait_value(char, "horns") or "none"
    if horns == "crown":
        frac = max(frac, _TOP_ACCESSORY_FRAC["crown"])
    elif horns == "antlers":
        frac = max(frac, _TOP_ACCESSORY_FRAC["antlers"])
    elif horns == "small":
        frac = max(frac, _TOP_ACCESSORY_FRAC["horns_small"])
    elif horns == "curved":
        frac = max(frac, _TOP_ACCESSORY_FRAC["horns_curved"])
    return frac


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
    # D2 (RicksClips loop round 1): a full-frame map background
    # has no ground plane -- no character is staged on it. The
    # predicate calls the same selection build_environment uses
    # (select_archetype -> _select_archetype_detail), so it agrees
    # with the scene build's _is_map by construction. The map shot
    # is a graphic insert; the character-free scene-2 behaviour
    # becomes the rule for every map shot.
    _v1_loc = shot.get("v1_location")
    _shot_is_map = (isinstance(_v1_loc, dict)
                    and select_archetype(_v1_loc)[0] == "MAP")
    _visible = shot.get("visible")
    if _visible is None:
        _visible = [str(c["name"]) for c in package["characters"]]
    _costume_overrides = shot.get("costume_overrides") or {}
    _char_by_name = {str(c["name"]): (i, c)
                     for i, c in enumerate(package["characters"])}
    names = [n for n in _char_by_name if n in _visible]
    _map_suppressed = _shot_is_map and len(names) > 0
    if _shot_is_map:
        names = []
    # Resting faces (V1 DEFAULT_EXPRESSION, verbatim script text):
    # a character with no shot expression or keyframe renders their
    # declared default instead of "neutral" for everyone. The whole
    # string interprets position-ordered, so "Caring, worried,
    # determined" resolves to the first mappable emotion (worried);
    # an unmappable default stays None -> neutral. Legacy packages
    # without the field are unaffected.
    _default_expr: dict[str, str | None] = {}
    for _n in names:
        _dflt = str(_char_by_name[_n][1].get("default_expression")
                    or "")
        _default_expr[_n] = interpret_expression(_dflt) \
            if _dflt else None
    speaker = shot.get("speaker")
    # Round-7 listener mirroring: the speaker's resolved
    # expression name, computed once per shot. Listeners with
    # no declared resting face mirror it at half strength (see
    # the per-frame listener branch); a neutral speaker mirrors
    # to neutral, so neutral shots render unchanged.
    _speaker_expr_name = None
    if speaker and speaker in names:
        _slabel = shot.get("expression")
        _sinterp = interpret_expression(_slabel) if _slabel else None
        _speaker_expr_name = (
            _sinterp if _sinterp in EXPRESSION_NAMES
            else resolve_expression(_slabel, shot.get("text", "")))
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
    # Round 8 (R4-A5): micro-saccade seeds, one per character per
    # RENDERED shot -- the same seed-base scheme as the ambient
    # blink schedules (directive + index + start_sec), with a
    # distinct domain tag so gaze phases never correlate with
    # blink times. Gaze wander is a pure function of (t, seed),
    # so the seeds are computed once here and read per frame.
    _gaze_seed_base = "{}:{}:{}".format(
        shot.get("directive_shot_id"), shot.get("index", ""),
        shot.get("start_sec", 0.0))
    _gaze_seeds = {}
    for _c in package.get("characters") or []:
        _nm = str(_c.get("name") or "")
        if _nm:
            _gaze_seeds[_nm] = zlib.crc32(
                f"gaze:{_gaze_seed_base}:{_nm}".encode("utf-8")) \
                & 0x7FFFFFFF
    _furniture_staging: dict[str, tuple] = {}
    _seated_at_start: dict[str, bool] = {}
    _compiled_all = (package.get("compiled_actions") or {}).get(
        "events") or []
    # Round 16 (L02-D8): POSE_HELD body poses carried across the
    # segment/cut boundary within a scene (a sit_down persists into
    # later segments of the same directive shot and later shots of
    # the scene until the character stands, walks, or sits at a
    # desk). All staged characters, not just the shot's actor.
    _held_at_start = _held_poses_at_start(
        _compiled_all, shot.get("scene"), _t0, _id_to_name)
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
    # ---- Round-5 striker staging: HAMMER_STRIKE actors stand AT
    # the anvil. Before this, the striker stayed on the character
    # plane while the anvil sat ~3 units behind it, so every strike
    # hit air ~2 m from the anvil in screen space while the
    # contact audit passed (the primitive clamps to arm reach and
    # "misses honestly"). Same pattern as the furniture staging
    # above: the anvil element's world position comes from the
    # deterministic environment package; the striker stages beside
    # it (0.9 units, staying on their current side) at the anvil's
    # depth, facing the anvil. No anvil element -> no staging
    # change, never an invented anvil. The strike point itself
    # (ctx["anvil"]) is unchanged -- it already anchors to the
    # environment anvil; only the striker's position was wrong.
    _anvil_staging: dict[str, tuple] = {}
    _striker_names = [
        _n for _n in names
        if any(((e.get("required_pose") or {}).get("primitive")
                == "hammer_strike")
               for _s, _e, e in _per_actor.get(_n, []))]
    if _striker_names and isinstance(shot.get("v1_location"), dict):
        _anvil_pkg = None
        try:
            _anvil_pkg = build_environment(
                shot["v1_location"],
                time_of_day=shot.get("time_of_day", "day"),
                style={"mood": shot.get("mood", "warm")})
        except Exception:
            _anvil_pkg = None
        if _anvil_pkg is not None:
            _anvil_el = None
            for _el in _anvil_pkg.get("elements") or []:
                if _el.get("id") == "anvil_top":
                    _anvil_el = _el
                    break
                if _anvil_el is None and _el.get("kind") == "anvil":
                    _anvil_el = _el
            if _anvil_el is not None:
                _ax, _ay, _az = _anvil_el["center"]
                for _n in _striker_names:
                    _side = -1.0 if world_xs[_n] <= float(_ax) else 1.0
                    _sx = float(_ax) + _side * 0.9
                    world_xs[_n] = _sx
                    world_zs[_n] = float(_az)
                    _anvil_staging[_n] = (_sx, float(_az), _side)
    # ---- pick staging (round 8, R2-A3 lift half) --------------------
    # Same defect family as the striker staging: an actor who picks
    # a prop off a support must stand AT that support, or the grasp
    # point is pulled inside arm reach (face height) and the stone
    # glides 245 px across the screen and sinks to the waist instead
    # of rising off the surface. The support is the one the shot's
    # own events name for the picked prop (the take's source_support,
    # or a same-shot placement's destination_support -- the same
    # precedence _assign_prop_rests uses), matched against an
    # environment element; no named support or no matching element
    # -> no staging change, never an invented support. Ground and
    # pocket pickups stage nothing. Pickers are anchored like
    # strikers (staging fit, clearance and head clearance never
    # move them) and face the support.
    _pick_staging: dict[str, tuple] = {}
    _PICK_PRIMITIVES = ("pick_up", "bend_pick", "kneel_pick")
    _pick_events: list[tuple[str, dict]] = []
    for _n in names:
        for _s, _e, _ev in _per_actor.get(_n, []):
            _pose = _ev.get("required_pose") or {}
            if _pose.get("primitive") in _PICK_PRIMITIVES \
                    and not (_pose.get("params") or {}).get("pocket"):
                _pick_events.append((_n, _ev))
    if _pick_events and isinstance(shot.get("v1_location"), dict):
        _pick_pkg = None
        try:
            _pick_pkg = build_environment(
                shot["v1_location"],
                time_of_day=shot.get("time_of_day", "day"),
                style={"mood": shot.get("mood", "warm")})
        except Exception:
            _pick_pkg = None
        if _pick_pkg is not None:
            _named_support: dict[str, str] = {}
            for _e in _shot_events:
                _pid = _e.get("prop_id")
                if _pid and _e.get("source_support"):
                    _named_support[str(_pid)] = _e["source_support"]
            for _e in _shot_events:
                _pid = _e.get("prop_id")
                if _pid and _e.get("destination_support"):
                    _named_support[str(_pid)] = \
                        _e["destination_support"]
            for _n, _ev in _pick_events:
                _pid = _ev.get("prop_id")
                _sup = _named_support.get(str(_pid)) if _pid else None
                if not _sup or _n in _pick_staging:
                    continue
                _sup_el = None
                for _el in _pick_pkg.get("elements") or []:
                    _eid = str(_el.get("id") or "")
                    _ekind = str(_el.get("kind") or "")
                    if _eid == _sup or _ekind == _sup \
                            or _eid == f"{_sup}_top" \
                            or _ekind == f"statue_{_sup}" \
                            or (_sup == "table" and _ekind in (
                                "desk", "workbench", "table")):
                        _sup_el = _el
                        break
                if _sup_el is None:
                    continue
                _ax, _ay, _az = _sup_el["center"]
                _side = -1.0 if world_xs[_n] <= float(_ax) else 1.0
                _sx = float(_ax) + _side * 0.9
                world_xs[_n] = _sx
                world_zs[_n] = float(_az)
                _pick_staging[_n] = (_sx, float(_az), _side)
    # NOTE (Round-8): place staging lives AFTER the viewpoint
    # resolution (below, next to the shield pass): staging the
    # placer beside a support needs the shot camera -- a
    # world-space offset breaks across the depth gap between the
    # placer and a far support (the pedestal at z -8.5 staged
    # Linh as a giant at the frame top).
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
    # Round-11 establishing elevation cap (R10-D1): a steep
    # requested angle on an establishing shot pitches the whole
    # frustum below the horizon -- Loop-01 #1/#5 rendered 0 px of
    # sky (high_angle 32 deg against the 46 deg fov). An
    # establishing shot must show the place and the sky, so the
    # EXECUTED elevation is capped at ESTABLISHING_MAX_ELEV_DEG
    # (15 deg: ~260 px sky band, clouds fully in frame, still
    # elevated). Only the elevation is capped; azimuth and radius
    # still apply, and the requested angle is recorded on the
    # report (camera_angle_requested), never silently dropped.
    # The map frontal rule above takes precedence (it already
    # forces eye_level). Other shot types are untouched: a steep
    # angle on a reaction or close-up frames a subject, not a
    # place. The fit calls below receive the same executed
    # elevation so they measure the camera that will render.
    _exec_elev = None
    _elev_capped = False
    _requested_elev = None
    if shot["shot_type"] == "establishing" and not _map_frontal:
        _requested_elev = elevation_for_angle(_angle)
        # Round 14 (Loop-02 pre-render catch): an explicitly
        # requested birds_eye is EXEMPT. No shot type defaults
        # to birds_eye, so a resolved birds_eye is always the
        # script asking for a top-down view -- and the cap's
        # rationale (an establishing shot must show the place
        # AND the sky) does not apply to a view that deliberately
        # looks down. Capping it to 15 deg flattened Loop-02's
        # flagship diversity angle into a mildly elevated wide.
        if _requested_elev > ESTABLISHING_MAX_ELEV_DEG \
                and _angle != "birds_eye":
            _exec_elev = ESTABLISHING_MAX_ELEV_DEG
            _elev_capped = True
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
        [char_scales[n] for n in names],
        top_fracs=[_top_accessory_frac(_char_by_name[n][1])
                   if _char_by_name.get(n) else 0.0 for n in names],
        elevation_deg=_exec_elev)
    shot_cam = viewpoint_for_shot(
        shot["shot_type"], _angle,
        subject_pos=(_target_x, 1.2, _target_z),
        counterpart_x=_counterpart_x, srs_side=shot.get("srs_side", 0),
        radius_scale=_radius_scale,
        azimuth_side=shot.get("viewpoint_azimuth_side"),
        elevation_deg=_exec_elev)
    # R16-2a: the character elevation projection uses the
    # EXECUTED elevation -- the same elevation the
    # environment camera renders with (the establishing cap
    # and map-frontal rules already folded into _exec_elev
    # / _angle above).
    _char_elev_deg = (_exec_elev if _exec_elev is not None
                      else elevation_for_angle(_angle))
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
    # ---- Round-7 shield staging: the protected character hides
    # behind the shielder. "Behind" is measured along the shot
    # camera's view axis (a bare world-z push lands sideways under
    # an azimuth camera -- the first version put Bé Nam at the
    # frame edge). The protected figure stages 0.8 units behind
    # the shielder along the camera forward and 0.45 units to the
    # side toward frame centre, so they peek from behind the
    # shielder's shoulder with the shield between them and the
    # threat instead of being fully occluded. This runs AFTER the
    # OTS fit (the shielder's final x) and BEFORE the staging fit.
    # Shield-staged characters are anchored (exempt from the
    # staging fit and the clearance push): the overlap IS the
    # staging, not a collision to resolve.
    _shield_staging: dict[str, tuple] = {}
    _shield_disc_align: dict[str, dict] = {}
    _fwd_x = shot_cam.target[0] - shot_cam.position[0]
    _fwd_z = shot_cam.target[2] - shot_cam.position[2]
    _fwd_len = math.hypot(_fwd_x, _fwd_z) or 1.0
    _fwd_x, _fwd_z = _fwd_x / _fwd_len, _fwd_z / _fwd_len
    _right_x, _right_z = -_fwd_z, _fwd_x
    for _e in _shot_events:
        if str(_e.get("action_type", "")).upper() != "SHIELD":
            continue
        _actor = _id_to_name.get(str(_e.get("actor_id") or ""))
        _prot = _id_to_name.get(str(_e.get("target_id") or ""))
        if (_actor not in world_xs or _prot not in world_xs
                or _prot == _actor):
            continue
        _ax, _az = world_xs[_actor], world_zs[_actor]
        # Round-8 (R7-D3): align the protected figure with the
        # SHIELD DISC from the camera's view, not just with the
        # shielder's body. The disc sits at the guard hand: the
        # primitive's guard target is chest_x + facing * 110
        # (scaled), both hands stacked at that x. The R7 staging
        # (fwd 0.8 + side 0.45) left Be Nam 82 px left of the disc
        # centre in the delivered OTS shot -- beside the disc,
        # tucking behind the shoulder. Binary-search the lateral
        # offset along the camera-right axis for the protected
        # figure's projected cx == the guard x (depth unchanged:
        # the figure stays behind the shielder). The search is
        # bounded to 1.2 m about the shielder and keeps the
        # closest candidate when the disc x is unreachable.
        _acx, _, _agh = char_metrics(
            shot_cam, _ax, _az, base_scale=char_scales[_actor])
        _other_n = next(
            (n for n in names if n != _actor and n != _prot), None)
        if _other_n is not None:
            _ocx, _, _ = char_metrics(
                shot_cam, world_xs[_other_n], world_zs[_other_n],
                base_scale=char_scales[_other_n])
            _sfacing = 1.0 if _ocx > _acx else -1.0
        else:
            _sfacing = 1.0 if W / 2.0 > _acx else -1.0
        _guard_x = _acx + _sfacing * 110.0 * _agh / 560.0
        _lo, _hi = -1.2, 1.2
        _best_lat = None
        for _ in range(14):
            _mid = (_lo + _hi) / 2.0
            _tx = _ax + _fwd_x * 0.8 + _right_x * _mid
            _tz = _az + _fwd_z * 0.8 + _right_z * _mid
            _gx, _, _ = char_metrics(
                shot_cam, _tx, _tz,
                base_scale=char_scales[_prot])
            if _best_lat is None or abs(_gx - _guard_x) < _best_lat[0]:
                _best_lat = (abs(_gx - _guard_x), _tx, _tz, _mid, _gx)
            if _gx < _guard_x:
                _lo = _mid
            else:
                _hi = _mid
        _, _px, _pz, _plat, _pgx = _best_lat
        _pside = 1.0 if _plat >= 0.0 else -1.0
        world_xs[_prot] = _px
        world_zs[_prot] = _pz
        _shield_staging[_prot] = (_px, _pz, _pside)
        _shield_disc_align[_prot] = {
            "disc_x": round(_guard_x, 1),
            "protected_cx": round(_pgx, 1),
            "residual_px": round(abs(_pgx - _guard_x), 1)}
    # Round-8 (R2-V1): place staging, in SCREEN space. The mirror
    # of pick staging for RELEASE (PLACE_ON_SURFACE) beats: the
    # placing actor stages beside the NAMED destination support
    # so the hand travels to the surface and the release glide is
    # a short set-down, not a 700 px teleport (delivered R7 shot
    # #10). A world-space offset breaks across the depth gap: the
    # pedestal at z -8.5 staged Linh as a giant (copying its z)
    # or 600 px away (keeping her z with a 0.9 world offset).
    # Instead the placer's projected cx is solved onto a target
    # beside the support's projected box, moving along the
    # camera-right axis (depth preserved, screen-x monotonic).
    # Only RELEASE events with a destination_support stage;
    # PUT_AWAY (pocket) stages nothing; a character who also
    # picks in this shot keeps the pick staging. The support must
    # match a real environment element. Placers are anchored like
    # pickers and face the support. The projected support boxes
    # are shared with the sightline pass below.
    _place_staging: dict[str, tuple] = {}
    _place_supports: dict[str, dict] = {}
    _place_events: list[tuple[str, dict]] = []
    for _n in names:
        for _s, _e, _ev in _per_actor.get(_n, []):
            if str(_ev.get("action_type", "")).upper() == "RELEASE" \
                    and _ev.get("destination_support"):
                _place_events.append((_n, _ev))
    if _place_events and isinstance(shot.get("v1_location"), dict):
        _place_pkg = None
        try:
            _place_pkg = build_environment(
                shot["v1_location"],
                time_of_day=shot.get("time_of_day", "day"),
                style={"mood": shot.get("mood", "warm")})
        except Exception:
            _place_pkg = None
        if _place_pkg is not None:
            for _n, _ev in _place_events:
                _sup = str(_ev.get("destination_support"))
                if _sup in _place_supports:
                    continue
                _sup_el = None
                for _el in _place_pkg.get("elements") or []:
                    _eid = str(_el.get("id") or "")
                    _ekind = str(_el.get("kind") or "")
                    if _eid == _sup or _ekind == _sup \
                            or _eid == f"{_sup}_top" \
                            or _ekind == f"statue_{_sup}" \
                            or (_sup == "table" and _ekind in (
                                "desk", "workbench", "table")):
                        _sup_el = _el
                        break
                if _sup_el is None:
                    continue
                _scx, _scy, _scz = (float(v)
                                    for v in _sup_el["center"])
                _ssx, _ssy, _ssz = (float(v)
                                    for v in _sup_el["size"])
                _corners = []
                for _dx in (-_ssx / 2.0, _ssx / 2.0):
                    for _dy in (-_ssy / 2.0, _ssy / 2.0):
                        for _dz in (-_ssz / 2.0, _ssz / 2.0):
                            _px, _py, _, _vis = shot_cam.project(
                                (_scx + _dx, _scy + _dy, _scz + _dz),
                                W, H)
                            if _vis:
                                _corners.append((_px, _py))
                if len(_corners) < 4:
                    continue
                _l = min(c[0] for c in _corners)
                _r = max(c[0] for c in _corners)
                _place_supports[_sup] = {
                    "l": _l, "r": _r,
                    "t": min(c[1] for c in _corners),
                    "b": max(c[1] for c in _corners),
                    "cx": (_l + _r) / 2.0,
                    "depth": ((_scx - shot_cam.position[0]) * _fwd_x
                              + (_scz - shot_cam.position[2])
                              * _fwd_z)}
            for _n, _ev in _place_events:
                if _n in _place_staging or _n in _pick_staging:
                    continue
                _box = _place_supports.get(
                    str(_ev.get("destination_support")))
                if _box is None:
                    continue
                _wx, _wz = world_xs[_n], world_zs[_n]
                _cx0, _, _gh0 = char_metrics(
                    shot_cam, _wx, _wz,
                    base_scale=char_scales[_n])
                _hw0 = max(0.17 * _gh0 + 20.0, 0.15 * _gh0)
                _side = -1.0 if _cx0 <= _box["cx"] else 1.0
                _target = _box["cx"] + _side * (
                    (_box["r"] - _box["l"]) / 2.0 + _hw0 + 30.0)
                _lo, _hi = -3.0, 3.0
                _best = None
                for _ in range(14):
                    _mid = (_lo + _hi) / 2.0
                    _tx = _wx + _right_x * _mid
                    _tz = _wz + _right_z * _mid
                    _gx, _, _ = char_metrics(
                        shot_cam, _tx, _tz,
                        base_scale=char_scales[_n])
                    if _best is None \
                            or abs(_gx - _target) < _best[0]:
                        _best = (abs(_gx - _target), _tx, _tz)
                    if _gx < _target:
                        _lo = _mid
                    else:
                        _hi = _mid
                _, _px, _pz = _best
                world_xs[_n] = _px
                world_zs[_n] = _pz
                _place_staging[_n] = (_px, _pz, _side)
    # Round-8 (R2-V1): support sightline clearance. In a
    # placement shot the support (pedestal, table, anvil) is the
    # visual target; a bystander standing between the camera and
    # the support hides the placement (delivered R7 shot #10:
    # Ong Ba covered the pedestal, so the stone's arrival was
    # invisible). Bystanders whose projected standing box
    # overlaps the support's projected box -- and who stand in
    # front of the support -- are pushed laterally away from the
    # support's screen centre until clear. The placing actor is
    # exempt (staged beside the support), as are all set-piece
    # anchors and shield-staged figures. The support itself never
    # moves (continuity: it is world-anchored across shots). OTS
    # shots skip: the foreground listener IS the composition.
    _sightline_moved: dict[str, dict] = {}
    _sightline_skipped = None
    if _place_staging and _place_supports \
            and shot.get("shot_type") != "over_the_shoulder":
        for _sup in sorted(_place_supports):
            _box = _place_supports[_sup]
            _sup_l = _box["l"]
            _sup_r = _box["r"]
            _sup_t = _box["t"]
            _sup_b = _box["b"]
            _sup_cx = _box["cx"]
            _sup_depth = _box["depth"]
            # Round-8: the obstacle is the support UNION the
            # placers' boxes. Clearing only the support left the
            # bystander standing on top of the placer (probe: Ong
            # Ba's head covered Linh's face -- both exempt from
            # the head-clearance pass, so nothing separated
            # them). The bystander must clear the whole
            # placement group.
            _ob_l, _ob_r = _sup_l, _sup_r
            _ob_t, _ob_b = _sup_t, _sup_b
            for _pn in _place_staging:
                _pgx, _pgy, _pgh = char_metrics(
                    shot_cam, world_xs[_pn], world_zs[_pn],
                    base_scale=char_scales[_pn])
                _phw = max(0.17 * _pgh + 20.0, 0.15 * _pgh)
                _ob_l = min(_ob_l, _pgx - _phw)
                _ob_r = max(_ob_r, _pgx + _phw)
                _ob_t = min(_ob_t, _pgy - _pgh)
                _ob_b = max(_ob_b, _pgy)
            _ob_cx = (_ob_l + _ob_r) / 2.0
            _exempt = (set(_anvil_staging)
                       | set(_furniture_staging)
                       | set(_shield_staging)
                       | set(_pick_staging)
                       | set(_place_staging))
            for _n in names:
                if _n in _exempt or _n in _sightline_moved:
                    continue
                _depth = ((world_xs[_n] - shot_cam.position[0])
                          * _fwd_x
                          + (world_zs[_n] - shot_cam.position[2])
                          * _fwd_z)
                if _depth >= _sup_depth - 0.3:
                    continue  # behind the support: no occlusion
                _gx, _gy, _gh = char_metrics(
                    shot_cam, world_xs[_n], world_zs[_n],
                    base_scale=char_scales[_n])
                _hw = max(0.17 * _gh + 20.0, 0.15 * _gh)
                if _gx + _hw < _ob_l or _gx - _hw > _ob_r \
                        or _gy - _gh > _ob_b or _gy < _ob_t:
                    continue  # no box overlap: sightline clear
                _dir = 1.0 if _gx >= _ob_cx else -1.0
                _ox = world_xs[_n]
                _steps = 0
                _blocked = False
                for _step in range(40):
                    _nx = world_xs[_n] + _dir * 0.1
                    _ngx, _ngy, _ngh = char_metrics(
                        shot_cam, _nx, world_zs[_n],
                        base_scale=char_scales[_n])
                    _nhw = max(0.17 * _ngh + 20.0, 0.15 * _ngh)
                    if _ngx - _nhw < 40.0 \
                            or _ngx + _nhw > W - 40.0:
                        _blocked = True
                        break
                    world_xs[_n] = _nx
                    _steps += 1
                    if _ngx + _nhw < _ob_l \
                            or _ngx - _nhw > _ob_r:
                        break
                _sightline_moved[_n] = {
                    "steps": _steps,
                    "moved_world": round(
                        abs(world_xs[_n] - _ox), 3),
                    "cleared": _steps > 0 and not _blocked,
                    "margin_blocked": _blocked,
                    "support": _sup}
    elif _place_staging:
        _sightline_skipped = "over_the_shoulder"
    # Round-6 staging fit: the fixed STAGING_X slots can project
    # a character fully outside the frame under an azimuth camera
    # (the 3rd slot at 2.6 m landed at cx 2473 in a 1920 frame, so
    # a SHIELD beat's protected figure never appeared even though
    # the planner staged them -- staging, not the crop, was the
    # defect: the crop was already the full frame). Compress every
    # staged offset from the camera target's x by 0.9 per step
    # until all projected standing boxes fit horizontally (40 px
    # margin). Scaling about the target preserves left-right
    # order and keeps the subject fixed; shots that already fit
    # take 0 steps and are pixel-identical. Set-piece-anchored
    # characters (anvil strikers, furniture-seated) are exempt:
    # their x is bound to a visible set piece, and moving them
    # would break the contact the anchor exists for.
    _staging_fit_steps = 0
    _anchored = (set(_anvil_staging) | set(_furniture_staging)
                 | set(_shield_staging) | set(_pick_staging)
                 | set(_place_staging) | set(_sightline_moved))
    _fittable = [n for n in names if n not in _anchored]
    for _step in range(24):
        _all_fit = True
        for _n in _fittable:
            _gx, _gy, _gh = char_metrics(
                shot_cam, world_xs[_n], world_zs[_n],
                base_scale=char_scales[_n])
            if _gh <= 0:
                continue
            _hw = max(0.34 * _gh / 2.0 + 20.0, 0.15 * _gh)
            if not (40.0 + _hw <= _gx <= W - 40.0 - _hw):
                _all_fit = False
                break
        if _all_fit:
            break
        for _n in _fittable:
            world_xs[_n] = _target_x + (world_xs[_n] - _target_x) \
                * 0.9
        _staging_fit_steps += 1
    # ---- bystander clearance (round 7 / R6-D1) -------------------
    # After the fit, before the metrics assignment: a bystander whose
    # head sits inside an acting character's sweep disc gets pushed
    # laterally (in world x, re-projecting each step) until clear of
    # every sweep disc, or the 40 px frame margin blocks the push.
    # Actors never move; anchored characters never move; co-participants
    # of a sweep action never move. Over-the-shoulder shots skip the
    # pass: the foreground listener's head is the framing, and pushing
    # it would break the shot (intrusions there stay visible to the
    # head-intrusion audit below). The push is minimal: it stops at
    # the first clear step, and the record says what moved, how far,
    # and what stayed intruding.
    _bystander_clearance: dict = {"moved": {}, "exempt": [],
                                  "skipped": None}
    _id_to_name = {str(_c.get("id")): _nm
                   for _nm, (_i, _c) in _char_by_name.items()
                   if _c.get("id")}
    _sweep_actors: dict[str, set] = {}
    for _n in names:
        for (_ls, _le, _ev) in _per_actor.get(_n, []):
            _prim = (_ev.get("required_pose") or {}).get("primitive")
            if _prim in _HAND_SWEEP_PRIMITIVES:
                _parts = _sweep_actors.setdefault(_n, set())
                _tname = _id_to_name.get(str(_ev.get("target_id")))
                if _tname is not None and _tname != _n:
                    _parts.add(_tname)
    if shot.get("shot_type") == "over_the_shoulder":
        _bystander_clearance["skipped"] = "over_the_shoulder"
    elif _sweep_actors:
        _clear_anchored = (set(_anvil_staging)
                           | set(_furniture_staging)
                           | set(_shield_staging)
                           | set(_pick_staging)
                           | set(_place_staging)
                           | set(_sightline_moved))
        _sweep_discs = {}
        for _n in _sweep_actors:
            _agx, _agy, _agh = char_metrics(
                shot_cam, world_xs[_n], world_zs[_n],
                base_scale=char_scales[_n])
            if _agh > 0:
                _sweep_discs[_n] = (_sweep_disc(_agx, _agy, _agh),
                                    _agx, _agh)
        _co_parts = set()
        for _parts in _sweep_actors.values():
            _co_parts |= _parts
        for _b in names:
            if _b in _sweep_actors:
                continue
            if _b in _clear_anchored or _b in _co_parts:
                _bystander_clearance["exempt"].append(_b)
                continue
            _bx0 = world_xs[_b]
            _steps = 0
            _blocked = False
            _cleared = True
            while _steps < 40:
                _bgx, _bgy, _bgh = char_metrics(
                    shot_cam, world_xs[_b], world_zs[_b],
                    base_scale=char_scales[_b])
                if _bgh <= 0:
                    break
                _bhead = _head_disc(_bgx, _bgy, _bgh)
                _intruder = None
                for _an, (_disc, _agx, _agh) in _sweep_discs.items():
                    if not _discs_clear(
                            _disc, _bhead,
                            _SWEEP_MARGIN_FRAC * _agh):
                        _intruder = _an
                        break
                if _intruder is None:
                    _cleared = True
                    break
                _cleared = False
                _dir = 1.0 if _bgx >= _sweep_discs[_intruder][1] else -1.0
                world_xs[_b] += _dir * 0.1
                _ngx, _ngy, _ngh = char_metrics(
                    shot_cam, world_xs[_b], world_zs[_b],
                    base_scale=char_scales[_b])
                _nhw = max(0.34 * _ngh / 2.0 + 20.0, 0.15 * _ngh)
                if not (40.0 + _nhw <= _ngx <= W - 40.0 - _nhw):
                    world_xs[_b] -= _dir * 0.1
                    _blocked = True
                    break
                _steps += 1
            else:
                _cleared = False
            if _steps or not _cleared:
                _bystander_clearance["moved"][_b] = {
                    "steps": _steps,
                    "moved_world": round(world_xs[_b] - _bx0, 3),
                    "cleared": bool(_cleared),
                    "margin_blocked": bool(_blocked),
                    "actors": sorted(_sweep_discs)}
    # ---- head-clearance separation (round 7 / R6-D4) ----
    # Adjacent standing boxes must not overlap: a neighbour's
    # hat brim (which extends to 1.15r, inside the standing
    # box) crossing a head edge reads as a layering defect.
    # Pairs are pushed apart in 0.1 world steps until the gap
    # reaches 0.2x the smaller head radius. Anchored characters
    # (anvil/furniture/shield staging) and the OTS foreground
    # listener never move; interaction pairs (one character's
    # event targets the other: give/hand-over/shield) are
    # supposed to stand close and are exempt. A push blocked
    # by the 40 px frame margin reverts and the pair is
    # recorded unresolved -- never silently left overlapping.
    # Round 19 (R18-D1): the boxes above are STATIC, but
    # locomotion carries the head up to 380 px from the staging
    # mark, so a pair that clears standing still collides
    # mid-shot. The gap below is computed on SWEPT head ranges
    # (compiled replay + legacy cue travel + lean allowance),
    # re-projected every round like the static boxes were.
    _head_clearance: dict = {"moved": {}, "exempt": [],
                             "unresolved": []}
    # Round 20 (R19-D1): default for OTS shots, whose
    # pass block (and its staging package build) is skipped.
    _dress_pkg = None
    if shot.get("shot_type") != "over_the_shoulder":
        _hc_anchored = (set(_anvil_staging)
                        | set(_furniture_staging)
                        | set(_shield_staging)
                        | set(_pick_staging)
                        | set(_place_staging)
                        | set(_sightline_moved))
        if _ots_listener is not None:
            _hc_anchored.add(_ots_listener)
        _interact_pairs: set = set()
        for _n in names:
            for (_ls, _le, _ev) in _per_actor.get(_n, []):
                _tname = _id_to_name.get(str(_ev.get("target_id")))
                if _tname is not None and _tname != _n:
                    _interact_pairs.add(frozenset((_n, _tname)))
        _hc_blocked: set = set()
        _hc_start = dict(world_xs)
        # Round 20 (R19-D1): staging-time environment package
        # for the dressing-occlusion check below, mirroring
        # the furniture/anvil staging probes. A failed build
        # (or a shot without v1_location) skips the check and
        # leaves the pair separation exactly as before.
        _dress_pkg = None
        if isinstance(shot.get("v1_location"), dict):
            try:
                _dress_pkg = build_environment(
                    shot["v1_location"],
                    time_of_day=shot.get("time_of_day", "day"),
                    style={"mood": shot.get("mood", "warm")})
            except Exception:
                _dress_pkg = None
        # Round 19 (R18-D1): locomotion replay inputs, mirroring
        # the pose section below. The shot direction runs toward
        # the other character; legacy cue travel fires only for
        # the actor, only when no compiled event covers the
        # span, with the pose section's own steps (walk 320 /
        # run 380 / board to the bus door).
        _hc_dir = 1
        if actor is not None and other is not None:
            _hc_dir = 1 if world_xs[other] > world_xs[actor] \
                else -1
        _hc_legacy: dict = {}
        if shot.get("kind") == "action" and actor is not None \
                and not _shot_events:
            _hc_cues = _effective_cues(shot, package)
            if "board" in _hc_cues:
                _hc_legacy[actor] = ("abs", float(sx(
                    BUS_DOOR_X, shot_cam)))
            elif "run" in _hc_cues:
                _hc_legacy[actor] = (
                    "dx", 380.0 * _hc_dir)
            elif any(c in _hc_cues
                     for c in ("walk", "walk_fast")):
                _hc_legacy[actor] = (
                    "dx", 320.0 * _hc_dir)
        for _round in range(40):
            _boxes = {}
            for _n in names:
                _gx, _gy, _gh = char_metrics(
                    shot_cam, world_xs[_n], world_zs[_n],
                    base_scale=char_scales[_n])
                if _gh > 0:
                    _hw = max(0.34 * _gh / 2.0 + 20.0, 0.15 * _gh)
                    _legacy_end = None
                    if _n in _hc_legacy:
                        _kind, _val = _hc_legacy[_n]
                        _legacy_end = _val if _kind == "abs" \
                            else _gx + _val
                    _lo, _hi = _swept_head_range(
                        _per_actor.get(_n, []), _gx, _hc_dir,
                        _gh, _legacy_end)
                    _boxes[_n] = (_lo, _hi, _gh, _hw)
            _ordered = sorted(
                _boxes,
                key=lambda _n: (_boxes[_n][0] + _boxes[_n][1]) / 2.0)
            _pushed = False
            for _a, _b in zip(_ordered, _ordered[1:]):
                if frozenset((_a, _b)) in _interact_pairs:
                    continue
                _alo, _ahi, _ah, _ahw = _boxes[_a]
                _blo, _bhi, _bh, _bhw = _boxes[_b]
                _gap = (_blo - _bhw) - (_ahi + _ahw)
                _need = 0.2 * min(0.34 * _ah / 2.0,
                                  0.34 * _bh / 2.0)
                if _gap >= _need:
                    continue
                _movable = [x for x in (_a, _b)
                            if x not in _hc_anchored
                            and x not in _hc_blocked]
                if not _movable:
                    _pair = sorted((_a, _b))
                    if _pair not in _head_clearance["unresolved"]:
                        _head_clearance["unresolved"].append(_pair)
                    continue
                for _m in _movable:
                    _dir = -1.0 if _m == _a else 1.0
                    world_xs[_m] += _dir * 0.1
                    _ngx, _ngy, _ngh = char_metrics(
                        shot_cam, world_xs[_m], world_zs[_m],
                        base_scale=char_scales[_m])
                    _nhw = max(0.34 * _ngh / 2.0 + 20.0,
                               0.15 * _ngh)
                    if not (40.0 + _nhw <= _ngx
                            <= W - 40.0 - _nhw):
                        world_xs[_m] -= _dir * 0.1
                        _hc_blocked.add(_m)
                        continue
                    _pushed = True
                    _rec = _head_clearance["moved"].setdefault(
                        _m, {"steps": 0, "moved_world": 0.0})
                    _rec["steps"] += 1
                    _rec["moved_world"] = round(
                        world_xs[_m] - _hc_start[_m], 3)
            if not _pushed:
                break
        _head_clearance["exempt"] = sorted(
            _hc_anchored | set(_hc_blocked))
    # ---- post-staging headroom re-fit (round 7 / framing guard) --
    # The radius fit above ran on pre-fit positions; the staging fit
    # and the bystander clearance move characters after it, and a
    # moved character can push their head above the frame (R6 shot
    # #5: Linh's head cut for the whole shot). Re-fit on the FINAL
    # staging. Pulling the camera back only shrinks characters
    # toward the frame centre, so the fit and clearance guarantees
    # above can only improve; the radius never decreases here, so a
    # re-fit can never invalidate them. Every downstream consumer
    # (metrics, anchors, environment, freeze) reads shot_cam after
    # this point, so the rebuilt camera stays consistent.
    _camera_pullback = 1.0
    _radius_scale_final = _fit_radius_scale(
        shot["shot_type"], _angle, _target_x, _target_z,
        _counterpart_x, shot.get("srs_side", 0),
        [(world_xs[n], world_zs[n]) for n in names],
        [char_scales[n] for n in names],
        top_fracs=[_top_accessory_frac(_char_by_name[n][1])
                   if _char_by_name.get(n) else 0.0 for n in names],
        elevation_deg=_exec_elev)
    if _radius_scale_final > _radius_scale:
        _camera_pullback = _radius_scale_final / _radius_scale
        _radius_scale = _radius_scale_final
        shot_cam = viewpoint_for_shot(
            shot["shot_type"], _angle,
            subject_pos=(_target_x, 1.2, _target_z),
            counterpart_x=_counterpart_x,
            srs_side=shot.get("srs_side", 0),
            radius_scale=_radius_scale,
            azimuth_side=shot.get("viewpoint_azimuth_side"),
            elevation_deg=_exec_elev)
    # Round 20 (R19-D1): dressing occlusion runs AFTER the
    # headroom re-fit so corridors and element rects use the
    # FINAL camera. The pre-fit camera overestimates head
    # discs (764 px vs 602 px rendered in Loop 02 #17) and
    # invents wedges between elements that are actually
    # clear. Lateral-only moves: the re-fit's vertical
    # headroom is unaffected, and metrics/staging below read
    # the final world_xs.
    _dressing_moves: dict = {}
    _unresolved_dressing: list = []
    # Round 21 (R20-D1): deferred-insert shots frame the prop
    # + hands, not the room -- staging moves decouple the
    # hands from a world-static prop and break the insert
    # anchor, while the dressing the loop chases sits outside
    # the insert crop anyway. Skip the loop for those shots.
    if (shot.get("shot_type") != "over_the_shoulder"
            and _dress_pkg is not None
            and not _deferred_insert_shot(shot, _shot_events)):
        _dress_rects = []
        try:
            _dress_rects = _dressing_rects(
                _dress_pkg, shot_cam, W, H)
        except Exception:
            _dress_rects = []
        # Round 20 (R19-D1): corridors use DRAWN heights
        # (template ratio x stature), not the pre-template
        # char_metrics heights -- see _drawn_height_factor.
        _drawn_factors = {}
        for _n in names:
            _cd = _char_by_name.get(_n)
            _drawn_factors[_n] = (
                _drawn_height_factor(_cd[1]) if _cd else 1.0)
        if _dress_rects:
            _dress_seen: set = set()
            # 10 push rounds + 1 evaluation-only round: the
            # unresolved record reflects the FINAL staging.
            for _dround in range(11):
                _corridors = {}
                for _n in names:
                    _gx, _gy, _gh = char_metrics(
                        shot_cam, world_xs[_n], world_zs[_n],
                        base_scale=char_scales[_n])
                    if _gh <= 0:
                        continue
                    _gh = _gh * _drawn_factors.get(_n, 1.0)
                    _legacy_end = None
                    if _n in _hc_legacy:
                        _kind, _val = _hc_legacy[_n]
                        _legacy_end = (_val if _kind == "abs"
                                       else _gx + _val)
                    _lo, _hi = _swept_head_range(
                        _per_actor.get(_n, []), _gx, _hc_dir,
                        _gh, _legacy_end)
                    _r = 0.17 * _gh
                    _corridors[_n] = (
                        _lo - _r, _hi + _r,
                        _gy - _gh, _gy - _gh + 2.0 * _r, _gh)
                _ordered_d = sorted(
                    _corridors,
                    key=lambda _n: (_corridors[_n][0]
                                    + _corridors[_n][1]) / 2.0)
                _covered = []
                for _n in _ordered_d:
                    _clo, _chi, _ctop, _cbot, _gh = \
                        _corridors[_n]
                    for _rect in _dress_rects:
                        if (_clo <= _rect["cx"] <= _chi
                                and _ctop <= _rect["cy"] <= _cbot):
                            _covered.append((_n, _rect))
                            break
                # Oscillation guard: a corridor wedged
                # between two elements ping-pongs forever
                # (Ba Tu, rounds 0-9 of the first version).
                # A repeated state ends the loop with the
                # elements recorded unresolved.
                _state = (
                    tuple(round(world_xs[_n], 3)
                          for _n in names),
                    tuple(sorted((_n, _r["id"])
                                 for _n, _r in _covered)))
                if _state in _dress_seen:
                    for _n, _rect in _covered:
                        if _rect["id"] not in _unresolved_dressing:
                            _unresolved_dressing.append(_rect["id"])
                    break
                _dress_seen.add(_state)
                if _dround == 10:
                    # Evaluation-only round: whatever 10 push
                    # rounds could not clear stays unresolved.
                    for _n, _rect in _covered:
                        if _rect["id"] not in _unresolved_dressing:
                            _unresolved_dressing.append(_rect["id"])
                    break
                _movable_covered = [
                    (_n, _r) for _n, _r in _covered
                    if _n not in _hc_anchored
                    and _n not in _hc_blocked]
                if not _movable_covered:
                    # Nothing movable left to push; elements
                    # still covered by anchored/blocked
                    # characters are unresolved.
                    for _n, _rect in _covered:
                        if _rect["id"] not in _unresolved_dressing:
                            _unresolved_dressing.append(_rect["id"])
                    break
                _dpushed = False
                for _n, _rect in _movable_covered:
                    _clo, _chi, _ctop, _cbot, _gh = \
                        _corridors[_n]
                    _mid = (_clo + _chi) / 2.0
                    _dirs = ((-1.0, 1.0) if _mid <= _rect["cx"]
                             else (1.0, -1.0))
                    for _dir in _dirs:
                        _cand = world_xs[_n] + _dir * 0.1
                        _cgx, _cgy, _cgh = char_metrics(
                            shot_cam, _cand, world_zs[_n],
                            base_scale=char_scales[_n])
                        _cgh = _cgh * _drawn_factors.get(_n, 1.0)
                        _chw = max(0.34 * _cgh / 2.0 + 20.0,
                                   0.15 * _cgh)
                        if not (40.0 + _chw <= _cgx
                                <= W - 40.0 - _chw):
                            continue
                        _clegacy = None
                        if _n in _hc_legacy:
                            _kind, _val = _hc_legacy[_n]
                            _clegacy = (_val if _kind == "abs"
                                        else _cgx + _val)
                        _clo2, _chi2 = _swept_head_range(
                            _per_actor.get(_n, []), _cgx,
                            _hc_dir, _cgh, _clegacy)
                        _idx = _ordered_d.index(_n)
                        _neighbours = []
                        if _idx > 0:
                            _neighbours.append(
                                (_ordered_d[_idx - 1], -1))
                        if _idx + 1 < len(_ordered_d):
                            _neighbours.append(
                                (_ordered_d[_idx + 1], 1))
                        _ok = True
                        for _nb, _side in _neighbours:
                            if frozenset((_n, _nb)) \
                                    in _interact_pairs:
                                continue
                            (_nlo, _nhi, _ntop, _nbot,
                             _ngh) = _corridors[_nb]
                            _nhw = max(0.34 * _ngh / 2.0 + 20.0,
                                       0.15 * _ngh)
                            _need = 0.2 * min(
                                0.34 * _cgh / 2.0,
                                0.34 * _ngh / 2.0)
                            _nr = 0.17 * _ngh
                            _nlo_s = _nlo + _nr
                            _nhi_s = _nhi - _nr
                            if _side < 0:
                                _gap = ((_clo2 - _chw)
                                        - (_nhi_s + _nhw))
                            else:
                                _gap = ((_nlo_s - _nhw)
                                        - (_chi2 + _chw))
                            if _gap < _need:
                                _ok = False
                                break
                        if not _ok:
                            continue
                        world_xs[_n] = _cand
                        _dpushed = True
                        _rec = _head_clearance["moved"].setdefault(
                            _n, {"steps": 0, "moved_world": 0.0})
                        _rec["steps"] += 1
                        _rec["moved_world"] = round(
                            world_xs[_n] - _hc_start[_n], 3)
                        _drec = _dressing_moves.setdefault(
                            _n, {"steps": 0, "moved_world": 0.0})
                        _drec["steps"] += 1
                        _drec["moved_world"] = round(
                            _drec["moved_world"] + _dir * 0.1, 3)
                        break
                if not _dpushed:
                    # No feasible push this round; positions
                    # are final, so the current coverage is
                    # the unresolved record.
                    for _n, _rect in _covered:
                        if _rect["id"] not in _unresolved_dressing:
                            _unresolved_dressing.append(_rect["id"])
                    break
    _head_clearance["dressing_moves"] = _dressing_moves
    _head_clearance["unresolved_dressing"] = _unresolved_dressing
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
    # ---- D2 frozen crop anchor (Phase C checkpoint) ---
    # ONE crop per shot, computed HERE from STANDING boxes
    # and frozen for every frame (directive D2). It runs
    # BEFORE the environment build (round 6): the FG
    # fit/clearance must target the VISIBLE window (the
    # frozen crop rect), not the full frame, or a fitted
    # occluder lands mid-frame after the crop zoom. The
    # frame loop below reuses this one computation — the
    # crop is never recomputed from live state.
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
    # Round 8 (R7-D2): kneeled-head union. A kneel/bend drops the
    # head far below its standing position -- kneel_pick's head top
    # falls to 56% of standing height -- and the frozen crop,
    # fitted to the STANDING box, sliced the kneeled head (shot #0
    # f14-19: head below the frame bottom). Head-framing boxes
    # extend their foot_y down to the kneeled head bottom
    # (standing head top + head diameter + head drop), and no
    # further: the box is exactly the union window, so safe_frame
    # keeps the tightest scale that holds both the standing head
    # and the kneeled head, and steps down honestly when the union
    # cannot fit a tight crop (a deep bend_pick in an MCU becomes
    # a medium -- correct, not a silent cut). A plain downward
    # expansion overshoots (the R7-D2 first attempt zoomed shot #0
    # to full frame) and shifting the box down double-counts with
    # safe_frame's fit logic and cuts the standing head top; the
    # union bound is the minimal correct window. Full-body boxes
    # already span to the ground and need nothing.
    _HEAD_DROP_FRAC = {"kneel_pick": 0.44, "bend_pick": 0.70}
    _union_bottom: dict[str, float] = {}
    for _n in names:
        for _s, _e, _ev in _per_actor.get(_n, []):
            _prim = ((_ev.get("required_pose") or {}).get("primitive"))
            if _prim in _HEAD_DROP_FRAC:
                _hr_n = float(getattr(chars[_n], "head_r", 133.0))
                _top_n = float(ground_ys[_n] - char_heights[_n])
                _union_bottom[_n] = max(
                    _union_bottom.get(_n, 0.0),
                    _top_n + 2.0 * _hr_n
                    + _HEAD_DROP_FRAC[_prim] * float(char_heights[_n]))

    def _standing_box(_n, _kind):
        _hr = float(getattr(chars[_n], "head_r", 133.0))
        _cx = float(staging[_n])
        _top = float(ground_ys[_n] - char_heights[_n])
        _hc = _top + _hr  # standing head centre (B §5.1 formula)
        # Round 9: the box top covers top accessories (bun/hat/
        # crown/horns), not just the head circle -- otherwise a
        # bun nearly touches the frame top in MCU framings (R8
        # shot #3: ~5 px). "tight" deliberately crops into the
        # head and "head_hands" already carries 1.9r; both keep
        # their tops.
        _acc = _top_accessory_frac(chars[_n]) * _hr
        _ub = _union_bottom.get(_n)
        if _kind == "full":
            return {"cx": _cx, "head_y": _top - _acc,
                    "foot_y": float(ground_ys[_n]),
                    "half_w": max(_hr + 20,
                                  0.15 * float(char_heights[_n]))}
        if _kind == "tight":
            _foot = _hc + 1.1 * _hr
        elif _kind == "mcu":
            _foot = _hc + 2.8 * _hr
        elif _kind == "head_hands":
            # D1: head -> waist, plus headroom for a raised hand
            # (a full overhead reach peaks ~0.8 head-radii above
            # the head top). Chest/pocket-level props and raised
            # hands stay inside the anchor.
            _foot = float(ground_ys[_n]
                          - 0.45 * float(char_heights[_n]))
        else:
            _foot = _hc + 1.8 * _hr
        if _ub is not None:
            _foot = max(_foot, _ub)
        if _kind == "tight":
            return {"cx": _cx, "head_y": _hc - 0.7 * _hr,
                    "foot_y": _foot, "half_w": 0.8 * _hr + 15}
        if _kind == "mcu":
            return {"cx": _cx, "head_y": _hc - _hr - _acc,
                    "foot_y": _foot, "half_w": _hr + 40}
        if _kind == "head_hands":
            return {"cx": _cx, "head_y": _hc - 1.9 * _hr,
                    "foot_y": _foot,
                    "half_w": max(_hr + 30,
                                  0.15 * float(char_heights[_n]))}
        return {"cx": _cx, "head_y": _hc - _hr - _acc,
                "foot_y": _foot, "half_w": _hr + 30}

    _anchor_st = shot["shot_type"]
    _anchor_lead = (actor if actor in names else
                    (names[0] if names else None))
    _anchor_max_scale = None
    # D1: the anchor tier follows the shot's staged actions.
    _anchor_tier = _anchor_tier_for_shot(_shot_events, shot)
    # Round 7: a head framing is a head framing. A ground-level verb
    # (bend_pick, kneel, drop) used to widen close_ups and reactions
    # to the full body, so a scripted close-up rendered as a wide
    # two-shot (R6 shot #0). Head framings cap the tier at
    # head_hands: the head, shoulders and waist stay in frame, the
    # bend reads through the upper body, and the hand exits the crop
    # bottom the way a close-up cutaway does in the reference. A
    # travelling lead keeps the head framing with a path-widened
    # box (Round 8, R2-C2) instead of the old full-frame widening.
    _tier_capped = False
    if _anchor_tier == "full" and _anchor_st in HEAD_FRAMING_TYPES:
        _anchor_tier = "head_hands"
        _tier_capped = True
    _head_kind = {"head": "head", "head_hands": "head_hands",
                  "full": "full"}[_anchor_tier]
    # Round 8 (R2-C2): path-aware locomotion framing. The old rule
    # widened ANY head-framing shot containing ANY cast member's
    # walk to full-body at full frame -- one bystander's 320px
    # retreat destroyed the striker's MCU in the delivered R7
    # (shot #3: 148px heads). A short walk fits inside a head
    # framing: the walking character's subject box widens to cover
    # the walk PATH (start..end union) at the head-framing kind,
    # and safe_frame steps down honestly only when the path truly
    # cannot fit. A walking bystander no longer widens the shot
    # (he may exit the frozen crop -- natural for a retreat).
    # The swept-path replay is shared with the FG clearance
    # (_swept_x_for_actor): step sizes and the retreat flip live
    # in one place, matching _event_fn. The cue fallback (no
    # compiled events) keeps the old full-body behaviour for
    # legacy shots.
    _shot_dir = 1
    if actor is not None and other is not None:
        _shot_dir = 1 if staging[other] > staging[actor] else -1

    def _walk_path_box(_box, _n):
        _lo, _hi = _swept_x_for_actor(
            _per_actor.get(_n, []), staging[_n], _shot_dir)
        if _hi <= _lo:
            return _box
        _box = dict(_box)
        _box["cx"] = (_lo + _hi) / 2.0
        _box["half_w"] = float(_box["half_w"]) + (_hi - _lo) / 2.0
        return _box

    # Round 16 (L02-D2): an extreme close-up on a prop-manipulation
    # event frames the HANDS + PROP, never the face -- the face
    # defined the R15 ECU of the key going into the lock. Like
    # object_insert, the crop defers to telemetry (pass 2) or the
    # mid-shot frame (stills); the anchor branch below leaves the
    # subjects unset so the freeze path can do its job.
    # Round 21 (R20-D1): the prop-action test lives in
    # _deferred_insert_shot (single definition); the ECU
    # conjunction keeps this flag ECU-only, as before.
    _ecu_prop_action = (
        _anchor_st == "extreme_close_up"
        and _deferred_insert_shot(shot, _shot_events))
    _locomotion_widened = (
        not _shot_events
        and _shot_has_locomotion(_shot_events, shot)
        and _anchor_st in _LOCOMOTION_WIDENED_TYPES)
    if not names:
        # Empty-cast shot: nothing to frame — the full frame.
        _anchor_subjects, _anchor_others = [], []
        _anchor_max_scale = 1.0
    elif _locomotion_widened:
        # Cue fallback only (no compiled events): frame the full
        # body at full frame so the travelling subject cannot walk
        # out of the frozen crop (ECU-exit).
        _anchor_subjects = [_standing_box(n, "full") for n in names]
        _anchor_others = []
        _anchor_max_scale = 1.0
    elif _anchor_st == "close_up":
        _anchor_subjects = [_walk_path_box(
            _standing_box(_anchor_lead, _head_kind), _anchor_lead)]
        _anchor_others = [_walk_path_box(
            _standing_box(n, "full"), n)
            for n in names if n != _anchor_lead]
    elif _anchor_st == "medium_close_up":
        _anchor_subjects = [_walk_path_box(_standing_box(
            _anchor_lead, "full" if _anchor_tier == "full" else "mcu"),
            _anchor_lead)]
        _anchor_others = [_walk_path_box(
            _standing_box(n, "head"), n)
            for n in names if n != _anchor_lead]
    elif _anchor_st == "extreme_close_up":
        if _ecu_prop_action:
            # Deferred: the prop-action framing freezes from
            # telemetry (see _defer_framing) / the mid-shot
            # frame. No standing-box subjects: the face must
            # not define this frame.
            _anchor_subjects = None
            _anchor_others = [_standing_box(n, "head")
                              for n in names]
        else:
            _anchor_subjects = [_walk_path_box(
                _standing_box(_anchor_lead, "tight"), _anchor_lead)]
            _anchor_others = [_walk_path_box(
                _standing_box(n, "head"), n)
                for n in names if n != _anchor_lead]
    elif _anchor_st == "shot_reverse_shot":
        _anchor_subjects = [_walk_path_box(
            _standing_box(_anchor_lead, _head_kind), _anchor_lead)]
        # Round 19 (R18-D1 follow-up): the others' boxes are
        # walk-path-widened like the lead's -- safe_frame's
        # fully-in-or-fully-out rule must judge the TRAVELLED
        # extent, not the staging mark, or a runner judged OUT
        # runs into the crop and ends half-cut.
        _anchor_others = [_walk_path_box(
            _standing_box(n, "head"), n)
            for n in names if n != _anchor_lead]
    elif _anchor_st == "over_the_shoulder":
        _anchor_subjects = [_standing_box(n, "full") for n in names]
        _anchor_others = []
        _anchor_max_scale = 1.0
    elif _anchor_st == "reaction":
        _anchor_subjects = [_walk_path_box(
            _standing_box(n, _head_kind), n) for n in names]
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
    # The frozen crop rect the FG passes target (None for
    # object_insert / ECU prop-action: the crop defers to
    # telemetry in pass 2,
    # so no early estimate is trusted — FG keeps full-frame
    # behaviour there, recorded in provenance).
    _frozen_crop_rect = (
        list(_frozen[2]["crop_rect"]) if _frozen is not None
        else None)
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
    _fg_clearance: dict = {}
    # Round 7: _env_fitted is read by _build_frame's ground_kind
    # lookup; it must be bound on EVERY path (map shots and
    # env-less shots never assign it in the elif below).
    _env_fitted = None
    _flame_els: list = []
    # Round 20: _smoke_els follows the _flame_els precedent --
    # _build_frame reads it on EVERY path, but the elif below
    # assigns it only for env shots, so env-less shots raised
    # NameError (21 suite errors). Bound empty here; the elif
    # overwrites it with the rising-smoke elements when an
    # environment exists.
    _smoke_els: list = []
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
        # elements are frustum-fitted against the SHOT camera (the
        # camera the FG layer renders with): fitting against the
        # establishing camera left every non-establishing shot's FG
        # off-frame, because the standard viewpoint radius is much
        # closer than the establishing radius (round 2, scene
        # richness -- the fitted x for the wide camera projects
        # outside the standard camera's frustum at the FG plane).
        _env_archetype = _env_pkg.get("archetype")
        bg_scene = Scene25D(boxes=boxes, characters=[], camera=shot_cam,
                            sky_top=sky_top, sky_bottom=sky_bottom,
                            ground_color=ground_color,
                            ground_extent=30.0)
        _env_fitted = fit_foreground_to_frustum(
            _env_pkg, shot_cam, (W, H),
            visible_rect=_frozen_crop_rect)
        # Round 3: the frustum fit is azimuth-blind -- under an OTS
        # camera a fitted FG rock projects center-frame and covers
        # the cast (Loop 01 cave shots). Clear FG elements off the
        # subjects' standing boxes (same "full" box definition as
        # the parity telemetry) before rendering the layers.
        _subject_boxes = []
        _head_boxes = []
        for _n in names:
            _hr = float(getattr(chars[_n], "head_r", 133.0))
            _hw = max(_hr + 20.0,
                      0.15 * float(char_heights[_n]))
            # Round 17 (L02-D11): the box covers the character's
            # whole swept path in the shot, not just the staging
            # mark -- clearing against the static mark parks the
            # FG trunk exactly where a runner ends up.
            _lo, _hi = _swept_x_for_actor(
                _per_actor.get(_n, []), staging[_n], _shot_dir)
            _subject_boxes.append(
                (_lo - _hw,
                 float(ground_ys[_n] - char_heights[_n]),
                 _hi + _hw,
                 float(ground_ys[_n])))
            # Round 15 (L02-D6): head boxes for sun/moon
            # placement -- the disc must not sit behind a head.
            # The top margin covers hats/hair above the head
            # circle. Staging positions: a walking character
            # can still pass under the disc mid-shot.
            _head_boxes.append(
                (float(staging[_n]) - _hr * 1.4,
                 float(ground_ys[_n] - char_heights[_n] - 12.0),
                 float(staging[_n]) + _hr * 1.4,
                 float(ground_ys[_n] - char_heights[_n]
                       + 2.4 * _hr)))
        _env_fitted = clear_foreground_from_subjects(
            _env_fitted, shot_cam, (W, H), _subject_boxes,
            visible_rect=_frozen_crop_rect)
        _fg_clearance = (_env_fitted.get("provenance") or {}).get(
            "fg_clearance", {})
        # Round 8 (R7-D4): sparks elements animate per frame (the
        # set-piece block in _build_frame draws them live at the
        # real frame index). Baking them into a static layer froze
        # the streaks at frame 0 for the whole shot, so they are
        # excluded from both static renders. They cast no shadow
        # (shadows are box-geometry only), so the exclusion
        # removes nothing but the frozen streaks. Round 14:
        # fire/flame elements join the animated set (flame
        # flicker): they are drawn per frame by _draw_flames
        # in _build_frame, never baked into the background.
        # Round 20: rising smoke (flagged ``rises`` by the
        # builder -- chimney/hearth smoke only; distant
        # artillery smoke and steam keep the static blob)
        # joins the animated set, drawn per frame by
        # _draw_smoke in _build_frame.
        _smoke_els = [e for e in _env_fitted.get("elements", [])
                      if isinstance(e, dict)
                      and e.get("kind") in _SMOKE_KINDS
                      and (e.get("extra") or {}).get("rises")]
        _animated_ids = [e["id"] for e in
                         _env_fitted.get("elements", [])
                         if isinstance(e, dict)
                         and (e.get("kind") == "sparks"
                              or e.get("geometry") == "sparks"
                              or e.get("kind") in _FLICKER_KINDS)]
        _animated_ids += [e["id"] for e in _smoke_els]
        _flame_els = [e for e in _env_fitted.get("elements", [])
                      if isinstance(e, dict)
                      and e.get("kind") in _FLICKER_KINDS]
        bg_img = render_environment(
            _env_fitted, shot_cam, (W, H), draw_layers=("BG", "MG"),
            exclude_ids=_animated_ids,
            visible_rect=_frozen_crop_rect,
            avoid_boxes=_head_boxes)
        fg_layer = None
        if _env_fitted.get("layers", {}).get("FG"):
            _fg = render_environment(
                _env_fitted, shot_cam, (W, H), draw_layers=("FG",),
                transparent=True,
                exclude_ids=_animated_ids,
                fg_blur_radius=6.0 * (W / 1920.0))
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
    if _shot_is_map:
        # D2: no staged props on a full-frame map either (map
        # annotations come from the map spec, not the prop system).
        has_prop = False
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
        if n in _anvil_staging:
            # Round-5: the striker faces the anvil, not the scene
            # partner -- staged at anvil_x + side*0.9, the anvil is
            # in the -side direction. World-x order maps to
            # screen-x order under every camera we use.
            facing = -int(_anvil_staging[n][2])
        if n in _pick_staging:
            # Round 8: the picker faces the support, same geometry.
            facing = -int(_pick_staging[n][2])
        if n in _place_staging:
            # Round 8: the placer faces the support, same geometry.
            facing = -int(_place_staging[n][2])
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
    # Round 16 (L02-D2): lock anchors for INSERT_KEY events.
    # The lock is a staged target assembly (a coop-door panel +
    # a padlock), not a script prop: its position is solved from
    # the actor's staged shoulder and arm reach so the insert
    # is reachable BY CONSTRUCTION (the IK clamp is the
    # backstop, not the plan). In-segment insert events come
    # from _per_actor; locks opened earlier in the scene come
    # from the cross-segment scan (same shape as the held-pose
    # memory). The panel + lock draw in _build_frame; the open
    # articulation keys off the event window (see _lock_open_u).
    _lock_events: dict[str, dict] = {}
    for _an, _wins in _per_actor.items():
        for _ws, _we, _ev in _wins:
            if ((_ev.get("required_pose") or {}).get("primitive")
                    == "insert_key" and _an in chars):
                _lock_events[_an] = _ev
                break
    for _an, _ev in _lock_events_at_start(
            _compiled_all, shot.get("scene"), _t0,
            _id_to_name).items():
        if _an in chars and _an not in _lock_events:
            _lock_events[_an] = _ev
    _lock_anchors: dict[str, tuple[float, float]] = {}
    for _an in _lock_events:
        _sh = joints0[_an]["shoulder"]
        _reach = float(chars[_an].u_arm) + float(chars[_an].l_arm)
        _lock_anchors[_an] = (
            _sh[0] + facings[_an] * 0.82 * _reach,
            _sh[1] + 0.12 * char_heights[_an])
    # Round-8 (R2-V1): named support tops for surface placements
    # (the place_on_surface primitive reaches to the support the
    # script names). Same structural selection as the prop-rest
    # anchors -- never an invented surface.
    _support_tops = {a["support"]: a for a in _support_anchors(
        _env_pkg, shot_cam, (W, H))}
    # Prop rest positions: surface props (letter/pen/...) rest on the
    # paper; everything else rests in its owner's pocket (hidden
    # until manipulated — never on the ground by default, P2). A
    # prop whose semantic initial location is ON_GROUND rests on
    # the ground line instead (ground rule, §7).
    _prop_dicts = {str(p["id"]): p for p in package.get("props") or []
                   if isinstance(p, dict) and p.get("id")}
    # Round 17 (L02-D3): bag-kind props get the worn presentation
    # when no event stages them this frame (see _build_frame).
    _worn_bag_pids = [str(_pid) for _pid, _pd in _prop_dicts.items()
                      if infer_prop_kind(_pd) == "bag"]
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
    _support_anchor_list = _support_anchors(_env_pkg, shot_cam, (W, H))
    # Light payoff (round-2 system 5): burst events, set-piece
    # reaction anchors, strike contact moments, and set-piece
    # activations, computed once per shot.
    _reactive_anchors = _reactive_element_anchors(
        _env_pkg, shot_cam, (W, H))
    _burst_events = [e for e in _shot_events
                     if e.get("action_type") in BURST_TYPES
                     and e.get("prop_id")]
    # Round-5 hammer contact: the strike spans (actor name +
    # global span) drive the held hammer's grip angle per frame,
    # so the DRAWN hammer head tracks hammer_head_position --
    # the same point the primitive aims at and the contact audit
    # measures. Before this the hammer drew at the footprint
    # scale with a fixed orientation, ~70 px short of the
    # computed head, while the audit passed (R2-A2).
    _strike_spans: list[tuple] = []
    for _nm, _evs in _per_actor.items():
        for (_ls, _le, _ev) in _evs:
            if (_ev.get("required_pose") or {}).get("primitive") \
                    == "hammer_strike":
                # _per_actor windows are CLIPPED to this shot
                # (local times); _shot_events carries the
                # unclipped span, which would lag the grip-angle
                # phase behind the primitive's own cycle.
                _strike_spans.append((
                    _nm, _t0 + float(_ls), _t0 + float(_le)))
    _strike_moments: list[float] = []
    for _ev in _shot_events:
        if _ev.get("action_type") == "HAMMER_STRIKE":
            _dur = max(0.05, float(_ev.get("end_time", 0.0))
                       - float(_ev.get("start_time", 0.0)))
            for _rel in hammer_strike_times(
                    _dur, hammer_cycles(_dur)):
                _strike_moments.append(
                    float(_ev.get("start_time", 0.0)) + _rel)
    # Round-7 contact snaps (R5-A2): frames where the drawn hammer
    # head was extended to the anvil top at the contact instant.
    # Closure-appended by _build_frame; reported on the shot result.
    _contact_snaps: list[dict] = []
    # Round 20: previous frame's hammer screen position, for the
    # impact speed lines (the trail follows the hammer head's
    # own motion, never an invented path).
    _prev_hammer_xy: list = [None]
    _activate_events = [
        e for e in _shot_events
        if e.get("action_type") == "ACTIVATE"
        and names_set_piece(e.get("directive_text", ""))]
    _support_records: dict[str, str] = {}
    (_rests, _rest_kinds, _pocket_anchors) = _assign_prop_rests(
        _pids_all, _prop_dicts, _first_actor_for_pid, actor, _anchors,
        joints0, ground_ys, staging, _name_to_id, tracker=_tracker,
        fallback_ground_y=shot_ground_y, events=_shot_events,
        support_anchors=_support_anchor_list,
        support_records=_support_records)
    (_prop_machine, _machine_pids, _machine_kinds,
     _machine_rest_kinds, _prop_diagnostics) = _build_shot_prop_machine(
         package, shot, _shot_events, _rests, _rest_kinds,
         _pocket_anchors, _id_to_name, _name_to_id, set(names), _t0)
    for _pid, _sup in _support_records.items():
        if _sup.startswith("missing:"):
            _prop_diagnostics.append(
                f"{_pid}: placement names support {_sup[8:]!r} but "
                "the shot environment has no such support; fell back "
                "to the kind rule")
    if _shot_is_map:
        # D2: the machine is built (diagnostics stay honest) but
        # draws nothing -- a holderless prop must not float on the
        # map. The machine object is nulled; diagnostics are kept.
        _prop_machine, _machine_pids, _machine_kinds = None, [], {}
        _machine_rest_kinds = {}
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
        # Round 7: when the shot's motion is compiled (V1), a cue
        # that no compiled event covers in this span stages NOTHING.
        # The cue list is shot-wide while compiled events are clipped
        # per split shot, so a "walk" cue fired the legacy walk for
        # the WHOLE span of a shot whose walk event belongs to a
        # later split shot (R6-D1 residue: the watcher drifted into
        # the hammer's arc during the strike). Free-form shots have
        # no compiled events, so the legacy path runs unchanged
        # there.
        _compiled_motion = bool(_shot_events)
        # Round 18 (R17-D1): the round-7 _compiled_motion guard
        # covered locomotion only, so a scene-leaked "give" cue
        # staged a phantom handover in a split shot whose
        # handover event belongs to a later span (Loop 02 #15:
        # the key sat at the unreachable meeting point while
        # An's hand never contacted it). A prop-affecting legacy
        # pose stages only when an event of the same family
        # covers THIS span -- or when the package has no compiled
        # actions at all (free-form, where cues are the only
        # motion source). When an event covers the span, the W4
        # loop owns the pose anyway, so the gate changes nothing
        # there.
        _shot_types = {e.get("action_type") for e in _shot_events}
        _give_covered = (not _compiled_all) or (
            "HAND_OVER" in _shot_types)
        _pick_covered = (not _compiled_all) or bool(
            {"BEND_PICK", "KNEEL_PICK"} & _shot_types)
        if "board" in cues and not _compiled_motion:
            # Lan boards: walk to the bus door.
            fns[actor] = walk_to(chars[actor], ax, sx(BUS_DOOR_X, shot_cam),
                                 duration, ground_ys[actor])
        elif "run" in cues and not _compiled_motion:
            fns[actor] = run_to(chars[actor], ax, ax + 380 * direction,
                                duration, ground_ys[actor])
        elif (any(c in cues for c in ("walk", "walk_fast"))
              and not _compiled_motion):
            fns[actor] = walk_to(chars[actor], ax, ax + 320 * direction,
                                 duration, ground_ys[actor])
        elif "bend_pick" in cues and _pick_covered:
            prop_x, prop_y = ax + 220, ground_ys[actor] - 6
            prop.update(x=prop_x, y=prop_y)
            fns[actor] = kneel_pick(chars[actor], (prop_x, prop_y), duration, ground_ys[actor])
        elif "give" in cues and other is not None \
                and _give_covered:
            standing(chars[actor], ax, ground_ys[actor],
                     facing=1 if staging[other] > ax else -1)
            standing(chars[other], staging[other], ground_ys[other],
                     facing=1 if ax > staging[other] else -1)
            give_fn = give_to(chars[actor], chars[other], prop, duration)
            fns[actor] = give_fn
        elif "wave" in cues:
            fns[actor] = wave(chars[actor], duration)
        else:
            fns[actor] = idle(chars[actor], duration, ground_ys[actor],
                              gaze_seed=_gaze_seeds.get(actor, 0))
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
            fns[n] = idle(ch, 99.0, ground_ys[n],
                          gaze_seed=_gaze_seeds.get(n, 0))
            fns[n](0.0)
    # ---- W4: compiled events override cue/idle fns ------------------
    # Each actor with events gets a sequenced fn (windows in time
    # order, overlays for carry_bag, blocks for handover receivers so
    # the pair fn owns the receiver's pose). Windows whose primitive
    # cannot be built fall back to idle AND are recorded loudly in
    # the shot report (never a silent substitution).
    _dispatch_fallback: list[str] = []
    _insert_idle_windows: list[str] = []
    _pair_blocks: dict[str, list] = {}
    _pair_windows: dict[str, list] = {}

    def _make_event_ctx(_name):
        # One construction for the _event_fn context, shared by the
        # _per_actor loop and the Round-16 held-pose fallback so the
        # two can never drift. "pos" is fresh per call: movers update
        # it so chained events start where the previous one ended.
        return {
            "name": _name, "char": chars[_name],
            "gaze_seed": _gaze_seeds.get(_name, 0),
            "other_name": other,
            "other_char": chars.get(other) if other else None,
            "staging_x": staging[_name],
            "ground_y": ground_ys[_name],
            "direction": _direction, "facing": facings[_name],
            "prop": prop, "paper": _anchors[_name]["paper"],
            "desk": _anchors[_name]["desk"],
            "anvil": _anchors[_name]["anvil"],
            "supports": _support_tops,
            "chair_x": _anchors[_name]["chair"]["x"],
            "seat_y": _anchors[_name]["chair"]["seat_y"],
            "rests": _rests, "pos": {"x": staging[_name]},
            "joints0": joints0, "id_to_name": _id_to_name,
            "lock_anchor": _lock_anchors.get(_name),
            "name_to_id": _name_to_id,
        }

    if _per_actor:
        for _name, _wins in _per_actor.items():
            if _name not in chars:
                continue
            _ctx = _make_event_ctx(_name)
            _base_windows = []
            _overlays = []
            _has_sit = any(
                ((_ev.get("required_pose") or {}).get("primitive")
                 == "sit_at_desk")
                for _ws, _we, _ev in _wins)
            _held_ev = _held_at_start.get(_name)
            _held_prim = ((_held_ev or {}).get("required_pose")
                          or {}).get("primitive") \
                if _held_ev is not None else None
            _has_held_here = _held_prim is not None and any(
                ((_ev.get("required_pose") or {}).get("primitive")
                 == _held_prim)
                for _ws, _we, _ev in _wins)
            if _held_ev is not None and not _has_held_here:
                # Round 16 (L02-D8): the character entered this shot
                # in a held body pose (sat down in an earlier
                # segment/shot of the scene). Seat them in the first
                # instant (a 1 ms hold window at the completion
                # pose, like the seated prefix below) so the
                # following windows act on the held body and gaps
                # hold the pose instead of standing idle. The shot
                # that carries the establishing event itself skips
                # this: its own window animates the sit.
                _held_dur = max(
                    0.05,
                    float(_held_ev.get("end_time", 0.0))
                    - float(_held_ev.get("start_time", 0.0)))
                _held_fn = _event_fn(
                    _held_prim,
                    (_held_ev.get("required_pose") or {}).get(
                        "params") or {},
                    _held_ev, _ctx, _held_dur)
                if _held_fn is not None:
                    _base_windows.append((
                        0.0, 0.001,
                        lambda _t, _f=_held_fn, _d=_held_dur: _f(_d)))
            elif _seated_at_start.get(_name) and not _has_sit:
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
                if shot.get("shot_type") in _INSERT_SHOT_TYPES \
                        and _prim in _INSERT_IDLE_PRIMITIVES:
                    # Round 9 (R2-C4): an insert shows the OBJECT.
                    # A reach-without-grasp gesture is amputated by
                    # the frozen crop into a disembodied frozen
                    # claw. The body holds idle; the face stays
                    # alive (expression/blink/gaze) and the event
                    # still fires effects -- bursts read events,
                    # not primitives. Recorded loudly, like the
                    # dispatch fallback, never silently.
                    _insert_idle_windows.append(
                        str(_event.get("action_id")))
                    _base_windows.append((
                        _start, _end,
                        idle(chars[_name], _dur, ground_ys[_name],
                             gaze_seed=_gaze_seeds.get(_name, 0))))
                    continue
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
                            idle(chars[_name], _dur, ground_ys[_name],
                                 gaze_seed=_gaze_seeds.get(_name, 0))))
                        continue
                    _recv_hand = _params.get("receive_hand", "l")
                    if _recv_hand not in ("l", "r", "both"):
                        _recv_hand = "l"
                    _pair_fn = hand_over(chars[_name], chars[_recv],
                                         prop, _dur,
                                         receive_hand=_recv_hand)
                    _base_windows.append((_start, _end, _pair_fn))
                    _pair_blocks.setdefault(_recv, []).append(
                        (_start, _end))
                    continue
                _fn = _event_fn(_prim, _params, _event, _ctx, _dur)
                if _fn is None:
                    _dispatch_fallback.append(
                        str(_event.get("action_id")))
                    _fn = idle(chars[_name], _dur, ground_ys[_name],
                                 gaze_seed=_gaze_seeds.get(_name, 0))
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
    # Round 16 (L02-D8): characters with a held pose but NO events in
    # this shot never enter the _per_actor loop above, so without this
    # they idle standing -- the Loop 02 shot-13 defect (An's sit
    # vanished in the segment after the sit event's span ended).
    # Give them a sequenced fn whose only window is the 1 ms
    # completion-pose hold: the body holds the pose for the shot
    # while the face stays alive (expression/blink/gaze and the
    # talk/listen nods run as overlays in the frame loop).
    # Seated-at-desk characters are NOT covered here: the seated path
    # stages them at furniture, which this fallback cannot reproduce;
    # that gap is recorded as a follow-up.
    _held_override = set(_pair_windows) | set(_pair_blocks)
    for _name, _held_ev in _held_at_start.items():
        if _name not in chars or _name in _held_override:
            continue
        _held_prim = ((_held_ev or {}).get("required_pose")
                      or {}).get("primitive")
        _held_dur = max(
            0.05,
            float(_held_ev.get("end_time", 0.0))
            - float(_held_ev.get("start_time", 0.0)))
        _held_fn = _event_fn(
            _held_prim,
            (_held_ev.get("required_pose") or {}).get("params") or {},
            _held_ev, _make_event_ctx(_name), _held_dur)
        if _held_fn is None:
            continue
        _base_fn = fns.get(_name)
        fns[_name] = _sequence_fns(
            [(0.0, 0.001,
              lambda _t, _f=_held_fn, _d=_held_dur: _f(_d))],
            [], _base_fn)
        try:
            fns[_name](0.0)
        except Exception:
            pass
    talk_nod = None
    # Round-4 "hon": listeners react while someone else speaks --
    # a slow nod each, phase-offset per character (deterministic
    # crc32 seed) so two listeners never nod in sync. Same
    # head_look-overlay mechanism as the speaker's talk_nod.
    listen_nods: dict[str, tuple] = {}
    if shot["kind"] in ("narration", "dialogue") and actor is not None:
        # Round 16 (R15-D1): the talk nod runs on the
        # speaker's gaze grid (the seed shared with the idle
        # and the eyes) at 0.5 Hz. A 1.1 Hz sine sampled on
        # the 0.25 s grid jumps up to 0.12 rad per boundary
        # (99 deg phase steps) -- measured 8.6M rim-diff pops
        # on delivered frames; at 0.5 Hz the 45 deg steps
        # glide inside the 2-frame ease.
        # Round 19: the talk nod is gated by the real voice
        # segment -- the same span the mouth envelope uses --
        # so the head nods while speech is happening and holds
        # still through the post-voice beat.
        talk_nod = nod(chars[actor], duration, freq=0.5, amp=0.08,
                       gaze_seed=_gaze_seeds.get(actor, 0),
                       speech_gate=(0.0, float(shot.get(
                           "voice_duration", duration))))
        talk_nod(0.0)
        for _ln in names:
            if _ln == actor or _ln not in chars:
                continue
            _phase = (zlib.crc32(
                f"{shot.get('directive_shot_id')}:{_ln}".encode(
                    "utf-8")) % 1000) / 1000.0 * 3.0
            _lfn = nod(chars[_ln], duration, freq=0.33, amp=0.05,
                       gaze_seed=_gaze_seeds.get(_ln, 0),
                       phase=_phase)
            _lfn(0.0)
            listen_nods[_ln] = (_lfn, _phase)
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

    def _burst_records(t_abs, joints_by_key):
        """(event_id, action_type, glow record) live at ``t_abs``.

        One producer for the three burst consumers: the in-frame
        glow paint, the crack lines (CRACK entries), and the
        deferred insert pass (which maps the staging-space record
        through the crop). Pocket-hidden props burst nothing: an
        invisible prop cannot light the frame. A prop at rest on
        a surface DOES burst -- the cracking core on its pedestal
        is the payoff case.
        """
        out = []
        if _prop_machine is None:
            return out
        for _ev in _burst_events:
            _start = float(_ev.get("start_time", 0.0))
            _end = float(_ev.get("end_time", _start))
            _u = (t_abs - _start) / max(_end - _start, 1e-6)
            _inten = burst_envelope(_ev.get("action_type"), _u)
            if _inten <= 0.0:
                continue
            _pid = str(_ev.get("prop_id"))
            if _pid not in _machine_pids:
                continue
            (_bx, _by, _bang, _bstate, _bhand) = \
                _prop_machine.transform_at(_pid, t_abs,
                                           joints_by_key)
            if _bstate == "WORLD_STATIC" and \
                    _machine_rest_kinds.get(_pid) == "pocket":
                continue
            _color, _radius = burst_color_radius(
                _prop_dicts.get(_pid))
            out.append((str(_ev.get("action_id")),
                        _ev.get("action_type"),
                        burst_record(_pid, _bx, _by, _inten,
                                     _color, _radius)))
        return out

    # Effect telemetry accumulators (mutation only -- the frame
    # closures append without rebinding).
    _effect_peak: dict[str, float] = {}
    _effect_frames: dict[str, int] = {}
    _reaction_acc = {"peak": 0.0, "frames": 0}

    # Round 14 (R13-D1 root cause): the shadow key. _build_frame
    # used to pass bg_scene.lights.key to the shadow drawer, but
    # Scene25D is built WITHOUT lights here, so that was the
    # DEFAULT rig key (0.35,-1.0,-0.3) -- elevation 0.92, spread
    # 0.087 -- and every character cast spec returned None
    # (154/154 logged calls on the #1 probe). The key is now the
    # palette rig's key -- the same rig render_environment uses
    # -- so contact offsets and cast quads follow the scene's
    # actual sun. Legacy/map shots without an env package keep
    # the scene key (the previous behaviour there).
    _env_light = _env_pkg.get("light") if _env_pkg else None
    _shadow_key = (rig_for(_env_light).key if _env_light
                   else bg_scene.lights.key)

    def _lock_open_u(_t, _name):
        # 0 through the approach + insert, ramping during the
        # turn phase (the last 40% of the event window -- the
        # same phase split the insert_key primitive uses), 1
        # after the window closes (the lock stays open for the
        # rest of the shot, including later segments). The
        # clipped window wins when the event runs inside this
        # segment (exact, no trust assumption); else the
        # absolute event times (trusted: the cross-segment scan
        # only admits trusted events).
        _ev = _lock_events.get(_name)
        if _ev is None:
            return 0.0
        for _ws, _we, _wev in _per_actor.get(_name, []):
            if _wev is _ev:
                _s, _e = _ws, _we
                break
        else:
            _s = float(_ev.get("start_time", 0.0)) - _t0
            _e = float(_ev.get("end_time", _s)) - _t0
        if _t <= _s + 0.6 * (_e - _s):
            return 0.0
        if _t >= _e:
            return 1.0
        return (_t - (_s + 0.6 * (_e - _s))) / max(
            0.4 * (_e - _s), 1e-6)

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
            # Round 13: cast shadows outdoors only (the sun is
            # not the light indoors).
            _draw_character_shadow(
                img, chars[n], shot_cam,
                (world_xs[n], 0.0, world_zs[n]), _shadow_key,
                cast=_env_archetype not in _ENCLOSED_ARCHETYPES)
        d = ImageDraw.Draw(img, "RGBA")
        # Round 14: flame flicker -- fire/flame elements draw
        # per frame on the background copy, BEFORE the
        # characters, so a character in front of the furnace
        # correctly occludes the flame. The floor glow pools
        # with the same flicker value (see _draw_flames).
        for _fel in _flame_els:
            _draw_flames(img, d, _fel, shot_cam, W, H, frame=fi)
        # Round 20: rising smoke draws per frame on the
        # background copy, before the characters, like the
        # flames -- a character in front of the chimney
        # correctly occludes the plume.
        for _sel in _smoke_els:
            _draw_smoke(img, d, _sel, shot_cam, W, H, frame=fi)
        # Poses are set: the live joints give heads (gaze targets),
        # hips (pocket rests) and hands (prop attachment) for this
        # exact frame.
        joints_pre = {n: chars[n].joints() for n in names}
        # Round 20 (R19-D2): worn-bag presentations, computed
        # once per frame from the pre-draw joints. The held-
        # prop clearance (machine + legacy paths below) and
        # the worn draw block share these positions, so the
        # clearance rects exactly match the drawn bags. The
        # rect covers the bag body plus the handle arc above
        # it (the _draw_prop "bag" branch geometry).
        _worn_draws: list[dict] = []
        if _worn_bag_pids and _char_elev_deg < 45.0:
            for _pid in _worn_bag_pids:
                _owner = _worn_bag_owner(
                    _compiled_all, _pid, _t0 + t, _id_to_name)
                if _owner is None or _owner not in joints_pre:
                    continue
                _jn = joints_pre[_owner]
                _sc = float(chars[_owner].H) / 560.0
                _facing = chars[_owner].pose.get(
                    "facing", facings.get(_owner, 1))
                _shx, _shy = _jn["shoulder"]
                _hpx, _hpy = _jn["hip"]
                _bx = _hpx + _facing * 52.0 * _sc
                _by = _hpy + 26.0 * _sc
                _fw, _fh = geometry_footprint("bag")
                _w, _h = _fw * _sc, _fh * _sc
                _worn_draws.append({
                    "pid": _pid, "bx": _bx, "by": _by,
                    "w": _w, "h": _h,
                    "strap_from": (_shx, _shy),
                    "strap_to": (_bx, _by - 20.0 * _sc),
                    "strap_w": max(3, int(6 * _sc)),
                    "rect": (_bx - _w / 2.0, _by - _h / 2.0 - 6.0,
                             _bx + _w / 2.0, _by + _h / 2.0),
                })
        _worn_rects = [_wd["rect"] for _wd in _worn_draws]
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
        # Set-piece reaction (round-2 system 5) + live sparks
        # (round 8, R7-D4): the furnace flares and the anvil sparks
        # accelerate when a hammer strike lands or a set-piece
        # activation runs. Painted BEFORE the characters (the MG
        # layer the sparks live in). The furnace wash stays gated
        # on paint_glow like the energy halo: a pre-crop wash
        # would be magnified by an insert zoom. The sparks draw
        # EVERY frame at the real frame index -- the ambient field
        # is forge activity that must animate, and baking it into
        # the static background froze the streaks at frame 0 (the
        # R7-D4 defect). Inside the gated reaction window the
        # count boosts and the field accelerates, exactly as
        # before; outside it the base field rises and dies on its
        # per-spark lifetimes (round 9: no exact repeat). The burst
        # gating (decay 0.10 s, paint
        # floor 0.15) is unchanged: only the ambient field is
        # always visible, never the burst.
        _sparks_el = _reactive_anchors["sparks_el"]
        if _sparks_el is not None \
                or _reactive_anchors["furnace"] is not None:
            _reaction = strike_reaction(_t0 + t, _strike_moments)
            for _ev in _activate_events:
                _as = float(_ev.get("start_time", 0.0))
                _ae = float(_ev.get("end_time", _as))
                _reaction = max(
                    _reaction,
                    burst_envelope(
                        "ACTIVATE",
                        (_t0 + t - _as) / max(_ae - _as, 1e-6)))
            _bursting = paint_glow \
                and _reaction > REACTION_PAINT_FLOOR
            if _bursting:
                _furn = _reactive_anchors["furnace"]
                if _furn is not None:
                    paint_energy_glow(
                        img, burst_record(
                            "furnace", _furn[0], _furn[1], _reaction,
                            REACTION_GLOW_COLOR,
                            REACTION_GLOW_RADIUS_PX))
                _reaction_acc["peak"] = max(_reaction_acc["peak"],
                                            _reaction)
                _reaction_acc["frames"] += 1
            if _sparks_el is not None:
                _extra = dict(_sparks_el.get("extra") or {})
                if _bursting:
                    _extra["spark_count"] = int(
                        _extra.get("spark_count", 14)
                        * (1.0 + 2.0 * _reaction))
                    _spark_frame = int(fi * (1.0 + 2.0 * _reaction))
                else:
                    _spark_frame = fi
                # Round 9 (R7-D4 residual): the contact burst. The
                # age window (12 frames from the latest strike
                # moment) is its own gate -- it outlives the glow
                # flash so the flying sparks arc and fade after
                # contact, and it never fires without a strike.
                # paint_glow does not gate it: a strike inside an
                # insert IS the insert's subject. Scan newest-first
                # so the freshest in-window strike owns the burst.
                for _si in range(len(_strike_moments) - 1, -1, -1):
                    _sm = _strike_moments[_si]
                    _age = int((_t0 + t - _sm) * FPS)
                    if 0 <= _age < _SPARK_BURST_LIFETIME:
                        _extra["burst_age_frames"] = _age
                        _extra["burst_strike_index"] = _si
                        break
                # Round 11 (R11-4): debris has its own, longer age
                # window (44 frames): the fragments land and cool
                # on the floor long after the streaks are gone. A
                # second strike re-fires debris with its own seed
                # while the first strike's debris is still cooling.
                for _si in range(len(_strike_moments) - 1, -1, -1):
                    _sm = _strike_moments[_si]
                    _age = int((_t0 + t - _sm) * FPS)
                    if 0 <= _age < _DEBRIS_LIFETIME:
                        _extra["debris_age_frames"] = _age
                        _extra["debris_strike_index"] = _si
                        break
                _draw_sparks(
                    img, d, dict(_sparks_el, extra=_extra),
                    shot_cam, None, W, H,
                    spark_frame=_spark_frame)
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
                # Round 17 (R16-O1): held-prop head clearance.
                # A small prop centred on a hand raised beside a
                # face draws across the eye/cheek (Loop 02: the
                # key over Ba Tu's eye, An's temple). Push the
                # DRAW position radially out of every head disc
                # it intrudes; the hand never moves. Shield /
                # hammer / bag keep their choreographed
                # presentations. Before the tip: tips follow the
                # cleared position.
                if _mstate in ("GRASPED", "ATTACHED_TO_HAND",
                               "IN_USE") \
                        and _machine_kinds[_pid] not in (
                            "shield", "hammer", "bag"):
                    for _nm2, _jj2 in joints_pre.items():
                        if _nm2 not in chars:
                            continue
                        _hc2 = _jj2.get("head")
                        if _hc2 is None:
                            continue
                        _mx, _my = _clear_head(
                            (_mx, _my), _hc2,
                            float(getattr(chars[_nm2], "head_r",
                                          0.0)),
                            float(chars[_nm2].H))
                    # Round 20 (R19-D2): a held prop whose
                    # hand swings over the owner's worn bag
                    # hides behind the bag (the bag draws
                    # after the props). Push the DRAW position
                    # radially out of every worn-bag rect;
                    # the hand never moves. Same gating as
                    # the head clearance above.
                    if _worn_rects:
                        _mx, _my = _clear_worn_bags(
                            (_mx, _my), _worn_rects)
                _tip = None
                if _holder_name in chars and _mstate in (
                        "GRASPED", "ATTACHED_TO_HAND", "IN_USE"):
                    _facing = chars[_holder_name].pose.get(
                        "facing", facings.get(_holder_name, 1))
                    _ch_h = chars[_holder_name].H
                    if _machine_kinds[_pid] == "pen":
                        _tip = pen_tip_position((_mx, _my), _facing,
                                                _ch_h)
                    elif _machine_kinds[_pid] == "hammer":
                        # Round-5: the hammer's striking face, at
                        # the grip angle in force this frame. The
                        # phase comes from the active strike span;
                        # a carried (non-striking) hammer rests at
                        # the strike angle, per hammer_grip_angle.
                        _angle = None
                        _strike_u = None
                        for (_an, _ss, _se) in _strike_spans:
                            if _an == _holder_name and _ss <= _t0 + t <= _se:
                                _sd = max(0.05, _se - _ss)
                                _cyc = hammer_cycles(_sd)
                                _strike_u = ((_t0 + t - _ss) / _sd * _cyc) % 1.0
                                _angle = hammer_grip_angle(_strike_u)
                                break
                        _tip = hammer_head_position(
                            (_mx, _my), _facing, _ch_h, _angle)
                        # Round-7 contact snap (R5-A2): at the
                        # contact instant the drawn striking face is
                        # extended along the handle axis down to the
                        # anvil top the primitive aimed at, so the
                        # contact frame shows contact. Only at the
                        # contact instant, only downward, only when
                        # a real environment anvil anchors the
                        # strike, and only by a small extension. The
                        # hand's own shortfall (IK reach) is
                        # unchanged and stays visible to the contact
                        # audit; only the drawn head is snapped.
                        if (_strike_u is not None and _angle is not None
                                and abs(_strike_u
                                        - HAMMER_CYCLE_STRIKE_U) <= 0.03):
                            _anv = ((_anchors.get(_holder_name) or {})
                                    .get("anvil"))
                            if _anv is not None:
                                _top_y = float(_anv["top_y"])
                                _dir_y = math.sin(_angle)
                                if _tip[1] < _top_y and _dir_y > 0.1:
                                    _ext = (_top_y - _tip[1]) / _dir_y
                                    if 0.0 < _ext <= 0.08 * _ch_h:
                                        _tip = (
                                            _tip[0] + _facing
                                            * math.cos(_angle) * _ext,
                                            _tip[1] + _dir_y * _ext)
                                        _contact_snaps.append({
                                            "time": round(_t0 + t, 3),
                                            "extension_px": round(_ext, 1),
                                            "anvil_top_y": round(_top_y, 1)})
                _machine_draws.append(
                    (_pid, _mx, _my, _machine_kinds[_pid],
                     float(_detail.get("open_u", 0.0)), _mstate,
                     _tip))
                if _holder_name in names and _mstate in (
                        "GRASPED", "ATTACHED_TO_HAND", "IN_USE"):
                    if _mhand == "both":
                        _grips.setdefault(_holder_name, {})["l"] = "grip"
                        _grips.setdefault(_holder_name, {})["r"] = "grip"
                    elif _mhand in ("l", "r"):
                        _grips.setdefault(
                            _holder_name, {})[_mhand] = "grip"
                _machine_meta[_pid] = {
                    "holder": _holder_name, "hand": _mhand,
                    "angle": float(_mang)}
        # Burst records for this frame (shared by the glow paint
        # and the crack lines in both draw passes). Computed once
        # per frame; the crack intensities are the CRACK entries.
        _burst_now = _burst_records(_t0 + t, _joints_by_key) \
            if _prop_machine is not None and joints_pre else []
        _crack_now = {rec["prop_id"]: rec["intensity"]
                      for _eid, _atype, rec in _burst_now
                      if _atype == "CRACK"}
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
            if _pid in _crack_now:
                _fw, _fh = geometry_footprint(_dkind)
                _alpha = int(220 * _crack_now[_pid])
                for _line in crack_lines(
                        (_dx - _fw / 2.0, _dy - _fh / 2.0,
                         _dx + _fw / 2.0, _dy + _fh / 2.0), _pid):
                    d.line(_line, fill=(30, 25, 20, _alpha), width=3,
                           joint="curve")
        # Energy glow (item 10): held energy-carrying props
        # emit a halo from the lighting stage, painted
        # BEFORE the characters (round 6, R2-F1): the halo
        # lights the environment around the prop — the
        # anvil, the ground, the walls — while the cast
        # draws over it, so a glowing stone resting
        # against a leg no longer washes the leg out.
        # Held props draw after the characters, crisp on
        # top of their own light. No record (not held, no
        # energy spec) means no glow; radius 0 paints
        # nothing. The record's positions are
        # staging-plane pixels, the space this frame is
        # built in, so no bridge is needed here.
        # a halo from the lighting stage, painted after the
        # characters and before the props themselves, so the prop
        # stays crisp on top of its own light and the halo tints
        # the surroundings. No record (not held, no energy spec)
        # means no glow; radius 0 paints nothing. The record's
        # positions are staging-plane pixels, the space this
        # frame is built in, so no bridge is needed here.
        # Round 10 (R10-6): the light pool's ground line is the
        # floor under the glow source -- the ground line of the
        # character nearest the source in x (usually the holder
        # or the actor at the pedestal). A soft pool tolerates a
        # small depth error; the wrong character's floor would
        # float it visibly.
        def _pool_ground_y(sx):
            _best = None
            _best_dx = None
            for _n in names:
                _j = joints_pre.get(_n)
                if _j is None or _n not in ground_ys:
                    continue
                _dx = abs(float(_j["head"][0]) - float(sx))
                if _best_dx is None or _dx < _best_dx:
                    _best_dx = _dx
                    _best = _n
            return ground_ys.get(_best) if _best else None

        if paint_glow and _prop_machine is not None and joints_pre:
            for _pid in _machine_pids:
                _glow = _prop_machine.energy_glow_at(
                    _pid, _t0 + t, _joints_by_key)
                if _glow is not None and _glow["radius"] > 0:
                    paint_energy_glow(img, _glow)
                    _pool_gy = _pool_ground_y(
                        _glow["source_position"][0])
                    if _pool_gy is not None:
                        paint_light_pool(img, _glow, _pool_gy)
            # Event-driven burst (round-2 system 5): the payoff
            # halo paints at the same stage as the held glow --
            # halo paints at the same stage as the held glow
            # -- before the characters -- so the payoff
            # lights the scene without washing the cast.
            # The prop stays crisp on top of its own light.
            for _eid, _atype, _rec in _burst_now:
                paint_energy_glow(img, _rec)
                _pool_gy = _pool_ground_y(
                    _rec["source_position"][0])
                if _pool_gy is not None:
                    paint_light_pool(img, _rec, _pool_gy)
                _effect_peak[_eid] = max(
                    _effect_peak.get(_eid, 0.0), _rec["intensity"])
                _effect_frames[_eid] = _effect_frames.get(_eid, 0) + 1
        # Round 16 (L02-D2): the lock target assembly -- a
        # grounded coop-door panel + padlock at each staged
        # lock anchor, on the MG layer (before the characters,
        # so the actor occludes the panel). The panel is the
        # door the script names ("chuồng gà"); the lock opens
        # on the insert event's turn phase. Flat fills, like
        # the props (no tod bake on staged elements).
        for _ln, _la in _lock_anchors.items():
            _gy = ground_ys[_ln]
            _pw, _pt = 170.0, _la[1] - 90.0
            d.rectangle([_la[0] - _pw / 2, _pt,
                         _la[0] + _pw / 2, _gy],
                        fill=(150, 110, 70),
                        outline=(30, 25, 20), width=4)
            for _sx in (-_pw / 6, _pw / 6):
                d.line([(_la[0] + _sx, _pt),
                        (_la[0] + _sx, _gy)],
                       fill=(30, 25, 20), width=3)
            d.line([(_la[0] - _pw / 2, _pt + 26),
                    (_la[0] + _pw / 2, _pt + 26)],
                   fill=(30, 25, 20), width=3)
            _draw_prop(d, _la[0], _la[1], kind="lock",
                       w=64, h=56,
                       open_u=_lock_open_u(t, _ln))
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
                _mirror = False
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
                    # No keyframe and not the speaker: the
                    # character's declared resting face wins;
                    # otherwise mirror the speaker's expression
                    # at half strength (round 7: a listener with
                    # a flat neutral face while the speaker
                    # worries reads as an NPC -- the child's brow
                    # stayed 0.0 deg in R6 while the adults'
                    # slanted 11-15 deg). A neutral speaker
                    # mirrors to neutral: no change.
                    _rest = _default_expr.get(n)
                    if _rest:
                        expr = _rest
                    elif (_speaker_expr_name
                            and _speaker_expr_name != "neutral"):
                        expr = "neutral"
                        _mirror = True
                    else:
                        expr = "neutral"
                # Param-dict path ONLY when W4 adds information
                # (extended-label blend, an active blink, or
                # lip-sync above the base mouth): otherwise the
                # legacy name path renders pixel-identically.
                _base_params = dict(
                    EXPRESSIONS.get(expr) or EXPRESSIONS["neutral"])
                _params = None
                if _mirror:
                    # The mirror blend rides the param-dict
                    # path; blinks and lip-sync apply onto it
                    # in the branch below.
                    _params = dict(blend_expressions_lib(
                        "neutral", _speaker_expr_name, 0.5))
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
            # W4 gaze: LOOK_AT events aim the eyes at their target.
            # Round-4 "hon": conversational attention is MUTUAL and
            # covers narration too. Before this, only the actor
            # looked at `other`, only in dialogue -- so in narration
            # shots (most of a first-person script) every listener
            # stared forward and the speaker stared forward: the NPC
            # look. Now the actor looks at the scene partner and
            # every other on-screen character looks at the actor,
            # in dialogue AND narration. Action shots keep
            # LOOK_AT-only gaze (actors watch what they do). The OTS
            # listener (back view) has no face.
            # Round 8 (R4-A5): micro-saccades. The look direction
            # alone is locked within a shot (gaze_for_target
            # saturates at its clamp for distant targets), so a
            # small seeded wander rides on top of it -- the eyes
            # drift around the look target instead of freezing on
            # it, and a targetless stare wanders around centre.
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
                if _target is None and shot["kind"] in (
                        "dialogue", "narration"):
                    if n == actor and other is not None \
                            and other in joints_pre:
                        _target = joints_pre[other]["head"]
                    elif n != actor and actor in joints_pre:
                        _target = joints_pre[actor]["head"]
                _base_gaze = (0.0, 0.0)
                if _target is not None:
                    _base_gaze = gaze_for_target(_head, _target)
                _wander = gaze_wander(t, _gaze_seeds.get(n, 0))
                _gaze = (_base_gaze[0] + _wander[0],
                         _base_gaze[1] + _wander[1])
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
                hand_grips=_grips.get(n),
                ground_kind=((_env_fitted or {}).get("ground")
                            or {}).get("kind"),
                elevation_deg=_char_elev_deg)
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
        # R17-D15: the puddle is a RAIN element, not a bend_pick
        # element -- without the rainy gate, the scene-leaked
        # bend_pick cue drew a rain puddle on sunny streets.
        if rainy and "bend_pick" in cues and prop.get("x"):
            _draw_puddle(d, prop["x"], _prop_ground_y)
        # prop: at the actor's hand once picked up / at the handover
        # midpoint during give, on the ground before that. In dialogue
        # shots the current holder (tracked in plan_shots) holds it.
        # Empty-cast shots have no hands: the prop is skipped.
        wx, wy = None, None
        _legacy_drew = False
        _home_x = staging[actor] + 220 if actor in staging else W // 2
        if _prop_machine is not None:
            # W4: held/moving props draw at their state-machine
            # transform (hand-attached, in use, or in transfer).
            # At-rest props were drawn behind the characters
            # above; pocket rests never reach _machine_draws.
            if _front_draws:
                d = ImageDraw.Draw(img, "RGBA")
                for (_pid, _dx, _dy, _dkind, _open_u, _st, _tip) \
                        in _front_draws:
                    _pw, _ph = None, None
                    if _dkind == "shield":
                        # Round-7: a held shield draws at the
                        # holder's head scale (a guard shield covers
                        # the torso), not the 76 px footprint -- the
                        # R6 shield read as a small grey tag. The
                        # diameter is the holder's head diameter
                        # (head ratio 0.34 of the drawn height); a
                        # holderless shield keeps the footprint.
                        # Round-8 (R7-D3): detail_at reports no
                        # holder until GRASPED, so an APPROACHING
                        # shield drew at the footprint and popped
                        # 4x at the grasp instant (72 -> 296 px in
                        # 6 frames). The shield is the same physical
                        # object from the moment it starts moving:
                        # size it by the actor of the event moving
                        # it, so the raise reads as a position move
                        # (the disc travelling up with the hands),
                        # not a growth.
                        _holder = (_machine_meta.get(_pid) or {}).get(
                            "holder")
                        if _holder is None:
                            _now = _t0 + t
                            for _ev in _shot_events:
                                if _ev.get("prop_id") != _pid:
                                    continue
                                if float(_ev.get("start_time", 0.0)) \
                                        <= _now <= float(_ev.get(
                                            "end_time", 0.0)):
                                    _holder = _id_to_name.get(str(
                                        _ev.get("actor_id") or ""))
                                    break
                        _m = metrics.get(_holder) \
                            if _holder else None
                        if _m is not None and _m[2] > 0:
                            _pw = _ph = 0.34 * float(_m[2])
                    _draw_prop(d, _dx, _dy, kind=_dkind, open_u=_open_u,
                               tip=_tip, w=_pw, h=_ph)
                    if _pid in _crack_now:
                        _fw, _fh = geometry_footprint(_dkind)
                        _alpha = int(220 * _crack_now[_pid])
                        for _line in crack_lines(
                                (_dx - _fw / 2.0, _dy - _fh / 2.0,
                                 _dx + _fw / 2.0, _dy + _fh / 2.0),
                                _pid):
                            d.line(_line, fill=(30, 25, 20, _alpha),
                                   width=3, joint="curve")
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
                            # Round-6 grip readability: the gate is
                            # footprint-aware (a two-hand grip puts
                            # each hand at the prop's edge, ~44 px
                            # from its centre for a 76 px footprint
                            # -- the old fixed 30 px gate dropped
                            # both repaints), and each fan repaints
                            # from its OWN hand position: both fans
                            # used to originate at the prop centre
                            # and collapse into one blob.
                            _gfw, _gfh = geometry_footprint(_dkind)
                            if abs(_hx - _dx) > _gfw / 2.0 + 30 \
                                    or abs(_hy - _dy) > _gfh / 2.0 + 30:
                                continue
                            _ex, _ey = _jn[_elbow_key]
                            draw_grip_fingers(
                                d, (_hx, _hy), (_hx - _ex, _hy - _ey),
                                chars[_holder], INK_RGB)
                            _grip_matches.append({
                                "pid": _pid, "holder": _holder,
                                "hand": _side})
                wx, wy = _front_draws[0][1], _front_draws[0][2]
            elif _behind_draws:
                wx, wy = _behind_draws[0][1], _behind_draws[0][2]
        elif has_prop and joints_now:
            _legacy_drew = True
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
            else:
                # Round 17 (L02-D7): a held prop stays in the
                # holder's hand in EVERY shot kind. The old
                # action-kind branch dropped the prop on the
                # ground even when the shot declared a holder
                # and the event history said it was held (Loop
                # 02 #11/#17: the key on the ground / at the
                # frame corner while An held it). Event history
                # wins over the plan_shots holder: the handover
                # event, not the shot plan, decides who holds
                # the prop at this instant.
                _holder = None
                _pids0 = shot.get("props") or []
                if _pids0:
                    _hid = _incoming_holder(
                        _compiled_all, str(_pids0[0]), _t0)
                    if _hid is not None:
                        _holder = _id_to_name.get(str(_hid))
                if _holder is None:
                    _holder = shot.get("prop_holder")
                if _holder in joints_now:
                    hx, hy = joints_now[_holder]["hand_r"]
                    wx, wy = hx + 10, hy + 14
                else:
                    wx, wy = prop["x"] or _home_x, _prop_ground_y - 6
            # Round 17 (R16-O1): head clearance for the
            # legacy draw too (same rule as the machine path;
            # the disc test gates it, so ground rests only move
            # when a head is at ground level beside them).
            if (shot.get("prop_kind") or "wallet") not in (
                    "shield", "hammer", "bag"):
                for _nm2, _jj2 in joints_now.items():
                    if _nm2 not in chars:
                        continue
                    _hc2 = _jj2.get("head")
                    if _hc2 is None:
                        continue
                    wx, wy = _clear_head(
                        (wx, wy), _hc2,
                        float(getattr(chars[_nm2], "head_r", 0.0)),
                        float(chars[_nm2].H))
                # Round 20 (R19-D2): worn-bag clearance for
                # the legacy draw too (same rule as the
                # machine path).
                if _worn_rects:
                    wx, wy = _clear_worn_bags((wx, wy), _worn_rects)
            _draw_prop(d, wx, wy,
                       kind=shot.get("prop_kind") or "wallet")
        # Round 17 (L02-D3): worn bags. A bag the owner possesses
        # but no event stages this frame is pocket-hidden by the
        # machine -- invisible for whole shots (Loop 02: An's
        # letter bag). Draw it worn: a diagonal strap over the
        # torso + the bag at the hip, following the owner's live
        # joints. Skipped when the machine or the legacy path
        # drew the prop this frame (an actively staged bag keeps
        # its staged presentation), and at top-view elevations
        # (rig joints do not project there -- the R16-2a gap).
        if _worn_draws and _char_elev_deg < 45.0:
            _drawn_pids = {d[0] for d in _machine_draws}
            if _legacy_drew:
                _lp = (shot.get("props") or [None])[0]
                if _lp is not None:
                    _drawn_pids.add(str(_lp))
            for _wd in _worn_draws:
                if _wd["pid"] in _drawn_pids:
                    continue
                _d2 = ImageDraw.Draw(img, "RGBA")
                _d2.line([_wd["strap_from"], _wd["strap_to"]],
                         fill=INK_RGB, width=_wd["strap_w"])
                _draw_prop(_d2, _wd["bx"], _wd["by"], kind="bag",
                           w=_wd["w"], h=_wd["h"])
        # Round 20 (effects richness): the strike impact
        # overlay -- an expanding ring at the contact point for
        # 3 frames after each strike moment, plus speed lines
        # trailing the hammer through the STRIKE phase
        # ([HOLD_U, STRIKE_U] of the cycle). Both anchor on
        # real state only: the sparks element's projected
        # centre (no sparks element / off-camera -> nothing)
        # and the hammer's own drawn position (machine draw,
        # else the striker's hammer hand). The overlay draws
        # last, over the characters, like a comic impact beat.
        _sparks_xy = _reactive_anchors.get("sparks_xy")
        _now = _t0 + t
        if _sparks_xy is not None and _strike_moments:
            _sx, _sy = _sparks_xy
            # Round 21: one most-recent strike drives the
            # whole impact beat -- glow pulse (8f) + dust puff
            # (10f) + ring (3f) + star (2f). The ring/star
            # drawing below is unchanged; the wider search
            # window only adds the glow and dust. No camera
            # shake: the camera stays FIXED within the shot.
            _age_f = None
            for _sm in _strike_moments:
                _a = (_now - _sm) * FPS
                if 0 <= _a < 10:
                    _age_f = _a
                    break
            if _age_f is not None:
                _glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                _gd = ImageDraw.Draw(_glow)
                if _age_f < 8:
                    _fade = 1.0 - _age_f / 8.0
                    _grow = 1.0 + 0.08 * _age_f
                    for _gr, _ga in ((54, 45), (36, 75), (20, 110)):
                        _r = _gr * _grow
                        _gd.ellipse(
                            [_sx - _r, _sy - _r * 0.62,
                             _sx + _r, _sy + _r * 0.62],
                            fill=(255, 190, 110, int(_ga * _fade)))
                # Dust: five dots fanning out and down from the
                # contact, expanding and fading over 10 frames.
                _dust_a = int(150 * (1.0 - _age_f / 10.0))
                if _dust_a > 0:
                    for _ang in (20.0, 60.0, 90.0, 120.0, 160.0):
                        _rad = math.radians(_ang)
                        _dist = 16.0 + 7.0 * _age_f
                        _dx = _sx + math.cos(_rad) * _dist
                        _dy = (_sy + 8.0
                               + math.sin(_rad) * _dist * 0.55)
                        _dr = 5.0 + 1.6 * _age_f
                        _gd.ellipse(
                            [_dx - _dr * 1.6, _dy - _dr,
                             _dx + _dr * 1.6, _dy + _dr],
                            fill=(205, 188, 155, _dust_a // 2))
                        _gd.ellipse(
                            [_dx - _dr, _dy - _dr * 0.7,
                             _dx + _dr, _dy + _dr * 0.7],
                            fill=(205, 188, 155, _dust_a))
                img.paste(_glow, (0, 0), _glow)
                if _age_f < 3:
                    _rr = 12.0 + 11.0 * _age_f
                    d.ellipse([_sx - _rr, _sy - _rr * 0.62,
                               _sx + _rr, _sy + _rr * 0.62],
                              outline=(255, 250, 235), width=3)
                    if _age_f < 2:
                        _sl = 30.0 - 8.0 * _age_f
                        d.line([(_sx - _sl, _sy), (_sx + _sl, _sy)],
                               fill=(255, 250, 235), width=2)
                        d.line([(_sx, _sy - _sl), (_sx, _sy + _sl)],
                               fill=(255, 250, 235), width=2)
            _strike_window = (HAMMER_CYCLE_STRIKE_U
                              - HAMMER_CYCLE_HOLD_U) \
                * HAMMER_CYCLE_SEC
            _in_strike = any(
                _sm - _strike_window <= _now < _sm
                for _sm in _strike_moments)
            _hammer_xy = None
            for (_pid, _dx, _dy, _dkind, _ou, _st, _tip) \
                    in _machine_draws:
                if _dkind == "hammer":
                    _hammer_xy = (_dx, _dy)
                    break
            if _hammer_xy is None:
                for (_nm, _ss, _se) in _strike_spans:
                    if _ss <= _now <= _se and _nm in joints_now:
                        _hammer_xy = joints_now[_nm].get("hand_r")
                        break
            _prev = _prev_hammer_xy[0]
            if (_in_strike and _hammer_xy is not None
                    and _prev is not None):
                _vx = _hammer_xy[0] - _prev[0]
                _vy = _hammer_xy[1] - _prev[1]
                if _vy > 6.0 and (_vx * _vx + _vy * _vy) ** 0.5 > 8.0:
                    _sp = (_vx * _vx + _vy * _vy) ** 0.5
                    _ux, _uy = _vx / _sp, _vy / _sp
                    _px, _py = -_uy, _ux
                    # Round 21: longer trails (1.2x speed
                    # span, was 0.7x) and thicker strokes -- the
                    # lines already fire on f16-f18; they must
                    # READ at full-frame distance.
                    for _off, _wd in ((-12.0, 3), (0.0, 4),
                                      (12.0, 3)):
                        _bx = _hammer_xy[0] + _px * _off
                        _by = _hammer_xy[1] + _py * _off
                        d.line([(_bx - _ux * _sp * 1.5,
                                 _by - _uy * _sp * 1.5),
                                (_bx - _ux * _sp * 0.3,
                                 _by - _uy * _sp * 0.3)],
                               fill=(255, 248, 230), width=_wd)
            _prev_hammer_xy[0] = _hammer_xy
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
                    "tip": ([float(_tip[0]), float(_tip[1])]
                            if _tip is not None else None),
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
    # Round-7 head-intrusion audit (R6-D1): frames where a HELD
    # prop's drawn point (striking tip when present, else the draw
    # position) lands inside another character's head disc. Sparse
    # by design: the list caps at 200 entries, the count is exact.
    _head_intrusions: list[dict] = []
    _head_intrusion_count = 0
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
            for _lfn, _lph in listen_nods.values():
                _lfn(_st)  # phase rides inside the nod now
    # The D2 frozen crop (_frozen, _crop_notes, _standing_box)
    # was computed before the environment build above (round 6)
    # and is reused here unchanged.
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
        (shot["shot_type"] == "object_insert"
         or (shot["shot_type"] == "extreme_close_up"
             and _ecu_prop_action))
        and not still_only
        and _split is None
        and (_prop_machine is not None or has_prop))
    _insert_anchor: dict | None = None
    # ---- T1: executed camera life ----------------------------------
    # Scripted DOLLY_*/PAN_* are EXECUTED here as an image-level
    # micro move (and reported as executed, never as a limitation).
    # The scene camera itself stays fixed: no parallax is invented,
    # and framing still changes only by cut. An UNSCRIPTED auto
    # push-in on quiet shots is OPT-IN ONLY (see below): the locked
    # D2 rule + channel study R9 fix the camera within a shot, and
    # the reference study observed no in-shot camera motion.
    _movement_req_early = normalize_movement(shot.get("camera_movement"))
    _dolly: dict | None = None
    _auto_drift = False
    _executed_movement = "STATIC"
    if _movement_req_early in ("DOLLY_IN", "DOLLY_OUT"):
        _dolly = {"zoom": 0.045, "pan": 0.0,
                  "out": _movement_req_early == "DOLLY_OUT"}
        _executed_movement = _movement_req_early
    elif _movement_req_early in ("PAN_LEFT", "PAN_RIGHT"):
        _dolly = {"zoom": 0.012, "out": False,
                  "pan": -0.020 if _movement_req_early == "PAN_LEFT" else 0.020}
        _executed_movement = _movement_req_early
    _has_action_events = bool(names) and any(
        _per_actor.get(n) for n in names) if _per_actor else False
    # Auto push-in is OPT-IN ONLY via the explicit shot/package
    # flag "auto_camera_drift". Default OFF per D2/R9 (above).
    _auto_drift_opt_in = bool(shot.get("auto_camera_drift")
                              or package.get("auto_camera_drift"))
    if (_dolly is None and not still_only and shot["kind"] != "action"
            and not _has_action_events and _auto_drift_opt_in):
        _dolly = {"zoom": 0.050, "pan": 0.006, "out": False}
        _executed_movement = "DOLLY_IN"
        _auto_drift = True
    # Exposure floor is OPT-IN ONLY via the explicit shot/package
    # flag "exposure_floor". A global RGB gain remaps the exact
    # palette colors (face cream, prop fills) the pixel QA
    # contracts and character consistency rely on — proven by 5
    # regressions on the merged tree (2026-11-14). Dark shots are
    # fixed in the environment palette, not by brightening
    # finished frames (see apply_exposure_floor's docstring).
    _exposure_floor_opt_in = bool(shot.get("exposure_floor")
                                  or package.get("exposure_floor"))
    _exposure_gains: list[float] = []
    _shot_gain: float | None = None
    for fi in range(n_frames):
        t = (duration / 2.0) if still_only else fi / FPS
        for n, fn in fns.items():
            if n == actor and give_fn is not None:
                give_fn(t)
            else:
                fn(t)
        if talk_nod is not None:
            talk_nod(t)
        for _lfn, _lph in listen_nods.values():
            _lfn(t + _lph)
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
                        # Head: the hero-insert lean rule needs the
                        # holder's head position (same frame).
                        # Shoulder/knees/feet: the pass-2 glow
                        # exclusion follows the posed limbs
                        # (round-7: the static standing box ate
                        # the insert halo whenever the holder
                        # stood at the prop).
                        "hip": [float(v) for v in
                                joints_now[n]["hip"]],
                        "head": [float(v) for v in
                                 joints_now[n]["head"]],
                        "shoulder": [float(v) for v in
                                     joints_now[n]["shoulder"]],
                        "knee_l": [float(v) for v in
                                   joints_now[n]["knee_l"]],
                        "knee_r": [float(v) for v in
                                   joints_now[n]["knee_r"]],
                        "foot_l": [float(v) for v in
                                   joints_now[n]["foot_l"]],
                        "foot_r": [float(v) for v in
                                   joints_now[n]["foot_r"]],
                        "head_r": float(getattr(
                            chars[n], "head_r", 0.0)),
                        "H": float(chars[n].H)}
                    for n in names},
                "draws": _telemetry_draws})
            # Round-7 head-intrusion audit (R6-D1): a held prop
            # drawn over another character's face. The point is the
            # prop's striking tip when the draw carries one (the
            # hammer head), else the draw position; the head disc
            # comes from the live joints of the same frame.
            # Round 8 (R7-D1): the holder's OWN head counts too --
            # the wind-up swept the stone and hammer across the
            # striker's own face while the audit only watched
            # bystanders. Resting props never count (only held
            # states intrude).
            for _dr in _telemetry_draws:
                if _dr.get("state") not in (
                        "GRASPED", "ATTACHED_TO_HAND", "IN_USE"):
                    continue
                _holder = _dr.get("holder")
                if _holder not in names:
                    continue
                _pt = _dr.get("tip") or (_dr["x"], _dr["y"])
                for _other in names:
                    _hc = joints_now[_other]["head"]
                    _hr = float(getattr(chars[_other], "head_r", 0.0))
                    _dd = math.hypot(_pt[0] - _hc[0], _pt[1] - _hc[1])
                    if _prop_intrudes_head(
                            _pt, _hc, _hr, float(chars[_other].H)):
                        _head_intrusion_count += 1
                        if len(_head_intrusions) < 200:
                            _head_intrusions.append({
                                "frame": int(fi),
                                "time": round(float(_t0 + t), 3),
                                "pid": _dr.get("pid"),
                                "kind": _dr.get("kind"),
                                "holder": _holder,
                                "other": _other,
                                "self": _other == _holder,
                                "distance_px": round(_dd, 1),
                                "head_r_px": round(_hr, 1)})
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
            # object_insert / ECU prop-action (stills / split-screen only — the
            # multi-frame path defers to pass 2): the prop
            # position is only known once a frame is built.
            # Anchor from THIS first frame's prop position (or
            # the full-body boxes when no prop is drawn), then
            # freeze for the whole shot.
            if _prop_xy is not None:
                _px, _py = _prop_xy
                # Hero prop grammar: the still-frame insert uses
                # the SAME footprint-sized subject box as pass 2
                # (kind from this frame's telemetry draws, else
                # the shot's prop_kind). No hand median exists
                # at frame 0, so the box is prop-only.
                _kind0 = shot.get("prop_kind") or "wallet"
                for _d0 in _telemetry_draws or []:
                    if _d0.get("kind"):
                        _kind0 = _d0["kind"]
                        break
                _box0, _fields0 = _insert_subject_box(
                    _px, _py, _kind0, None, W, H)
                _subjects0 = [_box0]
                _insert_anchor = {
                    "source": "first_frame_prop", "kind": _kind0,
                    "x": _fields0["cx"], "y": _fields0["cy"],
                    "n_draws": 1,
                    "n_hands": 0, "pair_anchored": False,
                    "n_pairs": 0}
                if (_fields0["cx"], _fields0["cy"]) != (_px, _py):
                    _insert_anchor.update(
                        {"clamped_to_frame": True,
                         "raw_x": _px, "raw_y": _py})
                _insert_anchor.update(_fields0)
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
            if _insert_anchor is not None:
                _cw0 = float(_frozen_crop0["crop_rect"][2]
                             - _frozen_crop0["crop_rect"][0])
                if _cw0 > 0 and _insert_anchor.get("prop_w"):
                    _insert_anchor["screen_share_w"] = round(
                        _insert_anchor["prop_w"] / _cw0, 4)
                _insert_anchor["applied_scale"] = float(
                    _safe_shot0["camera"]["scale"])
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
        # ---- T1/T2: camera life, then the exposure floor ---------------
        # Both are image-level ops applied to the finished frame, so they
        # run after cropping/occlusion and BEFORE subtitles: the caption
        # stays the same 64 px white on every frame and is never
        # brightened or drifted with the picture.
        if _dolly is not None and not _defer_framing:
            # Deferred framing (object_insert pass 2) re-crops the saved
            # frames later; a dolly baked in here would be applied twice,
            # so those shots keep the fixed camera.
            _u = 0.0 if n_frames <= 1 else fi / float(n_frames - 1)
            img = apply_micro_dolly(img, _u, zoom=_dolly["zoom"],
                                    pan=_dolly["pan"], out=_dolly["out"])
        # One gain per shot, measured on the first finished frame: the
        # dolly/exposure ops happen before captions, and a per-frame gain
        # would track the moving characters as a slow brightness flicker.
        # Opt-in only (see the flag above): without it the gain is 1.0
        # and apply_gain is the identity, so palette colors stay exact.
        if _shot_gain is None:
            _shot_gain = (measured_exposure_gain(img)
                          if _exposure_floor_opt_in else 1.0)
            _exposure_gains.append(_shot_gain)
        img = apply_gain(img, _shot_gain)
        # ---- subtitles last, always at fixed 64 px --------------------
        if windows and not _defer_framing:
            d = ImageDraw.Draw(img, "RGBA")
            for w in windows:
                if w["start"] <= t < w["end"] or (
                        t >= duration - 1 / FPS and w is windows[-1]):
                    draw_phrase(d, w["phrase"], lift_px=(
                        _MAP_SUBTITLE_LIFT_PX if _is_map else 0.0))
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
            [_standing_box(n, "full") for n in names],
            W, H)
        (_safe_shot2, _safe_focus2, _notes2,
         _frozen_crop2) = _freeze_anchor(_subjects2, [])
        _frozen = (_safe_shot2, _safe_focus2, _frozen_crop2)
        safe_shot, safe_focus, _frozen_crop = _frozen
        _cw2 = float(_frozen_crop2["crop_rect"][2]
                     - _frozen_crop2["crop_rect"][0])
        if _cw2 > 0 and _insert_anchor.get("prop_w"):
            _insert_anchor["screen_share_w"] = round(
                _insert_anchor["prop_w"] / _cw2, 4)
        _insert_anchor["applied_scale"] = float(
            safe_shot["camera"]["scale"])
        # Round 17 (R16-D1): bystander-head exclusion for the
        # deferred crop. The subject box is small (180x120 floor)
        # but the ECU crop at the 3.4x scale cap is 565x318, so a
        # bystander staged near the insert point lands inside the
        # crop even though no subject box touches them (Loop 02
        # ECU: Ba Tu's face top-right in every frame). Shift the
        # crop rect away from intruding non-subject heads; the
        # prop anchor stays inside with margin and the rect stays
        # in frame. Computed once from medians: the crop stays
        # frozen within the shot (the RicksClips rule).
        if _insert_anchor.get("x") is not None:
            _heads2 = _median_bystander_heads(_grip_telemetry)
            _rect2, _excl2 = _exclude_heads_from_crop(
                list(_frozen_crop2["crop_rect"]),
                (_insert_anchor["x"], _insert_anchor["y"]),
                _heads2, 40.0, W, H)
            if _excl2 is not None:
                _frozen_crop2["crop_rect"] = _rect2
                _frozen = (_safe_shot2, _safe_focus2, _frozen_crop2)
                safe_shot, safe_focus, _frozen_crop = _frozen
                _insert_anchor["bystander_crop_exclusion"] = _excl2
                _crop_notes.append(
                    "bystander crop exclusion: "
                    f"cleared={_excl2['cleared']} "
                    f"remaining={_excl2['remaining']}")
        _crop_notes.extend(_notes2)
        _crop_notes.append(
            "insert two-pass: crop frozen from "
            f"{_insert_anchor['source']} "
            f"(kind={_insert_anchor['kind']}, "
            f"n_draws={_insert_anchor['n_draws']})")
        # Glow exclusions (round 6, R2-F1; round-7 rework): the
        # repainted halos must not wash the cast on the flattened
        # cropped frames. The exclusion follows the POSED limbs
        # per frame (see _glow_exclusion_boxes) -- the static
        # standing box erased the halo whenever the holder stood
        # at the prop. A hole around each glow source stays lit
        # (the glowing prop itself + the flesh touching it).
        _crx0, _cry0, _crx1, _cry1 = (
            float(v) for v in _frozen_crop["crop_rect"])
        _czx = W / max(_crx1 - _crx0, 1.0)
        _czy = H / max(_cry1 - _cry0, 1.0)
        _glow_hole_r = GLOW_SOURCE_HOLE_STAGING_PX * _czx
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
                _glow_exclusions = _glow_exclusion_boxes(
                    _joints2, names, _frozen_crop["crop_rect"],
                    _img2.size)
                for _pid2 in _machine_pids:
                    _glow2 = _prop_machine.energy_glow_at(
                        _pid2, _t0 + _fi2 / FPS, _joints2)
                    if _glow2 is not None and _glow2["radius"] > 0:
                        _mapped2 = _screen_glow_record(
                            _glow2, _frozen_crop["crop_rect"],
                            _img2.size)
                        _sx2, _sy2 = _mapped2["source_position"]
                        paint_energy_glow_excluding(
                            _img2, _mapped2, _glow_exclusions,
                            holes=[(_sx2, _sy2, _glow_hole_r)])
                # Event-driven burst, deferred like the held halo:
                # re-derived from this frame's telemetry joints and
                # painted post-crop with a capped radius, so an
                # insert zoom cannot magnify it into a wash.
                for _eid2, _atype2, _rec2 in _burst_records(
                        _t0 + _fi2 / FPS, _joints2):
                    _mapped_rec2 = _screen_glow_record(
                        _rec2, _frozen_crop["crop_rect"], _img2.size)
                    _sx2, _sy2 = _mapped_rec2["source_position"]
                    paint_energy_glow_excluding(
                        _img2, _mapped_rec2, _glow_exclusions,
                        holes=[(_sx2, _sy2, _glow_hole_r)])
                    _effect_peak[_eid2] = max(
                        _effect_peak.get(_eid2, 0.0),
                        _rec2["intensity"])
                    _effect_frames[_eid2] = _effect_frames.get(
                        _eid2, 0) + 1
            if _occluder is not None:
                _img2.paste(_occluder, (0, 0), _occluder)
            if windows:
                _d2 = ImageDraw.Draw(_img2, "RGBA")
                for _w2 in windows:
                    if _w2["start"] <= _t2 < _w2["end"] or (
                            _t2 >= duration - 1 / FPS
                            and _w2 is windows[-1]):
                        draw_phrase(_d2, _w2["phrase"], lift_px=(
                            _MAP_SUBTITLE_LIFT_PX if _is_map else 0.0))
                        break
            _img2.save(_path2, compress_level=1)
    # Camera report (Stage 3 / F9): the executed viewpoint + the
    # movement semantics. A requested non-STATIC movement renders
    # with a FIXED camera and a recorded limitation — never a
    # silent crop-zoom presented as a camera move. A dutch angle
    # renders with eye-level geometry and a recorded limitation
    # (the frame tilt is not applied: the rotation overscan needed
    # to fill the corners would break the F2 head-size cap).
    # ---- T3/T4: parity telemetry in FINAL frame coordinates --------
    # The scorecard cannot judge character framing or captions from a
    # plan that does not carry them, so the renderer reports what it
    # actually drew. Boxes are mapped through the SAME frozen crop and
    # micro-dolly rects the frames went through, at mid-shot.
    _parity_boxes: list[dict] = []
    _parity_captions: list[dict] = []
    if names and _frozen is not None:
        _crop_rect = None
        if float(safe_shot["camera"]["scale"]) > 1.0:
            _crop_rect = _frozen_crop["crop_rect"]
        _dolly_apply = _dolly is not None and not _defer_framing
        for _bn in names:
            _b = _standing_box(_bn, "full")
            _p0 = (_b["cx"] - _b["half_w"], _b["head_y"])
            _p1 = (_b["cx"] + _b["half_w"], _b["foot_y"])
            if _crop_rect is not None:
                _p0 = _map_rect_point(_p0, _crop_rect, (W, H))
                _p1 = _map_rect_point(_p1, _crop_rect, (W, H))
            if _dolly_apply:
                _dr = dolly_rect((W, H), 0.5, zoom=_dolly["zoom"],
                                 pan=_dolly["pan"], out=_dolly["out"])
                _p0 = _map_rect_point(_p0, _dr, (W, H))
                _p1 = _map_rect_point(_p1, _dr, (W, H))
            _bh = float(char_heights.get(_bn) or getattr(chars[_bn], "H", 0.0))
            _hr = float(getattr(chars[_bn], "head_r", 0.0))
            _x0, _x1 = sorted((_p0[0], _p1[0]))
            _y0, _y1 = sorted((_p0[1], _p1[1]))
            _parity_boxes.append({
                "name": _bn,
                "bbox": [round(_x0, 1), round(_y0, 1),
                         round(_x1, 1), round(_y1, 1)],
                # head DIAMETER over body height: the 0.34 identity lock
                # is a diameter ratio, head_r is a radius.
                "head_ratio": round(2.0 * _hr / _bh, 4) if _bh else None,
                # A close-up legitimately pushes the other characters out
                # of frame; measuring them as "not in the safe area"
                # would be a false failure.
                "in_frame": bool(_x1 > 0 and _y1 > 0
                                 and _x0 < W and _y0 < H),
            })
    for _cw in windows or []:
        if not isinstance(_cw, dict) or not _cw.get("phrase"):
            continue
        try:
            _parity_captions.append(caption_metrics(_cw["phrase"]))
        except Exception:  # noqa: BLE001 - metrics never fail a render
            continue
    _movement_req = normalize_movement(shot.get("camera_movement"))
    _movement_limitation = None
    if _movement_req != "STATIC" and _executed_movement == "STATIC":
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
    elif _elev_capped:
        _camera_limitation = (
            "establishing elevation cap: the requested angle "
            f"{_angle_requested} ({_requested_elev:.0f} deg) would "
            "pitch the frustum below the horizon (0 px of sky); "
            "the executed elevation is capped at "
            f"{ESTABLISHING_MAX_ELEV_DEG:.0f} deg so the place and "
            "the sky stay in frame; requested angle recorded as "
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

    def _effect_records_list():
        """Per-shot effect telemetry: one record per burst event
        that painted at least one frame, plus the set-piece
        reaction record when it fired. Coverage verification reads
        this, never the event list alone: an event that never
        painted (out of span, pocket-hidden, unanchored) leaves no
        record."""
        _out = []
        for _eid, _peak in sorted(_effect_peak.items()):
            _ev = next((e for e in _shot_events
                        if str(e.get("action_id")) == _eid), None)
            _out.append({
                "event_id": _eid,
                "effect": (_ev or {}).get("action_type"),
                "prop_id": (_ev or {}).get("prop_id"),
                "peak_intensity": round(_peak, 3),
                "frames": _effect_frames.get(_eid, 0),
            })
        if _reaction_acc["frames"] > 0:
            _out.append({
                "event_id": None,
                "effect": "SET_PIECE_REACTION",
                "prop_id": None,
                "peak_intensity": round(_reaction_acc["peak"], 3),
                "frames": _reaction_acc["frames"],
            })
        return _out

    return {
        "index": shot["index"], "scene": shot["scene"],
        "kind": shot["kind"], "speaker": shot.get("speaker"),
        "shot_type": shot["shot_type"], "duration": duration,
        "n_frames": len(frames_written),
        "applied_scale": float(safe_shot["camera"]["scale"]),
        "anchor_tier": _anchor_tier,
        "locomotion_widened": bool(_locomotion_widened),
        "characters_suppressed_for_map": bool(_map_suppressed),
        "subtitle_lift_px": (
            _MAP_SUBTITLE_LIFT_PX if _is_map else 0.0),
        "camera_movement": shot.get("camera_movement", "STATIC"),
        "camera_movement_requested": _movement_req,
        "camera_movement_executed": _executed_movement,
        "camera_auto_drift": _auto_drift,
        "exposure_gain_max": round(max(_exposure_gains or [1.0]), 4),
        "character_boxes": _parity_boxes,
        "fg_clearance": _fg_clearance,
        "captions": _parity_captions,
        "movement_limitation": _movement_limitation,
        "camera_angle": _angle,
        "camera_angle_requested": _angle_requested,
        "camera_elevation_deg": float(_exec_elev)
        if _exec_elev is not None else float(elevation_for_angle(_angle)),
        "camera_elevation_requested_deg": float(_requested_elev)
        if _requested_elev is not None else float(elevation_for_angle(_angle)),
        "camera_elevation_capped": _elev_capped,
        "camera_position": tuple(shot_cam.position),
        "camera_target": tuple(shot_cam.target),
        "camera_radius_scale": _radius_scale,
        "camera_limitation": _camera_limitation,
        "crop_anchor": _frozen[2] if _frozen is not None else None,
        "crop_frozen": _frozen is not None,
        "crop_notes": list(_crop_notes),
        "insert_two_pass": _defer_framing,
        "insert_anchor": _insert_anchor,
        "lock_anchors": {n: [float(a[0]), float(a[1])]
                         for n, a in _lock_anchors.items()},
        "lock_open_u_end": {n: round(_lock_open_u(duration, n), 3)
                            for n in _lock_events},
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
        "insert_idle_windows": list(_insert_idle_windows),
        "effect_records": _effect_records_list(),
        "prop_machine": _prop_machine is not None,
        "prop_diagnostics": list(_prop_diagnostics),
        "prop_rest_kinds": dict(_rest_kinds),
        "prop_support_rests": dict(_support_records),
        "furniture_staging": dict(_furniture_staging),
        "staging_fit_steps": _staging_fit_steps,
        "anvil_staging": dict(_anvil_staging),
        "pick_staging": dict(_pick_staging),
        "place_staging": dict(_place_staging),
        "support_sightline": {"moved": dict(_sightline_moved),
                              "skipped": _sightline_skipped},
        "shield_staging": dict(_shield_staging),
        "shield_disc_alignment": dict(_shield_disc_align),
        "bystander_clearance": _bystander_clearance,
        "head_clearance": _head_clearance,
        "head_intrusions": list(_head_intrusions),
        "head_intrusion_count": _head_intrusion_count,
        "hammer_contact_snaps": list(_contact_snaps),
        "camera_radius_scale": _radius_scale,
        "camera_pullback": _camera_pullback,
        "anchor_tier": _anchor_tier,
        "anchor_tier_capped": _tier_capped,
        "seated_at_start": dict(_seated_at_start),
        "held_at_start": {n: str(e.get("action_id"))
                          for n, e in _held_at_start.items()},
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
