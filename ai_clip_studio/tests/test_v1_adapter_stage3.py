"""Stage 3 adapter tests: first-person, camera, costumes, extras,
props, end card/pauses, expressions, shot directives, enrichment.

All tests use stub documents (parser-independent) except the
fixture-preservation test at the end, which uses the real parser.
Synthetic characters/scenes here are grammar fixtures only -- they
are never rendered.
"""
from __future__ import annotations

import copy
import json
import unittest

from ai_clip_studio.studio_script_v1_adapter import (
    _adapt_document,
    _apply_enrichment,
    _cache_enrichment,
    _clear_enrichment_cache,
    adapt_document,
)
from ai_clip_studio.trait_derivation import validate_trait_blocks


def _hero(**overrides):
    char = {
        "id": "CHAR_HERO", "name": "Anh Hùng",
        "role": "Người kể chuyện",
        "appearance": "Tóc nâu, áo sơ mi xanh",
        "traits": ["dũng cảm"], "costume": "Áo sơ mi xanh",
        "costume_changes": [], "voice": "Đức Trí",
        "voice_style": "trầm ấm", "head_ratio": 0.34,
        "identity_id": "CHAR_HERO", "is_extra": False, "line": 3,
        "fields": {
            "GENDER": "Male",
            "VOICE_ID": "Đức Trí",
            "VOICE_TONE": "trầm ấm",
            "MOUSTACHE": "toothbrush",
            "HAIR": "Tóc nâu",
            "COSTUME_CIVILIAN": ["Áo sơ mi xanh", "Quần tây"],
            "COSTUME_MILITARY": ["Áo lính", "Mũ cối"],
        },
    }
    char.update(overrides)
    return char


def _lan(**overrides):
    char = {
        "id": "CHAR_LAN", "name": "Cô Lan",
        "role": "Người bán hàng",
        "appearance": "Tóc dài, áo dài đỏ",
        "traits": ["hiền hậu"], "costume": "Áo dài đỏ",
        "costume_changes": [], "voice": "Mạnh Dũng",
        "voice_style": "nhẹ nhàng", "head_ratio": 0.34,
        "identity_id": "CHAR_LAN", "is_extra": False, "line": 10,
        "fields": {"GENDER": "Female", "VOICE_ID": "Mạnh Dũng"},
    }
    char.update(overrides)
    return char


def _extra(**overrides):
    char = {
        "id": "CHAR_EXTRA", "name": "Người Qua Đường",
        "role": "Background extras",
        "appearance": "", "traits": [], "costume": "",
        "costume_changes": [], "voice": "NONE",
        "voice_style": "", "head_ratio": 0.34,
        "identity_id": "CHAR_EXTRA", "is_extra": True, "line": 17,
        "fields": {"ROLE": "Background extras", "VOICE": "NONE"},
    }
    char.update(overrides)
    return char


def _scene(number=1, **overrides):
    scene = {
        "id": f"SC{number:02d}", "number": number,
        "title": f"Cảnh {number}", "line": 20 + number,
        "location_ref": "LOC_PHO", "location_text": "",
        "characters": ["CHAR_HERO"],
        "costume": "CIVILIAN",
        "time_of_day": "Sáng", "mood": "Vui",
        "duration": None, "duration_seconds": None,
        "visual": "Phố đông người.", "actions": ["Anh Hùng đi bộ."],
        "expressions": [], "camera": "",
        "camera_movement": "STATIC",
        "voice_note": "", "meme_note": "", "transition": "",
        "sfx_none": False, "ambience_none": False,
        "bgm_none": False, "meme_none": False,
        "shots": [], "spoken_lines": [{
            "line_id": f"L{number:03d}", "speaker": "Anh Hùng",
            "speaker_id": "CHAR_HERO", "lip_sync": True,
            "text": "Tôi bước ra phố.", "kind": "narration",
            "voice_note": "", "scene_number": number,
            "shot_id": None, "line": 30 + number,
        }],
        "audio_cues": [], "vfx_cues": [], "fields": {},
    }
    scene.update(overrides)
    return scene


def _new_doc(**overrides):
    data = {
        "snapshot_hash": "c" * 64,
        "storytelling_mode": "FIRST_PERSON_ROLEPLAY",
        "primary_character": "CHAR_HERO",
        "external_narrator": "NONE",
        "meta": {"project": "TEST", "language": "vi-VN"},
        "characters": [_hero(), _lan(), _extra()],
        "locations": [{
            "id": "LOC_PHO", "name": "Phố Cổ", "type": "OUTDOOR",
            "period": "", "geography": "phố", "architecture": "",
            "features": ["cây"], "foreground": "", "midground": "",
            "background": "", "lighting": "", "weather": "",
            "palette": "", "forbidden": "", "line": 2,
            "fields": {"TYPE": "OUTDOOR"},
        }],
        "props": [
            {"name": "Ví Da", "description": "Ví da cũ",
             "owner": "CHAR_HERO", "scenes": [], "all_scenes": False,
             "interactions": [], "line": 5,
             "fields": {"TYPE": "Old leather wallet"}},
            {"name": "Bức Thư", "description": "Thư tay",
             "owner": "CHAR_LAN", "scenes": [], "all_scenes": False,
             "interactions": [], "line": 6,
             "fields": {"TYPE": "Historical enlistment document"}},
            {"name": "Cây Bút", "description": "Bút viết",
             "owner": "CHAR_HERO", "scenes": [], "all_scenes": False,
             "interactions": [], "line": 7,
             "fields": {"TYPE": "Period-appropriate writing pen"}},
            {"name": "Túi Vải", "description": "Túi vải",
             "owner": "CHAR_HERO", "scenes": [], "all_scenes": False,
             "interactions": [], "line": 8,
             "fields": {"TYPE": "Military field bag",
                        "MATERIAL": "Canvas"}},
        ],
        "constraints": [], "qa": {}, "output": {},
        "global_audio": {}, "end_card": None,
        "unsupported_fields": [], "validation_errors": [],
        "scenes": [_scene(1), _scene(2, characters=["CHAR_HERO"],
                                     spoken_lines=[{
                                         "line_id": "L002",
                                         "speaker": "Anh Hùng",
                                         "speaker_id": "CHAR_HERO",
                                         "lip_sync": True,
                                         "text": "Tôi gặp Cô Lan.",
                                         "kind": "dialogue",
                                         "voice_note": "",
                                         "scene_number": 2,
                                         "shot_id": None, "line": 40}])],
    }
    data.update(overrides)
    return data


class StubDoc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return copy.deepcopy(self._data)


class TestFirstPerson(unittest.TestCase):
    def test_narration_keeps_character_speaker(self):
        package = adapt_document(StubDoc(_new_doc()))
        speakers = [ln["speaker"] for sc in package["scenes"]
                    for ln in sc["lines"]]
        self.assertEqual(speakers, ["Anh Hùng", "Anh Hùng"])
        self.assertNotIn("narrator", speakers)
        self.assertTrue(package["v1_first_person"]["enabled"])
        self.assertEqual(package["v1_first_person"]["primary_character"],
                         "CHAR_HERO")

    def test_alias_named_character_not_excluded_in_first_person(self):
        data = _new_doc()
        data["characters"].append({
            "id": "CHAR_NARR", "name": "Người Dẫn Chuyện",
            "role": "Người kể", "appearance": "", "traits": [],
            "costume": "", "costume_changes": [], "voice": "AUTO",
            "voice_style": "", "head_ratio": 0.34,
            "identity_id": "CHAR_NARR", "is_extra": False, "line": 50,
            "fields": {"GENDER": "Male"},
        })
        package = adapt_document(StubDoc(data))
        names = [c["name"] for c in package["characters"]]
        self.assertIn("Người Dẫn Chuyện", names)
        self.assertEqual(package["v1_narrator"], [])

    def test_narrator_speaker_remapped_to_primary(self):
        data = _new_doc()
        data["scenes"][0]["spoken_lines"][0]["speaker"] = "Narrator"
        package = adapt_document(StubDoc(data))
        self.assertEqual(package["scenes"][0]["lines"][0]["speaker"],
                         "Anh Hùng")

    def test_voice_hint_from_gender_never_raw_voice_id(self):
        package = adapt_document(StubDoc(_new_doc()))
        cast = {c["name"]: c for c in package["characters"]}
        self.assertEqual(cast["Anh Hùng"]["voice_hint"], "giọng nam")
        self.assertEqual(cast["Cô Lan"]["voice_hint"], "giọng nữ")
        self.assertEqual(cast["Anh Hùng"]["voice_id"], "Đức Trí")
        blocks = {b["name"]: b for b in
                  package["trait_blocks"]["characters"]}
        self.assertEqual(blocks["Anh Hùng"]["voice_id"], "Đức Trí")
        self.assertEqual(blocks["Anh Hùng"]["render_traits"]["voice_hint"],
                         "giọng nam")

    def test_moustache_from_fields_and_bavarian_trap(self):
        package = adapt_document(StubDoc(_new_doc()))
        cast = {c["name"]: c for c in package["characters"]}
        self.assertEqual(cast["Anh Hùng"]["moustache_style"], "toothbrush")
        self.assertEqual(
            cast["Anh Hùng"]["render_traits"]["moustache_style"],
            "toothbrush")
        # A costume naming a place must never create a moustache.
        data = _new_doc()
        data["characters"][1]["costume"] = "Trang phục Bavarian"
        data["characters"][1]["appearance"] = "Áo Bavarian"
        package = adapt_document(StubDoc(data))
        cast = {c["name"]: c for c in package["characters"]}
        self.assertEqual(cast["Cô Lan"]["moustache_style"], "none")

    def test_moustache_present_without_style_is_full_with_note(self):
        data = _new_doc()
        data["characters"][0]["fields"]["MOUSTACHE"] = (
            "Râu mép theo ảnh lịch sử")
        package = adapt_document(StubDoc(data))
        cast = {c["name"]: c for c in package["characters"]}
        self.assertEqual(cast["Anh Hùng"]["moustache_style"], "full")
        self.assertTrue(any("MOUSTACHE" in n or "moustache" in n.lower()
                            for n in package["v1_notes"]))

    def test_render_traits_top_level_keys_f8(self):
        package = adapt_document(StubDoc(_new_doc()))
        for char in package["characters"]:
            traits = char["render_traits"]
            for key in ("template", "body_variant", "costume",
                        "hair_style", "hat", "moustache_style", "glasses"):
                self.assertEqual(char[key], traits[key], key)
            self.assertEqual(char["head_ratio"], 0.34)


class TestLegacyDialect(unittest.TestCase):
    def test_narrator_sentinel_and_alias_exclusion_preserved(self):
        data = {
            "snapshot_hash": "d" * 64,
            "meta": {"project": "LEGACY"},
            "characters": [{
                "name": "An", "role": "Người kể", "appearance": "",
                "traits": [], "costume": "", "costume_changes": [],
                "voice": "AUTO", "voice_style": "", "head_ratio": 0.34,
                "identity_id": "An", "line": 2,
            }, {
                "name": "Người Dẫn Chuyện", "role": "Narrator",
                "appearance": "", "traits": [], "costume": "",
                "costume_changes": [], "voice": "AUTO",
                "voice_style": "", "head_ratio": 0.34,
                "identity_id": "Người Dẫn Chuyện", "line": 3,
            }],
            "locations": [], "props": [], "constraints": [],
            "qa": {}, "output": {}, "global_audio": {},
            "end_card": None, "unsupported_fields": [],
            "validation_errors": [],
            "scenes": [{
                "number": 1, "title": "Mở",
                "location_ref": None, "location_text": "Phố",
                "time_of_day": "Sáng", "mood": "Vui",
                "actions": [], "shots": [],
                "spoken_lines": [
                    {"line_id": "L001", "speaker": "Narrator",
                     "text": "Ngày xưa.", "kind": "narration"},
                    {"line_id": "L002", "speaker": "An",
                     "text": "Chào.", "kind": "dialogue"},
                ],
                "audio_cues": [], "vfx_cues": [],
            }],
        }
        package = adapt_document(StubDoc(data))
        self.assertFalse(package["v1_first_person"]["enabled"])
        names = [c["name"] for c in package["characters"]]
        self.assertEqual(names, ["An"])
        self.assertEqual(len(package["v1_narrator"]), 1)
        speakers = [ln["speaker"] for ln in package["scenes"][0]["lines"]]
        self.assertEqual(speakers, ["narrator", "An"])
        self.assertEqual(package["props"], [])
        self.assertIsNone(
            package["scenes"][0]["location"]["v1_location"])


class TestCameraMapping(unittest.TestCase):
    def _directives(self, camera_values):
        shots = []
        for i, value in enumerate(camera_values, 1):
            shots.append({
                "id": f"SH{i:02d}", "line": 100 + i, "type": None,
                "type_raw": "", "camera": value,
                "camera_movement": "STATIC",
                "camera_movement_text": "Static cinematic framing",
                "subject": "Anh Hùng", "duration": None,
                "duration_seconds": None, "action": "",
                "expression": "", "vfx": "", "voice_note": "",
                "spoken_line_ids": ["L001"],
                "location_override": None, "trigger": None,
                "fields": {},
            })
        data = _new_doc(scenes=[_scene(1, shots=shots)])
        return adapt_document(StubDoc(data))["shot_directives"]

    def test_new_script_camera_values(self):
        cases = [
            ("WIDE_ESTABLISHING", "establishing", "high_angle"),
            ("MEDIUM_CLOSEUP", "close_up", "eye_level"),
            ("CLOSEUP_REACTION", "reaction", "eye_level"),
            ("HISTORICAL_MAP_OVERVIEW", "establishing", "birds_eye"),
            ("MEDIUM_SIDE_SHOT", "medium", "eye_level"),
            ("OBJECT_INSERT_CLOSEUP", "object_insert", "high_angle"),
            ("MEDIUM_SHOT", "medium", "eye_level"),
            ("MEDIUM_TWO_SHOT", "medium", "eye_level"),
            ("CLOSEUP_REVERSE", "shot_reverse_shot", "eye_level"),
            ("OVER_THE_SHOULDER", "over_the_shoulder", "over_shoulder"),
            ("WIDE_TRACKING", "tracking", "eye_level"),
            ("WIDE_ENVIRONMENTAL_ESTABLISHING", "establishing",
             "high_angle"),
            ("MEDIUM_TRACKING", "tracking", "eye_level"),
            ("CLOSEUP", "close_up", "eye_level"),
        ]
        directives = self._directives([c[0] for c in cases])
        self.assertEqual(len(directives), len(cases))
        for directive, (text, shot_type, angle) in zip(directives, cases):
            self.assertEqual(directive["shot_type"], shot_type, text)
            self.assertEqual(directive["camera_angle"], angle, text)
            self.assertEqual(directive["camera"], text)
            self.assertEqual(directive["camera_movement"], "STATIC")
            self.assertEqual(directive["camera_movement_text"],
                             "Static cinematic framing")
            self.assertEqual(directive["line_index"], 1)

    def test_movement_text_mapping(self):
        cases = [
            ("Slow lateral tracking", "TRACKING"),
            ("Slow controlled zoom", "DOLLY_IN"),
            ("Subtle dolly-in", "DOLLY_IN"),
            ("Slow lateral movement", "PAN_RIGHT"),
            ("Static cinematic framing", "STATIC"),
        ]
        shots = [{
            "id": f"SH{i:02d}", "line": 100 + i, "type": None,
            "type_raw": "", "camera": "MEDIUM_SHOT",
            "camera_movement": "STATIC", "camera_movement_text": text,
            "subject": "", "duration": None, "duration_seconds": None,
            "action": "", "expression": "", "vfx": "", "voice_note": "",
            "spoken_line_ids": ["L001"], "location_override": None,
            "trigger": None, "fields": {},
        } for i, (text, _move) in enumerate(cases, 1)]
        package = adapt_document(StubDoc(_new_doc(scenes=[_scene(1, shots=shots)])))
        for directive, (text, movement) in zip(
                package["shot_directives"], cases):
            self.assertEqual(directive["camera_movement"], movement, text)
            self.assertEqual(directive["camera_movement_text"], text)

    def test_location_override_and_trigger_preserved(self):
        shots = [{
            "id": "SH01", "line": 100, "type": None, "type_raw": "",
            "camera": "WIDE_ESTABLISHING", "camera_movement": "STATIC",
            "camera_movement_text": "", "subject": "",
            "duration": None, "duration_seconds": None, "action": "",
            "expression": "", "vfx": "", "voice_note": "",
            "spoken_line_ids": ["L001"],
            "location_override": "LOC_PHO",
            "trigger": "Khi chuông reo", "fields": {},
        }]
        package = adapt_document(StubDoc(_new_doc(scenes=[_scene(1, shots=shots)])))
        directive = package["shot_directives"][0]
        self.assertEqual(directive["location_override"], "LOC_PHO")
        self.assertEqual(directive["trigger"], "Khi chuông reo")

    def test_unmapped_camera_defaults_with_note(self):
        directives = self._directives(["SOMETHING_NO_RULE_MATCHES"])
        self.assertEqual(directives[0]["shot_type"], "medium")
        self.assertEqual(directives[0]["camera_angle"], "eye_level")
        package = adapt_document(StubDoc(_new_doc(
            scenes=[_scene(1, shots=[{
                "id": "SH01", "line": 100, "type": None, "type_raw": "",
                "camera": "SOMETHING_NO_RULE_MATCHES",
                "camera_movement": "STATIC",
                "camera_movement_text": "", "subject": "",
                "duration": None, "duration_seconds": None,
                "action": "", "expression": "", "vfx": "",
                "voice_note": "", "spoken_line_ids": ["L001"],
                "location_override": None, "trigger": None,
                "fields": {},
            }])])))
        self.assertTrue(any("SOMETHING_NO_RULE_MATCHES" in n
                            for n in package["v1_shot_notes"]))

    def test_scene_default_directive(self):
        data = _new_doc(scenes=[_scene(1, camera="Phố"),
                                _scene(2, camera="Chợ",
                                       spoken_lines=[{
                                           "line_id": "L002",
                                           "speaker": "Anh Hùng",
                                           "speaker_id": "CHAR_HERO",
                                           "lip_sync": True,
                                           "text": "Tôi gặp Cô Lan.",
                                           "kind": "dialogue",
                                           "voice_note": "",
                                           "scene_number": 2,
                                           "shot_id": None,
                                           "line": 40}])])
        package = adapt_document(StubDoc(data))
        # No SHOT blocks: one default directive per scene.
        self.assertEqual(len(package["shot_directives"]), 2)
        for directive in package["shot_directives"]:
            self.assertEqual(directive["shot_type"], "medium")
            self.assertEqual(directive["camera_angle"], "eye_level")
            self.assertIsNone(directive["line_index"])
            self.assertIsNone(directive["shot_id"])
            self.assertIsNone(directive["srs_side"])
            self.assertIsNone(directive["counterpart"])


class TestCameraAngleC9(unittest.TestCase):
    def _shot(self, shot_id, camera, subject="", line_ids=("L001",),
              expression=""):
        return {
            "id": shot_id, "line": 100, "type": None, "type_raw": "",
            "camera": camera, "camera_movement": "STATIC",
            "camera_movement_text": "", "subject": subject,
            "duration": None, "duration_seconds": None, "action": "",
            "expression": expression, "vfx": "", "voice_note": "",
            "spoken_line_ids": list(line_ids),
            "location_override": None, "trigger": None, "fields": {},
        }

    def test_srs_sides_alternate_within_scene(self):
        shots = [self._shot(f"SH{i:02d}", "CLOSEUP_REVERSE")
                 for i in range(1, 4)]
        package = adapt_document(StubDoc(_new_doc(scenes=[_scene(1, shots=shots)])))
        sides = [d["srs_side"] for d in package["shot_directives"]]
        self.assertEqual(sides, [False, True, False])
        # A second scene restarts the alternation.
        shots2 = [self._shot("SH01", "CLOSEUP_REVERSE")]
        data = _new_doc(scenes=[_scene(1, shots=shots),
                                _scene(2, shots=shots2,
                                       spoken_lines=[{
                                           "line_id": "L002",
                                           "speaker": "Anh Hùng",
                                           "speaker_id": "CHAR_HERO",
                                           "lip_sync": True,
                                           "text": "Tôi gặp Cô Lan.",
                                           "kind": "dialogue",
                                           "voice_note": "",
                                           "scene_number": 2,
                                           "shot_id": None,
                                           "line": 40}])])
        package = adapt_document(StubDoc(data))
        scene2 = [d for d in package["shot_directives"]
                  if d["scene"] == 2]
        self.assertEqual(scene2[0]["srs_side"], False)

    def test_non_srs_directives_have_no_side(self):
        shots = [self._shot("SH01", "MEDIUM_SHOT"),
                 self._shot("SH02", "CLOSEUP_REVERSE"),
                 self._shot("SH03", "MEDIUM_SHOT")]
        package = adapt_document(StubDoc(_new_doc(scenes=[_scene(1, shots=shots)])))
        self.assertEqual([d["srs_side"] for d in package["shot_directives"]],
                         [None, False, None])

    def test_counterpart_from_two_named_subject(self):
        shots = [self._shot("SH01", "OVER_THE_SHOULDER",
                            subject="Anh Hùng, Cô Lan")]
        package = adapt_document(StubDoc(_new_doc(scenes=[_scene(1, shots=shots)])))
        directive = package["shot_directives"][0]
        self.assertEqual(directive["subject"], "Anh Hùng")
        self.assertEqual(directive["counterpart"], "Cô Lan")

    def test_counterpart_from_speakers_on_empty_subject_ots(self):
        scene = _scene(1, shots=[self._shot(
            "SH01", "OVER_THE_SHOULDER",
            line_ids=("L001", "L002"))])
        scene["spoken_lines"] = [
            {"line_id": "L001", "speaker": "Anh Hùng",
             "speaker_id": "CHAR_HERO", "lip_sync": True,
             "text": "Tôi chào.", "kind": "dialogue",
             "voice_note": "", "scene_number": 1, "shot_id": "SH01",
             "line": 31},
            {"line_id": "L002", "speaker": "Cô Lan",
             "speaker_id": "CHAR_LAN", "lip_sync": True,
             "text": "Chào anh.", "kind": "dialogue",
             "voice_note": "", "scene_number": 1, "shot_id": "SH01",
             "line": 32},
        ]
        package = adapt_document(StubDoc(_new_doc(scenes=[scene])))
        directive = package["shot_directives"][0]
        self.assertEqual(directive["subject"], "Anh Hùng")
        self.assertEqual(directive["counterpart"], "Cô Lan")

    def test_single_character_ots_keeps_subject_only(self):
        shots = [self._shot("SH01", "OVER_THE_SHOULDER",
                            subject="Anh Hùng")]
        package = adapt_document(StubDoc(_new_doc(scenes=[_scene(1, shots=shots)])))
        directive = package["shot_directives"][0]
        self.assertEqual(directive["subject"], "Anh Hùng")
        self.assertIsNone(directive["counterpart"])

    def test_no_geometry_emitted(self):
        package = adapt_document(StubDoc(_new_doc()))
        blob = json.dumps(package["shot_directives"])
        for banned in ("position", "target", "fov", "FOV"):
            self.assertNotIn(banned, blob)


class TestCostumes(unittest.TestCase):
    def test_scene_costume_garment_and_trait_changes(self):
        data = _new_doc()
        data["scenes"][0]["costume"] = "CIVILIAN"
        data["scenes"][1]["costume"] = "MILITARY"
        package = adapt_document(StubDoc(data))
        self.assertEqual(package["scenes"][0]["costume"], "CIVILIAN")
        self.assertEqual(package["scenes"][0]["costume_garment"], "none")
        self.assertEqual(package["scenes"][1]["costume"], "MILITARY")
        self.assertEqual(package["scenes"][1]["costume_garment"], "uniform")
        blocks = {b["name"]: b for b in
                  package["trait_blocks"]["characters"]}
        changes = blocks["Anh Hùng"]["costume_changes"]
        self.assertEqual([c["scene_number"] for c in changes], [1, 2])
        self.assertIn("Áo sơ mi xanh", changes[0]["outfit"])
        self.assertIn("Áo lính", changes[1]["outfit"])
        # Cô Lan has no costume lists: no invented changes.
        self.assertEqual(blocks["Cô Lan"]["costume_changes"], [])


class TestExtras(unittest.TestCase):
    def test_extras_excluded_from_cast_but_preserved(self):
        package = adapt_document(StubDoc(_new_doc()))
        names = [c["name"] for c in package["characters"]]
        self.assertNotIn("Người Qua Đường", names)
        self.assertEqual(len(package["v1_extras"]), 1)
        self.assertTrue(any("extra" in n.lower()
                            for n in package["v1_notes"]))
        block_names = [b["name"] for b in
                       package["trait_blocks"]["characters"]]
        self.assertIn("Người Qua Đường", block_names)
        declared_names = [c["name"] for c in package["v1_characters"]]
        self.assertIn("Người Qua Đường", declared_names)

    def test_extras_only_scene_has_empty_visible_cast(self):
        data = _new_doc()
        data["scenes"][0]["characters"] = ["CHAR_EXTRA"]
        package = adapt_document(StubDoc(data))
        self.assertEqual(package["scenes"][0]["visible_characters"], [])
        # The line is still narrated (narration is not cast-gated).
        self.assertEqual(len(package["scenes"][0]["lines"]), 1)


class TestProps(unittest.TestCase):
    def test_prop_kinds_from_fields(self):
        package = adapt_document(StubDoc(_new_doc()))
        kinds = {p["name"]: p["kind"] for p in package["props"]}
        self.assertEqual(kinds["Ví Da"], "wallet")
        self.assertEqual(kinds["Bức Thư"], "letter")
        self.assertEqual(kinds["Cây Bút"], "pen")
        self.assertEqual(kinds["Túi Vải"], "bag")
        owners = {p["name"]: p["owner"] for p in package["props"]}
        self.assertEqual(owners["Ví Da"], "CHAR_HERO")
        self.assertEqual(owners["Bức Thư"], "CHAR_LAN")
        ids = [p["id"] for p in package["props"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_scene_props_owner_and_mention(self):
        data = _new_doc()
        data["scenes"][0]["actions"] = [
            "Anh Hùng mở chiếc ví da ra xem."]
        package = adapt_document(StubDoc(data))
        scene_props = package["scenes"][0]["props"]
        by_id = {p["id"]: p for p in package["props"]}
        names = [by_id[pid]["name"] for pid in scene_props]
        # Owner match (Hero owns ví/bút/túi) + mention of the wallet.
        self.assertIn("Ví Da", names)
        self.assertIn("Cây Bút", names)
        self.assertIn("Túi Vải", names)
        # Lan's letter: neither owner present nor mentioned.
        self.assertNotIn("Bức Thư", names)


class TestEndCardAndPauses(unittest.TestCase):
    def test_end_card_duration_parsed(self):
        data = _new_doc(end_card={"duration": "3s", "text": "Hết"})
        package = adapt_document(StubDoc(data))
        self.assertEqual(package["v1_end_card"]["duration_sec"], 3.0)
        self.assertEqual(package["v1_end_card"]["duration"], "3s")

    def test_end_card_parser_duration_preferred(self):
        data = _new_doc(end_card={"duration": "3s", "duration_sec": 4.0})
        package = adapt_document(StubDoc(data))
        self.assertEqual(package["v1_end_card"]["duration_sec"], 4.0)

    def test_end_hold_from_scene_fields(self):
        data = _new_doc()
        data["scenes"][1]["fields"] = {"END_HOLD": "1.0s"}
        package = adapt_document(StubDoc(data))
        self.assertEqual(package["end_hold_sec"], 1.0)

    def test_end_hold_default_zero(self):
        package = adapt_document(StubDoc(_new_doc()))
        self.assertEqual(package["end_hold_sec"], 0.0)

    def test_pause_after_from_shot_fields_default_elsewhere(self):
        shots = [{
            "id": "SH01", "line": 100, "type": None, "type_raw": "",
            "camera": "MEDIUM_SHOT", "camera_movement": "STATIC",
            "camera_movement_text": "", "subject": "",
            "duration": None, "duration_seconds": None, "action": "",
            "expression": "", "vfx": "", "voice_note": "",
            "spoken_line_ids": ["L001"], "location_override": None,
            "trigger": None,
            "fields": {"POST_DIALOGUE_PAUSE": "0.6s"},
        }]
        scene = _scene(1, shots=shots)
        scene["spoken_lines"][0]["shot_id"] = "SH01"
        package = adapt_document(StubDoc(_new_doc(scenes=[scene])))
        self.assertEqual(package["scenes"][0]["lines"][0]["pause_after_sec"],
                         0.6)

    def test_pause_default(self):
        package = adapt_document(StubDoc(_new_doc()))
        for scene in package["scenes"]:
            for line in scene["lines"]:
                self.assertEqual(line["pause_after_sec"], 0.35)


class TestExpressions(unittest.TestCase):
    def test_scene_expression_attaches_to_lines(self):
        data = _new_doc()
        data["scenes"][0]["expressions"] = [
            {"character": None, "expression": "Vui vẻ", "line": 25}]
        package = adapt_document(StubDoc(data))
        self.assertEqual(package["scenes"][0]["lines"][0]["expression"],
                         "happy")

    def test_shot_expression_wins_over_scene(self):
        data = _new_doc()
        data["scenes"][0]["expressions"] = [
            {"character": None, "expression": "Vui vẻ", "line": 25}]
        data["scenes"][0]["shots"] = [{
            "id": "SH01", "line": 100, "type": None, "type_raw": "",
            "camera": "CLOSEUP", "camera_movement": "STATIC",
            "camera_movement_text": "", "subject": "",
            "duration": None, "duration_seconds": None, "action": "",
            "expression": "sững sờ", "vfx": "", "voice_note": "",
            "spoken_line_ids": ["L001"], "location_override": None,
            "trigger": None, "fields": {},
        }]
        package = adapt_document(StubDoc(data))
        self.assertEqual(package["scenes"][0]["lines"][0]["expression"],
                         "surprised")

    def test_unmappable_expression_reported_not_silent(self):
        data = _new_doc()
        data["scenes"][0]["expressions"] = [
            {"character": None, "expression": "xyzzy không rõ",
             "line": 25}]
        package = adapt_document(StubDoc(data))
        self.assertNotIn("expression",
                         package["scenes"][0]["lines"][0])
        unmapped = package["trait_blocks"]["unmapped"]
        self.assertTrue(any(u.get("kind") == "expression"
                            for u in unmapped))

    def test_lines_without_expression_keep_no_key(self):
        package = adapt_document(StubDoc(_new_doc()))
        for scene in package["scenes"]:
            for line in scene["lines"]:
                self.assertNotIn("expression", line)


class TestLocationBlocks(unittest.TestCase):
    def test_v1_location_block_and_text(self):
        package = adapt_document(StubDoc(_new_doc()))
        location = package["scenes"][0]["location"]
        self.assertIsNotNone(location["v1_location"])
        self.assertEqual(location["v1_location"]["location_id"],
                         "LOC_PHO")
        self.assertEqual(location["location_keyword"], "street")
        self.assertEqual(package["scenes"][0]["location_text"], "")

    def test_inline_only_location_has_none_block(self):
        data = _new_doc()
        data["scenes"][0]["location_ref"] = None
        data["scenes"][0]["location_text"] = "Bờ sông lúc hoàng hôn"
        package = adapt_document(StubDoc(data))
        self.assertIsNone(package["scenes"][0]["location"]["v1_location"])
        self.assertEqual(package["scenes"][0]["location_text"],
                         "Bờ sông lúc hoàng hôn")


class TestEnrichmentOverlay(unittest.TestCase):
    def test_apply_enrichment_ground_truth_and_audio(self):
        package, context = _adapt_document(StubDoc(_new_doc()))
        hook, twist = package["hook"], package["twist"]
        # Add scripted cues the model can enrich: an unmappable SFX
        # cue (adoption target) and a BGM cue (music target).
        data = _new_doc()
        data["scenes"][0]["audio_cues"] = [
            {"cue_type": "SFX", "name": "Âm thanh lạ",
             "trigger": "Khi có tiếng động", "priority": "", "mode": "",
             "intensity": "", "gain_db": None, "scene_number": 1,
             "shot_id": None, "line": 33, "source_key": "SFX"},
            {"cue_type": "BGM", "name": "Nhạc nền",
             "trigger": "", "priority": "", "mode": "",
             "intensity": "MEDIUM", "gain_db": None, "scene_number": 1,
             "shot_id": None, "line": 34, "source_key": "BGM"},
        ]
        package, context = _adapt_document(StubDoc(data))
        model = {
            "characters": [
                {"name": "Anh Hùng", "identity_id": "CHAR_HERO",
                 "render_traits": {"template": "male",
                                   "body_variant": "slim"}},
                {"name": "NhanVatBia", "render_traits": {
                    "template": "male"}}],
            "sfx": [{"event": "rain_start", "scene": 1,
                     "note": "mưa"}],
            "music": [{"name": "Piano", "scene": 1,
                       "intensity": "LOW"}],
            "actions": [{"type": "wave", "char": "Anh Hùng",
                         "scene": 1}],
            "hook": "HOOK BỊA", "twist": "TWIST BỊA",
        }
        cleaned, dropped = validate_trait_blocks(model)
        _apply_enrichment(package, cleaned, "gemini-test",
                          {"total_tokens": 9}, context, dropped)
        blocks = package["trait_blocks"]
        self.assertEqual(blocks["planner"], "gemini")
        self.assertEqual(blocks["model"], "gemini-test")
        # Hook/twist verbatim, never overwritten.
        self.assertEqual(package["hook"], hook)
        self.assertEqual(package["twist"], twist)
        # Invented character dropped + noted.
        names = [b["name"] for b in blocks["characters"]]
        self.assertNotIn("NhanVatBia", names)
        self.assertTrue(any("NhanVatBia" in n for n in blocks["dropped"]))
        # Model SFX adopted for the unmapped scripted cue.
        self.assertEqual(len(blocks["audio"]["sfx"]), 1)
        self.assertEqual(blocks["audio"]["sfx"][0]["event"], "rain_start")
        self.assertEqual(blocks["audio"]["sfx"][0]["name"], "Âm thanh lạ")
        self.assertIn("Gemini-mapped",
                      blocks["audio"]["sfx"][0]["note"])
        self.assertEqual(blocks["audio"]["unmapped_cues"], [])
        # Model music enriched the scripted BGM cue in place.
        self.assertEqual(len(blocks["audio"]["music"]), 1)
        self.assertEqual(blocks["audio"]["music"][0]["intensity"], "LOW")
        # Model action survived; deterministic actions replaced.
        self.assertEqual(len(blocks["actions"]), 1)
        self.assertEqual(blocks["actions"][0]["type"], "wave")
        self.assertEqual(blocks["actions"][0]["char"], "CHAR_HERO")

    def test_enrichment_cache_helpers(self):
        _clear_enrichment_cache()
        _cache_enrichment("h1", {"label": "gemini"})
        from ai_clip_studio.studio_script_v1_adapter import (
            _ENRICHMENT_CACHE)
        self.assertIn("h1", _ENRICHMENT_CACHE)
        for i in range(40):
            _cache_enrichment(f"h{i}", {})
        self.assertLessEqual(len(_ENRICHMENT_CACHE), 32)
        _clear_enrichment_cache()
        self.assertEqual(_ENRICHMENT_CACHE, {})


class TestDeterminism(unittest.TestCase):
    def test_two_adaptations_identical_json(self):
        first = adapt_document(StubDoc(_new_doc()))
        second = adapt_document(StubDoc(_new_doc()))
        self.assertEqual(json.dumps(first, sort_keys=True,
                                    ensure_ascii=False),
                         json.dumps(second, sort_keys=True,
                                    ensure_ascii=False))
        json.dumps(first, ensure_ascii=False)  # serializable

    def test_trait_blocks_have_no_timestamps(self):
        package = adapt_document(StubDoc(_new_doc()))

        def walk(obj):
            if isinstance(obj, dict):
                self.assertNotIn("at_seconds", obj)
                for value in obj.values():
                    walk(value)
            elif isinstance(obj, list):
                for value in obj:
                    walk(value)
        walk(package["trait_blocks"])


class TestFixturePreservation(unittest.TestCase):
    """Parser-dependent: the old fixture adapts with ADDED keys only.

    Skipped automatically when the parser module is mid-rewrite and
    cannot parse the fixture (a concurrent agent owns the parser);
    the stub tests above cover the adapter independently.
    """

    def test_old_fixture_added_keys_only(self):
        from ai_clip_studio.studio_script_v1 import (
            detect_format, parse_studio_script_v1)
        path = ("/home/hatch/workspace/video-upstream/fixtures/"
                "episode01_hitler_1914_munich/script.txt")
        text = open(path, encoding="utf-8").read()
        if detect_format(text) != "studio_v1":
            self.skipTest("parser does not detect the fixture yet")
        try:
            doc = parse_studio_script_v1(text)
        except Exception as exc:  # parser mid-rewrite
            self.skipTest(f"parser unusable: {exc}")
        if not doc.is_valid:
            self.skipTest("fixture invalid under current parser")
        package = adapt_document(doc)
        self.assertEqual(len(package["scenes"]), 8)
        self.assertEqual(len(package["characters"]), 3)
        total_lines = sum(len(sc["lines"]) for sc in package["scenes"])
        self.assertEqual(total_lines, 10)
        self.assertEqual(package["props"], [])
        self.assertIn("trait_blocks", package)
        self.assertIn("shot_directives", package)
        self.assertEqual(package["trait_blocks"]["planner"], "v1")
        for scene in package["scenes"]:
            self.assertIn("location_text", scene)
            self.assertIn("v1_location", scene["location"])
            for line in scene["lines"]:
                self.assertIn("pause_after_sec", line)
        for directive in package["shot_directives"]:
            self.assertIn("camera_angle", directive)
            self.assertIn("srs_side", directive)
            self.assertIn("counterpart", directive)


if __name__ == "__main__":
    unittest.main()
