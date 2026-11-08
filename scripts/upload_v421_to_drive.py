"""Upload all V4.2.1 deliverables to Google Drive review folder."""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

TARGET_FOLDER_ID = "1LcjoqswcbPe3be5jm_Ss3VfyyLfEqxBS"
SRC_DIR = Path("output/Universal_Cinematic_Pipeline_V421_Renderer_Recovery")


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
        SRC_DIR / "v421_renderer_forensic_report.md",
        SRC_DIR / "v421_renderer_provenance.json",
        SRC_DIR / "v421_v4_vs_v42_vs_fixed_comparison.png",
        SRC_DIR / "v421_edo_bridge_proof.mp4",
        SRC_DIR / "v421_edo_house_proof.mp4",
        SRC_DIR / "v421_unrelated_story_proof.mp4",
        SRC_DIR / "v421_character_quality_sheet.png",
        SRC_DIR / "v421_environment_quality_sheet.png",
        SRC_DIR / "v421_font_validation.json",
        SRC_DIR / "v421_audio_validation.json",
        SRC_DIR / "v421_drive_playback_validation.json",
        SRC_DIR / "v421_regression_report.json"
    ]

    results = []
    for fp in files_to_upload:
        if fp.exists():
            rec = upload_file(fp, TARGET_FOLDER_ID)
            results.append(rec)
        else:
            print(f"File not found: {fp}")

    manifest_path = SRC_DIR / "v421_drive_manifest.json"
    manifest_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nManifest saved to {manifest_path}")
    upload_file(manifest_path, TARGET_FOLDER_ID)


if __name__ == "__main__":
    main()
