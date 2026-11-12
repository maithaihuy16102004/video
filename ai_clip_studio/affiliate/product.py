"""Product configuration (§5) — user facts only, never invented.

Everything in a ProductInfo comes from the user (manual entry or an
approved integration import). This module NEVER invents a price,
discount, certification, medical benefit, or performance claim. When
information is missing, the copy layer must use neutral wording built
only from the visible demonstration and verified user-provided facts
(see ``neutral_description``).

The claim scanner (``scan_for_claims``) is a heuristic tripwire: it
flags wording that LOOKS like an invented/unsupported claim so a human
reviews it. It never silently rewrites product text.
"""
from __future__ import annotations

import re

from .schema import ProductInfo

DEFAULT_DISCLOSURE = (
    "Video này có chứa liên kết tiếp thị liên kết (affiliate). "
    "Nếu bạn mua hàng qua liên kết mình cung cấp, mình có thể nhận "
    "một khoản hoa hồng nhỏ mà bạn không phải trả thêm chi phí nào."
)

# Heuristic claim patterns (Vietnamese + common marketing English).
# A match is a REVIEW flag, not proof of a false claim — the user may
# have verified the fact. The scanner reports; a human decides.
_CLAIM_PATTERNS: list[tuple[str, str]] = [
    (r"chữa\s+(khỏi|bệnh|trị)|trị\s+(dứt|khỏi|bệnh)|giảm\s+cân|tăng\s+cân|trắng\s+da|trị\s+mụn",
     "medical/beauty outcome claim"),
    (r"giảm\s+giá\s*\d|khuyến\s*mãi\s*\d|sale\s*\d|off\s*\d|-\d+\s*%",
     "discount/percentage claim — verify against the live listing"),
    (r"chính\s*hãng|chứng\s*nhận|iso\s*\d|fda|ce\b|tiêu\s*chuẩn\s+quốc\s*tế",
     "certification/authenticity claim — needs documentation"),
    (r"100\s*%|tuyệt\s*đối|đảm\s*bảo\s+100|hiệu\s*quả\s+tức\s*thì|ngay\s+lập\s*tức",
     "absolute/performance claim — needs evidence"),
    (r"bán\s+chạy\s+nhất|số\s*1|tốt\s+nhất|duy\s+nhất",
     "superlative claim — needs evidence"),
    (r"mình\s+đã\s+(dùng|thử|trải\s+nghiệm)|tôi\s+đã\s+(dùng|thử|trải\s+nghiệm)",
     "personal-testimonial wording — needs explicit confirmation"),
    (r"thu\s*nhập|kiếm\s+tiền|đảm\s*bảo\s+doanh\s*thu|làm\s+giàu",
     "earnings/revenue promise — never allowed in affiliate copy"),
]


def scan_for_claims(text: str) -> list[dict[str, str]]:
    """Flag claim-like wording. Returns [{pattern, kind, excerpt}]."""
    findings: list[dict[str, str]] = []
    for pattern, kind in _CLAIM_PATTERNS:
        for match in re.finditer(pattern, text or "", re.IGNORECASE):
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 30)
            findings.append({
                "kind": kind,
                "excerpt": text[start:end].strip(),
                "matched": match.group(0),
            })
    return findings


def product_claim_findings(product: ProductInfo) -> list[dict[str, str]]:
    """Scan every user-facing product text field for claim wording."""
    findings: list[dict[str, str]] = []
    fields = {
        "product_name": product.product_name,
        "product_features": "\n".join(product.product_features),
        "product_benefits": "\n".join(product.product_benefits),
        "call_to_action": product.call_to_action,
        "target_audience": product.target_audience,
    }
    for field_name, text in fields.items():
        for finding in scan_for_claims(text):
            findings.append({"field": field_name, **finding})
    return findings


def neutral_description(product: ProductInfo,
                        visible_demonstration: str = "") -> str:
    """Neutral wording from verified facts + visible demo ONLY.

    Used when product information is incomplete. It states the product
    name, the category, and what the video visibly shows — nothing
    else. No benefits, no price, no superlatives are added.
    """
    parts = [f"Sản phẩm: {product.product_name}."]
    if product.product_category:
        parts.append(f"Loại sản phẩm: {product.product_category}.")
    if visible_demonstration.strip():
        parts.append(f"Trong video, sản phẩm được cho thấy: "
                     f"{visible_demonstration.strip()}")
    if product.brand_name:
        parts.append(f"Thương hiệu: {product.brand_name}.")
    return " ".join(parts)


def effective_disclosure(product: ProductInfo) -> str:
    """The disclosure to show: user-provided text, else the default
    template. An empty string is returned only when there is no
    affiliate link AND the user explicitly left the disclosure blank
    (the schema gate AFF019 requires a disclosure whenever a link is
    present)."""
    if product.disclosure_text.strip():
        return product.disclosure_text.strip()
    if product.affiliate_url.strip():
        return DEFAULT_DISCLOSURE
    return ""


def price_display(product: ProductInfo) -> str:
    """Formatted price, or "" when the user did not provide one.

    A missing price is never filled in from anywhere else.
    """
    if product.product_price is None:
        return ""
    amount = product.product_price
    if float(amount) == int(amount):
        rendered = f"{int(amount):,}".replace(",", ".")
    else:
        rendered = f"{amount:,.2f}".replace(",", ".")
    currency = (product.price_currency or "VND").strip()
    return f"{rendered} {currency}".strip()


def product_facts_block(product: ProductInfo) -> dict:
    """Verified-facts block handed to translation/script stages.

    Only user-provided fields appear here. Downstream stages must
    treat anything absent from this block as UNKNOWN — never to be
    filled in by the model.
    """
    return {
        "product_name": product.product_name,
        "product_category": product.product_category or None,
        "brand_name": product.brand_name or None,
        "price_display": price_display(product) or None,
        "features": list(product.product_features),
        "benefits": list(product.product_benefits),
        "target_audience": product.target_audience or None,
        "call_to_action": product.call_to_action or None,
        "shopee_product_url": product.shopee_product_url or None,
        "affiliate_url": product.affiliate_url or None,
        "seller_information": product.seller_information or None,
        "disclosure": effective_disclosure(product) or None,
        "personally_tested_confirmed": bool(product.personally_tested_confirmed),
    }
