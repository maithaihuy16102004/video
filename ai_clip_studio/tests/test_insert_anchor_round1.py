"""RicksClips loop round 1 -- insert anchors include the holder's
hands, not just the prop median (leg-only / head-only inserts)."""
import unittest

from ai_clip_studio.product_renderer import _insert_anchor_subjects


def _entry(draws, hands):
    return {"t": 0.0, "frame": 0, "hands": hands, "draws": draws}


class TestInsertAnchorHands(unittest.TestCase):
    def test_prop_only_unchanged_without_hands(self):
        tel = [_entry([{"kind": "bolt", "x": 500.0, "y": 300.0}], {})]
        subjects, anchor = _insert_anchor_subjects(tel, [])
        # Prop-led box (hero-insert grammar): the bolt's
        # aspect-preserving footprint (76x156, round 6) x margin
        # gives a 180x234 box centred on the prop; the floor
        # binds the width only. No hands: no hand union, and
        # the face never defines the box.
        self.assertEqual(subjects, [{"cx": 500.0, "head_y": 183.0,
                                     "foot_y": 417.0, "half_w": 90.0}])
        self.assertFalse(anchor["hands_included"])
        self.assertEqual(anchor["n_hands"], 0)

    def test_hand_expansion_is_bounded(self):
        # Ground-level prop (y=950), holder hand at waist (y=550):
        # the old union ballooned the box to span hand + prop and
        # the prop shrank at the stepped-down scale. The hero
        # grammar bounds the hand expansion to one box height from
        # the prop centre: head_y == 950 - 114 == 836 (stone
        # footprint 76x76 x 1.5), and the hand stays recorded
        # (hands_included) without defining the frame.
        tel = [_entry(
            [{"kind": "stone", "x": 500.0, "y": 950.0,
              "holder": "An", "hand": "r"}],
            {"An": {"hand_r": [520.0, 550.0],
                    "hand_l": [400.0, 600.0]}})]
        subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertEqual(subjects, [{"cx": 500.0, "head_y": 836.0,
                                     "foot_y": 1007.0, "half_w": 90.0}])
        self.assertTrue(anchor["hands_included"])
        self.assertEqual((anchor["hand_x"], anchor["hand_y"]),
                         (520.0, 550.0))

    def test_other_kind_draws_do_not_pollute_hands(self):
        tel = [_entry(
            [{"kind": "bolt", "x": 500.0, "y": 300.0,
              "holder": "Zeus", "hand": "r"},
             {"kind": "stone", "x": 100.0, "y": 900.0,
              "holder": "Zeus", "hand": "l"}],
            {"Zeus": {"hand_r": [510.0, 310.0],
                      "hand_l": [110.0, 910.0]}}),
            _entry(
            [{"kind": "bolt", "x": 500.0, "y": 300.0,
              "holder": "Zeus", "hand": "r"}],
            {"Zeus": {"hand_r": [510.0, 310.0],
                      "hand_l": [110.0, 910.0]}})]
        # Bolt dominates (2 draws vs 1): only bolt-holder hands count.
        subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertEqual(anchor["kind"], "bolt")
        self.assertEqual(anchor["n_hands"], 2)
        self.assertEqual((anchor["hand_x"], anchor["hand_y"]),
                         (510.0, 310.0))
        self.assertGreater(subjects[0]["head_y"], 100.0)

    def test_handover_hands_from_both_holders(self):
        tel = [
            _entry([{"kind": "bolt", "x": 400.0, "y": 500.0,
                     "holder": "Cyclops", "hand": "r"}],
                   {"Cyclops": {"hand_r": [410.0, 510.0]}}),
            _entry([{"kind": "bolt", "x": 600.0, "y": 500.0,
                     "holder": "Zeus", "hand": "r"}],
                   {"Zeus": {"hand_r": [590.0, 510.0]}}),
        ]
        subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertEqual(anchor["n_hands"], 2)
        self.assertTrue(anchor["pair_anchored"])
        self.assertEqual(anchor["n_pairs"], 2)
        # Hand median sits mid-exchange; the anchor is the pair
        # median (500, 500) with the footprint box (180x234).
        # The 5x crop is centred on the pair median, so both
        # prop positions (400/600, 100 px from the centre) stay
        # in frame -- the old union-span assertion pinned the
        # ballooning box the hero grammar replaced.
        self.assertEqual(anchor["hand_x"], 500.0)
        self.assertEqual(subjects, [{"cx": 500.0, "head_y": 383.0,
                                     "foot_y": 617.0, "half_w": 90.0}])

    def test_missing_holder_or_hand_is_ignored(self):
        tel = [_entry(
            [{"kind": "bolt", "x": 500.0, "y": 300.0,
              "holder": "Ghost", "hand": "r"},
             {"kind": "bolt", "x": 500.0, "y": 300.0,
              "holder": "An", "hand": None}],
            {"An": {"hand_r": [510.0, 310.0]}})]
        _, anchor = _insert_anchor_subjects(tel, [])
        self.assertFalse(anchor["hands_included"])
        self.assertEqual(anchor["n_hands"], 0)


if __name__ == "__main__":
    unittest.main()
