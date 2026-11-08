"""Voice/TTS CLI — giọng đọc tiếng Việt + voice cloning cho Local Workspace.

Cách dùng nhanh:
    # Đọc 1 câu thành giọng nữ tiếng Việt
    python tts.py "Xin chào, đây là video hôm nay" -o output/hello.mp3

    # Đọc giọng nam, nhanh hơn 10%
    python tts.py "Báo cáo ngày hôm nay..." --voice namminh --rate +10% -o report.mp3

    # Đọc cả file kịch bản (mỗi dòng là 1 đoạn)
    python tts.py --file kichban.txt --voice hoaimy -o output/giongdoc.mp3

    # Liệt kê các giọng tiếng Việt có sẵn (cần mạng)
    python tts.py --list-voices

    # Voice cloning: nhân bản giọng từ file mẫu
    python tts.py "Nội dung muốn đọc bằng giọng clone" --clone sample.wav -o clone.mp3
"""

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "src"))

from engines import get_engine  # noqa: E402
from voices import VI_VOICES, VI_ALIASES, describe, list_vi_voices_async, resolve_voice  # noqa: E402


def _load_text(args) -> str:
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"LỖI: không tìm thấy file: {p}")
            sys.exit(1)
        return p.read_text(encoding="utf-8").strip()
    if args.text:
        return args.text
    print("Cần nhập văn bản (đối số) hoặc --file. Xem --help.")
    sys.exit(1)


def cmd_list_voices():
    print("Các giọng tiếng Việt (preset):")
    for key, (vid, gender, desc) in VI_VOICES.items():
        print(f"  {key:10s} -> {vid:24s} ({gender}) — {desc}")
    for alias, target in VI_ALIASES.items():
        print(f"  (alias) {alias} -> {target}")
    print()
    print("Đang truy vấn danh sách giọng đầy đủ từ edge-tts...")
    try:
        voices = list_vi_voices_async()
        if not voices:
            print("  (không tìm thấy giọng tiếng Việt nào — kiểm tra kết nối mạng)")
            return
        for v in voices:
            print(f"  {v['id']:24s} {v['gender']:10s} {v['locale']}")
    except Exception as e:  # noqa: BLE001
        print(f"  Lỗi khi truy vấn (có thể chưa cài edge-tts hoặc mất mạng): {e}")


def cmd_speak(args):
    # --clone luôn dùng engine XTTS v2 (voice cloning), trừ khi user chỉ định rõ
    if args.clone and args.engine == "edge-tts":
        args.engine = "xtts"
    engine = get_engine(args.engine)

    if not engine.available():
        print(f"LỖI: engine '{engine.name}' chưa cài đặt.")
        if engine.name == "xtts":
            print("      Voice cloning cần cài: pip install coqui-tts")
        else:
            print(f"      Cài bằng: pip install edge-tts")
        sys.exit(1)

    text = _load_text(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    voice = resolve_voice(args.voice or "hoaimy")
    print(f"[tts] engine={engine.name}  voice={voice} ({describe(args.voice or 'hoaimy')})")
    print(f"[tts] text: {text[:80]}{'...' if len(text) > 80 else ''}")

    kwargs = {"rate": args.rate, "pitch": args.pitch, "volume": args.volume}
    if args.clone:
        sample = Path(args.clone)
        if not sample.exists():
            print(f"LỖI: không tìm thấy file giọng mẫu: {sample}")
            sys.exit(1)
        kwargs["sample_wav"] = str(sample)

    engine.synthesize(text, voice, str(out), **kwargs)
    size = out.stat().st_size if out.exists() else 0
    print(f"[tts] xong -> {out}  ({size} bytes)")


def main():
    ap = argparse.ArgumentParser(
        description="Voice/TTS tiếng Việt + voice cloning cho Local Workspace")
    ap.add_argument("text", nargs="?", help="văn bản cần đọc (hoặc dùng --file)")
    ap.add_argument("--file", help="file kịch bản .txt (mỗi dòng = 1 đoạn)")
    ap.add_argument("--voice", default="hoaimy",
                    help="preset giọng (hoaimy/namminh/nu/nam) hoặc voice id")
    ap.add_argument("--engine", default="edge-tts",
                    help="engine: edge-tts (mặc định) | melo | xtts")
    ap.add_argument("--clone", help="file giọng mẫu .wav để nhân bản giọng (XTTS)")
    ap.add_argument("--rate", help="tốc độ, vd +10%% hoặc -5%%")
    ap.add_argument("--pitch", help="cao độ, vd +5Hz")
    ap.add_argument("--volume", help="âm lượng, vd +0%%")
    ap.add_argument("--list-voices", action="store_true",
                    help="liệt kê giọng tiếng Việt rồi thoát")
    ap.add_argument("-o", "--output", default="output/voice.mp3",
                    help="đường dẫn file âm thanh xuất (mặc định output/voice.mp3)")
    args = ap.parse_args()

    if args.list_voices:
        cmd_list_voices()
        return
    cmd_speak(args)


if __name__ == "__main__":
    main()
