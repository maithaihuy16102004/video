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
CHARACTER_RE = re.compile(r"^-\s*([A-ZÀ-Ỹ][\wÀ-ỹ]{0,15}(?: [A-ZÀ-Ỹ][\wÀ-ỹ]{0,15})?)\s*:\s*(.+)$")
QUOTED_RE = re.compile(r"\"([^\"]+)\"")

# Generic Vietnamese action-verb map: regex -> action cue. Phrase
# context decides: a bare verb never stages what the sentence does
# not say. "cúi đầu" (bow the head) is head_tilt, NEVER bend_pick;
# bend_pick fires only on explicit ground-pickup phrasing; "lấy ...
# từ túi" (take from a pocket/container) is take_out, never a
# ground-staged take; a bare "lấy"/"nhặt" is a plain take whose
# object source is left to the prop system (never assumed to be the
# ground). Matching is span-greedy (see _accepted_cue_matches): when
# two patterns start at the same character, the longest span wins
# (head_tilt's "cúi đầu" is protected from the pickup patterns by
# their gap guards, walk_fast beats walk on "đi nhanh", take_out
# beats take on "lấy ví từ túi áo"). Nothing here is
# story-specific.
ACTION_VERBS: list[tuple[str, str]] = [
    (r"\bchạy\b", "run"),
    (r"\bđi nhanh\b|\bvội\b", "walk_fast"),
    (r"\bđi\b|\bbước\b", "walk"),
    (r"\bdừng\b", "stop"),
    (r"\bcúi đầu\b|\bcúi mặt\b|\bngẩng đầu\b|\bnghiêng đầu\b",
     "head_tilt"),
    # Ground pickup ONLY: "cúi (xuống) nhặt" (contiguous or split
    # around a short gap), or "nhặt" + a ground marker / "lên"
    # within the same clause. A bare "cúi" never fires this rule.
    (r"\bcúi(\s+xuống)?\s+nhặt\b"
     r"|\bcúi(\s+xuống)?\b(?:(?!\b(đầu|mặt)\b)[^.!?;\n]){0,20}\bnhặt\b"
     r"|\bnhặt\b[^.!?;\n,]{0,30}\b(dưới đất|trên đất|mặt đất"
     r"|dưới chân|đánh rơi|rơi xuống|rớt xuống|lên)\b",
     "bend_pick"),
    (r"\bđưa (chiếc )?(ví|tiền|đồ|thư|phong bì)\b"
     r"|\bđưa\b[^.!?;\n,]{0,25}\bcho\b|\btrao\b", "give"),
    # Take OUT of a pocket/container: the source is explicit in the
    # phrase, so staging must come from the pocket, never the ground.
    (r"\blấy\b[^.!?;\n,]{0,25}\btừ\s+(túi áo|túi quần|túi ngực|túi"
     r"|ba lô)\b"
     r"|\blấy\b[^.!?;\n,]{0,25}\bra khỏi\b"
     r"|\bmóc\b|\brút\b", "take_out"),
    (r"\bnhận\b|\blấy\b|\bnhặt\b", "take"),
    (r"\bmở ví\b|\bmở túi\b|\bmở\b", "open"),
    (r"\bcất\b|\bbỏ vào\b", "put_away"),
    (r"\bgiơ tay\b|\bchào\b", "wave"),
    (r"\bquay đầu\b|\bngoái\b", "turn_back"),
    (r"\bmỉm cười\b|\bcười\b", "smile"),
    (r"\bnhìn quanh\b|\bnhìn xuống\b|\bnhìn\b", "look"),
    (r"\bkiểm tra\b|\btìm\b", "search"),
    # "board" requires a VEHICLE: bare "bước lên" (step up) also
    # matches stairs and thrones -- "Zeus bước lên bậc thang
    # Olympus" summoned a modern bus behind every Olympus shot of
    # the Zeus re-render. Mirrors the compiler's BOARD tuple.
    (r"\bbước lên xe\b|\blên xe\b", "board"),
    (r"\bngồi\b", "sit"),
    (r"\bđứng\b", "stand"),
    (r"\bmưa\b", "rain"),
    # "bus" requires "xe buýt": bare "xe" is any vehicle (car,
    # carriage, bicycle) and must not summon a modern bus.
    (r"\bxe buýt\b", "bus"),
]

_COMPILED_VERBS = [(re.compile(pattern), cue)
                   for pattern, cue in ACTION_VERBS]


def _cue_match_spans(text: str):
    """All raw matches: (start, rule_order, end, cue, pattern, text).

    Matched against the lowercased text; ``text`` in each tuple is
    the matched span (lowercased). Overlapping matches are resolved
    by the caller (span-greedy: earliest start, then earliest rule).
    """
    low = text.lower()
    matches = []
    for order, (pattern_re, cue) in enumerate(_COMPILED_VERBS):
        for found in pattern_re.finditer(low):
            matches.append((found.start(), order, found.end(), cue,
                            pattern_re.pattern, found.group(0)))
    return matches


def _accepted_cue_matches(text: str):
    """Non-overlapping matches in text order (first-seen order).

    Greedy by (start, longest span, rule order): a match is
    accepted only when its span does not intersect an
    already-accepted span, so the longest phrase wins the tokens it
    covers ("bước lên xe" wins over "bước", "đi nhanh" over "đi",
    "lấy ví từ túi áo" over a bare "lấy" take). A head bow can never
    be swallowed by the discontinuous pickup pattern: its gap
    refuses to cross "đầu"/"mặt", so "cúi đầu" stays head_tilt.
    Duplicate cues collapse to their first occurrence, as
    extract_action_cues has always done.
    """
    ordered = sorted(_cue_match_spans(text),
                     key=lambda m: (m[0], -m[2], m[1]))
    # Span competition first: every match competes for its tokens,
    # even when its cue already fired elsewhere -- a duplicate
    # bend_pick span must still block a bare "nhặt" take from the
    # same tokens (a second ground pickup later in the text).
    accepted = []
    for match in ordered:
        start, _order, end, _cue, _pattern, _text = match
        if any(start < other[2] and other[0] < end
               for other in accepted):
            continue
        accepted.append(match)
    # Then collapse duplicate cues to their first occurrence.
    seen_cues: set[str] = set()
    deduped = []
    for match in accepted:
        if match[3] in seen_cues:
            continue
        seen_cues.add(match[3])
        deduped.append(match)
    return deduped


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
    cues = [m[3] for m in _accepted_cue_matches(text)]
    if "walk_fast" in cues and "walk" in cues:
        cues.remove("walk")
    if "board" in cues and "walk" in cues:
        cues.remove("walk")
    return cues


def extract_action_cues_detailed(
        text: str, *, source_script_hash: str | None = None,
        source_scene_id: str | None = None,
        source_shot_id: str | None = None,
        source_directive_id: str | None = None) -> list[dict]:
    """Cue records with provenance, 1:1 with extract_action_cues().

    Every record carries the provenance contract shared with the
    action compiler: source_script_hash / source_scene_id /
    source_shot_id / source_directive_id (caller-supplied, None
    when unknown -- never invented), action_origin
    ("PLANNER_INFERRED_ACTION", a semantic_contracts ActionOrigin),
    inference_reason (the matched pattern and span), and
    authorization_status ("INFERRED", a semantic_contracts
    AuthorizationStatus). Cue records are PLANNER_INFERRED_ACTION
    by construction: they are keyword inferences from action
    text, not verbatim directive actions, and the contradiction
    check (action_compiler.detect_conflicts) may resolve one
    against a higher-authority compiled event. The enum literals
    must stay members of semantic_contracts (guarded by
    test_cue_extraction).
    """
    records = []
    for start, _order, end, cue, pattern, matched in \
            _accepted_cue_matches(text):
        records.append({
            "cue": cue,
            "matched_text": matched,
            "match_start": start,
            "match_end": end,
            "pattern": pattern,
            "source_script_hash": source_script_hash,
            "source_scene_id": source_scene_id,
            "source_shot_id": source_shot_id,
            "source_directive_id": source_directive_id,
            "action_origin": "PLANNER_INFERRED_ACTION",
            "inference_reason": (
                f"keyword pattern {pattern!r} matched {matched!r}"),
            "authorization_status": "INFERRED",
        })
    # Same generic-cue suppressions as extract_action_cues, so the
    # records stay 1:1 with the cue list.
    cues = [r["cue"] for r in records]
    if "walk_fast" in cues and "walk" in cues:
        records = [r for r in records if r["cue"] != "walk"]
        cues = [r["cue"] for r in records]
    if "board" in cues and "walk" in cues:
        records = [r for r in records if r["cue"] != "walk"]
    return records


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
                # One entry per character: scripts repeat the cast list
                # in every scene; keep the first description.
                if cm.group(1) not in {c["name"] for c in result.characters}:
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
