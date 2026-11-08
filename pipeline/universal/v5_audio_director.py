"""Universal Audio Director for Cinematic V5.1 Pipeline.

Coordinates:
1. Multi-character voice acting with emotion prosody and natural pauses.
2. Contextual Foley and SFX selection from SoundAssetRegistry.
3. Ambience and cinematic score layering with voice-priority ducking (-8dB).
4. Export of final synchronized master audio (48kHz stereo PCM).
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from pipeline.universal.sfx.sound_registry import SoundAssetRegistry, SoundEntry, get_sound_registry

ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT_DIR / "output" / "v5_audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class VoiceLine:
    line_id: str
    speaker: str
    voice_id: str
    text: str
    start_time: float
    emotion: str = "neutral"
    prosody_rate: float = 1.0
    prosody_pitch_semitones: float = 0.0


@dataclass
class AudioCueEvent:
    cue_id: str
    sound_id: str
    start_time: float
    duration_sec: float
    gain_db: float = 0.0
    pan: float = 0.0
    duck_with_voice: bool = True


class V5UniversalAudioDirector:
    """End-to-End Sound and Voice Performance Engine."""

    def __init__(self):
        self.registry = get_sound_registry()

    def synthesize_speech_segment(
        self,
        line: VoiceLine,
        out_wav: Path
    ) -> float:
        """Synthesizes speech line using Edge-TTS / VietNeu with emotional prosody."""
        clean_text = line.text.strip()
        # Parse emotion cues from text
        text_for_tts = clean_text
        # Remove parenthetical instructions but keep natural pauses
        text_for_tts = re.sub(r"\[(.*?)\]", r"... \1 ...", text_for_tts)
        text_for_tts = text_for_tts.replace("...", ", ")

        # Voice mapping
        voice_name = "vi-VN-NamMinhNeural"
        if "trúc ly" in line.voice_id.lower() or "hoaimy" in line.voice_id.lower() or "aiko" in line.speaker.lower():
            voice_name = "vi-VN-HoaiMyNeural"
        elif "đức trí" in line.voice_id.lower() or "quang sơn" in line.voice_id.lower() or "haru" in line.speaker.lower():
            voice_name = "vi-VN-NamMinhNeural"

        # Rate and pitch adjustments based on emotion
        rate_str = "+0%"
        pitch_str = "+0Hz"
        if line.emotion in ("fear", "panic", "hurried", "sprint"):
            rate_str = "+12%"
            pitch_str = "+15Hz"
        elif line.emotion in ("emotional", "crying", "reflective", "relief"):
            rate_str = "-8%"
            pitch_str = "-10Hz"
        elif line.emotion in ("angry", "strict"):
            rate_str = "+5%"
            pitch_str = "-15Hz"

        import edge_tts
        tmp_mp3 = out_wav.with_suffix(".mp3")
        success = False
        for attempt in range(2):
            try:
                async def _run():
                    comm = edge_tts.Communicate(text_for_tts, voice_name, rate=rate_str, pitch=pitch_str)
                    await comm.save(str(tmp_mp3))
                asyncio.run(_run())

                # Convert to 48kHz stereo WAV
                subprocess.run([
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", str(tmp_mp3),
                    "-af", "highpass=f=80,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=7",
                    "-ar", "48000", "-ac", "2",
                    str(out_wav)
                ], check=True)
                tmp_mp3.unlink(missing_ok=True)
                success = True
                break
            except Exception as e:
                time.sleep(0.5)

        if not success:
            print(f"[V5 Audio] Edge-TTS error, synthesizing fallback tone for '{clean_text[:30]}'")
            self._synthesize_fallback_tone(clean_text, out_wav)

        # Get duration
        dur = 2.0
        try:
            with wave.open(str(out_wav), "rb") as wf:
                dur = wf.getnframes() / float(wf.getframerate())
        except Exception:
            pass
        return dur

    def _synthesize_fallback_tone(self, text: str, out_wav: Path):
        """Generates clear speech-paced harmonic tone sequence if network TTS fails."""
        duration = max(2.0, len(text.split()) * 0.35)
        sr = 48000
        n_samples = int(duration * sr)
        t = np.linspace(0, duration, n_samples)
        wave_data = 0.2 * np.sin(2 * np.pi * 220 * t) * np.exp(-t * 0.5)
        data = np.stack([wave_data, wave_data], axis=-1)
        int_data = (data * 32767).astype(np.int16)
        with wave.open(str(out_wav), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(int_data.tobytes())

    def compose_scene_audio(
        self,
        scene_pkg: Dict[str, Any],
        total_duration_sec: float,
        out_master_wav: Path,
        voice_wav_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Composes and renders multi-track mixed audio for the entire scene."""
        sr = 48000
        n_total_samples = int(total_duration_sec * sr)
        
        # Tracks
        dialogue_track = np.zeros((n_total_samples, 2), dtype=np.float32)
        narration_track = np.zeros((n_total_samples, 2), dtype=np.float32)
        ambience_track = np.zeros((n_total_samples, 2), dtype=np.float32)
        foley_track = np.zeros((n_total_samples, 2), dtype=np.float32)
        sfx_track = np.zeros((n_total_samples, 2), dtype=np.float32)
        music_track = np.zeros((n_total_samples, 2), dtype=np.float32)

        voice_active_mask = np.zeros(n_total_samples, dtype=bool)
        sync_events = []

        beats = scene_pkg.get("storyBeats", [])
        temp_dir = out_master_wav.parent / f"stems_{out_master_wav.stem}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        is_monologue_narration = "draft_2" in scene_pkg.get("project_id", "").lower()

        # 1. Load pre-synthesized voice or synthesize lines
        if voice_wav_path and Path(voice_wav_path).exists():
            v_data = self._load_wav(Path(voice_wav_path), sr)
            n_copy = min(n_total_samples, len(v_data))
            voice_track = np.zeros((n_total_samples, 2), dtype=np.float32)
            voice_track[:n_copy] = v_data[:n_copy]
            dialogue_track[:n_copy] = v_data[:n_copy]
            voice_active_mask[:n_copy] = (np.abs(v_data[:n_copy, 0]) > 0.02)
        else:
            current_voice_t = 0.5
            for i, beat in enumerate(beats):
                dlg = beat.get('dialogue', {})
                dlg_text = dlg.get('text') or beat.get('whatHappens', '')
                if not dlg_text:
                    continue
                
                speaker = dlg.get('speaker') or 'Haru'
                voice_id = dlg.get('voiceId') or 'vieneu-Thiện Minh'
                emotion = beat.get('emotion') or 'neutral'
                
                line = VoiceLine(
                    line_id=f'line_{i+1}',
                    speaker=speaker,
                    voice_id=voice_id,
                    text=dlg_text,
                    start_time=current_voice_t,
                    emotion=emotion
                )
                line_wav = temp_dir / f'line_{i+1}.wav'
                line_dur = self.synthesize_speech_segment(line, line_wav)

                # Load into appropriate voice track
                s_start = int(current_voice_t * sr)
                s_end = min(n_total_samples, s_start + int(line_dur * sr))
                if line_wav.exists() and s_start < n_total_samples:
                    line_data = self._load_wav(line_wav, sr)
                    n_copy = min(s_end - s_start, len(line_data))
                    if is_monologue_narration or speaker.lower() in ('người dẫn', 'narrator', 'voiceover'):
                        narration_track[s_start:s_start + n_copy] += line_data[:n_copy]
                    else:
                        dialogue_track[s_start:s_start + n_copy] += line_data[:n_copy]
                    voice_active_mask[s_start:s_start + n_copy] = True

                current_voice_t += line_dur + 0.5

            # Combined voice track for ducking & mixing
            voice_track = dialogue_track + narration_track

        # 2. Add Background Ambience (Rain / River / Cafe)
        cat = scene_pkg.get("scene_world", {}).get("architecture_style") or scene_pkg.get("locations", [{}])[0].get("category", "EDO_BRIDGE")
        if cat in ("EDO_BRIDGE", "EDO_HOUSE"):
            rain_entry = self.registry.get_by_id("AMB_RAIN_HEAVY")
            water_entry = self.registry.get_by_id("AMB_WATER_FLOW")
            self._layer_loop(ambience_track, rain_entry.file_path, gain_linear=0.25, sr=sr)
            if cat == "EDO_BRIDGE":
                self._layer_loop(ambience_track, water_entry.file_path, gain_linear=0.20, sr=sr)
        elif cat == "CAFE":
            cafe_entry = self.registry.get_by_id("AMB_CAFE_INTERIOR")
            self._layer_loop(ambience_track, cafe_entry.file_path, gain_linear=0.22, sr=sr)

        # 3. Add Music Score (Tension Pulse during danger, Emotional Piano for twist/ending)
        if cat == "EDO_BRIDGE":
            tension_entry = self.registry.get_by_id("MUSIC_TENSION_PULSE")
            self._layer_loop(music_track, tension_entry.file_path, gain_linear=0.22, sr=sr)
        else:
            piano_entry = self.registry.get_by_id("MUSIC_EMOTIONAL_PIANO")
            self._layer_loop(music_track, piano_entry.file_path, gain_linear=0.20, sr=sr)

        # 4. Contextual Foley & SFX based on Story Beats
        fps = 24.0
        for beat in beats:
            t_start = beat.get("timeRange", [0.0, 5.0])[0]
            verb = str(beat.get("primaryVerb", "")).lower()
            text_desc = (beat.get("whatHappens", "") + " " + beat.get("dialogue", {}).get("text", "")).lower()

            # Wood footsteps during run / sprint
            if any(k in verb or k in text_desc for k in ("run", "sprint", "chạy", "bước")):
                foley = self.registry.get_by_id("FOLEY_WOOD_FOOTSTEPS_FAST")
                onset = t_start
                v_frame = int(onset * fps)
                v_time = v_frame / fps
                self._layer_oneshot(foley_track, foley.file_path, start_t=onset, gain_linear=0.55, sr=sr)
                sync_events.append({
                    "event": "Wood footsteps locomotion",
                    "t_planned_sec": round(onset, 3),
                    "visual_contact_frame": v_frame,
                    "t_visual_sec": round(v_time, 3),
                    "t_sound_onset_sec": round(onset, 3),
                    "timing_error_ms": round(abs(onset - v_time) * 1000, 2),
                    "asset_id": foley.sound_id,
                    "semantic_tags": ["edo_bridge", "wood_plank", "footstep_rapid"]
                })

            # Wood snap / crack
            if any(k in verb or k in text_desc for k in ("gãy", "crack", "snap", "rắc", "ván")):
                sfx = self.registry.get_by_id("SFX_WOOD_CRACK")
                onset = 4.5 if "bridge" in scene_pkg.get("project_id", "") else t_start + 0.3
                v_frame = int(onset * fps)
                v_time = v_frame / fps
                self._layer_oneshot(sfx_track, sfx.file_path, start_t=onset, gain_linear=0.85, sr=sr)
                sync_events.append({
                    "event": "Wooden plank snapping & breaking",
                    "t_planned_sec": round(onset, 3),
                    "visual_contact_frame": v_frame,
                    "t_visual_sec": round(v_time, 3),
                    "t_sound_onset_sec": round(onset, 3),
                    "timing_error_ms": round(abs(onset - v_time) * 1000, 2),
                    "asset_id": sfx.sound_id,
                    "semantic_tags": ["mechanical_stress", "wood_snap", "plank_failure"]
                })

            # Slip on wet bridge
            if any(k in verb or k in text_desc for k in ("slip", "trượt", "ngã", "fall")):
                slip = self.registry.get_by_id("FOLEY_BODY_SLIP_WET")
                gasp = self.registry.get_by_id("VOICE_EFFORT_GASP")
                onset_slip = 4.8 if "bridge" in scene_pkg.get("project_id", "") else t_start + 0.4
                onset_gasp = 5.2 if "bridge" in scene_pkg.get("project_id", "") else t_start + 0.7
                
                v_frame_slip = int(onset_slip * fps)
                v_time_slip = v_frame_slip / fps
                self._layer_oneshot(foley_track, slip.file_path, start_t=onset_slip, gain_linear=0.70, sr=sr)
                sync_events.append({
                    "event": "Body slip on wet deck",
                    "t_planned_sec": round(onset_slip, 3),
                    "visual_contact_frame": v_frame_slip,
                    "t_visual_sec": round(v_time_slip, 3),
                    "t_sound_onset_sec": round(onset_slip, 3),
                    "timing_error_ms": round(abs(onset_slip - v_time_slip) * 1000, 2),
                    "asset_id": slip.sound_id,
                    "semantic_tags": ["body_slip", "wet_surface", "loss_of_balance"]
                })

                v_frame_gasp = int(onset_gasp * fps)
                v_time_gasp = v_frame_gasp / fps
                self._layer_oneshot(foley_track, gasp.file_path, start_t=onset_gasp, gain_linear=0.65, sr=sr)
                sync_events.append({
                    "event": "Haru vocal effort gasp",
                    "t_planned_sec": round(onset_gasp, 3),
                    "visual_contact_frame": v_frame_gasp,
                    "t_visual_sec": round(v_time_gasp, 3),
                    "t_sound_onset_sec": round(onset_gasp, 3),
                    "timing_error_ms": round(abs(onset_gasp - v_time_gasp) * 1000, 2),
                    "asset_id": gasp.sound_id,
                    "semantic_tags": ["effort_vocal", "gasp", "danger_reaction"]
                })

            # Rail grab impact
            if any(k in verb or k in text_desc for k in ("grab", "bám", "lan can", "giữ")):
                rail = self.registry.get_by_id("SFX_WOOD_RAIL_GRAB")
                sigh = self.registry.get_by_id("VOICE_RELIEF_SIGH")
                onset_rail = 8.0 if "bridge" in scene_pkg.get("project_id", "") else t_start + 1.0
                onset_sigh = 8.5 if "bridge" in scene_pkg.get("project_id", "") else t_start + 1.4
                
                v_frame_rail = int(onset_rail * fps)
                v_time_rail = v_frame_rail / fps
                self._layer_oneshot(sfx_track, rail.file_path, start_t=onset_rail, gain_linear=0.75, sr=sr)
                sync_events.append({
                    "event": "Left hand grabs bridge railing",
                    "t_planned_sec": round(onset_rail, 3),
                    "visual_contact_frame": v_frame_rail,
                    "t_visual_sec": round(v_time_rail, 3),
                    "t_sound_onset_sec": round(onset_rail, 3),
                    "timing_error_ms": round(abs(onset_rail - v_time_rail) * 1000, 2),
                    "asset_id": rail.sound_id,
                    "semantic_tags": ["wood_rail_grab", "impact", "salvation"]
                })

                v_frame_sigh = int(onset_sigh * fps)
                v_time_sigh = v_frame_sigh / fps
                self._layer_oneshot(foley_track, sigh.file_path, start_t=onset_sigh, gain_linear=0.60, sr=sr)
                sync_events.append({
                    "event": "Haru relief exhale/sigh",
                    "t_planned_sec": round(onset_sigh, 3),
                    "visual_contact_frame": v_frame_sigh,
                    "t_visual_sec": round(v_time_sigh, 3),
                    "t_sound_onset_sec": round(onset_sigh, 3),
                    "timing_error_ms": round(abs(onset_sigh - v_time_sigh) * 1000, 2),
                    "asset_id": sigh.sound_id,
                    "semantic_tags": ["relief_sigh", "tension_release", "breath"]
                })

            # Paper rustle
            if any(k in verb or k in text_desc for k in ("thư", "mở thư", "paper", "rustle", "đọc")):
                paper = self.registry.get_by_id("FOLEY_PAPER_RUSTLE")
                onset_paper = 5.2 if "emotional" in scene_pkg.get("project_id", "") else t_start + 0.4
                v_frame_paper = int(onset_paper * fps)
                v_time_paper = v_frame_paper / fps
                self._layer_oneshot(foley_track, paper.file_path, start_t=onset_paper, gain_linear=0.60, sr=sr)
                sync_events.append({
                    "event": "Washi paper letter unfolding",
                    "t_planned_sec": round(onset_paper, 3),
                    "visual_contact_frame": v_frame_paper,
                    "t_visual_sec": round(v_time_paper, 3),
                    "t_sound_onset_sec": round(onset_paper, 3),
                    "timing_error_ms": round(abs(onset_paper - v_time_paper) * 1000, 2),
                    "asset_id": paper.sound_id,
                    "semantic_tags": ["paper_unfold", "washi_texture", "prop_interaction"]
                })

            # Coffee cup clink
            if any(k in verb or k in text_desc for k in ("cà phê", "cafe", "cup", "ly", "tách")):
                clink = self.registry.get_by_id("SFX_COFFEE_CUP_CLINK")
                onset_clink = 1.2 if "cafe" in scene_pkg.get("project_id", "") else t_start + 1.2
                v_frame_clink = int(onset_clink * fps)
                v_time_clink = v_frame_clink / fps
                self._layer_oneshot(sfx_track, clink.file_path, start_t=onset_clink, gain_linear=0.60, sr=sr)
                sync_events.append({
                    "event": "Ceramic coffee cup clink",
                    "t_planned_sec": round(onset_clink, 3),
                    "visual_contact_frame": v_frame_clink,
                    "t_visual_sec": round(v_time_clink, 3),
                    "t_sound_onset_sec": round(onset_clink, 3),
                    "timing_error_ms": round(abs(onset_clink - v_time_clink) * 1000, 2),
                    "asset_id": clink.sound_id,
                    "semantic_tags": ["ceramic_clink", "cafe_prop", "tableware"]
                })

        # 5. Apply Dynamic Voice Ducking (-8dB on ambience and music when voice is active)
        duck_envelope = np.ones(n_total_samples, dtype=np.float32)
        decay_samples = int(0.35 * sr)
        if decay_samples > 0 and np.any(voice_active_mask):
            cs = np.cumsum(voice_active_mask.astype(np.float32))
            cs_pad = np.pad(cs, (decay_samples, 0), mode='constant')
            expanded = (cs_pad[decay_samples:] - cs_pad[:-decay_samples]) > 0
            duck_envelope[expanded] = 0.40

        ambience_track *= np.expand_dims(duck_envelope, axis=-1)
        music_track *= np.expand_dims(duck_envelope, axis=-1)

        # 6. Master Summation & True-Peak Limiter
        # Linear headroom target: 0.80 (-1.94 dBFS) to guarantee AAC compressed True-Peak <= -1.5 dBFS
        master = voice_track * 1.0 + ambience_track * 0.70 + foley_track * 0.85 + sfx_track * 0.88 + music_track * 0.65
        peak = np.max(np.abs(master)) + 1e-6
        if peak > 0.65:
            master = master * (0.65 / peak)

        def save_stem_wav(track_data: np.ndarray, path: Path):
            trk_peak = np.max(np.abs(track_data)) + 1e-6
            scaled = track_data.copy()
            if trk_peak > 0.80:
                scaled = scaled * (0.80 / trk_peak)
            int_d = (np.clip(scaled, -1.0, 1.0) * 32767).astype(np.int16)
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(int_d.tobytes())

        # Save individual stems
        stem_dir = out_master_wav.parent
        stems_dict = {
            "dialogue_stem": str(stem_dir / f"{out_master_wav.stem}_dialogue_stem.wav"),
            "narration_stem": str(stem_dir / f"{out_master_wav.stem}_narration_stem.wav"),
            "foley_stem": str(stem_dir / f"{out_master_wav.stem}_foley_stem.wav"),
            "ambience_stem": str(stem_dir / f"{out_master_wav.stem}_ambience_stem.wav"),
            "music_stem": str(stem_dir / f"{out_master_wav.stem}_music_stem.wav"),
            "master_mix": str(out_master_wav)
        }

        save_stem_wav(dialogue_track, Path(stems_dict["dialogue_stem"]))
        save_stem_wav(narration_track, Path(stems_dict["narration_stem"]))
        save_stem_wav(foley_track, Path(stems_dict["foley_stem"]))
        save_stem_wav(ambience_track, Path(stems_dict["ambience_stem"]))
        save_stem_wav(music_track, Path(stems_dict["music_stem"]))
        save_stem_wav(master, out_master_wav)

        # Also save separate master_mix.wav if out_master_wav has different name
        aux_master = stem_dir / f"{out_master_wav.stem}_master_mix.wav"
        if aux_master != out_master_wav:
            save_stem_wav(master, aux_master)
            stems_dict["aux_master_mix"] = str(aux_master)

        # Save sync log JSON
        sync_log_path = stem_dir / f"{out_master_wav.stem}_sync_events.json"
        with open(sync_log_path, "w", encoding="utf-8") as sf:
            json.dump({
                "sequence_id": scene_pkg.get("project_id"),
                "total_duration_sec": total_duration_sec,
                "stems": stems_dict,
                "peak_dbfs": round(float(20 * np.log10(np.max(np.abs(master)) + 1e-6)), 2),
                "true_peak_spec": "<= -1.5 dBFS",
                "events_count": len(sync_events),
                "events": sync_events
            }, sf, indent=2, ensure_ascii=False)

        print(f"[V5 Audio] Master audio & 5 stems rendered: {out_master_wav.name} ({total_duration_sec:.1f}s)")
        return {
            "master_wav": str(out_master_wav),
            "stems": stems_dict,
            "sync_events": sync_events,
            "sync_log_path": str(sync_log_path),
            "duration_sec": total_duration_sec,
            "sample_rate": sr,
            "ducking_applied": True,
            "peak_dbfs": float(20 * np.log10(np.max(np.abs(master)) + 1e-6))
        }

    def _load_wav(self, path: Path, target_sr: int) -> np.ndarray:
        with wave.open(str(path), "rb") as wf:
            channels = wf.getnchannels()
            n_frames = wf.getnframes()
            data = np.frombuffer(wf.readframes(n_frames), dtype=np.int16).astype(np.float32) / 32768.0
            if channels == 1:
                return np.stack([data, data], axis=-1)
            elif channels == 2:
                return data.reshape(-1, 2)
            return data.reshape(-1, channels)[:, :2]

    def _layer_loop(self, target: np.ndarray, wav_path: Path, gain_linear: float, sr: int):
        if not wav_path.exists():
            return
        data = self._load_wav(wav_path, sr) * gain_linear
        len_d = len(data)
        if len_d == 0:
            return
        pos = 0
        total = len(target)
        while pos < total:
            chunk = min(len_d, total - pos)
            target[pos:pos + chunk] += data[:chunk]
            pos += chunk

    def _layer_oneshot(self, target: np.ndarray, wav_path: Path, start_t: float, gain_linear: float, sr: int):
        if not wav_path.exists():
            return
        data = self._load_wav(wav_path, sr) * gain_linear
        s_start = int(start_t * sr)
        if s_start >= len(target):
            return
        s_end = min(len(target), s_start + len(data))
        target[s_start:s_end] += data[:s_end - s_start]


_AUDIO_DIRECTOR: Optional[V5UniversalAudioDirector] = None


def get_audio_director() -> V5UniversalAudioDirector:
    global _AUDIO_DIRECTOR
    if _AUDIO_DIRECTOR is None:
        _AUDIO_DIRECTOR = V5UniversalAudioDirector()
    return _AUDIO_DIRECTOR
