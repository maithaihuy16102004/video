"""Unit tests for the Zero-Cost Cinematic Procedural Visual Engine."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cairo

from pipeline.director_v2.zero_cost.primitives import (
    draw_stone_column,
    draw_arched_loggia,
    draw_building_facade,
    draw_prussian_window,
    draw_timber_wall,
    draw_cobblestone_plane,
    draw_mud_duckboard_corridor,
    draw_puddle_reflection,
    draw_hospital_bed,
    draw_tavern_table_and_steins,
    draw_hanging_brass_lantern,
    draw_sandbag_revetment,
    draw_barbed_wire_entanglement,
    draw_artillery_crater,
    draw_light_shaft,
    draw_smoke_plumes,
    draw_ground_fog,
    draw_rain_and_drizzle,
    draw_vignette,
)
from pipeline.director_v2.zero_cost.location_kits import (
    get_location_kit,
    WWITrenchKit,
    MilitaryHospitalKit,
    Early1900sEuropeanStreetKit,
    BeerHallKit,
)
from pipeline.director_v2.zero_cost.lighting_engine import CinematicLightingEngine
from pipeline.director_v2.zero_cost.multi_plane_renderer import CinematicEnvironmentRenderer
from pipeline.director_v2.zero_cost.actor_rig import StickmanActorRig
from pipeline.director_v2.zero_cost.provider_router import VisualProviderRouter, QualityMode
from pipeline.director_v2.zero_cost.cost_ledger import ZeroCostBudgetLedger
from pipeline.director_v2.zero_cost.five_scene_prototype import create_five_blueprints, FiveSceneZeroCostRunner


class TestZeroCostEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 960, 540)
        self.ctx = cairo.Context(self.surf)

    def test_primitives_render_without_error(self) -> None:
        """Verify all parametric primitives draw cleanly onto a Cairo Context."""
        draw_stone_column(self.ctx, 10, 10, 60, 200, "CORINTHIAN", 1.0)
        draw_arched_loggia(self.ctx, 80, 10, 300, 200, 2, 20.0, 1.0)
        draw_building_facade(self.ctx, 400, 10, 250, 200, 2, 3, "NEOCLASSICAL", 1.0)
        draw_prussian_window(self.ctx, 670, 10, 120, 200, arched=True, light_shaft=True)
        draw_timber_wall(self.ctx, 10, 230, 200, 150, planks=6, damage=0.2)
        draw_cobblestone_plane(self.ctx, 220, 230, 250, 150, horizon_y=0.4, vp_x=340, vp_y=150)
        draw_mud_duckboard_corridor(self.ctx, 480, 380, 520, 230, vp_x=520, vp_y=230)
        draw_hospital_bed(self.ctx, 10, 400, 180, 100)
        draw_tavern_table_and_steins(self.ctx, 210, 400, 220, 100)
        draw_hanging_brass_lantern(self.ctx, 450, 420, scale=0.8, is_lit=True)
        draw_sandbag_revetment(self.ctx, 500, 400, 200, 80)
        draw_vignette(self.ctx, 960, 540, intensity=0.4)

    def test_location_kit_resolver(self) -> None:
        """Verify location IDs correctly map to the appropriate LocationKit subclass."""
        self.assertIsInstance(get_location_kit("western_front_trench_1916"), WWITrenchKit)
        self.assertIsInstance(get_location_kit("somme_1916"), WWITrenchKit)
        self.assertIsInstance(get_location_kit("pasewalk_military_hospital_1918"), MilitaryHospitalKit)
        self.assertIsInstance(get_location_kit("hospital_ward"), MilitaryHospitalKit)
        self.assertIsInstance(get_location_kit("beer_hall_munich_1919"), BeerHallKit)
        self.assertIsInstance(get_location_kit("buergerbraukeller"), BeerHallKit)
        self.assertIsInstance(get_location_kit("munich_odeonsplatz_1914"), Early1900sEuropeanStreetKit)

    def test_lighting_engine(self) -> None:
        """Verify lighting calculations, vectors, and shadow orientations."""
        bps = create_five_blueprints()
        bp1 = bps[0]  # LEFT_HIGH, SULLEN_OVERCAST, BOTTOM_RIGHT shadow
        engine = CinematicLightingEngine(bp1.lighting, bp1.atmosphere)

        self.assertEqual(engine.get_lighting_dx(), 1.0)
        sdx, sdy = engine.get_shadow_offset(1.0)
        self.assertGreater(sdx, 0.0)  # Shadow casts to right
        self.assertGreater(sdy, 0.0)  # Shadow casts down

    def test_actor_rig_pose_families(self) -> None:
        """Verify StickmanActorRig renders all specified pose families without exception."""
        rig = StickmanActorRig(960, 540)
        bps = create_five_blueprints()
        bp = bps[0]

        poses = [
            "THINK_CHIN", "ORATE_FIST", "DUCK_COVER", "LIE_BED", "KNEEL_GRIEF",
            "WALK", "RUN", "CROUCH", "SIT", "POINT", "READ", "WRITE",
            "LISTEN", "FEAR", "EXHAUSTED", "INJURED", "CONFUSED", "ANGRY",
            "OBSERVE", "HIDE", "CARRY", "PUSH", "PULL", "SALUTE",
        ]
        for p in poses:
            bp.character.pose_envelope = p
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 960, 540)
            ctx = cairo.Context(surf)
            rig.render_actor(ctx, bp)

    def test_zero_cost_budget_ledger(self) -> None:
        """Verify budget ledger strictly enforces $0.00 and tracks all local events."""
        ledger = ZeroCostBudgetLedger()
        ledger.record_free_intelligence("S01", "plan_shot")
        ledger.record_procedural_render("S01", "western_front_trench")
        ledger.record_cache_hit("S02", "asset_123")
        ledger.record_asset_reuse("S03", "master_456")

        d = ledger.to_dict()
        self.assertEqual(d["cost_summary"]["paid_cost_usd"], 0.00)
        self.assertEqual(d["cost_summary"]["gemini_image_paid_calls"], 0)
        self.assertTrue(d["cost_summary"]["zero_cost_guarantee_met"])
        self.assertEqual(d["cost_summary"]["gemini_text_free_calls"], 1)
        self.assertEqual(d["cost_summary"]["local_procedural_renders"], 1)

    def test_five_scene_blueprints_completeness(self) -> None:
        """Verify the 5 required test scenes cover all required shot sizes and locations."""
        bps = create_five_blueprints()
        self.assertEqual(len(bps), 5)

        shot_sizes = [b.camera.shot_size for b in bps]
        self.assertIn("GROUND_LEVEL", shot_sizes)
        self.assertIn("OTS", shot_sizes)
        self.assertIn("LOW_ANGLE", shot_sizes)
        self.assertIn("DEEP_PERSPECTIVE", shot_sizes)
        self.assertIn("HIGH_ANGLE", shot_sizes)

        locations = [b.history.location_id for b in bps]
        self.assertIn("western_front_trench_1916", locations)
        self.assertIn("pasewalk_military_hospital_1918", locations)
        self.assertIn("munich_odeonsplatz_1914", locations)
        self.assertIn("beer_hall_munich_1919", locations)


if __name__ == "__main__":
    unittest.main()
