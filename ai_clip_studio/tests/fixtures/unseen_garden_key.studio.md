STUDIO SCRIPT V1
# Fixture for the semantic regression matrix (directive §16) and
# TEST E (unseen script). NOT a Mai-supplied story: new characters,
# locations and props, written to exercise the 16 distinction
# families through the real pipeline. No per-script code may depend
# on this fixture's content.

PROJECT
PROJECT_ID: TESTE_UNSEEN_GARDEN_KEY
TITLE: Chiếc chìa khóa trong vườn
EPISODE: 01
GENRE: Đời thường
LANGUAGE: vi-VN
STORYTELLING_MODE: FIRST_PERSON_ROLEPLAY
PRIMARY_CHARACTER: CHAR_GARDENER
EXTERNAL_NARRATOR: NONE
PLATFORM: YouTube
ASPECT_RATIO: 16:9
RESOLUTION: 1920x1080
FPS: 24
DURATION_MODE: AUDIO_DRIVEN
TARGET_DURATION: AUTO

⸻

VISUAL_STYLE
STYLE: RicksClips stickman đơn giản, nét viền sạch
QUALITY_REFERENCE: Tham chiếu nội bộ
VISUAL_TARGET_SCORE: 90/100
DESIGN_POLICY: Thiết kế gốc
HEAD_RATIO: 0.34
BODY_STYLE: Thân hình hoạt hình có khớp đầy đủ
OUTLINE: Nét viền sạch, tròn, nhất quán
SHADING: Tô bóng điện ảnh nhẹ
LIGHTING: Ánh sáng điện ảnh theo môi trường
BACKGROUND: Môi trường nhiều lớp chi tiết
DEPTH: Tiền cảnh, trung cảnh, hậu cảnh
ANIMATION: Hoạt hình khớp nối điều khiển bằng code
FACIAL_ANIMATION: Enabled
LIP_SYNC: Enabled for dialogue
EYE_TRACKING: Enabled
CAMERA_STYLE: Kể chuyện điện ảnh
COLOR_PROGRESSION:
* Cảnh mở đầu: màu ấm, ánh sáng dịu.
* Cảnh kết: màu lạnh, giảm độ bão hòa.
STATIC_SLIDESHOW: FORBIDDEN
PREGENERATED_AI_VIDEO: FORBIDDEN

⸻

GLOBAL_AUDIO
TTS_ENGINE: VieNeu-TTS
LANGUAGE: vi-VN
TTS_SPEED: 1.0
VOICE_FALLBACK: NONE
VOICE_PRIORITY: CHARACTER_VOICE_ID
BGM_DUCKING: 12–18 dB
SFX_DENSITY: SPARSE
SFX_TRIGGER_MODE: EXPLICIT_ONLY
AMBIENCE_MODE: LOOP
SUBTITLE_LANGUAGE: vi-VN
SUBTITLE_SYNC: WORD_LEVEL
SUBTITLE_STYLE: SHORT_PHRASES
AUDIO_TRUNCATION: FORBIDDEN
UNNATURAL_AUDIO_SPEEDUP: FORBIDDEN
MEME_SOUND: DISABLED
AUTOMATIC_TRANSITION_WHOOSH: DISABLED

⸻

CHARACTER: CHAR_GARDENER
NAME: Bà Tư
ROLE: Nhân vật chính, người kể chuyện
AGE: 62
GENDER: Nữ
NATIONALITY: Việt Nam
BODY_TYPE: Nhỏ nhắn
HEAD_RATIO: 0.34
FACE_SHAPE: Tròn
HAIR: Tóc bạc búi cao
EYES: Mắt tròn hiền
SKIN_TONE: Ngăm
DEFAULT_EXPRESSION: Hiền hậu
PERSONALITY_PRESENTATION: Chậm rãi, cẩn thận
FACIAL_FEATURES: Nếp nhăn khóe mắt
COSTUME_CIVILIAN:
* Áo bà ba nâu
* Khăn rằn quàng cổ
* Tạp dề có túi
VOICE_ENGINE: VieNeu-TTS
VOICE_ID: GIONG_DOC_MAU_BA_TU
VOICE_SPEED: 1.0
VOICE_TONE: Ấm, chậm rãi
ANIMATION_CAPABILITIES:
* Đi bộ
* Cầm vật dụng
* Biểu cảm khuôn mặt
IDENTITY_LOCK: TRUE

CHARACTER: CHAR_BOY
NAME: Bé Nam
ROLE: Nhân vật phụ
AGE: 9
GENDER: Nam
NATIONALITY: Việt Nam
BODY_TYPE: Nhỏ
HEAD_RATIO: 0.34
FACE_SHAPE: Tròn
HAIR: Tóc ngắn đen
EYES: Mắt to
SKIN_TONE: Sáng
DEFAULT_EXPRESSION: Tò mò
COSTUME:
* Áo thun xanh
* Quần ngắn
VOICE_ENGINE: VieNeu-TTS
VOICE_ID: GIONG_DOC_MAU_BE_NAM
VOICE_SPEED: 1.0
VOICE_TONE: Trong trẻo
IDENTITY_LOCK: TRUE

⸻

LOCATION: LOC_GARDEN
NAME: Khu vườn sau nhà
TYPE: EXTERIOR
YEAR: 2024
TIME_OF_DAY: MORNING
WEATHER: Nắng nhẹ
HISTORICAL_REFERENCE: Không có
DISTINCTIVE_FEATURES:
* Cổng sắt cũ màu xanh rêu
* Luống rau thẳng tắp
* Cây khế lớn giữa vườn
FOREGROUND:
* Chậu hoa gần camera
MIDGROUND:
* Lối đi lát gạch đỏ
BACKGROUND:
* Hàng rào tre và mái nhà
LIGHTING: Ánh sáng buổi sáng dịu
COLOR_PALETTE: Xanh lá, nâu đất, vàng nhạt
AMBIENCE: Tiếng chim và tiếng lá xào xạc
FORBIDDEN:
* Không thay địa điểm khác

LOCATION: LOC_SHED
NAME: Chòi lá cuối vườn
TYPE: EXTERIOR
YEAR: 2024
TIME_OF_DAY: AFTERNOON
WEATHER: Mưa rào
HISTORICAL_REFERENCE: Không có
DISTINCTIVE_FEATURES:
* Mái lá dốc
* Bàn gỗ cũ dưới mái
* Thùng tưới nước bằng kim loại
FOREGROUND:
* Mưa rơi thành dòng từ mái lá
MIDGROUND:
* Bàn gỗ và ghế đẩu
BACKGROUND:
* Vườn cây mờ trong mưa
LIGHTING: Ánh sáng xám của trời mưa
COLOR_PALETTE: Xám xanh, nâu gỗ sẫm
AMBIENCE: Tiếng mưa rơi trên mái lá
FORBIDDEN:
* Không thay địa điểm khác

⸻

PROP: PROP_KEY
TYPE: TOOL
COLOR: Vàng đồng
MATERIAL: Kim loại
INTERACTION: Cầm, tra vào ổ khóa, đánh rơi, nhặt lên
DESCRIPTION: Chiếc chìa khóa cổng bằng đồng
OWNER: CHAR_GARDENER

PROP: PROP_LETTER
TYPE: DOCUMENT
COLOR: Trắng ngà
MATERIAL: Giấy
INTERACTION: Cầm, đưa, nhận, mở, đọc
DESCRIPTION: Bức thư tay gấp ba
OWNER: CHAR_BOY

⸻

SCENE: SC01
TITLE: Buổi sáng trong vườn
LOCATION: LOC_GARDEN
CHARACTERS: CHAR_GARDENER
MOOD: Bình yên
STORY_PURPOSE: Giới thiệu bà Tư và chiếc chìa khóa
AMBIENCE: Tiếng chim buổi sáng
BGM: Nhạc nền nhẹ
TRANSITION: CUT

SHOT: SC01_SH01
CAMERA: Medium shot, bà Tư ở trung tâm khung hình
CAMERA_MOVEMENT: STATIC
ACTION:
* Bà Tư bước đi trên lối gạch, tay đung đưa tự nhiên.
* Bà Tư hơi cúi đầu suy nghĩ.
NARRATION:
SPEAKER: CHAR_GARDENER
LINE_ID: TESTE_001
TEXT: “Tôi đã giữ chiếc chìa khóa này hơn ba mươi năm rồi, từ ngày khu vườn này mới chỉ là một mảnh đất trống với vài luống rau non và một cây khế con.”
LIP_SYNC: REQUIRED
SFX: NONE

SHOT: SC01_SH02
CAMERA: Close-up, bàn tay bà Tư
CAMERA_MOVEMENT: STATIC
ACTION:
* Bà Tư dừng lại, lấy chìa khóa từ túi tạp dề.
* Bà Tư mở cổng sắt.
NARRATION:
SPEAKER: CHAR_GARDENER
LINE_ID: TESTE_002
TEXT: “Sáng nào tôi cũng mở cổng đúng giờ này.”
LIP_SYNC: REQUIRED
SFX:
* ID: SFX_001
* EVENT: Tiếng chìa khóa tra vào ổ
* TRIGGER: TESTE_002
* TYPE: Foley
* INTENSITY: LOW
* DURATION: 0.4s
* DURATION_MODE: FIXED

SHOT: SC01_SH03
CAMERA: Medium shot, bà Tư và cổng sắt
CAMERA_MOVEMENT: STATIC
ACTION:
* Bà Tư đánh rơi chìa khóa xuống đất.
* Bà Tư cúi xuống nhặt chìa khóa lên.
NARRATION:
SPEAKER: CHAR_GARDENER
LINE_ID: TESTE_003
TEXT: “Tay tôi run, chìa khóa rơi mất rồi.”
LIP_SYNC: REQUIRED
SFX: NONE

⸻

SCENE: SC02
TITLE: Cơn mưa và bức thư
LOCATION: LOC_SHED
CHARACTERS: CHAR_GARDENER, CHAR_BOY
MOOD: Ấm áp
STORY_PURPOSE: Bé Nam đưa thư cho bà Tư dưới cơn mưa
AMBIENCE: Tiếng mưa rơi trên mái lá
BGM: NONE
TRANSITION: CUT

SHOT: SC02_SH01
CAMERA: Medium shot, chòi lá trong mưa
CAMERA_MOVEMENT: STATIC
ACTION:
* Bé Nam chạy tới chòi lá, tay cầm bức thư.
* Bé Nam đưa bức thư cho bà Tư.
* Bà Tư nhận bức thư bằng tay trái.
* Bà Tư cúi người tránh giọt nước rơi từ mái lá.
DIALOGUE:
SPEAKER: CHAR_BOY
LINE_ID: TESTE_004
TEXT: “Bà ơi, có thư cho bà này!”
LIP_SYNC: REQUIRED
SFX: NONE

SHOT: SC02_SH02
CAMERA: Close-up, bà Tư mở thư
CAMERA_MOVEMENT: STATIC
ACTION:
* Bà Tư mở bức thư ra.
* Bà Tư đọc thư, mỉm cười.
NARRATION:
SPEAKER: CHAR_GARDENER
LINE_ID: TESTE_005
TEXT: “Thì ra là thư của con gái tôi gửi từ xa về.”
LIP_SYNC: REQUIRED
SFX: NONE

⸻

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
EXPECTED_SCENES: 2
EXPECTED_SHOTS: 5
EXPECTED_SPOKEN_LINES: 5
EXPECTED_NARRATION_LINES: 4
EXPECTED_DIALOGUE_LINES: 1
EXPECTED_EXTERNAL_NARRATOR_LINES: 0
EXPECTED_EXPLICIT_SFX_EVENTS: 1
SCRIPT_INTEGRITY_CHECK: REQUIRED
CHARACTER_IDENTITY_CHECK: REQUIRED
