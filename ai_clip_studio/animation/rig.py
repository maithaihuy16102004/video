"""12-joint stickman rig, PREMIUM_STICKMAN v4 proportions, frame-by-frame
animation.

Proportions are MEASURED from the reference stickman
(~/workspace/user/media_library/image/image.png, 1024x1024) by
~/workspace/acceptance_loop/stickman_v4/measure_reference.py -- not
guessed, not the V51 standard. Measured (fractions of the DRAWN total
height, head top -> foot bottom): head diameter 0.339, torso 0.231,
legs 0.429, arms 0.283, limb thickness 0.026, head outline 0.028.
See reference_measurements.json for the full table.

Geometry (v4): the head sits DIRECTLY on the shoulders -- head centre
1.0*head_r above the shoulder, head bottom exactly at shoulder level,
no neck gap -- so the drawn total height equals H exactly:
2*head_r + torso + legs = (0.34 + 0.231 + 0.429) * H = 1.0 * H.
(v3 had the head centre 1.5r above the shoulder, which made the drawn
height 1.085*H and capped the achievable head ratio at ~0.27.)

The character is drawn in side view (profile), facing +1 (right) or -1 (left).
Joints are computed every frame from a pose; nothing is a static image.

Two-bone IK is used for hands and feet when a target is given (reach, plant,
hand-to-face). Swing limbs use FK from joint angles. Every frame returns the
full joint map so motion can be measured (joint displacement per frame).
"""
import math

# --- PREMIUM_STICKMAN v4 proportions (fractions of total height) ---
# Measured from the reference image (see module docstring). HEAD_RATIO
# is the head DIAMETER as a fraction of the drawn total height; the
# schema allows 0.20-0.35 and the measured value 0.339 sits inside it.
HEAD_RATIO = 0.34
HEAD_RATIO_MIN = 0.33  # tight lock around the measured 0.339
HEAD_RATIO_MAX = 0.35
TORSO_FRAC = 0.231
UPPER_LEG_FRAC = 0.2145
LOWER_LEG_FRAC = 0.2145
UPPER_ARM_FRAC = 0.13
LOWER_ARM_FRAC = 0.153
SHOULDER_HALF_FRAC = 0.09   # half shoulder width
HIP_HALF_FRAC = 0.06

# Body-variant width scale. ONE scale multiplies torso width AND limb
# width together, so a sturdy character is uniformly thicker, never a
# thin arm on a wide torso (PREMIUM_STICKMAN v4 line rule).
BODY_WIDTH_SCALE = {"slim": 0.9, "standard": 1.0, "sturdy": 1.15}


def ik_2bone(ax, ay, tx, ty, l1, l2, bend=+1):
    """Two-bone IK: anchor (ax,ay), target (tx,ty), lengths l1,l2.
    bend=+1 puts the middle joint on one side of the anchor->target line,
    bend=-1 on the other. Returns (mx,my) middle joint, clamped to reach."""
    dx, dy = tx - ax, ty - ay
    raw_d = math.hypot(dx, dy)
    if raw_d < 1e-6:
        # Target on the anchor: no direction to bend toward. Put the
        # middle joint straight down at l1 so bone lengths stay exact.
        return ax, ay + l1
    d = max(1.0, min(raw_d, l1 + l2 - 0.5))
    # unit vector anchor->target
    ux, uy = dx / raw_d, dy / raw_d
    # distance from anchor to the middle joint projected on the line
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, l1 * l1 - a * a))
    # perpendicular (bend side)
    px, py = -uy * bend, ux * bend
    mx = ax + ux * a + px * h
    my = ay + uy * a + py * h
    return mx, my


def smoothstep(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def lerp(a, b, u):
    return a + (b - a) * u


def interp_keys(keys, t):
    """keys: list of (time, value) sorted by time. Smoothstep-interpolated."""
    if t <= keys[0][0]:
        return keys[0][1]
    if t >= keys[-1][0]:
        return keys[-1][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            return lerp(v0, v1, smoothstep((t - t0) / (t1 - t0)))
    return keys[-1][1]


# Gait parameters (audit 2026-11-11 vs RicksClips): every template walks
# differently -- these are DATA on the template, never hardcoded per
# story and never a character name inside the animation code.
#   stride_frac: step length as a fraction of total height H
#     (natural walk ~0.35-0.45 x leg length = ~0.15-0.19 H; the old
#     walk used 55 px steps = 0.10 H at 267 steps/min -- a shuffle).
#   arm_amp: arm-swing amplitude in radians (anti-phase with the legs).
#   lean: forward torso lean in radians while walking.
#   bob_frac: vertical COM excursion as a fraction of leg length
#     (real ~0.04-0.05; the old bob was 10 px = 0.013 H and INVERTED:
#     highest at foot strike, lowest at mid-stance).
#   lift_frac: max foot lift during swing, fraction of H.
#   overlap: fraction of a step the old foot stays planted AFTER the
#     other foot strikes (+0.20 = 20% double support, a walk;
#     negative = flight phase, a run).
GAIT_DEFAULT = {
    "stride_frac": 0.16,
    "arm_amp": 0.45,
    "lean": 0.08,
    "bob_frac": 0.04,
    "lift_frac": 0.08,
    "overlap": 0.20,
}

# Run gait: longer stride, real flight phase (overlap < 0), more lean,
# bigger arm pump. A run is NOT a fast walk.
GAIT_RUN = {
    "stride_frac": 0.22,
    "arm_amp": 0.60,
    "lean": 0.22,
    "bob_frac": 0.05,
    "lift_frac": 0.10,
    "overlap": -0.30,
    "flight_lift_frac": 0.03,
}


class Stickman:
    """A V51 stickman. Pose is set per frame via `pose` dict, then `joints()`."""

    def __init__(self, height=560, suit="#172033", skin="#F3F0E8",
                 hat="bowler", moustache=True, name="lustig",
                 template="male", body_variant="standard",
                 hair_style=None, glasses=False, cane=False,
                 costume="none", gait=None):
        self.H = height
        self.head_r = HEAD_RATIO * height / 2
        self.torso = TORSO_FRAC * height
        self.u_leg = UPPER_LEG_FRAC * height
        self.l_leg = LOWER_LEG_FRAC * height
        self.u_arm = UPPER_ARM_FRAC * height
        self.l_arm = LOWER_ARM_FRAC * height
        self.sh_half = SHOULDER_HALF_FRAC * height
        self.hip_half = HIP_HALF_FRAC * height
        self.suit = suit
        self.skin = skin
        self.hat = hat
        self.moustache = moustache
        self.name = name
        # PREMIUM_STICKMAN v4 identity (see animation/character_art.py).
        # template: male | female | child | elderly. body_variant scales
        # torso/limb widths TOGETHER (slim 0.9 / standard 1.0 / sturdy
        # 1.15) so line thickness stays uniform within one character.
        self.template = template
        self.body_variant = body_variant
        self.width_scale = BODY_WIDTH_SCALE.get(body_variant, 1.0)
        # hair_style: None (use template default) | short | long | tuft.
        self.hair_style = hair_style
        self.glasses = glasses
        self.cane = cane
        # costume: "none" | "dress" (dress extends the torso A-line).
        self.costume = costume
        # gait: per-template walk parameters (see GAIT_DEFAULT). A
        # character's walk is part of its identity -- Minh strides,
        # Lan steps shorter, an elder shuffles -- and it lives here,
        # on the character, not in a per-story animation routine.
        self.gait = dict(GAIT_DEFAULT)
        if gait:
            self.gait.update(gait)
        # pose defaults (angles in radians; + = forward / toward facing)
        self.pose = {
            "root_x": 960.0, "root_y": 900.0, "facing": 1,
            "torso_lean": 0.0, "head_look": 0.0, "head_pitch": 0.0,
            "thigh_l": 0.0, "thigh_r": 0.0, "knee_l": 0.0, "knee_r": 0.0,
            "arm_l": 0.0, "arm_r": 0.0, "elbow_l": 0.0, "elbow_r": 0.0,
            "bob": 0.0,
        }
        # IK targets (screen coords) override FK for a limb when set
        self.hand_target_l = None
        self.hand_target_r = None
        self.foot_target_l = None
        self.foot_target_r = None

    def set_pose(self, **kw):
        self.pose.update(kw)

    def joints(self):
        """Return dict of joint positions (x, y) in screen coords."""
        p = self.pose
        f = p["facing"]
        hip_x = p["root_x"]
        hip_y = p["root_y"] - p["bob"]
        lean = p["torso_lean"]

        def clamped_target(ax, ay, tx, ty, reach):
            """Clamp a target to 98% of the two-bone reach so the IK
            solution never stretches a bone (V51 bone-length invariant)."""
            dx, dy = tx - ax, ty - ay
            d = math.hypot(dx, dy)
            if d < 1e-6:
                return ax, ay
            limit = reach * 0.98
            if d > limit:
                return ax + dx / d * limit, ay + dy / d * limit
            return tx, ty
        # spine: hip -> shoulder (lean tilts forward)
        sh_x = hip_x + math.sin(lean) * self.torso
        sh_y = hip_y - math.cos(lean) * self.torso
        neck_x = sh_x + math.sin(lean) * self.head_r * 0.4
        neck_y = sh_y - math.cos(lean) * self.head_r * 0.4
        # v4: head centre is only 0.6r above the neck (1.0r above the
        # shoulder), so the head bottom sits exactly at shoulder level
        # -- the reference stickman's head sits directly on its
        # shoulders with no neck gap, and the drawn total height is H.
        head_x = neck_x + math.sin(lean + p["head_look"]) * self.head_r * 0.6
        head_y = neck_y - math.cos(lean + p["head_look"]) * self.head_r * 0.6
        J = {"hip": (hip_x, hip_y), "shoulder": (sh_x, sh_y),
             "neck": (neck_x, neck_y), "head": (head_x, head_y),
             "facing": f}
        # --- legs: IK when a foot target is set, else FK ---
        for side, thigh, knee in (("l", p["thigh_l"], p["knee_l"]),
                                  ("r", p["thigh_r"], p["knee_r"])):
            tgt = self.foot_target_l if side == "l" else self.foot_target_r
            if tgt is not None:
                tgt = clamped_target(hip_x, hip_y, tgt[0], tgt[1],
                                     self.u_leg + self.l_leg)
                # knee bends forward (toward facing) in side view
                kx, ky = ik_2bone(hip_x, hip_y, tgt[0], tgt[1],
                                  self.u_leg, self.l_leg, bend=f)
                J[f"knee_{side}"] = (kx, ky)
                J[f"foot_{side}"] = tgt
            else:
                a1 = thigh  # thigh angle from vertical, + forward
                kx = hip_x + math.sin(a1) * self.u_leg
                ky = hip_y + math.cos(a1) * self.u_leg
                a2 = a1 - knee  # shin bends backward relative to thigh
                fx = kx + math.sin(a2) * self.l_leg
                fy = ky + math.cos(a2) * self.l_leg
                J[f"knee_{side}"] = (kx, ky)
                J[f"foot_{side}"] = (fx, fy)
        # --- arms: FK, or IK when a hand target is set ---
        for side, arm, elbow in (("l", p["arm_l"], p["elbow_l"]),
                                 ("r", p["arm_r"], p["elbow_r"])):
            tgt = self.hand_target_l if side == "l" else self.hand_target_r
            if tgt is not None:
                tgt = clamped_target(sh_x, sh_y, tgt[0], tgt[1],
                                     self.u_arm + self.l_arm)
                # elbow hangs BELOW the shoulder->hand line (toward the
                # ground) for a natural forward reach; bend follows facing.
                ex, ey = ik_2bone(sh_x, sh_y, tgt[0], tgt[1],
                                  self.u_arm, self.l_arm, bend=f)
                J[f"elbow_{side}"] = (ex, ey)
                J[f"hand_{side}"] = tgt
            else:
                a1 = arm  # arm angle from straight down, + forward
                ex = sh_x + math.sin(a1) * self.u_arm
                ey = sh_y + math.cos(a1) * self.u_arm
                a2 = a1 - elbow
                hx = ex + math.sin(a2) * self.l_arm
                hy = ey + math.cos(a2) * self.l_arm
                J[f"elbow_{side}"] = (ex, ey)
                J[f"hand_{side}"] = (hx, hy)
        return J


def walk_pose(phase, stride=0.55, amp=0.5):
    """Walk-cycle joint angles. phase in radians; one full cycle = 2 steps.
    Returns dict of thigh/knee/arm angles + bob. Foot contacts happen at
    phase 0 and pi (each foot in turn).

    Bob phase (fixed by the 2026-11-11 animation audit): the body is
    LOWEST at foot contact / double support (phase 0, pi) and HIGHEST
    at mid-stance (phase pi/2, 3pi/2) -- Richard Williams' walk cycle
    (Contact, Down, Passing, Up). The old bob ``10*abs(cos)`` peaked
    exactly at foot strike, i.e. the walk was upside-down.
    """
    s = math.sin(phase)
    c = math.cos(phase)
    return {
        "thigh_l": amp * s,
        "thigh_r": -amp * s,
        # knee bends when the leg is swinging back / lifting
        "knee_l": max(0.0, -0.9 * c) + 0.15,
        "knee_r": max(0.0, 0.9 * c) + 0.15,
        "arm_l": -0.45 * s,
        "arm_r": 0.45 * s,
        "elbow_l": 0.25,
        "elbow_r": 0.25,
        "bob": 10.0 * abs(s),
        "torso_lean": 0.08,
    }


# ---------------------------------------------------------------------------
# Rig validation helpers (PREMIUM_STICKMAN v4, §3).
#
# These are pure checks on a joint map: they never move a joint, so a
# test can assert them on every frame of a timeline. A violation is a
# string; an empty list means the frame is clean.
# ---------------------------------------------------------------------------

def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def bone_lengths(joints):
    """Bone lengths of a joint map: torso, both legs, both arms."""
    return {
        "torso": _dist(joints["hip"], joints["shoulder"]),
        "upper_leg_l": _dist(joints["hip"], joints["knee_l"]),
        "lower_leg_l": _dist(joints["knee_l"], joints["foot_l"]),
        "upper_leg_r": _dist(joints["hip"], joints["knee_r"]),
        "lower_leg_r": _dist(joints["knee_r"], joints["foot_r"]),
        "upper_arm_l": _dist(joints["shoulder"], joints["elbow_l"]),
        "lower_arm_l": _dist(joints["elbow_l"], joints["hand_l"]),
        "upper_arm_r": _dist(joints["shoulder"], joints["elbow_r"]),
        "lower_arm_r": _dist(joints["elbow_r"], joints["hand_r"]),
    }


def expected_bone_lengths(char):
    """Bone lengths a character of this height must have (from the rig)."""
    return {
        "torso": char.torso,
        "upper_leg_l": char.u_leg, "lower_leg_l": char.l_leg,
        "upper_leg_r": char.u_leg, "lower_leg_r": char.l_leg,
        "upper_arm_l": char.u_arm, "lower_arm_l": char.l_arm,
        "upper_arm_r": char.u_arm, "lower_arm_r": char.l_arm,
    }


def check_bone_lengths(joints, char, tol=2.0):
    """Every bone must keep its rig length (no stretching between frames)."""
    got = bone_lengths(joints)
    want = expected_bone_lengths(char)
    return [f"bone {k} is {v:.1f}, expected {want[k]:.1f}"
            for k, v in got.items() if abs(v - want[k]) > tol]


def check_foot_contact(joints, ground_y, tol=3.0, stance=("l", "r")):
    """Each stance foot must sit ON the ground line (not float, not sink).

    A foot in the air is only legal mid-stride; callers pass the stance
    foot/feet for the frame they check (e.g. the foot at phase 0 / pi).
    """
    bad = []
    for side in stance:
        fy = joints[f"foot_{side}"][1]
        if fy < ground_y - tol:
            bad.append(f"foot_{side} floats {ground_y - fy:.1f}px above ground")
        elif fy > ground_y + tol:
            bad.append(f"foot_{side} sinks {fy - ground_y:.1f}px below ground")
    return bad


def check_hand_contact(joints, hand, target, tol=3.0):
    """A hand that must touch a prop (hold / give / take) must be at the
    prop position within tolerance. ``hand`` is 'l' or 'r'."""
    got = joints[f"hand_{hand}"]
    d = _dist(got, target)
    if d > tol:
        return [f"hand_{hand} is {d:.1f}px from prop at {target}, "
                f"expected within {tol}px"]
    return []


def validate_joints(joints, char, ground_y=None, tol=2.0):
    """All rig invariants for one frame: bone lengths, and (when a ground
    line is given) both feet planted. Returns a list of violations."""
    bad = check_bone_lengths(joints, char, tol=tol)
    if ground_y is not None:
        bad += check_foot_contact(joints, ground_y, tol=max(tol, 3.0))
    return bad


def plant_feet(char, ground_y, stance="both"):
    """Pin the stance foot/feet exactly onto ``ground_y`` via IK targets,
    under the character's current root_x. ``stance``: 'both' | 'l' | 'r'.

    Call this after set_pose for any standing pose: it guarantees the
    feet touch the ground instead of floating a few px above it (the
    old failure mode when root_y was rounded or bob was applied).

    The foot spread is clamped to what the legs can actually reach:
    with the hip at ``ground_y - leg_length`` ANY horizontal spread
    makes the target unreachable and the IK clamp floats the feet
    (v3's ~10px float in front view). Standing callers must set
    ``root_y = ground_y - 0.93 * (u_leg + l_leg)`` (as walk_to does)
    so the legs are slightly bent and the full spread is reachable;
    if they did not, the spread shrinks instead of the feet floating.
    """
    x = char.pose["root_x"]
    hip_y = char.pose["root_y"]
    reach = char.u_leg + char.l_leg
    spread = 0.06 * char.H
    dv = ground_y - hip_y
    # Max horizontal offset the legs can reach at this hip height
    # (98% of reach, matching the IK clamp in joints()).
    max_spread = math.sqrt(max(0.0, (0.98 * reach) ** 2 - dv * dv))
    spread = min(spread, max_spread)
    if stance in ("both", "l"):
        char.foot_target_l = (x - spread, ground_y)
    if stance in ("both", "r"):
        char.foot_target_r = (x + spread, ground_y)
    return char


def head_track(char, target, max_angle=0.6):
    """Turn the head toward ``target`` (x, y): set head_look to the angle
    between the head and the target, clamped to +/-max_angle so the head
    never snaps past its neck. Returns the applied angle.

    v5 (animation audit 2026-11-11): the old code returned the raw
    target angle as head_look, but the head's direction is
    ``lean + head_look`` (see joints()), so the look must be the
    target angle RELATIVE to the lean -- and wrapped to [-pi, pi].
    Without the wrap, a target BELOW the head (a wallet on the ground)
    gives an angle near +/-pi, and the sign flips every time the head
    crosses the target's vertical line: head_look jumped +0.6 / -0.6
    frame to frame and the head oscillated +/-60 px while the body
    stood up from the bend. With the wrap, both sides give the same
    look-down value and the head moves smoothly.
    """
    J = char.joints()
    hx, hy = J["head"]
    dx, dy = target[0] - hx, target[1] - hy
    angle = math.atan2(dx, -dy)  # direction to target, 0 = straight up
    lean = char.pose.get("torso_lean", 0.0)
    diff = (angle - lean + math.pi) % (2 * math.pi) - math.pi
    diff = max(-max_angle, min(max_angle, diff))
    char.set_pose(head_look=diff)
    return diff


def interp_pose(pose_a, pose_b, u):
    """Smoothstep-interpolated pose between two pose dicts.

    Numeric values are lerped; ``facing`` flips at the midpoint (a head
    never half-turns). Keys present in only one pose keep their value.
    """
    u = smoothstep(u)
    out = dict(pose_a)
    for key, vb in pose_b.items():
        va = pose_a.get(key, vb)
        if key == "facing":
            out[key] = vb if u >= 0.5 else va
        elif isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            out[key] = lerp(va, vb, u)
        else:
            out[key] = vb if u >= 0.5 else va
    return out


def pose_at(keyframes, t):
    """Pose at time ``t`` from ``[(time, pose_dict), ...]`` keyframes,
    smoothstep-interpolated between the bracketing keyframes."""
    if t <= keyframes[0][0]:
        return dict(keyframes[0][1])
    if t >= keyframes[-1][0]:
        return dict(keyframes[-1][1])
    for (t0, p0), (t1, p1) in zip(keyframes, keyframes[1:]):
        if t0 <= t <= t1:
            return interp_pose(p0, p1, (t - t0) / (t1 - t0))
    return dict(keyframes[-1][1])
