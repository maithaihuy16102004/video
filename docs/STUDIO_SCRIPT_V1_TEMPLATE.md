# STUDIO SCRIPT V1
# =====================================================================
# MẪU KỊCH BẢN STUDIO SCRIPT V1 — sao chép toàn bộ tệp này để bắt đầu.
# - Thay mọi giá trị mẫu bằng nội dung thật của dự án. Tên trong mẫu này
#   (NHÂN VẬT A, NHÂN VẬT B, ĐỊA ĐIỂM X, VẬT DỤNG X) là tên giả rõ ràng.
# - Giữ nguyên các khóa (PROJECT, CHARACTER, SCENE, ...). Khóa không phân
#   biệt hoa/thường; giá trị giữ nguyên tiếng Việt, không viết lại.
# - Dòng bắt đầu bằng # là ghi chú, không ảnh hưởng kịch bản. Dòng trống
#   cũng được bỏ qua. Ngoài ghi chú, tệp này chỉ chứa cú pháp hợp lệ.
# - Lời dẫn và lời thoại được giữ nguyên từng chữ và đọc thành tiếng.
#   Các dòng khác (VISUAL, ACTION, CAMERA, VOICE_NOTE, ...) không bị đọc.
# - HEAD_RATIO chỉ nhận 0.33-0.35, mặc định 0.34. Không dùng 0.42.
# - Đặc tả đầy đủ: docs/STUDIO_SCRIPT_V1_SPEC.md
# =====================================================================

# --- PHẦN ĐẦU (HEADER): đặt trước khối đầu tiên. ---
# PROJECT: tên dự án (tùy chọn).
PROJECT: Tên dự án mẫu
# LANGUAGE: ngôn ngữ, mặc định vi-VN.
LANGUAGE: vi-VN
# GENRE: thể loại (tùy chọn).
GENRE: Thể loại mẫu
# STYLE: tên cũ của VISUAL_STYLE. Nếu cả hai khác nhau, VISUAL_STYLE thắng.
STYLE: Phong cách hình ảnh mẫu
# VISUAL_STYLE: phong cách hình ảnh (tùy chọn).
VISUAL_STYLE: Phong cách hình ảnh mẫu
# ASPECT_RATIO: chỉ 16:9 hoặc 9:16; mặc định 16:9.
ASPECT_RATIO: 16:9
# TARGET_DURATION: AUTO hoặc số giây; mặc định AUTO.
TARGET_DURATION: AUTO
# TONE: giọng điệu chung (tùy chọn).
TONE: Giọng điệu mẫu
# MEME_POLICY: CONTEXTUAL, NONE hoặc ALWAYS; mặc định CONTEXTUAL.
MEME_POLICY: CONTEXTUAL
# MEME_MAX_PER_MINUTE: số nguyên từ 0 trở lên; mặc định 2.
MEME_MAX_PER_MINUTE: 2

# --- NHÂN VẬT: một khối CHARACTER cho mỗi nhân vật. Tên không trùng nhau. ---
CHARACTER: NHÂN VẬT A
# ROLE: vai trò của nhân vật trong câu chuyện.
ROLE: Vai trò mẫu
# APPEARANCE: mô tả ngoại hình riêng, giúp nhân vật khác biệt.
APPEARANCE: Ngoại hình mẫu riêng biệt
# TRAITS: các nét riêng, phân cách bằng dấu ; .
TRAITS: Nét riêng mẫu một; nét riêng mẫu hai
# COSTUME: trang phục mặc định của nhân vật.
COSTUME: Trang phục mặc định mẫu
# COSTUME_CHANGE: lặp lại được; đổi trang phục theo cảnh, không đổi danh tính.
COSTUME_CHANGE: SCENE 1: Trang phục mẫu cho cảnh 1
# VOICE: AUTO để pipeline tự chọn, hoặc ghi mã giọng đọc cụ thể.
VOICE: AUTO
# VOICE_STYLE: phong cách giọng đọc.
VOICE_STYLE: Phong cách giọng mẫu
# HEAD_RATIO: tỉ lệ đầu, chỉ 0.33-0.35; mặc định 0.34. Không dùng 0.42.
HEAD_RATIO: 0.34
# IDENTITY_ID: mã danh tính ổn định; mặc định bằng tên nhân vật.
IDENTITY_ID: NHAN_VAT_A

CHARACTER: NHÂN VẬT B
# ROLE: vai trò của nhân vật trong câu chuyện.
ROLE: Vai trò mẫu khác
# APPEARANCE: mô tả ngoại hình riêng, giúp nhân vật khác biệt.
APPEARANCE: Ngoại hình mẫu riêng biệt khác
# TRAITS: các nét riêng, phân cách bằng dấu ; .
TRAITS: Nét riêng mẫu ba; nét riêng mẫu bốn
# COSTUME: trang phục mặc định của nhân vật.
COSTUME: Trang phục mặc định mẫu khác
# COSTUME_CHANGE: lặp lại được; đổi trang phục theo cảnh, không đổi danh tính.
COSTUME_CHANGE: SCENE 1: Trang phục mẫu khác cho cảnh 1
# VOICE: AUTO để pipeline tự chọn, hoặc ghi mã giọng đọc cụ thể.
VOICE: AUTO
# VOICE_STYLE: phong cách giọng đọc.
VOICE_STYLE: Phong cách giọng mẫu khác
# HEAD_RATIO: tỉ lệ đầu, chỉ 0.33-0.35; mặc định 0.34. Không dùng 0.42.
HEAD_RATIO: 0.34
# IDENTITY_ID: mã danh tính ổn định; mặc định bằng tên nhân vật.
IDENTITY_ID: NHAN_VAT_B

# --- ĐỊA ĐIỂM: một khối LOCATION cho mỗi bối cảnh. Mã không trùng nhau. ---
LOCATION: ĐỊA ĐIỂM X
# NAME: tên hiển thị của địa điểm.
NAME: Tên địa điểm mẫu
# PERIOD: thời kỳ lịch sử hoặc niên đại.
PERIOD: Thời kỳ mẫu
# GEOGRAPHY: mô tả địa lý.
GEOGRAPHY: Địa lý mẫu
# ARCHITECTURE: mô tả kiến trúc.
ARCHITECTURE: Kiến trúc mẫu
# FEATURES: các đặc điểm riêng, phân cách bằng dấu ; . Phải nhìn thấy được.
FEATURES: Đặc điểm riêng mẫu một; đặc điểm riêng mẫu hai
# FOREGROUND: mô tả tiền cảnh.
FOREGROUND: Tiền cảnh mẫu
# MIDGROUND: mô tả trung cảnh.
MIDGROUND: Trung cảnh mẫu
# BACKGROUND: mô tả hậu cảnh.
BACKGROUND: Hậu cảnh mẫu
# LIGHTING: mô tả ánh sáng.
LIGHTING: Ánh sáng mẫu
# WEATHER: mô tả thời tiết.
WEATHER: Thời tiết mẫu
# PALETTE: các màu chủ đạo, phân cách bằng dấu ; .
PALETTE: Màu mẫu một; màu mẫu hai
# FORBIDDEN: các yếu tố cấm xuất hiện, phân cách bằng dấu ; .
FORBIDDEN: Yếu tố cấm mẫu một; yếu tố cấm mẫu hai

# --- ĐẠO CỤ: một khối PROP cho mỗi vật dụng. Tên không trùng nhau. ---
PROP: VẬT DỤNG X
# DESCRIPTION: mô tả vật dụng.
DESCRIPTION: Mô tả vật dụng mẫu
# OWNER: tên CHARACTER sở hữu, hoặc NONE nếu không thuộc ai.
OWNER: NHÂN VẬT A
# SCENES: danh sách số cảnh phân cách bằng dấu phẩy, hoặc ALL.
SCENES: 1
# INTERACTION: các động từ tương tác, phân cách bằng dấu ; .
INTERACTION: Cầm; đưa; đặt xuống

# --- ÂM THANH TOÀN CỤC: mức âm (dB) cho 6 bus. Tối đa một khối. ---
GLOBAL_AUDIO:
# NARRATION_GAIN_DB: mức bus lời dẫn; mặc định 0.
NARRATION_GAIN_DB: 0
# DIALOGUE_GAIN_DB: mức bus thoại; mặc định 0.
DIALOGUE_GAIN_DB: 0
# AMBIENCE_GAIN_DB: mức bus âm thanh nền; mặc định -18.
AMBIENCE_GAIN_DB: -18
# FOLEY_GAIN_DB: mức bus foley; mặc định -12.
FOLEY_GAIN_DB: -12
# SFX_GAIN_DB: mức bus hiệu ứng; mặc định -6.
SFX_GAIN_DB: -6
# BGM_GAIN_DB: mức bus nhạc nền; mặc định -18.
BGM_GAIN_DB: -18
# BGM_DUCKING_DB: nhạc nền giảm thêm bấy nhiêu dB khi có lời nói; mặc định -6.
BGM_DUCKING_DB: -6
# MASTER_LIMIT_DB: trần âm lượng tổng; mặc định -1.0.
MASTER_LIMIT_DB: -1.0

# --- RÀNG BUỘC CẤM TOÀN CỤC: mỗi dòng một ràng buộc. Tối đa một khối. ---
GLOBAL_NEGATIVE_CONSTRAINTS:
# Dạng "- ..." hoặc "NO: ...".
- Điều cấm mẫu một
NO: Điều cấm mẫu hai

# --- CẢNH: số cảnh không trùng nhau; thứ tự sản xuất theo thứ tự văn bản. ---
SCENE 1: Tiêu đề cảnh mẫu
# LOCATION: ghi đúng mã LOCATION đã khai báo, hoặc mô tả tự do (dạng cũ).
LOCATION: ĐỊA ĐIỂM X
# TIME_OF_DAY: thời điểm trong ngày.
TIME_OF_DAY: Thời điểm mẫu
# MOOD: tâm trạng của cảnh.
MOOD: Tâm trạng mẫu
# DURATION: AUTO hoặc số giây; mặc định AUTO.
DURATION: AUTO
# VISUAL: mô tả hình ảnh của cảnh.
VISUAL: Mô tả hình ảnh mẫu
# TRANSITION: CUT, DISSOLVE, FADE, FADE_TO_BLACK, MATCH_CUT hoặc WIPE; mặc định CUT.
# Có thể đặt ở đây hoặc ở cuối cảnh; hai vị trí cùng một ý nghĩa.
TRANSITION: CUT
# CAMERA: mô tả góc máy mặc định của cảnh (cho nội dung ngoài SHOT).
CAMERA: Mô tả góc máy mẫu
# CAMERA_MOVEMENT: STATIC, PAN_LEFT, PAN_RIGHT, TILT_UP, TILT_DOWN, DOLLY_IN,
# DOLLY_OUT, TRACKING, CRANE_UP, CRANE_DOWN hoặc HANDHELD; mặc định STATIC.
CAMERA_MOVEMENT: STATIC
# ACTION: mô tả hành động, giữ nguyên văn, không bị đọc thành lời.
ACTION: Hành động mẫu trong cảnh.
# EXPRESSION: dạng "EXPRESSION: Nhân vật: biểu cảm" hoặc "EXPRESSION: biểu cảm".
EXPRESSION: NHÂN VẬT A: Biểu cảm mẫu
# VOICE_NOTE: chỉ đạo sản xuất về giọng đọc; KHÔNG được đọc thành lời.
VOICE_NOTE: Chỉ đạo giọng đọc mẫu.
# NARRATION: lời dẫn, người nói là Narrator. Dòng này được gán mã L001 tự động.
NARRATION: Lời dẫn mẫu thứ nhất.
# NARRATION [Lnn]: lời dẫn có mã dòng ghi rõ. Mã dòng là duy nhất toàn văn bản.
NARRATION [L002]: Lời dẫn mẫu thứ hai.
# DIALOGUE: dạng "DIALOGUE: Người nói: lời thoại"; người nói phải là CHARACTER đã khai báo.
DIALOGUE: NHÂN VẬT A: Lời thoại mẫu của nhân vật A.
# Dạng cũ: dòng thoại trần "TÊN NHÂN VẬT: lời thoại".
NHÂN VẬT B: Lời thoại mẫu của nhân vật B.
# SFX: lặp lại được; TRIGGER là mã dòng (ví dụ L001) hoặc mô tả hành động;
# PRIORITY là REQUIRED (mặc định) hoặc OPTIONAL.
SFX: Hiệu ứng âm thanh mẫu | TRIGGER: L001 | PRIORITY: REQUIRED
# SFX: NONE nghĩa là cảnh này không có hiệu ứng nào; ghi nhận rõ ràng, không tự thêm.
# SFX: NONE
# AMBIENCE: MODE là LOOP (mặc định) hoặc ONCE. Tối đa một dòng mỗi cảnh.
AMBIENCE: Âm thanh nền mẫu | MODE: LOOP
# AMBIENCE: NONE nghĩa là cảnh này không có âm thanh nền.
# AMBIENCE: NONE
# BGM: INTENSITY là LOW, MEDIUM (mặc định) hoặc HIGH. MUSIC: là tên cũ của BGM.
BGM: Nhạc nền mẫu | INTENSITY: MEDIUM
# MUSIC: Nhạc nền mẫu | INTENSITY: MEDIUM
# MEME: dạng cũ, chỉ ghi nhận dữ liệu; GAIN_DB không có mặc định; PRIORITY mặc định OPTIONAL.
MEME: Meme mẫu | TRIGGER: L003 | GAIN_DB: -12 | PRIORITY: OPTIONAL
# MEME: NONE nghĩa là cảnh này không có meme.
# MEME: NONE
# VFX: lặp lại được; hoặc nhiều hiệu ứng trên một dòng, phân cách bằng dấu ; .
VFX: Hiệu ứng hình ảnh mẫu | TRIGGER: L003
# SHOT: khối cảnh quay trong SCENE; mã shot duy nhất trong cảnh; TYPE là bắt buộc.
SHOT SH01:
# TYPE: establishing, medium, close_up, extreme_close_up, over_the_shoulder,
# reaction, object_insert, tracking hoặc shot_reverse_shot (dạng UPPER_SNAKE cũng được).
TYPE: establishing
# CAMERA: mô tả góc máy của shot.
CAMERA: Mô tả góc máy mẫu của shot
# CAMERA_MOVEMENT: xem danh sách ở cấp cảnh; mặc định STATIC.
CAMERA_MOVEMENT: DOLLY_IN
# SUBJECT: tên CHARACTER hoặc PROP làm chủ thể của shot.
SUBJECT: NHÂN VẬT A
# DURATION: AUTO hoặc số giây; mặc định AUTO.
DURATION: AUTO
# ACTION: hành động trong shot, giữ nguyên văn.
ACTION: Hành động mẫu trong shot.
# EXPRESSION: biểu cảm trong shot; dạng có hoặc không có tên nhân vật.
EXPRESSION: NHÂN VẬT A: Biểu cảm mẫu trong shot
# VFX: các hiệu ứng của shot, phân cách bằng dấu ; .
VFX: Hiệu ứng mẫu một; hiệu ứng mẫu hai
# Dòng nội dung trong SHOT thuộc về shot này (ví dụ một câu thoại).
DIALOGUE: NHÂN VẬT B: Lời thoại mẫu trong shot.
# END_SCENE: kết thúc cảnh (dạng cũ, không bắt buộc).
END_SCENE

# --- KIỂM ĐỊNH CHẤT LƯỢNG (QA): tối đa một khối. ---
QA:
# MIN_SCORE: điểm tối thiểu 0-10; mặc định 8.0.
MIN_SCORE: 8.0
# REQUIRE_TECHNICAL: true hoặc false; mặc định true.
REQUIRE_TECHNICAL: true
# REQUIRE_CREATIVE_REVIEW: true hoặc false; mặc định true.
REQUIRE_CREATIVE_REVIEW: true
# LANGUAGE_GATE: true hoặc false; mặc định true.
LANGUAGE_GATE: true
# MAX_HARD_FAILS: số nguyên từ 0 trở lên; mặc định 0.
MAX_HARD_FAILS: 0

# --- ĐẦU RA (OUTPUT): tối đa một khối. ---
OUTPUT:
# RESOLUTION: 1920x1080 hoặc 1280x720; mặc định 1920x1080.
RESOLUTION: 1920x1080
# FPS: 24, 25 hoặc 30; mặc định 24.
FPS: 24
# FORMAT: chỉ MP4; mặc định MP4.
FORMAT: MP4
# DRAFT_FOLDER: thư mục chứa bản draft; mặc định "drive:drafts".
DRAFT_FOLDER: drive:drafts
# MASTER: chỉ MANUAL_ONLY. Master không bao giờ tự động.
MASTER: MANUAL_ONLY

# --- THẺ KẾT (END_CARD): tối đa một khối; vắng mặt nghĩa là không có thẻ kết. ---
END_CARD:
# TEXT: nội dung thẻ kết.
TEXT: Nội dung thẻ kết mẫu
# DURATION: số giây; mặc định 3.0. Không nhận AUTO.
DURATION: 3.0
# STYLE: phong cách thẻ kết.
STYLE: Phong cách thẻ kết mẫu

# END_SCRIPT: kết thúc kịch bản (dạng cũ, không bắt buộc).
END_SCRIPT
