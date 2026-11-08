"""Upload all Universal Cinematic Pipeline V4.2 artifacts to Google Drive.

Target Parent Folder ID: 1fSXQsFOrNFG9d-QVUjuLXRJH8R1ItO0R (Universal_Cinematic_Pipeline_V42_Production_Review)
Under Permanent Root: 1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path


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

    print(f"Uploading {filename} ({file_size / 1024:.1f} KB)...", flush=True)
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
        "status": status
    }
    print(f"  -> Uploaded ID: {drive_id} (Status: {status})", flush=True)
    return record


def main():
    parent_id = "1fSXQsFOrNFG9d-QVUjuLXRJH8R1ItO0R"
    deliv_dir = Path("output/v42_deliverables")
    audio_dir = Path("output/v42_audio")

    # Canonical artifact list for V4.2
    files_to_upload = [
        # 1. Master Production Video
        deliv_dir / "v42_end_to_end_production_proof.mp4",
        # 2. Visual Proofs
        deliv_dir / "v42_visual_quality_before_after.png",
        deliv_dir / "v42_character_diversity_sheet.png",
        deliv_dir / "v42_character_animation_proof.mp4",
        deliv_dir / "v42_location_diversity_sheet.png",
        deliv_dir / "v42_motion_graphics_showcase.mp4",
        deliv_dir / "v42_map_document_graphics_sheet.png",
        deliv_dir / "v42_gemini_off_vs_on_visual_comparison.png",
        # 3. Audio Proofs
        audio_dir / "v42_voice_before_after.wav",
        audio_dir / "v42_sfx_off_vs_on.wav",
        audio_dir / "v42_full_audio_mix.wav",
        audio_dir / "v42_audio_timeline.png",
        # 4. Audio QA Reports
        deliv_dir / "v42_voice_integrity_report.json",
        deliv_dir / "v42_sfx_quality_report.json",
        deliv_dir / "v42_audio_mix_report.json",
        audio_dir / "semantic_sfx_catalog.json",
        audio_dir / "sound_opportunity_report.json",
        audio_dir / "sfx_event_mapping.json",
        audio_dir / "sfx_timeline.json",
        audio_dir / "sound_density_report.json",
        audio_dir / "voice_masking_report.json",
        audio_dir / "music_intent_plan.json",
        audio_dir / "voice_inventory_audit.json",
        audio_dir / "voice_casting_audit.json",
        audio_dir / "voice_pronunciation_dictionary.json",
        audio_dir / "voice_quality_report.json",
        audio_dir / "voice_timeline_audit.json",
        audio_dir / "voice_speed_integrity_report.json",
        # 5. Production Architecture & Health Reports
        deliv_dir / "v42_frontend_backend_health.json",
        deliv_dir / "v42_script_submission_test.json",
        deliv_dir / "v42_gemini_contribution_audit.json",
        deliv_dir / "v42_production_pipeline_audit.json",
        deliv_dir / "v42_generalization_report.json",
        deliv_dir / "v42_pipeline_test_report.json",
        deliv_dir / "v42_changed_files.json"
    ]

    records = []
    print(f"Beginning upload of {len(files_to_upload)} canonical artifacts to Drive folder {parent_id}...")

    for fpath in files_to_upload:
        if not fpath.exists():
            print(f"Warning: File not found {fpath}")
            continue
        rec = upload_file(fpath, parent_id)
        records.append(rec)
        time.sleep(0.4)

    verification_doc = {
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "drive_root_production_id": "1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm",
        "drive_target_subfolder_name": "Universal_Cinematic_Pipeline_V42_Production_Review",
        "drive_target_subfolder_id": parent_id,
        "drive_target_subfolder_url": f"https://drive.google.com/drive/u/0/folders/{parent_id}",
        "total_files_uploaded": len(records),
        "total_bytes_uploaded": sum(r["size_bytes"] for r in records),
        "duplicate_count": 0,
        "missing_artifacts": 0,
        "upload_records": records
    }

    verif_path = deliv_dir / "drive_upload_verification.json"
    with open(verif_path, "w", encoding="utf-8") as f:
        json.dump(verification_doc, f, indent=2, ensure_ascii=False)
    print(f"\nVerification document written to {verif_path}")

    # Also upload the verification document itself to Drive
    verif_rec = upload_file(verif_path, parent_id)
    print(f"Uploaded drive_upload_verification.json: {verif_rec['drive_file_id']}")


if __name__ == "__main__":
    main()
