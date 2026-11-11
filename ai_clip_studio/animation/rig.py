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
TORSO_FRAC = 0.32
UPPER_LEG_FRAC = 0.23
LOWER_LEG_FRAC = 0.23
UPPER_ARM_FRAC = 0.20
LOWER_ARM_FRAC = 0.19
SHOULDER_HALF_FRAC = 0.09   # half shoulder width
HIP_HALF_FRAC = 0.06


def ik_2bone(ax, ay, tx, ty, l1, l2, bend=+1):
    """Two-bone IK: anchor (ax,ay), target (tx,ty), lengths l1,l2.
    bend=+1 puts the middle joint on one side of the anchor->target line,
    bend=-1 on the other. Returns (mx,my) middle joint, clamped to reach."""
    dx, dy = tx - ax, ty - ay
    d = math.hypot(dx, dy)
    d = max(1.0, min(d, l1 + l2 - 0.5))
    # unit vector anchor->target
    ux, uy = dx / math.hypot(dx, dy), dy / math.hypot(dx, dy)
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
                 hat="bowler", moustache=True, name="lustig"):
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
