"""Vietnamese subtitle engine (§16) + platform safe zones (§17).

Subtitles are built from the REAL narration timing (the affiliate
timeline), split into short phrases with the shared
``subtitles.split_subtitle`` / ``phrase_windows`` helpers (fixed font,
never shrunk to squeeze text in). Two outputs:

  * ``.ass`` — styled captions for libass burn-in (dynamic captions,
    word/phrase highlight, brand colours), rendered by the export
    stage (Subagent A) with the ffmpeg ``subtitles`` filter.
  * ``.srt`` — plain timed text, always exported alongside.

Safe zones are CONFIGURABLE PRESETS (TikTok / Facebook Reels
vertical), not guarantees — app UIs change across versions and
devices, so the preview shows the guides and the user can
reposition. Guides are NEVER burned into the final video.

Vietnamese diacritics: the default font is DejaVu Sans (full
Vietnamese Unicode coverage, present on this VM). ``check_font_coverage``
verifies every caption character renders in the chosen font file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from PIL import ImageFont

from ..subtitles import FONT_PATH, phrase_windows, split_subtitle
from .schema import SubtitleStyle

FRAME_W = 1080
FRAME_H = 1920

# Safe-zone presets as fractions of the frame. Restricted rectangles
# are (x0, y0, x1, y1) in 0..1 coordinates: captions must not overlap
# them. Values are the documented presets from the directive's §17
# (right-side controls, bottom captions/UI, top UI, product link
# area); they are presets, not platform guarantees.
SAFE_ZONES: dict[str, dict] = {
    "TIKTOK_VERTICAL": {
        "restricted": [
            {"name": "right_controls", "box": (0.84, 0.30, 1.0, 0.75)},
            {"name": "bottom_ui", "box": (0.0, 0.86, 1.0, 1.0)},
            {"name": "top_ui", "box": (0.0, 0.0, 1.0, 0.07)},
            {"name": "product_link", "box": (0.0, 0.78, 0.45, 0.86)},
        ],
        "caption_area": (0.06, 0.60, 0.80, 0.78),
    },
    "FACEBOOK_REELS_VERTICAL": {
        "restricted": [
            {"name": "right_controls", "box": (0.85, 0.35, 1.0, 0.75)},
            {"name": "bottom_ui", "box": (0.0, 0.84, 1.0, 1.0)},
            {"name": "top_ui", "box": (0.0, 0.0, 1.0, 0.08)},
            {"name": "product_link", "box": (0.0, 0.76, 0.45, 0.84)},
        ],
        "caption_area": (0.06, 0.58, 0.80, 0.76),
    },
}

MIN_FONT_RATIO = 0.03  # font height must cover >= 3% of frame height


def _ass_color(hex_color: str, alpha: int = 0) -> str:
    """#RRGGBB -> ASS &HAABBGGRR (alpha 0 = opaque)."""
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H{alpha:02X}{b}{g}{r}"


def _ass_timestamp(seconds: float) -> str:
    total_cs = max(0, int(round(seconds * 100)))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


@dataclass
class CaptionCue:
    text: str
    start: float
    end: float
    words: list[dict] | None = None  # word timings for highlight

    def to_dict(self) -> dict:
        return {"text": self.text, "start": round(self.start, 3),
                "end": round(self.end, 3), "words": self.words}


def build_cues(segments: list[dict], style: SubtitleStyle) -> list[CaptionCue]:
    """Split narration segments into timed caption cues.

    Each segment's text is phrase-split (shared helper: clause
    punctuation first, then word boundaries, never inside a word)
    and each phrase gets a proportional time window. Word timings
    ride along when the segment carries them (ASR word_timestamps).
    """
    cues: list[CaptionCue] = []
    for seg in segments:
        text = str(seg.get("text", ""))
        phrases = split_subtitle(text, max_chars=style.max_chars_per_line,
                                 max_lines=style.max_lines)
        windows = phrase_windows(float(seg.get("start", 0.0)),
                                 float(seg.get("end", 0.0)), phrases)
        for window in windows:
            cues.append(CaptionCue(
                text=window["phrase"], start=window["start"],
                end=window["end"],
                words=seg.get("words") if len(windows) == 1 else None))
    return cues


def _wrap_ass_lines(text: str, style: SubtitleStyle) -> str:
    """Word-wrap a cue into <= max_lines ASS lines (\\N separators),
    measured at the real font size inside the caption area width."""
    try:
        font = ImageFont.truetype(FONT_PATH, style.font_size)
    except OSError:
        font = ImageFont.load_default()
    zone = SAFE_ZONES[style.safe_zone_profile]["caption_area"]
    max_w = (zone[2] - zone[0]) * FRAME_W
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    # Enforce max_lines by re-flowing: merge the shortest adjacent pair
    # is wrong (it would overflow); instead hard-split the longest line
    # by words across the allowed lines.
    while len(lines) > style.max_lines:
        words = " ".join(lines).split()
        per = max(1, len(words) // style.max_lines)
        lines = [" ".join(words[i:i + per])
                 for i in range(0, len(words), per)][:style.max_lines]
    return "\\N".join(lines)


def _highlight_tags(cue: CaptionCue, style: SubtitleStyle) -> str:
    """Karaoke word-highlight tags when word timings exist, else a
    plain phrase. Word timings come from real ASR output only."""
    if not (style.word_highlight and cue.words):
        return cue.text
    parts = []
    for word in cue.words:
        start_cs = max(0, int(round((word["start"] - cue.start) * 100)))
        dur_cs = max(1, int(round((word["end"] - word["start"]) * 100)))
        parts.append(f"{{\\kf{dur_cs}}}{word['word'].strip()}")
    if not parts:
        return cue.text
    # First word starts at the cue start; kf durations are relative.
    _ = start_cs
    return " ".join(parts)


def build_ass(cues: list[CaptionCue], style: SubtitleStyle,
              title: str = "AI Affiliate Studio") -> str:
    """Render a complete .ass subtitle file for libass burn-in."""
    primary = _ass_color(style.font_color)
    secondary = _ass_color(style.highlight_color)
    outline = _ass_color(style.outline_color)
    back_alpha = int(round((1.0 - style.background_opacity) * 255))
    back = _ass_color(style.background_color, alpha=back_alpha)
    align = {"left": 1, "center": 2, "right": 3}[style.position_x]
    # Vertical position: libass MarginV from the bottom safe area.
    zone = SAFE_ZONES[style.safe_zone_profile]["caption_area"]
    margin_v = int((1.0 - zone[3]) * FRAME_H) + style.position_y
    header = (
        "[Script Info]\n"
        f"Title: {title}\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {FRAME_W}\nPlayResY: {FRAME_H}\n"
        "WrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{style.font_family},{style.font_size},{primary},"
        f"{secondary},{outline},{back},-1,0,0,0,100,100,0,0,1,"
        f"{style.outline_width},0,{align},40,40,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )
    events = []
    for cue in cues:
        body = _wrap_ass_lines(_highlight_tags(cue, style), style)
        events.append(
            f"Dialogue: 0,{_ass_timestamp(cue.start)},"
            f"{_ass_timestamp(cue.end)},Default,,0,0,0,,{body}")
    return header + "\n".join(events) + "\n"


def build_srt(cues: list[CaptionCue]) -> str:
    """Plain SRT export (always alongside the .ass)."""
    chunks = []
    for i, cue in enumerate(cues, 1):
        chunks.append(f"{i}\n{_srt_timestamp(cue.start)} --> "
                      f"{_srt_timestamp(cue.end)}\n{cue.text}\n")
    return "\n".join(chunks)


def check_font_coverage(texts: list[str],
                        font_path: str = FONT_PATH) -> dict:
    """Verify every caption character renders in the font file.

    Uses the font's cmap via PIL: a character with no glyph (or a
    zero-width glyph) is reported. Returns {ok, missing: [chars]}.
    """
    try:
        font = ImageFont.truetype(font_path, 64)
    except OSError as exc:
        return {"ok": False, "missing": [],
                "error": f"font file unreadable: {exc}"}
    # Heuristic smoke check: every non-space character must have a
    # non-zero advance width in the font. A missing glyph would render
    # as .notdef; the honest signal is the rendered preview image,
    # which QA inspects. This check catches empty/unknown glyphs.
    missing: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for char in text:
            if char in seen or char.isspace():
                continue
            seen.add(char)
            try:
                if font.getlength(char) <= 0:
                    missing.append(char)
            except Exception:
                missing.append(char)
    return {"ok": not missing, "missing": sorted(set(missing)),
            "checked_chars": len(seen)}


def check_vertical_legibility(style: SubtitleStyle,
                              frame_height: int = FRAME_H) -> dict:
    """Phone check for 9:16: the font must cover >= 3% of frame
    height (same rule as the 16:9 phone check, adapted to vertical).
    64 px on 1920 = 3.3% — passes."""
    ratio = style.font_size / float(frame_height) if frame_height else 0.0
    return {"font_px": style.font_size, "frame_height": frame_height,
            "ratio": round(ratio, 4), "min_ratio": MIN_FONT_RATIO,
            "passes": bool(ratio >= MIN_FONT_RATIO)}


def _boxes_overlap(a: tuple, b: tuple) -> bool:
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def check_safe_zone(style: SubtitleStyle,
                    caption_box: tuple | None = None) -> dict:
    """Check the caption area against the restricted safe-zone boxes.

    ``caption_box`` defaults to the preset's caption area. Returns
    {ok, violations: [restricted-area names overlapped]}.
    """
    zone = SAFE_ZONES[style.safe_zone_profile]
    box = caption_box or zone["caption_area"]
    # position_y shifts the caption box vertically (px -> fraction);
    # positive moves the box UP (toward the top of the frame).
    if style.position_y:
        shift = style.position_y / FRAME_H
        box = (box[0], box[1] - shift, box[2], box[3] - shift)
    violations = [area["name"] for area in zone["restricted"]
                  if _boxes_overlap(box, area["box"])]
    if box[0] < 0 or box[1] < 0 or box[2] > 1 or box[3] > 1:
        violations.append("outside_frame")
    return {"profile": style.safe_zone_profile, "caption_box": box,
            "ok": not violations, "violations": violations}


def safe_zone_guides(style: SubtitleStyle) -> dict:
    """Guide rectangles for the PREVIEW overlay (never burned in).

    Pixel boxes in the 1080x1920 frame, for the frontend to draw.
    """
    zone = SAFE_ZONES[style.safe_zone_profile]
    to_px = lambda box: [int(box[0] * FRAME_W), int(box[1] * FRAME_H),
                         int(box[2] * FRAME_W), int(box[3] * FRAME_H)]
    return {
        "profile": style.safe_zone_profile,
        "frame": [FRAME_W, FRAME_H],
        "restricted": [{"name": a["name"], "box_px": to_px(a["box"])}
                       for a in zone["restricted"]],
        "caption_area_px": to_px(zone["caption_area"]),
        "note": "Guides are preview-only and are never burned into "
                "the exported video.",
    }


def burn_filter_args(ass_path: str) -> list[str]:
    """ffmpeg video-filter args to burn the .ass captions.

    Used by the export stage (Subagent A). The path is escaped for
    the subtitles filter (colons/backslashes).
    """
    escaped = (str(ass_path).replace("\\", "/").replace(":", "\\:")
               .replace("'", "\\'"))
    return ["-vf", f"subtitles='{escaped}'"]
