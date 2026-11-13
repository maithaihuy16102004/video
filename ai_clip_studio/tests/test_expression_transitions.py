"""Tests for expression transition alignment (Phase D)."""
from __future__ import annotations

import unittest

from ai_clip_studio.cinematic_contracts import ExpressionTransition
from ai_clip_studio.expression_library import (
    blink_times_for,
    schedule_transitions,
    validate_transitions,
)


def _tr(from_state, to_state, align):
    return ExpressionTransition(from_state=from_state, to_state=to_state,
                                align=align)


class TestBlinkSchedule(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(blink_times_for(10.0, seed=3),
                         blink_times_for(10.0, seed=3))

    def test_gaps_in_range_and_first_blink_early(self):
        times = blink_times_for(20.0, seed=1)
        self.assertGreater(len(times), 2)
        self.assertLess(times[0], 2.8)
        for a, b in zip(times, times[1:]):
            self.assertGreaterEqual(b - a, 2.8)
            self.assertLessEqual(b - a, 5.0)
        self.assertLess(times[-1], 20.0)

    def test_empty_for_nonpositive_duration(self):
        self.assertEqual(blink_times_for(0.0), [])
        self.assertEqual(blink_times_for(-1.0), [])


class TestValidateTransitions(unittest.TestCase):
    def test_major_change_at_cut_is_clean(self):
        bad = validate_transitions(
            [(2.0, _tr("neutral", "angry", "cut"))], cut_times=[2.0])
        self.assertEqual(bad, [])

    def test_major_change_at_beat_is_clean(self):
        bad = validate_transitions(
            [(2.0, _tr("neutral", "surprised", "beat"))], beat_times=[2.05])
        self.assertEqual(bad, [])

    def test_major_change_with_micro_align_is_violation(self):
        bad = validate_transitions(
            [(2.0, _tr("neutral", "angry", "micro"))], cut_times=[2.0])
        self.assertEqual(len(bad), 1)
        self.assertIn("micro", bad[0])

    def test_cut_aligned_change_without_a_cut_is_violation(self):
        bad = validate_transitions(
            [(2.0, _tr("neutral", "angry", "cut"))], cut_times=[5.0])
        self.assertEqual(len(bad), 1)
        self.assertIn("no cut", bad[0])

    def test_beat_aligned_change_without_a_beat_is_violation(self):
        bad = validate_transitions(
            [(2.0, _tr("neutral", "angry", "beat"))], beat_times=[5.0])
        self.assertEqual(len(bad), 1)

    def test_same_base_is_not_major(self):
        # "focused" resolves to the "thinking" base.
        bad = validate_transitions(
            [(2.0, _tr("focused", "thinking", "micro"))])
        self.assertEqual(bad, [])

    def test_unresolvable_state_is_violation(self):
        bad = validate_transitions(
            [(2.0, _tr("neutral", "gibberish_no_such_face", "cut"))],
            cut_times=[2.0])
        self.assertEqual(len(bad), 1)
        self.assertIn("unresolvable", bad[0])

    def test_tolerance_boundary(self):
        bad = validate_transitions(
            [(2.0, _tr("neutral", "angry", "cut"))],
            cut_times=[2.13], tol=0.12)
        self.assertEqual(len(bad), 1)
        bad = validate_transitions(
            [(2.0, _tr("neutral", "angry", "cut"))],
            cut_times=[2.11], tol=0.12)
        self.assertEqual(bad, [])


class TestScheduleTransitions(unittest.TestCase):
    def test_snaps_to_nearest_cut_with_warning(self):
        keyframes, transitions, warnings = schedule_transitions(
            [(2.05, "neutral", "angry", "cut")], cut_times=[2.0, 5.0])
        self.assertEqual(keyframes[0][0], 2.0)
        self.assertEqual(transitions[0][0], 2.0)
        self.assertEqual(len(warnings), 1)
        self.assertIn("snapped", warnings[0])

    def test_no_anchor_keeps_time_with_warning(self):
        keyframes, _transitions, warnings = schedule_transitions(
            [(2.05, "neutral", "angry", "cut")], cut_times=[5.0])
        self.assertEqual(keyframes[0][0], 2.05)
        self.assertEqual(len(warnings), 1)
        self.assertIn("no cut", warnings[0])

    def test_micro_major_keeps_time_and_align_with_warning(self):
        keyframes, transitions, warnings = schedule_transitions(
            [(2.0, "neutral", "angry", "micro")], cut_times=[2.0])
        self.assertEqual(keyframes[0][0], 2.0)
        self.assertEqual(transitions[0][1].align, "micro")
        self.assertEqual(len(warnings), 1)

    def test_non_major_change_is_not_snapped(self):
        keyframes, _transitions, warnings = schedule_transitions(
            [(2.05, "focused", "thinking", "cut")], cut_times=[2.0])
        self.assertEqual(keyframes[0][0], 2.05)
        self.assertEqual(warnings, [])

    def test_scheduled_major_changes_validate_clean(self):
        requests = [
            (1.02, "neutral", "thinking", "beat"),
            (4.98, "thinking", "angry", "cut"),
        ]
        _keyframes, transitions, _warnings = schedule_transitions(
            requests, cut_times=[5.0], beat_times=[1.0])
        bad = validate_transitions(transitions, cut_times=[5.0],
                                   beat_times=[1.0])
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
