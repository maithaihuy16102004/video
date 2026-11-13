"""SFX anchor wiring (A2 wiring item 11): HAMMER_STRIKE anchors via
hammer_strike_times (one hit per strike), RECEIVE_PROP at
RECEIVE_REACH_U, KNEEL_PICK/BEND_PICK at KNEEL_PICK_GRASP_U.
"""

import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.animation.primitives import (
    HAMMER_CYCLE_STRIKE_U, hammer_cycles, hammer_strike_times)
from ai_clip_studio.audio_events import _anchor_fraction, resolve_v1_cues

AGENT = Path(__file__).resolve().parent.parent.parent


def _resolve(events, cues):
    shots = [{"scene": 1, "duration": 20.0, "v1_shot_id": "SC01_SH02",
              "line_index": None, "kind": "shot"}]
    return resolve_v1_cues(
        cues, package={"scenes": [{"number": 1}]}, shots=shots,
        timeline_entries=[], compiled_events=events)


def _cue(cue_id, trigger):
    return {"cue_id": cue_id, "cue_type": "SFX", "name": cue_id,
            "type": "Soft thud", "trigger": trigger,
            "scene_number": 1, "shot_id": "SC01_SH02"}


class TestAnchorFractions(unittest.TestCase):
    def test_ground_pickup_and_receive_fractions(self):
        # Staggered spans: identical (kind, rounded start) pairs
        # dedupe by design, so each cue needs its own time.
        events = [
            {"action_id": "SC01_SH02_ACT01", "action_type": "KNEEL_PICK",
             "start_time": 10.0, "end_time": 11.0},
            {"action_id": "SC01_SH02_ACT02", "action_type": "BEND_PICK",
             "start_time": 16.0, "end_time": 17.2},
            {"action_id": "SC01_SH02_ACT03", "action_type": "RECEIVE_PROP",
             "start_time": 12.0, "end_time": 13.0},
            {"action_id": "SC01_SH02_ACT04", "action_type": "PICK_UP",
             "start_time": 14.0, "end_time": 15.0},
        ]
        cues = [_cue("T1", "KNEEL_PICK"), _cue("T2", "BEND_PICK"),
                _cue("T3", "PROP_RECEIVE"), _cue("T4", "PROP_PICK_UP")]
        report = _resolve(events, cues)
        by_id = {s["cue_id"]: s for s in report["segments"]}
        # Kneel/ground grasp at u=0.50, receive reach at u=0.60,
        # standing pick-up unchanged at u=0.45.
        self.assertEqual(by_id["T1"]["at_seconds"], 10.5)
        self.assertEqual(by_id["T2"]["at_seconds"], 16.6)
        self.assertEqual(by_id["T3"]["at_seconds"], 12.6)
        self.assertEqual(by_id["T4"]["at_seconds"], 14.45)
        for seg in by_id.values():
            self.assertEqual(seg["anchor_method"], "action_event")

    def test_fraction_helper_values(self):
        self.assertEqual(_anchor_fraction("KNEEL_PICK"), 0.50)
        self.assertEqual(_anchor_fraction("BEND_PICK"), 0.50)
        self.assertEqual(_anchor_fraction("RECEIVE_PROP"), 0.60)
        self.assertEqual(_anchor_fraction("PICK_UP"), 0.45)


class TestHammerStrikeAnchors(unittest.TestCase):
    def test_cycles_helper(self):
        self.assertEqual(hammer_cycles(2.7), 3)
        self.assertEqual(hammer_cycles(1.8), 2)
        self.assertEqual(hammer_cycles(0.4), 1)
        self.assertEqual(hammer_cycles(0.0), 1)

    def test_one_segment_per_strike(self):
        events = [{"action_id": "SC01_SH02_ACT01",
                   "action_type": "HAMMER_STRIKE",
                   "start_time": 10.0, "end_time": 12.7}]
        report = _resolve(events, [_cue("H1", "HAMMER_METAL_CONTACT")])
        segs = [s for s in report["segments"] if s["cue_id"] == "H1"]
        expected = [round(10.0 + t, 3) for t in hammer_strike_times(
            2.7, hammer_cycles(2.7))]
        self.assertEqual([s["at_seconds"] for s in segs], expected)
        self.assertEqual(len(expected), 3)
        self.assertEqual(expected[0], round(
            10.0 + 0.9 * HAMMER_CYCLE_STRIKE_U, 3))
        for seg in segs:
            self.assertEqual(seg["anchor_method"], "action_event")
            self.assertEqual(seg["anchor_event_id"], "SC01_SH02_ACT01")

    def test_zeus_forge_cue_anchors_to_strikes(self):
        from ai_clip_studio.action_compiler import compile_actions
        from ai_clip_studio.product_renderer import plan_shots
        from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
        from ai_clip_studio.studio_script_v1_adapter import adapt_document
        text = (AGENT / "examples"
                / "zeus_ep01_fall_of_cronus.studio.md").read_text(
                    encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(text))
        shots = plan_shots(
            package, [{"line_index": i + 1, "duration": 3.0}
                      for i in range(40)])
        spans, clock = {}, 0.0
        for s in shots:
            did = s.get("directive_shot_id")
            if did:
                span = spans.setdefault(str(did), [clock, clock])
                span[1] = clock + float(s["duration"])
            clock += float(s["duration"])
        events, _unsupported = compile_actions(
            package, timeline={"spans": spans})
        hammers = [e for e in events
                   if e["action_type"] == "HAMMER_STRIKE"]
        self.assertTrue(hammers, "no HAMMER_STRIKE event compiled")
        timeline = []
        clock = 0.0
        for s in shots:
            if s.get("line_index") is not None:
                timeline.append({"line_index": s["line_index"],
                                 "start": clock,
                                 "end": clock + float(s["duration"])})
            clock += float(s["duration"])
        report = resolve_v1_cues(
            package.get("v1_audio_cues") or [], package=package,
            shots=shots, timeline_entries=timeline,
            compiled_events=events)
        # SFX_009 ("Forge hammer strike" / "Controlled metal
        # strike") maps to the metal_strike synthesis kind and
        # renders one segment per strike at the strike times.
        cue_report = next(c for c in report["cues"]
                          if c["cue_id"] == "SFX_009")
        self.assertEqual(cue_report["render"], "rendered")
        parts = cue_report["mapping"]["parts"]
        self.assertEqual([p["synth_kind"] for p in parts],
                         ["metal_strike"])
        timing = cue_report["trigger"]
        self.assertEqual(timing["method"], "action_event")
        event = next(e for e in hammers
                     if e["action_id"] == timing["anchor_event_id"])
        expected = [round(float(event["start_time"]) + t, 3)
                    for t in hammer_strike_times(
                        float(event["end_time"])
                        - float(event["start_time"]),
                        hammer_cycles(float(event["end_time"])
                                      - float(event["start_time"])))]
        self.assertEqual(timing["strike_times"], expected)
        self.assertEqual(timing["start"], expected[0])
        self.assertGreaterEqual(len(expected), 1)
        segs = [s for s in report["segments"]
                if s["cue_id"] == "SFX_009"]
        self.assertEqual(len(segs), len(expected))
        for seg, strike in zip(segs, expected):
            self.assertEqual(seg["synth_kind"], "metal_strike")
            self.assertAlmostEqual(seg["at_seconds"], strike,
                                   delta=0.05)


class TestMetalStrikeSynthesis(unittest.TestCase):
    def test_strike_renders_a_decaying_ring(self):
        import wave
        import numpy as np
        from ai_clip_studio.audio_events import SYNTHESIS_MAP
        from ai_clip_studio.product_flow import _synth_segment
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "strike.wav"
            _synth_segment(SYNTHESIS_MAP["metal_strike"], 0.7, out)
            with wave.open(str(out), "rb") as wav:
                self.assertEqual(wav.getframerate(), 48000)
                self.assertEqual(wav.getnchannels(), 1)
                frames = wav.getnframes()
                raw = wav.readframes(frames)
            samples = np.frombuffer(raw, dtype=np.int16).astype(
                np.float64) / 32768.0
            self.assertAlmostEqual(frames / 48000.0, 0.7, delta=0.02)
            peak_db = 20 * np.log10(max(np.max(np.abs(samples)), 1e-9))
            self.assertGreater(peak_db, -30.0)
            # A strike rings then dies: the first 100 ms carry far
            # more energy than the last 100 ms.
            head = samples[:4800]
            tail = samples[-4800:]
            head_rms = float(np.sqrt(np.mean(head ** 2)))
            tail_rms = float(np.sqrt(np.mean(tail ** 2)))
            self.assertGreater(head_rms, 2.0 * tail_rms)
            # Inharmonic partials present: strong energy above 2 kHz.
            spectrum = np.abs(np.fft.rfft(head * np.hanning(len(head))))
            freqs = np.fft.rfftfreq(len(head), 1.0 / 48000.0)
            high = float(np.sum(spectrum[freqs > 2000] ** 2))
            total = float(np.sum(spectrum ** 2))
            self.assertGreater(high / total, 0.15)

    def test_ep1_cues_unaffected_by_the_new_keywords(self):
        from ai_clip_studio.action_compiler import compile_actions
        from ai_clip_studio.product_renderer import plan_shots
        from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
        from ai_clip_studio.studio_script_v1_adapter import adapt_document
        text = (AGENT / "examples"
                / "hitler_ep01_munich_1914.studio.md").read_text(
                    encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(text))
        shots = plan_shots(
            package, [{"line_index": i + 1, "duration": 3.0}
                      for i in range(9)])
        events, _ = compile_actions(package)
        report = resolve_v1_cues(
            package.get("v1_audio_cues") or [], package=package,
            shots=shots, timeline_entries=[], compiled_events=events)
        kinds = {p["synth_kind"]
                 for c in report["cues"]
                 for p in (c.get("mapping") or {}).get("parts", [])}
        self.assertNotIn("metal_strike", kinds)


if __name__ == "__main__":
    unittest.main()
