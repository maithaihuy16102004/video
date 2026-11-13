# FRONTEND WIRING — nối frontend hiện có vào orchestrator mới

## 1. Frontend hiện tại là gì (kiểm chứng, không đoán)

- **Không phải Vite dev server port 5173.** Frontend thật là **Next.js 16**
  trong `~/workspace/video-upstream/sites/ai-clip-studio/` (`package.json`:
  `"next": "16.3.4"`, engines `node >=22.13.0`, script `dev` chạy qua
  `scripts/run-framework.mjs`, script `start` chạy wrangler/Cloudflare).
  Không tìm thấy `localhost:5173`/`127.0.0.1:5173` trong repo. Port 5173
  trong Master Prompt có lẽ là Vite mặc định Mai nhớ — khi Mai chạy
  frontend, cần xác nhận cô ấy chạy bằng lệnh nào (`pnpm dev` qua
  run-framework hay một Vite app khác). Port 9000 trong `vite.config.ts`
  ở root repo là **Motion Canvas**, không phải frontend.
- Frontend **không gọi trực tiếp backend Python**. Nó gọi các route
  Next.js của chính nó (`/api/*`), và các route đó proxy sang backend
  Python qua biến `RENDER_BACKEND_URL`, mặc định
  `http://127.0.0.1:8787` (backend `pipeline/studio_api.py`).

## 2. Mapping: frontend gọi gì hôm nay → endpoint mới tương ứng

| Frontend gọi (file:dòng) | Route Next.js hiện tại | Backend Python hiện tại | Endpoint mới (`ai_clip_studio/server.py`, port 8788) |
|---|---|---|---|
| `app/page.tsx:438` `fetch("/api/plan")` (Analyze) | `app/api/plan/route.ts:308-309` → `POST {backend}/api/story-world` | `studio_api.py:2410` `POST /api/story-world` (Gemini/director + V1 parser) | `POST /api/production/analyze` — planning stages 1–8 |
| `app/page.tsx:464` `fetch("/api/plan")` (lần 2, review) | như trên | như trên | như trên |
| `app/page.tsx:474` `fetch("/api/review-content")` | `app/api/review-content/route.ts:8` → `POST {backend}/api/review-content` | `studio_api.py:2565` | giữ nguyên (chưa có endpoint mới) |
| `app/page.tsx:500` `fetch("/api/gemini")` | `app/api/gemini/route.ts:8` → `POST {backend}/api/settings/gemini` | `studio_api.py:2553` | giữ nguyên |
| `app/page.tsx:526` `fetch("/api/render")` (Generate Draft) | `app/api/render/route.ts:3` → `POST {backend}/api/render` | `studio_api.py:2605` `POST /api/render` → trả `{id, status: queued}` 202, worker thread | `POST /api/production/draft` — trả `{job_id, status: queued}` 202, orchestrator 19 stage chạy background |
| `app/page.tsx:545` `fetch(/api/status?id=...)` | `app/api/status/route.ts:3` → `GET {backend}/api/status?id=` | `studio_api.py:2684` `GET /api/status` | `GET /api/production/jobs/{job_id}` — trạng thái + từng stage, persistent trên đĩa |
| `app/page.tsx:579` `fetch("/api/review")` | `app/api/review/route.ts:8` → `POST {backend}/api/review` | `studio_api.py:2584` | giữ nguyên |
| `app/page.tsx:596` `fetch(/api/status?id=...)` | như trên | như trên | `GET /api/production/jobs/{job_id}` |
| `app/page.tsx:641` `<PreflightPanel .../>` | `components/PreflightPanel.tsx` (350 dòng) | không gọi backend — preflight chạy **trong trình duyệt** | `POST /api/production/preflight` — preflight thật phía server |
| `app/api/video/route.ts:2` | proxy `GET {backend}/videos/{id}/{file}` | `studio_api.py` phục vụ file video | chưa có endpoint mới (artifacts lấy qua `GET /api/production/jobs/{id}/artifacts`) |

## 3. Mai cần sửa dòng nào để gọi endpoint mới (trên máy cô ấy)

Không tạo frontend mới. Các sửa đổi tối thiểu, đều trong
`sites/ai-clip-studio/`:

1. **Generate Draft → orchestrator mới.** `app/page.tsx:526`:
   đổi `fetch("/api/render", ...)` thành `fetch("/api/production/draft", ...)`.
   Hoặc không đổi `page.tsx`, mà sửa proxy `app/api/render/route.ts:3`:
   đổi `${backend()}/api/render` thành `http://127.0.0.1:8788/api/production/draft`
   (và đổi tên field trả về `id` → `job_id` nếu frontend đọc `j.id` ở
   `page.tsx:545`).
2. **Poll trạng thái → orchestrator mới.** `app/page.tsx:545` và `:596`:
   đổi `` `/api/status?id=${j.id}` `` thành
   `` `/api/production/jobs/${j.job_id}` ``. Response mới có dạng
   `{job_id, status, stages: [{stage, status, detail, artifacts}], ...}`
   thay vì `{status, message}` của backend cũ — cần map `status`:
   `queued/running` → `IMPLEMENTATION_IN_PROGRESS`,
   `failed` → `BLOCKED_WITH_EXPLICIT_REASON`,
   `done` → `END_TO_END_DRAFT_READY_FOR_REVIEW`.
3. **Preflight → server thật.** `components/PreflightPanel.tsx`:
   thay logic preflight trong trình duyệt bằng
   `POST /api/production/preflight` với body `{script, available_voices}`.
   **Bắt buộc** vì `app/api/preflight/route.ts` hiện hardcode luật
   Episode01 (xem §4).
4. **Approve Master (mới, chưa có UI).** Thêm nút gọi
   `POST /api/production/jobs/{job_id}/approve-master` — chỉ enable khi
   job ở trạng thái `END_TO_END_DRAFT_READY_FOR_REVIEW`.
5. **Chạy 2 backend cùng lúc trên máy Mai:**
   - Backend cũ: `python pipeline/studio_api.py` → `127.0.0.1:8787`
   - Orchestrator mới: `python -m ai_clip_studio.server --port 8788`
     (chạy từ `~/workspace/agent/` sau khi push code lên repo
     và pull về máy cô ấy — hiện chưa push được vì GitHub App chưa có
     quyền, xem STATUS.md).

## 4. Cảnh báo: PreflightPanel hiện tại hardcode Episode01

`app/api/preflight/route.ts` yêu cầu **đúng 8 scene, đúng 4 nhân vật,
địa danh Munich 1914, đúng 3 meme** ("ối dồi ôi", "Gòi gòi tới công
chuyện", "Among Us Role Reveal") và không có meme ở scene 3,4,6,7,8.
Mọi kịch bản khác đều FAIL preflight ở frontend dù backend có thể làm
được. Đây là điểm DISCONNECTED/BROKEN đối với mục tiêu "dùng chung cho
mọi kịch bản". Sửa bằng cách thay route này bằng proxy tới
`POST /api/production/preflight` (mục 3 ở trên) thay vì sửa từng luật.
