"""Final MP4 verification (directive section 19).

Planned timestamps are NOT rendered evidence. This module extracts
the ACTUAL audio from the rendered MP4 and measures it against the
TTS sources and the frozen schedule:

* every spoken line: exactly once, complete (tail present), onset
  within 100 ms of the frozen schedule, no unintended overlap;
* subtitle windows match the measured speech;
* SFX segments exist on the foley stem at their planned times, and
  anchored segments match their visual contact moments;
* audio/video durations agree with each other and the frozen total.

Method: FFT cross-correlation of each TTS wav against the rendered
audio at 16 kHz mono (resolution 0.0625 ms). Each line is correlated
against BOTH the MP4-extracted audio (rendered evidence) and the
pre-codec mix.wav (reference): the difference between the two onset
measurements IS the codec delay, measured rather than assumed. AAC
priming is typically ~1024 samples (~21 ms at 48 kHz); ffmpeg's
decoder applies the container's skip metadata, so the residual is
usually a few ms -- the report states the measured value per job.

Uncertainty budget: correlation resolution 0.0625 ms; mix processing
(ducking, limiter, fade) does not move onsets; codec delay measured
per job (see codec_delay_estimate_sec). The 100 ms tolerance exceeds
all of these by a wide margin; a failure means the render is wrong,
not the measurement.
"""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import fftconvolve

from .animation.primitives import hammer_cycles, hammer_strike_times
from .audio_events import _anchor_fraction

SAMPLE_RATE = 16000
ONSET_TOLERANCE_SEC = 0.100
SUBTITLE_TOLERANCE_SEC = 0.100
OVERLAP_TOLERANCE_SEC = 0.050
AV_TOLERANCE_SEC = 0.150
ANCHOR_SCHEDULE_TOLERANCE_SEC = 0.050
MIN_LINE_COEFFICIENT = 0.5
MIN_TAIL_COEFFICIENT = 0.15
MIN_TAIL_DISCRIMINATION = 4.0
MAX_SECOND_PEAK_RATIO = 0.6


def _decode_mono(path: Path, rate: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any audio file to mono float32 via ffmpeg."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"],
        capture_output=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"decode failed for {path}: "
                           f"{r.stderr[:300]!r}")
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def _probe_streams(mp4_path: Path) -> dict[str, Any]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=index,codec_type,codec_name,duration,start_time",
         "-show_entries", "format=duration",
         "-of", "json", str(mp4_path)],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {r.stderr[:300]}")
    return json.loads(r.stdout)


def _extract_mp4_audio(mp4_path: Path, out_path: Path) -> Path:
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(mp4_path),
         "-map", "0:a:0", "-ac", "1", "-ar", str(SAMPLE_RATE),
         str(out_path)], capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"audio extraction failed: {r.stderr[:300]}")
    return out_path


def _correlate(mix: np.ndarray, source: np.ndarray) -> np.ndarray:
    """Full cross-correlation: corr[lag] = sum(mix[lag:lag+M] * src)."""
    if len(mix) < len(source):
        return np.empty(0, dtype=np.float64)
    return fftconvolve(mix.astype(np.float64),
                       source[::-1].astype(np.float64), mode="valid")


def _window_energy(mix: np.ndarray, start: int, length: int) -> float:
    window = mix[start:start + length]
    return float(np.sqrt(np.sum(window.astype(np.float64) ** 2)))


def _window_overlaps_speech(start: float, end: float,
                            spans) -> bool:
    """True when [start, end] intersects any span in ``spans``.

    ``spans`` is a list of (start_sec, end_sec) planned speech
    windows, or None (no guard — the legacy single-line callers).
    """
    if not spans:
        return False
    for span_start, span_end in spans:
        if start < span_end and end > span_start:
            return True
    return False


def _measure_line(mix: np.ndarray, source: np.ndarray,
                  planned_start: float,
                  other_spans=None) -> dict[str, Any]:
    """Correlate one TTS wav against the rendered mix. Returns the
    measured onset, coefficient, second-peak ratio and tail check.

    ``other_spans``: planned (start, end) windows of the OTHER
    lines, used to keep the tail discrimination control out of
    neighbouring speech (see the control block below).
    """
    record: dict[str, Any] = {
        "planned_start_sec": round(planned_start, 3),
        "source_duration_sec": round(len(source) / SAMPLE_RATE, 3),
    }
    if len(source) == 0:
        record.update(status="failed", reason="empty TTS wav")
        return record
    corr = _correlate(mix, source)
    if corr.size == 0:
        record.update(status="failed",
                      reason="mix shorter than the line (truncated?)")
        return record
    peak_idx = int(np.argmax(corr))
    peak = float(corr[peak_idx])
    src_energy = float(np.sqrt(np.sum(source.astype(np.float64) ** 2)))
    mix_energy = _window_energy(mix, peak_idx, len(source))
    coefficient = (peak / (src_energy * mix_energy)
                   if src_energy > 0 and mix_energy > 0 else 0.0)
    onset = peak_idx / SAMPLE_RATE
    # Exactly-once: mask the peak's neighbourhood (one line length)
    # and look for a second comparable peak elsewhere.
    masked = corr.copy()
    lo = max(0, peak_idx - len(source))
    hi = min(corr.size, peak_idx + len(source))
    masked[lo:hi] = -np.inf
    second = float(np.max(masked)) if masked.size else 0.0
    second_ratio = second / peak if peak > 0 else 0.0
    record.update(
        measured_onset_sec=round(onset, 4),
        onset_error_sec=round(onset - planned_start, 4),
        coefficient=round(coefficient, 4),
        second_peak_ratio=round(second_ratio, 4),
        status="measured")
    # Completeness: the line's tail must be present at the expected
    # tail position (onset + duration - tail_len).
    tail_len = min(int(0.5 * SAMPLE_RATE), max(1, len(source) // 3))
    tail = source[-tail_len:]
    expected_tail = onset + len(source) / SAMPLE_RATE \
        - tail_len / SAMPLE_RATE
    search_lo = max(0, int((expected_tail - 0.15) * SAMPLE_RATE))
    search_hi = min(len(mix), int(
        (expected_tail + 0.15) * SAMPLE_RATE) + tail_len)
    window = mix[search_lo:search_hi]
    tail_corr = _correlate(window, tail)
    if tail_corr.size:
        tail_peak = int(np.argmax(tail_corr))
        tail_onset = (search_lo + tail_peak) / SAMPLE_RATE
        tail_peak_value = float(tail_corr[tail_peak])
        tail_src_energy = float(np.sqrt(np.sum(
            tail.astype(np.float64) ** 2)))
        tail_mix_energy = _window_energy(window, tail_peak, tail_len)
        tail_coef = (tail_peak_value / (tail_src_energy
                                        * tail_mix_energy)
                     if tail_src_energy > 0 and tail_mix_energy > 0
                     else 0.0)
        # Discrimination control: the same tail correlated
        # against a window OUTSIDE every spoken line must NOT
        # match. A real tail in a loud mix can have a low absolute
        # coefficient (an overlapping next line dilutes it --
        # measured 0.18-0.34 on the Zeus draft, controls ~0.00), so
        # presence is judged RELATIVELY: the match must beat the
        # control by 4x and clear a floor. The control sits before
        # the line, never inside it: 1 s before the tail would land
        # in the line's own body for long lines. It must ALSO sit
        # outside the PREVIOUS line: with a 0.31 s inter-line gap
        # the 1 s-back control lands inside the previous line's
        # speech (same voice) and reads 0.26, failing a present
        # tail (0.89) on the ratio alone -- measured on the Zeus
        # re-render, line 14. Candidates step back 1..5 s; the
        # first window clear of all other lines wins, else there
        # is no control and the absolute 0.35 rule decides.
        control_coef = None
        tail_dur = tail_len / SAMPLE_RATE
        candidates = [onset - back
                      for back in (1.0, 2.0, 3.0, 4.0, 5.0)]
        candidates.append(onset + len(source) / SAMPLE_RATE + 1.0)
        control_at = None
        for cand in candidates:
            if cand < 0:
                continue
            if _window_overlaps_speech(cand, cand + tail_dur,
                                       other_spans):
                continue
            control_at = cand
            break
        if control_at is not None:
            control_start = int(round(control_at * SAMPLE_RATE))
            if 0 <= control_start \
                    and control_start + tail_len <= len(mix):
                control_seg = mix[control_start:control_start + tail_len]
                control_energy = float(np.sqrt(np.sum(
                    control_seg.astype(np.float64) ** 2)))
                if control_energy > 0 and tail_src_energy > 0:
                    control_coef = float(np.dot(
                        control_seg.astype(np.float64),
                        tail.astype(np.float64))
                        / (control_energy * tail_src_energy))
        if control_coef is None:
            strong = tail_coef >= 0.35
        else:
            strong = (tail_coef >= MIN_TAIL_COEFFICIENT
                      and tail_coef >= MIN_TAIL_DISCRIMINATION
                      * abs(control_coef))
        record.update(
            tail_present=bool(
                abs(tail_onset - expected_tail) <= ONSET_TOLERANCE_SEC
                and strong),
            tail_error_sec=round(tail_onset - expected_tail, 4),
            tail_coefficient=round(tail_coef, 4),
            tail_control_coefficient=(
                round(control_coef, 4)
                if control_coef is not None else None))
    else:
        record.update(tail_present=False, tail_error_sec=None,
                      tail_coefficient=0.0,
                      tail_reason="tail window outside the mix")
    return record


def _rms_envelope(signal: np.ndarray, window: int = 160,
                  hop: int = 80) -> tuple[np.ndarray, np.ndarray]:
    """10 ms RMS windows, 5 ms hop, at 16 kHz. Returns (times, db)."""
    if len(signal) < window:
        return np.empty(0), np.empty(0)
    frames = 1 + (len(signal) - window) // hop
    idx = (np.arange(frames)[:, None] * hop
           + np.arange(window)[None, :])
    rms = np.sqrt(np.mean(signal[idx].astype(np.float64) ** 2, axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-9))
    times = (np.arange(frames) * hop + window / 2) / SAMPLE_RATE
    return times, db


def _measure_sfx_onset(foley: np.ndarray, planned: float,
                       floor_db: float) -> dict[str, Any]:
    """First envelope rise above the floor in the search window."""
    times, db = _rms_envelope(foley)
    threshold = floor_db + 8.0
    lo, hi = planned - 0.15, planned + 0.35
    in_window = (times >= lo) & (times <= hi)
    if not np.any(in_window):
        return {"measured_onset_sec": None, "present": False,
                "reason": "search window outside the stem"}
    window_db = db[in_window]
    window_times = times[in_window]
    above = np.nonzero(window_db >= threshold)[0]
    if above.size == 0:
        return {"measured_onset_sec": None, "present": False,
                "peak_db": round(float(np.max(window_db)), 1),
                "threshold_db": round(threshold, 1),
                "reason": "no rise above the noise floor"}
    onset = float(window_times[above[0]])
    return {"measured_onset_sec": round(onset, 4),
            "onset_error_sec": round(onset - planned, 4),
            "present": abs(onset - planned) <= ONSET_TOLERANCE_SEC,
            "peak_db": round(float(np.max(window_db)), 1),
            "threshold_db": round(threshold, 1)}


def verify_mp4(mp4_path: Path, *,
               lines: list[dict],
               subtitles: list[dict] | None = None,
               segments: list[dict] | None = None,
               unified: dict | None = None,
               mix_wav: Path | None = None,
               foley_wav: Path | None = None,
               ) -> dict[str, Any]:
    """Verify a rendered MP4 against its TTS sources and schedule.

    ``lines``: [{line_index, wav, start, end}] with planned starts
    from the frozen schedule. ``subtitles``: the subtitles.json
    records. ``segments``: rendered foley segments [{at_seconds,
    end_seconds, synth_kind, cue_id, anchor_event_id}].
    ``unified``: the unified_timeline.json dict (for the frozen
    total + action-track anchor checks).
    """
    report: dict[str, Any] = {
        "mp4": str(mp4_path),
        "method": "FFT cross-correlation at 16 kHz mono; "
                  "codec delay measured per job (MP4 vs mix.wav)",
        "tolerances": {
            "onset_sec": ONSET_TOLERANCE_SEC,
            "subtitle_sec": SUBTITLE_TOLERANCE_SEC,
            "overlap_sec": OVERLAP_TOLERANCE_SEC,
            "av_sec": AV_TOLERANCE_SEC},
        "failures": [],
    }
    probe = _probe_streams(mp4_path)
    streams = probe.get("streams", [])
    video = next((s for s in streams
                  if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams
                  if s.get("codec_type") == "audio"), {})
    report["streams"] = {
        "video_codec": video.get("codec_name"),
        "video_duration_sec": float(video.get("duration", 0.0) or 0.0),
        "video_start_time_sec": float(
            video.get("start_time", 0.0) or 0.0),
        "audio_codec": audio.get("codec_name"),
        "audio_duration_sec": float(audio.get("duration", 0.0) or 0.0),
        "audio_start_time_sec": float(
            audio.get("start_time", 0.0) or 0.0),
        "format_duration_sec": float(
            probe.get("format", {}).get("duration", 0.0) or 0.0),
    }
    with tempfile.TemporaryDirectory() as tmp:
        extracted = _extract_mp4_audio(
            mp4_path, Path(tmp) / "extracted.wav")
        mix = _decode_mono(extracted)
        reference = _decode_mono(mix_wav) if mix_wav else None
        line_records = []
        spans = [(float(ln["start"]), float(ln["end"]))
                 for ln in lines]
        for i, line in enumerate(lines):
            source = _decode_mono(Path(line["wav"]))
            others = spans[:i] + spans[i + 1:]
            measured = _measure_line(mix, source, float(line["start"]),
                                     others)
            measured["line_index"] = line["line_index"]
            measured["planned_end_sec"] = round(float(line["end"]), 3)
            if reference is not None:
                ref = _measure_line(reference, source,
                                    float(line["start"]), others)
                measured["mix_onset_sec"] = ref.get("measured_onset_sec")
                measured["mix_onset_error_sec"] = ref.get(
                    "onset_error_sec")
                if (measured.get("measured_onset_sec") is not None
                        and ref.get("measured_onset_sec") is not None):
                    measured["codec_delay_sec"] = round(
                        measured["measured_onset_sec"]
                        - ref["measured_onset_sec"], 4)
            line_records.append(measured)
        report["lines"] = line_records
        # Codec delay estimate: the median MP4-vs-mix onset shift.
        delays = [r["codec_delay_sec"] for r in line_records
                  if r.get("codec_delay_sec") is not None]
        report["codec_delay_estimate_sec"] = (
            round(float(np.median(delays)), 4) if delays else None)
        report["codec_delay_note"] = (
            "Median MP4-minus-mix onset shift across lines. AAC "
            "priming (~1024 samples) is absorbed by ffmpeg's decoder "
            "via container skip metadata; the residual is the true "
            "mux/decode offset for this file.")
        # SFX onsets on the foley stem.
        sfx_records = []
        if segments and foley_wav is not None and foley_wav.exists():
            foley = _decode_mono(foley_wav)
            _t, floor_env = _rms_envelope(foley)
            floor_db = float(np.median(floor_env)) \
                if floor_env.size else -90.0
            floor_db = max(floor_db, -70.0)
            for seg in segments:
                rec = _measure_sfx_onset(
                    foley, float(seg["at_seconds"]), floor_db)
                rec.update(cue_id=seg.get("cue_id"),
                           synth_kind=seg.get("synth_kind"),
                           planned_sec=round(
                               float(seg["at_seconds"]), 3),
                           anchor_event_id=seg.get("anchor_event_id"))
                sfx_records.append(rec)
            report["foley_floor_db"] = round(floor_db, 1)
        report["sfx"] = sfx_records
    # Subtitle timing vs measured speech.
    sub_records = []
    measured_by_line = {r["line_index"]: r for r in line_records}
    for sub in subtitles or []:
        line_index = sub["line_index"]
        rec = measured_by_line.get(line_index)
        windows = sub.get("windows") or []
        entry: dict[str, Any] = {"line_index": line_index}
        if rec is None or rec.get("measured_onset_sec") is None:
            entry.update(status="unmeasured",
                         reason="no measured onset for this line")
        elif not windows:
            entry.update(status="failed", reason="no phrase windows")
        else:
            first_start = float(windows[0]["start"])
            last_end = float(windows[-1]["end"])
            measured_end = rec["measured_onset_sec"] \
                + rec["source_duration_sec"]
            entry.update(
                planned_span=[round(first_start, 3),
                              round(last_end, 3)],
                measured_span=[round(rec["measured_onset_sec"], 3),
                               round(measured_end, 3)],
                start_error_sec=round(
                    first_start - rec["measured_onset_sec"], 4),
                end_error_sec=round(last_end - measured_end, 4),
                status="measured")
            # Continuity: phrase windows tile the span, no gaps.
            gaps = [round(float(windows[i + 1]["start"])
                          - float(windows[i]["end"]), 4)
                    for i in range(len(windows) - 1)]
            entry["phrase_gaps_sec"] = gaps
            entry["continuous"] = all(abs(g) <= 0.005 for g in gaps)
        sub_records.append(entry)
    report["subtitles"] = sub_records
    # Durations vs the frozen schedule.
    if unified is not None:
        report["frozen_total_sec"] = unified.get("total_sec")
        report["frozen_total_frames"] = unified.get("total_frames")
    # Anchor checks: an anchored segment's planned time must equal
    # the visual contact moment of its action event (recomputed from
    # the frozen action track + the shared anchor fractions), and
    # the measured foley onset must match the same moment. The
    # frame-quantized schedule bounds the schedule check at 50 ms.
    anchor_checks = []
    if unified is not None and sfx_records:
        actions = {}
        for interval in unified.get("intervals", []):
            if interval["track"] != "actions":
                continue
            action_id = interval["interval_id"].split(":", 1)[1]
            actions[action_id] = interval
        sfx_by_cue = {}
        for rec in sfx_records:
            sfx_by_cue.setdefault(rec.get("cue_id"), []).append(rec)
        for seg in segments or []:
            event_id = seg.get("anchor_event_id")
            if not event_id or event_id not in actions:
                continue
            interval = actions[event_id]
            verb = (interval.get("payload") or {}).get("verb", "")
            start = float(interval["start_sec"])
            end = float(interval["end_sec"])
            if verb == "HAMMER_STRIKE":
                moments = [start + t for t in hammer_strike_times(
                    end - start, hammer_cycles(end - start))]
            else:
                moments = [start + _anchor_fraction(verb)
                           * (end - start)]
            planned = float(seg["at_seconds"])
            nearest = min(moments, key=lambda m: abs(m - planned))
            check = {
                "cue_id": seg.get("cue_id"),
                "anchor_event_id": event_id, "verb": verb,
                "contact_moments_sec": [round(m, 3) for m in moments],
                "planned_sec": round(planned, 3),
                "schedule_error_sec": round(planned - nearest, 4),
            }
            for rec in sfx_by_cue.get(seg.get("cue_id"), []):
                # Pair this segment with ITS OWN onset record: a
                # multi-hit cue (two hammer strikes) has one record
                # per segment, and taking the last record for every
                # segment compares strike 2 against strike 1's
                # contact moment (+0.91 s false failure on the Zeus
                # re-render). planned_sec is round(at_seconds, 3)
                # on both sides; 2 ms absorbs the rounding.
                if (rec.get("measured_onset_sec") is not None
                        and abs(float(rec.get("planned_sec", -1.0))
                                - planned) <= 0.002):
                    check["measured_onset_sec"] = rec[
                        "measured_onset_sec"]
                    check["onset_vs_contact_sec"] = round(
                        rec["measured_onset_sec"] - nearest, 4)
                    break
            anchor_checks.append(check)
    report["anchor_checks"] = anchor_checks
    # Verdicts.
    failures: list[str] = []
    for rec in line_records:
        label = f"line {rec['line_index']}"
        if rec.get("status") != "measured":
            failures.append(
                f"{label}: {rec.get('reason', 'unmeasured')}")
            continue
        if abs(rec["onset_error_sec"]) > ONSET_TOLERANCE_SEC:
            failures.append(
                f"{label}: onset error {rec['onset_error_sec']:+.3f}s "
                f"(tolerance {ONSET_TOLERANCE_SEC}s)")
        if rec["coefficient"] < MIN_LINE_COEFFICIENT:
            failures.append(
                f"{label}: weak match (coefficient "
                f"{rec['coefficient']}, min {MIN_LINE_COEFFICIENT})")
        if rec["second_peak_ratio"] > MAX_SECOND_PEAK_RATIO:
            failures.append(
                f"{label}: possible duplicate (second-peak ratio "
                f"{rec['second_peak_ratio']})")
        if not rec.get("tail_present"):
            failures.append(
                f"{label}: tail missing/truncated "
                f"(tail error {rec.get('tail_error_sec')}, "
                f"coefficient {rec.get('tail_coefficient')})")
    measured_lines = sorted(
        (r for r in line_records if r.get("measured_onset_sec") is not None),
        key=lambda r: r["measured_onset_sec"])
    for prev, nxt in zip(measured_lines, measured_lines[1:]):
        prev_end = prev["measured_onset_sec"] \
            + prev["source_duration_sec"]
        overlap = prev_end - nxt["measured_onset_sec"]
        if overlap > OVERLAP_TOLERANCE_SEC:
            failures.append(
                f"lines {prev['line_index']}/{nxt['line_index']}: "
                f"overlap {overlap:.3f}s")
    for entry in sub_records:
        if entry.get("status") == "failed":
            failures.append(
                f"subtitle line {entry['line_index']}: "
                f"{entry.get('reason')}")
        elif entry.get("status") == "measured":
            if abs(entry["start_error_sec"]) > SUBTITLE_TOLERANCE_SEC:
                failures.append(
                    f"subtitle line {entry['line_index']}: start "
                    f"error {entry['start_error_sec']:+.3f}s")
            if abs(entry["end_error_sec"]) > SUBTITLE_TOLERANCE_SEC:
                failures.append(
                    f"subtitle line {entry['line_index']}: end error "
                    f"{entry['end_error_sec']:+.3f}s")
            if not entry.get("continuous"):
                failures.append(
                    f"subtitle line {entry['line_index']}: phrase "
                    f"windows do not tile {entry['phrase_gaps_sec']}")
    for rec in sfx_records:
        if not rec.get("present"):
            failures.append(
                f"SFX {rec.get('cue_id')} ({rec.get('synth_kind')}): "
                f"no onset at {rec.get('planned_sec')}s "
                f"({rec.get('reason', 'outside tolerance')})")
    for check in anchor_checks:
        if abs(check["schedule_error_sec"]) \
                > ANCHOR_SCHEDULE_TOLERANCE_SEC:
            failures.append(
                f"SFX {check['cue_id']}: planned "
                f"{check['planned_sec']}s vs contact moment "
                f"{check['contact_moments_sec']} "
                f"(error {check['schedule_error_sec']:+.3f}s)")
        if check.get("onset_vs_contact_sec") is not None and abs(
                check["onset_vs_contact_sec"]) > ONSET_TOLERANCE_SEC:
            failures.append(
                f"SFX {check['cue_id']}: measured onset "
                f"{check['measured_onset_sec']}s vs contact moment "
                f"(error {check['onset_vs_contact_sec']:+.3f}s)")
    streams = report["streams"]
    av_diff = abs(streams["video_duration_sec"]
                  - streams["audio_duration_sec"])
    report["av_diff_sec"] = round(av_diff, 4)
    if av_diff > AV_TOLERANCE_SEC:
        failures.append(
            f"A/V duration mismatch: video "
            f"{streams['video_duration_sec']:.3f}s vs audio "
            f"{streams['audio_duration_sec']:.3f}s")
    report["failures"] = failures
    report["passed"] = not failures
    report["summary"] = (
        f"{len(line_records)} lines, "
        f"{sum(1 for r in line_records if r.get('status') == 'measured')} "
        f"measured, {len(sfx_records)} SFX, "
        f"{len(sub_records)} subtitle lines, "
        f"{len(failures)} failure(s)")
    return report


def verify_job_mp4(job_dir: Path, mp4_path: Path | None = None
                   ) -> dict[str, Any]:
    """Job-dir convenience wrapper: reads timeline.json (wav paths),
    unified_timeline.json (frozen line spans), subtitles.json,
    audio_plan.json (segments) and the audio stems."""
    job_dir = Path(job_dir)
    if mp4_path is None:
        mp4_path = job_dir / "draft.mp4"
    timeline = json.loads(
        (job_dir / "timeline.json").read_text(encoding="utf-8"))
    unified = json.loads(
        (job_dir / "unified_timeline.json").read_text(encoding="utf-8"))
    wavs = {line["line_index"]: line["wav"]
            for line in timeline["lines"]}
    lines = []
    for interval in unified["intervals"]:
        if interval["track"] not in ("narration", "dialogue"):
            continue
        line_index = int(interval["interval_id"].split(":")[1])
        lines.append({"line_index": line_index,
                      "wav": wavs[line_index],
                      "start": interval["start_sec"],
                      "end": interval["end_sec"]})
    lines.sort(key=lambda e: e["line_index"])
    subtitles = json.loads(
        (job_dir / "subtitles.json").read_text(encoding="utf-8"))
    plan = json.loads(
        (job_dir / "audio_plan.json").read_text(encoding="utf-8"))
    segments = list(
        plan.get("v1_cue_resolution", {}).get("segments", []))
    mix_wav = job_dir / "audio" / "mix.wav"
    foley_wav = job_dir / "audio" / "foley.wav"
    report = verify_mp4(
        mp4_path, lines=lines, subtitles=subtitles,
        segments=segments, unified=unified,
        mix_wav=mix_wav if mix_wav.exists() else None,
        foley_wav=foley_wav if foley_wav.exists() else None)
    # Sprint section 8: every downstream artifact must reference
    # this frozen schedule. A missing/mismatched reference fails
    # verification exactly like a misplaced line -- the media was
    # built against a schedule its artifacts do not agree on.
    from .unified_timeline import check_timeline_refs
    ref_check = check_timeline_refs(job_dir, unified)
    report["timeline_ref_check"] = ref_check
    if ref_check["failures"]:
        report["failures"].extend(ref_check["failures"])
        report["passed"] = not report["failures"]
        report["summary"] += (
            f"; {len(ref_check['failures'])} timeline-ref failure(s)")
    return report
