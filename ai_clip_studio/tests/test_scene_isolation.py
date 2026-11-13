"""Scene-local isolation tests (Semantic Engine Upgrade §6, B2).

Covers: the ScopedState scope mechanism (SHOT -> SCENE -> PROJECT
inheritance via the contract, reset rules, entity no-sideways-leak,
explicit carry-over only), build_environment_scoped (store wins over
traits, per-attribute provenance, the Munich/trench/Munich leak
regression on REAL Ep1 script traits), and the scoped rain overlay
(deterministic, frame-animated, drawn only when the current scene
resolves rain — overcast dims light but draws no streaks).

Run from ~/workspace/agent/:
  python3 -m unittest ai_clip_studio.tests.test_scene_isolation -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.environment_v2 import (
    ScopedState,
    build_environment,
    build_environment_scoped,
    rain_overlay,
    render_environment,
    resolve_environment_attributes,
)
from ai_clip_studio.semantic_contracts import StateScope
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
SMALL = (480, 270)
CAMERA = ((0.0, 2.3, 4.8), (0.0, 1.5, 0.0), 50.0)


def _location_traits(script: str, location_id: str) -> dict:
    text = (EXAMPLES / script).read_text(encoding="utf-8")
    doc = parse_studio_script_v1(text)
    for loc in doc.locations:
        data = dict(loc) if isinstance(loc, dict) else vars(loc)
        if data.get("id") == location_id:
            return data
    raise AssertionError(f"location {location_id} not in {script}")


def _munich_traits():
    return _location_traits("hitler_ep01_munich_1914.studio.md",
                            "LOC_MUNICH_STREET")


def _trench_traits():
    return _location_traits("hitler_ep01_munich_1914.studio.md",
                            "LOC_YPRES_TRENCH")


def _diff_px(a, b) -> int:
    return sum(1 for x, y in zip(a.getdata(), b.getdata()) if x != y)


class TestScopedStateInheritance(unittest.TestCase):
    def _store(self):
        store = ScopedState()
        store.begin_project("P1")
        store.set(StateScope.PROJECT, "weather", "clear")
        store.begin_scene("SC01")
        store.set(StateScope.SCENE, "weather", "overcast")
        store.begin_shot("SH01")
        return store

    def test_shot_beats_scene_beats_project(self):
        store = self._store()
        store.set(StateScope.SHOT, "weather", "rain")
        self.assertEqual(store.resolve("weather"), "rain")
        store.set(StateScope.SHOT, "weather", None)
        self.assertEqual(store.resolve("weather"), "overcast")

    def test_fallback_chain_when_scopes_unset(self):
        store = ScopedState()
        store.begin_project("P1")
        store.set(StateScope.PROJECT, "weather", "clear")
        self.assertEqual(store.resolve("weather"), "clear")
        store.begin_scene("SC01")
        self.assertEqual(store.resolve("weather"), "clear")
        store.set(StateScope.SCENE, "weather", "rain")
        self.assertEqual(store.resolve("weather"), "rain")

    def test_unset_resolves_none(self):
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        self.assertIsNone(store.resolve("weather"))

    def test_resolve_with_source_agrees_with_resolve(self):
        store = self._store()
        store.set(StateScope.SHOT, "weather", "rain")
        store.set(StateScope.PROJECT, "mood", "warm")
        for key in ("weather", "mood", "missing"):
            value, source = store.resolve_with_source(key)
            self.assertEqual(value, store.resolve(key))
        self.assertEqual(store.resolve_with_source("weather"),
                         ("rain", "SHOT"))
        self.assertEqual(store.resolve_with_source("mood"),
                         ("warm", "PROJECT"))
        self.assertEqual(store.resolve_with_source("missing"),
                         (None, None))

    def test_string_scope_coercion_and_bad_scope(self):
        store = ScopedState()
        store.begin_project("P1")
        store.set("PROJECT", "weather", "clear")
        self.assertEqual(store.resolve("weather"), "clear")
        with self.assertRaises(ValueError):
            store.set("NOWHERE", "weather", "clear")

    def test_set_none_unsets(self):
        store = self._store()
        store.set(StateScope.SCENE, "weather", None)
        self.assertEqual(store.resolve("weather"), "clear")


class TestScopedStateResets(unittest.TestCase):
    def test_scene_change_resets_shot_scope(self):
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        store.begin_shot("SH01")
        store.set(StateScope.SHOT, "rain", True)
        store.begin_scene("SC02")
        self.assertIsNone(store.resolve("rain"))
        # Returning to the scene + shot does NOT resurrect the
        # deleted SHOT value: the reset was destructive.
        store.begin_scene("SC01")
        store.begin_shot("SH01")
        self.assertIsNone(store.resolve("rain"))

    def test_scene_values_persist_per_scene(self):
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        store.set(StateScope.SCENE, "weather", "rain")
        store.begin_scene("SC02")
        self.assertIsNone(store.resolve("weather"))
        store.begin_scene("SC01")
        self.assertEqual(store.resolve("weather"), "rain")

    def test_project_change_resets_below_project(self):
        store = ScopedState()
        store.begin_project("P1")
        store.set(StateScope.PROJECT, "mood", "warm")
        store.begin_scene("SC01")
        store.set(StateScope.SCENE, "weather", "rain")
        store.begin_shot("SH01")
        store.set(StateScope.SHOT, "rain", True)
        store.set(StateScope.CHARACTER, "costume", "military",
                  entity_id="CHAR_A")
        store.begin_project("P2")
        self.assertIsNone(store.resolve("weather"))
        self.assertIsNone(store.resolve("rain"))
        self.assertIsNone(store.resolve("mood"))
        store.begin_scene("SC01")
        self.assertIsNone(store.resolve(
            "costume", StateScope.CHARACTER, "CHAR_A"))
        # P1's PROJECT fact survives keyed-but-unreachable; its
        # below-PROJECT state was deleted by the reset.
        store.begin_project("P1")
        self.assertEqual(store.resolve("mood"), "warm")
        store.begin_scene("SC01")
        self.assertIsNone(store.resolve("weather"))

    def test_begin_shot_starts_empty(self):
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        store.begin_shot("SH01")
        store.set(StateScope.SHOT, "rain", True)
        store.begin_shot("SH02")
        self.assertIsNone(store.resolve("rain"))

    def test_same_scene_reentry_is_noop(self):
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        store.begin_shot("SH01")
        store.set(StateScope.SHOT, "rain", True)
        store.begin_scene("SC01")
        self.assertEqual(store.resolve("rain"), True)

    def test_guards_fail_loudly(self):
        store = ScopedState()
        with self.assertRaises(ValueError):
            store.begin_scene("SC01")
        with self.assertRaises(ValueError):
            store.begin_shot("SH01")
        with self.assertRaises(ValueError):
            store.set(StateScope.PROJECT, "weather", "clear")
        store.begin_project("P1")
        with self.assertRaises(ValueError):
            store.set(StateScope.SCENE, "weather", "rain")
        with self.assertRaises(ValueError):
            store.begin_shot("SH01")
        store.begin_scene("SC01")
        with self.assertRaises(ValueError):
            store.set(StateScope.SHOT, "rain", True)
        with self.assertRaises(ValueError):
            store.set(StateScope.CHARACTER, "costume", "military")
        with self.assertRaises(ValueError):
            store.begin_project("")


class TestScopedStateEntities(unittest.TestCase):
    def _store(self):
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        store.begin_shot("SH01")
        return store

    def test_character_values_do_not_leak_sideways(self):
        store = self._store()
        store.set(StateScope.CHARACTER, "costume", "military",
                  entity_id="CHAR_A")
        self.assertEqual(store.resolve("costume", StateScope.CHARACTER,
                                       "CHAR_A"), "military")
        # CHAR_B sees the chain only — never CHAR_A's value.
        self.assertIsNone(store.resolve("costume", StateScope.CHARACTER,
                                        "CHAR_B"))

    def test_prop_state_is_scene_local(self):
        store = self._store()
        store.set(StateScope.PROP, "held", True,
                  entity_id="PROP_LIGHTNING")
        store.begin_scene("SC02")
        self.assertIsNone(store.resolve("held", StateScope.PROP,
                                        "PROP_LIGHTNING"))

    def test_entity_value_beats_chain(self):
        store = self._store()
        store.set(StateScope.SCENE, "costume", "civilian")
        store.set(StateScope.CHARACTER, "costume", "military",
                  entity_id="CHAR_A")
        self.assertEqual(store.resolve("costume", StateScope.CHARACTER,
                                       "CHAR_A"), "military")
        self.assertEqual(store.resolve("costume"), "civilian")

    def test_carry_over_entity_explicit_only(self):
        store = self._store()
        store.set(StateScope.PROP, "held", True,
                  entity_id="PROP_LIGHTNING")
        store.begin_scene("SC02")
        self.assertIsNone(store.resolve("held", StateScope.PROP,
                                        "PROP_LIGHTNING"))
        store.carry_over_entity(StateScope.PROP, "PROP_LIGHTNING",
                                "held", "SC01")
        self.assertTrue(store.resolve("held", StateScope.PROP,
                                      "PROP_LIGHTNING"))
        self.assertEqual(len(store.carryover_log), 1)


class TestCarryOver(unittest.TestCase):
    def test_carry_over_copies_and_logs(self):
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        store.set(StateScope.SCENE, "weather", "rain")
        store.begin_scene("SC02")
        self.assertIsNone(store.resolve("weather"))
        store.carry_over("weather", "SC01")
        self.assertEqual(store.resolve("weather"), "rain")
        entry = store.carryover_log[0]
        self.assertEqual(entry["from_scene_id"], "SC01")
        self.assertEqual(entry["to_scene_id"], "SC02")

    def test_carry_over_missing_key_raises(self):
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        store.begin_scene("SC02")
        with self.assertRaises(KeyError):
            store.carry_over("weather", "SC01")

    def test_carry_over_same_scene_raises(self):
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        store.set(StateScope.SCENE, "weather", "rain")
        with self.assertRaises(ValueError):
            store.carry_over("weather", "SC01")

    def test_snapshot_is_json_safe(self):
        import json
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        store.set(StateScope.SCENE, "weather", "rain")
        json.dumps(store.snapshot())


class TestScopedBuild(unittest.TestCase):
    def test_store_weather_overrides_trait(self):
        store = ScopedState()
        store.begin_project("HITLER_EP01")
        store.begin_scene("SC01")
        store.set(StateScope.SCENE, "weather", "rain")
        pkg = build_environment_scoped(store, _munich_traits())
        self.assertEqual(pkg["provenance"]["scoped_resolution"]
                         ["weather"], "SCENE")
        self.assertEqual(pkg["light"]["mood"], "cold")
        self.assertEqual(pkg["provenance"]["scope"]["scene_id"], "SC01")

    def test_trait_fallback_when_store_silent(self):
        store = ScopedState()
        store.begin_project("HITLER_EP01")
        store.begin_scene("SC01")
        pkg = build_environment_scoped(store, _munich_traits())
        # Munich traits declare 'Overcast' -> trait source, cold.
        self.assertEqual(pkg["provenance"]["scoped_resolution"]
                         ["weather"], "trait")
        self.assertEqual(pkg["light"]["mood"], "cold")

    def test_store_time_of_day_and_mood(self):
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        store.set(StateScope.SCENE, "time_of_day", "dusk")
        store.set(StateScope.SCENE, "mood", "cold")
        pkg = build_environment_scoped(store, _trench_traits())
        self.assertEqual(pkg["light"]["time_of_day"], "dusk")
        self.assertEqual(pkg["provenance"]["scoped_resolution"]
                         ["time_of_day"], "SCENE")

    def test_no_scene_raises(self):
        store = ScopedState()
        store.begin_project("P1")
        with self.assertRaises(ValueError):
            build_environment_scoped(store, _munich_traits())

    def test_munich_trench_munich_light_identity(self):
        """The leak regression: a rainy trench scene between two
        Munich scenes must not change Munich's light."""
        store = ScopedState()
        store.begin_project("HITLER_EP01")
        store.begin_scene("SC01")
        munich1 = build_environment_scoped(store, _munich_traits())
        store.begin_scene("SC06")
        store.set(StateScope.SCENE, "weather", "Cold rain")
        trench = build_environment_scoped(store, _trench_traits())
        # Overcast and rain both resolve to the day/cold palette,
        # so the lights legitimately agree — what differs is the
        # archetype and the weather's provenance (SCENE vs trait).
        self.assertNotEqual(trench["archetype"], munich1["archetype"])
        self.assertEqual(trench["provenance"]["scoped_resolution"]
                         ["weather"], "SCENE")
        self.assertEqual(munich1["provenance"]["scoped_resolution"]
                         ["weather"], "trait")
        store.begin_scene("SC01")
        munich2 = build_environment_scoped(store, _munich_traits())
        self.assertEqual(munich2["light"], munich1["light"])
        self.assertEqual(munich2["archetype"], munich1["archetype"])

    def test_forge_point_light_absent_from_olympus(self):
        """Forge lighting must not affect Olympus: point lights
        travel with the per-scene package, never globally."""
        forge_traits = _location_traits(
            "zeus_ep01_fall_of_cronus.studio.md", "LOC_DIVINE_FORGE")
        olympus_traits = _location_traits(
            "zeus_ep01_fall_of_cronus.studio.md", "LOC_OLYMPUS")
        forge = build_environment(forge_traits, time_of_day="day")
        olympus = build_environment(olympus_traits, time_of_day="day")
        self.assertEqual(forge["archetype"], "FORGE")
        forge_light_ids = [pl["id"] for pl in forge["point_lights"]]
        self.assertIn("forge_mouth_glow", forge_light_ids)
        olympus_light_ids = [pl["id"] for pl in olympus["point_lights"]]
        self.assertNotIn("forge_mouth_glow", olympus_light_ids)

    def test_resolve_environment_attributes_read_only(self):
        store = ScopedState()
        store.begin_project("P1")
        store.begin_scene("SC01")
        store.set(StateScope.SCENE, "weather", "rain")
        resolved = resolve_environment_attributes(store)
        self.assertEqual(resolved["weather"],
                         {"value": "rain", "source": "SCENE"})
        self.assertEqual(resolved["rain"],
                         {"value": None, "source": None})
        self.assertEqual(store.resolve("weather"), "rain")


class TestScopedRainOverlay(unittest.TestCase):
    def test_overlay_deterministic_and_frame_animated(self):
        a = rain_overlay(SMALL, frame=0)
        b = rain_overlay(SMALL, frame=0)
        c = rain_overlay(SMALL, frame=1)
        self.assertEqual(a.tobytes(), b.tobytes())
        self.assertNotEqual(a.tobytes(), c.tobytes())
        self.assertEqual(a.mode, "RGBA")
        alphas = {px[3] for px in a.getdata()}
        self.assertIn(0, alphas)
        self.assertTrue(any(v > 0 for v in alphas))

    def test_render_with_scoped_rain_draws_streaks(self):
        store = ScopedState()
        store.begin_project("HITLER_EP01")
        store.begin_scene("SC06")
        store.set(StateScope.SCENE, "weather", "Cold rain")
        pkg = build_environment_scoped(store, _trench_traits())
        dry = render_environment(pkg, CAMERA, size=SMALL)
        wet = render_environment(pkg, CAMERA, size=SMALL,
                                 scoped_state=store, rain_frame=9)
        self.assertGreater(_diff_px(dry, wet), 100)

    def test_render_without_scoped_state_is_dry_and_stable(self):
        pkg = build_environment(_trench_traits(), time_of_day="day")
        a = render_environment(pkg, CAMERA, size=SMALL)
        b = render_environment(pkg, CAMERA, size=SMALL)
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_scoped_rain_false_overrides_rainy_weather(self):
        """A dry SHOT inside a rainy scene: explicit rain=False
        wins over the scene's rainy weather."""
        store = ScopedState()
        store.begin_project("HITLER_EP01")
        store.begin_scene("SC06")
        store.set(StateScope.SCENE, "weather", "Cold rain")
        store.begin_shot("SH01")
        store.set(StateScope.SHOT, "rain", False)
        pkg = build_environment_scoped(store, _trench_traits())
        dry = render_environment(pkg, CAMERA, size=SMALL)
        scoped = render_environment(pkg, CAMERA, size=SMALL,
                                    scoped_state=store, rain_frame=9)
        self.assertEqual(scoped.tobytes(), dry.tobytes())

    def test_overcast_draws_no_streaks(self):
        """Munich 'Overcast' dims the light (cold mood) but draws
        no rain streaks: overcast is not rain."""
        store = ScopedState()
        store.begin_project("HITLER_EP01")
        store.begin_scene("SC01")
        pkg = build_environment_scoped(store, _munich_traits())
        self.assertEqual(pkg["light"]["mood"], "cold")
        dry = render_environment(pkg, CAMERA, size=SMALL)
        scoped = render_environment(pkg, CAMERA, size=SMALL,
                                    scoped_state=store, rain_frame=9)
        self.assertEqual(scoped.tobytes(), dry.tobytes())

    def test_rain_isolation_across_scenes(self):
        """Render-level leak regression: Munich rendered after a
        rainy trench scene is byte-identical to Munich rendered
        before it, through one shared store."""
        store = ScopedState()
        store.begin_project("HITLER_EP01")
        store.begin_scene("SC01")
        munich_pkg = build_environment_scoped(store, _munich_traits())
        before = render_environment(munich_pkg, CAMERA, size=SMALL,
                                    scoped_state=store, rain_frame=9)
        store.begin_scene("SC06")
        store.set(StateScope.SCENE, "weather", "Cold rain")
        trench_pkg = build_environment_scoped(store, _trench_traits())
        wet = render_environment(trench_pkg, CAMERA, size=SMALL,
                                 scoped_state=store, rain_frame=9)
        self.assertGreater(_diff_px(
            render_environment(trench_pkg, CAMERA, size=SMALL), wet),
            100)
        store.begin_scene("SC01")
        munich_pkg2 = build_environment_scoped(store, _munich_traits())
        after = render_environment(munich_pkg2, CAMERA, size=SMALL,
                                   scoped_state=store, rain_frame=9)
        self.assertEqual(after.tobytes(), before.tobytes())


if __name__ == "__main__":
    unittest.main()
