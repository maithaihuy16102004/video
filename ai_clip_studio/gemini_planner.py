"""Gemini story planner for the product pipeline (shared engine).

Real Gemini analysis of a pasted script -- characters, scenes, shots,
SFX and animation cues -- with the labelled deterministic fallback
when Gemini is unavailable. The planner emits SPEC section 15 trait
blocks (``package["trait_blocks"]``) on every route; the envelope is
built by one shared builder in trait_derivation.py so the gemini,
fallback and v1 shapes are identical.

Gemini access goes through gemini_client.GeminiClient (provider
seam): an explicitly passed key, the registered custom.gemini
connector helper subprocess, or the GEMINI_API_KEY env var. No key
material is ever read from a file, logged, or stored by this module.

Activation: resolve_plan() attempts a Gemini call for free-form
scripts only when a key is available (explicit ``api_key`` argument
or GEMINI_API_KEY) or when ``use_gemini_connector=True`` is passed
(the server enables this once its wiring lands). When the connector
flag is set, the registered helper subprocess is preferred over any
GEMINI_API_KEY value (GeminiClient's resolution order); the env var
is a credential path only on machines without the helper. Otherwise it
returns the labelled fallback without a network call, so planning
stays deterministic for tests and offline runs. The V1 route is
likewise opt-in via ``enrich_v1=True`` (see resolve_v1_plan); the
default V1 plan is the deterministic adapter, labelled "v1".

Model: ``gemini-3.5-flash-lite`` first, then
``gemini-flash-lite-latest``. On HTTP 429 the planner stops
immediately and falls back, labelled -- no retry.

Safety rule: the parsed script is GROUND TRUTH. Gemini only
ENRICHES it (character descriptions, template guesses, location
keywords, shot types, SFX suggestions, action directives). Spoken
lines, speakers and scene order always come from the real
segmentation; anything Gemini invents is dropped by validation
(trait_derivation.validate_trait_blocks) plus ground-truth
filtering in _merge. If the Gemini call fails or its JSON is
unusable, the deterministic planner's package is used and the plan
is labelled "fallback".
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .gemini_client import (
    GeminiClient,
    GeminiError,
    NoGeminiAvailable,
    RateLimitedError,
)
from .pipeline import segment_script
from .planner_fallback import deterministic_planner
from .studio_script_v1 import detect_format
from .studio_script_v1_adapter import resolve_v1_plan
from .trait_derivation import (
    build_character_trait_block,
    build_location_trait_block,
    build_music_event,
    build_sfx_event,
    build_trait_blocks,
    derive_location_traits,
    derive_render_traits,
    map_action_cue_to_primitive,
    snapshot_hash_for_text,
    validate_trait_blocks,
)
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
    any HTTP/API failure (caller decides the fallback).

    Kept byte-compatible for the affiliate callers that import it
    (affiliate/translation.py, affiliate/script_gen.py). New planner
    code uses gemini_client.GeminiClient instead.
    """
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
        '"render_traits": {"description": "mô tả ngoại hình/tính cách ngắn gọn '
        'bằng tiếng Việt", '
        '"voice_hint": "giọng nam" hoặc "giọng nữ" hoặc "giọng kể", '
        '"template": "male" hoặc "female" hoặc "child" hoặc "elderly", '
        '"body_variant": "slim" hoặc "standard" hoặc "sturdy", '
        '"costume": "none" hoặc "dress" hoặc "uniform", '
        '"hair_style": "short" hoặc "long" hoặc "tuft" hoặc "side_part" hoặc "none", '
        '"hat": "none" hoặc "bowler", '
        '"moustache_style": "none" hoặc "toothbrush" hoặc "handlebar" hoặc "full", '
        '"glasses": true/false, '
        '"jacket_color": "#RRGGBB"}}], '
        '"locations": [{"scene": 1, '
        '"render_traits": {"setting": "mô tả bối cảnh ngắn gọn", '
        '"location_keyword": "great_wall" hoặc "eiffel_tower" hoặc "rainy_street" '
        'hoặc "street" hoặc "generic", "mood": "warm" hoặc "cold", '
        '"time_of_day": "day" hoặc "night"}}], '
        '"shots": [{"scene": 1, "line_index": 1, '
        '"shot_type": "establishing" hoặc "medium" hoặc "close_up" hoặc '
        '"extreme_close_up" hoặc "over_the_shoulder" hoặc "reaction" hoặc '
        '"object_insert" hoặc "tracking" hoặc "shot_reverse_shot", '
        '"purpose": "mục đích của shot, ngắn gọn"}], '
        '"sfx": [{"event": "rain_start" hoặc "foot_contact" hoặc "door_contact" '
        'hoặc "door_rotation" hoặc "paper_movement" hoặc "object_impact" hoặc '
        '"character_reaction", "scene": 1, "note": "ghi chú ngắn"}], '
        '"music": [{"name": "tên nhạc nền gợi ý", "scene": 1, '
        '"intensity": "LOW" hoặc "MEDIUM" hoặc "HIGH", '
        '"note": "ghi chú ngắn, KHÔNG dùng tên sự kiện SFX"}], '
        '"actions": [{"type": "walk_to" hoặc "run_to" hoặc "turn_to" hoặc '
        '"look_at" hoặc "point_at" hoặc "wave" hoặc "reach_to" hoặc "give_to" '
        'hoặc "shrug" hoặc "cover_face" hoặc "nod" hoặc "sit_down" hoặc '
        '"stand_up" hoặc "idle" hoặc "bend_pick" hoặc "kneel_pick", '
        '"char": "tên nhân vật đúng như trong kịch bản", "scene": 1, '
        '"note": "hành động trong kịch bản, ngắn gọn"}], '
        '"hook": "câu hook của truyện", "twist": "cú twist của truyện"}.\n'
        "QUY TẮC: chỉ dùng nhân vật và câu thoại có trong kịch bản dưới đây, "
        "không bịa thêm nhân vật, cảnh hay lời thoại. line_index là số thứ tự "
        "câu trong danh sách. Nhân vật lịch sử ngoài đời thật thì giữ đặc trưng "
        "nhận diện của họ (ví dụ râu mép). head_ratio luôn là 0.34, không bao giờ "
        "trả về giá trị khác. KHÔNG đưa thời gian ước tính (không at_seconds). "
        "Nhạc nền KHÔNG được dùng tên sự kiện SFX. Hành động CHỈ dùng 16 tên "
        "nguyên thủy đã liệt kê; hành động không có nguyên thủy thì bỏ qua, "
        "không thay bằng chuyển động camera. Kịch bản:\n\n"
        f"{script_text}\n\nDanh sách câu thoại (ground truth):\n{lines}\n"
    )


def _parse_model_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    enrichment = json.loads(text)
    if not isinstance(enrichment, dict):
        raise ValueError("Gemini returned non-object JSON")
    return enrichment


def _merged_render_traits(target: dict, validated: dict) -> dict:
    """Deterministic derivation overlaid with validated model fields."""
    derived = derive_render_traits(
        target.get("name", ""),
        target.get("role", ""),
        target.get("appearance", "") or target.get("description", ""),
        target.get("costume_text", ""),
        target.get("traits", []),
        target.get("voice_style", ""),
        height_px=target.get("height_px", 540))
    derived.update({k: v for k, v in validated.items() if v is not None})
    if target.get("jacket_color") and "jacket_color" not in validated:
        derived["jacket_color"] = target["jacket_color"]
    return derived


def _merge(base: dict, enrichment: dict, parsed_lines: list[dict],
           *, model: str | None = None,
           usage: dict | None = None) -> dict:
    """Overlay Gemini enrichment onto the deterministic base package.

    Only values that reference real script content survive: the
    enrichment is validated against the section 15 enums first, then
    filtered against ground truth (real character names, real scene
    numbers, real line ordinals). Missing or invalid render fields
    are filled from the deterministic derivation, and everything
    dropped is recorded in trait_blocks["dropped"]. The package also
    gains its section 15 trait_blocks envelope (planner "gemini").
    """
    cleaned, dropped = validate_trait_blocks(enrichment)
    real_names = {c["name"] for c in base["characters"]}
    real_names |= {l["speaker"] for l in parsed_lines
                   if l["speaker"] != "narrator"}
    real_scenes = {s["number"] for s in base.get("scenes", [])}
    chars_by_name = {c["name"]: c for c in base["characters"]}
    for g in cleaned["characters"]:
        name = g["name"]
        if name not in real_names:
            dropped.append(
                f"character {name!r} is not in the script; dropped")
            continue
        target = chars_by_name.get(name)
        if target is None:
            target = {"name": name, "description": "", "voice_hint": "",
                      "jacket_color": "#3a4a5f", "height_px": 540}
            base["characters"].append(target)
            chars_by_name[name] = target
        merged = _merged_render_traits(target, g["render_traits"])
        target["render_traits"] = dict(merged)
        target["description"] = merged["description"]
        target["voice_hint"] = merged["voice_hint"]
        target["jacket_color"] = merged["jacket_color"]
        for key in ("template", "body_variant", "costume", "hair_style",
                    "hat", "moustache_style", "glasses"):
            target[key] = merged[key]
    loc_by_scene = {}
    for loc in cleaned["locations"]:
        scene_no = loc.get("scene")
        if scene_no is not None and scene_no not in real_scenes:
            dropped.append(
                f"location for scene {scene_no} is not a real scene; "
                "dropped")
            continue
        if scene_no is not None:
            loc_by_scene[scene_no] = loc["render_traits"]
    for scene in base.get("scenes", []):
        extra = loc_by_scene.get(scene["number"])
        if extra:
            existing = scene.get("location") or {}
            merged_loc = derive_location_traits(
                inline_text=existing.get("setting")
                or scene.get("setting", ""))
            merged_loc.update(existing)
            merged_loc.update(extra)
            scene["location"] = {
                "setting": merged_loc.get("setting", ""),
                "location_keyword": merged_loc.get(
                    "location_keyword", "street"),
                "mood": merged_loc.get("mood", "warm"),
                "time_of_day": merged_loc.get("time_of_day", "day"),
            }
    n_lines = len(parsed_lines)
    shots = []
    for s in cleaned["shots"]:
        if not 1 <= s["line_index"] <= n_lines:
            dropped.append(
                f"shot for line_index {s['line_index']} is not a real "
                "line; dropped")
            continue
        if real_scenes and s["scene"] not in real_scenes:
            dropped.append(
                f"shot for scene {s['scene']} is not a real scene; "
                "dropped")
            continue
        shots.append(s)
    if shots:
        base["gemini_shots"] = shots
    sfx = []
    for e in cleaned["sfx"]:
        if real_scenes and e["scene"] not in real_scenes:
            dropped.append(
                f"sfx event for scene {e['scene']} is not a real "
                "scene; dropped")
            continue
        sfx.append(e)
    if sfx:
        base["gemini_sfx"] = sfx
    music = []
    for m in cleaned["music"]:
        if real_scenes and m["scene"] not in real_scenes:
            dropped.append(
                f"music event for scene {m['scene']} is not a real "
                "scene; dropped")
            continue
        music.append(m)
    if music:
        base["gemini_music"] = music
    actions = []
    for a in cleaned["actions"]:
        char = a.get("char")
        if char is not None and char not in real_names:
            dropped.append(
                f"action for character {char!r} is not in the script; "
                "dropped")
            continue
        actions.append(a)
    if cleaned["hook"] is not None:
        base["hook"] = cleaned["hook"]
    if cleaned["twist"] is not None:
        base["twist"] = cleaned["twist"]
    base["trait_blocks"] = _gemini_trait_blocks(
        base, parsed_lines, actions, sfx, music, dropped,
        model=model, usage=usage)
    return base


def _gemini_trait_blocks(base: dict, parsed_lines: list[dict],
                         actions: list[dict], sfx: list[dict],
                         music: list[dict], dropped: list[str],
                         *, model, usage) -> dict:
    prior = base.get("trait_blocks") or {}
    snapshot = prior.get("snapshot_hash") or snapshot_hash_for_text(
        "\n".join(l.get("text", "") for l in parsed_lines))
    blocks = []
    for char in base["characters"]:
        traits = char.get("render_traits") or _merged_render_traits(char, {})
        blocks.append(build_character_trait_block(
            identity_id=char.get("identity_id") or char["name"],
            name=char["name"], role=char.get("role", ""),
            appearance=char.get("appearance", ""),
            traits=char.get("traits", []),
            costume=char.get("costume_text", ""),
            costume_changes=char.get("costume_changes", []),
            voice=char.get("voice", ""),
            voice_style=char.get("voice_style", ""),
            voice_id=char.get("voice_id", ""),
            head_ratio=char.get("head_ratio", 0.34),
            render_traits=traits,
            actions=[a for a in actions
                     if a.get("char") == char["name"]],
            dropped_notes=dropped))
    location_blocks = []
    for scene in base.get("scenes", []):
        existing = scene.get("location") or {}
        traits = derive_location_traits(
            inline_text=existing.get("setting")
            or scene.get("setting", ""))
        traits.update({k: existing[k] for k in (
            "setting", "location_keyword", "mood", "time_of_day")
            if k in existing})
        location_blocks.append(build_location_trait_block(
            location_id=f"scene_{scene['number']}",
            scene_numbers=[scene["number"]],
            name=scene.get("setting", ""),
            render_traits=traits))
    sfx_events = [build_sfx_event(
        name=e.get("note") or e["event"], scene_number=e["scene"],
        source_key="SFX", event=e["event"],
        note=e.get("note", "")) for e in sfx]
    music_events = [build_music_event(
        name=m["name"], intensity=m.get("intensity", "MEDIUM"),
        scene_number=m["scene"], source_key="BGM",
        note=m.get("note", "")) for m in music]
    return build_trait_blocks(
        snapshot_hash=snapshot, planner=PLANNER_GEMINI, model=model,
        usage=usage, reason=None, characters=blocks,
        locations=location_blocks, sfx=sfx_events, music=music_events,
        unmapped_cues=[], actions=actions, unmapped=[],
        dropped=dropped)


def _ensure_hook_twist(package: dict, parsed_lines: list[dict]) -> dict:
    """Hook/twist are required by preflight. Gemini supplies them when
    it answers; otherwise derive them generically from the script
    itself: the opening line is the hook, the final line is the
    twist/payoff. Never invented -- both are the script's own words."""
    if parsed_lines:
        if not package.get("hook"):
            package["hook"] = parsed_lines[0]["text"][:200]
        if not package.get("twist"):
            package["twist"] = parsed_lines[-1]["text"][:200]
    return package


def resolve_plan(script_text: str, *, api_key: str | None = None,
                 use_gemini_connector: bool = False,
                 enrich_v1: bool = False,
                 gemini_client: GeminiClient | None = None
                 ) -> tuple[dict, str, str]:
    """Plan a script. Returns (package, planner_label, planner_detail).

    planner_label is "gemini" only when a real Gemini call produced the
    enrichment; "v1" for STUDIO SCRIPT V1 scripts without enrichment
    (deterministic V1 parser + adapter); otherwise "fallback" with the
    reason. The package always has the deterministic planner's shape,
    so the pipeline never breaks when Gemini is unavailable.

    Gemini is attempted for free-form scripts when ``api_key`` is
    given, GEMINI_API_KEY is set, ``gemini_client`` is injected, or
    ``use_gemini_connector`` is True (connector helper path). When
    ``use_gemini_connector`` is True the connector helper is
    preferred over GEMINI_API_KEY: the client is constructed without
    an explicit key, so GeminiClient's helper-first resolution
    applies and the env var is used only when no helper exists.
    ``enrich_v1`` enables Gemini enrichment for V1 scripts (cached
    per snapshot hash; see resolve_v1_plan).
    """
    # STUDIO SCRIPT V1 route (Phase B): one pipeline, two parsers.
    if detect_format(script_text) == "studio_v1":
        return resolve_v1_plan(
            script_text, enrich_with_gemini=enrich_v1,
            gemini_client=gemini_client)
    if is_structured_vi_script(script_text):
        parsed = parse_vi_script(script_text)
        parsed_lines = [{"speaker": l.speaker, "kind": l.kind, "text": l.text}
                        for l in parsed.lines]
    else:
        segmented = segment_script(script_text)
        parsed_lines = [{"speaker": l.speaker, "kind": l.kind, "text": l.text}
                        for l in segmented.lines]
    base = deterministic_planner(script_text) if is_structured_vi_script(script_text) else _base_from_segmented(script_text)
    client = gemini_client
    if client is None:
        if api_key:
            client = GeminiClient(api_key=api_key)
        elif use_gemini_connector:
            # Connector path: construct without a key so the client
            # prefers the registered helper subprocess over any
            # GEMINI_API_KEY value; the env var is consulted by the
            # client only when no helper exists (other machines).
            client = GeminiClient()
        elif os.environ.get("GEMINI_API_KEY", ""):
            client = GeminiClient(
                api_key=os.environ["GEMINI_API_KEY"])
    if client is None:
        return _ensure_hook_twist(base, parsed_lines), PLANNER_FALLBACK, (
            "No Gemini credential configured (no explicit key, "
            "GEMINI_API_KEY not set, connector not enabled) — "
            "deterministic local planner used "
            "(labelled fallback, not Gemini output)")
    last_error = ""
    prompt = _prompt(script_text, parsed_lines)
    for model in MODELS:
        try:
            raw, usage, used = client.generate_json(
                prompt, model=model, max_tokens=4096)
            enrichment = _parse_model_json(raw)
            package = _ensure_hook_twist(
                _merge(base, enrichment, parsed_lines, model=used,
                       usage=usage), parsed_lines)
            tokens = (usage or {}).get("total_tokens") or 0
            token_note = f", {tokens} tokens" if tokens else ""
            return package, PLANNER_GEMINI, (
                f"Gemini {used} analysed the script "
                f"({len(parsed_lines)} lines, "
                f"{len(package['characters'])} characters{token_note})")
        except RateLimitedError as exc:
            # 429: stop immediately, no retry, no next model.
            last_error = str(exc)[:200]
            break
        except NoGeminiAvailable as exc:
            last_error = str(exc)[:200]
            break
        except (GeminiError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)[:200]
            continue
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
    package = {
        "characters": characters,
        "locations": [s["setting"] for s in scenes],
        "scenes": scenes,
        "shots": shots,
        "audio_events": [{"event": e["event"], "scene": 1,
                          "at_seconds": e.get("at_seconds", 0.0)}
                         for e in segmented.visual_events],
    }
    package["trait_blocks"] = _segmented_trait_blocks(
        script_text, characters, scenes)
    return package


def _segmented_trait_blocks(script_text: str, characters: list[dict],
                            scenes: list[dict]) -> dict:
    """Fallback trait blocks for the free-form segmented package."""
    directives: list[dict] = []
    unmapped: list[dict] = []
    for scene in scenes:
        for cue in scene["action_cues"]:
            primitive = map_action_cue_to_primitive(cue)
            if primitive is None:
                unmapped.append({
                    "kind": "action_cue", "action_text": cue,
                    "scene_number": scene["number"], "shot_id": None,
                    "source_line": None,
                    "reason": "no PRIMITIVES mapping for this action cue",
                })
            else:
                directives.append({
                    "type": primitive, "char": None, "start": None,
                    "duration": 1.5, "scene_number": scene["number"],
                    "shot_id": None, "source_line": None,
                    "action_text": cue,
                })
    blocks = []
    for char in characters:
        traits = derive_render_traits(
            char["name"], "", "", "", [], "",
            height_px=char["height_px"])
        traits["jacket_color"] = char["jacket_color"]
        blocks.append(build_character_trait_block(
            identity_id=char["name"], name=char["name"],
            render_traits=traits, actions=[]))
    location_blocks = [
        build_location_trait_block(
            location_id=f"scene_{scene['number']}",
            scene_numbers=[scene["number"]],
            name=scene.get("setting", ""),
            render_traits=derive_location_traits(
                inline_text=scene.get("setting", "")))
        for scene in scenes
    ]
    return build_trait_blocks(
        snapshot_hash=snapshot_hash_for_text(script_text),
        planner="fallback", model=None, usage=None,
        reason="deterministic local planner (no Gemini call ran)",
        characters=blocks, locations=location_blocks,
        sfx=[], music=[], unmapped_cues=[],
        actions=directives, unmapped=unmapped, dropped=[])
