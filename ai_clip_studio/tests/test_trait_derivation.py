"""Tests for ai_clip_studio.trait_derivation (shared derivation).

Covers word-boundary identity rules (including the substring trap
that once read a moustache out of an unrelated word), prop/SFX/
expression/camera mappings, action directives, audio blocks,
trait-block validation, and the sync tests that keep the mirrored
engine vocabularies identical.
"""
from __future__ import annotations

import unittest

from ai_clip_studio.trait_derivation import (
    CAMERA_ANGLES,
    COLOR_WORDS,
    DEFAULT_ANGLE_BY_SHOT,
    EXPRESSION_NAMES,
    HEAD_RATIO_LOCKED,
    PRIMITIVE_NAMES,
    PROP_KINDS,
    SFX_EVENTS,
    build_character_trait_block,
    build_trait_blocks,
    derive_action_directives,
    derive_audio_blocks,
    derive_location_traits,
    derive_prop_kind,
    derive_render_traits,
    derive_voice_hint,
    map_action_cue_to_primitive,
    map_action_text_to_primitive,
    map_camera_angle,
    map_camera_movement_text,
    map_camera_text_to_shot_and_angle,
    map_camera_text_to_shot_type,
    map_expression_text,
    map_scene_costume_to_garment,
    map_sfx_cue,
    moustache_style_from_fields,
    parse_duration_seconds,
    validate_trait_blocks,
)


def _traits(**kw):
    base = dict(name="An", role="", appearance="", costume_text="",
                traits=[], voice_style="")
    base.update(kw)
    return derive_render_traits(**base)


class TestVoiceHint(unittest.TestCase):
    def test_explicit_phrase_wins(self):
        self.assertEqual(derive_voice_hint("An", "", "", "giọng nữ trầm"),
                         "giọng nữ")
        self.assertEqual(derive_voice_hint("An", "", "", "giọng nam trầm"),
                         "giọng nam")

    def test_gender_field(self):
        self.assertEqual(derive_voice_hint("An", "", "", "", gender="Male"),
                         "giọng nam")
        self.assertEqual(derive_voice_hint("An", "", "", "", gender="Female"),
                         "giọng nữ")

    def test_honorifics_word_boundary(self):
        self.assertEqual(derive_voice_hint("Bà Tư", "", "", ""), "giọng nữ")
        self.assertEqual(derive_voice_hint("An", "Chàng trai", "", ""),
                         "giọng nam")
        # Bare "Nam" in a name never fires.
        self.assertEqual(derive_voice_hint("Thanh Nam", "", "", ""), "")
        self.assertEqual(derive_voice_hint("An", "Người bán hàng", "", ""),
                         "")


class TestRenderTraits(unittest.TestCase):
    def test_moustache_word_boundary_trap(self):
        # "Bavarian" contains "ria" but is not a moustache.
        traits = _traits(name="Bà Chủ", appearance="tạp dề Bavarian")
        self.assertEqual(traits["moustache_style"], "none")
        traits = _traits(appearance="ria mép nhỏ")
        self.assertEqual(traits["moustache_style"], "toothbrush")
        traits = _traits(appearance="râu quai nón rậm")
        self.assertEqual(traits["moustache_style"], "full")
        traits = _traits(appearance="để râu")
        self.assertEqual(traits["moustache_style"], "full")

    def test_moustache_field_styles(self):
        style, note = moustache_style_from_fields(
            {"MOUSTACHE": "toothbrush style"})
        self.assertEqual(style, "toothbrush")
        self.assertIsNone(note)
        style, note = moustache_style_from_fields(
            {"MOUSTACHE": "handlebar"})
        self.assertEqual(style, "handlebar")
        style, note = moustache_style_from_fields(
            {"MOUSTACHE": "Period-appropriate moustache from photos"})
        self.assertEqual(style, "full")
        self.assertIsNotNone(note)
        style, note = moustache_style_from_fields({"MOUSTACHE": "NONE"})
        self.assertEqual(style, "none")
        style, note = moustache_style_from_fields({})
        self.assertIsNone(style)
        # An explicit NONE field wins over prose mentioning a beard.
        traits = _traits(appearance="râu rậm",
                         fields={"MOUSTACHE": "NONE"})
        self.assertEqual(traits["moustache_style"], "none")
        # A field naming a moustache wins over silent prose.
        traits = _traits(fields={"MOUSTACHE": "moustache"})
        self.assertEqual(traits["moustache_style"], "full")

    def test_elderly_detection(self):
        traits = _traits(name="Bà Cụ", role="bà lão bán hàng")
        self.assertEqual(traits["template"], "elderly")
        traits = _traits(appearance="ông già tóc bạc")
        self.assertEqual(traits["template"], "elderly")
        traits = _traits(fields={"AGE": "72"})
        self.assertEqual(traits["template"], "elderly")
        traits = _traits(fields={"AGE": "25"})
        self.assertEqual(traits["template"], "male")

    def test_child_vs_young_woman(self):
        traits = _traits(name="Cô Lan", role="Cô gái trẻ bán hoa")
        self.assertEqual(traits["template"], "female")
        traits = _traits(name="Bé Bo", role="Cậu bé bán báo")
        self.assertEqual(traits["template"], "child")
        traits = _traits(role="đứa trẻ mồ côi")
        self.assertEqual(traits["template"], "child")

    def test_female_male_and_gender_field(self):
        self.assertEqual(_traits(name="Chị Hoa")["template"], "female")
        self.assertEqual(_traits(name="An")["template"], "male")
        self.assertEqual(
            _traits(name="Alex", fields={"GENDER": "Female"})["template"],
            "female")
        self.assertEqual(
            _traits(name="Alex", fields={"GENDER": "Male"})["template"],
            "male")

    def test_costume_garment(self):
        self.assertEqual(_traits(costume_text="Áo dài vàng")["costume"],
                         "dress")
        self.assertEqual(_traits(costume_text="quân phục dã chiến")["costume"],
                         "uniform")
        self.assertEqual(_traits(costume_text="áo khoác nâu")["costume"],
                         "none")

    def test_hair_hat_glasses(self):
        self.assertEqual(
            _traits(fields={"HAIR": "Dark brown, side-parted"})["hair_style"],
            "side_part")
        self.assertEqual(_traits(appearance="tóc dài")["hair_style"], "long")
        self.assertEqual(_traits(appearance="đội mũ nồi")["hat"], "bowler")
        self.assertEqual(_traits(appearance="mũ quân đội")["hat"], "none")
        self.assertTrue(_traits(appearance="đeo kính cận")["glasses"])
        # Standalone respectful "kính" is not glasses.
        self.assertFalse(_traits(appearance="kính thưa bà con")["glasses"])
        self.assertTrue(_traits(fields={"GLASSES": "yes"})["glasses"])

    def test_body_variant_and_colors(self):
        self.assertEqual(_traits(role="gầy gò")["body_variant"], "slim")
        self.assertEqual(
            _traits(fields={"BODY_TYPE": "Slim"})["body_variant"], "slim")
        self.assertEqual(_traits(role="vạm vỡ")["body_variant"], "sturdy")
        self.assertEqual(_traits(appearance="áo khoác nâu")["jacket_color"],
                         "#7a4a2b")
        self.assertEqual(_traits(appearance="khăn xám")["jacket_color"],
                         "#6b7280")
        self.assertEqual(_traits()["jacket_color"], "#3a4a5f")

    def test_shape_and_height(self):
        traits = _traits(height_px=560)
        self.assertEqual(
            set(traits),
            {"description", "voice_hint", "template", "body_variant",
             "costume", "hair_style", "hat", "moustache_style",
             "glasses", "jacket_color", "height_px"})
        self.assertEqual(traits["height_px"], 560)
        self.assertEqual(_traits()["height_px"], 540)

    def test_fields_never_scanned_whole(self):
        # A costume field mentioning a place name must not create a
        # moustache or change the template.
        traits = _traits(fields={
            "COSTUME_MILITARY": ["Quân phục Bavaria năm 1914"],
            "NATIONALITY": "Austrian"})
        self.assertEqual(traits["moustache_style"], "none")
        self.assertEqual(traits["template"], "male")


class TestLocationTraits(unittest.TestCase):
    def test_keywords(self):
        self.assertEqual(
            derive_location_traits(
                inline_text="Vạn Lý Trường Thành")["location_keyword"],
            "great_wall")
        self.assertEqual(
            derive_location_traits(inline_text="Tháp Eiffel")[
                "location_keyword"], "eiffel_tower")
        self.assertEqual(
            derive_location_traits(inline_text="Phố mưa")[
                "location_keyword"], "rainy_street")
        self.assertEqual(
            derive_location_traits(inline_text="Căn gác nhỏ")[
                "location_keyword"], "street")

    def test_time_and_mood(self):
        traits = derive_location_traits(time_of_day_text="Đêm khuya",
                                        mood_text="Lạnh lẽo")
        self.assertEqual(traits["time_of_day"], "night")
        self.assertEqual(traits["mood"], "cold")
        traits = derive_location_traits(time_of_day_text="Morning",
                                        mood_text="Warm")
        self.assertEqual(traits["time_of_day"], "day")
        self.assertEqual(traits["mood"], "warm")
        self.assertEqual(
            derive_location_traits(time_of_day_text="Hoàng hôn")[
                "time_of_day"], "day")

    def test_setting_falls_back_to_name(self):
        traits = derive_location_traits(name="Chợ đêm")
        self.assertEqual(traits["setting"], "Chợ đêm")
        traits = derive_location_traits(name="Chợ đêm",
                                        inline_text="Chợ ven sông")
        self.assertEqual(traits["setting"], "Chợ ven sông")


class TestPropKinds(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(derive_prop_kind("Ví Da", ""), "wallet")
        self.assertEqual(derive_prop_kind("PROP_WALLET",
                                          "Old leather wallet"), "wallet")
        self.assertEqual(derive_prop_kind("Chiếc Ô", ""), "umbrella")
        self.assertEqual(derive_prop_kind("Tờ Báo", ""), "newspaper")
        self.assertEqual(derive_prop_kind("PROP_LETTER",
                                          "enlistment document"), "letter")
        self.assertEqual(derive_prop_kind("Vé Xe", ""), "ticket")
        self.assertEqual(derive_prop_kind("Cốc Nước", ""), "cup")
        self.assertEqual(derive_prop_kind("PROP_MILITARY_BAG",
                                          "Military field bag"), "bag")
        self.assertEqual(derive_prop_kind("Chìa Khóa", ""), "key")
        self.assertEqual(derive_prop_kind("Quyển Sách", ""), "book")
        self.assertEqual(derive_prop_kind("Giỏ Hoa",
                                          "giỏ tre đầy hoa"), "flower")

    def test_pen_is_own_kind(self):
        self.assertEqual(
            derive_prop_kind("PROP_PEN", "writing pen"), "pen")
        self.assertEqual(derive_prop_kind("Cây Bút", "bút viết"), "pen")
        self.assertEqual(derive_prop_kind("Vật Lạ", "không rõ"), "generic")


class TestSfxMapping(unittest.TestCase):
    def test_mapped(self):
        self.assertEqual(map_sfx_cue("Tiếng mưa rơi"), "rain_start")
        self.assertEqual(map_sfx_cue("Tiếng bước chân"), "foot_contact")
        self.assertEqual(map_sfx_cue("Gõ cửa"), "door_contact")
        self.assertEqual(map_sfx_cue("Mở cửa"), "door_rotation")
        self.assertEqual(map_sfx_cue("Lật báo"), "paper_movement")
        self.assertEqual(map_sfx_cue("Đặt cọ xuống bàn"), "object_impact")
        self.assertEqual(map_sfx_cue("Thở dài não nề"),
                         "character_reaction")

    def test_unmapped(self):
        self.assertIsNone(map_sfx_cue("Tiếng rao hàng"))
        self.assertIsNone(map_sfx_cue("Wallet opening"))
        self.assertIsNone(map_sfx_cue("Crowd murmur"))
        # A bare "open" is not a door event.
        self.assertIsNone(map_sfx_cue("Open"))
        self.assertIsNone(map_sfx_cue(""))
        self.assertIsNone(map_sfx_cue("Melancholic piano"))

    def test_cooccurrence_rules(self):
        # "rustle" needs a paper word: leather is not paper.
        self.assertIsNone(map_sfx_cue("Soft leather rustle"))
        self.assertEqual(map_sfx_cue("Paper rustle"), "paper_movement")
        self.assertEqual(map_sfx_cue("Tiếng giấy sột soạt"),
                         "paper_movement")
        # "xuống" needs a put-down verb: looking down is not impact.
        self.assertIsNone(map_sfx_cue("Nhìn xuống phố"))
        self.assertEqual(map_sfx_cue("Đặt ví xuống"), "object_impact")
        self.assertEqual(map_sfx_cue("Để chiếc túi xuống bàn"),
                         "object_impact")


class TestExpressionMapping(unittest.TestCase):
    def test_vietnamese_families(self):
        self.assertEqual(map_expression_text("sững sờ"), "surprised")
        self.assertEqual(map_expression_text("Sững người"), "surprised")
        self.assertEqual(map_expression_text("ngạc nhiên"), "surprised")
        self.assertEqual(map_expression_text("buồn bã"), "sad")
        self.assertEqual(map_expression_text("vui vẻ"), "happy")
        self.assertEqual(map_expression_text("lo lắng"), "worried")
        self.assertEqual(map_expression_text("giận dữ"), "angry")
        self.assertEqual(map_expression_text("trầm ngâm"), "thinking")
        self.assertEqual(map_expression_text("hoài nghi"), "doubtful")
        self.assertEqual(map_expression_text("bình thản"), "neutral")

    def test_bare_sung_frozen_startled(self):
        # Bare "sững" (frozen/startled) maps to "surprised", alone or
        # in a sentence; word boundaries still apply, so "sững" glued
        # inside a longer token does not fire.
        self.assertEqual(map_expression_text("sững"), "surprised")
        self.assertEqual(map_expression_text("Sững"), "surprised")
        self.assertEqual(map_expression_text("Bà cụ sững người."),
                         "surprised")
        self.assertIsNone(map_expression_text("sữngsờ"))

    def test_word_boundary_ua(self):
        # "ủa" never fires inside "của".
        self.assertIsNone(map_expression_text("của cháu"))
        self.assertEqual(map_expression_text("Ủa, sao vậy?"), "surprised")

    def test_english_words(self):
        self.assertEqual(map_expression_text("Thoughtful"), "thinking")
        self.assertEqual(map_expression_text("Disappointed"), "sad")
        self.assertEqual(map_expression_text("Uncertain"), "doubtful")
        self.assertEqual(map_expression_text("Skeptical"), "doubtful")
        self.assertEqual(map_expression_text("surprised"), "surprised")

    def test_earliest_keyword_wins(self):
        self.assertEqual(map_expression_text("Grim, reflective"), "sad")
        self.assertEqual(map_expression_text("Reflective, uncertain"),
                         "thinking")

    def test_no_match(self):
        self.assertIsNone(map_expression_text("Biểu cảm mẫu"))
        self.assertIsNone(map_expression_text(""))
        self.assertIsNone(map_expression_text("   "))


class TestCameraMapping(unittest.TestCase):
    def test_shot_types(self):
        cases = [
            ("WIDE_ESTABLISHING", "establishing"),
            ("MEDIUM_CLOSEUP", "close_up"),
            ("CLOSEUP_REACTION", "reaction"),
            ("OBJECT_INSERT_CLOSEUP", "object_insert"),
            ("HISTORICAL_MAP_OVERVIEW", "establishing"),
            ("MEDIUM_SIDE_SHOT", "medium"),
            ("MEDIUM_SHOT", "medium"),
            ("MEDIUM_TWO_SHOT", "medium"),
            ("CLOSEUP_REVERSE", "shot_reverse_shot"),
            ("OVER_THE_SHOULDER", "over_the_shoulder"),
            ("WIDE_TRACKING", "tracking"),
            ("WIDE_ENVIRONMENTAL_ESTABLISHING", "establishing"),
            ("MEDIUM_TRACKING", "tracking"),
            ("CLOSEUP", "close_up"),
            ("EXTREME_CLOSE_UP", "extreme_close_up"),
        ]
        for text, expected in cases:
            shot_type, note = map_camera_text_to_shot_type(text)
            self.assertEqual(shot_type, expected, text)
            self.assertIsNone(note, text)

    def test_unmapped_defaults_with_note(self):
        shot_type, note = map_camera_text_to_shot_type("SOMETHING_ODD")
        self.assertEqual(shot_type, "medium")
        self.assertIsNotNone(note)
        shot_type, note = map_camera_text_to_shot_type("")
        self.assertEqual(shot_type, "medium")
        self.assertIsNotNone(note)

    def test_movements(self):
        cases = [
            ("Slow lateral tracking", "TRACKING"),
            ("Slow controlled zoom", "DOLLY_IN"),
            ("Subtle dolly-in", "DOLLY_IN"),
            ("Slow lateral movement", "PAN_RIGHT"),
            ("Static cinematic framing", "STATIC"),
            ("Zoom out slowly", "DOLLY_OUT"),
            ("Pan left", "PAN_LEFT"),
            ("Tilt up", "TILT_UP"),
            ("Handheld", "HANDHELD"),
            ("", "STATIC"),
        ]
        for text, expected in cases:
            movement, _note = map_camera_movement_text(text)
            self.assertEqual(movement, expected, text)

    def test_movement_notes_for_assumed_direction(self):
        _m, note = map_camera_movement_text("Slow controlled zoom")
        self.assertIsNotNone(note)
        _m, note = map_camera_movement_text("Subtle dolly-in")
        self.assertIsNone(note)


class TestCameraAnglesC9(unittest.TestCase):
    """C9 (PROVISIONAL): CAMERA text -> (shot_type, camera_angle)."""

    def test_combined_map(self):
        cases = [
            ("OVER_THE_SHOULDER", "over_the_shoulder", "over_shoulder"),
            ("WIDE_ESTABLISHING", "establishing", "high_angle"),
            ("WIDE_ENVIRONMENTAL_ESTABLISHING", "establishing", "high_angle"),
            ("CLOSEUP_REACTION", "reaction", "eye_level"),
            ("OBJECT_INSERT_CLOSEUP", "object_insert", "high_angle"),
            ("HISTORICAL_MAP_OVERVIEW", "establishing", "birds_eye"),
            ("MEDIUM_SIDE_SHOT", "medium", "eye_level"),
            ("MEDIUM_SHOT", "medium", "eye_level"),
            ("MEDIUM_TWO_SHOT", "medium", "eye_level"),
            ("MEDIUM_CLOSEUP", "close_up", "eye_level"),
            ("MEDIUM_TRACKING", "tracking", "eye_level"),
            ("CLOSEUP", "close_up", "eye_level"),
            ("CLOSEUP_REVERSE", "shot_reverse_shot", "eye_level"),
            ("WIDE_TRACKING", "tracking", "eye_level"),
        ]
        for text, shot_type, angle in cases:
            got_type, got_angle, note = map_camera_text_to_shot_and_angle(text)
            self.assertEqual(got_type, shot_type, text)
            self.assertEqual(got_angle, angle, text)
            self.assertIsNone(note, text)

    def test_explicit_angle_words_override_defaults(self):
        self.assertEqual(map_camera_angle("LOW_ANGLE_CLOSEUP", "close_up"),
                         "low_angle")
        self.assertEqual(map_camera_angle("HIGH_ANGLE_MEDIUM", "medium"),
                         "high_angle")
        self.assertEqual(map_camera_angle("DUTCH_MEDIUM", "medium"), "dutch")
        self.assertEqual(map_camera_angle("AERIAL_ESTABLISHING",
                                          "establishing"), "birds_eye")
        self.assertEqual(map_camera_angle("OTS", "medium"), "over_shoulder")
        # "ots" must not fire inside "shots".
        self.assertEqual(map_camera_angle("TWO_SHOTS", "medium"), "eye_level")

    def test_default_table(self):
        self.assertEqual(map_camera_angle("", "establishing"), "high_angle")
        self.assertEqual(map_camera_angle("", "object_insert"), "high_angle")
        self.assertEqual(map_camera_angle("", "over_the_shoulder"),
                         "over_shoulder")
        self.assertEqual(map_camera_angle("", "medium"), "eye_level")
        self.assertEqual(map_camera_angle("SOMETHING_ODD", "tracking"),
                         "eye_level")
        self.assertEqual(map_camera_angle("", "unknown_type"), "eye_level")

    def test_angle_vocabulary(self):
        self.assertEqual(
            set(CAMERA_ANGLES),
            {"eye_level", "low_angle", "high_angle", "dutch",
             "over_shoulder", "birds_eye"})
        self.assertEqual(set(DEFAULT_ANGLE_BY_SHOT), {
            "establishing", "medium", "close_up", "extreme_close_up",
            "over_the_shoulder", "reaction", "object_insert", "tracking",
            "shot_reverse_shot", "medium_close_up", "graphic_insert"})
        self.assertTrue(all(a in CAMERA_ANGLES
                            for a in DEFAULT_ANGLE_BY_SHOT.values()))


class TestSceneCostume(unittest.TestCase):
    def test_garments(self):
        self.assertEqual(map_scene_costume_to_garment("CIVILIAN"), "none")
        self.assertEqual(map_scene_costume_to_garment("MILITARY"), "uniform")
        self.assertEqual(map_scene_costume_to_garment("military"), "uniform")
        self.assertEqual(map_scene_costume_to_garment(""), "")
        self.assertEqual(map_scene_costume_to_garment("FANCY"), "")


class TestActionDirectives(unittest.TestCase):
    def test_primitive_mapping(self):
        self.assertEqual(map_action_text_to_primitive("An đi bộ trên phố"),
                         "walk_to")
        self.assertEqual(map_action_text_to_primitive("An chạy tới"),
                         "run_to")
        self.assertEqual(map_action_text_to_primitive("An nhặt ví lên"),
                         "kneel_pick")
        self.assertEqual(map_action_text_to_primitive("An đưa ví cho Bình"),
                         "give_to")
        self.assertEqual(map_action_text_to_primitive("An vẫy tay"),
                         "wave")
        self.assertEqual(map_action_text_to_primitive("An gật đầu"), "nod")
        self.assertEqual(map_action_text_to_primitive("An ngồi xuống"),
                         "sit_down")
        self.assertEqual(map_action_text_to_primitive("An nhìn quanh"),
                         "look_at")
        self.assertEqual(map_action_text_to_primitive("An quay lại"),
                         "turn_to")
        self.assertIsNone(map_action_text_to_primitive("An viết thư"))
        self.assertIsNone(map_action_text_to_primitive("An hơi cúi đầu"))

    def test_cue_mapping(self):
        self.assertEqual(map_action_cue_to_primitive("walk"), "walk_to")
        self.assertEqual(map_action_cue_to_primitive("bend_pick"),
                         "kneel_pick")
        # board_vehicle is NOT in the PRIMITIVES registry.
        self.assertIsNone(map_action_cue_to_primitive("board"))
        self.assertIsNone(map_action_cue_to_primitive("open"))

    def test_derive_reports_unmapped_never_substitutes(self):
        directives, unmapped = derive_action_directives(
            [{"text": "An đi bộ. An viết thư cho em.",
              "scene_number": 1, "shot_id": None, "source_line": None}],
            {"an": "An"})
        self.assertEqual([d["type"] for d in directives], ["walk_to"])
        self.assertEqual(directives[0]["char"], "An")
        self.assertIsNone(directives[0]["start"])
        self.assertEqual(len(unmapped), 1)
        self.assertEqual(unmapped[0]["kind"], "action")
        self.assertIn("viết thư", unmapped[0]["action_text"])
        # No camera-move substitution anywhere in the output.
        self.assertNotIn("camera", str(directives).lower())


class TestAudioBlocks(unittest.TestCase):
    def test_sfx_music_unmapped_and_no_timestamps(self):
        cues = [
            {"cue_type": "SFX", "name": "Tiếng mưa rơi", "trigger": "L001",
             "priority": "REQUIRED", "scene_number": 1, "shot_id": None,
             "line": 10, "source_key": "SFX"},
            {"cue_type": "SFX", "name": "Tiếng rao hàng", "trigger": "",
             "priority": "REQUIRED", "scene_number": 1, "shot_id": None,
             "line": 11, "source_key": "SFX"},
            {"cue_type": "BGM", "name": "Nhạc piano", "intensity": "LOW",
             "scene_number": 1, "shot_id": None, "line": 12,
             "source_key": "BGM"},
            {"cue_type": "AMBIENCE", "name": "Room tone",
             "scene_number": 1, "shot_id": None, "line": 13,
             "source_key": "AMBIENCE"},
            {"cue_type": "MEME", "name": "meme X", "scene_number": 1,
             "shot_id": None, "line": 14, "source_key": "MEME"},
        ]
        sfx, music, unmapped, dropped = derive_audio_blocks(cues)
        self.assertEqual(len(sfx), 1)
        self.assertEqual(sfx[0]["event"], "rain_start")
        self.assertNotIn("at_seconds", sfx[0])
        self.assertEqual(len(music), 1)
        self.assertNotIn("event", music[0])
        self.assertEqual(music[0]["intensity"], "LOW")
        self.assertEqual(
            [c["cue_type"] for c in unmapped], ["SFX", "AMBIENCE", "MEME"])
        self.assertEqual(dropped, [])

    def test_new_dialect_structured_cue(self):
        cues = [{"cue_type": "SFX", "event": "Wallet opening",
                 "fields": {"TYPE": "Soft leather rustle"},
                 "scene_number": 1, "shot_id": "SH01", "line": 20,
                 "source_key": "SFX"}]
        sfx, _music, unmapped, _dropped = derive_audio_blocks(cues)
        self.assertEqual(sfx, [])
        self.assertEqual(len(unmapped), 1)
        self.assertEqual(unmapped[0]["name"], "Wallet opening")


class TestValidateTraitBlocks(unittest.TestCase):
    def test_valid_nested_and_flat(self):
        blocks, dropped = validate_trait_blocks({
            "characters": [{
                "name": "An",
                "render_traits": {"template": "male", "glasses": True,
                                  "jacket_color": "#112233"},
            }, {
                "name": "Bình", "template": "female",
                "moustache_style": "full",
            }],
            "locations": [{"scene": 1, "location_keyword": "street",
                           "mood": "warm", "time_of_day": "day"}],
            "shots": [{"scene": 1, "line_index": 1,
                       "shot_type": "over_the_shoulder"}],
            "sfx": [{"event": "rain_start", "scene": 1}],
            "music": [{"name": "Piano", "scene": 1, "intensity": "LOW"}],
            "actions": [{"type": "walk_to", "char": "An", "scene": 1}],
        })
        self.assertEqual(dropped, [])
        self.assertEqual(blocks["characters"][0]["render_traits"]["template"],
                         "male")
        self.assertEqual(blocks["characters"][1]["render_traits"]["template"],
                         "female")
        self.assertEqual(blocks["shots"][0]["shot_type"],
                         "over_the_shoulder")

    def test_invalid_values_dropped_with_notes(self):
        blocks, dropped = validate_trait_blocks({
            "characters": [{
                "name": "An",
                "render_traits": {"template": "alien",
                                  "jacket_color": "blue",
                                  "glasses": "yes"},
                "head_ratio": 0.42,
            }],
            "locations": [{"scene": 1, "location_keyword": "moon"}],
            "shots": [{"scene": 1, "line_index": 1, "shot_type": "dolly"}],
            "sfx": [{"event": "explosion", "scene": 1}],
            "actions": [{"type": "fly_away", "char": "An"}],
        })
        self.assertEqual(blocks["characters"][0]["render_traits"], {})
        self.assertEqual(blocks["locations"][0]["render_traits"], {})
        self.assertEqual(blocks["shots"], [])
        self.assertEqual(blocks["sfx"], [])
        self.assertEqual(blocks["actions"], [])
        self.assertGreaterEqual(len(dropped), 6)
        self.assertTrue(any("head_ratio" in n for n in dropped))
        self.assertTrue(any("0.42" in n for n in dropped))

    def test_head_ratio_030_dropped(self):
        _blocks, dropped = validate_trait_blocks({
            "characters": [{"name": "An", "head_ratio": 0.30}]})
        self.assertTrue(any("head_ratio" in n for n in dropped))

    def test_music_must_not_reuse_sfx_names(self):
        blocks, dropped = validate_trait_blocks({
            "music": [{"name": "X", "scene": 1, "event": "rain_start"}]})
        self.assertNotIn("event", blocks["music"][0])
        self.assertTrue(any("SFX" in n for n in dropped))

    def test_never_crashes_on_garbage(self):
        for garbage in (None, "text", 42, [], {"characters": "nope"},
                        {"characters": [None, 3, {"name": 5}]},
                        {"actions": [{"type": None}]},
                        {"sfx": [{"event": None, "scene": "x"}]}):
            blocks, dropped = validate_trait_blocks(garbage)
            self.assertIsInstance(blocks, dict)
            self.assertIsInstance(dropped, list)
            self.assertEqual(
                set(blocks),
                {"characters", "locations", "shots", "sfx", "music",
                 "actions", "hook", "twist"})

    def test_directive_params_validated(self):
        blocks, dropped = validate_trait_blocks({
            "actions": [{"type": "walk_to", "char": "An",
                         "from_x": "far", "target": [1],
                         "hand": "middle", "duration": 2.0}]})
        directive = blocks["actions"][0]
        self.assertEqual(directive["duration"], 2.0)
        self.assertNotIn("from_x", directive)
        self.assertNotIn("target", directive)
        self.assertNotIn("hand", directive)
        self.assertEqual(len(dropped), 3)


class TestBuilders(unittest.TestCase):
    def test_envelope_shape(self):
        blocks = build_trait_blocks(
            snapshot_hash="abc", planner="fallback", model=None,
            usage=None, reason="r")
        self.assertEqual(
            set(blocks),
            {"snapshot_hash", "planner", "model", "usage", "reason",
             "characters", "locations", "audio", "actions", "unmapped",
             "dropped"})
        self.assertEqual(set(blocks["audio"]),
                         {"sfx", "music", "unmapped_cues"})

    def test_character_block_locks_head_ratio(self):
        dropped = []
        block = build_character_trait_block(
            identity_id="X", name="X", head_ratio=0.30,
            dropped_notes=dropped)
        self.assertEqual(block["head_ratio"], HEAD_RATIO_LOCKED)
        self.assertEqual(len(dropped), 1)

    def test_duration_parsing(self):
        self.assertEqual(parse_duration_seconds("3s"), 3.0)
        self.assertEqual(parse_duration_seconds("0.6s"), 0.6)
        self.assertEqual(parse_duration_seconds("350ms"), 0.35)
        self.assertEqual(parse_duration_seconds(3.0), 3.0)
        self.assertEqual(parse_duration_seconds("4"), 4.0)
        self.assertIsNone(parse_duration_seconds("AUTO"))
        self.assertIsNone(parse_duration_seconds("85-100 seconds"))
        self.assertEqual(parse_duration_seconds("bad", default=1.0), 1.0)


class TestSyncWithEngine(unittest.TestCase):
    def test_color_words_match_fallback(self):
        from ai_clip_studio.planner_fallback import COLOR_WORDS as FALLBACK
        self.assertEqual(COLOR_WORDS, FALLBACK)

    def test_primitives_match_registry(self):
        from ai_clip_studio.animation.primitives import PRIMITIVES
        self.assertEqual(set(PRIMITIVE_NAMES), set(PRIMITIVES))
        # 37 = 35 + crouch + receive_prop (A2 semantic props, 2026-11-12).
        self.assertEqual(len(PRIMITIVE_NAMES), 37)

    def test_expressions_match_face_system(self):
        from ai_clip_studio.animation.character_art import EXPRESSIONS
        self.assertEqual(set(EXPRESSION_NAMES), set(EXPRESSIONS))
        self.assertEqual(len(EXPRESSION_NAMES), 8)

    def test_sfx_events_match_audio_map(self):
        from ai_clip_studio.audio_events import EVENT_SFX_MAP
        # The planner vocabulary is the event map minus the ambience
        # entry, which is not a planner SFX event.
        self.assertEqual(set(SFX_EVENTS),
                         set(EVENT_SFX_MAP) - {"crowd murmur"})

    def test_prop_kinds_match_renderer_when_defined(self):
        # 25 kinds since wiring item 7 (2026-11-12): + the 13
        # geometry kinds, kept identical in both constants.
        own = {"wallet", "umbrella", "newspaper", "letter", "ticket",
               "cup", "bag", "key", "book", "flower", "pen", "generic",
               "bolt", "hammer", "trident", "helmet", "sword", "staff",
               "shield", "crown", "ring", "hat", "chain", "stone",
               "boulder"}
        self.assertEqual(set(PROP_KINDS), own)
        try:
            import ai_clip_studio.product_renderer as renderer
        except ImportError as exc:
            # The engine is mid-rewrite by another agent; the sync
            # assertion cannot run until it imports again.
            self.skipTest(f"product_renderer unimportable: {exc}")
        engine_kinds = getattr(renderer, "PROP_KINDS", None)
        if engine_kinds is None:
            self.skipTest("engine PROP_KINDS not defined yet; "
                          "re-verify at integration")
        self.assertEqual(set(PROP_KINDS), set(engine_kinds))

    def test_camera_angles_match_planner(self):
        from ai_clip_studio.camera_planner import ANGLES
        self.assertEqual(tuple(CAMERA_ANGLES), tuple(ANGLES))

    def test_default_angle_table_matches_planner(self):
        from ai_clip_studio.camera_planner import _ANGLE_BY_SHOT
        self.assertEqual(dict(DEFAULT_ANGLE_BY_SHOT), dict(_ANGLE_BY_SHOT))


if __name__ == "__main__":
    unittest.main()
