"""Round-8 true lift (R2-A3 lift half): the stone popped from the
anvil to face height and sank to the waist -- no bend, no rising
lift. Three general fixes:

1. Pick staging: an actor picking a prop off a support the shot's
   own events name stages BESIDE that support (same pattern as the
   striker staging), anchored against the fit/clearance passes,
   facing the support. No named support or no matching element ->
   no staging change.
2. pick_up stoop: a low "ground"-source target bends the torso
   and drops the root in proportion to its depth below the
   shoulder, eased in with the reach and released with the lift.
3. Delayed APPROACHING glide: the prop holds still for the first
   half of the reach (the hands travel to it), then glides to
   meet the hands -- no more floating up on its own.
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.animation.primitives import pick_up
from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.product_renderer import _render_shot, plan_shots
from ai_clip_studio.prop_system import PropStateMachine
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
JOB = Path(__file__).resolve().parents[2] / "jobs/req_ca4d2c6d1959"


def _loop01_probe_plan():
    """The probe plan (R6 job timeline), same as round7_shot5_probe."""
    text = (EXAMPLES / "loop_test_01_fire_stone.studio.md").read_text(
        encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    timeline = json.loads((JOB / "timeline.json").read_text())["lines"]
    shots = plan_shots(package, timeline)
    for i, s in enumerate(shots):
        s["index"] = i
    spans = {}
    t = 0.0
    for s in shots:
        d = float(s["duration"])
        sid = s.get("directive_shot_id")
        if sid:
            if sid in spans:
                spans[sid][1] = t + d
            else:
                spans[sid] = [t, t + d]
        t += d
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None,
    }
    return package, shots


class TestPickUpStoop(unittest.TestCase):
    def _run(self, source, target_y):
        char = Stickman(height=600.0, template="default")
        char.pose["root_x"] = 500.0
        # Standing root_y: hips ride leg*0.93 above the ground
        # (setting root_y = ground_y crouches the hips to the
        # floor and puts the shoulder 239 px too low).
        standing_root = 1000.0 - (char.u_leg + char.l_leg) * 0.93
        char.pose["root_y"] = standing_root
        char.pose["facing"] = 1
        fn = pick_up(char, (620.0, target_y), duration=1.0,
                     ground_y=1000.0, hand="r", source=source)
        samples = {}
        for u in (0.0, 0.5, 1.0):
            fn(u)
            samples[u] = (char.pose["torso_lean"],
                          char.pose["root_y"])
        return samples, standing_root

    def test_low_ground_target_stoops_and_recovers(self):
        # Shoulder sits ~0.63H above the ground (y ~622 at
        # H=600); a target at y=886 is 0.44H below the shoulder
        # (knee height, like the anvil top): full stoop at grasp.
        samples, standing = self._run("ground", 886.0)
        self.assertGreater(samples[0.5][0], 0.4)
        self.assertGreater(samples[0.5][1], standing + 10.0)
        self.assertLess(samples[1.0][0], 0.1)
        self.assertAlmostEqual(samples[1.0][1], standing, places=6)

    def test_pocket_pickup_does_not_bend(self):
        samples, standing = self._run("pocket", 886.0)
        self.assertLess(samples[0.5][0], 0.06)
        self.assertAlmostEqual(samples[0.5][1], standing, places=6)


class TestDelayedApproachGlide(unittest.TestCase):
    def _machine(self):
        props = [{"id": "prop_pen", "kind": "pen",
                  "owner": "CHAR_A"}]
        staging = {"prop_pen": (100.0, 900.0, 0.0)}
        events = [{
            "action_id": "A1", "actor_id": "CHAR_A",
            "action_type": "PICK_UP", "target_id": None,
            "prop_id": "prop_pen", "start_time": 1.0,
            "end_time": 2.0,
            "required_pose": {"pose": "x",
                              "params": {"hand": "r"}},
            "contact_points": [],
        }]
        return PropStateMachine(props, events, staging=staging,
                                ground_y=1000.0)

    def _joints(self):
        return {"CHAR_A": {"hip": (400.0, 600.0),
                           "hand_r": (450.0, 700.0),
                           "hand_l": (380.0, 700.0),
                           "facing": 1}}

    def test_prop_holds_still_first_half_then_meets_hand(self):
        sm = self._machine()
        joints = self._joints()
        # APPROACHING spans 1.0 -> grasp 1.45. At 25% the prop is
        # still exactly at rest; at the grasp instant it is
        # exactly at the hand (no jump into GRASPED).
        x, y, _, state, _ = sm.transform_at("prop_pen", 1.11, joints)
        self.assertEqual(state, "APPROACHING")
        self.assertAlmostEqual(x, 100.0, places=6)
        self.assertAlmostEqual(y, 900.0, places=6)
        x, y, _, state, _ = sm.transform_at("prop_pen", 1.45, joints)
        self.assertEqual(state, "GRASPED")
        self.assertAlmostEqual(x, 450.0, places=6)
        self.assertAlmostEqual(y, 700.0, places=6)
        # Midway through the glide the prop is between rest and hand.
        x, y, _, _, _ = sm.transform_at("prop_pen", 1.34, joints)
        self.assertGreater(x, 100.0)
        self.assertLess(x, 450.0)


class TestLiftShotStagingAndArc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package, shots = _loop01_probe_plan()
        cls.shot = next(s for s in shots
                        if s.get("directive_shot_id") == "SC02_SH01"
                        and s["shot_type"] == "establishing")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = _render_shot({
            "shot": cls.shot, "package": package,
            "out_dir": cls.tmp.name, "still_only": False})
        tel = cls.result["grip_telemetry"]
        cls.stone_track = []
        for e in tel:
            for d in e["draws"]:
                if d["kind"] == "stone":
                    cls.stone_track.append(
                        (e["frame"], d["state"], d["x"], d["y"],
                         e["hands"]["Linh"]))
                    break

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _take_run(self):
        """Frames from the first APPROACHING to the end of the
        continuous grasp/hold run (before the later place-back)."""
        run = []
        started = False
        for row in self.stone_track:
            if row[1] == "APPROACHING":
                started = True
            if started and row[1] in (
                    "APPROACHING", "GRASPED", "ATTACHED_TO_HAND"):
                run.append(row)
            elif started:
                break
        return run

    def test_picker_staged_beside_the_anvil(self):
        staging = self.result.get("pick_staging", {})
        self.assertIn("Linh", staging)
        sx, sz, _side = staging["Linh"]
        self.assertAlmostEqual(sz, -3.2, places=6)
        # Anvil world x is 0.6; the picker stands 0.9 to its side.
        self.assertAlmostEqual(abs(sx - 0.6), 0.9, places=6)

    def test_stone_starts_on_the_anvil(self):
        run = self._take_run()
        self.assertTrue(run)
        self.assertEqual(run[0][1], "APPROACHING")
        rests = self.result.get("prop_support_rests", {})
        self.assertEqual(self.result["prop_rest_kinds"]
                         .get("viên_đá_lửa"), "support")

    def test_stone_rises_monotonically_no_pop(self):
        # The lift span is the 1.0 s TAKE event = 24 frames from
        # the first APPROACHING frame; after it the stone is held
        # (idle sway) and then lowered again by the later
        # place-back beat, which is a different action.
        run = self._take_run()[:24]
        self.assertEqual(len(run), 24)
        ys = [row[3] for row in run]
        for a, b in zip(ys, ys[1:]):
            self.assertLessEqual(b, a + 2.0)
        self.assertGreater(ys[0] - ys[-1], 50.0)
        for (f0, _, x0, y0, _), (f1, _, x1, y1, _) in zip(run, run[1:]):
            self.assertLessEqual(math.hypot(x1 - x0, y1 - y0), 45.0,
                                 msg=f"pop between f{f0} and f{f1}")

    def test_grasp_below_the_face_both_hands_flanking(self):
        run = self._take_run()
        grasp = next(row for row in run if row[1] == "GRASPED")
        _, _, gx, gy, hands = grasp
        head_y = hands["head"][1]
        self.assertGreater(gy - head_y, 100.0)
        hl, hr = hands["hand_l"], hands["hand_r"]
        self.assertAlmostEqual(abs(hl[0] - gx), 44.0, delta=15.0)
        self.assertAlmostEqual(abs(hr[0] - gx), 44.0, delta=15.0)
        self.assertAlmostEqual(abs(hr[0] - hl[0]), 88.0, delta=15.0)

    def test_stone_holds_still_while_hands_travel(self):
        run = self._take_run()
        approach = [row for row in run if row[1] == "APPROACHING"]
        self.assertGreaterEqual(len(approach), 6)
        head = approach[:3]
        self.assertAlmostEqual(head[0][3], head[2][3], delta=1.0)


if __name__ == "__main__":
    unittest.main()
