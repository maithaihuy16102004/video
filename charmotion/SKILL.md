---
name: charmotion
description: Tạo video nhân vật hoạt hình + motion graphics cho TikTok/Shorts (dọc) và YouTube (ngang) từ kịch bản JSON hoặc template. Dùng khi người dùng muốn làm video có character hoạt hình, kinetic typography, motion graphics để đăng mạng xã hội.
---

# charmotion Skill

Skill điều khiển bộ công cụ `charmotion.py` (Pillow + numpy + FFmpeg) để tạo video nhân vật hoạt hình + motion graphics, phỏng phong cách TikToker dev/tech Việt Nam.

## Khi nào dùng

- Người dùng muốn "làm video TikTok/YouTube có nhân vật hoạt hình", "motion graphics", "kinetic typography".
- Người dùng muốn tạo nội dung giải thích (tech, giáo dục, động lực) dạng character + text chạy chữ.

## Quy trình

1. **Chọn template** phù hợp: `tech` / `motivation` / `education`.
2. **Viết nội dung**: `--title` + `--points` (phân cách `|`) + `--hook` (tùy chọn).
3. **Chọn khổ**: `--size vertical` (TikTok) hoặc `horizontal` (YouTube).
4. **Render**: chạy lệnh, kiểm tra video ra.
5. **Tùy chỉnh**: nếu cần tinh chỉnh từng cảnh, viết kịch bản JSON rồi `--script`.

## Lệnh

```bash
python charmotion.py --template tech \
  --title "Tiêu đề" \
  --points "Ý 1|Ý 2|Ý 3" \
  --hook "Câu hook" \
  --size vertical \
  -o output/video.mp4

# hoặc dùng kịch bản JSON
python charmotion.py --script scripts/kichban.json -o output/video.mp4 --audio nhac.mp3
```

## Cấu trúc kịch bản JSON (tối thiểu)

```json
{
  "width": 1080, "height": 1920, "fps": 30,
  "scenes": [
    {
      "duration": 4.0,
      "background": {"type": "tech"},
      "character": {"pose": "talk", "expression": "happy", "talking": true},
      "texts": [{"text": "Nội dung", "x": 0.5, "y": 0.4, "size": 70, "effect": "pop"}]
    }
  ]
}
```

## Nguyên tắc

- Luôn render ra file `.mp4` trong `output/` rồi trình cho người dùng kiểm tra.
- Tôn trọng khổ video người dùng yêu cầu (vertical = TikTok, horizontal = YouTube).
- Chữ tiếng Việt có dấu được hỗ trợ; nếu cần giọng đọc, tạo file mp3 TTS rồi truyền `--audio`.
