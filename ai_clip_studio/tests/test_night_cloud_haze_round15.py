"""Round 15 (L02-D5): night clouds haze into the sky.

At night the dimmed clouds still contrasted against the dark
sky and their flat shaded base read as saucer rims. The cloud
colour hazes toward the upper sky as the light drops below
dusk; dusk and day clouds are untouched.
"""
import json
import math
import unittest

from ai_clip_studio.environment_v2 import build_environment
from ai_clip_studio.lighting import light_for, tod_surface_response


def _seaside_location():
    timeline = json.load(open(
        "/home/hatch/workspace/agent/jobs/req_b1f6b9669724/"
        "timeline.json"))
    return timeline["shots"][13]["v1_location"]  # SC04, seaside, night


def _cloud_colours(tod):
    pkg = build_environment(_seaside_location(), time_of_day=tod,
                            style={"mood": "warm"})
    return pkg, {tuple(e["color"]) for e in pkg["elements"]
                 if e["id"].startswith("sky_cloud_")}


class TestNightCloudHazeRound15(unittest.TestCase):
    def test_night_clouds_haze_toward_sky(self):
        pkg, colours = _cloud_colours("night")
        self.assertEqual(len(colours), 1)
        colour = next(iter(colours))
        top = tuple(pkg["light"]["sky_top"])
        dist = math.dist(colour, top)
        self.assertLess(dist, 60.0)

    def test_dusk_clouds_unchanged(self):
        _, colours = _cloud_colours("dusk")
        light = light_for("dusk", "warm")
        want = tod_surface_response(light, (246, 246, 250),
                                    sky_rgb=tuple(light["sky_bottom"]))
        self.assertEqual(colours, {tuple(want)})

    def test_morning_clouds_unchanged(self):
        _, colours = _cloud_colours("morning")
        light = light_for("morning", "warm")
        want = tod_surface_response(light, (246, 246, 250),
                                    sky_rgb=tuple(light["sky_bottom"]))
        self.assertEqual(colours, {tuple(want)})


if __name__ == "__main__":
    unittest.main()
