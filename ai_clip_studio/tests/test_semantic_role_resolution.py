"""Semantic role resolution (integration sprint section 5).

Positional giver/recipient/target resolution through the REAL paths
(resolver -> compiler -> scene package), with Vietnamese paraphrases
and UNSEEN character names. No hardcoding for Zeus/Cyclops/Hitler:
the unseen-script fixture (tests/fixtures/
unseen_role_resolution.studio.md) carries new characters, locations
and props, and every unit-test sentence uses fresh names.

The bug this pins: the previous longest-name-match rule inverted
giver and receiver ("Rhea đưa bọc khăn cho Cronus" resolved actor
Cronus) and let the first-person default overwrite supporting
characters ("Một Cyclops đưa tia sét cho Zeus" resolved actor
Zeus). Position, not length, decides roles: the subject before the
verb is the actor; a "cho + name" complement is the recipient,
never the actor.

Known honest gaps (documented, not hidden):
- Asking/answering/attacking/helping have no staging verb: the
  resolver resolves their roles, and the compiler honestly reports
  the sentence unsupported (no invented staging). Asking and
  answering stage through dialogue lines, whose SPEAKER fields
  carry the roles.
- A receive names no giver when its shot has no earlier HAND_OVER:
  ownership_before stays None, never guessed.
- Group subjects ("Tôi và Chú Tư đưa...") resolve to the single
  subject closest to the verb; multi-actor staging is unsupported.

Run from ~/workspace/agent/:
  python3 -m unittest ai_clip_studio.tests.test_semantic_role_resolution -v
"""

import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import (
    _character_index, _classify, compile_actions, resolve_semantic_actions,
    resolve_sentence_roles)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

FIXTURE = Path(__file__).with_name(
    "fixtures") / "unseen_role_resolution.studio.md"
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

PRIMARY = "CHAR_LAN"


def _unit_index():
    """char_map + extras for unseen names (no real-script ids)."""
    package = {
        "characters": [
            {"identity_id": "CHAR_LAN", "name": "Bà Lan"},
            {"identity_id": "CHAR_TU", "name": "Chú Tư"},
            {"identity_id": "CHAR_DAO", "name": "Cô Đào"},
            {"identity_id": "CHAR_HUNG", "name": "Anh Hùng"},
            {"identity_id": "CHAR_NA", "name": "Bé Na"},
            {"identity_id": "CHAR_LAMPSMITH", "name": "Lampsmiths"},
            {"identity_id": "CHAR_SOLDIER", "name": "Người lính"},
        ],
        "v1_extras": [
            {"identity_id": "CHAR_BACKGROUND_SOLDIERS",
             "name": "Binh lính", "role": "Background extras"},
        ],
    }
    return _character_index(package)


def _roles(sentence, action_type=None, phrase=None, carry_actor=None,
            first_person=True):
    char_map, extras = _unit_index()
    match = ({"mechanism": "rule", "phrase": phrase}
             if phrase else None)
    return resolve_sentence_roles(
        sentence, char_map=char_map, extras=extras,
        action_type=action_type, match=match,
        primary_character=PRIMARY if first_person else None,
        first_person_enabled=first_person, carry_actor=carry_actor)


def _compile_script(path):
    package = adapt_document(parse_studio_script_v1(
        Path(path).read_text(encoding="utf-8")))
    events, unsupported = compile_actions(package)
    return package, events, unsupported


def _by_id(events):
    return {e["action_id"]: e for e in events}


class TestPositionalRoles(unittest.TestCase):
    def test_give_explicit_subject_beats_longer_recipient(self):
        roles = _roles("Bà Lan đưa chiếc chìa khóa cho Chú Tư.",
                       "HAND_OVER", "đưa")
        self.assertEqual(roles["actor_id"], "CHAR_LAN")
        self.assertEqual(roles["recipient_id"], "CHAR_TU")
        self.assertEqual(roles["target_id"], "CHAR_TU")

    def test_give_indefinite_subject_via_identity_token(self):
        # NAME is the plural "Lampsmiths"; prose says "Một
        # Lampsmith" -- the identity-id token resolves it.
        roles = _roles("Một Lampsmith đưa thanh kiếm cho Anh Hùng.",
                       "HAND_OVER", "đưa")
        self.assertEqual(roles["actor_id"], "CHAR_LAMPSMITH")
        self.assertEqual(roles["recipient_id"], "CHAR_HUNG")

    def test_give_elided_subject_uses_carryover_not_recipient(self):
        roles = _roles("Đưa chiếc thư cho Chú Tư.",
                       "HAND_OVER", "đưa", carry_actor="CHAR_HUNG")
        self.assertEqual(roles["actor_id"], "CHAR_HUNG")
        self.assertEqual(roles["recipient_id"], "CHAR_TU")

    def test_give_elided_subject_defaults_to_primary_not_recipient(
            self):
        roles = _roles("Đưa chiếc thư cho Chú Tư.", "HAND_OVER", "đưa")
        self.assertEqual(roles["actor_id"], PRIMARY)
        self.assertEqual(roles["recipient_id"], "CHAR_TU")

    def test_give_first_person_pronoun_subject(self):
        roles = _roles("Tôi đưa chiếc nhẫn cho Cô Đào.",
                       "HAND_OVER", "đưa")
        self.assertEqual(roles["actor_id"], PRIMARY)
        self.assertEqual(roles["recipient_id"], "CHAR_DAO")

    def test_give_recipient_pronoun(self):
        roles = _roles("Chú Tư đưa chiếc cốc cho tôi.",
                       "HAND_OVER", "đưa")
        self.assertEqual(roles["actor_id"], "CHAR_TU")
        self.assertEqual(roles["recipient_id"], PRIMARY)

    def test_give_permission_shape(self):
        # "Cho tôi đưa..." (let me give...): the pre-verbal
        # pronoun is the subject; the recipient follows the verb.
        roles = _roles("Cho tôi đưa chiếc cốc cho Chú Tư.",
                       "HAND_OVER", "đưa")
        self.assertEqual(roles["actor_id"], PRIMARY)
        self.assertEqual(roles["recipient_id"], "CHAR_TU")

    def test_embedded_clause_first_person_narration(self):
        # First-person narration DESCRIBING another character's
        # action: the embedded subject acts, not the narrator.
        roles = _roles("Tôi thấy Chú Tư đưa chiếc cốc cho Cô Đào.",
                       "HAND_OVER", "đưa")
        self.assertEqual(roles["actor_id"], "CHAR_TU")
        self.assertEqual(roles["recipient_id"], "CHAR_DAO")

    def test_give_tang_paraphrase(self):
        roles = _roles("Bà Lan tặng hoa cho Bé Na.",
                       "HAND_OVER", "tặng")
        self.assertEqual(roles["actor_id"], "CHAR_LAN")
        self.assertEqual(roles["recipient_id"], "CHAR_NA")

    def test_receive_sentence_actor(self):
        roles = _roles("Cô Đào nhận bằng tay phải.",
                       "RECEIVE_PROP", "nhận")
        self.assertEqual(roles["actor_id"], "CHAR_DAO")
        self.assertIsNone(roles["recipient_id"])

    def test_look_at_named(self):
        roles = _roles("Bà Lan nhìn Chú Tư.", "LOOK_AT", "nhìn")
        self.assertEqual(roles["actor_id"], "CHAR_LAN")
        self.assertEqual(roles["target_id"], "CHAR_TU")

    def test_look_at_pronoun_subject(self):
        roles = _roles("Tôi nhìn Chú Tư.", "LOOK_AT", "nhìn")
        self.assertEqual(roles["actor_id"], PRIMARY)
        self.assertEqual(roles["target_id"], "CHAR_TU")

    def test_look_at_pronoun_object(self):
        roles = _roles("Chú Tư nhìn tôi.", "LOOK_AT", "nhìn")
        self.assertEqual(roles["actor_id"], "CHAR_TU")
        self.assertEqual(roles["target_id"], PRIMARY)

    def test_ask_shape_actor(self):
        roles = _roles("Bà Lan hỏi Chú Tư.")
        self.assertEqual(roles["actor_id"], "CHAR_LAN")

    def test_answer_shape_actor(self):
        roles = _roles("Chú Tư trả lời Bà Lan.")
        self.assertEqual(roles["actor_id"], "CHAR_TU")

    def test_attack_shape_actor(self):
        roles = _roles("Anh Hùng tấn công Chú Tư.")
        self.assertEqual(roles["actor_id"], "CHAR_HUNG")

    def test_help_shape_actor(self):
        roles = _roles("Cô Đào giúp Bà Lan.")
        self.assertEqual(roles["actor_id"], "CHAR_DAO")

    def test_collective_subject_wins_over_singular(self):
        roles = _roles("Các binh lính hành quân.", "MARCH", "hành quân")
        self.assertEqual(roles["actor_id"], "CHAR_BACKGROUND_SOLDIERS")
        self.assertTrue(roles["was_collective"])

    def test_singular_soldier_without_collective_marker(self):
        roles = _roles("Người lính hành quân.", "MARCH", "hành quân")
        self.assertEqual(roles["actor_id"], "CHAR_SOLDIER")
        self.assertFalse(roles["was_collective"])

    def test_no_actor_without_first_person_or_carryover(self):
        roles = _roles("Đưa cốc cho Chú Tư.", "HAND_OVER", "đưa",
                       first_person=False)
        self.assertIsNone(roles["actor_id"])
        self.assertEqual(roles["recipient_id"], "CHAR_TU")

    def test_trao_doi_is_not_a_give(self):
        action_type, _cat, _notes, _match = _classify(
            "trao đổi với chú tư về kế hoạch",
            {"locomotion": None, "seated": False})
        self.assertNotEqual(action_type, "HAND_OVER")

    def test_qua_tang_is_not_a_give(self):
        action_type, _cat, _notes, _match = _classify(
            "món quà tặng cho bé na nằm trên bàn",
            {"locomotion": None, "seated": False})
        self.assertNotEqual(action_type, "HAND_OVER")

    def test_mang_ten_is_not_a_carry(self):
        action_type, _cat, _notes, _match = _classify(
            "chiếc túi mang tên bà lan",
            {"locomotion": None, "seated": False})
        self.assertNotEqual(action_type, "CARRY")


class TestUnseenFixtureEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.events, cls.unsupported = _compile_script(
            FIXTURE)
        cls.by_id = _by_id(cls.events)

    def test_fixture_compiles_with_one_honest_gap(self):
        self.assertEqual(len(self.events), 12)
        self.assertEqual(len(self.unsupported), 1)
        self.assertEqual(self.unsupported[0]["category"], "UNCLEAR")
        self.assertIn("quà tặng", self.unsupported[0]["directive_text"])

    def test_give_key_left_hand(self):
        give = self.by_id["SC01_SH01_ACT01"]
        self.assertEqual(give["action_type"], "HAND_OVER")
        self.assertEqual(give["actor_id"], "CHAR_LAN")
        self.assertEqual(give["recipient_id"], "CHAR_TU")
        self.assertEqual(give["target_id"], "CHAR_TU")
        self.assertEqual(give["prop_id"], "prop_key")
        self.assertEqual(give["ownership_before"], "CHAR_LAN")
        self.assertEqual(give["ownership_after"], "CHAR_TU")
        self.assertEqual(give["recipient_hand"], "l")
        recv = self.by_id["SC01_SH01_ACT02"]
        self.assertEqual(recv["action_type"], "RECEIVE_PROP")
        self.assertEqual(recv["actor_id"], "CHAR_TU")
        self.assertEqual(recv["prop_id"], "prop_key")
        self.assertEqual(recv["ownership_before"], "CHAR_LAN")
        self.assertEqual(recv["ownership_after"], "CHAR_TU")
        self.assertEqual(recv["recipient_hand"], "l")
        self.assertEqual(recv["paired_handover_id"], "SC01_SH01_ACT01")

    def test_give_sword_right_hand_guild_giver(self):
        give = self.by_id["SC01_SH02_ACT01"]
        self.assertEqual(give["actor_id"], "CHAR_LAMPSMITH")
        self.assertEqual(give["recipient_id"], "CHAR_HUNG")
        self.assertEqual(give["prop_id"], "prop_sword")
        self.assertEqual(give["ownership_before"], "CHAR_LAMPSMITH")
        self.assertEqual(give["ownership_after"], "CHAR_HUNG")
        self.assertEqual(give["recipient_hand"], "r")
        recv = self.by_id["SC01_SH02_ACT02"]
        self.assertEqual(recv["ownership_before"], "CHAR_LAMPSMITH")
        self.assertEqual(recv["recipient_hand"], "r")

    def test_embedded_clause_transfer(self):
        give = self.by_id["SC01_SH03_ACT01"]
        self.assertEqual(give["actor_id"], "CHAR_TU")
        self.assertEqual(give["recipient_id"], "CHAR_DAO")
        self.assertEqual(give["prop_id"], "prop_cup")

    def test_carryover_give_and_look(self):
        give = self.by_id["SC02_SH01_ACT02"]
        self.assertEqual(give["actor_id"], "CHAR_HUNG")
        self.assertEqual(give["recipient_id"], "CHAR_TU")
        self.assertEqual(give["prop_id"], "prop_letter")
        look = self.by_id["SC02_SH01_ACT03"]
        self.assertEqual(look["action_type"], "LOOK_AT")
        self.assertEqual(look["actor_id"], "CHAR_TU")
        self.assertEqual(look["target_id"], "CHAR_HUNG")

    def test_pronoun_object_look_and_carry(self):
        look = self.by_id["SC02_SH02_ACT01"]
        self.assertEqual(look["actor_id"], "CHAR_TU")
        self.assertEqual(look["target_id"], "CHAR_LAN")
        carry = self.by_id["SC02_SH02_ACT02"]
        self.assertEqual(carry["action_type"], "CARRY")
        self.assertEqual(carry["actor_id"], "CHAR_DAO")
        self.assertEqual(carry["prop_id"], "prop_bag")

    def test_tang_give(self):
        give = self.by_id["SC02_SH03_ACT01"]
        self.assertEqual(give["action_type"], "HAND_OVER")
        self.assertEqual(give["actor_id"], "CHAR_LAN")
        self.assertEqual(give["recipient_id"], "CHAR_NA")

    def test_no_invented_self_transfer(self):
        for event in self.events:
            if event["action_type"] == "HAND_OVER":
                # The giver must differ from the receiver: Zeus
                # giving the bolt to himself is rejected.
                self.assertNotEqual(
                    event["actor_id"], event.get("recipient_id"),
                    f"self-transfer invented at {event['action_id']}")
            if event["action_type"] in ("HAND_OVER", "RECEIVE_PROP"):
                # The ownership transition must move the prop
                # between two different holders. (For RECEIVE_PROP
                # the actor IS the recipient by definition, so the
                # ownership pair -- not actor/recipient -- is the
                # self-transfer check.)
                self.assertNotEqual(
                    event.get("ownership_before"),
                    event.get("ownership_after"),
                    f"no-op ownership at {event['action_id']}")

    def test_dialogue_speakers_preserved(self):
        lines = [ln for sc in self.package["scenes"]
                 for ln in sc["lines"]]
        by_line = {ln["line_id"]: ln for ln in lines}
        self.assertEqual(by_line["TESTR_004"]["speaker_id"], "CHAR_HUNG")
        self.assertEqual(by_line["TESTR_005"]["speaker_id"], "CHAR_TU")
        for line_id in ("TESTR_001", "TESTR_002", "TESTR_003",
                        "TESTR_006"):
            self.assertEqual(by_line[line_id]["kind"], "narration")
            self.assertEqual(by_line[line_id]["speaker_id"], "CHAR_LAN")


class TestRealScriptRolePins(unittest.TestCase):
    def test_zeus_transfers(self):
        _pkg, events, _uns = _compile_script(
            EXAMPLES / "zeus_ep01_fall_of_cronus.studio.md")
        by_id = _by_id(events)
        rhea = by_id["SC03_SH04_ACT01"]
        self.assertEqual(rhea["actor_id"], "CHAR_RHEA")
        self.assertEqual(rhea["recipient_id"], "CHAR_CRONUS")
        cronus_recv = by_id["SC03_SH04_ACT02"]
        self.assertEqual(cronus_recv["actor_id"], "CHAR_CRONUS")
        self.assertEqual(cronus_recv["ownership_before"], "CHAR_RHEA")
        cup = by_id["SC06_SH01_ACT03"]
        self.assertEqual(cup["actor_id"], "CHAR_ZEUS")
        self.assertEqual(cup["recipient_id"], "CHAR_CRONUS")
        self.assertEqual(cup["prop_id"], "prop_herbal_potion")
        bolt = by_id["SC08_SH02_ACT01"]
        self.assertEqual(bolt["actor_id"], "CHAR_CYCLOPS")
        self.assertEqual(bolt["recipient_id"], "CHAR_ZEUS")
        self.assertEqual(bolt["prop_id"], "prop_lightning")
        self.assertEqual(bolt["ownership_before"], "CHAR_CYCLOPS")
        self.assertEqual(bolt["ownership_after"], "CHAR_ZEUS")
        self.assertEqual(bolt["recipient_hand"], "r")
        grip = by_id["SC08_SH02_ACT02"]
        self.assertEqual(grip["actor_id"], "CHAR_ZEUS")
        self.assertEqual(grip["prop_id"], "prop_lightning")
        self.assertEqual(grip["ownership_before"], "CHAR_CYCLOPS")
        self.assertEqual(grip["ownership_after"], "CHAR_ZEUS")
        self.assertEqual(grip["recipient_hand"], "r")
        self.assertEqual(grip["paired_handover_id"], "SC08_SH02_ACT01")

    def test_zeus_counts_unchanged(self):
        package, events, _uns = _compile_script(
            EXAMPLES / "zeus_ep01_fall_of_cronus.studio.md")
        self.assertEqual(len(events), 62)
        self.assertEqual(len(resolve_semantic_actions(package)), 50)

    def test_ep1_off_frame_recipient_stays_unknown(self):
        _pkg, events, _uns = _compile_script(
            EXAMPLES / "hitler_ep01_munich_1914.studio.md")
        by_id = _by_id(events)
        give = by_id["SC03_SH03_ACT04"]
        self.assertEqual(give["actor_id"], "CHAR_HITLER")
        self.assertEqual(give["prop_id"], "prop_letter")
        self.assertIsNone(give["recipient_id"])
        self.assertIsNone(give["ownership_after"])

    def test_ep1_counts_unchanged(self):
        package, events, _uns = _compile_script(
            EXAMPLES / "hitler_ep01_munich_1914.studio.md")
        self.assertEqual(len(events), 52)
        self.assertEqual(len(resolve_semantic_actions(package)), 41)

    def test_no_self_transfer_in_real_scripts(self):
        for name in ("zeus_ep01_fall_of_cronus.studio.md",
                     "hitler_ep01_munich_1914.studio.md"):
            _pkg, events, _uns = _compile_script(EXAMPLES / name)
            for event in events:
                if event["action_type"] == "HAND_OVER":
                    self.assertNotEqual(
                        event["actor_id"], event.get("recipient_id"),
                        f"{name} {event['action_id']}: self-transfer")


if __name__ == "__main__":
    unittest.main()
