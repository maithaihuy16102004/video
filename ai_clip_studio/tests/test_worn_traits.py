"""Round-3 system 3: worn traits (hair/beard/hat/scarf) from script data.

The tester found zero worn traits in the Loop 01 re-render: the script
named tied hair, grey hair, a white beard, an orange hat and a yellow
scarf, but every character rendered hair_style="short", hat="none",
and no beard/scarf at all. The data path dropped the traits AND the
art had no beard / hair-colour / hat-colour / scarf drawing.
"""

import unittest

from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import draw_character_v4
from ai_clip_studio.animation.primitives import standing
from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.trait_derivation import (
    _apron_color_from_segments,
    _beard_from_text,
    _hair_color_from_text,
    _hair_style,
    _hat_from_segments,
    _scarf_color_from_segments,
    derive_render_traits,
)


def _traits(**kw):
    fields = kw.pop("fields", {})
    return derive_render_traits(
        kw.pop("name", "T"), kw.pop("role", ""), kw.pop("appearance", ""),
        kw.pop("costume_text", ""), [], kw.pop("voice_style", ""),
        fields=fields, gender=kw.pop("gender", ""),
        height_px=540)


class TestHairDerivation(unittest.TestCase):
    def test_tied_high(self):
        self.assertEqual(_hair_style("black hair tied high"), "tied")
        self.assertEqual(_hair_style("tóc búi cao"), "tied")
        self.assertEqual(_hair_style("ponytail"), "tied")

    def test_existing_styles_unchanged(self):
        self.assertEqual(_hair_style("tóc dài"), "long")
        self.assertEqual(_hair_style("rẽ ngôi"), "side_part")
        self.assertEqual(_hair_style("tóc chỏm"), "tuft")
        self.assertEqual(_hair_style("short black hair"), "short")
        self.assertEqual(_hair_style("hói"), "none")

    def test_hair_color_scoped_to_hair_field(self):
        self.assertEqual(_hair_color_from_text("Short grey hair"), "#9aa0a6")
        self.assertEqual(_hair_color_from_text("Black hair tied high"), "#222222")
        self.assertEqual(_hair_color_from_text("Tóc bạc"), "#c9ccd1")
        self.assertIsNone(_hair_color_from_text("Short hair"))

    def test_costume_color_never_colors_hair(self):
        # The jacket scan sees "đỏ gạch"; the hair scan sees only the
        # HAIR field, so a red shirt never makes hair red.
        t = _traits(name="L", costume_text="Áo màu đỏ gạch.",
                    fields={"HAIR": "Short black hair"})
        self.assertEqual(t["jacket_color"], "#a84332")
        self.assertEqual(t["hair_color"], "#222222")


class TestBeardDerivation(unittest.TestCase):
    def test_white_beard(self):
        style, color = _beard_from_text("Râu bạc, nếp nhăn hiền hậu")
        self.assertEqual((style, color), ("full", "#c9ccd1"))

    def test_black_beard_no_color_word(self):
        style, color = _beard_from_text("Full beard")
        self.assertEqual(style, "full")
        self.assertIsNone(color)

    def test_no_beard_without_evidence(self):
        self.assertEqual(_beard_from_text("Clean shaven"), ("none", None))
        self.assertEqual(_beard_from_text(""), ("none", None))

    def test_beard_flows_through_traits(self):
        t = _traits(name="B", fields={
            "HAIR": "Short grey hair",
            "FACIAL_FEATURES": "Râu bạc, nếp nhăn hiền hậu"})
        self.assertEqual(t["beard_style"], "full")
        self.assertEqual(t["beard_color"], "#c9ccd1")
        self.assertEqual(t["hair_color"], "#9aa0a6")


class TestHatDerivation(unittest.TestCase):
    def test_orange_hat(self):
        self.assertEqual(
            _hat_from_segments(["Áo màu xanh lá.", "Mũ màu cam."]),
            ("cap", "#d97a2b"))

    def test_bare_hat_word_is_not_enough(self):
        self.assertEqual(_hat_from_segments(["Mũ."]), ("none", None))

    def test_wearing_verb_without_color(self):
        self.assertEqual(
            _hat_from_segments(["Đội mũ ra đồng."]), ("cap", None))

    def test_color_in_another_segment_does_not_leak(self):
        # The colour must share the hat's segment: a red shirt plus a
        # bare hat word yields no hat colour (and no hat at all --
        # the verb is absent too).
        self.assertEqual(
            _hat_from_segments(["Áo màu đỏ.", "Mũ."]), ("none", None))

    def test_bowler_still_wins_from_full_scan(self):
        t = _traits(name="L", role="Bowler hat gentleman",
                    costume_text="Dark suit.")
        self.assertEqual((t["hat"], t["hat_color"]), ("bowler", None))


class TestScarfDerivation(unittest.TestCase):
    def test_yellow_scarf(self):
        self.assertEqual(
            _scarf_color_from_segments(
                ["Áo màu đỏ gạch.", "Khăn màu vàng buộc quanh cổ."]),
            "#d9a441")

    def test_scarf_without_color_draws_nothing(self):
        self.assertIsNone(_scarf_color_from_segments(["Khăn quàng cổ."]))

    def test_color_in_another_segment_does_not_leak(self):
        self.assertIsNone(_scarf_color_from_segments(
            ["Áo màu đỏ.", "Khăn quàng cổ."]))


class TestApronDerivation(unittest.TestCase):
    def test_dark_brown_leather_apron(self):
        self.assertEqual(
            _apron_color_from_segments(["Tạp dề da màu nâu đậm."]),
            "#5a3421")

    def test_apron_without_color_draws_nothing(self):
        self.assertIsNone(_apron_color_from_segments(["Tạp dề da."]))

    def test_color_in_another_segment_does_not_leak(self):
        self.assertIsNone(_apron_color_from_segments(
            ["Áo màu đỏ.", "Tạp dề da."]))


class TestWornTraitArt(unittest.TestCase):
    def _draw(self, view="front", **attrs):
        img = Image.new("RGB", (600, 700), (200, 190, 170))
        ch = Stickman(height=560, name="T", hat="none", moustache=False)
        for k, v in attrs.items():
            setattr(ch, k, v)
        standing(ch, 300, 650)
        draw_character_v4(ImageDraw.Draw(img), ch, expression="neutral",
                          view=view)
        return img, ch

    def _count(self, img, box, pred):
        px = list(img.crop(box).getdata())
        return sum(1 for p in px if pred(p))

    def test_bun_above_head_for_tied(self):
        img, ch = self._draw(hair_style="tied", hair_color="#222222")
        J = ch.joints()
        hx, hy = J["head"]
        r = ch.head_r
        dark = self._count(
            img, (int(hx - 0.3 * r), int(hy - 1.4 * r),
                  int(hx + 0.3 * r), int(hy - 0.9 * r)),
            lambda p: p[0] < 80 and p[1] < 80 and p[2] < 100)
        self.assertGreater(dark, 200)

    def test_no_bun_for_short(self):
        img, ch = self._draw(hair_style="short", hair_color="#222222")
        J = ch.joints()
        hx, hy = J["head"]
        r = ch.head_r
        dark = self._count(
            img, (int(hx - 0.3 * r), int(hy - 1.4 * r),
                  int(hx + 0.3 * r), int(hy - 1.05 * r)),
            lambda p: p[0] < 80 and p[1] < 80 and p[2] < 100)
        self.assertEqual(dark, 0)

    def test_grey_hair_cap(self):
        img, ch = self._draw(hair_style="short", hair_color="#9aa0a6")
        J = ch.joints()
        hx, hy = J["head"]
        r = ch.head_r
        grey = self._count(
            img, (int(hx - 0.5 * r), int(hy - r), int(hx + 0.5 * r),
                  int(hy - 0.75 * r)),
            lambda p: 140 < p[0] < 180 and abs(p[0] - p[1]) < 12)
        self.assertGreater(grey, 200)

    def test_beard_below_mouth(self):
        img, ch = self._draw(beard_style="full", beard_color="#c9ccd1")
        J = ch.joints()
        hx, hy = J["head"]
        r = ch.head_r
        light = self._count(
            img, (int(hx - 0.5 * r), int(hy + 0.55 * r),
                  int(hx + 0.5 * r), int(hy + 0.9 * r)),
            lambda p: p[0] > 180 and p[1] > 180 and p[2] > 180)
        # The beard fill is light grey; the face is cream -- the beard
        # region must be overwhelmingly light (fill + face), and the
        # beard OUTLINE must draw dark pixels along the chord.
        self.assertGreater(light, 500)
        dark = self._count(
            img, (int(hx - 0.6 * r), int(hy + 0.45 * r),
                  int(hx + 0.6 * r), int(hy + 0.6 * r)),
            lambda p: p[0] < 80 and p[1] < 80 and p[2] < 100)
        self.assertGreater(dark, 50)

    def test_no_beard_by_default(self):
        img, ch = self._draw()
        J = ch.joints()
        hx, hy = J["head"]
        r = ch.head_r
        dark = self._count(
            img, (int(hx - 0.6 * r), int(hy + 0.45 * r),
                  int(hx + 0.6 * r), int(hy + 0.6 * r)),
            lambda p: p[0] < 80 and p[1] < 80 and p[2] < 100)
        self.assertEqual(dark, 0)

    def test_orange_hat_dome(self):
        img, ch = self._draw(hat="cap", hat_color="#d97a2b")
        J = ch.joints()
        hx, hy = J["head"]
        r = ch.head_r
        orange = self._count(
            img, (int(hx - 0.5 * r), int(hy - 1.7 * r),
                  int(hx + 0.5 * r), int(hy - 1.0 * r)),
            lambda p: p[0] > 180 and 90 < p[1] < 150 and p[2] < 80)
        self.assertGreater(orange, 200)

    def test_scarf_band_at_neck(self):
        img, ch = self._draw(scarf_color="#d9a441")
        J = ch.joints()
        hx, hy = J["head"]
        r = ch.head_r
        yellow = self._count(
            img, (int(hx - 0.6 * r), int(hy + 0.95 * r),
                  int(hx + 0.6 * r), int(hy + 1.25 * r)),
            lambda p: p[0] > 180 and 130 < p[1] < 190 and p[2] < 110)
        self.assertGreater(yellow, 200)

    def test_invalid_beard_style_raises(self):
        with self.assertRaises(ValueError):
            Stickman(beard_style="goatee")


if __name__ == "__main__":
    unittest.main()


class TestApronArt(unittest.TestCase):
    """Apron pixels: a panel in the named colour over the torso
    front, absent without a colour, absent from behind."""

    def _draw(self, view="front", **kw):
        img = Image.new("RGB", (400, 560), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        ch = Stickman(height=500, name="T", hat="none", moustache=False,
                      **kw)
        standing(ch, 200, 540)
        draw_character_v4(draw, ch, expression="neutral", view=view)
        return img

    def _apron_pixels(self, img):
        # Apron colour #5a3421: count near-exact pixels in the torso
        # band (centre column, chest to mid-thigh).
        px = img.load()
        n = 0
        for y in range(200, 420):
            for x in range(180, 221):
                r, g, b = px[x, y][:3]
                if abs(r - 0x5a) < 12 and abs(g - 0x34) < 12 \
                        and abs(b - 0x21) < 12:
                    n += 1
        return n

    def test_apron_panel_draws_in_front_view(self):
        img = self._draw(apron_color="#5a3421")
        self.assertGreater(self._apron_pixels(img), 200)

    def test_no_apron_without_colour(self):
        img = self._draw()
        self.assertEqual(self._apron_pixels(img), 0)

    def test_no_apron_from_behind(self):
        img = self._draw(view="back", apron_color="#5a3421")
        self.assertEqual(self._apron_pixels(img), 0)
