"""Tests for STUDIO SCRIPT V1 cue -> mixed-audio wiring (Phase B Stage 3).

Covers: trigger resolution (LINE_ID / action text / owning shot /
scene span / recorded fallbacks / V1E022), explicit NONE (scene +
shot level), dedupe, keyword + trait-block mapping, unmapped honesty,
INTENSITY/DURATION handling, stem synthesis + mixing (ffmpeg astats
window checks), the >= 6 dB restraint rule with re-mix, mix length
and fade-out, the legacy _mix_audio contract, and the two Ep1 offline
cue-resolution checks (old-dialect Stage 2 package + new-dialect
authoritative script shapes). No live Gemini, no network, no video
rendering — fixtures and synthetic wavs only.

Stage 3 continuation additions (TestEp1V2Stage3Continuation,
TestBgmDuckingMeasurement): all 7 Ep1 v2 SFX segments inside the
timeline, SFX: NONE shots producing no SFX jobs on the real package,
unresolvable triggers yielding no jobs plus a V1E022 review entry,
BGM-bed dedup, no automatic sounds (no cues / no whooshes / no
legacy events from V1 action-cue vocabulary), the BGM nominal gain
chain, and the measured BGM ducking step on a synthetic mix.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_clip_studio.audio_events import (  # noqa: E402
    DUCKING_DB,
    EVENT_SFX_MAP,
    SYNTHESIS_MAP,
    AudioEvent,
    audio_event_to_synth_job,
    build_shot_clock,
    parse_cue_duration,
    plan_audio_events,
    resolve_mix_gains,
    resolve_v1_cues,
)
from ai_clip_studio.product_flow import (  # noqa: E402
    _mix_audio,
    _rms_db_windows,
)
from ai_clip_studio.product_renderer import plan_shots  # noqa: E402
from ai_clip_studio.studio_script_v1_adapter import (  # noqa: E402
    resolve_v1_plan,
)
from ai_clip_studio.timeline import (  # noqa: E402
    TimelineLine,
    build_timeline,
    measure_wav_duration,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SPEC_GAINS = {
    "narration_gain_db": 0.0, "dialogue_gain_db": 0.0,
    "ambience_gain_db": -18.0, "foley_gain_db": -12.0,
    "sfx_gain_db": -6.0, "bgm_gain_db": -18.0,
    "bgm_ducking_db": -6.0, "master_limit_db": -1.0,
}


def _sine_wav(path: Path, seconds: float, freq: int = 440,
              volume: float = 0.5) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"sine=frequency={freq}:duration={seconds}",
         "-af", f"volume={volume}", "-ac", "1", "-ar", "48000",
         str(path)], check=True, timeout=60)
    return path


def _resolver_fixture():
    """Two scenes, three lines. Scene 1 action text is richer than
    its shot action text so shot-match vs scene-fallback differ."""
    shots = [
        {"scene": 1, "kind": "action", "duration": 1.0,
         "line_index": None, "action_text": "An gõ cửa phòng.",
         "action_cues": []},
        {"scene": 1, "kind": "dialogue", "duration": 2.35,
         "line_index": 1, "action_text": "", "action_cues": []},
        {"scene": 1, "kind": "dialogue", "duration": 2.35,
         "line_index": 2, "action_text": "", "action_cues": []},
        {"scene": 2, "kind": "action", "duration": 1.6,
         "line_index": None,
         "action_text": "An bước đi trên đường đá.",
         "action_cues": ["walk"]},
        {"scene": 2, "kind": "narration", "duration": 3.35,
         "line_index": 3, "action_text": "", "action_cues": []},
    ]
    entries = [
        {"line_index": 1, "start": 1.0, "end": 3.0, "duration": 2.0},
        {"line_index": 2, "start": 3.35, "end": 5.35, "duration": 2.0},
        {"line_index": 3, "start": 7.3, "end": 10.3, "duration": 3.0},
    ]
    package = {
        "scenes": [
            {"number": 1,
             "action_text": "An gõ cửa phòng. Bà chủ nhà đứng "
                            "ngoài hành lang.",
             "v1_scene": {
                 "number": 1, "shots": [],
                 "spoken_lines": [
                     {"line_id": "L001", "speaker": "An",
                      "text": "Câu một.", "kind": "dialogue",
                      "scene_number": 1},
                     {"line_id": "L002", "speaker": "Bà Chủ Nhà",
                      "text": "Câu hai.", "kind": "dialogue",
                      "scene_number": 1}],
                 "sfx_none": False, "ambience_none": False,
                 "bgm_none": False, "meme_none": False}},
            {"number": 2,
             "action_text": "An bước đi trên đường đá.",
             "v1_scene": {
                 "number": 2, "shots": [],
                 "spoken_lines": [
                     {"line_id": "L003", "speaker": "narrator",
                      "text": "Câu ba.", "kind": "narration",
                      "scene_number": 2}],
                 "sfx_none": False, "ambience_none": False,
                 "bgm_none": False, "meme_none": False}},
        ],
        "v1_global_audio": dict(SPEC_GAINS),
    }
    return package, shots, entries


def _cue(cue_type="SFX", name="Heavy door knock on wood", trigger="L001",
         scene=1, **extra):
    cue = {"cue_type": cue_type, "name": name, "trigger": trigger,
           "priority": "REQUIRED", "scene_number": scene,
           "shot_id": None, "line": 42, "source_key": cue_type}
    cue.update(extra)
    return cue


class TestAudioEventCompat(unittest.TestCase):
    def test_to_dict_without_provenance_is_unchanged(self):
        event = AudioEvent("door_contact", 1.0, "DOOR_KNOCK",
                           "foley", -12.0)
        self.assertEqual(set(event.to_dict()), {
            "event_type", "at_seconds", "sfx", "category", "gain_db",
            "source", "meme_id"})

    def test_provenance_fields_round_trip(self):
        event = AudioEvent("door_contact", 1.0, "DOOR_KNOCK", "foley",
                           -12.0, source="synthesised", cue_name="Knock",
                           cue_id="SFX_001", scene=2,
                           synthesis="synthesised: test")
        d = event.to_dict()
        self.assertEqual(d["cue_name"], "Knock")
        self.assertEqual(d["cue_id"], "SFX_001")
        self.assertEqual(d["scene"], 2)
        self.assertIn("synthesised", d["synthesis"])


class TestTriggerResolution(unittest.TestCase):
    def test_end_card_shot_excluded_from_scene_span(self):
        # The card advances the clock (total includes it) but never
        # extends its scene span, so beds end before the card.
        clock = build_shot_clock([
            {"kind": "line", "scene": 1, "line_index": 1,
             "duration": 4.35},
            {"kind": "end_card", "scene": 1, "line_index": None,
             "duration": 3.0}])
        self.assertEqual(clock["scene_spans"][1], (0.0, 4.35))
        self.assertEqual(clock["total_shot_sec"], 7.35)
        self.assertEqual(len(clock["shot_spans"]), 2)

    def test_line_id_trigger_resolves_to_line_start(self):
        package, shots, entries = _resolver_fixture()
        rep = resolve_v1_cues(
            [_cue(trigger="L002")], package=package, shots=shots,
            timeline_entries=entries)
        self.assertEqual(rep["cues"][0]["trigger"]["method"], "line_id")
        self.assertEqual(rep["cues"][0]["trigger"]["start"], 3.35)
        self.assertEqual(rep["segments"][0]["at_seconds"], 3.35)

    def test_unknown_line_id_is_v1e022_unrendered(self):
        package, shots, entries = _resolver_fixture()
        rep = resolve_v1_cues(
            [_cue(trigger="L099")], package=package, shots=shots,
            timeline_entries=entries)
        cue = rep["cues"][0]
        self.assertEqual(cue["render"], "unrendered")
        self.assertEqual(cue["trigger"]["status"], "unresolved")
        self.assertIn("V1E022", cue["trigger"]["reason"])
        self.assertEqual(len(rep["unresolved_triggers"]), 1)
        self.assertEqual(rep["segments"], [])

    def test_action_text_trigger_matches_shot_start(self):
        package, shots, entries = _resolver_fixture()
        rep = resolve_v1_cues(
            [_cue(trigger="An gõ cửa")], package=package, shots=shots,
            timeline_entries=entries)
        trigger = rep["cues"][0]["trigger"]
        self.assertEqual(trigger["method"], "action_text_shot")
        self.assertEqual(trigger["start"], 0.0)
        self.assertEqual(rep["cues"][0]["render"], "rendered")

    def test_action_text_weak_match_falls_back_to_scene_start(self):
        package, shots, entries = _resolver_fixture()
        # "bà chủ nhà" appears in the scene text but in no shot text.
        rep = resolve_v1_cues(
            [_cue(trigger="Bà chủ nhà đứng đợi",
                  name="Heavy door knock on wood")],
            package=package, shots=shots, timeline_entries=entries)
        trigger = rep["cues"][0]["trigger"]
        self.assertEqual(trigger["status"], "fallback")
        self.assertEqual(trigger["method"], "scene_start_fallback")
        self.assertEqual(trigger["start"], 0.0)
        self.assertTrue(any("fallback" in r
                            for r in rep["cues"][0]["reasons"]))

    def test_action_text_no_match_is_unresolved(self):
        package, shots, entries = _resolver_fixture()
        rep = resolve_v1_cues(
            [_cue(trigger="Tiếng còi tàu hỏa")],
            package=package, shots=shots, timeline_entries=entries)
        cue = rep["cues"][0]
        self.assertEqual(cue["trigger"]["status"], "unresolved")
        self.assertIn("V1E022", cue["trigger"]["reason"])
        self.assertEqual(cue["render"], "unrendered")

    def test_triggerless_old_dialect_sfx_is_unresolved(self):
        package, shots, entries = _resolver_fixture()
        rep = resolve_v1_cues(
            [_cue(trigger="")], package=package, shots=shots,
            timeline_entries=entries)
        self.assertEqual(
            rep["cues"][0]["trigger"]["status"], "unresolved")

    def test_ambience_and_bgm_span_the_scene(self):
        package, shots, entries = _resolver_fixture()
        rep = resolve_v1_cues(
            [_cue("AMBIENCE", "Cold wind", "", scene=2),
             _cue("BGM", "Soft reflective instrumental", "", scene=2)],
            package=package, shots=shots, timeline_entries=entries)
        for cue in rep["cues"]:
            self.assertEqual(cue["trigger"]["method"], "scene_span")
            self.assertEqual(cue["trigger"]["start"], 5.7)
            self.assertEqual(cue["trigger"]["end"], 10.65)
        self.assertEqual(len(rep["beds"]), 2)

    def test_planner_timestamp_on_cue_is_ignored(self):
        package, shots, entries = _resolver_fixture()
        cue = _cue(trigger="L001")
        cue["at_seconds"] = 999.0
        rep = resolve_v1_cues([cue], package=package, shots=shots,
                              timeline_entries=entries)
        self.assertEqual(rep["segments"][0]["at_seconds"], 1.0)
        self.assertNotIn("at_seconds", rep["cues"][0]["cue"])
        self.assertTrue(any("timestamp" in w for w in rep["warnings"]))

    def test_snake_event_trigger_uses_owning_shot_start(self):
        package, shots, entries = _resolver_fixture()
        shots[0]["v1_shot_id"] = "SC01_SH02"
        cue = {"cue_type": "SFX", "cue_id": "SFX_001",
               "event": "Wallet opening", "trigger": "PROP_WALLET_OPEN",
               "cue_type_text": "Soft leather rustle",
               "intensity": "LOW", "duration": "0.4s",
               "scene_number": 1, "shot_id": "SC01_SH02"}
        rep = resolve_v1_cues([cue], package=package, shots=shots,
                              timeline_entries=entries)
        trigger = rep["cues"][0]["trigger"]
        self.assertEqual(trigger["method"], "owning_shot_start")
        self.assertEqual(trigger["start"], 0.0)
        self.assertEqual(rep["segments"][0]["synth_kind"], "soft_rustle")
        self.assertEqual(rep["segments"][0]["duration"], 0.4)

    def test_snake_event_trigger_uses_shot_line_anchor(self):
        package, shots, entries = _resolver_fixture()
        package["scenes"][1]["v1_scene"]["shots"] = [
            {"id": "SC02_SH09",
             "trigger": "L003 — “đường đá”"}]
        cue = {"cue_type": "SFX", "cue_id": "SFX_009",
               "event": "Group marching",
               "trigger": "MARCH_SEQUENCE_START",
               "cue_type_text": "Soft collective footsteps",
               "intensity": "LOW", "duration_mode": "ACTION_DURATION",
               "scene_number": 2, "shot_id": "SC02_SH09"}
        rep = resolve_v1_cues([cue], package=package, shots=shots,
                              timeline_entries=entries)
        trigger = rep["cues"][0]["trigger"]
        self.assertEqual(trigger["method"], "owning_shot_line_anchor")
        self.assertEqual(trigger["start"], 7.3)

    def test_snake_event_trigger_without_anchor_falls_back(self):
        package, shots, entries = _resolver_fixture()
        cue = {"cue_type": "SFX", "cue_id": "SFX_001",
               "event": "Wallet opening", "trigger": "PROP_WALLET_OPEN",
               "cue_type_text": "Soft leather rustle",
               "intensity": "LOW", "duration": "0.4s",
               "scene_number": 2, "shot_id": "SC99_SH99"}
        rep = resolve_v1_cues([cue], package=package, shots=shots,
                              timeline_entries=entries)
        trigger = rep["cues"][0]["trigger"]
        self.assertEqual(trigger["status"], "fallback")
        self.assertEqual(trigger["start"], 5.7)

    def test_empty_trigger_structured_cue_anchors_to_shot(self):
        package, shots, entries = _resolver_fixture()
        shots[3]["v1_shot_id"] = "SC02_SH01"
        cue = {"cue_type": "SFX", "cue_id": "SFX_002",
               "event": "Map reveal", "trigger": "",
               "cue_type_text": "Soft paper rustle",
               "intensity": "LOW", "duration": "0.6s",
               "scene_number": 2, "shot_id": "SC02_SH01"}
        rep = resolve_v1_cues([cue], package=package, shots=shots,
                              timeline_entries=entries)
        self.assertEqual(
            rep["cues"][0]["trigger"]["method"], "owning_shot_start")
        self.assertEqual(rep["cues"][0]["trigger"]["start"], 5.7)


class TestNoneAndMemes(unittest.TestCase):
    def test_scene_flag_coexisting_with_real_cue_renders(self):
        # The parser collapses shot-level NONE to the scene flag, so
        # a flag coexisting with real cues of the kind is shot-scoped
        # NONE: the cue renders for its own shot, with the
        # coexistence recorded, and no scene-wide NONE span.
        package, shots, entries = _resolver_fixture()
        package["scenes"][0]["v1_scene"]["sfx_none"] = True
        rep = resolve_v1_cues(
            [_cue(trigger="L001")], package=package, shots=shots,
            timeline_entries=entries)
        self.assertEqual(rep["cues"][0]["render"], "rendered")
        self.assertTrue(any("coexists" in r
                            for r in rep["cues"][0]["reasons"]))
        self.assertTrue(any("coexists" in w for w in rep["warnings"]))
        self.assertEqual(rep["none_suppressed"], [])
        self.assertEqual(rep["none_spans"]["sfx"], [])
        self.assertEqual(len(rep["segments"]), 1)

    def test_scene_ambience_none_without_cues_yields_span(self):
        # Scene-wide NONE (flag + no cues of that kind): the span is
        # recorded for bed muting and no bed is produced.
        package, shots, entries = _resolver_fixture()
        package["scenes"][1]["v1_scene"]["ambience_none"] = True
        rep = resolve_v1_cues(
            [_cue(trigger="L001", scene=1)], package=package,
            shots=shots, timeline_entries=entries)
        self.assertEqual(rep["none_spans"]["ambience"], [[5.7, 10.65]])
        self.assertEqual(
            [b for b in rep["beds"] if b["stem"] == "ambience"], [])

    def test_scene_ambience_none_coexisting_with_cue_renders(self):
        package, shots, entries = _resolver_fixture()
        package["scenes"][1]["v1_scene"]["ambience_none"] = True
        rep = resolve_v1_cues(
            [_cue("AMBIENCE", "Cold wind", "", scene=2)],
            package=package, shots=shots, timeline_entries=entries)
        self.assertEqual(rep["cues"][0]["render"], "rendered")
        self.assertEqual(rep["none_spans"]["ambience"], [])
        self.assertEqual(len(rep["beds"]), 1)

    def test_scene_bgm_none_coexisting_with_cue_renders(self):
        package, shots, entries = _resolver_fixture()
        package["scenes"][0]["v1_scene"]["bgm_none"] = True
        rep = resolve_v1_cues(
            [_cue("BGM", "Soft reflective instrumental", "", scene=1)],
            package=package, shots=shots, timeline_entries=entries)
        self.assertEqual(rep["cues"][0]["render"], "rendered")
        self.assertTrue(any("coexists" in r
                            for r in rep["cues"][0]["reasons"]))
        self.assertEqual(len(rep["beds"]), 1)

    def test_shot_level_sfx_none_suppresses_cue(self):
        package, shots, entries = _resolver_fixture()
        package["scenes"][0]["v1_scene"]["shots"] = [
            {"id": "SC01_SH03", "sfx_none": True}]
        cue = {"cue_type": "SFX", "cue_id": "SFX_001",
               "event": "Wallet opening", "trigger": "PROP_WALLET_OPEN",
               "cue_type_text": "Soft leather rustle",
               "intensity": "LOW", "duration": "0.4s",
               "scene_number": 1, "shot_id": "SC01_SH03"}
        rep = resolve_v1_cues([cue], package=package, shots=shots,
                              timeline_entries=entries)
        self.assertEqual(rep["cues"][0]["render"], "unrendered")
        self.assertIn("SC01_SH03", rep["cues"][0]["reasons"][0])

    def test_meme_and_vfx_cues_never_render_audio(self):
        package, shots, entries = _resolver_fixture()
        rep = resolve_v1_cues(
            [_cue("MEME", "ối dồi ôi", "L001", scene=1),
             _cue("VFX", "Subtle glow", "L001", scene=1)],
            package=package, shots=shots, timeline_entries=entries)
        self.assertTrue(all(c["render"] == "unrendered"
                            for c in rep["cues"]))
        self.assertEqual(rep["segments"], [])
        self.assertEqual(rep["beds"], [])

    def test_trait_mapped_cue_renders_despite_coexisting_flag(self):
        # Trait mapping still applies when the scene flag coexists
        # with the real cue (shot-scoped NONE, not suppression).
        package, shots, entries = _resolver_fixture()
        package["scenes"][0]["v1_scene"]["sfx_none"] = True
        package["trait_blocks"] = {"audio": [
            {"cue_type": "SFX", "name": "Heavy door knock on wood",
             "trigger": "L001", "scene_number": 1, "line": 42,
             "event": "door_contact"}]}
        rep = resolve_v1_cues(
            [_cue(trigger="L001")], package=package, shots=shots,
            timeline_entries=entries)
        self.assertEqual(rep["cues"][0]["render"], "rendered")
        self.assertEqual(rep["cues"][0]["mapping"]["source"],
                         "trait_blocks")
        self.assertEqual(len(rep["segments"]), 1)


class TestMapping(unittest.TestCase):
    def _resolve_one(self, name, trigger="L001", scene=1, **extra):
        package, shots, entries = _resolver_fixture()
        cue = _cue(name=name, trigger=trigger, scene=scene, **extra)
        rep = resolve_v1_cues([cue], package=package, shots=shots,
                              timeline_entries=entries)
        return rep

    def test_keyword_table_maps_honest_syntheses(self):
        cases = [
            ("Heavy door knock on wood", "knock", "door_contact"),
            ("Door opening slowly", "door_open", "door_rotation"),
            ("Rustling paper", "paper_rustle", "paper_movement"),
            ("Soft leather rustle", "soft_rustle", None),
            ("Pen writing", "writing_scratch", None),
            ("Postcards dropping", "impact", "object_impact"),
            ("Footsteps on cobblestones", "footstep", "foot_contact"),
            ("Group marching", "march_bed", None),
            ("Foot enters mud", "mud_squelch", None),
            ("Distant artillery", "artillery_rumble", None),
        ]
        for name, kind, engine in cases:
            with self.subTest(name=name):
                rep = self._resolve_one(name)
                self.assertEqual(rep["cues"][0]["render"], "rendered")
                seg = rep["segments"][0]
                self.assertEqual(seg["synth_kind"], kind)
                self.assertEqual(seg["event_type"], engine or kind)
                self.assertTrue(seg["method"].startswith("synthesised:"))

    def test_unmapped_kinds_are_reported_never_substituted(self):
        for name in ("Cathedral bells tolling",
                     "Massive crowd roar and martial fanfare",
                     "Military bugle call",
                     "Distant sirens wailing"):
            with self.subTest(name=name):
                rep = self._resolve_one(name)
                self.assertEqual(rep["cues"][0]["render"], "unrendered")
                self.assertEqual(
                    rep["cues"][0]["mapping"]["status"], "unmapped")
                self.assertEqual(rep["segments"], [])
                self.assertEqual(len(rep["unmapped_cues"]), 1)

    def test_compound_cue_renders_mapped_part_only(self):
        rep = self._resolve_one(
            "Rustling paper and paperboy shout", trigger="L001")
        cue = rep["cues"][0]
        self.assertEqual(cue["render"], "rendered")
        self.assertTrue(cue["mapping"].get("partial"))
        self.assertIn("paperboy shout",
                      cue["mapping"]["unmapped_parts"])
        self.assertEqual(len(rep["segments"]), 1)
        self.assertEqual(rep["segments"][0]["synth_kind"],
                         "paper_rustle")

    def test_paper_does_not_match_paperboy(self):
        rep = self._resolve_one("Paperboy shout", trigger="L001")
        self.assertEqual(rep["cues"][0]["render"], "unrendered")

    def test_trait_mapping_wins_over_keywords(self):
        package, shots, entries = _resolver_fixture()
        package["trait_blocks"] = {"audio": [
            {"cue_type": "SFX", "name": "Mysterious sound",
             "trigger": "L001", "scene_number": 1, "line": 42,
             "event": "door_contact", "at_seconds": 999.0}]}
        rep = resolve_v1_cues(
            [_cue(name="Mysterious sound", trigger="L001")],
            package=package, shots=shots, timeline_entries=entries)
        self.assertTrue(rep["trait_blocks_present"])
        self.assertTrue(rep["planner_timestamps_ignored"])
        self.assertEqual(rep["segments"][0]["synth_kind"], "knock")
        # Time recomputed from the measured clock, not the trait's 999.
        self.assertEqual(rep["segments"][0]["at_seconds"], 1.0)
        self.assertEqual(
            rep["cues"][0]["mapping"]["source"], "trait_blocks")

    def test_trait_unmapped_listing_is_advisory_not_veto(self):
        # A planner "unmapped" listing means "no engine SFX event in
        # the planner's vocabulary" — the audio stage's own keyword
        # mapping still applies, and the listing is recorded as a
        # note. (The deterministic planner lists all 7 new-dialect
        # SFX cues this way; vetoing them would silence the mix.)
        package, shots, entries = _resolver_fixture()
        package["trait_blocks"] = {"audio": {
            "events": [],
            "unmapped_cues": [{"cue_type": "SFX",
                               "name": "Heavy door knock on wood",
                               "scene_number": 1}]}}
        rep = resolve_v1_cues(
            [_cue(trigger="L001")], package=package, shots=shots,
            timeline_entries=entries)
        self.assertEqual(rep["cues"][0]["render"], "rendered")
        self.assertEqual(
            rep["cues"][0]["mapping"]["source"], "keyword")
        self.assertTrue(any("lists this cue as unmapped" in r
                            for r in rep["cues"][0]["reasons"]))

    def test_trait_music_item_without_event_renders_pad(self):
        # SPEC 15.4 music events carry no SFX event name; a trait
        # music item must NOT be treated as an unmapped veto.
        package, shots, entries = _resolver_fixture()
        package["trait_blocks"] = {"audio": {
            "music": [{"cue_type": "BGM",
                       "name": "Soft reflective instrumental",
                       "scene_number": 1, "line": 42}]}}
        rep = resolve_v1_cues(
            [_cue("BGM", "Soft reflective instrumental", "",
                  scene=1)],
            package=package, shots=shots, timeline_entries=entries)
        self.assertEqual(rep["cues"][0]["render"], "rendered")
        self.assertEqual(
            rep["cues"][0]["mapping"]["source"], "trait_blocks")
        self.assertEqual(rep["beds"][0]["synth_kind"], "music_pad")

    def test_trait_character_reaction_never_renders(self):
        package, shots, entries = _resolver_fixture()
        package["trait_blocks"] = {"audio": [
            {"cue_type": "SFX", "name": "Funny reaction",
             "trigger": "L001", "scene_number": 1, "line": 42,
             "event": "character_reaction"}]}
        rep = resolve_v1_cues(
            [_cue(name="Funny reaction", trigger="L001")],
            package=package, shots=shots, timeline_entries=entries)
        self.assertEqual(rep["cues"][0]["render"], "unrendered")
        self.assertEqual(rep["segments"], [])

    def test_no_trait_blocks_still_works(self):
        package, shots, entries = _resolver_fixture()
        rep = resolve_v1_cues(
            [_cue(trigger="L001")], package=package, shots=shots,
            timeline_entries=entries)
        self.assertFalse(rep["trait_blocks_present"])
        self.assertEqual(rep["cues"][0]["render"], "rendered")

    def test_bgm_renders_labelled_pad_never_sfx_names(self):
        rep = self._resolve_one(
            "Epic martial orchestral crescendo", trigger="",
            cue_type="BGM")
        self.assertEqual(rep["cues"][0]["render"], "rendered")
        self.assertEqual(rep["segments"], [])
        bed = rep["beds"][0]
        self.assertEqual(bed["stem"], "music")
        self.assertEqual(bed["synth_kind"], "music_pad")
        self.assertIn("NOT the scripted piece", bed["method"])

    def test_intensity_ladder(self):
        for intensity, expected in (("LOW", -18.0), ("MODERATE", -12.0),
                                    ("MEDIUM", -12.0), ("HIGH", -9.0)):
            with self.subTest(intensity=intensity):
                rep = self._resolve_one(
                    "Heavy door knock on wood", trigger="L001",
                    intensity=intensity)
                # knock base -12 + sfx bus offset 0 + ladder offset.
                self.assertEqual(rep["segments"][0]["gain_db"], expected)

    def test_duration_parsing(self):
        seconds, mode, note = parse_cue_duration({"duration": "0.4s"})
        self.assertEqual((seconds, mode, note), (0.4, None, None))
        seconds, mode, _ = parse_cue_duration({"duration": 1.5})
        self.assertEqual(seconds, 1.5)
        seconds, mode, _ = parse_cue_duration(
            {"duration_mode": "ACTION_DURATION"})
        self.assertEqual((seconds, mode), (None, "ACTION_DURATION"))
        seconds, _, note = parse_cue_duration({"duration": "soon"})
        self.assertIsNone(seconds)
        self.assertIn("unparsable", note)

    def test_action_duration_spans_owning_shot(self):
        package, shots, entries = _resolver_fixture()
        shots[0]["v1_shot_id"] = "SC01_SH02"
        cue = {"cue_type": "SFX", "cue_id": "SFX_003",
               "event": "Pen writing", "trigger": "PEN_CONTACT_PAPER",
               "cue_type_text": "Soft writing scratch",
               "intensity": "LOW", "duration_mode": "ACTION_DURATION",
               "scene_number": 1, "shot_id": "SC01_SH02"}
        rep = resolve_v1_cues([cue], package=package, shots=shots,
                              timeline_entries=entries)
        seg = rep["segments"][0]
        self.assertEqual((seg["at_seconds"], seg["end_seconds"]),
                         (0.0, 1.0))
        self.assertEqual(seg["duration"], 1.0)

    def test_identical_events_deduplicate(self):
        package, shots, entries = _resolver_fixture()
        rep = resolve_v1_cues(
            [_cue(trigger="L001"), _cue(trigger="L001")],
            package=package, shots=shots, timeline_entries=entries)
        self.assertEqual(len(rep["segments"]), 1)
        self.assertTrue(all(c["render"] == "rendered"
                            for c in rep["cues"]))

    def test_rain_cue_dedupes_against_global_rain_bed(self):
        package, shots, entries = _resolver_fixture()
        rep = resolve_v1_cues(
            [_cue("AMBIENCE", "Light rain", "", scene=1)],
            package=package, shots=shots, timeline_entries=entries,
            rainy=True)
        self.assertEqual(rep["beds"], [])
        self.assertEqual(rep["cues"][0]["render"], "rendered")
        self.assertTrue(any("rain bed" in r
                            for r in rep["cues"][0]["reasons"]))

    def test_synthesis_map_covers_engine_events(self):
        for event, kind in (("door_contact", "knock"),
                            ("door_rotation", "door_open"),
                            ("paper_movement", "paper_rustle"),
                            ("object_impact", "impact"),
                            ("foot_contact", "footstep"),
                            ("rain_start", "rain_bed")):
            self.assertIn(kind, SYNTHESIS_MAP)
            spec = SYNTHESIS_MAP[kind]
            self.assertTrue(spec["method"].startswith("synthesised:"))
            self.assertTrue(spec["inputs"])
            self.assertIn("[out]", spec["filter"])


class TestMixGains(unittest.TestCase):
    def test_v1_bus_offset_applies(self):
        gains = resolve_mix_gains({"v1_global_audio": {
            **SPEC_GAINS, "sfx_gain_db": -12.0}})
        package, shots, entries = _resolver_fixture()
        package["v1_global_audio"] = gains["bus_gains"]
        rep = resolve_v1_cues(
            [_cue(trigger="L001")], package=package, shots=shots,
            timeline_entries=entries)
        # knock base -12 + sfx offset (-12 - -6) = -18.
        self.assertEqual(rep["segments"][0]["gain_db"], -18.0)

    def test_prose_gain_falls_back_to_default_with_warning(self):
        gains = resolve_mix_gains({"v1_global_audio": {
            "bgm_ducking_db": "12–18 dB below speech"}})
        self.assertEqual(gains["ducking_db"], -6.0)
        self.assertTrue(any("bgm_ducking_db" in w
                            for w in gains["warnings"]))

    def test_no_global_audio_uses_engine_defaults(self):
        gains = resolve_mix_gains({})
        self.assertEqual(gains["ducking_db"], DUCKING_DB)
        self.assertIsNone(gains["master_limit_db"])
        self.assertEqual(gains["source"], "engine_defaults")


class TestLegacyAudioEventJobs(unittest.TestCase):
    def test_meme_event_never_gets_a_job(self):
        gains = resolve_mix_gains({})
        kind, job, reason = audio_event_to_synth_job(
            AudioEvent("character_reaction", 1.0, "CONTEXTUAL_MEME",
                       "memes", -12.0), gains, total_sec=10.0)
        self.assertIsNone(kind)
        self.assertIn("meme", reason.lower())

    def test_rain_start_becomes_a_bed_to_timeline_end(self):
        gains = resolve_mix_gains({})
        kind, job, _ = audio_event_to_synth_job(
            AudioEvent("rain_start", 2.0, "RAIN_AMBIENCE", "ambience",
                       -20.0), gains, total_sec=10.0)
        self.assertEqual(kind, "bed")
        self.assertEqual((job["start"], job["end"]), (2.0, 10.0))


class TestMixAudio(unittest.TestCase):
    def _entries(self, tmp: Path):
        v1 = _sine_wav(tmp / "v1.wav", 2.0, volume=0.5)
        v2 = _sine_wav(tmp / "v2.wav", 2.0, freq=520, volume=0.5)
        return [
            {"line_index": 1, "speaker": "An", "kind": "dialogue",
             "text": "x", "wav": str(v1), "duration": 2.0,
             "start": 0.5, "end": 2.5},
            {"line_index": 2, "speaker": "narrator",
             "kind": "narration", "text": "y", "wav": str(v2),
             "duration": 2.0, "start": 4.0, "end": 6.0},
        ]

    def _jobs(self):
        segments = [{
            "event_type": "door_contact", "at_seconds": 1.0,
            "end_seconds": 1.4, "duration": 0.4, "sfx": "DOOR_KNOCK",
            "category": "foley", "gain_db": -12.0,
            "synth_kind": "knock",
            "method": SYNTHESIS_MAP["knock"]["method"],
            "cue_name": "knock", "cue_id": None, "scene": 1,
            "source": "v1_cue"},
            {"event_type": "paper_movement", "at_seconds": 5.0,
             "end_seconds": 5.6, "duration": 0.6,
             "sfx": "PAPER_RUSTLE", "category": "foley",
             "gain_db": -14.0, "synth_kind": "paper_rustle",
             "method": SYNTHESIS_MAP["paper_rustle"]["method"],
             "cue_name": "paper", "cue_id": None, "scene": 1,
             "source": "v1_cue"}]
        beds = [{
            "stem": "ambience", "synth_kind": "wind_bed",
            "start": 0.0, "end": 8.0, "gain_db": -22.0,
            "method": SYNTHESIS_MAP["wind_bed"]["method"],
            "cue_name": "wind", "cue_id": None, "scene": 1,
            "fade_down": False, "source": "v1_cue"},
            {"stem": "music", "synth_kind": "music_pad",
             "start": 0.0, "end": 8.0, "gain_db": -18.0,
             "method": SYNTHESIS_MAP["music_pad"]["method"],
             "cue_name": "pad", "cue_id": None, "scene": 1,
             "fade_down": False, "source": "bgm_pad"}]
        return segments, beds

    def test_full_stem_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            entries = self._entries(tmp)
            segments, beds = self._jobs()
            mix, info = _mix_audio(
                tmp, entries, 8.5, False, segments=segments,
                beds=beds, mix_gains=resolve_mix_gains({}),
                none_spans={})
            # Stems exported, mix exact length, fade-out present.
            for name in ("dialogue.wav", "narration.wav", "foley.wav",
                         "ambience.wav", "music.wav"):
                self.assertIn(name, info["stems"])
                self.assertTrue(Path(info["stems"][name]).exists())
            self.assertAlmostEqual(measure_wav_duration(mix), 8.5,
                                   delta=0.05)
            self.assertEqual(info["mix_duration_sec"], 8.5)
            voice_rms = _rms_db_windows(mix, [(1.0, 2.0)])
            tail_rms = _rms_db_windows(mix, [(8.2, 8.5)])
            self.assertLess(tail_rms, voice_rms - 10.0)
            # Foley energy in event windows, silence elsewhere
            # (ffmpeg astats, as the brief requires).
            foley = Path(info["stems"]["foley.wav"])
            self.assertGreater(_rms_db_windows(foley, [(0.9, 1.5)]),
                               -60.0)
            self.assertEqual(_rms_db_windows(foley, [(2.0, 3.0)]),
                             -120.0)
            self.assertGreater(_rms_db_windows(foley, [(4.9, 5.7)]),
                               -60.0)
            self.assertEqual(_rms_db_windows(foley, [(6.5, 7.5)]),
                             -120.0)
            # Restraint: voice clearly above every stem.
            restraint = info["restraint"]
            self.assertTrue(restraint["ok"])
            for gap in restraint["gaps_db"].values():
                self.assertGreaterEqual(gap, 6.0)
            # Every synthesis labelled.
            for seg in segments:
                self.assertTrue(seg["method"].startswith("synthesised:"))

    def test_restraint_remix_lowers_hot_stem(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            entries = self._entries(tmp)
            segments, _ = self._jobs()
            segments[0] = dict(segments[0], gain_db=6.0)
            _, info = _mix_audio(
                tmp, entries, 8.5, False, segments=segments, beds=[],
                mix_gains=resolve_mix_gains({}), none_spans={})
            restraint = info["restraint"]
            self.assertTrue(restraint["ok"])
            self.assertLess(
                restraint["extra_attenuation_db"]["foley.wav"], 0.0)
            self.assertGreater(restraint["iterations"], 1)
            self.assertGreaterEqual(
                restraint["gaps_db"]["foley.wav"], 6.0)

    def test_legacy_path_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            entries = self._entries(tmp)
            mix, info = _mix_audio(tmp, entries, 8.5, True)
            self.assertAlmostEqual(measure_wav_duration(mix), 8.5,
                                   delta=0.05)
            self.assertIsNotNone(info["rain_db"])
            self.assertIsNotNone(info["rain_bed"])
            self.assertIn("voice_minus_rain_db", info)
            self.assertNotIn("stems", info)

    def test_voice_only_stem_mix_has_no_empty_stems(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            entries = self._entries(tmp)
            mix, info = _mix_audio(
                tmp, entries, 8.5, False, segments=[], beds=[],
                mix_gains=resolve_mix_gains({}), none_spans={})
            self.assertEqual(set(info["stems"]),
                             {"dialogue.wav", "narration.wav"})
            self.assertAlmostEqual(measure_wav_duration(mix), 8.5,
                                   delta=0.05)

    def test_none_span_mutes_rain_bed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            entries = self._entries(tmp)
            _, info = _mix_audio(
                tmp, entries, 8.5, True, segments=[], beds=[],
                mix_gains=resolve_mix_gains({}),
                none_spans={"ambience": [[4.0, 6.0]]})
            ambience = Path(info["stems"]["ambience.wav"])
            self.assertEqual(
                _rms_db_windows(ambience, [(4.2, 5.8)]), -120.0)
            self.assertGreater(
                _rms_db_windows(ambience, [(6.2, 6.9)]), -60.0)

    def test_master_limiter_and_no_clipping(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            entries = self._entries(tmp)
            segments, beds = self._jobs()
            gains = resolve_mix_gains(
                {"v1_global_audio": dict(SPEC_GAINS)})
            mix, info = _mix_audio(
                tmp, entries, 8.5, False, segments=segments,
                beds=beds, mix_gains=gains, none_spans={})
            self.assertEqual(info["master_limit_db"], -1.0)
            r = subprocess.run(
                ["ffmpeg", "-v", "info", "-i", str(mix), "-vn",
                 "-af", "astats=metadata=1", "-f", "null", "-"],
                capture_output=True, text=True, timeout=120)
            overall = False
            peak = None
            for line in (r.stderr or "").splitlines():
                if "Overall" in line:
                    overall = True
                if overall and "Peak level dB:" in line:
                    peak = float(line.split("Peak level dB:")[-1])
                    break
            self.assertIsNotNone(peak)
            self.assertLessEqual(peak, 0.0)

    def test_bed_ends_at_scene_end_silence_after(self):
        """End-card rule by construction: no bed spans past its
        scene, so the mix tail past the last bed holds no bed
        energy (voice/rain aside — here: no rain, voice ended)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            entries = self._entries(tmp)
            _, beds = self._jobs()
            beds = [dict(beds[0], end=6.0)]
            _, info = _mix_audio(
                tmp, entries, 8.5, False, segments=[], beds=beds,
                mix_gains=resolve_mix_gains({}), none_spans={})
            ambience = Path(info["stems"]["ambience.wav"])
            self.assertEqual(
                _rms_db_windows(ambience, [(6.5, 8.0)]), -120.0)


class TestPauseAfterSec(unittest.TestCase):
    def test_timeline_honours_per_line_pause(self):
        lines = [
            TimelineLine(text="Câu một.", speaker="An",
                         kind="dialogue", duration_sec=2.0,
                         pause_after_sec=0.35),
            TimelineLine(text="Câu hai.", speaker="An",
                         kind="dialogue", duration_sec=2.0,
                         pause_after_sec=0.6),
        ]
        timeline = build_timeline(lines)
        # 2.0 + 0.35 + 2.0 + 0.6 + 0.5 tail.
        self.assertAlmostEqual(timeline.total_duration_sec, 5.45,
                               delta=0.05)
        self.assertTrue(timeline.all_measured)


class TestEp1OldDialectOffline(unittest.TestCase):
    """Stage 2 reference: jobs/req_8faa5a8dd9e2/scene_package.json
    (27 cues) resolved against the real measured shot clock from
    its timeline.json. No rendering — resolution only."""

    def test_ep1_cue_resolution_counts(self):
        job_dir = REPO_ROOT / "jobs" / "req_8faa5a8dd9e2"
        package = json.loads(
            (job_dir / "scene_package.json").read_text(
                encoding="utf-8"))
        timeline = json.loads(
            (job_dir / "timeline.json").read_text(encoding="utf-8"))
        shots = timeline["shots"]
        clock = build_shot_clock(shots)
        line_by_index = {e["line_index"]: dict(e)
                         for e in timeline["lines"]}
        entries = []
        for span in clock["shot_spans"]:
            shot = span["shot"]
            if shot["kind"] != "action":
                entry = line_by_index[shot["line_index"]]
                entry["start"] = span["start"]
                entry["end"] = round(span["start"] + entry["duration"],
                                     3)
                entries.append(entry)
        entries.sort(key=lambda e: e["line_index"])
        rep = resolve_v1_cues(
            package["v1_audio_cues"], package=package, shots=shots,
            timeline_entries=entries, rainy=False,
            script_text=(job_dir / "script.txt").read_text(
                encoding="utf-8"))
        # Honest counts from the real data (brief said 8 MEME_NOTEs
        # / 0 BGM; the package actually holds 8 BGM + 3 MEME cues).
        self.assertEqual(rep["total_cues"], 27)
        self.assertEqual(rep["rendered_cues"], 19)
        self.assertEqual(rep["unrendered_cues"], 8)
        self.assertEqual(rep["counts_by_type"]["SFX"],
                         {"total": 8, "rendered": 5, "unrendered": 3})
        self.assertEqual(rep["counts_by_type"]["AMBIENCE"],
                         {"total": 8, "rendered": 6, "unrendered": 2})
        self.assertEqual(rep["counts_by_type"]["BGM"],
                         {"total": 8, "rendered": 8, "unrendered": 0})
        self.assertEqual(rep["counts_by_type"]["MEME"],
                         {"total": 3, "rendered": 0, "unrendered": 3})
        self.assertEqual(len(rep["segments"]), 5)
        self.assertEqual(len(rep["beds"]), 15)
        # Every cue accounted for exactly once, with a reason.
        self.assertEqual(len(rep["cues"]), 27)
        # Door knock renders at the scene-2 shot start.
        knock = next(s for s in rep["segments"]
                     if s["synth_kind"] == "knock")
        self.assertEqual(knock["at_seconds"], 7.2)
        # Bells + crowd roar stay unmapped; boots stamp unresolved.
        names = {c["name"]: c for c in rep["cues"]}
        self.assertEqual(
            names["Cathedral bells tolling and distant sirens"]
            ["mapping"]["status"], "unmapped")
        self.assertEqual(
            names["Massive crowd roar and martial fanfare"]
            ["mapping"]["status"], "unmapped")
        boots = names["Military boots stamp in unison and solemn "
                      "bugle call"]
        self.assertEqual(boots["trigger"]["status"], "unresolved")
        self.assertIn("V1E022", boots["trigger"]["reason"])
        # All MEME cues unrendered; all jobs labelled synthesised.
        for cue in rep["cues"]:
            if cue["cue_type"] == "MEME":
                self.assertEqual(cue["render"], "unrendered")
        for job in rep["segments"] + rep["beds"]:
            self.assertTrue(job["method"].startswith("synthesised:"))
        # The report must be JSON-serializable (audio_plan.json).
        json.dumps(rep, ensure_ascii=False)


def _new_dialect_fixture():
    """Hand-derived from examples/hitler_ep01_munich_1914.studio.md:
    7 structured SFX + 5 AMBIENCE + 6 BGM cues in the new shape,
    with a synthetic measured timeline. The parser dialect has not
    landed, so the cue dicts below encode the redirect's field list
    (cue_id/event/trigger/cue_type_text/intensity/duration/
    duration_mode) verbatim from the script file."""
    sfx = [
        ("SFX_001", "Wallet opening", "PROP_WALLET_OPEN",
         "Soft leather rustle", "LOW", "0.4s", None, 1, "SC01_SH02"),
        ("SFX_002", "Map reveal", "MAP_FIRST_REVEAL",
         "Soft paper rustle", "LOW", "0.6s", None, 2, "SC02_SH01"),
        ("SFX_003", "Pen writing", "PEN_CONTACT_PAPER",
         "Soft writing scratch", "LOW", None, "ACTION_DURATION",
         3, "SC03_SH02"),
        ("SFX_004", "Document pickup", "DOCUMENT_PICKUP",
         "Paper rustle", "LOW", "0.5s", None, 3, "SC03_SH03"),
        ("SFX_005", "Group marching", "MARCH_SEQUENCE_START",
         "Soft collective footsteps", "LOW", None, "ACTION_DURATION",
         5, "SC05_SH02"),
        ("SFX_006", "Foot enters mud", "FIRST_MUD_CONTACT",
         "Wet mud squelch", "LOW", "0.5s", None, 6, "SC06_SH02"),
        ("SFX_007", "Distant artillery", "DISTANT_ARTILLERY_EVENT",
         "Muffled distant artillery", "MODERATE", "1.5s", None,
         6, "SC06_SH03"),
    ]
    cues = []
    for cid, event, trigger, typ, intensity, dur, dmode, scene, shot in sfx:
        cue = {"cue_type": "SFX", "cue_id": cid, "event": event,
               "trigger": trigger, "cue_type_text": typ,
               "intensity": intensity, "scene_number": scene,
               "shot_id": shot, "source_key": "SFX"}
        if dur:
            cue["duration"] = dur
        if dmode:
            cue["duration_mode"] = dmode
        cues.append(cue)
    for scene, name in [
            (1, "Distant footsteps and quiet street activity"),
            (3, "Quiet office room tone"),
            (4, "Distant soldiers and quiet barracks activity"),
            (5, "Cold wind"),
            (6, "Continuous light rain and distant battlefield "
                "rumble")]:
        cues.append({"cue_type": "AMBIENCE", "name": name,
                     "mode": "LOOP", "scene_number": scene,
                     "source_key": "AMBIENCE"})
    for scene, name in [
            (1, "Soft reflective instrumental"),
            (2, "Restrained historical tension"),
            (3, "Subtle tension"),
            (4, "Very low, restrained"),
            (5, "Somber instrumental transition"),
            (6, "Fade down to near silence")]:
        cues.append({"cue_type": "BGM", "name": name,
                     "scene_number": scene, "source_key": "BGM"})

    def _shot(scene, kind, duration, line_index=None, v1=None,
              action_text=""):
        shot = {"scene": scene, "kind": kind, "duration": duration,
                "line_index": line_index, "action_text": action_text,
                "action_cues": []}
        if v1:
            shot["v1_shot_id"] = v1
        return shot

    shots = [
        _shot(1, "action", 2.0, None, "SC01_SH01",
              "Hitler đi bộ trên vỉa hè."),
        _shot(1, "narration", 8.0, 1),
        _shot(1, "action", 1.5, None, "SC01_SH02",
              "Hitler mở ví bằng hai tay."),
        _shot(1, "action", 1.0, None, "SC01_SH03",
              "Hitler đóng ví, cất vào túi."),
        _shot(2, "narration", 9.0, 2, "SC02_SH01"),
        _shot(3, "action", 1.5, None, "SC03_SH01",
              "Hitler ngồi trước bàn gỗ."),
        _shot(3, "narration", 7.0, 3),
        _shot(3, "action", 2.5, None, "SC03_SH02",
              "Ngòi bút tiếp xúc mặt giấy."),
        _shot(3, "action", 1.5, None, "SC03_SH03",
              "Hitler cầm tờ đơn lên."),
        _shot(4, "dialogue", 2.0, 4, "SC04_SH01"),
        _shot(4, "dialogue", 1.5, 5, "SC04_SH02"),
        _shot(4, "dialogue", 2.5, 6, "SC04_SH03"),
        _shot(4, "dialogue", 2.0, 7, "SC04_SH04"),
        _shot(5, "narration", 8.0, 8),
        # SC05_SH02 deliberately carries no plan-shot id: it anchors
        # via its V1 shot TRIGGER LINE_ID (see v1_scene shots below).
        _shot(5, "action", 4.0, None, None,
              "Đoàn binh lính hành quân trên đường đất."),
        _shot(6, "narration", 9.0, 9),
        _shot(6, "action", 2.0, None, "SC06_SH02",
              "Hitler bước qua lối đi đầy bùn."),
        _shot(6, "action", 2.0, None, "SC06_SH03",
              "Hitler giật mình, cúi người."),
        _shot(6, "action", 1.5, None, "SC06_SH04",
              "Hitler ngẩng đầu, nhìn về xa."),
    ]
    clock = build_shot_clock(shots)
    entries = []
    for span in clock["shot_spans"]:
        shot = span["shot"]
        if shot["kind"] != "action":
            entries.append({
                "line_index": shot["line_index"],
                "start": span["start"],
                "end": round(span["start"] + shot["duration"] - 0.35, 3),
                "duration": round(shot["duration"] - 0.35, 3)})
    line_scenes = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4, 6: 4, 7: 4, 8: 5, 9: 6}
    scenes = []
    for number in range(1, 7):
        spoken = [{"line_id": f"EP01_FP_0{i}", "speaker": "Adolf Hitler",
                   "text": "x", "kind": "narration",
                   "scene_number": number}
                  for i, sc in line_scenes.items() if sc == number]
        v1_shots = [{"id": s["v1_shot_id"]}
                    for s in shots
                    if s["scene"] == number and s.get("v1_shot_id")]
        if number == 4:
            # SFX: NONE on every dialogue shot of scene 4.
            v1_shots = [{**s, "sfx_none": True} for s in v1_shots]
        if number == 5:
            v1_shots.append(
                {"id": "SC05_SH02",
                 "trigger": "EP01_FP_08 — “Trung đoàn Bộ binh”"})
        scenes.append({
            "number": number,
            "action_text": " ".join(
                s["action_text"] for s in shots if s["scene"] == number),
            "v1_scene": {
                "number": number, "spoken_lines": spoken,
                "shots": v1_shots, "sfx_none": False,
                "ambience_none": number == 2, "bgm_none": False,
                "meme_none": True}})
    package = {"scenes": scenes, "v1_audio_cues": cues,
               "v1_meta": {"meme_policy": "NONE"}}
    return package, shots, entries, cues


class TestEp1NewDialectOffline(unittest.TestCase):
    def test_new_script_cue_resolution_counts(self):
        package, shots, entries, cues = _new_dialect_fixture()
        rep = resolve_v1_cues(cues, package=package, shots=shots,
                              timeline_entries=entries, rainy=False)
        self.assertEqual(rep["total_cues"], 18)
        self.assertEqual(rep["rendered_cues"], 18)
        self.assertEqual(rep["unrendered_cues"], 0)
        self.assertEqual(rep["counts_by_type"]["SFX"],
                         {"total": 7, "rendered": 7, "unrendered": 0})
        self.assertEqual(len(rep["segments"]), 7)
        by_id = {s["cue_id"]: s for s in rep["segments"]}
        # Owning-shot anchors + durations from the script.
        self.assertEqual(by_id["SFX_001"]["at_seconds"], 10.0)
        self.assertEqual(by_id["SFX_001"]["duration"], 0.4)
        self.assertEqual(by_id["SFX_001"]["synth_kind"], "soft_rustle")
        self.assertEqual(by_id["SFX_001"]["gain_db"], -22.0)  # LOW
        self.assertEqual(by_id["SFX_002"]["synth_kind"], "paper_rustle")
        # ACTION_DURATION spans the owning shot (30.0 -> 32.5).
        self.assertEqual((by_id["SFX_003"]["at_seconds"],
                          by_id["SFX_003"]["end_seconds"]),
                         (30.0, 32.5))
        self.assertEqual(by_id["SFX_003"]["synth_kind"],
                         "writing_scratch")
        self.assertEqual(by_id["SFX_006"]["synth_kind"], "mud_squelch")
        self.assertEqual(by_id["SFX_007"]["synth_kind"],
                         "artillery_rumble")
        self.assertEqual(by_id["SFX_007"]["gain_db"], -16.0)  # MODERATE
        # SFX_005 anchors via the shot TRIGGER LINE_ID (no plan id).
        sfx5 = next(c for c in rep["cues"]
                    if c["cue_id"] == "SFX_005")
        self.assertEqual(sfx5["trigger"]["method"],
                         "owning_shot_line_anchor")
        self.assertEqual(sfx5["trigger"]["start"], 42.0)
        # BGM: 6 pads; SC06 fades down; SC04 very low.
        music = [b for b in rep["beds"] if b["stem"] == "music"]
        self.assertEqual(len(music), 6)
        sc6_pad = next(b for b in music if b["scene"] == 6)
        self.assertTrue(sc6_pad["fade_down"])
        self.assertEqual(sc6_pad["gain_db"], -24.0)
        sc4_pad = next(b for b in music if b["scene"] == 4)
        self.assertEqual(sc4_pad["gain_db"], -24.0)
        # Ambience: SC02 NONE span recorded; SC06 gets rain + rumble.
        self.assertEqual(rep["none_spans"]["ambience"], [[12.5, 21.5]])
        sc6_beds = {b["synth_kind"] for b in rep["beds"]
                    if b["scene"] == 6 and b["stem"] == "ambience"}
        self.assertEqual(sc6_beds, {"rain_bed", "artillery_rumble"})
        json.dumps(rep, ensure_ascii=False)

    def test_shot_level_none_suppresses_new_dialect_cue(self):
        package, shots, entries, cues = _new_dialect_fixture()
        extra = {"cue_type": "SFX", "cue_id": "SFX_008",
                 "event": "Test knock", "trigger": "PROP_TEST",
                 "cue_type_text": "Door knock", "intensity": "LOW",
                 "duration": "0.4s", "scene_number": 4,
                 "shot_id": "SC04_SH01"}
        rep = resolve_v1_cues(cues + [extra], package=package,
                              shots=shots, timeline_entries=entries)
        self.assertEqual(rep["total_cues"], 19)
        suppressed = next(c for c in rep["cues"]
                          if c["cue_id"] == "SFX_008")
        self.assertEqual(suppressed["render"], "unrendered")
        self.assertIn("SC04_SH01", suppressed["reasons"][0])


class TestEp1RealPackageOffline(unittest.TestCase):
    """New-dialect authoritative script through the REAL parser +
    adapter + plan_shots clock (no rendering). This is the redirect
    offline check: 18 cues (7 SFX + 5 AMBIENCE + 6 BGM), real cue
    shapes, real scene flags (sfx_none on scenes 1/4/6 collapsed
    from shot-level NONE lines)."""

    def test_real_package_cue_resolution(self):
        text = (REPO_ROOT / "examples"
                / "hitler_ep01_munich_1914.studio.md").read_text(
                    encoding="utf-8")
        package, label, _detail = resolve_v1_plan(text)
        self.assertEqual(label, "v1")
        cues = package["v1_audio_cues"]
        self.assertEqual(len(cues), 18)
        # Adapter contract my stage 6/7 pause line reads: numeric
        # pause_after_sec on every package line; 0.6 on the last
        # scene-4 line (POST_DIALOGUE_PAUSE), 0.35 elsewhere.
        pauses = {}
        for scene in package["scenes"]:
            for line in scene["lines"]:
                pauses[line["line_id"]] = line["pause_after_sec"]
        self.assertEqual(len(pauses), 9)
        self.assertEqual(pauses["EP01_FP_07"], 0.6)
        for line_id, pause in pauses.items():
            if line_id != "EP01_FP_07":
                self.assertEqual(pause, 0.35)
        # Real plan_shots clock with synthetic measured durations.
        flat = []
        for scene in package["scenes"]:
            flat.extend(scene["lines"])
        timeline = [{"line_index": i + 1, "duration": 4.0}
                    for i in range(len(flat))]
        shots = plan_shots(package, timeline)
        clock = build_shot_clock(shots)
        by_index = {e["line_index"]: dict(e) for e in timeline}
        entries = []
        for span in clock["shot_spans"]:
            shot = span["shot"]
            if shot["kind"] != "action" \
                    and shot.get("line_index") is not None:
                entry = by_index[shot["line_index"]]
                entry["start"] = span["start"]
                entry["end"] = round(span["start"] + entry["duration"],
                                     3)
                entries.append(entry)
        entries.sort(key=lambda e: e["line_index"])
        line_starts = {e["line_index"]: e["start"] for e in entries}
        rep = resolve_v1_cues(cues, package=package, shots=shots,
                              timeline_entries=entries, rainy=True)
        self.assertEqual(rep["total_cues"], 18)
        self.assertEqual(rep["rendered_cues"], 18)
        self.assertEqual(rep["unrendered_cues"], 0)
        # The deterministic planner lists all 7 SFX + 5 AMBIENCE
        # cues as unmapped (no engine SFX event); that listing is
        # advisory — audio-stage mapping applies and is recorded.
        self.assertTrue(rep["trait_blocks_present"])
        by_id = {c["cue_id"]: c for c in rep["cues"]}
        self.assertEqual(by_id["SFX_001"]["mapping"]["source"],
                         "keyword")
        self.assertTrue(any("lists this cue as unmapped" in r
                            for r in by_id["SFX_001"]["reasons"]))
        bgm = next(c for c in rep["cues"]
                   if c["cue_type"] == "BGM")
        self.assertEqual(bgm["mapping"]["source"], "trait_blocks")
        self.assertEqual(rep["counts_by_type"]["SFX"],
                         {"total": 7, "rendered": 7, "unrendered": 0})
        self.assertEqual(rep["counts_by_type"]["AMBIENCE"],
                         {"total": 5, "rendered": 5, "unrendered": 0})
        self.assertEqual(rep["counts_by_type"]["BGM"],
                         {"total": 6, "rendered": 6, "unrendered": 0})
        self.assertEqual(len(rep["segments"]), 7)
        # 5 ambience cues -> 6 beds (SC06 splits rain + rumble),
        # 6 BGM cues -> 6 pads.
        self.assertEqual(len(rep["beds"]), 12)
        # SFX_001 renders DESPITE scene 1 sfx_none=True: the flag is
        # shot-scoped NONE collapsed to scene level (SC01_SH03),
        # and the cue belongs to SC01_SH02. Same for SFX_006/007
        # in scene 6 (NONE on SC06_SH04 only).
        for cue_id in ("SFX_001", "SFX_006", "SFX_007"):
            self.assertEqual(by_id[cue_id]["render"], "rendered")
            self.assertTrue(any("coexists" in r
                                for r in by_id[cue_id]["reasons"]))
        # The only scene-wide SFX NONE span is scene 4 (flag + zero
        # SFX cues); scenes 1/6 yield no span (coexistence).
        scene_spans = clock["scene_spans"]
        self.assertEqual(
            rep["none_spans"]["sfx"],
            [[scene_spans[4][0], scene_spans[4][1]]])
        # Anchoring: line-anchored owning shots; SFX_004 (no trigger
        # anchor on SC03_SH03) falls back to the recorded scene
        # start; ACTION_DURATION without a known span uses the
        # default stem length with a note.
        for cue_id, line_idx in (("SFX_001", 1), ("SFX_002", 2),
                                 ("SFX_003", 3), ("SFX_005", 8),
                                 ("SFX_006", 9), ("SFX_007", 9)):
            trig = by_id[cue_id]["trigger"]
            self.assertEqual(trig["method"],
                             "owning_shot_line_anchor", cue_id)
            self.assertEqual(trig["start"], line_starts[line_idx],
                             cue_id)
        self.assertEqual(by_id["SFX_004"]["trigger"]["method"],
                         "scene_start_fallback")
        segs = {s["cue_id"]: s for s in rep["segments"]}
        self.assertEqual(segs["SFX_003"]["duration"], 1.0)
        self.assertEqual(segs["SFX_005"]["duration"], 2.0)
        self.assertTrue(any("ACTION_DURATION" in r and "default" in r
                            for r in by_id["SFX_003"]["reasons"]))
        # SC02 ambience NONE (scene-wide: no ambience cue there)
        # yields the only ambience NONE span; SC06 pad fades down.
        self.assertEqual(len(rep["none_spans"]["ambience"]), 1)
        sc6_pad = next(b for b in rep["beds"]
                       if b["stem"] == "music" and b["scene"] == 6)
        self.assertTrue(sc6_pad["fade_down"])
        # End card carries BGM/SFX NONE and no bed/segment extends
        # past the last content shot: the 3s card shot stays in the
        # clock (the mix pads to total length) but outside every
        # scene span, so the card is silent by construction.
        card = package["v1_end_card"]
        self.assertEqual(card["bgm"], "NONE")
        self.assertEqual(card["sfx"], "NONE")
        content_end = max(span["end"] for span in clock["shot_spans"]
                          if span["shot"].get("kind") != "end_card")
        total_end = max(span["end"] for span in clock["shot_spans"])
        self.assertEqual(total_end, round(content_end + 3.0, 3))
        self.assertTrue(all(b["end"] <= content_end + 0.001
                            for b in rep["beds"]))
        self.assertTrue(all(s["at_seconds"] + s["duration"]
                            <= content_end + 0.001
                            for s in rep["segments"]))
        sc6_bed_ends = {b["end"] for b in rep["beds"]
                        if b["scene"] == 6}
        self.assertEqual(sc6_bed_ends, {content_end})
        json.dumps(rep, ensure_ascii=False)


# Shots carrying an explicit "SFX: NONE" line in the authoritative
# Ep1 v2 script (examples/hitler_ep01_munich_1914.studio.md):
# SC01_SH03 (line 688), SC04_SH01 (883), SC04_SH02 (907),
# SC04_SH03 (931), SC04_SH04 (958), SC06_SH04 (1153). The END_CARD
# SFX: NONE (line 1179) is not a shot. The adapter collapses
# shot-level NONE to the scene sfx_none flag and emits no per-shot
# flag, so these tests pin the attribution the resolver CAN see:
# no scripted SFX cue is attached to one of these shots, and no
# segment job carries one of these shot ids.
EP1_SFX_NONE_SHOTS = frozenset({
    "SC01_SH03", "SC04_SH01", "SC04_SH02", "SC04_SH03",
    "SC04_SH04", "SC06_SH04",
})


class TestEp1V2Stage3Continuation(unittest.TestCase):
    """Stage 3 continuation requirements, checked on the real Ep1
    v2 package (parser + adapter + plan_shots clock, no rendering)
    and on the resolver fixture. rainy=True matches the real
    product flow (scene 6 carries the 'rain' action cue)."""

    def _real_ep1(self):
        text = (REPO_ROOT / "examples"
                / "hitler_ep01_munich_1914.studio.md").read_text(
                    encoding="utf-8")
        package, label, _detail = resolve_v1_plan(text)
        self.assertEqual(label, "v1")
        flat = []
        for scene in package["scenes"]:
            flat.extend(scene["lines"])
        timeline = [{"line_index": i + 1, "duration": 4.0}
                    for i in range(len(flat))]
        shots = plan_shots(package, timeline)
        clock = build_shot_clock(shots)
        by_index = {e["line_index"]: dict(e) for e in timeline}
        entries = []
        for span in clock["shot_spans"]:
            shot = span["shot"]
            if shot["kind"] != "action" \
                    and shot.get("line_index") is not None:
                entry = by_index[shot["line_index"]]
                entry["start"] = span["start"]
                entry["end"] = round(span["start"] + entry["duration"],
                                     3)
                entries.append(entry)
        entries.sort(key=lambda e: e["line_index"])
        rep = resolve_v1_cues(
            package["v1_audio_cues"], package=package, shots=shots,
            timeline_entries=entries, rainy=True)
        total_sec = clock["total_shot_sec"] + 0.5
        content_end = max(
            span["end"] for span in clock["shot_spans"]
            if span["shot"].get("kind") != "end_card")
        return package, shots, clock, entries, rep, total_sec, \
            content_end

    def test_all_seven_sfx_segments_inside_timeline(self):
        _, _, clock, _, rep, total_sec, content_end = self._real_ep1()
        self.assertEqual(len(rep["segments"]), 7)
        cue_ids = [s["cue_id"] for s in rep["segments"]]
        self.assertEqual(sorted(cue_ids),
                         [f"SFX_00{i}" for i in range(1, 8)])
        self.assertEqual(len(set(cue_ids)), 7)  # no duplicates
        for seg in rep["segments"]:
            with self.subTest(cue_id=seg["cue_id"]):
                self.assertGreaterEqual(seg["at_seconds"], 0.0)
                self.assertGreater(seg["end_seconds"],
                                   seg["at_seconds"])
                self.assertLessEqual(seg["end_seconds"], total_sec)
                # No segment extends into the end card.
                self.assertLessEqual(seg["end_seconds"],
                                     content_end + 0.001)
                self.assertGreater(seg["duration"], 0.0)
                self.assertIn("shot_id", seg)
        for bed in rep["beds"]:
            with self.subTest(bed=(bed["stem"], bed["synth_kind"],
                                   bed["scene"])):
                self.assertGreaterEqual(bed["start"], 0.0)
                self.assertGreater(bed["end"], bed["start"])
                self.assertLessEqual(bed["end"], content_end + 0.001)
                self.assertIn("shot_id", bed)

    def test_sfx_none_shots_produce_no_sfx_jobs(self):
        package, _, clock, _, rep, _, _ = self._real_ep1()
        sfx_cues = [c for c in package["v1_audio_cues"]
                    if c["cue_type"] == "SFX"]
        self.assertEqual(len(sfx_cues), 7)
        for cue in sfx_cues:
            self.assertNotIn(cue["shot_id"], EP1_SFX_NONE_SHOTS)
        self.assertEqual(
            {s["shot_id"] for s in rep["segments"]},
            {"SC01_SH02", "SC02_SH01", "SC03_SH02", "SC03_SH03",
             "SC05_SH02", "SC06_SH02", "SC06_SH03"})
        for seg in rep["segments"]:
            self.assertNotIn(seg["shot_id"], EP1_SFX_NONE_SHOTS)
        # Scene 4 (SFX: NONE on every shot, zero SFX cues) yields
        # the scene-wide NONE span, muting legacy/rain SFX there.
        scene_spans = clock["scene_spans"]
        self.assertEqual(
            rep["none_spans"]["sfx"],
            [[scene_spans[4][0], scene_spans[4][1]]])
        # Scoping: SFX: NONE does NOT prohibit ambience/BGM. The
        # scene-1 ambience + BGM cues sit on SC01_SH03 (an SFX:NONE
        # shot) and must still render.
        for cue_type in ("AMBIENCE", "BGM"):
            cue = next(c for c in rep["cues"]
                       if c["cue_type"] == cue_type
                       and c["shot_id"] == "SC01_SH03")
            self.assertEqual(cue["render"], "rendered", cue_type)

    def test_unresolvable_trigger_yields_no_jobs_and_v1e022(self):
        package, shots, entries = _resolver_fixture()
        cues = [
            # Unknown LINE_ID (no underscores: an underscore-shaped
            # token takes the documented SNAKE event-token path
            # with a recorded scene-start fallback instead).
            _cue(name="Heavy door knock on wood",
                 trigger="L099"),
            _cue(name="Heavy door knock on wood",
                 trigger="zebra quantum flux"),
        ]
        rep = resolve_v1_cues(cues, package=package, shots=shots,
                              timeline_entries=entries)
        # A mappable sound with an unresolvable trigger: no guessed
        # time, no job, and an explicit V1E022 review entry.
        self.assertEqual(rep["segments"], [])
        self.assertEqual(rep["beds"], [])
        self.assertEqual(len(rep["unresolved_triggers"]), 2)
        for cue_report in rep["cues"]:
            self.assertEqual(cue_report["render"], "unrendered")
            self.assertEqual(cue_report["trigger"]["status"],
                             "unresolved")
            self.assertIn("V1E022", cue_report["trigger"]["reason"])
            self.assertTrue(any("V1E022" in r
                                for r in cue_report["reasons"]))
        for entry in rep["unresolved_triggers"]:
            self.assertIn("V1E022", entry["reason"])

    def test_duplicate_bgm_cues_deduplicate_to_one_bed(self):
        package, shots, entries = _resolver_fixture()
        cue = _cue("BGM", "Soft reflective instrumental", "",
                   scene=1)
        rep = resolve_v1_cues([cue, dict(cue)], package=package,
                              shots=shots, timeline_entries=entries)
        self.assertEqual(len(rep["beds"]), 1)
        self.assertTrue(all(c["render"] == "rendered"
                            for c in rep["cues"]))
        self.assertTrue(any("deduplicated" in r
                            for r in rep["cues"][1]["reasons"]))

    def test_no_cues_no_sound_and_no_automatic_events(self):
        package, shots, entries = _resolver_fixture()
        rep = resolve_v1_cues([], package=package, shots=shots,
                              timeline_entries=entries)
        self.assertEqual(rep["total_cues"], 0)
        self.assertEqual(rep["segments"], [])
        self.assertEqual(rep["beds"], [])
        # The V1 action-cue vocabulary (walk/open/take/...) shares
        # no key with EVENT_SFX_MAP, so the legacy path invents no
        # footsteps, impacts, knocks or rain beds for V1 packages:
        # every planned event is refused as unknown.
        visual_events = [
            {"event": cue, "at_seconds": 0.0}
            for cue in ("walk", "stop", "bend_pick", "take", "open",
                        "put_away", "look", "sit", "stand", "rain")]
        plan = plan_audio_events(visual_events, script_text="")
        self.assertEqual(plan.events, [])
        self.assertEqual(len(plan.blocked_memes),
                         len(visual_events))
        self.assertTrue(all("unknown visual event" in b["reason"]
                            for b in plan.blocked_memes))
        # No whoosh anywhere in the synthesis vocabulary: automatic
        # transition whooshes are DISABLED in the script and have
        # no synthesis, no event-map entry, no code path here.
        for kind, spec in SYNTHESIS_MAP.items():
            self.assertNotIn("whoosh", kind)
            self.assertNotIn("whoosh", spec["method"].lower())
        for spec in EVENT_SFX_MAP.values():
            self.assertNotIn("WHOOSH", spec["sfx"])

    def test_bgm_nominal_chain_is_spec_default(self):
        # Nominal chain only: BGM bed gain -18 dB (SPEC default)
        # with a further -6 dB duck under speech. The MEASURED
        # RMS gap between the music stem and real VieNeu speech is
        # NOT asserted here: it depends on source levels (the
        # placeholder sine pad is far quieter than speech before
        # gains), so a 12-18 dB measured-gap assertion would be
        # fixture-fitting, not a design guarantee. The measured
        # ducking step itself is proven in
        # TestBgmDuckingMeasurement.
        gains = resolve_mix_gains(
            {"v1_global_audio": dict(SPEC_GAINS)})
        self.assertEqual(gains["ducking_db"], -6.0)
        self.assertEqual(gains["bus_gains"]["bgm_gain_db"], -18.0)
        package, shots, entries = _resolver_fixture()
        package["v1_global_audio"] = dict(SPEC_GAINS)
        rep = resolve_v1_cues(
            [_cue("BGM", "Soft reflective instrumental", "",
                  scene=1)],
            package=package, shots=shots, timeline_entries=entries)
        self.assertEqual(len(rep["beds"]), 1)
        self.assertEqual(rep["beds"][0]["gain_db"], -18.0)
        self.assertEqual(rep["beds"][0]["stem"], "music")


class TestBgmDuckingMeasurement(unittest.TestCase):
    """Measured ducking on a synthetic mix: the music stem must sit
    ~ducking_db lower inside speech windows than outside them, on
    separate stems, with the restraint check passing."""

    def test_bgm_ducking_step_measured_on_synthetic_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            v1 = _sine_wav(tmp / "v1.wav", 2.0, volume=0.5)
            v2 = _sine_wav(tmp / "v2.wav", 2.0, freq=520, volume=0.5)
            entries = [
                {"line_index": 1, "speaker": "An", "kind": "dialogue",
                 "text": "x", "wav": str(v1), "duration": 2.0,
                 "start": 0.5, "end": 2.5},
                {"line_index": 2, "speaker": "narrator",
                 "kind": "narration", "text": "y", "wav": str(v2),
                 "duration": 2.0, "start": 4.0, "end": 6.0},
            ]
            beds = [{
                "stem": "music", "synth_kind": "music_pad",
                "start": 0.0, "end": 8.5, "gain_db": -18.0,
                "method": SYNTHESIS_MAP["music_pad"]["method"],
                "cue_name": "pad", "cue_id": None, "scene": 1,
                "shot_id": None, "fade_down": False,
                "source": "bgm_pad"}]
            gains = resolve_mix_gains(
                {"v1_global_audio": dict(SPEC_GAINS)})
            _, info = _mix_audio(
                tmp, entries, 8.5, False, segments=[], beds=beds,
                mix_gains=gains, none_spans={})
            # Separate buses: voice stems + music stem, no foley
            # stem when no segments were supplied.
            self.assertEqual(set(info["stems"]),
                             {"dialogue.wav", "narration.wav",
                              "music.wav"})
            music = Path(info["stems"]["music.wav"])
            inside = _rms_db_windows(music, [(0.5, 2.5), (4.0, 6.0)])
            # Outside windows avoid the pad edge fades (0-0.2s in,
            # last 0.35s out) and the duck-window edges.
            outside = _rms_db_windows(music, [(2.6, 3.9),
                                              (6.1, 8.0)])
            self.assertIsNotNone(inside)
            self.assertIsNotNone(outside)
            step = outside - inside
            # Resolved ducking is -6 dB; allow measurement slack
            # for window-edge/rounding effects.
            self.assertGreaterEqual(step, 4.0)
            self.assertLessEqual(step, 8.0)
            # Dialogue stays intelligible: restraint holds.
            self.assertTrue(info["restraint"]["ok"])
            self.assertGreaterEqual(
                info["restraint"]["gaps_db"]["music.wav"], 6.0)


if __name__ == "__main__":
    unittest.main()
