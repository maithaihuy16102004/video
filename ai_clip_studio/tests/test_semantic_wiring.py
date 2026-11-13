"""Semantic wiring (A2 item 3): per-shot cue records, conflict sinks,
losing-cue discard.

The adapter attaches provenance-carrying cue records per shot; the
pipeline runs the conflict mechanism before staging (early pass) and
again with real spans (7a); a cue that loses to a higher-authority
compiled event is discarded from the scene's action_cues so it can
never shape a shot.
"""

import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from ai_clip_studio import product_flow
from ai_clip_studio.action_compiler import (
    LEVEL_AUTHORITY, compile_actions)
from ai_clip_studio.semantic_contracts import (
    ActionAuthority, ConflictRecord)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.tests.test_unauthorized_story_change import _stub_tts

AGENT = Path(__file__).resolve().parent.parent.parent


def _package(name):
    doc = parse_studio_script_v1(
        (AGENT / "examples" / f"{name}.studio.md").read_text(
            encoding="utf-8"))
    return adapt_document(doc)


class TestPerShotCueRecords(unittest.TestCase):
    def test_records_cover_tags_and_carry_provenance(self):
        for name in ("hitler_ep01_munich_1914",
                     "zeus_ep01_fall_of_cronus"):
            pkg = _package(name)
            for scene in pkg["scenes"]:
                records = scene.get("cue_records")
                self.assertIsInstance(records, list, name)
                # Every staging tag has a provenance record. Records
                # may carry extra tags: the tag extractor suppresses
                # "walk" when "walk_fast" fires in the JOINED text,
                # while per-shot extraction sees each shot alone.
                tags = set(scene.get("action_cues", []))
                record_tags = {r["cue"] for r in records}
                self.assertLessEqual(tags, record_tags, name)
                for rec in records:
                    self.assertEqual(
                        rec["source_scene_id"],
                        f"SC{scene['number']:02d}", name)
                    self.assertEqual(
                        rec["action_origin"],
                        "PLANNER_INFERRED_ACTION", name)
                    self.assertEqual(
                        rec["authorization_status"], "INFERRED", name)

    def test_ep1_scene1_records_are_story_correct(self):
        pkg = _package("hitler_ep01_munich_1914")
        records = pkg["scenes"][0]["cue_records"]
        cues = [r["cue"] for r in records]
        self.assertIn("head_tilt", cues)
        self.assertIn("take_out", cues)
        self.assertNotIn("bend_pick", cues)
        by_shot = {}
        for rec in records:
            by_shot.setdefault(rec["source_shot_id"], []).append(
                rec["cue"])
        self.assertIn("head_tilt", by_shot["SC01_SH01"])
        self.assertIn("take_out", by_shot["SC01_SH02"])
        self.assertIn("put_away", by_shot["SC01_SH03"])


class TestDiscardLosingCues(unittest.TestCase):
    def _record(self, entity, description, winner):
        return ConflictRecord(
            level_a="cues", level_b="compiled_events",
            entity_id=entity, description=description,
            mandatory=True, winner_authority=winner)

    def test_losing_cue_removed_from_its_scene_only(self):
        package = {"scenes": [
            {"number": 1, "action_cues": ["walk", "bend_pick", "take_out"]},
            {"number": 2, "action_cues": ["bend_pick", "walk"]},
        ]}
        events = [{"action_id": "A1", "scene_number": 1,
                   "shot_id": "SC01_SH02", "action_type": "TAKE_OUT"}]
        rec = self._record(
            "A1", "cue 'bend_pick' stages a ground pickup, but "
            "directive A1 is an explicit pocket action",
            ActionAuthority.COMPILED_EVENT)
        discards = product_flow._discard_losing_cues(
            package, [rec], events)
        self.assertEqual(package["scenes"][0]["action_cues"],
                         ["walk", "take_out"])
        self.assertEqual(package["scenes"][1]["action_cues"],
                         ["bend_pick", "walk"])
        self.assertEqual(len(discards), 1)
        self.assertTrue(discards[0]["removed"])
        self.assertEqual(discards[0]["cue"], "bend_pick")
        self.assertEqual(discards[0]["scene"], 1)

    def test_unresolved_and_winning_cues_kept(self):
        package = {"scenes": [
            {"number": 1, "action_cues": ["bend_pick"]}]}
        events = [{"action_id": "A1", "scene_number": 1,
                   "shot_id": "SC01_SH02"}]
        unresolved = self._record("A1", "cue 'bend_pick' stages x", None)
        winner = self._record(
            "A1", "cue 'bend_pick' stages x",
            ActionAuthority.PLANNER_SUGGESTION)
        discards = product_flow._discard_losing_cues(
            package, [unresolved, winner], events)
        self.assertEqual(package["scenes"][0]["action_cues"],
                         ["bend_pick"])
        self.assertEqual(discards, [])

    def test_unresolvable_scope_never_guesses(self):
        package = {"scenes": [
            {"number": 1, "action_cues": ["bend_pick"]}]}
        rec = self._record(
            "NO_SUCH_ACTION", "cue 'bend_pick' stages x",
            ActionAuthority.COMPILED_EVENT)
        discards = product_flow._discard_losing_cues(package, [rec], [])
        self.assertEqual(package["scenes"][0]["action_cues"],
                         ["bend_pick"])
        self.assertEqual(discards[0]["reason"], "unresolved")


class TestConflictMechanismEndToEnd(unittest.TestCase):
    def test_injected_bend_pick_loses_to_pocket_event(self):
        pkg = _package("hitler_ep01_munich_1914")
        records = [r for s in pkg["scenes"]
                   for r in s.get("cue_records", [])]
        injected = {
            "cue": "bend_pick", "matched_text": "cúi xuống nhặt ví",
            "match_start": 0, "match_end": 18,
            "pattern": "test-injected", "source_script_hash": "test",
            "source_scene_id": "SC01", "source_shot_id": "SC01_SH02",
            "source_directive_id": None,
            "action_origin": "PLANNER_INFERRED_ACTION",
            "inference_reason": "injected contradiction for the test",
            "authorization_status": "INFERRED"}
        # Simulate the old extractor's tag output for this shot.
        pkg["scenes"][0]["action_cues"].append("bend_pick")
        sem_sink, con_sink = [], []
        events, _unsupported = compile_actions(
            pkg, inferred_cues=records + [injected],
            semantic_sink=sem_sink, conflict_sink=con_sink)
        self.assertTrue(sem_sink)
        r1 = [r for r in con_sink
              if "bend_pick" in r.description]
        self.assertEqual(len(r1), 1)
        self.assertEqual(r1[0].winner_authority,
                         ActionAuthority.COMPILED_EVENT)
        self.assertFalse(r1[0].fails_preflight)
        discards = product_flow._discard_losing_cues(
            pkg, con_sink, events)
        self.assertNotIn("bend_pick",
                         pkg["scenes"][0]["action_cues"])
        self.assertTrue(any(d.get("removed") for d in discards))

    def test_ep1_job_persists_semantic_sinks(self):
        script = (AGENT / "examples"
                  / "hitler_ep01_munich_1914.studio.md").read_text(
                      encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            with mock.patch.object(product_flow, "tts_cli_provider",
                                   side_effect=_stub_tts), \
                mock.patch.object(
                    product_flow, "emit_job_spec",
                    side_effect=RuntimeError("STOP_AFTER_7A")):
                job = product_flow.run_product_job(
                    script, job_dir, upload=False)
            stages = {s["stage"]: s for s in job.stages}
            self.assertEqual(stages["semantic_conflicts"]["status"],
                             "done")
            self.assertIn("STOP_AFTER_7A", job.errors[0])
            early = json.loads(
                (job_dir / "semantic_conflicts_early.json").read_text(
                    encoding="utf-8"))
            self.assertIsInstance(early, list)
            actions = json.loads(
                (job_dir / "semantic_actions.json").read_text(
                    encoding="utf-8"))
            self.assertTrue(actions)
            for rec in actions:
                self.assertIn("action_type", rec)
                self.assertIn("source_directive_id", rec)
                self.assertIn("source_text", rec)
            conflicts = json.loads(
                (job_dir / "semantic_conflicts.json").read_text(
                    encoding="utf-8"))
            self.assertIsInstance(conflicts, list)
            self.assertIn("discarded_cues", job.package)


if __name__ == "__main__":
    unittest.main()
