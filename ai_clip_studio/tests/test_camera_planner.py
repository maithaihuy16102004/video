"""Unit tests for ai_clip_studio.camera_planner (stdlib unittest).

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/video-16x9-v2/
"""
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.camera_planner import (
    CameraPlanner, SHOT_TYPES, SHOT_SCALE,
)


def _seg(cues, speaker="speaker_a", duration=6.0, scene_number=1):
    return {"action_cues": cues, "speaker": speaker,
            "text": "Some line of dialogue.", "duration": duration,
            "scene_number": scene_number}


def _gradient_frame(w=1920, h=1080):
    """Frame whose four quadrants differ strongly, so a crop is visible."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 255) // w, (y * 255) // h,
                        ((x + y) * 255) // (w + h))
    return img


class TestCameraPlanner(unittest.TestCase):
    def test_handoff_is_three_shot_chain(self):
        shots = CameraPlanner.plan([_seg(["give", "take"], duration=6.0)])
        self.assertEqual(len(shots), 3)
        self.assertEqual([s["shot_type"] for s in shots],
                         ["establishing", "object_insert", "reaction"])
        self.assertEqual([s["camera"]["scale"] for s in shots],
                         [1.0, 3.4, 2.6])
        self.assertEqual([s["camera"]["focus_target"] for s in shots],
                         ["two_shot_center", "object", "subject_head"])
        # durations split the segment and sum back to it
        self.assertAlmostEqual(sum(s["duration"] for s in shots), 6.0,
                               places=2)

    def test_handoff_not_hardcoded_to_any_story(self):
        # Invented speakers / no story names anywhere in the plan.
        shots = CameraPlanner.plan([
            _seg(["give", "take"], speaker="person_x", duration=6.0),
            _seg(["walk"], speaker="person_y", duration=4.0),
        ])
        blob = repr(shots)
        for forbidden in ("Minh", "Lan", "Lustig", "Eiffel", "wallet",
                          "Ví", "Tháp"):
            self.assertNotIn(forbidden, blob)
        # ...and the planner works the same for any speaker label
        self.assertEqual(shots[0]["shot_type"], "establishing")
        self.assertEqual(shots[3]["shot_type"], "tracking")

    def test_walk_is_tracking(self):
        shots = CameraPlanner.plan([_seg(["walk_fast"], duration=4.0)])
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["shot_type"], "tracking")
        self.assertEqual(shots[0]["camera"]["scale"], 1.6)

    def test_run_is_tracking(self):
        shots = CameraPlanner.plan([_seg(["run"], duration=3.0)])
        self.assertEqual(shots[0]["shot_type"], "tracking")

    def test_bend_pick_is_object_insert(self):
        shots = CameraPlanner.plan([_seg(["bend_pick"], duration=2.0)])
        self.assertEqual(shots[0]["shot_type"], "object_insert")
        self.assertEqual(shots[0]["camera"]["scale"], 3.4)
        self.assertEqual(shots[0]["camera"]["focus_target"], "object")

    def test_open_is_object_insert(self):
        shots = CameraPlanner.plan([_seg(["open"], duration=2.0)])
        self.assertEqual(shots[0]["shot_type"], "object_insert")

    def test_look_search_is_medium_plus_reaction(self):
        shots = CameraPlanner.plan([_seg(["look", "search"], duration=4.0)])
        self.assertEqual([s["shot_type"] for s in shots],
                         ["medium", "reaction"])

    def test_smile_is_close_up_reaction(self):
        shots = CameraPlanner.plan([_seg(["smile"], duration=2.0)])
        self.assertEqual(shots[0]["shot_type"], "reaction")
        self.assertEqual(shots[0]["camera"]["scale"], 2.6)

    def test_board_is_establishing_then_medium(self):
        shots = CameraPlanner.plan([_seg(["board", "bus"], duration=5.0)])
        self.assertEqual([s["shot_type"] for s in shots],
                         ["establishing", "medium"])

    def test_narration_only_is_establishing(self):
        shots = CameraPlanner.plan([_seg([], speaker="narrator",
                                         duration=3.0)])
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["shot_type"], "establishing")

    def test_every_shot_has_full_shape(self):
        shots = CameraPlanner.plan([
            _seg(["give", "take"], duration=6.0),
            _seg(["walk"], duration=4.0),
            _seg(["smile"], duration=2.0),
        ])
        for s in shots:
            self.assertIn(s["shot_type"], SHOT_TYPES)
            self.assertIn("narrative_purpose", s)
            self.assertIn("subject", s)
            self.assertIn("focus_target", s)
            self.assertIn("composition_rules", s)
            self.assertTrue(s["composition_rules"])
            self.assertIn(s["transition"], ("cut", "dissolve"))
            self.assertEqual(s["camera"]["scale"],
                             SHOT_SCALE[s["shot_type"]])
            self.assertIn(s["camera"]["focus_target"],
                          ("subject_head", "object", "subject_full",
                           "two_shot_center"))
            self.assertIn(s["camera"]["center_rule"],
                          ("rule_of_thirds_left", "center",
                           "rule_of_thirds_right"))
            self.assertGreater(s["duration"], 0)

    def test_apply_camera_wide_is_identity(self):
        img = _gradient_frame()
        shot = {"shot_type": "establishing",
                "camera": {"scale": 1.0, "focus_target": "two_shot_center",
                           "center_rule": "center"}}
        out = CameraPlanner.apply_camera(img, shot, (960, 540))
        self.assertEqual(out.size, (1920, 1080))
        diff = np.mean(np.abs(np.asarray(out, dtype=np.float32)
                              - np.asarray(img, dtype=np.float32)))
        self.assertLess(diff, 1.0)

    def test_apply_camera_close_up_differs_clearly_from_wide(self):
        img = _gradient_frame()
        wide = {"shot_type": "establishing",
                "camera": {"scale": 1.0, "focus_target": "two_shot_center",
                           "center_rule": "center"}}
        close = {"shot_type": "close_up",
                 "camera": {"scale": 2.6, "focus_target": "subject_head",
                            "center_rule": "rule_of_thirds_left"}}
        out_wide = CameraPlanner.apply_camera(img, wide, (960, 540))
        out_close = CameraPlanner.apply_camera(img, close, (960, 400))
        self.assertEqual(out_close.size, (1920, 1080))
        diff = np.mean(np.abs(np.asarray(out_close, dtype=np.float32)
                              - np.asarray(out_wide, dtype=np.float32)))
        self.assertGreater(diff, 5.0)

    def test_apply_camera_clamps_focus_at_frame_edge(self):
        img = _gradient_frame()
        shot = {"shot_type": "object_insert",
                "camera": {"scale": 3.4, "focus_target": "object",
                           "center_rule": "center"}}
        for focus in ((0, 0), (1920, 1080), (-100, 5000)):
            out = CameraPlanner.apply_camera(img, shot, focus)
            self.assertEqual(out.size, (1920, 1080))

    def test_shot_diversity_report(self):
        shots = CameraPlanner.plan([
            _seg(["give", "take"], duration=6.0),
            _seg(["walk"], duration=4.0),
        ])
        rep = CameraPlanner.shot_diversity_report(shots)
        self.assertEqual(rep["total_shots"], 4)
        self.assertEqual(rep["num_shot_types"], 4)
        self.assertTrue(rep["has_close_up"])
        self.assertTrue(rep["has_insert"])
        self.assertTrue(rep["has_reaction"])
        rep2 = CameraPlanner.shot_diversity_report(
            CameraPlanner.plan([_seg(["walk"], duration=4.0)]))
        self.assertFalse(rep2["has_close_up"])
        self.assertFalse(rep2["has_insert"])
        self.assertFalse(rep2["has_reaction"])


    def test_multi_cue_composition_walk_and_pick(self):
        shots = CameraPlanner.plan([_seg(["walk_fast", "bend_pick"],
                                         duration=4.2)])
        types = [s["shot_type"] for s in shots]
        self.assertEqual(types, ["tracking", "object_insert"])
        self.assertAlmostEqual(sum(s["duration"] for s in shots), 4.2,
                               places=2)

    def test_multi_cue_composition_run_search_open(self):
        shots = CameraPlanner.plan([_seg(["run", "search", "open"],
                                         duration=4.5)])
        types = [s["shot_type"] for s in shots]
        # tracking in, medium search, insert of the opened object;
        # the reaction comes in the following dialogue segment.
        self.assertEqual(types, ["tracking", "medium", "object_insert"])
        self.assertLessEqual(len(shots), 3)

    def test_bus_alone_is_not_a_boarding_shot(self):
        # "bus" is a location noun: a lead set at a bus stop (walk +
        # pick) must compose walk/pick shots, not a boarding chain.
        shots = CameraPlanner.plan([_seg(["walk_fast", "bend_pick", "look",
                                          "bus"], duration=4.2)])
        types = [s["shot_type"] for s in shots]
        self.assertEqual(types, ["tracking", "medium", "object_insert"])

    def test_line_narrator_with_object_cue_is_insert(self):
        shots = CameraPlanner.plan([{
            "action_cues": ["bend_pick", "look"], "speaker": "narrator",
            "duration": 5.0, "scene_number": 1, "kind": "line"}])
        self.assertEqual([s["shot_type"] for s in shots], ["object_insert"])

    def test_line_speaker_is_medium_not_insert(self):
        shots = CameraPlanner.plan([{
            "action_cues": ["bend_pick", "look"], "speaker": "Minh",
            "duration": 3.0, "scene_number": 1, "kind": "line"}])
        self.assertEqual([s["shot_type"] for s in shots], ["medium"])

    def test_line_narrator_with_emotion_cue_is_reaction(self):
        shots = CameraPlanner.plan([{
            "action_cues": ["smile", "relief"], "speaker": "narrator",
            "duration": 3.0, "scene_number": 3, "kind": "line"}])
        self.assertEqual([s["shot_type"] for s in shots], ["reaction"])

    def test_line_narrator_without_cues_is_establishing(self):
        shots = CameraPlanner.plan([{
            "action_cues": [], "speaker": "narrator",
            "duration": 3.0, "scene_number": 1, "kind": "line"}])
        self.assertEqual([s["shot_type"] for s in shots], ["establishing"])

    def test_line_does_not_repeat_handoff_chain(self):
        shots = CameraPlanner.plan([{
            "action_cues": ["give", "take", "open"], "speaker": "Lan",
            "duration": 3.0, "scene_number": 3, "kind": "line"}])
        self.assertEqual([s["shot_type"] for s in shots], ["medium"])


    def test_line_narrator_boarding_beats_pick(self):
        # Scene 4: the narrator line carries both "open"/"put_away"
        # (pick cues) and "board"/"bus" — the bus arriving is the
        # subject, so the boarding chain wins, not a 10 s object insert.
        shots = CameraPlanner.plan([{
            "action_cues": ["stop", "open", "put_away", "wave",
                            "turn_back", "smile", "board", "bus"],
            "speaker": "narrator", "duration": 9.7, "scene_number": 4,
            "kind": "line"}])
        self.assertEqual([s["shot_type"] for s in shots],
                         ["establishing", "medium"])


if __name__ == "__main__":
    unittest.main()
