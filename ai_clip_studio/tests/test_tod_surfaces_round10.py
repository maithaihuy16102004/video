"""Round 10 (R10-2): the time of day must read on WALLS and
FLOORS, not only the sky. The round-9 sky response never reached
delivered interior frames (identical-box gap 0.29 vs 0.28, shot
#8 pixel-identical between rounds) because the sky is barely
visible indoors and the render-time key tint leaves
inward-facing walls at flat ambient. The tod response (sun tint
+ light level) now bakes into the facade, roof and ground base
colours, so midday, afternoon and dusk read differently on
surfaces in every archetype. Thresholds below are measured on
env renders with identical boxes -- the method that governs.
"""

import json
import unittest
from pathlib import Path

import numpy as np

from ai_clip_studio.environment_v2 import (
    build_environment, render_environment)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera

JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _delivered_traits(shot_index):
    timeline = json.loads(
        (JOBS / "req_3ee64748a857" / "timeline.json").read_text(
            encoding="utf-8"))
    return timeline["shots"][shot_index]["v1_location"]


def _rb(rgb):
    return rgb[0] / max(1.0, rgb[2])


class TestTodSurfacesPalette(unittest.TestCase):
    def _palette(self, traits, tod):
        pkg = build_environment(traits, time_of_day=tod,
                                style={"mood": "warm"})
        return pkg["palette"]

    def test_facade_and_ground_answer_tod(self):
        for idx in (3, 9, 11):  # forge, cave, house
            traits = _delivered_traits(idx)
            mid = self._palette(traits, "midday")
            aft = self._palette(traits, "afternoon")
            dusk = self._palette(traits, "dusk")
            for key in ("facade", "ground"):
                mid_c = mid[key][0] if key == "facade" else mid[key]
                aft_c = aft[key][0] if key == "facade" else aft[key]
                dusk_c = dusk[key][0] if key == "facade" else dusk[key]
                self.assertGreater(_rb(aft_c), _rb(mid_c),
                                   f"shot {idx} {key}")
                self.assertGreater(_rb(dusk_c), _rb(aft_c),
                                   f"shot {idx} {key}")
                self.assertLess(sum(dusk_c), sum(mid_c),
                                f"shot {idx} {key} dims at dusk")


class TestTodSurfacesOnRenders(unittest.TestCase):
    CAM = PerspectiveCamera(position=(0, 2.0, 4.8),
                            target=(0, 1.2, -3.0), fov_deg=50,
                            aspect=1920 / 1080)

    @classmethod
    def _boxes(cls, traits, tod):
        pkg = build_environment(traits, time_of_day=tod,
                                style={"mood": "warm"})
        img = render_environment(pkg, cls.CAM, (1920, 1080))
        arr = np.asarray(img.convert("RGB")).astype(float)
        wall = arr[200:500, 700:1250].mean(axis=(0, 1))
        floor = arr[800:1050, 700:1250].mean(axis=(0, 1))
        return wall, floor

    def test_wall_and_floor_answer_tod(self):
        for idx in (3, 9, 11):
            traits = _delivered_traits(idx)
            mid_w, mid_f = self._boxes(traits, "midday")
            aft_w, aft_f = self._boxes(traits, "afternoon")
            dusk_w, dusk_f = self._boxes(traits, "dusk")
            # Walls: the old key-tint-only whisper was +0.22 R/B
            # total; the baked response must clear +0.35.
            self.assertGreater(_rb(aft_w) - _rb(mid_w), 0.35,
                               f"shot {idx} wall")
            self.assertGreater(_rb(dusk_w), _rb(aft_w),
                               f"shot {idx} wall dusk")
            self.assertGreater(_rb(aft_f) - _rb(mid_f), 0.25,
                               f"shot {idx} floor")
            self.assertGreater(_rb(dusk_f), _rb(aft_f),
                               f"shot {idx} floor dusk")
            self.assertLess(dusk_w.mean(), aft_w.mean(),
                            f"shot {idx} wall dims at dusk")


if __name__ == "__main__":
    unittest.main()
