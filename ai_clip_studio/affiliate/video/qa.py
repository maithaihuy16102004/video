"""Video QA (§23, video side): checks on REAL rendered files.

Every check reports a measured value, the threshold applied, the
evidence, and the method. Nothing here invents a score: checks are
PASS / FAIL / PENDING, and the report's ``hard_fail_count`` is the
count of FAILs. Heuristic checks (sharpness, blockiness, freeze)
report measured numbers as PENDING when a human look is the honest
verdict — a static product shot is not an encoding freeze, and this
module does not pretend it can tell the difference alone.

Checks:
  * valid_mp4 / resolution / aspect / fps — ffprobe, exact.
  * audio specs — codec / sample rate / bitrate when audio exists.
  * black frames — ffmpeg blackdetect.
  * frozen frames — ffmpeg freezedetect (PENDING when detected:
    intentional stills look identical to freezes).
  * faststart — moov-before-mdat box scan.
  * content retention — when the source is supplied: the export's
    foreground vs the source, mean abs diff (real comparison).
  * sharpness / blockiness — numpy measurements, PENDING + numbers.
"""
from __future__ import annotations

import math
import re
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .capabilities import run_command
from .models import QAReport, QACheck
from .probe import ProbeError, probe_source

_BLACK_RE = re.compile(
    r"black_start:\s*([0-9.]+)\s+black_end:\s*([0-9.]+)\s+black_duration:\s*([0-9.]+)")
# ffmpeg <= 7 logs freezedetect as one combined line; ffmpeg 8 logs
# three metadata lines (lavfi.freezedetect.freeze_start/duration/end).
# Both formats are parsed.
_FREEZE_RE = re.compile(
    r"freeze_start:\s*([0-9.]+)\s+freeze_end:\s*([0-9.]+)\s+freeze_duration:\s*([0-9.]+)")
_FREEZE_META_RE = re.compile(
    r"freeze_(start|end|duration):\s*([0-9.]+)")

# Thresholds (documented; freeze/black are FAIL only above these).
BLACK_FAIL_SEC = 0.5
FREEZE_FAIL_FRAC = 0.5
RETENTION_MAX_DIFF = 0.15


# ---------------------------------------------------------------------
# ffmpeg detectors
# ---------------------------------------------------------------------

def detect_black(path: str | Path, min_duration: float = 0.1,
                 pix_th: float = 0.10) -> list[tuple[float, float, float]]:
    """Black segments via blackdetect: (start, end, duration)."""
    argv = ["ffmpeg", "-v", "info", "-i", str(path),
            "-vf", f"blackdetect=d={min_duration}:pix_th={pix_th}",
            "-an", "-f", "null", "-"]
    proc = run_command(argv, timeout=600.0)
    out = []
    for line in (proc.stderr or "").splitlines():
        match = _BLACK_RE.search(line)
        if match:
            out.append(tuple(float(g) for g in match.groups()))
    return out


def detect_freeze(path: str | Path, noise_db: float = -50.0,
                  min_duration: float = 0.5) -> list[tuple[float, float, float]]:
    """Frozen segments via freezedetect: (start, end, duration)."""
    argv = ["ffmpeg", "-v", "info", "-i", str(path),
            "-vf", f"freezedetect=n={noise_db}dB:d={min_duration}",
            "-an", "-f", "null", "-"]
    proc = run_command(argv, timeout=600.0)
    out = []
    pending: dict[str, float] = {}
    for line in (proc.stderr or "").splitlines():
        match = _FREEZE_RE.search(line)
        if match:
            out.append(tuple(float(g) for g in match.groups()))
            continue
        meta = _FREEZE_META_RE.search(line)
        if meta:
            pending[meta.group(1)] = float(meta.group(2))
            if {"start", "end", "duration"} <= pending.keys():
                out.append((pending["start"], pending["end"],
                            pending["duration"]))
                pending = {}
    if "start" in pending and "duration" in pending:
        # Trailing freeze cut off at end-of-stream: duration logged,
        # end missing — derive it rather than dropping the segment.
        out.append((pending["start"], pending["start"] + pending["duration"],
                    pending["duration"]))
    return out


def check_faststart(path: str | Path) -> tuple[bool, str]:
    """True when the moov box precedes the mdat box (faststart)."""
    data = Path(path).read_bytes()[:1 << 20]
    moov = data.find(b"moov")
    mdat = data.find(b"mdat")
    if moov == -1:
        return False, "moov box not found in the first 1MB"
    if mdat == -1:
        return True, "moov found, no mdat in the first 1MB"
    return moov < mdat, f"moov at byte {moov}, mdat at byte {mdat}"


# ---------------------------------------------------------------------
# numpy measurements
# ---------------------------------------------------------------------

def laplacian_variance(gray: np.ndarray) -> float:
    """Sharpness proxy: variance of the Laplacian response."""
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    padded = np.pad(gray, 1, mode="edge")
    response = (
        padded[:-2, 1:-1] + padded[2:, 1:-1]
        + padded[1:-1, :-2] + padded[1:-1, 2:]
        - 4 * padded[1:-1, 1:-1])
    return float(np.var(response))


def blockiness(gray: np.ndarray) -> float:
    """8x8 blocking proxy: boundary vs interior pixel differences."""
    h, w = gray.shape
    if h < 16 or w < 16:
        return 0.0
    horiz = np.abs(np.diff(gray, axis=1))
    boundary_cols = horiz[:, 7::8]
    interior_cols = np.delete(horiz, list(range(7, horiz.shape[1], 8)), axis=1)
    vert = np.abs(np.diff(gray, axis=0))
    boundary_rows = vert[7::8, :]
    interior_rows = np.delete(vert, list(range(7, vert.shape[0], 8)), axis=0)
    boundary = float(np.mean(np.concatenate(
        [boundary_cols.ravel(), boundary_rows.ravel()])))
    interior = float(np.mean(np.concatenate(
        [interior_cols.ravel(), interior_rows.ravel()])))
    return boundary - interior


def _sample_grays(path: str | Path, count: int = 6,
                  width: int = 320) -> list[np.ndarray]:
    from .analysis import extract_frame_sequence
    info = probe_source(path)
    sample_fps = max(0.5, count / max(info.duration_sec, 0.1))
    with tempfile.TemporaryDirectory(prefix="aff_qa_") as tmp:
        frames = extract_frame_sequence(path, sample_fps, tmp, width=width)
        grays = []
        for _, frame_path in frames[:count]:
            grays.append(np.asarray(
                Image.open(frame_path).convert("L"), dtype=np.float32))
        return grays


def content_retention(source_path: str | Path, export_path: str | Path,
                      strategy: str, count: int = 4) -> dict[str, Any]:
    """Compare export foreground content against the source.

    Samples matching timestamps, resizes both to the same small size
    (export: foreground crop for blur_fill/pad, full frame for
    crop_center — approximated by the center region), and reports the
    mean absolute difference. A small diff means the export kept the
    source picture; a large diff means content was lost or replaced.
    """
    from .analysis import extract_frame_at
    src = probe_source(source_path)
    exp = probe_source(export_path)
    times = [(i + 0.5) * min(src.duration_sec, exp.duration_sec) / count
             for i in range(count)]
    diffs: list[float] = []
    with tempfile.TemporaryDirectory(prefix="aff_ret_") as tmp:
        tmp_path = Path(tmp)
        for i, time_sec in enumerate(times):
            s_frame = extract_frame_at(source_path, time_sec,
                                       tmp_path / f"s{i}.jpg", width=320)
            e_frame = extract_frame_at(export_path, time_sec,
                                       tmp_path / f"e{i}.jpg", width=320)
            s_gray = np.asarray(Image.open(s_frame).convert("L"),
                                dtype=np.float32)
            e_img = Image.open(e_frame).convert("L")
            if strategy in ("blur_fill", "pad"):
                # Foreground occupies the center; crop the middle band
                # with the source aspect ratio.
                ew, eh = e_img.size
                target_h = int(ew * s_gray.shape[0] / s_gray.shape[1])
                target_h = min(eh, target_h)
                top = (eh - target_h) // 2
                e_img = e_img.crop((0, top, ew, top + target_h))
            e_gray = np.asarray(e_img.resize(
                (s_gray.shape[1], s_gray.shape[0]), Image.BILINEAR),
                dtype=np.float32)
            diffs.append(float(np.mean(np.abs(s_gray - e_gray)) / 255.0))
    mean_diff = float(np.mean(diffs)) if diffs else 1.0
    return {"mean_abs_diff": round(mean_diff, 4),
            "per_sample": [round(d, 4) for d in diffs],
            "method": f"center/foreground comparison, {count} samples, "
                      f"strategy={strategy}"}


# ---------------------------------------------------------------------
# main QA entry point
# ---------------------------------------------------------------------

def qa_export(path: str | Path, profile_name: str,
              expected_width: int, expected_height: int,
              expected_fps: float | None = None,
              source_path: str | Path | None = None,
              reframe_strategy: str = "blur_fill",
              expect_audio: bool = True) -> QAReport:
    """Run video QA on a rendered export. All checks measured."""
    target = Path(path)
    checks: list[QACheck] = []
    notes: list[str] = []
    try:
        info = probe_source(target)
    except ProbeError as exc:
        checks.append(QACheck("valid_mp4", "FAIL", None, "ffprobe parses",
                              str(exc), "ffprobe"))
        return QAReport(str(target), profile_name, checks, {}, notes)
    measured = info.to_dict()

    checks.append(QACheck(
        "valid_mp4", "PASS",
        {"duration_sec": round(info.duration_sec, 3),
         "video_codec": info.video_codec,
         "has_audio": info.has_audio},
        "ffprobe parses + video stream + duration > 0",
        f"{info.resolution} {info.video_codec} {info.duration_sec:.2f}s",
        "ffprobe"))

    res_ok = (info.width, info.height) == (expected_width, expected_height)
    checks.append(QACheck(
        "resolution", "PASS" if res_ok else "FAIL",
        info.resolution, f"{expected_width}x{expected_height}",
        f"measured {info.resolution}", "ffprobe"))
    gcd = math.gcd(expected_width, expected_height) or 1
    checks.append(QACheck(
        "aspect_ratio", "PASS" if res_ok else "FAIL",
        info.aspect_ratio,
        f"{expected_width // gcd}:{expected_height // gcd}",
        f"measured {info.aspect_ratio}", "ffprobe"))

    if expected_fps:
        fps_ok = abs(info.fps - expected_fps) <= 0.5
        checks.append(QACheck(
            "fps", "PASS" if fps_ok else "FAIL", round(info.fps, 3),
            f"{expected_fps} ± 0.5", f"measured {info.fps:.3f}", "ffprobe"))
    else:
        checks.append(QACheck(
            "fps", "PENDING", round(info.fps, 3), "no expected fps supplied",
            f"measured {info.fps:.3f} (source fps preserved)",
            "ffprobe"))

    if info.has_audio:
        raw = info.probe_raw.get("streams", [])
        audio = next((s for s in raw if s.get("codec_type") == "audio"), {})
        try:
            bitrate_kbps = int(audio.get("bit_rate") or 0) // 1000
        except (TypeError, ValueError):
            bitrate_kbps = 0
        sample_rate = int(audio.get("sample_rate") or 0)
        audio_ok = info.audio_codec == "aac" and sample_rate == 48000 \
            and 96 <= bitrate_kbps <= 320
        checks.append(QACheck(
            "audio_specs", "PASS" if audio_ok else "FAIL",
            {"codec": info.audio_codec, "sample_rate": sample_rate,
             "bitrate_kbps": bitrate_kbps},
            "aac, 48000 Hz, 96..320 kbps",
            f"measured {info.audio_codec} {sample_rate}Hz ~{bitrate_kbps}kbps",
            "ffprobe"))
    else:
        checks.append(QACheck(
            "audio_specs", "PENDING", None,
            "audio checked by the voice/mix stage",
            "no audio stream in this video-side export; narration and "
            "mixing are owned by the audio stage",
            "ffprobe"))

    blacks = detect_black(target)
    black_total = sum(d for _, _, d in blacks)
    checks.append(QACheck(
        "black_frames", "FAIL" if black_total > BLACK_FAIL_SEC else "PASS",
        {"segments": len(blacks), "total_sec": round(black_total, 3)},
        f"total black <= {BLACK_FAIL_SEC}s",
        f"{len(blacks)} black segment(s), {black_total:.3f}s total",
        "ffmpeg blackdetect d=0.1 pix_th=0.10"))

    freezes = detect_freeze(target)
    freeze_total = sum(d for _, _, d in freezes)
    freeze_frac = freeze_total / max(info.duration_sec, 0.01)
    if freeze_frac > FREEZE_FAIL_FRAC:
        freeze_status, freeze_evidence = "FAIL", (
            f"{len(freezes)} freeze segment(s), {freeze_total:.2f}s "
            f"({freeze_frac:.0%} of duration)")
    elif freezes:
        freeze_status, freeze_evidence = "PENDING", (
            f"{len(freezes)} freeze segment(s), {freeze_total:.2f}s — "
            "intentional stills look identical to freezes; human review")
    else:
        freeze_status, freeze_evidence = "PASS", "no frozen segments detected"
    checks.append(QACheck(
        "frozen_frames", freeze_status,
        {"segments": len(freezes), "total_sec": round(freeze_total, 3)},
        f"frozen fraction <= {FREEZE_FAIL_FRAC:.0%}",
        freeze_evidence, "ffmpeg freezedetect n=-50dB d=0.5"))

    fast_ok, fast_evidence = check_faststart(target)
    checks.append(QACheck(
        "faststart", "PASS" if fast_ok else "FAIL", fast_ok,
        "moov box precedes mdat", fast_evidence, "MP4 box scan"))

    if source_path is not None:
        retention = content_retention(source_path, target, reframe_strategy)
        retained = retention["mean_abs_diff"] <= RETENTION_MAX_DIFF
        checks.append(QACheck(
            "content_retention", "PASS" if retained else "FAIL",
            retention["mean_abs_diff"],
            f"mean abs diff <= {RETENTION_MAX_DIFF}",
            f"per-sample diffs {retention['per_sample']}",
            retention["method"]))
    else:
        checks.append(QACheck(
            "content_retention", "PENDING", None,
            "needs the source video for comparison",
            "no source supplied — retention not measured",
            "foreground comparison"))

    grays = _sample_grays(target)
    if grays:
        sharp = float(np.mean([laplacian_variance(g) for g in grays]))
        block = float(np.mean([blockiness(g) for g in grays]))
        checks.append(QACheck(
            "sharpness", "PENDING", round(sharp, 2),
            "no absolute threshold — compare against the source",
            f"mean Laplacian variance {sharp:.2f} over {len(grays)} frames",
            "numpy Laplacian variance"))
        checks.append(QACheck(
            "compression_blockiness", "PENDING", round(block, 3),
            "provisional: values >> 0 suggest visible blocking",
            f"mean 8x8 boundary discontinuity {block:.3f} over "
            f"{len(grays)} frames", "numpy block-boundary metric"))
        notes.append("sharpness/blockiness are measured proxies reported "
                     "as PENDING: no absolute pass threshold is claimed")
    return QAReport(str(target), profile_name, checks, measured, notes)
