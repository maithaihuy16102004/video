"""Round 16 (Mai 2026-11-15: walking "bi ngua"): forward-intent
lean/arm/sway values must follow the travel direction / facing.

The rig applies torso_lean and the FK arm/elbow angles as
ABSOLUTE +x offsets, so _locomote's facing-blind values tilted
left-walkers backward (shoulder +21.6 px behind the hip, head
+37.4 px) and swung their arms backwards, and bend_pick /
kneel_pick stooped left-facers up to 77 deg AWAY from the prop.
The fix signs those values by ``direction`` / ``facing``; a
leftward motion must be the EXACT MIRROR of the rightward one.
Rightward motion is byte-identical to the pre-fix behaviour.
"""
import math
import unittest

from ai_clip_studio.animation.primitives import (
    bend_pick, kneel_pick, run_to, standing, walk_mud, walk_to)
from ai_clip_studio.animation.rig import Stickman

H = 780
GROUND = 900
JOINTS = ("shoulder", "neck", "head", "knee_l", "knee_r", "foot_l",
          "foot_r", "elbow_l", "elbow_r", "hand_l", "hand_r")
UPPER = ("shoulder", "neck", "head", "elbow_l", "elbow_r", "hand_l",
         "hand_r")
# Bend/kneel reach keys: the torso + the REACHING arm. The other
# arm keeps the facing-blind standing hang (arm 0.08 / elbow 0.15
# from standing()), a ~9 px quirk present in every standing pose
# for left-facers -- invisible, out of scope for the lean fix.


REACH = ("shoulder", "neck", "head", "elbow_r", "hand_r")


def _walk(direction, t, factory=walk_to, **kw):
    ch = Stickman(height=H)
    standing(ch, 960, GROUND, facing=direction)
    if direction > 0:
        fn = factory(ch, 400, 1200, 2.0, GROUND, **kw)
    else:
        fn = factory(ch, 1200, 400, 2.0, GROUND, **kw)
    fn(t)
    return ch.joints()


def _assert_mirror(test, jl, jr, centre, keys, tol=1.0):
    for key in keys:
        test.assertAlmostEqual(jl[key][0] - centre,
                               -(jr[key][0] - centre), delta=tol,
                               msg=key)
        test.assertAlmostEqual(jl[key][1], jr[key][1], delta=tol,
                               msg=key)


class TestWalkMirror(unittest.TestCase):
    def test_travel_mirrors_exactly(self):
        for t in (0.5, 1.0, 1.5):
            with self.subTest(t=t):
                _assert_mirror(self, _walk(-1, t), _walk(1, t), 800,
                               JOINTS)

    def test_settle_mirrors(self):
        # Torso + legs only: the arms lerp back to the shared
        # standing hang (0.08 / 0.15, facing-blind), so mid-blend
        # they pass through the hang instead of mirroring -- that
        # continuity (no pop at the segment boundary) is
        # deliberate; the lean itself mirrors exactly.
        _assert_mirror(self, _walk(-1, 1.9), _walk(1, 1.9), 800,
                       ("shoulder", "neck", "head", "knee_l",
                        "knee_r", "foot_l", "foot_r"))

    def test_anticipation_upper_body_mirrors(self):
        # Torso + head only: the feet step from the facing-blind
        # standing split into the directional split during
        # anticipation, and the arms lerp from the shared hang --
        # both are boundary-continuity effects, not the lean
        # defect. The lean (shoulder/head) mirrors exactly.
        _assert_mirror(self, _walk(-1, 0.1), _walk(1, 0.1), 800,
                       ("shoulder", "neck", "head"))

    def test_lean_points_forward_in_both_directions(self):
        for direction in (1, -1):
            with self.subTest(direction=direction):
                J = _walk(direction, 1.0)
                lean_dx = J["shoulder"][0] - J["hip"][0]
                self.assertGreater(lean_dx * direction, 15.0)
                head_dx = J["head"][0] - J["hip"][0]
                self.assertGreater(head_dx * direction, 30.0)

    def test_right_walk_unchanged(self):
        # Pre-fix probe values for the rightward walk (the fix
        # must not move the already-correct direction).
        J = _walk(1, 1.0)
        self.assertAlmostEqual(J["shoulder"][0] - J["hip"][0], 21.6,
                               delta=0.5)
        self.assertAlmostEqual(J["head"][0] - J["hip"][0], 37.4,
                               delta=0.5)

    def test_run_mirrors(self):
        for t in (0.6, 1.2):
            with self.subTest(t=t):
                _assert_mirror(self, _walk(-1, t, factory=run_to),
                               _walk(1, t, factory=run_to), 800,
                               JOINTS)

    def test_walk_mud_mirrors(self):
        for t in (0.6, 1.2):
            with self.subTest(t=t):
                _assert_mirror(self, _walk(-1, t, factory=walk_mud),
                               _walk(1, t, factory=walk_mud), 800,
                               JOINTS)


def _bend(facing, t, factory):
    ch = Stickman(height=H)
    standing(ch, 960, GROUND, facing=facing)
    fn = factory(ch, (960 + facing * 200, GROUND), 1.2, GROUND)
    fn(t)
    return ch.joints()


class TestBendMirror(unittest.TestCase):
    def test_bend_pick_mirrors(self):
        # Upper body only: the feet stay in the facing-blind
        # standing split (symmetric by design -- a standing split
        # does not care which foot is ahead), so the knees cannot
        # mirror; the knees bend forward via bend=-f in both
        # facings (the 2026-11-11 fix). The lean defect lives in
        # the torso + reaching arm, which must mirror exactly.
        for t in (0.4, 0.66, 1.0):
            with self.subTest(t=t):
                _assert_mirror(self, _bend(-1, t, bend_pick),
                               _bend(1, t, bend_pick), 960, REACH)

    def test_kneel_pick_mirrors(self):
        for t in (0.4, 0.66, 1.0):
            with self.subTest(t=t):
                _assert_mirror(self, _bend(-1, t, kneel_pick),
                               _bend(1, t, kneel_pick), 960, REACH)

    def test_stoop_heads_toward_the_target(self):
        for factory, name in ((bend_pick, "bend"),
                              (kneel_pick, "kneel")):
            for facing in (1, -1):
                with self.subTest(factory=name, facing=facing):
                    J = _bend(facing, 0.66, factory)
                    self.assertGreater(
                        (J["shoulder"][0] - J["hip"][0]) * facing,
                        100.0)


if __name__ == "__main__":
    unittest.main()
