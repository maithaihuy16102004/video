"""Prop interaction system (Visual Quality Recovery, Priority 2).

An object attachment + interaction state machine driven by the
action compiler's events. A prop is never staged by a guess: it has
an explicit rest transform (from ``staging``), follows the named hand
joint while held, and returns to the ground ONLY after an explicit
release action. The defect this replaces: the old renderer staged
every prop on the ground in every shot (the wallet under the
character's feet in the trench, the pen on the office floor).

States:
  WORLD_STATIC: at rest (fixed point, or anchored to an owner --
    e.g. a pocket that follows the owner's hip).
  APPROACHING: travelling from its rest to the grasping hand.
  GRASPED: contact made, not yet lifted (the grasp hold).
  ATTACHED_TO_HAND: follows the named hand joint + hold offset.
  IN_USE: held AND operated (wallet opening, pen writing).
  TRANSFERRED: travelling between giver and receiver hands.
  RELEASED: travelling from the hand back to its rest.

API (exact contract):
  PropStateMachine(props, events, staging=None, ground_y=None)
  state_at(prop_id, t) -> state name
  transform_at(prop_id, t, joints) -> (x, y, angle_deg, state, hand)
  contact_satisfied(event, joints, prop_transforms) -> bool

``joints`` is {actor_id: joints_dict} (or a single flat joints dict
for one-actor scenes). ``transform_at`` returns the prop's ANCHOR
point: the grip point for a pen (the hand), the centre for a wallet,
the handle for a bag; drawing offsets are the renderer's job.
``hand`` is "l" | "r" | "both" | None.

Invariants (enforced by construction, asserted by tests):
  1. While ATTACHED_TO_HAND / IN_USE the prop anchor equals the
     named hand joint (plus a fixed per-kind hold offset).
  2. No teleport: consecutive samples never jump more than
     MAX_JUMP_PX_PER_SEC (hand-speed upper bound). Every transition
     interpolates between continuous endpoints.
  3. A prop is on the ground ONLY when its rest kind is "ground"
     after an explicit release (PUT_AWAY / RELEASE) -- never as a
     default staging.

Unstaged props: a prop with no staging entry and no
``initial_transform`` rests at (0, 0) and earns a diagnostics entry.
The state machine never invents a plausible position -- staging is
the renderer's job (ATLAS wires it), and the diagnostic makes a
missing staging visible instead of silently wrong.

``contact_satisfied`` checks an event's contact_points against live
joints + prop transforms. Target kinds: "prop" (anchor distance),
"prop_surface" (pen tip inside the paper rect -- the tip is computed
from the hand joint through the pen geometry in primitives),
"character_hand" (distance to the target actor's nearest hand),
"ground" (|joint_y - ground_y|), "furniture" / "anchor" (distance to
a staged position), "gaze_target" (angular, tolerance_deg).
``prop_transforms`` maps prop ids to (x, y, angle, state, hand)
tuples (or {"x","y"} dicts) and may carry "__ground_y__" plus
furniture entries {"x","y"}.
"""
from __future__ import annotations

import inspect
import math
import re

from .animation.primitives import (
    HAMMER_CYCLE_SEC,
    HAMMER_CYCLE_STRIKE_U,
    HAMMER_GRIP_ANGLE_RAD,
    HAMMER_HANDLE_FRAC,
    HAMMER_HEAD_HALF_FRAC,
    HAND_OVER_TRANSFER_U,
    KNEEL_PICK_GRASP_U,
    PEN_GRIP_ANGLE_RAD,
    PEN_LEN_FRAC,
    PICK_UP_GRASP_U,
    PICK_UP_LIFT_U,
    PUT_AWAY_RELEASE_U,
    RECEIVE_REACH_U,
    hammer_head_position,
    pen_tip_position,
)
from .semantic_contracts import (
    PROP_TRANSITIONS,
    PropContainer,
    PropLifecycle,
    PropLocation,
    prop_may_rest_on_ground,
    prop_transition_allowed,
)

__all__ = [
    "PropStateMachine",
    "PROP_STATES",
    "MAX_JUMP_PX_PER_SEC",
    "MAX_JUMP_PX_PER_FRAME",
    "contact_satisfied",
    "contact_report",
    "sampled_max_jump",
    "bolt_shape_spec",
    "bolt_polygon_vertices",
    "ENERGY_RAMP_SEC",
    "DEFAULT_ENERGY_COLOR",
    "EMISSIVE_SLOT_COLOR",
    "default_energy_spec",
    "BOLT_DEFAULT_LENGTH_PX",
    "UnsupportedPropError", "MissingMaterialError",
    "PLACEHOLDER_MATERIAL", "PROP_FAMILIES", "PROP_KIND_FAMILY",
    "PROP_GEOMETRY_BUILDERS", "geometry_for_prop",
    "resolve_materials", "draw_prop_geometry",
    "draw_prop_placeholder", "spec_world_bbox",
    "spec_world_contact_points",
    "ForbiddenPropTransition", "SemanticPropTracker",
    "validate_staging_against_semantics",
]

PROP_STATES = (
    "WORLD_STATIC",
    "APPROACHING",
    "GRASPED",
    "ATTACHED_TO_HAND",
    "IN_USE",
    "TRANSFERRED",
    "RELEASED",
)

# Teleport thresholds. A hand at full reach speed moves ~600 px/s; a
# teleport (staging jump, holder switch without a handover) is
# typically several thousand px/s. The per-frame value is the same
# bound at 24 fps. Tests assert realistic sequences stay far below.
MAX_JUMP_PX_PER_SEC = 1200.0
MAX_JUMP_PX_PER_FRAME = MAX_JUMP_PX_PER_SEC / 24.0

# Hold angles (degrees, screen coords, y down) per prop kind while
# attached. A pen points forward-down at the grip angle; everything
# else rides level. Facing left mirrors the pen angle.
_HOLD_ANGLE_DEG = {
    "pen": 65.0,
}

# Paper size default (w, h) for prop_surface checks when the event
# carries no paper_size and the prop carries no size.
_DEFAULT_PAPER_SIZE = (120.0, 80.0)

# --- Bolt prop geometry (Test F, 2026-11-12) ---------------------------
# A lightning bolt is a GENERAL prop: a jagged closed polygon, never
# a box. The shape is DATA (this spec), consumed by any renderer --
# the product renderer's _draw_prop branch (ATLAS wiring) and the
# Test F proofs draw the same vertices through
# bolt_polygon_vertices(). Colours are NOT in the spec: the renderer
# owns the palette (INK outline + flat fill, like every other prop);
# the bolt's light is the energy_glow record (below), whose colour
# comes from the prop's own energy data.
BOLT_DEFAULT_LENGTH_PX = 170.0
BOLT_DEFAULT_WIDTH_FRAC = 0.24   # ribbon width, fraction of length
BOLT_DEFAULT_JAG_FRAC = 0.14     # zigzag amplitude, fraction of length
BOLT_GRIP_U = 0.60               # grip point: 60% down from top tip


def bolt_shape_spec(length, width=None, segments=4, jag=None):
    """Closed jagged-polygon spec for a lightning bolt prop.

    Local coordinates: origin at the GRIP point (where the holding
    hand wraps the shaft), +y down along the bolt. The spine runs
    from the top tip (y = -0.60 * length) to the bottom tip
    (y = +0.40 * length) with ``segments`` zigzag elbows; the ribbon
    around the spine tapers toward the bottom tip and closes to a
    point at both tips.

    Returns {"kind": "bolt", "vertices": [(x, y), ...] (closed
    polygon, no duplicated tip points), "spine": [...], "grip":
    (0.0, 0.0), "center": bbox centre, "length", "width",
    "segments", "bbox": (x0, y0, x1, y1)}. Pure function of its
    inputs (deterministic; the same inputs always give the same
    vertices). Raises ValueError on non-positive length/width or
    fewer than 2 segments.
    """
    length = float(length)
    if length <= 0.0:
        raise ValueError(f"bolt length must be positive, got {length!r}")
    width = float(BOLT_DEFAULT_WIDTH_FRAC * length
                  if width is None else width)
    if width <= 0.0:
        raise ValueError(f"bolt width must be positive, got {width!r}")
    jag = float(BOLT_DEFAULT_JAG_FRAC * length if jag is None else jag)
    if jag < 0.0:
        raise ValueError(f"bolt jag must be >= 0, got {jag!r}")
    segments = int(segments)
    if segments < 2:
        raise ValueError(f"bolt needs >= 2 segments, got {segments!r}")
    y_top = -BOLT_GRIP_U * length
    y_bot = (1.0 - BOLT_GRIP_U) * length
    spine = []
    for i in range(segments + 1):
        y = y_top + (y_bot - y_top) * i / segments
        if i == 0 or i == segments:
            x = 0.0
        else:
            x = jag if i % 2 == 1 else -jag
        spine.append((x, y))
    left, right = [], []
    for i, (px, py) in enumerate(spine):
        if i == 0:
            dx, dy = spine[1][0] - px, spine[1][1] - py
        elif i == segments:
            dx, dy = px - spine[i - 1][0], py - spine[i - 1][1]
        else:
            dx, dy = spine[i + 1][0] - spine[i - 1][0], \
                spine[i + 1][1] - spine[i - 1][1]
        norm = math.hypot(dx, dy) or 1.0
        perp = (-dy / norm, dx / norm)
        if i == 0 or i == segments:
            half = 0.0
        else:
            half = 0.5 * width * (1.0 - 0.3 * i / segments)
        left.append((px + perp[0] * half, py + perp[1] * half))
        right.append((px - perp[0] * half, py - perp[1] * half))
    vertices = left + right[::-1]
    deduped = []
    for vertex in vertices:
        if not deduped or vertex != deduped[-1]:
            deduped.append(vertex)
    if len(deduped) > 1 and deduped[0] == deduped[-1]:
        deduped.pop()
    xs = [v[0] for v in deduped]
    ys = [v[1] for v in deduped]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    return {
        "kind": "bolt",
        "vertices": deduped,
        "spine": spine,
        "grip": (0.0, 0.0),
        "center": ((bbox[0] + bbox[2]) / 2.0,
                   (bbox[1] + bbox[3]) / 2.0),
        "length": length,
        "width": width,
        "segments": segments,
        "bbox": bbox,
    }


def bolt_polygon_vertices(spec, x, y, angle_deg=0.0):
    """World-space polygon vertices for a bolt spec placed with its
    grip point at (x, y), rotated ``angle_deg`` degrees (positive =
    clockwise on screen, y down -- the transform-angle convention).
    Angle 0 draws the bolt vertical, grip at (x, y)."""
    theta = math.radians(float(angle_deg))
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return [(float(x) + vx * cos_t - vy * sin_t,
             float(y) + vx * sin_t + vy * cos_t)
            for vx, vy in spec["vertices"]]


# --- Energy glow (Test F, 2026-11-12) ----------------------------------
# DATA interface only: while an energy-carrying prop is gripped, the
# state machine emits an energy_glow record per frame --
# {prop_id, intensity, color, radius, source_position, state,
# holder}. Lighting response (glow rendering, surface illumination)
# belongs to the lighting stage (B owns lighting.py); this module
# never draws light. A prop carries energy only when its prop dict
# declares an "energy" spec: {"color": (r, g, b) | "#hex",
# "radius_px": float, "ramp_sec": float}. The colour is prop DATA
# (the script's trait path supplies it); the default below is the
# neutral fallback for an energy spec that names no colour.
ENERGY_RAMP_SEC = 0.4
DEFAULT_ENERGY_COLOR = (170, 205, 255)
# Colour of the "emissive" geometry slot: the gold-emissive
# material's emissive colour (MATERIAL_CATALOG, lighting.py).
# Drift-guarded by test_energy_glow_wiring against the catalog
# and the renderer's geometry slot fills; this module must not
# import lighting (the material catalog lives there, the geometry
# specs live here -- the test ties the two together).
EMISSIVE_SLOT_COLOR = (255, 210, 90)
_HELD_STATES = ("GRASPED", "ATTACHED_TO_HAND", "IN_USE", "TRANSFERRED")


def _smooth(u: float) -> float:
    u = max(0.0, min(1.0, float(u)))
    return u * u * (3.0 - 2.0 * u)


def _lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def _hand_pos(joints: dict, hand: str):
    """Hand joint position; "both" is the midpoint of both hands."""
    if hand == "both":
        left = joints["hand_l"]
        right = joints["hand_r"]
        return ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)
    return joints["hand_" + hand]


def _resolve_joints(joints: dict, actor_id):
    """joints for one actor from {actor_id: joints} or a flat dict."""
    if not isinstance(joints, dict):
        return None
    if actor_id is not None and actor_id in joints:
        candidate = joints[actor_id]
        if isinstance(candidate, dict) and "hand_r" in candidate:
            return candidate
    if "hand_r" in joints:
        return joints
    return None


def _transform_xy(transform):
    """(x, y) from a transform tuple or dict."""
    if isinstance(transform, dict):
        return float(transform["x"]), float(transform["y"])
    return float(transform[0]), float(transform[1])


def _transfer_pairs(ordered_events):
    """(paired_handover_ids, paired_receive_ids) by event identity.

    A HAND_OVER whose NEXT event for the same prop is a RECEIVE_PROP
    is one transfer in two descriptions (giver sentence + receiver
    sentence): the transfer stays TRANSFERRED / IN_TRANSIT until
    the receive completes it, instead of completing twice.
    """
    by_prop: dict = {}
    for event in ordered_events:
        pid = event.get("prop_id")
        if pid:
            by_prop.setdefault(pid, []).append(event)
    paired_ho, paired_recv = set(), set()
    for evs in by_prop.values():
        for prev, cur in zip(evs, evs[1:]):
            if (prev.get("action_type") == "HAND_OVER"
                    and cur.get("action_type") == "RECEIVE_PROP"):
                paired_ho.add(id(prev))
                paired_recv.add(id(cur))
    return paired_ho, paired_recv


class PropStateMachine:
    """Per-prop state timelines built from compiler events."""

    def __init__(self, props, events, staging=None, ground_y=None):
        self.ground_y = ground_y
        self.diagnostics: list[dict] = []
        self._props: dict[str, dict] = {}
        self._rest: dict[str, dict] = {}
        staging = staging or {}
        for prop in props or []:
            if not isinstance(prop, dict):
                continue
            pid = prop.get("id") or prop.get("name")
            if not pid:
                continue
            self._props[pid] = prop
            rest = staging.get(pid)
            if rest is None:
                rest = prop.get("initial_transform")
            if rest is None:
                self.diagnostics.append({
                    "prop_id": pid,
                    "issue": "unstaged: no staging entry and no "
                             "initial_transform; rest defaults to "
                             "the origin (0, 0)",
                })
                rest = {"x": 0.0, "y": 0.0, "angle": 0.0,
                        "kind": "point"}
            self._rest[pid] = self._normalise_rest(pid, rest)
        # Markers: prop_id -> [(time, state, meta)] sorted by time.
        self._markers: dict[str, list] = {pid: [] for pid in self._props}
        self._detail_markers: dict[str, list] = {
            pid: [] for pid in self._props}
        self._build(events or [])
        # Semantic state timelines (contract dimensions + the ground
        # rule). Raises ForbiddenPropTransition on definitive
        # contradictions in events carrying semantic_action_type;
        # legacy event lists without semantic types warn instead.
        self.semantic_tracker = SemanticPropTracker(
            self._props, events or [])

    # -- setup ---------------------------------------------------------

    def _normalise_rest(self, pid: str, rest) -> dict:
        """Rest spec -> {"x","y","angle","kind","anchor_id","offset"}.

        Accepts (x, y), (x, y, angle), or a dict with x/y/angle/kind
        ("point" | "ground" | "surface" | "pocket") and, for a pocket
        anchor, anchor_id + offset (dx, dy) from the anchor's hip.
        """
        if isinstance(rest, (list, tuple)):
            x, y = float(rest[0]), float(rest[1])
            angle = float(rest[2]) if len(rest) > 2 else 0.0
            return {"x": x, "y": y, "angle": angle, "kind": "point",
                    "anchor_id": None, "offset": (0.0, 0.0)}
        spec = dict(rest)
        out = {
            "x": float(spec.get("x", 0.0)),
            "y": float(spec.get("y", 0.0)),
            "angle": float(spec.get("angle", 0.0)),
            "kind": str(spec.get("kind", "point")),
            "anchor_id": spec.get("anchor_id"),
            "offset": tuple(spec.get("offset", (0.0, 0.0))),
        }
        if out["kind"] == "pocket" and not out["anchor_id"]:
            owner = (self._props[pid] or {}).get("owner")
            out["anchor_id"] = owner or None
        return out

    # -- transition building -------------------------------------------

    def _build(self, events: list[dict]):
        """Turn events into per-prop marker timelines."""
        ordered = sorted(
            (e for e in events if isinstance(e, dict)),
            key=lambda e: (float(e.get("start_time", 0.0)),
                           str(e.get("action_id", ""))))
        paired_ho, paired_recv = _transfer_pairs(ordered)
        held: dict[str, dict] = {}  # prop_id -> {holder, hand}
        for event in ordered:
            pid = event.get("prop_id")
            if not pid or pid not in self._props:
                continue
            action = event.get("action_type")
            start = float(event.get("start_time", 0.0))
            end = float(event.get("end_time", start))
            dur = max(end - start, 0.0)
            params = ((event.get("required_pose") or {}).get("params")
                      or {})
            hand = params.get("hand", "r")
            actor = event.get("actor_id")
            if action in ("BEND_PICK", "KNEEL_PICK"):
                # Ground pickup: the hand reaches the prop at the
                # kneel/bend grasp moment, holds through the hold
                # phase, then lifts with the rise. (Before A2 this
                # branch did not exist: a ground pickup left the
                # prop WORLD_STATIC at its rest while the character
                # grasped thin air.)
                grasp_t = start + KNEEL_PICK_GRASP_U * dur
                lift_t = start + PICK_UP_LIFT_U * dur
                self._add(pid, start, "APPROACHING",
                          {"event": event, "hand": hand, "actor": actor})
                self._add(pid, grasp_t, "GRASPED",
                          {"event": event, "hand": hand, "actor": actor})
                self._add(pid, lift_t, "ATTACHED_TO_HAND",
                          {"event": event, "hand": hand, "actor": actor})
                held[pid] = {"holder": actor, "hand": hand}
            elif action in ("PICK_UP", "TAKE_OUT", "HOLD"):
                grasp_t = start + PICK_UP_GRASP_U * dur
                lift_t = start + PICK_UP_LIFT_U * dur
                self._add(pid, start, "APPROACHING",
                          {"event": event, "hand": hand, "actor": actor})
                self._add(pid, grasp_t, "GRASPED",
                          {"event": event, "hand": hand, "actor": actor})
                self._add(pid, lift_t, "ATTACHED_TO_HAND",
                          {"event": event, "hand": hand, "actor": actor})
                held[pid] = {"holder": actor, "hand": hand}
            elif action == "HOLD_PEN":
                grasp_t = start + 0.40 * dur
                ready_t = start + 0.55 * dur
                self._add(pid, start, "APPROACHING",
                          {"event": event, "hand": hand, "actor": actor})
                self._add(pid, grasp_t, "GRASPED",
                          {"event": event, "hand": hand, "actor": actor})
                self._add(pid, ready_t, "ATTACHED_TO_HAND",
                          {"event": event, "hand": hand, "actor": actor})
                held[pid] = {"holder": actor, "hand": hand}
            elif action in ("OPEN_WALLET", "CLOSE_WALLET",
                            "OPEN", "CLOSE"):
                if pid not in held:
                    self.diagnostics.append({
                        "prop_id": pid,
                        "issue": f"{action} without a preceding grasp "
                                 f"(event {event.get('action_id')}); "
                                 "the prop is treated as held from "
                                 "the event start",
                        "action_id": event.get("action_id"),
                    })
                    held[pid] = {"holder": actor, "hand": hand}
                # Two-handed operation: the prop stays anchored to
                # the DOMINANT (holding) hand; the second hand joins
                # the prop. Anchoring to the hand midpoint would
                # teleport the prop whenever an event switches
                # between one-hand and two-hand holds.
                if hand == "both":
                    hand = held[pid].get("hand") or "r"
                    if hand == "both":
                        hand = "r"
                self._add(pid, start, "IN_USE",
                          {"event": event, "hand": hand, "actor": actor})
                self._add(pid, end, "ATTACHED_TO_HAND",
                          {"event": event, "hand": hand, "actor": actor})
                self._detail_markers[pid].append(
                    (start, end, "open_u",
                     1.0 if action in ("OPEN_WALLET", "OPEN") else 0.0))
            elif action in ("WRITE", "SIGN", "HAMMER_STRIKE"):
                # HAMMER_STRIKE: the tool stays gripped and IN_USE for
                # the whole striking run (the hammer never leaves the
                # hand between strikes); the strike contact itself is
                # measured through hammer_head_position, not here.
                if pid not in held:
                    self.diagnostics.append({
                        "prop_id": pid,
                        "issue": f"{action} without a preceding grasp "
                                 f"(event {event.get('action_id')})",
                        "action_id": event.get("action_id"),
                    })
                    held[pid] = {"holder": actor, "hand": hand}
                self._add(pid, start, "IN_USE",
                          {"event": event, "hand": hand, "actor": actor})
                self._add(pid, end, "ATTACHED_TO_HAND",
                          {"event": event, "hand": hand, "actor": actor})
            elif action == "HAND_OVER":
                receiver = event.get("target_id")
                # The receiver's taking hand: the compiler's
                # receive_hand param (from "tay phải" / "tay trái"
                # in the shot text), else the historical "l".
                receive_hand = params.get("receive_hand", "l")
                if receive_hand not in ("l", "r"):
                    receive_hand = "l"
                self._add(pid, start, "TRANSFERRED",
                          {"event": event, "hand": hand, "actor": actor,
                           "receiver": receiver,
                           "receive_hand": receive_hand})
                if id(event) in paired_ho:
                    # Paired with a following RECEIVE_PROP: the
                    # transfer stays TRANSFERRED until the receive
                    # completes it. Adding an ATTACHED marker here
                    # and a second TRANSFERRED window at the receive
                    # would swing the prop back toward the giver.
                    pass
                else:
                    self._add(pid, end, "ATTACHED_TO_HAND",
                              {"event": event, "hand": receive_hand,
                               "actor": receiver})
                    if receiver:
                        held[pid] = {"holder": receiver,
                                     "hand": receive_hand}
            elif action == "RECEIVE_PROP":
                receiver = actor
                giver = (held.get(pid) or {}).get("holder")
                giver_hand = (held.get(pid) or {}).get("hand", "r")
                receive_hand = params.get("receive_hand", hand)
                if receive_hand not in ("l", "r"):
                    receive_hand = hand if hand in ("l", "r") else "l"
                if id(event) not in paired_recv:
                    # Unpaired: the transfer window starts here (the
                    # giver is unknown -- transform_at falls back to
                    # the receiver's hand when the giver has no
                    # joints; the semantic tracker records the gap).
                    self._add(pid, start, "TRANSFERRED",
                              {"event": event, "hand": giver_hand,
                               "actor": giver, "receiver": receiver,
                               "receive_hand": receive_hand})
                self._add(pid, end, "ATTACHED_TO_HAND",
                          {"event": event, "hand": receive_hand,
                           "actor": receiver})
                held[pid] = {"holder": receiver, "hand": receive_hand}
            elif action in ("PUT_AWAY", "RELEASE"):
                # The prop is HELD until the release moment: without
                # a held marker here the pre-release span falls back
                # to the rest position, so a dropped prop would sit
                # on the ground (or hide in a pocket) before the
                # hand ever lets go of it.
                if pid not in held:
                    self.diagnostics.append({
                        "prop_id": pid,
                        "issue": f"{action} without a preceding grasp "
                                 f"(event {event.get('action_id')}); "
                                 "the prop is treated as held from "
                                 "the event start",
                        "action_id": event.get("action_id"),
                    })
                    held[pid] = {"holder": actor, "hand": hand}
                self._add(pid, start, "ATTACHED_TO_HAND",
                          {"event": event, "hand": hand, "actor": actor})
                release_t = start + PUT_AWAY_RELEASE_U * dur
                rest_kind = ("pocket" if action == "PUT_AWAY"
                             else "surface")
                self._add(pid, release_t, "RELEASED",
                          {"event": event, "hand": hand, "actor": actor,
                           "rest_kind": rest_kind})
                self._add(pid, end, "WORLD_STATIC",
                          {"event": event, "hand": hand, "actor": actor,
                           "rest_kind": rest_kind})
                held.pop(pid, None)
            elif action == "CARRY":
                if pid not in held:
                    held[pid] = {"holder": actor, "hand": hand}
                self._add(pid, start, "ATTACHED_TO_HAND",
                          {"event": event, "hand": hand, "actor": actor})
                self._add(pid, end, "ATTACHED_TO_HAND",
                          {"event": event, "hand": hand, "actor": actor})
        for pid in self._markers:
            self._markers[pid].sort(key=lambda m: (m[0], m[1]))

    def _add(self, pid: str, when: float, state: str, meta: dict):
        self._markers[pid].append((float(when), state, meta))

    # -- queries ---------------------------------------------------------

    def _marker_at(self, pid: str, t: float):
        """Latest marker at or before t: (time, state, meta) | None."""
        best = None
        for marker in self._markers.get(pid, []):
            if marker[0] <= t:
                best = marker
            else:
                break
        return best

    def _next_marker(self, pid: str, t: float):
        for marker in self._markers.get(pid, []):
            if marker[0] > t:
                return marker
        return None

    def state_at(self, pid: str, t: float) -> str:
        if pid not in self._props:
            raise KeyError(f"unknown prop: {pid!r}")
        marker = self._marker_at(pid, float(t))
        return marker[1] if marker else "WORLD_STATIC"

    def rest_kind(self, pid: str) -> str:
        """Staging rest kind for a prop ("point" | "ground" |
        "surface" | "pocket")."""
        if pid not in self._props:
            raise KeyError(f"unknown prop: {pid!r}")
        return self._rest[pid]["kind"]

    def semantic_location_at(self, pid: str, t: float):
        """Semantic location (PropLocation value) at t, or None when
        the events never establish one."""
        return self.semantic_tracker.location_at(pid, t)

    def semantic_initial_location(self, pid: str):
        """Semantic location before the first event, or None."""
        return self.semantic_tracker.initial_location(pid)

    def ground_rest_allowed(self, pid: str, t: float) -> bool:
        """The ground rule: ground rest requires a DEFINITIVE
        ON_GROUND semantic location. Unknown is not ON_GROUND."""
        return self.semantic_tracker.ground_rest_allowed(pid, t)

    @property
    def semantic_warnings(self) -> list:
        return self.semantic_tracker.warnings

    def _rest_position(self, pid: str, joints: dict):
        """Rest (x, y, angle) -- pocket anchors follow the owner's hip."""
        rest = self._rest[pid]
        if rest["kind"] == "pocket" and rest["anchor_id"]:
            owner_joints = _resolve_joints(joints, rest["anchor_id"])
            if owner_joints is not None:
                hip = owner_joints["hip"]
                dx, dy = rest["offset"]
                return (hip[0] + dx, hip[1] + dy, rest["angle"])
        return (rest["x"], rest["y"], rest["angle"])

    def _hold_angle(self, pid: str, joints: dict, actor_id) -> float:
        kind = str(self._props[pid].get("kind") or "").lower()
        base = _HOLD_ANGLE_DEG.get(kind, 0.0)
        if base == 0.0:
            return 0.0
        actor_joints = _resolve_joints(joints, actor_id)
        facing = 1
        if actor_joints is not None:
            facing = actor_joints.get("facing", 1) or 1
        return base if facing >= 0 else 180.0 - base

    def transform_at(self, pid: str, t: float, joints: dict):
        """(x, y, angle_deg, state, hand) for a prop at time t."""
        if pid not in self._props:
            raise KeyError(f"unknown prop: {pid!r}")
        t = float(t)
        marker = self._marker_at(pid, t)
        state = marker[1] if marker else "WORLD_STATIC"
        meta = marker[2] if marker else {}
        hand = meta.get("hand") if marker else None
        rest_x, rest_y, rest_angle = self._rest_position(pid, joints)

        if state == "WORLD_STATIC":
            return (rest_x, rest_y, rest_angle, state, None)
        if state == "RELEASED":
            # Glide from the hand (where the prop was at release)
            # to its rest over the RELEASED window. At the release
            # instant u == 0, so the position equals the hand
            # position the ATTACHED state returned -- no jump even
            # if the staging rest differs slightly from where the
            # primitive put the hand. At the window end u == 1 and
            # the prop is at rest, matching WORLD_STATIC.
            nxt = self._next_marker(pid, t)
            end_t = nxt[0] if nxt else t
            u = _smooth((t - marker[0]) / max(end_t - marker[0], 1e-9))
            actor_joints = _resolve_joints(joints, meta.get("actor"))
            if actor_joints is None:
                return (rest_x, rest_y, rest_angle, state, hand)
            hx, hy = _hand_pos(actor_joints, hand or "r")
            return (_lerp(hx, rest_x, u), _lerp(hy, rest_y, u),
                    _lerp(self._hold_angle(pid, joints, meta.get("actor")),
                          rest_angle, u),
                    state, hand)
        if state == "APPROACHING":
            nxt = self._next_marker(pid, t)
            grasp_t = nxt[0] if nxt else t
            start_t = marker[0]
            u = _smooth((t - start_t) / max(grasp_t - start_t, 1e-9))
            actor_joints = _resolve_joints(joints, meta.get("actor"))
            if actor_joints is None:
                return (rest_x, rest_y, rest_angle, state, hand)
            hx, hy = _hand_pos(actor_joints, hand or "r")
            return (_lerp(rest_x, hx, u), _lerp(rest_y, hy, u),
                    _lerp(rest_angle,
                          self._hold_angle(pid, joints, meta.get("actor")),
                          u),
                    state, hand)
        if state == "TRANSFERRED":
            nxt = self._next_marker(pid, t)
            end_t = nxt[0] if nxt else t
            u = _smooth((t - marker[0]) / max(end_t - marker[0], 1e-9))
            giver = _resolve_joints(joints, meta.get("actor"))
            receiver = _resolve_joints(joints, meta.get("receiver"))
            if giver is None or receiver is None:
                fallback = giver if giver is not None else receiver
                if fallback is None:
                    return (rest_x, rest_y, rest_angle, state, hand)
                hx, hy = _hand_pos(fallback, hand or "r")
                return (hx, hy, self._hold_angle(pid, joints,
                                                 meta.get("actor")),
                        state, hand)
            gx, gy = _hand_pos(giver, hand or "r")
            recv_hand = meta.get("receive_hand", "l")
            if recv_hand not in ("l", "r"):
                recv_hand = "l"
            rx, ry = _hand_pos(receiver, recv_hand)
            active_hand = ((hand or "r")
                           if u < HAND_OVER_TRANSFER_U else recv_hand)
            return (_lerp(gx, rx, u), _lerp(gy, ry, u),
                    self._hold_angle(pid, joints, meta.get("actor")),
                    state, active_hand)
        # GRASPED / ATTACHED_TO_HAND / IN_USE: follow the named hand.
        actor_joints = _resolve_joints(joints, meta.get("actor"))
        if actor_joints is None:
            return (rest_x, rest_y, rest_angle, state, hand)
        hx, hy = _hand_pos(actor_joints, hand or "r")
        return (hx, hy, self._hold_angle(pid, joints, meta.get("actor")),
                state, hand)

    def detail_at(self, pid: str, t: float) -> dict:
        """Object state detail: open_u (wallet), holder, rest kind."""
        if pid not in self._props:
            raise KeyError(f"unknown prop: {pid!r}")
        t = float(t)
        open_u = 0.0
        for start, end, key, value in self._detail_markers.get(pid, []):
            if key != "open_u":
                continue
            if t < start:
                break
            if t >= end:
                open_u = float(value)
            else:
                prev = open_u
                open_u = _lerp(prev, float(value),
                               _smooth((t - start) / max(end - start,
                                                         1e-9)))
        marker = self._marker_at(pid, t)
        holder = None
        if marker and marker[1] in ("ATTACHED_TO_HAND", "IN_USE",
                                    "GRASPED"):
            holder = marker[2].get("actor")
        elif marker and marker[1] == "TRANSFERRED":
            holder = marker[2].get("actor")
        return {
            "open_u": open_u,
            "holder": holder,
            "state": marker[1] if marker else "WORLD_STATIC",
            "rest_kind": self._rest[pid]["kind"],
        }

    # -- energy glow (Test F: data interface for the lighting stage) --

    def _energy_spec(self, pid: str) -> dict | None:
        """Normalised energy spec for a prop, or None when the prop
        carries no energy. Accepts color as an (r, g, b) tuple or a
        "#rrggbb" string; radius_px / ramp_sec fall back to the
        module defaults."""
        prop = self._props.get(pid) or {}
        energy = prop.get("energy")
        if not isinstance(energy, dict):
            return None
        color = energy.get("color", DEFAULT_ENERGY_COLOR)
        if isinstance(color, str):
            text = color.lstrip("#")
            try:
                color = tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
            except (ValueError, IndexError):
                color = DEFAULT_ENERGY_COLOR
        color = tuple(int(c) for c in color[:3])
        return {
            "color": color,
            "radius_px": float(energy.get("radius_px", 240.0)),
            "ramp_sec": max(float(energy.get("ramp_sec",
                                             ENERGY_RAMP_SEC)),
                            1e-6),
        }

    def _energy_center_offset(self, pid: str, angle_deg: float):
        """Glow-centre offset from the prop's transform position.

        For a bolt the glow centres on the bolt's bbox centre (the
        shape spec knows it); every other energy prop glows from its
        transform position. The offset rotates with the prop's
        transform angle (same convention as bolt_polygon_vertices).
        """
        prop = self._props.get(pid) or {}
        if str(prop.get("kind") or "").lower() != "bolt":
            return (0.0, 0.0)
        length = prop.get("length_px", BOLT_DEFAULT_LENGTH_PX)
        spec = bolt_shape_spec(length)
        cx, cy = spec["center"]
        theta = math.radians(float(angle_deg))
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        return (cx * cos_t - cy * sin_t, cx * sin_t + cy * cos_t)

    def energy_glow_at(self, pid: str, t: float, joints: dict
                       ) -> dict | None:
        """Energy-glow record for a prop at time t, or None.

        Returns None when the prop carries no energy spec or is not
        currently held (WORLD_STATIC / RELEASED / APPROACHING): no
        record means no glow, and the lighting stage only acts on
        records it receives. While held (GRASPED / ATTACHED_TO_HAND
        / IN_USE / TRANSFERRED) the intensity ramps 0 -> 1 over
        ``ramp_sec`` from the start of the current continuous held
        run -- a handover does NOT restart the ramp (the bolt stays
        energised across the transfer); a release + re-grasp starts
        a new run. Intensity is the steady envelope (no flicker is
        synthesised here; per-frame flicker is the lighting stage's
        choice). Record fields: prop_id, intensity (0..1), color
        (r, g, b), radius (px, radius_px * intensity),
        source_position (world x, y of the glow centre), state,
        holder.
        """
        if pid not in self._props:
            raise KeyError(f"unknown prop: {pid!r}")
        spec = self._energy_spec(pid)
        if spec is None:
            return None
        t = float(t)
        marker = self._marker_at(pid, t)
        if marker is None or marker[1] not in _HELD_STATES:
            return None
        markers = self._markers[pid]
        run_start = marker[0]
        for idx in range(len(markers) - 1, -1, -1):
            if markers[idx] is marker:
                j = idx
                while j > 0 and markers[j - 1][1] in _HELD_STATES:
                    j -= 1
                run_start = markers[j][0]
                break
        intensity = max(0.0, min(1.0, (t - run_start)
                                 / spec["ramp_sec"]))
        x, y, angle, state, _hand = self.transform_at(pid, t, joints)
        ox, oy = self._energy_center_offset(pid, angle)
        holder = self.detail_at(pid, t)["holder"]
        return {
            "prop_id": pid,
            "intensity": intensity,
            "color": spec["color"],
            "radius": spec["radius_px"] * intensity,
            "source_position": (x + ox, y + oy),
            "state": state,
            "holder": holder,
        }

    def rest_kind_at(self, pid: str, t: float) -> str:
        """Rest kind in force at t (for the ground invariant)."""
        marker = self._marker_at(pid, t)
        if marker and marker[1] == "WORLD_STATIC":
            return marker[2].get("rest_kind") or self._rest[pid]["kind"]
        return self._rest[pid]["kind"]


# --- Contact ---------------------------------------------------------------

def _paper_rect(event: dict, prop_transforms: dict, paper_id):
    """(x0, y0, x1, y1) paper surface rect, or None."""
    if paper_id is None:
        return None
    transform = prop_transforms.get(paper_id)
    if transform is None:
        return None
    cx, cy = _transform_xy(transform)
    params = ((event.get("required_pose") or {}).get("params") or {})
    size = params.get("paper_size") or _DEFAULT_PAPER_SIZE
    w, h = float(size[0]), float(size[1])
    return (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def _furniture_pos(event: dict, prop_transforms: dict, target_id):
    """(x, y) for a furniture/anchor target, or None."""
    transform = prop_transforms.get(target_id) if target_id else None
    if transform is not None:
        return _transform_xy(transform)
    params = ((event.get("required_pose") or {}).get("params") or {})
    furniture = params.get("furniture")
    if isinstance(furniture, dict):
        entry = furniture.get(target_id)
        if entry is not None:
            return _transform_xy(entry)
    return None


def contact_report(event: dict, joints: dict, prop_transforms: dict,
                   ground_y=None) -> list[dict]:
    """Per-contact-point check: [{point, satisfied, measured, ...}].

    ``joints`` is {actor_id: joints} or a flat joints dict.
    ``prop_transforms`` maps prop ids to (x, y, angle, state, hand)
    tuples or {"x","y"} dicts, and may carry "__ground_y__".
    """
    actor_joints = _resolve_joints(joints, event.get("actor_id"))
    if actor_joints is None:
        actor_joints = joints if isinstance(joints, dict) else {}
    if ground_y is None:
        ground_y = prop_transforms.get("__ground_y__")
    results: list[dict] = []
    for point in event.get("contact_points") or []:
        joint = point.get("joint")
        kind = point.get("target_kind")
        target_id = point.get("target_id")
        tol = point.get("tolerance_px")
        joint_pos = actor_joints.get(joint) if joint else None
        entry = {"point": dict(point), "satisfied": False,
                 "measured": None, "reason": ""}
        if joint_pos is None:
            entry["reason"] = f"joint {joint!r} not in joints"
            results.append(entry)
            continue
        if kind == "prop":
            transform = prop_transforms.get(target_id)
            if transform is None:
                entry["reason"] = f"prop {target_id!r} has no transform"
            else:
                tx, ty = _transform_xy(transform)
                dist = math.hypot(joint_pos[0] - tx, joint_pos[1] - ty)
                entry["measured"] = dist
                entry["satisfied"] = tol is not None and dist <= tol
        elif kind == "prop_surface":
            rect = _paper_rect(event, prop_transforms, target_id)
            if rect is None:
                entry["reason"] = f"paper {target_id!r} has no transform"
            else:
                facing = actor_joints.get("facing", 1) or 1
                height = actor_joints.get("_H", 560.0)
                tip = pen_tip_position(joint_pos, facing, height)
                x0, y0, x1, y1 = rect
                pad = tol or 0.0
                inside = (x0 - pad <= tip[0] <= x1 + pad
                          and y0 - pad <= tip[1] <= y1 + pad)
                dx = max(x0 - tip[0], 0.0, tip[0] - x1)
                dy = max(y0 - tip[1], 0.0, tip[1] - y1)
                entry["measured"] = math.hypot(dx, dy)
                entry["tip"] = tip
                entry["satisfied"] = inside
        elif kind == "tool_head":
            # Tool-head contact (HAMMER_STRIKE): the TOOL's working
            # end -- not the hand -- must touch the surface point.
            # The surface point resolves from the target prop's
            # transform, else a staged furniture/anchor position.
            surface = None
            transform = prop_transforms.get(target_id)
            if transform is not None:
                surface = _transform_xy(transform)
            else:
                surface = _furniture_pos(event, prop_transforms,
                                         target_id)
            if surface is None:
                entry["reason"] = (f"tool_head target {target_id!r} "
                                   "has no staged position")
            else:
                facing = actor_joints.get("facing", 1) or 1
                height = actor_joints.get("_H", 560.0)
                head = hammer_head_position(joint_pos, facing, height)
                dist = math.hypot(head[0] - surface[0],
                                  head[1] - surface[1])
                entry["measured"] = dist
                entry["tool_head"] = head
                entry["satisfied"] = tol is not None and dist <= tol
        elif kind == "character_hand":
            other = _resolve_joints(joints, target_id)
            if other is None:
                entry["reason"] = f"actor {target_id!r} has no joints"
            else:
                wanted = point.get("target_hand")
                if wanted in ("l", "r"):
                    # The script names the receiving hand: measure
                    # THAT hand only, never the nearer one.
                    other_hand = other["hand_" + wanted]
                    dist = math.hypot(joint_pos[0] - other_hand[0],
                                      joint_pos[1] - other_hand[1])
                else:
                    dist = min(
                        math.hypot(joint_pos[0] - other["hand_l"][0],
                                   joint_pos[1] - other["hand_l"][1]),
                        math.hypot(joint_pos[0] - other["hand_r"][0],
                                   joint_pos[1] - other["hand_r"][1]))
                entry["measured"] = dist
                entry["satisfied"] = tol is not None and dist <= tol
        elif kind == "ground":
            if ground_y is None:
                entry["reason"] = "no ground_y supplied"
            else:
                dist = abs(joint_pos[1] - float(ground_y))
                entry["measured"] = dist
                entry["satisfied"] = tol is not None and dist <= tol
        elif kind in ("furniture", "anchor"):
            pos = _furniture_pos(event, prop_transforms, target_id)
            if pos is None:
                entry["reason"] = (f"furniture/anchor {target_id!r} "
                                   "has no staged position")
            else:
                dist = math.hypot(joint_pos[0] - pos[0],
                                  joint_pos[1] - pos[1])
                entry["measured"] = dist
                entry["satisfied"] = tol is not None and dist <= tol
        elif kind == "gaze_target":
            target_pos = None
            transform = prop_transforms.get(target_id)
            if transform is not None:
                target_pos = _transform_xy(transform)
            else:
                other = _resolve_joints(joints, target_id)
                if other is not None:
                    target_pos = other.get("head")
            if target_pos is None:
                entry["reason"] = f"gaze target {target_id!r} unresolved"
            else:
                dx = target_pos[0] - joint_pos[0]
                dy = target_pos[1] - joint_pos[1]
                if math.hypot(dx, dy) < 1e-6:
                    entry["measured"] = 0.0
                    entry["satisfied"] = True
                else:
                    facing = actor_joints.get("facing", 1) or 1
                    look = actor_joints.get("_head_look", 0.0)
                    gaze = (facing * math.cos(look), math.sin(look))
                    dot = (dx * gaze[0] + dy * gaze[1]) / (
                        math.hypot(dx, dy) * math.hypot(*gaze))
                    angle = math.degrees(
                        math.acos(max(-1.0, min(1.0, dot))))
                    entry["measured"] = angle
                    tol_deg = point.get("tolerance_deg")
                    entry["satisfied"] = (tol_deg is not None
                                          and angle <= tol_deg)
        else:
            entry["reason"] = f"unknown target_kind {kind!r}"
        results.append(entry)
    return results


def contact_satisfied(event: dict, joints: dict,
                      prop_transforms: dict) -> bool:
    """True when every contact point of ``event`` is satisfied.

    Events with no contact points are vacuously satisfied. The
    ``_H`` (character height) and ``_head_look`` keys in a joints
    dict are optional measurement hints the caller may attach; when
    absent, defaults (H=560, look=0) are used.
    """
    report = contact_report(event, joints, prop_transforms)
    return all(entry["satisfied"] for entry in report)


def sampled_max_jump(samples) -> dict:
    """Max movement from [(t, x, y), ...] samples.

    Returns {"max_jump_px": ..., "max_speed_px_per_sec": ...,
    "teleport": bool} where teleport means the per-second bound
    MAX_JUMP_PX_PER_SEC was exceeded between consecutive samples.
    Samples must be time-ordered.
    """
    max_jump = 0.0
    max_speed = 0.0
    prev = None
    for t, x, y in samples:
        if prev is not None:
            dt = float(t) - float(prev[0])
            dist = math.hypot(float(x) - prev[1], float(y) - prev[2])
            max_jump = max(max_jump, dist)
            if dt > 0:
                max_speed = max(max_speed, dist / dt)
        prev = (t, x, y)
    return {
        "max_jump_px": max_jump,
        "max_speed_px_per_sec": max_speed,
        "teleport": max_speed > MAX_JUMP_PX_PER_SEC,
    }


# --- Chain verification (Phase D / TEST E) -------------------------------
# check_chain_order is the standalone, testable version of the
# ordering rules the state machine enforces while building: a prop
# must be grasped before it is used or handed over, and released
# only while held. The state machine tolerates violations at runtime
# (diagnostics); this helper FAILS them loudly for proofs and tests.

_GRASP_ACTIONS = frozenset({"PICK_UP", "TAKE_OUT", "HOLD", "HOLD_PEN",
                            "CARRY"})
_USE_ACTIONS = frozenset({"WRITE", "SIGN", "OPEN_WALLET", "CLOSE_WALLET"})
_RELEASE_ACTIONS = frozenset({"PUT_AWAY", "RELEASE"})


def check_chain_order(events, initial_holders=None) -> list[dict]:
    """Violations of the grasp -> use -> handover/release order.

    ``events`` are compiler events (action_id/action_type/actor_id/
    prop_id/target_id/start_time). ``initial_holders`` maps prop ids
    to the actor holding them when the event list starts (a grasp in
    an earlier scene); without it, a use with no grasp in THIS list
    is a violation. Returns [{prop_id, action_id, action_type,
    issue}]; empty means the chain order is clean.
    """
    held: dict[str, str] = dict(initial_holders or {})
    violations: list[dict] = []
    ordered = sorted(
        (e for e in events if isinstance(e, dict)),
        key=lambda e: (float(e.get("start_time", 0.0)),
                       str(e.get("action_id", ""))))
    for event in ordered:
        pid = event.get("prop_id")
        if not pid:
            continue
        action = event.get("action_type")
        actor = event.get("actor_id")
        if action in _GRASP_ACTIONS:
            held[pid] = actor
        elif action in _USE_ACTIONS:
            if pid not in held:
                violations.append({
                    "prop_id": pid,
                    "action_id": event.get("action_id"),
                    "action_type": action,
                    "issue": f"{action} without a preceding grasp "
                             f"for prop {pid!r}",
                })
                held[pid] = actor
            elif held[pid] != actor:
                violations.append({
                    "prop_id": pid,
                    "action_id": event.get("action_id"),
                    "action_type": action,
                    "issue": f"{action} by {actor!r} but prop {pid!r} "
                             f"is held by {held[pid]!r}",
                })
        elif action == "HAND_OVER":
            if pid not in held:
                violations.append({
                    "prop_id": pid,
                    "action_id": event.get("action_id"),
                    "action_type": action,
                    "issue": f"HAND_OVER without a preceding grasp "
                             f"for prop {pid!r}",
                })
            elif held[pid] != actor:
                violations.append({
                    "prop_id": pid,
                    "action_id": event.get("action_id"),
                    "action_type": action,
                    "issue": f"HAND_OVER by {actor!r} but prop {pid!r} "
                             f"is held by {held[pid]!r}",
                })
            receiver = event.get("target_id")
            if receiver:
                held[pid] = receiver
        elif action in _RELEASE_ACTIONS:
            if pid not in held:
                violations.append({
                    "prop_id": pid,
                    "action_id": event.get("action_id"),
                    "action_type": action,
                    "issue": f"{action} without a preceding grasp "
                             f"for prop {pid!r}",
                })
            held.pop(pid, None)
    return violations


_HOLD_PEN_GRASP_U = 0.40  # matches the HOLD_PEN grasp in _build


def _contact_moment_u(action_type: str, event: dict | None = None
                    ) -> float:
    """Event fraction at which the action's contact is meaningful.

    A handover's hands meet at the event END (give_to converges
    linearly); a grasp's contact is AT the grasp moment; sustained
    actions (WRITE/SIGN) hold contact through the middle. Checking
    every event at its midpoint would fail a correct handover (the
    hands are still 150+ px apart mid-event) and miss a failed grasp.
    A hammer strike's contact is the FIRST strike moment: the
    cycle count comes from the event (required_pose params, else the
    primitive default from the event duration), so the fraction is
    HAMMER_CYCLE_STRIKE_U / cycles. Without an event the single-cycle
    strike fraction is returned.
    """
    if action_type == "HAND_OVER":
        return 1.0
    if action_type in ("PICK_UP", "TAKE_OUT", "HOLD"):
        return PICK_UP_GRASP_U
    if action_type in ("BEND_PICK", "KNEEL_PICK"):
        return KNEEL_PICK_GRASP_U
    if action_type == "RECEIVE_PROP":
        return RECEIVE_REACH_U
    if action_type == "HOLD_PEN":
        return _HOLD_PEN_GRASP_U
    if action_type in ("PUT_AWAY", "RELEASE"):
        return PUT_AWAY_RELEASE_U
    if action_type == "HAMMER_STRIKE":
        cycles = None
        if event is not None:
            params = ((event.get("required_pose") or {}).get("params")
                      or {})
            cycles = params.get("cycles")
            if cycles is None:
                dur = float(event.get("end_time", 0.0)) - float(
                    event.get("start_time", 0.0))
                cycles = max(1, round(dur / HAMMER_CYCLE_SEC))
        if cycles is None:
            return HAMMER_CYCLE_STRIKE_U
        return HAMMER_CYCLE_STRIKE_U / max(1, int(cycles))
    return 0.5


def verify_chain(psm, samples, events, ground_y=None) -> dict:
    """Full chain verification over sampled timeline data.

    ``samples`` is [{"t", "joints": {actor_id: joints}, "transforms":
    {prop_id: transform}}, ...] in time order (the proof script
    samples the state machine's ``transform_at`` per frame).
    ``events`` are the compiler events driving the chain.

    Returns {"teleports": {pid: sampled_max_jump result}, "contact":
    {action_id: contact_report at the event's contact moment (see
    _contact_moment_u)}, "contact_times": {action_id: evaluated t},
    "states": {pid: [states in time order]}, "violations":
    check_chain_order result}. A clean chain has no teleports, every
    contact report satisfied, and no order violations.
    """
    ordered = sorted(samples, key=lambda s: float(s["t"]))
    prop_series: dict[str, list[tuple[float, float, float]]] = {}
    states: dict[str, list[str]] = {}
    for sample in ordered:
        t = float(sample["t"])
        for pid, transform in (sample.get("transforms") or {}).items():
            x, y = _transform_xy(transform)
            prop_series.setdefault(pid, []).append((t, x, y))
        for pid in prop_series:
            state = psm.state_at(pid, t)
            if pid not in states:
                states[pid] = []
            if not states[pid] or states[pid][-1] != state:
                states[pid].append(state)
    teleports = {pid: sampled_max_jump(series)
                 for pid, series in prop_series.items()}
    contact: dict[str, list[dict]] = {}
    contact_times: dict[str, float] = {}
    for event in events:
        if not event.get("contact_points"):
            continue
        start = float(event.get("start_time", 0.0))
        end = float(event.get("end_time", start))
        moment = start + _contact_moment_u(
            event.get("action_type"), event) * (end - start)
        nearest = min(ordered,
                      key=lambda s: abs(float(s["t"]) - moment),
                      default=None)
        if nearest is None:
            continue
        transforms = dict(nearest.get("transforms") or {})
        if ground_y is not None:
            transforms.setdefault("__ground_y__", ground_y)
        contact[event.get("action_id")] = contact_report(
            event, nearest.get("joints") or {}, transforms,
            ground_y=ground_y)
        contact_times[event.get("action_id")] = float(nearest["t"])
    return {
        "teleports": teleports,
        "contact": contact,
        "contact_times": contact_times,
        "states": states,
        "violations": check_chain_order(events),
    }

# ---------------------------------------------------------------------------
# Semantic prop states (A2; directive §7 + semantic_contracts.py)
#
# Independent dimensions per prop -- location (PropLocation),
# container (PropContainer), lifecycle (PropLifecycle), ownership
# (holder id + transfer-in-progress) -- driven by the contract table
# PROP_TRANSITIONS (imported, never redefined). Anything the table
# forbids fails loudly (ForbiddenPropTransition) on the new semantic
# path: events carrying semantic_action_type. Legacy event lists
# without semantic types warn and assume the required from-state
# instead of raising, so old job records keep working.
#
# Initial locations are BACK-PROPAGATED, never guessed from staging:
# the first location-changing event's required from-state is the
# prop's location before it (TAKE_FROM_POCKET implies IN_POCKET,
# BEND_PICK implies ON_GROUND). Inferred states are revisable: a
# later event that contradicts an INFERRED state revises it with a
# warning; a later event that contradicts a DEFINITIVE state
# (established by a table transition) raises. Hold/use verbs
# (WRITE, HOLD, ...) never raise -- they warn and revise, matching
# the PSM's long-standing tolerance for grasp-less operations.
#
# The ground rule: a prop renders on the ground ONLY while its
# semantic location is ON_GROUND (ground_rest_allowed). Unknown is
# not ON_GROUND. validate_staging_against_semantics checks staging
# rest kinds against inferred initial locations and raises on every
# mismatch at once (preflight aggregates; it must see them all).
#
# The table gates transitions; the HAND comes from the event: the
# table's to-state HELD_RIGHT is refined to the event's hand
# (HELD_LEFT / HELD_BOTH) when the event names one. Handover
# pairing (see _transfer_pairs) keeps a paired HAND_OVER +
# RECEIVE_PROP in IN_TRANSIT until the receive completes it.
# ---------------------------------------------------------------------------


class ForbiddenPropTransition(ValueError):
    """A prop transition the contract table forbids, or a staging
    rest that contradicts the prop's semantic location. Raised
    loudly -- never silently restage."""


# Compiler verb -> semantic action for transition lookup, when the
# event carries no semantic_action_type (legacy/foreign lists).
# PICK_UP is deliberately absent: without a semantic type its source
# (surface / ground / pocket) is ambiguous, so it takes the legacy
# path below instead of a guessed table entry.
_COMPILER_VERB_SEMANTIC = {
    "TAKE_OUT": "TAKE_OUT",
    "PUT_AWAY": "PUT_AWAY",
    "HAND_OVER": "HAND_OVER",
    "KNEEL_PICK": "BEND_PICK",
    "BEND_PICK": "BEND_PICK",
    "RELEASE": "RELEASE_PROP",
    "RECEIVE_PROP": "RECEIVE_PROP",
}

_CONTAINER_OPEN_VERBS = ("OPEN_WALLET", "OPEN")
_CONTAINER_CLOSE_VERBS = ("CLOSE_WALLET", "CLOSE")
_CONTAINER_KINDS = ("wallet", "bag", "cup")
_HOLD_VERBS = ("HOLD", "HOLD_PEN", "WRITE", "SIGN", "HAMMER_STRIKE",
               "CARRY")
_NO_LOCATION_VERBS = _HOLD_VERBS + _CONTAINER_OPEN_VERBS \
    + _CONTAINER_CLOSE_VERBS


class SemanticPropTracker:
    """Per-prop semantic state timelines from compiler events."""

    def __init__(self, props, events):
        if isinstance(props, dict):
            self._props = dict(props)
        else:
            self._props = {}
            for prop in props or []:
                if isinstance(prop, dict):
                    pid = prop.get("id") or prop.get("name")
                    if pid:
                        self._props[pid] = prop
        self.warnings: list[dict] = []
        self.transitions: list[dict] = []
        self._initial: dict = {}
        self._initial_inferred: dict = {}
        self._initial_container: dict = {}
        self._loc_changes: dict = {}
        self._holder_changes: dict = {}
        self._container_changes: dict = {}
        self._build(events or [])

    # -- queries ------------------------------------------------------

    @property
    def prop_ids(self):
        return tuple(self._props)

    def initial_location(self, pid):
        """Semantic location before the first event, or None."""
        return self._initial.get(pid)

    def initial_inferred(self, pid) -> bool:
        return bool(self._initial_inferred.get(pid))

    def location_at(self, pid, t):
        if pid not in self._props:
            raise KeyError(f"unknown prop: {pid!r}")
        loc = self._initial.get(pid)
        for change_t, change_loc in self._loc_changes.get(pid, []):
            if change_t <= float(t):
                loc = change_loc
            else:
                break
        return loc

    def container_at(self, pid, t):
        if pid not in self._props:
            raise KeyError(f"unknown prop: {pid!r}")
        state = self._initial_container.get(
            pid, PropContainer.NOT_APPLICABLE.value)
        for change_t, change_state in self._container_changes.get(
                pid, []):
            if change_t <= float(t):
                state = change_state
            else:
                break
        return state

    def lifecycle_at(self, pid, t):
        if pid not in self._props:
            raise KeyError(f"unknown prop: {pid!r}")
        return PropLifecycle.PRESENT.value

    def holder_at(self, pid, t):
        if pid not in self._props:
            raise KeyError(f"unknown prop: {pid!r}")
        holder = None
        for change_t, change_holder in self._holder_changes.get(
                pid, []):
            if change_t <= float(t):
                holder = change_holder
            else:
                break
        return holder

    def transfer_in_progress(self, pid, t) -> bool:
        return self.location_at(pid, t) == PropLocation.IN_TRANSIT.value

    def ground_rest_allowed(self, pid, t) -> bool:
        """Ground rest requires a DEFINITIVE ON_GROUND location."""
        return prop_may_rest_on_ground(self.location_at(pid, t) or "")

    # -- construction ---------------------------------------------------

    def _warn(self, pid, action_id, issue):
        self.warnings.append({"prop_id": pid, "action_id": action_id,
                              "issue": issue})

    def _set_initial(self, pid, loc, inferred):
        if pid not in self._initial:
            self._initial[pid] = loc
            self._initial_inferred[pid] = inferred

    @staticmethod
    def _infer_from(froms, held_loc):
        """A from-state in ``froms``: the event's held state when it
        is allowed, else HELD_RIGHT-first deterministic fallback."""
        if held_loc in froms:
            return held_loc
        for candidate in ("HELD_RIGHT", "HELD_LEFT", "HELD_BOTH"):
            if candidate in froms:
                return candidate
        return sorted(froms)[0]

    def _build(self, events):
        ordered = sorted(
            (e for e in events if isinstance(e, dict)),
            key=lambda e: (float(e.get("start_time", 0.0)),
                           str(e.get("action_id", ""))))
        paired_ho, paired_recv = _transfer_pairs(ordered)
        by_prop: dict = {}
        for event in ordered:
            pid = event.get("prop_id")
            if pid and pid in self._props:
                by_prop.setdefault(pid, []).append(event)
        for pid, evs in by_prop.items():
            self._build_prop(pid, evs, paired_ho, paired_recv)

    def _build_prop(self, pid, evs, paired_ho, paired_recv):
        kind = str(self._props[pid].get("kind") or "").lower()
        container = (PropContainer.CLOSED.value
                     if kind in _CONTAINER_KINDS
                     else PropContainer.NOT_APPLICABLE.value)
        self._initial_container[pid] = container
        cont_changes: list = []
        loc = None
        definitive = False
        holder = None
        loc_changes: list = []
        holder_changes: list = []
        prev_sem = None
        prev_shot = None
        for event in evs:
            action = event.get("action_type")
            sem = (event.get("semantic_action_type")
                   or _COMPILER_VERB_SEMANTIC.get(action))
            start = float(event.get("start_time", 0.0))
            end = float(event.get("end_time", start))
            dur = max(end - start, 0.0)
            params = ((event.get("required_pose") or {}).get("params")
                      or {})
            hand = params.get("hand", "r")
            if hand not in ("l", "r", "both"):
                hand = "r"
            held_loc = {"l": PropLocation.HELD_LEFT.value,
                        "r": PropLocation.HELD_RIGHT.value,
                        "both": PropLocation.HELD_BOTH.value}[hand]
            actor = event.get("actor_id")
            aid = event.get("action_id")
            shot = event.get("shot_id")
            has_sem = event.get("semantic_action_type") is not None
            if action in _CONTAINER_OPEN_VERBS:
                container = PropContainer.OPEN.value
                cont_changes.append((end, container))
            elif action in _CONTAINER_CLOSE_VERBS:
                container = PropContainer.CLOSED.value
                cont_changes.append((end, container))
            if action in _NO_LOCATION_VERBS:
                if loc is None:
                    loc, definitive = held_loc, False
                    self._set_initial(pid, loc, inferred=True)
                elif loc in (PropLocation.HELD_LEFT.value,
                             PropLocation.HELD_RIGHT.value,
                             PropLocation.HELD_BOTH.value,
                             PropLocation.IN_TRANSIT.value):
                    pass
                elif not definitive:
                    self._warn(pid, aid,
                               f"revised inferred location {loc} to "
                               f"{held_loc} for {action}")
                    loc = held_loc
                elif has_sem:
                    raise ForbiddenPropTransition(
                        f"prop {pid!r}: {action} requires a held prop "
                        f"but its semantic location is {loc} "
                        f"(event {aid})")
                else:
                    self._warn(pid, aid,
                               f"{action} with semantic location "
                               f"{loc} (legacy event, no semantic "
                               f"type); assumed {held_loc}")
                    loc, definitive = held_loc, False
                if holder is None and actor is not None:
                    holder = actor
                    holder_changes.append((start, actor))
                continue
            if sem is None:
                if action == "PICK_UP":
                    sem = "TAKE"  # legacy take: ambiguous source
                else:
                    continue  # verb with no prop-location semantics
            if sem == "TAKE":
                froms = (PropLocation.IN_POCKET.value,
                         PropLocation.ON_SURFACE.value,
                         PropLocation.ON_GROUND.value)
                from_loc, gap = self._resolve(
                    pid, aid, sem, loc, definitive, froms, held_loc,
                    has_sem, prev_sem, prev_shot, shot)
                if from_loc is None:
                    continue
                switch_t = start + PICK_UP_GRASP_U * dur
                loc_changes.append((switch_t, held_loc))
                holder_changes.append((switch_t, actor))
                holder = actor
                self.transitions.append(
                    {"prop_id": pid, "action_id": aid, "action": sem,
                     "from": from_loc, "to": held_loc, "gap": gap})
                loc = held_loc
                definitive = True
                prev_sem, prev_shot = sem, shot
                continue
            froms = tuple(f for (f, a) in PROP_TRANSITIONS
                          if a == sem)
            if not froms:
                # Location-neutral semantic action (LOOK_AT, OPEN
                # as a state verb, ...): the table defines what
                # changes location, and this is not it. Silent --
                # warning here would fire on every gaze.
                continue
            resolved, gap = self._resolve(
                pid, aid, sem, loc, definitive, froms, held_loc,
                has_sem, prev_sem, prev_shot, shot)
            if resolved is None:
                continue
            loc = resolved
            table_to = PROP_TRANSITIONS[(loc, sem)]
            if table_to in (PropLocation.HELD_LEFT.value,
                            PropLocation.HELD_RIGHT.value,
                            PropLocation.HELD_BOTH.value):
                to = held_loc  # the hand comes from the event
            else:
                to = table_to
            if sem in ("TAKE_FROM_POCKET", "TAKE_OUT",
                       "PICK_FROM_SURFACE", "BEND_PICK",
                       "PICK_FROM_GROUND"):
                grasp_u = (KNEEL_PICK_GRASP_U
                           if sem in ("BEND_PICK", "PICK_FROM_GROUND")
                           else PICK_UP_GRASP_U)
                switch_t = start + grasp_u * dur
                loc_changes.append((switch_t, to))
                holder_changes.append((switch_t, actor))
                holder = actor
            elif sem in ("PUT_AWAY", "RELEASE_PROP",
                         "PLACE_ON_SURFACE"):
                switch_t = start + PUT_AWAY_RELEASE_U * dur
                loc_changes.append((switch_t, to))
                holder_changes.append((switch_t, None))
                holder = None
            elif sem in ("HAND_OVER", "GIVE"):
                recv_hand = params.get("receive_hand") or "l"
                comp_hand = {"l": PropLocation.HELD_LEFT.value,
                             "r": PropLocation.HELD_RIGHT.value}.get(
                                 recv_hand, PropLocation.HELD_LEFT.value)
                loc_changes.append((start, PropLocation.IN_TRANSIT.value))
                holder_changes.append((start, None))
                holder = None
                if id(event) not in paired_ho:
                    transfer_t = start + HAND_OVER_TRANSFER_U * dur
                    loc_changes.append((transfer_t, comp_hand))
                    holder_changes.append(
                        (transfer_t, event.get("target_id")))
                    holder = event.get("target_id")
                    to = comp_hand
                else:
                    to = PropLocation.IN_TRANSIT.value
            elif sem == "RECEIVE_PROP":
                recv_hand = params.get("receive_hand") or hand
                comp_hand = {"l": PropLocation.HELD_LEFT.value,
                             "r": PropLocation.HELD_RIGHT.value,
                             "both": PropLocation.HELD_BOTH.value}.get(
                                 recv_hand, PropLocation.HELD_RIGHT.value)
                if id(event) not in paired_recv:
                    self._warn(pid, aid,
                               "RECEIVE_PROP without a preceding "
                               "HAND_OVER/GIVE transfer; giver unknown")
                loc_changes.append((end, comp_hand))
                holder_changes.append((end, actor))
                holder = actor
                to = comp_hand
            self.transitions.append(
                {"prop_id": pid, "action_id": aid, "action": sem,
                 "from": loc, "to": to, "gap": gap})
            loc = to
            definitive = True
            prev_sem, prev_shot = sem, shot
        self._loc_changes[pid] = sorted(loc_changes,
                                        key=lambda c: c[0])
        self._holder_changes[pid] = sorted(holder_changes,
                                           key=lambda c: c[0])
        self._container_changes[pid] = sorted(cont_changes,
                                              key=lambda c: c[0])

    def _resolve(self, pid, aid, sem, loc, definitive, froms,
                 held_loc, has_sem, prev_sem, prev_shot, shot):
        """Resolve the current location against a transition's
        from-states. Returns (location, gap) or (None, False) for a
        tolerated redundant completion. Raises on definitive
        contradictions in semantic-typed events."""
        if loc is None:
            resolved = self._infer_from(froms, held_loc)
            self._set_initial(pid, resolved, inferred=True)
            return resolved, False
        if loc in froms:
            return loc, False
        if not definitive:
            resolved = self._infer_from(froms, held_loc)
            self._warn(pid, aid,
                       f"location gap: assumed {resolved} for {sem} "
                       f"after inferred {loc}")
            return resolved, True
        if (sem == "RECEIVE_PROP" and prev_sem in ("HAND_OVER", "GIVE")
                and prev_shot == shot):
            self._warn(pid, aid,
                       "redundant RECEIVE_PROP completion after a "
                       "HAND_OVER; no state change")
            return None, False
        if has_sem:
            raise ForbiddenPropTransition(
                f"prop {pid!r}: forbidden transition {loc} + {sem} "
                f"(event {aid}); allowed from-states for {sem}: "
                f"{sorted(froms)}")
        resolved = self._infer_from(froms, held_loc)
        self._warn(pid, aid,
                   f"forbidden transition {loc} + {sem} (legacy "
                   f"event, no semantic type); assumed {resolved}")
        return resolved, True


def validate_staging_against_semantics(psm):
    """Staging rest kinds vs semantic initial locations.

    A prop staged on the ground must start ON_GROUND, a
    pocket-anchored rest must start IN_POCKET, a surface rest must
    start ON_SURFACE. Props with no established initial location
    are skipped (never guessed). Raises one ForbiddenPropTransition
    listing EVERY mismatch, so preflight sees them all.
    """
    tracker = psm.semantic_tracker
    want = {"ground": PropLocation.ON_GROUND.value,
            "pocket": PropLocation.IN_POCKET.value,
            "surface": PropLocation.ON_SURFACE.value}
    violations = []
    for pid in tracker.prop_ids:
        kind = psm.rest_kind(pid)
        if kind not in want:
            continue
        initial = tracker.initial_location(pid)
        if initial is not None and initial != want[kind]:
            violations.append(
                f"prop {pid!r}: staging rest kind {kind!r} requires "
                f"initial location {want[kind]}, but the semantic "
                f"timeline starts {initial}")
    if violations:
        raise ForbiddenPropTransition(
            "staging/semantics mismatch: " + "; ".join(violations))
    return []


# ---------------------------------------------------------------------------
# Semantic prop geometry (A2, 2026-11-12; Mai directive §5)
#
# Props are DATA-DRIVEN geometry: each kind has one parametric builder
# returning a spec made of composed polygon / polyline / rect parts, with
# grip, contact and attachment points, material slots, and state-dependent
# geometry. There are no per-story render functions: the same builder
# serves every script that names the kind, and a prop's identity comes
# from the script's prop dict (kind + size + state), never from a story
# branch in this module.
#
# Conventions:
#   * Local coordinates, origin at the GRIP point (where the holding
#     hand wraps the prop), +y down. Rotation is clockwise-positive in
#     screen space (the same convention as bolt_polygon_vertices), so
#     angle 0 is the spec's natural orientation.
#   * A spec is plain data (dicts / tuples / numbers). Colours live in
#     MATERIALS, not in specs: a spec names material slots ("core",
#     "metal", "leather", ...); the material CATALOG is B's
#     (lighting/materials) and is consumed here as a plain dict
#     {slot: material}. A material is {"fill": (r, g, b),
#     "outline": (r, g, b) | None, "width": int, "emissive": bool,
#     "glow_color": (r, g, b) | None, "glow_radius_px": float | None};
#     only "fill" is required. The draw entry point never invents a
#     colour: a missing slot raises MissingMaterialError, unless the
#     caller passes engineering_preview=True (magenta placeholders,
#     recorded in the report).
#   * Unknown MANDATORY prop kinds raise UnsupportedPropError. There is
#     no silent brown-box path: placeholders exist only through the
#     explicit draw_prop_placeholder() helper, for clearly labelled
#     engineering previews.
#   * Glow is DATA here (the "emissive" slot + the energy_glow_at
#     interface above); lighting renders it. This module never draws
#     light.
# ---------------------------------------------------------------------------


class UnsupportedPropError(ValueError):
    """Raised when a mandatory prop kind has no semantic geometry.

    Production paths must surface this, never substitute a box.
    """


class MissingMaterialError(ValueError):
    """Raised when a material slot has no entry in the material catalog
    and the caller did not ask for an engineering preview."""


PLACEHOLDER_MATERIAL = {"fill": (255, 0, 255), "outline": (255, 0, 255),
                        "width": 2}


# The ten prop families (Mai directive §5). Each family lists the kinds
# with builders today; musical_instruments / furniture / everyday_objects
# are taxonomy reserved for future builders -- a kind in those families
# with no builder still raises UnsupportedPropError (loud, not a box).
PROP_FAMILIES = {
    "containers": ("bag", "wallet", "cup"),
    "books": ("book",),
    "paper": ("letter",),
    "writing_instruments": ("pen",),
    "tools": ("hammer", "key", "staff"),
    "clothing_accessories": ("hat", "ring", "helmet", "crown"),
    "mythological_weapons": ("bolt", "trident", "sword", "shield"),
    "stone_and_restraint": ("chain", "stone", "boulder"),
    "musical_instruments": (),
    "furniture": (),
    "everyday_objects": (),
}
PROP_KIND_FAMILY = {kind: family
                    for family, kinds in PROP_FAMILIES.items()
                    for kind in kinds}


def _ellipse_points(cx, cy, rx, ry, n=24):
    return [(cx + rx * math.cos(2.0 * math.pi * i / n),
             cy + ry * math.sin(2.0 * math.pi * i / n))
            for i in range(n)]


def _arc_points(cx, cy, rx, ry, start_deg, end_deg, n=12):
    return [(cx + rx * math.cos(math.radians(
                start_deg + (end_deg - start_deg) * i / n)),
             cy + ry * math.sin(math.radians(
                start_deg + (end_deg - start_deg) * i / n)))
            for i in range(n + 1)]


def _rounded_rect_points(x0, y0, x1, y1, r, n=3):
    """Rounded-rectangle outline as a polygon (+y down)."""
    pts = []
    for cx, cy, a0 in ((x1 - r, y1 - r, 0.0),
                       (x0 + r, y1 - r, 90.0),
                       (x0 + r, y0 + r, 180.0),
                       (x1 - r, y0 + r, 270.0)):
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _part_points(part):
    if part["op"] in ("polygon", "polyline"):
        return list(part["points"])
    if part["op"] == "rect":
        x0, y0, x1, y1 = part["bbox"]
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    raise ValueError(f"unknown part op {part['op']!r}")


def _spec(kind, parts, contact_points, *, attachment_points=None,
          state=None, articulation=None, energy=False, state_params=()):
    pts = [pt for part in parts for pt in _part_points(part)]
    xs = [pt[0] for pt in pts]
    ys = [pt[1] for pt in pts]
    return {
        "kind": kind,
        "family": PROP_KIND_FAMILY[kind],
        "parts": parts,
        "contact_points": dict(contact_points),
        "attachment_points": dict(attachment_points or {}),
        "material_slots": sorted({part["slot"] for part in parts}),
        "bbox": (min(xs), min(ys), max(xs), max(ys)),
        "state": dict(state or {}),
        "articulation": articulation,
        "energy": bool(energy),
        "state_params": list(state_params),
    }


# --- Builders: one per kind. Each is a pure function of its params. ---


def _bolt_spec(length=170.0, segments=4, lit=True):
    """Zeus bolt: the jagged polygon from bolt_shape_spec (single
    source of truth), plus an emissive halo part when lit."""
    base = bolt_shape_spec(length=length, segments=segments)
    verts = base["vertices"]
    cx, cy = base["center"]
    parts = []
    if lit:
        halo = [((x - cx) * 1.35 + cx, (y - cy) * 1.35 + cy)
                for x, y in verts]
        parts.append({"op": "polygon", "name": "halo",
                      "slot": "emissive", "points": halo})
    parts.append({"op": "polygon", "name": "core",
                  "slot": "core", "points": list(verts)})
    return _spec("bolt", parts,
                 {"grip": (0.0, 0.0),
                  "tip_top": base["spine"][0],
                  "tip_bottom": base["spine"][-1],
                  "glow_center": (cx, cy)},
                 state={"lit": bool(lit)}, energy=True,
                 state_params=["lit"])


def _trident_spec(length=210.0, prong_spread=None):
    top = -0.55 * length
    butt = 0.45 * length
    prong_tip = top - 0.26 * length
    side_tip = top - 0.19 * length
    w = 0.03 * length
    s = float(prong_spread) if prong_spread is not None else 0.22 * length
    parts = [
        {"op": "polyline", "name": "shaft", "slot": "shaft",
         "points": [(0.0, top), (0.0, butt)],
         "width": max(3, int(0.03 * length))},
        {"op": "polyline", "name": "crossbar", "slot": "metal",
         "points": [(-s, top), (s, top)],
         "width": max(3, int(0.03 * length))},
        {"op": "polygon", "name": "prong_center", "slot": "metal",
         "points": [(-w, top), (0.0, prong_tip), (w, top)]},
        {"op": "polygon", "name": "prong_left", "slot": "metal",
         "points": [(-s - 6.0, top), (-s * 1.25, side_tip),
                    (-s + 8.0, top)]},
        {"op": "polygon", "name": "prong_right", "slot": "metal",
         "points": [(s + 6.0, top), (s * 1.25, side_tip),
                    (s - 8.0, top)]},
        {"op": "polygon", "name": "butt_knob", "slot": "trim",
         "points": _ellipse_points(0.0, butt, w, w, n=12)},
    ]
    return _spec("trident", parts,
                 {"grip": (0.0, 0.0),
                  "prong_center_tip": (0.0, prong_tip),
                  "prong_left_tip": (-s * 1.25, side_tip),
                  "prong_right_tip": (s * 1.25, side_tip),
                  "butt": (0.0, butt)})


def _helmet_spec(size=120.0):
    r = 0.5 * float(size)
    dome = _arc_points(0.0, 0.0, r, 0.8 * r, 180.0, 360.0, n=16)
    parts = [
        {"op": "polygon", "name": "dome", "slot": "metal",
         "points": dome},
        {"op": "rect", "name": "brim", "slot": "trim",
         "bbox": (-1.1 * r, -2.0, 1.1 * r, 8.0)},
        {"op": "polygon", "name": "nasal", "slot": "metal",
         "points": [(-4.0, 0.0), (4.0, 0.0), (3.0, 0.5 * r),
                    (-3.0, 0.5 * r)]},
        {"op": "polygon", "name": "crest", "slot": "trim",
         "points": [(-0.5 * r, -0.75 * r), (0.0, -1.15 * r),
                    (0.5 * r, -0.75 * r)]},
        {"op": "polygon", "name": "cheek_left", "slot": "metal",
         "points": [(-r, 0.0), (-0.7 * r, 0.0), (-0.75 * r, 0.45 * r),
                    (-0.95 * r, 0.4 * r)]},
        {"op": "polygon", "name": "cheek_right", "slot": "metal",
         "points": [(r, 0.0), (0.7 * r, 0.0), (0.75 * r, 0.45 * r),
                    (0.95 * r, 0.4 * r)]},
    ]
    return _spec("helmet", parts,
                 {"grip": (0.0, 0.0), "crown": (0.0, -0.8 * r)},
                 attachment_points={"head_anchor": (0.0, 0.0)})


def _hammer_spec(H=None, length=None, grip_angle_rad=None, facing=1):
    """Cyclops hammer: handle + head subparts articulated at the grip.
    The strike face is hammer_head_position() (single source of
    truth); the head sits BEHIND the face, up the handle, never
    centred on it. Needs H (fractions) or an explicit handle length.
    """
    if grip_angle_rad is None:
        grip_angle_rad = HAMMER_GRIP_ANGLE_RAD
    if H is not None:
        handle_len = HAMMER_HANDLE_FRAC * float(H)
        half = HAMMER_HEAD_HALF_FRAC * float(H)
        face = hammer_head_position((0.0, 0.0), facing, H,
                                    grip_angle_rad)
    elif length is not None:
        handle_len = float(length)
        half = 0.22 * handle_len
        face = (facing * math.cos(grip_angle_rad) * handle_len,
                math.sin(grip_angle_rad) * handle_len)
    else:
        raise ValueError("hammer geometry needs H or length")
    dx, dy = face[0] / handle_len, face[1] / handle_len
    px, py = -dy, dx
    cx, cy = face[0] - dx * half, face[1] - dy * half
    head = [(cx + sx * px * 1.6 * half + sy * dx * half,
             cy + sx * py * 1.6 * half + sy * dy * half)
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    parts = [
        {"op": "polyline", "name": "handle", "slot": "wood",
         "points": [(0.0, 0.0), face],
         "width": max(3, int(0.35 * half))},
        {"op": "polygon", "name": "head", "slot": "metal",
         "points": head},
    ]
    return _spec("hammer", parts,
                 {"grip": (0.0, 0.0), "strike_face": face},
                 state={"grip_angle_rad": grip_angle_rad},
                 articulation={"joint": (0.0, 0.0),
                               "angle_param": "grip_angle_rad",
                               "angle_rad": grip_angle_rad,
                               "subparts": ["handle", "head"]},
                 state_params=["grip_angle_rad"])


def _wallet_spec(length=110.0, height=70.0, open_u=0.0):
    """Openable wallet: closed it is one rounded body with a clasp;
    opening widens the body around the centre fold and reveals the
    inner card slots + a bill corner. open_u in [0, 1]."""
    open_u = min(1.0, max(0.0, float(open_u)))
    half_l = 0.5 * float(length) * (1.0 + 0.35 * open_u)
    half_h = 0.5 * float(height)
    parts = [
        {"op": "polygon", "name": "body", "slot": "leather",
         "points": _rounded_rect_points(-half_l, -half_h, half_l,
                                        half_h, 10.0)},
        {"op": "polyline", "name": "stitch", "slot": "trim",
         "points": [(-half_l + 6.0, -half_h + 6.0),
                    (half_l - 6.0, -half_h + 6.0),
                    (half_l - 6.0, half_h - 6.0),
                    (-half_l + 6.0, half_h - 6.0)],
         "width": 2, "close": True},
    ]
    if open_u > 0.05:
        parts.append(
            {"op": "polyline", "name": "fold", "slot": "trim",
             "points": [(0.0, -half_h), (0.0, half_h)], "width": 2})
        for i, frac in enumerate((-0.3, 0.3)):
            parts.append(
                {"op": "polyline", "name": f"card_slot_{i + 1}",
                 "slot": "paper",
                 "points": [(-half_l + 10.0, half_h * frac),
                            (-12.0, half_h * frac)], "width": 2})
        parts.append(
            {"op": "polygon", "name": "bill", "slot": "paper",
             "points": [(14.0, -half_h + 8.0), (half_l - 10.0, -half_h + 8.0),
                        (half_l - 10.0, -half_h + 26.0),
                        (14.0, -half_h + 26.0)]})
    else:
        parts.append(
            {"op": "polygon", "name": "clasp", "slot": "trim",
             "points": _ellipse_points(half_l - 12.0, 0.0, 5.0, 5.0,
                                       n=12)})
    return _spec("wallet", parts,
                 {"grip": (0.0, 0.0), "opening": (0.0, -half_h)},
                 state={"open_u": open_u}, state_params=["open_u"])


def _pen_spec(H=None, length=None, facing=1):
    """Writing pen: shaft along PEN_GRIP_ANGLE_RAD (single source of
    truth via pen_tip_position), tip at the far end. Needs H or an
    explicit length."""
    if H is not None:
        length = PEN_LEN_FRAC * float(H)
        tip = pen_tip_position((0.0, 0.0), facing, H)
    elif length is not None:
        length = float(length)
        tip = (facing * math.cos(PEN_GRIP_ANGLE_RAD) * length,
               math.sin(PEN_GRIP_ANGLE_RAD) * length)
    else:
        raise ValueError("pen geometry needs H or length")
    dx, dy = tip[0] / length, tip[1] / length
    px, py = -dy, dx
    base = (tip[0] - dx * 0.15 * length, tip[1] - dy * 0.15 * length)
    parts = [
        {"op": "polyline", "name": "shaft", "slot": "body",
         "points": [(0.0, 0.0), tip],
         "width": max(2, int(0.08 * length))},
        {"op": "polygon", "name": "tip", "slot": "tip",
         "points": [(base[0] - px * 0.05 * length,
                     base[1] - py * 0.05 * length),
                    (base[0] + px * 0.05 * length,
                     base[1] + py * 0.05 * length),
                    tip]},
        {"op": "polyline", "name": "clip", "slot": "trim",
         "points": [(dx * 0.1 * length + px * 0.06 * length,
                     dy * 0.1 * length + py * 0.06 * length),
                    (dx * 0.35 * length + px * 0.06 * length,
                     dy * 0.35 * length + py * 0.06 * length)],
         "width": 2},
    ]
    return _spec("pen", parts,
                 {"grip": (0.0, 0.0), "tip": tip})


def _letter_spec(width=120.0, height=80.0):
    w, h = 0.5 * float(width), 0.5 * float(height)
    parts = [
        {"op": "rect", "name": "paper", "slot": "paper",
         "bbox": (-w, -h, w, h)},
        {"op": "polyline", "name": "fold", "slot": "edge",
         "points": [(0.0, -h), (0.0, h)], "width": 1},
        {"op": "polyline", "name": "text_line_1", "slot": "ink",
         "points": [(-w + 12.0, -h * 0.5), (w - 12.0, -h * 0.5)],
         "width": 2},
        {"op": "polyline", "name": "text_line_2", "slot": "ink",
         "points": [(-w + 12.0, 0.0), (w - 20.0, 0.0)], "width": 2},
        {"op": "polyline", "name": "text_line_3", "slot": "ink",
         "points": [(-w + 12.0, h * 0.5), (w - 30.0, h * 0.5)],
         "width": 2},
    ]
    return _spec("letter", parts, {"grip": (0.0, 0.0)})


def _book_spec(width=100.0, height=140.0, thickness=14.0):
    w, h = 0.5 * float(width), 0.5 * float(height)
    parts = [
        {"op": "rect", "name": "cover", "slot": "cover",
         "bbox": (-w, -h, w, h)},
        {"op": "rect", "name": "pages", "slot": "paper",
         "bbox": (-w + 4.0, -h + 4.0, w - 2.0, h - 4.0)},
        {"op": "polyline", "name": "spine", "slot": "trim",
         "points": [(-w + 2.0, -h), (-w + 2.0, h)], "width": 3},
    ]
    return _spec("book", parts, {"grip": (0.0, 0.0)})


def _bag_spec(width=110.0, height=130.0):
    w, h = 0.5 * float(width), 0.5 * float(height)
    # Origin at the grip (top of the handle); the body hangs below.
    dy = h + 0.2 * float(height)
    parts = [
        {"op": "polygon", "name": "body", "slot": "fabric",
         "points": [(-w, -h + 10.0 + dy), (w, -h + 10.0 + dy),
                    (w - 8.0, h + dy), (-w + 8.0, h + dy)]},
        {"op": "polyline", "name": "handle", "slot": "trim",
         "points": _arc_points(0.0, -h + 10.0 + dy,
                               0.3 * float(width),
                               0.25 * float(height), 180.0, 360.0),
         "width": 4},
        {"op": "polygon", "name": "flap", "slot": "trim",
         "points": [(-w + 6.0, -h + 10.0 + dy),
                    (w - 6.0, -h + 10.0 + dy),
                    (w - 14.0, -h + 44.0 + dy),
                    (-w + 14.0, -h + 44.0 + dy)]},
    ]
    return _spec("bag", parts, {"grip": (0.0, 0.0)})


def _sword_spec(length=200.0):
    L = float(length)
    w = 0.035 * L
    parts = [
        {"op": "polygon", "name": "blade", "slot": "metal",
         "points": [(-w, -0.12 * L), (0.0, -0.85 * L),
                    (w, -0.12 * L)]},
        {"op": "rect", "name": "guard", "slot": "trim",
         "bbox": (-0.16 * L, -0.14 * L, 0.16 * L, -0.08 * L)},
        {"op": "polyline", "name": "grip", "slot": "wood",
         "points": [(0.0, -0.08 * L), (0.0, 0.08 * L)],
         "width": max(3, int(0.04 * L))},
        {"op": "polygon", "name": "pommel", "slot": "trim",
         "points": _ellipse_points(0.0, 0.1 * L, 0.04 * L, 0.04 * L,
                                   n=12)},
    ]
    return _spec("sword", parts,
                 {"grip": (0.0, 0.0), "tip": (0.0, -0.85 * L)})


def _staff_spec(length=240.0):
    L = float(length)
    parts = [
        {"op": "polyline", "name": "shaft", "slot": "wood",
         "points": [(0.0, -0.6 * L), (0.0, 0.4 * L)],
         "width": max(3, int(0.025 * L))},
        {"op": "polygon", "name": "knob", "slot": "trim",
         "points": _ellipse_points(0.0, -0.62 * L, 0.04 * L, 0.04 * L,
                                   n=12)},
        {"op": "polygon", "name": "tip", "slot": "metal",
         "points": [(-0.02 * L, 0.4 * L), (0.02 * L, 0.4 * L),
                    (0.0, 0.46 * L)]},
    ]
    return _spec("staff", parts,
                 {"grip": (0.0, 0.0), "tip": (0.0, 0.46 * L)})


def _shield_spec(width=110.0, height=140.0):
    w, h = 0.5 * float(width), 0.5 * float(height)
    parts = [
        {"op": "polygon", "name": "face", "slot": "metal",
         "points": [(-w, -h), (w, -h), (w, 0.0), (0.0, h), (-w, 0.0)]},
        {"op": "polygon", "name": "boss", "slot": "trim",
         "points": _ellipse_points(0.0, -0.1 * float(height),
                                   0.14 * float(width),
                                   0.14 * float(width), n=16)},
    ]
    return _spec("shield", parts, {"grip": (0.0, 0.0)},
                 attachment_points={"forearm": (0.0, 0.0)})


def _crown_spec(width=110.0, height=60.0):
    w = 0.5 * float(width)
    h = float(height)
    parts = [
        {"op": "rect", "name": "band", "slot": "metal",
         "bbox": (-w, -0.2 * h, w, 0.2 * h)},
    ]
    for cx in (-w * 2.0 / 3.0, 0.0, w * 2.0 / 3.0):
        parts.append(
            {"op": "polygon", "name": "spike", "slot": "metal",
             "points": [(cx - 0.14 * w, -0.2 * h), (cx, -h),
                        (cx + 0.14 * w, -0.2 * h)]})
        parts.append(
            {"op": "polygon", "name": "jewel", "slot": "jewel",
             "points": _ellipse_points(cx, 0.0, 5.0, 5.0, n=10)})
    return _spec("crown", parts, {"grip": (0.0, 0.0)},
                 attachment_points={"head_anchor": (0.0, 0.2 * h)})


def _ring_spec(radius=16.0):
    r = float(radius)
    parts = [
        {"op": "polyline", "name": "band", "slot": "metal",
         "points": _ellipse_points(0.0, 0.0, r, r, n=20),
         "width": 5, "close": True},
        {"op": "polygon", "name": "jewel", "slot": "jewel",
         "points": _ellipse_points(0.0, -r, 5.0, 5.0, n=10)},
    ]
    return _spec("ring", parts, {"grip": (0.0, 0.0)})


def _hat_spec(width=130.0, height=70.0):
    w = 0.5 * float(width)
    h = float(height)
    parts = [
        {"op": "polygon", "name": "brim", "slot": "fabric",
         "points": _ellipse_points(0.0, 0.3 * h, w, 0.18 * h, n=24)},
        {"op": "rect", "name": "crown", "slot": "fabric",
         "bbox": (-0.3 * float(width), -0.7 * h,
                  0.3 * float(width), 0.3 * h)},
        {"op": "polyline", "name": "band", "slot": "trim",
         "points": [(-0.3 * float(width), 0.1 * h),
                    (0.3 * float(width), 0.1 * h)], "width": 4},
    ]
    return _spec("hat", parts, {"grip": (0.0, 0.0)},
                 attachment_points={"head_anchor": (0.0, 0.3 * h)})


def _cup_spec(width=70.0, height=90.0):
    w, h = 0.5 * float(width), 0.5 * float(height)
    # Origin at the grip (the handle); the body sits to the left.
    dx = w + 10.0
    parts = [
        {"op": "polygon", "name": "body", "slot": "body",
         "points": [(-w - dx, -h), (w - dx, -h), (w - 8.0 - dx, h),
                    (-w + 8.0 - dx, h)]},
        {"op": "polyline", "name": "rim", "slot": "trim",
         "points": [(-w - dx, -h), (w - dx, -h)], "width": 3},
        {"op": "polyline", "name": "handle", "slot": "body",
         "points": _arc_points(w - dx, 0.0, 14.0,
                               0.3 * float(height),
                               -60.0, 60.0, n=10), "width": 4},
    ]
    return _spec("cup", parts, {"grip": (0.0, 0.0)})


def _key_spec(length=70.0):
    L = float(length)
    # Origin at the grip (the bow); the shaft hangs below.
    dy = 0.3 * L
    parts = [
        {"op": "polyline", "name": "bow", "slot": "metal",
         "points": _ellipse_points(0.0, 0.0, 0.18 * L, 0.18 * L,
                                   n=16), "width": 4, "close": True},
        {"op": "polyline", "name": "shaft", "slot": "metal",
         "points": [(0.0, -0.15 * L + dy), (0.0, 0.4 * L + dy)],
         "width": 5},
        {"op": "rect", "name": "tooth_1", "slot": "metal",
         "bbox": (0.0, 0.2 * L + dy, 0.17 * L, 0.26 * L + dy)},
        {"op": "rect", "name": "tooth_2", "slot": "metal",
         "bbox": (0.0, 0.3 * L + dy, 0.13 * L, 0.36 * L + dy)},
    ]
    return _spec("key", parts,
                 {"grip": (0.0, 0.0), "tip": (0.0, 0.4 * L + dy)})


def _chain_spec(length=180.0, links=6):
    """Prison chain: interlocking oval links hanging from the grip.

    Origin at the top link (the held end); links alternate a small
    x offset so the interlock reads. Deterministic: no RNG.
    """
    n = max(1, int(links))
    pitch = float(length) / n
    rx, ry = 0.34 * pitch, 0.58 * pitch
    parts = []
    for i in range(n):
        cx = (0.10 * pitch) if i % 2 == 0 else (-0.10 * pitch)
        cy = i * pitch * 0.82
        parts.append(
            {"op": "polyline", "name": f"link_{i + 1}", "slot": "metal",
             "points": _ellipse_points(cx, cy, rx, ry, n=14),
             "width": 4, "close": True})
    end_y = (n - 1) * pitch * 0.82
    return _spec("chain", parts,
                 {"grip": (0.0, 0.0),
                  "end": (0.10 * pitch if (n - 1) % 2 == 0
                          else -0.10 * pitch, end_y)},
                 state={"links": n})


# Fixed radius multipliers: irregular but deterministic outlines.
# No RNG anywhere in prop geometry (reproducible renders).
_STONE_RADII = (1.00, 0.84, 0.93, 0.78, 0.90, 0.82, 0.95, 0.87)
_BOULDER_RADII = (1.00, 0.88, 0.95, 0.80, 0.92, 0.85, 0.97, 0.83,
                  0.90, 0.86)


def _rock_outline(size, radii):
    r = 0.5 * float(size)
    n = len(radii)
    return [(r * m * math.cos(2.0 * math.pi * i / n - math.pi / 2.0),
             r * m * math.sin(2.0 * math.pi * i / n - math.pi / 2.0))
            for i, m in enumerate(radii)]


def _stone_spec(size=90.0, wrapped=False):
    """Carried stone: irregular rounded body, origin at the centre
    (the grip for a held rock). ``wrapped`` adds the swaddling-cloth
    bands (Rhea's stone) as cloth parts. Ground rest uses ``bottom``.
    """
    r = 0.5 * float(size)
    parts = [
        {"op": "polygon", "name": "body", "slot": "stone",
         "points": _rock_outline(size, _STONE_RADII)},
        {"op": "polyline", "name": "crack", "slot": "stone",
         "points": [(-0.35 * r, -0.45 * r), (-0.1 * r, -0.1 * r),
                    (-0.3 * r, 0.35 * r)], "width": 2},
    ]
    if wrapped:
        parts.extend([
            {"op": "polyline", "name": "cloth_band_v", "slot": "cloth",
             "points": [(-0.12 * r, -0.92 * r), (-0.12 * r, 0.92 * r)],
             "width": 6},
            {"op": "polyline", "name": "cloth_band_h", "slot": "cloth",
             "points": [(-0.92 * r, 0.1 * r), (0.92 * r, 0.1 * r)],
             "width": 6},
        ])
    return _spec("stone", parts,
                 {"grip": (0.0, 0.0), "top": (0.0, -r),
                  "bottom": (0.0, r), "left": (-r, 0.0),
                  "right": (r, 0.0)},
                 state={"wrapped": bool(wrapped)},
                 state_params=["wrapped"])


def _boulder_spec(size=170.0):
    """Hurled/lifted boulder: larger irregular body with facet lines.
    Origin at the centre (the grip for a two-handed lift)."""
    r = 0.5 * float(size)
    parts = [
        {"op": "polygon", "name": "body", "slot": "stone",
         "points": _rock_outline(size, _BOULDER_RADII)},
        {"op": "polyline", "name": "facet_1", "slot": "stone",
         "points": [(-0.6 * r, -0.5 * r), (0.1 * r, -0.1 * r),
                    (0.55 * r, 0.45 * r)], "width": 2},
        {"op": "polyline", "name": "facet_2", "slot": "stone",
         "points": [(0.5 * r, -0.55 * r), (0.25 * r, 0.0)],
         "width": 2},
    ]
    return _spec("boulder", parts,
                 {"grip": (0.0, 0.0), "top": (0.0, -r),
                  "bottom": (0.0, r), "left": (-r, 0.0),
                  "right": (r, 0.0)})


# Kind inference for props whose adapter kind is "generic" (the
# adapter's unresolved-kind fallback): the kind is recovered from
# the prop's OWN name/description/id text, longest phrase wins,
# and the inference is recorded on the spec (kind_inferred) --
# never silent. An explicit non-generic kind is authoritative: an
# unknown explicit kind raises, it is never inferred over. This
# table is the geometry twin of the compiler's PROP_KIND_NOUNS;
# the drift guard in test_semantic_props pins the two together
# (deliberate deltas: bare "túi" and "glass" are excluded here --
# "túi" is the pocket word, "glass" is ambiguous).
_KIND_INFERENCE_NOUNS: dict[str, tuple[str, ...]] = {
    "bolt": ("tia chớp", "tia sét", "lightning", "bolt"),
    "hammer": ("búa", "hammer"),
    "trident": ("đinh ba", "trident"),
    "helmet": ("mũ sắt", "mũ tàng hình", "helmet"),
    "sword": ("kiếm", "sword"),
    "shield": ("khiên", "shield"),
    "crown": ("vương miện", "crown"),
    "ring": ("nhẫn", "ring"),
    "hat": ("mũ", "hat"),
    "wallet": ("ví", "bóp", "wallet", "purse"),
    "pen": ("bút", "pen"),
    "letter": ("tài liệu", "thư", "đơn", "giấy", "letter",
               "document", "paper"),
    "book": ("sách", "vở", "notebook", "book"),
    "bag": ("túi hành quân", "ba lô", "cặp sách", "backpack",
            "bag"),
    "cup": ("cốc", "ly", "chén", "cup"),
    "key": ("chìa khóa", "key"),
    "staff": ("quyền trượng", "gậy", "scepter", "staff"),
    "chain": ("dây xích", "xích", "chain", "shackle"),
    "stone": ("hòn đá", "viên đá", "stone", "pebble"),
    "boulder": ("tảng đá", "boulder", "mountain rock", "giant rock"),
}


def _infer_kind(prop: dict):
    """(kind, record) from the prop's own text, or (None, None).

    Longest matching phrase wins; ties break by field order
    (name, description, id). Only used when the declared kind is
    missing or "generic".
    """
    best = None  # (length, field_order, kind, noun, field)
    for order, field in enumerate(("name", "description", "id")):
        text = str(prop.get(field) or "").lower().replace("_", " ")
        if not text.strip():
            continue
        for kind, nouns in _KIND_INFERENCE_NOUNS.items():
            for noun in nouns:
                if re.search(r"(?<!\w)" + re.escape(noun) + r"(?!\w)",
                             text):
                    cand = (len(noun), -order, kind, noun, field)
                    if best is None or cand[:2] > best[:2]:
                        best = cand
    if best is None:
        return None, None
    _length, _order, kind, noun, field = best
    return kind, {"token": noun, "field": field,
                  "declared_kind": str(prop.get("kind") or "")}


PROP_GEOMETRY_BUILDERS = {
    "bolt": _bolt_spec,
    "trident": _trident_spec,
    "helmet": _helmet_spec,
    "hammer": _hammer_spec,
    "wallet": _wallet_spec,
    "pen": _pen_spec,
    "letter": _letter_spec,
    "book": _book_spec,
    "bag": _bag_spec,
    "sword": _sword_spec,
    "staff": _staff_spec,
    "shield": _shield_spec,
    "crown": _crown_spec,
    "ring": _ring_spec,
    "hat": _hat_spec,
    "cup": _cup_spec,
    "key": _key_spec,
    "chain": _chain_spec,
    "stone": _stone_spec,
    "boulder": _boulder_spec,
}


def geometry_for_prop(prop, *, H=None, state=None, **overrides):
    """Build the semantic geometry spec for one script prop dict.

    ``prop`` carries at least ``kind`` (and optionally ``id``,
    ``length_px`` / ``width_px`` / ``height_px`` / ``size_px``,
    ``energy``). ``state`` carries state params (``open_u`` for the
    wallet, ``lit`` for the bolt, ``grip_angle_rad`` for the hammer).
    ``H`` supplies the character height the H-relative kinds (pen,
    hammer) are sized from. Unknown kinds raise UnsupportedPropError;
    params a builder does not accept are listed on the spec as
    ``ignored_params`` (visible, never silently dropped into a
    different shape).
    """
    prop = prop or {}
    kind = str(prop.get("kind") or "").strip().lower()
    builder = PROP_GEOMETRY_BUILDERS.get(kind)
    inferred = None
    if builder is None and kind in ("", "generic"):
        # The adapter's unresolved-kind fallback: recover the
        # kind from the prop's own text, recorded on the spec.
        kind, inferred = _infer_kind(prop)
        builder = PROP_GEOMETRY_BUILDERS.get(kind) if kind else None
    if builder is None:
        shown = kind if kind else str(prop.get("kind") or "")
        raise UnsupportedPropError(
            f"no semantic geometry for prop kind {shown!r} "
            f"(prop id {prop.get('id')!r}); known kinds: "
            + ", ".join(sorted(PROP_GEOMETRY_BUILDERS)))
    kwargs = dict(overrides)
    if H is not None:
        kwargs.setdefault("H", H)
    for prop_key, arg in (("length_px", "length"),
                          ("width_px", "width"),
                          ("height_px", "height"),
                          ("size_px", "size")):
        if prop.get(prop_key) is not None:
            kwargs.setdefault(arg, prop[prop_key])
    for key, value in (state or {}).items():
        kwargs.setdefault(key, value)
    if kind == "bolt" and "lit" not in kwargs and prop.get("energy"):
        kwargs["lit"] = True
    allowed = set(inspect.signature(builder).parameters)
    dropped = sorted(set(kwargs) - allowed)
    spec = builder(**{k: v for k, v in kwargs.items() if k in allowed})
    if dropped:
        spec["ignored_params"] = dropped
    spec["prop_id"] = prop.get("id")
    spec["kind_inferred"] = inferred
    return spec


def default_energy_spec(kind) -> dict | None:
    """Default ``energy`` spec for a prop kind, or None.

    A kind carries energy when its geometry spec has a part in the
    ``emissive`` slot (today: only the bolt's halo). The colour is
    the emissive slot's colour; radius_px / ramp_sec fall back to
    the state machine's defaults. Kinds without geometry, or
    whose geometry cannot be probed with neutral dimensions,
    carry no energy -- never guessed. An explicit ``energy``
    entry on a prop dict always wins over this default.
    """
    kind = str(kind or "").strip().lower()
    if not kind:
        return None
    try:
        spec = geometry_for_prop(
            {"kind": kind, "length_px": 200.0, "size_px": 170.0})
    except Exception:  # noqa: BLE001 - unprobable kind: no energy
        return None
    for part in spec.get("parts", []):
        if part.get("slot") == "emissive":
            return {"color": EMISSIVE_SLOT_COLOR}
    return None


def resolve_materials(spec, catalog, *, engineering_preview=False):
    """Resolve a spec's material slots against a material catalog.

    Returns (resolved, missing): resolved is {slot: material}, missing
    is the list of slots the catalog did not supply. A missing slot
    raises MissingMaterialError unless engineering_preview is True,
    in which case it resolves to the magenta placeholder material and
    is reported in ``missing``.
    """
    catalog = catalog or {}
    resolved = {}
    missing = []
    for slot in spec["material_slots"]:
        mat = catalog.get(slot)
        if not isinstance(mat, dict) or "fill" not in mat:
            missing.append(slot)
            if engineering_preview:
                resolved[slot] = dict(PLACEHOLDER_MATERIAL)
            continue
        resolved[slot] = mat
    if missing and not engineering_preview:
        raise MissingMaterialError(
            f"prop kind {spec['kind']!r} needs material slots "
            f"{missing}, not present in the material catalog")
    return resolved, missing


def _rotate_point(pt, cos_t, sin_t):
    return (pt[0] * cos_t - pt[1] * sin_t,
            pt[0] * sin_t + pt[1] * cos_t)


def spec_world_bbox(spec, x, y, angle_deg=0.0):
    """World-space bbox of a spec placed with its grip at (x, y)."""
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    pts = [_rotate_point(pt, cos_t, sin_t)
           for part in spec["parts"] for pt in _part_points(part)]
    xs = [pt[0] + x for pt in pts]
    ys = [pt[1] + y for pt in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def spec_world_contact_points(spec, x, y, angle_deg=0.0):
    """World-space contact/attachment points of a placed spec."""
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    out = {}
    for name, pt in spec["contact_points"].items():
        wx, wy = _rotate_point(pt, cos_t, sin_t)
        out[name] = (wx + x, wy + y)
    for name, pt in spec["attachment_points"].items():
        wx, wy = _rotate_point(pt, cos_t, sin_t)
        out[name] = (wx + x, wy + y)
    return out


def draw_prop_geometry(draw, spec, x, y, angle_deg=0.0, materials=None,
                       *, engineering_preview=False):
    """Draw a geometry spec on a PIL ImageDraw at grip position (x, y).

    ``materials`` is the catalog ({slot: material}) or a dict already
    resolved by resolve_materials; missing slots raise
    MissingMaterialError unless engineering_preview is True. Returns a
    report {"kind", "parts_drawn", "placeholders", "bbox", "prop_id"}:
    "placeholders" lists every slot drawn with the placeholder
    material, and in preview mode the bbox is crossed in magenta so a
    placeholder is unmistakable on the image itself.
    """
    resolved, missing = resolve_materials(
        spec, materials, engineering_preview=engineering_preview)
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    def world(pt):
        wx, wy = _rotate_point(pt, cos_t, sin_t)
        return (wx + x, wy + y)

    drawn = 0
    for part in spec["parts"]:
        mat = resolved[part["slot"]]
        fill = mat["fill"]
        outline = mat.get("outline")
        width = int(mat.get("width", 1))
        if part["op"] == "polygon":
            pts = [world(pt) for pt in part["points"]]
            draw.polygon(pts, fill=fill)
            if outline is not None:
                draw.line(pts + [pts[0]], fill=outline, width=width,
                          joint="curve")
        elif part["op"] == "polyline":
            pts = [world(pt) for pt in part["points"]]
            if part.get("close"):
                pts.append(pts[0])
            draw.line(pts, fill=outline if outline is not None else fill,
                      width=int(part.get("width", width)),
                      joint="curve")
        elif part["op"] == "rect":
            corners = [world(pt) for pt in _part_points(part)]
            draw.polygon(corners, fill=fill)
            if outline is not None:
                draw.line(corners + [corners[0]], fill=outline,
                          width=width, joint="curve")
        else:
            raise ValueError(f"unknown part op {part['op']!r}")
        drawn += 1
    bbox = spec_world_bbox(spec, x, y, angle_deg)
    if missing and engineering_preview:
        magenta = PLACEHOLDER_MATERIAL["fill"]
        draw.rectangle(bbox, outline=magenta, width=2)
        draw.line([bbox[0], bbox[1], bbox[2], bbox[3]], fill=magenta,
                  width=2)
        draw.line([bbox[2], bbox[1], bbox[0], bbox[3]], fill=magenta,
                  width=2)
    return {"kind": spec["kind"], "parts_drawn": drawn,
            "placeholders": missing, "bbox": bbox,
            "prop_id": spec.get("prop_id")}


def draw_prop_placeholder(draw, x, y, size=60.0, *,
                          engineering_preview=False):
    """Draw an explicit labelled placeholder (magenta box + cross).

    Only for engineering previews: the caller must pass
    engineering_preview=True, or this raises. Production paths must
    raise UnsupportedPropError instead -- never call this.
    """
    if not engineering_preview:
        raise ValueError(
            "draw_prop_placeholder requires engineering_preview=True; "
            "production paths must raise UnsupportedPropError instead")
    half = 0.5 * float(size)
    bbox = (x - half, y - half, x + half, y + half)
    magenta = PLACEHOLDER_MATERIAL["fill"]
    draw.rectangle(bbox, fill=None, outline=magenta, width=3)
    draw.line([bbox[0], bbox[1], bbox[2], bbox[3]], fill=magenta,
              width=2)
    draw.line([bbox[2], bbox[1], bbox[0], bbox[3]], fill=magenta,
              width=2)
    return {"placeholder": True, "bbox": bbox}
