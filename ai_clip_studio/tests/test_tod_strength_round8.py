"""Round-8 time-of-day strength (R2-V4): the key light shaded
grayscale, so the palette's sun colour never reached a shaded
face -- a white noon sun and an amber afternoon sun produced
identical wall hues, and the ground gradient repeated the fixed
spec colour at every hour. Interiors (whose skies are
overridden) showed no time-of-day hue at all.

Now the key tints per channel (flat faces via shade_with_points,
textured faces via the paste gain, ground via the lit gradient),
so the midday forge reads neutral and the afternoon cave reads
golden. Measured on env-only renders with the delivered
Loop-01 traits: wall R/B 1.49 -> 1.71 (forge) and 1.59 -> 1.80
(cave) from midday to afternoon; floor R/B 1.29 -> 1.44.
"""
import json
import unittest
from pathlib import Path

import numpy as np

from ai_clip_studio.environment_v2 import (
    build_environment, render_environment)
from ai_clip_studio.lighting import (
    key_factor_for, light_for, rig_for)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera

JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _delivered_traits(shot_index):
    timeline = json.loads(
        (JOBS / "req_3ee64748a857" / "timeline.json").read_text(
            encoding="utf-8"))
    return timeline["shots"][shot_index]["v1_location"]


class TestKeyFactor(unittest.TestCase):
    def test_white_key_is_scalar(self):
        spec = light_for("day", "warm")
        spec["sun_color"] = (255, 255, 255)
        rig = rig_for(spec)
        factor = key_factor_for(rig, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        self.assertEqual(factor[0], factor[1])
        self.assertEqual(factor[1], factor[2])
        self.assertAlmostEqual(
            factor[0],
            min(1.0, rig.ambient
                + rig.key.irradiance((0.0, 1.0, 0.0),
                                     (0.0, 0.0, 1.0))))

    def test_amber_key_suppresses_blue(self):
        rig = rig_for(light_for("afternoon", "warm"))
        factor = key_factor_for(rig, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        self.assertGreater(factor[0], factor[2])
        self.assertGreater(factor[1], factor[2])

    def test_midday_key_near_neutral(self):
        rig = rig_for(light_for("midday", "warm"))
        factor = key_factor_for(rig, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        # Sun (255, 253, 246) since round 11 (whitened so the
        # strengthened surface response keeps noon near-neutral):
        # the channels stay within 8%.
        self.assertLess(factor[0] - factor[2], 0.08)


class TestTodHueOnRenders(unittest.TestCase):
    CAM = PerspectiveCamera(position=(0, 2.0, 4.8),
                            target=(0, 1.2, -3.0), fov_deg=50,
                            aspect=1920 / 1080)

    @classmethod
    def _bands(cls, traits, tod):
        pkg = build_environment(traits, time_of_day=tod,
                                style={"mood": "warm"})
        img = render_environment(pkg, cls.CAM, (1920, 1080))
        arr = np.asarray(img.convert("RGB")).astype(float)
        wall = arr[200:500, 700:1250].mean(axis=(0, 1))
        floor = arr[800:1050, 700:1250].mean(axis=(0, 1))
        return wall, floor

    def test_afternoon_warmer_than_midday_same_place(self):
        for index in (3, 9):
            traits = _delivered_traits(index)
            mid_wall, mid_floor = self._bands(traits, "midday")
            aft_wall, aft_floor = self._bands(traits, "afternoon")
            self.assertGreater(
                aft_wall[0] / max(aft_wall[2], 1.0),
                mid_wall[0] / max(mid_wall[2], 1.0) + 0.1,
                f"shot {index}: afternoon walls not warmer")
            self.assertGreater(
                aft_floor[0] / max(aft_floor[2], 1.0),
                mid_floor[0] / max(mid_floor[2], 1.0) + 0.05,
                f"shot {index}: afternoon floor not warmer")

    def test_delivered_pairing_separates(self):
        # The delivered pairing: forge at midday vs cave in the
        # afternoon. Both surfaces must read the hue gap.
        forge_wall, forge_floor = self._bands(
            _delivered_traits(3), "midday")
        cave_wall, cave_floor = self._bands(
            _delivered_traits(9), "afternoon")
        self.assertGreater(
            cave_wall[0] / max(cave_wall[2], 1.0),
            forge_wall[0] / max(forge_wall[2], 1.0) + 0.15)
        self.assertGreater(
            cave_floor[0] / max(cave_floor[2], 1.0),
            forge_floor[0] / max(forge_floor[2], 1.0) + 0.05)


if __name__ == "__main__":
    unittest.main()
