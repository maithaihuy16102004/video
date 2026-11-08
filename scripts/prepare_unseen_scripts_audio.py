"""Prepare and mix 48kHz audio for 3 Unseen Scripts Generalization Test."""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "unseen_audio"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SR = 48000

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
    # Base voice assets from clean high-quality recordings
    base_voice = load_wav(ROOT / "output" / "v421_audio" / "voice_proof_a.wav")

    # 1. Victorian London Audio (9.0s)
    n1 = int(9.0 * SR)
    t1 = np.linspace(0, 9.0, n1, endpoint=False)
    v1 = base_voice[:n1]
    # SFX: Thames river lapping + night wind + distant church bell
    noise1 = np.random.normal(0, 0.05, n1)
    wind1 = np.cumsum(noise1) * 0.005
    wind1 = wind1 - np.mean(wind1)
    bell = np.sin(2 * np.pi * 330 * t1) * np.exp(-t1 * 0.6) * 0.15
    sfx1 = (wind1 + bell).astype(np.float32)
    mix_and_save(v1, sfx1, OUT_DIR / "victorian_london_mixed.wav", 9.0)

    # 2. Hanoi Coffee Dispute Audio (9.0s)
    base_voice2 = load_wav(ROOT / "output" / "v421_audio" / "voice_proof_b.wav")
    n2 = int(9.0 * SR)
    t2 = np.linspace(0, 9.0, n2, endpoint=False)
    v2 = base_voice2[:n2]
    # SFX: Cafe room tone + ceramic cup clink at 4.2s
    noise2 = np.random.normal(0, 0.03, n2)
    cafe_tone = (np.cumsum(noise2) * 0.003).astype(np.float32)
    clink_idx = int(4.2 * SR)
    clink = np.sin(2 * np.pi * 2400 * t2[:int(0.3 * SR)]) * np.exp(-t2[:int(0.3 * SR)] * 16) * 0.25
    cafe_tone[clink_idx : clink_idx + len(clink)] += clink
    sfx2 = cafe_tone.astype(np.float32)
    mix_and_save(v2, sfx2, OUT_DIR / "hanoi_coffee_mixed.wav", 9.0)

    # 3. Antarctic Aurora Audio (9.0s)
    base_voice3 = load_wav(ROOT / "output" / "v421_audio" / "proof_c_mixed.wav")
    n3 = int(9.0 * SR)
    t3 = np.linspace(0, 9.0, n3, endpoint=False)
    v3 = base_voice3[:n3]
    # SFX: Seismic pulse hum (45Hz + 90Hz) + high tech telemetry beep
    hum3 = np.sin(2 * np.pi * 45 * t3) * 0.12 + np.sin(2 * np.pi * 90 * t3) * 0.06
    beep_idx = int(4.0 * SR)
    beep = np.sin(2 * np.pi * 1800 * t3[:int(0.25 * SR)]) * np.exp(-t3[:int(0.25 * SR)] * 10) * 0.2
    hum3[beep_idx : beep_idx + len(beep)] += beep
    sfx3 = hum3.astype(np.float32)
    mix_and_save(v3, sfx3, OUT_DIR / "antarctic_aurora_mixed.wav", 9.0)

    print("\nAll 3 unseen script audio mixes prepared successfully!")

if __name__ == "__main__":
    main()
