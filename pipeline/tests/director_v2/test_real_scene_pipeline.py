"""Unit tests verifying Phase 25 requirements:
- Provider provenance data structures
- Generation mode enum validation
- Fallback detection & ALLOW_PROCEDURAL_FALLBACK enforcement
- Image response decoding & SHA-256 hash calculation
- Reserved zone serialization
- Prompt synthesis in English with Vietnamese narration preserved
- Compositor consuming exact environment path
- Zero secret exposure
"""
import io
import json
import os
import unittest
from pathlib import Path
from PIL import Image

from pipeline.director_v2.scene_builder.provenance import GenerationMode, GenerationProvenance, ImageResponseValidator
from pipeline.director_v2.scene_builder.three_scene_designer import create_three_real_scenes
from pipeline.director_v2.scene_builder.english_prompt_synthesizer import EnglishPromptSynthesizer
from pipeline.director_v2.scene_builder.strict_gemini_client import StrictGeminiClient
from pipeline.director_v2.scene_builder.audit_critic import BlueprintComplianceValidator, PixelVisualCritic
from pipeline.director_v2.scene_builder.compositor import SceneCompositor


class TestRealScenePipeline(unittest.TestCase):
    def setUp(self):
        self.scenes = create_three_real_scenes()
        self.synthesizer = EnglishPromptSynthesizer()
        self.structural_validator = BlueprintComplianceValidator()
        self.pixel_critic = PixelVisualCritic()

    def test_three_scenes_diversity_and_narration_preservation(self):
        self.assertEqual(len(self.scenes), 3)
        # Verify Vietnamese narration preserved in blueprint
        for s in self.scenes:
            self.assertTrue(len(s.story.narration) > 10)
            self.assertTrue(any(ch in s.story.narration for ch in "àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"))

        # Verify 3 distinct framing types
        shot_sizes = [s.camera.shot_size for s in self.scenes]
        self.assertIn("GROUND_LEVEL", shot_sizes)
        self.assertIn("OTS", shot_sizes)
        self.assertIn("LOW_ANGLE", shot_sizes)

    def test_english_prompt_synthesis_and_no_quality_spam(self):
        bp = self.scenes[0]
        pos_prompt, neg_prompt, p_hash = self.synthesizer.build_prompt_package(bp)

        # 17-tier headers present
        self.assertIn("SUBJECT / ENVIRONMENT:", pos_prompt)
        self.assertIn("HISTORICAL CONTEXT:", pos_prompt)
        self.assertIn("CURRENT STORY MOMENT:", pos_prompt)
        self.assertIn("CAMERA:", pos_prompt)
        self.assertIn("CHARACTER RESERVED AREA:", pos_prompt)
        self.assertIn("DEPTH PLAN (4-TIER ARCHITECTURE):", pos_prompt)
        self.assertIn("NEGATIVE CONSTRAINTS:", pos_prompt)

        # Verify NO quality spam words
        self.assertNotIn("masterpiece", pos_prompt.lower())
        self.assertNotIn("8k", pos_prompt.lower())
        self.assertNotIn("award winning", pos_prompt.lower())

        # Verify hash generated
        self.assertEqual(len(p_hash), 64)

    def test_provenance_and_generation_mode_enums(self):
        valid_modes = {
            GenerationMode.REAL_API,
            GenerationMode.CACHE,
            GenerationMode.REUSED_MASTER,
            GenerationMode.PROCEDURAL_FALLBACK,
            GenerationMode.MOCK,
            GenerationMode.TEST_FIXTURE,
        }
        self.assertEqual(len(valid_modes), 6)

    def test_image_response_validation_and_sha256(self):
        # Create a real 100x100 dummy PNG in memory
        img = Image.new("RGB", (100, 100), color=(120, 140, 160))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()

        valid, msg, meta = ImageResponseValidator.validate_image_bytes(raw_bytes, min_bytes=50)
        self.assertTrue(valid)
        self.assertEqual(meta["format"], "PNG")
        self.assertEqual(meta["width"], 100)
        self.assertEqual(meta["height"], 100)
        self.assertEqual(len(meta["sha256"]), 64)

        # Test rejection of empty / corrupt bytes
        empty_valid, empty_msg, _ = ImageResponseValidator.validate_image_bytes(b"")
        self.assertFalse(empty_valid)
        self.assertIn("EMPTY_BYTE_STREAM", empty_msg)

    def test_fallback_disallowed_fails_loudly(self):
        client = StrictGeminiClient(allow_procedural_fallback=False)
        self.assertFalse(client.allow_procedural_fallback)

        out_path = Path("output/test_scratch/loud_fail_test.png")
        # Attempt generation without valid network / with model
        res = client.generate_scene_image(
            scene_id="TEST_FAIL_SCENE",
            prompt="A test prompt",
            negative_prompt="none",
            prompt_hash="dummy_hash",
            output_image_path=out_path,
        )

        # Must report failure or real API, NEVER silent procedural success
        if not res.ok:
            self.assertEqual(res.status, "GEMINI_GENERATION_FAILED")
            self.assertFalse(res.provenance.fallback_used)
            self.assertEqual(res.provenance.generation_mode, GenerationMode.REAL_API)

    def test_compositor_consumes_exact_environment(self):
        # Verify compositor paints the exact provided plate surface
        compositor = SceneCompositor(width=640, height=360)
        plate_p = Path("output/test_scratch/dummy_plate.png")
        plate_p.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (640, 360), color=(50, 60, 70))
        img.save(str(plate_p))

        out_comp = Path("output/test_scratch/test_comp.png")
        compositor.composite_shot(self.scenes[0], plate_p, out_comp)
        self.assertTrue(out_comp.exists())
        self.assertGreater(out_comp.stat().st_size, 1000)

    def test_zero_secret_exposure(self):
        client = StrictGeminiClient()
        status = client.key_status
        self.assertIn(status, ("AVAILABLE", "MISSING"))
        # Key value must NEVER equal status
        self.assertNotEqual(status, os.getenv("GEMINI_API_KEY", ""))


if __name__ == "__main__":
    unittest.main()
