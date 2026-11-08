"""Motion graphics: nền động, hình khối động, kinetic typography, hiệu ứng chuyển cảnh."""

import math
from PIL import Image, ImageDraw

from easing import ease, clamp, lerp
from text import load_font, text_size, wrap_text


# ---------------- Nền (background) ----------------

def draw_gradient(draw, w, h, top, bottom):
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(lerp(top[0], bottom[0], t))
        g = int(lerp(top[1], bottom[1], t))
        b = int(lerp(top[2], bottom[2], t))
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def draw_tech_grid(draw, w, h, color=(40, 120, 200), spacing=48):
    for x in range(0, w, spacing):
        draw.line([(x, 0), (x, h)], fill=color, width=1)
    for y in range(0, h, spacing):
        draw.line([(0, y), (w, y)], fill=color, width=1)


def draw_dots(draw, w, h, color=(255, 255, 255), spacing=40, radius=2):
    for x in range(spacing // 2, w, spacing):
        for y in range(spacing // 2, h, spacing):
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)


# ---------------- Hình khối động ----------------

def draw_progress_bar(draw, x, y, w, h, progress, fill, bg=(255, 255, 255)):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=bg)
    pw = int(w * clamp(progress, 0, 1))
    if pw > 0:
        draw.rounded_rectangle([x, y, x + pw, y + h], radius=h // 2, fill=fill)


def draw_circle_ring(draw, cx, cy, radius, progress, fill, width=10, bg=(255, 255, 255)):
    draw.arc([cx - radius, cy - radius, cx + radius, cy + radius],
             0, 360, fill=bg, width=width)
    end = -90 + int(360 * clamp(progress, 0, 1))
    draw.arc([cx - radius, cy - radius, cx + radius, cy + radius],
             -90, end, fill=fill, width=width)


def draw_arrow(draw, p1, p2, fill, width=6, head=16):
    draw.line([p1, p2], fill=fill, width=width)
    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    for da in (math.radians(150), math.radians(-150)):
        hx = p2[0] + head * math.cos(ang + da)
        hy = p2[1] + head * math.sin(ang + da)
        draw.line([p2, (hx, hy)], fill=fill, width=width)


def draw_icon_star(draw, cx, cy, r, fill, rot=0.0):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5 + rot
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    draw.polygon(pts, fill=fill)


def draw_icon_heart(draw, cx, cy, size, fill):
    s = size
    draw.polygon([
        (cx, cy + s * 0.9),
        (cx - s, cy - s * 0.1),
        (cx - s * 0.5, cy - s * 0.7),
        (cx, cy - s * 0.2),
        (cx + s * 0.5, cy - s * 0.7),
        (cx + s, cy - s * 0.1),
    ], fill=fill)


def draw_icon_lightbulb(draw, cx, cy, r, fill):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r * 0.6], fill=fill)
    draw.rectangle([cx - r * 0.3, cy + r * 0.4, cx + r * 0.3, cy + r * 0.8], fill=fill)
    for k in range(6):
        a = k * math.pi / 3
        ex = cx + r * 1.5 * math.cos(a)
        ey = cy + r * 1.2 * math.sin(a)
        draw.line([(cx + r * math.cos(a), cy + r * math.sin(a)), (ex, ey)],
                  fill=fill, width=3)


# ---------------- Kinetic typography ----------------

def render_text_layer(text, font, fill, max_width=None, shadow=True,
                      shadow_color=(0, 0, 0, 255), stroke=0, stroke_fill=(0, 0, 0, 255)):
    """Render khối text ra ảnh RGBA riêng (để scale/fade/move tự do)."""
    if max_width:
        lines = wrap_text_measure(text, font, max_width)
    else:
        lines = text.split("\n")

    line_h = int(font.size * 1.25)
    max_lw = 0
    for ln in lines:
        w, _ = _measure(ln, font)
        max_lw = max(max_lw, w)

    pad = 30
    total_h = line_h * len(lines)
    img = Image.new("RGBA", (max_lw + pad * 2, total_h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = pad
    for ln in lines:
        w, _ = _measure(ln, font)
        x = (img.width - w) / 2
        if stroke:
            d.text((x, y), ln, font=font, fill=stroke_fill, stroke_width=stroke)
        if shadow:
            d.text((x + 3, y + 3), ln, font=font, fill=shadow_color)
        d.text((x, y), ln, font=font, fill=fill)
        y += line_h
    return img


def _measure(text, font):
    from PIL import ImageDraw, Image
    tmp = Image.new("RGBA", (10, 10))
    d = ImageDraw.Draw(tmp)
    bbox = d.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text_measure(text, font, max_width):
    words = text.split(" ")
    lines = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        w_, _ = _measure(trial, font)
        if w_ <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def apply_kinetic(layer, effect, t):
    """Áp hiệu ứng chuyển động lên text layer. Trả (layer, offset_x, offset_y)."""
    t = clamp(t, 0, 1)
    ox, oy = 0, 0
    scale = 1.0
    alpha = 1.0

    if effect == "fade":
        alpha = ease("linear", t)
    elif effect == "pop":
        scale = ease("out_back", t)
        alpha = ease("out_cubic", t)
    elif effect == "scale":
        scale = ease("out_back", t)
    elif effect == "slide_left":
        ox = int(lerp(-layer.width, 0, ease("out_cubic", t)))
    elif effect == "slide_right":
        ox = int(lerp(layer.width, 0, ease("out_cubic", t)))
    elif effect == "slide_up":
        oy = int(lerp(300, 0, ease("out_cubic", t)))
    elif effect == "bounce":
        oy = int(lerp(-300, 0, ease("out_bounce", t)))
    elif effect == "typewriter":
        # cắt nội dung theo t (xử lý ở lớp trên)
        pass
    else:
        pass

    if scale != 1.0:
        nw = max(1, int(layer.width * scale))
        nh = max(1, int(layer.height * scale))
        layer = layer.resize((nw, nh))

    if alpha < 1.0:
        # giảm alpha bằng putalpha
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer.putalpha(a)

    return layer, ox, oy
