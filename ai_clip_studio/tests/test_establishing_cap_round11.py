"""Round 11 (R10-D1): an establishing shot must show the place AND
the sky. Loop-01 #1/#5 declare high_angle (32 deg), which pitches
the whole frustum below the horizon -- the delivered R10 frames
contain 0 px of sky, so the R10 sky dressing (clouds/hills) never
reaches the frame. The renderer caps the EXECUTED elevation of
establishing shots at ESTABLISHING_MAX_ELEV_DEG (15 deg: ~260 px
sky band, clouds fully in frame, still elevated) while recording
the requested angle. Other shot types are untouched.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

import ai_clip_studio.product_renderer as PR
from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.camera_planner import (
    ESTABLISHING_MAX_ELEV_DEG, elevation_for_angle, viewpoint_for_shot)
from ai_clip_studio.product_renderer import _fit_radius_scale, _render_shot
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parents[2]
JOB = AGENT / "jobs" / "req_f28d511157dc"


def _elevation(cam, target=(0.0, 1.2, 0.0)):
    dx = cam.position[0] - target[0]
    dy = cam.position[1] - target[1]
    dz = cam.position[2] - target[2]
    return math.degrees(math.atan2(dy, math.hypot(dx, dz)))


def _delivered_shots():
    text = (AGENT / "examples" / "loop_test_01_fire_stone.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    timeline = json.loads((JOB / "timeline.json").read_text(
        encoding="utf-8"))
    shots = timeline["shots"]
    starts = {}
    _t = 0.0
    for s in shots:
        starts[id(s)] = _t
        _t += float(s["duration"])
    spans = {}
    for s in shots:
        sid = s.get("directive_shot_id")
        if sid:
            st = starts[id(s)]
            en = st + float(s["duration"])
            if sid in spans:
                spans[sid][1] = max(spans[sid][1], en)
            else:
                spans[sid] = [st, en]
    events, unsupported = compile_actions(package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    out = []
    for i, s in enumerate(shots):
        shot = dict(s)
        shot["index"] = i
        shot["start_sec"] = starts[id(s)]
        out.append(shot)
    return package, out


class TestElevationOverride(unittest.TestCase):
    def test_none_uses_angle_table(self):
        cam = viewpoint_for_shot("medium", "high_angle",
                                 subject_pos=(0.0, 1.2, 0.0))
        self.assertAlmostEqual(_elevation(cam), 32.0, places=6)

    def test_override_equal_to_table_is_identical(self):
        a = viewpoint_for_shot("medium", "high_angle",
                               subject_pos=(0.0, 1.2, 0.0))
        b = viewpoint_for_shot("medium", "high_angle",
                               subject_pos=(0.0, 1.2, 0.0),
                               elevation_deg=32.0)
        self.assertEqual(a.position, b.position)
        self.assertEqual(a.target, b.target)

    def test_override_changes_elevation_only(self):
        target = (0.0, 1.2, 0.0)
        a = viewpoint_for_shot("establishing", "high_angle",
                               subject_pos=target)
        b = viewpoint_for_shot("establishing", "high_angle",
                               subject_pos=target, elevation_deg=15.0)
        self.assertAlmostEqual(_elevation(a), 32.0, places=6)
        self.assertAlmostEqual(_elevation(b), 15.0, places=6)
        ra = math.dist(a.position, target)
        rb = math.dist(b.position, target)
        self.assertAlmostEqual(ra, rb, places=6)
        self.assertAlmostEqual(a.position[0], b.position[0], places=6)

    def test_legacy_exact_preserved_without_override(self):
        cam = viewpoint_for_shot("medium", "eye_level",
                                 subject_pos=(0.0, 1.2, 0.0))
        self.assertEqual(tuple(cam.position), (0.0, 2.0, 4.8))

    def test_override_disables_legacy_branch(self):
        a = viewpoint_for_shot("medium", "eye_level",
                               subject_pos=(0.0, 1.2, 0.0))
        b = viewpoint_for_shot("medium", "eye_level",
                               subject_pos=(0.0, 1.2, 0.0),
                               elevation_deg=15.0)
        self.assertNotEqual(a.position, b.position)
        self.assertAlmostEqual(_elevation(b), 15.0, places=6)

    def test_non_finite_override_ignored(self):
        for bad in (float("nan"), float("inf"), float("-inf"), "high"):
            cam = viewpoint_for_shot("medium", "high_angle",
                                     subject_pos=(0.0, 1.2, 0.0),
                                     elevation_deg=bad)
            self.assertAlmostEqual(_elevation(cam), 32.0, places=6)

    def test_cap_value(self):
        self.assertEqual(ESTABLISHING_MAX_ELEV_DEG, 15.0)
        self.assertEqual(elevation_for_angle("high_angle"), 32.0)
        self.assertEqual(elevation_for_angle("birds_eye"), 62.0)


class TestFitThreading(unittest.TestCase):
    def test_fit_passes_elevation_to_viewpoint(self):
        seen = []
        real = PR.viewpoint_for_shot

        def _spy(*args, **kwargs):
            seen.append(kwargs.get("elevation_deg", "MISSING"))
            return real(*args, **kwargs)

        with mock.patch.object(PR, "viewpoint_for_shot", _spy):
            _fit_radius_scale("establishing", "high_angle", 0.0, 0.0,
                              None, 0, [(0.0, 0.0)], [1.0],
                              elevation_deg=15.0)
        self.assertTrue(seen)
        self.assertTrue(all(v == 15.0 for v in seen))

    def test_fit_default_passes_none(self):
        seen = []
        real = PR.viewpoint_for_shot

        def _spy(*args, **kwargs):
            seen.append(kwargs.get("elevation_deg", "MISSING"))
            return real(*args, **kwargs)

        with mock.patch.object(PR, "viewpoint_for_shot", _spy):
            _fit_radius_scale("medium", "eye_level", 0.0, 0.0,
                              None, 0, [(0.0, 0.0)], [1.0])
        self.assertTrue(seen)
        self.assertTrue(all(v is None for v in seen))


class TestEstablishingCapRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.shots = _delivered_shots()

    def _render_still(self, idx):
        out = tempfile.mkdtemp()
        rep = _render_shot({"shot": dict(self.shots[idx]),
                            "package": self.package,
                            "out_dir": out, "still_only": True})
        frames = sorted(Path(out).rglob("*.png"))
        return rep, frames

    @staticmethod
    def _sky_excess(frame_path):
        arr = np.asarray(Image.open(frame_path).convert("RGB")
                         ).astype(float)
        top = arr[:120].reshape(-1, 3).mean(axis=0)
        return float(top[2] - top[0])

    def test_establishing_high_angle_capped(self):
        rep, frames = self._render_still(1)
        self.assertEqual(rep["shot_type"], "establishing")
        self.assertEqual(rep["camera_angle_requested"], "high_angle")
        self.assertTrue(rep["camera_elevation_capped"])
        self.assertEqual(rep["camera_elevation_deg"], 15.0)
        self.assertEqual(rep["camera_elevation_requested_deg"], 32.0)
        self.assertIn("elevation cap", rep["camera_limitation"])
        cam_elev = _elevation(
            viewpoint_for_shot("establishing", "high_angle",
                               subject_pos=(0.0, 1.2, 0.0),
                               elevation_deg=rep["camera_elevation_deg"]))
        self.assertAlmostEqual(cam_elev, 15.0, places=6)
        self.assertTrue(frames)
        self.assertGreater(self._sky_excess(frames[0]), 10.0)

    def test_uncapped_control_has_no_sky(self):
        # The cap is what brings the sky: with the cap disabled the
        # same shot renders ground at the top of the frame.
        with mock.patch.object(PR, "ESTABLISHING_MAX_ELEV_DEG", 90.0):
            rep, frames = self._render_still(1)
        self.assertFalse(rep["camera_elevation_capped"])
        self.assertEqual(rep["camera_elevation_deg"], 32.0)
        self.assertTrue(frames)
        self.assertLessEqual(self._sky_excess(frames[0]), 10.0)

    def test_establishing_interior_capped(self):
        rep, _ = self._render_still(5)
        self.assertEqual(rep["shot_type"], "establishing")
        self.assertTrue(rep["camera_elevation_capped"])
        self.assertEqual(rep["camera_elevation_deg"], 15.0)

    def test_reaction_high_angle_untouched(self):
        rep, _ = self._render_still(2)
        self.assertEqual(rep["shot_type"], "reaction")
        self.assertFalse(rep["camera_elevation_capped"])
        self.assertEqual(rep["camera_elevation_deg"], 32.0)

    def test_establishing_eye_level_untouched(self):
        # Same shot with an eye-level angle: below the cap, so the
        # executed elevation is the table value and nothing is
        # recorded as capped.
        shot = dict(self.shots[1])
        shot["camera_angle"] = "eye_level"
        rep = _render_shot({"shot": shot, "package": self.package,
                            "out_dir": tempfile.mkdtemp(),
                            "still_only": True})
        self.assertFalse(rep["camera_elevation_capped"])
        self.assertAlmostEqual(
            rep["camera_elevation_deg"],
            elevation_for_angle("eye_level"), places=6)

    def test_establishing_birds_eye_exempt(self):
        # Round 14 (Loop-02 pre-render catch): an explicitly
        # requested birds_eye on an establishing shot is exempt
        # from the 15 deg cap -- the cap's sky rationale does
        # not apply to a deliberate top-down view, and no shot
        # type defaults to birds_eye, so the request is always
        # explicit. Executed elevation stays at the table 62.
        shot = dict(self.shots[1])
        shot["camera_angle"] = "birds_eye"
        rep = _render_shot({"shot": shot, "package": self.package,
                            "out_dir": tempfile.mkdtemp(),
                            "still_only": True})
        self.assertEqual(rep["shot_type"], "establishing")
        self.assertEqual(rep["camera_angle_requested"], "birds_eye")
        self.assertFalse(rep["camera_elevation_capped"])
        self.assertEqual(rep["camera_elevation_deg"], 62.0)
        self.assertEqual(rep["camera_elevation_requested_deg"], 62.0)

    def test_end_card_path_untouched(self):
        # Shot #16 is the end card: it returns an early minimal
        # report with no camera fields at all, before the camera
        # code runs. The cap must not disturb that path.
        rep, _ = self._render_still(16)
        self.assertEqual(rep["kind"], "end_card")
        self.assertEqual(rep["shot_type"], "establishing")
        self.assertNotIn("camera_elevation_capped", rep)
        self.assertNotIn("camera_position", rep)


if __name__ == "__main__":
    unittest.main()
