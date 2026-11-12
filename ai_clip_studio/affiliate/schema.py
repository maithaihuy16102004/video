"""AFFILIATE_PROJECT_V1 schema — dataclasses, parser, validator.

Machine-readable counterpart: ``affiliate_project_v1.schema.json``
in this package (JSON Schema draft 2020-12). The dataclasses below
are the authoritative in-Python representation; ``validate_project``
enforces the same rules without depending on the ``jsonschema``
package, and ``validate_against_json_schema`` cross-checks with the
real JSON Schema when ``jsonschema`` is installed.

This schema is SEPARATE from STUDIO SCRIPT V1 (the storytelling
schema). They share infrastructure and artifact conventions only —
never field meanings. Do not merge them.

Structure (§22 of Mai's directive):
    PROJECT, SOURCE_VIDEO, SOURCE_AUTHORIZATION, PRODUCT,
    VIDEO_ANALYSIS, OCR_TRACKS, TRANSLATION, SCRIPT, VOICE,
    EDIT_OPERATIONS, SUBTITLE_STYLE, AUDIO_MIX, EXPORT_PROFILE,
    QA, OUTPUT.

Error codes (stable, field-pathed, AFF001–AFF024):
    AFF001  missing required field
    AFF002  wrong JSON type
    AFF003  value outside its enum
    AFF004  invalid URL (must be http/https)
    AFF005  invalid colour (must be #RRGGBB)
    AFF006  negative / out-of-range number
    AFF007  time range invalid (end <= start, or negative start)
    AFF008  authorization UNKNOWN — export refused
    AFF009  commercial-rights confirmation missing — export refused
    AFF010  duplicate ID (scene / text / segment)
    AFF011  dangling reference (unknown scene / track / segment id)
    AFF012  empty spoken/transcript content where content is required
    AFF013  subtitle style out of range (font size, lines, chars)
    AFF014  export profile invalid (resolution / fps / crf / bitrate)
    AFF015  audio mix invalid (unknown bus, gain out of range)
    AFF016  unknown edit operation or missing operation parameter
    AFF017  script not approved (approval required before TTS/export)
    AFF018  source checksum missing or malformed
    AFF019  affiliate link present but disclosure missing
    AFF020  watermark/attribution track targeted for removal
    AFF021  mirror enabled without the label/logo warning review
    AFF022  unsupported source container/codec
    AFF023  schema version mismatch
    AFF024  project JSON is not an object / unreadable
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

AFFILIATE_SCHEMA_VERSION = "AFFILIATE_PROJECT_V1"

# ---------------------------------------------------------------- enums

AUTHORIZATION_TYPES = ("USER_OWNED", "LICENSED", "SELLER_AUTHORIZED", "UNKNOWN")
# Gate-level codes: legitimate intermediate states that refuse an
# ACTION (export/TTS) but must not block parsing or storage.
GATE_CODES = frozenset({"AFF008", "AFF009", "AFF017", "AFF020", "AFF021"})
SUPPORTED_CONTAINERS = ("mp4", "mov", "mkv", "webm")
OCR_TEXT_CLASSES = ("SUBTITLE", "PROMOTIONAL_OVERLAY", "PRODUCT_LABEL",
                    "BRAND_LOGO", "CREATOR_ATTRIBUTION", "WATERMARK", "UNKNOWN")
# Classes that must NEVER be auto-removed (§7/§8).
PROTECTED_TEXT_CLASSES = ("PRODUCT_LABEL", "BRAND_LOGO",
                          "CREATOR_ATTRIBUTION", "WATERMARK")
TRANSLATION_MODES = ("DIRECT_TRANSLATION", "NATURAL_LOCALIZATION",
                     "AFFILIATE_COPYWRITING")
# Translation styles (§11 + Douyin standing requirement 2026-11-12):
# "humorous_viral_review" = funny, viral, review-style Vietnamese
# wording that stays CLOSE to the original meaning — humour in the
# wording only, never in the facts (fidelity rules still apply).
TRANSLATION_STYLES = ("neutral", "humorous_viral_review")
SCRIPT_VARIANTS = ("natural_review", "demonstration", "problem_solution",
                   "dubbed_translation")
SCRIPT_SECTIONS = ("HOOK", "PROBLEM", "PRODUCT_INTRODUCTION",
                   "DEMONSTRATION", "BENEFITS", "CALL_TO_ACTION")
EDIT_OPERATIONS = ("hflip", "vflip", "rotate", "crop", "scale", "reframe",
                   "trim", "scene_reorder", "speed", "brightness",
                   "contrast", "saturation", "white_balance", "sharpen",
                   "denoise", "stabilize", "text_overlay", "text_blur",
                   "text_inpaint", "text_crop", "manual_mask")
AUDIO_MIX_MODES = ("REPLACE_ALL", "KEEP_PRODUCT_SOUNDS",
                   "DUCK_ORIGINAL_AUDIO", "CUSTOM_MIX")
AUDIO_BUSES = ("voice", "original", "music", "sfx")
EXPORT_PROFILES = ("TIKTOK_REELS", "FACEBOOK_REELS", "HIGH_QUALITY_MASTER")
SAFE_ZONE_PROFILES = ("TIKTOK_VERTICAL", "FACEBOOK_REELS_VERTICAL")
QA_STATUSES = ("PASS", "FAIL", "PENDING", "NOT_RUN")

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AffiliateError(ValueError):
    """Schema/validation failure with a stable code + field path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code} at {path}: {message}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path,
                "message": self.message}


@dataclass
class Issue:
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path,
                "message": self.message}


# ------------------------------------------------------------- dataclasses

@dataclass
class SourceVideo:
    file_name: str
    file_size_bytes: int
    resolution: str = ""          # e.g. "1080x1920"
    fps: float = 0.0
    duration_sec: float = 0.0
    video_codec: str = ""
    audio_codec: str = ""
    aspect_ratio: str = ""        # e.g. "9:16"
    orientation: str = ""         # "vertical" | "horizontal" | "square"
    has_audio: bool = False
    container: str = ""           # mp4 | mov | mkv | webm
    sha256: str = ""              # checksum of the immutable source asset
    stored_path: str = ""         # server-side path of the stored copy
    source_url: str = ""          # original share/source link, if any
    # Provenance only: the URL is RECORDED, never fetched by this
    # module. A link without an uploaded file cannot be exported
    # (no checksum) and its authorization must still be confirmed.


@dataclass
class SourceAuthorization:
    authorization_type: str                     # AUTHORIZATION_TYPES
    commercial_rights_confirmed: bool = False
    rights_note: str = ""         # free text: licence / permission detail
    confirmed_by: str = ""        # who confirmed (user id / name)
    confirmed_at: str = ""        # ISO timestamp of the confirmation


@dataclass
class ProductInfo:
    product_name: str
    product_category: str = ""
    shopee_product_url: str = ""
    affiliate_url: str = ""       # user-provided ONLY — never generated
    product_price: float | None = None   # user-provided ONLY — never invented
    price_currency: str = "VND"
    product_features: list[str] = field(default_factory=list)
    product_benefits: list[str] = field(default_factory=list)
    target_audience: str = ""
    call_to_action: str = ""
    brand_name: str = ""
    brand_color: str = ""
    product_images: list[str] = field(default_factory=list)
    seller_information: str = ""
    disclosure_text: str = ""
    personally_tested_confirmed: bool = False


@dataclass
class AnalysisScene:
    scene_id: str
    start_time: float
    end_time: float
    visual_description: str = ""
    product_visibility: str = ""  # "clear" | "partial" | "absent" | ""
    detected_text: list[str] = field(default_factory=list)
    speech_transcript: str = ""
    important_regions: list[dict[str, Any]] = field(default_factory=list)
    suggested_edit: str = ""
    confidence: float = 0.0


@dataclass
class VideoAnalysis:
    scenes: list[AnalysisScene] = field(default_factory=list)
    faces_detected: bool = False
    hands_detected: bool = False
    motion_intensity: str = ""    # "low" | "medium" | "high" | ""
    has_speech: bool = False
    silence_segments: list[dict[str, float]] = field(default_factory=list)
    engine: str = ""              # e.g. "gemini:gemini-3.5-flash-lite" / "fallback"
    engine_detail: str = ""


@dataclass
class OcrTrack:
    text_id: str
    original_text: str
    translated_text: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    bounding_box: list[float] = field(default_factory=list)  # [x,y,w,h] 0..1
    polygon: list[list[float]] = field(default_factory=list)
    track_id: str = ""
    ocr_confidence: float = 0.0
    text_classification: str = "UNKNOWN"


@dataclass
class TranslationRecord:
    mode: str                     # TRANSLATION_MODES
    engine: str                   # "gemini:<model>" or "fallback"
    engine_detail: str = ""
    style: str = "neutral"        # TRANSLATION_STYLES
    # Three SEPARATE records (§11): original, translation, rewrite.
    original_segments: list[dict[str, Any]] = field(default_factory=list)
    translated_segments: list[dict[str, Any]] = field(default_factory=list)
    rewritten_segments: list[dict[str, Any]] = field(default_factory=list)
    needs_human_review: bool = False
    review_notes: list[str] = field(default_factory=list)


@dataclass
class ScriptSegment:
    segment_id: str
    section: str                  # SCRIPT_SECTIONS
    text: str
    speaker_id: str = ""          # dubbing: which on-screen speaker
    # says this line ("" = default narrator voice). The voice stage
    # maps speaker_id -> preset via VoiceConfig.speaker_voices.
    start_time: float | None = None   # filled by the audio timeline
    end_time: float | None = None
    estimated_sec: float = 0.0
    voice_wav: str = ""           # filled by the TTS stage
    measured_sec: float | None = None


@dataclass
class AffiliateScript:
    variant: str                  # SCRIPT_VARIANTS
    target_seconds: float         # 15/30/45/60 or audio-driven custom
    segments: list[ScriptSegment] = field(default_factory=list)
    engine: str = ""
    engine_detail: str = ""
    approved: bool = False
    approved_by: str = ""
    approved_at: str = ""
    approval_note: str = ""


@dataclass
class VoiceConfig:
    voice_id: str = ""            # real provider voice id (see voice.py)
    voice_gender: str = ""        # "female" | "male" | ""
    voice_region: str = ""        # provider default unless exposed
    voice_speed: int = 100        # 1-200 scale of the tts CLI; 100 = 1.00x
    voice_style: str = ""
    preset: str = ""              # preset name from voice.py, if used
    pause_after_sec: float = 0.5
    pronunciation_dictionary: dict[str, str] = field(default_factory=dict)
    # Per-character dubbing (data-driven, never hardcoded): maps a
    # speaker_id (from ASR speaker labels) to a voice PRESET name.
    # Segments whose speaker_id is absent here use the default voice
    # above. Preset names resolve through voice.py's preset table —
    # the single seam where provider voices (VieNeu on Mai's machine,
    # the tts CLI here) are bound.
    speaker_voices: dict[str, str] = field(default_factory=dict)


@dataclass
class EditOperation:
    operation: str                # EDIT_OPERATIONS
    parameters: dict[str, Any] = field(default_factory=dict)
    start_time: float | None = None
    end_time: float | None = None
    target_track_id: str = ""     # OCR track this edit applies to, if any
    approved: bool = False        # manual approval for sensitive edits
    approval_note: str = ""


@dataclass
class SubtitleStyle:
    font_family: str = "DejaVu Sans"
    font_size: int = 64
    font_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: int = 3
    background_color: str = "#000000"
    background_opacity: float = 0.0     # 0.0 transparent .. 1.0 opaque
    position_x: str = "center"    # "left" | "center" | "right"
    position_y: int = 0           # offset px from the bottom safe area
    max_lines: int = 2
    max_chars_per_line: int = 42
    highlight_color: str = "#FFE135"
    safe_zone_profile: str = "TIKTOK_VERTICAL"
    dynamic_captions: bool = True
    word_highlight: bool = False


@dataclass
class AudioMix:
    mode: str = "REPLACE_ALL"     # AUDIO_MIX_MODES
    bus_gains_db: dict[str, float] = field(default_factory=lambda: {
        "voice": 0.0, "original": -30.0, "music": -20.0, "sfx": -14.0})
    ducking_db: float = 14.0
    fade_in_sec: float = 0.3
    fade_out_sec: float = 0.5
    music_path: str = ""          # authorized music file only, or ""
    music_authorized: bool = False


@dataclass
class ExportProfile:
    profile: str = "TIKTOK_REELS"  # EXPORT_PROFILES
    aspect_ratio: str = "9:16"
    resolution: str = "1080x1920"
    fps: int = 30
    video_codec: str = "h264"
    pixel_format: str = "yuv420p"
    crf: int = 18
    audio_codec: str = "aac"
    audio_sample_rate: int = 48000
    audio_bitrate_kbps: int = 192
    faststart: bool = True
    color_space: str = "bt709"


@dataclass
class AffiliateProject:
    project_id: str
    schema_version: str = AFFILIATE_SCHEMA_VERSION
    project_name: str = ""
    created_at: str = ""
    source_video: SourceVideo | None = None
    authorization: SourceAuthorization | None = None
    product: ProductInfo | None = None
    video_analysis: VideoAnalysis = field(default_factory=VideoAnalysis)
    ocr_tracks: list[OcrTrack] = field(default_factory=list)
    translation: TranslationRecord | None = None
    script: AffiliateScript | None = None
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    edit_operations: list[EditOperation] = field(default_factory=list)
    subtitle_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    audio_mix: AudioMix = field(default_factory=AudioMix)
    export_profile: ExportProfile = field(default_factory=ExportProfile)
    qa: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    stages: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -------------------------------------------------------------- validation

def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_project(data: Any) -> list[Issue]:
    """Validate a raw project dict. Returns issues (empty = valid).

    This is the structural + rules validator: types, enums, ranges,
    references, and the authorization / commercial-content gates that
    must hold before an export. It never mutates its input.
    """
    issues: list[Issue] = []

    def err(code: str, path: str, message: str) -> None:
        issues.append(Issue(code, path, message))

    if not isinstance(data, dict):
        return [Issue("AFF024", "$", "project must be a JSON object")]
    if data.get("schema_version", AFFILIATE_SCHEMA_VERSION) != AFFILIATE_SCHEMA_VERSION:
        err("AFF023", "schema_version",
            f"expected {AFFILIATE_SCHEMA_VERSION!r}")
    if not isinstance(data.get("project_id"), str) or not data["project_id"].strip():
        err("AFF001", "project_id", "project_id is required")

    # ---- SOURCE_VIDEO
    src = data.get("source_video")
    if src is not None:
        if not isinstance(src, dict):
            err("AFF002", "source_video", "must be an object")
        else:
            if not isinstance(src.get("file_name"), str) or not src["file_name"]:
                err("AFF001", "source_video.file_name", "file_name is required")
            if not _is_number(src.get("file_size_bytes")) or src["file_size_bytes"] < 0:
                err("AFF006", "source_video.file_size_bytes", "must be >= 0")
            container = str(src.get("container", "")).lower()
            if container and container not in SUPPORTED_CONTAINERS:
                err("AFF022", "source_video.container",
                    f"unsupported container {container!r}; supported: "
                    f"{list(SUPPORTED_CONTAINERS)}")
            if _is_number(src.get("duration_sec")) and src["duration_sec"] < 0:
                err("AFF006", "source_video.duration_sec", "must be >= 0")
            sha = src.get("sha256", "")
            if sha and not _SHA256_RE.match(str(sha)):
                err("AFF018", "source_video.sha256",
                    "must be a 64-char lowercase hex sha256")
            url = src.get("source_url", "")
            if url and not (isinstance(url, str)
                            and url.startswith(("http://", "https://"))):
                err("AFF004", "source_video.source_url",
                    "must be an http/https URL")

    # ---- SOURCE_AUTHORIZATION
    auth = data.get("authorization")
    if auth is not None:
        if not isinstance(auth, dict):
            err("AFF002", "authorization", "must be an object")
        else:
            atype = auth.get("authorization_type")
            if atype not in AUTHORIZATION_TYPES:
                err("AFF003", "authorization.authorization_type",
                    f"must be one of {list(AUTHORIZATION_TYPES)}")
            elif atype == "UNKNOWN":
                err("AFF008", "authorization.authorization_type",
                    "UNKNOWN authorization — export is refused until the "
                    "user confirms the source is owned or licensed")
            if not auth.get("commercial_rights_confirmed"):
                err("AFF009", "authorization.commercial_rights_confirmed",
                    "commercial usage rights must be confirmed before export")

    # ---- PRODUCT
    prod = data.get("product")
    if prod is not None:
        if not isinstance(prod, dict):
            err("AFF002", "product", "must be an object")
        else:
            if not isinstance(prod.get("product_name"), str) or not prod["product_name"].strip():
                err("AFF001", "product.product_name", "product_name is required")
            for key in ("shopee_product_url", "affiliate_url"):
                url = prod.get(key, "")
                if url and not _URL_RE.match(str(url)):
                    err("AFF004", f"product.{key}",
                        f"must be an http(s) URL, got {url!r}")
            price = prod.get("product_price")
            if price is not None and (not _is_number(price) or price < 0):
                err("AFF006", "product.product_price", "must be >= 0 or null")
            color = prod.get("brand_color", "")
            if color and not _COLOR_RE.match(str(color)):
                err("AFF005", "product.brand_color", "must be #RRGGBB")
            if prod.get("affiliate_url") and not (prod.get("disclosure_text") or "").strip():
                err("AFF019", "product.disclosure_text",
                    "an affiliate disclosure is required when an affiliate "
                    "link is present")

    # ---- VIDEO_ANALYSIS
    analysis = data.get("video_analysis") or {}
    scene_ids: set[str] = set()
    if isinstance(analysis, dict):
        for i, scene in enumerate(analysis.get("scenes", []) or []):
            base = f"video_analysis.scenes[{i}]"
            if not isinstance(scene, dict):
                err("AFF002", base, "must be an object")
                continue
            sid = scene.get("scene_id")
            if not sid:
                err("AFF001", f"{base}.scene_id", "scene_id is required")
            elif sid in scene_ids:
                err("AFF010", f"{base}.scene_id", f"duplicate scene_id {sid!r}")
            scene_ids.add(sid)
            start, end = scene.get("start_time"), scene.get("end_time")
            if _is_number(start) and _is_number(end):
                if start < 0 or end <= start:
                    err("AFF007", base, "need 0 <= start_time < end_time")
            if _is_number(scene.get("confidence")) and not 0.0 <= scene["confidence"] <= 1.0:
                err("AFF006", f"{base}.confidence", "must be within 0..1")

    # ---- OCR_TRACKS
    track_ids: set[str] = set()
    for i, track in enumerate(data.get("ocr_tracks", []) or []):
        base = f"ocr_tracks[{i}]"
        if not isinstance(track, dict):
            err("AFF002", base, "must be an object")
            continue
        tid = track.get("text_id")
        if not tid:
            err("AFF001", f"{base}.text_id", "text_id is required")
        elif tid in track_ids:
            err("AFF010", f"{base}.text_id", f"duplicate text_id {tid!r}")
        track_ids.add(tid)
        cls = track.get("text_classification", "UNKNOWN")
        if cls not in OCR_TEXT_CLASSES:
            err("AFF003", f"{base}.text_classification",
                f"must be one of {list(OCR_TEXT_CLASSES)}")
        start, end = track.get("start_time"), track.get("end_time")
        if _is_number(start) and _is_number(end) and (start < 0 or end <= start):
            err("AFF007", base, "need 0 <= start_time < end_time")
        if _is_number(track.get("ocr_confidence")) and not 0.0 <= track["ocr_confidence"] <= 1.0:
            err("AFF006", f"{base}.ocr_confidence", "must be within 0..1")

    # ---- TRANSLATION
    trans = data.get("translation")
    if trans is not None:
        if not isinstance(trans, dict):
            err("AFF002", "translation", "must be an object")
        else:
            if trans.get("mode") not in TRANSLATION_MODES:
                err("AFF003", "translation.mode",
                    f"must be one of {list(TRANSLATION_MODES)}")
            if (trans.get("style") is not None
                    and trans.get("style") not in TRANSLATION_STYLES):
                err("AFF003", "translation.style",
                    f"must be one of {list(TRANSLATION_STYLES)}")

    # ---- VOICE (per-speaker map shape; preset existence is checked
    # in voice.py, which owns the preset table)
    voice = data.get("voice")
    if isinstance(voice, dict):
        mapping = voice.get("speaker_voices")
        if mapping is not None:
            if not isinstance(mapping, dict):
                err("AFF002", "voice.speaker_voices", "must be an object")
            else:
                for speaker, preset in mapping.items():
                    if not isinstance(speaker, str) or not speaker:
                        err("AFF002", "voice.speaker_voices",
                            "speaker ids must be non-empty strings")
                    if not isinstance(preset, str) or not preset:
                        err("AFF002",
                            f"voice.speaker_voices.{speaker}",
                            "preset name must be a non-empty string")

    # ---- SCRIPT
    script = data.get("script")
    if script is not None:
        if not isinstance(script, dict):
            err("AFF002", "script", "must be an object")
        else:
            if script.get("variant") not in SCRIPT_VARIANTS:
                err("AFF003", "script.variant",
                    f"must be one of {list(SCRIPT_VARIANTS)}")
            if _is_number(script.get("target_seconds")) and script["target_seconds"] <= 0:
                err("AFF006", "script.target_seconds", "must be > 0")
            seg_ids: set[str] = set()
            for j, seg in enumerate(script.get("segments", []) or []):
                sbase = f"script.segments[{j}]"
                if not isinstance(seg, dict):
                    err("AFF002", sbase, "must be an object")
                    continue
                if seg.get("section") not in SCRIPT_SECTIONS:
                    err("AFF003", f"{sbase}.section",
                        f"must be one of {list(SCRIPT_SECTIONS)}")
                if not (seg.get("text") or "").strip():
                    err("AFF012", f"{sbase}.text", "segment text must not be empty")
                sid = seg.get("segment_id")
                if sid in seg_ids:
                    err("AFF010", f"{sbase}.segment_id", f"duplicate {sid!r}")
                seg_ids.add(sid)

    # ---- EDIT_OPERATIONS (+ protected-track + mirror gates)
    tracks_by_id = {t.get("text_id"): t for t in (data.get("ocr_tracks") or [])
                    if isinstance(t, dict)}
    for i, op in enumerate(data.get("edit_operations", []) or []):
        base = f"edit_operations[{i}]"
        if not isinstance(op, dict):
            err("AFF002", base, "must be an object")
            continue
        if op.get("operation") not in EDIT_OPERATIONS:
            err("AFF016", f"{base}.operation",
                f"unknown operation {op.get('operation')!r}")
        target = op.get("target_track_id", "")
        if target and target not in tracks_by_id:
            err("AFF011", f"{base}.target_track_id",
                f"unknown OCR track {target!r}")
        if target and target in tracks_by_id and op.get("operation") in (
                "text_blur", "text_inpaint", "text_crop"):
            cls = tracks_by_id[target].get("text_classification")
            if cls in PROTECTED_TEXT_CLASSES and not op.get("approved"):
                err("AFF020", base,
                    f"track {target!r} is {cls} — removal/replacement "
                    "needs explicit user approval and authorization")
        if op.get("operation") == "hflip" and not op.get("approved"):
            err("AFF021", base,
                "horizontal mirror needs the label/logo warning review "
                "and explicit approval (mirror defaults OFF)")

    # ---- SUBTITLE_STYLE
    style = data.get("subtitle_style") or {}
    if isinstance(style, dict):
        if _is_number(style.get("font_size")) and not 16 <= style["font_size"] <= 160:
            err("AFF013", "subtitle_style.font_size", "must be within 16..160")
        if _is_number(style.get("max_lines")) and not 1 <= style["max_lines"] <= 4:
            err("AFF013", "subtitle_style.max_lines", "must be within 1..4")
        if _is_number(style.get("max_chars_per_line")) and not 10 <= style["max_chars_per_line"] <= 80:
            err("AFF013", "subtitle_style.max_chars_per_line", "must be within 10..80")
        if _is_number(style.get("background_opacity")) and not 0.0 <= style["background_opacity"] <= 1.0:
            err("AFF013", "subtitle_style.background_opacity", "must be within 0..1")
        for key in ("font_color", "outline_color", "background_color", "highlight_color"):
            if style.get(key) and not _COLOR_RE.match(str(style[key])):
                err("AFF005", f"subtitle_style.{key}", "must be #RRGGBB")
        if style.get("safe_zone_profile") and style["safe_zone_profile"] not in SAFE_ZONE_PROFILES:
            err("AFF003", "subtitle_style.safe_zone_profile",
                f"must be one of {list(SAFE_ZONE_PROFILES)}")

    # ---- AUDIO_MIX
    mix = data.get("audio_mix") or {}
    if isinstance(mix, dict):
        if mix.get("mode") and mix["mode"] not in AUDIO_MIX_MODES:
            err("AFF003", "audio_mix.mode", f"must be one of {list(AUDIO_MIX_MODES)}")
        for bus, gain in (mix.get("bus_gains_db") or {}).items():
            if bus not in AUDIO_BUSES:
                err("AFF015", f"audio_mix.bus_gains_db.{bus}", f"unknown bus {bus!r}")
            elif _is_number(gain) and not -60.0 <= gain <= 12.0:
                err("AFF015", f"audio_mix.bus_gains_db.{bus}", "gain must be within -60..+12 dB")
        if mix.get("music_path") and not mix.get("music_authorized"):
            err("AFF015", "audio_mix.music_path",
                "background music needs an authorization confirmation — "
                "no copyrighted music without appropriate rights")

    # ---- EXPORT_PROFILE
    prof = data.get("export_profile") or {}
    if isinstance(prof, dict):
        if prof.get("profile") and prof["profile"] not in EXPORT_PROFILES:
            err("AFF003", "export_profile.profile",
                f"must be one of {list(EXPORT_PROFILES)}")
        if _is_number(prof.get("crf")) and not 0 <= prof["crf"] <= 51:
            err("AFF014", "export_profile.crf", "must be within 0..51")
        if _is_number(prof.get("fps")) and prof["fps"] not in (24, 25, 30, 50, 60):
            err("AFF014", "export_profile.fps", "must be 24/25/30/50/60")
        if _is_number(prof.get("audio_bitrate_kbps")) and not 96 <= prof["audio_bitrate_kbps"] <= 320:
            err("AFF014", "export_profile.audio_bitrate_kbps", "must be within 96..320")
        res = prof.get("resolution", "")
        if res and not re.match(r"^\d+x\d+$", str(res)):
            err("AFF014", "export_profile.resolution", "must look like 1080x1920")

    return issues


def parse_project(data: dict) -> AffiliateProject:
    """Parse + validate a raw dict into an AffiliateProject.

    Raises AffiliateError (first issue) when STRUCTURAL validation
    fails. Gate-level issues (AFF008/AFF009/AFF017/AFF020/AFF021)
    describe legitimate intermediate states — an unconfirmed
    authorization, an unapproved script or edit — and do NOT block
    parsing: the gates that consume them (export, TTS) refuse the
    action instead. Without this, a project created with UNKNOWN
    authorization could never be loaded again. The full issue list
    is available via ``validate_project``.
    """
    issues = [i for i in validate_project(data) if i.code not in GATE_CODES]
    if issues:
        first = issues[0]
        raise AffiliateError(first.code, first.path,
                             f"{first.message} ({len(issues)} issue(s) total)")

    def _dc(cls, raw, default=None):
        if raw is None:
            return default
        if isinstance(raw, dict):
            known = {f for f in cls.__dataclass_fields__}
            return cls(**{k: v for k, v in raw.items() if k in known})
        return raw

    src = _dc(SourceVideo, data.get("source_video"))
    auth = _dc(SourceAuthorization, data.get("authorization"))
    prod = _dc(ProductInfo, data.get("product"))
    analysis_raw = data.get("video_analysis") or {}
    scenes = [_dc(AnalysisScene, s) for s in analysis_raw.get("scenes", [])]
    analysis = VideoAnalysis(
        scenes=scenes,
        faces_detected=bool(analysis_raw.get("faces_detected", False)),
        hands_detected=bool(analysis_raw.get("hands_detected", False)),
        motion_intensity=str(analysis_raw.get("motion_intensity", "")),
        has_speech=bool(analysis_raw.get("has_speech", False)),
        silence_segments=list(analysis_raw.get("silence_segments", [])),
        engine=str(analysis_raw.get("engine", "")),
        engine_detail=str(analysis_raw.get("engine_detail", "")))
    tracks = [_dc(OcrTrack, t) for t in data.get("ocr_tracks", [])]
    trans = _dc(TranslationRecord, data.get("translation"))
    script_raw = data.get("script")
    script = None
    if script_raw:
        segments = [_dc(ScriptSegment, s)
                    for s in script_raw.get("segments", [])]
        script = AffiliateScript(
            variant=script_raw["variant"],
            target_seconds=float(script_raw.get("target_seconds", 0)),
            segments=segments,
            engine=str(script_raw.get("engine", "")),
            engine_detail=str(script_raw.get("engine_detail", "")),
            approved=bool(script_raw.get("approved", False)),
            approved_by=str(script_raw.get("approved_by", "")),
            approved_at=str(script_raw.get("approved_at", "")),
            approval_note=str(script_raw.get("approval_note", "")))
    return AffiliateProject(
        project_id=data["project_id"],
        schema_version=data.get("schema_version", AFFILIATE_SCHEMA_VERSION),
        project_name=str(data.get("project_name", "")),
        created_at=str(data.get("created_at", "")),
        source_video=src,
        authorization=auth,
        product=prod,
        video_analysis=analysis,
        ocr_tracks=tracks,
        translation=trans,
        script=script,
        voice=_dc(VoiceConfig, data.get("voice"), VoiceConfig()),
        edit_operations=[_dc(EditOperation, o)
                         for o in data.get("edit_operations", [])],
        subtitle_style=_dc(SubtitleStyle, data.get("subtitle_style"),
                           SubtitleStyle()),
        audio_mix=_dc(AudioMix, data.get("audio_mix"), AudioMix()),
        export_profile=_dc(ExportProfile, data.get("export_profile"),
                           ExportProfile()),
        qa=dict(data.get("qa", {})),
        output=dict(data.get("output", {})),
        stages=list(data.get("stages", [])),
    )


def project_snapshot_hash(project: AffiliateProject) -> str:
    """SHA-256 of the canonical project JSON (volatile fields excluded).

    Mirrors the ProductionRequest hash-chain idea: the snapshot taken
    at approval time must match the snapshot at render time, or the
    approvals are invalid. ``stages``/``qa``/``output`` are excluded
    because they change as the job runs.
    """
    data = project.to_dict()
    for volatile in ("stages", "qa", "output", "created_at"):
        data.pop(volatile, None)
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    normalized = unicodedata.normalize("NFC", canonical)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def export_allowed(project: AffiliateProject) -> tuple[bool, list[str]]:
    """The export gate (§4): authorization + rights + approvals.

    Returns (allowed, reasons). Export is REFUSED when the source
    authorization is UNKNOWN, the commercial-rights confirmation is
    missing, the script is unapproved, or a mirror/protected-track
    edit lacks approval.
    """
    reasons: list[str] = []
    auth = project.authorization
    if auth is None:
        reasons.append("missing source authorization record")
    else:
        if auth.authorization_type == "UNKNOWN":
            reasons.append("source authorization is UNKNOWN")
        if auth.authorization_type not in AUTHORIZATION_TYPES:
            reasons.append(f"unknown authorization type {auth.authorization_type!r}")
        if not auth.commercial_rights_confirmed:
            reasons.append("commercial usage rights not confirmed")
    if project.source_video is None:
        reasons.append("no source video recorded")
    elif not project.source_video.sha256:
        reasons.append("source video checksum missing — the immutable "
                       "source asset must be recorded")
    if project.script is not None and not project.script.approved:
        reasons.append("affiliate script not approved by the user")
    tracks = {t.text_id: t for t in project.ocr_tracks}
    for op in project.edit_operations:
        if op.operation == "hflip" and not op.approved:
            reasons.append("horizontal mirror edit lacks approval")
        if op.target_track_id and op.operation in ("text_blur", "text_inpaint",
                                                   "text_crop"):
            track = tracks.get(op.target_track_id)
            if (track is not None
                    and track.text_classification in PROTECTED_TEXT_CLASSES
                    and not op.approved):
                reasons.append(
                    f"protected track {op.target_track_id} "
                    f"({track.text_classification}) edit lacks approval")
    if project.audio_mix.music_path and not project.audio_mix.music_authorized:
        reasons.append("background music lacks an authorization confirmation")
    return (not reasons), reasons


def validate_against_json_schema(data: dict) -> list[str]:
    """Cross-check with the real JSON Schema file.

    Returns a list of human-readable schema violations (empty = the
    document validates). Raises RuntimeError when ``jsonschema`` is
    not installed — the dataclass validator above is the dependency-
    free gate and always runs.
    """
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - env dependent
        raise RuntimeError("jsonschema is not installed") from exc
    schema_path = Path(__file__).resolve().parent / "affiliate_project_v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '$'}: {e.message}"
            for e in sorted(validator.iter_errors(data), key=lambda e: e.path)]
