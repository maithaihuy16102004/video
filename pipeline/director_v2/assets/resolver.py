"""Asset Resolver.

Checks cache first before scheduling generation.
Marks status: CACHED, SKIPPED_DRAFT, SKIPPED_DRY_RUN, or PLANNED.
"""
from __future__ import annotations

from typing import Any

from ..config import ProjectConfig
from ..schemas.assets import Asset, AssetManifest, AssetRequirement, AssetStatus
from .cache import AssetCache


def resolve_assets(
    manifest: AssetManifest,
    cache: AssetCache,
    config: ProjectConfig,
    dry_run: bool = True,
) -> AssetManifest:
    """Resolves existing assets from cache and tags remaining requirements."""
    resolved_assets: list[Asset] = []

    for req in manifest.requirements:
        model_name = config.models.image_model(req.tier)
        ckey = cache.compute_cache_key(req, model_name)
        req.cache_key = ckey
        cached_file = cache.get(ckey)

        if cached_file:
            resolved_assets.append(Asset(
                requirement_id=req.requirement_id,
                status=AssetStatus.CACHED,
                path=str(cached_file),
                model=model_name,
                tier=req.tier,
                cache_key=ckey,
                cache_hit=True,
            ))
        elif config.quality.value == "DRAFT":
            resolved_assets.append(Asset(
                requirement_id=req.requirement_id,
                status=AssetStatus.SKIPPED_DRAFT,
                model=model_name,
                tier=req.tier,
                cache_key=ckey,
            ))
        elif dry_run:
            resolved_assets.append(Asset(
                requirement_id=req.requirement_id,
                status=AssetStatus.SKIPPED_DRY_RUN,
                model=model_name,
                tier=req.tier,
                cache_key=ckey,
            ))
        else:
            resolved_assets.append(Asset(
                requirement_id=req.requirement_id,
                status=AssetStatus.PLANNED,
                model=model_name,
                tier=req.tier,
                cache_key=ckey,
            ))

    manifest.assets = resolved_assets
    return manifest
