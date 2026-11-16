"""R18 D12: kitchen readability -- the stove trades places with
the cabinet (in-frame for subject-framed shots), the lamp moves
clear of the stove sightline, and hanging pots draw with rim +
handle + highlight instead of a flat dark disc.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

from ai_clip_studio.environment_v2 import (
    _draw_hanging_pot, build_environment)
from ai_clip_studio.product_renderer import _render_shot
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.action_compiler import compile_actions
import ai_clip_studio.environment_v2 as ev

from ai_clip_studio.tests.test_cue_coverage_round18 import (
    _delivered_shot)

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


def _by_id(pkg):
    return {e["id"]: e for e in pkg["elements"]}


class TestKitchenLayout(unittest.TestCase):
    def test_stove_cabinet_swap_in_kitchen_only(self):
        els = _by_id(build_environment(KITCHEN, time_of_day="evening"))
        self.assertAlmostEqual(els["kitchen_stove"]["center"][0], -3.9)
        self.assertAlmostEqual(
            els["kitchen_stove_firebox"]["center"][0], -3.9)
        self.assertAlmostEqual(
            els["kitchen_stove_pipe"]["center"][0], -3.9)
        self.assertAlmostEqual(els["kitchen_kettle"]["center"][0], -3.9)
        self.assertAlmostEqual(els["room_cabinet"]["center"][0], -6.2)
        self.assertAlmostEqual(
            els["cabinet_papers"]["center"][0], -6.2)
        study = _by_id(build_environment(STUDY, time_of_day="evening"))
        self.assertNotIn("kitchen_stove", study)
        self.assertAlmostEqual(study["room_cabinet"]["center"][0], -4.6)

    def test_lamp_clears_stove_sightline_in_kitchen_only(self):
        els = _by_id(build_environment(KITCHEN, time_of_day="evening"))
        self.assertAlmostEqual(els["room_lamp_pole"]["center"][0], -0.5)
        self.assertAlmostEqual(
            els["room_lamp_shade"]["center"][0], -0.5)
        study = _by_id(build_environment(STUDY, time_of_day="evening"))
        self.assertAlmostEqual(
            study["room_lamp_pole"]["center"][0], -2.5)

    def test_hanging_pot_draws_structure(self):
        img = Image.new("RGB", (200, 200), (150, 110, 70))
        d = ImageDraw.Draw(img)
        _draw_hanging_pot(d, 100, 110, 40, 40, (45, 45, 50),
                          (27, 27, 30))
        px = img.load()
        # Body: dark iron at the centre.
        self.assertEqual(px[100, 120], (45, 45, 50))
        # Highlight: light pixels in the upper-left belly.
        light = [(x, y) for x in range(60, 100) for y in range(85, 115)
                 if sum(px[x, y]) > 300]
        self.assertGreater(len(light), 20)
        # Handle: dark arc pixels above the body (y < 70).
        handle = [(x, y) for x in range(70, 130) for y in range(40, 70)
                  if sum(px[x, y]) < 150]
        self.assertGreater(len(handle), 5)
        # Rim: lighter arc pixels across the upper belly.
        rim = [(x, y) for x in range(65, 135) for y in range(72, 105)
               if 300 < sum(px[x, y]) < 420]
        self.assertGreater(len(rim), 5)

    def test_stove_projects_into_shot17_frame(self):
        package, shot = _delivered_shot(17)
        orig = ev._draw_box_element
        seen = {}

        def spy(img, draw, el, camera, rig, width, height, *a, **k):
            if el["id"] == "kitchen_stove":
                x, y, sc, vis = camera.project(
                    el["center"], width, height)
                seen["stove"] = (x, y, sc, vis)
            return orig(img, draw, el, camera, rig, width, height,
                        *a, **k)

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(ev, "_draw_box_element", spy):
                _render_shot({"shot": shot, "package": package,
                              "out_dir": tmp, "still_only": True})
        self.assertIn("stove", seen)
        x, y, _sc, vis = seen["stove"]
        self.assertTrue(vis)
        self.assertGreater(x, 0)
        self.assertLess(x, 1920)
        self.assertGreater(y, 0)
        self.assertLess(y, 1080)


if __name__ == "__main__":
    unittest.main()
