"""
Manim VFX Bridge — Render các hiệu ứng VFX bằng Manim Community Edition
Tạo ra các overlay animation MP4 trong suốt (alpha) hoặc dạng thư mục ảnh PNG để ghép.

Các loại VFX:
  - kinetic_title: Tiêu đề xuất hiện phát sáng với glow effect
  - timeline_bar: Thanh tiến trình lịch sử trượt vào
  - data_reveal: Con số/dữ liệu đếm lên từ 0
  - impact_flash: Flash trắng + zoom shock khi sự kiện lớn xảy ra
  - particle_rise: Các hạt sáng bay lên từ dưới
  - wave_text: Chữ gợn sóng (wave propagation)
"""

import os
import sys
import subprocess
import tempfile
import hashlib
import json
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

AGENT_ROOT = Path(__file__).resolve().parent.parent.parent
MANIM_CACHE_DIR = AGENT_ROOT / "ai-engine" / "manim" / "vfx_cache"
MANIM_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Kiểm tra Manim có sẵn không
def _manim_available() -> bool:
    result = subprocess.run(["python", "-m", "manim", "--version"], capture_output=True, timeout=10)
    return result.returncode == 0


# -------------------------------------------------------------------------
# ĐỊNH NGHĨA CÁC SCENE MANIM VFX (tự generate Python code rồi render)
# -------------------------------------------------------------------------

MANIM_SCENES = {
    "kinetic_title": '''
from manim import *

class KineticTitleScene(Scene):
    CONFIG_TITLE = "{title}"
    CONFIG_SUBTITLE = "{subtitle}"
    CONFIG_COLOR = "{color}"
    
    def construct(self):
        self.camera.background_color = BLACK
        
        title = Text(self.CONFIG_TITLE, font_size=64, color=self.CONFIG_COLOR,
                     weight=BOLD).scale(0.8)
        subtitle = Text(self.CONFIG_SUBTITLE, font_size=28, color=LIGHT_GREY).scale(0.7)
        subtitle.next_to(title, DOWN, buff=0.3)
        
        # Hiệu ứng glow (nhân bản mờ)
        glow = title.copy().set_opacity(0.3).scale(1.08)
        
        # Animation
        self.play(
            FadeIn(glow, scale=0.5),
            Write(title, run_time=1.2),
        )
        self.play(FadeIn(subtitle, shift=UP*0.3), run_time=0.8)
        self.wait(1.5)
        self.play(FadeOut(VGroup(title, subtitle, glow), shift=UP*0.5))
''',

    "timeline_bar": '''
from manim import *

class TimelineBarScene(Scene):
    CONFIG_EVENTS = {events_json}
    CONFIG_COLOR = "{color}"
    
    def construct(self):
        self.camera.background_color = "#0a0a0a"
        
        # Vẽ trục thời gian
        line = Line(LEFT*5.5, RIGHT*5.5, color=GREY, stroke_width=3)
        self.play(Create(line))
        
        events = self.CONFIG_EVENTS
        total = len(events)
        for i, evt in enumerate(events):
            x = -5 + i * (10 / max(1, total - 1))
            dot = Dot([x, 0, 0], color=self.CONFIG_COLOR, radius=0.12)
            label = Text(evt["label"], font_size=22, color=WHITE).scale(0.65)
            label.next_to(dot, UP if i % 2 == 0 else DOWN, buff=0.2)
            year = Text(evt["year"], font_size=18, color=GREY_B).scale(0.55)
            year.next_to(dot, DOWN if i % 2 == 0 else UP, buff=0.1)
            self.play(
                GrowFromCenter(dot),
                Write(label),
                Write(year),
                run_time=0.5,
            )
        self.wait(1.5)
''',

    "data_reveal": '''
from manim import *

class DataRevealScene(Scene):
    CONFIG_NUMBER = {number}
    CONFIG_LABEL = "{label}"
    CONFIG_UNIT = "{unit}"
    CONFIG_COLOR = "{color}"
    
    def construct(self):
        self.camera.background_color = BLACK
        
        label_txt = Text(self.CONFIG_LABEL, font_size=36, color=LIGHT_GREY)
        label_txt.to_edge(UP, buff=1)
        
        num_str = f"{{self.CONFIG_NUMBER:,}}"
        num_display = Text(num_str, font_size=72, color=self.CONFIG_COLOR, weight=BOLD)
        unit_txt = Text(self.CONFIG_UNIT, font_size=36, color=self.CONFIG_COLOR)
        unit_txt.next_to(num_display, RIGHT, buff=0.2)
        group = VGroup(num_display, unit_txt)
        group.move_to(ORIGIN)
        
        self.add(label_txt)
        self.play(
            GrowFromCenter(group, run_time=1.5),
        )
        self.wait(1.5)
''',

    "impact_flash": '''
from manim import *

class ImpactFlashScene(Scene):
    CONFIG_TEXT = "{text}"
    CONFIG_COLOR = "{color}"
    
    def construct(self):
        self.camera.background_color = BLACK
        
        # Flash trắng
        flash_rect = Rectangle(
            width=16, height=9, fill_color=WHITE, fill_opacity=1
        ).set_stroke(width=0)
        
        # Text cú đấm
        impact = Text(self.CONFIG_TEXT, font_size=72, color=self.CONFIG_COLOR,
                      weight=BOLD)
        
        self.play(FadeIn(flash_rect, run_time=0.08))
        self.play(FadeOut(flash_rect, run_time=0.3))
        self.play(
            GrowFromCenter(impact, run_time=0.5),
        )
        self.play(impact.animate.scale(1.15).set_opacity(0.6), run_time=0.4)
        self.wait(1.0)
        self.play(FadeOut(impact))
''',

    "particle_rise": '''
from manim import *
import random

class ParticleRiseScene(Scene):
    CONFIG_COLOR = "{color}"
    
    def construct(self):
        self.camera.background_color = BLACK
        
        dots = VGroup()
        anims = []
        for _ in range(60):
            x = random.uniform(-6, 6)
            y_start = random.uniform(-4, -2)
            y_end = random.uniform(2, 5)
            size = random.uniform(0.03, 0.12)
            d = Dot([x, y_start, 0], radius=size, color=self.CONFIG_COLOR)
            d.set_opacity(random.uniform(0.4, 1.0))
            dots.add(d)
            anims.append(d.animate(run_time=random.uniform(1.5, 3.0)).move_to([x, y_end, 0]).set_opacity(0))
        
        self.add(dots)
        self.play(*anims, lag_ratio=0.03)
        self.wait(0.5)
''',
}


def _get_cache_key(vfx_type: str, params: dict) -> str:
    h = hashlib.md5(f"{vfx_type}:{json.dumps(params, sort_keys=True)}".encode()).hexdigest()[:10]
    return h


def render_vfx(
    vfx_type: str,
    params: dict | None = None,
    out_path: str | Path | None = None,
    quality: str = "l",  # "l"=480p15, "m"=720p30, "h"=1080p60
) -> str | None:
    """
    Render một đoạn VFX Manim và trả về đường dẫn file MP4.

    Args:
        vfx_type: Loại VFX (xem MANIM_SCENES)
        params: Tham số cho template scene
        out_path: Đường dẫn đầu ra. None → cache tự động.
        quality: "l" (nhanh), "m" (cân bằng), "h" (cao nhất)

    Returns:
        Đường dẫn file MP4 hoặc None nếu Manim không khả dụng.
    """
    if vfx_type not in MANIM_SCENES:
        print(f"⚠️  VFX type không nhận ra: {vfx_type}. Có thể dùng: {list(MANIM_SCENES.keys())}")
        return None

    if not _manim_available():
        print("⚠️  Manim chưa cài. Bỏ qua VFX overlay.")
        return None

    params = params or {}

    # Điền tham số vào template
    defaults = {
        "title": "Khám Phá Lịch Sử",
        "subtitle": "Hành trình vĩ đại của loài người",
        "color": "#FFD700",
        "events_json": '[{"label": "Khởi đầu", "year": "300.000 TCN"}, {"label": "Ngày nay", "year": "2024"}]',
        "number": 8000000000,
        "label": "Dân số thế giới",
        "unit": " người",
        "text": "BƯỚC NGOẶT!",
    }
    defaults.update(params)
    
    # Render events_json đúng kiểu JSON
    if "events" in defaults and isinstance(defaults["events"], list):
        defaults["events_json"] = json.dumps(defaults["events"], ensure_ascii=False)

    scene_code = MANIM_SCENES[vfx_type].format(**defaults)

    # Cache key
    cache_key = _get_cache_key(vfx_type, defaults)
    cache_dir = MANIM_CACHE_DIR / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Tên class trong code
    class_map = {
        "kinetic_title": "KineticTitleScene",
        "timeline_bar": "TimelineBarScene",
        "data_reveal": "DataRevealScene",
        "impact_flash": "ImpactFlashScene",
        "particle_rise": "ParticleRiseScene",
    }
    class_name = class_map[vfx_type]

    # Ghi file tạm Python
    script_file = cache_dir / f"{vfx_type}.py"
    script_file.write_text(scene_code, encoding="utf-8")

    # Render với Manim
    quality_map = {"l": "480p15", "m": "720p30", "h": "1080p60"}
    q_flag = {"l": "-ql", "m": "-qm", "h": "-qh"}.get(quality, "-ql")

    cmd = f'python -m manim {q_flag} "{script_file}" {class_name} --media_dir "{cache_dir}"'
    print(f"   🎨 Manim VFX '{vfx_type}': Đang render...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")

    # Tìm file MP4 được tạo ra
    mp4_files = list(cache_dir.rglob("*.mp4"))
    if not mp4_files:
        print(f"   ⚠️  Manim render thất bại: {result.stderr[-200:]}")
        return None

    rendered = max(mp4_files, key=lambda p: p.stat().st_mtime)

    # Copy sang out_path nếu được chỉ định
    if out_path:
        import shutil
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rendered, out_path)
        print(f"   ✅ VFX OK: {out_path.name}")
        return str(out_path)

    print(f"   ✅ VFX OK: {rendered.name}")
    return str(rendered)


def render_scene_vfx(scene: dict, out_dir: Path, scene_idx: int) -> str | None:
    """
    Chọn và render VFX phù hợp với nội dung một phân cảnh.

    Args:
        scene: Dict phân cảnh (title, spoken, epoch, ...)
        out_dir: Thư mục lưu file VFX
        scene_idx: Chỉ số phân cảnh

    Returns:
        Đường dẫn file MP4 VFX hoặc None
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    text = (scene.get("title", "") + " " + scene.get("spoken", "")).lower()
    out_mp4 = out_dir / f"vfx_scene_{scene_idx:02d}.mp4"

    # Quy tắc chọn VFX theo nội dung
    if scene_idx == 1 or any(k in text for k in ["mở đầu", "giới thiệu", "hook", "bắt đầu"]):
        return render_vfx("kinetic_title", {
            "title": scene.get("title", "Khám Phá"),
            "subtitle": scene.get("spoken", "")[:50],
            "color": "#FFD700",
        }, out_mp4)

    elif any(k in text for k in ["dân số", "con người", "tỷ", "triệu", "số lượng"]):
        # Tìm số trong nội dung
        import re
        nums = re.findall(r"\d+[\.,]?\d*", scene.get("spoken", ""))
        number = int(nums[0].replace(",", "").replace(".", "")) if nums else 8000000000
        return render_vfx("data_reveal", {
            "number": number,
            "label": scene.get("title", "Con số lịch sử"),
            "unit": " người",
            "color": "#00BFFF",
        }, out_mp4)

    elif any(k in text for k in ["chiến tranh", "bước ngoặt", "cách mạng", "đột phá", "khủng hoảng"]):
        return render_vfx("impact_flash", {
            "text": scene.get("title", "BƯỚC NGOẶT!")[:20].upper(),
            "color": "#FF4444",
        }, out_mp4)

    elif any(k in text for k in ["lịch sử", "thế kỷ", "timeline", "dòng thời gian", "tiến hoá"]):
        events = [
            {"label": "Khởi đầu", "year": "300.000 TCN"},
            {"label": "Nông nghiệp", "year": "10.000 TCN"},
            {"label": "Văn minh", "year": "3.000 TCN"},
            {"label": "Hiện đại", "year": "2024"},
        ]
        return render_vfx("timeline_bar", {"events": events, "color": "#FFD700"}, out_mp4)

    else:
        # Particle rise cho các cảnh chung
        return render_vfx("particle_rise", {"color": "#FFFFFF"}, out_mp4)


if __name__ == "__main__":
    # Test nhanh
    result = render_vfx("kinetic_title", {
        "title": "Lịch Sử Loài Người",
        "subtitle": "300.000 năm hành trình vĩ đại",
        "color": "#FFD700",
    })
    print(f"VFX output: {result}")
