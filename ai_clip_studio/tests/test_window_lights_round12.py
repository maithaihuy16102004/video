"""Round 12 (R12-3): window light pools. Bright glass windows
emit point lights with the pane's own colour, so dusk windows
warm the floor in front of them and lit facade windows spill
onto the street at night. Dark glass emits nothing.
"""

import unittest

from ai_clip_studio.environment_v2 import build_environment


def _room_traits():
    return {"id": "LOC_TEST", "location": "phòng khách",
            "fields": {"LOCATION": "trong nhà"}}


class TestWindowLights(unittest.TestCase):
    def test_room_windows_emit_sky_coloured_lights(self):
        pkg = build_environment(_room_traits(), time_of_day="dusk",
                                style={"mood": "warm"})
        lights = {pl["id"]: pl for pl in pkg["point_lights"]}
        self.assertIn("lamp_glow", lights)
        for i in range(2):
            pl = lights[f"window_light_room_win_{i}"]
            win = next(e for e in pkg["elements"]
                       if e["id"] == f"room_win_{i}")
            self.assertEqual(tuple(pl["color"]),
                             tuple(win["color"]))
            # 0.5 m in front of the pane, toward the room.
            self.assertAlmostEqual(pl["position"][2],
                                   win["center"][2] + 0.5)
            self.assertAlmostEqual(pl["position"][0],
                                   win["center"][0])
            self.assertGreater(pl["intensity"], 0)
            self.assertGreater(pl["falloff_k"], 0)
        import json
        json.dumps(pkg["point_lights"])

    def test_dark_facade_windows_emit_nothing_at_day(self):
        traits = {"id": "LOC_ST", "location": "phố",
                  "fields": {"LOCATION": "mặt tiền phố"},
                  "features": ["phố", "mặt tiền", "cửa hàng"]}
        pkg = build_environment(traits, time_of_day="day",
                                style={"mood": "warm"})
        wins = [e for e in pkg["elements"]
                if e.get("kind") == "window"]
        self.assertTrue(wins, "no facade windows to test against")
        self.assertEqual(
            [pl for pl in pkg["point_lights"]
             if pl["id"].startswith("window_light_")], [])

    def test_dropped_window_leaves_no_light(self):
        traits = dict(_room_traits())
        traits["negative_constraints"] = ["no windows"]
        pkg = build_environment(traits, time_of_day="dusk",
                                style={"mood": "warm"})
        self.assertEqual(
            [e for e in pkg["elements"]
             if e.get("kind") == "window"], [])
        self.assertEqual(
            [pl for pl in pkg["point_lights"]
             if pl["id"].startswith("window_light_")], [])

    def test_window_pool_warms_near_floor(self):
        import numpy as np
        from ai_clip_studio.environment_v2 import render_environment
        from ai_clip_studio.camera_planner import viewpoint_for_shot
        pkg = build_environment(_room_traits(), time_of_day="dusk",
                                style={"mood": "warm"})
        cam = viewpoint_for_shot("medium", "eye_level",
                                 subject_pos=(0.0, 1.2, 0.0))
        lit = np.asarray(render_environment(
            pkg, cam, (960, 540), draw_layers=("BG", "MG")).convert(
                "RGB")).astype(float)
        dark = np.asarray(render_environment(
            dict(pkg, point_lights=[
                pl for pl in pkg["point_lights"]
                if not pl["id"].startswith("window_light_")]),
            cam, (960, 540), draw_layers=("BG", "MG")).convert(
                "RGB")).astype(float)
        # The floor band under the windows warms substantially
        # with the lights on, and more than a far corner: the
        # pool is wide (falloff 0.06) but still a gradient, not
        # a uniform wash.
        near = (lit[400:500, 300:660] - dark[400:500, 300:660])
        far = (lit[400:500, 0:120] - dark[400:500, 0:120])
        self.assertGreater(near[:, :, 0].mean(), 8.0)
        self.assertLess(far[:, :, 0].mean(),
                        near[:, :, 0].mean())


if __name__ == "__main__":
    unittest.main()
