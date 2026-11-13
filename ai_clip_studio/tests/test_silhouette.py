"""Tests for silhouette identity differentiation (Phase D).

Identity must read without colour: two characters that differ only
by suit colour are INDISTINGUISHABLE here by design.
"""
from __future__ import annotations

import unittest

from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.animation.silhouette import (
    distinguishable,
    grayscale_features,
    identity_signature,
    pairwise_report,
    shape_distance,
)


class TestSilhouetteIdentity(unittest.TestCase):
    def test_identical_characters_are_indistinguishable(self):
        a = Stickman(height=560, hat="none", moustache_style="none")
        b = Stickman(height=560, hat="none", moustache_style="none")
        result = distinguishable(a, b)
        self.assertFalse(result["distinguishable"])
        self.assertEqual(result["distance"], 0.0)

    def test_colour_only_difference_is_indistinguishable(self):
        a = Stickman(height=560, suit="#172033", hat="none",
                     moustache_style="none")
        b = Stickman(height=560, suit="#8B0000", hat="none",
                     moustache_style="none")
        result = distinguishable(a, b)
        self.assertFalse(result["distinguishable"])
        self.assertEqual(result["distance"], 0.0)
        self.assertEqual(
            grayscale_features(identity_signature(a)),
            grayscale_features(identity_signature(b)))

    def test_hat_difference_distinguishes(self):
        a = Stickman(height=560, hat="none", moustache_style="none")
        b = Stickman(height=560, hat="bowler", moustache_style="none")
        result = distinguishable(a, b)
        self.assertTrue(result["distinguishable"])
        self.assertIn("hat", result["differing"])

    def test_moustache_alone_does_not_distinguish(self):
        a = Stickman(height=560, hat="none", moustache_style="none")
        b = Stickman(height=560, hat="none", moustache_style="full")
        result = distinguishable(a, b)
        self.assertFalse(result["distinguishable"])
        self.assertEqual(result["distance"], 1.0)

    def test_lustig_vs_soldier_distinguishes(self):
        lustig = Stickman(height=560, hat="bowler",
                          moustache_style="full", costume="none",
                          body_variant="standard")
        soldier = Stickman(height=560, hat="none",
                           moustache_style="toothbrush",
                           costume="uniform", body_variant="slim")
        result = distinguishable(lustig, soldier)
        self.assertTrue(result["distinguishable"])
        self.assertIn("hat", result["differing"])
        self.assertIn("costume", result["differing"])

    def test_giant_height_contributes(self):
        adult = Stickman(height=560, hat="none", moustache_style="none")
        giant = Stickman(height=972, hat="none", moustache_style="none")
        distance = shape_distance(identity_signature(adult),
                                  identity_signature(giant))
        # 4.0 * (972-560)/972 = 1.70: height alone is not enough.
        self.assertAlmostEqual(distance, 4.0 * 412.0 / 972.0, places=3)
        self.assertFalse(distinguishable(adult, giant)["distinguishable"])

    def test_dict_trait_input(self):
        a = {"template": "male", "body_variant": "standard",
             "hat": "none", "hair_style": "short",
             "moustache_style": "none", "glasses": False, "cane": False,
             "costume": "none", "H": 560}
        b = dict(a, hat="bowler")
        self.assertTrue(distinguishable(a, b)["distinguishable"])

    def test_pairwise_report(self):
        chars = {
            "plain": Stickman(height=560, hat="none",
                              moustache_style="none"),
            "bowler": Stickman(height=560, hat="bowler",
                               moustache_style="none"),
            "dress": Stickman(height=560, hat="none",
                              moustache_style="none", costume="dress",
                              hair_style="long"),
        }
        report = pairwise_report(chars)
        self.assertEqual(len(report), 3)
        by_pair = {(r["a"], r["b"]): r for r in report}
        self.assertTrue(by_pair[("plain", "bowler")]["distinguishable"])
        # dress (2.0) + long hair (2.0) = 4.0: distinguishes.
        self.assertTrue(by_pair[("plain", "dress")]["distinguishable"])
        self.assertTrue(by_pair[("bowler", "dress")]["distinguishable"])


if __name__ == "__main__":
    unittest.main()
