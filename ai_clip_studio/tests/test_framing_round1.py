"""RicksClips loop round 1 -- framing: no characters/props on a
full-frame map (D2), subtitles lifted clear of the attribution band
(D4), and action-aware anchor tiers so hand/ground actions stay in
the crop (D1)."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.camera_planner import anchor_focus_for_shot
from ai_clip_studio.product_renderer import (
    _MAP_SUBTITLE_LIFT_PX,
    _anchor_tier_for_shot,
    _render_map_background,
    _render_shot,
    _shot_action_events,
    plan_shots,
)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.subtitles import draw_phrase

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _ep1_package_and_shots():
    text = (EXAMPLES / "hitler_ep01_munich_1914.studio.md").read_text(
        encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(9)])
    for i, s in enumerate(shots):
        s["index"] = i
    spans = {}
    clock = 0.0
    for s in shots:
        did = s.get("directive_shot_id")
        if did:
            span = spans.setdefault(str(did), [clock, clock])
            span[1] = clock + float(s["duration"])
        clock += float(s["duration"])
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None,
    }
    return package, shots


def _event(action_type):
    return {"action_type": action_type}


class TestAnchorTier(unittest.TestCase):
    def test_hand_verbs(self):
        for verb in ("TAKE_OUT", "OPEN_WALLET", "HAND_OVER",
                     "RECEIVE_PROP", "PUT_AWAY", "HAMMER_STRIKE",
                     "POINT", "WRITE"):
            self.assertEqual(
                _anchor_tier_for_shot([_event(verb)], {}),
                "head_hands", verb)

    def test_ground_verbs(self):
        for verb in ("BEND_PICK", "KNEEL_PICK", "PICK_FROM_GROUND",
                     "CROUCH", "DROP"):
            self.assertEqual(
                _anchor_tier_for_shot([_event(verb)], {}), "full", verb)

    def test_ground_wins_over_hand(self):
        self.assertEqual(
            _anchor_tier_for_shot(
                [_event("TAKE_OUT"), _event("KNEEL_PICK")], {}), "full")

    def test_face_verbs_stay_head(self):
        for verb in ("LOOK_AT", "HEAD_TILT", "WALK", "IDLE", "REACT"):
            self.assertEqual(
                _anchor_tier_for_shot([_event(verb)], {}), "head", verb)

    def test_cues_are_fallback_only(self):
        shot = {"action_cues": ["put_away"]}
        self.assertEqual(_anchor_tier_for_shot([], shot), "head_hands")
        shot = {"action_cues": ["bend_pick"]}
        self.assertEqual(_anchor_tier_for_shot([], shot), "full")
        # A compiled span decides even when a stale cue disagrees.
        shot = {"action_cues": ["put_away"]}
        self.assertEqual(
            _anchor_tier_for_shot([_event("LOOK_AT")], shot), "head")
        self.assertEqual(_anchor_tier_for_shot([], {}), "head")


class TestAnchorLadder(unittest.TestCase):
    def _box(self, head_y, foot_y, half_w=162.0, cx=960.0):
        return {"cx": cx, "head_y": head_y, "foot_y": foot_y,
                "half_w": half_w}

    def test_head_box_keeps_close_up_scale(self):
        shot = {"shot_type": "close_up", "camera": {"scale": 2.6}}
        # H=774 standing geometry: head box 324 x 370 fits 2.6x.
        safe, _, _, _ = anchor_focus_for_shot(
            shot, [self._box(126.0, 495.6)], [], 1920, 1080)
        self.assertEqual(float(safe["camera"]["scale"]), 2.6)

    def test_head_hands_box_steps_down(self):
        shot = {"shot_type": "close_up", "camera": {"scale": 2.6}}
        # Head -> waist + raised-hand headroom: 324 x 545 exceeds
        # the 2.6x crop height (415) and steps down to 1.6x.
        safe, _, _, _ = anchor_focus_for_shot(
            shot, [self._box(7.2, 551.7)], [], 1920, 1080)
        self.assertEqual(float(safe["camera"]["scale"]), 1.6)


class TestSubtitleLift(unittest.TestCase):
    def test_lift_moves_the_block_up_exactly(self):
        def ink_top(lift):
            img = Image.new("RGB", (1920, 1080), (0, 0, 0))
            draw_phrase(ImageDraw.Draw(img, "RGBA"),
                        "Cuối năm 1914,", lift_px=lift)
            arr = np.asarray(img).sum(axis=2)
            ys, _ = np.nonzero(arr > 100)
            return int(ys.min())
        self.assertEqual(ink_top(80.0), ink_top(0.0) - 80)

    def test_lift_constant_clears_the_attribution_band(self):
        # Attribution text starts at H-104; the subtitle block ends
        # at H-40-lift. The lift must clear the band with margin.
        self.assertGreaterEqual(_MAP_SUBTITLE_LIFT_PX, 80.0)


class TestMapShotRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.shots = _ep1_package_and_shots()

    def _map_shot(self):
        for shot in self.shots:
            traits = shot.get("v1_location") or {}
            if traits.get("type") == "Historical animated map":
                return dict(shot)
        self.fail("no map shot in the fixture plan")

    def test_map_shot_suppresses_characters(self):
        shot = self._map_shot()
        hitler = next(c["name"] for c in self.package["characters"]
                      if "Hitler" in c["name"])
        shot["visible"] = [hitler]  # the D2 condition (shots #21-24)
        shot["text"] = ""
        with tempfile.TemporaryDirectory() as tmp:
            report = _render_shot({"shot": shot,
                                   "package": self.package,
                                   "out_dir": tmp, "still_only": True})
            still = Image.open(
                Path(tmp) / f"shot_{shot['index']:03d}" / "still.png")
            expected, _ = _render_map_background(shot, self.package)
            self.assertEqual(still.size, expected.size)
            self.assertEqual(still.convert("RGB").tobytes(),
                             expected.convert("RGB").tobytes(),
                             "map still differs from the pure map: "
                             "something staged on it")
        self.assertTrue(report["characters_suppressed_for_map"])

    def test_map_shot_subtitle_lift_reported(self):
        shot = self._map_shot()
        shot["text"] = "Cuối năm 1914, châu Âu chìm trong khói lửa."
        with tempfile.TemporaryDirectory() as tmp:
            report = _render_shot({"shot": shot,
                                   "package": self.package,
                                   "out_dir": tmp, "still_only": True})
        self.assertEqual(report["subtitle_lift_px"],
                         _MAP_SUBTITLE_LIFT_PX)


class TestAnchorTierRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.shots = _ep1_package_and_shots()

    def _shot_with_tier(self, tier):
        for shot in self.shots:
            _, events, _, _, _, _ = _shot_action_events(
                self.package, shot, float(shot["duration"]))
            if _anchor_tier_for_shot(events, shot) == tier:
                found = dict(shot)
                found["shot_type"] = "close_up"
                return found
        self.fail(f"no {tier} shot in the fixture plan")

    def test_wallet_close_up_uses_head_hands(self):
        shot = self._shot_with_tier("head_hands")
        with tempfile.TemporaryDirectory() as tmp:
            report = _render_shot({"shot": shot,
                                   "package": self.package,
                                   "out_dir": tmp, "still_only": True})
        self.assertEqual(report["anchor_tier"], "head_hands")
        self.assertLessEqual(report["applied_scale"], 1.6)

    def test_face_close_up_stays_head(self):
        shot = self._shot_with_tier("head")
        with tempfile.TemporaryDirectory() as tmp:
            report = _render_shot({"shot": shot,
                                   "package": self.package,
                                   "out_dir": tmp, "still_only": True})
        self.assertEqual(report["anchor_tier"], "head")


if __name__ == "__main__":
    unittest.main()
