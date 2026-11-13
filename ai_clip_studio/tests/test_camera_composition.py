"""Unit tests for the P6 shot-composition extension of
ai_clip_studio.camera_planner (stdlib unittest).

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/agent/
"""
import math
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.camera_planner import (
    FULL_BODY_SHOT_TYPES,
    frame_mad,
    head_width_stability,
    plan_coverage,
    plan_shot,
    sky_band_mad,
)

DIRECTIVES_17 = [
    {"shot_id": "SC01_SH01", "shot_type": "establishing",
     "camera_angle": "high_angle", "camera_movement": "TRACKING",
     "camera": "WIDE_ESTABLISHING", "location_override": None},
    {"shot_id": "SC01_SH02", "shot_type": "close_up",
     "camera_angle": "eye_level", "camera_movement": "STATIC",
     "camera": "MEDIUM_CLOSEUP"},
    {"shot_id": "SC01_SH03", "shot_type": "reaction",
     "camera_angle": "eye_level", "camera_movement": "STATIC",
     "camera": "CLOSEUP_REACTION"},
    {"shot_id": "SC02_SH01", "shot_type": "establishing",
     "camera_angle": "birds_eye", "camera_movement": "DOLLY_IN",
     "camera": "HISTORICAL_MAP_OVERVIEW"},
    {"shot_id": "SC03_SH01", "shot_type": "medium",
     "camera_angle": "eye_level", "camera_movement": "DOLLY_IN",
     "camera": "MEDIUM_SIDE_SHOT"},
    {"shot_id": "SC03_SH02", "shot_type": "object_insert",
     "camera_angle": "high_angle", "camera_movement": "STATIC",
     "camera": "OBJECT_INSERT_CLOSEUP"},
    {"shot_id": "SC03_SH03", "shot_type": "medium",
     "camera_angle": "eye_level", "camera_movement": "STATIC",
     "camera": "MEDIUM_SHOT"},
    {"shot_id": "SC04_SH01", "shot_type": "medium",
     "camera_angle": "eye_level", "camera_movement": "STATIC",
     "camera": "MEDIUM_TWO_SHOT"},
    {"shot_id": "SC04_SH02", "shot_type": "shot_reverse_shot",
     "camera_angle": "eye_level", "camera_movement": "STATIC",
     "camera": "CLOSEUP_REVERSE", "srs_side": False},
    {"shot_id": "SC04_SH03", "shot_type": "over_the_shoulder",
     "camera_angle": "over_shoulder", "camera_movement": "STATIC",
     "camera": "OVER_THE_SHOULDER", "subject": "Adolf Hitler"},
    {"shot_id": "SC04_SH04", "shot_type": "reaction",
     "camera_angle": "eye_level", "camera_movement": "STATIC",
     "camera": "CLOSEUP_REACTION"},
    {"shot_id": "SC05_SH01", "shot_type": "establishing",
     "camera_angle": "birds_eye", "camera_movement": "STATIC",
     "camera": "HISTORICAL_MAP_OVERVIEW",
     "location_override": "LOC_EUROPE_MAP"},
    {"shot_id": "SC05_SH02", "shot_type": "tracking",
     "camera_angle": "eye_level", "camera_movement": "STATIC",
     "camera": "WIDE_TRACKING"},
    {"shot_id": "SC06_SH01", "shot_type": "establishing",
     "camera_angle": "high_angle", "camera_movement": "PAN_RIGHT",
     "camera": "WIDE_ENVIRONMENTAL_ESTABLISHING"},
    {"shot_id": "SC06_SH02", "shot_type": "tracking",
     "camera_angle": "eye_level", "camera_movement": "STATIC",
     "camera": "MEDIUM_TRACKING"},
    {"shot_id": "SC06_SH03", "shot_type": "close_up",
     "camera_angle": "eye_level", "camera_movement": "STATIC",
     "camera": "MEDIUM_CLOSEUP"},
    {"shot_id": "SC06_SH04", "shot_type": "close_up",
     "camera_angle": "eye_level", "camera_movement": "STATIC",
     "camera": "CLOSEUP"},
]

SCENE = {"character_positions": {"Adolf Hitler": (-0.8, 0.0, 0.0),
                                 "Soldier": (0.8, 0.0, 0.0)}}


class TestPlanShot(unittest.TestCase):
    def test_pose_is_real_geometry(self):
        entry = plan_shot(DIRECTIVES_17[0], scene=SCENE)
        self.assertEqual(entry["shot_id"], "SC01_SH01")
        self.assertEqual(len(entry["camera_position"]), 3)
        self.assertEqual(len(entry["target"]), 3)
        self.assertEqual(entry["fov"], 46.0)
        self.assertEqual(entry["pose"]["angle"], "high_angle")
        self.assertGreater(entry["pose"]["elevation_deg"], 20.0)

    def test_establishing_uses_wide_radius(self):
        est = plan_shot(DIRECTIVES_17[0], scene=SCENE)
        med = plan_shot(DIRECTIVES_17[6], scene=SCENE)
        self.assertAlmostEqual(est["pose"]["radius"], 7.5, places=2)
        self.assertLess(med["pose"]["radius"], 6.0)

    def test_f2_cap_on_full_body_types(self):
        for shot_type in FULL_BODY_SHOT_TYPES:
            entry = plan_shot({"shot_id": "X", "shot_type": shot_type})
            self.assertLessEqual(entry["framing"]["crop_scale"], 1.0,
                                 shot_type)
        close = plan_shot({"shot_id": "X", "shot_type": "close_up"})
        self.assertEqual(close["framing"]["crop_scale"], 2.6)

    def test_movement_override_documented(self):
        entry = plan_shot(DIRECTIVES_17[0], scene=SCENE)
        decision = entry["movement_decision"]
        self.assertEqual(decision["requested"], "TRACKING")
        self.assertEqual(decision["executed"], "STATIC")
        self.assertTrue(decision["documented"])
        self.assertIn("fixed within a shot", decision["reason"])
        static = plan_shot(DIRECTIVES_17[1], scene=SCENE)
        self.assertEqual(
            static["movement_decision"]["requested"], "STATIC")

    def test_ots_azimuth_from_counterpart(self):
        scene = {"character_positions": {"Adolf Hitler": (0.0, 0.0, 0.0)},
                 "counterpart_x": 1.5}
        entry = plan_shot(
            {"shot_id": "OTS", "shot_type": "over_the_shoulder",
             "subject": "Adolf Hitler"}, scene=scene)
        self.assertNotEqual(entry["pose"]["azimuth_deg"], 0.0)
        self.assertGreater(entry["pose"]["azimuth_deg"], 0.0)

    def test_srs_alternates_sides(self):
        a = plan_shot({"shot_id": "A", "shot_type": "shot_reverse_shot",
                       "srs_side": 0})
        b = plan_shot({"shot_id": "B", "shot_type": "shot_reverse_shot",
                       "srs_side": 1})
        self.assertLess(a["pose"]["azimuth_deg"], 0.0)
        self.assertGreater(b["pose"]["azimuth_deg"], 0.0)

    def test_unknown_shot_type_recorded_not_dropped(self):
        entry = plan_shot({"shot_id": "BAD", "shot_type": "helicopter"})
        self.assertEqual(entry["shot_type_resolved"], "medium")
        self.assertTrue(entry["errors"])
        self.assertEqual(entry["shot_id"], "BAD")

    def test_frame_range_left_for_atlas(self):
        entry = plan_shot(DIRECTIVES_17[0])
        self.assertIsNone(entry["frame_range"])
        self.assertIn("ATLAS", entry["frame_range_note"])

    def test_location_override_noted(self):
        entry = plan_shot(DIRECTIVES_17[11], scene=SCENE)
        self.assertEqual(entry["location_override"], "LOC_EUROPE_MAP")
        self.assertTrue(any("LOC_EUROPE_MAP" in n
                            for n in entry["continuity_notes"]))

    def test_graphic_insert_flat_note(self):
        entry = plan_shot({"shot_id": "G", "shot_type": "graphic_insert"})
        self.assertTrue(any("flat graphic insert" in n
                            for n in entry["continuity_notes"]))

    def test_repeated_framing_detected(self):
        first = plan_shot(DIRECTIVES_17[6], scene=SCENE)
        second = plan_shot(DIRECTIVES_17[6], scene=SCENE,
                           prev_entry=first)
        self.assertTrue(any("same viewpoint" in n
                            for n in second["continuity_notes"]))


class TestPlanCoverage(unittest.TestCase):
    def test_17_directives_17_entries(self):
        result = plan_coverage(DIRECTIVES_17, scene=SCENE)
        self.assertEqual(len(result["entries"]), 17)
        self.assertEqual(result["accounting"]["total_directives"], 17)
        self.assertTrue(result["accounting"]["all_mapped"])
        self.assertEqual(
            [e["shot_id"] for e in result["entries"]],
            [d["shot_id"] for d in DIRECTIVES_17])

    def test_movement_overrides_listed(self):
        result = plan_coverage(DIRECTIVES_17, scene=SCENE)
        overrides = result["accounting"]["movement_overrides"]
        self.assertIn("SC01_SH01", overrides)   # TRACKING
        self.assertIn("SC02_SH01", overrides)   # DOLLY_IN
        self.assertIn("SC03_SH01", overrides)   # DOLLY_IN
        self.assertIn("SC06_SH01", overrides)   # PAN_RIGHT
        self.assertEqual(len(overrides), 4)

    def test_every_entry_has_pose_and_framing(self):
        result = plan_coverage(DIRECTIVES_17, scene=SCENE)
        for entry in result["entries"]:
            self.assertIn("camera_position", entry)
            self.assertIn("framing", entry)
            self.assertIn("movement_decision", entry)
            self.assertEqual(entry["errors"], [])


class TestMeasurement(unittest.TestCase):
    def _frame(self, sky, ground):
        img = Image.new("RGB", (320, 180), ground)
        img.paste(Image.new("RGB", (320, 60), sky), (0, 0))
        return img

    def test_sky_band_mad_identical_is_zero(self):
        a = self._frame((120, 160, 200), (100, 90, 80))
        b = self._frame((120, 160, 200), (100, 90, 80))
        self.assertEqual(sky_band_mad(a, b, band_h=60), 0.0)
        self.assertEqual(frame_mad(a, b), 0.0)

    def test_sky_band_mad_detects_camera_move(self):
        a = self._frame((120, 160, 200), (100, 90, 80))
        b = self._frame((30, 40, 60), (100, 90, 80))
        self.assertGreater(sky_band_mad(a, b, band_h=60), 50.0)
        # Lower frame unchanged: region MAD stays 0.
        self.assertEqual(frame_mad(a, b, region=(0, 60, 320, 180)), 0.0)

    def test_frame_mad_size_mismatch_raises(self):
        with self.assertRaises(ValueError):
            frame_mad(Image.new("RGB", (10, 10)),
                      Image.new("RGB", (20, 20)))

    def test_head_width_stable(self):
        result = head_width_stability([(100, 322), (101, 323),
                                       (99, 321), (100, 322)])
        self.assertTrue(result["ok"])
        self.assertLess(result["max_deviation_ratio"], 0.05)
        self.assertEqual(result["n"], 4)

    def test_head_width_pump_detected(self):
        result = head_width_stability([(100, 322), (100, 460)])
        self.assertFalse(result["ok"])
        self.assertGreater(result["max_deviation_ratio"], 0.2)

    def test_head_width_empty(self):
        result = head_width_stability([])
        self.assertFalse(result["ok"])
        self.assertEqual(result["n"], 0)


if __name__ == "__main__":
    unittest.main()
