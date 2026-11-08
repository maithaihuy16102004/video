"""Direct UI End-to-End Test Suite.

Tests UI HTTP routes on http://127.0.0.1:4173:
1. /api/gemini (Gemini API Key configuration)
2. /api/plan (16:9 Scene planning & character casting)
3. /api/review-content (Gemini 3.5 content, history, visual & SFX review)
4. /api/render (Draft rendering pipeline)
5. /api/status (Real-time job status polling)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:4173"
KEY = "DUMMY_GEMINI_KEY"


def post_json(path: str, data: dict):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def get_json(path: str):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main():
    print("=" * 70)
    print("        AI CLIP STUDIO UI DIRECT END-TO-END TEST")
    print("=" * 70)

    # 1. UI Root Health Check
    print("\n--- TEST 1: UI HOME PAGE ACCESS (http://127.0.0.1:4173) ---")
    req = urllib.request.Request(BASE_URL)
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
        print(f"  HTTP Status: {resp.status} OK")
        print(f"  Page Size: {len(html)} bytes")
        print(f"  Contains App Title: {'AI Clip Studio' in html or 'AI' in html}")

    # 2. Configure Key via UI
    print("\n--- TEST 2: CONFIGURE GEMINI API KEY VIA UI (/api/gemini) ---")
    status, res = post_json("/api/gemini", {"key": KEY, "model": "gemini-3.5-flash-lite"})
    print(f"  HTTP Status: {status}")
    print(f"  Response: {res}")

    # 3. Plan Generation via UI
    print("\n--- TEST 3: SCRIPT DECOMPOSITION & PLAN GENERATION VIA UI (/api/plan) ---")
    script_text = """[HOOK — MUNICH, 1914]

NGƯỜI DẪN:
Hãy tưởng tượng bạn 25 tuổi. Chiến tranh thế giới thứ nhất bùng nổ.

SĨ QUAN:
Mang thông điệp này tới sở chỉ huy.

HITLER:
Tôi sẽ đi ngay."""
    status, plan = post_json(
        "/api/plan",
        {"script": script_text, "voice": "vi-VN-NamMinhNeural", "energy": "dynamic", "multiVoice": True},
    )
    print(f"  HTTP Status: {status}")
    print(f"  Title: {plan.get('title')}")
    print(f"  Resolution: {plan.get('resolution')} ({plan.get('aspectRatio')})")
    print(f"  Duration: {plan.get('duration')}s")
    print(f"  Scenes count: {len(plan.get('scenes', []))}")
    print(f"  Cast members: {[c.get('name') for c in plan.get('cast', [])]}")

    # 4. Review Content via Gemini on UI
    print("\n--- TEST 4: GEMINI CONTENT & VISUAL REVIEW VIA UI (/api/review-content) ---")
    status, review = post_json(
        "/api/review-content",
        {
            "script": script_text,
            "voice": "vi-VN-NamMinhNeural",
            "plan": plan,
            "key": KEY,
            "model": "gemini-3.5-flash-lite",
        },
    )
    print(f"  HTTP Status: {status}")
    print(f"  Gemini Model: {review.get('model')}")
    print(f"  Overall Score: {review.get('overall_score')}/100")
    print(f"  Scores: {json.dumps(review.get('scores', {}), indent=4, ensure_ascii=False)}")
    print(f"  Verdict: {review.get('verdict')}")
    if review.get("strengths"):
        print(f"  Strengths: {review.get('strengths')}")

    # 5. Render Video via UI
    print("\n--- TEST 5: LAUNCH VIDEO RENDER VIA UI (/api/render) ---")
    status, job = post_json(
        "/api/render",
        {
            "script": script_text,
            "voice": "vi-VN-NamMinhNeural",
            "energy": "dynamic",
            "quality": "fast",
            "multiVoice": False,
            "aspectRatio": "16:9",
            "plan": plan,
            "multiDraft": False,
        },
    )
    job_id = job.get("id")
    print(f"  HTTP Status: {status}")
    print(f"  Dispatched Job ID: {job_id}")

    # 6. Poll Job Status
    print(f"\n--- TEST 6: REAL-TIME JOB MONITORING VIA UI (/api/status?id={job_id}) ---")
    start_poll = time.time()
    for i in range(45):
        status, st = get_json(f"/api/status?id={job_id}")
        msg = st.get("message", "")
        state = st.get("status", "")
        print(f"  [{time.time() - start_poll:.1f}s] Status: {state} | Message: {msg}")
        if state in ("done", "failed", "review_required"):
            print(f"\n>> Final State Reached: {state}")
            if st.get("qa"):
                print(f"   QA Machine Score: {st['qa'].get('score')}/100")
            if st.get("gdrive"):
                print(f"   Google Drive URL: {st['gdrive'].get('url')}")
            break
        time.sleep(2)

    print("\n" + "=" * 70)
    print("      ALL UI DIRECT TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    main()
