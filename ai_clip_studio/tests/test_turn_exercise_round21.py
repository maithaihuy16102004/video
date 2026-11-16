"""Round 21 (exercise shots): the front-view lean fix (R19-3) is
exercised on a delivered render for the first time.

Loop 02 SC01_SH02 gained "* An quay người lại." -- a TURN event
with no target, so _event_fn flips An's facing and turn_to drives
turn_u 0 -> 1 with peak lean at the midpoint. The spy proves the
front view is reached mid-turn with lean; the pixel track proves
the head travels smoothly through the front frame (no sideways
slide) while dipping.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image
from scipy import ndimage

from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.action_compiler import compile_actions


class TestTurnEventCompiles(unittest.TestCase):
    def test_turn_event_no_target(self):
        text = (Path("examples/loop_test_02_brass_key.studio.md")
                .read_text(encoding="utf-8"))
        pkg = adapt_document(parse_studio_script_v1(text))
        job = json.loads(
            Path("jobs/req_9525d57a99ee/timeline.json").read_text())
        shots = job["shots"]
        starts, clock = {}, 0.0
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
            pkg, timeline={"spans": spans})
        turns = [e for e in events
                 if e.get("action_type") == "TURN"]
        self.assertEqual(len(turns), 1)
        turn = turns[0]
        self.assertEqual(turn.get("action_id"), "SC01_SH02_ACT03")
        self.assertIsNone(turn.get("target_id"))
        self.assertEqual(
            (turn.get("required_pose") or {}).get("primitive"),
            "turn_to")
        self.assertGreater(
            turn["end_time"] - turn["start_time"], 0.3)
        self.assertEqual(len(unsupported), 6)


class TestTurnExerciseRender(unittest.TestCase):
    """Timeline shot #0 (SC01_SH02) with pose + view spies."""

    @classmethod
    def setUpClass(cls):
        import ai_clip_studio.product_renderer as pr
        from ai_clip_studio.product_renderer import _render_shot
        from ai_clip_studio.tests.test_cue_coverage_round18 import (
            _delivered_shot)
        package, shot = _delivered_shot(0, job="req_9525d57a99ee")
        cls.tmp = tempfile.TemporaryDirectory()
        poses = []
        views = []
        orig_draw = pr.draw_character_v4
        orig_resolve = pr.resolve_view

        def draw_spy(*a, **k):
            char = a[1] if len(a) > 1 else k.get("char")
            out = orig_draw(*a, **k)
            poses.append({
                "turn_u": float(char.pose.get("turn_u", 0.0) or 0.0),
                "lean": float(char.pose.get("torso_lean", 0.0)
                              or 0.0),
                "facing": char.pose.get("facing"),
            })
            return out

        def resolve_spy(char, default):
            v = orig_resolve(char, default)
            views.append(v)
            return v

        with mock.patch.object(pr, "draw_character_v4",
                               side_effect=draw_spy):
            with mock.patch.object(pr, "resolve_view",
                                   side_effect=resolve_spy):
                _render_shot({"shot": shot, "package": package,
                              "out_dir": cls.tmp.name,
                              "still_only": False})
        cls.poses = poses
        cls.views = views
        cls.out = Path(cls.tmp.name) / "shot_000"
        # Head-disc track (face fill), one entry per frame.
        cls.discs = []
        for fi in range(len(poses)):
            p = cls.out / f"f{fi:04d}.png"
            a = np.asarray(Image.open(p).convert("RGB")).astype(int)
            mask = (np.abs(a - np.array([247, 243, 232])).sum(axis=2)
                    < 40)
            lab, cnt = ndimage.label(mask)
            best = None
            for j in range(1, cnt + 1):
                ys, xs = np.nonzero(lab == j)
                if len(xs) >= 3000 and (best is None
                                        or len(xs) > best[0]):
                    best = (len(xs), float(xs.mean()),
                            float(ys.mean()))
            cls.discs.append(best[1:] if best else None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_front_view_reached_mid_turn_with_lean(self):
        fronts = [i for i, v in enumerate(self.views)
                  if v == "front"]
        self.assertGreaterEqual(len(fronts), 1)
        for i in fronts:
            p = self.poses[i]
            self.assertGreater(p["turn_u"], 0.35)
            self.assertLess(p["turn_u"], 0.65)
            self.assertGreater(abs(p["lean"]), 0.05)
        # Facing flips across the turn window.
        window = [i for i, p in enumerate(self.poses)
                  if 0.0 < p["turn_u"] < 1.0]
        self.assertGreater(len(window), 3)
        self.assertEqual(self.poses[window[0]]["facing"], 1)
        self.assertEqual(self.poses[window[-1]]["facing"], -1)

    def test_head_travels_smoothly_through_front_frame(self):
        fronts = [i for i, v in enumerate(self.views)
                  if v == "front"]
        window = [i for i, p in enumerate(self.poses)
                  if 0.0 < p["turn_u"] < 1.0]
        cxs = [self.discs[i][0] for i in window]
        steps = [abs(cxs[k + 1] - cxs[k]) for k in range(len(cxs) - 1)]
        median_step = float(np.median(steps))
        for i in fronts:
            k = window.index(i)
            if k > 0:
                self.assertLessEqual(steps[k - 1],
                                     1.5 * median_step + 2.0)
            if k < len(steps):
                self.assertLessEqual(steps[k],
                                     1.5 * median_step + 2.0)
        # The turn dips the head at the front frame.
        for i in fronts:
            cy = self.discs[i][1]
            self.assertGreater(cy, self.discs[window[0]][1] + 3.0)
            self.assertGreater(cy, self.discs[window[-1]][1] + 3.0)


if __name__ == "__main__":
    unittest.main()
