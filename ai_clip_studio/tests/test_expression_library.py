"""Tests for ai_clip_studio/expression_library.py."""
from __future__ import annotations

import unittest

from ai_clip_studio.animation.character_art import EXPRESSIONS
from ai_clip_studio.expression_library import (
    NEGATION_WORDS,
    blink_envelope,
    blend,
    gaze_for_target,
    interpret,
    interpret_detailed,
    interpret_params,
    params_at,
    speech_mouth_envelope,
)


class TestBaseExpressions(unittest.TestCase):
    def test_eight_bases_reused_not_duplicated(self):
        from ai_clip_studio import expression_library as lib
        self.assertIs(lib.EXPRESSIONS, EXPRESSIONS)
        self.assertEqual(len(EXPRESSIONS), 8)
        for name in ("neutral", "happy", "sad", "surprised", "worried",
                     "angry", "thinking", "doubtful"):
            self.assertIn(name, EXPRESSIONS)

    def test_blend_endpoints(self):
        # Float arithmetic: a + (b - a) * 1.0 is not bit-identical
        # to b, so endpoints are compared per parameter.
        for key in EXPRESSIONS["happy"]:
            self.assertAlmostEqual(
                blend("happy", "sad", 0.0)[key],
                EXPRESSIONS["happy"][key])
            self.assertAlmostEqual(
                blend("happy", "sad", 1.0)[key],
                EXPRESSIONS["sad"][key])

    def test_blend_midpoint_averages(self):
        mid = blend("happy", "sad", 0.5)
        for key in EXPRESSIONS["happy"]:
            expected = (EXPRESSIONS["happy"][key]
                        + EXPRESSIONS["sad"][key]) / 2.0
            self.assertAlmostEqual(mid[key], expected)

    def test_blend_clamps(self):
        for key in EXPRESSIONS["happy"]:
            self.assertAlmostEqual(
                blend("happy", "sad", -1.0)[key],
                EXPRESSIONS["happy"][key])
            self.assertAlmostEqual(
                blend("happy", "sad", 2.0)[key],
                EXPRESSIONS["sad"][key])

    def test_blend_rejects_unknown(self):
        with self.assertRaises(ValueError):
            blend("happy", "ecstatic", 0.5)


class TestInterpret(unittest.TestCase):
    def test_base_labels(self):
        cases = {
            "happy": "happy",
            "Thoughtful": "thinking",
            "Disappointed": "sad",
            "Uncertain": "doubtful",
            "Focused": "thinking",
            "Determined": "angry",
            "Curious": "surprised",
            "Deadpan": "neutral",
            "Hopeful, naive": "happy",
            "Skeptical": "doubtful",
            "Tired, serious": "sad",
            "Exhausted": "sad",
            "Fear, exhaustion": "worried",
            "Grim, reflective": "sad",
            "vui vẻ": "happy",
            "buồn": "sad",
            "giật mình": "surprised",
            "sững sờ": "surprised",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(interpret(text), expected)

    def test_unknown_returns_none(self):
        self.assertIsNone(interpret("màu xanh lá cây"))
        self.assertIsNone(interpret(""))
        self.assertIsNone(interpret(None))

    def test_negation_words_documented(self):
        for word in ("không", "chẳng", "chưa", "đừng", "never", "not"):
            self.assertIn(word, NEGATION_WORDS)

    def test_negation_never_maps_to_target(self):
        cases = {
            "không sợ": "worried",
            "chẳng vui": "happy",
            "không hề giận": "angry",
            "không buồn": "sad",
            "not happy": "happy",
            "never angry": "angry",
        }
        for text, target in cases.items():
            with self.subTest(text=text):
                detail = interpret_detailed(text)
                self.assertNotEqual(detail["expression"], target)
                self.assertTrue(detail["negated"])
                self.assertEqual(detail["expression"], "neutral")

    def test_negation_reported(self):
        detail = interpret_detailed("không sợ")
        self.assertEqual(detail["expression"], "neutral")
        self.assertTrue(detail["negated"])

    def test_legitimate_negation_phrase_still_maps(self):
        # "không chắc" (unsure) IS the doubtful expression, not a
        # negation of it.
        self.assertEqual(interpret("không chắc"), "doubtful")
        detail = interpret_detailed("không chắc")
        self.assertFalse(detail["negated"])

    def test_later_unnegated_keyword_wins(self):
        self.assertEqual(interpret("không sợ mà còn vui"), "happy")

    def test_interpret_params_returns_blend(self):
        params = interpret_params("Hopeful, naive")
        self.assertIsNotNone(params)
        # Hopeful blends happy/neutral at 0.5.
        for key in EXPRESSIONS["happy"]:
            expected = (EXPRESSIONS["happy"][key]
                        + EXPRESSIONS["neutral"][key]) / 2.0
            self.assertAlmostEqual(params[key], expected)

    def test_interpret_params_unknown_returns_none(self):
        self.assertIsNone(interpret_params("màu xanh lá cây"))


class TestEnvelopes(unittest.TestCase):
    def test_blink_envelope(self):
        self.assertEqual(blink_envelope(0.5, []), 1.0)
        # The dip bottoms out at the blink midpoint (start + 0.06 s),
        # not at the start: the eye closes, then reopens.
        self.assertEqual(blink_envelope(1.0, [1.0]), 1.0)
        self.assertAlmostEqual(blink_envelope(1.06, [1.0]), 0.1)
        self.assertEqual(blink_envelope(1.5, [1.0]), 1.0)
        # Between blinks the eye is open.
        self.assertEqual(blink_envelope(1.3, [1.0, 2.0]), 1.0)

    def test_speech_envelope_zero_outside(self):
        segments = [{"start": 1.0, "end": 2.0}]
        self.assertEqual(speech_mouth_envelope(0.5, segments), 0.0)
        self.assertEqual(speech_mouth_envelope(2.5, segments), 0.0)
        self.assertEqual(speech_mouth_envelope(1.5, []), 0.0)

    def test_speech_envelope_ramps_and_oscillates(self):
        segments = [{"start": 1.0, "end": 2.0}]
        self.assertEqual(speech_mouth_envelope(1.0, segments), 0.0)
        mid = speech_mouth_envelope(1.5, segments)
        self.assertGreater(mid, 0.0)
        self.assertLessEqual(mid, 1.0)
        values = [speech_mouth_envelope(1.0 + 0.05 * i, segments)
                  for i in range(20)]
        self.assertGreater(max(values), min(values))

    def test_speech_envelope_word_gating(self):
        segments = [{"start": 1.0, "end": 2.0,
                     "words": [(1.0, 1.4), (1.6, 2.0)]}]
        self.assertEqual(speech_mouth_envelope(1.5, segments), 0.0)
        self.assertGreater(speech_mouth_envelope(1.2, segments), 0.0)

    def test_params_at_combines_expression_blink_and_speech(self):
        keyframes = [(0.0, "sad"), (10.0, "sad")]
        segments = [{"start": 1.0, "end": 2.0}]
        params = params_at(keyframes, 1.5, speech_segments=segments,
                           blink_times=[5.0])
        self.assertEqual(params["eye_h"], EXPRESSIONS["sad"]["eye_h"])
        self.assertGreaterEqual(params["mouth_open"],
                                EXPRESSIONS["sad"]["mouth_open"])
        blinked = params_at(keyframes, 5.06, speech_segments=None,
                            blink_times=[5.0])
        self.assertAlmostEqual(
            blinked["eye_h"], EXPRESSIONS["sad"]["eye_h"] * 0.1)


class TestGaze(unittest.TestCase):
    def test_gaze_for_target(self):
        gaze = gaze_for_target((0.0, 0.0), (100.0, 0.0))
        self.assertGreater(gaze[0], 0.0)
        self.assertEqual(gaze[1], 0.0)
        self.assertEqual(gaze_for_target((0.0, 0.0), (0.0, 0.0)),
                         (0.0, 0.0))

    def test_gaze_clamped(self):
        gaze = gaze_for_target((0.0, 0.0), (10000.0, 0.0))
        self.assertLessEqual(abs(gaze[0]), 1.0)


if __name__ == "__main__":
    unittest.main()
