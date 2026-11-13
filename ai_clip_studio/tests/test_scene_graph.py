"""Canonical scene graph (A2 wiring item 12 + directive section 5):
the builder consumes SemanticAction records + SEMANTIC_TO_COMPILER_VERB,
indexes every entity with provenance, and validates references.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio.action_compiler import (
    SEMANTIC_TO_COMPILER_VERB, compile_actions)
from ai_clip_studio.scene_graph import (
    GraphValidationError, build_scene_graph, validate_or_raise,
    validate_scene_graph)
from ai_clip_studio.semantic_contracts import SemanticAction
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent


def _package(name):
    return adapt_document(parse_studio_script_v1(
        (AGENT / "examples" / f"{name}.studio.md").read_text(
            encoding="utf-8")))


def _compiled(name):
    package = _package(name)
    sem: list = []
    events, unsupported = compile_actions(package, semantic_sink=sem)
    return package, events, sem, unsupported


class TestSceneGraphRealScripts(unittest.TestCase):
    def test_ep1_graph(self):
        package, events, sem, unsupported = _compiled(
            "hitler_ep01_munich_1914")
        graph = build_scene_graph(
            package, events, semantic_actions=sem,
            unsupported=unsupported)
        validate_or_raise(graph)
        self.assertEqual(len(graph["scenes"]), 6)
        self.assertEqual(len(graph["shots"]), 17)
        # 2 cast + 2 extras groups (extras act and must resolve).
        self.assertEqual(len(graph["characters"]), 4)
        self.assertEqual(len(graph["props"]), 4)
        self.assertEqual(len(graph["events"]), 52)
        self.assertEqual(len(graph["semantic_actions"]), 41)
        self.assertEqual(graph["snapshot_hash"],
                         package["v1_snapshot_hash"])
        # Every semantic action links to its event; every event's
        # expected verb comes from the mapping.
        for directive_id, record in graph["semantic_actions"].items():
            self.assertEqual(
                record["compiler_verb"],
                SEMANTIC_TO_COMPILER_VERB[record["action_type"]])
            self.assertEqual(record["event_id"], directive_id)
        wallet = graph["events"]["SC01_SH02_ACT02"]
        self.assertEqual(wallet["semantic_type"], "TAKE_FROM_POCKET")
        self.assertEqual(wallet["verb"], "TAKE_OUT")
        self.assertEqual(wallet["prop_id"], "prop_wallet")

    def test_zeus_graph(self):
        package, events, sem, unsupported = _compiled(
            "zeus_ep01_fall_of_cronus")
        graph = build_scene_graph(
            package, events, semantic_actions=sem,
            unsupported=unsupported)
        validate_or_raise(graph)
        self.assertEqual(len(graph["scenes"]), 10)
        self.assertEqual(len(graph["shots"]), 41)
        self.assertEqual(len(graph["characters"]), 14)
        self.assertEqual(len(graph["props"]), 8)
        self.assertEqual(len(graph["events"]), 62)
        self.assertEqual(len(graph["semantic_actions"]), 50)
        hammers = [n for n in graph["events"].values()
                   if n["verb"] == "HAMMER_STRIKE"]
        self.assertTrue(hammers)
        for node in hammers:
            self.assertEqual(node["semantic_type"], "HAMMER_STRIKE")

    def test_resolve_path_matches_sink_path(self):
        package, events, sem, unsupported = _compiled(
            "hitler_ep01_munich_1914")
        resolved = build_scene_graph(package, events)
        sunk = build_scene_graph(
            package, events, semantic_actions=sem,
            unsupported=unsupported)
        self.assertEqual(len(resolved["semantic_actions"]),
                         len(sunk["semantic_actions"]))
        validate_or_raise(resolved)

    def test_json_round_trip_revalidates(self):
        package, events, sem, unsupported = _compiled(
            "hitler_ep01_munich_1914")
        graph = build_scene_graph(
            package, events, semantic_actions=sem,
            unsupported=unsupported)
        loaded = json.loads(json.dumps(graph, ensure_ascii=False))
        errors, warnings = validate_scene_graph(loaded)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings),
                         len(graph["validation"]["warnings"]))

    def test_provenance_on_event_nodes(self):
        package, events, sem, unsupported = _compiled(
            "hitler_ep01_munich_1914")
        graph = build_scene_graph(
            package, events, semantic_actions=sem,
            unsupported=unsupported)
        node = graph["events"]["SC01_SH02_ACT02"]
        provenance = node["provenance"]
        for field in ("source_script_hash", "source_scene_id",
                      "source_shot_id", "source_directive_id",
                      "action_origin", "inference_reason",
                      "authorization_status"):
            self.assertIn(field, provenance)
        self.assertEqual(provenance["source_directive_id"],
                         "SC01_SH02_ACT02")


def _minimal_package():
    return {
        "v1_snapshot_hash": "test",
        "scenes": [{"number": 1, "scene_id": "SC01", "title": "T",
                    "visible_characters": ["CHAR_A"],
                    "props": ["prop_wallet"]}],
        "shot_directives": [{"shot_id": "SC01_SH01", "scene": 1,
                             "shot_type": "medium"}],
        "characters": [{"id": "CHAR_A", "name": "A"}],
        "props": [{"id": "prop_wallet", "kind": "wallet",
                   "name": "wallet"}],
    }


def _action(action_type="WALK", directive_id="SC01_SH01_ACT01"):
    return SemanticAction(
        actor_id="CHAR_A", action_type=action_type, target_id=None,
        source_location=None, destination_location=None,
        body_part=None, interaction_hand="NONE",
        object_state_before=None, object_state_after=None,
        spatial_relationship=None, action_intent=None,
        source_scene_id="SC01", source_shot_id="SC01_SH01",
        source_directive_id=directive_id,
        source_text="A walks.", confidence=1.0,
        provenance="directive:SC01_SH01")


def _event(action_id="SC01_SH01_ACT01", verb="WALK", **overrides):
    event = {
        "action_id": action_id, "action_type": verb,
        "actor_id": "CHAR_A", "target_id": None,
        "prop_id": None, "shot_id": "SC01_SH01",
        "scene_number": 1, "start_time": 0.0, "end_time": 1.0,
        "source_script_hash": "test", "source_scene_id": "SC01",
        "source_shot_id": "SC01_SH01",
        "source_directive_id": action_id,
        "action_origin": "EXPLICIT_SCRIPT_ACTION",
        "inference_reason": "test", "authorization_status": "AUTHORIZED",
        "semantic_action_type": "WALK",
    }
    event.update(overrides)
    return event


class TestSceneGraphValidation(unittest.TestCase):
    def test_unknown_actor_fails(self):
        graph = build_scene_graph(
            _minimal_package(), [_event(actor_id="CHAR_GHOST")],
            semantic_actions=[_action()], unsupported=[])
        self.assertTrue(any("unknown actor" in e
                            for e in graph["validation"]["errors"]))
        with self.assertRaises(GraphValidationError):
            validate_or_raise(graph)

    def test_unknown_prop_shot_and_scene_fail(self):
        graph = build_scene_graph(
            _minimal_package(),
            [_event(prop_id="prop_nope", shot_id="SC99_SH99",
                    scene_number=99)],
            semantic_actions=[_action()], unsupported=[])
        errors = graph["validation"]["errors"]
        self.assertTrue(any("unknown prop" in e for e in errors))
        self.assertTrue(any("unknown shot" in e for e in errors))
        self.assertTrue(any("unknown scene" in e for e in errors))

    def test_unmapped_semantic_type_fails(self):
        # A dict record (hand-built/legacy shape): the builder
        # must fail loudly on a type the mapping does not cover
        # instead of guessing a verb. (The SemanticAction
        # dataclass itself rejects unknown types at construction.)
        record = {
            "actor_id": "CHAR_A", "action_type": "TELEPORT",
            "target_id": None, "source_scene_id": "SC01",
            "source_shot_id": "SC01_SH01",
            "source_directive_id": "SC01_SH01_ACT01",
            "source_text": "A teleports.", "confidence": 1.0,
            "provenance": "directive:SC01_SH01",
        }
        graph = build_scene_graph(
            _minimal_package(), [_event()], semantic_actions=[record],
            unsupported=[])
        self.assertTrue(any("no SEMANTIC_TO_COMPILER_VERB entry" in e
                            for e in graph["validation"]["errors"]))

    def test_forbidden_compilation_fails(self):
        action = _action(action_type="HEAD_TILT_DOWN")
        graph = build_scene_graph(
            _minimal_package(), [_event(verb="BEND_PICK")],
            semantic_actions=[action], unsupported=[])
        self.assertTrue(any("forbidden compilation" in e
                            for e in graph["validation"]["errors"]))

    def test_unlinked_semantic_action_fails(self):
        graph = build_scene_graph(
            _minimal_package(), [_event()],
            semantic_actions=[_action(directive_id="SC01_SH01_ACT99")],
            unsupported=[])
        self.assertTrue(any("produced no compiled event" in e
                            for e in graph["validation"]["errors"]))

    def test_supporting_event_warns_but_passes(self):
        graph = build_scene_graph(
            _minimal_package(), [_event(verb="IDLE")],
            semantic_actions=[], unsupported=[])
        validate_or_raise(graph)
        self.assertTrue(any("supporting action" in w
                            for w in graph["validation"]["warnings"]))

    def test_duplicate_event_ids_fail(self):
        graph = build_scene_graph(
            _minimal_package(), [_event(), _event()],
            semantic_actions=[_action()], unsupported=[])
        self.assertTrue(any("duplicate or missing action_id" in e
                            for e in graph["validation"]["errors"]))


class TestSceneGraphJobWiring(unittest.TestCase):
    def test_ep1_job_persists_scene_graph(self):
        from ai_clip_studio import product_flow
        from ai_clip_studio.tests.test_unauthorized_story_change import (
            _stub_tts)
        script = (AGENT / "examples"
                  / "hitler_ep01_munich_1914.studio.md").read_text(
                      encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            with mock.patch.object(product_flow, "tts_cli_provider",
                                   side_effect=_stub_tts), \
                mock.patch.object(
                    product_flow, "emit_job_spec",
                    side_effect=RuntimeError("STOP_AFTER_7A")):
                job = product_flow.run_product_job(
                    script, job_dir, upload=False)
            self.assertIn("STOP_AFTER_7A", job.errors[0])
            graph = json.loads(
                (job_dir / "scene_graph.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(len(graph["events"]), 52)
            self.assertEqual(graph["validation"]["errors"], [])
            self.assertEqual(len(job.package["scene_graph"]["events"]),
                             52)

    def test_graph_failure_fails_job_at_early_pass(self):
        from ai_clip_studio import product_flow
        from ai_clip_studio.tests.test_unauthorized_story_change import (
            _stub_tts)
        broken = {"validation": {
            "errors": ["event X: unknown actor 'CHAR_GHOST'"],
            "warnings": []}}
        script = (AGENT / "examples"
                  / "hitler_ep01_munich_1914.studio.md").read_text(
                      encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            with mock.patch.object(product_flow, "tts_cli_provider",
                                   side_effect=_stub_tts), \
                mock.patch.object(product_flow, "build_scene_graph",
                                  return_value=broken):
                job = product_flow.run_product_job(
                    script, job_dir, upload=False)
            stages = {s["stage"]: s for s in job.stages}
            self.assertEqual(job.status, "FAILED")
            self.assertEqual(stages["semantic_conflicts"]["status"],
                             "failed")
            self.assertNotIn("vietnamese_tts", stages)
            self.assertIn("GraphValidationError", job.errors[0])


if __name__ == "__main__":
    unittest.main()
