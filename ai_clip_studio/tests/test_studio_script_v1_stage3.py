"""Stage 3 tests: the new STUDIO SCRIPT V1 dialect (Phase B Stage 3).

Covers the authoritative new-dialect script (Ep1 v2), the Zeus script as
a second real-world validation case, the first-person prerequisite rule
(V1E025, SPEC §16), bullet lists / separators / terminator, per-block
duplicate scoping, LOCATION ref-vs-declare, CAMERA-vs-TYPE, the
CAMERA_MOVEMENT prose rule, scoped NONE directives, per-scope cue
limits, and the to_dict() contract shared with the adapter agent.

The scripts under examples/ are read-only fixtures; these tests never
write to them.
"""

import json
import os
import unittest

from ai_clip_studio.studio_script_v1 import (
    detect_format,
    parse_studio_script_v1,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
EP1_V2 = os.path.join(_ROOT, "examples", "hitler_ep01_munich_1914.studio.md")
ZEUS = os.path.join(_ROOT, "examples", "zeus_ep01_fall_of_cronus.studio.md")
TEMPLATE = os.path.join(_ROOT, "docs", "STUDIO_SCRIPT_V1_TEMPLATE.md")
SCHEMA = os.path.join(_ROOT, "docs", "studio_script_v1.schema.json")
FREEFORM = "/home/hatch/workspace/acceptance_loop/test_chiec_vi_trong_mua/script.txt"


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _codes(doc):
    return [(i.line, i.code) for i in doc.validation_errors]


def _error_codes(doc, code):
    return [i for i in doc.validation_errors if i.code == code]


FIRST_PERSON_HEADER = "\n".join([
    "STUDIO SCRIPT V1",
    "PROJECT",
    "STORYTELLING_MODE: FIRST_PERSON_ROLEPLAY",
    "PRIMARY_CHARACTER: CHAR_A",
    "EXTERNAL_NARRATOR: NONE",
    "CHARACTER: CHAR_A",
    "NAME: Anh A",
    "CHARACTER: CHAR_B",
    "NAME: Chi B",
    "",
])


def _doc_with_scene(body):
    return parse_studio_script_v1(
        FIRST_PERSON_HEADER
        + "SCENE: SC01\nTITLE: Canh mau\n"
        + body)


class TestNewScriptEp1V2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _read(EP1_V2)
        cls.doc = parse_studio_script_v1(cls.text)

    def test_detection(self):
        self.assertEqual(detect_format(self.text), "studio_v1")

    def test_no_errors_no_warnings_no_unsupported(self):
        self.assertTrue(self.doc.is_valid, _codes(self.doc))
        self.assertEqual(self.doc.validation_errors, [])
        self.assertEqual(self.doc.warnings, [])
        self.assertEqual(self.doc.unsupported_fields, [])

    def test_exact_counts(self):
        doc = self.doc
        self.assertEqual(len(doc.scenes), 6)
        self.assertEqual(sum(len(s.shots) for s in doc.scenes), 17)
        self.assertEqual(len(doc.spoken_lines), 9)
        narrations = [l for l in doc.spoken_lines if l.kind == "narration"]
        dialogues = [l for l in doc.spoken_lines if l.kind == "dialogue"]
        self.assertEqual(len(narrations), 5)
        self.assertEqual(len(dialogues), 4)
        self.assertEqual(
            [l for l in doc.spoken_lines if l.speaker == "Narrator"], [])
        sfx = [c for s in doc.scenes for c in s.audio_cues
               if c.cue_type == "SFX"]
        self.assertEqual(len(sfx), 7)
        self.assertEqual(len(doc.locations), 6)
        self.assertEqual(len(doc.props), 4)
        self.assertIsNotNone(doc.end_card)
        self.assertEqual(doc.qa.fields.get("MIN_OVERALL_SCORE"), "8.0/10")
        self.assertEqual(
            doc.output.fields.get("DRIVE_PROJECT_FOLDER"),
            "HITLER_EP01_MUNICH_1914")

    def test_first_person_meta(self):
        meta = self.doc.to_dict()["meta"]
        self.assertEqual(meta["storytelling_mode"], "FIRST_PERSON_ROLEPLAY")
        self.assertEqual(meta["primary_character"], "CHAR_HITLER")
        self.assertEqual(meta["external_narrator"], "NONE")
        self.assertEqual(meta["project_id"], "HITLER_EP01_MUNICH_1914")
        self.assertEqual(meta["target_duration_min"], 85.0)
        self.assertEqual(meta["target_duration_max"], 100.0)

    def test_speaker_resolution_to_display_names(self):
        for line in self.doc.spoken_lines:
            self.assertNotEqual(line.speaker, "Narrator")
            self.assertTrue(line.speaker_id)
        narrations = [l for l in self.doc.spoken_lines
                      if l.kind == "narration"]
        self.assertEqual(len(narrations), 5)
        self.assertTrue(all(l.speaker_id == "CHAR_HITLER"
                            for l in narrations))
        hitler_lines = [l for l in self.doc.spoken_lines
                        if l.speaker_id == "CHAR_HITLER"]
        self.assertEqual(len(hitler_lines), 7)
        self.assertTrue(all(l.speaker == "Adolf Hitler"
                            for l in hitler_lines))
        soldier_lines = [l for l in self.doc.spoken_lines
                         if l.speaker_id == "CHAR_SOLDIER"]
        self.assertEqual(len(soldier_lines), 2)
        self.assertTrue(all(l.speaker == "Người lính Bavaria"
                            for l in soldier_lines))

    def test_quote_stripping_one_layer(self):
        line = next(l for l in self.doc.spoken_lines
                    if l.line_id == "EP01_FP_01")
        self.assertFalse(line.text.startswith(("“", '"')))
        self.assertFalse(line.text.endswith(("”", '"')))

    def test_structured_sfx_subfields(self):
        cue = next(c for s in self.doc.scenes for c in s.audio_cues
                   if c.cue_id == "SFX_001")
        self.assertEqual(cue.event, "Wallet opening")
        self.assertEqual(cue.cue_type_text, "Soft leather rustle")
        self.assertEqual(cue.duration, "0.4s")
        self.assertEqual(cue.duration_seconds, 0.4)
        self.assertEqual(cue.shot_id, "SC01_SH02")

    def test_scene_and_shot_ids_and_fields(self):
        scene = self.doc.scenes[0]
        self.assertEqual(scene.id, "SC01")
        self.assertEqual(scene.number, 1)
        self.assertEqual(scene.location_ref, "LOC_MUNICH_STREET")
        shot = scene.shots[0]
        self.assertEqual(shot.id, "SC01_SH01")
        self.assertEqual(shot.type, "")
        data = self.doc.to_dict()
        self.assertIsNone(data["scenes"][0]["shots"][0]["type"])
        self.assertTrue(data["scenes"][0]["shots"][0]["camera"])

    def test_end_card_duration(self):
        card = self.doc.to_dict()["end_card"]
        self.assertEqual(card["duration_sec"], 3.0)
        self.assertEqual(card["duration_raw"], "3s")

    def test_schema_valid(self):
        import jsonschema
        with open(SCHEMA, encoding="utf-8") as handle:
            schema = json.load(handle)
        jsonschema.validate(self.doc.to_dict(), schema)


class TestZeusScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _read(ZEUS)
        cls.doc = parse_studio_script_v1(cls.text)

    def test_detection_and_counts(self):
        self.assertEqual(detect_format(self.text), "studio_v1")
        self.assertEqual(len(self.doc.scenes), 10)
        self.assertEqual(
            sum(len(s.shots) for s in self.doc.scenes), 41)
        self.assertEqual(len(self.doc.spoken_lines), 40)
        self.assertEqual(len(self.doc.characters), 14)
        self.assertEqual(len(self.doc.locations), 8)
        self.assertEqual(len(self.doc.props), 8)
        sfx = [c for s in self.doc.scenes for c in s.audio_cues
               if c.cue_type == "SFX"]
        self.assertEqual(len(sfx), 13)

    def test_only_head_ratio_lock_error(self):
        # The head-ratio lock (0.33-0.35) is deliberately NOT relaxed:
        # Cronus HEAD_RATIO 0.30 stays V1E009. Production renders at
        # 0.34 + scale and reports the difference (SPEC §5.1).
        self.assertEqual(
            [(i.line, i.code) for i in self.doc.validation_errors],
            [(252, "V1E009")])
        self.assertEqual(self.doc.unsupported_fields, [])

    def test_no_narrator_lines(self):
        self.assertEqual(
            [l for l in self.doc.spoken_lines if l.speaker == "Narrator"],
            [])


class TestDetectionForms(unittest.TestCase):
    def test_old_forms_detected(self):
        self.assertEqual(detect_format("# STUDIO SCRIPT V1\n"), "studio_v1")
        self.assertEqual(
            detect_format("PROJECT: X\nSCENE 1: Mo dau\n"), "studio_v1")

    def test_new_forms_detected(self):
        self.assertEqual(detect_format("STUDIO SCRIPT V1\n"), "studio_v1")
        self.assertEqual(
            detect_format("PROJECT\nPROJECT_ID: X\n"), "studio_v1")
        self.assertEqual(
            detect_format("SCENE: SC01\nTITLE: T\n"), "studio_v1")
        self.assertEqual(
            detect_format("SHOT: SH01\nCAMERA: wide\n"), "studio_v1")

    @unittest.skipUnless(os.path.exists(FREEFORM), "freeform fixture absent")
    def test_freeform_still_freeform(self):
        self.assertEqual(detect_format(_read(FREEFORM)), "freeform")


class TestSeparatorsAndTerminator(unittest.TestCase):
    def test_separator_lines_skipped(self):
        doc = _doc_with_scene("⸻\nSHOT: SH01\nCAMERA: wide\n⸻\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.unsupported_fields, [])

    def test_content_after_terminator_is_error(self):
        doc = _doc_with_scene("SHOT: SH01\nCAMERA: wide\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\nTEXT: “Chao.”\n"
                              "END STUDIO SCRIPT V1\n"
                              "NARRATION: Noi dung thua.\n")
        self.assertEqual([i.code for i in doc.validation_errors], ["V1E019"])

    def test_blank_lines_after_terminator_ok(self):
        doc = _doc_with_scene("SHOT: SH01\nCAMERA: wide\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\nTEXT: “Chao.”\n"
                              "END STUDIO SCRIPT V1\n\n\n")
        self.assertTrue(doc.is_valid, _codes(doc))


class TestDuplicateScoping(unittest.TestCase):
    def test_same_key_in_different_blocks_is_legal(self):
        text = FIRST_PERSON_HEADER.replace(
            "EXTERNAL_NARRATOR: NONE\n",
            "EXTERNAL_NARRATOR: NONE\nLANGUAGE: vi-VN\n")
        text += ("GLOBAL_AUDIO\nLANGUAGE: vi-VN\n"
                 "SCENE: SC01\nTITLE: T\nSHOT: SH01\nCAMERA: wide\n"
                 "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\n"
                 "TEXT: “Chao.”\n")
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(_error_codes(doc, "V1E006"), [])

    def test_same_key_twice_in_one_block_is_error(self):
        doc = _doc_with_scene("MOOD: Mot\nMOOD: Hai\n"
                              "SHOT: SH01\nCAMERA: wide\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E006")), 1)


class TestLocationRefVsDeclare(unittest.TestCase):
    def test_document_level_location_declares(self):
        doc = parse_studio_script_v1(
            FIRST_PERSON_HEADER
            + "LOCATION: LOC_X\nNAME: Noi X\n"
              "SCENE: SC01\nTITLE: T\nLOCATION: LOC_X\n"
              "SHOT: SH01\nCAMERA: wide\n"
              "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(len(doc.locations), 1)
        self.assertEqual(doc.scenes[0].location_ref, "LOC_X")

    def test_scene_location_inline_text_when_no_match(self):
        doc = _doc_with_scene("LOCATION: Mot noi chua khai bao\n"
                              "SHOT: SH01\nCAMERA: wide\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertIsNone(doc.scenes[0].location_ref)
        self.assertEqual(doc.scenes[0].location_text,
                         "Mot noi chua khai bao")


class TestCameraVsType(unittest.TestCase):
    def test_camera_only_shot_allowed_new_dialect(self):
        doc = _doc_with_scene("SHOT: SH01\nCAMERA: Bat ky van ban nao\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertIsNone(doc.to_dict()["scenes"][0]["shots"][0]["type"])
        self.assertEqual(doc.scenes[0].shots[0].camera,
                         "Bat ky van ban nao")

    def test_no_type_no_camera_is_v1e013(self):
        doc = _doc_with_scene("SHOT: SH01\nACTION: Dung yen.\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E013")), 1)

    def test_invalid_type_still_v1e014(self):
        doc = _doc_with_scene("SHOT: SH01\nTYPE: BOGUS_SHOT\n"
                              "CAMERA: wide\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E014")), 1)
        self.assertEqual(_error_codes(doc, "V1E013"), [])

    def test_valid_type_preserved(self):
        doc = _doc_with_scene("SHOT: SH01\nTYPE: CLOSE_UP\nCAMERA: wide\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.scenes[0].shots[0].type, "close_up")


class TestCameraMovementRule(unittest.TestCase):
    def _shot(self, movement):
        doc = _doc_with_scene(
            f"SHOT: SH01\nCAMERA: wide\nCAMERA_MOVEMENT: {movement}\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        return doc

    def test_enum_value_accepted(self):
        doc = self._shot("TRACKING")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.scenes[0].shots[0].camera_movement, "TRACKING")
        # camera_movement_text is the verbatim line whenever one exists.
        self.assertEqual(
            doc.scenes[0].shots[0].camera_movement_text, "TRACKING")

    def test_prose_accepted_verbatim(self):
        doc = self._shot("Slow lateral tracking")
        self.assertTrue(doc.is_valid, _codes(doc))
        shot = doc.scenes[0].shots[0]
        self.assertIsNone(shot.camera_movement)
        self.assertEqual(shot.camera_movement_text, "Slow lateral tracking")

    def test_upper_snake_non_enum_is_v1e007(self):
        doc = self._shot("WILD_SWING")
        self.assertEqual(len(_error_codes(doc, "V1E007")), 1)


class TestFirstPersonRule(unittest.TestCase):
    def test_narrator_line_in_first_person_doc_is_v1e025(self):
        doc = _doc_with_scene("SHOT: SH01\nCAMERA: wide\n"
                              "NARRATION: Loi dan ngoai.\n")
        self.assertEqual(len(_error_codes(doc, "V1E025")), 1)

    def test_narration_without_speaker_in_first_person_doc(self):
        doc = _doc_with_scene("SHOT: SH01\nCAMERA: wide\n"
                              "NARRATION:\nLINE_ID: T_01\n"
                              "TEXT: “Khong co speaker.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E025")), 1)

    def test_external_narrator_not_none_is_v1e025(self):
        text = FIRST_PERSON_HEADER.replace(
            "EXTERNAL_NARRATOR: NONE", "EXTERNAL_NARRATOR: PRESENT")
        doc = parse_studio_script_v1(
            text + "SCENE: SC01\nTITLE: T\nSHOT: SH01\nCAMERA: wide\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E025")), 1)

    def test_primary_character_must_resolve(self):
        text = FIRST_PERSON_HEADER.replace(
            "PRIMARY_CHARACTER: CHAR_A", "PRIMARY_CHARACTER: CHAR_MISSING")
        doc = parse_studio_script_v1(
            text + "SCENE: SC01\nTITLE: T\nSHOT: SH01\nCAMERA: wide\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E018")), 1)

    def test_legacy_doc_narrator_allowed_with_warning(self):
        doc = parse_studio_script_v1(
            "PROJECT: Cu\nSCENE 1: Mo dau\nNARRATION: Loi dan cu.\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual([w.code for w in doc.warnings], ["V1E025"])
        self.assertEqual(doc.warnings[0].line, 0)

    def test_legacy_doc_without_narrator_has_no_warning(self):
        doc = parse_studio_script_v1(
            "PROJECT: Cu\nCHARACTER: Anh A\n"
            "SCENE 1: Mo dau\nDIALOGUE: Anh A: Chao.\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.warnings, [])


class TestScopedNoneAndCueLimits(unittest.TestCase):
    def test_shot_none_does_not_conflict_with_other_shot(self):
        doc = _doc_with_scene(
            "SHOT: SH01\nCAMERA: wide\n"
            "SFX:\n* ID: SFX_001\n* EVENT: Tieng dong\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n"
            "SHOT: SH02\nCAMERA: wide\nSFX: NONE\n")
        self.assertTrue(doc.is_valid, _codes(doc))

    def test_shot_none_conflicts_with_same_shot_cue(self):
        doc = _doc_with_scene(
            "SHOT: SH01\nCAMERA: wide\nSFX: NONE\n"
            "SFX:\n* ID: SFX_001\n* EVENT: Tieng dong\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E024")), 1)

    def test_scene_none_conflicts_with_shot_cue(self):
        doc = _doc_with_scene(
            "SFX: NONE\nSHOT: SH01\nCAMERA: wide\n"
            "SFX:\n* ID: SFX_001\n* EVENT: Tieng dong\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E024")), 1)

    def test_bgm_in_different_shots_ok(self):
        doc = _doc_with_scene(
            "SHOT: SH01\nCAMERA: wide\nBGM: Nhac mot\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n"
            "SHOT: SH02\nCAMERA: wide\nBGM: Nhac hai\n")
        self.assertTrue(doc.is_valid, _codes(doc))

    def test_two_bgm_in_same_shot_is_v1e006(self):
        doc = _doc_with_scene(
            "SHOT: SH01\nCAMERA: wide\nBGM: Nhac mot\nBGM: Nhac hai\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E006")), 1)


class TestSpokenSubBlocks(unittest.TestCase):
    def test_dialogue_without_speaker_is_v1e019(self):
        doc = _doc_with_scene("SHOT: SH01\nCAMERA: wide\n"
                              "DIALOGUE:\nLINE_ID: T_01\n"
                              "TEXT: “Khong speaker.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E019")), 1)

    def test_narration_without_text_is_v1e019(self):
        doc = _doc_with_scene("SHOT: SH01\nCAMERA: wide\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\n")
        self.assertEqual(len(_error_codes(doc, "V1E019")), 1)

    def test_duplicate_line_id_is_v1e005(self):
        doc = _doc_with_scene(
            "SHOT: SH01\nCAMERA: wide\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: X_01\nTEXT: “Mot.”\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: X_01\nTEXT: “Hai.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E005")), 1)

    def test_straight_and_curly_quotes_stripped_one_layer(self):
        doc = _doc_with_scene(
            "SHOT: SH01\nCAMERA: wide\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\n"
            "TEXT: \"Noi 'trong' nay.\"\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_02\n"
            "TEXT: “Noi “long” nhau.”\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.spoken_lines[0].text, "Noi 'trong' nay.")
        self.assertEqual(doc.spoken_lines[1].text, "Noi “long” nhau.")

    def test_shot_level_lip_sync_attaches_to_last_line(self):
        doc = _doc_with_scene(
            "SHOT: SH01\nCAMERA: wide\n"
            "DIALOGUE:\nSPEAKER: CHAR_B\nLINE_ID: T_01\n"
            "TEXT: “Chao.”\nEXPRESSION: Vui\nLIP_SYNC: REQUIRED\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.spoken_lines[0].lip_sync, "REQUIRED")


class TestTargetDuration(unittest.TestCase):
    def _doc_with_duration(self, value):
        text = FIRST_PERSON_HEADER.replace(
            "EXTERNAL_NARRATOR: NONE\n",
            f"EXTERNAL_NARRATOR: NONE\nTARGET_DURATION: {value}\n")
        return parse_studio_script_v1(
            text + "SCENE: SC01\nTITLE: T\nSHOT: SH01\nCAMERA: wide\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")

    def test_range_parsed(self):
        doc = self._doc_with_duration("85–100 seconds")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.target_duration_min, 85.0)
        self.assertEqual(doc.target_duration_max, 100.0)

    def test_plain_number_parsed(self):
        doc = self._doc_with_duration("120")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.target_duration_min, 120.0)
        self.assertEqual(doc.target_duration_max, 120.0)

    def test_auto_ok(self):
        doc = self._doc_with_duration("AUTO")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertIsNone(doc.target_duration_min)

    def test_unparseable_is_v1e012(self):
        doc = self._doc_with_duration("khoang hai phut")
        self.assertEqual(len(_error_codes(doc, "V1E012")), 1)

    def test_seconds_suffix_still_v1e012(self):
        doc = self._doc_with_duration("30s")
        self.assertEqual(len(_error_codes(doc, "V1E012")), 1)


class TestShotFields(unittest.TestCase):
    def test_location_override_unknown_is_v1e018(self):
        doc = _doc_with_scene("SHOT: SH01\nCAMERA: wide\n"
                              "LOCATION_OVERRIDE: LOC_MISSING\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E018")), 1)

    def test_location_override_known_ok(self):
        doc = parse_studio_script_v1(
            FIRST_PERSON_HEADER
            + "LOCATION: LOC_X\nNAME: Noi X\n"
              "SCENE: SC01\nTITLE: T\nSHOT: SH01\nCAMERA: wide\n"
              "LOCATION_OVERRIDE: LOC_X\n"
              "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.scenes[0].shots[0].location_override, "LOC_X")

    def test_trigger_parses_line_id(self):
        doc = _doc_with_scene(
            "SHOT: SH01\nCAMERA: wide\n"
            "TRIGGER: T_01 — “Chao.”\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        shot = doc.scenes[0].shots[0]
        self.assertEqual(shot.trigger, "T_01 — “Chao.”")
        self.assertEqual(shot.trigger_line_id, "T_01")

    def test_pauses_parsed(self):
        doc = _doc_with_scene(
            "SHOT: SH01\nCAMERA: wide\nPOST_DIALOGUE_PAUSE: 0.6s\n"
            "END_HOLD: 1.5s\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        shot = doc.scenes[0].shots[0]
        self.assertEqual(shot.post_dialogue_pause, 0.6)
        self.assertEqual(shot.end_hold, 1.5)

    def test_unparseable_pause_is_v1e012(self):
        doc = _doc_with_scene(
            "SHOT: SH01\nCAMERA: wide\nPOST_DIALOGUE_PAUSE: lau\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E012")), 1)

    def test_transition_verbatim_new_dialect(self):
        doc = _doc_with_scene("TRANSITION: CUT_TO_BLACK\n"
                              "SHOT: SH01\nCAMERA: wide\n"
                              "NARRATION:\nSPEAKER: CHAR_A\n"
                              "LINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.scenes[0].transition, "CUT_TO_BLACK")


class TestCharacterExtrasAndHeadRatio(unittest.TestCase):
    def test_voice_none_is_not_extra(self):
        # 2026-11-12 (A2 wiring item 5): VOICE:NONE alone must NOT
        # mark a character an extra -- silent actors (the Cyclopes:
        # hammer, carry, hand over the bolt) belong in the visible
        # cast. Only the background-extras role marks an extra.
        doc = parse_studio_script_v1(
            FIRST_PERSON_HEADER
            + "CHARACTER: CHAR_X\nNAME: Quan chung\nVOICE: NONE\n"
              "SCENE: SC01\nTITLE: T\nSHOT: SH01\nCAMERA: wide\n"
              "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        char = next(c for c in doc.characters if c.id == "CHAR_X")
        self.assertFalse(char.is_extra)

    def test_background_extras_role_is_extra(self):
        doc = parse_studio_script_v1(
            FIRST_PERSON_HEADER
            + "CHARACTER: CHAR_X\nNAME: Dam dong\nROLE: Background extras\n"
              "SCENE: SC01\nTITLE: T\nSHOT: SH01\nCAMERA: wide\n"
              "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        extra = next(c for c in doc.characters if c.id == "CHAR_X")
        self.assertTrue(extra.is_extra)

    def test_head_ratio_lock_new_dialect(self):
        doc = parse_studio_script_v1(
            FIRST_PERSON_HEADER
            + "CHARACTER: CHAR_X\nNAME: X\nHEAD_RATIO: 0.42\n"
              "SCENE: SC01\nTITLE: T\nSHOT: SH01\nCAMERA: wide\n"
              "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertEqual(len(_error_codes(doc, "V1E009")), 1)


class TestPropNameMapping(unittest.TestCase):
    def test_prop_name_is_display_name_id_is_reference(self):
        doc = parse_studio_script_v1(
            FIRST_PERSON_HEADER
            + "PROP: PROP_X\nNAME: Ten hien thi\nTYPE: DOCUMENT\n"
              "SCENE: SC01\nTITLE: T\nSHOT: SH01\nCAMERA: wide\n"
              "SUBJECT: PROP_X\n"
              "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\nTEXT: “Chao.”\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.unsupported_fields, [])
        prop = doc.props[0]
        self.assertEqual(prop.id, "PROP_X")
        self.assertEqual(prop.name, "Ten hien thi")


class TestToDictContract(unittest.TestCase):
    def test_contract_keys_present(self):
        doc = parse_studio_script_v1(_read(EP1_V2))
        data = doc.to_dict()
        char = data["characters"][0]
        for key in ("id", "name", "is_extra", "fields", "role", "appearance",
                    "traits", "costume", "costume_changes", "voice",
                    "voice_style", "head_ratio", "identity_id", "line"):
            self.assertIn(key, char)
        self.assertEqual(char["fields"]["NAME"], "Adolf Hitler")
        loc = data["locations"][0]
        for key in ("fields", "type", "period", "geography", "features",
                    "foreground", "midground", "background", "palette",
                    "forbidden"):
            self.assertIn(key, loc)
        prop = data["props"][0]
        for key in ("fields", "id", "type"):
            self.assertIn(key, prop)
        scene = data["scenes"][0]
        for key in ("id", "characters", "costume", "fields"):
            self.assertIn(key, scene)
        shot = scene["shots"][0]
        for key in ("camera", "camera_movement_text", "location_override",
                    "trigger", "fields", "type", "camera_movement"):
            self.assertIn(key, shot)
        line = data["scenes"][0]["spoken_lines"][0]
        for key in ("speaker_id", "lip_sync", "line_id", "speaker"):
            self.assertIn(key, line)
        cue = next(c for s in data["scenes"] for c in s["audio_cues"]
                   if c["cue_id"] == "SFX_001")
        for key in ("cue_id", "event", "trigger", "cue_type_text",
                    "intensity", "duration", "duration_mode"):
            self.assertIn(key, cue)
        self.assertIn("duration_sec", data["end_card"])
        self.assertIn("expected_counts", data["qa"])
        self.assertEqual(data["qa"]["expected_counts"]["expected_scenes"], 6)

    def test_template_schema_valid(self):
        import jsonschema
        with open(SCHEMA, encoding="utf-8") as handle:
            schema = json.load(handle)
        jsonschema.validate(
            parse_studio_script_v1(_read(TEMPLATE)).to_dict(), schema)


if __name__ == "__main__":
    unittest.main()
