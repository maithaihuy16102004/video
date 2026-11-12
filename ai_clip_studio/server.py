"""AI Clip Studio product server (stdlib only, no new deps).

Run:  GEMINI_API_KEY=... python -m ai_clip_studio.server [--port 8788]
      (from ~/workspace/video-16x9-v2/)

Implements Mai's "luồng chuẩn" (standard flow) end to end:

  [1] Dán kịch bản -> [2] Phân tích script -> [3] Cấu hình video
  -> [4] Storyboard preview -> [5] Preflight validation
  -> NHẤN TẠO DRAFT -> product pipeline (product_flow.py, 15 stages
  in the drawn order) -> [6] Xem video draft ->
  QA FAILED -> rerender loop / QA PASSED -> user approves -> Master.

  GET  /                                  product UI (6 steps, no build)
  POST /api/production/analyze            {script} -> plan + planner label
                                          (+ storyboard stills, async)
  GET  /api/production/analyze/{id}/storyboard
  POST /api/production/preflight          validates the REAL plan
  POST /api/production/draft              {script} -> 202 {job_id}, runs
                                          product_flow in a background thread
  GET  /api/production/jobs/{job_id}      stage-by-stage status + QA + Drive
  GET  /api/production/jobs/{job_id}/video
                                          the draft MP4 (Range supported)
  GET  /api/production/jobs/{job_id}/storyboard/{shot}
                                          storyboard still PNG
  POST /api/production/jobs/{job_id}/rerender
                                          QA FAILED -> fix & re-render loop
  POST /api/production/jobs/{job_id}/approve-master
                                          human approval gate ONLY (never
                                          automatic); re-renders Master and
                                          uploads to the root folder
  POST /api/production/jobs/{job_id}/retry-upload
                                          re-upload the existing draft MP4

The legacy 19-stage orchestrator (orchestrator.py) is NOT used by
this server anymore — the product flow is product_flow.py. The
orchestrator module stays in the repo and keeps its own tests.
"""
from __future__ import annotations

import argparse
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .drive_uploader import GwsCliDriveClient
from .gemini_planner import resolve_plan
from .preflight import run_preflight
from .product_flow import (
    TEST_FOLDER_ID, approve_master, run_product_job,
)
from .product_renderer import render_storyboard_stills
from .production_request import ProductionRequest
from .qa_gates import script_hash
from .timeline import TimelineLine, build_timeline

DEFAULT_PORT = 8788
JOBS: dict[str, dict[str, Any]] = {}
ANALYSES: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()

UI_HTML = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<title>AI Clip Studio — Luồng chuẩn</title>
<style>
body{font-family:system-ui,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#1c2333}
h1{font-size:22px} h2{font-size:17px;margin-top:28px;border-top:1px solid #ddd;padding-top:16px}
textarea{width:100%;height:180px;font-size:14px} button{padding:10px 18px;font-size:15px;margin:6px 6px 6px 0;cursor:pointer}
button:disabled{opacity:.45;cursor:not-allowed}
pre{background:#f4f4f4;padding:12px;white-space:pre-wrap;font-size:13px}
.still{width:300px;margin:6px;border:1px solid #ccc} .still p{font-size:12px;margin:4px}
video{width:100%;background:#000} .ok{color:#0a7a2f} .bad{color:#b00020}
select,input{font-size:14px;padding:6px}
</style></head><body>
<h1>🎬 AI Clip Studio — Luồng chuẩn</h1>
<p>Dán kịch bản &rarr; Phân tích &rarr; Cấu hình &rarr; Storyboard &rarr; Preflight
&rarr; <b>Tạo Draft</b> &rarr; Xem video draft &rarr; Duyệt &rarr; Master.</p>

<h2>[1] Dán kịch bản</h2>
<textarea id="script" placeholder="Dán kịch bản tiếng Việt vào đây..."></textarea>

<h2>[3] Cấu hình video</h2>
<label>Tỉ lệ: <select id="aspect"><option>16:9</option></select></label>
<label>Độ phân giải: <select id="res"><option>1920x1080</option></select></label>
<label>Ngôn ngữ: <select id="lang"><option value="vi-VN">vi-VN (tiếng Việt)</option></select></label>
<label>Phong cách: <select id="style"><option>PREMIUM_STICKMAN v4</option></select></label>
<p><small>16:9 1920&times;1080, 24fps, vi-VN là cấu hình chuẩn của sản phẩm.</small></p>

<h2>[2] Phân tích script</h2>
<button id="btnAnalyze" onclick="analyze()">Phân tích script</button>
<div id="plan"></div>

<h2>[4] Storyboard preview</h2>
<div id="board"><small>Chưa có storyboard — phân tích script trước.</small></div>

<h2>[5] Preflight validation</h2>
<button id="btnPreflight" onclick="preflight()" disabled>Kiểm tra Preflight</button>
<div id="preflight"></div>

<h2>Tạo Draft</h2>
<button id="btnDraft" onclick="createDraft()" disabled>🎬 TẠO DRAFT</button>
<div id="job"></div>

<h2>[6] Xem video draft</h2>
<div id="video"></div>
<div id="qa"></div>
<button id="btnRerender" onclick="rerender()" disabled>🔁 Sửa và render lại</button>
<button id="btnMaster" onclick="approveMaster()" disabled>✅ Duyệt — Render Master</button>
<div id="master"></div>

<script>
let analysisId=null, jobId=null, planData=null;
async function post(url, body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return {status:r.status,data:await r.json()};}
async function analyze(){
  const script=document.getElementById('script').value;
  document.getElementById('plan').innerHTML='Đang phân tích... (Gemini nếu có key, fallback nếu không)';
  const {status,data}=await post('/api/production/analyze',{script});
  if(status!==200){document.getElementById('plan').innerHTML='<span class="bad">'+(data.error||'lỗi')+'</span>';return;}
  analysisId=data.analysis_id; planData=data;
  document.getElementById('plan').innerHTML='<pre>'+JSON.stringify({planner:data.planner,planner_detail:data.planner_detail,characters:data.package.characters.map(c=>c.name),scenes:data.package.scenes.length,shots:data.package.shots.length,hook:data.package.hook||'',twist:data.package.twist||''},null,2)+'</pre>';
  document.getElementById('btnPreflight').disabled=false;
  pollBoard();
}
async function pollBoard(){
  for(let i=0;i<40;i++){
    const r=await fetch('/api/production/analyze/'+analysisId+'/storyboard');
    const d=await r.json();
    if(d.stills && d.stills.length){
      document.getElementById('board').innerHTML=d.stills.map(s=>'<div class="still"><img src="'+s.url+'" style="width:100%"><p><b>'+s.shot_type+'</b> — '+ (s.speaker||'action') +' — '+s.text.slice(0,60)+'</p></div>').join('');
      return;
    }
    await new Promise(r=>setTimeout(r,3000));
  }
  document.getElementById('board').innerHTML='<span class="bad">Storyboard chưa xong sau 2 phút.</span>';
}
async function preflight(){
  const script=document.getElementById('script').value;
  const {status,data}=await post('/api/production/preflight',{script,analysis_id:analysisId});
  const el=document.getElementById('preflight');
  if(status!==200){el.innerHTML='<span class="bad">'+(data.error||'lỗi')+'</span>';return;}
  el.innerHTML='<pre>'+JSON.stringify(data,null,2)+'</pre>';
  document.getElementById('btnDraft').disabled=!data.passed;
}
async function createDraft(){
  const script=document.getElementById('script').value;
  document.getElementById('job').innerHTML='Đang tạo draft...';
  const {status,data}=await post('/api/production/draft',{script,analysis_id:analysisId});
  if(status!==202){document.getElementById('job').innerHTML='<span class="bad">'+(data.error||'lỗi')+'</span>';return;}
  jobId=data.job_id; pollJob();
}
async function pollJob(){
  for(let i=0;i<120;i++){
    const r=await fetch('/api/production/jobs/'+jobId); const d=await r.json();
    document.getElementById('job').innerHTML='<pre>'+JSON.stringify({status:d.status,planner:d.planner,stages:d.stages.map(s=>s.stage+': '+s.status)},null,2)+'</pre>';
    if(d.status && d.status!=='queued' && d.status!=='running'){
      showVideo(d); return;
    }
    await new Promise(r=>setTimeout(r,5000));
  }
}
function showVideo(d){
  const q=d.qa||{};
  document.getElementById('video').innerHTML=d.mp4 && d.mp4.path ? '<video controls src="/api/production/jobs/'+jobId+'/video"></video><p><a href="'+(d.drive&&d.drive.url||'#')+'" target="_blank">Drive: '+(d.drive&&d.drive.file_id||'chưa upload')+'</a></p>' : '<span class="bad">Chưa có video. '+(d.errors||[]).join('; ')+'</span>';
  document.getElementById('qa').innerHTML='<pre>'+JSON.stringify({verdict:q.verdict&&q.verdict.verdict,technical:q.technical&&q.technical.status,creative:q.creative&&q.creative.status},null,2)+'</pre>';
  document.getElementById('btnRerender').disabled=!(d.status==='QA_FAILED'||d.status==='FAILED');
  document.getElementById('btnMaster').disabled=!d.mp4 || !d.mp4.path || d.status==='QA_FAILED' || d.status==='FAILED';
}
async function rerender(){
  const {status,data}=await post('/api/production/jobs/'+jobId+'/rerender',{});
  if(status===202){jobId=data.job_id; pollJob();} else {alert(data.error||'lỗi');}
}
async function approveMaster(){
  if(!confirm('Bạn đã xem draft và duyệt render Master?')) return;
  const {status,data}=await post('/api/production/jobs/'+jobId+'/approve-master',{});
  document.getElementById('master').innerHTML='<pre>'+JSON.stringify(data,null,2)+'</pre>';
}
</script></body></html>
"""


def _jobs_root() -> Path:
    return Path(__file__).resolve().parent.parent / "jobs"


def _job_dir(job_id: str) -> Path:
    return _jobs_root() / job_id


def _run_product_job(job_id: str, script: str, config: dict) -> None:
    # Live progress: the job record in JOBS is updated on every stage
    # so GET /jobs/{id} shows real stage-by-stage progress (before
    # this fix it stayed "queued, 0 stages" until the whole job
    # finished, because run_product_job only returned at the end).
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "running"

    def on_stage(name: str, status: str, detail: str = "") -> None:
        with JOBS_LOCK:
            rec = JOBS.get(job_id)
            if rec is not None:
                rec.setdefault("stages", []).append(
                    {"stage": name, "status": status, "detail": detail})
                rec["status"] = "running"

    job = run_product_job(script, _job_dir(job_id), config=config,
                          job_id=job_id, on_stage=on_stage)
    with JOBS_LOCK:
        JOBS[job_id] = job.to_dict()


def _render_storyboard_bg(analysis_id: str, script: str) -> None:
    try:
        package = ANALYSES[analysis_id]["package"]
        # Estimated durations for the stills (real TTS is not run at
        # the preview step — stills show the planned shots, not the
        # final timing).
        est = [{"line_index": i + 1, "duration": 4.0}
               for i in range(sum(len(s["lines"])
                                for s in package["scenes"]))]
        out = _jobs_root() / analysis_id / "storyboard"
        stills = render_storyboard_stills(package, est, out)
        with JOBS_LOCK:
            ANALYSES[analysis_id]["stills"] = [
                {"shot_type": s["shot_type"], "speaker": s.get("speaker"),
                 "text": "", "url": f"/api/production/jobs/{analysis_id}"
                                   f"/storyboard/shot_{s['index']:03d}/still.png"}
                for s in stills]
            ANALYSES[analysis_id]["storyboard_status"] = "done"
    except Exception as exc:  # noqa: BLE001 - record, never crash the server
        with JOBS_LOCK:
            ANALYSES[analysis_id]["storyboard_status"] = f"failed: {exc}"


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

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            return self._send({"error": f"file not found: {path.name}"}, 404)
        size = path.stat().st_size
        range_hdr = self.headers.get("Range")
        if range_hdr and content_type.startswith("video/"):
            m = re.match(r"bytes=(\d+)-(\d*)", range_hdr)
            if m:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
                end = min(end, size - 1)
                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Range",
                                 f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with open(path, "rb") as fh:
                    fh.seek(start)
                    self.wfile.write(fh.read(end - start + 1))
                return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def _job_or_404(self, job_id: str) -> dict[str, Any] | None:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if job is None:
            job_file = _job_dir(job_id) / "job.json"
            if job_file.exists():
                job = json.loads(job_file.read_text(encoding="utf-8"))
                with JOBS_LOCK:
                    JOBS[job_id] = job
        if job is None:
            self._send({"error": f"job not found: {job_id}"}, 404)
            return None
        return job

    # -- routing ------------------------------------------------------
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            body = UI_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/health":
            return self._send({"status": "ok", "service": "ai_clip_studio",
                               "flow": "luong_chuan"})
        m = re.match(r"^/api/production/analyze/([^/]+)/storyboard$", self.path)
        if m:
            with JOBS_LOCK:
                analysis = ANALYSES.get(m.group(1))
            if analysis is None:
                return self._send({"error": "analysis not found"}, 404)
            # Attach the shot texts from the package for the preview.
            stills = analysis.get("stills") or []
            shots = analysis["package"].get("shots", [])
            for still, shot in zip(stills, shots):
                still["text"] = shot.get("text", "")
            return self._send({
                "analysis_id": m.group(1),
                "status": analysis.get("storyboard_status", "running"),
                "stills": stills})
        m = re.match(r"^/api/production/jobs/([^/]+)/video$", self.path)
        if m:
            job = self._job_or_404(m.group(1))
            if job is None:
                return
            mp4 = job.get("mp4", {}).get("path", "")
            if not mp4:
                return self._send({"error": "no video for this job"}, 404)
            return self._send_file(Path(mp4), "video/mp4")
        m = re.match(r"^/api/production/jobs/([^/]+)/storyboard/shot_(\d+)/still\.png$",
                     self.path)
        if m:
            path = (_jobs_root() / m.group(1) / "storyboard"
                    / f"shot_{m.group(2)}" / "still.png")
            return self._send_file(path, "image/png")
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
            artifacts = [str(p) for p in
                         sorted(Path(_job_dir(m.group(1))).rglob("*"))
                         if p.is_file()]
            return self._send({"job_id": m.group(1), "artifacts": artifacts})
        self._send({"error": "not found"}, 404)

    def do_POST(self) -> None:
        body = self._read_json()

        if self.path == "/api/production/analyze":
            script = str(body.get("script", "") or "")
            if len(script.strip()) < 10:
                return self._send({"error": "script too short (min 10 chars)"}, 400)
            try:
                package, planner, detail = resolve_plan(script)
            except Exception as exc:  # noqa: BLE001
                return self._send({"error": f"analysis failed: {exc}"}, 500)
            analysis_id = "analysis-" + uuid.uuid4().hex[:10]
            with JOBS_LOCK:
                ANALYSES[analysis_id] = {
                    "analysis_id": analysis_id, "package": package,
                    "planner": planner, "planner_detail": detail,
                    "storyboard_status": "running", "stills": []}
            (_jobs_root() / analysis_id).mkdir(parents=True, exist_ok=True)
            threading.Thread(target=_render_storyboard_bg,
                             args=(analysis_id, script), daemon=True).start()
            return self._send({
                "analysis_id": analysis_id,
                "script_hash": script_hash(script),
                "planner": planner, "planner_detail": detail,
                "package": package,
                "note": "planner is 'gemini' only when a real Gemini call "
                        "produced the plan; 'fallback' is the labelled "
                        "local planner."})

        if self.path == "/api/production/preflight":
            script = str(body.get("script", "") or "")
            if len(script.strip()) < 10:
                return self._send({"error": "script too short (min 10 chars)"}, 400)
            # Validate the REAL plan from the analyze step when given,
            # otherwise plan it now (same code path, no hardcoding).
            analysis_id = body.get("analysis_id")
            package = None
            planner = None
            with JOBS_LOCK:
                if analysis_id and analysis_id in ANALYSES:
                    package = ANALYSES[analysis_id]["package"]
                    planner = ANALYSES[analysis_id]["planner"]
            if package is None:
                try:
                    package, planner, _ = resolve_plan(script)
                except Exception as exc:  # noqa: BLE001
                    return self._send({"error": f"analysis failed: {exc}"}, 500)
            request = ProductionRequest(script_text=script)
            flat = [TimelineLine(speaker=l["speaker"], kind=l["kind"],
                                 text=l["text"])
                    for s in package["scenes"] for l in s["lines"]]
            if not flat:
                return self._send({"passed": False, "checks": [
                    {"name": "has_spoken_lines", "passed": False,
                     "detail": "no spoken lines found in the script"}]})
            timeline = build_timeline(flat)
            from .language_gate import resolve_voice
            from .tts_cli_provider import voice_for
            hints = {c["name"]: c.get("voice_hint", "")
                     for c in package["characters"]}
            # available_voices are SPEAKER names for whom a Vietnamese
            # voice resolves (resolve_voice raises instead of falling
            # back to English — a speaker with no vi voice fails here).
            available = []
            for speaker in {l.speaker for l in flat}:
                try:
                    resolve_voice("vi-VN", speaker,
                                  hints.get(speaker, ""))
                    available.append(speaker)
                except ValueError:
                    pass
            result = run_preflight(
                request, timeline=timeline,
                required_voices=tuple({l.speaker for l in flat}),
                available_voices=tuple(available),
                script_hash_at_preflight=request.script_hash,
                allow_estimated_timeline=True)
            checks = result.to_dict()["checks"]
            # Generic plan checks (no Episode01/Munich/Eiffel hardcoding):
            checks.append({"name": "plan_has_scenes", "passed": bool(package["scenes"]),
                           "detail": f"{len(package['scenes'])} scene(s)"})
            checks.append({"name": "plan_has_characters", "passed": bool(package["characters"]),
                           "detail": f"{len(package['characters'])} character(s): "
                                     f"{', '.join(c['name'] for c in package['characters'])}"})
            checks.append({"name": "plan_has_shots", "passed": bool(package["shots"]),
                           "detail": f"{len(package['shots'])} shot(s) planned"})
            checks.append({"name": "plan_has_hook_and_twist",
                           "passed": bool(package.get("hook") and package.get("twist")),
                           "detail": "hook + twist identified by the planner"
                                     if package.get("hook") and package.get("twist")
                                     else "hook or twist missing — story may lack a surprise ending"})
            passed = result.passed and all(c["passed"] for c in checks)
            return self._send({"passed": passed, "planner": planner,
                               "checks": checks})

        if self.path == "/api/production/draft":
            script = str(body.get("script", "") or "")
            if len(script.strip()) < 10:
                return self._send({"error": "script too short (min 10 chars)"}, 400)
            request = ProductionRequest(script_text=script)
            job_id = request.request_id
            config = {"language": str(body.get("language", "vi-VN")),
                      "aspect_ratio": str(body.get("aspect_ratio", "16:9")),
                      "analysis_id": body.get("analysis_id")}
            with JOBS_LOCK:
                JOBS[job_id] = {"job_id": job_id, "status": "queued",
                                "request_id": job_id,
                                "script_hash": request.script_hash,
                                "stages": []}
            threading.Thread(target=_run_product_job,
                             args=(job_id, script, config), daemon=True).start()
            return self._send({"job_id": job_id, "status": "queued",
                               "script_hash": request.script_hash}, 202)

        m = re.match(r"^/api/production/jobs/([^/]+)/rerender$", self.path)
        if m:
            job = self._job_or_404(m.group(1))
            if job is None:
                return
            if job.get("status") not in ("QA_FAILED", "FAILED"):
                return self._send({
                    "error": "rerender is only for QA_FAILED / FAILED jobs",
                    "status": job.get("status")}, 409)
            script = Path(_job_dir(m.group(1)) / "script.txt").read_text(
                encoding="utf-8")
            new_id = ProductionRequest(script_text=script).request_id
            with JOBS_LOCK:
                JOBS[new_id] = {"job_id": new_id, "status": "queued",
                                "loop_of": m.group(1),
                                "script_hash": job.get("script_hash"),
                                "stages": []}
            threading.Thread(target=_run_product_job,
                             args=(new_id, script, {"loop_of": m.group(1)}),
                             daemon=True).start()
            return self._send({"job_id": new_id, "status": "queued",
                               "loop_of": m.group(1)}, 202)

        m = re.match(r"^/api/production/jobs/([^/]+)/approve-master$", self.path)
        if m:
            job = self._job_or_404(m.group(1))
            if job is None:
                return
            if job.get("status") in ("QA_FAILED", "FAILED", "queued", "running"):
                return self._send({
                    "error": "cannot approve: draft is not ready for review",
                    "status": job.get("status")}, 409)
            if not job.get("mp4", {}).get("path"):
                return self._send({"error": "no draft video to master"}, 409)
            # Master renders in a background thread (same flow, master
            # bitrate, upload to the root folder). The UI polls the job.
            from .product_flow import ProductJob
            script = Path(_job_dir(m.group(1)) / "script.txt").read_text(
                encoding="utf-8")
            pj = ProductJob(job_id=m.group(1), script=script,
                            script_hash=job.get("script_hash", ""),
                            job_dir=_job_dir(m.group(1)),
                            status=job.get("status", ""))
            pj.mp4_path = job.get("mp4", {}).get("path", "")
            pj.mp4_size = job.get("mp4", {}).get("size_bytes", 0)

            def _do_master(job_id: str, pj: ProductJob):
                try:
                    approve_master(pj)
                except Exception as exc:  # noqa: BLE001
                    with JOBS_LOCK:
                        JOBS[job_id]["master_error"] = str(exc)[:300]
                    return
                with JOBS_LOCK:
                    JOBS[job_id]["status"] = "MASTER_UPLOADED"
                    JOBS[job_id]["master"] = pj.master

            with JOBS_LOCK:
                JOBS[m.group(1)]["status"] = "MASTER_RENDERING"
            threading.Thread(target=_do_master, args=(m.group(1), pj),
                             daemon=True).start()
            return self._send({"job_id": m.group(1),
                               "status": "MASTER_RENDERING"}, 202)

        m = re.match(r"^/api/production/jobs/([^/]+)/retry-upload$", self.path)
        if m:
            job = self._job_or_404(m.group(1))
            if job is None:
                return
            mp4 = job.get("mp4", {}).get("path", "")
            if not mp4 or not Path(mp4).exists():
                return self._send({"error": "no draft video to upload"}, 409)
            try:
                client = GwsCliDriveClient()
                rec = client.upload_file(Path(mp4), TEST_FOLDER_ID)
                file_id = rec.get("id", "")
                remote = client.get_file(file_id) if file_id else {}
                if not file_id or int(remote.get("size") or 0) != Path(mp4).stat().st_size:
                    raise RuntimeError("Drive verification failed")
                with JOBS_LOCK:
                    JOBS[m.group(1)]["drive"] = {
                        "file_id": file_id,
                        "url": f"https://drive.google.com/file/d/{file_id}/view",
                        "size_bytes": int(remote.get("size") or 0),
                        "folder": TEST_FOLDER_ID}
                return self._send({"job_id": m.group(1),
                                   "status": "uploaded",
                                   "drive": JOBS[m.group(1)]["drive"]})
            except Exception as exc:  # noqa: BLE001
                return self._send({"error": f"retry-upload failed: {exc}"}, 500)

        self._send({"error": "not found"}, 404)


def main() -> None:
    ap = argparse.ArgumentParser(description="AI Clip Studio product API")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--jobs-dir", default=None)
    args = ap.parse_args()
    if args.jobs_dir:
        global _jobs_root
        root = Path(args.jobs_dir)
        _jobs_root = lambda: root  # type: ignore[assignment]
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"AI Clip Studio product API: http://127.0.0.1:{args.port}")
    print("Flow: [1] paste -> [2] analyze -> [3] config -> [4] storyboard "
          "-> [5] preflight -> TAO DRAFT -> pipeline -> [6] watch draft")
    print("Endpoints: /api/production/analyze, /api/production/preflight, "
          "/api/production/draft, /api/production/jobs/{id}, "
          "/api/production/jobs/{id}/video, "
          "/api/production/jobs/{id}/rerender, "
          "/api/production/jobs/{id}/approve-master, "
          "/api/production/jobs/{id}/retry-upload")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
