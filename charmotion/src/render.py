"""Render toàn bộ timeline: duyệt scenes, render frame, encode ffmpeg thành MP4."""

import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from scene import render_frame


def render_video(script: dict, out_path: str, work_dir: Path = None,
                 audio_path: str = None, verbose=True) -> str:
    width = script.get("width", 1080)
    height = script.get("height", 1920)
    fps = script.get("fps", 30)
    scenes = script.get("scenes", [])

    if not scenes:
        raise ValueError("script không có scene nào")

    own_work = work_dir is None
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="charmotion_"))
    frame_dir = work_dir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    fonts_cache = {}
    frame_idx = 0
    total_frames = 0
    for sc in scenes:
        total_frames += int(round(sc.get("duration", 3.0) * fps))

    for si, sc in enumerate(scenes):
        dur = sc.get("duration", 3.0)
        n_frames = int(round(dur * fps))
        if verbose:
            print(f"[charmotion] scene {si+1}/{len(scenes)}: "
                  f"\"{sc.get('title', '')}\" ({dur}s, {n_frames} frames)")
        for f in range(n_frames):
            t_scene = f / fps
            t_global = frame_idx / fps
            img = render_frame(sc, t_scene, t_global, width, height, fps, fonts_cache)
            img.convert("RGB").save(frame_dir / f"frame_{frame_idx:06d}.png")
            frame_idx += 1

    if verbose:
        print(f"[charmotion] đã render {frame_idx} frames")

    # encode bằng ffmpeg
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-framerate", str(fps),
           "-i", str(frame_dir / "frame_%06d.png")]
    if audio_path and Path(audio_path).exists():
        cmd += ["-i", str(audio_path)]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p"]
    if audio_path and Path(audio_path).exists():
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += [str(out_path)]

    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"[charmotion] ffmpeg lỗi: {r.stderr[-800:]}")
    else:
        if verbose:
            print(f"[charmotion] xuất video: {out_path}")

    if own_work:
        shutil.rmtree(work_dir, ignore_errors=True)

    return str(out_path)
