"""Generic camera planner for AI Clip Studio (16:9, 1920x1080).

Purely rule-based on *action types* -- never on a specific story, scene
name or character name. A segment is a dict::

    {"action_cues": [...], "speaker": ..., "text": ...,
     "duration": <seconds>, "scene_number": <int>}

``CameraPlanner.plan(segments)`` turns each segment into 1-3 shots.
``apply_camera`` then realises a shot on a rendered frame with PIL:
crop around the focus point according to the shot scale, resize back
to 1920x1080 with LANCZOS. No clip is ever cropped out of existence:
the crop box is clamped inside the frame.

Shot scales (crop factor vs. the full frame):
  establishing / graphic_insert  1.0  (wide, whole frame / flat card)
  medium / tracking / over_the_shoulder / shot_reverse_shot /
  medium_close_up  1.6
  close_up / reaction  2.6
  object_insert / extreme_close_up  3.4
"""
from __future__ import annotations

import math

from PIL import Image

from .cinematic_contracts import (
    CameraDirective, CameraMode, CameraValidation, DEFAULT_CAMERA_MODE,
    TRANSFORM_TOLERANCE)

# ---------------------------------------------------------------------------
# Shot vocabulary
# ---------------------------------------------------------------------------
SHOT_TYPES = (
    "establishing",
    "medium",
    "close_up",
    "extreme_close_up",
    "over_the_shoulder",
    "reaction",
    "object_insert",
    "tracking",
    "shot_reverse_shot",
    # Stage 3 / channel-study vocabulary (R1/R6): a chest-up
    # medium close-up, and a flat full-frame graphic insert card
    # (time / counting / object card, rendered as a card, not a
    # crop). The planner/adapter selects them; the engine renders
    # them. Neither is a full-body type.
    "medium_close_up",
    "graphic_insert",
)

SHOT_SCALE = {
    "establishing": 1.0,
    "medium": 1.6,
    "close_up": 2.6,
    "extreme_close_up": 3.4,
    "over_the_shoulder": 1.6,
    "reaction": 2.6,
    "object_insert": 3.4,
    "tracking": 1.6,
    "shot_reverse_shot": 1.6,
    "medium_close_up": 1.6,
    "graphic_insert": 1.0,
}

# Camera-movement vocabulary (Stage 3 / F9, redefined by the P0
# camera redirect 2026-11-12). A movement is a CAMERA-POSITION path,
# never a crop: see camera_at() for the geometry. The enum is
# distinct from ShotDirector's lowercase CAMERA_MOVES below, which
# are 3D camera-path labels. Within-shot movement is NOT executed by
# the product renderer BY DESIGN: the camera is FIXED within a shot
# and framing changes only by hard cut (the RicksClips rule, Mai's
# verdict 2026-11-12, independently confirmed by the @giaothucngay30
# channel study R9 — no pan/tilt/dolly/zoom/tracking was observed).
# Movement values are recorded with a limitation; camera_at() keeps
# the tested geometry for tooling/preview use only.
CAMERA_MOVEMENT = (
    "STATIC",
    "PAN_LEFT",
    "PAN_RIGHT",
    "TILT_UP",
    "TILT_DOWN",
    "DOLLY_IN",
    "DOLLY_OUT",
    "TRACKING",
    "CRANE_UP",
    "CRANE_DOWN",
    "HANDHELD",
)

# Shot types that frame FULL BODIES. F2 RULE (hard): these never
# exceed scale 1.0 — including under DOLLY_IN. A movement on a
# full-body shot may pan the crop, never zoom past the cap.
# close_up / reaction / extreme_close_up / object_insert frame a
# head or a detail, so the zoom is the point of the shot; a
# shot_reverse_shot frames heads (alternating close-ups), so it is
# not a full-body type either.
FULL_BODY_SHOT_TYPES = (
    "establishing",
    "medium",
    "tracking",
    "over_the_shoulder",
)

# Where the camera focuses for each shot type.
SHOT_FOCUS = {
    "establishing": "two_shot_center",
    "medium": "subject_full",
    "close_up": "subject_head",
    "extreme_close_up": "subject_head",
    "over_the_shoulder": "subject_head",
    "reaction": "subject_head",
    "object_insert": "object",
    "tracking": "subject_full",
    "shot_reverse_shot": "subject_head",
    "medium_close_up": "subject_head",
    "graphic_insert": "full_frame",
}

COMPOSITION_RULES = {
    "establishing": ["wide_frame", "horizon_upper_third", "depth_layers"],
    "medium": ["waist_up", "headroom", "rule_of_thirds"],
    "close_up": ["headroom", "rule_of_thirds", "eye_line"],
    "extreme_close_up": ["fill_frame_with_face", "eye_line"],
    "over_the_shoulder": ["foreground_shoulder_soft", "subject_in_focus",
                          "rule_of_thirds"],
    "reaction": ["headroom", "eye_line", "rule_of_thirds"],
    "object_insert": ["centered_object", "fill_frame", "detail_visible"],
    "tracking": ["subject_left_third", "headroom", "motion_continuity"],
    "shot_reverse_shot": ["eye_line_match", "rule_of_thirds", "headroom"],
    "medium_close_up": ["chest_up", "headroom", "eye_line"],
    "graphic_insert": ["flat_card", "centred_text", "straight_on"],
}

# Generic action-cue keywords (substrings, after lower-casing and
# underscore normalisation). No story, character or scene names here.
_CUE_HANDOFF = ("give", "handoff", "hand_over")
# NOTE: bare "bus" is NOT a boarding action — it is a location noun
# (a lead set at a bus stop must not become a boarding shot). Boarding
# is "board" / "arrive" / "depart" / "vehicle".
_CUE_BOARD = ("board", "arrive", "depart", "vehicle")
_CUE_PICK = ("bend_pick", "pick", "take", "open", "take_out", "put_away")
_CUE_MOVE = ("walk", "run", "hurry", "chase")
_CUE_LOOK = ("look", "search", "glance", "notice", "spot")
_CUE_EMOTION = ("smile", "relief", "laugh", "cry", "emotion", "worried",
                "surprise", "fear", "happy", "sad", "nod", "wave")
# v9 (overnight scene/camera work): the planner's vocabulary had 9
# shot types but plan() could only ever produce 7 -- over_the_shoulder
# and shot_reverse_shot had NO cue path at all (a dialogue shot never
# went over a shoulder, a reply never reversed the angle). Two new
# generic paths, no story names:
#   * a line segment WITH a listener (or a "face_to_face" / "dialogue"
#     cue) frames the speaker over the listener's shoulder;
#   * a "reverse_shot" cue frames the other side of the conversation
#     (the caller plans the matching pair: A speaks, B replies).
#   * "requested_shot" on the segment requests one type explicitly
#     (validated against SHOT_TYPES) -- the shot-plan test uses it to
#     prove every type on a real scene; cue planning is unchanged.
_CUE_DIALOGUE = ("face_to_face", "dialogue", "conversation",
                 "over_shoulder", "ots")
_CUE_REVERSE = ("reverse_shot", "shot_reverse_shot", "reverse_angle")
_REQUESTED_SUBJECT = {
    "object_insert": "object",
    "establishing": "scene",
    "over_the_shoulder": "speaker",
    "shot_reverse_shot": "receiver",
    "reaction": "speaker",
    "medium_close_up": "speaker",
    "graphic_insert": "scene",
}
_REQUESTED_PURPOSE = {
    "establishing": "wide establishing shot of the place",
    "medium": "medium shot of the speaking character",
    "close_up": "close-up on the speaking character",
    "extreme_close_up": "extreme close-up on the face",
    "over_the_shoulder": "over the listener's shoulder onto the speaker",
    "reaction": "close-up reaction shot",
    "object_insert": "close-up insert of the object",
    "tracking": "camera tracks alongside the moving character",
    "shot_reverse_shot": "reverse angle on the other character",
    "medium_close_up": "medium close-up on the speaking character",
    "graphic_insert": "flat graphic insert card",
}


def _norm_cues(cues):
    out = []
    for c in (cues or []):
        out.append(str(c).lower().replace("_", " ").strip())
    return out


def _has(cues, keywords):
    joined = " ".join(cues)
    return any(k.replace("_", " ") in joined or k in joined
               for k in keywords)


def _shot(shot_type, purpose, subject, duration, transition="cut",
          center_rule=None):
    """Build one shot dict in the canonical shape."""
    if center_rule is None:
        center_rule = ("center" if shot_type in ("establishing", "object_insert")
                       else "rule_of_thirds_left")
    focus = SHOT_FOCUS[shot_type]
    return {
        "narrative_purpose": purpose,
        "subject": subject,
        "shot_type": shot_type,
        "camera": {
            "scale": SHOT_SCALE[shot_type],
            "focus_target": focus,
            "center_rule": center_rule,
        },
        "focus_target": focus,
        "composition_rules": list(COMPOSITION_RULES[shot_type]),
        "transition": transition,
        "duration": round(float(duration), 3),
    }


def _shots_for_segment(segment):
    """Return a list of (shot_type, purpose, subject) for one segment.

    Priority is by action type, most specific first. A handoff is a
    3-shot chain; an arrival is a 2-shot chain; a look/search is a
    2-shot chain; everything else is a single shot.

    When a segment mixes several action groups (e.g. walk + pick, or
    run + search + open) the chain composes them in story order —
    tracking/medium first, then the object insert, then the reaction —
    capped at 3 shots, de-duplicated by shot type. A single-group
    segment keeps exactly its old chain, so the single-cue behaviour
    is unchanged.
    """
    cues = _norm_cues(segment.get("action_cues"))
    speaker = (segment.get("speaker") or "").strip().lower()
    # v9: a line WITH a listener is dialogue, never narration -- the
    # old `or not cues` clause misclassified a bare line (speaker +
    # listener, no action cues) as narration and planned an
    # establishing shot for it, so the over-the-shoulder cue path
    # never fired for ordinary two-character dialogue.
    is_narration = speaker in ("narrator", "narration", "") or (
        not cues and not segment.get("listener"))

    # v9: an explicit shot request on the segment (validated) wins --
    # the shot-plan test uses it to prove every shot type on a real
    # scene. Anything else falls through to cue planning, unchanged.
    requested = segment.get("requested_shot")
    if requested in SHOT_TYPES:
        return [(requested, _REQUESTED_PURPOSE[requested],
                 _REQUESTED_SUBJECT.get(requested, "speaker"))]
    if requested is not None:
        raise ValueError(f"unknown requested_shot: {requested!r} "
                         f"(expected one of {sorted(SHOT_TYPES)})")

    # Dialogue segments ("kind": "line"): characters are standing and
    # talking, so movement cues do NOT apply — the camera should frame
    # the speaker, the object being discussed, or the emotion.
    # Narrator + object cue  -> insert on the object under narration.
    # Narrator + emotion cue -> reaction close-up.
    # Character speaker + emotion cue -> reaction close-up.
    # Character speaker otherwise -> medium on the speaker.
    # Narrator with neither -> establishing (breathing room).
    # v9: a line WITH a listener (or a face-to-face / dialogue cue)
    # goes over the listener's shoulder -- but an emotional beat still
    # wins the reaction close-up.
    if segment.get("kind") == "line":
        if is_narration:
            # A boarding/arrival line is about the vehicle arriving,
            # not about an object — the boarding chain wins over pick.
            if _has(cues, _CUE_BOARD):
                return [
                    ("establishing", "wide shot of the arrival place and "
                     "the vehicle entering the frame", "scene"),
                    ("medium", "medium shot of the character as the "
                     "vehicle arrives / the character boards", "speaker"),
                ]
            if _has(cues, _CUE_PICK):
                return [("object_insert", "close-up insert of the object "
                         "being talked about, under narration", "object")]
            if _has(cues, _CUE_EMOTION):
                return [("reaction", "close-up reaction shot carrying "
                         "the emotional beat", "speaker")]
            return [("establishing", "wide establishing shot under "
                     "narration, letting the scene breathe", "scene")]
        if _has(cues, _CUE_EMOTION):
            return [("reaction", "close-up reaction shot carrying the "
                     "emotional beat", "speaker")]
        # v9: a reverse cue on a dialogue line is the shot-reverse-shot
        # half of the conversation -- it wins over the plain OTS, so a
        # reply line can ask for the reverse angle by cue, not only by
        # requested_shot.
        if _has(cues, _CUE_REVERSE):
            return [("shot_reverse_shot",
                     "reverse angle on the replying character, eye-line "
                     "matched with the previous shot", "speaker")]
        if segment.get("listener") or _has(cues, _CUE_DIALOGUE):
            return [("over_the_shoulder",
                     "over the listener's shoulder onto the speaking "
                     "character, the conversation in one frame",
                     "speaker")]
        return [("medium", "medium shot of the speaking character",
                 "speaker")]
    if _has(cues, _CUE_HANDOFF):
        return [
            ("establishing", "establish both characters and the space "
             "between them before the exchange", "two_shot"),
            ("object_insert", "show the exchanged object clearly in "
             "the hands", "object"),
            ("reaction", "close-up reaction of the receiver as the "
             "object changes hands", "receiver"),
        ]
    if _has(cues, _CUE_BOARD):
        return [
            ("establishing", "wide shot of the arrival place and the "
             "vehicle entering the frame", "scene"),
            ("medium", "medium shot of the character as the vehicle "
             "arrives / the character boards", "speaker"),
        ]
    # v9: reverse angle -- the other side of a conversation. The
    # caller plans the matching pair (A speaks, B replies); each side
    # is one shot, eye-line matched by the renderer.
    if _has(cues, _CUE_REVERSE):
        return [("shot_reverse_shot",
                 "reverse angle on the other character, eye-line "
                 "matched with the previous shot", "receiver")]
    # Multi-group composition (story order: move -> look -> pick -> emotion).
    groups = []
    if _has(cues, _CUE_MOVE):
        groups.append(("tracking", "camera tracks alongside the moving "
                      "character, keeping them in the same third of frame",
                      "speaker"))
    if _has(cues, _CUE_LOOK):
        groups.append(("medium", "medium shot of the character looking / "
                      "searching", "speaker"))
    if _has(cues, _CUE_PICK):
        groups.append(("object_insert", "close-up insert of the object "
                      "being picked up, taken or opened", "object"))
    if _has(cues, _CUE_LOOK) or _has(cues, _CUE_EMOTION):
        groups.append(("reaction", "close-up reaction to what was seen, "
                      "found, or felt", "speaker"))
    if groups:
        seen, out = set(), []
        for g in groups:
            if g[0] not in seen:
                seen.add(g[0])
                out.append(g)
        return out[:3]
    if is_narration:
        return [
            ("establishing", "wide establishing shot under narration, "
             "letting the scene breathe", "scene"),
        ]
    # Generic fallback: a spoken line with unrecognised action cues.
    return [
        ("medium", "medium shot of the speaking character", "speaker"),
    ]


def _crop_rect(scale, focus_xy, frame_w, frame_h):
    """Crop rect [left, top, right, bottom] for a scale + focus."""
    cw, ch = frame_w / scale, frame_h / scale
    cx, cy = focus_xy
    left = min(max(cx - cw / 2.0, 0.0), frame_w - cw)
    top = min(max(cy - ch / 2.0, 0.0), frame_h - ch)
    return left, top, left + cw, top + ch


def _fit_shift(preferred, need_lo, need_hi, size, frame_size):
    """Crop edge that contains a need window [need_lo, need_hi].

    Keeps ``preferred`` when the window fits inside
    [preferred, preferred + size]; otherwise the SMALLEST shift
    that fits it, clamped inside the frame. The window fits the
    crop (callers check), so the valid range
    [need_hi - size, need_lo] ∩ [0, frame_size - size] is
    non-empty. (Stage 3 / F9 framing fix: the old clamp ignored
    the focus entirely and parked every close-up subject at the
    crop's left/top edge, leaving an empty right half.)"""
    lo = max(0.0, need_hi - size)
    hi = min(need_lo, frame_size - size)
    return min(max(preferred, lo), hi)


def _other_status(other, rect):
    """'in' / 'out' / 'partial' for a character vs a crop rect.

    The body box is [cx-half_w, cx+half_w] x [head_y, foot_y]. 'in'
    only when the whole box sits inside the crop with the same
    margins validate_framing uses (2% sides, 5% head headroom, 2%
    feet); 'out' when the whole box clears the crop; anything else is
    'partial' -- the head-cut defect.
    """
    l, t, r, b = rect
    cw, ch = r - l, b - t
    sl = other["cx"] - other["half_w"]
    sr = other["cx"] + other["half_w"]
    st, sb = other["head_y"], other["foot_y"]
    if (sl >= l + 0.02 * cw and sr <= r - 0.02 * cw
            and st >= t + 0.05 * ch and sb <= b - 0.02 * ch):
        return "in"
    if sr <= l or sl >= r or sb <= t or st >= b:
        return "out"
    return "partial"


def _track_best(best, n_issues, scale, focus, issues):
    if best is None or n_issues < best[0]:
        return (n_issues, scale, focus, list(issues))
    return best


def _fix_partial_others(shot, focus, subjects, others, frame_w, frame_h):
    """Shift the crop so every 'other' is fully in or fully out.

    Returns (focus, notes, remaining_issues). Per partial other, in
    order: (a) pull it fully IN by re-centring the crop on the union
    of subjects + other (when the union fits the crop); (b) push it
    fully OUT by shifting the crop away from it while the subjects
    still fit. Repeats until no partial other remains or no shift
    helps (then the caller zooms out a step).
    """
    scale = float(shot["camera"]["scale"])
    cw, ch = frame_w / scale, frame_h / scale
    notes = []
    for _round in range(4):
        rect = _crop_rect(scale, focus, frame_w, frame_h)
        partials = [o for o in others
                    if _other_status(o, rect) == "partial"]
        if not partials:
            return focus, notes, []
        other = partials[0]
        # (a) pull fully IN: union of subjects + other must fit.
        # The need window gets a 2 px slack beyond the required
        # margins: without it the crop lands EXACTLY on the headroom
        # boundary and float error flips the in/out test back to
        # partial on the next round (the v7 shot test caught this --
        # 4 identical shifts, still partial).
        boxes = list(subjects) + [other]
        need_l = min(s["cx"] - s["half_w"] for s in boxes) - 0.02 * cw - 2
        need_r = max(s["cx"] + s["half_w"] for s in boxes) + 0.02 * cw + 2
        need_t = min(s["head_y"] for s in boxes) - 0.05 * ch - 2
        need_b = max(s["foot_y"] for s in boxes) + 0.02 * ch + 2
        if need_r - need_l <= cw and need_b - need_t <= ch:
            # Centre the union (two-shot balance), clamped so the
            # need window still fits — the old clamp parked the
            # union at the crop's left/top edge.
            new_left = _fit_shift((need_l + need_r - cw) / 2.0,
                                  need_l, need_r, cw, frame_w)
            new_top = _fit_shift((need_t + need_b - ch) / 2.0,
                                 need_t, need_b, ch, frame_h)
            focus = (new_left + cw / 2.0, new_top + ch / 2.0)
            notes.append("shifted crop to include a partially-overlapped "
                         "character fully (head-safe)")
            continue
        # (b) push fully OUT: minimal shift in each of 4 directions
        # (+2 px clear of the edge, for the same float-boundary
        # reason as branch (a)); accept the first that keeps the
        # subjects fitting and puts this other fully out.
        l, t, r, b = rect
        sl = other["cx"] - other["half_w"]
        sr = other["cx"] + other["half_w"]
        st, sb = other["head_y"], other["foot_y"]
        fixed = False
        for dx, dy in ((sr - l + 2.0, 0.0), (sl - r - 2.0, 0.0),
                       (0.0, st - b - 2.0), (0.0, sb - t + 2.0)):
            cand = (focus[0] + dx, focus[1] + dy)
            crect = _crop_rect(scale, cand, frame_w, frame_h)
            if _other_status(other, crect) != "out":
                continue
            iss, _ = CameraPlanner.validate_framing(
                shot, cand, subjects, frame_w, frame_h)
            if not iss:
                focus = cand
                notes.append("shifted crop to push a partially-overlapped "
                             "character fully out of frame (head-safe)")
                fixed = True
                break
        if not fixed:
            return focus, notes, [
                f"partial overlap cannot be fixed at scale {scale} "
                f"(other at cx={other['cx']:.0f})"]
    rect = _crop_rect(scale, focus, frame_w, frame_h)
    remaining = [f"partial overlap remains after shifts "
                 f"(other at cx={o['cx']:.0f})"
                 for o in others if _other_status(o, rect) == "partial"]
    return focus, notes, remaining


def normalize_movement(value) -> str:
    """Normalise a camera-movement value to a CAMERA_MOVEMENT enum
    string. Accepts any case / underscore / hyphen / space spelling
    of an enum member; anything else (None, "", unknown) degrades to
    "STATIC" — a bad movement label must never crash a render."""
    if value is None:
        return "STATIC"
    norm = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    return norm if norm in CAMERA_MOVEMENT else "STATIC"


class CameraPlanner:
    """Plan camera shots from generic per-segment action cues."""

    @staticmethod
    def plan(segments):
        """segments: list of dicts {action_cues, speaker, text, duration,
        scene_number}. Returns a flat list of shot dicts, in order.
        Shot durations split the segment duration evenly and sum back
        to it (last shot absorbs rounding)."""
        shots = []
        for seg in segments or []:
            templates = _shots_for_segment(seg)
            total = seg.get("duration")
            try:
                total = float(total) if total else 3.0
            except (TypeError, ValueError):
                total = 3.0
            total = max(total, 0.3 * len(templates))
            per = total / len(templates)
            for i, (stype, purpose, subject) in enumerate(templates):
                dur = per if i < len(templates) - 1 else total - per * i
                shot = _shot(stype, purpose, subject, dur,
                             transition="cut")
                shot["scene_number"] = seg.get("scene_number")
                shot["speaker"] = seg.get("speaker")
                shots.append(shot)
        return shots

    @staticmethod
    def apply_camera(img, shot, focus_xy=None):
        """Crop around focus_xy by the shot scale, resize to the input
        size with LANCZOS. focus_xy defaults to frame centre. The crop
        box is clamped inside the frame, so edge focus points are safe.
        Returns a new PIL Image (input untouched).

        WARNING (Phase C / D2): this is a MECHANISM, not a framing
        policy. It must NOT be called per frame with a live,
        pose-dependent focus (e.g. the current head joint): that is
        the implicit head-tracking defect (W8 audit: background
        moved within the shot while the head stayed centred). The
        default path freezes ONE crop per shot from STANDING boxes
        via :func:`anchor_focus_for_shot` and applies the frozen
        crop to every frame with :func:`apply_camera_anchored`.
        """
        w, h = img.size
        scale = float((shot or {}).get("camera", {}).get("scale")
                      or SHOT_SCALE.get((shot or {}).get("shot_type", "medium"), 1.6))
        scale = max(1.0, scale)
        cw, ch = w / scale, h / scale
        cx, cy = focus_xy if focus_xy is not None else (w / 2.0, h / 2.0)
        left = min(max(cx - cw / 2.0, 0.0), w - cw)
        top = min(max(cy - ch / 2.0, 0.0), h - ch)
        box = (int(round(left)), int(round(top)),
               int(round(left + cw)), int(round(top + ch)))
        return img.crop(box).resize((w, h), Image.LANCZOS)

    @staticmethod
    def validate_framing(shot, focus_xy, subjects, frame_w=1920,
                         frame_h=1080):
        """Check a shot's crop keeps every subject whole in frame, and
        return a corrected focus point.

        Audit 2026-11-11 (Chiếc Ví v4 + Eiffel v5, real frames): the
        crop-by-scale camera cut Lan half out of the right edge, cut
        Minh's head off in an object_insert, and left a reaction shot
        dominated by an empty brown wall -- because ``apply_camera``
        only clamps the crop box inside the frame, it never checks
        whether the SUBJECT survives inside the crop. A shot that
        cuts its subject is not a shot; it is a framing bug.

        shot: shot dict (scale from ``camera.scale`` or SHOT_SCALE).
        focus_xy: (x, y) the crop is centred on, full-frame coords.
        subjects: list of {"cx", "head_y", "foot_y", "half_w"} in
        full-frame coords -- the people/objects the shot must keep.
        Returns (issues, corrected_focus_xy): issues is a list of
        strings (empty = framing is safe); the corrected focus shifts
        the crop so every subject fits with headroom, where that is
        possible. A subject WIDER than the crop cannot be fixed by
        shifting -- it is reported as a zoom-out issue and the focus
        is left unchanged.
        """
        scale = float((shot or {}).get("camera", {}).get("scale")
                      or SHOT_SCALE.get((shot or {}).get("shot_type",
                                                        "medium"), 1.6))
        scale = max(1.0, scale)
        cw, ch = frame_w / scale, frame_h / scale
        cx, cy = focus_xy if focus_xy is not None else (frame_w / 2.0,
                                                        frame_h / 2.0)
        left = min(max(cx - cw / 2.0, 0.0), frame_w - cw)
        top = min(max(cy - ch / 2.0, 0.0), frame_h - ch)
        right, bottom = left + cw, top + ch
        issues = []
        if not subjects:
            return issues, (cx, cy)
        # what the crop must contain (with headroom + edge margins)
        need_l = min(s["cx"] - s["half_w"] for s in subjects) - 0.02 * cw
        need_r = max(s["cx"] + s["half_w"] for s in subjects) + 0.02 * cw
        need_t = min(s["head_y"] for s in subjects) - 0.05 * ch
        need_b = max(s["foot_y"] for s in subjects) + 0.02 * ch
        for i, s in enumerate(subjects):
            if s["head_y"] < top + 0.05 * ch:
                issues.append(f"subject {i}: head cut at top "
                              f"(head_y={s['head_y']:.0f}, "
                              f"crop_top={top:.0f})")
            if s["foot_y"] > bottom - 0.02 * ch:
                issues.append(f"subject {i}: feet cut at bottom "
                              f"(foot_y={s['foot_y']:.0f}, "
                              f"crop_bottom={bottom:.0f})")
            if s["cx"] - s["half_w"] < left + 0.02 * cw:
                issues.append(f"subject {i}: cut at left edge "
                              f"(cx={s['cx']:.0f})")
            if s["cx"] + s["half_w"] > right - 0.02 * cw:
                issues.append(f"subject {i}: cut at right edge "
                              f"(cx={s['cx']:.0f})")
        if need_r - need_l > cw or need_b - need_t > ch:
            issues.append("subjects do not fit the crop at this scale "
                          "-- zoom out (smaller scale), do not just "
                          "shift the focus")
            return issues, (cx, cy)
        # Shift the crop so the required window fits inside it,
        # keeping the requested focus where possible: the crop
        # stays centred on the focus when the need window fits
        # around it, and otherwise shifts by the smallest amount
        # that fits the window (never to an extreme edge — the old
        # clamp put every close-up subject at the frame's left edge
        # with an empty right half, Stage 3 / F9 framing fix).
        new_left = _fit_shift(cx - cw / 2.0, need_l, need_r, cw,
                              frame_w)
        new_top = _fit_shift(cy - ch / 2.0, need_t, need_b, ch,
                             frame_h)
        corrected = (new_left + cw / 2.0, new_top + ch / 2.0)
        return issues, corrected

    @staticmethod
    def safe_frame(shot, focus_xy, subjects, others=None, frame_w=1920,
                   frame_h=1080, max_scale=None):
        """Return (safe_shot, safe_focus, notes): a shot + focus that
        cannot repeat the v4/v5 framing defects.

        Audit 2026-11-11 (Chiếc Ví v4: 8 defects, Eiffel v5: 5): the
        systematic pattern was a 3.4x object_insert centred on the
        wallet/photo that sliced the characters' heads -- the crop
        only had to contain the OBJECT, so a head at the crop edge was
        half-cut; and 2.6x reactions whose two subjects did not fit
        the crop at all. ``validate_framing`` only shifts the crop and
        cannot fix either case (it reports "do not fit" and leaves the
        focus unchanged).

        safe_frame fixes both, in order, never by faking the scale:
        1. Try the planned scale. If the intended subjects do not fit
           it, step DOWN the scale ladder (3.4 -> 2.6 -> 1.6 -> 1.0)
           until they do. An insert that must show the whole pick-up
           becomes a close-up; a reaction that cannot hold two people
           becomes a medium. The shot TYPE is kept (so the plan still
           reads as an insert / reaction) but the applied scale is
           recorded on the returned shot dict.
        2. For every OTHER character: it must end up FULLY inside the
           crop or FULLY outside it -- never half-cut. A partial other
           is fixed by shifting the crop so the other is fully IN
           (re-centre on the union of subjects + other, when it fits)
           or fully OUT (shift the crop away from the other while the
           subjects still fit). If neither works at this scale, zoom
           out one step and retry.
        3. If no scale works (subjects wider than the full frame --
           cannot happen for a single character, but a two-shot at
           opposite edges comes close), return the widest scale with
           the best focus and notes listing what still fails. The
           caller must surface the notes, not silently ship the shot.

        subjects / others: {"cx", "head_y", "foot_y", "half_w"} dicts
        in full-frame coords. Returns (safe_shot, safe_focus, notes)
        where safe_shot is a COPY of ``shot`` with camera.scale set to
        the applied scale and a "safe_frame" note; the input shot is
        untouched.

        ``max_scale`` (F2, TEST C Phase 2): an optional cap on the
        applied scale. A caller framing FULL BODIES passes 1.0 so a
        pose-dependent subject box can never zoom a full-body shot
        up mid-shot (a kneel shrinks the box and the ladder would
        otherwise climb to 1.6x while the character kneels,
        inflating the head to 33% of the frame). None (default)
        keeps the old behaviour: the ladder starts at the planned
        scale.
        """
        others = list(others or [])
        planned_scale = float((shot or {}).get("camera", {}).get("scale")
                              or SHOT_SCALE.get(
                                  (shot or {}).get("shot_type", "medium"),
                                  1.6))
        planned_scale = max(1.0, planned_scale)
        if not subjects:
            # Stage 3 (empty-cast / location-only shot): with nothing
            # to frame, the only honest crop is the full frame. A
            # 1.6x/2.6x crop centred on nothing would zoom into an
            # arbitrary patch of the location.
            full = dict(shot or {})
            full_cam = dict((shot or {}).get("camera") or {})
            full_cam["scale"] = 1.0
            full["camera"] = full_cam
            centre = focus_xy if focus_xy is not None else (
                frame_w / 2.0, frame_h / 2.0)
            full["safe_frame"] = {
                "planned_scale": planned_scale,
                "applied_scale": 1.0,
                "focus": [round(centre[0], 1), round(centre[1], 1)],
                "notes": ["no subjects: full frame (location-only shot)"],
            }
            return full, centre, ["no subjects: full frame "
                                  "(location-only shot)"]
        if max_scale is not None:
            planned_scale = min(planned_scale,
                                max(1.0, float(max_scale)))
        ladder = [s for s in (3.4, 2.6, 1.6, 1.0) if s <= planned_scale + 1e-9]
        if not ladder:
            ladder = [1.0]
        notes = []
        best = None  # (n_issues, scale, focus, issues)
        for scale in ladder:
            trial = dict(shot or {})
            trial_cam = dict((shot or {}).get("camera") or {})
            trial_cam["scale"] = scale
            trial["camera"] = trial_cam
            issues, focus = CameraPlanner.validate_framing(
                trial, focus_xy, subjects, frame_w, frame_h)
            if any("do not fit" in i for i in issues):
                notes.append(f"scale {scale}: subjects do not fit "
                             f"-- zoom out")
                best = _track_best(best, len(issues), scale, focus, issues)
                continue
            # subjects fit at this scale: fix partial others by shifting.
            focus, shift_notes, remaining = _fix_partial_others(
                trial, focus, subjects, others, frame_w, frame_h)
            notes.extend(shift_notes)
            if not remaining:
                safe = dict(trial)
                safe["safe_frame"] = {
                    "planned_scale": planned_scale,
                    "applied_scale": scale,
                    "focus": [round(focus[0], 1), round(focus[1], 1)],
                    "notes": notes,
                }
                return safe, focus, notes
            best = _track_best(best, len(remaining), scale, focus, remaining)
            notes.append(f"scale {scale}: {len(remaining)} partial "
                         f"other(s) remain -- zoom out")
        # nothing worked: widest scale, best focus found, honest notes.
        _, scale, focus, issues = best
        trial = dict(shot or {})
        trial_cam = dict((shot or {}).get("camera") or {})
        trial_cam["scale"] = scale
        trial["camera"] = trial_cam
        notes.append("NO SCALE FIXES THE FRAMING: subjects/others "
                     f"still conflict at scale {scale}: {issues}")
        safe = dict(trial)
        safe["safe_frame"] = {
            "planned_scale": planned_scale,
            "applied_scale": scale,
            "focus": [round(focus[0], 1), round(focus[1], 1)],
            "notes": notes,
        }
        return safe, focus, notes

    @staticmethod
    def apply_camera_safe(img, shot, focus_xy=None, subjects=None,
                          others=None):
        """apply_camera through safe_frame: the crop is re-framed so
        subjects fit and no other character is half-cut. Returns
        (image, safe_shot, safe_focus, notes)."""
        safe_shot, safe_focus, notes = CameraPlanner.safe_frame(
            shot, focus_xy, subjects or [], others or [],
            frame_w=img.size[0], frame_h=img.size[1])
        return (CameraPlanner.apply_camera(img, safe_shot, safe_focus),
                safe_shot, safe_focus, notes)

    @staticmethod
    def shot_diversity_report(shots):
        """Diversity summary of a planned shot list."""
        types = [s.get("shot_type") for s in (shots or [])]
        counts = {}
        for t in types:
            counts[t] = counts.get(t, 0) + 1
        uniq = sorted(set(types))
        return {
            "total_shots": len(types),
            "num_shot_types": len(uniq),
            "shot_types": uniq,
            "counts": counts,
            "has_close_up": any(t in ("close_up", "extreme_close_up",
                                      "reaction") for t in types),
            "has_insert": "object_insert" in types,
            "has_reaction": "reaction" in types,
            "has_tracking": "tracking" in types,
            "has_establishing": "establishing" in types,
        }


# Module-level aliases (same behaviour, for callers that prefer functions).
def plan(segments):
    return CameraPlanner.plan(segments)


def apply_camera(img, shot, focus_xy=None):
    return CameraPlanner.apply_camera(img, shot, focus_xy)


def safe_frame(shot, focus_xy, subjects, others=None, frame_w=1920,
               frame_h=1080, max_scale=None):
    return CameraPlanner.safe_frame(shot, focus_xy, subjects, others,
                                    frame_w, frame_h, max_scale)


def apply_camera_safe(img, shot, focus_xy=None, subjects=None,
                      others=None):
    return CameraPlanner.apply_camera_safe(img, shot, focus_xy, subjects,
                                           others)


def validate_framing(shot, focus_xy, subjects, frame_w=1920, frame_h=1080):
    return CameraPlanner.validate_framing(shot, focus_xy, subjects,
                                          frame_w, frame_h)


def shot_diversity_report(shots):
    return CameraPlanner.shot_diversity_report(shots)


# ---------------------------------------------------------------------------
# Shot Director (§4) — staging that explains with images, not illustration.
#
# CameraPlanner picks shot TYPES from action cues. ShotDirector takes
# those exact shots (1:1 — it NEVER adds shots to inflate a formal
# camera score) and directs each one: what the audience must notice,
# the main action, the emotion, the angle, the size, where the
# characters stand, the lighting, how the camera moves, and the exact
# cut point. All of it is driven by data — the segment plus an optional
# scene package (location / time of day / mood / characters / props) —
# never by a story, scene or character name.
#
# A shot's direction is a dict with exactly these 9 keys:
#   attention_target, main_action, emotion, angle, shot_size,
#   character_positions, lighting, camera_move, cut_point
# ``camera_move`` also carries a ``camera_path`` (from/to camera
# position+target in world units) so the 2.5D renderer can execute the
# move with PerspectiveCamera.interpolate() — it is not a label.
# ---------------------------------------------------------------------------
ANGLES = (
    "eye_level", "low_angle", "high_angle", "dutch",
    "over_shoulder", "birds_eye",
)

CAMERA_MOVES = (
    "static", "pan", "tilt", "dolly_in", "dolly_out",
    "tracking", "crane_up", "arc",
)

EMOTIONS = (
    "neutral", "tension", "relief", "surprise", "sadness",
    "joy", "fear", "determination",
)

# angle per shot type (a look/search looks UP from low; an object insert
# looks DOWN at the object; a reaction stays at eye level with the face)
_ANGLE_BY_SHOT = {
    "establishing": "high_angle",
    "medium": "eye_level",
    "close_up": "eye_level",
    "extreme_close_up": "eye_level",
    "over_the_shoulder": "over_shoulder",
    "reaction": "eye_level",
    "object_insert": "high_angle",
    "tracking": "eye_level",
    "shot_reverse_shot": "eye_level",
    "medium_close_up": "eye_level",
    "graphic_insert": "eye_level",
}

# ---------------------------------------------------------------------------
# Per-shot viewpoints (Stage 3 / F9, P0 camera redirect 2026-11-12).
#
# Mai's verdict: the videos did not change camera angle — shot types
# differed only by crop scale + focus (zoom). The fix is REAL
# viewpoint geometry: every shot resolves to its own PerspectiveCamera
# (position + target), and the product renderer threads that camera
# through the whole shot render (background, horizon, parallax,
# character projection). ShotDirector's angle/camera_move labels are
# NOT on the executed path; viewpoint_for_shot() is the executed
# equivalent, sharing the ANGLES / _ANGLE_BY_SHOT vocabulary.
#
# Geometry: cameras sit on a SPHERE around the subject target, at the
# same radius as the legacy fixed camera (so the same subject at the
# same camera distance keeps the same head size across angles — the
# F2 no-head-pump rule). Angles differ by elevation and azimuth:
#   eye_level      base elevation (~9.5 deg, the legacy camera)
#   low_angle      camera below eye line, looking up
#   high_angle     camera above, looking down
#   birds_eye      steep top-down
#   dutch          eye-level geometry + a frame tilt (see tilt_deg_for)
#   over_shoulder  azimuth toward the counterpart (camera behind the
#                  listener's shoulder, target on the subject)
# Shot-reverse-shot alternates azimuth across the axis by srs_side.
# FOV is never varied (46 deg, the legacy value).
# ---------------------------------------------------------------------------
from .renderer25d.camera import PerspectiveCamera  # noqa: E402

# Legacy fixed camera (product_renderer.CAM): the default viewpoint.
DEFAULT_CAM_POSITION = (0.0, 2.0, 4.8)
DEFAULT_CAM_TARGET = (0.0, 1.2, 0.0)
DEFAULT_CAM_FOV = 46.0

# Offset of the legacy camera from its target, and the sphere radius
# every viewpoint preserves. eye_level returns this offset EXACTLY so
# a default-angle shot is pixel-identical to the legacy render.
_EYE_OFFSET = (0.0, 0.8, 4.8)
_VIEWPOINT_RADIUS = math.sqrt(0.8 * 0.8 + 4.8 * 4.8)
_BASE_ELEV_DEG = math.degrees(math.atan2(0.8, 4.8))

# Elevation (degrees above the horizontal, seen from the target) per
# angle. dutch shares eye_level geometry; its tilt is a frame
# rotation applied by the renderer (tilt_deg_for).
_ANGLE_ELEV_DEG = {
    "eye_level": _BASE_ELEV_DEG,
    "low_angle": -8.0,
    "high_angle": 32.0,
    "birds_eye": 62.0,
    "dutch": _BASE_ELEV_DEG,
    "over_shoulder": _BASE_ELEV_DEG,
}

# Azimuth (degrees) for the two-sided framings.
_OTS_AZIMUTH_DEG = 28.0
_SRS_AZIMUTH_DEG = 18.0

# Dutch frame tilt, degrees (counter-clockwise, applied by the
# renderer to the composited frame before subtitles).
DUTCH_TILT_DEG = 7.0


# Executed viewpoint defaults (Stage 3 / F9 + channel study R3):
# ShotDirector's _ANGLE_BY_SHOT labels stay as-is; the EXECUTED
# viewpoint for an establishing shot with no explicit angle is
# eye-level at a WIDER radius, so the place reads and the characters
# sit small in the wide. (The F9 probe's establishing still used the
# high_angle default: the frame was ~80% ground plane and the
# buildings were cut at the top edge — a high angle looks at the
# ground, it does not establish a place. R3: the reference channel's
# wides are eye-level.) An explicit camera_angle always wins. Other
# shot types keep the standard radius (same distance -> same head
# size, the F2 rule).
_VIEWPOINT_ANGLE_BY_SHOT = {
    "establishing": "eye_level",
}
_VIEWPOINT_RADIUS_BY_SHOT = {
    "establishing": 7.5,
}


def resolve_camera_angle(shot_type, camera_angle=None):
    """Resolve the ANGLES-vocabulary angle for a shot.

    An explicit valid ``camera_angle`` wins; otherwise the
    _ANGLE_BY_SHOT default for the shot type; unknown shot types and
    invalid angles degrade to "eye_level". Never raises."""
    if isinstance(camera_angle, str):
        angle = camera_angle.strip().lower().replace("-", "_")
        if angle in ANGLES:
            return angle
    return _ANGLE_BY_SHOT.get(shot_type, "eye_level")


def resolve_viewpoint_angle(shot_type, camera_angle=None):
    """The EXECUTED angle for a shot: an explicit valid
    ``camera_angle`` wins; otherwise the viewpoint default for the
    shot type (_VIEWPOINT_ANGLE_BY_SHOT, else _ANGLE_BY_SHOT);
    unknown shot types and invalid angles degrade to "eye_level".
    Never raises. The renderer reports this angle, so the report
    matches the camera that actually rendered the shot."""
    if isinstance(camera_angle, str):
        angle = camera_angle.strip().lower().replace("-", "_")
        if angle in ANGLES:
            return angle
    return _VIEWPOINT_ANGLE_BY_SHOT.get(
        shot_type, _ANGLE_BY_SHOT.get(shot_type, "eye_level"))


def tilt_deg_for(angle):
    """Frame tilt in degrees for an angle (dutch only, else 0.0)."""
    return DUTCH_TILT_DEG if angle == "dutch" else 0.0


def _spherical_offset(azimuth_deg, elevation_deg,
                      radius=_VIEWPOINT_RADIUS):
    """Camera offset from target at (azimuth, elevation) on the sphere.

    Azimuth 0 = directly in front of the target (+z); positive
    azimuth moves the camera toward +x (frame-left side of the
    subject). Elevation is measured from the horizontal."""
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    return (radius * math.cos(el) * math.sin(az),
            radius * math.sin(el),
            radius * math.cos(el) * math.cos(az))


def viewpoint_for_shot(shot_type="medium", camera_angle=None,
                       subject_pos=(0.0, 1.2, 0.0), counterpart_x=None,
                       srs_side=0, radius_scale=1.0):
    """Resolve a shot's REAL viewpoint: a PerspectiveCamera.

    ``subject_pos`` is the world target point (usually the subject's
    world x at eye height, z on the subject plane). ``counterpart_x``
    is the other character's world x (over-the-shoulder: the camera
    sits on the counterpart's side). ``srs_side`` (0/1) alternates
    the azimuth for shot_reverse_shot runs. A shot that declares an
    angle always gets that angle's camera — never silently the fixed
    legacy camera; only the eye_level default reproduces it exactly.

    ``radius_scale`` (scale-variant rule): multiplies the viewpoint
    radius, dollying the camera out along the same azimuth/elevation
    so a scaled (taller) subject's standing box fits the frame. 1.0
    (default) reproduces the exact legacy geometry; non-positive or
    non-finite values fall back to 1.0.

    Returns a PerspectiveCamera (fov 46, aspect 16:9) positioned on
    the viewpoint sphere around ``subject_pos``. Establishing shots
    use the wide radius (_VIEWPOINT_RADIUS_BY_SHOT); all other types
    share the standard radius (same distance -> same head size).
    """
    angle = resolve_viewpoint_angle(shot_type, camera_angle)
    tx, ty, tz = (float(v) for v in subject_pos)
    elev = _ANGLE_ELEV_DEG.get(angle, _BASE_ELEV_DEG)
    try:
        rscale = float(radius_scale)
    except (TypeError, ValueError):
        rscale = 1.0
    if not (rscale > 0) or rscale != rscale or rscale in (
            float("inf"), float("-inf")):
        rscale = 1.0
    radius = _VIEWPOINT_RADIUS_BY_SHOT.get(shot_type,
                                           _VIEWPOINT_RADIUS) * rscale
    azimuth = 0.0
    if angle == "over_shoulder" or shot_type == "over_the_shoulder":
        if counterpart_x is not None and tx is not None:
            side = 1.0 if float(counterpart_x) >= tx else -1.0
        else:
            side = 1.0
        azimuth = side * _OTS_AZIMUTH_DEG
    elif shot_type == "shot_reverse_shot":
        azimuth = _SRS_AZIMUTH_DEG if int(srs_side or 0) else -_SRS_AZIMUTH_DEG
    if angle == "eye_level" and azimuth == 0.0 \
            and radius == _VIEWPOINT_RADIUS:
        # Exact legacy offset: default shots stay pixel-identical.
        off = _EYE_OFFSET
    else:
        off = _spherical_offset(azimuth, elev, radius)
    position = (tx + off[0], ty + off[1], tz + off[2])
    return PerspectiveCamera(position=position, target=(tx, ty, tz),
                             fov_deg=DEFAULT_CAM_FOV, aspect=16.0 / 9.0)


def camera_at(movement, t01, base_camera, direction=1):
    """Camera position along a movement path at progress t01 in [0,1].

    REAL camera-position geometry (never a crop): TRACKING translates
    camera + target laterally (subject stays framed, background
    parallaxes); DOLLY_IN/OUT move along the view axis; PAN/TILT move
    the target (camera rotates); CRANE moves the camera height;
    HANDHELD adds small deterministic offsets. STATIC returns the
    base camera unchanged.

    NOTE (P0 redirect + channel study R9): the product renderer
    does not execute within-shot movement BY DESIGN (camera fixed
    within a shot, framing changes by hard cut; movement values
    render STATIC with a recorded limitation). This resolver is
    the tested geometry for tooling/preview use only.
    """
    move = normalize_movement(movement)
    t = min(1.0, max(0.0, float(t01)))
    if move == "STATIC" or t == 0.0 and move != "HANDHELD":
        return base_camera
    pos = base_camera.position
    tgt = base_camera.target
    if move == "HANDHELD":
        dx = 0.05 * math.sin(2 * math.pi * 3 * t + 0.7)
        dy = 0.03 * math.sin(2 * math.pi * 2.3 * t + 1.9)
        return base_camera.moved(dpos=(dx, dy, 0.0))
    if move == "TRACKING":
        shift = 1.6 * float(direction) * t
        return base_camera.moved(dpos=(shift, 0.0, 0.0),
                                 dtarget=(shift, 0.0, 0.0))
    if move in ("DOLLY_IN", "DOLLY_OUT"):
        frac = 0.15 * t * (1.0 if move == "DOLLY_IN" else -1.0)
        delta = tuple((tgt[i] - pos[i]) * frac for i in range(3))
        return base_camera.moved(dpos=delta)
    if move == "PAN_LEFT":
        return base_camera.moved(dtarget=(-1.5 * t, 0.0, 0.0))
    if move == "PAN_RIGHT":
        return base_camera.moved(dtarget=(1.5 * t, 0.0, 0.0))
    if move == "TILT_UP":
        return base_camera.moved(dtarget=(0.0, 1.0 * t, 0.0))
    if move == "TILT_DOWN":
        return base_camera.moved(dtarget=(0.0, -1.0 * t, 0.0))
    if move == "CRANE_UP":
        return base_camera.moved(dpos=(0.0, 1.2 * t, 0.0))
    if move == "CRANE_DOWN":
        return base_camera.moved(dpos=(0.0, -1.2 * t, 0.0))
    return base_camera


# ---------------------------------------------------------------------------
# Camera Director (Phase C / D2)
# ---------------------------------------------------------------------------
# A camera TRANSFORM is a flat 7-tuple of floats:
#   (pos_x, pos_y, pos_z, target_x, target_y, target_z, fov_deg)
# Flat, because CameraValidation.is_static compares transforms
# element-wise. The default mode is STATIC_ANCHORED: the camera is
# constant within a shot (within TRANSFORM_TOLERANCE) and framing
# changes by hard cut. Scripted modes are explicit capabilities:
# every movement traces to a CameraDirective with a non-empty
# source. Nothing here tracks a live joint.

#: CameraMode -> camera_at movement name (direction >= 0 variant).
_SCRIPTED_MOVEMENTS = {
    CameraMode.SCRIPTED_PAN: "PAN_RIGHT",
    CameraMode.SCRIPTED_DOLLY: "DOLLY_IN",
    CameraMode.SCRIPTED_TRACKING: "TRACKING",
    CameraMode.SCRIPTED_REVEAL: "CRANE_UP",
    CameraMode.SCRIPTED_SHAKE: "HANDHELD",
}

#: Shot types whose framing is anchored on the head (eyeline checks).
_HEAD_FRAMING_TYPES = (
    "close_up", "extreme_close_up", "reaction",
    "shot_reverse_shot", "medium_close_up",
)


def camera_transform(camera):
    """Flat 7-tuple transform of a PerspectiveCamera."""
    return (tuple(float(v) for v in camera.position)
            + tuple(float(v) for v in camera.target)
            + (float(camera.fov_deg),))


def orientation_basis(camera):
    """(right, up, fwd) unit vectors — the camera orientation.

    9-tuple of floats, recomputed from position/target/up (no
    private access): fwd looks from the position at the target,
    right is fwd x up, up is right x fwd."""
    def _sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def _cross(a, b):
        return (a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0])

    def _norm(a):
        n = math.sqrt(sum(v * v for v in a))
        if n == 0:
            raise ValueError("zero-length vector has no direction")
        return tuple(v / n for v in a)

    fwd = _norm(_sub(camera.target, camera.position))
    right = _norm(_cross(fwd, camera.up))
    return right + _cross(right, fwd) + fwd


def projection_matrix(camera):
    """16-tuple row-major perspective matrix for the camera.

    Convention (the renderer25d convention): view space is
    +Z-forward (view depth is positive in FRONT of the camera),
    NDC depth runs [0, 1] (0 at ``near``, 1 at ``far``), and the
    matrix applies as ``(M @ [x, y, z, 1]) / w`` with ``w`` equal
    to the view-space depth. x/y NDC are +/-1 at the frustum
    edges. The matrix is derived from fov/aspect/near/far only.
    """
    tan_half = math.tan(math.radians(camera.fov_deg) / 2.0)
    aspect = float(camera.aspect)
    near = float(camera.near)
    far = float(camera.far)
    a = far / (far - near)
    b = -near * far / (far - near)
    return (1.0 / (tan_half * aspect), 0.0, 0.0, 0.0,
            0.0, 1.0 / tan_half, 0.0, 0.0,
            0.0, 0.0, a, b,
            0.0, 0.0, 1.0, 0.0)


def directive_for_shot(mode, start_camera, end_camera, duration_s,
                       source, anchor="scene"):
    """Build a CameraDirective from two cameras. Loud on an empty
    source and on a STATIC_ANCHORED start/end mismatch (the
    contract enforces both) — a directive that cannot be traced
    or that moves while claiming to be static is refused, never
    silently repaired."""
    if isinstance(mode, str):
        mode = CameraMode(mode)
    return CameraDirective(
        mode=mode, anchor=anchor, source=source,
        start_transform=camera_transform(start_camera),
        end_transform=camera_transform(end_camera),
        duration_s=float(duration_s))


def static_directive_for_shot(shot_id, camera, duration_s,
                              anchor="scene", source=None):
    """A STATIC_ANCHORED directive: start == end, always.

    Default source ``planner:static:<shot_id>`` keeps the static
    default traceable without the caller inventing an id."""
    return CameraDirective(
        mode=CameraMode.STATIC_ANCHORED, anchor=anchor,
        source=source or f"planner:static:{shot_id}",
        start_transform=camera_transform(camera),
        end_transform=camera_transform(camera),
        duration_s=float(duration_s))


def scripted_transforms(mode, base_camera, direction=1):
    """(start_camera, end_camera) for a scripted mode.

    The movement geometry is :func:`camera_at` evaluated at
    t=0 and t=1, so the directive's endpoints are exactly the
    path the renderer would execute. ``direction`` flips PAN
    (left/right) and DOLLY (in/out) and sets the TRACKING sign.
    Raises ValueError for STATIC_ANCHORED (use
    :func:`static_directive_for_shot`) and unknown modes."""
    if isinstance(mode, str):
        mode = CameraMode(mode)
    if mode is CameraMode.STATIC_ANCHORED:
        raise ValueError("STATIC_ANCHORED has no scripted path; use "
                         "static_directive_for_shot")
    movement = _SCRIPTED_MOVEMENTS.get(mode)
    if movement is None:
        raise ValueError(f"no scripted path for camera mode {mode!r}")
    if float(direction) < 0:
        if movement == "PAN_RIGHT":
            movement = "PAN_LEFT"
        elif movement == "DOLLY_IN":
            movement = "DOLLY_OUT"
    start = camera_at(movement, 0.0, base_camera,
                      direction=direction)
    end = camera_at(movement, 1.0, base_camera,
                    direction=direction)
    return start, end


def scripted_directive_for_shot(shot_id, mode, base_camera,
                                duration_s, source, anchor="scene",
                                direction=1):
    """A scripted CameraDirective with endpoints from
    :func:`scripted_transforms`. ``source`` is required and must
    be non-empty: an untraced movement is refused. The directive
    records the INTENT; executing within-shot movement is the
    renderer's job (ATLAS-owned spec — the current product
    renderer executes STATIC and records the limitation)."""
    start, end = scripted_transforms(mode, base_camera,
                                     direction=direction)
    if isinstance(mode, str):
        mode = CameraMode(mode)
    return CameraDirective(
        mode=mode, anchor=anchor, source=source,
        start_transform=camera_transform(start),
        end_transform=camera_transform(end),
        duration_s=float(duration_s))


def validation_for_camera(camera, crop_rect=None, anchor="scene",
                          start_transform=None, end_transform=None):
    """CameraValidation for a camera + optional frozen crop.

    ``crop_rect`` is the frozen (left, top, right, bottom) crop
    from :func:`crop_rect_for`, or None for a full-frame shot.
    ``start_transform``/``end_transform`` default to the camera's
    own transform (a static shot); pass the directive endpoints
    for a scripted shot so ``is_static()`` reports honestly."""
    transform = camera_transform(camera)
    return CameraValidation(
        position=tuple(float(v) for v in camera.position),
        orientation=orientation_basis(camera),
        projection_matrix=projection_matrix(camera),
        fov_deg=float(camera.fov_deg),
        crop_rect=(tuple(int(v) for v in crop_rect)
                   if crop_rect is not None else None),
        target_anchor=anchor,
        start_transform=(start_transform if start_transform is not None
                         else transform),
        end_transform=(end_transform if end_transform is not None
                       else transform))


def validate_shot_camera_static(transforms, tol=TRANSFORM_TOLERANCE):
    """(ok, max_delta, issues): is a per-frame transform series
    constant within tolerance? ``transforms`` is a list of flat
    7-tuples from :func:`camera_transform` (one per sampled
    frame). ``max_delta`` is the largest absolute component
    difference from the first transform. Empty input is an
    error, never a pass."""
    issues = []
    if not transforms:
        return False, float("inf"), ["no camera transforms sampled"]
    base = transforms[0]
    max_delta = 0.0
    for i, transform in enumerate(transforms):
        if len(transform) != len(base):
            issues.append(f"frame {i}: transform length "
                          f"{len(transform)} != {len(base)}")
            continue
        for a, b in zip(base, transform):
            max_delta = max(max_delta, abs(a - b))
    if max_delta > tol:
        issues.append(f"camera moved within shot: max transform "
                      f"delta {max_delta:.6g} > tolerance {tol:.6g}")
    return (not issues), max_delta, issues


def crop_rect_for(scale, focus_xy, frame_w, frame_h):
    """Integer (left, top, right, bottom) crop rect — the EXACT
    rect :func:`CameraPlanner.apply_camera` crops for the same
    scale + focus, so a frozen crop and the applied crop can
    never disagree."""
    scale = max(1.0, float(scale))
    cw, ch = frame_w / scale, frame_h / scale
    cx, cy = focus_xy
    left = min(max(cx - cw / 2.0, 0.0), frame_w - cw)
    top = min(max(cy - ch / 2.0, 0.0), frame_h - ch)
    return (int(round(left)), int(round(top)),
            int(round(left + cw)), int(round(top + ch)))


def anchor_focus_for_shot(shot, standing_subjects, others=None,
                          frame_w=1920, frame_h=1080, max_scale=None):
    """Freeze ONE crop for a shot from STANDING boxes (Phase C).

    ``standing_subjects`` / ``others`` are {"cx", "head_y",
    "foot_y", "half_w"} dicts in full-frame coords measured from
    the STANDING pose — pose-independent by construction (the
    standing extent does not change when a character kneels,
    bends or turns). The returned (safe_shot, safe_focus, notes,
    frozen_crop) must be computed ONCE per shot, before the
    frame loop, and the frozen crop applied to every frame.

    The anchor focus comes from the standing boxes: the primary
    subject's standing head position for head framings, the
    standing body centre otherwise — never a live joint.
    ``max_scale`` defaults to the F2 cap (1.0) for full-body
    shot types. ``frozen_crop`` is
    {scale, focus, crop_rect, frame_size, frozen: True,
    anchor: "standing_box", shot_type}; it is JSON-safe.
    """
    shot = dict(shot or {})
    shot_type = shot.get("shot_type", "medium")
    subjects = list(standing_subjects or [])
    if subjects:
        primary = subjects[0]
        if shot_type in _HEAD_FRAMING_TYPES:
            focus = (float(primary["cx"]), float(primary["head_y"]))
        else:
            focus = (float(primary["cx"]),
                     (float(primary["head_y"])
                      + float(primary["foot_y"])) / 2.0)
    else:
        focus = (frame_w / 2.0, frame_h / 2.0)
    if max_scale is None and shot_type in FULL_BODY_SHOT_TYPES:
        max_scale = 1.0
    safe_shot, safe_focus, notes = CameraPlanner.safe_frame(
        shot, focus, subjects, list(others or []), frame_w, frame_h,
        max_scale=max_scale)
    scale = float(safe_shot.get("camera", {}).get("scale")
                  or SHOT_SCALE.get(shot_type, 1.6))
    frozen_crop = {
        "scale": scale,
        "focus": [float(safe_focus[0]), float(safe_focus[1])],
        "crop_rect": list(crop_rect_for(scale, safe_focus,
                                        frame_w, frame_h)),
        "frame_size": [int(frame_w), int(frame_h)],
        "frozen": True,
        "anchor": "standing_box",
        "shot_type": shot_type,
    }
    return safe_shot, safe_focus, notes, frozen_crop


def apply_camera_anchored(img, frozen_crop):
    """Apply a frozen crop (from :func:`anchor_focus_for_shot`) to
    a frame: crop the recorded rect, resize to the input size
    with LANCZOS. The rect is taken as recorded — it is never
    recomputed from a live focus. Raises ValueError when the
    image size does not match the frozen frame size (a frozen
    crop for one frame size applied to another would silently
    reframe the shot)."""
    rect = frozen_crop["crop_rect"]
    size = frozen_crop.get("frame_size")
    if size is not None and tuple(size) != tuple(img.size):
        raise ValueError(
            f"frozen crop frame size {tuple(size)} != image size "
            f"{tuple(img.size)}")
    box = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
    return img.crop(box).resize(img.size, Image.LANCZOS)


def validate_composition(shot, focus_xy, subjects, others=None,
                         frame_w=1920, frame_h=1080,
                         movement_direction=None):
    """Composition issues for ONE frozen framing (Phase C).

    Builds on :func:`CameraPlanner.validate_framing` (subject
    survival in the crop) and adds, per shot type:

    * tracking + ``movement_direction`` ("left"/"right" or -1/1):
      lead room — at least 15% of the crop width must lie ahead
      of the subject in the direction of movement;
    * head framings: eyeline — the subject's head must sit in
      the upper part of the crop (relative head_y in [0.05,
      0.45] of the crop height), never centred or cut;
    * object_insert: the object centre must sit within 15% of
      the crop centre on both axes.

    ``subjects``/``others`` are standing boxes. Returns a list
    of issue strings (empty = clean). ``others`` half-cut by
    the crop is an issue here too (safe_frame fixes it; this
    validator reports it)."""
    issues, _corrected = CameraPlanner.validate_framing(
        shot, focus_xy, subjects, frame_w, frame_h)
    issues = list(issues)
    shot_type = (shot or {}).get("shot_type", "medium")
    scale = float((shot or {}).get("camera", {}).get("scale")
                  or SHOT_SCALE.get(shot_type, 1.6))
    scale = max(1.0, scale)
    left, top, right, bottom = _crop_rect(scale, focus_xy,
                                          frame_w, frame_h)
    cw, ch = right - left, bottom - top
    subjects = list(subjects or [])
    if (shot_type == "tracking" and movement_direction is not None
            and subjects):
        direction = movement_direction
        if isinstance(direction, str):
            direction = -1 if direction.strip().lower().startswith(
                "left") else 1
        for i, s in enumerate(subjects):
            ahead = ((right - (s["cx"] + s["half_w"])) if direction > 0
                     else ((s["cx"] - s["half_w"]) - left))
            if ahead < 0.15 * cw:
                issues.append(
                    f"subject {i}: lead room {ahead:.0f}px ahead "
                    f"of movement < 15% of crop width ({0.15 * cw:.0f}px)")
    if shot_type in _HEAD_FRAMING_TYPES and subjects:
        for i, s in enumerate(subjects):
            rel_y = (s["head_y"] - top) / ch if ch else 0.0
            if rel_y < 0.05 or rel_y > 0.45:
                issues.append(
                    f"subject {i}: eyeline head_y at {rel_y:.2f} of "
                    f"crop height (expected 0.05-0.45)")
    if shot_type == "object_insert" and subjects:
        for i, s in enumerate(subjects):
            cy = (s["head_y"] + s["foot_y"]) / 2.0
            if abs(s["cx"] - (left + cw / 2.0)) > 0.15 * cw:
                issues.append(
                    f"subject {i}: object off-centre horizontally "
                    f"(cx={s['cx']:.0f}, crop centre "
                    f"{left + cw / 2.0:.0f})")
            if abs(cy - (top + ch / 2.0)) > 0.15 * ch:
                issues.append(
                    f"subject {i}: object off-centre vertically "
                    f"(cy={cy:.0f}, crop centre "
                    f"{top + ch / 2.0:.0f})")
    for j, other in enumerate(others or []):
        status = _other_status(other, (left, top, right, bottom))
        if status == "partial":
            issues.append(f"other {j}: half-cut by the crop "
                          f"(must be fully in or fully out)")
    return issues


def validate_camera_sequence(entries):
    """Sequence-level camera validation (Phase C).

    ``entries`` are :func:`plan_shot` outputs in render order.
    Checks:

    * 180-degree rule: a screen-direction flip (LTR<->RTL) is an
      issue unless the crossing shot is an SRS/OTS pair member
      or an establishing/graphic_insert reset;
    * SRS eyeline match: consecutive shot_reverse_shot entries
      must come from viewpoints at least 30 deg apart in azimuth
      (a real reverse angle, not the same angle twice) with
      elevations matching within 2 deg;
    * repeated framing: consecutive entries with the same
      viewpoint (azimuth/elevation/radius within the plan_shot
      tolerances) are one angle, not two;
    * F2: full-body entries must carry crop_scale <= 1.0.

    Returns {"issues": [{shot_id, rule, message}], "checked": n,
    "ok": bool}."""
    issues = []
    entries = list(entries or [])

    def _add(entry, rule, message):
        issues.append({"shot_id": entry.get("shot_id", "UNKNOWN"),
                       "rule": rule, "message": message})

    prev = None
    for entry in entries:
        shot_type = entry.get("shot_type_resolved")
        crop_scale = (entry.get("framing") or {}).get("crop_scale")
        if (shot_type in FULL_BODY_SHOT_TYPES
                and crop_scale is not None and crop_scale > 1.0):
            _add(entry, "F2",
                 f"full-body shot {shot_type} carries crop_scale "
                 f"{crop_scale} > 1.0")
        if prev is not None:
            prev_dir = prev.get("screen_direction")
            direction = entry.get("screen_direction")
            if (prev_dir in ("LTR", "RTL")
                    and direction in ("LTR", "RTL")
                    and prev_dir != direction
                    and shot_type not in ("shot_reverse_shot",
                                          "over_the_shoulder",
                                          "establishing",
                                          "graphic_insert")):
                _add(entry, "180_degree",
                     f"screen direction flipped {prev_dir}->{direction} "
                     f"without an SRS/OTS pair or establishing reset")
            prev_pose = prev.get("pose") or {}
            pose = entry.get("pose") or {}
            if (abs(prev_pose.get("azimuth_deg", 0.0)
                    - pose.get("azimuth_deg", 0.0)) < 0.5
                    and abs(prev_pose.get("elevation_deg", 0.0)
                            - pose.get("elevation_deg", 0.0)) < 0.5
                    and abs(prev_pose.get("radius", 0.0)
                            - pose.get("radius", 0.0)) < 0.05):
                _add(entry, "repeated_framing",
                     "same viewpoint as previous shot: repeated "
                     "framing, not a new angle")
            if (shot_type == "shot_reverse_shot"
                    and prev.get("shot_type_resolved")
                    == "shot_reverse_shot"):
                az_diff = abs(pose.get("azimuth_deg", 0.0)
                              - prev_pose.get("azimuth_deg", 0.0))
                el_diff = abs(pose.get("elevation_deg", 0.0)
                              - prev_pose.get("elevation_deg", 0.0))
                if az_diff < 30.0:
                    _add(entry, "srs_eyeline",
                         f"SRS pair azimuths {az_diff:.1f} deg apart "
                         f"(< 30 deg): not a reverse angle")
                if el_diff > 2.0:
                    _add(entry, "srs_eyeline",
                         f"SRS pair elevations differ by {el_diff:.1f} "
                         f"deg (> 2 deg): eyelines do not match")
        prev = entry
    return {"issues": issues, "checked": len(entries),
            "ok": not issues}


# size label per shot type
_SIZE_BY_SHOT = {
    "establishing": "wide",
    "medium": "medium",
    "close_up": "close_up",
    "extreme_close_up": "extreme_close_up",
    "over_the_shoulder": "medium",
    "reaction": "close_up",
    "object_insert": "close_up",
    "tracking": "medium",
    "shot_reverse_shot": "medium",
}

# default move per shot type; action/emotion can override it below
_MOVE_BY_SHOT = {
    "establishing": "dolly_in",
    "medium": "static",
    "close_up": "dolly_in",
    "extreme_close_up": "static",
    "over_the_shoulder": "static",
    "reaction": "static",
    "object_insert": "tilt",
    "tracking": "tracking",
    "shot_reverse_shot": "static",
}

_CUE_EMOTION_MAP = (
    (("relief", "smile", "laugh", "happy", "joy", "nod"), "relief"),
    (("surprise", "surprised"), "surprise"),
    (("cry", "sad"), "sadness"),
    (("fear", "worried", "scared"), "fear"),
    (("emotion",), "tension"),
)

# lighting presets by time of day / mood — generic, from the scene
# package, not from any story.
_LIGHTING_PRESETS = {
    ("night", "cold"): {"key": "cool_moon", "fill": "warm_lamp",
                        "source": "street lamp + moonlight",
                        "mood": "cold night, warm pools of lamp light"},
    ("night", "warm"): {"key": "warm_lamp", "fill": "cool_moon",
                        "source": "street lamp",
                        "mood": "warm night, soft shadows"},
    ("day", "cold"): {"key": "overcast_sun", "fill": "cool_sky",
                      "source": "overcast daylight",
                      "mood": "flat cool daylight"},
    ("day", "warm"): {"key": "warm_sun", "fill": "cool_sky",
                      "source": "low warm sun",
                      "mood": "warm daylight, long shadows"},
    ("interior", "warm"): {"key": "warm_lamp", "fill": "soft_window",
                           "source": "lamps + window light",
                           "mood": "warm interior"},
    ("interior", "cold"): {"key": "cool_window", "fill": "warm_lamp",
                           "source": "window light",
                           "mood": "cool interior"},
}

# Default camera for camera_path (world units; matches renderer25d).
_DEFAULT_CAM_POS = (0.0, 2.4, 12.0)
_DEFAULT_CAM_TARGET = (0.0, 1.5, 0.0)


def _emotion_for_segment(segment):
    cues = _norm_cues(segment.get("action_cues"))
    for keywords, emotion in _CUE_EMOTION_MAP:
        if _has(cues, keywords):
            return emotion
    return "neutral"


def _attention_for(shot, segment):
    focus = shot.get("focus_target", "")
    subject = shot.get("subject", "speaker")
    if focus == "object":
        return {"target": "object", "why": "the object is what the line "
                "is about — the audience must see it, not the speaker"}
    if focus == "subject_head":
        return {"target": subject, "why": "the face carries the beat — "
                "emotion is read from the eyes, not the words"}
    if focus == "two_shot_center":
        return {"target": "two_shot", "why": "the space between the two "
                "characters is the story of this shot"}
    return {"target": subject, "why": "the speaking character in their "
            "environment"}


def _positions_for(shot, scene_package):
    """Generic staging positions, by role (speaker/receiver/object/
    scene), never by character name. If the scene package gives world
    positions for its characters, they are passed through as anchors."""
    subject = shot.get("subject", "speaker")
    shot_type = shot.get("shot_type", "medium")
    positions = {}
    if subject in ("two_shot", "receiver"):
        positions = {"speaker": "left_third", "receiver": "right_third",
                     "gap": "visible space between them"}
    elif subject == "object":
        positions = {"object": "centre_frame", "speaker": "soft_background"}
    elif subject == "scene":
        positions = {"scene": "full_frame"}
    else:
        positions = {subject: "rule_of_thirds_side"}
    pkg_chars = (scene_package or {}).get("characters") or []
    anchors = {}
    for ch in pkg_chars:
        if isinstance(ch, dict) and "world_pos" in ch:
            anchors[ch.get("role", ch.get("name", "character"))] = \
                ch["world_pos"]
    if anchors:
        positions["world_anchors"] = anchors
    if shot_type in ("close_up", "reaction", "extreme_close_up"):
        positions["headroom"] = "small"
    return positions


def _lighting_for(scene_package):
    pkg = scene_package or {}
    time_of_day = str(pkg.get("time_of_day", "day")).lower()
    mood = str(pkg.get("mood", "warm")).lower()
    preset = _LIGHTING_PRESETS.get((time_of_day, mood))
    if preset is None:
        preset = _LIGHTING_PRESETS.get(("day", mood)
                                       ) or _LIGHTING_PRESETS[("day", "warm")]
    out = dict(preset)
    if pkg.get("weather"):
        out["weather"] = str(pkg["weather"])
    return out


def _camera_path_for(move, shot):
    """from/to camera position+target for the move, in world units.

    Dolly-in moves the camera 15% closer along its forward axis;
    tracking slides it sideways 1.5 units; crane rises 1.2 units;
    arc orbits 1.5 units sideways while keeping the same target.
    Static / pan / tilt keep the position and move only the target.
    """
    pos = list(_DEFAULT_CAM_POS)
    tgt = list(_DEFAULT_CAM_TARGET)
    to_pos, to_tgt = list(pos), list(tgt)
    if move == "dolly_in":
        for i in range(3):
            to_pos[i] = pos[i] + (tgt[i] - pos[i]) * 0.15
    elif move == "dolly_out":
        for i in range(3):
            to_pos[i] = pos[i] - (tgt[i] - pos[i]) * 0.15
    elif move in ("tracking", "arc"):
        to_pos[0] += 1.5
        to_tgt[0] += 1.5
    elif move == "crane_up":
        to_pos[1] += 1.2
    elif move == "pan":
        to_tgt[0] += 2.0
    elif move == "tilt":
        to_tgt[1] += 1.0
    return {"move": move, "from": {"position": pos, "target": tgt},
            "to": {"position": to_pos, "target": to_tgt}}


def _cut_point_for(shot, segment):
    """When to cut, and why — the cut is motivated, not arbitrary."""
    purpose = (shot.get("narrative_purpose") or "").lower()
    cues = _norm_cues(segment.get("action_cues"))
    if "exchange" in purpose or "changes hands" in purpose:
        return {"at": "action_peak",
                "reason": "cut the instant the object changes hands"}
    if "reaction" in purpose or "emotional beat" in purpose:
        return {"at": "reaction_beat",
                "reason": "cut after the face has registered the emotion"}
    if _has(cues, _CUE_MOVE):
        return {"at": "action_peak",
                "reason": "cut mid-movement, on the strongest stride"}
    if _has(cues, _CUE_PICK):
        return {"at": "action_peak",
                "reason": "cut as the hand closes on the object"}
    if "reveal" in purpose or "twist" in purpose:
        return {"at": "reaction_beat",
                "reason": "hold, then cut on the reveal landing"}
    return {"at": "line_end",
            "reason": "cut at the end of the spoken line"}


class ShotDirector:
    """Direct planned shots: staging, light, camera move, cut point.

    ``direct(segments, scene_package)`` returns the SAME shots
    ``CameraPlanner.plan()`` returns (same count, same durations,
    same order), each enriched with a ``direction`` dict of 9 keys.
    ``validate_direction()`` checks the contract; a shot without a
    complete direction is not directable and must not render.
    """

    @staticmethod
    def direct(segments, scene_package=None):
        shots = CameraPlanner.plan(segments)
        for shot, seg in zip(shots, _segments_per_shot(segments, shots)):
            shot_type = shot.get("shot_type", "medium")
            emotion = _emotion_for_segment(seg)
            move = _MOVE_BY_SHOT.get(shot_type, "static")
            cues = _norm_cues(seg.get("action_cues"))
            if _has(cues, _CUE_MOVE) and shot_type in ("medium", "tracking"):
                move = "tracking"
            if emotion in ("surprise", "fear") and shot_type == "reaction":
                move = "dolly_in"  # push in on the shock
            shot["direction"] = {
                "attention_target": _attention_for(shot, seg),
                "main_action": (cues[0] if cues else
                                ("speaking" if seg.get("speaker") else
                                 "narration")),
                "emotion": emotion,
                "angle": _ANGLE_BY_SHOT.get(shot_type, "eye_level"),
                "shot_size": _SIZE_BY_SHOT.get(shot_type, "medium"),
                "character_positions": _positions_for(shot, scene_package),
                "lighting": _lighting_for(scene_package),
                "camera_move": _camera_path_for(move, shot),
                "cut_point": _cut_point_for(shot, seg),
            }
        return shots

    @staticmethod
    def validate_direction(shots):
        """Check every shot carries a complete, in-vocabulary direction.
        Returns a list of problems (empty = all directable)."""
        problems = []
        required = ("attention_target", "main_action", "emotion", "angle",
                    "shot_size", "character_positions", "lighting",
                    "camera_move", "cut_point")
        for i, shot in enumerate(shots or []):
            d = shot.get("direction")
            if not isinstance(d, dict):
                problems.append(f"shot {i}: no direction")
                continue
            for key in required:
                if key not in d:
                    problems.append(f"shot {i}: missing direction.{key}")
            if d.get("angle") not in ANGLES:
                problems.append(f"shot {i}: bad angle {d.get('angle')!r}")
            if d.get("emotion") not in EMOTIONS:
                problems.append(f"shot {i}: bad emotion {d.get('emotion')!r}")
            move = (d.get("camera_move") or {}).get("move")
            if move not in CAMERA_MOVES:
                problems.append(f"shot {i}: bad camera move {move!r}")
            if d.get("shot_size") not in set(_SIZE_BY_SHOT.values()):
                problems.append(f"shot {i}: bad size {d.get('shot_size')!r}")
            if (d.get("cut_point") or {}).get("at") not in (
                    "action_peak", "reaction_beat", "line_end"):
                problems.append(f"shot {i}: bad cut point "
                                f"{(d.get('cut_point') or {}).get('at')!r}")
        return problems


def _segments_per_shot(segments, shots):
    """Map each planned shot back to its source segment (shots keep
    their segment order, so a per-segment shot count walk suffices)."""
    per_seg = []
    for seg in segments or []:
        n = len(_shots_for_segment(seg))
        per_seg.extend([seg] * n)
    return per_seg[:len(shots)]


def direct(segments, scene_package=None):
    return ShotDirector.direct(segments, scene_package)


def validate_direction(shots):
    return ShotDirector.validate_direction(shots)


# ---------------------------------------------------------------------------
# Shot composition (Visual Quality Recovery, P6) — directive accounting.
#
# Every original SHOT directive must map to exactly one rendered
# camera pose, traceably. ``plan_shot`` resolves a directive dict
# (the adapter's ``shot_directives`` shape: shot_id, shot_type,
# camera_angle, camera_movement, camera, location_override, subject,
# counterpart, srs_side, trigger) to a REAL viewpoint via
# viewpoint_for_shot() plus a framing + accounting record.
# ``plan_coverage`` maps a whole directive list: 100% accounting —
# every directive yields exactly one entry, and anything unmapped
# or overridden is recorded in the entry, never silently dropped.
#
# Locked rules (Mai's verdict 2026-11-12 + channel study R9):
#   * camera FIXED within a shot; viewpoint changes BY CUT only;
#   * no zoom-as-angle: the pose comes from viewpoint geometry,
#     never from a crop scale;
#   * F2 standing-box rule: full-body shot types report a capped
#     crop scale of 1.0, and all non-establishing poses share the
#     same camera radius (same distance -> same head size);
#   * CAMERA_MOVEMENT requests are NOT executed within a shot;
#     the override is documented in every affected entry
#     (``movement_decision``) instead of being silently applied
#     as a crop path.
# ``frame_range`` is filled by ATLAS at render time from the
# timeline; the planner records None + the note, never a guess.
# ---------------------------------------------------------------------------
def _pose_angles(camera):
    """(azimuth_deg, elevation_deg, radius) of a camera vs its target."""
    ox = camera.position[0] - camera.target[0]
    oy = camera.position[1] - camera.target[1]
    oz = camera.position[2] - camera.target[2]
    radius = math.sqrt(ox * ox + oy * oy + oz * oz)
    if radius == 0:
        return (0.0, 0.0, 0.0)
    return (math.degrees(math.atan2(ox, oz)),
            math.degrees(math.asin(max(-1.0, min(1.0, oy / radius)))),
            radius)


def _staging_for(shot, scene):
    """(subject_pos, counterpart_x) from scene staging data.

    ``scene`` may carry ``character_positions`` {name: (x, y, z)}
    (feet positions) or ``subject_pos`` / ``counterpart_x``
    directly. Defaults: subject at (0, 1.2, 0) (eye height on the
    subject plane), no counterpart. Never raises."""
    scene = scene or {}
    subject = shot.get("subject") or ""
    counterpart = shot.get("counterpart")
    positions = scene.get("character_positions") or {}
    subject_pos = scene.get("subject_pos")
    if subject_pos is None and subject and subject in positions:
        feet = positions[subject]
        subject_pos = (float(feet[0]), float(feet[1]) + 1.2,
                       float(feet[2]))
    if subject_pos is None:
        subject_pos = (0.0, 1.2, 0.0)
    counterpart_x = scene.get("counterpart_x")
    if counterpart_x is None and counterpart and counterpart in positions:
        counterpart_x = float(positions[counterpart][0])
    return (tuple(float(v) for v in subject_pos), counterpart_x)


def plan_shot(directive, scene=None, prev_entry=None, camera_mode=None,
              camera_source=None):
    """Resolve ONE shot directive to a camera pose + accounting entry.

    Returns a dict with: shot_id, directive (echo), shot_type_resolved,
    camera_position, target, fov, pose {angle, azimuth_deg,
    elevation_deg, radius}, framing {shot_type, crop_scale (F2-capped),
    focus, composition_rules}, subject, counterpart, location_override,
    screen_direction, movement_decision, frame_range (None: filled by
    ATLAS at render), continuity_notes, errors. Never raises on
    directive data: unknown types degrade to "medium" WITH an error
    recorded.

    Phase C opt-in: ``camera_mode`` (a CameraMode or its value
    string) + ``camera_source`` (a non-empty traceable id) record
    the shot's camera directive + validation as JSON-safe dicts
    (``camera_directive``, ``camera_validation``) on the entry.
    With ``camera_mode=None`` (default) the entry is EXACTLY as
    before — the static default needs no opt-in. A scripted mode
    WITHOUT a source records an error and falls back to STATIC
    (plan_shot never raises on directive data); the directive
    dicts carry ``duration_s: None`` (filled at render from the
    timeline — the planner must not invent a duration)."""
    shot = dict(directive or {})
    errors = []
    shot_id = shot.get("shot_id") or "UNKNOWN"
    if not shot.get("shot_id"):
        errors.append("directive without shot_id")
    raw_type = str(shot.get("shot_type", "") or "").strip().lower()
    if raw_type in SHOT_TYPES:
        shot_type = raw_type
    else:
        shot_type = "medium"
        errors.append(f"unknown shot_type {raw_type!r}; resolved to medium")
    angle = resolve_viewpoint_angle(shot_type, shot.get("camera_angle"))
    subject_pos, counterpart_x = _staging_for(shot, scene)
    srs_side = shot.get("srs_side")
    try:
        srs_side = int(srs_side) if srs_side is not None else 0
    except (TypeError, ValueError):
        srs_side = 0
    camera = viewpoint_for_shot(
        shot_type, shot.get("camera_angle"), subject_pos,
        counterpart_x=counterpart_x, srs_side=srs_side)
    azimuth, elevation, radius = _pose_angles(camera)
    crop_scale = SHOT_SCALE.get(shot_type, 1.6)
    if shot_type in FULL_BODY_SHOT_TYPES:
        crop_scale = min(crop_scale, 1.0)  # F2 standing-box cap
    requested_move = normalize_movement(shot.get("camera_movement"))
    if requested_move == "STATIC":
        movement_decision = {
            "requested": requested_move, "executed": "STATIC",
            "documented": True,
            "reason": "STATIC as requested; camera fixed within shot"}
    else:
        movement_decision = {
            "requested": requested_move, "executed": "STATIC",
            "documented": True,
            "reason": ("within-shot movement is not executed: camera "
                       "fixed within a shot, framing changes by hard "
                       "cut (Mai verdict 2026-11-12; channel study R9). "
                       "camera_at() geometry kept for preview only.")}
    # Phase C: explicit camera directive (opt-in; default unchanged).
    camera_directive = None
    camera_validation = None
    if camera_mode is not None:
        try:
            mode = (camera_mode if isinstance(camera_mode, CameraMode)
                    else CameraMode(str(camera_mode)))
        except ValueError:
            errors.append(f"unknown camera_mode {camera_mode!r}; "
                          f"fell back to STATIC")
            mode = None
        if mode is not None:
            start_transform = camera_transform(camera)
            if mode is CameraMode.STATIC_ANCHORED:
                end_transform = start_transform
                source = (camera_source
                          or f"planner:static:{shot_id}")
            elif not camera_source:
                errors.append(
                    f"scripted camera mode {mode.value} requires a "
                    f"non-empty camera_source; fell back to STATIC")
                mode = None
                end_transform = start_transform
            else:
                _start, end_camera = scripted_transforms(
                    mode, camera)
                end_transform = camera_transform(end_camera)
                source = camera_source
                movement_decision = {
                    "requested": requested_move,
                    "executed": mode.value,
                    "documented": True,
                    "reason": ("scripted movement recorded by explicit "
                               f"directive (source: {source}); renderer "
                               "execution is ATLAS-owned — the current "
                               "product renderer executes STATIC and "
                               "records the limitation."),
                    "source": source}
            if mode is not None:
                camera_directive = {
                    "mode": mode.value, "anchor": "scene",
                    "source": source,
                    "start_transform": list(start_transform),
                    "end_transform": list(end_transform),
                    "duration_s": None,
                    "duration_note": ("filled at render from the "
                                      "timeline"),
                }
                validation = validation_for_camera(
                    camera, crop_rect=None, anchor="scene",
                    start_transform=start_transform,
                    end_transform=end_transform)
                camera_validation = {
                    "position": list(validation.position),
                    "orientation": list(validation.orientation),
                    "projection_matrix":
                        list(validation.projection_matrix),
                    "fov_deg": validation.fov_deg,
                    "crop_rect": validation.crop_rect,
                    "target_anchor": validation.target_anchor,
                    "start_transform": list(validation.start_transform),
                    "end_transform": list(validation.end_transform),
                    "is_static": validation.is_static(),
                }
    subject = shot.get("subject") or ""
    counterpart = shot.get("counterpart")
    if counterpart_x is not None and subject_pos is not None:
        screen_direction = ("LTR" if subject_pos[0] <= counterpart_x
                            else "RTL")
    else:
        screen_direction = "centered"
    continuity_notes = []
    if prev_entry is not None:
        prev_dir = prev_entry.get("screen_direction")
        if (prev_dir in ("LTR", "RTL") and screen_direction in ("LTR", "RTL")
                and prev_dir != screen_direction):
            if shot_type in ("shot_reverse_shot", "over_the_shoulder"):
                continuity_notes.append(
                    "axis crossed by cut (SRS/OTS pair — expected)")
            else:
                continuity_notes.append(
                    "axis flip vs previous shot: check 180-degree rule")
        prev_pose = prev_entry.get("pose") or {}
        if (abs(prev_pose.get("azimuth_deg", 0.0) - azimuth) < 0.5
                and abs(prev_pose.get("elevation_deg", 0.0) - elevation)
                < 0.5 and abs(prev_pose.get("radius", 0.0) - radius) < 0.05):
            continuity_notes.append(
                "same viewpoint as previous shot: repeated framing, "
                "not a new angle (counts as one angle)")
    if shot.get("location_override"):
        continuity_notes.append(
            f"location override: {shot['location_override']}")
    if shot_type == "graphic_insert":
        continuity_notes.append("flat graphic insert: straight-on, "
                                "no camera")
    entry = {
        "shot_id": shot_id,
        "directive": {k: shot.get(k) for k in (
            "shot_type", "camera_angle", "camera_movement", "camera",
            "location_override", "subject", "counterpart", "srs_side",
            "trigger", "scene", "line_index")},
        "shot_type_resolved": shot_type,
        "camera_position": tuple(camera.position),
        "target": tuple(camera.target),
        "fov": camera.fov_deg,
        "pose": {"angle": angle, "azimuth_deg": round(azimuth, 2),
                 "elevation_deg": round(elevation, 2),
                 "radius": round(radius, 3)},
        "framing": {"shot_type": shot_type, "crop_scale": crop_scale,
                    "focus": SHOT_FOCUS.get(shot_type, "subject_full"),
                    "composition_rules": list(
                        COMPOSITION_RULES.get(shot_type, []))},
        "subject": subject,
        "counterpart": counterpart,
        "location_override": shot.get("location_override"),
        "screen_direction": screen_direction,
        "movement_decision": movement_decision,
        "frame_range": None,
        "frame_range_note": "filled by ATLAS at render from the timeline",
        "continuity_notes": continuity_notes,
        "errors": errors,
    }
    if camera_directive is not None:
        entry["camera_directive"] = camera_directive
        entry["camera_validation"] = camera_validation
    return entry


def plan_coverage(directives, scene=None):
    """Map EVERY directive to a pose: 100% accounting.

    Returns ``{entries, accounting}`` where ``accounting`` counts
    total/mapped/error entries and lists movement overrides and
    repeated-framing pairs. No directive is ever silently omitted:
    len(entries) == len(directives), always. Directives may carry
    ``camera_mode`` / ``camera_source`` keys, forwarded to
    :func:`plan_shot` (Phase C opt-in; absent = default static
    behaviour, unchanged)."""
    entries = []
    prev = None
    for directive in directives or []:
        entry = plan_shot(
            directive, scene=scene, prev_entry=prev,
            camera_mode=(directive or {}).get("camera_mode"),
            camera_source=(directive or {}).get("camera_source"))
        entries.append(entry)
        prev = entry
    error_entries = [e["shot_id"] for e in entries if e["errors"]]
    overrides = [e["shot_id"] for e in entries
                 if e["movement_decision"]["requested"] != "STATIC"]
    repeated = [e["shot_id"] for e in entries
                if any("same viewpoint" in n
                       for n in e["continuity_notes"])]
    return {
        "entries": entries,
        "accounting": {
            "total_directives": len(entries),
            "mapped": len(entries) - len(error_entries),
            "with_errors": error_entries,
            "movement_overrides": overrides,
            "repeated_framing": repeated,
            "all_mapped": len(error_entries) == 0,
        },
    }


def _jsonable(value):
    """Deep-convert tuples to lists so accounting is JSON-serializable."""
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def build_camera_accounting(directives, shots, staging=None, fps=24,
                            executed=None):
    """Join planned shot directives to rendered shots (P6 / W3).

    ``directives`` is the package's ``shot_directives`` list (every V1
    SHOT directive); ``shots`` is the ``plan_shots`` output in render
    order (each with ``duration`` and, when a directive drove it,
    ``directive_shot_id``). ``staging`` is the scene staging dict for
    ``plan_coverage`` (``character_positions``); ``executed`` is an
    optional {shot index: _render_shot return dict} map for the
    planned-vs-executed pose comparison.

    Frame ranges use the SAME cumulative clock as
    ``render_product_video`` (shot i covers
    [round(start*fps), round(end*fps))) so they index the rendered
    frame list exactly; the 0.5 s audio tail is not part of any shot.

    Every directive gets exactly one entry with a status:
    ``rendered`` (a shot carries its id and renders its resolved
    type), ``type_defaulted`` (a shot carries its id but renders a
    different type — the directive's type was invalid/absent), or
    ``not_rendered`` (no shot carries its id — e.g. only the first
    scene-level directive per scene drives action leads). Shots with
    no directive id are listed separately as ``synthesized_shots``
    (cue defaults / Gemini plan / end card). Nothing is silently
    omitted: len(entries) == len(directives), always.
    """
    coverage = plan_coverage(directives, scene=staging)
    # Cumulative-clock frame ranges over the shot list.
    ranges = []
    cursor = 0.0
    for shot in shots or []:
        start = round(cursor * fps)
        cursor += float(shot.get("duration") or 0.0)
        ranges.append([start, round(cursor * fps)])
    total_frames = ranges[-1][1] if ranges else 0
    by_directive = {}
    for idx, shot in enumerate(shots or []):
        did = shot.get("directive_shot_id")
        if did:
            by_directive.setdefault(str(did), []).append(idx)
    executed = executed or {}
    entries = []
    for entry in coverage["entries"]:
        shot_id = entry["shot_id"]
        indices = by_directive.get(str(shot_id), [])
        frame_ranges = [ranges[i] for i in indices]
        rendered_types = [shots[i].get("shot_type") for i in indices]
        if not indices:
            status = "not_rendered"
        elif entry["shot_type_resolved"] in rendered_types:
            status = "rendered"
        else:
            status = "type_defaulted"
        out = _jsonable(entry)
        out["frame_range"] = frame_ranges[0] if len(frame_ranges) == 1 \
            else frame_ranges
        out["frame_ranges"] = frame_ranges
        out["frame_range_note"] = (
            "cumulative clock over plan_shots durations; "
            "excludes the 0.5 s audio tail")
        out["shot_indices"] = indices
        out["rendered_shot_types"] = rendered_types
        out["status"] = status
        # Planned-vs-executed comparison (when render results given).
        exec_blocks = []
        for i in indices:
            result = executed.get(i)
            if not isinstance(result, dict):
                continue
            pos = result.get("camera_position")
            planned = entry.get("camera_position")
            delta = None
            if pos is not None and planned is not None:
                delta = round(math.dist(
                    [float(v) for v in pos],
                    [float(v) for v in planned]), 3)
            exec_blocks.append({
                "shot_index": i,
                "camera_position": _jsonable(pos),
                "camera_target": _jsonable(result.get("camera_target")),
                "camera_angle": result.get("camera_angle"),
                "camera_angle_requested": result.get(
                    "camera_angle_requested"),
                "camera_movement_executed": result.get(
                    "camera_movement_executed"),
                "camera_radius_scale": result.get("camera_radius_scale"),
                "camera_limitation": result.get("camera_limitation"),
                "position_delta_vs_plan": delta,
            })
        out["executed"] = exec_blocks
        entries.append(out)
    synthesized = []
    for idx, shot in enumerate(shots or []):
        if shot.get("directive_shot_id"):
            continue
        synthesized.append({
            "shot_index": idx,
            "scene": shot.get("scene"),
            "kind": shot.get("kind"),
            "shot_type": shot.get("shot_type"),
            "frame_range": ranges[idx],
            "source": ("end_card" if shot.get("kind") == "end_card"
                       else "cue_default_or_gemini_plan"),
        })
    summary = dict(coverage["accounting"])
    summary.update({
        "total_shots": len(shots or []),
        "total_frames_excluding_tail": total_frames,
        "rendered": sum(1 for e in entries if e["status"] == "rendered"),
        "type_defaulted": sum(
            1 for e in entries if e["status"] == "type_defaulted"),
        "not_rendered": [e["shot_id"] for e in entries
                         if e["status"] == "not_rendered"],
        "synthesized_shots": len(synthesized),
    })
    return {"entries": entries, "synthesized_shots": synthesized,
            "accounting": summary}


# ---------------------------------------------------------------------------
# Measurement functions for the independent camera audit (PIL only).
# ---------------------------------------------------------------------------
def _mad_between(img_a, img_b):
    """Mean absolute per-pixel difference (0..255) of two RGB frames."""
    from PIL import ImageChops
    if img_a.size != img_b.size:
        raise ValueError(f"frame sizes differ: {img_a.size} vs {img_b.size}")
    diff = ImageChops.difference(img_a.convert("RGB"),
                                 img_b.convert("RGB")).convert("L")
    hist = diff.histogram()
    total = sum(hist)
    if total == 0:
        return 0.0
    return sum(i * count for i, count in enumerate(hist)) / total


def sky_band_mad(img_a, img_b, band_h: int = 150) -> float:
    """MAD of the top ``band_h`` rows (the sky band).

    Within one fixed-camera shot the sky band must be ~0 (the
    camera does not move) while the lower frame changes (characters
    animate). The audit compares this against lower-frame MAD."""
    band_a = img_a.crop((0, 0, img_a.size[0], min(band_h, img_a.size[1])))
    band_b = img_b.crop((0, 0, img_b.size[0], min(band_h, img_b.size[1])))
    return _mad_between(band_a, band_b)


def frame_mad(img_a, img_b, region=None) -> float:
    """MAD of a region (default: whole frame). ``region`` is a
    (left, upper, right, lower) pixel box. Cut MAD between two
    shots' end/start frames must be large when the viewpoint
    actually changed, ~0 only for repeated framing."""
    if region is not None:
        img_a = img_a.crop(region)
        img_b = img_b.crop(region)
    return _mad_between(img_a, img_b)


def head_width_stability(head_boxes) -> dict:
    """Head-width stability across frames (the F2 check).

    ``head_boxes``: a list of (x0, x1) pixel pairs (or dicts with
    x0/x1) measuring the same subject's head width per frame.
    Returns widths, mean, max deviation in px and ratio, and
    ``ok`` (max ratio deviation <= 5%). No zoom pump = stable."""
    widths = []
    for box in head_boxes or []:
        if isinstance(box, dict):
            widths.append(float(box["x1"]) - float(box["x0"]))
        else:
            widths.append(float(box[1]) - float(box[0]))
    if not widths:
        return {"widths": [], "mean": 0.0, "max_deviation_px": 0.0,
                "max_deviation_ratio": 0.0, "ok": False, "n": 0}
    mean = sum(widths) / len(widths)
    max_dev = max(abs(w - mean) for w in widths)
    ratio = (max_dev / mean) if mean else 0.0
    return {"widths": [round(w, 2) for w in widths],
            "mean": round(mean, 2), "max_deviation_px": round(max_dev, 2),
            "max_deviation_ratio": round(ratio, 4),
            "ok": ratio <= 0.05, "n": len(widths)}
