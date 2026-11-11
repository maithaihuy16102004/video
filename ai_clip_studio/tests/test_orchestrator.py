"""Tests for the 19-stage orchestrator (ai_clip_studio/orchestrator.py).

Rules enforced here, per Mai's instruction:
- Unit tests may use a mock Drive client and injected test doubles
  (a fallback planner built from real segmentation, a voice provider
  writing REAL wav files, a render_fn writing a REAL mp4 via ffmpeg).
  Those doubles are labelled as such in every test name/docstring.
- The production path (no injections) must FAIL honestly when a real
  dependency is missing — never mock success.
"""

import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.orchestrator import (
    UniversalProductionPipeline, STAGES,
    STATUS_BLOCKED, STATUS_DRAFT_READY,
)
from ai_clip_studio.pipeline import segment_script
from ai_clip_studio import upstream
from test_ai_clip_studio import MockDriveClient, make_silent_wav


def fallback_planner(script: str) -> dict:
    """Deterministic planner from REAL segmentation (test double,
    NOT Gemini — labelled as such wherever it is used)."""
    seg = segment_script(script)
    return {
        "characters": seg.characters,
        "locations": [],
        "scenes": [{"id": f"SCENE_{i+1:02d}", "text": t}
                   for i, t in enumerate(seg.sentences)],
        "shots": [{"id": f"SHOT_{i+1:02d}"} for i in range(len(seg.sentences))],
        "audio_events": [],
    }


def wav_voice_provider(lines, job_dir: Path):
    """Writes REAL silent WAVs (2.0s each) — durations are measured,
    not mocked."""
    wavs = []
    for i, _line in enumerate(lines):
        wav = job_dir / f"voice_{i+1:02d}.wav"
        make_silent_wav(wav, 2.0)
        wavs.append(wav)
    return wavs


def ffmpeg_render_fn(request, package, job_dir: Path):
    """Writes a REAL 1920x1080/24fps mp4 with audio via ffmpeg
    (test double for the Motion Canvas renderer)."""
    out = job_dir / "draft.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=24:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out),
    ], check=True, timeout=120)
    return out


class TestOrchestratorStages(unittest.TestCase):
    def test_19_stages_in_order(self):
        self.assertEqual(len(STAGES), 19)
        self.assertEqual(STAGES[0], "RECEIVE_SCRIPT")
        self.assertEqual(STAGES[3], "GEMINI_STORY_PLANNING")
        self.assertEqual(STAGES[8], "GENERATE_VIETNAMESE_TTS")
        self.assertEqual(STAGES[13], "RENDER_MOTION_CANVAS_THREEJS")
        self.assertEqual(STAGES[18], "RETURN_DRIVE_LINKS")

    def test_production_path_fails_honestly_at_gemini(self):
        """No injections: stages 1-3 pass with the real parser, stage 4
        fails with the exact missing-dependency diagnostic."""
        with tempfile.TemporaryDirectory() as tmp:
            pipe = UniversalProductionPipeline(Path(tmp))
            job = pipe.run("Lan: Chào buổi sáng. Lan mở cửa quán cà phê.")
            self.assertEqual(job.status, STATUS_BLOCKED)
            self.assertEqual(job.stages[0].stage, "RECEIVE_SCRIPT")
            self.assertEqual(job.stages[0].status.value, "passed")
            self.assertEqual(job.stages[2].stage, "PARSE_SCRIPT")
            self.assertEqual(job.stages[2].status.value, "passed")
            self.assertEqual(job.stages[3].stage, "GEMINI_STORY_PLANNING")
            self.assertEqual(job.stages[3].status.value, "failed")
            self.assertIn("GEMINI_API_KEY", job.blocked_reason)
            # Persistent job status exists on disk.
            status = json.loads((job.job_dir / "status.json").read_text())
            self.assertEqual(status["status"], STATUS_BLOCKED)

    def test_full_19_stages_with_test_doubles(self):
        """With labelled test doubles the job runs all 19 stages and
        reaches DRAFT_READY. The render here is a real ffmpeg mp4,
        the voices are real wavs, the Drive client is a mock."""
        with tempfile.TemporaryDirectory() as tmp:
            pipe = UniversalProductionPipeline(
                Path(tmp),
                planner=fallback_planner,
                voice_provider=wav_voice_provider,
                render_fn=ffmpeg_render_fn,
                drive_client=MockDriveClient(),
            )
            job = pipe.run("Lan: Chào buổi sáng. Lan mở cửa và trao lá thư.",
                           available_voices=("Lan", "narrator"))
            self.assertEqual(job.status, STATUS_DRAFT_READY, job.blocked_reason)
            self.assertEqual(len(job.stages), 19)
            self.assertTrue(all(s.status.value == "passed" for s in job.stages))
            draft = job.job_dir / "draft.mp4"
            self.assertTrue(draft.exists())
            self.assertGreater(draft.stat().st_size, 1000)

    def test_render_stage_fails_without_renderer(self):
        """Planner + voice injected, but no render_fn: stage 14 must
        fail with the Chrome-on-Windows diagnostic, not mock success."""
        with tempfile.TemporaryDirectory() as tmp:
            pipe = UniversalProductionPipeline(
                Path(tmp), planner=fallback_planner,
                voice_provider=wav_voice_provider)
            job = pipe.run("Lan: Chào buổi sáng.",
                           available_voices=("Lan", "narrator"))
            self.assertEqual(job.status, STATUS_BLOCKED)
            failed = [s for s in job.stages if s.status.value == "failed"]
            self.assertEqual(len(failed), 1)
            self.assertEqual(failed[0].stage, "RENDER_MOTION_CANVAS_THREEJS")
            self.assertIn("Chrome", failed[0].detail)

    def test_upstream_diagnostics(self):
        diag = upstream.diagnostics()
        self.assertFalse(diag["vieneu_tts"]["ok"])
        self.assertIn("vieneu", diag["vieneu_tts"]["detail"])
        self.assertFalse(diag["motion_canvas_threejs_render"]["ok"])
        self.assertIn("Chrome", diag["motion_canvas_threejs_render"]["detail"])
        self.assertTrue(diag["ffmpeg"]["ok"])
        self.assertTrue(diag["upstream_clone"]["ok"])


if __name__ == "__main__":
    unittest.main()
