"""Shopee Affiliate content package (§20).

For each completed video: TikTok caption, Facebook Reels caption,
suggested title, hashtags, product description, CTA text, affiliate
disclosure, the USER-PROVIDED affiliate link, and a thumbnail
suggestion.

Rules:
  * The affiliate link is copied verbatim from the product record.
    When the user provided none, the package records that plainly —
    a link is NEVER invented.
  * No auto-publish anywhere. No sales or revenue promises.
  * Description/CTA copy uses verified product facts only; the claim
    scanner from product.py flags anything that looks invented.
"""
from __future__ import annotations

import re

from .product import (
    effective_disclosure,
    neutral_description,
    price_display,
    product_claim_findings,
)
from .schema import AffiliateScript, ProductInfo, SourceAuthorization

# Generic, non-factual discovery hashtags. These describe the video
# format / platform, never the product's qualities.
_GENERIC_HASHTAGS = ["#shopee", "#shopeehaul", "#review", "#tiktokmademebuyit",
                     "#affiliate", "#giohang"]

_PROMISE_RE = re.compile(
    r"chắc\s*chắn\s*(bán|kiếm|thu)|đảm\s*bảo\s*(bán|thu\s*nhập|doanh\s*thu)"
    r"|thu\s*nhập\s*(khủng|cao)|làm\s*giàu|kiếm\s*tiền\s*(dễ|nhanh)",
    re.IGNORECASE)


def _slug_hashtag(text: str) -> str:
    """Turn a category/brand word into a hashtag slug (diacritics
    stripped, spaces removed). Empty input -> ''."""
    import unicodedata
    normalized = unicodedata.normalize("NFD", text or "")
    ascii_text = "".join(c for c in normalized
                         if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-zA-Z0-9]+", "", ascii_text)
    return f"#{slug.lower()}" if slug else ""


def build_hashtags(product: ProductInfo, limit: int = 8) -> list[str]:
    """Hashtags from the product category/brand + generic tags.

    No quality/superlative claims are turned into hashtags.
    """
    tags: list[str] = []
    for source in (product.product_category, product.brand_name):
        tag = _slug_hashtag(source)
        if tag and tag not in tags:
            tags.append(tag)
    for tag in _GENERIC_HASHTAGS:
        if len(tags) >= limit:
            break
        if tag not in tags:
            tags.append(tag)
    return tags[:limit]


def build_marketing_package(product: ProductInfo,
                            script: AffiliateScript | None,
                            *, video_duration_sec: float = 0.0,
                            hook_text: str = "",
                            authorization: SourceAuthorization | None = None
                            ) -> dict:
    """Build the full marketing package (data only — no publishing).

    Product facts come ONLY from the user-supplied ``product`` fields
    (and the user-approved script's hook). Nothing is ever taken from
    an unconfirmed source video: this function takes no analysis
    input at all, and when the source authorization is UNKNOWN or
    unconfirmed the package carries an explicit ``source_warning``.
    """
    hook = hook_text
    if not hook and script is not None:
        for seg in script.segments:
            if seg.section == "HOOK":
                hook = seg.text
                break
    title = (product.product_name or "Sản phẩm").strip()
    description_parts = [neutral_description(product)]
    if product.product_features:
        description_parts.append("Đặc điểm: "
                                 + "; ".join(product.product_features) + ".")
    price = price_display(product)
    if price:
        description_parts.append(f"Giá theo thông tin người bán: {price}.")
    cta = product.call_to_action or (
        "Nếu thấy phù hợp, bạn có thể xem thông tin sản phẩm ở giỏ hàng "
        "hoặc đường dẫn mình cung cấp.")
    disclosure = effective_disclosure(product)
    hashtags = build_hashtags(product)
    caption_base = f"{hook} {title}".strip()
    tiktok_caption = f"{caption_base}\n{cta}\n{' '.join(hashtags)}"
    if disclosure:
        tiktok_caption += f"\n{disclosure}"
    reels_caption = f"{caption_base}\n{cta}"
    if disclosure:
        reels_caption += f"\n{disclosure}"
    reels_caption += f"\n{' '.join(hashtags)}"
    link = product.affiliate_url.strip()
    source_warning = ""
    if authorization is not None and (
            authorization.authorization_type == "UNKNOWN"
            or not authorization.commercial_rights_confirmed):
        source_warning = (
            "Source authorization is unconfirmed: no product facts "
            "were taken from the source video. All facts in this "
            "package come from the user-supplied product information.")
    package = {
        "title": title,
        "facts_source": "user_input_only",
        "source_warning": source_warning,
        "tiktok_caption": tiktok_caption[:2200],
        "reels_caption": reels_caption,
        "description": " ".join(description_parts),
        "hashtags": hashtags,
        "cta_text": cta,
        "disclosure": disclosure,
        "affiliate_link": link if link else None,
        "affiliate_link_provided": bool(link),
        "thumbnail_suggestion": {
            "text_overlay": hook[:60] if hook else title[:60],
            "suggested_timestamp_sec": 1.0,
            "note": "Suggestion only — the thumbnail is chosen by the "
                    "user from a real frame of the exported video.",
        },
        "video_duration_sec": round(video_duration_sec, 2),
        "auto_publish": False,
        "claim_findings": product_claim_findings(product),
    }
    return package


def check_marketing_promises(package: dict) -> list[str]:
    """Flag sales/revenue-promise wording in the package text."""
    problems: list[str] = []
    for key in ("tiktok_caption", "reels_caption", "description", "cta_text"):
        text = package.get(key, "") or ""
        for match in _PROMISE_RE.finditer(text):
            problems.append(f"{key}: promise-like wording "
                            f"{match.group(0)!r} — remove it")
    if package.get("affiliate_link_provided") and not package.get("disclosure"):
        problems.append("affiliate link present but no disclosure text")
    return problems
