"""Source video intake — checksum, ffprobe metadata, immutable storage.

The original video is preserved as an immutable source asset: it is
copied once into the project directory and never overwritten. A
re-upload with the same checksum reuses the stored copy; a different
file under the same name is refused rather than silently replacing
the source (a new project is the correct remedy).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .schema import SUPPORTED_CONTAINERS, SourceVideo


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, streamed (no full read into memory)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_video(path: Path) -> dict:
    """ffprobe metadata for one video file. Raises on failure."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"source video not found: {path}")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr[:300]}")
    payload = json.loads(result.stdout)
    video = next((s for s in payload.get("streams", [])
                  if s.get("codec_type") == "video"), None)
    audio = next((s for s in payload.get("streams", [])
                  if s.get("codec_type") == "audio"), None)
    if video is None:
        raise RuntimeError(f"no video stream in {path}")
    width = int(video.get("width", 0))
    height = int(video.get("height", 0))
    fps_raw = video.get("avg_frame_rate", "0/1")
    try:
        num, den = fps_raw.split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    duration = float(payload.get("format", {}).get("duration", 0.0) or 0.0)
    orientation = ("vertical" if height > width else
                   "horizontal" if width > height else "square")
    aspect = ""
    if width and height:
        from math import gcd
        divisor = gcd(width, height)
        aspect = f"{width // divisor}:{height // divisor}"
    container = path.suffix.lower().lstrip(".")
    return {
        "resolution": f"{width}x{height}",
        "fps": round(fps, 3),
        "duration_sec": round(duration, 3),
        "video_codec": str(video.get("codec_name", "")),
        "audio_codec": str(audio.get("codec_name", "")) if audio else "",
        "aspect_ratio": aspect,
        "orientation": orientation,
        "has_audio": audio is not None,
        "container": container,
        "width": width,
        "height": height,
    }


def store_source_copy(source_path: Path, project_dir: Path) -> SourceVideo:
    """Copy the source into <project_dir>/source/ immutably and probe
    it. Returns the SourceVideo record. Refuses to overwrite a
    different file; reuses an identical one."""
    source_path = Path(source_path)
    container = source_path.suffix.lower().lstrip(".")
    if container not in SUPPORTED_CONTAINERS:
        raise ValueError(
            f"unsupported container {container!r}; supported: "
            f"{list(SUPPORTED_CONTAINERS)}")
    checksum = sha256_file(source_path)
    source_dir = Path(project_dir) / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    stored = source_dir / source_path.name
    if stored.exists():
        if sha256_file(stored) != checksum:
            raise ValueError(
                f"refusing to overwrite the immutable source asset "
                f"{stored.name} with a different file")
    else:
        shutil.copy2(source_path, stored)
    info = probe_video(stored)
    return SourceVideo(
        file_name=source_path.name,
        file_size_bytes=stored.stat().st_size,
        resolution=info["resolution"], fps=info["fps"],
        duration_sec=info["duration_sec"],
        video_codec=info["video_codec"], audio_codec=info["audio_codec"],
        aspect_ratio=info["aspect_ratio"],
        orientation=info["orientation"], has_audio=info["has_audio"],
        container=info["container"], sha256=checksum,
        stored_path=str(stored))
