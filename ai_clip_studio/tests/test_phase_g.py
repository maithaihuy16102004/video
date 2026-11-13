"""Phase G tests: semantic SFX anchors, footfall recording, and the
foley footstep stage. Sounds land on measured action/contact times,
never on invented ones; unresolved triggers stay reported."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

AGENT = Path(__file__).resolve().parent.parent.parent


def _ep1_package_shots_events():
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
    spans = {}
    clock = 0.0
    for s in shots:
        did = s.get("directive_shot_id")
        if did:
            span = spans.setdefault(str(did), [clock, clock])
            span[1] = clock + float(s["duration"])
        clock += float(s["duration"])
    events, _unsupported = compile_actions(
        package, timeline={"spans": spans})
    return package, shots, events


class TestSemanticAnchors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.shots, cls.events = _ep1_package_shots_events()

    def _resolve(self, compiled_events):
        from ai_clip_studio.audio_events import resolve_v1_cues
        timeline = []
        clock = 0.0
        for s in self.shots:
            if s.get("line_index") is not None:
                timeline.append({"line_index": s["line_index"],
                                 "start": clock,
                                 "end": clock + float(s["duration"])})
            clock += float(s["duration"])
        return resolve_v1_cues(
            self.package.get("v1_audio_cues") or [],
            package=self.package, shots=self.shots,
            timeline_entries=timeline,
            compiled_events=compiled_events)

    def test_wallet_open_anchors_to_the_open_event(self):
        report = self._resolve(self.events)
        seg = next(s for s in report["segments"]
                   if s["cue_id"] == "SFX_001")
        self.assertEqual(seg["anchor_method"], "action_event")
        self.assertEqual(seg["anchor_event_id"], "SC01_SH02_ACT03")
        # OPEN_WALLET's measured start in this clock; the rustle
        # anchors at the event start (fraction 0.0), not the shot
        # start (0.0).
        event = next(e for e in self.events
                     if e["action_id"] == "SC01_SH02_ACT03")
        self.assertEqual(seg["at_seconds"], round(event["start_time"], 3))
        self.assertGreater(seg["at_seconds"], 0.0)

    def test_without_compiled_events_old_behaviour_kept(self):
        report = self._resolve(None)
        seg = next(s for s in report["segments"]
                   if s["cue_id"] == "SFX_001")
        # The plan shots carry directive_shot_id, which _owning_shot
        # does not check, so the pre-existing resolution is the V1
        # shot entry's LINE_ID anchor: line 1 starts at 5.8 s in
        # this clock (after the 5.8 s lead: 3.57 + 2.23 under the
        # phrase-aware cue plan), so the wallet rustle landed ~4 s
        # AFTER the wallet actually opened — the defect the semantic
        # anchor fixes. This test pins the old behaviour, unchanged
        # by Phase G when no compiled events are supplied.
        self.assertEqual(seg["anchor_method"], "owning_shot_line_anchor")
        self.assertIsNone(seg["anchor_event_id"])
        self.assertEqual(seg["at_seconds"], 5.8)

    def test_contact_fractions(self):
        from ai_clip_studio.audio_events import resolve_v1_cues
        events = [
            {"action_id": "SC01_SH02_ACT01", "action_type": "HAND_OVER",
             "start_time": 10.0, "end_time": 11.5},
            {"action_id": "SC01_SH02_ACT02", "action_type": "PICK_UP",
             "start_time": 10.0, "end_time": 11.0},
        ]
        cues = [
            {"cue_id": "T1", "cue_type": "SFX", "name": "Handover",
             "type": "Soft thud", "trigger": "PROP_HANDOVER",
             "scene_number": 1, "shot_id": "SC01_SH02"},
            {"cue_id": "T2", "cue_type": "SFX", "name": "Pickup",
             "type": "Soft thud", "trigger": "PROP_PICK_UP",
             "scene_number": 1, "shot_id": "SC01_SH02"},
        ]
        shots = [{"scene": 1, "duration": 20.0, "v1_shot_id": "SC01_SH02",
                  "line_index": None, "kind": "shot"}]
        report = resolve_v1_cues(
            cues, package={"scenes": [{"number": 1}]}, shots=shots,
            timeline_entries=[], compiled_events=events)
        by_id = {s["cue_id"]: s for s in report["segments"]}
        # HAND_OVER transfers at u=0.60; PICK_UP grasps at u=0.45.
        self.assertEqual(by_id["T1"]["at_seconds"], 10.9)
        self.assertEqual(by_id["T2"]["at_seconds"], 10.45)

    def test_unknown_token_and_other_scene_never_anchor(self):
        from ai_clip_studio.audio_events import resolve_v1_cues
        events = [{"action_id": "SC02_SH01_ACT01",
                   "action_type": "OPEN_WALLET",
                   "start_time": 30.0, "end_time": 31.0}]
        cues = [
            {"cue_id": "L1", "cue_type": "SFX", "name": "Thunder",
             "type": "Soft thud", "trigger": "LIGHTNING_STRIKE",
             "scene_number": 1, "shot_id": "SC01_SH02"},
            {"cue_id": "W1", "cue_type": "SFX", "name": "Wallet",
             "type": "Soft leather rustle",
             "trigger": "PROP_WALLET_OPEN",
             "scene_number": 1, "shot_id": "SC01_SH02"},
        ]
        shots = [{"scene": 1, "duration": 20.0, "v1_shot_id": "SC01_SH02",
                  "line_index": None, "kind": "shot"},
                 {"scene": 2, "duration": 20.0, "v1_shot_id": "SC02_SH01",
                  "line_index": None, "kind": "shot"}]
        report = resolve_v1_cues(
            cues, package={"scenes": [{"number": 1}, {"number": 2}]},
            shots=shots, timeline_entries=[],
            compiled_events=events)
        by_id = {s["cue_id"]: s for s in report["segments"]}
        # LIGHTNING has no action verb; the wallet event lives in
        # another scene. Neither anchors semantically.
        self.assertNotEqual(by_id["L1"]["anchor_method"],
                            "action_event")
        self.assertNotEqual(by_id["W1"]["anchor_method"],
                            "action_event")
        self.assertEqual(by_id["W1"]["at_seconds"], 0.0)


class TestFootfallRecording(unittest.TestCase):
    def test_walking_shot_records_strikes(self):
        import tempfile
        from ai_clip_studio.product_renderer import (
            _render_shot, plan_shots)
        package, shots, _events = _ep1_package_shots_events()
        shot = dict(shots[0])  # close-up lead, walk cue
        shot["index"] = 0
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot({
                "shot": shot, "package": package,
                "out_dir": tmp, "still_only": False})
        falls = result["footfalls"]
        self.assertGreaterEqual(len(falls), 3)
        times = [f["t"] for f in falls]
        self.assertEqual(times, sorted(times))
        self.assertTrue(all(0.0 <= t <= shot["duration"]
                            for t in times))
        feet = [f["foot"] for f in falls]
        self.assertIn("l", feet)
        self.assertIn("r", feet)

    def test_still_records_no_footfalls(self):
        import tempfile
        from ai_clip_studio.product_renderer import _render_shot
        package, shots, _events = _ep1_package_shots_events()
        shot = dict(shots[0])
        shot["index"] = 0
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot({
                "shot": shot, "package": package,
                "out_dir": tmp, "still_only": True})
        self.assertEqual(result["footfalls"], [])


def _silent_mix(path: Path, seconds=10.0):
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"anullsrc=r=48000:cl=mono:duration={seconds}",
         "-ac", "1", "-ar", "48000", str(path)],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:300])


def _loud_mix(path: Path, seconds=10.0):
    # A base mix peaking at the -1 dBFS bound: without headroom,
    # ANY added stem exceeds it and the old code omitted every
    # footstep (the Zeus draft's omitted_peak).
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"aevalsrc='sin(2*PI*440*t)':duration={seconds}",
         "-af", "volume=-1dB", "-ac", "1", "-ar", "48000",
         str(path)],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:300])


class TestFoleySync(unittest.TestCase):
    def _job(self):
        tmp = tempfile.TemporaryDirectory()
        job_dir = Path(tmp.name)
        (job_dir / "audio").mkdir()
        mix = job_dir / "audio" / "mix.wav"
        _silent_mix(mix)
        return tmp, job_dir, mix

    def test_loud_mix_keeps_footsteps_via_headroom(self):
        from ai_clip_studio.audio_events import resolve_mix_gains
        from ai_clip_studio.product_flow import (
            FOLEY_MIX_MAX_PEAK_DB, _wav_levels, sync_foley_footsteps)
        tmp = tempfile.TemporaryDirectory()
        job_dir = Path(tmp.name)
        (job_dir / "audio").mkdir()
        mix = job_dir / "audio" / "mix.wav"
        _loud_mix(mix)
        try:
            shots = [{"scene": 1, "duration": 10.0,
                      "locomotion_direction": 1}]
            reports = [{"index": 0, "footfalls": [
                {"t": 0.2 + 0.4 * i, "foot": "l" if i % 2 == 0 else "r",
                 "x": 100.0, "character": "A"} for i in range(5)]}]
            before = mix.read_bytes()
            report = sync_foley_footsteps(
                job_dir, reports, shots, mix, 10.0, [],
                resolve_mix_gains({}))
            self.assertEqual(report["status"], "placed")
            self.assertTrue(report["mix_changed"])
            self.assertIn("headroom_applied_db", report)
            self.assertGreater(report["headroom_applied_db"], 0.0)
            self.assertLessEqual(report["headroom_applied_db"], 3.0)
            self.assertLessEqual(report["combined_peak_db"],
                                 FOLEY_MIX_MAX_PEAK_DB)
            # The original pre-foley mix is preserved byte-identical.
            self.assertEqual(
                (job_dir / "audio" / "mix_pre_foley.wav"
                 ).read_bytes(), before)
            levels = _wav_levels(mix, [(0.2, 0.42)])
            self.assertGreater(levels["window_rms_db"][0], -60.0)
        finally:
            tmp.cleanup()

    def test_footsteps_placed_and_audible(self):
        from ai_clip_studio.audio_events import resolve_mix_gains
        from ai_clip_studio.product_flow import (
            _wav_levels, sync_foley_footsteps)
        tmp, job_dir, mix = self._job()
        try:
            shots = [
                {"scene": 1, "duration": 5.0,
                 "locomotion_direction": 1},
                {"scene": 1, "duration": 5.0,
                 "locomotion_direction": None},
            ]
            reports = [
                {"index": 0, "footfalls": [
                    {"t": 0.2 + 0.4 * i, "foot": "l" if i % 2 == 0
                     else "r", "x": 100.0, "character": "A"}
                    for i in range(5)]},
                {"index": 1, "footfalls": [
                    {"t": 0.1, "foot": "l", "x": 100.0,
                     "character": "A"}]},
            ]
            before = mix.read_bytes()
            report = sync_foley_footsteps(
                job_dir, reports, shots, mix, 10.0,
                [{"start": 6.0, "end": 8.0}],
                resolve_mix_gains({}))
            self.assertEqual(report["status"], "placed")
            self.assertEqual(report["placements"], 5)
            self.assertTrue(report["mix_changed"])
            self.assertTrue((job_dir / "audio"
                             / "mix_pre_foley.wav").exists())
            self.assertEqual(
                (job_dir / "audio" / "mix_pre_foley.wav"
                 ).read_bytes(), before)
            self.assertNotEqual(mix.read_bytes(), before)
            levels = _wav_levels(mix, [(0.2, 0.42)])
            self.assertIsNotNone(levels["window_rms_db"][0])
            self.assertGreater(levels["window_rms_db"][0], -60.0)
            stored = json.loads(
                (job_dir / "foley_sync.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(stored["status"], "placed")
        finally:
            tmp.cleanup()

    def test_no_footfalls_leaves_mix_untouched(self):
        from ai_clip_studio.audio_events import resolve_mix_gains
        from ai_clip_studio.product_flow import sync_foley_footsteps
        tmp, job_dir, mix = self._job()
        try:
            shots = [{"scene": 1, "duration": 10.0,
                      "locomotion_direction": None}]
            reports = [{"index": 0, "footfalls": []}]
            before = mix.read_bytes()
            report = sync_foley_footsteps(
                job_dir, reports, shots, mix, 10.0, [],
                resolve_mix_gains({}))
            self.assertEqual(report["status"], "no_footfalls")
            self.assertEqual(mix.read_bytes(), before)
            self.assertFalse((job_dir / "audio"
                              / "mix_pre_foley.wav").exists())
        finally:
            tmp.cleanup()

    def test_locomotion_without_strikes_is_unresolved(self):
        from ai_clip_studio.audio_events import resolve_mix_gains
        from ai_clip_studio.product_flow import (
            footstep_placements)
        shots = [{"scene": 1, "duration": 5.0,
                  "locomotion_direction": 1}]
        reports = [{"index": 0, "footfalls": [
            {"t": 0.1, "foot": "l", "x": 1.0, "character": "A"},
            {"t": 0.1, "foot": "r", "x": 2.0, "character": "A"}]}]
        placements, _per_shot, unresolved = footstep_placements(
            reports, shots)
        self.assertEqual(placements, [])
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["shot_index"], 0)


class TestLineStartAssignment(unittest.TestCase):
    """Regression test for the Phase B narration-misplacement bug:
    the old loop overwrote each entry's start on EVERY segment, so
    segmented narration started at its LAST segment (measured
    +6.52 s on L1, +7.98 s on L9 by cross-correlation; the final
    line's end ran past the stem and truncated). First segment
    wins; a line with no shot raises loudly."""

    def test_real_ep1_job_clock(self):
        from ai_clip_studio.product_flow import _assign_line_starts
        job = json.loads(
            (AGENT / "jobs" / "req_b741afd59822"
             / "timeline.json").read_text(encoding="utf-8"))
        entries = [{"line_index": l["line_index"],
                    "duration": l["duration"]} for l in job["lines"]]
        _assign_line_starts(job["shots"], entries)
        by_index = {e["line_index"]: e for e in entries}
        # Segmented narration starts at its FIRST segment.
        self.assertEqual(by_index[1]["start"], 7.0)
        self.assertEqual(by_index[1]["end"], 16.792)
        self.assertEqual(by_index[9]["start"], 69.09)
        self.assertEqual(by_index[9]["end"], 79.722)
        # Single-segment dialogue unchanged.
        self.assertEqual(by_index[4]["start"], 43.71)
        self.assertEqual(by_index[4]["end"], 45.63)
        # Every line ends within the shot clock (no truncation).
        total = sum(s["duration"] for s in job["shots"])
        for e in entries:
            self.assertLessEqual(e["end"], total)

    def test_line_with_no_shot_raises(self):
        from ai_clip_studio.product_flow import _assign_line_starts
        entries = [{"line_index": 1, "duration": 1.0},
                   {"line_index": 2, "duration": 1.0}]
        shots = [{"kind": "narration", "line_index": 1,
                  "duration": 1.0}]
        with self.assertRaises(RuntimeError):
            _assign_line_starts(shots, entries)


if __name__ == "__main__":
    unittest.main()
