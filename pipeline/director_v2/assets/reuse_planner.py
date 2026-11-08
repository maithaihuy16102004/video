"""Asset reuse planner.

Maps 40-60 shots onto 10-25 master/environment plates.
Tracks reuse operations: DIRECT, CROP, REFRAME, PARALLAX, RELIGHT.
"""
from __future__ import annotations

from typing import Any

from ..schemas.assets import AssetManifest, AssetRequirement, ReuseEntry, ReuseOp, ReusePlan
from ..schemas.core import LayerRole, NormRect
from ..schemas.plan import Shot, ShotPlan


def plan_asset_reuse(shot_plan: ShotPlan, manifest: AssetManifest) -> tuple[ReusePlan, ShotPlan]:
    """Assigns asset requirements and reuse operations to shot layers."""
    entries: list[ReuseEntry] = []
    req_usage_count: dict[str, int] = {}
    slots_served = 0

    # Build index of requirements by semantic key and kind
    env_reqs_by_loc: dict[str, list[AssetRequirement]] = {}
    fg_reqs_by_loc: dict[str, list[AssetRequirement]] = {}

    for req in manifest.requirements:
        if "env:" in req.semantic_key or "location:" in req.semantic_key:
            env_reqs_by_loc.setdefault(req.subject_id, []).append(req)
        elif "fg:" in req.semantic_key:
            fg_reqs_by_loc.setdefault(req.subject_id, []).append(req)

    # For each shot, assign the best reusable requirement to its BG and FG layers
    for shot in shot_plan.shots:
        candidates = env_reqs_by_loc.get(shot.location_id, [])
        # Match perspective & height bucket if possible
        matched_req = None
        for c in candidates:
            if c.perspective_family == shot.perspective_type.value and c.camera_height_bucket == shot.camera_height.value:
                matched_req = c
                break
        if not matched_req and candidates:
            matched_req = candidates[0]

        if matched_req:
            is_first = (req_usage_count.get(matched_req.requirement_id, 0) == 0)
            req_usage_count[matched_req.requirement_id] = req_usage_count.get(matched_req.requirement_id, 0) + 1
            ops = [ReuseOp.DIRECT] if is_first else [ReuseOp.REFRAME, ReuseOp.PARALLAX]

            # Reframe crop depending on shot type
            crop = None
            if "CLOSE" in shot.shot_type.value:
                ops.append(ReuseOp.CROP)
                crop = NormRect(x=0.15, y=0.15, w=0.70, h=0.70)
            elif "WIDE" in shot.shot_type.value:
                crop = NormRect(x=0.0, y=0.0, w=1.0, h=1.0)

            # Assign to BG layer
            for layer in shot.layers:
                if layer.role in (LayerRole.BG, LayerRole.FAR_BG, LayerRole.MG):
                    layer.requirement_id = matched_req.requirement_id
                    layer.source = "generated" if is_first else "reuse"
                    layer.crop = crop

            shot.asset_requirements.append(matched_req.requirement_id)
            if not is_first:
                shot.reusable_asset_ids.append(matched_req.requirement_id)

            entries.append(ReuseEntry(
                shot_id=shot.shot_id,
                layer_role=LayerRole.BG,
                requirement_id=matched_req.requirement_id,
                ops=ops,
                crop=crop,
                is_first_use=is_first,
                reason="First generation" if is_first else f"Reframe/parallax reuse #{req_usage_count[matched_req.requirement_id]}",
            ))
            slots_served += 1

        # Foreground check
        if shot.foreground_occlusion >= 0.20:
            fg_cands = fg_reqs_by_loc.get(shot.location_id, [])
            if fg_cands:
                fg_req = fg_cands[0]
                is_first_fg = (req_usage_count.get(fg_req.requirement_id, 0) == 0)
                req_usage_count[fg_req.requirement_id] = req_usage_count.get(fg_req.requirement_id, 0) + 1
                for layer in shot.layers:
                    if layer.role == LayerRole.FG:
                        layer.requirement_id = fg_req.requirement_id
                        layer.source = "generated" if is_first_fg else "reuse"

                shot.asset_requirements.append(fg_req.requirement_id)
                if not is_first_fg:
                    shot.reusable_asset_ids.append(fg_req.requirement_id)

                entries.append(ReuseEntry(
                    shot_id=shot.shot_id,
                    layer_role=LayerRole.FG,
                    requirement_id=fg_req.requirement_id,
                    ops=[ReuseOp.DIRECT] if is_first_fg else [ReuseOp.PARALLAX],
                    is_first_use=is_first_fg,
                    reason="First foreground plate" if is_first_fg else "Parallax reuse",
                ))
                slots_served += 1

    unique_count = len(manifest.requirements)
    ratio = round(slots_served / max(1, unique_count), 2)

    reuse_plan = ReusePlan(
        entries=entries,
        shot_count=len(shot_plan.shots),
        unique_image_requirements=unique_count,
        generated_layer_slots=slots_served,
        reuse_ratio=ratio,
    )
    return reuse_plan, shot_plan
