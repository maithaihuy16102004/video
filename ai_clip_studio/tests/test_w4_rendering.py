"""W4 rendering tests: furniture staging, seated carry-over across
cuts, pen-tip contact, prop depth order + draw observability, and
still time-stepping.

The integration tests render real Ep1 shots (still_only) through
_render_shot with compiled actions attached, the way product_flow
stage 7a supplies them. The scene-2 map shots are skipped: they fail
loudly without a 1914 dataset decision (covered by
test_environment_w2), and this file tests the action/prop wiring.
"""
import math
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import build_environment
from ai_clip_studio.product_renderer import (
    H,
    W,
    _draw_prop,
    _furniture_anchors,
    _render_shot,
    _shot_location_kind,
    plan_shots,
)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _knee_angle(joints, side="r"):
    hip = joints["hip"]
    knee = joints["knee_" + side]
    foot = joints["foot_" + side]
    ax, ay = hip[0] - knee[0], hip[1] - knee[1]
    bx, by = foot[0] - knee[0], foot[1] - knee[1]
    dot = ax * bx + ay * by
    mag = math.hypot(ax, ay) * math.hypot(bx, by)
    if mag == 0:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / mag))))


class TestDrawPropWalletFlap(unittest.TestCase):
    def test_barely_open_wallet_flap_never_crashes(self):
        # Ep1 re-render crash: open_u ~0.06 gives a ~2 px flap,
        # narrower than PIL rounded_rectangle's 2*radius + 2 for
        # radius 6 ("x1 must be greater than or equal to x0").
        # Every open_u across the OPEN interpolation must draw.
        for open_u in (0.0, 0.05, 0.06, 0.1, 0.2, 0.34, 0.5, 1.0):
            img = Image.new("RGB", (200, 200), "white")
            d = ImageDraw.Draw(img)
            _draw_prop(d, 100, 100, kind="wallet", open_u=open_u)


class TestDrawPropPenTip(unittest.TestCase):
    def test_held_pen_nib_at_tip(self):
        img = Image.new("RGB", (300, 300), (255, 255, 255))
        d = ImageDraw.Draw(img)
        _draw_prop(d, 100, 100, kind="pen", tip=(150, 180))
        px = img.load()
        # Nib-coloured pixels cluster at the tip end.
        nib = [(x, y) for x in range(130, 170) for y in range(160, 200)
               if px[x, y] == (200, 200, 210)]
        self.assertTrue(nib, "no nib pixels near the tip")
        # Barrel pixels along the hand->tip segment.
        barrel = [(x, y) for x in range(100, 150) for y in range(100, 180)
                  if px[x, y] == (40, 40, 60)]
        self.assertTrue(len(barrel) >= 20, "no barrel along hand->tip")

    def test_rest_pen_keeps_legacy_shape(self):
        img = Image.new("RGB", (300, 300), (255, 255, 255))
        d = ImageDraw.Draw(img)
        _draw_prop(d, 150, 150, kind="pen")
        px = img.load()
        nib = [(x, y) for x in range(150, 200) for y in range(100, 160)
               if px[x, y] == (200, 200, 210)]
        self.assertTrue(nib, "legacy rest pen lost its nib")


class TestFurnitureAnchors(unittest.TestCase):
    def _anchors(self):
        traits = {
            "kind": "interior",
            "features": ["bàn gỗ", "ghế gỗ", "tủ hồ sơ",
                         "văn phòng", "cửa sổ"],
            "forbidden": [],
        }
        pkg = build_environment(traits, time_of_day="day")
        cam = viewpoint_for_shot("medium", "eye_level", (0.0, 1.2, 0.0))
        anchors = _furniture_anchors(pkg, cam, (W, H), 960, 900, 560, 1)
        return pkg, cam, anchors

    def test_paper_is_the_desk_paper(self):
        _pkg, cam, anchors = self._anchors()
        paper = anchors["paper"]
        self.assertEqual(anchors["source"], "environment")
        # Desk paper world centre (0.9, 0.84, -1.1); cabinet papers
        # sit at x=-4.6 and must never be the writing surface.
        ex, ey, _s, vis = cam.project((0.9, 0.84, -1.1), W, H)
        self.assertTrue(vis)
        cx = paper["x"] + paper["w"] / 2.0
        cy = paper["y"] + paper["h"] / 2.0
        self.assertAlmostEqual(cx, ex, delta=2.0)
        self.assertAlmostEqual(cy, ey, delta=2.0)

    def test_seat_y_is_the_projected_seat_top(self):
        _pkg, cam, anchors = self._anchors()
        chair = anchors["chair"]
        # Chair seat top: centre y 0.45 + half height 0.04.
        _ex, ey, _s, vis = cam.project((1.2, 0.49, -0.35), W, H)
        self.assertTrue(vis)
        self.assertAlmostEqual(chair["seat_y"], ey, delta=3.0)


def _ep1_package_and_shots():
    text = (EXAMPLES / "hitler_ep01_munich_1914.studio.md").read_text(
        encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(9)])
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


class TestW4RenderIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.shots = _ep1_package_and_shots()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name)
        cls.results = {}
        for s in cls.shots:
            if s.get("kind") == "end_card":
                continue  # camera-less by design, no W4 fields
            if _shot_location_kind(s) == "map_panel":
                # Map shots fail loudly without a 1914 dataset
                # decision (covered by test_environment_w2). Note
                # scene 5's narration shot is a map shot too (the
                # location override), so the skip is by location
                # kind, not by scene number.
                continue
            cls.results[s["index"]] = _render_shot({
                "shot": s, "package": cls.package,
                "out_dir": str(cls.out / f"shot_{s['index']:02d}"),
                "still_only": True,
            })

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_office_lead_seated_at_chair(self):
        r = self.results[5]
        self.assertEqual(r["furniture_staging"],
                         {"Adolf Hitler": (1.2, -0.35)})
        self.assertEqual(r["seated_at_start"], {"Adolf Hitler": True})
        self.assertEqual(r["action_dispatch_fallback"], [])
        self.assertTrue(r["prop_machine"])
        draws = dict(r["prop_draws"])
        self.assertEqual(draws.get("prop_pen"), "IN_USE")

    def test_office_line_shot_animates_sit_and_stays_seated(self):
        r = self.results[8]
        self.assertEqual(r["furniture_staging"],
                         {"Adolf Hitler": (1.2, -0.35)})
        # The shot carrying the SIT event animates it; it does not
        # start seated.
        self.assertEqual(r["seated_at_start"], {"Adolf Hitler": False})
        joints = r["joints_last_frame"]["Adolf Hitler"]
        # Still time-stepping: the sit ran before the hold_pen
        # window, so the knees are bent (standing reads ~180 deg).
        self.assertLess(_knee_angle(joints, "r"), 140.0)

    def test_wallet_put_away_before_scene1_line_shot(self):
        # Phase B: SC01_SH03 now renders, so the script's own
        # "Cất ví vào túi" (PUT_AWAY, 4.0-4.55 s) executes before
        # the line shot starts (5.8 s) — the wallet is correctly
        # NOT in hand. The old expectation (wallet in hand) was an
        # artifact of SH03 never rendering: its PUT_AWAY carried an
        # estimated span that never took effect.
        events = {e["action_id"]: e
                  for e in self.package["compiled_actions"]["events"]}
        put_away = events["SC01_SH03_ACT02"]
        self.assertEqual(put_away["action_type"], "PUT_AWAY")
        self.assertEqual(put_away["span_source"], "supplied")
        self.assertLess(put_away["end_time"],
                        self.shots[2]["start_sec"])
        r = self.results[2]
        draws = dict(r["prop_draws"])
        self.assertNotIn("prop_wallet", draws)
        # The bag was never taken out: pocket rest, never drawn.
        self.assertNotIn("prop_military_bag", draws)

    def test_no_cross_scene_prop_leak(self):
        r = self.results[16]
        draws = dict(r["prop_draws"])
        self.assertNotIn("prop_wallet", draws)

    def test_overflow_carry_is_flagged_not_silently_rendered(self):
        # SC05_SH02 carries 5 action sentences but a single 1.6 s
        # lead shot: the compiler flags overflow and the events
        # overrun the span, so the CARRY (and the later MARCHes)
        # render in NO shot. That loss must stay LOUD: the events
        # carry overflow=True, and no shot draws the bag. The
        # structural fix (lead durations from action content) is a
        # plan_shots behaviour change, flagged for P9 — not silently
        # papered over here by compressing the motion unreadably.
        events = {e["action_id"]: e
                  for e in self.package["compiled_actions"]["events"]}
        carry = events["SC05_SH02_ACT04"]
        self.assertEqual(carry["action_type"], "CARRY")
        self.assertTrue(carry["overflow"])
        for idx, r in sorted(self.results.items()):
            draws = dict(r["prop_draws"])
            self.assertNotIn(
                "prop_military_bag", draws,
                f"shot {idx} draws a bag no rendered event carries")

    def test_all_directives_render_with_supplied_spans(self):
        # Phase B: every Ep1 directive drives a shot, so every
        # directive's events carry supplied (measured) spans —
        # including SC01_SH03, which the old planner dropped. The
        # estimated-span path survives for directives with no
        # supplied span (verified below with SH03 deliberately
        # omitted from the spans dict).
        events = {e["action_id"]: e
                  for e in self.package["compiled_actions"]["events"]}
        self.assertEqual(
            events["SC01_SH03_ACT02"]["span_source"], "supplied")
        self.assertEqual(
            events["SC01_SH02_ACT02"]["span_source"], "supplied")

    def test_estimated_spans_for_directives_without_supplied_span(self):
        from ai_clip_studio.action_compiler import compile_actions
        spans = {}
        clock = 0.0
        for s in self.shots:
            did = s.get("directive_shot_id")
            if did and did != "SC01_SH03":
                span = spans.setdefault(str(did), [clock, clock])
                span[1] = clock + float(s["duration"])
            clock += float(s["duration"])
        events, _ = compile_actions(
            self.package, timeline={"spans": spans})
        by_id = {e["action_id"]: e for e in events}
        self.assertEqual(
            by_id["SC01_SH03_ACT02"]["span_source"], "estimated")
        self.assertEqual(
            by_id["SC01_SH02_ACT02"]["span_source"], "supplied")

    def test_no_dispatch_fallbacks_anywhere(self):
        for idx, r in sorted(self.results.items()):
            self.assertEqual(
                r["action_dispatch_fallback"], [],
                f"shot {idx} fell back to idle for "
                f"{r['action_dispatch_fallback']}")


if __name__ == "__main__":
    unittest.main()
