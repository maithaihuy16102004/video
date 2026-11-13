"""W3 camera accounting tests: directive -> shot join, frame ranges,
planned-vs-executed poses. Run from ~/workspace/agent/:
  python3 -m unittest ai_clip_studio.tests.test_camera_accounting -v
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.camera_planner import build_camera_accounting
from ai_clip_studio.product_renderer import camera_accounting, plan_shots


def _ep1_package():
    from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
    from ai_clip_studio.studio_script_v1_adapter import adapt_document
    root = Path(__file__).resolve().parents[2]
    text = (root / "examples"
            / "hitler_ep01_munich_1914.studio.md").read_text(
                encoding="utf-8")
    return adapt_document(parse_studio_script_v1(text))


def _ep1_shots(package):
    shots = plan_shots(
        package,
        [{"line_index": i + 1, "duration": 3.0} for i in range(9)])
    for i, s in enumerate(shots):
        s["index"] = i
    return shots


class TestBuildCameraAccounting(unittest.TestCase):
    def test_synthetic_join_and_frame_ranges(self):
        directives = [
            {"shot_id": "SC01_SH01", "shot_type": "establishing",
             "camera_angle": "eye_level", "camera_movement": "STATIC",
             "scene": 1, "line_index": 1},
            {"shot_id": "SC01_SH02", "shot_type": "close_up",
             "camera_angle": "eye_level", "camera_movement": "STATIC",
             "scene": 1, "line_index": None},
        ]
        shots = [
            {"index": 0, "scene": 1, "kind": "narration",
             "shot_type": "establishing", "duration": 2.0,
             "directive_shot_id": "SC01_SH01"},
            {"index": 1, "scene": 1, "kind": "action",
             "shot_type": "medium", "duration": 1.0},
        ]
        out = build_camera_accounting(directives, shots, fps=24)
        self.assertEqual(len(out["entries"]), 2)
        by_id = {e["shot_id"]: e for e in out["entries"]}
        self.assertEqual(by_id["SC01_SH01"]["status"], "rendered")
        self.assertEqual(by_id["SC01_SH01"]["frame_range"], [0, 48])
        self.assertEqual(by_id["SC01_SH01"]["shot_indices"], [0])
        self.assertEqual(by_id["SC01_SH02"]["status"], "not_rendered")
        self.assertEqual(by_id["SC01_SH02"]["frame_ranges"], [])
        self.assertEqual(by_id["SC01_SH02"]["shot_indices"], [])
        self.assertEqual(len(out["synthesized_shots"]), 1)
        self.assertEqual(out["synthesized_shots"][0]["frame_range"],
                         [48, 72])
        acc = out["accounting"]
        self.assertEqual(acc["total_directives"], 2)
        self.assertEqual(acc["rendered"], 1)
        self.assertEqual(acc["not_rendered"], ["SC01_SH02"])
        self.assertEqual(acc["total_frames_excluding_tail"], 72)
        json.dumps(out)  # must be JSON-serializable

    def test_type_defaulted_when_shot_renders_another_type(self):
        directives = [{"shot_id": "SC01_SH01", "shot_type": "close_up",
                       "camera_angle": "eye_level",
                       "camera_movement": "STATIC"}]
        shots = [{"index": 0, "scene": 1, "kind": "narration",
                  "shot_type": "medium", "duration": 1.0,
                  "directive_shot_id": "SC01_SH01"}]
        out = build_camera_accounting(directives, shots, fps=24)
        self.assertEqual(out["entries"][0]["status"], "type_defaulted")
        self.assertEqual(out["accounting"]["type_defaulted"], 1)

    def test_executed_pose_delta(self):
        directives = [{"shot_id": "SC01_SH01", "shot_type": "medium",
                       "camera_angle": "eye_level",
                       "camera_movement": "STATIC"}]
        shots = [{"index": 0, "scene": 1, "kind": "narration",
                  "shot_type": "medium", "duration": 1.0,
                  "directive_shot_id": "SC01_SH01"}]
        planned = build_camera_accounting(directives, shots, fps=24)
        planned_pos = planned["entries"][0]["camera_position"]
        executed = {0: {"camera_position": planned_pos,
                        "camera_target": [0.0, 1.2, 0.0],
                        "camera_angle": "eye_level",
                        "camera_angle_requested": None,
                        "camera_movement_executed": "STATIC",
                        "camera_radius_scale": 1.0,
                        "camera_limitation": None}}
        out = build_camera_accounting(directives, shots, fps=24,
                                      executed=executed)
        block = out["entries"][0]["executed"][0]
        self.assertEqual(block["position_delta_vs_plan"], 0.0)
        self.assertEqual(block["camera_movement_executed"], "STATIC")

    def test_no_directives_no_crash(self):
        out = build_camera_accounting([], [{"duration": 1.0}], fps=24)
        self.assertEqual(out["entries"], [])
        self.assertEqual(len(out["synthesized_shots"]), 1)


class TestEp1CameraAccounting(unittest.TestCase):
    def test_all_17_directives_accounted(self):
        package = _ep1_package()
        shots = _ep1_shots(package)
        out = camera_accounting(package, shots)
        self.assertEqual(len(out["entries"]), 17)
        statuses = [e["status"] for e in out["entries"]]
        self.assertEqual(len(statuses), 17)
        self.assertTrue(all(s in ("rendered", "type_defaulted",
                                  "not_rendered") for s in statuses))
        acc = out["accounting"]
        self.assertEqual(acc["total_directives"], 17)
        self.assertEqual(
            acc["rendered"] + acc["type_defaulted"]
            + len(acc["not_rendered"]), 17)
        # The 4 documented movement overrides (fixed-by-cut rule).
        self.assertEqual(sorted(acc["movement_overrides"]),
                         ["SC01_SH01", "SC02_SH01", "SC03_SH01",
                          "SC06_SH01"])
        # Frame ranges tile the shot list exactly (cumulative clock).
        covered = []
        for e in out["entries"]:
            covered.extend(e["frame_ranges"])
        for s in out["synthesized_shots"]:
            covered.append(s["frame_range"])
        covered.sort()
        total = round(sum(float(s["duration"]) for s in shots) * 24)
        self.assertEqual(covered[0][0], 0)
        self.assertEqual(covered[-1][1], total)
        for prev, cur in zip(covered, covered[1:]):
            self.assertEqual(prev[1], cur[0],
                             "frame ranges must tile without gaps")
        self.assertEqual(acc["total_frames_excluding_tail"], total)
        # Not-rendered directives carry no frames and no shots.
        for e in out["entries"]:
            if e["status"] == "not_rendered":
                self.assertEqual(e["frame_ranges"], [])
                self.assertEqual(e["shot_indices"], [])
        json.dumps(out)

    def test_subject_staging_uses_character_slots(self):
        package = _ep1_package()
        shots = _ep1_shots(package)
        out = camera_accounting(package, shots)
        by_id = {e["shot_id"]: e for e in out["entries"]}
        # SC04_SH03 subjects Adolf Hitler (slot 0, x=-1.6).
        ots = by_id["SC04_SH03"]
        self.assertAlmostEqual(ots["target"][0], -1.6, places=2)
        # A subject-less directive centres on the subject plane.
        est = by_id["SC01_SH01"]
        self.assertAlmostEqual(est["target"][0], 0.0, places=2)


if __name__ == "__main__":
    unittest.main()
