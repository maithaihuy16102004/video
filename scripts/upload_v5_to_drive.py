"""Upload all V5.0 deliverables to Google Drive review folder.
Target folder: Universal_Cinematic_Pipeline_V50_Production_Review (1pMm_l5XxpKADtqBBAp__E9q8iqujcPKH)
Under permanent root: 1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT_FOLDER_ID = "1pMm_l5XxpKADtqBBAp__E9q8iqujcPKH"

FILES_TO_UPLOAD = [
    # Master MP4 Videos
    ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review" / "v5_shanghai_1930_master.mp4",
    ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review" / "v5_choray_er_master.mp4",
    ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review" / "v5_sahara_2050_master.mp4",

    # Proof Contact Sheets
    ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review" / "v5_shanghai_1930_contact.png",
    ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review" / "v5_choray_er_contact.png",
    ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review" / "v5_sahara_2050_contact.png",

    # Scene Packages & Manifest
    ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review" / "package_shanghai_1930.json",
    ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review" / "package_choray_er.json",
    ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review" / "package_sahara_2050.json",
    ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review" / "v5_generalization_manifest.json",

    # 12 Technical Reports and Specifications
    ROOT / "V5_VISUAL_STYLE_BIBLE.md",
    ROOT / "V5_CHARACTER_ASSET_LIBRARY.md",
    ROOT / "V5_ANIMATION_CAPABILITY_MATRIX.md",
    ROOT / "V5_ENVIRONMENT_ASSET_LIBRARY.md",
    ROOT / "V5_PRODUCTION_SCENE_SCHEMA.json",
    ROOT / "V5_ENGINE_ARCHITECTURE.md",
    ROOT / "V5_FRONTEND_E2E_TEST_REPORT.md",
    ROOT / "V5_INSTALL_AND_RUN.md",
    ROOT / "V5_GENERALIZATION_TEST_REPORT.md",
    ROOT / "V5_SOURCE_FREEZE_VALIDATION.json",
    ROOT / "V5_RENDERER_PROVENANCE.json",
    ROOT / "V5_KNOWN_LIMITATIONS.md",
]

def upload_file(path: Path) -> dict:
    print(f"Uploading {path.name}...")
    cmd = [
        "gdrive", "mutate", "upload",
        str(path),
        "--parent", PARENT_FOLDER_ID
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", shell=True)
    output = res.stdout + res.stderr
    print(output.strip())

    file_id = ""
    # Extract file ID from output
    m = re.search(r"Uploaded\s+([a-zA-Z0-9_-]{20,})", output)
    if m:
        file_id = m.group(1)
    else:
        # Fallback regex
        m2 = re.search(r"([a-zA-Z0-9_-]{25,})", output)
        if m2:
            file_id = m2.group(1)

    url = f"https://drive.google.com/file/d/{file_id}/view" if file_id else ""
    return {
        "filename": path.name,
        "file_id": file_id,
        "view_url": url,
        "size_bytes": path.stat().st_size if path.exists() else 0
    }

def main():
    print(f"Starting V5.0 Google Drive Upload to folder: {PARENT_FOLDER_ID}")
    manifest = []
    for f in FILES_TO_UPLOAD:
        if not f.exists():
            print(f"Warning: file {f} does not exist, skipping.")
            continue
        record = upload_file(f)
        manifest.append(record)

    out_manifest = ROOT / "output" / "Universal_Cinematic_Pipeline_V50_Production_Review" / "v5_drive_upload_manifest.json"
    out_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nUpload complete! Manifest written to:", out_manifest)

if __name__ == "__main__":
    main()
