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
        # Round 7: SC01_SH02 is a MEDIUM CLOSE-UP directive; the
        # camera-text mapping fix reports it as medium_close_up
        # (the old close_up was the substring-order bug). The
        # frozen-crop wiring under test is unchanged.
        rep = self._render(0)
        self.assertEqual(rep["shot_type"], "medium_close_up")
        self.assertTrue(rep["crop_frozen"])
        anchor = rep["crop_anchor"]
        self.assertTrue(anchor["frozen"])
        self.assertEqual(anchor["anchor"], "standing_box")
        self.assertEqual(anchor["scale"], rep["applied_scale"])
        self.assertEqual(anchor["shot_type"], "medium_close_up")

    def test_close_up_directive_and_validation_static(self):
        # Round-1 locomotion widening (Zeus #51 defect family): shot 0
        # is a close_up on a WALKING shot, so its frozen crop widens
        # to the full frame (scale 1.0) instead of the old 2.6x head
        # crop the subject could walk out of. The freeze contract is
        # unchanged: one crop, static directive, frozen anchor. The
        # validation crop_rect is None by the full-frame convention
        # (see test_full_frame_shot_reports_no_crop_rect).
        rep = self._render(0)
        directive = rep["camera_directive"]
        self.assertEqual(directive["mode"], "static_anchored")
        self.assertEqual(directive["start_transform"],
                         directive["end_transform"])
        self.assertTrue(directive["source"])
        validation = rep["camera_validation"]
        self.assertTrue(validation["is_static"])
        self.assertEqual(rep["applied_scale"], 1.0)
        self.assertTrue(rep["locomotion_widened"])
        self.assertIsNone(validation["crop_rect"])
        self.assertEqual(rep["crop_anchor"]["crop_rect"],
                         [0, 0, 1920, 1080])
        # The crop_rect wiring pin moves to shot 1, a cropped
        # head_hands reaction shot: for a real crop, the validation
        # rect must equal the frozen anchor rect.
        rep1 = self._render(1)
        self.assertEqual(rep1["camera_validation"]["crop_rect"],
                         rep1["crop_anchor"]["crop_rect"])
        self.assertTrue(rep1["camera_validation"]["is_static"])

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
        # Round-1 locomotion widening: shot 0 is a walking close-up,
        # so the one frozen crop is the full frame (1.0), not the old
        # 2.6x head crop. All 24 frames still share that single crop.
        self.assertEqual(rep["crop_anchor"]["scale"], 1.0)
        self.assertTrue(rep["locomotion_widened"])


if __name__ == "__main__":
    unittest.main()
