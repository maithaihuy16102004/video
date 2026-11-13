"""Final MP4 verification (directive section 19): the verifier
measures the RENDERED file, never the plan. Fixtures are synthetic
chirps + a real ffmpeg/AAC mux, so the codec path is exercised."""

import json
import math
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from ai_clip_studio.mp4_verifier import verify_mp4

SR = 48000


def _write_wav(path: Path, samples: np.ndarray) -> Path:
    pcm = np.clip(samples, -1.0, 1.0)
    pcm16 = (pcm * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm16.tobytes())
    return path


def _chirp(f0: float, f1: float, duration: float) -> np.ndarray:
    t = np.arange(int(duration * SR)) / SR
    phase = 2 * np.pi * (f0 * t + (f1 - f0) * t ** 2 / (2 * duration))
    signal = 0.6 * np.sin(phase)
    edge = int(0.01 * SR)
    ramp = np.ones_like(signal)
    ramp[:edge] = np.linspace(0.0, 1.0, edge)
    ramp[-edge:] = np.linspace(1.0, 0.0, edge)
    return signal * ramp


def _burst(duration: float = 0.3) -> np.ndarray:
    t = np.arange(int(duration * SR)) / SR
    return 0.8 * np.sin(2 * np.pi * 1200 * t) * np.exp(-t * 12.0)


def _place_mix(job: Path, placements: list[tuple[Path, float]],
               total: float, name: str = "mix.wav") -> Path:
    """Place wavs at offsets, pad to total. Returns the mix path."""
    out = job / name
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for i, (wav, at) in enumerate(placements):
        inputs += ["-i", str(wav)]
        delay_ms = int(round(at * 1000))
        filters.append(f"[{i}:a]adelay={delay_ms}:all=1[v{i}]")
        labels.append(f"[v{i}]")
    filters.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0"
        f":duration=longest[mix]")
    filters.append(f"[mix]apad=whole_dur={total:.2f}[out]")
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error"] + inputs + [
            "-filter_complex", ";".join(filters), "-map", "[out]",
            "-ac", "1", "-ar", str(SR), str(out)],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return out


def _mux_mp4(job: Path, mix: Path, total: float, *,
             audio_total: float | None = None) -> Path:
    out = job / "draft.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "lavfi", "-i",
           f"color=c=0x14222B:s=320x180:r=24:d={total:.2f}",
           "-i", str(mix), "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k"]
    if audio_total is not None:
        cmd += ["-t", f"{audio_total:.2f}"]
    cmd.append(str(out))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return out


def _lines(job: Path, starts=(2.0, 5.0, 8.0)):
    specs = [(300.0, 900.0), (500.0, 1400.0), (800.0, 2000.0)]
    lines = []
    for i, ((f0, f1), start) in enumerate(zip(specs, starts)):
        wav = _write_wav(job / f"line{i + 1}.wav", _chirp(f0, f1, 1.5))
        lines.append({"line_index": i + 1, "wav": str(wav),
                      "start": start, "end": start + 1.5})
    return lines


def _subtitles(lines):
    subs = []
    for line in lines:
        mid = (line["start"] + line["end"]) / 2
        subs.append({"line_index": line["line_index"], "phrases": [
            "first half", "second half"],
            "windows": [
                {"phrase": "first half", "start": line["start"],
                 "end": mid},
                {"phrase": "second half", "start": mid,
                 "end": line["end"]}],
            "font_px": 64})
    return subs


def _unified(lines):
    intervals = []
    for line in lines:
        intervals.append({
            "track": "narration" if line["line_index"] % 2 else "dialogue",
            "interval_id": f"line:{line['line_index']}",
            "start_sec": line["start"], "end_sec": line["end"],
            "payload": {}})
    intervals.append({
        "track": "actions", "interval_id": "action:SC01_SH01_ACT01",
        "start_sec": 4.0, "end_sec": 5.0,
        "payload": {"verb": "PICK_UP"}})
    return {"total_sec": 12.0, "total_frames": 288,
            "intervals": intervals}


class TestMp4Verifier(unittest.TestCase):
    def _build(self, tmp: Path, *, line_starts=(2.0, 5.0, 8.0),
               truncate_last: bool = False, duplicate_first: bool = False,
               sfx_at: float | None = 4.45, segment_at: float = 4.45,
               audio_total: float | None = None):
        lines = _lines(tmp, starts=line_starts)
        placements = [(Path(line["wav"]), line["start"])
                      for line in lines]
        if truncate_last:
            # Rebuild line 3 from its first 0.8 s only.
            with wave.open(str(lines[2]["wav"]), "rb") as handle:
                frames = handle.readframes(int(0.8 * SR))
            cut = tmp / "line3_cut.wav"
            with wave.open(str(cut), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(SR)
                handle.writeframes(frames)
            placements[2] = (cut, lines[2]["start"])
        if duplicate_first:
            placements.append((Path(lines[0]["wav"]), 10.0))
        mix = _place_mix(tmp, placements, 12.0)
        burst = _write_wav(tmp / "burst.wav", _burst())
        foley = None
        segments = []
        if sfx_at is not None:
            foley = _place_mix(tmp, [(burst, sfx_at)], 12.0, "foley.wav")
            segments = [{"at_seconds": segment_at,
                         "end_seconds": segment_at + 0.3,
                         "synth_kind": "knock", "cue_id": "SFX_T1",
                         "anchor_event_id": "SC01_SH01_ACT01"}]
        mp4 = _mux_mp4(tmp, mix, 12.0, audio_total=audio_total)
        return lines, mix, foley, segments, mp4

    def test_clean_mp4_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            lines, mix, foley, segments, mp4 = self._build(tmp)
            report = verify_mp4(
                mp4, lines=lines, subtitles=_subtitles(lines),
                segments=segments, unified=_unified(lines),
                mix_wav=mix, foley_wav=foley)
            self.assertTrue(report["passed"], report["failures"])
            for rec in report["lines"]:
                self.assertLess(abs(rec["onset_error_sec"]), 0.02,
                                rec)
                self.assertGreater(rec["coefficient"], 0.5)
                self.assertTrue(rec["tail_present"])
                self.assertLess(rec["second_peak_ratio"], 0.6)
            # Codec delay is measured and small (decoder absorbs
            # AAC priming via container metadata).
            self.assertIsNotNone(report["codec_delay_estimate_sec"])
            self.assertLess(abs(report["codec_delay_estimate_sec"]),
                            0.05)
            self.assertEqual(len(report["sfx"]), 1)
            self.assertTrue(report["sfx"][0]["present"])
            self.assertEqual(len(report["anchor_checks"]), 1)
            self.assertLess(
                abs(report["anchor_checks"][0]["schedule_error_sec"]),
                0.05)
            self.assertLess(report["av_diff_sec"], 0.15)

    def test_shifted_line_fails_with_mix_blamed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Line 2's PLANNED start is 5.0; render it at 5.5.
            lines, mix, foley, segments, mp4 = self._build(
                tmp, line_starts=(2.0, 5.5, 8.0))
            planned = [dict(line) for line in lines]
            planned[1]["start"] = 5.0
            planned[1]["end"] = 6.5
            report = verify_mp4(
                mp4, lines=planned, subtitles=_subtitles(planned),
                segments=segments, unified=_unified(planned),
                mix_wav=mix, foley_wav=foley)
            self.assertFalse(report["passed"])
            line2 = report["lines"][1]
            self.assertAlmostEqual(line2["onset_error_sec"], 0.5,
                                   delta=0.03)
            # The error is in the mix, not the codec: both
            # measurements agree, so the delay estimate stays ~0.
            self.assertLess(abs(report["codec_delay_estimate_sec"]),
                            0.05)
            self.assertTrue(any("line 2" in f
                                for f in report["failures"]))

    def test_truncated_line_fails_tail_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            lines, mix, foley, segments, mp4 = self._build(
                tmp, truncate_last=True)
            report = verify_mp4(
                mp4, lines=lines, subtitles=_subtitles(lines),
                segments=segments, unified=_unified(lines),
                mix_wav=mix, foley_wav=foley)
            self.assertFalse(report["passed"])
            self.assertFalse(report["lines"][2]["tail_present"])
            self.assertTrue(any("tail" in f
                                for f in report["failures"]))

    def test_duplicated_line_fails_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            lines, mix, foley, segments, mp4 = self._build(
                tmp, duplicate_first=True)
            report = verify_mp4(
                mp4, lines=lines, subtitles=_subtitles(lines),
                segments=segments, unified=_unified(lines),
                mix_wav=mix, foley_wav=foley)
            self.assertFalse(report["passed"])
            self.assertGreater(
                report["lines"][0]["second_peak_ratio"], 0.6)
            self.assertTrue(any("duplicate" in f
                                for f in report["failures"]))

    def test_missing_sfx_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            lines, mix, _foley, segments, mp4 = self._build(tmp)
            # Foley stem with no burst: silence only.
            empty = tmp / "empty_foley.wav"
            _write_wav(empty, np.zeros(int(12.0 * SR)))
            report = verify_mp4(
                mp4, lines=lines, subtitles=_subtitles(lines),
                segments=segments, unified=_unified(lines),
                mix_wav=mix, foley_wav=empty)
            self.assertFalse(report["passed"])
            self.assertFalse(report["sfx"][0]["present"])
            self.assertTrue(any("SFX_T1" in f
                                for f in report["failures"]))

    def test_anchor_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Burst renders at the contact moment (4.45) but the
            # segment claims 4.9: the schedule is wrong.
            lines, mix, foley, segments, mp4 = self._build(
                tmp, sfx_at=4.45, segment_at=4.9)
            report = verify_mp4(
                mp4, lines=lines, subtitles=_subtitles(lines),
                segments=segments, unified=_unified(lines),
                mix_wav=mix, foley_wav=foley)
            self.assertFalse(report["passed"])
            self.assertTrue(any("contact moment" in f
                                for f in report["failures"]))


    def test_tight_gap_tail_control_stays_out_of_previous_line(self):
        # Zeus re-render line 14: a 0.31 s inter-line gap put the
        # 1 s-back discrimination control inside the previous
        # line's speech (same voice), reading 0.26 and failing a
        # present tail (0.89) on the 4x ratio alone. Here line 2's
        # tail duplicates line 1's tail, the gap is 0.5 s, and the
        # 1 s-back control window lands exactly on line 1's tail:
        # the old code fails the tail; the guarded control steps
        # back to silence and the absolute rule passes it.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tail = _chirp(300.0, 900.0, 0.5)
            line1 = np.concatenate([_chirp(300.0, 900.0, 1.0), tail])
            head2 = _chirp(500.0, 1400.0, 1.0)
            line2 = np.concatenate([head2, tail])
            specs = [(line1, 2.0), (line2, 4.0),
                     (_chirp(800.0, 2000.0, 1.5), 8.0)]
            lines = []
            placements = []
            for i, (sig, start) in enumerate(specs):
                wav = _write_wav(tmp / f"line{i + 1}.wav", sig)
                lines.append({"line_index": i + 1, "wav": str(wav),
                              "start": start,
                              "end": start + len(sig) / SR})
                placements.append((wav, start))
            mix = _place_mix(tmp, placements, 12.0)
            mp4 = _mux_mp4(tmp, mix, 12.0)
            report = verify_mp4(mp4, lines=lines,
                                subtitles=_subtitles(lines),
                                unified=_unified(lines),
                                mix_wav=mix)
        self.assertTrue(report["passed"], report["failures"])
        rec2 = [r for r in report["lines"]
                if r["line_index"] == 2][0]
        self.assertTrue(rec2["tail_present"], rec2)

    def test_multi_strike_anchor_pairs_each_onset_with_its_segment(self):
        # SFX_009 on the Zeus re-render: two hammer strikes under
        # one cue id. The anchor check took the LAST onset record
        # for every segment, comparing strike 2 against strike 1's
        # contact moment (+0.91 s false failure).
        from ai_clip_studio.animation.primitives import (
            hammer_cycles, hammer_strike_times)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            lines = _lines(tmp)
            mix = _place_mix(
                tmp, [(Path(line["wav"]), line["start"])
                      for line in lines], 12.0)
            start, end = 4.0, 5.8
            moments = [start + t for t in hammer_strike_times(
                end - start, hammer_cycles(end - start))]
            self.assertEqual(len(moments), 2)
            burst = _write_wav(tmp / "burst.wav", _burst())
            foley = _place_mix(
                tmp, [(burst, m) for m in moments], 12.0, "foley.wav")
            segments = [{"at_seconds": m, "end_seconds": m + 0.3,
                         "synth_kind": "metal_strike", "cue_id": "SFX_H1",
                         "anchor_event_id": "SC01_SH01_ACT01"}
                        for m in moments]
            unified = _unified(lines)
            unified["intervals"] = [
                i for i in unified["intervals"]
                if i["track"] != "actions"] + [{
                    "track": "actions",
                    "interval_id": "action:SC01_SH01_ACT01",
                    "start_sec": start, "end_sec": end,
                    "payload": {"verb": "HAMMER_STRIKE"}}]
            mp4 = _mux_mp4(tmp, mix, 12.0)
            report = verify_mp4(mp4, lines=lines,
                                subtitles=_subtitles(lines),
                                segments=segments, unified=unified,
                                mix_wav=mix, foley_wav=foley)
        self.assertTrue(report["passed"], report["failures"])
        checks = report["anchor_checks"]
        self.assertEqual(len(checks), 2)
        for check, moment in zip(checks, moments):
            self.assertAlmostEqual(check["planned_sec"], moment, places=2)
            self.assertLessEqual(
                abs(check["onset_vs_contact_sec"]), 0.1, check)


class TestVerificationGate(unittest.TestCase):
    """The pipeline gates the Drive upload on the verification
    result, exactly like Technical QA. The render is mocked to
    cheap solid frames (the real mux runs); the verifier and the
    TechnicalGate are mocked to isolate the gate logic. The real
    verifier + real pipeline integration is proven by the Zeus/Ep1
    renders, where both run unmocked."""

    def _run_job(self, tmp: Path, *, verifier_passed: bool):
        from unittest import mock
        from PIL import Image

        from ai_clip_studio import product_flow
        from ai_clip_studio.qa_gates import (
            CheckResult, TechnicalGateResult)
        from ai_clip_studio.tests.test_unauthorized_story_change import (
            _stub_tts)

        script = (Path(__file__).resolve().parent.parent.parent
                  / "examples"
                  / "hitler_ep01_munich_1914.studio.md").read_text(
                      encoding="utf-8")

        def _fake_render(package, timeline, job_dir, **_kw):
            frames_dir = Path(job_dir) / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            # Mirror production: the frozen plan (shots=) wins over
            # the timeline lines when the caller passes it.
            plan = _kw.get("shots") or timeline
            total = sum(s["duration"] for s in plan) + 0.5
            n_frames = int(round(total * 24))
            frame = frames_dir / "frame_000001.png"
            Image.new("RGB", (1920, 1080), (20, 34, 43)).save(frame)
            (frames_dir / "motion_report.json").write_text("{}")
            return {"n_frames": n_frames, "duration_sec": total,
                    "violations": [], "camera_accounting": {},
                    "shots": [], "frames": [str(frame)],
                    "frames_dir": str(frames_dir)}

        passing = TechnicalGateResult(
            status="TECHNICAL_PASS", checks={})
        verification = {"passed": verifier_passed,
                        "failures": [] if verifier_passed
                        else ["line 1: onset error +3.125s"],
                        "summary": "mocked"}
        with mock.patch.object(product_flow, "tts_cli_provider",
                               side_effect=_stub_tts), \
            mock.patch.object(product_flow, "render_product_video",
                              side_effect=_fake_render), \
            mock.patch.object(product_flow, "render_storyboard_stills",
                              return_value=[]), \
            mock.patch.object(
                product_flow, "sync_foley_footsteps",
                return_value={"status": "skipped", "placements": 0,
                              "unresolved": [], "mix_changed": False}), \
            mock.patch("ai_clip_studio.mp4_verifier.verify_job_mp4",
                       return_value=verification), \
            mock.patch(
                "ai_clip_studio.qa_gates.TechnicalGate.run",
                return_value=passing), \
            mock.patch.object(
                product_flow, "GwsCliDriveClient") as drive_cls:
            client = drive_cls.return_value
            uploaded: dict[str, Path] = {}

            def _upload(path, _folder):
                uploaded["last"] = Path(path)
                return {"id": "mock_drive_id"}

            client.upload_file.side_effect = _upload
            client.get_file.side_effect = lambda _fid: {
                "size": str(uploaded["last"].stat().st_size)}
            job = product_flow.run_product_job(
                script, tmp, upload=True)
        return job

    def test_failed_verification_blocks_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self._run_job(Path(tmp), verifier_passed=False)
            self.assertEqual(job.status, "QA_FAILED")
            stages = {s["stage"]: s["status"] for s in job.stages}
            self.assertEqual(stages["mp4_verification"], "failed")
            self.assertEqual(stages["drive_upload"], "skipped")
            self.assertIn("mp4_verification",
                          job.loops[0]["failed"])
            self.assertTrue(
                (Path(tmp) / "mp4_verification.json").exists())

    def test_passed_verification_allows_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self._run_job(Path(tmp), verifier_passed=True)
            stages = {s["stage"]: s["status"] for s in job.stages}
            self.assertEqual(stages["mp4_verification"], "done")
            self.assertEqual(stages["drive_upload"], "done")


if __name__ == "__main__":
    unittest.main()
