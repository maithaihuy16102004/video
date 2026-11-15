"""Round 15 (R15-5): the idle pose holds on the gaze fixation grid.

The isolation probe proved the gaze signal steps in perfect
6-frame holds and the drawn arc steps with it at a fixed head;
the delivered drift was continuous head motion (idle sines)
carrying the arcs across sub-pixel boundaries. With a gaze
seed, idle() evaluates its sines at the fixation-quantized
time, so the head holds pixel-flat during fixations.
"""
import unittest

from ai_clip_studio.animation.primitives import idle
from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.expression_library import (
    fixation_time,
    gaze_wander,
)

FPS = 24


class TestFixationTimeRound15(unittest.TestCase):
    def test_holds_and_saccades_share_gaze_grid(self):
        for seed in range(7):
            ts = [k / FPS for k in range(96)]
            ft = [fixation_time(t, seed) for t in ts]
            gz = [gaze_wander(t, seed) for t in ts]
            ft_changes = {k for k in range(1, 96)
                          if ft[k] != ft[k - 1]}
            gz_changes = {k for k in range(1, 96)
                          if gz[k] != gz[k - 1]}
            # The quantized time moves only when the gaze moves.
            self.assertTrue(ft_changes <= gz_changes,
                            f"seed {seed}: {sorted(ft_changes)}")
            # Holds last ~a dwell (6 frames). Each boundary
            # costs <= 2 change-frames: the 0.04 s ease spans
            # ~1 frame, so the value steps into the ease and
            # out to the next hold (gaze does the same).
            self.assertGreater(len(ft_changes), 8)
            self.assertLess(len(ft_changes), 34)

    def test_fixation_time_is_monotone(self):
        for seed in range(7):
            ts = [k / FPS for k in range(96)]
            ft = [fixation_time(t, seed) for t in ts]
            for a, b in zip(ft, ft[1:]):
                self.assertLessEqual(a, b)


class TestIdleFixationRound15(unittest.TestCase):
    def test_quantized_idle_holds_flat(self):
        char = Stickman(height=800.0, template="default")
        fn = idle(char, 99.0, 900.0, gaze_seed=7)
        roots = []
        for k in range(48):
            fn(k / FPS)
            roots.append(char.pose["root_x"])
        # 6-frame holds: values repeat exactly within a dwell.
        runs, run = [], 1
        for a, b in zip(roots, roots[1:]):
            if a == b:
                run += 1
            else:
                runs.append(run)
                run = 1
        runs.append(run)
        self.assertTrue(all(r >= 5 for r in runs[:-1]), runs)
        self.assertGreater(len(set(roots)), 4)

    def test_continuous_idle_still_varies(self):
        char = Stickman(height=800.0, template="default")
        fn = idle(char, 99.0, 900.0)
        roots = []
        for k in range(48):
            fn(k / FPS)
            roots.append(char.pose["root_x"])
        changes = sum(1 for a, b in zip(roots, roots[1:]) if a != b)
        self.assertGreater(changes, 40)


if __name__ == "__main__":
    unittest.main()
