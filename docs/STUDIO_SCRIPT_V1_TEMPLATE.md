STUDIO SCRIPT V1
# =====================================================================
# MẪU KỊCH BẢN STUDIO SCRIPT V1 — sao chép toàn bộ tệp này để bắt đầu.
# - Thay mọi giá trị mẫu bằng nội dung thật của dự án. Tên trong mẫu này
#   (CHAR_NHAN_VAT_A, CHAR_NHAN_VAT_B, LOC_DIA_DIEM_X, PROP_VAT_DUNG_X)
#   là tên giả rõ ràng.
# - Giữ nguyên các khóa (PROJECT, CHARACTER, SCENE, ...). Khóa không phân
#   biệt hoa/thường; giá trị giữ nguyên tiếng Việt, không viết lại.
# - Dòng bắt đầu bằng # là ghi chú, không ảnh hưởng kịch bản. Dòng trống
#   cũng được bỏ qua. Dòng ⸻ là dấu phân cách giữa các khối.
# - QUY TẮC TIÊN QUYẾT (SPEC §16): mọi kịch bản đều kể ở NGÔI THỨ NHẤT.
#   Không bao giờ có người dẫn truyện bên ngoài. Mọi dòng NARRATION đều
#   do nhân vật chính đọc bằng giọng của nhân vật (VOICE_ID), và mọi
#   dòng thoại đều phải có SPEAKER trỏ tới một CHARACTER đã khai báo.
#   Khai báo STORYTELLING_MODE, PRIMARY_CHARACTER và EXTERNAL_NARRATOR:
#   NONE trong khối PROJECT, như mẫu dưới đây.
# - Lời dẫn và lời thoại được giữ nguyên từng chữ và đọc thành tiếng.
#   Các dòng khác (VISUAL, ACTION, CAMERA, VOICE_NOTE, ...) không bị đọc.
# - HEAD_RATIO chỉ nhận 0.33-0.35, mặc định 0.34. Không dùng 0.42.
# - Đặc tả đầy đủ: docs/STUDIO_SCRIPT_V1_SPEC.md
# =====================================================================

PROJECT
# PROJECT_ID: mã dự án, dùng làm tên thư mục Drive.
PROJECT_ID: DU_AN_MAU
# TITLE: tiêu đề hiển thị của video.
TITLE: Tiêu đề mẫu
# EPISODE: số tập.
EPISODE: 01
# GENRE: thể loại.
GENRE: Thể loại mẫu
# LANGUAGE: ngôn ngữ lời thoại và phụ đề; mặc định vi-VN.
LANGUAGE: vi-VN
# STORYTELLING_MODE: phải bắt đầu bằng FIRST_PERSON.
STORYTELLING_MODE: FIRST_PERSON_ROLEPLAY
# PRIMARY_CHARACTER: id của nhân vật kể chuyện (phải đã khai báo).
PRIMARY_CHARACTER: CHAR_NHAN_VAT_A
# EXTERNAL_NARRATOR: luôn NONE — không có người dẫn truyện bên ngoài.
EXTERNAL_NARRATOR: NONE
# PLATFORM: nền tảng phát hành.
PLATFORM: YouTube
# ASPECT_RATIO: chỉ 16:9 hoặc 9:16; mặc định 16:9.
ASPECT_RATIO: 16:9
# RESOLUTION: 1920x1080 hoặc 1280x720.
RESOLUTION: 1920x1080
# FPS: 24, 25 hoặc 30.
FPS: 24
# DURATION_MODE: AUDIO_DRIVEN để timeline theo độ dài giọng đọc thật.
DURATION_MODE: AUDIO_DRIVEN
# TARGET_DURATION: AUTO, số giây, hoặc khoảng như "85–100 seconds".
TARGET_DURATION: AUTO

⸻

VISUAL_STYLE
# STYLE: phong cách hình ảnh chung.
STYLE: Phong cách hình ảnh mẫu
# QUALITY_REFERENCE: tham chiếu chất lượng hình ảnh.
QUALITY_REFERENCE: Tham chiếu mẫu
# VISUAL_TARGET_SCORE: mục tiêu điểm hình ảnh.
VISUAL_TARGET_SCORE: 90/100
# DESIGN_POLICY: chính sách thiết kế (thiết kế gốc, không sao chép).
DESIGN_POLICY: Thiết kế gốc
# HEAD_RATIO: tỉ lệ đầu, chỉ 0.33-0.35; mặc định 0.34. Không dùng 0.42.
HEAD_RATIO: 0.34
# BODY_STYLE / OUTLINE / SHADING / LIGHTING / BACKGROUND / DEPTH:
# mô tả phong cách tạo hình và môi trường.
BODY_STYLE: Thân hình hoạt hình có khớp đầy đủ
OUTLINE: Nét viền sạch, tròn, nhất quán
SHADING: Tô bóng điện ảnh nhẹ
LIGHTING: Ánh sáng điện ảnh theo môi trường
BACKGROUND: Môi trường nhiều lớp chi tiết
DEPTH: Tiền cảnh, trung cảnh, hậu cảnh
# ANIMATION: hoạt hình khớp nối điều khiển bằng code.
ANIMATION: Hoạt hình khớp nối điều khiển bằng code
# FACIAL_ANIMATION / LIP_SYNC / EYE_TRACKING: bật theo yêu cầu.
FACIAL_ANIMATION: Enabled
LIP_SYNC: Enabled for dialogue
EYE_TRACKING: Enabled
# CAMERA_STYLE: phong cách quay.
CAMERA_STYLE: Kể chuyện điện ảnh
# COLOR_PROGRESSION: danh sách gạch đầu dòng theo cảnh.
COLOR_PROGRESSION:
* Cảnh mở đầu: màu ấm, ánh sáng dịu.
* Cảnh kết: màu lạnh, giảm độ bão hòa.
# Các cờ FORBIDDEN: không bao giờ dùng slideshow tĩnh hay video AI có sẵn.
STATIC_SLIDESHOW: FORBIDDEN
PREGENERATED_AI_VIDEO: FORBIDDEN

⸻

GLOBAL_AUDIO
# TTS_ENGINE: engine đọc giọng nói.
TTS_ENGINE: VieNeu-TTS
# LANGUAGE: lặp lại trong khối này là hợp lệ (phạm vi theo khối).
LANGUAGE: vi-VN
# TTS_SPEED: tốc độ đọc.
TTS_SPEED: 1.0
# VOICE_FALLBACK: NONE — không thay giọng tiếng Anh.
VOICE_FALLBACK: NONE
# VOICE_PRIORITY: ưu tiên giọng theo CHARACTER.
VOICE_PRIORITY: CHARACTER_VOICE_ID
# BGM_DUCKING: mức nén nhạc nền, có thể là khoảng như "12–18 dB".
BGM_DUCKING: 12–18 dB
# SFX_DENSITY / SFX_TRIGGER_MODE / AMBIENCE_MODE: chính sách âm thanh.
SFX_DENSITY: SPARSE
SFX_TRIGGER_MODE: EXPLICIT_ONLY
AMBIENCE_MODE: LOOP
# SUBTITLE_LANGUAGE / SUBTITLE_SYNC / SUBTITLE_STYLE: chính sách phụ đề.
SUBTITLE_LANGUAGE: vi-VN
SUBTITLE_SYNC: WORD_LEVEL
SUBTITLE_STYLE: SHORT_PHRASES
# Các cờ FORBIDDEN / DISABLED: không cắt âm thanh, không tăng tốc bất
# thường, không dùng âm thanh meme, không chèn whoosh chuyển cảnh tự động.
AUDIO_TRUNCATION: FORBIDDEN
UNNATURAL_AUDIO_SPEEDUP: FORBIDDEN
MEME_SOUND: DISABLED
AUTOMATIC_TRANSITION_WHOOSH: DISABLED

⸻

# --- NHÂN VẬT: một khối CHARACTER cho mỗi nhân vật. Id không trùng nhau.
# NAME là tên hiển thị; id (sau CHARACTER:) dùng để tham chiếu. ---
CHARACTER: CHAR_NHAN_VAT_A
NAME: Nhân vật A
ROLE: Nhân vật chính, người kể chuyện
AGE: 25
GENDER: Nam
NATIONALITY: Việt Nam
BODY_TYPE: Cân đối
HEAD_RATIO: 0.34
FACE_SHAPE: Tròn
HAIR: Tóc ngắn đen
EYES: Mắt tròn
SKIN_TONE: Sáng
DEFAULT_EXPRESSION: Bình tĩnh
PERSONALITY_PRESENTATION: Điềm đạm, quyết đoán
FACIAL_FEATURES: Nét mặt riêng biệt
# COSTUME_CIVILIAN: danh sách gạch đầu dòng.
COSTUME_CIVILIAN:
* Áo sơ mi trắng
* Quần dài sẫm màu
VOICE_ENGINE: VieNeu-TTS
VOICE_ID: GIONG_DOC_MAU_A
VOICE_SPEED: 1.0
VOICE_TONE: Ấm, rõ ràng
# ANIMATION_CAPABILITIES: danh sách khả năng chuyển động.
ANIMATION_CAPABILITIES:
* Đi bộ
* Cầm vật dụng
* Biểu cảm khuôn mặt
IDENTITY_LOCK: TRUE

CHARACTER: CHAR_NHAN_VAT_B
NAME: Nhân vật B
ROLE: Nhân vật phụ
AGE: 30
GENDER: Nữ
NATIONALITY: Việt Nam
BODY_TYPE: Mảnh
HEAD_RATIO: 0.34
FACE_SHAPE: Dài
HAIR: Tóc dài đen
EYES: Mắt to
SKIN_TONE: Sáng
DEFAULT_EXPRESSION: Tò mò
COSTUME:
* Áo dài truyền thống
VOICE_ENGINE: VieNeu-TTS
VOICE_ID: GIONG_DOC_MAU_B
VOICE_SPEED: 1.0
VOICE_TONE: Nhẹ nhàng
IDENTITY_LOCK: TRUE

⸻

# --- ĐỊA ĐIỂM: một khối LOCATION cho mỗi địa điểm. Id không trùng nhau. ---
LOCATION: LOC_DIA_DIEM_X
NAME: Địa điểm X
TYPE: EXTERIOR
YEAR: 2024
TIME_OF_DAY: MORNING
WEATHER: Nắng nhẹ
HISTORICAL_REFERENCE: Tham chiếu mẫu
# DISTINCTIVE_FEATURES: nét riêng của địa điểm, dạng gạch đầu dòng.
DISTINCTIVE_FEATURES:
* Cổng chào lớn
* Hàng cây dọc lối đi
FOREGROUND:
* Bồn hoa gần camera
MIDGROUND:
* Lối đi lát đá
BACKGROUND:
* Dãy nhà phía xa
LIGHTING: Ánh sáng buổi sáng dịu
COLOR_PALETTE: Xanh lá, vàng nhạt, nâu gỗ
AMBIENCE: Tiếng chim và tiếng bước chân xa
FORBIDDEN:
* Không thay địa điểm khác

⸻

# --- ĐẠO CỤ: một khối PROP cho mỗi vật dụng. ---
PROP: PROP_VAT_DUNG_X
TYPE: DOCUMENT
COLOR: Nâu nhạt
MATERIAL: Giấy
INTERACTION: Cầm, mở, đọc
DESCRIPTION: Vật dụng mẫu
OWNER: CHAR_NHAN_VAT_A

⸻

# --- CẢNH: SCENE: <ID> với TITLE, LOCATION (tham chiếu id hoặc văn bản),
# CHARACTERS (danh sách id, hoặc NONE), MOOD, STORY_PURPOSE. ---
SCENE: SC01
TITLE: Cảnh mẫu mở đầu
LOCATION: LOC_DIA_DIEM_X
CHARACTERS: CHAR_NHAN_VAT_A, CHAR_NHAN_VAT_B
MOOD: Bình yên
STORY_PURPOSE: Giới thiệu nhân vật chính và địa điểm
AMBIENCE: Tiếng chim buổi sáng
BGM: Nhạc nền nhẹ
TRANSITION: CUT

# SHOT: <ID> với CAMERA là văn bản tự do mô tả góc quay. TYPE (enum) là
# tùy chọn khi đã có CAMERA; khi có TYPE thì TYPE phải thuộc 9 loại shot.
SHOT: SC01_SH01
CAMERA: Medium shot, nhân vật chính ở trung tâm khung hình
CAMERA_MOVEMENT: STATIC
ACTION:
* Nhân vật chính bước tới và dừng lại.
* Nhân vật chính nhìn quanh.
EXPRESSION: Bình tĩnh, tò mò
# NARRATION / DIALOGUE: khối con với SPEAKER, LINE_ID, TEXT, LIP_SYNC.
# TEXT chỉ bóc một lớp dấu ngoặc kép ngoài cùng; nội dung giữ nguyên.
NARRATION:
SPEAKER: CHAR_NHAN_VAT_A
LINE_ID: MAU_001
TEXT: “Tôi bước vào địa điểm này lần đầu tiên.”
LIP_SYNC: REQUIRED
# SFX: khối con có cấu trúc (gạch đầu dòng ID / EVENT / TRIGGER / TYPE /
# INTENSITY / DURATION / DURATION_MODE), hoặc SFX: NONE.
SFX:
* ID: SFX_001
* EVENT: Tiếng bước chân
* TRIGGER: MAU_001
* TYPE: Foley
* INTENSITY: LOW
* DURATION: 0.4s
* DURATION_MODE: FIXED

SHOT: SC01_SH02
CAMERA: Close-up, nhân vật phụ nhìn về phía camera
CAMERA_MOVEMENT: Slow dolly-in
ACTION:
* Nhân vật phụ mỉm cười.
DIALOGUE:
SPEAKER: CHAR_NHAN_VAT_B
LINE_ID: MAU_002
TEXT: “Chào mừng bạn đến đây.”
LIP_SYNC: REQUIRED
SFX: NONE
POST_DIALOGUE_PAUSE: 0.6s

⸻

# GLOBAL_NEGATIVE_CONSTRAINTS: danh sách gạch đầu dòng các điều cấm.
GLOBAL_NEGATIVE_CONSTRAINTS:
* Không thay đổi danh tính nhân vật giữa các cảnh.
* Không thay thế địa điểm đã khai báo.
* Không cắt câu thoại cuối.

⸻

END_CARD
BACKGROUND: Đen
TEXT: HẾT
SECONDARY_TEXT: Cảm ơn bạn đã xem
TEXT_LANGUAGE: vi-VN
DURATION: 3s
BGM: NONE
SFX: NONE

⸻

QA
MIN_OVERALL_SCORE: 8.0/10
MIN_CATEGORY_SCORE: 7.0/10
TARGET_VISUAL_SCORE: 90/100
HARD_FAIL_COUNT: 0
EXPECTED_SCENES: 1
EXPECTED_SHOTS: 2
EXPECTED_SPOKEN_LINES: 2
EXPECTED_NARRATION_LINES: 1
EXPECTED_DIALOGUE_LINES: 1
EXPECTED_EXTERNAL_NARRATOR_LINES: 0
EXPECTED_EXPLICIT_SFX_EVENTS: 1
SCRIPT_INTEGRITY_CHECK: REQUIRED
CHARACTER_IDENTITY_CHECK: REQUIRED
LIP_SYNC_CHECK: REQUIRED
VIETNAMESE_LANGUAGE_CHECK: REQUIRED
MP4_VALIDATION: REQUIRED
HUMAN_VISUAL_REVIEW: REQUIRED
FAILED_QA_POLICY: BLOCK_MASTER

⸻

OUTPUT
VIDEO_FORMAT: MP4
VIDEO_CODEC: H.264
AUDIO_CODEC: AAC
PIXEL_FORMAT: yuv420p
RESOLUTION: 1920x1080
FPS: 24
EXPORT_DRAFT: TRUE
EXPORT_MASTER: HUMAN_APPROVAL_REQUIRED
EXPORT_SCRIPT: TRUE
EXPORT_SUBTITLES: TRUE
EXPORT_QA_REPORT: TRUE
UPLOAD_GOOGLE_DRIVE: TRUE
DRIVE_PROJECT_FOLDER: DU_AN_MAU
DRIVE_SUBFOLDERS:
* 01_SCRIPT
* 02_STORYBOARD
* 03_AUDIO
* 04_DRAFT
* 05_QA_REPORTS
* 06_MASTER
MASTER_APPROVAL: HUMAN_REQUIRED

END STUDIO SCRIPT V1
