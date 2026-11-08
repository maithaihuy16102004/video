"""Upload Edo Courier Master Video and Proof Artifacts to Google Drive."""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

TARGET_FOLDER_ID = "1fSXQsFOrNFG9d-QVUjuLXRJH8R1ItO0R"
SRC_DIR = Path("output/Universal_Cinematic_Pipeline_V42_Production_Review")


def get_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def upload_file(filepath: Path, parent_id: str) -> dict:
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
        SRC_DIR / "v42_edo_courier_master.mp4",
        SRC_DIR / "v42_edo_courier_storyboard_contact.png",
        SRC_DIR / "frame_scene1_station_directive.png",
        SRC_DIR / "frame_scene2_street_sprint.png",
        SRC_DIR / "frame_scene3_bridge_snap_near_fall.png",
        SRC_DIR / "frame_scene4_lantern_house_aiko_laugh.png",
        SRC_DIR / "frame_scene5_twist_letter_lost_sandal.png",
        SRC_DIR / "v42_edo_courier_production_package.json"
    ]

    results = []
    for fp in files_to_upload:
        if fp.exists():
            rec = upload_file(fp, TARGET_FOLDER_ID)
            results.append(rec)
        else:
            print(f"File not found: {fp}")

    out_manifest = SRC_DIR / "v42_edo_courier_drive_manifest.json"
    out_manifest.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nManifest saved to {out_manifest}")
    upload_file(out_manifest, TARGET_FOLDER_ID)


if __name__ == "__main__":
    main()
