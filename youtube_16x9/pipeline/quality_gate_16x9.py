"""16:9 YouTube quality gate.

Runs BEFORE any render is uploaded. A package that fails a hard
check must not be published as a 16:9 YouTube video — the most common
failures in the V51 drafts were wrong aspect handling, captions
running outside the safe title area, and shots that were far too
long for the Ricks-style pacing.

Checks are pure and testable: give it a package dict and optional
probe info (from ffprobe) and it returns a structured report.
No file is modified.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "youtube_16x9.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@dataclass
class GateResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "errors": self.errors, "warnings": self.warnings}


def check_package(package: dict, config: dict | None = None) -> GateResult:
    config = config or load_config()
    errors: list[str] = []
    warnings: list[str] = []

    video = config["video"]
    if package.get("aspect_ratio") != video["aspect_ratio"]:
        errors.append(
            f"wrong_aspect_ratio: {package.get('aspect_ratio')} (must be 16:9)"
        )
    if (package.get("width"), package.get("height")) != (video["width"], video["height"]):
        errors.append(
            f"wrong_resolution: {package.get('width')}x{package.get('height')} "
            "(must be 1920x1080)"
        )
    if package.get("fps") != video["fps"]:
        errors.append(f"wrong_fps: {package.get('fps')} (must be {video['fps']})")

    shots = package.get("shots", [])
    if not shots:
        errors.append("no_shots: package has no shots")
        return GateResult(passed=False, errors=errors, warnings=warnings)

    story = config["story"]
    shot_min = float(story["shot_duration_sec"]["min"])
    shot_max = float(story["shot_duration_sec"]["max"])
    for shot in shots:
        dur = float(shot.get("duration_sec", 0))
        if dur > shot_max:
            errors.append(
                f"shot_too_long: {shot.get('shot_id')} is {dur}s (max {shot_max}s)"
            )
        elif dur < shot_min:
            warnings.append(
                f"shot_too_short: {shot.get('shot_id')} is {dur}s (min {shot_min}s)"
            )
        caption = shot.get("script_line") or shot.get("staging", {}).get("caption", "")
        max_chars = int(story["caption"]["max_chars_per_line"]) * int(
            story["caption"]["max_lines"]
        )
        if len(caption) > max_chars:
            errors.append(
                f"caption_overflow: {shot.get('shot_id')} has {len(caption)} chars "
                f"(max {max_chars} for 2 lines at 1080p)"
            )

    purposes = [s.get("purpose") for s in shots]
    if "HOOK" not in purposes:
        errors.append("no_hook: first shot must be the hook")
    if "TWIST" not in purposes:
        errors.append("no_twist: package needs a twist shot at 70-85% of runtime")
    if "PAYOFF" not in purposes:
        errors.append("no_payoff: package needs a closing payoff shot")

    total = float(package.get("total_duration_sec", 0) or 0)
    if total > float(story["max_total_duration_sec"]):
        errors.append(
            f"too_long: {total}s exceeds the {story['max_total_duration_sec']}s "
            "limit for this format"
        )
    return GateResult(passed=not errors, errors=errors, warnings=warnings)


def probe_video(path: Path) -> dict:
    """Return width/height/fps/duration via ffprobe, or {} if unavailable."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return {}
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return {}
    stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    fps = stream.get("r_frame_rate", "0/1")
    num, den = (int(x) for x in fps.split("/")) if "/" in fps else (0, 1)
    return {
        "width": stream.get("width"),
        "height": stream.get("height"),
        "fps": round(num / den, 2) if den else None,
        "duration_sec": float(data.get("format", {}).get("duration", 0) or 0),
        "codec": stream.get("codec_name"),
    }


def check_rendered_video(path: Path, config: dict | None = None) -> GateResult:
    config = config or load_config()
    errors: list[str] = []
    warnings: list[str] = []
    probe = probe_video(path)
    if not probe:
        return GateResult(passed=False, errors=["probe_failed: ffprobe could not read the file"])
    video = config["video"]
    if (probe.get("width"), probe.get("height")) != (video["width"], video["height"]):
        errors.append(
            f"wrong_resolution: rendered {probe.get('width')}x{probe.get('height')} "
            "(must be 1920x1080 — check for pillarboxing or a 9:16 crop)"
        )
    if probe.get("fps") != video["fps"]:
        warnings.append(f"unexpected_fps: {probe.get('fps')} (expected {video['fps']})")
    return GateResult(passed=not errors, errors=errors, warnings=warnings)
