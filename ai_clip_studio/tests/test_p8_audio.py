"""P8 audio recovery tests: voice identity, loudness normalisation,
synth reference levels, end-card mute, audibility measurements.

No real TTS API calls: the provider test uses a fake `tts` binary that
renders a sine MP3. ffmpeg is real (the pipeline's own tool).
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio import tts_cli_provider as tcp
from ai_clip_studio.audio_events import SYNTHESIS_MAP, resolve_mix_gains
from ai_clip_studio.product_flow import (
    _mix_audio, _normalize_synth_segment, _peak_db_window, _rms_db,
    _rms_db_windows, _synth_segment)


def _sine_wav(path: Path, seconds: float = 1.0, volume: float = 0.3,
              frequency: float = 440.0) -> Path:
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"sine=frequency={frequency}:duration={seconds}",
         "-af", f"volume={volume}", "-ac", "1", "-ar", "48000",
         str(path)],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return path


class TestVoiceFor(unittest.TestCase):
    def test_narrator(self):
        self.assertEqual(tcp.voice_for("narrator"), tcp.NARRATOR_VOICE)

    def test_female_first_southern_hint(self):
        # The old order matched bare "nam" first: "giọng nữ miền Nam"
        # (southern FEMALE voice) resolved to the male voice.
        self.assertEqual(tcp.voice_for("Lan", "giọng nữ miền Nam"),
                         tcp.FEMALE_VOICE)

    def test_male_phrase(self):
        self.assertEqual(tcp.voice_for("Minh", "giọng nam"),
                         tcp.MALE_VOICE)

    def test_bare_nam_substring_does_not_fire(self):
        self.assertEqual(tcp.voice_for("Nam", "giọng Việt Nam"),
                         tcp.DEFAULT_VOICE)
        self.assertEqual(tcp.voice_for("X", ""), tcp.DEFAULT_VOICE)


class TestResolveVoiceAssignment(unittest.TestCase):
    def test_distinct_voice_ids_get_distinct_voices(self):
        # The delivered Ep1 draft voiced BOTH male characters with
        # ronan; distinct script VOICE_IDs must stay distinct.
        assignment, warnings = tcp.resolve_voice_assignment(
            ["Adolf Hitler", "Người lính Bavaria"],
            voice_hints={"Adolf Hitler": "giọng nam",
                         "Người lính Bavaria": "giọng nam"},
            voice_ids={"Adolf Hitler": "Đức Trí",
                       "Người lính Bavaria": "Mạnh Dũng"})
        self.assertEqual(assignment["Adolf Hitler"]["voice"],
                         tcp.MALE_VOICE)
        self.assertEqual(assignment["Người lính Bavaria"]["voice"],
                         tcp.DEFAULT_VOICE)
        self.assertEqual(warnings, [])

    def test_same_voice_id_shares_voice(self):
        assignment, _ = tcp.resolve_voice_assignment(
            ["A", "B"], voice_hints={"A": "giọng nữ", "B": "giọng nữ"},
            voice_ids={"A": "Lan", "B": "Lan"})
        self.assertEqual(assignment["A"]["voice"],
                         assignment["B"]["voice"])

    def test_narrator_reserves_its_voice(self):
        assignment, _ = tcp.resolve_voice_assignment(
            ["narrator", "Lan", "Mai"],
            voice_hints={"Lan": "giọng nữ", "Mai": "giọng nữ"},
            voice_ids={"Lan": "L1", "Mai": "L2"})
        self.assertEqual(assignment["narrator"]["voice"],
                         tcp.NARRATOR_VOICE)
        self.assertNotIn(tcp.NARRATOR_VOICE,
                         [assignment["Lan"]["voice"],
                          assignment["Mai"]["voice"]])

    def test_pool_exhaustion_is_a_recorded_warning(self):
        _a, warnings = tcp.resolve_voice_assignment(
            ["A", "B", "C"],
            voice_hints={"A": "giọng nam", "B": "giọng nam",
                         "C": "giọng nam"},
            voice_ids={"A": "V1", "B": "V2", "C": "V3"})
        self.assertEqual(len(warnings), 1)
        self.assertIn("reuse", warnings[0])

    def test_deterministic(self):
        args = (["A", "B"],)
        kwargs = {"voice_hints": {"A": "giọng nam", "B": "giọng nữ"},
                  "voice_ids": {"A": "V1", "B": "V2"}}
        self.assertEqual(tcp.resolve_voice_assignment(*args, **kwargs),
                         tcp.resolve_voice_assignment(*args, **kwargs))


class TestNormalizeWav(unittest.TestCase):
    # The lavfi sine source renders quietly (peak near -18 dB at
    # volume 1.0), so the volumes below are calibrated to measured
    # volumedetect levels, not to naive sine amplitude math.
    def test_quiet_line_is_raised_to_target(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _sine_wav(Path(d) / "quiet.wav", volume=0.3)
            rec = tcp._normalize_wav(wav)
            self.assertGreater(rec["gain_db"], 5.0)
            mean_after, max_after = tcp._wav_levels(wav)
            self.assertAlmostEqual(mean_after, tcp.VOICE_TARGET_DB,
                                   delta=1.5)
            self.assertLessEqual(max_after, tcp.VOICE_PEAK_CEILING_DB)

    def test_boost_is_capped(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _sine_wav(Path(d) / "faint.wav", volume=0.03)
            rec = tcp._normalize_wav(wav)
            self.assertEqual(rec["gain_db"], tcp.VOICE_MAX_GAIN_DB)
            self.assertTrue(rec["capped"])

    def test_loud_line_is_lowered_without_clipping(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _sine_wav(Path(d) / "loud.wav", volume=3.0)
            rec = tcp._normalize_wav(wav)
            self.assertLess(rec["gain_db"], 0.0)
            _mean, max_after = tcp._wav_levels(wav)
            self.assertLessEqual(max_after, tcp.VOICE_PEAK_CEILING_DB)

    def test_silence_is_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            wav = _sine_wav(Path(d) / "silent.wav", volume=0.0)
            rec = tcp._normalize_wav(wav)
            self.assertEqual(rec["gain_db"], 0.0)
            self.assertIn("note", rec)


class TestNormalizeSynthSegment(unittest.TestCase):
    def test_music_pad_reaches_reference(self):
        # Raw pad renders near -40 dB RMS; the gain chain assumes a
        # -12 dB baseline. Normalisation must close that gap.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "pad.wav"
            _synth_segment(SYNTHESIS_MAP["music_pad"], 2.0, path)
            before = _rms_db(path)
            self.assertLess(before, -30.0)
            rec = _normalize_synth_segment(path)
            self.assertGreater(rec["gain_db"], 20.0)
            self.assertAlmostEqual(_rms_db(path), -12.0, delta=1.5)


class TestProviderManifest(unittest.TestCase):
    FAKE_TTS = (
        "import subprocess, sys\n"
        "data = sys.stdin.buffer.read()\n"
        "args = sys.argv[1:]\n"
        "out = args[args.index('--output') + 1]\n"
        "subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi',\n"
        "                '-i', 'sine=frequency=440:duration=0.6',\n"
        "                '-q:a', '4', out], check=True)\n")

    def test_manifest_records_engine_and_voices(self):
        with tempfile.TemporaryDirectory() as d:
            job_dir = Path(d)
            fake = job_dir / "fake_tts.py"
            fake.write_text(self.FAKE_TTS, encoding="utf-8")
            orig = tcp.TTS_BIN
            tcp.TTS_BIN = f"python3 {fake}"
            try:
                # The provider passes TTS_BIN as argv[0]; a command
                # string needs a real executable, so wrap it.
                wrapper = job_dir / "fake_tts"
                wrapper.write_text(
                    f"#!/bin/sh\nexec python3 {fake} \"$@\"\n",
                    encoding="utf-8")
                wrapper.chmod(0o755)
                tcp.TTS_BIN = str(wrapper)
                lines = [
                    {"text": "Tôi là Adolf.", "speaker": "Adolf Hitler",
                     "kind": "narration"},
                    {"text": "Đứng lại!", "speaker": "Người lính Bavaria",
                     "kind": "dialogue"},
                ]
                wavs = tcp.tts_cli_provider(
                    lines, job_dir,
                    voice_hints={"Adolf Hitler": "giọng nam",
                                 "Người lính Bavaria": "giọng nam"},
                    voice_ids={"Adolf Hitler": "Đức Trí",
                               "Người lính Bavaria": "Mạnh Dũng"})
            finally:
                tcp.TTS_BIN = orig
            self.assertEqual(len(wavs), 2)
            manifest = json.loads(
                (job_dir / "voices_manifest.json").read_text(
                    encoding="utf-8"))
            self.assertIn("NOT VieNeu", manifest["engine"])
            self.assertEqual(manifest["distinct_voices_used"], 2)
            by_speaker = {r["speaker"]: r for r in manifest["lines"]}
            self.assertEqual(by_speaker["Adolf Hitler"]["voice"],
                             tcp.MALE_VOICE)
            self.assertEqual(by_speaker["Adolf Hitler"]
                             ["script_voice_id"], "Đức Trí")
            self.assertEqual(by_speaker["Người lính Bavaria"]["voice"],
                             tcp.DEFAULT_VOICE)
            for row in manifest["lines"]:
                self.assertIn("gain_db",
                              row["normalisation"])


class TestMixEndCardMute(unittest.TestCase):
    def test_beds_muted_across_end_card(self):
        with tempfile.TemporaryDirectory() as d:
            job_dir = Path(d)
            v1 = _sine_wav(job_dir / "v1.wav", seconds=1.0)
            v2 = _sine_wav(job_dir / "v2.wav", seconds=1.0)
            entries = [
                {"wav": str(v1), "start": 0.0, "end": 1.0,
                 "kind": "narration"},
                {"wav": str(v2), "start": 2.0, "end": 3.0,
                 "kind": "dialogue"},
            ]
            _mix, info = _mix_audio(
                job_dir, entries, 6.0, [(0.0, 6.0)], segments=[], beds=[],
                mix_gains=resolve_mix_gains({}), none_spans={},
                end_card_span=(4.0, 6.0))
            self.assertEqual(info["end_card_mute"], [4.0, 6.0])
            ambience = Path(info["stems"]["ambience.wav"])
            # Rain is audible before the card...
            self.assertGreater(
                _rms_db_windows(ambience, [(0.5, 1.5)]), -50.0)
            # ...and silent across the card span.
            self.assertLess(
                _rms_db_windows(ambience, [(4.5, 5.5)]), -100.0)
            self.assertIn("audibility", info)
            self.assertEqual(info["audibility"]["foley_events"], [])

    def test_foley_peak_measurement(self):
        with tempfile.TemporaryDirectory() as d:
            job_dir = Path(d)
            v1 = _sine_wav(job_dir / "v1.wav", seconds=1.0)
            entries = [{"wav": str(v1), "start": 0.0, "end": 1.0,
                        "kind": "narration"}]
            segments = [{
                "event_type": "knock", "at_seconds": 2.0,
                "end_seconds": 2.4, "duration": 0.4,
                "sfx": "KNOCK", "category": "foley", "gain_db": -12.0,
                "synth_kind": "knock", "method": "test",
                "cue_name": "Knock", "cue_id": "SFX_TEST",
                "scene": 1, "shot_id": "SC01_SH01", "source": "test"}]
            _mix, info = _mix_audio(
                job_dir, entries, 4.0, [], segments=segments,
                beds=[], mix_gains=resolve_mix_gains({}),
                none_spans={})
            events = info["audibility"]["foley_events"]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["cue_id"], "SFX_TEST")
            # Normalised knock at -12 dB base gain: clearly present.
            self.assertGreater(events[0]["peak_db"], -45.0)
            self.assertFalse(events[0]["likely_inaudible"])
            self.assertIn("knock_000.wav",
                          info["synth_normalisation"])


if __name__ == "__main__":
    unittest.main()
