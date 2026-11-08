"""Layer 3 — Context Caching: cấu trúc prompt để tối đa hoá cache hit.

Quy tắc vàng từ DeepSeek/Anthropic: cache chỉ HIT khi phần đầu (prefix) của
input khớp chính xác từ token 0 trở đi. Vì vậy:

  1. Đặt phần TĨNH (system prompt + hướng dẫn + template báo cáo) ở ĐẦU.
  2. Đặt phần ĐỘNG (dữ liệu log/metadata của từng lần) ở CUỐI.
  3. Giữ phần tĩnh byte-identical qua các lần gọi — không đổi từ ngữ/format.

Kết quả: phần tĩnh được cache → tính giá rẻ (≈1/10 input thường).
"""

import hashlib


def build_report_system_prompt(project_name: str = "AI Video Editor",
                               template_md: str = None) -> str:
    """System prompt TĨNH (giữ nguyên qua mọi lần gọi để cache hit)."""
    base = (
        "You are a professional daily report assistant for a video processing "
        "pipeline. You receive OPTIMIZED logs (progress lines already removed) "
        "and produce a concise, well-structured Markdown report.\n\n"
        f"Project: {project_name}\n\n"
        "Rules:\n"
        "- Group events by process (cut video, whisper subtitles, render graphics).\n"
        "- Report start/end times, output files, and any errors/warnings.\n"
        "- Use bullet points. Keep it short — no fluff.\n"
    )
    if template_md:
        base += "\nReport template (follow this structure):\n" + template_md
    return base


def build_messages(system_prompt: str, dynamic_content: str,
                   task_instruction: str = None) -> list[dict]:
    """Tạo danh sách messages với phần tĩnh trước, động sau.

    system_prompt + task_instruction = TĨNH (cache-friendly).
    dynamic_content = ĐỘNG (đặt cuối cùng).
    """
    user_static = (task_instruction or
                   "Here is today's optimized log. Summarize it into a "
                   "clean Markdown daily report.") + "\n\n"
    user_msg = user_static + dynamic_content
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]


def fingerprint(text: str) -> str:
    """Băm phần tĩnh để so sánh có giữ nguyên (cache hit) hay không."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class CacheTracker:
    """Theo dõi prefix tĩnh giữa các lần gọi để phát hiện thay đổi (miss cache)."""

    def __init__(self):
        self._last_fp = None

    def check(self, static_text: str) -> bool:
        """Trả True nếu prefix tĩnh KHÔNG đổi (giữ nguyên cache) so với lần trước."""
        fp = fingerprint(static_text)
        unchanged = (self._last_fp is not None and self._last_fp == fp)
        self._last_fp = fp
        return unchanged
