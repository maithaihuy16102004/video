"""Shot planner rewire (directive section 10): the planner consumes
the canonical scene graph -- lead durations from compiled event
spans, event cross-references on every shot, no mechanical 2-5 s
rule -- and never filters cues (stage 2b owns that)."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import (
    _directive_event_span, plan_shots)
from ai_clip_studio.scene_graph import build_scene_graph
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent


def _package(name):
    return adapt_document(parse_studio_script_v1(
        (AGENT / "examples" / f"{name}.studio.md").read_text(
            encoding="utf-8")))


def _graph(package):
    sem: list = []
    events, unsupported = compile_actions(package, semantic_sink=sem)
    return build_scene_graph(package, events, semantic_actions=sem,
                             unsupported=unsupported)


def _node(verb, start, end, actor="CHAR_A", action_id="X"):
    return {"verb": verb, "start_time": start, "end_time": end,
            "actor_id": actor, "action_id": action_id}


class TestDirectiveEventSpan(unittest.TestCase):
    def test_distinct_verbs_chain(self):
        nodes = [_node("STOP", 0.0, 0.6, action_id="A1"),
                 _node("TAKE_OUT", 0.6, 1.4, action_id="A2"),
                 _node("OPEN_WALLET", 1.4, 2.2, action_id="A3")]
        self.assertAlmostEqual(_directive_event_span(nodes), 2.2)

    def test_sustained_action_collapses(self):
        # Four WALK_MUD events describing one trudge: one span.
        nodes = [_node("WALK_MUD", 0.0 + 2.4 * i, 2.4 + 2.4 * i,
                       action_id=f"A{i}") for i in range(4)]
        self.assertAlmostEqual(_directive_event_span(nodes), 2.4)

    def test_actors_run_concurrently(self):
        nodes = [_node("MARCH", 0.0, 1.6, actor="CHAR_S",
                       action_id="S1"),
                 _node("MARCH", 1.6, 3.2, actor="CHAR_H",
                       action_id="H1"),
                 _node("CARRY", 3.2, 4.2, actor="CHAR_H",
                       action_id="H2")]
        # Soldiers 1.6s, Hitler 1.6 + 1.0 = 2.6s -> max wins.
        self.assertAlmostEqual(_directive_event_span(nodes), 2.6)

    def test_separated_same_verb_counts_twice(self):
        nodes = [_node("WALK", 0.0, 1.0, action_id="A1"),
                 _node("STOP", 1.0, 1.5, action_id="A2"),
                 _node("WALK", 1.5, 2.5, action_id="A3")]
        self.assertAlmostEqual(_directive_event_span(nodes), 2.5)


class TestGraphPlans(unittest.TestCase):
    def test_ep1_lead_durations_follow_event_spans(self):
        package = _package("hitler_ep01_munich_1914")
        graph = _graph(package)
        entries = [{"line_index": i + 1, "duration": 0.65}
                   for i in range(9)]
        shots = plan_shots(package, entries, scene_graph=graph)
        self.assertEqual(len(shots), 21)
        events_by_shot = {}
        for shot_id, shot in graph["shots"].items():
            events_by_shot[shot_id] = [
                graph["events"][eid] for eid in shot["event_ids"]]
        for shot in shots:
            if shot["kind"] != "action":
                continue
            directive_id = shot.get("directive_shot_id")
            if shot["duration_source"] != "events":
                continue
            expected = round(max(
                0.5, _directive_event_span(
                    events_by_shot[directive_id])), 2)
            self.assertEqual(shot["duration"], expected, directive_id)
            self.assertEqual(
                shot["event_ids"],
                [n["action_id"]
                 for n in events_by_shot[directive_id]])
        # SC06_SH02: the sustained mud trudge is ONE span, not 4x.
        trench = next(s for s in shots
                      if s.get("directive_shot_id") == "SC06_SH02")
        self.assertEqual(trench["duration"], 2.4)
        # Staging cues survive: the planner never filters them.
        office = next(s for s in shots
                      if s.get("directive_shot_id") == "SC03_SH02")
        self.assertIn("sit", office["action_cues"])
        self.assertEqual(
            [s["dropped_cues"] for s in shots], [[]] * len(shots))

    def test_zeus_fallback_reproduces_legacy_total(self):
        package = _package("zeus_ep01_fall_of_cronus")
        graph = _graph(package)
        entries = [{"line_index": i + 1, "duration": 0.65}
                   for i in range(40)]
        legacy = plan_shots(package, entries)
        wired = plan_shots(package, entries, scene_graph=graph)
        self.assertEqual(len(wired), 64)
        self.assertAlmostEqual(
            sum(s["duration"] for s in wired),
            sum(s["duration"] for s in legacy), places=2)
        # Line shots cross-reference their directive's events.
        with_events = [s for s in wired
                       if s["kind"] != "action" and s["event_ids"]]
        self.assertEqual(len(with_events), 36)
        for shot in wired:
            self.assertEqual(shot["cue_validation"], "graph")

    def test_legacy_planning_unchanged(self):
        package = _package("hitler_ep01_munich_1914")
        entries = [{"line_index": i + 1, "duration": 0.65}
                   for i in range(9)]
        shots = plan_shots(package, entries)
        self.assertEqual(len(shots), 21)
        self.assertAlmostEqual(
            sum(s["duration"] for s in shots), 30.35, places=2)
        for shot in shots:
            self.assertEqual(shot["cue_validation"], "legacy")
            self.assertEqual(shot["event_ids"], [])

    def test_long_event_span_justifies_instead_of_warning(self):
        package = _package("hitler_ep01_munich_1914")
        graph = _graph(package)
        stretched = copy.deepcopy(graph)
        nodes = [stretched["events"][eid]
                 for eid in stretched["shots"]["SC01_SH02"]["event_ids"]]
        for i, node in enumerate(nodes):
            node["start_time"] = 2.0 * i
            node["end_time"] = 2.0 * i + 2.0
        entries = [{"line_index": i + 1, "duration": 0.65}
                   for i in range(9)]
        shots = plan_shots(package, entries, scene_graph=stretched)
        lead = next(s for s in shots
                    if s.get("directive_shot_id") == "SC01_SH02")
        self.assertEqual(lead["duration"], 8.0)
        self.assertIsNone(lead["duration_warning"])
        self.assertEqual(lead["duration_justification"],
                         "compiled event span 8.00s")

    def test_no_invented_street_default(self):
        package = _package("hitler_ep01_munich_1914")
        # Remove every declared keyword (scene locations AND trait
        # blocks, which location overrides resolve through): with no
        # declaration anywhere, the planner must report unknown (""),
        # never invent "street".
        def _strip(node):
            if isinstance(node, dict):
                node.pop("location_keyword", None)
                traits = node.get("render_traits")
                if isinstance(traits, dict):
                    traits.pop("location_keyword", None)
                for value in node.values():
                    _strip(value)
            elif isinstance(node, list):
                for value in node:
                    _strip(value)
        _strip(package)
        entries = [{"line_index": i + 1, "duration": 0.65}
                   for i in range(9)]
        shots = plan_shots(package, entries)
        for shot in shots:
            self.assertEqual(shot.get("location_keyword"), "",
                             shot.get("directive_shot_id"))


class TestJobWiring(unittest.TestCase):
    def test_ep1_job_plans_from_the_graph(self):
        from ai_clip_studio import product_flow
        from ai_clip_studio.tests.test_unauthorized_story_change import (
            _stub_tts)
        script = (AGENT / "examples"
                  / "hitler_ep01_munich_1914.studio.md").read_text(
                      encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            with mock.patch.object(product_flow, "tts_cli_provider",
                                   side_effect=_stub_tts), \
                mock.patch.object(
                    product_flow, "render_product_video",
                    side_effect=RuntimeError("STOP_AFTER_SUBTITLE")):
                job = product_flow.run_product_job(
                    script, job_dir, upload=False)
            self.assertIn("STOP_AFTER_SUBTITLE", job.errors[0])
            leads = [s for s in job.shots if s["kind"] == "action"]
            self.assertTrue(any(
                s["duration_source"] == "events" for s in leads))
            self.assertTrue(all(
                s["cue_validation"] == "graph" for s in job.shots))
            wallet_lead = next(
                s for s in job.shots
                if s.get("directive_shot_id") == "SC01_SH02")
            self.assertEqual(len(wallet_lead["event_ids"]), 4)
            self.assertNotIn("bend_pick", wallet_lead["action_cues"])


if __name__ == "__main__":
    unittest.main()
