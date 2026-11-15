"""FG clearance (round-3 system 2): the frustum fit is
azimuth-blind -- under an OTS camera a fitted FG rock projects
center-frame and covers the cast (Loop 01 cave shots: two giant
blurred rocks, no characters). The clearance pass projects each
FG element with the shot camera and shifts conflicting elements
outward until the subjects' standing boxes are clear."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.environment_v2 import (
    build_environment, clear_foreground_from_subjects,
    fit_foreground_to_frustum, validate_fg_composition)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _cave_traits():
    return {"id": "LOC_CAVE", "name": "Cave of Rhea",
            "features": ["Hang động.", "Đuốc.", "Thạch nhũ."],
            "period": "mythic"}


def _standing_box(cam, x=0.0, z=0.0):
    pts = [cam.project((cx, cy, z), 1920, 1080)[:2]
           for cx in (x - 0.4, x + 0.4) for cy in (0.0, 1.8)]
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def _ots_camera():
    # The Loop 01 SC03_SH01 viewpoint: subject Linh at (-1.6, 0.5),
    # counterpart (Ông Ba) to the right, azimuth 28 deg.
    return viewpoint_for_shot(
        "over_the_shoulder", None, subject_pos=(-1.6, 1.2, 0.5),
        counterpart_x=1.6)


class TestFgClearance(unittest.TestCase):
    def test_fit_alone_blocks_the_cast_under_ots(self):
        # Reproduces the defect at the validation level: the fit
        # leaves an FG element overlapping the standing box.
        env = build_environment(_cave_traits(), time_of_day="day")
        cam = _ots_camera()
        fit = fit_foreground_to_frustum(env, cam, size=(1920, 1080))
        res = validate_fg_composition(
            fit, cam, size=(1920, 1080),
            subject_boxes=[_standing_box(cam, x=-1.6, z=0.5)])
        self.assertFalse(res["ok"], res["errors"])

    def test_clearance_restores_a_valid_composition(self):
        env = build_environment(_cave_traits(), time_of_day="day")
        cam = _ots_camera()
        fit = fit_foreground_to_frustum(env, cam, size=(1920, 1080))
        cleared = clear_foreground_from_subjects(
            fit, cam, size=(1920, 1080),
            subject_boxes=[_standing_box(cam, x=-1.6, z=0.5)])
        res = validate_fg_composition(
            cleared, cam, size=(1920, 1080),
            subject_boxes=[_standing_box(cam, x=-1.6, z=0.5)])
        self.assertTrue(res["ok"], res["errors"])
        for el in res["elements"]:
            self.assertFalse(el["overlaps_standing_box"], el)
            self.assertLess(el["area_fraction"], 0.40)

    def test_clear_elements_are_untouched(self):
        env = build_environment(_cave_traits(), time_of_day="day")
        cam = viewpoint_for_shot("medium", "eye_level",
                                 subject_pos=(0.0, 1.2, 0.0))
        fit = fit_foreground_to_frustum(env, cam, size=(1920, 1080))
        cleared = clear_foreground_from_subjects(
            fit, cam, size=(1920, 1080),
            subject_boxes=[_standing_box(cam)])
        prov = cleared["provenance"]["fg_clearance"]
        self.assertEqual(prov["moved_count"], 0)
        self.assertEqual(
            [e["center"] for e in cleared["elements"]],
            [e["center"] for e in fit["elements"]])

    def test_input_package_is_not_mutated(self):
        env = build_environment(_cave_traits(), time_of_day="day")
        cam = _ots_camera()
        fit = fit_foreground_to_frustum(env, cam, size=(1920, 1080))
        before = [e["center"] for e in fit["elements"]]
        clear_foreground_from_subjects(
            fit, cam, size=(1920, 1080),
            subject_boxes=[_standing_box(cam, x=-1.6, z=0.5)])
        self.assertEqual([e["center"] for e in fit["elements"]], before)

    def test_grouped_elements_move_together(self):
        # A lamp pole + head share (x, z): the clearance must move
        # the assembly as one, never detach the head from the pole.
        pkg = {"elements": [
            {"id": "pole", "kind": "pole", "layer": "FG",
             "center": (0.0, 1.0, 1.6), "size": (0.3, 2.0, 0.3),
             "color": (60, 60, 60), "material": "iron"},
            {"id": "head", "kind": "lamp_head", "layer": "FG",
             "center": (0.0, 2.2, 1.6), "size": (0.5, 0.4, 0.5),
             "color": (255, 220, 140), "material": "glass"},
        ]}
        cam = viewpoint_for_shot("medium", "eye_level",
                                 subject_pos=(0.0, 1.2, 0.0))
        cleared = clear_foreground_from_subjects(
            pkg, cam, size=(1920, 1080),
            subject_boxes=[_standing_box(cam)])
        els = {e["id"]: e for e in cleared["elements"]}
        self.assertEqual(els["pole"]["center"][0],
                         els["head"]["center"][0])
        self.assertNotEqual(els["pole"]["center"][0], 0.0)

    def test_unclearable_element_uses_full_budget_recorded(self):
        # A wall-wide FG element cannot clear the standing box by
        # shifting: the pass must spend its whole step budget and
        # record the outcome honestly (still in frame, best
        # effort) -- never pretend it cleared, never loop forever.
        pkg = {"elements": [
            {"id": "wall", "kind": "wall", "layer": "FG",
             "center": (0.0, 1.8, 1.6), "size": (30.0, 3.6, 0.5),
             "color": (60, 60, 60), "material": "rock"},
        ]}
        cam = viewpoint_for_shot("medium", "eye_level",
                                 subject_pos=(0.0, 1.2, 0.0))
        cleared = clear_foreground_from_subjects(
            pkg, cam, size=(1920, 1080),
            subject_boxes=[_standing_box(cam)], max_steps=24)
        prov = cleared["provenance"]["fg_clearance"]
        self.assertEqual(prov["moved_count"], 1)
        move = prov["moved"][0]
        self.assertEqual(move["steps"], 24)
        self.assertAlmostEqual(move["to_x"] - move["from_x"], 6.0)
        self.assertFalse(move["off_frame"])


class TestFgClearanceProductPath(unittest.TestCase):
    def test_ots_shot_renders_the_cast_visible(self):
        from ai_clip_studio.action_compiler import compile_actions
        from ai_clip_studio.product_renderer import (
            _render_shot, plan_shots)
        from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
        from ai_clip_studio.studio_script_v1_adapter import adapt_document
        text = (EXAMPLES / "loop_test_01_fire_stone.studio.md"
                ).read_text(encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(text))
        shots = plan_shots(
            package, [{"line_index": i + 1, "duration": 3.0}
                      for i in range(7)])
        for i, s in enumerate(shots):
            s["index"] = i
        spans = {}
        clock = 0.0
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
            "spans_supplied": True, "compile_error": None,
        }
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC03_SH01")
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot({"shot": shot, "package": package,
                                   "out_dir": tmp})
            frames = sorted(Path(tmp).rglob("*.png"))
            mid = Image.open(frames[len(frames) // 2]).convert("RGB")
        clearance = result["fg_clearance"]
        self.assertGreater(clearance["moved_count"], 0)
        # Linh's standing box must contain her light face, not
        # uniform dark rock: before the fix the box was ~0% light.
        linh = next(b for b in result["character_boxes"]
                    if b["name"] == "Linh")
        x0, y0, x1, y1 = [int(v) for v in linh["bbox"]]
        box = mid.crop((max(x0, 0), max(y0, 0),
                        min(x1, 1920), min(y1, 1080)))
        px = list(box.getdata())
        light = sum(1 for r, g, b in px
                    if r > 180 and g > 180 and b > 180)
        self.assertGreater(light / len(px), 0.03)


if __name__ == "__main__":
    unittest.main()


def _frontal_camera():
    return viewpoint_for_shot("medium", "eye_level",
                              subject_pos=(0.0, 1.2, 0.0))


def _fg_package(elements):
    return {"archetype": "TEST", "elements": elements,
            "provenance": {}}


def _fg_box(el_id, center, size):
    return {"id": el_id, "kind": "column", "layer": "FG",
            "geometry": "box", "center": center, "size": size,
            "color": (120, 110, 100), "material": "stone",
            "attachment": None, "label": "", "extra": {}}


class TestFgVisibleWindowRound6(unittest.TestCase):
    """Round 6: FG fit/clearance target the VISIBLE window (the
    frozen crop rect), keep occluders out of the inter-subject
    gap corridor, and cap one element at 25% of the visible
    window."""

    def test_fit_targets_the_crop_rect_not_the_full_frame(self):
        cam = _frontal_camera()
        pkg = _fg_package([_fg_box("col", (2.0, 1.0, 2.0),
                                   (0.6, 1.8, 0.4))])
        # In-frame for the full frame: legacy fit leaves it.
        legacy = fit_foreground_to_frustum(pkg, cam,
                                           size=(1920, 1080))
        self.assertEqual(legacy["elements"][0]["center"],
                         (2.0, 1.0, 2.0))
        # Outside the left-half crop rect: the rect-aware fit
        # pulls it to the rect's right edge.
        rect = [0.0, 0.0, 960.0, 1080.0]
        fitted = fit_foreground_to_frustum(
            pkg, cam, size=(1920, 1080), visible_rect=rect)
        moved = fitted["elements"][0]["center"]
        self.assertLess(moved[0], 2.0)
        px, _, _, vis = cam.project(moved, 1920, 1080)
        self.assertTrue(vis)
        self.assertLess(px, 960.0)
        self.assertEqual(fitted["provenance"]["fg_fit"]
                         ["visible_rect"], rect)

    def test_clearance_keeps_fg_out_of_the_subject_gap(self):
        cam = _frontal_camera()
        # Two subjects with a 400 px gap between their boxes.
        left = (400.0, 200.0, 700.0, 900.0)
        right = (1100.0, 200.0, 1400.0, 900.0)
        # An FG column projecting into the gap's upper half.
        pkg = _fg_package([_fg_box("col", (0.0, 1.0, 2.0),
                                   (0.6, 1.8, 0.4))])
        cleared = clear_foreground_from_subjects(
            pkg, cam, size=(1920, 1080),
            subject_boxes=[left, right])
        prov = cleared["provenance"]["fg_clearance"]
        self.assertEqual(prov["gap_boxes"], 1)
        self.assertGreater(prov["moved_count"], 0)
        # The moved element no longer intersects the gap band
        # (x 700..1100, upper half y 200..550).
        el = cleared["elements"][0]
        cx, cy, cz = (float(v) for v in el["center"])
        sx, sy = el["size"][0] / 2, el["size"][1] / 2
        pts = [cam.project((cx + dx, cy + dy, cz), 1920, 1080)[:2]
               for dx in (-sx, sx) for dy in (-sy, sy)]
        x0 = min(q[0] for q in pts)
        x1 = max(q[0] for q in pts)
        y0 = min(q[1] for q in pts)
        self.assertTrue(x1 <= 700.0 or x0 >= 1100.0 or y0 >= 550.0,
                        f"FG still in the gap band: x {x0:.0f}..{x1:.0f}")

    def test_clearance_caps_one_element_at_25_percent(self):
        cam = _frontal_camera()
        # A wide FG slab covering ~30% of the frame, no subjects:
        # only the area rule applies, and it must move.
        pkg = _fg_package([_fg_box("slab", (0.0, 1.0, 2.0),
                                   (4.0, 1.8, 0.4))])
        cleared = clear_foreground_from_subjects(
            pkg, cam, size=(1920, 1080), subject_boxes=[])
        prov = cleared["provenance"]["fg_clearance"]
        self.assertEqual(prov["max_visible_fraction"], 0.25)
        self.assertGreater(prov["moved_count"], 0)
        el = cleared["elements"][0]
        cx, cy, cz = (float(v) for v in el["center"])
        sx, sy = el["size"][0] / 2, el["size"][1] / 2
        pts = [cam.project((cx + dx, cy + dy, cz), 1920, 1080)[:2]
               for dx in (-sx, sx) for dy in (-sy, sy)]
        ix0 = max(min(q[0] for q in pts), 0.0)
        ix1 = min(max(q[0] for q in pts), 1920.0)
        iy0 = max(min(q[1] for q in pts), 0.0)
        iy1 = min(max(q[1] for q in pts), 1080.0)
        frac = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0) / (1920 * 1080)
        self.assertLessEqual(frac, 0.25)
