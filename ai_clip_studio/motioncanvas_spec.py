"""Motion Canvas spec emitter: V1 adapter package -> World25D specs.

Pure functions (stdlib only) mapping a V1 adapter package + a shot
plan (``plan_shots`` output) + the measured timeline total to the
data-driven 3D world specs consumed by
``ai_clip_studio/motioncanvas25d/`` (``World25D.ts`` via
``scene25d.tsx`` or ``render25d.mjs``). One spec per scene: a scene
is one location, and a ``World25D`` world is one location, so a
multi-scene job emits one spec per scene, each independently
renderable. The job-level envelope (``emit_job_spec``) is what the
pipeline writes as ``world25d_spec.json``.

Generality rules (no per-script code anywhere in this module):

* Location -> world mapping is driven ONLY by generic location data:
  time of day + mood (lighting presets), the foreground / midground /
  background feature lists, the free feature list, and the palette.
  No location, script, character or place name is ever matched: two
  packages that differ only in names produce identical geometry
  (a test asserts this).
* Camera keyframes derive per shot from shot type + camera angle +
  camera movement + subject staging. Every shot gets a REAL
  viewpoint: position and target change per shot (spherical
  geometry around the subject, mirroring ``camera_planner``), the
  camera is FIXED within a shot (start and end keyframes carry the
  identical pose), and framing changes by HARD CUT at shot
  boundaries (the ``cut`` keyframe flag, honoured by
  ``World25D.updateCamera``). FOV is constant (46 deg): a shot-type
  change is a viewpoint change, never a zoom.
* Durations come ONLY from the shot plan (itself built from the
  measured audio timeline). There is no fixed duration anywhere in
  this module; the timeline total is carried through for a
  cross-check note only and never rescales anything.
* Character anchors come from the scene cast + deterministic
  staging (feet on the ground plane, heights from the package's
  ``height_px``). Anchor ids are the package's own character ids
  (data, not name matching).

Keyframe times are SCENE-LOCAL (0 at the scene start); the spec
carries ``start_sec`` / ``end_sec`` for the scene's place in the
job. ``render25d.mjs`` renders one scene spec standalone from t=0.

Schema (single-scene spec, the shape ``example_spec.json`` uses)::

    {
      "scene": <int>, "start_sec": <float>, "end_sec": <float>,
      "duration_seconds": <float>,  # sum of this scene's shot durations
      "world": {<World25DSpec: sky/ground/boxes/lights/camera/anchors>},
      "shots": [<per-shot provenance, incl. resolved angle + movement>],
      "meta": {"emitter": ..., "snapshot_hash": ..., "world_notes": [...]}
    }

``world`` is the only part ``World25D`` reads; ``shots`` / ``meta``
are provenance for the pipeline and the Motion Canvas project.
``example_spec.json`` omits ``scene`` / ``start_sec`` / ``end_sec`` /
``shots`` / ``meta`` and still validates: all of them are optional.

Camera geometry mirrors ``camera_planner.viewpoint_for_shot`` (the
executed F9 geometry): the same viewpoint sphere radius, the same
elevations per angle, the same over-the-shoulder / reverse-shot
azimuths, the same establishing wide radius, the same 46 deg FOV.
The mirror is numeric (this module must stay stdlib-only and cannot
import the PIL-dependent planner); a sync test compares the two.
ONE deliberate difference: in the 2D path every non-establishing
shot shares one radius (the F2 no-head-pump rule, because framing
there is a crop on top of the render). In a pure 3D render the
camera distance IS the framing, so close-up / reaction /
object-insert / extreme-close-up shots use shorter radii -- a real
close-up is a closer camera, not a crop. FOV never varies, so no
shot is ever a zoom.
"""
from __future__ import annotations

import math
import re

from .trait_derivation import CAMERA_ANGLES, DEFAULT_ANGLE_BY_SHOT

SPEC_VERSION = 1
EMITTER_NAME = "motioncanvas_spec v1"

# Frame contract shared with the pipeline snapshot (16:9, 24 fps).
FPS = 24
FOV_DEG = 46.0

# --- Viewpoint geometry (mirror of camera_planner; see module doc) --
_VIEWPOINT_RADIUS = math.sqrt(0.8 * 0.8 + 4.8 * 4.8)
_BASE_ELEV_DEG = math.degrees(math.atan2(0.8, 4.8))
_ANGLE_ELEV_DEG = {
    "eye_level": _BASE_ELEV_DEG,
    "low_angle": -8.0,
    "high_angle": 32.0,
    "birds_eye": 62.0,
    "dutch": _BASE_ELEV_DEG,
    "over_shoulder": _BASE_ELEV_DEG,
}
_OTS_AZIMUTH_DEG = 28.0
_SRS_AZIMUTH_DEG = 18.0
_ESTABLISHING_RADIUS = 7.5

# 3D framing radii per shot type (the deliberate difference from the
# 2D path documented above). Unknown types fall back to the standard
# radius, never to a crash.
_RADIUS_BY_SHOT = {
    "establishing": _ESTABLISHING_RADIUS,
    "medium": _VIEWPOINT_RADIUS,
    "close_up": 2.9,
    "extreme_close_up": 1.9,
    "over_the_shoulder": _VIEWPOINT_RADIUS,
    "reaction": 2.9,
    "object_insert": 2.2,
    "tracking": _VIEWPOINT_RADIUS,
    "shot_reverse_shot": _VIEWPOINT_RADIUS,
    "medium_close_up": 3.6,
    "graphic_insert": _VIEWPOINT_RADIUS,
}

# Establishing shots default to eye level at the wide radius (mirror
# of camera_planner._VIEWPOINT_ANGLE_BY_SHOT: a high angle looks at
# the ground, it does not establish a place). An explicit angle
# always wins.
_VIEWPOINT_ANGLE_BY_SHOT = {"establishing": "eye_level"}

# Target heights, as a fraction of the subject height, per shot type.
# Close framings target the face; object inserts target hand/object
# height; everything else targets the chest (legacy target height).
_TARGET_FRACTION_BY_SHOT = {
    "close_up": 0.88,
    "extreme_close_up": 0.90,
    "reaction": 0.88,
}
_OBJECT_TARGET_Y = 0.8
_DEFAULT_TARGET_Y = 1.2

# --- World layout -----------------------------------------------------
GROUND_SIZE = 30.0
GROUND_ROUGHNESS = 0.85
MAX_BOXES_PER_LAYER = 8
MAX_BOXES_TOTAL = 24

# Depth bands per layer (z: +z towards the default camera, -z into
# the scene). Characters stage on the z=0 plane; foreground boxes
# stay at the frame edges (|x| >= 2.2) so they never cover a
# character, midground boxes stay behind the staging plane.
_LAYER_Z = {
    "foreground": (1.5, 3.0),
    "midground": (-6.0, -3.5),
    "background": (-14.0, -8.0),
}
_LAYER_SIZE = {
    # (width range, height range, depth) in world units.
    "foreground": ((0.5, 1.2), (0.4, 1.0), 0.5),
    "midground": ((1.5, 3.0), (1.0, 2.5), 1.0),
    "background": ((2.5, 4.5), (3.0, 8.0), 1.5),
}
# Deterministic x slots per layer, cycled by feature index. No
# randomness: the same input always builds the same world.
_LAYER_X_SLOTS = {
    "foreground": (-3.4, 3.4, -2.4, 2.4, -4.4, 4.4),
    "midground": (-4.5, -0.5, 4.8, -2.5, 2.5, -5.5, 0.5, 5.5),
    "background": (-4.5, -0.5, 4.8, -2.5, 2.5, -5.5, 0.5, 5.5),
}
# Fallback box colours per layer when the script supplies no usable
# palette (muted, generic; the palette always wins when present).
_LAYER_COLORS = {
    "foreground": ("#4a4038", "#5a4a38", "#3a3a42"),
    "midground": ("#6b5a48", "#5a6a7a", "#7a6a55"),
    "background": ("#4a5a76", "#42506a", "#505e78"),
}

# Lighting presets keyed by (time_of_day, mood) only. The night/cold
# preset mirrors example_spec.json; the others follow the same
# structure (key light + hemisphere fill) with day/night-appropriate
# values. No other location data influences the lights.
#
# ENERGY GLOW (3D path -- NOT YET EMITTED): the 2D renderer paints
# energy_glow halos directly (lighting.paint_energy_glow, fed by
# PropStateMachine.energy_glow_at). The 3D path has no correct slot
# for them yet: World25D's point_lights live in the per-scene world
# spec (static for the whole scene), while an energy record is
# per-(prop, time) -- held only during part of a scene, with an
# intensity ramp and holder changes. Emitting a static scene-level
# light would shine in shots where the prop is not held. When the
# World25D contract gains time-varying (per-shot or keyframed)
# lights, the conversion is lighting.pixel_glow_to_world_glow with:
#   * camera = the shot's emitted camera (position/target/fov),
#   * frame_size = the full render frame (1920x1080),
#   * plane_depth = the staging-plane depth for the holder
#     (camera.depth_of(holder_ground_world_position)),
#   * the record's position translated by the shot crop offset
#     FIRST when the 2D position was measured on a cropped still
#     (energy_glow_at positions are full-canvas, so the offset is
#     (0, 0) for records taken straight from the state machine).
# A bridge round-trip test (real PSM record -> world record ->
# PointLight) lives in test_energy_glow_wiring.py; it proves the
# conversion, not an emitted light.
_LIGHTING_PRESETS = {
    ("day", "warm"): {
        "sky_top": "#6fa8dc", "sky_bottom": "#cfe5f5",
        "ground_color": "#8a7a5e",
        "key_light": {"color": "#fff2d0", "intensity": 2.2,
                      "position": [6.0, 10.0, 8.0], "target": [0.0, 0.0, -4.0]},
        "ambient_sky": "#bcd6f0", "ambient_ground": "#6a5a44",
        "ambient_intensity": 0.7,
    },
    ("day", "cold"): {
        "sky_top": "#8fa5bd", "sky_bottom": "#d5dde4",
        "ground_color": "#7a7a72",
        "key_light": {"color": "#e8eef5", "intensity": 1.8,
                      "position": [6.0, 10.0, 8.0], "target": [0.0, 0.0, -4.0]},
        "ambient_sky": "#aebfd0", "ambient_ground": "#5a5a52",
        "ambient_intensity": 0.75,
    },
    ("night", "warm"): {
        "sky_top": "#1a2340", "sky_bottom": "#4a5570",
        "ground_color": "#3a342c",
        "key_light": {"color": "#ffcf90", "intensity": 1.4,
                      "position": [6.0, 10.0, 8.0], "target": [0.0, 0.0, -4.0]},
        "ambient_sky": "#4a5a7a", "ambient_ground": "#2a241c",
        "ambient_intensity": 0.5,
    },
    ("night", "cold"): {
        "sky_top": "#0e1a33", "sky_bottom": "#3a5478",
        "ground_color": "#2a2a30",
        "key_light": {"color": "#ffd9a0", "intensity": 1.6,
                      "position": [6.0, 10.0, 8.0], "target": [0.0, 0.0, -4.0]},
        "ambient_sky": "#5a7396", "ambient_ground": "#2a2620",
        "ambient_intensity": 0.55,
    },
}
# Night point lights (warm lamp pools, deterministic positions).
_NIGHT_POINT_LIGHTS = [
    {"position": [-2.0, 3.0, -2.0], "color": "#ffbf69",
     "intensity": 12.0, "distance": 14.0},
    {"position": [3.5, 2.8, -4.0], "color": "#ffbf69",
     "intensity": 8.0, "distance": 12.0},
]

# Character staging: world height for the reference height_px, and
# the child-template scale. The reference height (1.7 world units
# at 540 px) matches renderer25d.CharacterAnchor's default.
_REFERENCE_HEIGHT_PX = 540.0
_REFERENCE_WORLD_HEIGHT = 1.7
_CHILD_HEIGHT_SCALE = 0.7
_STAGING_SPACING = 1.6

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_FEATURE_SPLIT_RE = re.compile(r"[,;•\n/]+")
_DURATION_TOLERANCE_SEC = 0.6


class MotionCanvasSpecError(ValueError):
    """Raised when a spec cannot be emitted from the given inputs."""


# ----------------------------------------------------------------------
# Small generic helpers
# ----------------------------------------------------------------------

def _is_hex_color(value) -> bool:
    return isinstance(value, str) and bool(_HEX_COLOR_RE.match(value.strip()))


def _valid_palette(palette) -> list[str]:
    """Palette entries that are usable hex colours, in script order.
    Non-hex entries are ignored (a palette word is not a colour)."""
    if not isinstance(palette, (list, tuple)):
        return []
    out = []
    for entry in palette:
        if _is_hex_color(entry):
            out.append(str(entry).strip().lower())
    return out


def _split_features(text) -> list[str]:
    """Split a free-text layer description into feature phrases.

    Splitting is punctuation-only (commas, semicolons, bullets,
    newlines, slashes). No word is ever interpreted: every phrase
    becomes one box, whatever it says."""
    if isinstance(text, (list, tuple)):
        parts = []
        for item in text:
            parts.extend(_split_features(item))
        return parts
    if not isinstance(text, str):
        return []
    return [p.strip() for p in _FEATURE_SPLIT_RE.split(text) if p.strip()]


def _spherical_offset(azimuth_deg: float, elevation_deg: float,
                      radius: float) -> tuple[float, float, float]:
    """Camera offset from target at (azimuth, elevation) on the sphere.

    Mirror of camera_planner._spherical_offset: azimuth 0 is directly
    in front of the target (+z); positive azimuth moves the camera
    towards +x."""
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    return (radius * math.cos(el) * math.sin(az),
            radius * math.sin(el),
            radius * math.cos(el) * math.cos(az))


def resolve_viewpoint_angle(shot_type: str, camera_angle=None) -> str:
    """The executed angle for a shot (mirror of
    camera_planner.resolve_viewpoint_angle): an explicit valid angle
    wins, else the viewpoint default for the shot type, else the
    per-type default, else eye_level. Never raises."""
    if isinstance(camera_angle, str):
        angle = camera_angle.strip().lower().replace("-", "_")
        if angle in CAMERA_ANGLES:
            return angle
    shot_type = str(shot_type or "")
    return _VIEWPOINT_ANGLE_BY_SHOT.get(
        shot_type, DEFAULT_ANGLE_BY_SHOT.get(shot_type, "eye_level"))


def normalize_movement(value) -> str:
    """Normalise a camera-movement label to the CAMERA_MOVEMENT enum
    spelling. Unknown values degrade to STATIC; the label is recorded
    in shot provenance either way, and no movement value ever
    produces within-shot camera motion (fixed camera per shot)."""
    if value is None:
        return "STATIC"
    norm = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    if norm in ("STATIC", "PAN_LEFT", "PAN_RIGHT", "TILT_UP", "TILT_DOWN",
                "DOLLY_IN", "DOLLY_OUT", "TRACKING", "CRANE_UP",
                "CRANE_DOWN", "HANDHELD"):
        return norm
    return "STATIC"


# ----------------------------------------------------------------------
# World building (location data -> ground / boxes / lights)
# ----------------------------------------------------------------------

def _layer_boxes(layer: str, phrases: list[str],
                 palette: list[str]) -> list[dict]:
    """One deterministic box per feature phrase in a depth layer."""
    boxes = []
    z_lo, z_hi = _LAYER_Z[layer]
    (w_lo, w_hi), (h_lo, h_hi), depth = _LAYER_SIZE[layer]
    slots = _LAYER_X_SLOTS[layer]
    colors = _LAYER_COLORS[layer]
    for i, _phrase in enumerate(phrases[:MAX_BOXES_PER_LAYER]):
        # Deterministic variation from the index only (no randomness,
        # no phrase content): sizes and depths cycle through the
        # layer's ranges so repeated features do not stack.
        frac = (i % 4) / 3.0
        width = w_lo + (w_hi - w_lo) * frac
        height = h_lo + (h_hi - h_lo) * ((i * 2 % 4) / 3.0)
        z = z_lo + (z_hi - z_lo) * ((i % 3) / 2.0)
        color = palette[i % len(palette)] if palette else colors[i % len(colors)]
        boxes.append({
            "name": f"{layer[:2]}_{i}",
            "center": [round(slots[i % len(slots)], 2),
                       round(height / 2.0, 3), round(z, 2)],
            "size": [round(width, 2), round(height, 2), depth],
            "color": color,
            "roughness": 0.8,
        })
    return boxes


def _default_boxes(palette: list[str]) -> list[dict]:
    """Minimal world for a scene with no feature data at all: three
    background masses and one midground block, so the world is never
    empty. Deterministic; flagged in the spec's world_notes."""
    colors = _LAYER_COLORS["background"]
    boxes = []
    for i, x in enumerate((-4.5, -0.5, 4.8)):
        color = palette[i % len(palette)] if palette else colors[i % len(colors)]
        boxes.append({
            "name": f"bg_{i}", "center": [x, 2.0, -12.0],
            "size": [3.2, 4.0, 1.5], "color": color, "roughness": 0.8,
        })
    boxes.append({
        "name": "mg_0", "center": [2.6, 0.22, -4.0],
        "size": [1.9, 0.45, 0.6],
        "color": palette[0] if palette else _LAYER_COLORS["midground"][0],
        "roughness": 0.8,
    })
    return boxes


def _rgb_to_hex(rgb) -> str | None:
    """RGB tuple/list (0-255) -> "#rrggbb". None when unusable."""
    try:
        r, g, b = (max(0, min(255, int(round(float(c))))) for c in rgb[:3])
    except (TypeError, ValueError, IndexError):
        return None
    return f"#{r:02x}{g:02x}{b:02x}"


def _env_boxes(pkg: dict) -> tuple[list[dict], list[str]]:
    """EnvironmentPackage elements -> World25D BoxSpecs.

    Box-geometry elements map 1:1. Gable prisms have no prism mesh in
    World25D.ts (boxes only), so they are emitted as boxes with the
    approximation recorded on the box and in the notes — massing is
    preserved, the roof profile is not. Any other geometry is skipped
    and counted, never silently dropped. Extra keys (kind/layer/
    material/geometry) are annotations the validator ignores.
    """
    boxes: list[dict] = []
    notes: list[str] = []
    approximated = 0
    skipped: list[str] = []
    for el in pkg.get("elements", []):
        if not isinstance(el, dict):
            continue
        color = _rgb_to_hex(el.get("color"))
        if color is None:
            skipped.append(str(el.get("id", "?")))
            continue
        try:
            center = [float(c) for c in el["center"]]
            size = [float(c) for c in el["size"]]
        except (KeyError, TypeError, ValueError):
            skipped.append(str(el.get("id", "?")))
            continue
        if len(center) != 3 or len(size) != 3:
            skipped.append(str(el.get("id", "?")))
            continue
        geometry = str(el.get("geometry") or "box")
        box = {
            "name": str(el.get("id") or "element"),
            "center": center, "size": size, "color": color,
            "roughness": 0.8,
            "kind": str(el.get("kind") or ""),
            "layer": str(el.get("layer") or ""),
            "material": str(el.get("material") or ""),
        }
        if geometry == "box":
            box["geometry"] = "box"
        elif geometry == "gable_prism":
            box["geometry"] = "gable_prism_approximated_as_box"
            approximated += 1
        else:
            skipped.append(str(el.get("id", "?")))
            continue
        boxes.append(box)
    if approximated:
        notes.append(f"{approximated} gable-prism element(s) emitted "
                     f"as boxes (World25D has no prism mesh)")
    if skipped:
        notes.append(f"{len(skipped)} element(s) skipped (unsupported "
                     f"geometry or unusable colour): "
                     + ", ".join(skipped[:8]))
    return boxes, notes


def build_world(location: dict | None, v1_location: dict | None,
                character_anchors: list[dict]) -> tuple[dict, list[str]]:
    """Build a World25DSpec ``world`` dict from generic location data.

    ``location`` is the package scene's ``location`` dict
    (location_keyword / setting / mood / time_of_day); ``v1_location``
    is the section 15.3 trait block (features / foreground /
    midground / background / palette). Either may be None/empty: the
    day/warm preset + default boxes apply. Returns (world, notes).
    The world dict has no camera yet: the caller fills
    ``camera_initial`` / ``camera_keyframes`` from the shot plan.
    """
    location = location if isinstance(location, dict) else {}
    v1_location = v1_location if isinstance(v1_location, dict) else {}
    time_of_day = str(location.get("time_of_day") or "day").strip().lower()
    if time_of_day not in ("day", "night"):
        time_of_day = "day"
    mood = str(location.get("mood") or "warm").strip().lower()
    if mood not in ("warm", "cold"):
        mood = "warm"
    preset = _LIGHTING_PRESETS[(time_of_day, mood)]
    palette = _valid_palette(v1_location.get("palette"))

    # W6 (visual recovery): when the scene carries a §15.3 trait
    # block, stage the SAME EnvironmentPackage the 2D renderer builds
    # from it (same deterministic inputs: traits + time_of_day +
    # mood), so the 3D world and the 2D render stage the same
    # environment. The phrase-box path below remains the fallback
    # when there is no trait block, the location is map-type, or the
    # environment build fails — every fallback is noted, never
    # silent. Camera poses stay PLANNED (stage 7b runs before the
    # render); they mirror viewpoint_for_shot, the geometry the 2D
    # renderer executes, but "executed" poses do not exist yet.
    env_pkg: dict | None = None
    env_notes: list[str] = []
    if v1_location:
        try:
            from .environment_v2 import build_environment
            env_pkg = build_environment(
                v1_location,
                period=str(v1_location.get("period")
                           or location.get("period") or ""),
                time_of_day=time_of_day, style={"mood": mood})
        except Exception as exc:  # noqa: BLE001 - fallback is noted
            env_notes.append(f"environment build failed ({exc}); "
                             f"phrase staging used")
            env_pkg = None
        if env_pkg is not None and env_pkg.get("kind") == "map_deferred":
            env_notes.append("map location; Motion Canvas world uses "
                             "phrase staging (maps render via "
                             "map_renderer in the 2D path)")
            env_pkg = None

    phrases = {
        "foreground": _split_features(v1_location.get("foreground")),
        "midground": _split_features(v1_location.get("midground")),
        "background": _split_features(v1_location.get("background")),
    }
    # The free feature list stages in the midground band.
    phrases["midground"].extend(_split_features(v1_location.get("features")))
    notes = list(env_notes)
    boxes: list[dict] = []
    env_light: dict = {}
    env_ground: dict = {}
    if env_pkg is not None:
        boxes, box_notes = _env_boxes(env_pkg)
        notes.extend(box_notes)
        prov = env_pkg.get("provenance") or {}
        notes.append(
            f"environment archetype {env_pkg.get('archetype')} "
            f"({len(boxes)} boxes from {len(env_pkg.get('elements', []))} "
            f"elements; trait source "
            f"{prov.get('trait_source') or 'anonymous'})")
        if not boxes:
            notes.append("environment package yielded no boxes; "
                         "phrase staging used")
            env_pkg = None
        else:
            env_light = env_pkg.get("light") or {}
            env_ground = env_pkg.get("ground") or {}
            trait_colors = (env_pkg.get("palette") or {}).get("trait_colors")
            if trait_colors:
                notes.append("trait palette tinted the archetype colours "
                             f"({len(trait_colors)} usable colours)")
    if env_pkg is None:
        for layer in ("foreground", "midground", "background"):
            boxes.extend(_layer_boxes(layer, phrases[layer], palette))
        boxes = boxes[:MAX_BOXES_TOTAL]
        if not boxes:
            boxes = _default_boxes(palette)
            notes.append("no feature data for this location; default world used")
        if palette:
            notes.append(f"palette applied ({len(palette)} usable colours)")
    point_lights = [dict(p) for p in _NIGHT_POINT_LIGHTS] \
        if time_of_day == "night" else []

    # Light + ground: the environment package's measured values win
    # when present (same staging as the 2D render); the preset fills
    # anything the package does not supply. The key-light POSITION
    # stays the preset's — the package carries a direction, not a
    # position, and inventing one would change the lighting.
    sky_top = _rgb_to_hex(env_light.get("sky_top")) or preset["sky_top"]
    sky_bottom = (_rgb_to_hex(env_light.get("sky_bottom"))
                  or preset["sky_bottom"])
    ground_color = (_rgb_to_hex(env_ground.get("color"))
                    or _rgb_to_hex(env_light.get("ground"))
                    or preset["ground_color"])
    key_light = dict(preset["key_light"])
    sun_hex = _rgb_to_hex(env_light.get("sun_color"))
    if sun_hex:
        key_light["color"] = sun_hex
    try:
        key_light["intensity"] = float(env_light["key_intensity"])
    except (KeyError, TypeError, ValueError):
        pass
    try:
        ambient_intensity = float(env_light["ambient"])
    except (KeyError, TypeError, ValueError):
        ambient_intensity = preset["ambient_intensity"]
    ambient_sky = (_rgb_to_hex(env_light.get("sky_top"))
                   or preset["ambient_sky"])
    ambient_ground = (_rgb_to_hex(env_light.get("ground"))
                      or preset["ambient_ground"])

    world = {
        "sky_top": sky_top,
        "sky_bottom": sky_bottom,
        "ground_color": ground_color,
        "ground_size": GROUND_SIZE,
        "ground_roughness": GROUND_ROUGHNESS,
        "boxes": boxes,
        "key_light": key_light,
        "ambient_sky": ambient_sky,
        "ambient_ground": ambient_ground,
        "ambient_intensity": ambient_intensity,
        "point_lights": point_lights,
        "camera_initial": {"position": [0.0, 2.4, 12.0],
                           "target": [0.0, 1.5, -2.0], "fov": FOV_DEG},
        "camera_keyframes": [],
        "character_anchors": list(character_anchors),
    }
    if env_pkg is not None:
        world["environment_archetype"] = env_pkg.get("archetype")
        world["environment_provenance"] = env_pkg.get("provenance") or {}
    return world, notes


# ----------------------------------------------------------------------
# Character anchors (scene cast + staging)
# ----------------------------------------------------------------------

def _world_height(cast_entry: dict) -> float:
    """World height from the package's height_px + template."""
    try:
        height_px = float(cast_entry.get("height_px") or _REFERENCE_HEIGHT_PX)
    except (TypeError, ValueError):
        height_px = _REFERENCE_HEIGHT_PX
    if height_px <= 0:
        height_px = _REFERENCE_HEIGHT_PX
    height = _REFERENCE_WORLD_HEIGHT * height_px / _REFERENCE_HEIGHT_PX
    traits = cast_entry.get("render_traits")
    template = cast_entry.get("template")
    if not template and isinstance(traits, dict):
        template = traits.get("template")
    if str(template or "").strip().lower() == "child":
        height *= _CHILD_HEIGHT_SCALE
    return round(height, 3)


def build_character_anchors(scene: dict, cast_by_name: dict,
                            scene_shots: list[dict]) -> list[dict]:
    """Feet positions + heights for the scene's visible characters.

    Characters spread along the staging plane (z=0) in
    ``visible_characters`` order, centred on x=0. A shot-level
    ``staging_override`` (e.g. a boarded character staged at a door)
    moves that character's anchor to the override x when present on
    any shot in the scene (last override wins). Characters with no
    cast entry are skipped, never invented."""
    visible = scene.get("visible_characters") or []
    if not isinstance(visible, (list, tuple)):
        visible = []
    overrides: dict[str, float] = {}
    for shot in scene_shots:
        staging = shot.get("staging_override") if isinstance(shot, dict) else None
        if isinstance(staging, dict):
            for name, x in staging.items():
                try:
                    overrides[str(name)] = float(x)
                except (TypeError, ValueError):
                    continue
    anchors = []
    names = [n for n in visible if str(n) in cast_by_name]
    for i, name in enumerate(names):
        entry = cast_by_name[str(name)]
        anchor_id = entry.get("id") or entry.get("identity_id") or str(name)
        x = overrides.get(str(name))
        if x is None:
            x = (i - (len(names) - 1) / 2.0) * _STAGING_SPACING
        anchors.append({
            "id": str(anchor_id),
            "feet": [round(float(x), 3), 0.0, 0.0],
            "height": _world_height(entry),
        })
    return anchors


# ----------------------------------------------------------------------
# Camera keyframes (shot plan -> real viewpoints, fixed within shots)
# ----------------------------------------------------------------------

def _anchor_lookup(anchors: list[dict], cast_by_name: dict) -> dict[str, dict]:
    """Map every usable character key (anchor id, cast name, cast id,
    identity id) to its anchor dict."""
    lookup: dict[str, dict] = {}
    by_id = {a["id"]: a for a in anchors}
    for anchor in anchors:
        lookup[anchor["id"]] = anchor
    for name, entry in cast_by_name.items():
        anchor_id = str(entry.get("id") or entry.get("identity_id") or name)
        anchor = by_id.get(anchor_id)
        if anchor is not None:
            lookup[str(name)] = anchor
            lookup[anchor_id] = anchor
            identity = entry.get("identity_id")
            if identity:
                lookup[str(identity)] = anchor
    return lookup


def _shot_subject(shot: dict, lookup: dict[str, dict]) -> dict | None:
    """The shot's subject anchor: over-the-shoulder subject, action
    actor, then speaker, in that order. None when the shot has no
    resolvable subject (location-only / end-card shots)."""
    for key in ("ots_subject", "directive_subject", "actor", "speaker"):
        candidate = shot.get(key)
        if candidate and str(candidate) in lookup:
            return lookup[str(candidate)]
    return None


def camera_pose_for_shot(shot: dict, anchors: list[dict],
                         cast_by_name: dict) -> dict:
    """One shot's REAL viewpoint: position + target + constant FOV.

    The camera sits on the viewpoint sphere around the subject (or
    the frame centre for subject-less shots). Shot type sets the
    radius and target height, the resolved angle sets elevation and
    azimuth, over-the-shoulder shots sit on the counterpart's side,
    reverse shots alternate azimuth by ``srs_side``. The returned
    pose is a plain dict (position / target / fov) ready for a
    keyframe."""
    shot_type = str(shot.get("shot_type") or "medium")
    angle = resolve_viewpoint_angle(shot_type, shot.get("camera_angle"))
    lookup = _anchor_lookup(anchors, cast_by_name)
    subject = _shot_subject(shot, lookup)
    if subject is not None:
        subject_x = float(subject["feet"][0])
        subject_z = float(subject["feet"][2])
        subject_height = float(subject["height"])
    else:
        subject_x, subject_z, subject_height = 0.0, 0.0, _REFERENCE_WORLD_HEIGHT
    if shot_type in _TARGET_FRACTION_BY_SHOT:
        target_y = subject_height * _TARGET_FRACTION_BY_SHOT[shot_type]
    elif shot_type == "object_insert":
        target_y = _OBJECT_TARGET_Y
    else:
        target_y = _DEFAULT_TARGET_Y
    target = [round(subject_x, 3), round(target_y, 3), round(subject_z, 3)]

    radius = _RADIUS_BY_SHOT.get(shot_type, _VIEWPOINT_RADIUS)
    elevation = _ANGLE_ELEV_DEG.get(angle, _BASE_ELEV_DEG)
    azimuth = 0.0
    if angle == "over_shoulder" or shot_type == "over_the_shoulder":
        counterpart = shot.get("ots_counterpart") or shot.get("counterpart")
        counterpart_anchor = lookup.get(str(counterpart)) \
            if counterpart else None
        if counterpart_anchor is not None:
            side = 1.0 if float(counterpart_anchor["feet"][0]) >= subject_x else -1.0
        else:
            side = 1.0
        azimuth = side * _OTS_AZIMUTH_DEG
    elif shot_type == "shot_reverse_shot":
        try:
            srs_side = int(shot.get("srs_side") or 0)
        except (TypeError, ValueError):
            srs_side = 0
        azimuth = _SRS_AZIMUTH_DEG if srs_side else -_SRS_AZIMUTH_DEG
    offset = _spherical_offset(azimuth, elevation, radius)
    position = [round(target[0] + offset[0], 3),
                round(target[1] + offset[1], 3),
                round(target[2] + offset[2], 3)]
    return {"position": position, "target": target, "fov": FOV_DEG}


def build_camera_keyframes(shots: list[dict], anchors: list[dict],
                           cast_by_name: dict) -> tuple[list[dict], list[dict], float]:
    """Shot plan -> (keyframes, shot provenance, scene duration).

    Each shot contributes TWO keyframes with the IDENTICAL pose: one
    at the shot start (``cut: true`` except for the first shot, so
    the camera jumps at the boundary and never interpolates across
    it) and one at the shot end. The camera is therefore fixed
    within every shot. Shot start times accumulate the shot
    durations in plan order; the scene duration is their sum.
    Raises MotionCanvasSpecError on a missing/non-positive duration.
    """
    keyframes: list[dict] = []
    provenance: list[dict] = []
    cursor = 0.0
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            raise MotionCanvasSpecError(f"shot {index} is not a dict")
        try:
            duration = float(shot.get("duration"))
        except (TypeError, ValueError):
            raise MotionCanvasSpecError(
                f"shot {index} (scene {shot.get('scene')}) has no "
                "numeric duration; durations must come from the "
                "measured shot plan") from None
        if duration <= 0:
            raise MotionCanvasSpecError(
                f"shot {index} (scene {shot.get('scene')}) has "
                f"non-positive duration {duration}")
        start = round(cursor, 3)
        end = round(cursor + duration, 3)
        pose = camera_pose_for_shot(shot, anchors, cast_by_name)
        shot_type = str(shot.get("shot_type") or "medium")
        keyframes.append({
            "t": start, "position": list(pose["position"]),
            "target": list(pose["target"]), "fov": pose["fov"],
            "cut": index > 0,
        })
        keyframes.append({
            "t": end, "position": list(pose["position"]),
            "target": list(pose["target"]), "fov": pose["fov"],
            "cut": False,
        })
        subject = _shot_subject(shot, _anchor_lookup(anchors, cast_by_name))
        provenance.append({
            "shot_id": shot.get("directive_shot_id") or shot.get("shot_id"),
            "scene": shot.get("scene"),
            "kind": shot.get("kind"),
            "shot_type": shot_type,
            "camera_angle": resolve_viewpoint_angle(
                shot_type, shot.get("camera_angle")),
            "camera_movement": normalize_movement(
                shot.get("camera_movement")),
            "start_sec": start,
            "end_sec": end,
            "duration": round(duration, 3),
            "subject": subject["id"] if subject is not None else None,
        })
        cursor += duration
    return keyframes, provenance, round(cursor, 3)


# ----------------------------------------------------------------------
# Validation (the emitter self-checks; render tooling can reuse these)
# ----------------------------------------------------------------------

def _vec3_errors(value, path: str, errors: list[str]) -> None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        errors.append(f"{path}: expected a 3-number vector, got {value!r}")
        return
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            errors.append(f"{path}: non-numeric component {component!r}")
            return


def validate_world_spec(world) -> list[str]:
    """Validate a World25DSpec ``world`` dict. Returns error strings
    (empty = valid). Checks every required key, vector shapes, hex
    colours, and keyframe time ordering. Unknown extra keys are
    ignored: the world is data, and tooling may annotate it."""
    errors: list[str] = []
    if not isinstance(world, dict):
        return ["world: expected a dict"]
    for key in ("sky_top", "sky_bottom", "ground_color", "ground_size",
                "boxes", "key_light", "ambient_sky", "ambient_ground",
                "ambient_intensity", "camera_initial"):
        if key not in world:
            errors.append(f"world.{key}: missing required key")
    for key in ("sky_top", "sky_bottom", "ground_color",
                "ambient_sky", "ambient_ground"):
        if key in world and not _is_hex_color(world[key]):
            errors.append(f"world.{key}: expected a hex colour, got {world[key]!r}")
    if "ground_size" in world:
        size = world["ground_size"]
        if isinstance(size, bool) or not isinstance(size, (int, float)) or size <= 0:
            errors.append(f"world.ground_size: expected a positive number, got {size!r}")
    boxes = world.get("boxes")
    if isinstance(boxes, list):
        for i, box in enumerate(boxes):
            if not isinstance(box, dict):
                errors.append(f"world.boxes[{i}]: expected a dict")
                continue
            for key in ("name", "center", "size", "color"):
                if key not in box:
                    errors.append(f"world.boxes[{i}].{key}: missing required key")
            _vec3_errors(box.get("center"), f"world.boxes[{i}].center", errors)
            _vec3_errors(box.get("size"), f"world.boxes[{i}].size", errors)
            if "color" in box and not _is_hex_color(box["color"]):
                errors.append(f"world.boxes[{i}].color: expected a hex colour, "
                              f"got {box['color']!r}")
    elif "boxes" in world:
        errors.append("world.boxes: expected a list")
    key_light = world.get("key_light")
    if isinstance(key_light, dict):
        if not _is_hex_color(key_light.get("color")):
            errors.append(f"world.key_light.color: expected a hex colour, "
                          f"got {key_light.get('color')!r}")
        if "intensity" in key_light:
            intensity = key_light["intensity"]
            if isinstance(intensity, bool) or not isinstance(intensity, (int, float)):
                errors.append("world.key_light.intensity: expected a number, "
                              f"got {intensity!r}")
        _vec3_errors(key_light.get("position"), "world.key_light.position", errors)
        if "target" in key_light:
            _vec3_errors(key_light["target"], "world.key_light.target", errors)
    elif "key_light" in world:
        errors.append("world.key_light: expected a dict")
    if "ambient_intensity" in world:
        intensity = world["ambient_intensity"]
        if isinstance(intensity, bool) or not isinstance(intensity, (int, float)):
            errors.append("world.ambient_intensity: expected a number, "
                          f"got {intensity!r}")
    for light in world.get("point_lights") or []:
        if not isinstance(light, dict):
            errors.append("world.point_lights: expected a list of dicts")
            break
        _vec3_errors(light.get("position"), "world.point_lights.position", errors)
        if not _is_hex_color(light.get("color")):
            errors.append(f"world.point_lights.color: expected a hex colour, "
                          f"got {light.get('color')!r}")
    camera_initial = world.get("camera_initial")
    if isinstance(camera_initial, dict):
        _vec3_errors(camera_initial.get("position"),
                     "world.camera_initial.position", errors)
        _vec3_errors(camera_initial.get("target"),
                     "world.camera_initial.target", errors)
        fov = camera_initial.get("fov")
        if fov is not None and (
                isinstance(fov, bool) or not isinstance(fov, (int, float))
                or not 10.0 <= float(fov) <= 120.0):
            errors.append(f"world.camera_initial.fov: expected 10..120, got {fov!r}")
    elif "camera_initial" in world:
        errors.append("world.camera_initial: expected a dict")
    previous_t = None
    for i, keyframe in enumerate(world.get("camera_keyframes") or []):
        if not isinstance(keyframe, dict):
            errors.append(f"world.camera_keyframes[{i}]: expected a dict")
            continue
        _vec3_errors(keyframe.get("position"),
                     f"world.camera_keyframes[{i}].position", errors)
        _vec3_errors(keyframe.get("target"),
                     f"world.camera_keyframes[{i}].target", errors)
        t = keyframe.get("t")
        if isinstance(t, bool) or not isinstance(t, (int, float)):
            errors.append(f"world.camera_keyframes[{i}].t: expected a number, "
                          f"got {t!r}")
        elif previous_t is not None and float(t) < previous_t:
            errors.append(f"world.camera_keyframes[{i}].t: times must be "
                          f"non-decreasing ({previous_t} -> {t})")
        else:
            previous_t = float(t)
    for anchor in world.get("character_anchors") or []:
        if not isinstance(anchor, dict):
            errors.append("world.character_anchors: expected a list of dicts")
            break
        if "id" not in anchor:
            errors.append("world.character_anchors: anchor without an id")
        _vec3_errors(anchor.get("feet"), "world.character_anchors.feet", errors)
        height = anchor.get("height")
        if isinstance(height, bool) or not isinstance(height, (int, float)) \
                or float(height or 0) <= 0:
            errors.append("world.character_anchors.height: expected a "
                          f"positive number, got {height!r}")
    return errors


def validate_spec(spec) -> list[str]:
    """Validate a single-scene spec (the ``example_spec.json`` shape).
    Returns error strings (empty = valid)."""
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["spec: expected a dict"]
    duration = spec.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) \
            or float(duration or 0) <= 0:
        errors.append(f"duration_seconds: expected a positive number, got {duration!r}")
    if "world" not in spec:
        errors.append("world: missing required key")
    else:
        errors.extend(validate_world_spec(spec["world"]))
    return errors


def validate_job_spec(job) -> list[str]:
    """Validate a job envelope from ``emit_job_spec``. Returns error
    strings (empty = valid)."""
    errors: list[str] = []
    if not isinstance(job, dict):
        return ["job spec: expected a dict"]
    if job.get("spec_version") != SPEC_VERSION:
        errors.append(f"spec_version: expected {SPEC_VERSION}, "
                      f"got {job.get('spec_version')!r}")
    duration = job.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) \
            or float(duration or 0) <= 0:
        errors.append(f"duration_seconds: expected a positive number, got {duration!r}")
    scene_specs = job.get("scene_specs")
    if not isinstance(scene_specs, list) or not scene_specs:
        errors.append("scene_specs: expected a non-empty list")
        return errors
    for i, scene_spec in enumerate(scene_specs):
        for error in validate_spec(scene_spec):
            errors.append(f"scene_specs[{i}].{error}")
    return errors


# ----------------------------------------------------------------------
# Emitters
# ----------------------------------------------------------------------

def _cast_by_name(package: dict) -> dict[str, dict]:
    cast: dict[str, dict] = {}
    for entry in package.get("characters") or []:
        if isinstance(entry, dict) and entry.get("name"):
            cast[str(entry["name"])] = entry
    return cast


def _find_scene(package: dict, scene_number) -> dict | None:
    for scene in package.get("scenes") or []:
        if isinstance(scene, dict) and scene.get("number") == scene_number:
            return scene
    return None


def emit_scene_spec(package: dict, scene_number, shots: list[dict], *,
                    start_sec: float = 0.0,
                    snapshot_hash: str | None = None) -> dict:
    """Emit one scene's Motion Canvas spec from package + shot plan.

    ``shots`` are the plan_shots entries for this scene, in plan
    order, with measured durations. ``start_sec`` is the scene's
    offset in the job timeline (keyframe times stay scene-local).
    The emitted spec is self-validated before return: an invalid
    spec raises MotionCanvasSpecError instead of being returned.
    """
    if not isinstance(package, dict):
        raise MotionCanvasSpecError("package must be a dict")
    scene = _find_scene(package, scene_number)
    if scene is None:
        raise MotionCanvasSpecError(f"no scene {scene_number!r} in the package")
    cast_by_name = _cast_by_name(package)
    scene_shots = [s for s in (shots or []) if isinstance(s, dict)]
    if not scene_shots:
        raise MotionCanvasSpecError(
            f"scene {scene_number} has no shots in the plan; a spec "
            "with no shots would have no duration and no camera")
    anchors = build_character_anchors(scene, cast_by_name, scene_shots)
    location = scene.get("location") if isinstance(scene, dict) else None
    v1_location = None
    if isinstance(location, dict):
        v1_location = location.get("v1_location")
    # The scene location's trait copy drops fields the shot blocks
    # carry (notably `type`, which MAP detection needs), so merge the
    # first shot block for the SAME location over it — the emitter
    # then consumes the same trait data the 2D renderer uses for
    # that location. Shots staging a DIFFERENT location (a per-shot
    # override) cannot be represented in one scene world; they are
    # noted, never silently absorbed.
    override_notes: list[str] = []
    scene_loc_id = (v1_location or {}).get("location_id") \
        if isinstance(v1_location, dict) else None
    for _shot in scene_shots:
        _sv1 = _shot.get("v1_location")
        if not isinstance(_sv1, dict) or not _sv1:
            continue
        _shot_loc_id = _sv1.get("location_id")
        if scene_loc_id is None or _shot_loc_id == scene_loc_id:
            merged = dict(v1_location) if isinstance(v1_location, dict) else {}
            merged.update(_sv1)
            v1_location = merged
            scene_loc_id = _shot_loc_id
            break
    for _shot in scene_shots:
        _sv1 = _shot.get("v1_location")
        if isinstance(_sv1, dict) and _sv1.get("location_id") \
                and _sv1.get("location_id") != scene_loc_id:
            override_notes.append(
                f"shot {_shot.get('shot_id') or _shot.get('index')} "
                f"stages location {_sv1.get('location_id')} (override); "
                f"the scene world uses {scene_loc_id}")
            break
    world, notes = build_world(location, v1_location, anchors)
    notes.extend(override_notes)
    keyframes, provenance, duration = build_camera_keyframes(
        scene_shots, anchors, cast_by_name)
    first = keyframes[0]
    world["camera_initial"] = {
        "position": list(first["position"]),
        "target": list(first["target"]), "fov": first["fov"],
    }
    world["camera_keyframes"] = keyframes
    spec = {
        "scene": scene_number,
        "start_sec": round(float(start_sec), 3),
        "end_sec": round(float(start_sec) + duration, 3),
        "duration_seconds": duration,
        "world": world,
        "shots": provenance,
        "meta": {
            "emitter": EMITTER_NAME,
            "snapshot_hash": snapshot_hash or package.get("v1_snapshot_hash") or "",
            "location": {
                "setting": (location or {}).get("setting", "")
                if isinstance(location, dict) else "",
                "time_of_day": (location or {}).get("time_of_day", "")
                if isinstance(location, dict) else "",
                "mood": (location or {}).get("mood", "")
                if isinstance(location, dict) else "",
            },
            "world_notes": notes,
        },
    }
    errors = validate_spec(spec)
    if errors:
        raise MotionCanvasSpecError(
            f"emitted scene {scene_number} spec failed validation: "
            + "; ".join(errors))
    return spec


def emit_job_spec(package: dict, shots: list[dict],
                  total_duration_sec: float, *,
                  snapshot_hash: str | None = None) -> dict:
    """Emit the whole job's Motion Canvas specs (one per scene).

    ``shots`` is the full plan_shots list (all scenes, plan order);
    ``total_duration_sec`` is the measured timeline total, carried
    for the cross-check note only. The job duration is the SUM of
    the shot-plan durations (the render clock); when it differs
    from the timeline total by more than the 0.6 s gate tolerance,
    the difference is recorded in ``meta.notes`` -- never silently
    rescaled, never a failure here (timeline QA owns that gate).
    Scenes with no shots get no spec and are noted. Raises
    MotionCanvasSpecError when the package has no scenes or no shot
    carries a usable duration.
    """
    if not isinstance(package, dict):
        raise MotionCanvasSpecError("package must be a dict")
    scenes = [s for s in (package.get("scenes") or []) if isinstance(s, dict)]
    if not scenes:
        raise MotionCanvasSpecError("package has no scenes")
    shots = [s for s in (shots or []) if isinstance(s, dict)]
    by_scene: dict = {}
    for shot in shots:
        by_scene.setdefault(shot.get("scene"), []).append(shot)
    scene_specs: list[dict] = []
    notes: list[str] = []
    cursor = 0.0
    for scene in scenes:
        number = scene.get("number")
        scene_shots = by_scene.get(number, [])
        if not scene_shots:
            notes.append(f"scene {number}: no shots in the plan; no spec emitted")
            continue
        spec = emit_scene_spec(
            package, number, scene_shots, start_sec=cursor,
            snapshot_hash=snapshot_hash)
        scene_specs.append(spec)
        cursor = spec["end_sec"]
    if not scene_specs:
        raise MotionCanvasSpecError("no scene in the package has any shots")
    job_duration = round(cursor, 3)
    try:
        timeline_total = float(total_duration_sec)
    except (TypeError, ValueError):
        timeline_total = 0.0
    delta = round(job_duration - timeline_total, 3)
    if abs(delta) > _DURATION_TOLERANCE_SEC:
        notes.append(
            f"shot-plan duration {job_duration}s differs from the "
            f"measured timeline total {timeline_total}s by {delta}s "
            "(tolerance 0.6s); spec durations follow the shot plan")
    job = {
        "spec_version": SPEC_VERSION,
        "duration_seconds": job_duration,
        "timeline_total_sec": timeline_total,
        "fps": FPS,
        "snapshot_hash": snapshot_hash or package.get("v1_snapshot_hash") or "",
        "scene_specs": scene_specs,
        "meta": {"emitter": EMITTER_NAME, "notes": notes},
    }
    errors = validate_job_spec(job)
    if errors:
        raise MotionCanvasSpecError(
            "emitted job spec failed validation: " + "; ".join(errors))
    return job
