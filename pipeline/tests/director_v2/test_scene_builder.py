"""Unit tests for Gemini Context-Aware Scene Builder architecture."""
import json
import unittest
from pathlib import Path

from pipeline.director_v2.scene_builder.blueprint import SceneBlueprint
from pipeline.director_v2.scene_builder.director_designer import DirectorDesigner
from pipeline.director_v2.scene_builder.prompt_synthesizer import PromptSynthesizer
from pipeline.director_v2.scene_builder.asset_resolver import AssetResolver, LocationMaster
from pipeline.director_v2.scene_builder.visual_critic import VisualCritic
from pipeline.director_v2.scene_builder.ab_evaluator import ABEvaluator


class TestSceneBuilder(unittest.TestCase):
    def setUp(self):
        self.director = DirectorDesigner()
        self.synthesizer = PromptSynthesizer()
        self.critic = VisualCritic(max_retry=2)
        self.evaluator = ABEvaluator()

    def test_director_creates_10_diverse_blueprints(self):
        blueprints = self.director.create_10_shot_prototype_blueprints()
        self.assertEqual(len(blueprints), 10)

        shot_sizes = {bp.camera.shot_size for bp in blueprints}
        expected_sizes = {
            "EXTREME_WIDE", "WIDE", "MEDIUM", "CLOSE", "LOW_ANGLE",
            "HIGH_ANGLE", "GROUND_LEVEL", "OTS", "POV", "DEEP_PERSPECTIVE"
        }
        self.assertTrue(expected_sizes.issubset(shot_sizes))

        locations = {bp.history.location_id for bp in blueprints}
        self.assertGreaterEqual(len(locations), 3)

    def test_prompt_synthesizer_contract(self):
        bp = self.director.create_10_shot_prototype_blueprints()[0]
        pos_prompt, neg_prompt = self.synthesizer.build_prompt_package(bp)

        self.assertIn("[LOCKED] CAMERA & PERSPECTIVE SYSTEM", pos_prompt)
        self.assertIn("[LOCKED] CHARACTER RESERVED ZONE", pos_prompt)
        self.assertIn("[GUIDED] 4-TIER DEPTH ARCHITECTURE", pos_prompt)
        self.assertIn("[FREE] TEXTURE & MICRO-SURFACE FREEDOM", pos_prompt)
        self.assertIn("RESERVED BOUNDING BOX", pos_prompt)

        # Ensure stickman and protagonist are forbidden in plate prompt
        self.assertIn("stickman", neg_prompt)
        self.assertIn("human protagonist", neg_prompt)

    def test_asset_resolver_cascade(self):
        cache_dir = Path("output/test_cache")
        resolver = AssetResolver(cache_dir=cache_dir)
        blueprints = self.director.create_10_shot_prototype_blueprints()

        for bp in blueprints:
            decision = resolver.resolve_blueprint(bp)
            if decision.action == "GENERATE_NEW_MASTER" and decision.source_master_id:
                resolver.register_master(
                    LocationMaster(
                        master_id=decision.source_master_id,
                        location_id=bp.history.location_id,
                        name=bp.history.location_id,
                        plate_path=Path("dummy.png"),
                        camera_height=bp.camera.height,
                        camera_yaw=bp.camera.yaw,
                        camera_pitch=bp.camera.pitch,
                        horizon_y=bp.camera.horizon_y,
                        perspective_type=bp.perspective.type,
                    )
                )

        reused = sum(1 for d in resolver.decisions if "REUSE" in d.action)
        self.assertGreaterEqual(reused, 2, "Asset reuse should achieve at least 2 reused/reframed assets")

    def test_visual_critic_feedback_loop(self):
        bp = self.director.create_10_shot_prototype_blueprints()[4]  # S05_SH05_LOW_ANGLE
        ev_fail = self.critic.inspect_artwork(bp, Path("dummy.png"), retry_count=0, simulate_first_pass_error=True)
        self.assertFalse(ev_fail.passed)
        self.assertGreater(len(ev_fail.issues), 0)
        self.assertIn("problem", ev_fail.issues[0])
        self.assertIn("fix", ev_fail.issues[0])

        correction_prompt = self.synthesizer.build_critic_correction_prompt(bp, "base prompt", ev_fail.issues)
        self.assertIn("VISUAL CRITIC QC CORRECTION ORDER", correction_prompt)

        ev_pass = self.critic.inspect_artwork(bp, Path("dummy.png"), retry_count=1, simulate_first_pass_error=False)
        self.assertTrue(ev_pass.passed)
        self.assertEqual(ev_pass.verdict, "ACCEPTED_AFTER_RETRY")

    def test_ab_evaluation(self):
        bp = self.director.create_10_shot_prototype_blueprints()[0]
        comp = self.evaluator.evaluate_shot(bp)
        self.assertEqual(comp.winner, "GEMINI_SCENE_BUILDER")
        self.assertGreater(comp.gemini_overall, comp.pycairo_overall)


if __name__ == "__main__":
    unittest.main()
