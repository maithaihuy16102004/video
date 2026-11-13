"""Regression tests for the D2 frozen crop (Phase C checkpoint).

_render_shot must compute ONE crop per shot from standing boxes and
apply it to every frame: the shot report records crop_frozen=True,
a frozen crop_anchor, a STATIC_ANCHORED directive with equal
start/end transforms, and a validation with is_static() True.
Pixel-level constancy is proven by proofs/proof_test_c.py (close-up
sky MAD 44.92 -> 0.00); these tests pin the wiring in the suite.
"""

import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.product_renderer import _render_shot, plan_shots
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent
SCRIPT = AGENT / "examples" / "hitler_ep01_munich_1914.studio.md"


def _planned_shots():
    doc = parse_studio_script_v1(SCRIPT.read_text(encoding="utf-8"))
    pkg = adapt_document(doc)
    n_lines = sum(len(sc["lines"]) for sc in pkg["scenes"])
    timeline = [{"line_index": i + 1, "duration": 0.65}
                for i in range(n_lines)]
    return pkg, plan_shots(pkg, timeline)


class TestCropFreeze(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg, cls.shots = _planned_shots()

    def _render(self, idx, still_only=True):
        shot = dict(self.shots[idx])
        shot["index"] = idx
        shot["duration"] = 1.0
        return _render_shot({"shot": shot, "package": self.pkg,
                             "out_dir": tempfile.mkdtemp(),
                             "still_only": still_only})

    def test_close_up_reports_frozen_crop(self):
        rep = self._render(0)
        self.assertEqual(rep["shot_type"], "close_up")
        self.assertTrue(rep["crop_frozen"])
        anchor = rep["crop_anchor"]
        self.assertTrue(anchor["frozen"])
        self.assertEqual(anchor["anchor"], "standing_box")
        self.assertEqual(anchor["scale"], rep["applied_scale"])
        self.assertEqual(anchor["shot_type"], "close_up")

    def test_close_up_directive_and_validation_static(self):
        rep = self._render(0)
        directive = rep["camera_directive"]
        self.assertEqual(directive["mode"], "static_anchored")
        self.assertEqual(directive["start_transform"],
                         directive["end_transform"])
        self.assertTrue(directive["source"])
        validation = rep["camera_validation"]
        self.assertTrue(validation["is_static"])
        self.assertEqual(validation["crop_rect"],
                         rep["crop_anchor"]["crop_rect"])

    def test_full_frame_shot_reports_no_crop_rect(self):
        rep = self._render(4)
        self.assertEqual(rep["shot_type"], "establishing")
        self.assertTrue(rep["crop_frozen"])
        self.assertEqual(rep["applied_scale"], 1.0)
        self.assertIsNone(rep["camera_validation"]["crop_rect"])

    def test_video_frames_share_one_frozen_crop(self):
        rep = self._render(0, still_only=False)
        self.assertTrue(rep["crop_frozen"])
        self.assertEqual(len(rep["frames"]), 24)
        self.assertEqual(rep["crop_anchor"]["scale"], 2.6)


if __name__ == "__main__":
    unittest.main()
