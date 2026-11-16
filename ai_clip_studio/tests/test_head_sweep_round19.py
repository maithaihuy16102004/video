"""Round 19 (R18-D1): head-clearance separation on SWEPT head
ranges, and walk-path-widened anchor OTHERS boxes.

The R6-D4 pass separated STATIC standing boxes, but locomotion
carries the head up to 380 px from the staging mark: Loop 02
#17 (320 px legacy walk) and #19 (380 px compiled run) both put
Be Ti's head on Ba Tu's face. The pass now separates swept
ranges (compiled replay + legacy cue travel + gait-lean
allowance), and the cropped anchor branches widen the OTHERS
boxes by their locomotion paths so safe_frame's fully-in-or-
fully-out rule judges the travelled extent.
"""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from ai_clip_studio.product_renderer import (
    _render_shot,
    _swept_head_range,
)
from ai_clip_studio.tests.test_cue_coverage_round18 import (
    _delivered_shot,
)

FACE = np.array([247, 243, 232])


def _ev(primitive, retreat=False):
    return {"required_pose": {"primitive": primitive,
                              "params": {"retreat": retreat}}}


class TestSweptHeadRange(unittest.TestCase):
    def test_no_travel_is_identity(self):
        self.assertEqual(
            _swept_head_range([], 500.0, 1, 700.0), (500.0, 500.0))

    def test_compiled_walk_replays_with_lean_allowance(self):
        lo, hi = _swept_head_range(
            [(0.0, 1.0, _ev("walk_to"))], 500.0, -1, 700.0)
        # 320 px left, plus 0.09 * 700 = 63 px lean allowance
        # on both ends.
        self.assertAlmostEqual(lo, 500.0 - 320.0 - 63.0)
        self.assertAlmostEqual(hi, 500.0 + 63.0)

    def test_retreat_flips(self):
        lo, hi = _swept_head_range(
            [(0.0, 1.0, _ev("run_to", retreat=True))],
            500.0, -1, 700.0)
        self.assertAlmostEqual(lo, 500.0 - 63.0)
        self.assertAlmostEqual(hi, 500.0 + 380.0 + 63.0)

    def test_legacy_end_extends_range(self):
        lo, hi = _swept_head_range([], 500.0, 1, 700.0,
                                   legacy_end=180.0)
        self.assertAlmostEqual(lo, 180.0 - 63.0)
        self.assertAlmostEqual(hi, 500.0 + 63.0)

    def test_non_locomotion_windows_ignored(self):
        self.assertEqual(
            _swept_head_range(
                [(0.0, 1.0, _ev("nod"))], 500.0, 1, 700.0),
            (500.0, 500.0))


def _discs(path):
    arr = np.asarray(Image.open(path).convert("RGB")).astype(int)
    mask = (np.abs(arr - FACE).sum(axis=2) < 40)
    lab, n = ndi.label(mask)
    out = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        if len(xs) < 3000:
            continue
        out.append((xs.mean(), ys.mean(),
                    (xs.max() - xs.min()) / 2.0))
    return sorted(out)


class TestHeadSweepRenders(unittest.TestCase):
    def _render(self, idx):
        package, shot = _delivered_shot(
            idx, job="req_c9c37b84b269")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        res = _render_shot({"shot": shot, "package": package,
                            "out_dir": tmp.name,
                            "still_only": False})
        return res, Path(tmp.name) / f"shot_{idx:03d}"

    def test_shot17_heads_clear_all_frames(self):
        res, shot_dir = self._render(17)
        moved = res["head_clearance"]["moved"]
        self.assertIn("Bé Tí", moved)
        self.assertIn("Bà Tư", moved)
        self.assertEqual(res["head_clearance"]["unresolved"], [])
        for path in sorted(shot_dir.glob("f*.png"))[::6]:
            discs = _discs(path)
            for a, b in zip(discs, discs[1:]):
                dist = ((a[0] - b[0]) ** 2
                        + (a[1] - b[1]) ** 2) ** 0.5
                self.assertLess(a[2] + b[2], dist,
                                f"{path.name}: discs overlap")

    def test_shot19_runner_stays_in_frame_and_clear(self):
        res, shot_dir = self._render(19)
        moved = res["head_clearance"]["moved"]
        self.assertIn("Bé Tí", moved)
        self.assertEqual(res["head_clearance"]["unresolved"], [])
        boxes = {b["name"]: b for b in res["character_boxes"]}
        self.assertTrue(boxes["Bé Tí"]["in_frame"])
        self.assertTrue(boxes["Bà Tư"]["in_frame"])
        for path in sorted(shot_dir.glob("f*.png"))[::6]:
            discs = _discs(path)
            for a, b in zip(discs, discs[1:]):
                dist = ((a[0] - b[0]) ** 2
                        + (a[1] - b[1]) ** 2) ** 0.5
                self.assertLess(a[2] + b[2], dist,
                                f"{path.name}: discs overlap")


if __name__ == "__main__":
    unittest.main()
