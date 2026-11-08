import subprocess
import json

res = subprocess.run(['gdrive', 'readonly', 'ls', '1pMm_l5XxpKADtqBBAp__E9q8iqujcPKH', '--json'], capture_output=True, text=True, shell=True)
data = json.loads(res.stdout)
print(f"Total files in Drive folder: {len(data)}")
for f in sorted(data, key=lambda x: x['name']):
    print(f" - {f['name']} ({f['size']} bytes) -> ID: {f['id']}")
