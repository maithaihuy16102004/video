"""Content-addressable asset cache.

Prevents duplicate API calls for identical visual requirements.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..schemas.assets import AssetRequirement


class AssetCache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def compute_cache_key(self, req: AssetRequirement, model_name: str) -> str:
        data = {
            "semantic_key": req.semantic_key,
            "description": req.description,
            "aspect": req.aspect_ratio,
            "size": req.image_size,
            "matte": req.matte,
            "model": model_name,
            "historical_constraints": sorted(req.historical_constraints),
        }
        raw = json.dumps(data, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def get(self, cache_key: str) -> Path | None:
        cand = self.cache_dir / f"{cache_key}.png"
        return cand if cand.is_file() and cand.stat().st_size > 0 else None

    def put(self, cache_key: str, image_bytes: bytes) -> Path:
        out = self.cache_dir / f"{cache_key}.png"
        out.write_bytes(image_bytes)
        return out
