"""Round 13 (R13-1): richness WITHIN layers. The round-12 layer
structure (ridges, skyline, FG foliage) is complete; the tester
found each layer primitive in kind (R11-D2, R12-D1). FG foliage
becomes branch + jittered lobes (the _tree treatment); hills get
seeded silhouette skew + varying flank sides; skyline houses get
chimneys + windows that glow at dusk/night. Element-presence +
render pins; the visual read lives on delivered frames.
"""

import json
import math
import unittest
from pathlib import Path

import numpy as np

from ai_clip_studio.camera_planner import (
    PerspectiveCamera, viewpoint_for_shot)
from ai_clip_studio.environment_v2 import (
    build_environment, render_environment,
    validate_fg_composition)

JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _traits(shot_index):
    timeline = json.loads(
        (JOBS / "req_3ee64748a857" / "timeline.json").read_text(
            encoding="utf-8"))
    return timeline["shots"][shot_index]["v1_location"]


def _by_id(pkg):
    return {e["id"]: e for e in pkg["elements"]}


class TestFgFoliageCluster(unittest.TestCase):
    def test_branch_and_lobes_per_side(self):
        pkg = build_environment(_traits(1), time_of_day="morning",
                                style={"mood": "warm"})
        ids = _by_id(pkg)
        for side in ("L", "R"):
            core = ids[f"fg_foliage_{side}"]
            self.assertEqual(core["kind"], "canopy")
            branch = ids[f"fg_foliage_{side}_branch"]
            self.assertEqual(branch["kind"], "branch")
            self.assertEqual(branch["geometry"], "box")
            self.assertEqual(
                branch["attachment"]["parent"], core["id"])
            lobes = [ids[f"fg_foliage_{side}_lobe{i}"]
                     for i in range(3)]
            for lobe in lobes:
                self.assertEqual(lobe["kind"], "canopy")
                self.assertEqual(
                    lobe["attachment"]["parent"], core["id"])
            # Lobe tones jitter: not all identical to the core.
            colors = {tuple(l["color"]) for l in lobes}
            colors.add(tuple(core["color"]))
            self.assertGreater(len(colors), 1)

    def test_cluster_stays_corner_fringe(self):
        pkg = build_environment(_traits(1), time_of_day="morning",
                                style={"mood": "warm"})
        cam = viewpoint_for_shot("establishing",
                                 elevation_deg=15.0)
        result = validate_fg_composition(pkg, cam)
        foliage_errors = [e for e in result["errors"]
                          if "fg_foliage_" in e]
        self.assertEqual(foliage_errors, [])
        for el in result["elements"]:
            if el["id"].startswith("fg_foliage_"):
                self.assertTrue(el["in_frame"], el)
                self.assertLessEqual(el["area_fraction"], 0.40)

    def test_absent_enclosed(self):
        for idx in (3, 9, 11):  # forge, cave, interior
            pkg = build_environment(_traits(idx),
                                    time_of_day="midday",
                                    style={"mood": "warm"})
            got = [e["id"] for e in pkg["elements"]
                   if e["id"].startswith("fg_foliage_")]
            self.assertEqual(got, [], f"shot {idx}")


class TestHillSkew(unittest.TestCase):
    def _hill_pkg(self):
        return build_environment(_traits(1), time_of_day="morning",
                                 style={"mood": "warm"})

    def test_silhouettes_skewed_and_shaded(self):
        pkg = self._hill_pkg()
        cam = PerspectiveCamera(
            position=(0.0, 1.2 + 7.5 * math.sin(math.radians(15.0)),
                      7.5 * math.cos(math.radians(15.0))),
            target=(0.0, 1.2, 0.0), fov_deg=46.0, aspect=16.0 / 9.0)
        hills = [e for e in pkg["elements"]
                 if e.get("kind") == "distant_hill"]
        self.assertEqual(len(hills), 7)
        all_ids = {e["id"] for e in pkg["elements"]}
        max_skew = 0.0
        for hill in hills:
            solo = np.asarray(render_environment(
                pkg, cam, (1920, 1080),
                exclude_ids=all_ids - {hill["id"]}).convert(
                "RGB")).astype(float)
            x, y, scale, vis = cam.project(hill["center"],
                                           1920, 1080)
            self.assertTrue(vis)
            cx, cy = int(x), int(y)
            ry = hill["size"][1] / 2 * scale
            # Gradient survives the skew: cap brighter than mid.
            # Round 14: peaked ridge hills sample inside the
            # silhouette on both sides of the cap boundary --
            # the dome cap sample (cy - 0.7ry) can land in a
            # valley (sky) or in the cap tone, and cy itself is
            # INSIDE the ridge cap polygon (it extends to
            # y + 0.05ry), so both dome samples read the same.
            # Ridge cap at cy - 0.5ry is inside (ridgeline >=
            # 0.55ry above centre at cx) and reads the 1.10 cap
            # tone; cy + 0.5ry reads the 0.94 base fill.
            if (hill.get("extra") or {}).get("ridge"):
                cap = solo[max(0, cy - int(0.5 * ry)), cx].mean()
                mid = solo[min(1079, cy + int(0.5 * ry)),
                           cx].mean()
            else:
                cap = solo[max(0, cy - int(0.7 * ry)), cx].mean()
                mid = solo[cy, cx].mean()
            self.assertGreater(float(cap - mid), 3.0, hill["id"])
            # Skew: left/right extents of the silhouette at the
            # centre row differ (sky = the top-left pixel).
            sky = solo[0, 0]
            row = solo[cy]
            mask = np.abs(row - sky).sum(axis=1) > 12
            xs = np.nonzero(mask)[0]
            left = cx - xs.min()
            right = xs.max() - cx
            max_skew = max(max_skew, abs(float(left - right)))
        self.assertGreater(max_skew, 8.0)


class TestFoliageSilhouette(unittest.TestCase):
    def test_bumpy_not_disc(self):
        # Round 13: the foliage silhouette modulates +-16%, so
        # the ellipse-normalized radius varies (0.08 measured;
        # a perfect ellipse scores ~0.00).
        import random
        from PIL import Image, ImageDraw
        from ai_clip_studio.environment_v2 import (
            _draw_foliage_blob)
        img = Image.new("RGB", (400, 300), (200, 210, 220))
        draw = ImageDraw.Draw(img)
        _draw_foliage_blob(draw, 200, 150, 120, 80, (84, 110, 66),
                           (50, 66, 40), random.Random(7))
        arr = np.asarray(img).astype(float)
        sky = np.array([200.0, 210.0, 220.0])
        mask = np.abs(arr - sky).sum(axis=2) > 12
        rs = []
        for k in range(36):
            ang = 2 * math.pi * k / 36
            for r in range(200, 0, -1):
                px = int(200 + r * math.cos(ang))
                py = int(150 + r * math.sin(ang))
                if 0 <= px < 400 and 0 <= py < 300 and mask[py, px]:
                    er = 1.0 / math.sqrt(
                        (math.cos(ang) / 120) ** 2
                        + (math.sin(ang) / 80) ** 2)
                    rs.append(r / er)
                    break
        self.assertEqual(len(rs), 36)
        rs = np.array(rs)
        self.assertGreater(float(rs.std() / rs.mean()), 0.03)


class TestSkylineDetail(unittest.TestCase):
    def test_chimneys_and_windows(self):
        pkg = build_environment(_traits(1), time_of_day="dusk",
                                style={"mood": "warm"})
        ids = _by_id(pkg)
        for i in range(4):
            chim = ids[f"skyline_chimney_{i}"]
            self.assertEqual(chim["kind"], "house_chimney")
            self.assertEqual(chim["attachment"]["parent"],
                             f"skyline_roof_{i}")
            for j in range(2):
                win = ids[f"skyline_win_{i}_{j}"]
                self.assertEqual(win["kind"], "house_window")
                # Glass material: the unshaded rule keeps the
                # pane bright; the light rule needs kind
                # "window" exactly (see the no-lights test).
                self.assertEqual(win["material"], "glass")
                # Lit at dusk: warm, red over blue.
                self.assertGreater(win["color"][0]
                                   - win["color"][2], 50)
        tower_win = ids["skyline_tower_win"]
        self.assertEqual(tower_win["kind"], "tower_window")
        self.assertGreater(tower_win["color"][0]
                           - tower_win["color"][2], 50)
        self.assertEqual(pkg.get("validation"), [])

    def test_windows_dark_by_day(self):
        pkg = build_environment(_traits(1), time_of_day="midday",
                                style={"mood": "warm"})
        ids = _by_id(pkg)
        win = ids["skyline_win_0_0"]
        self.assertLess(win["color"][0] - win["color"][2], 0)

    def test_no_houses_drops_house_parts_tower_stays(self):
        traits = dict(_traits(1))
        traits["negative_constraints"] = ["no houses"]
        pkg = build_environment(traits, time_of_day="morning",
                                style={"mood": "warm"})
        ids = _by_id(pkg)
        for i in range(4):
            self.assertNotIn(f"skyline_{i}", ids)
            self.assertNotIn(f"skyline_roof_{i}", ids)
            self.assertNotIn(f"skyline_chimney_{i}", ids)
            self.assertNotIn(f"skyline_win_{i}_0", ids)
        # The tower is not a house: it and its parts stay.
        self.assertIn("skyline_tower", ids)
        self.assertIn("skyline_spire", ids)
        self.assertIn("skyline_tower_win", ids)

    def test_no_towers_drops_tower_parts_houses_stay(self):
        traits = dict(_traits(1))
        traits["negative_constraints"] = ["no towers"]
        pkg = build_environment(traits, time_of_day="morning",
                                style={"mood": "warm"})
        ids = _by_id(pkg)
        self.assertNotIn("skyline_tower", ids)
        self.assertNotIn("skyline_spire", ids)
        self.assertNotIn("skyline_tower_win", ids)
        self.assertIn("skyline_0", ids)
        self.assertIn("skyline_roof_0", ids)

    def test_no_windows_drops_skyline_windows_only(self):
        traits = dict(_traits(1))
        traits["negative_constraints"] = ["no windows"]
        pkg = build_environment(traits, time_of_day="morning",
                                style={"mood": "warm"})
        ids = _by_id(pkg)
        self.assertIn("skyline_0", ids)
        self.assertNotIn("skyline_win_0_0", ids)
        self.assertNotIn("skyline_tower_win", ids)

    def test_skyline_windows_emit_no_point_lights(self):
        pkg = build_environment(_traits(1), time_of_day="dusk",
                                style={"mood": "warm"})
        leaked = [pl["id"] for pl in pkg["point_lights"]
                  if "skyline" in pl["id"]]
        self.assertEqual(leaked, [])


if __name__ == "__main__":
    unittest.main()
