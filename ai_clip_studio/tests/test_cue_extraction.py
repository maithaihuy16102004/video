"""Tests for phrase-aware cue extraction and contextual semantic
resolution (Subagent A2, Semantic Production Engine Upgrade,
2026-11-12).

The cue layer is the proven contamination root cause: the old
keyword map staged a wallet ON THE GROUND for Hitler SC01 ("hơi
cúi đầu" + "Lấy ví từ túi áo") because "cúi" -> bend_pick with
no phrase context. These tests pin the phrase-aware behaviour on
four texts (two from Mai's scripts, one genuine ground pickup,
one authored neutral fixture) plus the span-competition guards,
and the full 16-field SemanticAction resolution (7 normative
EXAMPLE_RESOLUTIONS + paraphrases + negatives).

Fixtures are synthetic except the verbatim Hitler SC01 action
sentences and the Zeus forge sentences (read-only inputs, never
modified).
"""
from __future__ import annotations

import unittest

from ai_clip_studio.action_compiler import resolve_semantic_action
from ai_clip_studio.semantic_contracts import (
    EXAMPLE_RESOLUTIONS,
    ActionOrigin,
    AuthorizationStatus,
)
from ai_clip_studio.vi_script_parser import (
    extract_action_cues,
    extract_action_cues_detailed,
)

# Verbatim action sentences of Hitler SC01 (Mai's script, read-only).
HITLER_SC01 = (
    "Hitler đi bộ qua phố Munich. Anh hơi cúi đầu. Anh dừng lại. "
    "Lấy ví từ túi áo. Mở ví bằng hai tay. Anh nhìn vào ví. "
    "Hitler đóng ví. Cất ví vào túi."
)
# Genuine ground pickup (Minh/Lan wallet story beats).
GROUND_PICKUP = "Minh cúi xuống nhặt chiếc ví dưới đất."
GROUND_PICKUP_2 = "Minh cúi người, đưa tay nhặt chiếc ví lên."
# Zeus forge sentences (Mai's script, read-only).
ZEUS_FORGE = (
    "Một Cyclops đưa tia sét thần thánh cho Zeus. "
    "Zeus nhận bằng tay phải. Cyclops đập búa."
)
# Authored neutral fixture (office) -- the only invented text.
OFFICE = (
    "An cúi đầu chào khách. Cô lấy điện thoại từ túi quần. "
    "Cô mỉm cười và vẫy tay."
)


class CueExtractionTest(unittest.TestCase):
    def test_hitler_sc01_no_ground_pickup(self):
        cues = extract_action_cues(HITLER_SC01)
        self.assertNotIn("bend_pick", cues)
        self.assertIn("take_out", cues)
        self.assertIn("head_tilt", cues)
        self.assertEqual(
            cues,
            ["walk", "head_tilt", "stop", "take_out", "open", "look",
             "put_away"])

    def test_ground_pickup_still_fires(self):
        # The true case must not break: explicit ground-pickup
        # phrasing still yields bend_pick.
        self.assertEqual(extract_action_cues(GROUND_PICKUP),
                         ["bend_pick"])
        self.assertEqual(extract_action_cues(GROUND_PICKUP_2),
                         ["bend_pick"])

    def test_zeus_forge_cues(self):
        cues = extract_action_cues(ZEUS_FORGE)
        self.assertEqual(cues, ["give", "take"])
        self.assertNotIn("bend_pick", cues)

    def test_office_fixture_no_ground_pickup(self):
        cues = extract_action_cues(OFFICE)
        self.assertNotIn("bend_pick", cues)
        self.assertIn("head_tilt", cues)
        self.assertIn("take_out", cues)
        self.assertEqual(cues, ["head_tilt", "wave", "take_out", "smile"])

    def test_bare_nhat_is_take_not_bend_pick(self):
        # "nhặt" with no ground evidence is a plain take; the
        # object's source is the prop system's job, never an
        # assumed ground.
        self.assertEqual(extract_action_cues("nhặt chiếc ví"),
                         ["take"])

    def test_both_cues_when_both_phrases_present(self):
        self.assertEqual(
            extract_action_cues("cúi đầu, nhặt chiếc ví lên"),
            ["head_tilt", "bend_pick"])

    def test_span_competition_blocks_bare_take(self):
        # The bend_pick span wins the "nhặt" token, so no
        # duplicate bare take survives for the same token.
        cues = extract_action_cues("cúi xuống nhặt đồ")
        self.assertEqual(cues, ["bend_pick"])

    def test_take_from_surface_is_take(self):
        self.assertEqual(extract_action_cues("Lấy bút trên bàn"),
                         ["take"])

    def test_pinned_fixture_preserved(self):
        self.assertEqual(
            extract_action_cues(
                "Cô ấy chạy đến rồi dừng lại và cúi xuống nhặt đồ."
            )[:3],
            ["run", "stop", "bend_pick"])

    def test_bow_alone_is_head_tilt(self):
        self.assertEqual(extract_action_cues("cúi đầu"), ["head_tilt"])

    def test_rain_cue_preserved(self):
        self.assertEqual(extract_action_cues("Mưa rơi ngoài cửa sổ."),
                         ["rain"])


class CueRecordTest(unittest.TestCase):
    def test_records_one_to_one_with_cues(self):
        records = extract_action_cues_detailed(HITLER_SC01)
        self.assertEqual([r["cue"] for r in records],
                         extract_action_cues(HITLER_SC01))

    def test_provenance_fields_pass_through(self):
        records = extract_action_cues_detailed(
            HITLER_SC01, source_script_hash="deadbeef",
            source_scene_id="SC01", source_shot_id="SC01_SH02",
            source_directive_id="SC01_SH02_ACT02")
        for rec in records:
            self.assertEqual(rec["source_script_hash"], "deadbeef")
            self.assertEqual(rec["source_scene_id"], "SC01")
            self.assertEqual(rec["source_shot_id"], "SC01_SH02")
            self.assertEqual(rec["source_directive_id"],
                             "SC01_SH02_ACT02")

    def test_provenance_unknown_is_none_not_invented(self):
        for rec in extract_action_cues_detailed("cúi đầu"):
            self.assertIsNone(rec["source_script_hash"])
            self.assertIsNone(rec["source_scene_id"])
            self.assertIsNone(rec["source_shot_id"])
            self.assertIsNone(rec["source_directive_id"])

    def test_contract_enum_values(self):
        origins = {o.value for o in ActionOrigin}
        statuses = {s.value for s in AuthorizationStatus}
        for rec in extract_action_cues_detailed(HITLER_SC01):
            self.assertIn(rec["action_origin"], origins)
            self.assertEqual(rec["action_origin"],
                             "PLANNER_INFERRED_ACTION")
            self.assertIn(rec["authorization_status"], statuses)
            self.assertEqual(rec["authorization_status"], "INFERRED")

    def test_inference_reason_names_pattern_and_span(self):
        rec = extract_action_cues_detailed("cúi đầu")[0]
        self.assertIn("cúi đầu", rec["inference_reason"])
        self.assertIn("cúi đầu", rec["matched_text"])
        self.assertEqual(rec["match_start"], 0)
        self.assertEqual(rec["match_end"], 7)
        self.assertEqual(rec["pattern"], rec["pattern"])
        self.assertIn("cúi đầu", rec["pattern"])

    def test_take_out_span_covers_full_phrase(self):
        text = "Lấy ví từ túi áo"
        recs = extract_action_cues_detailed(text)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["cue"], "take_out")
        # matched_text is the normalized (lowercased) span; the
        # offsets index the original text.
        self.assertEqual(recs[0]["matched_text"], "lấy ví từ túi áo")
        self.assertEqual(text[recs[0]["match_start"]:
                              recs[0]["match_end"]], text)


def _resolve(text):
    return resolve_semantic_action(
        text, actor_id="CHAR_X", source_scene_id="SC01",
        source_shot_id="SC01_SH01", source_directive_id="D1")


class NormativeResolutionTest(unittest.TestCase):
    def test_all_example_resolutions(self):
        # All 9 normative rows from the contract, resolved on
        # context -- the "wrong" column must be unreachable.
        self.assertEqual(len(EXAMPLE_RESOLUTIONS), 9)
        for row in EXAMPLE_RESOLUTIONS:
            with self.subTest(phrase=row["phrase"]):
                rec = _resolve(row["phrase"])
                self.assertIsNotNone(rec, row["phrase"])
                self.assertEqual(rec.action_type, row["expected"])
                self.assertNotEqual(rec.action_type, row["wrong"])
                for field in ("body_part", "source_location",
                              "interaction_hand"):
                    if field in row:
                        self.assertEqual(getattr(rec, field),
                                         row[field], field)

    def test_sixteen_fields_present(self):
        rec = _resolve("Lấy ví từ túi áo")
        self.assertEqual(rec.actor_id, "CHAR_X")
        self.assertEqual(rec.action_type, "TAKE_FROM_POCKET")
        self.assertEqual(rec.source_location, "pocket")
        self.assertEqual(rec.source_scene_id, "SC01")
        self.assertEqual(rec.source_shot_id, "SC01_SH01")
        self.assertEqual(rec.source_directive_id, "D1")
        self.assertEqual(rec.source_text, "Lấy ví từ túi áo")
        self.assertEqual(rec.confidence, 1.0)
        self.assertTrue(rec.provenance.startswith("phrase-rule:"))
        self.assertEqual(rec.object_state_before, "IN_POCKET")
        self.assertEqual(rec.object_state_after, "HELD")
        self.assertEqual(rec.action_origin,
                         ActionOrigin.EXPLICIT_SCRIPT_ACTION)
        self.assertEqual(rec.authorization_status,
                         AuthorizationStatus.AUTHORIZED)


class ParaphraseResolutionTest(unittest.TestCase):
    CASES = (
        ("Minh cúi người, đưa tay nhặt chiếc ví lên", "BEND_PICK",
         {"source_location": "ground",
          "object_state_before": "ON_GROUND"}),
        ("Rút điện thoại từ túi quần", "TAKE_FROM_POCKET",
         {"source_location": "pocket"}),
        ("Lấy túi", "TAKE", {"confidence": 0.85}),
        ("Nhận thanh kiếm bằng tay trái", "RECEIVE_PROP",
         {"interaction_hand": "LEFT",
          "object_state_after": "HELD_LEFT"}),
        ("Cúi đầu chào", "HEAD_TILT_DOWN", {"body_part": "head"}),
        ("Nhặt chiếc ví dưới đất", "PICK_FROM_GROUND",
         {"source_location": "ground",
          "destination_location": None}),
        ("Lấy bút trên bàn", "PICK_FROM_SURFACE",
         {"source_location": "surface",
          "destination_location": None}),
        ("Cúi người tránh tiếng pháo", "CROUCH",
         {"body_part": "torso", "spatial_relationship": "avoidance"}),
        ("Đón lấy chiếc búa bằng tay phải", "RECEIVE_PROP",
         {"interaction_hand": "RIGHT"}),
        ("Cyclops đập búa xuống đe", "HAMMER_STRIKE",
         {"body_part": "hand"}),
        ("Mở cửa ra", "OPEN", {"object_state_before": "CLOSED",
                               "object_state_after": "OPEN"}),
        ("Đóng nắp hộp lại", "CLOSE",
         {"object_state_before": "OPEN",
          "object_state_after": "CLOSED"}),
        ("Bước lên xe buýt", "BOARD",
         {"destination_location": "vehicle"}),
        ("Anh ta gật đầu", "NOD", {"body_part": "head"}),
        ("Cô ấy vẫy tay chào", "WAVE", {"body_part": "hand"}),
        ("Zeus nhận tia sét bằng tay phải", "RECEIVE_PROP",
         {"interaction_hand": "RIGHT"}),
        ("Một Cyclops đưa tia sét thần thánh cho Zeus", "GIVE",
         {"object_state_after": "IN_TRANSIT"}),
        ("Cất ví vào túi", "PUT_AWAY",
         {"destination_location": "pocket",
          "object_state_after": "IN_POCKET"}),
        # A pen put down ON THE DESK is a surface placement, not a
        # pocketing: the old PUT_AWAY label contradicted the row's
        # own ON_SURFACE expectation (regression matrix, 2026-11-12).
        ("Đặt bút xuống bàn", "PLACE_ON_SURFACE",
         {"destination_location": "surface",
          "object_state_after": "ON_SURFACE"}),
    )

    def test_paraphrases(self):
        for text, expected, fields in self.CASES:
            with self.subTest(text=text):
                rec = _resolve(text)
                self.assertIsNotNone(rec, text)
                self.assertEqual(rec.action_type, expected)
                for field, value in fields.items():
                    self.assertEqual(getattr(rec, field), value, field)


class NegativeResolutionTest(unittest.TestCase):
    def test_head_raise_alone_has_no_type(self):
        # No HEAD_TILT_UP type in the contract vocabulary.
        self.assertIsNone(_resolve("ngẩng đầu"))

    def test_nhan_ra_is_not_a_receive(self):
        self.assertIsNone(_resolve("Anh nhận ra mình đã quên"))

    def test_phenomenon_subject_is_not_a_character_action(self):
        self.assertIsNone(_resolve("Điện chạy nhẹ quanh cánh tay"))

    def test_idiomatic_lay_is_not_a_take(self):
        self.assertIsNone(_resolve("Lấy làm tiếc"))

    def test_missing_actor_raises(self):
        with self.assertRaises(ValueError):
            resolve_semantic_action(
                "Lấy ví từ túi áo", actor_id="",
                source_scene_id="SC01")
        with self.assertRaises(ValueError):
            resolve_semantic_action(
                "Lấy ví từ túi áo", actor_id="CHAR_X",
                source_scene_id="")


if __name__ == "__main__":
    unittest.main()
