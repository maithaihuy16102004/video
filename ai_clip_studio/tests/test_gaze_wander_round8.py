"""Round-8 micro-saccades (R4-A5): within-shot gaze was LOCKED
(tester: std ~1 px across a whole shot) because gaze_for_target
saturates at its clamp for distant look targets. A small seeded
wander now rides on the look direction, so the eyes drift around
the target instead of freezing on it, while mid-frame mutual
gaze still converges on the speaker.

Frame evidence: r8_delivered_shot9 (delivered R7 shot #9 plan:
spy gaze std 2.5-3.3 px, pixel eye-centroid std 2.5-4.2 px,
ranges 16-20 px; listeners converge on Linh).
"""
import json
import statistics
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

import ai_clip_studio.product_renderer as PR
from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.expression_library import gaze_wander
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


class TestGazeWanderUnit(unittest.TestCase):
    def test_deterministic_bounded_and_varying(self):
        series = [gaze_wander(t / 24.0, 12345) for t in range(89)]
        again = [gaze_wander(t / 24.0, 12345) for t in range(89)]
        self.assertEqual(series, again)
        # Round 12: the default amplitude is 0.12 (was 0.10); the
        # bound follows the amplitude by construction.
        for gx, gy in series:
            self.assertLessEqual(abs(gx), 0.12)
            self.assertLessEqual(abs(gy), 0.12)
        self.assertGreater(
            statistics.pstdev([g[0] for g in series]), 0.01)
        self.assertGreater(
            statistics.pstdev([g[1] for g in series]), 0.01)

    def test_seeds_differ_and_mean_near_zero(self):
        a = [gaze_wander(t / 24.0, 12345) for t in range(240)]
        b = [gaze_wander(t / 24.0, 999) for t in range(240)]
        self.assertNotEqual(a, b)
        # Zero-mean over a long window: the average gaze stays on
        # the look target. (Bound scales with the round-12
        # amplitude 0.12.)
        self.assertLess(abs(statistics.mean([g[0] for g in a])),
                        0.12 / 3.0)
        self.assertLess(abs(statistics.mean([g[1] for g in a])),
                        0.12 / 3.0)


class TestGazeWanderOnShot9(unittest.TestCase):
    """Delivered shot #9 (reaction): the gaze the renderer passes
    to the art varies within the shot, converges on the speaker,
    and the variation survives to pixels."""

    @classmethod
    def setUpClass(cls):
        cls.calls = []
        real = PR.draw_character_v4

        def _spy(d, ch, **kw):
            cls.calls.append(kw.get("gaze"))
            return real(d, ch, **kw)

        package, shot = _delivered_shot(9)
        cls.shot = shot
        cls.tmp = tempfile.TemporaryDirectory()
        prev = PR.draw_character_v4
        PR.draw_character_v4 = _spy
        try:
            cls.result = _render_shot(
                {"shot": shot, "package": package,
                 "out_dir": cls.tmp.name, "still_only": False})
        finally:
            PR.draw_character_v4 = prev
        cls.frames_dir = Path(cls.tmp.name) / "shot_009"
        cls.names = list(
            cls.result["grip_telemetry"][0]["hands"].keys())
        cls.tele = {e["frame"]: e["hands"]
                    for e in cls.result["grip_telemetry"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _gaze_series_px(self, name):
        j = self.names.index(name)
        n = self.result["n_frames"]
        out = []
        for i in range(n):
            g = self.calls[i * len(self.names) + j]
            r = self.tele[i][name]["head_r"]
            out.append(((g[0] if g else 0.0) * r,
                        (g[1] if g else 0.0) * r))
        return out

    def test_shot_is_the_reaction(self):
        self.assertEqual(self.shot.get("directive_shot_id"),
                         "SC03_SH01")
        self.assertEqual(self.shot["shot_type"], "reaction")
        self.assertEqual(len(self.calls),
                         self.result["n_frames"] * len(self.names))

    def test_gaze_varies_within_shot(self):
        # R4-A5: std ~1 px meant locked. The wander must clear
        # 2 px on both axes for every visible character.
        for name in self.names:
            series = self._gaze_series_px(name)
            self.assertGreater(
                statistics.pstdev([g[0] for g in series]), 2.0,
                f"{name}: gaze_x locked")
            self.assertGreater(
                statistics.pstdev([g[1] for g in series]), 2.0,
                f"{name}: gaze_y locked")

    def test_mutual_gaze_still_converges(self):
        speaker = self.result["speaker"]
        self.assertIn(speaker, self.names)
        mid = self.result["n_frames"] // 2
        speaker_x = self.tele[mid][speaker]["head"][0]
        for name in self.names:
            if name == speaker:
                continue
            series = self._gaze_series_px(name)
            mean_x = statistics.mean([g[0] for g in series])
            own_x = self.tele[mid][name]["head"][0]
            self.assertEqual(
                mean_x > 0, speaker_x > own_x,
                f"{name}: mean gaze {mean_x:.1f} does not point "
                f"at speaker {speaker}")

    def test_eye_centroids_vary_on_pixels(self):
        cr = self.result["crop_anchor"]["crop_rect"]
        sx = 1920.0 / (cr[2] - cr[0])
        sy = 1080.0 / (cr[3] - cr[1])
        for name in self.names:
            offs = []
            for fi in range(self.result["n_frames"]):
                h = self.tele[fi][name]
                cx = (h["head"][0] - cr[0]) * sx
                cy = (h["head"][1] - cr[1]) * sy
                rr = h["head_r"] * sx
                arr = np.asarray(Image.open(
                    self.frames_dir / f"f{fi:04d}.png").convert(
                        "RGB")).astype(int)
                # Round 10: the band must cover closed-arc eyes
                # AND wide oval eyes at full gaze travel. The old
                # +/-0.55r window clipped the outer edge of a
                # surprised oval at full look shift, compressing
                # the centroid (Bé Nam read 1.96 px); +/-0.80r
                # with the top at -0.25r covers arcs ([-0.15r,
                # -0.05r] measured) without clipping ovals, and
                # brows (above -0.43r) and the head ring (near
                # +/-0.99r at this height) stay out.
                x0 = int(cx - 0.80 * rr)
                x1 = int(cx + 0.80 * rr)
                y0 = int(cy - 0.25 * rr)
                y1 = int(cy + 0.20 * rr)
                band = arr[max(0, y0):y1, max(0, x0):x1]
                dark = (band[:, :, 0] + band[:, :, 1]
                        + band[:, :, 2]) < 250
                _ys, xs = np.nonzero(dark)
                self.assertGreaterEqual(
                    len(xs), 20,
                    f"{name} frame {fi}: no eye pixels in band")
                offs.append(float(xs.mean() + max(0, x0) - cx))
            self.assertGreater(
                statistics.pstdev(offs), 2.0,
                f"{name}: eye centroids locked on pixels")


if __name__ == "__main__":
    unittest.main()
