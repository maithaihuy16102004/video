# AI Clip Studio — README

Lớp additive trên V5.1 Universal Cinematic Pipeline, theo Master Prompt
của Mai (`MASTER_PROMPT.md`). Không sửa file gốc nào trong
`~/workspace/video-upstream/`, không push GitHub khi chưa có quyền.

## Chạy

```bash
cd ~/workspace/video-16x9-v2
python3 -m ai_clip_studio.server --port 8788        # API orchestrator
python3 -m ai_clip_studio.smoke_test --script <file.txt>
python3 -m unittest discover -s ai_clip_studio/tests
python3 ai_clip_studio/run_generalization.py
```

## Modules

| File | Vai trò |
|---|---|
| `production_request.py` | ProductionRequest bất biến, script_hash sha256, hash chain 6 stage |
| `preflight.py` | PASS/FAIL: hash, asset, giọng, timeline, output config |
| `timeline.py` | Timeline động từ thời lượng TTS thật; không cap, không cắt, không tăng tốc |
| `audio_events.py` | Map event→SFX, luật meme, stems, ducking −14 dB |
| `drive_uploader.py` | Drive root `1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm`, cấu trúc 01..06, verify + dedup |
| `pipeline.py` | `run_production()` (luồng gọn, dùng cho test nhanh) |
| `upstream.py` | Adapter import code thật read-only + diagnostics từng dependency |
| `orchestrator.py` | `UniversalProductionPipeline` — 19 stage theo đúng thứ tự Master Prompt |
| `server.py` | API stdlib: analyze / preflight / draft / jobs / approve-master / retry-upload |
| `smoke_test.py` | CLI chạy đúng orchestrator như API, fail thật khi thiếu dependency |
| `run_generalization.py` | Chạy 3 kịch bản chưa thấy, 2 chế độ (production / test doubles) |

## Docs

- `AUDIT.md` — đối chiếu 17 mục + 5 trạng thái từng component thật
- `FRONTEND_WIRING.md` — frontend gọi gì, sửa dòng nào (file + dòng)
- `GENERALIZATION_TESTS.md` — kết quả thật 3 kịch bản
- `STATUS.md` — trạng thái cuối + việc Mai cần làm
- `MASTER_PROMPT.md` — tài liệu gốc của Mai

## Trạng thái hiện tại

`BLOCKED_WITH_EXPLICIT_REASON` — xem `STATUS.md`. Production thật
dừng ở stage 4 (Gemini: thiếu `GEMINI_API_KEY` + `pydantic`); tiếp
theo là VieNeu (`vieneu` thiếu) và render (Chrome Windows). Mọi stage
thiếu dependency đều FAIL với diagnostic, không mock success.
