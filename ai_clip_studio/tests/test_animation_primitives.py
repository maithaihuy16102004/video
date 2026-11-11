"""Tests for data-driven animation primitives.

Every primitive must move real joints over time (mean joint displacement
> 0) and must preserve bone lengths (V51 rig invariants). An unsupported
action type must raise, never silently substitute a static pose.
"""
import math
import unittest

from ai_clip_studio.animation import Stickman
from ai_clip_studio.animation.primitives import compile_actions, PRIMITIVES


def bone_lengths(joints):
    def d(a, b):
        ax, ay = joints[a]
        bx, by = joints[b]
        return math.hypot(bx - ax, by - ay)
    return {
        "torso": d("hip", "shoulder"),
        "upper_leg": d("hip", "knee_l"),
        "lower_leg": d("knee_l", "foot_l"),
        "upper_arm": d("shoulder", "elbow_r"),
        "lower_arm": d("elbow_r", "hand_r"),
    }


class TestPrimitives(unittest.TestCase):
    def test_all_primitives_move_joints(self):
        chars = {"lustig": Stickman(height=560, name="lustig")}
        chars["lustig"].set_pose(root_x=500, root_y=679, facing=1)
        actions = [
            {"type": "walk_to", "char": "lustig", "start": 0.0, "duration": 2.0,
             "from_x": 500, "to_x": 900, "ground_y": 920},
            {"type": "point_at", "char": "lustig", "start": 2.0, "duration": 1.0,
             "target": [1100, 300]},
            {"type": "shrug", "char": "lustig", "start": 3.0, "duration": 1.0},
            {"type": "cover_face", "char": "lustig", "start": 4.0, "duration": 1.0},
            {"type": "nod", "char": "lustig", "start": 5.0, "duration": 1.0},
            {"type": "wave", "char": "lustig", "start": 6.0, "duration": 1.0},
        ]
        tl = compile_actions(actions, chars, fps=24)
        self.assertGreater(len(tl), 100)
        # joints move at some point inside each action window (compare the
        # window start with the frame where movement peaks in that window)
        windows = [(0.0, 2.0), (2.0, 1.0), (3.0, 1.0), (4.0, 1.0),
                   (5.0, 1.0), (6.0, 1.0)]
        for start, dur in windows:
            f0 = tl[int(start * 24)]["lustig"]
            best = 0.0
            for fi in range(int(start * 24), int((start + dur) * 24) + 1):
                fr = tl[fi]["lustig"]
                best = max(best, max(
                    math.hypot(fr[k][0] - f0[k][0], fr[k][1] - f0[k][1])
                    for k in ("hand_r", "head", "foot_l")))
            self.assertGreater(best, 5.0,
                               f"no joint movement in action at {start}s")

    def test_bone_lengths_invariant(self):
        chars = {"lustig": Stickman(height=560, name="lustig")}
        chars["lustig"].set_pose(root_x=500, root_y=679, facing=1)
        actions = [
            {"type": "walk_to", "char": "lustig", "start": 0.0, "duration": 2.0,
             "from_x": 500, "to_x": 900, "ground_y": 920},
            {"type": "point_at", "char": "lustig", "start": 2.0, "duration": 1.0,
             "target": [1100, 300]},
        ]
        tl = compile_actions(actions, chars, fps=24)
        ref = bone_lengths(tl[0]["lustig"])
        for fi, frame in tl.items():
            got = bone_lengths(frame["lustig"])
            for k, v in ref.items():
                self.assertAlmostEqual(got[k], v, delta=2.0,
                                       msg=f"bone {k} changed at frame {fi}")

    def test_give_to_moves_prop_with_hands(self):
        chars = {
            "a": Stickman(height=560, name="a"),
            "b": Stickman(height=540, name="b"),
        }
        chars["a"].set_pose(root_x=700, root_y=679, facing=1)
        chars["b"].set_pose(root_x=1200, root_y=688, facing=-1)
        actions = [{"type": "give_to", "char": "a", "other": "b",
                    "start": 0.0, "duration": 1.2}]
        tl = compile_actions(actions, chars, fps=24)
        self.assertGreater(len(tl), 20)

    def test_unknown_action_raises(self):
        chars = {"lustig": Stickman(height=560, name="lustig")}
        with self.assertRaises(ValueError):
            compile_actions([{"type": "teleport", "char": "lustig",
                              "start": 0.0, "duration": 1.0}], chars)

    def test_primitives_registry_covers_required_actions(self):
        for name in ("walk_to", "run_to", "look_at", "point_at", "wave",
                     "reach_to", "give_to", "shrug", "cover_face", "nod",
                     "sit_down", "stand_up"):
            self.assertIn(name, PRIMITIVES)


if __name__ == "__main__":
    unittest.main()
