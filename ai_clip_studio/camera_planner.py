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
    is_narration = speaker in ("narrator", "narration", "") or not cues

    # Dialogue segments ("kind": "line"): characters are standing and
    # talking, so movement cues do NOT apply — the camera should frame
    # the speaker, the object being discussed, or the emotion.
    # Narrator + object cue  -> insert on the object under narration.
    # Narrator + emotion cue -> reaction close-up.
    # Character speaker + emotion cue -> reaction close-up.
    # Character speaker otherwise -> medium on the speaker.
    # Narrator with neither -> establishing (breathing room).
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


def shot_diversity_report(shots):
    return CameraPlanner.shot_diversity_report(shots)
