"""Audio isolation audit (integration sprint section 9).

Stems are synthesised WAVs (silence + sine bursts at known spans);
the audit must catch leaks, plan-level span escapes, and mute-span
violations -- and pass the real Zeus job's rendered stems.
"""

import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from ai_clip_studio.isolation_audit import audit_audio_isolation

AGENT = Path(__file__).resolve().parent.parent.parent
SR = 48000


def _stem(path, total_sec, bursts):
    """Mono 16-bit WAV: silence except sine bursts (start, end)."""
    frames = bytearray()
    for n in range(int(total_sec * SR)):
        t = n / SR
        value = 0
        for start, end, freq in bursts:
            if start <= t < end:
                value = int(12000 * math.sin(2 * math.pi * freq * t))
                break
        frames += struct.pack("<h", value)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes(bytes(frames))


def _job(tmp, *, ambience_bursts, music_bursts, foley_bursts,
         beds, segments, none_spans=None, rain_spans=None,
         end_card=None):
    root = Path(tmp)
    (root / "audio").mkdir()
    _stem(root / "audio" / "ambience.wav", 8.0, ambience_bursts)
    _stem(root / "audio" / "music.wav", 8.0, music_bursts)
    _stem(root / "audio" / "foley.wav", 8.0, foley_bursts)
    (root / "timeline.json").write_text(json.dumps({
        "shots": [{"scene": 1, "duration": 4.0, "start_sec": 0.0},
                  {"scene": 2, "duration": 4.0, "start_sec": 4.0}]}),
        encoding="utf-8")
    (root / "audio_plan.json").write_text(json.dumps({
        "v1_cue_resolution": {
            "beds": beds, "segments": segments,
            "none_spans": none_spans or {}},
        "rain_spans": rain_spans or [],
        "mix": {"end_card_mute": end_card}}), encoding="utf-8")
    return root


BED_AMB = {"stem": "ambience", "synth_kind": "wind_bed",
           "start": 0.0, "end": 4.0, "gain_db": -20.0,
           "cue_id": "AMB_001", "scene": 1, "shot_id": "SC01_SH01"}
BED_MUS = {"stem": "music", "synth_kind": "music_pad",
           "start": 4.0, "end": 8.0, "gain_db": -20.0,
           "cue_id": "BGM_001", "scene": 2, "shot_id": "SC02_SH01"}
SEG = {"sfx": "IMPACT", "synth_kind": "impact",
       "at_seconds": 1.0, "duration": 1.0, "cue_id": "SFX_001",
       "scene": 1}


class TestIsolationAudit(unittest.TestCase):
    def test_clean_job_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_audio_isolation(_job(
                tmp, ambience_bursts=[(0.0, 4.0, 440)],
                music_bursts=[(4.0, 8.0, 330)],
                foley_bursts=[(1.0, 2.0, 880)],
                beds=[BED_AMB, BED_MUS], segments=[SEG]))
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["beds"], 2)
        self.assertEqual(report["segments"], 1)

    def test_leaked_bed_caught(self):
        # Ambience energy sounding through scene 2, where no
        # ambience bed is planned.
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_audio_isolation(_job(
                tmp, ambience_bursts=[(0.0, 8.0, 440)],
                music_bursts=[(4.0, 8.0, 330)],
                foley_bursts=[(1.0, 2.0, 880)],
                beds=[BED_AMB, BED_MUS], segments=[SEG]))
        self.assertFalse(report["passed"])
        self.assertTrue(any("ambience_occupancy" in f and "scene 2" in f
                            for f in report["failures"]),
                        report["failures"])

    def test_bed_escaping_its_scene_span_caught(self):
        bed = dict(BED_AMB, end=5.0)  # crosses into scene 2.
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_audio_isolation(_job(
                tmp, ambience_bursts=[(0.0, 4.0, 440)],
                music_bursts=[(4.0, 8.0, 330)],
                foley_bursts=[(1.0, 2.0, 880)],
                beds=[bed, BED_MUS], segments=[SEG]))
        self.assertFalse(report["passed"])
        self.assertTrue(any(f.startswith("bed_span") for f in
                            report["failures"]), report["failures"])

    def test_silent_planned_bed_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_audio_isolation(_job(
                tmp, ambience_bursts=[],
                music_bursts=[(4.0, 8.0, 330)],
                foley_bursts=[(1.0, 2.0, 880)],
                beds=[BED_AMB, BED_MUS], segments=[SEG]))
        self.assertFalse(report["passed"])
        self.assertTrue(any("bed_audible" in f for f in
                            report["failures"]), report["failures"])

    def test_mute_span_violation_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_audio_isolation(_job(
                tmp, ambience_bursts=[(0.0, 4.0, 440)],
                music_bursts=[(4.0, 8.0, 330)],
                foley_bursts=[(1.0, 2.0, 880)],
                beds=[BED_AMB, BED_MUS], segments=[SEG],
                none_spans={"ambience": [[1.0, 2.0]]}))
        self.assertFalse(report["passed"])
        self.assertTrue(any("mute_span" in f for f in
                            report["failures"]), report["failures"])

    def test_rain_span_crossing_scene_boundary_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_audio_isolation(_job(
                tmp, ambience_bursts=[(0.0, 4.0, 440)],
                music_bursts=[(4.0, 8.0, 330)],
                foley_bursts=[(1.0, 2.0, 880)],
                beds=[BED_AMB, BED_MUS], segments=[SEG],
                rain_spans=[[3.0, 5.0]]))
        self.assertFalse(report["passed"])
        self.assertTrue(any(f.startswith("rain_span") for f in
                            report["failures"]), report["failures"])

    def test_real_zeus_stems_pass(self):
        # The interrupted re-render's finished audio: 10 scenes,
        # 10 beds, 6 segments. Calibrated thresholds must hold.
        report = audit_audio_isolation(
            AGENT / "jobs" / "req_1dd4aed1b2e1")
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(len(report["checks"]), 52)
        self.assertEqual(report["beds"], 10)
        self.assertEqual(report["segments"], 6)


if __name__ == "__main__":
    unittest.main()
