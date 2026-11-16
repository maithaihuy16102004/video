"""R18-2 (R17-D2): no implicit child scale. Since R17-D13 the
template ratio (child 400/560) reaches the render through
map_character AND char_scales, so the adapter's implicit 0.75
for AGE < 14 double-counted: children rendered at
783 x 0.75 x 400/560 = 419 instead of the designed 559.
Child smallness is the template ratio's job alone; an explicit
scale_ratio trait still composes on top of it.
"""
import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio.product_flow import _design_scale_ratio
from ai_clip_studio.product_renderer import CHAR_H, map_character
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
import ai_clip_studio.product_renderer as pr

from ai_clip_studio.tests.test_cue_coverage_round18 import (
    _delivered_shot)


class TestChildScale(unittest.TestCase):
    def test_no_implicit_scale_for_declared_child(self):
        text = (Path(__file__).resolve().parent.parent.parent
                / "examples" / "loop_test_02_brass_key.studio.md"
                ).read_text(encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(text))
        be_ti = [c for c in package["characters"]
                 if c["name"] == "Bé Tí"][0]
        self.assertIsNone(be_ti.get("scale_ratio"))

    def test_design_heights_match_template_ratios(self):
        text = (Path(__file__).resolve().parent.parent.parent
                / "examples" / "loop_test_02_brass_key.studio.md"
                ).read_text(encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(text))
        expect = {"An": 755, "Bà Tư": 618, "Bé Tí": 559,
                  "Chú Sáu": 783}
        for c in package["characters"]:
            ratio = _design_scale_ratio(c)
            ch = map_character(c, 0,
                               height_px=int(round(CHAR_H * ratio)))
            self.assertEqual(int(ch.H), expect[c["name"]], c["name"])
            self.assertAlmostEqual(ch.head_r * 2 / ch.H, 0.34,
                                   places=2)

    def test_explicit_scale_still_composes(self):
        # An explicit 0.75 trait composes with the template ratio
        # (the re-pinned product_flow pin); the adapter change
        # only removed the IMPLICIT default.
        ch = map_character({"name": "Kid", "template": "child"},
                           0, height_px=int(round(CHAR_H * 0.75)))
        self.assertEqual(int(ch.H), 419)
        ch2 = map_character({"name": "Titan", "template": "male"},
                            0, height_px=int(round(CHAR_H * 1.8)))
        self.assertEqual(int(ch2.H), 1409)

    def test_rendered_child_height_is_559(self):
        # The render path (char_scales x perspective x template)
        # must build Be Ti at 559, not 419: spy map_character
        # during a real shot render.
        package, shot = _delivered_shot(17)
        seen = {}
        orig = pr.map_character

        def spy(char, index, **kw):
            ch = orig(char, index, **kw)
            seen[char.get("name")] = (kw.get("height_px"), int(ch.H))
            return ch

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(pr, "map_character", spy):
                pr._render_shot({"shot": shot, "package": package,
                                 "out_dir": tmp, "still_only": True})
        self.assertIn("Bé Tí", seen)
        height_px, h = seen["Bé Tí"]
        # The template ratio applies exactly ONCE: H is 400/560 of
        # the perspective height. (Shot #17 stages Be Ti nearer
        # than the default depth, so the absolute H is 636, not
        # 559 -- the ratio is the invariant.) The double-counted
        # 0.75 x 400/560 = 0.535 would fail the > 0.65 bound.
        self.assertEqual(h, round(height_px * 400 / 560))
        self.assertGreater(h / height_px, 0.65)


if __name__ == "__main__":
    unittest.main()
