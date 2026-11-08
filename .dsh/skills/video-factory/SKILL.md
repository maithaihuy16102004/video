---
name: video-factory
description: Phân xưởng sản xuất video tự động đa draft (2-5 video draft hoàn chỉnh). Nhận nhiệm vụ hoặc chủ đề content từ người dùng (@video-factory), tự động phân nhánh kịch bản theo nhiều phong cách/góc nhìn (storytelling, thực chiến how-to, chuyên gia mổ xẻ, sai lầm contrarian, tóm tắt recap), sinh giọng đọc tiếng Việt đa dạng (namminh, hoaimy), tạo phụ đề SRT, vẽ storyboard & thumbnail, rồi render đồng loạt từ 2 đến 5 video draft MP4 hoàn chỉnh. Toàn bộ chạy local 100%, không phụ thuộc Claude Code.
---

# Video Factory — Phân Xưởng Sản Xuất Đa Video Draft (2-5 Bản Hoàn Chỉnh)

Kỹ năng (Skill) biến Agent thành một **Phân xưởng sản xuất video tự động hoá khép kín**:
- **Đầu vào**: Chủ đề, link bài viết/video tham khảo, hoặc nhiệm vụ ngắn gọn từ bạn (VD: `@video-factory làm video về mẹo tài chính cá nhân`, `@video-factory hãy tạo 3 video draft về AI marketing`).
- **Đầu ra bắt buộc**: Tối thiểu **2 video draft** và tối đa **5 video draft** hoàn chỉnh (gồm đầy đủ kịch bản, lời thoại, file âm thanh giọng đọc tiếng Việt, phụ đề SRT, ảnh thumbnail và file video `.mp4`).

---

## ⚡ NGUYÊN TẮC HOẠT ĐỘNG
1. **Thuần hóa 100% Local**: Sử dụng trực tiếp hệ thống engine nội bộ tại `D:\Agent` (`pipeline/`, `charmotion/`, `tts/`, `ai-video-editor/`) với Python, FFmpeg, Edge-TTS và Whisper. **Không phụ thuộc vào Claude Code** hay API trung gian của bên thứ ba.
2. **Đa dạng hóa góc nhìn (Multi-angle Drafts)**: Mỗi draft video sinh ra mang một trường phái kịch bản, tiết tấu và visual hoàn toàn khác nhau để bạn lựa chọn:
   - **Draft 1**: *Storytelling & Bối cảnh kịch tính* (Voice trầm ấm Nam Minh, phong cách Gold)
   - **Draft 2**: *Thực chiến Actionable / How-to từng bước* (Voice năng động Hoài My, phong cách Neon)
   - **Draft 3**: *Chuyên gia phân tích số liệu & Bản chất sâu* (Voice sắc sảo Nam Minh, phong cách Dark)
   - **Draft 4**: *Vạch trần sai lầm / Contrarian phản biện* (Voice gay cấn Hoài My, phong cách Emerald)
   - **Draft 5**: *Siêu tốc 60s / Quick Recap tinh gọn* (Voice tốc độ cao Nam Minh, phong cách Ocean)
3. **Quy tắc số lượng**: Luôn đảm bảo số lượng kết quả xuất ra nằm trong khoảng: **2 ≤ Số lượng Draft ≤ 5** (mặc định 3 draft nếu người dùng không chỉ định con số cụ thể).

---

## 🛠️ CÁCH SỬ DỤNG TRONG PHIÊN LÀM VIỆC

Khi bạn gọi `@video-factory` kèm nhiệm vụ:
Ví dụ:
> `@video-factory Làm cho tôi 3 video draft phân tích tâm lý người mua hàng trên TikTok Shop`
> `@video-factory Tạo kịch bản và dựng 4 bản draft về tư duy đầu tư cho người mới`

Agent sẽ thực hiện ngay lệnh sau:
```bash
python D:\Agent\pipeline\video_factory.py "<CHỦ_ĐỀ_HOẶC_NHIỆM_VỤ>" --drafts <SỐ_LƯỢNG_2_ĐẾN_5>
```

---

## 📦 KẾT QUẢ ĐẦU RA CHO MỖI DRAFT
Mỗi draft được đóng gói riêng biệt tại thư mục `D:\Agent\drafts_factory\<ten_chu_de>\draft_0X\`:
1. `script.json`: Kịch bản phân cảnh chi tiết (Hook, Bối cảnh, Luận điểm, Call-to-action).
2. `spoken_text.txt`: Bản văn bản lời đọc chính thức.
3. `voice.mp3`: Giọng đọc lồng tiếng chuẩn AI neural tiếng Việt.
4. `subtitles.srt`: File phụ đề canh chuẩn timeline từng câu.
5. `thumbnail.jpg`: Ảnh bìa tỷ lệ 9:16 thiết kế chuẩn nhận diện thị giác.
6. `draft_video.mp4`: Video hoàn chỉnh render bằng FFmpeg + Motion Graphic.
7. `factory_manifest.json`: Bảng tổng kết so sánh giữa các bản draft để bạn duyệt chọn bản ưng ý nhất.
