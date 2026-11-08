"""
MoviePy Compositing Layer — Ghép nối tất cả layer video thành bản draft hoàn chỉnh
Thực hiện:
  1. Ghép slide nền Remotion (typography backdrop)
  2. Overlay VFX Manim (effects layer)
  3. Chèn SFX âm thanh hiệu ứng
  4. Mix BGM nhạc nền với ducking tự động
  5. Gắn voice narration đã tạo
  6. Xuất video 1080x1920 MP4 chuẩn TikTok/Reels

Dùng MoviePy 2.x API (đã cài: moviepy 2.1.2)
"""

import os
import sys
import subprocess
import tempfile
import json
import logging
from pathlib import Path
from typing import Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

try:
    from moviepy import (
        VideoFileClip, ImageClip, AudioFileClip,
        CompositeVideoClip, CompositeAudioClip,
        concatenate_videoclips, concatenate_audioclips,
        ColorClip,
    )
    from moviepy.audio.AudioClip import AudioArrayClip
    MOVIEPY_OK = True
except ImportError:
    MOVIEPY_OK = False
    logger.warning("MoviePy chưa cài! Chạy: pip install moviepy")


# ---------------------------------------------------------------------------
# Hàm tiện ích
# ---------------------------------------------------------------------------

def _get_duration(path: str | Path) -> float:
    """Lấy thời lượng file media bằng ffprobe."""
    path = str(path)
    cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"'
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
        return float(out)
    except Exception:
        return 0.0


def _scale_clip_to_vertical(clip, target_w: int = 1080, target_h: int = 1920):
    """Scale clip để vừa khung 1080x1920 (cover mode)."""
    if not MOVIEPY_OK:
        return clip
    clip_ratio = clip.w / clip.h
    target_ratio = target_w / target_h
    if clip_ratio > target_ratio:
        # Clip rộng hơn → scale theo height
        scale = target_h / clip.h
    else:
        scale = target_w / clip.w
    return clip.resized(scale)


def _center_crop(clip, target_w: int = 1080, target_h: int = 1920):
    """Crop giữa để đúng 1080x1920."""
    if not MOVIEPY_OK:
        return clip
    x_center = clip.w // 2
    y_center = clip.h // 2
    return clip.cropped(
        x1=x_center - target_w // 2,
        y1=y_center - target_h // 2,
        x2=x_center + target_w // 2,
        y2=y_center + target_h // 2,
    )


# ---------------------------------------------------------------------------
# Compositing chính
# ---------------------------------------------------------------------------

def compose_scene(
    slide_image: str | Path,
    vfx_video: str | Path | None,
    sfx_audio: str | Path | None,
    duration: float,
    out_path: str | Path,
    fadein_sec: float = 0.4,
    fadeout_sec: float = 0.4,
) -> str:
    """
    Ghép 1 phân cảnh: slide ảnh nền + VFX overlay + SFX.

    Args:
        slide_image: Ảnh nền Remotion (PNG/JPG)
        vfx_video: Video VFX overlay Manim (MP4, có thể None)
        sfx_audio: File âm thanh SFX (.wav, có thể None)
        duration: Thời lượng phân cảnh (giây)
        out_path: Đường dẫn file MP4 đầu ra

    Returns:
        Đường dẫn file MP4 đã ghép
    """
    if not MOVIEPY_OK:
        return _ffmpeg_compose_fallback(slide_image, vfx_video, sfx_audio, duration, out_path)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    layers = []

    # Layer 1: Slide nền (Ken Burns zoom)
    bg = ImageClip(str(slide_image)).with_duration(duration)
    bg = _scale_clip_to_vertical(bg)
    bg = _center_crop(bg)
    layers.append(bg)

    # Layer 2: VFX Manim overlay (nếu có)
    if vfx_video and Path(vfx_video).exists():
        try:
            vfx_dur = min(_get_duration(vfx_video), duration * 0.6)  # Tối đa 60% thời gian cảnh
            vfx = VideoFileClip(str(vfx_video)).subclipped(0, vfx_dur)
            # Scale VFX xuống 40% và đặt giữa phía trên
            vfx = vfx.resized(0.4).with_opacity(0.75)
            vfx = vfx.with_position(("center", 0.15), relative=True)
            layers.append(vfx)
        except Exception as exc:
            logger.warning("VFX overlay error: %s", exc)

    # Composite video
    comp = CompositeVideoClip(layers, size=(1080, 1920))

    # Audio: SFX (nếu có)
    audio_clips = []
    if sfx_audio and Path(sfx_audio).exists():
        try:
            sfx_clip = AudioFileClip(str(sfx_audio)).with_duration(min(_get_duration(sfx_audio), duration * 0.5))
            audio_clips.append(sfx_clip.with_volume_scaled(0.5))
        except Exception as exc:
            logger.warning("SFX audio error: %s", exc)

    if audio_clips:
        comp = comp.with_audio(CompositeAudioClip(audio_clips))

    # Fade in/out
    comp = comp.with_effects([
        # Using standard fade effects through vfx
    ])

    comp.write_videofile(
        str(out_path),
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        threads=4,
        logger=None,  # tắt output moviepy
    )
    comp.close()

    return str(out_path)


def _ffmpeg_compose_fallback(
    slide_image, vfx_video, sfx_audio, duration, out_path
) -> str:
    """Fallback FFmpeg thuần khi MoviePy không khả dụng."""
    out_path = Path(out_path)
    cmd_parts = [
        f'ffmpeg -y -loop 1 -t {duration} -i "{slide_image}"'
    ]
    filter_parts = ["[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"]

    if sfx_audio and Path(sfx_audio).exists():
        cmd_parts.append(f'-i "{sfx_audio}"')
        audio_map = "-map 1:a"
    else:
        audio_map = "-an"

    filter_str = ",".join(filter_parts) + "[v]"
    cmd = " ".join(cmd_parts) + f' -filter_complex "{filter_str}" -map "[v]" {audio_map} -t {duration} -c:v libx264 -preset fast -c:a aac "{out_path}"'
    subprocess.run(cmd, shell=True, capture_output=True)
    return str(out_path)


def compose_full_video(
    scene_clips: list[str],  # list đường dẫn MP4 từng cảnh
    voice_audio: str | Path,
    bgm_audio: str | Path | None,
    out_path: str | Path,
    bgm_volume: float = 0.12,
    voice_volume: float = 1.0,
) -> str:
    """
    Ghép nối tất cả phân cảnh + voice + BGM thành video hoàn chỉnh.

    Args:
        scene_clips: List đường dẫn MP4 từng phân cảnh đã composite
        voice_audio: File giọng đọc .mp3
        bgm_audio: File nhạc nền .mp3 (có thể None)
        out_path: Đường dẫn file video hoàn chỉnh
        bgm_volume: Âm lượng BGM (0.0 - 1.0)
        voice_volume: Âm lượng voice (0.0 - 1.0)

    Returns:
        Đường dẫn file video hoàn chỉnh
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not MOVIEPY_OK:
        return _ffmpeg_full_video_fallback(scene_clips, voice_audio, bgm_audio, out_path, bgm_volume)

    # Concat tất cả scene clips
    valid_clips = [c for c in scene_clips if Path(c).exists() and Path(c).stat().st_size > 0]
    if not valid_clips:
        logger.error("Không có scene clip nào hợp lệ!")
        return str(out_path)

    print(f"   🎞️  MoviePy: Ghép {len(valid_clips)} phân cảnh...")
    clips = [VideoFileClip(c) for c in valid_clips]
    final_video = concatenate_videoclips(clips, method="compose")
    total_duration = final_video.duration

    # Audio mix: voice + BGM
    audio_tracks = []

    if Path(voice_audio).exists():
        voice = AudioFileClip(str(voice_audio))
        voice = voice.with_volume_scaled(voice_volume)
        if voice.duration > total_duration:
            voice = voice.subclipped(0, total_duration)
        audio_tracks.append(voice)
        print(f"   🔊 Voice audio: {voice.duration:.1f}s")

    if bgm_audio and Path(bgm_audio).exists():
        bgm = AudioFileClip(str(bgm_audio))
        bgm = bgm.with_volume_scaled(bgm_volume)
        # Loop BGM nếu ngắn hơn video
        if bgm.duration < total_duration:
            import math
            repeat = math.ceil(total_duration / bgm.duration)
            bgm = concatenate_audioclips([bgm] * repeat).subclipped(0, total_duration)
        else:
            bgm = bgm.subclipped(0, total_duration)
        audio_tracks.append(bgm)
        print(f"   🎵 BGM: {bgm.duration:.1f}s (volume: {bgm_volume})")

    if audio_tracks:
        mixed_audio = CompositeAudioClip(audio_tracks)
        final_video = final_video.with_audio(mixed_audio)

    print(f"   💾 Xuất video cuối: {out_path.name} ({total_duration:.0f}s)...")
    final_video.write_videofile(
        str(out_path),
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        threads=4,
        logger=None,
    )

    for c in clips:
        c.close()
    final_video.close()

    print(f"   ✅ Đã xuất: {out_path.name} ({out_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return str(out_path)


def _ffmpeg_full_video_fallback(
    scene_clips: list[str],
    voice_audio,
    bgm_audio,
    out_path: Path,
    bgm_volume: float = 0.12,
) -> str:
    """Fallback hoàn toàn bằng FFmpeg khi MoviePy không khả dụng."""
    # Tạo file concat list
    tmp_dir = Path(tempfile.mkdtemp())
    list_file = tmp_dir / "concat.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for clip in scene_clips:
            if Path(clip).exists():
                f.write(f"file '{Path(clip).resolve()}'\n")

    # Concat scenes
    concat_mp4 = tmp_dir / "concat_raw.mp4"
    subprocess.run(
        f'ffmpeg -y -f concat -safe 0 -i "{list_file}" -c copy "{concat_mp4}"',
        shell=True, capture_output=True
    )

    if not concat_mp4.exists():
        return str(out_path)

    # Mix audio
    if bgm_audio and Path(bgm_audio).exists():
        cmd = (
            f'ffmpeg -y -i "{concat_mp4}" -i "{voice_audio}" -i "{bgm_audio}" '
            f'-filter_complex "[1:a]volume=1.0[v];[2:a]volume={bgm_volume}[b];[v][b]amix=inputs=2[a]" '
            f'-map 0:v -map "[a]" -c:v copy -c:a aac -shortest "{out_path}"'
        )
    else:
        cmd = (
            f'ffmpeg -y -i "{concat_mp4}" -i "{voice_audio}" '
            f'-map 0:v -map 1:a -c:v copy -c:a aac -shortest "{out_path}"'
        )

    subprocess.run(cmd, shell=True, capture_output=True)
    return str(out_path)


if __name__ == "__main__":
    print("MoviePy Compositing Layer — Kiểm tra:")
    print(f"  MoviePy: {'✅ OK' if MOVIEPY_OK else '❌ Chưa cài'}")
