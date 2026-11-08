r"""
Character Animation Bridge — Hoạt hoá nhân vật từ ảnh tĩnh
Hỗ trợ:
  1. LivePortrait (KwaiVGI) — ép chuyển động mặt/thân theo driving video
  2. AnimateAnyone (Moore) — hoạt hoá toàn thân theo pose skeleton
  3. Fallback: Ken Burns zoom/pan trên ảnh nhân vật (không cần GPU model)

Yêu cầu (tuỳ chọn, cài thêm để dùng AI đầy đủ):
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
  pip install -r D:\Agent\ai-engine\character\LivePortrait\requirements.txt
"""

import os
import sys
import subprocess
import shutil
import tempfile
import logging
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

AGENT_ROOT = Path(__file__).resolve().parent.parent.parent
LIVEPORTRAIT_DIR = Path(__file__).parent / "LivePortrait"
ANIMATE_ANYONE_DIR = Path(__file__).parent / "AnimateAnyone"

LIVEPORTRAIT_AVAILABLE = LIVEPORTRAIT_DIR.exists() and (LIVEPORTRAIT_DIR / "inference.py").exists()
ANIMATE_ANYONE_AVAILABLE = ANIMATE_ANYONE_DIR.exists()

try:
    import torch
    TORCH_AVAILABLE = True
    GPU_AVAILABLE = torch.cuda.is_available()
except ImportError:
    TORCH_AVAILABLE = False
    GPU_AVAILABLE = False


def setup_liveportrait() -> bool:
    """
    Clone LivePortrait nếu chưa có. Trả về True nếu thành công.
    Lưu ý: Cần VRAM ~6GB và PyTorch CUDA.
    """
    if LIVEPORTRAIT_DIR.exists():
        logger.info("LivePortrait đã tồn tại tại: %s", LIVEPORTRAIT_DIR)
        return True

    if not TORCH_AVAILABLE:
        logger.warning("⚠️  Cần cài PyTorch trước: pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
        return False

    print("📦 Đang clone LivePortrait (KwaiVGI)...")
    result = subprocess.run(
        f'git clone https://github.com/KwaiVGI/LivePortrait.git "{LIVEPORTRAIT_DIR}"',
        shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error("Lỗi clone LivePortrait: %s", result.stderr)
        return False

    # Cài requirements
    req_file = LIVEPORTRAIT_DIR / "requirements.txt"
    if req_file.exists():
        print("📦 Đang cài requirements LivePortrait...")
        subprocess.run(f'pip install -r "{req_file}" --quiet', shell=True)

    print("✅ LivePortrait đã sẵn sàng!")
    return True


def animate_with_liveportrait(
    source_image: str | Path,
    driving_video: str | Path,
    out_path: str | Path,
) -> bool:
    """
    Hoạt hoá ảnh nhân vật tĩnh theo chuyển động từ driving_video.

    Args:
        source_image: Ảnh nhân vật tĩnh (.jpg, .png)
        driving_video: Video mẫu chuyển động (có thể là webcam recording)
        out_path: Đường dẫn file video đầu ra (.mp4)

    Returns:
        True nếu thành công
    """
    if not LIVEPORTRAIT_AVAILABLE:
        if not setup_liveportrait():
            logger.warning("LivePortrait không khả dụng, dùng Ken Burns fallback")
            return False

    if not GPU_AVAILABLE:
        logger.warning("⚠️  LivePortrait cần GPU CUDA. Chuyển sang Ken Burns fallback.")
        return False

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    inference_script = LIVEPORTRAIT_DIR / "inference.py"
    cmd = (
        f'python "{inference_script}" '
        f'--source_image "{source_image}" '
        f'--driving_video "{driving_video}" '
        f'--output_dir "{out_path.parent}" '
        f'--output_name "{out_path.stem}"'
    )

    print(f"   🎭 LivePortrait: Đang hoạt hoá nhân vật từ ảnh...")
    result = subprocess.run(cmd, shell=True, cwd=str(LIVEPORTRAIT_DIR), capture_output=True, text=True)

    if result.returncode == 0 and out_path.exists():
        print(f"   ✅ Nhân vật đã được hoạt hoá: {out_path.name}")
        return True
    else:
        logger.warning("LivePortrait thất bại: %s", result.stderr[:300])
        return False


def ken_burns_character(
    source_image: str | Path,
    duration: float,
    out_path: str | Path,
    effect: str = "zoom_in",
) -> bool:
    """
    Fallback Ken Burns: tạo ảo giác chuyển động từ ảnh tĩnh bằng FFmpeg.

    Args:
        source_image: Ảnh nhân vật (.jpg, .png)
        duration: Thời lượng video (giây)
        out_path: Đường dẫn file video đầu ra (.mp4)
        effect: "zoom_in", "zoom_out", "pan_left", "pan_right", "float" (nhẹ nhàng)

    Returns:
        True nếu thành công
    """
    source_image = Path(source_image)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Chọn filter Ken Burns theo effect
    EFFECTS = {
        "zoom_in":    "zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fps}:s=1080x1920:fps={fps}",
        "zoom_out":   "zoompan=z='if(lte(zoom,1.0),1.5,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fps}:s=1080x1920:fps={fps}",
        "pan_left":   "zoompan=z=1.3:x='iw*0.1*(on/{fps})':y='ih/2-(ih/zoom/2)':d={fps}:s=1080x1920:fps={fps}",
        "pan_right":  "zoompan=z=1.3:x='iw*0.1*(1-on/{fps})':y='ih/2-(ih/zoom/2)':d={fps}:s=1080x1920:fps={fps}",
        "float":      "zoompan=z='1.05+0.05*sin(2*PI*on/{fps}/4)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fps}:s=1080x1920:fps={fps}",
    }

    fps = 24
    total_frames = int(duration * fps)
    filter_tpl = EFFECTS.get(effect, EFFECTS["zoom_in"])
    filter_str = filter_tpl.format(fps=total_frames)

    cmd = (
        f'ffmpeg -y -loop 1 -i "{source_image}" '
        f'-vf "{filter_str},format=yuv420p" '
        f'-t {duration} -c:v libx264 -preset fast -crf 23 '
        f'"{out_path}"'
    )

    result = subprocess.run(cmd, shell=True, capture_output=True)
    return out_path.exists() and out_path.stat().st_size > 0


def animate_character(
    source_image: str | Path,
    duration: float = 5.0,
    out_path: str | Path | None = None,
    driving_video: str | Path | None = None,
    effect: str = "float",
) -> str:
    """
    API thống nhất: Hoạt hoá nhân vật với tự động fallback.

    Thử LivePortrait → Ken Burns Fallback.

    Args:
        source_image: Ảnh nhân vật (.jpg, .png)
        duration: Thời lượng (giây)
        out_path: Đường dẫn đầu ra. None → tạo file tạm.
        driving_video: Video mẫu chuyển động (chỉ cần cho LivePortrait)
        effect: Hiệu ứng Ken Burns ("zoom_in", "zoom_out", "pan_left", "pan_right", "float")

    Returns:
        Đường dẫn tuyệt đối đến file video nhân vật đã hoạt hoá.
    """
    if out_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        out_path = Path(tmp.name)
        tmp.close()
    else:
        out_path = Path(out_path)

    # Thử LivePortrait nếu có driving_video và model khả dụng
    if driving_video and LIVEPORTRAIT_AVAILABLE and GPU_AVAILABLE and TORCH_AVAILABLE:
        if animate_with_liveportrait(source_image, driving_video, out_path):
            return str(out_path)

    # Fallback Ken Burns
    print(f"   🎞️  Ken Burns '{effect}': Tạo chuyển động từ ảnh tĩnh ({duration}s)...")
    ken_burns_character(source_image, duration, out_path, effect=effect)
    return str(out_path)


if __name__ == "__main__":
    # Test ken burns trên ảnh bất kỳ
    import sys
    test_img = sys.argv[1] if len(sys.argv) > 1 else r"D:\Agent\assets\characters\default.jpg"
    out = animate_character(test_img, duration=5.0, out_path="test_character.mp4", effect="float")
    print(f"Output: {out}")
