"""Round 20 (R19-D1): dressing-aware head separation.

The R19 swept separation moved Ba Tu onto the kitchen lamp
in Loop 02 #17, hiding it all 55 frames. The dressing loop
pushes head corridors off small dressing elements' centres
while pair gaps and frame margins allow. Heads win over
dressing; unresolved elements are recorded, never forced.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

import ai_clip_studio.product_renderer as pr
from ai_clip_studio.product_renderer import (
    _drawn_height_factor,
    _render_shot,
)
from ai_clip_studio.tests.test_cue_coverage_round18 import (
    _delivered_shot,
)

FACE = np.array([247, 243, 232])


def _discs(path):
    arr = np.asarray(Image.open(path).convert("RGB")).astype(int)
    m = (np.abs(arr - FACE).sum(axis=2) < 40)
    lab, n = ndi.label(m)
    out = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        if len(xs) >= 3000:
            out.append((float(xs.mean()), float(ys.mean()),
                        float((xs.max() - xs.min()) / 2)))
    return sorted(out), arr


class TestDressingRects(unittest.TestCase):
    def test_kitchen_rects_on_real_path(self):
        # Spy the real call: the kitchen package + the shot
        # camera of Loop 02 #17.
        seen = []
        orig = pr._dressing_rects

        def spy(pkg, camera, W, H):
            rects = orig(pkg, camera, W, H)
            seen.extend(rects)
            return rects

        package, shot = _delivered_shot(17, job="req_db6a67ff9ca3")
        with mock.patch.object(pr, "_dressing_rects", spy):
            with tempfile.TemporaryDirectory() as tmp:
                _render_shot({"shot": shot, "package": package,
                              "out_dir": tmp, "still_only": True})
        ids = {r["id"] for r in seen}
        # The lamp shade is protected dressing.
        self.assertIn("room_lamp_shade", ids)
        # Wall trim is architecture, never protected.
        self.assertNotIn("room_pilaster_1", ids)
        self.assertNotIn("room_win_0", ids)
        self.assertNotIn("room_win_1", ids)
        # Distant backdrop is never protected.
        self.assertFalse(any(i.startswith("skyline") for i in ids))
        # The wide table top is excluded by the width filter.
        self.assertNotIn("kitchen_table_top", ids)
        # The cabinet papers are specks under the area floor.
        self.assertNotIn("cabinet_papers", ids)
        # Rects carry centres inside their bounds.
        for r in seen:
            self.assertLessEqual(r["left"], r["cx"])
            self.assertLessEqual(r["cx"], r["right"])
            self.assertLessEqual(r["top"], r["cy"])
            self.assertLessEqual(r["cy"], r["bottom"])


class TestDrawnHeightFactor(unittest.TestCase):
    def test_elderly_small(self):
        f = _drawn_height_factor(
            {"name": "Ba Tu", "template": "elderly",
             "stature": 0.85})
        self.assertAlmostEqual(f, 520 / 560 * 0.85, places=6)

    def test_child(self):
        f = _drawn_height_factor(
            {"name": "Be Ti", "template": "child"})
        self.assertAlmostEqual(f, 400 / 560, places=6)

    def test_male_default(self):
        f = _drawn_height_factor({"name": "Anon"})
        self.assertAlmostEqual(f, 1.0, places=6)

    def test_registry_name_conservative(self):
        # "minh" is a locked registry instance: factor 1.0.
        f = _drawn_height_factor({"name": "Minh"})
        self.assertEqual(f, 1.0)

    def test_bad_stature_falls_back(self):
        f = _drawn_height_factor(
            {"name": "Anon", "template": "female",
             "stature": "tall"})
        self.assertAlmostEqual(f, 540 / 560, places=6)


class TestDressingSeparation(unittest.TestCase):
    def test_shot17_lamp_visible_heads_clear(self):
        package, shot = _delivered_shot(17, job="req_db6a67ff9ca3")
        with tempfile.TemporaryDirectory() as tmp:
            res = _render_shot({"shot": shot, "package": package,
                                "out_dir": tmp, "still_only": True})
            still = Path(tmp) / "shot_017" / "still.png"
            discs, arr = _discs(still)
        hc = res["head_clearance"]
        # The dressing loop moved Ba Tu (and only her).
        self.assertIn("Bà Tư", hc["dressing_moves"])
        self.assertEqual(hc["unresolved_dressing"], [])
        self.assertEqual(hc["unresolved"], [])
        # Three head discs, pairwise separated.
        self.assertEqual(len(discs), 3)
        for i in range(3):
            for j in range(i + 1, 3):
                dx = discs[i][0] - discs[j][0]
                dy = discs[i][1] - discs[j][1]
                dist = (dx * dx + dy * dy) ** 0.5
                self.assertGreater(
                    dist, discs[i][2] + discs[j][2],
                    f"discs {i},{j} overlap")
        # The lamp shade region is mostly NOT face fill: the
        # shade (centre 860, 356) reads instead of Ba Tu's
        # head (R19: face_frac 0.809).
        region = arr[300:420, 800:920]
        face_frac = float(
            (np.abs(region - FACE).sum(axis=2) < 40).mean())
        self.assertLess(face_frac, 0.3)

    def test_shot19_framing_holds(self):
        package, shot = _delivered_shot(19, job="req_db6a67ff9ca3")
        with tempfile.TemporaryDirectory() as tmp:
            res = _render_shot({"shot": shot, "package": package,
                                "out_dir": tmp, "still_only": True})
        hc = res["head_clearance"]
        self.assertEqual(hc["unresolved_dressing"], [])
        boxes = {b["name"]: b for b in res["character_boxes"]}
        self.assertTrue(boxes["Bà Tư"]["in_frame"])
        self.assertTrue(boxes["Bé Tí"]["in_frame"])
        self.assertFalse(boxes["An"]["in_frame"])


if __name__ == "__main__":
    unittest.main()
