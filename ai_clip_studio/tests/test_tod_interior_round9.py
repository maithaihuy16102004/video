"""Round 9 (R2-V4 residual): interior backdrops answer the time of
day. Archetype interiors (cave, forge) replaced the tod sky palette
with FIXED override colours, so the backdrop was pixel-identical at
every hour and only the weak key tint moved the walls. Now the
override is tinted by the tod sun colour and dimmed by the tod
light level: the cave stays dark and the forge stays warm, but
midday, afternoon and dusk read differently in the backdrop as
well as on the walls.
"""

import json
import unittest
from pathlib import Path

import numpy as np

from ai_clip_studio.environment_v2 import (
    build_environment, render_environment)
from ai_clip_studio.lighting import interior_sky_response, light_for
from ai_clip_studio.renderer25d.camera import PerspectiveCamera

JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _delivered_traits(shot_index):
    timeline = json.loads(
        (JOBS / "req_3ee64748a857" / "timeline.json").read_text(
            encoding="utf-8"))
    return timeline["shots"][shot_index]["v1_location"]


class TestInteriorSkyResponse(unittest.TestCase):
    BASE = (120, 96, 74)  # forge sky_bottom override

    def test_midday_near_identity(self):
        out = interior_sky_response(light_for("midday", "warm"),
                                    self.BASE)
        for got, want in zip(out, self.BASE):
            self.assertLessEqual(abs(got - want), 3)

    def test_afternoon_warmer_than_morning_warmer_than_midday(self):
        def rb(tod):
            r, _g, b = interior_sky_response(light_for(tod, "warm"),
                                             self.BASE)
            return r / b
        self.assertGreater(rb("afternoon"), rb("morning"))
        self.assertGreater(rb("morning"), rb("midday"))
        self.assertGreater(rb("afternoon") - rb("midday"), 0.2)

    def test_dusk_dims_and_warms(self):
        mid = interior_sky_response(light_for("midday", "warm"),
                                    self.BASE)
        dusk = interior_sky_response(light_for("dusk", "warm"),
                                     self.BASE)
        self.assertLess(sum(dusk), sum(mid))
        self.assertGreater(dusk[0] / dusk[2], mid[0] / mid[2])

    def test_night_keeps_cave_dark(self):
        out = interior_sky_response(light_for("night", "cold"),
                                    (52, 48, 44))
        self.assertLess(sum(out) / 3.0, 40.0)
        self.assertLessEqual(max(out), 52)


class TestInteriorSkyOnRenders(unittest.TestCase):
    CAM = PerspectiveCamera(position=(0, 2.0, 4.8),
                            target=(0, 1.2, -3.0), fov_deg=50,
                            aspect=1920 / 1080)

    @classmethod
    def _sky(cls, traits, tod):
        pkg = build_environment(traits, time_of_day=tod,
                                style={"mood": "warm"})
        img = render_environment(pkg, cls.CAM, (1920, 1080))
        arr = np.asarray(img.convert("RGB")).astype(float)
        sky = arr[20:100, 800:1100].mean(axis=(0, 1))
        return sky, arr.mean()

    def test_forge_sky_answers_tod(self):
        traits = _delivered_traits(3)
        mid, _ = self._sky(traits, "midday")
        aft, _ = self._sky(traits, "afternoon")
        dusk, _ = self._sky(traits, "dusk")
        self.assertGreater(aft[0] / aft[2] - mid[0] / mid[2], 0.15)
        self.assertGreater(dusk[0] / dusk[2], aft[0] / aft[2])

    def test_cave_sky_answers_tod_and_stays_dark(self):
        traits = _delivered_traits(9)
        mid, mid_lum = self._sky(traits, "midday")
        aft, _ = self._sky(traits, "afternoon")
        dusk, dusk_lum = self._sky(traits, "dusk")
        self.assertGreater(aft[0] / aft[2] - mid[0] / mid[2], 0.10)
        self.assertGreater(dusk[0] / dusk[2], aft[0] / aft[2])
        self.assertLess(mid_lum, 60.0)
        self.assertLess(dusk_lum, 60.0)


if __name__ == "__main__":
    unittest.main()
