"""Vietnamese translation (§11) — Gemini with a labelled fallback.

Modes:
  * DIRECT_TRANSLATION    — translate source speech accurately.
  * NATURAL_LOCALIZATION  — natural Vietnamese, same factual meaning.
  * AFFILIATE_COPYWRITING — NEW Vietnamese copy from verified product
    facts + visible demonstrations (not a translation of the source).

Original, translation, and rewrite are kept as SEPARATE records in
``TranslationRecord`` (§11) — the original meaning is never silently
replaced.

Engine labelling follows the established ``gemini_planner`` pattern:
``engine`` is ``"gemini:<model>"`` only when a real Gemini call
produced the output. When ``GEMINI_API_KEY`` is absent (the current
state of this VM) the fallback runs and says so:

  * DIRECT / NATURAL fallback: translation is NOT fabricated. The
    segments are returned untranslated with
    ``needs_human_review=True`` — a human translator (or a later
    Gemini run) must supply the Vietnamese text. Fabricating a
    Chinese→Vietnamese translation without a model would violate the
    no-fabrication rule.
  * AFFILIATE_COPYWRITING fallback: deterministic copy built ONLY
    from the verified product-facts block (product.py) and the
    visible-demonstration notes. This is new copy, not a translation,
    so a template fallback is honest — it adds no facts.

Numbers, units, and model numbers are preserved by contract: the
Gemini prompt requires them verbatim, and ``qa.py`` re-checks digit
sequences between original and translation.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error

from ..gemini_planner import MODELS, _gemini_generate
from .product import neutral_description, product_facts_block
from .schema import ProductInfo, TranslationRecord

PLANNER_GEMINI = "gemini"
PLANNER_FALLBACK = "fallback"

# Words the copy stages must never ADD (discount/urgency fabrication).
_FORBIDDEN_ADDITIONS = (
    "giảm giá", "khuyến mãi", "chỉ còn", "duy nhất hôm nay",
    "số lượng có hạn", "mua ngay kẻo hết", "giá sốc", "sale",
)


def _segments_text(segments: list[dict]) -> str:
    return "\n".join(f"{i + 1}. [{s.get('start', 0)}-{s.get('end', 0)}] "
                     f"{s.get('text', '')}"
                     for i, s in enumerate(segments))


def _translation_prompt(segments: list[dict], mode: str,
                        facts: dict, style: str = "neutral") -> str:
    facts_json = json.dumps(facts, ensure_ascii=False, indent=1)
    if mode == "DIRECT_TRANSLATION":
        instruction = ("Dịch chính xác từng đoạn thoại tiếng Trung sang "
                       "tiếng Việt tự nhiên, giữ nguyên nghĩa gốc.")
    elif mode == "NATURAL_LOCALIZATION":
        instruction = ("Viết lại từng đoạn thoại tiếng Trung thành tiếng "
                       "Việt tự nhiên, giữ nguyên nghĩa và sự thật gốc, "
                       "diễn đạt như người Việt nói.")
    else:  # AFFILIATE_COPYWRITING
        instruction = ("Viết lời giới thiệu sản phẩm bằng tiếng Việt từ "
                       "SỰ THẬT ĐÃ KIỂM CHỨNG và những gì video cho thấy. "
                       "Đây là lời mới, không phải bản dịch.")
    if style == "humorous_viral_review":
        # Standing requirement (Mai, 2026-11-12): the dubbing
        # translation stays CLOSE to the original meaning, in a
        # humorous, viral, review-style Vietnamese voice. Humour in
        # the WORDING only — facts, numbers, prices, measurements
        # and claims stay faithful; the fidelity rules below still
        # apply in full.
        instruction += (
            "\nGIỌNG VĂN: hài hước, viral, kiểu review — cách nói vui "
            "nhộn, gần gũi như người review trên TikTok, nhưng BÁM SÁT "
            "NGHĨA GỐC: giữ đúng ý, sự thật, con số, đơn vị đo, giá và "
            "tên sản phẩm của từng đoạn. Hài hước chỉ ở cách diễn đạt, "
            "KHÔNG bịa thêm sự thật, KHÔNG đổi nghĩa, KHÔNG thêm giảm "
            "giá, khuyến mãi hay áp lực mua.")
    return (
        "Bạn là biên dịch viên và biên tập viên video tiếp thị liên kết. "
        f"{instruction}\n"
        "QUY TẮC BẮT BUỘC:\n"
        "1. Giữ nguyên mọi con số, đơn vị đo, mã model, tên thương hiệu.\n"
        "2. Không bịa giá, giảm giá, chứng nhận, lợi ích y tế, hiệu năng.\n"
        "3. Không thêm từ ngữ tạo áp lực mua (giảm giá, số lượng có hạn...).\n"
        "4. Không bịa lời chứng thực cá nhân ('mình đã dùng...').\n"
        "5. Trả về CHỈ JSON hợp lệ, không giải thích, không markdown:\n"
        '{"segments": [{"index": 1, "text": "tiếng Việt"}]}.\n'
        "Số lượng segment và thứ tự phải khớp đúng đầu vào.\n\n"
        f"SỰ THẬT ĐÃ KIỂM CHỨNG (không thêm sự thật nào khác):\n{facts_json}\n\n"
        f"ĐOẠN GỐC:\n{_segments_text(segments)}\n"
    )


def _parse_gemini_segments(raw: str, expected: int) -> list[str]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    payload = json.loads(text)
    items = payload["segments"] if isinstance(payload, dict) else payload
    if not isinstance(items, list) or len(items) != expected:
        raise ValueError(
            f"Gemini returned {len(items) if isinstance(items, list) else '?'} "
            f"segments, expected {expected}")
    out = []
    for item in items:
        if isinstance(item, dict):
            out.append(str(item.get("text", "")).strip())
        else:
            out.append(str(item).strip())
    if any(not t for t in out):
        raise ValueError("Gemini returned an empty translated segment")
    return out


def _fallback_copywriting(segments: list[dict], product: ProductInfo,
                          visible_demo: str) -> list[str]:
    """Deterministic affiliate copy from verified facts ONLY.

    One neutral line per input segment slot (same count, same timing
    windows), built from the product name/category/demo — no invented
    benefits, prices, or claims. Labelled fallback, never Gemini.
    """
    base = neutral_description(product, visible_demo)
    lines = [base]
    if product.product_features:
        lines.append("Sản phẩm có các đặc điểm: "
                     + "; ".join(product.product_features) + ".")
    if product.call_to_action:
        lines.append(product.call_to_action)
    out = []
    for i in range(len(segments)):
        out.append(lines[i] if i < len(lines) else base)
    return out


def translate_segments(segments: list[dict], product: ProductInfo, *,
                       mode: str = "NATURAL_LOCALIZATION",
                       style: str = "neutral",
                       visible_demonstration: str = "",
                       api_key: str | None = None) -> TranslationRecord:
    """Translate / localize / rewrite segments. Segments are dicts
    with at least {"start","end","text"} (ASR or OCR shape); a
    "speaker_id" key, when present, is preserved through translation
    so per-character dubbing keeps its speaker labels.

    Returns a TranslationRecord with SEPARATE original / translated /
    rewritten lists and an honest engine label.
    """
    if mode not in ("DIRECT_TRANSLATION", "NATURAL_LOCALIZATION",
                    "AFFILIATE_COPYWRITING"):
        raise ValueError(f"unknown translation mode {mode!r}")
    if style not in ("neutral", "humorous_viral_review"):
        raise ValueError(f"unknown translation style {style!r}")
    originals = [{"start": float(s.get("start", 0.0)),
                  "end": float(s.get("end", 0.0)),
                  "text": str(s.get("text", "")),
                  "speaker_id": str(s.get("speaker_id", "SPEAKER_00"))}
                 for s in segments]
    facts = product_facts_block(product)
    key = api_key or os.environ.get("GEMINI_API_KEY", "")

    if key:
        last_error = ""
        for model in MODELS:
            for attempt in (1, 2):
                try:
                    raw = _gemini_generate(
                        _translation_prompt(originals, mode, facts, style),
                        model, key)
                    texts = _parse_gemini_segments(raw, len(originals))
                    translated = [dict(seg, text=text)
                                  for seg, text in zip(originals, texts)]
                    record = TranslationRecord(
                        mode=mode, engine=f"gemini:{model}",
                        engine_detail=f"Gemini {model} translated "
                                      f"{len(originals)} segment(s)",
                        style=style,
                        original_segments=originals)
                    if mode == "AFFILIATE_COPYWRITING":
                        record.rewritten_segments = translated
                    else:
                        record.translated_segments = translated
                    return record
                except Exception as exc:  # noqa: BLE001 - retry/next/fallback
                    last_error = str(exc)[:200]
                    if "503" in last_error and attempt == 1:
                        time.sleep(5)
                        continue
                    break
        fallback_detail = (f"Gemini unavailable ({last_error}) — labelled "
                           "fallback used")
    else:
        fallback_detail = ("GEMINI_API_KEY not set — labelled fallback used "
                           "(not Gemini output)")

    # ---- Fallback (honest, no fabricated translation) ----
    record = TranslationRecord(
        mode=mode, engine=PLANNER_FALLBACK, engine_detail=fallback_detail,
        style=style, original_segments=originals)
    if mode == "AFFILIATE_COPYWRITING":
        texts = _fallback_copywriting(originals, product,
                                      visible_demonstration)
        record.rewritten_segments = [dict(seg, text=text)
                                     for seg, text in zip(originals, texts)]
        record.review_notes.append(
            "Fallback copywriting from verified product facts only; "
            "review before TTS.")
    else:
        record.needs_human_review = True
        record.review_notes.append(
            "No Gemini key: segments were NOT translated. A human "
            "translator (or a Gemini run with a key) must supply the "
            "Vietnamese text — the fallback never invents translations.")
    return record


def translate_ocr_tracks(tracks: list[dict], product: ProductInfo, *,
                         mode: str = "NATURAL_LOCALIZATION",
                         style: str = "neutral",
                         api_key: str | None = None) -> list[dict]:
    """Translate OCR text tracks, preserving classification.

    Tracks classified PRODUCT_LABEL / BRAND_LOGO / CREATOR_ATTRIBUTION
    / WATERMARK get a translation for DISPLAY/REVIEW ONLY and are
    flagged ``replace_allowed=False`` — the edit engine must never
    auto-remove them (§7). SUBTITLE / PROMOTIONAL_OVERLAY tracks are
    the blur-then-overlay candidates for the Douyin edit: the edit
    engine blurs the Chinese regions and overlays Vietnamese
    subtitles from these translations. Returns new track dicts
    (input untouched).
    """
    from .schema import PROTECTED_TEXT_CLASSES
    segments = [{"start": t.get("start_time", 0.0),
                 "end": t.get("end_time", 0.0),
                 "text": t.get("original_text", "")} for t in tracks]
    record = translate_segments(segments, product, mode=mode, style=style,
                                api_key=api_key)
    translated = record.translated_segments or record.rewritten_segments
    out = []
    for track, seg in zip(tracks, segments):
        new = dict(track)
        cls = track.get("text_classification", "UNKNOWN")
        new["replace_allowed"] = cls not in PROTECTED_TEXT_CLASSES
        if translated:
            idx = segments.index(seg)
            new["translated_text"] = translated[idx]["text"]
        new["translation_engine"] = record.engine
        out.append(new)
    return out


def digit_sequences(text: str) -> list[str]:
    """Digit runs in a string — used by QA to check number preservation."""
    return re.findall(r"\d+(?:[.,]\d+)?", text or "")
