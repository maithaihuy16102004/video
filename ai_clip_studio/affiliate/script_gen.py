"""Affiliate script generator (§12) — structured Vietnamese copy.

Default structure (adapted to the available footage, never forced):
    HOOK → PROBLEM → PRODUCT_INTRODUCTION → DEMONSTRATION →
    BENEFITS → CALL_TO_ACTION

Variants: natural_review, demonstration, problem_solution, plus
dubbed_translation — a dub script built 1:1 from translated ASR
segments, preserving each line's speaker_id for per-character
dubbing (Douyin standing requirement, 2026-11-12). Durations:
15 / 30 / 45 / 60 s presets, or an audio-driven custom duration.

Rules:
  * Copy is built from VERIFIED product facts + visible demonstrations
    only. No invented prices, discounts, claims, or testimonials.
  * No fake personal testimonials: first-person testing wording
    ("mình đã dùng...") is flagged unless the user explicitly
    confirmed ``personally_tested_confirmed``.
  * The user edits + approves the script BEFORE any TTS. Approval is
    recorded immutably on the script; TTS/export stages require it.
  * Gemini output is labelled; the deterministic fallback builds
    neutral copy from the facts block and says so.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone

from ..gemini_planner import MODELS, _gemini_generate
from ..timeline import estimate_speech_duration
from .product import neutral_description, product_facts_block
from .schema import (
    AffiliateScript,
    ProductInfo,
    ScriptSegment,
    TranslationRecord,
)

# Engine label used when no real Gemini call produced the output.
PLANNER_FALLBACK = "fallback"

DURATION_PRESETS = (15.0, 30.0, 45.0, 60.0)

# Section emphasis per variant (weights only change which sections get
# more time/segments — the facts stay the same).
_VARIANT_SECTIONS: dict[str, list[str]] = {
    "natural_review": ["HOOK", "PRODUCT_INTRODUCTION", "DEMONSTRATION",
                       "BENEFITS", "CALL_TO_ACTION"],
    "demonstration": ["HOOK", "PRODUCT_INTRODUCTION", "DEMONSTRATION",
                      "DEMONSTRATION", "CALL_TO_ACTION"],
    "problem_solution": ["HOOK", "PROBLEM", "PRODUCT_INTRODUCTION",
                         "DEMONSTRATION", "BENEFITS", "CALL_TO_ACTION"],
}

_TESTIMONIAL_RE = re.compile(
    r"mình\s+đã\s+(dùng|thử|trải\s+nghiệm|mua)|tôi\s+đã\s+(dùng|thử|trải\s+nghiệm|mua)"
    r"|mình\s+thấy\s+(nó|em\s+này)|trải\s+nghiệm\s+(của\s+mình|cá\s+nhân)",
    re.IGNORECASE)

_DEFAULT_CTA = ("Nếu thấy phù hợp, bạn có thể xem thông tin sản phẩm ở "
                "giỏ hàng hoặc đường dẫn mình cung cấp.")
_DEFAULT_HOOK = "Bạn đang tìm một món đồ giúp cuộc sống tiện hơn?"


def check_testimonial_claims(text: str) -> list[str]:
    """Flag first-person testing/testimonial wording."""
    return [m.group(0) for m in _TESTIMONIAL_RE.finditer(text or "")]


def _fallback_script(product: ProductInfo, variant: str,
                     target_seconds: float,
                     visible_demonstration: str) -> list[ScriptSegment]:
    """Deterministic copy from verified facts only (labelled fallback)."""
    facts = product_facts_block(product)
    sections = _VARIANT_SECTIONS[variant]
    texts: dict[str, str] = {
        "HOOK": _DEFAULT_HOOK,
        "PROBLEM": ("Nhiều người gặp khó khăn khi sắp xếp không gian "
                    "sống và làm việc gọn gàng."),
        "PRODUCT_INTRODUCTION": neutral_description(product, visible_demonstration),
        "DEMONSTRATION": (
            f"Trong video, {product.product_name} được cho thấy đang "
            f"hoạt động: {visible_demonstration.strip()}"
            if visible_demonstration.strip()
            else f"Trong video, {product.product_name} được giới thiệu "
                 "qua hình ảnh thực tế."),
        "BENEFITS": ("Sản phẩm có các đặc điểm: "
                     + "; ".join(product.product_features) + ".")
        if product.product_features else
        "Thông tin chi tiết về sản phẩm có trong phần mô tả.",
        "CALL_TO_ACTION": product.call_to_action or _DEFAULT_CTA,
    }
    if product.product_benefits:
        benefit_text = ("Lợi ích theo thông tin sản phẩm: "
                        + "; ".join(product.product_benefits) + ".")
        if product.product_features:
            benefit_text += (" Đặc điểm: "
                             + "; ".join(product.product_features) + ".")
        texts["BENEFITS"] = benefit_text
    segments: list[ScriptSegment] = []
    per_section = max(0.8, target_seconds / max(1, len(sections)))
    for i, section in enumerate(sections, 1):
        text = texts[section]
        segments.append(ScriptSegment(
            segment_id=f"SEG{i:02d}", section=section, text=text,
            estimated_sec=round(max(estimate_speech_duration(text),
                                    per_section * 0.5), 2)))
    return segments


def _script_prompt(product: ProductInfo, variant: str,
                   target_seconds: float, visible_demonstration: str,
                   source_summary: str) -> str:
    facts_json = json.dumps(product_facts_block(product),
                            ensure_ascii=False, indent=1)
    return (
        "Bạn là biên kịch video tiếp thị liên kết tiếng Việt. Viết kịch "
        "bản lời đọc cho video giới thiệu sản phẩm, cấu trúc theo đúng "
        "thứ tự: HOOK, PROBLEM, PRODUCT_INTRODUCTION, DEMONSTRATION, "
        "BENEFITS, CALL_TO_ACTION (bỏ PROBLEM nếu không phù hợp với "
        "cảnh quay). Phong cách: "
        f"{variant}. Tổng thời lượng lời đọc khoảng {target_seconds} giây.\n"
        "QUY TẮC BẮT BUỘC:\n"
        "1. Chỉ dùng SỰ THẬT ĐÃ KIỂM CHỨNG dưới đây và những gì video cho "
        "thấy. Không bịa giá, giảm giá, chứng nhận, lợi ích y tế, hiệu năng.\n"
        "2. Không bịa lời chứng thực cá nhân ('mình đã dùng...') trừ khi "
        "người dùng xác nhận đã trải nghiệm.\n"
        "3. Không hứa hẹn doanh số hay thu nhập. Không tạo áp lực mua giả.\n"
        "4. Trả về CHỈ JSON hợp lệ: "
        '{"segments": [{"section": "HOOK", "text": "..."}]}.\n'
        f"SỰ THẬT ĐÃ KIỂM CHỨNG:\n{facts_json}\n"
        f"NHỮNG GÌ VIDEO CHO THẤY:\n{visible_demonstration}\n"
        f"TÓM TẮT LỜI GỐC (nếu có):\n{source_summary}\n"
    )


def generate_script(product: ProductInfo, *,
                    variant: str = "natural_review",
                    target_seconds: float = 30.0,
                    visible_demonstration: str = "",
                    source_summary: str = "",
                    api_key: str | None = None) -> AffiliateScript:
    """Generate an affiliate script. Returns an UNAPPROVED script —
    the user must edit + approve it before TTS (see approve_script)."""
    if variant not in _VARIANT_SECTIONS:
        raise ValueError(f"unknown script variant {variant!r}")
    if target_seconds <= 0:
        raise ValueError("target_seconds must be > 0")
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if key:
        last_error = ""
        for model in MODELS:
            for attempt in (1, 2):
                try:
                    raw = _gemini_generate(
                        _script_prompt(product, variant, target_seconds,
                                       visible_demonstration, source_summary),
                        model, key)
                    text = raw.strip()
                    if text.startswith("```"):
                        text = text.split("```", 2)[1]
                        if text.lstrip().lower().startswith("json"):
                            text = text.lstrip()[4:]
                    payload = json.loads(text)
                    items = payload["segments"]
                    segments = []
                    for i, item in enumerate(items, 1):
                        section = str(item["section"]).upper()
                        if section not in ("HOOK", "PROBLEM",
                                           "PRODUCT_INTRODUCTION",
                                           "DEMONSTRATION", "BENEFITS",
                                           "CALL_TO_ACTION"):
                            raise ValueError(f"bad section {section!r}")
                        body = str(item["text"]).strip()
                        if not body:
                            raise ValueError("empty script segment")
                        segments.append(ScriptSegment(
                            segment_id=f"SEG{i:02d}", section=section,
                            text=body,
                            estimated_sec=round(estimate_speech_duration(body), 2)))
                    return AffiliateScript(
                        variant=variant, target_seconds=float(target_seconds),
                        segments=segments, engine=f"gemini:{model}",
                        engine_detail=f"Gemini {model} wrote "
                                      f"{len(segments)} segment(s)")
                except Exception as exc:  # noqa: BLE001 - retry/next/fallback
                    last_error = str(exc)[:200]
                    if "503" in last_error and attempt == 1:
                        time.sleep(5)
                        continue
                    break
        detail = (f"Gemini unavailable ({last_error}) — deterministic "
                  "fallback copy from verified facts (labelled fallback)")
    else:
        detail = ("GEMINI_API_KEY not set — deterministic fallback copy "
                  "from verified facts (labelled fallback, not Gemini)")
    return AffiliateScript(
        variant=variant, target_seconds=float(target_seconds),
        segments=_fallback_script(product, variant, target_seconds,
                                  visible_demonstration),
        engine=PLANNER_FALLBACK, engine_detail=detail)


def script_estimated_total(script: AffiliateScript) -> float:
    """Estimated total narration time (replaced by measured TTS)."""
    return round(sum(s.estimated_sec for s in script.segments), 2)


def footage_fit_report(script: AffiliateScript,
                       footage_seconds: float) -> dict:
    """Compare estimated narration vs available footage.

    Never auto-truncates: when narration is longer than the footage,
    the report names the conflict and the four resolution options
    (§14) for the user to choose. Returns a dict, never raises.
    """
    estimated = script_estimated_total(script)
    overflow = round(estimated - footage_seconds, 2)
    if overflow <= 0:
        return {"fits": True, "estimated_sec": estimated,
                "footage_sec": footage_seconds, "overflow_sec": 0.0,
                "options": []}
    return {
        "fits": False,
        "estimated_sec": estimated,
        "footage_sec": footage_seconds,
        "overflow_sec": overflow,
        "options": [
            "shorten_script_with_approval",
            "reallocate_visual_segments",
            "use_additional_authorized_footage",
            "report_unresolved_conflict",
        ],
        "note": "Narration is longer than the available footage. Speech "
                "is never truncated or accelerated — pick a resolution.",
    }


def script_from_translation(record: TranslationRecord, *,
                          target_seconds: float = 0.0) -> AffiliateScript:
    """Build a dub script 1:1 from translated segments.

    Each translated line becomes one script segment with its
    ORIGINAL timing window and speaker_id preserved, so the voice
    stage can dub each character with their own voice, consistently
    across the video. Sections follow position (first line HOOK,
    last line CALL_TO_ACTION, the rest DEMONSTRATION) — the dub
    script mirrors the source, it does not invent structure.

    Requires real translated segments: a fallback record with no
    translations raises instead of producing an empty dub script.
    The result is UNAPPROVED — the user must approve before TTS.
    """
    lines = record.translated_segments or record.rewritten_segments
    if not lines:
        raise ValueError(
            "no translated segments to dub: the translation record "
            f"(engine={record.engine}) holds no Vietnamese text")
    segments: list[ScriptSegment] = []
    for i, line in enumerate(lines):
        if i == 0:
            section = "HOOK"
        elif i == len(lines) - 1 and len(lines) > 1:
            section = "CALL_TO_ACTION"
        else:
            section = "DEMONSTRATION"
        text = str(line.get("text", "")).strip()
        segments.append(ScriptSegment(
            segment_id=f"SEG{i + 1:02d}", section=section, text=text,
            speaker_id=str(line.get("speaker_id", "SPEAKER_00")),
            start_time=float(line.get("start", 0.0)),
            end_time=float(line.get("end", 0.0)),
            estimated_sec=round(estimate_speech_duration(text), 2)))
    total = target_seconds or sum(s.estimated_sec for s in segments)
    return AffiliateScript(
        variant="dubbed_translation", target_seconds=round(total, 2),
        segments=segments, engine=record.engine,
        engine_detail=f"dub script from {len(segments)} translated "
                      f"segment(s), style={record.style}")


def approve_script(script: AffiliateScript, *, approved_by: str,
                   note: str = "") -> AffiliateScript:
    """Record user approval (in place + returned). Approval is what
    unlocks TTS and export; an edited script must be re-approved by
    calling this again after edits (editors must clear approval)."""
    script.approved = True
    script.approved_by = approved_by
    script.approved_at = datetime.now(timezone.utc).isoformat()
    script.approval_note = note
    return script


def clear_approval_on_edit(script: AffiliateScript) -> AffiliateScript:
    """Any edit invalidates the previous approval — by construction,
    the user must re-approve the edited text before TTS."""
    script.approved = False
    script.approved_by = ""
    script.approved_at = ""
    script.approval_note = ""
    return script
