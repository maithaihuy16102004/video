"""Uploads all prototype images and reports to Google Drive."""
import os
import subprocess
from pathlib import Path

BASE_DIR = Path("output/gemini_scene_test")

PARENT_MAIN = "10CkwvKYlwn8oWdXSoFXXTTpIS71Mdu9W"      # Gemini_Scene_Test_AB
PARENT_CARDS = "1YBE5h894PSrfpon4_gUkZOtwV190gmLR"     # 3_Panel_Cards
PARENT_AB = "1DyW0_hGNDQrITcdJ34ddbhTbVCv8oskT"        # AB_Comparisons

def upload_file(file_path: Path, parent_id: str) -> None:
    print(f"Uploading {file_path.name} to {parent_id}...")
    cmd = f'gdrive mutate upload "{file_path}" --parent {parent_id}'
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error uploading {file_path.name}: {res.stderr.strip()}")
    else:
        print(f"  -> {res.stdout.strip()}")

def main():
    # 1. Upload Cards
    cards_dir = BASE_DIR / "cards"
    for f in sorted(cards_dir.glob("*.png")):
        upload_file(f, PARENT_CARDS)

    # 2. Upload AB Comparisons
    ab_dir = BASE_DIR / "ab_comparisons"
    for f in sorted(ab_dir.glob("*.png")):
        upload_file(f, PARENT_AB)

    # 3. Upload Reports to Main Folder
    for rep in ["visual_test_report.md", "gemini_scene_ab_test_report.json", "gemini_cost_report.json", "environment_reuse_report.json"]:
        p = BASE_DIR / rep
        if p.exists():
            upload_file(p, PARENT_MAIN)

    print("\n--- ALL ARTIFACTS UPLOADED TO GOOGLE DRIVE ---")

if __name__ == "__main__":
    main()
