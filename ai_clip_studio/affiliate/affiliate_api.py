"""Affiliate Studio API — mount-ready handlers for the :8788 server.

Design: this module NEVER edits ``server.py``. Integration adds two
dispatch lines to the product server's ``do_GET`` / ``do_POST``:

    from .affiliate.affiliate_api import (
        handle_affiliate_get, handle_affiliate_post)
    # in do_GET, before the final 404:
    if handle_affiliate_get(self, self.path):
        return
    # in do_POST, before the final 404:
    if handle_affiliate_post(self, self.path, body):
        return

The handler object must provide ``_send(payload, status)``,
``_send_file(path, content_type)`` and ``_send_html(text)`` — the
first two already exist on the product server's Handler; the third
is a 6-line addition documented in AFFILIATE_STUDIO_ARCHITECTURE.md.

Endpoints (all JSON unless noted):
    GET  /affiliate                       the workspace UI (HTML)
    GET  /api/affiliate/health
    GET  /api/affiliate/voices            voice presets (real voices)
    POST /api/affiliate/projects          create project (+inline source)
    GET  /api/affiliate/projects          history, newest first
    GET  /api/affiliate/projects/{id}
    POST /api/affiliate/projects/{id}/upload-chunk
    POST /api/affiliate/projects/{id}/upload-complete
    POST /api/affiliate/projects/{id}/analysis      (Subagent A data in)
    POST /api/affiliate/projects/{id}/ocr-tracks    (Subagent A data in)
    POST /api/affiliate/projects/{id}/edits         (edit operations)
    POST /api/affiliate/projects/{id}/transcribe    (background, 202)
    POST /api/affiliate/projects/{id}/speakers     (manual speaker ranges)
    POST /api/affiliate/projects/{id}/translate
    POST /api/affiliate/projects/{id}/script
    POST /api/affiliate/projects/{id}/script/edit   (clears approval)
    POST /api/affiliate/projects/{id}/script/approve
    POST /api/affiliate/projects/{id}/voice         (background, 202)
    POST /api/affiliate/projects/{id}/voice/preview
    POST /api/affiliate/projects/{id}/subtitles
    POST /api/affiliate/projects/{id}/mix
    POST /api/affiliate/projects/{id}/marketing
    POST /api/affiliate/projects/{id}/qa
    POST /api/affiliate/projects/{id}/export        (501 until render
                                                     integration lands)
    GET  /api/affiliate/projects/{id}/artifacts
    GET  /api/affiliate/projects/{id}/files/{name}  (artifact download)

Long stages (transcribe, voice) run in background threads and report
REAL stage status through the store — progress is never simulated.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import subprocess
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .affiliate_ui import AFFILIATE_UI_HTML
from .asr import (
    assign_speakers,
    extract_audio_for_asr,
    transcribe_chinese,
    transcript_from_dict,
    write_transcript_files,
)
from .audio_timeline import (
    build_affiliate_timeline,
    concatenate_voice,
    plan_mix,
    render_mix,
)
from .captions import build_ass, build_cues, build_srt, safe_zone_guides
from .marketing import build_marketing_package, check_marketing_promises
from .qa import run_affiliate_qa
from .schema import (
    AffiliateError,
    AffiliateProject,
    AudioMix,
    EditOperation,
    OcrTrack,
    ProductInfo,
    SourceAuthorization,
    SourceVideo,
    SubtitleStyle,
    VoiceConfig,
    export_allowed,
    parse_project,
    validate_project,
)
from .script_gen import (
    approve_script,
    clear_approval_on_edit,
    footage_fit_report,
    generate_script,
    script_from_translation,
)
from .source_media import probe_video, sha256_file, store_source_copy
from .store import AffiliateStore
from .translation import translate_segments
from .voice import VOICE_PRESETS, VoiceError, preset_config, preview_voice, synthesize_script

STORE = AffiliateStore()
MAX_INLINE_UPLOAD_BYTES = 200 * 1024 * 1024  # documented JSON-upload limit


# ------------------------------------------------------------------ helpers

def _project_or_404(handler, project_id: str):
    project = STORE.get(project_id)
    if project is None:
        handler._send({"error": f"project not found: {project_id}"}, 404)
        return None
    return project


def _run_in_background(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def _stages_dict(project: AffiliateProject) -> dict:
    return {s["stage"]: s for s in project.stages}


# ------------------------------------------------------------------- workers

def _worker_transcribe(project_id: str) -> None:
    STORE.set_stage(project_id, "transcription", "running")
    try:
        project = STORE.get(project_id)
        project_dir = STORE.project_dir(project_id)
        if project is None or project.source_video is None:
            raise RuntimeError("no source video to transcribe")
        wav = extract_audio_for_asr(Path(project.source_video.stored_path),
                                    project_dir / "transcription")
        transcript = transcribe_chinese(wav)
        write_transcript_files(transcript, project_dir / "transcription")
        detail = (f"{len(transcript.segments)} segment(s), "
                  f"has_speech={transcript.has_speech}, "
                  f"model={transcript.model}")
        STORE.set_stage(project_id, "transcription", "done", detail)
    except Exception as exc:  # noqa: BLE001 - stage failure is recorded
        STORE.set_stage(project_id, "transcription", "failed", str(exc)[:300])


def _worker_voice(project_id: str, voice_payload: dict) -> None:
    STORE.set_stage(project_id, "voice", "running")
    try:
        project = STORE.get(project_id)
        if project is None or project.script is None:
            raise RuntimeError("no approved script to voice")
        config = _voice_config_from_payload(voice_payload,
                                            project.voice)
        project_dir = STORE.project_dir(project_id)
        synthesize_script(project.script, project_dir, config=config)
        project.voice = config
        STORE.save(project)
        footage = project.source_video.duration_sec if project.source_video else 0.0
        timeline = build_affiliate_timeline(
            project.script, footage_sec=footage,
            pause_after_sec=config.pause_after_sec)
        audio_dir = project_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / "timeline.json").write_text(
            json.dumps(timeline.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")
        if timeline.conflict is not None:
            detail = ("voice done; TIMELINE CONFLICT: narration "
                      f"{timeline.conflict['overflow_sec']}s longer than "
                      "footage — resolution required before render")
        else:
            detail = (f"{len(timeline.segments)} segment(s), "
                      f"narration {timeline.narration_sec}s, "
                      f"total {timeline.total_sec}s")
        STORE.set_stage(project_id, "voice", "done", detail)
    except Exception as exc:  # noqa: BLE001 - stage failure is recorded
        STORE.set_stage(project_id, "voice", "failed", str(exc)[:300])


def _voice_config_from_payload(payload: dict,
                               current: VoiceConfig) -> VoiceConfig:
    preset = payload.get("preset", "")
    if preset:
        config = preset_config(str(preset))
    else:
        config = VoiceConfig(
            voice_id=str(payload.get("voice_id", current.voice_id)),
            voice_gender=str(payload.get("voice_gender", current.voice_gender)),
            voice_region=str(payload.get("voice_region", current.voice_region)),
            voice_speed=int(payload.get("voice_speed", current.voice_speed or 100)),
            voice_style=str(payload.get("voice_style", current.voice_style)),
            preset=current.preset)
    if "pause_after_sec" in payload:
        config.pause_after_sec = float(payload["pause_after_sec"])
    if "pronunciation_dictionary" in payload:
        config.pronunciation_dictionary = dict(payload["pronunciation_dictionary"])
    if "voice_speed" in payload and preset:
        config.voice_speed = int(payload["voice_speed"])
    if "speaker_voices" in payload:
        # Per-character dubbing map: speaker_id -> preset name.
        # Validated (preset existence) by synthesize_script.
        config.speaker_voices = {str(k): str(v) for k, v in
                                 dict(payload["speaker_voices"]).items()}
    return config


# ---------------------------------------------------------------------- GET

def handle_affiliate_get(handler, path: str) -> bool:
    """Route GET requests. Returns True when handled."""
    if path in ("/affiliate", "/affiliate/"):
        send_html = getattr(handler, "_send_html", None)
        if send_html is not None:
            send_html(AFFILIATE_UI_HTML)
        else:
            handler._send({"error": "HTML sender not mounted; see "
                           "AFFILIATE_STUDIO_ARCHITECTURE.md"}, 501)
        return True
    if path == "/api/affiliate/health":
        handler._send({"status": "ok", "module": "affiliate_studio",
                       "schema": "AFFILIATE_PROJECT_V1",
                       "phase": "phase1-standalone"})
        return True
    if path == "/api/affiliate/voices":
        handler._send({"presets": {
            name: {"voice_id": spec["voice_id"],
                   "voice_gender": spec["voice_gender"],
                   "voice_speed": spec["voice_speed"],
                   "voice_style": spec["voice_style"],
                   "label_vi": spec["label_vi"]}
            for name, spec in VOICE_PRESETS.items()},
            "note": "Presets map to real provider voices only; region "
                    "is the provider default (not exposed by the CLI)."})
        return True
    if path == "/api/affiliate/projects":
        handler._send({"projects": STORE.list_projects()})
        return True
    match = re.match(r"^/api/affiliate/projects/([^/]+)$", path)
    if match:
        project = _project_or_404(handler, match.group(1))
        if project is not None:
            handler._send(project.to_dict())
        return True
    match = re.match(r"^/api/affiliate/projects/([^/]+)/artifacts$", path)
    if match:
        project = _project_or_404(handler, match.group(1))
        if project is None:
            return True
        root = STORE.project_dir(match.group(1))
        handler._send({
            "project_id": match.group(1),
            "artifacts": sorted(str(p.relative_to(root))
                                for p in root.rglob("*") if p.is_file())})
        return True
    match = re.match(r"^/api/affiliate/projects/([^/]+)/files/(.+)$", path)
    if match:
        project = _project_or_404(handler, match.group(1))
        if project is None:
            return True
        root = STORE.project_dir(match.group(1))
        target = (root / match.group(2)).resolve()
        if root.resolve() not in target.parents and target != root.resolve():
            handler._send({"error": "path outside project directory"}, 400)
            return True
        if not target.exists() or not target.is_file():
            handler._send({"error": "file not found"}, 404)
            return True
        content_type = {
            ".mp4": "video/mp4", ".wav": "audio/wav", ".mp3": "audio/mpeg",
            ".srt": "text/plain", ".ass": "text/plain",
            ".json": "application/json", ".txt": "text/plain",
            ".png": "image/png", ".jpg": "image/jpeg",
        }.get(target.suffix.lower(), "application/octet-stream")
        handler._send_file(target, content_type)
        return True
    return False


# --------------------------------------------------------------------- POST

def handle_affiliate_post(handler, path: str, body: dict) -> bool:
    """Route POST requests. Returns True when handled."""
    if path == "/api/affiliate/projects":
        return _create_project(handler, body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/upload-chunk$", path)
    if match:
        return _upload_chunk(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/upload-complete$", path)
    if match:
        return _upload_complete(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/analysis$", path)
    if match:
        return _ingest_analysis(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/ocr-tracks$", path)
    if match:
        return _ingest_ocr(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/edits$", path)
    if match:
        return _ingest_edits(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/transcribe$", path)
    if match:
        project = _project_or_404(handler, match.group(1))
        if project is None:
            return True
        if project.source_video is None:
            handler._send({"error": "no source video uploaded yet"}, 409)
            return True
        _run_in_background(_worker_transcribe, match.group(1))
        handler._send({"project_id": match.group(1),
                       "status": "transcription_started"}, 202)
        return True
    match = re.match(r"^/api/affiliate/projects/([^/]+)/speakers$", path)
    if match:
        return _assign_speakers_endpoint(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/translate$", path)
    if match:
        return _translate(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/script$", path)
    if match:
        return _generate_script(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/script/edit$", path)
    if match:
        return _edit_script(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/script/approve$", path)
    if match:
        return _approve_script(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/voice$", path)
    if match:
        return _start_voice(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/voice/preview$", path)
    if match:
        return _voice_preview(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/subtitles$", path)
    if match:
        return _build_subtitles(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/mix$", path)
    if match:
        return _build_mix(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/marketing$", path)
    if match:
        return _build_marketing(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/qa$", path)
    if match:
        return _run_qa(handler, match.group(1), body)
    match = re.match(r"^/api/affiliate/projects/([^/]+)/export$", path)
    if match:
        project = _project_or_404(handler, match.group(1))
        if project is None:
            return True
        # The authorization/rights gate is enforced on the export path
        # itself — before the (Phase 1 unimplemented) render stage.
        allowed, reasons = export_allowed(project)
        if not allowed:
            handler._send({
                "error": "export refused: authorization/rights gate",
                "reasons": reasons}, 403)
            return True
        handler._send({
            "error": "export is not implemented in Phase 1: the render/"
                     "export stage is owned by Subagent A and is wired "
                     "at integration (ATLAS). No file was produced.",
            "export_gate": []}, 501)
        return True
    return False


# ------------------------------------------------------------------ handlers

def _create_project(handler, body: dict) -> bool:
    project_id = STORE.new_project_id()
    try:
        product = ProductInfo(**{k: v for k, v in (body.get("product") or {}).items()
                                 if k in ProductInfo.__dataclass_fields__})
        if not product.product_name:
            handler._send({"error": "product.product_name is required"}, 400)
            return True
        auth = SourceAuthorization(**{k: v for k, v in (body.get("authorization") or {}).items()
                                      if k in SourceAuthorization.__dataclass_fields__})
        source_url = str(body.get("source_url") or "").strip()
        if source_url and not source_url.startswith(("http://", "https://")):
            handler._send({"error": "source_url must be an http/https URL"},
                          400)
            return True
        project = AffiliateProject(
            project_id=project_id,
            project_name=str(body.get("project_name", "")),
            product=product, authorization=auth)
        issues = validate_project(project.to_dict())
        blocking = [i for i in issues if i.code in ("AFF003", "AFF004", "AFF005", "AFF006")]
        if blocking:
            handler._send({"error": "project validation failed",
                           "issues": [i.to_dict() for i in blocking]}, 400)
            return True
        STORE.create(project)
        project_dir = STORE.project_dir(project_id)
        source = body.get("source") or {}
        if source.get("data_base64"):
            try:
                raw = base64.b64decode(source["data_base64"], validate=True)
            except (binascii.Error, ValueError):
                handler._send({"error": "source.data_base64 is not valid base64"}, 400)
                return True
            if len(raw) > MAX_INLINE_UPLOAD_BYTES:
                handler._send({"error": "inline upload exceeds the "
                               f"{MAX_INLINE_UPLOAD_BYTES}-byte limit; use "
                               "the chunked upload endpoints"}, 413)
                return True
            tmp = project_dir / "upload_tmp.bin"
            tmp.write_bytes(raw)
            safe_name = Path(str(source.get("file_name", "source.mp4"))).name
            staged = project_dir / safe_name
            tmp.replace(staged)
            try:
                project.source_video = store_source_copy(staged, project_dir)
            finally:
                staged.unlink(missing_ok=True)
            STORE.save(project)
            STORE.set_stage(project_id, "upload", "done",
                            f"{project.source_video.file_name} "
                            f"({project.source_video.file_size_bytes} bytes, "
                            f"sha256 {project.source_video.sha256[:12]}…)")
        elif source.get("source_path"):
            try:
                project.source_video = store_source_copy(
                    Path(source["source_path"]), project_dir)
            except (ValueError, RuntimeError, FileNotFoundError) as exc:
                handler._send({"error": f"source intake failed: {exc}"}, 400)
                return True
            STORE.save(project)
            STORE.set_stage(project_id, "upload", "done",
                            f"{project.source_video.file_name} stored")
        # A source URL is recorded as PROVENANCE ONLY. This module
        # never fetches a URL: the file must be uploaded separately,
        # and the export gate still refuses without a checksum and a
        # confirmed authorization.
        if source_url:
            if project.source_video is not None:
                project.source_video.source_url = source_url
            else:
                project.source_video = SourceVideo(
                    file_name="(link only — no file uploaded)",
                    file_size_bytes=0, source_url=source_url)
            STORE.save(project)
        handler._send(project.to_dict(), 201)
        return True
    except (TypeError, ValueError) as exc:
        handler._send({"error": f"invalid project payload: {exc}"}, 400)
        return True


def _upload_chunk(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    try:
        index = int(body["chunk_index"])
        if index < 0:
            raise ValueError("negative chunk_index")
        raw = base64.b64decode(body["data_base64"], validate=True)
    except (KeyError, ValueError, binascii.Error):
        handler._send({"error": "chunk_index + valid data_base64 required"}, 400)
        return True
    chunk_dir = STORE.project_dir(project_id) / "upload_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    (chunk_dir / f"chunk_{index:06d}.bin").write_bytes(raw)
    STORE.set_stage(project_id, "upload", "running",
                    f"received chunk {index} ({len(raw)} bytes)")
    handler._send({"project_id": project_id, "chunk_index": index,
                   "received_bytes": len(raw)})
    return True


def _upload_complete(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    file_name = Path(str(body.get("file_name", ""))).name
    total = int(body.get("total_chunks", 0))
    if not file_name or total <= 0:
        handler._send({"error": "file_name + total_chunks required"}, 400)
        return True
    chunk_dir = STORE.project_dir(project_id) / "upload_chunks"
    project_dir = STORE.project_dir(project_id)
    staged = project_dir / file_name
    try:
        with open(staged, "wb") as out:
            for index in range(total):
                chunk = chunk_dir / f"chunk_{index:06d}.bin"
                if not chunk.exists():
                    handler._send({"error": f"missing chunk {index}"}, 400)
                    return True
                out.write(chunk.read_bytes())
        expected = str(body.get("sha256", ""))
        if expected and sha256_file(staged) != expected:
            staged.unlink(missing_ok=True)
            handler._send({"error": "checksum mismatch after assembly"}, 400)
            return True
        project.source_video = store_source_copy(staged, project_dir)
        STORE.save(project)
        STORE.set_stage(project_id, "upload", "done",
                        f"{project.source_video.file_name} assembled "
                        f"from {total} chunk(s)")
        handler._send(project.to_dict())
        return True
    except (ValueError, RuntimeError) as exc:
        handler._send({"error": f"source intake failed: {exc}"}, 400)
        return True
    finally:
        staged.unlink(missing_ok=True)


def _ingest_analysis(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    try:
        from .schema import AnalysisScene, VideoAnalysis
        scenes = [AnalysisScene(**{k: v for k, v in s.items()
                                   if k in AnalysisScene.__dataclass_fields__})
                  for s in body.get("scenes", [])]
        project.video_analysis = VideoAnalysis(
            scenes=scenes,
            faces_detected=bool(body.get("faces_detected", False)),
            hands_detected=bool(body.get("hands_detected", False)),
            motion_intensity=str(body.get("motion_intensity", "")),
            has_speech=bool(body.get("has_speech", False)),
            silence_segments=list(body.get("silence_segments", [])),
            engine=str(body.get("engine", "")),
            engine_detail=str(body.get("engine_detail", "")))
        STORE.save(project)
        STORE.set_stage(project_id, "analysis", "done",
                        f"{len(scenes)} scene(s), engine={project.video_analysis.engine}")
        handler._send(project.to_dict())
        return True
    except (TypeError, ValueError) as exc:
        handler._send({"error": f"invalid analysis payload: {exc}"}, 400)
        return True


def _ingest_ocr(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    try:
        tracks = [OcrTrack(**{k: v for k, v in t.items()
                              if k in OcrTrack.__dataclass_fields__})
                  for t in body.get("tracks", [])]
        project.ocr_tracks = tracks
        STORE.save(project)
        STORE.set_stage(project_id, "ocr", "done", f"{len(tracks)} track(s)")
        handler._send(project.to_dict())
        return True
    except (TypeError, ValueError) as exc:
        handler._send({"error": f"invalid OCR payload: {exc}"}, 400)
        return True


def _ingest_edits(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    try:
        ops = [EditOperation(**{k: v for k, v in o.items()
                                if k in EditOperation.__dataclass_fields__})
               for o in body.get("operations", [])]
        project.edit_operations = ops
        issues = validate_project(project.to_dict())
        gate_issues = [i for i in issues if i.code in ("AFF016", "AFF020", "AFF021")]
        STORE.save(project)
        STORE.set_stage(project_id, "edit", "done",
                        f"{len(ops)} operation(s); "
                        f"{len(gate_issues)} gate issue(s)")
        handler._send({"project": project.to_dict(),
                       "gate_issues": [i.to_dict() for i in gate_issues]})
        return True
    except (TypeError, ValueError) as exc:
        handler._send({"error": f"invalid edits payload: {exc}"}, 400)
        return True


def _transcript_segments(project_id: str) -> list[dict]:
    transcript_path = (STORE.project_dir(project_id) / "transcription"
                       / "source_transcript.json")
    if not transcript_path.exists():
        return []
    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    return [{"start": s["start"], "end": s["end"], "text": s["text"],
             "speaker_id": s.get("speaker_id", "SPEAKER_00")}
            for s in payload.get("segments", [])]


def _assign_speakers_endpoint(handler, project_id: str,
                            body: dict) -> bool:
    """Apply explicit user-supplied speaker ranges to the stored
    transcript (per-character dubbing). Ranges are user data — the
    server never guesses speakers."""
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    transcript_path = (STORE.project_dir(project_id) / "transcription"
                       / "source_transcript.json")
    if not transcript_path.exists():
        handler._send({"error": "no transcript yet — run transcription "
                               "first"}, 409)
        return True
    try:
        transcript = transcript_from_dict(
            json.loads(transcript_path.read_text(encoding="utf-8")))
        result = assign_speakers(transcript,
                                 list(body.get("ranges", [])))
    except ValueError as exc:
        handler._send({"error": str(exc)}, 400)
        return True
    write_transcript_files(transcript,
                           STORE.project_dir(project_id) / "transcription")
    handler._send({"project_id": project_id, **result,
                   "speaker_method": transcript.speaker_method})
    return True


def _translate(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    if project.product is None:
        handler._send({"error": "no product record"}, 409)
        return True
    mode = str(body.get("mode", "NATURAL_LOCALIZATION"))
    style = str(body.get("style", "neutral"))
    segments = _transcript_segments(project_id)
    if not segments and project.ocr_tracks:
        segments = [{"start": t.start_time, "end": t.end_time,
                     "text": t.original_text} for t in project.ocr_tracks
                    if t.text_classification == "SUBTITLE"]
    visible_demo = str(body.get("visible_demonstration", ""))
    try:
        record = translate_segments(
            segments, project.product, mode=mode, style=style,
            visible_demonstration=visible_demo)
    except ValueError as exc:
        handler._send({"error": str(exc)}, 400)
        return True
    project.translation = record
    STORE.save(project)
    STORE.set_stage(project_id, "translation", "done",
                    f"mode={mode} style={style} engine={record.engine} "
                    f"review={record.needs_human_review}")
    handler._send({"project_id": project_id,
                   "translation": asdict(record)})
    return True


def _generate_script(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    if project.product is None:
        handler._send({"error": "no product record"}, 409)
        return True
    # Dubbing flow: build the script 1:1 from the translated
    # segments, preserving speaker labels for per-character dubbing.
    if str(body.get("source", "")) == "translation":
        if (project.translation is None
                or not (project.translation.translated_segments
                        or project.translation.rewritten_segments)):
            handler._send(
                {"error": "no translated segments to dub yet — run "
                          "translation first"}, 409)
            return True
        try:
            script = script_from_translation(
                project.translation,
                target_seconds=float(body.get("target_seconds", 0.0)))
        except ValueError as exc:
            handler._send({"error": str(exc)}, 400)
            return True
        project.script = script
        STORE.save(project)
        STORE.set_stage(project_id, "script", "done",
                        f"variant=dubbed_translation engine={script.engine} "
                        f"segments={len(script.segments)}")
        handler._send({"project_id": project_id, "script": asdict(script),
                       "footage_fit": {"fits": None,
                                       "note": "dub script mirrors source "
                                               "timing; fit is checked at "
                                               "the voice stage"}})
        return True
    variant = str(body.get("variant", "natural_review"))
    target = float(body.get("target_seconds", 30.0))
    visible_demo = str(body.get("visible_demonstration", ""))
    summary = ""
    if project.translation is not None:
        summary = " ".join(s.get("text", "")
                           for s in project.translation.original_segments)[:500]
    try:
        script = generate_script(
            project.product, variant=variant, target_seconds=target,
            visible_demonstration=visible_demo, source_summary=summary)
    except ValueError as exc:
        handler._send({"error": str(exc)}, 400)
        return True
    project.script = script
    STORE.save(project)
    footage = project.source_video.duration_sec if project.source_video else 0.0
    fit = footage_fit_report(script, footage) if footage else {"fits": None}
    STORE.set_stage(project_id, "script", "done",
                    f"variant={variant} engine={script.engine} "
                    f"estimated={sum(s.estimated_sec for s in script.segments):.1f}s")
    handler._send({"project_id": project_id, "script": asdict(script),
                   "footage_fit": fit})
    return True


def _edit_script(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    if project.script is None:
        handler._send({"error": "no script to edit"}, 409)
        return True
    try:
        from .schema import ScriptSegment
        segments = [ScriptSegment(**{k: v for k, v in s.items()
                                     if k in ScriptSegment.__dataclass_fields__})
                    for s in body.get("segments", [])]
    except (TypeError, ValueError) as exc:
        handler._send({"error": f"invalid segments: {exc}"}, 400)
        return True
    project.script.segments = segments
    clear_approval_on_edit(project.script)
    STORE.save(project)
    STORE.set_stage(project_id, "script_approval", "queued",
                    "script edited — re-approval required")
    handler._send({"project_id": project_id, "approved": False,
                   "note": "Edits clear the previous approval; re-approve "
                           "before TTS."})
    return True


def _approve_script(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    if project.script is None:
        handler._send({"error": "no script to approve"}, 409)
        return True
    approve_script(project.script,
                   approved_by=str(body.get("approved_by", "user")),
                   note=str(body.get("note", "")))
    STORE.save(project)
    STORE.set_stage(project_id, "script_approval", "done",
                    f"approved by {project.script.approved_by}")
    handler._send({"project_id": project_id, "approved": True})
    return True


def _start_voice(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    if project.script is None or not project.script.approved:
        handler._send({"error": "script must be approved before TTS"}, 409)
        return True
    _run_in_background(_worker_voice, project_id, dict(body))
    handler._send({"project_id": project_id, "status": "voice_started"}, 202)
    return True


def _voice_preview(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    try:
        config = _voice_config_from_payload(dict(body), project.voice)
        wav = preview_voice(config, STORE.project_dir(project_id) / "voices")
    except VoiceError as exc:
        handler._send({"error": str(exc)}, 400)
        return True
    handler._send({"project_id": project_id, "preview": "voices/voice_preview.wav",
                   "voice_id": config.voice_id or config.preset})
    return True


def _build_subtitles(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    timeline_path = (STORE.project_dir(project_id) / "audio" / "timeline.json")
    if not timeline_path.exists():
        handler._send({"error": "no voice timeline yet — run voice first"}, 409)
        return True
    style_payload = body.get("subtitle_style") or {}
    style = SubtitleStyle(**{**project.subtitle_style.__dict__,
                             **{k: v for k, v in style_payload.items()
                                if k in SubtitleStyle.__dataclass_fields__}})
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    cues = build_cues(timeline["segments"], style)
    sub_dir = STORE.project_dir(project_id) / "subtitles"
    sub_dir.mkdir(parents=True, exist_ok=True)
    ass_text = build_ass(cues, style)
    srt_text = build_srt(cues)
    (sub_dir / "captions.ass").write_text(ass_text, encoding="utf-8")
    (sub_dir / "captions.srt").write_text(srt_text, encoding="utf-8")
    project.subtitle_style = style
    STORE.save(project)
    STORE.set_stage(project_id, "subtitles", "done", f"{len(cues)} cue(s)")
    handler._send({"project_id": project_id, "cues": len(cues),
                   "ass": "subtitles/captions.ass",
                   "srt": "subtitles/captions.srt",
                   "safe_zone_guides": safe_zone_guides(style)})
    return True


def _build_mix(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    timeline_path = (STORE.project_dir(project_id) / "audio" / "timeline.json")
    if not timeline_path.exists():
        handler._send({"error": "no voice timeline yet — run voice first"}, 409)
        return True
    mix_payload = body.get("audio_mix") or {}
    mix = AudioMix(**{**project.audio_mix.__dict__,
                      **{k: v for k, v in mix_payload.items()
                         if k in AudioMix.__dataclass_fields__}})
    try:
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        from .audio_timeline import AffiliateTimeline, TimelineSegment
        tl = AffiliateTimeline(
            segments=[TimelineSegment(**s) for s in timeline["segments"]],
            footage_sec=timeline["footage_sec"],
            narration_sec=timeline["narration_sec"],
            total_sec=timeline["total_sec"],
            all_measured=True, conflict=timeline.get("conflict"))
        audio_dir = STORE.project_dir(project_id) / "audio"
        voice_stem = concatenate_voice(tl, audio_dir / "voice_stem.wav")
        original_wav = ""
        if project.source_video and project.source_video.has_audio:
            original_wav = str(audio_dir / "original_stem.wav")
            result = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i",
                              project.source_video.stored_path,
                              "-vn", "-ac", "2", "-ar", "48000", original_wav],
                             capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                original_wav = ""
        music_wav = mix.music_path if mix.music_path else ""
        plan = plan_mix(mix, voice_wav=str(voice_stem),
                        original_wav=original_wav, music_wav=music_wav,
                        total_sec=tl.total_sec)
        mixed = render_mix(plan, audio_dir / "mix.wav")
    except Exception as exc:  # noqa: BLE001 - report, stage marked failed
        STORE.set_stage(project_id, "mix", "failed", str(exc)[:300])
        handler._send({"error": f"mix failed: {exc}"}, 500)
        return True
    project.audio_mix = mix
    STORE.save(project)
    STORE.set_stage(project_id, "mix", "done", f"mode={mix.mode} -> mix.wav")
    handler._send({"project_id": project_id, "mix": "audio/mix.wav",
                   "plan": plan.to_dict()})
    return True


def _build_marketing(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    if project.product is None:
        handler._send({"error": "no product record"}, 409)
        return True
    duration = project.source_video.duration_sec if project.source_video else 0.0
    package = build_marketing_package(project.product, project.script,
                                      video_duration_sec=duration,
                                      authorization=project.authorization)
    problems = check_marketing_promises(package)
    out_dir = STORE.project_dir(project_id) / "marketing"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "marketing_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    STORE.set_stage(project_id, "marketing", "done",
                    f"{len(package['hashtags'])} hashtag(s); "
                    f"{len(problems)} promise flag(s)")
    handler._send({"project_id": project_id, "package": package,
                   "promise_flags": problems})
    return True


def _run_qa(handler, project_id: str, body: dict) -> bool:
    project = _project_or_404(handler, project_id)
    if project is None:
        return True
    project_dir = STORE.project_dir(project_id)
    ass = project_dir / "subtitles" / "captions.ass"
    srt = project_dir / "subtitles" / "captions.srt"
    timeline_path = project_dir / "audio" / "timeline.json"
    cues: list[dict] = []
    total = 0.0
    if timeline_path.exists():
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        cues = timeline["segments"]
        total = timeline["total_sec"]
    duration = project.source_video.duration_sec if project.source_video else total
    mix = project_dir / "audio" / "mix.wav"
    voice_stem = project_dir / "audio" / "voice_stem.wav"
    report = run_affiliate_qa(
        project,
        ass_path=ass if ass.exists() else None,
        srt_path=srt if srt.exists() else None,
        cues=cues, video_duration_sec=duration,
        mix_path=mix if mix.exists() else None,
        voice_stem=voice_stem if voice_stem.exists() else None,
        music_stem=None, total_sec=total)
    project.qa = report
    STORE.save(project)
    qa_dir = project_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / "qa_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    STORE.set_stage(project_id, "qa",
                    "done" if report["verdict"] == "PASS" else "failed",
                    f"verdict={report['verdict']}, "
                    f"{report['total_checks']} check(s)")
    handler._send({"project_id": project_id, "qa": report})
    return True
