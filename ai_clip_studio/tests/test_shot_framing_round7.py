"""Round-7 shot-type framing: the script's MEDIUM_CLOSEUP direction
reaches the plan as medium_close_up (not close_up), head framings cap
the anchor tier at head_hands so a ground-level verb cannot widen a
close-up into a wide two-shot, the camera pulls back when a moved
subject's head would overflow the frame top, and a compiled shot
never stages legacy cue locomotion for an actor whose events fall in
a later split shot.

Frame evidence: probe renders of Loop-01 shots #0 (SC01_SH02) and #5
(SC02_SH02) under acceptance_loop/round7_probe_shot{0,5}/.
"""
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import _render_shot, plan_shots
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _loop01_package_and_shots():
    text = (EXAMPLES / "loop_test_01_fire_stone.studio.md").read_text(
        encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(7)])
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


def _render(package, shot):
    tmp = tempfile.TemporaryDirectory()
    result = _render_shot({
        "shot": shot, "package": package,
        "out_dir": Path(tmp.name), "still_only": False})
    tmp.cleanup()
    return result


class TestCameraMappingReachesPlan(unittest.TestCase):
    def test_medium_closeup_is_medium_close_up(self):
        _package, shots = _loop01_package_and_shots()
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC01_SH02")
        self.assertEqual(shot["shot_type"], "medium_close_up")


class TestAnchorTierCap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package, shots = _loop01_package_and_shots()
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC01_SH02")
        cls.result = _render(package, shot)

    def test_ground_action_does_not_widen_closeup(self):
        # SC01_SH02 stages a bend_pick; the head framing caps the
        # tier at head_hands instead of widening to the full body.
        self.assertTrue(self.result["anchor_tier_capped"])
        self.assertEqual(self.result["anchor_tier"], "head_hands")


class TestHeadroomAndNoLegacyDrift(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package, shots = _loop01_package_and_shots()
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC02_SH02")
        cls.result = _render(package, shot)

    def test_camera_pulled_back_for_anvil_depth_head(self):
        # Linh stages at anvil depth under a head-framing camera;
        # without the pullback her head is cut at the frame top.
        self.assertGreater(self.result["camera_radius_scale"], 1.0)

    def test_bystander_does_not_drift_on_discarded_cue(self):
        # The shot's "walk" cue belongs to a later split shot; the
        # watcher must stand still here, not drift 320 px toward the
        # striker on the legacy cue path.
        telemetry = self.result["grip_telemetry"]
        heads = [entry["hands"]["Ông Ba"]["head"] for entry in telemetry]
        first_x = heads[0][0]
        for head in heads:
            self.assertLess(abs(head[0] - first_x), 50.0)

    def test_no_head_intrusions(self):
        self.assertEqual(self.result["head_intrusion_count"], 0)


class TestShieldStagingRound7(unittest.TestCase):
    # Round-7: a SHIELD event's target stages behind the shielder
    # along the shot camera's view axis, peeking toward frame
    # centre -- visible and protected, not at the frame edge and
    # not fully occluded. Frame evidence: probe render of Loop-01
    # shot #10 (SC03_SH01) under
    # acceptance_loop/round7_probe_shot10/.
    @classmethod
    def setUpClass(cls):
        package, shots = _loop01_package_and_shots()
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC03_SH01")
        cls.result = _render(package, shot)

    def test_protected_character_staged_behind_shielder(self):
        staging = self.result.get("shield_staging") or {}
        self.assertIn("Bé Nam", staging)

    def test_protected_head_in_frame_beside_shielder(self):
        tel = self.result.get("grip_telemetry") or []
        self.assertTrue(tel)
        last = tel[-1]["hands"]
        child = last["Bé Nam"]["head"]
        guard = last["Ông Ba"]["head"]
        self.assertGreater(child[0], 0.0)
        self.assertLess(child[0], 1920.0)
        self.assertGreater(child[1], 0.0)
        self.assertLess(child[1], 1080.0)
        # Peeking from behind the shoulder: within one head width
        # horizontally of the shielder, not across the frame.
        self.assertLess(abs(child[0] - guard[0]), 400.0)

    def test_no_head_intrusions_on_guard_beat(self):
        self.assertEqual(self.result["head_intrusion_count"], 0)


class TestInsertRestRound7(unittest.TestCase):
    # Round-7 insert discipline: the EMIT resting sentence
    # ("Viên đá nằm trên đe, phát sáng") names the anvil as the
    # stone's home rest, and the resting sentence overrides the
    # incoming HOLD seed -- the stone rests WORLD_STATIC on the
    # anvil for the whole insert instead of staying in Linh's
    # hand against her leg (R6). Frame evidence: probe render
    # of Loop-01 shot #6 (SC02_SH03) under
    # acceptance_loop/round7_probe_shot6/.
    @classmethod
    def setUpClass(cls):
        package, shots = _loop01_package_and_shots()
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC02_SH03")
        cls.result = _render(package, shot)

    def test_stone_rests_on_the_anvil(self):
        self.assertEqual(
            self.result["prop_support_rests"].get("viên_đá_lửa"),
            "anvil_top")

    def test_stone_never_held_during_the_insert(self):
        for entry in self.result["grip_telemetry"]:
            for draw in entry["draws"]:
                if draw.get("kind") == "stone":
                    self.assertEqual(draw.get("state"),
                                     "WORLD_STATIC")

    def test_insert_crop_centres_on_the_anvil(self):
        # The anvil projects right-of-centre (~x1300); the held
        # stone sat at the hand (~x940). The crop must follow
        # the resting stone, not the hand.
        anchor = self.result["insert_anchor"]
        self.assertGreater(anchor["x"], 1100.0)


if __name__ == "__main__":
    unittest.main()
