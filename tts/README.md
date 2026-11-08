# Voice / TTS — Giọng đọc tiếng Việt + Voice Cloning

Module **giọng đọc** cho Local Workspace — bước "giọng đọc" còn thiếu trong
quy trình làm content (chủ đề → kịch bản → **giọng đọc** → hình ảnh → edit).

Tích hợp 3 engine, mặc định dùng **edge-tts** (giọng neural tiếng Việt tốt
nhất, miễn phí, không cần GPU/model).

## Vì sao chọn engine này

| Engine | Chất lượng tiếng Việt | Cài đặt | Cần mạng | GPU | Dùng cho |
|---|---|---|---|---|---|
| **edge-tts** (mặc định) | ⭐⭐⭐⭐⭐ (neural Azure) | `pip install edge-tts` | ✅ khi chạy | ❌ | Tất cả content, bulk, nhanh |
| **MeloTTS** | ⭐⭐⭐⭐ | nặng (torch) | ❌ offline | ❌ (CPU nhanh) | Chạy offline hoàn toàn |
| **XTTS v2** | ⭐⭐⭐⭐ (clone) | nặng (torch) | ❌ (sau tải model) | nên có | Voice cloning giọng cụ thể |

→ **Khuyến nghị**: dùng **edge-tts** làm chính (giọng `vi-VN-HoaiMyNeural` nữ,
`vi-VN-NamMinhNeural` nam — chuẩn và mượt nhất hiện nay). Chỉ cài **XTTS v2**
khi cần *nhân bản* một giọng cụ thể (clone giọng người thật/người nổi tiếng).

## Cài đặt

```bash
# Engine mặc định (đủ dùng 99% trường hợp)
pip install edge-tts

# Voice cloning (tùy chọn, nặng ~ vài GB)
pip install coqui-tts

# Offline (tùy chọn)
pip install git+https://github.com/myshell-ai/MeloTTS.git
```

## Cách dùng

```bash
# 1. Đọc 1 câu (giọng nữ mặc định)
python tts.py "Xin chào, đây là video hôm nay" -o output/hello.mp3

# 2. Giọng nam, đọc chậm/nhanh
python tts.py "Báo cáo ngày hôm nay..." --voice namminh --rate -5% -o report.mp3

# 3. Đọc cả kịch bản (mỗi dòng = 1 đoạn)
python tts.py --file kichban.txt --voice hoaimy -o output/giongdoc.mp3

# 4. Liệt kê giọng tiếng Việt có sẵn
python tts.py --list-voices

# 5. Voice cloning (nhân bản giọng từ file mẫu ~3s)
python tts.py "Nội dung cần đọc" --clone giọng_mẫu.wav -o output/clone.mp3
```

## Giọng tiếng Việt có sẵn

| Preset | Voice id | Giới tính | Phù hợp |
|---|---|---|---|
| `hoaimy` (mặc định) | `vi-VN-HoaiMyNeural` | Nữ | kể chuyện, tin tức, shorts |
| `namminh` | `vi-VN-NamMinhNeural` | Nam | báo cáo, documentary, daily |

Alias: `nu`/`female` → `hoaimy`, `nam`/`male` → `namminh`.
Có thể truyền trực tiếp voice id (`vi-VN-HoaiMyNeural`).

## Tích hợp vào pipeline

Kết quả là file `.mp3`, truyền thẳng vào `charmotion`:

```bash
python tts.py "Nội dung video" -o voice.mp3
python ../charmotion/charmotion.py --script kichban.json --audio voice.mp3 -o output/video.mp4
```

## Lưu ý

- **edge-tts** cần internet lúc chạy (gọi server Microsoft, miễn phí, không API key).
- **XTTS v2** tải model lần đầu (~1.5 GB); chạy nhanh hơn nhiều nếu có GPU.
- Tiếng Việt có dấu được hỗ trợ đầy đủ trên cả 3 engine.
