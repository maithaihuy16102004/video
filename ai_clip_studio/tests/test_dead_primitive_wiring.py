"""Dead-primitive wiring: every primitive the compiler can emit must
have a product-renderer branch.

Three mapped primitives had NO ``_event_fn`` branch, so their events
fell back to idle with a loud record and rendered as standing still:
``hammer_strike`` (every forging strike in Zeus SC08), ``crouch``,
and ``shield`` (round-2 system 1 -- its proof rendered the primitive
directly, never through the product path). The totality test below
pins the dispatch table so this class of defect cannot recur
silently: a compiler-mapped primitive without a branch fails the
suite instead of idling a shot.
"""

import math
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import PRIMITIVE_MAP, compile_actions
from ai_clip_studio.animation.primitives import Stickman, standing
from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import build_environment
from ai_clip_studio.product_renderer import (
    _event_fn, _furniture_anchors, _render_shot, plan_shots)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.tests.test_insert_two_pass import (
    _zeus_package_and_shots)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / \
    "unseen_garden_key.studio.md"


def _ctx():
    char = Stickman(height=560, name="Test")
    standing(char, 500.0, 900.0)
    joints0 = {
        "Test": char.joints(),
        "Other": {"head": (800.0, 500.0), "hip": (800.0, 700.0)},
    }
    return char, {
        "char": char, "name": "Test", "other_name": "Other",
        "ground_y": 900.0, "pos": {"x": 500.0}, "direction": 1,
        "facing": 1, "joints0": joints0, "rests": {},
        "id_to_name": {}, "name_to_id": {},
        "paper": {"x": 600.0, "y": 400.0, "w": 100.0, "h": 60.0},
        "desk": {"x": 600.0, "top_y": 450.0},
        "chair_x": 500.0, "seat_y": 600.0, "prop": None,
        "anvil": {"x": 700.0, "top_y": 500.0},
    }


class TestEventFnTotality(unittest.TestCase):
    def test_every_mapped_primitive_dispatches(self):
        # face_only is handled by the expression path and hand_over
        # by the pair-fn caller; every other mapped primitive must
        # produce a callable from _event_fn, never None.
        mapped = {v[0] for v in PRIMITIVE_MAP.values()}
        mapped -= {"face_only", "hand_over"}
        event = {"prop_id": None, "contact_points": [],
                 "target_id": None}
        for prim in sorted(mapped):
            with self.subTest(primitive=prim):
                char, ctx = _ctx()
                fn = _event_fn(prim, {"hand": "r"}, event, ctx, 1.0)
                self.assertTrue(
                    callable(fn), f"{prim} has no _event_fn branch")
                fn(0.5)  # the closure must run, not just construct


class TestHammerStrikeRenders(unittest.TestCase):
    def test_no_fallback_and_hand_swings(self):
        package, shots = _zeus_package_and_shots()
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC08_SH01")
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot(
                {"shot": shot, "package": package, "out_dir": tmp})
        self.assertNotIn(
            "SC08_SH01_ACT02", result["action_dispatch_fallback"])
        # The actor is Zeus (first-person narrator); the strike
        # window is the first ~1.8 s of the 3.35 s shot.
        hands = [f["hands"]["Zeus"]["hand_r"]
                 for f in result["grip_telemetry"][:44]]
        ys = [h[1] for h in hands]
        self.assertGreater(max(ys) - min(ys), 100.0,
                           "hammer hand never swung")


class TestAnvilAnchor(unittest.TestCase):
    def test_forge_anvil_projects_to_top_face(self):
        traits = {"kind": "forge",
                  "features": ["lò rèn", "đe", "bễ thổi"],
                  "forbidden": []}
        pkg = build_environment(traits, time_of_day="day")
        cam = viewpoint_for_shot("medium", "eye_level",
                                 (0.0, 1.2, 0.0))
        anchors = _furniture_anchors(pkg, cam, (1920, 1080),
                                     715, 900, 560, 1)
        self.assertEqual(anchors["source"], "environment")
        ex, ey, _s, vis = cam.project((0.6, 0.86, -3.2), 1920, 1080)
        self.assertTrue(vis)
        self.assertAlmostEqual(anchors["anvil"]["x"], ex, delta=2.0)
        self.assertAlmostEqual(anchors["anvil"]["top_y"], ey,
                               delta=2.0)

    def test_no_environment_falls_back_in_front(self):
        anchors = _furniture_anchors(None, None, (1920, 1080),
                                     500, 900, 560, 1)
        self.assertEqual(anchors["anvil"]["x"], 500 + 0.30 * 560)
        self.assertEqual(anchors["anvil"]["top_y"], 900 - 0.45 * 560)


def _render_fixture_with_sentence(sentence):
    text = FIXTURE.read_text(encoding="utf-8")
    anchor = "* Bà Tư hơi cúi đầu suy nghĩ."
    text = text.replace(anchor, anchor + "\n* " + sentence, 1)
    package = adapt_document(parse_studio_script_v1(text))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(5)])
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
    shot = next(s for s in shots
                if s.get("directive_shot_id") == "SC01_SH01")
    with tempfile.TemporaryDirectory() as tmp:
        result = _render_shot(
            {"shot": shot, "package": package, "out_dir": tmp})
    return package, result


class TestShieldRenders(unittest.TestCase):
    def test_guard_pose_not_idle(self):
        package, result = _render_fixture_with_sentence(
            "Bà Tư giơ hai tay che chắn.")
        shields = [e for e in package["compiled_actions"]["events"]
                   if e["action_type"] == "SHIELD"]
        self.assertEqual(len(shields), 1)
        self.assertNotIn(shields[0]["action_id"],
                         result["action_dispatch_fallback"])
        # Guard: both hands move together to a stacked guard in
        # front of the chest and hold (before the fix the hands
        # hung at the sides, idle). Round-7: the guard interposes
        # the arms at CHEST height -- the lower hand moves FORWARD
        # (~460 px) rather than up, so the discriminator is 2D
        # travel + the stack, not a y-rise for both hands.
        tel = result["grip_telemetry"]
        name = next(k for k in tel[0]["hands"] if "Tư" in k)
        hands = [f["hands"][name] for f in tel]
        first = hands[0]
        # The shield sentence is the shot's second sentence, so its
        # window covers the second half; the guard HOLDS to the end
        # (POSE_HELD), so the last frame is the guard pose.
        last = hands[-1]
        for hand in ("hand_l", "hand_r"):
            moved = math.hypot(last[hand][0] - first[hand][0],
                               last[hand][1] - first[hand][1])
            self.assertGreater(moved, 200.0,
                               f"{hand} never moved to the guard")
        self.assertGreater(abs(last["hand_l"][1] - last["hand_r"][1]),
                           40.0, "guard hands not stacked")
        spread = abs(last["hand_l"][0] - last["hand_r"][0])
        self.assertLess(spread, 120.0, f"guard hands split {spread}")


class TestCrouchRenders(unittest.TestCase):
    def test_hips_drop_not_idle(self):
        package, result = _render_fixture_with_sentence(
            "Bà Tư cúi người tránh tiếng pháo.")
        # The fixture already contains another CROUCH sentence;
        # pin the injected one by shot + directive text.
        crouches = [e for e in package["compiled_actions"]["events"]
                    if e["action_type"] == "CROUCH"
                    and e.get("shot_id") == "SC01_SH01"
                    and "tránh tiếng pháo" in e["directive_text"]]
        self.assertEqual(len(crouches), 1)
        self.assertNotIn(crouches[0]["action_id"],
                         result["action_dispatch_fallback"])
        tel = result["grip_telemetry"]
        name = next(k for k in tel[0]["hands"] if "Tư" in k)
        hips = [f["hands"][name]["hip"][1] for f in tel]
        self.assertGreater(max(hips) - min(hips), 30.0,
                           "hips never dropped into the crouch")


if __name__ == "__main__":
    unittest.main()
