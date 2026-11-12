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
  POST /api/production/validate           {script} -> STUDIO SCRIPT V1
                                          validation + human-readable review
                                          (422 with line-numbered errors for
                                          invalid V1; free-form scripts get a
                                          freeform note and are never blocked)
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
from .studio_script_v1 import (
    NARRATOR_ALIASES,
    detect_format,
    parse_studio_script_v1,
)
from .studio_script_v1_adapter import SUPPORTED_CUES, V1AdapterError
from .timeline import TimelineLine, build_timeline
from .vi_script_parser import extract_action_cues

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
.errbox{border:2px solid #b00020;background:#fff5f5;padding:10px;margin:8px 0}
.warnbox{border:2px solid #b87400;background:#fffaf0;padding:10px;margin:8px 0}
.rev h3{font-size:15px;margin:14px 0 4px} .rev ul{margin:4px 0} .rev li{font-size:13px;margin:2px 0}
.rev .hash{font-size:12px;word-break:break-all}
</style></head><body>
<h1>🎬 AI Clip Studio — Luồng chuẩn</h1>
<p>Dán kịch bản &rarr; Phân tích &rarr; Cấu hình &rarr; Storyboard &rarr; Preflight
&rarr; <b>Tạo Draft</b> &rarr; Xem video draft &rarr; Duyệt &rarr; Master.</p>

<h2>[1] Dán kịch bản</h2>
<textarea id="script" placeholder="Dán kịch bản tiếng Việt vào đây..."></textarea>

<h2>Kiểm tra kịch bản V1</h2>
<p><small>Xem lại trước khi sản xuất: kiểm tra định dạng STUDIO SCRIPT V1, xem nhân vật / bối cảnh / đạo cụ / cảnh / shot / lời thoại / âm thanh, và lỗi kèm số dòng. Kịch bản tự do không bị chặn ở bước này.</small></p>
<button id="btnValidate" onclick="validateScript()">Kiểm tra kịch bản V1</button>
<div id="validateStale"></div>
<div id="validation" class="rev"></div>

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
<div id="draftGate"></div>
<div id="job"></div>

<h2>[6] Xem video draft</h2>
<div id="video"></div>
<div id="qa"></div>
<div id="artifacts"></div>
<button id="btnRerender" onclick="rerender()" disabled>🔁 Sửa và render lại</button>
<button id="btnMaster" onclick="approveMaster()" disabled>✅ Duyệt — Render Master</button>
<div id="master"></div>

<script>
let analysisId=null, jobId=null, planData=null;
let v1Check=null, preflightPassed=false;
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function looksV1(t){return /#\\s*STUDIO\\s+SCRIPT\\s+V1/i.test(t)||(/^PROJECT\\s*:/im.test(t)&&/SCENE\\s+\\d+\\s*:/i.test(t));}
function refreshDraftButton(){
  const script=document.getElementById('script').value;
  const blocked=v1Check&&v1Check.script===script&&v1Check.format==='studio_script_v1'&&!v1Check.valid;
  document.getElementById('btnDraft').disabled=!(preflightPassed&&!blocked);
  document.getElementById('draftGate').innerHTML=blocked?'<span class="bad">Kịch bản V1 còn lỗi — sửa kịch bản rồi bấm “Kiểm tra kịch bản V1” lại trước khi tạo Draft.</span>':'';
}
document.getElementById('script').addEventListener('input',function(){
  const script=document.getElementById('script').value;
  document.getElementById('validateStale').innerHTML=(v1Check&&v1Check.script!==script)?'<small class="bad">Kịch bản đã thay đổi — snapshot mới cần kiểm tra lại.</small>':'';
  refreshDraftButton();
});
async function post(url, body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return {status:r.status,data:await r.json()};}
async function validateScript(){
  const script=document.getElementById('script').value;
  const el=document.getElementById('validation');
  el.innerHTML='Đang kiểm tra...';
  const {status,data}=await post('/api/production/validate',{script});
  if(status===400){el.innerHTML='<span class="bad">'+esc(data.error||'lỗi')+'</span>';return;}
  v1Check={script:script,format:data.format,valid:data.valid};
  document.getElementById('validateStale').innerHTML='';
  el.innerHTML=renderValidation(data);
  refreshDraftButton();
}
var FIELD_LABELS={name:'Tên',id:'ID',role:'Vai trò',appearance:'Ngoại hình',traits:'Đặc điểm',costume:'Trang phục',costume_changes:'Đổi trang phục',voice:'Giọng đọc',voice_style:'Phong cách giọng',voice_id:'Voice ID',voice_engine:'Voice engine',head_ratio:'head_ratio',identity_id:'Identity ID',period:'Thời kỳ',geography:'Địa lý',architecture:'Kiến trúc',features:'Đặc điểm',foreground:'Foreground',midground:'Midground',background:'Background',lighting:'Ánh sáng',weather:'Thời tiết',palette:'Bảng màu',forbidden:'Cấm',description:'Mô tả',owner:'Chủ sở hữu',interactions:'Tương tác',title:'Tiêu đề',location_text:'Bối cảnh',location_ref:'Location ref',time_of_day:'Thời gian trong ngày',mood:'Mood',duration:'Thời lượng',visual:'Visual',actions:'Hành động',action_cues:'Action cues',dropped_action_cues:'Action cues bị loại',camera:'Camera',camera_movement:'Chuyển động camera',subject:'Chủ thể',type:'Loại',expression:'Biểu cảm',expressions:'Biểu cảm',transition:'Chuyển cảnh',speaker:'Người nói',kind:'Loại dòng',text:'Nội dung',voice_note:'Ghi chú giọng',line_id:'LINE_ID',shot_id:'Shot',cue_type:'Loại cue',trigger:'Trigger',priority:'Ưu tiên',mode:'Mode',intensity:'Cường độ',gain_db:'Gain (dB)',source_key:'Khóa gốc',project:'Project',project_id:'Project ID',language:'Ngôn ngữ',genre:'Thể loại',visual_style:'Phong cách visual',aspect_ratio:'Tỉ lệ',target_duration:'Thời lượng mục tiêu',tone:'Tone',meme_policy:'Chính sách meme',meme_max_per_minute:'Meme tối đa/phút',storytelling_mode:'Chế độ kể chuyện',primary_character:'Nhân vật chính (ngôi thứ nhất)',external_narrator:'Người dẫn truyện ngoài',key:'Khóa',value:'Giá trị',context:'Ngữ cảnh',line:'Dòng'};
function lbl(k){return FIELD_LABELS[k]||k;}
function fmtVal(v,depth){
  if(v==null||v==='')return '—';
  if(Array.isArray(v)){if(!v.length)return '—';return v.map(function(x){return fmtVal(x,(depth||0)+1);}).join('; ');}
  if(typeof v==='object'){var keys=Object.keys(v);if(!keys.length)return '—';if((depth||0)>=1)return keys.map(function(k){return lbl(k)+': '+fmtVal(v[k],(depth||0)+1);}).join('; ');return '<ul>'+keys.map(function(k){return '<li><b>'+esc(lbl(k))+':</b> '+fmtVal(v[k],(depth||0)+1)+'</li>';}).join('')+'</ul>';}
  return esc(v);
}
function kvList(obj,skip){
  skip=skip||{};
  var keys=Object.keys(obj||{}).filter(function(k){return !skip[k]&&obj[k]!=null&&obj[k]!=='';});
  if(!keys.length)return '';
  return '<ul>'+keys.map(function(k){return '<li><b>'+esc(lbl(k))+':</b> '+fmtVal(obj[k],0)+'</li>';}).join('')+'</ul>';
}
function cueLine(c){return '<b>'+esc(c.cue_type||'')+'</b>: '+esc(c.name||'')+kvList(c,{cue_type:1,name:1,line:1,scene_number:1,shot_id:1});}
function renderValidation(d){
  if(d.format==='freeform'){
    return '<p class="ok">'+esc(d.note||'Kịch bản tự do.')+'</p><p class="hash">Snapshot hash: <code>'+esc(d.snapshot_hash||'')+'</code></p>';
  }
  const s=d.summary||{}, r=d.review||{};
  let h='';
  if(d.errors&&d.errors.length){
    h+='<div class="errbox"><b class="bad">Kịch bản V1 chưa hợp lệ — '+d.errors.length+' lỗi (sửa trước khi render):</b><ul>'+d.errors.map(function(e){return '<li>Dòng '+e.line+' ['+esc(e.code)+']: '+esc(e.message)+'</li>';}).join('')+'</ul></div>';
  } else {
    h+='<p class="ok">✓ Kịch bản V1 hợp lệ.</p>';
  }
  if(d.warnings&&d.warnings.length){
    h+='<div class="warnbox"><b>Cảnh báo:</b><ul>'+d.warnings.map(function(e){return '<li>Dòng '+e.line+' ['+esc(e.code)+']: '+esc(e.message)+'</li>';}).join('')+'</ul></div>';
  }
  h+='<p class="hash">Snapshot hash (SHA-256 của đúng văn bản đã dán, dùng xuyên suốt pipeline — sửa kịch bản sẽ tạo snapshot mới): <code>'+esc(d.snapshot_hash||'')+'</code></p>';
  h+='<p><small>Xem lại kỹ nội dung bên dưới trước khi sản xuất. '+(s.characters||0)+' nhân vật · '+(s.locations||0)+' bối cảnh · '+(s.props||0)+' đạo cụ · '+(s.scenes||0)+' cảnh · '+(s.shots||0)+' shot · '+(s.spoken_lines||0)+' dòng thoại'+(s.external_narrator_lines!=null?' · dòng narrator ngoài: '+s.external_narrator_lines:'')+'.</small></p>';
  const nc=r.narrator_check||{};
  const ext=nc.external_narrator;
  const extNone=String(ext).toUpperCase()==='NONE';
  h+='<h3>Chế độ kể chuyện &amp; người dẫn truyện</h3>';
  h+='<p><b>Người dẫn truyện ngoài (EXTERNAL_NARRATOR): <span class="'+(extNone?'ok':'')+'">'+(ext==null||ext===''?'không khai báo':esc(ext))+'</span></b>'+(extNone?' — bắt buộc: không có người dẫn truyện ngoài.':'')+'</p>';
  h+='<p>Số dòng narrator ngoài: <b>'+(nc.external_narrator_lines==null?'?':nc.external_narrator_lines)+'</b> (kỳ vọng 0 với kịch bản ngôi thứ nhất) · Narration: '+(nc.narration_lines||0)+' · Dialogue: '+(nc.dialogue_lines||0)+'</p>';
  if(nc.storytelling_mode)h+='<p>Chế độ kể chuyện: <b>'+esc(nc.storytelling_mode)+'</b></p>';
  if(nc.primary_character)h+='<p>Nhân vật chính (ngôi thứ nhất): <b>'+esc(nc.primary_character)+'</b></p>';
  if(r.meta)h+='<h3>Thông tin chung</h3>'+kvList(r.meta,{});
  h+='<h3>Nhân vật</h3><ul>'+(r.characters||[]).map(function(c){return '<li><b>'+esc(c.name||c.id||'')+'</b>'+kvList(c,{name:1,id:1,line:1})+'</li>';}).join('')+'</ul>';
  h+='<h3>Bối cảnh (LOCATION)</h3><ul>'+(r.locations||[]).map(function(l){return '<li><b>'+esc(l.id||'')+'</b>'+(l.name&&l.name!==l.id?' — '+esc(l.name):'')+kvList(l,{id:1,name:1,line:1})+'</li>';}).join('')+'</ul>';
  h+='<h3>Đạo cụ (PROP)</h3><ul>'+(r.props||[]).map(function(p){return '<li><b>'+esc(p.name||p.id||'')+'</b>'+kvList(p,{name:1,id:1,line:1})+'</li>';}).join('')+'</ul>';
  h+='<h3>Cảnh và shot</h3>'+(r.scenes||[]).map(function(sc){
    const lines=sc.lines||sc.spoken_lines||[];
    const cues=sc.all_audio_cues||((sc.audio_cues||[]).concat(sc.vfx_cues||[]));
    let sh='<div><b>Cảnh '+esc(sc.number!=null?sc.number:(sc.id||''))+': '+esc(sc.title||'')+'</b>';
    sh+=kvList(sc,{number:1,id:1,title:1,lines:1,spoken_lines:1,shots:1,audio_cues:1,vfx_cues:1,all_audio_cues:1,actions:1,action_cues:1,dropped_action_cues:1,line:1});
    if(sc.actions&&sc.actions.length){sh+='<ul>'+sc.actions.map(function(a){return '<li>Hành động: '+esc(a)+'</li>';}).join('')+'</ul>';}
    if(lines.length){sh+='<ul>'+lines.map(function(ln){return '<li>['+esc(ln.line_id||'')+'] <b>'+esc(ln.speaker||'')+'</b> ('+(ln.kind==='narration'?'narration':'dialogue')+'): '+esc(ln.text||'')+'</li>';}).join('')+'</ul>';}
    if(sc.shots&&sc.shots.length){sh+='<ul>'+sc.shots.map(function(o){return '<li>Shot <b>'+esc(o.id||'')+'</b>'+kvList(o,{id:1,line:1})+'</li>';}).join('')+'</ul>';}
    if(sc.action_cues&&sc.action_cues.length){sh+='<small>Action cues: '+sc.action_cues.map(esc).join(', ')+'</small>';}
    if(sc.dropped_action_cues&&sc.dropped_action_cues.length){sh+='<small> (bị loại: '+sc.dropped_action_cues.map(esc).join(', ')+')</small>';}
    if(cues.length){sh+='<ul>'+cues.map(function(c){return '<li>'+cueLine(c)+'</li>';}).join('')+'</ul>';}
    return sh+'</div>';
  }).join('');
  const ac=r.audio_cues||{};
  h+='<h3>Âm thanh</h3><ul>'+Object.keys(ac).map(function(k){return '<li><b>'+esc(k)+'</b> ('+((ac[k]||[]).length)+'): '+(ac[k]||[]).map(function(c){return esc(c.name||'');}).join('; ')+'</li>';}).join('')+'</ul>';
  if(r.constraints&&r.constraints.length){h+='<h3>Ràng buộc (constraints)</h3><ul>'+r.constraints.map(function(c){return '<li>'+esc(c)+'</li>';}).join('')+'</ul>';}
  if(r.unsupported_fields&&r.unsupported_fields.length){h+='<h3>Trường không hỗ trợ (được giữ lại, không bị loại bỏ âm thầm)</h3><ul>'+r.unsupported_fields.map(function(u){return '<li>Dòng '+u.line+' ['+esc(u.context||'')+'] '+esc(u.key||'')+': '+esc(u.value||'')+'</li>';}).join('')+'</ul>';}
  if(r.end_card)h+='<h3>End card</h3>'+kvList(r.end_card,{line:1});
  if(r.qa)h+='<h3>QA (số lượng kỳ vọng)</h3>'+kvList(r.qa,{});
  if(r.output)h+='<h3>OUTPUT (xuất bản &amp; Drive)</h3>'+kvList(r.output,{});
  if(r.global_audio)h+='<h3>Âm thanh tổng (global audio)</h3>'+kvList(r.global_audio,{});
  const handled={characters:1,locations:1,props:1,scenes:1,audio_cues:1,audio_cues_grouped:1,constraints:1,unsupported_fields:1,meta:1,narrator_check:1,end_card:1,qa:1,output:1,global_audio:1};
  const extra=Object.keys(r).filter(function(k){return !handled[k]&&r[k]!=null&&r[k]!=='';});
  if(extra.length){h+='<h3>Thông tin khác</h3><ul>'+extra.map(function(k){return '<li><b>'+esc(lbl(k))+':</b> '+fmtVal(r[k],0)+'</li>';}).join('')+'</ul>';}
  return h;
}
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
  preflightPassed=!!data.passed;
  refreshDraftButton();
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
  loadArtifacts(d.drive&&d.drive.file_id);
}
const ARTIFACT_LABELS={'script.txt':'Kịch bản (snapshot)','snapshot.json':'Snapshot + hash','scene_package.json':'Scene package','character_design.json':'Thiết kế nhân vật','animation_plan.json':'Kế hoạch animation','timeline.json':'Timeline âm thanh','audio_plan.json':'Kế hoạch âm thanh','subtitles.json':'Phụ đề','renderer_info.json':'Renderer info','manifest.json':'Manifest','QA_REPORT.md':'Báo cáo QA','job.json':'Job record'};
async function loadArtifacts(driveFileId){
  const el=document.getElementById('artifacts');
  try{
    const r=await fetch('/api/production/jobs/'+jobId+'/artifacts');
    const d=await r.json();
    const files=(d.artifacts||[]).map(function(p){const parts=p.split('/jobs/');const rel=parts.length>1?parts[1].split('/').slice(1).join('/'):p.split('/').pop();return rel;});
    let h='<h3>Artifacts của draft</h3>';
    h+=files.length?'<ul>'+files.map(function(f){const base=f.split('/').pop();return '<li>'+esc(ARTIFACT_LABELS[base]||base)+' <small>(<code>'+esc(f)+'</code>)</small></li>';}).join('')+'</ul>':'<p><small>Chưa có artifact.</small></p>';
    if(driveFileId){h+='<p><small>Drive file id của draft: <code>'+esc(driveFileId)+'</code></small></p>';}
    el.innerHTML=h;
  }catch(e){el.innerHTML='';}
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


# ---------------------------------------------------------------------------
# STUDIO SCRIPT V1 validation + review (DIRECTIVE §2: paste -> parse and
# validate -> display characters/locations/props/scenes/shots, narration
# and dialogue, SFX/ambience/BGM/VFX, line-numbered errors, review before
# production). This reuses the parser and the adapter's error type; it
# never re-implements parsing. Field names follow SPEC §13 / the parsed
# document's to_dict() shape.
# ---------------------------------------------------------------------------

def _issue_dicts(issues: list) -> list[dict[str, Any]]:
    """Normalise parser ValidationIssue objects (or plain dicts, as
    carried by V1AdapterError) to {line, code, message} dicts."""
    out = []
    for issue in issues:
        if isinstance(issue, dict):
            out.append({"line": issue.get("line", 0),
                        "code": issue.get("code", ""),
                        "message": issue.get("message", "")})
        else:
            out.append({"line": getattr(issue, "line", 0),
                        "code": getattr(issue, "code", ""),
                        "message": getattr(issue, "message", "")})
    return out


def _v1_error_payload(exc: V1AdapterError) -> dict[str, Any]:
    """Structured refusal for an invalid V1 script: the full
    line-numbered error list, never a bare 500."""
    return {"error": str(exc),
            "errors": _issue_dicts(exc.errors),
            "format": "studio_script_v1"}


def _normalize_speaker(speaker: str) -> str:
    """Same normalisation the parser/adapter use for narrator-alias
    detection (casefold + whitespace collapse). Display logic only;
    parsing itself stays in studio_script_v1.py."""
    return " ".join(str(speaker).strip().casefold().split())


def _scene_spoken_lines(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Spoken lines of one parsed scene, whatever key the parser used
    (``spoken_lines`` in the current dialect; ``lines`` is accepted
    so a future dialect shape still displays)."""
    lines = scene.get("spoken_lines") or scene.get("lines") or []
    return [ln for ln in lines if isinstance(ln, dict)]


def _narrator_check(doc: Any, data: dict[str, Any]) -> dict[str, Any]:
    """First-person / external-narrator facts for the review display.

    Reports the parser's own values verbatim — storytelling mode,
    primary character, external-narrator status — and COUNTS spoken
    lines whose speaker is one of the parser's narrator aliases.
    This introduces no validation rule of its own: whether a
    narrator line is an error (V1E025) is the parser's decision and
    surfaces through the errors list.
    """
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}

    def _find(*names: str) -> Any:
        for src in (meta, data):
            for name in names:
                if name in src and src[name] not in (None, ""):
                    return src[name]
        value = None
        for name in names:
            value = getattr(doc, name, None)
            if value not in (None, ""):
                return value
        return None

    total = narration = dialogue = narrator_lines = 0
    for scene in data.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        for line in _scene_spoken_lines(scene):
            total += 1
            if line.get("kind") == "narration":
                narration += 1
            elif line.get("kind") == "dialogue":
                dialogue += 1
            if _normalize_speaker(line.get("speaker", "")) in NARRATOR_ALIASES:
                narrator_lines += 1
    return {
        "storytelling_mode": _find("storytelling_mode"),
        "primary_character": _find("primary_character"),
        "external_narrator": _find("external_narrator"),
        "external_narrator_lines": narrator_lines,
        "spoken_lines": total,
        "narration_lines": narration,
        "dialogue_lines": dialogue,
    }


def _build_v1_review(doc: Any) -> dict[str, Any]:
    """Human-reviewable view of a parsed V1 document (valid or
    partially parsed), built GENERICALLY from the parser's own
    ``to_dict()`` output: every top-level key the parser produces is
    carried through, so both the original dialect and the newer
    FIRST_PERSON_ROLEPLAY dialect display correctly without this
    code knowing either dialect's field names. Only three things
    are added:

    * per-scene ``action_cues`` / ``dropped_action_cues`` (the SAME
      generic extract_action_cues() + SUPPORTED_CUES filter the
      adapter uses, so the review shows what the pipeline will
      actually do — dropped cues are listed, never silently
      discarded), a ``lines`` alias for ``spoken_lines``, and a
      combined ``all_audio_cues`` list (audio + VFX cues);
    * ``audio_cues`` grouped by cue_type (keys walked generically,
      never a hardcoded SFX/AMBIENCE/... list);
    * ``narrator_check`` (see _narrator_check).

    Envelope keys already present at the payload top level
    (format/snapshot_hash/is_valid/errors/warnings) are not
    duplicated inside the review.
    """
    data = doc.to_dict()
    scenes: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sc in data.get("scenes", []):
        if not isinstance(sc, dict):
            scenes.append(sc)
            continue
        actions = [a for a in (sc.get("actions") or []) if isinstance(a, str)]
        shot_actions = [sh.get("action", "") for sh in (sc.get("shots") or [])
                        if isinstance(sh, dict)]
        action_text = " ".join(
            p for p in actions + shot_actions if p).strip()
        raw_cues = extract_action_cues(action_text) if action_text else []
        entry = dict(sc)
        entry["action_cues"] = [c for c in raw_cues if c in SUPPORTED_CUES]
        entry["dropped_action_cues"] = [c for c in raw_cues
                                        if c not in SUPPORTED_CUES]
        if "spoken_lines" in sc and "lines" not in sc:
            entry["lines"] = sc["spoken_lines"]
        cues = [c for c in list(sc.get("audio_cues") or [])
                + list(sc.get("vfx_cues") or []) if isinstance(c, dict)]
        entry["all_audio_cues"] = cues
        for cue in cues:
            grouped.setdefault(str(cue.get("cue_type", "UNKNOWN")), []).append(cue)
        scenes.append(entry)
    review = {k: v for k, v in data.items()
              if k not in ("format", "snapshot_hash", "is_valid",
                           "validation_errors", "warnings")}
    review["scenes"] = scenes
    review["audio_cues"] = grouped
    review["narrator_check"] = _narrator_check(doc, data)
    return review


def _validate_script(script: str) -> tuple[int, dict[str, Any]]:
    """Validate one script for the /api/production/validate endpoint.

    Returns (http_status, payload). Free-form scripts are NOT
    rejected: they get a freeform note and keep using the existing
    analyze/preflight path. Invalid V1 scripts get HTTP 422 with
    every error, line-numbered, plus the partial review.
    """
    if detect_format(script) != "studio_v1":
        return 200, {
            "format": "freeform",
            "valid": True,
            "snapshot_hash": script_hash(script),
            "note": "Kịch bản tự do (không phải STUDIO SCRIPT V1) — "
                    "dùng luồng Phân tích / Preflight hiện có; kiểm tra "
                    "V1 không chặn kịch bản tự do."}
    doc = parse_studio_script_v1(script)
    review = _build_v1_review(doc)
    narrator = review["narrator_check"]
    payload: dict[str, Any] = {
        "format": "studio_script_v1",
        "valid": doc.is_valid,
        "snapshot_hash": doc.snapshot_hash,
        "errors": _issue_dicts(doc.validation_errors),
        "warnings": _issue_dicts(doc.warnings),
        "summary": {
            "characters": len(doc.characters),
            "locations": len(doc.locations),
            "props": len(doc.props),
            "scenes": len(doc.scenes),
            "shots": sum(len(s.shots) for s in doc.scenes),
            "spoken_lines": len(doc.spoken_lines),
            "narration_lines": narrator["narration_lines"],
            "dialogue_lines": narrator["dialogue_lines"],
            "external_narrator_lines": narrator["external_narrator_lines"],
        },
        "review": review,
    }
    return (200 if doc.is_valid else 422), payload


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

        if self.path == "/api/production/validate":
            script = str(body.get("script", "") or "")
            if len(script.strip()) < 10:
                return self._send({"error": "script too short (min 10 chars)"}, 400)
            try:
                status, payload = _validate_script(script)
            except Exception as exc:  # noqa: BLE001 - never a bare 500
                return self._send(
                    {"error": f"validation failed: {exc}",
                     "format": "studio_script_v1", "valid": False,
                     "errors": []}, 500)
            return self._send(payload, status)

        if self.path == "/api/production/analyze":
            script = str(body.get("script", "") or "")
            if len(script.strip()) < 10:
                return self._send({"error": "script too short (min 10 chars)"}, 400)
            try:
                package, planner, detail = resolve_plan(script)
            except V1AdapterError as exc:
                # Invalid V1: structured 422 with the line-numbered
                # error list, not a bare 500.
                return self._send(_v1_error_payload(exc), 422)
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
                        "local planner; 'v1' is the deterministic "
                        "STUDIO SCRIPT V1 adapter (no Gemini enrichment)."})

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
                except V1AdapterError as exc:
                    return self._send(_v1_error_payload(exc), 422)
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
            # Invalid V1 scripts are refused HERE, synchronously, via
            # the same resolve_plan/V1AdapterError path the pipeline
            # uses — no job is queued for a script that cannot render.
            # V1 planning is deterministic (parse + adapt, no Gemini,
            # no side effects), so this check is cheap and cannot
            # disagree with the background job. Free-form scripts are
            # untouched: they queue immediately, as before.
            if detect_format(script) == "studio_v1":
                try:
                    resolve_plan(script)
                except V1AdapterError as exc:
                    return self._send(_v1_error_payload(exc), 422)
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
    print("Endpoints: /api/production/validate, /api/production/analyze, /api/production/preflight, "
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
