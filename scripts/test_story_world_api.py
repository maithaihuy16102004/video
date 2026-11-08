import json
import sys
import urllib.request

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

req = urllib.request.Request(
    'http://localhost:8787/api/story-world',
    data=json.dumps({'script': 'Munich, tháng 8 năm 1914. Tôi đứng lẫn trong đám đông quảng trường Odeonsplatz, tay kẹp chặt tập ký họa kiến trúc chưa bán được.'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode('utf-8'))
    print(f"Title: {result.get('title')}")
    print(f"Duration: {result.get('duration')}s")
    print(f"Scenes: {len(result.get('scenes', []))}")
    print(f"Cast: {[c['name'] for c in result.get('cast', [])]}")
    print(f"Visual Plan elements: {len(result.get('visualPlan', []))}")
    print(f"Sound Plan cues: {len(result.get('soundPlan', []))}")
    print(f"Status: {result.get('status')}")
