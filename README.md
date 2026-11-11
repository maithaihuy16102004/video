# Local Workspace — Hệ thống làm content YouTube/TikTok tự động

Bộ công cụ chạy hoàn toàn trên máy để tự động hoá quy trình làm content
"bán content view ngoại" (tham khảo quy trình h2dev.vn): **chủ đề → kịch bản
→ giọng đọc → hình ảnh → edit → đăng**.

## 🔌 Đóng gói thành plugin DSH

Toàn bộ workspace đã được đóng gói thành plugin **Content Studio** tại
[`plugin/content-studio/`](plugin/content-studio/README.md):

```powershell
powershell -ExecutionPolicy Bypass -File plugin\content-studio\install.ps1
```

Sau đó trong phiên DSH mới chỉ cần nói:
> "Dùng content-studio làm video về ..."

Plugin tự đóng gói 5 module + motion graphic + draft mẫu, kèm skill định nghĩa
quy trình 10 bước cho agent.

## Các module

| Module | Chức năng | Bước trong quy trình |
|---|---|---|
| [`pipeline/`](pipeline/README.md) | **Pipeline A-Z**: chủ đề → kịch bản → giọng đọc → video → thumbnail | tất cả |
| [`tts/`](tts/README.md) | Giọng đọc tiếng Việt + voice cloning (edge-tts / MeloTTS / XTTS v2) | **giọng đọc** |
| [`charmotion/`](charmotion/README.md) | Video nhân vật hoạt hình + motion graphics từ kịch bản | hình ảnh + edit |
| [`ai-video-editor/`](ai-video-editor/README.md) | Edit video có sẵn: cắt lặng, phụ đề (Whisper), nhạc, storyboard | edit |
| [`context-optimizer/`](context-optimizer/README.md) | Dọn/tối ưu log, context cho AI | phụ trợ |
| [`drafts/`](drafts/kinh_te_thi_truong/README.md) | Draft mẫu "Kinh tế thị trường" + 17 hiệu ứng motion graphic | mẫu |

## Quy trình làm 1 video hoàn chỉnh

### Cách nhanh nhất — 1 lệnh

```bash
python pipeline/pipeline.py "kinh tế thị trường" --voice hoaimy --theme gold
```

Tự làm hết: kịch bản (LLM hoặc template) → giọng đọc tiếng Việt → video
1080×1920 → thumbnail → báo cáo JSON.

### Cách thủ công từng bước

```bash
# 1. Viết kịch bản (title + hook + points)
# 2. Tạo video + tự sinh giọng đọc (mới tích hợp --voice)
python charmotion/charmotion.py --template tech \
  --title "Cách dùng DeepSeek" \
  --points "Tạo tài khoản|Viết prompt|Tự động hoá" \
  --hook "Lập trình viên phải biết!" \
  --voice hoaimy \
  -o output/video.mp4

# 3. Hoặc sinh giọng đọc riêng rồi ghép
python tts/tts.py --file kichban.txt --voice namminh -o output/voice.mp3
python charmotion/charmotion.py --script kichban.json --audio output/voice.mp3

# 4. Voice cloning (nhân bản giọng từ file mẫu)
python tts/tts.py "Nội dung" --clone giong_mau.wav -o output/clone.mp3

# 5. Dịch phụ đề + thumbnail
python pipeline/srt.py video.srt --src en --dst vi -o output/video_vi.srt
python pipeline/thumbnail.py --title "Tiêu đề" --theme gold -o output/thumb.jpg
```

## Cài đặt chung

```bash
pip install pillow numpy          # charmotion
pip install edge-tts              # giọng đọc tiếng Việt (mặc định)
# FFmpeg trong PATH (cắt video, trộn audio)
```

## Lưu ý

- Tất cả đều chạy local, không cần API trả phí.
- `edge-tts` cần mạng lúc chạy (giọng neural Microsoft, miễn phí).
- Muốn clone giọng cụ thể: `pip install coqui-tts` (cần GPU thì mượt hơn).
- Sinh kịch bản bằng LLM là **tùy chọn**: đặt `DEEPSEEK_API_KEY` /
  `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`; không có key vẫn chạy bằng template.
# video
