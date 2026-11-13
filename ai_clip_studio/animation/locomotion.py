"""Canonical locomotion engine (Cinematic Engine Upgrade, Phase A).

ONE shared engine, parameterized per character (directive D1). This
module is the single bridge between the shared contracts
(``cinematic_contracts.GaitProfile``) and the proven planted-foot
core in ``primitives._locomote``. It does NOT reimplement walking:
it converts profiles to gait dicts, validates locomotion state plans,
guards facing continuity, and measures the 8 required metrics in
normalized character-space units.

Step vs stride (never mixed): STEP length is the distance between
two consecutive footfalls (either foot); STRIDE length is the full
two-step cycle (same foot to same foot). For a symmetric gait stride
== 2 * step, but both are always measured and reported separately.
The legacy gait-dict key ``stride_frac`` is a misnomer: it has always
meant STEP length (see ``_foot_state``: strikes are ``step`` apart,
same-foot strikes ``2*step`` apart). New code uses ``step_length_frac``
/ ``stride_length_frac``; ``stride_frac`` is kept as a legacy alias
equal to the step length so the proven core is untouched.

Cadence is a PLANNING input (it sets segment duration through
``duration_for_distance``) and a MEASURED output (footfalls per
minute from ``measure_locomotion``). The two must agree within
tolerance on a profile-driven walk; they are never assumed equal.
"""
from __future__ import annotations

import math

from ..cinematic_contracts import (
    CANONICAL_GAIT,
    GaitProfile,
    LocomotionMetrics,
    LocomotionState,
)
from .rig import GAIT_DEFAULT, GAIT_RUN

__all__ = [
    "GAIT_PRESETS",
    "VALID_TRANSITIONS",
    "profile_to_gait",
    "resolve_gait_profile",
    "duration_for_distance",
    "plan_locomotion",
    "state_at",
    "check_facing_continuity",
    "check_facing_vs_travel",
    "sample_primitive",
    "footfall_times",
    "measure_locomotion",
    "knee_angle",
]

# Posture -> forward torso lean (radians) while walking. The
# canonical upright lean (0.12) is GAIT_DEFAULT's value, kept.
_POSTURE_LEAN = {
    "upright": 0.12,
    "stooped": 0.28,
    "military": 0.06,
    "regal": 0.10,
}

# Gait presets: parameters only, one engine. "civilian" IS the
# canonical gait (the default); the others modify it without
# breaking the rig. Scale (giant body size) is NOT a gait parameter:
# it comes from the renderer's per-character height (the existing
# scale-variant mechanism, Cronus 1.8x precedent); the giant profile
# only slows the cadence and adds mass.
GAIT_PRESETS: dict[str, GaitProfile] = {
    "canonical": CANONICAL_GAIT,
    "civilian": CANONICAL_GAIT,
    "elderly": GaitProfile(
        step_length=0.22, stride_length=0.44, cadence=60.0,
        body_mass=0.9, posture="stooped", head_stability=0.7,
        arm_pose="restrained", fatigue=0.3, locomotion_style="elderly"),
    "soldier": GaitProfile(
        step_length=0.30, stride_length=0.60, cadence=100.0,
        body_mass=1.1, posture="military", head_stability=1.0,
        arm_pose="swing", locomotion_style="march"),
    "giant": GaitProfile(
        step_length=0.29, stride_length=0.58, cadence=55.0,
        body_mass=3.0, posture="regal", head_stability=0.9,
        arm_pose="swing", locomotion_style="giant"),
}

_MUD_GAIT = {
    "stride_frac": 0.12,
    "arm_amp": 0.55,
    "lean": 0.20,
    "bob_frac": 0.05,
    "lift_frac": 0.12,
    "overlap": 0.35,
}


def resolve_gait_profile(name_or_profile) -> GaitProfile:
    """Preset name -> GaitProfile; a GaitProfile passes through;
    None -> the canonical gait. Unknown names raise KeyError."""
    if name_or_profile is None:
        return CANONICAL_GAIT
    if isinstance(name_or_profile, GaitProfile):
        return name_or_profile
    if isinstance(name_or_profile, str):
        if name_or_profile in GAIT_PRESETS:
            return GAIT_PRESETS[name_or_profile]
        raise KeyError(
            f"unknown gait profile: {name_or_profile!r} "
            f"(expected one of {sorted(GAIT_PRESETS)})")
    raise TypeError(
        f"gait profile must be a name, a GaitProfile or None, "
        f"got {type(name_or_profile).__name__}")


def profile_to_gait(profile, run: bool = False,
                    terrain: str = "flat") -> dict:
    """GaitProfile -> the gait dict ``_locomote`` consumes.

    ``terrain`` "mud" starts from the mud gait (short steps, long
    double support, high lift); any other terrain_response value
    ("slope", "stairs", "sand") has NO engine behaviour yet and falls
    back to the flat gait -- the returned dict records the requested
    terrain in ``terrain_response`` so the gap stays visible instead
    of silently succeeding. ``run`` starts from GAIT_RUN.
    """
    profile = resolve_gait_profile(profile)
    if terrain == "mud" or profile.terrain_response == "mud":
        base = dict(_MUD_GAIT)
        step = min(profile.step_length, 0.15)
    elif run:
        base = dict(GAIT_RUN)
        step = profile.step_length
    else:
        base = dict(GAIT_DEFAULT)
        step = profile.step_length
    lean = _POSTURE_LEAN.get(profile.posture, 0.12)
    if run:
        lean = 0.40
        if profile.posture == "stooped":
            lean += 0.04
        elif profile.posture == "military":
            lean -= 0.04
    elif terrain == "mud" or profile.terrain_response == "mud":
        lean = max(lean, 0.20)
    bob_base = base["bob_frac"]
    if run:
        # A run bobs (flight phase); head stability damps the head
        # sway, not the flight bob.
        bob_frac = bob_base
    else:
        bob_frac = max(0.001, bob_base * (1.15 - profile.head_stability)
                       * (1.0 + 0.5 * profile.fatigue))
    gait = dict(base)
    gait.update({
        # Step/stride separation (see module docstring). stride_frac
        # is the legacy alias and ALWAYS equals the step length.
        "step_length_frac": step,
        "stride_length_frac": profile.stride_length,
        "stride_frac": step,
        "arm_amp": base["arm_amp"] * (1.0 - 0.3 * profile.fatigue),
        "lean": lean + 0.08 * profile.fatigue,
        "bob_frac": bob_frac,
        "arm_pose": profile.arm_pose,
        "head_stability": profile.head_stability,
        "terrain_response": profile.terrain_response,
        "profile_name": profile.locomotion_style,
        # Heavier bodies ease in/out more slowly (anticipation +
        # settle scale). 1.0 for the canonical mass; capped.
        "ease_scale": min(1.5, 1.0 + 0.15 * max(
            0.0, profile.body_mass - 1.0)),
        # Head anticipation/follow-through sway damps with stability.
        "sway_scale": 1.0 - 0.7 * profile.head_stability,
    })
    return gait


# Must match the ease fraction of primitives._ease_profile: the
# cruising speed exceeds the travel-average speed by 1/(1-e).
_EASE_FRACTION = 0.15


def duration_for_distance(dist_px: float, height_px: float,
                          profile, run: bool = False) -> float:
    """Segment duration for a profile-driven walk over ``dist_px``.

    The CRUISING speed equals the profile's effective speed
    (cadence * step, or its explicit movement_speed): the travel
    time is heights / speed / (1 - ease), because the eased ends
    make the middle run faster than the travel average. The
    anticipation + settle allowance (0.20 + 0.25 s, scaled by the
    profile's mass ease) is added on top -- a walk that must cover
    the distance at the profile speed cannot spend the anticipation
    time travelling. For short segments (< ~1.3 s) where the
    anticipation/settle caps are not reached, the allowance is the
    35% duration fraction instead. The measured steady cadence of
    the rendered walk must then match the profile cadence.
    """
    profile = resolve_gait_profile(profile)
    speed = profile.effective_speed
    if speed <= 0:
        raise ValueError(f"profile has no positive speed: {profile!r}")
    heights = abs(float(dist_px)) / float(height_px)
    travel = heights / speed / (1.0 - _EASE_FRACTION)
    ease_scale = profile_to_gait(profile, run=run).get("ease_scale", 1.0)
    total = travel + 0.45 * ease_scale
    if total < 1.34:
        total = travel / 0.65
    return total


# ------------------------------------------------------------------
# Locomotion state machine (Phase A)
# ------------------------------------------------------------------

VALID_TRANSITIONS: dict[LocomotionState, frozenset] = {
    LocomotionState.IDLE: frozenset({
        LocomotionState.START_WALK, LocomotionState.START_RUN,
        LocomotionState.TURN}),
    LocomotionState.START_WALK: frozenset({
        LocomotionState.WALK, LocomotionState.STOP_WALK}),
    LocomotionState.WALK: frozenset({
        LocomotionState.STOP_WALK, LocomotionState.START_RUN,
        LocomotionState.TERRAIN_ADAPTATION}),
    LocomotionState.STOP_WALK: frozenset({
        LocomotionState.IDLE, LocomotionState.TURN,
        LocomotionState.START_WALK}),
    LocomotionState.TURN: frozenset({
        LocomotionState.IDLE, LocomotionState.START_WALK,
        LocomotionState.START_RUN}),
    LocomotionState.START_RUN: frozenset({
        LocomotionState.RUN, LocomotionState.STOP_RUN}),
    LocomotionState.RUN: frozenset({
        LocomotionState.STOP_RUN, LocomotionState.TERRAIN_ADAPTATION}),
    LocomotionState.STOP_RUN: frozenset({
        LocomotionState.IDLE, LocomotionState.TURN,
        LocomotionState.START_RUN, LocomotionState.START_WALK}),
    LocomotionState.TERRAIN_ADAPTATION: frozenset({
        LocomotionState.WALK, LocomotionState.RUN,
        LocomotionState.STOP_WALK, LocomotionState.STOP_RUN}),
}

_TRAVEL_STATES = frozenset({
    LocomotionState.START_WALK, LocomotionState.WALK,
    LocomotionState.START_RUN, LocomotionState.RUN,
    LocomotionState.TERRAIN_ADAPTATION,
})


def _as_state(value) -> LocomotionState:
    if isinstance(value, LocomotionState):
        return value
    text = str(value)
    # Accept both the enum NAME ("WALK") and its VALUE ("walk").
    if text in LocomotionState.__members__:
        return LocomotionState[text]
    return LocomotionState(text)


def plan_locomotion(segments: list[dict]) -> list[dict]:
    """Validate + time a locomotion plan.

    Each segment: {"state", "duration", "direction" (+1/-1/None),
    "cut_before" (bool)}. Rules enforced (ValueError otherwise):
    1. Transitions must be in VALID_TRANSITIONS. A plan may start in
       IDLE / START_* / TURN, or in any state when cut_before is set
       (the motion continues across a cut).
    2. A direction change between travel segments requires an
       intervening TURN segment or a cut (cut_before on the new
       direction's first segment). Facing must NEVER instantly
       mirror inside one continuous segment.
    Returns timed segments: {"state", "start", "end", "direction",
    "cut_before"}.
    """
    plan: list[dict] = []
    cursor = 0.0
    prev_state: LocomotionState | None = None
    last_direction = None
    turn_since_direction = True
    for index, seg in enumerate(segments):
        state = _as_state(seg["state"])
        duration = float(seg["duration"])
        if duration <= 0:
            raise ValueError(f"segment {index}: duration must be > 0")
        direction = seg.get("direction")
        if direction not in (None, 1, -1):
            raise ValueError(
                f"segment {index}: direction must be +1, -1 or None")
        cut_before = bool(seg.get("cut_before", False))
        if prev_state is None:
            if state not in (LocomotionState.IDLE,
                             LocomotionState.START_WALK,
                             LocomotionState.START_RUN,
                             LocomotionState.TURN) and not cut_before:
                raise ValueError(
                    f"segment {index}: plan cannot start in {state.value} "
                    "without a cut (start in IDLE/START_*/TURN)")
        elif state not in VALID_TRANSITIONS[prev_state]:
            raise ValueError(
                f"segment {index}: illegal transition "
                f"{prev_state.value} -> {state.value}")
        if state is LocomotionState.TURN:
            turn_since_direction = True
        if state in _TRAVEL_STATES and direction is not None:
            if (last_direction is not None
                    and direction != last_direction
                    and not turn_since_direction
                    and not cut_before):
                raise ValueError(
                    f"segment {index}: direction change "
                    f"{last_direction} -> {direction} without a TURN "
                    "segment or a cut (facing must never mirror "
                    "inside one continuous segment)")
            last_direction = direction
            turn_since_direction = False
        if cut_before:
            turn_since_direction = True
        plan.append({"state": state, "start": cursor,
                     "end": cursor + duration, "direction": direction,
                     "cut_before": cut_before})
        cursor += duration
        prev_state = state
    return plan


def state_at(plan: list[dict], t: float) -> LocomotionState | None:
    """Locomotion state at time ``t`` in a timed plan (None outside)."""
    for seg in plan:
        if seg["start"] <= t < seg["end"]:
            return seg["state"]
    if plan and t >= plan[-1]["end"]:
        return plan[-1]["state"]
    return None


# ------------------------------------------------------------------
# Facing guards (measured on sampled frames)
# ------------------------------------------------------------------

def check_facing_continuity(frames, cut_times=()) -> list[str]:
    """Facing must not flip between consecutive frames unless a turn
    is in progress (turn_u > 0 on either frame) or a cut boundary
    falls between them. ``frames`` are sampled frames carrying
    ``_facing``, ``_turn_u`` and ``_t`` (see sample_primitive)."""
    cuts = sorted(float(c) for c in cut_times)
    bad: list[str] = []
    for prev, cur in zip(frames, frames[1:]):
        if prev.get("_facing") == cur.get("_facing"):
            continue
        if prev.get("_turn_u", 0.0) > 0.0 or cur.get("_turn_u", 0.0) > 0.0:
            continue
        t0, t1 = float(prev.get("_t", 0.0)), float(cur.get("_t", 0.0))
        if any(t0 < c <= t1 for c in cuts):
            continue
        bad.append(
            f"facing flipped {prev.get('_facing')} -> {cur.get('_facing')} "
            f"at t={t1:.3f} with no turn in progress and no cut")
    return bad


def check_facing_vs_travel(frames, fps: float = 24.0,
                           min_speed_px_per_s: float = 20.0,
                           min_run: int = 3) -> list[str]:
    """While travelling, facing must match the travel direction
    (the "di nguoc" / backwards-walk defect). Frames mid-turn
    (turn_u > 0) are exempt. ``frames`` carry hip positions + _t.

    A violation needs ``min_run`` CONSECUTIVE opposing frames: a
    single-frame hip shift is postural (the anticipation crouch
    dips the hip back ~3 px before the body moves), not travel. A
    real backwards walk opposes facing for its whole duration.
    """
    bad: list[str] = []
    run_start = None
    run_speed = 0.0
    run_count = 0

    def _flush():
        nonlocal run_start, run_count
        if run_count >= min_run:
            bad.append(
                f"facing opposes travel ({run_speed:+.0f} px/s) for "
                f"{run_count} frames from t={run_start:.3f}")
        run_start, run_count = None, 0

    for prev, cur in zip(frames, frames[1:]):
        opposing = False
        speed = 0.0
        if cur.get("_turn_u", 0.0) <= 0.0:
            dt = float(cur.get("_t", 0.0)) - float(prev.get("_t", 0.0))
            if dt > 0:
                speed = (cur["hip"][0] - prev["hip"][0]) / dt
                facing = cur.get("_facing", 1) or 1
                opposing = (abs(speed) >= min_speed_px_per_s
                            and (speed > 0) != (facing > 0))
        if opposing:
            if run_start is None:
                run_start = float(cur.get("_t", 0.0))
                run_speed = speed
            run_count += 1
        else:
            _flush()
    _flush()
    return bad


# ------------------------------------------------------------------
# Sampling + measurement
# ------------------------------------------------------------------

def sample_primitive(fn, char, duration: float, fps: float = 24.0,
                     t0: float = 0.0) -> list[dict]:
    """Run a primitive ``fn(t)`` frame by frame, capturing a joints
    dict per frame. Each frame is the joints dict plus ``_t``,
    ``_facing`` and ``_turn_u`` measurement keys. The character is
    left in its final pose."""
    frames: list[dict] = []
    count = int(round(duration * fps)) + 1
    for fi in range(count):
        t = fi / fps
        fn(t)
        frame = dict(char.joints())
        frame["_t"] = t0 + t
        frame["_facing"] = char.pose.get("facing", 1)
        frame["_turn_u"] = char.pose.get("turn_u", 0.0)
        frames.append(frame)
    return frames


def knee_angle(joints: dict, side: str) -> float:
    """Interior knee angle in degrees (180 = leg straight)."""
    hip = joints["hip"]
    knee = joints[f"knee_{side}"]
    foot = joints[f"foot_{side}"]
    ax, ay = hip[0] - knee[0], hip[1] - knee[1]
    bx, by = foot[0] - knee[0], foot[1] - knee[1]
    denom = math.hypot(ax, ay) * math.hypot(bx, by)
    if denom < 1e-9:
        return 180.0
    cosang = max(-1.0, min(1.0, (ax * bx + ay * by) / denom))
    return math.degrees(math.acos(cosang))


def _contact_runs(frames, side: str, ground_y: float,
                   tol: float) -> list[tuple[int, int]]:
    """(start_frame, end_frame) inclusive runs where the foot is in
    contact with the ground."""
    runs: list[tuple[int, int]] = []
    start = None
    for i, frame in enumerate(frames):
        contact = abs(frame[f"foot_{side}"][1] - ground_y) <= tol
        if contact and start is None:
            start = i
        elif not contact and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(frames) - 1))
    return runs


def footfall_times(frames, fps: float, ground_y: float,
                   contact_tol_px: float = 4.0) -> list[dict]:
    """Footfall events: [{"t", "foot", "x"}] at each strike.

    Shared by measurement and by the audio stage (Phase G): footstep
    SFX must land on these times, never at scene start. A strike is
    the first frame of a contact run.
    """
    falls: list[dict] = []
    for side in ("l", "r"):
        for start, _end in _contact_runs(frames, side, ground_y,
                                         contact_tol_px):
            falls.append({"t": float(frames[start].get(
                "_t", start / fps)),
                "foot": side,
                "x": float(frames[start][f"foot_{side}"][0])})
    falls.sort(key=lambda f: (f["t"], f["foot"]))
    return falls


def measure_locomotion(frames, fps: float, height_px: float,
                       ground_y: float,
                       contact_tol_px: float = 4.0) -> LocomotionMetrics:
    """The 8 Phase A metrics over sampled WALK/RUN frames.

    ``frames`` must cover a locomotion portion with at least 3
    footfalls (a standstill still yields 2 -- one per foot at the
    first frame -- and a 2-footfall sample cannot give a stride or
    a symmetry). All lengths are normalized by ``height_px``.
    Raises ValueError when the sample has too few footfalls to
    measure.
    """
    if len(frames) < 2:
        raise ValueError("measure_locomotion needs at least 2 frames")
    height = float(height_px)
    falls = footfall_times(frames, fps, ground_y, contact_tol_px)
    if len(falls) < 3:
        raise ValueError(
            f"measure_locomotion needs >= 3 footfalls, got {len(falls)} "
            "(sample a locomotion portion, not a standstill)")
    # Step: consecutive footfalls (either foot). Stride: same foot.
    step_lengths = [abs(b["x"] - a["x"]) / height
                    for a, b in zip(falls, falls[1:])]
    stride_lengths = []
    by_foot: dict[str, list[dict]] = {"l": [], "r": []}
    for fall in falls:
        by_foot[fall["foot"]].append(fall)
    for foot_falls in by_foot.values():
        stride_lengths.extend(
            abs(b["x"] - a["x"]) / height
            for a, b in zip(foot_falls, foot_falls[1:]))
    step_length = sum(step_lengths) / len(step_lengths)
    stride_length = (sum(stride_lengths) / len(stride_lengths)
                     if stride_lengths else 2.0 * step_length)
    # Cadence: the STEADY-STATE step rate from the inter-footfall
    # intervals. Simultaneous strikes (both feet planted when the
    # sample starts) contribute a zero interval and are not steps,
    # so only POSITIVE intervals count. The first positive interval
    # always spans the ease-in (the walk starts from rest, and the
    # distance profile eases over its first 15%), and the last spans
    # the ease-out, so both are dropped when enough intervals remain;
    # with only 2 intervals the first is dropped and the second (the
    # steady one) is the estimate. With a single interval there is
    # nothing to drop. This is a uniform rule, not a per-walk
    # adjustment: long walks and 2-step walks are measured the same
    # way.
    intervals = [b["t"] - a["t"] for a, b in zip(falls, falls[1:])
                 if b["t"] > a["t"]]
    if len(intervals) >= 3:
        steady = sorted(intervals[1:-1])
        mid = len(steady) // 2
        if len(steady) % 2:
            median_interval = steady[mid]
        else:
            median_interval = 0.5 * (steady[mid - 1] + steady[mid])
        cadence = 60.0 / median_interval
    elif len(intervals) == 2:
        cadence = 60.0 / intervals[1]
    elif intervals:
        cadence = 60.0 / intervals[0]
    else:
        cadence = 0.0
    # Head vertical displacement, peak-to-peak.
    head_ys = [f["head"][1] for f in frames]
    head_disp = (max(head_ys) - min(head_ys)) / height
    # Foot sliding: max drift of a planted foot from its strike x.
    sliding = 0.0
    stance_runs = 0
    stance_total = 0.0
    for side in ("l", "r"):
        for start, end in _contact_runs(frames, side, ground_y,
                                        contact_tol_px):
            strike_x = frames[start][f"foot_{side}"][0]
            drift = max(abs(frames[i][f"foot_{side}"][0] - strike_x)
                        for i in range(start, end + 1)) / height
            sliding = max(sliding, drift)
            stance_runs += 1
            stance_total += (end - start + 1) / fps
    stance_duration = stance_total / stance_runs if stance_runs else 0.0
    # Joint continuity: max per-frame knee-angle jump (either leg).
    worst = 0.0
    for side in ("l", "r"):
        angles = [knee_angle(f, side) for f in frames]
        for a, b in zip(angles, angles[1:]):
            worst = max(worst, abs(b - a))
    # Root movement + symmetry.
    root_movement = abs(frames[-1]["hip"][0]
                        - frames[0]["hip"][0]) / height
    per_foot_steps: dict[str, list[float]] = {"l": [], "r": []}
    for a, b in zip(falls, falls[1:]):
        per_foot_steps[b["foot"]].append(abs(b["x"] - a["x"]) / height)
    if per_foot_steps["l"] and per_foot_steps["r"]:
        mean_l = sum(per_foot_steps["l"]) / len(per_foot_steps["l"])
        mean_r = sum(per_foot_steps["r"]) / len(per_foot_steps["r"])
        denom = max(mean_l, mean_r)
        symmetry = 1.0 - abs(mean_l - mean_r) / denom if denom > 0 else 0.0
    else:
        symmetry = 0.0
    return LocomotionMetrics(
        step_length=step_length,
        stride_length=stride_length,
        cadence=cadence,
        head_vertical_displacement=head_disp,
        foot_sliding=sliding,
        stance_duration=stance_duration,
        joint_angle_continuity=worst,
        root_movement=root_movement,
        left_right_symmetry=max(0.0, min(1.0, symmetry)),
    )
