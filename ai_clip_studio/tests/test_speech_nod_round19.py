"""Round 19 animation gap 1: the talk nod is gated by the real
voice segment, so the head nods while speech is happening and
holds still through the post-voice beat. The gate mirrors
speech_mouth_envelope (80 ms ramps, same [0, voice_duration]
span) and runs on raw time -- the quantized gaze clock lags
real time by up to one dwell, which would drag the nod into
the beat. speech_gate=None keeps the exact historical
behaviour.
"""
import math
import tempfile
import unittest
from unittest import mock

from ai_clip_studio.animation.primitives import nod
from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.product_renderer import _render_shot
import ai_clip_studio.animation.primitives as prim
import ai_clip_studio.product_renderer as pr
from ai_clip_studio.tests.test_nod_quantize_round16 import (
    _delivered_shots,
)


class TestSpeechGateUnit(unittest.TestCase):
    def test_gate_values_raw_time(self):
        char = Stickman(height=560)
        fn = nod(char, 4.0, freq=0.5, amp=0.08,
                 speech_gate=(1.0, 3.0))
        seen = {}
        for t in (0.5, 1.0, 1.04, 1.5, 2.96, 3.0, 3.04, 3.5):
            fn(t)
            seen[t] = char.pose["head_look"]
        self.assertEqual(seen[0.5], 0.0)
        self.assertEqual(seen[3.5], 0.0)
        # Attack ramp: half-open at the midpoint of the ramp.
        self.assertAlmostEqual(
            seen[1.04],
            0.5 * 0.08 * math.sin(1.04 * 2 * math.pi * 0.5),
            places=6)
        # Release ramp mirrors the attack.
        self.assertAlmostEqual(
            seen[2.96],
            0.5 * 0.08 * math.sin(2.96 * 2 * math.pi * 0.5),
            places=6)
        # Fully open mid-span.
        self.assertAlmostEqual(
            seen[1.5], 0.08 * math.sin(1.5 * 2 * math.pi * 0.5),
            places=6)

    def test_none_gate_is_historical_sine(self):
        char = Stickman(height=560)
        fn = nod(char, 4.0, freq=1.1, amp=0.10)
        for t in (0.0, 0.3, 1.7, 3.9):
            fn(t)
            self.assertAlmostEqual(
                char.pose["head_look"],
                0.10 * math.sin(t * 2 * math.pi * 1.1), places=9)

    def test_gated_quantized_matches_ungated_during_voice(self):
        seed = 1390970424
        gated = Stickman(height=560)
        plain = Stickman(height=560)
        fn_g = nod(gated, 4.0, freq=0.5, amp=0.08,
                   gaze_seed=seed, speech_gate=(0.0, 3.22))
        fn_p = nod(plain, 4.0, freq=0.5, amp=0.08,
                   gaze_seed=seed)
        # Fully open between the ramps: identical to ungated.
        for i in range(2, 75):
            t = i / 24.0
            fn_g(t)
            fn_p(t)
            self.assertAlmostEqual(
                gated.pose["head_look"], plain.pose["head_look"],
                places=9, msg=f"t={t}")
        # The attack ramp starts at zero.
        fn_g(0.0)
        self.assertEqual(gated.pose["head_look"], 0.0)
        # After the gate end + ramp, the gated head is still.
        for i in range(80, 86):
            fn_g(i / 24.0)
            self.assertEqual(gated.pose["head_look"], 0.0)


class TestSpeechGateRender(unittest.TestCase):
    def test_talk_nod_zero_in_beat_on_real_path(self):
        package, shots = _delivered_shots()
        shot = shots[2]  # narration, voice 3.22 < duration 3.57
        records = []
        orig_nod = prim.nod

        def spy_nod(char, duration, **kw):
            fn = orig_nod(char, duration, **kw)
            gate = kw.get("speech_gate")

            def wrapped(t):
                out = fn(t)
                if gate is not None:
                    records.append((float(t),
                                    char.pose.get("head_look", 0.0)))
                return out

            return wrapped

        with mock.patch.object(prim, "nod", spy_nod), \
                mock.patch.object(pr, "nod", spy_nod):
            with tempfile.TemporaryDirectory() as tmp:
                _render_shot({"shot": shot, "package": package,
                              "out_dir": tmp, "still_only": False})
        vd = float(shot["voice_duration"])
        voice = [v for t, v in records if t <= vd]
        beat = [v for t, v in records if t > vd + 0.08]
        self.assertTrue(voice)
        self.assertGreater(max(abs(v) for v in voice), 0.05)
        self.assertTrue(beat)
        self.assertTrue(all(v == 0.0 for v in beat))


if __name__ == "__main__":
    unittest.main()
