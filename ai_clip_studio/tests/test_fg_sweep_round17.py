"""Round 17 (L02-D11): FG clearance covers the locomotion swept path.

The clearer parked FG occluders beside the STATIC staging box, so a
runner left the cleared box mid-shot and ran behind the FG trunk
(Loop 02 shot #3: An ran 380 px right, straight behind the trunk).
The subject boxes now cover the whole swept path, replayed with the
same step sizes and retreat flip as _event_fn.
"""
import json
import tempfile
import unittest
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.animation.character_art import STYLE_LOCK
from ai_clip_studio.product_renderer import (
    _LOCOMOTION_STEP_PX, _render_shot, _swept_x_for_actor)
import ai_clip_studio.product_renderer as pr
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent
JOB = AGENT / "jobs" / "req_b0fe5da148b7"  # R16 Loop 02


def _ev(primitive, retreat=False):
    rp = {"primitive": primitive}
    if retreat:
        rp["params"] = {"retreat": True}
    return {"required_pose": rp}


class TestSweptX(unittest.TestCase):
    def test_step_constants(self):
        self.assertEqual(_LOCOMOTION_STEP_PX,
                         {"walk_to": 320.0, "run_to": 380.0,
                          "walk_mud": 300.0})

    def test_no_locomotion(self):
        wins = [(0.0, 1.0, _ev("idle")), (1.0, 2.0, _ev("nod"))]
        self.assertEqual(_swept_x_for_actor(wins, 917.0, 1),
                         (917.0, 917.0))

    def test_walk_right(self):
        wins = [(0.0, 1.0, _ev("walk_to"))]
        self.assertEqual(_swept_x_for_actor(wins, 917.0, 1),
                         (917.0, 1237.0))

    def test_walk_left(self):
        wins = [(0.0, 1.0, _ev("walk_to"))]
        self.assertEqual(_swept_x_for_actor(wins, 917.0, -1),
                         (597.0, 917.0))

    def test_run_and_mud(self):
        self.assertEqual(
            _swept_x_for_actor([(0.0, 1.0, _ev("run_to"))], 0.0, 1),
            (0.0, 380.0))
        self.assertEqual(
            _swept_x_for_actor([(0.0, 1.0, _ev("walk_mud"))], 0.0, 1),
            (0.0, 300.0))

    def test_retreat_flip(self):
        wins = [(0.0, 1.0, _ev("walk_to", retreat=True))]
        self.assertEqual(_swept_x_for_actor(wins, 917.0, 1),
                         (597.0, 917.0))

    def test_chained_accumulates_in_window_order(self):
        wins = [(0.0, 1.0, _ev("walk_to")),
                (1.0, 2.0, _ev("run_to")),
                (2.0, 3.0, _ev("walk_to", retreat=True))]
        # 917 -> 1237 -> 1617 -> 1297
        self.assertEqual(_swept_x_for_actor(wins, 917.0, 1),
                         (917.0, 1617.0))

    def test_ignores_other_primitives(self):
        wins = [(0.0, 1.0, _ev("sit_down")),
                (1.0, 2.0, _ev("walk_to")),
                (2.0, 3.0, _ev("insert_key"))]
        self.assertEqual(_swept_x_for_actor(wins, 100.0, -1),
                         (-220.0, 100.0))


def _delivered_shots():
    text = (AGENT / "examples" / "loop_test_02_brass_key.studio.md"
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


class TestShot03Clearance(unittest.TestCase):
    def test_subject_box_covers_the_run(self):
        package, shots = _delivered_shots()
        captured = {}
        orig = pr.clear_foreground_from_subjects

        def spy(pkg, camera, size=(1920, 1080), subject_boxes=None,
                **kw):
            captured["boxes"] = list(subject_boxes or [])
            return orig(pkg, camera, size=size,
                        subject_boxes=subject_boxes, **kw)

        pr.clear_foreground_from_subjects = spy
        try:
            with tempfile.TemporaryDirectory() as tmp:
                rep = _render_shot({"shot": shots[3],
                                    "package": package,
                                    "out_dir": tmp,
                                    "still_only": True})
        finally:
            pr.clear_foreground_from_subjects = orig
        self.assertEqual(len(captured["boxes"]), 1)
        x0, _y0, x1, _y1 = captured["boxes"][0]
        # The run carries An 380 px right of her staging mark;
        # the box must span the whole path, not the mark.
        self.assertGreater(x1 - x0, 380.0)
        hip_x = rep["joints_last_frame"]["An"]["hip"][0]
        self.assertLess(x0, hip_x)
        self.assertGreater(x1, hip_x)

    def test_head_stays_visible_across_the_run(self):
        package, shots = _delivered_shots()
        _hex = STYLE_LOCK["face_fill"].lstrip("#")
        face = np.array([int(_hex[i:i + 2], 16)
                         for i in (0, 2, 4)], dtype=int)
        with tempfile.TemporaryDirectory() as tmp:
            _render_shot({"shot": shots[3], "package": package,
                          "out_dir": tmp, "still_only": False})
            blobs = []
            frames = sorted(Path(tmp).glob("shot_003/f*.png"))
            self.assertEqual(len(frames), 125)
            for f in frames[::12]:
                a = np.asarray(Image.open(f).convert("RGB")
                               ).astype(int)
                small = (np.abs(a[:550:4, ::4] - face).sum(axis=2)
                         < 40)
                seen = np.zeros_like(small, dtype=bool)
                best = 0
                H, W = small.shape
                for yy, xx in zip(*np.where(small)):
                    yy, xx = int(yy), int(xx)
                    if seen[yy, xx]:
                        continue
                    q = deque([(yy, xx)])
                    seen[yy, xx] = True
                    n = 0
                    while q:
                        cy, cx = q.popleft()
                        n += 1
                        for dy, dx in ((1, 0), (-1, 0),
                                       (0, 1), (0, -1)):
                            ny, nx = cy + dy, cx + dx
                            if (0 <= ny < H and 0 <= nx < W
                                    and small[ny, nx]
                                    and not seen[ny, nx]):
                                seen[ny, nx] = True
                                q.append((ny, nx))
                    best = max(best, n)
                blobs.append(best)
        # Measured on the R17 fix: 2069-2225, no occlusion dip.
        # The pre-fix trunk cut ~70% of the figure mid-run.
        self.assertGreater(min(blobs), 1800)
        self.assertLess(max(blobs) / min(blobs), 1.15)


if __name__ == "__main__":
    unittest.main()
