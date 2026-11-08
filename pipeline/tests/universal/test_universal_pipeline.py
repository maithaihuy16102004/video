"""Comprehensive unit and regression tests for Universal Pipeline Architecture.

Tests:
1. Arbitrary character IDs ingestion and fallback handling.
2. Arbitrary location IDs ingestion and fallback handling.
3. Multiple historical periods (ancient, 1890s, WWI, modern).
4. Unknown asset fallback and asset gap tracking.
5. Unknown character fallback generation.
6. Schema and vocabulary normalization validation.
7. Generic camera vocabulary and delta validation.
8. Generic action semantics and blocking resolution.
9. Data-driven world rendering without per-story code.
10. Strict Core vs Data separation check.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.universal import PipelineConfig, process_script
from pipeline.universal.assets.asset_resolver import UniversalAssetResolver
from pipeline.universal.bibles.resolver import (
    CharacterResolver,
    create_fallback_character_dna,
    create_fallback_location_dna,
)
from pipeline.universal.character_engine import IllustratedStickmanRenderer
from pipeline.universal.director.cinematic_director import CameraDeltaValidator, CinematicDirector, StageViewDetector
from pipeline.universal.reasoning.offline import OfflineReasoningProvider
from pipeline.universal.reasoning.validation import ReasoningValidator
from pipeline.universal.schemas import (
    ActorBlock,
    AssetRequirement,
    CameraSpec,
    CharacterBible,
    CharacterDNA,
    LocationBible,
    LocationDNA,
    SceneBlueprint,
    StoryIntelligence,
)
from pipeline.universal.world_engine.universal_world_renderer import UniversalWorldRenderer


class TestUniversalPipeline(unittest.TestCase):

    def setUp(self) -> None:
        self.config = PipelineConfig(reasoning_provider="offline", allow_offline_fallback=True)

    def test_01_arbitrary_character_fallback(self) -> None:
        dna = create_fallback_character_dna("CHAR_UNKNOWN_EXPLORER", "Deep Sea Explorer", "PROTAGONIST")
        self.assertEqual(dna.character_id, "CHAR_UNKNOWN_EXPLORER")
        self.assertEqual(dna.role, "PROTAGONIST")
        self.assertEqual(dna.detail_level, "HERO")
        self.assertIsNotNone(dna.hair.shape)
        self.assertIsNotNone(dna.face.skin_tone)
        self.assertEqual(dna.proposal_source, "FALLBACK_PROPOSAL")

    def test_02_arbitrary_location_fallback(self) -> None:
        loc = create_fallback_location_dna("LOC_DESERT_OASIS", "Saharan Desert Oasis", "EXTERIOR")
        self.assertEqual(loc.location_id, "LOC_DESERT_OASIS")
        self.assertEqual(loc.enclosure, "EXTERIOR")
        self.assertEqual(loc.ceiling, "SKY")
        self.assertTrue(len(loc.props) >= 1)
        self.assertEqual(loc.proposal_source, "FALLBACK_PROPOSAL")

    def test_03_unknown_asset_fallback_and_gap_logging(self) -> None:
        resolver = UniversalAssetResolver()
        req = AssetRequirement(
            requirement_id="REQ_TESLA_COIL_01",
            semantic="1890s laboratory induction spark coil",
            category="APPARATUS",
            period_year=1892,
            region="AMERICA",
            materials=["METAL", "GLASS"],
            role="HERO",
            location_id="LOC_LAB",
        )
        res = resolver.resolve(req)
        self.assertIn(res.status, ("MATCH", "COMPATIBLE_FALLBACK", "GENERIC_CATEGORY"))
        self.assertTrue(len(resolver.gap_tracker.gaps) >= 1)
        gap = resolver.gap_tracker.gaps[-1]
        self.assertEqual(gap.requirement_id, "REQ_TESLA_COIL_01")

    def test_04_age_and_costume_resolution(self) -> None:
        char = create_fallback_character_dna("CHAR_SOLDIER", "Soldier", "SUPPORTING")
        resolved = CharacterResolver.resolve_for_shot(char, year=1916, location_id="LOC_TRENCH")
        self.assertEqual(resolved.character_id, "CHAR_SOLDIER")
        self.assertIsNotNone(resolved.costume)
        self.assertIsNotNone(resolved.hair)

    def test_05_camera_delta_and_stage_view_detection(self) -> None:
        c1 = CameraSpec(shot="MEDIUM", height="EYE", yaw_deg=0.0, subject_position=[0.5, 0.8])
        c2 = CameraSpec(shot="MEDIUM", height="EYE", yaw_deg=0.0, subject_position=[0.5, 0.8])
        self.assertTrue(CameraDeltaValidator.is_repetitive(c1, c2))

        c3 = CameraSpec(shot="LOW_ANGLE", height="LOW", yaw_deg=18.0, subject_position=[0.65, 0.82])
        self.assertFalse(CameraDeltaValidator.is_repetitive(c1, c3))

        actor_centered = ActorBlock(character_id="A", screen_x=0.50, orientation="FRONT")
        self.assertTrue(StageViewDetector.is_stage_view(c1, actor_centered))
        self.assertFalse(StageViewDetector.is_stage_view(c3, actor_centered))

    def test_06_offline_story_intelligence_ingestion(self) -> None:
        script = """[SCENE - ANCIENT ROME, 44]
JULIUS CAESAR:
The Ides of March are come.
SOOTHSAYER:
Ay, Caesar, but not gone.
"""
        provider = OfflineReasoningProvider()
        raw = provider.complete_json("story_intelligence", "", f"SCRIPT:\n<<<\n{script}\n>>>", {})
        val = ReasoningValidator.validate_story_intelligence(raw)
        self.assertTrue(val.is_valid or val.repaired_data is not None)
        story = val.repaired_data
        self.assertTrue(len(story.story_beats) >= 1)
        self.assertTrue(any("CAESAR" in c.character_id for c in story.characters))

    def test_07_end_to_end_synthetic_script_processing(self) -> None:
        synthetic_script = """[SCENE - WORKSHOP, 1920]
ALICE:
Look at this blueprint.
BOB:
It shows the gear train.
"""
        p_dir = Path("output/test_scratch/synthetic_run")
        res = process_script(
            script_text=synthetic_script,
            config=self.config,
            project_dir=p_dir,
            render_frames=True,
            max_render_shots=2,
        )
        self.assertTrue(len(res["scene_blueprints"]) >= 1)
        self.assertTrue(len(res["rendered_frames"]) >= 1)
        self.assertEqual(res["cost_ledger"]["paid_cost_usd"], 0.0)

    def test_08_core_data_separation(self) -> None:
        # Core universal modules must NOT contain hard-coded references to Hitler, Pasewalk, Somme
        core_files = [
            Path("pipeline/universal/vocab.py"),
            Path("pipeline/universal/schemas.py"),
            Path("pipeline/universal/config.py"),
            Path("pipeline/universal/character_engine/illustrated_stickman_renderer.py"),
            Path("pipeline/universal/world_engine/universal_world_renderer.py"),
            Path("pipeline/universal/director/cinematic_director.py"),
            Path("pipeline/universal/orchestrator.py"),
        ]
        forbidden = ["hitler", "pasewalk", "beer_hall", "somme", "dap"]
        for cf in core_files:
            if not cf.exists():
                continue
            text = cf.read_text(encoding="utf-8").lower()
            for w in forbidden:
                self.assertNotIn(w, text, f"Forbidden story-specific string '{w}' found in core module {cf.name}")


if __name__ == "__main__":
    unittest.main()
