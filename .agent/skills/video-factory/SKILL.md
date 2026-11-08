---
name: video-factory
description: Phân xưởng sản xuất video tự động đa draft (2-5 video draft hoàn chỉnh). Nhận nhiệm vụ hoặc chủ đề content từ người dùng (@video-factory), tự động phân nhánh kịch bản theo nhiều phong cách/góc nhìn (storytelling, thực chiến how-to, chuyên gia mổ xẻ, sai lầm contrarian, tóm tắt recap), sinh giọng đọc tiếng Việt đa dạng (namminh, hoaimy), tạo phụ đề SRT, vẽ storyboard & thumbnail, rồi render đồng loạt từ 2 đến 5 video draft MP4 hoàn chỉnh. Toàn bộ chạy local 100%, tích hợp Remotion, Manim VFX, AudioCraft SFX, LivePortrait/Ken Burns và MoviePy Compositing.
---

# Video Factory 4.0 — Phân Xưởng Sản Xuất Đa Video Draft (2-5 Bản Hoàn Chỉnh)

Kỹ năng (Skill) biến Agent thành một **Phân xưởng sản xuất video tự động hoá khép kín**:
- **Đầu vào**: Chủ đề, link bài viết/video tham khảo, hoặc nhiệm vụ ngắn gọn từ bạn (VD: `@video-factory làm video về lịch sử loài người`, `@video-factory hãy tạo 3 video draft về AI marketing`).
- **Đầu ra bắt buộc**: Tối thiểu **2 video draft** và tối đa **5 video draft** hoàn chỉnh (gồm đầy đủ kịch bản, lời thoại, file âm thanh giọng đọc tiếng Việt, phụ đề SRT, ảnh thumbnail, hiệu ứng Manim VFX, hiệu ứng SFX và file video `.mp4` 1080x1920 ghép bằng MoviePy).

---

## ⚡ KIẾN TRÚC 4 TẦNG NỘI BỘ (100% LOCAL)

1. **Tầng 1 - Hoạt hoá nhân vật (Character Animation Layer)**:
   - `ai-engine/character/liveportrait_bridge.py`: Tích hợp LivePortrait (ép biểu cảm, cử động mặt theo driving video) cùng chế độ Ken Burns procedural mượt mà khi chạy ảnh tĩnh.
2. **Tầng 2 - Đồ họa chuyển động & VFX (VFX & Motion Graphics Layer)**:
   - `remotion-engine`: Render Typography động chuẩn vertical 9:16, glassmorphism card, hashtag badge, progress bar.
   - `ai-engine/vfx/manim_vfx.py`: Render visual effect phát sáng toán học, kinetic titles, timeline bar, data reveal và particle rise.
3. **Tầng 3 - Âm thanh & SFX (Sound Design & Audio Layer)**:
   - Giọng đọc AI Tiếng Việt (Nam Minh trầm ấm / Hoài My năng động) với hệ thống tự động fallback.
   - `ai-engine/sfx/audiocraft_bridge.py`: Sinh SFX thông minh từ văn bản phân cảnh (tiếng nổ, sóng biển, gió, tiếng reo hò, tiếng chuyển cảnh cinematic).
   - Nhạc nền (BGM) đa phong cách tự động ducking theo giọng nói.
4. **Tầng 4 - Ghép Master (MoviePy Compositing Layer)**:
   - `pipeline/composer.py`: MoviePy 2.x kết hợp đa tầng Video + VFX overlay + SFX + BGM ducking + Voice track thành sản phẩm hoàn thiện.

---

## 🛠️ CÁCH SỬ DỤNG TRONG PHIÊN LÀM VIỆC

Khi bạn gọi `@video-factory` kèm nhiệm vụ:
Ví dụ:
> `@video-factory Làm cho tôi 3 video draft phân tích tâm lý người mua hàng trên TikTok Shop`
> `@video-factory Tạo kịch bản và dựng 4 bản draft về lịch sử loài người`

Agent sẽ thực hiện ngay lệnh sau:
```bash
python D:\Agent\pipeline\video_factory_v4.py --topic <CHỦ_ĐỀ> --drafts <SỐ_LƯỢNG_2_ĐẾN_5>
```

---

## 📦 KẾT QUẢ ĐẦU RA CHO MỖI DRAFT
Mỗi draft được đóng gói riêng biệt tại thư mục `D:\Agent\drafts_factory\<ten_chu_de>\draft_0X\`:
1. `script.json`: Kịch bản phân cảnh chi tiết (Hook, Bối cảnh, Luận điểm, Call-to-action).
2. `spoken_text.txt`: Bản văn bản lời đọc chính thức.
3. `voice.mp3`: Giọng đọc lồng tiếng chuẩn AI neural tiếng Việt.
4. `subtitles.srt`: File phụ đề canh chuẩn timeline từng câu.
5. `thumbnail.jpg`: Ảnh bìa tỷ lệ 9:16 thiết kế chuẩn nhận diện thị giác.
6. `vfx/`: Thư mục các clip VFX đồ họa chuyển động Manim.
7. `sfx/`: Thư mục các hiệu ứng âm thanh Sound Effects theo cảnh.
8. `draft_video.mp4`: Video hoàn chỉnh render bằng MoviePy Master Compositing.
9. `factory_manifest.json`: Bảng tổng kết so sánh giữa các bản draft để bạn duyệt chọn bản ưng ý nhất.
