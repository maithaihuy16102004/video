"""Tests for ai_clip_studio/action_compiler.py.

Fixtures are SYNTHETIC (invented characters, locations, props) --
never the Ep1 script -- except one read-only integration test that
compiles the real job scene_package.json and asserts structural
accounting (events + unsupported == total sentences, no idle
substitution), not exact per-type counts.
"""
from __future__ import annotations

import json
import os
import unittest

from ai_clip_studio.action_compiler import (
    ACTION_TYPES,
    FIRST_PERSON_PRONOUNS,
    compile_actions,
    compile_shot_expressions,
)


def _package(scenes, meta=None):
    pkg = {
        "characters": [
            {"id": "CHAR_ANA", "name": "Ana", "gender": "female",
             "template": "female", "voice_id": "V_Ana",
             "costume": "red coat"},
            {"id": "CHAR_BEN", "name": "Ben", "gender": "male",
             "template": "male", "voice_id": "V_Ben",
             "costume": "blue uniform"},
        ],
        "props": [
            {"id": "prop_notebook", "name": "notebook",
             "kind": "book", "owner": ""},
            {"id": "prop_pen", "name": "pen", "kind": "pen",
             "owner": ""},
        ],
        "scenes": scenes,
    }
    if meta:
        pkg["v1_meta"] = meta
    return pkg


def _scene(shot_id, actions, expression="", meta=None):
    scene = {
        "id": "SC01",
        "location_id": "LOC_CAFE",
        "shots": [{
            "id": shot_id,
            "camera": "MEDIUM",
            "action": " ".join(actions),
            "expression": expression,
        }],
        "v1_scene": {
            "id": "SC01",
            "shots": [{
                "id": shot_id,
                "camera": "MEDIUM",
                "expression": expression,
                "fields": {"ACTION": list(actions)},
            }],
        },
    }
    return scene


_FIRST_PERSON_META = {
    "storytelling_mode": "FIRST_PERSON_ROLEPLAY",
    "primary_character": "CHAR_ANA",
    "external_narrator": "NONE",
}


class TestPronounResolution(unittest.TestCase):
    def test_first_person_pronouns_resolve_to_primary(self):
        pkg = _package(
            [_scene("SC01_SH01", ["Tôi ngồi xuống ghế.",
                                  "Mình cầm bút lên."])],
            meta=_FIRST_PERSON_META)
        events, unsupported = compile_actions(pkg, {})
        self.assertEqual(unsupported, [])
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e["actor_id"] == "CHAR_ANA"
                            for e in events))

    def test_pronoun_list_documented(self):
        self.assertIn("tôi", FIRST_PERSON_PRONOUNS)
        self.assertIn("mình", FIRST_PERSON_PRONOUNS)
        # "em" is deliberately excluded: it is ambiguous (sibling /
        # romantic address) and must not silently resolve.
        self.assertNotIn("em", FIRST_PERSON_PRONOUNS)

    def test_non_first_person_pronoun_does_not_resolve(self):
        pkg = _package(
            [_scene("SC01_SH01", ["Tôi ngồi xuống ghế."])],
            meta={"storytelling_mode": "THIRD_PERSON",
                  "primary_character": "CHAR_ANA",
                  "external_narrator": "NARRATOR"})
        events, unsupported = compile_actions(pkg, {})
        self.assertEqual(events, [])
        self.assertEqual(len(unsupported), 1)
        self.assertEqual(unsupported[0]["category"], "NO_ACTOR")

    def test_generic_nhan_vat_resolves_in_first_person(self):
        pkg = _package(
            [_scene("SC01_SH01", ["Nhân vật đứng dậy."])],
            meta=_FIRST_PERSON_META)
        events, _ = compile_actions(pkg, {})
        self.assertEqual(events[0]["actor_id"], "CHAR_ANA")

    def test_subject_elision_defaults_to_primary_in_first_person(self):
        pkg = _package(
            [_scene("SC01_SH01", ["Ana đi tới cửa.",
                                  "Dừng lại và nhìn quanh."])],
            meta=_FIRST_PERSON_META)
        events, _ = compile_actions(pkg, {})
        self.assertEqual(events[0]["actor_id"], "CHAR_ANA")
        self.assertEqual(events[1]["actor_id"], "CHAR_ANA")

    def test_named_actor_beats_pronoun(self):
        pkg = _package(
            [_scene("SC01_SH01", ["Ben nhìn tôi."])],
            meta=_FIRST_PERSON_META)
        events, _ = compile_actions(pkg, {})
        self.assertEqual(events[0]["actor_id"], "CHAR_BEN")
        self.assertEqual(events[0]["target_id"], "CHAR_ANA")

    def test_carry_over_within_scene(self):
        pkg = _package(
            [_scene("SC01_SH01", ["Ben đi tới cửa.",
                                  "Mở cửa và bước ra ngoài."])])
        events, _ = compile_actions(pkg, {})
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["actor_id"], "CHAR_BEN")


class TestClassification(unittest.TestCase):
    def _compile(self, actions, meta=None):
        pkg = _package([_scene("SC01_SH01", actions)], meta=meta)
        return compile_actions(pkg, {})

    def test_verb_mappings(self):
        cases = [
            # Chair-sits use the seated primitive (documented guard
            # in _classify: "ngồi" + chair/desk word -> SIT_AT_DESK,
            # which stages hips at chair height, knees ~90 deg).
            ("Ana ngồi xuống ghế.", "SIT_AT_DESK"),
            ("Ana ngồi xuống sàn.", "SIT_DOWN"),
            ("Ana ngồi vào bàn.", "SIT_AT_DESK"),
            ("Ana đứng dậy khỏi ghế.", "STAND_UP"),
            ("Ana bắt đầu viết thư.", "WRITE"),
            ("Ana ký tên vào giấy.", "SIGN"),
            ("Ana cầm bút.", "HOLD_PEN"),
            ("Ana đưa sổ cho Ben.", "HAND_OVER"),
            ("Ana chạy về phía cửa.", "RUN"),
            ("Ana quay đầu lại.", "TURN"),
            ("Ana gật đầu.", "NOD"),
            ("Ana vẫy tay chào.", "WAVE"),
            ("Ana nhún vai.", "SHRUG"),
            ("Ana nhìn ra cửa sổ.", "LOOK_AT"),
            ("Ana giật mình.", "REACT"),
            ("Ana hít một hơi thật sâu.", "BREATHE"),
            ("Ana đặt bút xuống.", "RELEASE"),
            ("Ana cầm tờ giấy lên.", "PICK_UP"),
            ("Ana lội qua vũng bùn.", "WALK_MUD"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                events, unsupported = self._compile([text])
                self.assertEqual(len(events), 1, unsupported)
                self.assertEqual(events[0]["action_type"], expected)

    def test_all_action_types_in_enum(self):
        for name in ("SIT_AT_DESK", "WRITE", "HAND_OVER", "WALK_MUD",
                     "RELEASE", "OPEN_WALLET", "CLOSE_WALLET"):
            self.assertIn(name, ACTION_TYPES)

    def test_sit_then_stand_pairs_to_stand_from_chair(self):
        events, _ = self._compile([
            "Ana ngồi vào bàn.",
            "Ana bắt đầu viết thư.",
            "Ana đứng dậy.",
        ])
        self.assertEqual([e["action_type"] for e in events],
                         ["SIT_AT_DESK", "WRITE", "STAND_FROM_CHAIR"])
        self.assertIn(events[0]["action_id"],
                      events[2]["animation_dependencies"])

    def test_display_verb_guard(self):
        events, unsupported = self._compile(
            ["Hiển thị tuyến di chuyển minh họa."])
        self.assertEqual(events, [])
        self.assertEqual(unsupported[0]["category"], "MAP")

    def test_bag_sway_is_not_march(self):
        events, _ = self._compile(
            ["Ana đi giữa đoàn.", "Túi hành quân dao động nhẹ."])
        self.assertEqual(events[1]["action_type"], "CARRY")

    def test_dialogue_delivery_is_not_reach(self):
        events, unsupported = self._compile(
            ["Ben trả lời với vẻ thờ ơ."])
        self.assertEqual(events, [])
        self.assertEqual(unsupported[0]["category"], "DIALOGUE")

    def test_non_character_categories(self):
        cases = [
            ("Hiển thị bản đồ thành phố.", "MAP"),
            ("Mưa rơi ngoài cửa sổ.", "ENVIRONMENT"),
            ("Camera chuyển sang cận cảnh.", "CAMERA"),
            ("Tiếng chuông vang lên.", "AUDIO"),
            ("Ana mặc áo khoác đỏ.", "COSTUME_STATE"),
        ]
        for text, category in cases:
            with self.subTest(text=text):
                events, unsupported = self._compile([text])
                self.assertEqual(events, [], text)
                self.assertEqual(unsupported[0]["category"], category)

    def test_unsupported_never_becomes_idle(self):
        events, unsupported = self._compile(
            ["Mưa rơi ngoài cửa sổ.", "Ana đi tới cửa."])
        self.assertEqual(len(events), 1)
        self.assertEqual(len(unsupported), 1)
        self.assertNotEqual(events[0]["action_type"], "IDLE")

    def test_write_depends_on_hold_pen(self):
        events, _ = self._compile([
            "Ana ngồi vào bàn.",
            "Ana cầm bút.",
            "Ana bắt đầu viết thư.",
        ])
        write = events[2]
        self.assertIn(events[0]["action_id"],
                      write["animation_dependencies"])
        self.assertIn(events[1]["action_id"],
                      write["animation_dependencies"])

    def test_contact_points_for_write(self):
        events, _ = self._compile([
            "Ana ngồi vào bàn.",
            "Ana cầm bút.",
            "Ana bắt đầu viết thư.",
        ])
        write = events[2]
        self.assertEqual(write["prop_id"], "prop_pen")
        kinds = [p["target_kind"] for p in write["contact_points"]]
        self.assertIn("prop_surface", kinds)
        self.assertTrue(all("tolerance_px" in p or "tolerance_deg" in p
                            for p in write["contact_points"]))

    def test_stable_ids_and_determinism(self):
        pkg = _package([_scene("SC01_SH01", [
            "Ana đi tới cửa.", "Ana dừng lại."])])
        first = compile_actions(pkg, {})
        second = compile_actions(pkg, {})
        self.assertEqual(first, second)
        self.assertEqual([e["action_id"] for e in first[0]],
                         ["SC01_SH01_ACT01", "SC01_SH01_ACT02"])

    def test_timeline_spans_used_when_present(self):
        pkg = _package([_scene("SC01_SH01", [
            "Ana đi tới cửa.", "Ana dừng lại."])])
        timeline = {"spans": {"SC01_SH01": (10.0, 14.0)}}
        events, _ = compile_actions(pkg, timeline)
        self.assertAlmostEqual(events[0]["start_time"], 10.0)
        self.assertLessEqual(events[-1]["end_time"], 14.0 + 1e-9)
        self.assertTrue(all(e["time_source"] == "timeline"
                            for e in events))

    def test_estimate_fallback_flagged(self):
        pkg = _package([_scene("SC01_SH01", ["Ana đi tới cửa."])])
        events, _ = compile_actions(pkg, {})
        self.assertEqual(events[0]["time_source"], "estimated")

    def test_completion_states(self):
        events, _ = self._compile([
            "Ana đưa sổ cho Ben.",
            "Ana ngồi xuống ghế.",
        ])
        self.assertEqual(events[0]["completion_state"]["state"],
                         "PROP_TRANSFERRED")
        self.assertEqual(events[1]["completion_state"]["state"],
                         "POSE_HELD")


class TestPropResolution(unittest.TestCase):
    def test_pocket_rule_keeps_wallet(self):
        pkg = _package([_scene("SC01_SH01", [
            "Ana lấy ví từ túi áo.",
            "Ana cất ví vào túi.",
        ])], meta=_FIRST_PERSON_META)
        # Add a wallet prop + a bag prop named "túi".
        pkg["props"].append({"id": "prop_wallet", "name": "ví",
                             "kind": "wallet", "owner": ""})
        pkg["props"].append({"id": "prop_bag", "name": "túi",
                             "kind": "bag", "owner": ""})
        events, _ = compile_actions(pkg, {})
        self.assertEqual(events[0]["action_type"], "TAKE_OUT")
        self.assertEqual(events[0]["prop_id"], "prop_wallet")
        self.assertEqual(events[1]["action_type"], "PUT_AWAY")
        self.assertEqual(events[1]["prop_id"], "prop_wallet")

    def test_bag_match_outside_pocket_context(self):
        pkg = _package([_scene("SC01_SH01", [
            "Ana đeo túi lên vai.",
        ])])
        pkg["props"].append({"id": "prop_bag", "name": "túi",
                             "kind": "bag", "owner": ""})
        events, _ = compile_actions(pkg, {})
        self.assertEqual(events[0]["prop_id"], "prop_bag")


class TestExpressionCompilation(unittest.TestCase):
    def test_shot_expressions_interpreted(self):
        pkg = _package([_scene("SC01_SH01", ["Ana đi tới cửa."],
                               expression="Hopeful, naive")])
        result = compile_shot_expressions(pkg)
        self.assertEqual(set(result), {"SC01_SH01"})
        self.assertEqual(result["SC01_SH01"]["expression"], "happy")
        self.assertFalse(result["SC01_SH01"]["negated"])

    def test_negated_expression_never_maps_to_target(self):
        pkg = _package([_scene("SC01_SH01", ["Ana đi tới cửa."],
                               expression="không sợ")])
        result = compile_shot_expressions(pkg)
        self.assertNotEqual(result["SC01_SH01"]["expression"], "worried")
        self.assertTrue(result["SC01_SH01"]["negated"])


class TestRealPackageIntegration(unittest.TestCase):
    """Read-only structural accounting on the real Ep1 job package."""

    JOB = os.path.join(os.path.dirname(__file__), "..", "..",
                       "jobs", "req_c4f037b79499")

    def test_ep1_accounting_complete(self):
        package_path = os.path.join(self.JOB, "scene_package.json")
        timeline_path = os.path.join(self.JOB, "timeline.json")
        if not os.path.exists(package_path):
            self.skipTest("job req_c4f037b79499 not present")
        with open(package_path, encoding="utf-8") as fh:
            pkg = json.load(fh)
        with open(timeline_path, encoding="utf-8") as fh:
            timeline = json.load(fh)
        events, unsupported = compile_actions(pkg, timeline)
        total = 0
        for scene in pkg["scenes"]:
            v1 = scene.get("v1_scene") or {}
            for shot in v1.get("shots", []):
                total += len((shot.get("fields") or {}).get("ACTION", []))
        self.assertEqual(len(events) + len(unsupported), total)
        self.assertGreater(len(events), 0)
        self.assertFalse(any(e["action_type"] == "IDLE"
                             for e in events),
                         "idle substitution is forbidden")
        # No actor-less events and no narrator actor.
        self.assertTrue(all(e["actor_id"] for e in events))
        self.assertFalse(any("narrator" in str(e["actor_id"]).lower()
                             for e in events))


if __name__ == "__main__":
    unittest.main()
