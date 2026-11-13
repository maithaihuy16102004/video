"""Procedural surface textures for Environment Engine V2 (P-S1).

Painted HD textures for walls, roofs and ground surfaces, so facades
stop being flat colour blocks. The painters are original PIL
re-implementations ADAPTED from the texture-painting algorithms in
``paint.ts`` of the MIT-licensed ``claude-animated-shorts`` repo
(see ``THIRD_PARTY_NOTICES.md``): seeded jitter, per-course/per-brick
variation, bevel highlights, blotches, cracks and grime. What was
NOT ported: the source's Broughton colour palette (every painter
here takes its palette from the calling archetype / element colour),
its THREE.js CanvasTexture plumbing, and its window/shutter/door
layout as render behaviour — the window GRID is exposed separately
as :func:`facade_window_layout`, the shared contract P-S2 uses to
unify painted windows with the 3D window elements.

Determinism: every painter is a pure function of its arguments
(including ``seed``); the same arguments always produce identical
pixels. Callers derive the seed from the element id (stable across
processes), so the same location renders the same textures in every
shot and every run.

Cache contract: :func:`texture_for_material` caches by full argument
key and returns the SAME Image object on repeat calls. Cached images
are READ-ONLY — callers must never draw onto them. ``paste_`` helpers
only read/transform, which is safe. :func:`clear_texture_cache`
exists for tests.
"""

from __future__ import annotations

import colorsys
import math
import random

from PIL import Image, ImageDraw, ImageEnhance

# Pixels per world metre inside a generated texture. 72 px/m matches
# the source HD painters; a 6 m facade becomes a 432 px texture.
PX_PER_M = 72
_MAX_TEX_SIDE = 1024
# Faces smaller than this on screen keep the flat fill: texture
# detail cannot read below ~40 px and the flat path is cheaper.
MIN_FACE_PX = 40

__all__ = [
    "PX_PER_M",
    "MIN_FACE_PX",
    "jit_color",
    "darken",
    "facade_window_layout",
    "paint_plaster",
    "paint_brick",
    "paint_stone",
    "paint_roof",
    "paint_cobble",
    "paint_grass",
    "paint_planks",
    "texture_for_material",
    "ground_texture_for",
    "paste_textured_quad",
    "clear_texture_cache",
]


# ------------------------------------------------------------------
# Colour helpers
# ------------------------------------------------------------------

def _as_rgb(color) -> tuple[int, int, int]:
    if isinstance(color, str):
        color = color.lstrip("#")
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    return (int(color[0]), int(color[1]), int(color[2]))


def darken(color, factor: float) -> tuple[int, int, int]:
    """Scale an RGB colour by ``factor`` (0..1 darkens, >1 lightens)."""
    r, g, b = _as_rgb(color)
    return (max(0, min(255, int(round(r * factor)))),
            max(0, min(255, int(round(g * factor)))),
            max(0, min(255, int(round(b * factor)))))


def jit_color(rng: random.Random, color, dv: float = 0.10,
              dh: float = 5.0, ds: float = 0.15) -> tuple[int, int, int]:
    """Jitter a colour in HSL space (adapted from the source ``jit``).

    Hue shifts by up to ``dh`` degrees, saturation and lightness scale
    by up to ``ds`` / ``dv``. Deterministic for a given ``rng`` state.
    """
    r, g, b = _as_rgb(color)
    h, li, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    h = ((h * 360.0 + rng.uniform(-dh, dh)) % 360.0) / 360.0
    s = max(0.0, min(1.0, s * (1.0 + rng.uniform(-ds, ds))))
    li = max(0.0, min(1.0, li * (1.0 + rng.uniform(-dv, dv))))
    r2, g2, b2 = colorsys.hls_to_rgb(h, li, s)
    return (int(round(r2 * 255)), int(round(g2 * 255)),
            int(round(b2 * 255)))


def _tex_size(wm: float, hm: float, px_per_m: int) -> tuple[int, int]:
    w = max(1, int(round(wm * px_per_m)))
    h = max(1, int(round(hm * px_per_m)))
    scale = min(1.0, _MAX_TEX_SIDE / max(w, h))
    if scale < 1.0:
        w = max(1, int(round(w * scale)))
        h = max(1, int(round(h * scale)))
    return w, h


def _blotches(draw: ImageDraw.ImageDraw, rng: random.Random,
              w: int, h: int, base, count: int, r_min: int, r_max: int,
              alpha: int, dv: float = 0.12) -> None:
    """Soft translucent blotches on an RGBA overlay draw context."""
    for _ in range(count):
        cx = rng.randint(0, w)
        cy = rng.randint(0, h)
        rad = rng.randint(r_min, r_max)
        col = jit_color(rng, base, dv=dv)
        draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
                     fill=col + (alpha,))


def _cracks(draw: ImageDraw.ImageDraw, rng: random.Random,
            w: int, h: int, color, count: int) -> None:
    """Thin dark hairline cracks: short downward random walks."""
    for _ in range(count):
        x = rng.uniform(0, w)
        y = rng.uniform(0, h * 0.5)
        pts = [(x, y)]
        for _ in range(rng.randint(3, 7)):
            x += rng.uniform(-8, 8)
            y += rng.uniform(8, 26)
            pts.append((x, y))
        draw.line(pts, fill=color + (28,), width=1)


# ------------------------------------------------------------------
# Facade window grid — the P-S2 shared contract
# ------------------------------------------------------------------

def facade_window_layout(wm: float, hm: float, *, grid: str = "pitch",
                         floor_h: float = 2.8, bay_w: float = 2.2,
                         win_w: float = 0.85, win_h: float = 1.25,
                         sill_h: float = 0.9, rows: int | None = None,
                         cols: int | None = None,
                         u_margin: float = 0.12, u_span: float = 0.76,
                         v_margin: float = 0.10, v_span: float = 0.80,
                         door_w: float = 1.0, door_h: float = 2.1,
                         door_u: float = 0.5) -> dict:
    """Window/door grid for a facade ``wm`` x ``hm`` metres.

    The P-S2 SHARED CONTRACT: the painted windows layer
    (``paint_plaster(windows=True)``) and the 3D window/door
    elements (``environment_v2._facade``) both compute their
    geometry from this one function, with the SAME parameters, so
    painted and geometric openings can never double-draw at
    mismatched positions. Positions are in METRES from the
    facade's bottom-left corner; ``windows`` is a list of
    ``(x_m, y_bottom_m, w_m, h_m)`` and ``door`` is
    ``(x_m, 0.0, w_m, h_m)`` or None.

    Two grid modes:

    * ``grid="pitch"`` (default): the source facade painter's
      grid — one floor per ``floor_h`` metres, one window bay
      per ``bay_w`` metres, windows ``win_w`` x ``win_h`` with
      sills at ``floor * floor_h + sill_h``. Defaults reproduce
      the original grid exactly (2.8 m floors, 2.2 m bays,
      0.85 x 1.25 m windows, 0.9 m sills, centred 1.0 x 2.1 m
      door).
    * ``grid="even"``: the 3D facade grid — ``rows`` x ``cols``
      windows distributed evenly across the wall inside
      fractional margins (``u_margin``/``u_span`` horizontally,
      ``v_margin``/``v_span`` vertically from the TOP, matching
      the ``local_rect`` convention). ``rows``/``cols`` default
      from ``floor_h``/``bay_w`` when not given. The door sits
      at fractional centre ``door_u``. Windows that would fall
      outside the wall are skipped, never clamped (a clamped
      window would disagree with the 3D element).

    ``floors``/``n_win`` report the row/column counts for both
    modes; ``grid`` echoes the mode used.
    """
    if grid not in ("pitch", "even"):
        raise ValueError(f"unknown facade grid: {grid!r} "
                         "(expected 'pitch' or 'even')")
    if grid == "pitch":
        floors = max(1, int(math.floor(hm / floor_h)))
        n_win = max(1, int(math.floor(wm / bay_w)))
        span = n_win * bay_w
        x0 = (wm - span) / 2.0 + (bay_w - win_w) / 2.0
        windows = []
        for fl in range(floors):
            y_bottom = fl * floor_h + sill_h
            if y_bottom + win_h > hm:
                continue
            for i in range(n_win):
                windows.append((x0 + i * bay_w, y_bottom,
                                win_w, win_h))
        door = None
        if hm >= door_h + 0.3 and wm >= door_w + 0.4:
            door = (door_u * wm - door_w / 2.0, 0.0, door_w, door_h)
        return {"grid": grid, "floors": floors, "n_win": n_win,
                "windows": windows, "door": door}
    # grid == "even": even-fraction distribution, rows counted
    # from the TOP (row 0 is the top row, matching _facade).
    n_rows = int(rows) if rows is not None else max(
        1, int(math.floor(hm / floor_h)))
    n_cols = int(cols) if cols is not None else max(
        1, int(math.floor(wm / bay_w)))
    n_rows = max(1, n_rows)
    n_cols = max(1, n_cols)
    windows = []
    for row in range(n_rows):
        v_c = v_margin + v_span * (row + 0.5) / n_rows
        y_bottom = hm * (1.0 - v_c) - win_h / 2.0
        if y_bottom < 0.0 or y_bottom + win_h > hm:
            continue
        for col in range(n_cols):
            u_c = u_margin + u_span * (col + 0.5) / n_cols
            x = u_c * wm - win_w / 2.0
            if x < 0.0 or x + win_w > wm:
                continue
            windows.append((x, y_bottom, win_w, win_h))
    door = None
    if hm >= door_h and wm >= door_w:
        door = (door_u * wm - door_w / 2.0, 0.0, door_w, door_h)
    return {"grid": grid, "floors": n_rows, "n_win": n_cols,
            "windows": windows, "door": door}


def _meters_to_px(x_m: float, y_bottom_m: float, w_m: float, h_m: float,
                  tex_h: int, px_per_m: int) -> tuple[int, int, int, int]:
    """Facade metres (origin bottom-left) -> image pixel box."""
    x0 = int(round(x_m * px_per_m))
    x1 = int(round((x_m + w_m) * px_per_m))
    y1 = tex_h - int(round(y_bottom_m * px_per_m))
    y0 = tex_h - int(round((y_bottom_m + h_m) * px_per_m))
    return x0, y0, x1, y1


# ------------------------------------------------------------------
# Painters. Each returns a NEW RGB Image, deterministic in its args.
# ------------------------------------------------------------------

def paint_plaster(wm: float, hm: float, wall_color, seed: int,
                  px_per_m: int = PX_PER_M, windows: bool = False,
                  trim_color=None, glass_top=None, glass_bottom=None,
                  shutter_color=None, door_color=None,
                  window_layout: dict | None = None) -> Image.Image:
    """Plaster wall: base + blotches + cracks + plinth, optional
    painted windows/door (the windows layer is OFF by default: the
    3D window elements already draw them — see module docstring).
    ``window_layout`` is a :func:`facade_window_layout` dict: when
    given with ``windows=True``, the painted openings use EXACTLY
    that layout (the P-S2 shared contract — the caller passes the
    same layout the 3D elements were built from, so the two can
    never disagree). Without it, the default pitch grid is used."""
    rng = random.Random(seed)
    base = _as_rgb(wall_color)
    w, h = _tex_size(wm, hm, px_per_m)
    img = Image.new("RGB", (w, h), base)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    _blotches(odraw, rng, w, h, base, max(6, w * h // 6000), 15, 90, 16)
    _cracks(odraw, rng, w, h, darken(base, 0.7),
            rng.randint(2, 5))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    # Fine grain, drawn DIRECTLY (alpha would dilute it ~7x): without
    # it the plaster reads as flat at normal shot distances (a 1 m
    # crop of blotches-only texture has std < 1).
    for _ in range(max(50, w * h // 16)):
        gx = rng.randint(0, w - 1)
        gy = rng.randint(0, h - 1)
        gs = rng.randint(1, 2)
        draw.rectangle([gx, gy, gx + gs, gy + gs],
                       fill=jit_color(rng, base, dv=0.12))
    # Plinth: darker band along the bottom 0.4 m.
    plinth_h = int(round(0.4 * px_per_m * h / max(1, hm * px_per_m)))
    plinth_h = max(2, min(h, plinth_h))
    draw.rectangle([0, h - plinth_h, w, h], fill=darken(base, 0.82))
    draw.line([(0, h - plinth_h), (w, h - plinth_h)],
              fill=darken(base, 0.65), width=2)
    if windows:
        _paint_facade_windows(draw, rng, w, h, px_per_m, wm, hm,
                              trim_color, glass_top, glass_bottom,
                              shutter_color, door_color, base,
                              window_layout)
    return img


def _paint_facade_windows(draw, rng, w, h, px_per_m, wm, hm,
                          trim_color, glass_top, glass_bottom,
                          shutter_color, door_color, base,
                          layout: dict | None = None) -> None:
    """Paint the windows/door layer onto a plaster texture."""
    trim = _as_rgb(trim_color) if trim_color else (240, 236, 224)
    gtop = _as_rgb(glass_top) if glass_top else (141, 156, 219)
    gbot = _as_rgb(glass_bottom) if glass_bottom else (87, 97, 168)
    shut = (_as_rgb(shutter_color) if shutter_color
            else darken(base, 0.55))
    door_c = (_as_rgb(door_color) if door_color else darken(base, 0.5))
    if layout is None:
        layout = facade_window_layout(wm, hm)
    scale = h / max(1.0, hm * px_per_m)
    ppm = px_per_m * scale
    for (x_m, y_m, ww_m, wh_m) in layout["windows"]:
        x0, y0, x1, y1 = _meters_to_px(x_m, y_m, ww_m, wh_m, h, ppm)
        # Shutters (0.45 m each side) with louvres.
        sw = int(round(0.45 * ppm))
        for sx0, sx1 in ((x0 - sw, x0), (x1, x1 + sw)):
            if sx0 < 0 or sx1 > w:
                continue
            draw.rectangle([sx0, y0, sx1, y1], fill=shut)
            ly = y0 + 4
            while ly < y1 - 2:
                draw.line([(sx0 + 2, ly), (sx1 - 2, ly)],
                          fill=darken(shut, 0.7), width=1)
                ly += max(3, int(round(0.09 * ppm)))
        # Trim + glass gradient + glint + sill.
        draw.rectangle([x0 - 3, y0 - 3, x1 + 3, y1 + 3], fill=trim)
        gh = max(1, y1 - y0)
        for yy in range(y0, y1):
            t = (yy - y0) / gh
            draw.line([(x0, yy), (x1, yy)],
                      fill=tuple(int(round(gtop[i] * (1 - t)
                                           + gbot[i] * t))
                                 for i in range(3)))
        draw.line([(x0 + 2, y1 - 2), (x1 - 2, y0 + 2)],
                  fill=(255, 255, 255, 70), width=2)
        draw.line([(x0 - 4, y1), (x1 + 4, y1)], fill=trim, width=3)
        # Curtains behind ~35% of windows.
        if rng.random() < 0.35:
            cw = max(2, (x1 - x0) // 3)
            curtain = (232, 226, 210)
            draw.rectangle([x0, y0, x0 + cw, y1], fill=curtain)
            draw.rectangle([x1 - cw, y0, x1, y1], fill=curtain)
        # Cross muntins.
        mx = (x0 + x1) // 2
        my = (y0 + y1) // 2
        draw.line([(mx, y0), (mx, y1)], fill=trim, width=2)
        draw.line([(x0, my), (x1, my)], fill=trim, width=2)
    if layout["door"]:
        x_m, y_m, ww_m, wh_m = layout["door"]
        x0, y0, x1, y1 = _meters_to_px(x_m, y_m, ww_m, wh_m, h, ppm)
        draw.rectangle([x0, y0, x1, y1], fill=door_c)
        draw.pieslice([x0, y0 - (x1 - x0) // 2, x1, y0 + (x1 - x0) // 2],
                      180, 360, fill=door_c)
        draw.rectangle([x0, y0, x1, y1], outline=darken(door_c, 0.7))
        mx = (x0 + x1) // 2
        draw.line([(mx, y0), (mx, y1)], fill=darken(door_c, 0.7), width=2)
        draw.ellipse([x1 - 8, (y0 + y1) // 2 - 3, x1 - 3,
                      (y0 + y1) // 2 + 3], fill=(220, 190, 90))


def paint_brick(wm: float, hm: float, brick_color, seed: int,
                px_per_m: int = PX_PER_M, mortar_color=None) -> Image.Image:
    """Brick courses with per-brick jitter and soot near the top."""
    rng = random.Random(seed)
    base = _as_rgb(brick_color)
    mortar = (_as_rgb(mortar_color) if mortar_color else darken(base, 0.72))
    w, h = _tex_size(wm, hm, px_per_m)
    img = Image.new("RGB", (w, h), mortar)
    draw = ImageDraw.Draw(img)
    bw = 0.215 * px_per_m * w / max(1.0, wm * px_per_m)
    bh = 0.065 * px_per_m * h / max(1.0, hm * px_per_m)
    joint = max(1.0, 0.01 * px_per_m)
    row = 0
    y = 0.0
    while y < h:
        offset = (bw / 2.0) if row % 2 else 0.0
        x = -offset
        while x < w:
            col = jit_color(rng, base, dv=0.12, dh=4, ds=0.12)
            if rng.random() < 0.08:
                col = darken(col, 0.75)
            draw.rectangle([x + joint / 2, y + joint / 2,
                            x + bw - joint / 2, y + bh - joint / 2],
                           fill=col)
            draw.line([(x + joint / 2, y + bh - joint / 2),
                       (x + bw - joint / 2, y + bh - joint / 2)],
                      fill=darken(col, 0.7), width=1)
            x += bw
        y += bh
        row += 1
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for _ in range(rng.randint(2, 4)):
        cx = rng.randint(0, w)
        rad = rng.randint(20, 60)
        odraw.ellipse([cx - rad, -rad // 2, cx + rad, rad],
                      fill=(20, 18, 16, 18))
    return Image.alpha_composite(img.convert("RGBA"),
                                 overlay).convert("RGB")


def paint_stone(wm: float, hm: float, stone_color, seed: int,
                px_per_m: int = PX_PER_M, mortar_color=None) -> Image.Image:
    """Ashlar stone courses: bevelled blocks, speckles, cracks, grime."""
    rng = random.Random(seed)
    base = _as_rgb(stone_color)
    mortar = (_as_rgb(mortar_color) if mortar_color else darken(base, 0.78))
    w, h = _tex_size(wm, hm, px_per_m)
    img = Image.new("RGB", (w, h), mortar)
    draw = ImageDraw.Draw(img)
    sx = w / max(1.0, wm * px_per_m)
    sy = h / max(1.0, hm * px_per_m)
    y = 0.0
    while y < h:
        row_h = rng.uniform(0.35, 0.55) * px_per_m * sy
        x = -rng.uniform(0, 0.6) * px_per_m * sx
        while x < w:
            block_w = rng.uniform(0.8, 1.6) * px_per_m * sx
            col = jit_color(rng, base, dv=0.08, dh=3, ds=0.10)
            x0, y0 = x + 2, y + 2
            x1, y1 = min(w, x + block_w - 2), min(h, y + row_h - 2)
            if x1 <= x0 or y1 <= y0:
                x += block_w
                continue
            draw.rectangle([x0, y0, x1, y1], fill=col)
            draw.line([(x0, y0), (x1, y0)], fill=darken(col, 1.15), width=2)
            draw.line([(x0, y0), (x0, y1)], fill=darken(col, 1.12), width=2)
            draw.line([(x0, y1), (x1, y1)], fill=darken(col, 0.8), width=2)
            draw.line([(x1, y0), (x1, y1)], fill=darken(col, 0.82), width=2)
            x += block_w
        y += row_h
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for _ in range(300):
        odraw.point((rng.randint(0, w - 1), rng.randint(0, h - 1)),
                    fill=darken(base, 0.7) + (22,))
    _cracks(odraw, rng, w, h, darken(base, 0.65), rng.randint(1, 3))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    # Bottom grime band.
    grime_h = max(2, int(round(0.3 * px_per_m * sy)))
    for i in range(grime_h):
        t = i / max(1, grime_h)
        col = darken(base, 0.85 - 0.1 * t)
        draw.line([(0, h - grime_h + i), (w, h - grime_h + i)],
                  fill=col)
    return img


def paint_roof(wm: float, hm: float, base_color, seed: int,
               px_per_m: int = PX_PER_M) -> Image.Image:
    """Roof tile courses running across the slope (v = eave->apex)."""
    rng = random.Random(seed)
    base = _as_rgb(base_color)
    w, h = _tex_size(wm, hm, px_per_m)
    img = Image.new("RGB", (w, h), darken(base, 0.9))
    draw = ImageDraw.Draw(img)
    tw = 0.30 * px_per_m * w / max(1.0, wm * px_per_m)
    rh = 0.18 * px_per_m * h / max(1.0, hm * px_per_m)
    row = 0
    y = 0.0
    while y < h:
        offset = (tw / 2.0) if row % 2 else 0.0
        x = -offset
        while x < w:
            col = jit_color(rng, base, dv=0.10, dh=3, ds=0.10)
            draw.rectangle([x + 1, y, x + tw - 1, y + rh], fill=col)
            draw.line([(x + 1, y + rh - 1), (x + tw - 1, y + rh - 1)],
                      fill=darken(col, 0.65), width=2)
            draw.line([(x + 1, y), (x + tw - 1, y)],
                      fill=darken(col, 1.1), width=1)
            x += tw
        y += rh
        row += 1
    return img


def paint_cobble(wm: float, hm: float, stone_color, seed: int,
                 px_per_m: int = PX_PER_M, joint_color=None) -> Image.Image:
    """Staggered cobblestone setts (ground painter; P-S5 use)."""
    rng = random.Random(seed)
    base = _as_rgb(stone_color)
    joint = (_as_rgb(joint_color) if joint_color else darken(base, 0.6))
    w, h = _tex_size(wm, hm, px_per_m)
    img = Image.new("RGB", (w, h), joint)
    draw = ImageDraw.Draw(img)
    sw = 0.18 * px_per_m * w / max(1.0, wm * px_per_m)
    sh = 0.12 * px_per_m * h / max(1.0, hm * px_per_m)
    row = 0
    y = 0.0
    while y < h:
        offset = (sw / 2.0) if row % 2 else 0.0
        x = -offset
        while x < w:
            col = jit_color(rng, base, dv=0.12, dh=3, ds=0.10)
            pad_x = min(2.0, sw * 0.2)
            pad_y = min(2.0, sh * 0.2)
            draw.rounded_rectangle(
                [x + pad_x, y + pad_y, x + sw - pad_x, y + sh - pad_y],
                radius=3, fill=col)
            if sw >= 8:
                draw.line([(x + 4, y + 3), (x + sw - 4, y + 3)],
                          fill=darken(col, 1.12), width=1)
            x += sw
        y += sh
        row += 1
    return img


def paint_grass(wm: float, hm: float, base_color, seed: int,
                px_per_m: int = PX_PER_M) -> Image.Image:
    """Grass: blotches + tufts + sparse flowers (ground painter)."""
    rng = random.Random(seed)
    base = _as_rgb(base_color)
    w, h = _tex_size(wm, hm, px_per_m)
    img = Image.new("RGB", (w, h), base)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    _blotches(odraw, rng, w, h, base, max(8, w * h // 4000), 10, 50, 26,
              dv=0.16)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    for _ in range(max(20, w * h // 150)):
        x = rng.randint(0, w - 1)
        y = rng.randint(0, h - 1)
        col = jit_color(rng, base, dv=0.18, dh=8, ds=0.2)
        ln = rng.randint(2, 6)
        draw.line([(x, y), (x + rng.randint(-2, 2), y - ln)], fill=col,
                  width=1)
    for _ in range(max(2, w * h // 4000)):
        x = rng.randint(0, w - 1)
        y = rng.randint(0, h - 1)
        col = rng.choice([(245, 240, 225), (240, 220, 90), (235, 170, 190)])
        draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=col)
    return img


def paint_planks(wm: float, hm: float, wood_color, seed: int,
                 px_per_m: int = PX_PER_M) -> Image.Image:
    """Vertical wood planks: grain, knots, nails, seams.

    Wired since the P-S2 round via :func:`texture_for_material`:
    the caller-side size gate (``MIN_FACE_PX`` in
    ``environment_v2._face_texture``) keeps small colour-critical
    wood elements flat, and the plank colours are tinted from the
    element's own colour, so hue is preserved.
    """
    rng = random.Random(seed)
    base = _as_rgb(wood_color)
    w, h = _tex_size(wm, hm, px_per_m)
    img = Image.new("RGB", (w, h), darken(base, 0.6))
    draw = ImageDraw.Draw(img)
    bw = 0.15 * px_per_m * w / max(1.0, wm * px_per_m)
    x = 0.0
    while x < w:
        col = jit_color(rng, base, dv=0.08, dh=3, ds=0.10)
        draw.rectangle([x + 1, 0, x + bw - 1, h], fill=col)
        for _ in range(rng.randint(3, 5)):
            gx = x + rng.uniform(3, max(4, bw - 3))
            pts = [(gx, 0)]
            yy = 0.0
            while yy < h:
                yy += rng.uniform(12, 30)
                pts.append((gx + rng.uniform(-2, 2), min(yy, h)))
            draw.line(pts, fill=darken(col, 0.75), width=1)
        if rng.random() < 0.3:
            kx, ky = x + bw / 2, rng.uniform(h * 0.2, h * 0.8)
            draw.ellipse([kx - 5, ky - 8, kx + 5, ky + 8],
                         outline=darken(col, 0.65), width=2)
            draw.ellipse([kx - 2, ky - 3, kx + 2, ky + 3],
                         fill=darken(col, 0.7))
        for ny in (6, h - 6):
            draw.ellipse([x + bw / 2 - 2, ny - 2, x + bw / 2 + 2, ny + 2],
                         fill=(40, 32, 24))
        draw.line([(x, 0), (x, h)], fill=darken(base, 0.55), width=1)
        x += bw
    return img


# ------------------------------------------------------------------
# Material mapping + cache
# ------------------------------------------------------------------

_TEXTURE_CACHE: dict = {}


def clear_texture_cache() -> None:
    """Empty the texture cache (tests)."""
    _TEXTURE_CACHE.clear()


def texture_for_material(material: str, base_color, wm: float, hm: float,
                         seed: int, px_per_m: int = PX_PER_M):
    """Texture for an environment element face, or None if the
    material keeps the flat fill. Cached; the returned image is
    READ-ONLY (see module docstring). ``windows=False`` for plaster:
    the 3D window/door elements already draw the openings, and the
    painted grid would double-draw at mismatched positions until
    P-S2 unifies the grids. Wood maps to planks (P-S2): the
    caller-side ``MIN_FACE_PX`` size gate keeps small
    colour-critical wood faces flat."""
    key = (material, _as_rgb(base_color), round(float(wm), 3),
           round(float(hm), 3), int(seed), int(px_per_m))
    hit = _TEXTURE_CACHE.get(key)
    if hit is not None:
        return hit
    if material == "plaster":
        img = paint_plaster(wm, hm, base_color, seed, px_per_m,
                            windows=False)
    elif material == "brick":
        img = paint_brick(wm, hm, base_color, seed, px_per_m)
    elif material in ("stone", "marble"):
        img = paint_stone(wm, hm, base_color, seed, px_per_m)
    elif material == "roof_tile":
        img = paint_roof(wm, hm, base_color, seed, px_per_m)
    elif material == "wood":
        img = paint_planks(wm, hm, base_color, seed, px_per_m)
    else:
        return None
    _TEXTURE_CACHE[key] = img
    return img


# Ground-kind -> painter (P-S2/P-S6 ground painting). Every painter
# takes its palette from the ground colour, so the ground stays
# palette-driven; kinds with no painter keep the gradient fill.
_GROUND_PAINTERS = {
    "cobblestone": paint_cobble,
    "grass": paint_grass,
    "forest_floor": paint_grass,
    "pale_stone": paint_stone,
    "dark_stone": paint_stone,
    "asphalt": paint_stone,
    "wood_floor": paint_planks,
    "sand": paint_plaster,
    "packed_earth": paint_plaster,
    "mud": paint_plaster,
}


def ground_texture_for(ground_kind: str, base_color, wm: float,
                       hm: float, seed: int,
                       px_per_m: int = PX_PER_M):
    """Texture for a ground-plane band, or None when the ground kind
    keeps the gradient fill (``neutral`` and unknown kinds — no
    material declared, nothing invented). Cached like
    :func:`texture_for_material`; the returned image is READ-ONLY.
    Plaster ground bands paint with ``windows=False`` (a ground
    plane has no facade openings)."""
    painter = _GROUND_PAINTERS.get(str(ground_kind or "").lower())
    if painter is None:
        return None
    key = ("ground:" + str(ground_kind).lower(), _as_rgb(base_color),
           round(float(wm), 3), round(float(hm), 3), int(seed),
           int(px_per_m))
    hit = _TEXTURE_CACHE.get(key)
    if hit is not None:
        return hit
    if painter is paint_plaster:
        img = painter(wm, hm, base_color, seed, px_per_m, windows=False)
    else:
        img = painter(wm, hm, base_color, seed, px_per_m)
    _TEXTURE_CACHE[key] = img
    return img


# ------------------------------------------------------------------
# Quad pasting (perspective-mapped texture onto a projected face)
# ------------------------------------------------------------------

def _solve_linear(matrix, vector):
    """Solve a small dense linear system by Gaussian elimination
    with partial pivoting. Returns the solution list, or None if
    the matrix is (near-)singular."""
    n = len(vector)
    aug = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[piv][col]) < 1e-12:
            return None
        aug[col], aug[piv] = aug[piv], aug[col]
        pivval = aug[col][col]
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col] / pivval
            if factor == 0.0:
                continue
            for c in range(col, n + 1):
                aug[r][c] -= factor * aug[col][c]
    return [aug[i][n] / aug[i][i] for i in range(n)]


def _perspective_coeffs(quad, tex_size):
    """PIL PERSPECTIVE coefficients mapping target ``quad`` pixels
    to texture pixels. ``quad`` winding must be the consistent
    face loop (bottom-left, top-left, top-right, bottom-right in
    the face's local frame) produced by the box/gable projectors;
    the texture is mapped upright onto that loop."""
    tw, th = tex_size
    src = [(0.0, float(th)), (0.0, 0.0), (float(tw), 0.0),
           (float(tw), float(th))]
    matrix = []
    vector = []
    for (x, y), (u, v) in zip(quad, src):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        vector.extend([u, v])
    coeffs = _solve_linear(matrix, vector)
    return tuple(coeffs) if coeffs is not None else None


def _is_axis_rect(quad, w: int, h: int) -> bool:
    corners = {(0.0, 0.0), (float(w), 0.0), (float(w), float(h)),
               (0.0, float(h))}
    got = {(round(float(x), 1), round(float(y), 1)) for x, y in quad}
    return got == corners


def paste_textured_quad(img: Image.Image, quad, texture: Image.Image,
                        irradiance: float = 1.0,
                        gain: tuple[float, float, float] | None = None
                        ) -> None:
    """Paste ``texture`` onto ``img`` inside the projected ``quad``
    (4 screen points, face-loop winding — see
    :func:`_perspective_coeffs`), shaded by ``irradiance`` the same
    way the flat fill is (``colour * min(1.0, irr)``). Pixels
    outside the quad are untouched; degenerate quads are no-ops.
    Works on RGB and RGBA canvases. ``texture`` is never mutated.

    ``gain`` (optional, B2) is a per-channel multiplier applied
    AFTER the brightness scaling: the point-light tint pass
    (``lighting.point_light_gain``) for textured faces, so a blue
    energy pulse cools a stone wall instead of only brightening
    it. ``None`` (default) or the unit gain reproduces the exact
    previous behaviour.
    """
    xs = [float(p[0]) for p in quad]
    ys = [float(p[1]) for p in quad]
    area2 = abs(sum(quad[i][0] * quad[(i + 1) % 4][1]
                    - quad[(i + 1) % 4][0] * quad[i][1]
                    for i in range(4)))
    if area2 < 1.0:
        return  # degenerate / zero-area quad
    bx0 = max(0, int(math.floor(min(xs))))
    by0 = max(0, int(math.floor(min(ys))))
    bx1 = min(img.width, int(math.ceil(max(xs))))
    by1 = min(img.height, int(math.ceil(max(ys))))
    w, h = bx1 - bx0, by1 - by0
    if w < 1 or h < 1:
        return
    local = [(x - bx0, y - by0) for x, y in zip(xs, ys)]
    if _is_axis_rect(local, w, h):
        patch = texture.resize((w, h), Image.LANCZOS)
    else:
        coeffs = _perspective_coeffs(local, texture.size)
        if coeffs is None:
            return
        patch = texture.transform((w, h), Image.PERSPECTIVE, coeffs,
                                  Image.BICUBIC)
    irr = max(0.0, min(1.0, float(irradiance)))
    if irr < 1.0:
        patch = ImageEnhance.Brightness(patch).enhance(irr)
    if gain is not None and tuple(gain) != (1.0, 1.0, 1.0):
        rgb = patch.convert("RGB")
        bands = []
        for ch in range(3):
            lut = [min(255, int(round(i * float(gain[ch]))))
                   for i in range(256)]
            bands.append(rgb.getchannel(ch).point(lut))
        patch = Image.merge("RGB", bands)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(local, fill=255)
    if img.mode == "RGBA":
        base = img.crop((bx0, by0, bx1, by1))
        out = Image.composite(patch.convert("RGBA"), base, mask)
        img.paste(out, (bx0, by0))
    else:
        img.paste(patch.convert(img.mode), (bx0, by0), mask)
