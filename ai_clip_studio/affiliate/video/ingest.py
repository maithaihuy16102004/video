"""Source ingest gate: URL + authorization, enforced in code.

A source URL is accepted together with its authorization field. The
gate runs BEFORE any network access: UNKNOWN authorization, an
unconfirmed commercial-rights flag, or a malformed URL is refused and
the downloader is never invoked. This is the code-level enforcement
of the rule that no Douyin (or any) video may be downloaded,
processed, or exported without confirmed authorization.

Phase 1: no network downloader is bundled and none is attempted.
``ingest_source`` requires an explicitly injected ``downloader``
callable; with none supplied it refuses with a clear reason. The real
downloader is wired at integration time, only after ATLAS confirms
authorization for a specific source.

Downloaded files land in an immutable store: the filename is derived
from the SHA-256 checksum, an existing file is never overwritten, and
a manifest records the URL, authorization decision, checksum, and
probe metadata next to the file.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .models import AUTHORIZATION_TYPES, export_gate_check
from .probe import ProbeError, probe_source, sha256_file

# Downloader contract: (url, suggested_target_path) -> path of the
# downloaded file. The caller owns transport safety; this module owns
# the authorization gate and the immutable store.
Downloader = Callable[[str, Path], Path]

_CONTAINER_EXT = {
    "mp4": "mp4",
    "mov": "mov",
    "matroska": "mkv",
    "webm": "webm",
    "avi": "avi",
}


class IngestRefused(Exception):
    """Raised when ingest is refused. No download was attempted."""


@dataclass(frozen=True)
class IngestRequest:
    """A request to ingest a remote source video."""
    source_url: str
    authorization_type: str
    commercial_rights_confirmed: bool
    declared_rights_holder: str = ""
    notes: str = ""


@dataclass(frozen=True)
class IngestRecord:
    """The stored result of an accepted ingest."""
    source_url: str
    authorization_type: str
    commercial_rights_confirmed: bool
    local_path: str
    sha256: str
    file_size_bytes: int
    probe: dict[str, Any]
    ingested_at_utc: str
    downloader_name: str
    manifest_path: str
    reused_existing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "authorization_type": self.authorization_type,
            "commercial_rights_confirmed": self.commercial_rights_confirmed,
            "local_path": self.local_path,
            "sha256": self.sha256,
            "file_size_bytes": self.file_size_bytes,
            "probe": self.probe,
            "ingested_at_utc": self.ingested_at_utc,
            "downloader_name": self.downloader_name,
            "manifest_path": self.manifest_path,
            "reused_existing": self.reused_existing,
            "gate": {
                "decision": "allowed",
                "authorization_type": self.authorization_type,
                "commercial_rights_confirmed":
                    self.commercial_rights_confirmed,
            },
        }


def validate_ingest_request(request: IngestRequest) -> list[str]:
    """Return refusal reasons; empty means the gate allows ingest."""
    reasons: list[str] = []
    url = (request.source_url or "").strip()
    if not url:
        reasons.append("source_url is required")
    else:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            reasons.append(
                f"source_url scheme must be http/https, got "
                f"'{parts.scheme or '(none)'}'")
        if not parts.netloc:
            reasons.append("source_url has no host")
        if parts.username or parts.password:
            reasons.append("source_url must not embed credentials")
    if request.authorization_type == "SYNTHETIC_FIXTURE":
        reasons.append(
            "SYNTHETIC_FIXTURE is a local-fixture marker, not a rights "
            "basis for ingesting a remote URL")
    elif request.authorization_type not in AUTHORIZATION_TYPES:
        reasons.append(
            f"unknown authorization_type "
            f"'{request.authorization_type}'")
    else:
        allowed, gate_reasons = export_gate_check(
            request.authorization_type,
            request.commercial_rights_confirmed)
        reasons.extend(gate_reasons)
    return reasons


def store_filename(sha256: str, container: str) -> str:
    """Immutable store name: checksum-derived, never user-supplied."""
    ext = _CONTAINER_EXT.get(container.lower(), "mp4")
    return f"{sha256[:16]}_source.{ext}"


def ingest_source(request: IngestRequest, store_dir: str | Path,
                  downloader: Downloader | None = None,
                  downloader_name: str = "") -> IngestRecord:
    """Gate, download (via the injected downloader), store, manifest.

    The gate is checked first; a refused request never reaches the
    downloader. With no downloader supplied, ingest refuses without
    attempting any network access.
    """
    reasons = validate_ingest_request(request)
    if reasons:
        raise IngestRefused("; ".join(reasons))
    if downloader is None:
        raise IngestRefused(
            "network ingest is not wired in Phase 1: no downloader was "
            "supplied, so no download was attempted. A downloader is "
            "injected at integration time, only after authorization is "
            "confirmed for a specific source.")
    store = Path(store_dir)
    store.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aff_ingest_") as tmp:
        tmp_target = Path(tmp) / "download.bin"
        downloaded = downloader(request.source_url, tmp_target)
        downloaded = Path(downloaded)
        if not downloaded.is_file():
            raise IngestRefused(
                f"downloader '{downloader_name or 'unnamed'}' did not "
                f"produce a file for {request.source_url}")
        checksum = sha256_file(downloaded)
        try:
            info = probe_source(downloaded)
        except ProbeError as exc:
            raise IngestRefused(
                f"downloaded file is not a readable video: {exc}") from exc
        dest = store / store_filename(checksum, info.container)
        manifest_path = dest.with_name(dest.name + ".ingest.json")
        reused = False
        if dest.is_file():
            if sha256_file(dest) != checksum:
                raise IngestRefused(
                    f"store collision at {dest}: existing file has a "
                    f"different checksum; refusing to overwrite")
            reused = True
        else:
            shutil.move(str(downloaded), str(dest))
        record = IngestRecord(
            source_url=request.source_url,
            authorization_type=request.authorization_type,
            commercial_rights_confirmed=(
                request.commercial_rights_confirmed),
            local_path=str(dest),
            sha256=checksum,
            file_size_bytes=dest.stat().st_size,
            probe=info.to_dict(),
            ingested_at_utc=datetime.now(timezone.utc).isoformat(),
            downloader_name=downloader_name,
            manifest_path=str(manifest_path),
            reused_existing=reused,
        )
        if not manifest_path.is_file():
            manifest_path.write_text(
                json.dumps(record.to_dict(), indent=2, ensure_ascii=False)
                + "\n", encoding="utf-8")
        return record


def load_ingest_record(manifest_path: str | Path) -> dict[str, Any]:
    """Read an ingest manifest back (raises on bad JSON)."""
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


__all__ = [
    "Downloader", "IngestRefused", "IngestRequest", "IngestRecord",
    "ingest_source", "load_ingest_record", "store_filename",
    "validate_ingest_request",
]
