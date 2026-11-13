"""Error propagation (integration sprint section 6).

A compiler failure must fail the job with a structured record --
never fall back to legacy cues and render on. Vocabulary gaps
(unsupported sentences with no verb mapping) are classified and
reported, not exceptions: see production_errors for the design
decision and the pending decision recorded for Mai.
"""

import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from ai_clip_studio import preflight as preflight_mod
from ai_clip_studio import product_flow
from ai_clip_studio.action_compiler import (
    UnauthorizedStoryChange, compile_actions)
from ai_clip_studio.map_renderer import (
    MapSpecError, MissingHistoricalMapData)
from ai_clip_studio.map_registry import RegistryError
from ai_clip_studio.preflight import semantic_preflight_checks
from ai_clip_studio.production_errors import (
    ACTOR_RESOLUTION_FAILED, COMPILER_EXCEPTION,
    GRAPH_VALIDATION_FAILED, HISTORICAL_DATASET_UNAVAILABLE,
    MANDATORY_PROP_UNSUPPORTED, MAP_SPEC_ERROR,
    PROP_STATE_CONTRADICTION,
    ProductionError, STAGE_EXCEPTION, STORY_CONFLICT,
    TIMELINE_CONFLICT, check_compile_outcome, classify_unsupported,
    wrap_exception)
from ai_clip_studio.prop_system import (
    ForbiddenPropTransition, UnsupportedPropError)
from ai_clip_studio.scene_graph import GraphValidationError
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.unified_timeline import SchedulingConflict

AGENT = Path(__file__).resolve().parent.parent.parent

# The ten sprint-section-6 fields every structured record carries.
TEN_FIELDS = {
    "error_code", "stage", "source_scene_id", "source_shot_id",
    "source_directive_id", "affected_entity", "severity",
    "recoverability", "diagnostic_message", "suggested_resolution",
}


def _package(name, subdir="examples"):
    doc = parse_studio_script_v1(
        (AGENT / subdir / f"{name}.studio.md").read_text(
            encoding="utf-8"))
    return adapt_document(doc)


def _compile(name, subdir="examples"):
    pkg = _package(name, subdir)
    events, unsupported = compile_actions(pkg)
    return pkg, events, unsupported


class TestClassifyUnsupported(unittest.TestCase):
    def test_zeus_counts(self):
        # Measured 2026-11-13: 94 unsupported = 58 vocabulary gaps
        # + 5 constraints + 28 routed + 3 staged expressions.
        _pkg, _events, unsupported = _compile(
            "zeus_ep01_fall_of_cronus")
        result = classify_unsupported(
            unsupported, _package("zeus_ep01_fall_of_cronus"))
        self.assertEqual(result["counts"], {
            "VOCABULARY_GAP": 58, "CONSTRAINT": 5, "ROUTED": 28,
            "EXPRESSION_STAGED": 3})
        self.assertEqual(len(result["entries"]), 94)
        self.assertTrue(result["warnings"])

    def test_zeus_constraint_and_expression_spots(self):
        pkg, _events, unsupported = _compile(
            "zeus_ep01_fall_of_cronus")
        result = classify_unsupported(unsupported, pkg)
        by_class = {}
        for entry in result["entries"]:
            by_class.setdefault(entry["handling_class"], []).append(
                entry)
        constraints = [e["directive_text"]
                       for e in by_class["CONSTRAINT"]]
        self.assertTrue(any("Match cut" in t for t in constraints))
        self.assertTrue(any(t.strip().startswith("Không")
                            for t in constraints))
        # The 3 staged expressions are smile sentences whose shots
        # carry expression records.
        for entry in by_class["EXPRESSION_STAGED"]:
            self.assertIn("cười", entry["directive_text"].lower())

    def test_ep1_all_routed(self):
        pkg, _events, unsupported = _compile(
            "hitler_ep01_munich_1914")
        result = classify_unsupported(unsupported, pkg)
        self.assertEqual(result["counts"], {"ROUTED": 19})
        self.assertEqual(result["warnings"], [])

    def test_no_actor_class(self):
        entry = {"action_id": "SC01_SH01_ACT01", "category": "NO_ACTOR",
                 "directive_text": "Đưa cốc cho Cronus",
                 "source_scene_id": "SC01",
                 "source_shot_id": "SC01_SH01",
                 "source_directive_id": "SC01_SH01_D1"}
        result = classify_unsupported([entry])
        self.assertEqual(result["entries"][0]["handling_class"],
                         "NO_ACTOR")
        self.assertIn("error", result["entries"][0]["handling"])

    def test_expression_unverified_without_package(self):
        entry = {"action_id": "SC01_SH01_ACT01", "category": "UNCLEAR",
                 "directive_text": "Bà Tư mỉm cười.",
                 "source_scene_id": "SC01",
                 "source_shot_id": "SC01_SH01",
                 "source_directive_id": "SC01_SH01_D1"}
        result = classify_unsupported([entry])
        self.assertEqual(result["entries"][0]["handling_class"],
                         "EXPRESSION_UNVERIFIED")

    def test_every_entry_gets_a_handling(self):
        _pkg, _events, unsupported = _compile(
            "zeus_ep01_fall_of_cronus")
        result = classify_unsupported(unsupported)
        for entry in result["entries"]:
            self.assertIn("handling_class", entry)
            self.assertTrue(entry["handling"])


class TestCheckCompileOutcome(unittest.TestCase):
    def test_raises_on_no_actor_with_all_ten_fields(self):
        entry = {"action_id": "SC06_SH01_ACT03", "category": "NO_ACTOR",
                 "directive_text": "Đưa cốc cho Cronus",
                 "source_scene_id": "SC06",
                 "source_shot_id": "SC06_SH01",
                 "source_directive_id": "SC06_SH01_D3"}
        with self.assertRaises(ProductionError) as caught:
            check_compile_outcome([], [entry], stage="action_compile")
        record = caught.exception.to_dict()
        self.assertTrue(TEN_FIELDS <= set(record),
                        set(record) ^ TEN_FIELDS)
        self.assertEqual(record["error_code"],
                         ACTOR_RESOLUTION_FAILED)
        self.assertEqual(record["stage"], "action_compile")
        self.assertEqual(record["source_scene_id"], "SC06")
        self.assertEqual(record["source_shot_id"], "SC06_SH01")
        self.assertEqual(record["source_directive_id"], "SC06_SH01_D3")
        self.assertEqual(record["affected_entity"], "SC06_SH01_ACT03")
        self.assertEqual(record["severity"], "fatal")
        self.assertTrue(record["diagnostic_message"])
        self.assertTrue(record["suggested_resolution"])

    def test_real_scripts_do_not_raise(self):
        for name in ("hitler_ep01_munich_1914",
                     "zeus_ep01_fall_of_cronus"):
            pkg, events, unsupported = _compile(name)
            result = check_compile_outcome(
                events, unsupported, stage="action_compile",
                package=pkg)
            self.assertIn("counts", result)


class TestWrapException(unittest.TestCase):
    def test_real_exception_instances_map_to_codes(self):
        cases = [
            (UnauthorizedStoryChange("conflict"), STORY_CONFLICT),
            (GraphValidationError("broken"), GRAPH_VALIDATION_FAILED),
            (ForbiddenPropTransition("bad move"),
             PROP_STATE_CONTRADICTION),
            (MissingHistoricalMapData("no data"),
             HISTORICAL_DATASET_UNAVAILABLE),
            (RegistryError("bad checksum"),
             HISTORICAL_DATASET_UNAVAILABLE),
            (MapSpecError("bad spec"), MAP_SPEC_ERROR),
            (UnsupportedPropError("telescope"),
             MANDATORY_PROP_UNSUPPORTED),
            (SchedulingConflict("overlap"), TIMELINE_CONFLICT),
            (ValueError("boom"), STAGE_EXCEPTION),
            (RuntimeError("boom"), STAGE_EXCEPTION),
        ]
        for exc, code in cases:
            record = wrap_exception(exc, stage="action_compile")
            self.assertEqual(record.error_code, code, type(exc))
            self.assertEqual(record.stage, "action_compile")
            self.assertEqual(record.cause_type, type(exc).__name__)
            self.assertIn(str(exc), record.diagnostic_message)
            self.assertTrue(record.suggested_resolution)
            self.assertTrue(TEN_FIELDS <= set(record.to_dict()))

    def test_explicit_code_override(self):
        record = wrap_exception(ValueError("boom"),
                                stage="semantic_conflicts",
                                error_code=COMPILER_EXCEPTION)
        self.assertEqual(record.error_code, COMPILER_EXCEPTION)


class TestPreflightActorResolution(unittest.TestCase):
    def test_no_actor_fails_preflight(self):
        pkg = _package("hitler_ep01_munich_1914")
        events, unsupported = compile_actions(pkg)
        injected = {"action_id": "SC01_SH01_ACT99",
                    "category": "NO_ACTOR",
                    "directive_text": "Đưa cốc cho Cronus",
                    "source_scene_id": "SC01",
                    "source_shot_id": "SC01_SH01",
                    "source_directive_id": "SC01_SH01_D9"}
        with mock.patch.object(
                preflight_mod, "compile_actions",
                return_value=(events, [*unsupported, injected])):
            checks = semantic_preflight_checks(pkg)
        by_name = {c.name: c for c in checks}
        self.assertIn("actor_resolution", by_name)
        check = by_name["actor_resolution"]
        self.assertFalse(check.passed)
        self.assertIn(ACTOR_RESOLUTION_FAILED, check.detail)
        self.assertIn("SC01_SH01_ACT99", check.detail)


def _stub_tts(flat_lines, job_dir, voice_hints=None, voice_ids=None):
    """1s sine WAVs + the manifest stage 6 reads. No real synthesis:
    these tests exercise failure propagation, not TTS."""
    job_dir = Path(job_dir)
    wavs = []
    for i, _line in enumerate(flat_lines):
        path = job_dir / f"line_{i + 1:02d}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            frames = b"".join(
                struct.pack("<h", int(12000 * math.sin(
                    2 * math.pi * 440 * n / 48000)))
                for n in range(48000))
            wav.writeframes(frames)
        wavs.append(path)
    (job_dir / "voices_manifest.json").write_text(json.dumps({
        "distinct_voices_used": 1,
        "speakers": sorted({line["speaker"] for line in flat_lines}),
    }), encoding="utf-8")
    return wavs


GARDEN = (AGENT / "ai_clip_studio" / "tests" / "fixtures"
          / "unseen_garden_key.studio.md").read_text(encoding="utf-8")


class TestEndToEndPropagation(unittest.TestCase):
    def _run(self, compile_side_effect, extra_patches=()):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            patches = [
                mock.patch.object(product_flow, "tts_cli_provider",
                                  side_effect=_stub_tts),
                mock.patch.object(product_flow, "compile_actions",
                                  side_effect=compile_side_effect),
                *extra_patches,
            ]
            for p in patches:
                p.start()
            try:
                job = product_flow.run_product_job(
                    GARDEN, job_dir, upload=False)
            finally:
                for p in patches:
                    p.stop()
            # Read job-dir artifacts BEFORE the temp dir is removed.
            artifacts = {}
            for name in ("production_error.json",
                         "action_events.json", "renderer_info.json"):
                path = job_dir / name
                artifacts[name] = json.loads(path.read_text(
                    encoding="utf-8")) if path.exists() else None
            artifacts["draft_exists"] = (job_dir / "draft.mp4").exists()
            artifacts["frames_exist"] = (job_dir / "frames").exists()
            return job, artifacts

    def test_stage_2b_raise_fails_job_before_tts(self):
        # The propagation is the code under test; the compiler is a
        # dependency, so a staged raise stands in for its failure.
        job, artifacts = self._run(ValueError("boom-2b"))
        self.assertEqual(job.status, "FAILED")
        self.assertIn("ValueError: boom-2b", job.errors[0])
        stages = {s["stage"]: s for s in job.stages}
        self.assertEqual(stages["semantic_conflicts"]["status"],
                         "failed")
        self.assertNotIn("vietnamese_tts", stages)
        self.assertFalse(artifacts["draft_exists"])
        self.assertFalse(artifacts["frames_exist"])
        prod_err = artifacts["production_error.json"]
        self.assertIsNotNone(prod_err)
        self.assertEqual(prod_err["stage"], "semantic_conflicts")
        self.assertEqual(prod_err["error_code"], STAGE_EXCEPTION)
        self.assertTrue(TEN_FIELDS <= set(prod_err))

    def test_stage_7a_raise_fails_job_after_record(self):
        # Early pass clean, real-span compile raises: the record is
        # written, then the job fails -- no render follows.
        job, artifacts = self._run(
            [([], []), ValueError("boom-7a")])
        self.assertEqual(job.status, "FAILED")
        self.assertIn("ValueError: boom-7a", job.errors[0])
        stages = {s["stage"]: s for s in job.stages}
        self.assertIn("vietnamese_tts", stages)
        self.assertEqual(stages["action_compile"]["status"], "failed")
        self.assertNotIn("renderer", stages)
        self.assertFalse(artifacts["draft_exists"])
        events = artifacts["action_events.json"]
        self.assertIsNotNone(events)
        self.assertEqual(events["compile_error"], "ValueError: boom-7a")
        prod_err = artifacts["production_error.json"]
        self.assertEqual(prod_err["stage"], "action_compile")
        self.assertEqual(prod_err["error_code"], STAGE_EXCEPTION)


class TestRendererLabel(unittest.TestCase):
    def test_label_is_code_renderer(self):
        # The frames are always drawn by the code renderer; the old
        # label claimed "motion_canvas" whenever Chrome merely
        # existed. The render itself is mocked -- the label
        # computation is the code under test -- but the job runs
        # the real path through stage 10.
        render_result = {"n_frames": 1, "duration_sec": 0.04,
                         "violations": [], "camera_accounting": {},
                         "frames": [], "shots": []}
        patches = [
            mock.patch.object(product_flow, "render_product_video",
                              return_value=render_result),
            mock.patch.object(product_flow, "render_storyboard_stills",
                              return_value=[]),
            mock.patch.object(
                product_flow, "sync_foley_footsteps",
                return_value={"status": "skipped", "placements": 0,
                              "unresolved": [], "mix_changed": False}),
        ]
        # Real compile (no mock): the garden fixture compiles clean.
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            all_patches = [
                mock.patch.object(product_flow, "tts_cli_provider",
                                  side_effect=_stub_tts),
                *patches,
            ]
            for p in all_patches:
                p.start()
            try:
                job = product_flow.run_product_job(
                    GARDEN, job_dir, upload=False)
            finally:
                for p in all_patches:
                    p.stop()
            info_path = job_dir / "renderer_info.json"
            self.assertTrue(info_path.exists())
            info = json.loads(info_path.read_text(encoding="utf-8"))
        self.assertEqual(info["renderer"], "code_renderer")
        self.assertIsInstance(info["motion_canvas_available"], bool)
        stages = {s["stage"]: s for s in job.stages}
        self.assertTrue(stages["renderer"]["detail"].startswith(
            "code_renderer"))


if __name__ == "__main__":
    unittest.main()
