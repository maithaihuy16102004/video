"""Round 14: selective time-of-day -- the sky blend must use the
OUTSIDE sky, never an interior override backdrop.

R13 defect: the facade/roof/ground bake ran after interior
overrides replaced the spec's sky_bottom with a dark warm
backdrop, so the R13 sky blend fired at 30% toward dark-warm
at EVERY hour (midday forge wall +0.129 R/B), keeping the
cave-forge gap flat. The bake now passes the outside sky
explicitly; the plain-spec GREY bake is unchanged.
"""
import unittest

from ai_clip_studio.lighting import (
    interior_sky_response,
    light_for,
    tod_surface_response,
)

GREY = (128, 128, 128)
STONE = (110, 100, 88)


class TestSelectiveTodRound14(unittest.TestCase):
    def test_grey_bake_unchanged(self):
        # R13 pins, re-derived: dusk gap > 0.9, dusk R >= 120.
        mid = tod_surface_response(light_for("midday", "warm"), GREY)
        dusk = tod_surface_response(light_for("dusk", "warm"), GREY)
        self.assertGreater(dusk[0] / dusk[2] - mid[0] / mid[2], 0.9)
        self.assertGreaterEqual(dusk[0], 120)

    def test_override_sky_no_longer_warms_midday(self):
        spec = light_for("midday", "warm")
        outside = spec["sky_bottom"]
        mutated = dict(spec)
        mutated["sky_bottom"] = interior_sky_response(
            spec, (64, 48, 40))
        fixed = tod_surface_response(mutated, STONE, sky_rgb=outside)
        plain = tod_surface_response(spec, STONE)
        self.assertEqual(fixed, plain)
        # The R13 behaviour (no sky_rgb) is the bug: it must
        # differ, proving the test exercises the override path.
        buggy = tod_surface_response(mutated, STONE)
        self.assertNotEqual(buggy, plain)
        self.assertLess(buggy[0], plain[0])

    def test_dusk_keeps_strength_with_outside_sky(self):
        spec = light_for("dusk", "warm")
        mutated = dict(spec)
        mutated["sky_bottom"] = interior_sky_response(
            spec, (64, 48, 40))
        out = tod_surface_response(mutated, STONE,
                                   sky_rgb=spec["sky_bottom"])
        self.assertGreater(out[0] / out[2], 2.0)

    def test_no_sky_identity_stands(self):
        spec = {"sun_color": (255, 255, 255), "ambient": 0.47,
                "key_intensity": 1.0}
        self.assertEqual(tod_surface_response(spec, GREY),
                         (128, 128, 128))


if __name__ == "__main__":
    unittest.main()
