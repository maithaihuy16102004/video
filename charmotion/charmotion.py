"""charmotion - Character + Motion Graphics Studio

Tạo video dọc (TikTok/Shorts) hoặc ngang (YouTube) với nhân vật hoạt hình
+ motion graphics từ một kịch bản JSON đơn giản.

Dùng:
  python charmotion.py --template tech --title "..." --points "a|b|c" -o out.mp4
  python charmotion.py --script kichban.json -o out.mp4
"""

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "src"))

# TTS module (chị em trong workspace) để tự sinh giọng đọc
TTS_DIR = BASE.parent / "tts"
if TTS_DIR.exists():
    sys.path.insert(0, str(TTS_DIR / "src"))

from render import render_video  # noqa: E402
from templates import TEMPLATES  # noqa: E402


def _generate_voiceover(text, voice, out_dir) -> str:
    """Dùng module tts để sinh giọng đọc từ văn bản. Trả về đường dẫn audio."""
    try:
        from engines import get_engine
        from voices import resolve_voice
    except Exception as e:  # noqa: BLE001
        print(f"[charmotion] không import được module tts: {e}")
        print("            bỏ qua giọng đọc (dùng --audio thủ công nếu cần).")
        return None

    engine = get_engine("edge-tts")
    if not engine.available():
        print("[charmotion] edge-tts chưa cài -> bỏ qua giọng đọc.")
        print("            cài: pip install edge-tts")
        return None

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "voiceover.mp3"
    voice_id = resolve_voice(voice or "hoaimy")
    print(f"[charmotion] sinh giọng đọc (voice={voice_id})...")
    engine.synthesize(text, voice_id, str(out))
    print(f"[charmotion] giọng đọc -> {out}")
    return str(out)


def main():
    ap = argparse.ArgumentParser(description="Character + Motion Graphics Studio")
    ap.add_argument("--template", choices=list(TEMPLATES) + [None],
                    default=None, help="template chủ đề (tech/motivation/education)")
    ap.add_argument("--title", help="tiêu đề video")
    ap.add_argument("--points", help="các ý chính, phân cách bằng |")
    ap.add_argument("--hook", help="câu hook mở đầu (tùy chọn)")
    ap.add_argument("--script", help="file kịch bản JSON (thay cho template)")
    ap.add_argument("--audio", help="file nhạc/giọng nói nền (tùy chọn)")
    ap.add_argument("--voice", help="tự sinh giọng đọc TTS (hoaimy/namminh/... )")
    ap.add_argument("--size", choices=["vertical", "square", "horizontal"],
                    default="vertical", help="khổ video")
    ap.add_argument("-o", "--output", default="output/video.mp4",
                    help="đường dẫn xuất")
    args = ap.parse_args()

    narration_text = None
    if args.script:
        script = json.loads(Path(args.script).read_text(encoding="utf-8"))
        if args.voice:
            # gom text từ các scene để đọc (title/hook/points nếu có)
            parts = [script.get("title"), script.get("hook")]
            for sc in script.get("scenes", []):
                for t in sc.get("texts", []):
                    parts.append(t.get("text"))
            narration_text = ". ".join(p for p in parts if p)
    else:
        if not args.template or not args.title or not args.points:
            print("Cần --template, --title và --points (hoặc dùng --script).")
            sys.exit(1)
        points = [p.strip() for p in args.points.split("|") if p.strip()]
        build = TEMPLATES[args.template]
        script = build(args.title, points, hook=args.hook)
        if args.voice:
            narration_text = ". ".join(
                [p for p in [args.title, args.hook, *points] if p])

    # khổ video
    sizes = {"vertical": (1080, 1920), "square": (1080, 1080),
             "horizontal": (1920, 1080)}
    w, h = sizes[args.size]
    script["width"] = w
    script["height"] = h

    out = args.output
    if not Path(out).is_absolute():
        out = str(BASE / out)

    audio_path = args.audio
    if args.voice and narration_text:
        voice_dir = Path(out).parent / "voice"
        voice_path = _generate_voiceover(narration_text, args.voice, voice_dir)
        if voice_path:
            audio_path = voice_path

    render_video(script, out, audio_path=audio_path)
    print(f"\nXONG: {out}")


if __name__ == "__main__":
    main()
