"""Tests for ai_clip_studio.paint_textures (P-S1).

Painters must be deterministic pure functions of their arguments,
palette-driven (mean colour stays near the element colour), and the
quad paste must respect the quad boundary, the irradiance shading
contract, and degenerate inputs. New tests, written for this repo;
no source-repo test code exists to copy.
"""

import math
import random
import unittest

from PIL import Image

from ai_clip_studio.paint_textures import (
    clear_texture_cache,
    darken,
    facade_window_layout,
    jit_color,
    paint_brick,
    paint_cobble,
    paint_grass,
    paint_planks,
    paint_plaster,
    paint_roof,
    paint_stone,
    paste_textured_quad,
    texture_for_material,
)


def _mean(img):
    px = list(img.convert("RGB").getdata())
    n = len(px)
    return tuple(sum(c[i] for c in px) / n for i in range(3))


def _std(img):
    px = list(img.convert("RGB").getdata())
    n = len(px)
    means = _mean(img)
    var = [sum((c[i] - means[i]) ** 2 for c in px) / n for i in range(3)]
    return tuple(math.sqrt(v) for v in var)


class TestJitColor(unittest.TestCase):
    def test_deterministic_for_rng_state(self):
        a = jit_color(random.Random(7), (200, 120, 60))
        b = jit_color(random.Random(7), (200, 120, 60))
        self.assertEqual(a, b)

    def test_stays_near_base(self):
        rng = random.Random(3)
        for _ in range(50):
            r, g, b = jit_color(rng, (200, 120, 60))
            self.assertTrue(0 <= r <= 255 and 0 <= g <= 255
                            and 0 <= b <= 255)
            self.assertGreater(r, g)  # warm hue family preserved

    def test_zero_jitter_is_identity(self):
        self.assertEqual(jit_color(random.Random(1), (10, 20, 30),
                                   dv=0.0, dh=0.0, ds=0.0), (10, 20, 30))

    def test_darken(self):
        self.assertEqual(darken((200, 100, 50), 0.5), (100, 50, 25))
        self.assertEqual(darken((200, 100, 50), 1.0), (200, 100, 50))


class TestFacadeWindowLayout(unittest.TestCase):
    def test_typical_facade(self):
        lay = facade_window_layout(6.0, 5.6)
        self.assertEqual(lay["floors"], 2)
        self.assertEqual(lay["n_win"], 2)
        self.assertEqual(len(lay["windows"]), 4)
        for (x, y, w, h) in lay["windows"]:
            self.assertGreaterEqual(x, 0)
            self.assertLessEqual(x + w, 6.0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(y + h, 5.6)
            self.assertAlmostEqual(w, 0.85)
            self.assertAlmostEqual(h, 1.25)
        self.assertIsNotNone(lay["door"])
        dx, dy, dw, dh = lay["door"]
        self.assertEqual(dy, 0.0)
        self.assertAlmostEqual(dw, 1.0)
        self.assertAlmostEqual(dh, 2.1)
        self.assertAlmostEqual(dx + dw / 2, 3.0)  # centred

    def test_tiny_wall(self):
        # A 2.0 m wall cannot fit a 1.25 m window on a 0.9 m sill:
        # the grid skips it (source-faithful behaviour), no door.
        lay = facade_window_layout(1.0, 2.0)
        self.assertEqual(lay["floors"], 1)
        self.assertEqual(lay["n_win"], 1)
        self.assertEqual(len(lay["windows"]), 0)
        self.assertIsNone(lay["door"])
        lay2 = facade_window_layout(2.2, 2.8)
        self.assertEqual(len(lay2["windows"]), 1)

    def test_deterministic(self):
        self.assertEqual(facade_window_layout(9.5, 8.4),
                         facade_window_layout(9.5, 8.4))


class TestPainters(unittest.TestCase):
    PAINTERS = [
        ("plaster", lambda: paint_plaster(3.0, 2.8, (210, 190, 160), 11)),
        ("brick", lambda: paint_brick(3.0, 2.8, (170, 80, 55), 11)),
        ("stone", lambda: paint_stone(3.0, 2.8, (150, 145, 135), 11)),
        ("roof", lambda: paint_roof(3.0, 2.0, (140, 60, 45), 11)),
        ("cobble", lambda: paint_cobble(3.0, 3.0, (130, 125, 118), 11)),
        ("grass", lambda: paint_grass(3.0, 3.0, (90, 130, 60), 11)),
        ("planks", lambda: paint_planks(2.0, 2.8, (150, 110, 70), 11)),
    ]

    def test_size_mode_determinism(self):
        for name, make in self.PAINTERS:
            with self.subTest(painter=name):
                a, b = make(), make()
                self.assertEqual(a.mode, "RGB")
                self.assertEqual(a.size, b.size)
                self.assertEqual(a.tobytes(), b.tobytes())

    def test_mean_stays_near_base(self):
        cases = [
            (paint_plaster(3.0, 2.8, (210, 190, 160), 11), (210, 190, 160)),
            (paint_brick(3.0, 2.8, (170, 80, 55), 11), (170, 80, 55)),
            (paint_stone(3.0, 2.8, (150, 145, 135), 11), (150, 145, 135)),
            (paint_roof(3.0, 2.0, (140, 60, 45), 11), (140, 60, 45)),
            (paint_cobble(3.0, 3.0, (130, 125, 118), 11), (130, 125, 118)),
            (paint_grass(3.0, 3.0, (90, 130, 60), 11), (90, 130, 60)),
            (paint_planks(2.0, 2.8, (150, 110, 70), 11), (150, 110, 70)),
        ]
        for img, base in cases:
            mean = _mean(img)
            for i in range(3):
                self.assertLess(abs(mean[i] - base[i]), 35,
                                f"channel {i}: mean {mean} vs base {base}")

    def test_not_flat(self):
        for name, make in self.PAINTERS:
            with self.subTest(painter=name):
                std = _std(make())
                self.assertGreater(max(std), 4.0,
                                   f"{name} texture is flat: std {std}")

    def test_seed_changes_pixels(self):
        a = paint_plaster(2.0, 2.0, (200, 180, 150), 1)
        b = paint_plaster(2.0, 2.0, (200, 180, 150), 2)
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_plaster_windows_layer_changes_pixels(self):
        plain = paint_plaster(6.0, 5.6, (210, 190, 160), 5, windows=False)
        with_win = paint_plaster(6.0, 5.6, (210, 190, 160), 5,
                                 windows=True)
        diff = sum(1 for a, b in zip(plain.getdata(), with_win.getdata())
                   if a != b)
        total = plain.width * plain.height
        self.assertGreater(diff / total, 0.05)
        # Glass is bluish: some pixels must be blue-dominant.
        blue = sum(1 for px in with_win.getdata()
                   if px[2] > px[0] + 20)
        self.assertGreater(blue, 100)

    def test_large_texture_capped(self):
        img = paint_stone(40.0, 30.0, (150, 145, 135), 1)
        self.assertLessEqual(max(img.size), 1024)
        # Every painter must survive the cap scale without errors.
        for make in (lambda: paint_brick(40.0, 30.0, (170, 80, 55), 1),
                     lambda: paint_roof(40.0, 30.0, (140, 60, 45), 1),
                     lambda: paint_cobble(40.0, 30.0, (130, 125, 118), 1),
                     lambda: paint_plaster(40.0, 30.0, (210, 190, 160), 1),
                     lambda: paint_grass(40.0, 30.0, (90, 130, 60), 1),
                     lambda: paint_planks(40.0, 30.0, (150, 110, 70), 1)):
            capped = make()
            self.assertLessEqual(max(capped.size), 1024)


class TestTextureCache(unittest.TestCase):
    def setUp(self):
        clear_texture_cache()

    def tearDown(self):
        clear_texture_cache()

    def test_same_args_same_object(self):
        a = texture_for_material("plaster", (210, 190, 160), 3.0, 2.8, 9)
        b = texture_for_material("plaster", (210, 190, 160), 3.0, 2.8, 9)
        self.assertIs(a, b)

    def test_different_seed_different_object(self):
        a = texture_for_material("brick", (170, 80, 55), 3.0, 2.8, 9)
        b = texture_for_material("brick", (170, 80, 55), 3.0, 2.8, 10)
        self.assertIsNot(a, b)

    def test_unmapped_material_is_none(self):
        # Wood is MAPPED since P-S2 (planks, size-gated by the
        # caller); the materials below keep the flat fill.
        for mat in ("glass", "silhouette", "foliage", "ground",
                    "iron", "paper", ""):
            self.assertIsNone(
                texture_for_material(mat, (100, 100, 100), 2.0, 2.0, 1))

    def test_mapped_materials(self):
        for mat in ("plaster", "brick", "stone", "marble", "roof_tile"):
            img = texture_for_material(mat, (150, 140, 130), 2.0, 2.0, 1)
            self.assertIsNotNone(img, mat)
            self.assertEqual(img.mode, "RGB")


class TestPasteTexturedQuad(unittest.TestCase):
    def _checker(self):
        from PIL import ImageDraw

        img = Image.new("RGB", (64, 64), (255, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([32, 0, 63, 31], fill=(0, 255, 0))
        draw.rectangle([0, 32, 31, 63], fill=(0, 0, 255))
        draw.rectangle([32, 32, 63, 63], fill=(255, 255, 0))
        return img

    def test_axis_rect_paste(self):
        canvas = Image.new("RGB", (100, 100), (10, 10, 10))
        tex = Image.new("RGB", (20, 20), (200, 100, 50))
        paste_textured_quad(canvas, [(20, 20), (20, 60), (60, 60), (60, 20)],
                            tex)
        self.assertEqual(canvas.getpixel((40, 40)), (200, 100, 50))
        self.assertEqual(canvas.getpixel((5, 5)), (10, 10, 10))
        self.assertEqual(canvas.getpixel((80, 80)), (10, 10, 10))

    def test_skewed_quad_stays_inside(self):
        canvas = Image.new("RGB", (100, 100), (10, 10, 10))
        tex = Image.new("RGB", (20, 20), (200, 100, 50))
        paste_textured_quad(canvas, [(20, 30), (30, 10), (70, 20), (60, 60)],
                            tex)
        # Centre of the quad is textured; far corners untouched.
        self.assertEqual(canvas.getpixel((45, 30)), (200, 100, 50))
        self.assertEqual(canvas.getpixel((5, 5)), (10, 10, 10))
        self.assertEqual(canvas.getpixel((95, 95)), (10, 10, 10))
        self.assertEqual(canvas.getpixel((5, 95)), (10, 10, 10))

    def test_irradiance_darkens(self):
        canvas = Image.new("RGB", (60, 60), (0, 0, 0))
        tex = Image.new("RGB", (10, 10), (200, 100, 50))
        paste_textured_quad(canvas, [(10, 10), (10, 50), (50, 50), (50, 10)],
                            tex, irradiance=0.5)
        px = canvas.getpixel((30, 30))
        self.assertEqual(px, (100, 50, 25))

    def test_irradiance_clamped_at_one(self):
        canvas = Image.new("RGB", (60, 60), (0, 0, 0))
        tex = Image.new("RGB", (10, 10), (200, 100, 50))
        paste_textured_quad(canvas, [(10, 10), (10, 50), (50, 50), (50, 10)],
                            tex, irradiance=1.6)
        self.assertEqual(canvas.getpixel((30, 30)), (200, 100, 50))

    def test_degenerate_quad_is_noop(self):
        canvas = Image.new("RGB", (60, 60), (7, 7, 7))
        tex = Image.new("RGB", (10, 10), (200, 100, 50))
        before = canvas.tobytes()
        paste_textured_quad(canvas, [(10, 10), (20, 10), (30, 10), (40, 10)],
                            tex)
        self.assertEqual(canvas.tobytes(), before)

    def test_off_frame_quad_clipped(self):
        canvas = Image.new("RGB", (60, 60), (7, 7, 7))
        tex = Image.new("RGB", (10, 10), (200, 100, 50))
        paste_textured_quad(canvas, [(-20, -20), (-20, 30), (30, 30),
                                     (30, -20)], tex)
        self.assertEqual(canvas.getpixel((10, 10)), (200, 100, 50))
        self.assertEqual(canvas.getpixel((50, 50)), (7, 7, 7))

    def test_rgba_canvas_preserves_alpha_outside(self):
        canvas = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
        tex = Image.new("RGB", (10, 10), (200, 100, 50))
        paste_textured_quad(canvas, [(10, 10), (10, 50), (50, 50), (50, 10)],
                            tex)
        self.assertEqual(canvas.getpixel((30, 30)), (200, 100, 50, 255))
        self.assertEqual(canvas.getpixel((5, 5)), (0, 0, 0, 0))

    def test_texture_not_mutated(self):
        tex = self._checker()
        before = tex.tobytes()
        canvas = Image.new("RGB", (100, 100), (0, 0, 0))
        paste_textured_quad(canvas, [(20, 30), (30, 10), (70, 20), (60, 60)],
                            tex, irradiance=0.5)
        self.assertEqual(tex.tobytes(), before)


class TestEnvironmentWiring(unittest.TestCase):
    """P-S1 wiring: render_environment paints textures onto mapped
    faces (default) and reproduces the flat behaviour with
    textures=False."""

    def _package(self, elements):
        layers = {"BG": [], "MG": [], "FG": []}
        for el in elements:
            layers[el["layer"]].append(el["id"])
        return {
            "archetype": "TEST", "kind": "environment",
            "layers": layers, "elements": elements,
            "palette": {}, "light": {},
            "ground": {"kind": "neutral", "color": (120, 118, 112)},
            "provenance": {}, "validation": [], "period_errors": [],
        }

    def _camera(self):
        from ai_clip_studio.renderer25d.camera import PerspectiveCamera
        return PerspectiveCamera(position=(0.0, 2.0, 4.8),
                                 target=(0.0, 1.2, 0.0), fov_deg=46.0,
                                 aspect=16 / 9)

    def _wall(self):
        return {"id": "wall1", "kind": "facade", "layer": "BG",
                "geometry": "box", "center": (0.0, 2.5, -6.0),
                "size": (6.0, 5.0, 1.0), "color": (210, 190, 160),
                "material": "plaster", "attachment": None,
                "label": "", "extra": {}}

    def _face_centre(self, cam, el):
        cx, cy, cz = el["center"]
        sx, sy, sz = (el["size"][0] / 2, el["size"][1] / 2,
                      el["size"][2] / 2)
        pts = []
        for dx, dy in ((-sx, -sy), (-sx, sy), (sx, sy), (sx, -sy)):
            x, y, _, vis = cam.project((cx + dx, cy + dy, cz + sz),
                                       960, 540)
            self.assertTrue(vis)
            pts.append((x, y))
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (int((min(xs) + max(xs)) / 2),
                int((min(ys) + max(ys)) / 2))

    def test_wall_face_textured_not_flat(self):
        from ai_clip_studio.environment_v2 import render_environment
        pkg = self._package([self._wall()])
        cam = self._camera()
        tex = render_environment(pkg, cam, (960, 540), textures=True)
        flat = render_environment(pkg, cam, (960, 540), textures=False)
        cx, cy = self._face_centre(cam, self._wall())
        region_tex = tex.crop((cx - 30, cy - 30, cx + 30, cy + 30))
        region_flat = flat.crop((cx - 30, cy - 30, cx + 30, cy + 30))
        self.assertGreater(max(_std(region_tex)), 4.0)
        self.assertEqual(max(_std(region_flat)), 0.0)

    def test_textured_render_deterministic(self):
        from ai_clip_studio.environment_v2 import (
            build_environment, render_environment)
        traits = {"features": ["Nhà nhiều tầng, mặt tiền trát vữa.",
                               "Cửa sổ cao, khung gỗ.", "Mái nhà dốc.",
                               "Đường lát đá."], "period": "1914"}
        pkg = build_environment(traits, period="1914", time_of_day="day")
        cam = self._camera()
        a = render_environment(pkg, cam, (960, 540))
        b = render_environment(pkg, cam, (960, 540))
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_street_package_differs_textured_vs_flat(self):
        from ai_clip_studio.environment_v2 import (
            build_environment, render_environment)
        traits = {"features": ["Nhà nhiều tầng, mặt tiền trát vữa.",
                               "Cửa sổ cao, khung gỗ.", "Mái nhà dốc.",
                               "Đường lát đá."], "period": "1914"}
        pkg = build_environment(traits, period="1914", time_of_day="day")
        cam = self._camera()
        tex = render_environment(pkg, cam, (960, 540), textures=True)
        flat = render_environment(pkg, cam, (960, 540), textures=False)
        diff = sum(1 for a, b in zip(tex.getdata(), flat.getdata())
                   if a != b)
        self.assertGreater(diff / (960 * 540), 0.01)

    def test_small_face_keeps_flat_fill(self):
        from ai_clip_studio.environment_v2 import render_environment
        tiny = dict(self._wall(), id="tiny1",
                    center=(0.0, 2.5, -25.0), size=(0.5, 0.5, 0.5))
        pkg = self._package([tiny])
        cam = self._camera()
        tex = render_environment(pkg, cam, (960, 540), textures=True)
        flat = render_environment(pkg, cam, (960, 540), textures=False)
        self.assertEqual(tex.tobytes(), flat.tobytes())

    def test_unmapped_material_keeps_flat_fill(self):
        from ai_clip_studio.environment_v2 import render_environment
        # Glass is unmapped, so the face keeps the flat fill even
        # with textures=True. (Wood is mapped since P-S2; the wood
        # face test lives in test_cinematic_upgrade_b.py.)
        glass = dict(self._wall(), id="glass1", material="glass")
        pkg = self._package([glass])
        cam = self._camera()
        tex = render_environment(pkg, cam, (960, 540), textures=True)
        flat = render_environment(pkg, cam, (960, 540), textures=False)
        self.assertEqual(tex.tobytes(), flat.tobytes())

    def test_roof_slopes_textured(self):
        from ai_clip_studio.environment_v2 import render_environment
        roof = {"id": "roof1", "kind": "gable_roof", "layer": "BG",
                "geometry": "gable_prism", "center": (0.0, 5.0, -6.0),
                "size": (6.0, 2.0, 3.0), "color": (140, 60, 45),
                "material": "roof_tile", "attachment": None,
                "label": "", "extra": {}}
        pkg = self._package([roof])
        cam = self._camera()
        tex = render_environment(pkg, cam, (960, 540), textures=True)
        flat = render_environment(pkg, cam, (960, 540), textures=False)
        diff = sum(1 for a, b in zip(tex.getdata(), flat.getdata())
                   if a != b)
        self.assertGreater(diff, 100)

    def test_transparent_fg_pass_textured(self):
        from ai_clip_studio.environment_v2 import render_environment
        fg = dict(self._wall(), id="fgwall", layer="FG",
                  center=(0.0, 2.5, 1.5), size=(3.0, 4.0, 1.0))
        pkg = self._package([fg])
        cam = self._camera()
        img = render_environment(pkg, cam, (960, 540),
                                 draw_layers=("FG",), transparent=True)
        self.assertEqual(img.mode, "RGBA")
        cx, cy = self._face_centre(cam, fg)
        region = img.crop((cx - 30, cy - 30, cx + 30, cy + 30))
        self.assertGreater(max(_std(region.convert("RGB"))), 4.0)
        # Outside the face the canvas stays transparent.
        self.assertEqual(img.getpixel((10, 10))[3], 0)


if __name__ == "__main__":
    unittest.main()
