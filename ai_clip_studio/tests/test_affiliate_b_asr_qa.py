"""Phase 1 tests — Chinese ASR (real faster-whisper) + QA sections.

ASR honesty rules:
- Silence yields has_speech=False and zero segments — never invented
  words.
- Real Chinese speech yields real Chinese segments with timestamps.
- Transcript files (json/srt/txt) are written from the real result.

The Chinese speech fixture is a real TTS recording made with the
shared tts CLI (``--language zh``) and stored under
acceptance_loop/affiliate_fixtures/. If it is absent the speech test
skips; the silence test always runs.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.affiliate.asr import (
    transcribe_chinese,
    transcript_to_srt,
    write_transcript_files,
)
from ai_clip_studio.affiliate.qa import (
    commercial_qa,
    run_affiliate_qa,
    translation_qa,
)
from ai_clip_studio.affiliate.schema import (
    AffiliateProject,
    AffiliateScript,
    ProductInfo,
    ScriptSegment,
    SourceAuthorization,
    SourceVideo,
    TranslationRecord,
)

FIXTURES = Path.home() / "workspace" / "acceptance_loop" / "affiliate_fixtures"


class TestAsr(unittest.TestCase):
    def test_silence_yields_no_speech(self):
        silence = FIXTURES / "silence_5s.wav"
        self.assertTrue(silence.exists(), "silence fixture missing")
        transcript = transcribe_chinese(silence, model="tiny")
        self.assertFalse(transcript.has_speech)
        self.assertEqual(transcript.segments, [])
        self.assertEqual(transcript.full_text, "")

    def test_chinese_speech_transcribed(self):
        demo = FIXTURES / "chinese_demo.mp3"
        if not demo.exists():
            self.skipTest("chinese_demo.mp3 fixture not present")
        transcript = transcribe_chinese(demo, model="tiny")
        self.assertTrue(transcript.has_speech, "expected real speech")
        self.assertTrue(transcript.segments)
        text = transcript.full_text
        # Real transcription must contain CJK characters.
        self.assertTrue(any("\u4e00" <= ch <= "\u9fff" for ch in text),
                        f"no CJK chars in transcription: {text!r}")
        for seg in transcript.segments:
            self.assertLessEqual(seg.start, seg.end)
            self.assertGreaterEqual(seg.start, 0.0)

    def test_transcript_files_written(self):
        silence = FIXTURES / "silence_5s.wav"
        transcript = transcribe_chinese(silence, model="tiny")
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_transcript_files(transcript, Path(tmp))
            self.assertTrue(paths["json"].exists())
            self.assertTrue(paths["srt"].exists())
            self.assertTrue(paths["txt"].exists())
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertFalse(payload["has_speech"])
            self.assertEqual(transcript_to_srt(transcript), "")

    def test_unknown_model_refused(self):
        with self.assertRaises(ValueError):
            transcribe_chinese(FIXTURES / "silence_5s.wav", model="large-v3")

    def test_missing_file_refused(self):
        with self.assertRaises(FileNotFoundError):
            transcribe_chinese(Path("/tmp/does-not-exist.wav"), model="tiny")


class TestQaSections(unittest.TestCase):
    def _project(self, **overrides):
        project = AffiliateProject(
            project_id="aff_qa_001",
            product=ProductInfo(product_name="Hộp X"),
            authorization=SourceAuthorization(
                authorization_type="USER_OWNED",
                commercial_rights_confirmed=True),
            source_video=SourceVideo(file_name="x.mp4", file_size_bytes=10,
                                     sha256="a" * 64))
        for key, value in overrides.items():
            setattr(project, key, value)
        return project

    def test_translation_qa_flags_untranslated(self):
        project = self._project(translation=TranslationRecord(
            mode="NATURAL_LOCALIZATION", engine="fallback",
            original_segments=[{"start": 0, "end": 1, "text": "你好"}],
            needs_human_review=True))
        checks = {c["name"]: c for c in translation_qa(project)}
        self.assertFalse(checks["translation_complete"]["passed"])

    def test_translation_qa_number_preservation(self):
        project = self._project(translation=TranslationRecord(
            mode="DIRECT_TRANSLATION", engine="gemini:test",
            original_segments=[{"start": 0, "end": 1,
                                "text": "容量500ml，型号X200"}],
            translated_segments=[{"start": 0, "end": 1,
                                  "text": "Dung tích 500ml, model X200"}]))
        checks = {c["name"]: c for c in translation_qa(project)}
        self.assertTrue(checks["numbers_preserved"]["passed"])
        self.assertTrue(checks["segment_count_match"]["passed"])

    def test_translation_qa_catches_dropped_number(self):
        project = self._project(translation=TranslationRecord(
            mode="DIRECT_TRANSLATION", engine="gemini:test",
            original_segments=[{"start": 0, "end": 1, "text": "500ml"}],
            translated_segments=[{"start": 0, "end": 1,
                                  "text": "Dung tích lớn"}]))
        checks = {c["name"]: c for c in translation_qa(project)}
        self.assertFalse(checks["numbers_preserved"]["passed"])

    def test_commercial_qa_passes_clean_project(self):
        project = self._project(script=AffiliateScript(
            variant="demonstration", target_seconds=30.0,
            segments=[ScriptSegment(segment_id="SEG01", section="HOOK",
                                    text="Sản phẩm có nắp kín.")],
            approved=True, approved_by="Mai"))
        checks = {c["name"]: c for c in commercial_qa(project)}
        self.assertTrue(checks["export_gate"]["passed"])
        self.assertTrue(checks["no_fabricated_testimonials"]["passed"])
        self.assertTrue(checks["script_approved"]["passed"])

    def test_commercial_qa_flags_unconfirmed_testimonial(self):
        project = self._project(script=AffiliateScript(
            variant="natural_review", target_seconds=30.0,
            segments=[ScriptSegment(segment_id="SEG01", section="HOOK",
                                    text="Mình đã dùng thử rồi, rất tốt.")],
            approved=True, approved_by="Mai"))
        checks = {c["name"]: c for c in commercial_qa(project)}
        self.assertFalse(checks["no_fabricated_testimonials"]["passed"])

    def test_full_report_marks_creative_review_required(self):
        project = self._project()
        report = run_affiliate_qa(project)
        self.assertEqual(report["creative_status"], "REVIEW_REQUIRED")
        self.assertEqual(report["sections"]["video"]["status"], "NOT_RUN")
        self.assertIn("verdict", report)


if __name__ == "__main__":
    unittest.main()
