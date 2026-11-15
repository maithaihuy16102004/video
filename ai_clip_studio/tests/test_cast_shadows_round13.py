"""Round 13 (R13-3): cast shadows. The W1 contact ellipse is
capped to the footprint by design, so a low sun never showed a
long shadow. The cast quad stretches from the feet along the
light's ground direction, outdoors only. Spec geometry is pinned
exactly; the render test checks the dusk shadow darkens its
ground patch relative to a sunlit patch, tod-normalized.
"""

import json
import math
import unittest
from pathlib import Path

import numpy as np

from ai_clip_studio.camera_planner import (
    PerspectiveCamera, viewpoint_for_shot)
from ai_clip_studio.environment_v2 import (
    build_environment, render_environment)
from ai_clip_studio.lighting import (
    cast_shadow_spec, light_for, rig_for)
from ai_clip_studio.renderer25d.lighting import DirectionalLight

JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _traits(shot_index):
    timeline = json.loads(
        (JOBS / "req_3ee64748a857" / "timeline.json").read_text(
            encoding="utf-8"))
    return timeline["shots"][shot_index]["v1_location"]


def _cam():
    return PerspectiveCamera(position=(0.0, 2.5, 7.5),
                             target=(0.0, 1.0, 0.0), fov_deg=46.0,
                             aspect=16.0 / 9.0)


class TestCastShadowSpec(unittest.TestCase):
    def test_dusk_length_follows_spread(self):
        light = DirectionalLight(direction=(0.7, -0.45, -0.2))
        spec = cast_shadow_spec((0.0, 0.0, 0.0), 1.75, 0.3, light,
                                _cam(), (1920, 1080))
        self.assertIsNotNone(spec)
        # The light normalizes its direction: elevation comes
        # from the light itself, spread = (1 - elev) / elev.
        elev = light.elevation_factor()
        self.assertAlmostEqual(spec["length_world"],
                               1.75 * (1.0 - elev) / elev, places=2)
        self.assertEqual(spec["alpha"], 0.30)
        self.assertEqual(len(spec["polygon_px"]), 4)

    def test_quad_extends_along_ground_direction(self):
        light = DirectionalLight(direction=(0.7, -0.45, -0.2))
        spec = cast_shadow_spec((0.0, 0.0, 0.0), 1.75, 0.3, light,
                                _cam(), (1920, 1080))
        pts = spec["polygon_px"]
        near_cx = (pts[0][0] + pts[1][0]) / 2
        far_cx = (pts[2][0] + pts[3][0]) / 2
        # Ground direction is +x: the far end sits right of the
        # near end in screen space from this camera.
        self.assertGreater(far_cx, near_cx)
        # Tapered: the far pair is narrower than the near pair.
        near_w = abs(pts[1][0] - pts[0][0])
        far_w = abs(pts[2][0] - pts[3][0])
        self.assertLess(far_w, near_w)

    def test_high_sun_returns_none(self):
        light = DirectionalLight(direction=(0.1, -1.0, -0.1))
        self.assertIsNone(cast_shadow_spec(
            (0.0, 0.0, 0.0), 1.75, 0.3, light, _cam(), (1920, 1080)))

    def test_straight_down_returns_none(self):
        light = DirectionalLight(direction=(0.0, -1.0, 0.0))
        self.assertIsNone(cast_shadow_spec(
            (0.0, 0.0, 0.0), 1.75, 0.3, light, _cam(), (1920, 1080)))

    def test_length_capped(self):
        light = DirectionalLight(direction=(0.9, -0.15, 0.0))
        spec = cast_shadow_spec((0.0, 0.0, 0.0), 1.75, 0.3, light,
                                _cam(), (1920, 1080))
        self.assertIsNotNone(spec)
        self.assertAlmostEqual(spec["length_world"], 2.2 * 1.75,
                               places=2)


class TestCastShadowRender(unittest.TestCase):
    def test_dusk_shadow_darkens_its_ground_patch(self):
        # Render the dusk env with and without the casting
        # element (exclude_ids): the quad-centroid ground patch
        # must be darker with the element (its cast shadow falls
        # there), while a far control patch is unchanged. The
        # element's own pixels sit away from the patch, so the
        # exclusion removes only the element + its shadows.
        cam = viewpoint_for_shot("establishing", elevation_deg=15.0)
        pkg = build_environment(_traits(1), time_of_day="dusk",
                                style={"mood": "warm"})
        rig = rig_for(pkg["light"])
        target, spec = None, None
        for el in pkg["elements"]:
            # Narrow + tall + grounded: the quad extends well
            # beyond the element's own pixels (a wide house
            # covers its own quad centroid).
            if (el["size"][1] > 2.0 and el["size"][0] < 1.0
                    and abs(el["center"][1] - el["size"][1] / 2)
                    < 0.1 and el.get("layer") == "BG"):
                spec = cast_shadow_spec(
                    (el["center"][0], 0.0, el["center"][2]),
                    el["size"][1],
                    max(el["size"][0], el["size"][2]) * 0.4,
                    rig.key, cam, (1920, 1080))
                if spec is not None:
                    target = el
                    break
        self.assertIsNotNone(spec)
        full = np.asarray(render_environment(
            pkg, cam).convert("L")).astype(float)
        cut = np.asarray(render_environment(
            pkg, cam, exclude_ids={target["id"]}).convert(
            "L")).astype(float)
        # The only differences between the renders are the
        # element, its contact ellipse, and its cast quad.
        # Mask out a box around the element's projected feet
        # (its own pixels + contact shadow); the remaining
        # darkened pixels are the cast shadow.
        fx, fy, _, _ = cam.project(
            (target["center"][0], 0.0, target["center"][2]),
            1920, 1080)
        darker = (full < cut - 8.0)
        darker[max(0, int(fy) - 120):int(fy) + 60,
               max(0, int(fx) - 60):int(fx) + 60] = False
        self.assertGreater(int(darker.sum()), 300)
        ctrl_full = full[900:920, 100:120].mean()
        ctrl_cut = cut[900:920, 100:120].mean()
        self.assertAlmostEqual(ctrl_full, ctrl_cut, delta=2.0)

    def test_midday_casts_no_shadow(self):
        cam = viewpoint_for_shot("establishing", elevation_deg=15.0)
        pkg = build_environment(_traits(1), time_of_day="midday",
                                style={"mood": "warm"})
        rig = rig_for(pkg["light"])
        for el in pkg["elements"]:
            if el["size"][1] > 2.5 and el.get("layer") == "BG":
                self.assertIsNone(cast_shadow_spec(
                    (el["center"][0], 0.0, el["center"][2]),
                    el["size"][1],
                    max(el["size"][0], el["size"][2]) * 0.4,
                    rig.key, cam, (1920, 1080)))


if __name__ == "__main__":
    unittest.main()
