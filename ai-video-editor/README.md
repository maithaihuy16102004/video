# AI Video Editor

Công cụ **tự động edit video** dựa trên quy trình 4 bước trong video của [@mindang.com](https://www.tiktok.com/@mindang.com).

Tự động: **cắt khoảng lặng → thêm phụ đề → trộn nhạc → motion graphic → storyboard để duyệt → xuất video**. Chạy hoàn toàn trên máy bạn (FFmpeg + Whisper + Pillow), không cần Claude Code hay API.

## Yêu cầu

- **Python 3.10+**
- **FFmpeg** (trong PATH): kiểm tra `ffmpeg -version`
- **Pillow**: `pip install pillow`
- **Whisper** (tùy chọn, để tự tạo phụ đề): `pip install openai-whisper`

## Cấu trúc thư mục (bước 1)

```
ai-video-editor/
├── avi_editor.py        # main CLI
├── config/default.json  # cấu hình phong cách
├── src/                 # các module
├── video/               # ← bỏ video GỐC vào đây
├── reference/           # ← bỏ video THAM KHẢO (học phong cách)
└── output/              # ← video đã edit xuất ra đây
```

## Cách dùng

### Nhanh nhất
```bash
# bỏ video gốc vào thư mục video/, rồi chạy:
python avi_editor.py video/bai_cua_ban.mp4
```

### Đầy đủ
```bash
python avi_editor.py video/bai.mp4 \
  --srt phude.srt \              # phụ đề có sẵn (nếu không có Whisper)
  --ref-dir reference \          # học phong cách từ video tham khảo
  --music nhac.mp3 \             # nhạc nền
  --motion \                     # thêm intro motion graphic
  --silence-thresh -40 \         # ngưỡng lặng (dB)
  --silence-dur 0.6 \            # độ dài lặng tối thiểu (giây)
  --out-dir output
```

> **Mẹo**: nếu chưa cài Whisper, dùng `--srt` trỏ tới file `.srt`/`.vtt`. Với video TikTok, bạn có thể lấy phụ đề `.vtt` từ URL của link người dùng chia sẻ.

### Tham số CLI

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `input` | — | đường dẫn video gốc |
| `--config` | `config/default.json` | JSON cấu hình |
| `--srt` | — | file phụ đề có sẵn (bỏ qua Whisper) |
| `--ref-dir` | `reference/` | thư mục video tham khảo phong cách |
| `--music` | — | file nhạc nền mp3/wav |
| `--motion` | off | bật intro motion graphic |
| `--vertical` | on | video dọc (TikTok) |
| `--silence-thresh` | `-40` | ngưỡng lặng (dB) |
| `--silence-dur` | `0.6` | độ dài lặng tối thiểu (giây) |
| `--storyboard-cols` | `4` | số cột storyboard |
| `--out-dir` | `output/` | thư mục xuất |

## Học phong cách (bước 3)

Bỏ 3–5 video của creator bạn muốn học vào thư mục `reference/`. Công cụ sẽ:
1. Phân tích độ dài trung bình, tỉ lệ khung hình (dọc/ngang), tốc độ cắt.
2. Sinh file `style_profile.json` (đây chính là "skill" có thể tái dùng mỗi lần edit).

Muốn giữ phong cách *của bạn*, bỏ video của chính bạn vào `reference/`.

## Kết quả

Sau khi chạy, trong `output/` có:
- `tên_gốc_edited.mp4` — video đã edit
- `tên_gốc_storyboard.jpg` — lưới frame để bạn duyệt trước
- `tên_gốc_report.json` — báo cáo chi tiết các bước

## Lưu ý

- Việc cắt khoảng lặng tái mã hóa video (dùng `libx264`), chọn `--silence-dur` lớn để cắt ít hơn nếu không muốn mất nhịp.
- Burn phụ đề dùng filter `subtitles` của FFmpeg; trên Windows cần `libass` (đã có sẵn trong bản build gyan.dev).
