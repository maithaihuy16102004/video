"""Universal Pipeline Orchestrator.

Universal Entrypoint:
    process_script(script_text, config, project_dir)

Converts ANY input script into:
- STORY_INTELLIGENCE (Reasoning layer)
- CHARACTER_BIBLE (Data-driven CharacterDNA + variants)
- LOCATION_BIBLE (Data-driven LocationDNA + prop specs)
- VOICE_REGISTRY (Persistent speaker mapping)
- SCENE_BLUEPRINTS (Cinematic shots with camera, actors, props)
- ASSET_GAP_REPORT (Tracks exact vs fallback asset matches)
- RENDER_PLAN (Execution plan)
- ZERO_COST_LEDGER ($0.00 verified guarantee)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from .assets.asset_resolver import UniversalAssetResolver
from .bibles.resolver import VoiceRegistry
from .compositor.universal_compositor import UniversalCompositor
from .config import PipelineConfig
from .director.cinematic_director import CinematicDirector
from .ledger import CostLedger
from .reasoning.prompts import bible_prompt, repair_prompt, story_prompt
from .reasoning.provider import build_reasoner
from .reasoning.validation import ReasoningValidator
from .schemas import (
    BiblesProposal,
    CharacterBible,
    LocationBible,
    SceneBlueprint,
    StoryIntelligence,
)


class UniversalPipelineOrchestrator:
    """Master orchestrator executing the data-driven universal video pipeline."""

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.ledger = CostLedger()
        self.asset_resolver = UniversalAssetResolver()

    def process_script(
        self,
        script_text: str,
        project_dir: Path | str,
        render_frames: bool = True,
        max_render_shots: int = 5,
    ) -> dict[str, Any]:
        """Universal entrypoint: executes end-to-end planning and rendering for an arbitrary script."""
        t_start = time.time()
        p_dir = Path(project_dir)
        p_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = p_dir / "cache"

        # Canonical open-world pass: persistent entities/DNA before scene planning.
        from .story_intelligence import build_story_world_model
        story_world_model = build_story_world_model(script_text)
        (p_dir / "story_world_model.json").write_text(
            story_world_model.model_dump_json(indent=2), encoding="utf-8"
        )

        # 1. Reasoning Brain (Gemini Free text or deterministic offline fallback)
        reasoner = build_reasoner(self.config, cache_dir, self.ledger)

        # Stage 1: Script Intelligence
        s_prompt = story_prompt(script_text, self.config)
        raw_story = reasoner.complete_json("story_intelligence", "You are Script Intelligence.", s_prompt, {})
        val_story = ReasoningValidator.validate_story_intelligence(raw_story)

        if not val_story.is_valid and self.config.reasoning_max_repairs > 0:
            # Attempt repair
            rep_prompt = repair_prompt(s_prompt, val_story.issues)
            raw_story = reasoner.complete_json("story_intelligence", "You are Script Intelligence.", rep_prompt, {})
            val_story = ReasoningValidator.validate_story_intelligence(raw_story)

        story_intel: StoryIntelligence = val_story.repaired_data or StoryIntelligence(title="Fallback Story")

        # Stage 2: Character and Location Bibles
        b_prompt = bible_prompt(story_intel.dump(), self.config)
        raw_bibles = reasoner.complete_json("bibles", "You are Bible Designer.", b_prompt, {"story_intelligence": story_intel})
        val_bibles = ReasoningValidator.validate_bibles_proposal(raw_bibles, story_intel)

        bibles_prop: BiblesProposal = val_bibles.repaired_data or BiblesProposal()
        char_bible = CharacterBible(characters=bibles_prop.characters)
        loc_bible = LocationBible(locations=bibles_prop.locations)

        # Stage 3: Voice Registry
        voice_reg = VoiceRegistry()
        for c in char_bible.characters:
            voice_reg.register_character(c)

        # Stage 4: Cinematic Director & SceneBlueprints
        from .reasoning.visual_director import (
            DeterministicVisualDirectionProvider,
            GeminiVisualDirectionProvider,
        )
        if self.config.reasoning_provider == "gemini":
            v_provider = GeminiVisualDirectionProvider(
                model="gemini-3-flash-preview",
                cache_dir=cache_dir / "visual_direction",
            )
        else:
            v_provider = DeterministicVisualDirectionProvider()

        director = CinematicDirector(
            self.config,
            char_bible,
            loc_bible,
            self.asset_resolver,
            visual_provider=v_provider,
        )
        blueprints = director.direct_story(story_intel)

        # Stage 5: Asset Gap Tracking & Manifests
        gap_report_path = p_dir / "asset_gap_report.json"
        self.asset_resolver.gap_tracker.write_json(gap_report_path)

        # Stage 6: Optional Frame Rendering
        rendered_images: list[Path] = []
        if render_frames:
            compositor = UniversalCompositor(width=self.config.width, height=self.config.height)
            frames_dir = p_dir / "renders"
            frames_dir.mkdir(parents=True, exist_ok=True)

            for i, bp in enumerate(blueprints[:max_render_shots]):
                loc = loc_bible.get(bp.location_id) or loc_bible.locations[0]
                frame_path = frames_dir / f"shot_{i+1:03d}_{bp.shot_id}.png"
                t_render_start = time.time()
                compositor.render_blueprint(bp, loc, char_bible, output_path=frame_path)
                self.ledger.local_renders += 1
                self.ledger.render_seconds += (time.time() - t_render_start)
                rendered_images.append(frame_path)

        self.ledger.planning_seconds = time.time() - t_start
        self.ledger.assert_zero_cost()

        # Write all project manifests into project_dir
        (p_dir / "story_intelligence.json").write_text(json.dumps(story_intel.dump(), indent=2, ensure_ascii=False), encoding="utf-8")
        (p_dir / "character_bible.json").write_text(json.dumps(char_bible.dump(), indent=2, ensure_ascii=False), encoding="utf-8")
        (p_dir / "location_bible.json").write_text(json.dumps(loc_bible.dump(), indent=2, ensure_ascii=False), encoding="utf-8")
        (p_dir / "voice_bible.json").write_text(json.dumps(voice_reg.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        (p_dir / "scene_blueprints.json").write_text(json.dumps([bp.dump() for bp in blueprints], indent=2, ensure_ascii=False), encoding="utf-8")
        (p_dir / "zero_cost_ledger.json").write_text(json.dumps(self.ledger.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "project_dir": str(p_dir),
            "story_world_model": story_world_model,
            "story_intelligence": story_intel,
            "character_bible": char_bible,
            "location_bible": loc_bible,
            "scene_blueprints": blueprints,
            "rendered_frames": [str(p) for p in rendered_images],
            "cost_ledger": self.ledger.to_dict(),
        }


def process_first_person_story_first(
    script_text: str = "",
    output_dir: Path | str = "output/first_person_research_story_integration",
) -> dict[str, Any]:
    """Canonical First-Person Story-First x Research-Grounded Universal Entrypoint."""
    from .run_first_person_research_story_integration import MasterIntegrationGateOrchestrator
    runner = MasterIntegrationGateOrchestrator(output_dir=Path(output_dir))
    comp_res, voice_wav, speaker_map = runner.execute_voice_truth_and_script()
    facts = runner.execute_visual_research()
    world_model = runner.execute_story_world_and_beats(facts)
    shot_plan = runner.execute_scene_intelligence_and_shots(world_model, speaker_map)
    sfx_map = runner.execute_semantic_sfx(shot_plan, speaker_map)
    rendered_paths = runner.execute_static_visual_renderings(shot_plan, facts)
    test_report = runner.execute_quality_gates_and_tests()
    drive_report = runner.execute_drive_sync()
    return {
        "voice_wav": str(voice_wav),
        "world_model": world_model,
        "shot_plan": shot_plan,
        "rendered_paths": [str(p) for p in rendered_paths],
        "test_report": test_report,
        "drive_report": drive_report,
    }


def process_script(
    script_text: str,
    config: Optional[PipelineConfig] = None,
    project_dir: Path | str = "projects/default",
    render_frames: bool = True,
    max_render_shots: int = 5,
    mode: str = "default",
) -> dict[str, Any]:
    """Top-level functional entrypoint."""
    if mode == "first_person_story_first":
        return process_first_person_story_first(script_text, output_dir=project_dir)
    orch = UniversalPipelineOrchestrator(config=config)
    return orch.process_script(
        script_text=script_text,
        project_dir=project_dir,
        render_frames=render_frames,
        max_render_shots=max_render_shots,
    )
