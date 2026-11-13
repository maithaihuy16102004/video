"""Expression library: the 8 base expressions, blends, negation-aware
interpretation, and timing-driven face modulation (blink + lip sync).

VISUAL QUALITY RECOVERY, Priority 5 (character acting). This module is
the single place that turns scripted expression text into face-system
parameters. It does NOT redefine the face: the 8 base expressions and
their numeric parameters live ONLY in
``animation/character_art.py`` (``EXPRESSIONS``) and are reused here by
import. The keyword vocabulary for the 8 families lives ONLY in
``trait_derivation.py`` (``_EXPRESSION_KEYWORDS``) and is reused here
by import; this module adds only the supplementary labels that have no
direct base (focused, determined, ...) as documented blends over the
8 bases, plus negation handling the base matcher does not have.

Negation (documented rule): a negation word immediately before an
expression keyword (within the 2 preceding words) CANCELS that match:
"không sợ" is NOT worried, it falls back to neutral (or to the next
non-negated match, e.g. "không sợ mà còn vui" -> happy). A keyword
phrase that itself begins with a negation word ("không chắc" =
uncertain) is a legitimate phrase, not a negation. NEGATION_WORDS is
the full documented list; "không" is by far the common Vietnamese
case. Double negation is NOT resolved ("không phải không vui" still
reads as negated "vui" -> neutral) -- that is a documented limit, not
a silent behaviour.

Lip sync (honest scope): ``speech_mouth_envelope`` is a TIMING
envelope, not phoneme synthesis. The TTS/audio stage (ATLAS owns it)
supplies speech segments; when word-level timing is available the
mouth gates per word, otherwise a syllabic-rate oscillation is used.
No phoneme, viseme or pronunciation data is fabricated here -- see
TTS_TIMING_INTERFACE. The renderer applies the envelope by overriding
``mouth_open`` in the expression param dict (see ``params_at``).
"""
from __future__ import annotations

import math
import random
import re

from .animation.character_art import (
    EXPRESSION_PARAMS,
    EXPRESSIONS,
    blend_expressions,
    expression_at,
)
from .cinematic_contracts import ExpressionTransition
from .trait_derivation import _EXPRESSION_KEYWORDS

__all__ = [
    "EXPRESSIONS",
    "EXPRESSION_PARAMS",
    "NEGATION_WORDS",
    "EXTENDED_EXPRESSIONS",
    "SUPPLEMENTARY_KEYWORDS",
    "SYLLABLE_RATE_HZ",
    "blend",
    "interpret",
    "interpret_detailed",
    "interpret_params",
    "blink_envelope",
    "speech_mouth_envelope",
    "params_at",
    "gaze_for_target",
    "blink_times_for",
    "validate_transitions",
    "schedule_transitions",
]

# --- Negation ------------------------------------------------------------
# Words that cancel an expression keyword when they appear within the
# 2 words immediately BEFORE the keyword (see module docstring).
# Vietnamese: không / chẳng / chả / chưa / đừng (+ intensified forms
# "không hề" / "chẳng hề", which tokenise to the same head word).
# English: not / never / no / n't (normalised to "not" before matching).
NEGATION_WORDS = frozenset({
    "không", "chẳng", "chả", "chưa", "đừng", "chớ",
    "not", "never", "no", "n't",
})

# How many words before a keyword are scanned for a negation word.
NEGATION_WINDOW = 2

# --- Extended labels -----------------------------------------------------
# Script EXPRESSION labels with no direct base expression. Each maps to
# a base expression plus an optional blend recipe (other base, u):
#   params = blend(base, other, u)   when a blend is given,
#   params = EXPRESSIONS[base]       otherwise.
# The blend recipes are deliberate and documented: "determined" is
# resolve without rage (half anger), "curious" is open attention
# (surprise leaning toward thought), "hopeful" is a softened happy,
# "naive" is open trust (happy leaning toward surprise), "serious" is
# gravity (neutral leaning toward anger). "deadpan" IS the neutral
# face (flat, no brows, line mouth). "focused" IS the thinking face
# (concentrated gaze, asymmetric brow). "awe" (Test F) is wonder at
# newly acquired power: the wide eyes + raised brows + open mouth of
# surprise, softened 35% toward happy's uplift (a slight smile) --
# awe is astonishment WITHOUT fear, so it must not collapse to
# worried. The blend recipe is the documented interpolation: every
# parameter morphs continuously through blend_expressions'
# smoothstep, and transitions into / out of awe validate through
# the same validate_transitions / schedule_transitions path as every
# other expression. Keywords that already belong to the surprised
# base family ("kinh ngạc", "sửng sốt", "choáng", "astonished") are
# deliberately NOT listed here: base families win ties, so listing
# them would be dead vocabulary. Only awe-specific words are listed.
EXTENDED_EXPRESSIONS = {
    "focused": {"base": "thinking", "blend": None},
    "determined": {"base": "angry", "blend": ("neutral", 0.55)},
    "curious": {"base": "surprised", "blend": ("thinking", 0.50)},
    "deadpan": {"base": "neutral", "blend": None},
    "hopeful": {"base": "happy", "blend": ("neutral", 0.50)},
    "naive": {"base": "happy", "blend": ("surprised", 0.40)},
    "serious": {"base": "neutral", "blend": ("angry", 0.30)},
    "relieved": {"base": "happy", "blend": ("neutral", 0.35)},
    "resolute": {"base": "angry", "blend": ("neutral", 0.65)},
    "attentive": {"base": "thinking", "blend": None},
    "awe": {"base": "surprised", "blend": ("happy", 0.35)},
    "tập trung": {"base": "thinking", "blend": None},
    "quyết tâm": {"base": "angry", "blend": ("neutral", 0.55)},
    "tò mò": {"base": "surprised", "blend": ("thinking", 0.50)},
    "vô cảm": {"base": "neutral", "blend": None},
    "hy vọng": {"base": "happy", "blend": ("neutral", 0.50)},
    "nghiêm túc": {"base": "neutral", "blend": ("angry", 0.30)},
}

# Supplementary keyword vocabulary: (extended label, keywords). Checked
# together with the 8 base families from trait_derivation; earliest
# keyword in the text wins (same rule as map_expression_text).
SUPPLEMENTARY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("focused", ("focused", "focus", "tập trung", "chú tâm",
                 "attentive", "concentrated")),
    ("determined", ("determined", "resolute", "quyết tâm",
                    "kiên quyết", "determination")),
    ("curious", ("curious", "tò mò", "curiosity")),
    ("deadpan", ("deadpan", "mặt lạnh", "thờ ơ", "dửng dưng",
                 "indifferent", "blank")),
    ("hopeful", ("hopeful", "hy vọng", "hope", "optimistic")),
    ("naive", ("naive", "ngây thơ", "khờ khạo", "innocent")),
    ("serious", ("serious", "nghiêm túc", "nghiêm nghị", "grave",
                 "solemn", "stern")),
    ("relieved", ("relieved", "nhẹ nhõm", "thở phào", "relief")),
    ("awe", ("awe", "awestruck", "awestricken", "wonderstruck",
             "in awe", "ngỡ ngàng", "trầm trồ", "thán phục")),
    # Base-name entries: word forms the base families do not list.
    # "Fear, exhaustion" (a real script label) needs "fear" and
    # "exhaustion": the base families list "fearful" and "exhausted"
    # only, and word-exact matching does not stem.
    ("worried", ("fear", "terror", "dread", "fright", "khiếp sợ",
                 "kinh hãi")),
    ("sad", ("exhaustion", "fatigue", "weariness", "kiệt sức",
             "mệt lả", "rã rời")),
    ("surprised", ("startle", "giật mình")),
]

# Syllabic rate for the speech mouth envelope when no word timing is
# available: Vietnamese conversational speech runs ~3-4 syllables/s.
SYLLABLE_RATE_HZ = 3.2

_WORD_RE = re.compile(r"[^\w']+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """Lowercased word tokens; n't is normalised to a negation word."""
    lowered = (text or "").lower().replace("n't", " not")
    lowered = lowered.replace("’", "'")
    return [t for t in _WORD_RE.split(lowered) if t]


def _phrase_spans(tokens: list[str], phrase: str) -> list[tuple[int, int]]:
    """Token spans [start, end) where ``phrase`` occurs, word-exact."""
    words = [w for w in _WORD_RE.split(phrase.lower()) if w]
    if not words:
        return []
    spans = []
    for i in range(len(tokens) - len(words) + 1):
        if tokens[i:i + len(words)] == words:
            spans.append((i, i + len(words)))
    return spans


def _is_negated(tokens: list[str], start: int, phrase: str) -> bool:
    """True when a negation word stands within NEGATION_WINDOW words
    BEFORE the match. A phrase that itself starts with a negation
    word ("không chắc") is a legitimate expression phrase, not a
    negation, and is never treated as negated."""
    first = _WORD_RE.split(phrase.lower())
    if first and first[0] in NEGATION_WORDS:
        return False
    lo = max(0, start - NEGATION_WINDOW)
    return any(t in NEGATION_WORDS for t in tokens[lo:start])


def _all_families() -> list[tuple[str, tuple[str, ...], str]]:
    """(label, keywords, source) for base + supplementary families.

    Base families come first (source "base"), so ties resolve in the
    base family order, exactly like trait_derivation.
    """
    families = [(name, tuple(kw), "base")
                for name, kw in _EXPRESSION_KEYWORDS]
    families.extend((label, tuple(kw), "extended")
                    for label, kw in SUPPLEMENTARY_KEYWORDS)
    return families


def interpret_detailed(text: str) -> dict:
    """Interpret free expression text, negation-aware.

    Returns {"expression": base name | None, "negated": bool,
    "matched_keyword": str | None, "source": "exact" | "base" |
    "extended" | None, "label": matched label | None}. "expression"
    is always one of the 8 base names (extended labels resolve to
    their base) or None when nothing matches. When every match is
    negated, expression is "neutral" and negated is True.
    """
    raw = (text or "").strip()
    if not raw:
        return {"expression": None, "negated": False,
                "matched_keyword": None, "source": None, "label": None}
    lowered = raw.lower()
    if lowered in EXPRESSIONS:
        return {"expression": lowered, "negated": False,
                "matched_keyword": lowered, "source": "exact",
                "label": lowered}
    tokens = _tokenize(raw)
    candidates = []  # (start, family order, keyword, label, source)
    any_negated = False
    for order, (label, keywords, source) in enumerate(_all_families()):
        for keyword in keywords:
            for (start, _end) in _phrase_spans(tokens, keyword):
                if _is_negated(tokens, start, keyword):
                    any_negated = True
                    continue
                candidates.append((start, order, keyword, label, source))
    if not candidates:
        if any_negated:
            return {"expression": "neutral", "negated": True,
                    "matched_keyword": None, "source": None,
                    "label": None}
        return {"expression": None, "negated": False,
                "matched_keyword": None, "source": None, "label": None}
    candidates.sort()
    _start, _order, keyword, label, source = candidates[0]
    if source == "extended" and label in EXTENDED_EXPRESSIONS:
        base = EXTENDED_EXPRESSIONS[label]["base"]
    else:
        # Base family, or a supplementary entry targeting a base name.
        base = label
    return {"expression": base, "negated": False,
            "matched_keyword": keyword, "source": source, "label": label}


def interpret(text: str) -> str | None:
    """Free expression text -> one of the 8 base expression names.

    Negation-aware (see module docstring): a negated emotion never
    returns the negated expression. Returns None when no expression
    family matches at all.
    """
    return interpret_detailed(text)["expression"]


def blend(expr_a, expr_b, u: float) -> dict:
    """Interpolate two expressions (names or param dicts).

    Thin wrapper over character_art.blend_expressions: every
    parameter morphs continuously with smoothstep.
    """
    return blend_expressions(expr_a, expr_b, u)


def interpret_params(text: str) -> dict | None:
    """Free expression text -> full expression param dict.

    Extended labels resolve to their documented blend recipes;
    base labels return the base params. Returns None when nothing
    matches. The returned dict is a fresh copy (safe to mutate for
    lip-sync / blink overrides).
    """
    detail = interpret_detailed(text)
    if detail["expression"] is None:
        return None
    if (detail["source"] == "extended"
            and detail["label"] in EXTENDED_EXPRESSIONS):
        recipe = EXTENDED_EXPRESSIONS[detail["label"]]
        base = recipe["base"]
        if recipe["blend"] is None:
            return dict(EXPRESSIONS[base])
        other, u = recipe["blend"]
        return blend_expressions(base, other, u)
    return dict(EXPRESSIONS[detail["expression"]])


def blink_envelope(t: float, blink_times, blink_duration: float = 0.12) -> float:
    """Eye-height multiplier at time ``t`` (1.0 = eyes open).

    ``blink_times`` is an iterable of blink START times (seconds).
    Each blink dips eye_h to 0.1 at its midpoint and returns to 1.0,
    smoothstepped on both halves. Outside blinks the multiplier is
    exactly 1.0, so stills are untouched.
    """
    mult = 1.0
    for start in blink_times or []:
        dt = t - float(start)
        if 0.0 <= dt <= blink_duration:
            half = blink_duration / 2.0
            if dt <= half:
                u = dt / half
            else:
                u = (blink_duration - dt) / half
            u = max(0.0, min(1.0, u))
            dip = 1.0 - 0.9 * (u * u * (3.0 - 2.0 * u))
            mult = min(mult, dip)
    return mult


# --- Lip sync: TTS timing interface --------------------------------------
# TTS_TIMING_INTERFACE (for ATLAS / the audio stage):
#   segments: list of {"start": float, "end": float, "words": [...]}
#   - "start"/"end": speech span in seconds, from the REAL TTS timing
#     (measured voice durations -- the same source the audio timeline
#     uses). The mouth is closed (envelope 0) outside these spans.
#   - "words" (optional): [(word_start, word_end), ...] word-level
#     timing when the TTS provider supplies it. The mouth gates per
#     word: it closes briefly between words instead of oscillating
#     continuously. When absent, a syllabic-rate oscillation
#     (SYLLABLE_RATE_HZ) is used inside the span.
#   No phoneme/viseme data is accepted or fabricated: this envelope
#   only ever claims "the mouth moves while speech is happening".

def speech_mouth_envelope(t: float, segments) -> float:
    """Mouth-openness (0..1) at time ``t`` from TTS speech segments.

    0 outside every segment. Inside a segment the mouth oscillates
    at the syllabic rate between 0.15 and 0.55 with 80 ms attack /
    release ramps at the edges, so speech starts and ends with a
    closing mouth instead of a pop. With word timing, the envelope
    gates per word (brief closures between words).
    """
    if not segments:
        return 0.0
    for seg in segments:
        start = float(seg["start"])
        end = float(seg["end"])
        if not (start <= t <= end):
            continue
        ramp = 0.08
        attack = min(1.0, max(0.0, (t - start) / ramp))
        release = min(1.0, max(0.0, (end - t) / ramp))
        gate = min(attack, release)
        words = seg.get("words") or []
        if words:
            in_word = False
            for ws, we in words:
                if float(ws) <= t <= float(we):
                    in_word = True
                    word_phase = t - float(ws)
                    break
            if not in_word:
                return 0.0
            osc = 0.35 + 0.20 * math.sin(2.0 * math.pi
                                         * SYLLABLE_RATE_HZ * word_phase)
        else:
            osc = 0.35 + 0.20 * math.sin(
                2.0 * math.pi * SYLLABLE_RATE_HZ * (t - start))
        # The gate multiplies the oscillation directly: the envelope
        # is exactly 0 at the segment edges (no pop from the 0
        # outside), ramps up over 80 ms, and reaches the full
        # oscillation mid-segment. (An earlier 0.35 floor left a
        # 0.12 discontinuity at the edges.)
        return max(0.0, min(1.0, osc * gate))
    return 0.0


def params_at(keyframes, t: float, speech_segments=None,
              blink_times=None) -> dict:
    """Expression params at time ``t`` with lip-sync + blink applied.

    ``keyframes`` is [(time, expression), ...] as in
    character_art.expression_at. The speech envelope RAISES
    mouth_open (max with the base value, so a surprised open mouth
    never closes mid-speech); the blink envelope MULTIPLIES eye_h.
    With no segments / blinks the result equals expression_at.
    """
    params = expression_at(keyframes, t)
    mouth = speech_mouth_envelope(t, speech_segments)
    if mouth > 0.0:
        params["mouth_open"] = max(params["mouth_open"], mouth)
    blink = blink_envelope(t, blink_times)
    if blink < 1.0:
        params["eye_h"] = params["eye_h"] * blink
    return params


def gaze_for_target(head_pos, target_pos, max_shift: float = 0.12):
    """Eye-shift (gx, gy) in units of head radius, for the ``gaze``
    parameter of draw_character_v4.

    The shift points from the head centre toward the target and is
    clamped to ``max_shift`` so the eyes never leave the face. This
    is EYE direction only; head orientation stays on the rig
    (head_look / head_track). Returns (0.0, 0.0) when the target
    coincides with the head.
    """
    dx = float(target_pos[0]) - float(head_pos[0])
    dy = float(target_pos[1]) - float(head_pos[1])
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return (0.0, 0.0)
    # Scale: a target one head-diameter away already earns the full
    # shift; nearer targets earn proportionally less.
    scale = min(1.0, dist / 120.0)
    shift = max_shift * scale
    return (dx / dist * shift, dy / dist * shift)


# --- Transition alignment (Phase D) --------------------------------------
# Directive: major expression changes align with a cut or a story
# beat; only micro-animation (blink, lipsync, eye/brow, breathing,
# small head, reactions) runs inside a shot, and faces must never
# freeze. These helpers VALIDATE and SCHEDULE -- they never silently
# re-time a transition: misalignments come back as warnings/violations
# for the caller (the shot planner owns timing; this module owns the
# expression semantics).

def blink_times_for(duration: float, seed: int = 0,
                    min_gap: float = 2.8, max_gap: float = 5.0
                    ) -> list[float]:
    """Deterministic blink schedule for ``duration`` seconds.

    Same seed -> same times (reproducible renders). Gaps are uniform
    in [min_gap, max_gap]; the first blink lands in the first
    ``min_gap`` seconds so no shot starts with a frozen face. Feeds
    ``blink_envelope`` / ``params_at``.
    """
    if duration <= 0:
        return []
    rng = random.Random(seed)
    times: list[float] = []
    t = rng.uniform(1.0, max(1.0, min_gap))
    while t < duration:
        times.append(round(t, 3))
        t += rng.uniform(min_gap, max_gap)
    return times


def _base_of(state) -> str | None:
    """Base expression name for a transition state: a base name
    passes through; extended labels and free text resolve via
    ``interpret``; unresolvable text returns None."""
    if state is None:
        return None
    text = str(state).strip().lower()
    if text in EXPRESSIONS:
        return text
    return interpret(text)


def _near(t: float, anchors, tol: float) -> bool:
    return any(abs(float(a) - float(t)) <= tol for a in anchors)


def validate_transitions(timed_transitions, cut_times=(),
                         beat_times=(), tol: float = 0.12) -> list[str]:
    """Check expression transitions against cut/beat alignment.

    ``timed_transitions`` is [(time, ExpressionTransition), ...]. A
    transition is MAJOR when the base expression changes (extended
    labels resolve to their base first). Rules:
      * major + align "micro" -> violation (micro is for
        within-shot micro-animation only);
      * major + align "cut" -> a cut time must be within ``tol``;
      * major + align "beat" -> a beat time must be within ``tol``;
      * unresolvable states -> violation (never silently dropped).
    Non-major transitions (same base) pass at any alignment. Returns
    violation strings; empty means clean. No timing is changed here.
    """
    violations: list[str] = []
    for t, transition in timed_transitions:
        base_from = _base_of(transition.from_state)
        base_to = _base_of(transition.to_state)
        if base_from is None or base_to is None:
            violations.append(
                f"t={float(t):.3f}: unresolvable expression state "
                f"{transition.from_state!r} -> {transition.to_state!r}")
            continue
        if base_from == base_to:
            continue
        if transition.align == "micro":
            violations.append(
                f"t={float(t):.3f}: major expression change "
                f"{base_from} -> {base_to} aligned 'micro' "
                "(major changes must align to a cut or a beat)")
        elif transition.align == "cut":
            if not _near(t, cut_times, tol):
                violations.append(
                    f"t={float(t):.3f}: cut-aligned change "
                    f"{base_from} -> {base_to} has no cut within "
                    f"{tol}s")
        elif transition.align == "beat":
            if not _near(t, beat_times, tol):
                violations.append(
                    f"t={float(t):.3f}: beat-aligned change "
                    f"{base_from} -> {base_to} has no beat within "
                    f"{tol}s")
    return violations


def schedule_transitions(requests, cut_times=(), beat_times=(),
                         tol: float = 0.12):
    """Schedule requested expression changes onto cut/beat anchors.

    ``requests`` is [(time, from_state, to_state, preferred_align),
    ...]. Returns (keyframes, transitions, warnings) where keyframes
    is [(time, to_state), ...] for ``params_at``/``expression_at``
    and transitions is [(time, ExpressionTransition), ...]. A major
    change with preferred align "cut"/"beat" SNAPS to the nearest
    anchor within ``tol`` (a warning records the move); with no
    anchor in range it keeps its requested time and a warning says
    so -- the planner, not this module, decides the final timing. A
    major change requesting "micro" keeps its time and alignment and
    earns a warning (``validate_transitions`` flags it as well).
    """
    keyframes: list[tuple[float, object]] = []
    transitions: list[tuple[float, ExpressionTransition]] = []
    warnings: list[str] = []
    for req_time, from_state, to_state, preferred in requests:
        t = float(req_time)
        base_from, base_to = _base_of(from_state), _base_of(to_state)
        major = (base_from is not None and base_to is not None
                 and base_from != base_to)
        if major and preferred in ("cut", "beat"):
            anchors = cut_times if preferred == "cut" else beat_times
            if anchors:
                nearest = min(anchors, key=lambda a: abs(float(a) - t))
                if abs(float(nearest) - t) <= tol:
                    if abs(float(nearest) - t) > 0.001:
                        warnings.append(
                            f"t={t:.3f}: snapped {base_from} -> "
                            f"{base_to} to {preferred} at "
                            f"{float(nearest):.3f}")
                    t = float(nearest)
                else:
                    warnings.append(
                        f"t={t:.3f}: no {preferred} within {tol}s "
                        f"for {base_from} -> {base_to}; keeping "
                        "requested time")
            else:
                warnings.append(
                    f"t={t:.3f}: no {preferred} times supplied for "
                    f"{base_from} -> {base_to}; keeping requested "
                    "time")
        elif major and preferred == "micro":
            warnings.append(
                f"t={t:.3f}: major change {base_from} -> {base_to} "
                "requested with align 'micro'; keeping requested "
                "time and alignment (validation will flag it)")
        transitions.append((t, ExpressionTransition(
            from_state=from_state, to_state=to_state, align=preferred)))
        keyframes.append((t, to_state))
    return keyframes, transitions, warnings
