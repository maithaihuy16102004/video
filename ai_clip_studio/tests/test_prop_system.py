"""Tests for ai_clip_studio/prop_system.py."""
from __future__ import annotations

import unittest

from ai_clip_studio.prop_system import (
    MAX_JUMP_PX_PER_SEC,
    PropStateMachine,
    contact_report,
    contact_satisfied,
    sampled_max_jump,
)
from ai_clip_studio.animation.primitives import pen_tip_position

PROPS = [
    {"id": "prop_wallet", "kind": "wallet", "owner": "CHAR_A"},
    {"id": "prop_pen", "kind": "pen", "owner": "CHAR_A"},
    {"id": "prop_letter", "kind": "letter"},
]

STAGING = {
    "prop_wallet": {"kind": "pocket", "anchor_id": "CHAR_A",
                    "offset": (30.0, -40.0)},
    "prop_pen": (100.0, 900.0, 0.0),
    "prop_letter": {"kind": "surface", "x": 500.0, "y": 800.0},
}


def _event(action_id, action_type, start, end, prop_id="prop_wallet",
           actor="CHAR_A", target=None, hand="r", extra_params=None):
    params = {"hand": hand}
    if extra_params:
        params.update(extra_params)
    return {
        "action_id": action_id, "actor_id": actor,
        "action_type": action_type, "target_id": target,
        "prop_id": prop_id, "start_time": start, "end_time": end,
        "required_pose": {"pose": "x", "params": params},
        "contact_points": [],
    }


def _joints(hand_r=(450.0, 700.0), hand_l=(380.0, 700.0),
            hip=(400.0, 600.0), facing=1):
    return {"CHAR_A": {"hip": hip, "hand_r": hand_r, "hand_l": hand_l,
                       "facing": facing},
            "CHAR_B": {"hip": (700.0, 600.0), "hand_r": (680.0, 700.0),
                       "hand_l": (650.0, 700.0), "facing": -1}}


class TestStateTransitions(unittest.TestCase):
    def _machine(self):
        events = [
            _event("A1", "TAKE_OUT", 1.0, 2.0),
            _event("A2", "OPEN_WALLET", 2.0, 3.0, hand="both"),
            _event("A3", "CLOSE_WALLET", 3.0, 4.0, hand="both"),
            _event("A4", "PUT_AWAY", 4.0, 5.0),
        ]
        return PropStateMachine(PROPS, events, staging=STAGING,
                                ground_y=1000.0)

    def test_full_lifecycle(self):
        sm = self._machine()
        self.assertEqual(sm.state_at("prop_wallet", 0.5), "WORLD_STATIC")
        self.assertEqual(sm.state_at("prop_wallet", 1.0), "APPROACHING")
        self.assertEqual(sm.state_at("prop_wallet", 1.45), "GRASPED")
        self.assertEqual(sm.state_at("prop_wallet", 1.6),
                         "ATTACHED_TO_HAND")
        self.assertEqual(sm.state_at("prop_wallet", 2.5), "IN_USE")
        self.assertEqual(sm.state_at("prop_wallet", 4.2),
                         "ATTACHED_TO_HAND")
        self.assertEqual(sm.state_at("prop_wallet", 4.8), "RELEASED")
        self.assertEqual(sm.state_at("prop_wallet", 5.0), "WORLD_STATIC")

    def test_open_u_interpolates(self):
        sm = self._machine()
        self.assertEqual(sm.detail_at("prop_wallet", 1.0)["open_u"], 0.0)
        self.assertAlmostEqual(sm.detail_at("prop_wallet", 2.5)["open_u"],
                               0.5, places=6)
        self.assertEqual(sm.detail_at("prop_wallet", 3.0)["open_u"], 1.0)
        self.assertAlmostEqual(sm.detail_at("prop_wallet", 3.5)["open_u"],
                               0.5, places=6)
        self.assertEqual(sm.detail_at("prop_wallet", 4.0)["open_u"], 0.0)

    def test_unknown_prop_raises(self):
        sm = self._machine()
        with self.assertRaises(KeyError):
            sm.state_at("prop_nope", 0.0)
        with self.assertRaises(KeyError):
            sm.transform_at("prop_nope", 0.0, _joints())

    def test_unstaged_prop_diagnostic(self):
        sm = PropStateMachine(
            [{"id": "prop_mystery", "kind": "ring"}], [], staging={})
        self.assertTrue(any(d["prop_id"] == "prop_mystery"
                            for d in sm.diagnostics))
        x, y, angle, state, hand = sm.transform_at(
            "prop_mystery", 0.0, _joints())
        self.assertEqual((x, y), (0.0, 0.0))
        self.assertEqual(state, "WORLD_STATIC")

    def test_use_without_grasp_diagnostic(self):
        sm = PropStateMachine(
            PROPS, [_event("W1", "WRITE", 0.0, 1.0, prop_id="prop_pen")],
            staging=STAGING)
        self.assertTrue(any("WRITE" in d["issue"]
                            for d in sm.diagnostics))
        self.assertEqual(sm.state_at("prop_pen", 0.5), "IN_USE")


class TestAttachmentInvariants(unittest.TestCase):
    def test_attached_follows_named_hand(self):
        sm = PropStateMachine(
            PROPS, [_event("A1", "PICK_UP", 0.0, 1.0)],
            staging=STAGING)
        joints = _joints(hand_r=(512.0, 633.0))
        x, y, _angle, state, hand = sm.transform_at(
            "prop_wallet", 0.9, joints)
        self.assertEqual(state, "ATTACHED_TO_HAND")
        self.assertEqual((x, y), (512.0, 633.0))
        self.assertEqual(hand, "r")

    def test_both_hands_anchor_to_dominant_hand(self):
        sm = PropStateMachine(
            PROPS, [_event("A1", "PICK_UP", 0.0, 1.0),
                    _event("A2", "OPEN_WALLET", 1.0, 2.0, hand="both")],
            staging=STAGING)
        joints = _joints(hand_r=(512.0, 633.0), hand_l=(300.0, 600.0))
        x, y, _angle, state, hand = sm.transform_at(
            "prop_wallet", 1.5, joints)
        self.assertEqual((x, y), (512.0, 633.0))
        self.assertEqual(hand, "r")

    def test_no_teleport_across_lifecycle(self):
        sm = PropStateMachine(
            PROPS,
            [_event("A1", "TAKE_OUT", 1.0, 2.0),
             _event("A2", "OPEN_WALLET", 2.0, 3.0, hand="both"),
             _event("A3", "CLOSE_WALLET", 3.0, 4.0, hand="both"),
             _event("A4", "PUT_AWAY", 4.0, 5.0)],
            staging=STAGING, ground_y=1000.0)

        def joints_at(t):
            # Hand drifts slowly; hip stays put (pocket anchor).
            return _joints(hand_r=(400.0 + 50.0 * t, 700.0))

        samples = []
        for i in range(121):
            t = i / 20.0
            x, y, _a, _s, _h = sm.transform_at(
                "prop_wallet", t, joints_at(t))
            samples.append((t, x, y))
        result = sampled_max_jump(samples)
        self.assertFalse(result["teleport"], result)
        self.assertLess(result["max_speed_px_per_sec"],
                        MAX_JUMP_PX_PER_SEC)

    def test_pocket_rest_follows_owner_hip(self):
        sm = PropStateMachine(PROPS, [], staging=STAGING)
        joints = _joints(hip=(500.0, 620.0))
        x, y, _a, state, _h = sm.transform_at("prop_wallet", 0.0, joints)
        self.assertEqual(state, "WORLD_STATIC")
        self.assertEqual((x, y), (530.0, 580.0))

    def test_ground_only_after_explicit_release(self):
        # A prop whose rest kind is "ground" appears on the ground
        # only after a RELEASE; before that it is held / at rest.
        events = [_event("A1", "PICK_UP", 0.0, 1.0,
                         prop_id="prop_letter"),
                  _event("A2", "RELEASE", 1.0, 2.0,
                         prop_id="prop_letter")]
        sm = PropStateMachine(PROPS, events, staging=STAGING,
                              ground_y=1000.0)
        self.assertNotEqual(sm.state_at("prop_letter", 0.9),
                            "WORLD_STATIC")
        self.assertEqual(sm.rest_kind_at("prop_letter", 2.0), "surface")
        # Without any release event the prop never reaches the
        # ground: it stays at its staged rest.
        sm2 = PropStateMachine(PROPS, [], staging=STAGING,
                               ground_y=1000.0)
        self.assertEqual(sm2.rest_kind_at("prop_letter", 5.0), "surface")


class TestHandover(unittest.TestCase):
    def test_transfer_moves_holder_and_stays_continuous(self):
        events = [
            _event("B1", "PICK_UP", 0.0, 1.0, prop_id="prop_letter"),
            _event("B2", "HAND_OVER", 1.0, 2.0, prop_id="prop_letter",
                   target="CHAR_B"),
        ]
        sm = PropStateMachine(PROPS, events, staging=STAGING,
                              ground_y=1000.0)
        self.assertEqual(sm.detail_at("prop_letter", 0.9)["holder"],
                         "CHAR_A")
        self.assertEqual(sm.state_at("prop_letter", 1.5), "TRANSFERRED")
        self.assertEqual(sm.detail_at("prop_letter", 2.0)["holder"],
                         "CHAR_B")
        samples = []
        for i in range(81):
            t = i / 20.0
            x, y, _a, _s, _h = sm.transform_at(
                "prop_letter", t, _joints())
            samples.append((t, x, y))
        self.assertFalse(sampled_max_jump(samples)["teleport"])
        # The active hand switches at the transfer fraction.
        self.assertEqual(
            sm.transform_at("prop_letter", 1.5, _joints())[4], "r")
        self.assertEqual(
            sm.transform_at("prop_letter", 1.7, _joints())[4], "l")


class TestContactSatisfied(unittest.TestCase):
    def test_pen_tip_on_paper(self):
        event = _event("W1", "WRITE", 1.0, 3.0, prop_id="prop_pen")
        event["contact_points"] = [{
            "joint": "hand_r", "target_kind": "prop_surface",
            "target_id": "prop_letter", "tolerance_px": 6.0}]
        event["required_pose"]["params"]["paper_size"] = (120.0, 80.0)
        offset = pen_tip_position((0.0, 0.0), 1, 560.0)
        hand = (500.0 - offset[0], 800.0 - offset[1])
        joints = {"CHAR_A": {"hand_r": hand, "facing": 1, "_H": 560.0}}
        transforms = {"prop_letter": (500.0, 800.0, 0.0,
                                      "WORLD_STATIC", None)}
        self.assertTrue(contact_satisfied(event, joints, transforms))
        joints_far = {"CHAR_A": {"hand_r": (100.0, 100.0),
                                 "facing": 1, "_H": 560.0}}
        self.assertFalse(contact_satisfied(event, joints_far, transforms))

    def test_hand_prop_and_foot_ground(self):
        event = _event("P1", "PICK_UP", 0.0, 1.0)
        event["contact_points"] = [
            {"joint": "hand_r", "target_kind": "prop",
             "target_id": "prop_wallet", "tolerance_px": 15.0},
            {"joint": "foot_r", "target_kind": "ground",
             "target_id": None, "tolerance_px": 2.0},
        ]
        joints = {"CHAR_A": {"hand_r": (450.0, 700.0),
                             "foot_r": (420.0, 1000.0), "facing": 1}}
        transforms = {"prop_wallet": (455.0, 705.0, 0.0,
                                      "ATTACHED_TO_HAND", "r"),
                      "__ground_y__": 1000.0}
        self.assertTrue(contact_satisfied(event, joints, transforms))
        transforms["prop_wallet"] = (700.0, 700.0, 0.0,
                                     "ATTACHED_TO_HAND", "r")
        self.assertFalse(contact_satisfied(event, joints, transforms))

    def test_character_hand_contact(self):
        event = _event("H1", "HAND_OVER", 1.0, 2.0, prop_id="prop_letter",
                       target="CHAR_B")
        event["contact_points"] = [{
            "joint": "hand_r", "target_kind": "character_hand",
            "target_id": "CHAR_B", "tolerance_px": 30.0}]
        joints = _joints(hand_r=(640.0, 700.0))
        self.assertTrue(contact_satisfied(event, joints, {}))
        joints = _joints(hand_r=(400.0, 700.0))
        self.assertFalse(contact_satisfied(event, joints, {}))

    def test_report_explains_missing_data(self):
        event = _event("P1", "PICK_UP", 0.0, 1.0)
        event["contact_points"] = [{
            "joint": "hand_r", "target_kind": "prop",
            "target_id": "prop_wallet", "tolerance_px": 15.0}]
        report = contact_report(event, _joints(), {})
        self.assertEqual(len(report), 1)
        self.assertFalse(report[0]["satisfied"])
        self.assertIn("no transform", report[0]["reason"])

    def test_no_contact_points_is_vacuously_satisfied(self):
        event = _event("P1", "PICK_UP", 0.0, 1.0)
        self.assertTrue(contact_satisfied(event, _joints(), {}))


class TestSampledMaxJump(unittest.TestCase):
    def test_teleport_detection(self):
        result = sampled_max_jump([(0.0, 0.0, 0.0), (0.04, 500.0, 0.0)])
        self.assertTrue(result["teleport"])
        result = sampled_max_jump([(0.0, 0.0, 0.0), (0.04, 10.0, 0.0)])
        self.assertFalse(result["teleport"])


if __name__ == "__main__":
    unittest.main()
