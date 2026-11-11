"""12-joint stickman rig, V51 proportions, frame-by-frame animation.

Proportions follow the V51 standard (see motioncanvas/contract/CharacterDNA.ts
and components/CanonicalStickmanRig.ts in the upstream repo):
  total height 300 px, headRatio 0.142-0.155, torso 96 px (lumbar 48 + chest 48),
  limbThicknessPx 7-16. Here the rig is scaled to a screen height H (default
  560 px at 1080p), so head = 0.146*H, torso = 0.32*H.

The character is drawn in side view (profile), facing +1 (right) or -1 (left).
Joints are computed every frame from a pose; nothing is a static image.

Two-bone IK is used for hands and feet when a target is given (reach, plant,
hand-to-face). Swing limbs use FK from joint angles. Every frame returns the
full joint map so motion can be measured (joint displacement per frame).
"""
import math

# --- V51 proportions (fractions of total height) ---
HEAD_RATIO = 0.146
HEAD_RATIO_MIN = 0.142  # V51 standard range; the schema allows 0.20-0.35
HEAD_RATIO_MAX = 0.155  # but the rig locks to 0.142-0.155 (see STYLE_LOCK)
TORSO_FRAC = 0.32
UPPER_LEG_FRAC = 0.23
LOWER_LEG_FRAC = 0.23
UPPER_ARM_FRAC = 0.20
LOWER_ARM_FRAC = 0.19
SHOULDER_HALF_FRAC = 0.09   # half shoulder width
HIP_HALF_FRAC = 0.06

# Body-variant width scale. ONE scale multiplies torso width AND limb
# width together, so a sturdy character is uniformly thicker, never a
# thin arm on a wide torso (PREMIUM_STICKMAN v3 line rule).
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


class Stickman:
    """A V51 stickman. Pose is set per frame via `pose` dict, then `joints()`."""

    def __init__(self, height=560, suit="#172033", skin="#F3F0E8",
                 hat="bowler", moustache=True, name="lustig",
                 template="male", body_variant="standard",
                 hair_style=None, glasses=False, cane=False,
                 costume="none"):
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
        # PREMIUM_STICKMAN v3 identity (see animation/character_art.py).
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
        head_x = neck_x + math.sin(lean + p["head_look"]) * self.head_r * 1.1
        head_y = neck_y - math.cos(lean + p["head_look"]) * self.head_r * 1.1
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
    phase 0 and pi (each foot in turn)."""
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
        "bob": 10.0 * abs(c),
        "torso_lean": 0.08,
    }


# ---------------------------------------------------------------------------
# Rig validation helpers (PREMIUM_STICKMAN v3, §3).
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
    """
    x = char.pose["root_x"]
    spread = 0.06 * char.H
    if stance in ("both", "l"):
        char.foot_target_l = (x - spread, ground_y)
    if stance in ("both", "r"):
        char.foot_target_r = (x + spread, ground_y)
    return char


def head_track(char, target, max_angle=0.6):
    """Turn the head toward ``target`` (x, y): set head_look to the angle
    between the head and the target, clamped to +/-max_angle so the head
    never snaps past its neck. Returns the applied angle."""
    J = char.joints()
    hx, hy = J["head"]
    dx, dy = target[0] - hx, target[1] - hy
    angle = math.atan2(dx, -dy)  # 0 = straight ahead/up, + = toward facing
    angle = max(-max_angle, min(max_angle, angle))
    char.set_pose(head_look=angle)
    return angle


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
