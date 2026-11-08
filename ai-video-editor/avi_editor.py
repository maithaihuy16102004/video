"""AI Video Editor - tự động cắt khoảng lặng, thêm phụ đề, nhạc, motion graphic.

Pipeline theo đúng 4 bước trong video @mindang.com:
  1. Cấu trúc thư mục (video input / reference / output)
  2. Cài/bộ công cụ edit (FFmpeg cắt ghép, Whisper phụ đề, Pillow motion graphic)
  3. Phân tích phong cách từ video tham khảo -> style profile (tái dùng = "skill")
  4. Xử lý: cắt lặng -> phụ đề -> nhạc -> motion graphic -> storyboard duyệt -> xuất

Chạy riêng không cần Claude Code: dùng FFmpeg + Whisper + Pillow có sẵn trên máy.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from ffmpeg_utils import (  # noqa: E402
    ffmpeg_available, ffprobe_json, detect_silence, cut_out_silence,
    concat_segments, loudness_normalize,
)
from transcript import transcribe_or_load  # noqa: E402
from subtitles import render_burnt_subtitles  # noqa: E402
from style import analyze_style, build_style_profile  # noqa: E402
from storyboard import make_storyboard  # noqa: E402


def load_config(path: Path) -> dict:
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def resolve_video_path(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if p.is_absolute():
        return p
    # tìm trong BASE_DIR/video trước, rồi cwd
    candidates = [BASE_DIR / "video" / p.name, Path.cwd() / p.name, p]
    for c in candidates:
        if c.exists():
            return c
    return p


@dataclass
class EditResult:
    input: str
    output: str
    storyboard: str = ""
    style_profile: str = ""
    transcript: str = ""
    steps: list = field(default_factory=list)


def _log(msg):
    print(f"[avi-editor] {msg}", flush=True)


def run_pipeline(args):
    cfg = load_config(Path(args.config) if args.config else None)

    if not ffmpeg_available():
        print("LỖI: không tìm thấy FFmpeg trong PATH. Hãy cài FFmpeg (https://ffmpeg.org/).")
        sys.exit(1)

    in_path = resolve_video_path(args.input)
    if not in_path.exists():
        print(f"LỖI: không tìm thấy video đầu vào: {in_path}")
        sys.exit(1)
    _log(f"video gốc: {in_path}")

    out_dir = Path(args.out_dir) if args.out_dir else BASE_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="avi_"))
    result = EditResult(input=str(in_path), output="")

    # ---- Bước 1: probe ---- #
    probe = ffprobe_json(str(in_path))
    dur = float(probe.get("format", {}).get("duration", 0))
    _log(f"độ dài: {dur:.1f}s")

    # ---- Bước 2: phụ đề (transcript) ---- #
    transcript_path = None
    if args.srt:
        transcript_path = Path(args.srt)
    transcript = transcribe_or_load(str(in_path), transcript_path, work)
    result.transcript = str(transcript_path or transcript)

    # ---- Bước 3: phong cách (style) ---- #
    ref_dir = Path(args.ref_dir) if args.ref_dir else BASE_DIR / "reference"
    style_profile = None
    if ref_dir.exists() and any(ref_dir.iterdir()):
        _log("phân tích phong cách từ video tham khảo...")
        style_profile = analyze_style(ref_dir, work)
    elif cfg.get("style"):
        style_profile = cfg["style"]
        _log("dùng style profile từ config")
    else:
        style_profile = build_style_profile(default=True)
        _log("không có tham khảo, dùng style mặc định")
    result.style_profile = str(style_profile)

    # ---- Bước 4.1: cắt khoảng lặng ---- #
    silence_thresh = cfg.get("silence_thresh", args.silence_thresh)
    silence_dur = cfg.get("silence_dur", args.silence_dur)
    _log(f"phát hiện khoảng lặng (thresh={silence_thresh}dB, dur>={silence_dur}s)...")
    silences = detect_silence(str(in_path), silence_thresh, silence_dur)
    _log(f"tìm thấy {len(silences)} khoảng lặng")

    cut_path = str(in_path)
    if silences:
        cut_path = str(work / "cut.mp4")
        cut_out_silence(str(in_path), silences, cut_path,
                        pad=cfg.get("silence_pad", 0.15))
        _log(f"đã cắt lặng -> cut.mp4")

    # ---- Bước 4.2: motion graphics (Pillow) ---- #
    # tạo overlay title/watermark kiểu motion graphic đơn giản
    motion_path = None
    if args.motion:
        from motion import make_intro_overlay, prepend_intro
        title = cfg.get("intro_title", "AI EDITOR")
        motion_path = make_intro_overlay(str(in_path), work, title)
        _log(f"tạo motion graphic intro -> {motion_path}")
        # ghép intro vào đầu video
        cut_path = prepend_intro(cut_path, motion_path, out_path=str(work / "intro.mp4"),
                                 duration=cfg.get("intro_duration", 2.0))

    # ---- Bước 4.3: nhạc nền (tùy chọn) ---- #
    if args.music and Path(args.music).exists():
        from ffmpeg_utils import mix_audio
        cut_path = mix_audio(cut_path, args.music, str(work / "music.mp4"),
                             volume=cfg.get("music_volume", 0.18))
        _log(f"trộn nhạc nền -> music.mp4")

    # ---- Bước 4.4: burn phụ đề + căn giữa dọc (Vertical/VN) ---- #
    if transcript_path and transcript_path.exists():
        subtitled = str(work / "subtitled.mp4")
        render_burnt_subtitles(cut_path, str(transcript_path), subtitled,
                               cfg=cfg, vertical=args.vertical)
        _log("đã burn phụ đề")
        final_video = subtitled
    else:
        final_video = cut_path

    # ---- Bước 4.5: storyboard để duyệt ---- #
    storyboard_img = make_storyboard(final_video, work, cols=args.storyboard_cols,
                                     vertical=args.vertical)
    result.storyboard = storyboard_img
    _log(f"storyboard -> {storyboard_img}")

    # ---- Xuất ---- #
    out_name = Path(in_path).stem + "_edited.mp4"
    final_out = out_dir / out_name
    shutil.copy2(final_video, final_out)
    result.output = str(final_out)

    if storyboard_img:
        shutil.copy2(storyboard_img, out_dir / (Path(in_path).stem + "_storyboard.jpg"))

    # ghi report
    report = {
        "input": result.input,
        "output": result.output,
        "storyboard": result.storyboard,
        "silences_removed": len(silences),
        "transcript": result.transcript,
        "style": style_profile if isinstance(style_profile, dict) else None,
    }
    report_path = out_dir / (Path(in_path).stem + "_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    print()
    print("=" * 60)
    print("HOÀN TẤT")
    print(f"  video xuất   : {final_out}")
    print(f"  storyboard   : {out_dir / (Path(in_path).stem + '_storyboard.jpg')}")
    print(f"  report       : {report_path}")
    print("=" * 60)
    return result


def main():
    ap = argparse.ArgumentParser(description="AI Video Editor (autonomous edit pipeline)")
    ap.add_argument("input", help="đường dẫn video gốc")
    ap.add_argument("--config", help="JSON config (đè mặc định)")
    ap.add_argument("--srt", help="file phụ đề .srt/.vtt có sẵn (bỏ qua Whisper)")
    ap.add_argument("--ref-dir", help="thư mục video tham khảo để học phong cách")
    ap.add_argument("--music", help="file nhạc nền (mp3/wav)")
    ap.add_argument("--motion", action="store_true", help="bật motion graphic intro")
    ap.add_argument("--vertical", action="store_true", default=True, help="video dọc (mặc định)")
    ap.add_argument("--silence-thresh", type=float, default=-40.0, help="ngưỡng lặng dB (mặc định -40)")
    ap.add_argument("--silence-dur", type=float, default=0.6, help="độ dài lặng tối thiểu giây")
    ap.add_argument("--storyboard-cols", type=int, default=4, help="số cột storyboard")
    ap.add_argument("--out-dir", help="thư mục xuất (mặc định ./output)")
    args = ap.parse_args()

    run_pipeline(args)


if __name__ == "__main__":
    main()
