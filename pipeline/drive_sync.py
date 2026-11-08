"""Google Drive automatic upload utility for images and videos.

Whenever video drafts, contact sheets, or environment assets are rendered,
this module automatically synchronizes them to Google Drive.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

# Authoritative Google Drive Folder IDs
DRIVE_DRAFT_FOLDER_ID = "1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm"


def upload_file_to_drive(file_path: Path | str, parent_folder_id: str = DRIVE_DRAFT_FOLDER_ID) -> Optional[str]:
    """Uploads a file to Google Drive using the authenticated gdrive CLI."""
    p = Path(file_path)
    if not p.exists():
        return None

    cmd = f'gdrive mutate upload "{p}" --parent {parent_folder_id}'
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        if res.returncode == 0:
            output = res.stdout.strip()
            # Extract ID if present
            # Output format: "Uploaded: <name> (ID: <id>)"
            drive_id = None
            if "(ID:" in output:
                drive_id = output.split("(ID:")[-1].replace(")", "").strip()
            print(f"[DRIVE_SYNC] Uploaded {p.name} to Drive (ID: {drive_id or 'OK'})")
            return drive_id
        else:
            print(f"[DRIVE_SYNC] Failed to upload {p.name}: {res.stderr.strip()}")
            return None
    except Exception as exc:
        print(f"[DRIVE_SYNC] Exception during upload of {p.name}: {exc}")
        return None
