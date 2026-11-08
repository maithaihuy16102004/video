"""Tạo thumbnail (ảnh bìa) tự động cho video — phong cách YouTube/TikTok.

Tái sử dụng bộ vẽ của charmotion (nhân vật + nền gradient + text tiếng Việt
có dấu) để sinh ảnh bìa 1280x720 (16:9) hoặc 1080x1920 (9:16) với:
  - nền gradient theo chủ đề (dark / red / gold / blue)
  - nhân vật hoạt hình ở góc
  - tiêu đề lớn (tự wrap, có bóng đổ + viền)
  - badge nhãn (vd "KINH TẾ", "PHẦN 1")

Dùng:
    python thumbnail.py --title "Kinh tế thị trường là gì?" \
        --subtitle "Giải thích trong 60 giây" --badge "KINH TẾ" \
        --theme gold --size horizontal -o output/thumb.jpg
"""

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
CHAR_SRC = BASE.parent / "charmotion" / "src"
sys.path.insert(0, str(CHAR_SRC))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

from character import draw_character, default_colors  # noqa: E402
from text import draw_text_centered, load_font, text_size, wrap_text  # noqa: E402
from motion import draw_gradient, draw_tech_grid, draw_dots  # noqa: E402


# bảng màu theo theme: (top, bottom, accent, text_color)
THEMES = {
    "dark":  ((24, 30, 52), (6, 10, 24), (255, 200, 60), (255, 255, 255)),
    "gold":  ((58, 40, 10), (20, 14, 4),  (255, 196, 40), (255, 248, 225)),
    "red":   ((70, 14, 14), (24, 4, 6),   (255, 90, 70),  (255, 245, 240)),
    "blue":  ((12, 40, 72), (4, 14, 30),  (80, 180, 255), (240, 248, 255)),
    "green": ((10, 52, 40), (4, 20, 16),  (90, 224, 160), (240, 255, 248)),
}

SIZES = {
    "horizontal": (1280, 720),   # YouTube thumbnail chuẩn
    "vertical": (1080, 1920),    # TikTok/Shorts cover
    "square": (1080, 1080),
}


def _draw_badge(draw, text, x, y, accent, fg=(20, 20, 25), pad_x=22, pad_y=10,
                font_size=38):
    font = load_font(font_size, bold=True)
    bw, bh = text_size(draw, text, font)
    box = [x, y, x + bw + pad_x * 2, y + bh + pad_y * 2]
    draw.rounded_rectangle(box, radius=(bh + pad_y * 2) // 2, fill=accent)
    draw.text((x + pad_x, y + pad_y - bh * 0.08), text, font=font, fill=fg)
    return box


def _draw_title(draw, text, cx, top, max_width, accent, fg, base_size=92):
    """Vẽ tiêu đề lớn, tự co font cho vừa max_width."""
    size = base_size
    while size > 40:
        font = load_font(size, bold=True)
        lines = wrap_text(draw, text, font, max_width)
        if len(lines) <= 3:
            # vẽ có viền đen + bóng đổ
            line_h = int(size * 1.18)
            y = top
            for ln in lines:
                # viền (stroke) bằng cách vẽ lệch nhiều hướng
                w, h = text_size(draw, ln, font)
                x = cx - w / 2
                for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3),
                               (-2, -2), (2, -2), (-2, 2), (2, 2)):
                    draw.text((x + dx, y + dy), ln, font=font, fill=(0, 0, 0))
                draw.text((x + 5, y + 6), ln, font=font, fill=(0, 0, 0))
                draw.text((x, y), ln, font=font, fill=fg)
                y += line_h
            return y
        size -= 6
    return top


def make_thumbnail(title, subtitle=None, badge=None, theme="dark",
                   size="horizontal", out_path=None, character=True,
                   url=None) -> str:
    w, h = SIZES.get(size, SIZES["horizontal"])
    top_c, bot_c, accent, fg = THEMES.get(theme, THEMES["dark"])

    img = Image.new("RGB", (w, h), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # nền gradient + lưới tech mờ
    draw_gradient(draw, w, h, top_c, bot_c)
    grid_col = tuple(min(255, c + 40) for c in bot_c)
    draw_tech_grid(draw, w, h, grid_col, spacing=max(60, w // 18))
    draw_dots(draw, w, h, (255, 255, 255), spacing=max(48, w // 22), radius=2)

    # dải accent dưới đáy
    bar_h = int(h * 0.045)
    draw.rectangle([0, h - bar_h, w, h], fill=accent)

    # nhân vật bên phải
    if character:
        cx = int(w * 0.78)
        cy = int(h * 0.60)
        scale = int(h * 0.17)
        draw_character(draw, cx, cy, scale=scale, pose="excited",
                       expression="excited", talking=0.0, arm_swing=0.15,
                       colors=default_colors())

    # badge
    y_cursor = int(h * 0.10)
    if badge:
        _draw_badge(draw, badge.upper(), int(w * 0.07), y_cursor,
                    accent, font_size=int(h * 0.052))
        y_cursor += int(h * 0.052) * 2 + 34

    # tiêu đề (chiếm 55% bề ngang nếu có nhân vật)
    title_cx = int(w * (0.34 if character else 0.5))
    title_max = int(w * (0.55 if character else 0.86))
    y_cursor = _draw_title(draw, title, title_cx, y_cursor, title_max,
                           accent, fg, base_size=int(h * 0.135))

    # subtitle
    if subtitle:
        sfont = load_font(int(h * 0.045))
        draw_text_centered(draw, subtitle, title_cx, y_cursor + int(h * 0.05),
                           sfont, accent, max_width=title_max, line_spacing=1.25)

    if out_path is None:
        out_path = BASE / "output" / "thumbnail.jpg"
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)
    return str(out)


def main():
    ap = argparse.ArgumentParser(description="Tạo thumbnail tự động")
    ap.add_argument("--title", required=True, help="tiêu đề lớn trên ảnh")
    ap.add_argument("--subtitle", help="dòng phụ (tùy chọn)")
    ap.add_argument("--badge", help="nhãn dán góc trên (vd KINH TẾ)")
    ap.add_argument("--theme", default="dark",
                    choices=list(THEMES), help="bảng màu")
    ap.add_argument("--size", default="horizontal",
                    choices=list(SIZES), help="khổ ảnh")
    ap.add_argument("--no-character", action="store_true",
                    help="không vẽ nhân vật")
    ap.add_argument("-o", "--output", default="output/thumbnail.jpg")
    args = ap.parse_args()

    if not Path(args.output).is_absolute():
        args.output = str(BASE / args.output)

    out = make_thumbnail(args.title, subtitle=args.subtitle, badge=args.badge,
                         theme=args.theme, size=args.size,
                         out_path=args.output,
                         character=not args.no_character)
    print(f"[thumbnail] xong -> {out}")


if __name__ == "__main__":
    main()
