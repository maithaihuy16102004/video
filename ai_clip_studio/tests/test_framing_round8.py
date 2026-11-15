"""Round-8 framing: a head framing pushes a partial bystander OUT
instead of re-centring on the union (the R7 pull-in widened the
strike MCU into a two-shot); a kneel/bend shot's frozen crop
holds BOTH the standing head and the kneeled head (R7-D2); and a
short walk inside a head framing widens only the walker's box to
cover the walk path instead of widening the whole shot to
full-body at full frame (R2-C2: the delivered R7 strike shot
rendered 148px heads because one bystander's 320px retreat
triggered the shot-level locomotion widening).

Frame evidence: r8_delivered_shot3 (delivered R7 shot #3 plan:
scale 1.6, Linh 330px heads, retreat covered, 0 intrusions) and
round7_probe_shot0 (kneel: cropped heads span [123, 1036]).
"""
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.camera_planner import (
    CameraPlanner, _crop_rect, _other_status, validate_framing)
from ai_clip_studio.product_renderer import _render_shot, plan_shots
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _loop01_package_and_shots():
    text = (EXAMPLES / "loop_test_01_fire_stone.studio.md").read_text(
        encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(7)])
    for i, s in enumerate(shots):
        s["index"] = i
    spans = {}
    clock = 0.0
    for s in shots:
        did = s.get("directive_shot_id")
        if did:
            span = spans.setdefault(str(did), [clock, clock])
            span[1] = clock + float(s["duration"])
        clock += float(s["duration"])
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None,
    }
    return package, shots


def _render(package, shot):
    tmp = tempfile.TemporaryDirectory()
    result = _render_shot({
        "shot": shot, "package": package,
        "out_dir": Path(tmp.name), "still_only": False})
    tmp.cleanup()
    return result


def _cropped_heads(result):
    crop = result["crop_anchor"]
    x0, y0, _x1, _y1 = crop["crop_rect"]
    scale = crop["scale"]
    heads = []
    for entry in result["grip_telemetry"]:
        for name, joints in entry["hands"].items():
            cx, cy = joints["head"]
            r = joints["head_r"]
            heads.append((entry["frame"], name,
                          (cx - x0) * scale, (cy - y0) * scale,
                          2.0 * r * scale))
    return heads


class TestPushOutFirst(unittest.TestCase):
    """_fix_partial_others tries push-out before pull-in for head
    framings, and keeps pull-in first for other shot types."""

    SUBJECT = {"cx": 960, "head_y": 200, "foot_y": 650, "half_w": 150}
    # Right edge 1580 sticks 20px past the 1.6x crop's right edge
    # (1560) while the subject+other union still fits the crop, so
    # the old pull-in-first order would re-centre on the union.
    OTHER = {"cx": 1500, "head_y": 200, "foot_y": 500, "half_w": 80}
    FOCUS = (960, 400)

    def _run(self, shot_type):
        shot = {"shot_type": shot_type,
                "camera": {"scale": 1.6,
                           "focus_target": "subject_head"}}
        safe, sfocus, _ = CameraPlanner.safe_frame(
            shot, self.FOCUS, [dict(self.SUBJECT)],
            [dict(self.OTHER)])
        rect = _crop_rect(float(safe["camera"]["scale"]), sfocus,
                          1920, 1080)
        return safe, sfocus, _other_status(self.OTHER, rect)

    def test_head_framing_pushes_partial_other_out(self):
        safe, sfocus, status = self._run("medium_close_up")
        self.assertEqual(status, "out",
                         "MCU must exclude the partial bystander, "
                         "not re-centre on the union")
        self.assertEqual(float(safe["camera"]["scale"]), 1.6)
        issues, _ = validate_framing(
            safe, sfocus, [dict(self.SUBJECT)])
        self.assertEqual(issues, [])

    def test_non_head_framing_still_pulls_in(self):
        _safe, _sfocus, status = self._run("medium")
        self.assertEqual(status, "in",
                         "a medium keeps the old pull-in behaviour")


class TestKneelHeadroom(unittest.TestCase):
    """Shot #0 (SC01_SH02, the kneel_pick) keeps the MCU scale and
    holds the head inside the cropped frame through the kneel."""

    @classmethod
    def setUpClass(cls):
        package, shots = _loop01_package_and_shots()
        cls.shot = shots[0]
        cls.result = _render(package, cls.shot)

    def test_shot_is_the_kneel_mcu(self):
        self.assertEqual(self.shot.get("directive_shot_id"),
                         "SC01_SH02")
        self.assertEqual(self.shot["shot_type"], "medium_close_up")

    def test_scale_stays_mcu(self):
        self.assertEqual(
            float(self.result["crop_anchor"]["scale"]), 1.6,
            "the kneeled-head union must not zoom the shot out")

    def test_kneeled_head_stays_in_frame(self):
        heads = _cropped_heads(self.result)
        self.assertTrue(heads)
        for frame, name, _cx, cy, diam in heads:
            self.assertGreaterEqual(
                cy - diam / 2.0, 0.0,
                f"{name} head top cut at frame {frame}")
            self.assertLessEqual(
                cy + diam / 2.0, 1080.0,
                f"{name} head bottom cut at frame {frame}")


class TestLocomotionKeepsMCU(unittest.TestCase):
    """Delivered R7 shot #3 (SC02_SH02, the strike + retreat) keeps
    the MCU scale: the walker's box widens to cover the walk path
    instead of widening the shot to full-body at full frame. Uses
    the DELIVERED R7 plan (jobs/req_3ee64748a857/timeline.json):
    the hand-made 3.0s plan splits the directive so the retreat
    falls outside the MCU shot and cannot exercise this path."""

    @classmethod
    def setUpClass(cls):
        import json

        from ai_clip_studio.action_compiler import compile_actions
        jobs = Path(__file__).resolve().parents[2] / "jobs"
        job = jobs / "req_3ee64748a857"
        text = (EXAMPLES / "loop_test_01_fire_stone.studio.md"
                ).read_text(encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(text))
        timeline = json.loads(
            (job / "timeline.json").read_text(encoding="utf-8"))
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
        cls.shot = dict(shots[3])
        cls.shot["index"] = 3
        cls.shot["start_sec"] = starts[id(shots[3])]
        cls.result = _render(package, cls.shot)

    def test_shot_is_the_strike_mcu(self):
        self.assertEqual(self.shot.get("directive_shot_id"),
                         "SC02_SH02")
        self.assertEqual(self.shot["shot_type"], "medium_close_up")

    def test_scale_stays_mcu(self):
        self.assertEqual(
            float(self.result["crop_anchor"]["scale"]), 1.6,
            "a 320px retreat must not widen the MCU to full frame")

    def test_heads_read_mcu_scale(self):
        heads = _cropped_heads(self.result)
        linh = [h for h in heads if h[1] == "Linh"]
        self.assertTrue(linh)
        mid = linh[len(linh) // 2]
        self.assertGreaterEqual(
            mid[4], 250.0,
            f"Linh head diameter {mid[4]:.0f}px is establishing "
            "scale, not MCU (delivered R7: 148px)")

    def test_walker_stays_in_frame(self):
        heads = _cropped_heads(self.result)
        last = max(h[0] for h in heads)
        for frame, name, cx, _cy, diam in heads:
            if frame == last:
                self.assertGreaterEqual(cx - diam / 2.0, 0.0)
                self.assertLessEqual(cx + diam / 2.0, 1920.0)

    def test_no_head_intrusions(self):
        self.assertEqual(self.result.get("head_intrusion_count"), 0)


if __name__ == "__main__":
    unittest.main()
