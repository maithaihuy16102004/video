"""Round 10 (R9-D1): a progression segment is a NEW shot by cut,
not the directive's shot. It keeps the directive's elevation-only
angle but never inherits over_shoulder: that angle names an
azimuth (28 deg OTS), which blocks the viewpoint flip and froze
shot #9's camera across rounds while every other eligible shot
moved. The plan below reproduces the delivered 17-shot Loop-01
plan (real line durations from the R9 job's timeline).
"""

import json
import math
import unittest
from pathlib import Path

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.product_renderer import plan_shots
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _loop01_plan():
    text = (EXAMPLES / "loop_test_01_fire_stone.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    lines = json.loads(
        (JOBS / "req_76dd3116401c" / "timeline.json").read_text(
            encoding="utf-8"))["lines"]
    return plan_shots(package, lines)


def _azimuth(shot):
    cam = viewpoint_for_shot(
        shot["shot_type"], shot.get("camera_angle"),
        subject_pos=(0.0, 1.2, 0.0),
        azimuth_side=shot.get("viewpoint_azimuth_side"))
    return math.degrees(math.atan2(cam.position[0], cam.position[2]))


class TestProgressionAngleInheritance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shots = _loop01_plan()

    def test_plan_shape_unchanged(self):
        self.assertEqual(len(self.shots), 17)

    def test_ots_shot_keeps_its_angle_and_exemption(self):
        ots = next(s for s in self.shots
                   if s["shot_type"] == "over_the_shoulder")
        self.assertEqual(ots.get("camera_angle"), "over_shoulder")
        self.assertIsNone(ots.get("viewpoint_azimuth_side"))

    def test_progression_segment_drops_over_shoulder(self):
        seg = next(s for s in self.shots
                   if s.get("directive_shot_id") == "SC03_SH01"
                   and s.get("segment_index") == 1)
        self.assertEqual(seg["shot_type"], "reaction")
        self.assertNotEqual(seg.get("camera_angle"), "over_shoulder")
        self.assertEqual(seg.get("viewpoint_azimuth_side"), -1)
        self.assertAlmostEqual(_azimuth(seg), -18.0, places=6)

    def test_elevation_only_angles_still_inherited(self):
        for did in ("SC01_SH01", "SC02_SH01"):
            seg = next(s for s in self.shots
                       if s.get("directive_shot_id") == did
                       and s.get("segment_index") == 1)
            self.assertEqual(seg.get("camera_angle"), "high_angle")
            self.assertEqual(seg.get("viewpoint_azimuth_side"), -1)
            self.assertAlmostEqual(_azimuth(seg), -18.0, places=6)

    def test_every_eligible_shot_gets_a_live_side(self):
        exempt = {"establishing", "object_insert",
                  "over_the_shoulder", "shot_reverse_shot",
                  "graphic_insert"}
        for s in self.shots:
            if s["kind"] == "end_card" \
                    or s["shot_type"] in exempt:
                continue
            side = s.get("viewpoint_azimuth_side")
            self.assertIn(side, (-2, -1, 1, 2),
                          f"shot {s['shot_type']} has no live side")
            self.assertAlmostEqual(
                _azimuth(s), float(side) * 18.0, places=6)


if __name__ == "__main__":
    unittest.main()
