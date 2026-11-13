"""Whole-sequence prop contact audit (integration sprint P1, sec 10).

A single-frame gap (the 2.69 px Test F figure) is not evidence of
a correct grip. This audit measures every prop interaction across
its WHOLE span, from the renderer's grip telemetry
(motion_report.json shot "grip_telemetry": per-frame hand joints +
prop draws in staging-plane pixels):

* grip-point distance (wrist joint -> prop anchor) per frame,
  normalized by hand size (finger length = 0.07 * character H);
* prop (machine) angle stability and forearm angle range;
* grip-pose engagement: the fraction of hold frames where the
  grip fan was repainted over the prop;
* geometry penetration: finger STROKE segments (wrist -> tip,
  sampled) tested against the drawn prop spec's polygons/
  polylines -- for geometry kinds only; legacy kinds get a
  footprint-bbox test, labelled approximate. Endpoint-only
  testing reads 0.0 on real held spans (the strokes cross thin
  shapes near the grip and end past them; measured on the Zeus
  re-render: endpoints 0.0, strokes 1.0);
* contact continuity: the prop stays drawn and attached across
  the span (visibility fraction, duplicate draws);
* ownership transition timing: the frame the holder switches,
  against the HAND_OVER/RECEIVE span. Gap and penetration are
  measured ONLY on held-state frames (GRASPED / ATTACHED_TO_HAND
  / IN_USE): a TRANSFERRED prop is in flight between hands, and
  its distance to either hand is transit, not grip -- the
  transition check carries the handover verdict;
* wallet open/close: the open_u series across OPEN/CLOSE spans.

Honesty limits, stated plainly. The hand is THREE finger strokes
fanning from the wrist (_draw_hand); grip modes vary length and
spread only, never topology. There is NO individual finger
articulation in this rig, and this audit never claims otherwise:
it verifies the grip POSE engages (fan repainted, finger strokes
crossing the shape), not finger articulation. The machine angle is
recorded but NOT rendered by the 2D draw path (props draw
axis-aligned); angle metrics are machine-consistency checks.
Penetration is measured against the spec the renderer drew, not
against rendered pixels -- a pixel-level check would need the
frame images and is not attempted here.

Thresholds are starting values, to be calibrated on the Zeus and
Ep1 re-renders; the audit is a non-gating report (stage 13e) so
a threshold miss is visible evidence, never a silent pass.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .prop_system import geometry_for_prop

AUDIT_VERSION = 1

INTERACTION_TYPES = frozenset({
    "HAND_OVER", "RECEIVE_PROP", "HOLD", "CARRY", "GIVE", "TAKE",
    "TAKE_OUT", "TAKE_FROM_POCKET", "PICK_FROM_GROUND", "BEND_PICK",
    "HAMMER_STRIKE", "PLACE_ON_SURFACE", "RELEASE_PROP", "PUT_AWAY",
    "OPEN", "CLOSE",
})

GEOMETRY_KINDS = frozenset({
    "bolt", "hammer", "trident", "helmet", "sword", "staff",
    "shield", "crown", "ring", "hat", "chain", "stone", "boulder",
})

FINGER_LEN_FRAC = 0.07
FOOTPRINT_W, FOOTPRINT_H = 76.0, 50.0
PENETRATION_TOL_PX = 4.0

# States where the prop is in a hand: gap and penetration are
# measurable. TRANSFERRED (in flight) and rest states are not.
HELD_CONTACT_STATES = ("GRASPED", "ATTACHED_TO_HAND", "IN_USE")

# Starting thresholds (see the module docstring).
GAP_NORM_LIMIT = 2.0
GAP_FRAME_FRACTION = 0.95
GRIP_REPAINT_MIN = 0.9
VISIBILITY_MIN = 0.95
HOLDER_MATCH_MIN = 0.95
PENETRATION_MIN = 0.5
HOLD_ANGLE_RANGE_MAX = 30.0
TRANSITION_LATE_TOL_SEC = 0.25


def _load(job_dir: Path, name: str):
    path = job_dir / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _point_in_polygon(pt, polygon) -> bool:
    x, y = pt
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and \
                x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _point_segment_distance(pt, a, b) -> float:
    px, py = pt
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy)
                     / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _spec_shapes(kind):
    """Mapped-shape helpers for one geometry kind, in the same
    construction the renderer uses (natural size -> (76, 50)
    footprint, grip contact at the origin). Returns (polygons,
    polylines, rects, bbox) in footprint-local coords with the
    grip point at (0, 0)."""
    spec = geometry_for_prop(
        {"kind": kind, "length_px": 200.0, "size_px": 170.0})
    x0, y0, x1, y1 = spec["bbox"]
    bw, bh = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    scale = min(FOOTPRINT_W / bw, FOOTPRINT_H / bh)
    gx, gy = spec["contact_points"]["grip"]

    def _map(pt):
        return ((pt[0] - gx) * scale, (pt[1] - gy) * scale)

    polygons, polylines, rects = [], [], []
    for part in spec["parts"]:
        if part["op"] == "polygon":
            polygons.append([_map(p) for p in part["points"]])
        elif part["op"] == "polyline":
            polylines.append([_map(p) for p in part["points"]])
        elif part["op"] == "rect":
            rx0, ry0, rx1, ry1 = part["bbox"]
            ax, ay = _map((rx0, ry0))
            bx, by = _map((rx1, ry1))
            rects.append((min(ax, bx), min(ay, by),
                          max(ax, bx), max(ay, by)))
    bbox = (_map((x0, y0))[0], _map((x0, y0))[1],
            _map((x1, y1))[0], _map((x1, y1))[1])
    return polygons, polylines, rects, bbox


def _fingertip_on_shape(tip, shapes) -> bool:
    polygons, polylines, rects, _bbox = shapes
    for polygon in polygons:
        if _point_in_polygon(tip, polygon):
            return True
    for polyline in polylines:
        for a, b in zip(polyline, polyline[1:]):
            if _point_segment_distance(tip, a, b) \
                    <= PENETRATION_TOL_PX:
                return True
    for rx0, ry0, rx1, ry1 in rects:
        if rx0 - PENETRATION_TOL_PX <= tip[0] <= \
                rx1 + PENETRATION_TOL_PX and \
                ry0 - PENETRATION_TOL_PX <= tip[1] <= \
                ry1 + PENETRATION_TOL_PX:
            return True
    return False


def _stroke_hits_shape(p0, p1, shapes, bbox) -> bool:
    """True when the segment p0->p1 touches the drawn shape.

    ``shapes`` is a _spec_shapes tuple for geometry kinds (bbox
    ignored); otherwise ``bbox`` is the (hw, hh) footprint
    half-extents for the legacy approximate test. Samples every
    ~2 px along the segment.
    """
    dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    steps = max(2, int(dist / 2.0))
    for k in range(steps + 1):
        u = k / steps
        pt = (p0[0] + (p1[0] - p0[0]) * u,
              p0[1] + (p1[1] - p0[1]) * u)
        if shapes is not None:
            if _fingertip_on_shape(pt, shapes):
                return True
        else:
            hw, hh = bbox
            if -hw <= pt[0] <= hw and -hh <= pt[1] <= hh:
                return True
    return False


def _finger_tips(hand, elbow, hand_size):
    """Grip-fan fingertip positions: three short strokes (0.55x)
    fanning +-0.22 rad around the forearm direction. Mirrors
    _finger_geometry(grip='grip') exactly."""
    dx, dy = hand[0] - elbow[0], hand[1] - elbow[1]
    if math.hypot(dx, dy) < 1e-6:
        dx, dy = 0.0, 1.0
    base = math.atan2(dy, dx)
    length = hand_size * 0.55
    return [(hand[0] + math.cos(base + off) * length,
             hand[1] + math.sin(base + off) * length)
            for off in (-0.22, 0.0, 0.22)]


def _forearm_angle(hand, elbow):
    return math.degrees(math.atan2(hand[1] - elbow[1],
                                   hand[0] - elbow[0]))


def audit_prop_contact(job_dir) -> dict:
    """Audit every prop interaction in one job directory."""
    job_dir = Path(job_dir)
    motion = _load(job_dir, "frames/motion_report.json") or {}
    action_data = _load(job_dir, "action_events.json") or {}
    package = _load(job_dir, "scene_package.json") or {}

    id_to_name = {}
    for char in package.get("v1_characters") or []:
        if char.get("id") and char.get("name"):
            id_to_name[char["id"]] = char["name"]
    for char in package.get("characters") or []:
        cid = char.get("id") or char.get("character_id")
        if cid and char.get("name"):
            id_to_name.setdefault(cid, char["name"])
    prop_kinds = {}
    for prop in package.get("props") or []:
        if prop.get("id"):
            prop_kinds[prop["id"]] = prop.get("kind")
    for prop in package.get("v1_props") or []:
        if prop.get("id"):
            prop_kinds.setdefault(prop["id"], prop.get("kind"))

    frames = []
    for shot in motion.get("shots") or []:
        for record in shot.get("grip_telemetry") or []:
            frames.append(record)
    frames.sort(key=lambda r: r["t"])

    events = [e for e in action_data.get("events") or []
              if e.get("action_type") in INTERACTION_TYPES
              and e.get("prop_id")]
    shapes_cache: dict[str, tuple] = {}
    interactions = []
    failures: list[str] = []
    for event in events:
        report = _audit_event(event, frames, id_to_name, prop_kinds,
                              shapes_cache)
        interactions.append(report)
        failures.extend(report["failures"])

    summary = {
        "interactions": len(interactions),
        "passed": sum(1 for i in interactions if i["passed"]),
        "failed": sum(1 for i in interactions if not i["passed"]),
        "frames_with_telemetry": len(frames),
        "telemetry_present": bool(frames),
    }
    return {
        "audit_version": AUDIT_VERSION,
        "job_dir": str(job_dir),
        "summary": summary,
        "failures": failures,
        "passed": not failures,
        "interactions": interactions,
    }


def _audit_event(event, frames, id_to_name, prop_kinds, shapes_cache):
    aid = event.get("action_id")
    action_type = event.get("action_type")
    prop_id = event.get("prop_id")
    start = float(event.get("start_time") or 0.0)
    end = float(event.get("end_time") or start)
    actor_name = id_to_name.get(event.get("actor_id"),
                                event.get("actor_id"))
    recipient_name = id_to_name.get(event.get("recipient_id") or
                                    event.get("target_id"))
    kind = prop_kinds.get(prop_id)
    span_frames = [f for f in frames if start <= f["t"] < end
                   or (f["t"] == end and start == end)]
    failures: list[str] = []
    metrics: dict = {"frames": len(span_frames), "kind": kind}

    if not frames:
        failures.append("no grip telemetry in this job dir")
        return {"action_id": aid, "action_type": action_type,
                "prop_id": prop_id, "actor_id": event.get("actor_id"),
                "recipient_id": event.get("recipient_id"),
                "span": [start, end], "metrics": metrics,
                "failures": failures, "passed": False}
    if not span_frames:
        failures.append("no telemetry frames inside the event span")
        return {"action_id": aid, "action_type": action_type,
                "prop_id": prop_id, "actor_id": event.get("actor_id"),
                "recipient_id": event.get("recipient_id"),
                "span": [start, end], "metrics": metrics,
                "failures": failures, "passed": False}

    # --- draw presence / duplicates / holder series ------------------
    draws_per_frame = []
    for record in span_frames:
        mine = [d for d in record["draws"]
                if d.get("pid") == prop_id]
        draws_per_frame.append(mine)
    visible = sum(1 for mine in draws_per_frame if mine)
    metrics["visibility"] = round(visible / len(span_frames), 3)
    duplicates = sum(1 for mine in draws_per_frame if len(mine) > 1)
    metrics["duplicate_frames"] = duplicates
    if metrics["visibility"] < VISIBILITY_MIN:
        failures.append(
            f"prop visible in only {metrics['visibility']:.0%} "
            f"of span frames (need >= {VISIBILITY_MIN:.0%})")
    if duplicates:
        failures.append(f"prop drawn twice in {duplicates} frame(s)")

    holders = []
    for mine in draws_per_frame:
        holders.append(mine[0].get("holder") if mine else None)
    metrics["holders"] = sorted({h for h in holders if h})
    is_transfer = action_type in ("HAND_OVER", "RECEIVE_PROP",
                                  "GIVE")
    if not is_transfer and actor_name:
        matched = sum(1 for h in holders if h == actor_name)
        drawn = sum(1 for h in holders if h is not None)
        metrics["holder_match"] = round(
            matched / drawn, 3) if drawn else 0.0
        if metrics["holder_match"] < HOLDER_MATCH_MIN:
            failures.append(
                f"holder is {actor_name} in only "
                f"{metrics['holder_match']:.0%} of drawn frames")

    # --- ownership transition (transfers) ----------------------------
    # The switch may land just past the handover span (the paired
    # receive begins there), so search past the span end and judge
    # lateness against the tolerance, not the span edge.
    transition_t = None
    if is_transfer and recipient_name:
        window = [f for f in frames
                  if start <= f["t"] <= end + 5.0]
        for record in window:
            mine = [d for d in record["draws"]
                    if d.get("pid") == prop_id]
            if mine and mine[0].get("holder") == recipient_name:
                transition_t = record["t"]
                break
        metrics["transition_t"] = transition_t
        metrics["recipient"] = recipient_name
        if transition_t is None:
            failures.append(
                f"ownership never transferred to {recipient_name} "
                "inside the span")
        elif transition_t > end + TRANSITION_LATE_TOL_SEC:
            failures.append(
                f"ownership transferred at {transition_t:.2f}s, "
                f"after the span end {end:.2f}s")

    # --- gap / orientation / grip / penetration ----------------------
    # Held-state frames only: a TRANSFERRED prop is in flight and
    # its distance to either hand is transit, not grip.
    gaps, gap_norms, angles, forearms = [], [], [], []
    repaint_hits, repaint_total = 0, 0
    pen_scores = []
    open_us = []
    held_frames = transit_frames = 0
    for record, mine in zip(span_frames, draws_per_frame):
        if not mine:
            continue
        draw = mine[0]
        state = draw.get("state")
        if state == "TRANSFERRED":
            transit_frames += 1
        held = state in HELD_CONTACT_STATES
        if held:
            held_frames += 1
        holder = draw.get("holder")
        hand_side = draw.get("hand") or "r"
        hands = record["hands"].get(holder or "") or {}
        hand = hands.get("hand_" + hand_side)
        elbow = hands.get("elbow_" + hand_side)
        if draw.get("open_u") is not None:
            open_us.append(float(draw["open_u"]))
        if hand is None or not held:
            continue
        gap = math.hypot(hand[0] - draw["x"], hand[1] - draw["y"])
        hand_size = FINGER_LEN_FRAC * float(hands.get("H") or 0.0)
        gaps.append(gap)
        gap_norms.append(gap / hand_size if hand_size else None)
        if draw.get("angle") is not None:
            angles.append(float(draw["angle"]))
        if elbow is not None:
            forearms.append(_forearm_angle(hand, elbow))
        repaint_total += 1
        if draw.get("grip_repaint"):
            repaint_hits += 1
        # Penetration: finger strokes vs the drawn shape.
        draw_kind = draw.get("kind") or kind
        if elbow is not None and hand_size:
            shapes = None
            bbox = None
            if draw_kind in GEOMETRY_KINDS:
                if draw_kind not in shapes_cache:
                    try:
                        shapes_cache[draw_kind] = _spec_shapes(
                            draw_kind)
                    except Exception:  # noqa: BLE001 - no spec, skip
                        shapes_cache[draw_kind] = None
                shapes = shapes_cache[draw_kind]
            else:
                # Legacy kinds: footprint bbox, labelled approximate.
                hw, hh = FOOTPRINT_W / 2, FOOTPRINT_H / 2
                if draw_kind == "wallet" and draw.get("open_u", 0) \
                        > 0.05:
                    hw += FOOTPRINT_W * 0.55 * min(
                        1.0, float(draw["open_u"]))
                bbox = (hw, hh)
            if shapes is not None or bbox is not None:
                wrist_rel = (hand[0] - draw["x"],
                             hand[1] - draw["y"])
                tips = _finger_tips(hand, elbow, hand_size)
                hits = 0
                for tip in tips:
                    tip_rel = (tip[0] - draw["x"],
                               tip[1] - draw["y"])
                    if _stroke_hits_shape(wrist_rel, tip_rel,
                                          shapes, bbox):
                        hits += 1
                pen_scores.append(hits / 3.0)
    metrics["held_frames"] = held_frames
    metrics["transit_frames"] = transit_frames
    metrics["gap_px_mean"] = round(
        sum(gaps) / len(gaps), 2) if gaps else None
    metrics["gap_px_max"] = round(max(gaps), 2) if gaps else None
    norms = [g for g in gap_norms if g is not None]
    metrics["gap_norm_mean"] = round(
        sum(norms) / len(norms), 3) if norms else None
    metrics["gap_norm_max"] = round(max(norms), 3) if norms else None
    within = sum(1 for g in norms if g <= GAP_NORM_LIMIT)
    metrics["gap_within_limit"] = round(
        within / len(norms), 3) if norms else 0.0
    if norms and metrics["gap_within_limit"] < GAP_FRAME_FRACTION:
        failures.append(
            f"grip gap within {GAP_NORM_LIMIT} hand-sizes in only "
            f"{metrics['gap_within_limit']:.0%} of frames "
            f"(mean {metrics['gap_norm_mean']})")
    if angles:
        metrics["angle_range"] = round(max(angles) - min(angles), 1)
        metrics["angle_mean"] = round(sum(angles) / len(angles), 1)
        if action_type in ("HOLD", "CARRY") and \
                metrics["angle_range"] > HOLD_ANGLE_RANGE_MAX:
            failures.append(
                f"held prop angle range "
                f"{metrics['angle_range']} deg exceeds "
                f"{HOLD_ANGLE_RANGE_MAX} deg")
    if forearms:
        metrics["forearm_range"] = round(
            max(forearms) - min(forearms), 1)
    if repaint_total:
        metrics["grip_repaint_fraction"] = round(
            repaint_hits / repaint_total, 3)
        if metrics["grip_repaint_fraction"] < GRIP_REPAINT_MIN:
            failures.append(
                f"grip fan repainted in only "
                f"{metrics['grip_repaint_fraction']:.0%} of hold "
                f"frames (need >= {GRIP_REPAINT_MIN:.0%})")
    if pen_scores:
        metrics["penetration_mean"] = round(
            sum(pen_scores) / len(pen_scores), 3)
        metrics["penetration_min"] = round(min(pen_scores), 3)
        if metrics["penetration_mean"] < PENETRATION_MIN:
            failures.append(
                f"finger strokes cross the prop shape in only "
                f"{metrics['penetration_mean']:.0%} "
                f"(need >= {PENETRATION_MIN:.0%})")
    if action_type in ("OPEN", "CLOSE") and open_us:
        metrics["open_u_first"] = round(open_us[0], 2)
        metrics["open_u_last"] = round(open_us[-1], 2)
        if action_type == "OPEN" and open_us[-1] < 0.9:
            failures.append(
                f"wallet open_u ends at {open_us[-1]:.2f}, "
                "expected ~1.0")
        if action_type == "CLOSE" and open_us[-1] > 0.1:
            failures.append(
                f"wallet open_u ends at {open_us[-1]:.2f}, "
                "expected ~0.0")

    return {"action_id": aid, "action_type": action_type,
            "prop_id": prop_id, "actor_id": event.get("actor_id"),
            "recipient_id": event.get("recipient_id"),
            "span": [start, end], "metrics": metrics,
            "failures": failures, "passed": not failures}


__all__ = ["AUDIT_VERSION", "INTERACTION_TYPES", "GEOMETRY_KINDS",
           "audit_prop_contact"]
