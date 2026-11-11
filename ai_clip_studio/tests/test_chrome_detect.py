"""Tests for Chrome auto-detection (ai_clip_studio/chrome_detect.py)."""
import os
import unittest

from ai_clip_studio import chrome_detect
from ai_clip_studio.upstream import check_render_available


class TestChromeDetect(unittest.TestCase):
    def test_detect_chrome_returns_tuple(self):
        path, detail = chrome_detect.detect_chrome()
        self.assertIsInstance(detail, str)
        self.assertTrue(detail)
        # On this VM the only candidate refuses to launch, so no path.
        self.assertIsNone(path)
        self.assertIn("Hatch WebGL domain policy", detail)

    def test_probe_rejects_nonexistent_binary(self):
        ok, detail = chrome_detect._probe("/nonexistent/chrome")
        self.assertFalse(ok)

    def test_env_override_is_tried(self):
        os.environ["CHROME_PATH"] = "/nonexistent/chrome"
        try:
            path, detail = chrome_detect.detect_chrome()
            self.assertIsNone(path)
            self.assertIn("/nonexistent/chrome", detail)
        finally:
            del os.environ["CHROME_PATH"]

    def test_check_render_available_reports_fallback(self):
        ok, detail = check_render_available()
        self.assertFalse(ok)
        self.assertIn("frame-by-frame", detail)


if __name__ == "__main__":
    unittest.main()
