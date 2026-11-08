"""Action verb to pose family mapping.

Rule: Contrapposto is NEVER a universal default for all standing scenes;
it is strictly reserved for POSE_RELAXED_STAND_CONTRAPPOSTO.
Every active verb maps to a dedicated kinetic pose family.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .pose_library import PoseLibrary

_LIB: PoseLibrary | None = None


def get_pose_library() -> PoseLibrary:
    global _LIB
    if _LIB is None:
        _LIB = PoseLibrary()
    return _LIB


def map_action_to_pose(
    action_verb: str,
    context_text: str = "",
    allow_contrapposto: bool = False,
) -> tuple[str, str]:
    """Maps action verb and contextual narration to (pose_family, weight_distribution).

    Returns:
      (pose_family_id, weight_distribution_string)
    """
    lib = get_pose_library()
    combined = f"{action_verb} {context_text}".lower().strip()

    if not combined:
        return lib.default_pose_id(), "CENTER_50_50"

    raw_data = json.loads(lib.data_path.read_text(encoding="utf-8"))
    for fam in raw_data.get("families", []):
        fam_id = fam["id"]
        if fam.get("contrapposto") and not allow_contrapposto:
            # Skip contrapposto unless explicitly allowed (e.g. relaxed standing)
            if not any(k in combined for k in ("thư thái", "thong thả", "lounge", "relaxed")):
                continue

        for kw in fam.get("keywords", []):
            if kw and kw in combined:
                return fam_id, fam.get("weight", "CENTER_50_50")

    # Fallback based on simple verbs
    if any(k in combined for k in ("walk", "đi", "bước")):
        return "POSE_WALK_STRIDE", "FRONT_FOOT_60"
    if any(k in combined for k in ("sit", "ngồi")):
        return "POSE_SIT_SLUMP", "SEATED"
    if any(k in combined for k in ("run", "chạy")):
        return "POSE_RUN_SPRINT", "FRONT_FOOT_85"
    if any(k in combined for k in ("speak", "nói", "kể")):
        return "POSE_SPEAK_GESTURE", "FRONT_FOOT_55"

    return lib.default_pose_id(), "CENTER_50_50"
