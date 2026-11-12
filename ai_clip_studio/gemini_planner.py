"""Gemini story planner for the product pipeline (shared engine).

Real Gemini analysis of a pasted script — characters, scenes, shots,
SFX and animation cues — via the public Generative Language API
(stdlib urllib, no new dependency). The API key comes ONLY from the
``GEMINI_API_KEY`` environment variable; it is never read from a
file, never logged, and never stored.

Model: ``gemini-3.5-flash-lite`` (validated 2026-11-11: a minimal
generateContent call returned HTTP 200). ``gemini-2.5-flash`` and
``gemini-2.0-flash`` return 404 "no longer available to new users";
``gemini-3.8-flash`` returned 503 (high demand) at validation time.
Fallback chain: gemini-3.5-flash-lite -> gemini-flash-lite-latest ->
deterministic local planner (clearly labelled "fallback", never
presented as Gemini output).

Safety rule: the parsed script is GROUND TRUTH. Gemini only
ENRICHES it (character descriptions, template guesses, location
keywords, shot types, SFX suggestions). Spoken lines, speakers and
scene order always come from the real segmentation
(``vi_script_parser`` / ``segment_script``); any line, character or
scene Gemini invents is dropped by validation. If the Gemini call
fails or its JSON is unusable, the deterministic planner's package is
used and the plan is labelled "fallback".
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .pipeline import segment_script
from .planner_fallback import deterministic_planner
from .studio_script_v1 import detect_format
from .studio_script_v1_adapter import resolve_v1_plan
from .vi_script_parser import is_structured_vi_script, parse_vi_script

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MODELS = ("gemini-3.5-flash-lite", "gemini-flash-lite-latest",
          "gemini-3.1-flash-lite")
REQUEST_TIMEOUT = 60

# Model name shown in reports/UI. Only set when a real Gemini call
# produced (part of) the plan.
PLANNER_GEMINI = "gemini"
PLANNER_FALLBACK = "fallback"


def _gemini_generate(prompt: str, model: str, api_key: str) -> str:
    """One generateContent call. Returns the model's text. Raises on
    any HTTP/API failure (caller decides the fallback)."""
    url = f"{GEMINI_API_URL}/{model}:generateContent"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "x-goog-api-key": api_key},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(
            f"Gemini API HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Gemini API unreachable: {exc}") from exc
    try:
        return payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"Gemini API returned no text: {str(payload)[:300]}") from exc


def _prompt(script_text: str, parsed_lines: list[dict]) -> str:
    lines = "\n".join(
        f"{i + 1}. [{l['speaker']}|{l['kind']}] {l['text']}"
        for i, l in enumerate(parsed_lines))
    return (
        "Bạn là đạo diễn phân tích kịch bản cho công cụ làm video hoạt hình "
        "phong cách RicksClips (người que đầu to, nét đậm, 16:9). "
        "Phân tích kịch bản dưới đây và CHỈ trả về JSON hợp lệ, không giải thích, "
        "không markdown, theo đúng schema này:\n"
        '{"characters": [{"name": "tên đúng như trong kịch bản", '
        '"description": "mô tả ngoại hình/tính cách ngắn gọn bằng tiếng Việt", '
        '"voice_hint": "giọng nam" hoặc "giọng nữ" hoặc "giọng kể", '
        '"template": "male" hoặc "female" hoặc "child" hoặc "elderly", '
        '"body_variant": "slim" hoặc "standard" hoặc "sturdy", '
        '"costume": "none" hoặc "dress" hoặc "uniform", '
        '"hair_style": "short" hoặc "long" hoặc "tuft" hoặc "side_part" hoặc "none", '
        '"hat": "none" hoặc "bowler", '
        '"moustache_style": "none" hoặc "toothbrush" hoặc "handlebar" hoặc "full", '
        '"glasses": true/false, '
        '"jacket_color": "#RRGGBB"}], '
        '"locations": [{"scene": 1, "setting": "mô tả bối cảnh ngắn gọn", '
        '"location_keyword": "great_wall" hoặc "eiffel_tower" hoặc "rainy_street" '
        'hoặc "street" hoặc "generic", "mood": "warm" hoặc "cold", '
        '"time_of_day": "day" hoặc "night"}], '
        '"shots": [{"scene": 1, "line_index": 1, '
        '"shot_type": "establishing" hoặc "medium" hoặc "close_up" hoặc '
        '"reaction" hoặc "object_insert" hoặc "tracking", '
        '"purpose": "mục đích của shot, ngắn gọn"}], '
        '"sfx": [{"event": "rain_start" hoặc "foot_contact" hoặc "door_contact" '
        'hoặc "door_rotation" hoặc "paper_movement" hoặc "object_impact" hoặc '
        '"character_reaction", "scene": 1, "note": "ghi chú ngắn"}], '
        '"hook": "câu hook của truyện", "twist": "cú twist của truyện"}.\n'
        "QUY TẮC: chỉ dùng nhân vật và câu thoại có trong kịch bản dưới đây, "
        "không bịa thêm nhân vật, cảnh hay lời thoại. line_index là số thứ tự "
        "câu trong danh sách. Nhân vật lịch sử ngoài đời thật thì giữ đặc trưng "
        "nhận diện của họ (ví dụ râu mép). Kịch bản:\n\n"
        f"{script_text}\n\nDanh sách câu thoại (ground truth):\n{lines}\n"
    )


def _merge(base: dict, enrichment: dict, parsed_lines: list[dict]) -> dict:
    """Overlay Gemini enrichment onto the deterministic base package.
    Only values that reference real script content survive."""
    real_names = {c["name"] for c in base["characters"]}
    real_names |= {l["speaker"] for l in parsed_lines
                   if l["speaker"] != "narrator"}
    chars_by_name = {c["name"]: c for c in base["characters"]}
    for g in enrichment.get("characters", []):
        name = g.get("name")
        if not isinstance(name, str) or name not in real_names:
            continue
        target = chars_by_name.get(name)
        if target is None:
            target = {"name": name, "description": "", "voice_hint": "",
                      "jacket_color": "#3a4a5f", "height_px": 540}
            base["characters"].append(target)
            chars_by_name[name] = target
        for key in ("description", "voice_hint", "jacket_color"):
            if isinstance(g.get(key), str) and g[key].strip():
                target[key] = g[key].strip()
        for key in ("template", "body_variant", "costume", "hair_style",
                    "hat", "moustache_style"):
            if isinstance(g.get(key), str) and g[key].strip():
                target[key] = g[key].strip()
        if isinstance(g.get("glasses"), bool):
            target["glasses"] = g["glasses"]
    loc_by_scene = {}
    for loc in enrichment.get("locations", []):
        try:
            scene_no = int(loc.get("scene", 0))
        except (TypeError, ValueError):
            continue
        if loc.get("location_keyword") in (
                "great_wall", "eiffel_tower", "rainy_street", "street",
                "generic"):
            loc_by_scene[scene_no] = {
                "setting": str(loc.get("setting", ""))[:120],
                "location_keyword": loc["location_keyword"],
                "mood": loc.get("mood") if loc.get("mood") in ("warm", "cold") else "warm",
                "time_of_day": loc.get("time_of_day")
                if loc.get("time_of_day") in ("day", "night") else "day",
            }
    for scene in base["scenes"]:
        extra = loc_by_scene.get(scene["number"])
        if extra:
            scene["location"] = extra
    n_lines = len(parsed_lines)
    shots = []
    for s in enrichment.get("shots", []):
        try:
            li = int(s.get("line_index", 0))
            scene_no = int(s.get("scene", 0))
        except (TypeError, ValueError):
            continue
        if 1 <= li <= n_lines and s.get("shot_type") in (
                "establishing", "medium", "close_up", "reaction",
                "object_insert", "tracking"):
            shots.append({"scene": scene_no, "line_index": li,
                          "shot_type": s["shot_type"],
                          "purpose": str(s.get("purpose", ""))[:120]})
    if shots:
        base["gemini_shots"] = shots
    sfx = []
    for e in enrichment.get("sfx", []):
        if e.get("event") in ("rain_start", "foot_contact", "door_contact",
                              "door_rotation", "paper_movement",
                              "object_impact", "character_reaction"):
            try:
                sfx.append({"event": e["event"],
                            "scene": int(e.get("scene", 0)),
                            "note": str(e.get("note", ""))[:120]})
            except (TypeError, ValueError):
                continue
    if sfx:
        base["gemini_sfx"] = sfx
    if isinstance(enrichment.get("hook"), str):
        base["hook"] = enrichment["hook"][:200]
    if isinstance(enrichment.get("twist"), str):
        base["twist"] = enrichment["twist"][:200]
    return base


def _ensure_hook_twist(package: dict, parsed_lines: list[dict]) -> dict:
    """Hook/twist are required by preflight. Gemini supplies them when
    it answers; otherwise derive them generically from the script
    itself: the opening line is the hook, the final line is the
    twist/payoff. Never invented — both are the script's own words."""
    if parsed_lines:
        if not package.get("hook"):
            package["hook"] = parsed_lines[0]["text"][:200]
        if not package.get("twist"):
            package["twist"] = parsed_lines[-1]["text"][:200]
    return package


def resolve_plan(script_text: str, *, api_key: str | None = None) -> tuple[dict, str, str]:
    """Plan a script. Returns (package, planner_label, planner_detail).

    planner_label is "gemini" only when a real Gemini call produced the
    enrichment; "v1" for STUDIO SCRIPT V1 scripts (deterministic V1
    parser + adapter, no Gemini enrichment); otherwise "fallback"
    with the reason. The package always has the deterministic
    planner's shape, so the pipeline never breaks when Gemini is
    unavailable.
    """
    # STUDIO SCRIPT V1 route (Phase B): one pipeline, two parsers.
    # V1 scripts are parsed by the V1 parser and mapped by the
    # adapter; the free-form path below is untouched. The adapter is
    # deterministic (the server plans at least twice per production)
    # and raises V1AdapterError on invalid documents.
    if detect_format(script_text) == "studio_v1":
        return resolve_v1_plan(script_text)
    if is_structured_vi_script(script_text):
        parsed = parse_vi_script(script_text)
        parsed_lines = [{"speaker": l.speaker, "kind": l.kind, "text": l.text}
                        for l in parsed.lines]
    else:
        segmented = segment_script(script_text)
        parsed_lines = [{"speaker": l.speaker, "kind": l.kind, "text": l.text}
                        for l in segmented.lines]
    base = deterministic_planner(script_text) if is_structured_vi_script(script_text) else _base_from_segmented(script_text)
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return _ensure_hook_twist(base, parsed_lines), PLANNER_FALLBACK, (
            "GEMINI_API_KEY not set — deterministic local planner used "
            "(labelled fallback, not Gemini output)")
    last_error = ""
    for model in MODELS:
        for attempt in (1, 2):
            try:
                raw = _gemini_generate(_prompt(script_text, parsed_lines),
                                       model, key)
                text = raw.strip()
                if text.startswith("```"):
                    text = text.split("```", 2)[1]
                    if text.lstrip().lower().startswith("json"):
                        text = text.lstrip()[4:]
                enrichment = json.loads(text)
                if not isinstance(enrichment, dict):
                    raise ValueError("Gemini returned non-object JSON")
                package = _ensure_hook_twist(
                    _merge(base, enrichment, parsed_lines), parsed_lines)
                return package, PLANNER_GEMINI, (
                    f"Gemini {model} analysed the script "
                    f"({len(parsed_lines)} lines, "
                    f"{len(package['characters'])} characters)")
            except Exception as exc:  # noqa: BLE001 - retry / next model / fallback
                last_error = str(exc)[:200]
                if "503" in last_error and attempt == 1:
                    time.sleep(5)  # transient overload: one retry
                    continue
                break
    return _ensure_hook_twist(base, parsed_lines), PLANNER_FALLBACK, (
        f"Gemini unavailable ({last_error}) — deterministic local planner "
        "used (labelled fallback, not Gemini output)")


def _base_from_segmented(script_text: str) -> dict:
    """Deterministic package for free-form (non-structured) scripts:
    one scene per 3 lines, characters from speakers, shots per line."""
    segmented = segment_script(script_text)
    characters = []
    for i, name in enumerate(segmented.characters):
        characters.append({
            "name": name, "description": "", "voice_hint": "",
            "jacket_color": ["#2E5FA3", "#47BD75", "#D9A441", "#7A4A2B"][i % 4],
            "height_px": 560 if i % 2 == 0 else 540,
        })
    scenes = []
    shots = []
    per_scene = 3
    lines = segmented.lines
    for start in range(0, max(1, len(lines)), per_scene):
        chunk = lines[start:start + per_scene]
        number = start // per_scene + 1
        scenes.append({
            "number": number, "title": f"Cảnh {number}",
            "setting": "", "action_text": "",
            "audio_text": "", "animation_reqs": [],
            "action_cues": sorted({e["event"] for e in segmented.visual_events}),
            "action_lead_sec": 1.0,
            "lines": [{"speaker": l.speaker, "kind": l.kind, "text": l.text}
                      for l in chunk],
        })
        for j, line in enumerate(chunk):
            shots.append({
                "shot_id": f"S{number}L{j + 1}", "scene": number,
                "kind": line.kind, "speaker": line.speaker,
                "text": line.text, "action_cues": [],
                "estimated_sec": 4.0,
            })
    return {
        "characters": characters,
        "locations": [s["setting"] for s in scenes],
        "scenes": scenes,
        "shots": shots,
        "audio_events": [{"event": e["event"], "scene": 1,
                          "at_seconds": e.get("at_seconds", 0.0)}
                         for e in segmented.visual_events],
    }
