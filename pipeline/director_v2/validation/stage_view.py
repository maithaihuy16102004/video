"""Detection and policy enforcement for dull, presentation-style 'Stage Views'.

A Stage View is defined by:
  - Eye-level camera height (camera_height == EYE_LEVEL, pitch ~= 0)
  - Medium / Medium-Wide / Wide framing
  - Centered or near-centered subject (0.42 <= subject_x <= 0.58)
  - Flat / weak perspective (perspective_type == FLAT or ONE_POINT with center VP)
  - Subject facing directly forward or parallel to image plane (FRONT / PROFILE)
  - Low or no foreground occlusion (foreground_occlusion < 0.10)

Rule: If a Stage View appears >= 2 times in any rolling window of 5 shots, it MUST
be rejected and replaced with an alternative cinematic archetype.
"""
from __future__ import annotations

from typing import Any

from ..schemas.plan import BodyOrientation, CameraHeight, PerspectiveType, Shot, ShotType


def is_stage_view(shot: Shot | dict[str, Any]) -> bool:
    def _val(key: str, default: Any = None) -> Any:
        if isinstance(shot, dict):
            return shot.get(key, default)
        return getattr(shot, key, default)

    ch = str(_val("camera_height", ""))
    if ch and "EYE_LEVEL" not in ch:
        return False

    pitch = abs(float(_val("camera_pitch", 0.0) or 0.0))
    if pitch > 8.0:
        return False

    st = str(_val("shot_type", ""))
    if not any(k in st for k in ("MEDIUM", "WIDE", "STAGE")):
        return False
    if any(k in st for k in ("CLOSE", "POV", "OTS", "INSERT")):
        return False

    sx = float(_val("subject_x", 0.5) or 0.5)
    if not (0.38 <= sx <= 0.62):
        return False

    bo = str(_val("body_orientation", ""))
    if bo and not any(k in bo for k in ("FRONT", "NONE")):
        # If facing 3/4 or away, it's less staged
        if "THREE_QUARTER" in bo or "BACK" in bo:
            return False

    fg = float(_val("foreground_occlusion", 0.0) or 0.0)
    if fg >= 0.15:
        return False

    pt = str(_val("perspective_type", ""))
    if pt and any(k in pt for k in ("THREE_POINT", "WORM", "BIRD", "DEEP")):
        return False

    return True


def check_stage_view_violations(
    shots: list[Shot],
    window_size: int = 5,
    max_allowed: int = 1,
) -> list[int]:
    """Returns list of shot indexes that violate the stage view policy."""
    violations: list[int] = []
    is_stages = [is_stage_view(s) for s in shots]
    for idx, is_stg in enumerate(is_stages):
        if not is_stg:
            continue
        start = max(0, idx - window_size + 1)
        count_in_window = sum(is_stages[start : idx + 1])
        if count_in_window > max_allowed:
            # If intentional repetition is flagged on the shot, allow it
            if not getattr(shots[idx], "intentional_repetition", False):
                violations.append(idx)
    return violations
