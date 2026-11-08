"""Autonomous replanner for rejected shots (similarity > 0.72 or stage view violation).

Selects from cinematic camera archetypes to break repetition without human intervention.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schemas.core import NormPoint
from ..schemas.plan import (
    BodyOrientation,
    CameraHeight,
    CameraMotion,
    PerspectiveType,
    Shot,
    ShotType,
)
from .camera_delta import compute_shot_similarity
from .stage_view import is_stage_view

ARCHETYPES_PATH = Path(__file__).resolve().parents[1] / "data" / "camera_archetypes.json"
_ARCHETYPES_CACHE: list[dict[str, Any]] = []


def get_archetypes() -> list[dict[str, Any]]:
    global _ARCHETYPES_CACHE
    if not _ARCHETYPES_CACHE and ARCHETYPES_PATH.exists():
        data = json.loads(ARCHETYPES_PATH.read_text(encoding="utf-8"))
        _ARCHETYPES_CACHE = data.get("archetypes", [])
    return _ARCHETYPES_CACHE


def apply_archetype_to_shot(shot: Shot, archetype: dict[str, Any], mirror: bool = False) -> Shot:
    """Updates a Shot with framing & perspective attributes from an archetype."""
    sx = float(archetype["subject_x"])
    yaw = float(archetype["camera_yaw"])
    vp1 = list(archetype["vp1"])
    vp2 = list(archetype["vp2"]) if archetype.get("vp2") else None

    bo_str = archetype["body_orientation"]
    if mirror:
        sx = 1.0 - sx
        yaw = -yaw
        vp1[0] = 1.0 - vp1[0]
        if vp2:
            vp2[0] = 1.0 - vp2[0]
        if "LEFT" in bo_str:
            bo_str = bo_str.replace("LEFT", "RIGHT")
        elif "RIGHT" in bo_str:
            bo_str = bo_str.replace("RIGHT", "LEFT")

    shot.archetype_id = archetype["id"]
    shot.shot_type = ShotType(archetype["shot_type"])
    shot.camera_height = CameraHeight(archetype["camera_height"])
    shot.camera_yaw = yaw
    shot.camera_pitch = float(archetype["camera_pitch"])
    shot.lens_feel = archetype.get("lens_feel", "35mm")
    shot.camera_motion = CameraMotion(archetype.get("motion", "STATIC"))
    shot.camera_motion_reason = archetype.get("motion_reason", "")

    shot.perspective_type = PerspectiveType(archetype["perspective_type"])
    shot.horizon_y = float(archetype.get("horizon_y", 0.5))
    shot.vanishing_point_primary = NormPoint(x=vp1[0], y=vp1[1])
    shot.vanishing_point_secondary = NormPoint(x=vp2[0], y=vp2[1]) if vp2 else None

    shot.subject_x = sx
    shot.subject_y = float(archetype["subject_y"])
    shot.subject_scale = float(archetype["subject_scale"])
    try:
        shot.body_orientation = BodyOrientation(bo_str)
    except Exception:
        shot.body_orientation = BodyOrientation.THREE_QUARTER_FRONT_RIGHT
    shot.head_direction = archetype.get("head_direction", "FORWARD")
    shot.eyeline = archetype.get("eyeline", "OFF_SCREEN_RIGHT")
    shot.foreground_occlusion = float(archetype.get("foreground_occlusion", 0.0))
    shot.is_stage_view = is_stage_view(shot)
    return shot


def replan_rejected_shot(
    shot: Shot,
    history_shots: list[Shot],
    threshold: float = 0.72,
    window_size: int = 6,
    require_non_stage: bool = True,
) -> tuple[Shot, bool]:
    """Finds best camera archetype to replace rejected shot parameters.

    Returns:
      (updated_shot, True) if replanned successfully,
      (shot, False) if no viable archetype lowered similarity below threshold.
    """
    archetypes = get_archetypes()
    if not archetypes:
        return shot, False

    recent = history_shots[-window_size:] if history_shots else []
    best_candidate: dict[str, Any] | None = None
    best_mirror: bool = False
    best_similarity: float = 1.0

    purpose_str = str(shot.shot_purpose.value if hasattr(shot.shot_purpose, "value") else shot.shot_purpose)

    # Sort archetypes: prefer ones that match the shot's purpose and are not discouraged
    sorted_archetypes = sorted(
        archetypes,
        key=lambda a: (
            1 if a.get("discouraged") else 0,
            0 if purpose_str in a.get("purposes", []) else 1,
        ),
    )

    for arch in sorted_archetypes:
        if arch.get("discouraged") and require_non_stage:
            continue

        for mirror in (False, True):
            # Test-apply onto a copy
            test_shot = shot.model_copy(deep=True)
            apply_archetype_to_shot(test_shot, arch, mirror=mirror)

            if require_non_stage and test_shot.is_stage_view:
                continue

            # Measure max similarity against recent history
            max_sim = max((compute_shot_similarity(test_shot, p) for p in recent), default=0.0)
            if max_sim < best_similarity:
                best_similarity = max_sim
                best_candidate = arch
                best_mirror = mirror
                if max_sim <= (threshold - 0.15):  # Comfortably below threshold
                    break
        if best_similarity <= (threshold - 0.15):
            break

    if best_candidate and (best_similarity <= threshold or best_similarity < shot.visual_similarity_score):
        prev_score = shot.visual_similarity_score
        shot.replan_history.append(f"{shot.archetype_id or 'ORIGINAL'} -> {best_candidate['id']} (sim {prev_score:.2f} -> {best_similarity:.2f})")
        apply_archetype_to_shot(shot, best_candidate, mirror=best_mirror)
        shot.visual_similarity_score = best_similarity
        shot.validator_action = f"REPLANNED_TO_{best_candidate['id']}"
        return shot, True

    return shot, False
