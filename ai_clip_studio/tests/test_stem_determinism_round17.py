"""R17 (R12-D2): noise-based stems render bit-identically.

ffmpeg's anoisesrc defaults to a random seed, so identical loop
inputs produced different ambience + foley stems run to run while
dialogue/narration/footsteps were bit-identical. Every noise
source now carries the fixed seed; identical specs render
identical WAV bytes, and distinct specs still sound distinct.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.audio_events import SYNTHESIS_MAP
from ai_clip_studio.product_flow import _synth_segment


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TestStemDeterminism(unittest.TestCase):
    def test_same_spec_renders_identical_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for kind in ("stone_crack", "street_bed", "room_tone",
                         "wind_bed", "soft_rustle"):
                a = _synth_segment(SYNTHESIS_MAP[kind], 1.5,
                                   tmp / f"{kind}_a.wav")
                b = _synth_segment(SYNTHESIS_MAP[kind], 1.5,
                                   tmp / f"{kind}_b.wav")
                self.assertEqual(_sha(a), _sha(b), kind)

    def test_distinct_specs_stay_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            a = _synth_segment(SYNTHESIS_MAP["stone_crack"], 1.0,
                               tmp / "a.wav")
            b = _synth_segment(SYNTHESIS_MAP["soft_rustle"], 1.0,
                               tmp / "b.wav")
            self.assertNotEqual(_sha(a), _sha(b))

    def test_every_noise_source_is_seeded(self):
        for kind, spec in SYNTHESIS_MAP.items():
            for lavfi in spec["inputs"]:
                if "anoisesrc" in lavfi:
                    self.assertIn("seed=", lavfi, kind)


if __name__ == "__main__":
    unittest.main()
