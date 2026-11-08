import os
import sys
import subprocess
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF_DIR = ROOT / "output" / "V51_Rig_Rebuild_Proofs"
FOLDER_ID = "17kYF2fMhcBo_G7EJqIlWwdnTb3p4Sbl1"

files = sorted(list(PROOF_DIR.glob("*")))
print(f"Total files to upload: {len(files)}")

manifest = []
for idx, f in enumerate(files):
    print(f"[{idx+1}/{len(files)}] Uploading {f.name} ({f.stat().st_size / 1024:.1f} KB)...")
    cmd = ["gdrive", "mutate", "upload", str(f), "--parent", FOLDER_ID, "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if res.returncode != 0:
        print(f"Error uploading {f.name}: {res.stderr}")
        continue
    try:
        data = json.loads(res.stdout)
        file_id = data.get("id")
        print(f"    Uploaded: {f.name} -> ID: {file_id}")
        manifest.append({
            "name": f.name,
            "id": file_id,
            "size": f.stat().st_size,
            "url": f"https://drive.google.com/file/d/1{file_id}/view" if not file_id.startswith("1") else f"https://drive.google.com/file/d/{file_id}/view"
        })
    except Exception as e:
        print(f"    Raw output: {res.stdout.strip()}")

manifest_path = PROOF_DIR / "v51_drive_manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nManifest saved to {manifest_path}")
