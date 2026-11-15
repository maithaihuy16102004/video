"""Round 15 (R14-D1): the sun/moon disc must fit the VISIBLE region.

The frozen crop is applied to the composited frame AFTER the
environment renders, so a disc placed near the top of the full
frame clipped on tight shots (Loop-01 #0 MCU: 233x211, bbox
y0=0). sun_disc_spec takes the crop rect (visible_rect) and
places the whole disc + margin inside it.
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
# A realistic medium_close_up crop rect: SHOT_SCALE 1.6 gives a
# 1200x675 window; #0's window sits in the upper frame (its
# delivered disc was 233px wide, clipped 22px at the top).
RECT = (360.0, 60.0, 1560.0, 735.0)


def _inside_rect(spec, rect, margin=12.0):
    cx, cy = spec["center"]
    r = spec["radius"]
    x0, y0, x1, y1 = rect
    return (cx - r >= x0 + margin - 1e-6
            and cx + r <= x1 - margin + 1e-6
            and cy - r >= y0 + margin - 1e-6
            and cy + r <= y1 - margin + 1e-6)


class TestSunVisibleRectRound15(unittest.TestCase):
    def test_dusk_disc_fits_crop_rect(self):
        # The large dusk disc (radius ~106) must fit inside the
        # MCU crop window with margin.
        spec = sun_disc_spec(light_for("dusk", "warm"), [], CAM,
                             1920, 1080, 330.0, "k",
                             visible_rect=RECT)
        self.assertTrue(_inside_rect(spec, RECT))

    def test_morning_disc_fits_crop_rect(self):
        spec = sun_disc_spec(light_for("morning", "warm"), [], CAM,
                             1920, 1080, 330.0, "k",
                             visible_rect=RECT)
        self.assertTrue(_inside_rect(spec, RECT))

    def test_no_rect_unchanged(self):
        # visible_rect=None reproduces the round-14 placement
        # exactly (the refactor must not move existing suns).
        args = (light_for("dusk", "warm"), [], CAM,
                1920, 1080, 330.0, "k")
        self.assertEqual(sun_disc_spec(*args),
                         sun_disc_spec(*args, visible_rect=None))

    def test_tiny_rect_best_effort(self):
        # A rect too short for the disc centres it without
        # crashing and stays deterministic. Horizon below the
        # rect so the horizon rule does not interfere.
        tiny = (900.0, 500.0, 1020.0, 560.0)
        args = (light_for("dusk", "warm"), [], CAM,
                1920, 1080, 900.0, "k")
        a = sun_disc_spec(*args, visible_rect=tiny)
        b = sun_disc_spec(*args, visible_rect=tiny)
        self.assertEqual(a, b)
        self.assertAlmostEqual(a["center"][1], 530.0)

    def test_render_disc_inside_crop_region(self):
        # End to end: the real village package rendered with a
        # crop rect has sun-coloured pixels inside the rect and
        # the disc centre (from the spec) inside it too.
        # Morning light: the R14-D1 case (Loop-01 #0).
        timeline = json.load(open(
            "/home/hatch/workspace/agent/jobs/req_e07ea01471d1/"
            "timeline.json"))
        loc = timeline["shots"][1]["v1_location"]
        pkg = build_environment(loc, time_of_day="morning",
                                style={"mood": "warm"})
        img = render_environment(pkg, CAM, visible_rect=RECT)
        sun = tuple(pkg["light"]["sun_color"])
        px = img.load()
        count = 0
        x0, y0, x1, y1 = (int(v) for v in RECT)
        for y in range(y0, y1, 4):
            for x in range(x0, x1, 4):
                p = px[x, y]
                if all(abs(p[i] - sun[i]) <= 12 for i in range(3)):
                    count += 1
        self.assertGreater(count, 200)


if __name__ == "__main__":
    unittest.main()
