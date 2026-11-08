"""Cost Ledger and estimation.

Estimates and tracks API calls, cache hits, retries, and estimated USD cost.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import ProjectConfig
from ..schemas.assets import AssetManifest, AssetStatus
from ..schemas.reports import CostEstimate, CostLine

PRICES_PATH = Path(__file__).resolve().parents[1] / "data" / "price_table.json"


def load_price_table() -> dict[str, Any]:
    if PRICES_PATH.exists():
        return json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    return {}


def estimate_costs(
    manifest: AssetManifest,
    config: ProjectConfig,
    dry_run: bool = True,
) -> CostEstimate:
    """Builds CostEstimate report from AssetManifest and configuration."""
    prices = load_price_table()
    img_prices = prices.get("images", {})

    lines: list[CostLine] = []
    counters = {
        "total_requirements": len(manifest.requirements),
        "cached": sum(1 for a in manifest.assets if a.status == AssetStatus.CACHED),
        "to_generate": sum(1 for a in manifest.assets if a.status in (AssetStatus.PLANNED, AssetStatus.SKIPPED_DRY_RUN)),
        "skipped_draft": sum(1 for a in manifest.assets if a.status == AssetStatus.SKIPPED_DRAFT),
    }

    total_usd = 0.0
    warnings: list[str] = []

    # Group planned assets by model
    model_counts: dict[str, int] = {}
    for a in manifest.assets:
        if a.status in (AssetStatus.PLANNED, AssetStatus.SKIPPED_DRY_RUN):
            m = a.model or config.models.main_image_model
            model_counts[m] = model_counts.get(m, 0) + 1

    for model, count in model_counts.items():
        price_info = img_prices.get(model, {})
        unit_p = price_info.get(config.image_size)
        if unit_p is not None:
            sub = count * float(unit_p)
            total_usd += sub
            lines.append(CostLine(
                item="Image generation",
                model=model,
                count=count,
                unit_price_usd=float(unit_p),
                subtotal_usd=round(sub, 4),
                note=f"Verified: {price_info.get('verified', False)}",
            ))
        else:
            warnings.append(f"Model {model} has unverified pricing in price_table.json")
            lines.append(CostLine(
                item="Image generation (unpriced)",
                model=model,
                count=count,
                note="Unverified rate",
            ))

    return CostEstimate(
        currency="USD",
        quality=config.quality.value,
        dry_run=dry_run,
        lines=lines,
        expected_total_usd=round(total_usd, 4) if total_usd > 0 else 0.0,
        counters=counters,
        warnings=warnings,
    )
