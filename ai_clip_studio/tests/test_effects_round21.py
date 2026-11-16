"""Round 21 (effects completion): the secondary burst renders as
embers with its own 24-frame lifetime, and debris fragments vary
widely enough to survive measurement in the ground window.

Tester R20: the secondary drew identical streaks in identical
colours on the primary's tail (no wider/lower signature -- only
a density excess), and the debris steps (1 px, 0.1) were swamped
by the uniform landed glow (ground-window distributions
overlapped). These tests pin the round-21 identities: embers
are round dots that persist after the primary dies; debris
sizes spread widely within one burst.
"""
import unittest

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from ai_clip_studio.environment_v2 import (
    _SECONDARY_BURST_LIFETIME, _SPARK_BURST_LIFETIME, _debris_style,
    _draw_debris, _draw_sparks, _ember_radii, burst_positions)
from ai_clip_studio.tests.test_effects_round20 import _cam, _sparks_el


def _spark_mask(a):
    return ((a[:, :, 0] > 200) & (a[:, :, 1] > 90)
            & (a[:, :, 1] < 210) & (a[:, :, 2] < 120))


def _components(a, min_area=4):
    lab, n = ndimage.label(_spark_mask(a))
    out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if len(xs) < min_area:
            continue
        out.append((len(xs), int(xs.max() - xs.min() + 1),
                    int(ys.max() - ys.min() + 1)))
    return out


def _canvas(**extra):
    img = Image.new("RGB", (640, 360), (20, 20, 24))
    el = _sparks_el(spark_count=0, **extra)
    age = extra.get("burst_age_frames",
                    extra.get("debris_age_frames", 0))
    _draw_sparks(img, ImageDraw.Draw(img, "RGBA"), el, _cam(),
                 None, 640, 360, spark_frame=age)
    return np.asarray(img).astype(int)


class TestSecondaryLifetime(unittest.TestCase):
    def test_primary_lifetime_unchanged(self):
        self.assertEqual(len(burst_positions(_sparks_el(), 11, 0)), 12)
        self.assertEqual(
            burst_positions(_sparks_el(), _SPARK_BURST_LIFETIME, 0), [])

    def test_secondary_outlives_primary(self):
        for age in (12, 18, 23):
            self.assertEqual(
                len(burst_positions(_sparks_el(), age, 0,
                                    secondary=True)), 6, age)

    def test_secondary_dead_at_own_lifetime(self):
        self.assertEqual(
            burst_positions(_sparks_el(), _SECONDARY_BURST_LIFETIME,
                            0, secondary=True), [])
        self.assertEqual(_SECONDARY_BURST_LIFETIME, 24)

    def test_secondary_age_frac_uses_own_lifetime(self):
        pos = burst_positions(_sparks_el(), 12, 0, secondary=True)
        self.assertAlmostEqual(pos[0][1], 0.5)


class TestEmberCanvas(unittest.TestCase):
    def test_embers_persist_after_primary_dies(self):
        # Burst age 20: primary dead (12), secondary age 14.
        # Round dots only; nothing left at age 30 (dead at 24).
        comps = _components(_canvas(burst_age_frames=20,
                                    burst_strike_index=0))
        self.assertTrue(any(area >= 25 for area, _w, _h in comps),
                        comps)
        for area, w, h in comps:
            self.assertLess(max(w, h) / min(w, h), 1.6)
        self.assertEqual(_components(_canvas(burst_age_frames=30,
                                             burst_strike_index=0)),
                         [])

    def test_ember_radii_spread(self):
        radii = _ember_radii(
            burst_positions(_sparks_el(), 4, 0, secondary=True), 1920)
        self.assertEqual(len(radii), 6)
        self.assertLess(min(radii), max(radii))
        self.assertEqual(radii, _ember_radii(
            burst_positions(_sparks_el(), 4, 0, secondary=True), 1920))
        self.assertEqual(_ember_radii([], 1920), [])


class TestDebrisStyle(unittest.TestCase):
    def test_wide_spread_within_one_burst(self):
        styles = [_debris_style(i, 0) for i in range(12)]
        self.assertEqual({b for b, _c in styles}, {0, 2, 4})
        self.assertEqual({c for _b, c in styles},
                         {0.5, 0.75, 1.0, 1.25})

    def test_shifted_across_strikes(self):
        self.assertNotEqual([_debris_style(i, 0) for i in range(6)],
                            [_debris_style(i, 1) for i in range(6)])


class TestDebrisCanvas(unittest.TestCase):
    def test_ground_window_size_spread(self):
        # Debris age 20, ambient off: several components whose
        # areas spread widely (measured 13..172 on this canvas).
        comps = _components(_canvas(debris_age_frames=20,
                                    debris_strike_index=0))
        areas = [area for area, _w, _h in comps]
        self.assertGreaterEqual(len(areas), 3, comps)
        self.assertGreater(max(areas) / min(areas), 5.0, comps)

    def test_landed_glow_scales_with_fragment(self):
        def glow_bbox(boost):
            img = Image.new("RGB", (640, 360), (20, 20, 24))
            _draw_debris(img, ImageDraw.Draw(img, "RGBA"), _cam(),
                         (0.6, 0.5, -3.2), 0.1, True, 640, 360,
                         radius_boost=boost)
            a = np.asarray(img).astype(int)
            diff = (np.abs(a - np.array([20, 20, 24])).sum(axis=2)
                    > 30)
            ys, xs = np.nonzero(diff)
            return int(xs.max() - xs.min() + 1), int(diff.sum())
        small = glow_bbox(0)
        big = glow_bbox(4)
        self.assertGreater(big[0], 2 * small[0])
        self.assertGreater(big[1], 2 * small[1])


class TestStrikeRenderRound21(unittest.TestCase):
    """Loop 01 #3, delivered render: speed lines follow the
    travelling hammer on f16-f18 (the R20 fixed burst corridor
    saw only f18 -- a measurement artifact), and the glow +
    dust pulse lifts the below-contact band for 10 frames
    after contact, then returns to baseline.

    Contact at shot-local 0.76 s = frame 18.3. ROIs derive
    from the sparks projection + the hammer's drawn position
    (spies), never fixed coordinates.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile
        from pathlib import Path
        from unittest import mock
        import ai_clip_studio.product_renderer as pr
        from ai_clip_studio.product_renderer import _render_shot
        from ai_clip_studio.tests.test_burst_round9 import (
            _delivered_shot)
        package, shot = _delivered_shot(3)
        cls.tmp = tempfile.TemporaryDirectory()
        caps = {}
        orig_env = pr.render_environment
        orig_prop = pr._draw_prop
        hammer = []

        def env_spy(pkg, cam, size, **kw):
            caps.setdefault("cam", cam)
            caps.setdefault("pkg", pkg)
            return orig_env(pkg, cam, size, **kw)

        def prop_spy(draw, x, y, kind="wallet", **kw):
            if kind == "hammer":
                hammer.append((float(x), float(y)))
            return orig_prop(draw, x, y, kind=kind, **kw)

        with mock.patch.object(pr, "render_environment", env_spy):
            with mock.patch.object(pr, "_draw_prop",
                                   side_effect=prop_spy):
                cls.result = _render_shot(
                    {"shot": shot, "package": package,
                     "out_dir": cls.tmp.name, "still_only": False})
        cls.out = Path(cls.tmp.name) / "shot_003"
        cls.n_frames = len(list(cls.out.glob("f*.png")))
        # One hammer draw per frame: the spy order IS the
        # frame order. Fail loudly if that ever stops holding.
        assert len(hammer) == cls.n_frames, (
            len(hammer), cls.n_frames)
        cls.hammer = hammer
        rect = cls.result["crop_anchor"]["crop_rect"]
        cls.rect = rect
        cls.scale = 1920.0 / (rect[2] - rect[0])
        sparks = next(e for e in caps["pkg"]["elements"]
                      if e.get("kind") == "sparks")
        sx, sy, _, _ = caps["cam"].project(sparks["center"],
                                           1920, 1080)
        cls.ssx = (sx - rect[0]) * cls.scale
        cls.ssy = (sy - rect[1]) * cls.scale

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _frame(self, fi):
        return np.asarray(Image.open(
            self.out / f"f{fi:04d}.png").convert("RGB")).astype(int)

    def _hammer_trail_count(self, fi):
        sx, sy = self.hammer[fi]
        dx = (sx - self.rect[0]) * self.scale
        dy = (sy - self.rect[1]) * self.scale
        a = self._frame(fi)
        roi = a[max(0, int(dy - 150)):int(dy + 10),
                max(0, int(dx - 60)):int(dx + 60)]
        nearwhite = ((roi[:, :, 0] > 235) & (roi[:, :, 1] > 235)
                     & (roi[:, :, 2] > 215))
        face = (np.abs(roi - np.array([247, 243, 232])).sum(axis=2)
                < 18)
        return int((nearwhite & ~face).sum())

    def test_speed_lines_follow_hammer_on_f16_f17_f18(self):
        # Measured post-strengthening: 595 / 498 / 931.
        for fi in (16, 17, 18):
            self.assertGreater(self._hammer_trail_count(fi), 300,
                               fi)
        for fi in (14, 19, 30):
            self.assertLess(self._hammer_trail_count(fi), 50, fi)

    def _tan_lift(self, fi):
        a = self._frame(fi)
        band = a[int(self.ssy + 10):int(self.ssy + 140),
                 int(self.ssx - 120):int(self.ssx + 120)]
        tan = ((band[:, :, 0] >= 90) & (band[:, :, 0] <= 200)
               & (band[:, :, 1] >= 70) & (band[:, :, 1] <= 170)
               & (band[:, :, 2] >= 50) & (band[:, :, 2] <= 130)
               & ((band[:, :, 0] - band[:, :, 2]) > 15))
        return int(tan.sum())

    def test_glow_dust_pulse_after_contact(self):
        # Measured: f21 2142 (peak), f22 1633, f24 959;
        # baseline f06/f28/f48 ~533-552.
        self.assertGreater(self._tan_lift(21), 1500)
        self.assertLess(self._tan_lift(6), 800)
        self.assertLess(self._tan_lift(28), 800)


if __name__ == "__main__":
    unittest.main()
