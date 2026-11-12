# AI Affiliate Studio — Architecture

AI Affiliate Studio — Shopee Edition is a module inside AI Clip Studio
V5.1 that localizes **authorized** product videos (including
Chinese-language demonstrations) into Vietnamese affiliate videos for
TikTok / Facebook Reels (9:16, 1080x1920). It shares infrastructure
with Story Studio (TTS, FFmpeg, Gemini, QA, Drive) but has its own
schema, pipeline, and frontend workspace.

Status: **Integration Stage 1 complete** (2026-11-12). Phase 1
(Subagent A: CV/video; Subagent B: frontend/language/audio) is done
and verified; the integration coordinator proved the two halves work
together with an end-to-end vertical slice on the synthetic fixture
(direct module calls, no server) and added the confirmed link-paste
input + provider seams. **Stage 2 (server mount + two-mode
navigation) is pending ATLAS go-ahead** — see "Stage 2 mount" below.
No GitHub push for this module without Mai's explicit approval.

## Standing rules

- Only videos the user owns or is permitted to reuse commercially.
  Export is **refused** when the source authorization is `UNKNOWN` or
  the commercial-rights confirmation is missing. The authorization
  gate runs **before any network call** (link fetch) and before
  export.
- The primary input is a **pasted video link** (seller-authorized),
  fetched only through the gated link-fetch endpoint. A blocked fetch
  is reported honestly with the file-upload fallback — never a fake
  success, never cookies/credentials/mirrors. (This supersedes the
  Phase 1 draft rule that a source URL is "provenance only".)
- Mirror / translation / dubbing never makes someone else's video
  original and never guarantees monetization eligibility (Mai's own
  caveat, 2026-11-12).
- No watermark or creator-attribution removal. No copyright-evasion
  transformations. Mirror defaults OFF with a label/logo warning.
- Never invent prices, discounts, certifications, medical benefits,
  performance claims, testimonials, or affiliate links. Product facts
  come only from user input + verified analysis. No product info or
  affiliate link had been supplied at integration time; the marketing
  package marks them MISSING.
- Vietnamese (vi-VN) narration/subtitles by default; no silent English
  TTS fallback. TTS failure stops the job.
- Gemini output is labelled `gemini` only when a real Gemini call
  produced it; otherwise the labelled fallback (or a labelled
  `human_review` record) is used. No key is hunted or stored by
  workers; the key arrives via the connector flow (see "Gemini seam"
  below).

## Confirmed flow (Mai, 2026-11-12 09:59)

Pasted Douyin link (seller-authorized) → authorization gate → fetch →
Gemini translates close to the original meaning → humorous dubbing →
export. URL-paste is the **primary** input; file upload is secondary.
The UI keeps this order: the link-paste block is prominent, the
upload control is the fallback.

## Douyin standing requirements (Mai, 2026-11-12 09:37 — "nhớ nhé")

1. **Translation** stays CLOSE to the original meaning ("bám sát
   nghĩa") for dubbing, in a **humorous, viral, review-style**
   Vietnamese voice. Humour in the wording only — facts, meaning,
   prices, measurements, and product claims stay faithful; the
   fidelity rules (no invented claims/discounts/urgency) still apply.
   Implemented as `TranslationRecord.style = "humorous_viral_review"`
   (see `translation.py`).
2. **Per-character dubbing**: each distinct Chinese speaker maps to
   its own Vietnamese voice, consistent across the video. Speaker
   labels flow ASR → translation → dub script → voice stage
   (`TranscriptSegment.speaker_id`, `ScriptSegment.speaker_id`,
   `VoiceConfig.speaker_voices`).
3. **VieNeu voices per character**: dubbing goes through the existing
   TTS provider abstraction with per-character voice assignment.
   `VOICE_PRESETS` in `voice.py` is the single seam where preset names
   bind to provider voice ids — the tts CLI voices on this VM, real
   VieNeu voices on Mai's Windows machine. The mapping is data
   (`speaker_voices`), never hardcoded.
4. **On-screen Chinese text**: BLUR the Chinese text regions, then
   OVERLAY Vietnamese subtitles on top. Blur is a video operation
   (`text_blur` on `SUBTITLE` / `PROMOTIONAL_OVERLAY` tracks;
   protected classes keep the approval gate). The overlay is the ASS
   subtitle engine (`captions.burn_filter_args`).

## Module map (final structure, Stage 1)

```
ai_clip_studio/affiliate/
  __init__.py            package doc + schema re-exports
  schema.py              AFFILIATE_PROJECT_V1 dataclasses, validator
                         (AFF001–AFF024 + gate codes), export gate,
                         snapshot hash, JSON Schema cross-check
  affiliate_project_v1.schema.json
  product.py             user-facts-only product rules, claim tripwire
  source_media.py        sha256, ffprobe intake, immutable source store
  asr.py                 faster-whisper Mandarin ASR + speaker labels
  translation.py         Gemini translation (3 modes, 2 styles) +
                         labelled fallback; OCR track translation
  script_gen.py          affiliate script generator (4 variants incl.
                         dubbed_translation) + approval lifecycle
  voice.py               TTS presets, per-speaker voice resolution,
                         real synthesis via tts_cli_provider
  audio_timeline.py      measured-audio timeline, mix plans, ffmpeg mix
  captions.py            ASS/SRT subtitle engine, safe zones, legibility
  marketing.py           captions/title/hashtags/CTA/disclosure package
  qa.py                  translation/voice/subtitle/audio/commercial QA
  store.py               JSON project store, 16-stage status
  affiliate_api.py       mount-ready HTTP handlers (GET/POST)
  affiliate_ui.py        Vietnamese single-page workspace (HTML/JS)
  providers.py           PROVIDER SEAMS (integration): Downloader,
                         OCREngine, TTSProvider, GeminiClient as
                         Protocols + thin adapters + registry + fakes
  link_input.py          LINK-PASTE INPUT (integration): prominent
                         paste-field HTML fragment + gated
                         handle_link_submit / handle_link_post
  pipeline_run.py        VERTICAL-SLICE GLUE (integration): thin
                         orchestration over A/B modules; CLI job runner
  video/                 Subagent A: CV + video editing
    models.py            BBox/TextRegion/SourceInfo/AnalysisReport/
                         MaskSpec/ReplacementSpec/SubtitleSlot/
                         TransformOp/ExportProfileSpec/QAReport,
                         export_gate_check, schema-dict converters
    capabilities.py      ffmpeg/ffprobe/filter/encoder probing, cv2 +
                         OCR backend probes, font discovery
    probe.py             ffprobe metadata, SHA-256, rotation, orientation
    analysis.py          scene cuts, silence, motion, edge/text
                         candidates, watermark heuristic, Haar faces
    ocr.py               PaddleOCR + RapidOCR adapters, tracking,
                         classifier, review queue, approve_removal gate
    text_replace.py      SMART_OVERLAY / LOCAL_BLUR / CROP_AND_REFRAME /
                         MANUAL_MASK / inpaint, filter-graph builder,
                         replacement_subtitle_slots
    transform.py         21 validated transforms, reframe math, reorder,
                         stabilize pre-pass, flip-safety assessment
    export.py            TIKTOK_REELS / FACEBOOK_REELS /
                         HIGH_QUALITY_MASTER, single-pass encode,
                         authorization gate first
    qa.py                ffprobe + blackdetect + freezedetect +
                         faststart + retention + sharpness/blockiness
                         proxies; PASS/FAIL/PENDING, no invented scores
    ingest.py            URL + authorization gate BEFORE any network
                         access; injectable downloader (none bundled);
                         immutable checksum-named store + manifest
```

Boundaries (backend quality bar, Mai 2026-11-12 09:59):

- A owns pixels: analysis, OCR, text replacement, transforms, export,
  video QA. B owns language/audio: schema, ASR, translation, script,
  voice, timeline/mix, captions, marketing, QA sections, API/UI.
- Neither side duplicates the other's logic. Glue (`pipeline_run.py`,
  `link_input.py`, `providers.py` adapters) orchestrates and adapts
  signatures only; it does not re-implement validation, mixing, QA,
  OCR, or export logic.
- Shared Story Studio modules reused by import (never modified):
  `subtitles.py`, `audio_events.py`, `timeline.py`, `language_gate.py`,
  `drive_uploader.py`, `qa_gates.py`, `production_request.py`,
  `gemini_planner.py`, `planner_fallback.py`, `tts_cli_provider.py`.
- Known duplications found at integration (D1–D3 below) are recorded
  as refactor backlog with exact locations; they were NOT fixed in
  Stage 1 (new-files-only rule). Do not add new copies.

## Provider seams (`providers.py`)

Four seams, each a `typing.Protocol` with a documented contract
(inputs, outputs, error behaviour), a thin adapter, a registry entry,
and a test-only fake. Registry: `get_provider(seam, name=None)` /
`register_provider` / `list_providers`.

| Seam | Default | Contract |
|---|---|---|
| `Downloader` | `yt-dlp` | `fetch(url, dest_dir) -> DownloadResult` or structured `DownloadFailure` (reason codes: `UNSUPPORTED_URL`, `COOKIES_REQUIRED`, `AUTH_REQUIRED`, `NETWORK_ERROR`, `NOT_FOUND`, `NOT_AVAILABLE`, `DOWNLOAD_FAILED`). `YtDlpDownloader` resolves the binary: explicit path > `PATH` > the `ytdlp` venv binary when present; a missing binary is an honest `NOT_AVAILABLE`, never a crash. **No cookies/credentials support exists in the interface, by design.** `as_ingest_downloader()` adapts fetch-style providers to the `ingest_source` callable shape. |
| `OCREngine` | `default` | `DelegatingOCREngine` delegates to `video/ocr.py` (`get_ocr_engine` lazily + `track_detections`). Zero OCR logic duplicated. |
| `TTSProvider` | `voice` | `VoiceTTSProvider` delegates to `voice.py` (presets, `synthesize_script`, `preview_voice`), which owns the `tts_cli_provider` / VieNeu seam. Zero TTS logic duplicated. |
| `GeminiClient` | `labelled_unavailable` | `translate(...) -> TranslationRecord`. The unavailable implementation makes no API call, reads no credential, returns zero translated segments + `needs_human_review=True`. `TranslationGeminiClient` delegates to `translation.translate_segments`. ALL key handling stays in `translation.py`; the seam adds no key parameter, env-var read, or secret path. |

### Gemini seam — enabling real Gemini (single change)

When Mai stores the key via the connector flow and the connector doc
wires the backend, Stage 2 swaps the registry default from
`labelled_unavailable` to `translation_adapter`. No pipeline, UI, or
handler code changes. Until then every translation/script result is
the labelled fallback or a labelled `human_review` record — never
presented as Gemini output.

## Data flow

```
PASTED LINK (primary) ──> authorization gate FIRST ──> fetch via
  Downloader seam ──> ingest_source (checksum + ffprobe + immutable
  store) ──> SourceVideo ──> pipeline (same as upload path)
FILE UPLOAD (secondary) ──> store_source_copy ──> SourceVideo ──┐
                                                                │
  -> analysis (scenes / silence / motion / watermark candidates)
  -> OCR (RapidOCR default; PaddleOCR adapter untested) -> tracks
       + classifications + review queue
  -> ASR (faster-whisper, zh, VAD, word timestamps)
       + speaker labels (single / manual ranges / pyannote seam)
  -> translation (Gemini, labelled fallback, or human_review) —
       original / translated / rewritten kept as SEPARATE records
  -> script (generated variants, or dubbed_translation 1:1 from
       translated segments) -> user edit + APPROVE
  -> voice (per-speaker presets -> real WAVs, measured durations)
  -> audio timeline (measured audio only; conflicts reported)
  -> mix (4 buses, ducking, fades) + subtitles (ASS/SRT, safe zones)
  -> text handling: blur approved SUBTITLE/PROMOTIONAL_OVERLAY
       regions, preserve labels/branding/attribution
  -> export (single-pass encode; TikTok/Facebook/Master profiles,
       CRF 17-19, 1080x1920) — see seam S1: subtitles + external mix
       currently need a documented 2nd pass
  -> QA (technical on real files; creative = REVIEW_REQUIRED)
  -> export gate -> Drive upload (AI_AFFILIATE_STUDIO, 9 subfolders)
```

Export profiles are config-driven (`video/models.py` presets +
`video/export.py`); adding a profile means adding preset data, not a
new encoder path.

## API (mount-ready; Stage 2 mounts into `server.py`)

`affiliate_api.handle_affiliate_get` / `handle_affiliate_post` take
the product server's handler and return True when they handled the
request. Mounting is a 2-line change in `server.py` plus a `_send_html`
helper — see the module docstring in `affiliate_api.py`.

| Method | Path | Notes |
|---|---|---|
| GET | `/affiliate` | Vietnamese workspace UI |
| GET | `/api/affiliate/health` | module + schema status |
| GET | `/api/affiliate/voices` | real voice presets |
| GET/POST | `/api/affiliate/projects` | list / create |
| GET | `/api/affiliate/projects/{id}` | project JSON |
| POST | `/api/affiliate/projects/{id}/link-fetch` | **NEW (integration, `link_input.py`): gated link fetch → SourceVideo; 400 bad URL, 403 gate refused (downloader never called), 404 unknown project, 502 fetch failure (honest status + upload fallback), 503 downloader unavailable, 422 unreadable download** |
| POST | `/api/affiliate/projects/{id}/upload-chunk` | chunked base64 upload |
| POST | `/api/affiliate/projects/{id}/upload-complete` | assemble + probe |
| POST | `/api/affiliate/projects/{id}/analysis` | ingest Subagent A analysis |
| POST | `/api/affiliate/projects/{id}/ocr-tracks` | ingest OCR tracks |
| POST | `/api/affiliate/projects/{id}/edits` | ingest edit ops + gate report |
| POST | `/api/affiliate/projects/{id}/transcribe` | background ASR (202) |
| POST | `/api/affiliate/projects/{id}/speakers` | manual speaker ranges |
| POST | `/api/affiliate/projects/{id}/translate` | mode + style |
| POST | `/api/affiliate/projects/{id}/script` | generate, or `source: translation` for dub script |
| POST | `/api/affiliate/projects/{id}/script/edit` | clears approval |
| POST | `/api/affiliate/projects/{id}/script/approve` | approval |
| POST | `/api/affiliate/projects/{id}/voice` | background TTS (202) |
| POST | `/api/affiliate/projects/{id}/voice/preview` | real preview phrase |
| POST | `/api/affiliate/projects/{id}/subtitles` | ASS + SRT |
| POST | `/api/affiliate/projects/{id}/mix` | mix plan + render |
| POST | `/api/affiliate/projects/{id}/marketing` | marketing package |
| POST | `/api/affiliate/projects/{id}/qa` | QA report |
| POST | `/api/affiliate/projects/{id}/export` | 403 when the gate refuses; 501 until Stage 2 wires A's render |
| GET | `/api/affiliate/projects/{id}/artifacts` | artifact listing |
| GET | `/api/affiliate/projects/{id}/files/{name}` | artifact download (traversal-guarded) |

### Stage 2 mount (exact, NOT applied in Stage 1)

1. `affiliate_api.py`: add `from .link_input import
   handle_link_post, match_link_fetch_path`, plus in
   `handle_affiliate_post` before the final `return False`:
   `match = match_link_fetch_path(path)` /
   `if match is not None: return handle_link_post(handler, match, body)`.
2. `server.py`: no new lines if the affiliate mount is already in
   place; the route rides the existing dispatch. Otherwise add the
   two dispatch lines documented in `affiliate_api.py`.
3. `affiliate_ui.py`: no file edit — inject
   `render_link_paste_section()` at request time with one
   `str.replace` on the anchor `<h2>1. Tạo dự án + tải video lên</h2>`.
4. Next.js: apply `frontend_patches/03-link-paste-input.patch` after
   patch 02; the catch-all proxy already forwards the new endpoint.
5. Wire A's `export_video` into the export endpoint (keep the 403
   gate first), merge A's QA sections, smoke-test BOTH modes,
   re-run the full Story Studio regression suite (must stay
   448/448).

## Intake quirks (recorded, do not re-derive)

- `ingest_source` probes the temp download file, so
  `record.probe["container"]` reflects the temp suffix (`"bin"`),
  not schema vocabulary. Any consumer of ingest records must derive
  the container from the STORED file's suffix (as `link_input.py`
  does via `ingest.store_filename`); otherwise schema validation
  fails with AFF022 on reload.
- `link_input` creates its own default `AffiliateStore()` at the
  default root (same root as `affiliate_api.STORE`) instead of
  importing `affiliate_api`, to avoid a circular import at Stage 2
  (the mount makes `affiliate_api` import `link_input`). Both store
  instances read/write the same JSON files.
- `validate_link_url` mirrors the URL-shape checks in
  `validate_ingest_request` deliberately: the handler needs 400-level
  input validation before the 403-level gate; ingest re-validates
  everything anyway.

## Refactor backlog (found at integration; NOT fixed in Stage 1)

Stage 1 forbade modifying existing files, so these stay as documented
backlog with exact locations. Fix in the order listed; S9 before
trusting blur on real Douyin videos.

- **D1 — `sha256_file` duplicated.** `source_media.py:20` and
  `video/probe.py:30` implement the same streaming hash (different
  signatures). One shared helper should exist.
- **D2 — ffprobe probing duplicated.** `source_media.probe_video`
  (dict) vs `video/probe.run_ffprobe` + `probe_source`
  (`SourceInfo`). Overlapping stream parsing, different shapes.
- **D3 — authorization vocabulary + gate duplicated.**
  `schema.AUTHORIZATION_TYPES` + `export_allowed` vs
  `video/models.AUTHORIZATION_TYPES` (+ `SYNTHETIC_FIXTURE`) +
  `export_gate_check` + `to_schema_authorization`. Two sources of
  truth with a manual mapping in between.
- **S1 — Export has no subtitle/mix inputs.** `export_video` accepts
  an `audio_filter` on the source audio but no ASS path and no
  external mix WAV, forcing the slice's documented 2nd pass
  (`pipeline_run.mux_final`). Add `ass_path`/`mix_wav` parameters or
  a filter-graph composition seam so the final encode stays
  single-pass.
- **S2 — No cross-venv OCR seam.** RapidOCR/cv2 live only in the
  `affiliate_cv` venv; the slice generates an `ocr_worker.py` and
  exchanges JSON via subprocess. `asr.py` already owns this pattern
  for the whisper venv — OCR needs the same owned seam inside
  `video/ocr.py`.
- **S3 — Gemini client seam is a private import.**
  `translation.py:41` and `script_gen.py:32` import `MODELS,
  _gemini_generate` from `..gemini_planner`. Replace with the public
  `GeminiClient` seam (`providers.py`); the key stays supplied via
  the connector, never hunted/stored by workers.
- **S4 — Timeline ignores dub timing windows.**
  `script_from_translation` preserves each line's original start/end
  on the `ScriptSegment`, but `build_affiliate_timeline` re-places
  segments sequentially from 0. For per-character dubbing the source
  timing is silently lost. Needs a timeline mode honouring original
  windows (or an explicit conflict when measured speech exceeds its
  window).
- **S5 — Snapshot hash invalidated by TTS.**
  `project_snapshot_hash` excludes stages/qa/output, but
  `synthesize_script` fills `voice_wav`/`measured_sec` on script
  segments after approval, so the hash changes post-approval. The
  approved-text snapshot should hash separately from measured
  artifacts.
- **S6 — No manual/human translation entry point.**
  `translation.py` offers only Gemini-or-fallback; the slice built a
  `TranslationRecord` directly with `engine="human_review"`. Add a
  `human_translation_record(...)` constructor validating the same
  fidelity rules.
- **S7 — `SubtitleSlot` boxes unused by captions.**
  `replacement_subtitle_slots` emits source-frame boxes, but
  `captions.build_ass` places all captions in the safe-zone area.
  Either captions accept slot-derived positions (mapped through the
  reframe), or slots are documented as timing-only.
- **S8 — Fade QA fails on equal silence.** `qa.audio_qa`
  (`smooth_fades`) requires strict `<` between adjacent windows;
  when both tail windows sit at the silence floor it FAILs although
  no hard cut exists. The equal-silence case should resolve to
  PENDING/unmeasurable instead of FAIL. (Measured on the slice:
  B QA 25/26, single FAIL `smooth_fades`.)
- **S9 — Moving-text blur is static per segment.** (MUST FIX before
  the Douyin job.) `build_replacement_filters` applies one static
  box per `ReplacementSpec` over its window; `segment_track`
  (piecewise median boxes) exists but is not wired into the export
  path. With 1 fps OCR sampling, fast-moving text escapes its box —
  measured on the slice at t=4.5 s (promo `限时优` legible). Needs
  denser sampling + tracked boxes + a QA check that re-OCRs the
  export to confirm blurred text is unreadable.
- **S10 — Two intake paths.** `video/ingest.ingest_source` (URL +
  injectable downloader) vs `source_media.store_source_copy` (local
  file), with separate manifests. One intake seam should serve both
  paths; the link-fetch handler is the first step.
- **Minor — TTS dual paths.** `voice.synthesize_script` has a
  shared-provider fast path and a per-segment path with duplicated
  decode/measure steps. Works; fragile seam; not urgent.
- **Minor — `pipeline_run.run_slice` is long** (~430 lines, one
  slice-specific orchestrator). If it grows beyond the slice, split
  it into a proper job runner instead of extending it.

## Install commands (this VM / Linux)

```bash
# System tools (already present on this VM; listed for a fresh box)
sudo apt-get install -y ffmpeg fonts-dejavu-core

# Python deps for schema cross-checks
pip install jsonschema

# faster-whisper lives in its own venv (do NOT install into system python):
#   ~/workspace/.venvs/whisper  (faster-whisper 1.2.1, models tiny/small/medium cached)
# The ASR worker runs under that venv's python automatically.

# RapidOCR/cv2 live in their own venv:
#   ~/workspace/.venvs/affiliate_cv  (opencv-python-headless 5.0.0,
#   rapidocr-onnxruntime 1.4.4, onnxruntime 1.31.1)

# yt-dlp lives in its own venv (Downloader seam default):
#   ~/workspace/.venvs/ytdlp  (yt-dlp 2026.10.26)

# TTS: /opt/hatch/bin/tts (shared provider). No install; requires the
# provider binary + network, like the production pipeline.
```

Known environment notes (verified 2026-11-12):

- `GEMINI_API_KEY` is absent: translation/script stages run the
  clearly-labelled fallback. Real Gemini applies when Mai stores the
  key via the secure connector flow and the backend is wired to it
  (registry-default swap, see "Gemini seam" above).
- VieNeu-TTS is absent: synthesis goes through `tts_cli_provider`.
- PaddleOCR is **not installed** (adapter written, untested).
  RapidOCR is the proven default on this VM.
- PyAV 19.0.2 breaks faster-whisper 1.2.1's file-path API; `asr.py`
  passes a numpy array instead (same workaround as
  `acceptance_loop/transcribe_check.py`).
- FFmpeg 8.1.2 on this VM exposes `sidechaincompress`, not
  `sidechaincompressor`; the mix builder probes for either.
- `pyannote.audio` is not installed: automatic diarization is
  unavailable; speaker labels come from explicit user ranges.
- opencv-python-headless 5.0.0 ships no Haar cascade XMLs: face
  detection reports unavailable; zero faces fabricated. No hand
  model is wired; product visibility is a labelled heuristic.
- **Douyin fetch ground truth (2026-11-12):** yt-dlp 2026.10.26
  rejects the `so.douyin.com` share URL (`Unsupported URL`) and the
  canonical `douyin.com/video/<id>` URL requires fresh cookies,
  which are forbidden. No Douyin video was fetched. Remaining
  routes: a live-browser fetch arranged by ATLAS, or Mai supplying
  the video file directly.

## Limitations (Stage 1)

- The export endpoint still returns 501 until Stage 2 wires A's
  render (render itself is proven via direct calls in the slice).
- Video/OCR/export QA sections report `NOT_RUN` in B's report by
  design (A's sections); integration presents both reports together.
- Creative QA is always `REVIEW_REQUIRED` — no fabricated creative
  pass. Pronunciation ear-check stays `PENDING` until a human listens.
- Moving-text blur gap (S9): verified defect on the slice; fix
  before trusting blur on real Douyin videos.
- The Next.js patches (02, 03) are verified with `git apply --check`
  only (+ esbuild TSX syntax check); `npm run build` needs Mai's
  Windows box.
- Per-character dubbing with real speech is code-complete but was
  NOT exercised by the fixture (no speech/faces/multi-speaker
  content). It needs the real Douyin job.
- No GitHub push for this module without Mai's explicit approval.
