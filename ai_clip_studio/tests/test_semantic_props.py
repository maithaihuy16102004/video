"""Tests for the semantic prop renderer and the semantic prop
state tracker (Subagent A2, Semantic Production Engine Upgrade,
2026-11-12).

Geometry: parametric specs per prop kind (10 families, 17
builders), material-slot interface, state-dependent geometry,
articulated subparts, unknown-kind error, placeholder policy.
Tracker: PROP_TRANSITIONS enforcement, the ground rule
(ON_GROUND only), initial-state back-propagation, paired
handover continuity, container states, staging validation.

Fixtures are synthetic; the wallet/bolt/pen instances are the
script props as DATA (no per-story render functions).
"""
from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from ai_clip_studio.action_compiler import (
    PROP_KIND_NOUNS,
    compile_actions,
)
from ai_clip_studio.prop_system import (
    _KIND_INFERENCE_NOUNS,
    PLACEHOLDER_MATERIAL,
    PROP_FAMILIES,
    PROP_GEOMETRY_BUILDERS,
    PROP_KIND_FAMILY,
    ForbiddenPropTransition,
    MissingMaterialError,
    PropStateMachine,
    SemanticPropTracker,
    UnsupportedPropError,
    draw_prop_geometry,
    draw_prop_placeholder,
    geometry_for_prop,
    resolve_materials,
    spec_world_bbox,
    spec_world_contact_points,
    validate_staging_against_semantics,
)


def _pkg(shots, props=None):
    scenes = []
    for i, (sid, actions) in enumerate(shots):
        sc = f"SC0{i + 1}"
        scenes.append({
            "id": sc, "number": i + 1, "location_id": "LOC_X",
            "shots": [{"id": sid, "camera": "MEDIUM",
                       "action": " ".join(actions), "expression": ""}],
            "v1_scene": {
                "id": sc, "number": i + 1,
                "shots": [{"id": sid, "camera": "MEDIUM",
                           "expression": "",
                           "fields": {"ACTION": list(actions)}}]},
        })
    return {
        "characters": [
            {"id": "CHAR_ANA", "name": "Ana", "gender": "female",
             "template": "female", "voice_id": "V_A",
             "costume": "red coat"},
            {"id": "CHAR_BEN", "name": "Ben", "gender": "male",
             "template": "male", "voice_id": "V_B",
             "costume": "blue uniform"},
        ],
        "props": props or [{"id": "prop_wallet", "name": "wallet",
                            "kind": "wallet", "owner": ""}],
        "scenes": scenes,
    }


def _catalog(spec):
    return {slot: {"fill": (10, 20, 30), "outline": (0, 0, 0),
                   "width": 2}
            for slot in spec["material_slots"]}


class GeometryFamiliesTest(unittest.TestCase):
    def test_eleven_families(self):
        # 11 since wiring item 4 (2026-11-12): + stone_and_restraint.
        self.assertEqual(len(PROP_FAMILIES), 11)
        self.assertEqual(
            PROP_FAMILIES["mythological_weapons"],
            ("bolt", "trident", "sword", "shield"))
        self.assertEqual(PROP_FAMILIES["containers"],
                         ("bag", "wallet", "cup"))
        self.assertEqual(PROP_FAMILIES["stone_and_restraint"],
                         ("chain", "stone", "boulder"))

    def test_reserved_families_have_no_builders(self):
        # musical_instruments / furniture / everyday_objects are
        # taxonomy only: no builders, so unknown kinds raise
        # instead of silently rendering a wrong shape.
        for family in ("musical_instruments", "furniture",
                       "everyday_objects"):
            self.assertEqual(PROP_FAMILIES[family], ())

    def test_kind_family_mapping_covers_builders(self):
        # 20 since wiring item 4 (2026-11-12): + chain/stone/boulder.
        self.assertEqual(len(PROP_GEOMETRY_BUILDERS), 20)
        for kind in PROP_GEOMETRY_BUILDERS:
            self.assertIn(kind, PROP_KIND_FAMILY)
            self.assertIn(kind, PROP_FAMILIES[PROP_KIND_FAMILY[kind]])

    def test_all_kinds_build_with_grip_contact(self):
        for kind in PROP_GEOMETRY_BUILDERS:
            with self.subTest(kind=kind):
                spec = geometry_for_prop({"id": "px", "kind": kind},
                                         H=560)
                self.assertTrue(spec["parts"], kind)
                self.assertEqual(spec["kind"], kind)
                self.assertIn("grip", spec["contact_points"])
                self.assertEqual(spec["contact_points"]["grip"],
                                 (0.0, 0.0))


class BoltGeometryTest(unittest.TestCase):
    def test_bolt_is_zigzag_not_box(self):
        spec = geometry_for_prop(
            {"id": "p1", "kind": "bolt", "length_px": 170}, H=560)
        core = [p for p in spec["parts"] if p["name"] == "core"][0]
        self.assertEqual(core["op"], "polygon")
        self.assertGreaterEqual(len(core["points"]), 6)
        # A box has 4 vertices with 2 distinct x values; the bolt
        # zigzag has many distinct x values and a reflex turn.
        xs = {round(x, 1) for x, _ in core["points"]}
        self.assertGreater(len(xs), 2)
        # The spine alternates sides (zigzag), it is not monotone.
        self.assertLess(min(xs), 0.0)
        self.assertGreater(max(xs), 0.0)

    def test_bolt_lit_by_default_with_emissive_slot(self):
        spec = geometry_for_prop(
            {"id": "p1", "kind": "bolt", "length_px": 170}, H=560)
        self.assertTrue(spec["state"]["lit"])
        self.assertIn("halo", [p["name"] for p in spec["parts"]])
        self.assertIn("emissive", spec["material_slots"])

    def test_bolt_unlit_has_no_halo_or_emissive(self):
        spec = geometry_for_prop(
            {"id": "p1", "kind": "bolt", "length_px": 170}, H=560,
            state={"lit": False})
        self.assertFalse(spec["state"]["lit"])
        self.assertEqual([p["name"] for p in spec["parts"]], ["core"])
        self.assertEqual(spec["material_slots"], ["core"])

    def test_bolt_grip_at_origin_and_contacts(self):
        spec = geometry_for_prop(
            {"id": "p1", "kind": "bolt", "length_px": 170}, H=560)
        self.assertEqual(spec["contact_points"]["grip"], (0.0, 0.0))
        self.assertIn("tip_top", spec["contact_points"])
        self.assertIn("tip_bottom", spec["contact_points"])
        world = spec_world_contact_points(spec, 200.0, 200.0, 0.0)
        self.assertEqual(world["grip"], (200.0, 200.0))


class WalletGeometryTest(unittest.TestCase):
    def test_open_differs_from_closed(self):
        closed = geometry_for_prop({"id": "p2", "kind": "wallet"},
                                   H=560)
        opened = geometry_for_prop(
            {"id": "p2", "kind": "wallet"}, H=560,
            state={"open_u": 1.0})
        closed_names = [p["name"] for p in closed["parts"]]
        opened_names = [p["name"] for p in opened["parts"]]
        self.assertEqual(closed_names, ["body", "stitch", "clasp"])
        self.assertEqual(
            opened_names,
            ["body", "stitch", "fold", "card_slot_1", "card_slot_2",
             "bill"])
        closed_w = closed["bbox"][2] - closed["bbox"][0]
        opened_w = opened["bbox"][2] - opened["bbox"][0]
        self.assertEqual(closed_w, 110.0)
        self.assertEqual(opened_w, 148.5)
        self.assertGreater(opened_w, closed_w)


class HammerPenGeometryTest(unittest.TestCase):
    def test_hammer_articulation(self):
        spec = geometry_for_prop({"id": "p4", "kind": "hammer"}, H=560)
        art = spec["articulation"]
        self.assertEqual(art["joint"], (0.0, 0.0))
        self.assertEqual(art["angle_param"], "grip_angle_rad")
        self.assertEqual(art["subparts"], ["handle", "head"])
        self.assertIn("strike_face", spec["contact_points"])

    def test_pen_tip_contact(self):
        spec = geometry_for_prop({"id": "p5", "kind": "pen"}, H=560)
        self.assertIn("tip", spec["contact_points"])
        tip = spec["contact_points"]["tip"]
        self.assertGreater(tip[1], 0.0)  # tip below the grip


class MaterialSlotTest(unittest.TestCase):
    def test_missing_slot_raises(self):
        spec = geometry_for_prop({"id": "p1", "kind": "bolt"}, H=560)
        with self.assertRaises(MissingMaterialError):
            resolve_materials(spec, {})

    def test_preview_resolves_magenta_and_reports_missing(self):
        spec = geometry_for_prop({"id": "p1", "kind": "bolt"}, H=560)
        resolved, missing = resolve_materials(
            spec, {}, engineering_preview=True)
        self.assertEqual(missing, ["core", "emissive"])
        self.assertEqual(resolved["core"]["fill"],
                         PLACEHOLDER_MATERIAL["fill"])
        self.assertEqual(PLACEHOLDER_MATERIAL["fill"], (255, 0, 255))

    def test_draw_report_and_world_bbox(self):
        spec = geometry_for_prop(
            {"id": "p1", "kind": "bolt", "length_px": 170}, H=560)
        img = Image.new("RGB", (400, 400), "white")
        draw = ImageDraw.Draw(img)
        report = draw_prop_geometry(draw, spec, 200, 200, 30,
                                    _catalog(spec))
        self.assertEqual(report["kind"], "bolt")
        self.assertEqual(report["parts_drawn"], 2)
        self.assertEqual(report["placeholders"], [])
        self.assertEqual(report["bbox"],
                         spec_world_bbox(spec, 200, 200, 30))

    def test_unknown_kind_raises(self):
        with self.assertRaises(UnsupportedPropError):
            geometry_for_prop({"id": "p3", "kind": "toaster"}, H=560)

    def test_param_filtering_lists_ignored(self):
        spec = geometry_for_prop(
            {"id": "p2", "kind": "wallet", "bogus": 1}, H=560,
            bogus_param=3)
        self.assertIn("bogus_param", spec["ignored_params"])

    def test_placeholder_requires_preview_flag(self):
        img = Image.new("RGB", (200, 200), "white")
        draw = ImageDraw.Draw(img)
        with self.assertRaises(ValueError):
            draw_prop_placeholder(draw, 100, 100, 60)
        report = draw_prop_placeholder(draw, 100, 100, 60,
                                       engineering_preview=True)
        self.assertTrue(report["placeholder"])
        self.assertEqual(report["bbox"], (70.0, 70.0, 130.0, 130.0))


class TrackerTransitionTest(unittest.TestCase):
    def test_paired_handover_stays_in_transit(self):
        pkg = _pkg([("SC01_SH01", [
            "Ana đưa chiếc ví cho Ben.",
            "Ben nhận bằng tay phải."])])
        events, _ = compile_actions(pkg, {})
        tracker = SemanticPropTracker(pkg["props"], events)
        self.assertEqual(
            [(t["action"], t["from"], t["to"])
             for t in tracker.transitions],
            [("GIVE", "HELD_RIGHT", "IN_TRANSIT"),
             ("RECEIVE_PROP", "IN_TRANSIT", "HELD_RIGHT")])
        # IN_TRANSIT from the handover start until the receive
        # completes; the holder is Ben only after the receive.
        self.assertEqual(tracker.location_at("prop_wallet", 0.5),
                         "IN_TRANSIT")
        self.assertEqual(tracker.location_at("prop_wallet", 2.0),
                         "IN_TRANSIT")
        self.assertEqual(tracker.location_at("prop_wallet", 3.0),
                         "HELD_RIGHT")
        self.assertEqual(tracker.holder_at("prop_wallet", 3.0),
                         "CHAR_BEN")

    def test_take_from_pocket_back_propagates_initial(self):
        pkg = _pkg([("SC01_SH01", ["Ana lấy ví từ túi áo."])])
        events, _ = compile_actions(pkg, {})
        tracker = SemanticPropTracker(pkg["props"], events)
        self.assertEqual(tracker.initial_location("prop_wallet"),
                         "IN_POCKET")
        self.assertTrue(tracker.initial_inferred("prop_wallet"))

    def test_definitive_contradiction_raises(self):
        pkg = _pkg([
            ("SC01_SH01", ["Ana cúi xuống nhặt chiếc ví dưới đất."]),
            ("SC02_SH01", ["Ana lấy ví từ túi áo."]),
        ])
        events, _ = compile_actions(pkg, {})
        with self.assertRaises(ForbiddenPropTransition) as ctx:
            SemanticPropTracker(pkg["props"], events)
        self.assertIn("TAKE_FROM_POCKET", str(ctx.exception))
        self.assertIn("IN_POCKET", str(ctx.exception))

    def test_legacy_events_warn_instead_of_raise(self):
        pkg = _pkg([
            ("SC01_SH01", ["Ana cúi xuống nhặt chiếc ví dưới đất."]),
            ("SC02_SH01", ["Ana lấy ví từ túi áo."]),
        ])
        events, _ = compile_actions(pkg, {})
        for event in events:
            event["semantic_action_type"] = None
        tracker = SemanticPropTracker(pkg["props"], events)
        self.assertEqual(len(tracker.warnings), 1)
        self.assertIn("legacy event", tracker.warnings[0]["issue"])

    def test_hold_verbs_never_raise(self):
        pkg = _pkg(
            [("SC01_SH01", ["Ana viết thư bằng bút."])],
            props=[{"id": "prop_pen", "name": "pen", "kind": "pen",
                    "owner": ""}])
        events, _ = compile_actions(pkg, {})
        tracker = SemanticPropTracker(pkg["props"], events)
        self.assertEqual(tracker.location_at("prop_pen", 5.0),
                         "HELD_RIGHT")

    def test_container_open_close(self):
        pkg = _pkg([("SC01_SH01", [
            "Ana mở ví bằng hai tay.", "Ana đóng ví."])])
        events, _ = compile_actions(pkg, {})
        tracker = SemanticPropTracker(pkg["props"], events)
        self.assertEqual(tracker.container_at("prop_wallet", 0.0),
                         "CLOSED")
        self.assertEqual(tracker.container_at("prop_wallet", 1.5),
                         "OPEN")
        self.assertEqual(tracker.container_at("prop_wallet", 2.5),
                         "CLOSED")


class GroundRuleTest(unittest.TestCase):
    def test_ground_rest_only_when_on_ground(self):
        pkg = _pkg([("SC01_SH01", [
            "Ana cúi xuống nhặt chiếc ví dưới đất."])])
        events, _ = compile_actions(pkg, {})
        tracker = SemanticPropTracker(pkg["props"], events)
        self.assertEqual(tracker.initial_location("prop_wallet"),
                         "ON_GROUND")
        self.assertTrue(
            tracker.ground_rest_allowed("prop_wallet", 0.0))
        self.assertFalse(
            tracker.ground_rest_allowed("prop_wallet", 5.0))
        self.assertEqual(tracker.location_at("prop_wallet", 5.0),
                         "HELD_RIGHT")

    def test_unknown_initial_never_rests_on_ground(self):
        pkg = _pkg([("SC01_SH01", ["Ana lấy ví từ túi áo."])])
        events, _ = compile_actions(pkg, {})
        tracker = SemanticPropTracker(pkg["props"], events)
        self.assertFalse(
            tracker.ground_rest_allowed("prop_wallet", 0.0))
        # A prop with no events at all has no location: unknown
        # is not ON_GROUND.
        empty = SemanticPropTracker(pkg["props"], [])
        self.assertIsNone(empty.initial_location("prop_wallet"))
        self.assertFalse(
            empty.ground_rest_allowed("prop_wallet", 0.0))


class StagingValidationTest(unittest.TestCase):
    def test_matching_staging_passes(self):
        pkg = _pkg([("SC01_SH01", ["Ana lấy ví từ túi áo."])])
        events, _ = compile_actions(pkg, {})
        psm = PropStateMachine(
            pkg["props"], events,
            staging={"prop_wallet": {"x": 0, "y": 0, "angle": 0,
                                     "kind": "pocket"}})
        self.assertEqual(validate_staging_against_semantics(psm), [])

    def test_ground_staging_for_pocket_prop_raises(self):
        pkg = _pkg([("SC01_SH01", ["Ana lấy ví từ túi áo."])])
        events, _ = compile_actions(pkg, {})
        psm = PropStateMachine(
            pkg["props"], events,
            staging={"prop_wallet": {"x": 0, "y": 900, "angle": 0,
                                     "kind": "ground"}})
        with self.assertRaises(ForbiddenPropTransition) as ctx:
            validate_staging_against_semantics(psm)
        self.assertIn("prop_wallet", str(ctx.exception))
        self.assertIn("IN_POCKET", str(ctx.exception))

    def test_ground_staging_for_ground_prop_passes(self):
        pkg = _pkg([("SC01_SH01", [
            "Ana cúi xuống nhặt chiếc ví dưới đất."])])
        events, _ = compile_actions(pkg, {})
        psm = PropStateMachine(
            pkg["props"], events,
            staging={"prop_wallet": {"x": 0, "y": 900, "angle": 0,
                                     "kind": "ground"}})
        self.assertEqual(validate_staging_against_semantics(psm), [])


class KindInferenceTest(unittest.TestCase):
    def test_generic_english_described_props_infer(self):
        cases = (
            ({"id": "prop_lightning", "name": "PROP_LIGHTNING",
              "kind": "generic",
              "description": "Divine lightning bolt"}, "bolt"),
            ({"id": "prop_forge_hammer", "name": "PROP_FORGE_HAMMER",
              "kind": "generic",
              "description": "Giant blacksmith hammer"}, "hammer"),
            ({"id": "prop_trident", "name": "PROP_TRIDENT",
              "kind": "generic",
              "description": "Divine trident"}, "trident"),
            ({"id": "prop_helmet", "name": "PROP_HELMET",
              "kind": "generic",
              "description": "Magical helmet"}, "helmet"),
        )
        for prop, kind in cases:
            with self.subTest(prop=prop["id"]):
                spec = geometry_for_prop(prop, H=560)
                self.assertEqual(spec["kind"], kind)
                self.assertIsNotNone(spec["kind_inferred"])
                self.assertEqual(spec["kind_inferred"]
                                 ["declared_kind"], "generic")

    def test_explicit_kind_is_never_inferred(self):
        spec = geometry_for_prop({"id": "p", "kind": "wallet"}, H=560)
        self.assertIsNone(spec["kind_inferred"])

    def test_explicit_unknown_kind_raises_not_inferred(self):
        with self.assertRaises(UnsupportedPropError):
            geometry_for_prop({"id": "p", "kind": "toaster",
                               "description": "a hammer"}, H=560)

    def test_generic_unmatchable_raises(self):
        with self.assertRaises(UnsupportedPropError):
            geometry_for_prop(
                {"id": "p", "kind": "generic",
                 "description": "An indescribable thing"}, H=560)

    def test_no_builder_kind_raises(self):
        # Umbrella has mention vocabulary but no geometry builder:
        # explicit error, never a silent box. (Chain/stone/boulder
        # used to be the examples here; wiring item 4 gave them
        # builders in 2026-11-12.)
        with self.assertRaises(UnsupportedPropError):
            geometry_for_prop(
                {"id": "prop_umbrella", "name": "PROP_UMBRELLA",
                 "kind": "umbrella",
                 "description": "A rain umbrella"}, H=560)

    def test_inference_table_drift_guard(self):
        # Every inference noun must exist in the compiler's
        # PROP_KIND_NOUNS for the same kind (one vocabulary, two
        # consumers). Deliberate deltas are asserted explicitly.
        for kind, nouns in _KIND_INFERENCE_NOUNS.items():
            for noun in nouns:
                with self.subTest(kind=kind, noun=noun):
                    self.assertIn(noun, PROP_KIND_NOUNS[kind])
        self.assertNotIn("túi", _KIND_INFERENCE_NOUNS["bag"])
        self.assertNotIn("glass", _KIND_INFERENCE_NOUNS["cup"])


if __name__ == "__main__":
    unittest.main()
