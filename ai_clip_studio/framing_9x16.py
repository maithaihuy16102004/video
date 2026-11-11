"""9:16 vertical framing for YouTube Shorts (§8) — a framing of its own,
not a blind crop of 16:9.

Two paths, in priority order:

1. **Re-render from the 3D scene (the right path).**
   ``vertical_camera_for_shot(shot, camera)`` returns a
   ``PerspectiveCamera`` with aspect 9:16, moved closer to the subject
   so the subject keeps its screen size in the narrow frame, and with
   the shot's own framing notes (an establishing shot keeps more
   distance and accepts losing the sides; a close-up barely moves).
   Render the same scene with this camera and the 9:16 video is a real
   vertical staging, not a crop.

2. **Crop of an already-rendered 16:9 master (fallback only).**
   ``vertical_crop_for_shot(shot, focus_xy)`` returns the 608x1080
   window centred on the shot's focus point (clamped inside the frame)
   plus the vertical caption safe zone. It keeps the focus in frame,
   but it CANNOT recover picture that was never rendered — a wide
   establishing shot cropped to 9:16 loses its sides, and the result
   says so in ``reframe_note``.

Caption layout for vertical differs from 16:9: captions sit in the
lower third but above the bottom 8% (thumb / UI zone), and the safe
zone is narrower (side margins 6% instead of 10%).
"""
from __future__ import annotations

from .renderer25d.camera import PerspectiveCamera

FRAME_16X9 = (1920, 1080)
VERTICAL_SIZE = (608, 1080)  # 1080 * 9/16 = 607.5 -> 608
VERTICAL_ASPECT = 9 / 16

# How much closer the vertical camera dollies (fraction of the
# camera-to-target distance) per shot type, so the subject keeps its
# screen size in the narrow frame.
_DOLLY_BY_SHOT = {
    "establishing": 0.10,   # keep distance: the space matters
    "medium": 0.30,
    "close_up": 0.45,
    "extreme_close_up": 0.50,
    "over_the_shoulder": 0.30,
    "reaction": 0.45,
    "object_insert": 0.45,
    "tracking": 0.30,
    "shot_reverse_shot": 0.30,
}


def vertical_camera_for_shot(shot, camera: PerspectiveCamera) -> dict:
    """A 9:16 camera for re-rendering this shot from the 3D scene."""
    shot_type = (shot or {}).get("shot_type", "medium")
    dolly = _DOLLY_BY_SHOT.get(shot_type, 0.30)
    pos, tgt = camera.position, camera.target
    new_pos = tuple(p + (t - p) * dolly for p, t in zip(pos, tgt))
    vertical = PerspectiveCamera(new_pos, tgt, camera.fov_deg,
                                 VERTICAL_ASPECT, camera.near, camera.far,
                                 camera.up)
    note = ("vertical re-render: subject reframed for 9:16"
            if shot_type != "establishing" else
            "vertical re-render: establishing loses the sides in 9:16 — "
            "consider a closer staging or a vertical-only wide")
    return {"camera": vertical, "aspect": VERTICAL_ASPECT,
            "size": VERTICAL_SIZE, "dolly_fraction": dolly,
            "reframe_note": note}


def vertical_crop_for_shot(shot, focus_xy, frame=FRAME_16X9) -> dict:
    """608x1080 crop window for an already-rendered 16:9 master.

    Centred on the shot's focus point (clamped inside the frame).
    ``focus_kept`` is False when the focus had to be clamped away —
    the crop then does NOT contain the intended subject centre.
    """
    w, h = frame
    cw, ch = VERTICAL_SIZE
    cx, cy = focus_xy if focus_xy is not None else (w / 2.0, h / 2.0)
    left = min(max(cx - cw / 2.0, 0.0), w - cw)
    top = 0.0  # full height is kept; only the sides are cut
    focus_kept = abs((left + cw / 2.0) - cx) < 1.0
    # vertical caption safe zone: lower third, above the bottom 8%
    caption_zone = {"x0": int(w * 0.06), "x1": int(w * 0.94),
                    "y0": int(h * 0.68), "y1": int(h * 0.92)}
    shot_type = (shot or {}).get("shot_type", "medium")
    note = ("crop fallback: focus kept in frame"
            if focus_kept else
            "crop fallback: focus was outside the 9:16 window and had "
            "to be clamped — re-render vertically instead")
    if shot_type == "establishing":
        note += "; establishing loses its sides in a 9:16 crop"
    return {"crop": (int(round(left)), int(round(top)),
                     int(round(left + cw)), int(round(top + ch))),
            "size": VERTICAL_SIZE, "focus_kept": focus_kept,
            "caption_zone": caption_zone, "reframe_note": note}
