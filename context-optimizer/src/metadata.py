"""Layer 4 — Trích xuất metadata video bằng ffprobe thành JSON siêu nhẹ.

Thay vì gửi dữ liệu nhị phân/thô của video vào LLM, chỉ gửi file JSON
chứa các thông số cốt lõi (duration, resolution, fps, codec, size...).
"""

import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def ffprobe_json(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe lỗi: {out.stderr}")
    return json.loads(out.stdout)


def _fmt_duration(seconds: float) -> str:
    if not seconds:
        return "00:00:00"
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def extract_metadata(path: str) -> dict:
    """Trích metadata cốt lõi của 1 file media -> dict JSON gọn."""
    p = Path(path)
    probe = ffprobe_json(path)
    fmt = probe.get("format", {})
    vstream = next((s for s in probe.get("streams", [])
                    if s.get("codec_type") == "video"), {})
    astream = next((s for s in probe.get("streams", [])
                    if s.get("codec_type") == "audio"), {})

    dur = float(fmt.get("duration", 0) or 0)

    meta = {
        "file_name": p.name,
        "size_mb": round(float(fmt.get("size", 0)) / (1024 * 1024), 2),
        "duration": _fmt_duration(dur),
        "duration_sec": round(dur, 2),
        "resolution": f"{vstream.get('width', 0)}x{vstream.get('height', 0)}",
        "fps": _eval_fps(vstream.get("r_frame_rate")),
        "video_codec": vstream.get("codec_name", ""),
        "audio_codec": astream.get("codec_name", ""),
        "has_audio": bool(astream),
    }
    return meta


def _eval_fps(rate_str):
    if not rate_str:
        return 0
    if "/" in rate_str:
        a, b = rate_str.split("/")
        try:
            return round(float(a) / float(b), 2)
        except (ValueError, ZeroDivisionError):
            return 0
    try:
        return float(rate_str)
    except ValueError:
        return 0


def extract_dir_metadata(dir_path: str, extensions=(".mp4", ".mov", ".mkv", ".webm")):
    """Quét thư mục, trả list metadata JSON của mọi file media."""
    metas = []
    for f in sorted(Path(dir_path).rglob("*")):
        if f.suffix.lower() in extensions:
            try:
                metas.append(extract_metadata(str(f)))
            except Exception as e:
                metas.append({"file_name": f.name, "error": str(e)})
    return metas


def metadata_to_json(meta, out_path: str = None) -> str:
    s = json.dumps(meta, ensure_ascii=False, indent=2)
    if out_path:
        Path(out_path).write_text(s, encoding="utf-8")
    return s
