"""Phase 1 tests — Douyin standing requirements (2026-11-12 09:37).

1. Translation STYLE: humorous/viral/review wording that stays CLOSE
   to the original meaning — humour in wording, never in facts.
2. Per-character dubbing: speaker labels from the ASR stage flow
   through translation into the dub script, and each speaker gets
   their own voice, consistently across the video.
3. Voice mapping is data-driven (speaker_id -> preset), resolved
   through the shared TTS provider abstraction — no hardcoded voice.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio.affiliate.asr import (
    DiarizationError,
    Transcript,
    TranscriptSegment,
    assign_speakers,
    diarization_available,
    diarize_with_pyannote,
    transcript_from_dict,
    transcript_to_srt,
)
from ai_clip_studio.affiliate.schema import (
    AffiliateScript,
    ProductInfo,
    ScriptSegment,
    TranslationRecord,
    VoiceConfig,
)
from ai_clip_studio.affiliate.script_gen import script_from_translation
from ai_clip_studio.affiliate.translation import (
    _translation_prompt,
    translate_segments,
)
from ai_clip_studio.affiliate.voice import (
    VoiceError,
    config_for_segment,
    preset_config,
    synthesize_script,
    validate_speaker_voices,
)

PRODUCT = ProductInfo(product_name="Hộp đựng đồ nhà bếp",
                      product_category="Nhà bếp",
                      product_features=["nắp kín"],
                      call_to_action="Xem ở giỏ hàng nhé.")

SEGMENTS = [
    {"start": 0.0, "end": 2.5, "text": "这个产品非常好用",
     "speaker_id": "NGUOI_1"},
    {"start": 2.5, "end": 5.0, "text": "大家可以看一下",
     "speaker_id": "NGUOI_2"},
]


def _gemini_payload(texts):
    return json.dumps({"segments": [
        {"index": i + 1, "text": t} for i, t in enumerate(texts)]},
        ensure_ascii=False)


class TestTranslationStyle(unittest.TestCase):
    def test_prompt_carries_style_and_fidelity(self):
        prompt = _translation_prompt(
            SEGMENTS, "NATURAL_LOCALIZATION", {},
            style="humorous_viral_review")
        self.assertIn("hài hước", prompt.lower())
        self.assertIn("viral", prompt.lower())
        self.assertIn("BÁM SÁT", prompt)
        self.assertIn("KHÔNG bịa thêm sự thật", prompt)
        self.assertIn("Giữ nguyên mọi con số", prompt)

    def test_neutral_prompt_has_no_style_instruction(self):
        prompt = _translation_prompt(SEGMENTS, "NATURAL_LOCALIZATION", {})
        self.assertNotIn("viral", prompt.lower())

    def test_unknown_style_rejected(self):
        with self.assertRaises(ValueError):
            translate_segments(SEGMENTS, PRODUCT, style="bogus")

    def test_style_recorded_on_gemini_path(self):
        captured = {}

        def fake_generate(prompt, model, key):
            captured["prompt"] = prompt
            return _gemini_payload(["Cái hộp này xịn thật sự luôn!",
                                    "Mọi người nhìn thử nè!"])
        with mock.patch(
                "ai_clip_studio.affiliate.translation._gemini_generate",
                side_effect=fake_generate):
            record = translate_segments(
                SEGMENTS, PRODUCT, mode="NATURAL_LOCALIZATION",
                style="humorous_viral_review", api_key="test-key")
        self.assertEqual(record.style, "humorous_viral_review")
        self.assertTrue(record.engine.startswith("gemini:"))
        self.assertIn("viral", captured["prompt"].lower())
        # Speaker labels survive translation.
        self.assertEqual(record.translated_segments[0]["speaker_id"],
                         "NGUOI_1")
        self.assertEqual(record.translated_segments[1]["speaker_id"],
                         "NGUOI_2")
        self.assertEqual(record.original_segments[0]["speaker_id"],
                         "NGUOI_1")

    def test_fallback_keeps_style_and_refuses_to_invent(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            record = translate_segments(
                SEGMENTS, PRODUCT, mode="DIRECT_TRANSLATION",
                style="humorous_viral_review")
        self.assertEqual(record.style, "humorous_viral_review")
        self.assertEqual(record.engine, "fallback")
        self.assertEqual(record.translated_segments, [])
        self.assertTrue(record.needs_human_review)


class TestSpeakerSegmentation(unittest.TestCase):
    def _transcript(self):
        return Transcript(
            language="zh", language_probability=1.0, duration_sec=5.0,
            segments=[TranscriptSegment(start=0.0, end=2.5,
                                        text="这个产品非常好用"),
                      TranscriptSegment(start=2.5, end=5.0,
                                        text="大家可以看一下")])

    def test_default_is_single_labelled_speaker(self):
        transcript = self._transcript()
        self.assertEqual(transcript.speaker_method, "single")
        self.assertEqual(transcript.speakers, ["SPEAKER_00"])
        self.assertEqual(transcript.to_dict()["speakers"], ["SPEAKER_00"])

    def test_manual_ranges_assign_speakers(self):
        transcript = self._transcript()
        result = assign_speakers(transcript, [
            {"start": 0.0, "end": 2.5, "speaker_id": "NGUOI_1"},
            {"start": 2.5, "end": 5.0, "speaker_id": "NGUOI_2"},
        ])
        self.assertEqual(result["assigned"], 2)
        self.assertEqual(transcript.speakers, ["NGUOI_1", "NGUOI_2"])
        self.assertEqual(transcript.speaker_method, "manual")
        self.assertEqual(transcript.segments[1].speaker_id, "NGUOI_2")

    def test_uncovered_segments_keep_default_speaker(self):
        transcript = self._transcript()
        assign_speakers(transcript, [
            {"start": 0.0, "end": 2.5, "speaker_id": "NGUOI_1"}])
        self.assertEqual(transcript.segments[0].speaker_id, "NGUOI_1")
        self.assertEqual(transcript.segments[1].speaker_id, "SPEAKER_00")

    def test_malformed_ranges_rejected(self):
        transcript = self._transcript()
        with self.assertRaises(ValueError):
            assign_speakers(transcript, [{"start": 5.0, "end": 2.0,
                                          "speaker_id": "X"}])
        with self.assertRaises(ValueError):
            assign_speakers(transcript, [{"start": 0.0, "end": 2.0}])

    def test_srt_prefixes_speakers_when_multi(self):
        transcript = self._transcript()
        assign_speakers(transcript, [
            {"start": 0.0, "end": 2.5, "speaker_id": "NGUOI_1"},
            {"start": 2.5, "end": 5.0, "speaker_id": "NGUOI_2"},
        ])
        srt = transcript_to_srt(transcript)
        self.assertIn("[NGUOI_1]", srt)
        self.assertIn("[NGUOI_2]", srt)

    def test_transcript_round_trip_preserves_speakers(self):
        transcript = self._transcript()
        assign_speakers(transcript, [
            {"start": 0.0, "end": 5.0, "speaker_id": "NGUOI_1"}])
        rebuilt = transcript_from_dict(transcript.to_dict())
        self.assertEqual(rebuilt.speakers, ["NGUOI_1"])
        self.assertEqual(rebuilt.speaker_method, "manual")

    def test_pyannote_unavailable_is_an_honest_error(self):
        # pyannote.audio is not installed in this environment: the
        # diarization seam must say so, never fake speakers.
        if diarization_available():
            self.skipTest("pyannote is installed here")
        with self.assertRaises(DiarizationError) as ctx:
            diarize_with_pyannote(Path("x.wav"), self._transcript())
        self.assertIn("pyannote.audio", str(ctx.exception))


class TestDubScript(unittest.TestCase):
    def test_script_from_translation_preserves_speakers(self):
        record = TranslationRecord(
            mode="NATURAL_LOCALIZATION", engine="gemini:test-model",
            style="humorous_viral_review",
            original_segments=SEGMENTS,
            translated_segments=[
                {"start": 0.0, "end": 2.5,
                 "text": "Cái hộp này xịn thật sự luôn!",
                 "speaker_id": "NGUOI_1"},
                {"start": 2.5, "end": 5.0,
                 "text": "Mọi người nhìn thử nè!",
                 "speaker_id": "NGUOI_2"},
            ])
        script = script_from_translation(record)
        self.assertEqual(script.variant, "dubbed_translation")
        self.assertEqual(script.engine, "gemini:test-model")
        self.assertFalse(script.approved)
        self.assertEqual(script.segments[0].speaker_id, "NGUOI_1")
        self.assertEqual(script.segments[1].speaker_id, "NGUOI_2")
        self.assertEqual(script.segments[0].section, "HOOK")
        self.assertEqual(script.segments[1].section, "CALL_TO_ACTION")
        self.assertEqual(script.segments[0].start_time, 0.0)
        self.assertEqual(script.segments[1].end_time, 5.0)

    def test_script_from_translation_requires_translations(self):
        record = TranslationRecord(
            mode="DIRECT_TRANSLATION", engine="fallback",
            original_segments=SEGMENTS, needs_human_review=True)
        with self.assertRaises(ValueError):
            script_from_translation(record)


class TestPerSpeakerVoices(unittest.TestCase):
    def _script(self):
        return AffiliateScript(
            variant="dubbed_translation", target_seconds=30.0,
            segments=[
                ScriptSegment(segment_id="SEG01", section="HOOK",
                              text="Cái hộp này xịn thật sự luôn!",
                              speaker_id="NGUOI_1"),
                ScriptSegment(segment_id="SEG02", section="DEMONSTRATION",
                              text="Mọi người nhìn thử nè!",
                              speaker_id="NGUOI_2"),
                ScriptSegment(segment_id="SEG03",
                              section="CALL_TO_ACTION",
                              text="Xem ở giỏ hàng nhé!",
                              speaker_id="NGUOI_1"),
            ],
            approved=True, approved_by="test")

    def test_config_for_segment_uses_speaker_preset(self):
        config = preset_config("female_review")
        config.speaker_voices = {"NGUOI_1": "female_review",
                                 "NGUOI_2": "male_review"}
        seg1 = config_for_segment(
            config, ScriptSegment(segment_id="S1", section="HOOK",
                                  text="x", speaker_id="NGUOI_1"))
        seg2 = config_for_segment(
            config, ScriptSegment(segment_id="S2", section="HOOK",
                                  text="x", speaker_id="NGUOI_2"))
        self.assertNotEqual(seg1.voice_id, seg2.voice_id)
        # Same speaker -> same voice, every time.
        seg1b = config_for_segment(
            config, ScriptSegment(segment_id="S3", section="HOOK",
                                  text="y", speaker_id="NGUOI_1"))
        self.assertEqual(seg1.voice_id, seg1b.voice_id)

    def test_unmapped_speaker_uses_default_voice(self):
        config = preset_config("female_review")
        config.speaker_voices = {"NGUOI_1": "male_review"}
        seg = config_for_segment(
            config, ScriptSegment(segment_id="S1", section="HOOK",
                                  text="x", speaker_id="NGUOI_9"))
        self.assertEqual(seg.voice_id, config.voice_id)

    def test_unknown_preset_in_map_rejected(self):
        config = preset_config("female_review")
        config.speaker_voices = {"NGUOI_1": "bogus_preset"}
        with self.assertRaises(VoiceError):
            validate_speaker_voices(config)

    def test_synthesis_uses_distinct_voices_per_speaker(self):
        # Mock the CLI call: capture (voice, speed) per segment and
        # write a tiny real WAV so measurement still runs for real.
        import subprocess as sp

        def fake_synth(text, voice, speed, mp3_path):
            calls.append((voice, speed))
            sp.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=0.5",
                    "-ac", "1", "-ar", "48000", str(mp3_path)],
                   check=True, timeout=60)

        def fake_decode(mp3_path, wav_path):
            sp.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3_path),
                    "-ac", "1", "-ar", "48000", str(wav_path)],
                   check=True, timeout=60)

        calls: list = []
        config = preset_config("female_review")
        config.speaker_voices = {"NGUOI_1": "female_review",
                                 "NGUOI_2": "male_review"}
        script = self._script()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("ai_clip_studio.affiliate.voice._synthesize_one",
                           side_effect=fake_synth), \
                mock.patch("ai_clip_studio.affiliate.voice._decode_to_wav",
                           side_effect=fake_decode):
            wavs = synthesize_script(script, Path(tmp), config=config)
        self.assertEqual(len(wavs), 3)
        self.assertEqual(len(calls), 3)
        # NGUOI_1 twice with the same voice; NGUOI_2 different.
        self.assertEqual(calls[0][0], calls[2][0])
        self.assertNotEqual(calls[0][0], calls[1][0])
        for seg in script.segments:
            self.assertIsNotNone(seg.measured_sec)

    def test_real_two_speaker_synthesis(self):
        """Real end-to-end: two short lines, two real voices."""
        config = preset_config("female_review")
        config.speaker_voices = {"NGUOI_1": "female_review",
                                 "NGUOI_2": "male_review"}
        script = AffiliateScript(
            variant="dubbed_translation", target_seconds=30.0,
            segments=[
                ScriptSegment(segment_id="SEG01", section="HOOK",
                              text="Xin chào các bạn!",
                              speaker_id="NGUOI_1"),
                ScriptSegment(segment_id="SEG02",
                              section="CALL_TO_ACTION",
                              text="Xem ở giỏ hàng nhé!",
                              speaker_id="NGUOI_2"),
            ],
            approved=True, approved_by="test")
        with tempfile.TemporaryDirectory() as tmp:
            wavs = synthesize_script(script, Path(tmp), config=config)
            self.assertEqual(len(wavs), 2)
            for wav, seg in zip(wavs, script.segments):
                self.assertTrue(wav.exists())
                self.assertGreater(seg.measured_sec, 0.3)


class TestDubbingApi(unittest.TestCase):
    """API-level: style, speakers endpoint, dub script, voice map."""

    def setUp(self):
        from ai_clip_studio.affiliate import affiliate_api
        from ai_clip_studio.affiliate.store import AffiliateStore
        self.affiliate_api = affiliate_api
        self._tmp = tempfile.TemporaryDirectory()
        self._store = AffiliateStore(Path(self._tmp.name) / "store")
        self._orig_store = affiliate_api.STORE
        affiliate_api.STORE = self._store

        class Handler:
            def __init__(self):
                self.sent = []

            def _send(self, payload, status=200):
                self.sent.append((status, payload))
                return payload
        self.handler = Handler()

    def tearDown(self):
        self.affiliate_api.STORE = self._orig_store
        self._tmp.cleanup()

    def _create(self):
        self.affiliate_api.handle_affiliate_post(
            self.handler, "/api/affiliate/projects",
            {"project_name": "dub-test",
             "product": {"product_name": "Hộp đựng đồ"},
             "authorization": {"authorization_type": "SELLER_AUTHORIZED",
                               "commercial_rights_confirmed": True}})
        return self.handler.sent[-1][1]["project_id"]

    def _write_transcript(self, project_id):
        from ai_clip_studio.affiliate.asr import write_transcript_files
        transcript = Transcript(
            language="zh", language_probability=1.0, duration_sec=5.0,
            segments=[TranscriptSegment(start=0.0, end=2.5,
                                        text="这个产品非常好用"),
                      TranscriptSegment(start=2.5, end=5.0,
                                        text="大家可以看一下")])
        write_transcript_files(
            transcript,
            self._store.project_dir(project_id) / "transcription")

    def test_speakers_endpoint_applies_ranges(self):
        project_id = self._create()
        self._write_transcript(project_id)
        self.affiliate_api.handle_affiliate_post(
            self.handler,
            f"/api/affiliate/projects/{project_id}/speakers",
            {"ranges": [{"start": 0, "end": 2.5, "speaker_id": "NGUOI_1"},
                        {"start": 2.5, "end": 5, "speaker_id": "NGUOI_2"}]})
        status, payload = self.handler.sent[-1]
        self.assertEqual(status, 200)
        self.assertEqual(payload["speakers"], ["NGUOI_1", "NGUOI_2"])
        self.assertEqual(payload["speaker_method"], "manual")

    def test_speakers_endpoint_requires_transcript(self):
        project_id = self._create()
        self.affiliate_api.handle_affiliate_post(
            self.handler,
            f"/api/affiliate/projects/{project_id}/speakers",
            {"ranges": []})
        self.assertEqual(self.handler.sent[-1][0], 409)

    def test_translate_accepts_style(self):
        project_id = self._create()
        self._write_transcript(project_id)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            self.affiliate_api.handle_affiliate_post(
                self.handler,
                f"/api/affiliate/projects/{project_id}/translate",
                {"mode": "NATURAL_LOCALIZATION",
                 "style": "humorous_viral_review"})
        status, payload = self.handler.sent[-1]
        self.assertEqual(status, 200)
        self.assertEqual(payload["translation"]["style"],
                         "humorous_viral_review")

    def test_dub_script_from_translation(self):
        project_id = self._create()
        project = self._store.get(project_id)
        project.translation = TranslationRecord(
            mode="NATURAL_LOCALIZATION", engine="gemini:test",
            style="humorous_viral_review",
            translated_segments=[
                {"start": 0.0, "end": 2.5, "text": "Xịn thật sự!",
                 "speaker_id": "NGUOI_1"},
                {"start": 2.5, "end": 5.0, "text": "Nhìn thử nè!",
                 "speaker_id": "NGUOI_2"},
            ])
        self._store.save(project)
        self.affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/script",
            {"source": "translation"})
        status, payload = self.handler.sent[-1]
        self.assertEqual(status, 200)
        self.assertEqual(payload["script"]["variant"], "dubbed_translation")
        segments = payload["script"]["segments"]
        self.assertEqual(segments[0]["speaker_id"], "NGUOI_1")
        self.assertEqual(segments[1]["speaker_id"], "NGUOI_2")

    def test_dub_script_requires_translation(self):
        project_id = self._create()
        self.affiliate_api.handle_affiliate_post(
            self.handler, f"/api/affiliate/projects/{project_id}/script",
            {"source": "translation"})
        self.assertEqual(self.handler.sent[-1][0], 409)


if __name__ == "__main__":
    unittest.main()
