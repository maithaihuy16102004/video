"""Reusable real-world landmark library (v8, animation audit 2026-11-11).

Mai's verdict on motion test v7: the scene must have distinctive
REAL-WORLD things (e.g. the Great Wall / Van Ly Truong Thanh), not
generic boxes. A landmark is a PARAMETRIC set of 3D boxes + colours +
a signature silhouette, defined once in the shared engine -- never
per-story. Each landmark carries:

  ``boxes``   -- list of 3D box dicts {center, size, color, name,
                 label} for the 2.5D scene (renderer25d). A scene must
                 be identifiable from ONE still frame.
  ``draw_2d`` -- a function (draw, w, h, ground_y) that draws the
                 landmark's fine detail in screen space (crenellations,
                 lattice bracing, ridge lines) on top of a rendered
                 frame, in the same PIL renderer as the motion test.
  ``features``-- the signature features a viewer uses to recognise it.
  ``sky`` / ``ground_color`` -- the setting it lives in.

Landmarks: great_wall, eiffel_tower, rainy_street (Vietnamese street
-- the motion-test scene, enriched with real street details as
engine-level location features, not hardcoded story props).

The 3D boxes give the structure (perspective, depth layers, parallax);
the 2D draw gives the detail boxes cannot express (a lattice, a
crenellated top edge, a sagging power line). Both are checked by the
v8 rubric: box counts/spans from the data, silhouette/span from the
rendered still's pixels.
"""
from __future__ import annotations

import math
import random

# ---------------------------------------------------------------------------
# Great Wall (Van Ly Truong Thanh)
# ---------------------------------------------------------------------------

GREAT_WALL_STONE = (150, 138, 112)
GREAT_WALL_STONE_DARK = (118, 106, 84)
GREAT_WALL_ROOF = (96, 84, 70)
RIDGE_FAR = (96, 116, 88)
RIDGE_MID = (74, 94, 68)
RIDGE_NEAR = (56, 76, 54)


def great_wall_boxes():
    """Wall segments snaking over a ridge line + watchtowers.

    8 wall segments follow a sine ridge (x -7..7, y and z both vary
    so the wall snakes in plan AND elevation); 3 watchtowers stand
    on the ridge, taller than the wall, with a roof box each.
    """
    boxes = []
    for i in range(8):
        x = -7.0 + i * 2.0
        y = 0.4 + 0.55 * math.sin(x * 0.45)
        z = -8.0 - 0.6 * math.cos(x * 0.35)
        boxes.append({"center": (x, y + 0.4, z), "size": (2.1, 0.8, 0.6),
                      "color": GREAT_WALL_STONE, "name": f"wall_{i}",
                      "label": ""})
    for j, x in enumerate((-4.5, 0.5, 5.0)):
        y = 0.4 + 0.55 * math.sin(x * 0.45)
        z = -8.0 - 0.6 * math.cos(x * 0.35)
        boxes.append({"center": (x, y + 1.0, z), "size": (1.2, 2.0, 1.2),
                      "color": GREAT_WALL_STONE_DARK,
                      "name": f"watchtower_{j}", "label": ""})
        boxes.append({"center": (x, y + 2.15, z), "size": (1.5, 0.3, 1.5),
                      "color": GREAT_WALL_ROOF,
                      "name": f"watchtower_roof_{j}", "label": ""})
    return boxes


def draw_great_wall_2d(draw, w, h, ground_y, font=None):
    """Draw the Great Wall over ridges (screen space, day).

    Ridge silhouettes (far -> near), the wall as a crenellated band
    following the middle ridge, and three watchtowers. The wall spans
    ~90% of the frame width and snakes vertically (the ridge sine),
    so the still reads as the Wall from one frame.
    """
    horizon = int(h * 0.52)
    # ridge silhouettes: sine tops, far (light) to near (dark)
    for amp, base_y, col in ((0.045, horizon - 40, RIDGE_FAR),
                             (0.065, horizon + 30, RIDGE_MID),
                             (0.085, horizon + 110, RIDGE_NEAR)):
        pts = [(0, h)]
        for x in range(0, w + 1, 24):
            y = base_y + amp * h * math.sin(x / w * math.pi * 2.2 + 0.6)
            pts.append((x, y))
        pts.append((w, h))
        draw.polygon(pts, fill=col)
    # the wall: a band following the middle ridge (amp 0.065, base
    # horizon+30), from 5% to 95% of the width.
    wall_pts = []
    for x in range(int(w * 0.05), int(w * 0.95) + 1, 24):
        y = (horizon + 30 + 0.065 * h * math.sin(x / w * math.pi * 2.2 + 0.6))
        wall_pts.append((x, y))
    # wall body: thick polyline (stone) + darker base line
    draw.line(wall_pts, fill=GREAT_WALL_STONE, width=26)
    draw.line([(x, y + 13) for x, y in wall_pts],
              fill=GREAT_WALL_STONE_DARK, width=4)
    # crenellations: small merlons along the top edge every ~30 px
    for (x, y) in wall_pts[::2]:
        draw.rectangle([x - 7, y - 26, x + 7, y - 13],
                       fill=GREAT_WALL_STONE)
    # watchtowers on the ridge at 18% / 50% / 82% of the width
    for fx in (0.18, 0.50, 0.82):
        tx = int(w * fx)
        ty = (horizon + 30
              + 0.065 * h * math.sin(tx / w * math.pi * 2.2 + 0.6))
        tw, th = 92, 150
        draw.rectangle([tx - tw // 2, ty - th, tx + tw // 2, ty + 14],
                       fill=GREAT_WALL_STONE_DARK,
                       outline=GREAT_WALL_ROOF, width=3)
        # roof: trapezoid cap + arched door
        draw.polygon([(tx - tw // 2 - 10, ty - th),
                      (tx + tw // 2 + 10, ty - th),
                      (tx + tw // 2 - 18, ty - th - 34),
                      (tx - tw // 2 + 18, ty - th - 34)],
                     fill=GREAT_WALL_ROOF)
        draw.rectangle([tx - 14, ty - 52, tx + 14, ty + 14],
                       fill=(52, 46, 36))
        draw.pieslice([tx - 14, ty - 66, tx + 14, ty - 38], 180, 360,
                      fill=(52, 46, 36))
    return {"wall_top_y": [y for _, y in wall_pts]}


# ---------------------------------------------------------------------------
# Eiffel Tower (Paris, dusk)
# ---------------------------------------------------------------------------

EIFFEL_IRON = (52, 48, 62)
EIFFEL_IRON_LIGHT = (88, 82, 100)
EIFFEL_LIGHT = (255, 200, 90)


def eiffel_tower_boxes():
    """Lattice tower as stacked boxes: 4 legs (2 tiers), 3 platforms,
    a shaft and a spire. The 2D draw adds the lattice bracing."""
    boxes = []
    # tier 1 legs: 4 corner posts, base +-1.2 -> +-0.7 at y 2.0
    for sx in (-1, 1):
        for sz in (-1, 1):
            boxes.append({"center": (sx * 0.95, 1.0, sz * 0.95),
                          "size": (0.5, 2.0, 0.5), "color": EIFFEL_IRON,
                          "name": f"leg1_{sx}_{sz}", "label": ""})
            boxes.append({"center": (sx * 0.55, 2.9, sz * 0.55),
                          "size": (0.4, 1.8, 0.4), "color": EIFFEL_IRON,
                          "name": f"leg2_{sx}_{sz}", "label": ""})
    # platforms (3) + shaft + spire
    for y, s in ((2.0, 3.0), (3.8, 1.8), (5.0, 1.0)):
        boxes.append({"center": (0.0, y, 0.0), "size": (s, 0.25, s),
                      "color": EIFFEL_IRON_LIGHT,
                      "name": f"platform_{y}", "label": ""})
    boxes.append({"center": (0.0, 4.4, 0.0), "size": (0.7, 1.4, 0.7),
                  "color": EIFFEL_IRON, "name": "shaft", "label": ""})
    boxes.append({"center": (0.0, 5.6, 0.0), "size": (0.18, 1.4, 0.18),
                  "color": EIFFEL_IRON_LIGHT, "name": "spire", "label": ""})
    return boxes


def draw_eiffel_tower_2d(draw, w, h, ground_y, font=None):
    """Draw the Eiffel Tower (screen space, dusk): curved legs, 3
    platforms, lattice cross-bracing, spire, warm lights. The tower
    is centred, base ~0.32W wide, top ~0.05W -- the lattice-tower
    silhouette is recognisable from one still."""
    cx = w // 2
    base_y = ground_y
    top_y = int(h * 0.06)
    # Paris rooftops at the base (dark, with chimneys) so the tower
    # stands in a city, not in a void.
    for rx, rw, rh in ((0.02, 0.16, 0.10), (0.80, 0.18, 0.12),
                       (0.68, 0.10, 0.08)):
        x0 = int(w * rx)
        draw.rectangle([x0, base_y - int(h * rh), x0 + int(w * rw), base_y],
                       fill=(38, 34, 44))
        draw.rectangle([x0 + int(w * rw * 0.3), base_y - int(h * rh) - 26,
                        x0 + int(w * rw * 0.3) + 16, base_y - int(h * rh)],
                       fill=(38, 34, 44))
    # legs: quadratic curves from the base corners to the first
    # platform, then a narrowing shaft to the top.
    p1_y = int(h * 0.55)   # first platform
    p2_y = int(h * 0.35)   # second platform
    p3_y = int(h * 0.18)   # top platform
    base_half = int(w * 0.16)
    p1_half = int(w * 0.085)
    p2_half = int(w * 0.045)
    p3_half = int(w * 0.020)

    def _leg(side):
        pts = []
        for i in range(21):
            u = i / 20.0
            # base -> p1: quadratic ease inward
            x = cx + side * (base_half + (p1_half - base_half) * u * u)
            y = base_y + (p1_y - base_y) * u
            pts.append((x, y))
        for i in range(1, 21):
            u = i / 20.0
            x = cx + side * (p1_half + (p2_half - p1_half) * u)
            y = p1_y + (p2_y - p1_y) * u
            pts.append((x, y))
        for i in range(1, 21):
            u = i / 20.0
            x = cx + side * (p2_half + (p3_half - p2_half) * u)
            y = p2_y + (p3_y - p2_y) * u
            pts.append((x, y))
        return pts

    for side in (-1, 1):
        draw.line(_leg(side), fill=EIFFEL_IRON, width=20)
        draw.line(_leg(side), fill=EIFFEL_IRON_LIGHT, width=6)
    # lattice cross-bracing between the legs (X patterns), lower
    # section only -- the dense lattice is the tower's signature.
    # (v8 fix: the first draft iterated range(base_y, p1_y, +46),
    # which is EMPTY going downward -- no bracing was drawn at all.)
    for y0 in range(p1_y + 40, base_y - 40, 46):
        t = (base_y - y0) / max(base_y - p1_y, 1)
        half = base_half + (p1_half - base_half) * t * t
        draw.line([(cx - half, y0), (cx + half, y0 - 46)],
                  fill=EIFFEL_IRON_LIGHT, width=4)
        draw.line([(cx + half, y0), (cx - half, y0 - 46)],
                  fill=EIFFEL_IRON_LIGHT, width=4)
    # platforms: horizontal bars with a lighter top edge
    for py, half in ((p1_y, p1_half + 14), (p2_y, p2_half + 12),
                     (p3_y, p3_half + 10)):
        draw.rectangle([cx - half, py - 12, cx + half, py + 12],
                       fill=EIFFEL_IRON, outline=EIFFEL_IRON_LIGHT, width=3)
    # spire + antenna
    draw.line([(cx, p3_y - 10), (cx, top_y + 26)], fill=EIFFEL_IRON, width=10)
    draw.line([(cx, top_y + 26), (cx, top_y)], fill=EIFFEL_LIGHT, width=4)
    # warm lights along the legs (the tower is lit at night)
    rng = random.Random(7)
    for side in (-1, 1):
        pts = _leg(side)
        for (x, y) in pts[::3]:
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=EIFFEL_LIGHT)
    return {"base_half_px": base_half, "top_half_px": p3_half,
            "tower_top_y": top_y, "tower_base_y": base_y}


# ---------------------------------------------------------------------------
# Vietnamese street details (engine-level location features)
# ---------------------------------------------------------------------------

def draw_awning_2d(draw, x0, y0, w, h, window=True):
    """A real shop awning, drawn in screen space (v9, overnight scene
    work). The v7/v8 motion test used a flat red Box3D slab floating
    above the bus-stop sign -- it read as a red bar, not an awning,
    because it had no slope, no stripes, no valance, no supports and
    no shadow. This one has all five: a SLOPED striped canopy (red /
    cream, sloping down toward the viewer), a SCALLOPED valance edge,
    two diagonal SUPPORT ARMS back to the wall, a soft SHADOW band on
    the wall beneath it, and (``window=True``) a LIT SHOPFRONT window
    under the canopy so the awning belongs to a shop, not to the sky.

    (x0, y0) is the top-left of the canopy's back edge; the canopy
    slopes down h*0.55 toward the front. ``window=False`` skips the
    shopfront window (use it when a sign sits directly beneath the
    awning -- the motion-test bus-stop sign's top is 16 px below the
    compact awning's valance). Returns the features drawn.
    """
    RED = (168, 52, 44)
    CREAM = (240, 224, 180)
    DARK = (23, 32, 51)
    slope = int(h * 0.55)
    # --- shadow band on the wall under the canopy --------------------
    # v9.1 fix: the shadow was drawn as fill=(0,0,0,60) -- an RGBA
    # tuple on an RGB ImageDraw, which PIL silently drops, so the
    # shadow NEVER rendered (the awning still read fine, but the
    # documented shadow was a lie). A solid dark navy band reads as
    # a shadow on the night wall and works on RGB frames.
    sh_h = int(h * 0.42) if window else max(8, int(h * 0.22))
    draw.rectangle([x0 - 8, y0 + slope + 6, x0 + w + 8,
                    y0 + slope + 6 + sh_h],
                   fill=(10, 14, 26))
    # --- lit shopfront window under the canopy (optional) ------------
    feats = ["awning_striped_canopy", "awning_scalloped_valance",
             "awning_support_arms", "awning_wall_shadow"]
    if window:
        win_x0, win_y0 = x0 + int(w * 0.14), y0 + slope + 14
        win_w, win_h = int(w * 0.72), int(h * 0.42)
        draw.rectangle([win_x0, win_y0, win_x0 + win_w, win_y0 + win_h],
                       fill=(255, 196, 92), outline=DARK, width=3)
        # goods silhouettes inside the window (jars / bottles on a shelf)
        draw.line([(win_x0 + 6, win_y0 + win_h - 16),
                   (win_x0 + win_w - 6, win_y0 + win_h - 16)],
                  fill=DARK, width=3)
        for gx in (0.20, 0.42, 0.64, 0.84):
            bx = win_x0 + int(win_w * gx)
            draw.rectangle([bx - 7, win_y0 + win_h - 40, bx + 7,
                            win_y0 + win_h - 16], fill=DARK)
            draw.rectangle([bx - 4, win_y0 + win_h - 48, bx + 4,
                            win_y0 + win_h - 40], fill=DARK)
        feats.append("shopfront_lit_window")
    # --- striped canopy: vertical stripes following the slope --------
    n_stripes = 8
    sw = w / n_stripes
    for i in range(n_stripes):
        sx0 = x0 + i * sw
        sx1 = x0 + (i + 1) * sw
        # the front edge is lower than the back edge by `slope`
        draw.polygon([(sx0, y0), (sx1, y0),
                      (sx1, y0 + slope), (sx0, y0 + slope)],
                     fill=RED if i % 2 == 0 else CREAM,
                     outline=DARK)
    # canopy outline (top edge + front edge)
    draw.line([(x0, y0), (x0 + w, y0)], fill=DARK, width=4)
    draw.line([(x0, y0 + slope), (x0 + w, y0 + slope)], fill=DARK, width=4)
    # --- scalloped valance hanging from the front edge ---------------
    val_h = max(10, int(h * 0.16))
    n_scallops = 8
    for i in range(n_scallops):
        sx0 = x0 + i * sw
        sx1 = x0 + (i + 1) * sw
        draw.pieslice([sx0, y0 + slope - val_h, sx1,
                       y0 + slope + val_h], 0, 180,
                      fill=RED if i % 2 == 0 else CREAM, outline=DARK)
    # --- support arms: diagonals from the front corners back up -----
    for sx in (x0 + 14, x0 + w - 14):
        draw.line([(sx, y0 + slope - 4), (sx + (14 if sx < x0 + w / 2 else -14),
                                          y0 - int(h * 0.22))],
                  fill=DARK, width=5)
    return feats


def draw_wet_ground_reflections(draw, w, h, ground_y, lamp_x, offset_x=0):
    """Wet-pavement detail for a rainy night street (v9): two puddles
    with a warm lamp-light streak and a cool sky reflection, plus
    pavement cracks. Puddles sit ON the ground plane (below the
    characters' feet), so they read as wet ground, not as objects.
    Returns the features drawn."""
    # puddle 1: under the lamp -- warm streak reflected in dark water
    px, py, pw, ph = int(w * 0.62) + offset_x, ground_y + 46, 260, 26
    draw.ellipse([px, py, px + pw, py + ph], fill=(28, 34, 52),
                 outline=(90, 96, 110), width=2)
    draw.ellipse([px + 30, py + 8, px + pw - 30, py + 16],
                 fill=(255, 196, 92))
    # puddle 2: left of frame -- cool sky reflection + a rain ripple
    px2, py2, pw2, ph2 = int(w * 0.16) + offset_x, ground_y + 90, 200, 22
    draw.ellipse([px2, py2, px2 + pw2, py2 + ph2], fill=(34, 44, 62),
                 outline=(90, 96, 110), width=2)
    draw.ellipse([px2 + 40, py2 + 6, px2 + pw2 - 40, py2 + 12],
                 fill=(140, 160, 190))
    draw.ellipse([px2 + 90, py2 + 4, px2 + 110, py2 + 14],
                 outline=(200, 210, 225), width=2)
    # pavement cracks (thin dark jagged lines)
    for (cx, cy, pts) in ((int(w * 0.34) + offset_x, ground_y + 120,
                           [(0, 0), (18, 8), (30, 2), (52, 14)]),
                          (int(w * 0.72) + offset_x, ground_y + 140,
                           [(0, 0), (14, -6), (34, 4), (48, -4)])):
        draw.line([(cx + dx, cy + dy) for dx, dy in pts],
                  fill=(20, 20, 24), width=3)
    return ["puddle_lamp_reflection", "puddle_sky_reflection",
            "pavement_cracks"]


# ---------------------------------------------------------------------------
# Vietnamese street -- DATA-DRIVEN location features (v9.1)
# ---------------------------------------------------------------------------
# Mai's reminder (2026-11-11 23:22): the engine must be UNIVERSAL --
# it receives a location's distinctive features as STRUCTURED DATA
# (from Gemini via the pipeline) and renders them; it must not hardcode
# one story's street. ``draw_vietnamese_street_features`` therefore
# takes a ``data`` dict: shop signs, hanging sign, vehicles, poles,
# lantern, wet ground. ``VIETNAMESE_STREET_DEFAULT`` is the default
# street (the rainy corner used by the motion test / camera test /
# five-moment test) -- callers that pass nothing get exactly the v9
# street, pixel-identical. A different script passes different data
# (different signs, different vehicles) through the SAME function.
# ``offset_x`` shifts every feature horizontally (for a camera pan /
# tracking shot: the 2D overlay must slide with the world, not stay
# glued to the screen). At offset_x=0 the output is pixel-identical
# to the v9 function it replaces.
# ---------------------------------------------------------------------------

VIETNAMESE_STREET_DEFAULT = {
    "signs": [
        {"fx": 0.30, "text": "PHỞ", "color": (150, 40, 40),
         "width": 190, "font": 34},
        {"fx": 0.60, "text": "C\u00c0 PH\u00ca", "color": (40, 70, 130),
         "width": 190, "font": 34},
        {"fx": 0.875, "text": "B\u00c1NH M\u00cc", "color": (150, 120, 30),
         "width": 150, "font": 26},
    ],
    "hanging_sign": {"fx": 0.30, "fy": 0.27, "text": "C\u01a0M B\u00ccNH D\u00c2N",
                     "color": (30, 60, 40), "width": 190, "font": 22},
    "vehicles": [{"kind": "motorbike", "fx": 0.80},
                 {"kind": "bicycle", "fx": 0.24}],
    "poles": [0.06, 0.96],
    "lantern": True,
    "wet_ground": True,
}


def _sign_font(size):
    try:
        from PIL import ImageFont
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return None


def _ascii_fold(text):
    """Fold Vietnamese text to an ASCII slug for feature names
    (``PHỞ`` -> ``pho``): NFKD decomposition, drop combining marks,
    đ -> d. Feature names stay the v8 slugs (``shop_sign_pho``)."""
    import unicodedata
    folded = "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c))
    return folded.lower().replace(" ", "_").replace("đ", "d")


def _draw_motorbike_2d(draw, bx, by, ink):
    """Parked motorbike, side view silhouette (reusable vehicle)."""
    wheel_r = 30
    for wx in (bx - 62, bx + 62):
        draw.ellipse([wx - wheel_r, by - wheel_r, wx + wheel_r, by + wheel_r],
                     outline=ink, width=7)
        draw.ellipse([wx - 8, by - 8, wx + 8, by + 8], fill=ink)
    draw.line([(bx - 62, by), (bx - 10, by - 46)], fill=ink, width=7)
    draw.line([(bx - 10, by - 46), (bx + 30, by - 52)], fill=ink, width=7)
    draw.line([(bx + 30, by - 52), (bx + 62, by)], fill=ink, width=7)
    draw.line([(bx - 10, by - 46), (bx + 6, by - 6)], fill=ink, width=6)
    draw.rectangle([bx - 34, by - 62, bx + 6, by - 48], fill=ink)
    draw.line([(bx + 30, by - 52), (bx + 44, by - 78)], fill=ink, width=6)
    draw.line([(bx + 44, by - 78), (bx + 62, by - 72)], fill=ink, width=5)
    draw.ellipse([bx + 62 - 6, by - 10, bx + 62 + 6, by + 2],
                 fill=(255, 211, 78))  # headlight


def _draw_bicycle_2d(draw, bx, by, ink):
    """Bicycle leaning at the kerb (reusable vehicle)."""
    for wx in (bx - 40, bx + 40):
        draw.ellipse([wx - 22, by - 22, wx + 22, by + 22],
                     outline=ink, width=5)
    draw.line([(bx - 40, by), (bx - 6, by - 34)], fill=ink, width=5)
    draw.line([(bx - 6, by - 34), (bx + 40, by)], fill=ink, width=5)
    draw.line([(bx - 6, by - 34), (bx + 8, by - 44)], fill=ink, width=5)
    draw.line([(bx + 8, by - 44), (bx + 28, by - 44)], fill=ink, width=5)


def draw_bus_2d(draw, x, y, w, h, route="", color=(36, 84, 138),
                facing=1, door_open=False):
    """A city bus, side view -- a REUSABLE vehicle prop, not a story
    prop. ``(x, y)`` is the top-left of the body, ``(w, h)`` its size;
    ``route`` is the route number / destination on the sign;
    ``facing`` 1 = front to the right, -1 = front to the left;
    ``door_open`` draws the entry door open (for a boarding shot).
    Returns the features drawn. The door rect (for a boarding
    primitive) is returned as well, in ``door``: (x0, y0, x1, y1)."""
    ink = (16, 18, 26)
    # body: rounded rectangle + roof line + skirt
    draw.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=color,
                           outline=ink, width=4)
    draw.rectangle([x, y + int(h * 0.62), x + w, y + h], fill=(24, 56, 92))
    # windows: lit warm band with pillars
    win_y0, win_y1 = y + int(h * 0.16), y + int(h * 0.52)
    draw.rectangle([x + 14, win_y0, x + w - 14, win_y1],
                   fill=(255, 214, 120), outline=ink, width=3)
    for i in range(1, 5):
        px = x + int(w * i / 5)
        draw.line([(px, win_y0), (px, win_y1)], fill=ink, width=4)
    # destination / route sign above the windscreen
    fx0 = x + w - 150 if facing == 1 else x + 20
    draw.rectangle([fx0, y + 8, fx0 + 130, y + 34], fill=(16, 18, 26))
    if route:
        draw.text((fx0 + 10, y + 10), route, fill=(255, 211, 78),
                  font=_sign_font(20))
    # windscreen (front) + headlights
    wx0 = x + w - 70 if facing == 1 else x + 10
    draw.rectangle([wx0, win_y0, wx0 + 60, win_y1], fill=(180, 210, 235),
                   outline=ink, width=3)
    for hx in ((x + 8, y + h - 26), (x + w - 30, y + h - 26)):
        draw.ellipse([hx[0], hx[1], hx[0] + 22, hx[1] + 16],
                     fill=(255, 240, 170), outline=ink, width=2)
    # door: just behind the front wheel; open = dark opening + panel
    door_w = int(w * 0.11)
    dx0 = (x + w - 190) if facing == 1 else (x + 120)
    door = (dx0, y + int(h * 0.16), dx0 + door_w, y + h)
    if door_open:
        draw.rectangle(door, fill=(10, 12, 20), outline=(255, 211, 78),
                       width=3)
        # open panel swung out
        draw.polygon([(door[0], door[1]), (door[0] + 26, door[1] - 8),
                      (door[0] + 26, door[3] - 8), (door[0], door[3])],
                     fill=color, outline=ink)
    else:
        draw.rectangle(door, fill=(255, 214, 120), outline=ink, width=3)
        draw.line([(door[0] + door_w // 2, door[1]),
                   (door[0] + door_w // 2, door[3])], fill=ink, width=3)
    # wheels + ground shadow
    for wx in (x + int(w * 0.20), x + int(w * 0.80)):
        draw.ellipse([wx - 26, y + h - 8, wx + 26, y + h + 30],
                     fill=(12, 12, 16), outline=ink, width=4)
        draw.ellipse([wx - 9, y + h + 7, wx + 9, y + h + 21],
                     fill=(120, 120, 130))
    draw.ellipse([x + 30, y + h + 26, x + w - 30, y + h + 36],
                 fill=(0, 0, 0, 90))
    return {"features": ["bus_body", "bus_windows", "bus_door",
                         "bus_wheels", "bus_route_sign"],
            "door": door}


def draw_vietnamese_street_features(draw, w, h, ground_y, data=None,
                                    offset_x=0):
    """Real-world Vietnamese street details, drawn as a 2D overlay on
    a night-street frame. DATA-DRIVEN (v9.1): ``data`` is the location
    package (signs, hanging sign, vehicles, poles, lantern, wet
    ground); ``data=None`` uses VIETNAMESE_STREET_DEFAULT, which is
    exactly the v9 street. ``offset_x`` shifts every feature
    horizontally (camera pan / tracking shot).

    Returns the list of features drawn (for the rubric).
    """
    data = data if data is not None else VIETNAMESE_STREET_DEFAULT
    ink = (16, 18, 26)

    def X(fx):
        return int(w * fx) + offset_x

    def Y(fy):
        return int(h * fy)

    feats = []
    # Draw order = the original v9 order (pixel-identity at offset_x=0
    # depends on it: the pole-to-pole line and the lantern are drawn
    # AFTER the signs, so they stay visible where they cross a board).
    poles = list(data.get("poles", []))
    pole_x = X(poles[0]) if poles else 0
    # --- first pole + power lines -------------------------------------
    if poles:
        draw.rectangle([pole_x - 7, Y(0.06), pole_x + 7, Y(0.52)],
                       fill=ink)
        draw.line([(pole_x - 60, Y(0.10)), (pole_x + 60, Y(0.10))],
                  fill=ink, width=6)
        feats.append("utility_pole")
    for y0, sag in ((Y(0.07), 46), (Y(0.12), 58)):
        pts = []
        for x in range(-192, w + 193, 32):
            y = y0 + sag * math.sin(math.pi * (x - offset_x) / w)
            pts.append((x, y))
        draw.line(pts, fill=ink, width=3)
    feats.append("power_lines")
    # --- shop signs: vertical boards on the facades ------------------
    # v8: the CA PHE board sits at fx 0.60, not 0.55 -- at 0.55 it
    # overlapped the bus-stop sign face. v9: the BANH MI board moves
    # to fx 0.875 and narrows to 150 px -- the v9 camera shift moves
    # Lan's head to x 1412-1678, so the old board (1651-1841) would
    # hide behind her head. (Positions now live in the data dict.)
    for sg in data.get("signs", []):
        x0 = X(sg["fx"])
        y0 = Y(0.16)
        draw.rectangle([x0, y0, x0 + sg["width"], y0 + 64],
                       fill=sg["color"], outline=(255, 211, 78), width=3)
        draw.text((x0 + 12, y0 + 12), sg["text"], fill=(255, 255, 255),
                  font=_sign_font(sg.get("font", 34)))
        feats.append("shop_sign_" + _ascii_fold(sg["text"]))
    # --- vehicles (data: kind + fx) -----------------------------------
    for v in data.get("vehicles", []):
        bx, by = X(v["fx"]), ground_y - 6
        if v["kind"] == "motorbike":
            _draw_motorbike_2d(draw, bx, by, ink)
            feats.append("motorbike")
        elif v["kind"] == "bicycle":
            # original bicycle baseline is ground_y - 4 (motorbike is -6)
            _draw_bicycle_2d(draw, bx, ground_y - 4, ink)
            feats.append("bicycle")
    # --- pavement: tile grid + manhole + drain grate -----------------
    for gx in range(-150, w + 1, 150):
        draw.line([(gx + offset_x, ground_y + 40),
                   (gx + offset_x - 60, h)], fill=(90, 86, 78), width=2)
    draw.line([(0, ground_y + 70), (w, ground_y + 70)], fill=(90, 86, 78),
              width=2)
    draw.ellipse([X(0.42), ground_y + 96, X(0.42) + 90,
                  ground_y + 126], fill=(30, 30, 34),
                 outline=(90, 86, 78), width=2)
    for i in range(4):
        gx = X(0.10) + i * 26
        draw.line([(gx, ground_y + 150), (gx, ground_y + 178)],
                  fill=(20, 20, 24), width=6)
    feats += ["pavement_tiles", "manhole", "drain_grate"]
    # --- hanging red lantern, glowing, from the first pole ------------
    if poles and data.get("lantern", True):
        lx, ly = pole_x + 44, Y(0.13)
        draw.line([(pole_x + 44, Y(0.10)), (lx, ly)], fill=ink, width=4)
        draw.ellipse([lx - 16, ly, lx + 16, ly + 34],
                     fill=(200, 40, 32), outline=(120, 20, 16), width=2)
        draw.ellipse([lx - 7, ly + 8, lx + 7, ly + 26],
                     fill=(255, 200, 90))
        draw.line([(lx - 8, ly + 34), (lx + 8, ly + 34)],
                  fill=(255, 211, 78), width=3)
        feats.append("hanging_lantern")
    # --- second utility pole (right) + one more sagging line ---------
    # v9: at fx 0.96 it clears the narrowed BANH MI board (ends x 1830).
    if len(poles) > 1:
        pole2_x = X(poles[1])
        draw.rectangle([pole2_x - 6, Y(0.08), pole2_x + 6, Y(0.48)],
                       fill=ink)
        pts2 = []
        for x in range(pole_x, pole2_x + 1, 32):
            y = Y(0.16) + 40 * math.sin(math.pi * (x - pole_x)
                                       / max(pole2_x - pole_x, 1))
            pts2.append((x, y))
        draw.line(pts2, fill=ink, width=3)
        feats.append("second_utility_pole")
    # --- hanging shop sign under the first board ----------------------
    hs = data.get("hanging_sign")
    if hs:
        hx0, hy0 = X(hs["fx"]), Y(hs.get("fy", 0.27))
        draw.rectangle([hx0, hy0, hx0 + hs["width"], hy0 + 46],
                       fill=hs["color"], outline=(255, 211, 78), width=3)
        draw.text((hx0 + 10, hy0 + 10), hs["text"], fill=(255, 255, 255),
                  font=_sign_font(hs.get("font", 22)))
        feats.append("hanging_sign_" + _ascii_fold(hs["text"]))
    # --- wet ground: puddles + cracks ---------------------------------
    if data.get("wet_ground", True):
        wet = draw_wet_ground_reflections(draw, w, h, ground_y,
                                          pole_x if poles else 0,
                                          offset_x=offset_x)
        feats += wet
    return feats




# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

LANDMARKS = {
    "great_wall": {
        "title": "Vạn Lý Trường Thành — Great Wall of China",
        "features": ["wall_segments", "watchtowers", "ridge_lines",
                     "crenellations"],
        "boxes": great_wall_boxes,
        "draw_2d": draw_great_wall_2d,
        "sky_top": (122, 164, 214),
        "sky_bottom": (214, 196, 160),
        "ground_color": (74, 94, 68),
    },
    "eiffel_tower": {
        "title": "Tháp Eiffel — Eiffel Tower, Paris",
        "features": ["lattice_legs", "three_platforms", "cross_bracing",
                     "spire", "paris_rooftops"],
        "boxes": eiffel_tower_boxes,
        "draw_2d": draw_eiffel_tower_2d,
        "sky_top": (24, 30, 64),
        "sky_bottom": (96, 72, 96),
        "ground_color": (52, 48, 56),
    },
    "rainy_street": {
        "title": "Phố mưa Việt Nam — Vietnamese rainy street",
        "features": ["power_lines", "utility_pole", "shop_signs",
                     "motorbike", "pavement_tiles", "manhole",
                     "bus_stop_sign"],
        "boxes": None,  # uses the motion-test scene's boxes
        "draw_2d": draw_vietnamese_street_features,
        "sky_top": (18, 30, 58),
        "sky_bottom": (110, 124, 150),
        "ground_color": (64, 58, 52),
    },
}


def landmark_boxes(name):
    """3D box data for ``name`` (list of dicts). Raises KeyError for
    an unknown landmark; rainy_street has no own boxes (it reuses the
    motion-test scene)."""
    if name not in LANDMARKS:
        raise KeyError(f"unknown landmark: {name!r} "
                       f"(expected one of {sorted(LANDMARKS)})")
    fn = LANDMARKS[name]["boxes"]
    return fn() if fn is not None else []


def landmark_features(name):
    return list(LANDMARKS[name]["features"])
