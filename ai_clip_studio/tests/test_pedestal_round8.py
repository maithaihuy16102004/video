"""Round-8 pedestal: the placer stages beside the named support in
SCREEN space (R2-V1: delivered R7 shot #10 placed the stone from
across the room -- a 700 px teleport -- and Ong Ba covered the
pedestal); bystanders clear the support UNION the placer, so the
placement stays visible; and the hand reaches to the support top
(place_on_surface) instead of the hip (put_away).

Frame evidence: r8_delivered_shot10 (delivered R7 shot #10 plan:
Linh stages beside the pedestal at her own depth, the stone's
release glide is ~10 px, the hand meets the rest within 5 px,
all three heads separated, the pedestal + glowing stone
unoccluded).
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import _render_shot
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
JOBS = Path(__file__).resolve().parents[2] / "jobs"


def _delivered_shot10():
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
    shot = dict(shots[10])
    shot["index"] = 10
    shot["start_sec"] = starts[id(shots[10])]
    return package, shot


class TestPlaceOnSurfacePrimitive(unittest.TestCase):
    """The hand reaches the surface, holds through the release,
    then withdraws; the prop stays at the surface point."""

    def test_reach_hold_withdraw(self):
        from ai_clip_studio.animation.primitives import (
            place_on_surface)
        from ai_clip_studio.animation.rig import Stickman

        char = Stickman(height=600.0, template="default")
        char.pose["root_x"] = 960.0
        char.pose["root_y"] = 600.0
        prop = {}
        target = (1060.0, 500.0)
        fn = place_on_surface(char, target, 1.0, hand="r", prop=prop)
        fn(0.0)
        start = char.joints()["hand_r"]
        d0 = math.hypot(start[0] - target[0], start[1] - target[1])
        fn(0.5)
        mid = char.joints()["hand_r"]
        d_mid = math.hypot(mid[0] - target[0], mid[1] - target[1])
        self.assertLess(d_mid, d0 * 0.5,
                        "hand must travel most of the way to the "
                        f"surface (start {d0:.0f}px, mid {d_mid:.0f}px)")
        self.assertFalse(prop["released"])
        fn(0.7)
        self.assertTrue(prop["released"])
        self.assertAlmostEqual(prop["x"], target[0], places=0)
        fn(1.0)
        end = char.joints()["hand_r"]
        d_end = math.hypot(end[0] - target[0], end[1] - target[1])
        self.assertGreater(d_end, d_mid,
                           "hand must withdraw after the release")


class TestPedestalPlacement(unittest.TestCase):
    """Delivered-plan shot #10: staged placement, clear sightline,
    short release glide, separated heads."""

    @classmethod
    def setUpClass(cls):
        package, shot = _delivered_shot10()
        cls.shot = shot
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = _render_shot({
            "shot": shot, "package": package,
            "out_dir": Path(cls.tmp.name), "still_only": False})
        cls.tmp.cleanup()
        cls.tel = {e["frame"]: e
                   for e in cls.result["grip_telemetry"]}

    def _stone_xy(self, frame):
        for draw in self.tel[frame]["draws"]:
            if draw.get("kind") in ("stone", "rock", "gem"):
                return float(draw["x"]), float(draw["y"])
        self.fail(f"no stone draw at frame {frame}")

    def test_shot_is_the_pedestal_medium(self):
        self.assertEqual(self.shot.get("directive_shot_id"),
                         "SC03_SH02")
        self.assertEqual(self.shot["shot_type"], "medium")

    def test_placer_staged_beside_support_at_own_depth(self):
        staging = self.result.get("place_staging") or {}
        self.assertIn("Linh", staging)
        _x, z, _side = staging["Linh"]
        # The pedestal sits at z -8.5; copying its depth rendered
        # Linh as a giant (radius pullback 2.41). She keeps her
        # own depth; the screen-space solve puts her beside it.
        self.assertGreater(abs(z - (-8.5)), 2.0,
                           f"placer depth {z} copies the support")

    def test_sightline_cleared_a_bystander(self):
        sight = self.result.get("support_sightline") or {}
        moved = sight.get("moved") or {}
        self.assertTrue(moved, "no bystander needed clearing?")
        for name, rec in moved.items():
            self.assertTrue(rec["cleared"], f"{name} not cleared")

    def test_heads_separated_in_final_frames(self):
        for frame in (30, 60):
            heads = {n: (h["head"], h["head_r"])
                     for n, h in self.tel[frame]["hands"].items()}
            names = sorted(heads)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    (ax, ay), ar = heads[a]
                    (bx, by), br = heads[b]
                    dist = math.hypot(ax - bx, ay - by)
                    self.assertGreater(
                        dist, ar + br,
                        f"frame {frame}: {a} and {b} heads overlap "
                        f"(dist {dist:.0f}, radii {ar:.0f}+{br:.0f})")

    def test_stone_travels_with_the_hand_not_a_teleport(self):
        # Every frame-to-frame step through the place window is
        # small (delivered R7: a 370 px jump in 6 frames).
        prev = None
        for frame in range(0, 21):
            xy = self._stone_xy(frame)
            if prev is not None:
                step = math.hypot(xy[0] - prev[0], xy[1] - prev[1])
                self.assertLessEqual(
                    step, 60.0,
                    f"stone jumps {step:.0f}px f{frame-1}->f{frame}")
            prev = xy

    def test_hand_meets_the_rest_at_release(self):
        rest = self._stone_xy(20)
        best = min(
            math.hypot(
                self.tel[f]["hands"]["Linh"]["hand_r"][0] - rest[0],
                self.tel[f]["hands"]["Linh"]["hand_r"][1] - rest[1])
            for f in range(8, 15))
        self.assertLessEqual(
            best, 80.0,
            f"hand never reaches the pedestal (closest {best:.0f}px)")

    def test_pedestal_rest_visible_past_every_head(self):
        rest = self._stone_xy(30)
        for name, joints in self.tel[30]["hands"].items():
            (hx, hy), hr = joints["head"], joints["head_r"]
            dist = math.hypot(hx - rest[0], hy - rest[1])
            self.assertGreater(
                dist, hr + 10.0,
                f"{name}'s head covers the placed stone "
                f"(dist {dist:.0f}, head_r {hr:.0f})")

    def test_no_head_intrusions(self):
        self.assertEqual(self.result.get("head_intrusion_count"), 0)


if __name__ == "__main__":
    unittest.main()
