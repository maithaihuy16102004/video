"""Builds the final RenderManifest — the single contract Phase 2 renderers consume."""
from __future__ import annotations

from typing import Any

from ..config import ProjectConfig
from ..schemas.assets import AssetManifest
from ..schemas.core import DEFAULT_PARALLAX, LayerRole
from ..schemas.manifest import (
    AudioCue,
    CameraKey,
    CameraTrack,
    RenderLayer,
    RenderManifest,
    RenderOutput,
    RenderShot,
    RigPlacement,
)
from ..schemas.plan import ShotPlan


def build_render_manifest(
    shot_plan: ShotPlan,
    manifest: AssetManifest,
    config: ProjectConfig,
    project_id: str = "project_01",
) -> RenderManifest:
    """Combines ShotPlan and resolved assets into RenderManifest."""
    asset_by_req = {a.requirement_id: a for a in manifest.assets}

    render_shots: list[RenderShot] = []
    fps = config.fps

    for shot in shot_plan.shots:
        start_frame = round(shot.start_sec * fps)
        frame_count = max(1, round(shot.duration * fps))

        # Build layers with assigned asset paths or procedural hints
        render_layers: list[RenderLayer] = []
        for z_idx, layer_intent in enumerate(shot.layers):
            asset = asset_by_req.get(layer_intent.requirement_id or "")
            asset_path = asset.path if asset else None
            asset_status = asset.status.value if asset else None

            # Rig placement for CHARACTER layer
            rigs = []
            if layer_intent.role == LayerRole.CHARACTER:
                for cid in (shot.character_ids or ["CHAR_001"]):
                    rigs.append(RigPlacement(
                        character_id=cid,
                        x=shot.subject_x,
                        y=shot.subject_y,
                        scale=shot.subject_scale,
                        orientation=shot.body_orientation.value,
                        head_direction=shot.head_direction,
                        eyeline=shot.eyeline,
                        action_verb=shot.action_verb,
                        pose_family=shot.pose_family,
                        weight_distribution=shot.weight_distribution,
                    ))

            render_layers.append(RenderLayer(
                role=layer_intent.role,
                z=z_idx,
                source=layer_intent.source,
                requirement_id=layer_intent.requirement_id,
                asset_path=asset_path,
                asset_status=asset_status,
                crop=layer_intent.crop,
                parallax=layer_intent.parallax,
                matte=layer_intent.matte,
                description=layer_intent.description,
                procedural_hint=f"{layer_intent.role.value}: {layer_intent.description}",
                rigs=rigs,
            ))

        # Camera track with cinematic pan/push
        zoom_start = 1.0
        zoom_end = 1.08 if "PUSH" in shot.camera_motion.value else (0.95 if "PULL" in shot.camera_motion.value else 1.02)
        pan_x_end = 0.05 if "PAN_RIGHT" in shot.camera_motion.value else (-0.05 if "PAN_LEFT" in shot.camera_motion.value else 0.0)

        cam_track = CameraTrack(
            motion=shot.camera_motion.value,
            start=CameraKey(zoom=zoom_start, pan_x=0.0, pan_y=0.0),
            end=CameraKey(zoom=zoom_end, pan_x=pan_x_end, pan_y=0.0),
            shake=0.15 if "SHAKE" in shot.camera_motion.value else 0.0,
            reason=shot.camera_motion_reason,
        )

        audio_cues = []
        if shot.narration_text:
            audio_cues.append(AudioCue(
                kind="narration",
                text=shot.narration_text,
                start_sec=shot.start_sec,
                duration_sec=shot.duration,
            ))

        render_shots.append(RenderShot(
            shot_id=shot.shot_id,
            scene_id=shot.scene_id,
            start_sec=shot.start_sec,
            duration_sec=shot.duration,
            start_frame=start_frame,
            frame_count=frame_count,
            shot_type=shot.shot_type.value,
            camera_height=shot.camera_height.value if hasattr(shot.camera_height, "value") else str(shot.camera_height),
            camera_pitch=shot.camera_pitch,
            camera_yaw=shot.camera_yaw,
            lens_feel=shot.lens_feel,
            depth_axis=getattr(shot, "depth_axis", "Z_INTO_SCREEN"),
            perspective_type=shot.perspective_type.value,
            horizon_y=shot.horizon_y,
            vanishing_point_primary=shot.vanishing_point_primary.to_json_dict(),
            vanishing_point_secondary=shot.vanishing_point_secondary.to_json_dict() if shot.vanishing_point_secondary else None,
            layers=render_layers,
            camera=cam_track,
            lighting={
                "direction": shot.key_light_direction.value,
                "intensity": shot.key_light_intensity,
                "fill": shot.fill,
                "rim": shot.rim_light,
            },
            atmosphere=shot.atmosphere,
            transition_in=shot.transition_in.value,
            transition_out=shot.transition_out.value,
            audio=audio_cues,
            location_id=shot.location_id,
        ))

    output = RenderOutput(
        width=config.width,
        height=config.height,
        fps=config.fps,
        aspect_ratio=config.aspect_ratio.value,
        safe_area=config.safe_area,
        reframe_policy=config.reframe_policy,
    )

    total_frames = max(1, round(shot_plan.total_duration_sec * fps))
    renderer_hint = "pycairo_draft" if config.quality.value == "DRAFT" else "motion_canvas"

    return RenderManifest(
        project_id=project_id,
        quality=config.quality.value,
        output=output,
        total_duration_sec=shot_plan.total_duration_sec,
        total_frames=total_frames,
        renderer_hint=renderer_hint,
        shots=render_shots,
    )
