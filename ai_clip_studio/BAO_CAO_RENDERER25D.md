# BÁO CÁO — Renderer 2.5D + Shot Director + Ngôn ngữ (§2, §4, §5, §8)

Ngày: 2026-11-11. Agent: renderer 2.5D / shot director / ngôn ngữ (không đụng
`character_art.py` / `rig.py` / `primitives.py` / `qa_gates.py` /
`subtitles.py`, không sửa `video-upstream/`, không push GitHub, không render
video dài hay prototype 12–15s — việc đó do agent khác làm sau, dùng engine
này). Chuẩn tham khảo phong cách: kênh @RicksClips3000 chỉ dùng làm chuẩn về
mức hoàn thiện hình ảnh / ánh sáng / dựng cảnh / nhịp kể / diễn xuất, không
sao chép nhân vật, video, tài nguyên hay thiết kế nhận diện của kênh.

## 1. Probe Chrome (VM này) — KẾT LUẬN: KHÔNG CHẠY ĐƯỢC, đã kiểm chứng lại

Lệnh + output (2026-11-11):

```
$ python3 -c "from ai_clip_studio.chrome_detect import detect_chrome; print(detect_chrome())"
(None, 'no usable Chrome: /opt/meta-chromium/chrome: cannot launch
([1111/080551.123014:ERROR:chrome/app/chrome_main_delegate.cc:1283]
Hatch WebGL domain policy is required for browser startup)')
$ /opt/meta-chromium/chrome --headless --no-sandbox --disable-gpu \
    --disable-dev-shm-usage --disable-webgl --dump-dom about:blank
[1111/081132.585877:ERROR:chrome/app/chrome_main_delegate.cc:1283]
Hatch WebGL domain policy is required for browser startup
```

- Đây là policy của Hatch chặn ngay lúc khởi động, không phải thiếu flag
  (đã thử cả `--headless=new` và `--headless`, có/không `--disable-webgl`).
- Không có trình duyệt khác: `chromium`, `chromium-browser`,
  `google-chrome`, `firefox` đều không có trên PATH/`/usr/bin`;
  `playwright` chưa cài, `~/.cache/ms-playwright` không tồn tại.
- Hệ quả: Motion Canvas + Three.js **không thể chạy trên VM này**.
  Renderer dự phòng frame-by-frame (§2c) là đường duy nhất trên VM;
  video cuối vẫn cần máy Windows có Chrome thật (§2a).

## 2. Kiến trúc 2.5D mới

### 2a. Motion Canvas + Three.js (đường chính, chạy trên Windows)

`ai_clip_studio/motioncanvas25d/` — code mới, không sửa upstream; pattern
theo upstream đã đọc (`three/ThreeWorldAdapter.ts`,
`three/UniversalWorldEngine.ts` V4.2.3, `three/ThreeWorldNode.ts`,
`components/UniversalCharacterEngine.ts` — chỉ tham khảo, không copy cảnh
Munich/Edo/lab):

| File | Vai trò |
|---|---|
| `World25D.ts` | Thế giới 3D data-driven theo `World25DSpec` JSON: ground plane + hộp solid với `MeshStandardMaterial`, key `DirectionalLight` **có shadow map** (2048, PCFSoft), `HemisphereLight` fill, `PointLight` tùy ý, fog, tone mapping ACES; camera keyframes nội suy smoothstep; `projectToScreen()` / `characterScreenBoxes()` để gắn nhân vật 2D vào không gian 3D |
| `ThreeWorld25DNode.ts` | Node Motion Canvas 2D: render WebGL vào offscreen canvas mỗi frame rồi vẽ vào scene graph (đúng pattern `ThreeWorldNode.ts` upstream) |
| `scene25d.tsx` | Scene Motion Canvas: world 3D ở dưới, nhân vật 2D ở trên, vị trí lấy từ `characterScreenBoxes()` mỗi frame; duration lấy từ timeline (độ dài giọng đọc thật, không fix 15s) |
| `render25d.mjs` | Render độc lập bằng puppeteer-core (không cần Motion Canvas): load page chứa `World25D`, bước timeline 24fps, screenshot từng frame. **Đường dẫn Chrome không hardcode**: `$CHROME_PATH` → PATH → đường dẫn Windows quen thuộc; mỗi ứng viên đều launch-probe, không có Chrome thì thoát mã 2 và báo rõ |
| `example_spec.json` | Spec phố đêm chung chung (nhà gần / bàn giữa / tháp xa, đèn đường, camera lia 5s) — đổi spec là đổi cảnh, không sửa code |
| `package.json` | Deps khớp upstream: `@motion-canvas/2d` + `core` 3.17.2, `three` 0.170.0, `puppeteer-core` 25.16.0 |
| `README_WINDOWS.md` | Hướng dẫn chạy trên máy Windows của Mai (npm install → smoke test 5s → render Motion Canvas) |

Kiểm chứng trên VM: `node --check render25d.mjs` OK; `node
--experimental-strip-types --check` OK cho `World25D.ts` và
`ThreeWorld25DNode.ts` (scene `.tsx` chứa JSX nên không check được bằng
Node — cần `tsc` trên máy Windows). **Chưa chạy được render thật** (không
có Chrome, §1) — Mai chạy smoke test theo README trên Windows.

### 2b. Renderer dự phòng frame-by-frame 2.5D (chạy được trên VM)

`ai_clip_studio/renderer25d/` — phép chiếu phối cảnh thật, không vignette:

| File | Vai trò |
|---|---|
| `camera.py` | `PerspectiveCamera`: tiêu cự từ FOV dọc, cơ sở look-at, chia phối cảnh `focal/depth`; điểm sau near plane báo không nhìn thấy; nội suy keyframe |
| `lighting.py` | `LightRig`/`PointLight`/`DirectionalLight`: suy giảm `1/(1+k·d²)` + cosine Lambert; `contact_shadow()` — bóng tiếp xúc từ chiều cao vật (độ lệch/tán/độ đậm đều phụ thuộc chiều cao và góc nắng) |
| `scene.py` | `Scene25D`: mặt đất y=0, `Box3D` 6 mặt có normal, `CharacterAnchor` (vị trí chân + chiều cao); `depth_layers()` xếp FG/MG/BG theo độ sâu từ camera |
| `render.py` | `render_frame()`: trời → lưới mặt đất chiếu phối cảnh → bóng tiếp xúc → hộp/nhân vật xa→gần, mỗi mặt tô sáng theo light rig. Nhân vật mặc định chỉ là marker trung tính; nhân vật thật cắm qua callback `draw_character` (art thuộc character engine, không vẽ lại ở đây) |
| `README.md` | Ma trận tính năng trung thực (xem §2c) |
| `proof_frame_{left,center,right}.png` | 3 frame tĩnh chứng minh parallax (camera lia ±1.5) |

Bằng chứng test: 15 test trong `tests/test_renderer25d.py` — cùng vật ở z
khác nhau thì kích thước/vị trí chiếu khác đúng phối cảnh (tỉ lệ =
nghịch đảo độ sâu); camera dịch chuyển thì lớp gần dịch nhanh hơn lớp xa
(tỉ lệ đúng `1/z`); bóng đổ dịch đúng khi vật dịch chuyển và loãng/xa dần
khi vật nâng cao. Trong lúc làm đã bắt và sửa 2 lỗi thật: (1) test kỳ vọng
tỉ lệ kích thước theo khoảng cách z thô — sai, phải theo độ sâu dọc trục
forward; (2) PIL `ImageDraw` không blend alpha trên ảnh RGBA (lưới mặt
đất alpha 16 biến thành trắng đục sau `convert("RGB")`) — sửa bằng overlay
+ `alpha_composite` và outline pre-blend.

### 2c. Ma trận tính năng TRUNG THỰC — fallback vs Motion Canvas + Three.js

| Tính năng 2.5D | Fallback (renderer25d) | Motion Canvas + Three.js |
|---|---|---|
| Không gian 3D thực, camera phối cảnh | ✅ phối cảnh thật | ✅ |
| Mặt đất + công trình hình khối | ✅ hộp 3D chiếu phối cảnh | ✅ mesh 3D |
| Ánh sáng có nguồn phát thực | ✅ điểm + hướng, suy giảm theo khoảng cách/góc | ✅ + shadow map |
| Bóng đổ / bóng tiếp xúc | ⚠️ GIẢI TÍCH 2D: ellipse mờ, đúng hướng/độ lệch theo chiều cao; **không** shadow map, không bóng lên tường/vật khác, không self-shadow | ✅ shadow map thật |
| Vật liệu phản ứng ánh sáng | ⚠️ CHỈ màu phẳng + Lambert; **không** roughness/metalness, phản chiếu, texture | ✅ MeshStandardMaterial |
| FG/MG/BG khoảng cách thực | ✅ độ sâu thật, parallax từ phép chiếu | ✅ |
| Camera di chuyển + parallax | ✅ keyframe nội suy | ✅ |
| Nhân vật 2D/2.5D trong không gian | ⚠️ CHỈ vị trí + tỉ lệ đúng phối cảnh (marker/callback); diễn xuất/rig/IK thuộc character engine | ✅ gắn qua world-to-screen, rig đầy đủ |
| Che khuất (occlusion) | ⚠️ CHỈ painter's order theo tâm vật; hộp chồng nhau có thể sai ở mặt kề | ✅ depth buffer thật |
| Tốc độ | ~0.2–0.5s/khung 960×540 (PIL, CPU) | GPU WebGL, realtime |
| Chạy trên VM này | ✅ | ❌ (§1) |

**Fallback KHÔNG tương đương Motion Canvas + Three.js về chất lượng hình
ảnh.** Nó chỉ chứng minh được hình học 2.5D (phối cảnh, parallax, bóng
tiếp xúc theo chiều cao, ánh sáng theo góc/khoảng cách) và dùng để kiểm
thử logic đạo diễn + test clip khi chưa có Chrome.

## 3. Shot Director (§4) — `camera_planner.py` mở rộng

`ShotDirector.direct(segments, scene_package)` (thêm mới, **không đổi**
hành vi `CameraPlanner.plan()` cũ):

- Lấy đúng các shot của planner, **1:1 — không tăng số lượng shot**
  (test khẳng định count + durations giữ nguyên), mỗi shot gắn thêm
  `direction` với đúng 9 khóa: `attention_target` (khán giả cần chú ý
  cái gì + tại sao), `main_action`, `emotion`, `angle`, `shot_size`,
  `character_positions` (theo vai trò speaker/receiver/object/scene,
  không theo tên nhân vật; có `world_anchors` nếu scene package cho vị
  trí thế giới), `lighting` (preset theo `time_of_day`/`mood`/`weather`
  của scene package), `camera_move` (kèm `camera_path` from/to vị trí +
  target trong đơn vị thế giới — dolly_in tiến 15% dọc trục forward,
  tracking trượt 1.5, crane lên 1.2, arc/pan/tilt đổi target — để
  renderer 2.5D chạy bằng `PerspectiveCamera.interpolate()`), `cut_point`
  (cắt ở `action_peak` / `reaction_beat` / `line_end` kèm lý do: cắt ngay
  lúc vật đổi tay, sau khi mặt đã biểu lộ cảm xúc, giữa bước mạnh nhất…).
- `ShotDirector.validate_direction(shots)` kiểm tra mọi shot có đủ 9 khóa
  và giá trị nằm trong từ vựng cho phép; shot không đủ direction thì
  không được render.
- Điều khiển bằng dữ liệu: cùng segments, scene package đêm-mưa-lạnh vs
  ngày-ấm cho lighting và vị trí khác nhau (test khẳng định); không có
  tên truyện/nhân vật/cảnh nào trong output (test quét "Minh/Lan/Lustig/
  Eiffel/wallet/Ví/Tháp").

## 4. Ngôn ngữ (§5)

### 4a. Kết quả kiểm tra 2 câu TTS nghi sai ở Chiếc Ví v4 — CHƯA XÁC NHẬN LÀ TTS SAI

File wav gốc v4 còn nguyên: `acceptance_loop/test_chiec_vi_trong_mua/jobs/
req_d25bab7756d5/voices/line03_narrator.wav` (MAI_01) và
`line09_Minh.wav` (ronan). Quy trình: transcribe lại wav gốc bằng
faster-whisper `small` → thu lại cả 2 câu bằng đúng giọng cũ + thu lại
bằng giọng khác (MAI_03) → transcribe lại → đối chiếu minimal-pair
("May" vs "Mày" cố ý, "hoảng" vs "khoảng" cố ý) bằng phân tích cao độ
F0 (autocorrelation, numpy) và tỉ lệ năng lượng cao tần ở onset.

| File | Whisper small nghe thành | WER (small) |
|---|---|---|
| v4 gốc line03 (MAI_01) | "…cô gái **hốt khoảng** chạy tới." (+ "ví"→"vĩ", "đã"→"đả", "cũ"→"củ") | 0.25 |
| Thu lại line03 (MAI_01) | "…**hốt khoảng**…" (các lỗi khác giảm) | 0.15 |
| Thu lại line03 (MAI_03) | "…**hút khoảng**…" ("Bên tròng", "đả cụ") | 0.30 |
| v4 gốc line09 (ronan) | "**Mày quá**, tôi cũng đang tìm…" | 0.10 |
| Thu lại line09 (ronan) | "**Mày quá**…" | 0.10 |
| Thu lại line09 (MAI_03) | "**Mày quá**…" | 0.10 |

Đổi giọng **không** sửa được lỗi nghe — cả 2 giọng, cả 2 lần thu đều bị
nghe thành "Mày"/"khoảng". Nhưng đó chưa phải bằng chứng TTS sai, vì
Whisper `small` tự nó đã sai hàng loạt từ có dấu trong **cùng các câu
đó** ("ví"→"vĩ", "đã"→"đả", "cũ"→"củ", "Bên trong"→"Bên tròng") —
transcriber nhầm thanh điệu/phụ âm đầu là lỗi kinh điển của ASR tiếng
Việt, không phải lỗi phát âm.

Bằng chứng phân biệt (F0, từ "May" vs "Mày" cố ý, cùng giọng ronan):

- "May quá" (nghi sai): onset ~123 Hz, gần như phẳng (124→113 Hz);
  "quá" sau đó tăng đúng thanh sắc (150→174 Hz).
- "Mày quá" (cố ý): onset ~107 Hz và rơi (107→95 Hz) — đúng thanh huyền
  (thấp + rơi).

TTS **phân biệt được** "May" (ngang: cao + phẳng) với "Mày" (huyền: thấp
+ rơi). Kết luận: **khả năng cao TTS đọc "May quá" đúng, Whisper small
nghe nhầm** — không xác nhận là TTS sai. Với "hốt hoảng": test onset
phụ âm (tỉ lệ năng lượng ≥4 kHz) không phân biệt được (0.062 vs 0.040,
ngược hướng giả thuyết, biên từ của Whisper không chắc) → **không kết
luận được** bằng phép đo này.

**Vì vậy KHÔNG thu lại/thay giọng 2 câu này** (đổi giọng đã thử và không
đổi kết quả nghe; thu lại cùng giọng cũng vậy). Việc còn lại cần tai
người: **Mai nghe trực tiếp 2 file wav gốc** (line03/line09 trong
`req_d25bab7756d5/voices/`) để phán quyết cuối — máy không thay được tai
người ở đây. Đã thử Whisper `medium` để có transcriber mạnh hơn: model
đã tải về cache (323 MB) nhưng chạy trên VM 1.5 CPU quá chậm (10+ phút
cho 4 file ngắn, 0 output) nên đã dừng; có thể chạy lại trên máy mạnh
hơn. File chi tiết: `ai_clip_studio/language_work/retake_wer.jsonl`
(6 dòng WER), wav thu lại trong `language_work/retake/`
(`line03_MAI_01/MAI_03`, `line09_ronan/MAI_03`,
`pair_may_ronan`, `pair_khoang_MAI_01` + `.wav` 16k).

### 4b. Kịch bản Eiffel bản Việt + voice test — ĐÃ CHUẨN BỊ, CHƯA RENDER VIDEO

`ai_clip_studio/language_work/eiffel_vi_script.json` — dịch 5 câu
narration của Eiffel v4 (`package_v4.json` SH01–SH05) sang tiếng Việt,
giữ hook/twist/payoff, tên riêng giữ nguyên:

1. SH01 (HOOK): "Hắn đã bán tháp Eiffel những hai lần, mà không ai ngăn cản."
2. SH02: "Một tay buôn phế liệu đã tin hắn, đưa tiền hối lộ rồi giao cả tiền mua tháp."
3. SH03: "Lustig ôm tiền rồi lên ngay chuyến tàu rời khỏi Paris."
4. SH04 (TWIST): "Chẳng ai trình báo vụ lừa đảo, vì nạn nhân xấu hổ quá."
5. SH05 (PAYOFF): "Thế là Lustig quay lại Paris, định bán tháp lần thứ hai."

Voice test: cả 5 câu thu bằng `avocado_v2:MAI_01` (narrator), `--language
vi`, speed 100 — file trong `language_work/eiffel_vi/` (`SH01–SH05.mp3` +
`.wav`). Transcribe kiểm chứng bằng faster-whisper `small`:

| Câu | Nghe thành (small) | WER |
|---|---|---|
| SH01 | "…tháp **FL** những 2 lần…" (Eiffel→FL) | 0.154 |
| SH02 | "…tay **buông** phế liệu đã **tình hắng**…" | 0.167 |
| SH03 | "Lustig **Om Tien Đồi** Lên Ngay **Chuyên** Tàu **Đồi Khói** Paris" | 0.545 |
| SH04 | gần như đúng hoàn toàn | **0.0** |
| SH05 | "…**los stick** quay lại **party** đến **băng** tháp lần thứ 2." | 0.5 |
| **Tổng** | | **0.254 (17/67 từ)** |

Đọc đúng con số: WER 0.254 **không có nghĩa TTS đọc dở** — lỗi tập
trung ở tên riêng nước ngoài (Eiffel/Lustig/Paris Whisper small nghe
thành "FL"/"los stick"/"party") và mất dấu thanh (ôm→Om, rồi→Đồi);
toàn bộ từ tiếng Việt nội dung đều có mặt, SH04 đúng 100%. Voice test
đủ điều kiện làm narration sẵn sàng sau khi Mai duyệt prototype — nhưng
tên riêng cần Mai nghe tai kiểm chứng. **Không render video Eiffel
trong đợt này** (theo nhiệm vụ).

### 4c. Language gate — `ai_clip_studio/language_gate.py` (mới)

- `DEFAULT_LANGUAGE = "vi-VN"`; `check_production_language()` FAIL mọi
  caption/narration trông giống tiếng Anh trong production vi-VN
  (heuristic stopwords + tỉ lệ ASCII).
- **Kiểm chứng Eiffel v5: 5/5 câu caption tiếng Anh → gate FAIL** (test
  khẳng định) — đây là lỗi, không được PASS khi request đặt vi-VN.
- `resolve_voice()` **không có fallback giọng Anh**: request ngôn ngữ
  không phải vi-VN thì raise `ValueError` thay vì trả giọng Anh.
- Giọng Việt dùng trong pipeline: narrator `avocado_v2:MAI_01`, nam
  `avocado_v2:ronan`, nữ `avocado_v2:paloma`, mặc định
  `avocado_v2:MAI_03` (đều với `--language vi`).

## 5. Định dạng 9:16 (§8) — ĐÃ LÀM Ở MỨC FRAMING/CONFIG, chưa tích hợp render

`ai_clip_studio/framing_9x16.py` (mới) — framing riêng, không phải crop mù:

- **Đường đúng: re-render từ scene 3D.** `vertical_camera_for_shot()`
  trả về `PerspectiveCamera` tỉ lệ 9:16, dolly lại gần chủ thể theo loại
  shot (establishing 10%, medium/tracking 30%, close-up/reaction/
  insert 45–50%) để chủ thể giữ kích thước trên khung hẹp; establishing
  cảnh báo rõ là mất hai bên trong 9:16.
- **Đường fallback: crop master 16:9 đã render.** `vertical_crop_for_shot()`
  trả cửa sổ 608×1080 căn theo focus của shot (clamp trong khung),
  `focus_kept` báo focus có còn trong khung không, kèm caption safe zone
  riêng cho dọc (dưới 1/3, trên vùng 8% đáy cho UI/ngón tay, biên 6%).
- Chưa làm: tích hợp framing này vào pipeline render (renderer 2.5D hiện
  chỉ render 16:9) và chưa có video 9:16 mẫu — việc đó thuộc về đợt
  render prototype sau, dùng `vertical_camera_for_shot()`.

## 6. Kiểm thử — regression PASS

```
$ python3 -m unittest discover -s ai_clip_studio/tests
Ran 186 tests in 18.4s — OK
$ python3 -m unittest discover -s youtube_16x9/tests
Ran 11 tests — OK
```

Tổng **197 test pass, 0 fail**. Baseline trước đợt này: 123 + 11.
Mới trong đợt này (+33): `test_renderer25d.py` (15),
`test_shot_director.py` (8), `test_language_and_framing.py` (10).
+30 còn lại là `test_character_v3.py` của agent character làm song song
(không phải của đợt này, không đụng vào). `camera_planner.py` cũ vẫn
pass nguyên (24 test).

## 7. File đã tạo / sửa trong đợt này (chỉ trong `video-16x9-v2/`)

Tạo mới: `ai_clip_studio/renderer25d/` (`__init__.py`, `camera.py`,
`lighting.py`, `scene.py`, `render.py`, `README.md`,
`proof_frame_{left,center,right}.png`); `ai_clip_studio/motioncanvas25d/`
(`World25D.ts`, `ThreeWorld25DNode.ts`, `scene25d.tsx`, `render25d.mjs`,
`example_spec.json`, `package.json`, `README_WINDOWS.md`);
`ai_clip_studio/language_gate.py`, `ai_clip_studio/framing_9x16.py`;
`ai_clip_studio/language_work/` (`eiffel_vi_script.json`,
`eiffel_vi/SH01–SH05.{txt,mp3,wav}`, `retake/*.mp3/*.wav`,
`retake_wer.jsonl`); test mới: `ai_clip_studio/tests/test_renderer25d.py`,
`test_shot_director.py`, `test_language_and_framing.py`; báo cáo này
`ai_clip_studio/BAO_CAO_RENDERER25D.md`.

Sửa: `ai_clip_studio/camera_planner.py` — **chỉ thêm** ShotDirector +
alias ở cuối file (305 dòng cũ nguyên vẹn, test cũ pass hết).
Không sửa: `video-upstream/` (chỉ đọc), `animation/character_art.py` /
`rig.py` / `primitives.py`, `qa_gates.py`, `subtitles.py`. Không push GitHub.

## 8. Giới hạn còn lại / chưa làm được

1. **Motion Canvas + Three.js chưa chạy được lần nào** (không có Chrome
   trên VM, §1). Code TS mới chỉ qua kiểm tra cú pháp Node, chưa qua
   `tsc`, chưa render 1 frame thật nào — cần Mai chạy smoke test trên
   Windows theo `motioncanvas25d/README_WINDOWS.md`.
2. **2 câu TTS nghi sai chưa có phán quyết cuối** — bằng chứng nghiêng về
   "Whisper small nghe nhầm, TTS đọc đúng" (đặc biệt "May quá" có bằng
   chứng F0), nhưng phán quyết cuối cần tai người (Mai) hoặc ASR mạnh
   hơn (Whisper medium đã tải về nhưng quá chậm trên VM).
3. **9:16 chưa có video mẫu**, chưa tích hợp vào pipeline render.
4. **Không render prototype 12–15s, không render video dài** trong đợt
   này (theo nhiệm vụ — agent render làm sau bằng engine này).
5. Eiffel tiếng Việt: tên riêng (Eiffel/Lustig/Paris) TTS đọc có thể cần
   Mai nghe kiểm chứng; chưa có video Eiffel tiếng Việt.
