"""Round 16 (L02-D8): POSE_HELD body poses persist across timeline-shot
segments of one directive shot (and across shots of the same scene)
until superseded.

Root cause: ``_shot_action_events`` clips compiled events to the
rendered segment, so a SIT_DOWN whose span ends before a later segment
never reaches that segment's ``_per_actor`` -- the character falls back
to standing idle. Delivered Loop 02 evidence: An sits in timeline shot
12 (head drops ~150 px) but stands in shot 13 (same directive shot
SC04_SH01, flat f1100). The fix carries the last POSE_HELD body pose
forward as the base pose (a 1 ms completion-pose hold window, the same
shape as the existing seated-at-desk prefix), for characters with and
without events in the shot.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import (
    _held_poses_at_start, _render_shot)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parents[2]
JOB = AGENT / "jobs" / "req_80be4e5ca4dd"

ID_TO_NAME = {"CHAR_AN": "An", "CHAR_BA_TU": "Ba Tu",
              "CHAR_BE_TI": "Be Ti", "CHAR_CHU_SAU": "Chu Sau"}


def _ev(action_id, shot_id, actor_id, prim, start, end,
        state="POSE_HELD", span_source=None):
    e = {"action_id": action_id, "shot_id": shot_id,
         "actor_id": actor_id, "start_time": start, "end_time": end,
         "required_pose": {"primitive": prim, "params": {}},
         "completion_state": {"state": state}}
    if span_source is not None:
        e["span_source"] = span_source
    return e


class TestHeldPosesAtStart(unittest.TestCase):
    def test_sit_persists_into_later_segment(self):
        ev = _ev("SC04_SH01_ACT01", "SC04_SH01", "CHAR_AN",
                 "sit_down", 41.43, 42.23)
        held = _held_poses_at_start([ev], 4, 44.76, ID_TO_NAME)
        self.assertEqual(held, {"An": ev})

    def test_stand_up_clears(self):
        sit = _ev("A1", "SC04_SH01", "CHAR_AN", "sit_down", 1.0, 2.0)
        stand = _ev("A2", "SC04_SH02", "CHAR_AN", "stand_up", 3.0, 4.0)
        held = _held_poses_at_start([sit, stand], 4, 5.0, ID_TO_NAME)
        self.assertEqual(held, {})

    def test_walk_clears(self):
        sit = _ev("A1", "SC04_SH01", "CHAR_AN", "sit_down", 1.0, 2.0)
        walk = _ev("A2", "SC04_SH02", "CHAR_AN", "walk_to", 3.0, 4.0,
                   state="POSITION_REACHED")
        held = _held_poses_at_start([sit, walk], 4, 5.0, ID_TO_NAME)
        self.assertEqual(held, {})

    def test_sit_at_desk_clears_floor_sit(self):
        sit = _ev("A1", "SC04_SH01", "CHAR_AN", "sit_down", 1.0, 2.0)
        desk = _ev("A2", "SC04_SH02", "CHAR_AN", "sit_at_desk",
                   3.0, 4.0)
        held = _held_poses_at_start([sit, desk], 4, 5.0, ID_TO_NAME)
        self.assertEqual(held, {})

    def test_other_scene_ignored(self):
        sit = _ev("A1", "SC02_SH02", "CHAR_AN", "sit_down", 1.0, 2.0)
        held = _held_poses_at_start([sit], 4, 5.0, ID_TO_NAME)
        self.assertEqual(held, {})

    def test_untrusted_times_ignored(self):
        sit = _ev("A1", "SC04_SH01", "CHAR_AN", "sit_down", 1.0, 2.0,
                  span_source="estimated")
        held = _held_poses_at_start([sit], 4, 5.0, ID_TO_NAME)
        self.assertEqual(held, {})

    def test_event_ending_after_t0_ignored(self):
        sit = _ev("A1", "SC04_SH01", "CHAR_AN", "sit_down",
                  41.43, 42.23)
        held = _held_poses_at_start([sit], 4, 41.43, ID_TO_NAME)
        self.assertEqual(held, {})

    def test_shield_and_crouch_do_not_persist(self):
        # Deliberate exclusions: crouch returns to standing, shield is
        # a reactive within-event hold. See _HELD_POSE_PRIMITIVES.
        shield = _ev("A1", "SC04_SH01", "CHAR_AN", "shield", 1.0, 2.0)
        crouch = _ev("A2", "SC04_SH01", "CHAR_AN", "crouch", 3.0, 4.0)
        held = _held_poses_at_start([shield, crouch], 4, 5.0,
                                    ID_TO_NAME)
        self.assertEqual(held, {})

    def test_non_pose_held_sit_down_ignored(self):
        sit = _ev("A1", "SC04_SH01", "CHAR_AN", "sit_down", 1.0, 2.0,
                  state="POSITION_REACHED")
        held = _held_poses_at_start([sit], 4, 5.0, ID_TO_NAME)
        self.assertEqual(held, {})

    def test_later_sit_replaces_earlier(self):
        first = _ev("A1", "SC04_SH01", "CHAR_AN", "sit_down",
                    1.0, 2.0)
        second = _ev("A2", "SC04_SH02", "CHAR_AN", "sit_down",
                     3.0, 4.0)
        held = _held_poses_at_start([first, second], 4, 5.0,
                                    ID_TO_NAME)
        self.assertEqual(held, {"An": second})

    def test_gesture_does_not_clear_sit(self):
        sit = _ev("A1", "SC04_SH01", "CHAR_AN", "sit_down", 1.0, 2.0)
        wave = _ev("A2", "SC04_SH02", "CHAR_AN", "wave", 3.0, 4.0)
        held = _held_poses_at_start([sit, wave], 4, 5.0, ID_TO_NAME)
        self.assertEqual(held, {"An": sit})

    def test_per_character_tracking(self):
        sit_an = _ev("A1", "SC04_SH01", "CHAR_AN", "sit_down",
                     1.0, 2.0)
        sit_ba = _ev("A2", "SC04_SH01", "CHAR_BA_TU", "sit_down",
                     1.5, 2.5)
        stand_ba = _ev("A3", "SC04_SH02", "CHAR_BA_TU", "stand_up",
                       3.0, 4.0)
        held = _held_poses_at_start([sit_an, sit_ba, stand_ba], 4,
                                    5.0, ID_TO_NAME)
        self.assertEqual(held, {"An": sit_an})

    def test_missing_scene_carries_nothing(self):
        sit = _ev("A1", "SC04_SH01", "CHAR_AN", "sit_down", 1.0, 2.0)
        self.assertEqual(
            _held_poses_at_start([sit], None, 5.0, ID_TO_NAME), {})
        self.assertEqual(
            _held_poses_at_start([sit], "4", 5.0, ID_TO_NAME),
            {"An": sit})


def _delivered_shots():
    text = (AGENT / "examples" / "loop_test_02_brass_key.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    timeline = json.loads((JOB / "timeline.json").read_text(
        encoding="utf-8"))
    shots = timeline["shots"]
    starts = {}
    _t = 0.0
    for s in shots:
        starts[id(s)] = _t
        _t += float(s["duration"])
    spans = {}
    for s in shots:
        sid = s.get("directive_shot_id")
        if sid:
            st = starts[id(s)]
            en = st + float(s["duration"])
            if sid in spans:
                spans[sid][1] = max(spans[sid][1], en)
            else:
                spans[sid] = [st, en]
    events, unsupported = compile_actions(package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    out = []
    for i, s in enumerate(shots):
        shot = dict(s)
        shot["index"] = i
        shot["start_sec"] = starts[id(s)]
        out.append(shot)
    return package, out


def _knee_bend_ratio(joints):
    """hip-foot distance / (hip-knee + knee-foot), averaged legs.

    A straight leg scores 1.0; a seated knee (1.5 rad bend) scores
    well under 0.9. Scale- and camera-invariant: all three points
    come from the same frame's joint snapshot.
    """
    ratios = []
    for side in ("l", "r"):
        hip = joints["hip"]
        knee = joints[f"knee_{side}"]
        foot = joints[f"foot_{side}"]
        d_hf = math.hypot(foot[0] - hip[0], foot[1] - hip[1])
        d_hk = math.hypot(knee[0] - hip[0], knee[1] - hip[1])
        d_kf = math.hypot(foot[0] - knee[0], foot[1] - knee[1])
        if d_hk + d_kf > 0:
            ratios.append(d_hf / (d_hk + d_kf))
    return sum(ratios) / len(ratios)


class TestSitPersistsOnRenderedShots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.shots = _delivered_shots()
        cls.an_name = next(
            str(c.get("name")) for c in cls.package["characters"]
            if str(c.get("id")) == "CHAR_AN")

    def _render_still(self, idx):
        shot = dict(self.shots[idx])
        with tempfile.TemporaryDirectory() as tmp:
            return _render_shot({"shot": shot, "package": self.package,
                                 "out_dir": tmp, "still_only": True})

    def test_shot12_sit_animates_in_shot(self):
        # The establishing shot itself: the sit event plays here, so
        # no carry-forward prefix (held_at_start empty), and the
        # mid-shot still shows the seated knee.
        rep = self._render_still(12)
        self.assertNotIn(self.an_name, rep["held_at_start"])
        joints = rep["joints_last_frame"][self.an_name]
        self.assertLess(_knee_bend_ratio(joints), 0.9)

    def test_shot13_holds_sit(self):
        # Same directive shot, later segment: the sit span ended
        # before this segment, so the carry-forward must hold it.
        rep = self._render_still(13)
        self.assertEqual(rep["held_at_start"].get(self.an_name),
                         "SC04_SH01_ACT01")
        joints = rep["joints_last_frame"][self.an_name]
        self.assertLess(_knee_bend_ratio(joints), 0.9)

    def test_shot14_same_scene_still_seated(self):
        # Later directive shot, same scene: the sit still holds.
        rep = self._render_still(14)
        self.assertEqual(rep["held_at_start"].get(self.an_name),
                         "SC04_SH01_ACT01")

    def test_shot11_before_sit_not_held(self):
        rep = self._render_still(11)
        self.assertNotIn(self.an_name, rep["held_at_start"])

    def test_shot15_next_scene_not_held(self):
        rep = self._render_still(15)
        self.assertNotIn(self.an_name, rep["held_at_start"])


if __name__ == "__main__":
    unittest.main()
