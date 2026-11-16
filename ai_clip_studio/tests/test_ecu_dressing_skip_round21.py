"""Round 21 (R20-D1): the dressing loop must skip deferred-insert shots.

In Loop 02 #21 (ECU, key into the lock) the R20 dressing loop
pushed An +0.3 m chasing roadside dressing outside the 3.4x
insert crop; the world-static lock did not follow, so the
insert anchor shifted +76 px and the head left the delivered
frame. Insert shots frame the prop + hands, never the room,
so staging moves must not run there. The skip is narrow:
ordinary shots (Loop 02 #17) still get dressing moves.
"""
import tempfile
import unittest
from unittest import mock

import ai_clip_studio.product_renderer as pr
from ai_clip_studio.tests.test_cue_coverage_round18 import (
    _delivered_shot as _delivered_shot_l02,
)

JOB = "req_9525d57a99ee"  # Loop 02 R20 timeline (== R19 timeline)


def _ev(primitive, prop_id="key"):
    return {"required_pose": {"primitive": primitive}, "prop_id": prop_id}


class TestDeferredInsertPredicate(unittest.TestCase):
    def test_object_insert_always_deferred(self):
        self.assertTrue(pr._deferred_insert_shot(
            {"shot_type": "object_insert"}, []))

    def test_ecu_prop_action_deferred(self):
        self.assertTrue(pr._deferred_insert_shot(
            {"shot_type": "extreme_close_up"}, [_ev("insert_key")]))

    def test_ecu_without_prop_action_not_deferred(self):
        self.assertFalse(pr._deferred_insert_shot(
            {"shot_type": "extreme_close_up"}, [_ev("wave", None)]))
        self.assertFalse(pr._deferred_insert_shot(
            {"shot_type": "extreme_close_up"},
            [{"required_pose": {"primitive": "insert_key"}}]))

    def test_other_shot_types_not_deferred(self):
        for st in ("medium", "establishing", "reaction",
                   "medium_close_up", "over_the_shoulder"):
            self.assertFalse(pr._deferred_insert_shot(
                {"shot_type": st}, [_ev("insert_key")]), st)


class TestEcuDressingSkipRender(unittest.TestCase):
    def test_shot21_skips_dressing_and_matches_nodress_crop(self):
        package, shot = _delivered_shot_l02(21, job=JOB)
        with tempfile.TemporaryDirectory() as tmp:
            rep = pr._render_shot(
                {"shot": shot, "package": package, "out_dir": tmp,
                 "still_only": False})
        hc = rep["head_clearance"]
        self.assertEqual(hc["dressing_moves"], {})
        self.assertEqual(hc["unresolved_dressing"], [])
        # The unpatched render must equal the dressing-disabled
        # counterfactual exactly (same crop, same lock anchor).
        package2, shot2 = _delivered_shot_l02(21, job=JOB)
        with mock.patch.object(pr, "_dressing_rects", return_value=[]):
            with tempfile.TemporaryDirectory() as tmp:
                rep2 = pr._render_shot(
                    {"shot": shot2, "package": package2, "out_dir": tmp,
                     "still_only": False})
        self.assertEqual(rep["crop_anchor"], rep2["crop_anchor"])
        self.assertEqual(rep["lock_anchors"], rep2["lock_anchors"])

    def test_shot17_still_gets_dressing_moves(self):
        package, shot = _delivered_shot_l02(17, job=JOB)
        with tempfile.TemporaryDirectory() as tmp:
            rep = pr._render_shot(
                {"shot": shot, "package": package, "out_dir": tmp,
                 "still_only": False})
        moves = rep["head_clearance"]["dressing_moves"]
        self.assertIn("Bà Tư", moves)
        self.assertLess(moves["Bà Tư"]["moved_world"], 0.0)


if __name__ == "__main__":
    unittest.main()
