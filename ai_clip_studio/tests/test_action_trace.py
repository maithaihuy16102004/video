"""Source-to-render action trace (integration sprint section 4).

Every mandatory action must survive script -> semantic parser ->
adapter -> scene graph -> compiler -> planner -> renderer -> video
with its actual frame range, or be named as a gap / classified
unsupported. Fixtures use the real artifact shapes (copied from
job req_1dd4aed1b2e1); one test runs the trace over the real legacy
Zeus job dir, where the parser/graph artifacts do not exist.
"""

import json
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_trace import STAGES, build_action_trace

AGENT = Path(__file__).resolve().parent.parent.parent

EVENT = {
    "action_id": "SC01_SH01_ACT01", "action_type": "TAKE_FROM_POCKET",
    "actor_id": "CHAR_GARDENER", "target_id": None,
    "prop_id": "PROP_KEY", "start_time": 1.0, "end_time": 2.0,
    "shot_id": "SC01_SH01", "scene_number": 1,
    "directive_text": "Bà Tư lấy chìa khóa từ túi áo",
    "notes": ["trait-derived"],
}
UNSUP = {
    "action_id": "SC01_SH02_ACT01", "category": "UNCLEAR",
    "reason": "no action mapping for this scripted sentence",
    "directive_text": "Bà Tư đọc thư, mỉm cười.",
    "shot_id": "SC01_SH02", "scene_number": 1, "source_line": 42,
}
CLASSIFICATION = {
    "entries": [{**UNSUP, "handling_class": "VOCABULARY_GAP",
                 "handling": "action sentence with no verb mapping "
                             "-- unstaged; listed in the coverage "
                             "report"}],
    "counts": {"VOCABULARY_GAP": 1}, "warnings": ["SC01_SH02_ACT01"],
}


def _job(tmp, *, dispatch=True, plan=True, motion=True, graph=True,
         sem=True, event_start=1.0, event_end=2.0):
    root = Path(tmp)
    package = {
        "scenes": [{"number": 1, "scene_id": "SC01",
                    "action_text": "Bà Tư lấy chìa khóa từ túi áo. "
                                   "Bà Tư đọc thư, mỉm cười."}],
        "shot_directives": [{"shot_id": "SC01_SH01", "scene": 1},
                            {"shot_id": "SC01_SH02", "scene": 1}],
        "shots": [],
    }
    (root / "scene_package.json").write_text(
        json.dumps(package), encoding="utf-8")
    if sem:
        (root / "semantic_actions.json").write_text(json.dumps([{
            "source_shot_id": "SC01_SH01",
            "source_text": "Bà Tư lấy chìa khóa từ túi áo",
            "action_type": "TAKE_FROM_POCKET"}]), encoding="utf-8")
    if graph:
        (root / "scene_graph.json").write_text(json.dumps({
            "events": {"SC01_SH01_ACT01": {"action_id":
                                           "SC01_SH01_ACT01"}},
            "semantic_actions": {"SC01_SH01_ACT01": {}},
            "unsupported": [dict(UNSUP)]}), encoding="utf-8")
    event = dict(EVENT, start_time=event_start, end_time=event_end)
    (root / "action_events.json").write_text(json.dumps({
        "events": [event], "unsupported": [dict(UNSUP)],
        "spans_supplied": True, "compile_error": None,
        "unsupported_classification": CLASSIFICATION}),
        encoding="utf-8")
    shots = [{"scene": 1, "kind": "action", "duration": 3.0,
              "start_sec": 0.0,
              "event_ids": ["SC01_SH01_ACT01"] if plan else [],
              "action_text": "Bà Tư lấy chìa khóa từ túi áo."},
             {"scene": 1, "kind": "action", "duration": 2.0,
              "start_sec": 3.0, "event_ids": [],
              "action_text": "Bà Tư đọc thư, mỉm cười."}]
    (root / "timeline.json").write_text(
        json.dumps({"shots": shots}), encoding="utf-8")
    if motion:
        frames = root / "frames"
        frames.mkdir(exist_ok=True)
        (frames / "motion_report.json").write_text(json.dumps({
            "fps": 24, "total_frames": 120,
            "shots": [{"index": 0, "scene": 1,
                       "action_event_ids":
                           ["SC01_SH01_ACT01"] if dispatch else [],
                       "action_dispatch_fallback": []},
                      {"index": 1, "scene": 1,
                       "action_event_ids": [],
                       "action_dispatch_fallback": []}]}),
            encoding="utf-8")
    (root / "draft.mp4").write_bytes(b"fake")
    return root


class TestActionTrace(unittest.TestCase):
    def test_full_trace_with_frame_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = build_action_trace(_job(tmp))
        self.assertEqual(trace["trace_version"], 1)
        self.assertEqual(trace["fps"], 24)
        self.assertEqual(trace["total_frames"], 120)
        by_id = {i["action_id"]: i for i in trace["items"]}
        event = by_id["SC01_SH01_ACT01"]
        self.assertEqual(event["status"], "TRACED")
        self.assertEqual(list(event["stages"]), list(STAGES))
        self.assertTrue(all(s["present"]
                            for s in event["stages"].values()))
        self.assertEqual(event["frame_range"], [24, 48])
        self.assertEqual(event["frame_range_source"], "event_span")
        self.assertEqual(event["stages"]["planner"]["match"],
                         "event_ids")
        self.assertEqual(event["notes"], ["trait-derived"])
        self.assertEqual(trace["summary"]["traced"], 1)
        self.assertEqual(trace["gaps"], [])

    def test_unsupported_listed_with_handling_and_shot_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = build_action_trace(_job(tmp))
        by_id = {i["action_id"]: i for i in trace["items"]}
        item = by_id["SC01_SH02_ACT01"]
        self.assertEqual(item["status"], "UNSUPPORTED_VOCABULARY_GAP")
        self.assertEqual(item["handling_class"], "VOCABULARY_GAP")
        self.assertIn("no verb mapping", item["handling"])
        # Owning shot: 3.0-5.0 s -> frames [72, 120).
        self.assertEqual(item["frame_range"], [72, 120])
        self.assertEqual(item["frame_range_source"], "owning_shot")
        self.assertTrue(item["stages"]["script"]["present"])
        self.assertTrue(item["stages"]["compiler"]["present"])
        self.assertFalse(item["stages"]["renderer"]["present"])
        # Classified unsupported is not a gap.
        self.assertEqual(trace["gaps"], [])
        self.assertEqual(
            trace["summary"]["unsupported_by_class"],
            {"VOCABULARY_GAP": 1})

    def test_renderer_gap_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = build_action_trace(_job(tmp, dispatch=False))
        event = trace["items"][0]
        self.assertEqual(event["status"], "GAP_AT_renderer")
        self.assertFalse(event["stages"]["renderer"]["present"])
        self.assertFalse(event["stages"]["video"]["present"])
        self.assertEqual(len(trace["gaps"]), 1)
        self.assertEqual(trace["gaps"][0]["stage"], "renderer")
        self.assertEqual(trace["gaps"][0]["action_id"],
                         "SC01_SH01_ACT01")

    def test_planner_gap_when_no_membership_or_overlap(self):
        # Event span 10-11 s: outside every timeline shot, and no
        # event_ids membership -> the planner never placed it.
        with tempfile.TemporaryDirectory() as tmp:
            trace = build_action_trace(
                _job(tmp, plan=False, event_start=10.0,
                     event_end=11.0))
        event = trace["items"][0]
        self.assertEqual(event["status"], "GAP_AT_planner")

    def test_overlap_match_counts_as_planned(self):
        # No event_ids membership, but the span overlaps shot 0.
        with tempfile.TemporaryDirectory() as tmp:
            trace = build_action_trace(_job(tmp, plan=False))
        event = trace["items"][0]
        self.assertEqual(event["status"], "TRACED")
        self.assertEqual(event["stages"]["planner"]["match"],
                         "overlap")

    def test_missing_motion_report_gaps_renderer_and_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = build_action_trace(_job(tmp, motion=False))
        event = trace["items"][0]
        self.assertEqual(event["status"], "GAP_AT_renderer")
        self.assertFalse(
            trace["artifacts_present"]["frames/motion_report.json"])

    def test_missing_graph_gaps_scene_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = build_action_trace(_job(tmp, graph=False))
        event = trace["items"][0]
        # semantic_actions.json still proves the parser stage.
        self.assertTrue(
            event["stages"]["semantic_parser"]["present"])
        self.assertEqual(event["status"], "GAP_AT_scene_graph")

    def test_empty_job_dir_reports_no_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = build_action_trace(tmp)
        self.assertEqual(trace["items"], [])
        self.assertEqual(trace["summary"]["events"], 0)
        self.assertTrue(all(not v for v in
                            trace["artifacts_present"].values()))

    def test_legacy_zeus_job_dir(self):
        # Real artifacts from job req_e0b777f729a5 (pre-upgrade: no
        # semantic_actions.json, no scene_graph.json). Every compiled
        # event must gap at the parser stage honestly; every
        # unsupported entry must be classified and listed.
        job_dir = AGENT / "jobs" / "req_e0b777f729a5"
        trace = build_action_trace(job_dir)
        self.assertEqual(trace["summary"]["events"], 56)
        self.assertEqual(trace["summary"]["unsupported"], 100)
        self.assertEqual(len(trace["items"]), 156)
        self.assertEqual(trace["summary"]["traced"], 0)
        self.assertEqual(len(trace["gaps"]), 56)
        self.assertTrue(all(g["stage"] == "semantic_parser"
                            for g in trace["gaps"]))
        for item in trace["items"]:
            self.assertEqual(list(item["stages"]), list(STAGES))
            if item["kind"] == "unsupported":
                self.assertTrue(item["status"].startswith(
                    "UNSUPPORTED_"))
                self.assertTrue(item["handling"])


if __name__ == "__main__":
    unittest.main()
