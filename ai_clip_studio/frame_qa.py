# MIT attribution — adapted detection logic from:
#   mromidev/claude-animated-shorts (https://github.com/mromidev/claude-animated-shorts.git)
#   Copyright (c) 2026 Mr omi, MIT License (see ../../THIRD_PARTY_NOTICES.md).
# Source file: templates/scripts/short_qa.py (frame-by-frame QA of a rendered
# short: black/white/frozen/pop detection, per-shot colour stats, contact
# sheets). Adapted here: parameterized for 16:9 / 24 fps (the original hard-
# codes a 180x320 vertical decode and 30 fps assumptions), restructured as
# importable pure functions, and given explicit planned-frame exclusions.
# NOT wired into any pipeline, renderer, or server — Phase 2 work, after
# Stage 3 lands. See acceptance_loop/EXTERNAL_REPO_AUDIT_CLAUDE_ANIMATED_SHORTS.md.
"""Frame-level QA detection for rendered videos: black / white / frozen / pop.

This module answers one question the existing gates cannot: *did the render
actually change from frame to frame, and did any frame come out black, white,
or with a single-frame glitch?* ``qa_gates.py`` checks ffprobe/RMS/resolution/
frame counts and a motion report; ``evaluate_16x9.py`` checks resolution,
black bars, audio presence, and caption overflow. Neither inspects per-frame
pixels, so a video that freezes for a second, flashes white, or pops on one
frame can pass Technical QA today. The detection thresholds below are the
measured ones from the external repo's ``short_qa.py``, re-parameterized:

- black frame: mean Rec.709 luma < 0.04 (unchanged).
- white frame: mean luma > 0.93, ignoring planned flashes (unchanged).
- frozen span: mean absolute frame diff < 0.02 for >= 0.4 s (the original
  hard-codes >= 12 frames at 30 fps = 0.4 s; here the span is computed from
  the actual fps, so 24 fps needs >= 10 frames).
- pop: frame diff > 3x the local median (window +-8 frames) + 1.0, ignoring
  planned frames (cuts, flashes, crossfades, impact kicks).

Planned frames MUST be supplied by the caller (shot boundaries, intentional
flashes, crossfade windows). A pop on a planned cut is not a defect; a pop
anywhere else is reported. Nothing here decides PASS/FAIL on its own — the
caller (a future QA gate) owns thresholds-as-policy and the verdict.

Requires numpy (present in the environment and already used by the test
suite) and ffmpeg/ffprobe on PATH for the decode/probe helpers. The pure
detection functions take numpy arrays and need no video file.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "FrameStats",
    "compute_frame_stats",
    "frame_diffs",
    "detect_black_frames",
    "detect_white_frames",
    "detect_frozen_spans",
    "detect_pops",
    "per_shot_stats",
    "planned_frame_set",
    "decode_frames",
    "probe_specs",
    "analyze_frames",
]

# Rec.709 luma weights, as in the source script.
LUMA_W = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

# Detection thresholds (source: templates/scripts/short_qa.py).
BLACK_LUMA_MAX = 0.04
WHITE_LUMA_MIN = 0.93
FROZEN_DIFF_MAX = 0.02
FROZEN_MIN_SECONDS = 0.4
POP_MEDIAN_FACTOR = 3.0
POP_MEDIAN_OFFSET = 1.0
POP_MEDIAN_WINDOW = 8


@dataclass
class FrameStats:
    """Per-frame pixel statistics for one decoded video.

    ``mean``/``std``/``p2``/``p98`` are Rec.709 luma statistics per frame;
    ``sat`` is mean HSV-style saturation per frame. ``diff`` has one fewer
    entry: ``diff[i]`` is the mean absolute pixel difference between frame
    ``i`` and frame ``i + 1`` (0..255 scale, as in the source script).
    """

    mean: np.ndarray
    std: np.ndarray
    p2: np.ndarray
    p98: np.ndarray
    sat: np.ndarray
    diff: np.ndarray
    n_frames: int = 0

    def to_dict(self) -> dict:
        return {
            "n_frames": int(self.n_frames),
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "p2": self.p2.tolist(),
            "p98": self.p98.tolist(),
            "sat": self.sat.tolist(),
            "diff": self.diff.tolist(),
        }


def compute_frame_stats(frames: np.ndarray) -> FrameStats:
    """Per-frame luma/saturation statistics for an ``(n, H, W, 3)`` uint8 stack.

    Raises ValueError on an empty stack or a wrong-shaped array. The math
    mirrors ``short_qa.py`` exactly (float32 luma, saturation suppressed
    where max channel <= 0.06).
    """
    arr = np.asarray(frames)
    if arr.ndim != 4 or arr.shape[-1] != 3:
        raise ValueError(f"expected (n, H, W, 3) frames, got shape {arr.shape}")
    n = int(arr.shape[0])
    if n == 0:
        raise ValueError("empty frame stack")
    f32 = arr.astype(np.float32) / 255.0
    luma = f32 @ LUMA_W
    mx = f32.max(-1)
    mn = f32.min(-1)
    sat = np.where(mx > 0.06, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    flat = luma.reshape(n, -1)
    diff = frame_diffs(arr)
    return FrameStats(
        mean=flat.mean(1),
        std=flat.std(1),
        p2=np.percentile(flat, 2, axis=1),
        p98=np.percentile(flat, 98, axis=1),
        sat=sat.reshape(n, -1).mean(1),
        diff=diff,
        n_frames=n,
    )


def frame_diffs(frames: np.ndarray) -> np.ndarray:
    """Mean absolute pixel difference between consecutive frames (0..255)."""
    arr = np.asarray(frames)
    if arr.shape[0] < 2:
        return np.zeros(0, dtype=np.float64)
    return np.abs(np.diff(arr.astype(np.int16), axis=0)).mean(axis=(1, 2, 3))


def detect_black_frames(stats: FrameStats, threshold: float = BLACK_LUMA_MAX) -> list[int]:
    """Frames whose mean luma is below ``threshold`` (default 0.04)."""
    return [int(i) for i in range(stats.n_frames) if float(stats.mean[i]) < threshold]


def detect_white_frames(
    stats: FrameStats,
    threshold: float = WHITE_LUMA_MIN,
    planned: set[int] | frozenset[int] | None = None,
) -> list[int]:
    """Frames whose mean luma exceeds ``threshold``, excluding planned ones.

    Planned frames cover intentional white flashes; an unplanned white frame
    is a render defect (blown-out frame / missing scene).
    """
    planned = planned or set()
    return [
        int(i)
        for i in range(stats.n_frames)
        if float(stats.mean[i]) > threshold and i not in planned
    ]


def detect_frozen_spans(
    stats: FrameStats,
    fps: float,
    diff_threshold: float = FROZEN_DIFF_MAX,
    min_seconds: float = FROZEN_MIN_SECONDS,
) -> list[tuple[int, int]]:
    """Spans where consecutive frame diffs stay below ``diff_threshold``.

    A span is ``(first_diff_index, last_diff_index)`` in diff coordinates:
    diff ``i`` covers frames ``i -> i+1``, so a span ``(a, b)`` means frames
    ``a..b+1`` are effectively identical. ``min_seconds`` converts to a
    minimum diff count via ``fps`` (0.4 s -> 10 diffs at 24 fps, 12 at
    30 fps, matching the source script's 12-frame rule at its native fps).
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    min_run = max(1, math.ceil(min_seconds * fps))
    diff = stats.diff
    spans: list[tuple[int, int]] = []
    run_start: int | None = None
    for i in range(len(diff)):
        if float(diff[i]) < diff_threshold:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start >= min_run:
                spans.append((run_start, i - 1))
            run_start = None
    if run_start is not None and len(diff) - run_start >= min_run:
        spans.append((run_start, len(diff) - 1))
    return spans


def detect_pops(
    stats: FrameStats,
    planned: set[int] | frozenset[int] | None = None,
    factor: float = POP_MEDIAN_FACTOR,
    offset: float = POP_MEDIAN_OFFSET,
    window: int = POP_MEDIAN_WINDOW,
) -> list[int]:
    """Single-frame glitch spikes: ``diff[i] > factor * local_median + offset``.

    The local median is taken over ``diff[max(0, i-window):i+window+1]``, as
    in the source script. Returns the index of the *second* frame of each
    spiking diff (``i + 1``), i.e. the frame that looks wrong. Planned
    frames (cuts, flashes, kicks) are excluded.
    """
    planned = planned or set()
    diff = stats.diff
    pops: list[int] = []
    for i in range(len(diff)):
        lo = max(0, i - window)
        hi = min(len(diff), i + window + 1)
        med = float(np.median(diff[lo:hi]))
        if float(diff[i]) > factor * med + offset and (i + 1) not in planned:
            pops.append(i + 1)
    return pops


def per_shot_stats(
    stats: FrameStats, shots: list[dict]
) -> list[dict]:
    """Median per-frame statistics over each shot's frame range.

    Each shot dict needs ``id``, ``a`` (first frame, inclusive) and ``b``
    (end frame, exclusive). Ranges are clamped to the decoded frames. With
    no shots, the whole video is reported as shot 0, as in the source.
    """
    ranges = shots or [{"id": 0, "a": 0, "b": stats.n_frames}]
    out: list[dict] = []
    for s in ranges:
        a = max(0, int(s["a"]))
        b = min(int(s["b"]), stats.n_frames)
        if a >= b:
            continue
        out.append(
            {
                "id": s.get("id", 0),
                "a": a,
                "b": b,
                "mean": float(np.median(stats.mean[a:b])),
                "std": float(np.median(stats.std[a:b])),
                "p2": float(np.median(stats.p2[a:b])),
                "p98": float(np.median(stats.p98[a:b])),
                "sat": float(np.median(stats.sat[a:b])),
            }
        )
    return out


def planned_frame_set(
    shots: list[dict] | None = None,
    flashes: list[tuple[int, int]] | None = None,
    xfades: list[tuple[int, int]] | None = None,
    extra_spans: list[tuple[int, int]] | None = None,
) -> set[int]:
    """Frames where a spike/flash is intentional and must not count as a pop.

    Mirrors the source script's ``planned`` set: every shot's first frame
    (and the frame before it, i.e. the cut boundary), plus each flash /
    crossfade / extra span widened by one frame on each side. ``extra_spans``
    covers impact kicks and other planned single-frame events the caller
    knows about.
    """
    planned: set[int] = set()
    for a, b in list(flashes or []) + list(xfades or []) + list(extra_spans or []):
        planned.update(range(int(a) - 1, int(b) + 1))
    for s in shots or []:
        a = int(s["a"])
        planned.update((a - 1, a))
    return {f for f in planned if f >= 0}


def decode_frames(
    video_path: str, width: int = 320, height: int = 180
) -> np.ndarray:
    """Decode a video to a small RGB stack with ffmpeg (``width`` x ``height``).

    The probe resolution defaults to 320x180 (16:9); the source script uses
    180x320 for vertical video. Detection thresholds were validated at small
    probe sizes — decoding full HD would only slow the check down.
    Raises RuntimeError if ffmpeg fails or returns no frames.
    """
    cmd = [
        "ffmpeg", "-v", "error", "-i", video_path,
        "-vf", f"scale={width}:{height}:flags=area",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed for {video_path}: {proc.stderr[:300]!r}")
    raw = proc.stdout
    frame_bytes = width * height * 3
    n = len(raw) // frame_bytes
    if n == 0:
        raise RuntimeError(f"ffmpeg returned no frames for {video_path}")
    return np.frombuffer(raw[: n * frame_bytes], dtype=np.uint8).reshape(n, height, width, 3)


def probe_specs(video_path: str) -> dict:
    """ffprobe stream/format summary (resolution, fps, frames, duration, audio)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,sample_rate,channels:format=duration",
        "-of", "json", video_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {video_path}: {proc.stderr[:300]!r}")
    data = json.loads(proc.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    return {
        "width": video.get("width"),
        "height": video.get("height"),
        "r_frame_rate": video.get("r_frame_rate"),
        "nb_frames": video.get("nb_frames"),
        "duration": float(data.get("format", {}).get("duration", 0.0) or 0.0),
        "audio": [
            {"codec": s.get("codec_name"), "sample_rate": s.get("sample_rate"), "channels": s.get("channels")}
            for s in audio
        ],
    }


@dataclass
class FrameQAReport:
    """Everything ``analyze_frames`` found, plus the inputs it used."""

    n_frames: int
    fps: float
    black_frames: list[int] = field(default_factory=list)
    white_frames: list[int] = field(default_factory=list)
    frozen_spans: list[tuple[int, int]] = field(default_factory=list)
    pops: list[int] = field(default_factory=list)
    per_shot: list[dict] = field(default_factory=list)
    motion_mean_diff: float = 0.0
    held_fraction: float = 0.0

    def to_dict(self) -> dict:
        return {
            "n_frames": self.n_frames,
            "fps": self.fps,
            "black_frames": self.black_frames,
            "white_frames": self.white_frames,
            "frozen_spans": [list(s) for s in self.frozen_spans],
            "pops": self.pops,
            "per_shot": self.per_shot,
            "motion_mean_diff": self.motion_mean_diff,
            "held_fraction": self.held_fraction,
        }


def analyze_frames(
    frames: np.ndarray,
    fps: float,
    shots: list[dict] | None = None,
    planned: set[int] | frozenset[int] | None = None,
) -> FrameQAReport:
    """Run all frame detections over a decoded stack. No verdict — see module docstring."""
    stats = compute_frame_stats(frames)
    planned_set = set(planned) if planned is not None else planned_frame_set(shots or [])
    diff = stats.diff
    return FrameQAReport(
        n_frames=stats.n_frames,
        fps=fps,
        black_frames=detect_black_frames(stats),
        white_frames=detect_white_frames(stats, planned=planned_set),
        frozen_spans=detect_frozen_spans(stats, fps),
        pops=detect_pops(stats, planned=planned_set),
        per_shot=per_shot_stats(stats, shots or []),
        motion_mean_diff=float(diff.mean()) if len(diff) else 0.0,
        held_fraction=float((diff < 0.3).mean()) if len(diff) else 0.0,
    )
