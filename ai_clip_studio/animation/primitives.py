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
take_from, open_door, sit_down, stand_up, shrug, cover_face, nod, wave,
idle (breathing / weight shift for a standing character), bend_pick
(natural knee-bend pickup with held contact).
Every primitive moves real joints over time; bone lengths are invariant
(checked in tests/test_animation_primitives.py).

v5 (animation audit 2026-11-11): walk/run rebuilt on PLANTED FEET --
the v4 walk slid 481 px per foot in 1.8 s (moonwalking), bobbed
upside-down, and the run had no flight phase. Steps are now defined in
space (fixed world-x strike positions), the body is lowest at foot
strike and highest at mid-stance, arms swing anti-phase with live
elbows, and every hand action starts from the hand's CURRENT position
so segment boundaries no longer teleport hands 100-240 px.
"""
import math

from .rig import (Stickman, walk_pose, interp_keys, smoothstep, lerp,
                  head_track, plant_feet, GAIT_DEFAULT, GAIT_RUN,
                  STAND_SPLIT_FRAC)
from .locomotion import profile_to_gait, resolve_gait_profile


def _pose(char, **kw):
    char.set_pose(**kw)
    return char


def _s(char, px):
    """Scale a pixel offset written for the reference height (560 px) to
    this character's height, so primitives work for a 400 px child as
    well as a 560 px adult (PREMIUM_STICKMAN v4: one proportion system)."""
    return px * float(char.H) / 560.0


def _ease_profile(u, e=0.15):
    """Distance profile for locomotion: eases in over the first ``e`` of
    the walk and out over the last ``e``, linear (constant speed) in
    between. Unlike a whole-walk smoothstep, step TIMING stays even in
    the middle -- the old smoothstep made steps land at 7, 8 and 12
    frame intervals in the v4 audit. p(0)=0, p(1)=1, p(0.5)=0.5 exactly,
    p'(0)=p'(1)=0 (the walk starts and ends at rest)."""
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    v = 1.0 / (1.0 - e)  # cruising speed must exceed the average speed
    if u < e:
        return v * u * u / (2.0 * e)
    if u > 1.0 - e:
        w = 1.0 - u
        return 1.0 - v * w * w / (2.0 * e)
    return v * (u - e / 2.0)


def _foot_state(s, step, overlap, lift, ground_y, from_x, direction,
                offset):
    """One foot's position at path distance ``s`` (px travelled).

    The foot strikes at ``s = offset, offset + 2*step, ...`` (``offset``
    0 for the left foot, ``step`` for the right), lands ``step/2`` ahead
    of the root, and STAYS AT THAT EXACT WORLD X until it lifts -- a
    planted foot never slides. It lifts ``step + overlap*step`` after
    its strike (``overlap`` > 0: double support, a walk; ``overlap``
    < 0: it lifts BEFORE the other foot strikes, a run's flight phase)
    and swings to its next strike with a smoothstep + a vertical lift
    arc. Returns ``(x, y, in_contact, lift_s, next_strike_s)``.
    """
    rel = s - offset
    k = math.floor(rel / (2.0 * step))
    s_strike = offset + 2.0 * k * step
    s_lift = s_strike + step + overlap * step
    s_next = s_strike + 2.0 * step
    x_plant = from_x + direction * (s_strike + step / 2.0)
    x_next = from_x + direction * (s_next + step / 2.0)
    # The first swing must start at s = 0 (the travel start), not
    # before it. For a run (negative overlap) the steady-state lift
    # point s_lift is < 0 for the first cycle, so at s = 0 the foot
    # was already 23% through its swing -- a 62 px jump from the
    # anticipation's stand split and a 77 px knee pop in one frame
    # (rubric C12, present in v6 too at 84.5 px). The foot was
    # planted during the anticipation, so its first swing starts at
    # s = 0; lift0 clamps the lift point for the POSITION only (the
    # returned s_lift stays the steady-state value, so the flight
    # detection in _locomote is unchanged). For a walk (positive
    # overlap) s_lift is already > 0 and nothing changes.
    lift0 = max(s_lift, 0.0)
    if s <= lift0:
        return x_plant, ground_y, True, s_lift, s_next
    q = (s - lift0) / max(1e-9, s_next - lift0)
    q = min(1.0, max(0.0, q))
    x = lerp(x_plant, x_next, smoothstep(q))
    y = ground_y - lift * math.sin(math.pi * q)
    return x, y, False, s_lift, s_next


def _start_moved(char, joint_key, last_target, thresh=50.0):
    """True if someone OTHER than this primitive moved the joint since
    the primitive's last call. Primitives capture their start state on
    the first call ("the hand starts from its CURRENT position") -- but
    a renderer may PRE-WARM a primitive in one pose and only run it
    later, after another segment moved the character: the capture is
    then stale and the hand teleports on the first real frame (v6:
    wave() pre-warmed in the standing pose, run after the handover,
    jumped the hand 94 px in one frame). The guard re-captures the
    start when the joint is far from where this primitive last put it.
    Callers must still warm a primitive in its start pose; this only
    saves the pre-warm case. ``last_target`` is None before the first
    call (nothing to compare against yet)."""
    if last_target is None:
        return False
    cur = char.joints()[joint_key]
    return math.hypot(cur[0] - last_target[0],
                      cur[1] - last_target[1]) > thresh


def _locomote(char, from_x, to_x, duration, ground_y, gait, *,
              phase_name):
    """Shared planted-foot locomotion core (audit 2026-11-11).

    The v4 walk was moonwalking: a 'planted' foot's target moved
    backwards ~75 px per step while the body moved forward 55 px
    (481 px of slip on one foot in 1.8 s). Here the step is defined in
    SPACE, not in time: step length is a gait parameter, each foot
    strikes at a fixed world x and stays there until it lifts, the
    root moves at constant speed (eased only at the ends), the body
    is LOWEST at foot strike / double support and HIGHEST at
    mid-stance (Richard Williams' walk cycle), and the arms swing
    anti-phase with the legs with elbows that bend more on the forward
    swing. A run uses the same core with a longer stride and a
    negative overlap -- a real flight phase where BOTH feet are off
    the ground, instead of the old 'walk + lean'.
    """
    leg = char.u_leg + char.l_leg
    step = gait.get("step_length_frac", gait["stride_frac"]) * float(char.H)
    overlap = gait["overlap"]
    lift = gait["lift_frac"] * float(char.H)
    bob_amp = gait["bob_frac"] * leg
    flight_amp = gait.get("flight_lift_frac", 0.0) * float(char.H)
    arm_amp = gait["arm_amp"]
    # D1 profile parameters (all default to the legacy behaviour when
    # absent, so the proven core is byte-identical without a profile).
    arm_mode = gait.get("arm_pose", "swing")
    sway_scale = gait.get("sway_scale", 1.0)
    ease_scale = gait.get("ease_scale", 1.0)

    def _arms(cyc):
        """(arm_l, arm_r, elbow_l, elbow_r) at cycle value ``cyc``
        (+1 = left arm forward). "swing" is the proven contralateral
        swing; the other modes are D1 parametric variants of the
        same engine -- task (hands committed, small counter-motion),
        carrying (both arms held forward), restrained (near-still)."""
        if arm_mode == "carrying":
            return 0.55, 0.55, 0.90, 0.90
        if arm_mode == "task":
            return (0.08 + 0.25 * arm_amp * cyc,
                    0.08 - 0.25 * arm_amp * cyc, 0.35, 0.35)
        if arm_mode == "restrained":
            return (0.10 * arm_amp * cyc, -0.10 * arm_amp * cyc,
                    0.15, 0.15)
        return (arm_amp * cyc, -arm_amp * cyc,
                0.25 + 0.25 * max(0.0, cyc),
                0.25 + 0.25 * max(0.0, -cyc))
    direction = 1 if to_x >= from_x else -1
    dist = abs(to_x - from_x)
    # Visible turn (v6, backwards-walk audit 2026-11-11): if the
    # character is currently facing the OTHER way, the walk does not
    # snap its facing around at t=0 -- it turns during the 0.2 s
    # anticipation, passing through front view (see
    # character_art.resolve_view). Captured lazily on the first call,
    # because the pose at closure-creation time is the pre-warm pose,
    # not the pose the walk actually starts from.
    _turn = {"start_facing": None, "needed": False}
    # Anticipation foot start (v7): the feet the walk starts from,
    # captured lazily like the turn (the pre-warm pose is not the real
    # start pose). After a CUT the incoming feet may sit at a
    # different split than this gait's stand split (walk +/-0.125H vs
    # run +/-0.14H = 12 px); the anticipation STEPS them there on a
    # lift arc instead of sliding them along the ground (the v6
    # anticipation assumed they already matched and set the targets
    # directly -- after the v7 walk->run cut that slid 12 px and
    # failed the run-slip check).
    # anticipation + settle: the walk starts from a stand (feet
    # together, body at rest) and ends in a stand. Both are short
    # (0.2 s) so the middle of the walk runs at constant speed.
    # v8: the settle is LONGER (0.25 s / 20% of the segment) -- the
    # v7 settle (0.165 s for a 1.1 s run) gathered the feet so fast
    # the foot hit 42 px/frame and the knee jerked 45.7 px/frame^2 at
    # the travel->settle boundary (rubric E7/E2).
    t_ant = min(0.20, duration * 0.15) * ease_scale
    t_set = min(0.25, duration * 0.20) * ease_scale
    if t_ant + t_set > duration * 0.6:
        # A heavy profile on a short segment must not eat the travel.
        scale = duration * 0.6 / (t_ant + t_set)
        t_ant *= scale
        t_set *= scale
    t_travel = max(0.05, duration - t_ant - t_set)
    stand_root_y = ground_y - leg * 0.93
    walk_root_y = ground_y - leg * 0.90
    # Foot offsets: the RIGHT foot strikes first (s = 0, 2*step, ...)
    # and the LEFT foot follows (s = step, 3*step, ...), so at s = 0
    # the right foot is ahead (+step/2) and the left foot behind
    # (-step/2) -- exactly the standing split. The v5-first-draft had
    # the offsets the other way round, so both feet SWAPPED SIDES
    # (126 px each, sliding along the ground) during anticipation.
    off_l, off_r = step, 0.0
    # standing foot positions: the split stance the cycle starts in
    # (right foot +step/2 ahead, left foot -step/2 behind -- exactly
    # the standing split, so the anticipation->travel boundary does
    # not slide the feet). This MUST track step/2: the old fixed
    # +/-45 px spread only matched the v5 step (0.16*H); with the v6
    # step (0.25*H) it would jump the feet ~35 px at travel start.
    stand_fl = (from_x - direction * step / 2.0, ground_y)
    stand_fr = (from_x + direction * step / 2.0, ground_y)
    # Travel-end arm/bob values, so anticipation and settle can lerp
    # TO/FROM them instead of snapping (the first v5 draft set the
    # arms to 0.0 at the settle start -- both hands teleported to the
    # same point, a 132 px jump in one frame).
    cyc_end = math.cos(math.pi * dist / step)
    bob_end = bob_amp * math.sin(math.pi * ((dist / step) % 1.0))
    _fl = _foot_state(dist, step, overlap, lift, ground_y, from_x,
                      direction, off_l)
    _fr = _foot_state(dist, step, overlap, lift, ground_y, from_x,
                      direction, off_r)
    if not _fl[2] and not _fr[2]:
        _fs, _fe = max(_fl[3], _fr[3]), min(_fl[4], _fr[4])
        if _fe > _fs:
            _q = min(1.0, max(0.0, (dist - _fs) / (_fe - _fs)))
            bob_end += flight_amp * math.sin(math.pi * _q)

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        if _turn["start_facing"] is None:
            _turn["start_facing"] = char.pose.get("facing", direction)
            _turn["needed"] = _turn["start_facing"] != direction
        if t < t_ant:
            # anticipation: crouch slightly, lean in, arms swing up
            # from their standing hang to the travel-start swing.
            # The feet STEP (lifted) from where they stand to the
            # cycle's starting split (v7 -- see the _turn comment):
            # they usually already match it within half a pixel and
            # do not move at all; after a cut they step up to 12 px
            # on a lift arc instead of sliding along the ground.
            a = smoothstep(t / max(t_ant, 0.01))
            # Feet start: captured lazily, and RE-captured on the first
            # real frame(s) (t < 0.05, LOCAL time -- not a < 0.05).
            # Two bugs the v7 rubric caught (C12 234 px, cut jump
            # 327 px):
            #  (1) `a < 0.05` misses the first real frame when t_ant
            #      is short: for the 1.1 s run t_ant = 0.165 s, so at
            #      the first run frame (lt = 0.025) a = 0.062 and no
            #      re-capture happened -- the run stepped from the
            #      STALE pre-warm capture (feet at the walk's start x,
            #      445 px away), the IK clamp dragged a foot to
            #      (285, 747), a 327 px teleport across the cut.
            #  (2) a re-capture can also capture the WRONG pose: the
            #      render pre-warms every segment, so at the walk's
            #      first real frame the rig still sits in the LAST
            #      pre-warm pose (standing at the handover x) -- the
            #      feet were ~1000 px from the walk's stand split and
            #      the anticipation swung one 234 px in a frame.
            # The guard below fixes (2): a captured foot is only a
            # real start if it is ON the ground and within one step
            # of this segment's stand split. A stale/unplaced foot
            # (default pose, another segment's pose) is replaced by
            # the stand split (no step); a real previous-segment foot
            # -- e.g. the 12 px walk->run cut difference -- is
            # stepped on the lift arc as intended.
            if not _turn.get("feet_captured") or t < 0.05:
                _ant = char.joints()
                # A real start has the feet SPLIT (one ahead, one
                # behind). An unposed character (fresh rig, or
                # set_pose with no foot targets) has both feet
                # together under the hip -- that is the FK default,
                # not a stance: stepping from it would leave the feet
                # together at t=0 instead of in the stand split (the
                # v3 walk test: both feet at x=500, y=919.24, 0.76 px
                # off the ground). Real segment-end spreads are
                # 154-208 px; the unposed default is 0 px.
                _spread = abs(_ant["foot_l"][0] - _ant["foot_r"][0])
                _split_ok = _spread > 0.15 * step
                for _side, _stand in (("l", stand_fl), ("r", stand_fr)):
                    _cap = _ant["foot_" + _side]
                    if (_split_ok and abs(_cap[1] - ground_y) <= 4.0 and
                            abs(_cap[0] - _stand[0]) <= step):
                        _turn["foot_" + _side] = _cap
                    else:
                        _turn["foot_" + _side] = _stand
                _turn["feet_captured"] = True
            # Arms: CONTRALATERAL with the legs (v6 fix -- the v5
            # walk swung each arm with the SAME-side leg, 37/51 frames
            # ipsilateral, which reads as walking backwards). At the
            # travel start the right foot strikes first, so the LEFT
            # arm is forward: arm_l=+amp, arm_r=-amp. Elbows bend more
            # on the forward swing.
            if _turn["needed"]:
                turn_u = a
                facing_now = (direction if turn_u >= 0.5
                              else _turn["start_facing"])
            else:
                turn_u = 0.0
                facing_now = direction
            ant_l, ant_r, ant_el, ant_er = _arms(1.0)
            _pose(char, root_x=from_x, root_y=lerp(stand_root_y, walk_root_y, a),
                  facing=facing_now, turn_u=turn_u,
                  torso_lean=gait["lean"] * a,
                  bob=-_s(char, 6) * math.sin(math.pi * a),
                  arm_l=lerp(0.08, ant_l, a),
                  arm_r=lerp(0.08, ant_r, a),
                  elbow_l=lerp(0.15, ant_el, a),
                  elbow_r=lerp(0.15, ant_er, a),
                  head_look=0.0,
                  # v8: head ANTICIPATION -- the head dips back a few
                  # px before the body moves (secondary motion). The
                  # v7 head was rigid on the torso (0 frames of lag).
                  # D1: the sway damps with head_stability.
                  head_sway_x=(-_s(char, 6) * math.sin(math.pi * a)
                               * sway_scale))
            for side, stand_xy in (("l", stand_fl), ("r", stand_fr)):
                sx, sy = _turn["foot_" + side]
                gx = lerp(sx, stand_xy[0], a)
                gy = lerp(sy, ground_y, a)
                if abs(stand_xy[0] - sx) > 1.0:
                    # v8: the anticipation step lifts PROPORTIONALLY to
                    # how far the foot actually steps, never the full
                    # gait lift. The v7 code lifted EVERY anticipation
                    # step by the full gait lift (44 px for the run) --
                    # a 12 px sideways step became a 44 px hop, both
                    # feet in the air at once, and the knee velocity
                    # oscillated 31 -> 8 -> 34 -> 4 px/frame (rubric
                    # E1/E2). A 12 px step now lifts ~8 px; a 100 px
                    # step lifts ~35 px.
                    step_lift = min(lift, max(8.0, 0.35 * abs(stand_xy[0] - sx)))
                    gy -= step_lift * math.sin(math.pi * a)
                if side == "l":
                    char.foot_target_l = (gx, gy)
                else:
                    char.foot_target_r = (gx, gy)
            char.hand_target_l = None
            char.hand_target_r = None
            return char
        if t > duration - t_set:
            # settle: the root decelerates, the body rises back to
            # standing, lean / bob / arms fade out FROM their travel
            # values (no snap). v7 gather: the feet STEP (lifted, not
            # slid) from wherever the cycle left them into the
            # canonical standing split (+/-step/2 around to_x) during
            # the settle, so the next segment starts from the same
            # split the walk ends in. The v6 settle FROZE the feet
            # mid-stride; the next segment's blend then dragged them
            # along the ground (walk_hold -> handover slid ~50 px per
            # foot). A foot already on its stand mark stays planted
            # (no pointless lift arc).
            b = smoothstep((t - (duration - t_set)) / max(t_set, 0.01))
            set_l, set_r, set_el, set_er = _arms(cyc_end)
            _pose(char, root_x=to_x, root_y=lerp(walk_root_y, stand_root_y, b),
                  facing=direction, turn_u=0.0,
                  torso_lean=gait["lean"] * (1.0 - b),
                  bob=bob_end * (1.0 - b),
                  arm_l=lerp(set_l, 0.08, b),
                  arm_r=lerp(set_r, 0.08, b),
                  elbow_l=lerp(set_el, 0.15, b),
                  elbow_r=lerp(set_er, 0.15, b),
                  head_look=0.0,
                  # v8: head FOLLOW-THROUGH -- the head overshoots
                  # forward a few px as the body stops and settles
                  # back. The v7 head stopped dead with the hips.
                  # D1: the sway damps with head_stability.
                  head_sway_x=_s(char, 8) * math.sin(math.pi * b)
                  * sway_scale)
            # (named gather_* -- assigning to stand_fl/stand_fr here
            # would make them locals of fn() and shadow the closure
            # variables the anticipation branch uses; the v7 settle
            # test caught the resulting UnboundLocalError.)
            # Gather each foot to its NEAREST canonical split
            # position. The travel can end with the feet SWAPPED (an
            # odd number of steps: the walk_hold covers ~1 step, so
            # foot_l ends ahead and foot_r behind) -- gathering
            # foot_l to the behind mark and foot_r to the ahead mark
            # would make the feet CROSS (196 px in 4 frames, a 72 px
            # per-frame pop, rubric C12). The feet are already in a
            # valid standing split, just swapped; a standing split
            # does not care which foot is ahead. The assignment that
            # minimises total foot travel is the correct one.
            split_a = (to_x - direction * step / 2.0, ground_y)
            split_b = (to_x + direction * step / 2.0, ground_y)
            if (abs(_fl[0] - split_a[0]) + abs(_fr[0] - split_b[0])
                    <= abs(_fl[0] - split_b[0])
                    + abs(_fr[0] - split_a[0])):
                gather_fl, gather_fr = split_a, split_b
            else:
                gather_fl, gather_fr = split_b, split_a
            for side, end_xy, gather_xy in (
                    ("l", _fl[:2], gather_fl), ("r", _fr[:2], gather_fr)):
                gx = lerp(end_xy[0], gather_xy[0], b)
                gy = lerp(end_xy[1], ground_y, b)
                if abs(gather_xy[0] - end_xy[0]) > 1.0:
                    # v8: proportional gather lift (see anticipation)
                    # -- the v7 full-lift gather (44 px) in a 0.165 s
                    # settle drove the foot to 42 px/frame.
                    gather_lift = min(
                        lift, max(8.0, 0.35 * abs(gather_xy[0] - end_xy[0])))
                    gy -= gather_lift * math.sin(math.pi * b)
                if side == "l":
                    char.foot_target_l = (gx, gy)
                else:
                    char.foot_target_r = (gx, gy)
            char.hand_target_l = None
            char.hand_target_r = None
            return char
        # travelling: distance from the eased profile, phase from distance.
        s = dist * _ease_profile((t - t_ant) / t_travel)
        root_x = from_x + direction * s
        fl_x, fl_y, fl_c, fl_lift, fl_next = _foot_state(
            s, step, overlap, lift, ground_y, from_x, direction, off_l)
        fr_x, fr_y, fr_c, fr_lift, fr_next = _foot_state(
            s, step, overlap, lift, ground_y, from_x, direction, off_r)
        # bob: lowest at contact (s = k*step), highest at mid-stance.
        frac = (s / step) % 1.0
        bob = bob_amp * math.sin(math.pi * frac)
        # flight phase: both feet off the ground -- the body rises to
        # a flight apex between push-off and landing.
        if not fl_c and not fr_c:
            f_start = max(fl_lift, fr_lift)
            f_end = min(fl_next, fr_next)
            if f_end > f_start:
                q = min(1.0, max(0.0, (s - f_start) / (f_end - f_start)))
                bob += flight_amp * math.sin(math.pi * q)
        # arms CONTRALATERAL with the legs (v6 fix -- see anticipation
        # above): when the right foot is forward, the LEFT arm is
        # forward. Elbows bend more on the forward swing.
        cyc = math.cos(math.pi * s / step)
        trav_l, trav_r, trav_el, trav_er = _arms(cyc)
        _pose(char, root_x=root_x, root_y=walk_root_y,
              facing=direction, turn_u=0.0, torso_lean=gait["lean"], bob=bob,
              arm_l=trav_l, arm_r=trav_r,
              elbow_l=trav_el,
              elbow_r=trav_er,
              head_look=0.0)
        char.foot_target_l = (fl_x, fl_y)
        char.foot_target_r = (fr_x, fr_y)
        char.hand_target_l = None
        char.hand_target_r = None
        return char
    return fn


def _profile_gait(char, profile, run=False, terrain="flat"):
    """Gait dict for a locomotion primitive from a D1 profile.

    Resolution: explicit ``profile`` > the character's carried
    ``gait_profile`` > None (the caller then uses the legacy gait
    dict, byte-identical to the pre-D1 behaviour). ``profile`` is a
    GaitProfile, a preset name ("canonical" / "elderly" / "soldier" /
    "giant" / "civilian"), or a gait dict (passed through).
    """
    if profile is None:
        profile = getattr(char, "gait_profile", None)
    if profile is None:
        return None
    if isinstance(profile, dict):
        return dict(profile)
    return profile_to_gait(resolve_gait_profile(profile), run=run,
                           terrain=terrain)


def walk_to(char, from_x, to_x, duration, ground_y, height=560,
            profile=None):
    """Walk from from_x to to_x over `duration` seconds. Returns f(t)->char.

    v5 (audit 2026-11-11): planted feet (zero slip), step length from
    the character's gait (~0.16*H, ~120 steps/min instead of the old
    55 px shuffle at 267 steps/min), correct bob phase (lowest at
    foot strike), anti-phase arm swing with live elbows, anticipation
    crouch at the start and a settle (feet together) at the end.

    D1 (2026-11-12): ``profile`` (a GaitProfile, a preset name, or a
    gait dict) parameterizes the SAME core -- step length, posture,
    arm pose, head stability, mass, fatigue. With no profile (and no
    gait_profile carried by the character) the legacy GAIT_DEFAULT
    path runs unchanged. A mud profile delegates to walk_mud.
    """
    gait = _profile_gait(char, profile)
    if gait is not None and gait.get("terrain_response") == "mud":
        return walk_mud(char, from_x, to_x, duration, ground_y,
                        profile=profile)
    if gait is None:
        gait = dict(GAIT_DEFAULT)
    return _locomote(char, from_x, to_x, duration, ground_y, gait,
                     phase_name="walk")


def run_to(char, from_x, to_x, duration, ground_y, profile=None):
    """Run: the same planted-foot core with a run gait -- longer stride,
    forward lean, bigger arm pump, and a REAL flight phase (both feet
    off the ground ~30% of each step). The old run was just a walk with
    torso_lean 0.22 and zero airborne frames.

    D1: ``profile`` parameterizes the run gait the same way walk_to's
    does (step, posture, arms, stability); None = legacy GAIT_RUN."""
    gait = _profile_gait(char, profile, run=True)
    if gait is None:
        gait = dict(GAIT_RUN)
    return _locomote(char, from_x, to_x, duration, ground_y, gait,
                     phase_name="run")


def detour_walk(char, from_x, to_x, duration, ground_y, obstacle, *,
                clearance=25.0, margin=40.0, profile=None):
    """Walk from ``from_x`` to ``to_x`` DETOURING AROUND a ground
    obstacle instead of through it -- a generic obstacle-avoidance
    primitive (the five-moment "avoids splashing water" beat is one
    use: the obstacle is a puddle; any script passes any obstacle).

    ``obstacle`` is a screen-space ellipse dict ``{x, y, rx, ry}``
    (the puddle). The detour is a lateral (depth) arc: while the
    character's x passes the obstacle, the root AND the feet rise by
    ``bulge`` (screen-up = further away), so the feet pass BEHIND the
    obstacle and never enter its ellipse, then return to the ground
    line. The bump is TRAPEZOIDAL: sin^2 ramps over the approach /
    exit margins, FLAT at full bulge across the whole obstacle, so
    the feet clear it by the full clearance instead of grazing its
    edge (the first sin^2 version grazed the ellipse at normalised
    distance 1.01). The underlying walk is the proven planted-foot core (``walk_to``); only the screen-Y follows the
    detour profile, so the foot-slip check is on X (a planted foot's
    x never moves; its y follows the depth, exactly as a real step
    around an obstacle does). If the obstacle is not on the path (or
    is already clear of it, e.g. a puddle in the foreground below the
    ground line), the bulge is 0 and the primitive degrades to a
    plain walk. Returns f(t) -> char; also exposes ``bulge`` and the
    crossing window as attributes on the returned function for tests.
    """
    walk_fn = walk_to(char, from_x, to_x, duration, ground_y,
                      profile=profile)
    ox, oy = float(obstacle["x"]), float(obstacle["y"])
    orx, ory = float(obstacle["rx"]), float(obstacle["ry"])
    direction = 1 if to_x >= from_x else -1
    span = to_x - from_x
    # Foot spread (v9.1 fix): the bump is keyed to the ROOT's x, but
    # the feet extend +/- half a stride around the root (the walk's
    # planted feet sit step/2 ahead and behind). With a margin of
    # only 40 px, the FRONT foot entered the puddle's x-range while
    # the root was still in the margin and the bump was ~0 -- the
    # scene-test detour (H=783, stride 196 px) measured a minimum
    # foot-ellipse distance of 0.76, i.e. a foot INSIDE the puddle.
    # The flat top must therefore span the obstacle PLUS the foot
    # spread on both sides, so the bump is at full height whenever
    # ANY foot is within the obstacle's x-range; the ramps sit
    # outside that. (The H=560 unit test passed by luck: its smaller
    # stride (140 px) happened to plant the feet clear of the worst
    # case. The v9 test now uses H=783 + the scene-test layout.)
    from ai_clip_studio.animation.rig import GAIT_DEFAULT
    spread = GAIT_DEFAULT["stride_frac"] * float(char.H) / 2.0
    if span == 0:
        u_a = u_b = u_c = u_d = 0.0
    else:
        # trapezoidal bump: ramp up over the margin, FLAT at full
        # bulge across the obstacle PLUS the foot spread, ramp down
        # over the far margin. (The first version used a single
        # sin^2 bump over the whole window: the feet grazed the
        # ellipse's side edge at normalised distance 1.01 -- outside,
        # but only just. The flat top alone was not enough either:
        # it was keyed to the root, not the feet.)
        u_a = (ox - direction * (orx + spread + margin) - from_x) / span
        u_b = (ox - direction * (orx + spread) - from_x) / span
        u_c = (ox + direction * (orx + spread) - from_x) / span
        u_d = (ox + direction * (orx + spread + margin) - from_x) / span
    u_a, u_d = max(0.0, u_a), min(1.0, u_d)
    u_b = min(max(0.0, u_b), 1.0)
    u_c = min(max(0.0, u_c), 1.0)
    # upward shift needed so the planted feet clear the obstacle's
    # top edge by `clearance` (screen-up = further away).
    bulge = max(0.0, (ground_y - (oy - ory)) + clearance)

    def fn(t):
        walk_fn(t)
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        if bulge > 0 and u_a < u < u_d:
            if u < u_b:
                w = math.sin(math.pi / 2 * (u - u_a)
                             / max(u_b - u_a, 1e-6)) ** 2
            elif u <= u_c:
                w = 1.0
            else:
                w = math.cos(math.pi / 2 * (u - u_c)
                             / max(u_d - u_c, 1e-6)) ** 2
        else:
            w = 0.0
        lat = bulge * w
        if lat:
            char.pose["root_y"] = char.pose.get("root_y", ground_y) - lat
            for attr in ("foot_target_l", "foot_target_r"):
                tgt = getattr(char, attr, None)
                if tgt is not None:
                    setattr(char, attr, (tgt[0], tgt[1] - lat))
        return char

    fn.bulge = bulge
    fn.crossing = (u_a, u_d)
    fn.obstacle = dict(obstacle)
    return fn


def board_vehicle(char, from_x, door, duration, ground_y, *,
                  step_height=36.0, profile=None):
    """Board a vehicle through its door -- a generic boarding
    primitive (the five-moment "boards the bus" beat is one use: any
    script passes any door). ``door`` is a screen-space rect dict
    ``{x, y, width, height}`` (the door rect returned by
    ``landmarks.draw_bus_2d``); the character walks to the door
    centre, steps UP onto the vehicle step (feet plant on the step,
    ``ground_y - step_height``), then walks IN through the doorway.
    Three phases, all planted-foot: an approach walk (50% of the
    duration), a step-up (20%, the whole body rises on a smoothstep
    while the feet plant on the step), and an entry walk at step
    height (30%). The caller draws the vehicle AFTER the character
    for the entry frames, so the character is occluded by the doorway
    as they go in (the occlusion contract -- the primitive only moves
    the character; it does not hide them). Returns f(t) -> char.
    """
    door_cx = float(door["x"]) + float(door["width"]) / 2.0
    door_top = float(door["y"])
    # inside the doorway: half a door-width past the centre, still
    # under the door top (the character is fully inside the frame).
    inside_x = door_cx + (float(door["width"]) * 0.35)
    t_walk = 0.50 * duration
    t_step = 0.20 * duration
    t_enter = 0.30 * duration
    walk_fn = walk_to(char, from_x, door_cx, t_walk, ground_y,
                      profile=profile)
    enter_fn = walk_to(char, door_cx, inside_x, t_enter,
                       ground_y - step_height, profile=profile)
    _state = {"stepped": False}

    def fn(t):
        if t < t_walk:
            walk_fn(t)
            return char
        if t < t_walk + t_step:
            # step up: the whole body rises onto the step. The feet
            # are planted on the step because standing() is called
            # with the RAISED ground line.
            u = smoothstep((t - t_walk) / max(t_step, 0.01))
            gy_eff = ground_y - step_height * u
            standing(char, door_cx, gy_eff,
                     facing=char.pose.get("facing", 1))
            _state["stepped"] = True
            return char
        enter_fn(t - t_walk - t_step)
        return char

    fn.door_centre_x = door_cx
    fn.step_height = step_height
    fn.inside_x = inside_x
    return fn


def turn_to(char, new_facing, duration=0.35):
    """Turn the character to face ``new_facing`` (+1 right / -1 left)
    as a VISIBLE rotation, not an instant flip.

    v6 (backwards-walk audit 2026-11-11): facing used to flip in a
    single frame whenever a walk started the other way -- the viewer
    sees the character mirror instantly, which reads as a glitch (and
    hides which way the body is actually turning). Here the turn takes
    ``duration`` seconds: ``turn_u`` eases 0 -> 1, the facing flips at
    the midpoint, and the renderer draws the character front-on at the
    midpoint (see character_art.resolve_view) -- profile -> 3/4 ->
    front -> 3/4 -> profile. A small dip + lean into the turn sells
    the weight shift. ``new_facing`` must be +1 or -1.
    """
    if new_facing not in (1, -1):
        raise ValueError(f"turn_to: new_facing must be +1 or -1, "
                         f"got {new_facing!r}")
    _start = {}

    def fn(t):
        if "facing" not in _start:
            _start["facing"] = char.pose.get("facing", new_facing)
        old = _start["facing"]
        if old == new_facing:
            char.set_pose(turn_u=0.0, facing=new_facing)
            return char
        u = smoothstep(t / max(duration, 0.01))
        char.set_pose(turn_u=u,
                      facing=new_facing if u >= 0.5 else old,
                      bob=-_s(char, 8) * math.sin(math.pi * u),
                      torso_lean=0.10 * math.sin(math.pi * u)
                      * (1 if new_facing > old else -1))
        return char
    return fn


def look_at(char, angle_keys, duration):
    """Head look angle over time; angle_keys = [(t, angle_rad), ...]."""
    def fn(t):
        char.set_pose(head_look=interp_keys(angle_keys, t))
        return char
    return fn


def point_at(char, target, duration):
    """Raise the right arm toward `target` (x, y) and look at it.

    The hand starts from its CURRENT position (captured on the first
    call), never from a fixed offset -- the old fixed start teleported
    the hand whenever the previous segment had left it elsewhere
    (audit: 100-240 px single-frame hand jumps at segment boundaries).
    """
    _start = {}

    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        if "hand" not in _start:
            _start["hand"] = char.joints()["hand_r"]
            _start["last"] = None
        elif (_start["last"] is not None and t < 0.25
                and _start_moved(char, "hand_r", _start["last"])):
            # stale pre-warm capture: another segment moved the hand
            # since this primitive was warmed -- re-capture (see
            # _start_moved). Gated to the first 0.25 s: later the hand
            # moves because THIS primitive moves it.
            _start["hand"] = char.joints()["hand_r"]
        sx, sy = _start["hand"]
        tx, ty = target
        char.hand_target_r = (lerp(sx, tx, u), lerp(sy, ty, u))
        _start["last"] = char.hand_target_r
        char.set_pose(head_look=-0.35 * u, torso_lean=-0.06 * u)
        return char
    return fn


def wave(char, duration, freq=1.8):
    """Wave the right hand SIDE TO SIDE (forearm rotation), ~1.8 Hz.

    v5 (audit 2026-11-11): the old wave moved the hand UP AND DOWN
    (+/-15 px in y at 3.3 Hz, 4 cycles in 1.2 s) with a FIXED x -- a
    fast vertical flap, not a wave. A friendly wave rises once to
    shoulder height, then sways side to side in X (+/-22 px) at
    ~1.5-2 Hz while the elbow stays bent so the forearm rotates. The
    hand also starts from its current position (no teleport). The
    rise takes 0.7 s (v6: was 0.5 s -- the elbow swung 87.8 px in a
    single frame on the rise; the longer rise keeps the elbow under
    ~60 px/frame while still leaving sway time in a 1.1 s wave).

    v8 (audit 2026-11-11): two fixes. (1) The rise is an ARC, not a
    straight line: the hand travels a quadratic Bezier whose control
    point bulges forward (facing direction) and up, so the hand
    sweeps out and up the way a real greeting does. The v7 rise was
    a perfect straight line (0.1 px deviation from the chord --
    rubric E8). (2) The rise goes FORWARD (facing direction). The
    v7 code used ``hx + 80`` with no facing factor, so Lan (facing
    left) waved BEHIND her back in the v7 motion test (hand at x
    1615, root at 1503).

    v8.1: the control bulge is (20, -10), not (40, -20) -- the
    40 px bulge made the rise START at 68% of peak velocity
    (rubric E10 ease-in, first3 10.7 / peak 15.8) because the hand
    lunges toward the far control point. The smaller bulge still
    gives ~13 px arc deviation (E8 needs >= 10) with a gentler
    start. The sway also EASES OUT over the last 0.3 s of the wave
    so the hand settles at the raised position instead of stopping
    mid-swing when the segment (and the video) ends (E10 end
    ratio was 0.82).

    v9 (audit 2026-11-11): the wave INHERITS the incoming torso lean
    and head look instead of snapping them to 0 at t=0. The motion
    test waves straight after the handover, which ends at lean 0.08;
    the old wave set lean 0 on its first frame, so the head moved
    10.7 px/frame in the wave's first 3 frames while the segment
    peak is only 12.7 (rubric E10 start ratio 0.84). The lean is now
    captured like the hand (with the same stale-pre-warm re-capture
    guard) and lerped from the incoming value to the wave's -0.05 as
    the rise progresses -- the head starts still and the body
    counter-leans gently as the arm rises, which is also the more
    natural motion. A standalone wave (incoming lean 0) is unchanged.
    """
    _start = {}

    def fn(t):
        hx, hy = char.pose["root_x"], char.pose["root_y"]
        f = char.pose.get("facing", 1)
        if "hand" not in _start:
            _start["hand"] = char.joints()["hand_r"]
            _start["last"] = None
            # v9: inherit the incoming lean / head look (see docstring).
            _start["lean"] = char.pose.get("torso_lean", 0.0)
            _start["look"] = char.pose.get("head_look", 0.0)
        elif (_start["last"] is not None and t < 0.25
                and _start_moved(char, "hand_r", _start["last"])):
            # stale pre-warm capture -- re-capture (see _start_moved)
            _start["hand"] = char.joints()["hand_r"]
            _start["lean"] = char.pose.get("torso_lean", 0.0)
            _start["look"] = char.pose.get("head_look", 0.0)
        elif t < 0.25 and abs(char.pose.get("torso_lean", 0.0)
                              - _start.get("lean", 0.0)) > 0.02:
            # the hand did not move (the guard above did not fire)
            # but the LEAN did -- e.g. the wave was pre-warmed
            # standing (lean 0) and now starts after a leaning
            # handover. Re-capture so the wave starts from the
            # incoming lean instead of snapping to 0.
            _start["lean"] = char.pose.get("torso_lean", 0.0)
            _start["look"] = char.pose.get("head_look", 0.0)
        sx, sy = _start["hand"]
        rise = smoothstep(min(1.0, t / 0.7))
        sway = math.sin(2 * math.pi * freq * max(0.0, t - 0.7))
        # Ease the sway OUT over the last 0.3 s so the hand settles
        # at the raised position instead of stopping mid-swing.
        if t > duration - 0.3:
            sway *= 1.0 - smoothstep((t - (duration - 0.3)) / 0.3)
        tx = hx + f * _s(char, 80)
        ty = hy - _s(char, 225)
        # Quadratic Bezier rise: P0 = hang, P1 = shoulder height,
        # control = midpoint bulged forward and up. Max deviation
        # from the chord is half the control offset (~10 px at a
        # (20, -10) bulge -- v8.1, was (40, -20) / ~27 px).
        cx = (sx + tx) / 2 + f * _s(char, 20)
        cy = (sy + ty) / 2 - _s(char, 10)
        q = rise
        x = (1 - q) ** 2 * sx + 2 * (1 - q) * q * cx + q * q * tx
        y = (1 - q) ** 2 * sy + 2 * (1 - q) * q * cy + q * q * ty
        x += _s(char, 22) * sway * rise
        char.hand_target_r = (x, y)
        _start["last"] = char.hand_target_r
        # v9: lean / look lerp from the INCOMING values (captured
        # above) to the wave's values as the rise progresses -- no
        # snap at t=0 (see docstring).
        char.set_pose(elbow_r=0.6,
                      torso_lean=lerp(_start["lean"], -0.05, rise),
                      head_look=lerp(_start["look"], -0.10, rise))
        return char
    return fn


def reach_to(char, target, duration, hand="r"):
    """Reach one hand toward a target point (IK). Starts from the
    hand's current position, not a fixed offset (see point_at)."""
    _start = {}

    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        key = "hand_" + hand
        if key not in _start:
            _start[key] = char.joints()[key]
            _start["last"] = None
        elif (_start["last"] is not None and t < 0.25
                and _start_moved(char, key, _start["last"])):
            # stale pre-warm capture -- re-capture (see _start_moved)
            _start[key] = char.joints()[key]
        sx, sy = _start[key]
        if hand == "r":
            char.hand_target_r = (lerp(sx, target[0], u),
                                  lerp(sy, target[1], u))
            _start["last"] = char.hand_target_r
        else:
            char.hand_target_l = (lerp(sx, target[0], u),
                                  lerp(sy, target[1], u))
            _start["last"] = char.hand_target_l
        return char
    return fn


def _reachable_meeting_point(giver, receiver, point):
    """Pull a handover meeting point into both characters' reach.

    The rig clamps each hand target INDEPENDENTLY to 98% of that
    arm's reach, so a meeting point outside either character's
    reach leaves the two hands clamped to DIFFERENT positions --
    the handover gap. For equal-height partners the classic meeting
    point is already reachable and this is a no-op. For mixed
    heights (a tall giver, a short receiver) the giver-height
    meeting point is out of the receiver's reach, and the pull
    moves it onto the receiver's reach circle -- the closest point
    both hands can actually meet at. Alternating projection onto
    the two reach circles until both constraints hold within
    0.01 px (the lens between the circles can be thin -- a fixed
    12 passes left a 1.5 px residual on the Test F staging,
    measured numerically); 50 passes is far more than the
    projection needs to converge when the lens is non-empty.
    Staging must still keep the partners within combined arm reach
    (A-S7); beyond that no meeting point exists and the residual
    gap is reported honestly by the measurement, never hidden.
    """
    px, py = float(point[0]), float(point[1])
    for _ in range(50):
        excess = 0.0
        for char in (giver, receiver):
            shoulder = char.joints()["shoulder"]
            limit = 0.98 * (char.u_arm + char.l_arm)
            dx, dy = px - shoulder[0], py - shoulder[1]
            dist = math.hypot(dx, dy)
            if dist > limit:
                excess = max(excess, dist - limit)
                px = shoulder[0] + dx / dist * limit
                py = shoulder[1] + dy / dist * limit
        if excess < 0.01:
            break
    return (px, py)


def give_to(giver, receiver, prop, duration, receive_hand="l"):
    """Handoff: giver's and receiver's hands converge on a midpoint and
    `prop` (dict with 'x','y') travels with them. Returns f(t)->(giver, receiver, prop).

    ``receive_hand`` ("l" | "r") is the hand the receiver takes the
    prop with -- named by the script ("tay phải" / "tay trái") via
    the compiler's HAND_OVER receive_hand param. The default "l"
    preserves the engine's historical behaviour. The giver always
    offers with the right hand.

    v5 (audit 2026-11-11): both hands start from their CURRENT
    positions and lerp in x AND y to the meeting point. The old code
    set the hand y to the meeting height from u=0 while lerping only
    x, so each hand teleported 100-180 px on the first frame of the
    handoff.
    """
    if receive_hand not in ("l", "r"):
        raise ValueError(f"receive_hand must be 'l' or 'r', "
                         f"got {receive_hand!r}")
    recv_joint = "hand_" + receive_hand
    recv_target = "hand_target_" + receive_hand
    _start = {}

    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        if "giver" not in _start:
            _start["giver"] = giver.joints()["hand_r"]
            _start["receiver"] = receiver.joints()[recv_joint]
            _start["last_g"] = None
            _start["last_recv"] = None
        elif t < 0.25:
            # stale pre-warm capture -- re-capture (see _start_moved)
            if (_start["last_g"] is not None and _start_moved(
                    giver, "hand_r", _start["last_g"])):
                _start["giver"] = giver.joints()["hand_r"]
            if (_start["last_recv"] is not None and _start_moved(
                    receiver, recv_joint, _start["last_recv"])):
                _start["receiver"] = receiver.joints()[recv_joint]
        # Pose FIRST: the meeting-point clamp reads the shoulder from
        # joints(), and the lean set here moves the shoulder by up to
        # ~14 px. Clamping before set_pose left an 8.7 px residual
        # gap on the Test F proof (the clamp and the drawn pose
        # disagreed); with the pose final first, the clamp reads the
        # shoulder the renderer will actually use.
        giver.set_pose(head_look=0.25 * u, torso_lean=0.06 * u)
        receiver.set_pose(head_look=-0.25 * u, torso_lean=-0.06 * u)
        gx, gy = giver.pose["root_x"], giver.pose["root_y"]
        rx, ry = receiver.pose["root_x"], receiver.pose["root_y"]
        mid_x = (gx + rx) / 2
        mid_y = gy - _s(giver, 180) - _s(giver, 40) * math.sin(u * math.pi)
        # Mixed-height partners: the meeting point must be reachable
        # by BOTH hands, or the rig's independent IK clamps leave a
        # gap (see _reachable_meeting_point). No-op when reachable.
        mid_x, mid_y = _reachable_meeting_point(
            giver, receiver, (mid_x, mid_y))
        gsx, gsy = _start["giver"]
        rsx, rsy = _start["receiver"]
        giver.hand_target_r = (lerp(gsx, mid_x, u), lerp(gsy, mid_y, u))
        setattr(receiver, recv_target,
                (lerp(rsx, mid_x, u), lerp(rsy, mid_y, u)))
        _start["last_g"] = giver.hand_target_r
        _start["last_recv"] = getattr(receiver, recv_target)
        prop["x"], prop["y"] = mid_x, mid_y + _s(giver, 10)
        return giver, receiver, prop
    return fn


def idle(char, duration, ground_y):
    """Standing idle: breathing, slow weight shift, slow head drift.

    The v4 audit caught the standing character as a frozen statue:
    0.000 px total joint displacement over 2.8 s while the other
    character walked. A living character breathes (~15/min), shifts
    weight every ~12 s and lets the head drift. Small amplitudes --
    this is a background life signal, not a gesture.
    """
    _base = {}

    def fn(t):
        if "root" not in _base:
            _base["root"] = (char.pose["root_x"], char.pose["root_y"])
        bx, by = _base["root"]
        breathe = math.sin(t * 2 * math.pi * 0.25)   # ~15 breaths/min
        sway = math.sin(t * 2 * math.pi * 0.08)      # ~12 s weight shift
        drift = math.sin(t * 2 * math.pi * 0.05)     # slow head drift
        char.set_pose(root_x=bx + _s(char, 6) * sway,
                      root_y=by,
                      torso_lean=0.02 * sway,
                      head_look=0.08 * drift,
                      bob=_s(char, 3) * (0.5 + 0.5 * breathe),
                      arm_l=0.05 + 0.03 * breathe,
                      arm_r=-0.05 - 0.03 * breathe,
                      elbow_l=0.10, elbow_r=0.10)
        char.foot_target_l = (bx - STAND_SPLIT_FRAC * float(char.H),
                              ground_y)
        char.foot_target_r = (bx + STAND_SPLIT_FRAC * float(char.H),
                              ground_y)
        char.hand_target_l = None
        char.hand_target_r = None
        return char
    return fn


def seated_idle(char, duration):
    """Seated idle: breathing + slow head drift while seated.

    Unlike idle() (standing), this never touches foot or hand
    targets: the seated character may hold a pen, rest hands on a
    desk, or keep feet planted under a chair -- the previous
    primitive's targets stay. Only the torso lean, the breathing
    bob and the head drift move, so the pose stays seated for the
    whole duration. Completion pose: the incoming seated pose.
    """
    _base = {}

    def fn(t):
        if "lean" not in _base:
            _base["lean"] = char.pose.get("torso_lean", 0.0)
            _base["bob"] = char.pose.get("bob", 0.0)
        breathe = math.sin(t * 2 * math.pi * 0.25)  # ~15 breaths/min
        drift = math.sin(t * 2 * math.pi * 0.05)     # slow head drift
        char.set_pose(
            torso_lean=_base["lean"] + 0.015 * breathe,
            bob=_base["bob"] + _s(char, 2) * (0.5 + 0.5 * breathe),
            head_look=0.06 * drift)
        return char
    return fn


def standing(char, root_x, ground_y, facing=1, lean=0.0):
    """Stand at ``root_x`` with the feet where they already are.

    v8 (animation audit 2026-11-11): the old per-script standing()
    (and rig.plant_feet) always forced the canonical +/-0.125H split.
    After a walk the feet end SWAPPED (the settle's nearest-split
    gather) -- the canonical split is the same two positions with the
    feet exchanged -- so forcing it made each foot cross ~196 px in
    the 0.2 s blend into the handover (59 px/frame, rubric E6). A
    standing split does not care which foot is ahead: if the feet are
    already planted on the ground in a reasonable split around this
    root, KEEP them; only an unposed character (no foot targets, or
    feet nowhere near this root) gets the canonical split. Hands are
    cleared -- the caller sets a hold after this, as before.
    """
    leg = char.u_leg + char.l_leg
    char.set_pose(root_x=root_x,
                  root_y=ground_y - leg * 0.93,
                  facing=facing, thigh_l=0.08, thigh_r=-0.08,
                  knee_l=0.12, knee_r=0.12, arm_l=0.08, arm_r=0.08,
                  elbow_l=0.15, elbow_r=0.15, bob=0.0,
                  torso_lean=lean, head_look=0.0, head_sway_x=0.0)
    char.hand_target_l = None
    char.hand_target_r = None
    fl = char.foot_target_l
    fr = char.foot_target_r
    spread = abs(fl[0] - fr[0]) if fl is not None and fr is not None else 0.0
    mid = (fl[0] + fr[0]) / 2.0 if fl is not None and fr is not None else None
    keep = (fl is not None and fr is not None
            and abs(fl[1] - ground_y) <= 4.0
            and abs(fr[1] - ground_y) <= 4.0
            and 0.10 * float(char.H) <= spread <= 0.35 * float(char.H)
            and mid is not None
            and abs(mid - root_x) <= 0.15 * float(char.H))
    if keep:
        char.foot_target_l = (fl[0], ground_y)
        char.foot_target_r = (fr[0], ground_y)
    else:
        plant_feet(char, ground_y)
    return char


def bend_pick(char, target, duration, ground_y, hand="r"):
    """Bend down to pick up a prop at `target` (x, y) on the ground.

    v5 (audit 2026-11-11): the old bend leaned 71 deg with STRAIGHT
    knees and dropped the hip 93% of leg length -- nearly sitting on
    the ground -- and the hand only touched the wallet for 3 frames.
    A natural pick is a STOOP + SQUAT: the torso leans ~77 deg and
    the knees bend (hip drops ~50% of leg length). The audit's first
    prescription (lean 40-50 deg, hip drop 30-40%) was geometrically
    IMPOSSIBLE for this rig -- the arm is only 0.283*H long, so with
    a 45 deg lean the shoulder stays ~290 px above the ground and the
    hand can never reach it; the numbers here are what the reach
    actually requires, verified by the IK clamp in the tests. The head
    tracks the prop, the hand reaches it by 55% of the motion and
    HOLDS contact (hand within 15 px) through the hold phase, then
    rises slowly carrying the prop.
    Phases: anticipate (0-12%), descend (12-50%), hold (50-65%),
    rise (65-100% -- the rise gets the longest share, 35%, because
    standing back up from a deep bend is the slowest part).
    """
    _start = {}
    leg = char.u_leg + char.l_leg

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        if "hand" not in _start:
            _start["hand"] = char.joints()["hand_" + hand]
            _start["root_y"] = char.pose["root_y"]
        # depth profile: 0 = standing, 1 = fully bent
        if u < 0.12:
            d = 0.12 * smoothstep(u / 0.12)
        elif u < 0.50:
            d = 0.12 + 0.88 * smoothstep((u - 0.12) / 0.38)
        elif u < 0.65:
            d = 1.0
        else:
            d = 1.0 - smoothstep((u - 0.65) / 0.35)
        root_y = ground_y - leg * (0.93 - 0.50 * d)
        lean = 1.35 * d
        # hand: reach the target by the end of the descend, hold it,
        # then lift it ~60 px as the body rises.
        reach = smoothstep(min(1.0, u / 0.50))
        rise = smoothstep(max(0.0, (u - 0.65) / 0.35))
        sx, sy = _start["hand"]
        tx, ty = target
        # v8: the rise carries the prop to the WAIST hold (root_x +
        # 40s forward, standing root_y - 60s) -- the same hold the
        # next walk segment uses. The v7 rise lifted the hand only
        # 60 px, leaving it 298 px from the waist, so the next
        # segment's 0.2 s blend had to sprint it 66 px/frame (rubric
        # E3/E4). The hand now travels the whole way during the
        # 0.49 s rise, smoothstepped, arriving at the waist exactly
        # when the body stands up.
        f = char.pose.get("facing", 1)
        waist = (char.pose["root_x"] + f * _s(char, 40),
                 ground_y - leg * 0.93 - _s(char, 60))
        hx = lerp(lerp(sx, tx, reach), waist[0], rise)
        hy = lerp(lerp(sy, ty, reach), waist[1], rise)
        char.set_pose(root_y=root_y, torso_lean=lean)
        # head tracks the prop (clamped by head_track)
        head_track(char, (tx, ty))
        if hand == "r":
            char.hand_target_r = (hx, hy)
        else:
            char.hand_target_l = (hx, hy)
        return char
    return fn


def kneel_pick(char, target, duration, ground_y, hand="r"):
    """Pick up a prop at ``target`` (x, y) on the ground by KNEELING on
    one knee -- the v6 alternative to bend_pick's 77 deg stoop, which
    reads as lying flat (the rig's arm is only 0.283*H, so a standing
    stoop must fold nearly horizontal to reach the ground).

    v7 (animation audit 2026-11-11): the v6 kneel still read as a deep
    bow -- lean 63 deg, head only 35% of standing height. The v7 kneel
    keeps the hip HIGHER (0.55 * thigh-length above the ground instead
    of 0.72) and leans less (0.92 rad ~ 53 deg instead of 1.10 rad),
    and the head tracks the prop with a CAPPED look (max 0.25 rad
    instead of the 0.6 default -- the v6 head_look clamped at +0.6
    pointed the head down-forward and dropped it from ~263 px to
    217 px). Result: head ~42% of standing height at full kneel.
    That is the RIG-GEOMETRY CAP for this arm (0.283*H): raising the
    hip further pushes the shoulder-to-prop distance past 98% of the
    arm and the hand can no longer reach the prop (see the IK-clamp
    test). A higher head needs a longer arm or a closer/higher prop,
    not a different kneel. The feet travel on LIFT arcs during the
    descend and the rise -- the v6 kneel lerped them along the ground,
    a hidden slide the v6 audit never measured.

    F1 (TEST C Phase 2, 2026-11-12): the v7 kneel still read as a knot
    in the rendered video (Phase 1 measurement: lean 52.7 deg, shins
    42.5 px apart, front knee 75.9 deg, head top 50.9% of standing
    height). The fix steps INTO the kneel: the root shifts forward
    toward the prop during the descend (an adaptive lunge step, sized
    from the prop's forward distance so the shoulder ends one short
    reach from the prop), the lean drops to 0.82 rad (~47 deg), and
    the front foot plants further ahead (0.72 * leg instead of 0.55),
    opening the front knee to ~101 deg and separating the shins to
    ~87 px. The root returns to its start during the rise, so the
    next segment starts without an offset. Measured on the real rig
    in both stagings (prop 83 px and 220 px ahead): hand exactly on
    the prop, back knee 1.2 px above the ground, head top 56.2% of
    standing height.

    The back knee stays folded at ~33 deg -- that is NOT an unfixed
    bug, it is the geometry of a kneel: the back shin lies flat on
    the ground, so the knee angle is set by the hip height and the
    foot tuck, and the knee-on-ground + ground-prop-reach constraints
    pin both. A grid search over (lean 30-45 deg, hip 60-160 px, tuck
    0.05-0.50) found ZERO combinations with lean <= 40 deg AND back
    knee >= 55 deg AND the knee on the ground AND the hand on the
    prop; the best achievable back-knee angle under those constraints
    is ~40 deg, and only with the arm overstretched 11.6 px past its
    clamp. A 55 deg back knee needs a longer arm or a raised prop,
    not a different kneel. Readability comes from the shin separation
    and the lower lean, not from unfolding the kneeling knee.

    A kneel is geometrically honest for this rig: the hip drops to a
    deep lunge-kneel, the BACK knee lands ON the ground (back foot
    tucks just behind the hip, shin flat on the ground), the FRONT
    foot plants ahead, and the torso leans ~47 deg -- so the shoulder
    is low enough for the hand to reach the prop without folding the
    body in half. (A textbook kneel -- hip one thigh-length up, knee
    under the hip -- still needs a ~83 deg lean to reach a ground prop
    with this rig's 0.283*H arm; the deep lunge-kneel is what actually
    reaches at 47 deg. The numbers are verified by the IK clamp in the
    tests, not assumed.) The reaching hand is on the same side as the
    planted front foot (the stable side); the kneeling knee is the
    opposite leg.

    Phases: anticipate (0-15%, crouch + weight shift), descend to
    kneel (15-50%), hold (50-65%, hand on the prop), rise (65-100%,
    standing back up carrying the prop). Feet start from their CURRENT
    positions (no teleport); the rise returns them to the walk's
    starting split (+/-step/2 around the root) so the next walk
    segment starts without a blend slide. The hand reaches the target
    by 50%.
    """
    _start = {}
    leg = char.u_leg + char.l_leg
    u_leg = char.u_leg
    l_leg = char.l_leg
    step = GAIT_DEFAULT["stride_frac"] * float(char.H)

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        if "hand" not in _start:
            _start["hand"] = char.joints()["hand_" + hand]
            _start["root_y"] = char.pose["root_y"]
            _start["root_x"] = char.pose["root_x"]
            _start["foot_l"] = char.joints()["foot_l"]
            _start["foot_r"] = char.joints()["foot_r"]
            _start["facing"] = char.pose.get("facing", 1)
        f = _start["facing"]
        rx = _start["root_x"]
        # F1: adaptive forward step into the kneel. The shoulder must
        # end within arm's reach of the prop; at the lower 0.82 lean
        # a fixed root cannot reach a prop 220 px ahead (the product
        # staging), so the root steps forward by the excess forward
        # distance, capped at 0.20H. A close prop (the test staging,
        # 83 px) needs no step. The step follows the depth profile:
        # it grows during the descend and returns during the rise, so
        # the character ends standing where they started.
        if "shift" not in _start:
            _fwd = f * (target[0] - rx)
            _shoulder_fwd = math.sin(0.82) * char.torso
            _start["shift"] = max(
                0.0, min(0.20 * float(char.H),
                         _fwd - (_shoulder_fwd + _s(char, 25))))
        shift = _start["shift"]
        # depth profile: 0 = standing, 1 = fully kneeled
        if u < 0.15:
            d = 0.15 * smoothstep(u / 0.15)
        elif u < 0.50:
            d = 0.15 + 0.85 * smoothstep((u - 0.15) / 0.35)
        elif u < 0.65:
            d = 1.0
        else:
            d = 1.0 - smoothstep((u - 0.65) / 0.35)
        root_x = rx + f * shift * d
        final_rx = rx + f * shift
        # hip: standing (leg * 0.93 above ground) -> deep lunge-kneel
        # (v7: 0.55 * thigh-length above ground, so the back knee
        # touches down without sinking below the ground plane AND the
        # head stays ~42% of standing height -- the rig-geometry cap
        # for the 0.283*H arm; see the docstring).
        root_y = ground_y - (leg * 0.93 - (leg * 0.93 - u_leg * 0.55) * d)
        lean = 0.82 * d  # F1: ~47 deg at full kneel (v7: 0.92 / 53 deg)
        # feet: front foot (same side as the reaching hand) plants
        # ahead; back foot (opposite side) tucks just behind the hip
        # so its knee lands on the ground forward of the hip (deep
        # lunge-kneel geometry -- see the module docstring for why a
        # textbook kneel cannot reach a ground prop with this rig).
        # The rise returns both feet to the walk's starting split so
        # the next walk starts without a blend slide.
        front_side = "r" if hand == "r" else "l"
        back_side = "l" if hand == "r" else "r"
        # F1: the front foot plants at 0.72 * leg ahead of the FINAL
        # (shifted) root (v7: 0.55). The longer lunge opens the front
        # knee to ~101 deg and separates the shins to ~87 px, so the
        # two legs read as two legs instead of one knot. Both kneel
        # targets are relative to the final root, so the hold pose is
        # consistent with the shifted root.
        front_tx = final_rx + f * 0.72 * leg
        # v7: the back foot tucks only 0.16*l_leg behind the hip (v6:
        # 0.30). The back knee's ground position is COUPLED to the hip
        # height: at the v7 hip (0.55*u_leg) the 0.30 tuck put the knee
        # 30 px BELOW the ground (it clips through the floor -- the
        # v6 hip 0.72*u_leg needed the wider tuck). 0.16 lands the
        # knee ~1 px above the ground; 0.165 is exactly on it. The
        # value is verified by the IK-clamp test, not assumed.
        back_tx = final_rx - f * l_leg * 0.16
        stand_tx = {front_side: rx + f * step / 2.0,
                    back_side: rx - f * step / 2.0}
        # v7: feet travel on LIFT arcs (0.05H), never along the ground.
        # The v6 kneel lerped the feet along the ground plane while
        # the hip descended -- a hidden slide the v6 audit never
        # measured (its slip metric only covered walk/run).
        lift = _s(char, 28)
        for side, tx in ((front_side, front_tx), (back_side, back_tx)):
            sx, sy = _start["foot_" + side]
            if u < 0.65:
                # descend: start -> kneel target, arc peaks mid-move
                gx = lerp(sx, tx, d)
                gy = lerp(sy, ground_y, d) - lift * math.sin(math.pi * d)
            else:
                # rise: kneel target -> standing split, arc peaks mid-move
                q = 1.0 - d
                gx = lerp(tx, stand_tx[side], q)
                gy = ground_y - lift * math.sin(math.pi * q)
            if side == "l":
                char.foot_target_l = (gx, gy)
            else:
                char.foot_target_r = (gx, gy)
        # hand: reach the target by the end of the descend, hold it,
        # then carry it to the WAIST hold as the body rises (v8 -- see
        # bend_pick: the v7 rise lifted the hand only 60 px, leaving
        # it 298 px from the waist, so the next segment's 0.2 s blend
        # had to sprint it 66 px/frame, rubric E3/E4).
        reach = smoothstep(min(1.0, u / 0.50))
        rise = smoothstep(max(0.0, (u - 0.65) / 0.35))
        sx, sy = _start["hand"]
        tx, ty = target
        waist = (rx + f * _s(char, 40),
                 ground_y - leg * 0.93 - _s(char, 60))
        hx = lerp(lerp(sx, tx, reach), waist[0], rise)
        hy = lerp(lerp(sy, ty, reach), waist[1], rise)
        char.set_pose(root_x=root_x, root_y=root_y, torso_lean=lean)
        # head tracks the prop -- CAPPED at 0.25 rad (v7): the default
        # 0.6 clamp let the head point down-forward and dropped it to
        # 35% of standing height; 0.25 keeps the head ~42% up.
        head_track(char, (tx, ty), max_angle=0.25)
        if hand == "r":
            char.hand_target_r = (hx, hy)
        else:
            char.hand_target_l = (hx, hy)
        return char
    return fn


def snapshot(char):
    """Capture a character's full pose state (pose dict + IK targets)
    so a renderer can blend between two snapshots at a segment
    boundary instead of snapping. See apply_snapshot."""
    return (dict(char.pose),
            char.hand_target_l, char.hand_target_r,
            char.foot_target_l, char.foot_target_r)


def apply_snapshot(char, snap_a, snap_b=None, u=0.0):
    """Restore snapshot ``snap_a``, or blend from ``snap_a`` to
    ``snap_b`` by ``u`` (0..1, smoothstepped by the caller). Pose
    values lerp numerically; an IK target that exists in only one
    snapshot fades in from / out to the other snapshot's value, so a
    hand never teleports across a segment boundary."""
    if snap_b is None:
        pose, hl, hr, fl, fr = snap_a
        char.set_pose(**pose)
        char.hand_target_l, char.hand_target_r = hl, hr
        char.foot_target_l, char.foot_target_r = fl, fr
        return char
    pa, hla, hra, fla, fra = snap_a
    pb, hlb, hrb, flb, frb = snap_b
    merged = {k: lerp(pa.get(k, 0.0), pb.get(k, 0.0), u)
              for k in set(pa) | set(pb)}
    char.set_pose(**merged)
    # FK fallback positions under the blended pose: a target that
    # exists in only one snapshot blends from/to the limb's natural
    # (FK) position instead of teleporting in on the first frame past
    # the midpoint. (The first v5 draft stepped here: a hand whose
    # target was None in snapshot A jumped 148 px when the blend
    # crossed u=0.5 and snapshot B's target switched on.)
    char.hand_target_l = char.hand_target_r = None
    char.foot_target_l = char.foot_target_r = None
    fk = char.joints()

    def _blend_target(ta, tb, fk_key):
        # v8: when NEITHER snapshot has a target, return None -- do
        # NOT invent one from the FK position. The old code always
        # returned the FK hand/foot position, which made a free limb
        # IK-driven during the blend; the IK elbow branch (bend=f)
        # sits on the OPPOSITE side of the shoulder->hand line from
        # the FK elbow, so the elbow snapped 60 px in one frame when
        # the blend ended and the limb went back to FK (rubric E5:
        # walk_hold elbow_l 59.5 px/frame at fi 115->116). A target
        # that exists in only one snapshot still blends from/to the
        # FK position, as before.
        if ta is None and tb is None:
            return None
        a = ta if ta is not None else fk[fk_key]
        b = tb if tb is not None else fk[fk_key]
        return (lerp(a[0], b[0], u), lerp(a[1], b[1], u))

    char.hand_target_l = _blend_target(hla, hlb, "hand_l")
    char.hand_target_r = _blend_target(hra, hrb, "hand_r")
    char.foot_target_l = _blend_target(fla, flb, "foot_l")
    char.foot_target_r = _blend_target(fra, frb, "foot_r")
    return char


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


# ---------------------------------------------------------------------------
# Visual Quality Recovery (2026-11-12): semantic-action primitives.
#
# The recovery directive (P1/P2/P5) requires reusable, parameterised
# primitives for sitting, grasping, writing, signing, handing over,
# mud walking, carrying, looking and reacting -- each with a defined
# COMPLETION POSE (see PRIMITIVE_COMPLETION) that tests measure on the
# real rig. Every primitive follows the existing conventions: hands
# start from their CURRENT position (captured lazily, stale-pre-warm
# re-capture), feet travel on lift arcs, bone lengths are invariant
# (IK targets clamp at 98% reach in the rig), and no primitive invents
# story geometry -- chair/desk/paper/pocket positions arrive as
# parameters from staging. Phase fractions that the prop state machine
# depends on (grasp / lift / transfer / release moments) are module
# constants, never magic numbers in two places.
# ---------------------------------------------------------------------------

# Phase fractions shared with ai_clip_studio/prop_system.py.
PICK_UP_GRASP_U = 0.45   # pick_up: hand arrives at the prop
PICK_UP_LIFT_U = 0.60    # pick_up: lift to the hold starts
KNEEL_PICK_GRASP_U = 0.50  # kneel_pick/bend_pick: hand on the prop
RECEIVE_REACH_U = 0.60   # receive_prop: hand arrives at the target
HAND_OVER_TRANSFER_U = 0.60  # hand_over: holder switches giver->receiver
PUT_AWAY_RELEASE_U = 0.55    # put_away: prop releases at the pocket

# Pen geometry (fractions of H / radians). A held pen points
# forward-down at ~65 deg below horizontal; the tip sits below and
# ahead of the gripping hand. write_on_paper / sign_document drive the
# HAND from a pen-TIP trajectory through pen_tip_position(), so the
# tip -- not the hand -- is what contacts the paper.
PEN_LEN_FRAC = 0.10
PEN_GRIP_ANGLE_RAD = 1.13

# Mud: planted feet sink this far below the ground plane.
MUD_SINK_FRAC = 0.03

# Mud gait: short steps, long double support, high lift to pull each
# foot out, forward lean, wide arm swing for balance. No flight phase.
MUD_GAIT = {
    "stride_frac": 0.12,
    "arm_amp": 0.55,
    "lean": 0.20,
    "bob_frac": 0.05,
    "lift_frac": 0.12,
    "overlap": 0.35,
}


def pen_tip_position(hand_pos, facing, H):
    """Pen tip for a hand gripping a pen (see PEN_GRIP_ANGLE_RAD)."""
    length = PEN_LEN_FRAC * float(H)
    return (hand_pos[0] + facing * math.cos(PEN_GRIP_ANGLE_RAD) * length,
            hand_pos[1] + math.sin(PEN_GRIP_ANGLE_RAD) * length)


# Hammer geometry (fractions of H / radians) + strike-cycle phases
# (Test F, 2026-11-12). A held hammer's head sits beyond the gripping
# hand along a fixed grip direction -- forward-down, like the pen
# tip, but longer and steeper: the head leads the strike. The
# hammer_strike primitive drives the HAND from a hammer-HEAD
# trajectory through hammer_head_position(), so the HEAD -- not the
# hand -- is what contacts the work surface. The strike fractions
# are shared with the prop system and the audio anchors (the same
# pattern as PICK_UP_GRASP_U / HAND_OVER_TRANSFER_U): a strike
# contact is meaningful only at the strike moment of a cycle.
HAMMER_HANDLE_FRAC = 0.16
HAMMER_GRIP_ANGLE_RAD = 1.25
HAMMER_HEAD_HALF_FRAC = 0.035
HAMMER_CYCLE_RAISE_U = 0.35   # hammer_strike: raise ends, hold begins
HAMMER_CYCLE_HOLD_U = 0.45    # hammer_strike: hold ends, strike begins
HAMMER_CYCLE_STRIKE_U = 0.60  # hammer_strike: head contacts surface
HAMMER_CYCLE_SEC = 0.9        # default duration of one strike cycle
# Carry angle: the hammer cocks up-back of the hand on the raise, so
# the head clears the face (a fixed strike angle puts the head ON the
# face during the raise -- measured on the first Test F proof
# render). The wrist articulates: the angle eases from the strike
# angle (hammer hanging at rest) to the carry angle over the raise,
# holds through the hold, eases back to the strike angle through the
# strike phase, and stays there through the recovery. At the strike
# moment the angle IS the strike angle, so the contact measurement
# (hammer_head_position's default) is exact.
HAMMER_CARRY_ANGLE_RAD = -2.09


def hammer_grip_angle(cycle_u):
    """Hammer grip angle in force at cycle fraction ``cycle_u``.

    Rest / strike / recovery: HAMMER_GRIP_ANGLE_RAD (head below the
    hand). Raise / hold: HAMMER_CARRY_ANGLE_RAD (head cocked up-back
    of the hand). Transitions ease with smoothstep over their phase,
    so the angle is continuous across cycle boundaries (u=0 and u=1
    are both the strike angle) and exactly the strike angle at
    HAMMER_CYCLE_STRIKE_U.
    """
    u = min(1.0, max(0.0, float(cycle_u)))
    if u < HAMMER_CYCLE_RAISE_U:
        e = smoothstep(u / HAMMER_CYCLE_RAISE_U)
        return (HAMMER_GRIP_ANGLE_RAD
                + (HAMMER_CARRY_ANGLE_RAD - HAMMER_GRIP_ANGLE_RAD) * e)
    if u < HAMMER_CYCLE_HOLD_U:
        return HAMMER_CARRY_ANGLE_RAD
    if u < HAMMER_CYCLE_STRIKE_U:
        v = ((u - HAMMER_CYCLE_HOLD_U)
             / (HAMMER_CYCLE_STRIKE_U - HAMMER_CYCLE_HOLD_U))
        e = smoothstep(v)
        return (HAMMER_CARRY_ANGLE_RAD
                + (HAMMER_GRIP_ANGLE_RAD - HAMMER_CARRY_ANGLE_RAD) * e)
    return HAMMER_GRIP_ANGLE_RAD


def hammer_head_position(hand_pos, facing, H, angle_rad=None):
    """Hammer head for a hand gripping a hammer handle.

    Mirrors pen_tip_position: the head is HAMMER_HANDLE_FRAC * H
    from the hand along the grip direction (forward-down at
    HAMMER_GRIP_ANGLE_RAD, mirrored by facing). The returned point
    is the hammer's STRIKING FACE -- the point that contacts the
    work surface -- so a drawn hammer head sits behind this point
    (up the handle), never centred on it. ``angle_rad`` overrides
    the grip angle (the phase angle from hammer_grip_angle, for
    drawing the swing); the default is the strike angle, which is
    the angle in force at every strike moment, so contact
    measurement always uses the default.
    """
    if angle_rad is None:
        angle_rad = HAMMER_GRIP_ANGLE_RAD
    length = HAMMER_HANDLE_FRAC * float(H)
    return (hand_pos[0] + facing * math.cos(angle_rad) * length,
            hand_pos[1] + math.sin(angle_rad) * length)


def hammer_cycles(duration) -> int:
    """Strike cycles in a hammer_strike run of ``duration`` seconds.

    Single source of truth for the cycle count: the primitive and
    the audio anchors both derive it from the duration (one strike
    per HAMMER_CYCLE_SEC), so the rendered strikes and the SFX
    hits can never disagree about how many strikes happened.
    """
    return max(1, round(float(duration) / HAMMER_CYCLE_SEC))


def hammer_strike_times(duration, cycles):
    """Contact times (seconds) of every strike in a hammer_strike
    run: each cycle's HAMMER_CYCLE_STRIKE_U moment. Audio anchors
    (e.g. a HAMMER_METAL_CONTACT cue) consume these times; they are
    the only moments the head touches the surface."""
    duration = float(duration)
    cycles = max(1, int(cycles))
    cycle = duration / cycles
    return [cycle * (i + HAMMER_CYCLE_STRIKE_U) for i in range(cycles)]


def _hand_start(char, hand, state, t):
    """Capture a hand's start position (lazy + stale-pre-warm guard).

    ``state`` is the primitive's private dict; ``hand`` is "l"/"r".
    Returns the captured start position. Mirrors the point_at /
    reach_to pattern without duplicating its body in every primitive.
    """
    key = "hand_" + hand
    if key not in state:
        state[key] = char.joints()[key]
        state["last_" + hand] = None
    elif (state.get("last_" + hand) is not None and t < 0.25
            and _start_moved(char, key, state["last_" + hand])):
        state[key] = char.joints()[key]
    return state[key]


def _set_hand(char, hand, pos, state):
    """Set one hand IK target and remember it for the stale guard."""
    if hand == "r":
        char.hand_target_r = pos
    else:
        char.hand_target_l = pos
    state["last_" + hand] = pos


def _seated_foot_offset(char, seat_h):
    """Forward foot offset (px) that puts seated knees at ~90 deg.

    With the hip ``seat_h`` above the ground and leg segments
    (u_leg, l_leg), a 90 deg interior knee angle needs a hip->foot
    distance of sqrt(u^2 + l^2); the forward offset is the remaining
    leg of that right triangle. Clamped to [0.05H, 0.30H]: a bar
    stool (seat too high) folds the knees more, which is geometry,
    not a bug -- the value is returned, never hidden.
    """
    c2 = char.u_leg ** 2 + char.l_leg ** 2
    dx2 = c2 - float(seat_h) ** 2
    dx = math.sqrt(dx2) if dx2 > 0.0 else 0.0
    return max(0.05 * float(char.H), min(0.30 * float(char.H), dx))


def _waist_hold(char, ground_y):
    """The waist hold every grasp ends at (bend_pick's hold)."""
    leg = char.u_leg + char.l_leg
    f = char.pose.get("facing", 1)
    return (char.pose["root_x"] + f * _s(char, 40),
            ground_y - leg * 0.93 - _s(char, 60))


def sit_at_desk(char, chair_x, seat_y, duration, ground_y, desk=None):
    """Sit on a chair at ``chair_x`` with the seat top at ``seat_y``.

    The root lowers to the seat, the feet plant on the ground ahead
    of the chair (offset solved for ~90 deg knees -- see
    _seated_foot_offset), the torso leans slightly forward and the
    hands settle on the desk top (``desk`` = {"x", "top_y"}) or, with
    no desk, on the knees. Feet travel on lift arcs, never slid.
    Completion pose: seated, knees ~90 deg, feet planted, hands on
    the desk (or knees), head looking down at the work surface.
    """
    _start = {}
    leg = char.u_leg + char.l_leg

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        if "root" not in _start:
            _start["root"] = (char.pose["root_x"], char.pose["root_y"])
            _start["lean"] = char.pose.get("torso_lean", 0.0)
            _start["look"] = char.pose.get("head_look", 0.0)
            _start["foot_l"] = char.joints()["foot_l"]
            _start["foot_r"] = char.joints()["foot_r"]
            _start["hand_l"] = char.joints()["hand_l"]
            _start["hand_r"] = char.joints()["hand_r"]
        f = char.pose.get("facing", 1)
        lower = smoothstep(min(1.0, u / 0.55))
        settle = smoothstep(max(0.0, (u - 0.55) / 0.45))
        seat_h = ground_y - seat_y
        dx = _seated_foot_offset(char, seat_h)
        root_x = lerp(_start["root"][0], chair_x, lower)
        root_y = lerp(_start["root"][1], seat_y, lower)
        char.set_pose(root_x=root_x, root_y=root_y,
                      torso_lean=lerp(_start["lean"], 0.12, lower),
                      head_look=lerp(_start["look"], 0.25, settle),
                      bob=0.0)
        lift = _s(char, 28)
        foot_targets = {
            "l": (chair_x + f * dx - _s(char, 18), ground_y),
            "r": (chair_x + f * dx + _s(char, 18), ground_y),
        }
        for side, tgt in foot_targets.items():
            sx, sy = _start["foot_" + side]
            gx = lerp(sx, tgt[0], lower)
            gy = lerp(sy, ground_y, lower) - lift * math.sin(math.pi * lower)
            if side == "l":
                char.foot_target_l = (gx, gy)
            else:
                char.foot_target_r = (gx, gy)
        if desk is not None:
            top_y = float(desk["top_y"])
            hand_targets = {
                "l": (chair_x + f * _s(char, 56), top_y + _s(char, 6)),
                "r": (chair_x + f * _s(char, 112), top_y),
            }
        else:
            hand_targets = {
                "l": (chair_x + f * _s(char, 80), seat_y + _s(char, 68)),
                "r": (chair_x + f * _s(char, 96), seat_y + _s(char, 68)),
            }
        for side, tgt in hand_targets.items():
            sx, sy = _start["hand_" + side]
            _set_hand(char, side,
                      (lerp(sx, tgt[0], settle), lerp(sy, tgt[1], settle)),
                      _start)
        return char
    return fn


def stand_from_chair(char, duration, ground_y, chair_x=None):
    """Stand up from a seated pose (inverse of sit_at_desk).

    Captures the seated state on the first call, rises to the
    canonical standing pose, gathers the feet to the standing split
    on lift arcs, and returns the hands to their hanging position
    before clearing the IK targets -- the hands never teleport from
    the desk to the sides. Completion pose: standing() exactly.
    """
    _start = {}
    leg = char.u_leg + char.l_leg

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        if "root" not in _start:
            _start["root"] = (char.pose["root_x"], char.pose["root_y"])
            _start["foot_l"] = char.joints()["foot_l"]
            _start["foot_r"] = char.joints()["foot_r"]
            _start["hand_l"] = char.joints()["hand_l"]
            _start["hand_r"] = char.joints()["hand_r"]
            _start["chair_x"] = (chair_x if chair_x is not None
                                 else char.pose["root_x"])
        rise = smoothstep(u)
        stand_y = ground_y - leg * 0.93
        root_x = _start["chair_x"]
        char.set_pose(root_x=root_x,
                      root_y=lerp(_start["root"][1], stand_y, rise),
                      torso_lean=lerp(char.pose.get("torso_lean", 0.0),
                                      0.0, rise),
                      head_look=lerp(char.pose.get("head_look", 0.0),
                                     0.0, rise),
                      bob=0.0)
        f = char.pose.get("facing", 1)
        lift = _s(char, 28)
        split = STAND_SPLIT_FRAC * float(char.H)
        for side, tgt_x in (("l", root_x - split), ("r", root_x + split)):
            sx, sy = _start["foot_" + side]
            gx = lerp(sx, tgt_x, rise)
            gy = lerp(sy, ground_y, rise) - lift * math.sin(math.pi * rise)
            if side == "l":
                char.foot_target_l = (gx, gy)
            else:
                char.foot_target_r = (gx, gy)
        hang_y = stand_y + _s(char, 28)
        for side in ("l", "r"):
            sx, sy = _start["hand_" + side]
            hx = lerp(sx, root_x + f * _s(char, 22), rise)
            hy = lerp(sy, hang_y, rise)
            _set_hand(char, side, (hx, hy), _start)
        if u >= 1.0:
            standing(char, root_x, ground_y, facing=f)
        return char
    return fn


def pick_up(char, target, duration, ground_y, hand="r", source="ground"):
    """Grasp a prop at ``target`` and lift it to the waist hold.

    Phases: reach (0-45%), grasp hold (45-60%), lift (60-100%).
    ``source`` ("ground" | "pocket" | "desk" | "surface") only sets
    the lean: a pocket/desk grasp barely leans, a ground grasp leans
    more. A deep ground pickup that must fold the body is bend_pick /
    kneel_pick, not this primitive. The grasp moment is
    PICK_UP_GRASP_U (shared with the prop state machine).
    Completion pose: hand at the waist hold, prop grasped.
    """
    _start = {}

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        sx, sy = _hand_start(char, hand, _start, t)
        reach = smoothstep(min(1.0, u / PICK_UP_GRASP_U))
        lift = smoothstep(max(0.0, (u - PICK_UP_LIFT_U)
                              / (1.0 - PICK_UP_LIFT_U)))
        hold = _waist_hold(char, ground_y)
        hx = lerp(lerp(sx, target[0], reach), hold[0], lift)
        hy = lerp(lerp(sy, target[1], reach), hold[1], lift)
        lean_max = 0.05 if source in ("pocket", "desk", "surface") else 0.15
        char.set_pose(torso_lean=lean_max * reach * (1.0 - 0.7 * lift))
        head_track(char, (lerp(target[0], hold[0], lift),
                          lerp(target[1], hold[1], lift)),
                   max_angle=0.35)
        _set_hand(char, hand, (hx, hy), _start)
        return char
    return fn


def open_wallet(char, duration, prop=None):
    """Bring both hands together and open the wallet they hold.

    The hands converge on a chest-height hold point; ``prop`` (a dict
    like give_to's) carries open_u 0 -> 1 over the second half of the
    motion and follows the midpoint of the hands. Completion pose:
    hands together at chest height, open_u == 1.0.
    """
    _start = {}
    prop = prop if prop is not None else {}

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        f = char.pose.get("facing", 1)
        joints = char.joints()
        hold = (char.pose["root_x"] + f * _s(char, 68),
                joints["shoulder"][1] + _s(char, 56))
        ease = smoothstep(u)
        hands = {}
        for side in ("l", "r"):
            sx, sy = _hand_start(char, side, _start, t)
            off = _s(char, 14) if side == "l" else -_s(char, 14)
            pos = (lerp(sx, hold[0] + f * off, ease),
                   lerp(sy, hold[1], ease))
            _set_hand(char, side, pos, _start)
            hands[side] = pos
        prop["open_u"] = smoothstep(max(0.0, (u - 0.4) / 0.6))
        prop["x"] = (hands["l"][0] + hands["r"][0]) / 2.0
        prop["y"] = (hands["l"][1] + hands["r"][1]) / 2.0
        head_track(char, (prop["x"], prop["y"]), max_angle=0.3)
        return char
    return fn


def close_wallet(char, duration, prop=None):
    """Close the wallet (open_u 1 -> 0) and let the hands part.

    Completion pose: hands slightly parted at chest height,
    open_u == 0.0.
    """
    _start = {}
    prop = prop if prop is not None else {"open_u": 1.0}

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        f = char.pose.get("facing", 1)
        joints = char.joints()
        hold = (char.pose["root_x"] + f * _s(char, 68),
                joints["shoulder"][1] + _s(char, 56))
        prop["open_u"] = 1.0 - smoothstep(min(1.0, u / 0.6))
        part = smoothstep(max(0.0, (u - 0.6) / 0.4))
        hands = {}
        for side in ("l", "r"):
            sx, sy = _hand_start(char, side, _start, t)
            off = _s(char, 14) + _s(char, 22) * part
            off = off if side == "l" else -off
            pos = (lerp(sx, hold[0] + f * off, smoothstep(u)),
                   lerp(sy, hold[1], smoothstep(u)))
            _set_hand(char, side, pos, _start)
            hands[side] = pos
        prop["x"] = (hands["l"][0] + hands["r"][0]) / 2.0
        prop["y"] = (hands["l"][1] + hands["r"][1]) / 2.0
        return char
    return fn


def hold_pen(char, pen_pos, paper, duration, hand="r"):
    """Grasp a pen at ``pen_pos`` and bring it to writing-ready above
    ``paper`` ({"x", "y", "w", "h"}: paper rect, surface at "y").

    Completion pose: hand positioned so the pen tip hovers 12 px
    above the paper surface at the line start, head looking at it.
    """
    _start = {}

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        sx, sy = _hand_start(char, hand, _start, t)
        f = char.pose.get("facing", 1)
        tip_ready = (float(paper["x"]) + 0.15 * float(paper["w"]),
                     float(paper["y"]) + 0.30 * float(paper["h"]) - 12.0)
        ready = (tip_ready[0]
                 - f * math.cos(PEN_GRIP_ANGLE_RAD) * PEN_LEN_FRAC * float(char.H),
                 tip_ready[1]
                 - math.sin(PEN_GRIP_ANGLE_RAD) * PEN_LEN_FRAC * float(char.H))
        reach = smoothstep(min(1.0, u / 0.40))
        move = smoothstep(max(0.0, (u - 0.55) / 0.45))
        hx = lerp(lerp(sx, pen_pos[0], reach), ready[0], move)
        hy = lerp(lerp(sy, pen_pos[1], reach), ready[1], move)
        head_track(char, (lerp(pen_pos[0], tip_ready[0], move),
                          lerp(pen_pos[1], tip_ready[1], move)),
                   max_angle=0.35)
        _set_hand(char, hand, (hx, hy), _start)
        return char
    return fn


def _writing_hand(char, hand, tip, start, blend_u):
    """Hand IK target for a pen tip at ``tip``, blended in from the
    captured ``start`` hand position over ``blend_u`` (0..1)."""
    f = char.pose.get("facing", 1)
    hx = (tip[0] - f * math.cos(PEN_GRIP_ANGLE_RAD)
          * PEN_LEN_FRAC * float(char.H))
    hy = (tip[1] - math.sin(PEN_GRIP_ANGLE_RAD)
          * PEN_LEN_FRAC * float(char.H))
    return (lerp(start[0], hx, blend_u), lerp(start[1], hy, blend_u))


def write_on_paper(char, paper, duration, hand="r", words=6):
    """Write one line: the pen tip stays ON the paper plane, tracing
    small oscillations left to right while the hand follows through
    the pen geometry (see pen_tip_position). ``paper`` is {"x", "y",
    "w", "h"}; the writing line sits at 35% of the paper height.
    ``words`` sets the oscillation count (one cycle per word).
    Completion pose: hand at the line end, pen tip on the paper.
    """
    _start = {}

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        sx, sy = _hand_start(char, hand, _start, t)
        x0 = float(paper["x"]) + 0.12 * float(paper["w"])
        x1 = float(paper["x"]) + 0.88 * float(paper["w"])
        base_y = float(paper["y"]) + 0.35 * float(paper["h"])
        amp = min(0.06 * float(paper["h"]), 0.02 * float(char.H))
        cycles = max(1, int(words))
        tip = (lerp(x0, x1, u),
               base_y + amp * math.sin(2.0 * math.pi * cycles * u))
        blend = smoothstep(min(1.0, u / 0.15))
        pos = _writing_hand(char, hand, tip, (sx, sy), blend)
        char.set_pose(torso_lean=0.15)
        head_track(char, tip, max_angle=0.3)
        _set_hand(char, hand, pos, _start)
        return char
    return fn


def sign_document(char, paper, duration, hand="r"):
    """Sign with a flourish: 3 loops across 40% of the paper width,
    then the pen lifts 30 px in the last 20% of the motion.
    Completion pose: pen lifted above the paper, hand retreating.
    """
    _start = {}

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        sx, sy = _hand_start(char, hand, _start, t)
        x0 = float(paper["x"]) + 0.30 * float(paper["w"])
        x1 = float(paper["x"]) + 0.70 * float(paper["w"])
        base_y = float(paper["y"]) + 0.60 * float(paper["h"])
        amp = min(0.10 * float(paper["h"]), 0.03 * float(char.H))
        if u < 0.8:
            q = u / 0.8
            tip = (lerp(x0, x1, q),
                   base_y + amp * math.sin(math.pi * q)
                   * math.sin(2.0 * math.pi * 3.0 * q))
        else:
            lift = smoothstep((u - 0.8) / 0.2)
            tip = (x1, base_y - _s(char, 30) * lift)
        blend = smoothstep(min(1.0, u / 0.15))
        pos = _writing_hand(char, hand, tip, (sx, sy), blend)
        char.set_pose(torso_lean=0.15)
        head_track(char, tip, max_angle=0.3)
        _set_hand(char, hand, pos, _start)
        return char
    return fn


def hand_over(giver, receiver, prop, duration,
              transfer_u=HAND_OVER_TRANSFER_U, receive_hand="l"):
    """Hand a prop over: both hands converge (give_to), and the prop's
    recorded holder switches from giver to receiver at ``transfer_u``
    (shared with the prop state machine). ``receive_hand`` ("l" | "r")
    is the receiver's taking hand (see give_to). Returns
    f(t) -> (giver, receiver, prop). Completion pose: prop at the
    receiver's hand, prop["holder"] == receiver name.
    """
    base = give_to(giver, receiver, prop, duration,
                   receive_hand=receive_hand)

    def fn(t):
        out = base(t)
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        prop["holder"] = (giver.name if u < transfer_u
                          else receiver.name)
        prop["transfer_u"] = transfer_u
        return out
    return fn


def hammer_strike(char, strike_point, duration, ground_y=None, hand="r",
                  cycles=None, raise_frac=0.24):
    """Repetitive hammer work at a surface point: raise / hold /
    strike / recover, repeated ``cycles`` times.

    General: any character, any anvil-like surface. The strike point
    is staging data (the surface the staging placed there), the tool
    is any hammer-like prop gripped in ``hand``, and the surface kind
    is the staging's business -- the primitive only guarantees the
    HEAD contacts the strike point. At each cycle's
    HAMMER_CYCLE_STRIKE_U moment the hand is driven to the strike
    point minus the hammer grip vector, so
    hammer_head_position(hand) equals the strike point up to IK
    reach: a strike point outside arm reach misses honestly (the
    measurement reports it), it is never faked closer.

    Acting weight: the raise decelerates into a brief hold
    (anticipation, with a small settle dip), the strike accelerates
    (ease-in), and the recovery overshoots past the rest position
    before settling (follow-through). The torso leans back on the
    raise and thrusts forward on the strike; the head tracks down
    toward the surface at contact. The feet never move (planted):
    ``ground_y`` is accepted for signature uniformity with the other
    work primitives and ignored -- the caller plants the feet with
    standing() before running this, as for every hand primitive.

    ``cycles`` defaults to duration / HAMMER_CYCLE_SEC (one strike
    per 0.9 s). Contact times for audio anchors come from
    hammer_strike_times(duration, cycles). The hammer's grip angle
    articulates with the swing (hammer_grip_angle): cocked up-back
    on the raise so the head clears the face, at the strike angle
    at every strike moment. A renderer draws the hammer with
    hammer_head_position(hand, facing, H, hammer_grip_angle(u));
    contact measurement uses the default strike angle. Completion
    pose: hand at rest, hammer head struck the surface at each
    cycle's strike moment.
    """
    if cycles is None:
        cycles = hammer_cycles(duration)
    cycles = max(1, int(cycles))
    sx, sy = float(strike_point[0]), float(strike_point[1])
    _start = {}

    def fn(t):
        u_global = min(1.0, max(0.0, t / max(duration, 0.01)))
        cycle = min(cycles - 1, int(u_global * cycles))
        u = u_global * cycles - cycle
        f = char.pose.get("facing", 1) or 1
        if "lean" not in _start:
            _start["lean"] = char.pose.get("torso_lean", 0.0)
            _start["look"] = char.pose.get("head_look", 0.0)
        rest = _hand_start(char, hand, _start, t)
        H = float(char.H)
        shoulder = char.joints()["shoulder"]
        raised = (shoulder[0] + f * 0.06 * H,
                  shoulder[1] - raise_frac * H)
        grip = (f * math.cos(HAMMER_GRIP_ANGLE_RAD)
                * HAMMER_HANDLE_FRAC * H,
                math.sin(HAMMER_GRIP_ANGLE_RAD)
                * HAMMER_HANDLE_FRAC * H)
        strike_hand = (sx - grip[0], sy - grip[1])
        if u < HAMMER_CYCLE_RAISE_U:
            v = u / HAMMER_CYCLE_RAISE_U
            e = 1.0 - (1.0 - v) ** 2  # ease-out: decelerate into hold
            pos = (lerp(rest[0], raised[0], e),
                   lerp(rest[1], raised[1], e))
            lean = _start["lean"] - 0.08 * e
            look = _start["look"] + 0.05 * e
        elif u < HAMMER_CYCLE_HOLD_U:
            v = ((u - HAMMER_CYCLE_RAISE_U)
                 / (HAMMER_CYCLE_HOLD_U - HAMMER_CYCLE_RAISE_U))
            dip = math.sin(v * math.pi) * 0.008 * H
            pos = (raised[0], raised[1] + dip)
            lean = _start["lean"] - 0.08
            look = _start["look"] + 0.10
        elif u < HAMMER_CYCLE_STRIKE_U:
            v = ((u - HAMMER_CYCLE_HOLD_U)
                 / (HAMMER_CYCLE_STRIKE_U - HAMMER_CYCLE_HOLD_U))
            e = v * v  # ease-in: accelerate into the strike
            pos = (lerp(raised[0], strike_hand[0], e),
                   lerp(raised[1], strike_hand[1], e))
            lean = _start["lean"] + lerp(-0.08, 0.18, e)
            look = _start["look"] + lerp(0.10, 0.30, e)
        else:
            v = (u - HAMMER_CYCLE_STRIKE_U) / (1.0 - HAMMER_CYCLE_STRIKE_U)
            e = smoothstep(v)
            base = (lerp(strike_hand[0], rest[0], e),
                    lerp(strike_hand[1], rest[1], e))
            rebound = math.sin(v * math.pi) * 0.18
            pos = (base[0] + rebound * (raised[0] - rest[0]),
                   base[1] + rebound * (raised[1] - rest[1]))
            lean = _start["lean"] + lerp(0.18, 0.0, e)
            look = _start["look"] + lerp(0.30, 0.05, e)
        _set_hand(char, hand, pos, _start)
        char.set_pose(torso_lean=lean, head_look=look)
        return char
    return fn


def walk_mud(char, from_x, to_x, duration, ground_y, sink=None,
           profile=None):
    """Walk through mud on the planted-foot core with a mud gait
    (short steps, long double support, high lift, forward lean) plus
    two mud behaviours the clean walk does not have: planted feet
    SINK ``sink`` px below the ground plane (default 0.03H), and the
    torso sways gently for balance. Planted feet never slide in x --
    only their y is offset. Completion pose: standing at to_x, feet
    sunk in the mud.

    D1: ``profile`` parameterizes the mud gait (step capped at 0.15H,
    posture/arm/stability from the profile); None = legacy MUD_GAIT.
    """
    if sink is None:
        sink = MUD_SINK_FRAC * float(char.H)
    gait = _profile_gait(char, profile, terrain="mud")
    if gait is None:
        gait = dict(MUD_GAIT)
    base = _locomote(char, from_x, to_x, duration, ground_y, gait,
                     phase_name="walk_mud")

    def fn(t):
        base(t)
        for attr in ("foot_target_l", "foot_target_r"):
            tgt = getattr(char, attr)
            if tgt is not None and abs(tgt[1] - ground_y) <= 1.5:
                setattr(char, attr, (tgt[0], ground_y + sink))
        char.set_pose(
            torso_lean=char.pose.get("torso_lean", 0.0)
            + 0.05 * math.sin(2.0 * math.pi * 1.1 * t))
        return char
    return fn


def carry_bag(char, duration, hand="r", bag=None, sway_amp=None,
              sway_freq=1.6):
    """Carry a bag hanging from one hand (hand-only overlay).

    The hand settles at a carry position at the character's side and
    the bag hangs below it on a pendulum sway. This primitive touches
    ONLY one hand target and the ``bag`` dict, so it composes with a
    walk: apply the walk first, then this overlay, each frame. With
    ``bag`` None only the hand is positioned. Completion pose: hand
    at the carry position, bag hanging below it.
    """
    _start = {}
    if sway_amp is None:
        sway_amp = 0.02 * float(char.H)

    def fn(t):
        f = char.pose.get("facing", 1)
        joints = char.joints()
        carry = (joints["hip"][0] + f * _s(char, 45),
                 joints["hip"][1] + _s(char, 68))
        sx, sy = _hand_start(char, hand, _start, t)
        blend = smoothstep(min(1.0, t / 0.4))
        pos = (lerp(sx, carry[0], blend), lerp(sy, carry[1], blend))
        _set_hand(char, hand, pos, _start)
        if bag is not None:
            bag["x"] = pos[0] + sway_amp * math.sin(
                2.0 * math.pi * sway_freq * t)
            bag["y"] = pos[1] + _s(char, 68)
        return char
    return fn


def look_at_point(char, target, duration):
    """Turn the head toward a screen point (head_track, capped).

    The existing look_at() takes angle keyframes; this is the
    target-based variant the action compiler emits for "look at X"
    sentences. Completion pose: head oriented toward the target
    (head_look at the capped tracking angle).
    """
    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        head_track(char, target, max_angle=0.6 * max(u, 0.05))
        return char
    return fn


def react_event(char, duration, kind="startle"):
    """React to an environmental event: startle / flinch / duck.

    A fast flinch (0-25%), a tense hold (25-55%), then a partial
    recovery that KEEPS 60% of the tension -- a startled character
    does not instantly relax. "flinch" also raises the hands toward
    the face; "duck" crouches deeper without the arm raise.
    Completion pose: tense hold (lean ~0.15, head ducked, crouched).
    """
    if kind not in ("startle", "flinch", "duck"):
        raise ValueError(f"react_event: unknown kind {kind!r} "
                         f"(expected 'startle', 'flinch' or 'duck')")
    _start = {}

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        if "root" not in _start:
            _start["root"] = (char.pose["root_x"], char.pose["root_y"])
            _start["lean"] = char.pose.get("torso_lean", 0.0)
            _start["look"] = char.pose.get("head_look", 0.0)
            _start["hand_l"] = char.joints()["hand_l"]
            _start["hand_r"] = char.joints()["hand_r"]
        f = char.pose.get("facing", 1)
        up = smoothstep(min(1.0, u / 0.25))
        recover = smoothstep(max(0.0, (u - 0.55) / 0.45))
        intensity = up * (1.0 - 0.4 * recover)
        crouch_px = _s(char, 45) if kind == "duck" else _s(char, 28)
        back_px = 0.0 if kind == "duck" else _s(char, 17)
        lean_t = 0.35 if kind == "duck" else 0.25
        char.set_pose(
            root_x=_start["root"][0] - f * back_px * intensity,
            root_y=_start["root"][1] + crouch_px * intensity,
            torso_lean=_start["lean"] + lean_t * intensity,
            head_look=_start["look"] + 0.30 * intensity,
            arm_l=0.5 * intensity, arm_r=0.5 * intensity,
            elbow_l=0.9 * intensity, elbow_r=0.9 * intensity)
        if kind == "flinch":
            head = char.joints()["head"]
            for side in ("l", "r"):
                sx, sy = _start["hand_" + side]
                off = -_s(char, 28) if side == "l" else _s(char, 28)
                pos = (lerp(sx, head[0] + off, intensity),
                       lerp(sy, head[1] + _s(char, 56), intensity))
                _set_hand(char, side, pos, _start)
        return char
    return fn


def raise_hand(char, duration, hand="r", raise_frac=0.30):
    """Raise one hand to above shoulder height and hold it (asking a
    question, volunteering, hailing). Completion pose: hand raised,
    held above the shoulder line.
    """
    _start = {}

    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        sx, sy = _hand_start(char, hand, _start, t)
        f = char.pose.get("facing", 1)
        shoulder = char.joints()["shoulder"]
        tgt = (char.pose["root_x"] + f * _s(char, 84),
               shoulder[1] - raise_frac * float(char.H))
        _set_hand(char, hand,
                  (lerp(sx, tgt[0], u), lerp(sy, tgt[1], u)), _start)
        char.set_pose(head_look=-0.10 * u)
        return char
    return fn


def head_tilt(char, duration, head_look=0.30, torso_lean=0.0):
    """Ease the head (and optionally the torso) to a held tilt.

    Covers bow-head (head_look > 0, head forward/down), lift-head
    (head_look < 0) and head-tilt holds through parameters -- one
    primitive, no per-gesture code. Completion pose: head held at
    the target look angle.
    """
    _start = {}

    def fn(t):
        u = smoothstep(t / max(duration, 0.01))
        if "look" not in _start:
            _start["look"] = char.pose.get("head_look", 0.0)
            _start["lean"] = char.pose.get("torso_lean", 0.0)
        char.set_pose(head_look=lerp(_start["look"], head_look, u),
                      torso_lean=lerp(_start["lean"], torso_lean, u))
        return char
    return fn


def breathe(char, duration, breaths=2):
    """Visible breathing: slow bob + lean oscillation, feet untouched.

    Starts and ends exactly at the incoming pose (the oscillation
    completes whole breaths), so it splices cleanly between segments.
    Completion pose: the incoming standing pose.
    """
    _start = {}

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        if "bob" not in _start:
            _start["bob"] = char.pose.get("bob", 0.0)
            _start["lean"] = char.pose.get("torso_lean", 0.0)
        phase = 2.0 * math.pi * breaths * u
        char.set_pose(
            bob=_start["bob"] + _s(char, 4) * (0.5 - 0.5 * math.cos(phase)),
            torso_lean=_start["lean"] + 0.02 * math.sin(phase),
            arm_l=0.08 + 0.02 * math.sin(phase),
            arm_r=0.08 - 0.02 * math.sin(phase))
        return char
    return fn


def put_away(char, pocket, duration, hand="r", prop=None):
    """Put a held prop away at ``pocket`` (x, y) and return the hand
    to its hanging position. The prop follows the hand until
    PUT_AWAY_RELEASE_U, then stays at the pocket -- the release
    position EQUALS the hand position at release, so nothing
    teleports. Completion pose: hand hanging, prop at the pocket.
    """
    _start = {}
    prop = prop if prop is not None else {}

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        sx, sy = _hand_start(char, hand, _start, t)
        f = char.pose.get("facing", 1)
        hang = (char.pose["root_x"] + f * _s(char, 22),
                char.pose["root_y"] + _s(char, 28))
        reach = smoothstep(min(1.0, u / 0.5))
        back = smoothstep(max(0.0, (u - 0.6) / 0.4))
        pos = (lerp(lerp(sx, pocket[0], reach), hang[0], back),
               lerp(lerp(sy, pocket[1], reach), hang[1], back))
        _set_hand(char, hand, pos, _start)
        if u < PUT_AWAY_RELEASE_U:
            prop["x"], prop["y"] = pos
            prop["released"] = False
        else:
            prop["x"], prop["y"] = pocket
            prop["released"] = True
        return char
    return fn


def pose_at_completion(fn, char, duration):
    """Run a primitive to its end and return the completion joints.

    ``fn`` is a primitive closure (or a hand_over-style closure
    returning a tuple -- the joints still come from ``char``).
    """
    fn(duration)
    return char.joints()


# Completion-pose contract for every recovery primitive: what a test
# or a proof may assert about the pose at t == duration.
PRIMITIVE_COMPLETION = {
    "sit_at_desk": "seated: hips at seat height, knees ~90 deg, feet "
                   "planted on the ground, hands on desk/knees",
    "stand_from_chair": "standing() pose at the chair x",
    "pick_up": "hand at the waist hold, prop grasped",
    "open_wallet": "hands together at chest height, open_u == 1.0",
    "close_wallet": "hands parted at chest height, open_u == 0.0",
    "hold_pen": "pen tip hovering over the paper line start",
    "write_on_paper": "hand at line end, pen tip on the paper",
    "sign_document": "pen lifted 30 px above the paper",
    "hand_over": "prop at receiver hand, holder == receiver",
    "crouch": "standing() pose restored, feet planted (a held dip, "
              "not a stance change)",
    "receive_prop": "hand pulled 25% toward the waist, prop grasped",
    "walk_mud": "standing at to_x, feet sunk in mud",
    "carry_bag": "hand at carry position, bag hanging below",
    "look_at_point": "head oriented toward the target",
    "react_event": "tense hold: lean ~0.15, head ducked, crouched",
    "raise_hand": "hand raised above the shoulder line, held",
    "head_tilt": "head held at the target look angle",
    "breathe": "incoming standing pose (whole breaths)",
    "put_away": "hand hanging, prop at the pocket",
    "seated_idle": "incoming seated pose (breathing only)",
    "hammer_strike": "hand at rest, hammer head struck the surface "
                     "at each cycle's strike moment",
}


def crouch(char, duration, ground_y, depth_frac=0.30, lean=0.35):
    """Crouch: lower the hips with bent knees and a forward torso
    lean, feet planted, then rise back to standing. The torso bends
    WITHOUT picking anything up -- the CROUCH semantic action ("cúi
    người tránh tiếng pháo"), distinct from bend_pick/kneel_pick.

    The feet are captured from the current pose and held as IK
    targets through the motion, so dropping root_y bends the knees
    instead of sliding the feet; the root never moves horizontally,
    so the next segment starts without an offset. Hands are
    untouched (a crouch carries no prop contact). Phases: descend
    (0-30%), hold (30-70%), rise (70-100%). Completion pose: the
    incoming standing pose.
    """
    _start = {}
    leg = char.u_leg + char.l_leg

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        if "root_y" not in _start:
            _start["root_y"] = char.pose["root_y"]
            _start["lean"] = char.pose.get("torso_lean", 0.0)
            _start["look"] = char.pose.get("head_look", 0.0)
            joints = char.joints()
            _start["foot_l"] = joints["foot_l"]
            _start["foot_r"] = joints["foot_r"]
        if u < 0.30:
            d = smoothstep(u / 0.30)
        elif u < 0.70:
            d = 1.0
        else:
            d = 1.0 - smoothstep((u - 0.70) / 0.30)
        char.foot_target_l = _start["foot_l"]
        char.foot_target_r = _start["foot_r"]
        char.set_pose(
            root_y=ground_y - leg * (0.93 - depth_frac * d),
            torso_lean=lerp(_start["lean"], lean, d),
            head_look=lerp(_start["look"], 0.12, d))
        return char
    return fn


def receive_prop(char, target, duration, hand="r"):
    """Receive a prop: the named hand reaches from its current
    position to the meeting ``target`` (x, y), holds contact, then
    draws the prop slightly toward the body (securing it). The
    receiver side of a transfer (RECEIVE_PROP, "nhận bằng tay
    phải"); the giver side is hand_over/give_to. When the hand
    already starts at the target (a hand_over just placed it there),
    the reach is a no-op and only the securing pull-in moves.
    Phases: reach (0-60%), hold + pull-in (60-100%). Completion
    pose: hand at the pulled-in hold, prop secured.
    """
    _start = {}

    def fn(t):
        u = min(1.0, max(0.0, t / max(duration, 0.01)))
        if "hand" not in _start:
            _start["hand"] = char.joints()["hand_" + hand]
            _start["lean"] = char.pose.get("torso_lean", 0.0)
            f = char.pose.get("facing", 1)
            _start["waist"] = (char.pose["root_x"] + f * _s(char, 40),
                               char.pose["root_y"] - _s(char, 60))
        reach = smoothstep(min(1.0, u / 0.60))
        pull = smoothstep(max(0.0, (u - 0.60) / 0.40))
        sx, sy = _start["hand"]
        tx, ty = target
        wx, wy = _start["waist"]
        hx = lerp(lerp(sx, tx, reach), lerp(tx, wx, 0.25), pull)
        hy = lerp(lerp(sy, ty, reach), lerp(ty, wy, 0.25), pull)
        char.set_pose(torso_lean=lerp(_start["lean"], 0.10, reach))
        if hand == "r":
            char.hand_target_r = (hx, hy)
        else:
            char.hand_target_l = (hx, hy)
        return char
    return fn


PRIMITIVES = {
    "walk_to": walk_to, "run_to": run_to, "turn_to": turn_to,
    "look_at": look_at,
    "point_at": point_at, "wave": wave, "reach_to": reach_to,
    "give_to": give_to, "shrug": shrug, "cover_face": cover_face,
    "nod": nod, "sit_down": sit_down, "stand_up": stand_up,
    "idle": idle, "bend_pick": bend_pick, "kneel_pick": kneel_pick,
    "sit_at_desk": sit_at_desk, "stand_from_chair": stand_from_chair,
    "pick_up": pick_up, "open_wallet": open_wallet,
    "close_wallet": close_wallet, "hold_pen": hold_pen,
    "write_on_paper": write_on_paper, "sign_document": sign_document,
    "hand_over": hand_over, "walk_mud": walk_mud,
    "carry_bag": carry_bag, "look_at_point": look_at_point,
    "react_event": react_event, "raise_hand": raise_hand,
    "head_tilt": head_tilt, "breathe": breathe, "put_away": put_away,
    "seated_idle": seated_idle, "hammer_strike": hammer_strike,
    "crouch": crouch, "receive_prop": receive_prop,
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
            fn = give_to(giver, receiver, prop, dur,
                         receive_hand=a.get("receive_hand", "l"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype in ("walk_to", "run_to"):
            c = chars[a["char"]]
            fn = PRIMITIVES[ptype](c, a["from_x"], a["to_x"], dur,
                                   a["ground_y"],
                                   profile=a.get("profile"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "look_at":
            c = chars[a["char"]]
            fn = look_at(c, a["angle_keys"], dur)
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype in ("point_at", "reach_to"):
            c = chars[a["char"]]
            fn = PRIMITIVES[ptype](c, tuple(a["target"]), dur)
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "turn_to":
            c = chars[a["char"]]
            fn = turn_to(c, a["facing"], dur)
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
        elif ptype == "idle":
            c = chars[a["char"]]
            fn = idle(c, dur, a["ground_y"])
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "bend_pick":
            c = chars[a["char"]]
            fn = bend_pick(c, tuple(a["target"]), dur, a["ground_y"],
                           hand=a.get("hand", "r"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "kneel_pick":
            c = chars[a["char"]]
            fn = kneel_pick(c, tuple(a["target"]), dur, a["ground_y"],
                            hand=a.get("hand", "r"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "sit_at_desk":
            c = chars[a["char"]]
            fn = sit_at_desk(c, a["chair_x"], a["seat_y"], dur,
                             a["ground_y"], desk=a.get("desk"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "stand_from_chair":
            c = chars[a["char"]]
            fn = stand_from_chair(c, dur, a["ground_y"],
                                  chair_x=a.get("chair_x"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "pick_up":
            c = chars[a["char"]]
            fn = pick_up(c, tuple(a["target"]), dur, a["ground_y"],
                         hand=a.get("hand", "r"),
                         source=a.get("source", "ground"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype in ("open_wallet", "close_wallet"):
            c = chars[a["char"]]
            fn = PRIMITIVES[ptype](c, dur, prop=a.get("prop"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "hold_pen":
            c = chars[a["char"]]
            fn = hold_pen(c, tuple(a["pen_pos"]), dict(a["paper"]), dur,
                          hand=a.get("hand", "r"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype in ("write_on_paper", "sign_document"):
            c = chars[a["char"]]
            fn = PRIMITIVES[ptype](c, dict(a["paper"]), dur,
                                   hand=a.get("hand", "r"),
                                   **({"words": a["words"]}
                                      if ptype == "write_on_paper"
                                      and "words" in a else {}))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "hand_over":
            giver, receiver = chars[a["char"]], chars[a["other"]]
            prop = a.get("prop") or {"x": 0, "y": 0}
            fn = hand_over(giver, receiver, prop, dur,
                           transfer_u=a.get("transfer_u",
                                            HAND_OVER_TRANSFER_U),
                           receive_hand=a.get("receive_hand", "l"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "walk_mud":
            c = chars[a["char"]]
            fn = walk_mud(c, a["from_x"], a["to_x"], dur, a["ground_y"],
                          sink=a.get("sink"),
                          profile=a.get("profile"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "carry_bag":
            c = chars[a["char"]]
            fn = carry_bag(c, dur, hand=a.get("hand", "r"),
                           bag=a.get("bag"),
                           sway_amp=a.get("sway_amp"),
                           sway_freq=a.get("sway_freq", 1.6))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "look_at_point":
            c = chars[a["char"]]
            fn = look_at_point(c, tuple(a["target"]), dur)
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "react_event":
            c = chars[a["char"]]
            fn = react_event(c, dur, kind=a.get("kind", "startle"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "raise_hand":
            c = chars[a["char"]]
            fn = raise_hand(c, dur, hand=a.get("hand", "r"),
                            raise_frac=a.get("raise_frac", 0.30))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "head_tilt":
            c = chars[a["char"]]
            fn = head_tilt(c, dur, head_look=a.get("head_look", 0.30),
                           torso_lean=a.get("torso_lean", 0.0))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "breathe":
            c = chars[a["char"]]
            fn = breathe(c, dur, breaths=a.get("breaths", 2))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "put_away":
            c = chars[a["char"]]
            fn = put_away(c, tuple(a["pocket"]), dur,
                          hand=a.get("hand", "r"), prop=a.get("prop"))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "seated_idle":
            c = chars[a["char"]]
            fn = seated_idle(c, dur)
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "hammer_strike":
            c = chars[a["char"]]
            fn = hammer_strike(c, tuple(a["target"]), dur,
                               a.get("ground_y"),
                               hand=a.get("hand", "r"),
                               cycles=a.get("cycles"),
                               raise_frac=a.get("raise_frac", 0.24))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "crouch":
            c = chars[a["char"]]
            fn = crouch(c, dur, a["ground_y"],
                        depth_frac=a.get("depth_frac", 0.30),
                        lean=a.get("lean", 0.35))
            compiled.append((start, dur, lambda t, fn=fn: fn(t)))
        elif ptype == "receive_prop":
            c = chars[a["char"]]
            fn = receive_prop(c, tuple(a["target"]), dur,
                              hand=a.get("hand", "r"))
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
