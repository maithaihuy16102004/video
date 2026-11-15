"""Round 14: the sun/moon disc in the sky (dossier "large sun").

The disc is screen-space, outdoor archetypes only, placed in the
most open sky by projecting the BG/MG/FG occluders through the
shot camera. Dusk gets the large sun; night gets a pale moon.
"""
import json
import unittest

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import (
    build_environment,
    render_environment,
    sun_disc_spec,
)
from ai_clip_studio.lighting import light_for

CAM = viewpoint_for_shot("establishing", elevation_deg=15.0)


def _village_location():
    timeline = json.load(open(
        "/home/hatch/workspace/agent/jobs/req_e07ea01471d1/"
        "timeline.json"))
    return timeline["shots"][1]["v1_location"]


def _sun_pixels(img, colour, band=260, tol=12):
    px = img.load()
    count = 0
    for y in range(0, band, 4):
        for x in range(0, img.size[0], 4):
            p = px[x, y]
            if all(abs(p[i] - colour[i]) <= tol for i in range(3)):
                count += 1
    return count


class TestSunDiscRound14(unittest.TestCase):
    def test_dusk_sun_larger_than_morning(self):
        els, cam = [], CAM
        dusk = sun_disc_spec(light_for("dusk", "warm"), els, cam,
                             1920, 1080, 330.0, "k")
        morn = sun_disc_spec(light_for("morning", "warm"), els, cam,
                             1920, 1080, 330.0, "k")
        self.assertGreater(dusk["radius"], morn["radius"] * 1.3)

    def test_night_is_a_pale_moon(self):
        spec = sun_disc_spec(light_for("night", "warm"), [], CAM,
                             1920, 1080, 330.0, "k")
        self.assertTrue(spec["is_moon"])
        self.assertEqual(spec["color"], (232, 236, 242))

    def test_deterministic_and_in_frame(self):
        args = (light_for("dusk", "warm"), [], CAM,
                1920, 1080, 330.0, "k")
        a = sun_disc_spec(*args)
        b = sun_disc_spec(*args)
        self.assertEqual(a, b)
        cx, cy = a["center"]
        r = a["radius"]
        self.assertGreaterEqual(cx - r, 0)
        self.assertLessEqual(cx + r, 1920)
        self.assertGreaterEqual(cy - r, 0)

    def test_disc_visible_outdoors_absent_indoors(self):
        loc = _village_location()
        pkg = build_environment(loc, time_of_day="dusk",
                                style={"mood": "warm"})
        img = render_environment(pkg, CAM)
        sun = tuple(pkg["light"]["sun_color"])
        self.assertGreater(_sun_pixels(img, sun), 200)
        # An enclosed archetype never draws the disc: the same
        # dusk light over the real forge package leaves the dark
        # sky band free of sun-coloured pixels.
        timeline = json.load(open(
            "/home/hatch/workspace/agent/jobs/req_e07ea01471d1/"
            "timeline.json"))
        forge = build_environment(
            timeline["shots"][3]["v1_location"],
            time_of_day="dusk", style={"mood": "warm"})
        self.assertEqual(forge.get("archetype"), "FORGE")
        img2 = render_environment(forge, CAM)
        self.assertEqual(_sun_pixels(img2, sun), 0)


if __name__ == "__main__":
    unittest.main()
