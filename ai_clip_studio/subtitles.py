"""Subtitles for AI Clip Studio -- fixed 64 px, phrase-split, never shrunk.

This replaces the old caption ladder in the acceptance-loop renderers
(``draw_caption`` in render_cv.py / render_v4.py), which shrank the
font 64 -> 32 px to squeeze a long line into 2 lines and still cut the
last words (the 132-char final line lost its ending at 36 px).

Rules now:
  * the font is FIXED at 64 px for every phrase -- never scaled down;
  * a long line is split into short phrases (<= ``max_chars`` = 42
    chars each) at punctuation / speech rhythm first, then at word
    boundaries -- never in the middle of a word;
  * each phrase gets its own time window, proportional to its
    character count, so the full line is spoken and shown in full;
  * ``check_phone_legibility`` verifies the fixed 64 px font still
    covers >= 3% of frame height after a 720p downscale (phone check).
"""
from __future__ import annotations

import re

from PIL import ImageFont

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PX = 64            # FIXED -- never shrink, for any phrase
FIXED_FONT_PX = 64
MAX_CHARS = 42
MAX_LINES = 2           # max wrapped lines a single phrase may occupy
SAFE_WIDTH_PX = 1536    # 80% of 1920 -- the safe title width at 64 px

_font_cache = {}

# Clause splitter: a chunk ends at a clause/sentence punctuation mark.
_CLAUSE_RE = re.compile(r"[^,;:.!?\u2026\u2014-]+[,;:.!?\u2026\u2014-]?")
_PUNCT = ",;:.!?\u2026\u2014-"


def get_font(size=FONT_PX):
    """Cached DejaVuSans-Bold at the requested size (default: fixed 64)."""
    if size not in _font_cache:
        _font_cache[size] = ImageFont.truetype(FONT_PATH, size)
    return _font_cache[size]


def _pack_words(words, max_chars, phrases):
    """Greedily pack whole words into phrases of <= max_chars.

    A single word longer than max_chars is hard-split by characters
    (last resort only -- Vietnamese words are far shorter than this).
    """
    cur = ""
    for w in words:
        if len(w) > max_chars:
            if cur:
                phrases.append(cur)
                cur = ""
            for i in range(0, len(w), max_chars):
                phrases.append(w[i:i + max_chars])
            continue
        trial = (cur + " " + w).strip()
        if len(trial) <= max_chars:
            cur = trial
        else:
            if cur:
                phrases.append(cur)
            cur = w
    if cur:
        phrases.append(cur)


def _wrap_lines(phrase, font=None, max_w=SAFE_WIDTH_PX):
    """Word-wrap a phrase at the fixed font; returns the line list."""
    font = font or get_font(FONT_PX)
    lines, cur = [], ""
    for w in phrase.split():
        trial = (cur + " " + w).strip()
        if font.getlength(trial) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def split_subtitle(text, max_chars=MAX_CHARS, max_lines=MAX_LINES):
    """Split a (possibly long) line into short phrases.

    Cut order: (1) clause/sentence punctuation, (2) word boundaries.
    Never cuts inside a word. Every phrase is <= ``max_chars`` chars
    and wraps to <= ``max_lines`` lines at the fixed 64 px font inside
    the safe title width (a phrase that would need more lines is
    split further by words). Returns a list of phrases; the phrases
    joined with single spaces reproduce the input (whitespace
    normalised). An empty/blank line returns [].
    """
    if not text or not text.strip():
        return []
    text = " ".join(str(text).split())
    font = get_font(FONT_PX)
    phrases = []
    # 1) split into clause chunks at punctuation, keep the punctuation
    clauses = [c.strip() for c in _CLAUSE_RE.findall(text) if c.strip()]
    if not clauses:  # no punctuation at all -- fall back to word packing
        clauses = [text]
    cur = ""
    for clause in clauses:
        if len(clause) > max_chars:
            if cur:
                phrases.append(cur)
                cur = ""
            _pack_words(clause.split(), max_chars, phrases)
            continue
        trial = (cur + " " + clause).strip() if cur else clause
        if len(trial) <= max_chars:
            cur = trial
        else:
            if cur:
                phrases.append(cur)
            cur = clause
    if cur:
        phrases.append(cur)
    # 2) enforce the max-lines guard at the fixed font: a phrase that
    # would wrap past max_lines is re-split by words.
    final = []
    for p in phrases:
        if len(_wrap_lines(p, font)) <= max_lines:
            final.append(p)
        else:
            _pack_words(p.split(), max_chars, final)
    return final


def phrase_windows(line_start, line_end, phrases):
    """Split [line_start, line_end] into one window per phrase,
    proportional to each phrase's character count. Returns a list of
    dicts {"phrase", "start", "end"} that exactly spans the line
    (the last window absorbs float rounding)."""
    phrases = list(phrases or [])
    if not phrases:
        return []
    total = float(line_end) - float(line_start)
    weights = [max(1, len(p)) for p in phrases]
    wsum = float(sum(weights))
    windows, t = [], float(line_start)
    for i, p in enumerate(phrases):
        if i < len(phrases) - 1:
            end = t + total * weights[i] / wsum
        else:
            end = float(line_end)
        windows.append({"phrase": p, "start": round(t, 3),
                        "end": round(end, 3)})
        t = end
    return windows


def check_phone_legibility(frame_720px_width, font_px=FONT_PX):
    """Phone check: does the fixed font cover >= 3% of frame height
    after downscaling the 1920x1080 frame to 720p?

    ``frame_720px_width`` is the downscaled width (1280 for 720p);
    the downscaled height is width * 9/16. The font scales by the
    same factor, so the ratio is font_px / 1080 -- 64 px gives 5.9%.
    Returns {"downscaled_font_px", "ratio", "min_ratio", "passes"}.
    """
    down_h = float(frame_720px_width) * 9.0 / 16.0
    scaled = float(font_px) * down_h / 1080.0
    ratio = scaled / down_h if down_h else 0.0
    return {
        "frame_720px_width": frame_720px_width,
        "downscaled_font_px": round(scaled, 2),
        "ratio": round(ratio, 4),
        "min_ratio": 0.03,
        "passes": bool(ratio >= 0.03),
    }


def draw_phrase(draw, phrase, width=1920, height=1080, font_px=FONT_PX,
                fill="white", y=None):
    """Draw ONE phrase centred near the bottom, at the FIXED font size
    (never shrunk), with a black outline for legibility. Returns the
    (x, y, font_size) used -- font_size is always ``font_px`` (64)."""
    font = get_font(font_px)
    lines = _wrap_lines(phrase, font)
    line_h = int(font_px * 1.22)
    total_h = len(lines) * line_h
    y0 = (height - 40 - total_h) if y is None else y
    for i, ln in enumerate(lines):
        w = font.getlength(ln)
        x = (width - w) / 2.0
        yy = y0 + i * line_h
        for dx in (-3, 0, 3):
            for dy in (-3, 0, 3):
                draw.text((x + dx, yy + dy), ln, font=font, fill="black")
        draw.text((x, yy), ln, font=font, fill=fill)
    return ((width - font.getlength(lines[0])) / 2.0 if lines else 0.0,
            y0, font_px)


def draw_subtitle(draw, text, width=1920, height=1080, font_px=FONT_PX):
    """Draw a full line as stacked fixed-64px phrases (for static
    checks / single-frame captions). For timed playback use
    ``split_subtitle`` + ``phrase_windows`` + ``draw_phrase`` per
    window instead. Returns the list of phrases drawn."""
    phrases = split_subtitle(text)
    line_h = int(font_px * 1.22)
    for i, p in enumerate(phrases):
        draw_phrase(draw, p, width=width, height=height,
                    font_px=font_px,
                    y=height - 40 - (len(phrases) - i) * line_h)
    return phrases
