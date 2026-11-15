"""Round 11 (R11-3): stronger time-of-day. The R10 tester verdict:
the wall gap doubled (0.33 -> 0.65) but the daylight shifts are
still whispers where the reference shouts. The surface response
now takes more of the sun colour (tint 0.30 + 0.70*s, was
0.5 + 0.5*s), the brightness floor drops to 0.50 so night reads
dark, and the afternoon/dusk suns are warmer. Midday stays
near-neutral (its sun was whitened in the same round).
"""

import json
import unittest
from pathlib import Path

from ai_clip_studio.environment_v2 import build_environment
from ai_clip_studio.lighting import light_for, tod_surface_response

GREY = (128, 128, 128)
JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _house_traits():
    timeline = json.loads(
        (JOBS / "req_f28d511157dc" / "timeline.json").read_text(
            encoding="utf-8"))
    return timeline["shots"][11]["v1_location"]


def _rb(rgb):
    return rgb[0] / max(1, rgb[2])


class TestTodSeparation(unittest.TestCase):
    def test_ordering_midday_afternoon_dusk(self):
        rbs = {tod: _rb(tod_surface_response(
            light_for(tod, "warm"), GREY))
            for tod in ("midday", "morning", "afternoon", "dusk")}
        self.assertLess(rbs["midday"], rbs["morning"])
        self.assertLess(rbs["morning"], rbs["afternoon"])
        self.assertLess(rbs["afternoon"], rbs["dusk"])

    def test_dusk_midday_gap_exceeds_half(self):
        mid = _rb(tod_surface_response(light_for("midday", "warm"),
                                       GREY))
        dusk = _rb(tod_surface_response(light_for("dusk", "warm"),
                                        GREY))
        self.assertGreater(dusk - mid, 0.5)

    def test_round13_gap_exceeds_nine_tenths(self):
        # Round 13: steeper tint (0.20 + 0.80*s) + the sky blend
        # toward a coloured/dark sky_bottom. Measured gap 1.07.
        mid = _rb(tod_surface_response(light_for("midday", "warm"),
                                       GREY))
        dusk = _rb(tod_surface_response(light_for("dusk", "warm"),
                                        GREY))
        self.assertGreater(dusk - mid, 0.9)

    def test_dusk_sky_blend_lifts_red(self):
        # The sky blend pulls the dusk wall toward the pink
        # horizon instead of leaving it dark brown: R rises
        # above the tint-only value (102) to 130 measured.
        out = tod_surface_response(light_for("dusk", "warm"), GREY)
        self.assertGreaterEqual(out[0], 120)

    def test_midday_near_identity(self):
        out = tod_surface_response(light_for("midday", "warm"), GREY)
        for got, want in zip(out, GREY):
            self.assertLessEqual(abs(got - want), 4)

    def test_white_sun_at_reference_level_is_identity(self):
        spec = {"sun_color": (255, 255, 255), "ambient": 0.47,
                "key_intensity": 1.0}
        self.assertEqual(
            tod_surface_response(spec, (120, 96, 74)), (120, 96, 74))

    def test_dusk_dims_and_night_darker_still(self):
        mid = tod_surface_response(light_for("midday", "warm"), GREY)
        dusk = tod_surface_response(light_for("dusk", "warm"), GREY)
        night = tod_surface_response(light_for("night", "cold"), GREY)
        self.assertLess(sum(dusk), 0.9 * sum(mid))
        self.assertLess(sum(night), sum(dusk))
        self.assertGreater(sum(night) / 3.0, 25.0)

    def test_night_is_blue_dominant(self):
        out = tod_surface_response(light_for("night", "cold"), GREY)
        self.assertGreater(out[2], out[0])

    def test_does_not_mutate_spec(self):
        spec = light_for("dusk", "warm")
        before = dict(spec)
        tod_surface_response(spec, GREY)
        self.assertEqual(spec, before)


class TestRoomWindowGlass(unittest.TestCase):
    def _glass(self, tod):
        pkg = build_environment(_house_traits(), time_of_day=tod,
                                style={"mood": "warm"})
        wins = [e for e in pkg["elements"]
                if e.get("id") in ("room_win_0", "room_win_1")]
        self.assertEqual(len(wins), 2)
        return tuple(wins[0]["color"])

    def test_dusk_glass_warmer_than_midday(self):
        mid = self._glass("midday")
        dusk = self._glass("dusk")
        self.assertGreater(_rb(dusk), _rb(mid) + 0.2)

    def test_midday_glass_near_old_fixed_colour(self):
        mid = self._glass("midday")
        for got, want in zip(mid, (170, 195, 220)):
            self.assertLessEqual(abs(got - want), 20)

    def test_night_glass_deep_blue(self):
        night = self._glass("night")
        self.assertGreater(night[2], night[0])
        self.assertLess(sum(night) / 3.0, 80.0)


if __name__ == "__main__":
    unittest.main()
