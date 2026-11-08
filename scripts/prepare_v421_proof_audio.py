"""Mix Proof Audio Tracks with Real Sound Effects & Foley."""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "v421_audio"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SR = 48000


def make_rain(duration: float, intensity: float = 0.5) -> np.ndarray:
    n = int(duration * SR)
    rng = np.random.default_rng(42)
    white = rng.normal(0, 0.15 * intensity, n)
    b0 = b1 = b2 = 0.0
    rain = np.zeros(n, dtype=np.float32)
    for i in range(n):
        b0 = 0.99765 * b0 + white[i] * 0.0990460
        b1 = 0.96300 * b1 + white[i] * 0.2965164
        b2 = 0.57000 * b2 + white[i] * 1.0526913
        rain[i] = (b0 + b1 + b2 + white[i] * 0.1848) * 0.35
    return np.clip(rain, -1.0, 1.0)


def make_wood_snap() -> np.ndarray:
    n = int(0.6 * SR)
    t = np.linspace(0, 0.6, n, endpoint=False)
    rng = np.random.default_rng(123)
    noise = rng.normal(0, 0.8, n) * np.exp(-t * 28.0)
    res = np.sin(2 * np.pi * 320 * t) * np.exp(-t * 18.0) + np.sin(2 * np.pi * 840 * t) * np.exp(-t * 35.0)
    snap = noise * 0.75 + res * 0.4
    return np.clip(snap, -1.0, 1.0)


def make_canal_torrent(duration: float) -> np.ndarray:
    n = int(duration * SR)
    rng = np.random.default_rng(789)
    brown = np.cumsum(rng.normal(0, 0.02, n))
    brown = brown - np.mean(brown)
    brown = brown / (np.max(np.abs(brown)) + 1e-6) * 0.35
    t = np.linspace(0, duration, n, endpoint=False)
    mod = 0.8 + 0.2 * np.sin(2 * np.pi * 0.8 * t)
    return (brown * mod).astype(np.float32)


def make_shamisen(duration: float) -> np.ndarray:
    n = int(duration * SR)
    out = np.zeros(n, dtype=np.float32)
    plucks = [0.5, 3.2, 5.8, 8.4]
    notes = [293.66, 392.00, 440.00, 587.33] # D4, G4, A4, D5 (Yo scale)
    for p_time, freq in zip(plucks, notes):
        idx = int(p_time * SR)
        plen = min(int(2.2 * SR), n - idx)
        if plen <= 0:
            continue
        t = np.linspace(0, plen / SR, plen, endpoint=False)
        decay = np.exp(-t * 4.5)
        tone = (np.sin(2 * np.pi * freq * t) * 0.7 + np.sin(2 * np.pi * freq * 2 * t) * 0.25) * decay
        out[idx : idx + plen] += tone * 0.28
    return out


def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        data = wf.readframes(wf.getnframes())
        ch = wf.getnchannels()
        arr = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32767.0
        if ch == 2:
            return (arr[0::2] + arr[1::2]) * 0.5
        return arr


def mix_and_save(voice: np.ndarray, sfx: np.ndarray, out_path: Path, duration: float):
    n = int(duration * SR)
    mix = np.zeros((n, 2), dtype=np.float32)

    v_len = min(len(voice), n)
    ducking = np.ones(n, dtype=np.float32)
    window = int(0.15 * SR)
    abs_v = np.pad(np.abs(voice[:v_len]), (0, max(0, n - v_len)))
    for i in range(0, n, window):
        chunk_max = np.max(abs_v[i : min(n, i + window)])
        if chunk_max > 0.08:
            ducking[i : min(n, i + window)] = 0.45

    sfx_padded = np.pad(sfx[:n], (0, max(0, n - len(sfx))))
    sfx_ducked = sfx_padded * ducking

    mix[:v_len, 0] += voice[:v_len] * 0.90
    mix[:v_len, 1] += voice[:v_len] * 0.90

    mix[:, 0] += sfx_ducked * 0.60
    mix[:, 1] += sfx_ducked * 0.60

    max_peak = np.max(np.abs(mix))
    if max_peak > 0.95:
        mix = mix * (0.95 / max_peak)

    int16_stereo = (mix * 32767).astype(np.int16)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(int16_stereo.tobytes())
    print(f"Created mix: {out_path} ({duration}s, size: {out_path.stat().st_size / 1024:.1f} KB)")


def main():
    # Proof A: Haru on Bridge (12.0s)
    voice_a = load_wav(OUT_DIR / "voice_proof_a.wav")
    rain_a = make_rain(12.0, 0.7)
    torrent_a = make_canal_torrent(12.0)
    snap = make_wood_snap()
    sfx_a = rain_a + torrent_a
    snap_idx = int(3.2 * SR)
    sfx_a[snap_idx : snap_idx + len(snap)] += snap * 1.5
    mix_and_save(voice_a, sfx_a, OUT_DIR / "proof_a_mixed.wav", 12.0)

    # Proof B: Haru & Aiko at Lantern House (10.0s)
    voice_b = load_wav(OUT_DIR / "voice_proof_b.wav")
    rain_b = make_rain(10.0, 0.35)
    shamisen_b = make_shamisen(10.0)
    sfx_b = rain_b + shamisen_b
    mix_and_save(voice_b, sfx_b, OUT_DIR / "proof_b_mixed.wav", 10.0)

    # Proof C: Modern Lab (10.0s)
    # Take an authoritative slice of voice (e.g. from part 1: Haru/Narrator discussing the core mission)
    voice_c = load_wav(ROOT / "output" / "edo_courier_audio" / "voice-part-001" / "voice.wav")[: int(10.0 * SR)]
    t = np.linspace(0, 10.0, int(10.0 * SR), endpoint=False)
    hum = np.sin(2 * np.pi * 60 * t) * 0.08 + np.sin(2 * np.pi * 120 * t) * 0.04
    servo = np.zeros(int(10.0 * SR), dtype=np.float32)
    for step_t in [1.5, 3.5, 5.5, 7.5]:
        s_idx = int(step_t * SR)
        dur = int(0.4 * SR)
        st = np.linspace(0, 0.4, dur, endpoint=False)
        servo[s_idx : s_idx + dur] = np.sin(2 * np.pi * 420 * st) * np.exp(-st * 8) * 0.15
    sfx_c = (hum + servo).astype(np.float32)
    mix_and_save(voice_c, sfx_c, OUT_DIR / "proof_c_mixed.wav", 10.0)

    print("All audio tracks prepared and mixed successfully!")


if __name__ == "__main__":
    main()
