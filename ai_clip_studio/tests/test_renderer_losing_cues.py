"""Renderer losing-cue discard (A2 wiring item 8): a cue that lost a
semantic conflict must never select a pose, draw a puddle, or stage
a prop on the ground. The renderer honors the pipeline's
discarded_cues record at the single point shot cues enter
_render_shot. The legacy cue fallback itself is preserved for
packages without semantics (its ground rest is pinned by
test_engine_stage3_locations_props): producing the discard record
is the pipeline's job (stage 2b), honoring it is the renderer's.
"""

import copy
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from ai_clip_studio.product_renderer import (
    PROP_FILL, _effective_cues, _render_shot, plan_shots)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


class TestEffectiveCues(unittest.TestCase):
    def test_discarded_cue_removed_for_its_scene_only(self):
        shot = {"scene": 1, "action_cues": ["walk", "bend_pick", "take"]}
        package = {"discarded_cues": [
            {"cue": "bend_pick", "scene": 1, "removed": True}]}
        self.assertEqual(_effective_cues(shot, package),
                         ["walk", "take"])

    def test_other_scene_unremoved_and_missing_records_kept(self):
        shot = {"scene": 1, "action_cues": ["walk", "bend_pick"]}
        package = {"discarded_cues": [
            {"cue": "bend_pick", "scene": 2, "removed": True},
            {"cue": "walk", "scene": 1, "removed": False},
            {"cue": "take", "scene": "nope", "removed": True},
            "not-a-dict"]}
        self.assertEqual(_effective_cues(shot, package),
                         ["walk", "bend_pick"])
        self.assertEqual(_effective_cues(shot, {}),
                         ["walk", "bend_pick"])
        self.assertEqual(
            _effective_cues({"scene": None, "action_cues": ["walk"]},
                            package), ["walk"])


def _ep1_package_no_events():
    """Ep1 package + shots with NO compiled actions, so the legacy
    cue-driven branch renders (the PSM path is skipped)."""
    text = (EXAMPLES / "hitler_ep01_munich_1914.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    package.pop("compiled_actions", None)
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(9)])
    for i, s in enumerate(shots):
        s["index"] = i
    return package, shots


def _wallet_pixels(still_path):
    """Exact PROP_FILL pixels anywhere in the still. The wallet is
    the only object drawn in PROP_FILL; the environment and
    costumes use different values (verified: the filtered renders
    below count exactly 0)."""
    img = np.asarray(Image.open(still_path).convert("RGB")).astype(int)
    match = (img[:, :, 0] == PROP_FILL[0]) \
        & (img[:, :, 1] == PROP_FILL[1]) \
        & (img[:, :, 2] == PROP_FILL[2])
    return int(match.sum())


class TestLegacyBranchGroundRule(unittest.TestCase):
    def _render(self, package, shot):
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot({
                "shot": shot, "package": package,
                "out_dir": str(Path(tmp) / "shot"),
                "still_only": True,
            })
            self.assertFalse(result["prop_machine"])
            return _wallet_pixels(result["still"])

    def test_surviving_bend_pick_stages_prop(self):
        # A surviving ground-pickup cue runs the kneel flow: the
        # wallet is visible (at the hand in the still's second
        # half). The pre-pickup ground visibility (first half) is
        # verified on real video frames by the regression matrix.
        package, shots = _ep1_package_no_events()
        shot = copy.deepcopy(shots[2])  # establishing, ground visible
        shot["action_cues"] = ["bend_pick"]
        count = self._render(package, shot)
        self.assertGreater(count, 0)

    def test_discarded_bend_pick_stages_nothing(self):
        package, shots = _ep1_package_no_events()
        package["discarded_cues"] = [
            {"cue": "bend_pick", "scene": 1, "removed": True,
             "winner_authority": "COMPILED_EVENT",
             "reason": "losing cue discarded"}]
        shot = copy.deepcopy(shots[2])
        shot["action_cues"] = ["bend_pick"]
        count = self._render(package, shot)
        self.assertEqual(count, 0)

    def test_discarded_bend_pick_selects_no_kneel_pose(self):
        # The filter applies before pose selection too: a
        # surviving bend_pick kneels (deep knee bend, dropped
        # hip); a discarded one leaves the character standing.
        # Action shots only: the cue-based kneel lives in the
        # action-shot pose branch.
        def knee_angle(package, shot):
            with tempfile.TemporaryDirectory() as tmp:
                result = _render_shot({
                    "shot": shot, "package": package,
                    "out_dir": str(Path(tmp) / "shot"),
                    "still_only": True,
                })
            joints = result["joints_last_frame"]["Adolf Hitler"]
            hip, knee, foot = (joints["hip"], joints["knee_r"],
                               joints["foot_r"])
            ax, ay = hip[0] - knee[0], hip[1] - knee[1]
            bx, by = foot[0] - knee[0], foot[1] - knee[1]
            dot = ax * bx + ay * by
            mag = math.hypot(ax, ay) * math.hypot(bx, by)
            angle = math.degrees(math.acos(
                max(-1.0, min(1.0, dot / mag)))) if mag else 180.0
            return angle, joints["hip"][1]

        package, shots = _ep1_package_no_events()
        shot = copy.deepcopy(shots[2])
        shot["kind"] = "action"
        shot["action_cues"] = ["bend_pick"]
        angle, hip_y = knee_angle(package, shot)
        self.assertLess(angle, 120.0, f"kneel expected, got {angle:.0f}")
        package["discarded_cues"] = [
            {"cue": "bend_pick", "scene": 1, "removed": True}]
        angle2, hip_y2 = knee_angle(package, copy.deepcopy(shot))
        self.assertGreater(angle2, 140.0,
                           f"standing expected, got {angle2:.0f}")
        self.assertLess(hip_y2, hip_y)


if __name__ == "__main__":
    unittest.main()
