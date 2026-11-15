"""Lighting contract for AI Clip Studio environments (Environment V2).

Visual Quality Recovery, P3/P6 support module. This module owns
four things, all of them measurable:

1. **Time-of-day palettes.** Sky/ground colours and the key-light
   direction per (time_of_day, mood). A DAY scene must stay bright:
   ``DAY_LUMINANCE_FLOOR`` is the documented minimum mean luminance
   of a rendered day environment, and ``check_day_brightness`` is
   the regression check (the Stage 3 dark-daytime bug — a day sky
   ramp rendering as near-black — must never come back).
2. **Contact-shadow ratio cap.** The oversized-blob defect in the
   delivered Ep1 draft came from the product renderer's fixed
   320x48 shadow tile pasted under every box plus a full-frame blur.
   The contract here: a contact shadow is sized from the object's
   OWN projected footprint, never wider than
   ``SHADOW_WIDTH_RATIO_MAX`` x the footprint, never taller than
   ``SHADOW_HEIGHT_RATIO`` of its own width, alpha capped at
   ``SHADOW_ALPHA_MAX``, and clipped to the ground (never above the
   horizon). Ground slabs (paths, kerbs) get NO shadow at all.
   ``shadow_ellipse_spec`` implements the cap on top of the
   geometry-correct ``renderer25d.lighting.contact_shadow``; ATLAS
   wires the same cap into ``product_renderer`` (see the wiring
   section in the Subagent B report).
3. **Measurement helpers** the QA/audit code reuses: mean luminance
   and sky-band luminance of a rendered frame (PIL only, no numpy).
4. **Point lights + energy glow (Test F).** ``rig_for`` accepts
   point lights; ``validate_energy_glow`` /
   ``energy_glow_to_point_light`` consume the Agent A prop-data
   record; the falloff is calibrated so the irradiance at
   ``radius`` is 5% of the peak. ``shade_with_points`` /
   ``add_point_light_tint`` / ``point_light_gain`` apply the
   colored falloff to faces and to already-lit colours. With no
   point lights and a white key, ``shade_with_points`` reproduces
   the grayscale ``shade_color`` exactly; a colored key (the
   palette's sun colour) tints faces per channel (round 8).
5. **Prop material catalog (Test F / B2).** ``MATERIAL_CATALOG``
   is the DATA the semantic prop system consumes: base colour,
   cartoon outline, and emissive parameters per material, with
   ``get_material`` / ``resolve_material`` / ``material_light``
   as the lookup + validation + light-conversion interface.
   The catalog carries no geometry and no story knowledge; the
   geometry lives in the prop system (A2) and the drawing in
   the product renderer (ATLAS). Environment surface textures
   (``paint_textures``) are a SEPARATE namespace — see the
   catalog docstring before wiring anything to it.
6. **Pixel-space glow bridge (B2).** The prop system emits
   ``energy_glow`` records in the 2D staging plane (pixel
   ``source_position``, pixel ``radius``); the environment
   renderer shades in 3D world units. ``pixel_glow_to_world_glow``
   converts a record through a shot camera at a stated depth
   plane — the ONLY sanctioned crossing between the two spaces.
   A pixel-space record handed straight to
   ``energy_glow_to_point_light`` fails loudly instead of
   inventing a depth.

The module is generic: no location, story or character names. Light
direction is the direction the light TRAVELS (renderer25d
convention), e.g. ``(0.35, -1.0, -0.3)`` = from up-left-front,
shining down towards the scene.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from .renderer25d.lighting import (
    DirectionalLight,
    LightRig,
    PointLight,
    contact_shadow,
)

# ---------------------------------------------------------------------------
# Documented constants (the contract)
# ---------------------------------------------------------------------------

# A rendered DAY environment (sky + ground + boxes, no characters)
# must average at least this mean luminance (0..255). Measured day
# renders (Subagent B proof set, 960x540, default camera): European
# street 108, Greek palace 153, Mediterranean island 157, barracks
# 109, trench 106, forest 103, modern city 103. The floor of 90
# leaves margin on the darkest outdoor archetype while still
# catching the dark-daytime failure mode (Stage 3 bug: a day sky
# ramp measured ~28). CAVE archetypes are exempt (dark by nature).
DAY_LUMINANCE_FLOOR = 90.0

# Contact-shadow cap, relative to the object's own projected
# footprint on the ground plane.
SHADOW_WIDTH_RATIO_MAX = 1.3   # shadow width <= 1.3 x footprint width
# Shadow height <= 0.31 x shadow width: exactly the geometry ratio
# of renderer25d.contact_shadow (radius_z = 0.62 x radius_x), so a
# geometry-correct ellipse is never capped, and anything taller is.
SHADOW_HEIGHT_RATIO = 0.31
SHADOW_ALPHA_MAX = 0.55        # resting object, darkest allowed
SHADOW_ALPHA_MIN = 0.10        # lifted object, lightest allowed

# Shadow offset along the light's ground direction, per world unit
# of object height above the ground, for a mid-elevation sun. The
# exact offset comes from contact_shadow(); this ratio is the
# documented bound the cap enforces: offset <= height * ratio.
SHADOW_OFFSET_RATIO_MAX = 1.2

_TIME_OF_DAY_ALIASES = {
    "day": "day", "daytime": "day",
    # Round 7: morning / midday / afternoon are DISTINCT
    # palettes (the old collapse to one "day" palette made
    # every daytime location render identically -- tester R6:
    # "no time-of-day palettes"). Vietnamese spellings included.
    "morning": "morning", "sáng": "morning", "sang": "morning",
    "buổi_sáng": "morning", "buoi_sang": "morning",
    "sáng_sớm": "morning", "sang_som": "morning",
    "midday": "midday", "noon": "midday",
    "trưa": "midday", "trua": "midday",
    "buổi_trưa": "midday", "buoi_trua": "midday",
    "afternoon": "afternoon", "chiều": "afternoon",
    "chieu": "afternoon", "buổi_chiều": "afternoon",
    "buoi_chieu": "afternoon",
    "dusk": "dusk", "dawn": "dusk", "sunset": "dusk",
    "sunrise": "dusk", "evening": "dusk", "golden_hour": "dusk",
    "tối": "dusk", "toi": "dusk", "buổi_tối": "dusk",
    "buoi_toi": "dusk", "chiều_tối": "dusk", "chieu_toi": "dusk",
    "hoàng_hôn": "dusk", "hoang_hon": "dusk",
    "night": "night", "midnight": "night",
    "đêm": "night", "dem": "night", "ban_đêm": "night",
    "ban_dem": "night", "nửa_đêm": "night", "nua_dem": "night",
    "interior": "interior", "indoor": "interior", "inside": "interior",
}

_MOODS = ("warm", "cold", "neutral")

# (time_of_day, mood) -> palette + key light. "day/cold" is the
# overcast case: high ambient, weak key, weak shadows — it must
# still clear DAY_LUMINANCE_FLOOR (flat grey light, not darkness).
TIME_OF_DAY_PALETTES = {
    ("day", "warm"): {
        "sky_top": (122, 168, 214), "sky_bottom": (205, 224, 240),
        "ground": (122, 112, 96), "sun_color": (255, 244, 214),
        "ambient": 0.45, "key_intensity": 1.0,
        "light_direction": (0.35, -1.0, -0.3), "shadow_strength": 0.55,
    },
    ("day", "cold"): {
        "sky_top": (128, 150, 178), "sky_bottom": (196, 208, 220),
        "ground": (108, 106, 100), "sun_color": (230, 236, 242),
        "ambient": 0.62, "key_intensity": 0.55,
        "light_direction": (0.15, -1.0, -0.2), "shadow_strength": 0.30,
    },
    ("day", "neutral"): {
        "sky_top": (130, 168, 208), "sky_bottom": (203, 220, 236),
        "ground": (116, 110, 98), "sun_color": (248, 246, 236),
        "ambient": 0.52, "key_intensity": 0.8,
        "light_direction": (0.25, -1.0, -0.25), "shadow_strength": 0.45,
    },
    # Round 7: distinct daytime palettes. Morning: soft low
    # eastern sun, cooler sky. Midday: bright overhead sun, the
    # strongest key. Afternoon: warm low western sun, golden
    # horizon. The three read differently in the sky, the sun
    # colour, and the shadow direction.
    ("morning", "warm"): {
        "sky_top": (141, 178, 216), "sky_bottom": (222, 232, 240),
        "ground": (118, 110, 96), "sun_color": (255, 240, 205),
        "ambient": 0.50, "key_intensity": 0.9,
        "light_direction": (0.6, -0.7, -0.3), "shadow_strength": 0.45,
    },
    ("morning", "cold"): {
        "sky_top": (135, 158, 185), "sky_bottom": (205, 215, 225),
        "ground": (110, 108, 100), "sun_color": (235, 238, 240),
        "ambient": 0.55, "key_intensity": 0.7,
        "light_direction": (0.55, -0.7, -0.3), "shadow_strength": 0.35,
    },
    ("morning", "neutral"): {
        "sky_top": (138, 168, 200), "sky_bottom": (214, 224, 232),
        "ground": (114, 109, 98), "sun_color": (248, 242, 222),
        "ambient": 0.52, "key_intensity": 0.8,
        "light_direction": (0.58, -0.7, -0.3), "shadow_strength": 0.4,
    },
    ("midday", "warm"): {
        "sky_top": (108, 162, 220), "sky_bottom": (198, 224, 244),
        "ground": (126, 114, 96), "sun_color": (255, 253, 246),
        "ambient": 0.42, "key_intensity": 1.1,
        "light_direction": (0.1, -1.0, -0.1), "shadow_strength": 0.6,
    },
    ("midday", "cold"): {
        "sky_top": (120, 148, 178), "sky_bottom": (192, 206, 218),
        "ground": (116, 112, 102), "sun_color": (240, 244, 248),
        "ambient": 0.48, "key_intensity": 0.85,
        "light_direction": (0.1, -1.0, -0.1), "shadow_strength": 0.45,
    },
    ("midday", "neutral"): {
        "sky_top": (114, 155, 199), "sky_bottom": (195, 215, 231),
        "ground": (121, 113, 99), "sun_color": (248, 248, 243),
        "ambient": 0.45, "key_intensity": 1.0,
        "light_direction": (0.1, -1.0, -0.1), "shadow_strength": 0.52,
    },
    ("afternoon", "warm"): {
        "sky_top": (128, 162, 203), "sky_bottom": (240, 214, 170),
        "ground": (120, 108, 90), "sun_color": (255, 214, 150),
        "ambient": 0.44, "key_intensity": 1.0,
        "light_direction": (-0.6, -0.7, -0.3), "shadow_strength": 0.55,
    },
    ("afternoon", "cold"): {
        "sky_top": (124, 148, 176), "sky_bottom": (210, 208, 198),
        "ground": (110, 106, 96), "sun_color": (238, 232, 218),
        "ambient": 0.5, "key_intensity": 0.75,
        "light_direction": (-0.55, -0.7, -0.3), "shadow_strength": 0.42,
    },
    ("afternoon", "neutral"): {
        "sky_top": (126, 155, 190), "sky_bottom": (224, 215, 195),
        "ground": (115, 107, 93), "sun_color": (248, 222, 178),
        "ambient": 0.47, "key_intensity": 0.88,
        "light_direction": (-0.58, -0.7, -0.3), "shadow_strength": 0.48,
    },
    # Round 12: dusk skies strengthened toward the reference's
    # pink-orange sunset (tester R2-V4: still no at-a-glance read).
    # The gradient, the room-window glass (blend of these two)
    # and the distant haze targets all follow these values.
    ("dusk", "warm"): {
        "sky_top": (74, 78, 138), "sky_bottom": (240, 152, 92),
        # Round 15: the pink mid-band (dossier "pink-orange-
        # purple sunset"). The gradient interpolates top->mid
        # over the upper 55%, mid->bottom below; enclosed
        # archetypes ignore it (no visible sky).
        "sky_mid": (235, 128, 138),
        "ground": (92, 82, 74), "sun_color": (255, 178, 105),
        "ambient": 0.35, "key_intensity": 0.85,
        "light_direction": (0.7, -0.45, -0.2), "shadow_strength": 0.5,
    },
    ("dusk", "cold"): {
        "sky_top": (70, 84, 124), "sky_bottom": (168, 160, 158),
        "ground": (84, 82, 78), "sun_color": (220, 210, 200),
        "ambient": 0.38, "key_intensity": 0.6,
        "light_direction": (0.6, -0.5, -0.2), "shadow_strength": 0.4,
    },
    ("dusk", "neutral"): {
        "sky_top": (80, 90, 132), "sky_bottom": (214, 158, 118),
        "sky_mid": (226, 140, 140),
        "ground": (88, 82, 76), "sun_color": (240, 196, 148),
        "ambient": 0.36, "key_intensity": 0.7,
        "light_direction": (0.65, -0.48, -0.2), "shadow_strength": 0.45,
    },
    ("night", "cold"): {
        "sky_top": (16, 26, 48), "sky_bottom": (52, 70, 102),
        "ground": (52, 50, 48), "sun_color": (180, 200, 235),
        "ambient": 0.22, "key_intensity": 0.5,
        "light_direction": (-0.2, -1.0, -0.25), "shadow_strength": 0.35,
    },
    ("night", "warm"): {
        "sky_top": (20, 26, 44), "sky_bottom": (64, 62, 80),
        "ground": (56, 50, 44), "sun_color": (255, 210, 140),
        "ambient": 0.25, "key_intensity": 0.55,
        "light_direction": (0.3, -1.0, -0.3), "shadow_strength": 0.4,
    },
    ("night", "neutral"): {
        "sky_top": (18, 26, 46), "sky_bottom": (58, 66, 92),
        "ground": (54, 50, 46), "sun_color": (220, 215, 200),
        "ambient": 0.23, "key_intensity": 0.5,
        "light_direction": (0.1, -1.0, -0.25), "shadow_strength": 0.38,
    },
    ("interior", "warm"): {
        "sky_top": (216, 200, 170), "sky_bottom": (232, 220, 196),
        "ground": (120, 96, 66), "sun_color": (255, 224, 170),
        "ambient": 0.55, "key_intensity": 0.7,
        "light_direction": (0.4, -0.8, -0.45), "shadow_strength": 0.4,
    },
    ("interior", "cold"): {
        "sky_top": (190, 200, 210), "sky_bottom": (214, 220, 226),
        "ground": (104, 100, 94), "sun_color": (225, 232, 240),
        "ambient": 0.58, "key_intensity": 0.6,
        "light_direction": (0.35, -0.85, -0.4), "shadow_strength": 0.35,
    },
    ("interior", "neutral"): {
        "sky_top": (204, 200, 190), "sky_bottom": (224, 220, 212),
        "ground": (112, 98, 80), "sun_color": (242, 236, 220),
        "ambient": 0.56, "key_intensity": 0.65,
        "light_direction": (0.38, -0.82, -0.42), "shadow_strength": 0.38,
    },
}


def normalize_time_of_day(value) -> str:
    """Any time-of-day spelling -> day | morning | midday |
    afternoon | dusk | night | interior.

    Unknown/empty values degrade to "day" (the pipeline's default);
    never raises."""
    if not isinstance(value, str):
        return "day"
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    return _TIME_OF_DAY_ALIASES.get(key, "day")


def normalize_mood(value) -> str:
    """Any mood spelling -> warm | cold | neutral (default warm)."""
    if not isinstance(value, str):
        return "warm"
    key = value.strip().lower()
    return key if key in _MOODS else "warm"


def light_for(time_of_day: str = "day", mood: str = "warm",
              weather: str | None = None) -> dict:
    """Palette + key-light spec for a scene.

    ``weather`` containing rain/overcast forces the cold variant of
    the same time of day (flat light, weak shadows) — rain never
    darkens a day scene into night. Returns a plain dict (JSON-safe)
    plus the resolved ``time_of_day``/``mood`` actually used."""
    tod = normalize_time_of_day(time_of_day)
    mood_v = normalize_mood(mood)
    weather_text = (weather or "").lower()
    if any(w in weather_text for w in ("rain", "mưa", "overcast",
                                       "u ám", "cloudy", "nhiều mây")):
        mood_v = "cold"
    spec = dict(TIME_OF_DAY_PALETTES[(tod, mood_v)])
    spec["time_of_day"] = tod
    spec["mood"] = mood_v
    sun = sun_position(spec)
    spec["sun_azimuth_deg"] = sun["azimuth_deg"]
    spec["sun_elevation_deg"] = sun["elevation_deg"]
    return spec


def sun_position(light_spec: dict) -> dict:
    """Sun position derived from a light spec's ``light_direction``.

    ``light_direction`` is the direction light TRAVELS (downward),
    so the sun sits in the opposite direction: ``sun_dir =
    -normalize(light_direction)``. ``elevation_deg`` is the sun's
    angle above the horizon (asin of the sun direction's y) and
    ``azimuth_deg`` is atan2(sun_x, sun_z): 0 deg = +z (behind the
    default camera), increasing toward +x (camera right). The
    convention is documented, not assumed: a dusk key travelling
    (0.7, -0.45, -0.2) puts the sun low in the -x sky (azimuth
    -74 deg, elevation 32 deg), matching long shadows falling
    toward +x. Deterministic and purely derived — no new state.
    """
    direction = light_spec.get("light_direction", (0.35, -1.0, -0.3))
    dx, dy, dz = (float(v) for v in direction)
    norm = math.sqrt(dx * dx + dy * dy + dz * dz)
    if norm == 0:
        raise ValueError("light_direction must not be the zero vector")
    sun = (-dx / norm, -dy / norm, -dz / norm)
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, sun[1]))))
    azimuth = math.degrees(math.atan2(sun[0], sun[2]))
    return {"azimuth_deg": round(azimuth, 3),
            "elevation_deg": round(elevation, 3),
            "direction": tuple(round(v, 6) for v in sun)}


def rig_for(light_spec: dict, points=None) -> LightRig:
    """A renderer25d LightRig from a light_for() spec dict.

    ``points`` (optional) is a list of PointLight objects or
    point-light spec dicts (see ``point_light_spec_to_light``)
    added to the rig. ``None`` (default) reproduces the exact
    previous behaviour: ambient + directional key only."""
    key = DirectionalLight(
        tuple(light_spec["light_direction"]),
        intensity=float(light_spec["key_intensity"]),
        color=tuple(light_spec["sun_color"]),
    )
    point_lights = []
    for p in points or ():
        if isinstance(p, PointLight):
            point_lights.append(p)
        else:
            point_lights.append(point_light_spec_to_light(p))
    return LightRig(ambient=float(light_spec["ambient"]), key=key,
                    points=point_lights)


# Full-strength energy pulse: the PointLight intensity at zero
# distance for a record with intensity == 1.0. A pulse is a
# dramatic light source (lightning held in hand), stronger than
# the forge mouth (1.2); falloff still applies, so only nearby
# surfaces flare.
ENERGY_GLOW_PEAK_INTENSITY = 2.0

# Falloff calibration: falloff_k is chosen so the irradiance at
# the record's ``radius`` is this fraction of the peak:
# 1 / (1 + k*r^2) = 0.05  =>  k = 19 / r^2. Beyond ``radius`` the
# glow is negligible by construction, and ``radius`` means the
# same thing for every caller.
ENERGY_GLOW_EDGE_FRACTION = 0.05


def _is_finite_number(value) -> bool:
    return (isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _validate_vec3(value, field: str):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(
            f"energy_glow[{field!r}] must be a 3-element sequence, "
            f"got {value!r}")
    out = []
    for v in value:
        if not _is_finite_number(v):
            raise ValueError(
                f"energy_glow[{field!r}] entries must be finite "
                f"numbers, got {value!r}")
        out.append(float(v))
    return tuple(out)


def _validate_vec2(value, field: str):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(
            f"energy_glow[{field!r}] must be a 2-element sequence, "
            f"got {value!r}")
    out = []
    for v in value:
        if not _is_finite_number(v):
            raise ValueError(
                f"energy_glow[{field!r}] entries must be finite "
                f"numbers, got {value!r}")
        out.append(float(v))
    return tuple(out)


# Prop-state vocabulary, mirrored from prop_system.PROP_STATES /
# _HELD_STATES (the prop system is the authority; a drift test in
# test_testf_materials.py pins the mirror). A record whose state is
# not a held state must never produce light: the producer already
# returns None for those states, and this consumer treats a stale
# or hand-built record with such a state as dark, loudly and
# visibly (zero-intensity light), never as a glow.
ENERGY_GLOW_PROP_STATES = (
    "WORLD_STATIC", "APPROACHING", "GRASPED", "ATTACHED_TO_HAND",
    "IN_USE", "TRANSFERRED", "RELEASED",
)
ENERGY_GLOW_HELD_STATES = (
    "GRASPED", "ATTACHED_TO_HAND", "IN_USE", "TRANSFERRED",
)


def _validate_rgb(value, field: str, label: str = "energy_glow"):
    """An RGB triple (or "#rrggbb" string) -> (r, g, b) ints."""
    if isinstance(value, str):
        text = value.lstrip("#")
        if len(text) != 6:
            raise ValueError(
                f"{label}[{field!r}] must be an RGB triple or "
                f"'#rrggbb', got {value!r}")
        try:
            value = tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            raise ValueError(
                f"{label}[{field!r}] must be an RGB triple or "
                f"'#rrggbb', got {value!r}") from None
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(
            f"{label}[{field!r}] must be an RGB triple, "
            f"got {value!r}")
    rgb = []
    for c in value:
        if not _is_finite_number(c) or not 0 <= float(c) <= 255:
            raise ValueError(
                f"{label}[{field!r}] channels must be in "
                f"[0, 255], got {value!r}")
        rgb.append(int(round(float(c))))
    return tuple(rgb)


def validate_energy_glow(record) -> dict:
    """Validate + normalize an energy_glow record.

    The record shape is the Agent A / prop-data contract
    (``PropStateMachine.energy_glow_at``), consumed EXACTLY as
    specified in the Test F acting report:

    ``{prop_id, intensity, color, radius, source_position, state,
    holder}`` — ``intensity`` 0..1 (pulse strength, steady
    envelope), ``color`` an RGB triple, ``radius`` the effective
    glow radius, ``source_position`` the glow-centre position,
    ``state`` the prop state, ``holder`` the holding character
    id (or None), ``prop_id`` the prop id.

    Two position spaces exist, and the record says which one it
    is by the length of ``source_position``:

    * 3 elements -> ``position_space == "world"``: (x, y, z) in
      3D world units, ``radius`` in world units. Ready for
      ``energy_glow_to_point_light``.
    * 2 elements -> ``position_space == "pixels"``: (x, y) in the
      2D staging plane (frame pixels), ``radius`` in pixels,
      already intensity-scaled by the producer
      (``radius_px * intensity`` — so a record with intensity 0
      legitimately carries radius 0). Pixel-space records MUST
      pass through ``pixel_glow_to_world_glow`` before they can
      become a light; handing one to
      ``energy_glow_to_point_light`` raises.

    ``prop_id`` / ``state`` / ``holder`` are optional in the
    input (hand-built world-space records, e.g. B's proof
    records, omit them) and carried through when present.
    ``state``, when present, must be a known prop state; a
    non-held state (WORLD_STATIC / RELEASED / APPROACHING)
    normalizes fine but produces no light (see
    ``energy_glow_to_point_light``). ``radius`` may be 0 (the
    intensity-0 case) but never negative.

    Returns a normalized dict. Raises ValueError on any missing
    required key, wrong type, non-finite number, out-of-range
    intensity, negative radius, unknown state, or a
    ``source_position`` that is neither 2 nor 3 elements: a
    malformed record is a programming error and must fail
    loudly, never render a wrong glow silently.
    """
    if not isinstance(record, dict):
        raise ValueError(
            f"energy_glow must be a dict, got {type(record).__name__}")
    for key in ("intensity", "color", "radius", "source_position"):
        if key not in record:
            raise ValueError(f"energy_glow missing required key {key!r}")
    intensity = record["intensity"]
    if not _is_finite_number(intensity):
        raise ValueError(
            f"energy_glow['intensity'] must be a finite number, "
            f"got {intensity!r}")
    intensity = float(intensity)
    if not 0.0 <= intensity <= 1.0:
        raise ValueError(
            f"energy_glow['intensity'] must be in [0, 1], "
            f"got {intensity}")
    rgb = _validate_rgb(record["color"], "color")
    radius = record["radius"]
    if not _is_finite_number(radius) or float(radius) < 0:
        raise ValueError(
            f"energy_glow['radius'] must be a non-negative finite "
            f"number, got {radius!r}")
    raw_pos = record["source_position"]
    if isinstance(raw_pos, (list, tuple)) and len(raw_pos) == 3:
        position = _validate_vec3(raw_pos, "source_position")
        space = "world"
    elif isinstance(raw_pos, (list, tuple)) and len(raw_pos) == 2:
        position = _validate_vec2(raw_pos, "source_position")
        space = "pixels"
    else:
        raise ValueError(
            "energy_glow['source_position'] must be a 2-element "
            f"pixel position or a 3-element world position, "
            f"got {raw_pos!r}")
    out = {"intensity": intensity, "color": rgb,
           "radius": float(radius), "source_position": position,
           "position_space": space}
    if "prop_id" in record:
        if not isinstance(record["prop_id"], str):
            raise ValueError(
                "energy_glow['prop_id'] must be a string, "
                f"got {record['prop_id']!r}")
        out["prop_id"] = record["prop_id"]
    if "state" in record:
        state = record["state"]
        if state not in ENERGY_GLOW_PROP_STATES:
            raise ValueError(
                f"energy_glow['state'] must be one of "
                f"{ENERGY_GLOW_PROP_STATES}, got {state!r}")
        out["state"] = state
    if "holder" in record:
        holder = record["holder"]
        if holder is not None and not isinstance(holder, str):
            raise ValueError(
                "energy_glow['holder'] must be a string or None, "
                f"got {holder!r}")
        out["holder"] = holder
    return out


def energy_glow_to_point_light(record) -> PointLight:
    """A WORLD-space energy_glow record as a renderer25d PointLight.

    Intensity scales linearly with the record's pulse strength
    (0 -> a light contributing nothing; 1 ->
    ENERGY_GLOW_PEAK_INTENSITY). Falloff is calibrated so the
    irradiance at ``radius`` is ENERGY_GLOW_EDGE_FRACTION (5%) of
    the peak. The record's color is the light color (cool/blue
    for the lightning pulse; the consumer does not assume a hue).

    Records that must stay dark return a zero-intensity light
    (same type, contributes nothing, never a crash): intensity 0,
    radius 0 (the producer's intensity-0 scaling), or a non-held
    ``state`` (WORLD_STATIC / RELEASED / APPROACHING — a stale
    record must not glow).

    Pixel-space records raise ValueError: the consumer cannot
    invent the depth that turns a 2D pixel position into a 3D
    light. Convert first with ``pixel_glow_to_world_glow``.
    """
    glow = validate_energy_glow(record)
    if glow["position_space"] != "world":
        raise ValueError(
            "energy_glow record is in pixel space "
            "(2-element source_position); convert it with "
            "pixel_glow_to_world_glow(camera, frame_size, "
            "plane_depth) before making a PointLight — the "
            "lighting stage must not invent a depth")
    dark = (glow["intensity"] <= 0.0 or glow["radius"] <= 0.0
            or ("state" in glow
                and glow["state"] not in ENERGY_GLOW_HELD_STATES))
    if dark:
        return PointLight(glow["source_position"], intensity=0.0,
                          falloff_k=0.08, color=glow["color"])
    radius = glow["radius"]
    falloff_k = ((1.0 / ENERGY_GLOW_EDGE_FRACTION - 1.0)
                 / (radius * radius))
    return PointLight(
        glow["source_position"],
        intensity=glow["intensity"] * ENERGY_GLOW_PEAK_INTENSITY,
        falloff_k=falloff_k,
        color=glow["color"],
    )


def _camera_basis(camera):
    """(right, up, fwd) unit vectors from a camera's position/target/up.

    Mirrors the projection basis in renderer25d/camera.py (and the
    ``_camera_basis`` helper in environment_v2.py) without touching
    the camera's privates: fwd is the normalized target-direction,
    right is fwd x up, cam-up is right x fwd."""
    def _sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def _cross(a, b):
        return (a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0])

    def _norm(a):
        n = math.sqrt(sum(v * v for v in a))
        if n == 0:
            raise ValueError("zero-length vector has no direction")
        return tuple(v / n for v in a)

    fwd = _norm(_sub(camera.target, camera.position))
    right = _norm(_cross(fwd, camera.up))
    return right, _cross(right, fwd), fwd


def unproject_pixel(camera, px: float, py: float,
                    frame_size, plane_depth: float):
    """World point of a screen pixel at a stated camera-space depth.

    The exact inverse of ``PerspectiveCamera.project`` at depth
    ``plane_depth``: the ray through pixel (``px``, ``py``) of a
    ``frame_size`` (width, height) frame meets the plane
    ``depth == plane_depth`` (camera-space forward distance from
    the camera position) at the returned (x, y, z) world point.
    ``plane_depth`` must exceed the camera's near plane; the
    caller supplies it from a known world anchor (e.g.
    ``camera.depth_of(holder_ground_position)``) — the lighting
    stage never guesses a depth. Round-trips
    ``project(unproject(p)) == p`` to float precision (tested).
    """
    width, height = int(frame_size[0]), int(frame_size[1])
    if width <= 0 or height <= 0:
        raise ValueError(f"frame_size must be positive, got {frame_size!r}")
    if not _is_finite_number(px) or not _is_finite_number(py):
        raise ValueError(
            f"pixel coordinates must be finite numbers, got {(px, py)!r}")
    depth = float(plane_depth)
    if not math.isfinite(depth) or depth <= float(camera.near):
        raise ValueError(
            f"plane_depth must exceed the camera near plane "
            f"({camera.near}), got {plane_depth!r}")
    f = camera.focal_px(height)
    xc = (float(px) - width / 2.0) * depth / f
    yc = (height / 2.0 - float(py)) * depth / f
    right, up, fwd = _camera_basis(camera)
    pos = tuple(float(v) for v in camera.position)
    return tuple(pos[k] + xc * right[k] + yc * up[k] + depth * fwd[k]
                 for k in range(3))


def pixel_glow_to_world_glow(record, camera, frame_size, plane_depth):
    """A pixel-space energy_glow record -> a world-space record.

    The ONLY sanctioned crossing between the prop system's 2D
    staging plane and the environment renderer's 3D world. The
    input record is validated (see ``validate_energy_glow``) and
    must be in pixel space (2-element ``source_position``); the
    output record carries the same ``prop_id`` / ``intensity`` /
    ``color`` / ``state`` / ``holder``, a 3-element world
    ``source_position`` from ``unproject_pixel`` at
    ``plane_depth``, and ``radius`` converted from pixels to
    world units at that depth (``radius_px * depth / focal`` —
    the inverse of ``project_size``).

    ``plane_depth`` is the camera-space depth of the plane
    containing the glow source — in practice the holder's depth
    plane: ATLAS computes it as
    ``camera.depth_of(holder_ground_world_position)`` in the
    product renderer, which owns both the holder's world
    position and the shot camera. The pixel coordinates must be
    expressed in the pixel space of the frame this camera
    renders: if the product renderer crops the shot canvas, it
    must translate the record's position by the crop offset
    BEFORE calling this function.

    World-space records pass through unchanged (validated, same
    values) so callers can convert unconditionally.
    """
    glow = validate_energy_glow(record)
    if glow["position_space"] == "world":
        return glow
    px, py = glow["source_position"]
    world_pos = unproject_pixel(camera, px, py, frame_size, plane_depth)
    height = int(frame_size[1])
    depth = float(plane_depth)
    world_radius = glow["radius"] * depth / camera.focal_px(height)
    out = dict(glow)
    out["source_position"] = world_pos
    out["radius"] = world_radius
    out["position_space"] = "world"
    return out


def paint_energy_glow(img: Image.Image, record) -> None:
    """Paint a pixel-space energy_glow halo onto a frame, in place.

    The 2D consumer of ``PropStateMachine.energy_glow_at``: the
    record's ``source_position`` is already in staging-plane
    pixels -- the same space the product renderer's frames are
    built in -- so no bridge is needed here (the bridge,
    ``pixel_glow_to_world_glow``, is for the 3D path only).

    The halo is a deterministic radial gradient (48 rings,
    quadratic falloff, peak alpha 0.55 * intensity) composited
    over the frame; the record's ``radius`` is already
    intensity-scaled by the producer. No flicker is
    synthesised: the intensity envelope is the steady ramp from
    the state machine. A record with radius 0 paints nothing.
    World-space records raise: handing one here would paint a
    world coordinate as if it were a pixel. Malformed records
    raise via ``validate_energy_glow`` -- never a silent wrong
    glow.
    """
    glow = validate_energy_glow(record)
    if glow["position_space"] != "pixels":
        raise ValueError(
            "paint_energy_glow needs a pixel-space energy_glow "
            "record; a world-space record belongs to "
            "energy_glow_to_point_light (3D path)")
    overlay = _energy_glow_overlay(img.size, glow)
    if overlay is None:
        return
    composited = Image.alpha_composite(
        img.convert("RGBA"), overlay).convert(img.mode)
    img.paste(composited, (0, 0))


def _energy_glow_overlay(size, glow):
    """The 48-ring radial halo layer for a validated record, or
    None when the radius paints nothing. Shared by the plain and
    the exclusion-masked painters so both render the same halo.
    """
    radius = float(glow["radius"])
    if radius <= 0:
        return None
    cx, cy = (float(v) for v in glow["source_position"])
    color = tuple(int(c) for c in glow["color"])
    peak = 0.55 * float(glow["intensity"])
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rings = 48
    for i in range(rings, 0, -1):
        frac = 1.0 - (i / rings) ** 2
        alpha = int(round(255 * peak * frac))
        if alpha <= 0:
            continue
        r = radius * i / rings
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=color + (alpha,))
    return overlay


def paint_light_pool(img: Image.Image, record,
                   ground_y: float) -> None:
    """Paint a ground pool of light under a glow source, in place.

    Round 10 (R10-6): a radial halo alone reads as a flat 2D
    sticker -- light reads as 3D when it lands on a surface. The
    pool is the same deterministic ring gradient as the halo,
    squashed into a floor-plane ellipse (vertical squash 0.38)
    centred on the ground line directly below the source, wider
    than the halo (1.6x radius) and dimmer (0.6x peak): bounced
    light, not a second source. Painted at the glow stage (before
    the characters), so the cast stands IN the lit floor. A
    record with radius 0 paints nothing; world-space records
    raise, like :func:`paint_energy_glow`.
    """
    glow = validate_energy_glow(record)
    if glow["position_space"] != "pixels":
        raise ValueError(
            "paint_light_pool needs a pixel-space energy_glow "
            "record")
    radius = float(glow["radius"])
    if radius <= 0:
        return
    cx = float(glow["source_position"][0])
    cy = float(ground_y)
    color = tuple(int(c) for c in glow["color"])
    peak = 0.55 * float(glow["intensity"]) * 0.6
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rings = 48
    for i in range(rings, 0, -1):
        frac = 1.0 - (i / rings) ** 2
        alpha = int(round(255 * peak * frac))
        if alpha <= 0:
            continue
        rx = radius * 1.6 * i / rings
        ry = rx * 0.38
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                     fill=color + (alpha,))
    composited = Image.alpha_composite(
        img.convert("RGBA"), overlay).convert(img.mode)
    img.paste(composited, (0, 0))


def paint_energy_glow_excluding(img: Image.Image, record,
                                boxes, feather_px: float = 24.0,
                                holes=()) -> None:
    """A halo that does not wash the excluded boxes (round 6,
    R2-F1): the deferred insert path repaints halos onto
    flattened, cropped frames, where painter's order cannot
    protect the cast — the halo bleached the leg the stone
    rested against. ``boxes`` are (x0, y0, x1, y1) pixel rects
    in the frame's own coordinates (the characters' posed limbs
    mapped through the frozen crop); the halo is masked out
    inside them with a feathered edge, so the light spills
    onto the environment around the cast instead of over it.
    ``holes`` are (cx, cy, r) pixel discs that stay lit even
    inside a box (round 7): the glowing prop itself, which
    sits between the limbs, must read. An empty box list
    paints exactly like :func:`paint_energy_glow`."""
    glow = validate_energy_glow(record)
    if glow["position_space"] != "pixels":
        raise ValueError(
            "paint_energy_glow_excluding needs a pixel-space "
            "energy_glow record")
    overlay = _energy_glow_overlay(img.size, glow)
    if overlay is None:
        return
    base = img.convert("RGBA")
    composited = Image.alpha_composite(base, overlay)
    if not boxes and not holes:
        img.paste(composited.convert(img.mode), (0, 0))
        return
    mask = Image.new("L", img.size, 255)
    draw = ImageDraw.Draw(mask)
    for (x0, y0, x1, y1) in boxes:
        draw.rectangle([x0, y0, x1, y1], fill=0)
    for (cx, cy, r) in holes:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    if feather_px > 0:
        mask = mask.filter(
            ImageFilter.GaussianBlur(radius=float(feather_px)))
    img.paste(Image.composite(composited, base, mask).convert(
        img.mode), (0, 0))


def point_light_spec_to_light(spec: dict) -> PointLight:
    """A JSON-safe point-light spec dict -> PointLight.

    Spec shape (as emitted in EnvironmentPackage["point_lights"]):
    ``{position, intensity, falloff_k, color}`` plus an optional
    ``id`` (ignored here, kept for provenance). ``falloff_k``
    defaults to the renderer25d PointLight default (0.08) when
    absent. Raises ValueError on missing/invalid fields."""
    if not isinstance(spec, dict):
        raise ValueError(f"point light spec must be a dict, got {spec!r}")
    if "position" not in spec:
        raise ValueError("point light spec missing required key 'position'")
    position = _validate_vec3(spec["position"], "position")
    intensity = spec.get("intensity", 1.0)
    if not _is_finite_number(intensity) or float(intensity) < 0:
        raise ValueError(
            f"point light 'intensity' must be >= 0, got {intensity!r}")
    falloff_k = spec.get("falloff_k", 0.08)
    if not _is_finite_number(falloff_k) or float(falloff_k) < 0:
        raise ValueError(
            f"point light 'falloff_k' must be >= 0, got {falloff_k!r}")
    color = spec.get("color", (255, 220, 160))
    if not isinstance(color, (list, tuple)) or len(color) != 3:
        raise ValueError(
            f"point light 'color' must be an RGB triple, got {color!r}")
    rgb = []
    for c in color:
        if not _is_finite_number(c) or not 0 <= float(c) <= 255:
            raise ValueError(
                f"point light 'color' channels must be in [0, 255], "
                f"got {color!r}")
        rgb.append(int(round(float(c))))
    return PointLight(position, intensity=float(intensity),
                      falloff_k=float(falloff_k), color=tuple(rgb))


def shade_color(base_rgb, irradiance: float):
    """Apply irradiance (0..~2) to a base colour, clamped 0..255."""
    f = min(1.0, max(0.0, float(irradiance)))
    return tuple(min(255, max(0, int(round(c * f)))) for c in base_rgb)


def point_light_gain(rig, point, normal):
    """Per-channel multiplicative gain (>= 1) from a rig's point lights.

    ``gain[ch] = 1 + sum_p(irradiance_p * color_p[ch] / 255)``.
    Multiplying an already-lit colour by the gain applies the
    point-light tint without re-applying ambient/key shading.
    Returns exactly ``(1.0, 1.0, 1.0)`` when the rig has no point
    lights. The rig's ambient/key lights are NOT included: this
    is the point-light pass only, with the same 1/(1+k*d^2)
    falloff and Lambert cosine the rig already computes.
    """
    gain = [1.0, 1.0, 1.0]
    for p in getattr(rig, "points", None) or ():
        irr = p.irradiance(point, normal)
        if irr <= 0.0:
            continue
        for ch in range(3):
            gain[ch] += irr * (p.color[ch] / 255.0)
    return tuple(gain)


def tod_surface_response(light_spec: dict,
                       base_rgb: tuple[int, int, int],
                       sky_rgb: tuple[int, int, int] | None = None,
                       blend_sky: bool = True
                       ) -> tuple[int, int, int]:
    """Time-of-day response for a surface base colour (sky
    override, facade, roof, ground).

    Round 9 (R2-V4 residual): archetype interiors (cave, forge)
    replaced the tod sky palette with FIXED override colours, so
    the interior backdrop was pixel-identical at every hour and
    only the weak key tint moved the walls (+0.22 R/B midday ->
    afternoon). Round 10 (R10-2): the sky response alone never
    reached delivered interior frames -- the sky is barely
    visible indoors, and the render-time key tint leaves
    inward-facing walls at flat ambient. The same response now
    bakes into the facade, roof and ground base colours, so the
    time of day reads on walls and floors in every archetype.
    The override keeps the interior's identity (a cave stays
    dark), but it must still answer the time of day: neutral
    daylight through the openings at midday, golden light in
    the afternoon, a dimmer backdrop at dusk so the fire and
    torch dominate.

    Two factors, both from the tod palette:

    * tint: ``0.20 + 0.80 * sun_color[ch]/255`` per channel -- a
      white noon sun is near-neutral, an amber afternoon sun
      warms the surface, a dusk sun warms it more. Round 11
      strengthened this from ``0.5 + 0.5 * s``; round 13 from
      ``0.30 + 0.70 * s``: the wall gaps STALLED between rounds
      11 and 12 (the round-12 tod work touched sky, glass and
      lamps, never this curve), and the reference palettes
      still shout where ours whisper;
    * brightness: the palette's light level
      ``ambient + 0.5 * key_intensity`` against the midday/warm
      reference (0.97), clamped to [0.50, 1.10] -- dusk dims to
      ~0.80, night to ~0.50 so a deep-blue night actually reads
      dark (the old 0.55 floor held it back), day tods stay near
      1.0. The clamp keeps a cave dark at every hour (its
      day-luminance-floor exemption stands).

    Round 13 adds a third term, the SKY BLEND: the tinted colour
    blends toward ``sky_bottom`` when the sky is coloured or
    dark (driver = saturation + darkness, zero for pale daylight
    skies), up to 30%. Ambient skylight tints every surface in
    reality; without it a dusk wall is dark brown where the
    reference is pink-orange, and a warm night stays amber where
    the sky is deep blue. The blend is skipped when the spec
    carries no sky (the white-sun identity property stands).

    Round 14: ``sky_rgb`` overrides the blend target. The facade
    bake runs AFTER interior overrides replace the spec's sky
    with a dark backdrop, and blending toward that backdrop
    warmed every interior at every hour (midday forge +0.129
    R/B, which kept the cave-forge gap flat in R13). Callers
    that bake surfaces pass the OUTSIDE sky here; the default
    (the spec's own sky) is kept for the sky-override
    computation itself, which runs before the mutation lands.

    Round 14 (suite fix): ``blend_sky=False`` skips the blend
    entirely. Enclosed archetypes (forge, cave, interior) have
    no visible sky: their surfaces cannot receive skylight, and
    blending them toward the outside sky made the forge ground
    BRIGHTER at dusk than at midday (the dusk-pink blend
    outweighed the dimming tint), breaking the R10 "dims at
    dusk" pin. Enclosed surfaces answer the time of day through
    the tint + brightness terms only; their warmth comes from
    the point lights (forge mouth, torch) at render time.
    """
    sun = tuple(light_spec.get("sun_color", (255, 255, 255)))
    level = float(light_spec.get("ambient", 0.5)) \
        + 0.5 * float(light_spec.get("key_intensity", 1.0))
    brightness = min(1.10, max(0.50, level / 0.97))
    tinted = tuple(
        float(base_rgb[ch]) * brightness
        * (0.20 + 0.80 * (float(sun[ch]) / 255.0))
        for ch in range(3))
    sky = sky_rgb if sky_rgb is not None else light_spec.get("sky_bottom")
    if blend_sky and sky is not None:
        sky = tuple(float(c) for c in sky)
        mx, mn = max(sky), min(sky)
        sat = (mx - mn) / max(1.0, mx)
        lum = sum(sky) / 3.0
        driver = min(1.0, max(0.0, (0.35 - lum / 255.0) + sat))
        w = min(0.30, 0.6 * driver)
        tinted = tuple(tinted[ch] * (1.0 - w) + sky[ch] * w
                       for ch in range(3))
    return tuple(
        min(255, max(0, int(round(tinted[ch])))) for ch in range(3))


# Round-9 name for the sky-override call site; the response is
# the same function.
interior_sky_response = tod_surface_response


def key_factor_for(rig, point, normal):
    """Per-channel ambient+key factor (each 0..1) for ``rig`` at
    ``point``/``normal``: ``ambient + key_irr * key_color[ch]/255``.

    The key light's colour tints faces: a white key reproduces
    the scalar ``ambient + key_irr`` on every channel, an amber
    afternoon key suppresses blue, a cold moon suppresses red.
    Flat faces apply this factor in ``shade_with_points``;
    textured faces fold it into the paste gain (the texture
    paste takes a scalar brightness plus a per-channel gain).
    One definition, so flat and textured faces of one element
    can never disagree about the sun."""
    key = getattr(rig, "key", None)
    key_irr = key.irradiance(point, normal) if key is not None else 0.0
    if key is not None:
        key_color = tuple(getattr(key, "color", (255, 255, 255)))
    else:
        key_color = (255, 255, 255)
    ambient = float(getattr(rig, "ambient", 0.0))
    return tuple(
        min(1.0, max(0.0, ambient + key_irr
                     * (float(key_color[ch]) / 255.0)))
        for ch in range(3))


def shade_with_points(base_rgb, rig, point, normal):
    """Lambert shade with a COLORED key light plus colored point
    lights.

    Round 8 (R2-V4): the key light used to shade as a neutral
    (grayscale) factor, so the palette's ``sun_color`` never
    reached a shaded face -- a white noon sun and an amber
    afternoon sun produced identical wall hues, and interiors
    (whose skies are overridden) showed no time-of-day hue at
    all. Now the key tints per channel, exactly like a point
    light: ``factor[ch] = ambient + key_irr * key_color[ch]/255``
    (clamped to 1.0 per channel), and each point light ADDS its
    own tinted contribution on top. A white key reproduces
    ``shade_color`` exactly; an amber key warms sunlit faces
    and a cold moon cools them. The renderer25d legacy path
    (``shade``) stays grayscale -- see the design doc."""
    factor = key_factor_for(rig, point, normal)
    out = [float(base_rgb[ch]) * factor[ch] for ch in range(3)]
    for p in getattr(rig, "points", None) or ():
        irr = p.irradiance(point, normal)
        if irr <= 0.0:
            continue
        for ch in range(3):
            out[ch] += irr * float(base_rgb[ch]) * (p.color[ch] / 255.0)
    return tuple(min(255, max(0, int(round(v)))) for v in out)


def add_point_light_tint(base_rgb, rig, point, normal):
    """Additive point-light pass over an ALREADY-LIT colour.

    Unlike ``shade_with_points``, this does NOT apply ambient/key
    shading: it multiplies the colour by ``point_light_gain``
    only. Use it for colours that already carry their base
    lighting — ground gradient bands, and (ATLAS wiring)
    character fills in product_renderer — so the glow brightens
    and tints without double-darkening. With no point lights the
    input colour is returned unchanged (as ints).
    """
    gain = point_light_gain(rig, point, normal)
    return tuple(min(255, max(0, int(round(c * gain[ch]))))
                 for ch, c in enumerate(base_rgb))


# ---------------------------------------------------------------------------
# Prop material catalog (Test F / B2) — DATA for the semantic prop system
# ---------------------------------------------------------------------------

# The locked cartoon ink, measured from Mai's reference image
# (#14222B). The same value as product_renderer.INK_RGB (the
# product renderer is the drawing authority; this module repeats
# the literal rather than importing the renderer, and a test pins
# the equality). Every catalog material outlines in this ink so
# props share the reference line language.
MATERIAL_INK = (20, 34, 43)

# Catalog entry fields (all JSON-safe types; colors are RGB
# triples of ints 0..255):
#
#   base_color:         diffuse fill colour of the prop surface.
#   outline:            cartoon outline colour (MATERIAL_INK).
#   emissive_color:     colour of light the material EMITS;
#                       (0, 0, 0) means "not emissive".
#   emissive_intensity: normalized emission strength, 0..1.
#                       0 = not emissive. 1.0 converts to a
#                       PointLight of ENERGY_GLOW_PEAK_INTENSITY
#                       (see material_emissive_light).
#   emissive_radius:    5%-edge radius of the emitted light in
#                       WORLD units (same calibration as an
#                       energy_glow radius); 0 = no light.
#
# The catalog is DEFAULTS, not per-story art direction: a prop
# may override any field from script/trait data through
# resolve_material (a dict with a "base" catalog name plus
# overrides, or a complete standalone entry). Overrides are
# validated exactly like catalog entries — an invalid override
# fails loudly, never renders a wrong material silently.
#
# NAMESPACE WARNING: these names are the PROP material catalog
# consumed by the semantic prop system (A2 geometry slots +
# ATLAS product renderer). They are NOT the environment surface
# texture names in paint_textures.py (plaster/brick/stone/...)
# consumed by environment_v2 faces. "stone" and "wood" exist in
# both namespaces with different meanings (a stone PROP's flat
# fill vs. a painted stone WALL texture). Never look one up in
# the other's table.
MATERIAL_CATALOG = {
    "leather": {
        "base_color": (146, 94, 48),
        "outline": MATERIAL_INK,
        "emissive_color": (0, 0, 0),
        "emissive_intensity": 0.0,
        "emissive_radius": 0.0,
    },
    "steel": {
        "base_color": (150, 156, 162),
        "outline": MATERIAL_INK,
        "emissive_color": (0, 0, 0),
        "emissive_intensity": 0.0,
        "emissive_radius": 0.0,
    },
    "gold-emissive": {
        "base_color": (232, 190, 60),
        "outline": MATERIAL_INK,
        "emissive_color": (255, 210, 90),
        "emissive_intensity": 0.6,
        "emissive_radius": 2.5,
    },
    "paper": {
        "base_color": (240, 234, 214),
        "outline": MATERIAL_INK,
        "emissive_color": (0, 0, 0),
        "emissive_intensity": 0.0,
        "emissive_radius": 0.0,
    },
    "wood": {
        "base_color": (122, 74, 43),
        "outline": MATERIAL_INK,
        "emissive_color": (0, 0, 0),
        "emissive_intensity": 0.0,
        "emissive_radius": 0.0,
    },
    "stone": {
        "base_color": (140, 136, 128),
        "outline": MATERIAL_INK,
        "emissive_color": (0, 0, 0),
        "emissive_intensity": 0.0,
        "emissive_radius": 0.0,
    },
    "cloth": {
        "base_color": (96, 116, 148),
        "outline": MATERIAL_INK,
        "emissive_color": (0, 0, 0),
        "emissive_intensity": 0.0,
        "emissive_radius": 0.0,
    },
    "bronze": {
        "base_color": (176, 124, 64),
        "outline": MATERIAL_INK,
        "emissive_color": (0, 0, 0),
        "emissive_intensity": 0.0,
        "emissive_radius": 0.0,
    },
}

_MATERIAL_FIELDS = ("base_color", "outline", "emissive_color",
                    "emissive_intensity", "emissive_radius")


def material_names() -> list[str]:
    """Catalog material names, in catalog order."""
    return list(MATERIAL_CATALOG.keys())


def get_material(name: str) -> dict:
    """A COPY of a catalog entry (mutating it never affects the
    catalog). Raises KeyError on an unknown name: an unknown
    material is a data error and must fail loudly, never fall
    back to a silent default fill."""
    entry = MATERIAL_CATALOG[name]  # KeyError by design
    return {field: (tuple(entry[field])
                    if isinstance(entry[field], tuple)
                    else entry[field])
            for field in _MATERIAL_FIELDS}


def validate_material_entry(entry) -> dict:
    """Validate + normalize a material entry dict.

    Requires all five catalog fields with valid values (RGB
    triples 0..255, emissive_intensity 0..1, emissive_radius
    >= 0). A non-emissive entry (intensity 0 or radius 0) keeps
    its emissive_color as data but emits no light (see
    ``material_emissive_light``). Raises ValueError on any
    missing field or invalid value."""
    if not isinstance(entry, dict):
        raise ValueError(
            f"material entry must be a dict, got {type(entry).__name__}")
    for field in _MATERIAL_FIELDS:
        if field not in entry:
            raise ValueError(
                f"material entry missing required field {field!r}")
    out = {}
    for field in ("base_color", "outline", "emissive_color"):
        out[field] = _validate_rgb(entry[field], field, "material")
    intensity = entry["emissive_intensity"]
    if not _is_finite_number(intensity) or not 0.0 <= float(intensity) <= 1.0:
        raise ValueError(
            "material 'emissive_intensity' must be in [0, 1], "
            f"got {intensity!r}")
    out["emissive_intensity"] = float(intensity)
    radius = entry["emissive_radius"]
    if not _is_finite_number(radius) or float(radius) < 0:
        raise ValueError(
            "material 'emissive_radius' must be >= 0, "
            f"got {radius!r}")
    out["emissive_radius"] = float(radius)
    return out


def resolve_material(spec) -> dict:
    """A material spec -> a validated, normalized entry.

    ``spec`` is either a catalog name (str) or a dict. A dict
    may carry ``"base": "<catalog-name>"`` plus any field
    overrides (script/trait data overriding a default), or be a
    complete standalone entry with all five fields. Unknown
    catalog names raise KeyError; invalid values raise
    ValueError; unknown dict keys (other than "base") raise
    ValueError — a typo'd field must never be silently ignored.
    """
    if isinstance(spec, str):
        return get_material(spec)
    if not isinstance(spec, dict):
        raise ValueError(
            f"material spec must be a name or a dict, "
            f"got {type(spec).__name__}")
    unknown = set(spec) - set(_MATERIAL_FIELDS) - {"base"}
    if unknown:
        raise ValueError(
            f"material spec has unknown field(s): {sorted(unknown)}")
    base = get_material(spec["base"]) if "base" in spec else {}
    merged = dict(base)
    for field in _MATERIAL_FIELDS:
        if field in spec:
            merged[field] = spec[field]
    return validate_material_entry(merged)


def material_emissive_light(material, position) -> PointLight | None:
    """A material entry's emitted light at a world position, or None.

    ``material`` is a validated entry (see ``resolve_material``)
    or a catalog name. Returns None when the material is not
    emissive (intensity 0 or radius 0). Otherwise a PointLight
    with the material's emissive color, intensity =
    ``emissive_intensity * ENERGY_GLOW_PEAK_INTENSITY``, and
    falloff calibrated so the irradiance at ``emissive_radius``
    is ENERGY_GLOW_EDGE_FRACTION (5%) of the peak — the same
    calibration as energy_glow, so a material light and a pulse
    light compose in the same units."""
    entry = (resolve_material(material) if isinstance(material, str)
             else validate_material_entry(material))
    intensity = entry["emissive_intensity"]
    radius = entry["emissive_radius"]
    if intensity <= 0.0 or radius <= 0.0:
        return None
    pos = _validate_vec3(position, "position")
    falloff_k = ((1.0 / ENERGY_GLOW_EDGE_FRACTION - 1.0)
                 / (radius * radius))
    return PointLight(
        pos, intensity=intensity * ENERGY_GLOW_PEAK_INTENSITY,
        falloff_k=falloff_k, color=entry["emissive_color"])


def material_catalog_json() -> dict:
    """The catalog as JSON-safe data (tuples -> lists).

    For the asset registry / Motion Canvas emitter: the same
    values as MATERIAL_CATALOG, serializable without a custom
    encoder."""
    out = {}
    for name, entry in MATERIAL_CATALOG.items():
        out[name] = {
            field: (list(entry[field])
                    if isinstance(entry[field], tuple)
                    else entry[field])
            for field in _MATERIAL_FIELDS}
    return out


def shadow_ellipse_spec(ground_pos, height_above_ground: float,
                        base_radius: float, light: DirectionalLight,
                        camera, frame_size, footprint_half_width_px: float,
                        is_ground_slab: bool = False,
                        footprint_half_depth_px: float | None = None
                        ) -> dict | None:
    """Screen-space contact-shadow ellipse, ratio-capped.

    ``ground_pos`` is the object's (x, 0, z) ground position,
    ``height_above_ground`` its lift, ``base_radius`` its ground
    footprint radius in world units, ``footprint_half_width_px``
    the object's projected half-width in screen pixels (the cap
    reference — the caller measures its own footprint, so the
    shadow can never outgrow its object).

    ``footprint_half_depth_px`` (optional) is the projected
    half-depth: when given, the ellipse's vertical extent is
    capped by the footprint's DEPTH extent too. This is what
    keeps a wide flat wall's shadow a thin strip along its base
    instead of a giant radial blob: the single-radius geometry
    would otherwise size both axes from the wall's width.

    Returns ``None`` for ground slabs (paths, kerbs) and for objects
    behind the camera. Otherwise a dict with ``center_px``,
    ``rx_px``, ``ry_px``, ``alpha`` and ``capped`` (True when the
    ratio cap actually reduced the ellipse). The ellipse is
    guaranteed: ``rx_px <= SHADOW_WIDTH_RATIO_MAX *
    footprint_half_width_px``, ``ry_px <= SHADOW_HEIGHT_RATIO *
    (2 * rx_px)``... i.e. height <= 0.31 x width, and
    ``alpha <= SHADOW_ALPHA_MAX``. Callers must still clip the
    drawn ellipse to below the horizon (see render_environment).
    """
    if is_ground_slab:
        return None
    sh = contact_shadow(ground_pos, float(height_above_ground),
                        float(base_radius), light)
    cx, cz = sh["center"]
    px, py, pscale, vis = camera.project((cx, 0.0, cz), *frame_size)
    if not vis:
        return None
    rx = sh["radius_x"] * pscale
    ry = sh["radius_z"] * pscale
    capped = False
    # Half-pixel tolerance: a geometry-correct ellipse sits exactly
    # ON the height-ratio boundary, and float noise must not flip
    # the "capped" flag.
    max_rx = SHADOW_WIDTH_RATIO_MAX * max(1.0, float(footprint_half_width_px))
    if rx > max_rx + 0.5:
        rx = max_rx
        capped = True
    max_ry = SHADOW_HEIGHT_RATIO * 2.0 * rx
    if ry > max_ry + 0.5:
        ry = max_ry
        capped = True
    if footprint_half_depth_px is not None:
        max_ry_depth = (SHADOW_WIDTH_RATIO_MAX
                        * max(1.0, float(footprint_half_depth_px)))
        if ry > max_ry_depth + 0.5:
            ry = max_ry_depth
            capped = True
    alpha = min(SHADOW_ALPHA_MAX, max(SHADOW_ALPHA_MIN, sh["alpha"]))
    if rx < 1 or ry < 1:
        return None
    return {"center_px": (px, py), "rx_px": rx, "ry_px": ry,
            "alpha": alpha, "capped": capped,
            "offset_world": sh["offset_world"]}


# Round 13 (R13-3): cast shadows. The contact ellipse above is
# capped to the footprint by design (W1) -- it can never show a
# long dusk shadow. The cast shadow is a separate ground-plane
# shape: a tapered quad from the feet along the light's ground
# direction, length = height * spread (the same spread the
# contact shadow uses for its offset), capped at 2.2 heights.
# High sun (length < 0.25 heights) returns None: the contact
# shadow already covers it.
CAST_SHADOW_ALPHA = 0.30
CAST_SHADOW_LENGTH_MAX = 2.2
CAST_SHADOW_LENGTH_MIN_FRAC = 0.25


def cast_shadow_spec(ground_pos, height: float, half_width: float,
                     light: DirectionalLight, camera, frame_size
                     ) -> dict | None:
    """Screen-space cast-shadow quad for a standing object.

    ``ground_pos`` is the object's (x, 0, z) ground position,
    ``height`` its world height, ``half_width`` its ground
    half-width in world units. Returns ``None`` for high sun, a
    straight-down light, or unprojectable corners. Otherwise a
    dict with ``polygon_px`` (4 screen points, near pair first),
    ``alpha`` and ``length_world``.
    """
    gx, gz = light.ground_direction()
    if gx == 0.0 and gz == 0.0:
        return None
    elev = max(0.15, light.elevation_factor())
    spread = (1.0 - elev) / elev
    height = float(height)
    length = min(height * spread, CAST_SHADOW_LENGTH_MAX * height)
    if length < CAST_SHADOW_LENGTH_MIN_FRAC * height:
        return None
    px_, pz = -gz, gx  # ground-plane perpendicular
    x0, z0 = float(ground_pos[0]), float(ground_pos[2])
    hw = float(half_width)
    corners = [
        (x0 - px_ * hw, 0.0, z0 - pz * hw),
        (x0 + px_ * hw, 0.0, z0 + pz * hw),
        (x0 + gx * length + px_ * hw * 0.6, 0.0,
         z0 + gz * length + pz * hw * 0.6),
        (x0 + gx * length - px_ * hw * 0.6, 0.0,
         z0 + gz * length - pz * hw * 0.6),
    ]
    pts = []
    for corner in corners:
        sx, sy, _, vis = camera.project(corner, *frame_size)
        if not vis:
            return None
        pts.append((sx, sy))
    return {"polygon_px": pts, "alpha": CAST_SHADOW_ALPHA,
            "length_world": length}


def measure_mean_luminance(img: Image.Image) -> float:
    """Mean luminance (0..255) of a PIL image, histogram-based."""
    grey = img.convert("L")
    hist = grey.histogram()
    total = sum(hist)
    if total == 0:
        return 0.0
    return sum(i * count for i, count in enumerate(hist)) / total


def sky_band_luminance(img: Image.Image, band_h: int = 150) -> float:
    """Mean luminance of the top ``band_h`` pixel rows (the sky band)."""
    band = img.crop((0, 0, img.size[0], min(band_h, img.size[1])))
    return measure_mean_luminance(band)


def check_day_brightness(img: Image.Image,
                         floor: float = DAY_LUMINANCE_FLOOR) -> dict:
    """Regression check: is this rendered DAY frame bright enough?

    Returns ``{mean_luminance, sky_band_luminance, floor, ok}``.
    ``ok`` is False when the frame mean falls below the floor —
    the signature of the dark-daytime failure mode."""
    mean = measure_mean_luminance(img)
    sky = sky_band_luminance(img)
    return {"mean_luminance": round(mean, 2),
            "sky_band_luminance": round(sky, 2),
            "floor": floor, "ok": mean >= floor}
