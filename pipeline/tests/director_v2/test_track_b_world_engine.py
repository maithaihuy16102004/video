"""Unit tests for Track B — General Cinematic Environment Engine."""
from __future__ import annotations

import unittest
from pathlib import Path
import cairo

from pipeline.director_v2.world_engine.location_dna import get_location_dna, LocationVisualDNA
from pipeline.director_v2.world_engine.materials import MaterialSystem, MaterialType, MATERIAL_REGISTRY
from pipeline.director_v2.world_engine.rough_path import ControlledIrregularityEngine
from pipeline.director_v2.world_engine.composition import CinematicCompositionEngine, DepthPlane
from pipeline.director_v2.world_engine.lighting import WorldLightingEngine
from pipeline.director_v2.world_engine.storytelling import EnvironmentalStorytelling, StoryState
from pipeline.director_v2.world_engine.svg_assets import IllustratedAssetResolver
from pipeline.director_v2.world_engine.scene_world_renderer import GeneralWorldEngine
from pipeline.director_v2.zero_cost.five_scene_prototype import create_five_blueprints


class TestTrackBWorldEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.blueprints = create_five_blueprints()
        self.bp_hospital = next(b for b in self.blueprints if "HOSPITAL" in b.scene_id)
        self.bp_beerhall = next(b for b in self.blueprints if "BEER_HALL" in b.scene_id)
        self.bp_trench = next(b for b in self.blueprints if "TRENCH_GROUND" in b.scene_id)

    def test_location_visual_dna(self) -> None:
        dna_hosp = get_location_dna("pasewalk_military_hospital_1918")
        self.assertEqual(dna_hosp.dna_id, "MILITARY_HOSPITAL")
        self.assertIn("PLASTER", dna_hosp.dominant_materials)

        dna_beer = get_location_dna("beer_hall_munich_1919")
        self.assertEqual(dna_beer.dna_id, "BEER_HALL")
        self.assertIn("WOOD", dna_beer.dominant_materials)

        dna_trench = get_location_dna("western_front_trench_1916")
        self.assertEqual(dna_trench.dna_id, "WWI_TRENCH")
        self.assertIn("MUD", dna_trench.dominant_materials)

    def test_material_system_registry(self) -> None:
        expected_types = [
            MaterialType.WOOD, MaterialType.METAL, MaterialType.STONE,
            MaterialType.PLASTER, MaterialType.FABRIC, MaterialType.GLASS,
            MaterialType.PAPER, MaterialType.MUD, MaterialType.BRICK,
            MaterialType.EARTH, MaterialType.LEATHER,
        ]
        for mt in expected_types:
            self.assertIn(mt, MATERIAL_REGISTRY)
            prop = MaterialSystem.get_material(mt)
            self.assertEqual(prop.mat_type, mt)

    def test_material_shaders_execution(self) -> None:
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 200)
        ctx = cairo.Context(surf)
        MaterialSystem.apply_wood_grain(ctx, 10, 10, 80, 80, seed=1)
        MaterialSystem.apply_metal_specular(ctx, 100, 10, 80, 80, light_dx=1.0)
        MaterialSystem.apply_stone_stipple(ctx, 10, 100, 80, 80, seed=2, count=20)
        MaterialSystem.apply_fabric_weave(ctx, 100, 100, 80, 80, step=8.0)
        MaterialSystem.apply_glass_reflection(ctx, 10, 10, 80, 80)
        MaterialSystem.apply_mud_squelch(ctx, 100, 10, 80, 80, seed=3)

    def test_controlled_irregularity(self) -> None:
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 200)
        ctx = cairo.Context(surf)
        ControlledIrregularityEngine.draw_hand_line(ctx, 10, 10, 100, 10, roughness=0.8)
        ControlledIrregularityEngine.draw_irregular_rect(ctx, 20, 20, 60, 60, roughness=0.6)
        ControlledIrregularityEngine.draw_architectural_hatch(ctx, [(10, 10), (90, 10), (90, 90), (10, 90)])

    def test_composition_engine(self) -> None:
        comp = CinematicCompositionEngine(1920, 1080)
        layers = comp.create_depth_hierarchy(self.bp_hospital)
        self.assertIn(DepthPlane.NEAR_FG, layers)
        self.assertIn(DepthPlane.FG, layers)
        self.assertIn(DepthPlane.MG, layers)
        self.assertIn(DepthPlane.BG, layers)
        self.assertIn(DepthPlane.FAR_BG, layers)

        framing = comp.get_foreground_framing_rect(self.bp_hospital)
        self.assertIsNotNone(framing)

    def test_lighting_engine_contrast_and_vectors(self) -> None:
        lighting = WorldLightingEngine(self.bp_hospital.lighting, self.bp_hospital.atmosphere)
        self.assertEqual(lighting.key_dx, 1.0)
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 400)
        ctx = cairo.Context(surf)
        lighting.apply_directional_ambient_pass(ctx, 400, 400, 200.0)
        lighting.apply_shadow_zone(ctx, 200, 200, 50, 20)
        lighting.apply_story_focus_contrast(ctx, 400, 400, 200, 200, 100)

    def test_environmental_storytelling(self) -> None:
        mods_trench = EnvironmentalStorytelling.resolve_prop_modifiers(self.bp_trench)
        self.assertGreater(len(mods_trench), 0)
        states = [st for m in mods_trench for st in m.states]
        self.assertIn(StoryState.DAMAGED, states)

    def test_illustrated_assets_catalog(self) -> None:
        resolver = IllustratedAssetResolver()
        assets = resolver.list_manifest()
        self.assertGreaterEqual(len(assets), 10)
        ids = [a["asset_id"] for a in assets]
        self.assertIn("hospital_bed_iron_01", ids)
        self.assertIn("tavern_table_oak_01", ids)
        self.assertIn("trench_timber_revetment_01", ids)

    def test_general_world_engine_render(self) -> None:
        engine = GeneralWorldEngine(960, 540)
        # Test Environment Only
        surf_env = engine.render_environment_only(self.bp_hospital)
        self.assertEqual(surf_env.get_width(), 960)
        self.assertEqual(surf_env.get_height(), 540)

        # Test Composite
        surf_comp = engine.render_composite_with_actor(self.bp_hospital)
        self.assertEqual(surf_comp.get_width(), 960)
        self.assertEqual(surf_comp.get_height(), 540)


if __name__ == "__main__":
    unittest.main()
