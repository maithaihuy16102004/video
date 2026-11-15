"""Event-driven light effects (round-2 system 5).

Pure functions: given a semantic event and a time, how bright is the
payoff, where does it paint, and what does a crack look like. The
renderer consumes these; nothing here draws.

The burst is keyed on the EVENT, not on the held state: a CRACK
bursts at the crack moment and leaks light afterwards, an ACTIVATE
ramps up and sustains, an EMIT pulses and holds warm. The held-prop
ramp (``PropStateMachine.energy_glow_at``) cannot mark a payoff
moment -- it starts when the prop is first grasped -- so payoff
moments need their own envelope.
"""

import math
import random
import zlib

# Semantic action types that drive a light burst on their prop.
BURST_TYPES = frozenset({"CRACK", "ACTIVATE", "EMIT"})

# Fallback burst colour/radius when the prop carries no energy spec
# (only the bolt's halo carries one today): forge gold, matching the
# anvil sparks. An explicit energy spec always wins.
DEFAULT_BURST_COLOR = (255, 200, 90)
DEFAULT_BURST_RADIUS_PX = 240.0

# A set-piece reaction paints at the furnace mouth / spark field.
REACTION_GLOW_COLOR = (255, 160, 60)
REACTION_GLOW_RADIUS_PX = 220.0

# How fast a hammer-strike spark pulse decays after contact.
# Round-7 (R6-D3): 0.35 s left the reaction at 0.50 six frames
# after contact, so sparks burst at the anvil while the hammer
# head was already up-left of it. Sparks are gated to contact
# frames: 0.10 s puts the visible pulse at ~4 frames (reaction
# 1.0 at contact, 0.44 at 2 frames, 0.19 at 4 frames).
STRIKE_DECAY_SEC = 0.10

# Below this reaction level the overlay paints nothing: the
# exponential strike decay never reaches exactly zero, and without
# a floor every frame after the first strike would count as a
# (invisible) reaction frame. Round-7 (R6-D3): 0.02 kept sparks
# painting for ~1.4 s after contact; 0.15 closes the visible
# window at ~0.19 s (4-5 frames), so a spark burst reads as
# contact + fade, never as a fresh burst with the hammer up.
REACTION_PAINT_FLOOR = 0.15


def _smoothstep(u):
    u = min(1.0, max(0.0, float(u)))
    return u * u * (3.0 - 2.0 * u)


def burst_envelope(action_type, u):
    """Payoff intensity (0..1) at event progress ``u`` (0..1).

    CRACK: silent until the crack moment (u=0.6), a sharp rise to
    full, then a decay to a 0.55 sustain -- light leaking from the
    cracks. ACTIVATE: a smooth power-up ramp (u=0.25..0.8), then
    full sustain. EMIT: a pulse that rises, peaks mid-event, and
    eases to a 0.6 warm sustain. Unknown types and out-of-range
    progress yield 0 (never a burst the script did not direct).
    """
    u = float(u)
    if u < 0.0 or u > 1.0:
        # Outside the event span there is no payoff: clamping
        # would paint the sustain forever after the event ends.
        return 0.0
    if action_type == "CRACK":
        if u < 0.6:
            return 0.0
        if u < 0.68:
            return (u - 0.6) / 0.08
        return 1.0 - 0.45 * _smoothstep((u - 0.68) / 0.32)
    if action_type == "ACTIVATE":
        if u < 0.25:
            return 0.0
        if u < 0.8:
            return _smoothstep((u - 0.25) / 0.55)
        return 1.0
    if action_type == "EMIT":
        if u < 0.45:
            return _smoothstep(u / 0.45)
        if u < 0.6:
            return 1.0
        return 1.0 - 0.4 * _smoothstep((u - 0.6) / 0.4)
    return 0.0


def burst_color_radius(prop):
    """(color, radius_px) for a prop's burst.

    The prop's ``energy`` spec wins (same fallbacks as the state
    machine: colour from the spec, radius_px default 240). Props
    without an energy spec burst forge gold at the default radius
    -- a crack reveals light whether or not the prop is a bolt.
    """
    energy = (prop or {}).get("energy") if isinstance(prop, dict) \
        else None
    color = DEFAULT_BURST_COLOR
    radius = DEFAULT_BURST_RADIUS_PX
    if isinstance(energy, dict):
        raw = energy.get("color", DEFAULT_BURST_COLOR)
        if isinstance(raw, str):
            text = raw.lstrip("#")
            try:
                raw = tuple(int(text[i:i + 2], 16)
                            for i in (0, 2, 4))
            except (ValueError, IndexError):
                raw = DEFAULT_BURST_COLOR
        try:
            color = tuple(int(c) for c in raw[:3])
        except (TypeError, ValueError):
            color = DEFAULT_BURST_COLOR
        try:
            radius = float(energy.get("radius_px",
                                      DEFAULT_BURST_RADIUS_PX))
        except (TypeError, ValueError):
            radius = DEFAULT_BURST_RADIUS_PX
    return color, radius


def burst_record(prop_id, x, y, intensity, color, radius_px):
    """A ``paint_energy_glow`` record for a burst.

    Same shape as ``energy_glow_at`` records (2-element
    ``source_position`` = pixel space; ``radius`` already
    intensity-scaled), so the lighting stage consumes it
    unchanged, including the deferred insert path's
    ``_screen_glow_record`` mapping.
    """
    return {
        "prop_id": str(prop_id),
        "intensity": min(1.0, max(0.0, float(intensity))),
        "color": tuple(int(c) for c in color),
        "radius": float(radius_px) * min(1.0, max(0.0,
                                                 float(intensity))),
        "source_position": (float(x), float(y)),
    }


def crack_lines(bbox, seed_key, count=3):
    """Deterministic jagged crack polylines inside ``bbox``.

    ``bbox`` is (x0, y0, x1, y1) in the space the lines draw in;
    ``seed_key`` (the prop id) makes the cracks STABLE across
    frames -- the crack pattern never shimmers; only its alpha
    ramps with the envelope. The lines stay in the CENTRE of the
    box: a prop's drawn shape occupies the middle of its
    footprint (a key is ~40 px wide in a 76 px footprint), so
    full-box lines would read as scratches in the air around the
    prop instead of cracks in it. Each line runs from near the
    centre outward in a spread direction, 4 segments with
    perpendicular jitter, clamped inside the inset box.
    """
    x0, y0, x1, y1 = (float(v) for v in bbox)
    ix = (x1 - x0) * 0.22
    iy = (y1 - y0) * 0.22
    x0, y0, x1, y1 = x0 + ix, y0 + iy, x1 - ix, y1 - iy
    seed = zlib.crc32(str(seed_key).encode("utf-8"))
    rng = random.Random(seed)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    reach = max(x1 - x0, y1 - y0) * 0.5
    lines = []
    base = rng.uniform(0.0, 2.0 * math.pi)
    for i in range(max(1, int(count))):
        angle = base + i * (2.0 * math.pi / max(1, int(count))) \
            + rng.uniform(-0.3, 0.3)
        px, py = cx + rng.uniform(-6.0, 6.0), cy + rng.uniform(
            -6.0, 6.0)
        pts = [(px, py)]
        step = reach / 4.0
        for _seg in range(4):
            px += math.cos(angle) * step \
                + rng.uniform(-step * 0.35, step * 0.35)
            py += math.sin(angle) * step \
                + rng.uniform(-step * 0.35, step * 0.35)
            px = min(max(px, x0 + 2.0), x1 - 2.0)
            py = min(max(py, y0 + 2.0), y1 - 2.0)
            pts.append((px, py))
        lines.append(pts)
    return lines


def names_set_piece(normed):
    """True when normalised sentence text names a reactive set-piece.

    Token-sequence matching on normalised text: "lò" (furnace),
    "lò rèn"/"lò nung"/"lò lửa", "máy"/"cỗ máy" (machine). The
    reaction still needs the matching element in the scene -- a
    machine named in a scene with no furnace element paints
    nothing, so this can never summon a set-piece.
    """
    toks = str(normed or "").lower().split()
    if not toks:
        return False
    singles = {"lò", "máy"}
    if any(tok in singles for tok in toks):
        return True
    pairs = {("lò", "rèn"), ("lò", "nung"), ("lò", "lửa"),
             ("cỗ", "máy")}
    return any((toks[i], toks[i + 1]) in pairs
               for i in range(len(toks) - 1))


def strike_reaction(t, strike_times, decay_sec=STRIKE_DECAY_SEC):
    """Spark-pulse reaction (0..1) at time ``t``.

    1.0 at each hammer-strike contact moment, decaying
    exponentially afterwards; 0 before the first strike. The
    strike moments come from ``hammer_strike_times`` -- the same
    moments the audio anchors use -- so sparks, sound, and the
    hammer head agree on when contact happens.
    """
    best = 0.0
    for moment in strike_times or ():
        dt = float(t) - float(moment)
        if dt < 0:
            continue
        best = max(best, math.exp(-dt / max(float(decay_sec), 1e-6)))
    return min(1.0, best)
