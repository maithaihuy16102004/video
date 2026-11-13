"""W1 shadow cap: contact shadows never outgrow their objects.

Visual recovery wiring: box shadows in renderer25d/render.py and the
character shadow in product_renderer.py use the ratio-capped contract
from ai_clip_studio.lighting (width <= 1.3x footprint, height <= 0.31x
width, depth-capped, alpha <= 0.55). These tests assert the contract
holds on real rendered pixels, not just on the spec dict.
"""

import unittest

from PIL import Image

from ai_clip_studio.renderer25d.camera import PerspectiveCamera
from ai_clip_studio.renderer25d.lighting import contact_shadow
from ai_clip_studio.renderer25d.render import (
    _base_corners, _draw_contact_shadow, _projected_footprint,
    render_frame)
from ai_clip_studio.renderer25d.scene import Box3D, Scene25D


def _cam():
    return PerspectiveCamera(position=(0.0, 2.4, 12.0),
                             target=(0.0, 1.5, 0.0),
                             fov_deg=46.0, aspect=16 / 9)


def _dark_bbox(img):
    """Bounding box of pixels with alpha > 0 on an RGBA image."""
    alpha = img.getchannel("A")
    bbox = alpha.getbbox()
    return bbox


class TestShadowCap(unittest.TestCase):
    def _draw(self, box, capped):
        cam = _cam()
        scene = Scene25D(camera=cam)
        img = Image.new("RGBA", (960, 540), (0, 0, 0, 0))
        foot = _projected_footprint(cam, _base_corners(box), 960, 540)
        self.assertIsNotNone(foot, "test box must be fully visible")
        _draw_contact_shadow(
            img, scene, cam, box.ground_pos(),
            box.height_above_ground(), box.base_radius(),
            horizon_y=None,
            footprint_half_width_px=foot[0] if capped else None,
            footprint_half_depth_px=foot[1] if capped else None)
        return img, foot

    def test_wide_wall_shadow_is_a_thin_strip(self):
        wall = Box3D(center=(0.0, 1.5, 0.0), size=(10.6, 3.0, 0.6),
                     color=(200, 200, 200), name="wall")
        img, _ = self._draw(wall, capped=True)
        bbox = _dark_bbox(img)
        self.assertIsNotNone(bbox, "capped wall shadow must still draw")
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        # Height <= 0.31 x width + blur slack (blur radius 2 at height 0).
        self.assertLessEqual(h, 0.31 * w + 20.0)

    def test_capped_wall_is_much_thinner_than_legacy(self):
        wall = Box3D(center=(0.0, 1.5, 0.0), size=(10.6, 3.0, 0.6),
                     color=(200, 200, 200), name="wall")
        capped_img, _ = self._draw(wall, capped=True)
        legacy_img, _ = self._draw(wall, capped=False)
        ch = _dark_bbox(capped_img)[3] - _dark_bbox(capped_img)[1]
        lh = _dark_bbox(legacy_img)[3] - _dark_bbox(legacy_img)[1]
        self.assertLess(ch, lh * 0.5)

    def test_small_crate_shadow_within_ratios(self):
        crate = Box3D(center=(0.0, 0.3, 0.0), size=(0.6, 0.6, 0.6),
                      color=(150, 100, 50), name="crate")
        img, foot = self._draw(crate, capped=True)
        bbox = _dark_bbox(img)
        self.assertIsNotNone(bbox)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        self.assertLessEqual(w, 1.3 * 2 * foot[0] + 20.0)
        self.assertLessEqual(h, 0.31 * w + 20.0)

    def test_legacy_path_matches_contact_shadow_geometry(self):
        box = Box3D(center=(1.0, 0.5, -1.0), size=(1.0, 1.0, 1.0),
                    color=(100, 100, 100), name="box")
        cam = _cam()
        scene = Scene25D(camera=cam)
        img = Image.new("RGBA", (960, 540), (0, 0, 0, 0))
        _draw_contact_shadow(img, scene, cam, box.ground_pos(),
                             box.height_above_ground(), box.base_radius())
        bbox = _dark_bbox(img)
        self.assertIsNotNone(bbox)
        sh = contact_shadow(box.ground_pos(), box.height_above_ground(),
                            box.base_radius(), scene.lights.key)
        _, _, pscale, _ = cam.project((sh["center"][0], 0.0,
                                       sh["center"][1]), 960, 540)
        exp_w = 2 * sh["radius_x"] * pscale
        exp_h = 2 * sh["radius_z"] * pscale
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        # Blur (radius 2) grows each side by a few px; allow slack.
        self.assertAlmostEqual(w, exp_w, delta=20.0)
        self.assertAlmostEqual(h, exp_h, delta=20.0)

    def test_horizon_clip_erases_shadow_above_horizon(self):
        box = Box3D(center=(0.0, 1.0, 0.0), size=(2.0, 2.0, 2.0),
                    color=(100, 100, 100), name="box")
        cam = _cam()
        scene = Scene25D(camera=cam)
        sh = contact_shadow(box.ground_pos(), box.height_above_ground(),
                            box.base_radius(), scene.lights.key)
        _, cy, _, _ = cam.project((sh["center"][0], 0.0,
                                   sh["center"][1]), 960, 540)
        img = Image.new("RGBA", (960, 540), (0, 0, 0, 0))
        _draw_contact_shadow(img, scene, cam, box.ground_pos(),
                             box.height_above_ground(), box.base_radius(),
                             horizon_y=cy - 5)
        alpha = img.getchannel("A")
        above = [alpha.getpixel((x, y))
                 for y in range(0, int(cy) - 5) for x in range(0, 960, 37)]
        self.assertTrue(all(v == 0 for v in above))
        below = [alpha.getpixel((x, y))
                 for y in range(int(cy), 540) for x in range(0, 960, 37)]
        self.assertTrue(any(v > 0 for v in below))

    def test_projected_footprint_none_behind_camera(self):
        cam = _cam()
        self.assertIsNone(_projected_footprint(
            cam, [(0.0, 0.0, 13.0), (1.0, 0.0, 13.0)], 960, 540))
        foot = _projected_footprint(
            cam, [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                  (0.0, 0.0, 1.0), (1.0, 0.0, 1.0)], 960, 540)
        self.assertIsNotNone(foot)
        self.assertGreater(foot[0], 0)
        self.assertGreater(foot[1], 0)

    def test_render_frame_day_sky_stays_bright_with_cap(self):
        cam = _cam()
        wall = Box3D(center=(0.0, 1.5, 0.0), size=(10.6, 3.0, 0.6),
                     color=(200, 190, 170), name="wall")
        scene = Scene25D(boxes=[wall], camera=cam,
                         sky_top=(140, 183, 221), sky_bottom=(200, 220, 240),
                         ground_color=(150, 140, 120))
        img = render_frame(scene, 480, 270)
        self.assertEqual(img.size, (480, 270))
        px = img.load()
        top = [px[x, y] for y in range(0, 40) for x in range(0, 480, 13)]
        mean_lum = sum(sum(p) / 3 for p in top) / len(top)
        self.assertGreater(mean_lum, 100.0)


class TestCharacterShadowFootprint(unittest.TestCase):
    def test_footprint_from_live_joints(self):
        from ai_clip_studio.animation.character_art import make_character
        from ai_clip_studio.animation.primitives import standing
        from ai_clip_studio.product_renderer import (
            _character_shadow_footprint)
        ch = make_character()
        standing(ch, 960, 900, facing=1)
        half_w, half_d = _character_shadow_footprint(ch)
        joints = ch.joints()
        span = abs(joints["foot_r"][0] - joints["foot_l"][0])
        self.assertAlmostEqual(half_w, span / 2.0 + 0.06 * ch.H, places=6)
        self.assertAlmostEqual(half_d, 0.025 * ch.H, places=6)
        self.assertGreater(half_w, 0)
        self.assertGreater(half_d, 0)


if __name__ == "__main__":
    unittest.main()
