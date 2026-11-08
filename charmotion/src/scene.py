"""Scene composer: định nghĩa cảnh + render từng frame thành PIL Image."""

import math
from PIL import Image, ImageDraw

from character import draw_character
from motion import (
    draw_gradient, draw_tech_grid, draw_dots,
    draw_progress_bar, draw_circle_ring, draw_arrow,
    draw_icon_star, draw_icon_heart, draw_icon_lightbulb,
    render_text_layer, apply_kinetic, wrap_text_measure,
)
from simulations import (
    draw_wheat_field, draw_fire_simulation, draw_industrial_gears,
    draw_futuristic_robot, draw_neural_network_brain, draw_space_rocket
)
from text import load_font


def _color(c, default=(255, 255, 255)):
    if c is None:
        return default
    return tuple(c)


def render_frame(scene, t_scene, t_global, width, height, fps, fonts_cache):
    """Render 1 frame của scene. t_scene = giây trong scene (0..duration)."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # ---- background ----
    bg = scene.get("background", {})
    _draw_background(draw, bg, width, height, t_scene)

    # ---- shapes (sau nền, trước text/character) ----
    for sh in scene.get("shapes", []):
        _draw_shape(draw, sh, width, height, t_scene)

    # ---- character ----
    ch = scene.get("character")
    if ch:
        _draw_character(draw, ch, width, height, t_scene, fps)

    # ---- texts (vẽ sau cùng) ----
    for tx in scene.get("texts", []):
        _draw_text(img, draw, tx, width, height, t_scene, fonts_cache)

    return img


def _draw_background(draw, bg, w, h, t):
    btype = bg.get("type", "gradient")
    if btype == "gradient":
        top = _color(bg.get("top"), (30, 40, 60))
        bottom = _color(bg.get("bottom"), (10, 15, 30))
        draw_gradient(draw, w, h, top, bottom)
    elif btype == "solid":
        draw.rectangle([0, 0, w, h], fill=_color(bg.get("color"), (20, 20, 30)))
    elif btype == "tech":
        top = _color(bg.get("top"), (20, 25, 45))
        bottom = _color(bg.get("bottom"), (5, 10, 25))
        draw_gradient(draw, w, h, top, bottom)
        grid_color = _color(bg.get("grid_color"), (60, 140, 220))
        draw_tech_grid(draw, w, h, grid_color, bg.get("spacing", 60))
        if bg.get("dots", True):
            draw_dots(draw, w, h, (255, 255, 255), 80, 2)
    else:
        draw.rectangle([0, 0, w, h], fill=(20, 20, 30))


def _draw_shape(draw, sh, w, h, t):
    stype = sh.get("type")
    # thời gian hiệu ứng của shape (delay + duration)
    delay = sh.get("delay", 0.0)
    dur = sh.get("duration", 1.0)
    if dur <= 0:
        dur = 1.0
    p = (t - delay) / dur  # progress 0..1
    if p < 0:
        return
    p = min(1.0, p)

    if stype == "progress":
        x = sh.get("x", 0.5) * w
        y = sh.get("y", 0.5) * h
        bw = sh.get("width", 600)
        bh = sh.get("height", 30)
        fill = _color(sh.get("color"), (255, 200, 60))
        draw_progress_bar(draw, x - bw / 2, y - bh / 2, bw, bh, p, fill)

    elif stype == "ring":
        cx = sh.get("x", 0.5) * w
        cy = sh.get("y", 0.5) * h
        r = sh.get("radius", 120)
        fill = _color(sh.get("color"), (255, 200, 60))
        draw_circle_ring(draw, cx, cy, r, p, fill, sh.get("width", 14))

    elif stype == "arrow":
        x1 = sh.get("x1", 0.2) * w
        y1 = sh.get("y1", 0.5) * h
        x2 = sh.get("x2", 0.8) * w
        y2 = sh.get("y2", 0.5) * h
        fill = _color(sh.get("color"), (255, 255, 255))
        # mũi tên dài dần theo p
        ex = x1 + (x2 - x1) * p
        ey = y1 + (y2 - y1) * p
        draw_arrow(draw, (x1, y1), (ex, ey), fill)

    elif stype == "star":
        cx = sh.get("x", 0.5) * w
        cy = sh.get("y", 0.5) * h
        r = sh.get("radius", 60) * p
        fill = _color(sh.get("color"), (255, 210, 40))
        draw_icon_star(draw, cx, cy, r, fill, rot=t * 2)

    elif stype == "heart":
        cx = sh.get("x", 0.5) * w
        cy = sh.get("y", 0.5) * h
        s = sh.get("size", 50) * p
        fill = _color(sh.get("color"), (255, 90, 90))
        draw_icon_heart(draw, cx, cy, s, fill)

    elif stype == "lightbulb":
        cx = sh.get("x", 0.5) * w
        cy = sh.get("y", 0.5) * h
        r = sh.get("radius", 60) * p
        fill = _color(sh.get("color"), (255, 220, 90))
        draw_icon_lightbulb(draw, cx, cy, r, fill)

    # ---- MÔ PHỎNG THỰC THỂ NỘI DUNG (SIMULATIONS) ----
    elif stype == "wheat":
        cx = sh.get("x", 0.5) * w
        cy = sh.get("y", 0.5) * h
        scale = sh.get("scale", 300)
        draw_wheat_field(draw, cx, cy, scale, t, grow=p)

    elif stype == "fire":
        cx = sh.get("x", 0.5) * w
        cy = sh.get("y", 0.5) * h
        scale = sh.get("scale", 260)
        draw_fire_simulation(draw, cx, cy, scale, t)

    elif stype == "gears":
        cx = sh.get("x", 0.5) * w
        cy = sh.get("y", 0.5) * h
        scale = sh.get("scale", 240)
        draw_industrial_gears(draw, cx, cy, scale, t)

    elif stype == "robot":
        cx = sh.get("x", 0.5) * w
        cy = sh.get("y", 0.5) * h
        scale = sh.get("scale", 220)
        draw_futuristic_robot(draw, cx, cy, scale, t)

    elif stype == "neural":
        cx = sh.get("x", 0.5) * w
        cy = sh.get("y", 0.5) * h
        sw = sh.get("width", 540)
        sh_h = sh.get("height", 280)
        draw_neural_network_brain(draw, cx, cy, sw, sh_h, t)

    elif stype == "rocket":
        cx = sh.get("x", 0.5) * w
        cy = sh.get("y", 0.5) * h
        scale = sh.get("scale", 240)
        draw_space_rocket(draw, cx, cy, scale, t)


def _draw_character(draw, ch, w, h, t, fps):
    cx = ch.get("x", 0.5) * w
    cy = ch.get("y", 0.65) * h
    scale = ch.get("scale", 120)
    pose = ch.get("pose", "idle")
    expr = ch.get("expression", "neutral")
    colors = ch.get("colors") or None

    # cử động miệng khi nói
    talking = 0.0
    if ch.get("talking"):
        # mở-đóng miệng theo chu kỳ ~4 lần/giây, điều biến ngẫu nhiên nhẹ
        talking = max(0.0, math.sin(t * 2 * math.pi * 4) * 0.7 + 0.3)
        # giả lập âm tiết: bật tắt nhanh
        talking *= (0.5 + 0.5 * math.sin(t * 13.7))

    # lắc nhẹ tay/cơ thể theo nhịp
    arm_swing = math.sin(t * 2 * math.pi * 1.2) * 0.4

    # nảy nhẹ toàn thân
    bounce = math.sin(t * 2 * math.pi * 1.2) * scale * 0.03
    cy += bounce

    draw_character(draw, cx, cy, scale, pose, expr, talking, arm_swing, colors)


def _draw_text(img, draw, tx, w, h, t, fonts_cache):
    text = tx.get("text", "")
    if not text:
        return
    cx = tx.get("x", 0.5) * w
    cy = tx.get("y", 0.5) * h
    size = tx.get("size", 60)
    bold = tx.get("bold", True)
    color = _color(tx.get("color"), (255, 255, 255))
    max_width = tx.get("max_width", int(w * 0.85))
    effect = tx.get("effect", "pop")
    delay = tx.get("delay", 0.0)
    dur = tx.get("duration", 1.0)
    if dur <= 0:
        dur = 1.0
    shadow = tx.get("shadow", True)

    # tiến độ hiệu ứng
    p = (t - delay) / dur
    if p < 0:
        return
    p = min(1.0, p)

    font = _font_cached(size, bold, fonts_cache)

    # typewriter: cắt text
    display_text = text
    if effect == "typewriter":
        n = int(len(text) * p)
        display_text = text[:n]
        p = 1.0  # không dịch chuyển nữa

    layer = render_text_layer(display_text, font, tuple(color) + (255,),
                              max_width=max_width, shadow=shadow)
    layer, ox, oy = apply_kinetic(layer, effect, p)

    px = int(cx - layer.width / 2 + ox)
    py = int(cy - layer.height / 2 + oy)
    img.alpha_composite(layer, (px, py))


def _font_cached(size, bold, cache):
    key = (size, bold)
    if key not in cache:
        cache[key] = load_font(size, bold)
    return cache[key]
