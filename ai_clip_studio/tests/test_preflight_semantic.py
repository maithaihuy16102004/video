"""Semantic preflight (A2 wiring item 9): preflight runs the conflict
mechanism over the real package and fails on blocking conflicts.
"""

import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio import preflight as preflight_mod
from ai_clip_studio.action_compiler import UnauthorizedStoryChange
from ai_clip_studio.preflight import semantic_preflight_checks
from ai_clip_studio.semantic_contracts import (
    ActionAuthority, ConflictRecord)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent


def _package(name):
    doc = parse_studio_script_v1(
        (AGENT / "examples" / f"{name}.studio.md").read_text(
            encoding="utf-8"))
    return adapt_document(doc)


class TestSemanticPreflightRealScripts(unittest.TestCase):
    def test_ep1_and_zeus_pass(self):
        for name in ("hitler_ep01_munich_1914",
                     "zeus_ep01_fall_of_cronus"):
            checks = semantic_preflight_checks(_package(name))
            by_name = {c.name: c for c in checks}
            self.assertEqual(
                set(by_name),
                {"semantic_conflicts", "scene_graph", "prop_states",
                 "prop_kinds", "actor_resolution"})
            # actor_resolution is the 5th check (sprint section 6):
            # a classified action with no resolvable actor fails
            # preflight; both real scripts resolve every actor.
            for check in checks:
                self.assertTrue(check.passed, check.detail)
            # Zeus 62/50 (regression matrix 2026-11-12): +2 from the
            # new "nắm chặt" HOLD and "đặt...lên bàn" PLACE_ON_SURFACE
            # rules, -1 from the abstract-receive exclusion ("nhận
            # một phần quyền cai quản" is not a prop receive).
            expected = "52 events" if "hitler" in name else "62 events"
            self.assertIn(expected, by_name["scene_graph"].detail)

    def test_resolved_conflict_passes_with_count(self):
        pkg = _package("hitler_ep01_munich_1914")
        records = [r for s in pkg["scenes"]
                   for r in s.get("cue_records", [])]
        injected = {
            "cue": "bend_pick", "matched_text": "cúi xuống nhặt ví",
            "match_start": 0, "match_end": 18,
            "pattern": "test-injected", "source_script_hash": "test",
            "source_scene_id": "SC01", "source_shot_id": "SC01_SH02",
            "source_directive_id": None,
            "action_origin": "PLANNER_INFERRED_ACTION",
            "inference_reason": "injected contradiction for the test",
            "authorization_status": "INFERRED"}
        pkg["scenes"][0]["cue_records"].append(injected)
        checks = semantic_preflight_checks(pkg)
        self.assertTrue(checks[0].passed, checks[0].detail)
        self.assertIn("1 conflict record(s)", checks[0].detail)

    def test_package_without_cue_records_degrades_gracefully(self):
        pkg = _package("hitler_ep01_munich_1914")
        for scene in pkg["scenes"]:
            scene.pop("cue_records", None)
        checks = semantic_preflight_checks(pkg)
        self.assertTrue(checks[0].passed, checks[0].detail)


class TestSemanticPreflightFailures(unittest.TestCase):
    def test_unresolved_record_fails(self):
        record = ConflictRecord(
            level_a="renderer_events", level_b="compiled_events",
            entity_id="A1", description="equal-authority disagreement",
            mandatory=True, winner_authority=None)
        self.assertTrue(record.fails_preflight)
        with mock.patch.object(
                preflight_mod, "detect_conflicts",
                return_value=[record]):
            checks = semantic_preflight_checks(
                _package("hitler_ep01_munich_1914"))
        self.assertFalse(checks[0].passed)
        self.assertIn("blocking semantic conflict", checks[0].detail)

    def test_parser_level_record_fails(self):
        # R3: the compiler emitted a forbidden verb. Resolution
        # (parser wins) does not clear it: staging the event
        # would stage the wrong story.
        record = ConflictRecord(
            level_a="parser", level_b="compiled_events",
            entity_id="A1",
            description="parser resolved HEAD_TILT_DOWN but the "
                        "compiler emitted forbidden verb BEND_PICK",
            mandatory=True,
            winner_authority=ActionAuthority.EXPLICIT_DIRECTIVE)
        self.assertFalse(record.fails_preflight)
        with mock.patch.object(
                preflight_mod, "detect_conflicts",
                return_value=[record]):
            checks = semantic_preflight_checks(
                _package("hitler_ep01_munich_1914"))
        self.assertFalse(checks[0].passed)
        self.assertIn("BEND_PICK", checks[0].detail)

    def test_unauthorized_story_change_is_a_preflight_failure(self):
        with mock.patch.object(
                preflight_mod, "compile_actions",
                side_effect=UnauthorizedStoryChange(
                    "unresolved mandatory semantic conflict(s): [x]")):
            checks = semantic_preflight_checks(
                _package("hitler_ep01_munich_1914"))
        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0].passed)
        self.assertEqual(checks[0].name, "semantic_conflicts")
        self.assertIn("UnauthorizedStoryChange", checks[0].detail)

    def test_ordinary_compile_failure_fails(self):
        with mock.patch.object(
                preflight_mod, "compile_actions",
                side_effect=RuntimeError("boom")):
            checks = semantic_preflight_checks(
                _package("hitler_ep01_munich_1914"))
        self.assertFalse(checks[0].passed)
        self.assertEqual(checks[0].name, "semantic_compile")
        self.assertIn("RuntimeError: boom", checks[0].detail)

    def test_graph_failure_fails_scene_graph_check(self):
        broken = {"scenes": {}, "shots": {}, "events": {},
                  "semantic_actions": {},
                  "validation": {
                      "errors": ["event X: unknown actor 'CHAR_GHOST'"],
                      "warnings": []}}
        with mock.patch.object(
                preflight_mod, "build_scene_graph",
                return_value=broken):
            checks = semantic_preflight_checks(
                _package("hitler_ep01_munich_1914"))
        by_name = {c.name: c for c in checks}
        self.assertTrue(by_name["semantic_conflicts"].passed)
        self.assertFalse(by_name["scene_graph"].passed)
        self.assertIn("GraphValidationError",
                      by_name["scene_graph"].detail)


if __name__ == "__main__":
    unittest.main()
