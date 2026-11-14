"""Generalization tests: generic visual profile, parser aliases and
non-action directive routing.

The fixtures here deliberately are NOT the project's acceptance
stories: a primate temple guard, a feline night-market courier and a
bovine forge smith. No engine branch may depend on a story or a
character name, so a special-case fix for one script fails here.

Three contracts are pinned:
  1. Character features are closed-vocabulary DATA (species / ears /
     tail / horns / face markings) with a controlled fallback.
  2. A documented key synonym (CAMERA_MOTION) is the same field at the
     parser boundary, never an unknown field.
  3. A sentence about the environment, sound or camera is routed to
     that discipline with its own category, never reported as a
     missing animation primitive.
"""
from __future__ import annotations

import unittest

from ai_clip_studio.animation import rig
from ai_clip_studio.animation.character_art import (
    draw_character_v4,
    make_character,
)
from ai_clip_studio.animation.primitives import standing
from ai_clip_studio.product_renderer import map_character
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.trait_derivation import (
    EAR_SHAPES,
    FACE_MARKING_STYLES,
    HORN_SHAPES,
    SPECIES_KINDS,
    TAIL_SHAPES,
    VISUAL_PROFILE_KEYS,
    classify_non_action_text,
    derive_action_directives,
    derive_render_traits,
    derive_visual_profile,
    merge_render_traits,
    validate_trait_blocks,
)

PROFILE_VOCAB = {
    "species": SPECIES_KINDS,
    "ears": EAR_SHAPES,
    "tail": TAIL_SHAPES,
    "horns": HORN_SHAPES,
    "face_markings": FACE_MARKING_STYLES,
}


def _codes(doc):
    return [(i.line, i.code) for i in doc.validation_errors]


def _script(char_blocks, body, title="Canh mau"):
    header = [
        "STUDIO SCRIPT V1",
        "PROJECT",
        "STORYTELLING_MODE: FIRST_PERSON_ROLEPLAY",
        "PRIMARY_CHARACTER: CHAR_A",
        "EXTERNAL_NARRATOR: NONE",
    ]
    header += char_blocks
    header += ["", "SCENE: SC01", f"TITLE: {title}"]
    return "\n".join(header) + "\n" + body


# --- Three unrelated fixtures -----------------------------------------
PRIMATE_FIXTURE = _script(
    [
        "CHARACTER: CHAR_A",
        "NAME: A",
        "SPECIES: primate",
        "ROLE: Chien binh canh cong",
        "APPEARANCE: long nau, mac giap da",
        "CHARACTER: CHAR_B",
        "NAME: B",
        "ROLE: Nguoi dan duong",
    ],
    "SHOT: SH01\nCAMERA: wide\n"
    "NARRATION:\nSPEAKER: CHAR_B\nLINE_ID: T_01\nTEXT: “Toi da toi.”\n",
    title="Cong den",
)

FELINE_FIXTURE = _script(
    [
        "CHARACTER: CHAR_A",
        "NAME: A",
        "SPECIES: feline",
        "ROLE: Nguoi dua hang",
        "APPEARANCE: tai nhon, duoi dai",
        "CHARACTER: CHAR_B",
        "NAME: B",
        "ROLE: Nguoi ban hang",
    ],
    "SHOT: SH01\nCAMERA: medium\n"
    "NARRATION:\nSPEAKER: CHAR_B\nLINE_ID: T_01\nTEXT: “Hang toi roi.”\n",
    title="Cho dem",
)

BOVINE_FIXTURE = _script(
    [
        "CHARACTER: CHAR_A",
        "NAME: A",
        "SPECIES: bovine",
        "HORNS: antlers",
        "FACE_MARKINGS: war_paint",
        "ROLE: Tho ren",
        "CHARACTER: CHAR_B",
        "NAME: B",
        "EARS: long",
        "ROLE: Nguoi hoc viec",
    ],
    "SHOT: SH01\nCAMERA: medium\n"
    "NARRATION:\nSPEAKER: CHAR_B\nLINE_ID: T_01\nTEXT: “Lua da chay.”\n",
    title="Lo ren",
)

FIXTURES = {
    "primate_temple": PRIMATE_FIXTURE,
    "feline_night_market": FELINE_FIXTURE,
    "bovine_forge": BOVINE_FIXTURE,
}


class TestVocabulariesStayInSync(unittest.TestCase):
    def test_derivation_mirrors_the_drawing_vocabulary(self):
        self.assertEqual(EAR_SHAPES, rig.EAR_SHAPES)
        self.assertEqual(TAIL_SHAPES, rig.TAIL_SHAPES)
        self.assertEqual(HORN_SHAPES, rig.HORN_SHAPES)
        self.assertEqual(FACE_MARKING_STYLES, rig.FACE_MARKING_STYLES)


class TestVisualProfileDerivation(unittest.TestCase):
    def test_human_default_has_no_features(self):
        profile, notes = derive_visual_profile()
        self.assertEqual(notes, [])
        self.assertEqual(profile["species"], "human")
        for key in ("ears", "tail", "horns", "face_markings"):
            self.assertEqual(profile[key], "none")

    def test_species_defaults_are_generic_not_name_based(self):
        for field_value, expected in (
                ("primate", {"ears": "round", "tail": "monkey"}),
                ("feline", {"ears": "pointed", "tail": "long"}),
                ("canine", {"ears": "pointed", "tail": "bushy"}),
                ("bovine", {"ears": "round", "horns": "curved"}),
                ("bird", {"tail": "tuft"}),
                ("mythic", {"horns": "small"})):
            profile, _notes = derive_visual_profile(
                fields={"SPECIES": field_value})
            self.assertEqual(profile["species"], field_value)
            for key, value in expected.items():
                self.assertEqual(profile[key], value, (field_value, key))

    def test_a_name_alone_never_creates_a_species(self):
        # A well-known name must not smuggle features in: the profile is
        # derived from declared fields and descriptive text only.
        for name in ("Ton Ngo Khong", "Zeus", "Arthur Sterling", "Minh"):
            profile, _notes = derive_visual_profile(scan_text=name)
            self.assertEqual(profile["species"], "human", name)
            self.assertEqual(profile["tail"], "none", name)

    def test_text_scan_is_the_fallback(self):
        profile, _notes = derive_visual_profile(
            scan_text="con khỉ đuôi dài trong rừng")
        self.assertEqual(profile["species"], "primate")
        self.assertEqual(profile["tail"], "long")

    def test_declared_feature_overrides_the_species_default(self):
        profile, _notes = derive_visual_profile(
            fields={"SPECIES": "feline", "EARS": "long"})
        self.assertEqual(profile["ears"], "long")
        self.assertEqual(profile["tail"], "long")

    def test_unknown_declaration_falls_back_with_a_note(self):
        profile, notes = derive_visual_profile(
            fields={"SPECIES": "kryptonian", "TAIL": "dragon"})
        self.assertEqual(profile["species"], "human")
        self.assertEqual(profile["tail"], "none")
        self.assertEqual(len(notes), 2)
        self.assertTrue(any("species" in n for n in notes))
        self.assertTrue(any("tail" in n for n in notes))

    def test_derive_render_traits_carries_a_complete_profile(self):
        notes = []
        traits = derive_render_traits(
            "A", "Chien binh", "long nau", "", [], "",
            fields={"SPECIES": "primate"}, notes=notes)
        profile = traits["visual_profile"]
        self.assertEqual(set(profile), set(VISUAL_PROFILE_KEYS))
        self.assertEqual(profile["ears"], "round")
        self.assertEqual(notes, [])


class TestAmbiguousWordsNeverDecideAPhysique(unittest.TestCase):
    """A generic word must never turn a person into an animal."""

    def test_newspaper_seller_is_not_a_leopard(self):
        profile, _notes = derive_visual_profile(
            scan_text="người bán báo, áo khoác nâu")
        self.assertEqual(profile["species"], "human")
        self.assertEqual(profile["tail"], "none")

    def test_crawling_is_not_cattle(self):
        profile, _notes = derive_visual_profile(
            scan_text="cô bé bò lê trên sàn")
        self.assertEqual(profile["species"], "human")

    def test_unambiguous_compounds_still_work(self):
        self.assertEqual(
            derive_visual_profile(scan_text="con báo đốm")[0]["species"],
            "feline")
        self.assertEqual(
            derive_visual_profile(scan_text="con bò tót")[0]["species"],
            "bovine")


class TestRealFixtureStaysHuman(unittest.TestCase):
    """The real Munich fixture: everyone in an installed cast is human."""

    def test_fixture_characters_get_no_invented_species(self):
        import os
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        path = os.path.join(root, "fixtures", "episode01_hitler_1914_munich",
                            "script.txt")
        with open(path, encoding="utf-8") as handle:
            doc = parse_studio_script_v1(handle.read())
        package = adapt_document(doc)
        for char in package["characters"]:
            profile = char["visual_profile"]
            self.assertEqual(profile["species"], "human", char["name"])
            self.assertEqual(profile["ears"], "none", char["name"])
            self.assertEqual(profile["tail"], "none", char["name"])


class TestProfileValidationAndMerge(unittest.TestCase):
    def test_validator_drops_undrawable_values_with_a_note(self):
        blocks, dropped = validate_trait_blocks({"characters": [{
            "name": "A", "identity_id": "A",
            "render_traits": {"template": "male",
                              "visual_profile": {"tail": "dragon",
                                                 "horns": "antlers"}}}]})
        traits = blocks["characters"][0]["render_traits"]
        self.assertEqual(traits["visual_profile"], {"horns": "antlers"})
        self.assertTrue(any("visual_profile.tail" in n for n in dropped))

    def test_merge_is_field_wise_and_never_erases_derived_fields(self):
        base = {"visual_profile": {"species": "bovine", "ears": "round",
                                   "tail": "none", "horns": "curved",
                                   "face_markings": "none"}}
        merged = merge_render_traits(base, {"visual_profile": {
            "horns": "antlers"}})
        self.assertEqual(merged["visual_profile"]["species"], "bovine")
        self.assertEqual(merged["visual_profile"]["ears"], "round")
        self.assertEqual(merged["visual_profile"]["horns"], "antlers")
        # Inputs are not mutated.
        self.assertEqual(base["visual_profile"]["horns"], "curved")


class TestRendererHonoursProfile(unittest.TestCase):
    def test_map_character_reads_contract_and_flat_fields(self):
        nested = map_character({
            "name": "A", "template": "male",
            "visual_profile": {"ears": "pointed", "tail": "long",
                               "horns": "none",
                               "face_markings": "war_paint"},
        }, 0)
        self.assertEqual(
            (nested.ears, nested.tail, nested.horns,
             nested.face_markings),
            ("pointed", "long", "none", "war_paint"))
        flat = map_character({"name": "B", "template": "female",
                              "horns": "curved"}, 1)
        self.assertEqual(flat.horns, "curved")

    def test_default_characters_keep_no_species_features(self):
        plain = map_character({"name": "C", "template": "male"}, 2)
        self.assertEqual((plain.ears, plain.tail, plain.horns,
                          plain.face_markings),
                         ("none", "none", "none", "none"))

    def test_unknown_feature_in_a_raw_dict_is_not_passed_to_the_rig(self):
        char = map_character({"name": "D", "template": "male",
                              "visual_profile": {"tail": "dragon"}}, 3)
        self.assertEqual(char.tail, "none")

    def test_every_shape_draws_in_every_view(self):
        from PIL import Image, ImageDraw
        for view in ("front", "three_quarter", "profile", "back"):
            for feature, value in (("ears", "wing"), ("tail", "bushy"),
                                   ("horns", "crown"),
                                   ("face_markings", "muzzle")):
                char = make_character("male", name="T", height=240,
                                      **{feature: value})
                standing(char, 120, 300, facing=1)
                img = Image.new("RGB", (240, 320), (255, 255, 255))
                draw_character_v4(ImageDraw.Draw(img, "RGBA"), char,
                                  view=view)


class TestCameraKeyAlias(unittest.TestCase):
    def test_shot_camera_motion_is_the_movement_field(self):
        doc = parse_studio_script_v1(_script(
            ["CHARACTER: CHAR_A", "NAME: A"],
            "SHOT: SH01\nCAMERA: medium\nCAMERA_MOTION: DOLLY_IN\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\n"
            "TEXT: “Chao.”\n"))
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.unsupported_fields, [])
        shot = doc.scenes[0].shots[0]
        self.assertEqual(shot.camera_movement_text, "DOLLY_IN")
        self.assertEqual(shot.camera_movement, "DOLLY_IN")

    def test_scene_camera_motion_is_the_movement_field(self):
        doc = parse_studio_script_v1(_script(
            ["CHARACTER: CHAR_A", "NAME: A"],
            "SHOT: SH01\nCAMERA: wide\n"
            "NARRATION:\nSPEAKER: CHAR_A\nLINE_ID: T_01\n"
            "TEXT: “Chao.”\n").replace(
                "SCENE: SC01", "SCENE: SC01\nCAMERA_MOVE: PAN_LEFT"))
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.unsupported_fields, [])
        self.assertEqual(doc.scenes[0].camera_movement, "PAN_LEFT")


class TestNonActionRouting(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(classify_non_action_text("Mưa bắt đầu rơi."),
                         "environment")
        self.assertEqual(classify_non_action_text("Âm thanh vang lên."),
                         "audio")
        self.assertEqual(classify_non_action_text("Máy quay lia sang trái."),
                         "camera")
        self.assertIsNone(classify_non_action_text("Anh ta ngồi xuống."))

    def test_directives_report_their_own_discipline(self):
        directives, unmapped = derive_action_directives([
            {"text": "Mưa bắt đầu rơi.", "scene_number": 1},
            {"text": "Tiếng động âm thanh vang lên.", "scene_number": 1},
            {"text": "Máy quay lia sang trái.", "scene_number": 1},
            {"text": "Anh ta xoay người kỳ lạ.", "scene_number": 1},
        ])
        self.assertEqual(directives, [])
        kinds = {u["kind"] for u in unmapped}
        self.assertEqual(kinds, {"environment", "audio", "camera", "action"})
        for entry in unmapped:
            self.assertIn("reason", entry)
            if entry["kind"] != "action":
                self.assertNotIn("no PRIMITIVES mapping", entry["reason"])


class TestMultiFixtureRegression(unittest.TestCase):
    """Parse -> adapt -> renderer across three unrelated scripts."""

    def test_every_fixture_keeps_a_closed_vocabulary_profile(self):
        for name, text in FIXTURES.items():
            doc = parse_studio_script_v1(text)
            self.assertTrue(doc.is_valid, (name, _codes(doc)))
            self.assertEqual(doc.unsupported_fields, [], name)
            package = adapt_document(doc)
            self.assertTrue(package["characters"], name)
            for char in package["characters"]:
                profile = char.get("visual_profile") or {}
                self.assertEqual(set(profile), set(VISUAL_PROFILE_KEYS),
                                 (name, char["name"]))
                for key, allowed in PROFILE_VOCAB.items():
                    self.assertIn(profile[key], allowed,
                                  (name, char["name"], key))
                # The renderer accepts the entry without raising.
                built = map_character(char, 0)
                self.assertIn(built.ears, EAR_SHAPES)

    def test_declared_species_reaches_the_renderer(self):
        expected = {
            "primate_temple": ("primate", "round", "monkey"),
            "feline_night_market": ("feline", "pointed", "long"),
            "bovine_forge": ("bovine", "round", "curved"),
        }
        for name, text in FIXTURES.items():
            package = adapt_document(parse_studio_script_v1(text))
            first = package["characters"][0]
            profile = first["visual_profile"]
            species, ears, tail_or_horns = expected[name]
            self.assertEqual(profile["species"], species, name)
            self.assertEqual(profile["ears"], ears, name)
            if species == "bovine":
                self.assertEqual(profile["horns"], "antlers", name)
            else:
                self.assertEqual(profile["tail"], tail_or_horns, name)

    def test_declared_face_markings_and_ears_survive(self):
        package = adapt_document(parse_studio_script_v1(BOVINE_FIXTURE))
        first, second = package["characters"][:2]
        self.assertEqual(first["visual_profile"]["face_markings"],
                         "war_paint")
        self.assertEqual(second["visual_profile"]["ears"], "long")
        self.assertEqual(map_character(first, 0).face_markings, "war_paint")


if __name__ == "__main__":
    unittest.main()
