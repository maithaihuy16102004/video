"""Round 1 geometry-footprint tests: long-handled props (trident,
staff, sword, hammer) draw at a tall footprint instead of squeezing
into the 76x50 box, where a trident spec scaled to 0.19x and drew
21x50px with a ~1px shaft -- present in telemetry, invisible on
screen. Compact kinds (bolt, helmet, wallet) are pinned unchanged,
and the contact audit's _spec_shapes must match the renderer's drawn
size (one shared table, geometry_footprint).
"""
import unittest

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.contact_audit import _spec_shapes
from ai_clip_studio.product_renderer import _draw_prop
from ai_clip_studio.prop_system import (
    DEFAULT_GEOMETRY_FOOTPRINT,
    geometry_footprint,
)


def _drawn_bbox(kind, w=None, h=None):
    img = Image.new("RGB", (400, 400), (255, 255, 255))
    kwargs = {"kind": kind}
    if w is not None:
        kwargs["w"] = w
    if h is not None:
        kwargs["h"] = h
    _draw_prop(ImageDraw.Draw(img), 200, 200, **kwargs)
    mask = (np.abs(np.asarray(img).astype(int) - 255).sum(axis=2) > 30)
    ys, xs = np.where(mask)
    return (int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1),
            int(mask.sum()))


class TestGeometryFootprint(unittest.TestCase):
    def test_table_values(self):
        self.assertEqual(geometry_footprint("trident"), (76.0, 170.0))
        self.assertEqual(geometry_footprint("staff"), (76.0, 170.0))
        self.assertEqual(geometry_footprint("sword"), (76.0, 170.0))
        self.assertEqual(geometry_footprint("hammer"), (110.0, 110.0))

    def test_compact_kinds_keep_default(self):
        # Round-6: bolt/helmet/shield/stone LEFT this list -- the
        # default 76x50 box shrank them to 24-50 px slivers
        # (uniform scaling against a tall native aspect). Only
        # genuinely wide/compact kinds keep the default now.
        for kind in ("wallet", "crown", "hat", "ring",
                     "unknown-kind"):
            self.assertEqual(geometry_footprint(kind),
                             DEFAULT_GEOMETRY_FOOTPRINT, kind)

    def test_tall_kinds_keep_native_aspect(self):
        # Round-6 footprint table: each tall/square kind draws at
        # a readable size instead of a squeezed sliver.
        self.assertEqual(geometry_footprint("bolt"), (76.0, 156.0))
        self.assertEqual(geometry_footprint("shield"), (76.0, 76.0))
        self.assertEqual(geometry_footprint("helmet"), (76.0, 57.0))
        self.assertEqual(geometry_footprint("chain"), (30.0, 170.0))
        self.assertEqual(geometry_footprint("stone"), (76.0, 76.0))
        self.assertEqual(geometry_footprint("boulder"), (96.0, 100.0))
        w, h, ink = _drawn_bbox("shield")
        self.assertGreaterEqual(w, 60)
        # Round-7: the shield is a round wooden disc, so the drawn
        # box is square (the old kite was taller than wide).
        self.assertGreaterEqual(h, 60)
        self.assertLess(abs(w - h), 6)
        self.assertGreaterEqual(ink, 1500)
        w, h, ink = _drawn_bbox("bolt")
        self.assertGreaterEqual(h, 130)
        self.assertGreaterEqual(ink, 500)
        w, h, ink = _drawn_bbox("stone")
        self.assertGreaterEqual(w, 60)
        self.assertGreaterEqual(h, 60)

    def test_trident_draws_tall_and_visible(self):
        w, h, ink = _drawn_bbox("trident")
        self.assertGreaterEqual(w, 60)
        self.assertGreaterEqual(h, 150)
        self.assertGreaterEqual(ink, 800)

    def test_staff_sword_hammer_draw_tall(self):
        w, h, ink = _drawn_bbox("staff")
        self.assertGreaterEqual(h, 150)
        self.assertGreaterEqual(ink, 500)
        w, h, ink = _drawn_bbox("sword")
        self.assertGreaterEqual(w, 40)
        self.assertGreaterEqual(h, 150)
        w, h, ink = _drawn_bbox("hammer")
        self.assertGreaterEqual(w, 70)
        self.assertGreaterEqual(h, 95)
        self.assertGreaterEqual(ink, 2000)

    def test_compact_kinds_unchanged(self):
        # Round-6: the bolt LEFT the compact list -- its old
        # <=35x60 pin was the squeezed sliver itself (native
        # 132x270 scaled to 24x50). It now draws tall; the wallet
        # keeps its legacy size.
        w, h, _ink = _drawn_bbox("bolt")
        self.assertGreaterEqual(h, 130)
        w, h, _ink = _drawn_bbox("wallet")
        self.assertTrue(70 <= w <= 82, w)
        self.assertTrue(45 <= h <= 56, h)

    def test_explicit_footprint_wins(self):
        _w0, h0, _i0 = _drawn_bbox("trident")
        _w1, h1, _i1 = _drawn_bbox("trident", w=300, h=200)
        self.assertGreater(h1, h0)

    def test_audit_shapes_match_renderer_size(self):
        for kind in ("trident", "hammer"):
            _polys, _lines, _rects, bbox = _spec_shapes(kind)
            w, h, _ink = _drawn_bbox(kind)
            # Drawn bbox includes the outline stroke; the spec bbox
            # is the part geometry. They must agree within 3px.
            self.assertAlmostEqual(bbox[2] - bbox[0], w, delta=3.0)
            self.assertAlmostEqual(bbox[3] - bbox[1], h, delta=3.0)


if __name__ == "__main__":
    unittest.main()
