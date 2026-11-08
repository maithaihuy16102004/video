import subprocess, json
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
    print(f"Uploading {f.name} ({f.stat().st_size / 1024 / 1024:.2f} MB)...")
    res = subprocess.run(["gdrive", "mutate", "upload", str(f), "--parent", FOLDER_ID, "--json"], capture_output=True, text=True, shell=True)
    if res.returncode == 0:
        data = json.loads(res.stdout)
        fid = data.get("id")
        manifest[f.name] = {
            "id": fid,
            "url": f"https://drive.google.com/file/d/{fid}/view",
            "size": f.stat().st_size
        }
        print(f"  -> OK! {fid}")

(ROOT / "output" / "v51_stabilized_winners_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("All stabilized winners uploaded successfully!")
