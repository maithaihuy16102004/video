"""Source-video probing: ffprobe metadata + SHA-256 checksum.

The original video is treated as an IMMUTABLE source asset: this
module only reads it. It never writes to the source path, never
transcodes in place, and records the checksum so later stages (and
the schema gate) can verify the asset was not swapped or modified.

Output is a :class:`SourceInfo` (engine model) which converts to the
schema ``SourceVideo`` dict via ``to_source_video_dict``.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any

from .capabilities import run_command
from .models import SourceInfo

SUPPORTED_CONTAINERS = ("mp4", "mov", "mkv", "webm")


class ProbeError(ValueError):
    """ffprobe failed or the file is not a usable video source."""


def sha256_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    """Streaming SHA-256 (works for multi-GB sources)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(path: str | Path, expected_sha256: str) -> bool:
    """True when the file's current checksum matches the recorded one."""
    return sha256_file(path) == expected_sha256.lower()


def _parse_fps(value: Any) -> float:
    """Parse ffprobe frame-rate values ('30000/1001', '30', 30.0)."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if "/" in text:
            num, _, den = text.partition("/")
            try:
                den_f = float(den)
                return float(num) / den_f if den_f else 0.0
            except ValueError:
                return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0
    return 0.0


def _stream_rotation(stream: dict[str, Any]) -> float:
    """Display-matrix rotation in degrees (0 when absent)."""
    for side in stream.get("side_data_list", []) or []:
        if isinstance(side, dict) and "rotation" in side:
            try:
                return float(side["rotation"])
            except (TypeError, ValueError):
                pass
    tags = stream.get("tags", {}) or {}
    if isinstance(tags, dict) and "rotate" in tags:
        try:
            return float(tags["rotate"])
        except (TypeError, ValueError):
            pass
    return 0.0


def run_ffprobe(path: str | Path) -> dict[str, Any]:
    """Run ffprobe and return the parsed JSON output."""
    exe = shutil.which("ffprobe")
    if not exe:
        raise ProbeError("ffprobe is not installed or not on PATH")
    proc = run_command([exe, "-v", "error", "-show_format", "-show_streams",
                        "-of", "json", str(path)], timeout=120.0)
    if proc.returncode != 0:
        raise ProbeError(f"ffprobe failed for {path}: "
                         f"{(proc.stderr or '').strip()[:300]}")
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ProbeError(f"ffprobe output for {path} is not JSON: {exc}") from exc


def probe_source(path: str | Path) -> SourceInfo:
    """Probe one source video file. Read-only; never modifies it."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ProbeError(f"source file does not exist: {path}")
    if file_path.stat().st_size == 0:
        raise ProbeError(f"source file is empty: {path}")

    data = run_ffprobe(file_path)
    streams = data.get("streams", []) or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ProbeError(f"no video stream found in {path}")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {}) or {}

    fps = _parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    duration = 0.0
    for raw in (fmt.get("duration"), video.get("duration")):
        try:
            duration = float(raw)
        except (TypeError, ValueError):
            continue
        if duration > 0:
            break
    try:
        bitrate = int(fmt.get("bit_rate") or 0)
    except (TypeError, ValueError):
        bitrate = 0
    container = file_path.suffix.lstrip(".").lower()
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ProbeError(f"video stream in {path} has no dimensions")

    return SourceInfo(
        path=str(file_path),
        file_name=file_path.name,
        file_size_bytes=file_path.stat().st_size,
        sha256=sha256_file(file_path),
        width=width,
        height=height,
        fps=fps,
        duration_sec=duration,
        video_codec=str(video.get("codec_name") or ""),
        audio_codec=str(audio.get("codec_name") or "") if audio else "",
        pix_fmt=str(video.get("pix_fmt") or ""),
        bitrate=bitrate,
        container=container,
        rotation_deg=_stream_rotation(video),
        probe_raw=data,
    )


def container_supported(source: SourceInfo) -> tuple[bool, str]:
    """Schema container gate (AFF022 vocabulary). Probe records; the
    schema validator refuses unsupported containers at project level."""
    if source.container in SUPPORTED_CONTAINERS:
        return True, ""
    return False, (f"unsupported container {source.container!r}; supported: "
                   f"{list(SUPPORTED_CONTAINERS)}")


def reduced_aspect(width: int, height: int) -> str:
    """Reduced 'W:H' string for arbitrary dimensions."""
    g = math.gcd(width, height) or 1
    return f"{width // g}:{height // g}"
