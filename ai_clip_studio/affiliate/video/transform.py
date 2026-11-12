"""Video transformation engine (§9): FFmpeg edit operations.

Every operation requires a non-empty editorial ``purpose`` — random
transformations are refused (§9: no evasion transforms). Horizontal
mirror (``hflip``) additionally requires explicit approval plus a
flip-safety review: ``assess_flip_safety`` detects text-like regions
and warns that flipping mirrors readable labels, packaging, and
logos. Mirror defaults OFF: no plan adds ``hflip`` unless the user
explicitly requests it.

The registry mirrors the schema EDIT_OPERATIONS vocabulary
(``hflip`` … ``stabilize``). Text operations (``text_overlay`` etc.)
live in ``text_replace.py``; ``manual_mask`` in ``models.py``.

Two use patterns:
  * ``apply_transforms`` — standalone render (preview / proof).
  * ``build_transform_graph`` — filter-graph fragment for the
    single-pass export in ``export.py``. Stabilization needs a
    detect pre-pass (``run_stabilize_detect``); the transform step
    then joins the final graph.
"""
from __future__ import annotations

import math
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .capabilities import run_command
from .models import SourceInfo, TransformOp
from .probe import ProbeError, probe_source


class TransformRefused(ValueError):
    """An operation was refused (missing purpose / approval / bad params)."""


# ---------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------

def _num(params: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        raise TransformRefused(f"parameter {key!r} must be a number")


def _int(params: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError):
        raise TransformRefused(f"parameter {key!r} must be an integer")


def validate_op(op: TransformOp, source: SourceInfo | None = None) -> None:
    """Validate one operation: known name, purpose, params, approvals."""
    from .models import TRANSFORM_OPERATIONS
    if op.operation not in TRANSFORM_OPERATIONS:
        raise TransformRefused(f"unknown transform operation {op.operation!r}")
    if not op.purpose.strip():
        raise TransformRefused(
            f"operation {op.operation!r} needs an editorial purpose "
            "(§9: every transform must have a legitimate purpose)")
    params = op.parameters
    if op.operation == "hflip" and not op.approved:
        raise TransformRefused(
            "horizontal mirror (hflip) needs explicit approval after the "
            "label/logo warning review (schema AFF021; mirror defaults OFF)")
    if op.operation == "rotate":
        deg = _num(params, "degrees", 0.0)
        if not -360.0 <= deg <= 360.0:
            raise TransformRefused("rotate degrees must be within -360..360")
    if op.operation == "crop" and source is not None:
        w, h = _int(params, "w", 0), _int(params, "h", 0)
        x, y = _int(params, "x", 0), _int(params, "y", 0)
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > source.width \
                or y + h > source.height:
            raise TransformRefused(
                f"crop rect ({x},{y},{w},{h}) is outside the "
                f"{source.width}x{source.height} frame")
    if op.operation == "scale":
        w, h = _int(params, "w", -2), _int(params, "h", -2)
        if (w <= 0 and w != -2) or (h <= 0 and h != -2):
            raise TransformRefused("scale w/h must be positive or -2 (auto)")
    if op.operation == "trim":
        start = _num(params, "start", 0.0)
        end = _num(params, "end", 0.0)
        if start < 0 or end <= start:
            raise TransformRefused("trim needs 0 <= start < end")
        if source is not None and end > source.duration_sec + 0.01:
            raise TransformRefused(
                f"trim end {end}s exceeds duration {source.duration_sec}s")
    if op.operation == "scene_reorder":
        segments = params.get("segments")
        if not isinstance(segments, list) or not segments:
            raise TransformRefused(
                "scene_reorder needs a non-empty 'segments' list of "
                "[start, end] pairs")
        for seg in segments:
            if (not isinstance(seg, (list, tuple)) or len(seg) != 2
                    or seg[1] <= seg[0] or seg[0] < 0):
                raise TransformRefused(f"invalid reorder segment {seg!r}")
    if op.operation == "speed":
        factor = _num(params, "factor", 1.0)
        if not 0.25 <= factor <= 4.0:
            raise TransformRefused("speed factor must be within 0.25..4.0")
    if op.operation == "brightness":
        value = _num(params, "value", 0.0)
        if not -1.0 <= value <= 1.0:
            raise TransformRefused("brightness must be within -1..1")
    if op.operation == "contrast":
        value = _num(params, "value", 1.0)
        if not 0.0 <= value <= 2.0:
            raise TransformRefused("contrast must be within 0..2")
    if op.operation == "saturation":
        value = _num(params, "value", 1.0)
        if not 0.0 <= value <= 3.0:
            raise TransformRefused("saturation must be within 0..3")
    if op.operation == "white_balance":
        value = _num(params, "warmth", 0.0)
        if not -1.0 <= value <= 1.0:
            raise TransformRefused("white_balance warmth must be within -1..1")
    if op.operation == "sharpen":
        value = _num(params, "amount", 0.5)
        if not 0.0 <= value <= 2.0:
            raise TransformRefused("sharpen amount must be within 0..2")
    if op.operation == "denoise":
        value = _num(params, "strength", 3.0)
        if not 0.0 <= value <= 10.0:
            raise TransformRefused("denoise strength must be within 0..10")
    if op.operation == "reframe":
        tw, th = _int(params, "target_w", 0), _int(params, "target_h", 0)
        if tw <= 0 or th <= 0:
            raise TransformRefused("reframe needs positive target_w/target_h")
        strategy = params.get("strategy", "blur_fill")
        if strategy not in ("blur_fill", "crop_center", "pad"):
            raise TransformRefused(f"unknown reframe strategy {strategy!r}")


def validate_ops(ops: list[TransformOp],
                 source: SourceInfo | None = None) -> None:
    """Validate a whole plan (reorder must come first when present)."""
    for op in ops:
        validate_op(op, source)
    reorder_at = [i for i, op in enumerate(ops)
                  if op.operation == "scene_reorder"]
    if reorder_at and reorder_at[0] != 0:
        raise TransformRefused(
            "scene_reorder must be the first operation in the plan")
    if len(reorder_at) > 1:
        raise TransformRefused("at most one scene_reorder per plan")


# ---------------------------------------------------------------------
# reframe builders (shared with export.py)
# ---------------------------------------------------------------------

def reframe_crop_rect(source_w: int, source_h: int, target_w: int,
                      target_h: int, focus_x: float = 0.5,
                      focus_y: float = 0.5) -> tuple[int, int, int, int]:
    """Center/focus crop rect of the target aspect inside the source."""
    target_aspect = target_w / target_h
    source_aspect = source_w / source_h
    if source_aspect > target_aspect:
        crop_h = source_h
        crop_w = int(round(crop_h * target_aspect))
    else:
        crop_w = source_w
        crop_h = int(round(crop_w / target_aspect))
    crop_w = max(2, min(source_w, crop_w // 2 * 2))
    crop_h = max(2, min(source_h, crop_h // 2 * 2))
    x = int(round((source_w - crop_w) * min(1.0, max(0.0, focus_x))))
    y = int(round((source_h - crop_h) * min(1.0, max(0.0, focus_y))))
    return (max(0, min(source_w - crop_w, x)),
            max(0, min(source_h - crop_h, y)), crop_w, crop_h)


# ---------------------------------------------------------------------
# graph builder
# ---------------------------------------------------------------------

class TransformGraph:
    """Filter-complex builder for transform plans (video + audio)."""

    def __init__(self) -> None:
        self.filters: list[str] = []
        self.video_label = "0:v"
        self.audio_label: str | None = "0:a"
        self._counter = 0
        self.notes: list[str] = []
        self.needs_stabilize_detect = False

    def _next(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    def video(self, expression: str, note: str = "") -> None:
        out = self._next("tv")
        self.filters.append(f"[{self.video_label}]{expression}[{out}]")
        self.video_label = out
        if note:
            self.notes.append(note)

    def audio(self, expression: str, note: str = "") -> None:
        if self.audio_label is None:
            return
        out = self._next("ta")
        self.filters.append(f"[{self.audio_label}]{expression}[{out}]")
        self.audio_label = out
        if note:
            self.notes.append(note)

    def build(self) -> tuple[str, str, str | None]:
        return ";".join(self.filters), self.video_label, self.audio_label


def _atempo_chain(factor: float) -> str:
    """atempo only supports 0.5..100 per instance; chain if needed."""
    parts: list[str] = []
    remaining = factor
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.4f}")
    return ",".join(parts)


def _apply_reframe(graph: TransformGraph, op: TransformOp,
                   cur_w: int, cur_h: int) -> tuple[int, int]:
    params = op.parameters
    tw, th = _int(params, "target_w", 1080), _int(params, "target_h", 1920)
    strategy = params.get("strategy", "blur_fill")
    focus_x = _num(params, "focus_x", 0.5)
    focus_y = _num(params, "focus_y", 0.5)
    if strategy == "crop_center":
        x, y, cw, ch = reframe_crop_rect(cur_w, cur_h, tw, th, focus_x, focus_y)
        graph.video(f"crop={cw}:{ch}:{x}:{y},scale={tw}:{th}",
                    f"reframe crop_center ({x},{y},{cw},{ch}) -> {tw}x{th}")
        return tw, th
    if strategy == "pad":
        color = params.get("pad_color", "black")
        graph.video(f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                    f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color={color}",
                    f"reframe pad -> {tw}x{th}")
        return tw, th
    # blur_fill: blurred stretched background + sharp foreground.
    bg = graph._next("bg")
    fg = graph._next("fg")
    out = graph._next("tv")
    blur = int(params.get("blur_radius", 20))
    graph.filters.append(f"[{graph.video_label}]split[{bg}][{fg}]")
    graph.filters.append(
        f"[{bg}]scale={tw}:{th},gblur=sigma={blur}[{bg}b]")
    graph.filters.append(
        f"[{fg}]scale={tw}:{th}:force_original_aspect_ratio=decrease[{fg}s]")
    graph.filters.append(
        f"[{bg}b][{fg}s]overlay=(W-w)/2:(H-h)/2[{out}]")
    graph.video_label = out
    graph.notes.append(f"reframe blur_fill -> {tw}x{th} (blur sigma={blur})")
    return tw, th


def _apply_reorder(graph: TransformGraph, op: TransformOp,
                   has_audio: bool) -> None:
    segments = op.parameters["segments"]
    v_labels, a_labels = [], []
    for i, (start, end) in enumerate(segments):
        v = graph._next("seg")
        graph.filters.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[{v}]")
        v_labels.append(f"[{v}]")
        if has_audio:
            a = graph._next("seg")
            graph.filters.append(
                f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[{a}]")
            a_labels.append(f"[{a}]")
    out_v = graph._next("tv")
    graph.filters.append(
        f"{''.join(v_labels)}concat=n={len(segments)}:v=1:a=0[{out_v}]")
    graph.video_label = out_v
    if has_audio:
        out_a = graph._next("ta")
        graph.filters.append(
            f"{''.join(a_labels)}concat=n={len(segments)}:v=0:a=1[{out_a}]")
        graph.audio_label = out_a
    graph.notes.append(f"scene_reorder {len(segments)} segments")


def build_transform_graph(ops: list[TransformOp], source: SourceInfo,
                          stabilize_file: str | None = None,
                          start_label: str = "0:v") -> TransformGraph:
    """Build the filter graph for a validated plan.

    ``start_label`` lets the export stage chain transforms after the
    replacement stage. Stabilization's detect pre-pass must already
    have produced ``stabilize_file`` (see ``run_stabilize_detect``).
    """
    validate_ops(ops, source)
    if start_label != "0:v" and any(op.operation == "scene_reorder"
                                    for op in ops):
        raise TransformRefused(
            "scene_reorder reads the source directly and cannot chain "
            "after earlier filter stages")
    graph = TransformGraph()
    graph.video_label = start_label
    graph.audio_label = "0:a" if source.has_audio else None
    cur_w, cur_h = source.width, source.height
    if source.rotation_deg in (90.0, 270.0):
        cur_w, cur_h = cur_h, cur_w
    for op in ops:
        p = op.parameters
        name = op.operation
        if name == "hflip":
            graph.video("hflip", "hflip (approved mirror)")
        elif name == "vflip":
            graph.video("vflip", "vflip")
        elif name == "rotate":
            deg = _num(p, "degrees", 0.0)
            if deg % 90 == 0:
                turns = int((deg % 360) // 90)
                mapping = {0: None, 1: "transpose=1", 2: "transpose=1,transpose=1",
                           3: "transpose=2"}
                expr = mapping[turns]
                if expr:
                    graph.video(expr, f"rotate {deg} deg")
                if turns % 2 == 1:
                    cur_w, cur_h = cur_h, cur_w
            else:
                graph.video(
                    f"rotate={deg}*PI/180:fillcolor=black",
                    f"rotate {deg} deg (arbitrary angle)")
        elif name == "crop":
            x, y = _int(p, "x", 0), _int(p, "y", 0)
            w, h = _int(p, "w", 0), _int(p, "h", 0)
            graph.video(f"crop={w}:{h}:{x}:{y}", f"crop ({x},{y},{w},{h})")
            cur_w, cur_h = w, h
        elif name == "scale":
            w, h = _int(p, "w", -2), _int(p, "h", -2)
            graph.video(f"scale={w}:{h}", f"scale {w}x{h}")
            if w > 0:
                cur_w = w
            if h > 0:
                cur_h = h
        elif name == "reframe":
            cur_w, cur_h = _apply_reframe(graph, op, cur_w, cur_h)
        elif name == "trim":
            start, end = _num(p, "start", 0.0), _num(p, "end", 0.0)
            graph.video(f"trim=start={start}:end={end},setpts=PTS-STARTPTS",
                        f"trim {start}-{end}s")
            graph.audio(f"atrim=start={start}:end={end},asetpts=PTS-STARTPTS")
        elif name == "scene_reorder":
            _apply_reorder(graph, op, source.has_audio)
        elif name == "speed":
            factor = _num(p, "factor", 1.0)
            graph.video(f"setpts=PTS/{factor:.4f}", f"speed {factor}x")
            graph.audio(_atempo_chain(factor))
        elif name == "brightness":
            graph.video(f"eq=brightness={_num(p, 'value', 0.0):.3f}",
                        f"brightness {_num(p, 'value', 0.0)}")
        elif name == "contrast":
            graph.video(f"eq=contrast={_num(p, 'value', 1.0):.3f}",
                        f"contrast {_num(p, 'value', 1.0)}")
        elif name == "saturation":
            graph.video(f"eq=saturation={_num(p, 'value', 1.0):.3f}",
                        f"saturation {_num(p, 'value', 1.0)}")
        elif name == "white_balance":
            warmth = _num(p, "warmth", 0.0)
            graph.video(
                f"colorbalance=rs={warmth * 0.2:.3f}:gs=0:bs={-warmth * 0.2:.3f}",
                f"white_balance warmth={warmth} (colorbalance approx.)")
        elif name == "sharpen":
            amount = _num(p, "amount", 0.5)
            graph.video(f"unsharp=5:5:{amount:.2f}:5:5:0.0",
                        f"sharpen amount={amount}")
        elif name == "denoise":
            strength = _num(p, "strength", 3.0)
            graph.video(
                f"hqdn3d={strength:.1f}:{strength:.1f}:"
                f"{strength * 0.6:.1f}:{strength * 0.6:.1f}",
                f"denoise hqdn3d strength={strength}")
        elif name == "stabilize":
            if stabilize_file is None:
                graph.needs_stabilize_detect = True
                graph.notes.append("stabilize requested — detect pre-pass "
                                   "required before building the graph")
            else:
                graph.video(
                    f"vidstabtransform=input={stabilize_file}:smoothing=10",
                    "stabilize (vidstabtransform)")
        else:  # pragma: no cover - validate_op guards this
            raise TransformRefused(f"unknown operation {name!r}")
    return graph


# ---------------------------------------------------------------------
# stabilization pre-pass
# ---------------------------------------------------------------------

def run_stabilize_detect(video_path: str | Path,
                         work_dir: str | Path) -> Path:
    """vidstabdetect pass 1: write the .trf transforms file."""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    trf = work / "stabilize.trf"
    argv = ["ffmpeg", "-v", "error", "-i", str(video_path),
            "-vf", f"vidstabdetect=result={trf}",
            "-f", "null", "-"]
    proc = run_command(argv, timeout=900.0)
    if proc.returncode != 0 or not trf.is_file():
        raise ProbeError(f"vidstabdetect failed: "
                         f"{(proc.stderr or '').strip()[:200]}")
    return trf


# ---------------------------------------------------------------------
# flip safety
# ---------------------------------------------------------------------

@dataclass
class FlipSafetyReport:
    warnings: list[dict[str, Any]] = field(default_factory=list)
    text_frames_checked: int = 0
    text_frames_flagged: int = 0
    method: str = ""
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"warnings": self.warnings,
                "text_frames_checked": self.text_frames_checked,
                "text_frames_flagged": self.text_frames_flagged,
                "method": self.method,
                "recommendation": self.recommendation}


def assess_flip_safety(video_path: str | Path, source: SourceInfo,
                       sample_times: list[float] | None = None,
                       ocr_engine: Any = None) -> FlipSafetyReport:
    """Detect text-like content that mirroring would corrupt.

    Uses the OCR engine when one is supplied, else the edge-density
    text-band heuristic. Warnings are DATA for the user's review —
    this function never blocks or allows a flip by itself.
    """
    from .analysis import edge_band_candidates, extract_frame_at, load_gray
    times = sample_times
    if times is None:
        step = max(1.0, source.duration_sec / 6.0)
        times = [round(i * step + 0.5, 2)
                 for i in range(6)
                 if i * step + 0.5 < source.duration_sec] or [0.5]
    warnings: list[dict[str, Any]] = []
    flagged = 0
    with tempfile.TemporaryDirectory(prefix="aff_flip_") as tmp:
        for time_sec in times:
            frame = extract_frame_at(video_path, time_sec,
                                     Path(tmp) / f"f_{time_sec:.2f}.jpg")
            found: list[str] = []
            method = "edge_density_heuristic"
            if ocr_engine is not None:
                try:
                    detections = ocr_engine.recognize(frame)
                    found = [d.text for d in detections if d.text.strip()]
                    method = "ocr"
                except Exception:  # noqa: BLE001 - fall back to heuristic
                    found = []
            if ocr_engine is None or not found:
                gray = load_gray(frame)
                boxes = edge_band_candidates(
                    gray, (source.width, source.height), time_sec)
                if boxes:
                    found = [f"{len(boxes)} text-like band(s)"]
                    method = "edge_density_heuristic"
            if found:
                flagged += 1
                warnings.append({
                    "time": time_sec,
                    "kind": "readable_text_detected",
                    "detail": ("text-like content detected; horizontal "
                               "mirror would reverse it — verify product "
                               "labels, packaging, brand logos and "
                               "direction-sensitive instructions before "
                               "approving the flip"),
                    "evidence": found[:3],
                    "method": method,
                })
    recommendation = (
        "mirror NOT recommended without review: text-like content "
        "detected in sampled frames" if flagged else
        "no text-like content detected in sampled frames; the user "
        "should still confirm labels/packaging are unaffected")
    return FlipSafetyReport(
        warnings=warnings, text_frames_checked=len(times),
        text_frames_flagged=flagged,
        method="ocr" if ocr_engine is not None else "edge_density_heuristic",
        recommendation=recommendation)


# ---------------------------------------------------------------------
# standalone application
# ---------------------------------------------------------------------

def apply_transforms(video_path: str | Path, ops: list[TransformOp],
                     output_path: str | Path,
                     work_dir: str | Path | None = None,
                     crf: int = 18) -> tuple[Path, list[str], list[str]]:
    """Render a transform plan onto a copy of the video (standalone).

    Returns (output_path, notes, command). The source is never
    modified. For production, prefer the single-pass export.
    """
    source = probe_source(video_path)
    validate_ops(ops, source)
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="aff_tr_"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        stabilize_file = None
        if any(op.operation == "stabilize" for op in ops):
            stabilize_file = str(run_stabilize_detect(video_path, work))
        graph = build_transform_graph(ops, source,
                                      stabilize_file=stabilize_file)
        filter_complex, video_label, audio_label = graph.build()
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        argv = ["ffmpeg", "-v", "error", "-i", str(video_path)]
        if filter_complex:
            argv += ["-filter_complex", filter_complex,
                     "-map", f"[{video_label}]"]
            if audio_label and audio_label != "0:a":
                argv += ["-map", f"[{audio_label}]", "-c:a", "aac",
                         "-b:a", "192k", "-ar", "48000"]
            elif source.has_audio:
                argv += ["-map", "0:a?", "-c:a", "copy"]
        argv += ["-c:v", "libx264", "-crf", str(crf), "-preset", "veryfast",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                 "-y", str(out)]
        proc = run_command(argv, timeout=900.0)
        if proc.returncode != 0 or not out.is_file():
            raise ProbeError(f"transform render failed: "
                             f"{(proc.stderr or '').strip()[:300]}")
        return out, graph.notes, argv
    finally:
        if work_dir is None:
            shutil.rmtree(work, ignore_errors=True)
