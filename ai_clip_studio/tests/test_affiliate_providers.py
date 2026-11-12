"""Tests: provider seams (providers.py) + registry.

No test in this file touches the network. The yt-dlp tests use a
bogus binary path (NOT_AVAILABLE) or a fake executable script that
records its argv. The Gemini tests run with GEMINI_API_KEY removed
from the environment, so the translation adapter takes its labelled
fallback path without any HTTP call.
"""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio.affiliate.providers import (
    REASON_COOKIES_REQUIRED,
    REASON_DOWNLOAD_FAILED,
    REASON_NETWORK_ERROR,
    REASON_NOT_AVAILABLE,
    REASON_NOT_FOUND,
    REASON_UNSUPPORTED_URL,
    DelegatingOCREngine,
    DownloadFailure,
    DownloadResult,
    FakeDownloader,
    FakeGeminiClient,
    FakeOCREngine,
    FakeTTSProvider,
    FailingDownloader,
    TranslationGeminiClient,
    UnavailableGeminiClient,
    VoiceTTSProvider,
    YtDlpDownloader,
    as_ingest_downloader,
    get_provider,
    list_providers,
    resolve_ytdlp_binary,
)
from ai_clip_studio.affiliate.schema import ProductInfo, VoiceConfig
from ai_clip_studio.affiliate.video.ingest import IngestRequest, ingest_source
from ai_clip_studio.affiliate.video.ocr import OCRDetection, track_detections
from ai_clip_studio.affiliate.video.probe import sha256_file

FIXTURES = Path.home() / "workspace/acceptance_loop/affiliate_fixtures"
FIXTURE = FIXTURES / "fixture.mp4"
EXAMPLE_URL = "https://example.com/videos/product-demo.mp4"


class TestDownloadFailure(unittest.TestCase):
    def test_reason_codes_and_shape(self) -> None:
        err = DownloadFailure(REASON_COOKIES_REQUIRED, "need cookies")
        self.assertEqual(err.reason, REASON_COOKIES_REQUIRED)
        self.assertEqual(err.detail, "need cookies")
        self.assertEqual(err.to_dict(), {"reason": REASON_COOKIES_REQUIRED,
                                         "detail": "need cookies"})

    def test_result_shape(self) -> None:
        result = DownloadResult(path="/tmp/x.mp4", downloader_name="yt-dlp",
                                metadata={"url": EXAMPLE_URL})
        self.assertEqual(result.path, "/tmp/x.mp4")
        self.assertEqual(result.metadata["url"], EXAMPLE_URL)


class TestYtDlpBinaryResolution(unittest.TestCase):
    def test_explicit_path_wins(self) -> None:
        self.assertEqual(resolve_ytdlp_binary("/opt/custom/yt-dlp"),
                         "/opt/custom/yt-dlp")

    def test_bogus_binary_reports_not_available_without_crash(self) -> None:
        downloader = YtDlpDownloader(binary="/definitely/not/here/yt-dlp")
        status = downloader.status()
        self.assertFalse(status["available"])
        self.assertEqual(status["status"], "NOT_AVAILABLE")
        self.assertFalse(downloader.available)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(DownloadFailure) as ctx:
                downloader.fetch(EXAMPLE_URL, tmp)
        self.assertEqual(ctx.exception.reason, REASON_NOT_AVAILABLE)

    def test_default_resolution_does_not_crash(self) -> None:
        downloader = YtDlpDownloader()
        status = downloader.status()
        self.assertIn(status["status"], ("AVAILABLE", "NOT_AVAILABLE"))
        self.assertIn(status["resolution"],
                      ("explicit", "PATH", "venv", "none"))


class TestYtDlpStderrClassification(unittest.TestCase):
    def test_share_url_unsupported(self) -> None:
        # Verbatim error from the 2026-11-12 Douyin share-URL probe.
        self.assertEqual(YtDlpDownloader.classify_stderr(
            "ERROR: Unsupported URL: https://so.douyin.com/video/detail"
            "?aweme_id=7698375090295314417"), REASON_UNSUPPORTED_URL)

    def test_canonical_url_cookies_required(self) -> None:
        # Verbatim error from the 2026-11-12 canonical-URL probe.
        self.assertEqual(YtDlpDownloader.classify_stderr(
            "ERROR: [Douyin] 7698375090295314417: Fresh cookies (not "
            "necessarily logged in) are needed"), REASON_COOKIES_REQUIRED)

    def test_not_found(self) -> None:
        self.assertEqual(YtDlpDownloader.classify_stderr(
            "ERROR: HTTP Error 404: Not Found"), REASON_NOT_FOUND)

    def test_network_error(self) -> None:
        self.assertEqual(YtDlpDownloader.classify_stderr(
            "ERROR: unable to download webpage: <urlopen error [Errno -2] "
            "Name or service not known>"), REASON_NETWORK_ERROR)

    def test_unknown_failure(self) -> None:
        self.assertEqual(YtDlpDownloader.classify_stderr(
            "ERROR: something completely different"),
            REASON_DOWNLOAD_FAILED)


class TestYtDlpDownloaderWithFakeBinary(unittest.TestCase):
    def _fake_binary(self, directory: Path, exit_code: int = 0,
                     stderr: str = "") -> Path:
        script = directory / "yt-dlp"
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import shutil, sys\n"
            "from pathlib import Path\n"
            "here = Path(sys.argv[0]).parent\n"
            "here.joinpath('argv.txt').write_text(' '.join(sys.argv[1:]))\n"
            f"sys.stderr.write({stderr!r})\n"
            "for i, a in enumerate(sys.argv):\n"
            "    if a == '-o':\n"
            "        dest = sys.argv[i + 1].replace('%(ext)s', 'mp4')\n"
            f"        shutil.copyfile({str(FIXTURE)!r}, dest)\n"
            f"sys.exit({exit_code})\n",
            encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return script

    def test_fetch_uses_fixed_command_without_cookies_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary = self._fake_binary(tmp_path)
            downloader = YtDlpDownloader(binary=binary)
            self.assertTrue(downloader.available)
            dest = tmp_path / "dest"
            result = downloader.fetch(EXAMPLE_URL, dest)
            self.assertTrue(Path(result.path).is_file())
            self.assertEqual(result.downloader_name, "yt-dlp")
            argv = (tmp_path / "argv.txt").read_text(encoding="utf-8")
            self.assertIn("--no-playlist", argv)
            self.assertIn(EXAMPLE_URL, argv)
            self.assertNotIn("cookie", argv.lower())
            self.assertNotIn("--cookies", argv)
            self.assertNotIn("password", argv.lower())

    def test_failed_exit_maps_stderr_to_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary = self._fake_binary(
                tmp_path, exit_code=1,
                stderr="ERROR: Unsupported URL: https://example.com/x")
            downloader = YtDlpDownloader(binary=binary)
            with self.assertRaises(DownloadFailure) as ctx:
                downloader.fetch(EXAMPLE_URL, tmp_path / "dest")
            self.assertEqual(ctx.exception.reason, REASON_UNSUPPORTED_URL)

    def test_call_shape_compatible_with_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary = self._fake_binary(tmp_path)
            downloader = YtDlpDownloader(binary=binary)
            target = tmp_path / "download.bin"
            out = downloader(EXAMPLE_URL, target)
            self.assertEqual(out, target)
            self.assertTrue(target.is_file())
            self.assertEqual(sha256_file(target), sha256_file(FIXTURE))


class TestAsIngestDownloader(unittest.TestCase):
    def test_fetch_style_fake_adapts_to_ingest(self) -> None:
        assert FIXTURE.is_file()
        fake = FakeDownloader(FIXTURE)
        adapted = as_ingest_downloader(fake)
        with tempfile.TemporaryDirectory() as tmp:
            record = ingest_source(
                IngestRequest(source_url=EXAMPLE_URL,
                              authorization_type="SELLER_AUTHORIZED",
                              commercial_rights_confirmed=True),
                Path(tmp) / "store", downloader=adapted,
                downloader_name="fake-test")
        self.assertEqual(fake.calls, [EXAMPLE_URL])
        self.assertEqual(record.sha256, sha256_file(FIXTURE))

    def test_plain_callable_passes_through_unchanged(self) -> None:
        def _plain(url: str, target: Path) -> Path:
            return target
        self.assertIs(as_ingest_downloader(_plain), _plain)

    def test_failing_downloader_propagates_reason(self) -> None:
        failing = FailingDownloader(REASON_NETWORK_ERROR, "boom")
        adapted = as_ingest_downloader(failing)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(DownloadFailure) as ctx:
                adapted(EXAMPLE_URL, Path(tmp) / "download.bin")
        self.assertEqual(ctx.exception.reason, REASON_NETWORK_ERROR)
        self.assertEqual(failing.calls, [EXAMPLE_URL])


class TestOCRSeam(unittest.TestCase):
    def test_adapter_status_before_probe_is_honest(self) -> None:
        engine = DelegatingOCREngine()
        status = engine.status()
        self.assertFalse(status["available"])
        self.assertIn("not probed", status["detail"])

    def test_adapter_track_delegates_to_real_tracking(self) -> None:
        det = OCRDetection(text="你好", confidence=0.9,
                           polygon=[(10, 10), (50, 10), (50, 30), (10, 30)])
        by_time = {0.0: [det], 1.0: [det]}
        adapter = DelegatingOCREngine()
        expected = track_detections(by_time, (100, 100))
        got = adapter.track(by_time, (100, 100))
        self.assertEqual(len(got.regions), len(expected.regions))
        self.assertEqual(got.regions[0].original_text, "你好")

    def test_fake_returns_canned_and_records(self) -> None:
        det = OCRDetection(text="测试", confidence=0.8,
                           polygon=[(0, 0), (9, 0), (9, 9), (0, 9)])
        fake = FakeOCREngine({"frame.jpg": [det]})
        self.assertEqual(fake.recognize("frame.jpg"), [det])
        self.assertEqual(fake.recognize("other.jpg"), [])
        self.assertEqual(len(fake.calls), 2)
        self.assertTrue(fake.status()["available"])


class TestTTSSeam(unittest.TestCase):
    def test_adapter_exposes_real_presets(self) -> None:
        from ai_clip_studio.affiliate.voice import VOICE_PRESETS
        provider = VoiceTTSProvider()
        self.assertEqual(provider.presets, VOICE_PRESETS)
        self.assertIn("female_review", provider.presets)

    def test_adapter_preset_config_validates(self) -> None:
        from ai_clip_studio.affiliate.voice import VoiceError
        provider = VoiceTTSProvider()
        config = provider.preset_config("male_review")
        self.assertEqual(config.preset, "male_review")
        with self.assertRaises(VoiceError):
            provider.preset_config("no_such_preset")

    def test_fake_records_and_returns_paths(self) -> None:
        from ai_clip_studio.affiliate.schema import (
            AffiliateScript, ScriptSegment)
        script = AffiliateScript(
            variant="natural_review", target_seconds=30.0,
            segments=[ScriptSegment(segment_id="s1", section="HOOK",
                                    text="Xin chào"),
                      ScriptSegment(segment_id="s2", section="BENEFITS",
                                    text="Rất tốt")],
            approved=True)
        fake = FakeTTSProvider()
        with tempfile.TemporaryDirectory() as tmp:
            paths = fake.synthesize_script(script, Path(tmp),
                                           VoiceConfig())
        self.assertEqual(len(paths), 2)
        self.assertEqual(fake.synthesize_calls[0]["segment_count"], 2)
        preview = fake.preview(VoiceConfig(), Path(tmp) / "out")
        self.assertEqual(preview.name, "voice_preview.wav")
        self.assertEqual(len(fake.preview_calls), 1)


class TestGeminiSeam(unittest.TestCase):
    def _product(self) -> ProductInfo:
        return ProductInfo(product_name="Hộp đựng đồ")

    def _segments(self) -> list[dict]:
        return [{"start": 0.0, "end": 2.0, "text": "这个产品非常好用",
                 "speaker_id": "NGUOI_1"}]

    def test_unavailable_returns_review_flag_zero_segments(self) -> None:
        client = UnavailableGeminiClient()
        record = client.translate(self._segments(), self._product(),
                                  mode="DIRECT_TRANSLATION",
                                  style="humorous_viral_review")
        self.assertEqual(record.engine, "fallback")
        self.assertTrue(record.needs_human_review)
        self.assertEqual(record.translated_segments, [])
        self.assertEqual(record.rewritten_segments, [])
        self.assertEqual(len(record.original_segments), 1)
        self.assertEqual(record.original_segments[0]["speaker_id"],
                         "NGUOI_1")
        self.assertEqual(record.style, "humorous_viral_review")

    def test_unavailable_rejects_unknown_mode_style(self) -> None:
        client = UnavailableGeminiClient()
        with self.assertRaises(ValueError):
            client.translate(self._segments(), self._product(),
                             mode="NOPE")
        with self.assertRaises(ValueError):
            client.translate(self._segments(), self._product(),
                             style="nope")

    def test_translation_adapter_falls_back_without_key(self) -> None:
        # No key in the environment: translate_segments takes the
        # labelled fallback path and performs no HTTP call.
        with mock.patch.dict(os.environ):
            os.environ.pop("GEMINI_API_KEY", None)
            record = TranslationGeminiClient().translate(
                self._segments(), self._product(),
                mode="NATURAL_LOCALIZATION")
        self.assertEqual(record.engine, "fallback")
        self.assertTrue(record.needs_human_review)
        self.assertEqual(record.translated_segments, [])

    def test_fake_canned_and_unavailable_modes(self) -> None:
        fake = FakeGeminiClient(canned_texts=["Sản phẩm này rất tiện"])
        record = fake.translate(self._segments(), self._product())
        self.assertEqual(record.engine, "fake_test_only")
        self.assertEqual(record.translated_segments[0]["text"],
                         "Sản phẩm này rất tiện")
        self.assertEqual(fake.calls[0]["segment_count"], 1)
        plain = FakeGeminiClient()
        record2 = plain.translate(self._segments(), self._product())
        self.assertEqual(record2.translated_segments, [])
        self.assertTrue(record2.needs_human_review)


class TestRegistry(unittest.TestCase):
    def test_all_four_seams_registered(self) -> None:
        providers = list_providers()
        self.assertEqual(set(providers), {"downloader", "ocr", "tts",
                                          "gemini"})
        for seam, names in providers.items():
            self.assertTrue(names, seam)

    def test_defaults_resolve_to_real_implementations(self) -> None:
        self.assertIsInstance(get_provider("downloader"),
                              YtDlpDownloader)
        self.assertIsInstance(get_provider("ocr"), DelegatingOCREngine)
        self.assertIsInstance(get_provider("tts"), VoiceTTSProvider)
        # Gemini default is the labelled-unavailable client while no
        # key exists — never a real call, never fabricated output.
        self.assertIsInstance(get_provider("gemini"),
                              UnavailableGeminiClient)

    def test_fakes_usable_in_tests(self) -> None:
        self.assertIsInstance(get_provider("ocr", "fake"), FakeOCREngine)
        self.assertIsInstance(get_provider("tts", "fake"), FakeTTSProvider)
        self.assertIsInstance(get_provider("gemini", "fake"),
                              FakeGeminiClient)
        self.assertIsInstance(get_provider("gemini",
                                           "translation_adapter"),
                              TranslationGeminiClient)

    def test_unknown_seam_or_name_raises_with_listing(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            get_provider("nope")
        self.assertIn("downloader", str(ctx.exception))
        with self.assertRaises(KeyError):
            get_provider("tts", "nope")


if __name__ == "__main__":
    unittest.main()
