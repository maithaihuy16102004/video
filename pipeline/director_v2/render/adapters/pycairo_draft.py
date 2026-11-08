"""PyCairo Fast Draft Adapter.

Translates RenderManifest into the `render-props.json` format expected by
`pipeline/fast_video_draft.py` for ultra-fast local previews without calling Image APIs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...schemas.core import LayerRole
from ...schemas.manifest import RenderManifest, RenderShot


class PyCairoDraftAdapter:
    def prepare_render_spec(self, manifest: RenderManifest, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        spec_path = output_dir / "render-props.json"

        # Group RenderShots into scenes
        scenes_map: dict[str, list[RenderShot]] = {}
        for shot in manifest.shots:
            scenes_map.setdefault(shot.scene_id, []).append(shot)

        cairo_scenes: list[dict[str, Any]] = []
        for s_idx, (sc_id, shots) in enumerate(scenes_map.items()):
            first_shot = shots[0]
            scene_frames = sum(s.frame_count for s in shots)
            scene_text = " ".join(c.text for s in shots for c in s.audio if c.kind == "narration")

            sub_shots: list[dict[str, Any]] = []
            for shot in shots:
                char_layer = next((l for l in shot.layers if l.role == LayerRole.CHARACTER), None)
                rig = char_layer.rigs[0] if (char_layer and char_layer.rigs) else None

                sub_shots.append({
                    "id": shot.shot_id,
                    "ratio": shot.frame_count / max(1, scene_frames),
                    "camera_height": shot.camera_height,
                    "camera_pitch": shot.camera_pitch,
                    "camera_yaw": shot.camera_yaw,
                    "horizon_y": shot.horizon_y,
                    "lens_feel": shot.lens_feel,
                    "depth_axis": shot.depth_axis,
                    "shot_size": shot.shot_type,
                    "camera": shot.shot_type,
                    "move": shot.camera.motion,
                    "camera_motion": shot.camera.motion,
                    "perspective_type": shot.perspective_type,
                    "vanishing_point_x": shot.vanishing_point_primary.get("x", 0.5),
                    "vanishing_point_y": shot.vanishing_point_primary.get("y", 0.5),
                    "vanishing_point_secondary": shot.vanishing_point_secondary,
                    "subject_x": rig.x if rig else 0.5,
                    "subject_y": rig.y if rig else 0.85,
                    "subject_scale": rig.scale if rig else 0.6,
                    "character_x": rig.x if rig else 0.5,
                    "character_y": rig.y if rig else 0.85,
                    "character_scale": rig.scale if rig else 0.6,
                    "body_orientation": rig.orientation if rig else "THREE_QUARTER_FRONT_RIGHT",
                    "pose": rig.pose_family if rig else "POSE_ALERT_STAND",
                    "pose_id": rig.pose_family if rig else "POSE_ALERT_STAND",
                    "action_verb": rig.action_verb if rig else "stand",
                })

            cairo_scenes.append({
                "id": sc_id,
                "text": scene_text,
                "location": first_shot.location_id.lower().replace("_", "-"),
                "year": str(first_shot.year or "1914"),
                "durationFrames": scene_frames,
                "camera": first_shot.shot_type,
                "subShots": sub_shots,
                "character": "protagonist",
                "characterPosition": "LEFT_THIRD" if s_idx % 2 == 0 else "RIGHT_THIRD",
                "pose": sub_shots[0]["pose"] if sub_shots else "POSE_ALERT_STAND",
            })

        spec_data = {
            "aspectRatio": manifest.output.aspect_ratio,
            "width": manifest.output.width,
            "height": manifest.output.height,
            "fps": manifest.output.fps,
            "totalFrames": manifest.total_frames,
            "scenes": cairo_scenes,
        }
        spec_path.write_text(json.dumps(spec_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return spec_path
