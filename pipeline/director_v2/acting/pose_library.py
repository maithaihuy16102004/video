"""Pose Library and Stickman Rig interfaces for Phase 1 and Phase 2.

All stickman character rendering is procedural / vector rig driven.
Gemini NEVER paints the protagonist from scratch per shot.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from ..schemas.manifest import RigPlacement


class StickmanRig(Protocol):
    """Protocol implemented by vector/procedural stickman rigs (PyCairo or Motion Canvas)."""

    def rig_id(self) -> str:
        ...

    def evaluate_pose(
        self,
        pose_family: str,
        action_verb: str,
        t: float = 0.0,
    ) -> dict[str, Any]:
        """Returns joint coordinates / skeletal angles at normalized time t in [0..1]."""
        ...


class PoseLibrary:
    """Manages pose definitions, keywords, and joint weight distributions."""

    def __init__(self, data_path: Path | None = None):
        if data_path is None:
            data_path = Path(__file__).resolve().parents[1] / "data" / "pose_families.json"
        self.data_path = data_path
        self._families: dict[str, dict[str, Any]] = {}
        self._default = "POSE_ALERT_STAND"
        self._load()

    def _load(self) -> None:
        if self.data_path.exists():
            raw = json.loads(self.data_path.read_text(encoding="utf-8"))
            self._default = raw.get("default", "POSE_ALERT_STAND")
            for item in raw.get("families", []):
                self._families[item["id"]] = item

    def get_pose(self, pose_id: str) -> dict[str, Any] | None:
        return self._families.get(pose_id)

    def default_pose_id(self) -> str:
        return self._default

    def is_contrapposto_allowed(self, pose_id: str) -> bool:
        family = self.get_pose(pose_id)
        if not family:
            return False
        return bool(family.get("contrapposto", False))

    def all_pose_ids(self) -> list[str]:
        return list(self._families.keys())
