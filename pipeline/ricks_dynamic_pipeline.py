"""Compile strict, character-driven short-form timelines for the local studio."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

FPS = 30
EMOTION_MAP = {
    "calm": "neutral", "focused": "serious", "serious": "serious", "grave": "serious",
    "urgent": "tense", "tense": "tense", "panicked": "tense", "excited": "excited",
    "amazed": "surprised", "surprised": "surprised", "curious": "curious",
    "intrigued": "curious", "hopeful": "excited", "inspired": "excited",
    "emotional": "excited", "confident": "serious", "firm": "serious", "whisper": "serious"
}

@dataclass(frozen=True)
class SfxCue:
    frame: int
    source: str
    volume: float = 1.0

def _tags(value: str) -> list[str]:
    return re.findall(r"\[([a-z_]+)\]", value.lower())

def primary_emotion(value: str) -> str:
    for tag in _tags(value):
        if tag in EMOTION_MAP:
            return EMOTION_MAP[tag]
    return "neutral"

def parse_sfx_trigger(value: str, scene_start: float, fps: int = FPS) -> SfxCue:
    match = re.fullmatch(r"f\+(\d+):(.+)", value.strip())
    if not match:
        raise ValueError(f"SFX trigger không hợp lệ: {value}")
    return SfxCue(round(scene_start * fps) + int(match.group(1)), match.group(2))

def validate_timeline(timeline: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not timeline:
        return ["Timeline rỗng."]
    previous_end = 0.0
    for index, scene in enumerate(timeline, 1):
        expected = f"scene_{index:03d}"
        scene_id = str(scene.get("scene_id", ""))
        if scene_id != expected:
            errors.append(f"Scene {index}: scene_id phải là {expected}.")
        ts = scene.get("timestamp") or {}
        start, end = float(ts.get("start", -1)), float(ts.get("end", -1))
        if abs(start - previous_end) > 0.001:
            errors.append(f"{scene_id}: timeline không liên tục.")
        duration = end - start
        if duration <= 0 or duration > 3.0:
            errors.append(f"{scene_id}: duration phải >0 và <=3.0 giây.")
        previous_end = end
        motion = scene.get("charmotion") or {}
        if motion.get("pipeline") not in {"LivePortrait", "SadTalker"}:
            errors.append(f"{scene_id}: pipeline nhân vật không hợp lệ.")
        if not 0 <= float(motion.get("motion_intensity", -1)) <= 1:
            errors.append(f"{scene_id}: motion_intensity ngoài 0..1.")
        if not _tags(str((scene.get("narrative") or {}).get("emotion_tagging", ""))):
            errors.append(f"{scene_id}: thiếu emotion tags.")
        audio = scene.get("audio_dynamics") or {}
        if not 0 <= float(audio.get("ducking_level", -1)) <= 1:
            errors.append(f"{scene_id}: ducking_level ngoài 0..1.")
        for trigger in audio.get("sfx_triggers", []):
            try:
                cue = parse_sfx_trigger(trigger, start)
                if cue.frame >= round(end * FPS):
                    errors.append(f"{scene_id}: SFX {trigger} nằm ngoài scene.")
            except ValueError as exc:
                errors.append(str(exc))
    return errors

def compile_timeline(timeline: list[dict[str, Any]]) -> dict[str, Any]:
    errors = validate_timeline(timeline)
    if errors:
        raise ValueError("\n".join(errors))
    scenes, all_sfx = [], []
    for scene in timeline:
        start, end = scene["timestamp"]["start"], scene["timestamp"]["end"]
        narrative, motion = scene["narrative"], scene["charmotion"]
        visual, audio = scene["visual_composition"], scene["audio_dynamics"]
        cues = [parse_sfx_trigger(item, start) for item in audio["sfx_triggers"]]
        all_sfx.extend(cues)
        scenes.append({
            "id": scene["scene_id"], "start_seconds": start, "duration": round(end-start, 3),
            "spoken": narrative["text"], "voice_profile": narrative["voice_profile"],
            "emotion": primary_emotion(narrative["emotion_tagging"]), "emotion_tags": _tags(narrative["emotion_tagging"]),
            "character": {"avatar_id": motion["avatar_id"], "pipeline": motion["pipeline"], "motion_intensity": motion["motion_intensity"], "driving_video_ref": motion["driving_video_ref"], "fallback_policy": "reject_static_slideshow"},
            "visual": {"b_roll_path": visual["b_roll_source"], "screen_effect": visual["screen_effect"], "subtitle_style": visual["subtitle_style"], "max_visual_beat_seconds": min(3.0, round(end-start, 3))},
            "audio": {"bgm_track": audio["bgm_track"], "ducking_level_during_speech": audio["ducking_level"], "ducking_level_transition": 0.8, "sfx": [asdict(cue) for cue in cues]}
        })
    return {"preset": "ricks_dynamic", "fps": FPS, "width": 1080, "height": 1920, "duration": timeline[-1]["timestamp"]["end"], "scene_count": len(scenes), "render_contract": {"max_scene_duration": 3.0, "character_animation_required": True, "static_portrait_fallback_allowed": False, "word_synced_captions": True, "frame_accurate_sfx": True, "dynamic_bgm_ducking": True}, "scenes": scenes, "sfx_timeline": [asdict(cue) for cue in sorted(all_sfx, key=lambda cue: cue.frame)]}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("timeline")
    parser.add_argument("--out", required=True)
    parser.add_argument("--preflight", action="store_true", help="Kiểm tra model và asset trước khi render")
    args = parser.parse_args()
    compiled = compile_timeline(json.loads(Path(args.timeline).read_text(encoding="utf-8")))
    if args.preflight:
        from character_motion_dispatcher import preflight_scene
        errors = [error for scene in compiled["scenes"] for error in preflight_scene(scene)]
        if errors:
            raise SystemExit("Preflight thất bại:\n" + "\n".join(errors))
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(compiled, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)

if __name__ == "__main__":
    main()
