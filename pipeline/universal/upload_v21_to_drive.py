"""Uploads all V2.1 review deliverables and shot frames to Google Drive."""
import subprocess
from pathlib import Path

OUT_V21 = Path("output/universal_review_v21")
PARENT_FOLDER_ID = "1D9oU3pohqCugsirhkbS6MilkcOad7-v8"  # Universal_Cinematic_Director_V21_Test

files_to_upload = sorted(list(OUT_V21.glob("*.png")) + list(OUT_V21.glob("*.json")))

results = {}
for p in files_to_upload:
    cmd = f'gdrive mutate upload "{p}" --parent {PARENT_FOLDER_ID}'
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode == 0:
        out = res.stdout.strip()
        drive_id = None
        if "(ID:" in out:
            drive_id = out.split("(ID:")[-1].replace(")", "").strip()
        print(f"[DRIVE_UPLOAD] {p.name:<45} -> ID: {drive_id}")
        results[p.name] = drive_id
    else:
        print(f"[DRIVE_ERROR] {p.name}: {res.stderr.strip()}")

print(f"\nSuccessfully synchronized {len(results)} files to Google Drive folder Universal_Cinematic_Director_V21_Test.")
