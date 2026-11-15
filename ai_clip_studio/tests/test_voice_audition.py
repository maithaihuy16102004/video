"""Voice audition packs (round-2 system 8): one listenable sample
per speaking voice, built from the job's own normalised WAVs. No
score is computed anywhere; the pack exists so Mai can listen."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.voice_audition import (
    AuditionError, build_audition_from_job)

AGENT = Path(__file__).parent.parent.parent
ZEUS_JOB = AGENT / "jobs" / "req_4d4db02aaef5"


def _sine_wav(path: Path, seconds=1.0):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"sine=frequency=440:duration={seconds}",
         "-ac", "1", "-ar", "48000", str(path)],
        check=True, timeout=60)


def _fake_job(root: Path, *, reuse=False):
    voices = root / "voices"
    voices.mkdir(parents=True)
    lines = [
        {"line_index": 1, "speaker": "An", "kind": "narration",
         "text": "Tôi là An, người kể chuyện này.",
         "wav": str(voices / "line01_An.wav"), "duration": 1.0},
        {"line_index": 2, "speaker": "Bình", "kind": "dialogue",
         "text": "Chào An, tôi là Bình.",
         "wav": str(voices / "line02_Bình.wav"), "duration": 1.0},
        {"line_index": 3, "speaker": "An", "kind": "narration",
         "text": "Dòng thứ hai của An, không được chọn.",
         "wav": str(voices / "line03_An.wav"), "duration": 1.0},
    ]
    for line in lines:
        _sine_wav(Path(line["wav"]))
    assignment = {
        "An": {"voice": "avocado_v2:ronan",
               "script_voice_id": "VOICE_AN",
               "voice_hint": "giọng nam", "gender": "male"},
        "Bình": {"voice": "avocado_v2:ronan" if reuse
                 else "avocado_v2:MAI_03",
                 "script_voice_id": "VOICE_BINH",
                 "voice_hint": "giọng nam", "gender": "male"},
    }
    manifest = {
        "engine": "test engine",
        "engine_note": "test note",
        "assignment": assignment,
        "reuse_warnings": (["voice reuse: Bình shares ronan"]
                           if reuse else []),
        "distinct_voices_used": 1 if reuse else 2,
        "speakers": ["An", "Bình"],
        "lines": [],
    }
    (root / "voices_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (root / "timeline.json").write_text(
        json.dumps({"lines": lines}, ensure_ascii=False),
        encoding="utf-8")
    return manifest


class TestVoiceAudition(unittest.TestCase):
    def test_one_sample_per_speaker_first_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            job.mkdir()
            _fake_job(job)
            out = Path(tmp) / "pack"
            record = build_audition_from_job(job, out,
                                             project_id="TEST")
            self.assertEqual([s["speaker"] for s in record["samples"]],
                             ["An", "Bình"])
            self.assertEqual(record["samples"][0]["line_index"], 1)
            self.assertEqual(record["samples"][1]["line_index"], 2)
            self.assertEqual(record["samples"][0]["text"],
                             "Tôi là An, người kể chuyện này.")
            mp3s = sorted(out.glob("*.mp3"))
            self.assertEqual(len(mp3s), 2)
            for mp3 in mp3s:
                self.assertGreater(mp3.stat().st_size, 1000)

    def test_sheet_states_facts_and_no_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            job.mkdir()
            _fake_job(job, reuse=True)
            out = Path(tmp) / "pack"
            build_audition_from_job(job, out, project_id="TEST")
            sheet = (out / "AUDITION.md").read_text(encoding="utf-8")
            for needle in ("VOICE_AN", "VOICE_BINH",
                           "avocado_v2:ronan",
                           "Tôi là An, người kể chuyện này.",
                           "voice reuse: Bình shares ronan",
                           "Không có điểm số"):
                self.assertIn(needle, sheet)
            self.assertNotIn("score:", sheet.lower())

    def test_missing_manifest_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            job.mkdir()
            (job / "timeline.json").write_text('{"lines": []}',
                                               encoding="utf-8")
            with self.assertRaises(AuditionError):
                build_audition_from_job(job, Path(tmp) / "pack")

    def test_missing_wav_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            job.mkdir()
            _fake_job(job)
            (job / "voices" / "line01_An.wav").unlink()
            with self.assertRaises(AuditionError):
                build_audition_from_job(job, Path(tmp) / "pack")

    @unittest.skipUnless(ZEUS_JOB.exists(),
                         "Zeus draft job not present on this machine")
    def test_real_zeus_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pack"
            record = build_audition_from_job(
                ZEUS_JOB, out, project_id="ZEUS_EP01_FALL_OF_CRONUS")
            self.assertEqual([s["speaker"] for s in record["samples"]],
                             ["Zeus", "Cronus", "Rhea", "Metis"])
            self.assertEqual(record["distinct_voices_used"], 4)
            self.assertEqual(record["reuse_warnings"], [])
            zeus = record["samples"][0]
            self.assertEqual(zeus["line_index"], 1)
            self.assertEqual(zeus["script_voice_id"], "Đức Trí")
            self.assertEqual(zeus["voice"], "avocado_v2:ronan")
            self.assertAlmostEqual(zeus["duration_sec"], 5.232,
                                   delta=0.15)


if __name__ == "__main__":
    unittest.main()
