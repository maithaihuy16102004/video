"""Tests for the deterministic fallback planner (shared engine)."""
import unittest

from ai_clip_studio.planner_fallback import deterministic_planner

REAL_SCRIPT = "/home/hatch/workspace/acceptance_loop/test_chiec_vi_trong_mua/script.txt"


class TestPlannerFallback(unittest.TestCase):
    def test_real_script_package(self):
        text = open(REAL_SCRIPT, encoding="utf-8").read()
        pkg = deterministic_planner(text)
        chars = {c["name"]: c for c in pkg["characters"]}
        self.assertEqual(set(chars), {"Minh", "Lan"})
        self.assertEqual(chars["Minh"]["jacket_color"], "#1d3a5f")
        self.assertEqual(chars["Lan"]["jacket_color"], "#c9b18c")
        self.assertEqual(len(pkg["scenes"]), 4)
        self.assertEqual(len(pkg["locations"]), 4)
        # one action lead-in shot per scene + one shot per spoken line
        self.assertEqual(len(pkg["shots"]), 4 + 10)
        # action leads are bounded: scene 1 must not charge for a bus
        # that only appears as a location word
        self.assertLess(pkg["scenes"][0]["action_lead_sec"], 6.0)
        # scene 4 DOES charge for the arriving bus
        self.assertGreater(pkg["scenes"][3]["action_lead_sec"], 8.0)

    def test_other_script_not_hardcoded(self):
        text = open("/home/hatch/workspace/video-16x9-v2/ai_clip_studio/tests/test_vi_script_parser.py",
                    encoding="utf-8").read()
        # the OTHER_SCRIPT constant lives in the parser test module
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "t", "/home/hatch/workspace/video-16x9-v2/ai_clip_studio/tests/test_vi_script_parser.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        pkg = deterministic_planner(mod.OTHER_SCRIPT)
        self.assertEqual(len(pkg["scenes"]), 2)
        self.assertEqual({c["name"] for c in pkg["characters"]}, {"Hùng", "Mai"})


if __name__ == "__main__":
    unittest.main()
