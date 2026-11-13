"""Tests for the prop interaction chain (Phase D / TEST E).

The chain is approach -> sit -> grasp pen -> write -> sign -> pick
up document -> hand over, driven by the real primitives and the
real PropStateMachine, with measured hand-object contact at each
action's contact moment and no teleports. Geometry is synthetic
staging (a desk, a pen, a paper), not a story script.
"""
from __future__ import annotations

import unittest

from ai_clip_studio.animation import primitives as P
from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.prop_system import (
    PropStateMachine,
    check_chain_order,
    verify_chain,
)

GY = 920.0
PAPER = {"x": 990, "y": 690, "w": 220, "h": 140}
DESK = {"x": 1000, "top_y": 760}


def _event(action_id, action_type, actor_id, prop_id, start, end,
           params=None, target_id=None, contact_points=None):
    return {
        "action_id": action_id,
        "action_type": action_type,
        "actor_id": actor_id,
        "prop_id": prop_id,
        "target_id": target_id,
        "start_time": start,
        "end_time": end,
        "required_pose": {"primitive": action_type.lower(),
                          "params": params or {"hand": "r"}},
        "contact_points": contact_points or [],
    }


class TestCheckChainOrder(unittest.TestCase):
    def test_clean_chain_has_no_violations(self):
        events = [
            _event("A1", "HOLD_PEN", "CHAR_A", "prop_pen", 1.0, 2.0),
            _event("A2", "WRITE", "CHAR_A", "prop_pen", 2.0, 5.0),
            _event("A3", "SIGN", "CHAR_A", "prop_pen", 5.0, 6.0),
            _event("A4", "PICK_UP", "CHAR_A", "prop_paper", 6.0, 7.0),
            _event("A5", "HAND_OVER", "CHAR_A", "prop_paper", 7.0, 8.0,
                   target_id="CHAR_B"),
            _event("A6", "PUT_AWAY", "CHAR_B", "prop_paper", 8.0, 9.0),
        ]
        self.assertEqual(check_chain_order(events), [])

    def test_write_without_grasp_is_violation(self):
        events = [_event("A1", "WRITE", "CHAR_A", "prop_pen", 1.0, 2.0)]
        bad = check_chain_order(events)
        self.assertEqual(len(bad), 1)
        self.assertIn("without a preceding grasp", bad[0]["issue"])

    def test_handover_without_grasp_is_violation(self):
        events = [_event("A1", "HAND_OVER", "CHAR_A", "prop_paper",
                         1.0, 2.0, target_id="CHAR_B")]
        bad = check_chain_order(events)
        self.assertEqual(len(bad), 1)

    def test_use_by_non_holder_is_violation(self):
        events = [
            _event("A1", "HOLD_PEN", "CHAR_A", "prop_pen", 1.0, 2.0),
            _event("A2", "WRITE", "CHAR_B", "prop_pen", 2.0, 3.0),
        ]
        bad = check_chain_order(events)
        self.assertEqual(len(bad), 1)
        self.assertIn("is held by", bad[0]["issue"])

    def test_release_without_grasp_is_violation(self):
        events = [_event("A1", "PUT_AWAY", "CHAR_A", "prop_pen",
                         1.0, 2.0)]
        self.assertEqual(len(check_chain_order(events)), 1)

    def test_initial_holders_excuse_an_earlier_grasp(self):
        events = [_event("A1", "WRITE", "CHAR_A", "prop_pen", 1.0, 2.0)]
        self.assertEqual(
            check_chain_order(events, initial_holders={"prop_pen": "CHAR_A"}),
            [])

    def test_handover_transfers_the_holder(self):
        events = [
            _event("A1", "PICK_UP", "CHAR_A", "prop_paper", 1.0, 2.0),
            _event("A2", "HAND_OVER", "CHAR_A", "prop_paper", 2.0, 3.0,
                   target_id="CHAR_B"),
            _event("A3", "PUT_AWAY", "CHAR_B", "prop_paper", 3.0, 4.0),
        ]
        self.assertEqual(check_chain_order(events), [])


class TestVerifyChain(unittest.TestCase):
    def _run_chain(self):
        writer = Stickman(height=560, name="writer")
        receiver = Stickman(height=560, name="receiver")
        # Receiver at 1300: the handover meeting point must be within
        # both characters' arm reach, or the IK clamp stops the
        # receiver's hand short (at 1350 the gap was ~33 px).
        P.standing(receiver, 1300, GY, facing=-1)
        P.standing(writer, 1000, GY, facing=1)
        segments = [
            (0.0, 1.0, P.sit_at_desk(writer, 1000, 770, 1.0, GY,
                                    desk=DESK)),
            (1.0, 2.0, P.hold_pen(writer, (1050, 745), PAPER, 1.0)),
            (2.0, 5.0, P.write_on_paper(writer, PAPER, 3.0, words=6)),
            (5.0, 6.2, P.sign_document(writer, PAPER, 1.2)),
            (6.2, 7.2, P.pick_up(writer, (1100, 760), 1.0, GY,
                                 source="desk")),
        ]
        prop_dict = {"x": 1100, "y": 760}
        handover = P.hand_over(writer, receiver, prop_dict, 1.5)
        events = [
            _event("E1", "HOLD_PEN", "CHAR_A", "prop_pen", 1.0, 2.0,
                   contact_points=[{
                       "joint": "hand_r", "target_kind": "prop",
                       "target_id": "prop_pen", "tolerance_px": 60}]),
            _event("E2", "WRITE", "CHAR_A", "prop_pen", 2.0, 5.0,
                   params={"hand": "r", "paper_id": "prop_paper",
                           "paper_size": (220, 140)},
                   contact_points=[{
                       "joint": "hand_r", "target_kind": "prop_surface",
                       "target_id": "prop_paper", "tolerance_px": 10}]),
            _event("E3", "SIGN", "CHAR_A", "prop_pen", 5.0, 6.2,
                   params={"hand": "r", "paper_id": "prop_paper",
                           "paper_size": (220, 140)},
                   contact_points=[{
                       "joint": "hand_r", "target_kind": "prop_surface",
                       "target_id": "prop_paper", "tolerance_px": 10}]),
            _event("E4", "PICK_UP", "CHAR_A", "prop_paper", 6.2, 7.2,
                   contact_points=[{
                       "joint": "hand_r", "target_kind": "prop",
                       "target_id": "prop_paper", "tolerance_px": 40}]),
            _event("E5", "HAND_OVER", "CHAR_A", "prop_paper", 7.2, 8.7,
                   target_id="CHAR_B",
                   contact_points=[{
                       "joint": "hand_r", "target_kind": "character_hand",
                       "target_id": "CHAR_B", "tolerance_px": 10}]),
        ]
        psm = PropStateMachine(
            [{"id": "prop_pen", "kind": "pen"},
             {"id": "prop_paper", "kind": "paper"}],
            events,
            staging={"prop_pen": (1050, 745),
                     "prop_paper": (1100, 760)},
            ground_y=GY)
        samples = []
        for fi in range(int(8.7 * 24) + 1):
            t = fi / 24.0
            for start, end, fn in segments:
                if start <= t <= end:
                    fn(t - start)
            if 7.2 <= t <= 8.7:
                handover(t - 7.2)
            joints = {"CHAR_A": writer.joints(),
                      "CHAR_B": receiver.joints()}
            samples.append({
                "t": t,
                "joints": joints,
                "transforms": {
                    pid: psm.transform_at(pid, t, joints)
                    for pid in ("prop_pen", "prop_paper")},
            })
        return psm, samples, events, prop_dict

    def test_chain_is_clean(self):
        psm, samples, events, _prop = self._run_chain()
        self.assertEqual(psm.diagnostics, [])
        report = verify_chain(psm, samples, events, ground_y=GY)
        self.assertEqual(report["violations"], [])
        for pid, jump in report["teleports"].items():
            self.assertFalse(jump["teleport"], pid)
            self.assertLess(jump["max_speed_px_per_sec"], 1200.0)
        for action_id, entries in report["contact"].items():
            for entry in entries:
                self.assertTrue(entry["satisfied"],
                                f"{action_id}: {entry}")

    def test_pen_state_sequence(self):
        psm, samples, events, _prop = self._run_chain()
        report = verify_chain(psm, samples, events, ground_y=GY)
        states = report["states"]["prop_pen"]
        self.assertEqual(states[0], "WORLD_STATIC")
        self.assertIn("GRASPED", states)
        self.assertIn("IN_USE", states)
        self.assertLess(states.index("GRASPED"), states.index("IN_USE"))

    def test_paper_holder_switches_at_handover(self):
        _psm, _samples, _events, prop_dict = self._run_chain()
        self.assertEqual(prop_dict["holder"], "receiver")

    def test_no_ground_prop_without_release(self):
        # The pen never returns to WORLD_STATIC (no release event),
        # so it must never sit at its rest position mid-chain.
        psm, samples, events, _prop = self._run_chain()
        report = verify_chain(psm, samples, events, ground_y=GY)
        states = report["states"]["prop_pen"]
        self.assertEqual(states.count("WORLD_STATIC"), 1)


if __name__ == "__main__":
    unittest.main()
