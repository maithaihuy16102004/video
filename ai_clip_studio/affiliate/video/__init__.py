"""AI Affiliate Studio — computer vision / video editing side (Subagent A).

Phase 1, new files only. These modules are deliberately decoupled
from the frontend / language / audio side (Subagent B): the two
halves meet only through the AFFILIATE_PROJECT_V1 schema
(``ai_clip_studio/affiliate/schema.py``). Nothing in this package
imports B's modules at module level; converters that produce
schema-shaped dicts live next to the engine objects they convert.

Submodules:
  models       — engine dataclasses + the export authorization gate
  capabilities — honest environment probing (ffmpeg, cv2, OCR, fonts)
  probe        — ffprobe source metadata + SHA-256 (immutable source)
  analysis     — scenes, motion, faces, text/watermark candidates,
                 silence segments (measured signals, no invented claims)
  ocr          — Chinese OCR engines, temporal tracking, classification,
                 manual-review queue, removal approvals
  text_replace — SMART_OVERLAY / LOCAL_BLUR / CROP_AND_REFRAME /
                 MANUAL_MASK (+ inpaint when cv2 is available)
  transform    — FFmpeg transform ops with editorial purpose + flip
                 safety warnings (mirror defaults OFF)
  export       — 9:16 reframe + TIKTOK/FACEBOOK/MASTER profiles
  qa           — video QA on real rendered files, measured numbers only

Standing rules (Mai's directive + rights caveat):
  * Only videos the user owns or is permitted to reuse commercially.
    Export is refused for UNKNOWN / unconfirmed authorization.
  * No watermark or creator-attribution removal. No copyright-evasion
    features. Classification never implies removability.
  * No invented claims, prices, or testimonials anywhere in this
    package (it carries no product facts at all).
"""
from __future__ import annotations

__all__: list[str] = []
