"""Round-6 staging variation: repeated stagings get distinct
viewpoints by cut (azimuth-side alternation), and the
staging-duplication detector measures the result.

The defect: shots sharing one staging signature rendered from
the same azimuth-0 viewpoint, so the cut changed nothing (R5:
14 pairs MAD < 12, worst #12->#13 at 1.60). The signature
excludes the subject -- R5 #12/#13 had different subjects yet
MAD 1.60, which is also why the subject-scoped
repeated-framing warning missed them.

Round 9 (F9): the alternation extends to EVERY eligible shot.
Round 6 only flipped repeats, so a plan with all-distinct
signatures (Loop-01) rendered every shot from azimuth 0 --
the zoom-only defect. Eligible shots now alternate +1/-1
within a scene; repeats escalate to an unused side. First
occurrences carry a side (no longer None).
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from ai_clip_studio.camera_planner import (
    _pose_angles, plan_shot, viewpoint_for_shot)
from ai_clip_studio.product_renderer import plan_shots
from ai_clip_studio.staging_duplication_audit import (
    MAD_THRESHOLD, audit_staging_duplication, flag_duplicate_pairs)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

LOOP01 = Path(__file__).resolve().parents[2] / "examples" / \
    "loop_test_01_fire_stone.studio.md"
EXEMPT_TYPES = ("establishing", "object_insert", "over_the_shoulder",
                "shot_reverse_shot", "graphic_insert")


class TestViewpointAzimuthSide(unittest.TestCase):
    def test_none_reproduces_legacy_position(self):
        base = viewpoint_for_shot("medium", None,
                                  subject_pos=(0.0, 1.2, 0.0))
        flipped = viewpoint_for_shot(
            "medium", None, subject_pos=(0.0, 1.2, 0.0),
            azimuth_side=None)
        self.assertEqual(base.position, flipped.position)
        self.assertEqual(base.position, (0.0, 2.0, 4.8))

    def test_sides_swing_symmetric_azimuth_steps(self):
        target = (0.0, 1.2, 0.0)
        _az, base_elev, base_radius = _pose_angles(
            viewpoint_for_shot("medium", None, subject_pos=target))
        for side, expected_deg in ((1, 18.0), (-1, -18.0),
                                   (2, 36.0), (-2, -36.0)):
            camera = viewpoint_for_shot(
                "medium", None, subject_pos=target,
                azimuth_side=side)
            azimuth, elevation, radius = _pose_angles(camera)
            self.assertAlmostEqual(azimuth, expected_deg, places=6)
            # Elevation and radius unchanged: an azimuth-only move
            # (compared against the unflipped camera, not a
            # guessed constant -- the legacy offset's length is
            # an implementation detail).
            self.assertAlmostEqual(radius, base_radius, places=6)
            self.assertAlmostEqual(elevation, base_elev, places=6)

    def test_side_never_overrides_ots_or_srs_azimuth(self):
        target = (0.0, 1.2, 0.0)
        ots = viewpoint_for_shot(
            "over_the_shoulder", None, subject_pos=target,
            counterpart_x=1.0)
        ots_flipped = viewpoint_for_shot(
            "over_the_shoulder", None, subject_pos=target,
            counterpart_x=1.0, azimuth_side=2)
        self.assertEqual(ots.position, ots_flipped.position)
        srs = viewpoint_for_shot(
            "shot_reverse_shot", None, subject_pos=target, srs_side=1)
        srs_flipped = viewpoint_for_shot(
            "shot_reverse_shot", None, subject_pos=target, srs_side=1,
            azimuth_side=-2)
        self.assertEqual(srs.position, srs_flipped.position)

    def test_plan_shot_pose_reflects_the_side(self):
        entry = plan_shot({
            "shot_id": "S1", "shot_type": "medium",
            "viewpoint_azimuth_side": 1,
            "subject": "Linh", "location": "forge"})
        self.assertAlmostEqual(
            entry["pose"]["azimuth_deg"], 18.0, places=6)
        plain = plan_shot({
            "shot_id": "S2", "shot_type": "medium",
            "subject": "Linh", "location": "forge"})
        self.assertAlmostEqual(
            plain["pose"]["azimuth_deg"], 0.0, places=6)


def _loop01_shots():
    package = adapt_document(parse_studio_script_v1(
        LOOP01.read_text(encoding="utf-8")))
    return plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(7)])


class TestPlannerSideAlternation(unittest.TestCase):
    def test_repeat_occurrences_get_distinct_sides(self):
        shots = _loop01_shots()
        groups = {}
        for shot in shots:
            if (shot["kind"] == "end_card"
                    or shot["shot_type"] in EXEMPT_TYPES):
                continue
            loc = shot.get("v1_location")
            loc_key = str(loc.get("id") or loc.get("location_id")
                          or "") if isinstance(loc, dict) else ""
            sig_type = ("medium" if shot["shot_type"] == "tracking"
                        else shot["shot_type"])
            key = (shot["scene"], sig_type,
                   tuple(shot.get("visible") or ()), loc_key)
            groups.setdefault(key, []).append(shot)
        multi = [g for g in groups.values() if len(g) > 1]
        # The fixture must actually exercise repetition, or the
        # distinctness assertions below prove nothing.
        self.assertTrue(multi)
        for group in multi:
            sides = [s.get("viewpoint_azimuth_side") for s in group]
            for side in sides:
                self.assertIn(side, (1, -1, 2, -2))
            self.assertEqual(len(set(sides)), len(sides),
                             "same-signature shots share a viewpoint")

    def test_exempt_types_carry_no_side(self):
        shots = _loop01_shots()
        exempt = [s for s in shots
                  if s["shot_type"] in EXEMPT_TYPES
                  or s["kind"] == "end_card"]
        self.assertTrue(exempt)
        for shot in exempt:
            self.assertNotIn("viewpoint_azimuth_side", shot)

    def test_first_occurrences_get_alternation_sides(self):
        # Round 9 (F9): first occurrences carry the scene
        # alternation side (+1/-1), never None -- the zoom-only
        # defect was exactly that every first occurrence stayed
        # frontal.
        shots = _loop01_shots()
        seen = set()
        firsts = 0
        for shot in shots:
            if (shot["kind"] == "end_card"
                    or shot["shot_type"] in EXEMPT_TYPES):
                continue
            loc = shot.get("v1_location")
            loc_key = str(loc.get("id") or loc.get("location_id")
                          or "") if isinstance(loc, dict) else ""
            sig_type = ("medium" if shot["shot_type"] == "tracking"
                        else shot["shot_type"])
            key = (shot["scene"], sig_type,
                   tuple(shot.get("visible") or ()), loc_key)
            if key not in seen:
                seen.add(key)
                firsts += 1
                self.assertIn(
                    shot.get("viewpoint_azimuth_side"), (1, -1))
        self.assertTrue(firsts)

    def test_every_scene_with_eligible_shots_varies_viewpoint(self):
        shots = _loop01_shots()
        per_scene = {}
        for shot in shots:
            if (shot["kind"] == "end_card"
                    or shot["shot_type"] in EXEMPT_TYPES):
                continue
            per_scene.setdefault(shot["scene"], []).append(
                shot.get("viewpoint_azimuth_side"))
        self.assertTrue(per_scene)
        for scene, sides in per_scene.items():
            for side in sides:
                self.assertIn(side, (1, -1, 2, -2))
            if len(sides) > 1:
                self.assertGreater(
                    len(set(sides)), 1,
                    f"scene {scene}: no viewpoint variation")


class TestDuplicationDetector(unittest.TestCase):
    def _probe(self, value):
        return np.full((90, 160), float(value), dtype=np.float32)

    def test_identical_pair_flagged_distinct_pair_not(self):
        pairs = flag_duplicate_pairs([
            (0, self._probe(100)), (1, self._probe(100)),
            (2, self._probe(200))])
        self.assertEqual(
            [(p["a"], p["b"]) for p in pairs], [(0, 1)])
        self.assertEqual(pairs[0]["mad"], 0.0)
        self.assertTrue(pairs[0]["adjacent"])

    def test_non_adjacent_repeat_flagged(self):
        pairs = flag_duplicate_pairs([
            (0, self._probe(50)), (1, self._probe(200)),
            (2, self._probe(50))])
        self.assertEqual(len(pairs), 1)
        self.assertEqual((pairs[0]["a"], pairs[0]["b"]), (0, 2))
        self.assertFalse(pairs[0]["adjacent"])

    def test_threshold_is_the_pinned_tester_value(self):
        self.assertEqual(MAD_THRESHOLD, 12.0)
        just_under = flag_duplicate_pairs([
            (0, self._probe(100)), (1, self._probe(111))])
        just_over = flag_duplicate_pairs([
            (0, self._probe(100)), (1, self._probe(113))])
        self.assertEqual(len(just_under), 1)
        self.assertEqual(len(just_over), 0)

    def test_job_dir_audit_clusters_triplets(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp)
            frames = job / "frames"
            for index, value in enumerate((80, 80, 80, 200)):
                shot_dir = frames / ("shot_%03d" % index)
                shot_dir.mkdir(parents=True)
                Image.new("L", (320, 180), value).save(
                    shot_dir / "f0000.png")
                Image.new("L", (320, 180), value).save(
                    shot_dir / "f0001.png")
            (job / "timeline.json").write_text(json.dumps(
                {"shots": [{}, {}, {}, {}]}), encoding="utf-8")
            report = audit_staging_duplication(job)
        self.assertEqual(report["shots_measured"], 4)
        self.assertEqual(report["pairs_flagged"], 3)
        self.assertEqual(report["triplets_or_larger"], [[0, 1, 2]])
        self.assertFalse(report["passed"])

    def test_job_dir_audit_skips_shots_without_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp)
            shot_dir = job / "frames" / "shot_000"
            shot_dir.mkdir(parents=True)
            Image.new("L", (320, 180), 90).save(
                shot_dir / "f0000.png")
            (job / "timeline.json").write_text(json.dumps(
                {"shots": [{}, {}]}), encoding="utf-8")
            report = audit_staging_duplication(job)
        self.assertEqual(report["shots_measured"], 1)
        self.assertEqual(report["shots_skipped"], [1])
        self.assertTrue(report["passed"])


if __name__ == "__main__":
    unittest.main()
