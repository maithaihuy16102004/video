"""Unit tests for ai_clip_studio.synth_sfx (stdlib unittest, no network).

Run from ~/workspace/video-16x9-v2/:
    python3 -m unittest ai_clip_studio.tests.test_synth_sfx -v

Tests verify synthesis properties (determinism, duration, finiteness,
spectral peak placement, placement, WAV round-trip) — not perceptual
quality. No sample files are read anywhere.
"""

import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_clip_studio import synth_sfx


class TestModal(unittest.TestCase):
    def test_duration_and_shape(self):
        y = synth_sfx.modal(0.5, [(440.0, 1.0, 0.2)])
        self.assertEqual(len(y), int(0.5 * synth_sfx.SR))

    def test_single_mode_is_decaying_sine(self):
        y = synth_sfx.modal(0.4, [(440.0, 1.0, 0.1)])
        self.assertTrue(np.all(np.isfinite(y)))
        # Envelope decays: late RMS much smaller than early RMS.
        early = np.sqrt(np.mean(y[:4800] ** 2))
        late = np.sqrt(np.mean(y[-4800:] ** 2))
        self.assertLess(late, early * 0.1)

    def test_dominant_frequency_matches_mode(self):
        y = synth_sfx.modal(0.5, [(440.0, 1.0, 1.0)])
        spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
        freqs = np.fft.rfftfreq(len(y), 1 / synth_sfx.SR)
        peak = freqs[int(np.argmax(spec))]
        self.assertAlmostEqual(peak, 440.0, delta=15.0)

    def test_modes_above_nyquist_skipped(self):
        y = synth_sfx.modal(0.1, [(30000.0, 1.0, 0.05)])
        self.assertTrue(np.allclose(y, 0.0))

    def test_seeded_phases_deterministic(self):
        a = synth_sfx.modal(0.2, [(440.0, 1.0, 0.1), (660.0, 0.5, 0.1)], seed=7)
        b = synth_sfx.modal(0.2, [(440.0, 1.0, 0.1), (660.0, 0.5, 0.1)], seed=7)
        self.assertTrue(np.array_equal(a, b))

    def test_unseeded_deterministic_phase_zero(self):
        a = synth_sfx.modal(0.2, [(440.0, 1.0, 0.1)])
        b = synth_sfx.modal(0.2, [(440.0, 1.0, 0.1)])
        self.assertTrue(np.array_equal(a, b))


class TestGenerators(unittest.TestCase):
    def test_thump_decays_and_is_low(self):
        y = synth_sfx.thump()
        self.assertEqual(len(y), int(0.22 * synth_sfx.SR))
        self.assertTrue(np.all(np.isfinite(y)))
        spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
        freqs = np.fft.rfftfreq(len(y), 1 / synth_sfx.SR)
        peak = freqs[int(np.argmax(spec))]
        self.assertLess(peak, 300.0)

    def test_clink_deterministic_per_seed(self):
        a = synth_sfx.clink(seed=3, f0=2500.0)
        b = synth_sfx.clink(seed=3, f0=2500.0)
        c = synth_sfx.clink(seed=4, f0=2500.0)
        self.assertTrue(np.array_equal(a, b))
        self.assertFalse(np.array_equal(a, c))
        self.assertEqual(len(a), int(0.12 * synth_sfx.SR))

    def test_clink_peak_near_f0(self):
        y = synth_sfx.clink(seed=3, f0=2500.0)
        spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
        freqs = np.fft.rfftfreq(len(y), 1 / synth_sfx.SR)
        peak = freqs[int(np.argmax(spec[10:])) + 10]
        self.assertAlmostEqual(peak, 2500.0, delta=250.0)

    def test_footstep_shape_and_level(self):
        y = synth_sfx.footstep(seed=11, intensity=1.0)
        self.assertEqual(len(y), int(0.22 * synth_sfx.SR))
        self.assertTrue(np.all(np.isfinite(y)))
        self.assertLessEqual(np.abs(y).max(), 1.0)
        self.assertGreater(np.abs(y).max(), 0.5)

    def test_footstep_deterministic(self):
        a = synth_sfx.footstep(seed=11)
        b = synth_sfx.footstep(seed=11)
        self.assertTrue(np.array_equal(a, b))

    def test_noise_burst_decays(self):
        y = synth_sfx.noise_burst(0.3, seed=5, decay_tau=0.05)
        early = np.sqrt(np.mean(y[:2400] ** 2))
        late = np.sqrt(np.mean(y[-2400:] ** 2))
        self.assertLess(late, early * 0.5)
        self.assertLessEqual(np.abs(y).max(), 1.0)

    def test_one_pole_lowpass_attenuates_highs(self):
        rng = np.random.default_rng(1)
        x = rng.standard_normal(synth_sfx.SR)
        y = synth_sfx.one_pole_lowpass(x, 1000.0)
        self.assertEqual(len(y), len(x))
        spec_x = np.abs(np.fft.rfft(x))
        spec_y = np.abs(np.fft.rfft(y))
        freqs = np.fft.rfftfreq(len(x), 1 / synth_sfx.SR)
        hi = freqs > 8000
        self.assertLess(np.mean(spec_y[hi]), np.mean(spec_x[hi]) * 0.5)


class TestMixPanIO(unittest.TestCase):
    def test_pan_centre_and_edges(self):
        x = np.ones(100)
        c = synth_sfx.pan(x, 0.0)
        self.assertTrue(np.allclose(c[0], c[1]))
        left = synth_sfx.pan(x, -1.0)
        self.assertGreater(left[0].mean(), left[1].mean() * 10)
        right = synth_sfx.pan(x, 1.0)
        self.assertGreater(right[1].mean(), right[0].mean() * 10)

    def test_mix_at_places_and_clips(self):
        buf = np.zeros((2, synth_sfx.SR))
        sig = np.ones(4800)
        synth_sfx.mix_at(buf, sig, 0.5)
        self.assertEqual(buf[0, 24000], 1.0)
        self.assertEqual(buf[0, 23999], 0.0)
        self.assertEqual(buf[0, 28799], 1.0)
        self.assertEqual(buf[0, 28800], 0.0)
        # Placement past the end clips instead of raising.
        synth_sfx.mix_at(buf, sig, 0.999)
        self.assertTrue(np.all(np.isfinite(buf)))

    def test_mix_at_adds(self):
        buf = np.zeros((2, synth_sfx.SR))
        synth_sfx.mix_at(buf, np.ones(100), 0.0)
        synth_sfx.mix_at(buf, np.ones(100), 0.0)
        self.assertEqual(buf[0, 0], 2.0)

    def test_write_wav16_round_trip(self):
        y = synth_sfx.footstep(seed=2)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "step.wav"
            synth_sfx.write_wav16(path, y)
            with wave.open(str(path), "rb") as w:
                self.assertEqual(w.getnchannels(), 2)
                self.assertEqual(w.getsampwidth(), 2)
                self.assertEqual(w.getframerate(), synth_sfx.SR)
                self.assertEqual(w.getnframes(), len(y))

    def test_peak_and_rms_db(self):
        self.assertAlmostEqual(synth_sfx.peak_db(np.array([1.0, -0.5])), 0.0, places=6)
        self.assertEqual(synth_sfx.peak_db(np.zeros(10)), -math.inf)
        self.assertEqual(synth_sfx.rms_db(np.zeros(10)), -math.inf)
        self.assertAlmostEqual(synth_sfx.rms_db(np.ones(100)), 0.0, places=6)

    def test_fade_edges(self):
        y = synth_sfx.fade_edges(np.ones(4800), fade_in=0.01, fade_out=0.01)
        self.assertEqual(y[0], 0.0)
        self.assertEqual(y[-1], 0.0)
        self.assertEqual(y[2400], 1.0)


if __name__ == "__main__":
    unittest.main()
