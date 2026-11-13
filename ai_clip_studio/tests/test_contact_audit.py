"""Whole-sequence prop contact audit (integration sprint P1, sec 10).

Fabricated telemetry in the exact shape the renderer records, plus
the spec-invariant check (the grip point lies on the drawn shape)
and the telemetry-less legacy job dir.
"""

import json
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.contact_audit import (
    _fingertip_on_shape, _spec_shapes, audit_prop_contact)

AGENT = Path(__file__).resolve().parent.parent.parent
H = 560.0  # hand_size = 0.07 * 560 = 39.2 px


def _hands(hand_r=(500.0, 500.0), elbow_r=(500.0, 400.0)):
    return {
        "An": {"hand_l": [400.0, 500.0], "hand_r": list(hand_r),
               "elbow_l": [400.0, 400.0], "elbow_r": list(elbow_r),
               "head_r": 95.0, "H": H},
        "Bình": {"hand_l": [700.0, 500.0], "hand_r": [700.0, 500.0],
                 "elbow_l": [700.0, 400.0], "elbow_r": [700.0, 400.0],
                 "head_r": 95.0, "H": H},
    }


def _draw(pid="PROP_WALLET", kind="wallet", holder="An", hand="r",
          x=500.0, y=500.0, state="ATTACHED_TO_HAND", angle=0.0,
          open_u=0.0, repaint=True):
    return {"pid": pid, "kind": kind, "state": state,
            "holder": holder, "hand": hand, "x": x, "y": y,
            "angle": angle, "open_u": open_u, "grip_repaint": repaint}


def _job(tmp, telemetry, events):
    root = Path(tmp)
    (root / "frames").mkdir()
    (root / "frames" / "motion_report.json").write_text(json.dumps({
        "fps": 24, "total_frames": len(telemetry),
        "shots": [{"index": 0, "grip_telemetry": telemetry}]}),
        encoding="utf-8")
    (root / "action_events.json").write_text(
        json.dumps({"events": events, "unsupported": []}),
        encoding="utf-8")
    (root / "scene_package.json").write_text(json.dumps({
        "v1_characters": [{"id": "CHAR_A", "name": "An"},
                          {"id": "CHAR_B", "name": "Bình"}],
        "props": [{"id": "PROP_WALLET", "kind": "wallet"},
                  {"id": "PROP_BOLT", "kind": "bolt"}]}),
        encoding="utf-8")
    return root


def _frames(n, draw_fn, hands_fn=_hands):
    out = []
    for i in range(n):
        t = round(i / 24.0, 4)
        out.append({"t": t, "frame": i, "hands": hands_fn(),
                    "draws": draw_fn(t, i)})
    return out


class TestContactAudit(unittest.TestCase):
    def test_clean_hold_passes_with_zero_gap(self):
        event = {"action_id": "E1", "action_type": "HOLD",
                 "actor_id": "CHAR_A", "prop_id": "PROP_WALLET",
                 "start_time": 0.0, "end_time": 1.0}
        telemetry = _frames(24, lambda t, i: [_draw()])
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_prop_contact(_job(tmp, telemetry, [event]))
        self.assertTrue(report["passed"], report["failures"])
        item = report["interactions"][0]
        self.assertEqual(item["metrics"]["gap_px_mean"], 0.0)
        self.assertEqual(item["metrics"]["gap_norm_mean"], 0.0)
        self.assertEqual(item["metrics"]["visibility"], 1.0)
        self.assertEqual(
            item["metrics"]["grip_repaint_fraction"], 1.0)
        self.assertEqual(item["metrics"]["penetration_mean"], 1.0)
        self.assertEqual(item["metrics"]["holder_match"], 1.0)

    def test_distant_prop_fails_gap(self):
        event = {"action_id": "E1", "action_type": "HOLD",
                 "actor_id": "CHAR_A", "prop_id": "PROP_WALLET",
                 "start_time": 0.0, "end_time": 1.0}
        telemetry = _frames(
            24, lambda t, i: [_draw(x=700.0, y=500.0)])
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_prop_contact(_job(tmp, telemetry, [event]))
        self.assertFalse(report["passed"])
        item = report["interactions"][0]
        self.assertAlmostEqual(item["metrics"]["gap_norm_mean"],
                               200.0 / 39.2, places=2)
        self.assertTrue(any("grip gap" in f for f in
                            report["failures"]))

    def test_duplicate_draws_fail(self):
        event = {"action_id": "E1", "action_type": "HOLD",
                 "actor_id": "CHAR_A", "prop_id": "PROP_WALLET",
                 "start_time": 0.0, "end_time": 1.0}
        telemetry = _frames(24, lambda t, i: [_draw(), _draw()])
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_prop_contact(_job(tmp, telemetry, [event]))
        self.assertFalse(report["passed"])
        self.assertEqual(
            report["interactions"][0]["metrics"]["duplicate_frames"],
            24)

    def test_transfer_transition_detected(self):
        handover = {"action_id": "E1", "action_type": "HAND_OVER",
                    "actor_id": "CHAR_A", "recipient_id": "CHAR_B",
                    "prop_id": "PROP_WALLET",
                    "start_time": 0.0, "end_time": 1.0}
        receive = {"action_id": "E2", "action_type": "RECEIVE_PROP",
                   "actor_id": "CHAR_B", "prop_id": "PROP_WALLET",
                   "start_time": 1.0, "end_time": 2.0}

        def draws(t, i):
            holder = "An" if t < 1.0 else "Bình"
            hand = (500.0, 500.0) if holder == "An" else (700.0, 500.0)
            return [_draw(holder=holder, x=hand[0], y=hand[1])]

        def hands():
            base = _hands()
            return base

        telemetry = _frames(48, draws, hands)
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_prop_contact(
                _job(tmp, telemetry, [handover, receive]))
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(
            report["interactions"][0]["metrics"]["transition_t"], 1.0)

    def test_transfer_without_switch_fails(self):
        handover = {"action_id": "E1", "action_type": "HAND_OVER",
                    "actor_id": "CHAR_A", "recipient_id": "CHAR_B",
                    "prop_id": "PROP_WALLET",
                    "start_time": 0.0, "end_time": 1.0}
        telemetry = _frames(24, lambda t, i: [_draw()])
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_prop_contact(_job(tmp, telemetry, [handover]))
        self.assertFalse(report["passed"])
        self.assertTrue(any("never transferred" in f for f in
                            report["failures"]))

    def test_wallet_open_series(self):
        event = {"action_id": "E1", "action_type": "OPEN",
                 "actor_id": "CHAR_A", "prop_id": "PROP_WALLET",
                 "start_time": 0.0, "end_time": 1.0}
        telemetry = _frames(
            24, lambda t, i: [_draw(open_u=i / 23.0)])
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_prop_contact(_job(tmp, telemetry, [event]))
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(
            report["interactions"][0]["metrics"]["open_u_last"], 1.0)
        stuck = _frames(24, lambda t, i: [_draw(open_u=0.0)])
        with tempfile.TemporaryDirectory() as tmp:
            stuck_report = audit_prop_contact(
                _job(tmp, stuck, [event]))
        self.assertFalse(stuck_report["passed"])

    def test_transfer_transit_frames_excluded_from_gap(self):
        # Zeus cup handover: the prop travels 0 -> 300 px from the
        # giver's hand while TRANSFERRED, then lands gap-0 in the
        # recipient's hand. Transit distance is not grip error.
        handover = {"action_id": "E1", "action_type": "HAND_OVER",
                    "actor_id": "CHAR_A", "recipient_id": "CHAR_B",
                    "prop_id": "PROP_WALLET",
                    "start_time": 0.0, "end_time": 1.5}

        def draws(t, i):
            if i < 12:
                return [_draw(holder="An", x=500.0, y=500.0)]
            if i < 36:
                x = 500.0 + (i - 11) * 8.0
                return [_draw(holder="An", x=x, y=500.0,
                              state="TRANSFERRED", repaint=False)]
            return [_draw(holder="Bình", x=700.0, y=500.0)]

        telemetry = _frames(48, draws)
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_prop_contact(
                _job(tmp, telemetry, [handover]))
        self.assertTrue(report["passed"], report["failures"])
        item = report["interactions"][0]
        self.assertGreater(item["metrics"]["transit_frames"], 0)
        self.assertEqual(item["metrics"]["gap_norm_mean"], 0.0)
        self.assertEqual(
            item["metrics"]["transition_t"], 1.5)

    def test_finger_strokes_cross_thin_shape_endpoints_miss(self):
        # Forearm horizontal, bolt shaft vertical through the grip:
        # the stroke endpoints sit 21 px past the shaft (endpoint
        # test reads 0.0) but every stroke starts on the shape.
        event = {"action_id": "E1", "action_type": "HOLD",
                 "actor_id": "CHAR_A", "prop_id": "PROP_BOLT",
                 "start_time": 0.0, "end_time": 1.0}
        hands = _hands(hand_r=(500.0, 500.0),
                       elbow_r=(400.0, 500.0))
        telemetry = _frames(
            24, lambda t, i: [_draw(pid="PROP_BOLT", kind="bolt")],
            lambda: hands)
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_prop_contact(_job(tmp, telemetry, [event]))
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(
            report["interactions"][0]["metrics"]["penetration_mean"],
            1.0)

    def test_grip_point_lies_on_the_drawn_shape(self):
        # Spec invariant: the grip contact (the origin after the
        # renderer's translate) must sit on the shape, or every
        # hold of that kind measures as floating.
        for kind in ("bolt", "hammer", "trident", "helmet"):
            shapes = _spec_shapes(kind)
            self.assertTrue(_fingertip_on_shape((0.0, 0.0), shapes),
                            kind)

    def test_legacy_job_without_telemetry_reports_honestly(self):
        report = audit_prop_contact(AGENT / "jobs" / "req_e0b777f729a5")
        self.assertFalse(report["summary"]["telemetry_present"])
        self.assertFalse(report["passed"])
        self.assertGreater(len(report["interactions"]), 0)
        self.assertTrue(all("no grip telemetry" in f
                            for i in report["interactions"]
                            for f in i["failures"]))


if __name__ == "__main__":
    unittest.main()
