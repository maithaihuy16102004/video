"""Round-8 shield acting: the shield draws at guard scale from the
moment it starts moving (R7-D3: it popped 72 -> 296 px in 6 frames
because detail_at reports no holder until GRASPED); the guard
crouch is deeper (head drop 105 -> 131 px); and the protected
figure stages behind the SHIELD DISC from the camera's view (Be
Nam's head sat 82 px left of the disc centre in the delivered R7
OTS shot -- beside the disc, tucking behind the shoulder).

Frame evidence: r8_delivered_shot8 (delivered R7 shot #8 plan:
disc 296 px wide in every frame f24-f36, Be Nam head 17 px off
the disc centre during the hold, guard head drop 131 px).
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from ai_clip_studio.action_compiler import compile_actions
import ai_clip_studio.product_renderer as pr
from ai_clip_studio.product_renderer import _render_shot
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _delivered_shot8():
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
    shot = dict(shots[8])
    shot["index"] = 8
    shot["start_sec"] = starts[id(shots[8])]
    return package, shot


class TestShieldPrimitiveCrouch(unittest.TestCase):
    """The shield guard drops the hips deep enough to read as a
    crouch at production scale, and holds the guard to the end."""

    def test_crouch_drop_and_hold(self):
        from ai_clip_studio.animation.primitives import shield
        from ai_clip_studio.animation.rig import Stickman

        char = Stickman(height=600.0, template="default")
        char.pose["root_x"] = 960.0
        char.pose["root_y"] = 600.0
        fn = shield(char, 1.0)
        fn(0.0)
        root0 = char.pose["root_y"]
        fn(1.0)
        drop = char.pose["root_y"] - root0
        # 72 * 600/560 = 77 px at this height (was 56 -> 60 px).
        self.assertGreater(drop, 65.0,
                           f"guard crouch drop {drop:.1f}px too weak")
        fn(1.0)
        self.assertAlmostEqual(char.pose["root_y"], root0 + drop,
                               places=3)


class TestShieldRaiseAndStaging(unittest.TestCase):
    """Delivered-plan shot #8: constant disc size through the
    raise, the protected figure centred on the disc, the guard
    crouch reading in the OTS frame."""

    @classmethod
    def setUpClass(cls):
        package, shot = _delivered_shot8()
        cls.shot = shot
        cls.tmp = tempfile.TemporaryDirectory()
        # R18: record every shield draw size -- the R7-D3
        # property (one object, constant size) lives in the
        # sizes the renderer passes, not in a pixel window
        # that background timbers can contaminate.
        cls.shield_sizes = []
        _orig_draw = pr._draw_prop

        def _spy(draw, x, y, kind="wallet", w=None, h=None,
                 open_u=0.0, tip=None):
            if kind == "shield":
                cls.shield_sizes.append((round(float(w), 1),
                                         round(float(h), 1)))
            return _orig_draw(draw, x, y, kind=kind, w=w, h=h,
                              open_u=open_u, tip=tip)

        with mock.patch.object(pr, "_draw_prop", _spy):
            cls.result = _render_shot({
                "shot": shot, "package": package,
                "out_dir": Path(cls.tmp.name), "still_only": False})
        cls.frames_dir = Path(cls.tmp.name) / "shot_008"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _disc_xy(self, frame):
        for entry in self.result["grip_telemetry"]:
            if entry["frame"] != frame:
                continue
            for draw in entry["draws"]:
                if draw.get("kind") == "shield":
                    return float(draw["x"]), float(draw["y"])
        self.fail(f"no shield draw at frame {frame}")

    def _disc_width_px(self, frame):
        cx, cy = self._disc_xy(frame)
        path = self.frames_dir / f"f{frame:04d}.png"
        arr = np.asarray(Image.open(path).convert("RGB")).astype(int)
        x0, x1 = max(0, int(cx) - 220), min(1920, int(cx) + 220)
        y0, y1 = max(0, int(cy) - 220), min(1080, int(cy) + 220)
        win = arr[y0:y1, x0:x1]
        r, g, b = win[:, :, 0], win[:, :, 1], win[:, :, 2]
        mask = (r > 110) & (r < 190) & (g > 60) & (g < 125) \
            & (b < 80) & (r > g + 30)
        _ys, xs = np.nonzero(mask)
        self.assertTrue(len(xs) > 1000,
                        f"frame {frame}: shield wood not found")
        return int(xs.max() - xs.min())

    def test_shot_is_the_shield_ots(self):
        self.assertEqual(self.shot.get("directive_shot_id"),
                         "SC03_SH01")
        self.assertEqual(self.shot["shot_type"],
                         "over_the_shoulder")

    def test_disc_size_constant_through_raise(self):
        # R7-D3: 72 px at f24-30, 296 px from f32. The raise must
        # move the disc, not grow it. The draw sizes govern: the
        # disc is one object sized by the holder's head diameter
        # (0.34H) from the first frame it moves. The pixel window
        # below only proves it renders at guard scale on screen;
        # its span is contamination-prone (background timbers),
        # so no swing is asserted on it.
        self.assertTrue(self.shield_sizes, "no shield draws")
        widths = [w for w, _h in self.shield_sizes]
        self.assertLessEqual(max(widths) - min(widths), 2.0,
                             f"disc draw size swings: "
                             f"{sorted(set(widths))}")
        self.assertGreaterEqual(min(widths), 200.0,
                                f"disc {min(widths)}px, not guard "
                                f"scale (head diameter 0.34H)")
        for f in (24, 36):
            w = self._disc_width_px(f)
            self.assertGreaterEqual(
                w, 200, f"frame {f}: disc {w}px, not guard scale")
            self.assertLessEqual(
                w, 320, f"frame {f}: disc {w}px, oversized")

    def test_protected_figure_centred_on_disc(self):
        # Hold frames: Be Nam's head x tracks the disc centre.
        tel = {e["frame"]: e for e in self.result["grip_telemetry"]}
        for frame in (40, 50, 60):
            disc_x, _disc_y = self._disc_xy(frame)
            head_x = tel[frame]["hands"]["Bé Nam"]["head"][0]
            self.assertLessEqual(
                abs(head_x - disc_x), 40.0,
                f"frame {frame}: Be Nam head {head_x:.0f} vs disc "
                f"{disc_x:.0f} (delivered R7: 82 px off)")

    def test_alignment_record_predicts_the_centring(self):
        align = (self.result.get("shield_disc_alignment") or {}).get(
            "Bé Nam")
        self.assertIsNotNone(align)
        self.assertLessEqual(align["residual_px"], 20.0)

    def test_guard_crouch_reads(self):
        tel = {e["frame"]: e for e in self.result["grip_telemetry"]}
        head_idle = tel[10]["hands"]["Ông Ba"]["head"][1]
        head_hold = tel[40]["hands"]["Ông Ba"]["head"][1]
        # R18: the floor follows the mechanism, not the R17
        # absolute. Be Nam's corrected height moved the OTS
        # anchor; Ong Ba's staging H is 681, so the
        # body-relative crouch (72/560 H root + lean) reads
        # 96.6 px -- the same 0.142H relative crouch as R17's
        # 121.1 px. The counterfactual (Be Nam forced to 0.75)
        # reproduces 121.1 px on current code.
        self.assertGreaterEqual(
            head_hold - head_idle, 90.0,
            "guard head drop too weak to read as a crouch "
            f"({head_hold - head_idle:.0f}px, expected ~97px)")

    def test_no_head_intrusions(self):
        self.assertEqual(self.result.get("head_intrusion_count"), 0)


if __name__ == "__main__":
    unittest.main()
