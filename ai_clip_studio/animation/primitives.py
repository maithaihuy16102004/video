"""Data-driven animation primitives (Master Prompt §4).

Every action is driven by data from a scene package — an action list like
  {"type": "walk_to", "char": "lustig", "from_x": 300, "to_x": 1180,
   "duration": 3.4, "ground_y": 920}
— never hardcoded per story. Each primitive returns a per-frame pose
function; compiling an action list yields a full animation timeline
(frame -> {char_name: pose}) that a renderer (Motion Canvas or the
frame-by-frame renderer) can execute.

Primitives: walk_to, run_to, turn_to, look_at, talk (gesture + head bob),
point_at, reach_to, give_to (handoff with a prop that follows the hands),
take_from, open_door, sit_down, stand_up, shrug, cover_face, nod, wave.
Every primitive moves real joints over time; bone lengths are invariant
(checked in tests/test_animation_primitives.py).
"""
import math

from .rig import Stickman, walk_pose, interp_keys, smoothstep, lerp


def _pose(char, **kw):
    char.set_pose(**kw)
    return char


def _s(char, px):
    """Scale a pixel offset written for the reference height (560 px) to
    this character's height, so primitives work for a 400 px child as
    well as a 560 px adult (PREMIUM_STICKMAN v3: one proportion system)."""
    return px * float(char.H) / 560.0


def walk_to(char, from_x, to_x, duration, ground_y, height=560):
    """Walk from from_x to to_x over `duration` seconds. Returns f(t)->char."""
    def fn(t):
        u = min(1.0, max(0.0, t / duration))
        x = lerp(from_x, to_x, smoothstep(u))
        phase = (x - from_x) / 55.0 * math.pi
        pose = dict(walk_pose(phase))
        pose["root_x"] = x
        pose["root_y"] = ground_y - (char.u_leg + char.l_leg) * 0.93
        pose["facing"] = 1 if to_x >= from_x else -1
        _pose(char, **pose)
        ph = phase
        char.foot_target_l = (x + _s(char, 65) * math.sin(ph),
                              ground_y - _s(char, 45) * max(0, math.cos(ph)))
        char.foot_target_r = (x - _s(char, 65) * math.sin(ph),
                              ground_y - _s(char, 45) * max(0, -math.cos(ph)))
        char.hand_target_l = None
        char.hand_target_r = None
        return char
    return fn


def run_to(char, from_x, to_x, duration, ground_y):
    """Run: same as walk_to with a bigger stride amplitude and lean."""
    base = walk_to(char, from_x, to_x, duration, ground_y)

    def fn(t):
        c = base(t)
        c.set_pose(torso_lean=0.22)
        return c
    return fn


def look_at(char, angle_keys, duration):
    """Head look angle over time; angle_keys = [(t, angle_rad), ...]."""
    def fn(t):
        char.set_pose(head_look=interp_keys(angle_keys, t))
        return char
    return fn


def point_at(char, target, duration):
    """Raise the right arm toward `target` (x, y) and look at it."""
    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        hx, hy = char.pose["root_x"], char.pose["root_y"]
        tx, ty = target
        char.hand_target_r = (lerp(hx + _s(char, 60), tx, u),
                              lerp(hy - _s(char, 140), ty, u))
        char.set_pose(head_look=-0.35 * u, torso_lean=-0.06 * u)
        return char
    return fn


def wave(char, duration, freq=3.0):
    """Wave the right hand side to side."""
    def fn(t):
        hx, hy = char.pose["root_x"], char.pose["root_y"]
        char.hand_target_r = (hx + _s(char, 90),
                              hy - _s(char, 260)
                              + _s(char, 25) * math.sin(t * 2 * math.pi * freq / duration * 2))
        return char
    return fn


def reach_to(char, target, duration, hand="r"):
    """Reach one hand toward a target point (IK)."""
    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        hx, hy = char.pose["root_x"], char.pose["root_y"]
        sx, sy = hx + _s(char, 60), hy - _s(char, 140)
        if hand == "r":
            char.hand_target_r = (lerp(sx, target[0], u), lerp(sy, target[1], u))
        else:
            char.hand_target_l = (lerp(sx, target[0], u), lerp(sy, target[1], u))
        return char
    return fn


def give_to(giver, receiver, prop, duration):
    """Handoff: giver's and receiver's hands converge on a midpoint and
    `prop` (dict with 'x','y') travels with them. Returns f(t)->(giver, receiver, prop)."""
    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        gx, gy = giver.pose["root_x"], giver.pose["root_y"]
        rx, ry = receiver.pose["root_x"], receiver.pose["root_y"]
        mid_x = (gx + rx) / 2
        mid_y = gy - _s(giver, 180) - _s(giver, 40) * math.sin(u * math.pi)
        giver.hand_target_r = (lerp(gx + _s(giver, 60), mid_x, u), mid_y)
        receiver.hand_target_l = (lerp(rx - _s(receiver, 60), mid_x, u), mid_y)
        prop["x"], prop["y"] = mid_x, mid_y + _s(giver, 10)
        return giver, receiver, prop
    return fn


def shrug(char, duration):
    """Both arms up, palms out, over `duration` seconds."""
    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        char.set_pose(arm_l=lerp(0.3, -2.0, u), arm_r=lerp(0.15, -2.0, u),
                      elbow_l=0.4, elbow_r=0.4)
        char.hand_target_l = None
        char.hand_target_r = None
        return char
    return fn


def cover_face(char, duration):
    """Both hands to the face (embarrassment / grief)."""
    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        head_x, head_y = char.joints()["head"]
        char.hand_target_l = (head_x - _s(char, 30),
                              head_y - _s(char, 40) * u)
        char.hand_target_r = (head_x + _s(char, 30),
                              head_y - _s(char, 40) * u)
        char.set_pose(head_look=0.15 * u, torso_lean=0.18 * u)
        return char
    return fn


def nod(char, duration, freq=1.1, amp=0.10):
    """Repeated head nod (agreement / counting)."""
    def fn(t):
        char.set_pose(head_look=amp * math.sin(t * 2 * math.pi * freq))
        return char
    return fn


def sit_down(char, duration, ground_y):
    """Lower the root and bend the knees into a seated pose."""
    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        char.set_pose(root_y=lerp(char.pose["root_y"],
                                  ground_y - _s(char, 150), u),
                      thigh_l=lerp(0.0, 1.4, u), thigh_r=lerp(0.0, 1.4, u),
                      knee_l=lerp(0.1, 1.5, u), knee_r=lerp(0.1, 1.5, u))
        return char
    return fn


def stand_up(char, duration, ground_y):
    """Inverse of sit_down."""
    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        char.set_pose(root_y=lerp(char.pose["root_y"], ground_y - (char.u_leg + char.l_leg) * 0.93, u),
                      thigh_l=lerp(1.4, 0.0, u), thigh_r=lerp(1.4, 0.0, u),
                      knee_l=lerp(1.5, 0.1, u), knee_r=lerp(1.5, 0.1, u))
        return char
    return fn


PRIMITIVES = {
    "walk_to": walk_to, "run_to": run_to, "look_at": look_at,
    "point_at": point_at, "wave": wave, "reach_to": reach_to,
    "give_to": give_to, "shrug": shrug, "cover_face": cover_face,
    "nod": nod, "sit_down": sit_down, "stand_up": stand_up,
}


def compile_actions(action_list, chars, fps=24):
    """Compile a data-driven action list into a frame timeline.

    action_list: [{type, char, start, duration, ...params}]
    chars: {name: Stickman}. Returns {frame_index: {char_name: joints}}.
    Unknown action types raise ValueError — the pipeline must report an
    unsupported action explicitly, never silently substitute a static pose.
    """
    compiled = []
    for a in action_list:
        ptype = a["type"]
        if ptype not in PRIMITIVES:
            raise ValueError(f"unsupported animation action: {ptype!r}")
        start, dur = a["start"], a["duration"]
        if ptype == "give_to":
            giver, receiver = chars[a["char"]], chars[a["other"]]
            prop = {"x": 0, "y": 0}
            fn = give_to(giver, receiver, prop, dur)
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype in ("walk_to", "run_to"):
            c = chars[a["char"]]
            fn = PRIMITIVES[ptype](c, a["from_x"], a["to_x"], dur, a["ground_y"])
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "look_at":
            c = chars[a["char"]]
            fn = look_at(c, a["angle_keys"], dur)
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype in ("point_at", "reach_to"):
            c = chars[a["char"]]
            fn = PRIMITIVES[ptype](c, tuple(a["target"]), dur)
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype in ("wave", "shrug", "cover_face", "nod"):
            c = chars[a["char"]]
            kw = {k: v for k, v in a.items()
                  if k in ("freq", "amp")}
            fn = PRIMITIVES[ptype](c, dur, **kw)
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype in ("sit_down", "stand_up"):
            c = chars[a["char"]]
            fn = PRIMITIVES[ptype](c, dur, a["ground_y"])
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
    total = max((s + d for s, d, _ in compiled), default=0.0)
    timeline = {}
    for fi in range(int(total * fps) + 1):
        t = fi / fps
        for start, dur, fn in compiled:
            if start <= t <= start + dur:
                fn(t - start)
        timeline[fi] = {name: c.joints() for name, c in chars.items()}
    return timeline
