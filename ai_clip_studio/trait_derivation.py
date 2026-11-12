"""Deterministic trait derivation and SPEC section 15 trait blocks.

Single source of truth shared by the fallback planner, the Gemini
planner and the STUDIO SCRIPT V1 adapter. Everything here is derived
from the script's own data with generic rules -- no per-script code,
no character/location/prop names from any particular story.

This module is stdlib-only and imports nothing from the engine: the
parser/planner layer must never import the heavy renderer. Vocabularies
that mirror engine constants (PROP_KINDS, SFX events, PRIMITIVES keys,
face-system expression names, colour words) are duplicated here with
sync tests asserting they stay identical to the engine originals.

Word-boundary rule: text scans that decide identity (moustache,
gender, age, glasses) match whole words only, never substrings. The
substring scan that once read a moustache out of an unrelated word
containing "ria" must never be reproduced here.

Head ratio is locked to 0.34. Trait data must never carry any other
value; anything else is dropped with a note by validate_trait_blocks
and coerced to 0.34 by the block builders.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

HEAD_RATIO_LOCKED = 0.34

# --- Closed vocabularies (SPEC section 15) ---------------------------

TEMPLATES = ("male", "female", "child", "elderly")
BODY_VARIANTS = ("slim", "standard", "sturdy")
COSTUME_GARMENTS = ("none", "dress", "uniform")
HAIR_STYLES = ("short", "long", "tuft", "side_part", "none")
HATS = ("none", "bowler")
MOUSTACHE_STYLES = ("none", "toothbrush", "handlebar", "full")
LOCATION_KEYWORDS = (
    "great_wall", "eiffel_tower", "rainy_street", "street", "generic")
MOODS = ("warm", "cold")
TIMES_OF_DAY = ("day", "night")
SHOT_TYPES = (
    "establishing", "medium", "close_up", "extreme_close_up",
    "over_the_shoulder", "reaction", "object_insert", "tracking",
    "shot_reverse_shot",
    # Stage 3 / channel-study vocabulary (R1/R6), mirroring
    # camera_planner.SHOT_TYPES exactly.
    "medium_close_up", "graphic_insert",
)
CAMERA_MOVEMENTS = (
    "STATIC", "PAN_LEFT", "PAN_RIGHT", "TILT_UP", "TILT_DOWN",
    "DOLLY_IN", "DOLLY_OUT", "TRACKING", "CRANE_UP", "CRANE_DOWN",
    "HANDHELD",
)
MUSIC_INTENSITIES = ("LOW", "MEDIUM", "HIGH")

# Planner SFX event vocabulary (SPEC section 15.4). Mirror of the
# foley/ambience keys of audio_events.EVENT_SFX_MAP minus the
# "crowd murmur" ambience entry, which is not a planner SFX event; a
# sync test asserts the relationship.
SFX_EVENTS = frozenset({
    "rain_start", "foot_contact", "door_contact", "door_rotation",
    "paper_movement", "object_impact", "character_reaction",
})

# Drawable prop kinds. Mirror of product_renderer.PROP_KINDS (the
# engine agent defines it); a sync test asserts the two stay
# identical. "generic" is the drawable fallback for props with no
# specific kind (for example a pen).
PROP_KINDS = frozenset({
    "wallet", "umbrella", "newspaper", "letter", "ticket", "cup",
    "bag", "key", "book", "flower", "pen", "generic",
})

# The sixteen keys of animation/primitives.PRIMITIVES (authoritative
# list; functions that exist but are NOT in the registry, such as
# detour_walk and board_vehicle, are deliberately absent). A sync
# test asserts this stays identical to PRIMITIVES.
PRIMITIVE_NAMES = frozenset({
    "walk_to", "run_to", "turn_to", "look_at", "point_at", "wave",
    "reach_to", "give_to", "shrug", "cover_face", "nod", "sit_down",
    "stand_up", "idle", "bend_pick", "kneel_pick",
})

# Face-system expression names (animation/character_art.EXPRESSIONS).
# A sync test asserts this stays identical.
EXPRESSION_NAMES = (
    "neutral", "happy", "sad", "surprised", "worried", "angry",
    "thinking", "doubtful",
)

# Camera angle vocabulary. Mirror of camera_planner.ANGLES (the
# engine owns viewpoint execution; this layer only emits the label).
# A sync test asserts the two stay identical. PROVISIONAL (C9): the
# data side of the camera-angle fix, pending reconciliation with the
# independent camera audit's fix spec.
CAMERA_ANGLES = (
    "eye_level", "low_angle", "high_angle", "dutch",
    "over_shoulder", "birds_eye",
)

# Default camera angle per shot type. Mirror of
# camera_planner._ANGLE_BY_SHOT (same sync-test pattern): an
# establishing shot looks down from high, an object insert looks
# down at the object, an over-the-shoulder shot uses the shoulder
# angle, everything else stays at eye level. Explicit angle words in
# the script's CAMERA text override this table.
DEFAULT_ANGLE_BY_SHOT = {
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

# Generic colour-word map. Mirror of planner_fallback.COLOR_WORDS
# (same order, same substring semantics); a sync test asserts the
# two stay identical. Kept here so this module stays dependency-free.
COLOR_WORDS: list[tuple[str, str]] = [
    ("xanh đậm", "#1d3a5f"), ("xanh dương", "#2b5ea7"), ("xanh lá", "#2e7d4f"),
    ("màu be", "#c9b18c"), ("be", "#c9b18c"), ("nâu", "#7a4a2b"),
    ("đen", "#222222"), ("đỏ", "#b03a2e"), ("vàng", "#d9a441"),
    ("trắng", "#f3f0e8"), ("xám", "#6b7280"), ("hồng", "#d98a9e"),
]
DEFAULT_JACKET_COLOR = "#3a4a5f"

# Planner duration hints (seconds) for special-action directives.
# Hints only: the timeline stage reconciles them with real speech
# timing (SPEC section 15.5).
ACTION_DURATION_HINTS: dict[str, float] = {
    "walk_to": 1.6, "run_to": 1.2, "turn_to": 0.35, "look_at": 0.8,
    "point_at": 0.8, "wave": 1.2, "reach_to": 1.0, "give_to": 1.5,
    "shrug": 0.8, "cover_face": 1.0, "nod": 0.6, "sit_down": 0.8,
    "stand_up": 0.8, "idle": 1.0, "bend_pick": 1.2, "kneel_pick": 1.2,
}

_JACKET_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


# --- Text helpers ----------------------------------------------------

def _norm(text: str) -> str:
    """Lowercase, underscores/hyphens to spaces, whitespace collapsed.

    Makes SNAKE_CASE tokens (block ids, camera values) match the same
    word-boundary scans as plain prose.
    """
    return " ".join((text or "").lower().replace("_", " ").replace("-", " ").split())


def _normalize_name(name: str) -> str:
    return " ".join((name or "").strip().casefold().split())


def _has_word(text: str, word: str) -> bool:
    return re.search(r"\b" + re.escape(word) + r"\b", text or "") is not None


def _has_any_word(text: str, words) -> bool:
    return any(_has_word(text, w) for w in words)


def _field(fields, key: str):
    """Case-insensitive lookup in a verbatim fields dict.

    Returns None when fields is not a dict or the key is absent.
    """
    if not isinstance(fields, dict):
        return None
    wanted = key.strip().casefold()
    for k, v in fields.items():
        if str(k).strip().casefold() == wanted:
            return v
    return None


def _field_text(fields, key: str) -> str:
    value = _field(fields, key)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return str(value)


def snapshot_hash_for_text(text: str) -> str:
    """SHA-256 of the exact input text (fallback/free-form snapshot)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def parse_duration_seconds(value, default=None):
    """Parse a duration value to seconds (float) or return default.

    Accepts numbers, "3", "3s", "0.6s", "350ms" (case-insensitive).
    "AUTO" and anything unparseable return the default. Never raises.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if not text or text == "auto":
        return default
    try:
        if text.endswith("ms"):
            return float(text[:-2].strip()) / 1000.0
        if text.endswith("s"):
            return float(text[:-1].strip())
        return float(text)
    except ValueError:
        return default


# --- Voice hint ------------------------------------------------------

_FEMALE_MARKERS = ("bà", "cô", "chị", "mẹ", "dì", "nữ", "gái")
_MALE_MARKERS = ("ông", "chàng", "cậu", "anh trai", "bác trai")


def _parse_gender(gender: str):
    """Structured GENDER value -> "male" | "female" | None."""
    text = (gender or "").strip().lower()
    if text in ("male", "man", "boy", "nam", "m", "ông"):
        return "male"
    if text in ("female", "woman", "girl", "nữ", "nu", "f", "bà"):
        return "female"
    return None


def derive_voice_hint(name: str, role: str, appearance: str,
                      voice_style: str, gender: str = "") -> str:
    """Pipeline voice_hint from the script's own character text.

    Returns exactly "giọng nam", "giọng nữ", or "" (default voice).
    Never returns a raw voice id: the voice resolvers match
    substrings, so a raw id could misfire. Precedence: an explicit
    "giọng nam"/"giọng nữ" phrase, then the structured GENDER field,
    then word-boundary honorifics. Bare "nam" in a name never fires.
    """
    combined = " ".join(
        p for p in (name, role, appearance, voice_style) if p).lower()
    if "giọng nữ" in combined:
        return "giọng nữ"
    if "giọng nam" in combined:
        return "giọng nam"
    parsed = _parse_gender(gender)
    if parsed == "female":
        return "giọng nữ"
    if parsed == "male":
        return "giọng nam"
    female = _has_any_word(combined, _FEMALE_MARKERS)
    male = _has_any_word(combined, _MALE_MARKERS)
    if female and not male:
        return "giọng nữ"
    if male and not female:
        return "giọng nam"
    return ""


# --- Character render traits -----------------------------------------

_ELDERLY_MARKERS = (
    "già", "lão", "elderly", "cụ già", "ông cụ", "bà cụ", "lớn tuổi",
    "cao tuổi", "tuổi già", "old man", "old woman", "senior",
    "người già",
)
_CHILD_MARKERS = (
    "trẻ em", "em bé", "đứa trẻ", "bé", "con nít", "thiếu nhi",
    "child", "kid", "cậu bé", "cô bé", "bé trai", "bé gái",
)
# "trẻ" alone is NOT a child marker: "cô gái trẻ" is a young woman,
# not a child. Only explicit child phrases count.
_FEMALE_TEMPLATE_MARKERS = (
    "bà", "cô", "chị", "mẹ", "dì", "nữ", "gái", "phụ nữ", "female",
    "woman", "girl", "thiếu nữ",
)
_SLIM_MARKERS = ("gầy", "mảnh", "mảnh khảnh", "slim", "thin", "slender",
                 "ốm", "nhỏ con")
_STURDY_MARKERS = ("to lớn", "vạm vỡ", "mập", "béo", "sturdy", "to con",
                   "đô con", "stocky", "heavyset", "cơ bắp")
_UNIFORM_MARKERS = ("quân phục", "đồng phục", "uniform", "quân đội",
                    "bộ đội", "lính", "military uniform")
_DRESS_MARKERS = ("váy", "dress", "áo dài", "đầm", "gown")
_GLASSES_MARKERS = ("đeo kính", "kính mắt", "kính cận", "kính râm",
                    "mắt kính", "gọng kính", "glasses", "spectacles",
                    "kính lão")
# Standalone "kính" is NOT a glasses marker: it is also a respectful
# form of address ("kính thưa"). Only compounds count.
_HAT_MARKERS = ("bowler", "mũ nồi", "mũ quả dưa", "mũ phớt")


def _jacket_color_from_text(text: str) -> str:
    low = (text or "").lower()
    for word, color in COLOR_WORDS:
        if word in low:
            return color
    return DEFAULT_JACKET_COLOR


def _hair_style(scan_text: str) -> str:
    if _has_any_word(scan_text, ("hói", "bald", "không tóc", "trọc")):
        return "none"
    if _has_any_word(scan_text, ("side part", "sidepart", "rẽ ngôi",
                                 "ngôi lệch", "side parted")):
        return "side_part"
    if _has_any_word(scan_text, ("tóc dài", "long hair", "mái tóc dài",
                                 "tóc xoã", "tóc xõa")):
        return "long"
    if _has_any_word(scan_text, ("tuft", "chỏm", "tóc chỏm")):
        return "tuft"
    return "short"


def _moustache_from_scan(scan_text: str) -> str:
    """Moustache style from prose text, word-boundary only.

    Generic moustache words without a style qualifier map to "full".
    Substring matches are forbidden: "Bavarian" contains "ria" but is
    not a moustache.
    """
    if _has_any_word(scan_text, ("toothbrush", "ria mép nhỏ",
                                 "ria con kiến", "ria ngắn")):
        return "toothbrush"
    if _has_any_word(scan_text, ("handlebar", "ria quặp", "ria vểnh",
                                 "ria xoắn")):
        return "handlebar"
    if _has_any_word(scan_text, ("râu rậm", "râu đầy", "râu quai nón",
                                 "full beard", "râu dài", "beard")):
        return "full"
    if _has_any_word(scan_text, ("râu", "ria", "moustache", "mustache",
                                 "ria mép")):
        return "full"
    return "none"


_MOUSTACHE_NONE_WORDS = (
    "none", "no moustache", "clean", "clean shaven", "clean-shaven",
    "không râu", "không có râu", "no facial hair",
)


def moustache_style_from_fields(fields) -> tuple[str | None, str | None]:
    """Moustache style from an explicit MOUSTACHE field.

    Returns (style, note): style is None when the field is absent or
    empty (caller falls back to the prose scan); note is set when the
    field is present without a style word and "full" is assumed, so
    the caller can record the assumption. An explicit none value
    returns ("none", None) and wins over any prose scan.
    """
    raw = _field_text(fields, "MOUSTACHE").strip()
    if not raw:
        return None, None
    text = _norm(raw)
    if _has_any_word(text, _MOUSTACHE_NONE_WORDS) or text in ("no", "none"):
        return "none", None
    style = _moustache_from_scan(text)
    if style == "none":
        # The field names a moustache (its presence is the claim) but
        # no style word is recognisable: assume "full" and say so.
        if _has_any_word(text, ("moustache", "mustache", "râu", "ria")):
            return "full", (
                "MOUSTACHE field present without an explicit style "
                "word; moustache_style defaulted to 'full'")
        return "full", (
            "MOUSTACHE field present without a recognisable style "
            "word; moustache_style defaulted to 'full'")
    if style == "full" and not _has_any_word(
            text, ("râu rậm", "râu đầy", "râu quai nón", "full beard",
                   "râu dài", "beard")):
        return "full", (
            "MOUSTACHE field present without an explicit style "
            "word; moustache_style defaulted to 'full'")
    return style, None


def _body_variant(scan_text: str, body_type_text: str) -> str:
    combined = _norm(f"{body_type_text} {scan_text}")
    if _has_any_word(combined, ("slim", "gầy", "mảnh", "thin",
                                "slender", "ốm")):
        return "slim"
    if _has_any_word(combined, _STURDY_MARKERS):
        return "sturdy"
    return "standard"


def _template(scan_text: str, gender: str, fields) -> str:
    if _has_any_word(scan_text, _ELDERLY_MARKERS):
        return "elderly"
    age_raw = _field(fields, "AGE")
    if age_raw is not None:
        match = re.search(r"\d+", str(age_raw))
        if match and int(match.group(0)) >= 60:
            return "elderly"
    if _has_any_word(scan_text, _CHILD_MARKERS):
        return "child"
    parsed = _parse_gender(gender)
    if parsed == "female":
        return "female"
    if parsed == "male":
        return "male"
    if _has_any_word(scan_text, _FEMALE_TEMPLATE_MARKERS):
        return "female"
    return "male"


def derive_render_traits(name: str, role: str, appearance: str,
                         costume_text: str, traits, voice_style: str,
                         *, fields=None, gender: str = "",
                         height_px: int = 540) -> dict:
    """Deterministic section 15.2 render_traits from script text.

    ``traits`` is a list of trait strings (a single string is also
    accepted). ``fields`` is the verbatim fields dict of the newer
    script dialect; only the GENDER, HAIR, BODY_TYPE, MOUSTACHE and
    GLASSES fields are read -- the whole dict is never scanned, so
    unrelated field values (a costume mentioning a place name, for
    example) can never create a moustache or change a template.
    Elderly detection yields template "elderly"; cane and glasses
    for that template are defined by the template system itself, not
    by extra trait fields.
    """
    if isinstance(traits, str):
        trait_list = [traits] if traits.strip() else []
    else:
        trait_list = [str(t) for t in (traits or [])]
    traits_text = "; ".join(trait_list)
    effective_gender = gender or _field_text(fields, "GENDER")
    scan = _norm(" ".join(p for p in (
        name, role, appearance, costume_text, traits_text,
        voice_style) if p))
    hair_scan = _norm(" ".join(p for p in (
        _field_text(fields, "HAIR"), appearance, role) if p))
    moustache_field_style, _note = moustache_style_from_fields(fields)
    if moustache_field_style is not None:
        moustache_style = moustache_field_style
    else:
        moustache_style = _moustache_from_scan(scan)
    glasses_field = _field_text(fields, "GLASSES").strip().lower()
    if glasses_field in ("yes", "true", "1", "đeo kính", "có"):
        glasses = True
    elif glasses_field in ("no", "false", "0", "none", "không"):
        glasses = False
    else:
        glasses = _has_any_word(scan, _GLASSES_MARKERS)
    if _has_any_word(scan, _UNIFORM_MARKERS):
        costume = "uniform"
    elif _has_any_word(scan, _DRESS_MARKERS):
        costume = "dress"
    else:
        costume = "none"
    hat = "bowler" if _has_any_word(scan, _HAT_MARKERS) else "none"
    return {
        "description": " ".join(
            p for p in (role, appearance) if p).strip(),
        "voice_hint": derive_voice_hint(
            name, role, appearance, voice_style,
            gender=effective_gender),
        "template": _template(scan, effective_gender, fields),
        "body_variant": _body_variant(
            scan, _field_text(fields, "BODY_TYPE")),
        "costume": costume,
        "hair_style": _hair_style(hair_scan),
        "hat": hat,
        "moustache_style": moustache_style,
        "glasses": glasses,
        "jacket_color": _jacket_color_from_text(" ".join(p for p in (
            role, appearance, costume_text, traits_text) if p)),
        "height_px": int(height_px),
    }


# --- Location render traits ------------------------------------------

_GREAT_WALL_MARKERS = ("vạn lý trường thành", "great wall", "trường thành")
_EIFFEL_MARKERS = ("eiffel",)
_RAINY_STREET_MARKERS = ("phố mưa", "rainy street")
_NIGHT_MARKERS = ("đêm", "tối", "khuya", "nửa đêm", "ban đêm", "night",
                  "evening", "midnight")
_COLD_MARKERS = ("lạnh", "lẽo", "giá lạnh", "buốt", "u ám", "âm u", "cold")


def derive_location_traits(name: str = "", geography: str = "",
                           architecture: str = "", features=None,
                           inline_text: str = "",
                           time_of_day_text: str = "",
                           mood_text: str = "") -> dict:
    """Deterministic section 15.3 render_traits.

    ``location_keyword`` is the renderer's generic fallback vocabulary
    ("street" for anything unrecognised); it never substitutes one
    scripted location for another -- the true location data travels
    in the trait block's verbatim fields. ``setting`` is the inline
    text, falling back to the location name.
    """
    if isinstance(features, str):
        feature_text = features
    else:
        feature_text = "; ".join(str(f) for f in (features or []))
    scan = " ".join(p for p in (
        name, geography, architecture, feature_text, inline_text) if p).lower()
    if any(m in scan for m in _GREAT_WALL_MARKERS):
        keyword = "great_wall"
    elif any(m in scan for m in _EIFFEL_MARKERS):
        keyword = "eiffel_tower"
    elif any(m in scan for m in _RAINY_STREET_MARKERS):
        keyword = "rainy_street"
    else:
        keyword = "street"
    night = _has_any_word((time_of_day_text or "").lower(), _NIGHT_MARKERS)
    cold = _has_any_word((mood_text or "").lower(), _COLD_MARKERS)
    return {
        "setting": inline_text or name or "",
        "location_keyword": keyword,
        "mood": "cold" if cold else "warm",
        "time_of_day": "night" if night else "day",
    }


# --- Props ------------------------------------------------------------

# Kind -> keywords, checked in dict order (most specific first).
# Word-boundary matching on normalised text. "flower" is checked
# before "bag" so a basket of flowers reads as flowers, not a bag.
PROP_KEYWORDS: dict[str, tuple[str, ...]] = {
    "wallet": ("wallet", "ví", "bóp", "purse"),
    "umbrella": ("umbrella", "ô", "dù", "parasol"),
    "newspaper": ("newspaper", "tờ báo", "nhật báo", "báo"),
    "letter": ("letter", "phong thư", "lá thư", "bức thư", "thư",
               "envelope"),
    "ticket": ("ticket", "vé xe", "vé"),
    "cup": ("cup", "mug", "cốc", "tách", "chén", "ly"),
    "key": ("chìa khóa", "chìa khoá", "key"),
    "flower": ("flower", "bó hoa", "bouquet", "hoa"),
    "bag": ("backpack", "ba lô", "túi xách", "túi", "cặp", "giỏ",
            "bag"),
    "book": ("quyển sách", "book", "novel", "sách", "truyện"),
    "pen": ("fountain pen", "bút chì", "pencil", "pen", "bút"),
}


def derive_prop_kind(name: str, description: str) -> str:
    """Drawable prop kind from a prop's name and description text.

    Unrecognised props map to "generic", which is itself a drawable
    kind -- never a mislabelled specific kind.
    """
    text = _norm(f"{name or ''} {description or ''}")
    for kind, keywords in PROP_KEYWORDS.items():
        if _has_any_word(text, keywords):
            return kind
    return "generic"


# --- SFX cue mapping ---------------------------------------------------

# Cue name -> engine SFX event, checked in order (most specific
# first). Conservative on purpose: a cue with no confident mapping
# returns None and is reported as unmapped, never given an invented
# sound. Door events require door words: a bare "open" is not a door.
_SFX_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("door_contact", ("gõ cửa", "door knock", "knocking", "knock",
                      "gõ")),
    ("door_rotation", ("mở cửa", "đóng cửa", "cửa mở", "cửa đóng",
                       "door open", "door close", "door creak",
                       "cửa kêu", "door")),
    ("rain_start", ("mưa rơi", "tiếng mưa", "rainfall", "mưa", "rain")),
    ("foot_contact", ("bước chân", "footstep", "footsteps", "bước đi",
                      "tiếng bước", "chân bước", "hành quân", "march")),
    ("paper_movement", ("lật báo", "lật trang", "lật sách", "giở báo",
                        "trang giấy", "xào xạc", "giấy",
                        "paper")),
    ("object_impact", ("đặt xuống", "set down", "thả xuống",
                       "đóng sầm", "va chạm", "rơi xuống", "slam",
                       "thud", "impact", "rơi", "drop", "đập")),
    ("character_reaction", ("thở dài", "hốt hoảng", "ngạc nhiên",
                            "thốt lên", "kêu lên", "cry out", "sigh",
                            "laugh", "gasp", "shout", "cười", "hét")),
]


def map_sfx_cue(cue_name: str) -> str | None:
    """Map a scripted SFX cue name to an engine event, or None.

    None means "no mapping": the cue is reported in unmapped_cues,
    never silently dropped and never given an invented timestamp.
    Two co-occurrence rules run before the keyword scan: "rustle"
    maps to paper_movement only beside a paper word (a leather
    rustle is not paper), and "xuống" maps to object_impact only
    beside a put-down verb (looking down is not an impact).
    """
    text = _norm(cue_name or "")
    if not text:
        return None
    if _has_word(text, "rustle") or _has_word(text, "rustling"):
        if _has_any_word(text, ("paper", "giấy", "page", "trang",
                                "báo", "sách", "letter", "thư",
                                "newspaper")):
            return "paper_movement"
    if _has_word(text, "xuống") and _has_any_word(
            text, ("đặt", "để", "thả")):
        return "object_impact"
    for event, keywords in _SFX_KEYWORDS:
        if _has_any_word(text, keywords):
            return event
    return None


# --- Expression mapping ------------------------------------------------

# Face-system expression -> keywords. Matching is earliest-keyword in
# the text wins, so "Grim, reflective" reads as the first-named
# feeling; ties resolve in the family order below. The "sững" family
# maps to "surprised". Word boundaries only: "ủa" never fires inside
# "của".
_EXPRESSION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("surprised", ("sững sờ", "sửng sốt", "sửng người", "ngạc nhiên",
                   "bất ngờ", "kinh ngạc", "há hốc", "bàng hoàng",
                   "choáng", "sững", "surprised", "shocked", "stunned",
                   "astonished", "startled", "ủa", "ôi")),
    ("angry", ("tức giận", "giận dữ", "phẫn nộ", "gắt gỏng", "đanh đá",
               "tức", "giận", "cáu", "angry", "furious", "enraged",
               "irritated")),
    ("worried", ("lo lắng", "hốt hoảng", "sợ hãi", "bất an",
                 "căng thẳng", "lo", "sợ", "hoảng", "worried",
                 "afraid", "scared", "anxious", "fearful", "nervous",
                 "panicked")),
    ("sad", ("thất vọng", "chán nản", "đau buồn", "mệt mỏi", "thất thần",
             "não nề", "u sầu", "buồn", "khóc", "disappointed", "sad",
             "gloomy", "grim", "sorrowful", "depressed", "weary",
             "tired", "exhausted", "dismayed", "downcast")),
    ("happy", ("hạnh phúc", "vui vẻ", "hớn hở", "thích thú",
               "phấn khởi", "vui", "cười", "mừng", "happy", "joyful",
               "cheerful", "delighted", "pleased", "laughing", "glad")),
    ("thinking", ("trầm ngâm", "suy nghĩ", "trầm tư", "đăm chiêu",
                  "nghĩ ngợi", "suy tư", "thoughtful", "thinking",
                  "reflective", "pensive", "contemplative",
                  "pondering")),
    ("doubtful", ("nghi ngờ", "hoài nghi", "ngờ vực", "băn khoăn",
                  "do dự", "không chắc", "uncertain", "doubtful",
                  "skeptical", "sceptical", "suspicious", "unsure",
                  "hesitant", "confused")),
    ("neutral", ("bình thản", "bình tĩnh", "vô cảm", "thản nhiên",
                 "điềm tĩnh", "calm", "neutral", "composed",
                 "indifferent", "blank")),
]


def map_expression_text(text: str) -> str | None:
    """Map free expression text to a face-system expression name.

    Returns None when no expression family matches; the caller then
    attaches no expression and the engine falls back to its text
    scan. An exact expression name is returned as-is.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered in EXPRESSION_NAMES:
        return lowered
    best = None  # (position, family order, expression)
    for order, (expression, keywords) in enumerate(_EXPRESSION_KEYWORDS):
        for keyword in keywords:
            match = re.search(r"\b" + re.escape(keyword) + r"\b", lowered)
            if match:
                candidate = (match.start(), order, expression)
                if best is None or candidate < best:
                    best = candidate
    return best[2] if best is not None else None


# --- Camera mapping ------------------------------------------------------

# Camera free text -> shot type, checked in priority order (most
# specific scale first). Camera values are controlled tokens, so
# substring matching on normalised text is the right tool here --
# unlike the identity scans above, which are word-boundary only.
_CAMERA_SHOT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("over_the_shoulder", ("over the shoulder", "over shoulder",
                           "qua vai")),
    ("shot_reverse_shot", ("shot reverse", "reverse shot", "reverse")),
    ("reaction", ("reaction", "phản ứng")),
    ("object_insert", ("object insert", "insert", "chèn vật")),
    ("extreme_close_up", ("extreme", "cực cận", "đặc tả")),
    ("close_up", ("closeup", "close up", "cận cảnh", "cận")),
    ("tracking", ("tracking", "bám theo", "theo dõi")),
    ("establishing", ("establishing", "overview", "wide",
                      "environmental", "toàn cảnh", "bao quát",
                      "rộng")),
    ("medium", ("medium", "trung cảnh", "trung")),
]


def map_camera_text_to_shot_type(text: str) -> tuple[str, str | None]:
    """Map shot "camera" free text to a shot type.

    Returns (shot_type, note): note is None when the text matched a
    rule, and explains the "medium" default otherwise. The verbatim
    text is always preserved by the caller in the directive.
    """
    raw = (text or "").strip()
    if not raw:
        return "medium", "no camera text; default medium shot applied"
    normed = _norm(raw)
    for shot_type, keywords in _CAMERA_SHOT_RULES:
        if any(k in normed for k in keywords):
            return shot_type, None
    return "medium", (
        f"camera text {raw!r} did not match a shot-type rule; "
        "default medium shot applied")


# Explicit angle words in CAMERA text, checked in order (most
# specific first). These override the DEFAULT_ANGLE_BY_SHOT table:
# the script's own angle wording wins over the per-type default.
# NOTE: "ots" is matched as a whole word only (it occurs inside
# "shots"); the other entries are distinctive phrases.
_CAMERA_ANGLE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("over_shoulder", ("over the shoulder", "over shoulder")),
    ("birds_eye", ("birds eye", "birdseye", "bird's eye", "bird s eye",
                   "aerial", "top down", "topdown", "overview")),
    ("low_angle", ("low angle", "lowangle", "from below", "worms eye",
                   "worm s eye", "nhìn lên", "góc thấp")),
    ("high_angle", ("high angle", "highangle", "from above",
                    "nhìn xuống", "nhìn từ trên", "góc cao")),
    ("dutch", ("dutch", "canted", "nghiêng")),
    ("eye_level", ("eye level", "eyelevel", "ngang tầm mắt")),
]


def map_camera_angle(text: str, shot_type: str = "medium") -> str:
    """Map CAMERA free text + shot type to a camera angle label.

    Explicit angle words in the text win; otherwise the default
    angle for the shot type applies (DEFAULT_ANGLE_BY_SHOT). Never
    raises; unknown text yields the default table value. This emits
    a label only -- all viewpoint geometry is engine-owned.
    """
    normed = _norm(text or "")
    if normed:
        if _has_word(normed, "ots"):
            return "over_shoulder"
        for angle, keywords in _CAMERA_ANGLE_RULES:
            if any(k in normed for k in keywords):
                return angle
    return DEFAULT_ANGLE_BY_SHOT.get(shot_type, "eye_level")


def map_camera_text_to_shot_and_angle(text: str
                                      ) -> tuple[str, str, str | None]:
    """Map shot "camera" free text to (shot_type, camera_angle, note).

    The note (if any) is the shot-type defaulting note from
    map_camera_text_to_shot_type; angle defaulting via the per-type
    table is the documented behaviour, not a warning.
    """
    shot_type, note = map_camera_text_to_shot_type(text)
    return shot_type, map_camera_angle(text, shot_type), note


def map_camera_movement_text(text: str) -> tuple[str, str | None]:
    """Map free camera-movement text to a CAMERA_MOVEMENT enum value.

    Returns (enum, note): note is None for a confident match and
    explains an assumed direction otherwise. Empty text maps to
    STATIC with no note (absence is normal, not an error).
    """
    raw = (text or "").strip()
    if not raw:
        return "STATIC", None
    normed = _norm(raw)
    if any(k in normed for k in ("handheld", "hand held", "rung tay",
                                 "cầm tay")):
        return "HANDHELD", None
    if "crane up" in normed or "cẩu lên" in normed:
        return "CRANE_UP", None
    if "crane down" in normed or "cẩu xuống" in normed:
        return "CRANE_DOWN", None
    if "tilt up" in normed or "ngẩng lên" in normed or "hất lên" in normed:
        return "TILT_UP", None
    if "tilt down" in normed or "hạ xuống" in normed:
        return "TILT_DOWN", None
    if "pan left" in normed or "quay trái" in normed or "lia trái" in normed:
        return "PAN_LEFT", None
    if "pan right" in normed or "quay phải" in normed or "lia phải" in normed:
        return "PAN_RIGHT", None
    if "tracking" in normed or "bám theo" in normed:
        return "TRACKING", None
    if any(k in normed for k in ("dolly in", "zoom in", "tiến vào",
                                 "tiến tới", "lại gần", "tiến gần")):
        return "DOLLY_IN", None
    if any(k in normed for k in ("dolly out", "zoom out", "lùi ra",
                                 "rút ra", "lùi lại")):
        return "DOLLY_OUT", None
    if "zoom" in normed:
        return "DOLLY_IN", (
            f"camera movement {raw!r} names a zoom without a "
            "direction; assumed dolly-in")
    if "dolly" in normed:
        return "DOLLY_IN", (
            f"camera movement {raw!r} names a dolly move without a "
            "direction; assumed dolly-in")
    if "lateral" in normed:
        return "PAN_RIGHT", (
            f"camera movement {raw!r} names lateral movement "
            "without a direction; assumed pan right")
    if "pan" in normed:
        return "PAN_RIGHT", (
            f"camera movement {raw!r} names a pan without a "
            "direction; assumed pan right")
    if any(k in normed for k in ("static", "still", "fixed", "tĩnh",
                                 "đứng yên", "cố định")):
        return "STATIC", None
    return "STATIC", (
        f"camera movement {raw!r} did not match a movement rule; "
        "default STATIC applied")


def map_scene_costume_to_garment(costume: str) -> str:
    """Scene costume label -> render garment enum value.

    CIVILIAN renders as "none" (no uniform garment), MILITARY as
    "uniform". Anything else (including absent) yields "" and the
    engine default applies. The raw scene costume is always emitted
    alongside the garment value.
    """
    text = (costume or "").strip().upper()
    if text in ("CIVILIAN", "CIVIL", "DÂN SỰ", "DAN SU", "THƯỜNG PHỤC",
                "THUONG PHUC"):
        return "none"
    if text in ("MILITARY", "QUÂN PHỤC", "QUAN PHUC", "QUÂN ĐỘI",
                "QUAN DOI", "SOLDIER", "UNIFORM"):
        return "uniform"
    return ""


# --- Action directives ---------------------------------------------------

# Action prose -> PRIMITIVES key, checked in order (most specific
# first). Pick-ups map to kneel_pick (the engine's preferred pickup
# primitive); bend_pick stays reachable from Gemini directives.
# Anything with no match is reported as unmapped, never replaced by
# a camera move.
_ACTION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("kneel_pick", ("cúi nhặt", "cúi xuống nhặt", "quỳ", "kneel",
                    "nhặt", "nhặt lên", "pick up", "pickup")),
    ("give_to", ("đưa cho", "trao cho", "hand over", "give", "đưa",
                 "trao", "hand_over")),
    ("run_to", ("chạy tới", "chạy đến", "lao tới", "chạy", "run")),
    ("walk_to", ("đi bộ", "bước đi", "đi ngang", "đi qua", "đi tới",
                 "hành quân", "walk", "march", "đi")),
    ("sit_down", ("ngồi xuống", "ngồi", "sit down", "sit")),
    ("stand_up", ("đứng dậy", "đứng lên", "stand up")),
    ("cover_face", ("che mặt", "cover face", "ôm mặt", "úp mặt")),
    ("shrug", ("nhún vai", "shrug")),
    ("wave", ("vẫy tay", "vẫy", "wave")),
    ("nod", ("gật đầu", "gật", "nod")),
    ("point_at", ("chỉ tay", "point", "chỉ")),
    ("reach_to", ("với lấy", "vươn tay", "reach", "với")),
    ("look_at", ("nhìn quanh", "nhìn về", "nhìn sang", "nhìn", "look",
                 "liếc", "ngó")),
    ("turn_to", ("quay lại", "quay đầu", "quay người", "quay", "turn")),
    ("idle", ("đứng yên", "đứng im", "dừng bước", "dừng", "idle",
              "đứng")),
]

# Action-cue tag -> PRIMITIVES key, for scripts that only carry cue
# tags. Cues with no primitive (open, take, board, rain, bus, ...)
# map to None and are reported as unmapped: board_vehicle exists as
# a function but is NOT in the PRIMITIVES registry, so it cannot be
# emitted as a directive.
ACTION_CUE_TO_PRIMITIVE: dict[str, str | None] = {
    "walk": "walk_to", "walk_fast": "walk_to", "run": "run_to",
    "bend_pick": "kneel_pick", "give": "give_to", "wave": "wave",
    "turn_back": "turn_to", "look": "look_at", "sit": "sit_down",
    "stand": "stand_up", "stop": "idle",
    "smile": None, "search": None, "open": None, "take": None,
    "put_away": None, "take_out": None, "board": None,
    "rain": None, "bus": None,
}

_SENTENCE_SPLIT_RE = re.compile(r"[.!?;\n]+")

# Directive parameter keys the validator keeps (SPEC section 15.5).
_DIRECTIVE_PARAM_KEYS = (
    "other", "start", "duration", "from_x", "to_x", "ground_y",
    "target", "angle_keys", "facing", "freq", "amp", "hand",
    "scene_number", "shot_id", "source_line", "action_text", "note",
)


def map_action_text_to_primitive(text: str) -> str | None:
    """Map one action sentence to a PRIMITIVES key, or None."""
    normed = _norm(text or "")
    if not normed:
        return None
    for primitive, keywords in _ACTION_KEYWORDS:
        if _has_any_word(normed, keywords):
            return primitive
    return None


def map_action_cue_to_primitive(cue: str) -> str | None:
    """Map an action-cue tag to a PRIMITIVES key, or None."""
    return ACTION_CUE_TO_PRIMITIVE.get(cue)


def _resolve_directive_char(sentence: str, char_map: dict) -> str | None:
    """Longest character name/identity mentioned in the sentence."""
    normed = _norm(sentence or "")
    best = None
    for key, identity in char_map.items():
        if key and key in normed:
            if best is None or len(key) > len(best[0]):
                best = (key, identity)
    return best[1] if best else None


def derive_action_directives(action_items, char_map=None):
    """Derive section 15.5 directives from scripted action text.

    ``action_items`` is a list of dicts: {text, scene_number,
    shot_id, source_line}. Each item is split into sentences; every
    sentence yields either a directive or an explicit unmapped
    entry. Returns (directives, unmapped). Geometry (from_x/to_x/
    target/...) is NOT invented: the animation stage assigns it.
    ``char_map`` maps normalised names/identity ids to identity ids.
    """
    char_map = char_map or {}
    directives: list[dict] = []
    unmapped: list[dict] = []
    for item in action_items or []:
        text = (item or {}).get("text", "") or ""
        scene_number = (item or {}).get("scene_number")
        shot_id = (item or {}).get("shot_id")
        source_line = (item or {}).get("source_line")
        for sentence in _SENTENCE_SPLIT_RE.split(text):
            sentence = sentence.strip(" \t\r\n•*-")
            if not sentence:
                continue
            primitive = map_action_text_to_primitive(sentence)
            if primitive is None:
                unmapped.append({
                    "kind": "action",
                    "action_text": sentence,
                    "scene_number": scene_number,
                    "shot_id": shot_id,
                    "source_line": source_line,
                    "reason": ("no PRIMITIVES mapping for this "
                               "scripted action"),
                })
                continue
            directives.append(build_action_directive(
                type=primitive,
                char=_resolve_directive_char(sentence, char_map),
                duration=ACTION_DURATION_HINTS[primitive],
                scene_number=scene_number,
                shot_id=shot_id,
                source_line=source_line,
                action_text=sentence,
            ))
    return directives, unmapped


# --- Trait-block builders (SPEC section 15) ------------------------------

def build_character_trait_block(*, identity_id: str, name: str,
                                role: str = "", appearance: str = "",
                                traits=None, costume: str = "",
                                costume_changes=None, voice: str = "",
                                voice_style: str = "", voice_id: str = "",
                                head_ratio=HEAD_RATIO_LOCKED,
                                render_traits: dict | None = None,
                                actions=None,
                                dropped_notes=None) -> dict:
    """One section 15.2 character block.

    V1 fields are copied verbatim; only head_ratio is locked (any
    other value is coerced to 0.34 and noted in ``dropped_notes``
    when a list is supplied). ``render_traits`` defaults to the
    deterministic derivation from the V1 fields.
    """
    if head_ratio != HEAD_RATIO_LOCKED:
        if dropped_notes is not None:
            dropped_notes.append(
                f"character {name!r}: head_ratio {head_ratio!r} "
                "dropped from trait data (locked to 0.34)")
        head_ratio = HEAD_RATIO_LOCKED
    if render_traits is None:
        render_traits = derive_render_traits(
            name, role, appearance, costume, traits or [],
            voice_style)
    return {
        "identity_id": identity_id,
        "name": name,
        "role": role,
        "appearance": appearance,
        "traits": list(traits or []),
        "costume": costume,
        "costume_changes": [dict(c) for c in (costume_changes or [])],
        "voice": voice,
        "voice_style": voice_style,
        "voice_id": voice_id,
        "head_ratio": HEAD_RATIO_LOCKED,
        "actions": list(actions or []),
        "render_traits": dict(render_traits),
    }


def build_location_trait_block(*, location_id: str, scene_numbers=None,
                               name: str = "", period: str = "",
                               geography: str = "",
                               architecture: str = "", features=None,
                               foreground: str = "", midground: str = "",
                               background: str = "", lighting: str = "",
                               weather: str = "", palette=None,
                               forbidden=None,
                               render_traits: dict | None = None) -> dict:
    """One section 15.3 location block (V1 fields verbatim)."""
    if render_traits is None:
        render_traits = derive_location_traits(
            name=name, geography=geography, architecture=architecture,
            features=features, inline_text=name)
    return {
        "location_id": location_id,
        "scene_numbers": list(scene_numbers or []),
        "name": name,
        "period": period,
        "geography": geography,
        "architecture": architecture,
        "features": list(features or []),
        "foreground": foreground,
        "midground": midground,
        "background": background,
        "lighting": lighting,
        "weather": weather,
        "palette": list(palette or []),
        "forbidden": list(forbidden or []),
        "render_traits": dict(render_traits),
    }


def build_sfx_event(*, cue_type: str = "SFX", name: str, trigger: str = "",
                    priority: str = "REQUIRED", scene_number: int = 0,
                    shot_id=None, line: int = 0,
                    source_key: str = "SFX", event: str,
                    note: str = "") -> dict:
    """One section 15.4 SFX event. Never carries a timestamp."""
    return {
        "cue_type": cue_type,
        "name": name,
        "trigger": trigger,
        "priority": priority,
        "scene_number": scene_number,
        "shot_id": shot_id,
        "line": line,
        "source_key": source_key,
        "event": event,
        "note": note,
    }


def build_music_event(*, cue_type: str = "BGM", name: str,
                      intensity: str = "MEDIUM", scene_number: int = 0,
                      shot_id=None, line: int = 0,
                      source_key: str = "BGM", note: str = "") -> dict:
    """One section 15.4 music event. Never reuses an SFX event name:
    music events carry no ``event`` key at all."""
    return {
        "cue_type": cue_type,
        "name": name,
        "intensity": intensity,
        "scene_number": scene_number,
        "shot_id": shot_id,
        "line": line,
        "source_key": source_key,
        "note": note,
    }


def build_unmapped_cue(*, cue_type: str, name: str, scene_number: int = 0,
                       shot_id=None, line: int = 0, reason: str,
                       trigger: str = "") -> dict:
    """One unmapped-cue report: visible, never silently dropped."""
    return {
        "cue_type": cue_type,
        "name": name,
        "trigger": trigger,
        "scene_number": scene_number,
        "shot_id": shot_id,
        "line": line,
        "reason": reason,
    }


def build_action_directive(*, type: str, char=None, duration: float = 1.5,
                           scene_number=None, shot_id=None,
                           source_line=None, action_text: str = "",
                           **params) -> dict:
    """One section 15.5 special-action directive.

    ``start`` is always None (assigned by the timeline stage).
    Only recognised directive parameters are kept.
    """
    directive = {
        "type": type,
        "char": char,
        "start": None,
        "duration": duration,
        "scene_number": scene_number,
        "shot_id": shot_id,
        "source_line": source_line,
        "action_text": action_text,
    }
    for key in _DIRECTIVE_PARAM_KEYS:
        if key in params and params[key] is not None:
            directive[key] = params[key]
    return directive


def build_trait_blocks(*, snapshot_hash: str, planner: str,
                       model=None, usage=None, reason=None,
                       characters=None, locations=None, sfx=None,
                       music=None, unmapped_cues=None, actions=None,
                       unmapped=None, dropped=None) -> dict:
    """The shared section 15 trait-block envelope.

    ONE builder for all three routes (gemini/fallback/v1) so shape
    parity is structural, not aspirational. ``reason`` explains a
    non-Gemini label (fallback reason, or why a V1 plan has no
    enrichment); it is None for a real Gemini enrichment.
    """
    return {
        "snapshot_hash": snapshot_hash,
        "planner": planner,
        "model": model,
        "usage": usage,
        "reason": reason,
        "characters": list(characters or []),
        "locations": list(locations or []),
        "audio": {
            "sfx": list(sfx or []),
            "music": list(music or []),
            "unmapped_cues": list(unmapped_cues or []),
        },
        "actions": list(actions or []),
        "unmapped": list(unmapped or []),
        "dropped": list(dropped or []),
    }


def derive_audio_blocks(audio_cues):
    """Section 15.4 audio blocks from scripted cues only.

    Returns (sfx, music, unmapped_cues, dropped_notes). SFX cues map
    through map_sfx_cue; BGM/MUSIC cues become music events (never
    SFX event names); AMBIENCE and MEME cues are reported in
    unmapped_cues with the reason -- they belong to other buses/
    stages, and inventing SFX events for them is forbidden. No
    timestamps are ever emitted. Cue dicts are read defensively so
    both script dialects work (name/event/type/fields variants).
    """
    sfx: list[dict] = []
    music: list[dict] = []
    unmapped_cues: list[dict] = []
    dropped_notes: list[str] = []
    for cue in audio_cues or []:
        if not isinstance(cue, dict):
            dropped_notes.append("audio cue was not an object; dropped")
            continue
        cue_type = str(cue.get("cue_type") or "").upper()
        fields = cue.get("fields") if isinstance(cue.get("fields"), dict) else {}
        name = (cue.get("name") or cue.get("event")
                or _field_text(fields, "EVENT")
                or cue.get("id") or "")
        name = str(name)
        trigger = str(cue.get("trigger") or "")
        scene_number = cue.get("scene_number") or 0
        try:
            scene_number = int(scene_number)
        except (TypeError, ValueError):
            scene_number = 0
        shot_id = cue.get("shot_id")
        line = cue.get("line") or 0
        try:
            line = int(line)
        except (TypeError, ValueError):
            line = 0
        source_key = str(cue.get("source_key") or cue_type or "")
        if cue_type == "SFX":
            mapping_text = " ".join(p for p in (
                name, str(cue.get("type") or ""),
                _field_text(fields, "TYPE")) if p)
            event = map_sfx_cue(mapping_text)
            priority = str(cue.get("priority") or "REQUIRED")
            if priority not in ("REQUIRED", "OPTIONAL"):
                dropped_notes.append(
                    f"SFX cue {name!r}: priority {priority!r} is not "
                    "REQUIRED/OPTIONAL; defaulted to REQUIRED")
                priority = "REQUIRED"
            if event is not None:
                sfx.append(build_sfx_event(
                    name=name, trigger=trigger, priority=priority,
                    scene_number=scene_number, shot_id=shot_id,
                    line=line, source_key=source_key, event=event))
            else:
                unmapped_cues.append(build_unmapped_cue(
                    cue_type="SFX", name=name, trigger=trigger,
                    scene_number=scene_number, shot_id=shot_id,
                    line=line,
                    reason=("no engine SFX event mapping for this "
                            "cue name")))
        elif cue_type == "BGM":
            intensity = str(cue.get("intensity") or "MEDIUM").upper()
            if intensity not in MUSIC_INTENSITIES:
                dropped_notes.append(
                    f"BGM cue {name!r}: intensity {intensity!r} is "
                    "not LOW/MEDIUM/HIGH; defaulted to MEDIUM")
                intensity = "MEDIUM"
            music.append(build_music_event(
                name=name, intensity=intensity,
                scene_number=scene_number, shot_id=shot_id, line=line,
                source_key=source_key or "BGM"))
        elif cue_type == "AMBIENCE":
            unmapped_cues.append(build_unmapped_cue(
                cue_type="AMBIENCE", name=name, trigger=trigger,
                scene_number=scene_number, shot_id=shot_id, line=line,
                reason=("ambience cue: no SFX event mapping applies; "
                        "the ambience bus owns it at the audio stage")))
        elif cue_type == "MEME":
            unmapped_cues.append(build_unmapped_cue(
                cue_type="MEME", name=name, trigger=trigger,
                scene_number=scene_number, shot_id=shot_id, line=line,
                reason=("meme cue: governed by meme policy at the "
                        "audio stage; no SFX event mapping")))
        else:
            dropped_notes.append(
                f"audio cue {name!r}: unknown cue_type "
                f"{cue_type!r}; dropped")
    return sfx, music, unmapped_cues, dropped_notes


# --- Model-output validation -------------------------------------------

def _clean_text(value, limit: int):
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:limit] if text else None


def _clean_render_traits(raw: dict, who: str, dropped: list) -> dict:
    """Validate one render_traits object (nested or flat fields).

    Invalid values are dropped with a note; the caller fills missing
    fields from derive_* so the result is always complete. Never
    raises.
    """
    cleaned: dict[str, Any] = {}
    enums = (
        ("template", TEMPLATES), ("body_variant", BODY_VARIANTS),
        ("costume", COSTUME_GARMENTS), ("hair_style", HAIR_STYLES),
        ("hat", HATS), ("moustache_style", MOUSTACHE_STYLES),
    )
    for key, allowed in enums:
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip() in allowed:
            cleaned[key] = value.strip()
        else:
            dropped.append(
                f"{who}: {key} {value!r} is not in {list(allowed)}; "
                "dropped")
    glasses = raw.get("glasses")
    if glasses is not None:
        if isinstance(glasses, bool):
            cleaned["glasses"] = glasses
        else:
            dropped.append(
                f"{who}: glasses {glasses!r} is not a boolean; dropped")
    color = raw.get("jacket_color")
    if color is not None:
        if isinstance(color, str) and _JACKET_COLOR_RE.match(color.strip()):
            cleaned["jacket_color"] = color.strip()
        else:
            dropped.append(
                f"{who}: jacket_color {color!r} is not #RRGGBB; dropped")
    for key in ("description", "voice_hint"):
        text = _clean_text(raw.get(key), 200)
        if raw.get(key) is not None and text is not None:
            cleaned[key] = text
    return cleaned


def _clean_location_traits(raw: dict, who: str, dropped: list) -> dict:
    cleaned: dict[str, Any] = {}
    setting = _clean_text(raw.get("setting"), 120)
    if setting is not None:
        cleaned["setting"] = setting
    for key, allowed in (("location_keyword", LOCATION_KEYWORDS),
                         ("mood", MOODS), ("time_of_day", TIMES_OF_DAY)):
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip() in allowed:
            cleaned[key] = value.strip()
        else:
            dropped.append(
                f"{who}: {key} {value!r} is not in {list(allowed)}; "
                "dropped")
    return cleaned


def _clean_directive(raw, who: str, dropped: list):
    """Validate one special-action directive; None when unusable."""
    if not isinstance(raw, dict):
        dropped.append(f"{who}: action directive was not an object; dropped")
        return None
    ptype = raw.get("type")
    if ptype not in PRIMITIVE_NAMES:
        dropped.append(
            f"{who}: action type {ptype!r} is not a PRIMITIVES key; "
            "dropped")
        return None
    directive = {"type": ptype}
    for key in ("char", "other", "shot_id"):
        if isinstance(raw.get(key), str) and raw[key].strip():
            directive[key] = raw[key].strip()
    for key in ("start", "duration", "from_x", "to_x", "ground_y",
                "facing", "freq", "amp"):
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            dropped.append(
                f"{who}: directive {key} {value!r} is not a number; "
                "dropped")
        else:
            directive[key] = value
    target = raw.get("target")
    if target is not None:
        if (isinstance(target, (list, tuple)) and len(target) == 2
                and all(isinstance(v, (int, float))
                        and not isinstance(v, bool) for v in target)):
            directive["target"] = [target[0], target[1]]
        else:
            dropped.append(
                f"{who}: directive target {target!r} is not a "
                "[x, y] number pair; dropped")
    angles = raw.get("angle_keys")
    if angles is not None:
        if (isinstance(angles, list)
                and all(isinstance(v, (int, float))
                        and not isinstance(v, bool) for v in angles)):
            directive["angle_keys"] = list(angles)
        else:
            dropped.append(
                f"{who}: directive angle_keys {angles!r} is not a "
                "number list; dropped")
    hand = raw.get("hand")
    if hand is not None:
        if hand in ("l", "left"):
            directive["hand"] = "l"
        elif hand in ("r", "right"):
            directive["hand"] = "r"
        else:
            dropped.append(
                f"{who}: directive hand {hand!r} is not l/r; dropped")
    for key in ("scene_number", "scene", "source_line"):
        value = raw.get(key)
        if value is None:
            continue
        try:
            directive["scene_number" if key == "scene" else key] = int(value)
        except (TypeError, ValueError):
            dropped.append(
                f"{who}: directive {key} {value!r} is not an integer; "
                "dropped")
    for key in ("action_text", "note"):
        text = _clean_text(raw.get(key), 200)
        if text is not None:
            directive[key] = text
    return directive


def validate_trait_blocks(blocks) -> tuple[dict, list[str]]:
    """Validate planner/model trait JSON against the section 15 enums.

    Returns (cleaned, dropped_notes). ``cleaned`` always has the
    canonical keys: characters, locations, shots, sfx, music,
    actions, hook, twist. Invalid values are dropped with a note,
    never passed through, never a crash. head_ratio must equal 0.34:
    anything else is dropped and noted. Character/location fields
    are accepted either nested under ``render_traits`` or flat at
    the top level of the entry (flat fills gaps left by nested).
    Ground-truth filtering (unknown characters/scenes/lines) is the
    caller's job -- this function only validates shapes and enums.
    """
    dropped: list[str] = []
    cleaned: dict[str, Any] = {
        "characters": [], "locations": [], "shots": [], "sfx": [],
        "music": [], "actions": [], "hook": None, "twist": None,
    }
    if not isinstance(blocks, dict):
        dropped.append(
            "trait blocks were not a JSON object; all enrichment dropped")
        return cleaned, dropped
    try:
        _validate_characters(blocks, cleaned, dropped)
        _validate_locations(blocks, cleaned, dropped)
        _validate_shots(blocks, cleaned, dropped)
        _validate_sfx(blocks, cleaned, dropped)
        _validate_music(blocks, cleaned, dropped)
        _validate_actions(blocks, cleaned, dropped)
        for key in ("hook", "twist"):
            value = blocks.get(key)
            if value is not None:
                text = _clean_text(value, 200)
                if text is not None:
                    cleaned[key] = text
                else:
                    dropped.append(f"{key} was not a non-empty string; dropped")
    except Exception as exc:  # noqa: BLE001 - validation never crashes
        dropped.append(f"trait validation failed partway ({exc}); "
                       "partial enrichment kept, rest dropped")
    return cleaned, dropped


def _validate_characters(blocks, cleaned, dropped):
    raw_list = blocks.get("characters")
    if raw_list is None:
        return
    if not isinstance(raw_list, list):
        dropped.append("characters was not a list; dropped")
        return
    for i, entry in enumerate(raw_list):
        who = f"character[{i}]"
        if not isinstance(entry, dict):
            dropped.append(f"{who} was not an object; dropped")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            dropped.append(f"{who} has no usable name; dropped")
            continue
        name = name.strip()
        who = f"character {name!r}"
        nested = entry.get("render_traits")
        merged_raw = dict(entry)
        if isinstance(nested, dict):
            merged_raw.update({k: v for k, v in nested.items()
                               if v is not None})
        traits = _clean_render_traits(merged_raw, who, dropped)
        head_ratio = entry.get("head_ratio")
        if head_ratio is not None and head_ratio != HEAD_RATIO_LOCKED:
            dropped.append(
                f"{who}: head_ratio {head_ratio!r} dropped "
                "(locked to 0.34)")
        out = {"name": name, "render_traits": traits}
        identity = entry.get("identity_id")
        if isinstance(identity, str) and identity.strip():
            out["identity_id"] = identity.strip()
        raw_actions = entry.get("actions")
        if isinstance(raw_actions, list):
            char_actions = []
            for raw in raw_actions:
                directive = _clean_directive(raw, who, dropped)
                if directive is not None:
                    char_actions.append(directive)
            out["actions"] = char_actions
        cleaned["characters"].append(out)


def _validate_locations(blocks, cleaned, dropped):
    raw_list = blocks.get("locations")
    if raw_list is None:
        return
    if not isinstance(raw_list, list):
        dropped.append("locations was not a list; dropped")
        return
    for i, entry in enumerate(raw_list):
        who = f"location[{i}]"
        if not isinstance(entry, dict):
            dropped.append(f"{who} was not an object; dropped")
            continue
        nested = entry.get("render_traits")
        merged_raw = dict(entry)
        if isinstance(nested, dict):
            merged_raw.update({k: v for k, v in nested.items()
                               if v is not None})
        traits = _clean_location_traits(merged_raw, who, dropped)
        out = {"render_traits": traits}
        scene = entry.get("scene", entry.get("scene_number"))
        location_id = entry.get("location_id")
        if scene is not None:
            try:
                out["scene"] = int(scene)
            except (TypeError, ValueError):
                dropped.append(f"{who}: scene {scene!r} is not an "
                               "integer; dropped")
                continue
        if isinstance(location_id, str) and location_id.strip():
            out["location_id"] = location_id.strip()
        if "scene" not in out and "location_id" not in out:
            dropped.append(f"{who} names no scene or location_id; dropped")
            continue
        cleaned["locations"].append(out)


def _validate_shots(blocks, cleaned, dropped):
    raw_list = blocks.get("shots")
    if raw_list is None:
        return
    if not isinstance(raw_list, list):
        dropped.append("shots was not a list; dropped")
        return
    for i, entry in enumerate(raw_list):
        who = f"shot[{i}]"
        if not isinstance(entry, dict):
            dropped.append(f"{who} was not an object; dropped")
            continue
        shot_type = entry.get("shot_type")
        if shot_type not in SHOT_TYPES:
            dropped.append(
                f"{who}: shot_type {shot_type!r} is not one of "
                f"{list(SHOT_TYPES)}; dropped")
            continue
        try:
            line_index = int(entry.get("line_index"))
            scene = int(entry.get("scene", 0))
        except (TypeError, ValueError):
            dropped.append(f"{who}: line_index/scene is not an integer; "
                           "dropped")
            continue
        shot = {"scene": scene, "line_index": line_index,
                "shot_type": shot_type}
        purpose = _clean_text(entry.get("purpose"), 120)
        if purpose is not None:
            shot["purpose"] = purpose
        cleaned["shots"].append(shot)


def _validate_sfx(blocks, cleaned, dropped):
    raw_list = blocks.get("sfx")
    if raw_list is None:
        return
    if not isinstance(raw_list, list):
        dropped.append("sfx was not a list; dropped")
        return
    for i, entry in enumerate(raw_list):
        who = f"sfx[{i}]"
        if not isinstance(entry, dict):
            dropped.append(f"{who} was not an object; dropped")
            continue
        event = entry.get("event")
        if event not in SFX_EVENTS:
            dropped.append(
                f"{who}: event {event!r} is not one of "
                f"{sorted(SFX_EVENTS)}; dropped")
            continue
        try:
            scene = int(entry.get("scene", entry.get("scene_number", 0)))
        except (TypeError, ValueError):
            dropped.append(f"{who}: scene is not an integer; dropped")
            continue
        item = {"event": event, "scene": scene}
        note = _clean_text(entry.get("note"), 120)
        if note is not None:
            item["note"] = note
        name = _clean_text(entry.get("name"), 120)
        if name is not None:
            item["name"] = name
        cleaned["sfx"].append(item)


def _validate_music(blocks, cleaned, dropped):
    raw_list = blocks.get("music")
    if raw_list is None:
        return
    if not isinstance(raw_list, list):
        dropped.append("music was not a list; dropped")
        return
    for i, entry in enumerate(raw_list):
        who = f"music[{i}]"
        if not isinstance(entry, dict):
            dropped.append(f"{who} was not an object; dropped")
            continue
        if "event" in entry:
            dropped.append(
                f"{who}: music must not reuse SFX event names; "
                "'event' key dropped")
        name = _clean_text(entry.get("name"), 120)
        if name is None:
            dropped.append(f"{who} has no usable name; dropped")
            continue
        intensity = entry.get("intensity")
        if intensity is not None and intensity not in MUSIC_INTENSITIES:
            dropped.append(
                f"{who}: intensity {intensity!r} is not one of "
                f"{list(MUSIC_INTENSITIES)}; dropped")
            intensity = None
        try:
            scene = int(entry.get("scene", entry.get("scene_number", 0)))
        except (TypeError, ValueError):
            dropped.append(f"{who}: scene is not an integer; dropped")
            continue
        item = {"name": name, "scene": scene}
        if intensity is not None:
            item["intensity"] = intensity
        note = _clean_text(entry.get("note"), 120)
        if note is not None:
            item["note"] = note
        cleaned["music"].append(item)


def _validate_actions(blocks, cleaned, dropped):
    raw_list = blocks.get("actions")
    if raw_list is None:
        return
    if not isinstance(raw_list, list):
        dropped.append("actions was not a list; dropped")
        return
    for i, entry in enumerate(raw_list):
        directive = _clean_directive(entry, f"action[{i}]", dropped)
        if directive is not None:
            cleaned["actions"].append(directive)
