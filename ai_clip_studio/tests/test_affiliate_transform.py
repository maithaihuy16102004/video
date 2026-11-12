"""Tests: transform engine (validation, graph, flip safety, renders)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.affiliate.video.models import TransformOp
from ai_clip_studio.affiliate.video.probe import probe_source
from ai_clip_studio.affiliate.video.transform import (
    TransformRefused, apply_transforms, assess_flip_safety,
    build_transform_graph, reframe_crop_rect, run_stabilize_detect,
    validate_ops)

FIXTURES = Path.home() / "workspace/acceptance_loop/affiliate_fixtures"
FIXTURE = FIXTURES / "fixture.mp4"


def _op(name: str, purpose: str = "editorial test", **params) -> TransformOp:
    return TransformOp(operation=name, parameters=params, purpose=purpose)


class TestValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert FIXTURE.is_file(), "run generate_fixture.py first"
        cls.source = probe_source(FIXTURE)

    def test_purpose_required(self) -> None:
        with self.assertRaises(TransformRefused):
            validate_ops([TransformOp(operation="brightness",
                                      parameters={"value": 0.1},
                                      purpose="")], self.source)

    def test_unknown_operation(self) -> None:
        with self.assertRaises(TransformRefused):
            validate_ops([_op("explode")], self.source)

    def test_hflip_needs_approval(self) -> None:
        with self.assertRaises(TransformRefused):
            validate_ops([_op("hflip")], self.source)
        op = _op("hflip")
        op.approved = True
        validate_ops([op], self.source)  # must not raise

    def test_crop_out_of_bounds(self) -> None:
        with self.assertRaises(TransformRefused):
            validate_ops([_op("crop", x=1200, y=0, w=200, h=200)],
                         self.source)

    def test_speed_range(self) -> None:
        with self.assertRaises(TransformRefused):
            validate_ops([_op("speed", factor=10.0)], self.source)

    def test_trim_range(self) -> None:
        with self.assertRaises(TransformRefused):
            validate_ops([_op("trim", start=5.0, end=2.0)], self.source)
        with self.assertRaises(TransformRefused):
            validate_ops([_op("trim", start=0.0, end=99.0)], self.source)

    def test_reorder_must_be_first(self) -> None:
        reorder = _op("scene_reorder", segments=[[6.0, 9.0], [0.0, 3.0]])
        with self.assertRaises(TransformRefused):
            validate_ops([_op("brightness", value=0.1), reorder],
                         self.source)
        validate_ops([reorder, _op("brightness", value=0.1)],
                     self.source)  # must not raise

    def test_reframe_strategy(self) -> None:
        with self.assertRaises(TransformRefused):
            validate_ops([_op("reframe", target_w=1080, target_h=1920,
                              strategy="bogus")], self.source)


class TestGraphBuilding(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = probe_source(FIXTURE)

    def test_brightness_contrast_chain(self) -> None:
        graph = build_transform_graph(
            [_op("brightness", value=0.1), _op("contrast", value=1.1)],
            self.source)
        filt, _, _ = graph.build()
        self.assertIn("eq=brightness=0.100", filt)
        self.assertIn("eq=contrast=1.100", filt)

    def test_speed_chain(self) -> None:
        graph = build_transform_graph([_op("speed", factor=2.0)],
                                      self.source)
        filt, _, audio = graph.build()
        self.assertIn("setpts=PTS/2.0000", filt)
        self.assertIn("atempo=2.0000", filt)
        self.assertNotEqual(audio, "0:a")

    def test_slow_speed_chains_atempo(self) -> None:
        graph = build_transform_graph([_op("speed", factor=0.25)],
                                      self.source)
        filt, _, _ = graph.build()
        self.assertIn("atempo=0.5,atempo=0.5000", filt)

    def test_reframe_crop_rect_math(self) -> None:
        x, y, w, h = reframe_crop_rect(1280, 720, 1080, 1920)
        # 720 * 9/16 = 405 -> rounded down to even 404 for yuv420p.
        self.assertEqual((w, h), (404, 720))
        self.assertEqual(x, 438)
        self.assertEqual(y, 0)

    def test_stabilize_flags_prepass(self) -> None:
        graph = build_transform_graph([_op("stabilize")], self.source)
        self.assertTrue(graph.needs_stabilize_detect)

    def test_reorder_after_other_stage_refused(self) -> None:
        with self.assertRaises(TransformRefused):
            build_transform_graph(
                [_op("scene_reorder", segments=[[0.0, 3.0]])],
                self.source, start_label="rep1")


class TestFlipSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = probe_source(FIXTURE)

    def test_flags_text_frames(self) -> None:
        report = assess_flip_safety(FIXTURE, self.source,
                                    sample_times=[1.5, 4.5, 7.5])
        self.assertEqual(report.text_frames_checked, 3)
        self.assertGreaterEqual(report.text_frames_flagged, 1)
        self.assertTrue(any("mirror" in w["detail"].lower()
                            for w in report.warnings))
        self.assertIn("mirror", report.recommendation.lower())


class TestApplyTransforms(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="aff_tr_test_")
        cls.work = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_brightness_render(self) -> None:
        out, notes, _ = apply_transforms(
            FIXTURE, [_op("brightness", value=0.1)],
            self.work / "bright.mp4")
        info = probe_source(out)
        self.assertEqual((info.width, info.height), (1280, 720))
        self.assertTrue(any("brightness" in n for n in notes))

    def test_reorder_render(self) -> None:
        out, _, _ = apply_transforms(
            FIXTURE, [_op("scene_reorder",
                          segments=[[6.0, 9.0], [0.0, 3.0]])],
            self.work / "reordered.mp4")
        info = probe_source(out)
        self.assertAlmostEqual(info.duration_sec, 6.0, places=1)

    def test_stabilize_detect_produces_trf(self) -> None:
        trf = run_stabilize_detect(FIXTURE, self.work)
        self.assertTrue(trf.is_file())
        self.assertGreater(trf.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
