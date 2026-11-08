"""Layer 1 — Chunking & Map-Reduce cho dữ liệu log lớn.

Thay vì ném toàn bộ log (hàng chục nghìn dòng) vào LLM, chia nhỏ thành các
đoạn (chunk) theo thời gian hoặc tiến trình, tóm tắt từng đoạn (Map), rồi gom
tất cả tóm tắt lại (Reduce) thành báo cáo cuối.

Hai chiến lược chunk:
  - by_time:    theo khung giờ (VD mỗi 1 giờ = 1 chunk)
  - by_process: theo tiến trình (cắt video / whisper / render...)
  - by_lines:   theo số dòng cố định
"""

import re


def chunk_by_lines(text: str, max_lines: int = 200) -> list[str]:
    """Chia theo số dòng tối đa mỗi chunk."""
    lines = text.split("\n")
    chunks = []
    for i in range(0, len(lines), max_lines):
        chunks.append("\n".join(lines[i:i + max_lines]))
    return chunks


def chunk_by_time(text: str, hours: int = 1) -> list[str]:
    """Chia theo khung giờ (dựa trên timestamp HH:MM:SS trong mỗi dòng)."""
    ts_re = re.compile(r"(\d{2}):(\d{2}):(\d{2})")
    lines = text.split("\n")
    chunks = []
    cur = []
    cur_bucket = None
    for line in lines:
        m = ts_re.search(line)
        if m:
            hh = int(m.group(1))
            bucket = hh // hours  # nhóm theo khối `hours` giờ
            if cur_bucket is None:
                cur_bucket = bucket
            elif bucket != cur_bucket:
                chunks.append("\n".join(cur))
                cur = []
                cur_bucket = bucket
        cur.append(line)
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def chunk_by_process(text: str, process_markers=None) -> list[str]:
    """Chia theo tiến trình (dòng bắt đầu 1 quá trình mới)."""
    markers = process_markers or [
        r"Starting", r"Started", r"Running", r"Processing",
        r"Starting FFmpeg", r"Starting Whisper", r"Render", r"Transcribe",
    ]
    lines = text.split("\n")
    chunks = []
    cur = []
    for line in lines:
        if any(re.search(m, line, re.IGNORECASE) for m in markers) and cur:
            chunks.append("\n".join(cur))
            cur = []
        cur.append(line)
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def smart_chunk(text: str, strategy: str = "auto", max_chunk_lines: int = 200,
                hours: int = 1) -> list[str]:
    """Tự chọn chiến lược chia chunk phù hợp.

    - Strategy tường minh (by_lines/by_time/by_process): luôn được tôn trọng.
    - Strategy "auto": nếu log nhỏ (<= max_chunk_lines) thì trả 1 chunk duy nhất.
    """
    lines = text.split("\n")

    if strategy == "by_lines":
        return chunk_by_lines(text, max_chunk_lines)
    if strategy == "by_time":
        return chunk_by_time(text, hours)
    if strategy == "by_process":
        return chunk_by_process(text)

    # auto
    if len(lines) <= max_chunk_lines:
        return [text]  # nhỏ, không cần chia

    # auto: ưu tiên theo tiến trình nếu có marker, ngược lại theo dòng
    proc = chunk_by_process(text)
    if len(proc) > 1 and all(len(c.split("\n")) < max_chunk_lines * 3 for c in proc):
        return proc
    return chunk_by_lines(text, max_chunk_lines)


def chunk_stats(chunks: list[str]) -> dict:
    return {
        "num_chunks": len(chunks),
        "lines_per_chunk": [len(c.split("\n")) for c in chunks],
        "chars_per_chunk": [len(c) for c in chunks],
    }
