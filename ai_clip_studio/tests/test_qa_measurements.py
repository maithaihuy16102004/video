"""Phase F measurement tests: rig-landmark boxes, pixel silhouette
IoU, and camera coverage. Fixtures use KNOWN dimensions — a box
measurement is only trusted when it reproduces an exact answer on
exact input."""

import unittest

from ai_clip_studio.qa_measurements import (
    SILHOUETTE_IOU_MAX,
    camera_coverage_report,
    character_height,
    costume_box,
    full_character_box,
    hair_box,
    head_box,
    head_ratio,
    measure_character,
    pairwise_silhouette_report,
    silhouette_iou,
    silhouette_mask,
)


def _joints(head=(100.0, 155.0), foot_y=620.0):
    return {
        "head": head, "neck": (100.0, 200.0),
        "shoulder": (100.0, 210.0), "hip": (100.0, 400.0),
        "knee_l": (85.0, 510.0), "knee_r": (115.0, 510.0),
        "foot_l": (80.0, foot_y), "foot_r": (120.0, foot_y),
        "elbow_l": (60.0, 300.0), "elbow_r": (140.0, 300.0),
        "hand_l": (50.0, 390.0), "hand_r": (150.0, 390.0),
        "facing": 1,
    }


class TestRigBoxes(unittest.TestCase):
    def test_head_box_is_exactly_the_circle(self):
        box = head_box((100.0, 100.0), 50.0)
        self.assertEqual(box["kind"], "head")
        self.assertEqual((box["x0"], box["y0"], box["x1"], box["y1"]),
                         (50.0, 50.0, 150.0, 150.0))
        self.assertEqual(box["width"], 100.0)
        self.assertEqual(box["height"], 100.0)
        self.assertEqual(box["source"], "rig")

    def test_hair_box_extents(self):
        base = hair_box((100.0, 100.0), 50.0, hair_style="short")
        self.assertEqual((base["x0"], base["y0"], base["x1"], base["y1"]),
                         (50.0, 50.0, 150.0, 150.0))
        long_h = hair_box((100.0, 100.0), 50.0, hair_style="long")
        self.assertEqual(long_h["y1"], 100.0 + 1.73 * 50.0)
        self.assertEqual(long_h["x0"], 100.0 - 1.08 * 50.0)
        tuft = hair_box((100.0, 100.0), 50.0, hair_style="tuft")
        self.assertEqual(tuft["y0"], 100.0 - 1.22 * 50.0)
        hat = hair_box((100.0, 100.0), 50.0, hair_style="short",
                       hat="bowler")
        self.assertEqual(hat["y0"], 100.0 - 1.75 * 50.0)
        self.assertEqual(hat["x0"], 100.0 - 1.15 * 50.0)
        unknown = hair_box((100.0, 100.0), 50.0,
                           hair_style="mohawk")
        self.assertEqual((unknown["x0"], unknown["y0"]),
                         (50.0, 50.0))
        self.assertTrue(any("unknown hair style" in n
                            for n in unknown["notes"]))

    def test_costume_box_excludes_head(self):
        joints = _joints()
        joints["head"] = (1000.0, -500.0)  # far away: must not matter
        box = costume_box(joints, 10.0)
        self.assertEqual(box["kind"], "costume")
        self.assertEqual((box["x0"], box["y0"], box["x1"], box["y1"]),
                         (40.0, 200.0, 160.0, 630.0))
        with self.assertRaises(ValueError):
            costume_box({}, 10.0)

    def test_full_box_is_the_union(self):
        joints = _joints()
        box = full_character_box(joints, (100.0, 155.0), 95.0,
                                 hair_style="short", hat="bowler",
                                 margin_px=10.0)
        self.assertEqual(box["kind"], "full_character")
        # Top = hat crown (155 - 1.75*95); bottom = feet + margin.
        self.assertAlmostEqual(box["y0"], 155.0 - 1.75 * 95.0)
        self.assertEqual(box["y1"], 630.0)

    def test_character_height_and_ratio_on_fixture(self):
        joints = _joints(head=(100.0, 155.0), foot_y=620.0)
        height = character_height(joints, (100.0, 155.0), 95.0)
        self.assertEqual(height, 620.0 - (155.0 - 95.0))
        ratio = head_ratio(head_box((100.0, 155.0), 95.0), height)
        self.assertAlmostEqual(ratio, 190.0 / 560.0)
        with self.assertRaises(ValueError):
            head_ratio(hair_box((100.0, 155.0), 95.0,
                                hat="bowler"), height)

    def test_degenerate_inputs_raise(self):
        with self.assertRaises(ValueError):
            head_box((100.0, 100.0), 0.0)
        with self.assertRaises(ValueError):
            head_box((float("nan"), 100.0), 50.0)
        with self.assertRaises(ValueError):
            character_height({"foot_l": None, "foot_r": None},
                             (100.0, 155.0), 95.0)


class TestRealRig(unittest.TestCase):
    def test_straight_pose_ratio_is_exactly_construction(self):
        from ai_clip_studio.animation.rig import Stickman
        ch = Stickman(height=560, hat="none", moustache_style="none",
                      hair_style="short")
        # Construction identity: head_r is 0.17H by definition.
        self.assertAlmostEqual(ch.head_r, 0.17 * 560.0)
        # Geometric fixture: legs perfectly vertical via the FK path
        # (no foot targets — the IK path clamps targets to 98% of
        # reach, which would shorten the legs by design), so the
        # standing height is exactly H and the measured ratio is
        # exactly the construction ratio 0.34. A natural spread-leg
        # stance compresses the height slightly (see the band test
        # below) — that is stance geometry, not a defect.
        leg = ch.u_leg + ch.l_leg
        ch.set_pose(root_x=300.0, root_y=620.0 - leg, facing=1,
                    thigh_l=0.0, thigh_r=0.0, knee_l=0.0, knee_r=0.0,
                    arm_l=0.0, arm_r=0.0, elbow_l=0.0, elbow_r=0.0,
                    bob=0.0, torso_lean=0.0, head_look=0.0,
                    head_sway_x=0.0)
        ch.foot_target_l = None
        ch.foot_target_r = None
        measured = measure_character(ch, ch.joints())
        self.assertAlmostEqual(measured["head_ratio"], 0.34, places=3)
        self.assertAlmostEqual(measured["character_height"], 560.0,
                               delta=1.0)

    def test_standing_pose_ratio_in_band(self):
        from ai_clip_studio.animation.primitives import standing
        from ai_clip_studio.animation.rig import Stickman
        ch = Stickman(height=560, hat="none", moustache_style="none",
                      hair_style="short")
        standing(ch, 300.0, 620.0, facing=1)
        measured = measure_character(ch, ch.joints())
        # Bent knees compress the standing height slightly, so the
        # pose-measured ratio sits just above construction 0.34.
        self.assertGreaterEqual(measured["head_ratio"], 0.33)
        self.assertLessEqual(measured["head_ratio"], 0.36)
        self.assertAlmostEqual(measured["head"]["height"],
                               2 * ch.head_r)

    def test_rendered_character_boxes(self):
        from PIL import Image, ImageDraw
        from ai_clip_studio.animation.character_art import (
            draw_character_v4, make_character_instance)
        from ai_clip_studio.animation.primitives import standing
        for view in ("front", "profile"):
            ch = make_character_instance("minh", height=560)
            img = Image.new("RGB", (600, 700), (255, 255, 255))
            d = ImageDraw.Draw(img, "RGBA")
            standing(ch, 300.0, 620.0, facing=1)
            joints = draw_character_v4(d, ch, expression="neutral",
                                       view=view)
            measured = measure_character(ch, joints)
            self.assertGreaterEqual(measured["head_ratio"], 0.33)
            self.assertLessEqual(measured["head_ratio"], 0.36)
            self.assertAlmostEqual(measured["head"]["width"],
                                   2 * ch.head_r)


class TestSilhouette(unittest.TestCase):
    def _render_mask(self, name):
        import numpy as np
        from PIL import Image, ImageDraw
        from ai_clip_studio.animation.character_art import (
            draw_character_v4, make_character_instance)
        from ai_clip_studio.animation.primitives import standing
        ch = make_character_instance(name, height=560)
        img = Image.new("RGB", (600, 700), (255, 255, 255))
        d = ImageDraw.Draw(img, "RGBA")
        standing(ch, 300, 620, facing=1)
        draw_character_v4(d, ch, expression="neutral", view="front")
        suit = tuple(int(ch.suit[i:i + 2], 16) for i in (1, 3, 5))
        mask = silhouette_mask(img, suit_rgb=suit)
        # Cross-check against the v8 numpy method.
        arr = np.asarray(img).astype(int)
        dark = arr.sum(axis=2) < 400
        r, g, b = suit
        suit_m = ((np.abs(arr[:, :, 0] - r) < 12)
                  & (np.abs(arr[:, :, 1] - g) < 12)
                  & (np.abs(arr[:, :, 2] - b) < 12))
        ref = dark | suit_m
        flat = [bool(v) for row in mask for v in row]
        self.assertEqual(flat, list(ref.flatten()))
        return mask

    def test_officer_lustig_below_bar(self):
        iou = silhouette_iou(self._render_mask("officer"),
                             self._render_mask("lustig"))
        self.assertLessEqual(iou, SILHOUETTE_IOU_MAX)

    def test_identical_renders_iou_one_blank_zero(self):
        mask = self._render_mask("minh")
        self.assertEqual(silhouette_iou(mask, mask), 1.0)
        blank = [[False] * 4 for _ in range(4)]
        self.assertEqual(silhouette_iou(blank, blank), 0.0)
        with self.assertRaises(ValueError):
            silhouette_iou(mask, blank)

    def test_pairwise_report(self):
        renders = {n: self._render_mask(n)
                   for n in ("minh", "lan", "lustig")}
        report = pairwise_silhouette_report(renders)
        self.assertEqual(len(report["pairs"]), 3)
        for pair in report["pairs"]:
            self.assertEqual(pair["distinct"],
                             pair["iou"] <= pair["threshold"])
        self.assertEqual(report["threshold"], SILHOUETTE_IOU_MAX)

    def test_qa_gates_reexport(self):
        from ai_clip_studio.qa_gates import (
            SILHOUETTE_IOU_MAX as exported_max, silhouette_iou as fn)
        self.assertEqual(exported_max, 0.78)
        self.assertIs(fn, silhouette_iou)


class TestCameraCoverage(unittest.TestCase):
    def _report(self, shot_type, transform, crop, location):
        return {
            "shot_type": shot_type,
            "camera_validation": {
                "start_transform": list(transform),
                "end_transform": list(transform),
                "crop_rect": crop},
            "location_text": location,
        }

    def test_synthetic_coverage_counts(self):
        t1 = (0.0, 2.0, 4.8, 0.0, 1.2, 0.5, 46.0)
        t2 = (1.5, 2.0, 4.8, 0.0, 1.2, 0.5, 46.0)
        reports = [
            self._report("medium", t1, None, "street"),
            self._report("close_up", t1, [100, 100, 500, 500], "street"),
            self._report("medium", t2, None, "office"),
            {"shot_type": "medium"},  # no validation: unmeasured
        ]
        out = camera_coverage_report(reports)
        self.assertEqual(out["n_shots"], 4)
        self.assertEqual(out["n_cuts"], 3)
        self.assertEqual(out["measured_cuts"], 2)
        self.assertEqual(out["unmeasured_cuts"], 1)
        self.assertEqual(out["viewpoint_changes"], 1)
        self.assertEqual(out["same_camera_editorial_cuts"], 1)
        self.assertEqual(out["location_transitions"], 1)
        self.assertEqual(out["camera_transform_changes"], 2)

    def test_real_rendered_reports(self):
        import tempfile
        from pathlib import Path
        from ai_clip_studio.product_renderer import (
            _render_shot, plan_shots)
        from ai_clip_studio.studio_script_v1 import (
            parse_studio_script_v1)
        from ai_clip_studio.studio_script_v1_adapter import (
            adapt_document)
        agent = Path(__file__).resolve().parent.parent.parent
        doc = parse_studio_script_v1(
            (agent / "examples"
             / "hitler_ep01_munich_1914.studio.md").read_text(
                encoding="utf-8"))
        pkg = adapt_document(doc)
        shots = plan_shots(
            pkg, [{"line_index": i + 1, "duration": 0.65}
                  for i in range(9)])
        reports = []
        for idx in (0, 4, 10):
            shot = dict(shots[idx])
            shot["index"] = idx
            with tempfile.TemporaryDirectory() as tmp:
                reports.append(_render_shot(
                    {"shot": shot, "package": pkg,
                     "out_dir": tmp, "still_only": True}))
        out = camera_coverage_report(reports)
        self.assertEqual(out["n_shots"], 3)
        self.assertEqual(out["measured_cuts"], 2)
        self.assertEqual(out["unmeasured_cuts"], 0)
        self.assertEqual(out["viewpoint_changes"], 2)
        # 2 transitions: shots 0/4/10 sit in three distinct locations
        # (Munich street -> Europe map -> Bavaria barracks). Before the
        # OHM registry opened the map gate (2026-11-12), the map shot
        # carried no distinct location identity and this read 1.
        self.assertEqual(out["location_transitions"], 2)


if __name__ == "__main__":
    unittest.main()
