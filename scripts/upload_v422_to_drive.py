"""Upload all V4.2.2 Universal Engine Deliverables to Google Drive."""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

TARGET_FOLDER_ID = "1LcjoqswcbPe3be5jm_Ss3VfyyLfEqxBS"
SRC_DIR = Path("output/Universal_Cinematic_Pipeline_V421_Renderer_Recovery")
ROOT = Path(__file__).resolve().parents[1]

def get_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def upload_file(filepath: Path, parent_id: str) -> dict:
    if not filepath.exists():
        print(f"Skipping missing file: {filepath}")
        return {"filename": filepath.name, "status": "FILE_NOT_FOUND"}

    file_size = filepath.stat().st_size
    sha256_hash = get_sha256(filepath)
    filename = filepath.name

    print(f"Uploading {filename} ({file_size / (1024*1024):.2f} MB)...", flush=True)
    cmd = f'gdrive mutate upload "{filepath}" --parent {parent_id}'
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    drive_id = ""
    status = "SUCCESS" if res.returncode == 0 else "FAILED"
    for line in res.stdout.splitlines():
        if "Uploaded" in line or "Created" in line or "ID:" in line:
            parts = line.split("ID:")
            if len(parts) > 1:
                drive_id = parts[1].strip().rstrip(")")
            elif "(" in line and ")" in line:
                drive_id = line[line.rfind("(") + 1 : line.rfind(")")].replace("ID:", "").strip()

    if not drive_id and res.returncode == 0:
        q_cmd = f'gdrive readonly search --name-contains "{filename}"'
        q_res = subprocess.run(q_cmd, shell=True, capture_output=True, text=True)
        for q_line in q_res.stdout.splitlines():
            if filename in q_line:
                drive_id = q_line.split()[0].strip()
                break

    record = {
        "filename": filename,
        "local_path": str(filepath),
        "size_bytes": file_size,
        "sha256": sha256_hash,
        "drive_folder_id": parent_id,
        "drive_file_id": drive_id,
        "url": f"https://drive.google.com/file/d/{drive_id}/view" if drive_id else "",
        "status": status
    }
    print(f"  -> Uploaded ID: {drive_id} (Status: {status})", flush=True)
    return record

def main():
    files_to_upload = [
        ROOT / "v421_hardcoding_audit_report.md",
        ROOT / "v422_visual_style_bible.md",
        ROOT / "negative_render_test_report.md",
        SRC_DIR / "render_telemetry.json",
        SRC_DIR / "v422_character_capability_sheet.png",
        SRC_DIR / "v422_environment_capability_sheet.png",
        SRC_DIR / "v422_unseen_scripts_generalization_showcase.png",
        SRC_DIR / "v422_unseen_01_victorian_london.mp4",
        SRC_DIR / "v422_unseen_02_hanoi_coffee.mp4",
        SRC_DIR / "v422_unseen_03_antarctic_aurora.mp4",
        SRC_DIR / "v422_recovered_edo_bridge_proof.mp4",
        SRC_DIR / "v422_recovered_edo_house_proof.mp4",
        SRC_DIR / "v422_recovered_modern_lab_proof.mp4",
    ]

    manifest = []
    print(f"Starting upload of {len(files_to_upload)} deliverables to Drive folder {TARGET_FOLDER_ID}...\n")
    for f in files_to_upload:
        rec = upload_file(f, TARGET_FOLDER_ID)
        manifest.append(rec)
        time.sleep(0.5)

    manifest_path = SRC_DIR / "v422_drive_upload_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nUpload complete! Manifest saved to: {manifest_path}")

if __name__ == "__main__":
    main()
