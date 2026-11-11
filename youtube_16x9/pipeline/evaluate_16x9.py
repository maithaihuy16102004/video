"""Self-evaluation for 16:9 YouTube videos, on a 0-10 scale.

See youtube_16x9/config/acceptance_rubric.json for the full rubric.
Pass = overall >= 8.0 AND every category >= 7.0 AND no hard fails.

This module scores everything that can be measured from the file:
resolution, fps, duration, black bars, audio presence, caption
overflow, shot pacing, hook/twist presence, and TTS fit
(planned timeline vs. real audio duration).

Character, scene, motion and story still need a human (or the
reviewing agent) to watch the video and look at the contact sheet.
Those categories are returned as "needs_visual_review" with the
contact-sheet path, so a score is never invented for them.

Usage:
    python3 youtube_16x9/pipeline/evaluate_16x9.py \
        --package youtube_16x9/examples/eiffel_tower_twice_package.json \
        --video out/master.mp4 [--audio out/master.wav] \
        --out out/evaluation.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_DIR = HERE.parent / "config"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def ffprobe(path: Path) -> dict:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return json.loads(out.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}


def cropdetect(path: Path) -> str:
    """Run cropdetect for a few seconds; returns the detected crop string."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-i", str(path), "-vf", "cropdetect=limit=24:round=2:reset=0",
             "-frames:v", "48", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
        lines = [l for l in out.stderr.splitlines() if "crop=" in l]
        return lines[-1].split("crop=")[-1].strip() if lines else ""
    except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return ""


def wav_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except (wave.Error, OSError, FileNotFoundError):
        return None


def evaluate(package: dict, video_path: Path, audio_path: Path | None = None) -> dict:
    rubric = load_json(CONFIG_DIR / "acceptance_rubric.json")
    errors: list[str] = []      # hard fails
    warnings: list[str] = []
    technical: dict[str, float | str] = {}

    # --- camera / framing (technical part) ---
    probe = ffprobe(video_path)
    if not probe:
        errors.append("probe_failed: ffprobe could not read the video")
        return _report(rubric, technical, errors, warnings, package)
    vstream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
    astream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), {})
    width, height = vstream.get("width"), vstream.get("height")
    technical["resolution"] = f"{width}x{height}"
    if (width, height) != (1920, 1080):
        errors.append(f"wrong_resolution: rendered {width}x{height} (must be 1920x1080)")
    if package.get("aspect_ratio") != "16:9":
        errors.append(f"wrong_aspect_ratio: {package.get('aspect_ratio')} (must be 16:9)")
    fps_raw = vstream.get("r_frame_rate", "0/1")
    try:
        num, den = (int(x) for x in fps_raw.split("/"))
        fps = round(num / den, 2) if den else 0
    except ValueError:
        fps = 0
    technical["fps"] = fps
    if fps != 24:
        warnings.append(f"unexpected_fps: {fps} (expected 24)")
    duration = float(probe.get("format", {}).get("duration", 0) or 0)
    technical["duration_sec"] = round(duration, 2)

    crop = cropdetect(video_path)
    technical["cropdetect"] = crop
    if crop and crop not in ("1920:1080:0:0", "1920:1080:0:0"):
        # cropdetect reports the non-black area; anything smaller than
        # 1920x1080 means black bars / pillarboxing.
        w_h = crop.split(":")[:2]
        if w_h != ["1920", "1080"]:
            errors.append(f"black_bars_pillarbox_letterbox: cropdetect says {crop}")

    # --- audio presence ---
    if not astream:
        errors.append("no_audio: rendered video has no audio stream")
    else:
        technical["audio_codec"] = astream.get("codec_name")

    # --- story: hook / twist / payoff ---
    purposes = [s.get("purpose") for s in package.get("shots", [])]
    if "HOOK" not in purposes:
        errors.append("missing_hook: no HOOK shot in the package")
    if "TWIST" not in purposes:
        errors.append("missing_twist: no TWIST shot in the package")
    if "PAYOFF" not in purposes:
        errors.append("missing_payoff: no PAYOFF shot in the package")

    # --- shot pacing + captions ---
    for shot in package.get("shots", []):
        dur = float(shot.get("duration_sec", 0))
        if dur > 6.5:
            warnings.append(f"shot_too_long: {shot.get('shot_id')} is {dur}s (max 6.5s)")
        caption = shot.get("script_line", "")
        if len(caption) > 84:
            errors.append(
                f"caption_outside_safe_title: {shot.get('shot_id')} has "
                f"{len(caption)} chars (max 84 for 2 lines)"
            )

    # --- voice / narration timing: the draft-3 bug ---
    planned = float(package.get("total_duration_sec", 0) or 0)
    technical["planned_duration_sec"] = planned
    if audio_path and audio_path.exists():
        real = wav_duration(audio_path)
        technical["real_audio_duration_sec"] = real
        if real is not None:
            if real > planned + 0.5:
                errors.append(
                    f"final_voice_line_cut_off: real audio is {real:.2f}s but "
                    f"the timeline is only {planned:.2f}s — the last line "
                    "will be cut, as in the V51 drafts"
                )
            elif real < planned - 2.0:
                warnings.append(
                    f"audio_shorter_than_timeline: real audio {real:.2f}s vs "
                    f"planned {planned:.2f}s — check for a silent tail"
                )
    if duration and planned and abs(duration - planned) > 1.0:
        warnings.append(
            f"video_duration_mismatch: rendered {duration:.2f}s vs planned {planned:.2f}s"
        )

    return _report(rubric, technical, errors, warnings, package)


def _report(rubric, technical, errors, warnings, package):
    # Technical categories get a provisional score; visual categories
    # must be scored by watching the video — never invented here.
    scores: dict[str, dict] = {}
    scores["camera_framing_16x9"] = {
        "score": 10.0 if not any("wrong_resolution" in e or "black_bars" in e or "wrong_aspect" in e for e in errors) else 0.0,
        "evidence": technical.get("resolution"),
        "method": "ffprobe + cropdetect",
    }
    scores["voice_narration_timing"] = {
        "score": 10.0 if not any("final_voice_line_cut_off" in e for e in errors) else 0.0,
        "evidence": f"planned={technical.get('planned_duration_sec')}s real_audio={technical.get('real_audio_duration_sec')}",
        "method": "timeline vs real WAV duration",
    }
    for name in ("character_consistency", "scene_environment",
                 "motion_smoothness", "story_hook_twist_payoff",
                 "sfx_music_sync", "captions_legibility"):
        scores[name] = {
            "score": None,
            "evidence": None,
            "method": "needs_visual_review — watch the full video and the contact sheet, then fill in 0-10 with a timestamped reason",
        }
    passed = not errors
    return {
        "title": package.get("title"),
        "slug": package.get("slug"),
        "technical": technical,
        "scores": scores,
        "errors": errors,
        "warnings": warnings,
        "acceptance": {
            "overall_threshold": rubric["acceptance"]["overall_threshold"],
            "per_category_minimum": rubric["acceptance"]["per_category_minimum"],
            "status": "TECHNICAL_PASS_NEEDS_VISUAL_REVIEW" if passed else "FAIL",
            "note": "Overall score cannot be computed until the visual categories are scored by watching the video. Do not publish on a technical pass alone.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Self-evaluate a 16:9 video against the rubric.")
    ap.add_argument("--package", required=True, help="Scene package JSON")
    ap.add_argument("--video", required=True, help="Rendered MP4 to check")
    ap.add_argument("--audio", help="Master WAV, if separate from the video")
    ap.add_argument("--out", help="Where to write the evaluation JSON")
    args = ap.parse_args()

    package = load_json(Path(args.package))
    report = evaluate(package, Path(args.video),
                      Path(args.audio) if args.audio else None)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["acceptance"]["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
