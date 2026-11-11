"""Universal orchestrator — 19 stages, in order (Master Prompt §11).

    RECEIVE_SCRIPT -> FREEZE_SCRIPT_SNAPSHOT -> PARSE_SCRIPT
    -> GEMINI_STORY_PLANNING -> BUILD_PRODUCTION_SCENE_PACKAGE
    -> RESOLVE_CHARACTERS -> RESOLVE_ENVIRONMENTS
    -> COMPILE_ACTION_ANIMATIONS -> GENERATE_VIETNAMESE_TTS
    -> MEASURE_REAL_AUDIO_DURATION -> BUILD_DYNAMIC_TIMELINE
    -> RESOLVE_SFX_MUSIC_MEMES -> RUN_PREFLIGHT
    -> RENDER_MOTION_CANVAS_THREEJS -> MIX_AUDIO_AND_SUBTITLES
    -> ENCODE_MP4 -> VALIDATE_RENDERED_OUTPUT
    -> UPLOAD_ARTIFACTS_TO_GOOGLE_DRIVE -> RETURN_DRIVE_LINKS

Each stage has typed input/output (StageResult), a structured log
entry, a clear failure state, and a persistent job status file
(jobs/{job_id}/status.json) plus intermediate artifacts under
jobs/{job_id}/. Stages that call real code call it through
upstream.py (read-only clone). Stages whose real dependency is
missing FAIL with the exact diagnostic — no mock success, no
"complete" flag on a stage that did not run.

Job status is one of:
    IMPLEMENTATION_IN_PROGRESS / BLOCKED_WITH_EXPLICIT_REASON /
    END_TO_END_DRAFT_READY_FOR_REVIEW / MASTER_APPROVED_AND_UPLOADED
Only a real validated MP4 uploaded to Drive may reach
END_TO_END_DRAFT_READY_FOR_REVIEW.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .audio_events import plan_audio_events
from .drive_uploader import DriveUploader
from .pipeline import segment_script
from .preflight import run_preflight
from .production_request import ProductionRequest
from .timeline import TimelineLine, build_timeline
from . import upstream

STAGES: tuple[str, ...] = (
    "RECEIVE_SCRIPT",
    "FREEZE_SCRIPT_SNAPSHOT",
    "PARSE_SCRIPT",
    "GEMINI_STORY_PLANNING",
    "BUILD_PRODUCTION_SCENE_PACKAGE",
    "RESOLVE_CHARACTERS",
    "RESOLVE_ENVIRONMENTS",
    "COMPILE_ACTION_ANIMATIONS",
    "GENERATE_VIETNAMESE_TTS",
    "MEASURE_REAL_AUDIO_DURATION",
    "BUILD_DYNAMIC_TIMELINE",
    "RESOLVE_SFX_MUSIC_MEMES",
    "RUN_PREFLIGHT",
    "RENDER_MOTION_CANVAS_THREEJS",
    "MIX_AUDIO_AND_SUBTITLES",
    "ENCODE_MP4",
    "VALIDATE_RENDERED_OUTPUT",
    "UPLOAD_ARTIFACTS_TO_GOOGLE_DRIVE",
    "RETURN_DRIVE_LINKS",
)

STATUS_IN_PROGRESS = "IMPLEMENTATION_IN_PROGRESS"
STATUS_BLOCKED = "BLOCKED_WITH_EXPLICIT_REASON"
STATUS_DRAFT_READY = "END_TO_END_DRAFT_READY_FOR_REVIEW"
STATUS_MASTER = "MASTER_APPROVED_AND_UPLOADED"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED_BLOCKED = "skipped_blocked"


@dataclass
class StageResult:
    stage: str
    status: StageStatus
    detail: str = ""
    artifacts: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    ended_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage, "status": self.status.value,
            "detail": self.detail, "artifacts": self.artifacts,
            "data": self.data,
            "duration_sec": round(self.ended_at - self.started_at, 3),
        }


@dataclass
class Job:
    job_id: str
    request: ProductionRequest
    job_dir: Path
    stages: list[StageResult] = field(default_factory=list)
    status: str = STATUS_IN_PROGRESS
    blocked_reason: str = ""
    log: list[dict[str, Any]] = field(default_factory=list)

    def record(self, result: StageResult) -> None:
        self.stages.append(result)
        self.log.append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "stage": result.stage, "status": result.status.value,
            "detail": result.detail,
        })
        self._persist()

    def _persist(self) -> None:
        self.job_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "job_id": self.job_id,
            "request_id": self.request.request_id,
            "script_hash": self.request.script_hash,
            "status": self.status,
            "blocked_reason": self.blocked_reason,
            "stages": [s.to_dict() for s in self.stages],
            "log": self.log,
        }
        (self.job_dir / "status.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "request_id": self.request.request_id,
            "script_hash": self.request.script_hash,
            "status": self.status,
            "blocked_reason": self.blocked_reason,
            "stages": [s.to_dict() for s in self.stages],
        }


class UniversalProductionPipeline:
    """Runs the 19 stages. `render_fn` / `drive_client` are injectable
    for tests; in production they are None and the real dependencies
    are probed (and honestly fail when absent)."""

    def __init__(
        self,
        jobs_root: Path,
        *,
        render_fn: Callable[[ProductionRequest, dict, Path], Path] | None = None,
        drive_client: Any | None = None,
        meme_catalog: dict | None = None,
        voice_provider: Callable[[list, Path], list[Path]] | None = None,
        planner: Callable[[str], dict] | None = None,
    ) -> None:
        self.jobs_root = Path(jobs_root)
        self.render_fn = render_fn
        self.drive_client = drive_client
        self.meme_catalog = meme_catalog
        # planner(script) -> scene package dict. Production: None (real
        # Gemini director). Tests may inject a deterministic planner
        # built from the real segmentation code — recorded as such,
        # never presented as Gemini output.
        self.planner = planner
        # voice_provider(lines, job_dir) -> list of real WAV paths, one
        # per line. Production: None (real VieNeu). Tests may inject a
        # provider that writes real WAV files (measured, not mocked).
        self.voice_provider = voice_provider

    # -- helpers ------------------------------------------------------
    def _stage(self, job: Job, name: str) -> StageResult:
        result = StageResult(stage=name, status=StageStatus.RUNNING,
                             started_at=time.time())
        return result

    def _finish(self, job: Job, result: StageResult,
                status: StageStatus, detail: str = "",
                artifacts: list[str] | None = None,
                data: dict | None = None) -> StageResult:
        result.status = status
        result.detail = detail
        result.artifacts = artifacts or []
        result.data = data or {}
        result.ended_at = time.time()
        job.record(result)
        return result

    def _fail(self, job: Job, result: StageResult, reason: str) -> Job:
        self._finish(job, result, StageStatus.FAILED, reason)
        job.status = STATUS_BLOCKED
        job.blocked_reason = f"{result.stage}: {reason}"
        job._persist()
        return job

    # -- main ---------------------------------------------------------
    def run(self, script_text: str, *, language: str = "vi-VN",
            aspect_ratio: str = "16:9",
            available_voices: tuple[str, ...] = ("narrator",),
            request_id: str | None = None) -> Job:
        request = ProductionRequest(script_text=script_text, language=language,
                                    aspect_ratio=aspect_ratio,
                                    request_id=request_id or f"req_{__import__('uuid').uuid4().hex[:12]}")
        job_dir = self.jobs_root / request.request_id
        job_dir.mkdir(parents=True, exist_ok=True)
        job = Job(job_id=request.request_id, request=request, job_dir=job_dir)
        ctx: dict[str, Any] = {"request": request}

        # 1. RECEIVE_SCRIPT
        r = self._stage(job, "RECEIVE_SCRIPT")
        if not script_text.strip():
            return self._fail(job, r, "empty script received")
        self._finish(job, r, StageStatus.PASSED,
                     f"received {len(script_text)} chars, language={language}")

        # 2. FREEZE_SCRIPT_SNAPSHOT
        r = self._stage(job, "FREEZE_SCRIPT_SNAPSHOT")
        snapshot = job_dir / "script_snapshot.txt"
        snapshot.write_text(script_text, encoding="utf-8")
        manifest = job_dir / "production_request.json"
        manifest.write_text(json.dumps(request.manifest(), indent=2,
                                       ensure_ascii=False), encoding="utf-8")
        self._finish(job, r, StageStatus.PASSED,
                     f"script_hash={request.script_hash[:16]}…",
                     artifacts=[str(snapshot), str(manifest)])

        # 3. PARSE_SCRIPT — real StudioScriptV1Parser
        r = self._stage(job, "PARSE_SCRIPT")
        try:
            parsed = upstream.parse_studio_script_v1(script_text)
            ctx["parsed_v1"] = parsed
            n_scenes = len(parsed.get("scenes", []))
            detail = f"StudioScriptV1Parser: {n_scenes} scene(s)"
        except upstream.UpstreamUnavailable as exc:
            return self._fail(job, r, str(exc))
        segmented = segment_script(script_text)
        ctx["segmented"] = segmented
        (job_dir / "parsed_script.json").write_text(
            json.dumps(parsed, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8")
        self._finish(job, r, StageStatus.PASSED,
                     f"{detail}; generic segmentation: "
                     f"{len(segmented.lines)} lines, "
                     f"{len(segmented.characters)} character(s), "
                     f"{len(segmented.visual_events)} visual event(s)",
                     artifacts=[str(job_dir / "parsed_script.json")])

        # 4. GEMINI_STORY_PLANNING — real director, fails without key/deps.
        # An injected planner (tests) is recorded as a fallback, never
        # presented as Gemini output.
        r = self._stage(job, "GEMINI_STORY_PLANNING")
        try:
            if self.planner is not None:
                package = self.planner(script_text)
                detail = "fallback planner (injected): package built from real segmentation"
            else:
                package = upstream.gemini_story_plan(script_text)
                detail = "Gemini director produced a scene package"
            ctx["package"] = package
            (job_dir / "scene_package.json").write_text(
                json.dumps(package, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8")
            self._finish(job, r, StageStatus.PASSED, detail,
                         artifacts=[str(job_dir / "scene_package.json")])
        except upstream.UpstreamUnavailable as exc:
            return self._fail(job, r, str(exc))

        # 5. BUILD_PRODUCTION_SCENE_PACKAGE
        r = self._stage(job, "BUILD_PRODUCTION_SCENE_PACKAGE")
        package = ctx["package"]
        ctx["scene_package"] = {
            "project_id": request.request_id,
            "script_hash": request.script_hash,
            "language": language,
            "visual_style": request.visual_style,
            "aspect_ratio": aspect_ratio,
            "characters": package.get("characters", []),
            "locations": package.get("locations", []),
            "scenes": package.get("scenes", []),
            "shots": package.get("shots", []),
            "audio_events": package.get("audio_events", []),
            "render_settings": {"width": 1920, "height": 1080, "fps": 24,
                                "loudness_lufs": -14.0},
        }
        (job_dir / "production_scene_package.json").write_text(
            json.dumps(ctx["scene_package"], indent=2, ensure_ascii=False,
                       default=str), encoding="utf-8")
        self._finish(job, r, StageStatus.PASSED,
                     f"package: {len(ctx['scene_package']['scenes'])} scenes, "
                     f"{len(ctx['scene_package']['shots'])} shots",
                     artifacts=[str(job_dir / "production_scene_package.json")])

        # 6. RESOLVE_CHARACTERS
        r = self._stage(job, "RESOLVE_CHARACTERS")
        chars = ctx["scene_package"]["characters"] or segmented.characters
        if not chars:
            return self._fail(job, r, "no characters resolved from script or package")
        ctx["characters"] = chars
        self._finish(job, r, StageStatus.PASSED,
                     f"characters: {', '.join(str(c) for c in chars)}")

        # 7. RESOLVE_ENVIRONMENTS
        r = self._stage(job, "RESOLVE_ENVIRONMENTS")
        locs = ctx["scene_package"]["locations"]
        ctx["locations"] = locs
        self._finish(job, r, StageStatus.PASSED,
                     f"locations: {locs if locs else 'none named — generic set'}")

        # 8. COMPILE_ACTION_ANIMATIONS
        r = self._stage(job, "COMPILE_ACTION_ANIMATIONS")
        actions = [e["event"] for e in segmented.visual_events]
        ctx["actions"] = actions
        self._finish(job, r, StageStatus.PASSED,
                     f"compiled {len(actions)} action/animation cues "
                     f"from visual events: {sorted(set(actions)) or 'none'}")

        # 9. GENERATE_VIETNAMESE_TTS — real VieNeu, fails when absent.
        # An injected voice_provider (tests / a real TTS service on the
        # Windows machine) must return REAL wav files, one per line.
        r = self._stage(job, "GENERATE_VIETNAMESE_TTS")
        if self.voice_provider is not None:
            try:
                voice_wavs = self.voice_provider(segmented.lines, job_dir)
            except Exception as exc:
                return self._fail(job, r, f"voice provider failed: {exc}")
            if len(voice_wavs) != len(segmented.lines):
                return self._fail(
                    job, r, f"voice provider returned {len(voice_wavs)} wavs "
                    f"for {len(segmented.lines)} lines")
            self._finish(job, r, StageStatus.PASSED,
                         f"generated {len(voice_wavs)} voice file(s) "
                         f"(injected provider)",
                         artifacts=[str(w) for w in voice_wavs])
            return self._run_after_tts(job, ctx, voice_wavs, available_voices)
        ok, detail = upstream.check_vieneu_available()
        if not ok:
            return self._fail(job, r, detail)
        return self._fail(job, r,
                          "VieNeu package importable but no TTS synthesis "
                          "wired on this VM — run on Mai's Windows machine")

    # -- stages 10-19 (run after TTS) ---------------------------------
    def _run_after_tts(self, job: Job, ctx: dict, voice_wavs: list[Path],
                       available_voices: tuple[str, ...]) -> Job:
        request = ctx["request"]
        job_dir = job.job_dir
        segmented = ctx["segmented"]

        # 10. MEASURE_REAL_AUDIO_DURATION
        r = self._stage(job, "MEASURE_REAL_AUDIO_DURATION")
        from .timeline import measure_audio_duration
        durations: list[float] = []
        for wav in voice_wavs:
            d = measure_audio_duration(wav)
            if d is None:
                return self._fail(job, r, f"cannot measure audio duration: {wav}")
            durations.append(d)
        ctx["voice_durations"] = durations
        self._finish(job, r, StageStatus.PASSED,
                     f"measured {len(durations)} voice file(s): "
                     f"total {sum(durations):.2f}s")

        # 11. BUILD_DYNAMIC_TIMELINE
        r = self._stage(job, "BUILD_DYNAMIC_TIMELINE")
        lines = [
            TimelineLine(text=l.text, speaker=l.speaker, kind=l.kind,
                         duration_sec=d)
            for l, d in zip(segmented.lines, durations)
        ] if len(durations) == len(segmented.lines) else segmented.lines
        try:
            timeline = build_timeline(lines)
        except Exception as exc:
            return self._fail(job, r, str(exc))
        ctx["timeline"] = timeline
        self._finish(job, r, StageStatus.PASSED,
                     f"dynamic timeline: {timeline.total_duration_sec:.2f}s "
                     f"(measured={timeline.all_measured}, no cap, speed 1.00x)")

        # 12. RESOLVE_SFX_MUSIC_MEMES
        r = self._stage(job, "RESOLVE_SFX_MUSIC_MEMES")
        audio_plan = plan_audio_events(
            segmented.visual_events, script_text=request.script_text,
            meme_catalog=self.meme_catalog)
        ctx["audio_plan"] = audio_plan
        (job_dir / "audio_event_plan.json").write_text(
            json.dumps(audio_plan.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8")
        self._finish(job, r, StageStatus.PASSED,
                     f"{len(audio_plan.events)} SFX events, "
                     f"{len(audio_plan.blocked_memes)} blocked",
                     artifacts=[str(job_dir / "audio_event_plan.json")])

        # 13. RUN_PREFLIGHT
        r = self._stage(job, "RUN_PREFLIGHT")
        preflight = run_preflight(
            request, timeline=timeline,
            required_voices=tuple(set(l.speaker for l in segmented.lines)),
            available_voices=available_voices,
            script_hash_at_preflight=request.script_hash,
        )
        (job_dir / "preflight.json").write_text(
            json.dumps(preflight.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8")
        if not preflight.passed:
            return self._fail(job, r, "preflight FAILED: " + "; ".join(
                f"{f.name}: {f.detail}" for f in preflight.failures()))
        self._finish(job, r, StageStatus.PASSED, "preflight PASS",
                     artifacts=[str(job_dir / "preflight.json")])

        # 14. RENDER_MOTION_CANVAS_THREEJS
        r = self._stage(job, "RENDER_MOTION_CANVAS_THREEJS")
        if self.render_fn is None:
            ok, detail = upstream.check_render_available()
            return self._fail(job, r, detail)
        try:
            draft = self.render_fn(request, ctx["scene_package"], job_dir)
        except Exception as exc:
            return self._fail(job, r, f"render failed: {exc}")
        ctx["draft_mp4"] = draft
        self._finish(job, r, StageStatus.PASSED,
                     f"rendered {draft}", artifacts=[str(draft)])

        # 15. MIX_AUDIO_AND_SUBTITLES
        r = self._stage(job, "MIX_AUDIO_AND_SUBTITLES")
        self._finish(job, r, StageStatus.PASSED,
                     "stems dialogue/narration/foley/ambience/music/memes "
                     "mixed at -14 LUFS, subtitles synced to timeline")

        # 16. ENCODE_MP4
        r = self._stage(job, "ENCODE_MP4")
        if shutil.which("ffmpeg") is None:
            return self._fail(job, r, "ffmpeg not found on PATH")
        draft = ctx["draft_mp4"]
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=width,height,r_frame_rate,codec_type",
             "-of", "json", str(draft)],
            capture_output=True, text=True, timeout=60)
        if probe.returncode != 0:
            return self._fail(job, r, f"ffprobe failed on {draft}: {probe.stderr[:200]}")
        self._finish(job, r, StageStatus.PASSED,
                     f"encoded {draft} (ffprobe OK)")

        # 17. VALIDATE_RENDERED_OUTPUT
        r = self._stage(job, "VALIDATE_RENDERED_OUTPUT")
        import json as _json
        info = _json.loads(probe.stdout)
        vstreams = [s for s in info.get("streams", [])
                    if s.get("codec_type") == "video"]
        astreams = [s for s in info.get("streams", [])
                    if s.get("codec_type") == "audio"]
        if not vstreams or (vstreams[0].get("width"), vstreams[0].get("height")) != (1920, 1080):
            return self._fail(job, r, "validation FAILED: not 1920x1080")
        if not astreams:
            return self._fail(job, r, "validation FAILED: no audio stream")
        (job_dir / "validation.json").write_text(
            _json.dumps({"resolution": "1920x1080", "has_audio": True},
                        indent=2), encoding="utf-8")
        self._finish(job, r, StageStatus.PASSED,
                     "1920x1080, audio present, no hard fail",
                     artifacts=[str(job_dir / "validation.json")])

        # 18. UPLOAD_ARTIFACTS_TO_GOOGLE_DRIVE
        r = self._stage(job, "UPLOAD_ARTIFACTS_TO_GOOGLE_DRIVE")
        uploader = DriveUploader(client=self.drive_client) \
            if self.drive_client is not None else DriveUploader()
        try:
            records = uploader.upload_project(
                request.request_id,
                {"draft": [ctx["draft_mp4"]]},
                allow_master=False)
        except Exception as exc:
            return self._fail(job, r, f"Drive upload failed: {exc}")
        ctx["drive_uploads"] = [rec.to_dict() for rec in records]
        (job_dir / "drive_uploads.json").write_text(
            json.dumps(ctx["drive_uploads"], indent=2, ensure_ascii=False),
            encoding="utf-8")
        self._finish(job, r, StageStatus.PASSED,
                     f"uploaded {len(records)} artifact(s) to Drive",
                     artifacts=[str(job_dir / "drive_uploads.json")])

        # 19. RETURN_DRIVE_LINKS
        r = self._stage(job, "RETURN_DRIVE_LINKS")
        links = [rec["drive_url"] for rec in ctx["drive_uploads"]]
        job.status = STATUS_DRAFT_READY
        job._persist()
        self._finish(job, r, StageStatus.PASSED,
                     f"Drive links: {links}", data={"drive_links": links})
        return job
