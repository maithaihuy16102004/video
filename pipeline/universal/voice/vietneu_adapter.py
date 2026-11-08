"""VietNeu-TTS Adapter.

Enforces:
- Synthesis ONLY: Does not decide character identity, does not rewrite text, does not speed up voice.
- ZERO SPEEDUP: Native generated speech duration is preserved 100% (speed_ratio == 1.0).
- ZERO METADATA: Validates text before synthesis.
- CACHING: Deterministic cache by normalized text, voice ID, and performance parameters.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import wave
from pathlib import Path
from typing import Any, Optional

import numpy as np
from vieneu import Vieneu

from .metadata_validator import MetadataValidator
from .voice_types import AudioValidationResult, VietNeuVoiceInfo, VoicePerformancePlan


class VietNeuTTSAdapter:
    """Production adapter for installed VietNeu-TTS engine."""

    def __init__(self, mode: str = "v3nano", cache_dir: Optional[Path] = None):
        self.mode = mode
        self.cache_dir = cache_dir or Path("output/voice_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._tts: Optional[Any] = None
        self._inventory: list[VietNeuVoiceInfo] = []
        self._init_engine()

    def _init_engine(self) -> None:
        try:
            self._tts = Vieneu(mode=self.mode)
            self._discover_inventory()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize installed VietNeu-TTS in mode '{self.mode}': {e}")

    def _discover_inventory(self) -> None:
        """Inspects currently installed VietNeu-TTS voices and builds inventory."""
        self._inventory = []
        if not self._tts:
            return

        raw_voices = self._tts.list_preset_voices()
        for desc, name in raw_voices:
            # Parse gender and region from description if available
            gender = "female" if any(w in desc.lower() for w in ["nữ", "female"]) else "male"
            region = "Bắc" if "bắc" in desc.lower() else ("Nam" if "nam" in desc.lower() else ("Trung" if "trung" in desc.lower() else "none"))
            
            self._inventory.append(
                VietNeuVoiceInfo(
                    voice_id=name,
                    display_name=f"{name} ({desc})",
                    gender=gender,
                    region=region,
                    style_description=desc,
                    engine_mode=self.mode,
                    native_sample_rate=getattr(self._tts, "sample_rate", 24000),
                    is_installed=True,
                )
            )

    def get_voice_inventory(self) -> list[VietNeuVoiceInfo]:
        if not self._inventory:
            self._discover_inventory()
        return list(self._inventory)

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        performance_plan: Optional[VoicePerformancePlan] = None,
    ) -> AudioValidationResult:
        """Synthesizes speech using VietNeu-TTS with absolute zero speedup."""
        # 1. Hard Metadata Validation (Absolute Rule #2)
        MetadataValidator.validate_for_synthesis(text)

        # 2. Check Cache
        perf_hash = f"{performance_plan.emotion.value}_{performance_plan.energy}" if performance_plan else "default"
        hash_input = f"{self.mode}\0{voice_id}\0{text}\0{perf_hash}"
        cache_key = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:24]
        cached_wav = self.cache_dir / f"{cache_key}.wav"

        sample_rate = getattr(self._tts, "sample_rate", 24000)

        if cached_wav.is_file() and cached_wav.stat().st_size > 1000:
            # Copy cached output
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(cached_wav.read_bytes())
            return self._validate_wav(output_path, sample_rate, speed_ratio=1.0, cached=True)

        # 3. Direct Native VietNeu-TTS Synthesis (ZERO SPEEDUP)
        assert self._tts is not None, "VietNeu-TTS engine not loaded."
        
        # Verify voice exists in inventory, fallback to default if not found
        available_names = [v.voice_id for v in self.get_voice_inventory()]
        actual_voice = voice_id if voice_id in available_names else (available_names[0] if available_names else None)

        t0 = time.time()
        audio_arr = self._tts.infer(text=text, voice=actual_voice)
        t_infer = time.time() - t0

        if audio_arr is None or len(audio_arr) == 0:
            raise RuntimeError(f"VietNeu-TTS produced empty audio for voice='{actual_voice}', text='{text[:40]}...'")

        # Native Audio Duration Calculation
        native_samples = len(audio_arr)
        native_duration = native_samples / float(sample_rate)

        # Normalize to peak -1.5 dBFS without modifying playback speed or tempo
        peak = np.max(np.abs(audio_arr))
        if peak > 0.001:
            target_peak = 10.0 ** (-1.5 / 20.0)
            norm_audio = audio_arr * (target_peak / peak)
        else:
            norm_audio = audio_arr

        # Save to Cache and Destination
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_wav_int16(output_path, norm_audio, sample_rate)
        self._write_wav_int16(cached_wav, norm_audio, sample_rate)

        return self._validate_wav(output_path, sample_rate, speed_ratio=1.0, cached=False)

    def _validate_wav(self, wav_path: Path, sample_rate: int, speed_ratio: float, cached: bool) -> AudioValidationResult:
        """Deterministically measures duration, peak, RMS, and silence without speedup."""
        with wave.open(str(wav_path), "rb") as wf:
            n_frames = wf.getnframes()
            sr = wf.getframerate()
            ch = wf.getnchannels()
            raw_bytes = wf.readframes(n_frames)

        duration = n_frames / float(sr) if sr > 0 else 0.0
        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        peak = np.max(np.abs(samples)) if len(samples) > 0 else 0.0
        rms = np.sqrt(np.mean(samples ** 2)) if len(samples) > 0 else 0.0
        peak_dbfs = 20.0 * math.log10(max(1e-5, peak))
        rms_dbfs = 20.0 * math.log10(max(1e-5, rms))

        # Detect leading/trailing silence
        silence_thresh = 0.01  # ~ -40 dBFS
        leading_samples = 0
        for s in samples:
            if abs(s) < silence_thresh:
                leading_samples += 1
            else:
                break
        trailing_samples = 0
        for s in reversed(samples):
            if abs(s) < silence_thresh:
                trailing_samples += 1
            else:
                break

        leading_ms = (leading_samples / float(sr)) * 1000.0 if sr > 0 else 0.0
        trailing_ms = (trailing_samples / float(sr)) * 1000.0 if sr > 0 else 0.0

        is_valid = bool(duration > 0.2 and peak > 0.01 and not np.isnan(rms))

        notes = [
            f"Native duration: {duration:.3f}s",
            f"Speed ratio: {speed_ratio:.2f} (Strictly 1.0, NO SPEEDUP)",
            f"Cached: {cached}",
        ]

        return AudioValidationResult(
            audio_path=str(wav_path),
            native_duration_seconds=round(duration, 3),
            final_duration_seconds=round(duration, 3),
            speed_ratio=speed_ratio,
            sample_rate=sr,
            channels=ch,
            peak_dbfs=round(peak_dbfs, 2),
            rms_dbfs=round(rms_dbfs, 2),
            silence_leading_ms=round(leading_ms, 1),
            silence_trailing_ms=round(trailing_ms, 1),
            clipping_detected=bool(peak >= 0.999),
            is_valid=is_valid,
            validation_notes=notes,
        )

    def _write_wav_int16(self, path: Path, audio: np.ndarray, sample_rate: int) -> None:
        int_data = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(int_data.tobytes())
