"""Tests for ai_clip_studio.semantic_contracts (ATLAS-owned interfaces).

These pin the contracts A2/B2 build against: authority order, semantic
action validation, prop transitions + the ground rule, scope isolation,
frozen-schedule immutability, and conflict resolution.
"""

import unittest
from dataclasses import FrozenInstanceError

from ai_clip_studio.semantic_contracts import (
    ActionAuthority, ActionOrigin, AuthorizationStatus, SemanticAction,
    EXAMPLE_RESOLUTIONS, PropLocation, PROP_TRANSITIONS,
    prop_transition_allowed, prop_may_rest_on_ground,
    StateScope, resolve_scoped_attribute,
    TimelineInterval, FrozenSchedule,
    ConflictRecord, resolve_conflict,
)


def _action(**overrides):
    base = dict(
        actor_id="CHAR_HITLER", action_type="TAKE_FROM_POCKET",
        target_id="PROP_WALLET", source_location="pocket",
        destination_location=None, body_part="hand",
        interaction_hand="RIGHT", object_state_before="CLOSED",
        object_state_after="CLOSED", spatial_relationship="in_pocket",
        action_intent="inspect", source_scene_id="SC01",
        source_shot_id="SC01_SH02", source_directive_id="SC01_SH02",
        source_text="Lấy ví từ túi áo", confidence=0.95,
        provenance="directive:SC01_SH02",
    )
    base.update(overrides)
    return SemanticAction(**base)


class TestAuthorityOrder(unittest.TestCase):
    def test_explicit_beats_keyword(self):
        self.assertLess(ActionAuthority.EXPLICIT_DIRECTIVE,
                        ActionAuthority.PLANNER_SUGGESTION)
        self.assertLess(ActionAuthority.COMPILED_EVENT,
                        ActionAuthority.PLANNER_SUGGESTION)

    def test_origins_complete(self):
        names = {o.value for o in ActionOrigin}
        self.assertIn("UNAUTHORIZED_STORY_CHANGE", names)
        self.assertIn("EXPLICIT_SCRIPT_ACTION", names)


class TestSemanticAction(unittest.TestCase):
    def test_valid_action(self):
        a = _action()
        self.assertEqual(a.action_type, "TAKE_FROM_POCKET")
        self.assertEqual(a.authorization_status,
                         AuthorizationStatus.AUTHORIZED)

    def test_unknown_type_rejected(self):
        with self.assertRaises(ValueError):
            _action(action_type="SPAWN_PROP")

    def test_bad_hand_rejected(self):
        with self.assertRaises(ValueError):
            _action(interaction_hand="MIDDLE")

    def test_confidence_bounds(self):
        with self.assertRaises(ValueError):
            _action(confidence=1.5)

    def test_source_text_required(self):
        with self.assertRaises(ValueError):
            _action(source_text="  ")

    def test_frozen(self):
        a = _action()
        with self.assertRaises(FrozenInstanceError):
            a.action_type = "BEND_PICK"

    def test_normative_examples_well_formed(self):
        # The Mai-specified distinctions (7) + the release-destination
        # distinctions (2, regression matrix 2026-11-12); the parser
        # tests assert resolution, here we pin the table itself.
        self.assertEqual(len(EXAMPLE_RESOLUTIONS), 9)
        for row in EXAMPLE_RESOLUTIONS:
            self.assertIn(row["expected"],
                          {"HEAD_TILT_DOWN", "BEND_PICK",
                           "TAKE_FROM_POCKET", "PICK_FROM_SURFACE",
                           "CROUCH", "RECEIVE_PROP", "HAMMER_STRIKE",
                           "RELEASE_PROP", "PLACE_ON_SURFACE"})


class TestPropTransitions(unittest.TestCase):
    def test_pocket_to_hand(self):
        self.assertTrue(prop_transition_allowed("IN_POCKET",
                                                "TAKE_FROM_POCKET"))

    def test_ground_pickup_requires_bend_pick(self):
        self.assertTrue(prop_transition_allowed("ON_GROUND", "BEND_PICK"))
        self.assertFalse(prop_transition_allowed("ON_GROUND",
                                                 "TAKE_FROM_POCKET"))

    def test_no_teleport_pocket_to_ground(self):
        # No direct IN_POCKET -> ON_GROUND transition exists.
        self.assertFalse(any(
            f == "IN_POCKET" and t == "ON_GROUND"
            for (f, _), t in PROP_TRANSITIONS.items()))

    def test_ground_rule(self):
        self.assertTrue(prop_may_rest_on_ground("ON_GROUND"))
        self.assertFalse(prop_may_rest_on_ground("IN_POCKET"))
        self.assertFalse(prop_may_rest_on_ground("HELD_RIGHT"))

    def test_handover_round_trip(self):
        self.assertEqual(PROP_TRANSITIONS[("HELD_RIGHT", "HAND_OVER")],
                         "IN_TRANSIT")
        self.assertEqual(PROP_TRANSITIONS[("IN_TRANSIT", "RECEIVE_PROP")],
                         "HELD_RIGHT")


class TestScopeIsolation(unittest.TestCase):
    def test_scene_beats_project(self):
        self.assertEqual(
            resolve_scoped_attribute({
                StateScope.PROJECT: "dry",
                StateScope.SCENE: "rain"}),
            "rain")

    def test_no_scene_value_falls_back(self):
        self.assertEqual(
            resolve_scoped_attribute({StateScope.PROJECT: "dry"}), "dry")

    def test_unrelated_scene_sees_no_rain(self):
        # Each scene resolves its own chain: scene 1 has no rain value,
        # so it resolves the project default even though scene 6 rains.
        scene1 = resolve_scoped_attribute({StateScope.PROJECT: "dry"})
        scene6 = resolve_scoped_attribute({
            StateScope.PROJECT: "dry", StateScope.SCENE: "rain"})
        self.assertEqual(scene1, "dry")
        self.assertEqual(scene6, "rain")


class TestFrozenSchedule(unittest.TestCase):
    def _interval(self, track, iid, start, end):
        return TimelineInterval(
            track=track, interval_id=iid,
            start_frame=start, end_frame=end,
            start_sample=start * 2000, end_sample=end * 2000)

    def test_frame_seconds_derive(self):
        iv = self._interval("narration", "L1", 168, 408)
        self.assertEqual(iv.start_sec, 7.0)
        self.assertEqual(iv.duration_frames, 240)

    def test_invalid_interval_rejected(self):
        with self.assertRaises(ValueError):
            self._interval("narration", "L1", 408, 168)

    def test_freeze_blocks_mutation(self):
        sched = FrozenSchedule()
        sched.add(self._interval("narration", "L1", 0, 24))
        sched.freeze()
        self.assertTrue(sched.frozen)
        with self.assertRaises(FrozenInstanceError):
            sched.add(self._interval("narration", "L2", 24, 48))

    def test_narration_completeness(self):
        sched = FrozenSchedule()
        sched.add(self._interval("narration", "L1", 0, 24))
        sched.add(self._interval("dialogue", "L2", 24, 48))
        self.assertTrue(sched.narration_complete(["L1", "L2"]))
        self.assertFalse(sched.narration_complete(["L1"]))
        sched2 = FrozenSchedule()
        sched2.add(self._interval("narration", "L1", 0, 24))
        sched2.add(self._interval("narration", "L1", 24, 48))
        self.assertFalse(sched2.narration_complete(["L1"]))


class TestConflicts(unittest.TestCase):
    def test_higher_authority_wins(self):
        rec = ConflictRecord(
            level_a="cues", level_b="compiled_events",
            entity_id="ACT01", description="bend_pick vs take_out",
            mandatory=True)
        resolved = resolve_conflict(
            rec, ActionAuthority.PLANNER_SUGGESTION,
            ActionAuthority.COMPILED_EVENT)
        self.assertEqual(resolved.winner_authority,
                         ActionAuthority.COMPILED_EVENT)
        self.assertFalse(resolved.fails_preflight)

    def test_unresolved_mandatory_fails_preflight(self):
        rec = ConflictRecord(
            level_a="parser", level_b="cues", entity_id="ACT02",
            description="disagreement", mandatory=True)
        unresolved = resolve_conflict(
            rec, ActionAuthority.EXPLICIT_DIRECTIVE,
            ActionAuthority.EXPLICIT_DIRECTIVE)
        self.assertTrue(unresolved.fails_preflight)

    def test_optional_conflict_does_not_fail(self):
        rec = ConflictRecord(
            level_a="parser", level_b="cues", entity_id="ACT03",
            description="minor", mandatory=False)
        self.assertFalse(rec.fails_preflight)


if __name__ == "__main__":
    unittest.main()
