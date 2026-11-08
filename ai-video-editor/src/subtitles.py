"""Burn phụ đề vào video (style TikTok dọc: chữ to, giữa, viền đen, canh trên)."""

import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def render_burnt_subtitles(video_path: str, srt_path: str, out_path: str,
                           cfg: dict = None, vertical: bool = True):
    cfg = cfg or {}
    # style mặc định hợp video dọc TikTok
    fontsize = cfg.get("fontsize", 26)
    fontcolor = cfg.get("fontcolor", "white")
    border_color = cfg.get("border_color", "black")
    # margin top để chữ nằm dưới 1/3 trên (vertical video)
    if vertical:
        # canh giữa ngang, đặt lệch lên phía trên
        alignment = 10  # centered-ish (MIDDLE)
        margin_v = "180"
    else:
        alignment = 2
        margin_v = "50"

    # path phụ đề cần escape cho ffmpeg (Windows)
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    srt_escaped = srt_escaped.replace("'", r"\'")

    vf = (
        f"subtitles='{srt_escaped}'"
        f":force_style='FontSize={fontsize},FontName=Arial,"
        f"PrimaryColour=&H00FFFFFF&,"
        f"OutlineColour=&H00000000&,BorderStyle=1,Outline=3,Shadow=1,"
        f"Alignment={alignment},MarginV={margin_v},Bold=1'"
    )
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vf", vf,
           "-c:v", "libx264", "-preset", "fast", "-crf", "20",
           "-c:a", "copy", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"[avi-editor] burn phụ đề lỗi, giữ video chưa burn: {r.stderr[-500:]}")
        import shutil
        shutil.copy2(video_path, out_path)
    return out_path
