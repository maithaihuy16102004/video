"""Scene Overlay Renderer - Quy tắc 3 Giây & Kỹ thuật Cắt đè (30/70) bằng FFmpeg.
- Nửa đầu (30% hoặc 1.5s): Hiển thị Avatar nói (Hook).
- Nửa sau: Chèn đè B-Roll (video hoặc ảnh Ken Burns) toàn màn hình.
- Áp dụng Camera Effect (glitch_shake, zoom_in_slow, zoom_in_fast, pan).
- Giữ luồng âm thanh thoại xuyên suốt và tích hợp Sound FX (whoosh, boom, pop).
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SFX_DIR = Path(__file__).resolve().parent.parent / "assets" / "sfx"


def _resolve_sfx(sfx_name: Optional[str]) -> Optional[str]:
    """Tìm file sfx trong assets/sfx"""
    if not sfx_name:
        return None
    name_map = {
        "subtle_whoosh": "whoosh.wav",
        "whoosh": "whoosh.wav",
        "cinematic_boom_bass": "boom.wav",
        "boom": "boom.wav",
        "pop": "pop.wav",
        "chime": "chime.wav",
        "sub_drop": "boom.wav",
    }
    target = name_map.get(sfx_name, f"{sfx_name}.wav")
    path = SFX_DIR / target
    return str(path) if path.exists() else None


def _build_camera_filter(camera_effect: str, width: int, height: int,
                         total_frames: int, is_image: bool) -> str:
    """Tạo filter chuẩn cho avatar stream dựa trên camera_effect."""
    w2, h2 = width * 2, height * 2
    d = total_frames if is_image else 1

    if camera_effect == "glitch_shake":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"crop=w=iw*0.95:h=ih*0.95:"
            f"x='if(eq(mod(n\\,2)\\,0)\\,0\\,iw*0.05)':"
            f"y='if(eq(mod(n\\,3)\\,0)\\,0\\,ih*0.05)',"
            f"scale={width}:{height},setsar=1"
        )
    elif camera_effect == "zoom_in_fast":
        return (
            f"scale={w2}:{h2}:force_original_aspect_ratio=increase,crop={w2}:{h2},"
            f"zoompan=z='min(zoom+0.003,1.3)':d={d}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps=30,setsar=1"
        )
    else:  # zoom_in_slow (mặc định), static, pan_left, pan_right
        return (
            f"scale={w2}:{h2}:force_original_aspect_ratio=increase,crop={w2}:{h2},"
            f"zoompan=z='min(zoom+0.0012,1.15)':d={d}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps=30,setsar=1"
        )


def render_scene_with_overlay(
    avatar_input: str,
    b_roll_input: Optional[str],
    output_scene_path: str,
    scene_config: Dict[str, Any],
    scene_duration: float = 4.0,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Xử lý phối trộn video 30/70 trực tiếp qua FFmpeg Filter Complex."""
    out_p = Path(output_scene_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    visual = scene_config.get("visual_director", {})
    ratio = float(visual.get("b_roll_overlay_ratio", 0.0))
    camera_effect = visual.get("camera_effect", "zoom_in_slow")
    audio_fx = scene_config.get("audio_fx", {})
    sfx_file = _resolve_sfx(audio_fx.get("sfx_insert"))

    fps = 30
    total_frames = int(scene_duration * fps)

    is_avatar_img = Path(avatar_input).suffix.lower() in (
        ".jpg", ".jpeg", ".png", ".webp",
    )
    has_broll = bool(
        b_roll_input and os.path.exists(b_roll_input) and ratio > 0.0
    )
    is_broll_img = (
        Path(b_roll_input).suffix.lower()
        in (".jpg", ".jpeg", ".png", ".webp")
        if has_broll else False
    )

    # Thời điểm bắt đầu chèn đè B-Roll
    overlay_start = (
        max(1.0, scene_duration * (1.0 - ratio)) if ratio > 0.0
        else scene_duration
    )

    # --- Inputs ---
    cmd = ["ffmpeg", "-y"]
    # Input 0: avatar (ảnh hoặc video)
    if is_avatar_img:
        cmd += ["-loop", "1", "-t", str(scene_duration), "-i", avatar_input]
    else:
        cmd += ["-i", avatar_input]
    # Input 1: B-Roll (nếu có)
    if has_broll:
        if is_broll_img:
            cmd += ["-loop", "1", "-t", str(scene_duration), "-i", b_roll_input]
        else:
            cmd += ["-i", b_roll_input]
    # Input 2 (hoặc 1): SFX (nếu có)
    has_sfx = bool(sfx_file and os.path.exists(sfx_file))
    if has_sfx:
        cmd += ["-i", sfx_file]

    # --- Filter Complex ---
    avatar_cam = _build_camera_filter(camera_effect, width, height,
                                      total_frames, is_avatar_img)
    fc = f"[0:v]{avatar_cam}[avatar_fx];"

    if has_broll:
        w2, h2 = width * 2, height * 2
        if is_broll_img:
            fc += (
                f"[1:v]scale={w2}:{h2}:force_original_aspect_ratio=increase,"
                f"crop={w2}:{h2},"
                f"zoompan=z='min(zoom+0.0015,1.2)':d={total_frames}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={width}x{height}:fps=30,"
                f"setpts=PTS-STARTPTS+{overlay_start}/TB[broll];"
            )
        else:
            fc += (
                f"[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},"
                f"setpts=PTS-STARTPTS+{overlay_start}/TB[broll];"
            )
        fc += (
            f"[avatar_fx][broll]overlay="
            f"enable='gte(t,{overlay_start:.2f})':eof_action=pass[out_v]"
        )
    else:
        fc += "[avatar_fx]copy[out_v]"

    # SFX audio delay
    if has_sfx:
        sfx_idx = 2 if has_broll else 1
        sfx_time = float(audio_fx.get("sfx_timestamp", 0.0))
        delay_ms = int(sfx_time * 1000)
        fc += f";[{sfx_idx}:a]adelay={delay_ms}|{delay_ms}[delayed_sfx]"

    # --- Output ---
    cmd += ["-filter_complex", fc, "-map", "[out_v]"]
    if has_sfx:
        cmd += ["-map", "[delayed_sfx]", "-c:a", "aac", "-b:a", "128k"]
    cmd += [
        "-t", str(scene_duration),
        "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "22", "-pix_fmt", "yuv420p",
        str(out_p),
    ]

    print(f"[SceneRenderer] Render phân cảnh (ratio={ratio}, cam={camera_effect})...")
    res = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if res.returncode != 0:
        stderr_tail = res.stderr[-500:] if res.stderr else "(no stderr)"
        print(f"[SceneRenderer] FFmpeg lỗi:\n{stderr_tail}")
        raise RuntimeError(f"FFmpeg render lỗi: {stderr_tail}")

    print(f"[SceneRenderer] -> {out_p}")
    return str(out_p)
