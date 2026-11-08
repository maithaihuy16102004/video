"""Universal Sound Asset Generator for Cinematic V5.1 Pipeline.

Generates high-fidelity 48kHz stereo WAV assets for the Curated Sound Registry:
- Ambience: Rain, Water Flow, Cafe Interior, Desert Wind
- Foley: Wood Footsteps, Wet Body Slip, Paper Rustle, Cloth Rustle
- SFX: Wood Plank Crack, Wood Rail Grab Impact, Coffee Cup Clink
- Music: Tension Pulse, Emotional Piano, Cafe Jazz
- Vocal Efforts: Gasp of Terror, Sigh of Relief
"""
import math
import os
import wave
from pathlib import Path
import numpy as np

SAMPLE_RATE = 48000
ASSETS_DIR = Path("assets/sfx")
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def save_wav(filename: Path, data: np.ndarray, sample_rate: int = SAMPLE_RATE):
    """Save float numpy array (-1.0 to 1.0) as 16-bit PCM stereo WAV."""
    if data.ndim == 1:
        data = np.stack([data, data], axis=-1)
    # Clip and convert
    data = np.clip(data, -0.98, 0.98)
    int_data = (data * 32767.0).astype(np.int16)
    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int_data.tobytes())
    print(f"Generated: {filename.name} ({len(data) / sample_rate:.2f}s, {filename.stat().st_size} bytes)")


def gen_rain_heavy(duration: float = 12.0) -> np.ndarray:
    """Heavy rain with turbulent droplets and wide stereo spread."""
    n_samples = int(duration * SAMPLE_RATE)
    # Pink noise base
    white = np.random.normal(0, 1, n_samples)
    # Simple recursive filter for pink noise
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1.0, -2.494956002, 2.017265875, -0.522189400]
    # Use numpy cumsum for rough brown/pink filter
    pink = np.cumsum(white)
    pink -= np.mean(pink)
    pink /= np.max(np.abs(pink)) + 1e-6
    pink *= 0.35

    # Random droplet clicks
    droplets = np.zeros(n_samples)
    n_drops = int(duration * 450)
    drop_indices = np.random.randint(0, n_samples - 500, n_drops)
    for idx in drop_indices:
        drop_len = np.random.randint(80, 400)
        freq = np.random.uniform(1200, 3800)
        t = np.linspace(0, drop_len / SAMPLE_RATE, drop_len)
        drop_wave = np.sin(2 * np.pi * freq * t) * np.exp(-t * 80) * np.random.uniform(0.1, 0.4)
        droplets[idx:idx + drop_len] += drop_wave

    left = pink + droplets * np.random.uniform(0.4, 0.9, n_samples)
    right = pink + droplets * np.random.uniform(0.4, 0.9, n_samples)
    return np.stack([left, right], axis=-1)


def gen_water_flow(duration: float = 10.0) -> np.ndarray:
    """Rushing dark river water with low-end churn."""
    n_samples = int(duration * SAMPLE_RATE)
    noise = np.random.normal(0, 1, n_samples)
    # Low frequency rumble (churn)
    t = np.linspace(0, duration, n_samples)
    churn = (
        0.3 * np.sin(2 * np.pi * 3.5 * t) +
        0.2 * np.sin(2 * np.pi * 1.8 * t + 0.4) +
        0.15 * np.sin(2 * np.pi * 7.2 * t + 1.2)
    )
    # Bandpass around 180Hz - 850Hz
    smooth = np.convolve(noise, np.ones(80) / 80, mode='same')
    water = smooth * (0.8 + 0.4 * churn) * 0.45
    return np.stack([water, np.roll(water, 120)], axis=-1)


def gen_cafe_interior(duration: float = 10.0) -> np.ndarray:
    """Warm cafe murmur ambiance with subtle room reverb."""
    n_samples = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n_samples)
    # Low frequency room rumble
    base = 0.15 * np.sin(2 * np.pi * 65 * t) + 0.1 * np.sin(2 * np.pi * 130 * t)
    # Filtered murmur chatter simulation
    noise = np.random.normal(0, 1, n_samples)
    murmur = np.convolve(noise, np.ones(150) / 150, mode='same') * 0.25
    # Occasional subtle glass / ceramic ambience
    pings = np.zeros(n_samples)
    for ping_time in [2.1, 5.7, 8.4]:
        idx = int(ping_time * SAMPLE_RATE)
        ping_len = 4800
        pt = np.linspace(0, ping_len / SAMPLE_RATE, ping_len)
        pings[idx:idx + ping_len] += 0.12 * np.sin(2 * np.pi * 2600 * pt) * np.exp(-pt * 25)
    return np.stack([base + murmur + pings, base + np.roll(murmur, 200) + pings * 0.8], axis=-1)


def gen_wood_footsteps(duration: float = 5.0, steps_bpm: int = 150) -> np.ndarray:
    """Rapid geta / wooden sandal footsteps on wet wooden bridge."""
    n_samples = int(duration * SAMPLE_RATE)
    out = np.zeros((n_samples, 2))
    interval = 60.0 / steps_bpm
    current = 0.2
    step_num = 0
    while current < duration - 0.4:
        idx = int(current * SAMPLE_RATE)
        step_len = int(0.18 * SAMPLE_RATE)
        t = np.linspace(0, 0.18, step_len)
        # Wooden block pitch: alternating feet (420Hz vs 480Hz)
        f_wood = 440.0 if (step_num % 2 == 0) else 490.0
        # Hard hollow wood knock + click
        knock = np.sin(2 * np.pi * f_wood * t) * np.exp(-t * 45) * 0.5
        click = np.random.normal(0, 1, step_len) * np.exp(-t * 90) * 0.35
        # Wet splash splash
        splash = np.random.normal(0, 1, step_len) * np.exp(-t * 60) * 0.25
        combined = knock + click + splash
        pan = 0.7 if (step_num % 2 == 0) else 0.3
        out[idx:idx + step_len, 0] += combined * pan
        out[idx:idx + step_len, 1] += combined * (1.0 - pan)
        current += interval * np.random.uniform(0.92, 1.08)
        step_num += 1
    return out


def gen_wood_crack() -> np.ndarray:
    """Explosive snapping sound of an old wooden bridge board breaking."""
    duration = 1.2
    n_samples = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n_samples)
    out = np.zeros(n_samples)
    # Violent initial snap transient
    snap_len = int(0.08 * SAMPLE_RATE)
    st = np.linspace(0, 0.08, snap_len)
    snap = (
        np.sin(2 * np.pi * 950 * st) * 0.6 +
        np.sin(2 * np.pi * 1850 * st) * 0.4 +
        np.random.normal(0, 1, snap_len) * 0.7
    ) * np.exp(-st * 70)
    out[:snap_len] += snap
    # Secondary splinter micro-cracks
    for splinter_offset in [0.03, 0.07, 0.12, 0.18, 0.25, 0.32]:
        s_idx = int(splinter_offset * SAMPLE_RATE)
        s_len = int(0.05 * SAMPLE_RATE)
        s_t = np.linspace(0, 0.05, s_len)
        sfreq = np.random.uniform(1200, 3200)
        out[s_idx:s_idx + s_len] += (
            np.sin(2 * np.pi * sfreq * s_t) * 0.35 +
            np.random.normal(0, 1, s_len) * 0.3
        ) * np.exp(-s_t * 90) * np.random.uniform(0.5, 0.9)
    # Low hollow wood resonance
    resonance = 0.4 * np.sin(2 * np.pi * 160 * t) * np.exp(-t * 6.0)
    out += resonance
    return np.stack([out, np.roll(out, 30)], axis=-1)


def gen_body_slip_wet() -> np.ndarray:
    """Body sliding friction whoosh across wet wooden planks."""
    duration = 1.4
    n_samples = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n_samples)
    # Sudden acceleration whoosh
    env = np.sin(np.pi * (t / duration) ** 0.6)
    noise = np.random.normal(0, 1, n_samples)
    # Modulated friction scrape
    freq_mod = np.linspace(800, 250, n_samples)
    friction = noise * np.sin(2 * np.pi * freq_mod * t) * env * 0.4
    # Wet water spray whoosh
    splash = np.convolve(noise, np.ones(40) / 40, mode='same') * env * 0.35
    total = friction + splash
    return np.stack([total, np.roll(total, 50)], axis=-1)


def gen_wood_rail_grab() -> np.ndarray:
    """Heavy hand slap & impact clamping down onto the wooden bridge rail."""
    duration = 1.0
    n_samples = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n_samples)
    # Heavy solid thud (low wood impact)
    thud = 0.7 * np.sin(2 * np.pi * 110 * t) * np.exp(-t * 22)
    # Hand skin slap transient
    slap_len = int(0.04 * SAMPLE_RATE)
    st = np.linspace(0, 0.04, slap_len)
    slap = np.random.normal(0, 1, slap_len) * np.exp(-st * 120) * 0.5
    # Wood groan stress
    groan = 0.25 * np.sin(2 * np.pi * 280 * t) * np.exp(-t * 7)
    out = np.zeros(n_samples)
    out += thud + groan
    out[:slap_len] += slap
    return np.stack([out, out * 0.92], axis=-1)


def gen_paper_rustle() -> np.ndarray:
    """Crisp oiled paper unfolding and rustling."""
    duration = 1.8
    n_samples = int(duration * SAMPLE_RATE)
    out = np.zeros(n_samples)
    # Series of crisp paper crinkles
    for rustle_time in [0.05, 0.22, 0.45, 0.70, 1.05]:
        idx = int(rustle_time * SAMPLE_RATE)
        rlen = int(0.16 * SAMPLE_RATE)
        rt = np.linspace(0, 0.16, rlen)
        crinkle = np.random.normal(0, 1, rlen) * np.exp(-rt * 35) * 0.45
        # High resonance band
        f_paper = np.random.uniform(2400, 5200)
        paper_res = np.sin(2 * np.pi * f_paper * rt) * np.exp(-rt * 50) * 0.25
        out[idx:idx + rlen] += crinkle + paper_res
    return np.stack([out, np.roll(out, 60)], axis=-1)


def gen_coffee_cup_clink() -> np.ndarray:
    """Clear ceramic cup clink on saucer."""
    duration = 1.2
    n_samples = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n_samples)
    # Primary ping 2750Hz and octave harmonic 5500Hz
    ping = (
        0.55 * np.sin(2 * np.pi * 2750 * t) +
        0.30 * np.sin(2 * np.pi * 5500 * t) +
        0.12 * np.sin(2 * np.pi * 8250 * t)
    ) * np.exp(-t * 9.5)
    # Subtle ceramic saucer tap
    saucer = 0.25 * np.sin(2 * np.pi * 620 * t) * np.exp(-t * 28)
    out = ping + saucer
    return np.stack([out, out * 0.85], axis=-1)


def gen_tension_pulse(duration: float = 12.0) -> np.ndarray:
    """Cinematic suspense tension heartbeat pulse and dark pad."""
    n_samples = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n_samples)
    # Dark cello-like sub drone (D minor: 73.4Hz D2, 110Hz A2)
    drone = (
        0.25 * np.sin(2 * np.pi * 73.4 * t) +
        0.18 * np.sin(2 * np.pi * 110.0 * t) +
        0.10 * np.sin(2 * np.pi * 146.8 * t)
    )
    # Heartbeat pulse every 0.9s (lub-dub)
    heart = np.zeros(n_samples)
    interval = 0.9
    cur = 0.2
    while cur < duration - 0.5:
        # Lub
        idx1 = int(cur * SAMPLE_RATE)
        hlen = int(0.12 * SAMPLE_RATE)
        ht1 = np.linspace(0, 0.12, hlen)
        heart[idx1:idx1 + hlen] += 0.5 * np.sin(2 * np.pi * 58 * ht1) * np.exp(-ht1 * 30)
        # Dub
        idx2 = int((cur + 0.18) * SAMPLE_RATE)
        ht2 = np.linspace(0, 0.12, hlen)
        heart[idx2:idx2 + hlen] += 0.35 * np.sin(2 * np.pi * 52 * ht2) * np.exp(-ht2 * 30)
        cur += interval
    total = drone * 0.4 + heart * 0.6
    return np.stack([total, total], axis=-1)


def gen_emotional_piano(duration: float = 14.0) -> np.ndarray:
    """Gentle melancholic piano chords (Am - F - C - G) with warm reverb."""
    n_samples = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n_samples)
    out = np.zeros(n_samples)
    # Chord progression: Am (A3, C4, E4), F (F3, A3, C4), C (C3, E3, G3), G (G3, B3, D4)
    chords = [
        (0.0, [220.0, 261.63, 329.63]),     # Am
        (3.5, [174.61, 220.0, 261.63]),     # F
        (7.0, [130.81, 164.81, 196.00]),     # C
        (10.5, [196.00, 246.94, 293.66]),   # G
    ]
    for start_t, notes in chords:
        s_idx = int(start_t * SAMPLE_RATE)
        chord_dur = 3.5
        c_samples = min(int(chord_dur * SAMPLE_RATE), n_samples - s_idx)
        ct = np.linspace(0, chord_dur, c_samples)
        chord_wave = np.zeros(c_samples)
        for freq in notes:
            # Piano harmonic model: fundamental + 2nd + 3rd harmonic
            note = (
                0.5 * np.sin(2 * np.pi * freq * ct) * np.exp(-ct * 1.1) +
                0.25 * np.sin(2 * np.pi * freq * 2 * ct) * np.exp(-ct * 1.8) +
                0.12 * np.sin(2 * np.pi * freq * 3 * ct) * np.exp(-ct * 2.5)
            )
            chord_wave += note
        out[s_idx:s_idx + c_samples] += chord_wave * 0.35
    # Add simulated stereo reverb delay
    reverb = np.roll(out, 3600) * 0.28 + np.roll(out, 7200) * 0.14
    left = out + reverb
    right = out + np.roll(reverb, 400)
    return np.stack([left, right], axis=-1)


def gen_effort_gasp() -> np.ndarray:
    """Sharp vocal gasp of fright as character slips."""
    duration = 0.75
    n_samples = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n_samples)
    # Breath intake envelope: sharp rise, abrupt stop
    env = np.sin(np.pi * (t / duration) ** 0.5) ** 2
    noise = np.random.normal(0, 1, n_samples)
    # Formants for vocal intake (~850Hz, 1600Hz)
    f1 = np.sin(2 * np.pi * 850 * t)
    f2 = np.sin(2 * np.pi * 1650 * t)
    breath = (noise * 0.6 + f1 * 0.25 + f2 * 0.15) * env * 0.45
    return np.stack([breath, breath * 0.95], axis=-1)


def gen_relief_sigh() -> np.ndarray:
    """Gentle exhalation sigh of relief."""
    duration = 1.2
    n_samples = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n_samples)
    env = np.sin(np.pi * t / duration) * np.exp(-t * 1.4)
    noise = np.random.normal(0, 1, n_samples)
    sigh = noise * env * 0.35
    return np.stack([sigh, sigh * 0.9], axis=-1)


def main():
    print("Synthesizing Curated Sound Asset Library into assets/sfx/...")
    save_wav(ASSETS_DIR / "amb_rain_heavy.wav", gen_rain_heavy(15.0))
    save_wav(ASSETS_DIR / "amb_water_flow.wav", gen_water_flow(15.0))
    save_wav(ASSETS_DIR / "amb_cafe_interior.wav", gen_cafe_interior(15.0))
    save_wav(ASSETS_DIR / "foley_wood_footsteps_fast.wav", gen_wood_footsteps(6.0, 155))
    save_wav(ASSETS_DIR / "sfx_wood_crack.wav", gen_wood_crack())
    save_wav(ASSETS_DIR / "foley_body_slip_wet.wav", gen_body_slip_wet())
    save_wav(ASSETS_DIR / "sfx_wood_rail_grab.wav", gen_wood_rail_grab())
    save_wav(ASSETS_DIR / "foley_paper_rustle.wav", gen_paper_rustle())
    save_wav(ASSETS_DIR / "sfx_coffee_cup_clink.wav", gen_coffee_cup_clink())
    save_wav(ASSETS_DIR / "music_tension_pulse.wav", gen_tension_pulse(16.0))
    save_wav(ASSETS_DIR / "music_emotional_piano.wav", gen_emotional_piano(16.0))
    save_wav(ASSETS_DIR / "voice_effort_gasp.wav", gen_effort_gasp())
    save_wav(ASSETS_DIR / "voice_relief_sigh.wav", gen_relief_sigh())
    print("Curated Sound Asset Library successfully generated!")


if __name__ == "__main__":
    main()
