STUDIO SCRIPT V1
# Fixture for the semantic role-resolution tests (integration sprint
# section 5). NOT a Mai-supplied story: new characters, locations
# and props, written to exercise giver/recipient/target/observer
# resolution through the real pipeline. No per-script code may
# depend on this fixture's content.

PROJECT
PROJECT_ID: TESTR_UNSEEN_ROLE_RESOLUTION
TITLE: Buổi chiều ở xưởng đèn
EPISODE: 01
GENRE: Đời thường
LANGUAGE: vi-VN
STORYTELLING_MODE: FIRST_PERSON_ROLEPLAY
PRIMARY_CHARACTER: CHAR_LAN
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

CHARACTER: CHAR_LAN
NAME: Bà Lan
ROLE: Nhân vật chính, người kể chuyện
AGE: 60
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
VOICE_ENGINE: VieNeu-TTS
VOICE_ID: GIONG_DOC_MAU_BA_LAN
VOICE_SPEED: 1.0
VOICE_TONE: Ấm, chậm rãi
ANIMATION_CAPABILITIES:
* Đi bộ
* Cầm vật dụng
* Biểu cảm khuôn mặt
IDENTITY_LOCK: TRUE

CHARACTER: CHAR_TU
NAME: Chú Tư
ROLE: Nhân vật phụ
AGE: 45
GENDER: Nam
NATIONALITY: Việt Nam
BODY_TYPE: Trung bình
HEAD_RATIO: 0.34
FACE_SHAPE: Tròn
HAIR: Tóc ngắn đen
EYES: Mắt tròn
SKIN_TONE: Ngăm
DEFAULT_EXPRESSION: Vui vẻ
COSTUME:
* Áo sơ mi xanh
* Quần dài
VOICE_ENGINE: VieNeu-TTS
VOICE_ID: GIONG_DOC_MAU_CHU_TU
VOICE_SPEED: 1.0
VOICE_TONE: Trầm, vui vẻ
IDENTITY_LOCK: TRUE

CHARACTER: CHAR_DAO
NAME: Cô Đào
ROLE: Nhân vật phụ
AGE: 38
GENDER: Nữ
NATIONALITY: Việt Nam
BODY_TYPE: Nhỏ nhắn
HEAD_RATIO: 0.34
FACE_SHAPE: Tròn
HAIR: Tóc dài đen
EYES: Mắt to
SKIN_TONE: Sáng
DEFAULT_EXPRESSION: Dịu dàng
COSTUME:
* Áo dài tím
VOICE_ENGINE: VieNeu-TTS
VOICE_ID: GIONG_DOC_MAU_CO_DAO
VOICE_SPEED: 1.0
VOICE_TONE: Nhẹ nhàng
IDENTITY_LOCK: TRUE

CHARACTER: CHAR_HUNG
NAME: Anh Hùng
ROLE: Nhân vật phụ
AGE: 30
GENDER: Nam
NATIONALITY: Việt Nam
BODY_TYPE: Cao lớn
HEAD_RATIO: 0.34
FACE_SHAPE: Tròn
HAIR: Tóc ngắn đen
EYES: Mắt to
SKIN_TONE: Sáng
DEFAULT_EXPRESSION: Nhiệt tình
COSTUME:
* Áo thun đỏ
* Quần dài
VOICE_ENGINE: VieNeu-TTS
VOICE_ID: GIONG_DOC_MAU_ANH_HUNG
VOICE_SPEED: 1.0
VOICE_TONE: Khỏe khoắn
IDENTITY_LOCK: TRUE

CHARACTER: CHAR_NA
NAME: Bé Na
ROLE: Nhân vật phụ
AGE: 8
GENDER: Nữ
NATIONALITY: Việt Nam
BODY_TYPE: Nhỏ
HEAD_RATIO: 0.34
FACE_SHAPE: Tròn
HAIR: Tóc ngắn đen
EYES: Mắt to
SKIN_TONE: Sáng
DEFAULT_EXPRESSION: Tò mò
COSTUME:
* Áo thun vàng
* Quần ngắn
VOICE_ENGINE: VieNeu-TTS
VOICE_ID: GIONG_DOC_MAU_BE_NA
VOICE_SPEED: 1.0
VOICE_TONE: Trong trẻo
IDENTITY_LOCK: TRUE

CHARACTER: CHAR_LAMPSMITH
NAME: Lampsmiths
ROLE: Thợ đèn lồng
AGE: 50
GENDER: Nam
NATIONALITY: Việt Nam
BODY_TYPE: Trung bình
HEAD_RATIO: 0.34
FACE_SHAPE: Tròn
HAIR: Tóc hoa râm
EYES: Mắt tròn
SKIN_TONE: Ngăm
DEFAULT_EXPRESSION: Tập trung
COSTUME:
* Áo lao động xám
* Tạp dề da
VOICE: NONE
IDENTITY_LOCK: TRUE

⸻

LOCATION: LOC_YARD
NAME: Sân nhà buổi chiều
TYPE: EXTERIOR
YEAR: 2024
TIME_OF_DAY: AFTERNOON
WEATHER: Nắng nhẹ
HISTORICAL_REFERENCE: Không có
DISTINCTIVE_FEATURES:
* Giếng nước cũ
* Giàn hoa giấy đỏ
FOREGROUND:
* Chậu hoa gần camera
MIDGROUND:
* Sân gạch đỏ
BACKGROUND:
* Hàng rào và mái nhà
LIGHTING: Ánh sáng buổi chiều ấm
COLOR_PALETTE: Đỏ gạch, xanh lá, vàng nhạt
AMBIENCE: Tiếng chim buổi chiều
FORBIDDEN:
* Không thay địa điểm khác

LOCATION: LOC_WORKSHOP
NAME: Xưởng đèn lồng
TYPE: INTERIOR
YEAR: 2024
TIME_OF_DAY: AFTERNOON
WEATHER: Nắng nhẹ
HISTORICAL_REFERENCE: Không có
DISTINCTIVE_FEATURES:
* Bàn thợ dài
* Đèn lồng treo khắp trần
FOREGROUND:
* Dụng cụ trên bàn thợ
MIDGROUND:
* Bàn thợ và ghế đẩu
BACKGROUND:
* Kệ gỗ đựng đèn lồng
LIGHTING: Ánh sáng ấm trong xưởng
COLOR_PALETTE: Nâu gỗ, đỏ đèn, vàng ấm
AMBIENCE: Tiếng dụng cụ khẽ chạm nhau
FORBIDDEN:
* Không thay địa điểm khác

⸻

PROP: PROP_KEY
TYPE: TOOL
COLOR: Vàng đồng
MATERIAL: Kim loại
INTERACTION: Cầm, đưa, nhận, tra vào ổ khóa
DESCRIPTION: Chiếc chìa khóa cổng bằng đồng
OWNER: CHAR_LAN

PROP: PROP_LETTER
TYPE: DOCUMENT
COLOR: Trắng ngà
MATERIAL: Giấy
INTERACTION: Cầm, đưa, nhận, mở
DESCRIPTION: Bức thư tay gấp ba
OWNER: CHAR_HUNG

PROP: PROP_SWORD
TYPE: TOOL
COLOR: Bạc
MATERIAL: Kim loại
INTERACTION: Cầm, đưa, nhận
DESCRIPTION: Thanh kiếm tập bằng kim loại
OWNER: CHAR_LAMPSMITH

PROP: PROP_CUP
TYPE: CONTAINER
COLOR: Trắng
MATERIAL: Sứ
INTERACTION: Cầm, đưa, nhận, uống
DESCRIPTION: Chiếc cốc sứ trắng
OWNER: CHAR_TU

PROP: PROP_BAG
TYPE: CONTAINER
COLOR: Nâu
MATERIAL: Vải
INTERACTION: Mang, xách, cầm
DESCRIPTION: Chiếc túi vải nâu
OWNER: CHAR_DAO

⸻

SCENE: SC01
TITLE: Chìa khóa và thanh kiếm
LOCATION: LOC_YARD
CHARACTERS: CHAR_LAN, CHAR_TU, CHAR_LAMPSMITH, CHAR_HUNG, CHAR_DAO
MOOD: Bình yên
STORY_PURPOSE: Trao chìa khóa, nhận kiếm, thấy người khác trao cốc
AMBIENCE: Tiếng chim buổi chiều
BGM: NONE
TRANSITION: CUT

SHOT: SC01_SH01
CAMERA: Medium shot, bà Lan và chú Tư ở sân
CAMERA_MOVEMENT: STATIC
ACTION:
* Bà Lan đưa chiếc chìa khóa cho Chú Tư.
* Chú Tư nhận bằng tay trái.
NARRATION:
SPEAKER: CHAR_LAN
LINE_ID: TESTR_001
TEXT: “Tôi đưa chìa khóa cho chú Tư giữ hộ.”
LIP_SYNC: REQUIRED
SFX: NONE

SHOT: SC01_SH02
CAMERA: Medium shot, thợ đèn và anh Hùng
CAMERA_MOVEMENT: STATIC
ACTION:
* Một Lampsmith đưa thanh kiếm cho Anh Hùng.
* Anh Hùng nhận bằng tay phải.
NARRATION:
SPEAKER: CHAR_LAN
LINE_ID: TESTR_002
TEXT: “Người thợ trao thanh kiếm cho anh Hùng.”
LIP_SYNC: REQUIRED
SFX: NONE

SHOT: SC01_SH03
CAMERA: Medium shot, chú Tư và cô Đào
CAMERA_MOVEMENT: STATIC
ACTION:
* Tôi thấy Chú Tư đưa chiếc cốc cho Cô Đào.
* Cô Đào nhận bằng tay phải.
NARRATION:
SPEAKER: CHAR_LAN
LINE_ID: TESTR_003
TEXT: “Tôi thấy chú Tư đưa cốc cho cô Đào.”
LIP_SYNC: REQUIRED
SFX: NONE

⸻

SCENE: SC02
TITLE: Bức thư trong xưởng đèn
LOCATION: LOC_WORKSHOP
CHARACTERS: CHAR_HUNG, CHAR_TU, CHAR_DAO, CHAR_LAN, CHAR_NA
MOOD: Ấm áp
STORY_PURPOSE: Trao thư, nhìn nhau, tặng hoa
AMBIENCE: Tiếng dụng cụ khẽ chạm nhau
BGM: NONE
TRANSITION: CUT

SHOT: SC02_SH01
CAMERA: Medium shot, anh Hùng và chú Tư
CAMERA_MOVEMENT: STATIC
ACTION:
* Anh Hùng bước tới chỗ Chú Tư.
* Đưa chiếc thư cho Chú Tư.
* Chú Tư nhìn Anh Hùng.
DIALOGUE:
SPEAKER: CHAR_HUNG
LINE_ID: TESTR_004
TEXT: “Chú Tư ơi, có thư cho chú này!”
LIP_SYNC: REQUIRED
SFX: NONE

SHOT: SC02_SH02
CAMERA: Medium shot, chú Tư và cô Đào
CAMERA_MOVEMENT: STATIC
ACTION:
* Chú Tư nhìn tôi.
* Cô Đào mang chiếc túi.
DIALOGUE:
SPEAKER: CHAR_TU
LINE_ID: TESTR_005
TEXT: “Bà Lan ơi, bà thấy bức thư chưa?”
LIP_SYNC: REQUIRED
SFX: NONE

SHOT: SC02_SH03
CAMERA: Medium shot, bà Lan và bé Na
CAMERA_MOVEMENT: STATIC
ACTION:
* Bà Lan tặng hoa cho Bé Na.
* Món quà tặng cho Bé Na nằm trên bàn.
NARRATION:
SPEAKER: CHAR_LAN
LINE_ID: TESTR_006
TEXT: “Tôi tặng hoa cho bé Na.”
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
EXPECTED_SHOTS: 6
EXPECTED_SPOKEN_LINES: 6
EXPECTED_NARRATION_LINES: 4
EXPECTED_DIALOGUE_LINES: 2
EXPECTED_EXTERNAL_NARRATOR_LINES: 0
EXPECTED_EXPLICIT_SFX_EVENTS: 0
SCRIPT_INTEGRITY_CHECK: REQUIRED
CHARACTER_IDENTITY_CHECK: REQUIRED
