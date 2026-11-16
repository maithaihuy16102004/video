"""Round 20 (voice pinning): the TTS cache pins voice durations.

The TTS CLI is nondeterministic, so identical lines re-synthesised
on every render re-flow the audio-driven timeline (Loop 01 R19:
17 -> 15 shots). The cache stores the normalised WAV per content
key and reuses it byte-identically.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio import tts_cli_provider as tcp

FAKE_TTS = (
    "import subprocess, sys\n"
    "data = sys.stdin.buffer.read()\n"
    "args = sys.argv[1:]\n"
    "out = args[args.index('--output') + 1]\n"
    "counter = args[args.index('--counter') + 1] if '--counter' in args else None\n"
    "subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi',\n"
    "                '-i', 'sine=frequency=440:duration=0.6',\n"
    "                '-q:a', '4', out], check=True)\n")

LINES = [{"text": "Tôi là Linh.", "speaker": "Linh"}]


def _install_fake(job_dir: Path):
    fake = job_dir / "fake_tts.py"
    fake.write_text(FAKE_TTS, encoding="utf-8")
    wrapper = job_dir / "fake_tts"
    wrapper.write_text(
        f"#!/bin/sh\nexec python3 {fake} \"$@\"\n", encoding="utf-8")
    wrapper.chmod(0o755)
    return str(wrapper)


class TestCacheKey(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(tcp.cache_key(voice="v", text="xin chào"),
                         tcp.cache_key(voice="v", text="xin chào"))

    def test_sensitive_to_inputs(self):
        base = tcp.cache_key(voice="v", text="xin chào")
        self.assertNotEqual(
            base, tcp.cache_key(voice="w", text="xin chào"))
        self.assertNotEqual(
            base, tcp.cache_key(voice="v", text="xin chao"))
        self.assertNotEqual(
            base, tcp.cache_key(voice="v", text="xin chào", speed=90))
        self.assertNotEqual(
            base, tcp.cache_key(voice="v", text="xin chào",
                                target_db=-18.0))


class TestCacheBehaviour(unittest.TestCase):
    def _run(self, job_dir, cache_dir, tts_bin):
        orig = tcp.TTS_BIN
        tcp.TTS_BIN = tts_bin
        try:
            return tcp.tts_cli_provider(
                LINES, job_dir, cache_dir=cache_dir)
        finally:
            tcp.TTS_BIN = orig

    def test_miss_then_hit_reuses_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cache = root / "cache"
            tts_bin = _install_fake(root)
            job1, job2 = root / "job1", root / "job2"
            wavs1 = self._run(job1, cache, tts_bin)
            first = wavs1[0].read_bytes()
            manifest1 = json.loads(
                (job1 / "voices_manifest.json").read_text(
                    encoding="utf-8"))
            self.assertFalse(manifest1["lines"][0]["cached"])
            self.assertEqual(manifest1["cache"]["hits"], 0)
            self.assertEqual(len(list(cache.glob("*.wav"))), 1)
            # Second job, same line: no re-synthesis -- remove
            # the fake binary so any TTS call would explode.
            Path(tts_bin).unlink()
            wavs2 = self._run(job2, cache, tts_bin)
            self.assertEqual(wavs2[0].read_bytes(), first)
            manifest2 = json.loads(
                (job2 / "voices_manifest.json").read_text(
                    encoding="utf-8"))
            self.assertTrue(manifest2["lines"][0]["cached"])
            self.assertEqual(manifest2["cache"]["hits"], 1)

    def test_cache_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tts_bin = _install_fake(root)
            job1 = root / "job1"
            self._run(job1, False, tts_bin)
            manifest = json.loads(
                (job1 / "voices_manifest.json").read_text(
                    encoding="utf-8"))
            self.assertIsNone(manifest["cache"]["dir"])
            self.assertFalse(manifest["lines"][0]["cached"])

    def test_small_cache_entry_is_miss(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cache = root / "cache"
            cache.mkdir()
            voice = tcp.resolve_voice_assignment(
                ["Linh"])[0]["Linh"]["voice"]
            key = tcp.cache_key(voice=voice, text="Tôi là Linh.")
            (cache / f"{key}.wav").write_bytes(b"x" * 500)
            tts_bin = _install_fake(root)
            job = root / "job"
            wavs = self._run(job, cache, tts_bin)
            self.assertGreater(wavs[0].stat().st_size, 1000)
            manifest = json.loads(
                (job / "voices_manifest.json").read_text(
                    encoding="utf-8"))
            self.assertFalse(manifest["lines"][0]["cached"])
            self.assertGreater(
                (cache / f"{key}.wav").stat().st_size, 1000)

    def test_env_off_disables_default_cache(self):
        with mock.patch.dict(os.environ, {"AI_CLIP_TTS_CACHE": "off"}):
            self.assertEqual(tcp.default_cache_dir(), Path("off"))
        with mock.patch.dict(os.environ,
                             {"AI_CLIP_TTS_CACHE": "/tmp/tts-x"}):
            self.assertEqual(tcp.default_cache_dir(),
                             Path("/tmp/tts-x"))


if __name__ == "__main__":
    unittest.main()
