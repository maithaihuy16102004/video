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
  establishing  1.0  (wide, whole frame)
  medium / tracking / over_the_shoulder / shot_reverse_shot  1.6
  close_up / reaction  2.6
  object_insert / extreme_close_up  3.4
"""
from __future__ import annotations

from PIL import Image

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
}

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
            new_left = min(max(need_l, need_r - cw), frame_w - cw)
            new_left = max(0.0, new_left)
            new_top = min(max(need_t, need_b - ch), frame_h - ch)
            new_top = max(0.0, new_top)
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
        Returns a new PIL Image (input untouched)."""
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
        # shift the crop so the required window fits inside it
        new_left = min(max(need_l, need_r - cw), frame_w - cw)
        new_left = max(0.0, new_left)
        new_top = min(max(need_t, need_b - ch), frame_h - ch)
        new_top = max(0.0, new_top)
        corrected = (new_left + cw / 2.0, new_top + ch / 2.0)
        return issues, corrected

    @staticmethod
    def safe_frame(shot, focus_xy, subjects, others=None, frame_w=1920,
                   frame_h=1080):
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
        """
        others = list(others or [])
        planned_scale = float((shot or {}).get("camera", {}).get("scale")
                              or SHOT_SCALE.get(
                                  (shot or {}).get("shot_type", "medium"),
                                  1.6))
        planned_scale = max(1.0, planned_scale)
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
               frame_h=1080):
    return CameraPlanner.safe_frame(shot, focus_xy, subjects, others,
                                    frame_w, frame_h)


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
}

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
