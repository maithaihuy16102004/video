"""Round 9 environment detail: field faces get the grass texture
(they rendered as flat-colour voids -- paint_grass existed but no
face-texture branch mapped "grass"), and countryside trees are
trait-led: leafy canopies by default, bare branching crowns only
when the traits name a bare season ("cây trụi lá", autumn,
winter). The bare crown itself branches at five staggered heights
instead of two signpost limbs.
"""

import unittest

import numpy as np

from ai_clip_studio.environment_v2 import build_environment
from ai_clip_studio.paint_textures import texture_for_material

BARE_TRAITS = {"id": "LOC_ROAD", "name": "Country road",
               "features": ["Đường đất.", "Đồng quê châu Âu.",
                            "Cây trụi lá.", "Binh lính hành quân."],
               "period": "1914"}
LEAFY_TRAITS = {"id": "LOC_V", "name": "Village",
                "features": ["Làng quê.", "Đường đất.", "Cây xanh.",
                             "Nhà tranh."]}


def _kinds(env):
    kinds = {}
    for e in env["elements"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    return kinds


class TestGrassTexture(unittest.TestCase):
    def test_grass_maps_to_a_varied_texture(self):
        tex = texture_for_material("grass", (128, 138, 84),
                                   9.0, 22.0, 12345)
        self.assertIsNotNone(tex)
        self.assertGreater(float(np.asarray(tex).std()), 10.0)

    def test_grass_texture_deterministic(self):
        a = texture_for_material("grass", (128, 138, 84),
                                 9.0, 22.0, 7)
        b = texture_for_material("grass", (128, 138, 84),
                                 9.0, 22.0, 7)
        self.assertEqual(np.asarray(a).tobytes(),
                         np.asarray(b).tobytes())


class TestTraitLedTrees(unittest.TestCase):
    def test_bare_traits_keep_bare_branching_crowns(self):
        env = build_environment(BARE_TRAITS, time_of_day="day")
        kinds = _kinds(env)
        self.assertEqual(env["archetype"], "COUNTRYSIDE_ROAD")
        self.assertEqual(kinds.get("tree_trunk"), 4)
        # Round 10: 20 limbs + 40 twigs (2 per limb) -- twigs share
        # the "branch" kind. Round 13: + 2 FG foliage branches.
        # The trait-led guarantee is about the
        # TREES: no leafy tree canopies. The 10 remaining canopies
        # are the Round-10 distant treeline crowns, silhouette
        # masses present in every season (like the hedgerows).
        self.assertEqual(kinds.get("branch"), 62)
        self.assertEqual([e["id"] for e in env["elements"]
                          if e["kind"] == "canopy"
                          and e["id"].startswith("tree_")], [])
        self.assertEqual(sum(1 for e in env["elements"]
                             if e["kind"] == "canopy"
                             and e["id"].startswith("treeline_")), 10)

    def test_neutral_traits_get_leafy_canopies(self):
        env = build_environment(LEAFY_TRAITS, time_of_day="morning")
        kinds = _kinds(env)
        self.assertEqual(env["archetype"], "COUNTRYSIDE_ROAD")
        # Round 10: 16 tree canopies + 10 distant treeline crowns.
        # Round 12: + 2 foreground foliage canopies (fg_foliage_).
        # Round 13: + 6 FG foliage lobes (3 per side).
        self.assertEqual(kinds.get("canopy"), 34)
        self.assertEqual(sum(1 for e in env["elements"]
                             if e["id"].startswith("fg_foliage_")),
                         10)
        # Round 13: the only branches are the 2 FG foliage limbs;
        # leafy trees carry no bare limbs/twigs.
        self.assertEqual(kinds.get("branch", 0), 2)

    def test_winter_word_also_bare(self):
        traits = dict(LEAFY_TRAITS)
        traits["features"] = ["Làng quê.", "Mùa đông."]
        env = build_environment(traits, time_of_day="day")
        kinds = _kinds(env)
        # Round 10: 20 limbs + 40 twigs; Round 13: + 2 FG foliage
        # branches. No tree canopies, and the
        # 10 treeline crowns (see test_bare_traits_... above).
        self.assertEqual(kinds.get("branch"), 62)
        self.assertEqual([e["id"] for e in env["elements"]
                          if e["kind"] == "canopy"
                          and e["id"].startswith("tree_")], [])
        self.assertEqual(sum(1 for e in env["elements"]
                             if e["kind"] == "canopy"
                             and e["id"].startswith("treeline_")), 10)

    def test_builds_deterministic(self):
        a = build_environment(LEAFY_TRAITS, time_of_day="morning")
        b = build_environment(LEAFY_TRAITS, time_of_day="morning")
        self.assertEqual(
            [(e["id"], e["kind"], e["center"], e["size"])
             for e in a["elements"]],
            [(e["id"], e["kind"], e["center"], e["size"])
             for e in b["elements"]])


if __name__ == "__main__":
    unittest.main()
