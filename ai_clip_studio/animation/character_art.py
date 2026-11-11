"""Character art v2 for AI Clip Studio -- Premium Stickman Cinematic B.

Replaces the old straight-line stickman (``draw_character`` in the
acceptance-loop renderers: 7-18 px lines, a flat circle head, a single
arc/line mouth) with a *structured* figure built from the same V51
12-joint rig (``ai_clip_studio.animation.rig.Stickman.joints()``):

  * torso: a structured jacket -- rounded trapezoid, collar, shirt V,
    lapels, buttons, inner shirt layer -- instead of one thick line;
  * arms/legs: thick sleeves / trouser legs with rounded joints, skin
    hands, shoes with toes;
  * head: hair block, eyebrows, eyes with pupils, nose, a mouth that
    changes with ``mood`` (neutral / worried / smile / speak / relief),
    blush on smile/relief;
  * a soft ground shadow under the feet.

Style stays flat Premium Stickman Cinematic B, V51 palette
(#FFD34E, #FF6B5E, #F3F0E8, #172033, #47BD75) and V51 headRatio 0.146
(the rig itself enforces it: ``char.head_r == 0.146 * char.H / 2``).

``draw_character_v2(draw, char, mood, palette)`` takes a PIL
ImageDraw, a rig ``Stickman`` (pose already set via ``set_pose()`` /
IK targets) and returns the joint map, like the old renderer.
"""
from __future__ import annotations

import math

from .rig import Stickman  # noqa: F401  (re-exported for callers)

# V51 palette -- Premium Stickman Cinematic B.
PALETTE_V51 = {
    "yellow": "#FFD34E",
    "red": "#FF6B5E",
    "cream": "#F3F0E8",
    "dark": "#172033",
    "green": "#47BD75",
    "skin": "#F0C8A0",
    "hair": "#222222",
    "blush": "#FF9A8A",
    "shadow": (0, 0, 0, 70),
}

MOODS = ("neutral", "worried", "smile", "speak", "relief")


def _hex(rgb):
    if isinstance(rgb, str):
        rgb = rgb.lstrip("#")
        return tuple(int(rgb[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(rgb)


def _shade(color, factor):
    r, g, b = _hex(color)
    return (max(0, min(255, int(r * factor))),
            max(0, min(255, int(g * factor))),
            max(0, min(255, int(b * factor))))


def _thick(d, a, b, width, color):
    """Thick segment with rounded caps (line + joint circles)."""
    d.line([a, b], fill=color, width=int(width))
    r = width / 2.0
    for p in (a, b):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def draw_character_v2(draw, char, mood="neutral", palette=None):
    """Draw a structured character from ``char.joints()``.

    draw: PIL ImageDraw (ideally ``ImageDraw.Draw(img, "RGBA")`` so the
    ground shadow blends; on plain RGB the shadow still draws dark).
    char: ``Stickman`` with its pose already set.
    mood: 'neutral' | 'worried' | 'smile' | 'speak' | 'relief'.
    palette: optional dict overriding suit/skin/accent colours.
    Returns the joint map from ``char.joints()``.
    """
    if mood not in MOODS:
        mood = "neutral"
    pal = dict(PALETTE_V51)
    if palette:
        pal.update(palette)
    suit = getattr(char, "suit", pal["dark"])
    skin = getattr(char, "skin", pal["skin"])
    dark = pal["dark"]
    cream = pal["cream"]
    hair_c = pal["hair"]

    J = char.joints()
    f = J["facing"]
    H = float(char.H)
    head_r = char.head_r
    hip = J["hip"]
    shoulder = J["shoulder"]
    neck = J["neck"]
    head = J["head"]

    # --- ground shadow (drawn first, under everything) -----------------
    feet_y = max(J["foot_l"][1], J["foot_r"][1])
    feet_x = (J["foot_l"][0] + J["foot_r"][0]) / 2.0
    shadow_w = H * 0.30
    draw.ellipse([feet_x - shadow_w, feet_y - 6,
                  feet_x + shadow_w, feet_y + 14],
                 fill=pal["shadow"])

    # --- legs: thick trouser legs + shoes -------------------------------
    leg_w = max(14.0, 0.036 * H)
    suit_far = _shade(suit, 0.72)
    for side, col in (("l", suit_far), ("r", suit)):
        _thick(draw, hip, J[f"knee_{side}"], leg_w, col)
        _thick(draw, J[f"knee_{side}"], J[f"foot_{side}"],
               leg_w * 0.92, col)
        fx, fy = J[f"foot_{side}"]
        # shoe: ellipse with a toe pointing toward facing
        draw.ellipse([fx - 16, fy - 9, fx + 16, fy + 9], fill="#111111")
        draw.ellipse([fx + f * 8 - 12, fy - 7,
                      fx + f * 8 + 16, fy + 7], fill="#111111")

    # --- torso: structured jacket ---------------------------------------
    # spine direction hip -> shoulder, perpendicular = jacket width axis
    sx, sy = shoulder[0] - hip[0], shoulder[1] - hip[1]
    slen = math.hypot(sx, sy) or 1.0
    ux, uy = sx / slen, sy / slen
    px, py = -uy, ux
    w_top = 0.058 * H
    w_bot = 0.078 * H
    jacket = [
        (shoulder[0] + px * w_top, shoulder[1] + py * w_top),
        (shoulder[0] - px * w_top, shoulder[1] - py * w_top),
        (hip[0] - px * w_bot, hip[1] - py * w_bot),
        (hip[0] + px * w_bot, hip[1] + py * w_bot),
    ]
    draw.polygon(jacket, fill=suit, outline=_shade(suit, 0.6))
    # shirt V (inner layer) from the neck down the chest
    # NOTE: (ux, uy) points hip -> shoulder (up the spine), so going
    # DOWN the torso from the shoulder is -u.
    chest = (shoulder[0] - ux * 0.55 * slen, shoulder[1] - uy * 0.55 * slen)
    draw.polygon([
        (neck[0] + px * w_top * 0.45, neck[1] + py * w_top * 0.45),
        (neck[0] - px * w_top * 0.45, neck[1] - py * w_top * 0.45),
        chest,
    ], fill=cream)
    # lapels: two triangles flanking the shirt V
    for sgn in (+1, -1):
        draw.polygon([
            (neck[0] + px * w_top * 0.55 * sgn,
             neck[1] + py * w_top * 0.55 * sgn),
            (shoulder[0] + px * w_top * 0.95 * sgn,
             shoulder[1] + py * w_top * 0.95 * sgn),
            chest,
        ], fill=_shade(suit, 0.85))
    # collar: small band at the neck
    draw.polygon([
        (neck[0] + px * w_top * 0.5, neck[1] + py * w_top * 0.5),
        (neck[0] - px * w_top * 0.5, neck[1] - py * w_top * 0.5),
        (shoulder[0] - px * w_top * 0.4, shoulder[1] - py * w_top * 0.4),
        (shoulder[0] + px * w_top * 0.4, shoulder[1] + py * w_top * 0.4),
    ], fill=cream)
    # --- arms: thick sleeves, skin hands --------------------------------
    arm_w = max(12.0, 0.030 * H)
    for side, col in (("l", suit_far), ("r", suit)):
        _thick(draw, shoulder, J[f"elbow_{side}"], arm_w, col)
        _thick(draw, J[f"elbow_{side}"], J[f"hand_{side}"],
               arm_w * 0.92, col)
        hx, hy = J[f"hand_{side}"]
        hr = max(10.0, 0.021 * H)
        draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=skin)

    # buttons down the jacket front -- after the arms, so they stay
    # visible on the chest (the near arm hangs in front of the torso
    # in side view and would otherwise hide them)
    for t in (0.30, 0.55, 0.80):
        bx = shoulder[0] - ux * t * slen + px * w_top * 0.12
        by = shoulder[1] - uy * t * slen + py * w_top * 0.12
        draw.ellipse([bx - 4, by - 4, bx + 4, by + 4], fill=cream)

    # --- head ------------------------------------------------------------
    hx, hy = head
    r = head_r
    # long hair (behind the head, down to the shoulder) if the rig has it
    if getattr(char, "long_hair", False):
        draw.rectangle([hx - f * r - r * 0.9, hy - r * 0.4,
                        hx - f * r + r * 0.1, hy + r * 1.6], fill=hair_c)
    # face
    draw.ellipse([hx - r, hy - r, hx + r, hy + r], fill=skin,
                 outline=suit, width=3)
    # hair block: cap over the top/back of the head
    draw.pieslice([hx - r, hy - r, hx + r, hy + r * 0.5], 180, 360,
                  fill=hair_c)
    draw.ellipse([hx - r, hy - r * 0.9, hx - f * r * 0.2, hy - r * 0.1],
                 fill=hair_c)
    # bowler hat, if the rig carries one
    if getattr(char, "hat", None):
        draw.ellipse([hx - r * 1.15, hy - r * 1.05, hx + r * 1.15,
                      hy - r * 0.72], fill=dark)
        draw.rectangle([hx - r * 0.62, hy - r * 1.75,
                        hx + r * 0.62, hy - r * 0.85], fill=dark)
    # nose (small mark toward facing)
    nx, ny = hx + f * r * 0.72, hy + r * 0.08
    draw.line([(nx - f * 4, ny - 4), (nx + f * 5, ny + 2)], fill=dark,
              width=3)
    # moustache, if the rig carries one
    if getattr(char, "moustache", False):
        mx0, my0 = hx + f * r * 0.25, hy + r * 0.28
        draw.arc([mx0 - 16, my0 - 6, mx0 + 16, my0 + 8], 0, 180,
                 fill=dark, width=4)

    # eyes: two eyes, pupils toward facing; relief = closed happy eyes
    eye_y = hy - r * 0.12
    eye_dx = f * r * 0.38
    eye2_dx = -f * r * 0.28
    if mood == "relief":
        for ex in (hx + eye_dx, hx + eye2_dx):
            draw.arc([ex - 7, eye_y - 6, ex + 7, eye_y + 6], 180, 360,
                     fill=dark, width=4)
    else:
        for ex, ew in ((hx + eye_dx, 6.5), (hx + eye2_dx, 5.5)):
            draw.ellipse([ex - ew, eye_y - 7, ex + ew, eye_y + 7],
                         fill="white", outline=dark, width=2)
            draw.ellipse([ex + f * 2 - 3.5, eye_y - 3.5,
                          ex + f * 2 + 3.5, eye_y + 3.5], fill=dark)
    # eyebrows: angle carries the mood (worried = inner ends down)
    brow_y = eye_y - r * 0.42
    for ex in (hx + eye_dx, hx + eye2_dx):
        if mood == "worried":
            inner = (ex - f * 7, brow_y + 10)
            outer = (ex + f * 7, brow_y - 4)
        elif mood in ("smile", "relief"):
            inner = (ex - f * 7, brow_y - 3)
            outer = (ex + f * 7, brow_y - 6)
        else:
            inner = (ex - f * 7, brow_y)
            outer = (ex + f * 7, brow_y)
        draw.line([inner, outer], fill=dark, width=4)
    # sweat drop on the temple when worried
    if mood == "worried":
        sx0, sy0 = hx - f * r * 0.85, hy - r * 0.55
        draw.ellipse([sx0 - 6, sy0 - 9, sx0 + 6, sy0 + 9],
                     fill=(180, 220, 255), outline=dark, width=2)

    # blush on smile / relief (bigger on relief)
    if mood in ("smile", "relief"):
        br = 9 if mood == "smile" else 13
        draw.ellipse([hx + f * r * 0.55 - br, hy + r * 0.18 - br * 0.7,
                      hx + f * r * 0.55 + br, hy + r * 0.18 + br * 0.7],
                     fill=pal["blush"])

    # mouth by mood -- the main expression carrier
    mx, my = hx + f * r * 0.20, hy + r * 0.45
    if mood == "smile":
        draw.arc([mx - 15, my - 9, mx + 15, my + 11], 15, 165,
                 fill=dark, width=5)
    elif mood == "relief":
        draw.arc([mx - 16, my - 10, mx + 16, my + 12], 15, 165,
                 fill=dark, width=5)
        draw.arc([mx - 8, my + 12, mx + 8, my + 18], 15, 165,
                 fill=dark, width=3)
    elif mood == "worried":
        draw.arc([mx - 18, my - 4, mx + 18, my + 16], 195, 345,
                 fill=dark, width=6)
    elif mood == "speak":
        draw.ellipse([mx - 8, my - 5, mx + 8, my + 9], fill=dark)
        draw.ellipse([mx - 4, my + 1, mx + 4, my + 7], fill=pal["red"])
    else:  # neutral
        draw.line([(mx - 12, my), (mx + 12, my)], fill=dark, width=4)
    return J
