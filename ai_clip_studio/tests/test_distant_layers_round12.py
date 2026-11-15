"""Round 12 (R12-1): layered distant background + foreground
foliage. The horizon gains a far ridge row (atmospheric haze),
a distant settlement skyline, and near-camera foliage masses
for the blurred-foreground depth cue. Element-presence +
validation pins; the visual read lives on env renders and
delivered establishing frames.
"""

import json
import unittest
from pathlib import Path

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import (
    _projected_bbox, build_environment, validate_fg_composition)

JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _establishing_camera():
    # The R11-capped establishing camera (radius 7.5): the shot
    # type where FG edge framing matters, and the camera the #1
    # probe verified. The close legacy camera puts edge-framing
    # elements off-frame -- the pre-existing fenceFG pattern.
    return viewpoint_for_shot("establishing", elevation_deg=15.0)


def _traits(shot_index):
    timeline = json.loads(
        (JOBS / "req_3ee64748a857" / "timeline.json").read_text(
            encoding="utf-8"))
    return timeline["shots"][shot_index]["v1_location"]


def _by_id(pkg):
    return {e["id"]: e for e in pkg["elements"]}


def _dist(c1, c2):
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5


class TestFarRidges(unittest.TestCase):
    def test_ridge_row_present_farther_and_paler(self):
        pkg = build_environment(_traits(1), time_of_day="morning",
                                style={"mood": "warm"})
        ids = _by_id(pkg)
        ridges = [ids[f"sky_ridge_{i}"] for i in range(4)]
        hills = [ids[f"sky_hill_{i}"] for i in range(3)]
        sky_bottom = pkg["light"]["sky_bottom"]
        for r in ridges:
            self.assertEqual(r["kind"], "distant_hill")
            self.assertEqual(r["geometry"], "blob")
            self.assertLess(r["center"][2], -29.0)
        # Atmospheric perspective: the far row hazes further
        # toward the sky than the near row.
        ridge_haze = sum(_dist(r["color"], sky_bottom)
                         for r in ridges) / len(ridges)
        hill_haze = sum(_dist(h["color"], sky_bottom)
                        for h in hills) / len(hills)
        self.assertLess(ridge_haze, hill_haze)
        # Far tops clear the near row in world units.
        ridge_top = max(r["center"][1] + r["size"][1] / 2
                        for r in ridges)
        hill_top = max(h["center"][1] + h["size"][1] / 2
                       for h in hills)
        self.assertGreater(ridge_top, hill_top)
        self.assertEqual(pkg.get("validation"), [])


class TestDistantSkyline(unittest.TestCase):
    def test_houses_tower_and_roofs(self):
        pkg = build_environment(_traits(1), time_of_day="morning",
                                style={"mood": "warm"})
        ids = _by_id(pkg)
        for i in range(4):
            wall = ids[f"skyline_{i}"]
            self.assertEqual(wall["kind"], "distant_house")
            self.assertEqual(wall["geometry"], "box")
            self.assertLessEqual(wall["center"][2], -20.0)
            self.assertGreaterEqual(wall["center"][2], -22.0)
            roof = ids[f"skyline_roof_{i}"]
            self.assertEqual(roof["geometry"], "gable_prism")
            self.assertEqual(
                roof["attachment"]["parent"], f"skyline_{i}")
        tower = ids["skyline_tower"]
        self.assertEqual(tower["kind"], "distant_tower")
        self.assertGreater(
            tower["size"][1],
            max(ids[f"skyline_{i}"]["size"][1] for i in range(4)))
        self.assertIn("skyline_spire", ids)
        self.assertEqual(pkg.get("validation"), [])

    def test_negative_constraint_drops_houses(self):
        traits = dict(_traits(1))
        traits["negative_constraints"] = ["no houses"]
        pkg = build_environment(traits, time_of_day="morning",
                                style={"mood": "warm"})
        ids = _by_id(pkg)
        for i in range(4):
            self.assertNotIn(f"skyline_{i}", ids)


class TestFgFoliage(unittest.TestCase):
    def test_present_outdoors_absent_enclosed(self):
        road = build_environment(_traits(1), time_of_day="morning",
                                 style={"mood": "warm"})
        ids = _by_id(road)
        for side in ("L", "R"):
            el = ids[f"fg_foliage_{side}"]
            self.assertEqual(el["layer"], "FG")
            self.assertEqual(el["kind"], "canopy")
            self.assertEqual(el["geometry"], "blob")
        for idx in (3, 9, 11):  # forge, cave, interior
            pkg = build_environment(_traits(idx),
                                    time_of_day="midday",
                                    style={"mood": "warm"})
            got = [e["id"] for e in pkg["elements"]
                   if e["id"].startswith("fg_foliage_")]
            self.assertEqual(got, [], f"shot {idx}")

    def test_foliage_projects_to_frame_edges(self):
        pkg = build_environment(_traits(1), time_of_day="morning",
                                style={"mood": "warm"})
        cam = _establishing_camera()
        ids = _by_id(pkg)
        for side, edge in (("L", "left"), ("R", "right")):
            bbox = _projected_bbox(ids[f"fg_foliage_{side}"], cam,
                                   1920, 1080)
            self.assertIsNotNone(bbox, side)
            x0, y0, x1, y1 = bbox
            # Edge framing: the mass bleeds off its frame edge,
            # and its VISIBLE portion stays in the outer third.
            ix0, ix1 = max(x0, 0.0), min(x1, 1920.0)
            iy0, iy1 = max(y0, 0.0), min(y1, 1080.0)
            self.assertGreater(ix1, ix0, f"{side}: off-frame")
            # Actually visible (not fully above the frame) and a
            # corner fringe, not a dominant mass (frame-rejected
            # at 25% per side on the first sizing).
            self.assertGreater(iy1 - iy0, 40.0, f"{side}: not visible")
            if edge == "left":
                self.assertLess(ix1, 640, f"bbox {bbox}")
            else:
                self.assertGreater(ix0, 1280, f"bbox {bbox}")
            area = (ix1 - ix0) * (iy1 - iy0) / (1920 * 1080)
            self.assertLessEqual(area, 0.15)

    def test_fg_composition_ok_without_subjects(self):
        pkg = build_environment(_traits(1), time_of_day="morning",
                                style={"mood": "warm"})
        cam = _establishing_camera()
        result = validate_fg_composition(pkg, cam)
        # fenceFG is off-frame for head-on cameras (pre-existing:
        # it enters frame only under azimuth cameras). The new
        # foliage must raise no error of its own.
        foliage_errors = [e for e in result["errors"]
                          if "fg_foliage_" in e]
        self.assertEqual(foliage_errors, [])
        for el in result["elements"]:
            if el["id"].startswith("fg_foliage_"):
                self.assertTrue(el["in_frame"], el)
                self.assertLessEqual(el["area_fraction"], 0.40)

    def test_deterministic(self):
        a = build_environment(_traits(1), time_of_day="morning",
                              style={"mood": "warm"})
        b = build_environment(_traits(1), time_of_day="morning",
                              style={"mood": "warm"})
        self.assertEqual(
            [(e["id"], e["center"], e["size"]) for e in a["elements"]],
            [(e["id"], e["center"], e["size"]) for e in b["elements"]])


if __name__ == "__main__":
    unittest.main()
