"""Hero prop insert grammar (RicksClips loop round 2): an
object_insert frames the PROP with the holder hand(s) as context
-- never the face. The subject box is sized from the prop's own
footprint with a bounded hand expansion, the anchor centre comes
from prop/hand pairs (the hold phase), and the scale ladder tops
at 5.0 for inserts so the prop occupies a readable frame share.
"""
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.camera_planner import SHOT_SCALE, safe_frame
from ai_clip_studio.product_renderer import (
    _insert_anchor_subjects,
    _insert_subject_box,
    _render_shot,
    plan_shots,
)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.tests.test_insert_two_pass import (
    _zeus_package_and_shots,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


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


class TestInsertSubjectBox(unittest.TestCase):
    def test_small_prop_uses_floor(self):
        # bolt 76x156 x 1.5 = 114x234 -> floored to 180x234
        # (round 6: the aspect-preserving footprint replaced the
        # old 76x50 box that squashed the tall bolt spec to
        # 24x50; the floor now binds the width only).
        box, fields = _insert_subject_box(500.0, 300.0, "bolt")
        self.assertEqual(box, {"cx": 500.0, "head_y": 183.0,
                               "foot_y": 417.0, "half_w": 90.0})
        self.assertEqual((fields["prop_w"], fields["prop_h"]),
                         (76.0, 156.0))
        self.assertEqual((fields["box_w"], fields["box_h"]),
                         (180.0, 234.0))
        self.assertFalse(fields["hands_included"])

    def test_tall_prop_keeps_height(self):
        # trident 76x170 x 1.5 = 114x255 -> 180x255.
        box, fields = _insert_subject_box(500.0, 300.0, "trident")
        self.assertEqual((fields["box_w"], fields["box_h"]),
                         (180.0, 255.0))
        self.assertEqual(box["head_y"], 172.5)
        self.assertEqual(box["foot_y"], 427.5)

    def test_wide_prop_keeps_width(self):
        # hammer 110x110 x 1.5 = 165x165 -> 180x165.
        _box, fields = _insert_subject_box(500.0, 300.0, "hammer")
        self.assertEqual((fields["box_w"], fields["box_h"]),
                         (180.0, 165.0))

    def test_near_hand_expands_box(self):
        box, fields = _insert_subject_box(500.0, 300.0, "bolt",
                                          (540.0, 280.0))
        self.assertTrue(fields["hands_included"])
        # Hand box (480..600, 220..340) unions with the prop box
        # (410..590, 183..417): only x1 moves -- the hand sits
        # inside the taller footprint box vertically.
        self.assertEqual(box["cx"], 505.0)
        self.assertEqual(box["head_y"], 183.0)
        self.assertEqual(box["foot_y"], 417.0)
        self.assertEqual(box["half_w"], 95.0)

    def test_far_hand_cannot_balloon_box(self):
        # Hand 300px above the prop: the expansion is capped at
        # one prop-box half-extent per edge, so the box grows to
        # at most 2x the prop box in the hand direction.
        box, fields = _insert_subject_box(500.0, 300.0, "bolt",
                                          (500.0, 0.0))
        self.assertTrue(fields["hands_included"])
        self.assertEqual(box["head_y"], 66.0)  # cy - box_h
        self.assertEqual(box["foot_y"], 417.0)
        self.assertEqual((fields["box_w"], fields["box_h"]),
                         (180.0, 351.0))
        # The old union rule would have framed y -60..417.
        self.assertGreater(box["head_y"], 0.0)

    def test_unknown_kind_uses_default_footprint(self):
        _box, fields = _insert_subject_box(500.0, 300.0, "nope")
        self.assertEqual((fields["prop_w"], fields["prop_h"]),
                         (76.0, 50.0))


class TestPairAnchoring(unittest.TestCase):
    def _entry(self, draws, hands=None):
        return {"t": 0.0, "frame": 0, "hands": hands or {},
                "draws": draws}

    def test_hold_phase_anchors_travelling_prop(self):
        # 10 draws travelling x=100..1000; only the last 4 are
        # held (holder + hand). The anchor sits at the hold
        # phase, not the all-draw median (550).
        tel = []
        for i, x in enumerate(range(100, 1100, 100)):
            if i < 6:
                tel.append(self._entry([{"kind": "stone",
                                         "x": float(x),
                                         "y": 300.0}]))
            else:
                tel.append(self._entry(
                    [{"kind": "stone", "x": float(x), "y": 300.0,
                      "holder": "Hero", "hand": "r"}],
                    {"Hero": {"hand_r": [float(x), 310.0]}}))
        _subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertTrue(anchor["pair_anchored"])
        self.assertEqual(anchor["n_pairs"], 4)
        self.assertEqual(anchor["x"], 850.0)
        self.assertEqual(anchor["hand_x"], 850.0)
        self.assertEqual(anchor["hand_y"], 310.0)
        self.assertTrue(anchor["hands_included"])

    def test_holderless_falls_back_to_all_draw_median(self):
        tel = [self._entry([{"kind": "stone", "x": float(x),
                              "y": 300.0}])
               for x in (100, 200, 300)]
        _subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertFalse(anchor["pair_anchored"])
        self.assertEqual(anchor["n_pairs"], 0)
        self.assertEqual((anchor["x"], anchor["y"]),
                         (200.0, 300.0))
        self.assertFalse(anchor["hands_included"])
        self.assertNotIn("hand_x", anchor)

    def test_pairs_of_other_kinds_ignored(self):
        tel = [self._entry([{"kind": "bolt", "x": 500.0,
                              "y": 300.0}]),
               self._entry([{"kind": "stone", "x": 100.0,
                              "y": 100.0, "holder": "Hero",
                              "hand": "r"}],
                           {"Hero": {"hand_r": [100.0, 100.0]}}),
               self._entry([{"kind": "bolt", "x": 510.0,
                              "y": 310.0}]),
               self._entry([{"kind": "bolt", "x": 520.0,
                              "y": 320.0}])]
        # bolt dominates (3 draws); the stone pair must not
        # anchor the bolt box.
        _subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertEqual(anchor["kind"], "bolt")
        self.assertFalse(anchor["pair_anchored"])
        self.assertEqual((anchor["x"], anchor["y"]),
                         (510.0, 310.0))

    def test_draw_without_coordinates_skipped(self):
        tel = [self._entry([{"kind": "bolt"}]),
               self._entry([{"kind": "bolt", "x": 500.0,
                              "y": 300.0}])]
        _subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertEqual(anchor["n_draws"], 1)
        self.assertEqual((anchor["x"], anchor["y"]),
                         (500.0, 300.0))

    def test_off_frame_median_clamps_to_edge(self):
        # A prop staged half off-frame (Zeus scene-10 insert
        # median x < 0): the anchor clamps to the frame edge so
        # the crop centres on the visible part, and the record
        # keeps the raw median for staging diagnostics.
        tel = [self._entry([{"kind": "stone", "x": -22.0,
                              "y": 300.0}])]
        _subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertEqual((anchor["x"], anchor["y"]),
                         (0.0, 300.0))
        self.assertTrue(anchor["clamped_to_frame"])
        self.assertEqual(anchor["raw_x"], -22.0)


class TestHeadLean(unittest.TestCase):
    def _entry(self, draw, joints):
        return {"t": 0.0, "frame": 0, "hands": {"Hero": joints},
                "draws": [draw]}

    def _held(self, x, y, head, head_r=120.0):
        return self._entry(
            {"kind": "bolt", "x": x, "y": y,
             "holder": "Hero", "hand": "r"},
            {"hand_r": [x + 10.0, y + 10.0], "head": list(head),
             "head_r": head_r})

    def test_lean_shifts_box_away_from_close_head(self):
        # Head 150px above the prop (inside 2x head_r): the box
        # translates DOWN, capped so the prop stays inside. The
        # hand at (510, 310) sits inside the 180x234 footprint
        # box, so the y cap is 117 - 78 - 8 = 31.
        tel = [self._held(500.0, 300.0, (500.0, 150.0))]
        subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertIn("lean", anchor)
        self.assertEqual(anchor["lean"]["shift_x"], 0.0)
        self.assertEqual(anchor["lean"]["shift_y"], 31.0)
        self.assertEqual(subjects[0]["head_y"], 214.0)
        self.assertEqual(subjects[0]["foot_y"], 448.0)
        # The anchor point itself does not move.
        self.assertEqual((anchor["x"], anchor["y"]),
                         (500.0, 300.0))

    def test_lean_gated_off_for_far_head(self):
        tel = [self._held(500.0, 300.0, (900.0, 300.0))]
        _subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertNotIn("lean", anchor)

    def test_lean_gated_off_without_pairs(self):
        tel = [{"t": 0.0, "frame": 0,
                "hands": {"Hero": {"head": [500.0, 150.0],
                                   "head_r": 120.0}},
                "draws": [{"kind": "bolt", "x": 500.0,
                           "y": 300.0}]}]
        _subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertNotIn("lean", anchor)

    def test_lean_without_head_telemetry_is_safe(self):
        tel = [{"t": 0.0, "frame": 0,
                "hands": {"Hero": {"hand_r": [510.0, 310.0]}},
                "draws": [{"kind": "bolt", "x": 500.0, "y": 300.0,
                           "holder": "Hero", "hand": "r"}]}]
        subjects, anchor = _insert_anchor_subjects(tel, [])
        self.assertNotIn("lean", anchor)
        self.assertTrue(anchor["pair_anchored"])


class TestInsertLadder(unittest.TestCase):
    def _subjects(self, w=180.0, h=110.0):
        return [{"cx": 960.0, "head_y": 540.0 - h / 2.0,
                 "foot_y": 540.0 + h / 2.0, "half_w": w / 2.0}]

    def test_insert_planned_scale_is_five(self):
        self.assertEqual(SHOT_SCALE["object_insert"], 5.0)
        self.assertEqual(SHOT_SCALE["extreme_close_up"], 3.4)

    def test_tight_insert_holds_five(self):
        shot = {"shot_type": "object_insert",
                "camera": {"scale": 5.0}}
        safe, _focus, _notes = safe_frame(
            shot, (960.0, 540.0), self._subjects(), [])
        self.assertEqual(safe["camera"]["scale"], 5.0)

    def test_big_subject_steps_down(self):
        shot = {"shot_type": "object_insert",
                "camera": {"scale": 5.0}}
        safe, _focus, _notes = safe_frame(
            shot, (960.0, 540.0), self._subjects(1200.0, 700.0),
            [])
        self.assertLess(safe["camera"]["scale"], 5.0)

    def test_ecu_cannot_reach_five(self):
        shot = {"shot_type": "extreme_close_up",
                "camera": {"scale": 3.4}}
        safe, _focus, _notes = safe_frame(
            shot, (960.0, 540.0), self._subjects(), [])
        self.assertEqual(safe["camera"]["scale"], 3.4)

    def test_medium_ladder_unchanged(self):
        shot = {"shot_type": "medium", "camera": {"scale": 1.6}}
        safe, _focus, _notes = safe_frame(
            shot, (960.0, 540.0), self._subjects(), [])
        self.assertEqual(safe["camera"]["scale"], 1.6)


class TestHeroInsertRenders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name)
        cls.results = {}
        zpackage, zshots = _zeus_package_and_shots()
        bolt = next(s for s in zshots
                    if s.get("directive_shot_id") == "SC08_SH02")
        cls.results["bolt"] = _render_shot({
            "shot": bolt, "package": zpackage,
            "out_dir": str(cls.out / "bolt")})
        cls.results["bolt"]["_out_dir"] = cls.out / "bolt"
        scene10 = next(s for s in zshots
                       if str(s.get("scene")) == "10"
                       and s.get("shot_type") == "object_insert")
        cls.results["scene10"] = _render_shot({
            "shot": scene10, "package": zpackage,
            "out_dir": str(cls.out / "scene10")})
        cls.results["scene10"]["_out_dir"] = cls.out / "scene10"
        epackage, eshots = _ep1_package_and_shots()
        pen = next(s for s in eshots
                   if str(s.get("scene")) == "3"
                   and s.get("shot_type") == "object_insert"
                   and s.get("prop_kind") == "pen")
        cls.results["pen"] = _render_shot({
            "shot": pen, "package": epackage,
            "out_dir": str(cls.out / "pen")})
        cls.results["pen"]["_out_dir"] = cls.out / "pen"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _check_insert_contract(self, key):
        r = self.results[key]
        self.assertEqual(r["shot_type"], "object_insert")
        self.assertTrue(r["insert_two_pass"])
        anchor = r["insert_anchor"]
        self.assertEqual(anchor["source"], "telemetry_median")
        self.assertGreater(anchor["n_draws"], 0)
        # The frozen crop contains the anchor point.
        x0, y0, x1, y1 = r["crop_anchor"]["crop_rect"]
        self.assertLessEqual(x0, anchor["x"])
        self.assertLessEqual(anchor["x"], x1)
        self.assertLessEqual(y0, anchor["y"])
        self.assertLessEqual(anchor["y"], y1)
        # Hero share: the prop occupies a readable fraction of
        # the frame in its LONG dimension at the applied scale.
        # A tall prop (the bolt's true footprint is 76x156) is
        # legitimately narrow, so the width share alone
        # understates its readability; the height share is the
        # honest measure for it.
        self.assertGreaterEqual(anchor["applied_scale"], 3.4)
        _cw = x1 - x0
        _ch = y1 - y0
        _share = max(anchor["prop_w"] / _cw,
                     anchor["prop_h"] / _ch)
        self.assertGreaterEqual(_share, 0.15)
        # The mid frame is not empty at the centre: prop/hand
        # ink is present where the insert points.
        frames = sorted(r["_out_dir"].rglob("f*.png"))
        arr = np.asarray(
            Image.open(frames[len(frames) // 2]).convert("RGB")
        ).astype(float)
        centre = arr[330:750, 660:1260]
        ink = ((centre[:, :, 0] < 60) & (centre[:, :, 1] < 60)
               & (centre[:, :, 2] < 60)).sum()
        self.assertGreater(ink, 200)
        return r

    def test_bolt_handover_is_hero_framed(self):
        r = self._check_insert_contract("bolt")
        anchor = r["insert_anchor"]
        self.assertEqual(anchor["kind"], "bolt")
        self.assertTrue(anchor["pair_anchored"])
        # The exchange happens at chest height between two facing
        # characters, so the holder's head is near the bolt: the
        # lean must fire, shifting the framing box AWAY from the
        # head so the face does not dominate the insert (verified
        # on the rendered frame: chin arcs only, no eyes/mouth).
        self.assertIn("lean", anchor)
        lean = anchor["lean"]
        dx = anchor["x"] - lean["head_x"]
        dy = anchor["y"] - lean["head_y"]
        self.assertGreater(lean["shift_x"] * dx
                           + lean["shift_y"] * dy, 0.0)
        self.assertGreater(math.hypot(lean["shift_x"],
                                      lean["shift_y"]), 10.0)

    def test_pen_insert_is_hero_framed(self):
        r = self._check_insert_contract("pen")
        anchor = r["insert_anchor"]
        self.assertEqual(anchor["kind"], "pen")
        # The holder's head bows close to the pen while writing:
        # the lean must fire, shifting the framing box AWAY from
        # the head (dot product of shift and prop-minus-head > 0)
        # so the face does not dominate the insert.
        self.assertIn("lean", anchor)
        lean = anchor["lean"]
        dx = anchor["x"] - lean["head_x"]
        dy = anchor["y"] - lean["head_y"]
        self.assertGreater(lean["shift_x"] * dx
                           + lean["shift_y"] * dy, 0.0)
        self.assertGreater(math.hypot(lean["shift_x"],
                                      lean["shift_y"]), 10.0)

    def test_scene10_insert_renders(self):
        # History: the stone used to stage OFF-FRAME for the
        # whole shot (the legacy prop path followed Zeus's hand
        # at x ~ -32), and this test pinned the clamp response.
        # The round-6 staging fit pulls fittable staging into
        # the frame, so the defect is gone: the stone now
        # renders on-frame, centred and visible at 5.0x (mid
        # frame READ: grey stone with a crack mark, held at the
        # hand). The clamp path itself is still pinned by
        # test_off_frame_median_clamps_to_edge; here the honest
        # assertion is the visible prop, including centre ink.
        r = self.results["scene10"]
        self.assertEqual(r["shot_type"], "object_insert")
        self.assertTrue(r["insert_two_pass"])
        anchor = r["insert_anchor"]
        self.assertEqual(anchor["source"], "telemetry_median")
        self.assertEqual(anchor["kind"], "stone")
        self.assertNotIn("clamped_to_frame", anchor)
        self.assertGreater(anchor["x"], 0.0)
        self.assertLess(anchor["x"], 1920.0)
        self.assertGreater(anchor["y"], 0.0)
        self.assertLess(anchor["y"], 1080.0)
        self.assertEqual(anchor["applied_scale"], 5.0)
        x0, y0, x1, y1 = r["crop_anchor"]["crop_rect"]
        self.assertLessEqual(x0, anchor["x"])
        self.assertLessEqual(anchor["x"], x1)
        self.assertLessEqual(y0, anchor["y"])
        self.assertLessEqual(anchor["y"], y1)
        frames = sorted(r["_out_dir"].rglob("f*.png"))
        arr = np.asarray(
            Image.open(frames[len(frames) // 2]).convert("RGB")
        ).astype(float)
        centre = arr[330:750, 660:1260]
        ink = ((centre[:, :, 0] < 60) & (centre[:, :, 1] < 60)
               & (centre[:, :, 2] < 60)).sum()
        self.assertGreater(ink, 200)
        self.assertLessEqual(y0, anchor["y"])
        self.assertLessEqual(anchor["y"], y1)
        self.assertGreaterEqual(anchor["applied_scale"], 3.4)
        self.assertGreaterEqual(anchor["screen_share_w"], 0.15)


if __name__ == "__main__":
    unittest.main()
