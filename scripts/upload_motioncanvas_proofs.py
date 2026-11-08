"""Upload Motion Canvas V4 Proof deliverables to locked Google Drive folder.
Folder ID: 1mN4-LlldQX2A_C005oCn8XfDCEmeno3W
"""
import hashlib
import json
from pathlib import Path
import subprocess

DRIVE_FOLDER_ID = "1mN4-LlldQX2A_C005oCn8XfDCEmeno3W"

FILES_TO_UPLOAD = [
    Path("output/motioncanvas_proof/episode01_motioncanvas_3d_world_proof_master.png"),
    Path("output/motioncanvas_proof/odeonsplatz_proof_00s.png"),
    Path("output/motioncanvas_proof/odeonsplatz_proof_38s.png"),
    Path("output/motioncanvas_proof/odeonsplatz_proof_75s.png"),
    Path("output/motioncanvas_proof/odeonsplatz_proof_11s.png"),
    Path("output/motioncanvas_proof/motioncanvas_scene_validation_report.json"),
    Path("output/motioncanvas_upstream_integration_audit.json"),
]

def main():
    print(f"Target Drive Folder: {DRIVE_FOLDER_ID}")
    
    # 1. List existing files to avoid duplicate uploads
    res = subprocess.run(f"gdrive readonly ls {DRIVE_FOLDER_ID} --max 200 --json", shell=True, capture_output=True, text=True)
    existing_files = {}
    if res.returncode == 0 and res.stdout.strip():
        try:
            data = json.loads(res.stdout)
            for item in data:
                existing_files[item.get("name")] = item.get("id")
        except Exception:
            pass

    records = []
    for fpath in FILES_TO_UPLOAD:
        if not fpath.exists():
            print(f"Skipping missing: {fpath}")
            continue
        fname = fpath.name
        fhash = hashlib.sha256(fpath.read_bytes()).hexdigest()[:16]

        if fname in existing_files:
            fid = existing_files[fname]
            # Update existing file in-place
            cmd = f'gdrive mutate update {fid} "{fpath}"'
            ures = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            action = "UPDATED_IN_PLACE"
        else:
            # Upload new file
            cmd = f'gdrive mutate upload "{fpath}" --parent {DRIVE_FOLDER_ID}'
            ures = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            action = "UPLOADED_NEW"
            # Get fid from output
            fid = None
            for token in ures.stdout.split():
                if len(token) > 20 and not token.startswith("http"):
                    fid = token
                    break

        print(f"[{action}] {fname} -> {fid} (hash: {fhash})")
        records.append({
            "name": fname,
            "id": fid,
            "action": action,
            "sha256_short": fhash,
            "size": fpath.stat().st_size
        })

    out_rep = Path("output/motioncanvas_proof/motioncanvas_drive_sync_report.json")
    out_rep.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved sync report to: {out_rep}")

if __name__ == "__main__":
    main()
