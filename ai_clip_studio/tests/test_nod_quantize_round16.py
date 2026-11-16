"""Round 16 (R15-D1 / R4-A5): the nod overlays step on the gaze
fixation grid instead of erasing the idle's step structure.

The R15-8 idle quantization reached the delivered frames, but the
continuous talk nod (a raw 1.1 Hz sine applied AFTER the body
fns) overwrote the quantized head_look on every frame: spy-logged
on Loop 01 shot #14, the idle's head_look changed 28 times
across 87 calls while the nod's changed 85. The fix quantizes
the nod on the SAME gaze grid (the actor's own seed, shared with
the idle and the eyes) with a 2-frame head ease, and slows the
talk nod to 0.5 Hz (a 1.1 Hz sine sampled every 0.25 s jumps up
to 0.12 rad per boundary -- measured 8.6M rim-diff pops).
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from ai_clip_studio.animation.primitives import (
    PRIMITIVES, nod, standing)
from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.expression_library import (
    _GAZE_DWELL_SEC, fixation_time)
from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import _render_shot
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent
JOB = AGENT / "jobs" / "req_fda6b9c59f7e"  # R15 Loop 01
SEED = 1390970424  # Linh's gaze seed on Loop 01 shot #14


def _char():
    ch = Stickman(height=780)
    standing(ch, 960, 900, facing=1)
    return ch


class TestFixationTimeEase(unittest.TestCase):
    def test_default_unchanged(self):
        # ease_sec=None reproduces the historical 0.04 s ease.
        for t in [0.0, 0.03, 0.06, 0.24, 0.26, 0.30, 1.13, 2.7]:
            self.assertEqual(fixation_time(t, SEED),
                             fixation_time(t, SEED, ease_sec=0.04))

    def test_longer_ease_widens_the_window(self):
        # At phase 0.06 (past the eye ease, inside a 0.083 ease)
        # the default has settled on the new dwell while the
        # longer ease is still gliding between dwells.
        t = 1.0 + 0.06 - 0.037 * (SEED % 7)
        default = fixation_time(t, SEED)
        gliding = fixation_time(t, SEED, ease_sec=0.083)
        self.assertNotEqual(default, gliding)
        self.assertLess(gliding, default)

    def test_grid_unchanged_outside_the_ease(self):
        # Dwell values are identical whatever the ease.
        for t in [0.1, 0.2, 0.35, 0.5, 1.2, 2.1]:
            self.assertEqual(fixation_time(t, SEED),
                             fixation_time(t, SEED, ease_sec=0.083))


class TestNodQuantization(unittest.TestCase):
    def test_default_is_the_historical_sine(self):
        ch = _char()
        fn = nod(ch, 1.0)
        for t in (0.0, 0.13, 0.3, 0.71):
            fn(t)
            self.assertAlmostEqual(
                ch.pose["head_look"],
                0.10 * math.sin(t * 2 * math.pi * 1.1), places=9)

    def test_phase_shifts_the_unquantized_sine(self):
        ch = _char()
        plain = nod(ch, 1.0)
        phased = nod(ch, 1.0, phase=0.7)
        plain(0.3 + 0.7)
        expected = ch.pose["head_look"]
        phased(0.3)
        self.assertAlmostEqual(ch.pose["head_look"], expected, places=9)

    def test_quantized_nod_holds_within_dwells(self):
        ch = _char()
        fn = nod(ch, 1.0, freq=0.5, amp=0.08, gaze_seed=SEED)
        # Dwell interiors (past the 0.083 s ease): identical.
        off = 0.037 * (SEED % 7)
        base = 1.0 - off  # a dwell boundary in caller time
        vals = set()
        for k in range(4):
            fn(base + 0.10 + k / 24.0)
            vals.add(round(ch.pose["head_look"], 9))
        self.assertEqual(len(vals), 1)

    def test_quantized_nod_follows_the_grid_formula(self):
        ch = _char()
        fn = nod(ch, 1.0, freq=0.5, amp=0.08, gaze_seed=SEED,
                 phase=0.4)
        for t in (0.0, 0.2, 0.55, 1.3, 2.9):
            fn(t)
            t_q = fixation_time(t, SEED, ease_sec=0.083)
            self.assertAlmostEqual(
                ch.pose["head_look"],
                0.08 * math.sin((t_q + 0.4) * 2 * math.pi * 0.5),
                places=9)

    def test_compilable_nod_unchanged(self):
        ch = _char()
        fn = PRIMITIVES["nod"](ch, 1.0)
        fn(0.3)
        self.assertAlmostEqual(
            ch.pose["head_look"],
            0.10 * math.sin(0.3 * 2 * math.pi * 1.1), places=9)


def _delivered_shots():
    text = (AGENT / "examples" / "loop_test_01_fire_stone.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    timeline = json.loads((JOB / "timeline.json").read_text(
        encoding="utf-8"))
    shots = timeline["shots"]
    starts, _t = {}, 0.0
    for s in shots:
        starts[id(s)] = _t
        _t += float(s["duration"])
    spans = {}
    for s in shots:
        sid = s.get("directive_shot_id")
        if sid:
            st, en = starts[id(s)], starts[id(s)] + float(s["duration"])
            spans[sid] = [min(spans[sid][0], st), max(spans[sid][1], en)] \
                if sid in spans else [st, en]
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    out = []
    for i, s in enumerate(shots):
        shot = dict(s)
        shot["index"] = i
        shot["start_sec"] = starts[id(s)]
        out.append(shot)
    return package, out


class TestDeliveredStepStructure(unittest.TestCase):
    def test_shot14_head_steps_on_delivered_frames(self):
        package, shots = _delivered_shots()
        with tempfile.TemporaryDirectory() as tmp:
            rep = _render_shot({"shot": shots[14], "package": package,
                                "out_dir": tmp, "still_only": False})
            crop = (rep["crop_anchor"] or {})["crop_rect"]
            x0, y0, x1, y1 = [float(v) for v in crop]
            sx, sy = 1920.0 / (x1 - x0), 1080.0 / (y1 - y0)
            head = rep["joints_last_frame"]["Linh"]["head"]
            cx = int((head[0] - x0) * sx)
            cy = int((head[1] - y0) * sy)
            bx, by = max(0, cx - 300), max(0, cy - 300)
            diffs = []
            prev = None
            frames = sorted(Path(tmp).glob("shot_014/f*.png"))
            self.assertEqual(len(frames), 86)
            for f in frames:
                a = np.asarray(Image.open(f).convert("RGB")).astype(int)
                a = a[by:by + 600, bx:bx + 600]
                if prev is not None:
                    dd = np.abs(a - prev).sum(axis=2)
                    # Mask the independently animated features
                    # (eyes/brows/mouth) and the scarf: only the
                    # head rim may judge the step structure.
                    dd[190:410, 210:390] = 0
                    dd[500:600, :] = 0
                    diffs.append(dd.sum())
                prev = a
        diffs = np.array(diffs)
        # Measured on the R16 implementation: 20 frozen pairs,
        # median 118K, max 4.35M. The pre-fix control had 0
        # frozen pairs and a 1.61M median. Thresholds carry
        # headroom; the defect is a REGRESSION if the head
        # drifts every frame again.
        self.assertGreaterEqual((diffs == 0).sum(), 15)
        self.assertLess(int(np.median(diffs)), 300000)
        self.assertLess(int(diffs.max()), 5000000)


if __name__ == "__main__":
    unittest.main()
