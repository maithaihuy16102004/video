import json
import sys
import urllib.request

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

req = urllib.request.Request(
    'http://localhost:8787/api/v42/test-submission',
    data=json.dumps({'script': 'Munich, tháng 8 năm 1914. Tôi đứng lẫn trong đám đông quảng trường Odeonsplatz, tay kẹp chặt tập ký họa kiến trúc chưa bán được.'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode('utf-8'))
    print(json.dumps(result, indent=2, ensure_ascii=False))
