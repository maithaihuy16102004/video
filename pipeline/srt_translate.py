"""Dịch phụ đề SRT/VTT — hỗ trợ dịch qua LLM hoặc qua file kịch bản có sẵn.

Chức năng chính (lấy ý tưởng từ "Tool dịch phụ đề SRT VIP" của h2dev):
  - Đọc .srt / .vtt -> danh sách cue (index, start, end, text)
  - Dịch từng cue theo batch (giữ nguyên mốc thời gian)
  - Ghi lại .srt đã dịch
  - Tùy chọn: ghép giọng đọc TTS cho từng cue (tạo voiceover khớp timeline)
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TIME_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})")


# --------------------------------------------------------------------------
# Đọc / ghi phụ đề
# --------------------------------------------------------------------------

def parse_srt(path):
    """Đọc file .srt hoặc .vtt -> list cue dict."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    # bỏ header WEBVTT nếu có
    raw = re.sub(r"^WEBVTT.*?\n\n", "", raw, flags=re.S)

    cues = []
    blocks = re.split(r"\n\s*\n", raw.strip())
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        m = None
        text_start = 0
        for i, ln in enumerate(lines):
            m = TIME_RE.search(ln)
            if m:
                text_start = i + 1
                break
        if not m:
            continue
        start, end = m.group(1), m.group(2)
        text = "\n".join(lines[text_start:]).strip()
        text = re.sub(r"<[^>]+>", "", text)  # bỏ tag html
        cues.append({"index": len(cues) + 1, "start": start, "end": end,
                     "text": text})
    return cues


def write_srt(cues, path):
    out = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{c['start']} --> {c['end']}\n{c['text'].strip()}\n")
    Path(path).write_text("\n".join(out), encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------
# Dịch
# --------------------------------------------------------------------------

def _translate_batch(texts, src="en", tgt="vi"):
    """Dịch 1 batch câu bằng LLM. Trả về list câu đã dịch (giữ đúng thứ tự)."""
    prompt = (
        f"Dịch các phụ đề sau từ {src} sang {tgt}. "
        "Giữ nguyên ý, văn phong tự nhiên như lời thoại video. "
        "Trả về JSON object: {\"lines\": [\"câu 1\", \"câu 2\", ...]} "
        "với đúng số dòng và đúng thứ tự, không giải thích.\n\n"
        "Các dòng cần dịch:\n"
        + json.dumps(texts, ensure_ascii=False)
    )
    from generator import _call_deepseek, _call_claude, _call_openai

    raw = _call_deepseek(prompt) or _call_claude(prompt) or _call_openai(prompt)
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    data = json.loads(s.strip())
    lines = data.get("lines") or data.get("translation") or []
    if isinstance(lines, str):
        lines = [lines]
    return [str(x) for x in lines]


def translate_cues(cues, src="en", tgt="vi", batch_size=15, use_llm=True):
    """Dịch toàn bộ cue. Nếu không có LLM, trả nguyên văn + cảnh báo."""
    if not use_llm:
        print("[srt] không dùng LLM -> giữ nguyên nội dung gốc")
        return cues

    total = len(cues)
    out = []
    for i in range(0, total, batch_size):
        batch = cues[i:i + batch_size]
        texts = [c["text"] for c in batch]
        print(f"[srt] dịch cue {i+1}-{min(i+batch_size, total)}/{total}...")
        try:
            translated = _translate_batch(texts, src, tgt)
        except Exception as e:  # noqa: BLE001
            print(f"[srt] lỗi dịch batch (giữ nguyên): {e}")
            translated = None

        if not translated or len(translated) != len(texts):
            if translated and len(translated) != len(texts):
                print(f"[srt]   cảnh báo: {len(translated)}/{len(texts)} dòng, "
                      "giữ nguyên batch này")
            for c in batch:
                out.append(dict(c))
            continue

        for c, new_text in zip(batch, translated):
            d = dict(c)
            d["text"] = new_text
            out.append(d)

    return out


def make_tts_voiceover(cues, out_path, voice="hoaimy", tgt="vi"):
    """Sinh 1 file voiceover liền mạch từ các cue đã dịch (ghép theo thứ tự)."""
    from engines import get_engine
    from voices import resolve_voice

    engine = get_engine("edge-tts")
    if not engine.available():
        print("[srt] edge-tts chưa cài -> bỏ qua voiceover")
        return None
    text = " ".join(c["text"].strip() for c in cues if c["text"].strip())
    if not text:
        return None
    engine.synthesize(text, resolve_voice(voice), out_path)
    return out_path
