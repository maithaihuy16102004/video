"""Round-7 glow exclusions: the deferred insert halo must light the
prop without washing the cast.

The static standing-box exclusion (round 6, R2-F1) covered the
whole insert crop whenever the holder stood AT the prop, erasing
the prop's own halo (the R7 probe insert rendered grey: no gold,
no halo). The exclusion now follows the posed limbs per frame,
and a hole around each glow source stays lit even inside a limb
box.
"""

import unittest

from PIL import Image

from ai_clip_studio.effects import burst_record
from ai_clip_studio.lighting import paint_energy_glow_excluding
from ai_clip_studio.product_renderer import _glow_exclusion_boxes


def _joints_at_prop():
    # The holder stands AT the prop (a held glowing prop in an
    # insert crop): head/hip near x1280, the right hand at the
    # prop (1300, 280), legs straddling x1240/1320.
    return {
        "head": [1250.0, 200.0], "hip": [1280.0, 640.0],
        "shoulder": [1270.0, 300.0],
        "elbow_l": [1200.0, 420.0], "hand_l": [1150.0, 520.0],
        "elbow_r": [1260.0, 400.0], "hand_r": [1300.0, 280.0],
        "knee_l": [1240.0, 850.0], "foot_l": [1240.0, 1080.0],
        "knee_r": [1320.0, 850.0], "foot_r": [1320.0, 1080.0],
        "head_r": 120.0, "H": 704.0,
    }


_CROP = (1110.0, 136.0, 1494.0, 352.0)


def _map(x, y):
    return ((x - _CROP[0]) * 5.0, (y - _CROP[1]) * 5.0)


class TestGlowExclusionBoxes(unittest.TestCase):
    def test_boxes_follow_the_limbs_not_the_standing_box(self):
        # The gap between the shins is inside the standing box
        # (cx 1280 +- 140, y 376..1080) but outside every limb
        # box: the halo spills through the gap instead of being
        # erased by one big rect.
        boxes = _glow_exclusion_boxes(
            {"Linh": _joints_at_prop()}, ["Linh"], _CROP,
            (1920, 1080))
        self.assertTrue(boxes)
        px, py = _map(1280.0, 900.0)
        for (x0, y0, x1, y1) in boxes:
            self.assertFalse(x0 <= px <= x1 and y0 <= py <= y1,
                             f"gap point inside {x0, y0, x1, y1}")

    def test_leg_segment_is_covered(self):
        # A point on the left shin maps inside some box.
        boxes = _glow_exclusion_boxes(
            {"Linh": _joints_at_prop()}, ["Linh"], _CROP,
            (1920, 1080))
        px, py = _map(1240.0, 965.0)
        self.assertTrue(any(x0 <= px <= x1 and y0 <= py <= y1
                            for (x0, y0, x1, y1) in boxes))

    def test_missing_joints_skip_segments(self):
        partial = {"head": [960.0, 200.0], "hip": [980.0, 640.0],
                   "head_r": 120.0, "H": 704.0}
        boxes = _glow_exclusion_boxes(
            {"Linh": partial}, ["Linh"],
            (0.0, 0.0, 1920.0, 1080.0), (1920, 1080))
        # Torso + head disc only; no crash on the missing limbs.
        self.assertEqual(len(boxes), 2)


class TestGlowHoles(unittest.TestCase):
    def test_hole_stays_lit_inside_a_box(self):
        img = Image.new("RGB", (200, 200), (40, 40, 40))
        record = burst_record("p", 100.0, 100.0, 1.0,
                              (255, 200, 90), 80.0)
        paint_energy_glow_excluding(
            img, record, [(0.0, 0.0, 200.0, 200.0)],
            feather_px=0.0, holes=[(100.0, 100.0, 30.0)])
        centre = img.getpixel((100, 100))
        corner = img.getpixel((10, 10))
        self.assertGreater(centre[0], 150,
                           f"hole centre unlit: {centre}")
        self.assertLess(corner[0], 80,
                        f"box corner washed: {corner}")

    def test_box_without_hole_stays_dark(self):
        img = Image.new("RGB", (200, 200), (40, 40, 40))
        record = burst_record("p", 100.0, 100.0, 1.0,
                              (255, 200, 90), 80.0)
        paint_energy_glow_excluding(
            img, record, [(0.0, 0.0, 200.0, 200.0)],
            feather_px=0.0)
        self.assertLess(img.getpixel((100, 100))[0], 80)


if __name__ == "__main__":
    unittest.main()
