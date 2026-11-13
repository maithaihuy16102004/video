"""QA gates for AI Clip Studio — split Technical QA and Creative QA.

Background (2026-11-11, Mai's review)
--------------------------------------
The old single-score QA gave "Chiec Vi Trong Mua" v3 8.70/10 and Eiffel
v4 8.75/10, but Mai rejected both scores. The design flaw:

* camera 10.0 was scored from ffprobe + RMS + SRT — i.e. from
  1920x1080 / 24 fps only. No shot was ever evaluated.
* Vietnamese voice 10.0 was scored from duration + RMS. Pronunciation
  was never checked and the voice was never ear-verified.
* animation 8.0 came from motion delta only; environment 8.0 only
  because lamps / rain / a bus stop were present; image quality 7.0
  was docked only because night scenes were dark.

Both videos are therefore reclassified TECHNICAL_PASS /
CREATIVE_REVIEW_FAILED (Mai's preliminary art score: 4-5/10).

This module enforces the split. DRAFT_PASSED_QA now requires BOTH
gates to pass, independently:

* :class:`TechnicalGate` — objective, measurable by code: container,
  codec, fps, resolution, timeline sync, audio not cut off, script
  hash, real rendered frames, no pipeline errors. It says NOTHING
  about art. Its numbers must never be reused as creative evidence.
* :class:`CreativeGate` — 10 independent creative criteria, each
  0-10, each requiring its own evidence. Missing evidence for any
  criterion means that criterion is ``None`` and the gate returns
  ``CREATIVE_REVIEW_REQUIRED`` — it never invents a PASS.
* :func:`combine` — the only place a final verdict is produced.
* :func:`rescore_old` — re-scores an old single-score QA JSON under
  the new definitions and spells out, per old score, where it was wrong.

Hard rules (enforced in code, not just documented)
--------------------------------------------------
(a) Missing evidence for a criterion -> that criterion is ``None``
    and the creative gate returns ``CREATIVE_REVIEW_REQUIRED``.
(b) ffprobe / RMS / resolution / frame count / motion delta are
    FORBIDDEN as evidence for cinematography and for art criteria.
    Cinematography evidence must be a shot list (distinct shot types,
    close-up / insert / reaction present?, narrative purpose per shot)
    plus a contact sheet. Character / environment art evidence must
    be frame inspections stamped with timestamp / frame number.
(c) Voice: without verified transcription / pronunciation the
    audio_experience score is capped at 7.0. Evidence must state
    ``pronunciation_verified: False, method: timing+RMS only`` and a
    10.0 is never given without verification.
(d) subtitle_readability must measure the real font size of each
    phrase (uniform or not) and the number of lines.

faster-whisper experiment (run 2026-11-11 on this VM, real results)
--------------------------------------------------------------------
Goal: verify pronunciation by transcribing real narration, so rule (c)
can eventually be lifted with evidence instead of a cap.

* ``python3 -m venv /tmp/whisper-venv`` then
  ``pip install faster-whisper`` FAILED at first: ``OSError: [Errno 28]
  No space left on device`` — /tmp is a 512 MB tmpfs and only ~125 MB
  was free. Retry with ``pip install --no-cache-dir faster-whisper``
  and ``TMPDIR=~/workspace/.pip-tmp`` SUCCEEDED. Installed:
  faster-whisper 1.2.1, av 19.0.2, ctranslate2 4.9.0,
  tokenizers 0.23.3, onnxruntime 1.31.1, numpy 2.5.4. The venv is
  472 MB, i.e. it barely fits in /tmp (41 MB free afterwards).
* Transcribing a file path FAILED: faster-whisper 1.2.1 calls
  ``av.open(..., metadata_errors="ignore")`` but av 19.0.2 no longer
  accepts that keyword (``TypeError: open() got an unexpected keyword
  argument 'metadata_errors'``). The file-path API is therefore broken
  with this av version; fix options are pinning ``av<19`` or bypassing
  av (see below).
* Workaround that WORKED: decode the WAV with the stdlib ``wave``
  module to a float32 numpy array resampled to 16 kHz and pass the
  array to ``model.transcribe()`` (array input skips av entirely).
  ``~/workspace/acceptance_loop/v3/narration/line1.wav`` (3.552 s,
  48 kHz) with the ``tiny`` model (downloaded from the HF hub,
  Systran/faster-whisper-tiny) transcribed as::

      [0.00-3.20] He sold the Eiffel Tower twice, and nobody stopped him.

  detected language ``en``, probability 1.0 — an EXACT match of the
  script hook in ``v3/package_v3.json``. Pronunciation verification
  via faster-whisper is therefore feasible on this VM; the remaining
  work is wiring the numpy-array path (or an av pin) into the
  pipeline and comparing transcription vs script text (WER) per line.
  Vietnamese lines still need a real test with a Vietnamese-capable
  model (``small`` is already cached in ~/.cache/huggingface from the
  earlier run) before the voice cap can be lifted for Vietnamese.

Only the standard library is used by the gates themselves (ffprobe /
ffmpeg are invoked as subprocesses). No AI video generation, no
network, no Drive access in this module.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Pixel silhouette IoU (A-S5 / Phase F): implemented in
# qa_measurements.py, re-exported here so the QA gates own the
# entry point. qa_measurements imports no qa_gates code (no cycle).
from .qa_measurements import (  # noqa: E402
    SILHOUETTE_IOU_MAX,
    pairwise_silhouette_report,
    silhouette_iou,
    silhouette_mask,
)

__all__ = [
    "EXPECTED_FPS",
    "EXPECTED_WIDTH",
    "EXPECTED_HEIGHT",
    "EXPECTED_CODEC",
    "DURATION_TOLERANCE_SEC",
    "RMS_MIN",
    "CREATIVE_CRITERIA",
    "CREATIVE_WEIGHTS",
    "CREATIVE_PASS_TOTAL",
    "CREATIVE_PASS_MIN",
    "CHARACTER_ART_CRITERIA",
    "CHARACTER_ART_WEIGHTS",
    "CHARACTER_ART_PASS_TOTAL",
    "CHARACTER_ART_PASS_MIN",
    "VOICE_UNVERIFIED_CAP",
    "CheckResult",
    "TechnicalGateResult",
    "CreativeGateResult",
    "CharacterArtGateResult",
    "TechnicalGate",
    "CreativeGate",
    "CharacterArtGate",
    "combine",
    "rescore_old",
    "probe_video",
    "SILHOUETTE_IOU_MAX",
    "silhouette_mask",
    "silhouette_iou",
    "pairwise_silhouette_report",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_FPS = 24
EXPECTED_WIDTH = 1920
EXPECTED_HEIGHT = 1080
EXPECTED_CODEC = "h264"
DURATION_TOLERANCE_SEC = 0.6
RMS_MIN = 0.005
VOICE_UNVERIFIED_CAP = 7.0
CREATIVE_PASS_TOTAL = 8.0
CREATIVE_PASS_MIN = 7.0

CREATIVE_CRITERIA = (
    "character_art",
    "environment_art",
    "cinematography",
    "animation_quality",
    "acting_expressions",
    "visual_storytelling",
    "composition",
    "lighting",
    "audio_experience",
    "subtitle_readability",
)

# Weights sum to 1.0. Cinematography and storytelling carry the most
# weight because the old QA failed exactly there (no shot evaluation,
# no story-beat evaluation).
CREATIVE_WEIGHTS = {
    "character_art": 0.12,
    "environment_art": 0.12,
    "cinematography": 0.14,
    "animation_quality": 0.12,
    "acting_expressions": 0.10,
    "visual_storytelling": 0.12,
    "composition": 0.08,
    "lighting": 0.08,
    "audio_experience": 0.07,
    "subtitle_readability": 0.05,
}

# ---------------------------------------------------------------------------
# Character Art Gate (PREMIUM_STICKMAN v3, independent of Technical QA).
#
# The creative criterion "character_art" above is a single 0-10 score
# inside the creative gate; this gate judges the CHARACTER DESIGN
# itself, from the design sheet, on 8 sub-criteria. It is independent:
# a technical PASS can never compensate for a bad character design, and
# a video can never reach DRAFT_PASSED_QA while this gate is not
# CHARACTER_ART_PASS. Until Mai (the human reviewer) approves the
# design sheet, the status is CHARACTER_ART_REVIEW_REQUIRED -- the gate
# never invents a PASS from scores alone.
# ---------------------------------------------------------------------------

CHARACTER_ART_CRITERIA = (
    "silhouette",
    "proportion",
    "line_quality",
    "joint_quality",
    "expression",
    "style_consistency",
    "small_size_readability",
    "animation_compatibility",
)

CHARACTER_ART_WEIGHTS = {
    "silhouette": 0.18,
    "proportion": 0.18,
    "line_quality": 0.14,
    "joint_quality": 0.14,
    "expression": 0.12,
    "style_consistency": 0.10,
    "small_size_readability": 0.07,
    "animation_compatibility": 0.07,
}

CHARACTER_ART_PASS_TOTAL = 8.0
CHARACTER_ART_PASS_MIN = 7.0

# Evidence that is FORBIDDEN for cinematography / art criteria (rule b).
# These measure the container or the signal, never the art. If any of
# them is the *basis* of the evidence (declared in ``method`` or as the
# only evidence keys), the evidence is rejected.
FORBIDDEN_EVIDENCE_TOKENS = (
    "ffprobe",
    "rms",
    "resolution",
    "frame_count",
    "motion_delta",
    "total_frames",
)

# Shot types that prove the camera actually varies (rule b).
CLOSE_SHOT_TYPES = {
    "CLOSE_UP", "CLOSEUP", "HOOK_CLOSEUP", "CLOSE-UP",
    "INSERT", "REACTION", "REACTION_SHOT", "INSERT_SHOT",
    "OVER_THE_SHOULDER", "OTS", "EXTREME_CLOSE_UP",
}

# Old QA category name -> new creative criterion.
OLD_TO_NEW = {
    "camera_layout": "cinematography",
    "camera_framing_16x9": "cinematography",
    "vietnamese_voice": "audio_experience",
    "voice_narration_timing": "audio_experience",
    "character_animation": "animation_quality",
    "motion_smoothness": "animation_quality",
    "character_consistency": "character_art",
    "environment_quality": "environment_art",
    "scene_environment": "environment_art",
    "dialogue_subtitle_sync": "subtitle_readability",
    "captions_legibility": "subtitle_readability",
    "sfx_sync": "audio_experience",
    "sfx_music_sync": "audio_experience",
    "image_quality": "lighting",
    "storytelling_pacing": "visual_storytelling",
    "story_hook_twist_payoff": "visual_storytelling",
    "script_accuracy": None,  # legitimate technical check, not a creative criterion
}


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """One technical check: pass/fail plus the measured detail."""

    name: str
    passed: bool
    detail: str
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass
class TechnicalGateResult:
    status: str  # TECHNICAL_PASS | TECHNICAL_FAIL
    checks: dict[str, CheckResult] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "TECHNICAL_PASS"

    def failed_checks(self) -> list[str]:
        return [n for n, c in self.checks.items() if not c.passed]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "checks": {n: c.to_dict() for n, c in self.checks.items()},
            "failed_checks": self.failed_checks(),
        }


@dataclass
class CreativeGateResult:
    status: str  # CREATIVE_PASS | CREATIVE_FAIL | CREATIVE_REVIEW_REQUIRED
    # criterion -> score 0..10, or None when evidence is missing.
    scores: dict[str, float | None] = field(default_factory=dict)
    weighted_total: float | None = None
    # criterion -> human-readable reason (cap applied, evidence rejected, ...)
    reasons: dict[str, str] = field(default_factory=dict)
    capped: dict[str, float] = field(default_factory=dict)  # criterion -> cap applied

    @property
    def passed(self) -> bool:
        return self.status == "CREATIVE_PASS"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "scores": self.scores,
            "weighted_total": self.weighted_total,
            "reasons": self.reasons,
            "capped": self.capped,
        }


@dataclass
class CharacterArtGateResult:
    """Result of the independent Character Art Gate.

    status: CHARACTER_ART_PASS | CHARACTER_ART_FAIL |
        CHARACTER_ART_REVIEW_REQUIRED.
    ``human_approved`` records whether Mai approved the design sheet;
    without it the gate can never PASS, whatever the scores say.
    """
    status: str
    # sub-criterion -> score 0..10, or None when evidence is missing.
    scores: dict[str, float | None] = field(default_factory=dict)
    weighted_total: float | None = None
    reasons: dict[str, str] = field(default_factory=dict)
    design_sheet: dict = field(default_factory=dict)
    human_approved: bool = False

    @property
    def passed(self) -> bool:
        return self.status == "CHARACTER_ART_PASS"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "scores": self.scores,
            "weighted_total": self.weighted_total,
            "reasons": self.reasons,
            "design_sheet": self.design_sheet,
            "human_approved": self.human_approved,
        }


# ---------------------------------------------------------------------------
# ffprobe / ffmpeg helpers (real measurement, stdlib subprocess only)
# ---------------------------------------------------------------------------


def probe_video(video_path: str | Path) -> dict:
    """Run ffprobe on a real file and return its parsed JSON.

    Raises FileNotFoundError if the file does not exist and
    RuntimeError if ffprobe fails (file unreadable / not a video).
    """
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"video file not found: {path}")
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,width,height,"
            "r_frame_rate,avg_frame_rate",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def _parse_frame_rate(value: str | None) -> float | None:
    if not value:
        return None
    try:
        num, den = value.split("/")
        den_f = float(den)
        return float(num) / den_f if den_f else None
    except (ValueError, ZeroDivisionError):
        try:
            return float(value)
        except ValueError:
            return None


def _measure_rms_db(video_path: str | Path, start: float, end: float) -> float | None:
    """Measure linear RMS of the audio in [start, end) with ffmpeg astats.

    Returns None when ffmpeg fails or the window is silent / has no
    audio. ``-inf`` dB (digital silence) maps to 0.0.
    """
    duration = max(0.0, end - start)
    if duration <= 0:
        return None
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "info",
            "-ss", f"{start:.3f}",
            "-i", str(video_path),
            "-t", f"{duration:.3f}",
            "-vn", "-af", "astats=metadata=1",
            "-f", "null", "-",
        ],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        return None
    # astats prints one "Overall" section; take its RMS level dB.
    overall = False
    for line in (proc.stderr or "").splitlines():
        if "Overall" in line:
            overall = True
        if overall and "RMS level dB:" in line:
            value = line.split("RMS level dB:")[-1].strip()
            if value in ("-inf", "-infinity"):
                return 0.0
            try:
                return 10.0 ** (float(value) / 20.0)
            except ValueError:
                return None
    return None


# ---------------------------------------------------------------------------
# Technical gate
# ---------------------------------------------------------------------------


class TechnicalGate:
    """Objective checks measurable by code. Says nothing about art.

    ``run()`` needs the real video file plus the production artefacts:
    the planned timeline duration, the dialogue windows (start/end per
    spoken line), the expected script hash, the motion report from the
    frame-by-frame renderer, and the pipeline error list. Every check
    is reported individually; the gate passes only when ALL pass.
    """

    CHECKS = (
        "video_valid",
        "codec_h264",
        "fps_24",
        "resolution_1920x1080",
        "has_audio",
        "timeline_sync",
        "audio_not_cut",
        "script_hash_match",
        "frames_rendered_real",
        "pipeline_no_errors",
    )

    def run(
        self,
        video_path: str | Path,
        timeline_duration_sec: float | None = None,
        dialogue_windows: list[dict] | None = None,
        expected_script_hash: str | None = None,
        actual_script_hash: str | None = None,
        motion_report_path: str | Path | None = None,
        pipeline_errors: list | None = None,
        probe: dict | None = None,
    ) -> TechnicalGateResult:
        checks: dict[str, CheckResult] = {}
        path = Path(video_path)

        # --- probe (real ffprobe unless a probe dict is injected) ---
        probe_data: dict | None = probe
        probe_error: str | None = None
        if probe_data is None:
            try:
                probe_data = probe_video(path)
            except (FileNotFoundError, RuntimeError) as exc:
                probe_error = str(exc)

        streams = (probe_data or {}).get("streams", []) if probe_data else []
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        vstream = video_streams[0] if video_streams else {}
        try:
            duration = float((probe_data or {}).get("format", {}).get("duration", 0) or 0)
        except (TypeError, ValueError):
            duration = 0.0

        checks["video_valid"] = CheckResult(
            "video_valid",
            probe_error is None and bool(video_streams) and duration > 0,
            probe_error or f"video stream present, duration={duration:.3f}s",
            {"duration_sec": duration},
        )

        codec = (vstream.get("codec_name") or "").lower()
        checks["codec_h264"] = CheckResult(
            "codec_h264", codec == EXPECTED_CODEC,
            f"codec={codec or 'none'} (expected {EXPECTED_CODEC})",
            {"codec_name": codec},
        )

        fps = _parse_frame_rate(
            vstream.get("avg_frame_rate") or vstream.get("r_frame_rate")
        )
        checks["fps_24"] = CheckResult(
            "fps_24",
            fps is not None and abs(fps - EXPECTED_FPS) <= 0.5,
            f"fps={fps} (expected {EXPECTED_FPS})",
            {"fps": fps},
        )

        width, height = vstream.get("width"), vstream.get("height")
        checks["resolution_1920x1080"] = CheckResult(
            "resolution_1920x1080",
            width == EXPECTED_WIDTH and height == EXPECTED_HEIGHT,
            f"resolution={width}x{height} (expected "
            f"{EXPECTED_WIDTH}x{EXPECTED_HEIGHT})",
            {"width": width, "height": height},
        )

        checks["has_audio"] = CheckResult(
            "has_audio", bool(audio_streams),
            f"audio streams={len(audio_streams)}",
            {"audio_streams": len(audio_streams)},
        )

        # --- timeline sync: |video duration - planned timeline| <= 0.6 s ---
        if timeline_duration_sec is None:
            checks["timeline_sync"] = CheckResult(
                "timeline_sync", False,
                "no timeline duration supplied — cannot verify sync",
                {"video_duration_sec": duration},
            )
        else:
            diff = abs(duration - timeline_duration_sec)
            checks["timeline_sync"] = CheckResult(
                "timeline_sync", diff <= DURATION_TOLERANCE_SEC,
                f"video={duration:.3f}s timeline={timeline_duration_sec:.3f}s "
                f"diff={diff:.3f}s (tolerance {DURATION_TOLERANCE_SEC}s)",
                {"video_duration_sec": duration,
                 "timeline_duration_sec": timeline_duration_sec, "diff_sec": diff},
            )

        # --- audio not cut: every dialogue window audible, last line inside timeline ---
        checks["audio_not_cut"] = self._check_audio_not_cut(
            path, duration, timeline_duration_sec, dialogue_windows,
            probe_error is not None,
        )

        # --- script hash ---
        if not expected_script_hash or not actual_script_hash:
            checks["script_hash_match"] = CheckResult(
                "script_hash_match", False,
                "script hash missing (expected and actual both required)",
                {},
            )
        else:
            match = expected_script_hash == actual_script_hash
            checks["script_hash_match"] = CheckResult(
                "script_hash_match", match,
                "script hash matches" if match
                else "script hash MISMATCH — video was rendered from a "
                     "different script version",
                {"expected": expected_script_hash[:12],
                 "actual": actual_script_hash[:12]},
            )

        # --- real rendered frames: motion report exists, frame count matches ---
        checks["frames_rendered_real"] = self._check_frames_rendered(
            motion_report_path, duration, fps,
        )

        # --- pipeline errors ---
        errors = pipeline_errors or []
        checks["pipeline_no_errors"] = CheckResult(
            "pipeline_no_errors", not errors,
            "no pipeline errors" if not errors else f"errors: {errors}",
            {"errors": list(errors)},
        )

        status = (
            "TECHNICAL_PASS"
            if all(c.passed for c in checks.values())
            else "TECHNICAL_FAIL"
        )
        return TechnicalGateResult(status=status, checks=checks)

    # -- helpers ----------------------------------------------------------

    def _check_audio_not_cut(
        self, path: Path, duration: float,
        timeline_duration_sec: float | None,
        dialogue_windows: list[dict] | None,
        probe_failed: bool,
    ) -> CheckResult:
        if probe_failed:
            return CheckResult(
                "audio_not_cut", False,
                "video could not be probed — audio cannot be verified", {},
            )
        if not dialogue_windows:
            return CheckResult(
                "audio_not_cut", False,
                "no dialogue windows supplied — cannot verify the final "
                "line is not cut off",
                {},
            )
        problems: list[str] = []
        measured: list[dict] = []
        for window in dialogue_windows:
            start = float(window.get("start", 0))
            end = float(window.get("end", 0))
            label = window.get("line", window.get("text", "?")) or "?"
            if "rms" in window and window["rms"] is not None:
                rms = float(window["rms"])
            else:
                rms = _measure_rms_db(path, start, end)
            measured.append({"line": str(label)[:40], "start": start,
                             "end": end, "rms": rms})
            if rms is None:
                problems.append(f"line '{label}': RMS could not be measured")
            elif rms <= RMS_MIN:
                problems.append(
                    f"line '{label}': RMS {rms:.5f} <= {RMS_MIN} "
                    f"(silent / cut off)"
                )
        last = dialogue_windows[-1]
        last_end = float(last.get("end", 0))
        limit = timeline_duration_sec if timeline_duration_sec is not None else duration
        if last_end > limit + 1e-9:
            problems.append(
                f"final line ends at {last_end:.2f}s, after the timeline "
                f"({limit:.2f}s) — final line is cut off"
            )
        if problems:
            return CheckResult("audio_not_cut", False, "; ".join(problems),
                               {"windows": measured})
        return CheckResult(
            "audio_not_cut", True,
            f"all {len(dialogue_windows)} dialogue windows audible "
            f"(RMS > {RMS_MIN}); final line ends at {last_end:.2f}s "
            f"inside the timeline",
            {"windows": measured},
        )

    def _check_frames_rendered(
        self, motion_report_path: str | Path | None,
        duration: float, fps: float | None,
    ) -> CheckResult:
        if not motion_report_path:
            return CheckResult(
                "frames_rendered_real", False,
                "no motion report supplied — cannot prove frames were "
                "rendered by code",
                {},
            )
        report_path = Path(motion_report_path)
        if not report_path.is_file():
            return CheckResult(
                "frames_rendered_real", False,
                f"motion report not found: {report_path}",
                {},
            )
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return CheckResult(
                "frames_rendered_real", False,
                f"motion report unreadable: {exc}",
                {},
            )
        total_frames = report.get("total_frames")
        if total_frames is None or fps is None or duration <= 0:
            return CheckResult(
                "frames_rendered_real", False,
                "motion report has no total_frames, or fps/duration unknown",
                {"total_frames": total_frames},
            )
        expected = int(round(duration * fps))
        ok = int(total_frames) == expected
        return CheckResult(
            "frames_rendered_real", ok,
            f"motion report total_frames={total_frames}, expected "
            f"round({duration:.3f}s x {fps}fps)={expected}"
            + ("" if ok else " — MISMATCH: frames were not all rendered"),
            {"total_frames": total_frames, "expected_frames": expected},
        )


# ---------------------------------------------------------------------------
# Creative gate
# ---------------------------------------------------------------------------


def _evidence_method(evidence: dict) -> str:
    return str(evidence.get("method", "") or "").lower()


def _evidence_text(evidence: dict) -> str:
    """All evidence text, lower-cased, for forbidden-token detection."""
    parts = [str(evidence.get("method", ""))]
    parts.extend(str(k) for k in evidence.keys())
    return " ".join(parts).lower()


def _uses_forbidden_evidence(evidence: dict) -> list[str]:
    """Forbidden tokens that appear as the *basis* of the evidence.

    A token counts only when it is named in ``method`` or is the only
    substance of the evidence — e.g. method "ffprobe + RMS + SRT check"
    or evidence keys {"resolution": ...}. A passing mention inside a
    frame-inspection note does not trigger this.
    """
    method = _evidence_method(evidence)
    found = [t for t in FORBIDDEN_EVIDENCE_TOKENS if t in method]
    return found


def _frame_inspections(evidence: dict) -> list[dict]:
    insp = evidence.get("frame_inspections") or evidence.get("frames") or []
    return insp if isinstance(insp, list) else []


def _has_valid_frame_inspections(evidence: dict, minimum: int = 1) -> bool:
    insp = _frame_inspections(evidence)
    if len(insp) < minimum:
        return False
    for item in insp:
        if not isinstance(item, dict):
            return False
        if "frame" not in item and "timestamp_sec" not in item:
            return False
        if not str(item.get("note", "")).strip():
            return False
    return True


def _validate_evidence(criterion: str, evidence: Any) -> tuple[bool, str]:
    """Check that evidence for one criterion is sufficient (rule a/b/d).

    Returns (ok, reason). ``ok=False`` means the criterion scores None.
    """
    if not isinstance(evidence, dict) or not evidence:
        return False, "no evidence supplied"
    if criterion == "cinematography":
        forbidden = _uses_forbidden_evidence(evidence)
        if forbidden:
            return False, (
                "evidence based on forbidden technical measurement(s): "
                + ", ".join(forbidden)
                + " — cinematography must be judged from the shot list "
                  "and contact sheet, never from ffprobe/RMS/resolution"
            )
        shots = evidence.get("shot_list")
        if not isinstance(shots, list) or not shots:
            return False, "no shot_list supplied"
        if not evidence.get("contact_sheet"):
            return False, "no contact_sheet supplied"
        for shot in shots:
            if not isinstance(shot, dict):
                return False, "shot_list entry is not a shot dict"
            if not shot.get("shot_type"):
                return False, "a shot has no shot_type"
            if not str(shot.get("narrative_purpose", "")).strip():
                return False, (
                    f"shot {shot.get('shot_id', '?')} has no "
                    "narrative_purpose"
                )
        return True, "shot list + contact sheet present"
    if criterion in ("character_art", "environment_art", "acting_expressions",
                    "composition", "lighting"):
        if _uses_forbidden_evidence(evidence):
            return False, (
                "evidence based on forbidden technical measurement(s) — "
                "art must be judged from frame inspection, never from "
                "ffprobe/RMS/resolution/frame count/motion delta"
            )
        if not _has_valid_frame_inspections(evidence):
            return False, (
                "no frame inspection with timestamp/frame + note supplied"
            )
        return True, "frame inspection(s) present"
    if criterion == "animation_quality":
        if _has_valid_frame_inspections(evidence):
            return True, "frame inspection(s) present"
        if evidence.get("motion_report"):
            return False, (
                "motion report alone is not enough — animation_quality "
                "needs at least one frame inspection with timestamp/frame "
                "+ note (motion delta measures movement, not acting)"
            )
        return False, "no frame inspection or motion report supplied"
    if criterion == "visual_storytelling":
        beats = evidence.get("beats") or evidence.get("story_beats")
        if isinstance(beats, dict) and beats.get("hook") and beats.get("twist"):
            return True, "hook/twist/payoff beats present"
        if isinstance(beats, list) and len(beats) >= 2:
            return True, "story beats present"
        return False, "no hook/twist/payoff beats supplied"
    if criterion == "audio_experience":
        if "pronunciation_verified" not in evidence:
            return False, (
                "pronunciation_verified not declared — voice evidence "
                "must state pronunciation_verified: True/False and its "
                "method (rule c)"
            )
        if not evidence.get("sfx_events") and not evidence.get("voice_lines"):
            return False, "no sfx_events or voice_lines supplied"
        return True, "audio evidence present"
    if criterion == "subtitle_readability":
        sizes = evidence.get("font_sizes_px")
        if not isinstance(sizes, list) or not sizes:
            return False, (
                "no font_sizes_px supplied — subtitle readability must "
                "measure the real font size of each phrase (rule d)"
            )
        if "max_lines" not in evidence and "lines_per_phrase" not in evidence:
            return False, "no max_lines / lines_per_phrase supplied"
        return True, "font sizes + line counts present"
    return True, "evidence present"


class CreativeGate:
    """10 independent creative criteria, each 0-10 with mandatory evidence.

    ``evaluate(scores, evidence)`` applies the hard rules:
    missing/insufficient evidence -> score None + CREATIVE_REVIEW_REQUIRED;
    unverified voice -> audio_experience capped at 7.0.
    """

    def evaluate(
        self,
        scores: dict[str, float | None],
        evidence: dict[str, dict],
    ) -> CreativeGateResult:
        final: dict[str, float | None] = {}
        reasons: dict[str, str] = {}
        capped: dict[str, float] = {}
        for criterion in CREATIVE_CRITERIA:
            ev = evidence.get(criterion)
            ok, reason = _validate_evidence(criterion, ev)
            if not ok:
                final[criterion] = None
                reasons[criterion] = f"evidence insufficient: {reason}"
                continue
            raw = scores.get(criterion)
            if raw is None:
                final[criterion] = None
                reasons[criterion] = "no score supplied for this criterion"
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                final[criterion] = None
                reasons[criterion] = f"score {raw!r} is not a number"
                continue
            if not (0.0 <= value <= 10.0):
                final[criterion] = None
                reasons[criterion] = f"score {value} out of range 0-10"
                continue
            if criterion == "audio_experience":
                verified = bool(ev.get("pronunciation_verified"))
                if not verified and value > VOICE_UNVERIFIED_CAP:
                    capped[criterion] = VOICE_UNVERIFIED_CAP
                    reasons[criterion] = (
                        "voice capped at 7.0: pronunciation_verified is "
                        "False — evidence states "
                        "'pronunciation_verified: False, method: "
                        "timing+RMS only'. A 10.0 requires verified "
                        "transcription/pronunciation (rule c)."
                    )
                    value = VOICE_UNVERIFIED_CAP
            if criterion == "subtitle_readability":
                sizes = ev.get("font_sizes_px") or []
                if len(set(sizes)) > 1:
                    reasons[criterion] = (
                        "font sizes are NOT uniform across phrases: "
                        f"{sorted(set(sizes))} px — readability is judged "
                        "on the real sizes, long lines must be split, not "
                        "shrunk (rule d)"
                    )
            final[criterion] = value
            reasons.setdefault(criterion, reason)

        missing = [c for c, s in final.items() if s is None]
        if missing:
            return CreativeGateResult(
                status="CREATIVE_REVIEW_REQUIRED",
                scores=final,
                weighted_total=None,
                reasons={**reasons,
                         "_gate": "evidence missing for: " + ", ".join(missing)
                         + " — human creative review required, no PASS invented"},
                capped=capped,
            )
        total = sum(final[c] * CREATIVE_WEIGHTS[c] for c in CREATIVE_CRITERIA)
        total = round(total, 2)
        below_min = [c for c in CREATIVE_CRITERIA if final[c] < CREATIVE_PASS_MIN]
        if total >= CREATIVE_PASS_TOTAL and not below_min:
            status = "CREATIVE_PASS"
        else:
            status = "CREATIVE_FAIL"
            reasons["_gate"] = (
                f"weighted total {total} (need >= {CREATIVE_PASS_TOTAL})"
                + (f"; below minimum {CREATIVE_PASS_MIN}: "
                   + ", ".join(below_min) if below_min else "")
            )
        return CreativeGateResult(
            status=status, scores=final, weighted_total=total,
            reasons=reasons, capped=capped,
        )


# ---------------------------------------------------------------------------
# Combine
# ---------------------------------------------------------------------------


def _validate_character_art_evidence(evidence: dict) -> tuple[bool, str, dict]:
    """Evidence for the Character Art Gate: the design sheet (Drive file
    id or local path) plus one inspection note per scored sub-criterion.

    Returns (ok, reason, design_sheet_dict)."""
    if not isinstance(evidence, dict) or not evidence:
        return False, "no evidence supplied", {}
    sheet = evidence.get("design_sheet")
    if not isinstance(sheet, dict) or not sheet:
        return False, "no design_sheet supplied (need drive_file_id or path)", {}
    if not sheet.get("drive_file_id") and not sheet.get("path"):
        return False, ("design_sheet has neither drive_file_id nor path — "
                       "the sheet must be a real file, not a claim"), {}
    notes = evidence.get("notes") or evidence.get("inspections") or {}
    if not isinstance(notes, dict):
        return False, "notes/inspections must be a dict criterion -> note", sheet
    return True, "design sheet + notes present", sheet


class CharacterArtGate:
    """Independent gate for the character DESIGN (not the video).

    ``evaluate(scores, evidence, human_approved=False)``:

    * no design sheet / missing notes / missing scores ->
      CHARACTER_ART_REVIEW_REQUIRED (never invent a PASS);
    * ``human_approved`` False -> CHARACTER_ART_REVIEW_REQUIRED even
      with perfect scores (Mai must approve the sheet herself);
    * approved + every sub-criterion >= 7.0 and weighted total >= 8.0
      -> CHARACTER_ART_PASS, otherwise CHARACTER_ART_FAIL.

    Technical QA scores are never consulted here: a technical PASS
    cannot compensate for a bad character design.
    """

    def evaluate(
        self,
        scores: dict[str, float | None],
        evidence: dict,
        human_approved: bool = False,
    ) -> CharacterArtGateResult:
        ok, reason, sheet = _validate_character_art_evidence(evidence)
        notes = (evidence.get("notes") or evidence.get("inspections") or {}
                 if isinstance(evidence, dict) else {})
        final: dict[str, float | None] = {}
        reasons: dict[str, str] = {}
        if not ok:
            for criterion in CHARACTER_ART_CRITERIA:
                final[criterion] = None
            reasons["_gate"] = f"evidence insufficient: {reason}"
            return CharacterArtGateResult(
                status="CHARACTER_ART_REVIEW_REQUIRED",
                scores=final, weighted_total=None, reasons=reasons,
                design_sheet=sheet, human_approved=bool(human_approved),
            )
        for criterion in CHARACTER_ART_CRITERIA:
            note = notes.get(criterion) if isinstance(notes, dict) else None
            if not str(note or "").strip():
                final[criterion] = None
                reasons[criterion] = ("no inspection note for this "
                                      "sub-criterion")
                continue
            raw = scores.get(criterion)
            if raw is None:
                final[criterion] = None
                reasons[criterion] = "no score supplied for this criterion"
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                final[criterion] = None
                reasons[criterion] = f"score {raw!r} is not a number"
                continue
            if not (0.0 <= value <= 10.0):
                final[criterion] = None
                reasons[criterion] = f"score {value} out of range 0-10"
                continue
            final[criterion] = value
            reasons.setdefault(criterion, reason)
        missing = [c for c, s in final.items() if s is None]
        if missing:
            return CharacterArtGateResult(
                status="CHARACTER_ART_REVIEW_REQUIRED",
                scores=final, weighted_total=None,
                reasons={**reasons,
                         "_gate": "evidence missing for: " + ", ".join(missing)
                         + " — human character-art review required"},
                design_sheet=sheet, human_approved=bool(human_approved),
            )
        total = round(sum(final[c] * CHARACTER_ART_WEIGHTS[c]
                          for c in CHARACTER_ART_CRITERIA), 2)
        below_min = [c for c in CHARACTER_ART_CRITERIA
                     if final[c] < CHARACTER_ART_PASS_MIN]
        if not human_approved:
            return CharacterArtGateResult(
                status="CHARACTER_ART_REVIEW_REQUIRED",
                scores=final, weighted_total=total,
                reasons={**reasons,
                         "_gate": "scores computed (total "
                         f"{total}) but the design sheet has not been "
                         "approved by Mai yet — status stays "
                         "CHARACTER_ART_REVIEW_REQUIRED"},
                design_sheet=sheet, human_approved=False,
            )
        if total >= CHARACTER_ART_PASS_TOTAL and not below_min:
            status = "CHARACTER_ART_PASS"
        else:
            status = "CHARACTER_ART_FAIL"
            reasons["_gate"] = (
                f"weighted total {total} (need >= {CHARACTER_ART_PASS_TOTAL})"
                + (f"; below minimum {CHARACTER_ART_PASS_MIN}: "
                   + ", ".join(below_min) if below_min else "")
            )
        return CharacterArtGateResult(
            status=status, scores=final, weighted_total=total,
            reasons=reasons, design_sheet=sheet, human_approved=True,
        )


def combine(
    technical: TechnicalGateResult | dict,
    creative: CreativeGateResult | dict,
    character_art: CharacterArtGateResult | dict | None = None,
) -> dict:
    """Produce the single final verdict from the two independent gates.

    * technical FAIL            -> TECHNICAL_FAIL
    * technical PASS, creative evidence missing -> CREATIVE_REVIEW_REQUIRED
    * technical PASS + creative PASS          -> DRAFT_PASSED_QA
    * technical PASS + creative FAIL          -> TECHNICAL_PASS_CREATIVE_FAIL

    When a Character Art Gate result is supplied (third argument), it is
    a third independent gate: DRAFT_PASSED_QA additionally requires
    CHARACTER_ART_PASS. An unapproved design sheet gives
    CHARACTER_ART_REVIEW_REQUIRED; an approved-but-failing design gives
    CHARACTER_ART_FAIL. Technical scores never compensate for it.
    Omitting it preserves the old two-gate behaviour.
    """
    t_status = technical.status if hasattr(technical, "status") else technical.get("status")
    c_status = creative.status if hasattr(creative, "status") else creative.get("status")
    if t_status != "TECHNICAL_PASS":
        verdict = "TECHNICAL_FAIL"
    elif c_status == "CREATIVE_REVIEW_REQUIRED":
        verdict = "CREATIVE_REVIEW_REQUIRED"
    elif c_status == "CREATIVE_PASS":
        verdict = "DRAFT_PASSED_QA"
    elif c_status == "CREATIVE_FAIL":
        verdict = "TECHNICAL_PASS_CREATIVE_FAIL"
    else:  # unknown creative status — fail closed, never invent a PASS
        verdict = "CREATIVE_REVIEW_REQUIRED"
    ca_status = None
    if character_art is not None:
        ca_status = (character_art.status if hasattr(character_art, "status")
                     else character_art.get("status"))
        if verdict == "DRAFT_PASSED_QA":
            if ca_status == "CHARACTER_ART_PASS":
                pass  # all three gates pass
            elif ca_status == "CHARACTER_ART_FAIL":
                verdict = "CHARACTER_ART_FAIL"
            else:  # REVIEW_REQUIRED or unknown — fail closed
                verdict = "CHARACTER_ART_REVIEW_REQUIRED"
    return {
        "verdict": verdict,
        "technical_status": t_status,
        "creative_status": c_status,
        "character_art_status": ca_status,
        "draft_passed_qa": verdict == "DRAFT_PASSED_QA",
    }


# ---------------------------------------------------------------------------
# Re-scoring old QA JSONs under the new definitions
# ---------------------------------------------------------------------------


def _derive_cinematography(old_score: float, evidence: dict) -> tuple[float, str]:
    """Cinematography from the shot list actually used (rule b).

    Old camera scores of 10.0 were measured from resolution/fps only.
    The new score counts distinct shot types and whether close-up /
    insert / reaction shots exist at all.
    """
    shots = evidence.get("shot_list") or []
    types = {str(s.get("shot_type", "")).upper() for s in shots
             if isinstance(s, dict)}
    has_close = bool(types & CLOSE_SHOT_TYPES)
    if not shots:
        return old_score, "no shot_list in evidence — cannot re-derive"
    if len(types) == 1:
        new = 4.0
    elif len(types) == 2:
        new = 6.0
    elif len(types) <= 4:
        new = 7.5 if has_close else 6.5
    else:
        new = 8.5 if has_close else 7.5
    # A derived score (no human creative review) never exceeds 8.5.
    new = min(new, 8.5)
    return new, (
        f"old camera score {old_score} was measured from ffprobe/RMS/"
        f"resolution only (no shot was evaluated). Re-derived from the "
        f"real shot list: {len(types)} distinct shot type(s) "
        f"({', '.join(sorted(types)) or 'none'}), "
        f"close-up/insert/reaction: {'yes' if has_close else 'NO'} "
        f"-> {new}"
    )


def _derive_voice(old_score: float, evidence: dict) -> tuple[float, str]:
    """Voice: capped at 7.0 unless pronunciation is verified (rule c)."""
    verified = bool(evidence.get("pronunciation_verified"))
    if verified:
        return old_score, (
            f"pronunciation verified ({evidence.get('method', 'method not '
            'stated')}) — old voice score {old_score} kept"
        )
    return min(old_score, VOICE_UNVERIFIED_CAP), (
        f"old voice score {old_score} was measured from timing+RMS only — "
        f"no pronunciation check, never ear-verified. Evidence states "
        f"'pronunciation_verified: False, method: timing+RMS only' "
        f"-> capped at {VOICE_UNVERIFIED_CAP} (rule c)"
    )


def rescore_old(old_qa_json_path: str | Path, evidence: dict) -> dict:
    """Re-score an old single-score QA JSON under the new definitions.

    ``evidence`` uses the same shape as :class:`CreativeGate` evidence
    (per-criterion dicts), plus optional keys:

    * ``shot_list`` — top-level shot list, used when the cinematography
      evidence has none.
    * ``pronunciation_verified`` / ``method`` — top-level voice facts,
      used when audio_experience evidence has none.
    * ``technical`` — an optional TechnicalGateResult/dict; when
      present the final verdict is computed with :func:`combine`,
      otherwise the technical status is reported as NOT_RECHECKED.

    Returns a dict with the old total, the new per-criterion scores
    (each with old score, new score and the reason the old score was
    wrong), the new weighted total (None when a criterion is missing
    evidence) and the verdict.
    """
    path = Path(old_qa_json_path)
    old = json.loads(path.read_text(encoding="utf-8"))
    old_scores = old.get("scores", {}) or {}
    old_total = old.get("weighted_total")

    # Collect old scores per new criterion (several old categories can
    # map to one new criterion; keep the lowest — the weakest link).
    per_criterion: dict[str, list[tuple[str, float, str]]] = {}
    unmapped: dict[str, float] = {}
    for old_name, entry in old_scores.items():
        score = entry.get("score") if isinstance(entry, dict) else None
        if score is None:
            continue
        new_name = OLD_TO_NEW.get(old_name)
        if new_name is None:
            unmapped[old_name] = float(score)
            continue
        per_criterion.setdefault(new_name, []).append(
            (old_name, float(score),
             str(entry.get("method", "")) if isinstance(entry, dict) else "")
        )

    new_scores: dict[str, dict] = {}
    for criterion in CREATIVE_CRITERIA:
        ev = dict(evidence.get(criterion) or {})
        # Top-level fallbacks for the two most common inputs.
        if criterion == "cinematography" and not ev.get("shot_list"):
            ev["shot_list"] = evidence.get("shot_list") or []
        if criterion == "audio_experience":
            ev.setdefault("pronunciation_verified",
                          evidence.get("pronunciation_verified", False))
            ev.setdefault("method",
                          evidence.get("method", "timing+RMS only"))
        entries = per_criterion.get(criterion, [])
        if not entries:
            new_scores[criterion] = {
                "old_category": None, "old_score": None, "new_score": None,
                "reason": "no old QA category maps to this criterion and "
                          "no new evidence was supplied — human creative "
                          "review required",
            }
            continue
        old_name, old_score, old_method = min(entries, key=lambda e: e[1])
        if criterion == "cinematography":
            new, reason = _derive_cinematography(old_score, ev)
        elif criterion == "audio_experience":
            # Voice cap applies to the voice part; SFX (RMS-verified) is
            # legitimate audio evidence, so the criterion is the minimum
            # of the capped voice score and the SFX score, if both exist.
            # The reported old_score is the VOICE old score (the SFX
            # old score is a different measurement, not the voice).
            voice_entries = [e for e in entries
                             if e[0] in ("vietnamese_voice",
                                         "voice_narration_timing")]
            voice_old = voice_entries[0][1] if voice_entries else old_score
            if voice_entries:
                old_name = voice_entries[0][0]
            voice_new, reason = _derive_voice(voice_old, ev)
            sfx = [s for n, s, _ in entries if n.startswith("sfx")]
            if sfx:
                new = min(voice_new, min(sfx))
                reason += (f"; SFX part scored {min(sfx)} (RMS-verified "
                           "SFX is legitimate audio evidence) -> "
                           f"audio_experience = min(voice, sfx) = {new}")
            else:
                new = voice_new
            old_score = voice_old
        elif criterion == "character_art":
            if _has_valid_frame_inspections(ev):
                new, reason = old_score, (
                    f"old score {old_score} kept — frame inspections with "
                    "face/expression/volume notes are present"
                )
            else:
                new = min(old_score, 6.0)
                reason = (
                    f"old score {old_score} was based on rig/proportions/"
                    "colours only (no volumes, faces, expressions or "
                    "layered costume inspected) -> capped at 6.0"
                )
        elif criterion == "environment_art":
            if _has_valid_frame_inspections(ev):
                new, reason = old_score, (
                    f"old score {old_score} kept — frame inspections with "
                    "depth/lighting notes are present"
                )
            else:
                new = min(old_score, 6.0)
                reason = (
                    f"old score {old_score} was given only because lamps/"
                    "rain/a bus stop were present (no foreground/"
                    "midground/background, lighting or depth inspection) "
                    "-> capped at 6.0"
                )
        elif criterion == "animation_quality":
            if _has_valid_frame_inspections(ev):
                new, reason = old_score, (
                    f"old score {old_score} kept — frame inspections "
                    "support the motion report"
                )
            else:
                new = min(old_score, 7.0)
                reason = (
                    f"old score {old_score} was measured from motion delta "
                    "only (movement, not acting) -> capped at 7.0"
                )
        elif criterion == "subtitle_readability":
            sizes = ev.get("font_sizes_px") or []
            if sizes and len(set(sizes)) > 1:
                new = min(old_score, 7.0)
                reason = (
                    f"old score {old_score} ignored that the final caption "
                    f"was shrunk to {min(sizes)}px while others were "
                    f"{max(sizes)}px — long lines must be split, not "
                    f"shrunk (rule d) -> capped at 7.0"
                )
            elif sizes:
                new, reason = old_score, (
                    f"old score {old_score} kept — font sizes uniform "
                    f"({sorted(set(sizes))} px)"
                )
            else:
                new = min(old_score, 7.0)
                reason = (
                    f"old score {old_score} was given without measuring "
                    "real phrase font sizes -> capped at 7.0 (rule d)"
                )
        elif criterion == "lighting":
            new, reason = old_score, (
                f"old score {old_score} kept as a starting point, but its "
                "method was frame inspection only ('dark night scenes') — "
                "no lighting/shadow/depth measurement; needs a real "
                "lighting inspection to confirm"
            )
        elif criterion == "visual_storytelling":
            beats = ev.get("beats")
            if beats:
                new, reason = old_score, (
                    f"old score {old_score} kept — hook/twist/payoff beats "
                    "with timings are present"
                )
            else:
                new = min(old_score, 7.0)
                reason = (
                    f"old score {old_score} was based on timeline totals / "
                    "motion report, not on hook/twist/payoff beats -> "
                    "capped at 7.0"
                )
        else:  # composition, acting_expressions: no old category at all
            new, reason = None, (
                "no old QA category measured this criterion — human "
                "creative review required"
            )
            new_scores[criterion] = {
                "old_category": old_name, "old_score": old_score,
                "new_score": new, "reason": reason,
            }
            continue
        new_scores[criterion] = {
            "old_category": old_name, "old_score": old_score,
            "new_score": new, "reason": reason,
        }

    # Criteria with no old mapping at all (composition, acting_expressions
    # in both old files) stay None unless evidence supplies a score —
    # rescore_old never invents one.
    scored = {c: v["new_score"] for c, v in new_scores.items()
              if v["new_score"] is not None}
    missing = [c for c, v in new_scores.items() if v["new_score"] is None]
    if missing:
        new_total = None
        creative_status = "CREATIVE_REVIEW_REQUIRED"
    else:
        new_total = round(
            sum(scored[c] * CREATIVE_WEIGHTS[c] for c in CREATIVE_CRITERIA), 2
        )
        below = [c for c in CREATIVE_CRITERIA if scored[c] < CREATIVE_PASS_MIN]
        creative_status = (
            "CREATIVE_PASS"
            if new_total >= CREATIVE_PASS_TOTAL and not below else "CREATIVE_FAIL"
        )

    technical = evidence.get("technical")
    if technical is not None:
        t_status = (technical.status if hasattr(technical, "status")
                    else technical.get("status"))
        verdict = combine(
            {"status": t_status}, {"status": creative_status},
        )["verdict"]
        technical_status = t_status
    else:
        technical_status = "NOT_RECHECKED"
        verdict = creative_status if missing else (
            "CREATIVE_PASS_TECHNICAL_NOT_RECHECKED"
            if creative_status == "CREATIVE_PASS"
            else "CREATIVE_FAIL_TECHNICAL_NOT_RECHECKED"
        )

    return {
        "old_file": str(path),
        "old_weighted_total": old_total,
        "old_status": (old.get("acceptance", {}) or {}).get("status"),
        "new_scores": new_scores,
        "new_weighted_total": new_total,
        "missing_evidence_criteria": missing,
        "unmapped_old_categories": unmapped,
        "creative_status": creative_status,
        "technical_status": technical_status,
        "verdict": verdict,
    }


def script_hash(text: str) -> str:
    """SHA-256 of a script text (helper for the script_hash_match check)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
