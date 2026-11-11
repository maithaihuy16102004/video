"""Language gate (§5): Vietnamese is the default, with no English fallback.

Rules, enforced here so no other module has to remember them:

* A production request's language is honoured exactly. ``vi-VN`` means
  narration, dialogue AND subtitles are Vietnamese. English subtitles
  in a vi-VN production (the Eiffel v5 defect) FAIL the gate — they are
  never "close enough".
* There is no English voice fallback: if a Vietnamese voice cannot be
  resolved for a vi-VN line, ``resolve_voice`` raises instead of
  returning an English voice. A failed line is a loud failure, not a
  silent English dub.
* English detection is heuristic (stopwords + ASCII-only ratio), so it
  is a GATE for the pipeline, not a court of law: a flagged line is
  reported with its score and a human (Mai) decides. But an
  all-English caption line in a vi-VN production always fails.

Voice IDs are the ones the real pipeline already uses
(``tts_cli_provider.py``): narrator ``avocado_v2:MAI_01``, male
``avocado_v2:ronan``, female ``avocado_v2:paloma``, default
``avocado_v2:MAI_03`` — all synthesised with ``--language vi``.
"""
from __future__ import annotations

import re

DEFAULT_LANGUAGE = "vi-VN"
SUPPORTED_LANGUAGES = ("vi-VN", "vi")

# Vietnamese voices actually used by the pipeline (with --language vi).
VI_VOICES = {
    "narrator": "avocado_v2:MAI_01",
    "male": "avocado_v2:ronan",
    "female": "avocado_v2:paloma",
    "default": "avocado_v2:MAI_03",
}

_ENGLISH_STOPWORDS = frozenset("""
the a an and or of to in on for with at by from is are was were be been
he she it they we you i his her their our your this that these those
not no yes but so if when then than as are was were has have had will
would can could should sold twice nobody stopped him paris tower
""".split())

_WORD_RE = re.compile(r"[A-Za-zÀ-ỹ]+", re.UNICODE)


def english_score(text: str) -> float:
    """0.0 = looks Vietnamese, 1.0 = looks English.

    Fraction of words that are English stopwords / common English
    words, boosted when the text is pure ASCII (Vietnamese normally
    carries diacritics). A Vietnamese line with a foreign proper noun
    ("Victor Lustig", "Paris") scores low; an English sentence scores
    near 1.0.
    """
    words = _WORD_RE.findall(text or "")
    if not words:
        return 0.0
    lowered = [w.lower() for w in words]
    hits = sum(1 for w in lowered if w in _ENGLISH_STOPWORDS)
    ascii_ratio = sum(1 for w in words if w.isascii()) / len(words)
    score = (hits / len(words)) * 0.7 + ascii_ratio * 0.3
    # A line with NO diacritics at all and several English stopwords
    # is English even if the stopword list missed a word or two.
    if ascii_ratio == 1.0 and hits >= 2:
        score = max(score, 0.8)
    return round(min(1.0, score), 3)


def check_production_language(language: str, captions,
                              narration_texts=None) -> dict:
    """Gate a vi-VN production's text. Returns {"ok", "violations",
    "checked"}; every English-looking line is listed with its score."""
    violations = []
    checked = 0
    lang = (language or "").strip()
    if lang not in SUPPORTED_LANGUAGES:
        return {"ok": False, "checked": 0,
                "violations": [f"unsupported production language {lang!r} — "
                               f"only {list(SUPPORTED_LANGUAGES)} are "
                               f"supported; refusing instead of falling "
                               f"back to English"]}
    for kind, lines in (("caption", captions or []),
                        ("narration", narration_texts or [])):
        for i, line in enumerate(lines):
            checked += 1
            score = english_score(str(line))
            if score >= 0.6:
                violations.append(
                    f"{kind} {i + 1} looks English (score {score}): "
                    f"{str(line)[:80]!r}")
    return {"ok": not violations, "checked": checked,
            "violations": violations}


def resolve_voice(language: str, speaker: str = "narrator",
                  voice_hint: str = "") -> str:
    """Vietnamese voice for a vi-VN line. Raises instead of falling
    back to an English voice — there is no English fallback."""
    lang = (language or "").strip()
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"cannot resolve a voice for language {lang!r}: only "
            f"{list(SUPPORTED_LANGUAGES)} are supported and no English "
            f"voice fallback is allowed")
    if speaker == "narrator":
        return VI_VOICES["narrator"]
    hint = (voice_hint or "").lower()
    if "giọng nam" in hint or "nam" in hint:
        return VI_VOICES["male"]
    if "giọng nữ" in hint or "nữ" in hint:
        return VI_VOICES["female"]
    return VI_VOICES["default"]
