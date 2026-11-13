"""Semantic prop kinds (A2 wiring item 4): real kinds instead of
"generic", plus chain/stone/boulder geometry builders.

The adapter assigns kinds from prop name/description text; the
renderer inference agrees; geometry_for_prop builds specs for all
20 kinds (17 inherited + 3 new). PROP_KINDS + _draw_prop geometry
consumption is wiring item 7.
"""

import unittest
from pathlib import Path

from ai_clip_studio.product_renderer import infer_prop_kind
from ai_clip_studio.prop_system import (
    PROP_GEOMETRY_BUILDERS, UnsupportedPropError, geometry_for_prop)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.trait_derivation import derive_prop_kind

AGENT = Path(__file__).resolve().parent.parent.parent


def _package(name):
    doc = parse_studio_script_v1(
        (AGENT / "examples" / f"{name}.studio.md").read_text(
            encoding="utf-8"))
    return adapt_document(doc)


class TestDerivePropKind(unittest.TestCase):
    def test_mythological_and_restraint_kinds(self):
        cases = [
            ("PROP_LIGHTNING", "Divine lightning bolt", "bolt"),
            ("Tia Sét", "", "bolt"),
            ("PROP_FORGE_HAMMER", "Giant blacksmith hammer", "hammer"),
            ("Chiếc Búa", "", "hammer"),
            ("PROP_TRIDENT", "Divine trident", "trident"),
            ("Đinh Ba", "", "trident"),
            ("PROP_INVISIBILITY_HELMET", "Magical helmet", "helmet"),
            ("Mũ Tàng Hình", "", "helmet"),
            ("Thanh Kiếm", "", "sword"),
            ("Chiếc Khiên", "", "shield"),
            ("Vương Miện", "", "crown"),
            ("Chiếc Nhẫn", "", "ring"),
            ("Quyền Trượng", "", "staff"),
            ("PROP_CHAIN", "Giant ancient prison chain", "chain"),
            ("Dây Xích", "", "chain"),
            ("PROP_BOULDER", "Giant mountain rock", "boulder"),
            ("Tảng Đá", "", "boulder"),
            ("PROP_SWADDLED_STONE", "Large stone wrapped in baby cloth",
             "stone"),
            ("Hòn Đá", "", "stone"),
            ("Viên Đá", "", "stone"),
        ]
        for name, desc, want in cases:
            with self.subTest(name=name):
                self.assertEqual(derive_prop_kind(name, desc), want)

    def test_ordering_helmet_before_hat_boulder_before_stone(self):
        self.assertEqual(derive_prop_kind("Mũ Sắt", ""), "helmet")
        self.assertEqual(derive_prop_kind("Mũ Rơm", ""), "hat")
        self.assertEqual(derive_prop_kind("Tảng Đá Lớn", ""), "boulder")
        self.assertEqual(derive_prop_kind("Hòn Đá Nhỏ", ""), "stone")
        self.assertEqual(derive_prop_kind("Rock", ""), "stone")

    def test_existing_kinds_unchanged_and_unknown_generic(self):
        self.assertEqual(derive_prop_kind("Ví Da", ""), "wallet")
        self.assertEqual(derive_prop_kind("Lá Thư", ""), "letter")
        self.assertEqual(derive_prop_kind("Cây Bút", ""), "pen")
        self.assertEqual(derive_prop_kind("Chiếc Túi", ""), "bag")
        self.assertEqual(derive_prop_kind("Quantum Flux Capacitor", ""),
                         "generic")


class TestInferPropKindAgrees(unittest.TestCase):
    def test_keyword_fallback_for_kindless_props(self):
        cases = [
            ({"name": "Tia sét"}, "bolt"),
            ({"name": "Chiếc búa"}, "hammer"),
            ({"name": "Đinh ba"}, "trident"),
            ({"name": "Mũ tàng hình"}, "helmet"),
            ({"name": "Dây xích"}, "chain"),
            ({"name": "Tảng đá"}, "boulder"),
            ({"name": "Hòn đá"}, "stone"),
            ({"name": "Mũ rơm"}, "hat"),
        ]
        for prop, want in cases:
            with self.subTest(prop=prop):
                self.assertEqual(infer_prop_kind(prop), want)

    def test_explicit_new_kind_wins(self):
        # Since wiring item 7 the geometry kinds are in PROP_KINDS,
        # so an explicit kind wins outright; a kind-less prop still
        # falls back to keyword inference.
        self.assertEqual(
            infer_prop_kind({"kind": "bolt", "name": "Xyzzy"}), "bolt")
        self.assertEqual(
            infer_prop_kind({"kind": "boulder", "name": "Xyzzy"}),
            "boulder")
        self.assertEqual(
            infer_prop_kind({"kind": "nonsense", "name": "Xyzzy"}),
            "generic")


class TestAdapterPropKinds(unittest.TestCase):
    def test_zeus_props_have_real_kinds(self):
        pkg = _package("zeus_ep01_fall_of_cronus")
        kinds = {p["id"]: p["kind"] for p in pkg["props"]}
        self.assertEqual(kinds, {
            "prop_swaddled_stone": "stone",
            "prop_herbal_potion": "cup",
            "prop_lightning": "bolt",
            "prop_trident": "trident",
            "prop_invisibility_helmet": "helmet",
            "prop_chain": "chain",
            "prop_forge_hammer": "hammer",
            "prop_boulder": "boulder",
        })

    def test_ep1_props_unchanged(self):
        pkg = _package("hitler_ep01_munich_1914")
        kinds = {p["id"]: p["kind"] for p in pkg["props"]}
        self.assertEqual(kinds, {
            "prop_wallet": "wallet",
            "prop_letter": "letter",
            "prop_pen": "pen",
            "prop_military_bag": "bag",
        })


class TestNewGeometryBuilders(unittest.TestCase):
    def test_registry_has_20_kinds(self):
        for kind in ("chain", "stone", "boulder"):
            self.assertIn(kind, PROP_GEOMETRY_BUILDERS)
        self.assertEqual(len(PROP_GEOMETRY_BUILDERS), 20)

    def test_chain_spec(self):
        spec = geometry_for_prop({"id": "c", "kind": "chain"})
        self.assertEqual(spec["kind"], "chain")
        self.assertEqual(spec["family"], "stone_and_restraint")
        self.assertEqual(len(spec["parts"]), 6)
        self.assertEqual(spec["contact_points"]["grip"], (0.0, 0.0))
        self.assertEqual(spec["material_slots"], ["metal"])
        self.assertEqual(spec["state"], {"links": 6})
        spec4 = geometry_for_prop({"id": "c", "kind": "chain"}, links=4)
        self.assertEqual(len(spec4["parts"]), 4)

    def test_stone_spec_and_wrapped_state(self):
        spec = geometry_for_prop({"id": "s", "kind": "stone"})
        self.assertEqual(spec["family"], "stone_and_restraint")
        self.assertEqual(spec["contact_points"]["grip"], (0.0, 0.0))
        self.assertEqual(spec["contact_points"]["bottom"], (0.0, 45.0))
        self.assertEqual(spec["state"], {"wrapped": False})
        again = geometry_for_prop({"id": "s", "kind": "stone"})
        self.assertEqual(spec, again)  # deterministic, no RNG
        wrapped = geometry_for_prop({"id": "s", "kind": "stone"},
                                    wrapped=True)
        names = [p["name"] for p in wrapped["parts"]]
        self.assertIn("cloth_band_v", names)
        self.assertIn("cloth_band_h", names)
        self.assertIn("cloth", wrapped["material_slots"])
        self.assertEqual(wrapped["state"], {"wrapped": True})

    def test_boulder_spec(self):
        spec = geometry_for_prop({"id": "b", "kind": "boulder"})
        self.assertEqual(spec["kind"], "boulder")
        self.assertEqual(spec["contact_points"]["grip"], (0.0, 0.0))
        self.assertEqual(len(spec["parts"]), 3)
        xs = [pt[0] for part in spec["parts"]
              for pt in part.get("points", [])]
        self.assertGreater(max(xs) - min(xs), 100.0)

    def test_h_relative_kinds_need_h(self):
        for kind in ("pen", "hammer"):
            with self.assertRaises(ValueError):
                geometry_for_prop({"id": "p", "kind": kind})
            spec = geometry_for_prop({"id": "p", "kind": kind}, H=774)
            self.assertEqual(spec["contact_points"]["grip"], (0.0, 0.0))

    def test_unknown_kind_raises_loudly(self):
        with self.assertRaises(UnsupportedPropError):
            geometry_for_prop({"id": "u", "kind": "umbrella"})
        with self.assertRaises(UnsupportedPropError):
            geometry_for_prop({"id": "u", "kind": "generic",
                               "name": "Quantum Flux Capacitor"})

    def test_generic_kind_recovers_from_text(self):
        spec = geometry_for_prop(
            {"id": "x", "kind": "generic", "name": "PROP_CHAIN",
             "description": "Giant ancient prison chain"})
        self.assertEqual(spec["kind"], "chain")
        self.assertEqual(spec["kind_inferred"]["token"], "chain")
        spec = geometry_for_prop(
            {"id": "x", "kind": "generic", "name": "Rock",
             "description": "Giant mountain rock"})
        self.assertEqual(spec["kind"], "boulder")
        self.assertEqual(spec["kind_inferred"]["token"],
                         "mountain rock")


if __name__ == "__main__":
    unittest.main()
