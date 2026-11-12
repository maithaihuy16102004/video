"""Video analysis: measured signals about a source video.

Stages (all measured, no invented claims):
  * scene boundaries — ffmpeg ``select`` scene-change detection
  * motion intensity — numpy frame differencing on sampled frames
  * silence segments — ffmpeg ``silencedetect``
  * faces — OpenCV Haar cascade when cv2 is installed, else an
    explicit "unavailable" status (never a faked result)
  * hands — unavailable in Phase 1 (no hand model installed); the
    status says so plainly
  * text-region candidates — edge-density heuristic (always) or MSER
    (when cv2 is installed); candidates, not OCR results
  * watermark candidates — temporal-persistence heuristic on corner
    regions; candidates only, never a removal instruction

"Product visibility" here is a heuristic proxy (center-region edge
activity). Real product recognition/description is the Gemini stage
owned by Subagent B; this module labels its proxy as such and leaves
``visual_description`` empty for that stage to fill.
"""
from __future__ import annotations

import math
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .capabilities import cv2_info, run_command
from .models import (AnalysisReport, AudioSegment, BBox, FaceDetection,
                     SceneSegment, SourceInfo, TextClassification,
                     TextRegion, WatermarkCandidate)
from .probe import ProbeError, probe_source

# Heuristic thresholds (documented, tunable, measured against the
# synthetic fixture — see the Phase 1 report for the numbers).
MOTION_LOW_MAX = 0.015
MOTION_MEDIUM_MAX = 0.06
VISIBILITY_CLEAR_MIN = 0.08
VISIBILITY_PARTIAL_MIN = 0.03
SCENE_MIN_GAP_SEC = 0.25
TEXT_BAND_MIN_WIDTH_FRAC = 0.25

_SHOWINFO_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")
_SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9]+(?:\.[0-9]+)?)")
_SILENCE_END_RE = re.compile(
    r"silence_end:\s*([0-9]+(?:\.[0-9]+)?)\s*\|\s*silence_duration:\s*([0-9.]+)")


# ---------------------------------------------------------------------
# frame extraction
# ---------------------------------------------------------------------

def extract_frame_at(video_path: str | Path, time_sec: float,
                     out_path: str | Path, width: int | None = None) -> Path:
    """Extract one frame (ffmpeg applies display rotation by default)."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, time_sec):.3f}",
            "-i", str(video_path), "-frames:v", "1"]
    if width:
        argv += ["-vf", f"scale={width}:-2"]
    argv += ["-q:v", "2", "-y", str(out)]
    proc = run_command(argv, timeout=120.0)
    if proc.returncode != 0 or not out.is_file():
        raise ProbeError(f"frame extraction failed at t={time_sec}: "
                         f"{(proc.stderr or '').strip()[:200]}")
    return out


def extract_frame_sequence(video_path: str | Path, sample_fps: float,
                           out_dir: str | Path,
                           width: int | None = 320) -> list[tuple[float, Path]]:
    """Extract frames at ``sample_fps``; returns [(time, path), ...]."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pattern = str(out / "frame_%04d.jpg")
    vf = f"fps={sample_fps}"
    if width:
        vf += f",scale={width}:-2"
    argv = ["ffmpeg", "-v", "error", "-i", str(video_path), "-vf", vf,
            "-q:v", "3", "-y", pattern]
    proc = run_command(argv, timeout=300.0)
    if proc.returncode != 0:
        raise ProbeError(f"frame sequence extraction failed: "
                         f"{(proc.stderr or '').strip()[:200]}")
    frames = sorted(out.glob("frame_*.jpg"))
    return [(i / sample_fps, p) for i, p in enumerate(frames)]


def load_gray(path: str | Path, width: int | None = None) -> np.ndarray:
    """Load an image as a float32 grayscale numpy array."""
    img = Image.open(path).convert("L")
    if width and img.width != width:
        height = max(1, round(img.height * width / img.width))
        img = img.resize((width, height), Image.BILINEAR)
    return np.asarray(img, dtype=np.float32)


# ---------------------------------------------------------------------
# scene cuts + silence
# ---------------------------------------------------------------------

def detect_scene_cuts(video_path: str | Path, duration_sec: float,
                      threshold: float = 0.3) -> list[float]:
    """Scene-change timestamps via ffmpeg select/showinfo.

    Returns cut times in seconds, always starting with 0.0. Cuts
    closer than SCENE_MIN_GAP_SEC are merged; a cut within 0.3s of
    the end is dropped (no trailing micro-scene).

    Default threshold 0.3: measured on the synthetic fixture, real
    cuts score 0.37-0.42 while fast in-scene motion (sliding promo)
    scores <= 0.03, so 0.3 sits in a wide clean gap. The previous
    0.4 missed a genuine cut scoring 0.37.
    """
    argv = ["ffmpeg", "-v", "info", "-i", str(video_path), "-an",
            "-filter:v", f"select='gt(scene,{threshold})',showinfo",
            "-f", "null", "-"]
    proc = run_command(argv, timeout=300.0)
    if proc.returncode != 0:
        raise ProbeError(f"scene detection failed: "
                         f"{(proc.stderr or '').strip()[:200]}")
    cuts = [0.0]
    for line in (proc.stderr or "").splitlines():
        if "showinfo" not in line:
            continue
        match = _SHOWINFO_RE.search(line)
        if match:
            cuts.append(float(match.group(1)))
    cuts = sorted(set(round(c, 3) for c in cuts))
    merged: list[float] = []
    for cut in cuts:
        if merged and cut - merged[-1] < SCENE_MIN_GAP_SEC:
            continue
        merged.append(cut)
    if len(merged) > 1 and duration_sec - merged[-1] < 0.3:
        merged.pop()
    return merged


def detect_silence(video_path: str | Path, duration_sec: float,
                   noise_db: float = -40.0,
                   min_duration: float = 0.5) -> list[AudioSegment]:
    """Silence segments via ffmpeg silencedetect (empty if no audio)."""
    argv = ["ffmpeg", "-v", "info", "-i", str(video_path),
            "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
            "-f", "null", "-"]
    proc = run_command(argv, timeout=300.0)
    if proc.returncode != 0:
        return []
    segments: list[AudioSegment] = []
    pending_start: float | None = None
    for line in (proc.stderr or "").splitlines():
        start = _SILENCE_START_RE.search(line)
        if start:
            pending_start = float(start.group(1))
            continue
        end = _SILENCE_END_RE.search(line)
        if end and pending_start is not None:
            segments.append(AudioSegment(
                start_time=pending_start, end_time=float(end.group(1)),
                kind="silence", source="silencedetect", confidence=0.9))
            pending_start = None
    if pending_start is not None and duration_sec > pending_start:
        segments.append(AudioSegment(
            start_time=pending_start, end_time=duration_sec,
            kind="silence", source="silencedetect", confidence=0.9))
    return segments


def non_silence_segments(silences: list[AudioSegment],
                         duration_sec: float) -> list[AudioSegment]:
    """Complement of the silence list: ranges where audio is present."""
    out: list[AudioSegment] = []
    cursor = 0.0
    for seg in sorted(silences, key=lambda s: s.start_time):
        if seg.start_time > cursor:
            out.append(AudioSegment(start_time=cursor,
                                    end_time=seg.start_time,
                                    kind="non_silence",
                                    source="silencedetect",
                                    confidence=0.9))
        cursor = max(cursor, seg.end_time)
    if cursor < duration_sec:
        out.append(AudioSegment(start_time=cursor, end_time=duration_sec,
                                kind="non_silence", source="silencedetect",
                                confidence=0.9))
    return out


# ---------------------------------------------------------------------
# motion + visibility heuristics
# ---------------------------------------------------------------------

def motion_series(grays: list[np.ndarray]) -> list[float]:
    """Mean absolute frame difference (0..1) between consecutive frames."""
    values: list[float] = []
    for prev, cur in zip(grays, grays[1:]):
        if prev.shape != cur.shape:
            continue
        values.append(float(np.mean(np.abs(cur - prev)) / 255.0))
    return values


def motion_label(intensity: float) -> str:
    if intensity < MOTION_LOW_MAX:
        return "low"
    if intensity < MOTION_MEDIUM_MAX:
        return "medium"
    return "high"


def edge_activity(gray: np.ndarray, region: tuple[float, float, float, float] | None = None) -> float:
    """Mean gradient magnitude in a region (fractions of frame size).

    ``region`` is (x0, y0, x1, y1) in 0..1 fractions; None = whole frame.
    """
    if region is None:
        crop = gray
    else:
        h, w = gray.shape
        x0, y0, x1, y1 = region
        crop = gray[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    if crop.size == 0:
        return 0.0
    gy, gx = np.gradient(crop)
    return float(np.mean(np.hypot(gx, gy)) / 255.0)


def visibility_label(score: float) -> str:
    if score >= VISIBILITY_CLEAR_MIN:
        return "clear"
    if score >= VISIBILITY_PARTIAL_MIN:
        return "partial"
    return "absent"


# ---------------------------------------------------------------------
# faces (cv2 Haar, optional)
# ---------------------------------------------------------------------

def detect_faces(frames: list[tuple[float, Path]], frame_size: tuple[int, int],
                 cascade_path: str | None) -> tuple[list[FaceDetection], str, str]:
    """Haar face detection. Returns (faces, status, detail)."""
    if cascade_path is None:
        return [], "unavailable", ("cv2 Haar cascade not available in this "
                                   "environment")
    try:
        import cv2
    except ImportError:
        return [], "unavailable", "cv2 is not installed"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        return [], "unavailable", f"cascade failed to load: {cascade_path}"
    fw, fh = frame_size
    faces: list[FaceDetection] = []
    for time_sec, path in frames:
        img = cv2.imread(str(path))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        scale_x = fw / gray.shape[1]
        scale_y = fh / gray.shape[0]
        for (x, y, w, h) in cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)):
            faces.append(FaceDetection(
                time=round(time_sec, 3),
                bbox=BBox(x * scale_x, y * scale_y, w * scale_x, h * scale_y),
                confidence=0.5, method="haar_frontalface_default"))
    return faces, "ok", f"Haar cascade, {len(frames)} sampled frames"


# ---------------------------------------------------------------------
# text-region candidates
# ---------------------------------------------------------------------

def edge_band_candidates(gray: np.ndarray, frame_size: tuple[int, int],
                         time_sec: float) -> list[BBox]:
    """Subtitle-band heuristic: rows of high horizontal-edge density
    in the bottom 30% of the frame. Low-confidence candidates only."""
    h, w = gray.shape
    gx = np.abs(np.diff(gray, axis=1))
    row_mean = gx.mean(axis=1)
    band_top = int(h * 0.70)
    band = row_mean[band_top:]
    if band.size == 0:
        return []
    threshold = max(float(band.mean()) + 1.5 * float(band.std()), 6.0)
    active = band > threshold
    boxes: list[BBox] = []
    start = None
    for i, flag in enumerate(active):
        if flag and start is None:
            start = i
        if (not flag or i == len(active) - 1) and start is not None:
            end = i if not flag else i + 1
            run_h = end - start
            if 4 <= run_h <= int(h * 0.25):
                rows = gx[band_top + start:band_top + end]
                col_mean = rows.mean(axis=0)
                cols = np.where(col_mean > threshold * 0.5)[0]
                if cols.size and (cols.max() - cols.min()) >= w * TEXT_BAND_MIN_WIDTH_FRAC:
                    scale_x = frame_size[0] / w
                    scale_y = frame_size[1] / h
                    boxes.append(BBox(
                        float(cols.min()) * scale_x,
                        float(band_top + start) * scale_y,
                        float(cols.max() - cols.min()) * scale_x,
                        float(run_h) * scale_y))
            start = None
    return boxes


def mser_candidates(frame_path: str | Path,
                    frame_size: tuple[int, int]) -> list[BBox]:
    """MSER text-region candidates (cv2 only)."""
    import cv2
    img = cv2.imread(str(frame_path))
    if img is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mser = cv2.MSER_create(_min_area=60, _max_area=int(gray.size * 0.2))
    regions, _ = mser.detectRegions(gray)
    fw, fh = frame_size
    scale_x, scale_y = fw / gray.shape[1], fh / gray.shape[0]
    boxes: list[BBox] = []
    for points in regions:
        x, y, w, h = cv2.boundingRect(points.reshape(-1, 1, 2))
        if w < 10 or h < 8 or w > gray.shape[1] * 0.85:
            continue
        boxes.append(BBox(x * scale_x, y * scale_y, w * scale_x, h * scale_y))
    # Merge heavily-overlapping boxes.
    merged: list[BBox] = []
    for box in sorted(boxes, key=lambda b: (b.y, b.x)):
        for other in merged:
            if box.iou(other) > 0.3:
                other.x = min(other.x, box.x)
                other.y = min(other.y, box.y)
                other.w = max(other.x2, box.x2) - other.x
                other.h = max(other.y2, box.y2) - other.y
                break
        else:
            merged.append(box)
    return merged


def _merge_candidate_detections(
        detections: list[tuple[float, BBox, str]],
        frame_size: tuple[int, int], max_gap_sec: float = 2.0) -> list[TextRegion]:
    """Group per-frame candidate boxes into time-spanning TextRegions."""
    tracks: list[dict[str, Any]] = []
    for time_sec, box, method in sorted(detections):
        placed = False
        for track in tracks:
            last_box = track["boxes"][-1]
            gap = time_sec - track["last_time"]
            if gap <= max_gap_sec and box.iou(last_box) > 0.4:
                track["boxes"].append(box)
                track["last_time"] = time_sec
                placed = True
                break
        if not placed:
            tracks.append({"boxes": [box], "first_time": time_sec,
                           "last_time": time_sec, "method": method})
    regions: list[TextRegion] = []
    for i, track in enumerate(tracks, start=1):
        boxes = track["boxes"]
        median = BBox(
            float(np.median([b.x for b in boxes])),
            float(np.median([b.y for b in boxes])),
            float(np.median([b.w for b in boxes])),
            float(np.median([b.h for b in boxes])))
        regions.append(TextRegion(
            text_id=f"cand-{i:03d}", track_id=f"cand-track-{i:03d}",
            original_text="", start_time=track["first_time"],
            end_time=track["last_time"], bbox=median, frame_size=frame_size,
            classification=TextClassification.UNKNOWN,
            classification_reason="candidate only — classification needs OCR",
            source="candidate", detection_method=track["method"],
            ocr_confidence=0.0, needs_review=True,
            review_reasons=["text-region candidate, not an OCR result; "
                            "confirm content before any edit"]))
    return regions


# ---------------------------------------------------------------------
# watermark candidates (temporal persistence in corners)
# ---------------------------------------------------------------------

_CORNERS = {
    "top_left": (0.0, 0.0, 0.30, 0.20),
    "top_right": (0.70, 0.0, 1.0, 0.20),
    "bottom_left": (0.0, 0.80, 0.30, 1.0),
    "bottom_right": (0.70, 0.80, 1.0, 1.0),
}


def watermark_candidates(grays: list[np.ndarray], times: list[float],
                         frame_size: tuple[int, int]) -> list[WatermarkCandidate]:
    """Persistent corner graphics: low temporal variance + structure.

    A watermark/logo stays pixel-stable while the scene moves. This
    heuristic reports CANDIDATES with a persistence score; it never
    authorizes removal.
    """
    if len(grays) < 4:
        return []
    stack = np.stack(grays)
    mean_img = stack.mean(axis=0)
    std_img = stack.std(axis=0)
    gy, gx = np.gradient(mean_img)
    grad = np.hypot(gx, gy)
    h, w = mean_img.shape
    fw, fh = frame_size
    out: list[WatermarkCandidate] = []
    for name, (x0, y0, x1, y1) in _CORNERS.items():
        cx0, cy0, cx1, cy1 = int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)
        corner_std = std_img[cy0:cy1, cx0:cx1]
        corner_grad = grad[cy0:cy1, cx0:cx1]
        stable = (corner_std < 4.0) & (corner_grad > 10.0)
        frac = float(stable.mean())
        if frac < 0.02:
            continue
        ys, xs = np.where(stable)
        # Persistence: fraction of frames whose corner matches the mean.
        matches = 0
        for frame in grays:
            corner = frame[cy0:cy1, cx0:cx1]
            if float(np.mean(np.abs(corner - mean_img[cy0:cy1, cx0:cx1]))) < 6.0:
                matches += 1
        persistence = matches / len(grays)
        if persistence < 0.5:
            continue
        out.append(WatermarkCandidate(
            bbox=BBox(float(cx0 + xs.min()) * fw / w,
                      float(cy0 + ys.min()) * fh / h,
                      float(xs.max() - xs.min() + 1) * fw / w,
                      float(ys.max() - ys.min() + 1) * fh / h),
            region=name, first_seen=times[0], last_seen=times[-1],
            persistence=round(persistence, 3),
            confidence=round(persistence * 0.7, 3),
            method="temporal_persistence_corners"))
    return out


# ---------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------

def analyze_source(video_path: str | Path, sample_fps: float = 2.0,
                   scene_threshold: float = 0.3,
                   work_dir: str | Path | None = None,
                   keep_frames: bool = False) -> AnalysisReport:
    """Run the full measurement analysis on one source video."""
    source = probe_source(video_path)
    duration = source.duration_sec
    cuts = detect_scene_cuts(video_path, duration, threshold=scene_threshold)
    silences = detect_silence(video_path, duration) if source.has_audio else []
    audio_segments = list(silences) + non_silence_segments(silences, duration) \
        if source.has_audio else []

    cv2 = cv2_info()
    engine = "ffmpeg+numpy+cv2" if cv2["available"] else "ffmpeg+numpy"
    notes: list[str] = []
    if not cv2["available"]:
        notes.append(f"cv2 unavailable ({cv2.get('detail')}); face "
                     "detection and MSER text candidates skipped")

    tmp = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="aff_an_"))
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        frames = extract_frame_sequence(video_path, sample_fps, tmp / "frames")
        grays = [load_gray(p, width=320) for _, p in frames]
        times = [t for t, _ in frames]
        motion = motion_series(grays)
        motion_mean = float(np.mean(motion)) if motion else 0.0

        # Per-scene aggregation.
        scenes: list[SceneSegment] = []
        bounds = cuts + [duration]
        for i in range(len(bounds) - 1):
            start, end = bounds[i], bounds[i + 1]
            # Diffs straddling a cut belong to neither scene: the cut
            # itself is a huge frame difference and would otherwise
            # inflate the static scene before it (measured: scene 1
            # read "medium" from a single cut diff). Require the next
            # sample to fall inside the same scene.
            idx = [j for j, t in enumerate(times[:-1])
                   if start <= t < end and times[j + 1] < end
                   and j < len(motion)]
            scene_motion = float(np.mean([motion[j] for j in idx])) if idx else 0.0
            scene_frames = [grays[j] for j, t in enumerate(times)
                            if start <= t < end]
            vis_score = 0.0
            if scene_frames:
                vis_score = float(np.mean([
                    edge_activity(g, region=(0.25, 0.2, 0.75, 0.8))
                    for g in scene_frames]))
            label = visibility_label(vis_score)
            suggested = []
            if scene_motion >= MOTION_MEDIUM_MAX:
                suggested.append("high motion — prefer short cuts")
            if not any(a.kind == "non_silence" and a.start_time < end
                       and a.end_time > start for a in audio_segments):
                suggested.append("no audio in this range — narration can "
                                 "be placed freely")
            scenes.append(SceneSegment(
                scene_id=f"scene-{i + 1:02d}", start_time=round(start, 3),
                end_time=round(end, 3), motion_intensity=round(scene_motion, 4),
                motion_label=motion_label(scene_motion),
                product_visibility_score=round(vis_score, 4),
                product_visibility=label,
                product_visibility_method=(
                    "heuristic proxy: center-region edge activity; NOT "
                    "product recognition (Gemini stage fills real "
                    "product visibility)"),
                suggested_edit="; ".join(suggested),
                confidence=0.6,
                method_notes=["scene cut: ffmpeg select/showinfo",
                              "motion: numpy frame differencing",
                              "visibility: center edge-activity proxy"]))

        # Faces (cv2 only).
        face_frames = [(t, p) for t, p in frames[::max(1, int(sample_fps))]]
        faces, faces_status, faces_detail = detect_faces(
            face_frames, (source.width, source.height),
            cv2.get("haar_cascade") if cv2["available"] else None)

        # Text candidates (1 fps sampling).
        detections: list[tuple[float, BBox, str]] = []
        step = max(1, int(sample_fps))
        for j in range(0, len(frames), step):
            t, path = frames[j]
            gray_full = load_gray(path)  # sampled-frame resolution
            if cv2["available"]:
                try:
                    boxes = mser_candidates(path, (source.width, source.height))
                    method = "mser"
                except Exception:  # noqa: BLE001 - fall back to heuristic
                    boxes = edge_band_candidates(
                        gray_full, (source.width, source.height), t)
                    method = "edge_density_heuristic"
            else:
                boxes = edge_band_candidates(
                    gray_full, (source.width, source.height), t)
                method = "edge_density_heuristic"
            for box in boxes:
                detections.append((t, box, method))
        candidates = _merge_candidate_detections(
            detections, (source.width, source.height))

        # Watermark candidates on the sampled frames.
        watermarks = watermark_candidates(grays, times,
                                          (source.width, source.height))

        motion_summary = {
            "mean": round(motion_mean, 4),
            "max": round(max(motion), 4) if motion else 0.0,
            "label": motion_label(motion_mean),
            "samples": len(motion),
            "method": "mean absolute frame difference at "
                      f"{sample_fps} fps, 320px-wide grayscale",
        }
        return AnalysisReport(
            source=source, scenes=scenes, faces=faces,
            faces_status=faces_status, faces_status_detail=faces_detail,
            watermark_candidates=watermarks, text_candidates=candidates,
            audio_segments=sorted(audio_segments, key=lambda a: a.start_time),
            motion_summary=motion_summary, engine=engine,
            engine_detail=("scene cuts: ffmpeg select/showinfo; motion: "
                           "numpy differencing; silence: silencedetect; "
                           f"faces: {faces_status}; text candidates: "
                           f"{'mser' if cv2['available'] else 'edge heuristic'}; "
                           "watermarks: temporal-persistence heuristic"),
            capability_notes=notes)
    finally:
        if not keep_frames and work_dir is None:
            shutil.rmtree(tmp, ignore_errors=True)
