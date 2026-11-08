import os
import sys
import subprocess
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "v51_drafts"
FOLDER_ID = "184s_VkSeauebGwyIshIyBFlVhW7GWN82"

files_to_upload = [
    # Videos
    OUTPUT_DIR / "draft_1_v51_draft_1_cafe_dialogue.mp4",
    OUTPUT_DIR / "draft_2_v51_draft_2_bridge_action.mp4",
    OUTPUT_DIR / "draft_3_v51_draft_3_emotional_twist.mp4",
    # Contact Sheets & Proofs
    OUTPUT_DIR / "draft_1_contact.png",
    OUTPUT_DIR / "draft_2_contact.png",
    OUTPUT_DIR / "draft_3_contact.png",
    OUTPUT_DIR / "frontend_edo_script_parsed_proof.png",
    # Sync Logs
    OUTPUT_DIR / "draft_1_master_audio_sync_events.json",
    OUTPUT_DIR / "draft_2_master_audio_sync_events.json",
    OUTPUT_DIR / "draft_3_master_audio_sync_events.json",
    # Audio Masters & Stems
    OUTPUT_DIR / "draft_1_master_audio.wav",
    OUTPUT_DIR / "draft_2_master_audio.wav",
    OUTPUT_DIR / "draft_3_master_audio.wav",
    OUTPUT_DIR / "draft_1_master_audio_dialogue_stem.wav",
    OUTPUT_DIR / "draft_1_master_audio_foley_stem.wav",
    OUTPUT_DIR / "draft_1_master_audio_ambience_stem.wav",
    OUTPUT_DIR / "draft_1_master_audio_music_stem.wav",
    OUTPUT_DIR / "draft_2_master_audio_narration_stem.wav",
    OUTPUT_DIR / "draft_2_master_audio_foley_stem.wav",
    OUTPUT_DIR / "draft_2_master_audio_ambience_stem.wav",
    OUTPUT_DIR / "draft_2_master_audio_music_stem.wav",
    OUTPUT_DIR / "draft_3_master_audio_dialogue_stem.wav",
    OUTPUT_DIR / "draft_3_master_audio_foley_stem.wav",
    OUTPUT_DIR / "draft_3_master_audio_ambience_stem.wav",
    OUTPUT_DIR / "draft_3_master_audio_music_stem.wav",
]

print(f"Uploading {len(files_to_upload)} files to Google Drive Folder: {FOLDER_ID}...")

manifest = []
for idx, f in enumerate(files_to_upload):
    if not f.exists():
        print(f"[{idx+1}/{len(files_to_upload)}] SKIPPED (not found): {f.name}")
        continue
    size_mb = f.stat().st_size / (1024 * 1024)
    print(f"[{idx+1}/{len(files_to_upload)}] Uploading {f.name} ({size_mb:.2f} MB)...")
    cmd = ["gdrive", "mutate", "upload", str(f), "--parent", FOLDER_ID, "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if res.returncode != 0:
        print(f"  Error uploading {f.name}: {res.stderr}")
        continue
    try:
        data = json.loads(res.stdout)
        file_id = data.get("id")
        print(f"    -> OK! File ID: {file_id}")
        manifest.append({
            "name": f.name,
            "id": file_id,
            "size_bytes": f.stat().st_size,
            "url": f"https://drive.google.com/file/d/{file_id}/view"
        })
    except Exception as e:
        print(f"    Raw output: {res.stdout.strip()}")

manifest_path = OUTPUT_DIR / "v51_drive_manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nManifest successfully saved to {manifest_path}")
