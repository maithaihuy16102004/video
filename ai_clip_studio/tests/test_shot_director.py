"""Unit tests for the ShotDirector (§4) — direction, not shot inflation.

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/video-16x9-v2/
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.camera_planner import (
    ANGLES, CAMERA_MOVES, EMOTIONS, CameraPlanner, ShotDirector,
)


def _seg(cues, speaker="speaker_a", duration=6.0, scene_number=1):
    return {"action_cues": cues, "speaker": speaker,
            "text": "Some line of dialogue.", "duration": duration,
            "scene_number": scene_number}


_PKG_NIGHT = {"time_of_day": "night", "mood": "cold",
              "weather": "rain",
              "characters": [{"role": "speaker", "world_pos": [-1.0, 0.0, -2.0]},
                             {"role": "receiver", "world_pos": [1.0, 0.0, -2.0]}]}
_PKG_DAY = {"time_of_day": "day", "mood": "warm"}


class TestShotDirector(unittest.TestCase):
    def test_same_shot_count_as_planner_no_inflation(self):
        segs = [_seg(["give", "take"], duration=6.0),
                _seg(["walk"], duration=4.0),
                _seg(["look"], speaker="narrator", duration=3.0)]
        planned = CameraPlanner.plan(segs)
        directed = ShotDirector.direct(segs, _PKG_NIGHT)
        self.assertEqual(len(directed), len(planned))
        self.assertEqual([s["shot_type"] for s in directed],
                         [s["shot_type"] for s in planned])
        self.assertAlmostEqual(
            sum(s["duration"] for s in directed),
            sum(s["duration"] for s in planned), places=2)

    def test_every_shot_has_all_nine_direction_keys(self):
        segs = [_seg(["give", "take"], duration=6.0),
                _seg(["walk", "pick"], duration=6.0),
                _seg(["smile"], duration=3.0)]
        directed = ShotDirector.direct(segs, _PKG_NIGHT)
        self.assertEqual(ShotDirector.validate_direction(directed), [])
        for shot in directed:
            d = shot["direction"]
            for key in ("attention_target", "main_action", "emotion",
                        "angle", "shot_size", "character_positions",
                        "lighting", "camera_move", "cut_point"):
                self.assertIn(key, d)
            self.assertIn(d["angle"], ANGLES)
            self.assertIn(d["emotion"], EMOTIONS)
            self.assertIn(d["camera_move"]["move"], CAMERA_MOVES)
            self.assertIn("from", d["camera_move"])
            self.assertIn("to", d["camera_move"])

    def test_direction_is_data_driven_not_hardcoded(self):
        # Same segments, different scene packages -> different lighting
        # and positions; no story/character names anywhere.
        segs = [_seg(["give", "take"], duration=6.0)]
        night = ShotDirector.direct(segs, _PKG_NIGHT)
        day = ShotDirector.direct(segs, _PKG_DAY)
        self.assertNotEqual(night[0]["direction"]["lighting"],
                            day[0]["direction"]["lighting"])
        self.assertEqual(night[0]["direction"]["lighting"]["key"],
                         "cool_moon")
        self.assertEqual(day[0]["direction"]["lighting"]["key"],
                         "warm_sun")
        self.assertIn("world_anchors",
                      night[0]["direction"]["character_positions"])
        blob = repr(night) + repr(day)
        for forbidden in ("Minh", "Lan", "Lustig", "Eiffel", "wallet",
                          "Ví", "Tháp"):
            self.assertNotIn(forbidden, blob)

    def test_handoff_cut_on_action_peak_object_insert_looks_down(self):
        directed = ShotDirector.direct([_seg(["give", "take"], duration=6.0)],
                                       _PKG_NIGHT)
        insert = [s for s in directed
                  if s["shot_type"] == "object_insert"][0]
        self.assertEqual(insert["direction"]["cut_point"]["at"],
                         "action_peak")
        self.assertEqual(insert["direction"]["angle"], "high_angle")
        self.assertEqual(insert["direction"]["attention_target"]["target"],
                         "object")

    def test_reaction_gets_emotion_and_eye_level(self):
        directed = ShotDirector.direct([_seg(["smile", "relief"],
                                             duration=3.0)], _PKG_DAY)
        self.assertEqual(directed[0]["direction"]["emotion"], "relief")
        self.assertEqual(directed[0]["direction"]["angle"], "eye_level")

    def test_tracking_move_for_walk_and_camera_path_moves(self):
        directed = ShotDirector.direct([_seg(["walk"], duration=4.0)],
                                       _PKG_DAY)
        move = directed[0]["direction"]["camera_move"]
        self.assertEqual(move["move"], "tracking")
        self.assertNotEqual(move["from"]["position"],
                            move["to"]["position"])

    def test_validate_catches_missing_direction(self):
        shots = CameraPlanner.plan([_seg(["walk"], duration=4.0)])
        problems = ShotDirector.validate_direction(shots)
        self.assertTrue(problems)
        self.assertIn("no direction", problems[0])

    def test_direct_without_scene_package_still_valid(self):
        directed = ShotDirector.direct([_seg(["look"], speaker="narrator",
                                             duration=3.0)])
        self.assertEqual(ShotDirector.validate_direction(directed), [])


if __name__ == "__main__":
    unittest.main()
