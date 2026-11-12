# MIT attribution — measured values adapted from:
#   mromidev/claude-animated-shorts (https://github.com/mromidev/claude-animated-shorts.git)
#   Copyright (c) 2026 Mr omi, MIT License (see ../../THIRD_PARTY_NOTICES.md).
# Sources: references/reports/grade.md, lighting.md, depth.md, motion.md,
# outlines.md, textures.md; templates/bridge/grade.ts, lights.ts, ink.ts,
# lensblur.ts, cast.ts. Values only — no artwork, characters, or scripts.
# MEASUREMENT ONLY: nothing in this module alters a render. Grade presets
# were fitted to the reference channel's look and to the bridge world; the
# source itself warns they over-correct on a re-lit renderer (grade.ts
# header) — re-fit before any use as an applied grade. Timing values come
# from a DIFFERENT reference channel than RicksClips and are marked
# PROPOSED wherever they could conflict with Mai's locked animation values.
# NOT wired into any pipeline, renderer, or server. See
# acceptance_loop/EXTERNAL_REPO_AUDIT_CLAUDE_ANIMATED_SHORTS.md.
"""Look targets: measured reference values + frame measurement helpers.

The external repo measured its reference channel frame by frame (2,164
frames for the grade, 539 for depth, 32,337 for motion) and fitted numbers.
This module freezes the non-conflicting subset as named constants so AI Clip
Studio can *measure* its own frames against the same yardstick, plus the
small pure functions needed to apply the grade curve math and to measure a
frame. It deliberately excludes everything that conflicts with Mai's locked
rules: no character proportions, no face construction, no camera-move
grammar, no vertical-format values.

Sections:
- GRADE: 7-knot tone curves + zone saturation + 3-way tint + vignette.
- LIGHT: two-tone lit/shade/lift values and sky/fog stops.
- DEPTH: thin-lens DOF table, headroom, horizon, camera height.
- INK: world outline widths / angles.
- LUMA: frame-level luma/saturation targets.
- TIMING (PROPOSED): blink / reaction-lead / anticipation / walk values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = [
    "KX",
    "GRADE_DAY",
    "GRADE_GOLDEN",
    "GRADE_DAY_GENTLE",
    "GRADE_GOLDEN_GENTLE",
    "GradeParams",
    "mono_tangents",
    "grade_curve",
    "LIGHT_DAY",
    "LIGHT_GOLDEN",
    "SKY_DAY",
    "SKY_GOLDEN",
    "FOG_DAY",
    "FOG_GOLDEN",
    "DOF_CINF",
    "HEADROOM_Y",
    "HORIZON_Y",
    "CAMERA_HEIGHT_RATIO",
    "INK",
    "LUMA_DAY",
    "LUMA_GOLDEN",
    "SHADOW_RATIOS",
    "TIMING",
    "blink_lid_frames",
    "frames_for_seconds",
    "frame_luma_stats",
    "compare_luma_to_target",
]

# ---------------------------------------------------------------------------
# Grade (grade.md + grade.ts). KX: fixed knot positions of the 7-knot curve.
# GRADE_DAY/GOLDEN: fitted presets (scripts/fit2.py). GRADE_*_GENTLE: the
# round-2 re-fit actually used on the relit world (GRADE_DAY2/GOLDEN2) —
# prefer these as measurement targets; the fitted ones over-brighten.
# ---------------------------------------------------------------------------
KX = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)


@dataclass(frozen=True)
class GradeParams:
    ky: tuple[float, ...]  # 7 curve values at KX
    sat: tuple[float, float, float]  # shadows, mids, highlights
    tint_s: tuple[float, float]  # (Cb, Cr) shadows
    tint_m: tuple[float, float]  # (Cb, Cr) mids
    tint_h: tuple[float, float]  # (Cb, Cr) highlights
    vig: tuple[float, float]  # (strength k, start radius r0)


GRADE_DAY = GradeParams(
    ky=(0.0345, 0.1828, 0.3812, 0.6605, 0.8814, 0.9631, 1.0),
    sat=(0.9831, 1.2727, 1.4573),
    tint_s=(-0.0291, 0.0411),
    tint_m=(0.0376, -0.0104),
    tint_h=(0.0144, -0.0047),
    vig=(0.10, 0.45),
)
GRADE_GOLDEN = GradeParams(
    ky=(0.0311, 0.1877, 0.4017, 0.6754, 0.8750, 0.9582, 1.0),
    sat=(0.8316, 0.8799, 1.7061),
    tint_s=(0.0528, 0.0004),
    tint_m=(0.0583, -0.0003),
    tint_h=(0.0, 0.0),
    vig=(0.16, 0.40),
)
GRADE_DAY_GENTLE = GradeParams(
    ky=(0.0, 0.1, 0.28, 0.6, 0.835, 0.945, 1.0),
    sat=(1.0, 1.05, 1.0),
    tint_s=(0.01, 0.002),
    tint_m=(0.0, 0.0),
    tint_h=(0.006, 0.0),
    vig=(0.12, 0.45),
)
GRADE_GOLDEN_GENTLE = GradeParams(
    ky=(0.0, 0.09, 0.245, 0.54, 0.8, 0.93, 1.0),
    sat=(1.0, 1.12, 1.15),
    tint_s=(0.02, 0.002),
    tint_m=(0.0, 0.0),
    tint_h=(-0.012, 0.006),
    vig=(0.20, 0.40),
)


def mono_tangents(ky: tuple[float, ...] | list[float]) -> list[float]:
    """Fritsch-Carlson monotone tangents for the 7 fixed knots (port of grade.ts monoTangents)."""
    n = len(KX)
    h = [KX[k + 1] - KX[k] for k in range(n - 1)]
    d = [(ky[k + 1] - ky[k]) / h[k] for k in range(n - 1)]
    m = [0.0] * n
    m[0] = d[0]
    m[n - 1] = d[n - 2]
    for k in range(1, n - 1):
        if d[k - 1] * d[k] <= 0:
            m[k] = 0.0
            continue
        w1 = 2 * h[k] + h[k - 1]
        w2 = h[k] + 2 * h[k - 1]
        m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    return m


def _hermite(v: float, x0: float, x1: float, y0: float, y1: float, m0: float, m1: float) -> float:
    h = x1 - x0
    t = (v - x0) / h
    t2, t3 = t * t, t * t * t
    return (
        (2 * t3 - 3 * t2 + 1) * y0
        + (t3 - 2 * t2 + t) * h * m0
        + (-2 * t3 + 3 * t2) * y1
        + (t3 - t2) * h * m1
    )


def grade_curve(v: float, params: GradeParams) -> float:
    """Evaluate the 7-knot monotone cubic Hermite tone curve (port of grade.ts gradeCurve)."""
    v = min(1.0, max(0.0, v))
    ky = params.ky
    m = mono_tangents(ky)
    for k in range(len(KX) - 1):
        if v < KX[k + 1] or k == len(KX) - 2:
            return _hermite(v, KX[k], KX[k + 1], ky[k], ky[k + 1], m[k], m[k + 1])
    return ky[-1]


# ---------------------------------------------------------------------------
# Light (lights.ts final tuned values; lighting.md recipe). Two-tone shading:
# albedo x mix(shade, lit, sunTerm). Values are renderer-agnostic targets;
# the three.js LFB chunk hack that applies them is NOT ported here.
# ---------------------------------------------------------------------------
LIGHT_DAY = {
    "sun_az_deg": 75.0, "sun_el_deg": 48.0,
    "lit": (1.58, 1.50, 1.33), "shade": (0.30, 0.29, 0.36), "lift": (0.05, 0.06, 0.11),
    "lambert": 0.35, "side_k": 0.84, "term": 0.20,
    "char_tint": (1.0, 0.94, 0.92), "char_shade": 0.86, "char_grad": 0.07, "body_grad": 0.20,
    "side_tint": (0.92, 0.90, 0.96),
}
LIGHT_GOLDEN = {
    "sun_az_deg": 6.0, "sun_el_deg": 7.0,
    "lit": (1.50, 0.68, 0.24), "shade": (0.15, 0.15, 0.30), "lift": (0.04, 0.06, 0.17),
    "lambert": 0.35, "side_k": 0.84, "term": 0.07,
    "char_tint": (1.0, 0.78, 0.56), "char_shade": 0.88, "char_grad": 0.10, "body_grad": 0.25,
    "side_tint": (0.85, 0.80, 0.95),
}

# Sky: 5 colour stops by elevation in degrees (LOOK table, lights.ts).
# depth.md: 2-stop mixes through grey are the bug — use >= 4 stops.
SKY_DAY = {"elevations_deg": (0, 3, 8, 16, 40),
           "colors": ("#b8d0ec", "#9db8e2", "#7ba0d6", "#5a8ccb", "#3373cc")}
SKY_GOLDEN = {"elevations_deg": (0, 4, 14, 32, 40),
              "colors": ("#ffc47c", "#f7a878", "#e08a90", "#a87a9e", "#8a6f8a")}
# Fog colour = horizon colour; linear fog near -> far in metres (depth.md).
FOG_DAY = {"color": "#b8d0ec", "near_m": 25.0, "far_m": 300.0}
FOG_GOLDEN = {"color": "#efb489", "near_m": 50.0, "far_m": 380.0}

# ---------------------------------------------------------------------------
# Depth (depth.md recipe + story.ts DOF table). C_inf = blur disc radius at
# infinity in px at 1080p output height scaling; focus on the eyes. NO rack
# focus inside shots (whole-frame blur pulses at cuts only) — consistent
# with the fixed-camera rule.
# ---------------------------------------------------------------------------
DOF_CINF = {"close_up": 13.0, "medium": 13.0, "full_shot": 8.0, "wide": 5.0,
            "insert": 13.0, "foreground": 19.5, "aerial": 0.0}
HEADROOM_Y = {"close_up": 0.28, "medium": 0.35, "full_shot": 0.38, "wide": 0.50}
HORIZON_Y = 0.45
CAMERA_HEIGHT_RATIO = 0.79  # median camera height as a fraction of character height; 82% eye level

# ---------------------------------------------------------------------------
# Ink (ink.ts final DEF; outlines.md recipe). Widths in px at 1920 output
# height, scaled with output height. World-geometry edges only — character
# outlines are separate drawn strokes and are NOT covered here.
# ---------------------------------------------------------------------------
INK = {
    "color": "#030303", "strength": 1.0,
    "width_near_px": 5.1, "width_far_px": 3.3, "dist_near_m": 6.0, "dist_far_m": 90.0,
    "crease_scale": 0.8, "depth_lo": 0.01, "depth_hi": 0.03,
    "angle_lo_deg": 35.0, "angle_hi_deg": 50.0,
    "concave_gain": 0.7, "far_opacity": 0.95, "fade_near_m": 150.0, "fade_far_m": 450.0,
}

# ---------------------------------------------------------------------------
# Frame-level luma targets (grade.md, 2,164 reference frames) + shadow ratios
# (lighting.md). Use compare_luma_to_target() to measure a frame against them.
# ---------------------------------------------------------------------------
LUMA_DAY = {"median_y": 0.571, "p99_y": 0.967, "non_ink_p5_y": 0.234,
            "lit_chroma_p50": 34.0, "lit_chroma_p90": 55.0, "vignette_corner_centre": 0.86}
LUMA_GOLDEN = {"median_y": 0.516}
SHADOW_RATIOS = {
    "day_shade_over_lit_y": (0.49, 0.52),  # wood, day
    "sunset_shade_over_lit_y": (0.15, 0.27),
    "sunset_blue_ratio": (1.35, 3.04),  # B channel replacement colour, not additive light
    "lit_over_shadow_linear": (2.8, 4.4),
}

# ---------------------------------------------------------------------------
# TIMING — PROPOSED values from motion.md / cast.ts. Different reference
# channel than RicksClips; the rig's locked walk values (stride 0.25 H,
# lean 0.12 rad, bob 0.015) take precedence on conflict. These constants
# document the external measurements for a future comparison, with fps
# conversion helpers so 30 fps frame counts translate to 24 fps correctly.
# ---------------------------------------------------------------------------
TIMING = {
    # Blink: 4-frame pattern half/shut/shut/half at 30 fps; gaps 0.5-2.3 s;
    # one blink across every expression swap (shut frames hide the swap).
    "blink_lid_pattern": (0.5, 1.0, 1.0, 0.5),
    "blink_gap_seconds": (0.5, 2.3),
    "blink_source_fps": 30,
    # Reactions land 0-3 frames BEFORE the word onset; LEAD = 2 frames.
    "reaction_lead_frames_at_30fps": 2,
    # Anticipation: jump 2-3 f crouch; spear 3 f lower + ~6 f hold + 1 f
    # thrust; impact flash + 4-5 f ring. Frame counts at 30 fps.
    "anticipation_jump_crouch_frames": (2, 3),
    "anticipation_thrust_frames": (3, 6, 1),
    "impact_ring_frames": (4, 5),
    # Walk (studied channel): step 9-12 f at 30 fps; bob 3-7% of height,
    # lowest at contact; lean 1 deg passing -> 5-7 deg at contact; stance
    # foot planted (<= 1.1 px/frame while the ground moves 7.2 px/frame).
    "walk_step_frames_at_30fps": (9, 12),
    "walk_bob_frac_height": (0.03, 0.07),
    "walk_lean_deg": (1.0, 7.0),
    # Impact shake: sign flips every frame (15 Hz), ~3 px offset at 720p,
    # gone in 6-8 frames (kickAt 7-frame decay). A shake is a within-shot
    # camera effect — needs Mai's approval before any use (fixed-camera rule).
    "impact_shake_frames": (6, 8),
}


def frames_for_seconds(seconds: float, fps: float) -> int:
    """Frame count for a duration at ``fps`` (round-half-up, min 1)."""
    return max(1, int(math.floor(seconds * fps + 0.5)))


def blink_lid_frames(fps: float) -> tuple[float, ...]:
    """Blink lid pattern resampled to ``fps``.

    The source pattern is 4 frames at 30 fps (133 ms). At 24 fps the same
    133 ms is ~3.2 frames, so the pattern is returned time-stretched to the
    nearest whole frame count (3 frames at 24 fps: half/shut/half), keeping
    the total blink duration, not the frame count. The pattern values are
    lid closure 0 (open) .. 1 (shut).
    """
    pattern = TIMING["blink_lid_pattern"]
    src_fps = TIMING["blink_source_fps"]
    dur = len(pattern) / src_fps
    n = frames_for_seconds(dur, fps)
    if n == len(pattern):
        return tuple(float(v) for v in pattern)
    # Resample by nearest source index so endpoints stay half-closed.
    out = []
    for i in range(n):
        src = min(len(pattern) - 1, int(round(i * (len(pattern) - 1) / max(n - 1, 1))))
        out.append(float(pattern[src]))
    return tuple(out)


def frame_luma_stats(rgb: np.ndarray) -> dict:
    """Mean/std/p2/p98 luma + mean saturation for one RGB frame (uint8)."""
    arr = np.asarray(rgb)
    if arr.ndim != 3 or arr.shape[-1] != 3:
        raise ValueError(f"expected (H, W, 3) frame, got shape {arr.shape}")
    f32 = arr.astype(np.float32) / 255.0
    luma = f32 @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    mx = f32.max(-1)
    mn = f32.min(-1)
    sat = np.where(mx > 0.06, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    flat = luma.reshape(-1)
    return {
        "mean": float(flat.mean()),
        "std": float(flat.std()),
        "p2": float(np.percentile(flat, 2)),
        "p98": float(np.percentile(flat, 98)),
        "median": float(np.median(flat)),
        "sat_mean": float(sat.mean()),
    }


def compare_luma_to_target(stats: dict, light: str = "day") -> dict:
    """Delta between measured frame stats and the reference luma targets.

    Returns ``{key: {"measured": ..., "target": ..., "delta": ...}}`` for the
    keys the target defines. Positive delta = brighter than the reference.
    Measurement only — no verdict.
    """
    target = LUMA_DAY if light == "day" else LUMA_GOLDEN
    key_map = {"median_y": "median", "p99_y": "p98", "non_ink_p5_y": "p2"}
    out = {}
    for tkey, skey in key_map.items():
        if tkey in target and skey in stats:
            out[tkey] = {
                "measured": float(stats[skey]),
                "target": float(target[tkey]),
                "delta": float(stats[skey]) - float(target[tkey]),
            }
    return out
