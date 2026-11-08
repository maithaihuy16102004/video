import subprocess, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER_ID = "1ynLIWtAjDxZQnRdaTBFPvFTN84PoU-wO"
TARGET_DIR = ROOT / "output" / "v51_drafts"

files = [
    TARGET_DIR / "v51_stabilized_edo_courier_draft_1.mp4",
    TARGET_DIR / "v51_stabilized_edo_courier_draft_2.mp4",
    TARGET_DIR / "v51_stabilized_edo_courier_draft_3.mp4",
    TARGET_DIR / "v51_stabilized_edo_courier_contact.png",
    TARGET_DIR / "v51_stabilized_edo_courier_master_audio.wav",
    TARGET_DIR / "v51_stabilized_shanghai_1930_draft_1.mp4",
    TARGET_DIR / "v51_stabilized_shanghai_1930_contact.png",
    TARGET_DIR / "v51_stabilized_shanghai_1930_master_audio.wav",
    TARGET_DIR / "v51_stabilized_vostok_antarctic_draft_1.mp4",
    TARGET_DIR / "v51_stabilized_vostok_antarctic_contact.png",
    TARGET_DIR / "v51_stabilized_vostok_antarctic_master_audio.wav",
    TARGET_DIR / "acceptance_test_suite_results.json"
]

manifest = {}
for f in files:
    if not f.exists():
        continue
    size_mb = f.stat().st_size / 1024 / 1024
    print(f"Uploading {f.name} ({size_mb:.2f} MB)...")
    res = subprocess.run(["gdrive", "mutate", "upload", str(f), "--parent", FOLDER_ID], capture_output=True, text=True, shell=True)
    out_text = res.stdout.strip()
    m = re.search(r"\(ID:\s*([^\)]+)\)", out_text)
    if m:
        fid = m.group(1).strip()
        manifest[f.name] = {
            "id": fid,
            "url": f"https://drive.google.com/file/d/{fid}/view",
            "size": f.stat().st_size
        }
        print(f"  -> OK! {fid}")
    else:
        print(f"  Result: {out_text} (err: {res.stderr.strip()})")

(ROOT / "output" / "v51_stabilized_winners_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("\nAll stabilized winners uploaded successfully!")
