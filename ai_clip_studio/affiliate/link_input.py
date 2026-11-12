"""Link-paste input for AI Affiliate Studio — Shopee Edition.

Mai's confirmed flow (2026-11-12 09:59): the frontend video-input
section takes a PASTED DOUYIN LINK (seller-authorized) -> Gemini
translates close to the original meaning -> humorous dubbing ->
export. URL paste is the PRIMARY input; file upload is secondary.

This module is the link-paste half of that flow, built mount-ready
for Stage 2 (it modifies no existing file — see the mount block
below). It provides:

* :func:`render_link_paste_section` — a prominent, self-contained
  HTML fragment (Vietnamese UI, same inline-CSS/JS style as
  ``affiliate_ui.py``) with a large URL input, the authorization
  selector, the commercial-rights confirmation checkbox, a
  "Dán link và tải video" submit button, a status area, and a
  clearly SECONDARY file-upload note.
* :func:`handle_link_submit` — the endpoint logic for
  ``POST /api/affiliate/projects/{id}/link-fetch``. It validates the
  URL, runs the AUTHORIZATION GATE FIRST (via the existing gate in
  ``video/ingest.py`` — a refused request never reaches the
  downloader), calls ``ingest_source`` with the injected downloader,
  maps downloader failures to honest user-facing statuses, and on
  success records the ingested source on the project for the
  existing pipeline (translate -> dub -> export) to consume.
* :func:`handle_link_post` — the thin ``affiliate_api``-shaped
  wrapper (``handler._send(payload, status)``, returns ``True``) the
  Stage-2 mount calls.

Ordering guarantee (tested with fake downloaders): URL validation
(400) -> project lookup (404) -> authorization gate (403) -> ONLY
THEN the downloader. The default downloader is resolved from the
provider registry AFTER the gate passes.

Failure mapping (downloader reason -> user-facing status; HTTP 502
unless noted; every failure carries a plain Vietnamese explanation
plus the file-upload fallback, and NEVER claims a file):

    UNSUPPORTED_URL    -> FETCH_UNSUPPORTED   (link form unsupported)
    COOKIES_REQUIRED   -> FETCH_BLOCKED       (login/cookies needed)
    AUTH_REQUIRED      -> FETCH_BLOCKED       (same handling)
    NETWORK_ERROR      -> FETCH_FAILED        (transient-looking)
    NOT_FOUND          -> FETCH_NOT_FOUND     (video gone/private)
    NOT_AVAILABLE      -> DOWNLOADER_UNAVAILABLE (HTTP 503, no tool)
    DOWNLOAD_FAILED    -> FETCH_FAILED        (anything else)
    unreadable video   -> FETCH_INVALID       (HTTP 422, probe failed)

Honest fetch limitation (measured 2026-11-12, see
``acceptance_loop/affiliate_integration/douyin_fetch_result.md``):
yt-dlp rejects the Douyin share URL form (``Unsupported URL``) and
the canonical form requires fresh cookies, which are forbidden.
This module reports both outcomes as above; it never retries with
cookies, mirrors, or credential tricks. The remaining routes are a
live-browser fetch arranged by ATLAS or the user uploading the
video file directly.

STAGE 2 MOUNT (do NOT apply before the coordinator/ATLAS go-ahead —
this module is new-files-only work; the lines below are the exact
edits Stage 2 makes to EXISTING files):

1. ``affiliate/affiliate_api.py`` — add the import (with the other
   ``from .`` imports at the top of the file)::

       from .link_input import handle_link_post, match_link_fetch_path

   and add this route inside ``handle_affiliate_post``, before the
   final ``return False`` (after the ``/export`` block)::

       match = match_link_fetch_path(path)
       if match is not None:
           return handle_link_post(handler, match, body)

   (``match_link_fetch_path`` returns the project id or ``None``;
   the endpoint path is ``/api/affiliate/projects/{id}/link-fetch``.)

2. ``server.py`` — NO new lines are needed if the affiliate mount
   from ``affiliate_api.py``'s docstring is already in place
   (``handle_affiliate_post`` dispatch + ``_send_html``). If it is
   not mounted yet, add exactly the two dispatch lines documented
   there; the link-fetch route rides on the same dispatch.

3. ``affiliate/affiliate_ui.py`` — NO edit to the file itself is
   needed: Stage 2 injects the fragment at request time in the
   ``GET /affiliate`` handler by replacing the stable anchor
   ``<h2>1. Tạo dự án + tải video lên</h2>`` with
   ``render_link_paste_section() + anchor`` (one ``str.replace``,
   count 1). The fragment's JS is self-contained (it defines its
   own ``linkPost`` helper in the same style as the page's
   ``post()``) and only reads the page-global ``projectId`` when it
   is already set, so it composes with the existing page without
   changing any existing element id.

Handoff: after a successful fetch, the project carries a real
``SourceVideo`` (checksum + ffprobe metadata + stored path) exactly
as if the file had been uploaded. The downstream stages —
transcription, translation, dub script, voice, subtitles, edit,
export — are the EXISTING pipeline (``pipeline_run.py`` + the A/B
modules); this module does not rebuild any of them.
"""
from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .providers import (
    REASON_AUTH_REQUIRED,
    REASON_COOKIES_REQUIRED,
    REASON_DOWNLOAD_FAILED,
    REASON_NETWORK_ERROR,
    REASON_NOT_AVAILABLE,
    REASON_NOT_FOUND,
    REASON_UNSUPPORTED_URL,
    DownloadFailure,
    as_ingest_downloader,
    get_provider,
)
from .schema import AUTHORIZATION_TYPES, SourceAuthorization, SourceVideo
from .store import AffiliateStore
from .video.ingest import (
    IngestRefused,
    IngestRequest,
    ingest_source,
    validate_ingest_request,
)

# Endpoint path (Stage 2 mount target).
LINK_FETCH_PATH_TEMPLATE = "/api/affiliate/projects/{project_id}/link-fetch"
_LINK_FETCH_RE = re.compile(r"^/api/affiliate/projects/([^/]+)/link-fetch$")

# Downloader reason -> (user-facing status, HTTP status, Vietnamese
# explanation). The fallback suggestion is appended by the handler.
_FAILURE_MAP: dict[str, tuple[str, int, str]] = {
    REASON_UNSUPPORTED_URL: (
        "FETCH_UNSUPPORTED", 502,
        "Link này không tải được trực tiếp: dạng link chưa được công cụ "
        "tải video hỗ trợ. Hệ thống không tạo video giả — hãy tải file "
        "video lên thay thế."),
    REASON_COOKIES_REQUIRED: (
        "FETCH_BLOCKED", 502,
        "Douyin chặn tải trực tiếp link này (yêu cầu cookie đăng nhập). "
        "Hệ thống không dùng cookie hay thủ thuật đăng nhập — hãy tải "
        "file video lên thay thế."),
    REASON_AUTH_REQUIRED: (
        "FETCH_BLOCKED", 502,
        "Link này yêu cầu đăng nhập nên không tải trực tiếp được. Hệ "
        "thống không dùng cookie hay thông tin đăng nhập — hãy tải file "
        "video lên thay thế."),
    REASON_NETWORK_ERROR: (
        "FETCH_FAILED", 502,
        "Không tải được video do lỗi mạng. Hãy kiểm tra lại link và thử "
        "lại, hoặc tải file video lên thay thế."),
    REASON_NOT_FOUND: (
        "FETCH_NOT_FOUND", 502,
        "Không tìm thấy video ở link này (có thể video đã bị xóa hoặc "
        "đặt ở chế độ riêng tư). Hãy kiểm tra lại link hoặc tải file "
        "video lên thay thế."),
    REASON_NOT_AVAILABLE: (
        "DOWNLOADER_UNAVAILABLE", 503,
        "Công cụ tải video chưa sẵn sàng trên máy chủ này. Hãy tải file "
        "video lên thay thế."),
    REASON_DOWNLOAD_FAILED: (
        "FETCH_FAILED", 502,
        "Không tải được video từ link này. Hệ thống không tạo video giả "
        "— hãy tải file video lên thay thế."),
}

_UPLOAD_FALLBACK_VI = ("Phương án dự phòng: tải file video lên ở mục "
                       "“Tạo dự án + tải video lên” bên dưới.")


def match_link_fetch_path(path: str) -> str | None:
    """Return the project id for a link-fetch path, else ``None``.

    The Stage-2 mount calls this from ``handle_affiliate_post`` so
    the route regex lives in exactly one place.
    """
    match = _LINK_FETCH_RE.match(path)
    return match.group(1) if match else None


def validate_link_url(url: str) -> list[str]:
    """URL-shape validation for the pasted link (400-level errors).

    Rules mirror the URL checks in ``ingest.validate_ingest_request``
    (which re-validates everything at the gate): non-empty, http/https
    scheme, a host, no embedded credentials. Returns refusal reasons;
    empty means the shape is acceptable.
    """
    reasons: list[str] = []
    value = (url or "").strip()
    if not value:
        return ["source_url is required"]
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https"):
        reasons.append(
            f"source_url scheme must be http/https, got "
            f"'{parts.scheme or '(none)'}'")
    if not parts.netloc:
        reasons.append("source_url has no host")
    if parts.username or parts.password:
        reasons.append("source_url must not embed credentials")
    return reasons


# ---------------------------------------------------------------------
# HTML fragment
# ---------------------------------------------------------------------

def render_link_paste_section() -> str:
    """Prominent link-paste block, composable into the affiliate page.

    Returns a plain HTML string (Vietnamese UI, same inline classes
    as ``affiliate_ui.py``: ``.card`` / ``.small`` / ``.bad``).
    Stage 2 inserts it before the ``<h2>1. Tạo dự án...`` anchor —
    see the module docstring. The fragment's JS is self-contained:
    it defines ``linkPost`` (same fetch/JSON shape as the page's
    ``post()`` helper), creates a link-only project through the
    existing ``POST /api/affiliate/projects`` endpoint when no
    project exists yet, then calls the new link-fetch endpoint.
    Element ids are prefixed ``link*`` and collide with nothing on
    the existing page.
    """
    return """<!-- STAGE-2 INSERTION POINT: insert this fragment before the
     '<h2>1. Tạo dự án + tải video lên</h2>' anchor of AFFILIATE_UI_HTML
     (one str.replace, count 1, at request time in the GET /affiliate
     handler). Do not edit affiliate_ui.py for this; see link_input.py
     module docstring for the exact mount. -->
<h2>Dán link Douyin để tải video</h2>
<div class="card" style="border:2px solid #0a7a2f">
<label for="linkPasteUrl"><b>Link video Douyin (nguồn được phép dùng):</b></label><br>
<input id="linkPasteUrl" size="70" style="width:100%" placeholder="https://www.douyin.com/video/... — dán link video Douyin tại đây"><br>
<label>Quyền sử dụng nguồn:
<select id="linkAuthType"><option value="USER_OWNED">USER_OWNED — video của tôi</option>
<option value="LICENSED">LICENSED — có giấy phép</option>
<option value="SELLER_AUTHORIZED">SELLER_AUTHORIZED — người bán cho phép</option>
<option value="UNKNOWN">UNKNOWN — không rõ</option></select></label><br>
<label><input type="checkbox" id="linkRightsConfirmed"> Tôi xác nhận có quyền dùng video này cho mục đích thương mại</label><br>
<label>Ghi chú quyền: <input id="linkRightsNote" size="50" placeholder="VD: nhà bán hàng gửi link qua chat Shopee"></label><br>
<label>Tên dự án (tùy chọn): <input id="linkProjectName" size="40" placeholder="VD: Hop-dung-do-bep-01"></label><br>
<button onclick="submitLinkFetch()">Dán link và tải video</button>
<div id="linkFetchOut"></div>
<p class="small">Hệ thống chỉ tải video khi quyền sử dụng đã rõ ràng và được xác nhận. Nếu Douyin chặn tải trực tiếp (ví dụ: yêu cầu cookie), hệ thống sẽ báo rõ lý do và không tạo video giả.</p>
<p class="small">Hoặc tải file lên: dùng mục “Tạo dự án + tải video lên” bên dưới — tải file lên luôn là phương án dự phòng khi link không tải được.</p>
</div>
<script>
let linkProjectId=null;
async function linkPost(url, body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});let data={};try{data=await r.json();}catch(e){}return {status:r.status,data};}
function currentLinkProjectId(){try{if(typeof projectId!=='undefined'&&projectId){return projectId;}}catch(e){}return linkProjectId;}
async function submitLinkFetch(){
  const url=document.getElementById('linkPasteUrl').value.trim();
  const out=document.getElementById('linkFetchOut');
  const auth={authorization_type:document.getElementById('linkAuthType').value,
    commercial_rights_confirmed:document.getElementById('linkRightsConfirmed').checked,
    rights_note:document.getElementById('linkRightsNote').value};
  if(!url){out.innerHTML='<p class="bad">Dán link video trước.</p>';return;}
  let pid=currentLinkProjectId();
  if(!pid){
    const created=await linkPost('/api/affiliate/projects',{project_name:document.getElementById('linkProjectName').value||'Video từ link Douyin',source_url:url,product:{product_name:'Sản phẩm chưa đặt tên'},authorization:auth});
    if(created.status!==201){out.innerHTML='<pre>'+JSON.stringify(created.data,null,2)+'</pre>';return;}
    pid=created.data.project_id;linkProjectId=pid;
    try{projectId=pid;}catch(e){}
  }
  out.innerHTML='<p>Đang tải video…</p>';
  const res=await linkPost('/api/affiliate/projects/'+pid+'/link-fetch',{source_url:url,authorization:auth});
  out.innerHTML='<pre>'+JSON.stringify(res.data,null,2)+'</pre>';
}
</script>
"""


# ---------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------

def _failure_payload(project_id: str, reason: str, detail: str = "") -> tuple[int, dict]:
    """Map a DownloadFailure reason to (HTTP status, payload)."""
    status, http_status, message_vi = _FAILURE_MAP.get(
        reason, _FAILURE_MAP[REASON_DOWNLOAD_FAILED])
    payload: dict[str, Any] = {
        "project_id": project_id,
        "status": status,
        "reason": reason,
        "message_vi": message_vi,
        "fallback_vi": _UPLOAD_FALLBACK_VI,
        "source_video": None,
        "file_claimed": False,
    }
    if detail:
        payload["detail"] = detail[:300]
    return http_status, payload


def _source_video_from_record(record: Any, url: str) -> SourceVideo:
    """Build the project SourceVideo from an IngestRecord.

    Checksum, size, and ffprobe metadata come from the record's
    measured probe; the file name is the immutable store name (the
    probe's temp-download name is never used). The container is taken
    from the STORED file's suffix: ``probe_source`` records the
    suffix of the file it probed, and ingest probes the temp file
    ``download.bin`` — so the probe's container value (``"bin"``)
    is not schema vocabulary. The stored name is built by
    ``ingest.store_filename``, which maps to a supported container
    extension, so the stored suffix is both honest and valid.
    """
    probe = record.probe or {}
    stored = Path(record.local_path)
    container = stored.suffix.lstrip(".").lower() or str(
        probe.get("container", ""))
    return SourceVideo(
        file_name=stored.name,
        file_size_bytes=record.file_size_bytes,
        resolution=str(probe.get("resolution", "")),
        fps=float(probe.get("fps", 0.0) or 0.0),
        duration_sec=float(probe.get("duration_sec", 0.0) or 0.0),
        video_codec=str(probe.get("video_codec", "")),
        audio_codec=str(probe.get("audio_codec", "")),
        aspect_ratio=str(probe.get("aspect_ratio", "")),
        orientation=str(probe.get("orientation", "")),
        has_audio=bool(probe.get("has_audio", False)),
        container=container,
        sha256=record.sha256,
        stored_path=record.local_path,
        source_url=url)


def handle_link_submit(project_id: str, body: dict,
                       store_dir: str | Path | None = None,
                       downloader: Any = None,
                       store: AffiliateStore | None = None,
                       downloader_name: str = "") -> tuple[int, dict]:
    """Handle one link-paste submission. Returns ``(status, payload)``
    in the same shapes ``affiliate_api`` uses (``_send`` payloads:
    ``{"error": ...}`` / ``{"error": ..., "reasons": [...]}`` for
    failures, the project-shaped success payload otherwise).

    ``store_dir`` is the ingest store directory (defaults to
    ``<project_dir>/ingest``). ``downloader`` is either a
    fetch-style provider (``providers.Downloader``) or an
    ingest-style callable ``(url, target) -> Path``; when omitted,
    the registry default downloader is resolved — AFTER the gate
    passes. ``store`` defaults to a fresh ``AffiliateStore`` at the
    default root (the same root ``affiliate_api.STORE`` uses);
    tests pass an isolated store.
    """
    if store is None:
        store = AffiliateStore()
    if not isinstance(body, dict):
        return 400, {"error": "request body must be a JSON object"}

    # (1) URL validation — before anything else.
    url = str(body.get("source_url") or body.get("url") or "").strip()
    url_reasons = validate_link_url(url)
    if url_reasons:
        return 400, {"error": "invalid source_url", "reasons": url_reasons}

    # Project lookup (same 404 shape as affiliate_api._project_or_404).
    project = store.get(project_id)
    if project is None:
        return 404, {"error": f"project not found: {project_id}"}

    # Effective authorization: the submitted declaration wins when
    # present (the fragment always sends it); otherwise the stored
    # record. A submitted declaration is persisted on the project so
    # the record reflects what the user declared.
    auth_payload = body.get("authorization")
    if isinstance(auth_payload, dict) and auth_payload:
        auth_type = str(auth_payload.get("authorization_type", "UNKNOWN"))
        if auth_type not in AUTHORIZATION_TYPES:
            return 400, {"error": "authorization_type must be one of "
                         f"{list(AUTHORIZATION_TYPES)}"}
        confirmed = bool(auth_payload.get("commercial_rights_confirmed", False))
        project.authorization = SourceAuthorization(
            authorization_type=auth_type,
            commercial_rights_confirmed=confirmed,
            rights_note=str(auth_payload.get("rights_note", "")),
            confirmed_by=str(auth_payload.get("confirmed_by", "")),
            confirmed_at=str(auth_payload.get("confirmed_at", "")))
        store.save(project)
    elif project.authorization is not None:
        auth_type = project.authorization.authorization_type
        confirmed = project.authorization.commercial_rights_confirmed
    else:
        auth_type, confirmed = "UNKNOWN", False

    # (2) AUTHORIZATION GATE FIRST, via the existing gate code. A
    # refused request never reaches the downloader — the downloader
    # is not even resolved until this passes.
    request = IngestRequest(
        source_url=url, authorization_type=auth_type,
        commercial_rights_confirmed=confirmed)
    gate_reasons = validate_ingest_request(request)
    if gate_reasons:
        return 403, {"error": "ingest refused: authorization/rights gate",
                     "reasons": gate_reasons, "status": "GATE_REFUSED"}

    # (3) Resolve + adapt the downloader (gate already passed).
    resolved = downloader if downloader is not None else get_provider("downloader")
    ingest_downloader = as_ingest_downloader(resolved)
    name = downloader_name or getattr(resolved, "name", "") or "link_input"
    ingest_dir = Path(store_dir) if store_dir else (
        store.project_dir(project_id) / "ingest")

    # (4) Ingest. Failures map to honest statuses; nothing is
    # claimed on failure (the project's source record is untouched).
    try:
        record = ingest_source(request, ingest_dir,
                               downloader=ingest_downloader,
                               downloader_name=name)
    except DownloadFailure as exc:
        store.set_stage(project_id, "upload", "failed",
                        f"link fetch failed: {exc.reason}")
        return _failure_payload(project_id, exc.reason, exc.detail)
    except IngestRefused as exc:
        message = str(exc)
        store.set_stage(project_id, "upload", "failed",
                        f"link fetch refused: {message[:200]}")
        if ("authorization" in message or "commercial" in message
                or "source_url" in message):
            return 403, {"error": "ingest refused: authorization/rights gate",
                         "reasons": [message], "status": "GATE_REFUSED"}
        return 422, {"project_id": project_id, "status": "FETCH_INVALID",
                     "message_vi": "Video tải về không đọc được hoặc "
                                   "không phải video. Hãy kiểm tra lại "
                                   "link hoặc tải file video lên thay thế.",
                     "fallback_vi": _UPLOAD_FALLBACK_VI,
                     "detail": message[:300], "source_video": None,
                     "file_claimed": False}
    except Exception as exc:  # noqa: BLE001 - stage failure is recorded
        store.set_stage(project_id, "upload", "failed", str(exc)[:300])
        return 500, {"error": f"link fetch failed: {exc}",
                     "source_video": None, "file_claimed": False}

    # (5) Success: record the ingested source on the project and hand
    # off to the existing pipeline (transcription -> translation ->
    # dubbing -> export). The SourceVideo shape is identical to an
    # uploaded file's, so downstream stages need no link awareness.
    project.source_video = _source_video_from_record(record, url)
    store.save(project)
    store.set_stage(project_id, "upload", "done",
                    f"{project.source_video.file_name} "
                    f"({project.source_video.file_size_bytes} bytes, "
                    f"sha256 {project.source_video.sha256[:12]}…) "
                    f"via link fetch ({name})")
    return 200, {
        "project_id": project_id,
        "status": "FETCHED",
        "source_video": asdict(project.source_video),
        "ingest": record.to_dict(),
        "next_stage": "transcription",
        "handoff": {
            "pipeline": ("existing affiliate pipeline "
                         "(pipeline_run.py + A/B modules)"),
            "note": ("The stored source record is identical to an "
                     "uploaded file's; run transcription, then "
                     "translation (humorous_viral_review dubbing), "
                     "then the existing stages."),
        },
    }


def handle_link_post(handler: Any, project_id: str, body: dict,
                     store_dir: str | Path | None = None,
                     downloader: Any = None,
                     store: AffiliateStore | None = None) -> bool:
    """``affiliate_api``-shaped wrapper: sends via ``handler._send``
    and returns ``True`` (handled). The Stage-2 mount calls this
    from ``handle_affiliate_post`` — see the module docstring.
    """
    status, payload = handle_link_submit(
        project_id, body, store_dir=store_dir,
        downloader=downloader, store=store)
    handler._send(payload, status)
    return True


__all__ = [
    "LINK_FETCH_PATH_TEMPLATE",
    "handle_link_post",
    "handle_link_submit",
    "match_link_fetch_path",
    "render_link_paste_section",
    "validate_link_url",
]
