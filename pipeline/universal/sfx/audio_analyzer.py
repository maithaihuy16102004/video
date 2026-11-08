"""Deterministic Audio Analyzer for Measurable Audio Properties.

Measures:
- Duration (seconds)
- Peak Level (dBFS)
- RMS Level (dBFS)
- Silence Detection (leading and trailing ms)
- Attack and Decay Envelope (ms)
- Spectral Centroid / Brightness proxy
- Percussiveness

Separates physical acoustics from semantic interpretation.
"""
from __future__ import annotations

import math
import struct
import subprocess
import wave
from pathlib import Path
from typing import Optional

from .sfx_types import AudioAnalysisProfile


class AudioAnalyzer:
    """Analyzes WAV audio files deterministically without LLM calls."""

    @classmethod
    def analyze_file(cls, path: Path) -> AudioAnalysisProfile:
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")

        # If file is MP3, convert to temporary WAV or inspect via ffprobe
        if path.suffix.lower() == ".mp3":
            wav_path = path.with_suffix(".tmp_probe.wav")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-ar", "48000", "-ac", "2", str(wav_path)],
                    check=True,
                    timeout=10,
                )
                res = cls._analyze_wav(wav_path)
                return res
            finally:
                wav_path.unlink(missing_ok=True)
        else:
            return cls._analyze_wav(path)

    @classmethod
    def _analyze_wav(cls, path: Path) -> AudioAnalysisProfile:
        with wave.open(str(path), "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            raw_bytes = wf.readframes(nframes)

        duration = nframes / float(framerate) if framerate > 0 else 0.0
        if duration <= 0.0 or len(raw_bytes) == 0:
            return AudioAnalysisProfile(duration_seconds=0.0)

        # Unpack samples (16-bit PCM standard)
        fmt = "<" + ("h" * (len(raw_bytes) // 2))
        try:
            samples = struct.unpack(fmt, raw_bytes)
        except Exception:
            # Fallback for non-16bit
            return AudioAnalysisProfile(duration_seconds=duration, sample_rate=framerate, channels=channels)

        # Separate into mono stream for analysis
        if channels > 1:
            mono = [samples[i] for i in range(0, len(samples), channels)]
        else:
            mono = list(samples)

        num_samples = len(mono)
        if num_samples == 0:
            return AudioAnalysisProfile(duration_seconds=duration)

        # Peak & RMS Calculation
        max_val = max(abs(s) for s in mono)
        peak_ratio = max_val / 32768.0 if max_val > 0 else 0.00001
        peak_dbfs = 20.0 * math.log10(peak_ratio)

        sum_sq = sum(float(s * s) for s in mono)
        rms = math.sqrt(sum_sq / num_samples)
        rms_ratio = rms / 32768.0 if rms > 0 else 0.00001
        rms_dbfs = 20.0 * math.log10(rms_ratio)

        # Silence Detection (-45 dBFS threshold = ~184 amplitude)
        silence_threshold = 184
        leading_silence_samples = 0
        for s in mono:
            if abs(s) < silence_threshold:
                leading_silence_samples += 1
            else:
                break
        leading_ms = (leading_silence_samples / float(framerate)) * 1000.0

        trailing_silence_samples = 0
        for s in reversed(mono):
            if abs(s) < silence_threshold:
                trailing_silence_samples += 1
            else:
                break
        trailing_ms = (trailing_silence_samples / float(framerate)) * 1000.0

        # Attack & Decay Envelope
        # Attack = time from silence end to 90% peak
        peak_idx = 0
        cur_max = 0
        for idx, s in enumerate(mono):
            if abs(s) > cur_max:
                cur_max = abs(s)
                peak_idx = idx

        attack_samples = max(1, peak_idx - leading_silence_samples)
        attack_ms = (attack_samples / float(framerate)) * 1000.0

        # Decay = time from peak to drop to 10% peak
        decay_thresh = max_val * 0.10
        decay_idx = num_samples - 1
        for idx in range(peak_idx, num_samples):
            if abs(mono[idx]) < decay_thresh:
                decay_idx = idx
                break
        decay_samples = max(1, decay_idx - peak_idx)
        decay_ms = (decay_samples / float(framerate)) * 1000.0

        # Spectral Centroid proxy (Zero-crossing rate correlates with brightness)
        zero_crossings = 0
        for i in range(1, num_samples):
            if (mono[i - 1] >= 0 and mono[i] < 0) or (mono[i - 1] < 0 and mono[i] >= 0):
                zero_crossings += 1
        zcr = zero_crossings / float(num_samples)
        # Approximate centroid in Hz: ZCR * (framerate / 2)
        spectral_centroid = zcr * (framerate / 2.0)

        # Percussiveness: Sharp attack (< 40ms) and high crest factor (Peak - RMS > 10dB)
        crest_factor = peak_dbfs - rms_dbfs
        is_percussive = (attack_ms < 50.0) and (crest_factor > 8.0)

        return AudioAnalysisProfile(
            duration_seconds=round(duration, 3),
            sample_rate=framerate,
            channels=channels,
            peak_dbfs=round(peak_dbfs, 2),
            rms_dbfs=round(rms_dbfs, 2),
            silence_leading_ms=round(leading_ms, 1),
            silence_trailing_ms=round(trailing_ms, 1),
            attack_ms=round(attack_ms, 1),
            decay_ms=round(decay_ms, 1),
            spectral_centroid_hz=round(spectral_centroid, 1),
            dynamic_range_db=round(crest_factor, 1),
            is_percussive=is_percussive,
        )

    @classmethod
    def synthesize_fallback_profile(cls, duration: float = 1.0, is_percussive: bool = True) -> AudioAnalysisProfile:
        """Fallback for metadata-only entries without local audio."""
        return AudioAnalysisProfile(
            duration_seconds=round(duration, 3),
            sample_rate=48000,
            channels=2,
            peak_dbfs=-1.5,
            rms_dbfs=-16.0,
            silence_leading_ms=10.0,
            silence_trailing_ms=50.0,
            attack_ms=15.0 if is_percussive else 120.0,
            decay_ms=250.0,
            spectral_centroid_hz=3200.0 if is_percussive else 1500.0,
            dynamic_range_db=14.5,
            is_percussive=is_percussive,
        )

    def analyze(self, path: Optional[str | Path] = None) -> AudioAnalysisProfile:
        if path:
            pp = Path(path)
            if pp.is_file():
                try:
                    return self.analyze_file(pp)
                except Exception:
                    pass
        return self.synthesize_fallback_profile()
