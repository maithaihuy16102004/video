"""Tests for locomotion metadata in the action compiler (Phase A).

Additive only: locomotion_state params on locomotion events and
gait_profile passthrough from character data. Event counts must not
change. Fixtures are synthetic (Ana/Ben), never a supplied script.
"""
from __future__ import annotations

import unittest

from ai_clip_studio.action_compiler import compile_actions


def _package(scenes, characters=None):
    return {
        "characters": characters or [
            {"id": "CHAR_ANA", "name": "Ana", "gender": "female",
             "template": "female"},
            {"id": "CHAR_BEN", "name": "Ben", "gender": "male",
             "template": "male"},
        ],
        "props": [],
        "scenes": scenes,
    }


def _scene(shot_id, actions):
    return {
        "id": "SC01",
        "location_id": "LOC_CAFE",
        "shots": [{
            "id": shot_id,
            "camera": "MEDIUM",
            "action": " ".join(actions),
            "expression": "",
        }],
        "v1_scene": {
            "id": "SC01",
            "shots": [{
                "id": shot_id,
                "camera": "MEDIUM",
                "action": " ".join(actions),
            }],
        },
    }


class TestLocomotionMetadata(unittest.TestCase):
    def test_walk_and_turn_carry_locomotion_state(self):
        pkg = _package([_scene("SC01_SH01", [
            "Ana đi tới cửa.", "Ana quay lại.", "Ana dừng lại."])])
        events, _unsupported = compile_actions(pkg)
        by_type = {e["action_type"]: e for e in events}
        self.assertIn("WALK", by_type)
        self.assertIn("TURN", by_type)
        self.assertIn("STOP", by_type)
        self.assertEqual(
            by_type["WALK"]["required_pose"]["params"]["locomotion_state"],
            "WALK")
        self.assertEqual(
            by_type["TURN"]["required_pose"]["params"]["locomotion_state"],
            "TURN")
        self.assertEqual(
            by_type["STOP"]["required_pose"]["params"]["locomotion_state"],
            "STOP_WALK")

    def test_non_locomotion_events_have_no_locomotion_state(self):
        pkg = _package([_scene("SC01_SH01", ["Ana vẫy tay."])])
        events, _unsupported = compile_actions(pkg)
        for event in events:
            self.assertNotIn(
                "locomotion_state",
                event["required_pose"]["params"])

    def test_gait_profile_passes_through(self):
        characters = [
            {"id": "CHAR_ANA", "name": "Ana", "gender": "female",
             "template": "female", "gait_profile": "elderly"},
            {"id": "CHAR_BEN", "name": "Ben", "gender": "male",
             "template": "male"},
        ]
        pkg = _package([_scene("SC01_SH01", ["Ana đi tới cửa."])],
                       characters=characters)
        events, _unsupported = compile_actions(pkg)
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["required_pose"]["params"]["gait_profile"],
            "elderly")

    def test_no_gait_profile_no_param(self):
        pkg = _package([_scene("SC01_SH01", ["Ana đi tới cửa."])])
        events, _unsupported = compile_actions(pkg)
        self.assertNotIn("gait_profile",
                         events[0]["required_pose"]["params"])

    def test_event_count_unchanged_by_gait_data(self):
        actions = ["Ana đi tới cửa.", "Ana quay lại.",
                   "Ana dừng lại.", "Ana vẫy tay."]
        plain, _ = compile_actions(_package([_scene("SC01_SH01", actions)]))
        characters = [
            {"id": "CHAR_ANA", "name": "Ana", "gender": "female",
             "template": "female", "gait_profile": "elderly"},
            {"id": "CHAR_BEN", "name": "Ben", "gender": "male",
             "template": "male", "gait_profile": "soldier"},
        ]
        gaited, _ = compile_actions(
            _package([_scene("SC01_SH01", actions)], characters=characters))
        self.assertEqual(len(plain), len(gaited))
        self.assertEqual([e["action_type"] for e in plain],
                         [e["action_type"] for e in gaited])


if __name__ == "__main__":
    unittest.main()
