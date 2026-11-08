"""Motion graphic đơn giản: tạo intro overlay (title card) bằng Pillow."""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402


def _font(size):
    # tìm font hệ thống
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
    ]
    for f in candidates:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    return ImageFont.load_default()


def make_intro_overlay(video_path: str, work_dir: Path, title: str = "AI EDITOR") -> str:
    """Vẽ 1 frame title card (PNG) để ghép đầu video làm motion graphic intro."""
    W, H = 576, 1024
    img = Image.new("RGBA", (W, H), (12, 12, 20, 255))
    d = ImageDraw.Draw(img)

    # gradient đơn giản
    for y in range(H):
        t = y / H
        r = int(12 + 20 * t)
        g = int(12 + 30 * t)
        b = int(60 + 100 * t)
        d.line([(0, y), (W, y)], fill=(r, g, b, 255))

    big = _font(72)
    small = _font(36)

    text = title.upper()
    bbox = d.textbbox((0, 0), text, font=big)
    tw = bbox[2] - bbox[0]
    d.text(((W - tw) / 2, H * 0.42), text, font=big, fill=(255, 255, 255, 255))
    sub = "LET THE AI EDIT"
    bbox2 = d.textbbox((0, 0), sub, font=small)
    tw2 = bbox2[2] - bbox2[0]
    d.text(((W - tw2) / 2, H * 0.52), sub, font=small, fill=(120, 220, 255, 255))

    out = work_dir / "intro.png"
    img.convert("RGB").save(str(out))
    return str(out)


def prepend_intro(video_path: str, intro_png: str, out_path: str,
                  duration: float = 2.0) -> str:
    """Ghép intro (ảnh title card) vào đầu video. Tạo track audio im lặng cho intro
    để đồng bộ, rồi concat theo thời gian (tránh lỗi AAC/xfade)."""
    import subprocess
    # 1) intro video từ ảnh + audio im lặng
    intro_v = out_path.rsplit(".", 1)[0] + "_intro.mp4"
    cmd1 = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", intro_png,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(duration),
        "-vf", "scale=576:1024:force_original_aspect_ratio=decrease,"
               "pad=576:1024:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", "-shortest", intro_v,
    ]
    subprocess.run(cmd1, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")

    # 2) concat intro + video gốc (re-encode để đồng bộ)
    import os
    concat_list = out_path.rsplit(".", 1)[0] + "_list.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        f.write(f"file '{intro_v.replace(os.sep, '/')}'\n")
        f.write(f"file '{video_path.replace(os.sep, '/')}'\n")
    cmd2 = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", out_path,
    ]
    r = subprocess.run(cmd2, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        import shutil
        print(f"[avi-editor] ghép intro lỗi, giữ video gốc: {r.stderr[-400:]}")
        shutil.copy2(video_path, out_path)
    return out_path
