"""Two-hand handling: a script sentence naming both hands ("bằng hai
tay") must be honored end to end -- the compiler emits hand "both",
the state machine stages HELD_BOTH at the hands' midpoint, the
primitives converge both hands on the prop, the pair animation
receives with both hands, and both audits check EACH hand. Before
this, every such event staged at one hand while the semantic record
said BOTH (the Zeus Cronus receive: semantic BOTH, staged "l").

The "nâng" (lift) vocabulary lands here too: "nâng lõi đá bằng hai
tay" was UNSUPPORTED -- no rule matched bare "nâng" -- so the Fox
lift could never reach the two-hand handling at all.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import (
    _BOTH_HAND_EVENT_TYPES, _classify, _contact_points, _normalize,
    _receive_hand_from_text, _semantic_hand, compile_actions)
from ai_clip_studio.animation.primitives import (
    Stickman, bend_pick, carry_bag, give_to, kneel_pick, pick_up,
    pose_at_completion, present_prop, put_away, receive_prop,
    standing)
from ai_clip_studio.contact_audit import audit_prop_contact
from ai_clip_studio.product_renderer import (
    _event_fn, _render_shot, plan_shots)
from ai_clip_studio.prop_system import (
    PropStateMachine, SemanticPropTracker, contact_report)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.tests.test_insert_two_pass import (
    EXAMPLES, _zeus_package_and_shots)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / \
    "unseen_garden_key.studio.md"


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TestLiftVocabulary(unittest.TestCase):
    def _type(self, sentence):
        return _classify(_normalize(sentence), {})[0]

    def test_nang_core_with_both_hands_is_pick_up(self):
        atype, _cat, _notes, info = _classify(
            _normalize("Cáo nâng lõi đá bằng hai tay."), {})
        self.assertEqual(atype, "PICK_UP")
        self.assertEqual(info["mechanism"], "lift_fallback")

    def test_nang_object_up_is_pick_up(self):
        atype, _cat, _notes, info = _classify(
            _normalize("Nâng hòn đá lên."), {})
        self.assertEqual(atype, "PICK_UP")
        self.assertEqual(info["mechanism"], "discontinuous")

    def test_abstract_nang_stays_unclear(self):
        for sentence in ("Anh ấy nâng cấp vũ khí.",
                         "Cô ấy nâng cao tay.",
                         "Em nâng đỡ bà cụ."):
            with self.subTest(sentence=sentence):
                self.assertIsNone(self._type(sentence))

    def test_nang_hammer_still_strikes(self):
        self.assertEqual(self._type("Ana nâng búa."), "HAMMER_STRIKE")

    def test_semantic_hand_both(self):
        self.assertEqual(
            _semantic_hand(_normalize("nhận bằng hai tay")), "BOTH")
        self.assertEqual(
            _semantic_hand(_normalize("nhận bằng tay phải")), "RIGHT")


class TestReceiveHandFromText(unittest.TestCase):
    def test_two_hand_receive(self):
        self.assertEqual(_receive_hand_from_text(
            "Rhea đưa bọc khăn cho Cronus\n"
            "Cronus nhận bằng hai tay"), "both")

    def test_single_hand_receive(self):
        self.assertEqual(_receive_hand_from_text(
            "Lan đưa thư cho Minh\nMinh nhận bằng tay phải"), "r")

    def test_unmentioned_defaults_left(self):
        self.assertEqual(_receive_hand_from_text(
            "Lan đưa thư cho Minh\nMinh nhận thư"), "l")

    def test_giver_two_hands_does_not_set_receiver(self):
        # The giver offering with both hands must not make the
        # RECEIVER take with both hands.
        self.assertEqual(_receive_hand_from_text(
            "Rhea đưa bọc khăn bằng hai tay cho Cronus\n"
            "Cronus nhận bọc khăn"), "l")


class TestCompilerBothHand(unittest.TestCase):
    def _package_and_events(self, injections):
        text = FIXTURE.read_text(encoding="utf-8")
        for anchor, addition in injections:
            self.assertIn(anchor, text)
            text = text.replace(anchor, anchor + "\n" + addition, 1)
        package = adapt_document(parse_studio_script_v1(text))
        shots = plan_shots(
            package, [{"line_index": i + 1, "duration": 3.0}
                      for i in range(5)])
        spans = {}
        clock = 0.0
        for s in shots:
            did = s.get("directive_shot_id")
            if did:
                span = spans.setdefault(str(did), [clock, clock])
                span[1] = clock + float(s["duration"])
            clock += float(s["duration"])
        events, _unsupported = compile_actions(
            package, timeline={"spans": spans})
        return package, shots, events

    def test_lift_with_both_hands_event(self):
        _pkg, _shots, events = self._package_and_events([
            ("* Bà Tư cúi xuống nhặt chìa khóa lên.",
             "* Bà Tư nhấc chìa khóa lên bằng hai tay."),
        ])
        lifts = [e for e in events
                 if "bằng hai tay" in e["directive_text"]]
        self.assertEqual(len(lifts), 1)
        self.assertEqual(lifts[0]["action_type"], "PICK_UP")
        self.assertEqual(lifts[0]["prop_id"], "prop_key")
        self.assertEqual(
            lifts[0]["required_pose"]["params"]["hand"], "both")
        joints = sorted(cp["joint"]
                        for cp in lifts[0]["contact_points"])
        self.assertEqual(joints, ["hand_l", "hand_r"])

    def test_both_hand_lift_carries_flank_px(self):
        # Round-6: the compiler stamps the prop-sized flank
        # (half the drawn footprint + 6 px) on both-hand events.
        # The fixture key draws at the default 76x50 footprint.
        _pkg, _shots, events = self._package_and_events([
            ("* Bà Tư cúi xuống nhặt chìa khóa lên.",
             "* Bà Tư nhấc chìa khóa lên bằng hai tay."),
        ])
        lifts = [e for e in events
                 if "bằng hai tay" in e["directive_text"]]
        self.assertEqual(len(lifts), 1)
        self.assertEqual(
            lifts[0]["required_pose"]["params"]["flank_px"], 44.0)

    def test_single_hand_lift_carries_no_flank_px(self):
        _pkg, _shots, events = self._package_and_events([
            ("* Bà Tư hơi cúi đầu suy nghĩ.",
             "* Bà Tư nhấc chìa khóa lên."),
        ])
        lifts = [e for e in events
                 if e["directive_text"].strip()
                 == "Bà Tư nhấc chìa khóa lên"]
        self.assertEqual(len(lifts), 1)
        self.assertNotIn(
            "flank_px", lifts[0]["required_pose"]["params"])

    def test_lift_without_mention_stays_right(self):
        _pkg, _shots, events = self._package_and_events([
            ("* Bà Tư hơi cúi đầu suy nghĩ.",
             "* Bà Tư nhấc chìa khóa lên."),
        ])
        # directive_text carries no trailing period (the sentence
        # splitter strips punctuation).
        lifts = [e for e in events
                 if e["directive_text"].strip()
                 == "Bà Tư nhấc chìa khóa lên"]
        self.assertEqual(len(lifts), 1)
        self.assertEqual(
            lifts[0]["required_pose"]["params"]["hand"], "r")

    def test_two_hand_receive_event_and_handover(self):
        _pkg, _shots, events = self._package_and_events([
            ("* Bà Tư nhận bức thư bằng tay trái.",
             "* Bà Tư nhận bức thư bằng hai tay."),
        ])
        receives = [e for e in events
                    if e["action_type"] == "RECEIVE_PROP"]
        by_hand = {e["required_pose"]["params"]["hand"]: e
                   for e in receives}
        # The left-hand receive keeps "l"; the two-hand receive is
        # "both"; the shot's handover names receive_hand "both".
        self.assertIn("l", by_hand)
        self.assertIn("both", by_hand)
        handovers = [e for e in events
                     if e["action_type"] == "HAND_OVER"]
        self.assertEqual(len(handovers), 1)
        self.assertEqual(
            handovers[0]["required_pose"]["params"]["receive_hand"],
            "both")

    def test_pen_verbs_excluded_from_both_gate(self):
        for verb in ("WRITE", "SIGN", "HOLD_PEN"):
            self.assertNotIn(verb, _BOTH_HAND_EVENT_TYPES)
        for verb in ("PICK_UP", "RECEIVE_PROP", "CARRY",
                     "BEND_PICK", "KNEEL_PICK"):
            self.assertIn(verb, _BOTH_HAND_EVENT_TYPES)


class TestContactPointsBoth(unittest.TestCase):
    def test_pick_up_both_yields_two_points(self):
        pts = _contact_points("PICK_UP", "both", "p1", None, None)
        self.assertEqual([p["joint"] for p in pts],
                         ["hand_l", "hand_r"])
        self.assertTrue(all(p["tolerance_px"] == 15.0 for p in pts))

    def test_pick_up_single_yields_one_point(self):
        pts = _contact_points("PICK_UP", "r", "p1", None, None)
        self.assertEqual([p["joint"] for p in pts], ["hand_r"])

    def test_handover_target_hand_both_passes_through(self):
        pts = _contact_points("HAND_OVER", "r", "p1", "CHAR_B", None,
                              target_hand="both")
        hand_pts = [p for p in pts
                    if p["target_kind"] == "character_hand"]
        self.assertEqual(hand_pts[0]["target_hand"], "both")


class TestBothHandPrimitives(unittest.TestCase):
    def _char(self, name="T"):
        char = Stickman(height=560, name=name)
        standing(char, 500, 900)
        return char

    def test_pick_up_both_hands_flank_the_hold(self):
        char = self._char()
        joints = pose_at_completion(
            pick_up(char, (600, 700), 1.0, 900, hand="both"),
            char, 1.0)
        self.assertAlmostEqual(
            _dist(joints["hand_l"], joints["hand_r"]), 24.0, delta=1.0)
        mid = ((joints["hand_l"][0] + joints["hand_r"][0]) / 2.0,
               (joints["hand_l"][1] + joints["hand_r"][1]) / 2.0)
        self.assertAlmostEqual(mid[0], 540.0, delta=2.0)

    def test_pick_up_flank_px_spreads_hands_to_prop_edges(self):
        # Round-6: with flank_px the hands end one flank width
        # either side of the hold -- the prop's edges, not its
        # centre -- so both hands read at production scale.
        char = Stickman(height=560, name="T")
        standing(char, 400, 500)
        fn = pick_up(char, (450, 480), 1.0, 500, hand="both",
                     flank_px=61.0)
        joints = pose_at_completion(fn, char, 1.0)
        spread = abs(joints["hand_r"][0] - joints["hand_l"][0])
        self.assertAlmostEqual(spread, 122.0, places=0)

    def test_present_prop_flank_px_spreads_hold(self):
        char = Stickman(height=560, name="T")
        standing(char, 400, 500)
        fn = present_prop(char, 1.0, hand="both", flank_px=44.0)
        joints = pose_at_completion(fn, char, 1.0)
        spread = abs(joints["hand_r"][0] - joints["hand_l"][0])
        # The hold sits 130 px forward of the chest, so the far
        # hand's flanked target exceeds arm reach and the IK clamp
        # trims the spread (76.9 measured) below the nominal 88.
        # The assertion pins the widened hold against the legacy
        # 24 px spread, not the unreachable nominal width.
        self.assertGreater(spread, 70.0)

    def test_pick_up_single_hand_unchanged(self):
        char = self._char()
        joints = pose_at_completion(
            pick_up(char, (600, 700), 1.0, 900, hand="r"), char, 1.0)
        self.assertAlmostEqual(joints["hand_r"][0], 540.0, delta=2.0)
        # The idle left hand stays ~95 px from the hold: it did not
        # travel with the right hand (contrast: 24 px for "both").
        self.assertGreater(_dist(joints["hand_l"], joints["hand_r"]),
                           60.0)

    def test_receive_prop_both(self):
        char = self._char()
        joints = pose_at_completion(
            receive_prop(char, (620, 650), 1.0, hand="both"),
            char, 1.0)
        self.assertAlmostEqual(
            _dist(joints["hand_l"], joints["hand_r"]), 24.0, delta=1.0)

    def test_put_away_both_prop_follows_midpoint(self):
        char = self._char()
        prop = {}
        pose_at_completion(
            put_away(char, (520, 800), 1.0, hand="both", prop=prop),
            char, 1.0)
        self.assertEqual((prop["x"], prop["y"]), (520, 800))
        self.assertTrue(prop["released"])

    def test_carry_bag_both_hangs_from_midpoint(self):
        char = self._char()
        bag = {}
        joints = pose_at_completion(
            carry_bag(char, 1.0, hand="both", bag=bag), char, 1.0)
        # The bag hangs from the carry TARGET midpoint (hip + 45
        # forward, 68 down), not from the clamped hand joints: the
        # carry point sits past arm reach, so the IK clamps the
        # joints ~46 px short -- pre-existing hanging-carry
        # geometry, documented by the contact audit's bag gap.
        hip = joints["hip"]
        self.assertLess(abs(bag["x"] - (hip[0] + 45.0)), 12.0)
        self.assertAlmostEqual(bag["y"], hip[1] + 136.0, delta=3.0)
        # Both hands converged on the carry point (flanked).
        self.assertLess(
            _dist(joints["hand_l"], joints["hand_r"]), 30.0)

    def test_bend_pick_both(self):
        char = self._char()
        joints = pose_at_completion(
            bend_pick(char, (600, 894), 1.2, 900, hand="both"),
            char, 1.2)
        self.assertAlmostEqual(
            _dist(joints["hand_l"], joints["hand_r"]), 24.0, delta=1.0)

    def test_kneel_pick_both(self):
        char = self._char()
        joints = pose_at_completion(
            kneel_pick(char, (600, 894), 1.2, 900, hand="both"),
            char, 1.2)
        self.assertAlmostEqual(
            _dist(joints["hand_l"], joints["hand_r"]), 24.0, delta=1.0)

    def test_give_to_both_receiver_hands_converge(self):
        giver = Stickman(height=560, name="G")
        standing(giver, 400, 900)
        receiver = Stickman(height=560, name="R")
        standing(receiver, 700, 900)
        give_to(giver, receiver, {"x": 0, "y": 0}, 1.0,
                receive_hand="both")(1.0)
        joints = receiver.joints()
        self.assertLess(
            _dist(joints["hand_l"], joints["hand_r"]), 30.0)

    def test_give_to_single_hand_leaves_other_hand(self):
        giver = Stickman(height=560, name="G")
        standing(giver, 400, 900)
        receiver = Stickman(height=560, name="R")
        standing(receiver, 700, 900)
        give_to(giver, receiver, {"x": 0, "y": 0}, 1.0,
                receive_hand="l")(1.0)
        joints = receiver.joints()
        self.assertGreater(
            _dist(joints["hand_l"], joints["hand_r"]), 100.0)


class TestMachineBothHand(unittest.TestCase):
    def _event(self, action_id, action_type, start, end, hand="r",
               extra=None):
        params = {"hand": hand}
        if extra:
            params.update(extra)
        return {"action_id": action_id, "actor_id": "CHAR_A",
                "action_type": action_type, "target_id": None,
                "prop_id": "prop_wallet", "start_time": start,
                "end_time": end,
                "required_pose": {"pose": "x", "params": params},
                "contact_points": []}

    def test_held_both_draws_at_hands_midpoint(self):
        props = [{"id": "prop_wallet", "kind": "wallet",
                  "owner": "CHAR_A"}]
        events = [self._event("A1", "PICK_UP", 1.0, 2.0, hand="both")]
        sm = PropStateMachine(
            props, events,
            staging={"prop_wallet": {"kind": "pocket",
                                     "anchor_id": "CHAR_A",
                                     "offset": (30.0, -40.0)}},
            ground_y=1000.0)
        joints = {"CHAR_A": {"hip": (400.0, 600.0),
                             "hand_r": (450.0, 700.0),
                             "hand_l": (380.0, 700.0), "facing": 1}}
        x, y, _ang, state, hand = sm.transform_at(
            "prop_wallet", 1.6, joints)
        self.assertEqual(state, "ATTACHED_TO_HAND")
        self.assertEqual(hand, "both")
        self.assertAlmostEqual(x, 415.0)
        self.assertAlmostEqual(y, 700.0)

    def test_held_both_location(self):
        props = [{"id": "prop_wallet", "kind": "wallet",
                  "owner": "CHAR_A"}]
        events = [self._event("A1", "PICK_UP", 1.0, 2.0, hand="both")]
        tracker = SemanticPropTracker(props, events)
        self.assertEqual(tracker.location_at("prop_wallet", 1.6),
                         "HELD_BOTH")

    def test_transfer_to_both_lands_at_midpoint(self):
        props = [{"id": "prop_wallet", "kind": "wallet",
                  "owner": "CHAR_A"}]
        events = [self._event("A1", "HAND_OVER", 1.0, 2.0, hand="r",
                              extra={"receive_hand": "both"})]
        events[0]["target_id"] = "CHAR_B"
        sm = PropStateMachine(props, events, staging={}, ground_y=1000.0)
        joints = {"CHAR_A": {"hip": (400.0, 600.0),
                             "hand_r": (450.0, 700.0),
                             "hand_l": (380.0, 700.0), "facing": 1},
                  "CHAR_B": {"hip": (700.0, 600.0),
                             "hand_r": (680.0, 700.0),
                             "hand_l": (650.0, 700.0), "facing": -1}}
        # Past the transfer moment the prop is attached to the
        # receiver's pair midpoint (665, 700).
        x, y, _ang, state, hand = sm.transform_at(
            "prop_wallet", 2.0, joints)
        self.assertEqual(state, "ATTACHED_TO_HAND")
        self.assertEqual(hand, "both")
        self.assertAlmostEqual(x, 665.0)
        self.assertAlmostEqual(y, 700.0)


class TestContactReportBoth(unittest.TestCase):
    def test_target_hand_both_measures_pair_midpoint(self):
        event = {"action_id": "H1", "actor_id": "CHAR_A",
                 "action_type": "HAND_OVER", "target_id": "CHAR_B",
                 "prop_id": "prop_letter", "start_time": 1.0,
                 "end_time": 2.0,
                 "required_pose": {"pose": "x", "params": {}},
                 "contact_points": [{
                     "joint": "hand_r",
                     "target_kind": "character_hand",
                     "target_id": "CHAR_B", "tolerance_px": 30.0,
                     "target_hand": "both"}]}
        # Giver hand at the pair midpoint (665, 700): satisfied.
        joints = {"CHAR_A": {"hip": (400.0, 600.0),
                             "hand_r": (665.0, 700.0),
                             "hand_l": (380.0, 700.0), "facing": 1},
                  "CHAR_B": {"hip": (700.0, 600.0),
                             "hand_r": (680.0, 700.0),
                             "hand_l": (650.0, 700.0), "facing": -1}}
        report = contact_report(event, joints, {})
        self.assertTrue(report[0]["satisfied"])
        self.assertAlmostEqual(report[0]["measured"], 0.0)
        # Giver hand 40 px from the midpoint: fails even though it
        # is 25 px from the nearer hand (the nearer-hand shortcut
        # must not apply to a named pair).
        joints["CHAR_A"]["hand_r"] = (625.0, 700.0)
        report = contact_report(event, joints, {})
        self.assertFalse(report[0]["satisfied"])
        self.assertAlmostEqual(report[0]["measured"], 40.0)


def _audit_hands(hand_l=(488.0, 500.0), hand_r=(512.0, 500.0)):
    return {"An": {"hand_l": list(hand_l), "hand_r": list(hand_r),
                   "elbow_l": [488.0, 400.0],
                   "elbow_r": [512.0, 400.0],
                   "head_r": 95.0, "H": 560.0}}


def _audit_draw(hand="both", x=500.0, y=500.0):
    return {"pid": "PROP_WALLET", "kind": "wallet",
            "state": "ATTACHED_TO_HAND", "holder": "An", "hand": hand,
            "x": x, "y": y, "angle": 0.0, "open_u": 0.0,
            "grip_repaint": True}


def _audit_job(tmp, telemetry, events):
    root = Path(tmp)
    (root / "frames").mkdir()
    (root / "frames" / "motion_report.json").write_text(json.dumps({
        "fps": 24, "total_frames": len(telemetry),
        "shots": [{"index": 0, "grip_telemetry": telemetry}]}),
        encoding="utf-8")
    (root / "action_events.json").write_text(
        json.dumps({"events": events, "unsupported": []}),
        encoding="utf-8")
    (root / "scene_package.json").write_text(json.dumps({
        "v1_characters": [{"id": "CHAR_A", "name": "An"}],
        "props": [{"id": "PROP_WALLET", "kind": "wallet"}]}),
        encoding="utf-8")
    return root


class TestAuditBothHand(unittest.TestCase):
    def _event(self):
        return {"action_id": "E1", "action_type": "HOLD",
                "actor_id": "CHAR_A", "prop_id": "PROP_WALLET",
                "start_time": 0.0, "end_time": 1.0}

    def test_both_hands_gripping_passes(self):
        telemetry = [{"t": round(i / 24.0, 4), "frame": i,
                      "hands": _audit_hands(),
                      "draws": [_audit_draw()]}
                     for i in range(24)]
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_prop_contact(
                _audit_job(tmp, telemetry, [self._event()]))
        self.assertTrue(report["passed"], report["failures"])
        item = report["interactions"][0]
        self.assertEqual(item["metrics"]["gap_within_limit"], 1.0)
        self.assertEqual(item["metrics"]["gap_px_mean"], 12.0)

    def test_one_hand_off_fails_gap(self):
        telemetry = [{"t": round(i / 24.0, 4), "frame": i,
                      "hands": _audit_hands(hand_l=(200.0, 500.0)),
                      "draws": [_audit_draw()]}
                     for i in range(24)]
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_prop_contact(
                _audit_job(tmp, telemetry, [self._event()]))
        self.assertFalse(report["passed"])
        item = report["interactions"][0]
        self.assertEqual(item["metrics"]["gap_within_limit"], 0.5)
        self.assertTrue(any("grip gap" in f for f in item["failures"]))


class TestRenderBothHand(unittest.TestCase):
    def test_cronus_two_hand_receive_converges(self):
        # Zeus SC03_SH04, rendered: Cronus receives "bằng hai tay".
        # At the end of the shot both of his hands must sit together
        # at the meeting point (before the fix the right hand hung
        # at his side, 150+ px from the left).
        package, shots = _zeus_package_and_shots()
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC03_SH04")
        events = [e for e in
                  package["compiled_actions"]["events"]
                  if e.get("shot_id") == "SC03_SH04"
                  and e["action_type"] == "RECEIVE_PROP"]
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["required_pose"]["params"]["hand"], "both")
        handovers = [e for e in
                     package["compiled_actions"]["events"]
                     if e.get("shot_id") == "SC03_SH04"
                     and e["action_type"] == "HAND_OVER"]
        self.assertEqual(
            handovers[0]["required_pose"]["params"]["receive_hand"],
            "both")
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot(
                {"shot": shot, "package": package, "out_dir": tmp})
        telemetry = result["grip_telemetry"]
        self.assertTrue(telemetry)
        last = telemetry[-1]["hands"]["Cronus"]
        spread = _dist(last["hand_l"], last["hand_r"])
        self.assertLess(spread, 60.0, f"hand spread {spread}")

    def test_fixture_two_hand_lift_draws_at_midpoint(self):
        # The lift goes in SC01_SH01, where the key is still in the
        # pocket: the shot-scoped tracker forbids a TAKE of an
        # already-held prop, and SC01_SH03 already picks the key up.
        text = FIXTURE.read_text(encoding="utf-8")
        anchor = "* Bà Tư hơi cúi đầu suy nghĩ."
        text = text.replace(
            anchor, anchor + "\n* Bà Tư nhấc chìa khóa lên bằng hai tay.",
            1)
        package = adapt_document(parse_studio_script_v1(text))
        shots = plan_shots(
            package, [{"line_index": i + 1, "duration": 3.0}
                      for i in range(5)])
        for i, s in enumerate(shots):
            s["index"] = i
        spans = {}
        clock = 0.0
        for s in shots:
            did = s.get("directive_shot_id")
            if did:
                span = spans.setdefault(str(did), [clock, clock])
                span[1] = clock + float(s["duration"])
            clock += float(s["duration"])
        events, unsupported = compile_actions(
            package, timeline={"spans": spans})
        package["compiled_actions"] = {
            "events": events, "unsupported": unsupported,
            "spans_supplied": True, "compile_error": None,
        }
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC01_SH01")
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot(
                {"shot": shot, "package": package, "out_dir": tmp})
        held = [(rec, d) for rec in result["grip_telemetry"]
                for d in rec["draws"]
                if d.get("pid") == "prop_key"
                and d.get("state") in ("GRASPED", "ATTACHED_TO_HAND",
                                       "IN_USE")]
        self.assertTrue(held, "no held key draws in the shot")
        both = [d for _rec, d in held if d.get("hand") == "both"]
        self.assertTrue(both, "no HELD_BOTH key draws in the shot")
        for rec, draw in held:
            hands = rec["hands"].get(draw.get("holder") or "")
            if not hands or draw.get("hand") != "both":
                continue
            mid = ((hands["hand_l"][0] + hands["hand_r"][0]) / 2.0,
                   (hands["hand_l"][1] + hands["hand_r"][1]) / 2.0)
            self.assertLess(_dist((draw["x"], draw["y"]), mid), 30.0)


class TestMeetingHeight(unittest.TestCase):
    """Handovers meet at elbow/chest height, not neck height.

    The old meeting point (gy - 180s) sat ~35 px above the
    shoulder, so inserts around a handover framed two faces
    instead of the prop. The meeting point must sit below the
    chin, in the elbow/chest band.
    """

    def test_hands_meet_below_chin(self):
        giver = Stickman(height=560, name="Giver")
        receiver = Stickman(height=560, name="Receiver")
        standing(giver, 400, 720, facing=1)
        standing(receiver, 660, 720, facing=-1)
        prop = {"x": 0.0, "y": 0.0}
        fn = give_to(giver, receiver, prop, 1.0, receive_hand="r")
        fn(0.0)
        fn(1.0)
        joints = giver.joints()
        gy = giver.pose["root_y"]
        hand_y = joints["hand_r"][1]
        self.assertGreater(hand_y, gy - 140.0)
        self.assertLess(hand_y, gy - 60.0)
        head_y = joints["head"][1]
        head_r = 0.17 * 560.0
        self.assertGreater(hand_y, head_y + head_r)


class TestGiveToRelease(unittest.TestCase):
    """A completed transfer releases the receiver.

    The sequencer holds the pair fn at its end pose after the
    pair window; before the release, that hold re-asserted the
    receiver's hand at the meeting point every frame, so the
    receive window's pull-in never took effect (the hand froze
    mid-air for the rest of the shot).
    """

    def test_plateau_drives_giver_only(self):
        giver = Stickman(height=560, name="Giver")
        receiver = Stickman(height=560, name="Receiver")
        standing(giver, 400, 720, facing=1)
        standing(receiver, 660, 720, facing=-1)
        prop = {"x": 0.0, "y": 0.0}
        fn = give_to(giver, receiver, prop, 1.0, receive_hand="r")
        fn(0.0)
        fn(0.5)
        fn(1.0)
        meeting = giver.hand_target_r
        # The first completion call drives the receiver too.
        self.assertLess(_dist(receiver.hand_target_r, meeting), 2.0)
        # The receiver's next window takes over the hand...
        receiver.hand_target_r = (650.0, 600.0)
        # ...and the pair fn's end-pose hold must not take it back.
        fn(1.0)
        self.assertEqual(receiver.hand_target_r, (650.0, 600.0))
        self.assertEqual(giver.hand_target_r, meeting)


class TestReceiveWiring(unittest.TestCase):
    """RECEIVE_PROP dispatches to receive_prop in the product path.

    The primitive was dead there: _event_fn had no branch, so
    receive windows fell back to idle. target=None means the
    pair animation already placed the hand at the meeting point.
    """

    def test_event_fn_receive_prop_pulls_in(self):
        char = Stickman(height=560, name="Receiver")
        standing(char, 500, 720, facing=1)
        ctx = {"char": char, "ground_y": 720.0}
        fn = _event_fn("receive_prop", {"hand": "r"}, {}, ctx, 1.0)
        self.assertIsNotNone(fn)
        # A reachable meeting point (the pair animation only ever
        # places the hand inside arm reach).
        char.hand_target_r = (560.0, 470.0)
        fn(0.0)
        start = char.joints()["hand_r"]
        fn(1.0)
        pull = _dist(char.joints()["hand_r"], start)
        self.assertGreater(pull, 5.0)
        self.assertLess(pull, 40.0)

    def test_event_fn_receive_prop_both_converges(self):
        char = Stickman(height=560, name="Receiver")
        standing(char, 500, 720, facing=1)
        ctx = {"char": char, "ground_y": 720.0}
        fn = _event_fn("receive_prop", {"hand": "both"}, {}, ctx, 1.0)
        self.assertIsNotNone(fn)
        char.hand_target_l = (560.0, 470.0)
        char.hand_target_r = (560.0, 470.0)
        fn(0.0)
        fn(1.0)
        joints = char.joints()
        self.assertAlmostEqual(
            _dist(joints["hand_l"], joints["hand_r"]), 24.0, delta=2.0)


class TestRenderTransfer(unittest.TestCase):
    """The full transfer on a real shot: meet, then pull in.

    Zeus SC08_SH02 with the compiler's sequential event times:
    the hands meet, the receiver pulls the bolt toward the body
    while the giver's hand stays at the meeting point, and the
    bolt follows the receiver's hand.
    """

    def test_bolt_transfer_meets_then_pulls_in(self):
        package = adapt_document(parse_studio_script_v1(
            (EXAMPLES / "zeus_ep01_fall_of_cronus.studio.md").read_text(
                encoding="utf-8")))
        shots = plan_shots(
            package, [{"line_index": i + 1, "duration": 3.0}
                      for i in range(40)])
        for i, s in enumerate(shots):
            s["index"] = i
        spans = {}
        clock = 0.0
        for s in shots:
            did = s.get("directive_shot_id")
            if did:
                span = spans.setdefault(str(did), [clock, clock])
                span[1] = clock + float(s["duration"])
            clock += float(s["duration"])
        events, _unsupported = compile_actions(
            package, timeline={"spans": spans})
        package["compiled_actions"] = {
            "events": events, "unsupported": _unsupported,
            "spans_supplied": True, "compile_error": None,
        }
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC08_SH02")
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot({"shot": shot, "package": package,
                                   "out_dir": tmp})
        tel = result["grip_telemetry"]
        self.assertGreater(len(tel), 60)

        def _hands(rec, name):
            return rec["hands"].get(name) or {}

        # Meeting frame: the smallest giver/receiver hand gap in
        # the first half of the shot.
        meet_i, meet_gap = 0, float("inf")
        for i, rec in enumerate(tel[: len(tel) // 2]):
            zh = _hands(rec, "Zeus")
            ch = _hands(rec, "Cyclopes")
            if not zh or not ch:
                continue
            gap = _dist(zh["hand_r"], ch["hand_r"])
            if gap < meet_gap:
                meet_i, meet_gap = i, gap
        self.assertLess(meet_gap, 15.0)
        meet = tel[meet_i]
        meet_pos = _hands(meet, "Zeus")["hand_r"]
        meet_hip_dist = _dist(
            meet_pos, _hands(meet, "Zeus")["hip"])
        late = tel[-1]
        late_pos = _hands(late, "Zeus")["hand_r"]
        # The receiver pulled the bolt toward the body...
        self.assertLess(
            _dist(late_pos, _hands(late, "Zeus")["hip"]),
            meet_hip_dist - 5.0)
        # ...while the giver's hand stayed at the meeting point...
        self.assertLess(
            _dist(_hands(late, "Cyclopes")["hand_r"], meet_pos), 5.0)
        # ...and the bolt follows the receiver's hand.
        draws = [d for d in (late.get("draws") or [])
                 if d.get("kind") == "bolt"]
        self.assertEqual(len(draws), 1)
        self.assertLess(
            _dist((draws[0]["x"], draws[0]["y"]), late_pos), 5.0)


if __name__ == "__main__":
    unittest.main()
