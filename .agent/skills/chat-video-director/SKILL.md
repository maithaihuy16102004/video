---
name: chat-video-director
description: Đạo diễn video tự động qua đoạn chat AI (không cần API key). AI chat đóng vai trò LLM Director phân rã kịch bản thành JSON chuẩn, điều phối climax_score, giọng đọc tiếng Việt, B-roll 30/70, camera effects và audio ducking.
---

# Chat Video Director Skill

Kỹ năng biến Antigravity thành **Đạo diễn AI (AI Director)** ngay trong đoạn chat:
- Không cần cấu hình bất kỳ API Key nào (OpenAI/DeepSeek/Anthropic API).
- AI trực tiếp phân tích kịch bản của người dùng, phân cảnh, chấm điểm cao trào (`climax_score` 1-10), và xuất ra cấu trúc `scene_schema.json`.
- Tự động gọi pipeline local (`build_video_from_director_json.py`) để render ra video hoàn chỉnh:
  1. Giọng đọc tiếng Việt tự nhiên (`edge-tts` với `vi-VN-NamMinhNeural` / `vi-VN-HoaiMyNeural`).
  2. Hoạt ảnh nhân vật cảm xúc (`LivePortrait` / micro-motion generator).
  3. Quy tắc 30/70: 30% Avatar Hook, 70% Cắt đè B-Roll toàn màn hình.
  4. Hiệu ứng Camera linh hoạt (`zoom_in_slow`, `zoom_in_fast`, `glitch_shake`, `whip_pan`).
  5. Cắt khoảng lặng chết (Auto-Editor/FFmpeg) + Audio Ducking BGM (-18dB khi có voice).

## Cách kích hoạt
Người dùng chỉ cần đưa chủ đề hoặc kịch bản thô:
> "Làm video về [chủ đề]" hoặc "Đạo diễn kịch bản sau: [nội dung]"

## Lệnh thực thi Backend
```bash
python pipeline/build_video_from_director_json.py <path_to_director.json>
```
Output xuất xưởng chuẩn định dạng dọc 9:16 (1080x1920) sẵn sàng đăng TikTok/Shorts/Reels.
