"""16:9 YouTube render commands.

Builds the exact FFmpeg commands the V5 ProductionRenderService
uses, locked to 1920x1080 / 24 fps / H.264 High / AAC 48 kHz.

Important: this module only *builds* commands. It never runs a
render on import, and it never invents a resolution — the config is
the single source of truth. A 9:16 input is rejected here instead
of being silently pillarboxed into 16:9.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "youtube_16x9.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_master_command(
    frames_pattern: str,
    audio_path: str | Path,
    out_path: str | Path,
    config: dict | None = None,
) -> list[str]:
    """FFmpeg command: PNG frames + WAV audio -> 1080p 16:9 MP4 master."""
    config = config or load_config()
    v = config["video"]
    a = config["audio"]
    return [
        "ffmpeg", "-y",
        "-framerate", str(v["fps"]),
        "-i", frames_pattern,
        "-i", str(audio_path),
        "-c:v", v["codec"],
        "-profile:v", v["profile"],
        "-level", v["level"],
        "-pix_fmt", v["pixel_format"],
        "-vf", f"scale={v['width']}:{v['height']},setsar=1,fps={v['fps']},format={v['pixel_format']}",
        "-b:v", v["bitrate_video"],
        "-maxrate", v["maxrate"],
        "-bufsize", v["bufsize"],
        "-c:a", a["codec"],
        "-b:a", a["bitrate_audio"],
        "-ar", str(a["sample_rate_hz"]),
        "-ac", str(a["channels"]),
        # YouTube loudness: -14 LUFS, true peak capped at -1 dBFS.
        "-af", f"loudnorm=I={a['loudness_lufs']}:TP={a['true_peak_dbfs_max']}:LRA=11",
        "-movflags", "+faststart",
        "-shortest",
        str(out_path),
    ]


def build_thumbnail_command(
    master_path: str | Path,
    out_path: str | Path,
    at_seconds: float = 2.0,
    config: dict | None = None,
) -> list[str]:
    config = config or load_config()
    ex = config["export"]
    return [
        "ffmpeg", "-y",
        "-ss", str(at_seconds),
        "-i", str(master_path),
        "-frames:v", "1",
        "-vf", f"scale={ex['thumbnail_width']}:{ex['thumbnail_height']}",
        str(out_path),
    ]


def build_contact_sheet_command(
    frames_pattern: str,
    out_path: str | Path,
    cols: int = 4,
    rows: int = 3,
) -> list[str]:
    return [
        "ffmpeg", "-y",
        "-i", frames_pattern,
        "-vf", f"scale=480:-1,tile={cols}x{rows}",
        "-frames:v", "1",
        str(out_path),
    ]


def validate_16x9_input(width: int, height: int) -> None:
    if (width, height) != (1920, 1080):
        raise ValueError(
            f"Refusing to render {width}x{height} as a 16:9 YouTube master. "
            "Render natively at 1920x1080 — do not pillarbox a 9:16 Short."
        )
