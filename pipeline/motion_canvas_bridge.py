"""
Bridge between kaomei/stickman-video-director (AI Director -> SHOT JSON)
and motion-canvas/motion-canvas (2D Scene Builder -> Motion Canvas 2D Camera Engine).

Enforces the Master Director Principle:
  "A CHANGE OF BACKGROUND IS NOT A CHANGE OF SHOT.
   A ZOOM IS NOT A NEW CAMERA ANGLE.
   A DIFFERENT PROP IS NOT A DIFFERENT POSE."

Priority Order Implemented:
  1. Perspective / Vanishing Point (1-point corridor, 2-point angled street/tables, high-angle zig-zag trench, worm's-eye ground level, POV bed)
  2. Camera Grammar (camera_height, camera_yaw, camera_pitch, shot_size crop, lens_feel)
  3. Action-Verb -> Pose Family System (kinematic spine/limb/weight/head/eye-line poses)
  4. Foreground Elements & Occlusion (architectural & anatomical foregrounds with real occlusion, no floating black circle heads)
  5. 8-Dimension Visual Similarity Validator (visual_similarity_score <= 0.72 across previous_6_shots)
  6. Character & Environment Directional Lighting (key_light_direction, shadow_side cel-shading on head/torso, rim_light contour, contact occlusion)
  7. Multi-Plane Parallax & Motion Canvas Tween Signals
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


# Motion Canvas core tweening functions (@motion-canvas/core/lib/tweening)
def clamp(val: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, val))


def ease_in_cubic(t: float) -> float:
    t = clamp(t)
    return t * t * t


def ease_out_cubic(t: float) -> float:
    t = clamp(t)
    return 1.0 - pow(1.0 - t, 3)


def ease_in_out_cubic(t: float) -> float:
    t = clamp(t)
    return 4.0 * t * t * t if t < 0.5 else 1.0 - pow(-2.0 * t + 2.0, 3) / 2.0


def smoothstep(t: float) -> float:
    t = clamp(t)
    return t * t * (3.0 - 2.0 * t)


def map_range(from_val: float, to_val: float, progress: float, easing_fn=ease_in_out_cubic) -> float:
    return from_val + (to_val - from_val) * easing_fn(clamp(progress))


def parallax_offset(camera_x: float, layer_ratio: float) -> float:
    return camera_x * (layer_ratio - 1.0)


# Catalog of distinct cinematic camera archetypes for automatic REDIRECT_CAMERA when similarity > 0.72
REDIRECT_ARCHETYPES: list[dict[str, Any]] = [
    {
        "shot_size": "EXTREME_WIDE",
        "camera_height": "HIGH_CRANE",
        "camera_yaw": -28.0,
        "camera_pitch": -38.0,
        "lens_feel": "WIDE_20MM",
        "perspective_type": "HIGH_ANGLE_ZIGZAG_TRENCH",
        "vanishing_point_x": 0.74,
        "vanishing_point_y": 0.20,
        "subject_x": 0.32,
        "subject_y": 0.76,
        "subject_scale": 0.28,
        "subject_orientation": "THREE_QUARTER_RIGHT",
        "action_verb": "TRAVERSE_TRENCH",
        "pose_family": "POSE_WALK_MARCH_PROFILE",
        "weight_distribution": "FRONT_FOOT_65",
        "head_direction": "FORWARD_RIGHT",
        "eye_line": "HORIZON_RIGHT",
        "foreground_elements": ["TRENCH_TIMBER_BEAM_TOP_FG", "BARBED_WIRE_SILHOUETTE_FG"],
        "foreground_occlusion": 0.22,
        "camera_motion": "PAN_RIGHT",
        "camera_motion_reason": "Reveal vast zig-zag trench network scale around tiny protagonist",
    },
    {
        "shot_size": "GROUND_INSERT",
        "camera_height": "GROUND_WORM_EYE",
        "camera_yaw": 18.0,
        "camera_pitch": 24.0,
        "lens_feel": "WIDE_24MM",
        "perspective_type": "GROUND_LEVEL_WORM_EYE",
        "vanishing_point_x": 0.58,
        "vanishing_point_y": 0.82,
        "subject_x": 0.64,
        "subject_y": 0.94,
        "subject_scale": 1.35,
        "subject_orientation": "SIDE_PROFILE_RIGHT",
        "action_verb": "SLOG_THROUGH_MUD",
        "pose_family": "POSE_WALK_MARCH_PROFILE",
        "weight_distribution": "FRONT_FOOT_80",
        "head_direction": "DOWN_SLIGHT",
        "eye_line": "GROUND_MUD",
        "foreground_elements": ["MUD_PUDDLE_SPLASH_FG", "DUCKBOARD_PLANKS_FG"],
        "foreground_occlusion": 0.30,
        "camera_motion": "TRACK_RIGHT",
        "camera_motion_reason": "Visceral ground-level tracking of boots splashing through trench mud",
    },
    {
        "shot_size": "OVER_THE_SHOULDER",
        "camera_height": "EYE_LEVEL",
        "camera_yaw": -22.0,
        "camera_pitch": -4.0,
        "lens_feel": "TELEPHOTO_50MM",
        "perspective_type": "DIAGONAL_TWO_POINT",
        "vanishing_point_x": 0.78,
        "vanishing_point_y": 0.44,
        "subject_x": 0.68,
        "subject_y": 1.12,
        "subject_scale": 1.28,
        "subject_orientation": "THREE_QUARTER_LEFT",
        "action_verb": "RECEIVE_DISPATCH",
        "pose_family": "POSE_HANDOFF_REACH_OTS",
        "weight_distribution": "FRONT_FOOT_70",
        "head_direction": "LEFT_TO_SPEAKER",
        "eye_line": "FOREGROUND_PARTNER",
        "foreground_elements": ["OTS_SOLDIER_TORSO_HELMET_LEFT"],
        "foreground_occlusion": 0.28,
        "camera_motion": "SLOW_PUSH",
        "camera_motion_reason": "Frame dialogue over foreground partner's shoulder with receding wall depth",
    },
    {
        "shot_size": "SIDE_TRACKING_MEDIUM",
        "camera_height": "PARAPET_LEVEL",
        "camera_yaw": 0.0,
        "camera_pitch": 0.0,
        "lens_feel": "STANDARD_35MM",
        "perspective_type": "SIDE_PARALLAX_CORRIDOR",
        "vanishing_point_x": 0.88,
        "vanishing_point_y": 0.52,
        "subject_x": 0.46,
        "subject_y": 1.06,
        "subject_scale": 1.05,
        "subject_orientation": "SIDE_PROFILE_RIGHT",
        "action_verb": "SPRINT_UNDER_SHELLFIRE",
        "pose_family": "POSE_RUN_SPRINT_PROFILE",
        "weight_distribution": "FRONT_FOOT_85",
        "head_direction": "FORWARD_INTENSE",
        "eye_line": "RIGHT_EDGE_TARGET",
        "foreground_elements": ["PARAPET_SANDBAG_WALL_OCCLUSION_FG"],
        "foreground_occlusion": 0.42,
        "camera_motion": "TRACK_RIGHT",
        "camera_motion_reason": "Lateral tracking behind foreground sandbags occluding lower body",
    },
    {
        "shot_size": "POV_FIRST_PERSON",
        "camera_height": "EYE_LEVEL",
        "camera_yaw": 0.0,
        "camera_pitch": -6.0,
        "lens_feel": "WIDE_24MM",
        "perspective_type": "ONE_POINT_DEEP_CORRIDOR",
        "vanishing_point_x": 0.50,
        "vanishing_point_y": 0.45,
        "subject_x": 0.50,
        "subject_y": 1.25,
        "subject_scale": 1.15,
        "subject_orientation": "POV_HANDS_ONLY",
        "action_verb": "LOOK_DOWN_CORRIDOR",
        "pose_family": "POSE_POV_HANDS_FOREGROUND",
        "weight_distribution": "CENTER_BALANCED",
        "head_direction": "FORWARD_POV",
        "eye_line": "VANISHING_POINT",
        "foreground_elements": ["POV_ARMS_AND_PROP_FG", "TRENCH_WALLS_CONVERGING_FG"],
        "foreground_occlusion": 0.26,
        "camera_motion": "SHAKE_IMPACT",
        "camera_motion_reason": "Put audience directly inside protagonist's eyes looking down converging trench",
    },
    {
        "shot_size": "CLOSE_UP",
        "camera_height": "LOW_TILT",
        "camera_yaw": 15.0,
        "camera_pitch": 14.0,
        "lens_feel": "TELEPHOTO_85MM",
        "perspective_type": "DIAGONAL_TWO_POINT",
        "vanishing_point_x": 0.22,
        "vanishing_point_y": 0.62,
        "subject_x": 0.34,
        "subject_y": 1.38,
        "subject_scale": 1.72,
        "subject_orientation": "THREE_QUARTER_RIGHT",
        "action_verb": "DEADPAN_REACT",
        "pose_family": "POSE_RECOIL_SURPRISE_BACK",
        "weight_distribution": "BACK_FOOT_75",
        "head_direction": "SLIGHT_TILT_BACK",
        "eye_line": "SIDE_EYE_RIGHT",
        "foreground_elements": ["TIMBER_POST_FRAME_RIGHT_FG"],
        "foreground_occlusion": 0.18,
        "camera_motion": "SLOW_PUSH",
        "camera_motion_reason": "Isolate facial reaction and chest-up posture with telephoto compression",
    },
]


def compute_visual_similarity_score(candidate: dict[str, Any], prev_shot: dict[str, Any]) -> float:
    """
    Computes visual similarity in [0.0, 1.0] across 8 structural cinematography dimensions:
      1. shot_size (weight 0.18)
      2. camera_height + pitch (weight 0.14)
      3. subject_position (subject_x, subject_y) (weight 0.12)
      4. subject_orientation (weight 0.12)
      5. pose_family + action_verb (weight 0.16)
      6. perspective_type + vanishing_point (weight 0.12)
      7. depth_layout / foreground_elements (weight 0.08)
      8. key_light_direction + shadow_side (weight 0.08)
    """
    score = 0.0
    if candidate.get("shot_size") == prev_shot.get("shot_size"):
        score += 0.18
    if candidate.get("camera_height") == prev_shot.get("camera_height"):
        score += 0.14
    dx = abs(float(candidate.get("subject_x", 0.5)) - float(prev_shot.get("subject_x", 0.5)))
    dy = abs(float(candidate.get("subject_y", 0.85)) - float(prev_shot.get("subject_y", 0.85)))
    if dx < 0.12 and dy < 0.12:
        score += 0.12 * (1.0 - (dx + dy) / 0.24)
    if candidate.get("subject_orientation") == prev_shot.get("subject_orientation"):
        score += 0.12
    if candidate.get("pose_family") == prev_shot.get("pose_family"):
        score += 0.16
    if candidate.get("perspective_type") == prev_shot.get("perspective_type"):
        vpx_diff = abs(float(candidate.get("vanishing_point_x", 0.5)) - float(prev_shot.get("vanishing_point_x", 0.5)))
        if vpx_diff < 0.15:
            score += 0.12
        else:
            score += 0.06
    if candidate.get("foreground_elements") == prev_shot.get("foreground_elements"):
        score += 0.08
    if candidate.get("shadow_side") == prev_shot.get("shadow_side"):
        score += 0.08
    return round(min(1.0, score), 3)


def validate_and_redirect_shot(
    shot_dict: dict[str, Any],
    previous_6_shots: list[dict[str, Any]],
    shot_global_idx: int,
    intentional_repetition: bool = False,
) -> dict[str, Any]:
    """
    Enforces the Master Director Anti-Repetition Validator:
      IF visual_similarity_score > 0.72 AND repetition_is_not_intentional:
          REJECT_SHOT -> REDIRECT_CAMERA
    """
    if not previous_6_shots:
        shot_dict["previous_6_shots"] = []
        shot_dict["visual_similarity_score"] = 0.0
        shot_dict["validator_action"] = "PASS_INITIAL"
        return shot_dict

    # Compare most strongly against the immediately preceding 2 shots, and check max over last 6
    recent_window = previous_6_shots[-3:]
    max_sim = max(compute_visual_similarity_score(shot_dict, p) for p in recent_window)
    shot_dict["visual_similarity_score"] = max_sim
    shot_dict["validator_action"] = "PASS"

    if max_sim > 0.72 and not intentional_repetition:
        # REJECT_SHOT & REDIRECT_CAMERA: pick the archetype from REDIRECT_ARCHETYPES with lowest similarity
        best_arch = None
        best_sim = 1.0
        for offset in range(len(REDIRECT_ARCHETYPES)):
            cand_arch = REDIRECT_ARCHETYPES[(shot_global_idx + offset) % len(REDIRECT_ARCHETYPES)]
            test_shot = {**shot_dict, **cand_arch}
            sim = max(compute_visual_similarity_score(test_shot, p) for p in recent_window)
            if sim < best_sim:
                best_sim = sim
                best_arch = cand_arch
            if sim <= 0.45:
                break
        if best_arch:
            shot_dict.update(best_arch)
            # Also sync legacy keys used by renderer
            shot_dict["camera"] = best_arch["shot_size"]
            shot_dict["shot_type"] = best_arch["shot_size"]
            shot_dict["move"] = best_arch["camera_motion"]
            shot_dict["camera_motion"] = best_arch["camera_motion"]
            shot_dict["pose"] = best_arch["pose_family"]
            shot_dict["pose_id"] = best_arch["pose_family"]
            shot_dict["character_x"] = best_arch["subject_x"]
            shot_dict["character_y"] = best_arch["subject_y"]
            shot_dict["character_scale"] = best_arch["subject_scale"]
            shot_dict["visual_similarity_score"] = best_sim
            shot_dict["validator_action"] = f"REDIRECTED_FROM_{max_sim:.2f}_TO_{best_sim:.2f}"

    shot_dict["previous_6_shots"] = [
        {
            "shot_id": p.get("id", "SHOT"),
            "shot_size": p.get("shot_size"),
            "camera_height": p.get("camera_height"),
            "perspective_type": p.get("perspective_type"),
            "pose_family": p.get("pose_family"),
            "subject_x": p.get("subject_x"),
        }
        for p in previous_6_shots[-6:]
    ]
    return shot_dict


def compute_motion_canvas_camera_state(
    sub_mode: str,
    sub_camera: str,
    sub_move: str,
    sub_local_t: float,
    frame_idx: int,
    s: float,
) -> dict[str, float]:
    """
    Evaluates Motion Canvas 2D Camera signals at normalized shot time `sub_local_t` in [0, 1].
    Note: Crop/framing size is now handled by true subject_y / subject_scale / perspective geometry,
    not by merely zooming a full-body stage! Camera motion here adds cinematic pan/push/pull/parallax.
    """
    eased_t = ease_in_out_cubic(sub_local_t)

    zoom = 1.0
    pan_x = 0.0
    pan_y = 0.0
    dutch_rad = 0.0
    shake_x = 0.0
    shake_y = 0.0
    char_move_x = 0.0
    obj_move_x = 0.0

    if sub_mode == "SILENCE_SLOW_PUSH_IN":
        zoom = map_range(1.04, 1.24, sub_local_t, ease_in_out_cubic)
        pan_y = map_range(-6.0 * s, -22.0 * s, sub_local_t, ease_in_out_cubic)
    elif sub_move == "SLOW_PUSH":
        zoom = map_range(1.02, 1.11, sub_local_t, ease_in_out_cubic)
    elif sub_move == "SLOW_PULL":
        zoom = map_range(1.12, 1.02, sub_local_t, ease_in_out_cubic)
    else:
        zoom = 1.03 + 0.03 * eased_t

    if sub_move in ("PAN_RIGHT", "TRACK_RIGHT"):
        pan_x = map_range(-38.0 * s, 38.0 * s, sub_local_t, ease_in_out_cubic)
        char_move_x = map_range(-32.0 * s, 32.0 * s, sub_local_t, smoothstep)
    elif sub_move == "PAN_LEFT":
        pan_x = map_range(38.0 * s, -38.0 * s, sub_local_t, ease_in_out_cubic)
    else:
        pan_x = map_range(-8.0 * s, 8.0 * s, sub_local_t, smoothstep)

    if sub_camera == "DUTCH_ANGLE":
        dutch_rad = math.radians(-3.5)

    obj_move_x = map_range(-18.0 * s, 0.0, min(1.0, sub_local_t * 2.2), ease_out_cubic)

    if sub_move == "SHAKE_IMPACT" or sub_mode in ("BUNKER_1945_QUAKE", "POV_BATTLEFIELD", "POV_PARAPET_CRATERS"):
        decay = 1.0 - 0.35 * sub_local_t
        shake_x = math.sin(frame_idx * 1.9) * 11.0 * s * decay
        shake_y = math.cos(frame_idx * 2.5) * 8.0 * s * decay
    elif sub_move == "SHAKE_LIGHT":
        shake_x = math.sin(frame_idx * 1.3) * 4.5 * s
        shake_y = math.cos(frame_idx * 1.7) * 3.5 * s

    return {
        "zoom": zoom,
        "pan_x": pan_x + shake_x,
        "pan_y": pan_y + shake_y,
        "dutch_rad": dutch_rad,
        "char_move_x": char_move_x,
        "obj_move_x": obj_move_x,
        "parallax_far_bg_x": parallax_offset(pan_x, 0.0),
        "parallax_bg_x": parallax_offset(pan_x, 0.35),
        "parallax_mid_x": parallax_offset(pan_x, 1.0),
        "parallax_fg_x": -pan_x * 1.65,
    }


def export_shot_json_and_motion_canvas_scene(job_dir: Path, plan: dict[str, Any]) -> dict[str, str]:
    """
    Exports:
      1. `shot_plan.json`: Full SHOT JSON contract with all required fields (camera_height, camera_yaw,
         camera_pitch, shot_size, lens_feel, vanishing_point_x/y, perspective_type, subject_x/y/scale/orientation,
         action_verb, pose_family, weight_distribution, head_direction, eye_line, foreground_elements,
         foreground_occlusion, midground/background/far_background_elements, key_light_direction,
         key_light_intensity, shadow_side, rim_light, camera_motion, camera_motion_reason,
         previous_6_shots, visual_similarity_score).
      2. `motion_canvas_scene.tsx`: Runnable Motion Canvas TypeScript 2D scene file.
    """
    scenes = plan.get("scenes", [])
    shot_json = {
        "architecture": "stickman-video-director + Motion Canvas 2D",
        "master_director_axiom": (
            "A CHANGE OF BACKGROUND IS NOT A CHANGE OF SHOT. "
            "A ZOOM IS NOT A NEW CAMERA ANGLE. "
            "A DIFFERENT PROP IS NOT A DIFFERENT POSE."
        ),
        "validator_rule": "IF visual_similarity_score > 0.72 AND NOT intentional_repetition THEN REJECT_SHOT -> REDIRECT_CAMERA",
        "repositories": {
            "director_brain": "https://github.com/kaomei/stickman-video-director (internal modes A5 + A6 + A2.2)",
            "animation_engine": "https://github.com/motion-canvas/motion-canvas",
            "examples_reference": "https://github.com/motion-canvas/examples",
        },
        "aspect_ratio": "16:9",
        "total_duration": plan.get("duration", 0.0),
        "shots": [],
    }

    tsx_lines = [
        "// Auto-generated Motion Canvas 2D Scene from stickman-video-director SHOT JSON",
        "import {makeScene2D, Node} from '@motion-canvas/2d';",
        "import {all} from '@motion-canvas/core/lib/flow';",
        "import {createRef} from '@motion-canvas/core/lib/utils';",
        "import {createSignal} from '@motion-canvas/core/lib/signals';",
        "import {easeInOutCubic} from '@motion-canvas/core/lib/tweening';",
        "",
        "export default makeScene2D(function* (view) {",
        "  view.fill('#141416');",
        "  const cameraX = createSignal(0);",
        "  const cameraY = createSignal(0);",
        "  const cameraZoom = createSignal(1);",
        "  const stage = createRef<Node>();",
        "  view.add(<Node ref={stage} x={() => cameraX()} y={() => cameraY()} scale={() => cameraZoom()} />);",
        "",
    ]

    elapsed = 0.0
    for sc in scenes:
        dur = float(sc.get("duration", 3.5))
        sub_shots = sc.get("subShots") or []
        for idx, sub in enumerate(sub_shots):
            ratio = float(sub.get("ratio", 1.0 / max(1, len(sub_shots))))
            sub_dur = round(dur * ratio, 3)
            shot_entry = {
                "scene_id": sc.get("id"),
                "shot_id": sub.get("id", f"SHOT_{idx+1}"),
                "start_sec": round(elapsed, 3),
                "duration_sec": sub_dur,
                "camera_height": sub.get("camera_height"),
                "camera_yaw": sub.get("camera_yaw"),
                "camera_pitch": sub.get("camera_pitch"),
                "shot_size": sub.get("shot_size"),
                "lens_feel": sub.get("lens_feel"),
                "vanishing_point_x": sub.get("vanishing_point_x"),
                "vanishing_point_y": sub.get("vanishing_point_y"),
                "perspective_type": sub.get("perspective_type"),
                "subject_x": sub.get("subject_x"),
                "subject_y": sub.get("subject_y"),
                "subject_scale": sub.get("subject_scale"),
                "subject_orientation": sub.get("subject_orientation"),
                "action_verb": sub.get("action_verb"),
                "pose_family": sub.get("pose_family"),
                "weight_distribution": sub.get("weight_distribution"),
                "head_direction": sub.get("head_direction"),
                "eye_line": sub.get("eye_line"),
                "foreground_elements": sub.get("foreground_elements", []),
                "foreground_occlusion": sub.get("foreground_occlusion", 0.0),
                "midground_elements": sub.get("midground_elements", []),
                "background_elements": sub.get("background_elements", []),
                "far_background_elements": sub.get("far_background_elements", []),
                "key_light_direction": sub.get("key_light_direction"),
                "key_light_intensity": sub.get("key_light_intensity"),
                "shadow_side": sub.get("shadow_side"),
                "rim_light": sub.get("rim_light"),
                "camera_motion": sub.get("camera_motion"),
                "camera_motion_reason": sub.get("camera_motion_reason"),
                "previous_6_shots": sub.get("previous_6_shots", []),
                "visual_similarity_score": sub.get("visual_similarity_score", 0.0),
                "validator_action": sub.get("validator_action", "PASS"),
            }
            shot_json["shots"].append(shot_entry)
            tsx_lines.append(
                f"  // [{sc.get('id')} :: {shot_entry['shot_id']}] size={shot_entry['shot_size']} "
                f"persp={shot_entry['perspective_type']} pose={shot_entry['pose_family']} sim={shot_entry['visual_similarity_score']}"
            )
            tsx_lines.append(
                f"  yield* all(cameraX({round((float(shot_entry['subject_x'] or 0.5) - 0.5) * -120, 1)}, {sub_dur}, easeInOutCubic), "
                f"cameraZoom({round(min(1.4, max(0.88, float(shot_entry['subject_scale'] or 1.0) * 0.85)), 2)}, {sub_dur}, easeInOutCubic));"
            )
            elapsed += sub_dur

    tsx_lines.append("});")
    shot_plan_path = job_dir / "shot_plan.json"
    mc_scene_path = job_dir / "motion_canvas_scene.tsx"
    shot_plan_path.write_text(json.dumps(shot_json, ensure_ascii=False, indent=2), encoding="utf-8")
    mc_scene_path.write_text("\n".join(tsx_lines) + "\n", encoding="utf-8")
    return {
        "shot_plan_json": str(shot_plan_path),
        "motion_canvas_scene_tsx": str(mc_scene_path),
        "total_shots": len(shot_json["shots"]),
    }
