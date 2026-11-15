"""Round-7 bystander clearance (R6-D1): a bystander whose head sits
inside an acting character's hand-sweep disc gets pushed laterally
until clear, held props over another character's face are audited
per frame, and the drawn hammer head snaps to the anvil top at the
contact instant.

The R6 draft's worst single visual was the hammer parking on the
watcher's face for 1.7 s in the forge shot: the striker stood
behind the bystander and the presenting hand rose through the
bystander's head. The clearance pass, the intrusion audit, and the
contact snap close that defect class.
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import (
    _discs_clear,
    _head_disc,
    _prop_intrudes_head,
    _render_shot,
    _sweep_disc,
    plan_shots,
)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _loop01_package_and_shots():
    text = (EXAMPLES / "loop_test_01_fire_stone.studio.md").read_text(
        encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(7)])
    for i, s in enumerate(shots):
        s["index"] = i
    spans = {}
    clock = 0.0
    for s in shots:
        did = s.get("directive_shot_id")
        if did:
            span = spans.setdefault(str(did), [clock, clock])
            span[1] = clock + float(s["duration"])
        clock += float(s["duration"])
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None,
    }
    return package, shots


class TestSweepDiscGeometry(unittest.TestCase):
    def test_disc_fractions(self):
        cx, cy, r = _sweep_disc(1000.0, 900.0, 800.0)
        self.assertAlmostEqual(cx, 1000.0)
        self.assertAlmostEqual(cy, 900.0 - 0.72 * 800.0)
        self.assertAlmostEqual(r, 0.60 * 800.0)
        hx, hy, hr = _head_disc(1000.0, 900.0, 800.0)
        self.assertAlmostEqual(hx, 1000.0)
        self.assertAlmostEqual(hy, 900.0 - 0.83 * 800.0)
        self.assertAlmostEqual(hr, 0.17 * 800.0)

    def test_discs_clear_threshold(self):
        a = (0.0, 0.0, 100.0)
        # Centres 250 apart, radii sum 180: clear even with margin.
        self.assertTrue(_discs_clear(a, (250.0, 0.0, 80.0)))
        self.assertTrue(_discs_clear(a, (250.0, 0.0, 80.0), 10.0))
        # Centres 190 apart: clear without margin, not with 20.
        self.assertTrue(_discs_clear(a, (190.0, 0.0, 80.0)))
        self.assertFalse(_discs_clear(a, (190.0, 0.0, 80.0), 20.0))
        # Overlapping discs never clear.
        self.assertFalse(_discs_clear(a, (100.0, 0.0, 80.0)))

    def test_r6_geometry_intrudes_before_push(self):
        # f50 measurements: Linh sweep disc vs Ong Ba head disc.
        sweep = _sweep_disc(720.0, 600.0, 663.0)
        head = _head_disc(955.0, 830.0, 690.0)
        self.assertFalse(_discs_clear(sweep, head, 0.05 * 663.0))
        # A 300 px lateral push clears it.
        moved = _head_disc(1255.0, 830.0, 690.0)
        self.assertTrue(_discs_clear(sweep, moved, 0.05 * 663.0))


class TestPropIntrudesHead(unittest.TestCase):
    def test_inside_disc_intrudes(self):
        # The A/B probe's frame-10 hammer tip: 45.4 px from the head
        # centre, head_r 119.7.
        self.assertTrue(_prop_intrudes_head(
            (45.4, 0.0), (0.0, 0.0), 119.7, 700.0))

    def test_outside_disc_with_margin_clear(self):
        self.assertFalse(_prop_intrudes_head(
            (300.0, 0.0), (0.0, 0.0), 119.7, 700.0))

    def test_margin_zone_intrudes(self):
        # 130 px out: outside head_r (119.7) but inside the 0.05H
        # margin band (119.7 + 35 = 154.7).
        self.assertTrue(_prop_intrudes_head(
            (130.0, 0.0), (0.0, 0.0), 119.7, 700.0))

    def test_zero_head_radius_never_intrudes(self):
        self.assertFalse(_prop_intrudes_head(
            (0.0, 0.0), (0.0, 0.0), 0.0, 700.0))


class TestHammerShotClearance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package, shots = _loop01_package_and_shots()
        cls.shot = next(
            s for s in shots
            if s.get("directive_shot_id") == "SC02_SH02")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.result = _render_shot({
            "shot": cls.shot, "package": package,
            "out_dir": Path(cls._tmp.name), "still_only": False})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_bystander_pushed_clear(self):
        rec = self.result["bystander_clearance"]
        self.assertIsNone(rec["skipped"])
        moved = rec["moved"]
        self.assertIn("Ông Ba", moved)
        self.assertTrue(moved["Ông Ba"]["cleared"])
        self.assertFalse(moved["Ông Ba"]["margin_blocked"])
        self.assertGreater(moved["Ông Ba"]["steps"], 0)
        self.assertIn("Linh", moved["Ông Ba"]["actors"])

    def test_no_head_intrusions(self):
        self.assertEqual(self.result["head_intrusion_count"], 0)
        self.assertEqual(self.result["head_intrusions"], [])

    def test_contact_snap_fired(self):
        snaps = self.result["hammer_contact_snaps"]
        self.assertGreaterEqual(len(snaps), 1)
        for snap in snaps:
            self.assertGreater(snap["extension_px"], 0.0)
            self.assertLessEqual(snap["extension_px"], 60.0)


if __name__ == "__main__":
    unittest.main()
