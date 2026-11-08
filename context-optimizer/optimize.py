"""context-optimizer — CLI tối ưu token & sinh báo cáo daily từ log.

4 chế độ:
  filter    : chỉ lọc log (Layer 2) -> ghi file tinh gọn
  metadata  : trích metadata video bằng ffprobe (Layer 4) -> JSON
  report    : filter -> chunk -> map-reduce -> báo cáo Markdown (cần API key)
  stats     : ước lượng token rác đã cắt

Ví dụ:
  python optimize.py filter    samples/ffmpeg.log -o output/cleaned.log
  python optimize.py metadata  video_goc.mp4 -o output/meta.json
  python optimize.py report    samples/ffmpeg.log -o output/report.md
"""

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "src"))

from filter import filter_log, filter_log_file, estimate_tokens  # noqa: E402
from metadata import extract_metadata, extract_dir_metadata, metadata_to_json  # noqa: E402
from chunker import smart_chunk, chunk_stats  # noqa: E402


def cmd_filter(args):
    raw = Path(args.input).read_text(encoding="utf-8", errors="replace")
    cleaned = filter_log(raw)
    out = args.output or (str(Path(args.input)) + ".clean.log")
    Path(out).write_text(cleaned, encoding="utf-8")
    before_tok = estimate_tokens(raw)
    after_tok = estimate_tokens(cleaned)
    print(f"Input  : {args.input} ({len(raw.splitlines())} dòng, ~{before_tok} tokens)")
    print(f"Output : {out} ({len(cleaned.splitlines())} dòng, ~{after_tok} tokens)")
    print(f"Đã cắt : {round((1 - after_tok / max(1, before_tok)) * 100, 1)}% token rác")


def cmd_metadata(args):
    p = Path(args.input)
    if p.is_dir():
        metas = extract_dir_metadata(str(p))
    else:
        metas = extract_metadata(str(p))
    s = metadata_to_json(metas, args.output)
    print(s)


def cmd_stats(args):
    raw = Path(args.input).read_text(encoding="utf-8", errors="replace")
    cleaned = filter_log(raw)
    chunks = smart_chunk(cleaned, strategy=args.chunk)
    print(f"Log thô      : {len(raw.splitlines())} dòng, ~{estimate_tokens(raw)} tokens")
    print(f"Đã lọc       : {len(cleaned.splitlines())} dòng, ~{estimate_tokens(cleaned)} tokens")
    print(f"Số chunk     : {len(chunks)} (chiến lược: {args.chunk})")
    print(f"Giảm token   : {round((1 - estimate_tokens(cleaned)/max(1,estimate_tokens(raw)))*100,1)}%")


def cmd_report(args):
    from report import generate_daily_report
    from client import DeepSeekClient

    raw = Path(args.input).read_text(encoding="utf-8", errors="replace")
    client = DeepSeekClient(model=args.model)
    try:
        result = generate_daily_report(raw, client, project_name=args.project,
                                       chunk_strategy=args.chunk)
    except RuntimeError as e:
        print(f"\nLỖI: {e}")
        print("Hướng dẫn: đặt biến môi trường DEEPSEEK_API_KEY rồi chạy lại.\n"
              "  PowerShell:  $env:DEEPSEEK_API_KEY = \"sk-...\"\n"
              "  Bash:        export DEEPSEEK_API_KEY=\"sk-...\"")
        sys.exit(1)
    report = result["report"]
    out = args.output or "output/daily_report.md"
    Path(out).write_text(report, encoding="utf-8")

    print("\n" + "=" * 60)
    print("BÁO CÁO DAILY")
    print("=" * 60)
    print(report)
    print("=" * 60)
    stats = result["stats"]
    print(f"Log: {stats['raw_chars']} -> {stats['cleaned_chars']} ký tự "
          f"(giảm {stats['reduction_pct']}%)")
    cs = result["cache_summary"]
    print(f"Cache: hit {cs['hit_tokens']} tokens, miss {cs['miss_tokens']} "
          f"(tỉ lệ hit {cs['cache_hit_ratio']:.0%}), ước tính ${cs['estimated_cost_usd']}")
    print(f"Báo cáo đã ghi: {out}")


def main():
    ap = argparse.ArgumentParser(description="Context optimizer cho log video pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_f = sub.add_parser("filter", help="lọc log rác (Layer 2)")
    p_f.add_argument("input")
    p_f.add_argument("-o", "--output")

    p_m = sub.add_parser("metadata", help="trích metadata video (Layer 4)")
    p_m.add_argument("input", help="file media hoặc thư mục")
    p_m.add_argument("-o", "--output")

    p_s = sub.add_parser("stats", help="thống kê token rác")
    p_s.add_argument("input")
    p_s.add_argument("--chunk", default="auto")

    p_r = sub.add_parser("report", help="sinh báo cáo daily (cần DEEPSEEK_API_KEY)")
    p_r.add_argument("input")
    p_r.add_argument("-o", "--output")
    p_r.add_argument("--model", default="deepseek-chat")
    p_r.add_argument("--project", default="AI Video Editor")
    p_r.add_argument("--chunk", default="auto")

    args = ap.parse_args()
    if args.cmd == "filter":
        cmd_filter(args)
    elif args.cmd == "metadata":
        cmd_metadata(args)
    elif args.cmd == "stats":
        cmd_stats(args)
    elif args.cmd == "report":
        cmd_report(args)


if __name__ == "__main__":
    main()
