---
name: context-optimizer
description: Tối ưu token & context khi đưa log video pipeline (FFmpeg/Whisper/render) vào LLM — lọc log rác (regex), chia chunk map-reduce, tận dụng Context Caching, trích metadata ffprobe. Dùng khi người dùng muốn giảm chi phí token hoặc sinh báo cáo daily từ log.
---

# context-optimizer Skill

Skill điều khiển bộ công cụ `optimize.py` để thực thi chiến lược 4 lớp tối ưu token.

## Khi nào dùng

- Người dùng muốn "giảm token", "tiết kiệm chi phí API", "tối ưu context".
- Người dùng có file log lớn (render video, ffmpeg, whisper) cần tóm tắt thành báo cáo.
- Người dùng muốn trích metadata video để đưa vào prompt mà không gửi dữ liệu nhị phân.

## Quy trình 4 lớp

1. **Lọc** (`filter`): xóa dòng tiến trình rác, giữ lỗi/sự kiện/file.
2. **Chia chunk** (`--chunk`): by_time / by_process / by_lines / auto.
3. **Map-Reduce** (`report`): tóm tắt từng chunk rồi gom thành báo cáo Markdown.
4. **Context caching**: giữ system prompt + template tĩnh ở đầu để cache hit (~1/10 giá input).
5. **Metadata** (`metadata`): ffprobe → JSON nhẹ thay vì dữ liệu video thô.

## Lệnh

```bash
# lọc log
python optimize.py filter logs/render.log -o logs/render.clean.log

# metadata video
python optimize.py metadata video.mp4 -o meta.json

# thống kê token rác (offline, không cần key)
python optimize.py stats logs/render.log

# sinh báo cáo daily (cần DEEPSEEK_API_KEY)
python optimize.py report logs/render.log -o report.md --chunk by_time
```

## Nguyên tắc

- Luôn lọc (Layer 2) trước khi gọi LLM — đây là bước giảm token lớn nhất.
- Đặt dữ liệu TĨNH trước, ĐỘNG sau (Layer 3) để cache hit.
- Không gửi dữ liệu nhị phân video vào context — chỉ gửi metadata JSON.
- Model mặc định là `deepseek-chat` (không phải "deepseek-flash" — tên đó không tồn tại).
