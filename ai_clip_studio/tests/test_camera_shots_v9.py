"""v9 regression tests: camera shot planner, scene packages, v9 scene
detail, the wave lean-inheritance fix, and the generic detour / board
primitives (audit animation v9, overnight 2026-11-11).

These tests are NEW in v9 -- they do not modify any existing test.
Baseline: 295 ai_clip_studio tests + 11 youtube_16x9 (the full-suite
count moved 285 -> 295 while Subagent B added product tests).
"""
import math
import unittest

from PIL import Image, ImageDraw

from ai_clip_studio.animation import landmarks
from ai_clip_studio.animation.character_art import make_character_instance
from ai_clip_studio.animation.primitives import (
    board_vehicle, detour_walk, standing, wave,
)
from ai_clip_studio.animation.scene_packages import (
    build_scene, rainy_street_night, register_scene_package,
)
from ai_clip_studio.camera_planner import (
    CameraPlanner, ShotDirector, safe_frame, validate_framing,
)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera
from ai_clip_studio.renderer25d.scene import CharacterAnchor

W, H = 1920, 1080


def _all_nine_segments():
    """One generic segment per shot type (requested_shot), plus the
    two cue paths (line+listener -> OTS, line+listener+reverse ->
    shot_reverse_shot). No story names: the segments are data."""
    segs = []
    for t in ("establishing", "medium", "close_up", "extreme_close_up",
              "over_the_shoulder", "reaction", "object_insert",
              "tracking", "shot_reverse_shot"):
        segs.append({"kind": "action", "speaker": "a",
                     "action_cues": ["walk"], "requested_shot": t,
                     "text": "x"})
    return segs


class TestCameraShotsV9(unittest.TestCase):
    def test_plan_returns_all_nine_shot_types(self):
        shots = CameraPlanner.plan(_all_nine_segments())
        types = [s["shot_type"] for s in shots]
        self.assertEqual(
            sorted(set(types)),
            sorted(["establishing", "medium", "close_up",
                    "extreme_close_up", "over_the_shoulder", "reaction",
                    "object_insert", "tracking", "shot_reverse_shot"]))
        self.assertEqual(len(shots), 9)

    def test_ots_and_srs_cue_paths(self):
        # A dialogue line WITH a listener (no emotion cue) goes over
        # the listener's shoulder -- the v9 gap: plan() could only
        # ever produce 7 of 9 types. A reverse cue on the reply line
        # is the shot-reverse-shot half.
        ots = CameraPlanner.plan([{"kind": "line", "speaker": "a",
                                   "listener": "b", "text": "x",
                                   "action_cues": []}])
        self.assertEqual(ots[0]["shot_type"], "over_the_shoulder")
        srs = CameraPlanner.plan([{"kind": "line", "speaker": "b",
                                   "listener": "a", "text": "y",
                                   "action_cues": ["reverse_shot"]}])
        self.assertEqual(srs[0]["shot_type"], "shot_reverse_shot")
        # The narration bug: a bare line (speaker + listener, no
        # cues) was misclassified as narration -> establishing.
        self.assertNotEqual(ots[0]["shot_type"], "establishing")

    def test_bad_requested_shot_raises(self):
        with self.assertRaises(ValueError):
            CameraPlanner.plan([{"kind": "action", "speaker": "a",
                                 "action_cues": ["walk"],
                                 "requested_shot": "bogus"}])

    def test_safe_frame_no_head_cut_on_camera_test_shots(self):
        # Every shot type, one centred subject: safe_frame must
        # return a crop with no head/edge cut and no "do not fit".
        shots = CameraPlanner.plan(_all_nine_segments())
        subject = {"cx": 960, "head_y": 200, "foot_y": 900,
                   "half_w": 120}
        for shot in shots:
            safe_shot, safe_focus, _notes = safe_frame(
                shot, (960, 500), [subject])
            issues, _focus = validate_framing(
                safe_shot, safe_focus, [subject])
            bad = [i for i in issues
                   if "cut" in i or "do not fit" in i]
            self.assertEqual(
                bad, [],
                f"{shot['shot_type']}: safe_frame left {bad}")

    def test_shot_director_directions_complete(self):
        shots = ShotDirector.direct(_all_nine_segments())
        self.assertEqual(ShotDirector.validate_direction(shots), [])
        for shot in shots:
            self.assertEqual(len(shot["direction"]), 9)

    def test_tracking_parallax_near_gt_far(self):
        # A tracking move must sell depth: the same world dx moves a
        # near point (z=1.0, foreground) much further on screen than
        # a far point (z=-12, background). Ratio must be >= 2.
        cam = PerspectiveCamera(position=(0.0, 2.0, 4.8),
                                target=(0.0, 1.2, 0.0))
        near = cam.parallax_shift_px((0.0, 0.0, 1.0), 0.5, H)
        far = cam.parallax_shift_px((0.0, 0.0, -12.0), 0.5, H)
        self.assertGreater(abs(near), 2 * abs(far))
        self.assertGreater(abs(near), 20)

    def test_frame_zero_head_margin(self):
        # v9 camera shift (-0.15 world x): frame-0 Minh head left
        # edge must be >= 20 px inside the frame (v8: -8 px, the
        # head touched the left edge).
        cam = PerspectiveCamera(position=(-0.15, 2.0, 4.8),
                                target=(-0.15, 1.2, 0.0))
        _fx, gy, _, _ = cam.project((0.0, 0.0, 0.5), W, H)
        hx, hy, _, _ = cam.project((0.0, 2.7, 0.5), W, H)
        char_h = gy - hy
        # Minh root at world x -3.0; head centre is ~1 head radius
        # above the top of the character box.
        mx, _, _, _ = cam.project((-3.0, 0.0, 0.5), W, H)
        head_r = 0.34 * char_h / 2.0
        head_left = mx - head_r
        self.assertGreaterEqual(head_left, 20,
                                f"frame-0 head left edge {head_left:.1f}px")


class TestScenePackagesV9(unittest.TestCase):
    def _scene(self, **kw):
        cam = PerspectiveCamera(position=(-0.15, 2.0, 4.8),
                                target=(-0.15, 1.2, 0.0))
        chars = [CharacterAnchor(world_pos=(-3.0, 0.0, 0.5),
                                 height=2.7, label="a"),
                 CharacterAnchor(world_pos=(1.95, 0.0, 0.5),
                                 height=2.7, label="b")]
        return build_scene("rainy_street_night", cam, chars, **kw)

    def test_rainy_street_has_all_layers(self):
        scene = self._scene()
        # Layers by WORLD depth (the scene's construction): foreground
        # z > 0 (crate / railing / path), midground -5 < z <= 0
        # (lamp / bench / sign / kerb), background z <= -5 (buildings
        # + lit windows). All three must be populated -- the v6 scene
        # had an empty foreground.
        # NOTE: Scene25D.depth_layers() buckets by RELATIVE depth
        # thirds of this scene's range, and the far buildings stretch
        # the range so the midground items fall in its "foreground"
        # bucket -- that is the bucketing's behaviour, not a missing
        # layer; the world-z bands below are the scene's own layers.
        layers = scene.depth_layers()
        self.assertEqual(sorted(layers), ["background", "foreground",
                                          "midground"])
        by_z = {"foreground": [], "midground": [], "background": []}
        for b in scene.boxes:
            z = b.center[2]
            by_z["foreground" if z > 0 else
                 "midground" if z > -5 else "background"].append(b.name)
        for layer, names in by_z.items():
            self.assertTrue(names, f"{layer} layer is empty")
        names = [b.name for b in scene.boxes]
        self.assertEqual(len(names), 20)
        for needed in ("building_left", "building_center",
                       "building_right", "lamp_post", "lamp_head",
                       "bench", "bus_stop_sign", "kerb", "crate_fg",
                       "railing_fg", "path_fg"):
            self.assertIn(needed, names)
        self.assertEqual(
            sum(1 for b in scene.boxes if b.name.startswith("window_")),
            6)

    def test_bus_option_adds_bus_box(self):
        scene = self._scene(bus={"center": (3.0, 1.0, -3.0),
                                 "size": (4.0, 2.4, 1.8),
                                 "color": (36, 84, 138),
                                 "name": "bus", "label": "01"})
        self.assertEqual(len(scene.boxes), 21)
        self.assertIn("bus", [b.name for b in scene.boxes])

    def test_unknown_package_raises(self):
        cam = PerspectiveCamera(position=(0.0, 2.0, 4.8),
                                target=(0.0, 1.2, 0.0))
        with self.assertRaises(KeyError):
            build_scene("no_such_place", cam, [])

    def test_register_scene_package(self):
        from ai_clip_studio.animation import scene_packages
        register_scene_package("test_place_v9",
                               lambda cam, chars, **kw: "ok")
        self.assertEqual(
            build_scene("test_place_v9", None, []), "ok")
        del scene_packages.SCENE_PACKAGES["test_place_v9"]
        with self.assertRaises(KeyError):
            build_scene("test_place_v9", None, [])

    def test_awning_has_stripes_struts_and_shadow(self):
        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)
        landmarks.draw_awning_2d(d, 700, 64, 600, 66, window=False)
        px = img.load()
        red = sum(1 for x in range(700, 1300, 4)
                  for y in range(64, 130, 4)
                  if px[x, y][0] > 150 and px[x, y][1] < 110
                  and px[x, y][2] < 110)
        self.assertGreater(red, 200, "awning stripes missing")
        # struts / valance: dark ink pixels inside the awning rect
        dark = sum(1 for x in range(700, 1300, 4)
                   for y in range(64, 130, 4)
                   if sum(px[x, y]) < 200)
        self.assertGreater(dark, 100, "awning struts/valance missing")
        # wall shadow band just below the valance: darker than white.
        # (The shadow rect is y0+slope+6 .. +sh_h = 106..120 for this
        # call; the valance covers 100..110, so the visible band is
        # y 111..120.)
        band = [px[x, y] for x in range(750, 1250, 8)
                for y in range(112, 119, 2)]
        mean = sum(sum(p) for p in band) / (3 * len(band))
        self.assertLess(mean, 245, "awning wall shadow missing")

    def test_street_features_at_least_twelve_including_new(self):
        img = Image.new("RGB", (W, H), (20, 30, 58))
        feats = landmarks.draw_vietnamese_street_features(
            ImageDraw.Draw(img), W, H, 892)
        self.assertGreaterEqual(len(feats), 12)
        for needed in ("hanging_lantern", "bicycle",
                       "second_utility_pole",
                       "hanging_sign_com_binh_dan",
                       "puddle_lamp_reflection",
                       "puddle_sky_reflection", "pavement_cracks",
                       "shop_sign_pho", "shop_sign_ca_phe",
                       "shop_sign_banh_mi", "motorbike"):
            self.assertIn(needed, feats)

    def test_street_features_data_driven(self):
        img0 = Image.new("RGB", (W, H), (20, 30, 58))
        feats0 = landmarks.draw_vietnamese_street_features(
            ImageDraw.Draw(img0), W, H, 892)
        # Alt data: different signs, no motorbike -- the picture
        # must change (data drives the drawing) and the feature list
        # must follow the data.
        alt = {
            "signs": [{"fx": 0.30, "text": "BÚN CHẢ", "width": 150,
                       "color": (120, 40, 40), "font": 34},
                      {"fx": 0.60, "text": "TRÀ ĐÁ", "width": 150,
                       "color": (40, 80, 40), "font": 34}],
            "vehicles": [{"kind": "bicycle", "fx": 0.72}],
            "poles": [0.10],
            "lantern": True, "wet_ground": True,
        }
        img1 = Image.new("RGB", (W, H), (20, 30, 58))
        feats1 = landmarks.draw_vietnamese_street_features(
            ImageDraw.Draw(img1), W, H, 892, data=alt)
        self.assertIn("shop_sign_bun_cha", feats1)
        self.assertNotIn("motorbike", feats1)
        self.assertIn("bicycle", feats1)
        self.assertNotEqual(list(img0.getdata()), list(img1.getdata()))
        # offset_x shifts the picture but not the feature list.
        img2 = Image.new("RGB", (W, H), (20, 30, 58))
        feats2 = landmarks.draw_vietnamese_street_features(
            ImageDraw.Draw(img2), W, H, 892, offset_x=120)
        self.assertEqual(feats2, feats0)
        self.assertNotEqual(list(img0.getdata()), list(img2.getdata()))

    def test_draw_bus_2d_door_rect(self):
        img = Image.new("RGB", (W, H), (20, 30, 58))
        out = landmarks.draw_bus_2d(ImageDraw.Draw(img), 900, 500,
                                    700, 260, route="01")
        self.assertIn("door", out)
        x0, y0, x1, y1 = out["door"]
        self.assertLess(x0, x1)
        self.assertLess(y0, y1)
        self.assertGreater(x1 - x0, 40)
        self.assertIn("bus_body", out["features"])
        self.assertIn("bus_door", out["features"])

    def test_make_character_from_data(self):
        # The Gemini hook: a structured spec dict builds a character
        # without touching CHARACTER_INSTANCES; an "instance" key
        # resolves a known name; unknown extra fields are ignored.
        from ai_clip_studio.animation.character_art import (
            make_character_from_data)
        ch = make_character_from_data({
            "template": "female", "name": "test_woman",
            "suit": "#47BD75", "body_variant": "slim", "height": 560,
            "hair_style": "bun", "extra_gemini_field": "ignored"})
        self.assertEqual(ch.name, "test_woman")
        self.assertEqual(ch.suit, "#47BD75")
        minh = make_character_from_data({"instance": "minh"})
        self.assertEqual(minh.name, "minh")
        with self.assertRaises(ValueError):
            make_character_from_data({"template": "no_such_template"})


class TestMovementPrimitivesV9(unittest.TestCase):
    def test_wave_inherits_incoming_lean(self):
        # E10 (v8): a wave after a leaning handover started with a
        # head velocity of 10.7 px/frame because wave() reset the
        # torso lean to 0 on its first frame. After the v9 fix the
        # head must start at <= 4 px/frame (measured 3.0; the
        # threshold catches any snap-back to ~10, not the small
        # residual lean-lerp motion of ~3).
        ch = make_character_instance("minh", height=560)
        standing(ch, 960, 900, facing=1, lean=0.08)
        wv = wave(ch, 1.1)
        prev_head = None
        max_start_v = 0.0
        for i in range(8):
            wv(i / 24.0)
            head = ch.joints()["head"]
            if prev_head is not None:
                v = abs(head[0] - prev_head[0]) + abs(head[1] - prev_head[1])
                max_start_v = max(max_start_v, v)
            prev_head = head
        self.assertLessEqual(max_start_v, 4.0,
                             f"wave start head velocity {max_start_v:.1f}")

    def test_detour_walk_avoids_puddle(self):
        ch = make_character_instance("minh", height=560)
        standing(ch, 200, 900, facing=1)
        puddle = {"x": 500, "y": 900, "rx": 90, "ry": 13}
        fn = detour_walk(ch, 200, 800, 2.0, 900, puddle)
        self.assertGreater(fn.bulge, 0)
        min_nd = 1e9
        for i in range(49):
            fn(i / 24.0)
            joints = ch.joints()
            for key in ("foot_l", "foot_r"):
                x, y = joints[key]
                nd = math.hypot((x - puddle["x"]) / puddle["rx"],
                                (y - puddle["y"]) / puddle["ry"])
                min_nd = min(min_nd, nd)
        self.assertGreater(min_nd, 1.0,
                           "a foot entered the puddle ellipse")
        # A puddle already off the path (foreground, below the ground
        # line) needs no detour: bulge 0, plain walk.
        fn2 = detour_walk(ch, 200, 800, 2.0, 900,
                          {"x": 500, "y": 960, "rx": 90, "ry": 13})
        self.assertEqual(fn2.bulge, 0.0)

    def test_detour_walk_avoids_puddle_at_scene_height(self):
        # v9.1 regression: the first detour passed at H=560 by luck
        # (small stride) but FAILED at the scene-test height H=783
        # (min foot-ellipse distance 0.76 -- a foot INSIDE the
        # puddle). The bump is keyed to the root's x, but the feet
        # extend +/- half a stride around the root; the flat top must
        # span the obstacle PLUS the foot spread. This test uses the
        # exact scene-test geometry (H=783, walk 125->620, puddle at
        # x=350 on the ground line).
        ch = make_character_instance("minh", height=783)
        standing(ch, 125, 892, facing=1)
        puddle = {"x": 350, "y": 892, "rx": 90, "ry": 13}
        fn = detour_walk(ch, 125, 620, 3.0, 892, puddle)
        self.assertGreater(fn.bulge, 0)
        min_nd = 1e9
        for i in range(73):
            fn(i / 24.0)
            joints = ch.joints()
            for key in ("foot_l", "foot_r"):
                x, y = joints[key]
                nd = math.hypot((x - puddle["x"]) / puddle["rx"],
                                (y - puddle["y"]) / puddle["ry"])
                min_nd = min(min_nd, nd)
        self.assertGreater(min_nd, 1.0,
                           f"a foot entered the puddle ellipse (min {min_nd:.2f})")

    def test_detour_walk_v9_camera_start(self):
        # v9.2 regression: the v9 camera shift (dx=-0.15) moved the
        # scene-test start sx(-3.0) from 125 to 167, so Minh's
        # starting front foot (167+98=265) sat ON the puddle's left
        # edge at x=350 (M1 measured 0.95 at frame 0 of the real
        # render -- the only failing frame; the crossing itself was
        # clean at 1.98). The scene-test puddle moved to x=400; with
        # the v9 start (167) the min distance over the WHOLE detour
        # including frame 0 must be > 1.0.
        ch = make_character_instance("minh", height=783)
        standing(ch, 167, 892, facing=1)
        puddle = {"x": 400, "y": 892, "rx": 90, "ry": 13}
        fn = detour_walk(ch, 167, 620, 3.0, 892, puddle)
        self.assertGreater(fn.bulge, 0)
        min_nd = 1e9
        for i in range(73):
            fn(i / 24.0)
            joints = ch.joints()
            for key in ("foot_l", "foot_r"):
                x, y = joints[key]
                nd = math.hypot((x - puddle["x"]) / puddle["rx"],
                                (y - puddle["y"]) / puddle["ry"])
                min_nd = min(min_nd, nd)
        self.assertGreater(min_nd, 1.0,
                           f"a foot entered the puddle ellipse (min {min_nd:.2f})")

    def test_board_vehicle_steps_up_and_enters(self):
        ch = make_character_instance("lan", height=560)
        standing(ch, 300, 900, facing=1)
        door = {"x": 700, "y": 640, "width": 110, "height": 260}
        fn = board_vehicle(ch, 300, door, 2.0, 900)
        step_ys = []
        for i in range(49):
            t = i / 24.0
            fn(t)
            joints = ch.joints()
            if 1.0 <= t < 1.4:
                step_ys.append(joints["foot_l"][1])
                step_ys.append(joints["foot_r"][1])
        # Feet plant on the step (ground_y - step_height) by the end
        # of the step phase.
        self.assertTrue(step_ys)
        self.assertAlmostEqual(min(step_ys), 900 - fn.step_height,
                               delta=3.0)
        # Ends inside the doorway.
        self.assertGreaterEqual(ch.pose["root_x"], door["x"])
        self.assertLessEqual(ch.pose["root_x"],
                             door["x"] + door["width"])


if __name__ == "__main__":
    unittest.main()
