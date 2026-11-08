"""Extracts AssetRequirements from ShotPlan and ProjectBible.

Rule: 50 shots != 50 Gemini calls.
Assets are identified by semantic keys so the same environment plate
or master asset can serve multiple shots via cropping and parallax.
"""
from __future__ import annotations

from typing import Any

from ..schemas.assets import AssetKind, AssetManifest, AssetRequirement
from ..schemas.bible import Location, ProjectBible
from ..schemas.core import ImageTier, LayerRole
from ..schemas.plan import Shot, ShotPlan


def extract_asset_requirements(
    shot_plan: ShotPlan,
    bible: ProjectBible,
    locations: list[Location],
    quality_tier: str = "STANDARD",
) -> AssetManifest:
    """Consolidates visual needs across all shots into unique AssetRequirements."""
    reqs: dict[str, AssetRequirement] = {}
    loc_map: dict[str, Location] = {loc.id: loc for loc in locations}

    # 1. Location Masters (1 per unique location)
    for loc in locations:
        key = f"LOC_MASTER_{loc.id}"
        reqs[key] = AssetRequirement(
            requirement_id=key,
            kind=AssetKind.LOCATION_MASTER,
            layer_roles=[LayerRole.BG, LayerRole.FAR_BG],
            subject_id=loc.id,
            semantic_key=f"location:{loc.id}:master",
            description=f"Wide master reference plate for {loc.name}. {loc.description}",
            tier=ImageTier.HERO if quality_tier == "MASTER" else ImageTier.MAIN,
            aspect_ratio="21:9",  # Ultra-wide overscan for panning/reframing
            image_size="1K",
            historical_constraints=bible.historical_constraints,
        )

    # 2. Environment Plates & Foregrounds required by Shots
    for shot in shot_plan.shots:
        loc = loc_map.get(shot.location_id)
        loc_name = loc.name if loc else "Environment"

        # Unique key based on location + perspective + camera height bucket
        h_bucket = shot.camera_height.value
        p_fam = shot.perspective_type.value
        plate_key = f"ENV_{shot.location_id}_{p_fam}_{h_bucket}"

        if plate_key not in reqs:
            reqs[plate_key] = AssetRequirement(
                requirement_id=plate_key,
                kind=AssetKind.ENVIRONMENT_PLATE,
                layer_roles=[LayerRole.FAR_BG, LayerRole.BG, LayerRole.MG],
                subject_id=shot.location_id,
                semantic_key=f"env:{shot.location_id}:{p_fam}:{h_bucket}",
                description=(
                    f"Historical environment plate for {loc_name}. "
                    f"Perspective: {p_fam}, camera height: {h_bucket}. "
                    f"Background: {shot.background}. Far background: {shot.far_background}."
                ),
                shot_ids=[shot.shot_id],
                tier=ImageTier.MAIN,
                aspect_ratio="16:9",
                image_size="1K",
                camera_height_bucket=h_bucket,
                perspective_family=p_fam,
                lighting_key=shot.key_light_direction.value,
                historical_constraints=shot.historical_constraints,
            )
        else:
            reqs[plate_key].shot_ids.append(shot.shot_id)

        # Foreground occluder if significant occlusion is planned
        if shot.foreground_occlusion >= 0.20:
            fg_key = f"FG_{shot.location_id}_{h_bucket}"
            if fg_key not in reqs:
                reqs[fg_key] = AssetRequirement(
                    requirement_id=fg_key,
                    kind=AssetKind.FOREGROUND_ELEMENT,
                    layer_roles=[LayerRole.FG],
                    subject_id=shot.location_id,
                    semantic_key=f"fg:{shot.location_id}:{h_bucket}",
                    description=f"Isolated foreground architectural occluder for {loc_name}: {shot.foreground}",
                    shot_ids=[shot.shot_id],
                    tier=ImageTier.FAST,
                    matte="chroma_green",
                    image_size="1K",
                )
            else:
                reqs[fg_key].shot_ids.append(shot.shot_id)

    return AssetManifest(
        requirements=list(reqs.values()),
        assets=[],
    )
