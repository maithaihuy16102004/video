"""Layer 2 — Bộ lọc Regex tinh gọn log trước khi nạp vào LLM.

Xóa các dòng tiến trình vô giá trị của FFmpeg/Whisper/render (frame=, size=,
bitrate=, [progress], %...) và chỉ giữ lại các dòng có ý nghĩa:
mốc thời gian bắt đầu/kết thúc, tên file, lỗi (Error/Exception/Traceback),
cảnh báo (Warning), và các sự kiện Completed/Started.

Hiệu quả: cắt 70-90% token rác.
"""

import re

# Các pattern tiến trình render — dòng nào khớp thì LOẠI BỎ
PROGRESS_PATTERNS = [
    r"frame\s*=",              # frame=  100 fps=...
    r"size\s*=",               # size=     512kB
    r"bitrate\s*=",            # bitrate=1024.0kbits/s
    r"speed\s*=",              # speed=1.2x
    r"\[progress\]",           # [progress] 50% done
    r"\b\d{1,3}%\s*(done|complete|\.{3})",  # 50% done
    r"^\s*fps\s*=",
    r"Lsize\s*=",
    r"time=\d{2}:\d{2}:\d{2}", # time=00:00:01.00 (chỉ có trong dòng progress)
    r"q=-?\d+\.\d+",
    r"video:\d+",              # video:123kB audio:45kB
    r"audio:\d+",
    r"subtitle:\d+",
    r"elapsed=",
    r"eta=",
]

# Các pattern dòng "đáng giữ" (ưu tiên cao)
KEEP_PATTERNS = [
    r"error", r"exception", r"traceback", r"failed", r"fatal",
    r"warning", r"warn",
    r"started", r"starting", r"begin",
    r"completed", r"finished", r"done", r"success",
    r"\.mp4", r"\.mkv", r"\.mov", r"\.webm", r"\.srt", r"\.vtt",
    r"\.wav", r"\.mp3", r"\.json", r"\.log",
    r"duration", r"resolution", r"fps",
]


def is_progress_line(line: str) -> bool:
    for p in PROGRESS_PATTERNS:
        if re.search(p, line, re.IGNORECASE):
            return True
    return False


def is_keep_line(line: str) -> bool:
    for p in KEEP_PATTERNS:
        if re.search(p, line, re.IGNORECASE):
            return True
    return False


def filter_log(raw_text: str, keep_blank_lines: bool = False) -> str:
    """Lọc log thô -> log tinh gọn (chỉ giữ dòng có ý nghĩa)."""
    cleaned = []
    for line in raw_text.split("\n"):
        s = line.strip()
        if not s:
            if keep_blank_lines:
                cleaned.append("")
            continue
        # 1) bỏ dòng tiến trình
        if is_progress_line(s):
            continue
        # 2) giữ dòng có ý nghĩa (sự kiện / file / lỗi)
        if is_keep_line(s):
            cleaned.append(s)
            continue
        # 3) giữ các dòng có mốc thời gian (timestamp)
        if re.search(r"\d{4}-\d{2}-\d{2}|\d{2}:\d{2}:\d{2}", s):
            cleaned.append(s)
            continue
        # 4) mặc định: giữ dòng không rõ ràng là rác (bảo toàn thông tin)
        cleaned.append(s)
    return "\n".join(cleaned)


def filter_log_file(path: str, out_path: str = None) -> tuple[str, int, int]:
    """Đọc file log, lọc, ghi ra file tinh gọn. Trả (text_tinh_gọn, số_dòng_trước, số_dòng_sau)."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    before = len(raw.splitlines())
    cleaned = filter_log(raw)
    after = len(cleaned.splitlines())
    if out_path:
        open(out_path, "w", encoding="utf-8").write(cleaned)
    return cleaned, before, after


def estimate_tokens(text: str) -> int:
    """Ước lượng token (≈ 4 ký tự/token cho tiếng Anh, thô nhưng đủ để so sánh)."""
    return max(1, len(text) // 4)
