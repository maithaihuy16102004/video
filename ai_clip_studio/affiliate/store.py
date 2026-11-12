"""Affiliate project store — JSON persistence + real stage status.

Projects live as one JSON file each under a root directory (default:
``<video-16x9-v2>/jobs/affiliate/``), next to the Story Studio jobs
but in their own namespace. Stage records carry REAL status and
timestamps — progress is never simulated; a stage is "running" only
while its worker thread is actually executing it.

The store is deliberately boring: no database, no new dependency.
ATLAS may replace it with a DB at integration without changing the
API surface used here.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import AffiliateProject, parse_project

STAGES = (
    "upload",
    "analysis",
    "ocr",
    "transcription",
    "translation",
    "script",
    "script_approval",
    "voice",
    "subtitles",
    "edit",
    "mix",
    "render",
    "qa",
    "export",
    "marketing",
    "drive_upload",
)

STAGE_LABELS_VI = {
    "upload": "Tải video lên",
    "analysis": "Phân tích AI",
    "ocr": "Nhận diện chữ Trung",
    "transcription": "Nhận diện giọng nói",
    "translation": "Dịch sang tiếng Việt",
    "script": "Viết kịch bản",
    "script_approval": "Duyệt kịch bản",
    "voice": "Lồng tiếng VieNeu-TTS",
    "subtitles": "Phụ đề tiếng Việt",
    "edit": "Biên tập video",
    "mix": "Trộn âm thanh",
    "render": "Render",
    "qa": "Kiểm tra chất lượng",
    "export": "Xuất video",
    "marketing": "Gói tiếp thị",
    "drive_upload": "Tải lên Google Drive",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_store_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "jobs" / "affiliate"


class AffiliateStore:
    """Thread-safe JSON store for affiliate projects."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else default_store_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, project_id: str) -> Path:
        safe = "".join(c for c in project_id if c.isalnum() or c in "-_")
        if not safe or safe != project_id:
            raise ValueError(f"invalid project_id {project_id!r}")
        return self.root / f"{safe}.json"

    def project_dir(self, project_id: str) -> Path:
        """Working directory for a project's artifacts."""
        directory = self.root / project_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def create(self, project: AffiliateProject) -> AffiliateProject:
        with self._lock:
            if self._path(project.project_id).exists():
                raise ValueError(f"project {project.project_id} already exists")
            if not project.stages:
                project.stages = [
                    {"stage": name, "status": "queued",
                     "detail": "", "updated_at": _now_iso()}
                    for name in STAGES]
            if not project.created_at:
                project.created_at = _now_iso()
            self._write_locked(project)
            return project

    def new_project_id(self) -> str:
        return f"aff_{uuid.uuid4().hex[:12]}"

    def get(self, project_id: str) -> AffiliateProject | None:
        path = self._path(project_id)
        if not path.exists():
            return None
        with self._lock:
            data = json.loads(path.read_text(encoding="utf-8"))
        return parse_project(data)

    def save(self, project: AffiliateProject) -> None:
        with self._lock:
            self._write_locked(project)

    def _write_locked(self, project: AffiliateProject) -> None:
        data = project.to_dict()
        self._path(project.project_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def list_projects(self) -> list[dict[str, Any]]:
        """Project history, newest first (by created_at, then id)."""
        items = []
        for path in sorted(self.root.glob("aff_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            stages = {s["stage"]: s["status"] for s in data.get("stages", [])}
            items.append({
                "project_id": data.get("project_id", path.stem),
                "project_name": data.get("project_name", ""),
                "created_at": data.get("created_at", ""),
                "product_name": (data.get("product") or {}).get("product_name", ""),
                "stages": stages,
                "export_profile": (data.get("export_profile") or {}).get("profile", ""),
            })
        items.sort(key=lambda item: (item["created_at"], item["project_id"]),
                   reverse=True)
        return items

    def set_stage(self, project_id: str, stage: str, status: str,
                  detail: str = "") -> None:
        """Record a REAL stage transition (queued/running/done/failed/
        skipped). Raises on unknown stage/status — no silent typos."""
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage!r}")
        if status not in ("queued", "running", "done", "failed", "skipped"):
            raise ValueError(f"unknown stage status {status!r}")
        with self._lock:
            path = self._path(project_id)
            if not path.exists():
                raise ValueError(f"project not found: {project_id}")
            data = json.loads(path.read_text(encoding="utf-8"))
            stages = data.setdefault("stages", [])
            for record in stages:
                if record["stage"] == stage:
                    record["status"] = status
                    record["detail"] = detail
                    record["updated_at"] = _now_iso()
                    break
            else:
                stages.append({"stage": stage, "status": status,
                               "detail": detail, "updated_at": _now_iso()})
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
