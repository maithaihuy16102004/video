"""
Animated Character Studio — Xưởng Phim Hoạt Hình & Motion Graphics AI Đích Thực
Khắc phục 100% các vấn đề:
1. VẼ NHÂN VẬT THỰC SỰ (2D Parametric Character Rig):
   - Đầy đủ cử động: vẫy tay chào (wave), chỉ tay vào biểu đồ (point), mím môi suy nghĩ (thinking),
     nhảy cẫng phấn khích (excited), giơ ngón tay cái (thumbs_up), nói chuyện chuyển động miệng liên tục theo giọng đọc.
2. ANIMATION & MOTION GRAPHICS ĐÍCH THỰC:
   - Chữ nảy bật (pop kinetic), trượt lên (slide up), bóng đèn phát sáng (lightbulb), thanh tiến trình (progress bar),
     lưới công nghệ (tech grid), ngôi sao nổ (star explosion).
3. SOUND EFFECTS (SFX) ĐỒNG BỘ TỪNG MỐC CỬ ĐỘNG:
   - POP khi chữ/icon bật ra, WHOOSH khi chuyển cảnh & vung tay, BOOM khi lửa nổ, CHIME khi thành tựu đạt được.
4. MASTER COMPOSITING:
   - Ghép Voice lồng tiếng + BGM ducking + SFX đa tầng thành video 1080x1920 MP4 hoàn chỉnh.
"""

import os
import sys
import json
import math
import tempfile
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
AGENT_ROOT = BASE_DIR.parent
CHARMOTION_SRC = AGENT_ROOT / "charmotion" / "src"
BGM_FILE = AGENT_ROOT / "assets" / "bgm" / "cinematic_epic.mp3"
SFX_DIR = AGENT_ROOT / "assets" / "sfx"
OUTPUT_DIR = AGENT_ROOT / "drafts_factory" / "lich_su_loai_nguoi_animated" / "draft_01"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

for p in [str(CHARMOTION_SRC), str(BASE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from render import render_video


# ===========================================================================
# 1. KỊCH BẢN HOẠT HÌNH NHÂN VẬT (5 CẢNH, TIẾT TẤU DỒN DẬP ~35 GIÂY)
# ===========================================================================

ANIMATED_SCENES = [
    {
        "title": "Khoảnh khắc khởi đầu",
        "duration": 6.5,
        "background": {"type": "tech", "top": [20, 25, 45], "bottom": [5, 10, 25], "grid_color": [70, 150, 230]},
        "character": {"pose": "wave", "expression": "happy", "x": 0.28, "y": 0.72, "scale": 125, "talking": True},
        "texts": [
            {"text": "70.000 NĂM LỊCH SỬ", "x": 0.5, "y": 0.15, "size": 65, "effect": "pop", "delay": 0.2, "duration": 1.2, "color": [255, 215, 0]},
            {"text": "Làm sao loài người thống trị Trái Đất?", "x": 0.5, "y": 0.26, "size": 68, "effect": "slide_up", "delay": 0.5, "duration": 1.4, "max_width": 950},
            {"text": "Bắt đầu từ loài linh trưởng yếu ớt châu Phi...", "x": 0.62, "y": 0.40, "size": 44, "effect": "fade", "delay": 1.5, "duration": 1.5, "color": [180, 200, 220], "max_width": 620}
        ],
        "shapes": [
            {"type": "fire", "x": 0.72, "y": 0.65, "scale": 240, "delay": 0.4, "duration": 1.2},
            {"type": "star", "x": 0.18, "y": 0.22, "radius": 40, "color": [255, 215, 0], "delay": 0.4, "duration": 1.0},
            {"type": "star", "x": 0.85, "y": 0.22, "radius": 40, "color": [255, 215, 0], "delay": 0.6, "duration": 1.0}
        ],
        "spoken": "Bảy mươi nghìn năm trước, tổ tiên chúng ta chỉ là một loài linh trưởng nhỏ bé, chật vật sinh tồn giữa thiên nhiên hoang dã.",
        "sfx_events": [
            {"time": 0.0, "sfx": "whoosh.wav"},
            {"time": 0.2, "sfx": "pop.wav"},
            {"time": 0.5, "sfx": "pop.wav"}
        ]
    },
    {
        "title": "Bước ngoặt ngọn lửa",
        "duration": 7.0,
        "background": {"type": "gradient", "top": [45, 15, 10], "bottom": [15, 5, 5]},
        "character": {"pose": "excited", "expression": "excited", "x": 0.26, "y": 0.72, "scale": 120, "talking": True},
        "texts": [
            {"text": "BƯỚC NGOẶT: THUẦN HÓA LỬA", "x": 0.5, "y": 0.15, "size": 68, "effect": "pop", "delay": 0.2, "duration": 1.2, "color": [255, 90, 40]},
            {"text": "VŨ KHÍ: TRÍ TƯỞNG TƯỢNG", "x": 0.5, "y": 0.26, "size": 62, "effect": "pop", "delay": 0.8, "duration": 1.2, "color": [255, 215, 0]},
            {"text": "Nấu chín thức ăn & gắn kết bộ tộc!", "x": 0.64, "y": 0.40, "size": 46, "effect": "slide_up", "delay": 1.4, "duration": 1.5, "max_width": 600}
        ],
        "shapes": [
            {"type": "fire", "x": 0.70, "y": 0.64, "scale": 340, "delay": 0.3, "duration": 1.5},
            {"type": "star", "x": 0.70, "y": 0.35, "radius": 45, "color": [255, 215, 0], "delay": 1.0, "duration": 1.0}
        ],
        "spoken": "Nhưng bước ngoặt đến khi con người thuần hóa ngọn lửa, và sở hữu vũ khí tối thượng: Trí tưởng tượng để kết nối hàng triệu cá nhân xa lạ.",
        "sfx_events": [
            {"time": 0.0, "sfx": "whoosh.wav"},
            {"time": 0.2, "sfx": "boom.wav"},
            {"time": 0.8, "sfx": "pop.wav"},
            {"time": 1.4, "sfx": "chime.wav"}
        ]
    },
    {
        "title": "Cách mạng nông nghiệp",
        "duration": 7.0,
        "background": {"type": "tech", "top": [20, 40, 20], "bottom": [8, 18, 10], "grid_color": [80, 190, 110]},
        "character": {"pose": "point", "expression": "happy", "x": 0.25, "y": 0.72, "scale": 115, "talking": True},
        "texts": [
            {"text": "CÁCH MẠNG NÔNG NGHIỆP", "x": 0.5, "y": 0.15, "size": 66, "effect": "pop", "delay": 0.2, "duration": 1.2, "color": [255, 220, 80]},
            {"text": "Thuần Hóa Cây Lúa Mì & Lập Đế Chế", "x": 0.5, "y": 0.26, "size": 54, "effect": "slide_up", "delay": 0.6, "duration": 1.4, "max_width": 950},
            {"text": "Từ săn bắt hái lượm sang định cư canh tác!", "x": 0.62, "y": 0.40, "size": 44, "effect": "fade", "delay": 1.6, "duration": 1.5, "color": [200, 240, 180], "max_width": 600}
        ],
        "shapes": [
            {"type": "wheat", "x": 0.72, "y": 0.74, "scale": 380, "delay": 0.4, "duration": 2.2},
            {"type": "progress", "x": 0.5, "y": 0.92, "width": 800, "height": 30, "color": [255, 215, 60], "delay": 0.5, "duration": 2.5}
        ],
        "spoken": "Từ săn bắt hái lượm, chúng ta định cư, thuần hóa lúa mì, xây dựng làng mạc và đắp nên những kỳ quan đế chế đầu tiên.",
        "sfx_events": [
            {"time": 0.0, "sfx": "whoosh.wav"},
            {"time": 0.2, "sfx": "pop.wav"},
            {"time": 0.6, "sfx": "pop.wav"},
            {"time": 2.0, "sfx": "chime.wav"}
        ]
    },
    {
        "title": "Bùng nổ công nghiệp",
        "duration": 7.0,
        "background": {"type": "tech", "top": [20, 30, 50], "bottom": [8, 12, 25], "grid_color": [50, 150, 240]},
        "character": {"pose": "talk", "expression": "neutral", "x": 0.26, "y": 0.72, "scale": 115, "talking": True},
        "texts": [
            {"text": "BÙNG NỔ CÔNG NGHIỆP", "x": 0.5, "y": 0.15, "size": 66, "effect": "pop", "delay": 0.2, "duration": 1.2, "color": [80, 180, 255]},
            {"text": "Bánh Răng Động Cơ Hơi Nước & Điện Năng", "x": 0.5, "y": 0.26, "size": 52, "effect": "slide_up", "delay": 0.6, "duration": 1.4, "max_width": 950},
            {"text": "Cơ khí hóa sản xuất và chuyển động không ngừng!", "x": 0.62, "y": 0.40, "size": 42, "effect": "fade", "delay": 1.6, "duration": 1.5, "color": [180, 210, 240], "max_width": 600}
        ],
        "shapes": [
            {"type": "gears", "x": 0.70, "y": 0.64, "scale": 310, "delay": 0.4, "duration": 1.5}
        ],
        "spoken": "Rồi động cơ hơi nước và điện năng bùng nổ, biến Trái Đất thành một mạng lưới khổng lồ của sắt thép và ánh sáng rực rỡ.",
        "sfx_events": [
            {"time": 0.0, "sfx": "whoosh.wav"},
            {"time": 0.2, "sfx": "pop.wav"},
            {"time": 0.6, "sfx": "boom.wav"}
        ]
    },
    {
        "title": "Kỷ nguyên AI và vũ trụ",
        "duration": 7.5,
        "background": {"type": "tech", "top": [30, 10, 45], "bottom": [10, 5, 20], "grid_color": [180, 90, 230]},
        "character": {"pose": "thumbs_up", "expression": "excited", "x": 0.20, "y": 0.75, "scale": 120, "talking": True},
        "texts": [
            {"text": "ROBOT, AI & CHINH PHỤC VŨ TRỤ", "x": 0.5, "y": 0.15, "size": 62, "effect": "pop", "delay": 0.2, "duration": 1.2, "color": [0, 240, 255]},
            {"text": "Kỷ Nguyên Mạng Nơ-ron & Không Gian", "x": 0.5, "y": 0.26, "size": 52, "effect": "slide_up", "delay": 0.6, "duration": 1.4, "max_width": 950},
            {"text": "Từ hang đá tăm tối đến bá chủ hành tinh!", "x": 0.5, "y": 0.38, "size": 48, "effect": "pop", "delay": 1.8, "duration": 1.4, "color": [255, 215, 0], "max_width": 900}
        ],
        "shapes": [
            {"type": "robot", "x": 0.52, "y": 0.62, "scale": 220, "delay": 0.3, "duration": 1.5},
            {"type": "rocket", "x": 0.82, "y": 0.52, "scale": 230, "delay": 0.8, "duration": 1.5},
            {"type": "neural", "x": 0.55, "y": 0.90, "width": 620, "height": 170, "delay": 0.5, "duration": 2.0}
        ],
        "spoken": "Hôm nay chúng ta phóng tàu vào vũ trụ sâu thẳm, kiến tạo AI. Chúng ta đã chính thức trở thành bá chủ của cả hành tinh!",
        "sfx_events": [
            {"time": 0.0, "sfx": "whoosh.wav"},
            {"time": 0.2, "sfx": "pop.wav"},
            {"time": 1.8, "sfx": "chime.wav"},
            {"time": 2.5, "sfx": "boom.wav"}
        ]
    }
]


# ===========================================================================
# 2. HÀM SINH GIỌNG ĐỌC AI TIẾNG VIỆT
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
# 3. QUY TRÌNH SẢN XUẤT MASTER ANIMATION VIDEO
# ===========================================================================

def build_animated_character_master():
    print("=" * 75)
    print("🎬 ANIMATED CHARACTER STUDIO — XƯỞNG PHIM HOẠT HÌNH & MOTION GRAPHICS")
    print("🎯 Chủ đề: HÀNH TRÌNH 70.000 NĂM CỦA LOÀI NGƯỜI (MASTER ANIMATION)")
    print("💎 Nhân vật 2D hoạt hoạ + Chuyển động cơ thể + Chữ nảy Pop + Sound Effects")
    print("=" * 75)

    # 1. Sinh voice
    full_spoken = " ".join(s["spoken"] for s in ANIMATED_SCENES)
    voice_file = OUTPUT_DIR / "voice.mp3"
    print("\n🎙️ [BƯỚC 1] Sinh giọng đọc AI tiếng Việt...")
    generate_voice(full_spoken, voice_file)

    dur_cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{voice_file}"'
    voice_dur = float(subprocess.check_output(dur_cmd, shell=True).decode().strip())
    print(f"   ⏱️ Thời lượng audio: {voice_dur:.1f} giây")

    # Điều chỉnh thời lượng từng scene khớp với voice thực tế
    total_scene_target = sum(s["duration"] for s in ANIMATED_SCENES)
    ratio = voice_dur / total_scene_target
    for s in ANIMATED_SCENES:
        s["duration"] = round(s["duration"] * ratio, 2)

    # 2. Render Animation từng frame bằng Charmotion Engine
    script_data = {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "scenes": ANIMATED_SCENES
    }
    raw_video = OUTPUT_DIR / "raw_animation.mp4"
    print("\n🎨 [BƯỚC 2] Vẽ nhân vật 2D cử động & Motion Graphics từng frame...")
    render_video(script_data, str(raw_video), verbose=True)
    print(f"   ✅ Đã render xong animation: {raw_video.name}")

    # 3. Thu thập mốc thời gian tất cả sự kiện Sound Effects
    print("\n🔊 [BƯỚC 3] Lập bản đồ Sound Effects (Pop, Whoosh, Boom, Chime) chính xác theo chuyển động...")
    sfx_timeline = []
    t_scene_start = 0.0
    for sc in ANIMATED_SCENES:
        for ev in sc.get("sfx_events", []):
            global_t = t_scene_start + ev["time"]
            sfx_file = SFX_DIR / ev["sfx"]
            if sfx_file.exists():
                sfx_timeline.append((global_t, sfx_file))
        t_scene_start += sc["duration"]

    print(f"   ⚡ Tổng cộng có {len(sfx_timeline)} hiệu ứng âm thanh SFX được kích hoạt!")

    # 4. Master Audio Mix: Voice + BGM Ducking + toàn bộ Sound Effects!
    final_video = OUTPUT_DIR / "draft_video.mp4"
    print("\n🎛️ [BƯỚC 4] Hòa âm Master Compositing đa tầng...")

    cmd_inputs = [
        f'-i "{raw_video}"',
        f'-i "{voice_file}"',
        f'-i "{BGM_FILE}"'
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
    res = subprocess.run(final_cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"⚠️ FFmpeg Error: {res.stderr[:500]}")

    # 5. Lưu script & subtitles
    with open(OUTPUT_DIR / "script.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_DIR / "subtitles.srt", "w", encoding="utf-8") as f:
        t_curr = 0.0
        for idx, sc in enumerate(ANIMATED_SCENES, start=1):
            t_next = t_curr + sc["duration"]
            m_s, s_s = int(t_curr // 60), int(t_curr % 60)
            m_e, s_e = int(t_next // 60), int(t_next % 60)
            f.write(f"{idx}\n00:{m_s:02d}:{s_s:02d},000 --> 00:{m_e:02d}:{s_e:02d},000\n{sc['title']}: {sc['spoken']}\n\n")
            t_curr = t_next

    file_size_mb = final_video.stat().st_size / (1024 * 1024) if final_video.exists() else 0.0
    print("\n" + "=" * 75)
    print(f"🎉 HOÀN THÀNH XUẤT XƯỞNG BẢN ANIMATION MASTER HOÀN CHỈNH!")
    print(f"📁 Video Master: {final_video} ({file_size_mb:.1f} MB, {voice_dur:.1f}s)")
    print("=" * 75)
    return str(final_video)


if __name__ == "__main__":
    build_animated_character_master()
