"""Round 11 (R11-5), sharpened round 12 (R12-4): saccade dwell.
The R10 wander was verified alive in 2x strips but subtle at
full-frame distance: continuous drift smears at 24 fps. The
wander fixates (0.25 s holds) and jumps (round 11: 0.08 s eased
saccades; round 12: 0.04 s single-frame snaps -- the 2-frame
ease never survived to pixels against head sway, tester
R11-D1), at amplitude 0.12, so single frames show clearly
shifted gazes and fixations read as distinct looks.
"""

import math
import statistics
import unittest

from ai_clip_studio.expression_library import gaze_wander


class TestGazeDwell(unittest.TestCase):
    def test_holds_within_fixation(self):
        # Seed 0 has zero time offset: step 1 spans [0.25, 0.50),
        # the ease ends at 0.29, so 0.35..0.45 all hold one value.
        vals = {gaze_wander(t, 0) for t in (0.35, 0.40, 0.45, 0.49)}
        self.assertEqual(len(vals), 1)

    def test_fixations_differ(self):
        holds = [gaze_wander(0.40 + 0.25 * k, 12345)
                 for k in range(20)]
        diffs = sum(1 for a, b in zip(holds, holds[1:]) if a != b)
        self.assertGreaterEqual(diffs, 15)

    def test_bounded_by_amplitude(self):
        for t in range(240):
            gx, gy = gaze_wander(t / 24.0, 12345)
            self.assertLessEqual(abs(gx), 0.12)
            self.assertLessEqual(abs(gy), 0.12)

    def test_no_teleport_between_frames(self):
        prev = gaze_wander(0.0, 12345)
        worst = 0.0
        for t in range(1, 240):
            cur = gaze_wander(t / 24.0, 12345)
            worst = max(worst, abs(cur[0] - prev[0]),
                        abs(cur[1] - prev[1]))
            prev = cur
        # Round 12: a saccade IS a one-frame snap (0.04 s ease),
        # so a single frame step may carry a full dwell-to-dwell
        # jump (<= 2 * amplitude = 0.24) -- but never more.
        self.assertLessEqual(worst, 0.25)

    def test_zero_mean_over_long_window(self):
        series = [gaze_wander(t / 24.0, 12345) for t in range(480)]
        self.assertLess(abs(statistics.mean([g[0] for g in series])),
                        0.12 / 3.0)
        self.assertLess(abs(statistics.mean([g[1] for g in series])),
                        0.12 / 3.0)

    def test_seeds_desynchronised(self):
        # Different seeds hold different values at the same clock
        # time (offsets + phases), so characters do not jump eyes
        # in lockstep.
        vals = {gaze_wander(1.0, seed) for seed in range(6)}
        self.assertGreaterEqual(len(vals), 4)

    def test_negative_time_clamps(self):
        self.assertEqual(gaze_wander(-1.0, 0), gaze_wander(0.0, 0))

    def test_explicit_amplitude_respected(self):
        for t in range(120):
            gx, gy = gaze_wander(t / 24.0, 7, amplitude=0.05)
            self.assertLessEqual(abs(gx), 0.05)
            self.assertLessEqual(abs(gy), 0.05)


if __name__ == "__main__":
    unittest.main()
