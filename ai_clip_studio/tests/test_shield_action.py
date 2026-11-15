"""SHIELD: the general shielding action (round-2 system).

A character interposes both arms as a guard in front of the chest.
Wired at every layer: semantic type, compiler verb, classification
phrases, rig primitive, and the compile_actions dispatch. The phrase
rules are multi-word only: bare "chắn" would fire on "chắc chắn"
(certainly), and bare "che" is not a pose.
"""

import math
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import (
    ACTION_TYPES, FORBIDDEN_SEMANTIC_COMPILATIONS, PRIMITIVE_MAP,
    SEMANTIC_TO_COMPILER_VERB, _classify, _normalize,
    compile_actions as compile_directives, resolve_semantic_action)
from ai_clip_studio.animation import Stickman
from ai_clip_studio.animation.primitives import (
    PRIMITIVES, compile_actions, shield)
from ai_clip_studio.product_renderer import (
    _render_shot, plan_shots)
from ai_clip_studio.prop_system import (
    SemanticPropTracker, geometry_for_prop)
from ai_clip_studio.semantic_contracts import SEMANTIC_ACTION_TYPES
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

LOOP01 = Path(__file__).resolve().parents[2] / "examples" / \
    "loop_test_01_fire_stone.studio.md"


def _loop01_package_and_shots():
    package = adapt_document(parse_studio_script_v1(
        LOOP01.read_text(encoding="utf-8")))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(7)])
    for i, shot in enumerate(shots):
        shot["index"] = i
    spans = {}
    for shot in shots:
        did = shot.get("directive_shot_id")
        if did:
            spans[did] = (shot["start_sec"],
                          shot["start_sec"] + shot["duration"])
    events, unsupported = compile_directives(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    return package, shots, events


def _resolve(text, actor_id="CHAR_X"):
    return resolve_semantic_action(
        text, actor_id=actor_id, source_scene_id="SC01",
        source_shot_id="SC01_SH01", source_directive_id="D1")


def _classify_type(text):
    action_type, _cat, _notes, _info = _classify(
        _normalize(text), {"locomotion": None, "seated": False})
    return action_type


class TestShieldWiring(unittest.TestCase):
    def test_semantic_type_and_verb_registered(self):
        self.assertIn("SHIELD", SEMANTIC_ACTION_TYPES)
        self.assertEqual(SEMANTIC_TO_COMPILER_VERB["SHIELD"], "SHIELD")
        self.assertIn("SHIELD", ACTION_TYPES)
        self.assertEqual(PRIMITIVE_MAP["SHIELD"],
                         ("shield", 1.0, "POSE_HELD"))
        self.assertIn("shield", PRIMITIVES)

    def test_mapped_verb_not_forbidden(self):
        forbidden = FORBIDDEN_SEMANTIC_COMPILATIONS["SHIELD"]
        self.assertNotIn(SEMANTIC_TO_COMPILER_VERB["SHIELD"], forbidden)
        # Shielding must never compile as a pickup, pocketing, or drop.
        self.assertIn("PICK_UP", forbidden)
        self.assertIn("PUT_AWAY", forbidden)


class TestShieldClassification(unittest.TestCase):
    def test_shield_phrases_classify(self):
        sentences = [
            "Người Đá giơ hai tay che chắn cho Cáo.",
            "Cô giơ khiên chắn trước mặt.",
            "Anh đứng chắn trước mặt em.",
            "He raises his shield.",
            "She holds up a shield.",
        ]
        for text in sentences:
            with self.subTest(text=text):
                self.assertEqual(_classify_type(text), "SHIELD")

    def test_certainly_is_not_a_shield(self):
        # "chắc chắn" (certainly) contains "chắn" but is not a pose.
        self.assertNotEqual(_classify_type("Cô ấy chắc chắn sẽ đến."),
                            "SHIELD")

    def test_cover_face_not_stolen(self):
        self.assertEqual(_classify_type("Anh che mặt khóc."),
                         "COVER_FACE")

    def test_raise_hand_not_stolen(self):
        self.assertEqual(_classify_type("Anh giơ tay chào mọi người."),
                         "RAISE_HAND")


class TestShieldResolution(unittest.TestCase):
    def test_record_fields(self):
        record = _resolve("Người Đá giơ hai tay che chắn cho Cáo.")
        self.assertIsNotNone(record)
        self.assertEqual(record.action_type, "SHIELD")
        self.assertEqual(record.interaction_hand, "BOTH")
        self.assertEqual(record.confidence, 1.0)
        self.assertEqual(record.body_part, "arms")
        self.assertEqual(record.action_intent, "protect")
        self.assertEqual(record.provenance, "phrase-rule:shield")

    def test_both_hands_without_explicit_mention(self):
        # The pose is definitionally two-armed even when the
        # sentence does not say "hai tay".
        record = _resolve("Người Đá che chắn cho Cáo.")
        self.assertIsNotNone(record)
        self.assertEqual(record.interaction_hand, "BOTH")


class TestShieldSpec(unittest.TestCase):
    # Round-7: the shield is a ROUND WOODEN disc ("khiên gỗ tròn"),
    # not the old grey kite. The face is a circle in the wood slot,
    # the grip is the upper strap above the centre, and the drawn
    # box is square.
    def test_face_is_round_and_wooden(self):
        spec = geometry_for_prop({"kind": "shield"})
        x0, y0, x1, y1 = spec["bbox"]
        self.assertLess(abs((x1 - x0) - (y1 - y0)), 1.0)
        face = [p for p in spec["parts"] if p["name"] == "face"][0]
        self.assertEqual(face["slot"], "wood")
        self.assertEqual(face["op"], "polygon")
        self.assertGreaterEqual(len(face["points"]), 16)
        self.assertIn("wood", spec["material_slots"])

    def test_grip_is_upper_strap_above_centre(self):
        spec = geometry_for_prop({"kind": "shield"})
        gx, gy = spec["contact_points"]["grip"]
        x0, y0, x1, y1 = spec["bbox"]
        self.assertAlmostEqual(gx, (x0 + x1) / 2.0, places=6)
        self.assertLess(gy, (y0 + y1) / 2.0)
        radius = (x1 - x0) / 2.0
        self.assertAlmostEqual((y0 + y1) / 2.0 - gy, 0.33 * radius,
                               places=3)

    def test_round_whatever_box_it_is_built_in(self):
        spec = geometry_for_prop(
            {"kind": "shield", "width_px": 200.0, "height_px": 60.0})
        x0, y0, x1, y1 = spec["bbox"]
        self.assertLess(abs((x1 - x0) - (y1 - y0)), 1.0)


class TestShieldPrimitive(unittest.TestCase):
    def _char(self):
        char = Stickman(height=560, name="guard")
        char.set_pose(root_x=500, root_y=679, facing=1)
        return char

    def test_guard_pose_hands_in_front_of_chest(self):
        char = self._char()
        before = char.joints()
        fn = shield(char, 1.0)
        fn(1.0)
        after = char.joints()
        head_y = after["head"][1]
        hip_y = after["hip"][1]
        shoulder_x = after["shoulder"][0]
        for hand in ("hand_l", "hand_r"):
            moved = math.hypot(after[hand][0] - before[hand][0],
                               after[hand][1] - before[hand][1])
            self.assertGreater(moved, 20.0, hand)
            # In front of the shoulder line, at chest height.
            self.assertGreater(after[hand][0], shoulder_x + 20, hand)
            self.assertGreater(after[hand][1], head_y - 20, hand)
            self.assertLess(after[hand][1], hip_y + 20, hand)
        # Stacked guard: the two hands sit at different heights.
        self.assertGreater(abs(after["hand_r"][1] - after["hand_l"][1]),
                           40.0)
        # Slight crouch: the root drops.
        self.assertGreater(char.pose["root_y"], 679)

    def test_guard_holds_to_end_of_duration(self):
        char = self._char()
        fn = shield(char, 1.0)
        fn(0.5)
        mid = char.joints()
        fn(1.0)
        end = char.joints()
        for hand in ("hand_l", "hand_r"):
            self.assertAlmostEqual(mid[hand][0], end[hand][0], places=1)
            self.assertAlmostEqual(mid[hand][1], end[hand][1], places=1)

    def test_compile_actions_dispatch(self):
        chars = {"guard": self._char()}
        tl = compile_actions(
            [{"type": "shield", "char": "guard", "start": 0.0,
              "duration": 1.0}],
            chars, fps=24)
        self.assertGreater(len(tl), 20)
        first = tl[0]["guard"]
        last = tl[max(tl)]["guard"]
        moved = max(math.hypot(last[k][0] - first[k][0],
                               last[k][1] - first[k][1])
                    for k in ("hand_l", "hand_r"))
        self.assertGreater(moved, 20.0)


if __name__ == "__main__":
    unittest.main()


class TestShieldStagingRound6(unittest.TestCase):
    """Round-6: the shield beat stages the guard, the prop AND the
    protected figure. Before this the SHIELD event had no target,
    the planner hid the protected figure until their first speaking
    scene, the prop trackers never attached the shield, and the
    fixed staging slots projected the third character off-frame."""

    def test_shield_event_targets_the_protected_figure(self):
        _pkg, _shots, events = _loop01_package_and_shots()
        shield = [e for e in events
                  if e["action_id"] == "SC03_SH01_ACT02"]
        self.assertEqual(len(shield), 1)
        self.assertEqual(shield[0]["target_id"], "CHAR_BE_NAM")
        self.assertEqual(shield[0]["prop_id"], "khiên_gỗ")
        self.assertEqual(
            shield[0]["required_pose"]["params"]["hand"], "both")

    def test_protected_figure_visible_in_the_shield_shot(self):
        _pkg, shots, _events = _loop01_package_and_shots()
        shield_shots = [s for s in shots
                        if s.get("directive_shot_id") == "SC03_SH01"]
        self.assertTrue(shield_shots)
        for shot in shield_shots:
            self.assertIn("Bé Nam", shot["visible"])

    def test_tracker_holds_the_shield_through_the_beat(self):
        package, _shots, events = _loop01_package_and_shots()
        shield_evs = [e for e in events
                      if e.get("prop_id") == "khiên_gỗ"
                      and e["action_type"] in ("SHIELD", "RELEASE")]
        tracker = SemanticPropTracker(
            [p for p in package["props"] if p["id"] == "khiên_gỗ"],
            shield_evs)
        shield = next(e for e in shield_evs
                      if e["action_type"] == "SHIELD")
        mid = (shield["start_time"] + shield["end_time"]) / 2.0
        self.assertEqual(tracker.location_at("khiên_gỗ", mid),
                         "HELD_BOTH")
        self.assertEqual(tracker.holder_at("khiên_gỗ", mid),
                         "CHAR_ONG_BA")

    def test_staging_fit_brings_the_third_character_in_frame(self):
        package, shots, _events = _loop01_package_and_shots()
        # Any SC03_SH01 shot staging all three: the shot-type
        # split (OTS vs reaction) shifts with line durations, but
        # the staging slots + cave camera are duration-independent.
        target = next(s for s in shots
                      if s.get("directive_shot_id") == "SC03_SH01"
                      and len(s["visible"]) == 3)
        with tempfile.TemporaryDirectory() as tmp:
            res = _render_shot({"shot": target, "package": package,
                                "out_dir": tmp})
        # Round-7: the third character (Bé Nam) is shield-staged
        # behind the shielder -- anchored, hence exempt from the
        # staging fit -- so the fit takes 0 steps here and the
        # outcome (in frame) is the shield staging's doing. The
        # fixed slots projected Bé Nam to cx 2473 (off-frame)
        # before round 6; the fit still covers non-shield shots.
        self.assertIn("Bé Nam", res.get("shield_staging") or {})
        tel = res["grip_telemetry"]
        head = tel[-1]["hands"]["Bé Nam"]["head"]
        self.assertGreater(head[0], 0.0)
        self.assertLess(head[0], 1920.0)

    def test_two_character_shot_needs_no_staging_fit(self):
        # The fit is a no-op when every staged character already
        # fits: existing two-character framings are untouched.
        package, shots, _events = _loop01_package_and_shots()
        target = next(s for s in shots
                      if s.get("directive_shot_id") == "SC02_SH01")
        self.assertEqual(len(target["visible"]), 2)
        with tempfile.TemporaryDirectory() as tmp:
            res = _render_shot({"shot": target, "package": package,
                                "out_dir": tmp})
        self.assertEqual(res["staging_fit_steps"], 0)
