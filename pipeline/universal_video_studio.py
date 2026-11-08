"""
Universal AI Video Studio — Xưởng Sản Xuất Video AI Toàn Diện Cho Mọi Chủ Đề
Tự động hóa 100% từ A đến Z:
1. NHẬN BẤT KỲ CHỦ ĐỀ NÀO (Topic / Concept / Idea / Custom Script).
2. TỰ ĐỘNG PHÂN CẢNH ĐIỆN ẢNH (Hook, Setup, Problem, Climax, Resolution).
3. ĐỒ HỌA HOẠT HÌNH RỰC RỠ PHONG CÁCH KURZGESAGT (Không 1 màu, giàu chiều sâu).
4. NHÂN VẬT MASCOT HOẠT HỌA THEO 12 NGUYÊN LÝ DISNEY (Squash & Stretch, Breathing, Tilt).
5. CAMERA PARALLAX 2.5D KEN BURNS & HẠT MÔI TRƯỜNG ĐA DẠNG.
6. HỆ THỐNG SOUND DESIGN EBU R128 (Voice AI + 15+ SFX + BGM Ducking).
7. XUẤT RA VIDEO MASTER 1080x1920 MP4 DỌC (Shorts / Reels / TikTok) + SUBTITLES.

Sử dụng:
    python pipeline/universal_video_studio.py --topic "Trí tuệ nhân tạo AGI"
    python pipeline/universal_video_studio.py --topic "Bí quyết quản lý tài chính cá nhân"
    python pipeline/universal_video_studio.py --topic "Lỗ đen vũ trụ hoạt động thế nào"
    python pipeline/universal_video_studio.py --topic "Tại sao chúng ta ngủ mơ"
"""

import os
import sys
import json
import math
import random
import argparse
import tempfile
import subprocess
import urllib.request
import urllib.parse
import copy
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from production_quality import (
    enrich_scene_plan,
    generate_contact_sheet,
    select_preset,
    write_quality_report,
    inspect_render,
)
from premium_remotion_renderer import render_premium

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
AGENT_ROOT = BASE_DIR.parent
ASSETS_DIR = AGENT_ROOT / "assets"
CHARACTERS_DIR = ASSETS_DIR / "characters"
SFX_DIR = ASSETS_DIR / "sfx"
BGM_DIR = ASSETS_DIR / "bgm"
FACTORY_DIR = AGENT_ROOT / "drafts_factory"

WIDTH = 1080
HEIGHT = 1920
FPS = 30


# ===========================================================================
# 1. KHO KỊCH BẢN THÔNG MINH MẪU (PRESET TOPICS & GENERAL GENERATOR)
# ===========================================================================

UNIVERSAL_PRESETS = {
    "tri_tue_nhan_tao": {
        "title_vi": "Trí tuệ nhân tạo và tương lai loài người",
        "category": "Công nghệ & AI",
        "bgm": "cinematic_epic.mp3",
        "palette": {
            "top": (10, 15, 35),
            "bottom": (5, 8, 20),
            "accent": (0, 240, 255),
            "badge_bg": (0, 60, 100)
        },
        "scenes": [
            {
                "badge": "⚡ CƠN SỐT TOÀN CẦU",
                "headline": "AI ĐANG THAY ĐỔI\nTHẾ GIỚI NHƯ THẾ NÀO?",
                "subtext": "Từ những dòng lệnh thô sơ đến trí tuệ vượt bậc nhân loại...",
                "spoken": "Chỉ trong vài năm ngắn ngủi, trí tuệ nhân tạo đã bùng nổ từ phòng thí nghiệm ra toàn thế giới, làm thay đổi hoàn toàn cách chúng ta sống và làm việc.",
                "theme_color": (0, 240, 255),
                "particle_type": "neon",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}]
            },
            {
                "badge": "🧠 BÊN TRONG BỘ NÃO AI",
                "headline": "MẠNG NƠ-RON NHÂN TẠO:\nHỌC HỎI NHƯ CON NGƯỜI",
                "subtext": "Hàng trăm tỷ tham số kết nối xử lý tri thức toàn cầu...",
                "spoken": "Mô phỏng mạng thần kinh sinh học, các mô hình ngôn ngữ lớn nuốt trọn tri thức nhân loại để sáng tạo thơ ca, lập trình và giải mã protein phức tạp.",
                "theme_color": (160, 80, 255),
                "particle_type": "neon",
                "char_side": "left",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "boom.wav"}, {"time": 1.5, "sfx": "chime.wav"}]
            },
            {
                "badge": "🤖 TỰ ĐỘNG HÓA KỶ LỤC",
                "headline": "ROBOT CÔNG NGHỆ CAO\n& LAO ĐỘNG TƯƠNG LAI",
                "subtext": "Giải phóng sức lao động hay làn sóng chuyển dịch việc làm?",
                "spoken": "Từ nhà máy tự động đến các cánh tay phẫu thuật chính xác tuyệt đối, robot đang dần đảm nhận những công việc nặng nhọc và nguy hiểm nhất.",
                "theme_color": (70, 190, 255),
                "particle_type": "steam",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}, {"time": 1.2, "sfx": "chime.wav"}]
            },
            {
                "badge": "⚠️ THÁCH THỨC ĐẠO ĐỨC",
                "headline": "RANH GIỚI KIỂM SOÁT\n& TRÍ TUỆ TỔNG QUÁT AGI",
                "subtext": "Liệu trí tuệ nhân tạo có vượt khỏi tầm kiểm soát của con người?",
                "spoken": "Khi chạm ngưỡng siêu trí tuệ, việc kiểm soát và căn chỉnh giá trị của AI để phục vụ nhân loại chính là bài toán sinh tử lớn nhất kỷ nguyên này.",
                "theme_color": (255, 90, 60),
                "particle_type": "embers",
                "char_side": "left",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "boom.wav"}, {"time": 1.5, "sfx": "pop.wav"}]
            },
            {
                "badge": "🚀 KỶ NGUYÊN MỚI",
                "headline": "KẾT HỢP CON NGƯỜI & AI:\nCHINH PHỤC VŨ TRỤ",
                "subtext": "Sức mạnh mới giúp giải mã các bí ẩn vĩ đại của tự nhiên!",
                "spoken": "Tương lai không phải là cuộc chiến giữa người và máy, mà là sự cộng sinh để mở rộng tầm vóc của văn minh nhân loại vào vũ trụ bao la.",
                "theme_color": (0, 255, 180),
                "particle_type": "neon",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}, {"time": 2.0, "sfx": "chime.wav"}, {"time": 2.8, "sfx": "boom.wav"}]
            }
        ]
    },

    "tai_chinh_ca_nhan": {
        "title_vi": "Bí quyết làm chủ tài chính cá nhân",
        "category": "Tài chính & Đầu tư",
        "bgm": "cinematic_epic.mp3",
        "palette": {
            "top": (15, 30, 20),
            "bottom": (5, 15, 10),
            "accent": (255, 215, 60),
            "badge_bg": (20, 80, 40)
        },
        "scenes": [
            {
                "badge": "💰 NGHỆ THUẬT TIỀN BẠC",
                "headline": "TẠI SAO CÀNG KIẾM NHIỀU\nLẠI CÀNG THIẾU TIỀN?",
                "subtext": "Bẫy lạm phát lối sống và vòng xoáy tài chính vô tận...",
                "spoken": "Rất nhiều người kiếm được thu nhập tốt nhưng vẫn luôn cạn kiệt tiền cuối tháng. Nguyên nhân không nằm ở số tiền bạn kiếm, mà ở cách bạn quản lý nó.",
                "theme_color": (255, 215, 60),
                "particle_type": "pollen",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}]
            },
            {
                "badge": "📊 NGUYÊN TẮC VÀNG",
                "headline": "QUY TẮC 50 - 30 - 20:\nCHIA TIỀN TỰ ĐỘNG",
                "subtext": "50% Thiết yếu - 30% Sở thích cá nhân - 20% Tích lũy đầu tư",
                "spoken": "Hãy chia thu nhập ngay khi nhận lương: năm mươi phần trăm cho nhu cầu thiết yếu, ba mươi phần trăm cho sở thích, và tối thiểu hai mươi phần trăm để tích lũy.",
                "theme_color": (80, 220, 140),
                "particle_type": "pollen",
                "char_side": "left",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}, {"time": 1.5, "sfx": "chime.wav"}]
            },
            {
                "badge": "🛡️ TẤM KHIÊN BẢO VỆ",
                "headline": "QUỸ DỰ PHÒNG KHẨN CẤP:\nAN TÂM TRƯỚC SÓNG GIÓ",
                "subtext": "Duy trì 3 đến 6 tháng chi phí sinh hoạt tối thiểu...",
                "spoken": "Trước khi nghĩ đến làm giàu, hãy xây dựng một quỹ khẩn cấp từ ba đến sáu tháng chi tiêu. Đây là tấm khiên giúp bạn không bao giờ phải rơi vào cảnh nợ nần.",
                "theme_color": (70, 180, 255),
                "particle_type": "steam",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "boom.wav"}, {"time": 1.2, "sfx": "pop.wav"}]
            },
            {
                "badge": "📈 KỲ QUAN THỨ 8",
                "headline": "SỨC MẠNH LÃI KÉP:\nTIỀN ĐẺ RA TIỀN",
                "subtext": "Thời gian và sự kiên trì là đòn bẩy tài chính vĩ đại nhất!",
                "spoken": "Albert Einstein từng gọi lãi kép là kỳ quan thứ tám của thế giới. Đầu tư đều đặn từ sớm sẽ biến những khoản tiền nhỏ thành gia sản khổng lồ theo năm tháng.",
                "theme_color": (255, 180, 50),
                "particle_type": "pollen",
                "char_side": "left",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}, {"time": 1.5, "sfx": "chime.wav"}]
            },
            {
                "badge": "🏆 TỰ DO TÀI CHÍNH",
                "headline": "LÀM CHỦ ĐỒNG TIỀN:\nSỐNG CUỘC ĐỜI THEO Ý BẠN",
                "subtext": "Bắt đầu hành động ngay hôm nay để gặt hái tương lai độc lập!",
                "spoken": "Tự do tài chính không phải là để lười biếng, mà là để bạn có quyền lựa chọn làm những việc mình yêu thích và sống một cuộc đời trọn vẹn nhất.",
                "theme_color": (0, 240, 255),
                "particle_type": "stars",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}, {"time": 2.0, "sfx": "chime.wav"}, {"time": 2.8, "sfx": "boom.wav"}]
            }
        ]
    },

    "vu_tru_lo_den": {
        "title_vi": "Bí ẩn hố đen và vũ trụ sâu thẳm",
        "category": "Thiên văn & Vũ trụ",
        "bgm": "cinematic_epic.mp3",
        "palette": {
            "top": (25, 10, 40),
            "bottom": (5, 5, 15),
            "accent": (200, 100, 255),
            "badge_bg": (60, 20, 90)
        },
        "scenes": [
            {
                "badge": "🌌 BÍ ẨN VĨ ĐẠI",
                "headline": "HỐ ĐEN VŨ TRỤ:\nQUÁI VẬT THÔI MIÊN KHÔNG GIAN",
                "subtext": "Nơi lực hấp dẫn mạnh đến mức ánh sáng cũng không thể thoát ra...",
                "spoken": "Giữa lòng vũ trụ bao la tồn tại những quái vật bí ẩn mang tên hố đen, nơi lực hấp dẫn khủng khiếp đến mức nuốt chửng cả không thời gian và ánh sáng.",
                "theme_color": (200, 100, 255),
                "particle_type": "stars",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}]
            },
            {
                "badge": "💥 CÁI CHẾT CỦA CÁC NGÔI SAO",
                "headline": "SỰ SỤP ĐỔ SIÊU TÂN TINH:\nSINH RA TỪ HỦY DIỆT",
                "subtext": "Khi một ngôi sao khổng lồ cạn kiệt nhiên liệu hạt nhân...",
                "spoken": "Khi một ngôi sao có khối lượng gấp hàng chục lần Mặt Trời đốt cạn nhiên liệu, nó nổ tung thành siêu tân tinh và sụp đổ thành một điểm kỳ dị vô hạn.",
                "theme_color": (255, 90, 50),
                "particle_type": "embers",
                "char_side": "left",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "boom.wav"}, {"time": 1.5, "sfx": "chime.wav"}]
            },
            {
                "badge": "🌀 CHÂN TRỜI SỰ KIỆN",
                "headline": "RANH GIỚI MỘT ĐI KHÔNG TRỞ LẠI:\nEVENT HORIZON",
                "subtext": "Thời gian ngưng đọng và thực tại bị kéo giãn vô cực...",
                "spoken": "Chân trời sự kiện là ranh giới định mệnh. Bất kỳ vật chất nào vượt qua mốc này sẽ mãi mãi biến mất khỏi vũ trụ có thể quan sát của chúng ta.",
                "theme_color": (0, 240, 255),
                "particle_type": "neon",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}, {"time": 1.2, "sfx": "boom.wav"}]
            },
            {
                "badge": "⏳ BẺ CONG THỜI GIAN",
                "headline": "THỜI GIAN CHẬM LẠI:\nNGHỊCH LÝ THUYẾT TƯƠNG ĐỐI",
                "subtext": "Một phút gần hố đen bằng cả ngàn năm ngoài Trái Đất!",
                "spoken": "Thuyết tương đối của Einstein đã chứng minh: Càng đến gần hố đen, thời gian càng trôi chậm lại. Bạn có thể nhìn thấy tương lai hàng tỷ năm trôi qua trong chớp mắt.",
                "theme_color": (255, 215, 60),
                "particle_type": "stars",
                "char_side": "left",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}, {"time": 1.5, "sfx": "chime.wav"}]
            },
            {
                "badge": "🔭 CHÌA KHÓA TỰ NHIÊN",
                "headline": "GIẢI MÃ NGUỒN GỐC VŨ TRỤ:\nCÁNH CỔNG VÀO VÔ TẬN",
                "subtext": "Nơi cất giữ chìa khóa dung hợp lượng tử và hấp dẫn!",
                "spoken": "Hố đen không chỉ là điểm kết thúc, mà chính là chìa khóa mở ra bí mật về cách vũ trụ sinh ra và giới hạn tột cùng của tri thức loài người.",
                "theme_color": (180, 100, 255),
                "particle_type": "neon",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}, {"time": 2.0, "sfx": "chime.wav"}, {"time": 2.8, "sfx": "boom.wav"}]
            }
        ]
    }
}


def build_dynamic_topic(topic_str: str) -> dict:
    """Tự động phân tích và tạo kịch bản chuyên nghiệp cho BẤT KỲ chủ đề nào."""
    preset_key, preset = select_preset(topic_str, UNIVERSAL_PRESETS)
    if preset is not None:
        preset["preset_key"] = preset_key
        return enrich_scene_plan(preset, topic_str)

    # Nếu là chủ đề hoàn toàn mới, tự động xây dựng kịch bản 5 cảnh chuẩn điện ảnh
    # Không âm thầm render một kịch bản chung chung. Cấu hình này vẫn được trả
    # về để công cụ lập kế hoạch có thể điền nội dung, nhưng bị quality gate
    # chặn trước render nếu người dùng chưa cung cấp scene plan thật.
    generic = {
        "title_vi": topic_str,
        "category": "Khám phá & Tri thức",
        "bgm": "cinematic_epic.mp3",
        "palette": {
            "top": (15, 25, 45),
            "bottom": (5, 10, 25),
            "accent": (255, 215, 0),
            "badge_bg": (20, 50, 90)
        },
        "scenes": [
            {
                "badge": "💡 CÂU HỎI LỚN",
                "headline": f"BÍ MẬT ĐẰNG SAU:\n{topic_str.upper()}",
                "subtext": "Những sự thật đáng kinh ngạc mà ít người từng biết...",
                "spoken": f"Bạn đã bao giờ tự hỏi điều gì thực sự đứng sau {topic_str}? Hãy cùng khám phá một trong những bí ẩn thú vị nhất ngay sau đây.",
                "theme_color": (255, 215, 0),
                "particle_type": "stars",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}]
            },
            {
                "badge": "🔍 BẢN CHẤT VẤN ĐỀ",
                "headline": "NGUỒN CỘI VÀ BẢN CHẤT:\nCÁCH MỌI THỨ VẬN HÀNH",
                "subtext": "Giải mã từ những nguyên lý căn bản sâu xa nhất...",
                "spoken": f"Mọi hiện tượng đều bắt nguồn từ những quy luật tự nhiên và logic chặt chẽ. Hiểu được cơ chế này sẽ giúp bạn nhìn nhận thế giới hoàn toàn khác.",
                "theme_color": (70, 190, 255),
                "particle_type": "pollen",
                "char_side": "left",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "boom.wav"}, {"time": 1.2, "sfx": "pop.wav"}]
            },
            {
                "badge": "⚡ TÁC ĐỘNG MẠNH MẼ",
                "headline": "ẢNH HƯỞNG TRỰC TIẾP:\nĐẾN CUỘC SỐNG CHÚNG TA",
                "subtext": "Từng khoảnh khắc thay đổi cách suy nghĩ và hành động...",
                "spoken": f"Điều đáng kinh ngạc là {topic_str} không hề xa vời, mà tác động từng ngày từng giờ tới nhận thức, công việc và lối sống của mỗi người chúng ta.",
                "theme_color": (255, 120, 50),
                "particle_type": "embers",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}, {"time": 1.5, "sfx": "chime.wav"}]
            },
            {
                "badge": "🎯 BÀI HỌC CỐT LÕI",
                "headline": "ỨNG DỤNG THỰC TẾ:\nBIẾN TRI THỨC THÀNH SỨC MẠNH",
                "subtext": "Phương pháp đột phá được các chuyên gia áp dụng...",
                "spoken": f"Khi bạn làm chủ được bản chất của {topic_str}, bạn có thể biến nó thành đòn bẩy để giải quyết các vấn đề phức tạp và đạt hiệu suất vượt trội.",
                "theme_color": (80, 220, 140),
                "particle_type": "steam",
                "char_side": "left",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}, {"time": 1.2, "sfx": "chime.wav"}]
            },
            {
                "badge": "🚀 TỔNG KẾT HÀNH ĐỘNG",
                "headline": "TƯƠNG LAI BẮT ĐẦU TỪ HÔM NAY:\nHÀNH ĐỘNG ĐỂ KHÁC BIỆT",
                "subtext": "Khám phá tri thức mới mỗi ngày cùng chúng tôi!",
                "spoken": "Tri thức chỉ thực sự có giá trị khi bạn áp dụng nó vào hành động. Đừng dừng lại ở hiểu biết, hãy bắt đầu thay đổi ngay hôm nay!",
                "theme_color": (0, 240, 255),
                "particle_type": "neon",
                "char_side": "right",
                "sfx_events": [{"time": 0.0, "sfx": "whoosh.wav"}, {"time": 0.2, "sfx": "pop.wav"}, {"time": 2.0, "sfx": "chime.wav"}, {"time": 2.8, "sfx": "boom.wav"}]
            }
        ]
    }
    generic["requires_content_plan"] = True
    return enrich_scene_plan(generic, topic_str)


# ===========================================================================
# 2. HỆ THỐNG FONT & TIỆN ÍCH VẼ
# ===========================================================================

def get_font(size: int, bold: bool = True):
    font_candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/tahomabd.ttf" if bold else "C:/Windows/Fonts/tahoma.ttf",
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def ease_out_back(x: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * math.pow(x - 1, 3) + c1 * math.pow(x - 1, 2)


def draw_visual_concept(draw: ImageDraw.ImageDraw, scene: dict, t: float, beat_index: int):
    """Draw topic-aware motion graphics instead of reusing one mascot layout."""
    visual = scene.get("edit_plan", {}).get("visual_language", "data_stream")
    accent = tuple(scene["theme_color"])
    cx, cy = WIDTH // 2, 1050

    if visual == "neural_network":
        nodes = []
        for layer, count in enumerate((4, 7, 7, 4)):
            x = 145 + layer * 265
            for i in range(count):
                y = 690 + int((i + 1) * 650 / (count + 1))
                nodes.append((layer, x, y))
        for layer in range(3):
            left = [n for n in nodes if n[0] == layer]
            right = [n for n in nodes if n[0] == layer + 1]
            for ai, a in enumerate(left):
                for bi, b in enumerate(right):
                    if (ai * 3 + bi + beat_index) % 4 == 0:
                        pulse = int(50 + 90 * (math.sin(t * 3 + ai + bi) * .5 + .5))
                        draw.line((a[1], a[2], b[1], b[2]), fill=(*accent, pulse), width=2)
        for _, x, y in nodes:
            r = 8 + int(4 * (math.sin(t * 4 + x * .01 + y * .02) * .5 + .5))
            draw.ellipse((x-r, y-r, x+r, y+r), fill=(*accent, 235), outline=(255,255,255,180), width=2)

    elif visual == "automation":
        # Conveyor and articulated robot arm.
        belt_y = 1320
        draw.rounded_rectangle((90, belt_y, 990, belt_y + 95), 35, fill=(20,35,55,230), outline=(*accent,220), width=4)
        shift = int((t * 150) % 220)
        for x in range(-100 + shift, 1100, 220):
            draw.rounded_rectangle((x, belt_y-90, x+130, belt_y), 18, fill=(*accent,170), outline=(255,255,255,160), width=3)
        shoulder = (260, 1110); elbow = (430 + int(math.sin(t*2)*70), 900); hand = (640, 1080 + int(math.cos(t*2)*55))
        draw.line((*shoulder, *elbow), fill=(225,235,245,255), width=48)
        draw.line((*elbow, *hand), fill=(*accent,255), width=38)
        for p, r in ((shoulder,48),(elbow,42),(hand,34)):
            draw.ellipse((p[0]-r,p[1]-r,p[0]+r,p[1]+r), fill=(12,20,34,255), outline=(*accent,255), width=8)

    elif visual == "ethics_balance":
        pulse = 1 + .04 * math.sin(t * 3)
        draw.ellipse((cx-245, cy-245, cx+245, cy+245), outline=(*accent,190), width=8)
        draw.ellipse((cx-185, cy-185, cx+185, cy+185), outline=(*accent,80), width=3)
        draw.line((cx, 750, cx, 1370), fill=(235,240,250,255), width=18)
        tilt = int(math.sin(t*1.6) * 55)
        draw.line((250, 920+tilt, 830, 920-tilt), fill=(*accent,255), width=18)
        for x, y, label in ((280,1080+tilt,"HUMAN"),(800,1080-tilt,"AGI")):
            draw.arc((x-130,y-80,x+130,y+90),0,180,fill=(255,255,255,220),width=8)
            draw.text((x,y+25), label, font=get_font(36, True), fill=(255,255,255), anchor="mm")

    elif visual == "orbital_future":
        draw.ellipse((cx-210, cy-210, cx+210, cy+210), fill=(*accent,90), outline=(*accent,255), width=6)
        for ring in (300, 410):
            draw.ellipse((cx-ring, cy-ring//2, cx+ring, cy+ring//2), outline=(180,220,255,100), width=4)
        angle = t * 1.1
        ox, oy = cx + int(math.cos(angle)*405), cy + int(math.sin(angle)*205)
        draw.ellipse((ox-28,oy-28,ox+28,oy+28), fill=(255,255,255,255))
        # Minimal rocket with a pulsing exhaust.
        rx, ry = 730, 760-int((t*35)%160)
        draw.polygon(((rx,ry-100),(rx-45,ry+35),(rx+45,ry+35)), fill=(240,245,255), outline=(*accent,255))
        flame = 45 + int(25*(math.sin(t*8)*.5+.5))
        draw.polygon(((rx-25,ry+35),(rx,ry+35+flame),(rx+25,ry+35)), fill=(255,130,45,230))

    elif visual == "black_hole":
        for ring in range(9, 0, -1):
            radius = 55 + ring*38
            color = ((*accent, max(20, 170-ring*12)))
            draw.ellipse((cx-radius*1.45,cy-radius*.55,cx+radius*1.45,cy+radius*.55), outline=color, width=10)
        draw.ellipse((cx-155,cy-155,cx+155,cy+155), fill=(0,0,0,255), outline=(255,255,255,90), width=3)

    elif visual == "data_chart":
        values = (0.22, 0.42, 0.36, 0.68, 0.82)
        pts=[]
        for i,v in enumerate(values):
            x=130+i*205; y=1380-int(v*620*(.35+.65*min(1,t/2.5)))
            pts.append((x,y)); draw.ellipse((x-14,y-14,x+14,y+14),fill=(*accent,255))
        if len(pts)>1: draw.line(pts,fill=(*accent,255),width=12,joint="curve")
        draw.line((100,1400,980,1400),fill=(255,255,255,100),width=3)

    else:
        # Fast data ribbons for broad technology scenes.
        for i in range(18):
            y = 650 + i*47
            offset = int((t*(80+i*7)+i*97) % 1080)
            length = 80 + (i*37)%260
            draw.rounded_rectangle((offset-length,y,offset,y+9),5,fill=(*accent,70+(i%4)*35))
            draw.ellipse((offset-8,y-4,offset+8,y+12),fill=(*accent,230))


# ===========================================================================
# 3. TRÌNH TẠO NỀN THÔNG MINH (DYNAMIC VECTOR BACKGROUND GENERATOR)
# ===========================================================================

def create_dynamic_background(palette: dict, theme_color: tuple, scene_idx: int) -> Image.Image:
    """Tạo nền vector Kurzgesagt có chiều sâu không gian, gradient mượt mà và hình khối nghệ thuật."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    top_col = palette["top"]
    bot_col = palette["bottom"]

    # 1. Gradient dọc sâu thẳm
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(top_col[0] + (bot_col[0] - top_col[0]) * ratio)
        g = int(top_col[1] + (bot_col[1] - top_col[1]) * ratio)
        b = int(top_col[2] + (bot_col[2] - top_col[2]) * ratio)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

    # 2. Các tầng đồi/sóng vector Kurzgesagt ở nửa dưới
    layer_colors = [
        (int(bot_col[0] * 1.5 + theme_color[0] * 0.1), int(bot_col[1] * 1.5 + theme_color[1] * 0.1), int(bot_col[2] * 1.5 + theme_color[2] * 0.1)),
        (int(bot_col[0] * 2.0 + theme_color[0] * 0.2), int(bot_col[1] * 2.0 + theme_color[1] * 0.2), int(bot_col[2] * 2.0 + theme_color[2] * 0.2)),
        (int(bot_col[0] * 2.5 + theme_color[0] * 0.3), int(bot_col[1] * 2.5 + theme_color[1] * 0.3), int(bot_col[2] * 2.5 + theme_color[2] * 0.3)),
    ]

    for idx, col in enumerate(layer_colors):
        base_y = 1100 + idx * 250
        pts = [(0, HEIGHT), (0, base_y)]
        steps = 10
        for s in range(1, steps + 1):
            px = int(WIDTH * (s / steps))
            freq = 2.0 + idx
            py = int(base_y + math.sin(s * 0.8 + idx * 1.5 + scene_idx) * 80)
            pts.append((px, py))
        pts.append((WIDTH, HEIGHT))
        draw.polygon(pts, fill=col)

    # 3. Mặt trăng / Vầng hào quang mặt trời ở trên cao
    sun_x = 850 if scene_idx % 2 == 0 else 230
    sun_y = 480
    sun_r = 130
    # Vầng sáng mờ ngoài
    for gr in range(sun_r + 80, sun_r, -15):
        alpha = int(35 * (1 - (gr - sun_r) / 80))
        draw.ellipse([sun_x - gr, sun_y - gr, sun_x + gr, sun_y + gr],
                     fill=(theme_color[0], theme_color[1], theme_color[2], alpha))
    # Quả cầu sáng trung tâm
    draw.ellipse([sun_x - sun_r, sun_y - sun_r, sun_x + sun_r, sun_y + sun_r],
                 fill=(theme_color[0], theme_color[1], theme_color[2], 180))

    return img


# ===========================================================================
# 4. RENDER FRAME HOẠT HỌA MASTER
# ===========================================================================

def render_frame_universal(
    scene: dict,
    t: float,
    bg_img: Image.Image,
    char_img: Image.Image,
    fonts: dict,
    dur: float
) -> Image.Image:
    theme = scene["theme_color"]

    # 1. Visual beats: đổi cỡ cảnh tối đa mỗi 3.5 giây, thay vì giữ một
    # bố cục Ken Burns suốt 10-12 giây.
    beat_seconds = float(scene.get("edit_plan", {}).get("max_visual_beat_seconds", 3.5))
    beat_index = int(t / max(1.0, beat_seconds))
    beat_phase = (t % max(1.0, beat_seconds)) / max(1.0, beat_seconds)
    shot_zooms = (1.0, 1.10, 1.04, 1.14)
    zoom = shot_zooms[beat_index % len(shot_zooms)] + 0.025 * beat_phase
    bw, bh = bg_img.size
    crop_w = int(bw / zoom)
    crop_h = int(bh / zoom)
    pan_y = int(12 * math.sin(t / dur * math.pi))
    pan_direction = (-1, 1, 0, -1)[beat_index % 4]
    x0 = max(0, min(bw - crop_w, (bw - crop_w) // 2 + pan_direction * int(crop_w * 0.04)))
    y0 = max(0, min(bh - crop_h, (bh - crop_h) // 2 + pan_y))
    frame = bg_img.crop((x0, y0, x0 + crop_w, y0 + crop_h)).resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)

    draw = ImageDraw.Draw(frame, "RGBA")

    # 2. Hạt môi trường sống động
    ptype = scene["particle_type"]
    if ptype == "embers":
        for i in range(22):
            seed = i * 47.3
            life = (t * 0.8 + i * 0.04) % 1.0
            px = 540 + math.sin(seed + t * 4.0) * 380 * life
            py = HEIGHT - life * 1400
            pr = int((1.0 - life) * 6 + 2)
            alpha = int((1.0 - life) * 220)
            draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(255, 180, 50, alpha))
    elif ptype == "pollen":
        for i in range(20):
            seed = i * 83.1
            life = (t * 0.4 + i * 0.05) % 1.0
            px = 100 + (seed * 11) % (WIDTH - 200) + math.sin(t * 2.0 + seed) * 40
            py = 300 + life * 1200
            pr = int(3 + math.sin(t * 5.0 + i) * 2)
            alpha = int(120 + 80 * math.sin(t * 3.0 + seed))
            draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(255, 235, 120, alpha))
    elif ptype == "steam":
        for i in range(12):
            life = (t * 0.5 + i * 0.08) % 1.0
            px = 750 + math.sin(life * 3.0 + i) * 80 + life * 100
            py = 1100 - life * 800
            pr = int(30 + life * 70)
            alpha = int((1.0 - life) * 110)
            draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(220, 230, 240, alpha))
    elif ptype == "neon":
        for i in range(20):
            seed = i * 61.7
            life = (t * 0.7 + i * 0.05) % 1.0
            px = 200 + (seed * 17) % (WIDTH - 400)
            py = 400 + math.sin(t * 3.0 + seed) * 250
            pr = int(4 + math.sin(t * 6.0 + seed) * 2)
            col = (0, 240, 255, 200) if i % 2 == 0 else (200, 100, 255, 200)
            draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=col)
    else:  # stars
        for i in range(25):
            seed = i * 31.5
            px = int((seed * 37) % WIDTH)
            py = int((seed * 53) % 900)
            twinkle = math.sin(t * 4.0 + seed) * 0.5 + 0.5
            pr = int(2 + twinkle * 3)
            alpha = int(100 + 155 * twinkle)
            draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(255, 255, 255, alpha))

    # Topic-aware visual stage. This is the main subject in body scenes;
    # presenter/mascot is reserved for the hook and final CTA.
    role = scene.get("edit_plan", {}).get("role", "body")
    draw_visual_concept(draw, scene, t, beat_index)

    # 3. Nhân vật Explorer Hoạt Họa (Squash & Stretch, Breathing Bob, Tilt)
    entry_dur = 0.65
    entry_p = ease_out_back(t / entry_dur) if t < entry_dur else 1.0

    bob = math.sin(t * 3.4)
    y_float = -bob * 18.0
    scale_x = (1.0 - bob * 0.035) * entry_p
    scale_y = (1.0 + bob * 0.035) * entry_p
    rot_deg = math.sin(t * 1.7) * 2.8

    base_x = 760 if scene["char_side"] == "right" else 240
    if beat_index % 2:
        base_x = WIDTH - base_x
    base_y = 1260

    orig_w, orig_h = char_img.size
    target_scale = 0.42 if role in {"hook", "cta"} else 0.0
    cw = max(10, int(orig_w * target_scale * scale_x))
    ch = max(10, int(orig_h * target_scale * scale_y))

    char_resized = char_img.resize((cw, ch), Image.Resampling.BILINEAR)
    if abs(rot_deg) > 0.5:
        char_resized = char_resized.rotate(rot_deg, resample=Image.Resampling.BILINEAR, expand=True)

    cur_x = int(base_x - char_resized.width // 2)
    cur_y = int(base_y - char_resized.height // 2 + y_float)

    # Bóng đổ mềm dưới chân nhân vật
    shadow_w = int(cw * 0.7)
    shadow_h = int(cw * 0.16)
    shadow_x = base_x - shadow_w // 2
    shadow_y = base_y + int(ch * 0.42)
    draw.ellipse([shadow_x, shadow_y, shadow_x + shadow_w, shadow_y + shadow_h],
                 fill=(0, 0, 0, 95))

    frame.paste(char_resized, (cur_x, cur_y), char_resized)

    # Vòng hào quang phát sáng trên đầu nhân vật khi thuyết trình
    talk_wave = math.sin(t * 12.0) * 0.5 + 0.5
    head_top_y = cur_y + int(ch * 0.12)
    head_center_x = cur_x + char_resized.width // 2
    glow_r = int(22 + talk_wave * 8)
    draw.ellipse([head_center_x - glow_r, head_top_y - glow_r, head_center_x + glow_r, head_top_y + glow_r],
                 outline=(theme[0], theme[1], theme[2], int(150 * talk_wave)), width=3)

    # 4. Thẻ chữ Glassmorphism hiện đại
    card_delay = 0.25
    cp = min(1.0, (t - card_delay) / 0.5) if t >= card_delay else 0.0
    cp_ease = ease_out_back(cp) if cp > 0 else 0.0

    role = scene.get("edit_plan", {}).get("role", "body")
    show_full_card = role in {"hook", "cta"} or t < min(2.4, dur * 0.28)
    if cp_ease > 0.01 and show_full_card:
        card_w = 980
        card_h = 320
        sc_w = int(card_w * cp_ease)
        sc_h = int(card_h * cp_ease)
        sc_x = WIDTH // 2 - sc_w // 2
        cy = 140
        sc_y = (cy + card_h // 2) - sc_h // 2

        draw.rounded_rectangle(
            [sc_x, sc_y, sc_x + sc_w, sc_y + sc_h],
            radius=28,
            fill=(12, 16, 26, 215),
            outline=(theme[0], theme[1], theme[2], 230),
            width=3
        )

        if cp_ease > 0.8:
            # Badge
            draw.text((WIDTH // 2, cy + 45), scene["badge"], font=fonts["badge"],
                      fill=theme, anchor="mm")
            # Headline
            draw.text((WIDTH // 2, cy + 145), scene["headline"], font=fonts["headline"],
                      fill=(255, 255, 255), anchor="mm", align="center")
            # Subtext
            draw.text((WIDTH // 2, cy + 265), scene["subtext"], font=fonts["subtext"],
                      fill=(200, 220, 240), anchor="mm")

    # 5. Thanh tiến trình thời gian ở đáy video
    prog_y = 1860
    prog_w = 900
    prog_x = (WIDTH - prog_w) // 2
    draw.rounded_rectangle([prog_x, prog_y, prog_x + prog_w, prog_y + 16], radius=8, fill=(30, 40, 55, 180))
    prog_fill_w = int(prog_w * min(1.0, t / dur))
    if prog_fill_w > 0:
        draw.rounded_rectangle([prog_x, prog_y, prog_x + prog_fill_w, prog_y + 16],
                               radius=8, fill=(theme[0], theme[1], theme[2], 255))

    return frame


# ===========================================================================
# 5. HÀM TẠO GIỌNG ĐỌC AI TIẾNG VIỆT
# ===========================================================================

def generate_voice(text: str, out_path: Path):
    clean_text = text.replace("%", " phần trăm ").replace("&", " và ")
    words = clean_text.split()
    chunks, curr = [], []
    for w in words:
        if len(" ".join(curr + [w])) < 90:
            curr.append(w)
        else:
            chunks.append(" ".join(curr))
            curr = [w]
    if curr:
        chunks.append(" ".join(curr))

    tmp_dir = Path(tempfile.mkdtemp())
    parts = []
    for idx, c in enumerate(chunks):
        url = "https://translate.google.com/translate_tts?ie=UTF-8&tl=vi&client=tw-ob&q=" + urllib.parse.quote(c)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        p_file = tmp_dir / f"p_{idx:02d}.mp3"
        with urllib.request.urlopen(req, timeout=10) as resp, open(p_file, "wb") as f_out:
            f_out.write(resp.read())
        parts.append(p_file)

    list_txt = tmp_dir / "list.txt"
    with open(list_txt, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{p.resolve()}'\n")

    subprocess.run(
        f'ffmpeg -y -f concat -safe 0 -i "{list_txt}" -c copy "{out_path}"',
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return out_path


# ===========================================================================
# 6. PIPELINE SẢN XUẤT VIDEO TOÀN DIỆN CHO MỌI CHỦ ĐỀ
# ===========================================================================

def produce_video_for_topic(topic: str, output_folder_name: str = None, renderer: str = "remotion") -> str:
    print("=" * 80)
    print("🎬 UNIVERSAL AI VIDEO STUDIO — HỆ THỐNG SẢN XUẤT VIDEO TOÀN DIỆN")
    print(f"🎯 CHỦ ĐỀ: {topic.upper()}")
    print("💎 Phong cách: Vector Kurzgesagt + Mascot Squash & Stretch + Sound Master -14 LUFS")
    print("=" * 80)

    # 1. Phân tích kịch bản
    config = build_dynamic_topic(topic)
    if config.get("requires_content_plan"):
        raise ValueError(
            f"Chưa có content plan đủ cụ thể cho chủ đề '{topic}'. "
            "Hãy thêm preset hoặc dùng Director JSON; hệ thống từ chối render template generic."
        )
    scenes = config["scenes"]
    palette = config["palette"]

    # Đặt thư mục đầu ra
    if not output_folder_name:
        slug = "".join(c if c.isalnum() else "_" for c in topic.lower().strip())[:40]
        output_dir = FACTORY_DIR / f"{slug}_master" / "draft_01"
    else:
        output_dir = FACTORY_DIR / output_folder_name / "draft_01"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. Sinh Voice AI
    full_spoken = " ".join(s["spoken"] for s in scenes)
    voice_file = output_dir / "voice.mp3"
    print("\n🎙️ [BƯỚC 1/5] Sinh giọng đọc AI tiếng Việt...")
    generate_voice(full_spoken, voice_file)

    dur_cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{voice_file}"'
    voice_dur = float(subprocess.check_output(dur_cmd, shell=True).decode().strip())
    print(f"   ⏱️ Thời lượng audio thực tế: {voice_dur:.1f} giây")

    # Cân bằng thời lượng từng cảnh
    word_counts = [max(1, len(s.get("spoken", "").split())) for s in scenes]
    total_words = sum(word_counts)
    for s, words in zip(scenes, word_counts):
        s["duration"] = round(voice_dur * words / total_words, 2)

    quality_report = write_quality_report(config, output_dir / "quality_report.json")
    if not quality_report.passed:
        raise ValueError("Quality gate thất bại: " + "; ".join(quality_report.errors))

    # 3. Chuẩn bị hình ảnh nền và nhân vật
    print("\n🎨 [BƯỚC 2/5] Tạo tài nguyên đồ họa nghệ thuật Kurzgesagt & nhân vật Mascot...")
    char_path = CHARACTERS_DIR / "kurzgesagt_character.png"
    char_img = Image.open(char_path).convert("RGBA")

    # Tạo các nền vector đẹp mắt theo từng cảnh
    bg_images = []
    for idx, sc in enumerate(scenes):
        bg = create_dynamic_background(palette, sc["theme_color"], idx)
        bg_images.append(bg)

    fonts = {
        "badge": get_font(42, bold=True),
        "headline": get_font(54, bold=True),
        "subtext": get_font(34, bold=False),
    }

    # 4. Render Video Frame-by-Frame qua FFmpeg
    raw_video = output_dir / "raw_animation.mp4"
    if renderer == "remotion":
        print("\n🎬 [BƯỚC 3/5] Render PremiumMotion bằng Remotion (SVG + spring + stagger + captions)...")
        render_premium(config, raw_video, output_dir / "premium_motion_props.json")
        print("   ✅ Remotion PremiumMotion hoàn tất; Pillow không được dùng.")
    else:
        print("\n🎬 [BƯỚC 3/5] Render Pillow fallback 1080x1920 @ 30 FPS...")
        ffmpeg_proc = subprocess.Popen(
            ["ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
             "-s", f"{WIDTH}x{HEIGHT}", "-pix_fmt", "rgba", "-r", str(FPS),
             "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-preset", "fast", "-crf", "18", str(raw_video)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        total_frames = 0
        for s_idx, (sc, bg) in enumerate(zip(scenes, bg_images), start=1):
            sc_dur = sc["duration"]
            sc_frames = int(round(sc_dur * FPS))
            print(f"   [Cảnh {s_idx}/{len(scenes)}] {sc['badge']} ({sc_dur:.1f}s, {sc_frames} frames)...")
            for f_idx in range(sc_frames):
                frame_img = render_frame_universal(sc, f_idx / FPS, bg, char_img, fonts, sc_dur)
                ffmpeg_proc.stdin.write(frame_img.tobytes())
                total_frames += 1
        ffmpeg_proc.stdin.close()
        ffmpeg_proc.wait()
        if ffmpeg_proc.returncode != 0:
            raise RuntimeError("Pillow/FFmpeg fallback render thất bại")
        print(f"   ✅ Pillow fallback đã render {total_frames} frames.")

    # 5. Master Sound Design: Voice + BGM + SFX
    print("\n🔊 [BƯỚC 4/5] Hòa âm Master Sound Design chuẩn EBU R128 (-14 LUFS)...")
    sfx_timeline = []
    t_scene_start = 0.0
    for sc in scenes:
        for ev in sc.get("sfx_events", []):
            global_t = t_scene_start + ev["time"]
            sfx_file = SFX_DIR / ev["sfx"]
            if sfx_file.exists():
                sfx_timeline.append((global_t, sfx_file))
        t_scene_start += sc["duration"]

    final_video = output_dir / "draft_video.mp4"
    bgm_path = BGM_DIR / config.get("bgm", "cinematic_epic.mp3")
    if not bgm_path.exists():
        bgm_path = BGM_DIR / "cinematic_epic.mp3"

    cmd_inputs = [
        f'-i "{raw_video}"',
        f'-i "{voice_file}"',
        f'-i "{bgm_path}"'
    ]
    for _, sfx_p in sfx_timeline:
        cmd_inputs.append(f'-i "{sfx_p}"')

    filter_lines = [
        "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.40[voice];",
        "[2:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.22[bgm];"
    ]
    mix_tags = ["[voice]", "[bgm]"]

    for idx, (offset_sec, _) in enumerate(sfx_timeline):
        in_idx = 3 + idx
        delay_ms = int(offset_sec * 1000)
        tag = f"[sfx{idx}]"
        filter_lines.append(f"[{in_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay={delay_ms}|{delay_ms},volume=1.35{tag};")
        mix_tags.append(tag)

    total_inputs = len(mix_tags)
    filter_lines.append(f'{"".join(mix_tags)}amix=inputs={total_inputs}:duration=longest:normalize=0[mixed];')
    filter_lines.append('[mixed]loudnorm=I=-14:LRA=7:TP=-1.5[aout]')
    full_filter = "".join(filter_lines)

    final_cmd = (
        f'ffmpeg -y {" ".join(cmd_inputs)} '
        f'-filter_complex "{full_filter}" '
        f'-map 0:v -map "[aout]" '
        f'-c:v copy -c:a aac -b:a 256k -shortest "{final_video}"'
    )
    subprocess.run(final_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 6. Lưu script & Subtitles SRT
    with open(output_dir / "script.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    with open(output_dir / "subtitles.srt", "w", encoding="utf-8") as f:
        t_curr = 0.0
        for idx, sc in enumerate(scenes, start=1):
            t_next = t_curr + sc["duration"]
            m_s, s_s = int(t_curr // 60), int(t_curr % 60)
            m_e, s_e = int(t_next // 60), int(t_next % 60)
            f.write(f"{idx}\n00:{m_s:02d}:{s_s:02d},000 --> 00:{m_e:02d}:{s_e:02d},000\n{sc['badge']}: {sc['spoken']}\n\n")
            t_curr = t_next

    # 7. Trích xuất ảnh preview
    print("\n📸 [BƯỚC 5/5] Trích xuất các ảnh preview xác thực...")
    subprocess.run(
        f'ffmpeg -y -ss 00:00:05.0 -i "{final_video}" -vframes 1 "{output_dir / "preview_scene1.jpg"}"',
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    generate_contact_sheet(final_video, output_dir / "contact_sheet.jpg")
    render_report = inspect_render(final_video, output_dir / "render_quality_report.json")
    if not render_report.passed:
        raise ValueError("Render quality gate thất bại: " + "; ".join(render_report.errors))
    subprocess.run(
        f'ffmpeg -y -ss 00:00:20.0 -i "{final_video}" -vframes 1 "{output_dir / "preview_scene2.jpg"}"',
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    file_size_mb = final_video.stat().st_size / (1024 * 1024) if final_video.exists() else 0.0
    print("\n" + "=" * 80)
    print("🎉 XUẤT XƯỞNG VIDEO THÀNH CÔNG!")
    print(f"📁 Video Master: {final_video} ({file_size_mb:.1f} MB, {voice_dur:.1f}s)")
    print(f"📁 Thư mục sản phẩm: {output_dir}")
    print("=" * 80)
    return str(final_video)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal AI Video Studio")
    parser.add_argument("--topic", type=str, default="Trí tuệ nhân tạo AGI", help="Chủ đề video bất kỳ")
    parser.add_argument("--out", type=str, default=None, help="Tên thư mục output")
    parser.add_argument("--renderer", choices=["remotion", "pillow"], default="remotion",
                        help="Remotion là mặc định; Pillow chỉ là fallback")
    args = parser.parse_args()

    produce_video_for_topic(args.topic, args.out, args.renderer)
