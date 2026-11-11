# GENERALIZATION TESTS — orchestrator trên 3 kịch bản chưa thấy trước

Ngày chạy: 2026-11-11, trên Linux VM này.
Runner: `ai_clip_studio/run_generalization.py` (dùng đúng
`UniversalProductionPipeline`, không có đường render riêng cho test).

## Phân biệt rõ: mocked test vs real integration test

- **Mode A — production thật, không injection nào.** Đây là integration
  test thật: parser thật, Gemini thật, TTS thật, render thật. Kết quả
  dưới đây là kết quả thật.
- **Mode B — test doubles có ghi nhãn.** Planner fallback (xây package
  từ segmentation thật, KHÔNG phải Gemini), voice provider viết file WAV
  thật (silent 2.0s, đo bằng `wave`), render viết MP4 thật bằng ffmpeg
  (testsrc 1920x1080/24fps + sine tone), Drive client là mock
  (không gọi Drive thật). Mode B chỉ chứng minh máy móc 19 stage chạy
  đúng thứ tự và pass/fail đúng chỗ — **không chứng minh render Motion
  Canvas thật chạy được**.

## Kịch bản (viết mới cho test này, không dùng Eiffel/Munich)

- **G1 — đối thoại trong nhà:** Minh và Lan ở quán cà phê, trao thư.
  161 ký tự, 2 nhân vật, 5 câu.
- **G2 — hành động ngoài trời:** Haru chạy qua cầu gỗ trong mưa, ván
  bật, ngã, bám lan can, giữ thư khô. 197 ký tự, 1 nhân vật.
- **G3 — hài có meme cue:** Tuấn khoe video AI, Minh cười "Ối dồi ôi",
  gõ cửa/mở cửa, "Gòi gòi tới công chuyện". 190 ký tự, 2 nhân vật.

## Kết quả thật

| Kịch bản | Mode A (production) | Mode B (test doubles) |
|---|---|---|
| G1 indoor dialogue | BLOCKED — stages 1–3 PASS, stage 4 `GEMINI_STORY_PLANNING` FAILED: `GEMINI_API_KEY is not set` | DRAFT_READY — 19/19 stage PASS, MP4 thật 100.477 bytes |
| G2 outdoor action | BLOCKED — stages 1–3 PASS, stage 4 FAILED: `GEMINI_API_KEY is not set` | DRAFT_READY — 19/19 stage PASS, MP4 thật 100.477 bytes |
| G3 comedy meme | BLOCKED — stages 1–3 PASS, stage 4 FAILED: `GEMINI_API_KEY is not set` | DRAFT_READY — 19/19 stage PASS, MP4 thật 100.477 bytes |

Chi tiết Mode A (giống nhau cả 3 kịch bản):
- `RECEIVE_SCRIPT` PASS, `FREEZE_SCRIPT_SNAPSHOT` PASS (snapshot +
  `production_request.json` ghi ra đĩa), `PARSE_SCRIPT` PASS bằng
  `StudioScriptV1Parser` thật.
- `GEMINI_STORY_PLANNING` FAILED: `GEMINI_API_KEY is not set —
  V5UniversalStoryDirector cannot call Gemini
  (pipeline/universal/v5_story_director.py:90-91)`. Không có mock
  package nào được trả về; job dừng, `status.json` persistent ghi rõ
  lý do.
- Các stage sau (TTS, render, upload) chưa tới được — đúng thiết kế:
  fail sớm, fail rõ.

Chi tiết Mode B (giống nhau cả 3 kịch bản):
- 19/19 stage PASS, trạng thái cuối `END_TO_END_DRAFT_READY_FOR_REVIEW`,
  MP4 100.477 bytes (ffmpeg testsrc — giống nhau cả 3 vì render test
  không dùng nội dung kịch bản; đây là giới hạn của test double, đã
  ghi rõ).
- Timeline động đo từ WAV thật: mỗi câu 2.0s + pause 0.5s + tail 0.5s.

## Bug tìm được nhờ test này (đã sửa, có test hồi quy)

- G3 lần chạy đầu FAIL ở `RUN_PREFLIGHT`: câu narration
  "Minh cười và nói: Ối dồi ôi..." bị nhận nhầm thành dialogue với
  speaker "Minh cười và nói", nên preflight báo giọng không có trong
  registry. Đã sửa `DIALOGUE_RE` trong `pipeline.py`: speaker chỉ còn
  tối đa 2 từ viết hoa. Thêm test
  `test_narration_with_colon_is_not_dialogue`. Chạy lại: G3 PASS.

## Kết luận

- Orchestrator khái quát được qua 3 thể loại khác nhau mà không viết
  renderer riêng cho từng truyện, không hardcode tên nhân vật hay số
  cảnh — cùng một code, cùng một thứ tự 19 stage.
- Production thật trên VM này dừng ở stage 4 (Gemini). Muốn chạy tiếp
  cần máy Windows của Mai: `GEMINI_API_KEY`, package `pydantic` +
  `vieneu`, Chrome Windows cho render.
- Bằng chứng cũ trên Windows (2026-11-08, `V5_GENERALIZATION_TEST_REPORT.md`):
  3 script chưa thấy (Thượng Hải 1930, Chợ Rẫy ER, Sahara 2050) đều
  PASS end-to-end với engine V5.0 — cho thấy pipeline gốc khái quát
  được khi đủ dependency; việc còn lại là nối nó vào orchestrator này.
