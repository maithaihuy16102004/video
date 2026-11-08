"""Render text tiếng Việt với wrap + căn giữa, dùng font có dấu tiếng Việt."""

from pathlib import Path
from PIL import ImageFont


def _find_font(bold=False):
    candidates = []
    if bold:
        candidates = [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
    else:
        candidates = [
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
    for f in candidates:
        if Path(f).exists():
            return f
    return None


def load_font(size, bold=False):
    path = _find_font(bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(draw, text, font, max_width):
    """Ngắt dòng text cho vừa max_width. Trả list các dòng."""
    words = text.split(" ")
    lines = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        w_, _ = text_size(draw, trial, font)
        if w_ <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_text_centered(draw, text, cx, cy, font, fill, max_width=None,
                       line_spacing=1.2, shadow=True, shadow_color=(0, 0, 0),
                       shadow_offset=3):
    """Vẽ text căn giữa tại (cx, cy) — hỗ trợ nhiều dòng + bóng đổ."""
    if max_width:
        lines = wrap_text(draw, text, font, max_width)
    else:
        lines = text.split("\n")

    line_h = int(font.size * line_spacing)
    total_h = line_h * len(lines)
    y = cy - total_h / 2 + line_h / 2

    for ln in lines:
        w, h = text_size(draw, ln, font)
        x = cx - w / 2
        if shadow:
            draw.text((x + shadow_offset, y + shadow_offset), ln,
                      font=font, fill=shadow_color)
        draw.text((x, y), ln, font=font, fill=fill)
        y += line_h
    return total_h
