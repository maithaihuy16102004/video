"""Round-6 environment fixes: position-word landmark slots, the
three-piece pedestal, the cave's own rock floor, and the flame
teardrop.

Before: the cave pedestal declared "ở giữa hang" (middle of the
cave) staged at x=-5.5 (far left, first slot in cycle order) as
a single cube nobody could identify; the cave floor reused the
forge's dressed-stone pavers; the torch flame drew as a flat
yellow oval on a stick.
"""

import random
import unittest

from PIL import Image, ImageDraw

from ai_clip_studio.environment_v2 import (
    ARCHETYPES, _draw_blob, build_environment, build_landmarks,
    validate_attachments)
from ai_clip_studio.lighting import rig_for, light_for
from ai_clip_studio.paint_textures import ground_texture_for
from ai_clip_studio.renderer25d.camera import PerspectiveCamera

CTX = {"facade_colors": [(74, 66, 60), (62, 56, 52)],
       "roof_color": (52, 46, 42),
       "window_color": (52, 66, 88), "is_night": False,
       "sign_text": "", "trait_text": ""}


class TestLandmarkPositionWords(unittest.TestCase):
    def _pedestal(self, text):
        els = build_landmarks(
            {"landmarks": [text]}, random.Random(1), CTX)
        shaft = [e for e in els if e["kind"] == "statue_pedestal"]
        self.assertEqual(len(shaft), 1)
        return els, shaft[0]

    def test_middle_word_stages_center(self):
        _els, shaft = self._pedestal("Bệ đá ở giữa hang.")
        self.assertEqual(shaft["center"][0], 0.0)
        self.assertEqual(shaft["center"][2], -8.5)

    def test_left_phrase_stages_left(self):
        _els, shaft = self._pedestal("Bệ đá bên trái hang.")
        self.assertEqual(shaft["center"][0], -5.5)

    def test_right_phrase_stages_right(self):
        _els, shaft = self._pedestal("Bệ đá bên phải hang.")
        self.assertEqual(shaft["center"][0], 5.5)

    def test_bare_phai_modal_does_not_mean_right(self):
        # "phải" as "must" must not stage right: center wins via
        # "giữa", and without any position word the cycle order
        # (first slot) applies.
        _els, shaft = self._pedestal("Bệ đá phải ở giữa hang.")
        self.assertEqual(shaft["center"][0], 0.0)
        _els, shaft = self._pedestal("Bệ đá phải thật lớn.")
        self.assertEqual(shaft["center"][0], -5.5)

    def test_no_position_word_keeps_cycle_order(self):
        _els, shaft = self._pedestal("Bệ đá.")
        self.assertEqual(shaft["center"][0], -5.5)

    def test_two_positioned_landmarks_do_not_collide(self):
        els = build_landmarks(
            {"landmarks": ["Bệ đá ở giữa hang.",
                           "Tượng đá ở giữa hang."]},
            random.Random(1), CTX)
        # Footprints only: a statue's figure shares its own
        # pedestal's (x, z) by design (it stands on it).
        centers = [(e["center"][0], e["center"][2]) for e in els
                   if e["kind"] == "statue_pedestal"]
        self.assertEqual(len(set(centers)), len(centers))


class TestPedestalShape(unittest.TestCase):
    def test_pedestal_pieces_share_cap_plane(self):
        els = build_landmarks(
            {"landmarks": ["Bệ đá ở giữa hang."]},
            random.Random(1), CTX)
        # Round-8: seven pieces (base + shaft + cap + 4 rim
        # bars). The support anchor reads the shaft's top face:
        # 1.55 m, the same plane as the cap top; the rim bars sit
        # on the cap (bottom 1.55, top 1.65) and frame the socket.
        self.assertEqual(len(els), 7)
        by_id = {e["id"]: e for e in els}
        shaft = by_id["lm_pedestal_pedestal"]
        base = by_id["lm_pedestal_pedestal_base"]
        cap = by_id["lm_pedestal_pedestal_cap"]
        self.assertEqual(shaft["center"][1] + shaft["size"][1] / 2,
                         1.55)
        # The cap's top is the same plane; base/cap are wider.
        self.assertEqual(cap["center"][1] + cap["size"][1] / 2, 1.55)
        self.assertGreater(cap["size"][0], shaft["size"][0])
        self.assertGreater(base["size"][0], shaft["size"][0])
        rims = [e for e in els if "rim" in e["id"]]
        self.assertEqual(len(rims), 4)
        for rim in rims:
            self.assertAlmostEqual(
                rim["center"][1] - rim["size"][1] / 2, 1.55,
                places=6)
            self.assertAlmostEqual(
                rim["center"][1] + rim["size"][1] / 2, 1.65,
                places=6)
        # Only the shaft carries the anchor kind.
        self.assertEqual(
            [e["id"] for e in els
             if e["kind"] == "statue_pedestal"],
            ["lm_pedestal_pedestal"])

    def test_pedestal_group_validates_attachments(self):
        env = build_environment({
            "location_keyword": "cave",
            "landmarks": ["Bệ đá ở giữa hang."],
            "features": ["hang động"]})
        self.assertEqual(validate_attachments(env), [])


class TestCaveGround(unittest.TestCase):
    def test_cave_has_its_own_rock_floor(self):
        self.assertEqual(ARCHETYPES["CAVE"]["ground_kind"],
                         "cave_rock")
        self.assertEqual(ARCHETYPES["FORGE"]["ground_kind"],
                         "dark_stone")

    def test_cave_rock_texture_differs_from_dressed_stone(self):
        rock = ground_texture_for("cave_rock", (70, 62, 56),
                                  8.0, 2.0, 777)
        stone = ground_texture_for("dark_stone", (70, 62, 56),
                                   8.0, 2.0, 777)
        self.assertIsNotNone(rock)
        self.assertIsNotNone(stone)
        self.assertNotEqual(rock.tobytes(), stone.tobytes())


class TestFlameTeardrop(unittest.TestCase):
    def test_flame_draws_teardrop_with_hot_core(self):
        img = Image.new("RGB", (200, 200), (10, 10, 10))
        draw = ImageDraw.Draw(img)
        camera = PerspectiveCamera(
            position=(0.0, 2.0, 4.8), target=(0.0, 1.2, 0.0))
        rig = rig_for(light_for("day", "warm"))
        el = {"id": "flame", "kind": "flame", "layer": "MG",
              "geometry": "blob", "center": (0.0, 1.75, -7.8),
              "size": (0.5, 0.7, 0.5), "color": (255, 170, 60),
              "material": "fire", "attachment": None, "label": "",
              "extra": {}}
        _draw_blob(img, draw, el, camera, rig, 200, 200)
        # Float geometry, exactly as _draw_blob computes it:
        # rounding the center/radii first shifts probes by a
        # pixel into the outline stroke.
        x, y, scale, _vis = camera.project(el["center"], 200, 200)
        rx = el["size"][0] / 2 * scale
        ry = el["size"][1] / 2 * scale
        # Pointed top: the tip pixel is flame, and the upper
        # flank at 70% of the half-width is background -- a flat
        # oval would fill it (0.7**2 + 0.5**2 < 1), while the
        # teardrop narrows to ~45% of the half-width there.
        self.assertGreater(
            img.getpixel((int(round(x)), int(round(y - ry + 2))))[0],
            150)
        self.assertEqual(
            img.getpixel((int(round(x - 0.7 * rx)),
                          int(round(y - 0.5 * ry)))),
            (10, 10, 10))
        # Hot core near the base reads near-white.
        core = img.getpixel(
            (int(round(x)), int(round(y + 0.55 * ry))))
        self.assertGreater(min(core), 200)


if __name__ == "__main__":
    unittest.main()


def _draw_blob_on_canvas(el, size=(200, 200)):
    img = Image.new("RGB", size, (10, 10, 10))
    camera = PerspectiveCamera(
        position=(0.0, 2.0, 4.8), target=(0.0, 1.2, 0.0))
    rig = rig_for(light_for("day", "warm"))
    _draw_blob(img, ImageDraw.Draw(img), el, camera, rig,
               size[0], size[1])
    x, y, scale, _vis = camera.project(el["center"], size[0],
                                       size[1])
    return img, x, y, scale


def _blob_el(el_id, kind, center, blob_size, color):
    return {"id": el_id, "kind": kind, "layer": "MG",
            "geometry": "blob", "center": center,
            "size": blob_size, "color": color,
            "material": "fire", "attachment": None, "label": "",
            "extra": {}}


class TestFireBedAndCloudsRound6(unittest.TestCase):
    """Round-6 blob fixes: wide fire draws a fire bed with
    tongues (nested outlined ellipses read as a donut), clouds
    break the ball silhouette with bumps, coal heaps get a
    visible cap, and steam sits on the quench water."""

    def test_wide_fire_has_tongues_not_a_ring(self):
        el = _blob_el("firemouth", "fire", (0.0, 1.0, -5.75),
                      (1.0, 0.7, 0.3), (255, 140, 40))
        img, x, y, scale = _draw_blob_on_canvas(el)
        rx = el["size"][0] / 2 * scale
        ry = el["size"][1] / 2 * scale
        # A tongue rises above the ellipse's top edge at center.
        tongue = img.getpixel((int(round(x)),
                               int(round(y - 1.05 * ry))))
        self.assertGreater(tongue[0], 150,
                           "no flame tongue above the fire bed")
        # The bed's center is the bright core, not a ring hole.
        core = img.getpixel((int(round(x)), int(round(y + 0.25 * ry))))
        self.assertGreater(min(core), 180)

    def test_cloud_silhouette_extends_beyond_base_ellipse(self):
        el = _blob_el("steam", "steam", (0.0, 1.5, -2.8),
                      (0.5, 0.5, 0.4), (200, 205, 210))
        img, x, y, scale = _draw_blob_on_canvas(el)
        ry = el["size"][1] / 2 * scale
        bump = img.getpixel((int(round(x)),
                             int(round(y - 1.15 * ry))))
        self.assertNotEqual(bump, (10, 10, 10),
                            "cloud bumps do not break the silhouette")

    def test_coal_heap_cap_reads_on_near_black(self):
        el = _blob_el("coal", "coal", (0.0, 0.25, -6.3),
                      (1.0, 0.5, 0.8), (30, 28, 26))
        img, x, y, scale = _draw_blob_on_canvas(el)
        rx = el["size"][0] / 2 * scale
        ry = el["size"][1] / 2 * scale
        cap = img.getpixel((int(round(x - 0.26 * rx)),
                            int(round(y - 0.32 * ry))))
        base = img.getpixel((int(round(x + 0.6 * rx)),
                             int(round(y + 0.5 * ry))))
        self.assertGreater(sum(cap) - sum(base), 60,
                           "coal cap does not read as a heap")

    def test_steam_sits_on_the_quench_barrel(self):
        env = build_environment({
            "location_keyword": "forge",
            "features": ["lò rèn", "cái đe"]})
        els = {e["id"]: e for e in env["elements"]}
        steam = els["quench_steam"]
        barrel = els["quench_barrel"]
        steam_bottom = steam["center"][1] - steam["size"][1] / 2
        barrel_top = barrel["center"][1] + barrel["size"][1] / 2
        self.assertAlmostEqual(steam_bottom, barrel_top, places=6)
        self.assertEqual(validate_attachments(env), [])
