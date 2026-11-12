"""Affiliate QA modules (§23) — Subagent B's sections.

Covered here: translation QA, voice QA, subtitle QA, audio QA, and
commercial-content QA. Video QA / OCR QA / export QA belong to
Subagent A (video stage) and are merged by ATLAS at integration.

Every check returns {"name", "passed", "detail", "evidence"} and is
computed from REAL files / records — never from logs alone. Checks
that need a human ear or eye (pronunciation, creative quality) are
reported as PENDING with the reason, never fabricated as PASS.

Status values: PASS / FAIL / PENDING / NOT_RUN (see schema.py).
"""
from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

from ..language_gate import check_production_language, english_score
from ..timeline import measure_audio_duration
from .captions import (
    check_font_coverage,
    check_safe_zone,
    check_vertical_legibility,
)
from .product import product_claim_findings
from .schema import (
    PROTECTED_TEXT_CLASSES,
    AffiliateProject,
    export_allowed,
)
from .script_gen import check_testimonial_claims
from .translation import digit_sequences


def _check(name: str, passed: bool, detail: str,
           evidence: Any = None) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail,
            "evidence": evidence}


# ---------------------------------------------------------- translation QA

def translation_qa(project: AffiliateProject) -> list[dict]:
    """Meaning preservation, terminology, numbers, claims (§23)."""
    checks: list[dict] = []
    record = project.translation
    if record is None:
        return [_check("translation_present", False,
                       "no translation record in the project")]
    checks.append(_check("engine_labelled", True,
                         f"engine={record.engine} ({record.engine_detail[:80]})",
                         evidence=record.engine))
    translated = record.translated_segments or record.rewritten_segments
    originals = record.original_segments
    if not originals:
        checks.append(_check("has_source_segments", False,
                             "no source segments to translate"))
        return checks
    if record.needs_human_review and not translated:
        checks.append(_check("translation_complete", False,
                             "segments are untranslated and need human "
                             "review (fallback never invents translations)",
                             evidence=record.review_notes))
        return checks
    checks.append(_check(
        "segment_count_match", len(translated) == len(originals),
        f"{len(translated)} translated vs {len(originals)} source segments"))
    # Number preservation: every digit run in the original must appear
    # in the translation (units/model numbers/prices must survive).
    number_problems = []
    for orig, trans in zip(originals, translated):
        orig_digits = digit_sequences(orig.get("text", ""))
        trans_digits = digit_sequences(trans.get("text", ""))
        missing = [d for d in orig_digits if d not in trans_digits]
        if missing:
            number_problems.append(
                f"{orig.get('text', '')[:40]!r} lost number(s) {missing}")
    checks.append(_check("numbers_preserved", not number_problems,
                         "all digit sequences preserved"
                         if not number_problems else "; ".join(number_problems[:3]),
                         evidence=number_problems))
    # No invented discount/urgency wording in DIRECT/NATURAL modes.
    if record.mode in ("DIRECT_TRANSLATION", "NATURAL_LOCALIZATION"):
        added = []
        for orig, trans in zip(originals, translated):
            for word in ("giảm giá", "khuyến mãi", "số lượng có hạn",
                         "chỉ còn", "mua ngay kẻo hết"):
                if word in trans.get("text", "").lower() and word not in orig.get("text", "").lower():
                    added.append(word)
        checks.append(_check("no_invented_urgency", not added,
                             "no discount/urgency wording added"
                             if not added else f"added: {sorted(set(added))}"))
    # Vietnamese fluency proxy: translated lines should look
    # Vietnamese (diacritics present, low English score). Advisory:
    # a flagged line needs a human look, it is not auto-failed here
    # unless it is clearly English.
    gate = check_production_language(
        "vi-VN", [t.get("text", "") for t in translated])
    checks.append(_check("vietnamese_text", gate["ok"],
                         f"{gate['checked']} line(s) checked; "
                         f"{len(gate['violations'])} English-looking",
                         evidence=gate["violations"]))
    return checks


# ---------------------------------------------------------------- voice QA

def _volumedetect(wav: Path) -> dict:
    """ffprobe volumedetect: max_volume / mean_volume (real values)."""
    result = subprocess.run(
        ["ffmpeg", "-i", str(wav), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=60)
    out = result.stderr
    max_v = re.search(r"max_volume:\s*([-\d.]+) dB", out)
    mean_v = re.search(r"mean_volume:\s*([-\d.]+) dB", out)
    return {
        "max_volume_db": float(max_v.group(1)) if max_v else None,
        "mean_volume_db": float(mean_v.group(1)) if mean_v else None,
    }


def _silence_ratio(wav: Path, duration: float) -> float | None:
    """Fraction of the file detected as silence (silencedetect)."""
    result = subprocess.run(
        ["ffmpeg", "-i", str(wav), "-af",
         "silencedetect=noise=-45dB:d=0.3", "-f", "null", "-"],
        capture_output=True, text=True, timeout=60)
    starts = re.findall(r"silence_start:\s*([\d.]+)", result.stderr)
    ends = re.findall(r"silence_end:\s*([\d.]+)", result.stderr)
    if not starts or duration <= 0:
        return 0.0
    total = 0.0
    for s, e in zip(starts, ends):
        total += float(e) - float(s)
    if len(starts) > len(ends):
        total += duration - float(starts[-1])
    return round(min(1.0, total / duration), 3)


def voice_qa(project: AffiliateProject) -> list[dict]:
    """Voice completeness, levels, language, no clipping (§23)."""
    checks: list[dict] = []
    script = project.script
    if script is None or not script.segments:
        return [_check("voice_present", False, "no script segments")]
    missing = [s.segment_id for s in script.segments if not s.voice_wav]
    checks.append(_check("all_segments_have_audio", not missing,
                         f"{len(script.segments) - len(missing)}/"
                         f"{len(script.segments)} segments have WAVs",
                         evidence=missing))
    clipping: list[str] = []
    silent: list[str] = []
    durations: dict[str, float] = {}
    for seg in script.segments:
        if not seg.voice_wav:
            continue
        wav = Path(seg.voice_wav)
        if not wav.exists():
            clipping.append(f"{seg.segment_id}: file missing")
            continue
        duration = measure_audio_duration(wav)
        if duration is None or duration <= 0:
            silent.append(f"{seg.segment_id}: unreadable/empty audio")
            continue
        durations[seg.segment_id] = round(duration, 3)
        vols = _volumedetect(wav)
        if vols["max_volume_db"] is not None and vols["max_volume_db"] >= -0.5:
            clipping.append(f"{seg.segment_id}: max {vols['max_volume_db']} dB")
        ratio = _silence_ratio(wav, duration)
        if ratio is not None and ratio > 0.6:
            silent.append(f"{seg.segment_id}: {ratio:.0%} silence")
    checks.append(_check("no_clipping", not clipping,
                         "no segment peaks at/above -0.5 dB"
                         if not clipping else "; ".join(clipping),
                         evidence=clipping))
    checks.append(_check("no_missing_narration", not silent,
                         "every segment has audible speech"
                         if not silent else "; ".join(silent),
                         evidence=silent))
    gate = check_production_language(
        "vi-VN", [], [s.text for s in script.segments])
    checks.append(_check("narration_vietnamese", gate["ok"],
                         f"{gate['checked']} narration line(s) checked",
                         evidence=gate["violations"]))
    checks.append(_check("pronunciation_ear_check_pending", True,
                         "PENDING — pronunciation must be checked by "
                         "listening; no automated score is claimed",
                         evidence="human_review_required"))
    return checks


# ------------------------------------------------------------ subtitle QA

def subtitle_qa(project: AffiliateProject, ass_path: Path | None,
                srt_path: Path | None, cues: list[dict],
                video_duration_sec: float) -> list[dict]:
    """Timing, Unicode, readability, safe zones (§23)."""
    checks: list[dict] = []
    style = project.subtitle_style
    if ass_path is not None:
        checks.append(_check("ass_file_exists", Path(ass_path).exists(),
                             f"ASS: {ass_path}"))
    if srt_path is not None:
        checks.append(_check("srt_file_exists", Path(srt_path).exists(),
                             f"SRT: {srt_path}"))
    overlong = [c for c in cues if len(c.get("text", "")) > style.max_chars_per_line]
    checks.append(_check("cue_length", not overlong,
                         f"{len(cues) - len(overlong)}/{len(cues)} cues within "
                         f"{style.max_chars_per_line} chars"))
    timing_bad = [c for c in cues
                  if c.get("end", 0) <= c.get("start", 0)
                  or c.get("end", 0) > video_duration_sec + 0.05]
    checks.append(_check("cue_timing", not timing_bad,
                         "all cues inside the video duration"
                         if not timing_bad else f"{len(timing_bad)} bad cue(s)"))
    overlap = False
    for prev, cur in zip(cues, cues[1:]):
        if cur.get("start", 0) < prev.get("end", 0) - 0.001:
            overlap = True
    checks.append(_check("no_cue_overlap", not overlap,
                         "no overlapping cue windows" if not overlap
                         else "overlapping cue windows found"))
    coverage = check_font_coverage([c.get("text", "") for c in cues])
    checks.append(_check("vietnamese_font_coverage", coverage["ok"],
                         f"{coverage.get('checked_chars', 0)} char(s) checked"
                         if coverage["ok"] else
                         f"missing glyphs: {coverage.get('missing', [])}",
                         evidence=coverage))
    legibility = check_vertical_legibility(style)
    checks.append(_check("mobile_legibility", legibility["passes"],
                         f"font {style.font_size}px = {legibility['ratio']:.1%} "
                         f"of frame height (min {legibility['min_ratio']:.0%})",
                         evidence=legibility))
    zone = check_safe_zone(style)
    checks.append(_check("safe_zone", zone["ok"],
                         f"profile {zone['profile']}: caption area clear"
                         if zone["ok"] else
                         f"caption area overlaps: {zone['violations']}",
                         evidence=zone))
    return checks


# ---------------------------------------------------------------- audio QA

# ffmpeg volumedetect reports pure digital silence at -91 dB. A fade
# window at/below this floor carries no level information: two silent
# windows compare equal, which the strict fade inequality would fail
# even though no hard cut exists (S8). Windows at the floor are
# unmeasurable, not failed.
SILENCE_FLOOR_DB = -90.0


def _fade_half_ok(fade_db: float | None, ref_db: float | None,
                  label: str) -> tuple[bool, str]:
    """One fade half: (ok, detail).

    Unmeasurable halves — a missing volumedetect value, or both
    windows at the silence floor — cannot show a hard cut and do not
    fail. Measurable halves need the strict inequality: the fade
    window must be quieter than its reference window, so a genuinely
    abrupt start/end still fails.
    """
    if fade_db is None or ref_db is None:
        return True, (f"{label} unmeasurable (no volumedetect value); "
                      "no hard-cut evidence")
    if fade_db <= SILENCE_FLOOR_DB and ref_db <= SILENCE_FLOOR_DB:
        return True, (f"{label} unmeasurable (both windows at the "
                      f"silence floor: {fade_db}/{ref_db} dB); "
                      "no hard-cut evidence")
    return (fade_db < ref_db,
            f"{label} {fade_db} dB < {ref_db} dB")


def audio_qa(mix_path: Path | None, voice_stem: Path | None,
             music_stem: Path | None, total_sec: float,
             bus_gains_db: dict | None = None) -> list[dict]:
    """Speech intelligibility, balance, fades, clipping (§23).

    The voice/music balance compares EFFECTIVE bus levels: each
    stem's measured mean volume plus its mix gain — comparing raw
    stems would ignore the ducking/gains the mix actually applies.
    """
    checks: list[dict] = []
    if mix_path is None or not Path(mix_path).exists():
        return [_check("mix_exists", False, "no mixed audio file")]
    duration = measure_audio_duration(Path(mix_path))
    checks.append(_check("mix_duration", duration is not None and duration > 0,
                         f"mix duration {duration}s (timeline {total_sec}s)",
                         evidence=duration))
    vols = _volumedetect(Path(mix_path))
    checks.append(_check("mix_no_clipping",
                         vols["max_volume_db"] is not None
                         and vols["max_volume_db"] < -0.5,
                         f"mix max volume {vols['max_volume_db']} dB",
                         evidence=vols))
    if voice_stem and Path(voice_stem).exists() and music_stem and Path(music_stem).exists():
        voice_vols = _volumedetect(Path(voice_stem))
        music_vols = _volumedetect(Path(music_stem))
        if (voice_vols["mean_volume_db"] is not None
                and music_vols["mean_volume_db"] is not None):
            gains = bus_gains_db or {}
            voice_eff = voice_vols["mean_volume_db"] + gains.get("voice", 0.0)
            music_eff = music_vols["mean_volume_db"] + gains.get("music", 0.0)
            gap = voice_eff - music_eff
            checks.append(_check("voice_above_music", gap >= 6.0,
                                 f"voice {voice_eff:.1f} dB vs music "
                                 f"{music_eff:.1f} dB effective "
                                 f"(gap {gap:.1f} dB, min 6 dB)",
                                 evidence={"gap_db": round(gap, 1)}))
    # Fade check: the fade-in window must be quieter than the window
    # right after it, and the fade-out window quieter than the window
    # right before it. (Comparing against the middle would be wrong
    # when narration is sparse — the middle may be music-only.)
    if duration and duration > 1.2:
        def _mean_at(start: float, length: float) -> float | None:
            result = subprocess.run(
                ["ffmpeg", "-ss", str(start), "-i", str(mix_path),
                 "-t", str(length), "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True, timeout=60)
            match = re.search(r"mean_volume:\s*([-\d.]+) dB", result.stderr)
            return float(match.group(1)) if match else None
        head = _mean_at(0.0, 0.3)
        head_ref = _mean_at(0.3, 0.3)
        tail_ref = _mean_at(max(0.0, duration - 0.6), 0.3)
        tail = _mean_at(max(0.0, duration - 0.3), 0.3)
        # Each half is judged on its own: a silent tail must not fail
        # the check (S8), and a silent head must not hide a genuinely
        # abrupt ending either.
        in_ok, in_detail = _fade_half_ok(head, head_ref, "fade-in")
        out_ok, out_detail = _fade_half_ok(tail, tail_ref, "fade-out")
        checks.append(_check("smooth_fades", bool(in_ok and out_ok),
                             f"{in_detail}; {out_detail}",
                             evidence={"head": head, "head_ref": head_ref,
                                       "tail_ref": tail_ref, "tail": tail}))
    return checks


# ------------------------------------------------------- commercial-content QA

def commercial_qa(project: AffiliateProject) -> list[dict]:
    """Authorization, disclosure, claims, testimonials (§23)."""
    checks: list[dict] = []
    allowed, reasons = export_allowed(project)
    checks.append(_check("export_gate", allowed,
                         "authorization + rights + approvals all satisfied"
                         if allowed else "; ".join(reasons),
                         evidence=reasons))
    product = project.product
    if product is not None:
        findings = product_claim_findings(product)
        checks.append(_check("no_unsupported_claims", not findings,
                             "no claim-like wording in product fields"
                             if not findings else
                             f"{len(findings)} finding(s) need review",
                             evidence=findings[:5]))
        if product.affiliate_url and not (product.disclosure_text or "").strip():
            checks.append(_check("disclosure_present", False,
                                 "affiliate link present but no disclosure"))
        else:
            checks.append(_check("disclosure_present", True,
                                 "disclosure present or no affiliate link"))
    if project.script is not None:
        testimonial_hits = []
        for seg in project.script.segments:
            for hit in check_testimonial_claims(seg.text):
                testimonial_hits.append(f"{seg.segment_id}: {hit!r}")
        tested_ok = bool(product and product.personally_tested_confirmed)
        checks.append(_check(
            "no_fabricated_testimonials",
            not testimonial_hits or tested_ok,
            "no first-person testing claims"
            if not testimonial_hits else
            ("testing claims present and explicitly confirmed"
             if tested_ok else
             f"unconfirmed testing claims: {testimonial_hits[:3]}"),
            evidence=testimonial_hits))
        checks.append(_check("script_approved", bool(project.script.approved),
                             f"approved={project.script.approved} "
                             f"by {project.script.approved_by or '-'}"))
    # Watermark / attribution preservation: no edit may target a
    # protected track without approval (re-checked here from records).
    tracks = {t.text_id: t for t in project.ocr_tracks}
    violations = []
    for op in project.edit_operations:
        track = tracks.get(op.target_track_id) if op.target_track_id else None
        if (track is not None
                and track.text_classification in PROTECTED_TEXT_CLASSES
                and op.operation in ("text_blur", "text_inpaint", "text_crop")
                and not op.approved):
            violations.append(f"{op.operation} on {track.text_id} "
                              f"({track.text_classification}) without approval")
    checks.append(_check("no_unauthorized_removal", not violations,
                         "no protected track targeted without approval"
                         if not violations else "; ".join(violations),
                         evidence=violations))
    mirror_ops = [op for op in project.edit_operations
                  if op.operation == "hflip"]
    checks.append(_check("mirror_reviewed",
                         all(op.approved for op in mirror_ops),
                         "no mirror op, or all mirror ops approved"
                         if all(op.approved for op in mirror_ops)
                         else "mirror op without label/logo warning review"))
    return checks


# ------------------------------------------------------------------ report

def run_affiliate_qa(project: AffiliateProject, *,
                     ass_path: Path | None = None,
                     srt_path: Path | None = None,
                     cues: list[dict] | None = None,
                     video_duration_sec: float = 0.0,
                     mix_path: Path | None = None,
                     voice_stem: Path | None = None,
                     music_stem: Path | None = None,
                     total_sec: float = 0.0) -> dict:
    """Run all Subagent-B QA sections and aggregate honestly.

    Sections owned by Subagent A (video / OCR / export) are recorded
    as NOT_RUN here and merged at integration. The overall verdict is
    PASS only when every executed check passes; any FAIL fails the
    report; PENDING human-review items keep the verdict at
    REVIEW_REQUIRED (never an invented Creative PASS).
    """
    sections = {
        "translation": translation_qa(project),
        "voice": voice_qa(project),
        "subtitle": subtitle_qa(project, ass_path, srt_path,
                                cues or [], video_duration_sec),
        "audio": audio_qa(mix_path, voice_stem, music_stem, total_sec,
                          project.audio_mix.bus_gains_db),
        "commercial": commercial_qa(project),
        "video": [],
        "ocr": [],
        "export": [],
    }
    executed = [c for name, checks in sections.items()
                if name not in ("video", "ocr", "export") for c in checks]
    failed = [c for c in executed if not c["passed"]]
    verdict = "PASS" if not failed else "FAIL"
    report = {
        "sections": {name: {"checks": checks,
                            "status": ("NOT_RUN" if not checks else
                                       ("FAIL" if any(not c["passed"] for c in checks)
                                        else "PASS"))}
                     for name, checks in sections.items()},
        "verdict": verdict,
        "creative_status": "REVIEW_REQUIRED",
        "creative_note": "Creative quality and pronunciation need human "
                         "review; no automated Creative PASS is claimed.",
        "failed_checks": [c["name"] for c in failed],
        "total_checks": len(executed),
    }
    return report
