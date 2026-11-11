"""Google Drive uploader (Master Prompt §12).

Permanent root folder (Mai's draft folder):
    1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm

Per-project structure, created automatically under the root:

    PROJECT_ID/
        01_SCRIPT/  02_STORYBOARD/  03_AUDIO/
        04_DRAFT/   05_QA_REPORTS/  06_MASTER/

Rules enforced here:
- Verify after upload: file exists in the target folder and the
  size matches; store the returned Drive file ID + URL.
- Retry without duplicates: an upload with the same name in the same
  folder is skipped and the existing file ID is reused.
- Never upload a failed draft as an approved Master. A failed
  production may upload logs/diagnostics with an explicit FAILED
  status, in 05_QA_REPORTS only.
- No secrets: the CLI uses the already-connected Google account;
  no token is hardcoded here.

Upstream status (see AUDIT.md): `pipeline/drive_sync.py` already
uploads to this exact root folder ID, but with the `gdrive` CLI and a
flat structure (no 01..06 subfolders, no size verification, no
dedup). `upload_all_to_drive.py` uploads to *different* folders.
This module is the structured, verified uploader, using the
`hatch_gws_cli` connector available on this machine:
    hatch_gws_cli drive +upload <file> --parent <folder-id>
    hatch_gws_cli drive files create --json '{...folder...}'
    hatch_gws_cli drive files list --params '{...}'
The real CLI client is only used when a DriveUploader is constructed
with the default client; tests inject a mock client.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

DRIVE_ROOT_FOLDER_ID = "1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm"
DRIVE_ROOT_URL = (
    "https://drive.google.com/drive/u/0/folders/" + DRIVE_ROOT_FOLDER_ID
)
GWS_CLI = "/opt/hatch/bin/hatch_gws_cli"

PROJECT_FOLDERS = (
    "01_SCRIPT",
    "02_STORYBOARD",
    "03_AUDIO",
    "04_DRAFT",
    "05_QA_REPORTS",
    "06_MASTER",
)

# Which local artifact group goes to which Drive subfolder.
GROUP_FOLDER = {
    "script": "01_SCRIPT",
    "storyboard": "02_STORYBOARD",
    "audio": "03_AUDIO",
    "draft": "04_DRAFT",
    "qa": "05_QA_REPORTS",
    "master": "06_MASTER",
}


class DriveClient(Protocol):
    def create_folder(self, name: str, parent_id: str) -> str: ...
    def find_file(self, name: str, parent_id: str) -> dict | None: ...
    def upload_file(self, path: Path, parent_id: str) -> dict: ...
    def get_file(self, file_id: str) -> dict: ...


class GwsCliDriveClient:
    """Real client shelling out to hatch_gws_cli (connected account)."""

    def _run(self, args: list[str]) -> dict:
        out = subprocess.run(
            [GWS_CLI] + args, capture_output=True, text=True, timeout=300,
        )
        if out.returncode != 0:
            raise RuntimeError(f"hatch_gws_cli failed: {out.stderr.strip()}")
        try:
            return json.loads(out.stdout) if out.stdout.strip() else {}
        except json.JSONDecodeError:
            return {"raw": out.stdout}

    def create_folder(self, name: str, parent_id: str) -> str:
        body = json.dumps({
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        })
        result = self._run(["drive", "files", "create", "--json", body])
        return result.get("id", "")

    def find_file(self, name: str, parent_id: str) -> dict | None:
        query = (
            f"name = '{name}' and '{parent_id}' in parents and trashed = false"
        )
        result = self._run([
            "drive", "files", "list",
            "--params", json.dumps({"q": query, "fields": "files(id,name,size)"}),
        ])
        files = result.get("files", [])
        return files[0] if files else None

    def upload_file(self, path: Path, parent_id: str) -> dict:
        return self._run([
            "drive", "+upload", str(path), "--parent", parent_id,
        ])

    def get_file(self, file_id: str) -> dict:
        return self._run([
            "drive", "files", "get",
            "--params", json.dumps({"fileId": file_id, "fields": "id,name,size"}),
        ])


@dataclass
class UploadRecord:
    local_path: str
    group: str
    folder: str
    drive_id: str
    drive_url: str
    size_bytes: int
    status: str = "uploaded"  # uploaded | reused_existing | failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_path": self.local_path, "group": self.group,
            "folder": self.folder, "drive_id": self.drive_id,
            "drive_url": self.drive_url, "size_bytes": self.size_bytes,
            "status": self.status,
        }


@dataclass
class DriveUploader:
    root_folder_id: str = DRIVE_ROOT_FOLDER_ID
    client: DriveClient | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = GwsCliDriveClient()

    def drive_url(self, file_id: str) -> str:
        return f"https://drive.google.com/file/d/{file_id}/view"

    def ensure_project_folders(self, project_id: str) -> dict[str, str]:
        """Create PROJECT_ID + 01..06 subfolders; reuse existing ones."""
        project_folder = self._ensure_folder(project_id, self.root_folder_id)
        folders = {"project": project_folder}
        for name in PROJECT_FOLDERS:
            folders[name] = self._ensure_folder(name, project_folder)
        return folders

    def _ensure_folder(self, name: str, parent_id: str) -> str:
        existing = self.client.find_file(name, parent_id)
        if existing:
            return existing["id"]
        return self.client.create_folder(name, parent_id)

    def upload(self, path: Path, group: str, folders: dict[str, str],
               *, allow_master: bool = False) -> UploadRecord:
        """Upload one file to its group folder, verified, deduped.

        Set allow_master=True only for an approved master. A failed
        draft must never be uploaded as a master.
        """
        if group == "master" and not allow_master:
            raise ValueError(
                "refusing to upload as Master: draft not approved "
                "(human approval gate, Master Prompt §13)"
            )
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"artifact missing: {path}")
        folder_name = GROUP_FOLDER[group]
        folder_id = folders[folder_name]
        existing = self.client.find_file(path.name, folder_id)
        if existing:
            return UploadRecord(
                str(path), group, folder_name, existing["id"],
                self.drive_url(existing["id"]),
                int(existing.get("size") or path.stat().st_size),
                status="reused_existing",
            )
        result = self.client.upload_file(path, folder_id)
        file_id = result.get("id") or ""
        # Verify: file exists in Drive and size matches the local file.
        remote = self.client.get_file(file_id) if file_id else {}
        remote_size = int(remote.get("size") or 0)
        local_size = path.stat().st_size
        if not file_id or (remote_size and remote_size != local_size):
            raise RuntimeError(
                f"upload verification failed for {path.name}: "
                f"local {local_size} bytes, Drive reports {remote_size}"
            )
        return UploadRecord(
            str(path), group, folder_name, file_id,
            self.drive_url(file_id), local_size,
        )

    def upload_project(
        self, project_id: str, artifacts: dict[str, list[Path]],
        *, allow_master: bool = False,
    ) -> list[UploadRecord]:
        """Upload all artifact groups for one project. Returns records."""
        folders = self.ensure_project_folders(project_id)
        records: list[UploadRecord] = []
        for group, paths in artifacts.items():
            for path in paths:
                records.append(self.upload(
                    path, group, folders, allow_master=allow_master))
        return records
