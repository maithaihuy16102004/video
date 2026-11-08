---
name: tts
description: Tạo giọng đọc tiếng Việt (TTS) hoặc nhân bản giọng nói (voice cloning) cho video/content. Dùng khi người dùng cần "giọng đọc", "text to speech", "đọc kịch bản", "clone giọng", "voiceover" cho video TikTok/YouTube.
---

# TTS / Voice Skill

Skill điều khiển bộ công cụ `tts.py` để tạo giọng đọc tiếng Việt (edge-tts,
mặc định) hoặc nhân bản giọng nói (XTTS v2). Đây là bước "giọng đọc" trong
quy trình làm content.

## Khi nào dùng

- Người dùng cần "giọng đọc", "đọc văn bản thành giọng nói", "TTS", "voiceover".
- Người dùng muốn "clone giọng", "nhân bản giọng nói" từ 1 file mẫu.
- Người dùng có kịch bản (.txt) muốn chuyển thành file audio để ghép vào video.

## Quy trình

1. **Xác định nhu cầu**: giọng nữ hay nam (`hoaimy` / `namminh`), chỉ đọc text
   hay cần clone giọng.
2. **Kiểm tra engine**: mặc định `edge-tts` (`pip install edge-tts`). Nếu clone,
   cài `pip install coqui-tts`.
3. **Chạy TTS**: gọi lệnh dưới đây, xuất file `.mp3`.
4. **Ghép vào video**: truyền file `.mp3` vào `charmotion --audio` hoặc
   `avi-editor --music`.

## Lệnh

```bash
python tts.py "<văn bản>" --voice hoaimy -o output/voice.mp3
python tts.py --file kichban.txt --voice namminh --rate +10% -o output/voice.mp3
python tts.py --list-voices
python tts.py "<văn bản>" --clone giong_mau.wav -o output/clone.mp3
```

## Nguyên tắc

- Mặc định dùng `edge-tts` (giọng neural tiếng Việt tốt nhất, miễn phí, nhanh).
- Chỉ chuyển sang `xtts` khi người dùng yêu cầu **clone** giọng cụ thể.
- Luôn xuất ra `output/` và báo đường dẫn file cho người dùng.
- Tiếng Việt có dấu: viết bình thường, không cần xử lý gì thêm.
