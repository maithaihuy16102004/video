---
name: ai-video-editor
description: Tự động edit video TikTok — cắt khoảng lặng, thêm phụ đề (Whisper), trộn nhạc, motion graphic, tạo storyboard để duyệt rồi xuất. Dùng khi người dùng muốn làm AI video editor hoặc edit video theo phong cách tham khảo.
---

# AI Video Editor Skill

Skill điều khiển bộ công cụ `avi_editor.py` (FFmpeg + Whisper + Pillow) để edit video tự động theo 4 bước, tái tạo quy trình trong video của @mindang.com.

## Khi nào dùng

- Người dùng yêu cầu "edit video", "cắt khoảng lặng", "thêm phụ đề tự động", "làm video TikTok", "học phong cách creator X".
- Người dùng muốn chạy pipeline để xuất video thành phẩm.

## Quy trình 4 bước

1. **Chuẩn bị thư mục**: đảm bảo `video/`, `reference/`, `output/` tồn tại (xem README).
2. **Cài công cụ**: kiểm tra `ffmpeg -version`, `python -c "import PIL"`. Nếu thiếu Whisper, yêu cầu người dùng cung cấp `--srt` hoặc cài `openai-whisper`.
3. **Học phong cách**: bỏ 3–5 video tham khảo vào `reference/` (hoặc video của chính người dùng để giữ phong cách). Chạy sẽ sinh `style_profile.json`.
4. **Chạy pipeline**: gọi lệnh dưới đây, sau đó trình storyboard cho người dùng duyệt; chỗ nào chưa ưng thì chỉnh lại tham số (ngưỡng lặng, fontsize...) và chạy lại.

## Lệnh

```bash
python avi_editor.py <video_goc.mp4> \
  [--srt phude.srt] \
  [--ref-dir reference] \
  [--music nhac.mp3] \
  [--motion] \
  [--silence-thresh -40] \
  [--silence-dur 0.6] \
  [--out-dir output]
```

## Nguyên tắc

- Luôn chạy `python avi_editor.py --help` nếu không chắc tham số.
- Trước khi xuất, luôn tạo storyboard (`storyboard.jpg`) và hỏi người dùng duyệt.
- Không ghi đè video gốc; kết quả luôn nằm trong `output/`.
