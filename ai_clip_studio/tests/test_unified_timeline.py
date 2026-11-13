"""Unified production timeline (directive section 9): one clock,
integer indices, frozen schedule, explicit rebuild on conflict."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.audio_events import build_shot_clock, resolve_mix_gains
from ai_clip_studio.product_flow import (
    _assign_line_starts, _mix_audio, _rms_db_windows)
from ai_clip_studio.product_renderer import plan_shots
from ai_clip_studio.semantic_contracts import FrozenInstanceError
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.unified_timeline import (
    SchedulingConflict, UnifiedTimelineBuilder, build_unified_timeline,
    check_timeline_refs, sec_to_frame, sec_to_sample,
    stamp_timeline_refs, timeline_ref)

AGENT = Path(__file__).resolve().parent.parent.parent


def _package(name):
    return adapt_document(parse_studio_script_v1(
        (AGENT / "examples" / f"{name}.studio.md").read_text(
            encoding="utf-8")))


def _fixture(name, durations):
    pkg = _package(name)
    n_lines = sum(len(sc["lines"]) for sc in pkg["scenes"])
    entries = [{"line_index": i + 1,
                "kind": ("narration" if i % 2 == 0 else "dialogue"),
                "speaker": "CHAR", "text": f"line {i + 1}",
                "duration": durations[i] if i < len(durations) else 0.65}
               for i in range(n_lines)]
    shots = plan_shots(pkg, entries)
    _assign_line_starts(shots, entries)
    events, _unsupported = compile_actions(pkg)
    return pkg, shots, entries, events


class TestConversion(unittest.TestCase):
    def test_round_half_up(self):
        self.assertEqual(sec_to_frame(1.0), 24)
        self.assertEqual(sec_to_frame(0.5), 12)
        # 0.0208333s = half a frame: rounds UP (banker's would give 0).
        self.assertEqual(sec_to_frame(0.5 / 24), 1)
        self.assertEqual(sec_to_sample(1.0), 48000)
        self.assertEqual(sec_to_sample(0.5), 24000)

    def test_seconds_derive_from_indices(self):
        builder = UnifiedTimelineBuilder()
        builder.add_shot("s1", 0.0, 2.0)
        timeline = builder.freeze()
        self.assertEqual(timeline.total_frames, 48 + 12)
        self.assertEqual(timeline.total_sec, 60 / 24)
        self.assertEqual(timeline.total_samples, 120000)


class TestBuilderValidation(unittest.TestCase):
    def test_shot_gap_is_a_conflict(self):
        builder = UnifiedTimelineBuilder()
        builder.add_shot("s1", 0.0, 2.0)
        with self.assertRaises(SchedulingConflict):
            builder.add_shot("s2", 2.5, 4.0)

    def test_shot_overlap_is_a_conflict(self):
        builder = UnifiedTimelineBuilder()
        builder.add_shot("s1", 0.0, 2.0)
        with self.assertRaises(SchedulingConflict):
            builder.add_shot("s2", 1.5, 3.0)

    def test_speech_overlap_spans_kinds(self):
        builder = UnifiedTimelineBuilder()
        builder.add_shot("s1", 0.0, 10.0)
        builder.add_line(1, "narration", 1.0, 3.0)
        with self.assertRaises(SchedulingConflict):
            builder.add_line(2, "dialogue", 2.5, 4.0)

    def test_duplicate_interval_id_is_a_conflict(self):
        builder = UnifiedTimelineBuilder()
        builder.add_shot("s1", 0.0, 2.0)
        builder.add_line(1, "dialogue", 0.5, 1.5)
        with self.assertRaises(SchedulingConflict):
            builder.add_line(1, "dialogue", 1.6, 1.9)

    def test_frozen_schedule_rejects_mutation(self):
        builder = UnifiedTimelineBuilder()
        builder.add_shot("s1", 0.0, 2.0)
        timeline = builder.freeze()
        with self.assertRaises(SchedulingConflict):
            builder.add_shot("s2", 2.0, 3.0)
        with self.assertRaises(FrozenInstanceError):
            from ai_clip_studio.semantic_contracts import TimelineInterval
            timeline.schedule.add(TimelineInterval(
                track="shots", interval_id="x", start_frame=48,
                end_frame=72, start_sample=96000, end_sample=144000))

    def test_freeze_requires_shots_and_complete_narration(self):
        builder = UnifiedTimelineBuilder()
        with self.assertRaises(SchedulingConflict):
            builder.freeze()
        builder.add_shot("s1", 0.0, 4.0)
        builder.add_line(1, "dialogue", 0.5, 1.5)
        with self.assertRaises(SchedulingConflict):
            builder.freeze(expected_line_ids=["line:1", "line:2"])
        timeline = builder.freeze(expected_line_ids=["line:1"])
        self.assertTrue(timeline.narration_complete(["line:1"]))

    def test_draft_total_tracks_shots_plus_tail(self):
        builder = UnifiedTimelineBuilder()
        builder.add_shot("s1", 0.0, 2.0)
        self.assertAlmostEqual(builder.draft_total_sec, 2.5)
        builder.add_shot("s2", 2.0, 5.0)
        self.assertAlmostEqual(builder.draft_total_sec, 5.5)

    def test_camera_cut_is_a_one_frame_marker(self):
        builder = UnifiedTimelineBuilder()
        builder.add_shot("s1", 0.0, 2.0)
        builder.add_camera_cut("s2", 2.0)
        builder.add_shot("s2", 2.0, 4.0)
        timeline = builder.freeze()
        cuts = timeline.track("camera_cuts")
        self.assertEqual(len(cuts), 1)
        interval, _payload = cuts[0]
        self.assertEqual(interval.start_frame, 48)
        self.assertEqual(interval.end_frame, 49)

    def test_to_dict_round_trip_shape(self):
        builder = UnifiedTimelineBuilder()
        builder.add_shot("s1", 0.0, 2.0, {"scene": 1})
        builder.add_line(1, "dialogue", 0.5, 1.5, {"text": "hi"})
        blob = builder.freeze().to_dict()
        self.assertEqual(blob["total_frames"], 60)
        self.assertEqual(len(blob["intervals"]), 2)
        self.assertEqual(blob["intervals"][1]["payload"]["text"], "hi")


class TestRealScripts(unittest.TestCase):
    def test_ep1_fixture_clock(self):
        _pkg, shots, entries, events = _fixture(
            "hitler_ep01_munich_1914", [0.65] * 9)
        timeline = build_unified_timeline(shots, entries, events)
        self.assertEqual(len(timeline.track("shots")), 21)
        self.assertEqual(len(timeline.track("camera_cuts")), 20)
        self.assertTrue(timeline.narration_complete(
            [f"line:{i + 1}" for i in range(9)]))
        # Total = shot clock + 0.5 s tail, in whole frames.
        shot_sec = sum(float(s["duration"]) for s in shots)
        self.assertEqual(timeline.total_frames,
                         sec_to_frame(shot_sec) + 12)
        # Prop interactions = events carrying a prop.
        with_prop = [e for e in events if e.get("prop_id")]
        self.assertEqual(len(timeline.track("prop_interactions")),
                         len(with_prop))
        self.assertGreater(len(with_prop), 0)
        # Shots tile: end of one == start of the next, in frames.
        spans = [i for i, _ in timeline.track("shots")]
        for prev, nxt in zip(spans, spans[1:]):
            self.assertEqual(prev.end_frame, nxt.start_frame)

    def test_zeus_fixture_clock(self):
        _pkg, shots, entries, events = _fixture(
            "zeus_ep01_fall_of_cronus", [0.65] * 40)
        timeline = build_unified_timeline(shots, entries, events)
        self.assertEqual(len(timeline.track("shots")), 64)
        self.assertTrue(timeline.narration_complete(
            [f"line:{i + 1}" for i in range(40)]))
        shot_sec = sum(float(s["duration"]) for s in shots)
        self.assertEqual(timeline.total_frames,
                         sec_to_frame(shot_sec) + 12)

    def test_end_card_track(self):
        _pkg, shots, entries, events = _fixture(
            "hitler_ep01_munich_1914", [0.65] * 9)
        timeline = build_unified_timeline(shots, entries, events)
        cards = timeline.track("end_cards")
        self.assertEqual(len(cards), 1)
        interval, _payload = cards[0]
        last_shot = timeline.track("shots")[-1][0]
        self.assertEqual(interval.start_frame, last_shot.start_frame)


def _sine_wav(path: Path, seconds: float = 1.0) -> Path:
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"sine=frequency=440:duration={seconds}",
         "-af", "volume=0.3", "-ac", "1", "-ar", "48000",
         str(path)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return path


class TestRainConfinement(unittest.TestCase):
    def test_rain_stays_inside_its_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            voice = _sine_wav(job_dir / "v1.wav")
            entries = [{"wav": str(voice), "start": 0.0, "end": 1.0,
                        "kind": "narration"}]
            _mix, info = _mix_audio(
                job_dir, entries, 8.5, [(4.0, 6.0)],
                segments=[], beds=[],
                mix_gains=resolve_mix_gains({}), none_spans={})
            self.assertEqual(len(info["rain_beds"]), 1)
            self.assertIsNotNone(info["rain_db"])
            ambience = Path(info["stems"]["ambience.wav"])
            # Audible inside the rainy span...
            self.assertGreater(
                _rms_db_windows(ambience, [(4.5, 5.5)]), -50.0)
            # ...silent in the dry scenes before and after.
            self.assertLess(
                _rms_db_windows(ambience, [(1.5, 2.5)]), -100.0)
            self.assertLess(
                _rms_db_windows(ambience, [(7.0, 8.0)]), -100.0)

    def test_no_spans_means_no_rain(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            voice = _sine_wav(job_dir / "v1.wav")
            entries = [{"wav": str(voice), "start": 0.0, "end": 1.0,
                        "kind": "narration"}]
            _mix, info = _mix_audio(
                job_dir, entries, 8.5, [],
                segments=[], beds=[],
                mix_gains=resolve_mix_gains({}), none_spans={})
            self.assertEqual(info["rain_beds"], [])
            self.assertIsNone(info["rain_db"])
            self.assertNotIn("ambience.wav", info["stems"])


class TestJobWiring(unittest.TestCase):
    def test_ep1_job_freezes_timeline_and_scopes_rain(self):
        from ai_clip_studio import product_flow
        from ai_clip_studio.tests.test_unauthorized_story_change import (
            _stub_tts)
        script = (AGENT / "examples"
                  / "hitler_ep01_munich_1914.studio.md").read_text(
                      encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            with mock.patch.object(product_flow, "tts_cli_provider",
                                   side_effect=_stub_tts), \
                mock.patch.object(
                    product_flow, "render_product_video",
                    side_effect=RuntimeError("STOP_AFTER_SUBTITLE")):
                job = product_flow.run_product_job(
                    script, job_dir, upload=False)
            self.assertIn("STOP_AFTER_SUBTITLE", job.errors[0])
            unified = json.loads(
                (job_dir / "unified_timeline.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(unified["fps"], 24)
            self.assertEqual(unified["total_frames"],
                             sec_to_frame(sum(
                                 float(s["duration"])
                                 for s in job.shots)) + 12)
            tracks = {i["track"] for i in unified["intervals"]}
            for expected in ("shots", "narration", "dialogue",
                             "actions", "prop_interactions", "sfx",
                             "ambience", "subtitles", "camera_cuts",
                             "end_cards"):
                self.assertIn(expected, tracks)
            # Rain: scene 6 only, exactly its shot-clock span.
            plan = json.loads(
                (job_dir / "audio_plan.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(plan["rainy_scenes"], [6])
            clock = build_shot_clock(job.shots)
            span = clock["scene_spans"][6]
            self.assertEqual(plan["rain_spans"], [[span[0], span[1]]])
            self.assertEqual(len(plan["mix"]["rain_beds"]), 1)


class TestChecksumAndRefs(unittest.TestCase):
    """Sprint section 8: version + checksum + artifact references."""

    def _timeline(self, end=2.0):
        builder = UnifiedTimelineBuilder()
        builder.add_shot("s1", 0.0, end, {"scene": 1})
        builder.add_line(1, "dialogue", 0.5, 1.5, {"text": "hi"})
        return builder.freeze()

    def test_to_dict_carries_version_and_checksum(self):
        blob = self._timeline().to_dict()
        self.assertEqual(blob["timeline_version"], 1)
        self.assertEqual(len(blob["checksum"]), 64)
        self.assertEqual(blob["checksum"],
                         self._timeline().checksum)

    def test_checksum_deterministic_and_sensitive(self):
        self.assertEqual(self._timeline().checksum,
                         self._timeline().checksum)
        self.assertNotEqual(self._timeline(end=2.0).checksum,
                            self._timeline(end=2.5).checksum)

    def test_version_passthrough(self):
        builder = UnifiedTimelineBuilder(version=3)
        builder.add_shot("s1", 0.0, 2.0)
        timeline = builder.freeze()
        self.assertEqual(timeline.version, 3)
        self.assertEqual(timeline.to_dict()["timeline_version"], 3)
        # The version is NOT part of the hashed content: a rebuild
        # with identical intervals keeps the checksum.
        builder1 = UnifiedTimelineBuilder(version=1)
        builder1.add_shot("s1", 0.0, 2.0)
        self.assertEqual(timeline.checksum,
                         builder1.freeze().checksum)

    def test_timeline_ref_from_object_and_dict(self):
        timeline = self._timeline()
        ref = timeline_ref(timeline)
        self.assertEqual(ref, {"timeline_version": 1,
                               "timeline_checksum": timeline.checksum})
        self.assertEqual(timeline_ref(timeline.to_dict()), ref)

    def test_stamp_and_check_round_trip(self):
        timeline = self._timeline()
        ref = timeline_ref(timeline)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "timeline.json").write_text(
                json.dumps({"shots": []}), encoding="utf-8")
            (root / "subtitles.json").write_text(
                json.dumps([]), encoding="utf-8")
            outcomes = stamp_timeline_refs(
                root, ref, ("timeline.json", "subtitles.json",
                            "missing.json"))
            self.assertEqual(outcomes["timeline.json"], "stamped")
            self.assertEqual(outcomes["subtitles.json"],
                             "skipped_non_dict")
            self.assertEqual(outcomes["missing.json"], "missing")
            stamped = json.loads(
                (root / "timeline.json").read_text(encoding="utf-8"))
            self.assertEqual(stamped["timeline_ref"], ref)
            self.assertEqual(stamped["shots"], [])
            check = check_timeline_refs(
                root, timeline.to_dict(), ("timeline.json",))
            self.assertFalse(check["skipped"])
            self.assertEqual(check["failures"], [])
            self.assertEqual(check["checked"], ["timeline.json"])

    def test_check_fails_on_missing_and_mismatched_refs(self):
        timeline = self._timeline()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "timeline.json").write_text(
                json.dumps({"shots": []}), encoding="utf-8")
            (root / "action_events.json").write_text(json.dumps(
                {"timeline_ref": {"timeline_version": 1,
                                  "timeline_checksum": "0" * 64}}),
                encoding="utf-8")
            check = check_timeline_refs(
                root, timeline.to_dict(),
                ("timeline.json", "action_events.json"))
            self.assertEqual(len(check["failures"]), 2)
            self.assertIn("missing timeline_ref", check["failures"][0])
            self.assertIn("mismatch", check["failures"][1])

    def test_check_skipped_for_pre_checksum_timelines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "timeline.json").write_text(
                json.dumps({"shots": []}), encoding="utf-8")
            check = check_timeline_refs(
                root, {"intervals": []}, ("timeline.json",))
            self.assertTrue(check["skipped"])
            self.assertEqual(check["failures"], [])


if __name__ == "__main__":
    unittest.main()
