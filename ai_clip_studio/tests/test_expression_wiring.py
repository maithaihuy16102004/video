"""Per-character EXPRESSION wiring (round-2 maximum-detail review).

A V1 EXPRESSION field naming characters ("Cronus suspicious, Rhea
worried", "Bà Tư: lo lắng") must reach THOSE characters' faces --
not the speaker's, and not one mangled label for everyone. Before
this wiring, the adapter mapped the whole string to a single label
and attached it to the shot's spoken lines, so Zeus rendered
"angry" from "Zeus amused, Cronus furious" while Cronus stayed
neutral, and every non-speaking character rendered neutral in
every shot (the tester's "ONE neutral expression only" finding).
"""

import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import (
    _character_index, compile_actions,
    compile_shot_character_expressions)
from ai_clip_studio.expression_library import (
    interpret, parse_character_expressions)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.trait_derivation import map_expression_text

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent.parent / "examples"


def _norm(text):
    return " ".join(str(text or "").lower().split())


def _zeus_package():
    text = (EXAMPLES / "zeus_ep01_fall_of_cronus.studio.md").read_text(
        encoding="utf-8")
    return adapt_document(parse_studio_script_v1(text))


class TestParseCharacterExpressions(unittest.TestCase):
    KEYS = {"cronus": "CHAR_CRONUS", "rhea": "CHAR_RHEA",
            "zeus": "CHAR_ZEUS", "anh minh": "CHAR_MINH",
            "minh": "CHAR_MINH2"}

    def test_colon_form(self):
        self.assertEqual(
            parse_character_expressions("Cronus: suspicious", self.KEYS,
                                        _norm),
            {"CHAR_CRONUS": "suspicious"})

    def test_comma_form_two_characters(self):
        self.assertEqual(
            parse_character_expressions(
                "Cronus suspicious, Rhea worried", self.KEYS, _norm),
            {"CHAR_CRONUS": "suspicious", "CHAR_RHEA": "worried"})

    def test_comma_form_case_insensitive(self):
        self.assertEqual(
            parse_character_expressions(
                "ZEUS amused, cronus FURIOUS", self.KEYS, _norm),
            {"CHAR_ZEUS": "amused", "CHAR_CRONUS": "furious"})

    def test_longest_name_wins(self):
        # "Anh Minh" must beat the shorter key "Minh".
        self.assertEqual(
            parse_character_expressions("Anh Minh vui vẻ, Zeus calm",
                                        self.KEYS, _norm),
            {"CHAR_MINH": "vui vẻ", "CHAR_ZEUS": "calm"})

    def test_single_segment_named_form(self):
        self.assertEqual(
            parse_character_expressions("Cronus satisfied", self.KEYS,
                                        _norm),
            {"CHAR_CRONUS": "satisfied"})
        self.assertEqual(
            parse_character_expressions("Zeus astonished", self.KEYS,
                                        _norm),
            {"CHAR_ZEUS": "astonished"})

    def test_single_segment_unmappable_remainder_is_bare(self):
        # The remainder must interpret: "Grace under pressure"
        # stays bare even when "Grace" is a declared character.
        keys = dict(self.KEYS, grace="CHAR_GRACE")
        self.assertIsNone(parse_character_expressions(
            "Grace under pressure", keys, _norm))
        self.assertIsNone(parse_character_expressions(
            "Zeus confident", self.KEYS, _norm))

    def test_bare_form_returns_none(self):
        self.assertIsNone(parse_character_expressions(
            "Deadpan", self.KEYS, _norm))
        self.assertIsNone(parse_character_expressions(
            "Paranoid confidence", self.KEYS, _norm))

    def test_unknown_name_returns_none(self):
        self.assertIsNone(parse_character_expressions(
            "Zeus happy, Poseidon annoyed", self.KEYS, _norm))

    def test_unnamed_segment_returns_none(self):
        self.assertIsNone(parse_character_expressions(
            "Cronus suspicious, feeling blue", self.KEYS, _norm))

    def test_duplicate_character_returns_none(self):
        self.assertIsNone(parse_character_expressions(
            "Zeus happy, Zeus sad", self.KEYS, _norm))

    def test_name_without_remainder_returns_none(self):
        self.assertIsNone(parse_character_expressions(
            "Cronus, Rhea worried", self.KEYS, _norm))
        self.assertIsNone(parse_character_expressions(
            "Cronus:", self.KEYS, _norm))

    def test_empty_and_no_keys(self):
        self.assertIsNone(parse_character_expressions("", self.KEYS,
                                                      _norm))
        self.assertIsNone(parse_character_expressions(
            "Cronus suspicious, Rhea worried", {}, _norm))


class TestExpressionSynonyms(unittest.TestCase):
    # Plain synonyms of existing families (real script words that
    # previously mapped to nothing, leaving faces neutral).
    CASES = [("amused", "happy"), ("annoyed", "angry"),
             ("satisfied", "happy"), ("defeated", "sad"),
             ("unimpressed", "doubtful")]

    def test_interpret(self):
        for word, expected in self.CASES:
            with self.subTest(word=word):
                self.assertEqual(interpret(word), expected)

    def test_map_expression_text_agrees(self):
        for word, expected in self.CASES:
            with self.subTest(word=word):
                self.assertEqual(map_expression_text(word), expected)


class TestCompileShotCharacterExpressions(unittest.TestCase):
    def test_zeus_named_shots(self):
        package = _zeus_package()
        char_map, _extras = _character_index(package)
        result = compile_shot_character_expressions(package, char_map)
        self.assertEqual(
            {k: v["expression"]
             for k, v in result["SC01_SH02"]["entries"].items()},
            {"CHAR_CRONUS": "doubtful", "CHAR_RHEA": "worried"})
        self.assertEqual(
            {k: v["expression"]
             for k, v in result["SC06_SH04"]["entries"].items()},
            {"CHAR_ZEUS": "happy", "CHAR_CRONUS": "angry"})
        self.assertEqual(
            {k: v["expression"]
             for k, v in result["SC08_SH03"]["entries"].items()},
            {"CHAR_ZEUS": "happy", "CHAR_POSEIDON": "angry"})
        self.assertEqual(
            {k: v["expression"]
             for k, v in result["SC10_SH04"]["entries"].items()},
            {"CHAR_ZEUS": "worried", "CHAR_HERA": "doubtful"})
        # Bare-form shots carry no per-character entry: no target
        # is ever guessed.
        self.assertNotIn("SC01_SH01", result)
        self.assertNotIn("SC06_SH01", result)

    def test_ep1_has_no_named_forms(self):
        text = (EXAMPLES / "hitler_ep01_munich_1914.studio.md").read_text(
            encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(text))
        char_map, _extras = _character_index(package)
        self.assertEqual(
            compile_shot_character_expressions(package, char_map), {})

    def test_scene_entries_govern_all_shots_shot_wins(self):
        package = {"scenes": [{"number": 1, "v1_scene": {
            "number": 1,
            "expressions": [{"character": None,
                             "expression": "A sad, B angry",
                             "line": 10}],
            "shots": [
                {"id": "SC01_SH01", "expression": "A happy",
                 "line": 20},
                {"id": "SC01_SH02", "expression": None,
                 "line": 30},
            ]}}]}
        char_map = {"a": "CHAR_A", "b": "CHAR_B"}
        result = compile_shot_character_expressions(package, char_map)
        # SH01: shot-level "A happy" overrides the scene's "A sad";
        # B keeps the scene value. SH02 keeps both scene values.
        self.assertEqual(
            {k: v["expression"]
             for k, v in result["SC01_SH01"]["entries"].items()},
            {"CHAR_A": "happy", "CHAR_B": "angry"})
        self.assertEqual(
            {k: v["expression"]
             for k, v in result["SC01_SH02"]["entries"].items()},
            {"CHAR_A": "sad", "CHAR_B": "angry"})

    def test_unmappable_remainder_drops_only_that_character(self):
        package = {"scenes": [{"number": 1, "v1_scene": {
            "number": 1, "expressions": [],
            "shots": [{"id": "SC01_SH01",
                       "expression": "A confident, B furious",
                       "line": 5}]}}]}
        char_map = {"a": "CHAR_A", "b": "CHAR_B"}
        result = compile_shot_character_expressions(package, char_map)
        self.assertEqual(
            {k: v["expression"]
             for k, v in result["SC01_SH01"]["entries"].items()},
            {"CHAR_B": "angry"})


def _injected_garden_text():
    text = (FIXTURES / "unseen_garden_key.studio.md").read_text(
        encoding="utf-8")
    anchor1 = ("SHOT: SC01_SH01\nCAMERA: Medium shot, bà Tư ở trung "
               "tâm khung hình\nCAMERA_MOVEMENT: STATIC\n")
    assert text.count(anchor1) == 1
    text = text.replace(
        anchor1,
        anchor1 + "EXPRESSION: Bà Tư lo lắng, Bé Nam tò mò\n")
    anchor_action = "* Bà Tư hơi cúi đầu suy nghĩ."
    assert text.count(anchor_action) == 1
    text = text.replace(
        anchor_action,
        anchor_action + "\n* Bà Tư giữ vẻ bình tĩnh.")
    anchor2 = ("SHOT: SC01_SH02\nCAMERA: Close-up, bàn tay bà Tư\n"
               "CAMERA_MOVEMENT: STATIC\n")
    assert text.count(anchor2) == 1
    text = text.replace(anchor2, anchor2 + "EXPRESSION: Bà Tư: lo lắng\n")
    anchor3 = ("SHOT: SC01_SH03\nCAMERA: Medium shot, bà Tư và cổng "
               "sắt\nCAMERA_MOVEMENT: STATIC\n")
    assert text.count(anchor3) == 1
    text = text.replace(anchor3, anchor3 + "EXPRESSION: Buồn\n")
    return text


def _compile_injected():
    from ai_clip_studio.product_renderer import plan_shots
    package = adapt_document(
        parse_studio_script_v1(_injected_garden_text()))
    shots = plan_shots(
        package,
        [{"line_index": i + 1, "duration": 3.0} for i in range(5)])
    spans, clock = {}, 0.0
    for shot in shots:
        did = shot.get("directive_shot_id")
        if did:
            span = spans.setdefault(str(did), [clock, clock])
            span[1] = clock + float(shot["duration"])
        clock += float(shot["duration"])
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    return package, shots, spans, events, unsupported


class TestExpressionHoldEvents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (cls.package, cls.shots, cls.spans, cls.events,
         cls.unsupported) = _compile_injected()

    def _shot_events(self, shot_id):
        return [e for e in self.events if e.get("shot_id") == shot_id]

    def test_comma_form_emits_one_event_per_character(self):
        exprs = [e for e in self._shot_events("SC01_SH01")
                 if e["action_id"].endswith("_EXPR_CHAR_GARDENER")
                 or e["action_id"].endswith("_EXPR_CHAR_BOY")]
        by_actor = {e["actor_id"]: e for e in exprs}
        self.assertEqual(set(by_actor), {"CHAR_GARDENER", "CHAR_BOY"})
        self.assertEqual(by_actor["CHAR_GARDENER"]["expression"],
                         "worried")
        self.assertEqual(by_actor["CHAR_BOY"]["expression"],
                         "surprised")

    def test_colon_form_emits_one_event(self):
        exprs = [e for e in self._shot_events("SC01_SH02")
                 if "_EXPR_" in e["action_id"]]
        self.assertEqual(len(exprs), 1)
        self.assertEqual(exprs[0]["actor_id"], "CHAR_GARDENER")
        self.assertEqual(exprs[0]["expression"], "worried")

    def test_bare_form_emits_no_event(self):
        exprs = [e for e in self._shot_events("SC01_SH03")
                 if "_EXPR_" in e["action_id"]]
        self.assertEqual(exprs, [])

    def test_shot_span_and_provenance(self):
        event = next(e for e in self._shot_events("SC01_SH01")
                     if e["action_id"].endswith("_EXPR_CHAR_GARDENER"))
        span = self.spans["SC01_SH01"]
        self.assertEqual(event["start_time"], round(span[0], 3))
        self.assertEqual(event["end_time"], round(span[1], 3))
        self.assertEqual(event["action_type"], "EXPRESSION_HOLD")
        self.assertEqual(
            event["required_pose"]["primitive"], "face_only")
        self.assertEqual(
            event["required_pose"]["params"]["expression"], "worried")
        self.assertIsNone(event["semantic_action_type"])
        self.assertEqual(event["action_origin"],
                         "EXPLICIT_SCRIPT_ACTION")
        self.assertEqual(event["animation_dependencies"], [])
        self.assertEqual(event["span_source"], "supplied")
        self.assertIn("EXPRESSION field",
                      event["inference_reason"])

    def test_sentence_event_precedes_shot_span_event(self):
        shot_events = self._shot_events("SC01_SH01")
        sentence_idx = next(
            i for i, e in enumerate(shot_events)
            if e["action_type"] == "EXPRESSION_HOLD"
            and "_EXPR_" not in e["action_id"])
        span_idx = next(
            i for i, e in enumerate(shot_events)
            if "_EXPR_" in e["action_id"])
        self.assertLess(sentence_idx, span_idx)

    def test_adapter_skips_line_attachment_for_named_forms(self):
        lines = {ln["line_id"]: ln for sc in self.package["scenes"]
                 for ln in sc["lines"]}
        # Named forms: no mangled single label on the lines.
        self.assertNotIn("expression", lines["TESTE_001"])
        self.assertNotIn("expression", lines["TESTE_002"])
        # Bare form: the line path still owns it.
        self.assertEqual(lines["TESTE_003"]["expression"], "sad")

    def test_default_expression_carried(self):
        by_name = {c["name"]: c for c in self.package["characters"]}
        self.assertEqual(by_name["Bà Tư"]["default_expression"],
                         "Hiền hậu")
        self.assertEqual(by_name["Bé Nam"]["default_expression"],
                         "Tò mò")


class TestRendererDefaultExpression(unittest.TestCase):
    def test_non_speakers_render_their_defaults(self):
        from ai_clip_studio import product_renderer as pr
        from ai_clip_studio.product_renderer import (
            _render_shot, plan_shots)
        import tempfile
        package = _zeus_package()
        shots = plan_shots(
            package,
            [{"line_index": i + 1, "duration": 3.0} for i in range(40)])
        for i, shot in enumerate(shots):
            shot["index"] = i
        spans, clock = {}, 0.0
        for shot in shots:
            did = shot.get("directive_shot_id")
            if did:
                span = spans.setdefault(str(did), [clock, clock])
                span[1] = clock + float(shot["duration"])
            clock += float(shot["duration"])
        events, unsupported = compile_actions(
            package, timeline={"spans": spans})
        package["compiled_actions"] = {
            "events": events, "unsupported": unsupported,
            "spans_supplied": True, "compile_error": None}
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC01_SH01")
        seen = {}
        orig = pr.draw_character_v4

        def spy(draw, char, expression="neutral", **kw):
            seen.setdefault(getattr(char, "name", "?"), set()).add(
                expression if isinstance(expression, str)
                else "dict")
            return orig(draw, char, expression=expression, **kw)

        pr.draw_character_v4 = spy
        try:
            with tempfile.TemporaryDirectory() as tmp:
                _render_shot({"shot": shot, "package": package,
                              "out_dir": tmp})
        finally:
            pr.draw_character_v4 = orig
        # Cronus: "Suspicious, arrogant" -> doubtful. Rhea:
        # "Caring, worried, determined" -> worried. Neither speaks
        # in this shot, so only the default fallback can give them
        # these faces.
        self.assertIn("doubtful", seen.get("Cronus", set()))
        self.assertIn("worried", seen.get("Rhea", set()))


if __name__ == "__main__":
    unittest.main()
