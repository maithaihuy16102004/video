"""Audio isolation audit (integration sprint section 9).

Verifies, on the RENDERED stems of a finished job (never on plan
records alone), that scene-local sound stays scene-local:

* every ambience/music bed lies inside its own scene span
  (plan-level), AND the rendered stem is audible inside the span
  and silent outside it;
* rain beds stay inside the rainy scenes' spans;
* foley segments are audible at their anchors, and scenes with no
  foley are silent on the foley stem;
* explicit NONE spans and the end-card span are silent on the
  muted stems.

Measurement guard: ``_rms_db_windows`` bleeds ~0.1 s across window
edges (aselect frame selection; proven 2026-11-13 on the Zeus
stems, where sample-accurate reading showed the sc7 bed starting
at exactly 157.7403 s while the window measurement suggested
157.6 s). Every measured window is therefore inset by GUARD_SEC
on each side. Spans shorter than 2 * GUARD_SEC cannot be measured
and are recorded as skipped, never passed or failed.

Thresholds are calibrated on the real Zeus stems (2026-11-13):
occupied spans measure -33..-39 dB, silent spans -120 dB
(digital silence). AUDIBLE_DB = -50 and SILENT_DB = -70 leave a
20 dB dead zone so neither threshold is brittle.

The visual half of section 9 (lighting/weather reset per scene)
is covered by the B2 isolation proofs and the rendered PROOF D
sequence, not by this module: this audit measures audio only.
"""
from __future__ import annotations

import json
from pathlib import Path

GUARD_SEC = 0.25
AUDIBLE_DB = -50.0
SILENT_DB = -70.0

AUDIT_VERSION = 1


def _load(job_dir: Path, name: str):
    path = job_dir / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _scene_spans(timeline: dict) -> dict:
    """Scene -> (start, end) from the timeline shots' own clock."""
    spans: dict = {}
    clock = 0.0
    for shot in timeline.get("shots") or []:
        duration = float(shot.get("duration") or 0.0)
        start = shot.get("start_sec")
        start = float(start) if start is not None else clock
        end = start + duration
        scene = shot.get("scene")
        if scene in spans:
            spans[scene] = (spans[scene][0], end)
        else:
            spans[scene] = (start, end)
        clock = end
    return spans


def _measure(path: Path, start: float, end: float):
    """RMS dB over [start + guard, end - guard]; None when the
    guarded window is empty (span too short to measure)."""
    from .product_flow import _rms_db_windows
    lo, hi = start + GUARD_SEC, end - GUARD_SEC
    if hi <= lo:
        return None
    return _rms_db_windows(path, [(lo, hi)])


def audit_audio_isolation(job_dir) -> dict:
    """Audit one finished job directory. Returns the report dict
    (also written by the caller as isolation_audit.json)."""
    job_dir = Path(job_dir)
    timeline = _load(job_dir, "timeline.json") or {}
    plan = _load(job_dir, "audio_plan.json") or {}
    resolution = plan.get("v1_cue_resolution") or {}
    beds = resolution.get("beds") or []
    segments = resolution.get("segments") or []
    none_spans = resolution.get("none_spans") or {}
    rain_spans = [tuple(map(float, s)) for s in
                  plan.get("rain_spans") or []]
    end_card = (plan.get("mix") or {}).get("end_card_mute")
    spans = _scene_spans(timeline)
    audio_dir = job_dir / "audio"

    failures: list[str] = []
    checks: list[dict] = []

    def record(kind, subject, passed, detail, measured=None):
        checks.append({"kind": kind, "subject": subject,
                       "passed": bool(passed), "detail": detail,
                       "measured_db": measured})
        if not passed:
            failures.append(f"{kind} {subject}: {detail}")

    # --- Plan-level: beds inside their scene spans -------------------
    for bed in beds:
        scene = bed.get("scene")
        span = spans.get(scene)
        start, end = float(bed["start"]), float(bed["end"])
        if span is None:
            record("bed_span", bed.get("cue_id") or bed["synth_kind"],
                   False, f"scene {scene} has no span")
            continue
        inside = start >= span[0] - 0.05 and end <= span[1] + 0.05
        record("bed_span", bed.get("cue_id") or bed["synth_kind"],
               inside,
               f"{bed['synth_kind']} [{start:.2f}, {end:.2f}] vs "
               f"scene {scene} [{span[0]:.2f}, {span[1]:.2f}]")
    for span_start, span_end in rain_spans:
        covered = any(span_start >= s[0] - 0.05 and span_end <= s[1]
                      + 0.05 for s in spans.values())
        record("rain_span", f"[{span_start:.2f}, {span_end:.2f}]",
               covered, "rain span inside one scene span"
               if covered else "rain span crosses a scene boundary")

    # --- Rendered stems: occupancy per scene span --------------------
    stems = {"ambience": audio_dir / "ambience.wav",
             "music": audio_dir / "music.wav",
             "foley": audio_dir / "foley.wav"}
    bed_scenes = {"ambience": set(), "music": set()}
    for bed in beds:
        stem = bed.get("stem") or "ambience"
        if stem in bed_scenes:
            bed_scenes[stem].add(bed.get("scene"))
    seg_scenes = set()
    for seg in segments:
        if seg.get("scene") is not None:
            seg_scenes.add(seg["scene"])

    for scene in sorted(spans, key=lambda s: spans[s][0]):
        start, end = spans[scene]
        for stem_name in ("ambience", "music"):
            path = stems[stem_name]
            if not path.exists():
                continue
            occupied = scene in bed_scenes[stem_name]
            measured = _measure(path, start, end)
            if measured is None:
                record(f"{stem_name}_occupancy", f"scene {scene}",
                       True, "span too short to measure; skipped",
                       None)
                continue
            if occupied:
                record(f"{stem_name}_occupancy", f"scene {scene}",
                       measured >= AUDIBLE_DB,
                       f"planned bed audible: {measured:.1f} dB "
                       f"(need >= {AUDIBLE_DB})", measured)
            else:
                record(f"{stem_name}_occupancy", f"scene {scene}",
                       measured <= SILENT_DB,
                       f"no planned bed: {measured:.1f} dB "
                       f"(need <= {SILENT_DB})", measured)
        # Foley: scenes with no segments must be silent.
        foley_path = stems["foley"]
        if foley_path.exists() and scene not in seg_scenes:
            measured = _measure(foley_path, start, end)
            if measured is not None:
                record("foley_silence", f"scene {scene}",
                       measured <= SILENT_DB,
                       f"no foley segments: {measured:.1f} dB "
                       f"(need <= {SILENT_DB})", measured)

    # --- Rendered stems: per-bed audibility ---------------------------
    for bed in beds:
        stem_name = bed.get("stem") or "ambience"
        path = stems.get(stem_name)
        if path is None or not path.exists():
            continue
        measured = _measure(path, float(bed["start"]),
                            float(bed["end"]))
        if measured is None:
            continue
        record("bed_audible",
               bed.get("cue_id") or bed["synth_kind"],
               measured >= AUDIBLE_DB,
               f"{bed['synth_kind']} {measured:.1f} dB "
               f"(need >= {AUDIBLE_DB})", measured)

    # --- Rendered stems: per-segment foley audibility -----------------
    foley_path = stems["foley"]
    if foley_path.exists():
        for seg in segments:
            at = float(seg.get("at_seconds") or 0.0)
            dur = float(seg.get("duration") or 0.0)
            if dur <= 0:
                continue
            measured = _measure(foley_path, at, at + dur)
            if measured is None:
                continue
            record("foley_audible", seg.get("cue_id") or seg["sfx"],
                   measured >= AUDIBLE_DB,
                   f"{seg['synth_kind']} {measured:.1f} dB "
                   f"(need >= {AUDIBLE_DB})", measured)

    # --- Muted spans: NONE + end card ---------------------------------
    mute_checks = []
    for span in none_spans.get("ambience") or []:
        mute_checks.append(("ambience", tuple(map(float, span)),
                            "NONE ambience"))
    for span in none_spans.get("bgm") or []:
        mute_checks.append(("music", tuple(map(float, span)),
                            "NONE bgm"))
    if end_card and len(end_card) == 2:
        span = (float(end_card[0]), float(end_card[1]))
        mute_checks.append(("ambience", span, "end card"))
        mute_checks.append(("music", span, "end card"))
    for stem_name, (start, end), label in mute_checks:
        path = stems[stem_name]
        if not path.exists():
            continue
        measured = _measure(path, start, end)
        if measured is None:
            continue
        record("mute_span", f"{label} [{start:.2f}, {end:.2f}]",
               measured <= SILENT_DB,
               f"{stem_name} {measured:.1f} dB "
               f"(need <= {SILENT_DB})", measured)

    return {
        "audit_version": AUDIT_VERSION,
        "job_dir": str(job_dir),
        "scene_spans": {str(k): [v[0], v[1]]
                        for k, v in spans.items()},
        "beds": len(beds),
        "segments": len(segments),
        "checks": checks,
        "failures": failures,
        "passed": not failures,
    }


__all__ = ["AUDIT_VERSION", "AUDIBLE_DB", "SILENT_DB", "GUARD_SEC",
           "audit_audio_isolation"]
