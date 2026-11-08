"""Phân tích phong cách video tham khảo -> style profile (tái dùng = "skill")."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ffmpeg_utils import ffprobe_json  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def analyze_style(ref_dir: Path, work_dir: Path) -> dict:
    """Quét các video trong thư mục tham khảo, tổng hợp độ dài trung bình,
    tỉ lệ khung hình, và tốc độ cắt (số cảnh/giây) để build style profile."""
    vids = list(ref_dir.glob("*.mp4")) + list(ref_dir.glob("*.mov")) + \
        list(ref_dir.glob("*.webm")) + list(ref_dir.glob("*.mkv"))
    if not vids:
        return build_style_profile(default=True)

    profiles = []
    for v in vids:
        p = ffprobe_json(str(v))
        fmt = p.get("format", {})
        dur = float(fmt.get("duration", 0))
        vs = next((s for s in p.get("streams", []) if s.get("codec_type") == "video"), {})
        w = vs.get("width", 0)
        h = vs.get("height", 0)
        fps = eval_fps(vs.get("r_frame_rate"))
        profiles.append({
            "file": v.name,
            "duration": dur,
            "width": w,
            "height": h,
            "aspect": round(w / h, 3) if h else 0,
            "fps": fps,
        })

    # tổng hợp
    durs = [x["duration"] for x in profiles if x["duration"] > 0]
    fps_list = [x["fps"] for x in profiles if x["fps"] > 0]
    aspects = [x["aspect"] for x in profiles if x["aspect"] > 0]
    vertical_ratio = sum(1 for a in aspects if a < 1) / len(aspects) if aspects else 1.0

    style = {
        "name": f"style_from_{len(vids)}_refs",
        "avg_duration": round(sum(durs) / len(durs), 1) if durs else 0,
        "vertical": vertical_ratio > 0.5,
        "avg_fps": round(sum(fps_list) / len(fps_list), 2) if fps_list else 30,
        "target_aspect": min(aspects, key=lambda a: abs(a - (0.5625 if vertical_ratio > 0.5 else 1.7778))) if aspects else 0.5625,
        "refs": profiles,
    }
    out = work_dir / "style_profile.json"
    out.write_text(json.dumps(style, ensure_ascii=False, indent=2), encoding="utf-8")
    return style


def build_style_profile(default: bool = False) -> dict:
    return {
        "name": "default_tiktok_syle",
        "avg_duration": 45,
        "vertical": True,
        "avg_fps": 30,
        "target_aspect": 0.5625,
        "refs": [],
    }


def eval_fps(rate_str):
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
