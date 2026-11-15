"""Round 15: dusk light -- the pink sky mid-band (R15-2) and lit
facade windows at dusk (R15-3, the lit-window half of R13-D2).

The dossier sunset is "pink-orange-purple with a large sun":
the dusk gradient gains a pink mid stop (outdoor archetypes
only -- enclosed backdrops keep the two-stop gradient), and
facade windows glow whenever the light is dim (dusk joins
night, same ambient < 0.40 threshold as the round-13 skyline
rule; day facades keep dark glass).
"""
import json
import unittest

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import (
    build_environment,
    render_environment,
    sun_disc_spec,
)

CAM = viewpoint_for_shot("establishing", elevation_deg=15.0)


def _loop02_location(index):
    timeline = json.load(open(
        "/home/hatch/workspace/agent/jobs/req_b1f6b9669724/"
        "timeline.json"))
    return timeline["shots"][index]["v1_location"]


def _sky_pixel(pkg, y=297):
    """One pure-gradient pixel: no elements (draw_layers=()),
    sampled far from the sun disc + halo so nothing covers the
    sky gradient at that point."""
    img = render_environment(pkg, CAM, draw_layers=())
    light = pkg["light"]
    spec = sun_disc_spec(light, pkg.get("elements", []), CAM,
                         1920, 1080, 330.0, "probe")
    cx = spec["center"][0] if spec else 960.0
    r = spec["radius"] if spec else 0.0
    # 600px from the disc centre clears the 3.2x halo.
    x = int(cx + 600) if cx < 960 else int(cx - 600)
    x = min(max(x, 10), 1910)
    px = img.load()
    return px[x, y], (x, y, cx, r)


class TestDuskLightRound15(unittest.TestCase):
    def test_dusk_sky_has_pink_band(self):
        # At t=0.275 the gradient sits halfway between the
        # purple top and the pink mid: (154, 103, 138).
        loc = _loop02_location(8)  # SC03_SH01, old town, dusk
        pkg = build_environment(loc, time_of_day="dusk",
                                style={"mood": "warm"})
        got, _ = _sky_pixel(pkg)
        for g, want in zip(got, (154, 103, 138)):
            self.assertAlmostEqual(g, want, delta=3)

    def test_enclosed_backdrop_ignores_pink_band(self):
        # The forge at dusk: the interior override backdrop
        # uses the plain two-stop gradient of the OVERRIDDEN
        # sky values -- no pink band leaks indoors.
        timeline = json.load(open(
            "/home/hatch/workspace/agent/jobs/req_e07ea01471d1/"
            "timeline.json"))
        loc = timeline["shots"][3]["v1_location"]
        pkg = build_environment(loc, time_of_day="dusk",
                                style={"mood": "warm"})
        got, _ = _sky_pixel(pkg)
        light = pkg["light"]
        top = tuple(light["sky_top"])
        bottom = tuple(light["sky_bottom"])
        t = 297 / 1079
        want = tuple(int(round(top[i] * (1 - t) + bottom[i] * t))
                     for i in range(3))
        for g, w in zip(got, want):
            self.assertAlmostEqual(g, w, delta=3)

    def test_morning_sky_unchanged(self):
        # No sky_mid outside dusk: the morning gradient is the
        # plain two-stop interpolation.
        loc = _loop02_location(8)
        pkg = build_environment(loc, time_of_day="morning",
                                style={"mood": "warm"})
        got, _ = _sky_pixel(pkg)
        light = pkg["light"]
        top = tuple(light["sky_top"])
        bottom = tuple(light["sky_bottom"])
        t = 297 / 1079
        want = tuple(int(round(top[i] * (1 - t) + bottom[i] * t))
                     for i in range(3))
        for g, w in zip(got, want):
            self.assertAlmostEqual(g, w, delta=3)

    def _window_colours(self, tod):
        loc = _loop02_location(8)
        pkg = build_environment(loc, time_of_day=tod,
                                style={"mood": "warm"})
        colours = {tuple(e["color"]) for e in pkg["elements"]
                   if e.get("kind") == "window"
                   and e.get("material") == "glass"}
        return pkg, colours

    def test_facade_windows_lit_at_dusk(self):
        pkg, colours = self._window_colours("dusk")
        self.assertTrue(colours)
        self.assertEqual(colours, {(255, 200, 90)})
        lights = pkg.get("point_lights", [])
        self.assertTrue(any(str(p["id"]).startswith("window_light_")
                            for p in lights))

    def test_window_light_count_capped(self):
        # Round 15: ~50 lit panes emit at most 8 lights --
        # one light per pane floods the street yellow.
        loc = _loop02_location(8)
        pkg = build_environment(loc, time_of_day="dusk",
                                style={"mood": "warm"})
        wins = [e for e in pkg["elements"]
                if e.get("kind") == "window"]
        self.assertGreater(len(wins), 8)
        lights = [p for p in pkg.get("point_lights", [])
                  if str(p["id"]).startswith("window_light_")]
        self.assertEqual(len(lights), 8)

    def test_facade_windows_dark_by_day(self):
        _, colours = self._window_colours("morning")
        self.assertTrue(colours)
        self.assertEqual(colours, {(52, 66, 88)})

    def test_facade_windows_lit_at_night(self):
        _, colours = self._window_colours("night")
        self.assertTrue(colours)
        self.assertEqual(colours, {(255, 200, 90)})


if __name__ == "__main__":
    unittest.main()
