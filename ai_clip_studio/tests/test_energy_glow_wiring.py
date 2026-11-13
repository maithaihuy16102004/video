"""Energy-glow wiring (A2 wiring item 10): lighting consumes
energy_glow_at -- the 2D renderer paints the halo for held
energy-carrying props, emissive-slot kinds declare their energy
spec, and the 3D bridge converts a real record.
"""

import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.lighting import (
    MATERIAL_CATALOG, energy_glow_to_point_light,
    paint_energy_glow, pixel_glow_to_world_glow)
from ai_clip_studio.product_renderer import (
    _GEOMETRY_SLOT_FILLS, _render_shot, plan_shots)
from ai_clip_studio.prop_system import (
    EMISSIVE_SLOT_COLOR, default_energy_spec)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent


def _record(**overrides):
    record = {
        "prop_id": "prop_lightning", "intensity": 1.0,
        "color": (255, 210, 90), "radius": 100.0,
        "source_position": (200.0, 150.0),
        "state": "GRASPED", "holder": "CHAR_ZEUS",
    }
    record.update(overrides)
    return record


class TestPaintEnergyGlow(unittest.TestCase):
    def test_center_brightens_edge_unchanged(self):
        img = Image.new("RGB", (400, 300), (40, 40, 40))
        paint_energy_glow(img, _record())
        center = img.getpixel((200, 150))
        edge = img.getpixel((200 + 99, 150))
        outside = img.getpixel((200 + 150, 150))
        self.assertGreater(center[0], 150)  # pulled toward gold
        self.assertGreater(center[0], edge[0])  # falloff outward
        self.assertEqual(outside, (40, 40, 40))

    def test_radius_zero_paints_nothing(self):
        img = Image.new("RGB", (400, 300), (40, 40, 40))
        paint_energy_glow(img, _record(intensity=0.0, radius=0.0))
        self.assertEqual(img.getpixel((200, 150)), (40, 40, 40))

    def test_world_space_record_raises(self):
        img = Image.new("RGB", (400, 300), (40, 40, 40))
        with self.assertRaises(ValueError):
            paint_energy_glow(
                img, _record(source_position=(1.0, 2.0, 3.0)))

    def test_malformed_record_raises(self):
        img = Image.new("RGB", (400, 300), (40, 40, 40))
        with self.assertRaises(ValueError):
            paint_energy_glow(img, {"intensity": 2.0})


class TestDefaultEnergySpec(unittest.TestCase):
    def test_bolt_only(self):
        self.assertEqual(default_energy_spec("bolt"),
                         {"color": (255, 210, 90)})
        for kind in ("wallet", "hammer", "sword", "trident",
                     "stone", "chain", "cup", "helmet"):
            self.assertIsNone(default_energy_spec(kind), kind)
        self.assertIsNone(default_energy_spec("umbrella"))
        self.assertIsNone(default_energy_spec(""))

    def test_emissive_color_tied_to_catalog_and_fills(self):
        catalog = MATERIAL_CATALOG["gold-emissive"]
        self.assertEqual(EMISSIVE_SLOT_COLOR,
                         tuple(catalog["emissive_color"]))
        self.assertEqual(_GEOMETRY_SLOT_FILLS["emissive"],
                         EMISSIVE_SLOT_COLOR)


class TestAdapterEnergyDeclaration(unittest.TestCase):
    def _package(self, name):
        return adapt_document(parse_studio_script_v1(
            (AGENT / "examples" / f"{name}.studio.md").read_text(
                encoding="utf-8")))

    def test_zeus_bolt_declares_energy_ep1_none(self):
        zeus = self._package("zeus_ep01_fall_of_cronus")
        by_kind = {p["kind"]: p for p in zeus["props"]}
        self.assertEqual(by_kind["bolt"]["energy"],
                         {"color": (255, 210, 90)})
        for kind, prop in by_kind.items():
            if kind != "bolt":
                self.assertNotIn("energy", prop, kind)
        ep1 = self._package("hitler_ep01_munich_1914")
        for prop in ep1["props"]:
            self.assertNotIn("energy", prop, prop["kind"])


def _zeus_package_and_shots():
    text = (AGENT / "examples" / "zeus_ep01_fall_of_cronus.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(40)])
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
    return package, shots


class TestBoltGlowRender(unittest.TestCase):
    def test_held_bolt_glows_locally_and_brighter(self):
        package, shots = _zeus_package_and_shots()
        bolt = [p["id"] for p in package["props"]
                if p["kind"] == "bolt"][0]
        target = None
        with tempfile.TemporaryDirectory() as tmp:
            for shot in shots:
                if shot.get("scene") != 8:
                    continue
                result = _render_shot({
                    "shot": shot, "package": package,
                    "out_dir": str(Path(tmp) / f"s{shot['index']}"),
                    "still_only": True})
                draws = dict(result["prop_draws"])
                if draws.get(bolt) in ("GRASPED", "ATTACHED_TO_HAND",
                                       "IN_USE"):
                    target = shot
                    break
        self.assertIsNotNone(target, "no scene-8 shot holds the bolt")

        def render(pkg):
            with tempfile.TemporaryDirectory() as tmp:
                result = _render_shot({
                    "shot": copy.deepcopy(target), "package": pkg,
                    "out_dir": str(Path(tmp) / "shot"),
                    "still_only": True})
                return np.asarray(
                    Image.open(result["still"]).convert("RGB")
                    ).astype(int)

        glow = render(package)
        stripped = copy.deepcopy(package)
        for prop in stripped["props"]:
            prop.pop("energy", None)
        plain = render(stripped)
        diff = (np.abs(glow - plain).sum(axis=2) > 0)
        self.assertGreater(int(diff.sum()), 10000,
                           "the glow must change the frame")
        ys, xs = np.nonzero(diff)
        # A local disc, not a global shift: the 240px default
        # radius bounds the differ region.
        self.assertLessEqual(xs.max() - xs.min(), 480)
        self.assertLessEqual(ys.max() - ys.min(), 480)
        self.assertGreater(float(glow[diff].mean()),
                           float(plain[diff].mean()),
                           "the glow must add light")


class TestGlowBridge(unittest.TestCase):
    def test_real_record_bridges_to_world_point_light(self):
        # The 3D conversion path, end to end at the data level:
        # a real pixel-space record from the state machine
        # (shape as energy_glow_at emits it) bridges to a valid
        # world record and a PointLight. The emitter supplies
        # the shot camera + plane depth; here a camera in the
        # emitter's dict shape stands in.
        from ai_clip_studio.renderer25d.camera import PerspectiveCamera
        record = _record()
        camera = PerspectiveCamera(position=(0.0, 2.0, 4.8),
                                   target=(0.0, 1.2, 0.0),
                                   fov_deg=46.0, aspect=16 / 9)
        world = pixel_glow_to_world_glow(
            record, camera, (1920, 1080), plane_depth=4.8)
        self.assertEqual(world["position_space"], "world")
        self.assertEqual(len(world["source_position"]), 3)
        light = energy_glow_to_point_light(world)
        self.assertGreater(light.intensity, 0)


if __name__ == "__main__":
    unittest.main()
