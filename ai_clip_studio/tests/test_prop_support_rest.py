"""Prop-on-support rest: any prop rests naturally on any support
surface (pedestal, desk, workbench, anvil, altar, cabinet) the
environment actually contains, its drawn bottom on the support's
projected top edge. No support is ever invented: a named support
the environment lacks falls back to the kind rule with a recorded
"missing:<name>" marker.
"""

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.action_compiler import (
    _normalize, compile_actions, destination_support_name,
    source_support_name)
from ai_clip_studio.environment_v2 import (
    build_environment, build_landmarks, render_environment,
    select_landmarks, _projected_bbox)
from ai_clip_studio.product_renderer import (
    PROP_KINDS, _assign_prop_rests, _draw_prop, _render_shot,
    _support_anchors, plan_shots, prop_bottom_offset)
from ai_clip_studio.prop_system import (
    SemanticPropTracker, geometry_footprint)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

FIXTURE = Path(__file__).resolve().parent / "fixtures" / \
    "unseen_garden_key.studio.md"


def _support(text, sem_type):
    return destination_support_name(_normalize(text), sem_type)


def _home(text, sem_type):
    return source_support_name(_normalize(text), sem_type)


class TestDestinationSupport(unittest.TestCase):
    def test_support_names(self):
        cases = [
            ("Tôi đặt viên đá lên bệ.", "pedestal"),
            ("Tôi đặt chén lên bệ thờ.", "altar"),
            ("Tôi đặt bút lên bàn.", "table"),
            ("Tôi đặt sách lên kệ.", "shelf"),
            ("Tôi đặt búa lên đe.", "anvil"),
            ("Tôi đặt hộp lên tủ.", "cabinet"),
            ("He puts the stone on the pedestal.", "pedestal"),
            ("She sets the cup on the table.", "table"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    _support(text, "PLACE_ON_SURFACE"), expected)

    def test_altar_beats_pedestal(self):
        # "lên bệ thờ" contains "lên bệ": altar must win.
        self.assertEqual(
            _support("Tôi đặt lễ vật lên bệ thờ.", "PLACE_ON_SURFACE"),
            "altar")

    def test_non_placements_name_nothing(self):
        self.assertIsNone(_support("Tôi nhìn lên bệ.", "LOOK_AT"))
        self.assertIsNone(
            _support("Tôi lấy bút trên bàn.", "PICK_FROM_SURFACE"))
        self.assertIsNone(_support("Tôi bước lên bệ.", "WALK"))

    def test_bare_nouns_name_nothing(self):
        # "đe dọa" (threaten) contains "đe" but no directional
        # support phrasing; bare "bàn" is not a placement.
        self.assertIsNone(
            _support("Tôi đe dọa hắn.", "PLACE_ON_SURFACE"))
        self.assertIsNone(
            _support("Tôi ngồi cạnh bàn.", "PLACE_ON_SURFACE"))

    def test_take_sources_name_the_home_support(self):
        cases = [
            ("Tôi lấy lõi đá trên bệ.", "PICK_FROM_SURFACE", "pedestal"),
            ("Tôi nhặt búa từ trên đe.", "BEND_PICK", "anvil"),
            ("Tôi lấy bút trên bàn.", "PICK_FROM_SURFACE", "table"),
            ("Tôi lấy sách từ kệ.", "TAKE", "shelf"),
            ("Tôi lấy chén từ bệ thờ.", "PICK_FROM_SURFACE", "altar"),
            ("He takes the box off the cabinet.", "TAKE", "cabinet"),
        ]
        for text, sem_type, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(_home(text, sem_type), expected)

    def test_pocket_and_ground_takes_name_nothing(self):
        self.assertIsNone(
            _home("Tôi lấy ví từ túi áo.", "TAKE_FROM_POCKET"))
        self.assertIsNone(
            _home("Tôi nhặt chìa khóa dưới đất.", "PICK_FROM_GROUND"))
        self.assertIsNone(
            _home("Tôi nhìn lên bệ.", "LOOK_AT"))

    def test_resting_sentences_name_the_home_support(self):
        # Round-7: a resting verb names the prop's home for ANY
        # semantic type -- the R6 insert showed the stone held
        # because "nằm trên đe" (EMIT) named no support.
        cases = [
            ("Viên đá nằm trên đe, phát sáng.", "EMIT", "anvil"),
            ("Viên đá nằm trên bệ, phát sáng.", "EMIT", "pedestal"),
            ("Lõi đá nằm trên bệ thờ.", "CRACK", "altar"),
            ("Chiếc nhẫn để trên bàn.", "IDLE", "table"),
            ("Cuốn sách đặt trên kệ.", "ACTIVATE", "shelf"),
            ("Chiếc hộp nằm trên tủ.", "EMIT", "cabinet"),
            ("The stone lies on the anvil, glowing.", "EMIT", "anvil"),
            ("The core rests on the pedestal.", "CRACK", "pedestal"),
        ]
        for text, sem_type, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(_home(text, sem_type), expected)

    def test_resting_altar_beats_pedestal(self):
        # "nằm trên bệ" is a substring of "nằm trên bệ thờ".
        self.assertEqual(
            _home("Lễ vật nằm trên bệ thờ.", "EMIT"), "altar")

    def test_bare_on_phrase_without_resting_verb_names_nothing(self):
        # A look or a walk past a support is not a rest.
        self.assertIsNone(
            _home("Cô ấy nhìn viên đá trên bàn.", "LOOK_AT"))
        self.assertIsNone(
            _home("Anh bước qua chiếc đe.", "WALK"))


class TestPedestalLandmark(unittest.TestCase):
    def test_select_pedestal(self):
        self.assertEqual(select_landmarks({"landmarks": ["bệ đá"]}),
                         ["pedestal"])
        self.assertEqual(select_landmarks({"landmarks": ["cái bệ"]}),
                         ["pedestal"])

    def test_pedestal_has_no_figure(self):
        elements = build_landmarks(
            {"landmarks": ["bệ đá"]}, __import__("random").Random(7),
            {"facade_colors": [(150, 140, 120), (140, 130, 110)]})
        kinds = [e["kind"] for e in elements]
        # Round-8: seven pieces (base + shaft + cap + 4 rim
        # bars); the no-figure contract is that no "statue"
        # element stands on it, and exactly one shaft carries
        # the support-anchor kind.
        self.assertEqual(set(kinds),
                         {"pedestal_trim", "statue_pedestal"})
        self.assertEqual(kinds.count("statue_pedestal"), 1)
        self.assertNotIn("statue", kinds)

    def test_pedestal_silhouette_reads(self):
        # Round-7/8: the silhouette must read as a pedestal, not
        # a crate -- a narrow shaft, a cap wider than the shaft
        # with a visible overhang, a light cap that catches the
        # light against dark walls, and a dark rim frame socketing
        # the placed object on the cap plane.
        elements = build_landmarks(
            {"landmarks": ["bệ đá"]}, __import__("random").Random(7),
            {"facade_colors": [(150, 140, 120), (140, 130, 110)]})
        base = next(e for e in elements
                    if e["id"].endswith("_pedestal_base"))
        shaft = next(e for e in elements
                     if e["kind"] == "statue_pedestal")
        cap = next(e for e in elements
                   if e["id"].endswith("_pedestal_cap"))
        rims = [e for e in elements if "rim" in e["id"]]
        self.assertLess(shaft["size"][0], base["size"][0])
        self.assertGreater(cap["size"][0], shaft["size"][0] + 0.3)
        top = shaft["center"][1] + shaft["size"][1] / 2.0
        self.assertAlmostEqual(top, 1.55, places=3)
        cap_top = cap["center"][1] + cap["size"][1] / 2.0
        self.assertAlmostEqual(cap_top, top, places=3)
        self.assertGreater(sum(cap["color"]), sum(shaft["color"]))
        self.assertEqual(len(rims), 4)
        for rim in rims:
            self.assertAlmostEqual(
                rim["center"][1] - rim["size"][1] / 2.0, top,
                places=3)
            self.assertLess(sum(rim["color"]), sum(cap["color"]))
        for element in elements:
            self.assertEqual(element["extra"]["landmark"],
                             "pedestal")


class TestLandmarksField(unittest.TestCase):
    def _text_with_landmarks(self):
        text = FIXTURE.read_text(encoding="utf-8")
        anchor = ("FORBIDDEN:\n* Không thay địa điểm khác\n\n"
                  "LOCATION: LOC_SHED")
        self.assertIn(anchor, text)
        return text.replace(
            anchor,
            "FORBIDDEN:\n* Không thay địa điểm khác\n"
            "LANDMARKS:\n* Tượng đá\n* Bệ đá\n\nLOCATION: LOC_SHED",
            1)

    def test_landmarks_reach_the_environment(self):
        package = adapt_document(parse_studio_script_v1(
            self._text_with_landmarks()))
        blocks = [s["location"]["v1_location"]
                  for s in package["scenes"]]
        garden = blocks[0]
        self.assertEqual(garden["landmarks"], ["Tượng đá", "Bệ đá"])
        pkg = build_environment(garden)
        kinds = [e["kind"] for e in pkg["elements"]]
        self.assertIn("statue_pedestal", kinds)
        self.assertIn("statue", kinds)


class TestSupportAnchors(unittest.TestCase):
    class _Cam:
        def project(self, point, w, h):
            x, y, _z = point
            if x > 100:
                return (0.0, 0.0, 1.0, False)
            return (960.0 + x * 100.0, 540.0 - y * 100.0, 1.0, True)

    def _el(self, el_id, kind, center, size, relation):
        return {"id": el_id, "kind": kind, "layer": "MG",
                "geometry": "box", "center": center, "size": size,
                "color": (100, 100, 100), "material": "wood",
                "attachment": {"parent": None, "relation": relation,
                               "local_rect": None}}

    def test_selection_and_projection(self):
        env = {"elements": [
            self._el("desk_top", "desk", (1.2, 0.78, -1.2),
                     (2.2, 0.08, 1.0), "on_top"),
            self._el("bench_leg_0", "workbench", (2.6, 0.37, -4.6),
                     (0.18, 0.74, 0.7), "on_ground"),
            self._el("bench_top", "workbench", (3.3, 0.78, -4.6),
                     (1.9, 0.08, 0.8), "on_top"),
            self._el("anvil_top", "anvil", (0.6, 0.78, -3.2),
                     (1.1, 0.16, 0.34), "on_top"),
            self._el("plaza_pedestal", "statue_pedestal", (0.0, 0.5, -7.0),
                     (1.0, 1.0, 1.0), "on_ground"),
            self._el("temple_altar", "altar", (0.0, 0.5, -3.4),
                     (1.2, 1.0, 0.6), "on_ground"),
            self._el("room_cabinet", "cabinet", (-4.6, 0.9, -5.4),
                     (1.4, 1.8, 0.5), "on_ground"),
            self._el("chair_seat", "chair", (1.2, 0.4, -0.35),
                     (0.5, 0.1, 0.5), "on_top"),
            self._el("desk_paper", "paper_stack", (0.9, 0.84, -1.1),
                     (0.45, 0.04, 0.3), "on_top"),
            self._el("far_pedestal", "statue_pedestal", (200.0, 0.5, -7.0),
                     (1.0, 1.0, 1.0), "on_ground"),
            {"id": "broken", "kind": "desk"},
        ]}
        anchors = _support_anchors(env, self._Cam(), (1920, 1080))
        by_id = {a["id"]: a for a in anchors}
        # Legs, chairs, paper, off-screen and malformed: excluded.
        self.assertEqual(set(by_id),
                         {"desk_top", "bench_top", "anvil_top",
                          "plaza_pedestal", "temple_altar",
                          "room_cabinet"})
        self.assertEqual(by_id["desk_top"]["support"], "table")
        self.assertEqual(by_id["bench_top"]["support"], "table")
        self.assertEqual(by_id["anvil_top"]["support"], "anvil")
        self.assertEqual(by_id["plaza_pedestal"]["support"], "pedestal")
        self.assertEqual(by_id["temple_altar"]["support"], "altar")
        self.assertEqual(by_id["room_cabinet"]["support"], "cabinet")
        # Top-face centre: pedestal top y = 0.5 + 1.0/2 = 1.0.
        ped = by_id["plaza_pedestal"]
        self.assertAlmostEqual(ped["x"], 960.0)
        self.assertAlmostEqual(ped["top_y"], 540.0 - 1.0 * 100.0)
        self.assertAlmostEqual(ped["width"], 100.0)

    def test_empty_without_package_or_camera(self):
        self.assertEqual(_support_anchors(None, self._Cam(),
                                          (1920, 1080)), [])
        self.assertEqual(_support_anchors({"elements": []}, None,
                                          (1920, 1080)), [])


class TestPropBottomOffset(unittest.TestCase):
    def _measured_bottom(self, kind):
        img = Image.new("RGB", (400, 400), (1, 2, 3))
        draw = ImageDraw.Draw(img, "RGBA")
        _draw_prop(draw, 200, 200, kind=kind)
        arr = np.array(img)
        mask = np.abs(arr.astype(int) - np.array([1, 2, 3])).sum(
            axis=2) > 0
        ys, _xs = np.nonzero(mask)
        return int(ys.max()) - 200

    def test_every_kind_matches_its_offset(self):
        for kind in sorted(PROP_KINDS):
            with self.subTest(kind=kind):
                measured = self._measured_bottom(kind)
                expected = prop_bottom_offset(kind)
                self.assertAlmostEqual(measured, expected, delta=4,
                                        msg=f"{kind}: measured "
                                        f"{measured} vs offset "
                                        f"{expected}")

    def test_geometry_offset_scales_with_footprint(self):
        small = prop_bottom_offset("stone", w=76, h=50)
        big = prop_bottom_offset("stone", w=152, h=100)
        self.assertAlmostEqual(big, 2.0 * small, places=6)

    def test_unknown_kind_uses_generic(self):
        self.assertEqual(prop_bottom_offset("nope"),
                         prop_bottom_offset("generic"))


class TestSupportRestAssignment(unittest.TestCase):
    def _assign(self, pids, prop_dicts, events, anchors_list):
        tracker = SemanticPropTracker(
            [prop_dicts[p] for p in pids], events)
        records: dict = {}
        rests, kinds, _pa = _assign_prop_rests(
            pids, prop_dicts, {}, "Bà Tư",
            {"Bà Tư": {"paper": {"x": 100.0, "y": 200.0,
                                 "w": 80.0, "h": 60.0}}},
            {"Bà Tư": {"hip": (500.0, 600.0)}},
            {"Bà Tư": 900.0},
            {"Bà Tư": 400.0},
            {"Bà Tư": "CHAR_GARDENER"},
            tracker=tracker, fallback_ground_y=900.0,
            events=events, support_anchors=anchors_list,
            support_records=records)
        return rests, kinds, records

    def _pedestal(self, x=960.0, top_y=400.0, width=200.0,
                  el_id="plaza_pedestal"):
        return [{"id": el_id, "kind": "statue_pedestal",
                 "support": "pedestal", "x": x, "top_y": top_y,
                 "width": width}]

    def _take_event(self, pid, aid="A0", source=None,
                    sem="BEND_PICK", action="BEND_PICK"):
        return {"action_id": aid, "action_type": action,
                "actor_id": "CHAR_GARDENER", "prop_id": pid,
                "start_time": 0.0, "end_time": 1.0,
                "semantic_action_type": sem,
                "source_support": source,
                "required_pose": {"params": {"hand": "r"}}}

    def _place_event(self, pid, support="pedestal", aid="A1"):
        return {"action_id": aid, "action_type": "RELEASE",
                "actor_id": "CHAR_GARDENER", "prop_id": pid,
                "start_time": 1.0, "end_time": 2.0,
                "semantic_action_type": "PLACE_ON_SURFACE",
                "destination_support": support,
                "required_pose": {"params": {"hand": "r"}}}

    def test_stone_rests_on_pedestal_top(self):
        prop_dicts = {"PROP_STONE": {"id": "PROP_STONE",
                                     "kind": "stone"}}
        rests, kinds, records = self._assign(
            ["PROP_STONE"], prop_dicts,
            [self._take_event("PROP_STONE"),
             self._place_event("PROP_STONE")], self._pedestal())
        self.assertEqual(kinds["PROP_STONE"], "support")
        self.assertEqual(records["PROP_STONE"], "plaza_pedestal")
        x, y = rests["PROP_STONE"]
        self.assertAlmostEqual(x, 960.0)
        self.assertAlmostEqual(
            y, 400.0 - prop_bottom_offset("stone"))

    def test_take_source_names_the_home_rest(self):
        # A take from the pedestal, with no placement in the shot:
        # the prop's home rest is the pedestal.
        prop_dicts = {"PROP_STONE": {"id": "PROP_STONE",
                                     "kind": "stone"}}
        rests, kinds, records = self._assign(
            ["PROP_STONE"], prop_dicts,
            [self._take_event("PROP_STONE", source="pedestal",
                              sem="PICK_FROM_SURFACE",
                              action="PICK_UP")],
            self._pedestal())
        self.assertEqual(kinds["PROP_STONE"], "support")
        self.assertEqual(records["PROP_STONE"], "plaza_pedestal")
        _x, y = rests["PROP_STONE"]
        self.assertAlmostEqual(
            y, 400.0 - prop_bottom_offset("stone"))

    def test_missing_support_falls_back_with_marker(self):
        prop_dicts = {"PROP_STONE": {"id": "PROP_STONE",
                                     "kind": "stone"}}
        _rests, kinds, records = self._assign(
            ["PROP_STONE"], prop_dicts,
            [self._take_event("PROP_STONE"),
             self._place_event("PROP_STONE")], [])
        # No pedestal in the environment: the ground rule applies
        # (initial ON_GROUND) and the miss is recorded.
        self.assertEqual(kinds["PROP_STONE"], "ground")
        self.assertEqual(records["PROP_STONE"], "missing:pedestal")

    def test_drop_beats_placement(self):
        prop_dicts = {"PROP_STONE": {"id": "PROP_STONE",
                                     "kind": "stone"}}
        take2 = self._take_event(
            "PROP_STONE", aid="A2", sem="PICK_FROM_SURFACE",
            action="PICK_UP")
        take2["start_time"] = 2.0
        take2["end_time"] = 3.0
        drop = {"action_id": "A3", "action_type": "RELEASE",
                "actor_id": "CHAR_GARDENER", "prop_id": "PROP_STONE",
                "start_time": 3.0, "end_time": 4.0,
                "semantic_action_type": "RELEASE_PROP",
                "required_pose": {"params": {"hand": "r"}}}
        _rests, kinds, _rec = self._assign(
            ["PROP_STONE"], prop_dicts,
            [self._take_event("PROP_STONE"),
             self._place_event("PROP_STONE"), take2, drop],
            self._pedestal())
        self.assertEqual(kinds["PROP_STONE"], "ground")

    def test_paper_rule_preserved_without_placement(self):
        prop_dicts = {"PROP_PEN": {"id": "PROP_PEN", "kind": "pen"}}
        _rests, kinds, _rec = self._assign(
            ["PROP_PEN"], prop_dicts, [], self._pedestal())
        self.assertEqual(kinds["PROP_PEN"], "surface")

    def test_two_props_spread_across_one_support(self):
        prop_dicts = {"PROP_A": {"id": "PROP_A", "kind": "stone"},
                      "PROP_B": {"id": "PROP_B", "kind": "stone"}}
        rests, kinds, _rec = self._assign(
            ["PROP_A", "PROP_B"], prop_dicts,
            [self._take_event("PROP_A", aid="A0"),
             self._place_event("PROP_A", aid="A1"),
             self._take_event("PROP_B", aid="A2"),
             self._place_event("PROP_B", aid="A3")],
            self._pedestal())
        self.assertEqual(kinds["PROP_A"], "support")
        self.assertEqual(kinds["PROP_B"], "support")
        xa, ya = rests["PROP_A"]
        xb, yb = rests["PROP_B"]
        self.assertAlmostEqual(ya, yb)
        self.assertNotAlmostEqual(xa, xb)
        self.assertLess(abs(xa - 960.0), 60.0 + 1.0)
        self.assertLess(abs(xb - 960.0), 60.0 + 1.0)

    def test_nearest_support_wins(self):
        prop_dicts = {"PROP_STONE": {"id": "PROP_STONE",
                                     "kind": "stone"}}
        anchors = self._pedestal(x=200.0, el_id="far_pedestal") + \
            self._pedestal(x=450.0, el_id="near_pedestal")
        _rests, _kinds, records = self._assign(
            ["PROP_STONE"], prop_dicts,
            [self._take_event("PROP_STONE"),
             self._place_event("PROP_STONE")], anchors)
        # Actor staging x is 400: the 450 pedestal is nearer.
        self.assertEqual(records["PROP_STONE"], "near_pedestal")


class TestCompilerWiring(unittest.TestCase):
    def _package_and_events(self, injections):
        text = FIXTURE.read_text(encoding="utf-8")
        for anchor, addition in injections:
            self.assertIn(anchor, text)
            text = text.replace(anchor, anchor + "\n" + addition, 1)
        package = adapt_document(parse_studio_script_v1(text))
        shots = plan_shots(
            package, [{"line_index": i + 1, "duration": 3.0}
                      for i in range(5)])
        spans = {}
        clock = 0.0
        for s in shots:
            did = s.get("directive_shot_id")
            if did:
                span = spans.setdefault(str(did), [clock, clock])
                span[1] = clock + float(s["duration"])
            clock += float(s["duration"])
        events, _unsupported = compile_actions(
            package, timeline={"spans": spans})
        return package, shots, events

    def test_placement_event_names_the_pedestal(self):
        _package, _shots, events = self._package_and_events([
            ("* Bà Tư hơi cúi đầu suy nghĩ.",
             "* Bà Tư đặt chìa khóa lên bệ."),
        ])
        named = [e for e in events
                 if e.get("destination_support") == "pedestal"]
        self.assertEqual(len(named), 1)
        self.assertEqual(named[0]["prop_id"], "prop_key")
        self.assertIn(named[0]["semantic_action_type"],
                      ("PLACE_ON_SURFACE", "PUT_AWAY"))

    def test_take_event_names_the_home_support(self):
        _package, _shots, events = self._package_and_events([
            ("* Bà Tư dừng lại, lấy chìa khóa từ túi tạp dề.",
             "* Bà Tư lấy chìa khóa trên bệ."),
        ])
        named = [e for e in events
                 if e.get("source_support") == "pedestal"]
        self.assertEqual(len(named), 1)
        self.assertEqual(named[0]["prop_id"], "prop_key")
        self.assertEqual(named[0]["semantic_action_type"],
                         "PICK_FROM_SURFACE")


class TestComposedPixelProof(unittest.TestCase):
    def test_stone_bottom_lands_on_pedestal_face(self):
        traits = {"name": "Quảng trường", "landmarks": ["bệ đá"]}
        pkg = build_environment(traits)
        pedestal = next(e for e in pkg["elements"]
                        if e["kind"] == "statue_pedestal")
        cam = PerspectiveCamera(position=(0.0, 2.0, 4.8))
        size = (1920, 1080)
        anchors = _support_anchors(pkg, cam, size)
        anchor = next(a for a in anchors
                      if a["id"] == pedestal["id"])
        env_img = render_environment(pkg, cam, size=size).convert("RGB")
        # Draw the stone at the snapped rest position on a copy and
        # measure its lowest differing pixel: the composed bottom.
        rest_y = anchor["top_y"] - prop_bottom_offset("stone")
        copy = env_img.copy()
        draw = ImageDraw.Draw(copy, "RGBA")
        _draw_prop(draw, anchor["x"], rest_y, kind="stone")
        diff = np.abs(np.array(copy).astype(int)
                      - np.array(env_img).astype(int)).sum(axis=2)
        ys, _xs = np.nonzero(diff > 0)
        bottom = int(ys.max())
        self.assertAlmostEqual(bottom, anchor["top_y"], delta=2)
        # The snap point lies on the pedestal's drawn extent.
        bbox = _projected_bbox(pedestal, cam, size[0], size[1])
        self.assertIsNotNone(bbox)
        self.assertLessEqual(bbox[1], anchor["top_y"])
        self.assertGreaterEqual(bbox[3], anchor["top_y"])


class TestRenderShotWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = FIXTURE.read_text(encoding="utf-8")
        anchor = ("FORBIDDEN:\n* Không thay địa điểm khác\n\n"
                  "LOCATION: LOC_SHED")
        text = text.replace(
            anchor,
            "FORBIDDEN:\n* Không thay địa điểm khác\n"
            "LANDMARKS:\n* Bệ đá\n\nLOCATION: LOC_SHED",
            1)
        bullet = "* Bà Tư hơi cúi đầu suy nghĩ."
        text = text.replace(
            bullet, bullet + "\n* Bà Tư đặt chìa khóa lên bệ.", 1)
        cls.package = adapt_document(parse_studio_script_v1(text))
        shots = plan_shots(
            cls.package, [{"line_index": i + 1, "duration": 3.0}
                          for i in range(5)])
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
            cls.package, timeline={"spans": spans})
        cls.package["compiled_actions"] = {
            "events": events, "unsupported": unsupported,
            "spans_supplied": True, "compile_error": None,
        }
        cls.shot = next(s for s in shots
                        if s.get("directive_shot_id") == "SC01_SH01")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.result = _render_shot({
            "shot": cls.shot, "package": cls.package,
            "out_dir": str(Path(cls._tmp.name) / "shot_00"),
        })

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_shot_record_carries_support_rest(self):
        self.assertEqual(
            self.result["prop_rest_kinds"].get("prop_key"), "support")
        support_id = self.result["prop_support_rests"].get("prop_key")
        self.assertIsNotNone(support_id)
        self.assertNotIn("missing", str(support_id))


if __name__ == "__main__":
    unittest.main()
