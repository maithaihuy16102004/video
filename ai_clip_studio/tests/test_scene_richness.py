"""Scene richness (round-2 maximum-detail review, system 6F).

F1: the texture gate (MIN_FACE_PX 40 -> 24) after an A/B on real
backgrounds. F2: rock/sand/whitewash painters (the cave was 100%
flat, the trench 0 textured faces). F3: foreground layers for the
interior (none) + a second cave rock, AND the production FG fit
now uses the shot camera (fitting against the establishing camera
left every non-establishing shot's foreground off-frame). F4:
point lights at the cave torch and the interior lamp. F5
(per-element jitter for gated-small faces) was deliberately
SKIPPED: the remaining gated faces are sub-16px trim no texture
can rescue, and the frames already read rich without it.
"""

import unittest
from pathlib import Path

from ai_clip_studio import environment_v2 as env2
from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import (
    build_environment, fit_foreground_to_frustum,
    validate_fg_composition)
from ai_clip_studio.paint_textures import (
    MIN_FACE_PX, clear_texture_cache, paint_plaster, paint_rock,
    paint_sand, texture_for_material)

EXAMPLES = Path(__file__).parent.parent.parent / "examples"


def _std(img):
    px = list(img.convert("L").getdata())
    mean = sum(px) / len(px)
    return (sum((p - mean) ** 2 for p in px) / len(px)) ** 0.5


def _standing_box(cam, width=1920, height=1080, x=0.0, z=0.0):
    pts = [cam.project((cx, cy, z), width, height)[:2]
           for cx in (x - 0.4, x + 0.4) for cy in (0.0, 1.8)]
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


class TestTextureGate(unittest.TestCase):
    def test_gate_value(self):
        self.assertEqual(MIN_FACE_PX, 24)

    def test_gate_boundary(self):
        el = {"id": "wall", "color": (150, 145, 135),
              "material": "stone"}
        normal = (0.0, 0.0, 1.0)
        big = [(0, 0), (24, 0), (24, 24), (0, 24)]
        self.assertIsNotNone(env2._face_texture(el, normal, big,
                                                2.0, 2.0))
        narrow = [(0, 0), (23, 0), (23, 40), (0, 40)]
        self.assertIsNone(env2._face_texture(el, normal, narrow,
                                             2.0, 2.0))

    def test_unmapped_material_stays_flat_at_any_size(self):
        el = {"id": "win", "color": (120, 140, 170),
              "material": "glass"}
        big = [(0, 0), (200, 0), (200, 200), (0, 200)]
        self.assertIsNone(env2._face_texture(el, (0, 0, 1), big,
                                             2.0, 2.0))


class TestNewPainters(unittest.TestCase):
    def setUp(self):
        clear_texture_cache()

    def test_rock_deterministic_and_textured(self):
        a = paint_rock(4.0, 3.0, (74, 66, 60), 7)
        b = paint_rock(4.0, 3.0, (74, 66, 60), 7)
        self.assertEqual(list(a.getdata()), list(b.getdata()))
        self.assertGreater(_std(a), 5.0)
        c = paint_rock(4.0, 3.0, (74, 66, 60), 8)
        self.assertNotEqual(list(a.getdata()), list(c.getdata()))

    def test_sand_deterministic_and_textured(self):
        a = paint_sand(0.42, 0.3, (158, 138, 100), 7)
        b = paint_sand(0.42, 0.3, (158, 138, 100), 7)
        self.assertEqual(list(a.getdata()), list(b.getdata()))
        self.assertGreater(_std(a), 3.0)

    def test_sand_relief_shading_top_lighter_than_bottom(self):
        img = paint_sand(2.0, 1.0, (158, 138, 100), 7)
        top = sum(sum(p) for p in
                  list(img.getdata())[: img.width * 2])
        bot = sum(sum(p) for p in
                  list(img.getdata())[-img.width * 2:])
        self.assertGreater(top, bot)

    def test_material_mapping(self):
        self.assertIsNotNone(
            texture_for_material("rock", (74, 66, 60), 4.0, 3.0, 7))
        self.assertIsNotNone(
            texture_for_material("sand", (158, 138, 100), 1.0, 1.0,
                                 7))
        self.assertIsNotNone(
            texture_for_material("whitewash", (240, 238, 230), 3.0,
                                 2.5, 7))

    def test_whitewash_is_plaster(self):
        a = texture_for_material("whitewash", (240, 238, 230), 3.0,
                                 2.5, 7)
        b = paint_plaster(3.0, 2.5, (240, 238, 230), 7,
                          windows=False)
        self.assertEqual(list(a.getdata()), list(b.getdata()))

    def test_cache_returns_same_object(self):
        a = texture_for_material("rock", (74, 66, 60), 4.0, 3.0, 7)
        b = texture_for_material("rock", (74, 66, 60), 4.0, 3.0, 7)
        self.assertIs(a, b)


def _cave_traits():
    return {"id": "LOC_CAVE", "name": "Cave of Rhea",
            "features": ["Hang động.", "Đuốc.", "Thạch nhũ."],
            "period": "mythic"}


def _bare_room_traits():
    return {"id": "LOC_BARE", "name": "Empty room",
            "features": ["Nội thất trống.", "Tường trắng."],
            "period": "1914"}


class TestForegroundLayers(unittest.TestCase):
    def test_interior_has_two_fg_wall_returns(self):
        env = build_environment(_bare_room_traits(),
                                time_of_day="day")
        self.assertEqual(env["archetype"], "INTERIOR_GENERIC")
        fg = [e for e in env["elements"] if e["layer"] == "FG"]
        self.assertEqual({e["id"] for e in fg},
                         {"room_fg_L", "room_fg_R"})
        for el in fg:
            self.assertEqual(el["kind"], "room_wall")
            self.assertEqual(el["material"], "plaster")

    def test_cave_has_two_fg_rocks(self):
        env = build_environment(_cave_traits(), time_of_day="day")
        self.assertEqual(env["archetype"], "CAVE")
        fg = [e for e in env["elements"] if e["layer"] == "FG"]
        self.assertEqual({e["id"] for e in fg},
                         {"rockFG", "rockFG_left"})

    def test_fg_validates_at_shot_cameras(self):
        for traits in (_bare_room_traits(), _cave_traits()):
            env = build_environment(traits, time_of_day="day")
            for shot_type in ("establishing", "medium"):
                cam = viewpoint_for_shot(shot_type, None,
                                         (0, 1.2, 0))
                fit = fit_foreground_to_frustum(env, cam,
                                                size=(1920, 1080))
                res = validate_fg_composition(
                    fit, cam, size=(1920, 1080),
                    subject_boxes=[_standing_box(cam)])
                self.assertTrue(res["ok"],
                                f"{shot_type}: {res['errors']}")
                for el in res["elements"]:
                    self.assertTrue(el["in_frame"], el)
                    self.assertFalse(el["overlaps_standing_box"],
                                     el)
                    self.assertLess(el["area_fraction"], 0.40)


class TestPointLights(unittest.TestCase):
    def test_cave_torch_light_matches_flame_element(self):
        env = build_environment(_cave_traits(), time_of_day="day")
        flame = next(e for e in env["elements"]
                     if e["id"] == "flame")
        lights = env.get("point_lights") or []
        self.assertEqual(len(lights), 1)
        self.assertEqual(lights[0]["id"], "torch_glow")
        self.assertEqual(tuple(lights[0]["position"]),
                         tuple(flame["center"]))

    def test_interior_lamp_light_matches_shade_element(self):
        env = build_environment(_bare_room_traits(),
                                time_of_day="day")
        shade = next(e for e in env["elements"]
                     if e["id"] == "room_lamp_shade")
        lights = env.get("point_lights") or []
        # Round 12: the two bright room windows add window lights
        # after the spec lights, so the count is 3, not 1. The
        # lamp is still first and still matches the shade exactly.
        self.assertEqual(len(lights), 3)
        self.assertEqual(lights[0]["id"], "lamp_glow")
        self.assertEqual(tuple(lights[0]["position"]),
                         tuple(shade["center"]))
        self.assertEqual([pl["id"] for pl in lights[1:]],
                         ["window_light_room_win_0",
                          "window_light_room_win_1"])

    def test_torch_warms_the_wall_near_the_flame(self):
        env = build_environment(_cave_traits(), time_of_day="day")
        cam = viewpoint_for_shot("medium", "eye_level",
                                 subject_pos=(0.0, 1.2, 0.0))
        lit = env2.render_environment(env, cam, (1920, 1080),
                                      draw_layers=("BG", "MG"))
        dark = env2.render_environment(
            dict(env, point_lights=[]), cam, (1920, 1080),
            draw_layers=("BG", "MG"))

        def mean(img, cx, cy, half=40):
            crop = img.crop((cx - half, cy - half, cx + half,
                             cy + half))
            px = list(crop.getdata())
            n = len(px)
            return tuple(sum(p[ch] for p in px) / n
                         for ch in range(3))

        lit_m = mean(lit, 900, 400)
        dark_m = mean(dark, 900, 400)
        # Warmer (red gains more than blue) and brighter.
        self.assertGreater(lit_m[0] - dark_m[0],
                           lit_m[2] - dark_m[2])
        self.assertGreater(sum(lit_m), sum(dark_m))


class TestProductionFgFit(unittest.TestCase):
    def test_render_fits_fg_against_the_shot_camera(self):
        from ai_clip_studio import product_renderer as pr
        from ai_clip_studio.action_compiler import compile_actions
        from ai_clip_studio.product_renderer import (
            _render_shot, plan_shots)
        from ai_clip_studio.studio_script_v1 import (
            parse_studio_script_v1)
        from ai_clip_studio.studio_script_v1_adapter import (
            adapt_document)
        import tempfile
        text = (EXAMPLES / "hitler_ep01_munich_1914.studio.md"
                ).read_text(encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(text))
        shots = plan_shots(
            package,
            [{"line_index": i + 1, "duration": 3.0}
             for i in range(9)])
        for i, shot in enumerate(shots):
            shot["index"] = i
        spans, clock = {}, 0.0
        for shot in shots:
            did = shot.get("directive_shot_id")
            if did:
                span = spans.setdefault(str(did), [clock, clock])
                span[1] = clock + float(shot["duration"])
            clock += float(shot["duration"])
        events, unsupported = compile_actions(
            package, timeline={"spans": spans})
        package["compiled_actions"] = {
            "events": events, "unsupported": unsupported,
            "spans_supplied": True, "compile_error": None}
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC03_SH01")
        seen = []
        orig = pr.fit_foreground_to_frustum

        def spy(pkg, camera, size=(1920, 1080), **kw):
            seen.append(tuple(camera.position))
            return orig(pkg, camera, size, **kw)

        pr.fit_foreground_to_frustum = spy
        try:
            with tempfile.TemporaryDirectory() as tmp:
                _render_shot({"shot": shot, "package": package,
                              "out_dir": tmp})
        finally:
            pr.fit_foreground_to_frustum = orig
        self.assertTrue(seen)
        establishing = viewpoint_for_shot(
            "establishing", "eye_level", subject_pos=(0.0, 1.2, 0.0))
        # The bug: production always fitted against the
        # establishing camera (radius 7.5), so every other shot's
        # FG rendered off-frame. The fit must see the shot camera.
        for pos in seen:
            self.assertNotEqual(
                tuple(round(v, 3) for v in pos),
                tuple(round(v, 3) for v in establishing.position))


if __name__ == "__main__":
    unittest.main()
