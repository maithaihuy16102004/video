# STATUS — AI Clip Studio

**Trạng thái cuối: `IMPLEMENTATION_IN_PROGRESS`**

## Cập nhật 2026-11-11 (vòng v4 + frontend patches + animation primitives)

- **Draft v4 ĐẠT NGƯỠNG 8.75/10** (Eiffel Tower, render bằng code của tool,
  không clip AI): MP4 trên Drive `1GHeD4Siibtz2fx2FXLV1DaKjCWk6zaWp`,
  evaluation `1r47a-u85d4kesQ-3zzcwGKkjDasXvdXi`, mọi hạng mục ≥ 7.0,
  không hard fail, re-test giữ điểm. Chi tiết:
  `~/workspace/acceptance_loop/BAO_CAO_VONG_LAP.md` (mục Vòng 4).
- **Motion Canvas đã thử và BỊ CHẶN với lý do kỹ thuật rõ ràng:** Chrome duy
  nhất trên VM `/opt/meta-chromium/chrome` không launch được làm puppeteer
  executable — `Hatch WebGL domain policy is required for browser startup`
  (kiểm chứng trực tiếp 2026-11-11); không có chromium/google-chrome khác.
  Vì vậy v4 dùng renderer frame-by-frame (rig 12 khớp V51, 24 fps, 514 frame).
- **Mới:** `chrome_detect.py` (tự động phát hiện + launch-probe Chrome,
  thay cho đường dẫn Windows hard-code; `upstream.check_render_available()`
  đã dùng nó và báo fallback frame-by-frame), `animation/` (rig V51 +
  primitives data-driven walk/run/look/point/wave/reach/give/shrug/
  cover-face/nod/sit/stand — có test bone-length invariant),
  `frontend_patches/01-universal-preflight-and-production-api.patch`
  (patch thật, `git apply --check` pass trên clone `c4832c8`, 7 file TSX
  pass esbuild syntax check) + `frontend_patches/README.md`.
- **Unit test: 43/43 pass** (`ai_clip_studio/tests/`, gồm 5 animation
  primitives + 4 chrome-detect mới), cộng 11/11 `youtube_16x9`.
- **Orchestrator end-to-end VẪN CHƯA CHẠY ĐƯỢC trên VM này** (xem lý do
  chặn bên dưới) — v4 được render bởi renderer frame-by-frame độc lập,
  chưa đi qua `UniversalProductionPipeline`. Vì vậy trạng thái chung vẫn
  là `IMPLEMENTATION_IN_PROGRESS`, không phải `END_TO_END_DRAFT_READY_FOR_REVIEW`.

## Lý do chặn (chính xác, đã kiểm chứng trên VM này)

Job production thật dừng ở stage 4/19 `GEMINI_STORY_PLANNING`:
`GEMINI_API_KEY is not set — V5UniversalStoryDirector cannot call Gemini
(pipeline/universal/v5_story_director.py:90-91)`, và import director
cũng thiếu `pydantic` (`ModuleNotFoundError`). Các blocker tiếp theo
sau khi qua được Gemini (đã kiểm chứng từng cái):
- Stage 9 `GENERATE_VIETNAMESE_TTS`: package `vieneu` không có trên VM.
- Stage 14 `RENDER_MOTION_CANVAS_THREEJS`: renderer hard-code Chrome
  Windows `C:\Program Files\Google\Chrome\Application\chrome.exe`.
  Đã sửa ở tầng pipeline: `chrome_detect.py` tự động phát hiện Chrome
  trên máy đang chạy (env `CHROME_PATH`, PATH, `/opt/meta-chromium/chrome`)
  và kiểm chứng bằng cách launch thử. Trên VM này không có Chrome nào
  launch được (lỗi Hatch WebGL domain policy, xem trên) → fallback
  frame-by-frame (`ai_clip_studio/animation/`, tham chiếu
  `~/workspace/acceptance_loop/v4/`).

**Không có MP4 thật nào được render từ orchestrator trong đợt này.**
(Draft v4 8.75/10 trên Drive là sản phẩm của renderer frame-by-frame
độc lập — cùng code animation primitives của tool, chưa đi qua 19 stage.)

## Những gì chạy được ở đây (đã kiểm chứng)

- Audit 17 mục + 5 trạng thái từng component: `AUDIT.md`.
- `ProductionRequest` bất biến + hash chain 6 stage; timeline động đo
  WAV thật, không cap, guard cắt câu cuối; preflight PASS/FAIL;
  audio event map + luật meme + stems; Drive uploader cấu trúc
  01..06 + verify + dedup (mock Drive trong test).
- Orchestrator 19 stage với log có cấu trúc, job status persistent
  (`jobs/{job_id}/status.json`), stage nào thiếu dependency thì FAIL
  với diagnostic — không mock success.
- Server API stdlib: `python -m ai_clip_studio.server --port 8788`
  (đã test thật: `/health`, `/api/production/analyze`,
  `/api/production/preflight`, `/api/production/draft` → 202 + job_id,
  `GET /api/production/jobs/{id}`, `/artifacts`).
- Smoke test: `python -m ai_clip_studio.smoke_test --script <file>`
  (đã test thật: dừng ở stage 4 với diagnostic Gemini, exit 1).
- Unit test: **43 test pass** (`ai_clip_studio/tests/`), cộng
  **11 test** của `youtube_16x9` vẫn pass.
- Frontend patches thật (không chỉ hướng dẫn): `frontend_patches/`
  — preflight generic + 4 route proxy `/api/production/*` + nút
  Generate Draft / Approve Master trên `app/page.tsx`; đã kiểm chứng
  `git apply --check` trên clone mới `c4832c8` và cú pháp TSX bằng esbuild.
- Chrome auto-detect + animation primitives data-driven (xem mục cập nhật
  ở đầu file).
- Generalization: 3 kịch bản chưa thấy (đối thoại trong nhà, hành
  động ngoài trời, hài có meme) — mode production BLOCKED ở stage 4;
  mode test doubles 19/19 stage PASS, DRAFT_READY. Xem
  `GENERALIZATION_TESTS.md`.
- Bug thật tìm được và đã sửa: narration có dấu `:` bị nhận nhầm
  thành dialogue (G3) — sửa `DIALOGUE_RE`, có test hồi quy.

## Files created (mới trong `ai_clip_studio/`, additive, không sửa file gốc)

- `production_request.py`, `preflight.py`, `timeline.py`,
  `audio_events.py`, `drive_uploader.py`, `pipeline.py` (đợt trước)
- `upstream.py` (adapter import code thật read-only),
  `orchestrator.py` (19 stage), `server.py`, `smoke_test.py`,
  `run_generalization.py`, `__init__.py` (cập nhật export)
- `tests/test_ai_clip_studio.py` (28 test), `tests/test_orchestrator.py`
  (5 test + 1 test hồi quy dialogue)
- `AUDIT.md`, `FRONTEND_WIRING.md`, `GENERALIZATION_TESTS.md`,
  `STATUS.md` (file này), `MASTER_PROMPT.md`, `README.md`

Không sửa file nào trong `~/workspace/video-upstream/`. Không push
GitHub. Không tạo frontend mới. Không hardcode truyện.

## Components reused (code thật, không copy-paste)

- `pipeline/studio_script_v1_parser.py` — parse Studio Script V1.
- `pipeline/meme_resolver.py` + `assets/memes/catalog.json` (188 meme).
- `pipeline/universal/v5_story_director.py` — Gemini director (khi đủ key/deps).
- `pipeline/universal/v5_audio_director.py`, `pipeline/universal/sfx/*`,
  `pipeline/universal/voice/*` — nền tảng audio (chưa nối trực tiếp
  vì thiếu deps trên VM).
- `pipeline/studio_api.py` — mẫu endpoint/job (`/api/render`,
  `/api/status`, hash check) mà server mới adapt theo.
- `pipeline/video_quality_gate.py`, `youtube_16x9/pipeline/evaluate_16x9.py`
  — validation.

## API endpoints thật (server mới, port 8788)

- `POST /api/production/analyze`, `POST /api/production/preflight`
- `POST /api/production/draft` → `{job_id}` 202, chạy background
- `GET /api/production/jobs/{job_id}`, `GET /api/production/jobs/{job_id}/artifacts`
- `POST /api/production/jobs/{job_id}/approve-master`
- `POST /api/production/jobs/{job_id}/retry-upload` (trả 501, chưa implement — ghi rõ)

## Startup / smoke-test commands

```bash
cd ~/workspace/video-16x9-v2
python3 -m ai_clip_studio.server --port 8788
python3 -m ai_clip_studio.smoke_test --script <file.txt>
python3 -m unittest discover -s ai_clip_studio/tests
python3 ai_clip_studio/run_generalization.py
```

## Mai cần làm (theo thứ tự)

1. **Cấp quyền GitHub App** cho repo `video` để push được cây
   `video-16x9-v2/` (đang 403) — rồi pull code về máy Windows.
2. **Duyệt patch 01/02** (`patches/`, đã sửa xong và kiểm chứng
   `git apply`): khóa headRatio 0.142–0.155 và sửa lỗi TTS cắt câu cuối.
3. **Chạy trên máy Windows của cô ấy:** backend cũ
   `python pipeline/studio_api.py` (port 8787) + server mới
   (port 8788), với `GEMINI_API_KEY`, `pip install pydantic vieneu`
   (theo `requirements` của repo), Chrome đã cài, frontend Next.js
   (`sites/ai-clip-studio/`, `pnpm dev`).
4. **Áp frontend patch** trên máy Windows (xem
   `frontend_patches/README.md`): `git apply
   ai_clip_studio/frontend_patches/01-universal-preflight-and-production-api.patch`,
   rồi `npm run build` / `npm run lint` để kiểm tra lần cuối (trên VM này
   chỉ kiểm được cú pháp TSX bằng esbuild, chưa chạy được build đầy đủ
   vì thiếu node_modules).
5. Sau đó chạy smoke test trên máy cô ấy với một kịch bản mới; khi
   MP4 thật validate + upload Drive thành công thì trạng thái mới
   chuyển sang `END_TO_END_DRAFT_READY_FOR_REVIEW`, và chỉ sau khi cô
   ấy bấm approve-master mới thành `MASTER_APPROVED_AND_UPLOADED`.
