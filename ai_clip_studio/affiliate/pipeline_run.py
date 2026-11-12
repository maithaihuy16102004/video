"""Vertical-slice orchestration for AI Affiliate Studio (Stage 1).

Thin glue ONLY: this module calls the Phase 1 modules from Subagent A
(``affiliate/video/*``: probe/analysis/OCR/text-replace/export/QA) and
Subagent B (``affiliate/*``: schema/ASR/translation/script/voice/
timeline/captions/marketing/QA) in pipeline order and records the real
inputs/outputs of each step. It deliberately contains NO duplicated
validation, mixing, QA, or export logic — every rule lives in the
module that owns it. Anything this glue has to work around (a missing
seam, a cross-venv hop, a second ffmpeg pass) is recorded in the job
manifest so the integration quality pass can address it properly.

Pipeline (direct module calls, no server):

    ingest -> analysis -> OCR -> ASR -> translation (labelled fallback
    probed, then human-review record) -> script -> voice -> timeline/
    mix -> blur+subtitles -> export -> QA -> marketing package

Authorization: the synthetic fixture is content generated locally by
``generate_fixture.py``. The engine vocabulary (``video/models.py``)
carries the provenance label ``SYNTHETIC_FIXTURE`` and maps it to the
schema value ``USER_OWNED`` (``to_schema_authorization``); the schema
enum itself has no ``SYNTHETIC_FIXTURE`` value. Both labels are
recorded; the gate is enforced by the A/B modules at every step.

Environment hops (no package installs, no hunting for keys):
  * OCR runs in ``~/workspace/.venvs/affiliate_cv`` (RapidOCR; PaddleOCR
    is not installed) via a generated worker script + JSON exchange.
  * ASR runs through ``asr.transcribe_chinese``, which already shells
    out to the whisper venv itself.
  * No Gemini key exists in this environment: translation/script stages
    run the labelled fallback, and the Vietnamese lines in this slice
    come from an explicit human-review record (engine="human_review"),
    never presented as Gemini output.

Run:
    PYTHONPATH=~/workspace/video-16x9-v2 python3 -m \\
        ai_clip_studio.affiliate.pipeline_run \\
        --job-dir ~/workspace/acceptance_loop/affiliate_integration/slice_job \\
        --fixture ~/workspace/acceptance_loop/affiliate_fixtures/fixture.mp4 \\
        --demo-mp3 ~/workspace/acceptance_loop/affiliate_fixtures/chinese_demo.mp3
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# --- Subagent B modules (language / audio / schema) -------------------
from .asr import transcribe_chinese, write_transcript_files
from .audio_timeline import (
    build_affiliate_timeline,
    concatenate_voice,
    plan_mix,
    render_mix,
)
from .captions import (
    build_ass,
    build_cues,
    build_srt,
    burn_filter_args,
    check_font_coverage,
    check_safe_zone,
    check_vertical_legibility,
)
from .marketing import build_marketing_package, check_marketing_promises
from .qa import run_affiliate_qa
from .schema import (
    AffiliateProject,
    AnalysisScene,
    AudioMix,
    EditOperation,
    ExportProfile,
    OcrTrack,
    ProductInfo,
    SourceAuthorization,
    SubtitleStyle,
    TranslationRecord,
    VideoAnalysis,
    export_allowed,
    project_snapshot_hash,
    validate_project,
)
from .script_gen import approve_script, script_from_translation
from .source_media import sha256_file, store_source_copy
from .translation import translate_segments
from .voice import preset_config, synthesize_script

# --- Subagent A modules (CV / video) ----------------------------------
from ..timeline import measure_audio_duration
from .video.analysis import analyze_source
from .video.export import export_profile_for, export_video
from .video.models import (
    BBox,
    ReplacementMode,
    ReplacementSpec,
    TextClassification,
    TextRegion,
    TrackSample,
    export_gate_check,
    to_schema_authorization,
)
from .video.ocr import approve_removal, review_queue
from .video.probe import probe_source
from .video.qa import qa_export
from .video.text_replace import replacement_subtitle_slots

# Provenance / gate values for this synthetic-fixture slice.
ENGINE_AUTHORIZATION = "SYNTHETIC_FIXTURE"
RIGHTS_CONFIRMED = True
RIGHTS_NOTE = (
    "Synthetic fixture generated locally by generate_fixture.py; "
    "no real product, brand, or downloaded video. Engine label "
    "SYNTHETIC_FIXTURE maps to schema USER_OWNED (self-generated)."
)
APPROVER = "slice human reviewer (vertical-slice job)"

# Human-review translations for this slice, faithful to the fixture's
# known on-screen lines. Facts unchanged; no humorous embellishment
# added. The TranslationRecord carries style="humorous_viral_review"
# (the Douyin target voice) with a review note stating the wording is
# the faithful translation, not embellished copy.
HUMAN_TRANSLATIONS = {
    "这款收纳盒非常实用": "Chiếc hộp đựng đồ này rất tiện dụng",
    "限时优惠": "Ưu đãi có thời hạn",
    "质量很好，值得购买": "Chất lượng rất tốt, đáng mua",
}

# Product placeholder: NO product facts were supplied. The schema
# requires a non-empty product_name, so the placeholder states plainly
# that the information is missing instead of inventing a product.
PRODUCT_NAME_PLACEHOLDER = "[THÔNG TIN SẢN PHẨM CHƯA CUNG CẤP]"

CV_VENV_PYTHON = (
    Path.home() / "workspace" / ".venvs" / "affiliate_cv" / "bin" / "python"
)
ASR_MODEL = "tiny"  # B's proven model for the Chinese demo fixture
# OCR sampling interval (S9). Tracking links consecutive detections
# only when their boxes overlap (IoU >= 0.3), so the interval must be
# short enough that fast-moving text cannot jump clear of its own box
# between samples: measured on the fixture promo (~850 px/s, 254 px
# wide), 1 fps fragments it into single-sample tracks and 0.125 s
# (8 fps) links it into one track (consecutive IoU 0.38-0.64). Denser
# sampling costs OCR time (~2.7 s/frame here); 0.125 s is the
# coverage/speed trade-off for this slice, not a universal constant.
OCR_SAMPLE_INTERVAL_SEC = 0.125
VOICE_PRESET = "female_review"  # single narrator voice; no speakers invented
EXPORT_PROFILE_NAME = "TIKTOK_REELS"

# Worker executed inside the CV venv: RapidOCR + tracking only. Kept as
# data (written to the job dir as an artifact) so this module stays the
# single orchestration file and no second package module is created.
_OCR_WORKER = '''
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "workspace" / "video-16x9-v2"))
from ai_clip_studio.affiliate.video.ocr import (
    get_ocr_engine, run_ocr_on_frames, track_detections, review_queue)
video, out_path, width, height = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
interval, duration = float(sys.argv[5]), float(sys.argv[6])
times = [round(i * interval, 4) for i in range(int(duration / interval))]
engine, status = get_ocr_engine()
if engine is None:
    print(json.dumps({"error": "no OCR engine", "status": status}, ensure_ascii=False))
    raise SystemExit(1)
work = out_path.parent / "ocr_work"
detections = run_ocr_on_frames(video, times, engine, work_dir=work)
result = track_detections(detections, (width, height),
                          sample_interval_sec=interval)
payload = {
    "engine_status": status,
    "sample_times": times,
    "detection_counts": {str(t): len(detections.get(t, [])) for t in times},
    "regions": [r.to_dict() for r in result.regions],
    "tracks": [r.to_ocr_track_dict() for r in result.regions],
    "dropped_flicker": result.dropped_flicker,
    "review_queue": review_queue(result.regions),
}
out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"tracks": len(result.regions),
                  "dropped_flicker": len(result.dropped_flicker)}))
'''


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _norm(text: str) -> str:
    return "".join((text or "").split())


def run_ocr_in_venv(
    video_path: Path, frame_size: tuple[int, int], work_dir: Path
) -> dict:
    """Run RapidOCR + tracking in the CV venv; return the JSON payload.

    Samples at OCR_SAMPLE_INTERVAL_SEC (S9): dense enough that
    fast-moving text links into one track instead of fragments.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    worker = work_dir / "ocr_worker.py"
    worker.write_text(_OCR_WORKER, encoding="utf-8")
    out_path = work_dir / "ocr_result.json"
    duration = probe_source(video_path).duration_sec
    result = subprocess.run(
        [str(CV_VENV_PYTHON), str(worker), str(video_path), str(out_path),
         str(frame_size[0]), str(frame_size[1]),
         str(OCR_SAMPLE_INTERVAL_SEC), str(duration)],
        capture_output=True, text=True, timeout=1200,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"OCR worker failed: {result.stderr.strip()[-500:]}")
    return json.loads(out_path.read_text(encoding="utf-8"))


def regions_from_ocr_payload(payload: dict) -> list[TextRegion]:
    """Rebuild TextRegion objects from the venv worker's JSON.

    Track samples survive the round-trip (S9): the tracked-blur
    builder interpolates them, so dropping them here would silently
    downgrade moving tracks to static boxes. Payloads written before
    samples existed restore to an empty list (static fallback).
    """
    regions: list[TextRegion] = []
    for raw in payload["regions"]:
        box = raw["bbox"]
        regions.append(TextRegion(
            text_id=raw["text_id"], track_id=raw["track_id"],
            original_text=raw["original_text"],
            start_time=float(raw["start_time"]),
            end_time=float(raw["end_time"]),
            bbox=BBox(float(box["x"]), float(box["y"]),
                      float(box["w"]), float(box["h"])),
            frame_size=tuple(raw["frame_size"]),  # type: ignore[arg-type]
            polygon=[(float(px), float(py)) for px, py in raw["polygon"]],
            ocr_confidence=float(raw["ocr_confidence"]),
            classification=TextClassification(raw["classification"]),
            classification_reason=raw["classification_reason"],
            source=raw["source"],
            detection_method=raw["detection_method"],
            translated_text=raw.get("translated_text", ""),
            needs_review=bool(raw["needs_review"]),
            review_reasons=list(raw.get("review_reasons", [])),
            track_samples=[TrackSample.from_dict(s)
                           for s in raw.get("track_samples", [])],
        ))
    return regions


def build_human_translation(
    regions: list[TextRegion],
) -> tuple[TranslationRecord, dict]:
    """Human-review TranslationRecord from the OCR blur tracks.

    Groups SUBTITLE / PROMOTIONAL_OVERLAY tracks by normalized text,
    merges fragment windows (the sliding promo splits into fragments),
    and applies HUMAN_TRANSLATIONS. Any blur track whose text has no
    supplied translation fails loudly instead of inventing one.
    """
    blur_classes = {TextClassification.SUBTITLE,
                    TextClassification.PROMOTIONAL_OVERLAY}
    grouped: dict[str, dict] = {}
    for region in regions:
        if region.classification not in blur_classes:
            continue
        key = _norm(region.original_text)
        entry = grouped.setdefault(key, {
            "original_text": region.original_text,
            "start": region.start_time, "end": region.end_time,
            "track_ids": [],
        })
        entry["start"] = min(entry["start"], region.start_time)
        entry["end"] = max(entry["end"], region.end_time)
        entry["track_ids"].append(region.text_id)
    originals: list[dict] = []
    translated: list[dict] = []
    for key in sorted(grouped, key=lambda k: grouped[k]["start"]):
        entry = grouped[key]
        vietnamese = HUMAN_TRANSLATIONS.get(entry["original_text"])
        if vietnamese is None:
            vietnamese = next(
                (v for k, v in HUMAN_TRANSLATIONS.items()
                 if _norm(k) == key), None)
        if vietnamese is None:
            raise ValueError(
                f"no human translation supplied for OCR text "
                f"{entry['original_text']!r} (tracks {entry['track_ids']}); "
                "refusing to invent one")
        base = {"start": round(entry["start"], 3),
                "end": round(entry["end"], 3), "speaker_id": ""}
        originals.append({**base, "text": entry["original_text"]})
        translated.append({**base, "text": vietnamese})
    record = TranslationRecord(
        mode="NATURAL_LOCALIZATION",
        engine="human_review",
        engine_detail=(
            "Human reviewer (vertical-slice job) translated the fixture's "
            "known on-screen Chinese lines faithfully; NOT Gemini output "
            "(no Gemini key in this environment)."),
        style="humorous_viral_review",
        original_segments=originals,
        translated_segments=translated,
        needs_human_review=False,
        review_notes=[
            "Wording is the faithful human translation supplied for this "
            "slice; no humorous embellishment was added and no facts "
            "changed. Style records the Douyin target voice for the "
            "Gemini stage.",
            "Product-label track (净含量：500ml) is preserved, not dubbed; "
            "no display translation was supplied for it.",
        ],
    )
    audit = {"grouped_tracks": grouped,
             "lines": len(originals)}
    return record, audit


def mux_final(
    pass1_path: Path, mix_wav: Path, ass_path: Path,
    out_path: Path, total_sec: float,
) -> Path:
    """Second ffmpeg pass: burn ASS subtitles + replace audio with mix.

    WORKAROUND (missing seam): export_video() accepts neither an ASS
    path nor an external mix WAV, so the subtitle burn and the mix mux
    cannot join its single-pass graph. This pass re-encodes at the same
    profile settings (CRF 18, AAC 192k/48k, faststart, bt709). The
    filter text itself is built by captions.burn_filter_args.
    """
    subtitles_filter = burn_filter_args(str(ass_path))[1]
    filter_complex = f"[0:v]{subtitles_filter}[v]"
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-i", str(pass1_path), "-i", str(mix_wav),
           "-filter_complex", filter_complex,
           "-map", "[v]", "-map", "1:a",
           "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
           "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-colorspace", "bt709", "-color_primaries", "bt709",
           "-color_trc", "bt709",
           "-movflags", "+faststart",
           "-t", str(total_sec), str(out_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if result.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"subtitle/mix mux failed: {result.stderr[:400]}")
    return out_path


def run_slice(
    job_dir: Path,
    fixture_path: Path,
    demo_mp3: Path,
    manifest_path: Path,
) -> dict:
    """Run the full vertical slice; return the job manifest dict."""
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"steps": {}, "artifacts": {}, "limitations": []}
    steps = manifest["steps"]

    # ---- Step 1: ingest (immutable copy + probe + gate) -------------
    gate_ok, gate_reasons = export_gate_check(
        ENGINE_AUTHORIZATION, RIGHTS_CONFIRMED)
    if not gate_ok:
        raise RuntimeError(f"authorization gate refused: {gate_reasons}")
    source_video = store_source_copy(fixture_path, job_dir)
    stored = Path(source_video.stored_path)
    probe = probe_source(stored)
    assert probe.sha256 == source_video.sha256, "probe/store checksum mismatch"
    authorization = SourceAuthorization(
        authorization_type=to_schema_authorization(ENGINE_AUTHORIZATION),
        commercial_rights_confirmed=RIGHTS_CONFIRMED,
        rights_note=RIGHTS_NOTE,
        confirmed_by=APPROVER,
    )
    product = ProductInfo(product_name=PRODUCT_NAME_PLACEHOLDER)
    project = AffiliateProject(
        project_id="slice_synthetic_fixture_v1",
        project_name="Vertical slice — synthetic fixture",
        source_video=source_video,
        authorization=authorization,
        product=product,
    )
    intake = {
        "engine_authorization": ENGINE_AUTHORIZATION,
        "schema_authorization": authorization.authorization_type,
        "gate": {"allowed": gate_ok, "reasons": gate_reasons},
        "source": probe.to_dict(),
        "stored_path": str(stored),
        "fixture_manifest_authorization": json.loads(
            manifest_path.read_text(encoding="utf-8"))["authorization"],
    }
    _write_json(job_dir / "intake_manifest.json", intake)
    steps["1_ingest"] = intake
    manifest["artifacts"]["source_copy"] = str(stored)

    # ---- Step 2: analysis vs fixture ground truth -------------------
    analysis_dir = job_dir / "analysis"
    report = analyze_source(stored, work_dir=analysis_dir / "work")
    ground = json.loads(manifest_path.read_text(encoding="utf-8"))
    detected_bounds = [round(s.start_time, 3) for s in report.scenes]
    detected_bounds.append(round(report.scenes[-1].end_time, 3))
    expected_bounds = [0.0] + [s["end_time"] for s in ground["scenes"]]
    silences = [(round(a.start_time, 2), round(a.end_time, 2))
                for a in report.audio_segments if a.kind == "silence"]
    motion = {s.scene_id: {"label": s.motion_label,
                           "intensity": s.motion_intensity}
              for s in report.scenes}
    analysis_payload = {
        "report": report.to_dict(),
        "ground_truth_comparison": {
            "scene_bounds_detected": detected_bounds,
            "scene_bounds_expected": expected_bounds,
            "bounds_match_within_0.2s": all(
                abs(a - b) <= 0.2
                for a, b in zip(detected_bounds, expected_bounds))
            and len(detected_bounds) == len(expected_bounds),
            "silence_detected": silences,
            "silence_expected": [(3.0, 6.0)],
            "motion_by_scene": motion,
            "moving_scene_gt_static": (
                motion.get("scene-02", {}).get("intensity", 0) >
                motion.get("scene-01", {}).get("intensity", 0)
                and motion.get("scene-02", {}).get("intensity", 0) >
                motion.get("scene-03", {}).get("intensity", 0)),
            "watermark_candidates": [w.to_dict()
                                     for w in report.watermark_candidates],
            "faces_status": report.faces_status,
            "faces_status_detail": report.faces_status_detail,
            "hands_status": report.hands_status,
            "engine": report.engine,
        },
    }
    _write_json(analysis_dir / "analysis_report.json", analysis_payload)
    steps["2_analysis"] = analysis_payload["ground_truth_comparison"]

    # ---- Step 3: OCR (RapidOCR in the CV venv) ----------------------
    ocr_dir = job_dir / "ocr"
    ocr_payload = run_ocr_in_venv(
        stored, (probe.width, probe.height), ocr_dir)
    regions = regions_from_ocr_payload(ocr_payload)
    steps["3_ocr"] = {
        "engine_status": ocr_payload["engine_status"],
        "detection_counts": ocr_payload["detection_counts"],
        "tracks": ocr_payload["tracks"],
        "dropped_flicker": ocr_payload["dropped_flicker"],
        "review_queue": ocr_payload["review_queue"],
    }
    manifest["artifacts"]["ocr_tracks"] = str(ocr_dir / "ocr_result.json")

    # ---- Step 4: ASR (fixture tone/silence + Chinese demo) ----------
    asr_dir = job_dir / "asr"
    fixture_transcript = transcribe_chinese(stored, model=ASR_MODEL)
    demo_transcript = transcribe_chinese(demo_mp3, model=ASR_MODEL)
    fixture_files = write_transcript_files(
        fixture_transcript, asr_dir / "fixture")
    demo_files = write_transcript_files(demo_transcript, asr_dir / "demo")
    steps["4_asr"] = {
        "model": ASR_MODEL,
        "fixture": fixture_transcript.to_dict(),
        "fixture_files": {k: str(v) for k, v in fixture_files.items()},
        "demo": demo_transcript.to_dict(),
        "demo_files": {k: str(v) for k, v in demo_files.items()},
    }

    # ---- Step 5: translation ----------------------------------------
    # 5a. Probe the labelled fallback honestly (no Gemini key).
    fallback_probe_segments = [
        {"start": r.start_time, "end": r.end_time, "text": r.original_text}
        for r in regions
        if r.classification in (TextClassification.SUBTITLE,
                                TextClassification.PROMOTIONAL_OVERLAY)]
    fallback_record = translate_segments(
        fallback_probe_segments, product,
        mode="NATURAL_LOCALIZATION", style="humorous_viral_review")
    # 5b. Human-review record (the translations actually used).
    translation_record, translation_audit = build_human_translation(regions)
    project.translation = translation_record
    project.ocr_tracks = []
    human_map = {_norm(k): v for k, v in HUMAN_TRANSLATIONS.items()}
    for region in regions:
        track = region.to_ocr_track_dict()
        if region.classification in (TextClassification.SUBTITLE,
                                     TextClassification.PROMOTIONAL_OVERLAY):
            track["translated_text"] = human_map.get(
                _norm(region.original_text), "")
        project.ocr_tracks.append(OcrTrack(**track))
    translation_payload = {
        "fallback_probe": {
            "engine": fallback_record.engine,
            "engine_detail": fallback_record.engine_detail,
            "translated_segments": fallback_record.translated_segments,
            "needs_human_review": fallback_record.needs_human_review,
            "review_notes": fallback_record.review_notes,
        },
        "human_review_record": {
            "engine": translation_record.engine,
            "engine_detail": translation_record.engine_detail,
            "mode": translation_record.mode,
            "style": translation_record.style,
            "original_segments": translation_record.original_segments,
            "translated_segments": translation_record.translated_segments,
            "needs_human_review": translation_record.needs_human_review,
            "review_notes": translation_record.review_notes,
        },
        "audit": translation_audit,
    }
    _write_json(job_dir / "translation" / "translation_records.json",
                translation_payload)
    steps["5_translation"] = translation_payload

    # ---- Step 6: script (dubbed_translation + approval) -------------
    script = script_from_translation(translation_record)
    approve_script(script, approved_by=APPROVER,
                   note="Human-reviewed faithful dub script for the "
                        "synthetic fixture; approved for TTS in this slice.")
    project.script = script
    snapshot_hash_at_approval = project_snapshot_hash(project)
    script_payload = {
        "variant": script.variant,
        "target_seconds": script.target_seconds,
        "engine": script.engine,
        "engine_detail": script.engine_detail,
        "segments": [{"segment_id": s.segment_id, "section": s.section,
                      "text": s.text, "speaker_id": s.speaker_id,
                      "start_time": s.start_time, "end_time": s.end_time,
                      "estimated_sec": s.estimated_sec}
                     for s in script.segments],
        "approved": script.approved,
        "approved_by": script.approved_by,
        "approved_at": script.approved_at,
        "approval_note": script.approval_note,
        "snapshot_hash_at_approval": snapshot_hash_at_approval,
    }
    _write_json(job_dir / "translation" / "approved_script.json",
                script_payload)
    steps["6_script"] = script_payload

    # ---- Step 7: voice (single narrator, real TTS) ------------------
    voice_config = preset_config(VOICE_PRESET)
    project.voice = voice_config
    audio_dir = job_dir / "audio"
    wavs = synthesize_script(script, audio_dir, config=voice_config)
    steps["7_voice"] = {
        "preset": VOICE_PRESET,
        "voice_id": voice_config.voice_id,
        "segments": [{"segment_id": s.segment_id, "text": s.text,
                      "voice_wav": s.voice_wav,
                      "measured_sec": s.measured_sec}
                     for s in script.segments],
        "wav_paths": [str(w) for w in wavs],
    }

    # ---- Step 8: timeline + mix --------------------------------------
    project.audio_mix = AudioMix(mode="REPLACE_ALL")
    timeline = build_affiliate_timeline(
        script, footage_sec=probe.duration_sec,
        pause_after_sec=voice_config.pause_after_sec,
        audio_tail_sec=0.0,  # mix length == footage length for a clean mux
    )
    if timeline.conflict is not None and not timeline.conflict.get("resolved"):
        raise RuntimeError(
            f"timeline conflict unresolved, refusing to render: "
            f"{timeline.conflict}")
    voice_stem = concatenate_voice(timeline, audio_dir / "voice_stem.wav")
    mix_plan = plan_mix(project.audio_mix, voice_wav=str(voice_stem),
                        total_sec=timeline.total_sec)
    mix_wav = render_mix(mix_plan, audio_dir / "mix.wav")
    mix_duration = measure_audio_duration(mix_wav)
    voice_stem_duration = measure_audio_duration(voice_stem)
    timeline_payload = {
        "timeline": timeline.to_dict(),
        "mix_plan": mix_plan.to_dict(),
        "voice_stem": str(voice_stem),
        "voice_stem_duration_sec": voice_stem_duration,
        "mix_wav": str(mix_wav),
        "mix_duration_sec": mix_duration,
        "mix_matches_timeline": (
            mix_duration is not None
            and abs(mix_duration - timeline.total_sec) <= 0.05),
        "music": None,  # no authorized music in this slice; voice-only mix
    }
    _write_json(audio_dir / "timeline_and_mix.json", timeline_payload)
    steps["8_audio_timeline"] = timeline_payload
    manifest["artifacts"]["narration_wav"] = str(voice_stem)
    manifest["artifacts"]["mix_wav"] = str(mix_wav)

    # ---- Step 9: blur + subtitle slots + captions -------------------
    specs: list[ReplacementSpec] = []
    preserved: list[str] = []
    for region in regions:
        if region.classification in (TextClassification.SUBTITLE,
                                     TextClassification.PROMOTIONAL_OVERLAY):
            approve_removal(region, ENGINE_AUTHORIZATION,
                            RIGHTS_CONFIRMED, APPROVER)
            specs.append(ReplacementSpec(
                region=region, mode=ReplacementMode.LOCAL_BLUR,
                approved=True,
                approval_note="blur-and-subtitle: human-reviewed OCR track; "
                              "Vietnamese subtitle overlays separately"))
        else:
            preserved.append(
                f"{region.text_id} ({region.classification.value})")
    slots, skipped = replacement_subtitle_slots(
        specs, ENGINE_AUTHORIZATION, RIGHTS_CONFIRMED)
    project.edit_operations = [
        EditOperation(**spec.to_edit_operation_dict()) for spec in specs]
    style = SubtitleStyle()
    project.subtitle_style = style
    cue_segments = [{"text": seg.text, "start": seg.start, "end": seg.end}
                    for seg in timeline.segments]
    cues = build_cues(cue_segments, style)
    captions_dir = job_dir / "captions"
    captions_dir.mkdir(parents=True, exist_ok=True)
    ass_text = build_ass(cues, style)
    srt_text = build_srt(cues)
    ass_path = captions_dir / "captions.ass"
    srt_path = captions_dir / "captions.srt"
    ass_path.write_text(ass_text, encoding="utf-8")
    srt_path.write_text(srt_text, encoding="utf-8")
    caption_checks = {
        "font_coverage": check_font_coverage([c.text for c in cues]),
        "legibility": check_vertical_legibility(style),
        "safe_zone": check_safe_zone(style),
    }
    captions_payload = {
        "blur_specs": len(specs),
        "preserved_tracks": preserved,
        "subtitle_slots": [s.to_dict() for s in slots],
        "skipped_slots": skipped,
        "cues": [c.to_dict() for c in cues],
        "checks": caption_checks,
        "ass_path": str(ass_path),
        "srt_path": str(srt_path),
        "slot_note": "SubtitleSlot boxes are source-frame regions; the ASS "
                     "render uses the TIKTOK_VERTICAL safe-zone caption "
                     "area (captions.build_ass), not per-slot boxes.",
    }
    _write_json(captions_dir / "captions_report.json", captions_payload)
    steps["9_text_and_captions"] = captions_payload

    # ---- Step 10: export ---------------------------------------------
    export_dir = job_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    profile = export_profile_for(EXPORT_PROFILE_NAME)
    project.export_profile = ExportProfile(**profile.to_schema_dict())
    pass1_path = export_dir / "pass1_blur_reframe.mp4"
    pass1 = export_video(stored, pass1_path, profile,
                         ENGINE_AUTHORIZATION, RIGHTS_CONFIRMED,
                         replacements=specs)
    final_path = export_dir / "affiliate_slice_tiktok.mp4"
    mux_final(pass1_path, mix_wav, ass_path, final_path,
              timeline.total_sec)
    final_probe = probe_source(final_path)
    export_payload = {
        "profile": profile.to_dict(),
        "pass1": pass1.to_dict(),
        "final": final_probe.to_dict(),
        "final_sha256": final_probe.sha256,
        "passes": 2,
        "pass_note": "Pass 1 = export_video (blur + reframe, CRF 18, "
                     "faststart). Pass 2 = subtitle burn + mix mux "
                     "(same CRF/AAC/faststart settings) — required "
                     "because export_video has no ASS/mix inputs.",
    }
    _write_json(export_dir / "export_report.json", export_payload)
    steps["10_export"] = export_payload
    manifest["artifacts"]["export_mp4"] = str(final_path)
    manifest["artifacts"]["pass1_mp4"] = str(pass1_path)

    # Preview frame (blurred frame, for Drive 05_PREVIEW + visual check).
    preview_path = export_dir / "preview_frame.jpg"
    preview = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", "1.0", "-i", str(final_path),
         "-frames:v", "1", "-q:v", "2", str(preview_path)],
        capture_output=True, text=True, timeout=60)
    if preview.returncode != 0:
        raise RuntimeError(f"preview frame failed: {preview.stderr[:300]}")
    manifest["artifacts"]["preview_frame"] = str(preview_path)

    # ---- Step 11: QA --------------------------------------------------
    project.video_analysis = VideoAnalysis(
        scenes=[AnalysisScene(
            scene_id=s["scene_id"], start_time=s["start_time"],
            end_time=s["end_time"],
            visual_description=s["visual_description"],
            product_visibility=s["product_visibility"],
            detected_text=s["detected_text"],
            speech_transcript=s["speech_transcript"],
            important_regions=s["important_regions"],
            suggested_edit=s["suggested_edit"],
            confidence=s["confidence"])
            for s in report.to_video_analysis_dict()["scenes"]],
        faces_detected=report.faces_detected,
        hands_detected=False,
        motion_intensity=report.to_video_analysis_dict()["motion_intensity"],
        has_speech=fixture_transcript.has_speech,
        silence_segments=report.to_video_analysis_dict()["silence_segments"],
        engine=report.engine,
        engine_detail=report.engine_detail,
    )
    validation_issues = validate_project(project.to_dict())
    gate_allowed, gate_reasons = export_allowed(project)
    video_qa = qa_export(final_path, EXPORT_PROFILE_NAME, 1080, 1920,
                         expected_fps=30.0, source_path=stored,
                         reframe_strategy="blur_fill")
    affiliate_qa = run_affiliate_qa(
        project, ass_path=ass_path, srt_path=srt_path,
        cues=[c.to_dict() for c in cues],
        video_duration_sec=final_probe.duration_sec,
        mix_path=mix_wav, voice_stem=voice_stem, music_stem=None,
        total_sec=timeline.total_sec)
    project.qa = {"affiliate": affiliate_qa,
                  "video": video_qa.to_dict()}
    project.output = {"export_path": str(final_path),
                      "profile": EXPORT_PROFILE_NAME,
                      "sha256": final_probe.sha256}
    qa_payload = {
        "schema_validation_issues": [i.to_dict()
                                     for i in validation_issues],
        "export_gate": {"allowed": gate_allowed, "reasons": gate_reasons},
        "video_qa": video_qa.to_dict(),
        "affiliate_qa": affiliate_qa,
        "creative_status": "REVIEW_REQUIRED",
        "pronunciation": "PENDING — ear check required; no score claimed",
    }
    qa_dir = job_dir / "qa"
    _write_json(qa_dir / "qa_report.json", qa_payload)
    steps["11_qa"] = qa_payload

    # ---- Step 12: marketing package (facts: user input only) ---------
    package = build_marketing_package(
        product, script, video_duration_sec=final_probe.duration_sec,
        authorization=authorization)
    promise_problems = check_marketing_promises(package)
    marketing_payload = {
        "marketing_package": package,
        "product_info_status": "MISSING — awaiting Mai (no product name, "
                               "price, features, or link supplied)",
        "affiliate_link_status": "MISSING — awaiting Mai",
        "promise_problems": promise_problems,
    }
    marketing_dir = job_dir / "marketing"
    _write_json(marketing_dir / "marketing_package.json", marketing_payload)
    steps["12_marketing"] = marketing_payload
    manifest["artifacts"]["marketing_package"] = str(
        marketing_dir / "marketing_package.json")

    # ---- Project snapshot + manifest ----------------------------------
    manifest["project_snapshot_hash_final"] = project_snapshot_hash(project)
    manifest["snapshot_hash_note"] = (
        "Hash at approval (step 6) differs from the final hash because "
        "the TTS stage fills voice_wav/measured_sec on script segments "
        "after approval; the hash excludes stages/qa/output only.")
    _write_json(job_dir / "project.json", project.to_dict())
    manifest["limitations"] = [
        "No Gemini key: translation/script fallback only; Vietnamese "
        "lines are the human-review record, not Gemini output.",
        "No VieNeu: TTS via tts_cli_provider (female_review preset).",
        "PaddleOCR not installed: OCR via RapidOCR in the CV venv.",
        "Haar face detection unavailable (no cascade XMLs in "
        "opencv-headless 5.0.0); hands detection unavailable.",
        "No authorized music: voice-only mix (REPLACE_ALL); the "
        "voice-above-music QA check does not apply.",
        "Export needed 2 ffmpeg passes: export_video has no ASS "
        "subtitle or external-mix input (missing seam).",
        "ASS captions use the safe-zone caption area, not per-slot "
        "SubtitleSlot boxes.",
        "Creative QA REVIEW_REQUIRED; pronunciation ear-check PENDING.",
        "Product info + affiliate link MISSING (awaiting Mai); no "
        "product facts, prices, claims, or links invented.",
    ]
    manifest_path_out = job_dir / "job_manifest.json"
    _write_json(manifest_path_out, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Affiliate Studio vertical slice (synthetic fixture).")
    parser.add_argument("--job-dir", required=True, type=Path)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--demo-mp3", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    manifest = run_slice(args.job_dir, args.fixture, args.demo_mp3,
                         args.manifest)
    print(json.dumps({
        "status": "SLICE_COMPLETE",
        "export": manifest["artifacts"].get("export_mp4"),
        "qa_video_status": manifest["steps"]["11_qa"]["video_qa"]["status"],
        "qa_affiliate_verdict":
            manifest["steps"]["11_qa"]["affiliate_qa"]["verdict"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
