"""Deterministic local B-roll resolver.

It prefers an explicit asset path, then uses a sidecar manifest with semantic
tags.  A zero-score match returns no B-roll instead of silently showing an
unrelated image, which was the old behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path

from production_quality import normalize_topic_key


class LocalAssetResolver:
    def __init__(self, asset_dir: str | Path):
        self.asset_dir = Path(asset_dir)
        self.used: set[Path] = set()
        manifest_path = self.asset_dir / "manifest.json"
        self.manifest = {}
        if manifest_path.exists():
            self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    def resolve(self, visual: dict, allow_reuse: bool = False) -> Path | None:
        explicit = visual.get("asset_path") or visual.get("b_roll_path")
        if explicit:
            path = Path(explicit).expanduser().resolve()
            if path.exists():
                self.used.add(path)
                return path

        query = normalize_topic_key(str(visual.get("b_roll_prompt", "")))
        query_tokens = set(query.split("_"))
        candidates: list[tuple[int, Path]] = []
        for raw_name, metadata in self.manifest.items():
            path = (self.asset_dir / raw_name).resolve()
            if not path.exists() or (path in self.used and not allow_reuse):
                continue
            tags = metadata.get("tags", []) if isinstance(metadata, dict) else metadata
            haystack = normalize_topic_key(" ".join([raw_name, *map(str, tags)]))
            score = len(query_tokens & set(haystack.split("_")))
            if score:
                candidates.append((score, path))
        if not candidates:
            return None
        path = max(candidates, key=lambda item: (item[0], str(item[1])))[1]
        self.used.add(path)
        return path
