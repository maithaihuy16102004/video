"""Round 12 (R12-2): stronger time-of-day palettes. Dusk skies
strengthened toward pink-orange, and point-light pools tighten
as the ambient falls so the tod bake contrast survives in dim
rooms instead of being washed out by the lamp.
"""

import unittest

from ai_clip_studio.environment_v2 import build_environment
from ai_clip_studio.lighting import TIME_OF_DAY_PALETTES, light_for


def _rb(rgb):
    return rgb[0] / rgb[2]


class TestDuskPaletteStrength(unittest.TestCase):
    def test_sky_gradient_ordering(self):
        # Horizon warmth must order: midday < afternoon < dusk.
        mid = _rb(TIME_OF_DAY_PALETTES[("midday", "warm")]
                  ["sky_bottom"])
        aft = _rb(TIME_OF_DAY_PALETTES[("afternoon", "warm")]
                  ["sky_bottom"])
        dusk = _rb(TIME_OF_DAY_PALETTES[("dusk", "warm")]
                   ["sky_bottom"])
        self.assertLess(mid, aft)
        self.assertLess(aft, dusk)
        self.assertGreater(dusk, 2.2)
        # Dusk zenith reads purple-blue, clearly darker than day.
        self.assertLess(
            sum(TIME_OF_DAY_PALETTES[("dusk", "warm")]["sky_top"]),
            sum(TIME_OF_DAY_PALETTES[("midday", "warm")]["sky_top"]))

    def test_room_window_glass_warmer_at_dusk(self):
        # The R11 glass blend (0.65 toward sky_bottom) must carry
        # the stronger dusk palette: dusk glass R/B far above
        # midday glass.
        def glass(tod):
            light = light_for(tod, "warm")
            top = light["sky_top"]
            bot = light["sky_bottom"]
            mixed = tuple(top[i] * 0.35 + bot[i] * 0.65
                          for i in range(3))
            return _rb(mixed)
        self.assertGreater(glass("dusk"), glass("midday") + 0.8)


class TestTodPointLightFalloff(unittest.TestCase):
    def _lamp(self, tod):
        traits = {"id": "LOC_TEST", "location": "phòng khách",
                  "fields": {"LOCATION": "trong nhà"}}
        pkg = build_environment(traits, time_of_day=tod,
                                style={"mood": "warm"})
        self.assertEqual(pkg["archetype"], "INTERIOR_GENERIC")
        return pkg["point_lights"][0]

    def test_falloff_tightens_as_ambient_falls(self):
        mid = self._lamp("midday")
        dusk = self._lamp("dusk")
        night = self._lamp("night")
        self.assertLess(mid["falloff_k"], dusk["falloff_k"])
        self.assertLess(dusk["falloff_k"], night["falloff_k"])
        # Position/intensity/colour untouched by the scaling.
        for spec in (mid, dusk, night):
            self.assertEqual(spec["position"], (-2.5, 1.85, -2.0))
            self.assertEqual(spec["intensity"], 0.8)
            self.assertEqual(spec["color"], (255, 220, 140))

    def test_archetype_spec_not_mutated(self):
        from ai_clip_studio.environment_v2 import ARCHETYPES
        before = dict(
            ARCHETYPES["INTERIOR_GENERIC"]["point_lights"][0])
        self._lamp("night")
        self.assertEqual(
            ARCHETYPES["INTERIOR_GENERIC"]["point_lights"][0],
            before)


class TestGlassUnshaded(unittest.TestCase):
    def test_glass_face_keeps_element_colour(self):
        import numpy as np
        from PIL import Image
        from ai_clip_studio.environment_v2 import (
            _el, _projected_bbox, render_environment)
        from ai_clip_studio.renderer25d.camera import (
            PerspectiveCamera)
        glass_colour = (182, 126, 108)
        pkg = {
            "light": light_for("dusk", "warm"),
            "elements": [
                _el("win", "window", "BG", "box",
                    (0.0, 1.5, -3.0), (1.0, 1.0, 0.2),
                    glass_colour, "glass"),
                _el("wall", "wall", "BG", "box",
                    (2.5, 1.5, -3.0), (1.0, 1.0, 0.2),
                    (200, 180, 150), "plaster"),
            ],
            "ground": {"kind": "neutral", "color": (120, 110, 96)},
            "point_lights": [],
        }
        cam = PerspectiveCamera(position=(0, 2.0, 4.8),
                                target=(0, 1.2, -3.0), fov_deg=46,
                                aspect=1920 / 1080)
        img = render_environment(pkg, cam, size=(960, 540),
                                 textures=False)
        arr = np.asarray(img.convert("RGB")).astype(int)
        for el, expect_shaded in ((pkg["elements"][0], False),
                                  (pkg["elements"][1], True)):
            x0, y0, x1, y1 = _projected_bbox(el, cam, 960, 540)
            cx, cy = int((x0 + x1) / 2), int((y0 + y1) / 2)
            px = tuple(arr[cy, cx])
            if expect_shaded:
                self.assertNotEqual(px, tuple(el["color"]))
            else:
                for got, want in zip(px, el["color"]):
                    self.assertAlmostEqual(got, want, delta=2)


if __name__ == "__main__":
    unittest.main()
