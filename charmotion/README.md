# charmotion — Character + Motion Graphics Studio

Công cụ tạo video **nhân vật hoạt hình + motion graphics** để đăng **TikTok/Shorts (dọc)** và **YouTube (ngang)**, phỏng theo phong cách các TikToker dev/tech Việt Nam (như @h2_dev, @mindang.com).

Không cần phần mềm dựng video, không cần API trả phí. Chạy hoàn toàn trên máy bằng **Python (Pillow + numpy) + FFmpeg**.

## Video demo đã render sẵn

- `output/demo_ai.mp4` — video dọc 1080×1920, chủ đề AI (6 cảnh, 21.5s)
- `output/demo_horizontal.mp4` — video ngang 1920×1080 (YouTube)

## Yêu cầu

- **Python 3.10+** + Pillow + numpy
- **FFmpeg** trong PATH (kiểm tra `ffmpeg -version`)

```bash
pip install pillow numpy
```

## Cách dùng nhanh

### Cách 1: Dùng template có sẵn (nhanh nhất)

```bash
python charmotion.py --template tech \
  --title "Cách dùng Claude Code" \
  --points "Tạo dự án|Viết code|Debug" \
  --hook "Lập trình viên phải biết!" \
  --size vertical \
  -o output/video.mp4
```

Các template:
| `--template` | Chủ đề | Phong cách |
|---|---|---|
| `tech` | Công nghệ / lập trình | Nền tech grid + nhân vật giải thích |
| `motivation` | Động lực / truyền cảm hứng | Nền ấm + nhân vật phấn khích |
| `education` | Giáo dục / mẹo hay | Nền xanh + nhân vật chỉ dẫn |

### Cách 2: Kịch bản JSON tự do (toàn quyền kiểm soát)

```bash
python charmotion.py --script scripts/demo_ai.json -o output/video.mp4 --audio nhac.mp3
```

### Các tham số chính

| Tham số | Ý nghĩa |
|---|---|
| `--template` | tech / motivation / education |
| `--title` | Tiêu đề video |
| `--points` | Các ý chính, phân cách bằng `\|` |
| `--hook` | Câu mở đầu gây chú ý (tùy chọn) |
| `--script` | File kịch bản JSON (thay template) |
| `--audio` | Nhạc/giọng nói nền (mp3/wav) |
| `--size` | `vertical` (TikTok) / `square` / `horizontal` (YouTube) |
| `-o` | Đường dẫn xuất |

## Cấu trúc kịch bản JSON

```json
{
  "width": 1080, "height": 1920, "fps": 30,
  "scenes": [
    {
      "duration": 4.0,
      "background": {"type": "tech", "top": [20,25,45], "bottom": [5,10,25]},
      "character": {"pose": "talk", "expression": "happy",
                    "x": 0.5, "y": 0.72, "scale": 120, "talking": true},
      "texts": [
        {"text": "Chào mừng!", "x": 0.5, "y": 0.3, "size": 90,
         "effect": "pop", "delay": 0.2, "duration": 1.5, "max_width": 950}
      ],
      "shapes": [
        {"type": "progress", "x": 0.5, "y": 0.88, "width": 700,
         "height": 26, "color": [255,200,60], "delay": 0.6, "duration": 2.0}
      ]
    }
  ]
}
```

## Các thành phần (building blocks)

### Nhân vật (`character`)
- **Pose**: `idle`, `wave`, `point`, `talk`, `excited`, `thumbs_up`, `thinking`, `surprised`
- **Expression**: `neutral`, `happy`, `excited`, `surprised`, `thinking`
- **`talking: true`** → miệng tự động mở/đóng như đang nói
- `x`, `y` (0..1), `scale` (px), `colors` (tùy chỉnh màu da/tóc/áo)

### Hiệu ứng text (`effect`)
`pop`, `slide_left`, `slide_right`, `slide_up`, `scale`, `fade`, `bounce`, `typewriter`

### Hình khối (`shapes`)
`progress` (thanh tiến trình), `ring` (vòng tròn), `arrow`, `star`, `heart`, `lightbulb`

### Nền (`background`)
`gradient`, `solid`, `tech` (lưới tech + chấm)

## Tùy chỉnh màu nhân vật

Trong scene JSON:
```json
"character": {
  "pose": "talk", "expression": "happy",
  "x": 0.5, "y": 0.72, "scale": 120, "talking": true,
  "colors": {
    "skin": [255, 213, 170], "hair": [60, 45, 35],
    "shirt": [66, 133, 244], "pants": [50, 50, 60]
  }
}
```

## Quy trình làm video (gợi ý)

1. Chọn template phù hợp chủ đề.
2. Viết `--title` + `--points` (mỗi ý = 1 cảnh ~4s).
3. Render ra video, xem thử.
4. Thêm `--audio` (nhạc nền hoặc file lồng giọng đọc) nếu muốn.
5. Chỉnh kịch bản JSON nếu muốn tinh chỉnh từng cảnh.

## Lưu ý

- Chữ tiếng Việt có dấu được hỗ trợ đầy đủ (dùng font Segoe UI/Arial).
- Để có giọng đọc, dùng TTS (Google/Bark/edge-tts) tạo file mp3 rồi truyền `--audio`.
- Muốn video mượt hơn, tăng `fps` trong script (mặc định 30).
