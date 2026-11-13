"""Distinct job failure on UnauthorizedStoryChange (A2 wiring item 6).

An unresolved mandatory semantic conflict is a story dispute, not a
degraded mode: the job must FAIL distinctly (status FAILED, the
exception type + conflict detail in the record, action_compile failed)
instead of falling back to legacy cues and staging the wrong story.
Since the integration sprint (section 6, 2026-11-13) ordinary
compiler failures fail the job the same way -- the old
recorded-fallback behaviour was removed because falling back to
legacy cues stages a story the compiler could not validate.
"""

import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from ai_clip_studio.action_compiler import UnauthorizedStoryChange
from ai_clip_studio import product_flow

AGENT = Path(__file__).resolve().parent.parent.parent
EP1 = (AGENT / "examples" / "hitler_ep01_munich_1914.studio.md").read_text(
    encoding="utf-8")


def _stub_tts(flat_lines, job_dir, voice_hints=None, voice_ids=None):
    """1s sine WAVs + the manifest stage 6 reads. No real synthesis:
    these tests exercise stage 7a, not TTS."""
    job_dir = Path(job_dir)
    wavs = []
    for i, _line in enumerate(flat_lines):
        path = job_dir / f"line_{i + 1:02d}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            frames = b"".join(
                struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * n / 48000)))
                for n in range(48000))
            wav.writeframes(frames)
        wavs.append(path)
    (job_dir / "voices_manifest.json").write_text(json.dumps({
        "distinct_voices_used": 1,
        "speakers": sorted({line["speaker"] for line in flat_lines}),
    }), encoding="utf-8")
    return wavs


class TestUnauthorizedStoryChangeFailsJob(unittest.TestCase):
    def _run(self, compile_side_effect, emit_side_effect=None):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            patches = [
                mock.patch.object(product_flow, "tts_cli_provider",
                                  side_effect=_stub_tts),
                mock.patch.object(product_flow, "compile_actions",
                                  side_effect=compile_side_effect),
            ]
            if emit_side_effect is not None:
                patches.append(mock.patch.object(
                    product_flow, "emit_job_spec",
                    side_effect=emit_side_effect))
            for p in patches:
                p.start()
            try:
                job = product_flow.run_product_job(
                    EP1, job_dir, upload=False)
            finally:
                for p in patches:
                    p.stop()
            # Read job-dir artifacts BEFORE the temp dir is removed.
            events_path = job_dir / "action_events.json"
            events = json.loads(events_path.read_text(
                encoding="utf-8")) if events_path.exists() else None
            err_path = job_dir / "production_error.json"
            prod_err = json.loads(err_path.read_text(
                encoding="utf-8")) if err_path.exists() else None
            return job, events, (job_dir / "draft.mp4").exists(), prod_err

    def test_conflict_fails_job_distinctly_at_early_pass(self):
        # The conflict now surfaces at the EARLY semantic pass (2b),
        # before TTS: the job fails fast with the conflict named.
        detail = ("unresolved mandatory semantic conflict(s): "
                  "[cue vs event] wallet: bend_pick vs take_out")
        job, events, draft_exists, _prod_err = self._run(
            UnauthorizedStoryChange(detail))
        self.assertEqual(job.status, "FAILED")
        self.assertTrue(job.errors)
        self.assertIn("UnauthorizedStoryChange", job.errors[0])
        self.assertIn("bend_pick vs take_out", job.errors[0])
        stages = {s["stage"]: s for s in job.stages}
        self.assertEqual(stages["semantic_conflicts"]["status"],
                         "failed")
        self.assertIn("UnauthorizedStoryChange",
                      stages["semantic_conflicts"]["detail"])
        self.assertIn("UnauthorizedStoryChange",
                      stages["failed"]["detail"])
        self.assertNotIn("vietnamese_tts", stages)
        self.assertIsNone(events)
        self.assertFalse(draft_exists)

    def test_conflict_at_7a_fails_job_distinctly(self):
        # Early pass clean, 7a raises: the distinct failure still
        # applies at the real-span compile, with 7a's record.
        detail = ("unresolved mandatory semantic conflict(s): "
                  "[cue vs event] wallet: bend_pick vs take_out")
        job, events, draft_exists, _prod_err = self._run(
            [([], []), UnauthorizedStoryChange(detail)])
        self.assertEqual(job.status, "FAILED")
        self.assertIn("UnauthorizedStoryChange", job.errors[0])
        stages = {s["stage"]: s for s in job.stages}
        self.assertIn("vietnamese_tts", stages)
        self.assertEqual(stages["action_compile"]["status"], "failed")
        self.assertIn("UnauthorizedStoryChange",
                      stages["action_compile"]["detail"])
        self.assertIsNotNone(events)
        self.assertIn("UnauthorizedStoryChange",
                      events["compile_error"])
        self.assertEqual(events["events"], [])
        self.assertFalse(draft_exists)

    def test_ordinary_compiler_failure_fails_job_fast(self):
        # Sprint section 6 (2026-11-13): the old recorded-fallback
        # behaviour is REMOVED -- this test replaces
        # test_ordinary_compiler_failure_still_falls_back, which
        # pinned the swallow. An ordinary compiler failure fails
        # the job at the early semantic pass, before TTS, with a
        # structured production_error.json record; the RENDER_MARKER
        # stage is never reached.
        job, events, _draft_exists, prod_err = self._run(
            RuntimeError("boom"))
        self.assertEqual(job.status, "FAILED")
        self.assertIn("RuntimeError: boom", job.errors[0])
        stages = {s["stage"]: s for s in job.stages}
        self.assertEqual(stages["semantic_conflicts"]["status"],
                         "failed")
        self.assertNotIn("vietnamese_tts", stages)
        self.assertIsNone(events)
        self.assertIsNotNone(prod_err)
        self.assertEqual(prod_err["stage"], "semantic_conflicts")
        self.assertEqual(prod_err["error_code"], "STAGE_EXCEPTION")
        self.assertEqual(prod_err["cause_type"], "RuntimeError")
        self.assertIn("boom", prod_err["diagnostic_message"])


if __name__ == "__main__":
    unittest.main()
