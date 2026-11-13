"""Test F environment tests (Subagent B, Cinematic Engine Upgrade).

Covers: FORGE selection from the REAL Zeus traits Mai supplied
(no invented traits), forge element-composition distinctness vs
street archetypes, Test F forge elements + attachment validity,
the forge-mouth point light in the package, the energy_glow
consumer contract (validation + falloff + tint math), P-S12
foreground composition at the anvil station, and render
determinism + glow response. Code-rendered measurements only.
"""
import unittest
from pathlib import Path

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import (
    build_environment,
    fit_foreground_to_frustum,
    render_environment,
    select_archetype,
    validate_fg_composition,
)
from ai_clip_studio.lighting import (
    ENERGY_GLOW_EDGE_FRACTION,
    ENERGY_GLOW_PEAK_INTENSITY,
    add_point_light_tint,
    energy_glow_to_point_light,
    light_for,
    point_light_gain,
    point_light_spec_to_light,
    rig_for,
    shade_color,
    shade_with_points,
    validate_energy_glow,
)
from ai_clip_studio.renderer25d.lighting import PointLight
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1

AGENT = Path(__file__).resolve().parents[2]
ZEUS_SCRIPT = AGENT / "examples/zeus_ep01_fall_of_cronus.studio.md"

PULSE = {"intensity": 1.0, "color": (120, 180, 255), "radius": 6.0,
         "source_position": (0.6, 1.2, -2.5)}

# Minimal keyword traits for the street archetypes (same field
# shape as the TestSelection fixtures: features + period).
EUROPEAN_STREET_TRAITS = {
    "features": ["Đường lát đá.", "Cột đèn đường.",
                 "Mặt tiền trát vữa.", "Biển hiệu cửa hàng."],
    "period": "1914"}
SHOPHOUSE_TRAITS = {
    "features": ["Nhà ống.", "Biển hiệu.", "Mái hiên.",
                 "Vỉa hè."],
    "period": "2024"}


def _zeus_forge_traits():
    text = ZEUS_SCRIPT.read_text(encoding="utf-8")
    doc = parse_studio_script_v1(text)
    loc = next(l for l in doc.locations
               if (l.get("id") if isinstance(l, dict) else l.id)
               == "LOC_DIVINE_FORGE")
    return dict(loc) if isinstance(loc, dict) else vars(loc)


def _standing_box(cam, width, height, x=0.6, z=-3.2):
    """Screen rect of a 1.8 m standing figure at the anvil station."""
    pts = [cam.project((cx, cy, z), width, height)[:2]
           for cx in (x - 0.4, x + 0.4) for cy in (0.0, 1.8)]
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def _patch_means(img, cx, cy, half=30):
    crop = img.crop((int(cx) - half, int(cy) - half,
                     int(cx) + half, int(cy) + half))
    px = list(crop.getdata())
    n = len(px)
    return tuple(sum(p[ch] for p in px) / n for ch in range(3))


class TestForgeSelection(unittest.TestCase):
    def test_real_zeus_traits_select_forge(self):
        got, score, hits = select_archetype(_zeus_forge_traits())
        self.assertEqual(got, "FORGE")
        self.assertGreaterEqual(score, 2)
        self.assertTrue(hits)

    def test_street_keyword_cannot_hijack_forge(self):
        # The T4 hijack case: a defaulted location_keyword "street"
        # must not override the forge trait evidence.
        traits = _zeus_forge_traits()
        traits["render_traits"] = dict(traits.get("render_traits") or {})
        traits["render_traits"]["location_keyword"] = "street"
        pkg = build_environment(traits, time_of_day="day")
        self.assertEqual(pkg["archetype"], "FORGE")

    def test_forge_composition_distinct_from_streets(self):
        forge = build_environment(_zeus_forge_traits(),
                                  time_of_day="day")
        street = build_environment(EUROPEAN_STREET_TRAITS,
                                   time_of_day="day")
        shophouse = build_environment(SHOPHOUSE_TRAITS,
                                      time_of_day="day")
        self.assertEqual(street["archetype"], "EUROPEAN_STREET_1900")
        self.assertEqual(shophouse["archetype"], "SHOPHOUSE_STREET")
        forge_kinds = {e["kind"] for e in forge["elements"]}
        # Forge-only signature elements: none may appear in a street.
        for kind in ("furnace", "fire", "anvil", "bellows", "ingot",
                     "coal", "tongs", "hammer"):
            self.assertIn(kind, forge_kinds)
            self.assertNotIn(
                kind, {e["kind"] for e in street["elements"]},
                f"{kind} leaked into EUROPEAN_STREET_1900")
            self.assertNotIn(
                kind, {e["kind"] for e in shophouse["elements"]},
                f"{kind} leaked into SHOPHOUSE_STREET")
        # No street furniture in the forge: no facades, lamps,
        # awnings, or sign boards.
        for kind in ("facade", "lamp_post", "awning", "sign_board",
                     "shopfront"):
            self.assertNotIn(kind, forge_kinds)


class TestForgeBuild(unittest.TestCase):
    def test_forge_validates_clean(self):
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        self.assertEqual(pkg["validation"], [])
        self.assertEqual(pkg["period_errors"], [])

    def test_testf_elements_present_and_attached(self):
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        by_id = {e["id"]: e for e in pkg["elements"]}
        core = by_id["firemouth_core"]
        self.assertEqual(core["attachment"]["parent"], "firemouth")
        self.assertEqual(core["attachment"]["relation"], "overlaps")
        ingot = by_id["hot_ingot"]
        self.assertEqual(ingot["attachment"]["parent"], "anvil_top")
        self.assertEqual(ingot["attachment"]["relation"], "on_top")
        steam = by_id["quench_steam"]
        self.assertIn("suspension", steam["extra"])
        coal = by_id["coal_pile"]
        self.assertEqual(coal["attachment"]["relation"], "on_ground")
        self.assertAlmostEqual(
            coal["center"][1] - coal["size"][1] / 2, 0.0, places=6)
        for tool_id in ("bench_hammer", "bench_tongs"):
            tool = by_id[tool_id]
            self.assertEqual(tool["attachment"]["parent"], "bench_top")
            self.assertEqual(tool["attachment"]["relation"], "on_top")

    def test_forge_emits_point_light_package(self):
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        lights = pkg["point_lights"]
        self.assertEqual(len(lights), 1)
        light = lights[0]
        self.assertEqual(light["id"], "forge_mouth_glow")
        # The light sits exactly on the firemouth element.
        firemouth = next(e for e in pkg["elements"]
                         if e["id"] == "firemouth")
        self.assertEqual(tuple(light["position"]), firemouth["center"])
        self.assertEqual(tuple(light["color"]), firemouth["color"])
        self.assertGreater(light["intensity"], 0)
        self.assertGreater(light["falloff_k"], 0)
        # JSON-safe: the emitter/registry path serializes it.
        import json
        json.dumps(lights)

    def test_other_archetypes_emit_no_point_lights(self):
        for traits in (EUROPEAN_STREET_TRAITS, SHOPHOUSE_TRAITS):
            pkg = build_environment(traits, time_of_day="day")
            self.assertEqual(pkg["point_lights"], [])

    def test_forge_has_all_three_depth_layers(self):
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        layers = pkg["layers"]
        self.assertTrue(layers["BG"])  # forge mouth + walls
        self.assertTrue(layers["MG"])  # anvil station
        self.assertTrue(layers["FG"])  # occlusion barrel + crate
        bg_kinds = {e["kind"] for e in pkg["elements"]
                    if e["layer"] == "BG"}
        self.assertIn("fire", bg_kinds)
        mg_kinds = {e["kind"] for e in pkg["elements"]
                    if e["layer"] == "MG"}
        self.assertIn("anvil", mg_kinds)


class TestEnergyGlowContract(unittest.TestCase):
    def test_valid_record_normalizes(self):
        glow = validate_energy_glow(
            {"intensity": 0.5, "color": [120, 180, 255], "radius": 6,
             "source_position": [0.6, 1.2, -2.5]})
        self.assertEqual(glow["intensity"], 0.5)
        self.assertEqual(glow["color"], (120, 180, 255))
        self.assertEqual(glow["radius"], 6.0)
        self.assertEqual(glow["source_position"], (0.6, 1.2, -2.5))

    def test_missing_key_rejected(self):
        for missing in ("intensity", "color", "radius",
                        "source_position"):
            rec = dict(PULSE)
            del rec[missing]
            with self.assertRaises(ValueError, msg=missing):
                validate_energy_glow(rec)

    def test_bad_values_rejected(self):
        # NOTE (B2 contract evolution): radius=0 and 2-element
        # source_position were rejected here when the consumer
        # was written against an ASSUMED record shape. The real
        # producer (PropStateMachine.energy_glow_at) legitimately
        # emits radius 0 at intensity 0 (radius_px * intensity)
        # and 2-element pixel positions; rejecting them would
        # crash on real producer output. Both are now accepted
        # and covered by TestEnergyGlowProducerShape in
        # test_testf_materials.py. Negative radius and malformed
        # positions are still rejected.
        bad = [
            dict(PULSE, intensity=1.5),
            dict(PULSE, intensity=-0.1),
            dict(PULSE, intensity="full"),
            dict(PULSE, intensity=float("nan")),
            dict(PULSE, radius=-3),
            dict(PULSE, color=(300, 0, 0)),
            dict(PULSE, color=(1, 2)),
            dict(PULSE, source_position=(0,)),
            dict(PULSE, source_position=(0, 0, 0, 0)),
            dict(PULSE, source_position=(0, float("inf"), 0)),
        ]
        for rec in bad:
            with self.assertRaises(ValueError, msg=str(rec)):
                validate_energy_glow(rec)
        with self.assertRaises(ValueError):
            validate_energy_glow("not a dict")
        with self.assertRaises(ValueError):
            validate_energy_glow(None)

    def test_falloff_calibrated_to_radius(self):
        # Irradiance at exactly `radius`, facing the light, is 5%
        # of the peak: the documented ENERGY_GLOW_EDGE_FRACTION.
        light = energy_glow_to_point_light(PULSE)
        self.assertIsInstance(light, PointLight)
        self.assertAlmostEqual(light.intensity,
                               ENERGY_GLOW_PEAK_INTENSITY)
        irr = light.irradiance((0.6 + 6.0, 1.2, -2.5), (-1, 0, 0))
        self.assertAlmostEqual(
            irr, ENERGY_GLOW_PEAK_INTENSITY * ENERGY_GLOW_EDGE_FRACTION,
            places=6)

    def test_intensity_scales_linearly(self):
        zero = energy_glow_to_point_light(dict(PULSE, intensity=0.0))
        half = energy_glow_to_point_light(dict(PULSE, intensity=0.5))
        full = energy_glow_to_point_light(dict(PULSE, intensity=1.0))
        point, normal = (0.6, 1.2, -1.5), (0, 0, -1)
        self.assertEqual(zero.irradiance(point, normal), 0.0)
        self.assertAlmostEqual(half.irradiance(point, normal),
                               full.irradiance(point, normal) / 2,
                               places=9)

    def test_point_light_spec_round_trip(self):
        light = point_light_spec_to_light(
            {"id": "forge_mouth_glow", "position": (-3.2, 1.0, -5.75),
             "intensity": 1.2, "falloff_k": 0.08,
             "color": (255, 140, 40)})
        self.assertEqual(light.position, (-3.2, 1.0, -5.75))
        self.assertEqual(light.intensity, 1.2)
        self.assertEqual(light.color, (255, 140, 40))
        with self.assertRaises(ValueError):
            point_light_spec_to_light({"intensity": 1.0})
        with self.assertRaises(ValueError):
            point_light_spec_to_light(
                {"position": (0, 0, 0), "intensity": -1})


class TestPointLightShading(unittest.TestCase):
    def test_no_points_is_bit_identical_to_grayscale(self):
        rig = rig_for(light_for("day", "warm"))
        self.assertEqual(rig.points, [])
        for base in ((100, 100, 100), (96, 90, 84), (255, 140, 40)):
            for point, normal in (((0, 1, 0), (0, 0, 1)),
                                  ((2, 0.5, -3), (0, 1, 0)),
                                  ((-3, 2, -8), (0, 0, -1))):
                self.assertEqual(
                    shade_with_points(base, rig, point, normal),
                    shade_color(base, rig.irradiance(point, normal)))

    def test_gain_is_unit_without_points(self):
        rig = rig_for(light_for("day", "warm"))
        self.assertEqual(point_light_gain(rig, (0, 0, 0), (0, 1, 0)),
                         (1.0, 1.0, 1.0))
        self.assertEqual(
            add_point_light_tint((70, 62, 56), rig, (0, 0, 0),
                                 (0, 1, 0)),
            (70, 62, 56))

    def test_blue_pulse_cools_facing_surface(self):
        rig = rig_for(light_for("day", "warm"),
                      points=[energy_glow_to_point_light(PULSE)])
        base = (100, 100, 100)
        lit = shade_with_points(base, rig, (0.6, 1.2, -1.5),
                                (0, 0, -1))
        plain = shade_with_points(base, rig_for(light_for("day", "warm")),
                                  (0.6, 1.2, -1.5), (0, 0, -1))
        # Brighter overall, and blue rises more than red.
        self.assertGreater(sum(lit), sum(plain))
        self.assertGreater(lit[2] - lit[0], plain[2] - plain[0])

    def test_surface_facing_away_gets_no_point_light(self):
        rig = rig_for(light_for("day", "warm"),
                      points=[energy_glow_to_point_light(PULSE)])
        # Normal +z, light behind at -z: Lambert cosine is 0.
        self.assertEqual(point_light_gain(rig, (0.6, 1.2, -1.5),
                                          (0, 0, 1)),
                         (1.0, 1.0, 1.0))

    def test_forge_light_warms_floor_and_falls_off(self):
        rig = rig_for(light_for("day", "warm"), points=[
            point_light_spec_to_light(
                {"position": (-3.2, 1.0, -5.75), "intensity": 1.2,
                 "falloff_k": 0.08, "color": (255, 140, 40)})])
        base = (70, 62, 56)
        near = add_point_light_tint(base, rig, (-3.2, 0.0, -3.75),
                                    (0, 1, 0))
        far = add_point_light_tint(base, rig, (8.0, 0.0, 2.0),
                                   (0, 1, 0))
        self.assertGreater(near[0], base[0])  # warmed + brightened
        self.assertGreater(near[0] - near[2], base[0] - base[2])
        self.assertEqual(far, base)  # negligible at 12 m

    def test_rig_for_accepts_spec_dicts_and_objects(self):
        spec = light_for("day", "warm")
        by_dict = rig_for(spec, points=[
            {"position": (0, 1, 0), "intensity": 1.0,
             "color": (255, 255, 255)}])
        by_obj = rig_for(spec, points=[
            PointLight((0, 1, 0), intensity=1.0)])
        self.assertEqual(len(by_dict.points), 1)
        self.assertEqual(len(by_obj.points), 1)
        self.assertEqual(by_dict.points[0].position,
                         by_obj.points[0].position)


class TestForgeComposition(unittest.TestCase):
    def test_fg_validates_at_establishing_and_medium(self):
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        for shot_type in ("establishing", "medium"):
            cam = viewpoint_for_shot(shot_type, None, (0, 1.5, 0))
            fit = fit_foreground_to_frustum(pkg, cam,
                                            size=(1920, 1080))
            box = _standing_box(cam, 1920, 1080)
            res = validate_fg_composition(fit, cam, size=(1920, 1080),
                                          subject_boxes=[box])
            self.assertTrue(res["ok"], f"{shot_type}: {res['errors']}")
            self.assertEqual(res["errors"], [])
            self.assertEqual(len(res["elements"]), 2)
            for el in res["elements"]:
                self.assertTrue(el["in_frame"], el)
                self.assertFalse(el["overlaps_standing_box"], el)
                self.assertLess(el["area_fraction"], 0.40)


class TestForgeRender(unittest.TestCase):
    def test_render_deterministic_with_glow(self):
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        cam = viewpoint_for_shot("medium", None, (0, 1.5, 0))
        a = render_environment(pkg, cam, size=(480, 270),
                               energy_glow=PULSE)
        b = render_environment(pkg, cam, size=(480, 270),
                               energy_glow=PULSE)
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_glow_response_monotonic_on_anvil_patch(self):
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        cam = viewpoint_for_shot("medium", None, (0, 1.5, 0))
        ax, ay, _, _ = cam.project((0.6, 0.86, -3.2), 960, 540)
        means = []
        for intensity in (0.0, 0.5, 1.0):
            img = render_environment(
                pkg, cam, size=(960, 540),
                energy_glow=dict(PULSE, intensity=intensity))
            means.append(_patch_means(img, ax, ay))
        lums = [sum(m) / 3 for m in means]
        blue_shift = [m[2] - m[0] for m in means]
        # Luminance rises with pulse strength (margin 10/step).
        self.assertGreater(lums[1], lums[0] + 10)
        self.assertGreater(lums[2], lums[1] + 10)
        # Blue shift rises with pulse strength (margin 5/step):
        # the tint is cool, not just brighter.
        self.assertGreater(blue_shift[1], blue_shift[0] + 5)
        self.assertGreater(blue_shift[2], blue_shift[1] + 5)

    def test_forge_light_changes_render_vs_stripped(self):
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        cam = viewpoint_for_shot("medium", None, (0, 1.5, 0))
        lit = render_environment(pkg, cam, size=(480, 270))
        stripped = dict(pkg)
        stripped["point_lights"] = []
        unlit = render_environment(stripped, cam, size=(480, 270))
        self.assertNotEqual(lit.tobytes(), unlit.tobytes())

    def test_malformed_energy_glow_fails_loudly(self):
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        cam = viewpoint_for_shot("medium", None, (0, 1.5, 0))
        with self.assertRaises(ValueError):
            render_environment(pkg, cam, size=(480, 270),
                               energy_glow=dict(PULSE, intensity=2.0))

    def test_pixel_space_glow_fails_loudly_in_render(self):
        # A pixel-space record must be converted before render;
        # the renderer must not invent a depth (B2 bridge rule).
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        cam = viewpoint_for_shot("medium", None, (0, 1.5, 0))
        with self.assertRaises(ValueError):
            render_environment(
                pkg, cam, size=(480, 270),
                energy_glow={"intensity": 1.0,
                             "color": (170, 205, 255),
                             "radius": 240.0,
                             "source_position": (240.0, 135.0)})


class TestForgeSparks(unittest.TestCase):
    def _sparks_element(self):
        from ai_clip_studio.environment_v2 import spark_positions  # noqa: F401
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        return next(e for e in pkg["elements"]
                    if e["id"] == "anvil_sparks"), pkg

    def test_sparks_element_present_and_suspension_reasoned(self):
        el, pkg = self._sparks_element()
        self.assertEqual(el["kind"], "sparks")
        self.assertEqual(el["geometry"], "sparks")
        self.assertEqual(el["layer"], "MG")
        self.assertIn("suspension", el["extra"])
        self.assertEqual(el["extra"]["spark_count"], 14)
        self.assertEqual(pkg["validation"], [])

    def test_spark_positions_deterministic_count_and_envelope(self):
        from ai_clip_studio.environment_v2 import spark_positions
        el, _ = self._sparks_element()
        first = spark_positions(el, 7)
        second = spark_positions(el, 7)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 14)
        cx, cy, cz = el["center"]
        sx, sy, sz = el["size"]
        top = cy + sy / 2.0 + 0.07 * 18
        for (x, y, z), age_frac, _vel in first:
            self.assertLessEqual(abs(x - cx), sx / 2.0 + 0.4)
            self.assertLessEqual(abs(z - cz), sz / 2.0 + 0.4)
            self.assertGreaterEqual(y, cy - sy / 2.0 - 0.01)
            self.assertLessEqual(y, top + 0.01)
            self.assertGreaterEqual(age_frac, 0.0)
            self.assertLess(age_frac, 1.0)

    def test_spark_positions_vary_across_frames(self):
        from ai_clip_studio.environment_v2 import spark_positions
        el, _ = self._sparks_element()
        self.assertNotEqual(spark_positions(el, 0),
                            spark_positions(el, 9))

    def test_spark_frame_negative_rejected(self):
        from ai_clip_studio.environment_v2 import spark_positions
        el, _ = self._sparks_element()
        with self.assertRaises(ValueError):
            spark_positions(el, -1)

    def test_render_deterministic_per_spark_frame(self):
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        cam = viewpoint_for_shot("medium", None, (0, 1.5, 0))
        a = render_environment(pkg, cam, size=(480, 270),
                               spark_frame=5)
        b = render_environment(pkg, cam, size=(480, 270),
                               spark_frame=5)
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_sparks_move_and_stay_bounded(self):
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        cam = viewpoint_for_shot("medium", None, (0, 1.5, 0))
        a = render_environment(pkg, cam, size=(480, 270),
                               spark_frame=0)
        b = render_environment(pkg, cam, size=(480, 270),
                               spark_frame=9)
        self.assertNotEqual(a.tobytes(), b.tobytes())
        # Every differing pixel must lie inside the projected
        # spark envelope (expanded for streak tails + width).
        el = next(e for e in pkg["elements"]
                  if e["id"] == "anvil_sparks")
        cx, cy, cz = el["center"]
        sx, sy, sz = el["size"]
        corners = [(cx + dx * (sx / 2.0 + 0.4),
                    cy + dy * (sy / 2.0 + 1.3),
                    cz + dz * (sz / 2.0 + 0.4))
                   for dx in (-1, 1) for dy in (-1, 1)
                   for dz in (-1, 1)]
        pts = [cam.project(p, 480, 270)[:2] for p in corners]
        x0 = min(p[0] for p in pts) - 6
        x1 = max(p[0] for p in pts) + 6
        y0 = min(p[1] for p in pts) - 6
        y1 = max(p[1] for p in pts) + 6
        px_a, px_b = a.load(), b.load()
        differing = 0
        for y in range(270):
            for x in range(480):
                if px_a[x, y] != px_b[x, y]:
                    differing += 1
                    self.assertTrue(
                        x0 <= x <= x1 and y0 <= y <= y1,
                        f"spark pixel outside envelope at {(x, y)}")
        self.assertGreater(differing, 0)


class TestTintedTextureRender(unittest.TestCase):
    def test_textured_wall_cools_under_blue_pulse(self):
        # The forge back wall is a textured stone face. Under a
        # wide blue pulse it must COOL (blue-minus-red rises),
        # not merely brighten — the B2 tinted-texture path.
        pkg = build_environment(_zeus_forge_traits(),
                                time_of_day="day")
        cam = viewpoint_for_shot("medium", None, (0, 1.5, 0))
        wx, wy, _, _ = cam.project((-1.5, 3.0, -8.6), 960, 540)
        base = render_environment(pkg, cam, size=(960, 540))
        pulsed = render_environment(
            pkg, cam, size=(960, 540),
            energy_glow={"intensity": 1.0, "color": (120, 180, 255),
                         "radius": 12.0,
                         "source_position": (0.6, 1.2, -2.5)})
        m0 = _patch_means(base, wx, wy)
        m1 = _patch_means(pulsed, wx, wy)
        self.assertGreater((m1[2] - m1[0]) - (m0[2] - m0[0]), 3.0)


if __name__ == "__main__":
    unittest.main()
