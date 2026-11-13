"""Test F / B2 tests: prop material catalog + energy_glow producer shape.

Covers: the MATERIAL_CATALOG contract (entries, validation,
resolution, emissive-light conversion, JSON export), the
energy_glow consumer's acceptance of the REAL producer record
shape (PropStateMachine.energy_glow_at: prop_id / state / holder
/ 2-element pixel position / intensity-scaled radius), the
pixel->world glow bridge (unprojection round-trip, radius
conversion, loud failures), and the tinted-texture path that
lets point lights hue-shift textured faces.
"""
import json
import math
import unittest
from pathlib import Path

from PIL import Image

from ai_clip_studio.environment_v2 import (
    build_environment,
    render_environment,
)
from ai_clip_studio.lighting import (
    ENERGY_GLOW_EDGE_FRACTION,
    ENERGY_GLOW_HELD_STATES,
    ENERGY_GLOW_PEAK_INTENSITY,
    ENERGY_GLOW_PROP_STATES,
    MATERIAL_CATALOG,
    MATERIAL_INK,
    energy_glow_to_point_light,
    get_material,
    material_catalog_json,
    material_emissive_light,
    material_names,
    measure_mean_luminance,
    pixel_glow_to_world_glow,
    resolve_material,
    unproject_pixel,
    validate_energy_glow,
    validate_material_entry,
)
from ai_clip_studio.paint_textures import paste_textured_quad
from ai_clip_studio.prop_system import (
    PROP_STATES,
    PropStateMachine,
    _HELD_STATES,
)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera
from ai_clip_studio.renderer25d.lighting import PointLight
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1

# A record in the EXACT shape PropStateMachine.energy_glow_at
# returns (see TESTF_A_ACTING.md §4): pixel-space position,
# intensity-scaled radius, prop_id / state / holder carried.
A_RECORD = {
    "prop_id": "PROP_LIGHTNING",
    "intensity": 1.0,
    "color": (170, 205, 255),
    "radius": 240.0,
    "source_position": (960.0, 540.0),
    "state": "GRASPED",
    "holder": "CHAR_ZEUS",
}


class TestMaterialCatalog(unittest.TestCase):
    def test_all_required_materials_present(self):
        for name in ("leather", "steel", "gold-emissive", "paper",
                     "wood", "stone", "cloth", "bronze"):
            self.assertIn(name, MATERIAL_CATALOG, name)
        self.assertEqual(material_names(), list(MATERIAL_CATALOG))

    def test_entries_validate_and_outline_in_ink(self):
        for name, entry in MATERIAL_CATALOG.items():
            norm = validate_material_entry(entry)
            self.assertEqual(norm["outline"], MATERIAL_INK, name)
            self.assertEqual(norm, entry, name)

    def test_ink_matches_product_renderer(self):
        # The catalog repeats the literal rather than importing
        # the renderer (import cycle); the equality is pinned.
        from ai_clip_studio.product_renderer import INK_RGB
        self.assertEqual(MATERIAL_INK, INK_RGB)

    def test_get_material_returns_copy(self):
        first = get_material("leather")
        first["base_color"] = (1, 2, 3)
        self.assertNotEqual(get_material("leather")["base_color"],
                            (1, 2, 3))

    def test_unknown_material_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_material("unobtainium")

    def test_only_gold_emissive_emits(self):
        for name in MATERIAL_CATALOG:
            entry = get_material(name)
            if name == "gold-emissive":
                self.assertGreater(entry["emissive_intensity"], 0)
                self.assertGreater(entry["emissive_radius"], 0)
                self.assertNotEqual(entry["emissive_color"], (0, 0, 0))
            else:
                self.assertEqual(entry["emissive_intensity"], 0.0)
                self.assertEqual(entry["emissive_radius"], 0.0)

    def test_resolve_name_dict_and_override(self):
        self.assertEqual(resolve_material("steel"),
                         get_material("steel"))
        over = resolve_material({"base": "leather",
                                 "base_color": (10, 20, 30)})
        self.assertEqual(over["base_color"], (10, 20, 30))
        self.assertEqual(over["outline"], MATERIAL_INK)
        standalone = resolve_material({
            "base_color": (1, 2, 3), "outline": (4, 5, 6),
            "emissive_color": (0, 0, 0), "emissive_intensity": 0.0,
            "emissive_radius": 0.0})
        self.assertEqual(standalone["base_color"], (1, 2, 3))

    def test_resolve_rejects_bad_specs(self):
        with self.assertRaises(KeyError):
            resolve_material("nope")
        with self.assertRaises(KeyError):
            resolve_material({"base": "nope"})
        with self.assertRaises(ValueError):
            resolve_material({"base": "steel", "shininess": 9})
        with self.assertRaises(ValueError):
            resolve_material({"base": "steel",
                              "emissive_intensity": 2.0})
        with self.assertRaises(ValueError):
            resolve_material({"base": "steel",
                              "emissive_radius": -1.0})
        with self.assertRaises(ValueError):
            resolve_material({"base_color": (1, 2, 3)})
        with self.assertRaises(ValueError):
            resolve_material(42)

    def test_validate_entry_rejects_bad_values(self):
        good = dict(get_material("bronze"))
        for bad in (dict(good, base_color=(300, 0, 0)),
                    dict(good, outline=(1, 2)),
                    dict(good, emissive_intensity=-0.1),
                    dict(good, emissive_intensity=float("nan")),
                    dict(good, emissive_radius=-0.5)):
            with self.assertRaises(ValueError, msg=str(bad)):
                validate_material_entry(bad)
        missing = dict(good)
        del missing["outline"]
        with self.assertRaises(ValueError):
            validate_material_entry(missing)

    def test_material_light_none_when_not_emissive(self):
        for name in ("leather", "steel", "paper", "wood", "stone",
                     "cloth", "bronze"):
            self.assertIsNone(
                material_emissive_light(name, (0.0, 1.0, -2.0)), name)

    def test_material_light_calibrated_like_energy_glow(self):
        light = material_emissive_light("gold-emissive",
                                        (0.0, 1.0, -2.0))
        self.assertIsInstance(light, PointLight)
        self.assertAlmostEqual(
            light.intensity, 0.6 * ENERGY_GLOW_PEAK_INTENSITY)
        self.assertEqual(light.color, (255, 210, 90))
        # Irradiance at the emissive radius is 5% of the peak.
        irr = light.irradiance((2.5, 1.0, -2.0), (-1, 0, 0))
        self.assertAlmostEqual(
            irr, light.intensity * ENERGY_GLOW_EDGE_FRACTION,
            places=6)

    def test_catalog_json_round_trips(self):
        blob = material_catalog_json()
        text = json.dumps(blob)
        back = json.loads(text)
        self.assertEqual(back, blob)
        self.assertEqual(back["gold-emissive"]["base_color"],
                         [232, 190, 60])


class TestEnergyGlowProducerShape(unittest.TestCase):
    def test_state_vocabulary_mirrors_prop_system(self):
        self.assertEqual(tuple(PROP_STATES), ENERGY_GLOW_PROP_STATES)
        self.assertEqual(tuple(_HELD_STATES), ENERGY_GLOW_HELD_STATES)

    def test_a_record_validates_with_pixel_space(self):
        glow = validate_energy_glow(dict(A_RECORD))
        self.assertEqual(glow["position_space"], "pixels")
        self.assertEqual(glow["source_position"], (960.0, 540.0))
        self.assertEqual(glow["prop_id"], "PROP_LIGHTNING")
        self.assertEqual(glow["state"], "GRASPED")
        self.assertEqual(glow["holder"], "CHAR_ZEUS")
        self.assertEqual(glow["radius"], 240.0)

    def test_intensity_zero_radius_zero_is_valid_and_dark(self):
        # The producer scales radius by intensity, so the first
        # frame of a held run carries radius 0. It must validate
        # and produce a zero light, never raise.
        rec = dict(A_RECORD, intensity=0.0, radius=0.0,
                   source_position=(0.6, 1.2, -2.5))
        glow = validate_energy_glow(rec)
        self.assertEqual(glow["radius"], 0.0)
        light = energy_glow_to_point_light(rec)
        self.assertEqual(light.intensity, 0.0)
        self.assertEqual(
            light.irradiance((0.6, 1.2, -1.5), (0, 0, -1)), 0.0)

    def test_non_held_state_produces_no_light(self):
        for state in ("WORLD_STATIC", "RELEASED", "APPROACHING"):
            rec = dict(A_RECORD, state=state,
                       source_position=(0.6, 1.2, -2.5))
            light = energy_glow_to_point_light(rec)
            self.assertEqual(light.intensity, 0.0, state)
            self.assertEqual(
                light.irradiance((0.6, 1.2, -1.5), (0, 0, -1)), 0.0,
                state)

    def test_held_states_produce_light(self):
        for state in ENERGY_GLOW_HELD_STATES:
            rec = dict(A_RECORD, state=state,
                       source_position=(0.6, 1.2, -2.5),
                       radius=6.0)
            light = energy_glow_to_point_light(rec)
            self.assertGreater(light.intensity, 0.0, state)

    def test_unknown_state_rejected(self):
        with self.assertRaises(ValueError):
            validate_energy_glow(dict(A_RECORD, state="FLOATING"))
        with self.assertRaises(ValueError):
            validate_energy_glow(dict(A_RECORD, state=7))

    def test_bad_prop_id_and_holder_rejected(self):
        with self.assertRaises(ValueError):
            validate_energy_glow(dict(A_RECORD, prop_id=7))
        with self.assertRaises(ValueError):
            validate_energy_glow(dict(A_RECORD, holder=3.5))
        ok = validate_energy_glow(dict(A_RECORD, holder=None))
        self.assertIsNone(ok["holder"])

    def test_pixel_record_to_point_light_raises(self):
        with self.assertRaises(ValueError):
            energy_glow_to_point_light(dict(A_RECORD))

    def test_hex_color_accepted(self):
        glow = validate_energy_glow(dict(
            A_RECORD, color="#78B4FF",
            source_position=(0.6, 1.2, -2.5), radius=6.0))
        self.assertEqual(glow["color"], (120, 180, 255))

    def test_world_record_unchanged(self):
        rec = {"intensity": 0.5, "color": [120, 180, 255],
               "radius": 6, "source_position": [0.6, 1.2, -2.5]}
        glow = validate_energy_glow(rec)
        self.assertEqual(glow["position_space"], "world")
        self.assertNotIn("state", glow)
        self.assertNotIn("prop_id", glow)


class TestPixelGlowBridge(unittest.TestCase):
    def _camera(self):
        return PerspectiveCamera(position=(0.0, 2.0, 4.8),
                                 target=(0.0, 1.2, 0.0),
                                 fov_deg=46.0, aspect=16 / 9)

    def test_unproject_round_trips_projection(self):
        cam = self._camera()
        for world in ((0.6, 1.2, -2.5), (-3.2, 1.0, -5.75),
                      (2.0, 0.5, 1.0), (0.0, 1.8, -3.2)):
            px, py, _, vis = cam.project(world, 1920, 1080)
            self.assertTrue(vis, world)
            depth = cam.depth_of(world)
            back = unproject_pixel(cam, px, py, (1920, 1080), depth)
            for a, b in zip(back, world):
                self.assertAlmostEqual(a, b, places=6)

    def test_unproject_rejects_bad_depth(self):
        cam = self._camera()
        with self.assertRaises(ValueError):
            unproject_pixel(cam, 960, 540, (1920, 1080), 0.05)
        with self.assertRaises(ValueError):
            unproject_pixel(cam, 960, 540, (1920, 1080), -3.0)
        with self.assertRaises(ValueError):
            unproject_pixel(cam, 960, 540, (1920, 1080),
                            float("nan"))

    def test_bridge_converts_position_and_radius(self):
        cam = self._camera()
        anchor = (0.6, 1.2, -2.5)
        px, py, _, _ = cam.project(anchor, 1920, 1080)
        depth = cam.depth_of(anchor)
        rec = dict(A_RECORD, source_position=(px, py), radius=240.0)
        world = pixel_glow_to_world_glow(rec, cam, (1920, 1080),
                                         depth)
        self.assertEqual(world["position_space"], "world")
        for a, b in zip(world["source_position"], anchor):
            self.assertAlmostEqual(a, b, places=6)
        # Radius: inverse of project_size at the same depth.
        expect = 240.0 / cam.project_size(1.0, anchor, 1080)
        self.assertAlmostEqual(world["radius"], expect, places=6)
        # Provenance fields survive the crossing.
        self.assertEqual(world["prop_id"], "PROP_LIGHTNING")
        self.assertEqual(world["state"], "GRASPED")
        self.assertEqual(world["holder"], "CHAR_ZEUS")
        self.assertEqual(world["intensity"], 1.0)
        # The converted record makes a real light.
        light = energy_glow_to_point_light(world)
        self.assertGreater(light.intensity, 0.0)

    def test_bridge_passes_world_records_through(self):
        cam = self._camera()
        rec = {"intensity": 0.5, "color": (120, 180, 255),
               "radius": 6.0, "source_position": (0.6, 1.2, -2.5)}
        out = pixel_glow_to_world_glow(rec, cam, (1920, 1080), 5.0)
        self.assertEqual(out["source_position"], (0.6, 1.2, -2.5))
        self.assertEqual(out["radius"], 6.0)


class TestTintedTextures(unittest.TestCase):
    def test_unit_gain_is_identical(self):
        tex = Image.new("RGB", (40, 40), (100, 120, 140))
        quad = [(10, 10), (10, 50), (50, 50), (50, 10)]
        a = Image.new("RGB", (60, 60), (0, 0, 0))
        b = Image.new("RGB", (60, 60), (0, 0, 0))
        paste_textured_quad(a, quad, tex, 0.8)
        paste_textured_quad(b, quad, tex, 0.8, (1.0, 1.0, 1.0))
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_blue_gain_cools_patch(self):
        tex = Image.new("RGB", (40, 40), (100, 100, 100))
        quad = [(10, 10), (10, 50), (50, 50), (50, 10)]
        img = Image.new("RGB", (60, 60), (0, 0, 0))
        paste_textured_quad(img, quad, tex, 1.0, (1.0, 1.2, 1.6))
        px = img.getpixel((30, 30))
        self.assertEqual(px, (100, 120, 160))

    def test_gain_clamps_at_255(self):
        tex = Image.new("RGB", (40, 40), (200, 200, 200))
        quad = [(10, 10), (10, 50), (50, 50), (50, 10)]
        img = Image.new("RGB", (60, 60), (0, 0, 0))
        paste_textured_quad(img, quad, tex, 1.0, (1.5, 1.5, 1.5))
        self.assertEqual(img.getpixel((30, 30)), (255, 255, 255))


class TestRealProducerReconciliation(unittest.TestCase):
    """The B/A reconciliation, closed against the REAL producer.

    B's consumer was written against an assumed record shape before
    A delivered PropStateMachine.energy_glow_at. These tests call
    the actual producer (A's construction pattern from
    test_testf_acting.py: PICK_UP then HAND_OVER, 1920x1080 joints
    space) and feed its records through validate_energy_glow ->
    pixel_glow_to_world_glow -> render_environment. Hand-built
    dicts (TestEnergyGlowProducerShape) pin the contract; these
    pin the integration. The producer docstring calls
    source_position 'world x, y', but the values live in the
    joints-dict coordinate space (pixels in the 2D renderer) —
    the validator tags 2-tuples as pixels and the bridge is the
    only sanctioned crossing.
    """

    GROUND_Y = 920.0

    def _psm(self):
        events = [
            {"action_id": "P1", "action_type": "PICK_UP",
             "actor_id": "CHAR_A", "prop_id": "prop_bolt",
             "start_time": 0.0, "end_time": 1.0,
             "required_pose": {"primitive": "pick_up",
                               "params": {"hand": "r"}}},
            {"action_id": "H1", "action_type": "HAND_OVER",
             "actor_id": "CHAR_A", "target_id": "CHAR_B",
             "prop_id": "prop_bolt", "start_time": 1.0,
             "end_time": 2.5,
             "required_pose": {"primitive": "hand_over",
                               "params": {"hand": "r"}}},
        ]
        return PropStateMachine(
            [{"id": "prop_bolt", "kind": "bolt",
              "energy": {"color": (120, 180, 255), "radius_px": 260.0}},
             {"id": "prop_rock", "kind": "generic"}],
            events,
            staging={"prop_bolt": (500.0, 700.0),
                     "prop_rock": (300.0, 800.0)},
            ground_y=self.GROUND_Y)

    def _joints(self):
        return {
            "CHAR_A": {"hand_r": (500.0, 700.0), "hand_l": (460.0, 700.0),
                       "hip": (480.0, 600.0), "facing": 1},
            "CHAR_B": {"hand_r": (640.0, 700.0), "hand_l": (600.0, 700.0),
                       "hip": (620.0, 600.0), "facing": -1},
        }

    def test_full_ramp_record_validates_exactly(self):
        record = self._psm().energy_glow_at("prop_bolt", 1.0,
                                            self._joints())
        self.assertIsNotNone(record)
        glow = validate_energy_glow(record)
        self.assertEqual(glow["position_space"], "pixels")
        self.assertEqual(glow["prop_id"], "prop_bolt")
        self.assertEqual(glow["holder"], "CHAR_A")
        # t=1.0 is the HAND_OVER start: the state is TRANSFERRED,
        # still a held state (the ramp survives the transfer).
        self.assertEqual(glow["state"], "TRANSFERRED")
        self.assertIn(glow["state"], ENERGY_GLOW_HELD_STATES)
        self.assertAlmostEqual(glow["intensity"], 1.0)
        self.assertAlmostEqual(glow["radius"], 260.0)
        self.assertEqual(glow["color"], (120, 180, 255))
        # Mid pick-up (grasp 0.45, ramp ends 0.85) the bolt is
        # held at full intensity; the producer's hold state here
        # is ATTACHED_TO_HAND (GRASPED as a literal is covered by
        # the hand-built held-states test, not the live timing).
        held = validate_energy_glow(self._psm().energy_glow_at(
            "prop_bolt", 0.9, self._joints()))
        self.assertIn(held["state"], ENERGY_GLOW_HELD_STATES)
        self.assertAlmostEqual(held["intensity"], 1.0)

    def test_mid_ramp_record_validates(self):
        record = self._psm().energy_glow_at("prop_bolt", 0.65,
                                            self._joints())
        glow = validate_energy_glow(record)
        self.assertGreater(glow["intensity"], 0.0)
        self.assertLess(glow["intensity"], 1.0)
        self.assertAlmostEqual(glow["radius"],
                               260.0 * glow["intensity"])

    def test_pre_grasp_none_and_handover_holder(self):
        psm = self._psm()
        joints = self._joints()
        self.assertIsNone(psm.energy_glow_at("prop_bolt", 0.1, joints))
        # During the transfer the giver still holds (transfer at
        # u=0.60 of the 1.0-2.5 s window) and intensity stays full.
        during = psm.energy_glow_at("prop_bolt", 1.2, joints)
        glow = validate_energy_glow(during)
        self.assertEqual(glow["holder"], "CHAR_A")
        self.assertAlmostEqual(glow["intensity"], 1.0)
        # At the window end the receiver owns the bolt.
        after = validate_energy_glow(
            psm.energy_glow_at("prop_bolt", 2.5, joints))
        self.assertEqual(after["holder"], "CHAR_B")
        self.assertAlmostEqual(after["intensity"], 1.0)

    def test_producer_record_flows_to_render(self):
        psm = self._psm()
        joints = self._joints()
        record = psm.energy_glow_at("prop_bolt", 1.0, joints)
        cam = PerspectiveCamera(position=(0.0, 2.0, 4.8),
                                target=(0.0, 1.5, 0.0), fov_deg=50.0,
                                aspect=1920 / 1080)
        depth = cam.depth_of((0.0, 1.0, -2.0))
        world = pixel_glow_to_world_glow(record, cam, (1920, 1080),
                                         depth)
        self.assertEqual(world["position_space"], "world")
        self.assertGreater(world["radius"], 0.0)
        # Round-trip: the world point re-projects onto the
        # producer's pixel position in the joints space.
        px, py, _s, vis = cam.project(world["source_position"],
                                      1920, 1080)
        self.assertTrue(vis)
        ox, oy = record["source_position"]
        self.assertLess(math.hypot(px - ox, py - oy), 2.0)
        # GENERIC_NEUTRAL is unresponsive by construction (3
        # elements, unpainted ground), so the render leg uses the
        # real Zeus forge package, whose floor and walls carry
        # point-light shading (the pulse-clip proof subject).
        root = Path(__file__).resolve().parents[2]
        text = (root / "examples"
                / "zeus_ep01_fall_of_cronus.studio.md").read_text(
                    encoding="utf-8")
        doc = parse_studio_script_v1(text)
        loc = next(d for d in doc.locations
                   if (dict(d) if isinstance(d, dict) else vars(d))
                   .get("id") == "LOC_DIVINE_FORGE")
        traits = dict(loc) if isinstance(loc, dict) else vars(loc)
        pkg = build_environment(traits, time_of_day="day")
        dry = render_environment(pkg, cam, size=(960, 540))
        lit = render_environment(pkg, cam, size=(960, 540),
                                 energy_glow=world)
        self.assertGreater(measure_mean_luminance(lit),
                           measure_mean_luminance(dry) + 0.1)


if __name__ == "__main__":
    unittest.main()
