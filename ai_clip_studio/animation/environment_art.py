"""Layered background art for AI Clip Studio -- Premium Stickman Cinematic B.

``draw_layered_background(kind, width, height, mood)`` draws a scene
from code (PIL + numpy-free PIL only, no stock photos, no AI images)
in three depth layers so the frame stops looking flat:

  * background -- sky gradient (by mood) + distant silhouettes;
  * midground  -- architecture and props with real detail (windows,
    lamps, benches, signs, columns, trees);
  * foreground -- soft, blurred shapes at the frame edges (railing,
    branches, puddle, table edge) that frame the shot.

On top of the layers: a warm key light (radial glow at the scene's
light source) + a cool fill light, and soft ground shadows under the
midground objects. One consistent horizon (52% of height) and ground
line (85%) keep the perspective the same for every kind.

``kind`` is generic ('night_street' / 'shelter' / 'interior' /
'station' / 'park') and ``mood`` is generic ('cold' / 'warm') --
no story, character or scene names appear here.
"""
from __future__ import annotations

import random

from PIL import Image, ImageDraw, ImageFilter

KINDS = ("night_street", "shelter", "interior", "station", "park")
MOODS = ("cold", "warm")

# V51 palette.
YELLOW = (255, 211, 78)
CREAM = (243, 240, 232)
DARK = (23, 32, 51)
RED = (255, 107, 94)
GREEN = (71, 189, 117)

# Sky gradients per mood: (top, horizon).
SKIES = {
    "cold": ((10, 22, 44), (38, 62, 96)),
    "warm": ((46, 26, 48), (176, 92, 52)),
}


def _gradient(w, h, top, bottom):
    img = Image.new("RGB", (w, h), top)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        d.line([(0, y), (w, y)], fill=tuple(
            int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def _glow_layer(w, h, cx, cy, radius, color, alpha):
    """A soft radial glow on a transparent overlay."""
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
              fill=color + (alpha,))
    return ov.filter(ImageFilter.GaussianBlur(radius / 2.0))


def _buildings(d, w, horizon_y, rng, sky_dark=True):
    """Distant building silhouettes with lit windows (background)."""
    x = 0
    while x < w:
        bw = rng.randint(140, 260)
        bh = rng.randint(140, 380)
        col = (18, 34, 58) if sky_dark else (52, 40, 66)
        d.rectangle([x, horizon_y - bh, x + bw, horizon_y], fill=col)
        for wy in range(horizon_y - bh + 20, horizon_y - 20, 50):
            for wx in range(x + 15, x + bw - 15, 45):
                if rng.random() < 0.35:
                    d.rectangle([wx, wy, wx + 22, wy + 30],
                                fill=YELLOW + (160,) if d else YELLOW)
        x += bw + 10


def _distant_trees(d, w, horizon_y, rng):
    for _ in range(14):
        x = rng.randint(0, w)
        r = rng.randint(40, 90)
        d.ellipse([x - r, horizon_y - r * 1.6, x + r, horizon_y],
                  fill=(16, 42, 30))


def _lamp(d, x, ground_y, height=620, glow=True):
    d.rectangle([x - 8, ground_y - height, x + 8, ground_y],
                fill=(30, 32, 40))
    d.ellipse([x - 55, ground_y - height - 45, x + 55,
               ground_y - height + 35], fill=YELLOW)
    return (x, ground_y - height)


def _bench(d, x0, ground_y, w=420):
    d.rectangle([x0, ground_y - 140, x0 + w, ground_y - 110],
                fill=(122, 74, 43))
    d.rectangle([x0 + 30, ground_y - 110, x0 + 50, ground_y],
                fill=(90, 55, 32))
    d.rectangle([x0 + w - 50, ground_y - 110, x0 + w - 30, ground_y],
                fill=(90, 55, 32))
    d.ellipse([x0 + w // 2 - 90, ground_y - 8, x0 + w // 2 + 90,
               ground_y + 10], fill=(0, 0, 0, 60))


def _sign_board(d, x0, y0, w=150, h=80):
    d.rectangle([x0, y0, x0 + w, y0 + h], fill=DARK)
    d.rectangle([x0, y0, x0 + w, y0 + h], outline=YELLOW, width=4)
    d.rectangle([x0 + 18, y0 + 18, x0 + w - 18, y0 + 30], fill=YELLOW)
    d.rectangle([x0 + 18, y0 + 42, x0 + w - 60, y0 + 54], fill=CREAM)


def draw_layered_background(kind="night_street", width=1920, height=1080,
                            mood="cold"):
    """Return a PIL RGB image with background / midground / foreground
    depth layers, key + fill light and ground shadows.

    kind: 'night_street' | 'shelter' | 'interior' | 'station' | 'park'.
    mood: 'cold' (blue night) | 'warm' (amber dusk).
    Unknown kind/mood fall back to night_street / cold.
    """
    if kind not in KINDS:
        kind = "night_street"
    if mood not in MOODS:
        mood = "cold"
    w, h = int(width), int(height)
    horizon_y = int(h * 0.52)
    ground_y = int(h * 0.85)
    rng = random.Random(1234 + sum(ord(c) for c in kind)
                        + sum(ord(c) for c in mood))
    top, bottom = SKIES[mood]

    # --- background layer: sky gradient + distant silhouettes ----------
    if kind == "interior":
        # an interior has a wall, not a sky: warm/cool plaster gradient
        img = _gradient(w, h, (52, 44, 52) if mood == "warm" else (30, 38, 54),
                        (96, 78, 70) if mood == "warm" else (52, 64, 88))
    else:
        img = _gradient(w, h, top, bottom)
    d = ImageDraw.Draw(img, "RGBA")
    if kind in ("night_street", "shelter", "station"):
        _buildings(d, w, horizon_y, rng)
    elif kind == "park":
        _distant_trees(d, w, horizon_y, rng)
        d.ellipse([w * 0.12, horizon_y - 90, w * 0.88, horizon_y + 40],
                  fill=(20, 48, 34))  # distant hill
    elif kind == "interior":
        # back wall + a window onto the night sky
        d.rectangle([w * 0.62, h * 0.14, w * 0.90, h * 0.52],
                    fill=(14, 26, 48))
        d.rectangle([w * 0.62, h * 0.14, w * 0.90, h * 0.52],
                    outline=CREAM, width=6)
        d.line([(w * 0.76, h * 0.14), (w * 0.76, h * 0.52)],
               fill=CREAM, width=4)
        for _ in range(14):  # stars through the window
            sx = rng.randint(int(w * 0.63), int(w * 0.89))
            sy = rng.randint(int(h * 0.15), int(h * 0.50))
            d.ellipse([sx, sy, sx + 4, sy + 4], fill=YELLOW)
        # framed picture on the wall
        d.rectangle([w * 0.10, h * 0.20, w * 0.28, h * 0.44],
                    fill=(70, 60, 44), outline=YELLOW, width=4)

    # --- midground layer: ground + architecture + props -----------------
    ground_top = horizon_y
    ground_col = ((28, 43, 64) if kind != "park" else (26, 52, 36))
    if kind == "interior":
        ground_col = (74, 58, 44)  # wooden floor
    d.rectangle([0, ground_top, w, h], fill=ground_col)
    if kind != "interior":
        d.rectangle([0, ground_top, w, ground_top + 20],
                    fill=(52, 70, 100) if kind != "park" else (52, 84, 56))
    else:
        # floor boards
        for y in range(ground_top, h, 46):
            d.line([(0, y), (w, y)], fill=(58, 44, 32), width=2)

    lamp_pos = None
    if kind == "night_street":
        for cx, cy, rx, ry in [(420, 700, 180, 26), (1150, 800, 240, 30),
                               (1600, 660, 150, 22), (760, 880, 200, 24)]:
            d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                      fill=(38, 56, 82))
        lamp_pos = _lamp(d, 180, ground_y)
        _lamp(d, 1740, ground_y)
        # kerb line for perspective
        d.line([(0, ground_y - 60), (w, ground_y - 20)],
               fill=(52, 70, 100), width=4)
    elif kind == "shelter":
        # roof + posts + glass back panel + bench + sign
        d.rectangle([1000, 290, 1870, 340], fill=(52, 58, 72))
        d.rectangle([1000, 290, 1870, 306], fill=YELLOW)
        d.rectangle([1050, 330, 1090, ground_y], fill=(40, 44, 54))
        d.rectangle([1780, 330, 1820, ground_y], fill=(40, 44, 54))
        d.rectangle([1090, 340, 1780, ground_y], fill=(24, 44, 70, 180))
        _bench(d, 1150, ground_y)
        _sign_board(d, 1010, 360)
        lamp_pos = _lamp(d, 180, ground_y)
    elif kind == "station":
        # platform edge + columns + sign + bench + distant train
        d.rectangle([0, ground_y - 90, w, ground_y - 70], fill=YELLOW)
        for x in (300, 900, 1500):
            d.rectangle([x, horizon_y - 120, x + 46, ground_y - 90],
                        fill=(40, 44, 54))
            d.ellipse([x - 60, ground_y - 10, x + 106, ground_y + 12],
                      fill=(0, 0, 0, 60))
        d.rectangle([0, horizon_y - 190, w, horizon_y - 60],
                    fill=(30, 42, 66))  # distant train silhouette
        for i in range(8):
            d.rectangle([80 + i * 230, horizon_y - 170,
                         200 + i * 230, horizon_y - 90],
                        fill=(210, 228, 240))
        _bench(d, 1150, ground_y)
        _sign_board(d, 620, horizon_y - 260, w=220, h=90)
        lamp_pos = _lamp(d, 180, ground_y)
    elif kind == "park":
        # path + trees + bench + lamp
        d.polygon([(760, horizon_y), (1160, horizon_y), (1500, h),
                   (420, h)], fill=(96, 82, 62))
        for tx, tr in [(300, 150), (1650, 170), (520, 110)]:
            d.rectangle([tx - 14, ground_y - 260, tx + 14, ground_y],
                        fill=(74, 52, 32))
            d.ellipse([tx - tr, ground_y - 260 - tr, tx + tr,
                       ground_y - 260 + tr * 0.4], fill=(30, 78, 44))
            d.ellipse([tx - tr, ground_y - 10, tx + tr, ground_y + 12],
                      fill=(0, 0, 0, 60))
        _bench(d, 1150, ground_y)
        lamp_pos = _lamp(d, 180, ground_y)
    elif kind == "interior":
        # table + chairs + hanging lamp + rug
        d.ellipse([w * 0.30, ground_y - 10, w * 0.72, ground_y + 26],
                  fill=(0, 0, 0, 70))  # rug shadow
        d.ellipse([w * 0.32, ground_y - 4, w * 0.70, ground_y + 20],
                  fill=(122, 52, 52))
        d.rectangle([w * 0.38, ground_y - 190, w * 0.64, ground_y - 160],
                    fill=(122, 74, 43))  # tabletop
        d.rectangle([w * 0.42, ground_y - 160, w * 0.44, ground_y],
                    fill=(90, 55, 32))
        d.rectangle([w * 0.58, ground_y - 160, w * 0.60, ground_y],
                    fill=(90, 55, 32))
        for cx in (w * 0.30, w * 0.72):  # chairs
            d.rectangle([cx - 40, ground_y - 150, cx + 40, ground_y - 120],
                        fill=(70, 60, 44))
            d.rectangle([cx - 40, ground_y - 120, cx - 28, ground_y],
                        fill=(52, 44, 32))
            d.rectangle([cx + 28, ground_y - 120, cx + 40, ground_y],
                        fill=(52, 44, 32))
        lamp_pos = (w // 2, int(h * 0.22))
        d.line([(w // 2, 0), (w // 2, int(h * 0.16))], fill=DARK, width=6)
        d.polygon([(w // 2 - 70, int(h * 0.22)), (w // 2 + 70, int(h * 0.22)),
                   (w // 2 + 40, int(h * 0.14)), (w // 2 - 40, int(h * 0.14))],
                  fill=YELLOW)

    # --- key light + fill light (radial glows, composited soft) ---------
    base = img.convert("RGBA")
    if lamp_pos is not None:
        glow = _glow_layer(w, h, lamp_pos[0], lamp_pos[1], 320, YELLOW, 70)
        base = Image.alpha_composite(base, glow)
        # warm pool of light on the ground under the lamp
        pool = _glow_layer(w, h, lamp_pos[0], ground_y - 10, 260, YELLOW, 45)
        base = Image.alpha_composite(base, pool)
    # cool fill light from the opposite side
    fill = _glow_layer(w, h, int(w * 0.85), int(h * 0.30), 520,
                       (120, 170, 255), 28)
    base = Image.alpha_composite(base, fill)

    # --- foreground layer: soft blurred shapes framing the shot ---------
    fg = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fg)
    if kind in ("night_street", "shelter", "station"):
        # railing along the bottom edge
        fd.rectangle([0, h - 46, w, h - 30], fill=(12, 16, 26, 200))
        for x in range(0, w, 130):
            fd.rectangle([x, h - 120, x + 16, h - 30], fill=(12, 16, 26, 200))
        # branch intruding from the top-left corner
        fd.line([(0, 40), (420, 150)], fill=(10, 26, 18, 220), width=26)
        fd.line([(120, 0), (300, 190)], fill=(10, 26, 18, 200), width=18)
    elif kind == "park":
        fd.line([(0, 30), (520, 170)], fill=(10, 30, 18, 220), width=30)
        fd.ellipse([-80, h - 220, 420, h + 60], fill=(14, 40, 24, 200))
        fd.ellipse([w - 380, h - 180, w + 80, h + 60],
                   fill=(14, 40, 24, 200))
    elif kind == "interior":
        fd.rectangle([0, h - 90, w, h], fill=(30, 22, 18, 200))
        fd.ellipse([-120, -80, 260, 200], fill=(20, 16, 14, 180))
    fg = fg.filter(ImageFilter.GaussianBlur(8))
    base = Image.alpha_composite(base, fg)
    return base.convert("RGB")
