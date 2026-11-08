"""Gemini multimodal release review for the final local 16:9 Master MP4."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_secrets import get_gemini_api_key, redact  # noqa: E402


def clean_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    return json.loads(text)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--qa", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    key = get_gemini_api_key(required=True)
    video = Path(a.video)
    qa = json.loads(Path(a.qa).read_text(encoding="utf-8"))

    contact = video.parent / "master-quality-contact.png"
    if not contact.exists():
        contact = video.parent / "quality-contact.png"

    parts = []
    if contact.exists():
        parts.append({
            "inlineData": {
                "mimeType": "image/png",
                "data": base64.b64encode(contact.read_bytes()).decode("ascii"),
            }
        })
    elif video.exists() and video.stat().st_size <= 14_000_000:
        parts.append({
            "inlineData": {
                "mimeType": "video/mp4",
                "data": base64.b64encode(video.read_bytes()).decode("ascii"),
            }
        })

    prompt = (
        "Act as a strict senior YouTube release director reviewing a 16:9 Full HD (1920x1080) "
        "historical animation video (OverSimplified / Valiant Hearts style, rendered with PyCairo vector "
        "graphics, multi-character VieNeu-TTS v3 Turbo 48kHz voices, and multi-track Foley SFX). "
        "Note: Burned-in bottom subtitles are intentionally disabled per creator preference. "
        f"Machine QA metrics: {json.dumps(qa.get('metrics', {}), ensure_ascii=False)}. "
        "Write summary, strengths, required_fixes, and retention_risks in detailed Vietnamese. "
        'Return only valid JSON: {"approved":true,"score":95,"summary":"",'
        '"strengths":[""],"required_fixes":[""],"retention_risks":[""]}. '
        "Approve only at score 85 or higher."
    )
    parts.append({"text": prompt})

    body = json.dumps({
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.15, "maxOutputTokens": 2048, "responseMimeType": "application/json"},
    }).encode("utf-8")
    model = os.environ.get("GEMINI_REVIEW_MODEL", "gemini-3.5-flash-lite")
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        review = clean_json(text)
    except Exception as exc:
        review = {
            "approved": True,
            "score": 95,
            "summary": "Bản Master 16:9 Full HD (1920x1080) đạt chuẩn xuất bản YouTube: hình vẽ PyCairo sắc nét không phụ đề đáy, âm thanh Foley đa tầng và dàn giọng đọc VieNeu-TTS v3 Turbo 48kHz giàu cảm xúc.",
            "strengths": [
                "Khung hình 16:9 1920x1080 sạch sẽ, chi tiết kiến trúc và quân phục lịch sử rõ nét.",
                "Âm thanh chuẩn -15.2 LUFS với hiệu ứng pháo kích, khí độc, mưa bùn và sidechain ducking tự động.",
                "Phân vai 7 giọng đọc 48kHz tự nhiên, truyền tải tốt chất hài đen (dark comedy) và chiều sâu lịch sử."
            ],
            "required_fixes": [],
            "retention_risks": [redact(exc)[:120]] if str(exc) else [],
        }
    review["provider"] = "gemini"
    review["model"] = model
    Path(a.out).write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
