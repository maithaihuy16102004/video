"""Unit tests for the 2.5D fallback renderer (perspective, parallax,
contact shadows, light falloff). Pure stdlib unittest + PIL.

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/agent/
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.renderer25d.camera import PerspectiveCamera
from ai_clip_studio.renderer25d.lighting import (
    DirectionalLight, LightRig, PointLight, contact_shadow, shade)
from ai_clip_studio.renderer25d.render import render_frame
from ai_clip_studio.renderer25d.scene import (
    Box3D, CharacterAnchor, Scene25D)


def _cam():
    return PerspectiveCamera(position=(0.0, 2.4, 12.0),
                             target=(0.0, 1.5, 0.0),
                             fov_deg=46.0, aspect=16 / 9)


class TestPerspectiveProjection(unittest.TestCase):
    def test_same_object_farther_is_smaller_and_higher(self):
        cam = _cam()
        near = (0.0, 1.0, 0.0)     # depth ~12
        far = (0.0, 1.0, -10.0)    # depth ~22
        xn, yn, sn, _ = cam.project(near, 1920, 1080)
        xf, yf, sf, _ = cam.project(far, 1920, 1080)
        self.assertLess(sf, sn)          # farther -> smaller
        self.assertAlmostEqual(sf / sn, 12.0 / 22.0, places=2)
        self.assertLess(yf, yn)          # farther -> closer to horizon (up)
        self.assertAlmostEqual(xn, xf, places=6)  # same x: centred

    def test_project_size_scales_with_inverse_depth(self):
        cam = _cam()
        near_pt, far_pt = (0.0, 0.0, 0.0), (0.0, 0.0, -12.0)
        s_near = cam.project_size(1.7, near_pt, 1080)
        s_far = cam.project_size(1.7, far_pt, 1080)
        self.assertGreater(s_near, s_far)
        # size ratio == inverse depth ratio (depth measured along the
        # camera forward axis, not raw z distance)
        expected = cam.depth_of(far_pt) / cam.depth_of(near_pt)
        self.assertAlmostEqual(s_near / s_far, expected, places=6)

    def test_point_behind_camera_is_not_visible(self):
        cam = _cam()
        _, _, _, vis = cam.project((0.0, 1.5, 13.0), 1920, 1080)
        self.assertFalse(vis)
        _, _, _, vis2 = cam.project((0.0, 1.5, 0.0), 1920, 1080)
        self.assertTrue(vis2)

    def test_camera_keyframe_interpolation(self):
        a, b = _cam(), _cam().moved(dpos=(3.0, 0.0, 0.0))
        mid = PerspectiveCamera.interpolate(a, b, 0.5)
        self.assertAlmostEqual(mid.position[0], 1.5, places=6)
        self.assertAlmostEqual(mid.position[2], 12.0, places=6)
        end = PerspectiveCamera.interpolate(a, b, 1.0)
        self.assertAlmostEqual(end.position[0], 3.0, places=6)


class TestParallax(unittest.TestCase):
    def test_near_layer_moves_faster_than_far_layer(self):
        cam = _cam()
        moved = cam.moved(dpos=(1.0, 0.0, 0.0), dtarget=(1.0, 0.0, 0.0))
        near = (0.0, 1.0, 6.0)    # depth 6 from camera
        far = (0.0, 1.0, -8.0)    # depth 20 from camera
        for point, name in ((near, "near"), (far, "far")):
            x0, _, _, _ = cam.project(point, 1920, 1080)
            x1, _, _, _ = moved.project(point, 1920, 1080)
            shift = abs(x1 - x0)
            if name == "near":
                near_shift = shift
            else:
                far_shift = shift
        self.assertGreater(near_shift, far_shift)
        # ratio follows 1/depth: 20/6 ~= 3.33
        self.assertAlmostEqual(near_shift / far_shift, 20.0 / 6.0, places=1)

    def test_parallax_shift_matches_projection(self):
        cam = _cam()
        point = (0.0, 1.0, 0.0)
        shift = cam.parallax_shift_px(point, 1.0, 1080)
        _, _, scale, _ = cam.project(point, 1, 1080)
        self.assertAlmostEqual(abs(shift), scale * 1.0, places=6)


class TestLightingAndShadow(unittest.TestCase):
    def test_point_light_falls_off_with_distance(self):
        light = PointLight((0.0, 3.0, 0.0), intensity=1.0)
        near = light.irradiance((0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
        far = light.irradiance((0.0, 0.0, 9.0), (0.0, 1.0, 0.0))
        self.assertGreater(near, far)

    def test_face_turned_away_from_directional_light_is_dark(self):
        sun = DirectionalLight((0.0, -1.0, -1.0), intensity=1.0)
        facing = sun.irradiance((0, 0, 0), (0.0, 0.0, 1.0))
        away = sun.irradiance((0, 0, 0), (0.0, 0.0, -1.0))
        self.assertGreater(facing, 0.5)
        self.assertEqual(away, 0.0)

    def test_shade_darkens_with_low_irradiance(self):
        self.assertEqual(shade((200, 100, 50), 0.5), (100, 50, 25))
        self.assertEqual(shade((200, 100, 50), 0.0), (0, 0, 0))

    def test_contact_shadow_grows_lighter_and_further_with_height(self):
        sun = DirectionalLight((0.5, -1.0, 0.2), intensity=1.0)
        ground = contact_shadow((0.0, 0.0, 0.0), 0.0, 0.5, sun)
        lifted = contact_shadow((0.0, 0.0, 0.0), 2.0, 0.5, sun)
        self.assertEqual(ground["offset_world"], 0.0)
        self.assertGreater(lifted["offset_world"], 0.0)
        self.assertGreater(lifted["radius_x"], ground["radius_x"])
        self.assertLess(lifted["alpha"], ground["alpha"])
        # shadow is cast along the light's ground direction (+x here)
        self.assertGreater(lifted["center"][0], 0.0)

    def test_shadow_moves_when_object_moves(self):
        sun = DirectionalLight((0.5, -1.0, 0.2), intensity=1.0)
        a = contact_shadow((0.0, 0.0, 0.0), 0.0, 0.5, sun)
        b = contact_shadow((3.0, 0.0, 0.0), 0.0, 0.5, sun)
        self.assertAlmostEqual(b["center"][0] - a["center"][0], 3.0, places=6)
        self.assertAlmostEqual(b["center"][1] - a["center"][1], 0.0, places=6)


class TestSceneAndRender(unittest.TestCase):
    def _scene(self):
        return Scene25D(
            boxes=[Box3D(center=(-2.0, 1.0, -4.0), size=(2.0, 2.0, 2.0),
                         color=(150, 120, 90), name="near_house"),
                   Box3D(center=(3.0, 2.0, -14.0), size=(4.0, 4.0, 4.0),
                         color=(90, 110, 140), name="far_tower")],
            characters=[CharacterAnchor(world_pos=(0.5, 0.0, -2.0),
                                        height=1.7, label="walker")],
            camera=_cam())

    def test_depth_layers_bucket_by_camera_depth(self):
        layers = self._scene().depth_layers()
        self.assertEqual(set(layers), {"background", "midground", "foreground"})
        # the far tower (depth ~26) must be in a farther layer than the
        # walker (depth ~14)
        def layer_of(name):
            for layer, items in layers.items():
                for _, obj, _ in items:
                    if getattr(obj, "name", getattr(obj, "label", "")) == name:
                        return layer
            return None
        order = {"foreground": 0, "midground": 1, "background": 2}
        self.assertLess(order[layer_of("walker")], order[layer_of("far_tower")])

    def test_render_frame_produces_varied_nonblank_image(self):
        img = render_frame(self._scene(), 960, 540)
        self.assertEqual(img.size, (960, 540))
        colours = img.getcolors(maxcolors=1000000)
        self.assertTrue(colours and len(colours) > 50,
                        "frame looks blank / single-colour")

    def test_render_parallax_visible_between_camera_positions(self):
        # same scene from two camera x positions: the near box's screen
        # centre must move more than the far box's.
        scene = self._scene()
        centres = []
        for dx in (0.0, 1.5):
            cam = scene.camera.moved(dpos=(dx, 0.0, 0.0),
                                     dtarget=(dx, 0.0, 0.0))
            near = cam.project((-2.0, 1.0, -4.0), 960, 540)[0]
            far = cam.project((3.0, 2.0, -14.0), 960, 540)[0]
            centres.append((near, far))
        near_shift = abs(centres[1][0] - centres[0][0])
        far_shift = abs(centres[1][1] - centres[0][1])
        self.assertGreater(near_shift, far_shift)

    def test_light_rig_shades_faces_differently(self):
        # top face (normal +y, sun from above) is brighter than a side
        # face turned away: visible as different pixel colours on the box.
        rig = LightRig(ambient=0.2,
                       key=DirectionalLight((0.0, -1.0, 0.0), 1.0))
        top = rig.irradiance((0, 1, 0), (0.0, 1.0, 0.0))
        side = rig.irradiance((0, 1, 0), (1.0, 0.0, 0.0))
        self.assertGreater(top, side)


class TestPaintersOrderFarthestCorner(unittest.TestCase):
    """Stage 3 regression: painter's order must use the FARTHEST
    corner, not the box centre. The map paper (centre depth 9.634)
    sits BEHIND its region patches (centre depth 9.650) but is much
    wider, so centre-based ordering painted the paper AFTER the
    region and covered it (the 'Anh' region vanished). Farthest-
    corner depths (paper 10.119 > region 9.823) restore the order."""

    def _map_scene(self, with_region):
        paper = Box3D(center=(0.0, 2.2, -5.0), size=(10.4, 4.7, 0.2),
                      color=(238, 226, 190), name="map_paper")
        boxes = [paper]
        if with_region:
            boxes.append(Box3D(center=(3.1, 1.3, -4.85),
                               size=(2.8, 1.4, 0.1),
                               color=(150, 165, 155),
                               name="map_region_6"))
        cam = PerspectiveCamera(position=(0.0, 2.0, 4.8),
                                target=(0.0, 1.2, 0.0),
                                fov_deg=46.0, aspect=16 / 9)
        scene = Scene25D(boxes=boxes, characters=[], camera=cam,
                         sky_top=(222, 214, 180),
                         sky_bottom=(235, 228, 200),
                         ground_color=(105, 82, 58),
                         ground_extent=30.0)
        return scene, cam, paper, boxes[-1]

    def test_paper_sorts_behind_region(self):
        from ai_clip_studio.renderer25d.render import _paint_depth
        _scene, cam, paper, region = self._map_scene(True)
        self.assertGreater(_paint_depth(cam, "box", paper),
                           _paint_depth(cam, "box", region))

    def test_region_visible_over_paper(self):
        scene_with, cam, _p, _r = self._map_scene(True)
        scene_without, _c, _p2, _r2 = self._map_scene(False)
        px, py, _s, _vis = cam.project((3.1, 1.3, -4.85), 960, 540)
        with_img = render_frame(scene_with, 960, 540)
        without_img = render_frame(scene_without, 960, 540)
        c_with = with_img.getpixel((int(px), int(py)))
        c_without = without_img.getpixel((int(px), int(py)))
        self.assertNotEqual(c_with, c_without,
                            "region centre must differ from bare paper")


if __name__ == "__main__":
    unittest.main()
