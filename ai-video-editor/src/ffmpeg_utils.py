"""FFmpeg helpers: probe, phát hiện & cắt khoảng lặng, ghép đoạn, chuẩn hóa âm lượng, trộn nhạc."""

import json
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=15)
        return True
    except Exception:
        return False


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def ffprobe_json(path: str) -> dict:
    out = _run(["ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", path])
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe lỗi: {out.stderr}")
    return json.loads(out.stdout)


def detect_silence(path: str, thresh_db: float = -40.0, min_dur: float = 0.6):
    """Trả về list (start, end) giây của các khoảng lặng."""
    cmd = ["ffmpeg", "-i", path, "-af",
           f"silencedetect=noise={thresh_db}dB:d={min_dur}",
           "-f", "null", "-"]
    out = _run(cmd)
    # ffmpeg in log qua stderr
    text = out.stderr
    starts, ends = [], []
    for line in text.splitlines():
        if "silence_start" in line:
            starts.append(float(line.split("silence_start:")[1].split()[0]))
        elif "silence_end" in line and "silence_duration" in line:
            ends.append(float(line.split("silence_end:")[1].split()[0]))
    n = min(len(starts), len(ends))
    return [(starts[i], ends[i]) for i in range(n)]


def cut_out_silence(path: str, silences, out_path: str, pad: float = 0.15):
    """Cắt các khoảng lặng khỏi video: giữ các đoạn KHÔNG lặng rồi ghép lại."""
    segments = []
    prev_end = 0.0
    for s, e in silences:
        # giữ đoạn từ prev_end tới s (giữa các khoảng lặng)
        seg_start = prev_end
        seg_end = s
        if seg_end - seg_start > 0.05:
            segments.append((seg_start, seg_end))
        prev_end = e
    # đoạn cuối
    # (độ dài tổng cần biết; dùng ffprobe)
    total = float(ffprobe_json(path)["format"]["duration"])
    if total - prev_end > 0.05:
        segments.append((prev_end, total))

    if not segments:
        # không còn gì -> copy gốc
        import shutil
        shutil.copy2(path, out_path)
        return

    concat_segments(path, segments, out_path)


def concat_segments(path: str, segments, out_path: str):
    """Ghép các đoạn (start,end) của cùng 1 file thành video mới (re-encode, giữ A/V sync)."""
    filters = []
    inputs = []
    for i, (s, e) in enumerate(segments):
        dur = e - s
        inputs += ["-ss", f"{s:.3f}", "-t", f"{dur:.3f}", "-i", path]
        filters.append(f"[{i}:v:0][{i}:a:0]")
    vconcat = "".join(f"[{i}:v:0]" for i in range(len(segments)))
    aconcat = "".join(f"[{i}:a:0]" for i in range(len(segments)))
    filter_complex = f"{vconcat}concat=n={len(segments)}:v=1:a=0[v];{aconcat}concat=n={len(segments)}:v=0:a=1[a]"
    cmd = ["ffmpeg", "-y"] + inputs + \
        ["-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "fast", "-crf", "20",
         "-c:a", "aac", "-b:a", "128k", out_path]
    _run(cmd)


def loudness_normalize(path: str, out_path: str, target_lufs: float = -16.0):
    cmd = ["ffmpeg", "-y", "-i", path, "-af",
           f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
           "-c:v", "copy", "-c:a", "aac", out_path]
    _run(cmd)
    return out_path


def mix_audio(video_path: str, music_path: str, out_path: str, volume: float = 0.18):
    """Trộn nhạc nền (volume thấp) vào track audio video."""
    cmd = ["ffmpeg", "-y", "-i", video_path, "-i", music_path,
           "-filter_complex",
           f"[1:a]volume={volume},afade=t=in:d=1,afade=t=out:st=1:d=1[bg];"
           f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
           "-map", "0:v", "-map", "[a]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", out_path]
    _run(cmd)
    return out_path
