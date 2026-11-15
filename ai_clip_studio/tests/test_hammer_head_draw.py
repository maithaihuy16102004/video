"""Round-5 hammer contact: a held hammer draws articulated, its
striking face landing on the computed head position (the tip), and
strikers stage beside the anvil.

Before this, the hammer drew at the footprint scale with a fixed
orientation while the primitive aimed at, and the contact audit
measured, hammer_head_position -- the drawn head fell ~70 px short
of the computed head and the audit passed a non-contact strike
(R2-A2). The tip draw closes the record-vs-visual gap.
"""
import math
import unittest

from PIL import Image, ImageDraw

from ai_clip_studio.animation.primitives import (
    HAMMER_GRIP_ANGLE_RAD, hammer_head_position)
from ai_clip_studio.product_renderer import (
    _GEOMETRY_SLOT_FILLS, _draw_prop)


class TestHammerTipDraw(unittest.TestCase):
    def _draw(self, hand, tip):
        img = Image.new("RGB", (500, 500), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        _draw_prop(draw, hand[0], hand[1], kind="hammer", tip=tip)
        return img

    def _pixels(self, img, color):
        px = img.load()
        return [(x, y) for y in range(500) for x in range(500)
                if px[x, y][:3] == color]

    def test_strike_face_lands_on_tip(self):
        hand = (150, 150)
        tip = hammer_head_position(hand, 1, 560.0)
        img = self._draw(hand, tip)
        metal = self._pixels(img, _GEOMETRY_SLOT_FILLS["metal"])
        self.assertTrue(metal)
        best = min(math.dist(p, tip) for p in metal)
        self.assertLessEqual(best, 5.0)

    def test_head_lands_on_tip_facing_left(self):
        hand = (350, 150)
        tip = hammer_head_position(hand, -1, 560.0)
        img = self._draw(hand, tip)
        metal = self._pixels(img, _GEOMETRY_SLOT_FILLS["metal"])
        best = min(math.dist(p, tip) for p in metal)
        self.assertLessEqual(best, 5.0)

    def test_handle_spans_hand_to_tip(self):
        hand = (150, 150)
        tip = hammer_head_position(hand, 1, 560.0)
        img = self._draw(hand, tip)
        wood = self._pixels(img, _GEOMETRY_SLOT_FILLS["wood"])
        mid = ((hand[0] + tip[0]) / 2.0, (hand[1] + tip[1]) / 2.0)
        best = min(math.dist(p, mid) for p in wood)
        self.assertLessEqual(best, 8.0)

    def test_carry_angle_tip_draws_cocked_head(self):
        # The carry angle puts the head up-back of the hand; the
        # articulated draw follows the tip wherever it points.
        hand = (250, 250)
        tip = hammer_head_position(hand, 1, 560.0, -2.09)
        img = self._draw(hand, tip)
        metal = self._pixels(img, _GEOMETRY_SLOT_FILLS["metal"])
        best = min(math.dist(p, tip) for p in metal)
        self.assertLessEqual(best, 5.0)
        self.assertLess(tip[1], hand[1])

    def test_no_tip_keeps_footprint_draw(self):
        # The footprint draw is unchanged by the refactor: the
        # metal extent must equal the spec's scaled geometry
        # (grip-anchored, so the bound is the spec extent from
        # the grip, not half the footprint) plus the outline.
        from ai_clip_studio.prop_system import geometry_for_prop
        spec = geometry_for_prop(
            {"kind": "hammer", "length_px": 200.0, "size_px": 170.0})
        x0, y0, x1, y1 = spec["bbox"]
        scale = min(110.0 / max(x1 - x0, 1.0),
                    110.0 / max(y1 - y0, 1.0))
        gx, gy = spec["contact_points"]["grip"]
        head = next(pt for pt in spec["parts"]
                    if pt["name"] == "head")
        extent = max(
            max(abs(px - gx), abs(py - gy))
            for (px, py) in head["points"]) * scale + 3.0
        img = Image.new("RGB", (500, 500), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        _draw_prop(draw, 250, 250, kind="hammer")
        metal = self._pixels(img, _GEOMETRY_SLOT_FILLS["metal"])
        self.assertTrue(metal)
        for (x, y) in metal:
            self.assertLessEqual(abs(x - 250), extent + 1.0)
            self.assertLessEqual(abs(y - 250), extent + 1.0)

    def test_degenerate_tip_falls_back_without_crash(self):
        img = self._draw((250, 250), (250, 250))
        metal = self._pixels(img, _GEOMETRY_SLOT_FILLS["metal"])
        self.assertTrue(metal)

    def test_strike_angle_constant_unchanged(self):
        self.assertAlmostEqual(HAMMER_GRIP_ANGLE_RAD, 1.25)


if __name__ == "__main__":
    unittest.main()


class TestStrikerStaging(unittest.TestCase):
    """Round-5 staging: a HAMMER_STRIKE actor stages beside the
    anvil element at the anvil's depth, facing it."""

    def test_striker_stages_beside_anvil(self):
        import json
        import tempfile
        from pathlib import Path
        from ai_clip_studio.action_compiler import compile_actions
        from ai_clip_studio.product_renderer import (
            _render_shot, plan_shots)
        from ai_clip_studio.studio_script_v1 import (
            parse_studio_script_v1)
        from ai_clip_studio.studio_script_v1_adapter import (
            adapt_document)

        root = Path(__file__).resolve().parents[2]  # agent/
        script = (root / "examples"
                  / "loop_test_01_fire_stone.studio.md").read_text(
                      encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(script))
        # Fixed line durations: the strike shot must exist with the
        # same segmentation the production job produced.
        lines = [{"line_index": i, "duration": d} for i, d in
                 enumerate((6.65, 6.12, 6.79, 3.91, 3.31, 4.92, 5.95))]
        shots = plan_shots(package, lines)
        for i, s in enumerate(shots):
            s["index"] = i
        spans = {s["directive_shot_id"]: (
            s["start_sec"], s["start_sec"] + s["duration"])
            for s in shots if s.get("directive_shot_id")}
        events, unsupported = compile_actions(
            package, timeline={"spans": spans})
        package["compiled_actions"] = {
            "events": events, "unsupported": unsupported,
            "spans_supplied": True, "compile_error": None}
        strike = next(
            e for e in events
            if (e.get("required_pose") or {}).get("primitive")
            == "hammer_strike")
        target = next(
            s for s in shots
            if s.get("directive_shot_id") == strike["shot_id"]
            and s["start_sec"] <= strike["start_time"]
            < s["start_sec"] + s["duration"])
        with tempfile.TemporaryDirectory() as tmp:
            res = _render_shot({"shot": target, "package": package,
                                "out_dir": tmp})
        staging = res["anvil_staging"]
        self.assertIn("Linh", staging)
        x, z, side = staging["Linh"]
        # Forge anvil_top centre is (0.6, 0.78, -3.2); Linh stages
        # 0.9 to its left, at its depth, facing it (side -1).
        self.assertAlmostEqual(x, -0.3)
        self.assertAlmostEqual(z, -3.2)
        self.assertEqual(side, -1.0)
