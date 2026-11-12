"""Overnight delivery: Drive folder structure for the mission.

Root: OVERNIGHT_2026-11-12_AI_CLIP_STUDIO under the Drive root
(1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm). Per project:

  <PROJECT>/
    01_SCRIPT/       source script + script hash
    02_STORYBOARD/   storyboard stills + contact sheet
    03_AUDIO/        mixed audio + voice wavs + audio plan
    04_DRAFT/        rendered MP4 (labelled FAILED_QA when QA failed)
    05_QA_REPORTS/   QA report + manifest + renderer info + job record
    06_MASTER/       EMPTY — no Master without Mai's explicit approval

Every upload is verified with drive files get (id, name, size,
parents) and the size must match the local file. Failed drafts may
be uploaded but are labelled FAILED_QA in the file name.
"""
from __future__ import annotations

import json
from pathlib import Path

from .drive_uploader import (
    DRIVE_ROOT_FOLDER_ID, GwsCliDriveClient, PROJECT_FOLDERS,
)

OVERNIGHT_FOLDER_NAME = "OVERNIGHT_V9_2026-11-12"


def ensure_overnight_root(client: GwsCliDriveClient | None = None) -> str:
    """Create (or reuse) the overnight folder under the Drive root."""
    client = client or GwsCliDriveClient()
    existing = client.find_file(OVERNIGHT_FOLDER_NAME, DRIVE_ROOT_FOLDER_ID)
    if existing:
        return existing["id"]
    return client.create_folder(OVERNIGHT_FOLDER_NAME, DRIVE_ROOT_FOLDER_ID)


def ensure_project_folders(client: GwsCliDriveClient, overnight_id: str,
                           project_name: str) -> dict[str, str]:
    """Create <PROJECT>/ + 01..06 subfolders under the overnight root.
    06_MASTER is created empty on purpose."""
    project = client.find_file(project_name, overnight_id)
    project_id = project["id"] if project else client.create_folder(
        project_name, overnight_id)
    folders = {"project": project_id}
    for name in PROJECT_FOLDERS:
        existing = client.find_file(name, project_id)
        folders[name] = (existing["id"] if existing
                         else client.create_folder(name, project_id))
    return folders


def upload_verified(client: GwsCliDriveClient, path: Path,
                    parent_id: str) -> dict:
    """Upload one file and verify it with drive files get."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"artifact missing: {path}")
    existing = client.find_file(path.name, parent_id)
    if existing:
        file_id = existing["id"]
    else:
        result = client.upload_file(path, parent_id)
        file_id = result.get("id", "")
    remote = client.get_file(file_id) if file_id else {}
    remote_size = int(remote.get("size") or 0)
    local_size = path.stat().st_size
    if not file_id or remote_size != local_size:
        raise RuntimeError(
            f"upload verification failed for {path.name}: local "
            f"{local_size} bytes, Drive reports {remote_size}")
    return {"file_id": file_id,
            "url": f"https://drive.google.com/file/d/{file_id}/view",
            "name": path.name, "size_bytes": remote_size,
            "parents": remote.get("parents", [parent_id])}


def deliver_project(job_dir: Path, project_name: str, *,
                    qa_failed: bool = False,
                    client: GwsCliDriveClient | None = None) -> dict:
    """Upload one finished job's artifacts into the overnight folder
    structure. Returns the delivery record (folder ids + per-file
    Drive ids/sizes). 06_MASTER is left empty by design."""
    job_dir = Path(job_dir)
    client = client or GwsCliDriveClient()
    overnight_id = ensure_overnight_root(client)
    folders = ensure_project_folders(client, overnight_id, project_name)
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    records: dict[str, dict] = {}

    def put(group_folder: str, path: Path, name: str | None = None):
        target = path
        if name is not None and path.name != name:
            # Copy to a temp name for the upload (Drive dedups by name).
            import shutil
            target = job_dir / "_delivery" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        records[f"{group_folder}/{target.name}"] = upload_verified(
            client, target, folders[group_folder])

    # 01_SCRIPT
    put("01_SCRIPT", job_dir / "script.txt")
    (job_dir / "script_hash.txt").write_text(
        job["script_hash"] + "\n", encoding="utf-8")
    put("01_SCRIPT", job_dir / "script_hash.txt")
    # 02_STORYBOARD
    storyboard_dir = job_dir / "storyboard"
    if storyboard_dir.exists():
        for still in sorted(storyboard_dir.rglob("still.png")):
            put("02_STORYBOARD", still,
                name=f"{still.parent.name}_still.png")
    put("02_STORYBOARD", job_dir / "contact_sheet.png")
    # 03_AUDIO
    put("03_AUDIO", job_dir / "audio" / "mix.wav")
    put("03_AUDIO", job_dir / "audio_plan.json")
    for wav in sorted((job_dir / "voices").glob("*.wav")):
        put("03_AUDIO", wav)
    # 04_DRAFT
    mp4 = Path(job["mp4"]["path"])
    draft_name = mp4.name
    if qa_failed:
        draft_name = mp4.stem + "_FAILED_QA.mp4"
    put("04_DRAFT", mp4, name=draft_name)
    # 05_QA_REPORTS
    put("05_QA_REPORTS", job_dir / "QA_REPORT.md")
    put("05_QA_REPORTS", job_dir / "manifest.json")
    put("05_QA_REPORTS", job_dir / "renderer_info.json")
    put("05_QA_REPORTS", job_dir / "job.json")
    put("05_QA_REPORTS", job_dir / "scene_package.json")
    put("05_QA_REPORTS", job_dir / "timeline.json")
    # 06_MASTER: intentionally left empty.
    return {
        "project": project_name,
        "overnight_folder_id": overnight_id,
        "project_folder_id": folders["project"],
        "folders": folders,
        "files": records,
        "master_folder_empty": True,
    }
