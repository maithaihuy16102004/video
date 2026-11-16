"""R17 item 2 (night + identity): D15/D16/D5/D12/D13/D9.

D15: the rain puddle draws only when the shot is rainy.
D16: Mediterranean house windows use the lit-window rule.
D5: night clouds lose the flat-bottomed saucer underside.
D12: trait-gated kitchen dressing; no settlement skyline in forests.
D13: template heights + BODY_TYPE stature reach the render.
D9: straw hat type + sturdy broad-shoulder taper.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from ai_clip_studio.animation import character_art
from ai_clip_studio.animation.character_art import (
    TEMPLATES, draw_character_v4, make_character)
from ai_clip_studio.environment_v2 import (
    _draw_cloud_blob, build_environment)
from ai_clip_studio import product_renderer as pr
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.trait_derivation import (
    HATS, derive_render_traits)

AGENT = Path(__file__).resolve().parent.parent.parent
JOB = AGENT / "jobs" / "req_b0fe5da148b7"


def _delivered_shots():
    text = (AGENT / "examples" / "loop_test_02_brass_key.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    timeline = json.loads((JOB / "timeline.json").read_text(
        encoding="utf-8"))
    shots = timeline["shots"]
    starts, _t = {}, 0.0
    for s in shots:
        starts[id(s)] = _t
        _t += float(s["duration"])
    spans = {}
    for s in shots:
        sid = s.get("directive_shot_id")
        if sid:
            st, en = starts[id(s)], starts[id(s)] + float(s["duration"])
            spans[sid] = [min(spans[sid][0], st), max(spans[sid][1], en)] \
                if sid in spans else [st, en]
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    for i, sh in enumerate(shots):
        sh["index"] = i
        sh["start_sec"] = starts[id(sh)]
    return package, shots


class TestPuddleRainGate(unittest.TestCase):
    def test_no_puddle_on_dry_shot(self):
        package, shots = _delivered_shots()
        calls = []
        real = pr._draw_puddle

        def spy(draw, x, ground_y):
            calls.append((x, ground_y))
            return real(draw, x, ground_y)

        with patch.object(pr, "_draw_puddle", spy):
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                pr._render_shot({"shot": shots[0], "package": package,
                                 "out_dir": tmp, "still_only": True})
        self.assertEqual(calls, [])


class TestMediterraneanWindows(unittest.TestCase):
    TRAITS = {"features": ["Đảo Địa Trung Hải.", "Nhà vôi trắng.",
                           "Mái vòm.", "Cây ô liu.", "Bờ biển."]}

    def test_night_windows_lit(self):
        pkg = build_environment(self.TRAITS, time_of_day="night")
        wins = [e for e in pkg["elements"]
                if e["id"].startswith("house") and e["id"].endswith("_win")]
        self.assertTrue(wins)
        for e in wins:
            self.assertEqual(tuple(e["color"]), (255, 200, 90), e["id"])

    def test_day_windows_plain_glass(self):
        pkg = build_environment(self.TRAITS, time_of_day="day")
        wins = [e for e in pkg["elements"]
                if e["id"].startswith("house") and e["id"].endswith("_win")]
        self.assertTrue(wins)
        for e in wins:
            self.assertEqual(tuple(e["color"]), (52, 66, 88), e["id"])


class TestNightClouds(unittest.TestCase):
    def _underside_ratio(self, colour):
        img = Image.new("RGB", (400, 300), (0, 0, 0))
        d = ImageDraw.Draw(img)
        _draw_cloud_blob(d, 200, 150, 100, 60, colour, None)
        px = img.load()
        under = px[200, 180]  # trapezoid centre (y + 0.5ry)
        mean_c = sum(colour) / 3.0
        mean_u = sum(under) / 3.0
        return mean_u / mean_c

    def test_dark_cloud_underside_blends_into_body(self):
        self.assertGreater(self._underside_ratio((40, 38, 45)), 0.85)

    def test_day_cloud_keeps_shaded_underside(self):
        ratio = self._underside_ratio((240, 240, 245))
        self.assertAlmostEqual(ratio, 0.72, delta=0.03)

    def test_night_clouds_puff_up_day_clouds_unchanged(self):
        traits = {"features": ["Đảo Địa Trung Hải.", "Nhà vôi trắng.",
                               "Mái vòm.", "Cây ô liu.", "Bờ biển."]}
        night = build_environment(traits, time_of_day="night")
        day = build_environment(traits, time_of_day="day")
        night_aspects = [e["size"][0] / e["size"][1]
                         for e in night["elements"]
                         if e["id"].startswith("sky_cloud_")]
        day_aspects = [e["size"][0] / e["size"][1]
                       for e in day["elements"]
                       if e["id"].startswith("sky_cloud_")]
        self.assertEqual(len(night_aspects), 4)
        for a in night_aspects:
            self.assertLess(a, 3.0)
        for a in day_aspects:
            self.assertGreater(a, 2.5)


class TestKitchenAndForest(unittest.TestCase):
    KITCHEN = {
        "id": "LOC_BA_TU_KITCHEN", "name": "Gian bếp nhà Bà Tư",
        "features": ["Gian bếp trong nhà.", "Bàn gỗ và ghế gỗ thấp.",
                     "Bếp củi góc phòng.", "Nồi niêu treo trên tường.",
                     "Cửa sổ nhìn ra sân."],
        "foreground": ["Mép bàn gỗ.", "Ấm nước trên bếp."],
        "midground": ["An và Bà Tư trò chuyện."],
        "background": ["Tường trong nhà.", "Kệ gỗ với đồ dùng cũ."],
        "lighting": "Warm lamp light", "weather": "Calm"}
    STUDY = {
        "id": "LOC_STUDY", "name": "Phòng làm việc",
        "features": ["Phòng làm việc trong nhà.", "Bàn viết gỗ.",
                     "Tủ hồ sơ.", "Cửa sổ nhìn ra sân."],
        "foreground": [], "midground": [], "background": [],
        "lighting": "Lamp light", "weather": "Calm"}

    def test_kitchen_gets_stove_table_pots_no_desk(self):
        pkg = build_environment(self.KITCHEN, time_of_day="evening")
        self.assertEqual(pkg["archetype"], "INTERIOR_GENERIC")
        self.assertEqual(pkg["validation"], [])
        ids = {e["id"] for e in pkg["elements"]}
        for want in ("kitchen_table_top", "kitchen_stool_0",
                     "kitchen_stove", "kitchen_kettle",
                     "hanging_pot_0", "hanging_pot_2"):
            self.assertIn(want, ids)
        self.assertFalse([i for i in ids if i.startswith("desk")])
        self.assertFalse([i for i in ids if i.startswith("chair")])

    def test_study_keeps_writing_desk_no_stove(self):
        pkg = build_environment(self.STUDY, time_of_day="day")
        self.assertEqual(pkg["archetype"], "INTERIOR_GENERIC")
        ids = {e["id"] for e in pkg["elements"]}
        self.assertIn("desk_top", ids)
        self.assertFalse([i for i in ids if i.startswith("kitchen")])
        self.assertFalse([i for i in ids if i.startswith("hanging_pot")])

    def test_forest_has_no_skyline_and_denser_trees(self):
        pkg = build_environment(
            {"features": ["Khu rừng.", "Cây cổ thụ.", "Tán cây.",
                          "Bụi rậm."]}, time_of_day="day")
        self.assertEqual(pkg["archetype"], "FOREST")
        ids = [e["id"] for e in pkg["elements"]]
        self.assertEqual([i for i in ids if i.startswith("skyline")], [])
        self.assertTrue(any(i.startswith("tree13") for i in ids))
        self.assertTrue(any(i.startswith("under3") for i in ids))

    def test_street_keeps_skyline(self):
        pkg = build_environment(
            {"features": ["Kiến trúc đô thị đầu thế kỷ XX.",
                          "Nhà nhiều tầng, mặt tiền trát vữa.",
                          "Đường lát đá."], "period": "1914"},
            time_of_day="day")
        ids = [e["id"] for e in pkg["elements"]]
        self.assertTrue(any(i.startswith("skyline") for i in ids))


class TestStature(unittest.TestCase):
    def _traits(self, body_type, age, gender="Female"):
        fields = {"BODY_TYPE": body_type, "AGE": str(age),
                  "GENDER": gender}
        return derive_render_traits(
            "Test", "Supporting", "", "", [], "",
            fields=fields, gender=gender)

    def test_small_elder_is_shorter(self):
        t = self._traits("Small, bent back", 72)
        self.assertEqual(t["template"], "elderly")
        self.assertEqual(t["stature"], 0.85)

    def test_small_child_does_not_double_count(self):
        t = derive_render_traits(
            "Bé Tí", "Supporting", "", "", [], "",
            fields={"BODY_TYPE": "Small, energetic", "AGE": "8",
                    "GENDER": "Male"}, gender="Male")
        self.assertEqual(t["template"], "child")
        self.assertEqual(t["stature"], 1.0)

    def test_tall_body(self):
        t = self._traits("Tall, broad", 30, gender="Male")
        self.assertEqual(t["stature"], 1.08)

    def test_hair_word_is_not_stature(self):
        t = derive_render_traits(
            "Test", "Supporting", "", "", [], "",
            fields={"BODY_TYPE": "Average", "HAIR": "Short black hair",
                    "AGE": "45", "GENDER": "Male"}, gender="Male")
        self.assertEqual(t["stature"], 1.0)

    def test_default_stature(self):
        t = self._traits("Average build", 30, gender="Male")
        self.assertEqual(t["stature"], 1.0)


class TestRenderedHeights(unittest.TestCase):
    def _height(self, template, body_variant, stature):
        char = {"name": "test_height_probe", "template": template,
                "body_variant": body_variant, "stature": stature}
        return pr.map_character(char, 0, height_px=783)

    def test_template_and_stature_compose(self):
        self.assertEqual(self._height("male", "standard", 1.0).H, 783)
        self.assertEqual(self._height("female", "slim", 1.0).H, 755)
        self.assertEqual(self._height("elderly", "standard", 0.85).H, 618)
        self.assertEqual(self._height("child", "standard", 1.0).H, 559)

    def test_head_ratio_locked_at_all_heights(self):
        for template, body, stature in (
                ("male", "standard", 1.0), ("female", "slim", 1.0),
                ("elderly", "standard", 0.85), ("child", "standard", 1.0)):
            ch = self._height(template, body, stature)
            self.assertAlmostEqual(ch.head_r / ch.H, 0.17, places=3)


class TestStrawHat(unittest.TestCase):
    def test_straw_hat_in_registry(self):
        self.assertIn("straw", HATS)

    def test_derivation_from_costume(self):
        t = derive_render_traits(
            "Chú Sáu", "Supporting", "", "Mũ rơm rộng vành.", [], "",
            fields={"GENDER": "Male", "AGE": "45"}, gender="Male")
        self.assertEqual(t["hat"], "straw")
        self.assertEqual(t["hat_color"], "#D2B48C")

    def test_cap_and_bowler_unchanged(self):
        t = derive_render_traits(
            "An", "Protagonist", "", "Mũ lưỡi trai màu đỏ.", [], "",
            fields={"GENDER": "Female", "AGE": "19"}, gender="Female")
        self.assertEqual(t["hat"], "cap")
        t = derive_render_traits(
            "Lustig", "Supporting", "", "Mũ nồi đen.", [], "",
            fields={"GENDER": "Male", "AGE": "40"}, gender="Male")
        self.assertEqual(t["hat"], "bowler")

    def _draw(self, **kw):
        char = make_character(template="male", height=560, **kw)
        img = Image.new("RGB", (1200, 1200), (255, 255, 255))
        d = ImageDraw.Draw(img, "RGBA")
        J = draw_character_v4(d, char, view="front")
        return img, J, char

    def test_straw_brim_wider_than_head(self):
        img, J, char = self._draw(hat="straw", hat_color="#D2B48C")
        px = img.load()
        straw = [(x, y) for y in range(1200) for x in range(1200)
                 if abs(px[x, y][0] - 210) < 25
                 and abs(px[x, y][1] - 180) < 25
                 and abs(px[x, y][2] - 140) < 25]
        self.assertTrue(straw)
        xs = [x for x, _ in straw]
        brim_w = max(xs) - min(xs)
        self.assertGreater(brim_w / (2 * char.head_r), 1.4)

    def test_sturdy_torso_inverts_taper(self):
        def taper(body_variant):
            char = make_character(template="male", height=560,
                                  body_variant=body_variant,
                                  suit="#C00000")
            img = Image.new("RGB", (1200, 1200), (255, 255, 255))
            d = ImageDraw.Draw(img, "RGBA")
            J = draw_character_v4(d, char, view="front")
            px = img.load()
            sy = int(J["shoulder"][1])
            hy = int(J["hip"][1])
            def row_width(y):
                xs = [x for x in range(1200)
                      if abs(px[x, y][0] - 192) < 25
                      and px[x, y][1] < 60 and px[x, y][2] < 60]
                return (max(xs) - min(xs)) if xs else 0
            return row_width(sy + 6), row_width(hy - 6)
        top_s, bot_s = taper("standard")
        top_u, bot_u = taper("sturdy")
        self.assertLess(top_s, bot_s)  # reference taper kept
        self.assertGreater(top_u, bot_u)  # stocky: broad shoulders
        self.assertGreater(top_u, top_s)


if __name__ == "__main__":
    unittest.main()
