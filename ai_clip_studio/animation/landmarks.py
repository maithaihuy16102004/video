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

def draw_vietnamese_street_features(draw, w, h, ground_y):
    """Real-world Vietnamese street details, drawn as a 2D overlay on
    a night-street frame (the motion-test scene). Engine-level
    location features -- every rainy-street scene gets them, no story
    hardcoding: sagging power lines + a utility pole, a parked
    motorbike at the kerb, vertical shop signs (PHO / CA PHE /
    BANH MI), pavement tiles + a manhole + a drain grate.

    Returns the list of features drawn (for the rubric).
    """
    ink = (16, 18, 26)
    # --- power lines: 2 sagging curves across the top + a pole ------
    pole_x = int(w * 0.06)
    draw.rectangle([pole_x - 7, int(h * 0.06), pole_x + 7, int(h * 0.52)],
                   fill=ink)
    draw.line([(pole_x - 60, int(h * 0.10)), (pole_x + 60, int(h * 0.10))],
              fill=ink, width=6)
    for y0, sag in ((int(h * 0.07), 46), (int(h * 0.12), 58)):
        pts = []
        for x in range(0, w + 1, 32):
            # catenary-ish sag, deepest mid-frame
            y = y0 + sag * math.sin(math.pi * x / w)
            pts.append((x, y))
        draw.line(pts, fill=ink, width=3)
    # --- shop signs: vertical boards on the facades ------------------
    try:
        from PIL import ImageFont
        f_sign = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
        f_small = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
    except OSError:
        f_sign = f_small = None
    # v8: the CA PHE board sits at fx 0.60, not 0.55 -- at 0.55 it
    # overlapped the bus-stop sign face (x 901-1097, the CA PHE board
    # at 1056-1246 covered its right 41 px, hiding the "T" of
    # "TRẠM XE BUÝT"). At 0.60 (1152-1342) it is clear of the sign
    # AND of Lan's head (x 1370-1636).
    signs = [(0.30, "PHỞ", (150, 40, 40), f_sign),
             (0.60, "CÀ PHÊ", (40, 70, 130), f_sign),
             (0.86, "BÁNH MÌ", (150, 120, 30), f_small)]
    for fx, text, col, fnt in signs:
        x0 = int(w * fx)
        y0 = int(h * 0.16)
        draw.rectangle([x0, y0, x0 + 190, y0 + 64], fill=col,
                       outline=(255, 211, 78), width=3)
        draw.text((x0 + 12, y0 + 12), text, fill=(255, 255, 255), font=fnt)
    # --- motorbike parked at the right kerb (side view, silhouette) --
    bx, by = int(w * 0.80), ground_y - 6
    wheel_r = 30
    for wx in (bx - 62, bx + 62):
        draw.ellipse([wx - wheel_r, by - wheel_r, wx + wheel_r, by + wheel_r],
                     outline=ink, width=7)
        draw.ellipse([wx - 8, by - 8, wx + 8, by + 8], fill=ink)
    # frame: rear wheel -> seat -> handlebar -> front wheel
    draw.line([(bx - 62, by), (bx - 10, by - 46)], fill=ink, width=7)
    draw.line([(bx - 10, by - 46), (bx + 30, by - 52)], fill=ink, width=7)
    draw.line([(bx + 30, by - 52), (bx + 62, by)], fill=ink, width=7)
    draw.line([(bx - 10, by - 46), (bx + 6, by - 6)], fill=ink, width=6)
    draw.rectangle([bx - 34, by - 62, bx + 6, by - 48], fill=ink)  # seat
    draw.line([(bx + 30, by - 52), (bx + 44, by - 78)], fill=ink, width=6)
    draw.line([(bx + 44, by - 78), (bx + 62, by - 72)], fill=ink, width=5)
    draw.ellipse([bx + 62 - 6, by - 10, bx + 62 + 6, by + 2],
                 fill=(255, 211, 78))  # headlight
    # --- pavement: tile grid + manhole + drain grate -----------------
    for gx in range(0, w, 150):
        draw.line([(gx, ground_y + 40), (gx - 60, h)], fill=(90, 86, 78),
                  width=2)
    draw.line([(0, ground_y + 70), (w, ground_y + 70)], fill=(90, 86, 78),
              width=2)
    draw.ellipse([int(w * 0.42), ground_y + 96, int(w * 0.42) + 90,
                  ground_y + 126], fill=(30, 30, 34),
                 outline=(90, 86, 78), width=2)
    for i in range(4):
        gx = int(w * 0.10) + i * 26
        draw.line([(gx, ground_y + 150), (gx, ground_y + 178)],
                  fill=(20, 20, 24), width=6)
    return ["power_lines", "utility_pole", "shop_sign_pho",
            "shop_sign_ca_phe", "shop_sign_banh_mi", "motorbike",
            "pavement_tiles", "manhole", "drain_grate"]


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
