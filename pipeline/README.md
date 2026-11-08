# Pipeline — Tự động hoá A-Z làm video content

Bước còn thiếu trong workspace: **kịch bản tự động**, **dịch phụ đề SRT**,
**tạo thumbnail tự động**, và một **pipeline gộp** chạy hết quy trình h2dev:
*chủ đề → kịch bản → giọng đọc → hình ảnh → edit → thumbnail*.

## Cài đặt

```bash
pip install edge-tts pillow numpy      # giọng đọc + render
# FFmpeg trong PATH
```

## 1. Pipeline A-Z (1 lệnh duy nhất)

```bash
# Có API key (tự sinh kịch bản bằng LLM)
set DEEPSEEK_API_KEY=sk-...
python pipeline/pipeline.py "kinh tế thị trường" --voice hoaimy --theme gold

# Không có API (tự soạn ý chính)
python pipeline/pipeline.py --title "Kinh tế thị trường" \
  --points "Cung và cầu|Giá cả|Cạnh tranh|Vai trò nhà nước|Lạm phát" \
  --voice namminh --badge "KINH TẾ"

# Dùng kịch bản có sẵn
python pipeline/pipeline.py --script pipeline/scripts/kinh_te_thi_truong.json --voice hoaimy
```

Xuất ra `pipeline/output/`:
- `<tên>_script.json` — kịch bản đầy đủ (sửa và render lại được)
- `<tên>_voice.mp3` — giọng đọc tiếng Việt
- `<tên>.mp4` — video dọc 1080×1920 có giọng đọc
- `<tên>_thumb.jpg` — ảnh bìa
- `<tên>_pipeline.json` — báo cáo

## 2. Sinh kịch bản từ chủ đề

`generator.py` thử lần lượt **DeepSeek → Claude → OpenAI** (theo env key có sẵn),
nếu không có key nào thì fallback về template charmotion.

| Biến môi trường | Provider |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek (`deepseek-chat`) |
| `ANTHROPIC_API_KEY` | Claude |
| `OPENAI_API_KEY` | OpenAI |

## 3. Dịch phụ đề SRT/VTT

```bash
python pipeline/srt.py video.srt --src en --dst vi -o output/video_vi.srt

# Dịch + sinh luôn voiceover từ phụ đề đã dịch
python pipeline/srt.py video.srt --voice hoaimy --tts-out output/voiceover.mp3
```

Giữ nguyên mốc thời gian, dịch theo batch 15 cue để tránh lệch số dòng.

## 4. Thumbnail

```bash
python pipeline/thumbnail.py --title "Kinh tế thị trường là gì?" \
  --subtitle "Giải thích trong 60 giây" --badge "KINH TẾ" \
  --theme gold --size horizontal -o output/thumb.jpg
```

Theme: `dark` `gold` `red` `blue` `green` · Size: `horizontal` (1280×720)
`vertical` (1080×1920) `square`.

## Lưu ý

- Nếu chưa cài `edge-tts`, pipeline vẫn render video nhưng **không có giọng đọc**.
- Font tiếng Việt lấy từ Windows (`segoeuib.ttf`), không cần cài thêm.

## 5. Preset nhân vật động nhanh `ricks_dynamic`

Preset này ép mỗi scene dài tối đa 3 giây, gắn cảm xúc cho giọng đọc, driving video
cho nhân vật, B-roll/hiệu ứng, subtitle động, audio ducking và SFX chính xác theo frame.
Nó **không cho phép** tự thay nhân vật động bằng ảnh zoom giả lập.

```bash
python pipeline/ricks_dynamic_pipeline.py pipeline/samples/ricks_dynamic_sample.json ^
  --out pipeline/output/ricks_dynamic_compiled.json

# Kiểm tra cả model và asset thật trước khi render
python pipeline/ricks_dynamic_pipeline.py pipeline/samples/ricks_dynamic_sample.json ^
  --out pipeline/output/ricks_dynamic_compiled.json --preflight
```

Biến môi trường tùy chọn: `LIVEPORTRAIT_ROOT`, `SADTALKER_ROOT`.
SFX dùng cú pháp `f+12:whoosh.wav`, nghĩa là phát ở frame 12 tính từ đầu scene.

## 6. Render draft nhanh có cache

```bash
# Draft 540×960: render nhanh, cache toàn bộ visual frames
python pipeline/fast_video_draft.py --mode preview

# Đổi BGM/SFX không render lại hình
python pipeline/fast_video_draft.py --mode preview --no-bgm

# Chỉ dùng sau khi nội dung đã duyệt
python pipeline/fast_video_draft.py --mode final
```

Pipeline tách bốn công đoạn: `script/voice → visual frames → audio mix → encode`.
Visual frames được băm theo mã nguồn; thay âm thanh hoặc mức mix sẽ tái sử dụng frame cache.
