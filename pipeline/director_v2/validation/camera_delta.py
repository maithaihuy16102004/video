"""Camera delta and visual similarity calculator across 11 structural dimensions.

Cinematic principle:
  'A CHANGE OF BACKGROUND IS NOT A CHANGE OF SHOT.
   A ZOOM IS NOT A NEW CAMERA ANGLE.
   A DIFFERENT PROP IS NOT A DIFFERENT POSE.'
"""
from __future__ import annotations

import math
from typing import Any

from ..schemas.plan import (
    CAMERA_HEIGHT_ORDINAL,
    ORIENTATION_ANGLE,
    SHOT_SIZE_ORDINAL,
    BodyOrientation,
    CameraHeight,
    Shot,
    ShotType,
)


def compute_shot_similarity(a: Shot | dict[str, Any], b: Shot | dict[str, Any]) -> float:
    """Computes normalized similarity score [0.0..1.0] between two shots.

    Weights (sum to 1.00):
      1. Shot size / framing:      0.16
      2. Camera height + pitch:    0.14
      3. Camera yaw / horizontal:  0.10
      4. Subject position (x, y):  0.12
      5. Subject scale:            0.08
      6. Body orientation:         0.10
      7. Pose family:              0.12
      8. Perspective & VP:         0.10
      9. Depth & FG occlusion:     0.04
     10. Key light direction:      0.04
    """
    def _val(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    # 1. Shot size (0.16)
    st_a = _val(a, "shot_type")
    st_b = _val(b, "shot_type")
    ord_a = SHOT_SIZE_ORDINAL.get(st_a if isinstance(st_a, ShotType) else ShotType(st_a), 3.0) if st_a else 3.0
    ord_b = SHOT_SIZE_ORDINAL.get(st_b if isinstance(st_b, ShotType) else ShotType(st_b), 3.0) if st_b else 3.0
    diff_size = abs(ord_a - ord_b) / 6.0
    score_size = max(0.0, 1.0 - diff_size) * 0.16

    # 2. Camera height & pitch (0.14)
    ch_a = _val(a, "camera_height")
    ch_b = _val(b, "camera_height")
    ord_h_a = CAMERA_HEIGHT_ORDINAL.get(ch_a if isinstance(ch_a, CameraHeight) else CameraHeight(ch_a), 2.0) if ch_a else 2.0
    ord_h_b = CAMERA_HEIGHT_ORDINAL.get(ch_b if isinstance(ch_b, CameraHeight) else CameraHeight(ch_b), 2.0) if ch_b else 2.0
    diff_h = abs(ord_h_a - ord_h_b) / 4.0

    pitch_a = float(_val(a, "camera_pitch", 0.0) or 0.0)
    pitch_b = float(_val(b, "camera_pitch", 0.0) or 0.0)
    diff_pitch = min(1.0, abs(pitch_a - pitch_b) / 45.0)
    score_height = max(0.0, 1.0 - (diff_h * 0.6 + diff_pitch * 0.4)) * 0.14

    # 3. Camera yaw (0.10)
    yaw_a = float(_val(a, "camera_yaw", 0.0) or 0.0)
    yaw_b = float(_val(b, "camera_yaw", 0.0) or 0.0)
    diff_yaw = min(1.0, abs(yaw_a - yaw_b) / 60.0)
    score_yaw = max(0.0, 1.0 - diff_yaw) * 0.10

    # 4. Subject position (x, y) (0.12)
    sx_a = float(_val(a, "subject_x", 0.5) or 0.5)
    sx_b = float(_val(b, "subject_x", 0.5) or 0.5)
    sy_a = float(_val(a, "subject_y", 0.75) or 0.75)
    sy_b = float(_val(b, "subject_y", 0.75) or 0.75)
    dist_pos = math.sqrt((sx_a - sx_b) ** 2 + (sy_a - sy_b) ** 2)
    score_pos = max(0.0, 1.0 - min(1.0, dist_pos / 0.40)) * 0.12

    # 5. Subject scale (0.08)
    scale_a = float(_val(a, "subject_scale", 0.5) or 0.5)
    scale_b = float(_val(b, "subject_scale", 0.5) or 0.5)
    diff_scale = abs(scale_a - scale_b) / max(0.1, max(scale_a, scale_b))
    score_scale = max(0.0, 1.0 - min(1.0, diff_scale)) * 0.08

    # 6. Body orientation (0.10)
    bo_a = _val(a, "body_orientation")
    bo_b = _val(b, "body_orientation")
    ang_a = ORIENTATION_ANGLE.get(bo_a if isinstance(bo_a, BodyOrientation) else BodyOrientation(bo_a)) if bo_a else 0.0
    ang_b = ORIENTATION_ANGLE.get(bo_b if isinstance(bo_b, BodyOrientation) else BodyOrientation(bo_b)) if bo_b else 0.0
    if ang_a is None or ang_b is None:
        score_ori = 0.05
    else:
        diff_ang = abs(ang_a - ang_b)
        if diff_ang > 180.0:
            diff_ang = 360.0 - diff_ang
        score_ori = max(0.0, 1.0 - (diff_ang / 90.0)) * 0.10

    # 7. Pose family (0.12)
    pose_a = str(_val(a, "pose_family", ""))
    pose_b = str(_val(b, "pose_family", ""))
    score_pose = 0.12 if (pose_a and pose_b and pose_a == pose_b) else 0.0

    # 8. Perspective & Vanishing Point (0.10)
    pt_a = str(_val(a, "perspective_type", ""))
    pt_b = str(_val(b, "perspective_type", ""))
    score_pt = 0.05 if pt_a == pt_b else 0.0
    vp_a = _val(a, "vanishing_point_primary")
    vp_b = _val(b, "vanishing_point_primary")
    vpx_a = getattr(vp_a, "x", vp_a.get("x", 0.5) if isinstance(vp_a, dict) else 0.5) if vp_a else 0.5
    vpx_b = getattr(vp_b, "x", vp_b.get("x", 0.5) if isinstance(vp_b, dict) else 0.5) if vp_b else 0.5
    diff_vp = min(1.0, abs(float(vpx_a) - float(vpx_b)) / 0.35)
    score_vp = max(0.0, 1.0 - diff_vp) * 0.05
    score_persp = score_pt + score_vp

    # 9. Depth / FG occlusion (0.04)
    fg_a = float(_val(a, "foreground_occlusion", 0.0) or 0.0)
    fg_b = float(_val(b, "foreground_occlusion", 0.0) or 0.0)
    score_depth = max(0.0, 1.0 - min(1.0, abs(fg_a - fg_b) / 0.30)) * 0.04

    # 10. Key light (0.04)
    kl_a = str(_val(a, "key_light_direction", ""))
    kl_b = str(_val(b, "key_light_direction", ""))
    score_light = 0.04 if kl_a == kl_b else 0.0

    total = (
        score_size + score_height + score_yaw + score_pos + score_scale +
        score_ori + score_pose + score_persp + score_depth + score_light
    )
    return round(min(1.0, max(0.0, total)), 3)
