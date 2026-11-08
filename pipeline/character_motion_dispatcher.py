"""Dispatch character scenes to real animation engines; never fake motion silently."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHARMOTION_SRC = ROOT / "charmotion" / "src"
sys.path.insert(0, str(CHARMOTION_SRC))
from liveportrait_runner import LivePortraitRunner  # noqa: E402


def _asset(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def preflight_scene(scene: dict[str, Any]) -> list[str]:
    """Return actionable errors before an expensive render starts."""
    errors: list[str] = []
    character = scene["character"]
    avatar = _asset(character["avatar_id"])
    driver = _asset(character["driving_video_ref"])
    if not avatar.exists():
        errors.append(f"{scene['id']}: thiếu avatar {avatar}")
    if not driver.exists():
        errors.append(f"{scene['id']}: thiếu driving video {driver}")
    if character["pipeline"] == "LivePortrait":
        lp_root = Path(os.getenv("LIVEPORTRAIT_ROOT", ROOT / "charmotion" / "LivePortrait"))
        if not (lp_root / "inference.py").exists():
            errors.append(f"{scene['id']}: chưa cài LivePortrait tại {lp_root}")
    elif character["pipeline"] == "SadTalker":
        st_root = Path(os.getenv("SADTALKER_ROOT", ROOT / "SadTalker"))
        if not (st_root / "inference.py").exists():
            errors.append(f"{scene['id']}: chưa cài SadTalker tại {st_root}")
    return errors


def render_character_scene(
    scene: dict[str, Any], output_video: str, driven_audio: str | None = None
) -> str:
    """Render one compiled scene with the requested real character engine."""
    character = scene["character"]
    errors = preflight_scene(scene)
    if errors:
        raise RuntimeError("\n".join(errors))
    avatar = _asset(character["avatar_id"])
    driver = _asset(character["driving_video_ref"])
    output = Path(output_video).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if character["pipeline"] == "LivePortrait":
        runner = LivePortraitRunner(os.getenv("LIVEPORTRAIT_ROOT"))
        return runner.animate(
            str(avatar), str(output), emotion_tag=scene["emotion"],
            duration=float(scene["duration"]),
            driving_video_ref=str(driver),
            motion_intensity=float(character["motion_intensity"]),
            allow_static_fallback=False,
        )

    if not driven_audio:
        raise RuntimeError(f"{scene['id']}: SadTalker cần driven_audio đã đồng bộ lời thoại.")
    st_root = Path(os.getenv("SADTALKER_ROOT", ROOT / "SadTalker"))
    cmd = [
        sys.executable, str(st_root / "inference.py"),
        "--driven_audio", str(Path(driven_audio).resolve()),
        "--source_image", str(avatar),
        "--result_dir", str(output.parent),
        "--preprocess", "full",
        "--enhancer", "gfpgan",
    ]
    result = subprocess.run(cmd, cwd=st_root, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"SadTalker inference thất bại: {result.stderr[-1000:]}")
    candidates = sorted(output.parent.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError("SadTalker không tạo file MP4.")
    candidates[0].replace(output)
    return str(output)
