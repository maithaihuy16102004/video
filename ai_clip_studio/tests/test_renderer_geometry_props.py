"""Renderer geometry consumption (A2 wiring item 7): _draw_prop draws
the 13 geometry kinds from semantic specs, rest assignment follows
the ground rule, and gripping fingers repaint over held props.

Legacy hand-drawn shapes (wallet/pen/...) are untouched: their
pixel-pinned tests in test_w4_rendering.py + the distinct-shapes
test in test_engine_stage3_locations_props.py guard them.
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.lighting import MATERIAL_CATALOG
from ai_clip_studio.product_renderer import (
    INK_RGB, _GEOMETRY_PROP_KINDS, _GEOMETRY_SLOT_FILLS, _assign_prop_rests,
    _draw_prop, _render_shot, _shot_location_kind, plan_shots)
from ai_clip_studio.prop_system import (
    SemanticPropTracker, geometry_for_prop)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.action_compiler import compile_actions

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _canvas(kind, w=76, h=50):
    img = Image.new("RGB", (200, 160), (255, 255, 255))
    _draw_prop(ImageDraw.Draw(img), 100, 80, kind=kind, w=w, h=h)
    return np.asarray(img).astype(int)


class TestGeometryDrawPath(unittest.TestCase):
    def test_thirteen_geometry_kinds(self):
        self.assertEqual(len(_GEOMETRY_PROP_KINDS), 13)
        for kind in ("bolt", "hammer", "trident", "helmet", "sword",
                     "staff", "shield", "crown", "ring", "hat",
                     "chain", "stone", "boulder"):
            self.assertIn(kind, _GEOMETRY_PROP_KINDS)

    def test_every_geometry_slot_has_a_fill(self):
        for kind in sorted(_GEOMETRY_PROP_KINDS):
            spec = geometry_for_prop({"id": "p", "kind": kind}, H=560)
            for slot in spec["material_slots"]:
                with self.subTest(kind=kind, slot=slot):
                    self.assertIn(slot, _GEOMETRY_SLOT_FILLS)

    def test_bolt_fill_reads_at_default_footprint(self):
        # The outline width scales with the footprint: at the
        # default 76x50 footprint the fixed 3px outline measured
        # 392 ink vs 48 gold pixels and the bolt read as a dark
        # blob. The fill must now dominate the outline.
        arr = _canvas("bolt")
        core = np.array(
            MATERIAL_CATALOG["gold-emissive"]["base_color"])
        gold = int(((arr == core).all(axis=2)).sum())
        ink = int(((arr == np.array(INK_RGB)).all(axis=2)).sum())
        self.assertGreater(gold, 100)
        self.assertGreater(gold, ink)

    def test_geometry_kinds_draw_nonempty_and_distinct(self):
        generic = _canvas("generic")
        canvases = {}
        for kind in sorted(_GEOMETRY_PROP_KINDS):
            arr = _canvas(kind)
            canvases[kind] = arr
            painted = int((np.abs(arr - 255).sum(axis=2) > 0).sum())
            self.assertGreater(painted, 50, kind)
            diff = float(np.abs(arr - generic).mean())
            self.assertGreater(diff, 1.0, f"{kind} == generic box")
        kinds = sorted(canvases)
        # Footprint-region comparison (see the distinct-shapes
        # test): full-canvas means dilute thin geometry shapes.
        y0, y1, x0, x1 = 45, 115, 52, 148
        worst = None
        for i, a in enumerate(kinds):
            for b in kinds[i + 1:]:
                diff = float(np.abs(
                    canvases[a][y0:y1, x0:x1]
                    - canvases[b][y0:y1, x0:x1]).mean())
                if worst is None or diff < worst[0]:
                    worst = (diff, a, b)
        self.assertGreater(worst[0], 1.0, worst)

    def test_grip_mapping_chain_hangs_below_stone_centred(self):
        chain = _canvas("chain")
        mask = (np.abs(chain - 255).sum(axis=2) > 0)
        ys, _xs = np.nonzero(mask)
        # Grip at the top link's centre: the first link straddles
        # the grip point (one link radius + stroke above it), but
        # the mass hangs below it.
        self.assertGreaterEqual(int(ys.min()), 70)
        self.assertGreater(int(ys.max()), 100)
        self.assertGreater(float((ys > 80).mean()), 0.8)
        stone = _canvas("stone")
        mask = (np.abs(stone - 255).sum(axis=2) > 0)
        ys, xs = np.nonzero(mask)
        # Grip at the centre: paint surrounds (100, 80).
        self.assertLess(int(ys.min()), 80)
        self.assertGreater(int(ys.max()), 80)
        self.assertLess(int(xs.min()), 100)
        self.assertGreater(int(xs.max()), 100)


class TestRestAssignment(unittest.TestCase):
    def _setup(self, events):
        prop_dicts = {"prop_wallet": {"id": "prop_wallet",
                                      "kind": "wallet"},
                      "prop_letter": {"id": "prop_letter",
                                      "kind": "letter"}}
        props = [prop_dicts["prop_wallet"], prop_dicts["prop_letter"]]
        tracker = SemanticPropTracker(props, events)
        return prop_dicts, tracker

    def _assign(self, pids, prop_dicts, tracker):
        return _assign_prop_rests(
            pids, prop_dicts, {}, "Adolf Hitler",
            {"Adolf Hitler": {"paper": {"x": 100.0, "y": 200.0,
                                        "w": 80.0, "h": 60.0}}},
            {"Adolf Hitler": {"hip": (500.0, 600.0)}},
            {"Adolf Hitler": 900.0},
            {"Adolf Hitler": 400.0},
            {"Adolf Hitler": "CHAR_HITLER"},
            tracker=tracker, fallback_ground_y=900.0)

    def test_ground_pickup_rests_on_ground(self):
        events = [{"action_id": "A1", "action_type": "BEND_PICK",
                   "actor_id": "CHAR_HITLER", "prop_id": "prop_wallet",
                   "start_time": 0.0, "end_time": 1.0,
                   "semantic_action_type": "BEND_PICK",
                   "required_pose": {"params": {"hand": "r"}}}]
        prop_dicts, tracker = self._setup(events)
        self.assertEqual(tracker.initial_location("prop_wallet"),
                         "ON_GROUND")
        rests, kinds, _anchors = self._assign(
            ["prop_wallet"], prop_dicts, tracker)
        self.assertEqual(kinds["prop_wallet"], "ground")
        self.assertEqual(rests["prop_wallet"], (620.0, 900.0))

    def test_pocket_take_rests_in_pocket(self):
        events = [{"action_id": "A1", "action_type": "TAKE_OUT",
                   "actor_id": "CHAR_HITLER", "prop_id": "prop_wallet",
                   "start_time": 0.0, "end_time": 1.0,
                   "semantic_action_type": "TAKE_FROM_POCKET",
                   "required_pose": {"params": {"hand": "r"}}}]
        prop_dicts, tracker = self._setup(events)
        self.assertEqual(tracker.initial_location("prop_wallet"),
                         "IN_POCKET")
        _rests, kinds, _anchors = self._assign(
            ["prop_wallet"], prop_dicts, tracker)
        self.assertEqual(kinds["prop_wallet"], "pocket")

    def test_surface_kind_without_ground_semantics_stays_surface(self):
        prop_dicts, tracker = self._setup([])
        _rests, kinds, _anchors = self._assign(
            ["prop_letter"], prop_dicts, tracker)
        self.assertEqual(kinds["prop_letter"], "surface")

    def test_unknown_location_never_grounds(self):
        prop_dicts, tracker = self._setup([])
        _rests, kinds, _anchors = self._assign(
            ["prop_wallet"], prop_dicts, tracker)
        self.assertEqual(kinds["prop_wallet"], "pocket")


class TestEp1PocketRestRender(unittest.TestCase):
    def test_wallet_rest_is_pocket_not_ground(self):
        # The contamination regression at the real render path:
        # Ep1's wallet comes FROM THE POCKET, so no shot may rest
        # it on the ground.
        text = (EXAMPLES / "hitler_ep01_munich_1914.studio.md"
                ).read_text(encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(text))
        shots = plan_shots(
            package, [{"line_index": i + 1, "duration": 3.0}
                      for i in range(9)])
        for i, s in enumerate(shots):
            s["index"] = i
        spans, clock = {}, 0.0
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
            "spans_supplied": True, "compile_error": None}
        with tempfile.TemporaryDirectory() as tmp:
            shot0 = shots[0]
            self.assertNotEqual(
                _shot_location_kind(shot0), "map_panel")
            result = _render_shot({
                "shot": shot0, "package": package,
                "out_dir": str(Path(tmp) / "shot_00"),
                "still_only": True,
            })
        self.assertIn("prop_wallet", result["prop_rest_kinds"])
        self.assertEqual(
            result["prop_rest_kinds"]["prop_wallet"], "pocket")


if __name__ == "__main__":
    unittest.main()
