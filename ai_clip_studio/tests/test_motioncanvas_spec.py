"""Unit tests for ai_clip_studio.motioncanvas_spec (stdlib unittest).

Run from ~/workspace/video-16x9-v2/:
    python3 -m unittest ai_clip_studio.tests.test_motioncanvas_spec -v

The emitter is proven general on SYNTHETIC packages written here
(two distinct locations / casts / shot plans), never on one
particular script. The tests assert: example_spec.json conforms to
the emitter's schema; cameras change viewpoint per shot, hold fixed
within shots, and cut at boundaries; durations pass through from
the shot plan; renaming every character/location changes no
geometry; and the motioncanvas25d package scripts exist as the
README cites them.
"""

import copy
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_clip_studio import motioncanvas_spec as mc

MOTIONCANVAS_DIR = Path(__file__).resolve().parents[1] / "motioncanvas25d"


def _cast_entry(name, height_px=540, template="female"):
    return {
        "name": name,
        "id": f"CHAR_{name.upper()}",
        "identity_id": f"CHAR_{name.upper()}",
        "height_px": height_px,
        "template": template,
        "render_traits": {"template": template, "height_px": height_px},
    }


def _v1_location(location_id, *, features=(), foreground="", midground="",
                 background="", palette=(), time_of_day="day", mood="warm"):
    return {
        "location_id": location_id,
        "scene_numbers": [1],
        "name": f"place {location_id}",
        "period": "",
        "geography": "",
        "architecture": "",
        "features": list(features),
        "foreground": foreground,
        "midground": midground,
        "background": background,
        "lighting": "",
        "weather": "",
        "palette": list(palette),
        "forbidden": [],
        "render_traits": {"setting": "", "location_keyword": "street",
                          "mood": mood, "time_of_day": time_of_day},
    }


def _scene(number, *, setting, time_of_day, mood, v1_location, visible):
    return {
        "number": number,
        "scene_id": f"SC{number}",
        "title": "",
        "setting": setting,
        "location_text": "",
        "action_text": "",
        "action_cues": [],
        "action_lead_sec": 0.0,
        "lines": [],
        "location": {
            "location_keyword": "street",
            "setting": setting,
            "mood": mood,
            "time_of_day": time_of_day,
            "v1_location": v1_location,
        },
        "costume": "",
        "costume_garment": "none",
        "props": [],
        "visible_characters": list(visible),
        "v1_scene": {},
    }


def _shot(scene, *, kind="narration", speaker=None, shot_type="medium",
          camera_angle=None, camera_movement="STATIC", duration=3.0,
          ots_subject=None, ots_counterpart=None, srs_side=None,
          actor=None, staging_override=None, shot_id=None):
    entry = {
        "scene": scene, "kind": kind, "speaker": speaker, "text": "",
        "line_index": None, "duration": duration,
        "action_cues": [], "scene_cues": [],
        "actor": actor, "action_text": "",
        "visible": [], "shot_type": shot_type,
        "camera_movement": camera_movement, "camera_angle": camera_angle,
        "ots_subject": ots_subject, "ots_counterpart": ots_counterpart,
        "expression": None, "costume_overrides": {},
    }
    if srs_side is not None:
        entry["srs_side"] = srs_side
    if staging_override is not None:
        entry["staging_override"] = staging_override
    if shot_id is not None:
        entry["directive_shot_id"] = shot_id
    return entry


def _package_a():
    """Day/warm location, two adults, feature-rich layers + palette."""
    v1_loc = _v1_location(
        "LOC_A", features=["fountain", "market stall"],
        foreground="crates, barrels",
        midground="stall, awning pole",
        background="towers, wall",
        palette=["#aabbcc", "not-a-colour", "#112233"],
        time_of_day="day", mood="warm")
    return {
        "characters": [_cast_entry("Mara", 540, "female"),
                       _cast_entry("Theo", 560, "male")],
        "locations": ["harbour market"],
        "scenes": [_scene(1, setting="harbour market", time_of_day="day",
                          mood="warm", v1_location=v1_loc,
                          visible=["Mara", "Theo"])],
        "shots": [],
        "shot_directives": [],
        "trait_blocks": {"characters": [], "locations": [v1_loc]},
        "v1_snapshot_hash": "aabbccdd",
    }


def _shots_a():
    return [
        _shot(1, speaker="Mara", shot_type="establishing", duration=4.0),
        _shot(1, speaker="Theo", shot_type="medium", duration=3.5),
        _shot(1, speaker="Mara", shot_type="close_up",
              camera_movement="TRACKING", duration=2.5),
        _shot(1, speaker="Mara", shot_type="over_the_shoulder",
              ots_subject="Mara", ots_counterpart="Theo", duration=3.0),
    ]


def _package_b():
    """Night/cold location, adult + child, no feature data at all."""
    v1_loc = _v1_location("LOC_B", time_of_day="night", mood="cold")
    return {
        "characters": [_cast_entry("Nadia", 540, "female"),
                       _cast_entry("Pip", 540, "child")],
        "locations": ["cold yard"],
        "scenes": [_scene(1, setting="cold yard", time_of_day="night",
                          mood="cold", v1_location=v1_loc,
                          visible=["Nadia", "Pip"])],
        "shots": [],
        "shot_directives": [],
        "trait_blocks": {"characters": [], "locations": [v1_loc]},
        "v1_snapshot_hash": "11223344",
    }


def _shots_b():
    return [
        _shot(1, speaker="Nadia", shot_type="reaction", duration=2.0),
        _shot(1, speaker="Nadia", shot_type="shot_reverse_shot",
              srs_side=0, duration=2.0),
        _shot(1, speaker="Pip", shot_type="shot_reverse_shot",
              srs_side=1, duration=2.0),
        _shot(1, speaker="Nadia", shot_type="object_insert", duration=1.5),
    ]


def _distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


class TestExampleSpecConformance(unittest.TestCase):
    def test_example_spec_json_is_valid(self):
        spec = json.loads((MOTIONCANVAS_DIR / "example_spec.json").read_text())
        self.assertEqual(mc.validate_spec(spec), [])
        self.assertEqual(spec["duration_seconds"], 5)
        self.assertIn("world", spec)

    def test_example_spec_world_keys_all_consumed_by_schema(self):
        spec = json.loads((MOTIONCANVAS_DIR / "example_spec.json").read_text())
        world = spec["world"]
        for key in ("sky_top", "sky_bottom", "ground_color", "ground_size",
                    "boxes", "key_light", "ambient_sky", "ambient_ground",
                    "ambient_intensity", "camera_initial"):
            self.assertIn(key, world)


class TestSceneSpecs(unittest.TestCase):
    def test_day_warm_scene_uses_features_palette_and_no_night_lights(self):
        spec = mc.emit_scene_spec(_package_a(), 1, _shots_a())
        self.assertEqual(mc.validate_spec(spec), [])
        world = spec["world"]
        # 2 foreground + (2 midground + 2 features) + 2 background boxes.
        self.assertEqual(len(world["boxes"]), 8)
        colours = {b["color"] for b in world["boxes"]}
        self.assertIn("#aabbcc", colours)
        self.assertIn("#112233", colours)
        self.assertEqual(world["point_lights"], [])
        self.assertEqual(world["sky_top"], "#6fa8dc")
        anchors = {a["id"]: a for a in world["character_anchors"]}
        self.assertEqual(set(anchors), {"CHAR_MARA", "CHAR_THEO"})
        self.assertEqual(anchors["CHAR_MARA"]["feet"][1], 0.0)
        self.assertAlmostEqual(anchors["CHAR_MARA"]["height"], 1.7, places=2)
        self.assertGreater(anchors["CHAR_THEO"]["height"],
                           anchors["CHAR_MARA"]["height"])
        # Anchors spread symmetrically around x=0.
        self.assertAlmostEqual(anchors["CHAR_MARA"]["feet"][0], -0.8)
        self.assertAlmostEqual(anchors["CHAR_THEO"]["feet"][0], 0.8)
        # camera_initial matches the first keyframe pose.
        first = world["camera_keyframes"][0]
        self.assertEqual(world["camera_initial"]["position"], first["position"])
        self.assertEqual(world["camera_initial"]["target"], first["target"])

    def test_night_cold_scene_uses_default_world_and_lamp_lights(self):
        spec = mc.emit_scene_spec(_package_b(), 1, _shots_b())
        self.assertEqual(mc.validate_spec(spec), [])
        world = spec["world"]
        self.assertGreaterEqual(len(world["boxes"]), 3)
        self.assertEqual(len(world["point_lights"]), 2)
        self.assertEqual(world["sky_top"], "#0e1a33")
        self.assertIn("default world used",
                      " ".join(spec["meta"]["world_notes"]))
        anchors = {a["id"]: a for a in world["character_anchors"]}
        self.assertLess(anchors["CHAR_PIP"]["height"],
                        anchors["CHAR_NADIA"]["height"])
        self.assertAlmostEqual(anchors["CHAR_PIP"]["height"], 1.7 * 0.7,
                               places=2)

    def test_palette_invalid_entries_ignored(self):
        package = _package_a()
        v1_loc = package["scenes"][0]["location"]["v1_location"]
        v1_loc["palette"] = ["red", "#12", "", None, "#ABCDEF"]
        spec = mc.emit_scene_spec(package, 1, _shots_a())
        colours = {b["color"] for b in spec["world"]["boxes"]}
        self.assertEqual(colours, {"#abcdef"})
        for box in spec["world"]["boxes"]:
            self.assertRegex(box["color"], r"^#[0-9a-f]{3}([0-9a-f]{3})?$")

    def test_staging_override_moves_anchor(self):
        shots = _shots_a()
        shots[0]["staging_override"] = {"Theo": 1.6}
        spec = mc.emit_scene_spec(_package_a(), 1, shots)
        anchors = {a["id"]: a for a in spec["world"]["character_anchors"]}
        self.assertEqual(anchors["CHAR_THEO"]["feet"][0], 1.6)


class TestCameraKeyframes(unittest.TestCase):
    def test_fixed_within_shot_cut_at_boundaries(self):
        spec = mc.emit_scene_spec(_package_a(), 1, _shots_a())
        keys = spec["world"]["camera_keyframes"]
        self.assertEqual(len(keys), 8)  # 2 per shot x 4 shots
        for i in range(0, len(keys), 2):
            start, end = keys[i], keys[i + 1]
            self.assertEqual(start["position"], end["position"])
            self.assertEqual(start["target"], end["target"])
            self.assertEqual(start["fov"], end["fov"])
        self.assertFalse(keys[0]["cut"])
        for i in range(2, len(keys), 2):
            self.assertTrue(keys[i]["cut"])
            self.assertFalse(keys[i + 1]["cut"])
        # Times are scene-local and accumulate the shot durations.
        self.assertEqual([k["t"] for k in keys],
                         [0.0, 4.0, 4.0, 7.5, 7.5, 10.0, 10.0, 13.0])

    def test_viewpoint_changes_across_shots(self):
        spec = mc.emit_scene_spec(_package_a(), 1, _shots_a())
        keys = spec["world"]["camera_keyframes"]
        starts = [keys[i] for i in range(0, len(keys), 2)]
        poses = {(tuple(k["position"]), tuple(k["target"])) for k in starts}
        self.assertEqual(len(poses), 4)

    def test_fov_constant_and_radii_by_shot_type(self):
        spec = mc.emit_scene_spec(_package_a(), 1, _shots_a())
        keys = spec["world"]["camera_keyframes"]
        for key in keys:
            self.assertEqual(key["fov"], 46.0)
        starts = [keys[i] for i in range(0, len(keys), 2)]
        distances = [_distance(k["position"], k["target"]) for k in starts]
        establishing, medium, close_up, ots = distances
        self.assertAlmostEqual(establishing, 7.5, places=2)
        self.assertAlmostEqual(medium, math.sqrt(0.8 ** 2 + 4.8 ** 2),
                               places=2)
        self.assertAlmostEqual(close_up, 2.9, places=2)
        self.assertLess(close_up, medium)
        self.assertAlmostEqual(ots, medium, places=2)

    def test_ots_camera_sits_on_counterpart_side(self):
        spec = mc.emit_scene_spec(_package_a(), 1, _shots_a())
        keys = spec["world"]["camera_keyframes"]
        ots = keys[6]  # fourth shot
        # Subject Mara is at x=-0.8, counterpart Theo at x=+0.8: the
        # camera must sit on Theo's (+x) side of the subject.
        self.assertGreater(ots["position"][0], ots["target"][0])

    def test_reverse_shots_alternate_azimuth(self):
        spec = mc.emit_scene_spec(_package_b(), 1, _shots_b())
        keys = spec["world"]["camera_keyframes"]
        srs0, srs1 = keys[2], keys[4]
        dx0 = srs0["position"][0] - srs0["target"][0]
        dx1 = srs1["position"][0] - srs1["target"][0]
        self.assertLess(dx0, 0.0)
        self.assertGreater(dx1, 0.0)

    def test_movement_label_preserved_but_pose_fixed(self):
        spec = mc.emit_scene_spec(_package_a(), 1, _shots_a())
        provenance = spec["shots"][2]
        self.assertEqual(provenance["camera_movement"], "TRACKING")
        keys = spec["world"]["camera_keyframes"]
        self.assertEqual(keys[4]["position"], keys[5]["position"])
        self.assertEqual(keys[4]["target"], keys[5]["target"])

    def test_explicit_angle_wins_over_shot_default(self):
        shots = [_shot(1, speaker="Mara", shot_type="medium",
                       camera_angle="low_angle", duration=2.0)]
        spec = mc.emit_scene_spec(_package_a(), 1, shots)
        key = spec["world"]["camera_keyframes"][0]
        # Low angle: camera below the target height, looking up.
        self.assertLess(key["position"][1], key["target"][1])
        self.assertEqual(spec["shots"][0]["camera_angle"], "low_angle")


class TestDurations(unittest.TestCase):
    def test_scene_duration_is_shot_plan_sum(self):
        spec = mc.emit_scene_spec(_package_a(), 1, _shots_a())
        self.assertEqual(spec["duration_seconds"], 13.0)
        self.assertEqual(spec["end_sec"], 13.0)
        self.assertNotEqual(spec["duration_seconds"], 15.0)

    def test_job_spec_groups_scenes_and_offsets(self):
        package = _package_a()
        package["scenes"].append(_scene(
            2, setting="harbour market", time_of_day="day", mood="warm",
            v1_location=package["scenes"][0]["location"]["v1_location"],
            visible=["Mara"]))
        shots = _shots_a() + [
            _shot(2, speaker="Mara", shot_type="medium", duration=24.5)]
        job = mc.emit_job_spec(package, shots, 37.5)
        self.assertEqual(mc.validate_job_spec(job), [])
        self.assertEqual(job["duration_seconds"], 37.5)
        self.assertEqual(len(job["scene_specs"]), 2)
        self.assertEqual(job["scene_specs"][0]["start_sec"], 0.0)
        self.assertEqual(job["scene_specs"][1]["start_sec"], 13.0)
        self.assertEqual(job["scene_specs"][1]["end_sec"], 37.5)
        self.assertEqual(job["meta"]["notes"], [])

    def test_job_spec_records_timeline_mismatch_without_rescaling(self):
        job = mc.emit_job_spec(_package_a(), _shots_a(), 99.0)
        self.assertEqual(job["duration_seconds"], 13.0)
        self.assertEqual(len(job["meta"]["notes"]), 1)
        self.assertIn("differs from", job["meta"]["notes"][0])

    def test_job_spec_notes_shotless_scene(self):
        package = _package_a()
        package["scenes"].append(_scene(
            2, setting="elsewhere", time_of_day="day", mood="warm",
            v1_location=None, visible=[]))
        job = mc.emit_job_spec(package, _shots_a(), 13.0)
        self.assertEqual(len(job["scene_specs"]), 1)
        self.assertIn("scene 2", job["meta"]["notes"][0])


class TestGenerality(unittest.TestCase):
    def test_renaming_everything_changes_no_geometry(self):
        package = _package_a()
        renamed = copy.deepcopy(package)
        rename = {"Mara": "Zed", "Theo": "Yara"}
        for entry in renamed["characters"]:
            old_name = entry["name"]
            entry["name"] = rename[old_name]
            entry["id"] = f"CHAR_{rename[old_name].upper()}"
            entry["identity_id"] = entry["id"]
        renamed["scenes"][0]["visible_characters"] = ["Zed", "Yara"]
        renamed["scenes"][0]["setting"] = "a different place entirely"
        renamed["scenes"][0]["location"]["setting"] = "a different place"
        renamed["locations"] = ["a different place entirely"]
        shots = _shots_a()
        renamed_shots = copy.deepcopy(shots)
        for shot in renamed_shots:
            if shot.get("speaker") in rename:
                shot["speaker"] = rename[shot["speaker"]]
            if shot.get("ots_subject") in rename:
                shot["ots_subject"] = rename[shot["ots_subject"]]
            if shot.get("ots_counterpart") in rename:
                shot["ots_counterpart"] = rename[shot["ots_counterpart"]]
        spec_a = mc.emit_scene_spec(package, 1, shots)
        spec_b = mc.emit_scene_spec(renamed, 1, renamed_shots)
        world_a, world_b = spec_a["world"], spec_b["world"]
        self.assertEqual(world_a["boxes"], world_b["boxes"])
        self.assertEqual(world_a["key_light"], world_b["key_light"])
        self.assertEqual(world_a["camera_keyframes"],
                         world_b["camera_keyframes"])
        feet_a = [a["feet"] for a in world_a["character_anchors"]]
        feet_b = [a["feet"] for a in world_b["character_anchors"]]
        self.assertEqual(feet_a, feet_b)
        heights_a = [a["height"] for a in world_a["character_anchors"]]
        heights_b = [a["height"] for a in world_b["character_anchors"]]
        self.assertEqual(heights_a, heights_b)


class TestValidationAndErrors(unittest.TestCase):
    def test_validate_rejects_missing_keys_bad_colours_bad_times(self):
        spec = json.loads((MOTIONCANVAS_DIR / "example_spec.json").read_text())
        broken = copy.deepcopy(spec)
        del broken["world"]["ground_color"]
        self.assertTrue(any("ground_color" in e
                            for e in mc.validate_spec(broken)))
        broken = copy.deepcopy(spec)
        broken["world"]["sky_top"] = "blue"
        self.assertTrue(any("sky_top" in e
                            for e in mc.validate_spec(broken)))
        broken = copy.deepcopy(spec)
        broken["world"]["camera_keyframes"][1]["t"] = -1
        self.assertTrue(any("non-decreasing" in e
                            for e in mc.validate_spec(broken)))
        broken = copy.deepcopy(spec)
        broken["duration_seconds"] = 0
        self.assertTrue(any("duration_seconds" in e
                            for e in mc.validate_spec(broken)))
        self.assertIn("expected a dict", mc.validate_spec([])[0])
        self.assertIn("spec_version", mc.validate_job_spec({})[0])

    def test_emitter_rejects_bad_durations(self):
        for bad in (None, 0, -2.0, "long"):
            with self.subTest(bad=bad):
                shots = [_shot(1, speaker="Mara", duration=bad)]
                with self.assertRaises(mc.MotionCanvasSpecError):
                    mc.emit_scene_spec(_package_a(), 1, shots)

    def test_emitter_rejects_empty_shots_and_unknown_scene(self):
        with self.assertRaises(mc.MotionCanvasSpecError):
            mc.emit_scene_spec(_package_a(), 1, [])
        with self.assertRaises(mc.MotionCanvasSpecError):
            mc.emit_scene_spec(_package_a(), 99, _shots_a())
        with self.assertRaises(mc.MotionCanvasSpecError):
            mc.emit_job_spec({"characters": [], "scenes": []}, [], 1.0)


class TestPackageScripts(unittest.TestCase):
    def test_package_json_scripts_exist_as_readme_cites(self):
        package_json = json.loads(
            (MOTIONCANVAS_DIR / "package.json").read_text())
        scripts = package_json["scripts"]
        for name in ("install-deps", "build-world", "render-smoke"):
            self.assertIn(name, scripts)
        readme = (MOTIONCANVAS_DIR / "README_WINDOWS.md").read_text()
        self.assertIn("build-world", readme)
        self.assertIn("render-smoke", readme)

    def test_package_json_lists_every_runtime_dependency(self):
        package_json = json.loads(
            (MOTIONCANVAS_DIR / "package.json").read_text())
        deps = package_json["dependencies"]
        for name in ("three", "@motion-canvas/2d", "@motion-canvas/core",
                     "puppeteer-core"):
            self.assertIn(name, deps)
        self.assertIn("esbuild", package_json["devDependencies"])


class TestCameraPlannerSync(unittest.TestCase):
    def test_viewpoint_matches_executed_f9_geometry(self):
        from ai_clip_studio.camera_planner import viewpoint_for_shot
        package = _package_a()
        anchors = mc.build_character_anchors(
            package["scenes"][0],
            {c["name"]: c for c in package["characters"]}, _shots_a())
        cast = {c["name"]: c for c in package["characters"]}
        # Medium eye-level: identical pose to the executed geometry.
        shot = _shot(1, speaker="Mara", shot_type="medium", duration=2.0)
        pose = mc.camera_pose_for_shot(shot, anchors, cast)
        expected = viewpoint_for_shot(
            "medium", None, subject_pos=(-0.8, 1.2, 0.0))
        for got, want in zip(pose["position"], expected.position):
            self.assertAlmostEqual(got, want, places=3)
        self.assertEqual(pose["target"], [round(v, 3) for v in expected.target])
        # Establishing: same wide radius, eye level.
        shot = _shot(1, speaker="Mara", shot_type="establishing",
                     duration=2.0)
        pose = mc.camera_pose_for_shot(shot, anchors, cast)
        expected = viewpoint_for_shot(
            "establishing", None, subject_pos=(-0.8, 1.2, 0.0))
        self.assertAlmostEqual(
            _distance(pose["position"], pose["target"]),
            _distance(expected.position, expected.target), places=2)
        # Over-the-shoulder: same 28-degree azimuth side rule.
        shot = _shot(1, shot_type="over_the_shoulder", ots_subject="Mara",
                     ots_counterpart="Theo", duration=2.0)
        pose = mc.camera_pose_for_shot(shot, anchors, cast)
        expected = viewpoint_for_shot(
            "over_the_shoulder", None, subject_pos=(-0.8, 1.2, 0.0),
            counterpart_x=0.8)
        for got, want in zip(pose["position"], expected.position):
            self.assertAlmostEqual(got, want, places=3)


if __name__ == "__main__":
    unittest.main()
