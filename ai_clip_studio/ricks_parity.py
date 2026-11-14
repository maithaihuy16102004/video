"""Ricks-style parity scorecard: measure a rendered MP4 against the
reference targets derived from the @RicksClips3000 channel study.

Why this module exists
----------------------
"90% giống Ricks Clips" is not a feeling; it has to be a number that a
render can fail. Every dimension below is measured from the actual
decoded frames (or from the shot plan the renderer already produced),
compared with a target band, and scored 0-100. The overall score is the
weighted mean of the *measured* dimensions only: a dimension that could
not be measured is reported as ``None`` and never silently counted as a
pass.

Targets come from the channel study already encoded in this repo
(``youtube_16x9/config/youtube_16x9.json``: shot band 3.0-6.5 s, target
4.5 s, caption <= 2 lines / 42 chars, safe action 84%, luminance floors)
plus ``docs/CINEMATIC_ENGINE_CONTRACTS.md`` (hard cuts, static anchored
camera, head ratio 0.34). Nothing here copies channel artwork.

Usage
-----
    python -m ai_clip_studio.ricks_parity rendered.mp4 [--plan plan.json]

A plan (optional) is what the renderer knows and pixels cannot show::

    {"shots": [{"index": 0, "a": 0, "b": 120, "framing": "wide",
                "characters": [{"name": "A", "head_ratio": 0.34,
                                "bbox": [x0, y0, x1, y1]}]}],
     "captions": [{"font_px": 64, "lines": 2, "max_chars": 42,
                   "y_frac": 0.82}]}
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .frame_qa import (
    analyze_frames,
    decode_frames,
    probe_specs,
)

#: Reference targets (channel study). Bands, not single values: the
#: channel is not metronomic, so a render inside the band is correct.
TARGETS = {
    "width": 1920,
    "height": 1080,
    "fps_band": (24.0, 30.0),
    "duration_band_sec": (20.0, 60.0),
    "shot_band_sec": (3.0, 6.5),
    "shot_ideal_sec": 4.5,
    "min_cuts": 4,
    "luma_floor": 0.38,
    "contrast_floor": 0.06,
    "motion_floor": 0.35,       # mean |frame diff| per shot, 0..255
    "motion_ceiling": 18.0,     # above this the shot is unreadable churn
    "max_held_fraction": 0.25,
    "caption_font_px": 64,
    "caption_max_lines": 2,
    "caption_max_chars": 42,
    "caption_y_band": (0.70, 0.92),
    "head_ratio": 0.34,
    "head_ratio_tol": 0.06,
    "safe_action_margin": 0.08,
}

#: Weights sum to 1.0 over the dimensions that can be measured from
#: pixels alone; plan-only dimensions are scored when a plan is given
#: and their weight is redistributed when it is not.
WEIGHTS = {
    "format": 0.10,
    "pacing": 0.22,
    "cut_grammar": 0.10,
    "motion": 0.18,
    "lighting": 0.16,
    "framing_variety": 0.10,
    "captions": 0.07,
    "characters": 0.07,
}

PLAN_DIMENSIONS = ("framing_variety", "captions", "characters")


@dataclass
class Dimension:
    name: str
    score: float | None
    measured: object
    target: object
    weight: float
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": None if self.score is None else round(self.score, 2),
            "measured": self.measured,
            "target": self.target,
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass
class ParityReport:
    video: str
    dimensions: list[Dimension] = field(default_factory=list)
    overall: float | None = None
    passed: bool = False

    def to_dict(self) -> dict:
        return {
            "video": self.video,
            "overall": None if self.overall is None else round(self.overall, 2),
            "passed": self.passed,
            "dimensions": [d.to_dict() for d in self.dimensions],
        }

    def failing(self) -> list[Dimension]:
        return [d for d in self.dimensions if d.score is not None and d.score < 90.0]


# --------------------------------------------------------------------------
# scoring primitives
# --------------------------------------------------------------------------

def band_score(value: float, lo: float, hi: float, ideal: float | None = None) -> float:
    """100 inside ``[lo, hi]`` (peaking at ``ideal``), decaying outside.

    A dead-band metric must not punish being merely inside the band: the
    score is 100 anywhere in ``[lo, hi]`` and loses 100 points over a
    full band-width of overshoot outside it, so a value one band away
    from the allowed range scores 0.
    """
    if hi <= lo:
        raise ValueError(f"empty band ({lo}, {hi})")
    width = hi - lo
    if lo <= value <= hi:
        if ideal is None:
            return 100.0
        # Gentle preference for the ideal inside the band: at most a
        # 10-point penalty for sitting on an edge.
        return 100.0 - 10.0 * (abs(value - ideal) / max(width / 2.0, 1e-9))
    overshoot = (lo - value) if value < lo else (value - hi)
    return max(0.0, 100.0 * (1.0 - overshoot / width))


def fraction_score(fraction: float) -> float:
    """100 * fraction, clamped to 0..100."""
    return max(0.0, min(100.0, 100.0 * float(fraction)))


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------

def _shot_ranges_from_cuts(diff: np.ndarray, n_frames: int) -> list[dict]:
    """Shot ranges from cut spikes in the frame-diff signal."""
    if n_frames <= 1:
        return [{"id": 0, "a": 0, "b": max(1, n_frames)}]
    med = float(np.median(diff)) if len(diff) else 0.0
    threshold = max(12.0, 4.0 * med + 2.0)
    cuts = [int(i) + 1 for i in range(len(diff)) if float(diff[i]) >= threshold]
    bounds = [0] + cuts + [n_frames]
    shots = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        if b > a:
            shots.append({"id": i, "a": a, "b": b})
    return shots or [{"id": 0, "a": 0, "b": n_frames}]


def _parse_fps(specs: dict) -> float:
    rate = specs.get("r_frame_rate") or "0/1"
    try:
        num, den = str(rate).split("/")
        value = float(num) / float(den or 1)
    except (TypeError, ValueError, ZeroDivisionError):
        value = 0.0
    return value if value > 0 else 24.0


def _score_format(specs: dict, fps: float) -> Dimension:
    w, h = specs.get("width"), specs.get("height")
    duration = float(specs.get("duration") or 0.0)
    ok_res = (w, h) == (TARGETS["width"], TARGETS["height"])
    res_score = 100.0 if ok_res else 40.0
    fps_score = band_score(fps, *TARGETS["fps_band"])
    dur_score = band_score(duration, *TARGETS["duration_band_sec"])
    score = (res_score + fps_score + dur_score) / 3.0
    return Dimension(
        "format", score,
        {"width": w, "height": h, "fps": round(fps, 3), "duration_sec": round(duration, 2)},
        {"resolution": "1920x1080", "fps_band": TARGETS["fps_band"],
         "duration_band_sec": TARGETS["duration_band_sec"]},
        WEIGHTS["format"],
        "" if ok_res else "resolution is not 1080p 16:9",
    )


def _score_pacing(shots: list[dict], fps: float) -> Dimension:
    durations = [max(0.0, (s["b"] - s["a"]) / fps) for s in shots]
    if not durations:
        return Dimension("pacing", None, None, TARGETS["shot_band_sec"],
                         WEIGHTS["pacing"], "no shots decoded")
    lo, hi = TARGETS["shot_band_sec"]
    per_shot = [band_score(d, lo, hi, TARGETS["shot_ideal_sec"]) for d in durations]
    in_band = sum(1 for d in durations if lo <= d <= hi)
    score = 0.5 * (sum(per_shot) / len(per_shot)) + 0.5 * fraction_score(in_band / len(durations))
    return Dimension(
        "pacing", score,
        {"n_shots": len(shots), "durations_sec": [round(d, 2) for d in durations],
         "in_band": in_band},
        {"shot_band_sec": TARGETS["shot_band_sec"], "ideal_sec": TARGETS["shot_ideal_sec"]},
        WEIGHTS["pacing"],
        "shots outside 3.0-6.5 s" if in_band < len(durations) else "",
    )


def _score_cuts(shots: list[dict], frames: np.ndarray, fps: float) -> Dimension:
    """Hard cuts only: each boundary is one spike, not a soft ramp.

    A crossfade spreads its change over several frames, so the boundary
    diff never exceeds the cut threshold while the surrounding diffs rise.
    The check therefore compares the diff at the cut frame with the diffs
    two frames either side: a hard cut is sharply peaked, a fade is not.
    """
    n_shots = len(shots)
    if n_shots < 2:
        return Dimension("cut_grammar", 0.0, {"n_shots": n_shots}, TARGETS["min_cuts"],
                         WEIGHTS["cut_grammar"], "a single shot is not a Ricks-style edit")
    diff = (np.abs(np.diff(frames.astype(np.int16), axis=0)).mean(axis=(1, 2, 3))
            if frames.shape[0] > 1 else np.zeros(0))
    peaked = soft = 0
    for s in shots[1:]:
        i = s["a"] - 1
        # A cut can land a frame or two either side of the plan boundary
        # (muxing / GOP rounding), so look for the spike in a small
        # window instead of exactly on the boundary.
        window = range(max(0, i - 3), min(len(diff), i + 4))
        if not window:
            continue
        peak = max(float(diff[j]) for j in window)
        peak_at = max(window, key=lambda j: float(diff[j]))
        neighbours = [diff[j] for j in range(max(0, peak_at - 4), min(len(diff), peak_at + 5))
                      if abs(j - peak_at) >= 2]
        if not neighbours:
            continue
        others = float(np.mean(neighbours)) or 1e-6
        if peak >= max(12.0, 3.0 * others):
            peaked += 1
        else:
            soft += 1
    boundaries = peaked + soft
    # How many shots a video needs depends on how long it is: a 10 s clip
    # with 3 shots is correct editing, not a shortfall of cuts.
    covered = sum(max(0, s["b"] - s["a"]) for s in shots)
    duration_sec = covered / fps if fps else 0.0
    expected = max(2, math.ceil(duration_sec / TARGETS["shot_ideal_sec"]))
    count_score = fraction_score(min(1.0, n_shots / expected))
    hard_score = fraction_score(peaked / boundaries) if boundaries else 100.0
    return Dimension(
        "cut_grammar", 0.5 * count_score + 0.5 * hard_score,
        {"n_shots": n_shots, "hard_cuts": peaked, "soft_boundaries": soft},
        {"min_cuts": TARGETS["min_cuts"], "cuts": "hard only"},
        WEIGHTS["cut_grammar"],
        "soft boundary (fade/crossfade) detected" if soft else "",
    )


def _score_motion(shots: list[dict], report, frames: np.ndarray,
                  fps: float = 24.0) -> Dimension:
    if len(shots) == 0 or frames.shape[0] < 2:
        return Dimension("motion", None, None, TARGETS["motion_floor"],
                         WEIGHTS["motion"], "not enough frames")
    per_shot = []
    for s in shots:
        a, b = s["a"], min(s["b"], frames.shape[0])
        if b - a < 2:
            continue
        block = frames[a:b].astype(np.int16)
        d = float(np.abs(np.diff(block, axis=0)).mean())
        per_shot.append(d)
    if not per_shot:
        return Dimension("motion", None, None, TARGETS["motion_floor"],
                         WEIGHTS["motion"], "no shot with 2+ frames")
    floor, ceil = TARGETS["motion_floor"], TARGETS["motion_ceiling"]
    per_shot_scores = [
        band_score(d, floor, ceil, ideal=(floor + 3.0)) for d in per_shot
    ]
    # The channel ends on a deliberate ~1 s hold, so a static final second
    # is the one place stillness is correct; anything earlier is a defect.
    hold_start = frames.shape[0] - int(round(fps))
    frozen = len([s for s in report.frozen_spans if int(s[0]) < hold_start])
    held = float(report.held_fraction)
    held_score = 100.0 if held <= TARGETS["max_held_fraction"] else max(
        0.0, 100.0 * (1.0 - (held - TARGETS["max_held_fraction"]) / 0.5))
    # One frozen span is a visible defect, so it zeroes its share
    # outright instead of shaving a few points off.
    frozen_score = 0.0 if frozen else 100.0
    score = (sum(per_shot_scores) / len(per_shot_scores) * 0.5
             + held_score * 0.3 + frozen_score * 0.2)
    return Dimension(
        "motion", score,
        {"per_shot_mean_diff": [round(d, 2) for d in per_shot],
         "held_fraction": round(held, 3), "frozen_spans": frozen},
        {"floor": floor, "ceiling": ceil, "max_held_fraction": TARGETS["max_held_fraction"]},
        WEIGHTS["motion"],
        "frozen shots" if frozen else "",
    )


def _score_lighting(shots: list[dict], report) -> Dimension:
    if not report.per_shot:
        return Dimension("lighting", None, None, TARGETS["luma_floor"],
                         WEIGHTS["lighting"], "no per-shot stats")
    luma = [s["mean"] for s in report.per_shot]
    contrast = [s["std"] for s in report.per_shot]
    floor = TARGETS["luma_floor"]
    dark = [round(v, 3) for v in luma if v < floor]
    luma_score = fraction_score(sum(1 for v in luma if v >= floor) / len(luma))
    contrast_score = fraction_score(
        sum(1 for c in contrast if c >= TARGETS["contrast_floor"]) / len(contrast))
    black = len(report.black_frames)
    score = luma_score * 0.5 + contrast_score * 0.35 + max(0.0, 100.0 - 20.0 * black) * 0.15
    return Dimension(
        "lighting", score,
        {"per_shot_luma": [round(v, 3) for v in luma],
         "per_shot_contrast": [round(c, 3) for c in contrast],
         "shots_below_floor": dark, "black_frames": black},
        {"luma_floor": floor, "contrast_floor": TARGETS["contrast_floor"]},
        WEIGHTS["lighting"],
        "dark shots" if dark else "",
    )


def _score_framing(plan: dict | None) -> Dimension:
    if not plan or not plan.get("shots"):
        return Dimension("framing_variety", None, None, "plan", WEIGHTS["framing_variety"],
                         "needs a shot plan (--plan)")
    shots = plan["shots"]
    framings = [str(s.get("framing") or "unknown") for s in shots]
    pairs = list(zip(framings, framings[1:]))
    # Any adjacent repeat counts, wide included: a pair of identical wide
    # shots is exactly the repeated-framing defect the channel study flags.
    repeat_pairs = sum(1 for a, b in pairs if a == b)
    variety = fraction_score(len(set(framings)) / max(1, len(framings)))
    repeat_penalty = min(40.0, 20.0 * repeat_pairs)
    score = max(0.0, variety - repeat_penalty)
    return Dimension(
        "framing_variety", score,
        {"n_shots": len(shots), "distinct_framings": len(set(framings)),
         "adjacent_repeats": repeat_pairs, "sequence": framings[:12]},
        {"distinct_ratio": 1.0, "adjacent_repeats": 0},
        WEIGHTS["framing_variety"],
        "repeated adjacent framing" if repeat_pairs else "",
    )


def _score_captions(plan: dict | None) -> Dimension:
    if not plan or not plan.get("captions"):
        return Dimension("captions", None, None, "plan", WEIGHTS["captions"],
                         "needs caption metrics (--plan)")
    caps = plan["captions"]
    lo, hi = TARGETS["caption_y_band"]
    checks = []
    for c in caps:
        font = float(c.get("font_px") or 0)
        lines = int(c.get("lines") or 0)
        chars = int(c.get("max_chars") or 0)
        y = float(c.get("y_frac") or 0)
        ok = (font >= TARGETS["caption_font_px"]
              and lines <= TARGETS["caption_max_lines"]
              and chars <= TARGETS["caption_max_chars"]
              and lo <= y <= hi)
        checks.append(ok)
    score = fraction_score(sum(checks) / len(checks))
    return Dimension(
        "captions", score,
        {"n_captions": len(caps), "compliant": sum(checks)},
        {"font_px": TARGETS["caption_font_px"], "max_lines": TARGETS["caption_max_lines"],
         "max_chars": TARGETS["caption_max_chars"], "y_band": TARGETS["caption_y_band"]},
        WEIGHTS["captions"],
    )


def _score_characters(plan: dict | None) -> Dimension:
    if not plan or not plan.get("shots"):
        return Dimension("characters", None, None, "plan", WEIGHTS["characters"],
                         "needs character boxes (--plan)")
    shots = [s for s in plan["shots"] if s.get("characters") is not None]
    if not shots:
        return Dimension("characters", None, None, "plan", WEIGHTS["characters"],
                         "no shot declares characters")
    tol = TARGETS["head_ratio_tol"]
    ok_shots = 0
    insights = []
    for s in shots:
        chars = s.get("characters") or []
        if not chars:
            insights.append({"shot": s.get("index"), "issue": "no character"})
            continue
        head_ok = all(abs(float(c.get("head_ratio", TARGETS["head_ratio"]))
                          - TARGETS["head_ratio"]) <= tol for c in chars)
        inside = True
        for c in chars:
            box = c.get("bbox")
            if not box:
                continue
            w, h = TARGETS["width"], TARGETS["height"]
            m = TARGETS["safe_action_margin"]
            x0, y0, x1, y1 = box
            if x0 < w * m or y0 < h * m or x1 > w * (1 - m) or y1 > h * (1 - m):
                inside = False
                insights.append({"shot": s.get("index"), "issue": "outside safe area",
                                 "bbox": box})
        if head_ok and inside:
            ok_shots += 1
    score = fraction_score(ok_shots / len(shots))
    return Dimension(
        "characters", score,
        {"n_shots": len(shots), "compliant": ok_shots, "issues": insights[:8]},
        {"head_ratio": TARGETS["head_ratio"], "tol": tol,
         "safe_action_margin": TARGETS["safe_action_margin"]},
        WEIGHTS["characters"],
        "" if ok_shots == len(shots) else "character shots fail head-ratio/safe-area",
    )


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def score_video(video_path: str | Path, plan: dict | None = None,
                probe_size: tuple[int, int] = (320, 180)) -> ParityReport:
    """Measure ``video_path`` and score it against the reference targets."""
    video_path = str(video_path)
    specs = probe_specs(video_path)
    fps = _parse_fps(specs)
    frames = decode_frames(video_path, probe_size[0], probe_size[1])

    # Shot boundaries are ALWAYS detected from pixels: muxing drift makes
    # plan frame offsets unreliable, and a boundary the encoder moved by a
    # few frames is still a real cut. The plan only labels the detected
    # shots, and only when the counts agree.
    diff = (np.abs(np.diff(frames.astype(np.int16), axis=0)).mean(axis=(1, 2, 3))
            if frames.shape[0] > 1 else np.zeros(0))
    shots = _shot_ranges_from_cuts(diff, frames.shape[0])
    effective_plan = dict(plan or {})
    if plan and plan.get("shots"):
        labels = plan["shots"]
        if len(labels) == len(shots):
            effective_plan["shots"] = [
                {**lab, "index": s["id"], "a": s["a"], "b": s["b"]}
                for lab, s in zip(labels, shots)
            ]
        else:
            effective_plan["shots"] = []  # counts disagree: framing unmeasured
            effective_plan["plan_shot_count"] = len(labels)
    else:
        effective_plan["shots"] = []

    report = analyze_frames(frames, fps, shots=shots)

    dims = [
        _score_format(specs, fps),
        _score_pacing(shots, fps),
        _score_cuts(shots, frames, fps),
        _score_motion(shots, report, frames, fps),
        _score_lighting(shots, report),
        _score_framing(effective_plan),
        _score_captions(effective_plan),
        _score_characters(effective_plan),
    ]

    measured = [d for d in dims if d.score is not None]
    total_weight = sum(d.weight for d in measured)
    overall = (sum(d.score * d.weight for d in measured) / total_weight) if total_weight else None
    passed = bool(overall is not None and overall >= 90.0
                  and all(d.score >= 85.0 for d in measured))
    return ParityReport(video=video_path, dimensions=dims,
                        overall=overall, passed=passed)


def _main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Ricks-style parity scorecard")
    ap.add_argument("video")
    ap.add_argument("--plan", help="JSON with shots/captions for plan-only dimensions")
    ap.add_argument("--json-out", help="write the report here")
    args = ap.parse_args(argv)

    plan = None
    if args.plan:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))

    report = score_video(args.video, plan)
    payload = report.to_dict()
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main(__import__("sys").argv[1:]))
