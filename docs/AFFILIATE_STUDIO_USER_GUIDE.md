# AI Affiliate Studio — User Guide (Draft, Phase 1)

> Ngôn ngữ giao diện: tiếng Việt. Ngôn ngữ lồng tiếng/phụ đề mặc
> định: tiếng Việt (vi-VN).

AI Affiliate Studio biến **video sản phẩm bạn sở hữu hoặc được phép
dùng cho mục đích thương mại** thành video affiliate tiếng Việt
9:16 cho TikTok / Facebook Reels.

> **Lưu ý bản quyền:** chỉ xử lý video bạn sở hữu hoặc được phép sử
> dụng lại cho mục đích thương mại. Mirror, dịch chữ và lồng tiếng
> không tự động biến video của người khác thành nội dung nguyên bản
> hoặc đảm bảo đủ điều kiện kiếm tiền.

## Luồng làm việc

1. **Tạo dự án + tải video lên.** Chọn file video (mp4/mov/mkv/webm).
   Nếu video đến từ một đường link, bạn có thể dán link vào ô "Link
   nguồn" — hệ thống chỉ **ghi lại** link, không tự tải video. Chọn
   đúng loại quyền sử dụng và tick xác nhận quyền thương mại. Nếu
   quyền là `UNKNOWN` hoặc chưa xác nhận, hệ thống sẽ **từ chối xuất
   bản** cho đến khi bạn xác nhận.
2. **Thông tin sản phẩm.** Điền tên, danh mục, link Shopee, link
   affiliate, giá, đặc điểm, lợi ích, đối tượng, lời kêu gọi, thương
   hiệu. Chỉ điền những gì bạn biết chắc: hệ thống **không bao giờ bịa**
   giá, giảm giá, chứng nhận hay lợi ích. Bỏ trống giá nếu không rõ —
   video sẽ dùng cách nói trung tính.
3. **Phân tích + nhận diện giọng nói.** Hệ thống chạy phân tích video
   và nhận diện giọng nói tiếng Trung (faster-whisper) ra bản ghi có
   mốc thời gian. Nếu video không có lời nói, bạn sẽ dùng kịch bản
   viết từ hình ảnh.
4. **Gán người nói (lồng tiếng theo nhân vật).** Nếu video có nhiều
   người nói, gán từng khoảng thời gian cho từng người nói (mỗi dòng:
   `bắt đầu-giây, kết thúc-giây, tên người nói`). Mỗi người nói sẽ có
   giọng đọc riêng, nhất quán suốt video. Hệ thống chưa có tự động
   tách người nói — bạn gán bằng tay, hệ thống không đoán.
5. **Dịch.** Chọn chế độ dịch (bản địa hóa tự nhiên / dịch trực tiếp
   / viết lại kiểu affiliate) và giọng văn. Giọng văn **"Hài hước,
   viral, kiểu review"** dịch bám sát nghĩa gốc nhưng diễn đạt vui
   nhộn như người review — sự thật, con số và giá không đổi. Bản gốc,
   bản dịch và bản viết lại được lưu riêng. Khi chưa có Gemini API
   key, bản dịch trực tiếp/bản địa hóa sẽ để trống và chờ bạn dịch
   hoặc chạy lại khi có key — hệ thống không tự bịa bản dịch.
6. **Kịch bản.** Viết kịch bản mới theo 3 phong cách, hoặc **tạo kịch
   bản lồng tiếng từ bản dịch** (từng câu dịch thành từng câu đọc,
   giữ nguyên người nói và mốc thời gian). Bạn sửa và **duyệt** kịch
   bản trước khi lồng tiếng; mọi chỉnh sửa đều xóa duyệt cũ.
7. **Biên tập.** Mirror mặc định TẮT. Bật mirror cần xem cảnh báo
   nhãn/logo và tick xác nhận. Chữ Trung trên màn hình được làm mờ
   rồi phủ phụ đề tiếng Việt lên trên (xem phần phụ đề).
8. **Lồng tiếng.** Chọn giọng đọc mặc định, nghe thử, rồi lồng tiếng
   toàn bộ. Giọng theo từng nhân vật điền dạng JSON, ví dụ:
   `{"NGUOI_1": "female_review", "NGUOI_2": "male_review"}`. Giọng
   đọc là giọng VieNeu thật trên máy của bạn; trên máy chủ dùng thử
   hiện tại là giọng của bộ công cụ TTS dùng chung. Tốc độ đọc giữ
   trong khoảng tự nhiên 90–110; hệ thống không bao giờ tăng tốc
   giọng để khớp hình.
9. **Phụ đề.** Phụ đề tiếng Việt, phông chữ rõ trên điện thoại, cỡ
   chữ mặc định 64px, tối đa 2 dòng, tôn trọng vùng an toàn của
   TikTok/Reels (vùng bấm, vùng mô tả). Có thể bật tô sáng từng từ.
   Xuất kèm cả file SRT.
10. **Âm thanh.** Trộn 4 luồng: giọng Việt, âm thanh gốc của sản
    phẩm, nhạc nền, hiệu ứng. Mặc định: nhạc nhỏ, tự hạ nhạc khi có
    giọng nói, mở/đóng mượt, hiệu ứng tiết chế. Chỉ dùng nhạc bạn có
    quyền dùng.
11. **QA + xuất bản.** QA kỹ thuật chạy trên file thật; QA sáng tạo
    luôn cần bạn xem và duyệt. Xuất bản bị từ chối nếu quyền chưa
    xác nhận, kịch bản chưa duyệt, hoặc có thao tác mirror/xóa chữ
    chưa được duyệt. Video xuất ra 1080x1920, xem trước rồi mới
    đăng — hệ thống **không tự đăng** lên TikTok/Facebook.

## Gói tiếp thị (marketing package)

Hệ thống tạo sẵn: caption TikTok, caption Reels, tiêu đề, hashtag,
mô tả, lời kêu gọi, câu công bố affiliate, gợi ý thumbnail. Link
affiliate chỉ lấy từ link **bạn đã nhập** — không có link thì để
trống, không bịa. Không có hứa hẹn doanh số/thu nhập.

## Câu hỏi thường gặp

**Video của tôi không có tiếng nói?** Dùng kịch bản viết từ những gì
video cho thấy + thông tin sản phẩm bạn điền. Hệ thống không bịa lời
thoại.

**Tôi chỉ có link video, chưa có file?** Dán link để ghi lại nguồn,
nhưng bạn vẫn cần tải file lên mới xử lý và xuất bản được. Hệ thống
không tự tải video từ link.

**Bản dịch để trống?** Chưa có Gemini API key trên máy chủ hiện tại.
Dịch sẽ chạy thật khi key được cấu hình; cho đến lúc đó, bản dịch
trực tiếp/bản địa hóa cần bạn nhập tay hoặc chờ chạy lại.

**Giọng đọc nghe không đúng người?** Kiểm tra phần gán người nói
(bước 4) và bảng giọng theo nhân vật (bước 8): mỗi tên người nói
phải khớp đúng giữa hai chỗ.

**Xuất bản báo 403?** Quyền sử dụng chưa xác nhận, kịch bản chưa
duyệt, hoặc còn thao tác chưa duyệt. Xem danh sách lý do trong thông
báo và sửa từng mục.

## Giới hạn hiện tại (Phase 1)

- Chưa có render/xuất file thật trên máy chủ dùng thử — phần render
  đang được hoàn thiện và sẽ nối vào sau.
- Chưa có tự động tách người nói (cần cài thêm pyannote.audio).
- Chưa có nhận diện chữ trong video (OCR) trên máy chủ dùng thử.
- Gói tiếp thị chỉ là dữ liệu để bạn copy — không tự đăng.
