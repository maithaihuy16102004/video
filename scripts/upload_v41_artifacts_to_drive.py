"""Upload all Scene Proof V4.1 artifacts to Google Drive.

Target Parent Folder ID: 1Jz11rLWSHA4fSqmdaW8ull-cKe0JxADO (Episode01_MotionCanvas_Cinematic_Sequence_V41_Test)
Under Production Root: 1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm
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
        # Fallback: query Drive for the uploaded file
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
        "status": status,
        "stdout": res.stdout.strip(),
        "stderr": res.stderr.strip()
    }
    print(f"  -> Uploaded ID: {drive_id} (Status: {status})", flush=True)
    return record


def main():
    parent_id = "1Jz11rLWSHA4fSqmdaW8ull-cKe0JxADO"
    proof_dir = Path("output/motioncanvas_proof_v41")

    # Priority order for review
    priority_files = [
        # 1. Master Video
        "episode01_v41_cinematic_sequence.mp4",
        # 2. Master Audio Proof
        "episode01_v41_voice_proof.wav",
        # 3. Visual Contact Sheets & Proofs
        "episode01_v41_master_contact_sheet.png",
        "episode01_v41_storyboard_clean.png",
        "episode01_v41_story_state_progression.png",
        "episode01_v41_character_acting_sheet.png",
        "episode01_v41_character_grounding_debug.png",
        "episode01_v41_world_persistence_debug.png",
        "episode01_v41_crowd_state_progression.png",
        "episode01_v41_object_interaction_proof.png",
        "episode01_v41_camera_geography_debug.png",
        "episode01_v41_reference_vs_render.png",
        "episode01_v4_vs_v41_comparison.png",
        # 4. Individual Beat Frames
        "beat_A_shot_01_hud.png",
        "beat_A_shot_01_clean.png",
        "beat_B_shot_02_hud.png",
        "beat_B_shot_02_clean.png",
        "beat_C_shot_03_hud.png",
        "beat_C_shot_03_clean.png",
        "beat_D_shot_04_hud.png",
        "beat_D_shot_04_clean.png",
        "beat_E_shot_05_hud.png",
        "beat_E_shot_05_clean.png",
        "beat_F_shot_06_hud.png",
        "beat_F_shot_06_clean.png",
        # 5. Core Machine-Readable Reports
        "episode01_v41_production_scene_package.json",
        "episode01_v41_story_event_graph.json",
        "episode01_v41_sequence_plan.json",
        "episode01_v41_shot_plan.json",
        "episode01_v41_shot_necessity_report.json",
        "episode01_v41_voice_truth_report.json",
        "episode01_v41_sfx_timeline.json",
        "episode01_v41_historical_visual_accuracy.json",
        "episode01_v41_effect_intent_audit.json",
        "episode01_v41_character_contact_audit.json",
        "episode01_v41_world_continuity_audit.json",
        "episode01_v41_gemini_contribution_audit.json",
        "episode01_v41_capability_gap_report.json",
        "episode01_v41_core_data_separation_audit.json",
        "episode01_v41_pipeline_test_report.json",
        "episode01_v41_changed_files.json",
        "generalization_test_1905_lab.json"
    ]

    records = []
    print(f"Beginning upload of {len(priority_files)} artifacts to Google Drive folder {parent_id}...")

    for fname in priority_files:
        fpath = proof_dir / fname
        if not fpath.exists():
            print(f"Warning: File not found {fpath}")
            continue
        rec = upload_file(fpath, parent_id)
        records.append(rec)
        time.sleep(0.5)

    verification_doc = {
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "drive_root_production_id": "1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm",
        "drive_target_subfolder_name": "Episode01_MotionCanvas_Cinematic_Sequence_V41_Test",
        "drive_target_subfolder_id": parent_id,
        "drive_target_subfolder_url": f"https://drive.google.com/drive/u/0/folders/{parent_id}",
        "total_files_uploaded": len(records),
        "total_bytes_uploaded": sum(r["size_bytes"] for r in records),
        "upload_records": records
    }

    verif_path = proof_dir / "drive_upload_verification.json"
    with open(verif_path, "w", encoding="utf-8") as f:
        json.dump(verification_doc, f, indent=2, ensure_ascii=False)
    print(f"\nVerification document written to {verif_path}")

    # Also upload the verification document itself to Drive
    verif_rec = upload_file(verif_path, parent_id)
    print(f"Uploaded drive_upload_verification.json: {verif_rec['drive_file_id']}")


if __name__ == "__main__":
    main()
