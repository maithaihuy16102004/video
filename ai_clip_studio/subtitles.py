"""Subtitles for AI Clip Studio -- fixed 64 px, phrase-split, never shrunk.

This replaces the old caption ladder in the acceptance-loop renderers
(``draw_caption`` in render_cv.py / render_v4.py), which shrank the
font 64 -> 32 px to squeeze a long line into 2 lines and still cut the
last words (the 132-char final line lost its ending at 36 px).

Rules now:
  * the font is FIXED at 64 px for every phrase -- never scaled down;
  * a long line is split into short phrases (<= ``max_chars`` = 30
    chars each) at punctuation / speech rhythm first, then at word
    boundaries -- never in the middle of a word, and never inside a
    Vietnamese compound (``_COMPOUND_NGRAMS``) or between a
    quantifier and its number ("số 16", "năm 1914");
  * each phrase gets its own time window, proportional to its
    character count, so the full line is spoken and shown in full;
  * ``check_phone_legibility`` verifies the fixed 64 px font still
    covers >= 3% of frame height after a 720p downscale (phone check).

Compound protection is SHARED by the phrase tiling
(``split_subtitle``) and the render wrap (``_wrap_lines``): both
pack the same glued units, so a compound can split in neither
place. The tester found both failure modes on the Zeus/Ep1
re-renders (9 time-splits + 5 wrap splits); fixing only one side
leaves the other.
"""
from __future__ import annotations

import re

from PIL import ImageFont

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PX = 64            # FIXED -- never shrink, for any phrase
FIXED_FONT_PX = 64
MAX_CHARS = 30
MAX_LINES = 2           # max wrapped lines a single phrase may occupy
SAFE_WIDTH_PX = 1536    # 80% of 1920 -- the safe title width at 64 px

_font_cache = {}

# Clause splitter: a chunk ends at a clause/sentence punctuation mark.
_CLAUSE_RE = re.compile(r"[^,;:.!?\u2026\u2014-]+[,;:.!?\u2026\u2014-]?")
_PUNCT = ",;:.!?\u2026\u2014-"
_QUOTE_CHARS = "\u201c\u201d\u2018\u2019\"'\u00ab\u00bb"
_STRIP_CHARS = _PUNCT + _QUOTE_CHARS

# Vietnamese compounds that must never split across a phrase or wrap
# boundary. A general LANGUAGE resource (like the expression keyword
# tables), not story data: every entry is an unambiguous compound,
# and the failure mode of a glue is a slightly longer phrase, never
# a changed meaning. The first 19 are the compounds the tester
# caught splitting on the Zeus/Ep1 re-renders; the rest are
# high-frequency compounds of the same shape. The list grows from
# tester evidence, never from guessing a script's intent. Matching
# is on normalised tokens (lowercase, punctuation stripped), so
# "tự.", "bại…" and "Vị" all match. Three-token compounds are
# matched longest-first ("anh chị em" wins over "chị em").
_COMPOUND_NGRAMS = frozenset({
    # Tester-observed splits (round-1 re-renders).
    ("tương", "tự"), ("quyền", "lực"), ("vị", "thần"),
    ("đánh", "bại"), ("giải", "thoát"), ("tham", "chiến"),
    ("tạo", "ra"), ("bắt", "đầu"), ("mặc", "áo"),
    ("hùng", "dũng"), ("công", "dân"), ("đoàn", "quân"),
    ("sở", "hữu"), ("tiết", "kiệm"), ("phương", "pháp"),
    ("anh", "chị", "em"), ("anh", "em"), ("chị", "em"),
    ("anh", "chị"),
    # High-frequency compounds of the same shape.
    ("gia", "đình"), ("đất", "nước"), ("con", "người"),
    ("thời", "gian"), ("cuộc", "sống"), ("chiến", "tranh"),
    ("hạnh", "phúc"), ("tình", "yêu"), ("cha", "mẹ"),
    ("quân", "đội"), ("mặt", "trận"), ("lịch", "sử"),
    ("tương", "lai"), ("cuối", "cùng"), ("bây", "giờ"),
    ("hôm", "nay"), ("thế", "giới"), ("sức", "mạnh"),
    ("chiến", "thắng"), ("thất", "bại"), ("thành", "công"),
    ("khó", "khăn"), ("nguy", "hiểm"), ("tự", "do"),
    ("hòa", "bình"), ("trái", "tim"), ("đôi", "mắt"),
    ("bàn", "tay"), ("ánh", "sáng"), ("bầu", "trời"),
    ("mặt", "trời"), ("con", "đường"), ("ngôi", "nhà"),
    ("câu", "chuyện"), ("hòn", "đá"), ("ngọn", "lửa"),
    ("cơn", "bão"), ("người", "bạn"), ("trẻ", "con"),
    ("đứa", "trẻ"), ("vợ", "chồng"), ("hàng", "xóm"),
    ("đồng", "minh"), ("thiên", "thần"), ("hoàng", "đế"),
    ("công", "chúa"), ("bác", "sĩ"), ("cảnh", "sát"),
    ("nhà", "văn"), ("ca", "sĩ"), ("bộ", "binh"),
    ("dự", "bị"), ("giáng", "sinh"), ("phía", "tây"),
    # Second audit pass (2026-11-14): every remaining split found by
    # scanning ALL phrase/wrap boundaries of both real scripts.
    ("nói", "dối"), ("bình", "thường"), ("bùng", "nổ"),
    ("cực", "kỳ"), ("giải", "cứu"), ("giải", "quyết"),
    ("kết", "hôn"), ("kết", "thúc"), ("rung", "chuyển"),
    ("thần", "thánh"), ("thay", "đổi"), ("tác", "dụng"),
    ("tìm", "thấy"), ("trăm", "tay"), ("vũ", "khí"),
    ("nấu", "ăn"), ("sấm", "sét"), ("dựa", "trên"),
    ("gia", "nhập"), ("hang", "động"), ("khổng", "lồ"),
    ("lớn", "lên"), ("đồng", "cỏ"), ("cuộc", "chiến"),
    ("đâu", "đó"), ("tập", "sau"), ("nữ", "thần"),
    ("chúng", "tôi"), ("chúng", "ta"), ("như", "thế", "nào"),
    ("như", "thế"), ("tiên", "tri"), ("nuốt", "sống"),
    ("có", "thể"), ("hỗn", "hợp"), ("nguyên", "văn"),
    ("vấn", "đề"), ("kế", "hoạch"), ("có", "hậu"),
    ("mỗi", "khi"), ("phức", "tạp"), ("xảy", "ra"),
    ("kiểm", "tra"), ("hoành", "tráng"), ("xe", "buýt"),
})

# Single-token prefixes that glue RIGHT to the following unit: the
# ordinal marker "thứ" ("thứ sáu") and the classifiers "con/cái/
# chiếc" ("con dê", "chiếc ví"), which dangle unreadably at a
# phrase end. Only a unit that IS exactly the prefix glues (a
# compound merely ending in one, e.g. "trẻ con", does not). The
# pronoun use of "con" glues harmlessly (pronoun + verb stay
# together; the phrase is slightly longer, never reworded).
_PREFIX_GLUE = frozenset({"thứ", "con", "cái", "chiếc"})

# A bare number (with optional thousands separators) glues to the
# preceding unit: "số 16", "năm 1914", "tháng 8". The number alone
# on the next line/phrase reads as a dangling fragment.
_DIGIT_RE = re.compile(r"^\d{1,3}([.,]\d{3})*$|^\d+$")


def _norm_token(tok):
    return tok.strip(_STRIP_CHARS).lower()


def _glue_units(words):
    """Group space-separated tokens into unbreakable units.

    Longest-match compound scan (3-gram, then 2-gram) over
    normalised tokens, then bare numbers attach to the preceding
    unit. Original text (case, punctuation) is preserved inside
    each unit; units joined with single spaces reproduce the
    input words exactly.
    """
    normed = [_norm_token(w) for w in words]
    units = []
    i = 0
    while i < len(words):
        matched = None
        for n in (3, 2):
            if i + n <= len(words) and \
                    tuple(normed[i:i + n]) in _COMPOUND_NGRAMS:
                matched = n
                break
        if matched:
            units.append(" ".join(words[i:i + matched]))
            i += matched
        else:
            units.append(words[i])
            i += 1
    glued = []
    for u in units:
        first = _norm_token(u.split()[0])
        if glued and _DIGIT_RE.match(first):
            glued[-1] = glued[-1] + " " + u
        else:
            glued.append(u)
    merged = []
    for u in glued:
        if merged and _norm_token(merged[-1]) in _PREFIX_GLUE:
            merged[-1] = merged[-1] + " " + u
        else:
            merged.append(u)
    return merged


def get_font(size=FONT_PX):
    """Cached DejaVuSans-Bold at the requested size (default: fixed 64)."""
    if size not in _font_cache:
        _font_cache[size] = ImageFont.truetype(FONT_PATH, size)
    return _font_cache[size]


def _pack_words(words, max_chars, phrases):
    """Greedily pack whole GLUED UNITS into phrases of <= max_chars.

    Units come from :func:`_glue_units`, so a compound or a number
    never straddles a phrase boundary. A single unit longer than
    max_chars is hard-split by characters (last resort only --
    Vietnamese words and compounds are far shorter than this).
    """
    cur = ""
    for u in _glue_units(list(words)):
        if len(u) > max_chars:
            if cur:
                phrases.append(cur)
                cur = ""
            for i in range(0, len(u), max_chars):
                phrases.append(u[i:i + max_chars])
            continue
        trial = (cur + " " + u).strip()
        if len(trial) <= max_chars:
            cur = trial
        else:
            if cur:
                phrases.append(cur)
            cur = u
    if cur:
        phrases.append(cur)


def _wrap_lines(phrase, font=None, max_w=SAFE_WIDTH_PX):
    """Word-wrap a phrase at the fixed font; returns the line list.

    Wrapping packs the same glued units as the phrase tiling
    (:func:`_glue_units`), so a compound or a number can split at
    neither the phrase boundary nor the wrap. Orphan backstop: a
    final line holding a single unit pulls a unit back from the
    previous line (keeping every line inside the width), so an
    unlisted compound still cannot strand a lone syllable on its
    own line. A two-unit phrase that cannot fit one line cannot
    be helped.
    """
    font = font or get_font(FONT_PX)
    lines, cur = [], []
    for u in _glue_units(phrase.split()):
        trial = " ".join(cur + [u])
        if font.getlength(trial) <= max_w:
            cur.append(u)
        else:
            if cur:
                lines.append(cur)
            cur = [u]
    if cur:
        lines.append(cur)
    while len(lines) >= 2:
        if len(lines[-1]) >= 2:
            break
        prev = lines[-2]
        if len(prev) <= 1:
            break
        new_last = " ".join([prev[-1]] + lines[-1])
        if font.getlength(new_last) > max_w:
            break
        lines[-2] = prev[:-1]
        lines[-1] = [prev[-1]] + lines[-1]
    return [" ".join(ln) for ln in lines]


def _merge_short_phrases(phrases, max_chars, min_len=5):
    """Merge fragment phrases into a neighbour -- WITHOUT ever
    exceeding ``max_chars``.

    A phrase of <= ``min_len`` stripped characters ("rất…", "mình.",
    a lone closing quote) flashes for a fraction of a frame in a
    short line and reads as a dangling fragment; it belongs with
    its neighbour. The fragment joins the neighbour that keeps the
    result within ``max_chars`` when one does (previous preferred,
    restoring its own clause). Round 9: when NEITHER neighbour
    fits, the fragment stays standalone -- the old fallback joined
    the shorter neighbour anyway and produced 31-34 char phrases
    ("nơi ánh đuốc không bao giờ tắt.", "chỉ là một hòn bi ve bị
    nung nóng."), breaking the <=30 contract the tester measures.
    A standalone fragment's window is stretched to one frame by
    ``phrase_windows`` instead, so it never flashes. The join is
    lossless: the phrases joined with single spaces reproduce the
    input exactly. A lone short phrase (a line that IS "À.") is
    left alone.
    """
    out = list(phrases)
    changed = True
    while changed and len(out) > 1:
        changed = False
        for i, p in enumerate(out):
            if len(p.strip(_STRIP_CHARS + " ")) > min_len:
                continue
            prev_len = len(out[i - 1]) + 1 + len(p) if i > 0 else None
            next_len = len(p) + 1 + len(out[i + 1]) \
                if i + 1 < len(out) else None
            fits_prev = prev_len is not None and prev_len <= max_chars
            fits_next = next_len is not None and next_len <= max_chars
            if fits_prev:
                out[i - 1] = out[i - 1] + " " + p
                del out[i]
            elif fits_next:
                out[i + 1] = p + " " + out[i + 1]
                del out[i]
            else:
                # Neither neighbour fits: leave the fragment
                # standalone (phrase_windows stretches its window).
                continue
            changed = True
            break
    return out


def split_subtitle(text, max_chars=MAX_CHARS, max_lines=MAX_LINES):
    """Split a (possibly long) line into short phrases.

    Cut order: (1) clause/sentence punctuation, (2) word boundaries.
    Never cuts inside a word. Every phrase is <= ``max_chars`` chars
    (the fragment merge never exceeds it -- a fragment with no
    fitting neighbour stays standalone) and wraps to <= ``max_lines``
    lines at the fixed 64 px font inside the safe title width (a
    phrase that would need more lines is split further by words).
    Returns a list of phrases; the phrases joined with single
    spaces reproduce the input (whitespace normalised). An
    empty/blank line returns [].
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
    # 3) merge fragment phrases (a lone "rất…" or closing quote) into
    # a neighbour: a fragment's time window can fall below one frame,
    # which the unified timeline rejects, and it flashes unreadably.
    return _merge_short_phrases(final, max_chars)


def phrase_windows(line_start, line_end, phrases):
    """Split [line_start, line_end] into one window per phrase,
    proportional to each phrase's character count. Returns a list of
    dicts {"phrase", "start", "end"} that exactly spans the line
    (the last window absorbs float rounding). A window shorter than
    one frame (1/24 s) is STRETCHED to one frame by moving its
    boundary into the neighbour with room to spare: the phrases
    stay separate (no display phrase ever exceeds ``max_chars``
    by joining), the span stays exact, and no phrase flashes.
    Only a line too short for every window to reach one frame
    (under two frames for two phrases) still joins phrases --
    pathological, and the join is the only way to keep the text.
    A line shorter than one frame in total keeps its single
    window."""
    phrases = list(phrases or [])
    if not phrases:
        return []
    total = float(line_end) - float(line_start)
    weights = [max(1, len(p)) for p in phrases]
    wsum = float(sum(weights))
    bounds = [float(line_start)]
    for w in weights[:-1]:
        bounds.append(bounds[-1] + total * w / wsum)
    bounds.append(float(line_end))
    bounds = [round(b, 3) for b in bounds]
    # Stretch sub-frame windows (checked on the rounded bounds: a
    # 0.041 s rounded window can still map to one frame).
    spans = [[phrases[i], bounds[i], bounds[i + 1]]
             for i in range(len(phrases))]
    changed = True
    while changed and len(spans) > 1:
        changed = False
        for i, (p, s, e) in enumerate(spans):
            if e - s >= 0.042:
                continue
            # 1 ms margin: the moved boundary is rounded to 3
            # decimals, and a stretch landing at 0.0415 would
            # re-trigger the loop on rounding noise alone.
            need = 0.043 - (e - s)
            # Steal from the previous window when it can spare
            # the time and stay at/above one frame itself.
            if i > 0 and spans[i - 1][2] - spans[i - 1][1] \
                    - need >= 0.042:
                spans[i - 1][2] = round(spans[i - 1][2] - need, 3)
                spans[i][1] = spans[i - 1][2]
            elif i + 1 < len(spans) and spans[i + 1][2] \
                    - spans[i + 1][1] - need >= 0.042:
                spans[i + 1][1] = round(spans[i + 1][1] + need, 3)
                spans[i][2] = spans[i + 1][1]
            else:
                # Chain shift: neither neighbour can spare the
                # time, but a farther window can. Move every
                # boundary between this span and the longest
                # window by `need` toward it: this span grows,
                # the longest shrinks, intermediates keep their
                # lengths, the total stays exact.
                donor = None
                for j, (_p, _s, _e) in enumerate(spans):
                    if j != i and _e - _s - need >= 0.042 and (
                            donor is None
                            or _e - _s > spans[donor][2]
                            - spans[donor][1]):
                        donor = j
                if donor is None:
                    # Truly pathological: the line is too short
                    # for every window to reach one frame. Join.
                    if i > 0:
                        spans[i - 1][0] = spans[i - 1][0] + " " + p
                        spans[i - 1][2] = e
                        del spans[i]
                    else:
                        spans[i + 1][0] = p + " " + spans[i + 1][0]
                        spans[i + 1][1] = s
                        del spans[i]
                elif donor < i:
                    for k in range(donor + 1, i + 1):
                        spans[k - 1][2] = round(
                            spans[k - 1][2] - need, 3)
                        spans[k][1] = spans[k - 1][2]
                else:
                    for k in range(i + 1, donor + 1):
                        spans[k - 1][2] = round(
                            spans[k - 1][2] + need, 3)
                        spans[k][1] = spans[k - 1][2]
            changed = True
            break
    return [{"phrase": p, "start": round(s, 3), "end": round(e, 3)}
            for p, s, e in spans]


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
                fill="white", y=None, lift_px=0.0):
    """Draw ONE phrase centred near the bottom, at the FIXED font size
    (never shrunk), with a black outline for legibility. Returns the
    (x, y, font_size) used -- font_size is always ``font_px`` (64).
    ``lift_px`` raises the block above the default bottom margin
    (map shots lift clear of the attribution band)."""
    font = get_font(font_px)
    lines = _wrap_lines(phrase, font)
    line_h = int(font_px * 1.22)
    total_h = len(lines) * line_h
    # Merge (round-1 map lift + fdee737 safe-title pin): the default
    # position is the safe-title line, raised further by lift_px.
    y0 = (_caption_y0(height, total_h) - lift_px) if y is None else y
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


#: The caption block's bottom edge, as a fraction of frame height. The
#: project's own safe-title rule keeps text inside the inner 80% of the
#: frame (youtube_16x9.json: safe_title_margin_pct 10); 0.84 leaves a
#: visible margin below the caption on a TV and in a phone crop, and
#: clears the frame edge Mai flagged ("captions too close to the
#: bottom"). Verified on burned establishing/medium/OTS frames: no
#: figure overlap at 0.84, and at MAX_CHARS=30 every phrase is a
#: single line (0/279 two-line phrases across both real scripts), so
#: the raised block cannot climb onto a standing figure.
CAPTION_SAFE_BOTTOM = 0.84


def _caption_y0(height, total_h):
    """Top of the caption block: bottom pinned to the safe-title line."""
    safe = int(round(float(height) * CAPTION_SAFE_BOTTOM)) - int(total_h)
    return max(0, min(int(height) - 40 - int(total_h), safe))


def caption_metrics(phrase, width=1920, height=1080, font_px=FONT_PX):
    """What :func:`draw_phrase` will put on screen, without drawing it.

    The parity scorecard needs the caption numbers (font size, line
    count, longest line, vertical position) and they must come from the
    same wrapping the renderer uses, not from a second implementation.
    ``y_frac`` is the TOP line's centre as a fraction of the frame
    height, which is what a reviewer sees.
    """
    font = get_font(font_px)
    lines = _wrap_lines(phrase, font)
    line_h = int(font_px * 1.22)
    total_h = len(lines) * line_h
    y0 = _caption_y0(height, total_h)
    return {
        "font_px": int(font_px),
        "lines": len(lines),
        "max_chars": max((len(ln) for ln in lines), default=0),
        "y_frac": round((y0 + line_h / 2.0) / float(height), 4),
        "y_px": int(y0),
        "text": phrase,
    }


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
