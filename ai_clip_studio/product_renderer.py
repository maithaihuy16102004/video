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
    draw_character_v4, make_character, make_character_instance,
    resolve_view,
)
from .animation.landmarks import landmark_boxes
from .animation.primitives import (
    give_to, idle, kneel_pick, nod, run_to, standing, walk_to, wave,
)
from .animation.rig import check_bone_lengths, lerp, smoothstep
from .camera_planner import CameraPlanner
from .renderer25d.camera import PerspectiveCamera
from .renderer25d.render import render_frame
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
}

EMOTION_WORDS = (
    ("vui", "happy"), ("hạnh phúc", "happy"), ("cười", "happy"),
    ("buồn", "sad"), ("khóc", "sad"), ("ngạc nhiên", "surprised"),
    ("ủa", "surprised"), ("ôi", "surprised"), ("lo", "worried"),
    ("sợ", "worried"), ("hoảng", "worried"), ("tức", "angry"),
    ("giận", "angry"),
)

# F4 (TEST C Phase 2): emotion words match on WORD BOUNDARIES, not
# substrings. The old substring match fired "surprised" on nearly
# every gentle line because "của" contains "ủa" -- so "Bà ơi, bà cầm
# ô của cháu đi." showed a shocked face. A word matches only as a
# standalone word/phrase ("ủa" alone, never inside "của").
EMOTION_PATTERNS = tuple(
    (re.compile(r"\b" + re.escape(word) + r"\b"), expr)
    for word, expr in EMOTION_WORDS)

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


def sx(world_x: float) -> int:
    x, _, _, _ = CAM.project((world_x, 0.0, WORLD_Z), W, H)
    return int(round(x))


def ws(screen_x: float) -> float:
    lo, hi = -6.0, 7.0
    for _ in range(28):
        mid = (lo + hi) / 2.0
        mx, _, _, _ = CAM.project((mid, 0.0, WORLD_Z), W, H)
        if mx < screen_x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def expression_for(text: str) -> str:
    low = text.lower()
    for pattern, expr in EMOTION_PATTERNS:
        if pattern.search(low):
            return expr
    return "neutral"


def map_character(char: dict, index: int):
    """Package character dict -> Stickman. The engine ships a small
    registry of locked instances (make_character_instance); any name
    in that registry is used as-is, and EVERY other name is built
    generically from the package's own fields (template / voice_hint /
    description keywords) — no story names, no per-story branches in
    this pipeline. The registry lookup is a name lookup, not story
    logic: removing it would only change the exact suit colours of
    those instances, never the flow."""
    name = str(char.get("name", f"char{index}"))
    key = name.strip().lower()
    try:
        return make_character_instance(key, height=CHAR_H)
    except (ValueError, KeyError):
        pass  # not a locked instance — build generically below
    desc = f"{char.get('description', '')} {char.get('voice_hint', '')}".lower()
    template = char.get("template") or "male"
    if template not in ("male", "female", "child", "elderly"):
        # Elderly first: "bà lão" contains "bà" (female marker) but the
        # "lão"/"già" marker is the stronger identity signal.
        if any(w in desc for w in ("trẻ", "bé", "con nít", "child")):
            template = "child"
        elif any(w in desc for w in ("già", "lão", "ông lão", "elderly")):
            template = "elderly"
        elif any(w in desc for w in ("nữ", "gái", "cô", "bà", "female")):
            template = "female"
        else:
            template = "male"
    body = char.get("body_variant") or "standard"
    if body not in ("slim", "standard", "sturdy"):
        body = "sturdy" if any(w in desc for w in ("to", "vạm vỡ", "mập")) \
            else "slim" if any(w in desc for w in ("gầy", "mảnh")) \
            else "standard"
    kwargs = {
        "template": template,
        "name": name,
        "suit": char.get("jacket_color") or PALETTE[index % len(PALETTE)],
        "body_variant": body,
        "height": CHAR_H,
    }
    if char.get("costume") in ("dress", "uniform"):
        kwargs["costume"] = char["costume"]
    if char.get("hair_style") in ("short", "long", "tuft", "side_part"):
        kwargs["hair_style"] = char["hair_style"]
    if char.get("hat") in ("bowler", "none"):
        kwargs["hat"] = char["hat"]
    moustache = char.get("moustache_style")
    if moustache in ("toothbrush", "handlebar", "full"):
        kwargs["moustache"] = True
        kwargs["moustache_style"] = moustache
    elif "râu" in desc or "ria" in desc:
        kwargs["moustache"] = True
    if char.get("glasses") is True or "kính" in desc:
        kwargs["glasses"] = True
    return make_character(**kwargs)


def _boxes_from_landmark(name: str) -> list[Box3D]:
    out = []
    for b in landmark_boxes(name):
        out.append(Box3D(center=tuple(b["center"]), size=tuple(b["size"]),
                         color=tuple(b["color"]),
                         name=b.get("name", "box"),
                         label=b.get("label", "")))
    return out


def build_scene(location_keyword: str, setting: str, mood: str,
                time_of_day: str) -> tuple[list[Box3D], tuple, tuple, bool]:
    """Location -> 2.5D boxes + sky/ground colours + rain flag.
    Only three landmark libraries exist (great_wall, eiffel_tower,
    rainy_street); anything else is a generic street built from the
    same box vocabulary."""
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
        # Shopfronts (generic Vietnamese street, not story-specific):
        # labelled signs on the background buildings.
        boxes += [
            Box3D(center=(-4.5, 2.3, -11.15), size=(1.2, 0.5, 0.08),
                  color=(90, 30, 30), name="shop_pho", label="PHỞ"),
            Box3D(center=(4.8, 2.1, -10.15), size=(1.4, 0.5, 0.08),
                  color=(30, 60, 90), name="shop_cafe", label="CÀ PHÊ"),
        ]
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
    return boxes, sky[0], sky[1], rainy


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
    beat (voice_duration kept for subtitle windows). Shot type: Gemini's
    shot plan when it references a real line, else a cue-based rule.
    The prop holder is tracked across the shot list (bend_pick -> the
    picker holds it, give -> the receiver holds it, put_away -> hidden)
    so the prop is drawn at the right hand in dialogue shots."""
    durations = {e["line_index"]: e["duration"] for e in timeline}
    gemini_shots = {(s.get("scene"), s.get("line_index")): s.get("shot_type")
                    for s in package.get("gemini_shots", [])}
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
    holder = None  # who currently holds the prop (wallet-like object)
    for scene in package["scenes"]:
        number = scene["number"]
        loc = scene.get("location", {}) or {}
        setting = loc.get("setting") or scene.get("setting", "")
        lead = float(scene.get("action_lead_sec") or 0.0)
        cues = list(scene.get("action_cues") or [])
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
                if cue == "bend_pick":
                    holder = actor
                elif cue == "give" and actor is not None:
                    holder = next((n for n in char_names if n != actor),
                                  None)
                elif cue == "take":
                    holder = actor
                elif cue == "put_away":
                    holder = None
                shots.append({
                    "scene": number, "kind": "action", "speaker": None,
                    "text": "", "line_index": None,
                    "duration": dur,
                    "action_cues": [cue] if cue else cues,
                    "scene_cues": cues,
                    "actor": actor,
                    "action_text": scene.get("action_text", ""),
                    "visible": [n for n in char_names
                                if first_scene[n] <= number],
                    # bend_pick is a FULL-BODY action (kneel + wallet +
                    # puddle at the ground): medium frames the whole
                    # body, not a tight insert. A 3.4x object_insert on
                    # one kneeling subject cuts the head off (verified
                    # in the v3 storyboard still). give/take stay
                    # object_insert: two subjects + the wallet between
                    # them frame correctly at that scale.
                    "shot_type": "tracking" if cue in (
                        "walk", "walk_fast", "run", "board") else
                    "object_insert" if cue in ("give", "take") else "medium",
                    "prop_holder": holder,
                    "location_keyword": loc.get("location_keyword", "street"),
                    "setting": setting, "mood": loc.get("mood", "warm"),
                    "time_of_day": loc.get("time_of_day", "day"),
                })
        for line in scene.get("lines", []):
            line_no += 1
            st = gemini_shots.get((number, line_no))
            if st not in SHOT_SCALE:
                if line_no == 1 and number == 1:
                    st = "establishing"
                elif any(c in cues for c in ("bend_pick", "give", "take")):
                    st = "object_insert"
                elif expression_for(line["text"]) != "neutral":
                    st = "close_up"
                else:
                    st = "medium"
            shots.append({
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
                "prop_holder": holder,
                "visible": [n for n in char_names
                            if first_scene[n] <= number],
                "shot_type": st,
                "location_keyword": loc.get("location_keyword", "street"),
                "setting": setting, "mood": loc.get("mood", "warm"),
                "time_of_day": loc.get("time_of_day", "day"),
            })
    # Boarding is permanent within the video: once a character boards
    # the bus, later shots stage them at the bus door.
    boarded: dict[str, float] = {}
    for s in shots:
        if s["kind"] == "action" and "board" in (s.get("action_cues") or []) \
                and s.get("actor"):
            boarded[s["actor"]] = BUS_DOOR_X
        elif boarded:
            s["staging_override"] = dict(boarded)
    return shots


def _font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def _draw_prop(draw, x, y, w=76, h=50):
    draw.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2],
                           radius=9, fill=PROP_FILL, outline=INK_RGB, width=3)
    draw.line([(x - w / 2 + 8, y), (x + w / 2 - 8, y)],
              fill=INK_RGB, width=3)


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


def _draw_bus_details(img):
    """F6 (TEST C Phase 2): 2D bus details over the projected bus
    body -- wheels, headlight + glow, taillight, destination sign,
    door outline, side stripe. The 3D boxes alone read as a building:
    the kerb occludes the 3D wheels, the door is a dark slab, and
    there are no lights. Every position is derived by projecting the
    bus box corners with CAM.project, so the details track the bus
    at any camera -- no hardcoded pixels. Drawn on the static
    background (before the characters), so a boarding character
    occludes the bus correctly. The wheels straddle the body's
    bottom edge and may overlap the bench/kerb in front of the bus
    -- a small depth trade-off for a bus that reads as a bus at a
    glance (the alternative, 3D-only wheels, is invisible)."""
    cx, cy, cz = BUS_BODY_CENTER
    sx_, sy_, sz_ = BUS_BODY_SIZE
    zf = cz + sz_ / 2.0  # front face, facing the camera
    pts = [CAM.project((cx + dx * sx_ / 2.0, cy + dy * sy_ / 2.0, zf),
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
    dx0, _, _, _ = CAM.project((BUS_DOOR_X - 0.25, 0.2, zf), W, H)
    dx1, _, _, _ = CAM.project((BUS_DOOR_X + 0.25, 0.2, zf), W, H)
    _, dy0, _, _ = CAM.project((BUS_DOOR_X, 1.6, zf), W, H)
    _, dy1, _, _ = CAM.project((BUS_DOOR_X, 0.2, zf), W, H)
    d.rectangle([dx0, dy0, dx1, dy1],
                outline=(220, 230, 240, 255), width=3)
    d.line([((dx0 + dx1) / 2, dy0), ((dx0 + dx1) / 2, dy1)],
           fill=(220, 230, 240, 255), width=2)
    # Wheels: dark circles + light hubcaps, straddling the bottom
    # edge so they read as wheels under the body skirt.
    for wx in BUS_WHEEL_X:
        wcx, _, _, _ = CAM.project((wx, 0.15, zf), W, H)
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
    chars: dict[str, object] = {}
    # Only the scene's cast is drawn (see plan_shots: a character is
    # visible only from the scene where they first speak or act).
    _visible = shot.get("visible") or [
        str(c["name"]) for c in package["characters"]]
    for i, c in enumerate(package["characters"]):
        if str(c["name"]) not in _visible:
            continue
        chars[str(c["name"])] = map_character(c, i)
    names = list(chars)
    staging = {n: sx(STAGING_X[i % len(STAGING_X)])
               for i, n in enumerate(names)}
    # Boarded characters stay at the bus door in later shots.
    for _n, _wx in (shot.get("staging_override") or {}).items():
        if _n in staging:
            staging[_n] = sx(_wx)
    boxes, sky_top, sky_bottom, rainy = build_scene(
        shot.get("location_keyword", "street"), shot.get("setting", ""),
        shot.get("mood", "warm"), shot.get("time_of_day", "day"))
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
    bg_scene = Scene25D(boxes=boxes, characters=[], camera=CAM,
                        sky_top=sky_top, sky_bottom=sky_bottom,
                        ground_color=(78, 72, 66) if rainy else (96, 92, 84),
                        ground_extent=30.0)
    bg_img = render_frame(bg_scene, W, H)
    if rainy:
        _lx, _ly, _, _ = CAM.project((4.0, 0.0, -1.5), W, H)
        _hx2, _hy2, _, _ = CAM.project((4.0, 3.3, -1.5), W, H)
        _lamp_glow(bg_img, (int(_lx), int(_ly)), (int(_hx2), int(_hy2)))
    if _has_bus:
        # F6: bus details on the static background, once per shot.
        _draw_bus_details(bg_img)
    shadow_tile = Image.new("RGBA", (320, 48), (0, 0, 0, 0))
    _td = ImageDraw.Draw(shadow_tile)
    _td.ellipse([20, 8, 300, 40], fill=(0, 0, 0, 110))
    shadow_tile = shadow_tile.filter(ImageFilter.GaussianBlur(6))
    speaker = shot.get("speaker")
    cues = list(shot.get("action_cues") or [])
    has_prop = any(c in cues for c in ("bend_pick", "give", "take"))
    actor = None
    if shot["kind"] == "action" and shot.get("actor") in chars:
        # The action lead's actor comes from the scene's action text
        # (who runs / boards / gives) — not from the speaker.
        actor = shot["actor"]
    elif speaker and speaker != "narrator" and speaker in chars:
        actor = speaker
    elif names:
        actor = names[0]
    other = next((n for n in names if n != actor), None)
    # A kneel lunges ~250 px behind the root: keep the actor far
    # enough from the frame edge that the whole body (jacket, back
    # leg) stays in frame. v11: Minh knelt at the left staging slot
    # and his jacket was cut at x=0. The prop follows (ax+220).
    if "bend_pick" in cues:
        staging[actor] = min(max(staging[actor], 380), W - 380)
    # ---- facing: speaker faces the listener, narrator faces right --
    for n, ch in chars.items():
        facing = 1
        if n == actor and other is not None:
            facing = 1 if staging[other] > staging[n] else -1
        elif n != actor and actor is not None:
            facing = 1 if staging[actor] > staging[n] else -1
        standing(ch, staging[n], GROUND_Y, facing=facing)
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
            fns[actor] = walk_to(chars[actor], ax, sx(BUS_DOOR_X),
                                 duration, GROUND_Y)
        elif "run" in cues:
            fns[actor] = run_to(chars[actor], ax, ax + 380 * direction,
                                duration, GROUND_Y)
        elif any(c in cues for c in ("walk", "walk_fast")):
            fns[actor] = walk_to(chars[actor], ax, ax + 320 * direction,
                                 duration, GROUND_Y)
        elif "bend_pick" in cues:
            prop_x, prop_y = ax + 220, GROUND_Y - 6
            prop.update(x=prop_x, y=prop_y)
            fns[actor] = kneel_pick(chars[actor], (prop_x, prop_y), duration, GROUND_Y)
        elif "give" in cues and other is not None:
            standing(chars[actor], ax, GROUND_Y,
                     facing=1 if staging[other] > ax else -1)
            standing(chars[other], staging[other], GROUND_Y,
                     facing=1 if ax > staging[other] else -1)
            give_fn = give_to(chars[actor], chars[other], prop, duration)
            fns[actor] = give_fn
        elif "wave" in cues:
            fns[actor] = wave(chars[actor], duration)
        else:
            fns[actor] = idle(chars[actor], duration, GROUND_Y)
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
            fns[n] = idle(ch, 99.0, GROUND_Y)
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
        # Per frame: copy the static background, paste the soft contact
        # shadows at the feet, draw the real rig characters on top.
        img = bg_img.copy()
        for n in names:
            fx = int(chars[n].pose["root_x"])
            img.paste(shadow_tile, (fx - 160, GROUND_Y - 24), shadow_tile)
        d = ImageDraw.Draw(img, "RGBA")
        joints_now: dict[str, dict] = {}
        for n in names:
            ch = chars[n]
            expr = expression_for(shot.get("text", "")) \
                if n == shot.get("speaker") else "neutral"
            joints_now[n] = draw_character_v4(
                d, ch, expression=expr, view=resolve_view(ch))
        if rainy:
            _draw_rain(d, fi)
        # Puddle beside the wallet (bend_pick scenes): the wallet lies
        # at its edge and the character kneels beside it, never in it.
        if "bend_pick" in cues and prop.get("x"):
            _draw_puddle(d, prop["x"], GROUND_Y)
        # prop: at the actor's hand once picked up / at the handover
        # midpoint during give, on the ground before that. In dialogue
        # shots the current holder (tracked in plan_shots) holds it —
        # Minh holds it through scenes 1-2, Lan after the give.
        if has_prop:
            d = ImageDraw.Draw(img, "RGBA")
            if give_fn is not None:
                wx, wy = prop["x"], prop["y"]
            elif "bend_pick" in cues and t >= 0.5 * duration:
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
                    wx, wy = prop["x"] or staging[actor] + 220, GROUND_Y - 6
            else:
                wx, wy = prop["x"] or staging[actor] + 220, GROUND_Y - 6
            _draw_prop(d, wx, wy)
        # prop position for the camera (object_insert frames the prop).
        _prop_xy = (wx, wy) if has_prop else None
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
            # scale stays constant across the shot. At 1.0x the
            # character is CHAR_H/1080 = 72.5% of the frame height
            # (under the 75% cap) and the head is 24.6% (under 26%).
            # The horizontal extent still follows the pose (hand /
            # foot spread), so a wide stance still frames correctly.
            J = joints_now[n]
            _hr = float(getattr(chars[n], "head_r", 133.0))
            return {
                "cx": J["head"][0],
                "head_y": GROUND_Y - CHAR_H,
                "foot_y": GROUND_Y,
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

        _st = shot["shot_type"]
        _full = {n: _full_box(n) for n in names}
        # F2: full-body shot types never zoom above 1.0x (belt and
        # braces with the standing-extent box above: even if the box
        # computation changes later, a full body can never be
        # inflated mid-shot). Head/prop framings keep their scales:
        # the zoom is the point of a close_up / reaction / insert.
        _max_scale = None
        if _st == "close_up":
            _lead = actor if actor in joints_now else names[0]
            subjects = [_head_box(_lead)]
            others = [_full[n] for n in names if n != _lead]
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
                     "camera": {"scale": SHOT_SCALE.get(shot["shot_type"], 1.6)},
                     "focus_target": actor}
        safe_shot, safe_focus, notes = CameraPlanner.safe_frame(
            shot_dict, focus, subjects, others, max_scale=_max_scale)
        if safe_shot["camera"]["scale"] == 1.0:
            # Establishing shot: the crop is the full frame — skip the
            # LANCZOS round-trip resize (same pixels, ~0.3 s saved).
            pass
        else:
            # Use the engine's safe_focus as-is. It already centres
            # the crop on the subjects with headroom AND keeps every
            # `other` fully in or fully out. The product used to
            # override it with its own re-centring (v5-v9) because the
            # subject box was wrong (head joint instead of head top)
            # and the visibility bug put Lan in scene 1 — both fixed
            # now, so the override is gone: it re-included heads that
            # safe_frame had deliberately shifted out of the crop.
            img = CameraPlanner.apply_camera(img, safe_shot, safe_focus)
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
                if fy > GROUND_Y + 3:
                    violations.append(
                        f"{n}: foot_{side} sinks {fy - GROUND_Y:.1f}px")
        if prev_joints is not None:
            for n in names:
                for joint in ("head", "hip", "foot_l", "foot_r",
                              "hand_l", "hand_r"):
                    a = prev_joints[n][joint]
                    b = joints_now[n][joint]
                    jump = math.hypot(b[0] - a[0], b[1] - a[1])
                    max_jump = max(max_jump, jump)
        prev_joints = {n: dict(J) for n, J in joints_now.items()}
    return {
        "index": shot["index"], "scene": shot["scene"],
        "kind": shot["kind"], "speaker": shot.get("speaker"),
        "shot_type": shot["shot_type"], "duration": duration,
        "n_frames": len(frames_written),
        "applied_scale": float(safe_shot["camera"]["scale"]),
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
