"""Character distinctiveness (round-3 system 1): costume colours
reach the renderer from bullet-form COSTUME lists, the first colour
in the text wins, uncoloured cast members get distinct deterministic
palette colours, and declared children render shorter."""
import unittest

from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.trait_derivation import (
    DEFAULT_JACKET_COLOR, DISTINCT_JACKET_PALETTE,
    _jacket_color_from_text, resolve_cast_jacket_colors)

LOOP = "examples/loop_test_01_fire_stone.studio.md"
ZEUS = "examples/zeus_ep01_fall_of_cronus.studio.md"
EP1 = "examples/hitler_ep01_munich_1914.studio.md"


def _cast(path):
    doc = parse_studio_script_v1(open(path, encoding="utf-8").read())
    return adapt_document(doc)["characters"]


class TestJacketColorScan(unittest.TestCase):
    def test_first_colour_in_text_wins(self):
        self.assertEqual(
            _jacket_color_from_text(
                "Áo màu đỏ gạch. Khăn màu vàng buộc quanh cổ. "
                "Quần dài màu nâu."),
            "#a84332")

    def test_phrase_beats_single_word(self):
        self.assertEqual(_jacket_color_from_text("áo đỏ gạch"), "#a84332")
        self.assertEqual(_jacket_color_from_text("áo màu be"), "#c9b18c")
        self.assertEqual(_jacket_color_from_text("áo xanh lá"), "#2e7d4f")

    def test_word_boundaries_no_substring_match(self):
        # Bare "be" must not match "bé"/"bên"; "đỏ" must not match
        # inside unrelated words.
        self.assertEqual(
            _jacket_color_from_text("Bé Nam đứng bên cạnh bệ đá."),
            DEFAULT_JACKET_COLOR)

    def test_new_compound_words(self):
        self.assertEqual(_jacket_color_from_text("áo màu xám tro"),
                         "#6b7280")
        self.assertEqual(_jacket_color_from_text("mũ màu cam"), "#d97a2b")
        self.assertEqual(_jacket_color_from_text("áo tím"), "#7a4a8c")

    def test_no_colour_word_is_default(self):
        self.assertEqual(
            _jacket_color_from_text("Quân phục Bavaria năm 1914."),
            DEFAULT_JACKET_COLOR)
        self.assertEqual(_jacket_color_from_text(""), DEFAULT_JACKET_COLOR)


class TestCastPalette(unittest.TestCase):
    def test_script_colours_kept_verbatim_on_collision(self):
        out = resolve_cast_jacket_colors(
            [("a", "#f3f0e8"), ("b", "#f3f0e8")])
        self.assertEqual(out, {"a": "#f3f0e8", "b": "#f3f0e8"})

    def test_defaults_get_distinct_slots(self):
        out = resolve_cast_jacket_colors(
            [(f"c{i}", DEFAULT_JACKET_COLOR) for i in range(5)])
        self.assertEqual(len(set(out.values())), 5)
        self.assertEqual(out["c0"], DEFAULT_JACKET_COLOR)
        self.assertEqual(out["c1"], DISTINCT_JACKET_PALETTE[1])

    def test_palette_skips_script_colours(self):
        out = resolve_cast_jacket_colors(
            [("a", "#b03a2e"),
             ("b", DEFAULT_JACKET_COLOR),
             ("c", DEFAULT_JACKET_COLOR)])
        self.assertEqual(out["a"], "#b03a2e")
        self.assertEqual(out["b"], DEFAULT_JACKET_COLOR)
        # Slot 1 (#b03a2e) is taken by the script colour: skipped.
        self.assertEqual(out["c"], DISTINCT_JACKET_PALETTE[2])

    def test_deterministic_and_pure(self):
        colors = [(f"c{i}", DEFAULT_JACKET_COLOR) for i in range(14)]
        first = resolve_cast_jacket_colors(colors)
        second = resolve_cast_jacket_colors(colors)
        self.assertEqual(first, second)
        self.assertEqual(len(set(first.values())), 14)
        self.assertTrue(all(c == DEFAULT_JACKET_COLOR
                            for _, c in colors))

    def test_palette_covers_largest_cast(self):
        self.assertGreaterEqual(len(DISTINCT_JACKET_PALETTE), 14)


class TestCostumeDataPath(unittest.TestCase):
    def test_loop01_script_colours_reach_package(self):
        cast = {c["name"]: c for c in _cast(LOOP)}
        self.assertEqual(cast["Linh"]["jacket_color"], "#a84332")
        self.assertEqual(cast["Ông Ba"]["jacket_color"], "#6b7280")
        self.assertEqual(cast["Bé Nam"]["jacket_color"], "#2e7d4f")
        for name in ("Linh", "Ông Ba", "Bé Nam"):
            self.assertNotEqual(cast[name]["costume_text"], "")
            self.assertEqual(
                cast[name]["render_traits"]["jacket_color"],
                cast[name]["jacket_color"])

    def test_child_scale_from_age(self):
        cast = {c["name"]: c for c in _cast(LOOP)}
        self.assertEqual(cast["Bé Nam"]["scale_ratio"], 0.75)
        self.assertEqual(cast["Bé Nam"]["height_px"], 405)
        self.assertIsNone(cast["Linh"]["scale_ratio"])
        self.assertIsNone(cast["Ông Ba"]["scale_ratio"])

    def test_ep1_hitler_brown_soldier_default(self):
        cast = {c["name"]: c for c in _cast(EP1)}
        self.assertEqual(cast["Adolf Hitler"]["jacket_color"], "#7a4a2b")
        self.assertEqual(cast["Người lính Bavaria"]["jacket_color"],
                         DEFAULT_JACKET_COLOR)

    def test_zeus_cast_mostly_distinct(self):
        cast = _cast(ZEUS)
        colors = [c["jacket_color"] for c in cast]
        self.assertEqual(len(cast), 14)
        # Only the script-named white collision (Zeus/Rhea) remains.
        self.assertEqual(len(set(colors)), 13)
        self.assertEqual(colors.count("#f3f0e8"), 2)
        cronus = [c for c in cast if c["name"] == "Cronus"][0]
        self.assertEqual(cronus["scale_ratio"], 1.8)


if __name__ == "__main__":
    unittest.main()
