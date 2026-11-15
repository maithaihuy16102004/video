"""Round 15 (L02-D6): the sun/moon disc avoids subject heads.

A candidate window whose disc would sit behind a head box is
penalised out of the running; clear placements are untouched,
and when every window overlaps a head the disc still renders
(best effort).
"""
import json
import unittest

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import (
    build_environment,
    sun_disc_spec,
)


def _night_pkg():
    timeline = json.load(open(
        "/home/hatch/workspace/agent/jobs/req_b1f6b9669724/"
        "timeline.json"))
    loc = timeline["shots"][13]["v1_location"]  # SC04, seaside, night
    return build_environment(loc, time_of_day="night",
                             style={"mood": "warm"})


def _spec(pkg, avoid_boxes=None, visible_rect=None):
    cam = viewpoint_for_shot("medium", "eye_level")
    return sun_disc_spec(pkg["light"], pkg["elements"], cam,
                         1920, 1080, 330.0, "avoid-probe",
                         visible_rect=visible_rect,
                         avoid_boxes=avoid_boxes)


def _bbox(spec):
    cx, cy = spec["center"]
    r = spec["radius"]
    return (cx - r, cy - r, cx + r, cy + r)


def _overlaps(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


class TestSunHeadAvoidanceRound15(unittest.TestCase):
    def test_disc_moves_off_a_head(self):
        pkg = _night_pkg()
        base = _spec(pkg)
        self.assertTrue(base["is_moon"])
        bx0, by0, bx1, by1 = _bbox(base)
        box = (bx0 - 4, by0 - 4, bx1 + 4, by1 + 4)
        moved = _spec(pkg, avoid_boxes=[box])
        self.assertNotEqual(moved["center"], base["center"])
        self.assertFalse(_overlaps(_bbox(moved), box))

    def test_clear_placement_unchanged(self):
        pkg = _night_pkg()
        base = _spec(pkg)
        far = _spec(pkg, avoid_boxes=[(0, 900, 100, 1000)])
        self.assertEqual(far, base)

    def test_all_overlapping_still_renders(self):
        pkg = _night_pkg()
        spec = _spec(pkg, avoid_boxes=[(0, 0, 1920, 1080)])
        self.assertIsNotNone(spec)
        cx, cy = spec["center"]
        r = spec["radius"]
        self.assertGreaterEqual(cx - r, 0)
        self.assertGreaterEqual(cy - r, 0)

    def test_avoidance_respects_visible_rect(self):
        pkg = _night_pkg()
        rect = (360, 60, 1560, 735)
        base = _spec(pkg, visible_rect=rect)
        bx0, by0, bx1, by1 = _bbox(base)
        box = (bx0 - 4, by0 - 4, bx1 + 4, by1 + 4)
        moved = _spec(pkg, avoid_boxes=[box], visible_rect=rect)
        self.assertFalse(_overlaps(_bbox(moved), box))
        cx, cy = moved["center"]
        r = moved["radius"]
        self.assertGreaterEqual(cx - r, rect[0])
        self.assertLessEqual(cx + r, rect[2])
        self.assertGreaterEqual(cy - r, rect[1])
        self.assertLessEqual(cy + r, rect[3])


if __name__ == "__main__":
    unittest.main()
