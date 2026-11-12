"""Tests for the STUDIO SCRIPT V1 parser (ai_clip_studio/studio_script_v1.py).

Run from /home/hatch/workspace/video-16x9-v2:
    python3 -m unittest ai_clip_studio.tests.test_studio_script_v1 -v

The upstream fixture is used for schema/parser validation ONLY (no render).
Synthetic scripts use neutral invented names; nothing here hardcodes a story.
"""
import json
import re
import unittest

try:
    import jsonschema
except ImportError:  # jsonschema is optional; the structural check still runs
    jsonschema = None

from ai_clip_studio.studio_script_v1 import (
    HEAD_RATIO_DEFAULT,
    HEAD_RATIO_MAX,
    HEAD_RATIO_MIN,
    SHOT_TYPES,
    StudioScriptV1Error,
    StudioScriptV1Parser,
    detect_format,
    parse_studio_script_v1,
)

FIXTURE = "/home/hatch/workspace/video-upstream/fixtures/episode01_hitler_1914_munich/script.txt"
EXAMPLE = "/home/hatch/workspace/video-16x9-v2/examples/hitler_ep01.studio.md"
TEMPLATE = "/home/hatch/workspace/video-16x9-v2/docs/STUDIO_SCRIPT_V1_TEMPLATE.md"
FREEFORM_SCRIPT = "/home/hatch/workspace/acceptance_loop/test_chiec_vi_trong_mua/script.txt"
SCHEMA_PATH = "/home/hatch/workspace/video-16x9-v2/docs/studio_script_v1.schema.json"


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _codes(doc):
    return [issue.code for issue in doc.validation_errors]


def _error_at(doc, code):
    return [issue for issue in doc.validation_errors if issue.code == code]


SYNTHETIC_FULL = """# STUDIO SCRIPT V1 — UNIVERSAL VIDEO FORMAT

PROJECT: Dự án thử nghiệm
LANGUAGE: vi-VN
GENRE: Truyện ngắn
VISUAL_STYLE: Premium Stickman Cinematic B
ASPECT_RATIO: 16:9
TARGET_DURATION: AUTO
TONE: Ấm áp
MEME_POLICY: NONE
MEME_MAX_PER_MINUTE: 0

GLOBAL_AUDIO:
NARRATION_GAIN_DB: -1.5
DIALOGUE_GAIN_DB: 0
AMBIENCE_GAIN_DB: -20
FOLEY_GAIN_DB: -10
SFX_GAIN_DB: -8
BGM_GAIN_DB: -16
BGM_DUCKING_DB: -8
MASTER_LIMIT_DB: -1.5

GLOBAL_NEGATIVE_CONSTRAINTS:
- Không dùng chữ tiếng Anh trên màn hình
NO: Không thay đổi lời thoại

CHARACTER: Khoa
ROLE: Người kể chuyện trẻ
APPEARANCE: Đầu tròn, áo khoác xanh
TRAITS: Tốt bụng; hay giúp đỡ người lạ; đi nhanh
COSTUME: Áo khoác xanh đậm, quần đen
COSTUME_CHANGE: SCENE 2: Áo mưa vàng
VOICE: AUTO
VOICE_STYLE: Trẻ, ấm áp
HEAD_RATIO: 0.34
IDENTITY_ID: khoa-01

CHARACTER: Bà Tư
ROLE: Người lớn tuổi
APPEARANCE: Tóc bạc, áo dài tím, gậy tre
TRAITS: Chậm chạp; hiền hậu; mắt kém
COSTUME: Áo dài tím
VOICE: AUTO
VOICE_STYLE: Chậm, run nhẹ

LOCATION: BEN_SONG
NAME: Bến sông quê
PERIOD: Hiện đại
GEOGRAPHY: Miền Tây sông nước
ARCHITECTURE: Nhà sàn gỗ, cầu khỉ
FEATURES: Cầu khỉ cong; chợ nổi buổi sáng; hàng dừa nước
FOREGROUND: Bờ sông, xuồng ba lá
MIDGROUND: Mặt sông, chợ nổi
BACKGROUND: Hàng dừa, bầu trời chiều
LIGHTING: Nắng chiều vàng
WEATHER: Nắng nhẹ
PALETTE: Vàng nghệ; xanh lá; nâu gỗ
FORBIDDEN: Nhà cao tầng; xe hơi hiện đại

PROP: Chiếc Ô Đỏ
DESCRIPTION: Ô đỏ cán gỗ, nan tre
OWNER: Bà Tư
SCENES: 1, 2
INTERACTION: cầm; mở; đưa

QA:
MIN_SCORE: 8.5
REQUIRE_TECHNICAL: true
REQUIRE_CREATIVE_REVIEW: true
LANGUAGE_GATE: true
MAX_HARD_FAILS: 0

OUTPUT:
RESOLUTION: 1920x1080
FPS: 24
FORMAT: MP4
DRAFT_FOLDER: drive:drafts
MASTER: MANUAL_ONLY

END_CARD:
TEXT: Hẹn gặp lại
DURATION: 3.0
STYLE: Chữ trắng trên nền tối

SCENE 1: Buổi chiều ở bến sông
LOCATION: BEN_SONG
TIME_OF_DAY: Chiều
MOOD: Bình yên
DURATION: AUTO
VISUAL: Bến sông vàng nắng, chợ nổi nhộn nhịp.
ACTION: Khoa bước nhanh dọc bờ sông rồi dừng lại.
EXPRESSION: Bà Tư: lo lắng nhìn quanh
CAMERA: Góc rộng toàn cảnh bến sông
CAMERA_MOVEMENT: PAN_RIGHT
VOICE_NOTE: Giọng kể chậm, ấm.

SHOT SH01:
TYPE: ESTABLISHING
CAMERA: Toàn cảnh bến sông
CAMERA_MOVEMENT: PAN_RIGHT
SUBJECT: Bà Tư
DURATION: AUTO
ACTION: Bà Tư đứng chờ ở bến.
EXPRESSION: lo lắng
VFX: nắng chiều; bụi vàng

NARRATION [L001]: Chiều xuống, bến sông quê vàng rực nắng.
DIALOGUE: Khoa: Bà ơi, bà đợi ai vậy ạ?
DIALOGUE: Bà Tư: Tôi đợi con gái, mà nó chưa tới.
SFX: Tiếng mái chèo | TRIGGER: L001 | PRIORITY: REQUIRED
AMBIENCE: Sông nước buổi chiều | MODE: LOOP
BGM: Đàn tranh nhẹ | INTENSITY: LOW
VFX: Ánh nắng lấp lánh | TRIGGER: L001
TRANSITION: DISSOLVE
END_SCENE

SCENE 2: Chiếc ô đỏ
LOCATION: Bến sông quê buổi tối
TIME_OF_DAY: Tối
MOOD: Ấm áp
DURATION: AUTO
VISUAL: Bến sông lên đèn, mặt nước tối dần.
SHOT SH02:
TYPE: close_up
SUBJECT: Chiếc Ô Đỏ
NARRATION: Khoa đưa chiếc ô cho bà.
DIALOGUE: Bà Tư: Cảm ơn con nhé.
SFX: NONE
AMBIENCE: NONE
BGM: NONE
MEME: NONE
TRANSITION: FADE_TO_BLACK
END_SCENE

END_SCRIPT
"""


class TestFixtureParses(unittest.TestCase):
    def test_fixture_parses(self):
        text = open(FIXTURE, encoding="utf-8").read()
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.validation_errors, [])
        self.assertEqual(len(doc.scenes), 8)
        self.assertEqual([s.number for s in doc.scenes], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(len(doc.characters), 4)
        # 10 spoken lines: 1 + 2 + 1 + 1 + 2 + 1 + 1 + 1
        self.assertEqual(len(doc.spoken_lines), 10)
        self.assertEqual(
            [s.transition for s in doc.scenes],
            ["DISSOLVE", "CUT", "FADE", "CUT", "CUT", "MATCH_CUT", "FADE", "FADE_TO_BLACK"])
        # Every scene has SFX + ambience + MUSIC (aliased to BGM).
        for scene in doc.scenes:
            types = [c.cue_type for c in scene.audio_cues]
            self.assertIn("SFX", types)
            self.assertIn("AMBIENCE", types)
            self.assertIn("BGM", types)
        # MEME: NONE respected in scenes 3, 4, 6, 7, 8; real memes in 1, 2, 5.
        meme_none = {s.number for s in doc.scenes if s.meme_none}
        self.assertEqual(meme_none, {3, 4, 6, 7, 8})
        meme_scenes = {s.number for s in doc.scenes
                       if any(c.cue_type == "MEME" for c in s.audio_cues)}
        self.assertEqual(meme_scenes, {1, 2, 5})
        # No head_ratio in the fixture: the locked default applies, even
        # though an APPEARANCE line mentions "42%" as free text.
        for char in doc.characters:
            self.assertEqual(char.head_ratio, 0.34)
        # Narrator lines resolve to Narrator; character speakers canonical.
        narrations = [ln for ln in doc.spoken_lines if ln.kind == "narration"]
        self.assertEqual(len(narrations), 3)
        self.assertTrue(all(ln.speaker == "Narrator" for ln in narrations))
        # Line numbers are recorded on every node.
        self.assertGreater(doc.scenes[0].line, 0)
        self.assertGreater(doc.characters[0].line, 0)
        self.assertGreater(doc.spoken_lines[0].line, 0)

    def test_snapshot_hash_stable_and_round_trip(self):
        text = open(FIXTURE, encoding="utf-8").read()
        doc1 = parse_studio_script_v1(text)
        doc2 = parse_studio_script_v1(text)
        self.assertEqual(doc1.snapshot_hash, doc2.snapshot_hash)
        self.assertRegex(doc1.snapshot_hash, r"^[0-9a-f]{64}$")
        # A different input hashes differently.
        doc3 = parse_studio_script_v1(text + "\n")
        self.assertNotEqual(doc1.snapshot_hash, doc3.snapshot_hash)
        # to_dict() JSON round-trip.
        data = doc1.to_dict()
        self.assertEqual(json.loads(doc1.to_json()), data)
        self.assertEqual(data["snapshot_hash"], doc1.snapshot_hash)
        self.assertEqual(len(data["scenes"]), 8)
        self.assertEqual(len(data["characters"]), 4)


class TestSyntheticFullScript(unittest.TestCase):
    def test_every_block_parsed(self):
        doc = parse_studio_script_v1(SYNTHETIC_FULL)
        self.assertTrue(doc.is_valid, [(i.line, i.code, i.message) for i in doc.validation_errors])
        self.assertEqual(doc.warnings, [])

        meta = doc.to_dict()["meta"]
        self.assertEqual(meta["project"], "Dự án thử nghiệm")
        self.assertEqual(meta["language"], "vi-VN")
        self.assertEqual(meta["genre"], "Truyện ngắn")
        self.assertEqual(meta["visual_style"], "Premium Stickman Cinematic B")
        self.assertEqual(meta["aspect_ratio"], "16:9")
        self.assertEqual(meta["target_duration"], "AUTO")
        self.assertEqual(meta["tone"], "Ấm áp")
        self.assertEqual(meta["meme_policy"], "NONE")
        self.assertEqual(meta["meme_max_per_minute"], 0)

        ga = doc.global_audio
        self.assertEqual(ga.narration_gain_db, -1.5)
        self.assertEqual(ga.dialogue_gain_db, 0.0)
        self.assertEqual(ga.ambience_gain_db, -20.0)
        self.assertEqual(ga.foley_gain_db, -10.0)
        self.assertEqual(ga.sfx_gain_db, -8.0)
        self.assertEqual(ga.bgm_gain_db, -16.0)
        self.assertEqual(ga.bgm_ducking_db, -8.0)
        self.assertEqual(ga.master_limit_db, -1.5)
        self.assertEqual(ga.buses, ["narration", "dialogue", "ambience", "foley", "sfx", "bgm"])

        self.assertEqual(doc.constraints, [
            "Không dùng chữ tiếng Anh trên màn hình",
            "Không thay đổi lời thoại",
        ])

        khoa = doc.get_character("Khoa")
        self.assertEqual(khoa.role, "Người kể chuyện trẻ")
        self.assertEqual(khoa.appearance, "Đầu tròn, áo khoác xanh")
        self.assertEqual(khoa.traits, ["Tốt bụng", "hay giúp đỡ người lạ", "đi nhanh"])
        self.assertEqual(khoa.costume, "Áo khoác xanh đậm, quần đen")
        self.assertEqual(khoa.costume_changes[0]["scene_number"], 2)
        self.assertEqual(khoa.costume_changes[0]["outfit"], "Áo mưa vàng")
        self.assertEqual(khoa.voice, "AUTO")
        self.assertEqual(khoa.voice_style, "Trẻ, ấm áp")
        self.assertEqual(khoa.head_ratio, 0.34)
        self.assertEqual(khoa.identity_id, "khoa-01")
        ba_tu = doc.get_character("Bà Tư")
        self.assertEqual(ba_tu.traits, ["Chậm chạp", "hiền hậu", "mắt kém"])
        self.assertEqual(ba_tu.identity_id, "Bà Tư")  # default = name

        loc = doc.get_location("BEN_SONG")
        self.assertEqual(loc.name, "Bến sông quê")
        self.assertEqual(loc.period, "Hiện đại")
        self.assertEqual(loc.geography, "Miền Tây sông nước")
        self.assertEqual(loc.architecture, "Nhà sàn gỗ, cầu khỉ")
        self.assertEqual(loc.features, ["Cầu khỉ cong", "chợ nổi buổi sáng", "hàng dừa nước"])
        self.assertEqual(loc.foreground, "Bờ sông, xuồng ba lá")
        self.assertEqual(loc.midground, "Mặt sông, chợ nổi")
        self.assertEqual(loc.background, "Hàng dừa, bầu trời chiều")
        self.assertEqual(loc.lighting, "Nắng chiều vàng")
        self.assertEqual(loc.weather, "Nắng nhẹ")
        self.assertEqual(loc.palette, ["Vàng nghệ", "xanh lá", "nâu gỗ"])
        self.assertEqual(loc.forbidden, ["Nhà cao tầng", "xe hơi hiện đại"])

        prop = doc.props[0]
        self.assertEqual(prop.name, "Chiếc Ô Đỏ")
        self.assertEqual(prop.description, "Ô đỏ cán gỗ, nan tre")
        self.assertEqual(prop.owner, "Bà Tư")
        self.assertEqual(prop.scenes, [1, 2])
        self.assertFalse(prop.all_scenes)
        self.assertEqual(prop.interactions, ["cầm", "mở", "đưa"])

        self.assertEqual(doc.qa.min_score, 8.5)
        self.assertTrue(doc.qa.require_technical)
        self.assertTrue(doc.qa.require_creative_review)
        self.assertTrue(doc.qa.language_gate)
        self.assertEqual(doc.qa.max_hard_fails, 0)

        self.assertEqual(doc.output.resolution, "1920x1080")
        self.assertEqual(doc.output.fps, 24)
        self.assertEqual(doc.output.format, "MP4")
        self.assertEqual(doc.output.draft_folder, "drive:drafts")
        self.assertEqual(doc.output.master, "MANUAL_ONLY")

        self.assertEqual(doc.end_card.text, "Hẹn gặp lại")
        self.assertEqual(doc.end_card.duration, 3.0)
        self.assertEqual(doc.end_card.style, "Chữ trắng trên nền tối")

        scene1, scene2 = doc.scenes
        # LOCATION id reference vs inline free text.
        self.assertEqual(scene1.location_ref, "BEN_SONG")
        self.assertEqual(scene1.location_text, "")
        self.assertIsNone(scene2.location_ref)
        self.assertEqual(scene2.location_text, "Bến sông quê buổi tối")
        self.assertEqual(scene1.time_of_day, "Chiều")
        self.assertEqual(scene1.mood, "Bình yên")
        self.assertEqual(scene1.visual, "Bến sông vàng nắng, chợ nổi nhộn nhịp.")
        self.assertEqual(scene1.actions, ["Khoa bước nhanh dọc bờ sông rồi dừng lại."])
        self.assertEqual(scene1.expressions[0]["character"], "Bà Tư")
        self.assertEqual(scene1.expressions[0]["expression"], "lo lắng nhìn quanh")
        self.assertEqual(scene1.camera, "Góc rộng toàn cảnh bến sông")
        self.assertEqual(scene1.camera_movement, "PAN_RIGHT")
        self.assertEqual(scene1.voice_note, "Giọng kể chậm, ấm.")
        self.assertEqual(scene1.transition, "DISSOLVE")
        self.assertEqual(scene2.transition, "FADE_TO_BLACK")

        shot = scene1.shots[0]
        self.assertEqual(shot.id, "SH01")
        self.assertEqual(shot.type, "establishing")  # UPPER_SNAKE normalized
        self.assertEqual(shot.camera, "Toàn cảnh bến sông")
        self.assertEqual(shot.camera_movement, "PAN_RIGHT")
        self.assertEqual(shot.subject, "Bà Tư")
        self.assertEqual(shot.action, "Bà Tư đứng chờ ở bến.")
        self.assertEqual(shot.expression, "lo lắng")
        self.assertEqual(shot.vfx, ["nắng chiều", "bụi vàng"])
        self.assertEqual(scene2.shots[0].type, "close_up")
        self.assertEqual(scene2.shots[0].subject, "Chiếc Ô Đỏ")

        # Spoken lines: explicit L001, then auto L002.. in document order.
        lines = doc.spoken_lines
        self.assertEqual([ln.line_id for ln in lines],
                         ["L001", "L002", "L003", "L004", "L005"])
        self.assertEqual([ln.speaker for ln in lines],
                         ["Narrator", "Khoa", "Bà Tư", "Narrator", "Bà Tư"])
        self.assertEqual([ln.kind for ln in lines],
                         ["narration", "dialogue", "dialogue", "narration", "dialogue"])
        self.assertEqual(lines[0].text, "Chiều xuống, bến sông quê vàng rực nắng.")
        self.assertEqual(lines[0].shot_id, "SH01")
        self.assertEqual(lines[0].voice_note, "Giọng kể chậm, ấm.")
        self.assertEqual(lines[3].scene_number, 2)

        cues = scene1.audio_cues
        sfx = [c for c in cues if c.cue_type == "SFX"][0]
        self.assertEqual(sfx.name, "Tiếng mái chèo")
        self.assertEqual(sfx.trigger, "L001")
        self.assertEqual(sfx.priority, "REQUIRED")
        amb = [c for c in cues if c.cue_type == "AMBIENCE"][0]
        self.assertEqual(amb.mode, "LOOP")
        bgm = [c for c in cues if c.cue_type == "BGM"][0]
        self.assertEqual(bgm.intensity, "LOW")
        self.assertEqual(scene1.vfx_cues[0].name, "Ánh nắng lấp lánh")
        self.assertEqual(scene1.vfx_cues[0].trigger, "L001")

        # Scene 2: every NONE directive respected, no cues invented.
        self.assertTrue(scene2.sfx_none)
        self.assertTrue(scene2.ambience_none)
        self.assertTrue(scene2.bgm_none)
        self.assertTrue(scene2.meme_none)
        self.assertEqual(scene2.audio_cues, [])


class TestHeadRatioLock(unittest.TestCase):
    def _doc_with_ratio(self, ratio_line):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            ratio_line,
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
        ])
        return parse_studio_script_v1(text)

    def test_default_is_034(self):
        doc = self._doc_with_ratio("ROLE: Người kể")
        self.assertEqual(doc.characters[0].head_ratio, HEAD_RATIO_DEFAULT)
        self.assertEqual(HEAD_RATIO_DEFAULT, 0.34)
        self.assertEqual((HEAD_RATIO_MIN, HEAD_RATIO_MAX), (0.33, 0.35))
        self.assertTrue(doc.is_valid)

    def test_explicit_034_ok_and_boundaries_ok(self):
        for value in ("0.34", "0.33", "0.35"):
            doc = self._doc_with_ratio(f"HEAD_RATIO: {value}")
            self.assertTrue(doc.is_valid, _codes(doc))
            self.assertEqual(doc.characters[0].head_ratio, float(value))

    def test_042_rejected(self):
        doc = self._doc_with_ratio("HEAD_RATIO: 0.42")
        self.assertFalse(doc.is_valid)
        issues = _error_at(doc, "V1E009")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 3)

    def test_030_rejected(self):
        doc = self._doc_with_ratio("HEAD_RATIO: 0.30")
        self.assertIn("V1E009", _codes(doc))

    def test_non_numeric_rejected(self):
        doc = self._doc_with_ratio("HEAD_RATIO: to")
        self.assertIn("V1E008", _codes(doc))


class TestDetectFormat(unittest.TestCase):
    def test_fixture_is_studio_v1(self):
        text = open(FIXTURE, encoding="utf-8").read()
        self.assertEqual(detect_format(text), "studio_v1")

    def test_freeform_script_is_freeform(self):
        text = open(FREEFORM_SCRIPT, encoding="utf-8").read()
        self.assertEqual(detect_format(text), "freeform")

    def test_project_plus_scene_without_marker(self):
        text = "PROJECT: X\nSCENE 1: Mở đầu\nNARRATION: Chào.\n"
        self.assertEqual(detect_format(text), "studio_v1")

    def test_project_alone_is_freeform(self):
        self.assertEqual(detect_format("PROJECT: X\nNARRATION: Chào.\n"), "freeform")

    def test_plain_text_is_freeform(self):
        self.assertEqual(detect_format("Chào buổi sáng.\n"), "freeform")


class TestLineNumberedErrors(unittest.TestCase):
    def test_bad_shot_type(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "SHOT SH01:",
            "TYPE: BIRDSEYE",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E014")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 5)

    def test_missing_shot_type(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "SHOT SH01:",
            "CAMERA: Góc rộng",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E013")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 4)

    def test_undeclared_dialogue_speaker(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Người Lạ: Xin chào.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E015")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 4)

    def test_sfx_trigger_unknown_line_id_recorded_verbatim(self):
        # V1E022 is timeline-stage only: parse records the trigger
        # verbatim and raises NO parse-time error for an unknown LINE_ID.
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "SFX: Tiếng chuông | TRIGGER: L099 | PRIORITY: REQUIRED",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.scenes[0].audio_cues[0].trigger, "L099")
        self.assertNotIn("V1E022", _codes(doc))

    def test_sfx_trigger_existing_line_id_ok(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "SFX: Tiếng chuông | TRIGGER: L001 | PRIORITY: REQUIRED",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))

    def test_duplicate_character(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E001")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 3)

    def test_duplicate_scene(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Một",
            "DIALOGUE: Khoa: Chào.",
            "SCENE 1: Hai",
            "DIALOGUE: Khoa: Chào lại.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E003")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 5)

    def test_costume_change_to_nonexistent_scene(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "COSTUME_CHANGE: SCENE 9: Áo mưa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E018")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 3)

    def test_output_master_auto_rejected(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "OUTPUT:",
            "MASTER: AUTO",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E017")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 6)

    def test_production_tag_in_spoken_text(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Nhìn kìa SFX: chuông reo.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E016")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 4)
        # The spoken text itself is never rewritten.
        self.assertEqual(doc.spoken_lines[0].text, "Nhìn kìa SFX: chuông reo.")

    def test_duplicate_line_id(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "NARRATION [L001]: Một.",
            "NARRATION [L001]: Hai.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E005")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 5)

    def test_explicit_line_id_normalised_to_canonical_form(self):
        # SPEC §7.1: canonical form is L + 3-digit zero-pad.
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "NARRATION [L2]: Hai.",
            "NARRATION [L12]: Mười hai.",
            "NARRATION [L1234]: Dài.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid)
        ids = [ln.line_id for ln in doc.scenes[0].spoken_lines]
        self.assertEqual(ids, ["L002", "L012", "L1234"])
        # [L002] and [L2] are the same canonical id -> duplicate.
        text2 = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "NARRATION [L002]: Một.",
            "NARRATION [L2]: Hai.",
        ])
        doc2 = parse_studio_script_v1(text2)
        self.assertEqual(len(_error_at(doc2, "V1E005")), 1)
        # Auto ids skip explicitly used canonical ids.
        text3 = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "NARRATION [L1]: Một.",
            "NARRATION: Hai.",
        ])
        doc3 = parse_studio_script_v1(text3)
        self.assertEqual([ln.line_id for ln in doc3.scenes[0].spoken_lines],
                         ["L001", "L002"])

    def test_no_scenes_and_no_lines_are_errors(self):
        doc = parse_studio_script_v1("PROJECT: Trống\n")
        self.assertIn("V1E020", _codes(doc))
        self.assertIn("V1E023", _codes(doc))
        self.assertFalse(doc.is_valid)

    def test_parse_never_raises_without_strict(self):
        doc = parse_studio_script_v1("hello world, no structure at all")
        self.assertFalse(doc.is_valid)
        self.assertTrue(doc.validation_errors)

    def test_strict_raises_on_first_error(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Người Lạ: Xin chào.",
        ])
        with self.assertRaises(StudioScriptV1Error) as ctx:
            parse_studio_script_v1(text, strict=True)
        self.assertEqual(ctx.exception.issue.code, "V1E015")
        # The parser class also supports strict parsing.
        with self.assertRaises(StudioScriptV1Error):
            StudioScriptV1Parser().parse(text, strict=True)


class TestUnsupportedFields(unittest.TestCase):
    def test_unknown_keys_recorded_with_line_numbers(self):
        text = "\n".join([
            "PROJECT: Test",
            "FROBNICATE: yes",
            "CHARACTER: Khoa",
            "FAVORITE_COLOR: xanh",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "MYSTERY_KEY: something",
        ])
        doc = parse_studio_script_v1(text)
        by_key = {u.key: u for u in doc.unsupported_fields}
        self.assertIn("FROBNICATE", by_key)
        self.assertEqual(by_key["FROBNICATE"].line, 2)
        self.assertEqual(by_key["FROBNICATE"].context, "document")
        self.assertIn("FAVORITE_COLOR", by_key)
        self.assertEqual(by_key["FAVORITE_COLOR"].line, 4)
        self.assertEqual(by_key["FAVORITE_COLOR"].context, "character:Khoa")
        self.assertEqual(by_key["FAVORITE_COLOR"].value, "xanh")
        self.assertIn("MYSTERY_KEY", by_key)
        self.assertEqual(by_key["MYSTERY_KEY"].line, 7)
        # Unknown fields are warnings-free data, not validation errors.
        self.assertTrue(doc.is_valid)

    def test_unknown_sfx_param_recorded(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "SFX: Chuông | TRIGGER: L001 | SPARKLE: yes",
        ])
        doc = parse_studio_script_v1(text)
        keys = [u.key for u in doc.unsupported_fields]
        self.assertIn("SFX.SPARKLE", keys)


class TestUnicodeAndAliases(unittest.TestCase):
    def test_vietnamese_preserved_verbatim(self):
        text = "\n".join([
            "PROJECT: Chuyện ở Bến Sông",
            "CHARACTER: Bà Tư",
            "APPEARANCE: Tóc bạc, áo dài tím, gậy tre",
            "SCENE 1: Buổi chiều",
            "DIALOGUE: Bà Tư: Cảm ơn con nhé, trời sắp tối rồi!",
            "NARRATION: Nắng chiều vàng rực trên mặt sông quê.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.characters[0].name, "Bà Tư")
        self.assertEqual(doc.characters[0].appearance, "Tóc bạc, áo dài tím, gậy tre")
        self.assertEqual(doc.spoken_lines[0].text, "Cảm ơn con nhé, trời sắp tối rồi!")
        self.assertEqual(doc.spoken_lines[1].text, "Nắng chiều vàng rực trên mặt sông quê.")

    def test_narrator_aliases(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "NGƯỜI KỂ CHUYỆN: Một buổi chiều yên ả.",
            "DẪN CHUYỆN: Rồi mọi thứ thay đổi.",
            "NARRATOR: The end is near.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual([ln.speaker for ln in doc.spoken_lines],
                         ["Narrator", "Narrator", "Narrator"])
        self.assertTrue(all(ln.kind == "narration" for ln in doc.spoken_lines))

    def test_bare_speaker_lines_and_case_insensitive_match(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Bà Tư",
            "SCENE 1: Mở đầu",
            "BÀ TƯ: Chào con.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.spoken_lines[0].speaker, "Bà Tư")
        self.assertEqual(doc.spoken_lines[0].kind, "dialogue")

    def test_music_alias_of_bgm(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "MUSIC: Đàn tranh nhẹ | INTENSITY: LOW",
        ])
        doc = parse_studio_script_v1(text)
        cue = doc.scenes[0].audio_cues[0]
        self.assertEqual(cue.cue_type, "BGM")
        self.assertEqual(cue.source_key, "MUSIC")
        self.assertEqual(cue.intensity, "LOW")

    def test_style_alias_of_visual_style(self):
        # STYLE alone fills the single visual_style field; there is no
        # separate "style" field on the document or in to_dict() meta.
        text = "\n".join([
            "PROJECT: Test",
            "STYLE: Kiểu cũ",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertEqual(doc.visual_style, "Kiểu cũ")
        self.assertFalse(hasattr(doc, "style"))
        self.assertNotIn("style", doc.to_dict()["meta"])

    def test_keys_case_insensitive(self):
        text = "\n".join([
            "project: Test",
            "character: Khoa",
            "scene 1: Mở đầu",
            "dialogue: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(len(doc.spoken_lines), 1)

    def test_explicit_line_id_on_dialogue(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE [L007]: Khoa: Chào.",
            "DIALOGUE: Khoa: Lại chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertEqual([ln.line_id for ln in doc.spoken_lines], ["L007", "L001"])

    def test_prop_scenes_all_and_owner_error(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "PROP: Chiếc Ô",
            "OWNER: Người Lạ",
            "SCENES: ALL",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.props[0].all_scenes)
        self.assertEqual(doc.props[0].scenes, [])
        # Unresolvable OWNER is an ERROR (V1E018, SPEC §8.2), not a warning.
        self.assertFalse(doc.is_valid)
        self.assertEqual(_codes(doc), ["V1E018"])
        self.assertEqual(doc.warnings, [])

    def test_shot_subject_error(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "SHOT SH01:",
            "TYPE: medium",
            "SUBJECT: Vật Thể Lạ",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        # Unresolvable SUBJECT is an ERROR (V1E018, SPEC §8.2), not a warning.
        self.assertFalse(doc.is_valid)
        self.assertEqual(_codes(doc), ["V1E018"])
        self.assertEqual(doc.warnings, [])

    def test_global_audio_defaults(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        ga = doc.global_audio
        self.assertEqual((ga.narration_gain_db, ga.dialogue_gain_db), (0.0, 0.0))
        self.assertEqual((ga.ambience_gain_db, ga.foley_gain_db), (-18.0, -12.0))
        self.assertEqual((ga.sfx_gain_db, ga.bgm_gain_db), (-6.0, -18.0))
        self.assertEqual((ga.bgm_ducking_db, ga.master_limit_db), (-6.0, -1.0))
        self.assertIsNone(doc.end_card)
        self.assertEqual(doc.constraints, [])


class TestShotVocabularyMatchesCameraPlanner(unittest.TestCase):
    def test_shot_types_match(self):
        try:
            from ai_clip_studio.camera_planner import SHOT_TYPES as PLANNER_TYPES
        except ImportError:
            self.skipTest("camera_planner unavailable (PIL)")
        self.assertEqual(tuple(SHOT_TYPES), tuple(PLANNER_TYPES))


class TestSchemaStructuralCheck(unittest.TestCase):
    """Dependency-free structural check: the fixture document's to_dict()
    output must satisfy docs/studio_script_v1.schema.json (required keys,
    types, enums). No jsonschema package required."""

    def test_schema_file_valid_and_document_conforms(self):
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        defs = schema["$defs"]

        text = open(FIXTURE, encoding="utf-8").read()
        data = parse_studio_script_v1(text).to_dict()

        for key in schema["required"]:
            self.assertIn(key, data)
        self.assertRegex(data["snapshot_hash"], r"^[0-9a-f]{64}$")
        self.assertIs(data["is_valid"], True)

        meta = data["meta"]
        for key in ["project", "language", "genre", "visual_style",
                    "aspect_ratio", "target_duration", "tone", "meme_policy",
                    "meme_max_per_minute"]:
            self.assertIn(key, meta)
        self.assertNotIn("style", meta)
        self.assertIn(meta["aspect_ratio"], defs["aspectRatio"]["enum"])
        self.assertIn(meta["meme_policy"], defs["memePolicy"]["enum"])
        self.assertIsInstance(meta["meme_max_per_minute"], int)

        for char in data["characters"]:
            for key in ["name", "role", "appearance", "traits", "costume",
                        "costume_changes", "voice", "voice_style",
                        "head_ratio", "identity_id", "line"]:
                self.assertIn(key, char)
            self.assertIsInstance(char["traits"], list)
            self.assertGreaterEqual(char["head_ratio"], HEAD_RATIO_MIN)
            self.assertLessEqual(char["head_ratio"], HEAD_RATIO_MAX)

        for scene in data["scenes"]:
            for key in ["number", "title", "line", "location_ref",
                        "location_text", "time_of_day", "mood", "duration",
                        "duration_seconds", "visual", "actions", "expressions",
                        "camera", "camera_movement", "voice_note", "meme_note",
                        "transition", "sfx_none", "ambience_none", "bgm_none",
                        "meme_none", "shots", "spoken_lines", "audio_cues",
                        "vfx_cues"]:
                self.assertIn(key, scene)
            self.assertIn(scene["transition"], defs["transition"]["enum"])
            self.assertIn(scene["camera_movement"], defs["cameraMovement"]["enum"])
            for shot in scene["shots"]:
                self.assertIn(shot["type"], defs["shotType"]["enum"])
            for line in scene["spoken_lines"]:
                self.assertIn(line["kind"], ["narration", "dialogue"])
                self.assertRegex(line["line_id"], r"^L\d+$")
            for cue in scene["audio_cues"]:
                self.assertIn(cue["cue_type"], defs["cueType"]["enum"])

        ga = data["global_audio"]
        for key in ["narration_gain_db", "dialogue_gain_db", "ambience_gain_db",
                    "foley_gain_db", "sfx_gain_db", "bgm_gain_db",
                    "bgm_ducking_db", "master_limit_db", "buses"]:
            self.assertIn(key, ga)
        self.assertEqual(ga["buses"], ["narration", "dialogue", "ambience",
                                       "foley", "sfx", "bgm"])

        qa = data["qa"]
        self.assertGreaterEqual(qa["min_score"], 0)
        self.assertLessEqual(qa["min_score"], 10)
        self.assertIsInstance(qa["require_technical"], bool)

        out = data["output"]
        self.assertIn(out["resolution"], defs["resolution"]["enum"])
        self.assertIn(out["fps"], defs["frameRate"]["enum"])
        self.assertEqual(out["master"], "MANUAL_ONLY")

        self.assertIn(data["end_card"], (None, dict))
        self.assertIsInstance(data["constraints"], list)
        self.assertIsInstance(data["unsupported_fields"], list)
        self.assertIsInstance(data["validation_errors"], list)
        self.assertIsInstance(data["warnings"], list)


class TestHeaderDefaultsAndStyleAlias(unittest.TestCase):
    def test_absent_headers_are_unspecified_none(self):
        # SPEC §4: no upstream defaults are inherited. PROJECT / GENRE /
        # VISUAL_STYLE / TONE absent means "unspecified" (None); the
        # other header defaults are unchanged.
        doc = parse_studio_script_v1(
            "# STUDIO SCRIPT V1\nSCENE 1: Mở đầu\nNARRATION: Chào.\n")
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertIsNone(doc.project)
        self.assertIsNone(doc.genre)
        self.assertIsNone(doc.visual_style)
        self.assertIsNone(doc.tone)
        self.assertEqual(doc.language, "vi-VN")
        self.assertEqual(doc.aspect_ratio, "16:9")
        self.assertEqual(doc.target_duration, "AUTO")
        self.assertEqual(doc.meme_policy, "CONTEXTUAL")
        self.assertEqual(doc.meme_max_per_minute, 2)
        meta = doc.to_dict()["meta"]
        self.assertIsNone(meta["project"])
        self.assertIsNone(meta["genre"])
        self.assertIsNone(meta["visual_style"])
        self.assertIsNone(meta["tone"])
        self.assertNotIn("style", meta)

    def test_visual_style_only(self):
        text = "\n".join([
            "PROJECT: Test",
            "VISUAL_STYLE: Kiểu mới",
            "SCENE 1: Mở đầu",
            "NARRATION: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertEqual(doc.visual_style, "Kiểu mới")
        self.assertEqual(doc.unsupported_fields, [])

    def test_both_style_keys_same_value(self):
        text = "\n".join([
            "PROJECT: Test",
            "STYLE: Kiểu chung",
            "VISUAL_STYLE: Kiểu chung",
            "SCENE 1: Mở đầu",
            "NARRATION: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.visual_style, "Kiểu chung")
        self.assertEqual(doc.unsupported_fields, [])

    def test_both_style_keys_different_values_visual_style_wins(self):
        # STYLE first, then VISUAL_STYLE: the STYLE loser is recorded
        # with its own line number.
        text = "\n".join([
            "PROJECT: Test",
            "STYLE: Kiểu cũ",
            "VISUAL_STYLE: Kiểu mới",
            "SCENE 1: Mở đầu",
            "NARRATION: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.visual_style, "Kiểu mới")
        self.assertEqual(len(doc.unsupported_fields), 1)
        loser = doc.unsupported_fields[0]
        self.assertEqual(loser.key, "STYLE")
        self.assertEqual(loser.value, "Kiểu cũ")
        self.assertEqual(loser.line, 2)
        self.assertEqual(loser.context, "document")
        # VISUAL_STYLE first, then STYLE: same outcome, loser line is
        # the STYLE line itself.
        text2 = "\n".join([
            "PROJECT: Test",
            "VISUAL_STYLE: Kiểu mới",
            "STYLE: Kiểu cũ",
            "SCENE 1: Mở đầu",
            "NARRATION: Chào.",
        ])
        doc2 = parse_studio_script_v1(text2)
        self.assertEqual(doc2.visual_style, "Kiểu mới")
        self.assertEqual(len(doc2.unsupported_fields), 1)
        self.assertEqual(doc2.unsupported_fields[0].key, "STYLE")
        self.assertEqual(doc2.unsupported_fields[0].value, "Kiểu cũ")
        self.assertEqual(doc2.unsupported_fields[0].line, 3)


class TestDuplicateV1E006(unittest.TestCase):
    def _valid_prefix(self):
        return ["PROJECT: Test", "CHARACTER: Khoa"]

    def _with_scene(self, lines):
        return parse_studio_script_v1("\n".join(
            self._valid_prefix() + lines + [
                "SCENE 1: Mở đầu", "DIALOGUE: Khoa: Chào."]))

    def test_duplicate_header_key(self):
        for key, first, second in [
                ("PROJECT", "Một", "Hai"),
                ("LANGUAGE", "vi-VN", "en-US"),
                ("STYLE", "Kiểu một", "Kiểu hai"),
                ("MEME_POLICY", "NONE", "ALWAYS")]:
            with self.subTest(key=key):
                text = "\n".join([
                    f"{key}: {first}", f"{key}: {second}",
                    "SCENE 1: Mở đầu", "NARRATION: Chào.",
                ])
                doc = parse_studio_script_v1(text)
                issues = _error_at(doc, "V1E006")
                self.assertEqual(len(issues), 1)
                self.assertEqual(issues[0].line, 2)
        # STYLE + VISUAL_STYLE together is the alias rule, not a duplicate.
        doc = parse_studio_script_v1("\n".join([
            "STYLE: Kiểu cũ", "VISUAL_STYLE: Kiểu mới",
            "SCENE 1: Mở đầu", "NARRATION: Chào.",
        ]))
        self.assertNotIn("V1E006", _codes(doc))

    def test_duplicate_single_valued_block_fields(self):
        cases = [
            ("character", ["ROLE: Một", "ROLE: Hai"], "ROLE"),
            ("location", ["LOCATION: NOI_X", "NAME: Một", "NAME: Hai"], "NAME"),
            ("prop", ["PROP: Vật X", "DESCRIPTION: Một", "DESCRIPTION: Hai"],
             "DESCRIPTION"),
            ("global_audio", ["GLOBAL_AUDIO:", "NARRATION_GAIN_DB: 0",
                              "NARRATION_GAIN_DB: -3"], "NARRATION_GAIN_DB"),
            ("qa", ["QA:", "MIN_SCORE: 8.0", "MIN_SCORE: 9.0"], "MIN_SCORE"),
            ("output", ["OUTPUT:", "RESOLUTION: 1920x1080",
                        "RESOLUTION: 1280x720"], "RESOLUTION"),
            ("end_card", ["END_CARD:", "TEXT: Một", "TEXT: Hai"], "TEXT"),
        ]
        for label, block_lines, field in cases:
            with self.subTest(block=label):
                # Blocks that need a header of their own carry it in
                # block_lines; CHARACTER fields attach to the prefix char.
                if label == "character":
                    lines = block_lines
                else:
                    lines = block_lines
                doc = self._with_scene(lines)
                issues = _error_at(doc, "V1E006")
                self.assertEqual(len(issues), 1, _codes(doc))
                self.assertIn(field, issues[0].message)

    def test_duplicate_singleton_blocks(self):
        for block, field_line in [
                ("QA", "MIN_SCORE: 8.0"),
                ("GLOBAL_AUDIO", "NARRATION_GAIN_DB: 0"),
                ("OUTPUT", "FPS: 24"),
                ("END_CARD", "TEXT: Kết"),
                ("GLOBAL_NEGATIVE_CONSTRAINTS", "- Không làm X")]:
            with self.subTest(block=block):
                text = "\n".join([
                    "PROJECT: Test",
                    "CHARACTER: Khoa",
                    "SCENE 1: Mở đầu",
                    "DIALOGUE: Khoa: Chào.",
                    f"{block}:",
                    field_line,
                    f"{block}:",
                    field_line,
                ])
                doc = parse_studio_script_v1(text)
                issues = _error_at(doc, "V1E006")
                self.assertEqual(len(issues), 1, _codes(doc))
                self.assertEqual(issues[0].line, 7)

    def test_duplicate_pipe_subkey(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "SFX: Chuông | TRIGGER: L001 | TRIGGER: L002",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E006")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 5)
        # First value wins.
        self.assertEqual(doc.scenes[0].audio_cues[0].trigger, "L001")
        text2 = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "MEME: Meme mẫu | PRIORITY: REQUIRED | PRIORITY: OPTIONAL",
        ])
        doc2 = parse_studio_script_v1(text2)
        self.assertIn("V1E006", _codes(doc2))
        self.assertEqual(doc2.scenes[0].audio_cues[0].priority, "REQUIRED")

    def test_duplicate_costume_change_same_scene(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "COSTUME_CHANGE: SCENE 1: Áo mưa vàng",
            "COSTUME_CHANGE: SCENE 1: Áo mưa đỏ",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E006")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 4)
        self.assertEqual(len(doc.characters[0].costume_changes), 1)
        self.assertEqual(doc.characters[0].costume_changes[0]["outfit"],
                         "Áo mưa vàng")

    def test_costume_changes_for_different_scenes_ok(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "COSTUME_CHANGE: SCENE 1: Áo mưa vàng",
            "COSTUME_CHANGE: SCENE 2: Áo mưa đỏ",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "SCENE 2: Tiếp theo",
            "DIALOGUE: Khoa: Chào lại.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(len(doc.characters[0].costume_changes), 2)

    def test_second_ambience_bgm_meme_line(self):
        for label, cue_lines in [
                ("ambience", ["AMBIENCE: Sông | MODE: LOOP",
                              "AMBIENCE: Gió | MODE: ONCE"]),
                ("bgm+music", ["BGM: Đàn tranh | INTENSITY: LOW",
                               "MUSIC: Piano | INTENSITY: HIGH"]),
                ("meme", ["MEME: Meme một", "MEME: Meme hai"])]:
            with self.subTest(cue=label):
                text = "\n".join([
                    "PROJECT: Test",
                    "CHARACTER: Khoa",
                    "SCENE 1: Mở đầu",
                    "DIALOGUE: Khoa: Chào.",
                ] + cue_lines)
                doc = parse_studio_script_v1(text)
                self.assertIn("V1E006", _codes(doc))

    def test_duplicate_scene_and_shot_fields(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "TIME_OF_DAY: Sáng",
            "TIME_OF_DAY: Chiều",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertIn("V1E006", _codes(doc))
        self.assertEqual(doc.scenes[0].time_of_day, "Sáng")
        text2 = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "SHOT SH01:",
            "TYPE: medium",
            "TYPE: close_up",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc2 = parse_studio_script_v1(text2)
        self.assertIn("V1E006", _codes(doc2))
        self.assertEqual(doc2.scenes[0].shots[0].type, "medium")

    def test_transition_conflict_and_agreement(self):
        # Different values in the two TRANSITION positions: V1E006.
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "TRANSITION: CUT",
            "DIALOGUE: Khoa: Chào.",
            "TRANSITION: FADE",
        ])
        doc = parse_studio_script_v1(text)
        self.assertIn("V1E006", _codes(doc))
        self.assertEqual(doc.scenes[0].transition, "CUT")
        # Same value in both positions: allowed (SPEC §5.4).
        text2 = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "TRANSITION: FADE",
            "DIALOGUE: Khoa: Chào.",
            "TRANSITION: FADE",
        ])
        doc2 = parse_studio_script_v1(text2)
        self.assertTrue(doc2.is_valid, _codes(doc2))
        self.assertEqual(doc2.scenes[0].transition, "FADE")

    def test_repeatable_fields_do_not_false_positive(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "COSTUME_CHANGE: SCENE 1: Áo mưa vàng",
            "COSTUME_CHANGE: SCENE 2: Áo mưa đỏ",
            "SCENE 1: Mở đầu",
            "ACTION: Khoa bước đi.",
            "ACTION: Khoa dừng lại.",
            "EXPRESSION: Khoa: vui vẻ",
            "EXPRESSION: Khoa: ngạc nhiên",
            "VOICE_NOTE: Giọng chậm.",
            "VOICE_NOTE: Giọng ấm.",
            "NARRATION: Một.",
            "NARRATION: Hai.",
            "DIALOGUE: Khoa: Chào.",
            "SFX: Chuông | TRIGGER: L001",
            "SFX: Gió | TRIGGER: L002",
            "VFX: Nắng | TRIGGER: L001",
            "VFX: Bụi vàng",
            "SCENE 2: Tiếp theo",
            "DIALOGUE: Khoa: Chào lại.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertNotIn("V1E006", _codes(doc))
        self.assertEqual(len(doc.scenes[0].actions), 2)


class TestNoneDirectives(unittest.TestCase):
    def test_none_with_segments_is_v1e021(self):
        for label, none_line in [
                ("sfx", "SFX: NONE | TRIGGER: L001"),
                ("ambience", "AMBIENCE: NONE | MODE: ONCE"),
                ("bgm", "BGM: NONE | INTENSITY: LOW"),
                ("music", "MUSIC: NONE | INTENSITY: LOW"),
                ("meme", "MEME: NONE | PRIORITY: REQUIRED")]:
            with self.subTest(cue=label):
                text = "\n".join([
                    "PROJECT: Test",
                    "CHARACTER: Khoa",
                    "SCENE 1: Mở đầu",
                    "DIALOGUE: Khoa: Chào.",
                    none_line,
                ])
                doc = parse_studio_script_v1(text)
                issues = _error_at(doc, "V1E021")
                self.assertEqual(len(issues), 1, _codes(doc))
                self.assertEqual(issues[0].line, 5)

    def test_none_coexisting_with_cues_is_v1e024_error(self):
        cases = [
            ("sfx", "SFX: NONE", "SFX: Chuông | TRIGGER: L001"),
            ("ambience", "AMBIENCE: NONE", "AMBIENCE: Sông | MODE: LOOP"),
            ("bgm", "BGM: NONE", "BGM: Đàn tranh | INTENSITY: LOW"),
            ("meme", "MEME: NONE", "MEME: Meme mẫu"),
        ]
        for label, none_line, cue_line in cases:
            with self.subTest(cue=label):
                for order in ((none_line, cue_line), (cue_line, none_line)):
                    text = "\n".join([
                        "PROJECT: Test",
                        "CHARACTER: Khoa",
                        "SCENE 1: Mở đầu",
                        "DIALOGUE: Khoa: Chào.",
                        order[0], order[1],
                    ])
                    doc = parse_studio_script_v1(text)
                    self.assertFalse(doc.is_valid)
                    self.assertIn("V1E024", _codes(doc))

    def test_none_alone_is_valid(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "SFX: NONE",
            "AMBIENCE: NONE",
            "BGM: NONE",
            "MEME: NONE",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        scene = doc.scenes[0]
        self.assertTrue(scene.sfx_none)
        self.assertTrue(scene.ambience_none)
        self.assertTrue(scene.bgm_none)
        self.assertTrue(scene.meme_none)
        self.assertEqual(scene.audio_cues, [])


class TestDurations(unittest.TestCase):
    def test_duration_suffix_rejected(self):
        cases = [
            ("target", ["TARGET_DURATION: 30s"], 1),
            ("target-sec", ["TARGET_DURATION: 30sec"], 1),
            ("scene", ["SCENE 1: Mở đầu", "DURATION: 12s",
                       "DIALOGUE: Khoa: Chào."], 4),
            ("shot", ["SCENE 1: Mở đầu", "SHOT SH01:", "TYPE: medium",
                      "DURATION: 12s", "DIALOGUE: Khoa: Chào."], 6),
        ]
        for label, lines, err_line in cases:
            with self.subTest(case=label):
                text = "\n".join(["PROJECT: Test", "CHARACTER: Khoa"] + lines)
                # TARGET_DURATION cases need the header before CHARACTER.
                if label.startswith("target"):
                    text = "\n".join([
                        "PROJECT: Test", lines[0], "CHARACTER: Khoa",
                        "SCENE 1: Mở đầu", "DIALOGUE: Khoa: Chào."])
                    err_line = 2
                doc = parse_studio_script_v1(text)
                issues = _error_at(doc, "V1E012")
                self.assertEqual(len(issues), 1, _codes(doc))
                self.assertEqual(issues[0].line, err_line)

    def test_plain_and_auto_durations_accepted(self):
        for value, seconds in [("AUTO", None), ("0", 0.0), ("12", 12.0),
                               ("12.5", 12.5)]:
            with self.subTest(value=value):
                text = "\n".join([
                    "PROJECT: Test",
                    "CHARACTER: Khoa",
                    "SCENE 1: Mở đầu",
                    f"DURATION: {value}",
                    "DIALOGUE: Khoa: Chào.",
                ])
                doc = parse_studio_script_v1(text)
                self.assertTrue(doc.is_valid, _codes(doc))
                self.assertEqual(doc.scenes[0].duration_seconds, seconds)
        # Negative durations are invalid.
        doc = parse_studio_script_v1("\n".join([
            "PROJECT: Test", "CHARACTER: Khoa", "SCENE 1: Mở đầu",
            "DURATION: -5", "DIALOGUE: Khoa: Chào.",
        ]))
        self.assertIn("V1E012", _codes(doc))

    def test_end_card_duration(self):
        for value, valid in [("AUTO", False), ("12s", False), ("0", False),
                             ("-1", False), ("abc", False), ("3.0", True),
                             ("3", True)]:
            with self.subTest(value=value):
                text = "\n".join([
                    "PROJECT: Test",
                    "CHARACTER: Khoa",
                    "SCENE 1: Mở đầu",
                    "DIALOGUE: Khoa: Chào.",
                    "END_CARD:",
                    "TEXT: Kết",
                    f"DURATION: {value}",
                ])
                doc = parse_studio_script_v1(text)
                if valid:
                    self.assertTrue(doc.is_valid, _codes(doc))
                    self.assertEqual(doc.end_card.duration, float(value))
                else:
                    self.assertIn("V1E012", _codes(doc))


class TestMemeNote(unittest.TestCase):
    def test_meme_note_parsed_and_never_spoken(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "MEME: Meme mẫu | TRIGGER: L001",
            "MEME_NOTE: Ghi chú lý giải meme, không bao giờ bị đọc.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        scene = doc.scenes[0]
        self.assertEqual(scene.meme_note,
                         "Ghi chú lý giải meme, không bao giờ bị đọc.")
        # Never an unsupported field, never spoken text.
        self.assertEqual(doc.unsupported_fields, [])
        spoken = " ".join(ln.text for ln in doc.spoken_lines)
        self.assertNotIn("Ghi chú lý giải", spoken)
        self.assertEqual(doc.to_dict()["scenes"][0]["meme_note"],
                         scene.meme_note)

    def test_fixture_meme_notes_preserved(self):
        doc = parse_studio_script_v1(_read(FIXTURE))
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(len(doc.scenes), 8)
        for scene in doc.scenes:
            self.assertTrue(scene.meme_note, f"scene {scene.number}")


class TestVfxTriggerRule(unittest.TestCase):
    def test_single_vfx_name_with_trigger_ok(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "VFX: Ánh nắng | TRIGGER: L001",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(len(doc.scenes[0].vfx_cues), 1)
        self.assertEqual(doc.scenes[0].vfx_cues[0].trigger, "L001")

    def test_multiple_vfx_names_with_trigger_is_v1e019(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "VFX: Nắng chiều; bụi vàng | TRIGGER: L001",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E019")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 5)

    def test_multiple_vfx_names_without_trigger_ok(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
            "VFX: Nắng chiều; bụi vàng",
            "SHOT SH01:",
            "TYPE: medium",
            "VFX: hiệu ứng một; hiệu ứng hai",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(len(doc.scenes[0].vfx_cues), 2)
        self.assertEqual(doc.scenes[0].shots[0].vfx,
                         ["hiệu ứng một", "hiệu ứng hai"])


class TestShotContextTermination(unittest.TestCase):
    def test_transition_after_shot_content_attaches_to_scene(self):
        # SPEC §2.5 TRANSITION exception: a TRANSITION line written
        # after shot content still means the scene transition.
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "SHOT SH01:",
            "TYPE: medium",
            "DIALOGUE: Khoa: Chào.",
            "TRANSITION: DISSOLVE",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.scenes[0].transition, "DISSOLVE")
        # The dialogue inside the shot stays shot-scoped.
        self.assertEqual(doc.spoken_lines[0].shot_id, "SH01")
        self.assertEqual(doc.scenes[0].shots[0].spoken_line_ids, ["L001"])

    def test_scene_only_keys_in_shot_context_are_unsupported(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "LOCATION: NOI_X",
            "NAME: Nơi X",
            "SCENE 1: Mở đầu",
            "LOCATION: NOI_X",
            "SHOT SH01:",
            "TYPE: medium",
            "LOCATION: Nơi khác",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertTrue(doc.is_valid, _codes(doc))
        # The shot-context LOCATION did not overwrite the scene field.
        self.assertEqual(doc.scenes[0].location_ref, "NOI_X")
        self.assertEqual(doc.scenes[0].location_text, "")
        keys = [(u.key, u.value, u.context) for u in doc.unsupported_fields]
        self.assertIn(("LOCATION", "Nơi khác", "shot:SH01"), keys)


class TestExampleEqualsFixtureAndTemplate(unittest.TestCase):
    def _normalized(self, obj):
        if isinstance(obj, dict):
            return {k: (0 if k == "line" else self._normalized(v))
                    for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._normalized(v) for v in obj]
        return obj

    def test_example_equals_fixture_modulo_lines_and_hash(self):
        fixture_doc = parse_studio_script_v1(_read(FIXTURE))
        example_doc = parse_studio_script_v1(_read(EXAMPLE))
        self.assertTrue(fixture_doc.is_valid, _codes(fixture_doc))
        self.assertTrue(example_doc.is_valid, _codes(example_doc))
        # The 7-line "#" preamble shifts every line number by +7.
        self.assertEqual(
            example_doc.scenes[0].line, fixture_doc.scenes[0].line + 7)
        self.assertNotEqual(fixture_doc.snapshot_hash,
                            example_doc.snapshot_hash)
        fixture_data = fixture_doc.to_dict()
        example_data = example_doc.to_dict()
        fixture_data.pop("snapshot_hash")
        example_data.pop("snapshot_hash")
        self.assertEqual(self._normalized(fixture_data),
                         self._normalized(example_data))

    def test_template_parses_valid(self):
        doc = parse_studio_script_v1(_read(TEMPLATE))
        self.assertTrue(doc.is_valid, _codes(doc))
        self.assertEqual(doc.validation_errors, [])
        self.assertEqual(doc.warnings, [])
        self.assertEqual(doc.unsupported_fields, [])
        self.assertEqual(len(doc.scenes), 1)
        self.assertEqual(len(doc.characters), 2)
        self.assertEqual(len(doc.locations), 1)
        self.assertEqual(len(doc.props), 1)


class TestAdditionalV1ECodes(unittest.TestCase):
    def test_duplicate_location_is_v1e002(self):
        text = "\n".join([
            "PROJECT: Test",
            "LOCATION: NOI_X",
            "LOCATION: NOI_X",
            "SCENE 1: Mở đầu",
            "NARRATION: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E002")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 3)

    def test_duplicate_shot_id_is_v1e004_error(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "SHOT SH01:",
            "TYPE: medium",
            "SHOT SH01:",
            "TYPE: close_up",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertFalse(doc.is_valid)
        issues = _error_at(doc, "V1E004")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 6)
        # The same id in a DIFFERENT scene is allowed.
        text2 = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Một",
            "SHOT SH01:",
            "TYPE: medium",
            "DIALOGUE: Khoa: Chào.",
            "SCENE 2: Hai",
            "SHOT SH01:",
            "TYPE: medium",
            "DIALOGUE: Khoa: Chào lại.",
        ])
        doc2 = parse_studio_script_v1(text2)
        self.assertTrue(doc2.is_valid, _codes(doc2))

    def test_duplicate_prop_name_and_identity_id_are_v1e001(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "PROP: Chiếc Ô",
            "PROP: Chiếc Ô",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertIn("V1E001", _codes(doc))
        text2 = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "IDENTITY_ID: id-chung",
            "CHARACTER: Lan",
            "IDENTITY_ID: id-chung",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc2 = parse_studio_script_v1(text2)
        self.assertIn("V1E001", _codes(doc2))

    def test_unknown_prop_scenes_entry_is_v1e018(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "PROP: Chiếc Ô",
            "SCENES: 1, 9",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E018")
        self.assertEqual(len(issues), 1)

    def test_expression_unknown_prefix_is_v1e018(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "EXPRESSION: Người Lạ: vui vẻ",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertIn("V1E018", _codes(doc))
        text2 = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "SHOT SH01:",
            "TYPE: medium",
            "EXPRESSION: Người Lạ: vui vẻ",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc2 = parse_studio_script_v1(text2)
        self.assertIn("V1E018", _codes(doc2))
        # Bare expressions (no prefix) and known prefixes are fine.
        text3 = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "EXPRESSION: vui vẻ",
            "EXPRESSION: Khoa: ngạc nhiên",
            "DIALOGUE: Khoa: Chào.",
        ])
        doc3 = parse_studio_script_v1(text3)
        self.assertTrue(doc3.is_valid, _codes(doc3))

    def test_malformed_line_id_is_v1e019(self):
        for label, spoken in [
                ("bracket-before-colon", "NARRATION [LX]: Một."),
                ("bracket-missing", "NARRATION [L001: Một."),
                ("bracket-after-colon", "NARRATION: [LX] Một.")]:
            with self.subTest(case=label):
                text = "\n".join([
                    "PROJECT: Test",
                    "CHARACTER: Khoa",
                    "SCENE 1: Mở đầu",
                    spoken,
                    "NARRATION: Hai.",
                ])
                doc = parse_studio_script_v1(text)
                self.assertIn("V1E019", _codes(doc))
                # The malformed line produced no spoken line.
                self.assertEqual(len(doc.spoken_lines), 1)

    def test_malformed_headers_and_empty_block_names_are_v1e019(self):
        for label, header in [
                ("empty-character", "CHARACTER:"),
                ("empty-location", "LOCATION:"),
                ("empty-prop", "PROP:"),
                ("empty-shot", None),  # handled below, needs a scene
                ("scene-no-number", "SCENE: Không số"),
                ("scene-bad-number", "SCENE X: Không số")]:
            with self.subTest(case=label):
                if label == "empty-shot":
                    text = "\n".join([
                        "PROJECT: Test",
                        "SCENE 1: Mở đầu",
                        "SHOT:",
                        "NARRATION: Chào.",
                    ])
                else:
                    text = "\n".join([
                        "PROJECT: Test", header,
                        "SCENE 1: Mở đầu", "NARRATION: Chào.",
                    ])
                doc = parse_studio_script_v1(text)
                self.assertIn("V1E019", _codes(doc))

    def test_shot_outside_scene_is_v1e019(self):
        text = "\n".join([
            "PROJECT: Test",
            "SHOT SH01:",
            "TYPE: medium",
            "SCENE 1: Mở đầu",
            "NARRATION: Chào.",
        ])
        doc = parse_studio_script_v1(text)
        issues = _error_at(doc, "V1E019")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 2)

    def test_invalid_dialogue_and_empty_narration_are_v1e019(self):
        text = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "DIALOGUE: Khoa",
        ])
        doc = parse_studio_script_v1(text)
        self.assertIn("V1E019", _codes(doc))
        text2 = "\n".join([
            "PROJECT: Test",
            "CHARACTER: Khoa",
            "SCENE 1: Mở đầu",
            "NARRATION:",
        ])
        doc2 = parse_studio_script_v1(text2)
        self.assertIn("V1E019", _codes(doc2))

    def test_scene_without_spoken_lines_is_v1e023_only(self):
        text = "\n".join([
            "PROJECT: Test",
            "SCENE 1: Mở đầu",
            "VISUAL: Chỉ có hình ảnh, không có lời nói.",
        ])
        doc = parse_studio_script_v1(text)
        self.assertIn("V1E023", _codes(doc))
        self.assertNotIn("V1E020", _codes(doc))

    def test_enum_sites_are_v1e007(self):
        cases = [
            ("aspect", ["ASPECT_RATIO: 4:3"]),
            ("meme-policy", ["MEME_POLICY: SOMETIMES"]),
            ("transition", ["SCENE 1: Mở đầu", "TRANSITION: BOGUS",
                            "NARRATION: Chào."]),
            ("camera-movement", ["SCENE 1: Mở đầu", "CAMERA_MOVEMENT: BOGUS",
                                 "NARRATION: Chào."]),
            ("sfx-priority", ["SCENE 1: Mở đầu", "NARRATION: Chào.",
                              "SFX: Chuông | PRIORITY: BOGUS"]),
            ("ambience-mode", ["SCENE 1: Mở đầu", "NARRATION: Chào.",
                               "AMBIENCE: Sông | MODE: BOGUS"]),
            ("bgm-intensity", ["SCENE 1: Mở đầu", "NARRATION: Chào.",
                               "BGM: Đàn | INTENSITY: BOGUS"]),
            ("resolution", ["SCENE 1: Mở đầu", "NARRATION: Chào.",
                            "OUTPUT:", "RESOLUTION: 800x600"]),
            ("fps", ["SCENE 1: Mở đầu", "NARRATION: Chào.",
                     "OUTPUT:", "FPS: 60"]),
            ("format", ["SCENE 1: Mở đầu", "NARRATION: Chào.",
                        "OUTPUT:", "FORMAT: AVI"]),
        ]
        for label, lines in cases:
            with self.subTest(case=label):
                if label in ("aspect", "meme-policy"):
                    text = "\n".join(
                        ["PROJECT: Test"] + lines +
                        ["SCENE 1: Mở đầu", "NARRATION: Chào."])
                else:
                    text = "\n".join(["PROJECT: Test"] + lines)
                doc = parse_studio_script_v1(text)
                self.assertIn("V1E007", _codes(doc), _codes(doc))

    def test_number_boolean_sites(self):
        cases = [
            ("meme-max-nonnumeric", ["MEME_MAX_PER_MINUTE: nhiều"], "V1E008"),
            ("meme-max-negative", ["MEME_MAX_PER_MINUTE: -1"], "V1E008"),
            ("gain-nonnumeric", ["GLOBAL_AUDIO:", "SFX_GAIN_DB: to"], "V1E008"),
            ("min-score-nonnumeric", ["QA:", "MIN_SCORE: cao"], "V1E008"),
            ("max-hard-fails", ["QA:", "MAX_HARD_FAILS: -2"], "V1E008"),
            ("min-score-range", ["QA:", "MIN_SCORE: 11"], "V1E010"),
            ("min-score-negative", ["QA:", "MIN_SCORE: -1"], "V1E010"),
            ("bool-yes", ["QA:", "REQUIRE_TECHNICAL: yes"], "V1E011"),
        ]
        for label, block_lines, expected in cases:
            with self.subTest(case=label):
                if label.startswith("meme-max"):
                    text = "\n".join(
                        ["PROJECT: Test"] + block_lines +
                        ["SCENE 1: Mở đầu", "NARRATION: Chào."])
                else:
                    text = "\n".join([
                        "PROJECT: Test",
                        "SCENE 1: Mở đầu", "NARRATION: Chào.",
                    ] + block_lines)
                doc = parse_studio_script_v1(text)
                self.assertIn(expected, _codes(doc), _codes(doc))

    def test_every_emitted_code_is_a_v1e_code(self):
        # Global guard: the parser emits ONLY SPEC §8.2 codes, and
        # never V1E022 at parse time.
        docs = [
            "PROJECT: A\nPROJECT: B\n",
            "PROJECT: T\nCHARACTER: Khoa\nSCENE 1: X\nSHOT SH01:\n"
            "TYPE: BOGUS\nSUBJECT: Ai đó\nDIALOGUE: Người Lạ: Hi.\n"
            "SFX: NONE | TRIGGER: L001\nSFX: Chuông\n",
            "PROJECT: T\nCHARACTER: Khoa\nHEAD_RATIO: 0.42\n"
            "SCENE 1: X\nDURATION: 9s\nDIALOGUE: Khoa: SFX: chuông.\n",
        ]
        pattern = re.compile(r"^V1E0\d\d$")
        for text in docs:
            doc = parse_studio_script_v1(text)
            for issue in doc.validation_errors + doc.warnings:
                self.assertRegex(issue.code, pattern)
                self.assertNotEqual(issue.code, "V1E022")


class TestJsonSchemaValidation(unittest.TestCase):
    def test_issue_code_pattern_in_schema(self):
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        pattern = schema["$defs"]["validationIssue"]["properties"]["code"]["pattern"]
        self.assertEqual(pattern, r"^V1E0\d\d$")
        self.assertRegex("V1E001", pattern)
        self.assertRegex("V1E024", pattern)
        self.assertNotRegex("INVALID_SHOT_TYPE", pattern)
        # meme_note is a required scene field in the schema.
        scene_def = schema["$defs"]["scene"]
        self.assertIn("meme_note", scene_def["properties"])
        self.assertIn("meme_note", scene_def["required"])
        # Unspecified headers allow null; no separate "style" field.
        meta_def = schema["$defs"]["meta"]
        self.assertNotIn("style", meta_def["properties"])
        for field in ("project", "genre", "visual_style", "tone"):
            types = {t.get("type") for t in meta_def["properties"][field]["anyOf"]}
            self.assertEqual(types, {"string", "null"})

    @unittest.skipIf(jsonschema is None, "jsonschema package not installed")
    def test_valid_documents_validate_against_schema(self):
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        jsonschema.validators.validator_for(schema).check_schema(schema)
        documents = [
            ("fixture", _read(FIXTURE)),
            ("synthetic", SYNTHETIC_FULL),
            ("template", _read(TEMPLATE)),
            ("example", _read(EXAMPLE)),
            ("minimal", "# STUDIO SCRIPT V1\nSCENE 1: X\nNARRATION: Hi.\n"),
        ]
        for label, text in documents:
            with self.subTest(document=label):
                doc = parse_studio_script_v1(text)
                self.assertTrue(doc.is_valid, _codes(doc))
                jsonschema.validate(doc.to_dict(), schema)


if __name__ == "__main__":
    unittest.main()
