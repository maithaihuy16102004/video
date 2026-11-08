"""Sinh kịch bản video từ chủ đề (topic) — dùng LLM (deepseek/claude/openai)
hoặc template có sẵn khi không có API key.

Kết quả là dict kịch bản tương thích charmotion, có thêm trường:
  - title, hook, points   : metadata
  - narration             : văn bản đầy đủ để đọc thành giọng (TTS)
  - scenes                : danh sách cảnh charmotion
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# Gọi LLM (OpenAI-compatible + Anthropic) bằng urllib, không cần thư viện ngoài
# --------------------------------------------------------------------------

def _post_json(url, payload, headers, timeout=90):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _call_deepseek(prompt, key=None, model=None, base_url=None):
    key = key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None
    base = base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    url = base.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Bạn là biên kịch video ngắn. "
                                          "Chỉ trả lời JSON thuần, không giải thích."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = _post_json(url, payload, headers)
    return resp["choices"][0]["message"]["content"]


def _call_claude(prompt, key=None, model=None):
    key = key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = model or os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 2000,
        "system": "Bạn là biên kịch video ngắn. Chỉ trả về JSON thuần.",
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    resp = _post_json(url, payload, headers)
    return resp["content"][0]["text"]


def _call_openai(prompt, key=None, model=None, base_url=None):
    key = key or os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    base = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    url = base.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Bạn là biên kịch video ngắn. "
                                          "Chỉ trả lời JSON thuần."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = _post_json(url, payload, headers)
    return resp["choices"][0]["message"]["content"]


def _llm_script_json(topic, style="education", num_points=5):
    """Thử các provider theo thứ tự ưu tiên: deepseek -> claude -> openai."""
    prompt = (
        f"Viết kịch bản video ngắn (dọc, TikTok/Shorts) về chủ đề: \"{topic}\".\n"
        f"Phong cách: {style}. Trả về JSON đúng cấu trúc sau (không thêm gì ngoài JSON):\n"
        "{\n"
        "  \"title\": \"tiêu đề hấp dẫn, ngắn gọn\",\n"
        "  \"hook\": \"câu mở đầu gây tò mò\",\n"
        "  \"points\": [\"ý 1 ngắn\", \"ý 2 ngắn\", ...],\n"
        "  \"narration\": \"toàn bộ lời đọc (văn xuôi, tự nhiên, có mở-đóng)\"\n"
        "}\n"
        f"Yêu cầu: đúng {num_points} ý (points), tiếng Việt có dấu, "
        "narration dài ~90-140 từ để đọc thành giọng nói."
    )
    raw = _call_deepseek(prompt) or _call_claude(prompt) or _call_openai(prompt)
    if not raw:
        return None
    # tách JSON thuần (phòng LLM bọc thêm markdown)
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    return json.loads(s.strip())


# --------------------------------------------------------------------------
# Template fallback (không cần API) — dùng lại template charmotion
# --------------------------------------------------------------------------

_TEMPLATE_HINTS = {
    "tech": "chủ đề công nghệ/lập trình",
    "education": "chủ đề giáo dục/kiến thức",
    "motivation": "chủ đề động lực/cảm hứng",
}


def generate(topic, style="education", points=None, hook=None, use_llm=True,
             num_points=5) -> dict:
    """Sinh kịch bản từ topic.

    Trả về dict: {title, hook, points, narration, scenes, width/height/fps}.
    """
    # 1) thử LLM
    data = None
    if use_llm:
        try:
            data = _llm_script_json(topic, style=style, num_points=num_points)
        except Exception as e:  # noqa: BLE001
            print(f"[generator] LLM lỗi (chuyển sang template): {e}")

    if data:
        title = data.get("title", topic)
        hook = data.get("hook")
        pts = data.get("points", [])
        narration = data.get("narration")
    else:
        title = topic
        pts = list(points) if points else _default_points(topic)
        narration = None

    if not pts:
        pts = _default_points(topic)

    # 2) dựng scenes bằng template charmotion
    from templates import TEMPLATES
    build = TEMPLATES.get(style) or TEMPLATES["education"]
    script = build(title, pts, hook=hook)

    # 3) narration: dùng của LLM, hoặc tự ghép từ title+hook+points
    if not narration:
        parts = [hook, title, *pts]
        narration = ". ".join(p for p in parts if p) + "."

    script["title"] = title
    script["hook"] = hook
    script["points"] = pts
    script["narration"] = narration
    return script


def _default_points(topic):
    """Điểm mặc định khi không có LLM cũng không truyền points."""
    return [
        f"{topic} là gì?",
        "Tại sao nó quan trọng?",
        "3 ví dụ thực tế",
        "Sai lầm thường gặp",
        "Cách áp dụng ngay",
    ]
