"""Character art v3 for AI Clip Studio -- PREMIUM_STICKMAN.

Style lock (Mai, 2026-11-11): make a BEAUTIFUL STICKMAN before making a
beautiful film. The v2 art was rejected: a hybrid of stickman, geometric
doll and 2D character -- jacket with lapels/collar/buttons/shirt-V,
blush, sweat-drop symbols, white-dot hands, glued-on costume blocks
that broke the silhouette. Adding details does not make it prettier;
silhouette, proportion, line quality and acting matter most.

Reference (NOT copied as an asset -- style standard only):
``~/workspace/user/media_library/image/image.png`` -- a round-headed
stickman: big round head with a thick even outline, two simple solid
oval eyes, a small mouth, a slim solid torso, limbs drawn as clean
lines of uniform thickness with rounded joints, minimal hands with
clear fingers (never a white dot), flat structured feet on a sketched
ground line with a soft shadow.

v3 rules (``STYLE_LOCK`` -- every character goes through it):

  * ONE proportion system for every template: headRatio 0.146 (V51
    standard 0.142-0.155, enforced by the rig), torso 0.32*H, legs
    0.23+0.23, arms 0.20+0.19 (fractions of total height H).
  * ONE line language: ink ``#172033`` for outlines/limbs/hands/feet,
    face fill cream ``#F7F3E8``. Limb thickness is UNIFORM along a limb
    and between limbs (``limb_width``); joints are rounded caps, never
    broken angles. The torso is ONE slim tapered solid shape, not a
    jacket assembly. Costume only when it preserves the silhouette
    (``costume="dress"`` extends the torso into an A-line, it is never
    a glued block). No blush, no sweat drops, no nose, no pasted
    symbols -- the face is eyes + brows + mouth in the same line.
  * Hands: 3 short finger strokes fanning from the wrist, in ink.
    Feet: flat structured ellipses pointing toward ``facing``, sitting
    exactly on the ground line with a soft shadow + sketch strokes.
  * Expressions: 8 states as numeric parameter vectors
    (``EXPRESSIONS``); transitions interpolate every parameter with
    smoothstep (``blend_expressions`` / ``expression_at``) -- the eyes
    and mouth morph, they never swap suddenly.

``draw_character_v3(draw, char, expression, view, palette)`` takes a
PIL ImageDraw, a rig ``Stickman`` (pose already set via ``set_pose()`` /
IK targets) and returns the joint map, like the old renderer.
``make_character(template, ...)`` builds reusable templates (male /
female / child / elderly + slim / standard / sturdy body variants);
Minh / Lan / Lustig are only instances (suit colour, hair, hat,
moustache) on the same template system.

Legacy: ``draw_character_v2`` below is FROZEN (v4 / Chiec Vi renderers
in ~/workspace/acceptance_loop still import it for reproducibility).
New work must use v3. The old ``MOODS`` names map to v3 expressions
via ``LEGACY_MOOD_TO_EXPRESSION``.
"""
from __future__ import annotations

import math

from .rig import (  # noqa: F401  (re-exported for callers)
    Stickman, HEAD_RATIO, HEAD_RATIO_MIN, HEAD_RATIO_MAX,
    BODY_WIDTH_SCALE,
)

# ---------------------------------------------------------------------------
# Style lock -- PREMIUM_STICKMAN v3
# ---------------------------------------------------------------------------

CHARACTER_STYLE = "PREMIUM_STICKMAN"
STYLE_VERSION = "v3"

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

# Every measurement is a fraction of total height H (or of head radius r
# where noted), so the style scales from a 400 px child to a 560 px adult
# without changing the look. Measured from the reference image:
# head outline ~0.018*H, limbs ~0.015*H, eyes 0.17r wide / 0.33r tall,
# fingers ~0.038*H, foot 0.085*H wide.
STYLE_LOCK = {
    "character_style": CHARACTER_STYLE,
    "style_version": STYLE_VERSION,
    # Proportion system (ONE system for all templates).
    "head_ratio": HEAD_RATIO,            # 0.146; allowed 0.142-0.155
    "head_ratio_min": HEAD_RATIO_MIN,
    "head_ratio_max": HEAD_RATIO_MAX,
    "torso_frac": 0.32,
    "upper_leg_frac": 0.23,
    "lower_leg_frac": 0.23,
    "upper_arm_frac": 0.20,
    "lower_arm_frac": 0.19,
    # Line system (ONE thickness per element class, uniform along a limb).
    "outline_w_frac": 0.018,            # head outline
    "limb_w_frac": 0.015,               # arms AND legs, same value
    "torso_top_half_frac": 0.036,       # slim tapered torso, top
    "torso_bottom_half_frac": 0.026,    # ... and bottom (half-widths)
    # Face (fractions of head radius r).
    "eye_half_w_frac_of_r": 0.085,      # eye 0.17r wide
    "eye_half_h_frac_of_r": 0.165,      # eye 0.33r tall
    "eye_dx_frac_of_r": 0.33,           # eye centre offset from head centre
    "mouth_len_frac_of_r": 0.30,        # mouth line length
    # Hands / feet (fractions of H).
    "finger_len_frac": 0.038,
    "finger_count": 3,
    "foot_w_frac": 0.085,
    "foot_h_frac": 0.024,
    # Colours.
    "ink": "#172033",
    "face_fill": "#F7F3E8",
}

VIEWS = ("front", "three_quarter", "profile", "back")

# ---------------------------------------------------------------------------
# Expressions -- 8 states, one numeric language, smooth interpolation.
#
# eye_h/eye_w: eye size multipliers (eye_h <= 0.6 draws closed happy
#   arcs instead of ovals). eye_dx: gaze shift, in units of r.
# brow_in/brow_out: inner/outer brow-end vertical offset, in units of r
#   (+ = down). brow_asym: extra inner offset on ONE brow (thinking /
#   doubtful). mouth_curve: -1 = full frown .. 0 = line .. +1 = full
#   smile. mouth_open: 0 = closed line .. 1 = open "O". mouth_w: mouth
#   width multiplier. mouth_dx: mouth centre shift, in units of r.
# ---------------------------------------------------------------------------

EXPRESSION_PARAMS = (
    "eye_h", "eye_w", "eye_dx", "brow_in", "brow_out", "brow_asym",
    "mouth_curve", "mouth_open", "mouth_w", "mouth_dx",
)

EXPRESSIONS = {
    "neutral":   dict(eye_h=1.00, eye_w=1.00, eye_dx=0.00,
                      brow_in=0.00, brow_out=0.00, brow_asym=0.00,
                      mouth_curve=0.00, mouth_open=0.00,
                      mouth_w=1.00, mouth_dx=0.00),
    "happy":     dict(eye_h=0.50, eye_w=1.00, eye_dx=0.00,
                      brow_in=-0.10, brow_out=-0.08, brow_asym=0.00,
                      mouth_curve=1.00, mouth_open=0.12,
                      mouth_w=1.25, mouth_dx=0.00),
    "sad":       dict(eye_h=1.05, eye_w=0.95, eye_dx=0.00,
                      brow_in=-0.16, brow_out=0.06, brow_asym=0.00,
                      mouth_curve=-0.85, mouth_open=0.00,
                      mouth_w=0.90, mouth_dx=0.00),
    "surprised": dict(eye_h=1.50, eye_w=1.25, eye_dx=0.00,
                      brow_in=-0.22, brow_out=-0.18, brow_asym=0.00,
                      mouth_curve=0.00, mouth_open=1.00,
                      mouth_w=0.80, mouth_dx=0.00),
    "worried":   dict(eye_h=1.10, eye_w=1.00, eye_dx=0.00,
                      brow_in=-0.14, brow_out=0.05, brow_asym=0.00,
                      mouth_curve=-0.45, mouth_open=0.10,
                      mouth_w=0.80, mouth_dx=0.00),
    "angry":     dict(eye_h=0.80, eye_w=1.00, eye_dx=0.00,
                      brow_in=0.20, brow_out=-0.10, brow_asym=0.00,
                      mouth_curve=-0.55, mouth_open=0.00,
                      mouth_w=1.00, mouth_dx=0.00),
    "thinking":  dict(eye_h=0.95, eye_w=1.00, eye_dx=0.10,
                      brow_in=-0.05, brow_out=0.00, brow_asym=-0.16,
                      mouth_curve=0.00, mouth_open=0.00,
                      mouth_w=0.70, mouth_dx=0.08),
    "doubtful":  dict(eye_h=0.85, eye_w=1.00, eye_dx=0.06,
                      brow_in=0.06, brow_out=0.00, brow_asym=-0.14,
                      mouth_curve=-0.25, mouth_open=0.00,
                      mouth_w=0.85, mouth_dx=-0.05),
}

EXPRESSION_NAMES = tuple(EXPRESSIONS.keys())

LEGACY_MOOD_TO_EXPRESSION = {
    "neutral": "neutral", "worried": "worried", "smile": "happy",
    "speak": "neutral", "relief": "happy",
}

# ---------------------------------------------------------------------------
# Templates -- one proportion / line system, identity carried by colour,
# hair, hat and accessories only. Minh / Lan / Lustig are instances.
# ---------------------------------------------------------------------------

TEMPLATES = {
    "male": dict(height=560, suit="#172033", skin="#F3F0E8",
                 hat="none", moustache=False, hair_style="short",
                 glasses=False, cane=False, costume="none",
                 name="male"),
    "female": dict(height=540, suit="#2E5FA3", skin="#F3F0E8",
                   hat="none", moustache=False, hair_style="long",
                   glasses=False, cane=False, costume="none",
                   name="female"),
    "child": dict(height=400, suit="#D9A441", skin="#F3F0E8",
                  hat="none", moustache=False, hair_style="tuft",
                  glasses=False, cane=False, costume="none",
                  name="child"),
    "elderly": dict(height=520, suit="#6B6259", skin="#F3F0E8",
                    hat="none", moustache=False, hair_style="short",
                    glasses=True, cane=True, costume="none",
                    name="elderly"),
}

# Body variants scale torso width AND limb width together (see
# BODY_WIDTH_SCALE in rig.py): slim 0.9 / standard 1.0 / sturdy 1.15.
BODY_VARIANTS = tuple(BODY_WIDTH_SCALE.keys())

CHARACTER_INSTANCES = {
    "minh": dict(template="male", name="minh", suit="#2E5FA3"),
    "lan": dict(template="female", name="lan", suit="#47BD75"),
    "lustig": dict(template="male", name="lustig", suit="#172033",
                   hat="bowler", moustache=True),
}

_STICKMAN_KWARGS = (
    "height", "suit", "skin", "hat", "moustache", "name", "template",
    "body_variant", "hair_style", "glasses", "cane", "costume",
)


def make_character(template="male", name=None, suit=None,
                   body_variant="standard", height=None, **overrides):
    """Build a reusable character on the locked proportion system.

    template: 'male' | 'female' | 'child' | 'elderly'.
    body_variant: 'slim' | 'standard' | 'sturdy' (widths scale together).
    Any template field (suit, hat, moustache, hair_style, glasses, cane,
    costume, height, name) can be overridden per instance. Identity is
    preserved across shots because it lives in these fields, not in a
    per-story drawing routine.
    """
    if template not in TEMPLATES:
        raise ValueError(f"unknown character template: {template!r} "
                         f"(expected one of {sorted(TEMPLATES)})")
    if body_variant not in BODY_WIDTH_SCALE:
        raise ValueError(f"unknown body_variant: {body_variant!r} "
                         f"(expected one of {sorted(BODY_WIDTH_SCALE)})")
    spec = dict(TEMPLATES[template])
    spec["template"] = template
    spec["body_variant"] = body_variant
    if height is not None:
        spec["height"] = height
    if suit is not None:
        spec["suit"] = suit
    if name is not None:
        spec["name"] = name
    spec.update(overrides)
    return Stickman(**{k: v for k, v in spec.items()
                       if k in _STICKMAN_KWARGS})


def make_character_instance(name, **overrides):
    """Minh / Lan / Lustig: instances on the shared template system."""
    if name not in CHARACTER_INSTANCES:
        raise ValueError(f"unknown character instance: {name!r} "
                         f"(expected one of {sorted(CHARACTER_INSTANCES)})")
    spec = dict(CHARACTER_INSTANCES[name])
    template = spec.pop("template")
    spec.update(overrides)
    return make_character(template, **spec)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def limb_width(char):
    """ONE limb thickness for arms and legs (uniform along a limb and
    between limbs; scaled only by the body variant, together)."""
    return max(6.0, STYLE_LOCK["limb_w_frac"] * float(char.H)) \
        * float(getattr(char, "width_scale", 1.0))


def outline_width(char):
    """Head outline thickness (same line language, slightly heavier)."""
    return max(7.0, STYLE_LOCK["outline_w_frac"] * float(char.H))


def _smooth(u):
    u = max(0.0, min(1.0, float(u)))
    return u * u * (3 - 2 * u)


def _resolve_expression(expr):
    if isinstance(expr, dict):
        out = dict(EXPRESSIONS["neutral"])
        out.update({k: v for k, v in expr.items() if k in EXPRESSION_PARAMS})
        return out
    if expr not in EXPRESSIONS:
        raise ValueError(f"unknown expression: {expr!r} "
                         f"(expected one of {list(EXPRESSIONS)})")
    return dict(EXPRESSIONS[expr])


def blend_expressions(expr_a, expr_b, u):
    """Interpolate two expressions (names or param dicts) with
    smoothstep. Every parameter morphs continuously -- eyes and mouth
    never swap suddenly between states."""
    pa = _resolve_expression(expr_a)
    pb = _resolve_expression(expr_b)
    s = _smooth(u)
    return {k: pa[k] + (pb[k] - pa[k]) * s for k in EXPRESSION_PARAMS}


def expression_at(keyframes, t):
    """Expression params at time ``t`` from ``[(time, expression), ...]``
    keyframes, smoothstep-interpolated between bracketing keyframes."""
    if t <= keyframes[0][0]:
        return _resolve_expression(keyframes[0][1])
    if t >= keyframes[-1][0]:
        return _resolve_expression(keyframes[-1][1])
    for (t0, e0), (t1, e1) in zip(keyframes, keyframes[1:]):
        if t0 <= t <= t1:
            return blend_expressions(e0, e1, (t - t0) / (t1 - t0))
    return _resolve_expression(keyframes[-1][1])


# ---------------------------------------------------------------------------
# v3 renderer
# ---------------------------------------------------------------------------


def _draw_hand(draw, elbow, hand, char, ink):
    """Minimal hand in the reference language: 3 finger strokes fanning
    from the wrist along the forearm direction. Never a dot, never a
    skin circle, never a pasted symbol."""
    H = float(char.H)
    dx, dy = hand[0] - elbow[0], hand[1] - elbow[1]
    if math.hypot(dx, dy) < 1e-6:
        dx, dy = 0.0, 1.0
    base = math.atan2(dy, dx)
    flen = STYLE_LOCK["finger_len_frac"] * H
    fw = max(3.0, limb_width(char) * 0.62)
    for off in (-0.61, 0.0, 0.61):  # ~ -35deg, 0, +35deg
        a = base + off
        tip = (hand[0] + math.cos(a) * flen, hand[1] + math.sin(a) * flen)
        draw.line([hand, tip], fill=ink, width=int(fw))
        r = fw / 2.0
        draw.ellipse([tip[0] - r, tip[1] - r,
                      tip[0] + r, tip[1] + r], fill=ink)


def _draw_face(draw, char, hx, hy, view, face_dx, params, ink, pal):
    """Eyes + brows + mouth in the same line language. No nose, no
    blush, no sweat drop. ``face_dx``: 1.0 = profile, 0.55 = 3/4,
    0.0 = front. Back view has no face at all."""
    H = float(char.H)
    r = char.head_r
    f = char.joints()["facing"]
    eye_y = hy - 0.05 * r
    # Near eye (facing side) and far eye; front view is symmetric.
    ex_near = hx + (f * face_dx * 0.33 + (1 - face_dx) * 0.33) * r
    ex_far = hx + (f * face_dx * -0.28 + (1 - face_dx) * -0.33) * r
    far_scale = 0.88 if face_dx > 0 else 1.0
    brow_w = max(3.0, 0.007 * H)
    for ex, scale, is_left in ((ex_near, 1.0, ex_near < hx),
                               (ex_far, far_scale, ex_far < hx)):
        ew = STYLE_LOCK["eye_half_w_frac_of_r"] * r * params["eye_w"] * scale
        eh = STYLE_LOCK["eye_half_h_frac_of_r"] * r * params["eye_h"] * scale
        ex = ex + f * params["eye_dx"] * r * face_dx
        if params["eye_h"] <= 0.6:
            # Closed happy eyes: upper-half arcs, same ink.
            draw.arc([ex - ew, eye_y - eh, ex + ew, eye_y + eh],
                     180, 360, fill=ink, width=max(3, int(0.008 * H)))
        else:
            draw.ellipse([ex - ew, eye_y - eh, ex + ew, eye_y + eh],
                         fill=ink)
        # Brow: short line above the eye; inner end carries the mood,
        # brow_asym raises exactly one brow (thinking / doubtful).
        brow_y = eye_y - 0.52 * r
        sgn = 1.0 if ex >= hx else -1.0
        inner_dy = params["brow_in"] + (params["brow_asym"] if is_left else 0.0)
        inner = (ex - sgn * 0.11 * r, brow_y + inner_dy * r)
        outer = (ex + sgn * 0.11 * r, brow_y + params["brow_out"] * r)
        draw.line([inner, outer], fill=ink, width=int(brow_w))
    # Mouth: line <-> arc <-> open "O" morphs continuously with the
    # expression parameters (open height lerps from a line to an oval).
    mw = STYLE_LOCK["mouth_len_frac_of_r"] * r * params["mouth_w"]
    mx = hx + f * face_dx * 0.18 * r + params["mouth_dx"] * r
    my = hy + 0.42 * r
    mouth_w = max(3.0, 0.009 * H)
    curve = params["mouth_curve"]
    if params["mouth_open"] > 0.05:
        hh = 2.0 + (0.16 * r - 2.0) * params["mouth_open"]
        draw.ellipse([mx - mw / 2, my - hh, mx + mw / 2, my + hh], fill=ink)
    elif abs(curve) > 0.15:
        if curve > 0:  # smile
            draw.arc([mx - mw / 2, my - mw * 0.35, mx + mw / 2, my + mw * 0.35],
                     15, 165, fill=ink, width=int(mouth_w))
        else:  # frown
            draw.arc([mx - mw / 2, my - mw * 0.15, mx + mw / 2, my + mw * 0.55],
                     195, 345, fill=ink, width=int(mouth_w))
    else:
        draw.line([(mx - mw / 2, my), (mx + mw / 2, my)],
                  fill=ink, width=int(mouth_w))
    # Moustache (Lustig): two short strokes on the mouth line, same ink.
    if getattr(char, "moustache", False):
        my0 = my - 0.13 * r
        draw.line([(mx - 0.30 * r, my0 - 0.02 * r), (mx - 0.03 * r, my0 + 0.02 * r)],
                  fill=ink, width=int(brow_w))
        draw.line([(mx + 0.03 * r, my0 + 0.02 * r), (mx + 0.30 * r, my0 - 0.02 * r)],
                  fill=ink, width=int(brow_w))
    return mx, my


def _draw_hair(draw, char, hx, hy, view, ink, part="cap"):
    """Hair in the same line language: a cap following the head circle
    (short), a shape behind the head (long), a tuft (child). Back view
    shows the back of the hair, never a face.

    ``part``: 'back' draws ONLY the behind-the-head shape (call BEFORE
    the head circle); 'cap' draws the cap/tuft/back-of-head (call AFTER
    the head circle). Splitting the two matters: the back shape must
    never cover the face.
    """
    r = char.head_r
    style = getattr(char, "hair_style", None) or "short"
    if part == "back":
        if style == "long" and view != "back":
            # Long hair: two locks falling from the sides of the head to
            # just below the shoulders, drawn BEFORE the head circle so
            # the face stays clean (a full ellipse behind the head read
            # as a black balloon, not hair).
            lw = 0.30 * r
            for sgn in (+1, -1):
                _thick(draw, (hx + sgn * 0.80 * r, hy - 0.55 * r),
                       (hx + sgn * 0.95 * r, hy + 2.35 * r), lw, ink)
        return
    if view == "back":
        if style == "long":
            draw.ellipse([hx - r * 1.02, hy - r * 1.0,
                          hx + r * 1.02, hy + r * 1.6], fill=ink)
        else:
            draw.pieslice([hx - r, hy - r, hx + r, hy + r * 0.75],
                          180, 360, fill=ink)
        return
    if style == "short":
        draw.pieslice([hx - r, hy - r, hx + r, hy + r * 0.25],
                      180, 360, fill=ink)
    elif style == "long":
        draw.pieslice([hx - r, hy - r, hx + r, hy + r * 0.25],
                      180, 360, fill=ink)
    elif style == "tuft":
        draw.pieslice([hx - r, hy - r, hx + r, hy + r * 0.10],
                      180, 360, fill=ink)
        for dx0, dx1 in ((-0.10, -0.22), (0.0, 0.0), (0.10, 0.22)):
            draw.line([(hx + dx0 * r, hy - r * 0.92),
                       (hx + dx1 * r, hy - r * 1.22)],
                      fill=ink, width=max(3, int(0.006 * float(char.H))))


def draw_character_v3(draw, char, expression="neutral", view="profile",
                      palette=None, expression_blend=None):
    """Draw a PREMIUM_STICKMAN v3 character from ``char.joints()``.

    draw: PIL ImageDraw (ideally ``ImageDraw.Draw(img, "RGBA")``).
    char: ``Stickman`` with its pose already set.
    expression: one of the 8 ``EXPRESSION_NAMES`` (or a param dict).
    view: 'front' | 'three_quarter' | 'profile' | 'back'.
    expression_blend: optional ``(other_expression, u)`` -- morphs from
      ``expression`` toward the other one by ``u`` (0..1).
    Returns the joint map from ``char.joints()``.
    """
    if view not in VIEWS:
        view = "profile"
    if isinstance(expression, dict):
        params = _resolve_expression(expression)
    elif expression in EXPRESSIONS:
        params = dict(EXPRESSIONS[expression])
    else:
        params = dict(EXPRESSIONS["neutral"])
    if expression_blend is not None:
        other, u = expression_blend
        params = blend_expressions(params, other, u)

    pal = dict(PALETTE_V51)
    if palette:
        pal.update(palette)
    ink = _hex(pal["dark"])
    suit = _hex(getattr(char, "suit", pal["dark"]))
    face_fill = _hex(STYLE_LOCK["face_fill"])
    H = float(char.H)
    r = char.head_r
    J = char.joints()
    f = J["facing"]
    hip = J["hip"]
    shoulder = J["shoulder"]
    head = J["head"]
    limb_w = limb_width(char)
    out_w = outline_width(char)
    ws = float(getattr(char, "width_scale", 1.0))

    # --- limbs: front view is symmetric, other views use the rig -------
    if view == "front":
        ground_y = hip[1] + char.u_leg + char.l_leg
        limbs = {
            "knee_l": (hip[0] - 0.045 * H, hip[1] + char.u_leg),
            "foot_l": (hip[0] - 0.060 * H, ground_y),
            "knee_r": (hip[0] + 0.045 * H, hip[1] + char.u_leg),
            "foot_r": (hip[0] + 0.060 * H, ground_y),
            "elbow_l": (shoulder[0] - 0.10 * H, shoulder[1] + char.u_arm),
            "hand_l": (shoulder[0] - 0.13 * H, shoulder[1] + char.u_arm + char.l_arm),
            "elbow_r": (shoulder[0] + 0.10 * H, shoulder[1] + char.u_arm),
            "hand_r": (shoulder[0] + 0.13 * H, shoulder[1] + char.u_arm + char.l_arm),
        }
    else:
        ground_y = max(J["foot_l"][1], J["foot_r"][1])
        limbs = {k: J[k] for k in ("knee_l", "foot_l", "knee_r", "foot_r",
                                  "elbow_l", "hand_l", "elbow_r", "hand_r")}

    # --- ground shadow + sketch ground strokes (reference style) -------
    feet_x = (limbs["foot_l"][0] + limbs["foot_r"][0]) / 2.0
    shadow_w = H * 0.16
    draw.ellipse([feet_x - shadow_w, ground_y - 4,
                  feet_x + shadow_w, ground_y + 12],
                 fill=pal["shadow"])
    for k, (dx0, dx1, dy) in enumerate(((0.16, 0.14, 8), (0.11, 0.13, 12),
                                        (0.07, 0.05, 16))):
        draw.line([(feet_x - dx0 * H, ground_y + dy),
                   (feet_x + dx1 * H, ground_y + dy)],
                  fill=ink, width=2)

    # --- legs: clean uniform lines + flat structured feet --------------
    ink_far = _shade(ink, 0.72)
    for side, col in (("l", ink_far), ("r", ink)):
        _thick(draw, hip, limbs[f"knee_{side}"], limb_w, col)
        _thick(draw, limbs[f"knee_{side}"], limbs[f"foot_{side}"],
               limb_w * 0.96, col)
        fx, fy = limbs[f"foot_{side}"]
        fw = STYLE_LOCK["foot_w_frac"] * H * ws
        fh = STYLE_LOCK["foot_h_frac"] * H
        cx, cy = fx + f * fw * 0.18, fy - fh * 0.45
        draw.ellipse([cx - fw / 2, cy - fh / 2, cx + fw / 2, cy + fh / 2],
                     fill=ink)

    # --- torso: ONE slim tapered solid shape (no jacket assembly) ------
    sx, sy = shoulder[0] - hip[0], shoulder[1] - hip[1]
    slen = math.hypot(sx, sy) or 1.0
    ux, uy = sx / slen, sy / slen
    px, py = -uy, ux
    w_top = STYLE_LOCK["torso_top_half_frac"] * H * ws
    w_bot = STYLE_LOCK["torso_bottom_half_frac"] * H * ws
    draw.polygon([
        (shoulder[0] + px * w_top, shoulder[1] + py * w_top),
        (shoulder[0] - px * w_top, shoulder[1] - py * w_top),
        (hip[0] - px * w_bot, hip[1] - py * w_bot),
        (hip[0] + px * w_bot, hip[1] + py * w_bot),
    ], fill=suit)
    # Costume "dress": the torso EXTENDS into an A-line to mid-shin --
    # same colour, continuous with the torso, never a glued block.
    if getattr(char, "costume", "none") == "dress":
        hem_y = hip[1] + 0.20 * H
        hem_half = 0.085 * H * ws
        draw.polygon([
            (hip[0] - px * w_bot, hip[1] - py * w_bot),
            (hip[0] + px * w_bot, hip[1] + py * w_bot),
            (hip[0] + hem_half, hem_y),
            (hip[0] - hem_half, hem_y),
        ], fill=suit)

    # --- arms: same uniform line as the legs, minimal 3-finger hands ---
    for side, col in (("l", ink_far), ("r", ink)):
        _thick(draw, shoulder, limbs[f"elbow_{side}"], limb_w, col)
        _thick(draw, limbs[f"elbow_{side}"], limbs[f"hand_{side}"],
               limb_w * 0.96, col)
    # Cane (elderly): thin line from the right hand to the ground, hook
    # at the top; the hand is drawn over it so contact reads clearly.
    if getattr(char, "cane", False):
        hx0, hy0 = limbs["hand_r"]
        draw.line([(hx0, hy0), (hx0 + f * 0.02 * H, ground_y)],
                  fill=ink, width=max(3, int(limb_w * 0.7)))
        draw.arc([hx0 - 0.02 * H, hy0 - 0.02 * H,
                  hx0 + 0.02 * H, hy0 + 0.02 * H],
                 180, 360, fill=ink, width=max(3, int(limb_w * 0.7)))
    for side in ("l", "r"):
        _draw_hand(draw, limbs[f"elbow_{side}"], limbs[f"hand_{side}"],
                   char, ink)

    # --- head ------------------------------------------------------------
    hx, hy = head
    if getattr(char, "hair_style", None) == "long" and view != "back":
        _draw_hair(draw, char, hx, hy, view, ink, part="back")
    draw.ellipse([hx - r, hy - r, hx + r, hy + r], fill=face_fill,
                 outline=ink, width=int(out_w))
    _draw_hair(draw, char, hx, hy, view, ink, part="cap")
    # Bowler hat (Lustig): brim line + dome, same ink, same language.
    _hat = getattr(char, "hat", None)
    if _hat and _hat != "none":
        draw.line([(hx - r * 1.15, hy - r * 0.95),
                   (hx + r * 1.15, hy - r * 0.95)],
                  fill=ink, width=max(3, int(out_w * 0.8)))
        draw.pieslice([hx - r * 0.62, hy - r * 1.75,
                       hx + r * 0.62, hy - r * 0.85],
                      180, 360, fill=ink)
    # Glasses (elderly): two thin circles + bridge, same ink.
    if getattr(char, "glasses", False) and view != "back":
        face_dx = {"front": 0.0, "three_quarter": 0.55,
                   "profile": 1.0}[view]
        for ex in (hx + (f * face_dx * 0.33 + (1 - face_dx) * 0.33) * r,
                   hx + (f * face_dx * -0.28 + (1 - face_dx) * -0.33) * r):
            gr = 0.14 * r
            draw.ellipse([ex - gr, hy - 0.05 * r - gr,
                          ex + gr, hy - 0.05 * r + gr],
                         outline=ink, width=2)
    if view != "back":
        face_dx = {"front": 0.0, "three_quarter": 0.55,
                   "profile": 1.0}[view]
        _draw_face(draw, char, hx, hy, view, face_dx, params, ink, pal)
    return J


# Backwards-compatible alias: the canonical renderer is v3.
draw_character = draw_character_v3


# ---------------------------------------------------------------------------
# LEGACY v2 -- FROZEN. Do not edit: the v4 / Chiec Vi renderers in
# ~/workspace/acceptance_loop still import draw_character_v2 for
# reproducibility of already-rendered evidence. New work uses v3 above.
# (Blush, sweat drop, jacket assembly and white-dot hands live ONLY
# here, in the frozen function -- v3 removed them.)
# ---------------------------------------------------------------------------

MOODS = ("neutral", "worried", "smile", "speak", "relief")


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
    # bowler hat, if the rig carries one ("none" means no hat)
    _hat = getattr(char, "hat", None)
    if _hat and _hat != "none":
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
