"""Chinese OCR + temporal tracking for the Affiliate Studio.

Engines (all optional, import-guarded, probed before use):
  * ``PaddleOCREngine`` — PaddleOCR (``lang='ch'``: simplified +
    traditional Chinese). Adapter implemented; exercised only where
    paddlepaddle is installed (not this VM — see capabilities).
  * ``RapidOCREngine`` — rapidocr-onnxruntime (PaddleOCR detection +
    recognition models via ONNX Runtime). The lightweight real-OCR
    path used for the Phase 1 proof run.
  * ``StubOCREngine`` — test double with canned detections. Clearly
    named; never used outside tests.

Pipeline: per-frame detections -> temporal tracking (IoU + text
similarity) -> one :class:`TextRegion` per track -> rule-based
classification with explicit reasons -> manual-review queue for
low-confidence / ambiguous regions.

Safety rules (hard):
  * Classification NEVER implies removability. ``removal_approved``
    starts False; ``approve_removal`` requires authorization +
    confirmation + explicit approval, and protected classes
    (PRODUCT_LABEL / BRAND_LOGO / CREATOR_ATTRIBUTION / WATERMARK)
    additionally require an ownership-risk acknowledgement.
  * Flicker filtering drops only low-confidence single-sample
    detections, and the dropped items are returned for audit.
  * When no OCR engine is available, ``ocr_unavailable_report``
    says so and the pipeline falls back to manual text-region entry
    + the review queue. OCR results are never faked.
"""
from __future__ import annotations

import difflib
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .capabilities import ocr_backends
from .models import (AUTHORIZATION_TYPES, BBox, TextClassification,
                     TextRegion, TrackSample)
from .probe import ProbeError

# ---------------------------------------------------------------------
# detections + engine protocol
# ---------------------------------------------------------------------


@dataclass
class OCRDetection:
    text: str
    confidence: float
    polygon: list[tuple[float, float]]  # 4 points, pixels, any order

    @property
    def bbox(self) -> BBox:
        xs = [p[0] for p in self.polygon]
        ys = [p[1] for p in self.polygon]
        return BBox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


class OCREngine(Protocol):
    name: str

    def recognize(self, image_path: str | Path) -> list[OCRDetection]:
        """Detect + recognize text in one image file."""
        ...


# ---------------------------------------------------------------------
# PaddleOCR adapter (implemented; needs paddlepaddle installed)
# ---------------------------------------------------------------------

class PaddleOCREngine:
    """PaddleOCR adapter. ``lang='ch'`` covers simplified + traditional.

    Supports both the PaddleOCR 2.x ``.ocr()`` API and the 3.x
    ``.predict()`` API; unrecognized result shapes raise a clear error
    instead of being silently misread.
    """

    name = "paddleocr"

    def __init__(self) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is not installed (paddlepaddle + paddleocr "
                "required)") from exc
        self._ocr = PaddleOCR(use_angle_cls=True, lang="ch")

    def recognize(self, image_path: str | Path) -> list[OCRDetection]:
        path = str(image_path)
        if hasattr(self._ocr, "predict"):
            return self._parse_predict(self._ocr.predict(path))
        return self._parse_ocr(self._ocr.ocr(path))

    @staticmethod
    def _parse_ocr(result: Any) -> list[OCRDetection]:
        # 2.x: [[box, (text, score)], ...] wrapped in an outer list.
        detections: list[OCRDetection] = []
        lines = result[0] if isinstance(result, list) and result else []
        for item in lines or []:
            try:
                box, (text, score) = item[0], item[1]
            except (TypeError, ValueError, IndexError):
                continue
            detections.append(OCRDetection(
                text=str(text), confidence=float(score),
                polygon=[(float(px), float(py)) for px, py in box]))
        return detections

    @staticmethod
    def _parse_predict(result: Any) -> list[OCRDetection]:
        # 3.x: list of result objects exposing .json or dict-like data
        # with rec_texts / rec_scores / rec_polys (or rec_boxes).
        detections: list[OCRDetection] = []
        items = result if isinstance(result, list) else [result]
        for item in items:
            data = item.json if hasattr(item, "json") else item
            if not isinstance(data, dict):
                continue
            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            polys = data.get("rec_polys") or data.get("rec_boxes") or []
            for text, score, poly in zip(texts, scores, polys):
                points = [(float(px), float(py)) for px, py in
                          np.asarray(poly).reshape(-1, 2)]
                detections.append(OCRDetection(
                    text=str(text), confidence=float(score), polygon=points))
        return detections


# ---------------------------------------------------------------------
# RapidOCR (ONNX) adapter — the lightweight real-OCR path
# ---------------------------------------------------------------------

class RapidOCREngine:
    """rapidocr-onnxruntime adapter (PaddleOCR models via ONNX).

    First instantiation downloads the det/rec models (~15 MB) unless
    they are cached. That download happens here, explicitly, never
    during a capability probe.
    """

    name = "rapidocr_onnxruntime"

    def __init__(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise RuntimeError(
                "rapidocr-onnxruntime is not installed") from exc
        self._engine = RapidOCR()

    def recognize(self, image_path: str | Path) -> list[OCRDetection]:
        result, _ = self._engine(str(image_path))
        detections: list[OCRDetection] = []
        for item in result or []:
            try:
                box, text, score = item[0], item[1], float(item[2])
            except (TypeError, ValueError, IndexError):
                continue
            points = [(float(px), float(py)) for px, py in
                      np.asarray(box).reshape(-1, 2)]
            detections.append(OCRDetection(
                text=str(text), confidence=score, polygon=points))
        return detections


class StubOCREngine:
    """Test double: canned detections keyed by image file name.

    TEST-ONLY. Its name says so; it must never be wired into a
    production path.
    """

    name = "stub_test_only"

    def __init__(self, canned: dict[str, list[OCRDetection]]) -> None:
        self._canned = canned

    def recognize(self, image_path: str | Path) -> list[OCRDetection]:
        return list(self._canned.get(Path(image_path).name, []))


def get_ocr_engine(
        preference: tuple[str, ...] = ("paddleocr",
                                       "rapidocr_onnxruntime")) -> tuple[Any | None, dict[str, Any]]:
    """Instantiate the first available OCR engine (in preference order).

    Returns (engine_or_None, status). Instantiation may download
    models for backends that need them; that is the caller's explicit
    choice. Failures are recorded per backend, never hidden.
    """
    attempts: list[dict[str, Any]] = []
    available = {b["name"]: b["available"] for b in ocr_backends()}
    for name in preference:
        if not available.get(name):
            attempts.append({"backend": name, "ok": False,
                             "reason": "not installed"})
            continue
        try:
            if name == "paddleocr":
                engine: Any = PaddleOCREngine()
            elif name == "rapidocr_onnxruntime":
                engine = RapidOCREngine()
            else:
                attempts.append({"backend": name, "ok": False,
                                 "reason": "no adapter implemented"})
                continue
        except Exception as exc:  # noqa: BLE001 - recorded, next backend
            attempts.append({"backend": name, "ok": False,
                             "reason": f"instantiation failed: {exc}"})
            continue
        attempts.append({"backend": name, "ok": True})
        return engine, {"engine": name, "available": True, "attempts": attempts}
    return None, {"engine": None, "available": False, "attempts": attempts}


def ocr_unavailable_report() -> dict[str, Any]:
    """Honest status when no OCR engine can run here."""
    return {
        "ocr_available": False,
        "backends": ocr_backends(),
        "fallback": ("manual text-region entry + review queue; OCR "
                     "tracks are created from user-confirmed regions, "
                     "labelled source='manual'"),
        "detail": ("No OCR engine is installed in this Python "
                   "environment. Install PaddleOCR (paddlepaddle) or "
                   "rapidocr-onnxruntime to enable Chinese OCR."),
    }


# ---------------------------------------------------------------------
# frame OCR
# ---------------------------------------------------------------------

def run_ocr_on_frames(video_path: str | Path, times: list[float],
                      engine: Any, work_dir: str | Path | None = None,
                      frame_width: int | None = None) -> dict[float, list[OCRDetection]]:
    """Extract frames at ``times`` (native res unless width given) and
    run the OCR engine on each. Returns {time: detections}."""
    from .analysis import extract_frame_at  # local import: no cycle
    tmp = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="aff_ocr_"))
    tmp.mkdir(parents=True, exist_ok=True)
    out: dict[float, list[OCRDetection]] = {}
    try:
        for time_sec in times:
            frame = extract_frame_at(video_path, time_sec,
                                     tmp / f"ocr_{time_sec:.2f}.jpg",
                                     width=frame_width)
            try:
                out[time_sec] = engine.recognize(frame)
            except Exception as exc:  # noqa: BLE001 - per-frame failure
                raise ProbeError(f"OCR failed at t={time_sec}: {exc}") from exc
        return out
    finally:
        if work_dir is None:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------
# text similarity + tracking
# ---------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def text_similarity(a: str, b: str) -> float:
    """Character-level similarity for CJK + latin text (0..1)."""
    na, nb = _normalize_text(a), _normalize_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.85
    return difflib.SequenceMatcher(None, na, nb).ratio()


def classify_text_region(bbox: BBox, frame_size: tuple[int, int],
                         duration_sec: float, persistence: float,
                         text: str) -> tuple[TextClassification, str, bool]:
    """Rule-based classification with explicit reasons.

    Returns (classification, reason, needs_review). Every rule is
    documented; ambiguous cases stay UNKNOWN + needs_review. This
    function never decides removability.
    """
    fw, fh = frame_size
    x, y, w, h = bbox.x, bbox.y, bbox.w, bbox.h
    rel_y, rel_h, rel_w = y / fh, h / fh, w / fw
    in_corner = (rel_y < 0.12 or rel_y > 0.88) and (x / fw < 0.30 or x / fw > 0.70)
    if in_corner and persistence >= 0.6:
        if re.search(r"[@＠]|[号號]|ID|id", text):
            return (TextClassification.CREATOR_ATTRIBUTION,
                    "persistent corner graphic containing an account/ID "
                    "marker — verify attribution before any edit", True)
        return (TextClassification.WATERMARK,
                "persistent corner graphic across "
                f"{persistence:.0%} of the video — possible watermark/logo; "
                "verify before any edit", True)
    if rel_y > 0.62 and rel_h < 0.16 and duration_sec >= 1.0:
        return (TextClassification.SUBTITLE,
                "bottom-band text present for "
                f"{duration_sec:.1f}s — subtitle-like", False)
    # Promotional rule BEFORE the label rule: a large upper promo box
    # entering from the right edge can squeak under the label rule's
    # size/position thresholds (measured on the fixture: promo
    # fragment at x=1020, w=254, h=67 classified as PRODUCT_LABEL).
    # The promo rule's upper-area + tall-box conditions exclude real
    # labels (mid-frame, short), so the reorder is safe.
    if rel_y < 0.35 and rel_h >= 0.08 and duration_sec < 4.0:
        return (TextClassification.PROMOTIONAL_OVERLAY,
                "large short-lived upper text — promotional overlay-like",
                True)
    if rel_w < 0.20 and rel_h < 0.10 and 0.2 < (x / fw) < 0.8:
        return (TextClassification.PRODUCT_LABEL,
                "small text inside the central product area — possible "
                "product label; verify before any edit", True)
    return (TextClassification.UNKNOWN,
            "no classification rule matched — human review required", True)


@dataclass
class TrackingResult:
    regions: list[TextRegion] = field(default_factory=list)
    dropped_flicker: list[dict[str, Any]] = field(default_factory=list)


def track_detections(
        detections_by_time: dict[float, list[OCRDetection]],
        frame_size: tuple[int, int],
        sample_interval_sec: float = 1.0,
        iou_threshold: float = 0.3,
        text_similarity_min: float = 0.5,
        max_gap_samples: int = 1,
        min_persistence_samples: int = 2,
        min_confidence: float = 0.5) -> TrackingResult:
    """Group per-frame OCR detections into tracked TextRegions.

    Matching is greedy per time step: IoU overlap AND text similarity.
    Tracks that flicker (fewer than ``min_persistence_samples``
    samples with mean confidence below ``min_confidence``) are
    dropped — and returned in ``dropped_flicker`` for audit.
    """
    times = sorted(detections_by_time)
    total_samples = len(times)
    open_tracks: list[dict[str, Any]] = []
    closed: list[dict[str, Any]] = []

    for step, time_sec in enumerate(times):
        detections = detections_by_time[time_sec]
        matched_tracks: set[int] = set()
        matched_dets: set[int] = set()
        pairs: list[tuple[float, int, int]] = []
        for ti, track in enumerate(open_tracks):
            if step - track["last_step"] > max_gap_samples + 1:
                continue
            for di, det in enumerate(detections):
                iou = det.bbox.iou(track["last_bbox"])
                sim = text_similarity(det.text, track["texts"][-1])
                if iou >= iou_threshold and sim >= text_similarity_min:
                    pairs.append((iou + sim, ti, di))
        for _, ti, di in sorted(pairs, reverse=True):
            if ti in matched_tracks or di in matched_dets:
                continue
            matched_tracks.add(ti)
            matched_dets.add(di)
            det = detections[di]
            track = open_tracks[ti]
            track["detections"].append(det)
            track["texts"].append(det.text)
            track["times"].append(time_sec)
            track["last_bbox"] = det.bbox
            track["last_step"] = step
        for di, det in enumerate(detections):
            if di in matched_dets:
                continue
            open_tracks.append({"detections": [det], "texts": [det.text],
                                "times": [time_sec], "last_bbox": det.bbox,
                                "last_step": step})
        still_open = []
        for track in open_tracks:
            if step - track["last_step"] > max_gap_samples:
                closed.append(track)
            else:
                still_open.append(track)
        open_tracks = still_open
    closed.extend(open_tracks)

    regions: list[TextRegion] = []
    dropped: list[dict[str, Any]] = []
    for index, track in enumerate(closed, start=1):
        detections = track["detections"]
        mean_conf = float(np.mean([d.confidence for d in detections]))
        if (len(detections) < min_persistence_samples
                and mean_conf < min_confidence):
            dropped.append({
                "text": track["texts"][0],
                "times": track["times"],
                "mean_confidence": round(mean_conf, 3),
                "reason": "single-sample low-confidence flicker"})
            continue
        boxes = [d.bbox for d in detections]
        median_box = BBox(
            float(np.median([b.x for b in boxes])),
            float(np.median([b.y for b in boxes])),
            float(np.median([b.w for b in boxes])),
            float(np.median([b.h for b in boxes])))
        # Most common text wins (mode); ties -> first.
        texts = track["texts"]
        best_text = max(set(texts), key=texts.count)
        start = track["times"][0]
        end = track["times"][-1] + sample_interval_sec
        duration = end - start
        persistence = len(detections) / max(1, total_samples)
        classification, reason, needs_review = classify_text_region(
            median_box, frame_size, duration, persistence, best_text)
        if mean_conf < 0.7:
            needs_review = True
        reasons = [reason]
        if mean_conf < 0.7:
            reasons.append(f"low mean OCR confidence {mean_conf:.2f}")
        # Per-sample boxes, in time order: the tracked-blur builder
        # interpolates between these so the blur follows moving text.
        # The median box above stays the region's static summary.
        samples = [TrackSample(time=float(t), bbox=d.bbox)
                   for t, d in zip(track["times"], detections)]
        regions.append(TextRegion(
            text_id=f"txt-{index:03d}", track_id=f"track-{index:03d}",
            original_text=best_text, start_time=round(start, 3),
            end_time=round(end, 3), bbox=median_box, frame_size=frame_size,
            polygon=[(median_box.x, median_box.y),
                     (median_box.x2, median_box.y),
                     (median_box.x2, median_box.y2),
                     (median_box.x, median_box.y2)],
            ocr_confidence=round(mean_conf, 4),
            classification=classification,
            classification_reason=reason,
            source="ocr", detection_method="ocr+tracking",
            needs_review=needs_review, review_reasons=reasons,
            track_samples=samples))
    regions.sort(key=lambda r: r.start_time)
    for i, region in enumerate(regions, start=1):
        region.text_id = f"txt-{i:03d}"
        region.track_id = f"track-{i:03d}"
    return TrackingResult(regions=regions, dropped_flicker=dropped)


# ---------------------------------------------------------------------
# manual entry + review queue + removal approval
# ---------------------------------------------------------------------

def manual_text_region(text_id: str, text: str, start_time: float,
                       end_time: float, bbox: BBox,
                       frame_size: tuple[int, int],
                       classification: TextClassification =
                       TextClassification.UNKNOWN,
                       entered_by: str = "") -> TextRegion:
    """Create a TextRegion from user-confirmed manual entry.

    Used when OCR is unavailable or when the user corrects OCR. The
    region is labelled source='manual'; classification stays as given
    (default UNKNOWN) with an explicit reason.
    """
    if not text.strip():
        raise ValueError("manual text region needs non-empty text")
    if end_time <= start_time or start_time < 0:
        raise ValueError("need 0 <= start_time < end_time")
    fw, fh = frame_size
    if bbox.x < 0 or bbox.y < 0 or bbox.x2 > fw or bbox.y2 > fh:
        raise ValueError("bbox must lie inside the frame")
    return TextRegion(
        text_id=text_id, track_id=f"manual-{text_id}",
        original_text=text, start_time=start_time, end_time=end_time,
        bbox=bbox, frame_size=frame_size,
        polygon=[(bbox.x, bbox.y), (bbox.x2, bbox.y),
                 (bbox.x2, bbox.y2), (bbox.x, bbox.y2)],
        ocr_confidence=0.0, classification=classification,
        classification_reason="manual entry"
        + (f" by {entered_by}" if entered_by else ""),
        source="manual", detection_method="manual_entry",
        needs_review=False, review_reasons=[])


def review_queue(regions: list[TextRegion]) -> list[dict[str, Any]]:
    """Regions needing human review, with reasons, as plain dicts."""
    queue = []
    for region in regions:
        if not region.needs_review:
            continue
        entry = region.to_dict()
        entry["review_priority"] = (
            "high" if region.classification in
            (TextClassification.WATERMARK,
             TextClassification.CREATOR_ATTRIBUTION)
            else "normal")
        queue.append(entry)
    return queue


def approve_removal(region: TextRegion, authorization_type: str,
                    commercial_rights_confirmed: bool, approver: str,
                    acknowledge_ownership_risk: bool = False) -> TextRegion:
    """Approve removal/replacement of one region's original text.

    Gate: authorization must be known (not UNKNOWN) and commercial
    rights confirmed. Protected classes additionally require
    ``acknowledge_ownership_risk`` — the approver confirms the text
    is theirs / licensed for this edit. The approval is recorded on
    the region for audit. Raises ValueError when the gate fails.
    """
    from .models import PROTECTED_TEXT_CLASSES, export_gate_check
    allowed, reasons = export_gate_check(authorization_type,
                                         commercial_rights_confirmed)
    if not allowed:
        raise ValueError("removal approval refused: " + "; ".join(reasons))
    if authorization_type not in AUTHORIZATION_TYPES:
        raise ValueError(f"unknown authorization type {authorization_type!r}")
    if (region.classification in PROTECTED_TEXT_CLASSES
            and not acknowledge_ownership_risk):
        raise ValueError(
            f"region {region.text_id} is {region.classification.value}: "
            "removal needs an explicit ownership-risk acknowledgement "
            "from the approver")
    region.removal_approved = True
    region.removal_approval = {
        "authorization_type": authorization_type,
        "commercial_rights_confirmed": commercial_rights_confirmed,
        "approved_by": approver,
        "acknowledge_ownership_risk": acknowledge_ownership_risk,
        "classification": region.classification.value,
    }
    return region
