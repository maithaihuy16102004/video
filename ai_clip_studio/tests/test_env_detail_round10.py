"""Round 10 (R10-1): environment detail that reads at
full-frame distance. Sky dressing (clouds + rolling hills) for
every archetype, a varied treeline with crowns, foliage hedges,
branching bare trees, cave rock relief, interior wall dressing,
and a dirt texture for the road. Element-presence + validation
pins; the visual read lives on env renders (r10_env_*.png) and
delivered establishing frames.
"""

import json
import unittest
from pathlib import Path

from ai_clip_studio.environment_v2 import build_environment
from ai_clip_studio.paint_textures import texture_for_material

JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _traits(shot_index):
    timeline = json.loads(
        (JOBS / "req_3ee64748a857" / "timeline.json").read_text(
            encoding="utf-8"))
    return timeline["shots"][shot_index]["v1_location"]


def _by_id(pkg):
    return {e["id"]: e for e in pkg["elements"]}


class TestSkyDressing(unittest.TestCase):
    def test_clouds_and_hills_present_and_valid(self):
        for idx, tod in ((1, "morning"), (3, "midday"),
                         (9, "afternoon"), (11, "dusk")):
            pkg = build_environment(_traits(idx), time_of_day=tod,
                                    style={"mood": "warm"})
            ids = _by_id(pkg)
            hills = [i for i in ids if i.startswith("sky_hill_")]
            clouds = [i for i in ids if i.startswith("sky_cloud_")]
            self.assertEqual(len(hills), 3, f"shot {idx}")
            self.assertEqual(len(clouds), 4, f"shot {idx}")
            for i in clouds:
                self.assertEqual(ids[i]["kind"], "cloud")
                self.assertEqual(ids[i]["geometry"], "blob")
            for i in hills:
                self.assertEqual(ids[i]["geometry"], "blob")
            self.assertEqual(pkg.get("validation"), [],
                             f"shot {idx}: {pkg.get('validation')}")

    def test_deterministic(self):
        a = build_environment(_traits(1), time_of_day="morning",
                              style={"mood": "warm"})
        b = build_environment(_traits(1), time_of_day="morning",
                              style={"mood": "warm"})
        self.assertEqual(
            [(e["id"], e["center"], e["size"]) for e in a["elements"]],
            [(e["id"], e["center"], e["size"]) for e in b["elements"]])


class TestCountrysideDetail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg = build_environment(_traits(1), time_of_day="morning",
                                    style={"mood": "warm"})
        cls.ids = _by_id(cls.pkg)

    def test_treeline_varied_with_crowns(self):
        masses = [self.ids[f"treeline_{i}"] for i in range(7)]
        heights = {m["size"][1] for m in masses}
        self.assertGreater(len(heights), 3)
        crowns = [i for i in self.ids
                  if "_crown" in i and i.startswith("treeline_")]
        self.assertGreaterEqual(len(crowns), 7)

    def test_hedges_are_foliage_lobes(self):
        for i in range(3):
            core = self.ids[f"hedge_{i}_hedge"]
            self.assertLess(core["size"][1], 0.5)
            for j in range(3):
                lobe = self.ids[f"hedge_{i}_hedge_lobe{j}"]
                self.assertEqual(lobe["geometry"], "blob")

    def test_bare_trees_have_twigs(self):
        twigs = [i for i in self.ids if i.startswith("bare_twig_")]
        # 4 trees x 5 limbs x 2 twigs.
        self.assertEqual(len(twigs), 40)


class TestCaveAndInteriorDetail(unittest.TestCase):
    def test_cave_relief(self):
        pkg = build_environment(_traits(9), time_of_day="afternoon",
                                style={"mood": "warm"})
        ids = _by_id(pkg)
        self.assertEqual(len([i for i in ids
                              if i.startswith("backslab")]), 5)
        self.assertEqual(len([i for i in ids
                              if i.startswith("sideslab")]), 6)
        self.assertEqual(len([i for i in ids
                              if i.startswith("stalagmite")]), 3)
        self.assertEqual(len([i for i in ids
                              if i.startswith("roundrock")]), 2)
        self.assertEqual(pkg.get("validation"), [])

    def test_interior_wall_dressing(self):
        pkg = build_environment(_traits(11), time_of_day="dusk",
                                style={"mood": "warm"})
        ids = _by_id(pkg)
        for want in ("room_wainscot", "room_dado_rail",
                     "room_crown"):
            self.assertIn(want, ids)
        self.assertEqual(len([i for i in ids
                              if i.startswith("room_pilaster")]), 4)
        self.assertEqual(len([i for i in ids
                              if "_mull_" in i]), 6)
        self.assertEqual(pkg.get("validation"), [],
                         str(pkg.get("validation")))


class TestPackedEarthTexture(unittest.TestCase):
    def test_road_face_gets_texture(self):
        img = texture_for_material("packed_earth", (150, 128, 92),
                                   2.6, 22.0, seed=7)
        self.assertIsNotNone(img)


if __name__ == "__main__":
    unittest.main()
