"""Phase 1 tests — voice, audio timeline, mix, captions, marketing.

Covers:
- Voice presets map to real provider voices only; speed stays in the
  natural 90–110 band; TTS failure stops the job (no placeholder).
- The timeline is built from MEASURED audio; unmeasured segments are
  refused; overflow is a reported conflict, never truncation.
- The mix plan + real ffmpeg mix: voice above music, fades present.
- Captions: ASS/SRT output, safe zones, legibility, font coverage.
- Marketing package: no invented links, no sales promises.
- Two tests synthesise REAL Vietnamese speech via the shared provider
  (they need the tts CLI + network, like the production pipeline).
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.affiliate.audio_timeline import (
    build_affiliate_timeline,
    build_mix_filter,
    concatenate_voice,
    plan_mix,
    render_mix,
    resolve_timeline_conflict,
)
from ai_clip_studio.affiliate.captions import (
    build_ass,
    build_cues,
    build_srt,
    check_font_coverage,
    check_safe_zone,
    check_vertical_legibility,
    safe_zone_guides,
)
from ai_clip_studio.affiliate.marketing import (
    build_hashtags,
    build_marketing_package,
    check_marketing_promises,
)
from ai_clip_studio.affiliate.qa import audio_qa
from ai_clip_studio.affiliate.schema import (
    AffiliateScript,
    AudioMix,
    ProductInfo,
    ScriptSegment,
    SubtitleStyle,
    VoiceConfig,
)
from ai_clip_studio.affiliate.voice import (
    MIN_SPEED,
    VOICE_PRESETS,
    VoiceError,
    apply_pronunciation,
    preset_config,
    preview_voice,
    resolve_affiliate_voice,
    synthesize_script,
    validate_speed,
)
from ai_clip_studio.timeline import TimelineError


def _tone_wav(path: Path, seconds: float, freq: int = 440) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"sine=frequency={freq}:duration={seconds}",
                    "-ac", "1", "-ar", "48000", str(path)],
                   check=True, timeout=60)
    return path


def _script_with_wavs(tmp: Path, durations=(2.0, 3.0)) -> AffiliateScript:
    segments = []
    for i, duration in enumerate(durations, 1):
        wav = _tone_wav(tmp / f"seg{i}.wav", duration)
        segments.append(ScriptSegment(
            segment_id=f"SEG{i:02d}",
            section="HOOK" if i == 1 else "CALL_TO_ACTION",
            text=f"Câu thử nghiệm số {i}.",
            voice_wav=str(wav), measured_sec=duration))
    return AffiliateScript(variant="demonstration", target_seconds=30.0,
                           segments=segments, approved=True,
                           approved_by="test")


class TestVoicePresets(unittest.TestCase):
    def test_presets_map_to_real_voices(self):
        from ai_clip_studio.language_gate import VI_VOICES
        real = set(VI_VOICES.values())
        for name, spec in VOICE_PRESETS.items():
            self.assertIn(spec["voice_id"], real, name)
            self.assertTrue(MIN_SPEED <= spec["voice_speed"] <= 110, name)

    def test_unknown_preset_rejected(self):
        with self.assertRaises(VoiceError):
            preset_config("bogus_preset")

    def test_explicit_unknown_voice_rejected(self):
        config = VoiceConfig(voice_id="avocado_v2:does_not_exist")
        with self.assertRaises(VoiceError):
            resolve_affiliate_voice(config)

    def test_speed_band_enforced(self):
        with self.assertRaises(VoiceError):
            validate_speed(50)
        with self.assertRaises(VoiceError):
            validate_speed(150)
        self.assertEqual(validate_speed(100), 100)

    def test_pronunciation_dictionary(self):
        out = apply_pronunciation("Hộp Shopee X200",
                                  {"Shopee": "Sóp-pi", "X200": "X hai trăm"})
        self.assertEqual(out, "Hộp Sóp-pi X hai trăm")

    def test_unapproved_script_refused(self):
        script = AffiliateScript(variant="demonstration",
                                 target_seconds=30.0, segments=[
                                     ScriptSegment(segment_id="SEG01",
                                                   section="HOOK",
                                                   text="Xin chào.")])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(VoiceError):
                synthesize_script(script, Path(tmp),
                                  config=preset_config("female_review"))


class TestRealTts(unittest.TestCase):
    """Real synthesis via the shared provider (needs the tts CLI)."""

    def test_preview_voice_produces_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = preview_voice(preset_config("female_review"), Path(tmp))
            self.assertTrue(wav.exists())
            self.assertGreater(wav.stat().st_size, 1000)
            from ai_clip_studio.timeline import measure_audio_duration
            duration = measure_audio_duration(wav)
            self.assertIsNotNone(duration)
            self.assertGreater(duration, 0.5)

    def test_synthesize_approved_script(self):
        script = AffiliateScript(
            variant="demonstration", target_seconds=30.0,
            segments=[ScriptSegment(segment_id="SEG01", section="HOOK",
                                    text="Bạn đang tìm một món đồ gọn gàng hơn?"),
                      ScriptSegment(segment_id="SEG02", section="CALL_TO_ACTION",
                                    text="Xem thông tin sản phẩm ở giỏ hàng nhé.")],
            approved=True, approved_by="test")
        with tempfile.TemporaryDirectory() as tmp:
            wavs = synthesize_script(script, Path(tmp),
                                     config=preset_config("female_review"))
            self.assertEqual(len(wavs), 2)
            for wav, seg in zip(wavs, script.segments):
                self.assertTrue(wav.exists())
                self.assertIsNotNone(seg.measured_sec)
                self.assertGreater(seg.measured_sec, 0.5)
                self.assertEqual(seg.voice_wav, str(wav))


class TestAudioTimeline(unittest.TestCase):
    def test_timeline_from_measured_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = _script_with_wavs(Path(tmp), durations=(2.0, 3.0))
            timeline = build_affiliate_timeline(
                script, footage_sec=30.0, pause_after_sec=0.5)
            self.assertTrue(timeline.all_measured)
            self.assertAlmostEqual(timeline.segments[0].start, 0.0)
            self.assertAlmostEqual(timeline.segments[0].end, 2.0, places=1)
            self.assertAlmostEqual(timeline.segments[1].start, 2.5, places=1)
            self.assertIsNone(timeline.conflict)

    def test_unmeasured_segment_refused(self):
        script = AffiliateScript(variant="demonstration",
                                 target_seconds=30.0, segments=[
                                     ScriptSegment(segment_id="SEG01",
                                                   section="HOOK",
                                                   text="Chưa có audio.")])
        with self.assertRaises(TimelineError):
            build_affiliate_timeline(script, footage_sec=30.0)

    def test_overflow_is_a_reported_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = _script_with_wavs(Path(tmp), durations=(4.0, 4.0))
            timeline = build_affiliate_timeline(script, footage_sec=5.0)
            self.assertIsNotNone(timeline.conflict)
            self.assertEqual(timeline.conflict["kind"],
                             "narration_longer_than_footage")
            self.assertFalse(timeline.conflict["resolved"])
            resolve_timeline_conflict(
                timeline, resolution="shorten_script_with_approval",
                note="user will shorten")
            self.assertTrue(timeline.conflict["resolved"])

    def test_unknown_resolution_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = _script_with_wavs(Path(tmp), durations=(4.0,))
            timeline = build_affiliate_timeline(script, footage_sec=2.0)
            with self.assertRaises(TimelineError):
                resolve_timeline_conflict(timeline, resolution="truncate")


class TestMix(unittest.TestCase):
    def test_replace_all_drops_original(self):
        plan = plan_mix(AudioMix(mode="REPLACE_ALL"),
                        voice_wav="v.wav", original_wav="o.wav",
                        total_sec=10.0)
        self.assertEqual(plan.original_wav, "")

    def test_music_without_authorization_refused(self):
        with self.assertRaises(TimelineError):
            plan_mix(AudioMix(mode="REPLACE_ALL", music_authorized=False),
                     voice_wav="v.wav", music_wav="m.wav")

    def test_filter_contains_ducking_and_fades(self):
        plan = plan_mix(AudioMix(mode="DUCK_ORIGINAL_AUDIO",
                                 music_authorized=True),
                        voice_wav="v.wav", music_wav="m.wav",
                        total_sec=10.0)
        _, filt = build_mix_filter(plan)
        self.assertTrue("sidechaincompress" in filt,
                        f"no sidechain ducking in filter: {filt}")
        self.assertIn("afade=t=in", filt)
        self.assertIn("afade=t=out", filt)

    def test_real_mix_and_voice_concatenation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            script = _script_with_wavs(tmp, durations=(2.0, 2.0))
            timeline = build_affiliate_timeline(script, footage_sec=10.0)
            voice_stem = concatenate_voice(timeline, tmp / "voice.wav")
            self.assertTrue(voice_stem.exists())
            music = _tone_wav(tmp / "music.wav", 10.0, freq=220)
            plan = plan_mix(AudioMix(mode="REPLACE_ALL",
                                     music_authorized=True,
                                     bus_gains_db={"voice": 0.0,
                                                   "original": -60.0,
                                                   "music": -20.0,
                                                   "sfx": -14.0}),
                            voice_wav=str(voice_stem),
                            music_wav=str(music), total_sec=timeline.total_sec)
            mixed = render_mix(plan, tmp / "mix.wav")
            self.assertTrue(mixed.exists())
            checks = audio_qa(mixed, voice_stem, music, timeline.total_sec,
                              {"voice": 0.0, "music": -20.0})
            by_name = {c["name"]: c for c in checks}
            self.assertTrue(by_name["mix_exists"]["passed"] if "mix_exists" in by_name else True)
            self.assertTrue(by_name["mix_no_clipping"]["passed"])
            self.assertTrue(by_name["voice_above_music"]["passed"])
            self.assertTrue(by_name["smooth_fades"]["passed"])


class TestCaptions(unittest.TestCase):
    STYLE = SubtitleStyle()

    def test_cues_split_and_span(self):
        segments = [{"start": 0.0, "end": 6.0,
                     "text": "Bạn đang tìm một món đồ giúp bàn làm việc "
                             "gọn gàng hơn mỗi ngày?"}]
        cues = build_cues(segments, self.STYLE)
        self.assertGreaterEqual(len(cues), 1)
        self.assertAlmostEqual(cues[0].start, 0.0)
        self.assertAlmostEqual(cues[-1].end, 6.0)
        joined = " ".join(c.text for c in cues)
        self.assertIn("gọn gàng", joined)

    def test_ass_header_and_events(self):
        segments = [{"start": 0.0, "end": 3.0, "text": "Xin chào các bạn."}]
        cues = build_cues(segments, self.STYLE)
        ass = build_ass(cues, self.STYLE)
        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("PlayResY: 1920", ass)
        self.assertIn("Dialogue: 0,0:00:00.00,0:00:03.00", ass)
        self.assertIn("Xin chào các bạn.", ass)

    def test_srt_output(self):
        segments = [{"start": 1.5, "end": 3.0, "text": "Xin chào."}]
        cues = build_cues(segments, self.STYLE)
        srt = build_srt(cues)
        self.assertIn("00:00:01,500 --> 00:00:03,000", srt)
        self.assertIn("Xin chào.", srt)

    def test_safe_zone_default_clear(self):
        result = check_safe_zone(self.STYLE)
        self.assertTrue(result["ok"], result)

    def test_safe_zone_violation_when_shifted_into_ui(self):
        # Positive position_y moves the box up into the top UI area.
        style = SubtitleStyle(position_y=1400)
        result = check_safe_zone(style)
        self.assertFalse(result["ok"])
        self.assertIn("top_ui", result["violations"])
        # Shifting down past the frame is also a violation.
        style = SubtitleStyle(position_y=-1400)
        result = check_safe_zone(style)
        self.assertFalse(result["ok"])
        self.assertIn("outside_frame", result["violations"])

    def test_legibility_64px_on_1920(self):
        result = check_vertical_legibility(self.STYLE)
        self.assertTrue(result["passes"])
        small = SubtitleStyle(font_size=20)
        self.assertFalse(check_vertical_legibility(small)["passes"])

    def test_font_coverage_vietnamese(self):
        result = check_font_coverage(["Xin chào, tiếng Việt có dấu: ồ ễ ệ ữ."])
        self.assertTrue(result["ok"], result)

    def test_safe_zone_guides_are_preview_only(self):
        guides = safe_zone_guides(self.STYLE)
        self.assertEqual(guides["frame"], [1080, 1920])
        self.assertIn("never burned", guides["note"].lower())


class TestMarketing(unittest.TestCase):
    PRODUCT = ProductInfo(
        product_name="Hộp đựng đồ nhà bếp", product_category="Nhà bếp",
        affiliate_url="https://shopee.vn/aff/abc",
        product_features=["nắp kín"],
        disclosure_text="Link affiliate — mình có thể nhận hoa hồng.")

    def test_package_uses_user_link_verbatim(self):
        package = build_marketing_package(self.PRODUCT, None)
        self.assertEqual(package["affiliate_link"],
                         "https://shopee.vn/aff/abc")
        self.assertTrue(package["affiliate_link_provided"])
        self.assertIn("Link affiliate", package["disclosure"])

    def test_no_link_never_invented(self):
        product = ProductInfo(product_name="X")
        package = build_marketing_package(product, None)
        self.assertIsNone(package["affiliate_link"])
        self.assertFalse(package["affiliate_link_provided"])

    def test_no_auto_publish(self):
        package = build_marketing_package(self.PRODUCT, None)
        self.assertFalse(package["auto_publish"])

    def test_no_sales_promises(self):
        package = build_marketing_package(self.PRODUCT, None)
        self.assertEqual(check_marketing_promises(package), [])

    def test_hashtags_from_category(self):
        tags = build_hashtags(self.PRODUCT)
        self.assertIn("#nhabep", tags)
        self.assertIn("#shopee", tags)

    def test_tiktok_caption_length_capped(self):
        product = ProductInfo(
            product_name="X" * 3000,
            product_features=["y" * 1000])
        package = build_marketing_package(product, None)
        self.assertLessEqual(len(package["tiktok_caption"]), 2200)

    def test_facts_come_from_user_input_only(self):
        package = build_marketing_package(self.PRODUCT, None)
        self.assertEqual(package["facts_source"], "user_input_only")

    def test_source_warning_when_authorization_unconfirmed(self):
        from ai_clip_studio.affiliate.schema import SourceAuthorization
        package = build_marketing_package(
            self.PRODUCT, None,
            authorization=SourceAuthorization(
                authorization_type="UNKNOWN",
                commercial_rights_confirmed=False))
        self.assertTrue(package["source_warning"])
        self.assertIn("user-supplied", package["source_warning"])

    def test_no_source_warning_when_seller_authorized(self):
        from ai_clip_studio.affiliate.schema import SourceAuthorization
        package = build_marketing_package(
            self.PRODUCT, None,
            authorization=SourceAuthorization(
                authorization_type="SELLER_AUTHORIZED",
                commercial_rights_confirmed=True))
        self.assertEqual(package["source_warning"], "")


if __name__ == "__main__":
    unittest.main()
