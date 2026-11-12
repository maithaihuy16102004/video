"""Unit tests for ai_clip_studio.frame_qa (stdlib unittest, no network).

Run from ~/workspace/video-16x9-v2/:
    python3 -m unittest ai_clip_studio.tests.test_frame_qa -v
or via discovery:
    python3 -m unittest discover -s ai_clip_studio/tests -p 'test_frame_qa.py' -v

Detection tests use synthetic frame stacks (no video files). One integration
test encodes a tiny real video with ffmpeg (testsrc) and runs the decode +
analyze path end to end; it skips if ffmpeg is missing.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_clip_studio import frame_qa


def solid_stack(n, h, w, rgb):
    """n identical frames of one solid colour."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = rgb
    return np.stack([frame.copy() for _ in range(n)])


def moving_stack(n, h=16, w=16):
    """Frames with a bright square sliding across a dark field (real motion)."""
    out = np.zeros((n, h, w, 3), dtype=np.uint8)
    out[:, :, :] = (30, 30, 30)
    for i in range(n):
        x = (i * 2) % (w - 4)
        out[i, 4:8, x:x + 4] = (200, 200, 200)
    return out


class TestComputeStats(unittest.TestCase):
    def test_white_frame_stats(self):
        stats = frame_qa.compute_frame_stats(solid_stack(3, 8, 8, (255, 255, 255)))
        self.assertEqual(stats.n_frames, 3)
        self.assertTrue(np.allclose(stats.mean, 1.0))
        self.assertTrue(np.allclose(stats.sat, 0.0))

    def test_black_frame_stats(self):
        stats = frame_qa.compute_frame_stats(solid_stack(3, 8, 8, (0, 0, 0)))
        self.assertTrue(np.allclose(stats.mean, 0.0))

    def test_diff_length_and_zero_for_identical(self):
        stats = frame_qa.compute_frame_stats(solid_stack(5, 8, 8, (10, 20, 30)))
        self.assertEqual(len(stats.diff), 4)
        self.assertTrue(np.allclose(stats.diff, 0.0))

    def test_diff_positive_for_motion(self):
        stats = frame_qa.compute_frame_stats(moving_stack(10))
        self.assertTrue((stats.diff > 0).all())

    def test_rejects_bad_shapes(self):
        with self.assertRaises(ValueError):
            frame_qa.compute_frame_stats(np.zeros((0, 8, 8, 3), dtype=np.uint8))
        with self.assertRaises(ValueError):
            frame_qa.compute_frame_stats(np.zeros((4, 8, 8), dtype=np.uint8))


class TestBlackWhite(unittest.TestCase):
    def test_black_detection(self):
        frames = np.concatenate([
            solid_stack(4, 8, 8, (100, 100, 100)),
            solid_stack(2, 8, 8, (0, 0, 0)),
            solid_stack(4, 8, 8, (100, 100, 100)),
        ])
        stats = frame_qa.compute_frame_stats(frames)
        self.assertEqual(frame_qa.detect_black_frames(stats), [4, 5])

    def test_white_detection_excludes_planned(self):
        frames = np.concatenate([
            solid_stack(4, 8, 8, (100, 100, 100)),
            solid_stack(1, 8, 8, (255, 255, 255)),
            solid_stack(4, 8, 8, (100, 100, 100)),
            solid_stack(1, 8, 8, (255, 255, 255)),
        ])
        stats = frame_qa.compute_frame_stats(frames)
        self.assertEqual(frame_qa.detect_white_frames(stats), [4, 9])
        self.assertEqual(frame_qa.detect_white_frames(stats, planned={4}), [9])


class TestFrozen(unittest.TestCase):
    def test_frozen_span_at_24fps(self):
        # 12 identical frames at 24 fps = 11 diffs = 0.46 s > 0.4 s threshold.
        frames = np.concatenate([
            moving_stack(6),
            solid_stack(12, 16, 16, (90, 90, 90)),
            moving_stack(6),
        ])
        stats = frame_qa.compute_frame_stats(frames)
        spans = frame_qa.detect_frozen_spans(stats, fps=24.0)
        self.assertEqual(len(spans), 1)
        # Diffs 6..16 are zero (frames 6..17 identical); span is in diff coords.
        self.assertEqual(spans[0], (6, 16))

    def test_short_freeze_not_reported(self):
        # 5 identical frames = 4 diffs = 0.17 s at 24 fps < 0.4 s.
        frames = np.concatenate([
            moving_stack(6),
            solid_stack(5, 16, 16, (90, 90, 90)),
            moving_stack(6),
        ])
        stats = frame_qa.compute_frame_stats(frames)
        self.assertEqual(frame_qa.detect_frozen_spans(stats, fps=24.0), [])

    def test_frozen_threshold_scales_with_fps(self):
        # Same 12-frame freeze: 0.4 s at 30 fps needs 12 diffs; 11 diffs is
        # 0.37 s, so at 30 fps it must NOT report, at 24 fps it must.
        frames = np.concatenate([
            moving_stack(6),
            solid_stack(12, 16, 16, (90, 90, 90)),
            moving_stack(6),
        ])
        stats = frame_qa.compute_frame_stats(frames)
        self.assertEqual(frame_qa.detect_frozen_spans(stats, fps=30.0), [])
        self.assertEqual(len(frame_qa.detect_frozen_spans(stats, fps=24.0)), 1)

    def test_rejects_bad_fps(self):
        stats = frame_qa.compute_frame_stats(moving_stack(4))
        with self.assertRaises(ValueError):
            frame_qa.detect_frozen_spans(stats, fps=0)


class TestPops(unittest.TestCase):
    def test_pop_spike_detected(self):
        frames = moving_stack(30)
        frames[15] = 255  # one fully white frame mid-motion
        stats = frame_qa.compute_frame_stats(frames)
        pops = frame_qa.detect_pops(stats)
        self.assertIn(15, pops)

    def test_pop_on_planned_frame_excluded(self):
        frames = moving_stack(30)
        frames[15] = 255
        stats = frame_qa.compute_frame_stats(frames)
        pops = frame_qa.detect_pops(stats, planned={15})
        self.assertNotIn(15, pops)

    def test_steady_motion_has_no_pops(self):
        stats = frame_qa.compute_frame_stats(moving_stack(30))
        self.assertEqual(frame_qa.detect_pops(stats), [])


class TestPlannedAndPerShot(unittest.TestCase):
    def test_planned_frame_set(self):
        planned = frame_qa.planned_frame_set(
            shots=[{"id": 1, "a": 0, "b": 10}, {"id": 2, "a": 10, "b": 20}],
            flashes=[(5, 6)],
            xfades=[(18, 19)],
            extra_spans=[(12, 12)],
        )
        # Shot starts (and the frame before) + widened spans.
        # Widening follows the source: range(a-1, b+1), so a span (5, 6)
        # covers {4, 5, 6} — one frame past each end of the [a, b) span.
        self.assertIn(0, planned)
        self.assertIn(10, planned)
        self.assertIn(9, planned)
        self.assertIn(4, planned)  # flash widened by 1
        self.assertIn(6, planned)
        self.assertNotIn(7, planned)
        self.assertIn(17, planned)  # xfade widened by 1
        self.assertIn(19, planned)
        self.assertNotIn(20, planned)
        self.assertIn(11, planned)  # extra span widened by 1
        self.assertIn(12, planned)
        self.assertNotIn(13, planned)
        self.assertNotIn(2, planned)
        self.assertNotIn(-1, planned)

    def test_per_shot_stats(self):
        frames = np.concatenate([
            solid_stack(10, 8, 8, (50, 50, 50)),
            solid_stack(10, 8, 8, (200, 200, 200)),
        ])
        stats = frame_qa.compute_frame_stats(frames)
        rows = frame_qa.per_shot_stats(stats, [
            {"id": 1, "a": 0, "b": 10},
            {"id": 2, "a": 10, "b": 20},
        ])
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0]["mean"], 50 / 255, places=3)
        self.assertAlmostEqual(rows[1]["mean"], 200 / 255, places=3)

    def test_per_shot_clamps_and_defaults(self):
        stats = frame_qa.compute_frame_stats(solid_stack(6, 8, 8, (77, 77, 77)))
        rows = frame_qa.per_shot_stats(stats, [{"id": 9, "a": 0, "b": 999}])
        self.assertEqual(rows[0]["b"], 6)
        rows = frame_qa.per_shot_stats(stats, [])
        self.assertEqual(rows[0]["id"], 0)


class TestAnalyzeFrames(unittest.TestCase):
    def test_clean_video_report(self):
        report = frame_qa.analyze_frames(moving_stack(30), fps=24.0)
        self.assertEqual(report.black_frames, [])
        self.assertEqual(report.white_frames, [])
        self.assertEqual(report.frozen_spans, [])
        self.assertEqual(report.pops, [])
        self.assertGreater(report.motion_mean_diff, 0)

    def test_report_serializes(self):
        report = frame_qa.analyze_frames(moving_stack(12), fps=24.0)
        d = report.to_dict()
        self.assertEqual(d["n_frames"], 12)
        self.assertEqual(d["fps"], 24.0)
        self.assertIsInstance(d["frozen_spans"], list)


class TestDecodeIntegration(unittest.TestCase):
    def test_decode_and_probe_real_video(self):
        ffmpeg = subprocess.run(["which", "ffmpeg"], capture_output=True)
        if ffmpeg.returncode != 0:
            self.skipTest("ffmpeg not on PATH")
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "t.mp4")
            subprocess.run([
                "ffmpeg", "-v", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=1:size=320x180:rate=24",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-shortest", path,
            ], check=True)
            frames = frame_qa.decode_frames(path)
            self.assertEqual(frames.shape[1:], (180, 320, 3))
            self.assertGreaterEqual(frames.shape[0], 20)
            specs = frame_qa.probe_specs(path)
            self.assertEqual(specs["width"], 320)
            self.assertEqual(specs["height"], 180)
            self.assertEqual(len(specs["audio"]), 1)
            report = frame_qa.analyze_frames(frames, fps=24.0)
            self.assertEqual(report.black_frames, [])
            self.assertEqual(report.frozen_spans, [])


if __name__ == "__main__":
    unittest.main()
