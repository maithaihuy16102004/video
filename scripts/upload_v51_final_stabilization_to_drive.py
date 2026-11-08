import os
import sys
import subprocess
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER_ID = "1ynLIWtAjDxZQnRdaTBFPvFTN84PoU-wO"

def upload_file(f_path: Path):
    if not f_path.exists():
        print(f"SKIPPED (not found): {f_path.name}")
        return None
    size_mb = f_path.stat().st_size / (1024 * 1024)
    print(f"Uploading {f_path.name} ({size_mb:.2f} MB) to Google Drive...")
    cmd = ["gdrive", "mutate", "upload", str(f_path), "--parent", FOLDER_ID, "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if res.returncode != 0:
        print(f"  Error uploading {f_path.name}: {res.stderr}")
        return None
    try:
        data = json.loads(res.stdout)
        file_id = data.get("id")
        print(f"    -> OK! File ID: {file_id}")
        return {
            "name": f_path.name,
            "id": file_id,
            "size_bytes": f_path.stat().st_size,
            "url": f"https://drive.google.com/file/d/{file_id}/view"
        }
    except Exception as e:
        print(f"    Raw output: {res.stdout.strip()}")
        return None

def main():
    print(f"==================================================================")
    print(f"UPLOADING V5.1 FINAL STABILIZATION DELIVERABLES TO DRIVE FOLDER: {FOLDER_ID}")
    print(f"==================================================================")

    # Gather files
    files_to_upload = []
    
    # Check output/v51_drafts
    v51_dir = ROOT / "output" / "v51_drafts"
    if v51_dir.exists():
        for p in v51_dir.glob("*"):
            if p.is_file() and p.suffix in (".mp4", ".png", ".wav", ".json"):
                files_to_upload.append(p)
                
    # Also find newest completed studio job dirs
    jobs_dir = ROOT / "output" / "studio-jobs"
    if jobs_dir.exists():
        recent_jobs = sorted(jobs_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:3]
        for j in recent_jobs:
            if j.is_dir():
                for p in j.glob("draft-*.mp4"):
                    files_to_upload.append(p)
                for p in j.glob("*_mixed_master.wav"):
                    files_to_upload.append(p)
                for p in j.glob("*_sync_events.json"):
                    files_to_upload.append(p)

    # De-duplicate by name
    seen = set()
    unique_files = []
    for f in files_to_upload:
        if f.name not in seen and f.exists() and f.stat().st_size > 0:
            seen.add(f.name)
            unique_files.append(f)

    manifest = []
    for f in unique_files:
        info = upload_file(f)
        if info:
            manifest.append(info)

    out_manifest = ROOT / "output" / "v51_final_drive_manifest.json"
    out_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nManifest saved to {out_manifest}")

if __name__ == "__main__":
    main()
