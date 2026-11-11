# Motion Canvas + Three.js 2.5D — Hướng dẫn chạy trên máy Windows (Mai chạy)

> ⚠️ **Trên VM Linux này KHÔNG chạy được** (xem "Giới hạn đã biết" bên dưới).
> Các bước dưới đây chạy trên máy Windows có Chrome thật.

## 1. Cài đặt (một lần)

```powershell
cd <repo>\ai_clip_studio\motioncanvas25d
npm install
npm run build-world        # esbuild World25D.ts -> World25D.js (cho render25d.mjs)
```

Phiên bản khớp với upstream (`video-upstream/package.json`):
`@motion-canvas/2d` + `@motion-canvas/core` 3.17.2, `three` 0.170.0,
`puppeteer-core` 25.16.0.

## 2. Smoke test — render 5 giây bằng Chrome thật (không cần Motion Canvas)

```powershell
node render25d.mjs --spec example_spec.json --out frames --fps 24
```

Script tự tìm Chrome theo thứ tự: `$env:CHROME_PATH` → Chrome trên PATH →
`C:\Program Files\Google\Chrome\Application\chrome.exe` →
`C:\Program Files (x86)\...`. **Không hardcode** đường dẫn Windows như
upstream `scripts/production_render_service.mjs:137` (đó là lỗi đã biết:
trên máy khác là sai đường dẫn). Mỗi ứng viên đều được launch-probe
(`--dump-dom about:blank`, exit 0) trước khi dùng; nếu không có Chrome
nào chạy được, script thoát với mã 2 và in rõ lý do — không render giả.

Kết quả đúng: 120 file `frames/frame_0000.png` … `frame_0119.png`
(1920×1080, 24fps), camera lia từ trái sang phải, tháp xa parallax
chậm hơn nhà gần, bóng đổ dưới các hộp.

## 3. Render bằng Motion Canvas (đường chính)

`scene25d.tsx` là một Motion Canvas scene 2D chuẩn: `ThreeWorld25DNode`
vẽ thế giới 3D vào một offscreen canvas mỗi frame, nhân vật 2D vẽ ở lớp
trên, vị trí lấy từ `characterScreenBoxes()` (chân chạm đất, chiều cao
theo đúng độ sâu camera). Chạy bằng Motion Canvas CLI trong project
Motion Canvas của Mai, truyền `spec` (xây từ scene package) và
`durationSeconds` (độ dài giọng đọc thật, không fix 15s).

## 4. Spec là dữ liệu, không phải code

`example_spec.json` là một phố đêm chung chung (nhà gần / bàn giữa /
tháp xa, đèn đường, camera lia 5s). Pipeline xây spec từ scene package:
mặt đất, hộp, đèn, keyframe camera, vị trí nhân vật — không hardcode
theo Chiếc Ví hay Eiffel. Đổi spec là đổi cảnh, không sửa code.

## Giới hạn đã biết (VM Linux này, kiểm chứng 2026-11-11)

- `detect_chrome()` → `(None, 'no usable Chrome: /opt/meta-chromium/chrome:
  cannot launch ([1111/080551...] Hatch WebGL domain policy is required
  for browser startup)')`. Chrome duy nhất trên VM không launch được
  làm puppeteer executable — đây là policy của Hatch, không phải lỗi
  thiếu flag (đã thử `--headless=new --no-sandbox --disable-gpu
  --disable-dev-shm-usage`).
- Không có trình duyệt khác: `chromium`, `google-chrome`, `firefox` đều
  không có trên PATH; `playwright` chưa cài, không có browser
  Playwright nào trong `~/.cache/ms-playwright`.
- Vì vậy trên VM này chỉ chạy được renderer dự phòng frame-by-frame
  (`ai_clip_studio/renderer25d/`, xem `README.md` trong đó để biết
  ma trận tính năng trung thực). Video cuối vẫn cần render bằng
  Motion Canvas + Three.js trên máy Windows có Chrome thật.
