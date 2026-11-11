# Frontend patches — AI Clip Studio (universal preflight + production API)

Real unified diffs (generated from edited files, like `patches/01` and
`patches/02`). Apply on Mai's Windows machine, in the repo root
(`D:\Agent`, repo `maithaihuy16102004/video`, commit `c4832c8`).

## Apply

```powershell
cd D:\Agent
git apply --check ai_clip_studio/frontend_patches/01-universal-preflight-and-production-api.patch
git apply ai_clip_studio/frontend_patches/01-universal-preflight-and-production-api.patch
```

Verified 2026-11-11 on this Linux VM: `git apply --check` passes on a
fresh clone of `c4832c8`, the patch applies cleanly, and all 7 touched
files pass an esbuild TSX syntax check. Full `npm run build` / `npm run
lint` still needs to run on Windows (node_modules are not in the repo).

## What the patch changes (7 files)

| File | Change |
|---|---|
| `sites/ai-clip-studio/app/api/preflight/route.ts` | **Removes the Episode01-only gate.** Old: exactly 8 scenes, exactly 4 characters, memes "ối dồi ôi" / "gòi gòi" / "Among Us", no memes in scenes 3/4/6/7/8, scene 08 camera variety, every location must mention Munich 1914. New: generic checks for ANY script (structured or free-form) — scenes complete, ≥1 character/speaker, memes reported not required, meme not inside dialogue, no metadata leak into TTS, final scene has camera variety, locations consistent on period/year. Also merges the pipeline preflight (`PRODUCTION_BACKEND_URL`, default `http://127.0.0.1:8788`) best-effort with a 2 s timeout; unreachable backend is a warning, never a fabricated PASS. |
| `sites/ai-clip-studio/components/PreflightPanel.tsx` | Generic labels/counts (no more "/ 8 cảnh", "/ 4 nhân vật", "3/3 MP3", "Munich 1914"); dynamic passed-count badge; new optional `onReport(passed)` callback so the page can gate Master on the real verdict; warnings section. |
| `sites/ai-clip-studio/app/page.tsx` | Master-winner gate now uses the real `preflightPassed` state instead of `script.includes("SCENE 08")`. Adds a **Unified Pipeline** section: "Tạo Draft qua Unified Pipeline" button (POST `/api/production/draft`), live polling of the real job, clickable Google Drive link when ready, and an **Approve Master** button (disabled until the draft is `END_TO_END_DRAFT_READY_FOR_REVIEW`). The legacy 3-variant render flow on 8787 is untouched. |
| `sites/ai-clip-studio/app/api/production/draft/route.ts` | **New.** Proxies POST to 8788 `/api/production/draft`, returns `{job_id}` 202. 503 with a clear message when 8788 is not running. |
| `sites/ai-clip-studio/app/api/production/jobs/[jobId]/route.ts` | **New.** Proxies GET job status from 8788 and flattens `drive_links` / `drive_url` out of the `RETURN_DRIVE_LINKS` stage. |
| `sites/ai-clip-studio/app/api/production/approve-master/route.ts` | **New.** Proxies POST to 8788 approve-master. Backend returns 409 unless the draft is ready for review — no auto-approval. |
| `sites/ai-clip-studio/app/api/production/retry-upload/route.ts` | **New.** Proxies POST to 8788 retry-upload. **Honest limitation:** the pipeline server currently returns 501 for this (not implemented yet); the route passes that through instead of faking success. |

## Run after applying

```powershell
# Terminal 1: legacy backend (8787) — already exists
# Terminal 2: unified pipeline server (8788)
python -m ai_clip_studio.server --port 8788
# Terminal 3: frontend (Next.js, NOT Vite 5173 — see AUDIT.md)
npm run dev
```

Set `PRODUCTION_BACKEND_URL=http://127.0.0.1:8788` and
`RENDER_BACKEND_URL=http://127.0.0.1:8787` if the ports differ.
