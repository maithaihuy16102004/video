"""Rig-landmark measurement (Phase F, Cinematic Engine Upgrade).

Why this module exists: head-size numbers like 136x727 px, 222x883 px
and 138x719 px circulated in QA reports. A "head" box 727 px tall is
not a head — it is a segmentation column that merged the head with
the body (free pixel segmentation with no landmark anchor). No code
in the current tree produces those numbers (searched 2026-11-12; the
old head-outline scan that did was discarded as unreliable and must
never be revived). This module replaces pixel guessing with explicit
rig landmarks: every box is computed from joint positions and the
rig's own head radius, with the four bbox kinds kept separate
(contracts BBOX_KINDS): head, hair, full_character, costume.

Honest scope: rig boxes verify the RIG's construction (proportions
the rig was built with). They do NOT verify the drawn pixels — a
drawing bug could still deviate from the rig. Drawn-pixel
verification is the silhouette mask (below) plus human visual
review. A rig box must never be cited as pixel evidence, and a
pixel mask must never be cited as a rig proportion.
"""

from __future__ import annotations

import math

from .cinematic_contracts import BBOX_KINDS

__all__ = [
    "BBOX_KINDS",
    "SILHOUETTE_IOU_MAX",
    "head_box",
    "hair_box",
    "costume_box",
    "full_character_box",
    "character_height",
    "head_ratio",
    "measure_character",
    "silhouette_mask",
    "silhouette_iou",
    "pairwise_silhouette_report",
    "camera_coverage_report",
]

# Silhouette distinctness bar (A-S5): the v8 suite already certifies
# officer-vs-lustig at IoU <= 0.78 (test_animation_v8), and the
# Minh-Lan 0.796 reading was the defect that body variants fixed.
# Pairs above this bar are too similar to tell apart in silhouette.
SILHOUETTE_IOU_MAX = 0.78

# Joints that carry costume (torso + limbs). The head and neck are
# excluded: the costume box is the body, never the head column.
_COSTUME_JOINTS = (
    "shoulder", "hip",
    "knee_l", "knee_r", "foot_l", "foot_r",
    "elbow_l", "elbow_r", "hand_l", "hand_r",
)

# Hair/hat extents in units of head radius, from the draw geometry in
# animation/character_art.py (profile view). The short/side-part caps
# follow the head circle exactly and never leave it; long hair falls
# to hy+1.6r in 0.26r-wide locks; the tuft reaches hy-1.22r; any
# non-"none" hat draws the bowler shape (crown to hy-1.75r, brim to
# +/-1.15r). Other views use the same extents as an approximation,
# recorded on the box.
_HAIR_EXTENTS = {
    # style: (dx_left, dx_right, dy_top, dy_bottom) in units of r,
    # relative to the head centre. The head circle itself is
    # (-1, +1, -1, +1); extents never shrink below the circle.
    "short": (-1.0, 1.0, -1.0, 1.0),
    "side_part": (-1.0, 1.0, -1.0, 1.0),
    "long": (-1.08, 1.08, -1.0, 1.73),
    "tuft": (-1.0, 1.0, -1.22, 1.0),
    "bald": (-1.0, 1.0, -1.0, 1.0),
    "none": (-1.0, 1.0, -1.0, 1.0),
}
_HAT_EXTENTS = (-1.15, 1.15, -1.75, 1.0)


def _finite(value, name):
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    return float(value)


def _box(kind, x0, y0, x1, y1, notes=()):
    if kind not in BBOX_KINDS:
        raise ValueError(f"unknown bbox kind {kind!r} "
                         f"(expected one of {list(BBOX_KINDS)})")
    x0, y0, x1, y1 = (_finite(v, n) for v, n in (
        (x0, "x0"), (y0, "y0"), (x1, "x1"), (y1, "y1")))
    if x1 < x0 or y1 < y0:
        raise ValueError(f"inverted box: ({x0}, {y0})-({x1}, {y1})")
    return {"kind": kind, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "width": x1 - x0, "height": y1 - y0,
            "source": "rig", "notes": list(notes)}


def head_box(head_center, head_r):
    """The head circle as a box: exactly 2r x 2r, centred on the rig
    head joint. Never includes hair, hat, neck or body — that
    contamination is what produced the 136x727-style numbers."""
    hx, hy = head_center
    hx = _finite(hx, "head_x")
    hy = _finite(hy, "head_y")
    r = _finite(head_r, "head_r")
    if r <= 0:
        raise ValueError(f"head_r must be positive, got {r}")
    return _box("head", hx - r, hy - r, hx + r, hy + r)


def hair_box(head_center, head_r, hair_style=None, hat=None,
             long_hair=False, facing=1):
    """Head adornments: the head circle plus documented hair/hat
    extents. The hair box is a superset of the head box by
    construction; it is the box to use for headroom/framing, never
    for the head-ratio check (a hat must not shrink the ratio)."""
    hx, hy = head_center
    hx = _finite(hx, "head_x")
    hy = _finite(hy, "head_y")
    r = _finite(head_r, "head_r")
    if r <= 0:
        raise ValueError(f"head_r must be positive, got {r}")
    style = (hair_style or "short").lower()
    notes = []
    if style not in _HAIR_EXTENTS:
        notes.append(f"unknown hair style {style!r}: extents "
                     "unmeasured, head circle only")
        extents = _HAIR_EXTENTS["short"]
    else:
        extents = _HAIR_EXTENTS[style]
    dx0, dx1, dy0, dy1 = extents
    if long_hair:
        # v2 long-hair block behind the head (facing-dependent):
        # [hx-1.9r, hx-0.9r] when facing right, mirrored otherwise.
        if float(facing) >= 0:
            dx0 = min(dx0, -1.9)
        else:
            dx1 = max(dx1, 1.9)
        dy1 = max(dy1, 1.73)
        notes.append("long_hair block included (v2 geometry)")
    if hat not in (None, "none", ""):
        hx0, hx1, hy0, hy1 = _HAT_EXTENTS
        dx0, dx1 = min(dx0, hx0), max(dx1, hx1)
        dy0, dy1 = min(dy0, hy0), max(dy1, hy1)
        notes.append(f"hat {hat!r} extents included (bowler geometry)")
    return _box("hair", hx + dx0 * r, hy + dy0 * r,
                hx + dx1 * r, hy + dy1 * r, notes)


def costume_box(joints, margin_px):
    """Body joints (shoulders/hips/limbs) expanded by the limb
    half-width margin. Excludes the head and neck by construction."""
    margin = _finite(margin_px, "margin_px")
    if margin < 0:
        raise ValueError(f"margin_px must be >= 0, got {margin}")
    pts = []
    for key in _COSTUME_JOINTS:
        if key in joints and joints[key] is not None:
            x, y = joints[key]
            pts.append((_finite(x, key), _finite(y, key)))
    if not pts:
        raise ValueError("no costume joints present in joints dict")
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return _box("costume", min(xs) - margin, min(ys) - margin,
                max(xs) + margin, max(ys) + margin,
                [f"margin {margin}px (limb half-width, approximate)"])


def full_character_box(joints, head_center, head_r, hair_style=None,
                       hat=None, margin_px=0.0, long_hair=False,
                       facing=1):
    """Union of the head, hair and costume boxes: the drawn extent
    of the character for framing/collision. Never use this box's
    height for the head-ratio check — it includes hair/hat overhang
    and raised limbs."""
    head = head_box(head_center, head_r)
    hair = hair_box(head_center, head_r, hair_style, hat,
                    long_hair=long_hair, facing=facing)
    costume = costume_box(joints, margin_px)
    notes = ["union of head + hair + costume boxes"]
    notes.extend(hair["notes"])
    notes.extend(costume["notes"])
    return _box("full_character",
                min(head["x0"], hair["x0"], costume["x0"]),
                min(head["y0"], hair["y0"], costume["y0"]),
                max(head["x1"], hair["x1"], costume["x1"]),
                max(head["y1"], hair["y1"], costume["y1"]), notes)


def character_height(joints, head_center, head_r):
    """Standing height: lowest foot joint minus the HEAD CIRCLE top
    (hat/hair excluded — the reference definition of headRatio).
    Only meaningful on a standing/idle pose: sitting, kneeling or
    jumping poses compress or extend the measured height, which is
    a pose fact, not a proportion defect."""
    hx, hy = head_center
    hy = _finite(hy, "head_y")
    r = _finite(head_r, "head_r")
    feet = [joints[k] for k in ("foot_l", "foot_r")
            if k in joints and joints[k] is not None]
    if not feet:
        raise ValueError("no foot joints present in joints dict")
    foot_y = max(_finite(p[1], "foot_y") for p in feet)
    height = foot_y - (hy - r)
    if height <= 0:
        raise ValueError(f"non-positive character height {height}")
    return height


def head_ratio(head, height):
    """Head height / standing height. ``head`` is a head-kind box
    (kind enforced — a hair or full box here is the contamination
    this module exists to prevent)."""
    if head.get("kind") != "head":
        raise ValueError(
            f"head_ratio requires a head-kind box, got "
            f"{head.get('kind')!r}")
    height = _finite(height, "height")
    if height <= 0:
        raise ValueError(f"height must be positive, got {height}")
    return head["height"] / height


def measure_character(char, joints):
    """All four boxes + standing height + head ratio for one rig
    pose. ``char`` supplies head_r, H, hair_style, hat, long_hair
    and facing (a Stickman, or any object with those attributes);
    ``joints`` is the joints() dict for the pose. The limb margin
    is 2% of H (documented approximation of the drawn limb
    half-width)."""
    head_center = joints["head"]
    r = float(char.head_r)
    facing = joints.get("facing", 1)
    margin = 0.02 * float(char.H)
    head = head_box(head_center, r)
    hair = hair_box(head_center, r,
                    hair_style=getattr(char, "hair_style", None),
                    hat=getattr(char, "hat", None),
                    long_hair=bool(getattr(char, "long_hair", False)),
                    facing=facing)
    costume = costume_box(joints, margin)
    full = full_character_box(joints, head_center, r,
                              hair_style=getattr(char, "hair_style",
                                                 None),
                              hat=getattr(char, "hat", None),
                              margin_px=margin,
                              long_hair=bool(getattr(
                                  char, "long_hair", False)),
                              facing=facing)
    height = character_height(joints, head_center, r)
    return {"head": head, "hair": hair, "costume": costume,
            "full_character": full, "character_height": height,
            "head_ratio": head_ratio(head, height),
            "source": "rig"}


# --- Pixel silhouette (A-S5) ----------------------------------------

def silhouette_mask(image, suit_rgb=None, dark_threshold=400):
    """Ink mask for one character rendered alone on a flat light
    background: dark pixels (RGB sum below ``dark_threshold``) OR,
    when the suit colour is given, suit-coloured pixels (per-channel
    within 12 — the v8 suite's method, which catches light suits a
    pure threshold would miss). Returns a 2-D boolean list-of-lists
    (no numpy dependency in this module)."""
    from PIL import Image
    if isinstance(image, Image.Image):
        rgb = image.convert("RGB")
        width, height = rgb.size
        pixels = list(rgb.getdata())
    else:  # rows of (r, g, b) tuples
        rows = [list(row) for row in image]
        height = len(rows)
        width = len(rows[0]) if rows else 0
        pixels = [px for row in rows for px in row]
    mask = []
    for y in range(height):
        row = []
        for x in range(width):
            r, g, b = pixels[y * width + x][:3]
            dark = (r + g + b) < dark_threshold
            suit = False
            if suit_rgb is not None:
                sr, sg, sb = suit_rgb
                suit = (abs(r - sr) < 12 and abs(g - sg) < 12
                        and abs(b - sb) < 12)
            row.append(bool(dark or suit))
        mask.append(row)
    return mask


def silhouette_iou(mask_a, mask_b):
    """Intersection-over-union of two same-size masks. An empty union
    (both renders blank) returns 0.0 — blank renders certify
    nothing, so they must not read as identical."""
    if len(mask_a) != len(mask_b) or (
            mask_a and len(mask_a[0]) != len(mask_b[0])):
        raise ValueError("silhouette masks must have the same size")
    inter = union = 0
    for row_a, row_b in zip(mask_a, mask_b):
        for a, b in zip(row_a, row_b):
            if a and b:
                inter += 1
            if a or b:
                union += 1
    if union == 0:
        return 0.0
    return inter / union


def pairwise_silhouette_report(renders, threshold=SILHOUETTE_IOU_MAX):
    """Pairwise silhouette IoU for characters rendered alone.

    ``renders``: {name: (mask, n_ink)} or {name: mask}; masks come
    from :func:`silhouette_mask`. Every pair is reported with its
    IoU and a ``distinct`` flag (IoU <= threshold). A pair above the
    threshold is too similar to tell apart in silhouette — the
    data-level silhouette gate (animation/silhouette.py) and this
    pixel check are independent; either may flag a pair."""
    names = sorted(renders)
    masks = {}
    for name in names:
        value = renders[name]
        masks[name] = value[0] if isinstance(value, tuple) else value
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            iou = silhouette_iou(masks[a], masks[b])
            pairs.append({"a": a, "b": b, "iou": round(iou, 4),
                          "distinct": iou <= threshold,
                          "threshold": threshold})
    return {"pairs": pairs, "threshold": threshold,
            "all_distinct": all(p["distinct"] for p in pairs),
            "method": "grayscale+threshold mask (suit colour when "
                      "supplied), IoU over the union"}


# --- Camera measurement coverage (Phase F) --------------------------

def _location_identity(report):
    """Location identity for transition detection, from what the
    report actually carries: (scene, environment_archetype) when
    available (a scene change or an archetype change is a location
    change), else the location text/id/keyword. None when the report
    carries no location identity at all — a cut with unknown
    location on either side is not counted as a transition."""
    scene = report.get("scene")
    arch = report.get("environment_archetype")
    if scene is not None or arch is not None:
        return (scene, arch)
    text = (report.get("location_text")
            or (report.get("v1_location") or {}).get("id")
            or report.get("location_keyword"))
    return ("text", text) if text else None


def _transform_of(report):
    validation = (report or {}).get("camera_validation") or {}
    start = validation.get("start_transform")
    end = validation.get("end_transform")
    if start is None or end is None:
        return None
    return (tuple(start), tuple(end))


def _close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def camera_coverage_report(shot_reports):
    """Coverage of camera measurement over a rendered shot list.

    Each report is a _render_shot report (camera_directive /
    camera_validation / crop_anchor / location fields, per the §5.1
    freeze). A cut is MEASURED when both adjacent reports carry a
    camera validation; otherwise it is unmeasured and counted, never
    assumed. Viewpoint change = the camera position/target moved
    beyond tolerance; transform change = position/target/FOV/crop
    moved (a crop-only cut is a same-camera editorial cut, not a
    viewpoint change); location transition = the location identity
    changed. A background pixel difference alone never counts as a
    viewpoint change — only the recorded transforms do."""
    reports = list(shot_reports or [])
    cuts = []
    for i in range(1, len(reports)):
        prev, cur = reports[i - 1], reports[i]
        t_prev, t_cur = _transform_of(prev), _transform_of(cur)
        measured = t_prev is not None and t_cur is not None
        viewpoint = transform = None
        if measured:
            pos_prev = t_prev[0][:3] + t_prev[0][3:6]
            pos_cur = t_cur[0][:3] + t_cur[0][3:6]
            viewpoint = not _close(pos_prev, pos_cur)
            crop_prev = ((prev.get("camera_validation") or {})
                         .get("crop_rect"))
            crop_cur = ((cur.get("camera_validation") or {})
                        .get("crop_rect"))
            fov_changed = not _close(t_prev[0][6:], t_cur[0][6:])
            transform = bool(viewpoint or fov_changed
                             or crop_prev != crop_cur)
        loc_prev = _location_identity(prev)
        loc_cur = _location_identity(cur)
        cuts.append({
            "cut_index": i,
            "from_shot": prev.get("shot_type"),
            "to_shot": cur.get("shot_type"),
            "measured": measured,
            "viewpoint_change": viewpoint,
            "transform_change": transform,
            "same_camera_editorial_cut":
                bool(measured and not viewpoint and transform),
            "location_transition": bool(
                loc_prev is not None and loc_cur is not None
                and loc_prev != loc_cur),
        })
    measured = [c for c in cuts if c["measured"]]
    return {
        "n_shots": len(reports),
        "n_cuts": len(cuts),
        "measured_cuts": len(measured),
        "unmeasured_cuts": len(cuts) - len(measured),
        "viewpoint_changes": sum(
            1 for c in measured if c["viewpoint_change"]),
        "same_camera_editorial_cuts": sum(
            1 for c in measured if c["same_camera_editorial_cut"]),
        "location_transitions": sum(
            1 for c in cuts if c["location_transition"]),
        "camera_transform_changes": sum(
            1 for c in measured if c["transform_change"]),
        "cuts": cuts,
        "method": "recorded camera transforms only; pixel "
                  "differences never imply a viewpoint change",
    }
