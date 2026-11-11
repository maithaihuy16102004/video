# Renderer 2.5D dự phòng (frame-by-frame, PIL) — `ai_clip_studio/renderer25d/`

Renderer cũ (`animation/environment_art.py` + `acceptance_loop/.../render_cv.py`)
vẽ mặt phẳng 2D rồi crop/zoom camera, chiều sâu giả bằng vignette +
gradient. Module này thay bằng **phép chiếu phối cảnh thật**:

- `camera.py` — `PerspectiveCamera`: tiêu cự từ FOV dọc, cơ sở look-at,
  chia phối cảnh theo độ sâu (`focal / depth`). Điểm sau mặt phẳng near
  được báo là không nhìn thấy, không vẽ ngược.
- `lighting.py` — `LightRig` / `PointLight` / `DirectionalLight`:
  suy giảm theo khoảng cách `1/(1+k·d²)` + cosine Lambert theo góc mặt;
  `contact_shadow()` tính bóng tiếp xúc từ chiều cao vật so với mặt đất
  (độ lệch, độ tán, độ đậm đều phụ thuộc chiều cao và góc nắng).
- `scene.py` — `Scene25D`: mặt đất y=0, `Box3D` (hình khối thật, 6 mặt,
  normal riêng), `CharacterAnchor` (vị trí chân + chiều cao trong thế
  giới 3D). `depth_layers()` xếp FG/MG/BG theo độ sâu từ camera, không
  theo lớp vẽ cố định.
- `render.py` — `render_frame()`: bầu trời (chỉ phần trên đường chân
  trời) → lưới mặt đất chiếu phối cảnh → bóng tiếp xúc → hộp/nhân vật
  vẽ xa-trước-gần-sau, mỗi mặt tô sáng theo light rig. Nhân vật mặc
  định chỉ là marker trung tính; nhân vật thật được cắm qua callback
  `draw_character` — art nhân vật thuộc về `animation/character_art.py`,
  không vẽ lại ở đây.

## Ma trận tính năng — TRUNG THỰC (fallback vs Motion Canvas + Three.js)

| Tính năng 2.5D | Fallback này | Motion Canvas + Three.js (`motioncanvas25d/`) |
|---|---|---|
| Không gian 3D thực, camera phối cảnh | ✅ phép chiếu phối cảnh thật | ✅ PerspectiveCamera thật |
| Mặt đất + công trình có hình khối | ✅ hộp 3D chiếu phối cảnh | ✅ mesh 3D (Box/Cylinder/Plane…) |
| Ánh sáng có nguồn phát thực | ✅ điểm + hướng, suy giảm theo khoảng cách/góc | ✅ Directional/Point/Hemisphere + shadow map |
| Bóng đổ / bóng tiếp xúc | ⚠️ BÓNG GIẢI TÍCH 2D: ellipse mờ, đúng hướng/độ lệch theo chiều cao, nhưng KHÔNG có shadow map — không có bóng đổ lên tường/vật khác, không tự che bóng (self-shadow) | ✅ shadow map thật, bóng đổ lên mọi bề mặt |
| Vật liệu phản ứng với ánh sáng | ⚠️ CHỈ MÀU PHẲNG + Lambert: không có roughness/metalness, không phản chiếu (mặt đường ướt), không texture | ✅ MeshStandardMaterial (roughness/metalness, env map) |
| FG/MG/BG khoảng cách thực | ✅ độ sâu thật từ camera, parallax từ phép chiếu | ✅ độ sâu thật |
| Camera di chuyển + parallax | ✅ keyframe nội suy, parallax đúng phối cảnh | ✅ keyframe + orbit/dolly thật |
| Nhân vật 2D/2.5D đặt trong không gian | ⚠️ CHỈ VỊ TRÍ + TỈ LỆ đúng phối cảnh (marker/callback); diễn xuất, rig, IK thuộc character engine | ✅ nhân vật 2D gắn qua world-to-screen, rig đầy đủ |
| Che khuất (occlusion) | ⚠️ CHỈ painter's order xa→gần theo tâm vật; hộp chồng nhau có thể sai thứ tự ở mặt kề | ✅ depth buffer thật, che khuất đúng từng pixel |
| Tốc độ render | ~0.2–0.5s/khung 960×540 (PIL, CPU) | GPU WebGL, realtime |
| Chạy được trên VM này | ✅ thuần Python + PIL | ❌ Chrome trên VM không launch được (xem báo cáo) |

**Kết luận:** fallback KHÔNG tương đương Motion Canvas + Three.js về
chất lượng hình ảnh. Nó chỉ chứng minh được hình học 2.5D (phối cảnh,
parallax, bóng tiếp xúc theo chiều cao, ánh sáng theo góc/khoảng cách)
và dùng để kiểm thử logic đạo diễn + test clip khi chưa có Chrome.
Video cuối vẫn cần render bằng Motion Canvas + Three.js trên máy có
Chrome thật.
