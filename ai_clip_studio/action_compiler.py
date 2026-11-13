"""Semantic action compiler (Visual Quality Recovery, Priority 1).

Converts every ACTION directive in a V1 scene package into executable
animation events -- or into an EXPLICIT unsupported entry. Nothing is
silently replaced by an idle animation: a sentence the engine cannot
execute appears in the ``unsupported`` list with a reason and a
category, never as a standing pose.

Input: a V1 scene package (the adapter's ``scene_package`` dict, with
``v1_scene`` blocks carrying SHOT ACTION lists) plus a ``timeline``
dict. Output: ``(events, unsupported)``.

Event dict (exact contract):
  action_id: stable id, e.g. "SC01_SH02_ACT01" (shot id + ordinal).
  actor_id: resolved character identity id (or None, only when the
    sentence names an undeclared group -- then the event is still
    emitted with actor_id None and a note, so coverage stays exact;
    the renderer must skip actor-less events, never invent an actor).
  action_type: verb from ACTION_TYPES (documented enum below).
  target_id: interaction target (character / prop / None).
  prop_id: manipulated prop id (or None).
  start_time / end_time: seconds, from the timeline (see _shot_spans).
  required_pose: {"primitive": PRIMITIVES key (or "face_only" for
    face-system events), "params": {...semantic params...},
    "completion": <completion-state description>}. Geometry (pixel
    targets, chair/desk positions) is NOT invented here: params carry
    semantic references (hand, prop, target, furniture kind) and the
    animation stage / staging assigns pixels -- the same rule the
    section-15 directives follow.
  contact_points: [{joint, target_kind, target_id, tolerance_px,
    (tolerance_deg for gaze)}] -- measurable contact requirements.
  animation_dependencies: [action_ids that must complete first].
  completion_state: {"state": POSE_HELD | PROP_GRASPED |
    PROP_TRANSFERRED | OBJECT_STATE_CHANGED | POSITION_REACHED |
    GAZE_HELD | EXPRESSION_HELD, "details": {...}}.
  Plus provenance: shot_id, scene_number, directive_text, expression
  (the shot's resolved base expression, or None), time_source
  ("timeline" | "estimated"), notes, semantic_action_type (the
  resolved SemanticAction type, or None when the sentence does not
  resolve), and the authorization contract from semantic_contracts:
  source_script_hash (the package's immutable snapshot hash, None
  when the package carries none -- never invented), source_scene_id,
  source_shot_id, source_directive_id (== action_id), action_origin
  (ActionOrigin: EXPLICIT_SCRIPT_ACTION for rule-matched directives,
  SAFE_SUPPORTING_ACTION for gait notes), inference_reason (the
  matched classification phrase), authorization_status
  (AuthorizationStatus.AUTHORIZED). Unsupported entries carry the
  same provenance with action_origin UNSUPPORTED_ACTION and
  authorization_status REJECTED (not authorized to render; an
  explicit unsupported entry, never a substitution). The conflict
  mechanism (detect_conflicts, run when the caller supplies
  inferred_cues) produces ConflictRecords across the parser / cues /
  compiled_events / shot_staging / renderer_events levels with
  resolve_conflict semantics; an unresolved MANDATORY conflict
  raises UnauthorizedStoryChange.

Unsupported dict: {action_id, reason, directive_text, category,
shot_id, scene_number}. Categories: ENVIRONMENT, CAMERA, MAP, AUDIO,
DIALOGUE, COSTUME_STATE, UNCLEAR, NO_ACTOR.

First-person pronoun resolution (documented rule): when the package
declares STORYTELLING_MODE == FIRST_PERSON_ROLEPLAY (read from
``v1_meta`` / ``v1_first_person`` / ``meta`` -- all three shapes are
accepted), first-person pronouns in ACTION text resolve to the
PRIMARY_CHARACTER id, actor-less imperative sentences default to the
primary character (Vietnamese subject elision), and the generic
subject "nhân vật" ("the character") also resolves to the primary
character. FIRST_PERSON_PRONOUNS is the full documented list. In any
other mode, actor-less sentences use carry-over (last actor in the
shot, else the scene's first visible character) and otherwise become
NO_ACTOR unsupported entries -- the compiler never guesses an actor.

No character, story or script/project id is hardcoded anywhere in
this module: actors, props and extras resolve from the package's own
data, and the verb vocabulary is generic Vietnamese/English.
"""
from __future__ import annotations

import math
import re

from .expression_library import interpret as interpret_expression
from .semantic_contracts import (
    ActionAuthority,
    ActionOrigin,
    AuthorizationStatus,
    ConflictRecord,
    SEMANTIC_ACTION_TYPES,
    SemanticAction,
    resolve_conflict,
)

__all__ = [
    "ACTION_TYPES",
    "ACTION_DURATIONS",
    "PRIMITIVE_MAP",
    "FIRST_PERSON_PRONOUNS",
    "MIN_EVENT_SEC",
    "UnauthorizedStoryChange",
    "check_cue_authorization",
    "detect_conflicts",
    "LEVEL_AUTHORITY",
    "SEMANTIC_TO_COMPILER_VERB",
    "FORBIDDEN_SEMANTIC_COMPILATIONS",
    "resolve_semantic_action",
    "resolve_semantic_actions",
    "compile_actions",
    "compile_shot_expressions",
    "resolve_first_person",
    "resolve_sentence_roles",
]

# --- Verb enum -----------------------------------------------------------
# Every action_type the compiler can emit, with its primitive, default
# duration and completion-state kind. "face_only" is a pseudo-primitive
# executed by the expression system (expression_library.params_at),
# not by animation.primitives.
ACTION_TYPES = (
    "WALK", "RUN", "MARCH", "WALK_MUD", "STOP", "IDLE", "WAIT", "TURN",
    "SIT_DOWN", "STAND_UP", "SIT_AT_DESK", "STAND_FROM_CHAIR",
    "BEND_PICK", "KNEEL_PICK",
    "PICK_UP", "TAKE_OUT", "PUT_AWAY", "RELEASE", "OPEN_WALLET",
    "CLOSE_WALLET", "OPEN", "CLOSE",
    "HOLD", "HOLD_PEN", "WRITE", "SIGN", "HAND_OVER", "RECEIVE_PROP",
    "CARRY", "CROUCH", "BOARD",
    "HAMMER_STRIKE",
    "REACH", "POINT", "RAISE_HAND", "WAVE", "NOD", "SHRUG",
    "COVER_FACE", "LOOK_AT", "HEAD_TILT", "BREATHE", "REACT",
    "EXPRESSION_HOLD", "BROW_RAISE", "BLINK",
)

# action_type -> (primitive, default duration sec, completion state)
PRIMITIVE_MAP = {
    "WALK": ("walk_to", 1.6, "POSITION_REACHED"),
    "RUN": ("run_to", 1.2, "POSITION_REACHED"),
    "MARCH": ("walk_to", 1.6, "POSITION_REACHED"),
    "WALK_MUD": ("walk_mud", 2.4, "POSITION_REACHED"),
    "STOP": ("idle", 0.8, "POSE_HELD"),
    "IDLE": ("idle", 1.0, "POSE_HELD"),
    "WAIT": ("idle", 1.0, "POSE_HELD"),
    "TURN": ("turn_to", 0.35, "POSE_HELD"),
    "SIT_DOWN": ("sit_down", 0.8, "POSE_HELD"),
    "STAND_UP": ("stand_up", 0.8, "POSE_HELD"),
    "SIT_AT_DESK": ("sit_at_desk", 1.2, "POSE_HELD"),
    "STAND_FROM_CHAIR": ("stand_from_chair", 1.0, "POSE_HELD"),
    "BEND_PICK": ("bend_pick", 1.2, "PROP_GRASPED"),
    "KNEEL_PICK": ("kneel_pick", 1.2, "PROP_GRASPED"),
    "PICK_UP": ("pick_up", 1.0, "PROP_GRASPED"),
    "TAKE_OUT": ("pick_up", 1.0, "PROP_GRASPED"),
    "PUT_AWAY": ("put_away", 1.0, "OBJECT_STATE_CHANGED"),
    "RELEASE": ("put_away", 0.8, "OBJECT_STATE_CHANGED"),
    "OPEN_WALLET": ("open_wallet", 1.0, "OBJECT_STATE_CHANGED"),
    "CLOSE_WALLET": ("close_wallet", 0.8, "OBJECT_STATE_CHANGED"),
    # Generic open/close reuse the two-hand open/close execution;
    # the object articulation is the prop/environment's job.
    "OPEN": ("open_wallet", 1.0, "OBJECT_STATE_CHANGED"),
    "CLOSE": ("close_wallet", 0.8, "OBJECT_STATE_CHANGED"),
    "HOLD": ("pick_up", 1.0, "PROP_GRASPED"),
    "HOLD_PEN": ("hold_pen", 1.0, "PROP_GRASPED"),
    "WRITE": ("write_on_paper", 2.0, "OBJECT_STATE_CHANGED"),
    "SIGN": ("sign_document", 1.2, "OBJECT_STATE_CHANGED"),
    "HAND_OVER": ("hand_over", 1.5, "PROP_TRANSFERRED"),
    "RECEIVE_PROP": ("receive_prop", 1.0, "PROP_GRASPED"),
    "CARRY": ("carry_bag", 1.0, "POSE_HELD"),
    "CROUCH": ("crouch", 0.8, "POSE_HELD"),
    # Boarding stages as the approach to the vehicle door; the
    # step-up is a staging concern (ATLAS).
    "BOARD": ("walk_to", 1.6, "POSITION_REACHED"),
    "HAMMER_STRIKE": ("hammer_strike", 1.8, "OBJECT_STATE_CHANGED"),
    "REACH": ("reach_to", 1.0, "POSE_HELD"),
    "POINT": ("point_at", 0.8, "POSE_HELD"),
    "RAISE_HAND": ("raise_hand", 0.8, "POSE_HELD"),
    "WAVE": ("wave", 1.2, "POSE_HELD"),
    "NOD": ("nod", 0.6, "POSE_HELD"),
    "SHRUG": ("shrug", 0.8, "POSE_HELD"),
    "COVER_FACE": ("cover_face", 1.0, "POSE_HELD"),
    "LOOK_AT": ("look_at_point", 0.8, "GAZE_HELD"),
    "HEAD_TILT": ("head_tilt", 0.8, "POSE_HELD"),
    "BREATHE": ("breathe", 1.5, "POSE_HELD"),
    "REACT": ("react_event", 1.2, "POSE_HELD"),
    "EXPRESSION_HOLD": ("face_only", 1.0, "EXPRESSION_HELD"),
    "BROW_RAISE": ("face_only", 0.6, "EXPRESSION_HELD"),
    "BLINK": ("face_only", 0.4, "EXPRESSION_HELD"),
}

ACTION_DURATIONS = {k: v[1] for k, v in PRIMITIVE_MAP.items()}

# --- Semantic mapping (TOTAL over SEMANTIC_ACTION_TYPES) ------------
# Every semantic action type resolves to exactly one compiler verb.
# The mapping is total by construction and asserted total by test:
# set(SEMANTIC_TO_COMPILER_VERB) == SEMANTIC_ACTION_TYPES and every
# value is a member of ACTION_TYPES. Many-to-one is expected (GIVE
# and HAND_OVER share the transfer execution; BEND_PICK and
# PICK_FROM_GROUND share the kneel_pick execution, the engine's
# canonical ground pickup). The resolver (below) produces the
# semantic type; _classify produces the compiler verb from the same
# sentence; FORBIDDEN_SEMANTIC_COMPILATIONS names the verb choices
# that CONTRADICT a resolved type (the R3 conflict rule) -- it is a
# forbidden-pairs table, not full agreement checking, so compiler
# specializations (OPEN_WALLET for a wallet OPEN, SIT_AT_DESK for a
# desk SIT) never false-positive.
SEMANTIC_TO_COMPILER_VERB = {
    "HEAD_TILT_DOWN": "HEAD_TILT",
    "BEND_PICK": "KNEEL_PICK",
    "TAKE_FROM_POCKET": "TAKE_OUT",
    "PICK_FROM_GROUND": "KNEEL_PICK",
    "PICK_FROM_SURFACE": "PICK_UP",
    "CROUCH": "CROUCH",
    "RECEIVE_PROP": "RECEIVE_PROP",
    "HAMMER_STRIKE": "HAMMER_STRIKE",
    "WALK": "WALK",
    "RUN": "RUN",
    "STOP": "STOP",
    "TURN": "TURN",
    "LOOK_AT": "LOOK_AT",
    "GIVE": "HAND_OVER",
    "TAKE": "PICK_UP",
    "OPEN": "OPEN",
    "CLOSE": "CLOSE",
    "PUT_AWAY": "PUT_AWAY",
    "TAKE_OUT": "TAKE_OUT",
    "SIT": "SIT_DOWN",
    "STAND": "STAND_UP",
    "WAVE": "WAVE",
    "SHRUG": "SHRUG",
    "NOD": "NOD",
    "BREATHE": "BREATHE",
    "WRITE": "WRITE",
    "SIGN": "SIGN",
    "HAND_OVER": "HAND_OVER",
    "HOLD": "HOLD",
    "CARRY": "CARRY",
    "BOARD": "BOARD",
    "REACT": "REACT",
    "RELEASE_PROP": "RELEASE",
    "PLACE_ON_SURFACE": "RELEASE",
}

FORBIDDEN_SEMANTIC_COMPILATIONS = {
    # The proven contamination pairs: a head bow compiled as a
    # ground pickup, a pocket take compiled as a ground pickup.
    "HEAD_TILT_DOWN": frozenset({"BEND_PICK", "KNEEL_PICK", "PICK_UP"}),
    "BEND_PICK": frozenset({"HEAD_TILT", "TAKE_OUT"}),
    "TAKE_FROM_POCKET": frozenset({"BEND_PICK", "KNEEL_PICK", "PICK_UP"}),
    "PICK_FROM_SURFACE": frozenset({"TAKE_OUT", "BEND_PICK", "KNEEL_PICK"}),
    "PICK_FROM_GROUND": frozenset({"HEAD_TILT", "TAKE_OUT"}),
    "CROUCH": frozenset({"BEND_PICK", "KNEEL_PICK", "PICK_UP"}),
    "RECEIVE_PROP": frozenset({"BEND_PICK", "KNEEL_PICK", "PICK_UP",
                               "TAKE_OUT"}),
    # Release destinations: a drop or a surface put-down compiled
    # as a pocketing (PUT_AWAY) stages the wrong rest -- the
    # renderer pockets PUT_AWAY and surfaces RELEASE.
    "RELEASE_PROP": frozenset({"PUT_AWAY", "TAKE_OUT", "PICK_UP",
                               "KNEEL_PICK"}),
    "PLACE_ON_SURFACE": frozenset({"PUT_AWAY", "TAKE_OUT", "PICK_UP",
                                   "KNEEL_PICK"}),
}

# Shortest an event may be compressed to fit a shot span. Below this
# the event keeps its floor and the shot is flagged "overflow" --
# durations are never silently crushed to zero.
MIN_EVENT_SEC = 0.4

# --- First-person pronouns ----------------------------------------------
# Word-boundary matched, case-insensitive. "em" is deliberately NOT
# listed: it can mean "I" or "you" depending on the speaker, so it
# must never silently resolve. "nhân vật" ("the character") is handled
# separately: in FIRST_PERSON_ROLEPLAY it resolves to the primary
# character as the generic protagonist reference.
FIRST_PERSON_PRONOUNS = (
    "tôi", "mình", "ta", "tớ", "tui", "tao",
    "i", "me", "myself",
)

# --- Action authorization ----------------------------------------------
# Every compiled event and every shot cue record carries the
# provenance contract: source_script_hash / source_scene_id /
# source_shot_id / source_directive_id / action_origin /
# inference_reason / authorization_status. The vocabularies are
# ATLAS-owned (semantic_contracts.py -- imported, never redefined
# here): action_origin is an ActionOrigin value, authorization_status
# an AuthorizationStatus value. Cue records (vi_script_parser) carry
# origin PLANNER_INFERRED_ACTION + status INFERRED. A compiled event
# that stages something an explicit directive contradicts is an
# unauthorized story change: the conflict mechanism raises
# UnauthorizedStoryChange on unresolved mandatory conflicts, never
# renders a different story.


class UnauthorizedStoryChange(ValueError):
    """An inferred cue stages something an explicit directive
    contradicts (e.g. a ground pickup staged against a pocket-take
    directive). Raised loudly by check_cue_authorization so the
    pipeline never silently renders a different story. Callers must
    NOT swallow this into an empty event list: it is a distinct
    type so the pipeline can fail the job on it."""


def _script_hash(package: dict):
    """Source script hash from the package, or None (never invented).

    The adapter records the immutable snapshot hash as
    ``v1_snapshot_hash``; older/alternate shapes (script_hash,
    snapshot_hash, v1_meta/meta blocks) are accepted.
    """
    for key in ("v1_snapshot_hash", "script_hash", "snapshot_hash"):
        value = package.get(key)
        if value:
            return str(value)
    for block_key in ("v1_meta", "meta"):
        block = package.get(block_key) or {}
        if isinstance(block, dict):
            for key in ("script_hash", "snapshot_hash",
                        "v1_snapshot_hash"):
                if block.get(key):
                    return str(block[key])
    return None


def _scene_id(number) -> str | None:
    """Canonical scene id (SC01) from a scene number, or None."""
    if number is None:
        return None
    try:
        return f"SC{int(number):02d}"
    except (TypeError, ValueError):
        return str(number)


# Hand mentions that select the RECEIVER hand of a handover. The
# first mention in the shot's sentences wins; with no mention the
# receiver hand stays "l" (the engine's historical default -- the
# product renderer and prop state machine both assume it).
_HAND_MENTIONS = (("tay phải", "r"), ("right hand", "r"),
                  ("tay trái", "l"), ("left hand", "l"))


def _hand_mentioned(text: str) -> str | None:
    """First hand mention ("l" | "r") in action text, or None."""
    normed = _normalize(text or "")
    best = None
    for phrase, hand in _HAND_MENTIONS:
        found = re.search(r"(?:^| )" + re.escape(phrase) + r"(?: |$)",
                          normed)
        if found and (best is None or found.start() < best[0]):
            best = (found.start(), hand)
    return best[1] if best is not None else None


def _receive_hand_from_text(text: str) -> str:
    """Receiver hand ("l" | "r") named in action text, else "l"."""
    return _hand_mentioned(text) or "l"

# Collective markers: "<marker> + <group noun>" names a background
# group (extras), never an individual character.
_COLLECTIVE_MARKERS = ("các", "đoàn", "hàng", "đội", "nhóm", "đám",
                       "một nhóm", "một đoàn")

# Group-noun families for extras resolution. A family matches an
# extras group when the group's id/name/role/costume contains one of
# the family's identity words.
_GROUP_FAMILIES = {
    "soldiers": {
        "nouns": ("binh lính", "lính", "tân binh", "quân lính",
                  "soldiers", "troops", "recruits"),
        "identity": ("soldier", "binh", "quân"),
    },
    "civilians": {
        "nouns": ("người dân", "dân thường", "người qua đường",
                  "người đi đường", "civilians", "passersby",
                  "bystanders"),
        "identity": ("civilian", "dân sự", "background"),
    },
}

# Prop-kind noun vocabulary (generic Vietnamese/English). A prop
# matches when any term for its kind -- or any word from its own
# name/description -- appears in the sentence.
PROP_KIND_NOUNS = {
    "wallet": ("ví", "bóp", "wallet", "purse"),
    "pen": ("bút", "ngòi bút", "pen"),
    "letter": ("đơn", "tờ đơn", "lá đơn", "thư", "tài liệu", "giấy tờ",
               "giấy", "letter", "document", "paper", "form"),
    "bag": ("túi hành quân", "ba lô", "túi xách", "cặp sách", "túi",
            "bag", "backpack", "pack", "sack"),
    "book": ("sách", "quyển sách", "vở", "book", "notebook"),
    "key": ("chìa khóa", "key"),
    "phone": ("điện thoại", "phone"),
    "cup": ("cốc", "ly", "tách", "chén", "cup", "glass"),
    "sword": ("kiếm", "sword"),
    "bolt": ("tia chớp", "tia sét", "lightning", "bolt"),
    "hammer": ("búa", "hammer"),
    "trident": ("đinh ba", "trident"),
    "helmet": ("mũ sắt", "mũ tàng hình", "helmet"),
    "chain": ("xích", "dây xích", "chain", "shackle"),
    "stone": ("hòn đá", "viên đá", "tảng đá", "stone", "rock", "boulder",
              "pebble"),
    "boulder": ("tảng đá", "boulder", "mountain rock", "giant rock"),
    "staff": ("gậy", "quyền trượng", "staff", "scepter"),
    "shield": ("khiên", "shield"),
    "crown": ("vương miện", "crown"),
    "ring": ("nhẫn", "ring"),
    "hat": ("mũ", "nón", "hat"),
    "umbrella": ("ô", "dù", "umbrella"),
    "chair": ("ghế", "chair"),
    "desk": ("bàn", "desk", "table"),
}

# Pocket phrases: "túi áo" / "túi quần" is a pocket, never the bag
# prop. Bare "túi" in TAKE_OUT / PUT_AWAY sentences is also a pocket
# (a wallet goes into a pocket, not into a military bag); bare "túi"
# elsewhere resolves to a bag prop when one exists.
_POCKET_PHRASES = ("túi áo", "túi quần", "túi ngực", "pocket")

# --- Classification ------------------------------------------------------
# (action_type, keyword phrases), checked in order: most specific
# first. All matching is word-boundary on normalised text, so "chỉ"
# never fires inside "chỉ huy" and "đi" never fires inside "điều".
# A rule may carry a guard: a callable(sentence_norm, context) that
# must also pass (e.g. SIT_AT_DESK needs a desk/chair word).
_CLASSIFICATION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("SIGN", ("ký tên", "kí tên", "ký vào", "sign", "signing")),
    ("WRITE", ("bắt đầu viết", "viết", "ngòi bút tiếp xúc",
               "cổ tay chuyển động", "write", "writing")),    ("SIT_AT_DESK", ("ngồi trước bàn", "ngồi ở bàn", "ngồi vào bàn",
                     "ngồi trước", "ngồi bên bàn", "sit at the desk",
                     "sit at a desk")),
    ("OPEN_WALLET", ("mở ví", "mở bóp", "open the wallet",
                     "open wallet")),
    ("CLOSE_WALLET", ("đóng ví", "gấp ví", "đậy ví", "close the wallet",
                      "close wallet")),
    # Generic open/close (a door, box, lid): the wallet phrases
    # above win for wallets. Bare "mở" is NOT a rule: "mở rộng"
    # (widen, a camera verb) must never compile to OPEN.
    ("OPEN", ("mở cửa", "mở hộp", "mở nắp", "mở túi", "mở ra",
             "mở cổng", "mở thư", "mở sách", "mở phong bì",
             "open the", "open a")),
    ("CLOSE", ("đóng cửa", "đóng hộp", "đóng nắp", "đóng lại",
              "đóng túi", "đóng cổng", "close the", "close a")),
    ("TAKE_OUT", ("lấy ví từ", "lấy từ túi", "móc ví", "móc từ túi",
                  "rút ví", "take out", "pull out")),
    ("PUT_AWAY", ("cất ví", "cất vào túi", "bỏ ví vào", "bỏ vào túi",
                  "put away", "put back")),
    ("RELEASE", ("đặt xuống", "để xuống", "đặt bút xuống",
                 "đánh rơi", "làm rơi", "rơi khỏi tay",
                 "tuột khỏi tay",
                 "put down", "set down", "place down", "lay down")),
    ("CARRY", ("túi dao động", "đeo túi", "mang túi", "vác túi",
               "vác", "mang theo", "carry", "carrying")),
    ("HOLD_PEN", ("cầm bút", "cầm lấy bút", "hold the pen",
                  "hold a pen", "grip the pen")),
    # Hammer work (Test F): the phrases name the TOOL or the strike,
    # never just the place -- "lò rèn" (the forge) alone must NOT
    # match, or "bước vào lò rèn" (entering the forge) would compile
    # to hammering instead of walking. Bare "rèn" is likewise
    # excluded: it appears in the location name. A generic "working
    # around the forge" sentence stays UNCLEAR (honest: it names no
    # executable action); the specific hammer sentence in the same
    # shot compiles.
    ("HAMMER_STRIKE", ("nâng búa", "đập búa", "gõ búa", "vung búa",
                       "đóng búa", "dập búa", "búa đập", "búa gõ",
                       "rèn kim loại", "rèn vũ khí", "đập đe",
                       "gõ đe", "đập xuống đe", "hammer",
                       "hammering", "smithing", "strike the anvil",
                       "hit the anvil", "swing the hammer")),
    ("HAND_OVER", ("đưa cho", "trao cho", "đưa về phía",
                   "đưa đơn", "trao đơn", "trao tay", "chuyển giao",
                   "bàn giao", "hand over", "give the")),
    # Receiving: the receiver side of a transfer. "nhận ra" /
    # "nhận thấy" (realize/notice) and "thừa nhận" (admit) are NOT
    # receives -- the _RECEIVE_EXCLUSIONS guard in _classify vetoes
    # them after the phrase match.
    ("RECEIVE_PROP", ("nhận bằng tay", "nhận lấy", "đón lấy",
                      "nhận", "receive")),
    ("WALK_MUD", ("bước qua lối đi đầy bùn", "lội bùn", "lội",
                  "đi qua bùn", "bước qua bùn", "di chuyển khó khăn",
                  "giày lún", "lún nhẹ", "walk through mud",
                  "wade through mud")),
    ("MARCH", ("hành quân", "đi giữa đội hình", "march", "marching")),
    ("BROW_RAISE", ("nhướng mày", "nhướn mày", "raise an eyebrow",
                    "raise eyebrows", "raised brow")),
    ("BLINK", ("chớp mắt", "nháy mắt", "blink", "blinking")),
    ("EXPRESSION_HOLD", ("giữ biểu cảm", "giữ vẻ", "giữ nét mặt",
                         "hold the expression")),
    ("REACT", ("giật mình", "vai co lại", "cúi người theo phản xạ",
               "theo phản xạ", "rùng mình", "startle", "flinch",
               "recoil")),
    ("HEAD_TILT", ("hơi cúi đầu", "cúi đầu", "ngẩng đầu", "nghiêng đầu",
                   "cúi mặt", "ngẩng mặt", "gục đầu", "bow the head",
                   "raise the head", "tilt the head")),
    ("RAISE_HAND", ("đưa một tay lên", "đưa tay lên", "giơ tay",
                    "giơ một tay", "raise a hand", "raise hand")),
    # Bare "quỳ" (kneel) is NOT a pickup: kneeling to pray is a
    # posture, and compiling it to KNEEL_PICK would stage a ground
    # pickup the script never directed (the same error class as the
    # Hitler contamination). Only kneel + pickup phrasing matches.
    ("KNEEL_PICK", ("cúi xuống nhặt", "cúi nhặt", "quỳ xuống nhặt",
                    "quỳ nhặt", "nhặt lên",
                    "nhặt", "kneel", "pick up from the ground")),
    ("BEND_PICK", ("cúi xuống lấy", "cúi lấy", "bend down")),
    # Crouch: torso bends WITHOUT picking anything up. KNEEL_PICK
    # (any "nhặt") and REACT ("theo phản xạ") are checked before
    # this rule, so a pickup or a flinch never becomes a crouch.
    ("CROUCH", ("cúi người tránh", "cúi người xuống", "cúi thấp người",
               "hạ thấp người", "ngồi xổm", "cúi người",
               "khom người né", "khom người tránh",
               "khom lưng né", "khom lưng tránh",
               "crouch", "duck down")),
    ("PICK_UP", ("cầm lên", "cầm lấy", "nhấc lên", "lấy lên",
                 "pick up", "pickup", "take hold")),
    ("HOLD", ("cầm", "giữ chặt", "nắm chặt lấy", "nắm chặt",
              "nắm lấy", "nắm tay", "hold", "holding")),
    ("SIT_DOWN", ("ngồi xuống", "ngồi", "sit down", "sit")),
    ("STAND_UP", ("đứng dậy", "đứng lên", "stand up")),
    ("BOARD", ("lên xe buýt", "lên xe", "bước lên xe",
              "board the", "boarding")),
    ("RUN", ("chạy tới", "chạy đến", "lao tới", "chạy", "run",
             "running")),
    ("TURN", ("quay sang", "quay lại", "quay đầu", "quay người",
              "quay", "turn around", "turn to")),
    ("LOOK_AT", ("quay mắt", "nhìn quanh", "nhìn về", "nhìn sang",
                 "nhìn vào", "nhìn", "liếc", "ngó", "look at",
                 "look toward", "look", "gaze")),
    ("STOP", ("dừng bước", "dừng lại", "dừng chân", "dừng", "stop",
              "halt")),
    ("WALK", ("đi bộ", "bước đi", "đi ngang", "đi qua", "đi tới",
              "bước đến", "bước", "đi", "di chuyển", "walk",
              "walking", "stroll")),
    ("POINT", ("chỉ tay", "chỉ", "point")),
    # Bare "với" is NOT a reach verb: it is the preposition "with"
    # ("trả lời với vẻ thờ ơ" = answer indifferently). Only the
    # "với lấy / với tới" grasp forms reach.
    ("REACH", ("với lấy", "với tới", "vươn tay", "vươn tới",
               "reach")),
    ("WAVE", ("vẫy tay", "vẫy", "wave", "waving")),
    ("NOD", ("gật đầu", "gật", "nod")),
    ("SHRUG", ("nhún vai", "shrug")),
    ("COVER_FACE", ("che mặt", "ôm mặt", "úp mặt", "cover face")),
    ("BREATHE", ("hít một hơi", "hít thở", "hít sâu", "hít vào",
                 "hít", "thở nhẹ", "thở dài", "thở", "breathe",
                 "sigh")),
    ("WAIT", ("im lặng", "đợi", "chờ", "wait", "pause")),
    ("IDLE", ("đứng yên", "đứng im", "đứng", "stand still", "idle")),
]

# "nhận" false friends: cognition / admission, never a prop receive.
_RECEIVE_EXCLUSIONS = (
    "nhận ra", "nhận thấy", "nhận xét", "thừa nhận", "công nhận",
    "nhận được tin", "nhận định",
    # Abstract objects: receiving dominion, responsibility or a
    # mission is not receiving a prop ("Mỗi người nhận một phần
    # quyền cai quản"). Bare "quyền" is NOT excluded: "quyền
    # trượng" (scepter) is a prop receive.
    "quyền cai quản", "quyền lực", "trách nhiệm", "nhiệm vụ",
)


# Bare-"lấy" fallback vocabulary: generic graspable-object nouns
# (the PROP_KIND_NOUNS vocabulary minus furniture and single-letter
# nouns, plus the tool/weapon kinds the table does not list). A
# sentence with "lấy" + one of these nouns and no earlier rule match
# is a TAKE (PICK_UP) -- e.g. "Lấy bút trên bàn" (the normative
# PICK_FROM_SURFACE example), which no verb-phrase rule matches.
# Exclusions veto the idioms where "lấy" is not a grasp verb.
_TAKE_OBJECTS = tuple(sorted(
    {noun for kind, nouns in PROP_KIND_NOUNS.items()
     if kind not in ("chair", "desk") for noun in nouns
     if len(noun) > 1}
    | {"búa", "hammer", "đinh ba", "trident", "mũ sắt", "helmet"}))
_TAKE_EXCLUSIONS = (
    "lấy làm", "lấy vợ", "lấy chồng", "lấy cớ", "lấy lòng",
    "lấy lệ", "lấy danh",
)


# Gait/quality notes: sentences that describe HOW a locomotion or
# action is performed rather than a new action. They compile to the
# scene's current locomotion type with a gait_note flag, so the
# requirement is visible to the animation stage instead of dropped.
_GAIT_NOTE_PHRASES = (
    "chuyển động theo bước chân", "chuyển động đúng chu kỳ",
    "bước lệch pha", "tay và chân chuyển động",
    "chuyển động tự nhiên", "tay chuyển động",
    "cơ thể nghiêng để giữ thăng bằng", "giữ thăng bằng",
)

# Phenomenon subjects: sentences whose SUBJECT is a non-character
# phenomenon ("Điện chạy nhẹ quanh cánh tay" -- electricity running
# around the arm, a VFX description) must never compile to a
# character action ("chạy" -> RUN would make the character run).
# The guard requires the phenomenon phrase at the START of the
# sentence (the subject position); the same noun as an object
# ("Zeus nhận tia sét") is unaffected. "tiếng" (sound) is excluded:
# the AUDIO non-character rules already own sound subjects.
_PHENOMENON_SUBJECTS = (
    "điện", "ánh sáng", "lửa", "khói", "bóng tối", "tia sét",
    "tia chớp", "gió", "mưa", "nước", "bóng",
)


# Non-character categories, checked when no action rule matches.
_NON_CHARACTER_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("MAP", ("bản đồ", "quốc gia", "biên giới", "tuyến di chuyển",
             "tuyến đường", "đường kết nối", "đường nối", "kết nối",
             "làm nổi bật", "khu vực", "vị trí",
             "map", "country", "border", "route")),
    ("CAMERA", ("camera", "cận cảnh", "mở rộng", "góc quay",
                "quay cận", "zoom", "pan")),
    ("ENVIRONMENT", ("chiến hào", "khói", "mưa", "nước đọng",
                     "vũng bùn", "xuất hiện", "hiển thị",
                     "trench", "smoke", "rain", "puddle")),
    ("AUDIO", ("tiếng pháo", "tiếng nổ", "tiếng", "sound of")),
    ("DIALOGUE", ("trả lời", "đáp lời", "nói", "answer", "reply",
                  "respond")),
    ("COSTUME_STATE", ("quần áo", "trang phục", "bám bùn", "ướt",
                       "mặc", "áo khoác", "đội mũ",
                       "costume", "clothes", "wearing", "wears",
                       "dressed in")),
]

_SENTENCE_SPLIT_RE = re.compile(r"[.!?;\n]+")
_WORD_SPLIT_RE = re.compile(r"[^\w']+", re.UNICODE)


def _normalize(text: str) -> str:
    lowered = (text or "").lower().replace("’", "'")
    return " ".join(_WORD_SPLIT_RE.split(lowered)).strip()


def _tokens(text: str) -> list[str]:
    return [t for t in _WORD_SPLIT_RE.split(
        (text or "").lower().replace("’", "'")) if t]


def _has_phrase(normed: str, phrase: str) -> bool:
    """Word-boundary phrase match on normalised text."""
    if not phrase:
        return False
    pattern = r"(?:^| )" + re.escape(phrase) + r"(?: |$)"
    return re.search(pattern, normed) is not None


def _has_any(normed: str, phrases) -> bool:
    return any(_has_phrase(normed, p) for p in phrases)


def _matching_phrase(normed: str, phrases):
    """First phrase (in listed order) matching the text, or None."""
    for phrase in phrases:
        if _has_phrase(normed, phrase):
            return phrase
    return None


# --- Package reading -----------------------------------------------------

def _first_person_info(package: dict) -> dict:
    """{enabled, primary_character} from any meta shape the adapter
    emits: ``v1_meta`` / ``v1_first_person`` / ``meta``."""
    info = {"enabled": False, "primary_character": None}
    for key in ("v1_first_person", "v1_meta", "meta"):
        block = package.get(key) or {}
        if not isinstance(block, dict):
            continue
        mode = (block.get("storytelling_mode")
                or block.get("STORYTELLING_MODE") or "")
        primary = (block.get("primary_character")
                   or block.get("PRIMARY_CHARACTER"))
        if str(mode).upper() == "FIRST_PERSON_ROLEPLAY":
            info["enabled"] = True
            info["primary_character"] = primary
        elif primary and info["primary_character"] is None:
            info["primary_character"] = primary
    return info


def _character_index(package: dict):
    """(char_map, extras) for actor resolution.

    char_map: normalised-name-key -> identity id, from characters +
    v1_characters. extras: list of extras-group dicts (v1_extras /
    is_extra characters) for collective-noun resolution.
    """
    char_map: dict[str, str] = {}
    extras: list[dict] = []

    def _add(char: dict, is_extra: bool):
        ident = char.get("identity_id") or char.get("id")
        name = char.get("name") or ""
        if is_extra:
            extras.append(char)
        if not ident or not name:
            return
        normed = _normalize(name)
        char_map[normed] = ident
        # Last word of the name (e.g. "Minh" from "Anh Minh") and
        # the identity id itself are resolvable mentions.
        words = normed.split()
        if words:
            char_map.setdefault(words[-1], ident)
        char_map[_normalize(str(ident))] = ident
        # Identity-id tokens (e.g. "cyclops" from CHAR_CYCLOPS) are
        # resolvable mentions: script prose names a character by
        # its short id form ("Một Cyclops") where the declared NAME
        # is the plural/collective form ("Cyclopes"). Only for
        # non-extras characters (extras resolve via collective
        # nouns); never overrides a name-derived key.
        if not is_extra:
            id_tokens = str(ident).lower().replace("_", " ").split()
            if id_tokens and id_tokens[0] == "char":
                id_tokens = id_tokens[1:]
            for tok in id_tokens:
                if len(tok) >= 3:
                    char_map.setdefault(tok, ident)
        # Role words (e.g. "người lính" inside a two-word role name).
        if len(words) >= 2:
            char_map.setdefault(" ".join(words[:2]), ident)

    for char in package.get("characters") or []:
        if isinstance(char, dict):
            _add(char, bool(char.get("is_extra")))
    for char in package.get("v1_characters") or []:
        if isinstance(char, dict):
            _add(char, bool(char.get("is_extra"))
                 or str(char.get("identity_id", "")).startswith("CHAR_BACKGROUND"))
    for char in package.get("v1_extras") or []:
        if isinstance(char, dict):
            _add(char, True)
    return char_map, extras


def _extras_group_for(family: str, extras: list[dict]):
    """Extras group whose id/name/role/costume matches the family."""
    identity_words = _GROUP_FAMILIES[family]["identity"]
    for group in extras:
        hay = _normalize(" ".join(str(group.get(k) or "") for k in
                                  ("identity_id", "id", "name", "role",
                                   "costume")))
        if any(w in hay for w in identity_words):
            return group.get("identity_id") or group.get("id")
    return None


def _resolve_actor_mention(normed: str, char_map: dict,
                           extras: list[dict]):
    """Longest character-name / collective-group mention in the text.

    Collective mentions ("các binh lính", "đoàn binh lính", "người
    dân") resolve to extras groups BEFORE individual names, so the
    plural never steals the singular soldier's identity.
    Returns (actor_id, was_collective).
    """
    for family, spec in _GROUP_FAMILIES.items():
        for noun in spec["nouns"]:
            if _has_phrase(normed, noun):
                collective = _has_any(
                    normed, _COLLECTIVE_MARKERS) or noun in (
                        "binh lính", "tân binh", "người dân")
                if collective:
                    group_id = _extras_group_for(family, extras)
                    if group_id:
                        return group_id, True
    best = None
    for key, ident in char_map.items():
        if key and _has_phrase(normed, key):
            if best is None or len(key) > len(best[0]):
                best = (key, ident)
    if best is not None:
        return best[1], False
    return None, False


# Recipient-complement markers: "<marker> + <name>" at or after the
# transfer verb names the recipient, never the actor. Restricted to
# transfer sentences (HAND_OVER) -- "cho" also introduces purpose
# clauses ("cho chắc chắn") and permission ("cho phép"), which carry
# no character mention and therefore mark nothing. A marker BEFORE
# the verb never marks a recipient: "Cho tôi đưa cốc cho Cronus"
# ("let me give the cup to Cronus") has its recipient after the verb,
# and the pre-verbal pronoun is the subject.
_RECIPIENT_MARKERS = ("cho", "tặng", "đến", "tới", "to", "for")

# Action types whose event carries a character target (the
# target-eligible set compile_actions has always used -- unchanged).
_TARGET_ELIGIBLE = ("LOOK_AT", "TURN", "HAND_OVER", "POINT", "REACH")


def _find_mentions(normed, char_map, extras):
    """Character mentions with token spans.

    Returns [(start, end, ident, was_collective)] with overlaps
    resolved: the longest span wins at each position, collectives
    win ties (the previous global preference, kept positionally).
    Individual names come from char_map; collective group nouns
    resolve to extras groups under the same sentence-level
    collective test _resolve_actor_mention used.
    """
    tokens = normed.split()
    found = []
    for key, ident in char_map.items():
        if not key:
            continue
        ktoks = key.split()
        n = len(ktoks)
        if n == 0 or n > len(tokens):
            continue
        for i in range(len(tokens) - n + 1):
            if tokens[i:i + n] == ktoks:
                found.append((i, i + n, ident, False))
    has_marker = _has_any(normed, _COLLECTIVE_MARKERS)
    for family, spec in _GROUP_FAMILIES.items():
        for noun in spec["nouns"]:
            ntoks = noun.split()
            n = len(ntoks)
            if n == 0 or n > len(tokens):
                continue
            collective = has_marker or noun in (
                "binh lính", "tân binh", "người dân")
            if not collective:
                continue
            group_id = _extras_group_for(family, extras)
            if not group_id:
                continue
            for i in range(len(tokens) - n + 1):
                if tokens[i:i + n] == ntoks:
                    found.append((i, i + n, group_id, True))
    found.sort(key=lambda m: (m[0], -(m[1] - m[0]), not m[3]))
    kept = []
    for mention in found:
        if any(mention[0] < k[1] and k[0] < mention[1] for k in kept):
            continue
        kept.append(mention)
    return kept


def _verb_start(normed, match):
    """Token index of the classified verb head, or None.

    The head is the first word of the classification phrase ("đưa"
    in "đưa cho", "trao" in "trao ... cho", "lấy" in "lấy + ...").
    When the phrase is missing or its head word is not found, the
    caller falls back to whole-sentence order (documented
    degradation, never a guessed position).
    """
    phrase = (match or {}).get("phrase") or ""
    words = [w for w in str(phrase).split() if w.strip(" .+")]
    if not words:
        return None
    head = words[0]
    for i, tok in enumerate(normed.split()):
        if tok == head:
            return i
    return None


def resolve_sentence_roles(sentence, *, normed=None, char_map, extras,
                           action_type=None, match=None,
                           primary_character=None,
                           first_person_enabled=False, carry_actor=None):
    """Positional semantic role resolution for one directive sentence.

    Returns {"actor_id", "recipient_id", "target_id",
    "was_collective", "notes"}.

    The actor is the subject-slot occupant: the character mention,
    first-person pronoun, or generic subject ("nhân vật") CLOSEST
    BEFORE the classified verb head. A mention inside a recipient
    complement ("cho/tặng/đến/tới + name", at or after the transfer
    verb) is the recipient and can never be the actor; a
    first-person pronoun after the verb is the object, never the
    actor. Fallbacks, in order: the generic subject anywhere ->
    the shot's carried-over actor -> the primary character
    (first-person subject elision) -> None (no actor resolvable;
    the caller records NO_ACTOR).

    The previous rule -- longest name match over the whole
    sentence -- inverted giver and receiver ("Rhea đưa bọc khăn
    cho Cronus" resolved actor Cronus) and let the first-person
    default overwrite supporting characters ("Một Cyclops đưa tia
    sét cho Zeus" resolved actor Zeus). Position, not length,
    decides roles.
    """
    text = normed if normed is not None else _normalize(sentence)
    tokens = text.split()
    mentions = _find_mentions(text, char_map, extras)
    verb_at = _verb_start(text, match)
    notes = []

    # Recipient complements (transfer sentences only).
    recipient_id = None
    recipient_spans = []
    if action_type == "HAND_OVER":
        for i, tok in enumerate(tokens):
            if tok not in _RECIPIENT_MARKERS:
                continue
            if verb_at is not None and i < verb_at:
                continue
            for j in range(i + 1, min(i + 4, len(tokens))):
                if (first_person_enabled and primary_character
                        and tokens[j] in FIRST_PERSON_PRONOUNS):
                    recipient_id = primary_character
                    recipient_spans.append((j, j + 1))
                    notes.append(
                        "recipient is the primary character "
                        f"({tok} + first-person pronoun)")
                    break
                hit = next((m for m in mentions if m[0] == j), None)
                if hit is not None:
                    recipient_id = hit[2]
                    recipient_spans.append((hit[0], hit[1]))
                    notes.append(
                        f"recipient {recipient_id} ({tok} complement)")
                    break
            if recipient_id is not None:
                break

    def _in_recipient(start, end):
        return any(start < r_end and r_start < end
                   for r_start, r_end in recipient_spans)

    # Subject-slot candidates: mentions, first-person pronouns and
    # the generic subject, none of them inside a recipient span.
    candidates = []
    for start, end, ident, collective in mentions:
        if not _in_recipient(start, end):
            candidates.append((start, end, ident, collective))
    if first_person_enabled and primary_character:
        for i, tok in enumerate(tokens):
            if (tok in FIRST_PERSON_PRONOUNS
                    and not _in_recipient(i, i + 1)):
                candidates.append((i, i + 1, primary_character, False))
        for i in range(len(tokens) - 1):
            if (tokens[i] == "nhân" and tokens[i + 1] == "vật"
                    and not _in_recipient(i, i + 2)):
                candidates.append((i, i + 2, primary_character, False))

    actor_id = None
    was_collective = False
    if verb_at is not None:
        before = [c for c in candidates if c[1] <= verb_at]
        if before:
            # Closest to the verb wins: "Tôi thấy Chú Tư đưa..."
            # is Chú Tư's give, not the narrator's.
            start, _end, actor_id, was_collective = max(
                before, key=lambda c: c[0])
            notes.append(
                f"actor {actor_id} (subject mention at token {start})")
    elif candidates:
        start, _end, actor_id, was_collective = min(
            candidates, key=lambda c: c[0])
        notes.append(
            f"actor {actor_id} (earliest mention; verb unlocated)")

    if actor_id is None:
        if (first_person_enabled and primary_character
                and _has_phrase(text, "nhân vật")):
            actor_id = primary_character
            notes.append("generic subject 'nhân vật' resolved to "
                         "the primary character")
        elif carry_actor is not None:
            actor_id = carry_actor
            notes.append("actor carried over from the previous "
                         "sentence in this shot")
        elif first_person_enabled and primary_character:
            actor_id = primary_character
            notes.append("subject elision in FIRST_PERSON_ROLEPLAY: "
                         "actor defaults to the primary character")
        else:
            notes.append("no actor resolvable from the sentence, "
                         "the shot or the scene")

    # Target: the recipient for transfers; otherwise the earliest
    # non-actor mention, or a post-verbal first-person pronoun as
    # the object ("Chú Tư nhìn tôi" targets the primary character).
    target_id = None
    if action_type in _TARGET_ELIGIBLE:
        if action_type == "HAND_OVER":
            target_id = recipient_id
        else:
            others = [(s, e, ident) for (s, e, ident, _c) in mentions
                      if ident != actor_id
                      and not _in_recipient(s, e)]
            if others:
                target_id = min(others, key=lambda c: c[0])[2]
            elif (first_person_enabled and primary_character
                    and actor_id != primary_character):
                for i, tok in enumerate(tokens):
                    if (tok in FIRST_PERSON_PRONOUNS
                            and not _in_recipient(i, i + 1)
                            and (verb_at is None or i > verb_at)):
                        target_id = primary_character
                        notes.append("first-person pronoun as object "
                                     "resolved to the primary "
                                     "character")
                        break

    return {"actor_id": actor_id, "recipient_id": recipient_id,
            "target_id": target_id, "was_collective": was_collective,
            "notes": notes}


def resolve_first_person(text: str, primary_character: str | None) -> bool:
    """True when ACTION text uses a first-person pronoun (word-boundary
    match). The pronoun list is FIRST_PERSON_PRONOUNS."""
    if not primary_character:
        return False
    toks = set(_tokens(text))
    return bool(toks & set(FIRST_PERSON_PRONOUNS))


# Words that must never become prop match terms when extracted
# from a prop's own descriptive fields. A prop's INTERACTION text
# ("Cầm, tra vào ổ khóa, đánh rơi, nhặt lên") and DESCRIPTION
# ("Bức thư tay gấp ba") are full of verbs, classifiers, body
# parts and colours -- extracting them as terms made "tay đung
# đưa" match the letter (via 'tay') and "nhận bức thư bằng tay
# trái" match the key (via 'bằng'/'cầm'). Only NOUNS that name the
# prop may match. The curated PROP_KIND_NOUNS vocabulary bypasses
# this filter (it names kinds, not sentences); the filter applies
# to extracted tokens only.
_PROP_TERM_STOPWORDS = frozenset({
    # Classifiers / quantifiers.
    "chiếc", "cái", "con", "cây", "tấm", "tờ", "lá", "quyển",
    "cuốn", "bộ", "đôi", "cặp", "quả", "hạt", "viên", "hòn",
    "mảnh", "miếng", "sợi", "giọt", "loại",
    # Prepositions / particles / conjunctions.
    "bằng", "vào", "lên", "xuống", "từ", "cho", "với", "của",
    "ở", "trên", "dưới", "trong", "ra", "về", "đến", "tới",
    "qua", "theo", "như", "là", "và", "hoặc", "nhưng", "mà",
    "thì", "đã", "đang", "sẽ", "rất", "hơn", "nhất", "cũng",
    "còn", "chỉ", "mới", "lại", "nữa", "không", "chưa", "đừng",
    "hãy", "nên", "phải", "có", "được", "bị", "do", "vì", "nếu",
    "khi", "để",
    # Pronouns / people words.
    "tôi", "tao", "mày", "anh", "chị", "em", "ông", "bà", "cô",
    "chú", "bác", "nó", "hắn", "họ", "chúng", "mình", "ta",
    "người", "ai", "gì", "nào", "đâu",
    # Body parts (a "thư tay" is handwritten, not a hand).
    "đầu", "mặt", "mắt", "mũi", "miệng", "tai", "cổ", "vai",
    "lưng", "bụng", "chân", "tay", "ngón", "tóc", "da", "răng",
    "lưỡi", "gối", "khuỷu",
    # Colours / materials as bare words.
    "vàng", "đỏ", "xanh", "trắng", "đen", "nâu", "xám", "hồng",
    "tím", "cam", "bạc", "đồng", "sắt", "thép", "gỗ", "vải",
    "nhựa", "kim",
    # Common verbs (action words, never prop names).
    "cầm", "giữ", "lấy", "đặt", "mang", "đeo", "đưa", "nhận",
    "mở", "đóng", "đọc", "gấp", "tra", "đánh", "rơi", "nhặt",
    "nhấc", "nắm", "vác", "xách", "kéo", "đẩy", "quay", "nhìn",
    "đi", "đứng", "ngồi", "chạy", "bước", "nói", "cười", "khóc",
    "nghe", "thấy", "biết", "muốn", "thích", "làm", "chơi", "ăn",
    "uống", "ngủ", "thức", "mặc", "cởi", "rửa", "quét", "dọn",
    "cất", "bỏ", "tìm", "gặp", "gọi", "hỏi", "trả", "mua", "bán",
    "tặng", "mượn", "viết", "ký", "vẽ", "học", "dạy",
})

# Raw V1 record fields whose words may name a prop. INTERACTION
# lists actions (verbs) and OWNER names a character -- neither
# ever names the prop itself, so both are excluded.
_PROP_TERM_FIELDS = frozenset({
    "TYPE", "COLOR", "MATERIAL", "DESCRIPTION", "NAME", "KIND",
})
_ENGLISH_NOUN_KINDS: dict[str, tuple[str, ...]] = {}
for _kind, _nouns in PROP_KIND_NOUNS.items():
    for _noun in _nouns:
        if (_noun.isascii() and _noun.isalpha()
                and _noun not in ("form", "glass", "pack", "sack")):
            _ENGLISH_NOUN_KINDS.setdefault(_noun, []).append(_kind)
_ENGLISH_NOUN_KINDS = {k: tuple(v)
                       for k, v in _ENGLISH_NOUN_KINDS.items()}


def _prop_index(package: dict):
    """(props, terms): package props + match terms per prop id.

    Terms come from the prop's kind vocabulary plus nouns from its
    own name/description -- never from a hardcoded story list, and
    never from action words: INTERACTION/OWNER fields and stopwords
    (classifiers, prepositions, verbs, body parts, colours) are
    excluded, so a sentence about a hand never matches a letter.
    """
    props = []
    terms: dict[str, list[str]] = {}
    for prop in package.get("props") or []:
        if not isinstance(prop, dict):
            continue
        pid = prop.get("id") or prop.get("name")
        if not pid:
            continue
        props.append(prop)
        words = set()
        kind = str(prop.get("kind") or "").lower()
        words.update(PROP_KIND_NOUNS.get(kind, ()))
        for field in ("name", "kind", "description"):
            for word in _tokens(str(prop.get(field) or "")):
                if len(word) >= 3 and word not in _PROP_TERM_STOPWORDS:
                    words.add(word)
        fields = prop.get("fields") or {}
        if isinstance(fields, dict):
            for key, value in fields.items():
                if str(key).upper() not in _PROP_TERM_FIELDS:
                    continue
                for word in _tokens(str(value)):
                    if (len(word) >= 3
                            and word not in _PROP_TERM_STOPWORDS):
                        words.add(word)
        # The prop's own id token (e.g. "prop_wallet" -> "wallet")
        # is a match term too.
        for word in _tokens(str(pid)):
            if (word != "prop" and len(word) >= 3
                    and word not in _PROP_TERM_STOPWORDS):
                words.add(word)
        # Cross-language bridge: a prop described in English
        # ("Divine lightning bolt", kind "generic") must still
        # match its Vietnamese script mentions ("tia sét"). When a
        # token of the prop's own name/description/kind/id equals
        # an English noun of a known kind, that kind's full
        # vocabulary (including Vietnamese nouns) joins the prop's
        # terms. Longest-match selection in _resolve_prop keeps
        # this safe: a bridged term wins only when it is the
        # longest mention in the sentence.
        for token in list(words):
            for kind_key in _ENGLISH_NOUN_KINDS.get(token, ()):
                words.update(PROP_KIND_NOUNS[kind_key])
        terms[pid] = sorted(words, key=len, reverse=True)
    return props, terms


def _resolve_prop(normed: str, terms: dict, action_type: str | None):
    """Longest prop-term match. In TAKE_OUT / PUT_AWAY sentences the
    bare word "túi" means the POCKET, never the bag prop, so bag
    matches from that bare word are excluded before selection (the
    manipulated prop -- e.g. the wallet -- still matches)."""
    best = None
    for pid, words in terms.items():
        for word in words:
            if (word == "túi" and action_type in ("TAKE_OUT", "PUT_AWAY")):
                continue
            if _has_phrase(normed, word):
                if best is None or len(word) > len(best[1]):
                    best = (pid, word)
    return best[0] if best is not None else None


def _pocket_mentioned(normed: str) -> bool:
    return _has_any(normed, _POCKET_PHRASES) or _has_phrase(normed, "túi")


# Display verbs: a sentence that STARTS with one presents something
# (a map, an environment, a framing) instead of describing a
# character action, so it routes straight to the non-character
# categories -- "Hiển thị tuyến di chuyển" is a map route, not a
# walk, even though it contains "di chuyển".
_DISPLAY_VERBS = ("hiển thị", "hiện thị", "cho thấy", "trình bày",
                  "display", "show", "present")

# Discontinuous verb patterns: (first word, later word, action_type).
# Vietnamese verb phrases split around their object ("cầm tờ đơn
# lên", "đặt bút xuống"), so contiguous phrase matching alone misses
# them. The second word must come AFTER the first in the sentence.
_DISCONTINUOUS_PATTERNS: list[tuple[str, str, str]] = [
    ("cầm", "lên", "PICK_UP"),
    ("nhấc", "lên", "PICK_UP"),
    ("đặt", "xuống", "RELEASE"),
    ("để", "xuống", "RELEASE"),
    ("đặt", "lên bàn", "RELEASE"),
    ("để", "lên bàn", "RELEASE"),
    ("đặt", "lên kệ", "RELEASE"),
    ("để", "lên kệ", "RELEASE"),
    ("mở", "thư", "OPEN"),
    ("mở", "sách", "OPEN"),
    ("giơ", "lên", "RAISE_HAND"),
    ("đưa", "cho", "HAND_OVER"),
    ("trao", "cho", "HAND_OVER"),
    ("tặng", "cho", "HAND_OVER"),
    # Carry with a split object ("mang chiếc túi", "xách cái cặp"):
    # the classifier sits between the verb and the object noun.
    ("mang", "túi", "CARRY"),
    ("mang", "cặp", "CARRY"),
    ("mang", "ba lô", "CARRY"),
    ("xách", "túi", "CARRY"),
    ("xách", "cặp", "CARRY"),
]

# Bag/prop sway: a sway word + a carried-object noun is secondary
# prop motion (CARRY), never locomotion -- "túi hành quân dao động"
# is the marching bag swaying, not a march, even though the bag's
# name contains "hành quân".
_SWAY_WORDS = ("dao động", "đung đưa", "lung lay", "sway", "swaying")
_SWAY_OBJECTS = ("túi", "ba lô", "cặp", "bag", "pack", "sack")


def _has_discontinuous(normed: str, first: str, later: str) -> bool:
    toks = _tokens(normed)
    # ``later`` may be a multi-word phrase ("lên bàn"): its tokens
    # must appear consecutively after the first word.
    tail = _tokens(later)
    start = 0
    while True:
        try:
            i = toks.index(first, start)
        except ValueError:
            return False
        # "trao đổi" (exchange/discuss) is not a give: skip a
        # "trao" immediately followed by "đổi" and keep looking.
        if (first == "trao" and i + 1 < len(toks)
                and toks[i + 1] == "đổi"):
            start = i + 1
            continue
        # "quà tặng" (gift, noun compound) is not a give: skip a
        # "tặng" immediately preceded by "quà" and keep looking.
        if first == "tặng" and i > 0 and toks[i - 1] == "quà":
            start = i + 1
            continue
        # "mang tên" (named/called) is not a carry: skip a "mang"
        # immediately followed by "tên" and keep looking.
        if (first == "mang" and i + 1 < len(toks)
                and toks[i + 1] == "tên"):
            start = i + 1
            continue
        rest = toks[i + 1:]
        if any(rest[j:j + len(tail)] == tail
               for j in range(len(rest) - len(tail) + 1)):
            return True
        start = i + 1


# Take-from-pocket with a split object: "rút điện thoại từ túi",
# "móc ví ra khỏi túi áo", "take the wallet from the pocket". The
# take verb must precede a from-pocket marker in token order; the
# marker (not the bare noun "túi") is required, so "lấy túi" (take
# the bag) never becomes a pocket take.
_TAKE_FROM_POCKET_VERBS = ("lấy", "rút", "móc", "take", "pull")
_TAKE_FROM_POCKET_MARKERS = (("từ", "túi"), ("khỏi", "túi"),
                             ("from", "pocket"))


def _has_take_from_pocket(normed: str) -> bool:
    toks = _tokens(normed)
    for verb in _TAKE_FROM_POCKET_VERBS:
        if verb not in toks:
            continue
        rest = toks[toks.index(verb) + 1:]
        for marker, noun in _TAKE_FROM_POCKET_MARKERS:
            if marker in rest:
                after = rest[rest.index(marker) + 1:]
                if noun in after[:3]:
                    return True
    return False


def _classify(normed: str, context: dict):
    """(action_type | None, category | None, notes, match_info).

    ``context`` carries the scene's locomotion state (last locomotion
    type, seated actor set) for gait notes and sit/stand pairing.
    ``match_info`` is {"mechanism", "phrase", "detail"} naming exactly
    what decided the classification -- the inference_reason source
    for the event's provenance record. Mechanisms: "rule" (a
    classification phrase matched verbatim), "discontinuous" (a
    split verb phrase), "sway" (secondary prop motion), "gait_note"
    (a quality note compiled to the surrounding locomotion),
    "display_verb" / "non_character" (routed to a non-character
    category), "none" (no rule matched).
    """
    notes: list[str] = []
    info = {"mechanism": "none", "phrase": None, "detail": ""}
    # Display-verb sentences are never character actions.
    if normed.startswith(_DISPLAY_VERBS):
        verb = next((v for v in _DISPLAY_VERBS
                     if normed.startswith(v)), None)
        info.update(mechanism="display_verb", phrase=verb,
                    detail="sentence starts with a display verb; "
                           "routed to the non-character categories")
        for category, phrases in _NON_CHARACTER_RULES:
            phrase = _matching_phrase(normed, phrases)
            if phrase is not None:
                info["detail"] += (f"; matched {category} phrase "
                                   f"{phrase!r}")
                return None, category, notes, info
        return None, "UNCLEAR", notes, info
    # Phenomenon subjects are never character actions.
    for subject in _PHENOMENON_SUBJECTS:
        if normed == subject or normed.startswith(subject + " "):
            info.update(mechanism="non_character", phrase=subject,
                        detail="sentence subject is a non-character "
                               "phenomenon; routed to ENVIRONMENT")
            return None, "ENVIRONMENT", notes, info
    # Bag/prop sway before locomotion rules (see _SWAY_WORDS).
    sway_word = _matching_phrase(normed, _SWAY_WORDS)
    sway_obj = _matching_phrase(normed, _SWAY_OBJECTS)
    if sway_word is not None and sway_obj is not None:
        notes.append("secondary prop motion (sway), not locomotion")
        info.update(mechanism="sway",
                    phrase=f"{sway_word} + {sway_obj}",
                    detail="sway word + carried-object noun -> CARRY")
        return "CARRY", None, notes, info
    # Discontinuous verb phrases ("cầm tờ đơn lên").
    for first, later, action_type in _DISCONTINUOUS_PATTERNS:
        if _has_discontinuous(normed, first, later):
            info.update(
                mechanism="discontinuous",
                phrase=f"{first} ... {later}",
                detail=f"split verb phrase -> {action_type}")
            return action_type, None, notes, info
    # Split take-from-pocket ("rút điện thoại từ túi quần").
    if _has_take_from_pocket(normed):
        info.update(
            mechanism="discontinuous",
            phrase="lấy/rút/móc ... từ/khỏi túi",
            detail="split take-from-pocket phrase -> TAKE_OUT")
        return "TAKE_OUT", None, notes, info
    # Gait / quality notes compile to the current locomotion type --
    # EXCEPT writing-body sentences ("cổ tay chuyển động" is the
    # wrist moving while writing, not a gait note).
    gait_phrase = _matching_phrase(normed, _GAIT_NOTE_PHRASES)
    if (gait_phrase is not None
            and not _has_any(normed, ("cổ tay", "ngòi bút"))):
        loco = context.get("locomotion") or "WALK"
        notes.append("gait/quality note for the surrounding locomotion")
        info.update(mechanism="gait_note", phrase=gait_phrase,
                    detail=f"quality note compiled to the surrounding "
                           f"locomotion {loco}")
        return loco, None, notes, info
    for action_type, phrases in _CLASSIFICATION_RULES:
        phrase = _matching_phrase(normed, phrases)
        if phrase is not None:
            # "nhận ra" (realize) etc. are not receives: veto the
            # match and let later rules / UNCLEAR handle the sentence.
            if action_type == "RECEIVE_PROP" and _has_any(
                    normed, _RECEIVE_EXCLUSIONS):
                continue
            info.update(mechanism="rule", phrase=phrase,
                        detail=f"classification rule {action_type}")
            # "ngồi" + desk/chair word is sitting AT A DESK, not a
            # plain sit_down. The SIT_AT_DESK phrases catch the
            # common forms; this guard catches the rest.
            if action_type == "SIT_DOWN" and _has_any(
                    normed, ("bàn", "ghế", "desk", "chair", "table")):
                info["detail"] += ("; desk/chair guard -> SIT_AT_DESK")
                return "SIT_AT_DESK", None, notes, info
            # "đứng dậy" after sitting at a desk stands FROM A CHAIR.
            if action_type == "STAND_UP" and context.get("seated"):
                info["detail"] += ("; seated context -> "
                                   "STAND_FROM_CHAIR")
                return "STAND_FROM_CHAIR", None, notes, info
            # "mở" + a non-wallet prop has no open primitive.
            if action_type in ("OPEN_WALLET", "CLOSE_WALLET"):
                pass  # wallet phrases already require the wallet noun
            return action_type, None, notes, info
    # Bare-"lấy" fallback: "lấy" + a graspable-object noun, with no
    # earlier rule match, is a take. The object noun is required --
    # bare "lấy" alone ("lấy làm lạ") never matches.
    if (_has_phrase(normed, "lấy")
            and not _has_any(normed, _TAKE_EXCLUSIONS)):
        obj = _matching_phrase(normed, _TAKE_OBJECTS)
        if obj is not None:
            info.update(mechanism="take_fallback", phrase=f"lấy + {obj}",
                        detail="bare 'lấy' + graspable-object noun "
                               "-> PICK_UP")
            return "PICK_UP", None, notes, info
    for category, phrases in _NON_CHARACTER_RULES:
        phrase = _matching_phrase(normed, phrases)
        if phrase is not None:
            info.update(mechanism="non_character", phrase=phrase,
                        detail=f"non-character category {category}")
            return None, category, notes, info
    info["detail"] = "no classification rule matched"
    return None, "UNCLEAR", notes, info


def _contact_points(action_type: str, hand: str, prop_id, target_id,
                    paper_id, target_hand: str | None = None
                    ) -> list[dict]:
    """Measurable contact requirements for an action type."""
    pts: list[dict] = []
    if action_type in ("WRITE", "SIGN"):
        pts.append({"joint": "hand_" + hand, "target_kind": "prop",
                    "target_id": prop_id, "tolerance_px": 8.0})
        pts.append({"joint": "hand_" + hand,
                    "target_kind": "prop_surface",
                    "target_id": paper_id, "tolerance_px": 12.0})
    elif action_type in ("PICK_UP", "TAKE_OUT", "HOLD", "HOLD_PEN",
                         "BEND_PICK", "KNEEL_PICK", "OPEN", "CLOSE"):
        if prop_id:
            pts.append({"joint": "hand_" + hand, "target_kind": "prop",
                        "target_id": prop_id, "tolerance_px": 15.0})
    elif action_type == "HAND_OVER":
        point = {"joint": "hand_" + hand,
                 "target_kind": "character_hand",
                 "target_id": target_id, "tolerance_px": 20.0}
        if target_hand in ("l", "r"):
            # The receiving hand the script names ("tay phải" /
            # "tay trái"); contact_report measures that hand only
            # when present, else the nearer hand (legacy behaviour).
            point["target_hand"] = target_hand
        pts.append(point)
        if prop_id:
            pts.append({"joint": "hand_" + hand, "target_kind": "prop",
                        "target_id": prop_id, "tolerance_px": 15.0})
    elif action_type == "RECEIVE_PROP":
        # The receiver's hand meets the prop; when the giver
        # resolved, the hands must meet (same tolerance as the
        # giver-side HAND_OVER contact, same named-hand rule).
        if target_id:
            point = {"joint": "hand_" + hand,
                     "target_kind": "character_hand",
                     "target_id": target_id, "tolerance_px": 20.0}
            if target_hand in ("l", "r"):
                point["target_hand"] = target_hand
            pts.append(point)
        if prop_id:
            pts.append({"joint": "hand_" + hand, "target_kind": "prop",
                        "target_id": prop_id, "tolerance_px": 15.0})
    elif action_type == "CROUCH":
        # Feet stay planted through the crouch.
        pts.append({"joint": "foot_l", "target_kind": "ground",
                    "target_id": None, "tolerance_px": 4.0})
        pts.append({"joint": "foot_r", "target_kind": "ground",
                    "target_id": None, "tolerance_px": 4.0})
    elif action_type == "HAMMER_STRIKE":
        # The hand grips the tool; the TOOL HEAD contacts the
        # surface (target_kind "tool_head", measured through
        # hammer_head_position in prop_system). The surface point is
        # emitted only when a surface target resolved: without a
        # staged surface there is nothing measurable to check
        # against, and the strike-time head measurement in tests /
        # proofs covers the contact directly.
        if prop_id:
            pts.append({"joint": "hand_" + hand, "target_kind": "prop",
                        "target_id": prop_id, "tolerance_px": 15.0})
        if target_id:
            pts.append({"joint": "hand_" + hand,
                        "target_kind": "tool_head",
                        "target_id": target_id, "tolerance_px": 12.0})
    elif action_type == "CARRY":
        if prop_id:
            pts.append({"joint": "hand_" + hand, "target_kind": "prop",
                        "target_id": prop_id, "tolerance_px": 10.0})
    elif action_type == "SIT_AT_DESK":
        pts.append({"joint": "foot_l", "target_kind": "ground",
                    "target_id": None, "tolerance_px": 4.0})
        pts.append({"joint": "foot_r", "target_kind": "ground",
                    "target_id": None, "tolerance_px": 4.0})
        pts.append({"joint": "hip", "target_kind": "furniture",
                    "target_id": "chair", "tolerance_px": 10.0})
    elif action_type == "WALK_MUD":
        # Feet sink BELOW the ground plane; the tolerance covers the
        # sink depth (staging supplies the exact sink).
        pts.append({"joint": "foot_l", "target_kind": "ground",
                    "target_id": None, "tolerance_px": 20.0})
        pts.append({"joint": "foot_r", "target_kind": "ground",
                    "target_id": None, "tolerance_px": 20.0})
    elif action_type == "LOOK_AT":
        pts.append({"joint": "head", "target_kind": "gaze_target",
                    "target_id": target_id or prop_id,
                    "tolerance_px": None, "tolerance_deg": 15.0})
    elif action_type == "PUT_AWAY":
        pts.append({"joint": "hand_" + hand, "target_kind": "anchor",
                    "target_id": "pocket", "tolerance_px": 15.0})
    elif action_type == "RELEASE":
        if prop_id:
            pts.append({"joint": "hand_" + hand, "target_kind": "prop",
                        "target_id": prop_id, "tolerance_px": 15.0})
    return pts


# --- Conflict detection (A2 mechanism, ATLAS rules; directive §4) ---
# Semantic disagreements between levels, as ConflictRecords from
# semantic_contracts.py (imported -- the record shape and
# resolve_conflict semantics are ATLAS-owned, never redefined here).
# Levels: parser / cues / compiled_events / shot_staging /
# renderer_events. Higher authority (lower number) wins; equal
# authority with disagreement stays unresolved, and an unresolved
# MANDATORY conflict fails semantic preflight (check_cue_authorization
# raises UnauthorizedStoryChange; ATLAS wires preflight).
#
# Rules (first enforcement set; ATLAS extends the rule set):
#   R1 ground-pickup cue vs explicit pocket take/put-away in scope.
#   R2 rain cue vs an explicit no-rain directive in scope.
#   R3 parser resolution vs compiled verb (FORBIDDEN_SEMANTIC_
#      COMPILATIONS pairs only -- specializations never flag).
#   R4 shot staging rests a prop on the ground while its semantic
#      location is not ON_GROUND (the ground rule).
#   R5 a renderer event substitutes a different primitive than the
#      compiled event requires (equal authority -> unresolved).
# LIMITS (honest): the check sees only what it is given -- compiled
# events + directive texts in the same shot (preferred) or scene
# (fallback), plus the staging/renderer records the caller supplies.
# It cannot catch contradictions against environment/audio state no
# level reports (e.g. a job-level rain bed leaking across scenes --
# an audio-stage defect, ATLAS's). A cue record with neither a shot
# nor a scene id cannot be bound and is skipped, never guessed. R4
# skips props whose location is unknown, never guessing ON_GROUND.

LEVEL_AUTHORITY = {
    "parser": ActionAuthority.EXPLICIT_DIRECTIVE,
    "cues": ActionAuthority.PLANNER_SUGGESTION,
    "compiled_events": ActionAuthority.COMPILED_EVENT,
    "shot_staging": ActionAuthority.SUPPORTING_ACTION,
    "renderer_events": ActionAuthority.COMPILED_EVENT,
}

_NO_RAIN_PHRASES = (
    "không mưa", "không có mưa", "không còn mưa", "hết mưa",
    "trời quang", "trời nắng", "no rain", "without rain",
    "dry weather", "clear sky",
)


def _scene_number_of(scene_id):
    if scene_id is None:
        return None
    found = re.search(r"(\d+)", str(scene_id))
    return int(found.group(1)) if found else None


def _rec_get(record, key):
    """Attribute-or-item read (SemanticAction objects or plain dicts)."""
    if isinstance(record, dict):
        return record.get(key)
    return getattr(record, key, None)


def _conflict_ground_pickup_vs_pocket(bound_events, scope):
    """R1: bend_pick vs an explicit pocket take/put-away in scope."""
    pocket_take = [
        e for e in bound_events
        if (e.get("action_type") in ("TAKE_OUT", "PUT_AWAY")
            and ((e.get("required_pose") or {}).get("params") or {}
                 ).get("pocket"))
        or e.get("semantic_action_type") == "TAKE_FROM_POCKET"]
    if not pocket_take:
        return None
    if any(e.get("action_type") in ("BEND_PICK", "KNEEL_PICK")
           or e.get("semantic_action_type") in (
               "BEND_PICK", "PICK_FROM_GROUND")
           for e in bound_events):
        return None  # a genuine ground pickup is also directed
    first = pocket_take[0]
    return ConflictRecord(
        level_a="cues", level_b="compiled_events",
        entity_id=first.get("action_id") or scope,
        description=(
            f"cue 'bend_pick' stages a ground pickup, but directive "
            f"{first.get('action_id')} is an explicit pocket action "
            f"({first.get('action_type')}, pocket=True): "
            f"{first.get('directive_text')!r}; no ground-pickup "
            f"directive exists in {scope}"),
        mandatory=True)


def _conflict_rain_vs_no_rain(cue_record, bound_texts, scope):
    """R2: rain staging vs an explicit no-rain directive in scope."""
    for text in bound_texts:
        phrase = _matching_phrase(_normalize(text), _NO_RAIN_PHRASES)
        if phrase is not None:
            return ConflictRecord(
                level_a="cues", level_b="parser",
                entity_id=(cue_record.get("source_shot_id")
                           or cue_record.get("source_scene_id") or scope),
                description=(
                    f"cue 'rain' stages rain, but an explicit "
                    f"directive states no rain ({phrase!r}): {text!r}"),
                mandatory=True)
    return None


def _conflict_parser_vs_event(action, event):
    """R3: parser resolution vs a forbidden compiled verb."""
    sem_type = _rec_get(action, "action_type")
    verb = event.get("action_type")
    forbidden = FORBIDDEN_SEMANTIC_COMPILATIONS.get(sem_type,
                                                    frozenset())
    if verb in forbidden:
        return ConflictRecord(
            level_a="parser", level_b="compiled_events",
            entity_id=event.get("action_id") or _rec_get(
                action, "source_directive_id"),
            description=(
                f"parser resolved {sem_type} for directive "
                f"{_rec_get(action, 'source_directive_id')!r} "
                f"({_rec_get(action, 'source_text')!r}), but the "
                f"compiler emitted forbidden verb {verb}"),
            mandatory=True)
    return None


def _conflict_staging_ground(staging, prop_locations):
    """R4: ground rest while the semantic location is not ON_GROUND."""
    if staging.get("rest") != "ground":
        return None
    pid = staging.get("prop_id")
    location = (prop_locations or {}).get(pid)
    if location is None or location == "ON_GROUND":
        return None  # unknown: never guess; ON_GROUND: allowed
    return ConflictRecord(
        level_a="shot_staging", level_b="compiled_events",
        entity_id=pid,
        description=(
            f"shot staging rests prop {pid!r} on the ground, but "
            f"its semantic location is {location} (ground rest "
            f"requires ON_GROUND)"),
        mandatory=True)


def _conflict_renderer_primitive(renderer_event, event):
    """R5: renderer substitutes a different primitive."""
    want = (event.get("required_pose") or {}).get("primitive")
    got = renderer_event.get("primitive")
    if want is None or got is None or want == got:
        return None
    return ConflictRecord(
        level_a="renderer_events", level_b="compiled_events",
        entity_id=event.get("action_id"),
        description=(
            f"renderer event for {event.get('action_id')} uses "
            f"primitive {got!r}, but the compiled event requires "
            f"{want!r}"),
        mandatory=True)


def detect_conflicts(*, semantic_actions=(), cue_records=(),
                     compiled_events=(), unsupported=(),
                     staging_records=(), renderer_events=(),
                     prop_locations=None):
    """Detect semantic conflicts across levels; resolve by authority.

    Every rule runs only on the levels supplied. Returns
    ConflictRecords with resolve_conflict already applied (resolved
    records carry winner_authority; equal-authority disagreements
    stay unresolved). A record whose fails_preflight is true must
    fail semantic preflight -- the pipeline must not render a story
    it cannot agree on.
    """
    events = list(compiled_events or [])
    unsupported = list(unsupported or [])
    records: list = []
    # R1/R2: bind each cue record to its shot (preferred) or scene.
    by_shot: dict = {}
    by_scene: dict = {}
    for event in events:
        by_shot.setdefault(event.get("shot_id"), []).append(event)
        by_scene.setdefault(event.get("scene_number"), []).append(event)
    texts_by_shot: dict = {}
    texts_by_scene: dict = {}
    for entry in events + unsupported:
        text = entry.get("directive_text")
        if not text:
            continue
        texts_by_shot.setdefault(entry.get("shot_id"), []).append(text)
        texts_by_scene.setdefault(entry.get("scene_number"),
                                  []).append(text)
    for record in cue_records or []:
        if not isinstance(record, dict):
            continue
        cue = record.get("cue")
        if cue is None:
            continue
        shot_id = record.get("source_shot_id")
        scene_id = record.get("source_scene_id")
        if shot_id is not None:
            bound = by_shot.get(shot_id, [])
            texts = texts_by_shot.get(shot_id, [])
            scope = f"shot {shot_id}"
        elif scene_id is not None:
            number = _scene_number_of(scene_id)
            bound = by_scene.get(number, [])
            texts = texts_by_scene.get(number, [])
            scope = f"scene {scene_id}"
        else:
            continue
        found = None
        if cue == "bend_pick":
            found = _conflict_ground_pickup_vs_pocket(bound, scope)
        elif cue == "rain":
            found = _conflict_rain_vs_no_rain(record, texts, scope)
        if found is not None:
            records.append(found)
    # R3: pair semantic actions with compiled events by directive id.
    events_by_id = {e.get("action_id"): e for e in events}
    for action in semantic_actions or []:
        event = events_by_id.get(
            _rec_get(action, "source_directive_id"))
        if event is None:
            continue
        found = _conflict_parser_vs_event(action, event)
        if found is not None:
            records.append(found)
    # R4: staging ground rests vs semantic locations.
    for staging in staging_records or []:
        if not isinstance(staging, dict):
            continue
        found = _conflict_staging_ground(staging, prop_locations)
        if found is not None:
            records.append(found)
    # R5: renderer primitives vs compiled requirements.
    for rev in renderer_events or []:
        if not isinstance(rev, dict):
            continue
        event = events_by_id.get(rev.get("action_id"))
        if event is None:
            continue
        found = _conflict_renderer_primitive(rev, event)
        if found is not None:
            records.append(found)
    return [resolve_conflict(r, LEVEL_AUTHORITY[r.level_a],
                             LEVEL_AUTHORITY[r.level_b])
            for r in records]


def check_cue_authorization(events, cue_records, unsupported=None):
    """Detect cue conflicts; raise on unresolved mandatory ones.

    Returns every ConflictRecord found. Resolved records carry
    winner_authority -- the consumer must discard the losing
    level's instruction (a losing cue must never reach staging).
    Raises UnauthorizedStoryChange listing records whose
    fails_preflight is true (mandatory + unresolved).
    Cross-authority cue conflicts (R1/R2) resolve to the higher
    authority and do NOT raise: the compiled event wins.
    """
    records = detect_conflicts(
        cue_records=cue_records, compiled_events=events,
        unsupported=unsupported)
    failing = [r for r in records if r.fails_preflight]
    if failing:
        detail = "; ".join(
            f"[{r.level_a} vs {r.level_b}] {r.entity_id}: "
            f"{r.description}" for r in failing)
        raise UnauthorizedStoryChange(
            f"unresolved mandatory semantic conflict(s): {detail}")
    return records


def _iter_action_sentences(package: dict):
    """Yield (scene_number, shot_id, shot, sentence, source_line).

    V1 path: shot fields.ACTION lists (preferred) or the shot's joined
    action text, plus scene-level actions. Free-form fallback: the
    scene's action_text split into sentences under one synthetic shot.
    """
    scenes = package.get("scenes") or []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        v1 = scene.get("v1_scene") or {}
        number = v1.get("number", scene.get("number"))
        shots = v1.get("shots") or []
        if shots:
            for shot in shots:
                fields = shot.get("fields") or {}
                raw_actions = fields.get("ACTION")
                if isinstance(raw_actions, str):
                    raw_actions = [raw_actions]
                sentences: list[str] = []
                if raw_actions:
                    for item in raw_actions:
                        sentences.extend(
                            s.strip(" \t\r\n•*-")
                            for s in _SENTENCE_SPLIT_RE.split(str(item)))
                elif shot.get("action"):
                    sentences.extend(
                        s.strip(" \t\r\n•*-")
                        for s in _SENTENCE_SPLIT_RE.split(
                            str(shot.get("action"))))
                shot_id = shot.get("id") or shot.get("shot_id")
                for sentence in sentences:
                    if sentence:
                        yield (number, shot_id, shot, sentence,
                               shot.get("line"))
            for item in v1.get("actions") or []:
                for sentence in _SENTENCE_SPLIT_RE.split(str(item)):
                    sentence = sentence.strip(" \t\r\n•*-")
                    if sentence:
                        yield (number, None, None, sentence, None)
        else:
            # Free-form fallback: one synthetic shot per scene.
            text = scene.get("action_text") or ""
            shot_id = f"SC{int(number or 0):02d}_SH01"
            for sentence in _SENTENCE_SPLIT_RE.split(text):
                sentence = sentence.strip(" \t\r\n•*-")
                if sentence:
                    yield (number, shot_id, None, sentence, None)


def _shot_spans(package: dict, timeline: dict | None):
    """{shot_id: (start, end)} + time_source flag.

    Preferred: timeline["spans"] ({shot_id: [start, end]}), or
    timeline["shots"] entries carrying a V1 shot id with start/end
    (or cumulative durations). Otherwise ESTIMATED spans from the
    package (action_lead_sec + spoken-line durations, shots sharing
    the scene span) -- flagged time_source="estimated" on every
    event, never presented as measured.
    """
    timeline = timeline or {}
    spans: dict[str, tuple[float, float]] = {}
    # 1. Explicit spans dict.
    raw_spans = timeline.get("spans")
    if isinstance(raw_spans, dict):
        for shot_id, span in raw_spans.items():
            if isinstance(span, dict):
                spans[str(shot_id)] = (float(span["start"]),
                                       float(span["end"]))
            elif isinstance(span, (list, tuple)) and len(span) == 2:
                spans[str(shot_id)] = (float(span[0]), float(span[1]))
        if spans:
            return spans, "timeline"
    # 2. Timeline shots carrying V1 shot ids.
    tl_shots = timeline.get("shots")
    if isinstance(tl_shots, list):
        cursor = 0.0
        found = False
        for entry in tl_shots:
            if not isinstance(entry, dict):
                continue
            shot_id = entry.get("shot_id") or entry.get("v1_shot_id")
            dur = entry.get("duration")
            start = entry.get("start")
            end = entry.get("end")
            if start is None:
                start = cursor
            if end is None and dur is not None:
                end = float(start) + float(dur)
            if dur is not None:
                cursor = float(start) + float(dur)
            elif end is not None:
                cursor = float(end)
            if shot_id and end is not None:
                spans[str(shot_id)] = (float(start), float(end))
                found = True
        if found:
            return spans, "timeline"
    # 3. Estimates from the package.
    line_durations: dict[str, float] = {}
    tl_lines = timeline.get("lines")
    if isinstance(tl_lines, list):
        flat_ids: list[str] = []
        for scene in package.get("scenes") or []:
            v1 = (scene or {}).get("v1_scene") or {}
            for shot in v1.get("shots") or []:
                flat_ids.extend(shot.get("spoken_line_ids") or [])
            for line in (scene or {}).get("lines") or []:
                lid = line.get("line_id")
                if lid and lid not in flat_ids:
                    flat_ids.append(lid)
        for idx, entry in enumerate(tl_lines):
            if not isinstance(entry, dict):
                continue
            dur = entry.get("duration")
            if dur is None:
                continue
            lid = entry.get("line_id")
            if not lid and idx < len(flat_ids):
                lid = flat_ids[idx]
            if lid:
                line_durations[lid] = float(dur)
    cursor = 0.0
    for scene in package.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        v1 = scene.get("v1_scene") or {}
        shots = v1.get("shots") or []
        lead = float(scene.get("action_lead_sec") or 0.0)
        scene_line_ids: list[str] = []
        for shot in shots:
            scene_line_ids.extend(shot.get("spoken_line_ids") or [])
        if not scene_line_ids:
            for line in scene.get("lines") or []:
                if line.get("line_id"):
                    scene_line_ids.append(line["line_id"])
        line_total = sum(line_durations.get(lid, 4.0)
                         for lid in scene_line_ids)
        scene_total = max(lead + line_total, 1.5 * max(len(shots), 1))
        if not shots:
            shot_id = f"SC{int(v1.get('number', scene.get('number') or 0)):02d}_SH01"
            spans[shot_id] = (cursor, cursor + scene_total)
            cursor += scene_total
            continue
        # Shots with spoken lines take their lines' durations;
        # action-only shots share the lead time equally.
        weights = []
        for shot in shots:
            ids = shot.get("spoken_line_ids") or []
            weights.append(sum(line_durations.get(i, 4.0) for i in ids)
                           if ids else None)
        n_action = sum(1 for w in weights if w is None)
        per_action = (lead / n_action) if n_action else 0.0
        weights = [per_action if w is None else w for w in weights]
        total_w = sum(weights) or 1.0
        for shot, weight in zip(shots, weights):
            shot_id = shot.get("id") or shot.get("shot_id")
            dur = scene_total * (weight / total_w)
            spans[str(shot_id)] = (cursor, cursor + dur)
            cursor += dur
    return spans, "estimated"


def compile_shot_expressions(package: dict) -> dict:
    """{shot_id: {raw, expression, negated, label}} for every V1 shot
    carrying an EXPRESSION field. Uses expression_library.interpret
    (negation-aware); labels with no match resolve to None, never to
    a guessed expression."""
    out: dict[str, dict] = {}
    for scene in package.get("scenes") or []:
        v1 = (scene or {}).get("v1_scene") or {}
        for shot in v1.get("shots") or []:
            shot_id = shot.get("id") or shot.get("shot_id")
            raw = shot.get("expression") or ""
            if not raw or not shot_id:
                continue
            from .expression_library import interpret_detailed
            detail = interpret_detailed(raw)
            out[str(shot_id)] = {
                "raw": raw,
                "expression": detail["expression"],
                "negated": detail["negated"],
                "label": detail["label"],
            }
    return out


def _gait_profile_index(package: dict) -> dict[str, object]:
    """Identity id -> gait_profile value from character data.

    The value is passed through verbatim (a preset name or a profile
    dict); locomotion.resolve_gait_profile validates it at render
    time. Characters without a gait_profile key are absent here --
    the renderer then uses the canonical gait. This is dormant until
    trait derivation supplies gait_profile (ATLAS spec); it adds no
    events and changes no existing event.
    """
    index: dict[str, object] = {}
    for key in ("characters", "v1_characters"):
        for char in package.get(key) or []:
            if not isinstance(char, dict):
                continue
            ident = char.get("identity_id") or char.get("id")
            if ident and "gait_profile" in char:
                index[str(ident)] = char["gait_profile"]
    return index


# Action type -> LocomotionState name (cinematic_contracts) for the
# locomotion_state event param. MARCH is a walk (its gait profile
# carries the march cadence/posture); STOP/IDLE/WAIT are holds.
_LOCOMOTION_STATES = {
    "WALK": "WALK",
    "RUN": "RUN",
    "MARCH": "WALK",
    "WALK_MUD": "TERRAIN_ADAPTATION",
    "TURN": "TURN",
    "STOP": "STOP_WALK",
    "IDLE": "IDLE",
    "WAIT": "IDLE",
}


# --- Contextual semantic resolution (A2, directive §3) -------------------
# Phrase-level + contextual interpretation: each directive sentence
# resolves to ONE SemanticAction (the 16-field record + origin /
# authority / authorization from semantic_contracts.py, imported
# here -- never a parallel record shape). This is NOT keyword soup
# and NOT the parser's ACTION_VERBS map: _classify supplies the verb
# family, and the disambiguation below decides the semantic type
# from the DISCRIMINATING context -- the source location for the
# take family (pocket vs ground vs surface), the body part for the
# cúi family (head vs torso), the named hand for receives. The
# seven normative EXAMPLE_RESOLUTIONS resolve on their context, and
# the "wrong" column of each row is unreachable for its phrase.
#
# One action per sentence, the same granularity as _classify: a
# sentence naming two actions resolves to the higher-priority one
# (the cue layer, which is multi-action per sentence, is separate
# and preserves both). Face-only sentences (brow raise, blink,
# expression hold), idle/wait, and pure pointing/raising have no
# SemanticAction type in the contract vocabulary and resolve to
# None -- they are expression/stance records, not story actions.
# A sentence whose actor cannot be resolved gets no record: the
# caller (compile_actions) owns actor resolution and supplies the
# actor id; resolve_semantic_action raises on a missing actor
# rather than inventing one.

_GROUND_SOURCE_PHRASES = (
    "dưới đất", "trên đất", "mặt đất", "dưới chân", "trên đường",
    "mặt đường", "trên mặt đất", "dưới đường",
)
_SURFACE_SOURCE_PHRASES = (
    "trên bàn", "trên ghế", "trên kệ", "mặt bàn", "trên bệ",
    "trên tủ", "trên mặt bàn",
)


def _semantic_source_location(normed: str):
    """pocket / ground / surface, from explicit source phrasing."""
    if (_has_any(normed, _POCKET_PHRASES)
            or _has_phrase(normed, "từ túi")
            or _has_phrase(normed, "ra khỏi túi")
            or _has_phrase(normed, "trong túi")):
        return "pocket"
    if _has_any(normed, _GROUND_SOURCE_PHRASES):
        return "ground"
    if _has_any(normed, _SURFACE_SOURCE_PHRASES):
        return "surface"
    return None


def _semantic_destination_location(normed: str, sem_type=None):
    """Destination from directional phrasing. Bare locatives
    ("dưới đất", "trên bàn") are sources in take sentences and
    destinations only for placement verbs, so they count only
    when the semantic type is a placement (PUT_AWAY). Directional
    phrases ("vào túi", "xuống đất", "lên xe") always count."""
    if _has_any(normed, ("vào túi", "bỏ túi")):
        return "pocket"
    if _has_any(normed, ("xuống đất", "xuống sàn")):
        return "ground"
    if _has_any(normed, ("lên bàn", "xuống bàn", "lên kệ", "xuống kệ")):
        return "surface"
    if _has_any(normed, ("lên xe", "vào xe")):
        return "vehicle"
    if sem_type in ("PUT_AWAY", "RELEASE_PROP", "PLACE_ON_SURFACE"):
        if _has_any(normed, ("dưới đất",)):
            return "ground"
        if _has_any(normed, ("trên bàn",)):
            return "surface"
        if _has_any(normed, ("trong túi",)):
            return "pocket"
    return None


def _semantic_hand(normed: str) -> str:
    """Interaction hand from explicit mention; NONE when unmentioned
    (the record states story meaning, not the engine's default
    hand -- the event params carry the engine default separately)."""
    if _has_any(normed, ("hai tay", "cả hai tay", "both hands")):
        return "BOTH"
    if _has_any(normed, ("tay phải", "right hand")):
        return "RIGHT"
    if _has_any(normed, ("tay trái", "left hand")):
        return "LEFT"
    return "NONE"


def _held_state(hand: str) -> str:
    return {"RIGHT": "HELD_RIGHT", "LEFT": "HELD_LEFT",
            "BOTH": "HELD_BOTH"}.get(hand, "HELD")


def _semantic_object_states(sem_type: str, hand: str, dest):
    """(before, after) in PropLocation/PropContainer vocabulary."""
    held = _held_state(hand)
    if sem_type == "TAKE_FROM_POCKET":
        return ("IN_POCKET", held)
    if sem_type == "TAKE_OUT":
        return (None, held)
    if sem_type in ("BEND_PICK", "PICK_FROM_GROUND"):
        return ("ON_GROUND", held)
    if sem_type == "PICK_FROM_SURFACE":
        return ("ON_SURFACE", held)
    if sem_type == "TAKE":
        return (None, held)
    if sem_type == "PUT_AWAY":
        after = {"pocket": "IN_POCKET", "ground": "ON_GROUND",
                 "surface": "ON_SURFACE"}.get(dest)
        return (held, after)
    if sem_type == "RELEASE_PROP":
        return (held, "ON_GROUND")
    if sem_type == "PLACE_ON_SURFACE":
        return (held, "ON_SURFACE")
    if sem_type == "OPEN":
        return ("CLOSED", "OPEN")
    if sem_type == "CLOSE":
        return ("OPEN", "CLOSED")
    if sem_type == "RECEIVE_PROP":
        return ("IN_TRANSIT", held)
    if sem_type in ("GIVE", "HAND_OVER"):
        return (held, "IN_TRANSIT")
    if sem_type == "HOLD":
        return (None, held)
    return (None, None)


_SEMANTIC_BODY_PARTS = {
    "HEAD_TILT_DOWN": "head",
    "CROUCH": "torso",
    "WAVE": "hand",
    "NOD": "head",
    "SHRUG": "shoulder",
    "WRITE": "hand",
    "SIGN": "hand",
    "HAMMER_STRIKE": "hand",
    "RECEIVE_PROP": "hand",
    "HOLD": "hand",
    "LOOK_AT": "head",
    "RELEASE_PROP": "hand",
    "PLACE_ON_SURFACE": "hand",
}


def _disambiguate_semantic(action_type, normed, match):
    """(semantic_type, rule_name, confidence) or None.

    The verb family comes from _classify; the discriminating
    context decides the semantic type. Confidence is 1.0 when the
    discriminating evidence is explicit in the sentence, 0.85 when
    the source is inferred from verb sense (bare "nhặt", "cúi
    xuống lấy") or the type came from the bare-"lấy" fallback.
    """
    mechanism = match.get("mechanism")
    if mechanism in ("gait_note", "display_verb", "non_character"):
        return None
    if action_type is None:
        return None
    if action_type == "HEAD_TILT":
        raising = _has_any(normed, ("ngẩng đầu", "ngẩng mặt"))
        looking = _has_any(normed, ("nhìn", "liếc", "ngó", "look"))
        if raising and not looking:
            # Head UP: the contract vocabulary has no HEAD_TILT_UP.
            return None
        if raising:
            return ("LOOK_AT", "raise_head_to_look", 1.0)
        return ("HEAD_TILT_DOWN", "head_tilt_down", 1.0)
    if action_type in ("KNEEL_PICK", "BEND_PICK"):
        ground = _has_any(normed, _GROUND_SOURCE_PHRASES)
        bent = _has_any(normed, ("cúi xuống", "cúi", "quỳ"))
        if action_type == "BEND_PICK" or bent:
            return ("BEND_PICK", "bend_pick",
                    1.0 if (ground or bent) else 0.85)
        return ("PICK_FROM_GROUND", "pick_from_ground",
                1.0 if ground else 0.85)
    if action_type == "TAKE_OUT":
        if _semantic_source_location(normed) == "pocket":
            return ("TAKE_FROM_POCKET", "take_from_pocket", 1.0)
        return ("TAKE_OUT", "take_out", 0.85)
    if action_type == "PICK_UP":
        src = _semantic_source_location(normed)
        if src == "surface":
            return ("PICK_FROM_SURFACE", "pick_from_surface", 1.0)
        if src == "ground":
            return ("PICK_FROM_GROUND", "pick_from_ground", 1.0)
        if src == "pocket":
            return ("TAKE_FROM_POCKET", "take_from_pocket", 1.0)
        conf = 0.85 if mechanism == "take_fallback" else 1.0
        return ("TAKE", "take", conf)
    if action_type == "PUT_AWAY":
        return ("PUT_AWAY", "put_away", 1.0)
    if action_type == "RELEASE":
        # Release destinations decide the semantic type: a drop
        # goes to the ground, a put-down to a surface, and a bare
        # put-down defaults to a surface (0.85 -- pocketing needs
        # the explicit "vào túi", which is PUT_AWAY's rule and
        # matches first). Never PUT_AWAY: the renderer pockets
        # PUT_AWAY and surfaces RELEASE.
        if _has_any(normed, ("đánh rơi", "làm rơi", "rơi khỏi tay",
                             "tuột khỏi tay", "xuống đất", "xuống sàn",
                             "dưới đất")):
            return ("RELEASE_PROP", "release_drop", 1.0)
        if _has_any(normed, ("xuống bàn", "lên bàn", "xuống kệ",
                             "lên kệ", "trên bàn", "xuống ghế")):
            return ("PLACE_ON_SURFACE", "release_place_surface", 1.0)
        return ("PLACE_ON_SURFACE", "release_put_down", 0.85)
    if action_type in ("OPEN_WALLET", "OPEN"):
        return ("OPEN", "open", 1.0)
    if action_type in ("CLOSE_WALLET", "CLOSE"):
        return ("CLOSE", "close", 1.0)
    if action_type in ("HOLD", "HOLD_PEN"):
        return ("HOLD", "hold", 1.0)
    if action_type == "WRITE":
        return ("WRITE", "write", 1.0)
    if action_type == "SIGN":
        return ("SIGN", "sign", 1.0)
    if action_type == "HAND_OVER":
        if _has_any(normed, ("trao tay", "chuyển giao", "bàn giao")):
            return ("HAND_OVER", "hand_over_transfer", 1.0)
        return ("GIVE", "give", 1.0)
    if action_type == "RECEIVE_PROP":
        return ("RECEIVE_PROP", "receive_prop", 1.0)
    if action_type == "CARRY":
        return ("CARRY", "carry", 1.0)
    if action_type == "CROUCH":
        return ("CROUCH", "crouch", 1.0)
    if action_type == "BOARD":
        return ("BOARD", "board", 1.0)
    if action_type == "HAMMER_STRIKE":
        return ("HAMMER_STRIKE", "hammer_strike", 1.0)
    if action_type in ("WALK", "WALK_MUD"):
        return ("WALK", "walk", 1.0)
    if action_type == "MARCH":
        return ("WALK", "march", 1.0)
    if action_type == "RUN":
        return ("RUN", "run", 1.0)
    if action_type == "STOP":
        return ("STOP", "stop", 1.0)
    if action_type == "TURN":
        return ("TURN", "turn", 1.0)
    if action_type == "LOOK_AT":
        return ("LOOK_AT", "look_at", 1.0)
    if action_type in ("SIT_DOWN", "SIT_AT_DESK"):
        return ("SIT", "sit", 1.0)
    if action_type in ("STAND_UP", "STAND_FROM_CHAIR"):
        return ("STAND", "stand", 1.0)
    if action_type == "WAVE":
        return ("WAVE", "wave", 1.0)
    if action_type == "NOD":
        return ("NOD", "nod", 1.0)
    if action_type == "SHRUG":
        return ("SHRUG", "shrug", 1.0)
    if action_type == "BREATHE":
        return ("BREATHE", "breathe", 1.0)
    if action_type == "REACT":
        return ("REACT", "react", 1.0)
    if action_type == "REACH":
        if _has_phrase(normed, "với lấy"):
            return ("TAKE", "reach_take", 0.85)
        return None
    # RAISE_HAND, POINT, COVER_FACE, face-only, IDLE/WAIT: no
    # SemanticAction type in the contract vocabulary.
    return None


def _resolve_semantic_target(normed, sem_type, prop_id, target_id,
                             prop_index, char_index):
    """Canonical target id: compiler-supplied ids win; mention
    indices serve standalone use; None when unresolvable (never a
    guessed name)."""
    if sem_type in ("GIVE", "HAND_OVER", "LOOK_AT", "TURN"):
        if target_id:
            return target_id
    elif prop_id:
        return prop_id
    if prop_index:
        best = None
        for mention, pid in prop_index.items():
            if mention and _has_phrase(normed, mention):
                if best is None or len(mention) > len(best[0]):
                    best = (mention, pid)
        if best is not None:
            return best[1]
    if char_index and sem_type in ("GIVE", "HAND_OVER"):
        match = re.search(r"\bcho\s+([a-zà-ỹ]+(?:\s+[a-zà-ỹ]+)?)",
                          normed)
        if match:
            name = match.group(1).strip()
            if name in char_index:
                return char_index[name]
            for key, ident in char_index.items():
                if key and name.startswith(key):
                    return ident
    return None


def resolve_semantic_action(sentence, *, actor_id, source_scene_id,
                            source_shot_id=None, source_directive_id=None,
                            prop_id=None, target_id=None,
                            classification=None, prop_index=None,
                            char_index=None):
    """Resolve one directive sentence to a SemanticAction, or None.

    ``actor_id`` is required (the caller owns actor resolution).
    ``classification`` is the (action_type, match_info) pair from
    _classify when the caller already classified the sentence (the
    compile path -- one classification per sentence); otherwise the
    sentence is classified with neutral context. ``prop_id`` /
    ``target_id`` are the compiler-resolved canonical ids when
    available; ``prop_index`` / ``char_index`` (mention -> id) serve
    standalone use.
    """
    if not actor_id:
        raise ValueError(
            "resolve_semantic_action requires actor_id: the caller "
            "owns actor resolution and no actor may be invented")
    if not source_scene_id:
        raise ValueError("source_scene_id is required")
    normed = _normalize(sentence)
    if classification is None:
        action_type, _cat, _notes, match = _classify(
            normed, {"locomotion": None, "seated": False})
    else:
        action_type, match = classification
    dis = _disambiguate_semantic(action_type, normed, match)
    if dis is None:
        return None
    sem_type, rule, confidence = dis
    hand = _semantic_hand(normed)
    source = _semantic_source_location(normed)
    if sem_type in ("BEND_PICK", "PICK_FROM_GROUND") and source is None:
        # Verb sense: nhặt / cúi-lấy takes from a low place.
        source = "ground"
    if sem_type == "TAKE_FROM_POCKET":
        source = "pocket"
    if sem_type == "PICK_FROM_SURFACE" and source is None:
        source = "surface"
    dest = _semantic_destination_location(normed, sem_type)
    body = _SEMANTIC_BODY_PARTS.get(sem_type)
    if sem_type == "REACT" and _has_phrase(normed, "vai"):
        body = "shoulder"
    spatial = None
    if sem_type == "CROUCH" and _has_any(normed, ("tránh", "né")):
        spatial = "avoidance"
    elif sem_type in ("HAMMER_STRIKE", "WRITE", "SIGN"):
        spatial = "contact"
    elif (sem_type == "HEAD_TILT_DOWN"
          and _has_phrase(normed, "nghiêng đầu")):
        spatial = "sideways"
    elif action_type == "WALK_MUD":
        spatial = "mud"
    elif action_type == "SIT_AT_DESK":
        spatial = "at_desk"
    intent = None
    if _has_any(normed, ("suy nghĩ", "suy tư", "trầm tư", "suy ngẫm")):
        intent = "thinking"
    elif _has_any(normed, ("tránh", "né tránh")):
        intent = "avoid"
    elif _has_phrase(normed, "chào"):
        intent = "greeting"
    elif action_type == "MARCH":
        intent = "march"
    before, after = _semantic_object_states(sem_type, hand, dest)
    tid = _resolve_semantic_target(normed, sem_type, prop_id,
                                   target_id, prop_index, char_index)
    return SemanticAction(
        actor_id=actor_id, action_type=sem_type, target_id=tid,
        source_location=source, destination_location=dest,
        body_part=body, interaction_hand=hand,
        object_state_before=before, object_state_after=after,
        spatial_relationship=spatial, action_intent=intent,
        source_scene_id=source_scene_id, source_shot_id=source_shot_id,
        source_directive_id=source_directive_id, source_text=sentence,
        confidence=confidence, provenance=f"phrase-rule:{rule}")


def resolve_semantic_actions(package, timeline=None):
    """Resolve every ACTION directive in a package to SemanticActions.

    Implemented through compile_actions (single actor-resolution
    path, by construction consistent with the compiled events).
    Sentences with no actor or no semantic type yield no record.
    """
    records: list = []
    compile_actions(package, timeline, semantic_sink=records)
    return records


def _inference_reason(match_info: dict, action_type) -> str:
    """Human-readable reason naming what decided the classification."""
    mechanism = match_info.get("mechanism")
    phrase = match_info.get("phrase")
    detail = match_info.get("detail") or ""
    if mechanism == "rule":
        return f"classification rule {action_type}: phrase {phrase!r}"
    if mechanism == "take_fallback":
        return f"bare-'lấy' fallback {phrase!r} -> {action_type}"
    if mechanism == "discontinuous":
        return f"discontinuous verb pattern {phrase!r} -> {action_type}"
    if mechanism == "sway":
        return f"sway pattern {phrase!r} -> CARRY"
    if mechanism == "gait_note":
        return f"gait/quality note {phrase!r}: {detail}"
    if mechanism in ("display_verb", "non_character"):
        return detail or f"non-character sentence ({phrase!r})"
    return detail or f"directive sentence -> {action_type}"


def compile_actions(scene_package: dict, timeline: dict | None = None,
                    inferred_cues=None, semantic_sink=None,
                    conflict_sink=None):
    """Compile every ACTION directive into events + unsupported.

    See the module docstring for the exact output contract. Every
    event and unsupported entry carries the provenance contract
    (source_script_hash / source_scene_id / source_shot_id /
    source_directive_id / action_origin / inference_reason /
    authorization_status) plus semantic_action_type. When
    ``semantic_sink`` (a list) is supplied, the resolved
    SemanticAction records are appended to it. When ``inferred_cues``
    (detailed cue records) is supplied, the conflict mechanism runs
    before the return: unresolved mandatory conflicts raise
    UnauthorizedStoryChange, and every ConflictRecord found is
    appended to ``conflict_sink`` when one is supplied. None (the
    default) leaves existing callers unchanged.
    """
    package = scene_package or {}
    fp = _first_person_info(package)
    char_map, extras = _character_index(package)
    gait_profiles = _gait_profile_index(package)
    _props, prop_terms = _prop_index(package)
    shot_expressions = compile_shot_expressions(package)
    spans, time_source = _shot_spans(package, timeline)
    script_hash = _script_hash(package)
    # Directives whose span came from the caller's explicit spans
    # dict drive at least one rendered shot; every other directive
    # falls back to a (0, 0) span with sequential estimates from
    # t=0, and its events render nowhere. The per-event span_source
    # flag lets the renderer (cross-shot prop memory, seated-state
    # carry-over) and the P9 audit tell the two apart: phantom
    # times from unrendered directives must never poison state
    # that real rendered shots depend on.
    _raw_spans = (timeline or {}).get("spans")
    supplied_ids = set(_raw_spans) if isinstance(_raw_spans, dict) \
        else set()

    # Group sentences by shot, preserving script order.
    by_shot: dict[str, list[dict]] = {}
    shot_order: list[str] = []
    shot_meta: dict[str, dict] = {}
    for number, shot_id, shot, sentence, line in _iter_action_sentences(
            package):
        key = str(shot_id) if shot_id else f"SC{int(number or 0):02d}_SH01"
        if key not in by_shot:
            by_shot[key] = []
            shot_order.append(key)
            shot_meta[key] = {"scene_number": number, "shot": shot}
        by_shot[key].append({"sentence": sentence, "line": line})

    events: list[dict] = []
    unsupported: list[dict] = []
    semantic_records: list = []
    # Cross-shot compiler state (per scene): seated actors + last
    # locomotion type, for sit/stand pairing and gait notes.
    scene_state: dict[int, dict] = {}

    for shot_id in shot_order:
        items = by_shot[shot_id]
        number = shot_meta[shot_id]["scene_number"]
        state = scene_state.setdefault(
            int(number or 0), {"seated": set(), "locomotion": None,
                               "last_actor": None})
        span = spans.get(shot_id)
        if span is None:
            # Scene-level actions with no shot span: use the scene's
            # first shot span, else a zero span (events still get
            # sequential estimates from t=0 of the scene).
            span = (0.0, 0.0)
        shot_start, shot_end = span
        shot_span = max(shot_end - shot_start, 0.0)
        expression = (shot_expressions.get(shot_id) or {}).get("expression")
        # Receiver hand for this shot's handovers: the first hand
        # mention in the shot's sentences ("tay phải" / "tay trái"),
        # else the engine default "l".
        receive_hand = _receive_hand_from_text(
            " ".join(item["sentence"] for item in items))

        # First pass: classify + resolve, collecting durations.
        planned: list[dict] = []
        for ordinal, item in enumerate(items, 1):
            sentence = item["sentence"]
            normed = _normalize(sentence)
            action_id = f"{shot_id}_ACT{ordinal:02d}"
            action_type, category, notes, match = _classify(normed, {
                "locomotion": state["locomotion"],
                "seated": bool(state["seated"]),
            })
            if action_type is None:
                unsupported.append({
                    "action_id": action_id,
                    "reason": _unsupported_reason(category, sentence),
                    "directive_text": sentence,
                    "category": category,
                    "shot_id": shot_id,
                    "scene_number": number,
                    "source_line": item["line"],
                    "source_script_hash": script_hash,
                    "source_scene_id": _scene_id(number),
                    "source_shot_id": shot_id,
                    "source_directive_id": action_id,
                    "action_origin":
                        ActionOrigin.UNSUPPORTED_ACTION.value,
                    "inference_reason": _inference_reason(match, None),
                    "authorization_status":
                        AuthorizationStatus.REJECTED.value,
                    "semantic_action_type": None,
                })
                continue
            # Semantic role resolution (positional: the subject
            # before the verb is the actor; a "cho + name"
            # complement is the recipient, never the actor -- see
            # resolve_sentence_roles).
            roles = resolve_sentence_roles(
                sentence, normed=normed, char_map=char_map,
                extras=extras, action_type=action_type, match=match,
                primary_character=fp["primary_character"],
                first_person_enabled=fp["enabled"],
                carry_actor=state["last_actor"])
            actor_id = roles["actor_id"]
            notes.extend(roles["notes"])
            if actor_id is None:
                unsupported.append({
                    "action_id": action_id,
                    "reason": "no actor resolvable from the sentence, "
                              "the shot or the scene",
                    "directive_text": sentence,
                    "category": "NO_ACTOR",
                    "shot_id": shot_id,
                    "scene_number": number,
                    "source_line": item["line"],
                    "source_script_hash": script_hash,
                    "source_scene_id": _scene_id(number),
                    "source_shot_id": shot_id,
                    "source_directive_id": action_id,
                    "action_origin":
                        ActionOrigin.UNSUPPORTED_ACTION.value,
                    "inference_reason": _inference_reason(
                        match, action_type),
                    "authorization_status":
                        AuthorizationStatus.REJECTED.value,
                    "semantic_action_type": None,
                })
                continue
            state["last_actor"] = actor_id
            # Prop + target resolution.
            prop_id = _resolve_prop(normed, prop_terms, action_type)
            giver_id = None
            paired_handover_id = None
            if action_type == "RECEIVE_PROP":
                # A receive completes the transfer the shot already
                # directed: pair it with the shot's earlier
                # HAND_OVER (backward-only -- the giver sentence
                # precedes the receiver sentence in directive
                # order). The pairing records the giver for the
                # ownership transition whether or not the prop is
                # declared; the prop itself is inherited only when
                # the receive names none ("Zeus nhận bằng tay
                # phải") and the handover carries one.
                for prior in reversed(planned):
                    if prior["action_type"] == "HAND_OVER":
                        giver_id = prior["actor_id"]
                        paired_handover_id = prior["action_id"]
                        if prop_id is None and prior["prop_id"]:
                            prop_id = prior["prop_id"]
                            notes.append(
                                "receive inherits the shot's handover "
                                "prop (no prop named in this sentence)")
                        break
            # Target / recipient from the same positional
            # resolution (one role decision per sentence -- the
            # target cannot disagree with the actor about who did
            # what to whom).
            target_id = roles["target_id"]
            if action_type == "HAND_OVER":
                recipient_id = target_id
            elif action_type == "RECEIVE_PROP":
                recipient_id = actor_id
            else:
                recipient_id = None
            # Paper for WRITE/SIGN: the letter/document prop when one
            # is named or when the package has exactly one paper-like
            # prop; else None (staging supplies the paper).
            paper_id = None
            if action_type in ("WRITE", "SIGN"):
                paper_id = _paper_prop(normed, prop_terms, package)
                if prop_id is None:
                    prop_id = _pen_prop(prop_terms, package)
            if action_type in ("WALK", "RUN", "MARCH", "WALK_MUD"):
                state["locomotion"] = action_type
            if action_type == "SIT_AT_DESK":
                state["seated"].add(actor_id)
            if action_type in ("STAND_FROM_CHAIR", "STAND_UP"):
                state["seated"].discard(actor_id)
            if match["mechanism"] == "gait_note":
                origin = ActionOrigin.SAFE_SUPPORTING_ACTION.value
            else:
                origin = ActionOrigin.EXPLICIT_SCRIPT_ACTION.value
            status = AuthorizationStatus.AUTHORIZED.value
            # One semantic resolution per directive, reusing this
            # pass's classification + actor/prop/target ids (single
            # resolution path -- the record cannot disagree with the
            # event about who did what to which prop).
            # No scene id (synthetic/legacy packages) -> no
            # semantic record: the record requires provenance and
            # must never be built on an invented id.
            scene_id = _scene_id(number)
            semantic = None
            if scene_id:
                semantic = resolve_semantic_action(
                    sentence, actor_id=actor_id,
                    source_scene_id=scene_id,
                    source_shot_id=shot_id,
                    source_directive_id=action_id,
                    prop_id=prop_id, target_id=target_id,
                    classification=(action_type, match))
            if semantic is not None:
                semantic_records.append(semantic)
            planned.append({
                "action_id": action_id, "actor_id": actor_id,
                "action_type": action_type, "target_id": target_id,
                "prop_id": prop_id, "paper_id": paper_id,
                "recipient_id": recipient_id,
                "giver_id": giver_id,
                "paired_handover_id": paired_handover_id,
                "sentence": sentence, "line": item["line"],
                "notes": notes,
                "duration": ACTION_DURATIONS[action_type],
                "pocket": _pocket_mentioned(normed),
                "action_origin": origin,
                "authorization_status": status,
                "inference_reason": _inference_reason(
                    match, action_type),
                "semantic_action_type":
                    semantic.action_type if semantic else None,
            })

        # Second pass: layout in time + dependencies.
        total = sum(p["duration"] for p in planned)
        overflow = False
        if planned and shot_span > 0.0 and total > shot_span:
            floors = MIN_EVENT_SEC * len(planned)
            if floors > shot_span:
                overflow = True
                scale = 1.0  # keep floors; events overrun the span
            else:
                scale = shot_span / total
        else:
            scale = 1.0
        cursor = shot_start
        prev_by_actor: dict[str, str] = {}
        last_prop_event: dict[str, str] = {}
        last_by_type: dict[str, str] = {}
        for plan in planned:
            dur = max(MIN_EVENT_SEC, plan["duration"] * scale)
            start = cursor
            end = cursor + dur
            cursor = end
            primitive, _default, completion_kind = PRIMITIVE_MAP[
                plan["action_type"]]
            hand = "r"
            if plan["action_type"] in ("OPEN_WALLET", "CLOSE_WALLET"):
                hand = "both"
            elif plan["action_type"] == "RECEIVE_PROP":
                # The receiving hand: the receive sentence's own hand
                # mention wins (it names the receiver's hand); else
                # the shot's receiver hand (which defaults to "l").
                # Without this, a left-hand receive staged the prop
                # at the right hand -- the PSM attachment and the
                # receive primitive both read this param.
                mentioned = _hand_mentioned(plan["sentence"])
                hand = mentioned if mentioned is not None \
                    else receive_hand
            params: dict = {"hand": hand}
            if plan["action_type"] == "SIT_AT_DESK":
                params["furniture"] = "desk"
            if plan["action_type"] in ("TAKE_OUT", "PUT_AWAY"):
                params["pocket"] = bool(plan["pocket"])
            if plan["action_type"] == "WRITE":
                params["paper_id"] = plan["paper_id"]
            if plan["action_type"] == "SIGN":
                params["paper_id"] = plan["paper_id"]
            if plan["action_type"] == "REACT":
                params["kind"] = _react_kind(plan["sentence"])
            if plan["action_type"] in ("EXPRESSION_HOLD", "BROW_RAISE",
                                       "BLINK"):
                params["expression"] = expression
            if plan["action_type"] in _LOCOMOTION_STATES:
                params["locomotion_state"] = _LOCOMOTION_STATES[
                    plan["action_type"]]
            if plan["action_type"] == "HAND_OVER":
                params["receive_hand"] = receive_hand
            if plan["actor_id"] in gait_profiles:
                params["gait_profile"] = gait_profiles[plan["actor_id"]]
            deps: list[str] = []
            prev = prev_by_actor.get(plan["actor_id"])
            if prev:
                deps.append(prev)
            if plan["prop_id"]:
                last = last_prop_event.get(plan["prop_id"])
                if last and last not in deps:
                    deps.append(last)
            if plan["action_type"] in ("WRITE", "SIGN"):
                for dep_type in ("HOLD_PEN", "SIT_AT_DESK"):
                    dep = last_by_type.get(dep_type)
                    if dep and dep not in deps:
                        deps.append(dep)
            if plan["action_type"] == "HAND_OVER":
                for dep_type in ("PICK_UP", "HOLD", "TAKE_OUT"):
                    dep = last_by_type.get(dep_type)
                    if dep and dep not in deps:
                        deps.append(dep)
            if plan["action_type"] in ("PUT_AWAY", "RELEASE"):
                for dep_type in ("PICK_UP", "HOLD", "HOLD_PEN",
                                 "TAKE_OUT", "WRITE", "SIGN"):
                    dep = last_by_type.get(dep_type)
                    if dep and dep not in deps:
                        deps.append(dep)
            if plan["action_type"] == "CLOSE_WALLET":
                dep = last_by_type.get("OPEN_WALLET")
                if dep and dep not in deps:
                    deps.append(dep)
            if plan["action_type"] == "STAND_FROM_CHAIR":
                dep = last_by_type.get("SIT_AT_DESK")
                if dep and dep not in deps:
                    deps.append(dep)
            completion = {
                "state": completion_kind,
                "details": _completion_details(plan),
            }
            events.append({
                "action_id": plan["action_id"],
                "actor_id": plan["actor_id"],
                "action_type": plan["action_type"],
                "target_id": plan["target_id"],
                "prop_id": plan["prop_id"],
                "start_time": round(start, 3),
                "end_time": round(end, 3),
                "required_pose": {
                    "primitive": primitive,
                    "params": params,
                    "completion": _completion_text(plan["action_type"]),
                },
                "contact_points": _contact_points(
                    plan["action_type"], hand if hand != "both" else "r",
                    plan["prop_id"], plan["target_id"], plan["paper_id"],
                    target_hand=(receive_hand
                                 if plan["action_type"] == "HAND_OVER"
                                 else None)),
                "animation_dependencies": deps,
                "completion_state": completion,
                "shot_id": shot_id,
                "scene_number": number,
                "directive_text": plan["sentence"],
                "expression": expression,
                "time_source": time_source,
                "source_script_hash": script_hash,
                "source_scene_id": _scene_id(number),
                "source_shot_id": shot_id,
                "source_directive_id": plan["action_id"],
                "action_origin": plan["action_origin"],
                "inference_reason": plan["inference_reason"],
                "authorization_status": plan["authorization_status"],
                "semantic_action_type": plan["semantic_action_type"],
                "span_source": ("supplied" if shot_id in supplied_ids
                                else "estimated"),
                "notes": plan["notes"],
                "overflow": overflow,
                "source_line": plan["line"],
            })
            if plan["action_type"] in ("HAND_OVER", "RECEIVE_PROP"):
                # Transfer record: giver, receiver, receiving hand
                # and the ownership transition (sprint section 5).
                # A counterpart that is not directed stays None --
                # ownership is never invented.
                record = {
                    "recipient_id": plan["recipient_id"],
                    "ownership_before": (
                        plan["actor_id"]
                        if plan["action_type"] == "HAND_OVER"
                        else plan["giver_id"]),
                    "ownership_after": plan["recipient_id"],
                    "recipient_hand": (
                        receive_hand
                        if plan["action_type"] == "HAND_OVER"
                        else hand),
                }
                if plan["action_type"] == "RECEIVE_PROP":
                    record["paired_handover_id"] = \
                        plan["paired_handover_id"]
                events[-1].update(record)
            prev_by_actor[plan["actor_id"]] = plan["action_id"]
            if plan["prop_id"]:
                last_prop_event[plan["prop_id"]] = plan["action_id"]
            last_by_type[plan["action_type"]] = plan["action_id"]

    if semantic_sink is not None:
        semantic_sink.extend(semantic_records)
    if inferred_cues is not None:
        found = check_cue_authorization(events, inferred_cues,
                                        unsupported)
        if conflict_sink is not None:
            conflict_sink.extend(found)

    return events, unsupported


def _unsupported_reason(category: str | None, sentence: str) -> str:
    reasons = {
        "MAP": "map/geography directive: handled by the map renderer, "
               "not a character action",
        "CAMERA": "camera/framing directive: handled by the camera "
                  "stage, not a character action",
        "ENVIRONMENT": "environment/weather directive: handled by the "
                       "environment engine, not a character action",
        "AUDIO": "audio directive: handled by the audio stage, not a "
                 "character action",
        "DIALOGUE": "dialogue-delivery note: expression is carried by "
                    "the spoken line's EXPRESSION field",
        "COSTUME_STATE": "costume/state description: no animation "
                         "primitive changes costume state",
        "UNCLEAR": "no action mapping for this scripted sentence",
        "NO_ACTOR": "no actor resolvable from the sentence, the shot "
                    "or the scene",
    }
    return reasons.get(category or "UNCLEAR",
                       "no action mapping for this scripted sentence")


def _paper_prop(normed: str, prop_terms: dict, package: dict):
    """The paper-like prop for WRITE/SIGN: a named letter/document
    prop, else the package's only paper-like prop, else None."""
    for pid, words in prop_terms.items():
        prop = next((p for p in package.get("props") or []
                     if (p.get("id") or p.get("name")) == pid), None)
        kind = str((prop or {}).get("kind") or "").lower()
        if kind in ("letter", "document", "paper", "form"):
            if any(_has_phrase(normed, w) for w in words):
                return pid
    paper_like = []
    for prop in package.get("props") or []:
        kind = str(prop.get("kind") or "").lower()
        if kind in ("letter", "document", "paper", "form"):
            paper_like.append(prop.get("id") or prop.get("name"))
    if len(paper_like) == 1:
        return paper_like[0]
    return None


def _pen_prop(prop_terms: dict, package: dict):
    """The package's pen prop id, when exactly one exists."""
    pens = [prop.get("id") or prop.get("name")
            for prop in package.get("props") or []
            if str(prop.get("kind") or "").lower() == "pen"]
    return pens[0] if len(pens) == 1 else None


def _react_kind(sentence: str) -> str:
    normed = _normalize(sentence)
    if _has_any(normed, ("cúi người", "duck", "ngồi xổm")):
        return "duck"
    if _has_any(normed, ("vai co", "che mặt", "flinch")):
        return "flinch"
    return "startle"


def _completion_details(plan: dict) -> dict:
    details: dict = {}
    if plan["prop_id"]:
        details["prop_id"] = plan["prop_id"]
    if plan["action_type"] == "OPEN_WALLET":
        details["open_u"] = 1.0
    if plan["action_type"] == "CLOSE_WALLET":
        details["open_u"] = 0.0
    if plan["action_type"] == "SIGN":
        details["signed"] = True
        if plan["paper_id"]:
            details["paper_id"] = plan["paper_id"]
    if plan["action_type"] == "WRITE" and plan["paper_id"]:
        details["paper_id"] = plan["paper_id"]
    if plan["action_type"] == "HAND_OVER":
        details["holder"] = plan["target_id"]
    if plan["action_type"] in ("TAKE_OUT", "PUT_AWAY"):
        details["pocket"] = bool(plan["pocket"])
    if plan["action_type"] == "RELEASE":
        details["released"] = True
        details["rest"] = "surface"
    return details


def _completion_text(action_type: str) -> str:
    primitive, _d, state = PRIMITIVE_MAP[action_type]
    return f"{primitive} completion pose; {state}"
