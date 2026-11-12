# MIT attribution — synthesis mechanisms adapted from:
#   mromidev/claude-animated-shorts (https://github.com/mromidev/claude-animated-shorts.git)
#   Copyright (c) 2026 Mr omi, MIT License (see ../../THIRD_PARTY_NOTICES.md).
# Source files: templates/audio/dsp.py (modal synthesis, noise, envelopes,
# stereo placement, WAV I/O) and templates/audio/sfx_gen.py (boot/thump,
# clink, stick-slip creak engine, whoosh). Adapted here as a SMALL numpy-only
# prototype: no scipy (the originals need scipy for filters/STFT/reverb),
# only the mechanisms that survive without it. The full filter bank, STFT
# spectral shaping, reverb IRs, and BS.1770 loudness kit are Phase 2 work.
# NOT wired into any pipeline, audio plan, or server. Generators here make
# sound ONLY when called explicitly with explicit parameters — nothing in
# this module invents cues, places sounds on a timeline, or adds automatic
# whooshes. See acceptance_loop/EXTERNAL_REPO_AUDIT_CLAUDE_ANIMATED_SHORTS.md.
"""Prototype: pure-synthesis sound effects (no sample files, no network).

Every sound is computed from numbers: decaying sine modes, shaped noise, and
pitch glides, seeded for determinism. This proves the technique the external
repo uses for its whole soundtrack — ``sfx_gen.py`` / ``instruments.py``
generate every effect from numpy, with zero downloaded samples — in the
smallest form that stands alone:

- :func:`modal` — sum of exponentially decaying sines (the core of clinks,
  thocks, rings, and tuned percussion in ``dsp.modal``).
- :func:`thump` — low sine with a fast pitch drop (the boot-heel core of
  ``sfx_gen.boot``).
- :func:`clink` — inharmonic modes + a short noise click (``sfx_gen.clink``).
- :func:`footstep` — thump + plank modes + slap + click (``sfx_gen.boot``).
- :func:`noise_burst` — FFT-shaped noise with an exponential decay (a
  scipy-free stand-in for the filtered-noise layers in ``sfx_gen``).
- :func:`mix_at` / :func:`write_wav16` / :func:`peak_db` — placement and
  output helpers (cf. ``dsp.place`` / ``dsp.write_wav``).

Deliberately NOT included: whooshes (the original's ``whoosh`` needs STFT
spectral shaping via scipy, and automatic camera whooshes are forbidden by
Mai's SFX rules), formant voices (English-vowel content), reverb, and
loudness metering. Those are assessed in the audit report as ADAPT/FLAG
items, not silently shipped here.

Requires numpy only (plus stdlib ``wave`` for output).
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

__all__ = [
    "SR",
    "modal",
    "thump",
    "clink",
    "footstep",
    "noise_burst",
    "one_pole_lowpass",
    "mix_at",
    "pan",
    "write_wav16",
    "peak_db",
    "rms_db",
    "fade_edges",
]

SR = 48000
TAU = 2 * math.pi


def _rng(seed: int | None) -> np.random.Generator:
    return np.random.default_rng(seed if seed is not None else 0)


def _time(dur: float) -> np.ndarray:
    n = max(1, int(round(dur * SR)))
    return np.arange(n) / SR


def _phase(freq_per_sample: np.ndarray) -> np.ndarray:
    """Instantaneous frequency (Hz per sample) -> phase in radians (dsp.phase)."""
    return TAU * np.cumsum(freq_per_sample) / SR


def fade_edges(x: np.ndarray, fade_in: float = 0.003, fade_out: float = 0.01) -> np.ndarray:
    """Cosine fades at both ends (cf. dsp.fades). Returns a new array."""
    y = np.array(x, dtype=float, copy=True)
    n = y.shape[-1]
    a, b = int(round(fade_in * SR)), int(round(fade_out * SR))
    if a > 0:
        k = min(a, n)
        y[..., :k] *= (0.5 - 0.5 * np.cos(np.pi * np.linspace(0, 1, a)))[:k]
    if b > 0:
        k = min(b, n)
        ramp = 0.5 - 0.5 * np.cos(np.pi * np.linspace(0, 1, b))
        y[..., n - k:] *= ramp[::-1][-k:]
    return y


def modal(
    dur: float,
    modes: list[tuple[float, float, float]],
    seed: int | None = None,
    glide: float = 0.0,
    glide_tau: float = 0.02,
) -> np.ndarray:
    """Sum of exponentially decaying sines (port of ``dsp.modal``).

    ``modes`` is ``[(freq_hz, amp, decay_tau_s), ...]``; modes at or above
    Nyquist are skipped, as in the original. ``glide`` is an optional common
    fractional pitch glide that decays with ``glide_tau``. Random per-mode
    phases are used only when ``seed`` is given (otherwise phase 0, exactly
    like the original's ``r=None`` path), so unseeded calls are deterministic.
    """
    t = _time(dur)
    y = np.zeros_like(t)
    rng = _rng(seed) if seed is not None else None
    g = 1 + glide * np.exp(-t / glide_tau) if glide else None
    for freq, amp, tau in modes:
        if freq >= SR * 0.45 or freq <= 0:
            continue
        ph0 = float(rng.uniform(0, TAU)) if rng is not None else 0.0
        if g is None:
            y += amp * np.exp(-t / tau) * np.sin(TAU * freq * t + ph0)
        else:
            y += amp * np.exp(-t / tau) * np.sin(_phase(freq * g) + ph0)
    return y


def one_pole_lowpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """Single-pole low-pass via FFT multiplication (scipy-free helper).

    The original uses ``scipy.signal.butter``; this prototype shapes spectra
    with numpy's FFT instead. The response is a first-order roll-off above
    ``cutoff_hz``. Input is treated as one mono signal.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    resp = 1.0 / np.sqrt(1.0 + (freqs / max(cutoff_hz, 1.0)) ** 2)
    return np.fft.irfft(spec * resp, n)


def noise_burst(
    dur: float,
    seed: int,
    decay_tau: float = 0.05,
    cutoff_hz: float = 6000.0,
    attack: float = 0.002,
) -> np.ndarray:
    """Shaped noise: white noise, low-passed, exponential decay, fast attack.

    This is the scipy-free analogue of the filtered-noise layers used all
    through ``sfx_gen.py`` (slaps, taps, breaths). Deterministic per seed.
    """
    rng = _rng(seed)
    n = max(1, int(round(dur * SR)))
    t = np.arange(n) / SR
    y = one_pole_lowpass(rng.standard_normal(n), cutoff_hz)
    env = (1 - np.exp(-t / max(attack, 1e-4))) * np.exp(-t / decay_tau)
    y = y * env
    peak = np.abs(y).max()
    if peak > 0:
        y = y / peak * 0.9
    return fade_edges(y, 0.0, 0.01)


def thump(dur: float = 0.22, f0: float = 98.0, seed: int | None = None) -> np.ndarray:
    """Low sine with a fast pitch drop (the heel-thump core of ``boot``).

    ``f0`` is the settled pitch; the starting pitch is 18% higher and drops
    with a 12 ms time constant, as in the original.
    """
    rng = _rng(seed) if seed is not None else None
    f = (f0 * (0.8 + 0.4 * rng.uniform()) if rng is not None else f0)
    t = _time(dur)
    freq = f * (1 + 0.18 * np.exp(-t / 0.012))
    tau = 0.036
    return np.exp(-t / tau) * np.sin(_phase(freq))


def clink(seed: int, f0: float | None = None, dur: float = 0.12, bright: float = 1.0) -> np.ndarray:
    """One small metal-on-metal clink (port of ``sfx_gen.clink``).

    Three inharmonic modes plus a sub-millisecond high-frequency click. The
    original high-passes noise with scipy; here the click is raw noise gated
    by a 0.8 ms decay (the ear hears the same transient; the spectrum above
    3 kHz is unshaped in this prototype — a documented simplification).
    """
    rng = _rng(seed)
    f0 = f0 or float(np.exp(rng.uniform(np.log(1800), np.log(5200))))
    modes = [
        (f0, 1.0, float(rng.uniform(0.012, 0.03))),
        (f0 * float(rng.uniform(2.3, 2.9)), 0.5 * bright, 0.01),
        (f0 * float(rng.uniform(3.9, 5.1)), 0.25 * bright, 0.006),
    ]
    y = modal(dur, modes, seed=seed)
    t = _time(dur)
    y = y + rng.standard_normal(len(t)) * np.exp(-t / 0.0008) * 0.4
    return y


def footstep(seed: int, intensity: float = 1.0) -> np.ndarray:
    """One boot heel on a wooden plank (simplified port of ``sfx_gen.boot``).

    Thump + plank modes + band-limited slap + heel click. The original's
    Butterworth band-passes are replaced by the FFT one-pole helper and a
    spectral difference for the click band; the layer structure, timings,
    and relative levels follow the original.
    """
    rng = _rng(seed)
    dur = 0.22
    t = _time(dur)
    f = float(rng.uniform(78, 118))
    th = np.exp(-t / float(rng.uniform(0.028, 0.045))) * np.sin(
        _phase(f * (1 + 0.18 * np.exp(-t / 0.012)))
    )
    plank = modal(
        dur,
        [
            (float(rng.uniform(170, 260)), 0.6, float(rng.uniform(0.018, 0.035))),
            (float(rng.uniform(380, 620)), 0.45, float(rng.uniform(0.012, 0.025))),
            (float(rng.uniform(800, 1300)), 0.25, 0.01),
        ],
        seed=seed,
    )
    nz = rng.standard_normal(len(t))
    slap = one_pole_lowpass(nz, 3500) * np.exp(-t / 0.006) * 0.5
    click = (nz - one_pole_lowpass(nz, 3500)) * np.exp(-t / 0.0012) * 0.22 * intensity
    y = th + plank + slap + click
    peak = np.abs(y).max()
    return y / peak * 0.9 if peak > 0 else y


def pan(x: np.ndarray, p: float = 0.0) -> np.ndarray:
    """Constant-power pan of a mono signal (port of ``dsp.pan``)."""
    th = (float(np.clip(p, -1, 1)) + 1) * math.pi / 4
    mono = np.asarray(x, dtype=float)
    return np.stack([mono * math.cos(th), mono * math.sin(th)]) * math.sqrt(2)


def mix_at(buf: np.ndarray, x: np.ndarray, t: float, gain: float = 1.0) -> None:
    """Add ``x`` (mono or stereo) into stereo buffer ``buf`` at time ``t`` (port of ``dsp.place``)."""
    sig = np.asarray(x, dtype=float)
    if sig.ndim == 1:
        sig = np.stack([sig, sig])
    i = int(round(t * SR))
    a, b = max(0, i), min(buf.shape[1], i + sig.shape[1])
    if b > a:
        buf[:, a:b] += gain * sig[:, a - i: b - i]


def write_wav16(path: str | Path, x: np.ndarray, sr: int = SR) -> Path:
    """Write a mono/stereo float array as 16-bit PCM WAV (stdlib ``wave``).

    Simplified port of ``dsp.write_wav`` (which defaults to 24-bit). Values
    are clipped to [-1, 1]. Returns the path written.
    """
    sig = np.asarray(x, dtype=float)
    if sig.ndim == 1:
        sig = np.stack([sig, sig])
    ch, n = sig.shape
    q = np.clip(np.round(sig.T * 32767.0), -32768, 32767).astype("<i2")
    out = Path(path)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(q.tobytes())
    return out


def peak_db(x: np.ndarray) -> float:
    """Peak level in dBFS."""
    peak = float(np.abs(np.asarray(x, dtype=float)).max(initial=0.0))
    return 20 * math.log10(peak) if peak > 0 else -math.inf


def rms_db(x: np.ndarray) -> float:
    """RMS level in dBFS."""
    arr = np.asarray(x, dtype=float)
    if arr.size == 0:
        return -math.inf
    rms = float(np.sqrt(np.mean(arr**2)))
    return 20 * math.log10(rms) if rms > 0 else -math.inf
