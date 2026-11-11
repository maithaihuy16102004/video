"""Parser for structured free-form Vietnamese scripts (shared engine).

Many scripts Mai writes are NOT Studio Script V1 — they are structured
Vietnamese documents like::

    ## CẢNH 01 — CHIẾC VÍ BÊN VŨNG NƯỚC
    Bối cảnh: Đường phố ban đêm, trời mưa nhẹ...
    Hành động: Minh đi nhanh trên vỉa hè...
    Người dẫn chuyện: "Đêm mưa, Minh vội đến trạm xe buýt..."
    Minh: "Ủa? Ví của ai đánh rơi thế này?"
    Âm thanh: Mưa rơi nhẹ...
    Yêu cầu animation: Có chuyển động chân thật...

Rules (generic, not per-story):
- Only QUOTED speech becomes a spoken line: ``Người dẫn chuyện: "..."``
  (kind=narration, speaker=narrator) and ``Name: "..."`` (kind=dialogue).
  Headers, metadata, character lists, setting/action/audio/requirement
  paragraphs are NEVER spoken aloud (Master Prompt §3).
- Scene headers match ``CẢNH <number>`` with any separator (—, -, :).
- Character list (``Nhân vật:`` + ``- Name: description, giọng ...``)
  yields characters with a voice hint (giọng nam/nữ/kể) when present.
- Action verbs are extracted from ``Hành động:`` + ``Yêu cầu animation:``
  text with a generic Vietnamese verb map (ACTION_VERBS) — the renderer
  and the audio planner consume these cues; nothing here names a story.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SCENE_RE = re.compile(r"^#{0,3}\s*CẢNH\s+(\d+)\s*[—\-:–]?\s*(.*)$")
FIELD_RE = re.compile(r"^(Bối cảnh|Hành động|Âm thanh|Yêu cầu animation|Người dẫn chuyện)\s*:\s*(.*)$")
DIALOGUE_RE = re.compile(r"^([A-ZÀ-Ỹ][\wÀ-ỹ]{0,15}(?: [A-ZÀ-Ỹ][\wÀ-ỹ]{0,15})?)\s*:\s*\"(.+)\"\s*$")
NARRATOR_RE = re.compile(r"^Người dẫn chuyện\s*:\s*\"(.+)\"\s*$")
CHARACTER_RE = re.compile(r"^-\s*([A-ZÀ-Ỹ][\wÀ-ỹ]{0,15})\s*:\s*(.+)$")
QUOTED_RE = re.compile(r"\"([^\"]+)\"")

# Generic Vietnamese action-verb map: regex -> action cue. Used by the
# renderer (animation primitives) and the audio planner (SFX cues).
# Ordered: first match wins per clause. Nothing here is story-specific.
ACTION_VERBS: list[tuple[str, str]] = [
    (r"\bchạy\b", "run"),
    (r"\bđi nhanh\b|\bvội\b", "walk_fast"),
    (r"\bđi\b|\bbước\b", "walk"),
    (r"\bdừng\b|\bdừng lại\b", "stop"),
    (r"\bcúi\b|\bnhặt\b", "bend_pick"),
    (r"\bđưa (chiếc )?(ví|tiền|đồ|thư|phong bì)\b|\btrao\b", "give"),
    (r"\bnhận\b|\blấy\b", "take"),
    (r"\bmở ví\b|\bmở túi\b|\bmở\b", "open"),
    (r"\bcất\b|\bbỏ vào\b", "put_away"),
    (r"\brút\b", "take_out"),
    (r"\bgiơ tay\b|\bchào\b", "wave"),
    (r"\bquay đầu\b|\bngoái\b", "turn_back"),
    (r"\bmỉm cười\b|\bcười\b", "smile"),
    (r"\bnhìn\b|\bnhìn quanh\b|\bnhìn xuống\b", "look"),
    (r"\bkiểm tra\b|\btìm\b", "search"),
    (r"\bbước lên\b|\blên xe\b", "board"),
    (r"\bngồi\b", "sit"),
    (r"\bđứng\b", "stand"),
    (r"\bmưa\b", "rain"),
    (r"\bxe buýt\b|\bxe\b", "bus"),
]


@dataclass
class SpokenLine:
    speaker: str  # "narrator" or a character name
    kind: str     # "narration" | "dialogue"
    text: str


@dataclass
class ViScene:
    number: int
    title: str = ""
    setting: str = ""
    action_text: str = ""
    audio_text: str = ""
    animation_reqs: str = ""
    lines: list[SpokenLine] = field(default_factory=list)
    action_cues: list[str] = field(default_factory=list)


@dataclass
class ViScript:
    title: str = ""
    language: str = "vi-VN"
    characters: list[dict] = field(default_factory=list)  # {name, description, voice_hint}
    scenes: list[ViScene] = field(default_factory=list)

    @property
    def lines(self) -> list[SpokenLine]:
        out: list[SpokenLine] = []
        for s in self.scenes:
            out.extend(s.lines)
        return out


def extract_action_cues(text: str) -> list[str]:
    """Generic verb cues from Vietnamese action text, in first-seen order.
    Suppresses the generic cue when a more specific one already fired
    (e.g. "đi nhanh" gives walk_fast, not walk as well)."""
    cues: list[str] = []
    low = text.lower()
    for pattern, cue in ACTION_VERBS:
        if re.search(pattern, low) and cue not in cues:
            cues.append(cue)
    if "walk_fast" in cues and "walk" in cues:
        cues.remove("walk")
    if "board" in cues and "walk" in cues:
        cues.remove("walk")
    return cues


def is_structured_vi_script(script_text: str) -> bool:
    """True when the text is a structured CẢNH script with quoted speech."""
    has_scene = any(SCENE_RE.match(l.strip()) for l in script_text.splitlines())
    has_speech = bool(QUOTED_RE.search(script_text))
    return has_scene and has_speech


def parse_vi_script(script_text: str) -> ViScript:
    """Parse a structured Vietnamese free-form script. Raises ValueError
    when the text is not a structured CẢNH script (caller falls back to
    the generic line segmentation)."""
    if not is_structured_vi_script(script_text):
        raise ValueError("not a structured Vietnamese CẢNH script")
    result = ViScript()
    current: ViScene | None = None
    in_characters = False

    def finish_scene() -> None:
        nonlocal current
        if current is not None:
            current.action_cues = extract_action_cues(
                current.action_text + " " + current.animation_reqs)
            result.scenes.append(current)
            current = None

    for raw in script_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = SCENE_RE.match(line)
        if m:
            finish_scene()
            in_characters = False
            current = ViScene(number=int(m.group(1)), title=m.group(2).strip())
            continue
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            if title and not result.title:
                result.title = title
            continue
        if line.startswith("Nhân vật:"):
            in_characters = True
            continue
        if in_characters:
            cm = CHARACTER_RE.match(line)
            if cm:
                desc = cm.group(2).strip()
                hint = ""
                for key in ("giọng nam", "giọng nữ", "giọng kể", "giọng đọc"):
                    if key in desc.lower():
                        hint = key
                        break
                result.characters.append(
                    {"name": cm.group(1), "description": desc,
                     "voice_hint": hint})
                continue
            in_characters = False
        if current is None:
            continue  # header/metadata before the first scene: never spoken
        nm = NARRATOR_RE.match(line)
        if nm:
            current.lines.append(SpokenLine(
                speaker="narrator", kind="narration", text=nm.group(1).strip()))
            continue
        dm = DIALOGUE_RE.match(line)
        if dm:
            current.lines.append(SpokenLine(
                speaker=dm.group(1), kind="dialogue", text=dm.group(2).strip()))
            continue
        fm = FIELD_RE.match(line)
        if fm:
            field, value = fm.group(1), fm.group(2).strip()
            if field == "Bối cảnh":
                current.setting = value
            elif field == "Hành động":
                current.action_text = value
            elif field == "Âm thanh":
                current.audio_text = value
            elif field == "Yêu cầu animation":
                current.animation_reqs = value
            continue
        # Any other line inside a scene (e.g. unquoted description) is
        # treated as action/description text, never as speech.
        current.action_text = (current.action_text + " " + line).strip()
    finish_scene()
    if not result.scenes or not result.lines:
        raise ValueError("structured script has no scenes with spoken lines")
    return result
