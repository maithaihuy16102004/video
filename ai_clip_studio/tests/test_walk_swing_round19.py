"""Round 19 animation gap 3: wider gestures.

The free-walk arm swing (GAIT_DEFAULT arm_amp) is 0.45 rad
again: the v6 cut to 0.25 read the reference as "arms do not
swing", but that governs task walks (the arm_mode system);
a free walk swings. Measured on the rendered Loop 01 shot #7
(tracking walk): hand travel vs the shoulder 0.11H -> 0.20H.
"""
import tempfile
import unittest
from unittest import mock

import ai_clip_studio.product_renderer as pr
from ai_clip_studio.product_renderer import _render_shot
from ai_clip_studio.tests.test_nod_quantize_round16 import (
    _delivered_shots,
)


class TestWalkSwing(unittest.TestCase):
    def test_hand_travel_wide_on_rendered_walk(self):
        package, shots = _delivered_shots()
        orig = pr.draw_character_v4
        recs = []

        def spy(draw, char, **kw):
            joints = orig(draw, char, **kw)
            recs.append((joints["shoulder"], joints["hand_l"],
                         joints["hand_r"], char.H))
            return joints

        with mock.patch.object(pr, "draw_character_v4", spy):
            with tempfile.TemporaryDirectory() as tmp:
                _render_shot({"shot": shots[7], "package": package,
                              "out_dir": tmp, "still_only": False})
        # Three characters per frame, stable draw order.
        travels = []
        for i in range(3):
            rows = recs[i::3]
            hl = [r[1][0] - r[0][0] for r in rows]
            hr = [r[2][0] - r[0][0] for r in rows]
            travels.append((max(hl) - min(hl)) / rows[0][3])
            travels.append((max(hr) - min(hr)) / rows[0][3])
        # The walker swings wide; the bystanders stay still.
        self.assertGreater(max(travels), 0.15)
        self.assertLess(sorted(travels)[1], 0.05)


if __name__ == "__main__":
    unittest.main()
