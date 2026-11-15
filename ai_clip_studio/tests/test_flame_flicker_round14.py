"""Round 14: flame flicker -- fire/flame elements animate per
frame (shape, brightness, halo, floor glow) instead of sitting
frozen in the baked background.
"""
import json
import statistics
import unittest

from PIL import Image, ImageDraw

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import (
    _FLICKER_KINDS,
    _draw_flames,
    build_environment,
    flame_flicker,
    render_environment,
)

CAM = viewpoint_for_shot("establishing", elevation_deg=15.0)


class TestFlameFlickerRound14(unittest.TestCase):
    def test_flicker_deterministic_bounded_varying(self):
        vals = [flame_flicker(f, 1234) for f in range(48)]
        self.assertTrue(all(0.0 <= v <= 1.0 for v in vals))
        self.assertEqual(vals, [flame_flicker(f, 1234)
                                for f in range(48)])
        self.assertGreater(statistics.pstdev(vals), 0.1)
        self.assertNotAlmostEqual(vals[0], vals[24])

    def test_draw_flames_varies_by_frame(self):
        el = {"id": "test_fire", "kind": "fire", "layer": "MG",
              "geometry": "blob", "center": (0.0, 1.0, -4.0),
              "size": (1.0, 0.7, 0.3), "color": (255, 140, 40),
              "material": "fire"}
        hashes = set()
        for frame in (0, 1, 2, 3, 5, 8):
            img = Image.new("RGB", (640, 360), (40, 36, 32))
            _draw_flames(img, ImageDraw.Draw(img), el, CAM,
                         640, 360, frame=frame)
            hashes.add(hash(img.tobytes()))
            warm = sum(1 for p in img.getdata()
                       if p[0] > 180 and p[0] - p[2] > 60)
            self.assertGreater(warm, 200, f"frame {frame}")
        self.assertEqual(len(hashes), 6)

    def test_flame_kinds_present_in_forge_and_cave(self):
        timeline = json.load(open(
            "/home/hatch/workspace/agent/jobs/req_e07ea01471d1/"
            "timeline.json"))
        forge = build_environment(
            timeline["shots"][3]["v1_location"],
            time_of_day="midday", style={"mood": "warm"})
        cave = build_environment(
            timeline["shots"][8]["v1_location"],
            time_of_day="afternoon", style={"mood": "warm"})
        self.assertTrue(any(e.get("kind") == "fire"
                            for e in forge["elements"]))
        self.assertTrue(any(e.get("kind") == "flame"
                            for e in cave["elements"]))
        self.assertEqual(_FLICKER_KINDS, {"fire", "flame"})

    def test_excluding_fire_ids_removes_the_flame(self):
        # The exclusion mechanism _render_shot uses for animated
        # elements must remove the baked flame, or the per-frame
        # draw would double-paint over a frozen blob.
        timeline = json.load(open(
            "/home/hatch/workspace/agent/jobs/req_e07ea01471d1/"
            "timeline.json"))
        forge = build_environment(
            timeline["shots"][3]["v1_location"],
            time_of_day="midday", style={"mood": "warm"})
        fire_ids = [e["id"] for e in forge["elements"]
                    if e.get("kind") in _FLICKER_KINDS]
        self.assertTrue(fire_ids)
        full = render_environment(forge, CAM)
        bare = render_environment(forge, CAM,
                                  exclude_ids=fire_ids)

        def warm(img):
            return sum(1 for p in img.getdata()
                       if p[0] > 200 and p[0] - p[2] > 80)
        self.assertGreater(warm(full), warm(bare))


if __name__ == "__main__":
    unittest.main()
