"""Gemini Vision reviewer for three local draft contact sheets.

The API key is read from process memory only and is never written to disk.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_secrets import get_gemini_api_key, redact  # noqa: E402

RUBRIC = (
    "Score each 16:9 widescreen historical animation draft out of 100: hook first 3 seconds 20; "
    "pacing/pattern interrupts 20; character acting & costume detail 20; visuals support narration 15; "
    "dark comedy/payoff balance 10; story clarity 10; likely retention 5. Note: Bottom subtitles are "
    "intentionally disabled by user preference for a clean cinematic widescreen frame. Choose potential, "
    "never claim guaranteed virality. Write reasons and required_fixes in Vietnamese."
)


def image_part(path: Path) -> dict:
    return {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(path.read_bytes()).decode("ascii")}}


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    return json.loads(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    key = get_gemini_api_key(required=True)
    job = Path(args.job)
    contacts = sorted(job.glob("draft-*-contact.png"))
    if len(contacts) != 3:
        raise SystemExit("Expected three draft contact sheets")
    prompt = (
        "You are a strict senior YouTube animation editor. Compare the three "
        f"contact sheets in order Draft 1, Draft 2, Draft 3. {RUBRIC} "
        "Return only valid JSON with this exact shape: "
        '{"approved":false,"winner":0,"winner_score":0,'
        '"ranking":[0,1,2],"scores":[0,0,0],'
        '"reasons":["","",""],"required_fixes":[""]}. '
        "winner and ranking use zero-based indexes. approved may be true only "
        "when winner_score is at least 85 and there is no hard fail."
    )
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}, *[image_part(p) for p in contacts]]}],
        "generationConfig": {"temperature": 0.15, "maxOutputTokens": 2048, "responseMimeType": "application/json"},
    }).encode("utf-8")
    preferred = os.environ.get("GEMINI_REVIEW_MODEL", "gemini-3.5-flash-lite")
    models = list(dict.fromkeys([preferred, "gemini-3.8-flash"]))
    payload = None
    model = preferred
    errors = []
    for candidate in models:
        model = candidate
        for attempt in range(2):
            request = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                data=body,
                method="POST",
                headers={"Content-Type": "application/json", "x-goog-api-key": key},
            )
            try:
                with urllib.request.urlopen(request, timeout=240) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")[-500:]
                errors.append(f"{model} HTTP {error.code}: {detail}")
                if error.code not in (429, 503):
                    break
                time.sleep(2 * (attempt + 1))
        if payload is not None:
            break
    if payload is None:
        raise SystemExit(redact(" | ".join(errors[-3:])))
    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    review = extract_json(text)
    winner = int(review.get("winner", -1))
    if winner not in range(3) or len(review.get("scores", [])) != 3:
        raise SystemExit("Gemini returned invalid review JSON")
    review["provider"] = "gemini"
    review["model"] = model
    Path(args.out).write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
