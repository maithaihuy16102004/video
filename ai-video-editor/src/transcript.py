"""Transcript: dùng Whisper (nếu có) hoặc nhận file .srt/.vtt có sẵn, trả về đường dẫn file .srt chuẩn."""

import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WHISPER_BIN = shutil.which("whisper")


def _whisper_available() -> bool:
    if WHISPER_BIN:
        return True
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        return False


def vtt_to_srt(vtt_path: Path) -> Path:
    """Chuyển webvtt sang srt đơn giản (bỏ dấu thời gian phụ)."""
    srt_path = vtt_path.with_suffix(".srt")
    lines = vtt_path.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    idx = 0
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" in line:
            idx += 1
            # chuẩn hóa dấu '.' -> ','
            t = line.replace(".", ",")
            # lấy 2 dòng text sau đó
            text = []
            i += 1
            while i < len(lines) and lines[i].strip() != "":
                text.append(lines[i].strip())
                i += 1
            out.append(f"{idx}")
            out.append(t)
            out.append("\n".join(text))
            out.append("")
        i += 1
    srt_path.write_text("\n".join(out), encoding="utf-8", errors="replace")
    return srt_path


def transcribe_or_load(video_path: str, srt_provided, work_dir: Path) -> Path:
    """Trả về Path tới file .srt."""
    if srt_provided:
        p = Path(srt_provided)
        if p.suffix.lower() == ".vtt":
            return vtt_to_srt(p)
        if p.suffix.lower() == ".srt":
            return p
        return p

    # thử whisper
    if _whisper_available():
        out_srt = work_dir / "transcript.srt"
        print("[avi-editor] đang chạy Whisper (lần đầu sẽ tải model, có thể mất vài phút)...")
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(video_path, language="vi")
            # ghi srt
            segments = result["segments"]
            srt_lines = []
            for i, seg in enumerate(segments, 1):
                s = _ts(seg["start"])
                e = _ts(seg["end"])
                srt_lines += [str(i), f"{s} --> {e}", seg["text"].strip(), ""]
            out_srt.write_text("\n".join(srt_lines), encoding="utf-8", errors="replace")
            return out_srt
        except Exception as ex:
            print(f"[avi-editor] whisper lỗi: {ex}")
    else:
        print("[avi-editor] chưa cài Whisper. Dùng --srt để cung cấp phụ đề có sẵn.")
    return Path()


def _ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    ms = int((s - int(s)) * 1000)
    return f"{h:02d}:{m:02d}:{int(s):02d},{ms:03d}"
