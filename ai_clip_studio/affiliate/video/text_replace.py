"""Text replacement engine (§8): localize approved text regions.

Modes:
  * SMART_OVERLAY — a designed panel covers the original region and
    shows Vietnamese text (drawbox + drawtext, text via textfile so
    Vietnamese diacritics and punctuation need no escaping).
  * LOCAL_BLUR — localized blur on the approved region only
    (crop + boxblur + overlay, time-windowed). When the region
    carries track samples with real motion, the blur box follows
    the interpolated per-frame positions (tracked blur, S9);
    static tracks keep one box.
  * CROP_AND_REFRAME — crop a full-width subtitle band off, only when
    the product stays fully visible (validated, recorded).
  * MANUAL_MASK — MaskSpec data model applied through the same
    builders (the drawing UI is Subagent B's frontend work).
  * BACKGROUND_RECONSTRUCTION — cv2 inpainting of the region on the
    affected frames; only when cv2 is installed, otherwise an
    explicit UnsupportedError (never a fake result).

Every replacement requires approval: the spec must be approved, the
authorization gate must pass, protected-class regions need an
approved removal (see ``ocr.approve_removal``), and regions flagged
for review need an approval note. Watermarks and attribution are
never removed automatically — the gate refuses without the explicit
ownership-risk acknowledgement recorded on the region.

Two use patterns:
  * ``apply_replacements`` — standalone render (preview / proof).
  * ``build_replacement_filters`` — filter-graph fragment for the
    single-pass export in ``export.py`` (preferred: one encode).
"""
from __future__ import annotations

import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
import numpy as np

from .capabilities import find_vietnamese_font, run_command
from .models import (BBox, MaskSpec, ReplacementMode, ReplacementSpec,
                     SubtitleSlot, TextClassification, TextRegion,
                     TrackSample, export_gate_check)
from .probe import ProbeError


# Tracked blur (S9): when an OCR track moves, the blur box follows it
# with per-frame ffmpeg expressions interpolating the track samples
# (see FilterGraph.blur_region_tracked). Static tracks keep the exact
# single-box behaviour below.
TRACKED_BLUR_PAD_PX = 10.0
# Centre displacement at/below this is OCR jitter, not motion: the
# static single-box path is used (byte-identical to Phase 1).
TRACKED_BLUR_STATIC_PX = 2.0
# Max samples per tracked-blur expression chunk: bounds the nested-if
# expression length for long tracks (chunks tile the track window and
# share their boundary sample, so tracking stays continuous).
TRACKED_BLUR_MAX_SAMPLES_PER_CHUNK = 32


class ReplacementRefused(ValueError):
    """A replacement was refused by the approval/authorization gate."""


class UnsupportedReplacement(RuntimeError):
    """The requested mode cannot run in this environment."""


# ---------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------

def validate_replacement(spec: ReplacementSpec, authorization_type: str,
                         commercial_rights_confirmed: bool) -> None:
    """Enforce the approval + authorization gate for one replacement."""
    allowed, reasons = export_gate_check(authorization_type,
                                         commercial_rights_confirmed)
    if not allowed:
        raise ReplacementRefused("replacement refused: " + "; ".join(reasons))
    if not spec.approved:
        raise ReplacementRefused(
            f"replacement for track {spec.region.text_id} is not approved")
    region = spec.region
    from .models import PROTECTED_TEXT_CLASSES
    if region.classification in PROTECTED_TEXT_CLASSES \
            and not region.removal_approved:
        raise ReplacementRefused(
            f"track {region.text_id} is {region.classification.value}: "
            "removal/replacement needs an approved removal with "
            "ownership-risk acknowledgement (see ocr.approve_removal)")
    if region.needs_review and not spec.approval_note.strip():
        raise ReplacementRefused(
            f"track {region.text_id} needs review: an approval note "
            "acknowledging the review is required")
    if spec.mode == ReplacementMode.CROP_AND_REFRAME:
        if not spec.product_fully_visible:
            raise ReplacementRefused(
                "CROP_AND_REFRAME refused: the product would not stay "
                "fully visible after cropping the subtitle band")
    if spec.mode == ReplacementMode.SMART_OVERLAY and not spec.vietnamese_text.strip():
        raise ReplacementRefused(
            "SMART_OVERLAY needs vietnamese_text (supplied by the "
            "translation stage)")


# ---------------------------------------------------------------------
# filter graph builder
# ---------------------------------------------------------------------

def _enable(start: float, end: float) -> str:
    return f"enable='between(t,{start:.3f},{end:.3f})'"


def _ints(box: BBox, frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
    clamped = box.clamp(frame_w, frame_h)
    return (int(round(clamped.x)), int(round(clamped.y)),
            max(1, int(round(clamped.w))), max(1, int(round(clamped.h))))


def _blur_radii(w: int, h: int, radius: int) -> tuple[int, int]:
    """Per-plane boxblur radii clamped to the crop size.

    boxblur validates each plane's radius against the plane size
    (radius must be < min(plane_w, plane_h) / 2); the chroma plane
    of yuv420p is half-size, so an unclamped radius=20 fails on
    short crops (measured: cr=20 rejected, limit < 12, on a 400x50
    crop). Clamp per plane with one unit of margin and use power 2
    so small radii still hide the text.
    """
    luma_radius = max(1, min(radius, ((min(w, h) - 1) // 2) - 1))
    chroma_radius = max(1, min(
        radius, ((min(w // 2, h // 2) - 1) // 2) - 1))
    return luma_radius, chroma_radius


# ---------------------------------------------------------------------
# tracked blur (S9): interpolate track samples -> per-frame positions
# ---------------------------------------------------------------------

def _ordered_samples(samples: list[TrackSample]) -> list[TrackSample]:
    """Samples sorted by time, deduplicated by time (first wins)."""
    ordered = sorted(samples, key=lambda s: s.time)
    deduped: list[TrackSample] = []
    for sample in ordered:
        if deduped and sample.time == deduped[-1].time:
            continue
        deduped.append(sample)
    return deduped


def interpolate_box_at(samples: list[TrackSample],
                       time_sec: float) -> BBox:
    """Linearly interpolated box at ``time_sec`` between track samples.

    Holds the first/last sample box outside the sampled range. This
    is the interpolation the ffmpeg position expressions implement;
    QA tooling uses it to ask "where is the text at time t".
    """
    ordered = _ordered_samples(samples)
    if not ordered:
        raise ValueError("interpolate_box_at needs at least one sample")
    if time_sec <= ordered[0].time:
        return ordered[0].bbox
    if time_sec >= ordered[-1].time:
        return ordered[-1].bbox
    for prev, nxt in zip(ordered, ordered[1:]):
        if prev.time <= time_sec <= nxt.time:
            span = nxt.time - prev.time
            frac = (time_sec - prev.time) / span if span > 0 else 0.0
            a, b = prev.bbox, nxt.bbox
            return BBox(a.x + (b.x - a.x) * frac,
                        a.y + (b.y - a.y) * frac,
                        a.w + (b.w - a.w) * frac,
                        a.h + (b.h - a.h) * frac)
    return ordered[-1].bbox  # pragma: no cover - range guards above


def track_displacement_px(samples: list[TrackSample]) -> float:
    """Max box-centre displacement between consecutive samples (px)."""
    ordered = _ordered_samples(samples)
    worst = 0.0
    for prev, nxt in zip(ordered, ordered[1:]):
        cx0, cy0 = prev.bbox.x + prev.bbox.w / 2, prev.bbox.y + prev.bbox.h / 2
        cx1, cy1 = nxt.bbox.x + nxt.bbox.w / 2, nxt.bbox.y + nxt.bbox.h / 2
        worst = max(worst, abs(cx1 - cx0), abs(cy1 - cy0))
    return worst


def tracked_blur_chunks(samples: list[TrackSample],
                        max_samples_per_chunk: int =
                        TRACKED_BLUR_MAX_SAMPLES_PER_CHUNK
                        ) -> list[list[TrackSample]]:
    """Partition samples into chunks of at most N samples.

    Consecutive chunks share their boundary sample, so the
    interpolated position is continuous across chunk windows.
    """
    ordered = _ordered_samples(samples)
    if len(ordered) <= max_samples_per_chunk:
        return [ordered] if ordered else []
    chunks: list[list[TrackSample]] = []
    start = 0
    while start < len(ordered):
        end = min(start + max_samples_per_chunk, len(ordered))
        chunks.append(ordered[start:end])
        if end >= len(ordered):
            break
        start = end - 1  # share the boundary sample
    return chunks


def _pwl_expression(times: list[float], values: list[float]) -> str:
    """Nested-if ffmpeg expression for piecewise-linear values(t).

    Holds the first value before the first time and the last value
    after the last time (no extrapolation past the sampled range).
    """
    expr = f"{values[-1]:.4f}"
    for i in range(len(times) - 2, -1, -1):
        slope = (values[i + 1] - values[i]) / (times[i + 1] - times[i])
        expr = (f"if(lt(t,{times[i + 1]:.4f}),"
                f"{values[i]:.4f}+{slope:.4f}*(t-{times[i]:.4f}),"
                f"{expr})")
    return f"if(lt(t,{times[0]:.4f}),{values[0]:.4f},{expr})"


def build_tracked_position_expressions(
        samples: list[TrackSample], frame_w: int, frame_h: int,
        pad_px: float = TRACKED_BLUR_PAD_PX
) -> tuple[str, str, int, int] | None:
    """ffmpeg x/y expressions + fixed crop size for a moving blur box.

    Returns (x_expr, y_expr, crop_w, crop_h), or None when the track
    has fewer than two distinct-time samples. The crop size is fixed
    (crop w/h are evaluated once by ffmpeg): the largest sample box
    plus padding on every side. The position interpolates the
    per-sample box centres piecewise-linearly and is clamped so the
    box always stays inside the frame.
    """
    ordered = _ordered_samples(samples)
    if len(ordered) < 2:
        return None
    crop_w = min(frame_w, max(1, int(round(max(s.bbox.w for s in ordered)))
                              + 2 * int(round(pad_px))))
    crop_h = min(frame_h, max(1, int(round(max(s.bbox.h for s in ordered)))
                              + 2 * int(round(pad_px))))
    times = [s.time for s in ordered]
    xs = [s.bbox.x + s.bbox.w / 2 - crop_w / 2 for s in ordered]
    ys = [s.bbox.y + s.bbox.h / 2 - crop_h / 2 for s in ordered]
    max_x = float(frame_w - crop_w)
    max_y = float(frame_h - crop_h)
    x_expr = (f"clip({_pwl_expression(times, xs)},0,{max_x:.4f})"
              if max_x > 0 else "0")
    y_expr = (f"clip({_pwl_expression(times, ys)},0,{max_y:.4f})"
              if max_y > 0 else "0")
    return x_expr, y_expr, crop_w, crop_h


class FilterGraph:
    """Linear ffmpeg filter_complex builder for replacement steps."""

    def __init__(self, input_label: str = "0:v") -> None:
        self.filters: list[str] = []
        self.label = input_label
        self._counter = 0
        self.log: list[str] = []

    def _next_label(self) -> str:
        self._counter += 1
        return f"rep{self._counter}"

    def simple(self, expression: str, note: str = "") -> None:
        out = self._next_label()
        self.filters.append(f"[{self.label}]{expression}[{out}]")
        self.label = out
        if note:
            self.log.append(note)

    def blur_region(self, box: BBox, frame_w: int, frame_h: int,
                    start: float, end: float, radius: int = 20) -> None:
        x, y, w, h = _ints(box, frame_w, frame_h)
        luma_radius, chroma_radius = _blur_radii(w, h, radius)
        main = self._next_label()
        tmp = self._next_label()
        blur = self._next_label()
        out = self._next_label()
        self.filters.append(f"[{self.label}]split[{main}][{tmp}]")
        self.filters.append(
            f"[{tmp}]crop={w}:{h}:{x}:{y},"
            f"boxblur=lr={luma_radius}:lp=2:cr={chroma_radius}:cp=2"
            f"[{blur}]")
        self.filters.append(
            f"[{main}][{blur}]overlay={x}:{y}:{_enable(start, end)}[{out}]")
        self.label = out
        self.log.append(f"blur box=({x},{y},{w},{h}) t={start:.2f}-{end:.2f} "
                        f"radius={radius} effective lr={luma_radius} "
                        f"cr={chroma_radius}")

    def blur_region_tracked(self, samples: list[TrackSample],
                            frame_w: int, frame_h: int,
                            start: float, end: float, radius: int = 20,
                            pad_px: float = TRACKED_BLUR_PAD_PX) -> None:
        """Blur following a moving box (S9): one split/crop/overlay
        triple per chunk whose crop + overlay positions are per-frame
        ffmpeg expressions interpolating the track samples.

        Verified 2026-11-12 on ffmpeg 8.1.2: crop x/y expressions
        evaluate per frame (a moving crop over a static scene changes
        the output pixels; a static crop does not). The expressions
        hold the endpoint boxes outside the sampled range, and the
        last chunk's enable window extends to ``end`` (the region end
        is one sample interval past the last sample by construction).
        """
        chunks = tracked_blur_chunks(samples)
        for index, chunk in enumerate(chunks):
            built = build_tracked_position_expressions(
                chunk, frame_w, frame_h, pad_px)
            if built is None:
                continue
            x_expr, y_expr, cw, ch = built
            chunk_start = start if index == 0 else chunk[0].time
            chunk_end = end if index == len(chunks) - 1 else chunk[-1].time
            if chunk_end <= chunk_start:
                continue
            luma_radius, chroma_radius = _blur_radii(cw, ch, radius)
            main = self._next_label()
            tmp = self._next_label()
            blur = self._next_label()
            out = self._next_label()
            self.filters.append(f"[{self.label}]split[{main}][{tmp}]")
            self.filters.append(
                f"[{tmp}]crop=w={cw}:h={ch}:x='{x_expr}':y='{y_expr}',"
                f"boxblur=lr={luma_radius}:lp=2:cr={chroma_radius}:cp=2"
                f"[{blur}]")
            self.filters.append(
                f"[{main}][{blur}]overlay=x='{x_expr}':y='{y_expr}':"
                f"{_enable(chunk_start, chunk_end)}[{out}]")
            self.label = out
            self.log.append(
                f"tracked blur box={cw}x{ch} t={chunk_start:.2f}-"
                f"{chunk_end:.2f} samples={len(chunk)} "
                f"radius={radius} effective lr={luma_radius} "
                f"cr={chroma_radius}")

    def build(self) -> tuple[str, str]:
        """Returns (filter_complex_string, final_video_label)."""
        return ";".join(self.filters), self.label


def _write_textfile(text: str, work_dir: Path, name: str) -> Path:
    path = work_dir / name
    path.write_text(text, encoding="utf-8")
    return path


def build_replacement_filters(
        specs: list[ReplacementSpec], frame_size: tuple[int, int],
        work_dir: str | Path, font_path: str | None = None,
        authorization_type: str = "SYNTHETIC_FIXTURE",
        commercial_rights_confirmed: bool = True) -> tuple[str, str, list[str]]:
    """Build the filter_complex fragment for a list of replacements.

    Returns (filter_complex, final_label, log). An empty spec list
    returns ("", "0:v", []). Validation runs first: any refused spec
    aborts the whole build (no partial application).
    """
    fw, fh = frame_size
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        validate_replacement(spec, authorization_type,
                             commercial_rights_confirmed)
    if not specs:
        return "", "0:v", []
    modes = {s.mode for s in specs}
    if ReplacementMode.CROP_AND_REFRAME in modes and len(modes) > 1:
        raise ReplacementRefused(
            "CROP_AND_REFRAME cannot be mixed with other replacement "
            "modes in one graph (it changes the frame size the other "
            "regions are positioned in)")
    font = font_path or find_vietnamese_font()
    graph = FilterGraph()
    for index, spec in enumerate(specs, start=1):
        region = spec.region
        if spec.mode == ReplacementMode.SMART_OVERLAY:
            if font is None:
                raise UnsupportedReplacement(
                    "SMART_OVERLAY needs a Vietnamese-capable font; none "
                    "found in this environment")
            params = spec.parameters
            pad = int(params.get("padding_px", 12))
            panel = spec.parameters.get("panel_color", "black")
            opacity = float(params.get("panel_opacity", 0.72))
            font_size = params.get("font_size")
            if font_size is None:
                font_size = int(min(72, max(20, region.bbox.h * 0.6)))
            font_color = params.get("font_color", "white")
            box = region.bbox.expand(pad, fw, fh)
            x, y, w, h = _ints(box, fw, fh)
            textfile = _write_textfile(spec.vietnamese_text, work,
                                       f"overlay_{index:03d}.txt")
            graph.simple(
                f"drawbox=x={x}:y={y}:w={w}:h={h}:color={panel}@{opacity}:"
                f"t=fill:{_enable(region.start_time, region.end_time)}",
                f"overlay panel box=({x},{y},{w},{h}) "
                f"t={region.start_time:.2f}-{region.end_time:.2f}")
            graph.simple(
                f"drawtext=fontfile={font}:fontsize={font_size}:"
                f"fontcolor={font_color}:textfile={textfile}:"
                f"expansion=none:x={x}+({w}-text_w)/2:"
                f"y={y}+({h}-text_h)/2:"
                f"{_enable(region.start_time, region.end_time)}",
                f"overlay text track={region.text_id} "
                f"font_size={font_size}")
        elif spec.mode == ReplacementMode.LOCAL_BLUR:
            radius = int(spec.parameters.get("blur_radius", 20))
            samples = list(region.track_samples)
            if (len(samples) >= 2
                    and track_displacement_px(samples)
                    > TRACKED_BLUR_STATIC_PX):
                # Moving track: the blur box follows the interpolated
                # per-frame positions instead of one static box (S9).
                # The approval/authorization gate above already ran;
                # protected classes without an approved removal never
                # reach this branch (validate_replacement refuses).
                pad = float(spec.parameters.get(
                    "tracked_blur_pad_px", TRACKED_BLUR_PAD_PX))
                graph.blur_region_tracked(
                    samples, fw, fh, region.start_time, region.end_time,
                    radius=radius, pad_px=pad)
            else:
                graph.blur_region(region.bbox, fw, fh, region.start_time,
                                  region.end_time, radius=radius)
        elif spec.mode == ReplacementMode.CROP_AND_REFRAME:
            band = region.bbox
            if band.w < 0.9 * fw:
                raise ReplacementRefused(
                    "CROP_AND_REFRAME needs a full-width subtitle band "
                    f"(band width {band.w:.0f}px < 90% of {fw}px); use "
                    "LOCAL_BLUR or SMART_OVERLAY instead")
            cut_h = int(round(band.h))
            if band.y < fh * 0.5:
                graph.simple(f"crop={fw}:{fh - cut_h}:0:{cut_h}",
                             f"crop top band h={cut_h}")
                fh = fh - cut_h
            else:
                graph.simple(f"crop={fw}:{fh - cut_h}:0:0",
                             f"crop bottom band h={cut_h}")
                fh = fh - cut_h
        elif spec.mode == ReplacementMode.BACKGROUND_RECONSTRUCTION:
            raise UnsupportedReplacement(
                "BACKGROUND_RECONSTRUCTION is a frame-based mode; use "
                "apply_inpaint_replacement, not the filter graph")
        else:  # pragma: no cover - enum guard
            raise ValueError(f"unknown replacement mode {spec.mode}")
    filter_complex, label = graph.build()
    return filter_complex, label, graph.log


# Classifications the blur-and-subtitle default handling applies to.
# Product labels, branding, and creator attribution are NOT here:
# they are preserved unless the user authorized + explicitly approved
# their edit (allow_protected + removal_approved, see below).
BLUR_SUBTITLE_CLASSIFICATIONS = (
    TextClassification.SUBTITLE,
    TextClassification.PROMOTIONAL_OVERLAY,
)


def replacement_subtitle_slots(
        specs: list[ReplacementSpec], authorization_type: str,
        commercial_rights_confirmed: bool,
        allow_protected: bool = False
) -> tuple[list[SubtitleSlot], list[dict[str, Any]]]:
    """Subtitle slots for the blur-and-subtitle default handling.

    Default text handling for the Douyin test job (Mai, 2026-11-12):
    blur approved Chinese subtitle/promotional regions, then overlay
    Vietnamese subtitles on top. This function emits one SubtitleSlot
    per approved LOCAL_BLUR spec — the timing/region data the subtitle
    stage (Subagent B) consumes to place the Vietnamese overlay. The
    slots carry no translated text; translation is B's scope.

    Every spec passes ``validate_replacement`` first (unapproved or
    unauthorized specs raise). Specs that are not LOCAL_BLUR, or whose
    classification is protected, are SKIPPED with an audit entry in
    the second return value — never silently, never as slots.

    ``allow_protected`` is an explicit caller override for the case
    where the user authorized + explicitly approved editing a
    protected region (removal_approved recorded on the region). It
    defaults to False; without removal_approved the gate refuses
    before this function ever sees the spec.
    """
    slots: list[SubtitleSlot] = []
    skipped: list[dict[str, Any]] = []
    for spec in specs:
        validate_replacement(spec, authorization_type,
                             commercial_rights_confirmed)
        region = spec.region
        if spec.mode != ReplacementMode.LOCAL_BLUR:
            skipped.append({
                "text_id": region.text_id,
                "reason": f"mode is {spec.mode.value}, not LOCAL_BLUR; "
                          f"no subtitle slot (overlay modes render "
                          f"their own text)",
            })
            continue
        if region.classification not in BLUR_SUBTITLE_CLASSIFICATIONS:
            if not (allow_protected and region.removal_approved):
                skipped.append({
                    "text_id": region.text_id,
                    "reason": f"classification "
                              f"{region.classification.value} is "
                              f"protected and preserved; subtitle slots "
                              f"are emitted only for SUBTITLE / "
                              f"PROMOTIONAL_OVERLAY unless the user "
                              f"authorized + explicitly approved the "
                              f"edit (allow_protected)",
                })
                continue
        slots.append(SubtitleSlot(
            slot_id=f"slot-{region.text_id}",
            text_id=region.text_id,
            track_id=region.track_id,
            start_time=region.start_time,
            end_time=region.end_time,
            bbox=region.bbox,
            frame_size=region.frame_size,
            classification=region.classification,
            original_text=region.original_text))
    return slots, skipped


def mask_to_replacement(mask: MaskSpec, region: TextRegion,
                        vietnamese_text: str = "") -> ReplacementSpec:
    """Convert a MaskSpec (+ its region) into a ReplacementSpec.

    The mask's mode selects the replacement mode; the mask box (when
    present) overrides the region box for this edit.
    """
    mode_map = {"overlay": ReplacementMode.SMART_OVERLAY,
                "blur": ReplacementMode.LOCAL_BLUR,
                "inpaint": ReplacementMode.BACKGROUND_RECONSTRUCTION}
    mode = mode_map.get(mask.mode)
    if mode is None:
        raise ValueError(f"unknown mask mode {mask.mode!r}")
    effective = region
    if mask.bbox is not None:
        effective = TextRegion(
            text_id=region.text_id, track_id=region.track_id,
            original_text=region.original_text,
            start_time=mask.start_time or region.start_time,
            end_time=mask.end_time or region.end_time,
            bbox=mask.bbox, frame_size=region.frame_size,
            polygon=region.polygon, ocr_confidence=region.ocr_confidence,
            classification=region.classification,
            classification_reason=region.classification_reason,
            source=region.source, detection_method=region.detection_method,
            translated_text=region.translated_text,
            needs_review=region.needs_review,
            review_reasons=list(region.review_reasons),
            removal_approved=region.removal_approved,
            removal_approval=region.removal_approval)
    return ReplacementSpec(
        region=effective, mode=mode, vietnamese_text=vietnamese_text,
        parameters=dict(mask.parameters), approved=mask.approved,
        approved_by="", approval_note=mask.approval_note)


def segment_track(samples: list[tuple[float, BBox]],
                  segment_sec: float = 1.0) -> list[tuple[float, float, BBox]]:
    """Split tracked (time, box) samples into per-segment median boxes.

    Tracked masks are approximated as piecewise-static boxes, one per
    segment. Shorter segments track motion better; longer segments
    keep the filter graph small. Documented approximation.
    """
    if not samples:
        return []
    ordered = sorted(samples)
    segments: list[tuple[float, float, BBox]] = []
    start = ordered[0][0]
    current: list[BBox] = [ordered[0][1]]
    for time_sec, box in ordered[1:]:
        if time_sec - start >= segment_sec:
            segments.append((start, time_sec, _median_box(current)))
            start, current = time_sec, [box]
        else:
            current.append(box)
    segments.append((start, ordered[-1][0] + segment_sec,
                     _median_box(current)))
    return segments


def _median_box(boxes: list[BBox]) -> BBox:
    return BBox(float(np.median([b.x for b in boxes])),
                float(np.median([b.y for b in boxes])),
                float(np.median([b.w for b in boxes])),
                float(np.median([b.h for b in boxes])))


# ---------------------------------------------------------------------
# standalone application
# ---------------------------------------------------------------------

def apply_replacements(video_path: str | Path, specs: list[ReplacementSpec],
                       output_path: str | Path, frame_size: tuple[int, int],
                       authorization_type: str,
                       commercial_rights_confirmed: bool,
                       work_dir: str | Path | None = None,
                       font_path: str | None = None,
                       crf: int = 18) -> tuple[Path, list[str]]:
    """Render replacements onto a copy of the video (standalone).

    The source is never modified; output is a new file. Audio is
    copied unchanged. For production, prefer the single-pass export
    in ``export.py`` which composes these filters with the reframe.
    """
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="aff_rep_"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        filter_complex, label, log = build_replacement_filters(
            specs, frame_size, work, font_path=font_path,
            authorization_type=authorization_type,
            commercial_rights_confirmed=commercial_rights_confirmed)
        if not filter_complex:
            raise ReplacementRefused("no replacement specs supplied")
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        argv = ["ffmpeg", "-v", "error", "-i", str(video_path),
                "-filter_complex", filter_complex,
                "-map", f"[{label}]", "-map", "0:a?",
                "-c:v", "libx264", "-crf", str(crf), "-preset", "veryfast",
                "-pix_fmt", "yuv420p", "-c:a", "copy",
                "-movflags", "+faststart", "-y", str(out)]
        proc = run_command(argv, timeout=900.0)
        if proc.returncode != 0 or not out.is_file():
            raise ProbeError(f"replacement render failed: "
                             f"{(proc.stderr or '').strip()[:300]}")
        return out, log
    finally:
        if work_dir is None:
            shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------
# mask preview (before/after review data)
# ---------------------------------------------------------------------

def render_mask_preview(frame_path: str | Path, masks: list[MaskSpec],
                        output_path: str | Path,
                        frame_size: tuple[int, int] | None = None) -> Path:
    """Draw mask outlines + labels over a frame (review preview).

    This is review data, not a render: it shows WHERE masks apply and
    in which mode. The actual edit is applied by the filter builders.
    """
    img = Image.open(frame_path).convert("RGB")
    if frame_size and img.size != frame_size:
        img = img.resize(frame_size, Image.BILINEAR)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype(find_vietnamese_font()
                                  or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                                  22)
    except OSError:
        font = ImageFont.load_default()
    for mask in masks:
        if mask.bbox is None and not mask.polygon:
            continue
        if mask.polygon:
            points = [(px, py) for px, py in mask.polygon]
            draw.polygon(points, fill=(255, 60, 60, 90),
                         outline=(255, 60, 60, 255), width=3)
            label_xy = points[0]
        else:
            box = mask.bbox
            assert box is not None
            draw.rectangle([box.x, box.y, box.x2, box.y2],
                           fill=(255, 60, 60, 90),
                           outline=(255, 60, 60, 255), width=3)
            label_xy = (box.x, box.y)
        label = f"{mask.mask_id} [{mask.mode}]"
        draw.text((label_xy[0], max(0, label_xy[1] - 26)), label,
                  fill=(255, 60, 60, 255), font=font)
    out = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path)
    return out_path


def preview_before_after(video_path: str | Path, time_sec: float,
                         masks: list[MaskSpec], out_dir: str | Path,
                         frame_size: tuple[int, int] | None = None) -> dict[str, Any]:
    """Extract one frame and render the mask preview next to it."""
    from .analysis import extract_frame_at
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    original = extract_frame_at(video_path, time_sec, out / "before.jpg")
    preview = render_mask_preview(original, masks, out / "after_preview.jpg",
                                  frame_size=frame_size)
    return {
        "time": time_sec,
        "before": str(original),
        "after_preview": str(preview),
        "masks": [m.to_dict() for m in masks],
        "note": "after_preview shows mask placement only; the real edit "
                "is applied by the filter builders",
    }


# ---------------------------------------------------------------------
# background reconstruction (cv2 inpainting, frame-based)
# ---------------------------------------------------------------------

def apply_inpaint_replacement(video_path: str | Path, spec: ReplacementSpec,
                              output_path: str | Path,
                              authorization_type: str,
                              commercial_rights_confirmed: bool,
                              work_dir: str | Path | None = None,
                              max_seconds: float = 30.0,
                              dilate_px: int = 3,
                              crf: int = 18) -> tuple[Path, list[str]]:
    """Inpaint one region's frames with cv2 (TELEA) and re-encode.

    Frame-based by nature: all frames are extracted, the region is
    inpainted on frames inside [start, end), and the video is
    re-encoded with the original audio. Guarded to short clips
    (``max_seconds``) because full-frame extraction is expensive.
    Raises UnsupportedReplacement when cv2 is unavailable.
    """
    validate_replacement(spec, authorization_type,
                         commercial_rights_confirmed)
    try:
        import cv2
    except ImportError as exc:
        raise UnsupportedReplacement(
            "BACKGROUND_RECONSTRUCTION needs OpenCV (cv2.inpaint); "
            "cv2 is not installed in this environment") from exc
    from .probe import probe_source
    source = probe_source(video_path)
    if source.duration_sec > max_seconds:
        raise UnsupportedReplacement(
            f"inpainting is limited to clips of {max_seconds}s in Phase 1 "
            f"(source is {source.duration_sec:.1f}s); split the job or "
            "use LOCAL_BLUR / SMART_OVERLAY")
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="aff_inp_"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        frames_dir = work / "frames"
        frames_dir.mkdir(exist_ok=True)
        argv = ["ffmpeg", "-v", "error", "-i", str(video_path),
                "-q:v", "2", "-y", str(frames_dir / "f_%05d.png")]
        proc = run_command(argv, timeout=600.0)
        if proc.returncode != 0:
            raise ProbeError(f"frame extraction for inpaint failed: "
                             f"{(proc.stderr or '').strip()[:200]}")
        frames = sorted(frames_dir.glob("f_*.png"))
        if not frames:
            raise ProbeError("no frames extracted for inpainting")
        fps = source.fps or 30.0
        box = spec.region.bbox.clamp(source.width, source.height)
        x, y = int(round(box.x)), int(round(box.y))
        w, h = int(round(box.w)), int(round(box.h))
        painted = 0
        for index, frame_path in enumerate(frames):
            time_sec = index / fps
            if not (spec.region.start_time <= time_sec < spec.region.end_time):
                continue
            img = cv2.imread(str(frame_path))
            if img is None:
                continue
            mask = np.zeros(img.shape[:2], dtype=np.uint8)
            x0 = max(0, x - dilate_px)
            y0 = max(0, y - dilate_px)
            x1 = min(img.shape[1], x + w + dilate_px)
            y1 = min(img.shape[0], y + h + dilate_px)
            mask[y0:y1, x0:x1] = 255
            img = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)
            cv2.imwrite(str(frame_path), img)
            painted += 1
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        argv = ["ffmpeg", "-v", "error", "-framerate", f"{fps:.3f}",
                "-i", str(frames_dir / "f_%05d.png"),
                "-i", str(video_path),
                "-map", "0:v", "-map", "1:a?",
                "-c:v", "libx264", "-crf", str(crf), "-preset", "veryfast",
                "-pix_fmt", "yuv420p", "-c:a", "copy",
                "-movflags", "+faststart", "-shortest", "-y", str(out)]
        proc = run_command(argv, timeout=900.0)
        if proc.returncode != 0 or not out.is_file():
            raise ProbeError(f"inpaint re-encode failed: "
                             f"{(proc.stderr or '').strip()[:300]}")
        return out, [f"inpainted {painted}/{len(frames)} frames "
                     f"box=({x},{y},{w},{h}) t={spec.region.start_time:.2f}-"
                     f"{spec.region.end_time:.2f} method=cv2.INPAINT_TELEA"]
    finally:
        if work_dir is None:
            shutil.rmtree(work, ignore_errors=True)
