"""CLI dịch phụ đề SRT/VTT -> tiếng Việt (tái tạo "Tool dịch phụ đề SRT VIP").

Dùng:
    # Dịch file SRT sang tiếng Việt
    python srt.py video.srt --src en --dst vi -o output/video_vi.srt

    # Dịch + sinh luôn file giọng đọc từ phụ đề đã dịch
    python srt.py video.srt --voice hoaimy --tts-out output/voiceover.mp3
"""

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(ROOT / "tts" / "src"))

from srt_translate import (  # noqa: E402
    parse_srt, write_srt, translate_cues, make_tts_voiceover,
)


def main():
    ap = argparse.ArgumentParser(description="Dịch phụ đề SRT/VTT")
    ap.add_argument("input", help="file .srt/.vtt đầu vào")
    ap.add_argument("--src", default="en", help="ngôn ngữ nguồn (mặc định en)")
    ap.add_argument("--dst", default="vi", help="ngôn ngữ đích (mặc định vi)")
    ap.add_argument("--batch", type=int, default=15, help="số cue mỗi lần dịch")
    ap.add_argument("--no-llm", action="store_true", help="không dịch, chỉ parse")
    ap.add_argument("--voice", help="giọng đọc cho voiceover (hoaimy/namminh)")
    ap.add_argument("--tts-out", help="file mp3 voiceover xuất ra")
    ap.add_argument("-o", "--output", help="file .srt đã dịch")
    args = ap.parse_args()

    src_path = Path(args.input)
    if not src_path.exists():
        print(f"LỖI: không tìm thấy file: {src_path}")
        sys.exit(1)

    cues = parse_srt(src_path)
    print(f"[srt] đọc {len(cues)} cue từ {src_path.name}")
    if not cues:
        print("LỖI: không parse được cue nào (file có đúng định dạng SRT/VTT?)")
        sys.exit(1)

    translated = translate_cues(cues, src=args.src, dst=args.dst,
                                batch_size=args.batch,
                                use_llm=not args.no_llm)

    out = args.output or str(src_path.with_name(f"{src_path.stem}.{args.dst}.srt"))
    if not Path(out).is_absolute():
        out = str(BASE / out)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    write_srt(translated, out)
    print(f"[srt] đã ghi -> {out}")

    if args.voice:
        tts_out = args.tts_out or str(Path(out).with_suffix(".voice.mp3"))
        if not Path(tts_out).is_absolute():
            tts_out = str(BASE / tts_out)
        Path(tts_out).parent.mkdir(parents=True, exist_ok=True)
        p = make_tts_voiceover(translated, tts_out, voice=args.voice,
                               tgt=args.dst)
        print(f"[srt] voiceover -> {p}")


if __name__ == "__main__":
    main()
