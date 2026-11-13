"""P9 coverage-audit tests: synthetic job dirs + the real Ep1 v2 baseline."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ai_clip_studio.coverage_audit import audit_coverage

REPO = Path(__file__).resolve().parents[2]
V2_JOB = REPO / "jobs" / "req_c4f037b79499"


def _write(job_dir: Path, name: str, data) -> None:
    path = job_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _package(*, directive_status="rendered"):
    return {
        "scenes": [{
            "number": 1, "title": "Opening",
            "location": {"v1_location": {"location_id": "LOC_A"}},
            "props": ["prop_wallet"],
            "lines": [
                {"line_id": "L1", "kind": "narration", "text": "Xin chào.",
                 "speaker": "Mara", "speaker_id": "CHAR_MARA",
                 "expression": "thinking"},
                {"line_id": "L2", "kind": "dialogue",
                 "text": "Chào bạn.", "speaker": "Theo",
                 "speaker_id": "CHAR_THEO", "expression": ""},
            ],
        }],
        "shot_directives": [{
            "shot_id": "SC01_SH01", "scene": 1, "shot_type": "medium",
            "camera_angle": "eye_level"}],
        "props": [{"id": "prop_wallet", "name": "PROP_WALLET"},
                  {"id": "prop_rock", "name": "PROP_ROCK"}],
        "v1_locations": [{"id": "LOC_A", "name": "Somewhere"}],
    }


def _motion(*, dispatched=("SC01_SH01_ACT01",), fallback=(),
            prop_draws=(("prop_wallet", "ATTACHED_TO_HAND"),),
            archetype="EUROPEAN_STREET_1900"):
    return {
        "fps": 24, "total_frames": 72,
        "shots": [{
            "index": 0, "scene": 1, "kind": "narration",
            "shot_type": "medium", "duration": 3.0, "n_frames": 72,
            "action_event_ids": list(dispatched),
            "action_dispatch_fallback": list(fallback),
            "prop_draws": [list(d) for d in prop_draws],
            "environment_archetype": archetype,
        }],
    }


def _accounting(status="rendered"):
    return {"entries": [{
        "directive_id": "SC01_SH01", "status": status,
        "frame_range": [0, 72], "shot_indices": [0]}]}


def _actions(*, overflow=False, span_source="supplied"):
    return {
        "events": [{
            "action_id": "SC01_SH01_ACT01", "action_type": "PICK_UP",
            "actor_id": "CHAR_MARA", "prop_id": "prop_wallet",
            "start_time": 0.5, "end_time": 1.5,
            "overflow": overflow, "span_source": span_source}],
        "unsupported": [{
            "action_id": "SC01_SH01_ACT99", "category": "MAP",
            "source_text": "Show the map.",
            "reason": "map rendering is not an action primitive"}],
    }


def _subtitles():
    return [
        {"line_index": 1, "phrases": ["Xin chào."],
         "windows": [{"phrase": "Xin chào.", "start": 0.0, "end": 1.0}]},
        {"line_index": 2, "phrases": ["Chào bạn."],
         "windows": [{"phrase": "Chào bạn.", "start": 1.0, "end": 2.0}]},
    ]


def _audio_plan(render="rendered"):
    return {"v1_cue_resolution": {"cues": [{
        "cue_id": "SFX_001", "name": "Knock", "render": render,
        "reasons": [], "scene_number": 1,
        "trigger": {"status": "resolved", "start": 0.5, "end": 0.9}}]}}


def _by_category(report):
    out = {}
    for item in report["items"]:
        out.setdefault(item["category"], {})[item["id"]] = item
    return out


class TestCoverageAuditSynthetic(unittest.TestCase):
    def _job(self, tmp, **overrides):
        job_dir = Path(tmp)
        _write(job_dir, "scene_package.json", _package())
        _write(job_dir, "frames/motion_report.json", _motion())
        _write(job_dir, "camera_accounting.json", _accounting())
        _write(job_dir, "action_events.json", _actions())
        _write(job_dir, "subtitles.json", _subtitles())
        _write(job_dir, "audio_plan.json", _audio_plan())
        for name, data in overrides.items():
            if data is None:
                (job_dir / name).unlink(missing_ok=True)
            else:
                _write(job_dir, name, data)
        return job_dir

    def test_happy_path_all_implemented(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_coverage(self._job(tmp))
        by_cat = _by_category(report)
        self.assertEqual(by_cat["scene"]["SC1"]["status"], "IMPLEMENTED")
        self.assertEqual(by_cat["camera_directive"]["SC01_SH01"]["status"],
                         "IMPLEMENTED")
        self.assertEqual(by_cat["spoken_line"]["L1"]["status"], "IMPLEMENTED")
        self.assertEqual(by_cat["spoken_line"]["L2"]["status"], "IMPLEMENTED")
        self.assertEqual(by_cat["spoken_line"]["L1"]["frame_range"], [0, 24])
        self.assertEqual(by_cat["action_event"]["SC01_SH01_ACT01"]["status"],
                         "IMPLEMENTED")
        self.assertEqual(by_cat["unsupported_action"]["SC01_SH01_ACT99"]
                         ["status"], "UNSUPPORTED")
        self.assertEqual(by_cat["expression"]["L1"]["status"], "IMPLEMENTED")
        self.assertEqual(by_cat["prop"]["prop_wallet"]["status"],
                         "IMPLEMENTED")
        self.assertEqual(by_cat["prop"]["prop_rock"]["status"], "UNSUPPORTED")
        self.assertEqual(by_cat["audio_cue"]["SFX_001"]["status"],
                         "IMPLEMENTED")
        self.assertEqual(by_cat["location"]["LOC_A"]["status"], "IMPLEMENTED")

    def test_directive_statuses(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(
                tmp, **{"camera_accounting.json":
                        _accounting("not_rendered")})
            report = audit_coverage(job)
        self.assertEqual(
            _by_category(report)["camera_directive"]["SC01_SH01"]["status"],
            "FAILED")
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(
                tmp, **{"camera_accounting.json":
                        _accounting("type_defaulted")})
            report = audit_coverage(job)
        self.assertEqual(
            _by_category(report)["camera_directive"]["SC01_SH01"]["status"],
            "PARTIALLY_IMPLEMENTED")

    def test_overflow_and_estimated_events_fail_loudly(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(
                tmp,
                **{"frames/motion_report.json":
                   _motion(dispatched=()),
                   "action_events.json":
                   _actions(overflow=True)})
            report = audit_coverage(job)
        item = _by_category(report)["action_event"]["SC01_SH01_ACT01"]
        self.assertEqual(item["status"], "FAILED")
        self.assertIn("overflow", item["detail"])
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(
                tmp,
                **{"frames/motion_report.json":
                   _motion(dispatched=()),
                   "action_events.json":
                   _actions(span_source="estimated")})
            report = audit_coverage(job)
        item = _by_category(report)["action_event"]["SC01_SH01_ACT01"]
        self.assertEqual(item["status"], "FAILED")
        self.assertIn("estimated", item["detail"])

    def test_fallback_dispatch_is_partial(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(
                tmp,
                **{"frames/motion_report.json":
                   _motion(fallback=["SC01_SH01_ACT01"])})
            report = audit_coverage(job)
        item = _by_category(report)["action_event"]["SC01_SH01_ACT01"]
        self.assertEqual(item["status"], "PARTIALLY_IMPLEMENTED")

    def test_subtitle_mismatch_fails(self):
        import tempfile
        subs = _subtitles()
        subs[0]["phrases"] = ["Xin chào bạn."]
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(tmp, **{"subtitles.json": subs})
            report = audit_coverage(job)
        self.assertEqual(
            _by_category(report)["spoken_line"]["L1"]["status"], "FAILED")

    def test_missing_artifacts_fail_with_missing_evidence(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(
                tmp, **{"camera_accounting.json": None,
                        "action_events.json": None,
                        "audio_plan.json": None})
            report = audit_coverage(job)
        by_cat = _by_category(report)
        directive = by_cat["camera_directive"]["SC01_SH01"]
        self.assertEqual(directive["status"], "FAILED")
        self.assertEqual(directive["evidence_quality"], "missing")
        cue = by_cat["audio_cue"]["(all)"]
        self.assertEqual(cue["evidence_quality"], "missing")

    def test_prop_states(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(
                tmp,
                **{"frames/motion_report.json":
                   _motion(prop_draws=(("prop_wallet", "WORLD_STATIC"),))})
            report = audit_coverage(job)
        self.assertEqual(
            _by_category(report)["prop"]["prop_wallet"]["status"],
            "PARTIALLY_IMPLEMENTED")
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(
                tmp,
                **{"frames/motion_report.json": _motion(prop_draws=())})
            report = audit_coverage(job)
        self.assertEqual(
            _by_category(report)["prop"]["prop_wallet"]["status"], "FAILED")

    def test_generic_neutral_location_is_partial(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(
                tmp,
                **{"frames/motion_report.json":
                   _motion(archetype="GENERIC_NEUTRAL")})
            report = audit_coverage(job)
        self.assertEqual(
            _by_category(report)["location"]["LOC_A"]["status"],
            "PARTIALLY_IMPLEMENTED")

    def test_unknown_expression_is_partial_not_silent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pkg = _package()
            pkg["scenes"][0]["lines"][0]["expression"] = "xyzzy plugh"
            job = self._job(tmp, **{"scene_package.json": pkg})
            report = audit_coverage(job)
        item = _by_category(report)["expression"]["L1"]
        self.assertEqual(item["status"], "PARTIALLY_IMPLEMENTED")
        self.assertIn("falls back", item["detail"])


@unittest.skipUnless(V2_JOB.exists(), "delivered Ep1 v2 job dir absent")
class TestCoverageAuditV2Baseline(unittest.TestCase):
    def test_v2_baseline_totals(self):
        # Verified by ATLAS on the delivered job: lines/cues/scenes
        # implemented; directives + actions failed for missing
        # pre-recovery artifacts; locations partial (no archetype
        # evidence in pre-W2 shot reports).
        report = audit_coverage(V2_JOB)
        self.assertEqual(report["totals"], {
            "IMPLEMENTED": 35, "PARTIALLY_IMPLEMENTED": 6,
            "UNSUPPORTED": 1, "FAILED": 21})
        by_cat = _by_category(report)
        for line_id in ("EP01_FP_01", "EP01_FP_09"):
            self.assertEqual(by_cat["spoken_line"][line_id]["status"],
                             "IMPLEMENTED")
        for did in ("SC01_SH01", "SC06_SH04"):
            item = by_cat["camera_directive"][did]
            self.assertEqual(item["status"], "FAILED")
            self.assertEqual(item["evidence_quality"], "missing")


if __name__ == "__main__":
    unittest.main()
