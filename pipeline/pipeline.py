"""Pipeline A-Z: chủ đề -> kịch bản -> giọng đọc -> video -> thumbnail.

Một lệnh chạy toàn bộ quy trình làm content (chủ đề → kịch bản → giọng đọc →
hình ảnh → edit → thumbnail), đúng quy trình h2dev.vn.

Nếu KHÔNG có API key LLM, pipeline vẫn chạy được bằng template + points tự soạn.

Dùng:
    # Có API key DeepSeek/Claude/OpenAI: tự sinh kịch bản
    set DEEPSEEK_API_KEY=sk-...
    python pipeline.py "kinh tế thị trường" --style education --voice hoaimy

    # Không có API: tự soạn points
    python pipeline.py --title "Kinh tế thị trường" \
        --points "Cung và cầu|Giá cả|Cạnh tranh|Vai trò nhà nước|Lạm phát" \
        --voice namminh

    # Chỉ dùng kịch bản sẵn
    python pipeline.py --script scripts/kich_ban.json --voice hoaimy
"""

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(ROOT / "charmotion" / "src"))
sys.path.insert(0, str(ROOT / "tts" / "src"))


def _log(msg):
    print(f"[pipeline] {msg}", flush=True)


def _safe_name(title):
    """Tên file an toàn cho cả Windows lẫn POSIX (giữ được tiếng Việt)."""
    bad = set('<>:"/\\|?*')
    keep = []
    for ch in title:
        if ch in bad or ord(ch) < 32:
            keep.append("_")
        elif ch.isspace():
            keep.append("_")
        else:
            keep.append(ch)
    name = "".join(keep).strip("._ ")
    while "__" in name:
        name = name.replace("__", "_")
    return (name or "video")[:60]


def run(topic=None, title=None, points=None, hook=None, style="education",
        voice="hoaimy", size="vertical", use_llm=True, out_dir=None,
        make_thumb=True, theme="gold", badge=None, script_path=None):
    from generator import generate
    from render import render_video
    from engines import get_engine
    from voices import resolve_voice

    out_dir = Path(out_dir) if out_dir else BASE / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 1. Kịch bản ----------
    if script_path:
        _log(f"dùng kịch bản có sẵn: {script_path}")
        script = json.loads(Path(script_path).read_text(encoding="utf-8"))
    else:
        topic = topic or title
        if not topic and not points:
            raise SystemExit("Cần topic hoặc points.")
        _log(f"sinh kịch bản cho chủ đề: {topic or title}")
        script = generate(topic or title, style=style, points=points,
                          hook=hook, use_llm=use_llm)

    title = script.get("title") or title or topic
    points = script.get("points") or points or []
    hook = script.get("hook") or hook
    narration = script.get("narration") or ". ".join(
        [p for p in [hook, title, *points] if p])
    script["width"], script["height"] = {
        "vertical": (1080, 1920), "square": (1080, 1080),
        "horizontal": (1920, 1080),
    }[size]
    script.setdefault("fps", 30)

    safe = _safe_name(title)

    script_out = out_dir / f"{safe}_script.json"
    script_out.write_text(json.dumps(script, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    _log(f"kịch bản -> {script_out}  ({len(script['scenes'])} cảnh)")

    # ---------- 2. Giọng đọc ----------
    voice_path = None
    skip_voice = False
    engine = get_engine("edge-tts")
    if not engine.available():
        _log("edge-tts chưa cài (pip install edge-tts) -> bỏ qua giọng đọc")
        skip_voice = True
    if not skip_voice:
        voice_path = out_dir / f"{safe}_voice.mp3"
        try:
            _log(f"sinh giọng đọc ({resolve_voice(voice)})...")
            engine.synthesize(narration, resolve_voice(voice), str(voice_path))
            _log(f"giọng đọc -> {voice_path}")
        except Exception as e:  # noqa: BLE001
            _log(f"lỗi TTS ({e}) -> render không giọng đọc")
            voice_path = None

    # ---------- 3. Video ----------
    video_out = out_dir / f"{safe}.mp4"
    _log("render video...")
    render_video(script, str(video_out),
                 audio_path=str(voice_path) if voice_path else None)
    _log(f"video -> {video_out}")

    # ---------- 4. Thumbnail ----------
    thumb_out = None
    if make_thumb:
        from thumbnail import make_thumbnail
        thumb_out = out_dir / f"{safe}_thumb.jpg"
        make_thumbnail(title, subtitle=(hook or (points[0] if points else None)),
                       badge=badge or "VIDEO MỚI", theme=theme,
                       size="horizontal" if size != "vertical" else "vertical",
                       out_path=str(thumb_out))
        _log(f"thumbnail -> {thumb_out}")

    # ---------- 5. Report ----------
    report = {
        "topic": topic, "title": title, "hook": hook, "points": points,
        "narration": narration, "style": style, "voice": voice,
        "size": size, "scenes": len(script["scenes"]),
        "files": {
            "script": str(script_out),
            "voice": str(voice_path) if voice_path else None,
            "video": str(video_out),
            "thumbnail": str(thumb_out) if thumb_out else None,
        },
    }
    report_out = out_dir / f"{safe}_pipeline.json"
    report_out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    print()
    print("=" * 64)
    print("HOÀN TẤT PIPELINE")
    print(f"  kịch bản  : {script_out}")
    print(f"  giọng đọc : {voice_path or '(không có)'}")
    print(f"  video     : {video_out}")
    print(f"  thumbnail : {thumb_out or '(không có)'}")
    print(f"  report    : {report_out}")
    print("=" * 64)
    return report


def main():
    ap = argparse.ArgumentParser(description="Pipeline A-Z làm video content")
    ap.add_argument("topic", nargs="?", help="chủ đề video (dùng với LLM)")
    ap.add_argument("--title", help="tiêu đề (khi không dùng LLM)")
    ap.add_argument("--points", help="các ý chính, phân cách bằng |")
    ap.add_argument("--hook", help="câu hook mở đầu")
    ap.add_argument("--style", default="education",
                    choices=["tech", "education", "motivation"])
    ap.add_argument("--voice", default="hoaimy",
                    help="giọng: hoaimy (nữ) / namminh (nam)")
    ap.add_argument("--size", default="vertical",
                    choices=["vertical", "square", "horizontal"])
    ap.add_argument("--script", help="dùng kịch bản JSON có sẵn")
    ap.add_argument("--no-llm", action="store_true",
                    help="không gọi LLM, chỉ dùng template + points")
    ap.add_argument("--theme", default="gold",
                    choices=["dark", "gold", "red", "blue", "green"])
    ap.add_argument("--badge", help="nhãn trên thumbnail")
    ap.add_argument("--no-thumb", action="store_true", help="không tạo thumbnail")
    ap.add_argument("--out-dir", help="thư mục xuất (mặc định pipeline/output)")
    args = ap.parse_args()

    pts = [p.strip() for p in args.points.split("|")] if args.points else None
    run(topic=args.topic, title=args.title, points=pts, hook=args.hook,
        style=args.style, voice=args.voice, size=args.size,
        use_llm=not args.no_llm, out_dir=args.out_dir,
        make_thumb=not args.no_thumb, theme=args.theme, badge=args.badge,
        script_path=args.script)


if __name__ == "__main__":
    main()
