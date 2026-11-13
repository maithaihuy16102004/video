"""Timeline references end-to-end (integration sprint section 8).

A real garden-fixture job (mocked render only) must stamp every
downstream dict artifact with the frozen schedule's version +
checksum, and the job record must carry the same reference.
"""

import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from ai_clip_studio import product_flow
from ai_clip_studio.unified_timeline import (
    POST_RENDER_ARTIFACTS, PRE_FREEZE_ARTIFACTS, check_timeline_refs)

AGENT = Path(__file__).resolve().parent.parent.parent
GARDEN = (AGENT / "ai_clip_studio" / "tests" / "fixtures"
          / "unseen_garden_key.studio.md").read_text(encoding="utf-8")


def _stub_tts(flat_lines, job_dir, voice_hints=None, voice_ids=None):
    job_dir = Path(job_dir)
    wavs = []
    for i, _line in enumerate(flat_lines):
        path = job_dir / f"line_{i + 1:02d}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            frames = b"".join(
                struct.pack("<h", int(12000 * math.sin(
                    2 * math.pi * 440 * n / 48000)))
                for n in range(48000))
            wav.writeframes(frames)
        wavs.append(path)
    (job_dir / "voices_manifest.json").write_text(json.dumps({
        "distinct_voices_used": 1,
        "speakers": sorted({line["speaker"] for line in flat_lines}),
    }), encoding="utf-8")
    return wavs


class TestTimelineRefsEndToEnd(unittest.TestCase):
    def test_job_artifacts_carry_matching_refs(self):
        render_result = {"n_frames": 1, "duration_sec": 0.04,
                         "violations": [], "camera_accounting": {},
                         "frames": [], "shots": []}
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            patches = [
                mock.patch.object(product_flow, "tts_cli_provider",
                                  side_effect=_stub_tts),
                mock.patch.object(product_flow, "render_product_video",
                                  return_value=render_result),
                mock.patch.object(
                    product_flow, "render_storyboard_stills",
                    return_value=[]),
                mock.patch.object(
                    product_flow, "sync_foley_footsteps",
                    return_value={"status": "skipped", "placements": 0,
                                  "unresolved": [],
                                  "mix_changed": False}),
            ]
            for p in patches:
                p.start()
            try:
                job = product_flow.run_product_job(
                    GARDEN, job_dir, upload=False)
            finally:
                for p in patches:
                    p.stop()
            # The job fails at the mux (mocked render produced no
            # frames); freezing + both stamp passes ran before it.
            unified = json.loads(
                (job_dir / "unified_timeline.json").read_text(
                    encoding="utf-8"))
            expected = {
                "timeline_version": unified["timeline_version"],
                "timeline_checksum": unified["checksum"]}
            self.assertEqual(expected["timeline_version"], 1)
            self.assertEqual(len(expected["timeline_checksum"]), 64)
            stamped = {}
            for name in (*PRE_FREEZE_ARTIFACTS,
                         *POST_RENDER_ARTIFACTS):
                path = job_dir / name
                if not path.exists():
                    continue
                blob = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(blob, dict):
                    stamped[name] = blob.get("timeline_ref")
            # Every dict artifact that exists carries the ref.
            self.assertIn("timeline.json", stamped)
            self.assertIn("action_events.json", stamped)
            self.assertIn("scene_graph.json", stamped)
            self.assertIn("camera_accounting.json", stamped)
            self.assertIn("renderer_info.json", stamped)
            for name, ref in stamped.items():
                self.assertEqual(ref, expected, name)
            # The job record carries the same reference.
            job_blob = json.loads(
                (job_dir / "job.json").read_text(encoding="utf-8"))
            self.assertEqual(job_blob["timeline_ref"], expected)
            # The verifier's consistency check passes on this dir.
            check = check_timeline_refs(job_dir, unified)
            self.assertFalse(check["skipped"])
            self.assertEqual(check["failures"], [])
            self.assertIn("timeline.json", check["checked"])
        self.assertEqual(job.status, "FAILED")  # mux, by design here


if __name__ == "__main__":
    unittest.main()
