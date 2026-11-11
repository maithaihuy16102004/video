"""Tests for the 16:9 Ricks-style pipeline.

Run:  python3 -m unittest discover -s tests -v
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from quality_gate_16x9 import check_package, check_rendered_video  # noqa: E402
from render_16x9 import (  # noqa: E402
    build_master_command,
    build_thumbnail_command,
    validate_16x9_input,
)
from ricks_story_director import RicksStyleDirector  # noqa: E402

SCRIPT = Path(__file__).resolve().parent.parent / "examples" / "script_eiffel_tower_twice.txt"


class TestDirector(unittest.TestCase):
    def test_eiffel_package_is_16x9_and_has_hook_twist_payoff(self):
        pkg = RicksStyleDirector().analyze_script(
            SCRIPT.read_text(encoding="utf-8"), "He sold the Eiffel Tower. Twice."
        )
        self.assertEqual((pkg.width, pkg.height), (1920, 1080))
        self.assertEqual(pkg.aspect_ratio, "16:9")
        self.assertEqual(pkg.fps, 24)
        self.assertTrue(pkg.hook.startswith("He sold the Eiffel Tower"))
        purposes = [s.purpose for s in pkg.shots]
        self.assertIn("HOOK", purposes)
        self.assertIn("TWIST", purposes)
        self.assertIn("PAYOFF", purposes)
        self.assertEqual(RicksStyleDirector().validate(pkg), [])

    def test_empty_script_is_rejected(self):
        with self.assertRaises(ValueError):
            RicksStyleDirector().analyze_script("", "Nope")

    def test_short_script_is_rejected(self):
        with self.assertRaises(ValueError):
            RicksStyleDirector().analyze_script("Only one sentence.", "Nope")

    def test_each_shot_is_3_to_6_5_seconds(self):
        pkg = RicksStyleDirector().analyze_script(
            SCRIPT.read_text(encoding="utf-8"), "He sold the Eiffel Tower. Twice."
        )
        for shot in pkg.shots:
            self.assertGreaterEqual(shot.duration_sec, 3.0)
            self.assertLessEqual(shot.duration_sec, 6.5)


class TestQualityGate(unittest.TestCase):
    def _good_package(self):
        pkg = RicksStyleDirector().analyze_script(
            SCRIPT.read_text(encoding="utf-8"), "He sold the Eiffel Tower. Twice."
        )
        return pkg.to_dict()

    def test_good_package_passes(self):
        self.assertTrue(check_package(self._good_package()).passed)

    def test_vertical_package_fails(self):
        pkg = self._good_package()
        pkg["aspect_ratio"] = "9:16"
        pkg["width"], pkg["height"] = 1080, 1920
        result = check_package(pkg)
        self.assertFalse(result.passed)
        self.assertTrue(any("wrong_aspect_ratio" in e for e in result.errors))

    def test_long_shot_fails(self):
        pkg = self._good_package()
        pkg["shots"][0]["duration_sec"] = 14.0
        result = check_package(pkg)
        self.assertFalse(result.passed)
        self.assertTrue(any("shot_too_long" in e for e in result.errors))

    def test_missing_twist_fails(self):
        pkg = self._good_package()
        pkg["shots"] = [s for s in pkg["shots"] if s["purpose"] != "TWIST"]
        result = check_package(pkg)
        self.assertFalse(result.passed)
        self.assertTrue(any("no_twist" in e for e in result.errors))


class TestRender(unittest.TestCase):
    def test_master_command_is_1920x1080_h264_aac(self):
        cmd = build_master_command("frames/frame_%04d.png", "audio.wav", "out.mp4")
        self.assertIn("1920:1080", " ".join(cmd))
        self.assertIn("libx264", cmd)
        self.assertIn("aac", cmd)
        self.assertIn("+faststart", cmd)
        self.assertIn("loudnorm=I=-14.0", " ".join(cmd))

    def test_thumbnail_is_1280x720(self):
        cmd = build_thumbnail_command("out.mp4", "thumb.png")
        self.assertIn("scale=1280:720", " ".join(cmd))

    def test_vertical_input_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_16x9_input(1080, 1920)


if __name__ == "__main__":
    unittest.main()
