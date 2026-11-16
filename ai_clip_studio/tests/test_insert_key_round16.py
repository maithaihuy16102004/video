"""Round 16 (L02-D2): key-into-lock -- INSERT_KEY verb, the "lock"
prop kind, the insert_key primitive, the lock target assembly, the
prop-machine INSERT_KEY markers + seed-shadow fix, and the ECU
prop-action framing deferral.

The R15 ECU of "the brass key goes into the coop lock" framed An's
face: the action sentence was UNSUPPORTED, so no event existed and
the ECU branch framed the head box. R16-2b compiles the sentence,
stages a padlock on a coop-door panel at a reachable anchor, drives
the hand (and the key) into it, and defers the ECU crop to the
prop-action telemetry -- the face must not define the frame.
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.action_compiler import (
    ACTION_TYPES, PRIMITIVE_MAP, _classify, _normalize, compile_actions)
from ai_clip_studio.animation.character_art import STYLE_LOCK
from ai_clip_studio.animation.primitives import (
    PRIMITIVES, PRIMITIVE_COMPLETION, insert_key, standing)
from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.product_renderer import (
    PROP_KINDS, _build_shot_prop_machine, _draw_prop,
    _lock_events_at_start, _render_shot, infer_prop_kind)
from ai_clip_studio.prop_system import PropStateMachine
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.trait_derivation import derive_prop_kind

AGENT = Path(__file__).resolve().parent.parent.parent
JOB = AGENT / "jobs" / "req_80be4e5ca4dd"
BRASS = np.array([203, 160, 72])
WOOD = np.array([150, 110, 70])
FACE_FILL = tuple(int(STYLE_LOCK["face_fill"][i:i + 2], 16)
                  for i in (1, 3, 5))


class TestInsertKeyClassification(unittest.TestCase):
    def _type(self, sentence):
        return _classify(_normalize(sentence), {})[0]

    def test_ecu_sentence_compiles(self):
        self.assertEqual(
            self._type("Chiếc chìa khóa đồng tra vào ổ khóa chuồng gà"),
            "INSERT_KEY")

    def test_key_phrases(self):
        for s in ("An mở khóa", "An vặn chìa khóa",
                  "Bà Tư xoay chìa khóa", "An cắm chìa khóa vào ổ",
                  "She inserts the key into the lock",
                  "He turns the key"):
            with self.subTest(sentence=s):
                self.assertEqual(self._type(s), "INSERT_KEY")

    def test_course_guard(self):
        self.assertNotEqual(
            self._type("Mở khóa học trực tuyến"), "INSERT_KEY")

    def test_no_false_positives(self):
        # "trao cho" (hand over) shares the "tra" onset; "mở rộng"
        # (widen) shares "mở". Neither is a key insert.
        self.assertEqual(
            self._type("An trao chìa khóa cho bà Tư"), "HAND_OVER")
        self.assertNotEqual(
            self._type("An mở rộng vòng tay"), "INSERT_KEY")

    def test_registry_totality(self):
        self.assertIn("INSERT_KEY", ACTION_TYPES)
        self.assertEqual(
            PRIMITIVE_MAP["INSERT_KEY"],
            ("insert_key", 1.2, "OBJECT_STATE_CHANGED"))


class TestLockKind(unittest.TestCase):
    def test_derive_prop_kind(self):
        self.assertEqual(derive_prop_kind("Ổ khóa", ""), "lock")
        self.assertEqual(derive_prop_kind("Khóa cửa", ""), "lock")
        self.assertEqual(derive_prop_kind("Padlock", ""), "lock")
        # Longest match: "chìa khóa" (a key) beats bare "khóa".
        self.assertEqual(
            derive_prop_kind("Chiếc chìa khóa đồng", ""), "key")

    def test_infer_prop_kind(self):
        self.assertEqual(infer_prop_kind({"name": "Ổ khóa"}), "lock")
        self.assertEqual(infer_prop_kind({"name": "Chìa khóa"}), "key")
        self.assertEqual(
            infer_prop_kind({"kind": "lock", "name": "Xyzzy"}), "lock")

    def test_lock_in_prop_kinds(self):
        self.assertIn("lock", PROP_KINDS)

    def test_lock_draws_and_opens(self):
        closed = Image.new("RGB", (200, 240), (255, 255, 255))
        _draw_prop(ImageDraw.Draw(closed), 100, 120, kind="lock")
        opened = Image.new("RGB", (200, 240), (255, 255, 255))
        _draw_prop(ImageDraw.Draw(opened), 100, 120, kind="lock",
                   open_u=1.0)
        a = np.asarray(closed).astype(int)
        b = np.asarray(opened).astype(int)
        # Non-blank, brass present, and the shackle moves.
        self.assertGreater((np.abs(a - 255).sum(axis=2) > 30).sum(),
                           1000)
        self.assertGreater((np.abs(a - BRASS).sum(axis=2) < 40).sum(),
                           200)
        self.assertGreater((np.abs(a - b).sum(axis=2) > 30).sum(), 100)


class TestInsertKeyPrimitive(unittest.TestCase):
    def _char_at(self):
        ch = Stickman(height=780)
        standing(ch, 960, 900, facing=1)
        return ch

    def test_hand_reaches_and_holds_the_lock(self):
        ch = self._char_at()
        target = (960 + 180, 900 - 420)
        fn = insert_key(ch, target, 1.2, hand="r")
        fn(1.2)
        hand = ch.joints()["hand_r"]
        # The completion pose is the INSERTED point (a few px past
        # the lock face along the facing direction).
        self.assertLess(math.hypot(hand[0] - target[0],
                                   hand[1] - target[1]), 20.0)

    def test_turn_phase_moves_the_hand(self):
        ch = self._char_at()
        target = (960 + 180, 900 - 420)
        fn = insert_key(ch, target, 1.2, hand="r")
        fn(0.62 * 1.2)
        early = ch.joints()["hand_r"]
        fn(0.80 * 1.2)
        mid = ch.joints()["hand_r"]
        self.assertGreater(math.hypot(mid[0] - early[0],
                                      mid[1] - early[1]), 4.0)
        fn(1.2)
        end = ch.joints()["hand_r"]
        # The turn closes back to the inserted point.
        self.assertLess(math.hypot(end[0] - target[0],
                                   end[1] - target[1]), 20.0)

    def test_head_tracks_the_lock(self):
        ch = self._char_at()
        fn = insert_key(ch, (1140, 480), 1.2, hand="r")
        fn(1.2)
        self.assertGreater(abs(ch.pose.get("head_look", 0.0)), 0.05)

    def test_registered(self):
        self.assertIn("insert_key", PRIMITIVES)
        self.assertIn("insert_key", PRIMITIVE_COMPLETION)


class TestLockEventsAtStart(unittest.TestCase):
    def _ev(self, aid, shot_id, end, actor="CHAR_AN", trusted=True):
        return {"action_id": aid, "shot_id": shot_id,
                "actor_id": actor, "start_time": end - 1.0,
                "end_time": end,
                "required_pose": {"primitive": "insert_key"},
                "span_source": "supplied" if trusted else "estimated"}

    def test_same_scene_open_lock_returned(self):
        ev = self._ev("E1", "SC06_SH01", 70.0)
        out = _lock_events_at_start(
            [ev], 6, 71.0, {"CHAR_AN": "An"})
        self.assertEqual(out, {"An": ev})

    def test_other_scene_excluded(self):
        ev = self._ev("E1", "SC05_SH01", 70.0)
        out = _lock_events_at_start(
            [ev], 6, 71.0, {"CHAR_AN": "An"})
        self.assertEqual(out, {})

    def test_untrusted_times_excluded(self):
        ev = self._ev("E1", "SC06_SH01", 70.0, trusted=False)
        out = _lock_events_at_start(
            [ev], 6, 71.0, {"CHAR_AN": "An"})
        self.assertEqual(out, {})

    def test_latest_wins(self):
        early = self._ev("E1", "SC06_SH01", 60.0)
        late = self._ev("E2", "SC06_SH02", 70.0)
        out = _lock_events_at_start(
            [early, late], 6, 71.0, {"CHAR_AN": "An"})
        self.assertEqual(out, {"An": late})


def _mini_event(action_id, action_type, actor, prop, start, end,
                hand="r", target=None, primitive=None):
    return {"action_id": action_id, "action_type": action_type,
            "actor_id": actor, "target_id": target, "prop_id": prop,
            "start_time": start, "end_time": end,
            "required_pose": {
                "primitive": primitive or action_type.lower(),
                "params": {"hand": hand}},
            "shot_id": "SC06_SH01", "span_source": "supplied"}


class TestMachineInsertKey(unittest.TestCase):
    KEY = {"id": "key1", "name": "Chìa khóa", "kind": "key"}
    STAGING = {"key1": {"x": 0.0, "y": 0.0, "angle": 0.0,
                        "kind": "point"}}
    JOINTS = {
        "CHAR_AN": {"hand_l": (100.0, 100.0), "hand_r": (300.0, 200.0)},
        "CHAR_BA_TU": {"hand_l": (500.0, 100.0),
                       "hand_r": (700.0, 200.0)},
    }

    def test_insert_markers_follow_the_hand(self):
        ev = _mini_event("E1", "INSERT_KEY", "CHAR_AN", "key1",
                         10.0, 11.2, primitive="insert_key")
        m = PropStateMachine([self.KEY], [ev], staging=self.STAGING,
                             ground_y=None)
        states = [mk[1] for mk in m._markers["key1"]]
        self.assertEqual(states, ["IN_USE", "ATTACHED_TO_HAND"])
        x, y, _a, state, hand = m.transform_at(
            "key1", 10.6, self.JOINTS)
        self.assertEqual((x, y), (300.0, 200.0))
        self.assertEqual(state, "IN_USE")
        self.assertEqual(hand, "r")

    def test_insert_overrides_the_previous_holder(self):
        hold = _mini_event("E0", "HOLD", "CHAR_BA_TU", "key1",
                           5.0, 6.0, primitive="pick_up")
        ev = _mini_event("E1", "INSERT_KEY", "CHAR_AN", "key1",
                         10.0, 11.2, primitive="insert_key")
        m = PropStateMachine([self.KEY], [hold, ev],
                             staging=self.STAGING, ground_y=None)
        x, y, _a, _s, _h = m.transform_at("key1", 10.6, self.JOINTS)
        self.assertEqual((x, y), (300.0, 200.0))
        self.assertTrue(any("overrides holder" in str(d.get("issue"))
                            for d in m.diagnostics))

    def test_seed_skipped_when_insert_starts_at_shot_start(self):
        # The seed-shadow defect: the seeded hold's ATTACHED
        # marker (t0 + 0.006) shadowed the insert's IN_USE marker
        # (t0) and drew the key at the previous holder's hand.
        t0 = 70.27
        handover = _mini_event(
            "H0", "HAND_OVER", "CHAR_AN", "key1", 60.0, 61.0,
            target="CHAR_BA_TU", primitive="hand_over")
        insert = _mini_event("E1", "INSERT_KEY", "CHAR_AN", "key1",
                             t0, t0 + 1.2, primitive="insert_key")
        package = {
            "props": [self.KEY],
            "characters": [{"name": "An", "id": "CHAR_AN"},
                           {"name": "Bà Tư", "id": "CHAR_BA_TU"}],
            "compiled_actions": {"events": [handover, insert]},
        }
        shot = {"props": ["key1"], "prop_holders": {}}
        id_to_name = {"CHAR_AN": "An", "CHAR_BA_TU": "Bà Tư"}
        name_to_id = {"An": "CHAR_AN", "Bà Tư": "CHAR_BA_TU"}
        machine, _p, _k, _r, _d = _build_shot_prop_machine(
            package, shot, [insert], {"key1": (0.0, 0.0)}, {},
            {}, id_to_name, name_to_id, {"An", "Bà Tư"}, t0)
        self.assertIsNotNone(machine)
        seed = [mk for mk in machine._markers["key1"]
                if str((mk[2].get("event") or {}).get("action_id")
                       or "").startswith("SEED_HOLD")]
        self.assertEqual(seed, [])

    def test_seed_kept_for_a_mid_shot_insert(self):
        t0 = 70.27
        handover = _mini_event(
            "H0", "HAND_OVER", "CHAR_AN", "key1", 60.0, 61.0,
            target="CHAR_BA_TU", primitive="hand_over")
        insert = _mini_event("E1", "INSERT_KEY", "CHAR_AN", "key1",
                             t0 + 0.5, t0 + 1.7,
                             primitive="insert_key")
        package = {
            "props": [self.KEY],
            "characters": [{"name": "An", "id": "CHAR_AN"},
                           {"name": "Bà Tư", "id": "CHAR_BA_TU"}],
            "compiled_actions": {"events": [handover, insert]},
        }
        shot = {"props": ["key1"], "prop_holders": {}}
        id_to_name = {"CHAR_AN": "An", "CHAR_BA_TU": "Bà Tư"}
        name_to_id = {"An": "CHAR_AN", "Bà Tư": "CHAR_BA_TU"}
        machine, _p, _k, _r, _d = _build_shot_prop_machine(
            package, shot, [insert], {"key1": (0.0, 0.0)}, {},
            {}, id_to_name, name_to_id, {"An", "Bà Tư"}, t0)
        self.assertIsNotNone(machine)
        seed = [mk for mk in machine._markers["key1"]
                if str((mk[2].get("event") or {}).get("action_id")
                       or "").startswith("SEED_HOLD")]
        self.assertEqual(len(seed), 3)  # APPROACHING/GRASPED/ATTACHED


def _delivered_shots():
    text = (AGENT / "examples" / "loop_test_02_brass_key.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    timeline = json.loads((JOB / "timeline.json").read_text(
        encoding="utf-8"))
    shots = timeline["shots"]
    starts = {}
    _t = 0.0
    for s in shots:
        starts[id(s)] = _t
        _t += float(s["duration"])
    spans = {}
    for s in shots:
        sid = s.get("directive_shot_id")
        if sid:
            st = starts[id(s)]
            en = st + float(s["duration"])
            if sid in spans:
                spans[sid][1] = max(spans[sid][1], en)
            else:
                spans[sid] = [st, en]
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    out = []
    for i, s in enumerate(shots):
        shot = dict(s)
        shot["index"] = i
        shot["start_sec"] = starts[id(s)]
        out.append(shot)
    return package, out, events, unsupported


class TestEcuStill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.shots, cls.events, cls.unsupported = \
            _delivered_shots()

    def test_insert_event_compiled(self):
        evs = [e for e in self.events
               if e.get("action_id") == "SC06_SH01_ACT01"]
        self.assertEqual(len(evs), 1)
        ev = evs[0]
        self.assertEqual(ev["action_type"], "INSERT_KEY")
        self.assertEqual(
            ev["required_pose"]["primitive"], "insert_key")
        self.assertEqual(ev["prop_id"], "chiếc_chìa_khóa_đồng")
        self.assertIsNone(ev["semantic_action_type"])
        self.assertEqual(ev["contact_points"], [{
            "joint": "hand_r", "target_kind": "prop",
            "target_id": "chiếc_chìa_khóa_đồng",
            "tolerance_px": 15.0}])
        # 7 -> 6 unsupported: only ACT02 (the lock popping open,
        # an object-state sentence with no actor) stays UNCLEAR.
        self.assertEqual(len(self.unsupported), 6)
        self.assertEqual(
            {u["action_id"] for u in self.unsupported},
            {"SC02_SH01_ACT03", "SC03_SH01_ACT02", "SC03_SH01_ACT03",
             "SC03_SH02_ACT02", "SC04_SH01_ACT02",
             "SC06_SH01_ACT02"})

    def _render_still(self, shot, out_dir):
        return _render_shot({"shot": shot, "package": self.package,
                             "out_dir": str(out_dir),
                             "still_only": True})

    def test_ecu_frames_the_key_at_the_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            rep = self._render_still(self.shots[21], tmp)
            anchor = rep["insert_anchor"]
            self.assertIsNotNone(anchor)
            self.assertEqual(anchor["source"], "first_frame_prop")
            self.assertEqual(anchor["kind"], "key")
            self.assertEqual(anchor["applied_scale"], 3.4)
            lock = rep["lock_anchors"]["An"]
            # The key draw sits on the lock (the push press puts
            # it a few px past the lock face).
            self.assertLess(math.hypot(anchor["x"] - lock[0],
                                       anchor["y"] - lock[1]), 25.0)
            self.assertEqual(rep["lock_open_u_end"], {"An": 1.0})
            still = Path(tmp) / "shot_021" / "still.png"
            a = np.asarray(Image.open(still).convert("RGB")).astype(int)
            brass = (np.abs(a - BRASS).sum(axis=2) < 40).sum()
            wood = (np.abs(a - WOOD).sum(axis=2) < 40).sum()
            self.assertGreater(brass, 3000)
            self.assertGreater(wood, 100000)

    def test_ecu_without_a_prop_event_still_frames_the_head(self):
        shot = dict(self.shots[13])
        shot["shot_type"] = "extreme_close_up"
        with tempfile.TemporaryDirectory() as tmp:
            rep = self._render_still(shot, tmp)
            self.assertIsNone(rep["insert_anchor"])
            self.assertEqual(rep["lock_anchors"], {})


if __name__ == "__main__":
    unittest.main()
