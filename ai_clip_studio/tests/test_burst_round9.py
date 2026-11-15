"""Round 9 (R7-D4 residual): a flying spark burst at contact, and the
ambient field's exact period-18 loop is broken.

Before: the ambient field repeated every 18 frames (shared lifetime
+ ``(frame - birth) % lifetime``) and the contact reaction was a
glow flash only -- the tester measured streak counts at f20-22
inside the normal cycle range. Now each spark has its own lifetime
in [lifetime-3, lifetime+3] (combined repeat: LCM 15..21), and a
strike fires 12 fast sparks from the anvil contact point that fly
outward for 12 frames, cooling and shrinking as they fade. The
burst age window is its own gate: it never fires without a strike.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

import ai_clip_studio.product_renderer as PR
from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.environment_v2 import (
    _SPARK_BURST_LIFETIME, burst_positions, spark_positions)
from ai_clip_studio.product_renderer import _render_shot
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _sparks_el():
    return {"id": "anvil_sparks", "center": (0.6, 0.95, -3.2),
            "size": (1.2, 0.9, 0.5),
            "extra": {"spark_count": 14, "spark_seed": 20261112,
                      "spark_lifetime": 18}}


def _delivered_shot(index):
    text = (EXAMPLES / "loop_test_01_fire_stone.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    timeline = json.loads(
        (JOBS / "req_3ee64748a857" / "timeline.json").read_text(
            encoding="utf-8"))
    shots = timeline["shots"]
    starts = {}
    clock = 0.0
    for s in shots:
        starts[id(s)] = clock
        clock += float(s["duration"])
    spans = {}
    for s in shots:
        did = s.get("directive_shot_id")
        if did:
            st = starts[id(s)]
            span = spans.setdefault(str(did), [st, st])
            span[1] = max(span[1], st + float(s["duration"]))
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    shot = dict(shots[index])
    shot["index"] = index
    shot["start_sec"] = starts[id(shots[index])]
    return package, shot


class TestAmbientFieldAperiodic(unittest.TestCase):
    def test_no_exact_repeat_at_old_period(self):
        el = _sparks_el()
        f0 = spark_positions(el, 0)
        self.assertNotEqual(f0, spark_positions(el, 18))
        self.assertNotEqual(f0, spark_positions(el, 36))
        self.assertNotEqual(spark_positions(el, 18),
                            spark_positions(el, 36))

    def test_still_deterministic(self):
        el = _sparks_el()
        self.assertEqual(spark_positions(el, 7),
                         spark_positions(el, 7))
        self.assertEqual(len(spark_positions(el, 7)), 14)


class TestBurstPositions(unittest.TestCase):
    def test_born_at_origin_and_spreads(self):
        el = _sparks_el()
        origin = (0.6, 0.95, -3.2)
        at0 = burst_positions(el, 0, 0)
        self.assertEqual(len(at0), 12)
        for pos, frac, _ in at0:
            self.assertAlmostEqual(math.dist(pos, origin), 0.0)
            self.assertEqual(frac, 0.0)
        dists = []
        for age in (3, 6, 11):
            bp = burst_positions(el, age, 0)
            dists.append(sum(math.dist(p, origin) for p, _, _ in bp)
                         / len(bp))
        self.assertLess(dists[0], dists[1])
        self.assertLess(dists[1], dists[2])
        self.assertGreater(dists[2], 1.0)

    def test_dead_at_lifetime_and_deterministic(self):
        el = _sparks_el()
        self.assertEqual(
            burst_positions(el, _SPARK_BURST_LIFETIME, 0), [])
        self.assertEqual(burst_positions(el, 6, 0),
                         burst_positions(el, 6, 0))

    def test_strikes_differ(self):
        el = _sparks_el()
        self.assertNotEqual(burst_positions(el, 6, 0),
                            burst_positions(el, 6, 1))


class TestBurstFiresAtContact(unittest.TestCase):
    """Spy on _draw_sparks over delivered shot #3: burst_age_frames
    appears only within 12 frames after a strike moment."""

    @classmethod
    def setUpClass(cls):
        cls.calls = []
        real = PR._draw_sparks

        def _spy(img, draw, el, camera, rig, width, height,
                 spark_frame=0):
            extra = el.get("extra") or {}
            cls.calls.append(extra.get("burst_age_frames"))
            return real(img, draw, el, camera, rig, width, height,
                        spark_frame)

        package, shot = _delivered_shot(3)
        cls.tmp = tempfile.TemporaryDirectory()
        prev = PR._draw_sparks
        PR._draw_sparks = _spy
        try:
            cls.result = _render_shot(
                {"shot": shot, "package": package,
                 "out_dir": cls.tmp.name, "still_only": False})
        finally:
            PR._draw_sparks = prev

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_burst_window_covers_contact_frames(self):
        # Contact is at f20-22 (hammer reaches the workpiece f18-19).
        for fi in (20, 21, 22):
            self.assertIsNotNone(
                self.calls[fi], f"frame {fi}: no burst at contact")

    def test_no_burst_before_first_strike(self):
        for fi in range(0, 10):
            self.assertIsNone(
                self.calls[fi], f"frame {fi}: burst without a strike")

    def test_burst_ages_run_0_to_11(self):
        ages = [c for c in self.calls if c is not None]
        self.assertTrue(ages)
        self.assertEqual(min(ages), 0)
        self.assertLess(max(ages), _SPARK_BURST_LIFETIME)


class TestBurstPixels(unittest.TestCase):
    """Delivered shot #3 frames: the contact window carries far more
    streak pixels than the ambient field ever does, and the streak
    pattern never repeats at the old 18-frame period."""

    @classmethod
    def setUpClass(cls):
        package, shot = _delivered_shot(3)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = _render_shot(
            {"shot": shot, "package": package,
             "out_dir": cls.tmp.name, "still_only": False})
        cls.out = Path(cls.tmp.name) / "shot_003"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _streak_set(self, fi):
        a = np.asarray(Image.open(
            self.out / f"f{fi:04d}.png").convert("RGB")).astype(int)
        roi = a[700:800, 400:600]
        m = (roi[:, :, 0] > 240) & (roi[:, :, 1] > 170) \
            & (roi[:, :, 2] < 200)
        return set(map(tuple, np.argwhere(m)))

    def test_contact_window_exceeds_ambient_range(self):
        ambient = max(len(self._streak_set(fi))
                      for fi in range(2, 11))
        for fi in (20, 21, 22):
            self.assertGreater(
                len(self._streak_set(fi)), ambient,
                f"frame {fi}: burst must exceed the ambient range")

    def test_no_period_18_repeat(self):
        for fi in range(6, 18):
            self.assertNotEqual(self._streak_set(fi),
                                self._streak_set(fi + 18),
                                f"f{fi} == f{fi + 18}: loop persists")


class TestInsertHasNoBurst(unittest.TestCase):
    """Delivered shot #4 (object_insert, no strikes): no burst key
    on any frame -- the burst never fires without a strike."""

    @classmethod
    def setUpClass(cls):
        cls.calls = []
        real = PR._draw_sparks

        def _spy(img, draw, el, camera, rig, width, height,
                 spark_frame=0):
            cls.calls.append(
                (el.get("extra") or {}).get("burst_age_frames"))
            return real(img, draw, el, camera, rig, width, height,
                        spark_frame)

        package, shot = _delivered_shot(4)
        cls.tmp = tempfile.TemporaryDirectory()
        prev = PR._draw_sparks
        PR._draw_sparks = _spy
        try:
            cls.result = _render_shot(
                {"shot": shot, "package": package,
                 "out_dir": cls.tmp.name, "still_only": False})
        finally:
            PR._draw_sparks = prev

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_burst_frames(self):
        self.assertTrue(self.calls)
        self.assertTrue(all(c is None for c in self.calls))


if __name__ == "__main__":
    unittest.main()
