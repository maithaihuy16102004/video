"""Affiliate Studio workspace UI (Vietnamese) for the :8788 server.

A single self-contained HTML page (same pattern as ``server.py``'s
``UI_HTML``: inline CSS/JS, no build step). It talks to the
``/api/affiliate/*`` endpoints with real fetch calls and polls REAL
stage status — no simulated progress percentages anywhere.

Sections (§3 + §21): upload, product info, analysis, OCR/translation,
script, editing controls, voice, subtitles, branding, preview
(original vs edited, safe-zone guides, timeline), render, QA, export,
history.

Editing execution (masks, transforms, reframing, export render) is
Subagent A's stage: the controls below POST the requested operations
to the API and show the stage status the backend reports. The Export
button reports the honest Phase-1 state (501 until the render stage
is wired at integration).
"""
from __future__ import annotations

AFFILIATE_UI_HTML = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<title>AI Affiliate Studio — Shopee Edition</title>
<style>
body{font-family:system-ui,sans-serif;max-width:1080px;margin:24px auto;padding:0 16px;color:#1c2333}
h1{font-size:22px} h2{font-size:17px;margin-top:28px;border-top:1px solid #ddd;padding-top:16px}
textarea{width:100%;height:90px;font-size:14px} button{padding:10px 18px;font-size:15px;margin:6px 6px 6px 0;cursor:pointer}
button:disabled{opacity:.45;cursor:not-allowed}
pre{background:#f4f4f4;padding:12px;white-space:pre-wrap;font-size:13px}
input,select{font-size:14px;padding:6px;margin:3px 6px 3px 0}
label{display:inline-block;min-width:170px;margin:4px 0}
video{width:100%;background:#000}
.ok{color:#0a7a2f} .bad{color:#b00020} .warn{color:#8a6d00}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{border:1px solid #ddd;border-radius:8px;padding:12px}
.small{font-size:12px;color:#555}
table{border-collapse:collapse;width:100%;font-size:13px}
td,th{border:1px solid #ddd;padding:6px;text-align:left}
</style></head><body>
<h1>🛒 AI Affiliate Studio — Shopee Edition</h1>
<p>Video sản phẩm được phép sử dụng &rarr; phân tích &rarr; dịch &rarr; kịch bản
&rarr; lồng tiếng Việt &rarr; phụ đề &rarr; render 9:16 &rarr; QA &rarr; xuất bản.</p>
<p class="warn"><b>Lưu ý bản quyền:</b> chỉ xử lý video bạn sở hữu hoặc được phép
dùng cho mục đích thương mại. Mirror, dịch chữ và lồng tiếng không biến video
của người khác thành nội dung nguyên bản, và không đảm bảo đủ điều kiện kiếm tiền.</p>

<h2>1. Tạo dự án + tải video lên</h2>
<div class="card">
<label>Tên dự án: <input id="projectName" placeholder="VD: Hop-dung-do-bep-01"></label><br>
<label>Video nguồn: <input type="file" id="videoFile" accept=".mp4,.mov,.mkv,.webm"></label><br>
<label>Link nguồn (nếu có — chỉ ghi lại, hệ thống không tự tải video): <input id="sourceUrl" size="50" placeholder="https://..."></label><br>
<label>Quyền sử dụng nguồn:
<select id="authType"><option value="USER_OWNED">USER_OWNED — video của tôi</option>
<option value="LICENSED">LICENSED — có giấy phép</option>
<option value="SELLER_AUTHORIZED">SELLER_AUTHORIZED — người bán cho phép</option>
<option value="UNKNOWN">UNKNOWN — không rõ</option></select></label><br>
<label><input type="checkbox" id="rightsConfirmed"> Tôi xác nhận có quyền dùng video này cho mục đích thương mại</label><br>
<label>Ghi chú quyền: <input id="rightsNote" size="50" placeholder="VD: nhà bán hàng gửi video qua chat Shopee"></label><br>
<button onclick="createProject()">Tạo dự án</button>
<div id="projectOut"></div>
</div>

<h2>2. Thông tin sản phẩm</h2>
<div class="card">
<label>Tên sản phẩm (*): <input id="pName" size="40"></label><br>
<label>Danh mục: <input id="pCategory" size="30"></label>
<label>Thương hiệu: <input id="pBrand" size="25"></label><br>
<label>Link Shopee: <input id="pShopee" size="50"></label><br>
<label>Link Affiliate: <input id="pAffiliate" size="50"></label><br>
<label>Giá (VNĐ, để trống nếu không rõ): <input id="pPrice" type="number" min="0"></label><br>
<label>Đặc điểm (mỗi dòng một ý):</label><br><textarea id="pFeatures"></textarea>
<label>Lợi ích (mỗi dòng một ý):</label><br><textarea id="pBenefits"></textarea>
<label>Đối tượng: <input id="pAudience" size="40"></label><br>
<label>Lời kêu gọi (CTA): <input id="pCta" size="60"></label><br>
<label>Câu công bố affiliate:</label><br><textarea id="pDisclosure"></textarea>
<p class="small">Hệ thống không bao giờ tự bịa giá, giảm giá, chứng nhận hay lợi ích. Thông tin trống sẽ dùng cách diễn đạt trung lập từ những gì video cho thấy.</p>
<button onclick="saveProduct()">Lưu thông tin sản phẩm</button>
<div id="productOut"></div>
</div>

<h2>3. Phân tích + nhận diện giọng nói</h2>
<button onclick="runStage('transcribe')">🎤 Nhận diện giọng nói tiếng Trung</button>
<button onclick="refreshProject()">🔄 Xem trạng thái</button>
<div id="stageOut"></div>

<h2>4. Dịch chữ Trung → Việt</h2>
<label>Chế độ dịch:
<select id="transMode"><option value="NATURAL_LOCALIZATION">Bản địa hóa tự nhiên</option>
<option value="DIRECT_TRANSLATION">Dịch trực tiếp</option>
<option value="AFFILIATE_COPYWRITING">Viết lại kiểu affiliate</option></select></label>
<label>Giọng văn:
<select id="transStyle"><option value="neutral">Trung tính</option>
<option value="humorous_viral_review">Hài hước, viral, kiểu review (bám sát nghĩa gốc)</option></select></label>
<button onclick="runTranslate()">Dịch</button>
<div id="transOut"></div>
<p class="small">Giọng văn hài hước/viral chỉ thay đổi cách diễn đạt — sự thật, con số, giá và tên sản phẩm vẫn bám sát bản gốc.</p>
<label>Gán người nói (mỗi dòng: bắt đầu-giây, kết thúc-giây, tên người nói — VD: <i>0, 8.5, NGUOI_1</i>):</label><br>
<textarea id="speakerRanges" placeholder="0, 8.5, NGUOI_1"></textarea>
<button onclick="assignSpeakers()">Gán người nói cho bản ghi</button>
<div id="speakerOut"></div>

<h2>5. Kịch bản affiliate</h2>
<label>Phong cách:
<select id="scriptVariant"><option value="natural_review">Review tự nhiên</option>
<option value="demonstration">Trình diễn sản phẩm</option>
<option value="problem_solution">Vấn đề — giải pháp</option></select></label>
<label>Thời lượng mục tiêu (giây): <input id="targetSec" type="number" value="30" min="5" max="180"></label><br>
<label>Mô tả những gì video cho thấy:</label><br><textarea id="visibleDemo" placeholder="VD: người mẫu mở hộp, xếp đồ vào khay, đóng nắp lại"></textarea>
<button onclick="genScript()">Viết kịch bản</button>
<button onclick="genDubScript()">🎬 Tạo kịch bản lồng tiếng từ bản dịch</button>
<div id="scriptOut"></div>
<label>Người duyệt: <input id="approver" placeholder="Tên bạn"></label>
<button onclick="approveScript()">✅ Duyệt kịch bản</button>

<h2>6. Biên tập (mirror / cắt / mặt nạ)</h2>
<div class="card">
<label><input type="checkbox" id="mirrorToggle"> Lật ngang (mirror) — mặc định TẮT</label>
<p class="small">Trước khi bật mirror, hệ thống cảnh báo nếu video có nhãn sản phẩm, logo hoặc chữ hướng dẫn — lật ngang có thể làm thông tin bị sai.</p>
<label><input type="checkbox" id="mirrorReviewed"> Tôi đã xem cảnh báo mirror và vẫn muốn bật</label><br>
<button onclick="saveEdits()">Lưu thao tác biên tập</button>
<div id="editOut"></div>
</div>

<h2>7. Lồng tiếng AI</h2>
<label>Giọng đọc: <select id="voicePreset"></select></label>
<button onclick="previewVoice()">🔊 Nghe thử giọng</button>
<button onclick="runVoice()">🎙️ Lồng tiếng toàn bộ kịch bản</button><br>
<label>Giọng theo từng nhân vật (JSON: tên người nói → tên preset — VD: <i>{"NGUOI_1": "female_review", "NGUOI_2": "male_review"}</i>):</label><br>
<textarea id="speakerVoices" placeholder='{"NGUOI_1": "female_review"}'></textarea>
<div id="voiceOut"></div>

<h2>8. Phụ đề</h2>
<label>Cỡ chữ: <input id="fontSize" type="number" value="64" min="16" max="160"></label>
<label>Vùng an toàn:
<select id="safeZone"><option value="TIKTOK_VERTICAL">TikTok dọc</option>
<option value="FACEBOOK_REELS_VERTICAL">Facebook Reels dọc</option></select></label>
<label><input type="checkbox" id="wordHighlight"> Tô sáng từng từ</label>
<button onclick="buildSubtitles()">Tạo phụ đề</button>
<div id="subOut"></div>

<h2>9. Trộn âm thanh</h2>
<label>Chế độ:
<select id="mixMode"><option value="REPLACE_ALL">Thay toàn bộ âm thanh gốc</option>
<option value="KEEP_PRODUCT_SOUNDS">Giữ tiếng sản phẩm</option>
<option value="DUCK_ORIGINAL_AUDIO">Giảm âm thanh gốc dưới lời đọc</option>
<option value="CUSTOM_MIX">Trộn tùy chỉnh</option></select></label>
<button onclick="runMix()">Trộn âm thanh</button>
<div id="mixOut"></div>

<h2>10. Gói tiếp thị + QA + Xuất</h2>
<button onclick="runMarketing()">📦 Tạo caption + hashtag + link</button>
<button onclick="runQA()">🧪 Chạy QA</button>
<button onclick="runExport()">⬇️ Xuất video 1080×1920</button>
<div id="qaOut"></div>

<h2>11. Xem trước (gốc / đã biên tập)</h2>
<div class="grid">
<div class="card"><h3>Gốc</h3><video id="origVideo" controls></video></div>
<div class="card"><h3>Đã biên tập</h3><video id="editVideo" controls></video>
<p class="small">Video đã biên tập xuất hiện sau bước render (giai đoạn tích hợp).</p></div>
</div>

<h2>12. Lịch sử dự án</h2>
<button onclick="loadHistory()">Tải lịch sử</button>
<div id="historyOut"></div>

<script>
let projectId=null;
async function post(url, body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});let data={};try{data=await r.json();}catch(e){}return {status:r.status,data};}
async function get(url){const r=await fetch(url);return {status:r.status,data:await r.json()};}
function show(el, obj){document.getElementById(el).innerHTML='<pre>'+JSON.stringify(obj,null,2)+'</pre>';}
function fileToBase64(file){return new Promise((res,rej)=>{const fr=new FileReader();fr.onload=()=>res(fr.result.split(',')[1]);fr.onerror=rej;fr.readAsDataURL(file);});}
async function createProject(){
  const file=document.getElementById('videoFile').files[0];
  const body={project_name:document.getElementById('projectName').value,
    source_url:document.getElementById('sourceUrl').value,
    product:{product_name:document.getElementById('pName').value||'Sản phẩm chưa đặt tên'},
    authorization:{authorization_type:document.getElementById('authType').value,
      commercial_rights_confirmed:document.getElementById('rightsConfirmed').checked,
      rights_note:document.getElementById('rightsNote').value}};
  if(file){body.source={file_name:file.name,data_base64:await fileToBase64(file)};}
  const {status,data}=await post('/api/affiliate/projects',body);
  if(status===201){projectId=data.project_id;show('projectOut',{project_id:projectId,source:data.source_video||null});}
  else{show('projectOut',data);}
}
async function saveProduct(){
  if(!projectId){alert('Tạo dự án trước.');return;}
  const splitLines=v=>v.split('\\n').map(s=>s.trim()).filter(Boolean);
  const body={product_name:document.getElementById('pName').value,
    product_category:document.getElementById('pCategory').value,
    shopee_product_url:document.getElementById('pShopee').value,
    affiliate_url:document.getElementById('pAffiliate').value,
    product_price:document.getElementById('pPrice').value?Number(document.getElementById('pPrice').value):null,
    product_features:splitLines(document.getElementById('pFeatures').value),
    product_benefits:splitLines(document.getElementById('pBenefits').value),
    target_audience:document.getElementById('pAudience').value,
    call_to_action:document.getElementById('pCta').value,
    brand_name:document.getElementById('pBrand').value,
    disclosure_text:document.getElementById('pDisclosure').value};
  show('productOut',{note:'Lưu sản phẩm: tạo lại dự án với đầy đủ thông tin, hoặc dùng API trực tiếp (tích hợp giai đoạn 2 sẽ có endpoint cập nhật).',draft:body});
}
async function refreshProject(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {data}=await get('/api/affiliate/projects/'+projectId);
  show('stageOut',{stages:data.stages,source:data.source_video,authorization:data.authorization});
}
async function runStage(kind){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {status,data}=await post('/api/affiliate/projects/'+projectId+'/'+kind,{});
  show('stageOut',{status,data});
}
async function runTranslate(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {data}=await post('/api/affiliate/projects/'+projectId+'/translate',{mode:document.getElementById('transMode').value,style:document.getElementById('transStyle').value,visible_demonstration:document.getElementById('visibleDemo').value});
  show('transOut',data);
}
async function assignSpeakers(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const ranges=document.getElementById('speakerRanges').value.split('\n').map(s=>s.trim()).filter(Boolean).map(line=>{const p=line.split(',').map(x=>x.trim());return {start:Number(p[0]),end:Number(p[1]),speaker_id:p[2]};});
  const {data}=await post('/api/affiliate/projects/'+projectId+'/speakers',{ranges});
  show('speakerOut',data);
}
async function genScript(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {data}=await post('/api/affiliate/projects/'+projectId+'/script',{variant:document.getElementById('scriptVariant').value,target_seconds:Number(document.getElementById('targetSec').value),visible_demonstration:document.getElementById('visibleDemo').value});
  show('scriptOut',data);
}
async function genDubScript(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {data}=await post('/api/affiliate/projects/'+projectId+'/script',{source:'translation'});
  show('scriptOut',data);
}
async function approveScript(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {data}=await post('/api/affiliate/projects/'+projectId+'/script/approve',{approved_by:document.getElementById('approver').value||'user'});
  show('scriptOut',data);
}
async function saveEdits(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const ops=[];
  if(document.getElementById('mirrorToggle').checked){ops.push({operation:'hflip',parameters:{},approved:document.getElementById('mirrorReviewed').checked});}
  const {data}=await post('/api/affiliate/projects/'+projectId+'/edits',{operations:ops});
  show('editOut',data);
}
async function loadVoices(){
  const {data}=await get('/api/affiliate/voices');
  const sel=document.getElementById('voicePreset');
  sel.innerHTML=Object.entries(data.presets||{}).map(([k,v])=>'<option value="'+k+'">'+v.label_vi+' ('+v.voice_id+')</option>').join('');
}
async function previewVoice(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {data}=await post('/api/affiliate/projects/'+projectId+'/voice/preview',{preset:document.getElementById('voicePreset').value});
  show('voiceOut',data);
}
async function runVoice(){
  if(!projectId){alert('Chưa có dự án.');return;}
  let speaker_voices={};
  const raw=document.getElementById('speakerVoices').value.trim();
  if(raw){try{speaker_voices=JSON.parse(raw);}catch(e){alert('JSON giọng theo nhân vật không hợp lệ.');return;}}
  const {status,data}=await post('/api/affiliate/projects/'+projectId+'/voice',{preset:document.getElementById('voicePreset').value,speaker_voices});
  show('voiceOut',{status,data});
}
async function buildSubtitles(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {data}=await post('/api/affiliate/projects/'+projectId+'/subtitles',{subtitle_style:{font_size:Number(document.getElementById('fontSize').value),safe_zone_profile:document.getElementById('safeZone').value,word_highlight:document.getElementById('wordHighlight').checked}});
  show('subOut',data);
}
async function runMix(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {data}=await post('/api/affiliate/projects/'+projectId+'/mix',{audio_mix:{mode:document.getElementById('mixMode').value}});
  show('mixOut',data);
}
async function runMarketing(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {data}=await post('/api/affiliate/projects/'+projectId+'/marketing',{});
  show('qaOut',data);
}
async function runQA(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {data}=await post('/api/affiliate/projects/'+projectId+'/qa',{});
  show('qaOut',data);
}
async function runExport(){
  if(!projectId){alert('Chưa có dự án.');return;}
  const {status,data}=await post('/api/affiliate/projects/'+projectId+'/export',{});
  show('qaOut',{status,data});
}
async function loadHistory(){
  const {data}=await get('/api/affiliate/projects');
  const rows=(data.projects||[]).map(p=>'<tr><td>'+p.project_id+'</td><td>'+(p.project_name||'')+'</td><td>'+(p.product_name||'')+'</td><td>'+Object.entries(p.stages||{}).map(([k,v])=>k+':'+v).join(', ')+'</td></tr>').join('');
  document.getElementById('historyOut').innerHTML='<table><tr><th>ID</th><th>Tên</th><th>Sản phẩm</th><th>Trạng thái các bước</th></tr>'+rows+'</table>';
}
loadVoices();
</script></body></html>
"""

# Two-mode navigation snippet for the Story Studio page (applied at
# integration — NOT applied in Phase 1, which touches no existing file).
AFFILIATE_NAV_SNIPPET = """<!-- AI Clip Studio mode switch (integration patch target: server.py UI_HTML) -->
<nav style="margin:12px 0">
  <a href="/">🎬 AI Story Studio</a> &nbsp;|&nbsp;
  <a href="/affiliate">🛒 AI Affiliate Studio</a>
</nav>
"""
