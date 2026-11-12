"""Stage 3 engine tests: F9 camera + channel-study vocabulary (R1-R10).

F9: REAL per-shot viewpoint change executed in the render (per-shot
camera position/target, horizon/parallax shift, OTS/SRS staging),
camera FIXED within a shot, angle change BY CUT. F2: no head-size
pump across poses within a framing. Vocabulary: medium_close_up +
graphic_insert shot types, layered-depth staging, foreground
occlusion, split-screen, shot-level character view, map-board
frontal override.

Run: python3 -m unittest ai_clip_studio.tests.test_engine_stage3_camera
from ~/workspace/video-16x9-v2/
"""
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.camera_planner import (
    COMPOSITION_RULES, SHOT_FOCUS, SHOT_SCALE, SHOT_TYPES,
    CameraPlanner, resolve_viewpoint_angle, validate_framing,
    viewpoint_for_shot)
from ai_clip_studio.product_renderer import (
    CAM, CHAR_H, H, W, _normalize_character_view, _normalize_clock_time,
    _normalize_insert_card, _normalize_split_screen,
    _normalize_staging_mode, _render_graphic_card_image,
    _render_occlusion_layer, _render_shot, _split_composite,
    char_metrics, plan_shots)
from ai_clip_studio.renderer25d import render as render_mod
from ai_clip_studio.renderer25d.scene import Scene25D

FACE_FILL = (247, 243, 232)
TWO_CHAR_PACKAGE = {
    "characters": [
        {"name": "An", "description": "young woman",
         "template": "female", "voice_hint": "giọng nữ",
         "jacket_color": "#47BD75"},
        {"name": "Bình", "description": "young man",
         "template": "male", "voice_hint": "giọng nam",
         "jacket_color": "#2E5FA3"}],
    "scenes": [{
        "number": 1,
        "location": {"location_keyword": "street",
                     "setting": "day street corner",
                     "mood": "warm", "time_of_day": "day"},
        "setting": "day street corner",
        "action_text": "An và Bình trò chuyện.",
        "action_cues": [],
        "action_lead_sec": 0.0,
        "lines": [
            {"speaker": "An", "kind": "dialogue",
             "text": "Chào Bình, hôm nay trời đẹp quá."},
            {"speaker": "Bình", "kind": "dialogue",
             "text": "Ừ, mình đi dạo một vòng nhé."},
        ],
    }],
    "shot_directives": [],
    "props": [],
}


def _planned_shots(directives, cues=(), lead=0.0):
    import copy
    package = copy.deepcopy(TWO_CHAR_PACKAGE)
    package["shot_directives"] = directives
    package["scenes"][0]["action_cues"] = list(cues)
    package["scenes"][0]["action_lead_sec"] = lead
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 2.0}
                  for i in range(2)])
    for i, shot in enumerate(shots):
        shot["index"] = i
    return package, shots


def _render_still(package, shot):
    with tempfile.TemporaryDirectory() as tmp:
        rep = _render_shot({"shot": shot, "package": package,
                            "out_dir": tmp, "still_only": True})
        img = Image.open(rep["still"]).convert("RGB")
        img.load()
    return rep, img


def _face_fill_runs(arr, y_lo, y_hi):
    """Widest run of face-fill pixels per row band -> (width, cx).
    Used to measure head size / face position in a still."""
    band = (np.abs(arr[y_lo:y_hi].astype(int)
                   - np.array(FACE_FILL)).sum(axis=2) < 30)
    best_w, best_cx = 0, None
    for row in band:
        xs = np.where(row)[0]
        if len(xs) < 10:
            continue
        # widest contiguous run in this row
        splits = np.where(np.diff(xs) > 1)[0]
        starts = np.split(xs, splits + 1)
        for run in starts:
            if len(run) > best_w:
                best_w = len(run)
                best_cx = float(np.mean(run))
    return best_w, best_cx


class TestViewpointGeometry(unittest.TestCase):
    def test_default_medium_reproduces_legacy_camera(self):
        cam = viewpoint_for_shot("medium", None,
                                 subject_pos=(0.0, 1.2, 0.0))
        self.assertEqual(tuple(cam.position), (0.0, 2.0, 4.8))
        self.assertEqual(tuple(cam.target), (0.0, 1.2, 0.0))

    def test_viewpoint_sphere_radius_preserved(self):
        target = (0.5, 1.2, 0.0)
        for angle in ("eye_level", "low_angle", "high_angle",
                      "birds_eye"):
            cam = viewpoint_for_shot("medium", angle,
                                     subject_pos=target)
            dist = math.dist(cam.position, cam.target)
            self.assertAlmostEqual(dist, math.hypot(0.8, 4.8),
                                   places=2, msg=angle)
        cam = viewpoint_for_shot("establishing", None,
                                 subject_pos=target)
        self.assertAlmostEqual(math.dist(cam.position, cam.target),
                               7.5, places=2)

    def test_elevation_ordering(self):
        target = (0.0, 1.2, 0.0)
        ys = {}
        for angle in ("low_angle", "eye_level", "high_angle",
                      "birds_eye"):
            ys[angle] = viewpoint_for_shot(
                "medium", angle, subject_pos=target).position[1]
        self.assertLess(ys["low_angle"], ys["eye_level"])
        self.assertLess(ys["eye_level"], ys["high_angle"])
        self.assertLess(ys["high_angle"], ys["birds_eye"])

    def test_ots_azimuth_toward_counterpart(self):
        cam_r = viewpoint_for_shot(
            "over_the_shoulder", None, subject_pos=(0.0, 1.2, 0.0),
            counterpart_x=2.0)
        cam_l = viewpoint_for_shot(
            "over_the_shoulder", None, subject_pos=(0.0, 1.2, 0.0),
            counterpart_x=-2.0)
        self.assertGreater(cam_r.position[0], 0.0)
        self.assertLess(cam_l.position[0], 0.0)

    def test_srs_sides_mirror(self):
        target = (0.0, 1.2, 0.0)
        a = viewpoint_for_shot("shot_reverse_shot", None,
                               subject_pos=target, srs_side=0)
        b = viewpoint_for_shot("shot_reverse_shot", None,
                               subject_pos=target, srs_side=1)
        self.assertAlmostEqual(a.position[0], -b.position[0], places=6)
        self.assertNotAlmostEqual(a.position[0], 0.0)

    def test_resolve_viewpoint_angle(self):
        self.assertEqual(resolve_viewpoint_angle("establishing", None),
                         "eye_level")
        self.assertEqual(resolve_viewpoint_angle("establishing",
                                                 "high_angle"),
                         "high_angle")
        self.assertEqual(resolve_viewpoint_angle("medium", None),
                         "eye_level")
        self.assertEqual(resolve_viewpoint_angle("medium", "bogus"),
                         "eye_level")

    def test_horizon_shifts_with_elevation(self):
        scene = Scene25D(boxes=[], characters=[], camera=CAM,
                         sky_top=(135, 180, 220),
                         sky_bottom=(200, 220, 240),
                         ground_color=(96, 92, 84), ground_extent=30.0)
        low = viewpoint_for_shot("medium", "low_angle",
                                 subject_pos=(0.0, 1.2, 0.0))
        eye = viewpoint_for_shot("medium", "eye_level",
                                 subject_pos=(0.0, 1.2, 0.0))
        bird = viewpoint_for_shot("medium", "birds_eye",
                                  subject_pos=(0.0, 1.2, 0.0))
        h_low = render_mod._horizon_y(scene, low, W, H)
        h_eye = render_mod._horizon_y(scene, eye, W, H)
        h_bird = render_mod._horizon_y(scene, bird, W, H)
        self.assertGreater(h_low, h_eye)
        self.assertGreater(h_eye, h_bird)

    def test_char_metrics_no_pump_across_angles(self):
        heights = {}
        for angle in ("eye_level", "low_angle", "high_angle"):
            cam = viewpoint_for_shot("medium", angle,
                                     subject_pos=(0.0, 1.2, 0.0))
            heights[angle] = char_metrics(cam, 0.0)[2]
        self.assertEqual(heights["eye_level"], CHAR_H)
        for angle in ("low_angle", "high_angle"):
            self.assertLess(abs(heights[angle] - CHAR_H) / CHAR_H,
                            0.10, angle)


class TestFraming(unittest.TestCase):
    def test_framing_keeps_focus_when_subject_fits(self):
        # Regression: the old clamp parked every close-up subject at
        # the crop's left/top edge; the fit helper keeps the
        # requested focus when the need window fits.
        shot = {"shot_type": "close_up"}
        focus = (960.0, 540.0)
        subjects = [{"cx": 960.0, "head_y": 400.0, "foot_y": 650.0,
                     "half_w": 100.0}]
        _issues, corrected = validate_framing(shot, focus, subjects)
        self.assertEqual(corrected, focus)

    def test_framing_shifts_minimally_to_fit(self):
        shot = {"shot_type": "close_up"}
        subjects = [{"cx": 1700.0, "head_y": 340.0, "foot_y": 680.0,
                     "half_w": 150.0}]
        _issues, corrected = validate_framing(
            shot, (960.0, 540.0), subjects)
        # The need window [1550, 1850] fits in the crop (width
        # 1920/2.6 = 738) but not at the requested focus: the focus
        # must move right to the nearest fitting position.
        self.assertGreater(corrected[0], 960.0)


class TestRenderLevelCamera(unittest.TestCase):
    def test_f2_head_size_stable_across_poses(self):
        # Standing-box rule: a kneel medium shot must not pump the
        # head vs a standing medium shot (measured 225 vs 226 px).
        package, shots = _planned_shots([
            {"scene": 1, "line_index": 1, "shot_type": "medium",
             "camera_angle": "eye_level",
             "camera_movement": "STATIC"}])
        _rep, stand = _render_still(package, shots[0])
        w_stand, _ = _face_fill_runs(np.asarray(stand), 150, 450)
        package2, shots2 = _planned_shots([
            {"scene": 1, "line_index": 1, "shot_type": "medium",
             "camera_angle": "eye_level",
             "camera_movement": "STATIC"}],
            cues=("bend_pick",), lead=1.0)
        # The action-lead shot is the kneel shot.
        kneel_shot = shots2[0]
        self.assertIn("bend_pick", kneel_shot.get("action_cues") or [])
        _rep2, kneel = _render_still(package2, kneel_shot)
        w_kneel, _ = _face_fill_runs(np.asarray(kneel), 150, 650)
        self.assertGreater(w_stand, 150)
        self.assertLess(abs(w_kneel - w_stand) / w_stand, 0.05,
                        f"stand={w_stand} kneel={w_kneel}")

    def test_establishing_wide_heads_smaller_than_medium(self):
        package, shots = _planned_shots([
            {"scene": 1, "line_index": 1, "shot_type": "establishing",
             "camera_angle": None, "camera_movement": "STATIC"},
            {"scene": 1, "line_index": 2, "shot_type": "medium",
             "camera_angle": "eye_level",
             "camera_movement": "STATIC"}])
        _r1, wide = _render_still(package, shots[0])
        _r2, med = _render_still(package, shots[1])
        w_wide, _ = _face_fill_runs(np.asarray(wide), 150, 500)
        w_med, _ = _face_fill_runs(np.asarray(med), 150, 450)
        self.assertLess(w_wide, w_med,
                        f"wide={w_wide} medium={w_med}")

    def test_ots_listener_back_view_and_in_frame(self):
        package, shots = _planned_shots([
            {"scene": 1, "line_index": 1,
             "shot_type": "over_the_shoulder",
             "camera_angle": None, "camera_movement": "STATIC",
             "subject": "An", "counterpart": "Bình"}])
        rep, img = _render_still(package, shots[0])
        self.assertEqual(rep["shot_type"], "over_the_shoulder")
        arr = np.asarray(img).astype(int)
        # Listener head (right half): face fill present, but the
        # eye band must be nearly empty (back of head, no face).
        right = arr[100:500, 1100:1920]
        face = (np.abs(right - np.array(FACE_FILL)).sum(axis=2) < 30)
        self.assertGreater(int(face.sum()), 5000,
                           "listener head must be visible")
        # The listener head must fit inside the frame: face-fill
        # pixels must not touch the right edge.
        self.assertEqual(int(face[:, -5:].sum()), 0,
                         "listener head clipped at the right edge")

    def test_map_shot_renders_frontal_with_override_recorded(self):
        from ai_clip_studio.studio_script_v1 import (
            parse_studio_script_v1)
        from ai_clip_studio.studio_script_v1_adapter import (
            adapt_document)
        root = Path(__file__).resolve().parents[2]
        text = (root / "examples"
                / "hitler_ep01_munich_1914.studio.md").read_text(
                    encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(text))
        shots = plan_shots(
            package,
            [{"line_index": i + 1, "duration": 3.0} for i in range(9)])
        for i, shot in enumerate(shots):
            shot["index"] = i
        map_shot = next(s for s in shots if s.get("scene") == 2
                        and s.get("shot_type") == "establishing")
        self.assertEqual(map_shot.get("camera_angle"), "birds_eye")
        rep, _img = _render_still(package, map_shot)
        self.assertEqual(rep["camera_angle"], "eye_level")
        self.assertEqual(rep["camera_angle_requested"], "birds_eye")
        self.assertIn("map", (rep["camera_limitation"] or "").lower())


class TestChannelVocabulary(unittest.TestCase):
    def test_new_shot_types_registered(self):
        self.assertIn("medium_close_up", SHOT_TYPES)
        self.assertIn("graphic_insert", SHOT_TYPES)
        self.assertEqual(SHOT_SCALE["medium_close_up"], 1.6)
        self.assertEqual(SHOT_SCALE["graphic_insert"], 1.0)
        self.assertEqual(SHOT_FOCUS["medium_close_up"], "subject_head")
        self.assertEqual(SHOT_FOCUS["graphic_insert"], "full_frame")
        self.assertIn("chest_up", COMPOSITION_RULES["medium_close_up"])
        self.assertIn("flat_card", COMPOSITION_RULES["graphic_insert"])

    def test_normalizers_accept_valid_and_degrade_invalid(self):
        self.assertEqual(_normalize_staging_mode("layered_depth"),
                         "layered_depth")
        self.assertIsNone(_normalize_staging_mode("bogus"))
        self.assertIsNone(_normalize_staging_mode(None))
        self.assertEqual(_normalize_character_view("front"), "front")
        self.assertIsNone(_normalize_character_view("sideways"))
        self.assertEqual(_normalize_clock_time("03:10"), (3, 10))
        self.assertIsNone(_normalize_clock_time("25:99"))
        self.assertIsNone(_normalize_clock_time("noon"))
        card = _normalize_insert_card({
            "title": "Đếm ngược", "clock_time": "03:10",
            "tally_count": 3, "style": "dark", "bogus_key": 1})
        self.assertEqual(card["title"], "Đếm ngược")
        self.assertEqual(card["clock_time"], "03:10")
        self.assertEqual(card["tally_count"], 3)
        self.assertNotIn("bogus_key", card)
        self.assertEqual(_normalize_insert_card({"style": "neon"}),
                         {}, "invalid style is dropped, not defaulted")
        split = _normalize_split_screen({
            "left": {"expression": "neutral"},
            "right": {"expression": "worried"}})
        self.assertEqual(split["right"]["expression"], "worried")
        self.assertIsNone(_normalize_split_screen(
            {"left": {"expression": "bogus"}}))

    def test_plan_shots_carries_vocabulary_fields(self):
        package, shots = _planned_shots([
            {"scene": 1, "line_index": 1, "shot_type": "medium",
             "camera_angle": "eye_level",
             "camera_movement": "STATIC",
             "staging_mode": "layered_depth",
             "occluder_side": "right", "occluder_style": "blurred",
             "character_view": "front",
             "split_screen": {"left": {"expression": "neutral"},
                              "right": {"expression": "worried"}},
             "insert_card": {"title": "03:10", "clock_time": "03:10"}}])
        shot = shots[0]
        self.assertEqual(shot["staging_mode"], "layered_depth")
        self.assertEqual(shot["occluder_side"], "right")
        self.assertEqual(shot["occluder_style"], "blurred")
        self.assertEqual(shot["character_view"], "front")
        self.assertEqual(shot["split_screen"]["right"]["expression"],
                         "worried")
        self.assertEqual(shot["insert_card"]["clock_time"], "03:10")

    def test_graphic_card_renders_clock_and_tally(self):
        clock = _render_graphic_card_image({
            "shot_type": "graphic_insert",
            "insert_card": {"title": "Đồng hồ", "clock_time": "03:10",
                            "style": "paper"}})
        self.assertEqual(clock.size, (W, H))
        arr = np.asarray(clock.convert("RGB")).astype(int)
        # Clock zone (centre): dark ink pixels (face + hands).
        zone = arr[300:700, 700:1220]
        self.assertGreater(int((zone.sum(axis=2) < 200).sum()), 1000)
        tally = _render_graphic_card_image({
            "shot_type": "graphic_insert",
            "insert_card": {"title": "Đếm", "tally_count": 7,
                            "style": "dark"}})
        arr2 = np.asarray(tally.convert("RGB")).astype(int)
        zone2 = arr2[950:1070, 300:1620]
        self.assertGreater(int((zone2.sum(axis=2) > 500).sum()), 500)

    def test_occlusion_layer_and_split_composite(self):
        layer = _render_occlusion_layer("right", "blurred")
        self.assertEqual(layer.size, (W, H))
        alpha = np.asarray(layer)[:, :, 3]
        self.assertGreater(float((alpha[:, 1700:] > 100).mean()), 0.8)
        self.assertEqual(int((alpha[:, :500] > 0).sum()), 0)
        left = Image.new("RGB", (W, H), (200, 0, 0))
        right = Image.new("RGB", (W, H), (0, 0, 200))
        comp = _split_composite(left, right)
        arr = np.asarray(comp)
        self.assertTrue((arr[540, 100] == [200, 0, 0]).all())
        self.assertTrue((arr[540, 1800] == [0, 0, 200]).all())
        seam = arr[:, 958:962].astype(int)
        # Seam colour (20, 28, 36) sums to 84.
        self.assertGreater(float((seam.sum(axis=2) < 120).mean()), 0.5)

    def test_split_screen_still_has_both_viewports(self):
        package, shots = _planned_shots([
            {"scene": 1, "line_index": 1, "shot_type": "medium",
             "camera_angle": "eye_level",
             "camera_movement": "STATIC",
             "split_screen": {"left": {"expression": "neutral"},
                              "right": {"expression": "worried"}}}])
        _rep, img = _render_still(package, shots[0])
        arr = np.asarray(img).astype(int)
        face = (np.abs(arr - np.array(FACE_FILL)).sum(axis=2) < 30)
        self.assertGreater(int(face[:, :958].sum()), 1000)
        self.assertGreater(int(face[:, 962:].sum()), 1000)
        seam = arr[:, 958:962].astype(int)
        # Seam colour (20, 28, 36) sums to 84; subtitles may cover
        # the bottom rows of the seam.
        self.assertGreater(float((seam.sum(axis=2) < 120).mean()), 0.5)


if __name__ == "__main__":
    unittest.main()
