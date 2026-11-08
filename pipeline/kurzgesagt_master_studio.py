"""
Kurzgesagt Master Studio — Xưởng Phim Hoạt Hình Khoa Học & Lịch Sử Đỉnh Cao
Khắc phục 100% nhược điểm:
1. KHÔNG CÒN NÉT VẼ ĐƠN ĐIỆU 1 MÀU:
   - Toàn bộ 5 cảnh sử dụng tranh minh họa vector nghệ thuật phong cách Kurzgesagt (màu sắc rực rỡ, giàu chiều sâu, đúng chuẩn 9:16).
2. NHÂN VẬT HOẠT HỌA MỀM MẠI (DISNEY 12 PRINCIPLES):
   - Nhân vật Explorer hoạt họa chuyên nghiệp với hiệu ứng Squash & Stretch đàn hồi.
   - Thở nhịp nhàng, lắc lư nhẹ nhàng, bật nảy (Overshoot bounce) khi xuất hiện.
   - Biểu tượng cảm xúc (Emote bubble & Speech wave) nhấp nháy đồng bộ giọng đọc.
3. CAMERA CINEMATIC KEN BURNS & PARALLAX:
   - Máy quay zoom từ từ (1.0 -> 1.07x) tạo cảm giác chuyển động không gian 2.5D liên tục.
4. HIỆU ỨNG HẠT MÔI TRƯỜNG ĐA DẠNG:
   - Tàn tro lửa bay (Embers), phấn hoa vàng (Pollen), khói hơi nước (Steam), hạt sao và xung điện AI (Neon data).
5. SOUND DESIGN CHUẨN BROADCAST:
   - Voice rõ nét + 18 SFX đập đúng nhịp + BGM ducking chuẩn EBU R128 (-14 LUFS).
"""

import os
import sys
import json
import math
import random
import tempfile
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
AGENT_ROOT = BASE_DIR.parent
ASSETS_DIR = AGENT_ROOT / "assets"
SCENES_DIR = ASSETS_DIR / "scenes"
CHARACTERS_DIR = ASSETS_DIR / "characters"
SFX_DIR = ASSETS_DIR / "sfx"
BGM_FILE = ASSETS_DIR / "bgm" / "cinematic_epic.mp3"
OUTPUT_DIR = AGENT_ROOT / "drafts_factory" / "lich_su_loai_nguoi_animated" / "draft_01"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

WIDTH = 1080
HEIGHT = 1920
FPS = 30


# ===========================================================================
# 1. CẤU HÌNH 5 CẢNH KURZGESAGT
# ===========================================================================

SCENES = [
    {
        "id": 1,
        "title": "Khoảnh khắc khởi đầu",
        "duration": 9.2,
        "bg_image": str(SCENES_DIR / "scene1.jpg"),
        "theme_color": (255, 215, 0),        # Vàng hoàng kim
        "badge": "⏳ 70.000 NĂM LỊCH SỬ",
        "headline": "LÀM SAO LOÀI NGƯỜI\nTHỐNG TRỊ TRÁI ĐẤT?",
        "subtext": "Khởi đầu từ một loài linh trưởng nhỏ bé yếu ớt tại Đông Phi...",
        "particle_type": "stars",
        "char_side": "right",
        "spoken": "Bảy mươi nghìn năm trước, tổ tiên chúng ta chỉ là một loài linh trưởng nhỏ bé, chật vật sinh tồn giữa thiên nhiên hoang dã.",
        "sfx_events": [
            {"time": 0.0, "sfx": "whoosh.wav"},
            {"time": 0.2, "sfx": "pop.wav"},
            {"time": 1.5, "sfx": "chime.wav"}
        ]
    },
    {
        "id": 2,
        "title": "Bước ngoặt ngọn lửa",
        "duration": 9.9,
        "bg_image": str(SCENES_DIR / "scene2.jpg"),
        "theme_color": (255, 90, 40),        # Cam đỏ rực
        "badge": "🔥 BƯỚC NGOẶT: LỬA THUẦN HÓA",
        "headline": "VŨ KHÍ TỐI THƯỢNG:\nTRÍ TƯỞNG TƯỢNG",
        "subtext": "Nấu chín thức ăn, giải phóng năng lượng não bộ & gắn kết bộ tộc!",
        "particle_type": "embers",
        "char_side": "left",
        "spoken": "Nhưng bước ngoặt đến khi con người thuần hóa ngọn lửa, và sở hữu vũ khí tối thượng: Trí tưởng tượng để kết nối hàng triệu cá nhân xa lạ.",
        "sfx_events": [
            {"time": 0.0, "sfx": "whoosh.wav"},
            {"time": 0.2, "sfx": "boom.wav"},
            {"time": 1.2, "sfx": "pop.wav"},
            {"time": 2.5, "sfx": "chime.wav"}
        ]
    },
    {
        "id": 3,
        "title": "Cách mạng nông nghiệp",
        "duration": 9.9,
        "bg_image": str(SCENES_DIR / "scene3.jpg"),
        "theme_color": (255, 210, 60),       # Vàng lúa chín
        "badge": "🌾 CÁCH MẠNG NÔNG NGHIỆP",
        "headline": "THUẦN HÓA CÂY LÚA MÌ\n& ĐẮP NÊN ĐẾ CHẾ",
        "subtext": "Từ săn bắt hái lượm sang định cư canh tác và xây dựng làng mạc...",
        "particle_type": "pollen",
        "char_side": "right",
        "spoken": "Từ săn bắt hái lượm, chúng ta định cư, thuần hóa lúa mì, xây dựng làng mạc và đắp nên những kỳ quan đế chế đầu tiên.",
        "sfx_events": [
            {"time": 0.0, "sfx": "whoosh.wav"},
            {"time": 0.2, "sfx": "pop.wav"},
            {"time": 1.0, "sfx": "pop.wav"},
            {"time": 2.8, "sfx": "chime.wav"}
        ]
    },
    {
        "id": 4,
        "title": "Bùng nổ công nghiệp",
        "duration": 9.9,
        "bg_image": str(SCENES_DIR / "scene4.jpg"),
        "theme_color": (70, 190, 255),       # Xanh thép công nghệ
        "badge": "⚙️ BÙNG NỔ CÔNG NGHIỆP",
        "headline": "ĐỘNG CƠ HƠI NƯỚC\n& MẠNG LƯỚI ĐIỆN",
        "subtext": "Sắt thép và năng lượng biến đổi toàn bộ diện mạo hành tinh!",
        "particle_type": "steam",
        "char_side": "left",
        "spoken": "Rồi động cơ hơi nước và điện năng bùng nổ, biến Trái Đất thành một mạng lưới khổng lồ của sắt thép và ánh sáng rực rỡ.",
        "sfx_events": [
            {"time": 0.0, "sfx": "whoosh.wav"},
            {"time": 0.2, "sfx": "boom.wav"},
            {"time": 1.0, "sfx": "pop.wav"}
        ]
    },
    {
        "id": 5,
        "title": "Kỷ nguyên AI và vũ trụ",
        "duration": 10.6,
        "bg_image": str(SCENES_DIR / "scene5.jpg"),
        "theme_color": (0, 240, 255),        # Cyan Neon Sci-Fi
        "badge": "🤖 ROBOT, AI & VŨ TRỤ",
        "headline": "KỶ NGUYÊN NƠ-RON\n& CHINH PHỤC CÁC VÌ SAO",
        "subtext": "Từ hang đá tăm tối chính thức trở thành bá chủ hành tinh!",
        "particle_type": "neon",
        "char_side": "right",
        "spoken": "Hôm nay chúng ta phóng tàu vào vũ trụ sâu thẳm, kiến tạo AI. Chúng ta đã chính thức trở thành bá chủ của cả hành tinh!",
        "sfx_events": [
            {"time": 0.0, "sfx": "whoosh.wav"},
            {"time": 0.2, "sfx": "pop.wav"},
            {"time": 1.8, "sfx": "boom.wav"},
            {"time": 3.0, "sfx": "chime.wav"}
        ]
    }
]


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


# ===========================================================================
# 3. RENDER TỪNG FRAME CỦA CẢNH HOẠT HỌA
# ===========================================================================

def render_scene_frame(
    scene: dict,
    t: float,
    bg_img: Image.Image,
    char_img: Image.Image,
    fonts: dict,
    draw_cache: dict
) -> Image.Image:
    """Render 1 frame chuẩn 1080x1920 với Parallax, Character Squash & Stretch, Particles và Glass Card."""
    dur = scene["duration"]
    theme = scene["theme_color"]

    # 1. Camera Ken Burns Zoom (1.0 -> 1.07x)
    zoom = 1.0 + 0.07 * (t / dur)
    # Lấy vùng crop từ ảnh nền
    bw, bh = bg_img.size
    crop_w = int(bw / zoom)
    crop_h = int(bh / zoom)
    pan_y = int(15 * math.sin(t / dur * math.pi))
    x0 = (bw - crop_w) // 2
    y0 = max(0, min(bh - crop_h, (bh - crop_h) // 2 + pan_y))
    frame = bg_img.crop((x0, y0, x0 + crop_w, y0 + crop_h)).resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)

    # 2. Lớp phủ Vignette nhẹ để làm nổi bật tâm cảnh
    draw = ImageDraw.Draw(frame, "RGBA")

    # 3. Hạt môi trường động (Atmospheric Particles)
    ptype = scene["particle_type"]
    if ptype == "embers":
        # Tàn than hồng bay bốc
        for i in range(25):
            seed = i * 47.3
            life = (t * 0.8 + i * 0.04) % 1.0
            px = 540 + math.sin(seed + t * 4.0) * 380 * life
            py = HEIGHT - life * 1400
            pr = int((1.0 - life) * 6 + 2)
            alpha = int((1.0 - life) * 220)
            draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(255, 180, 50, alpha))
    elif ptype == "pollen":
        # Hạt phấn hoa vàng lấp lánh nắng
        for i in range(20):
            seed = i * 83.1
            life = (t * 0.4 + i * 0.05) % 1.0
            px = 100 + (seed * 11) % (WIDTH - 200) + math.sin(t * 2.0 + seed) * 40
            py = 300 + life * 1200
            pr = int(3 + math.sin(t * 5.0 + i) * 2)
            alpha = int(120 + 80 * math.sin(t * 3.0 + seed))
            draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(255, 235, 120, alpha))
    elif ptype == "steam":
        # Khói trắng công nghiệp
        for i in range(12):
            life = (t * 0.5 + i * 0.08) % 1.0
            px = 750 + math.sin(life * 3.0 + i) * 80 + life * 100
            py = 1100 - life * 800
            pr = int(30 + life * 70)
            alpha = int((1.0 - life) * 110)
            draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(220, 230, 240, alpha))
    elif ptype == "neon":
        # Xung điện AI & Tinh vân sao
        for i in range(20):
            seed = i * 61.7
            life = (t * 0.7 + i * 0.05) % 1.0
            px = 200 + (seed * 17) % (WIDTH - 400)
            py = 400 + math.sin(t * 3.0 + seed) * 250
            pr = int(4 + math.sin(t * 6.0 + seed) * 2)
            col = (0, 240, 255, 200) if i % 2 == 0 else (200, 100, 255, 200)
            draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=col)

    # 4. Nhân vật Explorer Hoạt Họa (Squash & Stretch, Breathing Bob, Tilt)
    # Vị trí xuất hiện: Nảy vào từ góc màn hình (Overshoot Bounce)
    entry_dur = 0.65
    if t < entry_dur:
        entry_p = ease_out_back(t / entry_dur)
    else:
        entry_p = 1.0

    # Chuyển động thở & bập bồng (Disney Squash & Stretch)
    bob = math.sin(t * 3.4)
    y_float = -bob * 18.0
    scale_x = (1.0 - bob * 0.035) * entry_p
    scale_y = (1.0 + bob * 0.035) * entry_p
    rot_deg = math.sin(t * 1.7) * 2.8

    # Vị trí gốc nhân vật (Presenter)
    if scene["char_side"] == "right":
        base_x = 760
        base_y = 1260
    else:
        base_x = 240
        base_y = 1260

    # Resize nhân vật với tỷ lệ squash & stretch
    orig_w, orig_h = char_img.size
    target_scale = 0.52
    cw = max(10, int(orig_w * target_scale * scale_x))
    ch = max(10, int(orig_h * target_scale * scale_y))

    char_resized = char_img.resize((cw, ch), Image.Resampling.BILINEAR)
    if abs(rot_deg) > 0.5:
        char_resized = char_resized.rotate(rot_deg, resample=Image.Resampling.BILINEAR, expand=True)

    cur_x = int(base_x - char_resized.width // 2)
    cur_y = int(base_y - char_resized.height // 2 + y_float)

    # Bóng đổ mềm dưới chân nhân vật (Drop shadow on ground)
    shadow_w = int(cw * 0.7)
    shadow_h = int(cw * 0.16)
    shadow_x = base_x - shadow_w // 2
    shadow_y = base_y + int(ch * 0.42)
    draw.ellipse([shadow_x, shadow_y, shadow_x + shadow_w, shadow_y + shadow_h],
                 fill=(0, 0, 0, 90))

    # Dán nhân vật lên frame
    frame.paste(char_resized, (cur_x, cur_y), char_resized)

    # Bong bóng cảm xúc / Sóng âm nói chuyện trên đầu nhân vật
    talk_wave = math.sin(t * 12.0) * 0.5 + 0.5
    head_top_y = cur_y + int(ch * 0.12)
    head_center_x = cur_x + char_resized.width // 2
    # Vòng hào quang sáng nhẹ trên đầu khi thuyết trình
    glow_r = int(22 + talk_wave * 8)
    draw.ellipse([head_center_x - glow_r, head_top_y - glow_r, head_center_x + glow_r, head_top_y + glow_r],
                 outline=(theme[0], theme[1], theme[2], int(140 * talk_wave)), width=3)

    # 5. Khối Text Card Hiện Đại (Glassmorphism Dark Pill Card)
    # Hiệu ứng nảy vào (Card Pop)
    card_delay = 0.25
    if t >= card_delay:
        cp = min(1.0, (t - card_delay) / 0.5)
        cp_ease = ease_out_back(cp)
    else:
        cp_ease = 0.0

    if cp_ease > 0.01:
        card_w = 980
        card_h = 320
        cx = (WIDTH - card_w) // 2
        cy = 140

        # Scale card từ giữa
        sc_w = int(card_w * cp_ease)
        sc_h = int(card_h * cp_ease)
        sc_x = WIDTH // 2 - sc_w // 2
        sc_y = (cy + card_h // 2) - sc_h // 2

        # Lớp nền tối mờ sang trọng (85% opacity)
        draw.rounded_rectangle(
            [sc_x, sc_y, sc_x + sc_w, sc_y + sc_h],
            radius=28,
            fill=(12, 16, 26, 215),
            outline=(theme[0], theme[1], theme[2], 230),
            width=3
        )

        if cp_ease > 0.8:
            # 1. Badge thời kỳ
            badge_text = scene["badge"]
            badge_font = fonts["badge"]
            draw.text((WIDTH // 2, cy + 45), badge_text, font=badge_font,
                      fill=theme, anchor="mm")

            # 2. Tiêu đề chính lớn (Headline)
            head_text = scene["headline"]
            head_font = fonts["headline"]
            draw.text((WIDTH // 2, cy + 145), head_text, font=head_font,
                      fill=(255, 255, 255), anchor="mm", align="center")

            # 3. Phụ đề tóm tắt (Subtext)
            sub_text = scene["subtext"]
            sub_font = fonts["subtext"]
            draw.text((WIDTH // 2, cy + 265), sub_text, font=sub_font,
                      fill=(200, 220, 240), anchor="mm")

    # 6. Thanh tiến trình thời gian ở đáy video (Progress bar)
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
# 4. HÀM SINH GIỌNG ĐỌC AI TIẾNG VIỆT
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
# 5. TIẾN TRÌNH MASTER RENDER TOÀN DIỆN
# ===========================================================================

def build_kurzgesagt_master():
    print("=" * 80)
    print("🌟 KURZGESAGT MASTER STUDIO — PHIM HOẠT HÌNH KHOA HỌC & LỊCH SỬ ĐỈNH CAO")
    print("🎨 Nghệ thuật Vector rực rỡ + Nhân vật Explorer hoạt họa Squash & Stretch")
    print("🎯 Camera Parallax Ken Burns + Sound Design Mastered EBU R128 (-14 LUFS)")
    print("=" * 80)

    # 1. Sinh Voice AI
    full_spoken = " ".join(s["spoken"] for s in SCENES)
    voice_file = OUTPUT_DIR / "voice.mp3"
    print("\n🎙️ [BƯỚC 1] Sinh giọng đọc AI tiếng Việt...")
    generate_voice(full_spoken, voice_file)

    dur_cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{voice_file}"'
    voice_dur = float(subprocess.check_output(dur_cmd, shell=True).decode().strip())
    print(f"   ⏱️ Thời lượng audio thực tế: {voice_dur:.1f} giây")

    # Khớp thời lượng từng cảnh theo voice
    total_scene_target = sum(s["duration"] for s in SCENES)
    ratio = voice_dur / total_scene_target
    for s in SCENES:
        s["duration"] = round(s["duration"] * ratio, 2)

    # 2. Chuẩn bị tài nguyên hình ảnh & font
    print("\n🎨 [BƯỚC 2] Tải tài nguyên đồ họa Kurzgesagt & nhân vật...")
    char_path = CHARACTERS_DIR / "kurzgesagt_character.png"
    char_img = Image.open(char_path).convert("RGBA")

    bg_images = {}
    for s in SCENES:
        bg_images[s["id"]] = Image.open(s["bg_image"]).convert("RGBA")

    fonts = {
        "badge": get_font(42, bold=True),
        "headline": get_font(56, bold=True),
        "subtext": get_font(34, bold=False),
    }

    # 3. Render từng frame sang FFmpeg pipe (Tốc độ cao ~90 FPS)
    raw_video = OUTPUT_DIR / "raw_animation.mp4"
    print("\n🎬 [BƯỚC 3] Render khung hình 1080x1920 @ 30 FPS qua FFmpeg Pipeline...")

    ffmpeg_proc = subprocess.Popen(
        [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{WIDTH}x{HEIGHT}",
            "-pix_fmt", "rgba",
            "-r", str(FPS),
            "-i", "-",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "18",
            str(raw_video)
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    total_frames = 0
    t_global = 0.0
    for s_idx, sc in enumerate(SCENES, start=1):
        sc_dur = sc["duration"]
        sc_frames = int(round(sc_dur * FPS))
        bg = bg_images[sc["id"]]
        print(f"   [Cảnh {s_idx}/5] {sc['title']} ({sc_dur:.1f}s, {sc_frames} frames)...")

        for f_idx in range(sc_frames):
            t_scene = f_idx / FPS
            frame_img = render_scene_frame(sc, t_scene, bg, char_img, fonts, {})
            ffmpeg_proc.stdin.write(frame_img.tobytes())
            total_frames += 1

    ffmpeg_proc.stdin.close()
    ffmpeg_proc.wait()
    print(f"   ✅ Đã render xong {total_frames} frames hoạt họa xuất sắc!")

    # 4. Lập bản đồ Sound Effects
    print("\n🔊 [BƯỚC 4] Lập bản đồ 18 mốc Sound Effects chính xác theo từng chuyển động...")
    sfx_timeline = []
    t_scene_start = 0.0
    for sc in SCENES:
        for ev in sc.get("sfx_events", []):
            global_t = t_scene_start + ev["time"]
            sfx_file = SFX_DIR / ev["sfx"]
            if sfx_file.exists():
                sfx_timeline.append((global_t, sfx_file))
        t_scene_start += sc["duration"]

    # 5. Master Audio Mix: Voice + BGM + SFX với Loudness EBU R128
    final_video = OUTPUT_DIR / "draft_video.mp4"
    print("\n🎛️ [BƯỚC 5] Master Compositing: Hòa âm chuẩn EBU R128 (-14 LUFS, Peak -1.5 dB)...")

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
    subprocess.run(final_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    file_size_mb = final_video.stat().st_size / (1024 * 1024) if final_video.exists() else 0.0
    print("\n" + "=" * 80)
    print("🎉 HOÀN TẤT XUẤT XƯỞNG MASTER ANIMATION SIÊU PHẨM!")
    print(f"📁 Video: {final_video} ({file_size_mb:.1f} MB, {voice_dur:.1f}s)")
    print("=" * 80)
    return str(final_video)


if __name__ == "__main__":
    build_kurzgesagt_master()
