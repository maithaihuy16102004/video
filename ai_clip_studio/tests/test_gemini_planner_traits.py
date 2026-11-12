"""Tests for the Gemini planner's section 15 wiring.

The Gemini route is exercised with injected fake clients -- no live
calls. Shape parity across the gemini / fallback / v1 routes is
asserted structurally (same envelope keys, same block keys).
"""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from ai_clip_studio.gemini_client import GeminiError, RateLimitedError
from ai_clip_studio.gemini_planner import (
    _merge,
    _prompt,
    resolve_plan,
)
from ai_clip_studio.planner_fallback import deterministic_planner
from ai_clip_studio.studio_script_v1_adapter import adapt_document

REAL_SCRIPT = "/home/hatch/workspace/acceptance_loop/test_chiec_vi_trong_mua/script.txt"


def _tiny_package():
    return {
        "characters": [{"name": "An", "description": "",
                        "voice_hint": "giọng nam",
                        "jacket_color": "#2E5FA3", "height_px": 560}],
        "locations": [""],
        "scenes": [{
            "number": 1, "title": "Cảnh 1", "setting": "",
            "action_text": "", "audio_text": "", "animation_reqs": [],
            "action_cues": [], "action_lead_sec": 0.0,
            "lines": [{"speaker": "An", "kind": "dialogue",
                       "text": "Xin chào, đây là một câu thử."}],
            "location": {"setting": "", "location_keyword": "street",
                         "mood": "warm", "time_of_day": "day"},
        }],
        "shots": [],
        "audio_events": [],
    }


class FakeClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = 0
        self.models = []

    def generate_json(self, prompt, *, model, max_tokens, timeout=None):
        self.calls += 1
        self.models.append(model)
        if self.error is not None:
            raise self.error
        usage = {"prompt_tokens": 10, "candidates_tokens": 20,
                 "total_tokens": 30}
        return json.dumps(self.payload), usage, model


class StubDoc:
    """A minimal legacy-dialect document (parser-independent)."""

    def to_dict(self):
        return {
            "snapshot_hash": "b" * 64,
            "meta": {"project": "T", "language": "vi-VN"},
            "characters": [{
                "name": "An", "role": "Người kể", "appearance": "Áo xanh",
                "traits": [], "costume": "", "costume_changes": [],
                "voice": "AUTO", "voice_style": "", "head_ratio": 0.34,
                "identity_id": "An", "line": 2,
            }],
            "locations": [], "props": [], "constraints": [],
            "qa": {}, "output": {}, "global_audio": {}, "end_card": None,
            "unsupported_fields": [], "validation_errors": [],
            "scenes": [{
                "number": 1, "title": "Mở",
                "location_ref": None, "location_text": "Phố",
                "time_of_day": "Sáng", "mood": "Vui",
                "actions": ["An đi bộ."], "shots": [],
                "spoken_lines": [{
                    "line_id": "L001", "speaker": "An",
                    "text": "Xin chào.", "kind": "dialogue"}],
                "audio_cues": [], "vfx_cues": [],
            }],
        }


def _assert_no_timestamps(obj, path="root"):
    if isinstance(obj, dict):
        assert "at_seconds" not in obj, path
        for key, value in obj.items():
            _assert_no_timestamps(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            _assert_no_timestamps(value, f"{path}[{i}]")


class TestPrompt(unittest.TestCase):
    def test_prompt_requests_full_vocabularies(self):
        prompt = _prompt("An: \"Chào.\"",
                         [{"speaker": "An", "kind": "dialogue",
                           "text": "Chào."}])
        for shot_type in ("establishing", "medium", "close_up",
                          "extreme_close_up", "over_the_shoulder",
                          "reaction", "object_insert", "tracking",
                          "shot_reverse_shot"):
            self.assertIn(shot_type, prompt)
        for primitive in ("walk_to", "run_to", "turn_to", "look_at",
                          "point_at", "wave", "reach_to", "give_to",
                          "shrug", "cover_face", "nod", "sit_down",
                          "stand_up", "idle", "bend_pick", "kneel_pick"):
            self.assertIn(primitive, prompt)
        self.assertIn("0.34", prompt)
        self.assertIn("at_seconds", prompt)  # in the prohibition rule
        self.assertIn("music", prompt.lower())

    def test_prompt_states_ground_truth_rule(self):
        prompt = _prompt("An: \"Chào.\"",
                         [{"speaker": "An", "kind": "dialogue",
                           "text": "Chào."}])
        self.assertIn("không bịa", prompt)


class TestMerge(unittest.TestCase):
    def test_nested_render_traits_and_trait_blocks(self):
        base = _tiny_package()
        enrichment = {
            "characters": [{
                "name": "An",
                "render_traits": {
                    "description": "thanh niên áo xanh",
                    "voice_hint": "giọng nam", "template": "male",
                    "body_variant": "slim", "costume": "none",
                    "hair_style": "short", "hat": "none",
                    "moustache_style": "none", "glasses": False,
                    "jacket_color": "#112233"},
            }],
            "locations": [{"scene": 1, "render_traits": {
                "setting": "phố", "location_keyword": "rainy_street",
                "mood": "cold", "time_of_day": "night"}}],
            "shots": [{"scene": 1, "line_index": 1,
                       "shot_type": "over_the_shoulder",
                       "purpose": "OTS"}],
            "sfx": [{"event": "rain_start", "scene": 1, "note": "mưa"}],
            "music": [{"name": "Piano", "scene": 1, "intensity": "LOW"}],
            "actions": [{"type": "walk_to", "char": "An", "scene": 1}],
            "hook": "hook", "twist": "twist",
        }
        merged = _merge(base, enrichment,
                        [{"speaker": "An", "kind": "dialogue",
                          "text": "Xin chào, đây là một câu thử."}],
                        model="gemini-test",
                        usage={"prompt_tokens": 1, "candidates_tokens": 2,
                               "total_tokens": 3})
        char = merged["characters"][0]
        self.assertEqual(char["description"], "thanh niên áo xanh")
        self.assertEqual(char["template"], "male")
        self.assertEqual(char["render_traits"]["jacket_color"], "#112233")
        self.assertEqual(merged["scenes"][0]["location"]["location_keyword"],
                         "rainy_street")
        self.assertEqual(len(merged["gemini_shots"]), 1)
        self.assertEqual(merged["gemini_shots"][0]["shot_type"],
                         "over_the_shoulder")
        self.assertEqual(len(merged["gemini_sfx"]), 1)
        self.assertEqual(len(merged["gemini_music"]), 1)
        blocks = merged["trait_blocks"]
        self.assertEqual(blocks["planner"], "gemini")
        self.assertEqual(blocks["model"], "gemini-test")
        self.assertEqual(blocks["usage"]["total_tokens"], 3)
        self.assertIsNone(blocks["reason"])
        self.assertEqual(len(blocks["actions"]), 1)
        self.assertEqual(blocks["characters"][0]["head_ratio"], 0.34)
        _assert_no_timestamps(blocks)

    def test_invalid_enums_dropped_and_derivation_fills(self):
        base = _tiny_package()
        enrichment = {
            "characters": [{
                "name": "An", "template": "alien",
                "head_ratio": 0.42,
                "render_traits": {"template": "alien"},
            }],
            "shots": [{"scene": 1, "line_index": 1, "shot_type": "dolly"}],
        }
        merged = _merge(base, enrichment,
                        [{"speaker": "An", "kind": "dialogue",
                          "text": "Xin chào, đây là một câu thử."}])
        char = merged["characters"][0]
        # Invalid template dropped; deterministic derivation filled it.
        self.assertEqual(char["template"], "male")
        self.assertEqual(merged.get("gemini_shots", []), [])
        dropped = merged["trait_blocks"]["dropped"]
        self.assertTrue(any("head_ratio" in n for n in dropped))
        self.assertTrue(any("alien" in n for n in dropped))

    def test_invented_content_dropped(self):
        base = _tiny_package()
        enrichment = {
            "characters": [
                {"name": "An", "description": "thật"},
                {"name": "NhanVatBia", "description": "bịa"}],
            "shots": [{"scene": 1, "line_index": 99, "shot_type": "medium"}],
            "actions": [{"type": "wave", "char": "NhanVatBia"}],
        }
        merged = _merge(base, enrichment,
                        [{"speaker": "An", "kind": "dialogue",
                          "text": "Xin chào, đây là một câu thử."}])
        names = [c["name"] for c in merged["characters"]]
        self.assertIn("An", names)
        self.assertNotIn("NhanVatBia", names)
        self.assertEqual(merged.get("gemini_shots", []), [])
        self.assertEqual(merged["trait_blocks"]["actions"], [])
        self.assertTrue(merged["trait_blocks"]["dropped"])


class TestResolvePlanWithFakeClient(unittest.TestCase):
    def setUp(self):
        with open(REAL_SCRIPT, encoding="utf-8") as handle:
            self.text = handle.read()

    def test_fake_client_success_labels_gemini(self):
        payload = {
            "characters": [
                {"name": "Minh", "render_traits": {"template": "male"}},
                {"name": "Lan", "render_traits": {"template": "female"}}],
            "hook": "hook", "twist": "twist",
        }
        client = FakeClient(payload)
        package, label, detail = resolve_plan(
            self.text, gemini_client=client)
        self.assertEqual(label, "gemini")
        self.assertIn("Gemini", detail)
        self.assertEqual(client.calls, 1)
        self.assertEqual(package["trait_blocks"]["planner"], "gemini")
        self.assertEqual(package["trait_blocks"]["usage"]["total_tokens"],
                         30)

    def test_fenced_json_parsed(self):
        client = FakeClient({"characters": [], "hook": "h", "twist": "t"})
        orig = client.generate_json

        def fenced(prompt, *, model, max_tokens, timeout=None):
            text, usage, used = orig(prompt, model=model,
                                     max_tokens=max_tokens)
            return "```json\n" + text + "\n```", usage, used
        client.generate_json = fenced
        _package, label, _detail = resolve_plan(
            self.text, gemini_client=client)
        self.assertEqual(label, "gemini")

    def test_failing_client_falls_back_labelled(self):
        client = FakeClient(error=GeminiError("boom"))
        package, label, detail = resolve_plan(
            self.text, gemini_client=client)
        self.assertEqual(label, "fallback")
        self.assertIn("fallback", detail.lower())
        self.assertEqual(client.calls, 3)  # one attempt per model
        self.assertEqual(package["trait_blocks"]["planner"], "fallback")
        self.assertIsNotNone(package["trait_blocks"]["reason"])

    def test_rate_limit_stops_immediately(self):
        client = FakeClient(error=RateLimitedError("HTTP 429"))
        _package, label, _detail = resolve_plan(
            self.text, gemini_client=client)
        self.assertEqual(label, "fallback")
        self.assertEqual(client.calls, 1)

    def test_no_key_no_connector_falls_back_without_client(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            package, label, detail = resolve_plan(self.text)
        self.assertEqual(label, "fallback")
        self.assertIn("fallback", detail.lower())
        self.assertIn("Gemini", detail)
        self.assertEqual(package["trait_blocks"]["planner"], "fallback")

    def test_bad_json_falls_back(self):
        client = FakeClient(payload=None)

        def bad_json(prompt, *, model, max_tokens, timeout=None):
            return "not json at all", {"total_tokens": 0}, model
        client.generate_json = bad_json
        _package, label, _detail = resolve_plan(
            self.text, gemini_client=client)
        self.assertEqual(label, "fallback")


class TestShapeParity(unittest.TestCase):
    def test_envelope_keys_identical_across_routes(self):
        with open(REAL_SCRIPT, encoding="utf-8") as handle:
            fallback = deterministic_planner(handle.read())
        gemini_pkg = _merge(
            _tiny_package(),
            {"characters": [{"name": "An", "description": "x"}]},
            [{"speaker": "An", "kind": "dialogue",
              "text": "Xin chào, đây là một câu thử."}],
            model="m", usage={"prompt_tokens": 0, "candidates_tokens": 0,
                              "total_tokens": 0})
        v1_pkg = adapt_document(StubDoc())
        envelopes = [fallback["trait_blocks"], gemini_pkg["trait_blocks"],
                     v1_pkg["trait_blocks"]]
        key_sets = [set(e) for e in envelopes]
        self.assertEqual(key_sets[0], key_sets[1])
        self.assertEqual(key_sets[0], key_sets[2])
        audio_sets = [set(e["audio"]) for e in envelopes]
        self.assertEqual(audio_sets[0], audio_sets[1])
        self.assertEqual(audio_sets[0], audio_sets[2])
        char_sets = [set(e["characters"][0]) for e in envelopes]
        self.assertEqual(char_sets[0], char_sets[1])
        self.assertEqual(char_sets[0], char_sets[2])
        # Location blocks: the v1 route emits one per declared
        # LOCATION block (none here -- the stub scene is inline-only),
        # while the other routes emit one per scene. Every block that
        # exists must share the canonical key set.
        loc_key_sets = [set(b) for e in envelopes for b in e["locations"]]
        self.assertTrue(loc_key_sets)  # at least one route has blocks
        for key_set in loc_key_sets[1:]:
            self.assertEqual(key_set, loc_key_sets[0])
        loc_render_sets = [set(b["render_traits"]) for e in envelopes
                           for b in e["locations"]]
        for key_set in loc_render_sets[1:]:
            self.assertEqual(key_set, loc_render_sets[0])
        render_sets = [set(e["characters"][0]["render_traits"])
                       for e in envelopes]
        self.assertEqual(render_sets[0], render_sets[1])
        self.assertEqual(render_sets[0], render_sets[2])
        for envelope in envelopes:
            _assert_no_timestamps(envelope)
            for block in envelope["characters"]:
                self.assertEqual(block["head_ratio"], 0.34)

    def test_segmented_package_has_trait_blocks(self):
        package, label, _detail = resolve_plan(
            "Một buổi sáng đẹp trời. An đi dạo quanh hồ. "
            "Bình ngồi đọc sách dưới gốc cây.")
        self.assertEqual(label, "fallback")
        self.assertIn("trait_blocks", package)
        self.assertEqual(package["trait_blocks"]["planner"], "fallback")
        _assert_no_timestamps(package["trait_blocks"])


if __name__ == "__main__":
    unittest.main()
