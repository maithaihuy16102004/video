"""Unit and integration tests for Director V2 pipeline."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ...director_v2.acting.action_to_pose import map_action_to_pose
from ...director_v2.config import ProjectConfig
from ...director_v2.orchestrator import DirectorV2Orchestrator
from ...director_v2.schemas.core import NormPoint
from ...director_v2.schemas.plan import BodyOrientation, CameraHeight, Shot, ShotPurpose, ShotType
from ...director_v2.validation.camera_delta import compute_shot_similarity
from ...director_v2.validation.replanner import replan_rejected_shot
from ...director_v2.validation.stage_view import is_stage_view


class TestDirectorV2(unittest.TestCase):
    def test_contrapposto_strictly_for_relaxed_stand(self):
        pose, _ = map_action_to_pose("march", "lính hành quân qua bùn lầy")
        self.assertNotEqual(pose, "POSE_RELAXED_STAND_CONTRAPPOSTO")

        pose, _ = map_action_to_pose("fall", "ngã gục xuống chiến hào")
        self.assertEqual(pose, "POSE_FALL_COLLAPSE")

        # Contrapposto allowed only when explicitly relaxed
        pose_relaxed, _ = map_action_to_pose("lounge", "đứng chờ thong thả", allow_contrapposto=True)
        self.assertEqual(pose_relaxed, "POSE_RELAXED_STAND_CONTRAPPOSTO")

    def test_stage_view_detection(self):
        staged = {
            "camera_height": "EYE_LEVEL",
            "camera_pitch": 0.0,
            "shot_type": "MEDIUM_WIDE",
            "subject_x": 0.50,
            "body_orientation": "FRONT",
            "foreground_occlusion": 0.0,
            "perspective_type": "FLAT",
        }
        self.assertTrue(is_stage_view(staged))

        cinematic = {
            "camera_height": "LOW",
            "camera_pitch": 18.0,
            "shot_type": "LOW_ANGLE",
            "subject_x": 0.32,
            "body_orientation": "THREE_QUARTER_BACK_LEFT",
            "foreground_occlusion": 0.25,
            "perspective_type": "THREE_POINT",
        }
        self.assertFalse(is_stage_view(cinematic))

    def test_camera_delta_similarity(self):
        s1 = {
            "shot_type": "CLOSE_UP",
            "camera_height": "EYE_LEVEL",
            "camera_yaw": 15.0,
            "camera_pitch": 4.0,
            "subject_x": 0.35,
            "subject_y": 0.90,
            "subject_scale": 1.2,
            "body_orientation": "THREE_QUARTER_FRONT_RIGHT",
            "pose_family": "POSE_SPEAK_GESTURE",
            "perspective_type": "TWO_POINT",
            "vanishing_point_primary": {"x": 0.70, "y": 0.45},
            "foreground_occlusion": 0.10,
            "key_light_direction": "UPPER_LEFT",
        }
        # Identical shot -> similarity ~= 1.0
        self.assertGreater(compute_shot_similarity(s1, s1), 0.95)

        # Drastically different shot -> similarity < 0.40
        s2 = {
            "shot_type": "EXTREME_WIDE",
            "camera_height": "HIGH",
            "camera_yaw": -45.0,
            "camera_pitch": -35.0,
            "subject_x": 0.70,
            "subject_y": 0.60,
            "subject_scale": 0.15,
            "body_orientation": "THREE_QUARTER_BACK_LEFT",
            "pose_family": "POSE_WALK_STRIDE",
            "perspective_type": "BIRD_EYE",
            "vanishing_point_primary": {"x": 0.20, "y": 0.80},
            "foreground_occlusion": 0.30,
            "key_light_direction": "UPPER_RIGHT",
        }
        self.assertLess(compute_shot_similarity(s1, s2), 0.40)

    def test_dry_run_pipeline_produces_all_10_files(self):
        fixture = Path(__file__).resolve().parent / "fixtures" / "episode_sample.txt"
        self.assertTrue(fixture.exists())
        script_text = fixture.read_text(encoding="utf-8")

        test_out = Path(__file__).resolve().parents[3] / "output" / "director_v2_test"
        cfg = ProjectConfig.for_aspect(aspect="16:9")

        orchestrator = DirectorV2Orchestrator(
            config=cfg,
            output_dir=test_out,
            offline=True,
            dry_run=True,
        )
        artifacts = orchestrator.run(script_text, project_id="test_run")

        expected_files = [
            "project_bible.json",
            "character_bible.json",
            "location_bible.json",
            "scene_plan.json",
            "shot_plan.json",
            "asset_manifest.json",
            "reuse_plan.json",
            "render_manifest.json",
            "validation_report.json",
            "estimated_api_cost.json",
        ]
        for f in expected_files:
            self.assertIn(f, artifacts)
            self.assertTrue(artifacts[f].exists())
            self.assertGreater(artifacts[f].stat().st_size, 0)

        # Check that dry-run generated 0 images
        assets_dir = test_out / "assets"
        if assets_dir.exists():
            pngs = list(assets_dir.glob("*.png"))
            self.assertEqual(len(pngs), 0)


if __name__ == "__main__":
    unittest.main()
