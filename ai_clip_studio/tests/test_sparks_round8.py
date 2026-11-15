"""Round-8 sparks (R7-D4): the anvil spark field animates every
frame instead of freezing at frame 0, while the strike burst
stays gated to contact frames.

Before: the sparks element baked into the static background at
``spark_frame=0``, so the streaks were pixel-identical for the
whole shot (the tester measured a constant 48 px texture) and
only the glow flash moved. Now the element is excluded from
both static layers and drawn live in _build_frame at the real
frame index; inside the gated reaction window the count boosts
and the field accelerates, exactly as before.

Frame evidence: r8_delivered_shot3 (delivered R7 shot #3 plan:
streak pixel sets differ on every consecutive pair f0-f90, the
R7 warm mask pulses 714/720/647 px at f20-f22 against a 424-682
ambient range, gone by f23); r8_delivered_shot4 (insert keeps
its streaks under paint_glow=False).
"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

import ai_clip_studio.product_renderer as PR
from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import _render_shot
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
JOBS = Path(__file__).resolve().parents[2] / "jobs"


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
        "spans_supplied": True, "compile_error": None,
    }
    shot = dict(shots[index])
    shot["index"] = index
    shot["start_sec"] = starts[id(shots[index])]
    return package, shot


def _streak_mask(arr):
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    return (r > 240) & (g > 170) & (b < 200)


def _warm_mask(arr):
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    return (r > 200) & (g > 90) & (g < 210) & (b < 120)


class TestSparksAnimateOnPixels(unittest.TestCase):
    """Delivered shot #3 (the strike MCU): the streak field moves
    every frame and the contact pulse still fires."""

    @classmethod
    def setUpClass(cls):
        package, shot = _delivered_shot(3)
        cls.shot = shot
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = _render_shot(
            {"shot": shot, "package": package,
             "out_dir": cls.tmp.name, "still_only": False})
        cls.frames_dir = Path(cls.tmp.name) / "shot_003"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _frame_arr(self, frame):
        path = self.frames_dir / f"f{frame:04d}.png"
        return np.asarray(Image.open(path).convert("RGB")).astype(int)

    def test_shot_is_the_strike_mcu(self):
        self.assertEqual(self.shot.get("directive_shot_id"),
                         "SC02_SH02")
        self.assertEqual(self.shot["shot_type"], "medium_close_up")
        # The pixel regions below are tuned to this frozen crop;
        # the framing test pins the crop, this pins the coupling.
        # R9-8: the accessory-aware camera fit pulls back slightly
        # to clear Linh's bun, shifting the crop 14 px left.
        self.assertEqual(
            self.result["crop_anchor"]["crop_rect"],
            [646, 0, 1846, 675])

    def test_streak_sets_differ_every_frame(self):
        # R7-D4: the streak texture was pixel-identical across
        # frames. The live field must change on every pair.
        prev = None
        for frame in range(0, 11):
            arr = self._frame_arr(frame)
            reg = arr[700:800, 400:600]
            ys, xs = np.nonzero(_streak_mask(reg))
            cur = set(zip(xs.tolist(), ys.tolist()))
            self.assertTrue(len(cur) > 0,
                            f"frame {frame}: no streak pixels")
            if prev is not None:
                self.assertGreater(
                    len(cur ^ prev), 0,
                    f"frames {frame - 1}-{frame}: streaks frozen")
            prev = cur

    def test_contact_pulse_above_ambient(self):
        # The R7 warm mask over the anvil: the strike pulse at
        # f20-f22 must clear the ambient range of f2-f10, and the
        # ambient range itself must vary (no frozen baseline).
        counts = {}
        for frame in list(range(2, 11)) + [20, 21, 22]:
            arr = self._frame_arr(frame)
            reg = arr[740:1000, 380:620]
            counts[frame] = int(_warm_mask(reg).sum())
        ambient = [counts[f] for f in range(2, 11)]
        self.assertGreater(max(ambient), min(ambient),
                           "ambient warm level is constant")
        pulse = [counts[f] for f in (20, 21, 22)]
        self.assertGreater(
            min(pulse), max(ambient),
            f"contact pulse {pulse} does not clear ambient "
            f"{ambient}")

    def test_reaction_record_short_and_strong(self):
        # The burst gating (decay 0.10 s, floor 0.15) is
        # unchanged: a short, strong reaction record.
        recs = [r for r in self.result["effect_records"]
                if r["effect"] == "SET_PIECE_REACTION"]
        self.assertEqual(len(recs), 1)
        # Peak is frame-quantized: the first frame at/after the
        # contact moment lands up to 1/24 s late, so the peak is
        # exp(-dt/0.10) in [0.66, 1.0] -- 0.73 here -- never a
        # clean 1.0. The floor it must clear is the paint floor.
        self.assertGreaterEqual(recs[0]["peak_intensity"], 0.6)
        self.assertLessEqual(recs[0]["frames"], 8)


class TestSparksDrawnLive(unittest.TestCase):
    """Spy on _draw_sparks: one live draw per frame at the real
    frame index, boosted only inside the reaction window."""

    @classmethod
    def setUpClass(cls):
        cls.calls = []
        real = PR._draw_sparks

        def _spy(img, draw, el, camera, rig, width, height,
                 spark_frame=0):
            cls.calls.append({
                "spark_frame": spark_frame,
                "count": int((el.get("extra") or {}).get(
                    "spark_count", 14)),
            })
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

    def test_one_draw_per_frame_at_real_index(self):
        n = self.result["n_frames"]
        self.assertEqual(len(self.calls), n,
                         "sparks must draw once per frame")
        ambient = [c for c in self.calls if c["count"] == 14]
        # The burst is ~4-5 frames of 91; the rest is ambient.
        self.assertGreaterEqual(len(ambient), n - 8)
        for fi, call in enumerate(self.calls):
            if call["count"] == 14:
                self.assertEqual(
                    call["spark_frame"], fi,
                    f"frame {fi}: ambient draw at wrong index")

    def test_burst_boosts_count(self):
        boosted = [c for c in self.calls if c["count"] > 14]
        self.assertTrue(1 <= len(boosted) <= 8,
                        f"burst frames: {len(boosted)}")
        self.assertTrue(all(c["count"] <= 42 for c in boosted),
                        "boosted count exceeds 14 * (1 + 2 * 1.0)")


class TestInsertKeepsSparks(unittest.TestCase):
    """Delivered shot #4 (object_insert, paint_glow=False in pass
    1): the ambient field still draws every frame -- excluding
    the element from the static background must not erase the
    insert's sparks."""

    @classmethod
    def setUpClass(cls):
        cls.calls = []
        real = PR._draw_sparks

        def _spy(img, draw, el, camera, rig, width, height,
                 spark_frame=0):
            cls.calls.append({
                "spark_frame": spark_frame,
                "count": int((el.get("extra") or {}).get(
                    "spark_count", 14)),
            })
            return real(img, draw, el, camera, rig, width, height,
                        spark_frame)

        package, shot = _delivered_shot(4)
        cls.shot = shot
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

    def test_shot_is_the_insert(self):
        self.assertEqual(self.shot.get("directive_shot_id"),
                         "SC02_SH03")
        self.assertEqual(self.shot["shot_type"], "object_insert")

    def test_ambient_draw_every_frame_no_burst(self):
        n = self.result["n_frames"]
        self.assertEqual(len(self.calls), n)
        for fi, call in enumerate(self.calls):
            self.assertEqual(call["spark_frame"], fi)
            self.assertEqual(call["count"], 14,
                             "insert must not burst (reaction "
                             "stays gated on paint_glow)")


if __name__ == "__main__":
    unittest.main()
