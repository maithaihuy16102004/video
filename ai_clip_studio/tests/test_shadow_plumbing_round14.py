"""Round 14: shadow plumbing (R13-D1 root cause) + cast-quad layer.

R13-D1: _build_frame passed bg_scene.lights.key -- the Scene25D
DEFAULT rig key (elevation 0.92, spread 0.087) -- so every
character cast spec returned None (154/154 logged calls). The
key is now the palette rig's key. Element quads additionally
move to their own blur-2 layer with a floored alpha, because
the shared blur-4 contact layer erased them on delivered
frames.
"""
import unittest

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import (
    build_environment,
    render_environment,
)
from ai_clip_studio.lighting import (
    cast_shadow_spec,
    light_for,
    rig_for,
)

CAM = viewpoint_for_shot("establishing", elevation_deg=15.0)


class TestShadowPlumbingRound14(unittest.TestCase):
    def test_palette_key_is_not_the_steep_default(self):
        # The default LightRig key has elevation ~0.92; the
        # palette morning/afternoon/dusk keys are low suns.
        for tod in ("morning", "afternoon", "dusk"):
            key = rig_for(light_for(tod, "warm")).key
            self.assertLess(key.elevation_factor(), 0.80, tod)

    def test_morning_key_yields_character_cast_spec(self):
        key = rig_for(light_for("morning", "warm")).key
        spec = cast_shadow_spec((-1.6, 0.0, 0.5), 2.81, 0.52,
                                key, CAM, (1920, 1080))
        self.assertIsNotNone(spec)
        self.assertGreater(spec["length_world"], 0.25 * 2.81)

    def test_element_cast_quad_darkens_ground(self):
        loc = {"name": "Test field", "setting": "open field"}
        pkg = build_environment(loc, time_of_day="morning",
                                style={"mood": "warm"})
        box = {"id": "test_pole", "kind": "pole", "layer": "MG",
               "geometry": "box", "center": (0.0, 1.5, -4.0),
               "size": (0.4, 3.0, 0.4), "color": (90, 80, 70),
               "material": "wood"}
        pkg["elements"] = [box]
        pkg["layers"] = {"BG": [], "MG": ["test_pole"], "FG": []}
        img = render_environment(pkg, CAM)
        key = rig_for(pkg["light"]).key
        spec = cast_shadow_spec((0.0, 0.0, -4.0), 3.0, 0.4,
                                key, CAM, (1920, 1080))
        self.assertIsNotNone(spec)
        pts = spec["polygon_px"]
        cx = sum(p[0] for p in pts) / 4.0
        cy = sum(p[1] for p in pts) / 4.0
        # Same package without the box: the bare ground at the
        # quad centroid must be brighter than the shadowed one.
        pkg2 = dict(pkg)
        pkg2["elements"] = []
        pkg2["layers"] = {"BG": [], "MG": [], "FG": []}
        bare = render_environment(pkg2, CAM)
        lum = lambda im: sum(im.getpixel((int(cx), int(cy)))) / 3.0
        self.assertLess(lum(img), lum(bare) - 10.0)


if __name__ == "__main__":
    unittest.main()
