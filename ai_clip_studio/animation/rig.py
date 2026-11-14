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
BODY_WIDTH_SCALE = {"slim": 0.9, "standard": 1.0, "sturdy": 1.15,
                    "massive": 1.30}
# "massive" (Test F, 2026-11-12): a general large-build variant for
# characters whose script traits declare a massive / giant build
# (BODY_TYPE "large muscular", "massive", ...). The same locked rule
# applies: torso + limb widths scale TOGETHER, so line thickness
# stays uniform within one character. Height scale is separate
# (the scale-variant mechanism); a massive character is wide, and
# may additionally be tall. trait_derivation maps script BODY_TYPE
# text to this variant (ATLAS wiring); the rig only honours it.

# Moustache styles (v8, animation audit 2026-11-11): a character's
# signature facial trait, carried as template data. See Stickman.
MOUSTACHE_STYLES = ("none", "toothbrush", "handlebar", "full")

# Species-feature vocabulary (generic visual profile, 2026-11-13).
# A character's non-human features are DATA, carried like the moustache
# style -- never a name or story lookup. These closed sets are the
# drawing vocabulary; trait_derivation keeps an identical mirror and a
# sync test pins them together. "none" is the default for every
# character, so an existing character draws exactly as before.
EAR_SHAPES = ("none", "round", "pointed", "long", "wing")
TAIL_SHAPES = ("none", "monkey", "curled", "bushy", "long", "tuft")
HORN_SHAPES = ("none", "small", "curved", "antlers", "crown")
FACE_MARKING_STYLES = ("none", "brow_patch", "cheek_stripes", "muzzle",
                       "war_paint")

# Hair styles (v8): "short" | "long" | "tuft" | "side_part" (hair
# parted on one side -- a slanted hairline, a signature trait for
# historical-figure-style test instances).
HAIR_STYLES = ("short", "long", "tuft", "side_part")

# Canonical standing foot split (v7, animation audit 2026-11-11): the
# feet stand +/-STAND_SPLIT_FRAC*H around the root in EVERY standing
# pose -- plant_feet, idle, the walk's start/end split (+/-step/2 with
# the v6 step 0.25*H) and kneel_pick's rise. Before v7 each caller
# used a different spread (plant_feet 0.06H, idle +/-45 px, walk
# +/-0.125H), so every segment blend slid the feet along the ground
# (walk_hold -> handover: +/-98 px -> +/-47 px). One split everywhere
# means a blend starts where the previous segment ended.
STAND_SPLIT_FRAC = 0.125


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
    # Clamp to the reach annulus: too far stretches the chain (the
    # old too-far clamp); too close (|l1-l2|) folds it back on
    # itself and the old code stretched bone 1 past l1 (W4 rig
    # hardening — a hand target inside the annulus must fold, never
    # stretch). The middle joint then sits at the folded geometry
    # and both bone lengths stay exact.
    d = max(max(1.0, abs(l1 - l2) + 0.5),
            min(raw_d, l1 + l2 - 0.5))
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


# Gait parameters (v6: ONE shared gait, RicksClips reference study
# 2026-11-11 -- every character walks the same short-step, level-head
# idiom; characters are distinguished by COSTUME colour, hat and hair,
# NOT by gait. The v5 per-template gaits (Minh strides, Lan steps
# shorter, elder shuffles) contradicted the reference and are no
# longer used by walk_to/run_to. Template `gait` data still exists on
# the character objects but locomotion ignores it; do not reintroduce
# per-template stride/cadence without a new reference finding.
#   stride_frac: step length as a fraction of total height H.
#     Reference: SHORT steps, ~1/4-1/3 body height, a few strides per
#     2-5 s insert, pace ~70-90 steps/min (estimate from visible
#     strides, not a measurement). v5 used 0.16 H at 115/min -- too
#     fast and too shuffly; v6 uses 0.25 H at ~80/min.
#   arm_amp: arm-swing amplitude in radians. Reference: arms do NOT
#     swing -- both hands are committed to a task; if they swing at
#     all, keep it SMALL and opposite to the legs. v6 cuts 0.45->0.25.
#   lean: forward torso lean in radians while walking. Reference:
#     weight is sold by forward LEAN into effort, not by bob.
#   bob_frac: vertical COM excursion as a fraction of leg length.
#     Reference: the head stays almost LEVEL -- v5's +9.6 px bob was
#     too much. v6 keeps the phase (lowest at strike, highest at
#     mid-stance) but cuts the amplitude to ~5 px.
#   lift_frac: max foot lift during swing, fraction of H (heel raised
#     on the swing, flat on the plant).
#   overlap: fraction of a step the old foot stays planted AFTER the
#     other foot strikes (+0.20 = 20% double support, a walk;
#     negative = flight phase, a run).
GAIT_DEFAULT = {
    # "stride_frac" is a LEGACY alias for the STEP length (one
    # footfall): strikes are step apart, same-foot strikes 2*step
    # apart (see primitives._foot_state). New code uses the explicit
    # step_length_frac / stride_length_frac keys; stride_frac is
    # kept equal to the step length for the proven core.
    "stride_frac": 0.25,
    "step_length_frac": 0.25,
    "stride_length_frac": 0.50,
    "arm_amp": 0.25,
    "lean": 0.12,
    "bob_frac": 0.015,
    "lift_frac": 0.05,
    "overlap": 0.20,
}

# Run gait: longer stride, real flight phase (overlap < 0), more lean,
# bigger arm pump. A run is a SHORT shot, not a sped-up walk cycle
# (the reference narrates runs; it does not show a run cycle).
# F10 (TEST C Phase 2, 2026-11-12): the v9 run still READ as a walk
# in still frames (Phase 1: torso upright, walking stride, no clear
# forward lean). The run must read as a run in a single frame: lean
# 0.22 -> 0.40 rad (~23 deg, the trunk clearly ahead of the hips),
# arm pump 0.45 -> 0.60, flight lift 0.03 -> 0.05 and swing lift
# 0.06 -> 0.09 (the swing knee tucks visibly). The overlap stays
# -0.30 (the flight phase already exists; the problem was the pose,
# not the airborne time). The stride stays 0.28: the run's stand
# split tracks step/2, and a longer stride makes the settle sprint
# the feet (stride 0.29 -> settle 32.3 px/frame, 0.30 -> 37.0, over
# the 30 px/frame smoothness bound; 0.28 -> 27.5). Readability comes
# from the lean, the arm drive and the flight/tuck, not from a
# longer stride. Short 2-5 s inserts only -- the reference has no
# sustained run cycle.
GAIT_RUN = {
    "stride_frac": 0.28,
    "step_length_frac": 0.28,
    "stride_length_frac": 0.56,
    "arm_amp": 0.60,
    "lean": 0.40,
    "bob_frac": 0.02,
    "lift_frac": 0.09,
    "overlap": -0.30,
    "flight_lift_frac": 0.05,
}


class Stickman:
    """A V51 stickman. Pose is set per frame via `pose` dict, then `joints()`."""

    def __init__(self, height=560, suit="#172033", skin="#F3F0E8",
                 hat="bowler", moustache=True, moustache_style=None,
                 name="lustig",
                 template="male", body_variant="standard",
                 hair_style=None, glasses=False, cane=False,
                 costume="none", gait=None, gait_profile=None,
                 eye_count=2, ears="none", tail="none", horns="none",
                 face_markings="none"):
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
        # v8 (animation audit 2026-11-11): moustache STYLES -- a
        # character's signature trait is data, not a per-story
        # drawing. Styles: "none" | "toothbrush" (small dark block
        # under the nose) | "handlebar" (wide, upturned ends) |
        # "full" (solid band above the mouth). ``moustache`` (bool)
        # is kept for backward compatibility: True with no style
        # means "full", False means "none".
        if moustache_style is None:
            moustache_style = "full" if moustache else "none"
        if moustache_style not in MOUSTACHE_STYLES:
            raise ValueError(
                f"unknown moustache_style: {moustache_style!r} "
                f"(expected one of {sorted(MOUSTACHE_STYLES)})")
        self.moustache_style = moustache_style
        self.moustache = moustache_style != "none"
        # eye_count (Test F, 2026-11-12): a general face trait, 1 or 2.
        # A single central eye is a script-declared distinctive
        # feature (e.g. a one-eyed giant); the face drawing honours
        # it (one larger centred eye, same line language, same
        # expression parameters). Default 2 reproduces every
        # existing character exactly. Any other value is a data
        # error, raised loudly like an unknown moustache style.
        if eye_count not in (1, 2):
            raise ValueError(
                f"unknown eye_count: {eye_count!r} (expected 1 or 2)")
        self.eye_count = int(eye_count)
        # Species features (generic visual profile): closed vocabularies
        # validated loudly, like moustache_style. "none" draws nothing.
        for _label, _value, _allowed in (
                ("ears", ears, EAR_SHAPES),
                ("tail", tail, TAIL_SHAPES),
                ("horns", horns, HORN_SHAPES),
                ("face_markings", face_markings, FACE_MARKING_STYLES)):
            if _value not in _allowed:
                raise ValueError(
                    f"unknown {_label}: {_value!r} "
                    f"(expected one of {sorted(_allowed)})")
        self.ears = ears
        self.tail = tail
        self.horns = horns
        self.face_markings = face_markings
        self.name = name
        # PREMIUM_STICKMAN v4 identity (see animation/character_art.py).
        # template: male | female | child | elderly. body_variant scales
        # torso/limb widths TOGETHER (slim 0.9 / standard 1.0 / sturdy
        # 1.15 / massive 1.30) so line thickness stays uniform within
        # one character.
        self.template = template
        self.body_variant = body_variant
        self.width_scale = BODY_WIDTH_SCALE.get(body_variant, 1.0)
        # hair_style: None (use template default) | short | long | tuft.
        self.hair_style = hair_style
        self.glasses = glasses
        self.cane = cane
        # costume: "none" | "dress" (dress extends the torso A-line).
        self.costume = costume
        # gait: v6 (RicksClips reference study 2026-11-11) -- locomotion
        # uses ONE shared gait (GAIT_DEFAULT / GAIT_RUN); characters
        # are told apart by costume, hat and hair, not by how they
        # walk. The per-template gait dicts below are kept as data
        # (and still stored here) but walk_to/run_to deliberately do
        # not read them. See GAIT_DEFAULT.
        self.gait = dict(GAIT_DEFAULT)
        if gait:
            self.gait.update(gait)
        # gait_profile (D1, Cinematic Engine Upgrade 2026-11-12): an
        # optional GaitProfile, preset name, or gait dict carried by
        # the character. walk_to/run_to/walk_mud read it when no
        # explicit profile is passed; None = the legacy shared gait.
        # Stored as given (no contract import here); locomotion.py
        # resolves it. The per-template gait dicts above remain
        # unread -- parametric profiles are the D1 mechanism.
        self.gait_profile = gait_profile
        # pose defaults (angles in radians; + = forward / toward facing)
        self.pose = {
            "root_x": 960.0, "root_y": 900.0, "facing": 1,
            "torso_lean": 0.0, "head_look": 0.0, "head_pitch": 0.0,
            "thigh_l": 0.0, "thigh_r": 0.0, "knee_l": 0.0, "knee_r": 0.0,
            "arm_l": 0.0, "arm_r": 0.0, "elbow_l": 0.0, "elbow_r": 0.0,
            "bob": 0.0,
            # head_sway_x (v8, animation audit 2026-11-11): secondary
            # motion -- the head lags the torso by a few px during
            # anticipation (dips back before the body moves) and
            # follow-through (overshoots forward after the body stops).
            # Set by _locomote; 0.0 = head rigid on the torso (v7).
            "head_sway_x": 0.0,
            # turn_u: 0 = not turning (profile view, facing as set);
            # 1 = turn complete. Mid-turn (0.5) the character is
            # front-on -- see character_art.resolve_view(). Set by
            # turn_to and by _locomote when a walk starts facing the
            # wrong way. A turn is a visible rotation, never an
            # instant facing flip.
            "turn_u": 0.0,
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
        head_x = (neck_x + math.sin(lean + p["head_look"]) * self.head_r * 0.6
                  + p.get("head_sway_x", 0.0))
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
                # Knee bends FORWARD (toward facing) in side view.
                # v6 (backwards-walk audit 2026-11-11): this used
                # bend=f, which puts the knee on the WRONG side of the
                # hip->foot line -- the knee sat 60-110 px BEHIND the
                # line in every walk frame, so the legs read as bending
                # backwards (the "di nguoc" Mai reported) even though
                # the face pointed the right way. ik_2bone's bend=+1
                # offsets the middle joint toward (-uy, +ux); for a leg
                # pointing down-forward that is the BACKWARD side, so
                # the knee needs bend=-f. (Arms keep bend=f: an elbow
                # hangs BELOW/BEHIND the shoulder->hand line, which is
                # what bend=+1 gives for a forward reach.)
                kx, ky = ik_2bone(hip_x, hip_y, tgt[0], tgt[1],
                                  self.u_leg, self.l_leg, bend=-f)
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


def walk_pose(phase, stride=0.55, amp=0.5, profile=None):
    """Walk-cycle joint angles. phase in radians; one full cycle = 2 steps.
    Returns dict of thigh/knee/arm angles + bob. Foot contacts happen at
    phase 0 and pi (each foot in turn).

    Bob phase (fixed by the 2026-11-11 animation audit): the body is
    LOWEST at foot contact / double support (phase 0, pi) and HIGHEST
    at mid-stance (phase pi/2, 3pi/2) -- Richard Williams' walk cycle
    (Contact, Down, Passing, Up). The old bob ``10*abs(cos)`` peaked
    exactly at foot strike, i.e. the walk was upside-down.

    With no ``profile`` the output is the legacy formula, unchanged.
    With a ``profile`` (a GaitProfile, a preset name, or a gait dict
    with step_length_frac/arm_pose/head_stability/posture keys) the
    SAME formula is driven by the profile: thigh amplitude from the
    step length (asin of half-step / leg length), arm amplitude and
    pose from arm_pose, bob from head_stability, lean from posture.
    This is a parameterization of one engine, not a second walk
    system. The rendered engine is ``primitives._locomote``
    (planted-foot, space-based); this helper is for analytic /
    prototype use.
    """
    s = math.sin(phase)
    c = math.cos(phase)
    if profile is None:
        thigh_amp = amp
        arm_mode = "swing"
        arm_amp = 0.45
        bob_scale = 1.0
        lean = 0.08
        elbows = (0.25, 0.25)
    else:
        if isinstance(profile, dict):
            step = float(profile.get(
                "step_length_frac", profile.get("stride_frac", 0.29)))
            arm_mode = profile.get("arm_pose", "swing")
            head_stability = float(profile.get("head_stability", 1.0))
            posture = profile.get("posture", "upright")
            arm_amp = float(profile.get("arm_amp", 0.45))
        else:
            from .locomotion import resolve_gait_profile
            resolved = resolve_gait_profile(profile)
            step = resolved.step_length
            arm_mode = resolved.arm_pose
            head_stability = resolved.head_stability
            posture = resolved.posture
            arm_amp = 0.45
        leg_frac = UPPER_LEG_FRAC + LOWER_LEG_FRAC
        thigh_amp = math.asin(min(1.0, (step / 2.0) / leg_frac))
        bob_scale = max(0.15, 1.15 - head_stability)
        lean = {"upright": 0.08, "stooped": 0.22,
                "military": 0.04, "regal": 0.06}.get(posture, 0.08)
        elbows = (0.25, 0.25)
    if arm_mode == "carrying":
        arm_l = arm_r = 0.55
        elbows = (0.90, 0.90)
    elif arm_mode == "task":
        arm_l = 0.08 + 0.25 * arm_amp * s
        arm_r = 0.08 - 0.25 * arm_amp * s
        elbows = (0.35, 0.35)
    elif arm_mode == "restrained":
        arm_l = 0.10 * arm_amp * s
        arm_r = -0.10 * arm_amp * s
        elbows = (0.15, 0.15)
    else:  # swing
        arm_l = -arm_amp * s
        arm_r = arm_amp * s
    return {
        "thigh_l": thigh_amp * s,
        "thigh_r": -thigh_amp * s,
        # knee bends when the leg is swinging back / lifting
        "knee_l": max(0.0, -0.9 * c) + 0.15,
        "knee_r": max(0.0, 0.9 * c) + 0.15,
        "arm_l": arm_l,
        "arm_r": arm_r,
        "elbow_l": elbows[0],
        "elbow_r": elbows[1],
        "bob": 10.0 * abs(s) * bob_scale,
        "torso_lean": lean,
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
    # v7: the canonical standing split (see STAND_SPLIT_FRAC) -- the
    # same +/-0.125H the walk starts/ends in, so blends do not slide
    # the feet. Reachable at the standard standing hip height
    # (ground - 0.93*leg): max spread is ~0.132H at any H.
    spread = STAND_SPLIT_FRAC * char.H
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
