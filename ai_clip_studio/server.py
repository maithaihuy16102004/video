"""AI Clip Studio production API server (stdlib only, no new deps).

Run:  python -m ai_clip_studio.server [--port 8788] [--jobs-dir <dir>]
      (from ~/workspace/video-16x9-v2/)

Endpoints (new, additive — they do NOT replace the real backend):
    POST /api/production/analyze
         {script} -> scene package planning (stages 1-8, via orchestrator
         planning path) — maps to upstream POST /api/story-world and
         POST /api/v1/studio-script (see FRONTEND_WIRING.md).
    POST /api/production/preflight
         {script} -> preflight verdict.
    POST /api/production/draft
         {script} -> returns {job_id} immediately, runs the 19-stage
         orchestrator in a background thread. Maps to upstream
         POST /api/render (which returns {id, status: queued} the same way).
    GET  /api/production/jobs/{job_id}
         -> job status + per-stage results (persistent status.json).
         Maps to upstream GET /api/status?id=.
    GET  /api/production/jobs/{job_id}/artifacts
         -> list of intermediate artifacts produced so far.
    POST /api/production/jobs/{job_id}/approve-master
         -> human approval gate; only then may a draft become a Master.
    POST /api/production/jobs/{job_id}/retry-upload
         -> retry the Drive upload without re-rendering.

The real backend is pipeline/studio_api.py on 127.0.0.1:8787 with
the same job pattern (STATE dict + worker threads + /api/render).
This server is the additive orchestrator front-end for it; on this
Linux VM the render stages fail honestly (no Chrome / VieNeu /
Gemini key) — see orchestrator.py.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .orchestrator import UniversalProductionPipeline, STAGES
from .pipeline import segment_script
from .preflight import run_preflight
from .production_request import ProductionRequest
from .timeline import build_timeline

DEFAULT_PORT = 8788
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def _jobs_root() -> Path:
    return Path(__file__).resolve().parent.parent / "jobs"


def _pipeline() -> UniversalProductionPipeline:
    return UniversalProductionPipeline(_jobs_root())


def _run_job(job_id: str, script: str, language: str, aspect: str) -> None:
    pipeline = _pipeline()
    job = pipeline.run(script, language=language, aspect_ratio=aspect,
                       request_id=job_id)
    with JOBS_LOCK:
        JOBS[job_id] = job.to_dict()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # keep stdout clean
        pass

    # -- helpers ------------------------------------------------------
    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _send(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _job_or_404(self, job_id: str) -> dict[str, Any] | None:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if job is None:
            # Also look for a persisted job on disk.
            status_file = _jobs_root() / job_id / "status.json"
            if status_file.exists():
                job = json.loads(status_file.read_text(encoding="utf-8"))
                with JOBS_LOCK:
                    JOBS[job_id] = job
        if job is None:
            self._send({"error": f"job not found: {job_id}"}, 404)
            return None
        return job

    # -- routing ------------------------------------------------------
    def do_GET(self) -> None:
        if self.path == "/health":
            return self._send({"status": "ok", "service": "ai_clip_studio"})
        m = re.match(r"^/api/production/jobs/([^/]+)$", self.path)
        if m:
            job = self._job_or_404(m.group(1))
            if job is not None:
                self._send(job)
            return
        m = re.match(r"^/api/production/jobs/([^/]+)/artifacts$", self.path)
        if m:
            job = self._job_or_404(m.group(1))
            if job is None:
                return
            artifacts: list[str] = []
            for stage in job.get("stages", []):
                artifacts.extend(stage.get("artifacts", []))
            return self._send({"job_id": m.group(1), "artifacts": artifacts})
        self._send({"error": "not found"}, 404)

    def do_POST(self) -> None:
        body = self._read_json()

        if self.path == "/api/production/analyze":
            script = str(body.get("script", "") or "")
            if len(script.strip()) < 10:
                return self._send({"error": "script too short (min 10 chars)"}, 400)
            segmented = segment_script(script)
            return self._send({
                "request_id": ProductionRequest(script_text=script).request_id,
                "script_hash": ProductionRequest(script_text=script).script_hash,
                "characters": segmented.characters,
                "sentence_count": len(segmented.sentences),
                "visual_events": segmented.visual_events,
                "note": "Planning stages 1-8 run inside the orchestrator; "
                        "full Gemini planning needs GEMINI_API_KEY on the "
                        "Windows machine.",
            })

        if self.path == "/api/production/preflight":
            script = str(body.get("script", "") or "")
            request = ProductionRequest(script_text=script)
            segmented = segment_script(script)
            timeline = build_timeline(segmented.lines)
            result = run_preflight(
                request, timeline=timeline,
                required_voices=tuple(set(l.speaker for l in segmented.lines)),
                available_voices=tuple(body.get("available_voices", ["narrator"])),
                script_hash_at_preflight=request.script_hash,
                allow_estimated_timeline=bool(body.get("allow_estimated_timeline", False)),
            )
            return self._send(result.to_dict())

        if self.path == "/api/production/draft":
            script = str(body.get("script", "") or "")
            if len(script.strip()) < 10:
                return self._send({"error": "script too short (min 10 chars)"}, 400)
            request = ProductionRequest(script_text=script)
            job_id = request.request_id
            with JOBS_LOCK:
                JOBS[job_id] = {"job_id": job_id, "status": "IMPLEMENTATION_IN_PROGRESS",
                                "request_id": job_id, "script_hash": request.script_hash,
                                "stages": []}
            thread = threading.Thread(
                target=_run_job,
                args=(job_id, script, str(body.get("language", "vi-VN")),
                      str(body.get("aspect_ratio", "16:9"))),
                daemon=True)
            thread.start()
            return self._send({"job_id": job_id, "status": "queued",
                               "script_hash": request.script_hash}, 202)

        m = re.match(r"^/api/production/jobs/([^/]+)/approve-master$", self.path)
        if m:
            job = self._job_or_404(m.group(1))
            if job is None:
                return
            if job.get("status") != "END_TO_END_DRAFT_READY_FOR_REVIEW":
                return self._send({
                    "error": "cannot approve: draft is not ready for review",
                    "status": job.get("status")}, 409)
            with JOBS_LOCK:
                JOBS[m.group(1)]["status"] = "MASTER_APPROVED_AND_UPLOADED"
                JOBS[m.group(1)]["master_approved"] = True
            return self._send({"job_id": m.group(1),
                               "status": "MASTER_APPROVED_AND_UPLOADED"})

        m = re.match(r"^/api/production/jobs/([^/]+)/retry-upload$", self.path)
        if m:
            job = self._job_or_404(m.group(1))
            if job is None:
                return
            return self._send({
                "job_id": m.group(1),
                "status": "retry-upload not implemented yet — re-run the "
                          "orchestrator's UPLOAD stage from the persisted "
                          "job dir; see FRONTEND_WIRING.md",
            }, 501)

        self._send({"error": "not found"}, 404)


def main() -> None:
    ap = argparse.ArgumentParser(description="AI Clip Studio production API")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--jobs-dir", default=None)
    args = ap.parse_args()
    if args.jobs_dir:
        global _jobs_root
        root = Path(args.jobs_dir)
        _jobs_root = lambda: root  # type: ignore[assignment]
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"AI Clip Studio API: http://127.0.0.1:{args.port}")
    print("Endpoints: /api/production/analyze, /api/production/preflight, "
          "/api/production/draft, /api/production/jobs/{id}, "
          "/api/production/jobs/{id}/artifacts, "
          "/api/production/jobs/{id}/approve-master, "
          "/api/production/jobs/{id}/retry-upload")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
