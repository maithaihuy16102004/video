"""Unit tests for ai_clip_studio.lighting (stdlib unittest).

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/agent/
"""
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.lighting import (
    DAY_LUMINANCE_FLOOR,
    SHADOW_ALPHA_MAX,
    SHADOW_HEIGHT_RATIO,
    SHADOW_WIDTH_RATIO_MAX,
    TIME_OF_DAY_PALETTES,
    check_day_brightness,
    light_for,
    measure_mean_luminance,
    normalize_mood,
    normalize_time_of_day,
    rig_for,
    shadow_ellipse_spec,
    sky_band_luminance,
)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera
from ai_clip_studio.renderer25d.lighting import DirectionalLight


def _solid(rgb, size=(64, 48)):
    return Image.new("RGB", size, rgb)


class TestNormalization(unittest.TestCase):
    def test_time_of_day_aliases(self):
        self.assertEqual(normalize_time_of_day("morning"), "day")
        self.assertEqual(normalize_time_of_day("sunset"), "dusk")
        self.assertEqual(normalize_time_of_day("midnight"), "night")
        self.assertEqual(normalize_time_of_day("indoor"), "interior")
        self.assertEqual(normalize_time_of_day("nonsense"), "day")
        self.assertEqual(normalize_time_of_day(None), "day")
        self.assertEqual(normalize_time_of_day(""), "day")

    def test_mood(self):
        self.assertEqual(normalize_mood("cold"), "cold")
        self.assertEqual(normalize_mood("weird"), "warm")
        self.assertEqual(normalize_mood(None), "warm")


class TestPalettes(unittest.TestCase):
    def test_all_combinations_present(self):
        for tod in ("day", "dusk", "night", "interior"):
            for mood in ("warm", "cold", "neutral"):
                self.assertIn((tod, mood), TIME_OF_DAY_PALETTES)

    def test_day_palettes_are_bright(self):
        # A day sky must never be dark: sky_top luminance > 120.
        for mood in ("warm", "cold", "neutral"):
            spec = TIME_OF_DAY_PALETTES[("day", mood)]
            top = spec["sky_top"]
            lum = 0.299 * top[0] + 0.587 * top[1] + 0.114 * top[2]
            self.assertGreater(lum, 120, f"day/{mood} sky too dark: {top}")

    def test_light_for_rain_forces_cold_not_night(self):
        spec = light_for("day", "warm", weather="Cold rain")
        self.assertEqual(spec["time_of_day"], "day")
        self.assertEqual(spec["mood"], "cold")
        self.assertGreater(spec["ambient"], 0.5)

    def test_light_for_json_safe_and_rig_builds(self):
        spec = light_for("dusk", "warm")
        import json
        json.dumps(spec)
        rig = rig_for(spec)
        self.assertAlmostEqual(rig.ambient, spec["ambient"])
        self.assertGreater(rig.key.intensity, 0)


class TestShadowCap(unittest.TestCase):
    def setUp(self):
        self.cam = PerspectiveCamera(
            position=(0.0, 2.0, 4.8), target=(0.0, 1.2, 0.0),
            fov_deg=46.0, aspect=16 / 9)
        self.light = DirectionalLight((0.35, -1.0, -0.3), 1.0)

    def test_shadow_capped_to_footprint(self):
        spec = shadow_ellipse_spec(
            (0.0, 0.0, -5.0), 0.0, 3.0, self.light, self.cam,
            (1920, 1080), footprint_half_width_px=100.0)
        self.assertIsNotNone(spec)
        self.assertLessEqual(spec["rx_px"],
                             SHADOW_WIDTH_RATIO_MAX * 100.0)
        self.assertLessEqual(spec["ry_px"],
                             SHADOW_HEIGHT_RATIO * 2.0 * spec["rx_px"])
        self.assertLessEqual(spec["alpha"], SHADOW_ALPHA_MAX)
        self.assertTrue(spec["capped"])  # base_radius 3.0 would overflow

    def test_small_object_shadow_not_capped(self):
        spec = shadow_ellipse_spec(
            (0.0, 0.0, -5.0), 0.0, 0.3, self.light, self.cam,
            (1920, 1080), footprint_half_width_px=100.0)
        self.assertIsNotNone(spec)
        self.assertFalse(spec["capped"])

    def test_ground_slab_gets_no_shadow(self):
        spec = shadow_ellipse_spec(
            (0.0, 0.0, -5.0), 0.0, 7.0, self.light, self.cam,
            (1920, 1080), footprint_half_width_px=500.0,
            is_ground_slab=True)
        self.assertIsNone(spec)

    def test_lifted_object_shadow_lighter_and_offset(self):
        resting = shadow_ellipse_spec(
            (0.0, 0.0, -5.0), 0.0, 0.5, self.light, self.cam,
            (1920, 1080), footprint_half_width_px=100.0)
        lifted = shadow_ellipse_spec(
            (0.0, 0.0, -5.0), 1.5, 0.5, self.light, self.cam,
            (1920, 1080), footprint_half_width_px=100.0)
        self.assertLess(lifted["alpha"], resting["alpha"])
        self.assertGreater(lifted["offset_world"], 0.0)

    def test_wide_wall_shadow_is_a_thin_strip(self):
        # A 10-unit-wide, 0.6-deep wall: without the depth cap the
        # single-radius geometry makes a giant radial blob; with
        # the depth cap the shadow stays a thin strip along the base.
        spec = shadow_ellipse_spec(
            (0.0, 0.0, -8.0), 0.0, 5.5, self.light, self.cam,
            (1920, 1080), footprint_half_width_px=400.0,
            footprint_half_depth_px=25.0)
        self.assertIsNotNone(spec)
        self.assertLessEqual(spec["ry_px"], 1.3 * 25.0)
        self.assertLess(spec["ry_px"], spec["rx_px"] * 0.2)


class TestMeasurement(unittest.TestCase):
    def test_mean_luminance_solid(self):
        self.assertAlmostEqual(measure_mean_luminance(_solid((128, 128, 128))),
                               128.0, places=1)
        self.assertAlmostEqual(measure_mean_luminance(_solid((0, 0, 0))),
                               0.0, places=1)

    def test_sky_band(self):
        img = Image.new("RGB", (64, 48), (0, 0, 0))
        img.paste(_solid((200, 200, 200), (64, 10)), (0, 0))
        self.assertAlmostEqual(sky_band_luminance(img, band_h=10),
                               200.0, places=1)

    def test_check_day_brightness(self):
        bright = check_day_brightness(_solid((180, 180, 180)))
        self.assertTrue(bright["ok"])
        self.assertEqual(bright["floor"], DAY_LUMINANCE_FLOOR)
        dark = check_day_brightness(_solid((28, 37, 45)))
        self.assertFalse(dark["ok"])  # the Stage 3 dark-daytime signature


if __name__ == "__main__":
    unittest.main()
