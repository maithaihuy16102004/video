"""Frame-by-frame 2.5D renderer (PIL) — the fallback when no Chrome runs.

Every pixel position comes from ``PerspectiveCamera.project()``: the
ground grid is projected line by line, boxes are projected cuboids
whose visible faces are shaded by the real light rig, and contact
shadows are projected ellipses from ``lighting.contact_shadow()``.
Depth is therefore REAL perspective — a far box is smaller because
``focal / depth`` says so, and a camera dolly shifts near layers more
than far ones because the projection says so. No vignette or gradient
is used to fake depth anywhere in this module (the sky is a vertical
colour ramp only, above the horizon).

What this renderer deliberately does NOT do (see README.md matrix):
no shadow maps, no PBR materials, no occlusion between boxes beyond
painter's order, no volumetric light. Character bodies are billboard
markers unless a caller passes ``draw_character`` — the real character
art is plugged in by the caller, never re-drawn here.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter

from .camera import PerspectiveCamera
from .lighting import contact_shadow, shade
from .scene import BOX_FACES, Box3D, CharacterAnchor, Scene25D


def _sky(img: Image.Image, top, bottom, horizon_frac: float = 0.52):
    """Vertical colour ramp for the sky only (above the horizon line)."""
    w, h = img.size
    d = ImageDraw.Draw(img)
    horizon = int(h * horizon_frac)
    for y in range(horizon):
        t = y / max(horizon - 1, 1)
        d.line([(0, y), (w, y)], fill=tuple(
            int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))


def _project_clipped(cam: PerspectiveCamera, p, width, height):
    """Project, clamping near-plane crossings so grid lines behind the
    camera do not wrap around to the front of the frame."""
    x, y, z = p
    _, _, zc = cam.view_coords((x, y, z))
    if zc <= cam.near:
        # pull the point just in front of the near plane along the
        # camera-forward axis; the line then exits the frame cleanly.
        fwd = cam._fwd
        p = (x + fwd[0] * (cam.near - zc + 0.01),
             y + fwd[1] * (cam.near - zc + 0.01),
             z + fwd[2] * (cam.near - zc + 0.01))
    return cam.project(p, width, height)


def _draw_ground_grid(img: Image.Image, scene: Scene25D, cam: PerspectiveCamera):
    """Ground plane (y=0) as a projected grid + a solid ground fill.

    The horizon is where the ground plane meets the sky: it is the
    projection of the far edge of the ground, not a painted line.
    """
    w, h = img.size
    # NOTE: PIL ImageDraw does NOT alpha-blend on an RGBA image — it
    # replaces pixels, so a (255,255,255,16) line would become opaque
    # white after convert("RGB"). Grid lines therefore go on a separate
    # overlay that is alpha-composited.
    d = ImageDraw.Draw(img)
    ext = scene.ground_extent
    # solid ground: polygon of the 4 far/near ground corners
    corners = [(-ext, 0.0, -ext), (ext, 0.0, -ext),
               (ext, 0.0, ext), (-ext, 0.0, ext)]
    pts = []
    for c in corners:
        x, y, _, vis = _project_clipped(cam, c, w, h)
        pts.append((x, y))
    d.polygon(pts, fill=scene.ground_color)
    # grid lines every 2 world units, faint white, on an overlay
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    step = 2.0
    n = int(ext / step)
    for i in range(-n, n + 1):
        xw = i * step
        for a, b in (((xw, 0.0, -ext), (xw, 0.0, ext)),
                     ((-ext, 0.0, xw), (ext, 0.0, xw))):
            xa, ya, _, _ = _project_clipped(cam, a, w, h)
            xb, yb, _, _ = _project_clipped(cam, b, w, h)
            od.line([(xa, ya), (xb, yb)], fill=(255, 255, 255, 22), width=1)
    img.alpha_composite(overlay)


def _horizon_y(scene: Scene25D, cam: PerspectiveCamera,
               width: int, height: int) -> float:
    """Screen y of the ground plane's far edge (the horizon line).

    The ground polygon's top edge is the projection of its far edge
    (z = -ground_extent); nothing that lies ON the ground may ever be
    drawn above it. Returns a value clamped to [0, height]: when the
    horizon is off-frame the clip is a no-op.
    """
    ext = scene.ground_extent
    ys = []
    for c in ((-ext, 0.0, -ext), (ext, 0.0, -ext)):
        _, y, _, vis = _project_clipped(cam, c, width, height)
        if vis:
            ys.append(y)
    if not ys:
        return 0.0
    return min(max(min(ys), 0.0), float(height))


def _draw_contact_shadow(img: Image.Image, scene: Scene25D,
                         cam: PerspectiveCamera, ground_pos, height,
                         base_radius: float, horizon_y: float | None = None):
    """Blurred ellipse on the ground, from lighting.contact_shadow().

    Stage 3: the ellipse is CLIPPED to the ground (never above
    ``horizon_y``). A contact shadow lies on the ground plane; the
    unclipped ellipse of a wide box extends hundreds of pixels above
    the horizon and darkens the sky (the dark-daytime bug: a day sky
    ramp of ~(140, 183, 221) rendered as (28, 37, 45)). The clip is
    applied after the blur, so no blurred fringe leaks into the sky.
    ``horizon_y=None`` keeps the old unclipped behaviour for direct
    callers; render_frame always passes the horizon.
    """
    sh = contact_shadow(ground_pos, height, base_radius, scene.lights.key)
    cx, cz = sh["center"]
    # ellipse axes in world units -> project the two axis end points
    px, py, pscale, vis = cam.project((cx, 0.0, cz), *img.size)
    if not vis:
        return
    rx = sh["radius_x"] * pscale
    rz = sh["radius_z"] * pscale
    if rx < 1 or rz < 1:
        return
    blur = max(1, int(2 + height * 6))
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer)
    alpha = int(255 * sh["alpha"])
    dl.ellipse([px - rx, py - rz, px + rx, py + rz], fill=(0, 0, 0, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    if horizon_y is not None and horizon_y > 0:
        # Erase everything above the horizon. On an RGBA image
        # ImageDraw REPLACES pixels, so a (0,0,0,0) rectangle clears
        # the alpha there instead of blending.
        ImageDraw.Draw(layer).rectangle(
            [0, 0, img.size[0], int(horizon_y)], fill=(0, 0, 0, 0))
    img.alpha_composite(layer)


def _draw_label(d, quad, text):
    """Draw ``text`` centred on a projected box face ``quad``.

    Yellow bold text (the RicksClips caption colour -- readable on a
    dark sign face) with a thin dark outline so it also reads on a
    light face. The font shrinks until the text fits the quad width.
    Uses DejaVu Sans Bold (covers Vietnamese diacritics) when present.
    """
    from PIL import ImageFont
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    if w < 8 or h < 8:
        return
    size = max(10, int(h * 0.55))
    font = None
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(path, size)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()
    # shrink until the text fits the face (with 8% side margins)
    while size > 10:
        bbox = d.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= w * 0.92:
            break
        size -= 2
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                size)
        except (OSError, IOError):
            break
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = (x0 + x1) / 2 - tw / 2 - bbox[0], (y0 + y1) / 2 - th / 2 - bbox[1]
    # thin dark outline (readable on light faces), yellow fill
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        d.text((tx + dx, ty + dy), text, font=font, fill=(20, 20, 20))
    d.text((tx, ty), text, font=font, fill=(255, 210, 0))


def _draw_box(img: Image.Image, scene: Scene25D, cam: PerspectiveCamera,
              box: Box3D):
    """Projected cuboid: visible faces only, each face shaded by the
    light rig from its own normal. Faces are drawn far-to-near within
    the box by face depth."""
    w, h = img.size
    d = ImageDraw.Draw(img)
    corners = box.corners()
    proj = [cam.project(c, w, h) for c in corners]
    faces = []
    front_pts = None  # the +z face, for the label (v7)
    for idxs, normal in BOX_FACES:
        if normal == (0.0, -1.0, 0.0):
            continue  # bottom face: never visible
        # face visible if its outward normal points towards the camera
        to_cam = (cam.position[0] - box.center[0],
                  cam.position[1] - box.center[1],
                  cam.position[2] - box.center[2])
        facing = (normal[0] * to_cam[0] + normal[1] * to_cam[1]
                  + normal[2] * to_cam[2])
        if facing <= 0:
            continue
        pts, ok = [], True
        for i in idxs:
            x, y, _, vis = proj[i]
            if not vis:
                ok = False
                break
            pts.append((x, y))
        if not ok:
            continue
        depth = sum(cam.depth_of(corners[i]) for i in idxs) / len(idxs)
        centre = tuple(sum(corners[i][k] for i in idxs) / len(idxs)
                       for k in range(3))
        irr = scene.lights.irradiance(centre, normal)
        faces.append((depth, pts, shade(box.color, irr)))
        if normal == (0.0, 0.0, 1.0):
            front_pts = pts
    for _, pts, colour in sorted(faces, key=lambda f: -f[0]):
        # outline pre-blended darker (same PIL alpha caveat as the grid)
        outline = tuple(int(c * 0.6) for c in colour)
        d.polygon(pts, fill=colour, outline=outline)
    if box.label and front_pts:
        _draw_label(d, front_pts, box.label)


def _draw_character_marker(img: Image.Image, scene: Scene25D,
                           cam: PerspectiveCamera, ch: CharacterAnchor,
                           draw_character=None):
    """Character billboard: feet->head line projected through the camera.

    Default marker is a neutral capsule (NOT character art — that lives
    in animation/character_art.py). A caller may pass ``draw_character
    (img, feet_xy, head_xy, height_px, anchor)`` to draw the real rig.
    """
    w, h = img.size
    fx, fy, _, vis_f = cam.project(ch.world_pos, w, h)
    hx, hy, _, vis_h = cam.project(
        (ch.world_pos[0], ch.world_pos[1] + ch.height, ch.world_pos[2]), w, h)
    if not (vis_f and vis_h):
        return
    height_px = fy - hy
    if draw_character is not None:
        draw_character(img, (fx, fy), (hx, hy), height_px, ch)
        return
    d = ImageDraw.Draw(img, "RGBA")
    r = max(3.0, height_px * 0.055)  # head radius ~ 1/18 of height
    # body line, head circle, feet ticks — a placement marker only
    d.line([(fx, fy), (hx, hy)], fill=(245, 240, 230, 255),
           width=max(2, int(height_px * 0.03)))
    d.ellipse([hx - r, hy - r, hx + r, hy + r],
              fill=(245, 240, 230, 255), outline=(20, 20, 30, 255))
    d.line([(fx - r, fy), (fx + r, fy)], fill=(245, 240, 230, 255), width=3)


def render_frame(scene: Scene25D, width: int = 1920, height: int = 1080,
                 draw_character=None) -> Image.Image:
    """Render one frame of ``scene`` at 24fps-pipeline resolution.

    Draw order: sky -> ground -> contact shadows -> boxes and
    characters far-to-near (painter's order by camera depth).
    Returns an RGB PIL image.
    """
    cam = scene.camera
    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    _sky(img, scene.sky_top, scene.sky_bottom)
    _draw_ground_grid(img, scene, cam)
    horizon = _horizon_y(scene, cam, width, height)
    # contact shadows first (they lie on the ground, under everything).
    # Flat ground slabs (path/kerb) cast NO shadow: a slab lying on
    # the ground has no visible shadow, and its huge footprint used
    # to darken the whole frame including the sky (Stage 3).
    for box in scene.boxes:
        if box.is_flat_ground_slab():
            continue
        _draw_contact_shadow(img, scene, cam, box.ground_pos(),
                             box.height_above_ground(), box.base_radius(),
                             horizon_y=horizon)
    for ch in scene.characters:
        _draw_contact_shadow(img, scene, cam, ch.world_pos, 0.0, 0.35,
                             horizon_y=horizon)
    # far-to-near painter's order across boxes + characters together
    items = [(cam.depth_of(b.center), "box", b) for b in scene.boxes]
    items += [(cam.depth_of(c.world_pos), "character", c)
              for c in scene.characters]
    for _, kind, obj in sorted(items, key=lambda t: -t[0]):
        if kind == "box":
            _draw_box(img, scene, cam, obj)
        else:
            _draw_character_marker(img, scene, cam, obj, draw_character)
    return img.convert("RGB")


def render_boxes_layer(scene: Scene25D, width: int = 1920,
                     height: int = 1080, boxes=None) -> Image.Image:
    """Boxes ONLY on a transparent layer, same projection + shading as
    render_frame (far-to-near painter's order, same light rig, same
    face labels). No sky, no ground, no contact shadows.

    Stage 3 (foreground occlusion): the product renderer draws the
    full scene as the background, then the characters, then composites
    this layer for the boxes that stand IN FRONT of the character
    plane — so a foreground crate genuinely occludes the feet behind
    it. The boxes are drawn with the same _draw_box call render_frame
    uses, so the layer pixels are identical to the background pixels
    wherever no character intervenes. ``boxes=None`` draws every box
    in the scene.
    """
    cam = scene.camera
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw_boxes = list(scene.boxes if boxes is None else boxes)
    for box in sorted(draw_boxes, key=lambda b: -cam.depth_of(b.center)):
        _draw_box(img, scene, cam, box)
    return img


def render_proof_frames(scene: Scene25D, out_dir, width: int = 960,
                        height: int = 540, draw_character=None):
    """Render the scene from 3 camera positions (left / centre / right)
    so parallax is visible frame-to-frame. Returns the file paths."""
    from pathlib import Path
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, dx in (("cam_left", -1.5), ("cam_center", 0.0),
                     ("cam_right", 1.5)):
        moved = scene.camera.moved(dpos=(dx, 0.0, 0.0),
                                   dtarget=(dx, 0.0, 0.0))
        frame_scene = Scene25D(boxes=scene.boxes, characters=scene.characters,
                               lights=scene.lights, camera=moved,
                               sky_top=scene.sky_top,
                               sky_bottom=scene.sky_bottom,
                               ground_color=scene.ground_color,
                               ground_extent=scene.ground_extent)
        path = out / f"{name}.png"
        render_frame(frame_scene, width, height, draw_character).save(path)
        paths.append(path)
    return paths
