"""Tests for the general scale-variant rule (Zeus Ep1 fallback).

The parser's head-ratio lock (0.33-0.35) is deliberately NOT relaxed:
an out-of-range HEAD_RATIO stays V1E009 (pinned by
test_only_head_ratio_lock_error). Production may still render a
document whose ONLY validation errors are V1E009, when every
out-of-range character declares a HEIGHT_RATIO* scale trait (SPEC
§5.1): head_ratio clamps to 0.34, the body scales, and the deviation
is recorded. The renderer multiplies drawn height by the package
scale_ratio (default 1.0, byte-identical).

All fixtures below are synthetic grammar shapes with invented names;
no story content is asserted. The real Zeus script is verified by
probe, not by these tests.
"""
from __future__ import annotations

import copy
import tempfile
import unittest

import numpy as np
from PIL import Image

from ai_clip_studio.camera_planner import viewpoint_for_shot
from ai_clip_studio.product_renderer import (
    CAM, CHAR_H, H, W, _render_shot, char_metrics, plan_shots,
)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import (
    ADAPTER_LABEL,
    V1AdapterError,
    _parse_scale_ratio,
    _scale_ratio_from_fields,
    _scale_variant_deviations,
    adapt_document,
    resolve_v1_plan,
)

FACE_FILL = (247, 243, 232)


def _make_script(characters, extra_blocks="", extra_scene=""):
    """Minimal V1 document. characters: (name, head_ratio|None,
    height_ratio|None) — values are raw script strings."""
    blocks = ["# STUDIO SCRIPT V1", "PROJECT: TEST_SCALE", ""]
    for name, head, height in characters:
        blocks.append(f"CHARACTER: {name}")
        blocks.append("ROLE: Nhân vật thử nghiệm")
        if head is not None:
            blocks.append(f"HEAD_RATIO: {head}")
        if height is not None:
            blocks.append(f"HEIGHT_RATIO_TO_ADULT: {height}")
        blocks.append("VOICE: AUTO")
        blocks.append("")
    if extra_blocks:
        blocks.append(extra_blocks)
        blocks.append("")
    blocks += [
        "SCENE 1: Quảng trường",
        "LOCATION: Quảng trường",
        "VISUAL: Quảng trường rộng.",
        "ACTION: Mọi người đứng yên.",
        "",
        "SHOT SH01:",
        "TYPE: ESTABLISHING",
        f"SUBJECT: {characters[0][0]}",
        "",
        "NARRATION: Một ngày bình thường.",
    ]
    if extra_scene:
        blocks.append(extra_scene)
    blocks += ["END_SCENE", "END_SCRIPT", ""]
    return "\n".join(blocks)


def _parse_errors(text):
    doc = parse_studio_script_v1(text)
    return doc, [(e.line, e.code) for e in doc.validation_errors]


class TestParseScaleRatio(unittest.TestCase):
    def test_numeric_and_string_forms(self):
        self.assertEqual(_parse_scale_ratio("1.8"), 1.8)
        self.assertEqual(_parse_scale_ratio("1.8x"), 1.8)
        self.assertEqual(_parse_scale_ratio("1.8X"), 1.8)
        self.assertEqual(_parse_scale_ratio("  1.8 x "), 1.8)
        self.assertEqual(_parse_scale_ratio(1.8), 1.8)
        self.assertEqual(_parse_scale_ratio(2), 2.0)
        self.assertEqual(_parse_scale_ratio("0.2"), 0.2)
        self.assertEqual(_parse_scale_ratio("3.0"), 3.0)

    def test_rejected_values(self):
        for bad in ("abc", "", "0", "-1", "0.1", "3.5", "5.0", "nan",
                    "inf", "-inf", None, True, ["1.8"], {"v": 1.8}):
            with self.subTest(value=bad):
                self.assertIsNone(_parse_scale_ratio(bad))


class TestScaleRatioFromFields(unittest.TestCase):
    def test_first_parseable_height_ratio_key(self):
        ratio, key = _scale_ratio_from_fields(
            {"HEIGHT_RATIO_A": "khổng lồ",
             "HEIGHT_RATIO_TO_ADULT": "1.5"})
        self.assertEqual((ratio, key), (1.5, "HEIGHT_RATIO_TO_ADULT"))

    def test_key_matching_is_case_insensitive(self):
        ratio, key = _scale_ratio_from_fields({"height_ratio_x": "2"})
        self.assertEqual((ratio, key), (2.0, "height_ratio_x"))

    def test_absent_and_non_dict(self):
        self.assertEqual(_scale_ratio_from_fields({"ROLE": "x"}),
                         (None, None))
        self.assertEqual(_scale_ratio_from_fields({}), (None, None))
        self.assertEqual(_scale_ratio_from_fields(None), (None, None))
        self.assertEqual(_scale_ratio_from_fields("HEIGHT_RATIO 1.8"),
                         (None, None))


class TestScaleVariantDeviations(unittest.TestCase):
    def _data(self, chars):
        return {"characters": chars}

    def test_all_v1e009_with_traits_proceeds(self):
        data = self._data([{
            "name": "Khổng Lồ", "identity_id": "C1",
            "head_ratio": 0.30,
            "fields": {"HEIGHT_RATIO_TO_ADULT": "1.8"}}])
        devs = _scale_variant_deviations(
            data, [{"line": 10, "code": "V1E009", "message": "m"}])
        self.assertEqual(len(devs), 1)
        self.assertEqual(devs[0]["character"], "Khổng Lồ")
        self.assertEqual(devs[0]["declared_head_ratio"], 0.30)
        self.assertEqual(devs[0]["rendered_head_ratio"], 0.34)
        self.assertEqual(devs[0]["scale_ratio"], 1.8)
        self.assertEqual(devs[0]["error_line"], 10)

    def test_global_error_refuses(self):
        # A V1E009 with NO out-of-range character (e.g. global
        # VISUAL_STYLE HEAD_RATIO) must not proceed.
        data = self._data([{
            "name": "Thường", "identity_id": "C1", "head_ratio": 0.34,
            "fields": {}}])
        self.assertIsNone(_scale_variant_deviations(
            data, [{"line": 5, "code": "V1E009", "message": "m"}]))

    def test_count_mismatch_refuses(self):
        data = self._data([{
            "name": "Khổng Lồ", "identity_id": "C1",
            "head_ratio": 0.30,
            "fields": {"HEIGHT_RATIO_TO_ADULT": "1.8"}}])
        self.assertIsNone(_scale_variant_deviations(data, [
            {"line": 10, "code": "V1E009", "message": "m"},
            {"line": 20, "code": "V1E009", "message": "m"}]))

    def test_mixed_codes_refuse(self):
        data = self._data([{
            "name": "Khổng Lồ", "identity_id": "C1",
            "head_ratio": 0.30,
            "fields": {"HEIGHT_RATIO_TO_ADULT": "1.8"}}])
        self.assertIsNone(_scale_variant_deviations(data, [
            {"line": 10, "code": "V1E009", "message": "m"},
            {"line": 11, "code": "V1E001", "message": "m"}]))

    def test_empty_errors_and_bad_values(self):
        data = self._data([{"name": "A", "head_ratio": 0.34,
                            "fields": {}}])
        self.assertIsNone(_scale_variant_deviations(data, []))
        bad = self._data([{"name": "A", "head_ratio": "abc",
                           "fields": {}}])
        self.assertIsNone(_scale_variant_deviations(
            bad, [{"line": 1, "code": "V1E009", "message": "m"}]))


class TestParserStillRefuses(unittest.TestCase):
    """Regression guard for the Stage 3 pin: the parser itself is
    untouched — an out-of-range HEAD_RATIO stays invalid."""

    def test_out_of_range_stays_v1e009(self):
        text = _make_script([("Người Khổng Lồ", "0.30", "1.8")])
        doc, errors = _parse_errors(text)
        self.assertFalse(doc.is_valid)
        self.assertEqual([c for _, c in errors], ["V1E009"])
        head_line = next(
            i for i, line in enumerate(text.splitlines(), 1)
            if line.startswith("HEAD_RATIO:"))
        self.assertEqual(errors[0][0], head_line)
        self.assertEqual(doc.characters[0].head_ratio, 0.30)


class TestAdapterProceeds(unittest.TestCase):
    def test_one_scale_character(self):
        text = _make_script([("Người Khổng Lồ", "0.30", "1.8"),
                             ("Người Thường", None, None)])
        package, label, detail = resolve_v1_plan(text)
        self.assertEqual(label, ADAPTER_LABEL)
        by_name = {c["name"]: c for c in package["characters"]}
        giant = by_name["Người Khổng Lồ"]
        self.assertEqual(giant["head_ratio"], 0.34)
        self.assertEqual(giant["scale_ratio"], 1.8)
        self.assertEqual(giant["height_px"], 972)
        self.assertIsNone(by_name["Người Thường"]["scale_ratio"])
        devs = package["v1_scale_deviations"]
        self.assertEqual(len(devs), 1)
        self.assertEqual(devs[0]["declared_head_ratio"], 0.30)
        self.assertEqual(devs[0]["rendered_head_ratio"], 0.34)
        self.assertEqual(devs[0]["scale_ratio"], 1.8)
        self.assertEqual(devs[0]["scale_key"],
                         "HEIGHT_RATIO_TO_ADULT")
        self.assertIn("scale-variant", detail)
        self.assertIn("1.8x", detail)
        self.assertTrue(any("clamped" in n for n in package["v1_notes"]))
        # Verbatim declared value survives in the preserved fields.
        declared = {c["name"]: c for c in package["v1_characters"]}
        self.assertEqual(
            declared["Người Khổng Lồ"]["fields"]["HEAD_RATIO"], "0.30")

    def test_two_scale_characters(self):
        text = _make_script([("Khổng Lồ A", "0.30", "1.8"),
                             ("Khổng Lồ B", "0.36", "0.5")])
        package, _, _ = resolve_v1_plan(text)
        by_name = {c["name"]: c for c in package["characters"]}
        self.assertEqual(by_name["Khổng Lồ A"]["height_px"], 972)
        self.assertEqual(by_name["Khổng Lồ B"]["height_px"], 270)
        self.assertEqual(by_name["Khổng Lồ B"]["scale_ratio"], 0.5)
        self.assertEqual(len(package["v1_scale_deviations"]), 2)

    def test_in_range_ratio_with_trait_scales_without_deviation(self):
        text = _make_script([("Người Cao", "0.34", "1.5")])
        package, _, detail = resolve_v1_plan(text)
        char = package["characters"][0]
        self.assertEqual(char["head_ratio"], 0.34)
        self.assertEqual(char["scale_ratio"], 1.5)
        self.assertEqual(char["height_px"], 810)
        self.assertEqual(package["v1_scale_deviations"], [])
        self.assertNotIn("scale-variant", detail)

    def test_no_trait_no_scale_no_deviation(self):
        text = _make_script([("Người Thường", None, None)])
        package, _, detail = resolve_v1_plan(text)
        self.assertIsNone(package["characters"][0]["scale_ratio"])
        self.assertEqual(package["v1_scale_deviations"], [])
        self.assertNotIn("scale-variant", detail)

    def test_adapt_document_public_path(self):
        doc = parse_studio_script_v1(
            _make_script([("Người Khổng Lồ", "0.30", "1.8")]))
        package = adapt_document(doc)
        self.assertEqual(package["characters"][0]["height_px"], 972)
        self.assertEqual(len(package["v1_scale_deviations"]), 1)

    def test_deterministic(self):
        text = _make_script([("Người Khổng Lồ", "0.30", "1.8")])
        first, _, _ = resolve_v1_plan(text)
        second, _, _ = resolve_v1_plan(text)
        self.assertEqual(first, second)


class TestAdapterRefuses(unittest.TestCase):
    def _assert_refuses(self, text):
        with self.assertRaises(V1AdapterError) as ctx:
            resolve_v1_plan(text)
        return ctx.exception

    def test_out_of_range_without_trait(self):
        self._assert_refuses(
            _make_script([("Người Khổng Lồ", "0.30", None)]))
        self._assert_refuses(
            _make_script([("Người Khổng Lồ", "0.42", None)]))

    def test_global_visual_style_head_ratio(self):
        err = self._assert_refuses(_make_script(
            [("Người Thường", None, None)],
            extra_blocks="VISUAL_STYLE:\nHEAD_RATIO: 0.42"))
        self.assertTrue(any(e["code"] == "V1E009"
                            for e in err.errors))

    def test_unparseable_and_out_of_range_trait(self):
        self._assert_refuses(_make_script(
            [("Người Khổng Lồ", "0.30", "khổng lồ")]))
        self._assert_refuses(
            _make_script([("Người Khổng Lồ", "0.30", "5.0")]))

    def test_scale_character_plus_unrelated_error(self):
        err = self._assert_refuses(_make_script(
            [("Người Khổng Lồ", "0.30", "1.8")],
            extra_scene="DIALOGUE: Người Lạ: Xin chào!"))
        codes = [e["code"] for e in err.errors]
        self.assertTrue(any(c != "V1E009" for c in codes),
                        f"expected a non-V1E009 error, got {codes}")

    def test_two_bad_characters_one_without_trait(self):
        self._assert_refuses(_make_script(
            [("Khổng Lồ A", "0.30", "1.8"),
             ("Khổng Lồ B", "0.30", None)]))


def _face_fill_runs(arr, y_lo, y_hi, x_lo=0, x_hi=1920):
    band = (np.abs(arr[y_lo:y_hi, x_lo:x_hi].astype(int)
                    - np.array(FACE_FILL)).sum(axis=2) < 30)
    best_w, best_top = 0, None
    for r, row in enumerate(band):
        xs = np.where(row)[0]
        if len(xs) < 10:
            continue
        if best_top is None:
            best_top = y_lo + r
        splits = np.where(np.diff(xs) > 1)[0]
        for run in np.split(xs, splits + 1):
            if len(run) > best_w:
                best_w = len(run)
    return best_w, best_top


class TestCharMetricsScale(unittest.TestCase):
    def test_base_scale_multiplies_height_only(self):
        base = char_metrics(CAM, 0.0, 0.0)
        scaled = char_metrics(CAM, 0.0, 0.0, base_scale=1.8)
        self.assertEqual(scaled[0], base[0])
        self.assertEqual(scaled[1], base[1])
        self.assertEqual(scaled[2], int(round(CHAR_H * 1.8)))
        self.assertEqual(base[2], CHAR_H)

    def test_default_is_unchanged(self):
        self.assertEqual(char_metrics(CAM, 0.5, 0.0),
                         char_metrics(CAM, 0.5, 0.0, base_scale=1.0))

    def test_invalid_scales_fall_back_to_default(self):
        base = char_metrics(CAM, 0.0, 0.0)
        for bad in (0, -1, None, "x", float("inf"), float("nan")):
            with self.subTest(value=bad):
                self.assertEqual(char_metrics(CAM, 0.0, 0.0,
                                              base_scale=bad), base)

    def test_scale_composes_with_shot_camera(self):
        cam = viewpoint_for_shot("establishing", "eye_level",
                                 subject_pos=(0.0, 1.2, 0.0))
        base = char_metrics(cam, 0.0, 0.0)
        scaled = char_metrics(cam, 0.0, 0.0, base_scale=1.8)
        self.assertAlmostEqual(scaled[2] / base[2], 1.8, delta=0.02)


def _two_char_package(scale_a=None, scale_b=None):
    chars = [
        {"name": "An", "description": "người thường",
         "template": "female", "voice_hint": "giọng nữ",
         "jacket_color": "#47BD75"},
        {"name": "Bình", "description": "người thường",
         "template": "male", "voice_hint": "giọng nam",
         "jacket_color": "#2E5FA3"},
    ]
    if scale_a is not None:
        chars[0]["scale_ratio"] = scale_a
    if scale_b is not None:
        chars[1]["scale_ratio"] = scale_b
    return {
        "characters": chars,
        "scenes": [{
            "number": 1,
            "location": {"location_keyword": "street",
                         "setting": "day street corner",
                         "mood": "warm", "time_of_day": "day"},
            "setting": "day street corner",
            "action_text": "An và Bình trò chuyện.",
            "action_cues": [],
            "action_lead_sec": 0.0,
            "lines": [
                {"speaker": "An", "kind": "dialogue",
                 "text": "Chào Bình, hôm nay trời đẹp quá."},
                {"speaker": "Bình", "kind": "dialogue",
                 "text": "Ừ, mình đi dạo một vòng nhé."},
            ],
        }],
        "shot_directives": [{
            "scene": 1, "line_index": 1, "shot_type": "establishing",
            "camera_angle": None, "camera_movement": "STATIC"}],
        "props": [],
    }


def _render_still(package, shot):
    with tempfile.TemporaryDirectory() as tmp:
        rep = _render_shot({"shot": shot, "package": package,
                            "out_dir": tmp, "still_only": True})
        img = Image.open(rep["still"]).convert("RGB")
        img.load()
    return rep, img


class TestScaledRender(unittest.TestCase):
    def _planned(self, package):
        shots = plan_shots(
            package, [{"line_index": i + 1, "duration": 2.0}
                      for i in range(2)])
        for i, shot in enumerate(shots):
            shot["index"] = i
        return shots[0]

    def test_scaled_character_head_is_proportionally_larger(self):
        package = _two_char_package(scale_a=1.8)
        shot = self._planned(package)
        _rep, img = _render_still(package, shot)
        arr = np.asarray(img)
        w_left, top_left = _face_fill_runs(arr, 0, H, 0, 960)
        w_right, top_right = _face_fill_runs(arr, 0, H, 960, 1920)
        self.assertGreater(w_left, 100)
        self.assertGreater(w_right, 100)
        # An (left, 1.8x) vs Bình (right, 1.0x) at the same depth:
        # head widths must scale with the body scale.
        self.assertAlmostEqual(w_left / w_right, 1.8, delta=0.25,
                               msg=f"left={w_left} right={w_right}")
        # In a wide shot the scaled head must stay inside the frame.
        self.assertIsNotNone(top_left)
        self.assertGreater(top_left, 0)

    def test_scale_ratio_1_renders_identically_to_absent(self):
        pkg_a = _two_char_package()
        pkg_b = _two_char_package(scale_a=1.0, scale_b=1.0)
        shot_a = self._planned(copy.deepcopy(pkg_a))
        shot_b = self._planned(copy.deepcopy(pkg_b))
        _ra, img_a = _render_still(pkg_a, shot_a)
        _rb, img_b = _render_still(pkg_b, shot_b)
        self.assertEqual(np.asarray(img_a).tobytes(),
                         np.asarray(img_b).tobytes())


if __name__ == "__main__":
    unittest.main()
