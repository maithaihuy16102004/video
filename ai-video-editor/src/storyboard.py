"""Tạo storyboard (lưới frame) để người dùng duyệt trước khi xuất."""

import math
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image  # noqa: E402
from ffmpeg_utils import ffprobe_json  # noqa: E402


def make_storyboard(video_path: str, work_dir: Path, cols: int = 4,
                    vertical: bool = True) -> str:
    dur = float(ffprobe_json(video_path)["format"]["duration"])
    if dur <= 0:
        dur = 1.0

    total_frames = cols * 3  # 3 hàng
    if total_frames > 12:
        total_frames = 12
    rows = math.ceil(total_frames / cols)

    # trích frame ở các mốc đều
    stamps = [dur * (i + 0.5) / total_frames for i in range(total_frames)]
    frame_dir = work_dir / "frames"
    frame_dir.mkdir(exist_ok=True)

    frame_paths = []
    thumb_w = 360
    for i, t in enumerate(stamps):
        fp = frame_dir / f"f{i:02d}.jpg"
        cmd = ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", video_path,
               "-frames:v", "1", "-vf", f"scale={thumb_w}:-2", "-q:v", "2", str(fp)]
        subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
        if fp.exists():
            frame_paths.append(fp)

    if not frame_paths:
        return ""

    # ghép lưới bằng Pillow
    imgs = [Image.open(p) for p in frame_paths]
    cell_w = thumb_w
    cell_h = max(im.height for im in imgs)
    pad = 6
    grid = Image.new("RGB", (cols * (cell_w + pad) + pad,
                             rows * (cell_h + pad) + pad), (20, 20, 20))
    for idx, im in enumerate(imgs):
        r, c = divmod(idx, cols)
        grid.paste(im, (pad + c * (cell_w + pad), pad + r * (cell_h + pad)))

    out = work_dir / "storyboard.jpg"
    grid.save(str(out), quality=85)
    return str(out)
