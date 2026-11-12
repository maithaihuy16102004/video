"""AI Affiliate Studio — Shopee Edition (Phase 1, Subagent B scope).

A production module inside AI Clip Studio that localizes AUTHORIZED
product videos (including Chinese-language demonstrations) into
Vietnamese affiliate videos for TikTok / Facebook Reels (9:16).

This package holds the frontend / language / audio side of the
module: the AFFILIATE_PROJECT_V1 schema, product configuration,
Chinese ASR, Vietnamese translation, affiliate script generation,
VieNeu-TTS integration (via the shared tts_cli_provider on this VM),
the audio-driven timeline, the subtitle engine, the marketing
package, QA modules, the project store, and the mount-ready API/UI
for the :8788 product server.

The computer-vision / video-editing side (OCR, text tracking, masks,
transforms, reframing, export) is owned by Subagent A under
``ai_clip_studio/affiliate/video/`` and is deliberately NOT imported
here — Phase 1 keeps the two halves decoupled behind the schema.

Standing rules (Mai's directive + rights caveat):
  * Only videos the user owns or is permitted to reuse commercially.
    Export is REFUSED when the source authorization is UNKNOWN or the
    commercial-rights confirmation is missing.
  * Mirror / translation / dubbing never makes someone else's video
    original and never guarantees monetization eligibility.
  * No watermark or creator-attribution removal. No copyright-evasion
    transformations. Mirror defaults OFF.
  * Never invent prices, discounts, certifications, medical benefits,
    performance claims, testimonials, or affiliate links.
  * Vietnamese (vi-VN) narration/subtitles by default; no silent
    English TTS fallback. TTS failure stops the job.
  * Gemini output is labelled "gemini" only when a real Gemini call
    produced it; otherwise the labelled fallback is used.
Douyin standing requirements (Mai, 2026-11-12):
  * Translation stays CLOSE to the original meaning, in a humorous,
    viral, review-style Vietnamese voice — humour in wording, never
    in facts (style="humorous_viral_review").
  * Per-character dubbing: each speaker maps to their own voice,
    consistently across the video (speaker_id -> preset, data-driven).
  * VieNeu voices per character through the provider abstraction
    (VOICE_PRESETS is the seam; real VieNeu on Mai's machine).
  * On-screen Chinese text is blurred, then Vietnamese subtitles are
    overlaid (blur = Subagent A; overlay = captions.burn_filter_args).
"""
from __future__ import annotations

from .schema import (
    AFFILIATE_SCHEMA_VERSION,
    AffiliateError,
    AffiliateProject,
    AudioMix,
    EditOperation,
    ExportProfile,
    OcrTrack,
    ProductInfo,
    SourceAuthorization,
    SourceVideo,
    SubtitleStyle,
    VideoAnalysis,
    export_allowed,
    parse_project,
    project_snapshot_hash,
    validate_project,
)

__all__ = [
    "AFFILIATE_SCHEMA_VERSION",
    "AffiliateError",
    "AffiliateProject",
    "AudioMix",
    "EditOperation",
    "ExportProfile",
    "OcrTrack",
    "ProductInfo",
    "SourceAuthorization",
    "SourceVideo",
    "SubtitleStyle",
    "VideoAnalysis",
    "export_allowed",
    "parse_project",
    "project_snapshot_hash",
    "validate_project",
]
