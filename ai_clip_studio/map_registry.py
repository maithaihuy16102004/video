"""Historical dataset registry — the gate for the commercial map path.

Reads ``assets/maps/registry.json`` (Mai's §4 structure). Only a dataset
whose entry is VERIFIED *and* whose geometry file matches the recorded
SHA-256 checksum may be returned. REJECTED / UNVERIFIED / UNDER_REVIEW
entries, missing files, and checksum mismatches all fail loudly —
the renderer must never silently fall back to an unverified dataset
or to modern borders.

The registry is the single place that decides which historical
geometries the pipeline may draw. Verification verdicts live in the
evidence/verdict docs referenced by each entry; this module enforces
the recorded decision, it does not re-litigate it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "assets" / "maps" / "registry.json"


class RegistryError(ValueError):
    """A dataset cannot be admitted to the production path."""


def _load_registry(registry_path: Path | None = None) -> dict:
    path = Path(registry_path) if registry_path else REGISTRY_PATH
    if not path.exists():
        raise RegistryError(f"map registry not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_dataset(dataset_id: str,
                    registry_path: Path | None = None) -> dict:
    """Return the admitted dataset record for ``dataset_id``.

    The record carries: dataset_id, geometry_path (absolute),
    provenance (dataset/source_url/license/date), attribution (the
    required on-frame credit line), valid_from/valid_to, and the
    metadata dict. Raises RegistryError unless the entry is VERIFIED
    and the geometry checksum matches.
    """
    registry = _load_registry(registry_path)
    base = (Path(registry_path).parent if registry_path
            else REGISTRY_PATH.parent)
    for entry in registry.get("datasets", []):
        if entry.get("dataset_id") != dataset_id:
            continue
        status = entry.get("verification_status")
        if status != "VERIFIED":
            raise RegistryError(
                f"dataset {dataset_id!r} is {status}, not VERIFIED; "
                "refusing to admit it to the production path "
                f"(see {entry.get('verdict_doc')})")
        rel = entry.get("path")
        if not rel:
            raise RegistryError(f"dataset {dataset_id!r} has no geometry path")
        geo_path = (base / rel).resolve()
        if not geo_path.exists():
            raise RegistryError(f"dataset {dataset_id!r} geometry missing: "
                                f"{geo_path}")
        digest = _sha256_file(geo_path)
        if digest != entry.get("geometry_checksum"):
            raise RegistryError(
                f"dataset {dataset_id!r} checksum mismatch: file "
                f"{digest} != registry {entry.get('geometry_checksum')}; "
                "the geometry file changed after verification")
        dataset_dir = geo_path.parent
        metadata = {}
        meta_path = dataset_dir / "metadata.json"
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        attribution = metadata.get("attribution", "")
        return {
            "dataset_id": dataset_id,
            "geometry_path": str(geo_path),
            "provenance": {
                "dataset": entry.get("dataset_id"),
                "source_url": (metadata.get("source_urls") or [""])[0],
                "license": entry.get("license"),
                "date": metadata.get("source_version", ""),
            },
            "attribution": attribution,
            "valid_from": entry.get("valid_from"),
            "valid_to": entry.get("valid_to"),
            "recommended_framing": metadata.get("recommended_framing"),
            "metadata": metadata,
        }
    raise RegistryError(f"unknown dataset {dataset_id!r} in the map registry")


def resolve_for_year(year: int, region: str = "Europe",
                     registry_path: Path | None = None) -> dict:
    """Resolve a VERIFIED dataset covering ``year`` in ``region``.

    Raises RegistryError when no verified dataset covers the request —
    the caller (map spec builder) lets that propagate as the
    MissingHistoricalMapData gate.
    """
    registry = _load_registry(registry_path)
    for entry in registry.get("datasets", []):
        if entry.get("verification_status") != "VERIFIED":
            continue
        if region and entry.get("geographic_region") != region:
            continue
        try:
            start = int(str(entry.get("valid_from", ""))[:4])
            end = int(str(entry.get("valid_to", ""))[:4])
        except ValueError:
            continue
        if start <= year <= end:
            return resolve_dataset(entry["dataset_id"], registry_path)
    raise RegistryError(
        f"no VERIFIED historical dataset covers year {year} "
        f"in region {region!r}")


__all__ = ["REGISTRY_PATH", "RegistryError", "resolve_dataset",
           "resolve_for_year"]
