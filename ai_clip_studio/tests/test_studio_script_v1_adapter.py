"""Tests for the STUDIO SCRIPT V1 -> scene-package adapter.

Covers: the supplied Episode 01 script end-to-end (verbatim text,
LINE_IDs, traits, constraints preserved), synthetic grammar shapes
the fixture does not exercise (LOCATION/PROP/SHOT blocks, explicit
LINE_IDs, NONE cues, GLOBAL_AUDIO/QA/OUTPUT/END_CARD), invalid-doc
refusal, format routing, determinism, and the guard sets that must
stay in sync with product_flow / product_renderer.

The synthetic snippets below are UNIT fixtures exercising grammar
shapes only -- they are never rendered. Rendered tests use only the
supplied Episode 01 script.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ai_clip_studio.product_flow import SUPPORTED_CUES as PRODUCT_FLOW_CUES
from ai_clip_studio.product_renderer import SHOT_SCALE
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import (
    ADAPTER_LABEL,
    HONOURED_SHOT_TYPES,
    SUPPORTED_CUES,
    V1AdapterError,
    _location_keyword,
    _mood,
    _time_of_day,
    _voice_hint,
    adapt_document,
    resolve_v1_plan,
)

FIXTURE = "/home/hatch/workspace/video-upstream/fixtures/episode01_hitler_1914_munich/script.txt"
# SHA-256 of the exact fixture bytes (verified by the Phase A/B spec
# work); the adapter must carry it through unchanged.
FIXTURE_HASH = "a4d542336adfc289d6d7d7adb3cb25baa63be5b06953c915d79a44736c7de8c9"

RICH_SCRIPT = """# STUDIO SCRIPT V1
PROJECT: TEST_SHAPES
LANGUAGE: vi-VN

CHARACTER: Cô Lan
ROLE: Cô gái trẻ bán hoa
APPEARANCE: Tóc dài, áo dài vàng
TRAITS: Nhanh nhẹn; vui vẻ
COSTUME: Áo dài vàng
VOICE: vieneu-Test
VOICE_STYLE: Giọng nữ trong trẻo

CHARACTER: Người Kể Chuyện
ROLE: Người dẫn chuyện
VOICE: AUTO

LOCATION: CHO_DEM
NAME: Chợ đêm ven sông
GEOGRAPHY: Bờ sông phía nam
ARCHITECTURE: Sạp gỗ mái lá
FEATURES: Đèn lồng đỏ; sạp hoa tươi
FOREGROUND: Sạp hoa, giỏ tre
MIDGROUND: Dòng người mua bán
BACKGROUND: Mặt sông, cầu sắt
LIGHTING: Đèn lồng ấm
WEATHER: Không mưa
PALETTE: Đỏ; vàng
FORBIDDEN: Nhà cao tầng

PROP: Giỏ Hoa
DESCRIPTION: Giỏ tre đầy hoa cúc vàng
OWNER: Cô Lan
SCENES: 1
INTERACTION: cầm; đưa

GLOBAL_AUDIO:
NARRATION_GAIN_DB: -1.5
SFX_GAIN_DB: -8

GLOBAL_NEGATIVE_CONSTRAINTS:
- Không dùng tiếng Anh.

QA:
MIN_SCORE: 8.5

OUTPUT:
RESOLUTION: 1920x1080
FPS: 24

END_CARD:
TEXT: Hẹn gặp lại
DURATION: 3.0
STYLE: Chữ trắng

SCENE 1: Chợ đêm
LOCATION: CHO_DEM
TIME_OF_DAY: Đêm
MOOD: Ấm áp, lạnh lẽo
DURATION: AUTO
VISUAL: Chợ đêm rực đèn lồng.
ACTION: Cô Lan đi nhanh qua các sạp rồi dừng lại nhìn quanh.
CAMERA: Góc rộng
CAMERA_MOVEMENT: PAN_RIGHT

SHOT SH01:
TYPE: ESTABLISHING
SUBJECT: Cô Lan
ACTION: Cô Lan bước vào chợ.

NARRATION [L001]: Đêm xuống, chợ hoa rực sáng.
DIALOGUE: Cô Lan: Hoa tươi đây, mời bà con ghé xem!
SFX: Tiếng rao hàng | TRIGGER: L001 | PRIORITY: REQUIRED
AMBIENCE: Chợ đêm ồn ào | MODE: LOOP
BGM: Nhạc dân ca | INTENSITY: LOW
TRANSITION: DISSOLVE
END_SCENE

SCENE 2: Lời chào
LOCATION: Chợ đêm ven sông
TIME_OF_DAY: Sáng
MOOD: Bình yên
VISUAL: Sáng sớm ở chợ.

SHOT SH02:
TYPE: OVER_THE_SHOULDER
SUBJECT: Cô Lan

NARRATION: Một ngày mới bắt đầu.
SFX: NONE
AMBIENCE: NONE
BGM: NONE
MEME: NONE
END_SCENE
END_SCRIPT
"""


def _load_fixture_text() -> str:
    return Path(FIXTURE).read_text(encoding="utf-8")


class TestFixtureEndToEnd(unittest.TestCase):
    def setUp(self):
        self.text = _load_fixture_text()
        self.doc = parse_studio_script_v1(self.text)
        self.assertTrue(self.doc.is_valid)
        self.package, self.label, self.detail = resolve_v1_plan(self.text)

    def test_label_and_detail(self):
        self.assertEqual(self.label, "v1")
        self.assertEqual(self.label, ADAPTER_LABEL)
        self.assertIn("8 scenes", self.detail)
        self.assertIn("3 characters", self.detail)
        self.assertIn("10 spoken", self.detail)
        self.assertIn("no Gemini enrichment", self.detail)

    def test_snapshot_hash_preserved(self):
        self.assertEqual(self.package["v1_snapshot_hash"], FIXTURE_HASH)
        self.assertEqual(self.package["v1_snapshot_hash"],
                         self.doc.snapshot_hash)

    def test_visible_cast_excludes_narrator(self):
        names = [c["name"] for c in self.package["characters"]]
        self.assertEqual(
            names, ["Adolf Hitler", "Bà Chủ Nhà", "Người Bán Báo"])
        self.assertEqual(len(self.package["v1_narrator"]), 1)
        self.assertEqual(self.package["v1_narrator"][0]["name"],
                         "Người Dẫn Chuyện")
        self.assertEqual(self.package["v1_narrator"][0]["voice"],
                         "vieneu-Hải Đăng")

    def test_character_traits_preserved(self):
        by_name = {c["name"]: c for c in self.package["characters"]}
        hitler = by_name["Adolf Hitler"]
        self.assertEqual(hitler["voice"], "vieneu-Thiện Minh")
        self.assertEqual(hitler["head_ratio"], 0.34)
        self.assertIn("Chàng trai thất bại", hitler["description"])
        self.assertIn("áo khoác nâu", hitler["description"])
        self.assertEqual(by_name["Bà Chủ Nhà"]["voice"], "vieneu-Trúc Ly")
        self.assertEqual(by_name["Người Bán Báo"]["voice"],
                         "vieneu-Phạm Tuyên")

    def test_voice_hints_derived(self):
        by_name = {c["name"]: c for c in self.package["characters"]}
        self.assertEqual(by_name["Adolf Hitler"]["voice_hint"], "giọng nam")
        self.assertEqual(by_name["Bà Chủ Nhà"]["voice_hint"], "giọng nữ")
        # No gender evidence in the script's own text for this role.
        self.assertEqual(by_name["Người Bán Báo"]["voice_hint"], "")

    def test_jacket_colors_from_generic_map(self):
        by_name = {c["name"]: c for c in self.package["characters"]}
        self.assertEqual(by_name["Adolf Hitler"]["jacket_color"], "#7a4a2b")
        self.assertEqual(by_name["Bà Chủ Nhà"]["jacket_color"], "#6b7280")
        self.assertEqual(by_name["Người Bán Báo"]["jacket_color"], "#3a4a5f")

    def test_scenes_and_lines_verbatim(self):
        self.assertEqual(len(self.package["scenes"]), 8)
        self.assertEqual([s["number"] for s in self.package["scenes"]],
                         [1, 2, 3, 4, 5, 6, 7, 8])
        package_lines = [ln for s in self.package["scenes"]
                         for ln in s["lines"]]
        self.assertEqual(len(package_lines), 10)
        parsed_lines = self.doc.spoken_lines
        self.assertEqual([ln["text"] for ln in package_lines],
                         [ln.text for ln in parsed_lines])
        self.assertEqual([ln["kind"] for ln in package_lines],
                         [ln.kind for ln in parsed_lines])
        speakers = [ln["speaker"] for ln in package_lines]
        self.assertEqual(speakers.count("narrator"), 3)
        self.assertNotIn("Narrator", speakers)
        self.assertEqual(self.package["hook"], package_lines[0]["text"])
        self.assertEqual(self.package["twist"], package_lines[-1]["text"])

    def test_action_cues_supported_and_lead_sized(self):
        for scene in self.package["scenes"]:
            for cue in scene["action_cues"]:
                self.assertIn(cue, SUPPORTED_CUES)
            self.assertGreaterEqual(scene["action_lead_sec"], 0.0)
        first = self.package["scenes"][0]
        self.assertEqual(first["action_cues"], ["look"])
        self.assertEqual(first["action_lead_sec"], 0.8)

    def test_location_dicts_generic(self):
        for scene in self.package["scenes"]:
            loc = scene["location"]
            self.assertEqual(loc["location_keyword"], "street")
            self.assertEqual(loc["time_of_day"], "day")
        self.assertEqual(self.package["scenes"][0]["location"]["mood"],
                         "warm")
        # Scene 8 mood carries "lạnh lẽo" in the script's own text.
        self.assertEqual(self.package["scenes"][7]["location"]["mood"],
                         "cold")
        self.assertEqual(len(self.package["locations"]), 8)

    def test_shots_present_for_preflight(self):
        # 8 action shots + 10 line shots (shape the server preflight
        # requires non-empty).
        self.assertEqual(len(self.package["shots"]), 18)
        self.assertTrue(all(s["shot_id"] for s in self.package["shots"]))

    def test_audio_cues_preserved_without_invented_timestamps(self):
        self.assertEqual(self.package["audio_events"], [])
        cues = self.package["v1_audio_cues"]
        self.assertEqual(len(cues), 27)
        counts: dict[str, int] = {}
        for cue in cues:
            counts[cue["cue_type"]] = counts.get(cue["cue_type"], 0) + 1
        self.assertEqual(
            counts, {"SFX": 8, "AMBIENCE": 8, "BGM": 8, "MEME": 3})
        self.assertEqual(self.package["gemini_shots"], [])
        self.assertEqual(self.package["v1_shot_notes"], [])
        self.assertEqual(self.package["v1_dropped_cues"], [])

    def test_v1_data_preserved(self):
        self.assertEqual(self.package["v1_format"], "studio_script_v1")
        self.assertEqual(self.package["v1_meta"]["project"],
                         "HITLER_EP01_MUNICH_1914")
        self.assertEqual(self.package["v1_meta"]["language"], "vi-VN")
        self.assertEqual(self.package["v1_locations"], [])
        self.assertEqual(self.package["v1_props"], [])
        # The fixture declares no GLOBAL_NEGATIVE_CONSTRAINTS block.
        self.assertEqual(self.package["v1_constraints"], [])
        self.assertEqual(self.package["v1_qa"]["min_score"], 8.0)
        self.assertEqual(self.package["v1_output"]["resolution"],
                         "1920x1080")

    def test_package_is_json_serializable(self):
        json.dumps(self.package, ensure_ascii=False)

    def test_deterministic(self):
        again, _, _ = resolve_v1_plan(self.text)
        self.assertEqual(
            json.dumps(self.package, sort_keys=True, ensure_ascii=False),
            json.dumps(again, sort_keys=True, ensure_ascii=False))


class TestGrammarShapes(unittest.TestCase):
    def setUp(self):
        self.package, _, _ = resolve_v1_plan(RICH_SCRIPT)

    def test_location_block_and_ref(self):
        self.assertEqual(len(self.package["v1_locations"]), 1)
        loc = self.package["v1_locations"][0]
        self.assertEqual(loc["id"], "CHO_DEM")
        self.assertEqual(loc["name"], "Chợ đêm ven sông")
        self.assertIn("Đèn lồng đỏ", loc["features"])
        scene1 = self.package["scenes"][0]
        self.assertEqual(scene1["setting"], "Chợ đêm ven sông")
        self.assertEqual(scene1["v1_scene"]["location_ref"], "CHO_DEM")
        self.assertEqual(scene1["location"]["time_of_day"], "night")
        self.assertEqual(scene1["location"]["mood"], "cold")
        scene2 = self.package["scenes"][1]
        self.assertEqual(scene2["setting"], "Chợ đêm ven sông")
        self.assertIsNone(scene2["v1_scene"]["location_ref"])
        self.assertEqual(scene2["location"]["time_of_day"], "day")
        self.assertEqual(scene2["location"]["mood"], "warm")

    def test_prop_preserved(self):
        self.assertEqual(len(self.package["v1_props"]), 1)
        prop = self.package["v1_props"][0]
        self.assertEqual(prop["name"], "Giỏ Hoa")
        self.assertEqual(prop["owner"], "Cô Lan")
        self.assertEqual(prop["scenes"], [1])

    def test_shot_blocks_map_to_gemini_shots(self):
        self.assertEqual(self.package["gemini_shots"], [
            {"scene": 1, "line_index": 1, "shot_type": "establishing"},
            {"scene": 1, "line_index": 2, "shot_type": "establishing"},
        ])
        # over_the_shoulder is valid V1 but not honoured by plan_shots:
        # noted, kept in the passthrough, never silently dropped.
        self.assertEqual(len(self.package["v1_shot_notes"]), 1)
        self.assertIn("over_the_shoulder", self.package["v1_shot_notes"][0])
        shot_ids = [sh["id"]
                    for sh in self.package["scenes"][1]["v1_scene"]["shots"]]
        self.assertEqual(shot_ids, ["SH02"])

    def test_explicit_line_ids_and_cue_triggers(self):
        scene1 = self.package["scenes"][0]["v1_scene"]
        self.assertEqual([ln["line_id"] for ln in scene1["spoken_lines"]],
                         ["L001", "L002"])
        sfx = [c for c in scene1["audio_cues"]
               if c["cue_type"] == "SFX"][0]
        self.assertEqual(sfx["trigger"], "L001")
        self.assertEqual(sfx["priority"], "REQUIRED")

    def test_none_cues_recorded(self):
        scene2 = self.package["scenes"][1]["v1_scene"]
        self.assertTrue(scene2["sfx_none"])
        self.assertTrue(scene2["ambience_none"])
        self.assertTrue(scene2["bgm_none"])
        self.assertTrue(scene2["meme_none"])

    def test_global_audio_qa_output_end_card(self):
        self.assertEqual(
            self.package["v1_global_audio"]["narration_gain_db"], -1.5)
        self.assertEqual(self.package["v1_global_audio"]["sfx_gain_db"], -8.0)
        self.assertEqual(self.package["v1_constraints"],
                         ["Không dùng tiếng Anh."])
        self.assertEqual(self.package["v1_qa"]["min_score"], 8.5)
        self.assertEqual(self.package["v1_output"]["resolution"],
                         "1920x1080")
        self.assertEqual(self.package["v1_end_card"]["text"],
                         "Hẹn gặp lại")

    def test_action_cues_from_action_and_shot_text(self):
        scene1 = self.package["scenes"][0]
        self.assertEqual(scene1["action_cues"],
                         ["walk_fast", "stop", "look"])
        self.assertEqual(scene1["action_lead_sec"], 3.0)
        scene2 = self.package["scenes"][1]
        self.assertEqual(scene2["action_cues"], [])
        self.assertEqual(scene2["action_lead_sec"], 0.0)

    def test_narrator_alias_character_excluded(self):
        names = [c["name"] for c in self.package["characters"]]
        self.assertEqual(names, ["Cô Lan"])
        self.assertEqual(len(self.package["v1_narrator"]), 1)
        self.assertEqual(self.package["v1_narrator"][0]["name"],
                         "Người Kể Chuyện")
        char = self.package["characters"][0]
        self.assertEqual(char["voice_hint"], "giọng nữ")
        self.assertEqual(char["jacket_color"], "#d9a441")
        self.assertEqual(char["traits"], ["Nhanh nhẹn", "vui vẻ"])
        self.assertEqual(char["costume_text"], "Áo dài vàng")


class TestRefusalAndRouting(unittest.TestCase):
    def test_invalid_document_refused_with_line_and_code(self):
        text = """# STUDIO SCRIPT V1
PROJECT: T
CHARACTER: An
ROLE: Người kể
HEAD_RATIO: 0.42
SCENE 1: Mở
NARRATION: Mở đầu.
END_SCENE
END_SCRIPT
"""
        doc = parse_studio_script_v1(text)
        self.assertFalse(doc.is_valid)
        with self.assertRaises(V1AdapterError) as ctx:
            adapt_document(doc)
        self.assertIn("V1E009", str(ctx.exception))
        self.assertTrue(ctx.exception.errors)
        with self.assertRaises(V1AdapterError):
            resolve_v1_plan(text)

    def test_no_spoken_lines_refused(self):
        text = """# STUDIO SCRIPT V1
PROJECT: T
CHARACTER: An
ROLE: Người kể
SCENE 1: Mở
VISUAL: Không lời thoại.
END_SCENE
END_SCRIPT
"""
        # The parser itself refuses a document with no spoken lines
        # (V1E023); the adapter surfaces that refusal. Its own
        # no-spoken-lines check is defense in depth for Documents
        # built programmatically.
        with self.assertRaises(V1AdapterError) as ctx:
            resolve_v1_plan(text)
        self.assertIn("V1E023", str(ctx.exception))

    def test_freeform_text_rejected_by_v1_route(self):
        with self.assertRaises(V1AdapterError):
            resolve_v1_plan("CẢNH 1: Mở đầu\nMinh: \"Xin chào.\"\n")
        with self.assertRaises(V1AdapterError):
            resolve_v1_plan("")

    def test_missing_speaker_gets_character_entry(self):
        # Defensive path: unreachable via the parser (V1E015 rejects
        # undeclared speakers), so exercise it through a stub
        # document exposing to_dict() only.
        class StubDoc:
            def to_dict(self):
                return {
                    "snapshot_hash": "0" * 64,
                    "meta": {}, "characters": [], "locations": [],
                    "props": [], "constraints": [], "qa": {},
                    "output": {}, "global_audio": {}, "end_card": None,
                    "unsupported_fields": [], "validation_errors": [],
                    "scenes": [{
                        "number": 1, "title": "Mở",
                        "location_ref": None, "location_text": "Phố",
                        "time_of_day": "Sáng", "mood": "Vui",
                        "actions": [], "shots": [],
                        "spoken_lines": [{
                            "line_id": "L001", "speaker": "Người Lạ",
                            "text": "Xin chào.", "kind": "dialogue"}],
                        "audio_cues": [], "vfx_cues": [],
                    }],
                }

        package = adapt_document(StubDoc())
        self.assertEqual(
            [c["name"] for c in package["characters"]], ["Người Lạ"])
        self.assertEqual(package["scenes"][0]["lines"][0]["speaker"],
                         "Người Lạ")


class TestDerivationHelpers(unittest.TestCase):
    def test_voice_hint(self):
        self.assertEqual(_voice_hint("Bà Tư", "Người lớn tuổi",
                                     "Tóc bạc", ""), "giọng nữ")
        self.assertEqual(_voice_hint("An", "Chàng trai trẻ", "", ""),
                         "giọng nam")
        self.assertEqual(_voice_hint("An", "", "", "giọng nữ trầm"),
                         "giọng nữ")
        self.assertEqual(_voice_hint("Bé Bo", "Cậu bé bán báo", "", ""),
                         "giọng nam")
        self.assertEqual(_voice_hint("An", "Người bán hàng",
                                     "Áo xanh", ""), "")
        # A name that merely contains "Nam" must not misfire.
        self.assertEqual(_voice_hint("Thanh Nam", "Người thợ",
                                     "Áo xám", ""), "")

    def test_location_keyword(self):
        self.assertEqual(_location_keyword("Vạn Lý Trường Thành hùng vĩ"),
                         "great_wall")
        self.assertEqual(_location_keyword("Tháp Eiffel, Paris"),
                         "eiffel_tower")
        self.assertEqual(_location_keyword("Phố mưa Sài Gòn"),
                         "rainy_street")
        self.assertEqual(_location_keyword("Căn gác nhỏ"), "street")

    def test_time_of_day_and_mood(self):
        self.assertEqual(_time_of_day("Đêm khuya"), "night")
        self.assertEqual(_time_of_day("Buổi tối"), "night")
        self.assertEqual(_time_of_day("Sáng sớm"), "day")
        self.assertEqual(_time_of_day("Hoàng hôn"), "day")
        self.assertEqual(_mood("Lạnh lẽo, u ám"), "cold")
        self.assertEqual(_mood("Ấm áp"), "warm")
        self.assertEqual(_mood("Vui vẻ"), "warm")


class TestGuardSetsAndGenerality(unittest.TestCase):
    def test_supported_cues_match_product_flow(self):
        self.assertEqual(set(SUPPORTED_CUES), set(PRODUCT_FLOW_CUES))

    def test_honoured_shot_types_match_renderer(self):
        self.assertEqual(set(HONOURED_SHOT_TYPES), set(SHOT_SCALE))

    def test_no_per_story_strings_in_adapter(self):
        source = Path(__file__).resolve().parent.parent.joinpath(
            "studio_script_v1_adapter.py").read_text(encoding="utf-8")
        lowered = source.lower()
        for banned in ("hitler", "munich", "odeonsplatz", "frauenkirche",
                       "bà chủ nhà", "người bán báo", "chiếc ví",
                       "chiếc ô"):
            self.assertNotIn(banned, lowered)


if __name__ == "__main__":
    unittest.main()
