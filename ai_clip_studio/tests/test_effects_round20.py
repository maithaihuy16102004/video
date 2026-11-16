"""Round 20 (effects richness): secondary bursts, per-streak
variety, debris variety, animated smoke, impact ring + speed
lines (the last two are render tests on Loop 01 #3).
"""
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.environment_v2 import (
    _SECONDARY_BURST_LIFETIME, _SPARK_BURST_LIFETIME, _draw_debris,
    _draw_smoke, _draw_sparks, _burst_streak_styles, burst_positions,
    smoke_positions)
from ai_clip_studio.product_renderer import _render_shot
from ai_clip_studio.renderer25d.camera import PerspectiveCamera
from ai_clip_studio.tests.test_burst_round9 import _delivered_shot


def _cam():
    return PerspectiveCamera(position=(0.0, 2.0, 4.8),
                             target=(0.0, 1.2, 0.0))


def _sparks_el(**extra):
    base = {"spark_count": 14, "spark_seed": 20261112,
            "spark_lifetime": 18}
    base.update(extra)
    return {"id": "anvil_sparks", "center": (0.6, 0.95, -3.2),
            "size": (1.2, 0.9, 0.5), "extra": base}


def _smoke_el(**extra):
    base = {"smoke_count": 5, "smoke_lifetime": 48}
    base.update(extra)
    return {"id": "forge_smoke", "center": (-3.2, 4.7, -6.5),
            "size": (1.4, 0.9, 0.8), "color": (120, 112, 104),
            "extra": base}


def _mean_speed(positions):
    return sum(math.sqrt(sum(v * v for v in vel))
               for (_p, _a, vel) in positions) / len(positions)


class TestSecondaryBurst(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(
            burst_positions(_sparks_el(), 3, 1, secondary=True),
            burst_positions(_sparks_el(), 3, 1, secondary=True))

    def test_defaults_to_six_slower_lower_wider(self):
        prim = burst_positions(_sparks_el(), 4, 0)
        sec = burst_positions(_sparks_el(), 4, 0, secondary=True)
        self.assertEqual(len(prim), 12)
        self.assertEqual(len(sec), 6)
        self.assertLess(_mean_speed(sec), _mean_speed(prim))
        mean_vy = lambda ps: sum(v[1] for (_p, _a, v) in ps) / len(ps)
        self.assertLess(mean_vy(sec), mean_vy(prim))
        mean_vx = lambda ps: sum(abs(v[0]) for (_p, _a, v) in ps) / len(ps)
        self.assertGreater(mean_vx(sec), mean_vx(prim))

    def test_distinct_from_primary(self):
        prim = burst_positions(_sparks_el(), 4, 0)
        sec = burst_positions(_sparks_el(), 4, 0, secondary=True)
        self.assertNotEqual([p for p, _a, _v in prim],
                            [p for p, _a, _v in sec])

    def test_dead_outside_window(self):
        # Round 21: the secondary lives 24 frames (it renders as
        # embers that outlive the 12-frame primary), not 12.
        self.assertEqual(
            burst_positions(_sparks_el(), _SECONDARY_BURST_LIFETIME,
                            0, secondary=True), [])
        self.assertEqual(
            burst_positions(_sparks_el(), -1, 0, secondary=True), [])
        self.assertEqual(
            len(burst_positions(_sparks_el(), 18, 0,
                                secondary=True)), 6)


class TestBurstStreakStyles(unittest.TestCase):
    def test_spread_within_a_burst(self):
        styles = _burst_streak_styles(
            burst_positions(_sparks_el(), 3, 0))
        self.assertEqual(len(styles), 12)
        boosts = {s[1] for s in styles}
        self.assertEqual(boosts, {0, 1})
        dots = [s[2] for s in styles]
        self.assertTrue(any(dots))
        self.assertTrue(any(not d for d in dots))
        mults = [s[0] for s in styles]
        self.assertGreater(max(mults) - min(mults), 0.3)

    def test_deterministic_and_empty(self):
        pos = burst_positions(_sparks_el(), 3, 0)
        self.assertEqual(_burst_streak_styles(pos),
                         _burst_streak_styles(pos))
        self.assertEqual(_burst_streak_styles([]), [])


class TestBurstCanvas(unittest.TestCase):
    def _canvas(self, burst_age, strike_index):
        img = Image.new("RGB", (640, 360), (20, 20, 24))
        el = _sparks_el(burst_age_frames=burst_age,
                        burst_strike_index=strike_index,
                        debris_age_frames=burst_age,
                        debris_strike_index=strike_index)
        _draw_sparks(img, ImageDraw.Draw(img, "RGBA"), el, _cam(),
                     None, 640, 360, spark_frame=burst_age)
        return np.asarray(img).astype(int)

    def test_strikes_differ(self):
        a = self._canvas(3, 0)
        b = self._canvas(3, 1)
        self.assertFalse(np.array_equal(a, b))
        self.assertGreater(int((a != b).any(axis=2).sum()), 50)

    def test_secondary_extends_the_burst(self):
        # At age 8 the primary is nearly cooled; the secondary
        # (born at age 6) keeps bright streaks in the frame.
        a = self._canvas(8, 0)
        hot = (a[:, :, 0] > 240) & (a[:, :, 1] > 170) \
            & (a[:, :, 2] < 200)
        self.assertGreater(int(hot.sum()), 30)


class TestDebrisVariety(unittest.TestCase):
    def test_radius_boost_changes_size(self):
        # Airborne (no floor glow): the hot core dot alone.
        def count(boost):
            img = Image.new("RGB", (640, 360), (20, 20, 24))
            _draw_debris(img, ImageDraw.Draw(img, "RGBA"), _cam(),
                         (0.6, 0.5, -3.2), 0.1, False, 640, 360,
                         radius_boost=boost)
            a = np.asarray(img).astype(int)
            core = (a[:, :, 0] > 240) & (a[:, :, 1] > 200) \
                & (a[:, :, 2] > 120)
            return int(core.sum())
        self.assertLess(count(0), count(2))

    def test_cool_scale_keeps_fragments_hot(self):
        def colour(scale):
            img = Image.new("RGB", (640, 360), (20, 20, 24))
            _draw_debris(img, ImageDraw.Draw(img, "RGBA"), _cam(),
                         (0.6, 0.5, -3.2), 0.8, False, 640, 360,
                         cool_scale=scale)
            a = np.asarray(img).astype(int)
            x, y, _, _ = _cam().project((0.6, 0.5, -3.2), 640, 360)
            return tuple(a[int(y), int(x)])
        hot = colour(0.7)
        cool = colour(1.0)
        self.assertGreater(sum(hot), sum(cool))


class TestSmokePositions(unittest.TestCase):
    def test_deterministic(self):
        el = _smoke_el()
        self.assertEqual(smoke_positions(el, 10),
                         smoke_positions(el, 10))

    def test_rises_expands_and_fades(self):
        el = _smoke_el()
        first = smoke_positions(el, 0)
        later = smoke_positions(el, 24)
        mean_y = lambda ps: sum(p[1] for p, _a, _r, _al in ps) / len(ps)
        mean_r = lambda ps: sum(r for _p, _a, r, _al in ps) / len(ps)
        self.assertGreater(mean_y(later), mean_y(first))
        self.assertGreater(mean_r(later), mean_r(first))

    def test_aperiodic(self):
        el = _smoke_el()
        self.assertNotEqual(smoke_positions(el, 0),
                            smoke_positions(el, 48))

    def test_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            smoke_positions(_smoke_el(smoke_count=-1), 0)
        with self.assertRaises(ValueError):
            smoke_positions(_smoke_el(), -1)


class TestSmokeCanvas(unittest.TestCase):
    def _canvas(self, frame):
        # Camera pitched up to frame the chimney plume.
        cam = PerspectiveCamera(position=(0.0, 2.0, 4.8),
                                target=(0.0, 3.5, -3.0))
        img = Image.new("RGB", (640, 360), (30, 28, 26))
        _draw_smoke(img, ImageDraw.Draw(img, "RGBA"), _smoke_el(),
                    cam, 640, 360, frame=frame)
        return np.asarray(img).astype(int)

    def test_smoke_draws_above_chimney_and_moves(self):
        # Translucent smoke lifts the background toward grey;
        # measure the lift, not an absolute colour.
        a = self._canvas(24)
        lift = (a[:, :, 0].astype(int) - 30) > 12
        self.assertGreater(int(lift.sum()), 200)
        b = self._canvas(0)
        self.assertFalse(np.array_equal(a, b))


class TestStrikeRender(unittest.TestCase):
    """Loop 01 #3, delivered render: smoke animates, the impact
    ring fires at contact, speed lines trail the downswing.

    The shot has ONE strike (single 0.9 s cycle in a 1.27 s
    span): contact at shot-local 0.76 s = frame 18.3, so the
    ring fires at f19-20 and the STRIKE-phase speed lines at
    f18. All ROIs derive from the sparks element's projected
    screen position (camera spy + crop map), never fixed
    coordinates."""

    @classmethod
    def setUpClass(cls):
        import ai_clip_studio.product_renderer as pr
        from unittest import mock
        package, shot = _delivered_shot(3)
        cls.package, cls.shot = package, shot
        cls.tmp = tempfile.TemporaryDirectory()
        caps = {}
        orig = pr.render_environment

        def spy(pkg, cam, size, **kw):
            caps.setdefault("cam", cam)
            caps.setdefault("pkg", pkg)
            return orig(pkg, cam, size, **kw)

        with mock.patch.object(pr, "render_environment", spy):
            cls.result = _render_shot(
                {"shot": shot, "package": package,
                 "out_dir": cls.tmp.name, "still_only": False})
        cls.out = Path(cls.tmp.name) / "shot_003"
        rect = cls.result["crop_anchor"]["crop_rect"]
        scale = 1920.0 / (rect[2] - rect[0])
        sparks = next(e for e in caps["pkg"]["elements"]
                      if e.get("kind") == "sparks")
        sx, sy, _, _ = caps["cam"].project(sparks["center"],
                                           1920, 1080)
        cls.ssx = (sx - rect[0]) * scale
        cls.ssy = (sy - rect[1]) * scale

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _frame(self, fi):
        return np.asarray(Image.open(
            self.out / f"f{fi:04d}.png").convert("RGB")).astype(int)

    def test_smoke_present(self):
        # Counterfactual stills: identical except the smoke
        # draw. The plume must paint a visible region.
        import ai_clip_studio.product_renderer as pr
        from unittest import mock

        def still(patch):
            with tempfile.TemporaryDirectory() as tmp:
                with patch:
                    _render_shot(
                        {"shot": self.shot, "package": self.package,
                         "out_dir": tmp, "still_only": True})
                return np.asarray(Image.open(
                    Path(tmp) / "shot_003" / "still.png"
                    ).convert("RGB")).astype(int)

        off = still(mock.patch.object(
            pr, "_draw_smoke", lambda *a, **k: None))
        on = still(mock.patch.object(pr, "_draw_smoke",
                                     pr._draw_smoke))
        diff = np.abs(on.astype(int) - off.astype(int)).sum(axis=2)
        self.assertGreater(int((diff > 0).sum()), 10000)

    def test_smoke_varies_across_frames(self):
        # Plume ROI (left edge, chimney column): the wall is
        # static, so brightness variation is the smoke alone.
        def mean(fi):
            return float(self._frame(fi)[40:250, 0:160].mean())
        means = [mean(fi) for fi in (0, 24, 48, 72)]
        self.assertGreater(max(means) - min(means), 5.0)

    def _ring_and_corridor(self, fi):
        a = self._frame(fi)
        white = (a[:, :, 0] > 245) & (a[:, :, 1] > 240) \
            & (a[:, :, 2] > 220)
        pale = (a[:, :, 0] > 240) & (a[:, :, 1] > 235) \
            & (a[:, :, 2] > 210)
        yy, xx = np.mgrid[0:1080, 0:1920]
        dist = np.sqrt((xx - self.ssx) ** 2
                       + ((yy - self.ssy) / 0.62) ** 2)
        # Lower half of the ring band only: burst streaks fly
        # UP, so only the ring/star paints below the contact.
        lower = (dist >= 10) & (dist <= 48) & (yy > self.ssy)
        corridor = np.zeros((1080, 1920), bool)
        corridor[int(max(0, self.ssy - 320)):int(self.ssy) + 10,
                 int(max(0, self.ssx - 120)):
                 int(self.ssx) + 120] = True
        corridor &= ~((dist >= 10) & (dist <= 48))
        return int((white & lower).sum()), int((pale & corridor).sum())

    def test_impact_ring_at_contact_only(self):
        contact = max(self._ring_and_corridor(19)[0],
                      self._ring_and_corridor(20)[0])
        off = max(self._ring_and_corridor(6)[0],
                  self._ring_and_corridor(30)[0],
                  self._ring_and_corridor(48)[0])
        self.assertGreater(contact, 200)
        self.assertLess(off, 50)

    def test_speed_lines_in_strike_window_only(self):
        strike = self._ring_and_corridor(18)[1]
        off = max(self._ring_and_corridor(6)[1],
                  self._ring_and_corridor(30)[1])
        self.assertGreater(strike, 300)
        self.assertLess(off, 100)


if __name__ == "__main__":
    unittest.main()
