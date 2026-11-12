"""Regression tests: S9 tracked moving-text blur + S8 silence-floor fade check.

S9: the blur box must follow moving text across frames (interpolated
per-frame positions from the OCR track samples) instead of one static
box per segment — the slice defect where the sliding promo stayed
legible at t=4.5s. The render test generates a moving-text video on
the fly and proves the tracked blur covers the text at every sampled
time while a static box does not.

S8: the smooth_fades QA check must not fail when both fade windows
sit at the digital-silence floor (-91 dB); a genuinely abrupt ending
must still fail.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ai_clip_studio.affiliate.qa import audio_qa
from ai_clip_studio.affiliate.video.models import (
    BBox, ReplacementMode, ReplacementSpec, TextClassification,
    TextRegion, TrackSample)
from ai_clip_studio.affiliate.video.ocr import (
    OCRDetection, approve_removal, track_detections)
from ai_clip_studio.affiliate.video.text_replace import (
    ReplacementRefused, apply_replacements, build_replacement_filters,
    build_tracked_position_expressions, interpolate_box_at,
    track_displacement_px, tracked_blur_chunks)

FRAME = (1280, 720)
CJK_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


def _det(text: str, x: float, y: float, w: float, h: float,
         conf: float = 0.95) -> OCRDetection:
    return OCRDetection(text=text, confidence=conf,
                        polygon=[(x, y), (x + w, y),
                                 (x + w, y + h), (x, y + h)])


def _samples() -> list[TrackSample]:
    """Promo-like slide: fast move, then hold (measured fixture shape)."""
    return [TrackSample(3.0 + i * 0.125,
                        BBox(1020 - 107 * i if i < 9 else 62,
                             121, 254, 67))
            for i in range(12)]


def _region(samples: list[TrackSample] | None = None,
            cls: TextClassification = TextClassification.PROMOTIONAL_OVERLAY,
            start: float = 3.0, end: float = 4.5) -> TextRegion:
    return TextRegion(
        text_id="txt-001", track_id="track-001", original_text="限时优惠",
        start_time=start, end_time=end, bbox=BBox(62, 121, 254, 67),
        frame_size=FRAME, classification=cls,
        classification_reason="test",
        track_samples=list(samples or []))


def _spec(region: TextRegion) -> ReplacementSpec:
    return ReplacementSpec(region=region, mode=ReplacementMode.LOCAL_BLUR,
                           approved=True, approval_note="reviewed")


class TestTrackSamplesRecorded(unittest.TestCase):
    def test_track_detections_records_samples(self) -> None:
        detections = {
            0.0: [_det("限时优惠", 900, 100, 200, 60)],
            0.125: [_det("限时优惠", 850, 100, 200, 60)],
            0.25: [_det("限时优惠", 800, 100, 200, 60)],
        }
        result = track_detections(detections, FRAME,
                                  sample_interval_sec=0.125)
        self.assertEqual(len(result.regions), 1)
        region = result.regions[0]
        self.assertEqual([s.time for s in region.track_samples],
                         [0.0, 0.125, 0.25])
        self.assertEqual([s.bbox.x for s in region.track_samples],
                         [900.0, 850.0, 800.0])
        # The static median summary is unchanged.
        self.assertEqual(region.bbox.x, 850.0)
        self.assertEqual(region.end_time, 0.375)

    def test_samples_survive_dict_round_trip(self) -> None:
        region = _region(_samples())
        data = region.to_dict()
        self.assertEqual(len(data["track_samples"]), 12)
        restored = [TrackSample.from_dict(s)
                    for s in data["track_samples"]]
        self.assertEqual(restored[0].time, 3.0)
        self.assertEqual(restored[0].bbox.x, 1020.0)
        self.assertEqual(restored[-1].bbox.x, 62.0)

    def test_regions_from_ocr_payload_restores_samples(self) -> None:
        from ai_clip_studio.affiliate.pipeline_run import \
            regions_from_ocr_payload
        region = _region(_samples())
        payload = {"regions": [region.to_dict()]}
        restored = regions_from_ocr_payload(payload)
        self.assertEqual(len(restored), 1)
        self.assertEqual(len(restored[0].track_samples), 12)
        self.assertEqual(restored[0].track_samples[5].bbox.x, 485.0)

    def test_payload_without_samples_restores_empty(self) -> None:
        from ai_clip_studio.affiliate.pipeline_run import \
            regions_from_ocr_payload
        region = _region()
        data = region.to_dict()
        data.pop("track_samples", None)
        restored = regions_from_ocr_payload({"regions": [data]})
        self.assertEqual(restored[0].track_samples, [])


class TestInterpolateBox(unittest.TestCase):
    def test_midpoint_and_endpoints(self) -> None:
        samples = [TrackSample(0.0, BBox(100, 50, 200, 60)),
                   TrackSample(1.0, BBox(200, 50, 200, 60))]
        self.assertEqual(interpolate_box_at(samples, 0.0).x, 100.0)
        self.assertEqual(interpolate_box_at(samples, 0.5).x, 150.0)
        self.assertEqual(interpolate_box_at(samples, 1.0).x, 200.0)

    def test_holds_outside_range(self) -> None:
        samples = [TrackSample(1.0, BBox(100, 50, 200, 60)),
                   TrackSample(2.0, BBox(200, 50, 200, 60))]
        self.assertEqual(interpolate_box_at(samples, 0.0).x, 100.0)
        self.assertEqual(interpolate_box_at(samples, 9.0).x, 200.0)

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            interpolate_box_at([], 0.0)


class TestTrackedExpressions(unittest.TestCase):
    def test_two_samples_linear(self) -> None:
        samples = [TrackSample(0.0, BBox(100, 50, 200, 60)),
                   TrackSample(1.0, BBox(300, 50, 200, 60))]
        built = build_tracked_position_expressions(samples, 1280, 720)
        assert built is not None
        x_expr, y_expr, cw, ch = built
        self.assertEqual((cw, ch), (220, 80))  # max box + 2x10 pad
        self.assertIn("if(lt(t,1.0000)", x_expr)
        self.assertIn("200.0000*(t-0.0000)", x_expr)  # slope 200 px/s
        self.assertIn("clip(", x_expr)
        self.assertIn("clip(", y_expr)

    def test_single_sample_returns_none(self) -> None:
        self.assertIsNone(build_tracked_position_expressions(
            [TrackSample(0.0, BBox(100, 50, 200, 60))], 1280, 720))

    def test_clamp_keeps_box_inside_frame(self) -> None:
        # Text hugging the right edge: the box must clamp, not overflow.
        samples = [TrackSample(0.0, BBox(1100, 50, 170, 60)),
                   TrackSample(1.0, BBox(1100, 50, 170, 60))]
        built = build_tracked_position_expressions(samples, 1280, 720)
        assert built is not None
        x_expr, _, cw, _ = built
        self.assertIn(f"0,{1280 - cw:.4f}", x_expr)

    def test_duplicate_times_deduped(self) -> None:
        samples = [TrackSample(0.0, BBox(100, 50, 200, 60)),
                   TrackSample(0.0, BBox(110, 50, 200, 60)),
                   TrackSample(1.0, BBox(300, 50, 200, 60))]
        built = build_tracked_position_expressions(samples, 1280, 720)
        self.assertIsNotNone(built)

    def test_displacement_measures_motion(self) -> None:
        self.assertEqual(track_displacement_px(_samples()), 107.0)
        static = [TrackSample(0.0, BBox(100, 50, 200, 60)),
                  TrackSample(1.0, BBox(101, 50, 200, 60))]
        self.assertEqual(track_displacement_px(static), 1.0)


class TestTrackedChunks(unittest.TestCase):
    def test_short_track_is_one_chunk(self) -> None:
        self.assertEqual(len(tracked_blur_chunks(_samples())), 1)

    def test_long_track_chunks_share_boundary(self) -> None:
        samples = [TrackSample(i * 0.125, BBox(100, 100, 50, 50))
                   for i in range(65)]
        chunks = tracked_blur_chunks(samples)
        self.assertEqual([len(c) for c in chunks], [32, 32, 3])
        self.assertIs(chunks[0][-1], chunks[1][0])
        self.assertIs(chunks[1][-1], chunks[2][0])


class TestTrackedBlurFilters(unittest.TestCase):
    def test_moving_track_uses_expressions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            filt, _, log = build_replacement_filters(
                [_spec(_region(_samples()))], FRAME, tmp,
                authorization_type="USER_OWNED",
                commercial_rights_confirmed=True)
        self.assertIn("if(lt(t", filt)
        self.assertIn("boxblur", filt)
        self.assertEqual(filt.count("overlay="), 1)
        self.assertIn("tracked blur", log[0])

    def test_static_track_keeps_single_box(self) -> None:
        # Samples with only jitter (<= 2 px): exact static behaviour.
        samples = [TrackSample(0.0, BBox(440, 620, 400, 50)),
                   TrackSample(1.0, BBox(441, 620, 400, 50)),
                   TrackSample(2.0, BBox(440, 620, 400, 50))]
        region = _region(samples, TextClassification.SUBTITLE, 0.0, 3.0)
        with tempfile.TemporaryDirectory() as tmp:
            filt, _, log = build_replacement_filters(
                [_spec(region)], FRAME, tmp,
                authorization_type="USER_OWNED",
                commercial_rights_confirmed=True)
        self.assertNotIn("if(lt(t", filt)
        self.assertIn("between(t,0.000,3.000)", filt)
        self.assertEqual(len(log), 1)

    def test_protected_track_still_needs_approval(self) -> None:
        region = _region(_samples(), TextClassification.WATERMARK)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ReplacementRefused):
                build_replacement_filters(
                    [_spec(region)], FRAME, tmp,
                    authorization_type="USER_OWNED",
                    commercial_rights_confirmed=True)
        # With an approved removal, the tracked blur builds.
        approve_removal(region, "USER_OWNED", True, "tester",
                        acknowledge_ownership_risk=True)
        with tempfile.TemporaryDirectory() as tmp:
            filt, _, _ = build_replacement_filters(
                [_spec(region)], FRAME, tmp,
                authorization_type="USER_OWNED",
                commercial_rights_confirmed=True)
        self.assertIn("if(lt(t", filt)


def _load_cjk(size: int) -> ImageFont.FreeTypeFont:
    last_error: Exception | None = None
    for index in range(5):
        try:
            return ImageFont.truetype(CJK_FONT, size, index=index)
        except Exception as exc:  # noqa: BLE001 - try next face
            last_error = exc
    raise unittest.SkipTest(f"CJK font unavailable: {last_error}")


class TestTrackedBlurRender(unittest.TestCase):
    """End-to-end: a moving-text video blurred by the tracked path."""

    WIDTH, HEIGHT, FPS, DURATION = 640, 360, 30, 3.0
    TEXT = "限时优惠"
    SPEED_PX_S = 120.0
    X0, Y = 40.0, 100.0

    @classmethod
    def setUpClass(cls) -> None:
        cls.font = _load_cjk(48)
        cls.tmp = tempfile.TemporaryDirectory(prefix="aff_tracked_test_")
        cls.work = Path(cls.tmp.name)
        cls.video = cls.work / "moving.mp4"
        cls._render_video(cls.video)
        # Ground-truth samples every 0.25 s from the same motion law
        # the frames were drawn with.
        probe = Image.new("RGB", (cls.WIDTH, cls.HEIGHT))
        draw = ImageDraw.Draw(probe)
        box = draw.textbbox((0, 0), cls.TEXT, font=cls.font, stroke_width=2)
        cls.tw, cls.th = box[2] - box[0], box[3] - box[1]
        cls.samples = [TrackSample(round(i * 0.25, 3),
                                   BBox(cls.X0 + cls.SPEED_PX_S * i * 0.25,
                                        cls.Y, cls.tw, cls.th))
                       for i in range(12)]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    @classmethod
    def _render_video(cls, out: Path) -> None:
        frames = out.parent / "frames"
        frames.mkdir(exist_ok=True)
        for i in range(int(cls.FPS * cls.DURATION)):
            t = i / cls.FPS
            img = Image.new("RGB", (cls.WIDTH, cls.HEIGHT), (200, 210, 220))
            draw = ImageDraw.Draw(img)
            x = cls.X0 + cls.SPEED_PX_S * t
            draw.rounded_rectangle(
                [x - 12, cls.Y - 10, x + 200, cls.Y + 70],
                radius=8, fill=(214, 69, 42))
            draw.text((x, cls.Y), cls.TEXT, font=cls.font,
                      fill=(255, 255, 255), stroke_width=2,
                      stroke_fill=(120, 20, 10))
            img.save(frames / f"f_{i:04d}.jpg", quality=92)
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-framerate", str(cls.FPS),
             "-i", str(frames / "f_%04d.jpg"),
             "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
             "-y", str(out)], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"test video render failed: {proc.stderr}")

    def _text_box_at(self, t: float) -> tuple[int, int, int, int]:
        x = int(self.X0 + self.SPEED_PX_S * t)
        return (x, int(self.Y), int(self.tw), int(self.th))

    def _diff_at(self, time_sec: float, out: Path,
                 box: tuple[int, int, int, int]) -> float:
        from ai_clip_studio.affiliate.video.analysis import extract_frame_at
        tag = f"{time_sec:.2f}".replace(".", "_")
        s_path = extract_frame_at(self.video, time_sec,
                                  self.work / f"s_{tag}.jpg")
        o_path = extract_frame_at(out, time_sec, self.work / f"o_{tag}.jpg")
        s = np.asarray(Image.open(s_path).convert("L"), dtype=np.float32)
        o = np.asarray(Image.open(o_path).convert("L"), dtype=np.float32)
        x, y, w, h = box
        return float(np.mean(np.abs(s[y:y + h, x:x + w]
                                    - o[y:y + h, x:x + w])))

    def _tracked_spec(self) -> ReplacementSpec:
        region = TextRegion(
            text_id="txt-001", track_id="track-001",
            original_text=self.TEXT, start_time=0.0, end_time=3.0,
            bbox=BBox(self.X0 + self.SPEED_PX_S * 1.5, self.Y,
                      self.tw, self.th),
            frame_size=(self.WIDTH, self.HEIGHT),
            classification=TextClassification.PROMOTIONAL_OVERLAY,
            classification_reason="test",
            track_samples=list(self.samples))
        return ReplacementSpec(region=region,
                               mode=ReplacementMode.LOCAL_BLUR,
                               approved=True, approval_note="reviewed")

    def test_tracked_blur_covers_text_at_every_sampled_time(self) -> None:
        out, log = apply_replacements(
            self.video, [self._tracked_spec()],
            self.work / "tracked.mp4", (self.WIDTH, self.HEIGHT),
            "SYNTHETIC_FIXTURE", True)
        self.assertIn("tracked blur", log[0])
        for t in (0.5, 1.5, 2.5):
            diff = self._diff_at(t, out, self._text_box_at(t))
            self.assertGreater(diff, 5.0,
                               f"text not blurred at t={t} (diff {diff})")
        # Far corner untouched (re-encode noise only).
        corner = self._diff_at(1.5, out, (480, 260, 120, 60))
        self.assertLess(corner, 2.0)

    def test_static_box_misses_moved_text(self) -> None:
        """Control: the old static behaviour leaves the text readable
        once it moves away — this is the S9 defect, reproduced."""
        spec = self._tracked_spec()
        spec.region = TextRegion(
            text_id=spec.region.text_id, track_id=spec.region.track_id,
            original_text=spec.region.original_text,
            start_time=spec.region.start_time,
            end_time=spec.region.end_time, bbox=spec.region.bbox,
            frame_size=spec.region.frame_size,
            classification=spec.region.classification,
            classification_reason="test")  # no samples -> static path
        out, _ = apply_replacements(
            self.video, [spec], self.work / "static.mp4",
            (self.WIDTH, self.HEIGHT), "SYNTHETIC_FIXTURE", True)
        # Right half of the text box at t=2.5 sits fully outside the
        # static median box: it must stay (nearly) unchanged.
        x, y, w, h = self._text_box_at(2.5)
        right_half = (x + w // 2, y, w // 2, h)
        diff = self._diff_at(2.5, out, right_half)
        self.assertLess(diff, 2.0, f"static box unexpectedly covered {diff}")


# --------------------------------------------------------------------- S8

def _write_wav(path: Path, samples: np.ndarray, sr: int = 48000) -> Path:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm.tobytes())
    return path


def _tone_mix(path: Path, fade_in: bool, fade_out: bool,
              speech_end: float, total: float = 9.0) -> Path:
    """480 Hz tone (integer cycles per 0.3 s window, so equal-level
    windows measure exactly equal) with optional fades and a silent
    tail after ``speech_end``."""
    sr = 48000
    n = int(sr * total)
    t = np.arange(n) / sr
    signal = 0.3 * np.sin(2 * np.pi * 480.0 * t)
    if fade_in:
        ramp = min(0.3, total)
        idx = int(sr * ramp)
        signal[:idx] *= np.linspace(0.0, 1.0, idx)
    if fade_out:
        idx = int(sr * max(0.0, speech_end - 0.3))
        end = int(sr * speech_end)
        signal[idx:end] *= np.linspace(1.0, 0.0, end - idx)
    signal[int(sr * speech_end):] = 0.0
    return _write_wav(path, signal, sr)


def _fades_passed(mix: Path) -> tuple[bool, dict]:
    checks = audio_qa(mix, None, None, 9.0)
    found = [c for c in checks if c["name"] == "smooth_fades"]
    assert len(found) == 1
    return found[0]["passed"], found[0]


class TestSmoothFadesSilenceFloor(unittest.TestCase):
    """S8: silence-floor windows must not fail the fade check."""

    def test_silent_tail_passes(self) -> None:
        """Slice case: narration ends at 6.76 s, tail windows are pure
        silence at -91 dB. The check must pass (unmeasurable tail)."""
        with tempfile.TemporaryDirectory() as tmp:
            mix = _tone_mix(Path(tmp) / "mix.wav", fade_in=True,
                            fade_out=True, speech_end=6.76)
            passed, check = _fades_passed(mix)
        self.assertTrue(passed, check["detail"])
        self.assertIn("unmeasurable", check["detail"])
        self.assertEqual(check["evidence"]["tail"], -91.0)

    def test_abrupt_ending_still_fails(self) -> None:
        """Fade-in present, but the tail runs at full level to the
        very end: a genuine hard cut must still FAIL."""
        with tempfile.TemporaryDirectory() as tmp:
            mix = _tone_mix(Path(tmp) / "mix.wav", fade_in=True,
                            fade_out=False, speech_end=9.0)
            passed, check = _fades_passed(mix)
        self.assertFalse(passed, check["detail"])

    def test_all_silence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mix = _write_wav(Path(tmp) / "mix.wav",
                             np.zeros(int(48000 * 9.0), dtype=np.float32))
            passed, check = _fades_passed(mix)
        self.assertTrue(passed, check["detail"])

    def test_proper_fades_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mix = _tone_mix(Path(tmp) / "mix.wav", fade_in=True,
                            fade_out=True, speech_end=9.0)
            passed, check = _fades_passed(mix)
        self.assertTrue(passed, check["detail"])


if __name__ == "__main__":
    unittest.main()
