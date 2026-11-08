"""Central pipeline orchestrator enforcing the immutable stage sequence.

Sequence:
  SCRIPT
  -> S01 SCRIPT ANALYZER
  -> S02 HISTORICAL / CONTINUITY ENGINE
  -> S03 ASSET BIBLES (Character / Location / Costume / Prop)
  -> S04 RETENTION DIRECTOR
  -> S05 SCENE DIRECTOR
  -> S06 SHOT PLANNER
  -> CAMERA DELTA & ANTI-REPETITION VALIDATION
  -> ASSET REUSE PLANNER
  -> ASSET RESOLUTION (Cache check)
  -> IMAGE GENERATION (Only missing assets, unless --dry-run)
  -> VISUAL CRITIC (Max 2 retries, logs fail reasons)
  -> RENDER MANIFEST BUILDER
  -> EXPORT 10 STANDARDIZED JSON ARTIFACTS
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .assets.cache import AssetCache
from .assets.requirements import extract_asset_requirements
from .assets.resolver import resolve_assets
from .assets.reuse_planner import plan_asset_reuse
from .config import ProjectConfig
from .cost.ledger import estimate_costs
from .critic.gemini_vision import GeminiVisionCritic
from .critic.visual_critic import VisualCritic
from .imaging.fake_image import FakeImageProvider
from .imaging.gemini_image import GeminiImageProvider
from .imaging.prompt_builder import build_image_prompt
from .imaging.provider import ImageProvider, ImageRequest
from .imaging.router import ImageRouter
from .llm.gemini_text import GeminiTextProvider
from .llm.heuristic_text import HeuristicTextProvider
from .llm.text_provider import TextProvider
from .logging_utils import RunLogger
from .render.manifest_builder import build_render_manifest
from .schemas.assets import AssetManifest, AssetStatus
from .schemas.bible import ProjectBible
from .schemas.manifest import RenderManifest
from .schemas.plan import ScenePlan, ShotPlan
from .schemas.reports import ValidationIssue, ValidationReport
from .stages.s01_script_analyzer import analyze_script
from .stages.s03_bibles import build_bibles
from .stages.s04_retention_director import plan_retention_segments
from .stages.s05_scene_director import direct_scenes
from .stages.s06_shot_planner import plan_shots
from .validation.camera_delta import compute_shot_similarity
from .validation.stage_view import check_stage_view_violations


class DirectorV2Orchestrator:
    def __init__(
        self,
        config: ProjectConfig,
        output_dir: Path,
        offline: bool = False,
        dry_run: bool = True,
        logger: RunLogger | None = None,
    ):
        self.config = config
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.dry_run = dry_run
        self.logger = logger or RunLogger(self.output_dir / "run_log.jsonl")

        self.cache = AssetCache(self.output_dir / "cache")
        self.router = ImageRouter(config)

        # Wire text provider
        if offline:
            self.text_provider: TextProvider = HeuristicTextProvider()
        else:
            try:
                self.text_provider = GeminiTextProvider(model=config.models.text_model)
            except Exception:
                self.text_provider = HeuristicTextProvider()

    def run(self, script_text: str, project_id: str = "episode_01") -> dict[str, Path]:
        self.logger.log("START", "Pipeline initiated", project=project_id, dry_run=self.dry_run, quality=self.config.quality.value)

        # 1. SCRIPT ANALYZER
        self.logger.log("S01_SCRIPT_ANALYZER", "Analyzing script into beats and entities")
        analysis = analyze_script(script_text, self.text_provider)

        # 2 & 3. CONTINUITY & BIBLES
        self.logger.log("S03_BIBLES", "Generating Project, Character and Location bibles")
        project_bible, characters, locations = build_bibles(analysis, project_id=project_id)

        # 4. RETENTION DIRECTOR
        self.logger.log("S04_RETENTION", "Partitioning narrative into retention segments")
        retention = plan_retention_segments(
            analysis,
            target_duration_sec=self.config.target_duration_sec,
            min_shot_sec=self.config.min_shot_sec,
            max_shot_sec=self.config.max_shot_sec,
        )

        # 5. SCENE DIRECTOR
        self.logger.log("S05_SCENE", "Directing continuous scenes")
        scene_plan = direct_scenes(analysis, retention, project_bible, locations)

        # 6. SHOT PLANNER
        self.logger.log("S06_SHOT_PLANNER", "Planning shots with 11-D camera delta and stage view guards")
        shot_plan = plan_shots(
            scene_plan,
            analysis,
            project_bible,
            locations,
            similarity_threshold=self.config.similarity_threshold,
            window_size=self.config.similarity_window,
        )

        # 7. ASSET REQUIREMENTS & REUSE PLANNING
        self.logger.log("ASSET_REUSE", "Extracting requirements and computing reuse ratio")
        manifest = extract_asset_requirements(shot_plan, project_bible, locations, quality_tier=self.config.quality.value)
        reuse_plan, shot_plan = plan_asset_reuse(shot_plan, manifest)
        self.logger.log("ASSET_REUSE", "Reuse ratio calculated", ratio=reuse_plan.reuse_ratio, unique_reqs=reuse_plan.unique_image_requirements)

        # 8. RESOLVE FROM CACHE
        manifest = resolve_assets(manifest, self.cache, self.config, dry_run=self.dry_run)

        # 9. GENERATE MISSING ASSETS (Unless dry-run or draft)
        critic = VisualCritic(provider=None if self.offline else GeminiVisionCritic(), max_retries=self.config.max_critic_retries)
        image_provider: ImageProvider = FakeImageProvider() if self.offline else GeminiImageProvider()

        if not self.dry_run and self.config.quality.value != "DRAFT":
            self.logger.log("IMAGE_GEN", "Executing image generation for missing assets")
            assets_dir = self.output_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)

            for a in manifest.assets:
                if a.status != AssetStatus.PLANNED:
                    continue
                req = next((r for r in manifest.requirements if r.requirement_id == a.requirement_id), None)
                if not req:
                    continue

                pos_prompt, neg_prompt = build_image_prompt(req, project_bible.style, project_bible)
                model_to_use = self.router.select_model(req.tier)
                dest = assets_dir / f"{req.requirement_id}.png"

                passed = False
                attempt_cnt = 0
                while attempt_cnt <= self.config.max_critic_retries and not passed:
                    attempt_cnt += 1
                    img_req = ImageRequest(
                        requirement_id=req.requirement_id,
                        prompt=pos_prompt,
                        negative_prompt=neg_prompt,
                        model=model_to_use,
                        aspect_ratio=req.aspect_ratio,
                        image_size=req.image_size,
                        output_path=dest,
                    )
                    res = image_provider.generate_image(img_req)
                    if not res.ok:
                        a.status = AssetStatus.ERROR
                        a.error = res.error
                        break

                    passed, critic_attempt = critic.evaluate_asset(dest, req, attempt_cnt, model_to_use)
                    a.attempts.append(critic_attempt)
                    if passed:
                        a.status = AssetStatus.GENERATED
                        a.path = str(dest)
                        self.cache.put(req.cache_key, dest.read_bytes())
                        break
                    else:
                        # Escalate model if in MASTER quality on retry
                        model_to_use = self.router.select_model(req.tier, retry_count=attempt_cnt)

                if not passed and a.status != AssetStatus.ERROR:
                    a.status = AssetStatus.FAILED_QC
                    a.path = str(dest)

        # 10. RENDER MANIFEST BUILDER
        self.logger.log("RENDER_MANIFEST", "Building final RenderManifest")
        render_manifest = build_render_manifest(shot_plan, manifest, self.config, project_id=project_id)

        # 11. VALIDATION REPORT
        self.logger.log("VALIDATION", "Computing final audit metrics")
        validation_issues: list[ValidationIssue] = []
        # Audit similarity across all shots
        for i in range(len(shot_plan.shots)):
            for j in range(max(0, i - self.config.similarity_window), i):
                sim = compute_shot_similarity(shot_plan.shots[i], shot_plan.shots[j])
                if sim > self.config.similarity_threshold and not shot_plan.shots[i].intentional_repetition:
                    validation_issues.append(ValidationIssue(
                        severity="WARN",
                        code="HIGH_SIMILARITY",
                        stage="SHOT_PLAN",
                        message=f"Shot {shot_plan.shots[i].shot_id} has {sim:.2f} similarity with {shot_plan.shots[j].shot_id}",
                        shot_id=shot_plan.shots[i].shot_id,
                    ))

        stage_violations = check_stage_view_violations(shot_plan.shots, window_size=self.config.stage_view_window, max_allowed=self.config.stage_view_max_in_window)
        for sv_idx in stage_violations:
            validation_issues.append(ValidationIssue(
                severity="WARN",
                code="EXCESSIVE_STAGE_VIEW",
                stage="SHOT_PLAN",
                message=f"Shot {shot_plan.shots[sv_idx].shot_id} violates stage-view frequency limits",
                shot_id=shot_plan.shots[sv_idx].shot_id,
            ))

        val_report = ValidationReport(
            passed=len([i for i in validation_issues if i.severity == "ERROR"]) == 0,
            issues=validation_issues,
            metrics={
                "total_shots": len(shot_plan.shots),
                "total_scenes": len(scene_plan.scenes),
                "total_duration_sec": shot_plan.total_duration_sec,
                "unique_requirements": len(manifest.requirements),
                "reuse_ratio": reuse_plan.reuse_ratio,
                "stage_view_count": sum(1 for s in shot_plan.shots if s.is_stage_view),
            },
        )

        # 12. COST ESTIMATE REPORT
        self.logger.log("COST_ESTIMATE", "Calculating estimated API costs")
        cost_report = estimate_costs(manifest, self.config, dry_run=self.dry_run)

        # 13. WRITE THE 10 CANONICAL ARTIFACT FILES
        out_files = {
            "project_bible.json": project_bible.to_json_dict(),
            "character_bible.json": {"characters": [c.to_json_dict() for c in characters]},
            "location_bible.json": {"locations": [l.to_json_dict() for l in locations]},
            "scene_plan.json": scene_plan.to_json_dict(),
            "shot_plan.json": shot_plan.to_json_dict(),
            "asset_manifest.json": manifest.to_json_dict(),
            "reuse_plan.json": reuse_plan.to_json_dict(),
            "render_manifest.json": render_manifest.to_json_dict(),
            "validation_report.json": val_report.to_json_dict(),
            "estimated_api_cost.json": cost_report.to_json_dict(),
        }

        created_paths: dict[str, Path] = {}
        for fname, data in out_files.items():
            fpath = self.output_dir / fname
            fpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            created_paths[fname] = fpath

        self.logger.log("COMPLETE", "Phase 1 run complete with all 10 canonical files", path=str(self.output_dir))
        return created_paths
