"""Shot Planner V2 tests (Cinematic Engine Upgrade, Phase B).

Covers: every SHOT directive shapes exactly one shot (the old code
used only scene_directives[0], silently dropping Ep1 SC01_SH03,
SC03_SH03, SC06_SH03, SC06_SH04); total-duration preservation;
long-line splitting over one uninterrupted narration; hook/reveal
records; pairing/duration/repeated-framing warnings; camera mode
intent vs execution; cut boundaries + locomotion direction.
"""

import unittest
from collections import Counter
from pathlib import Path

from ai_clip_studio.product_renderer import plan_shots
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.subtitles import split_subtitle

AGENT = Path(__file__).resolve().parent.parent.parent


def _package(name):
    doc = parse_studio_script_v1(
        (AGENT / "examples" / f"{name}.studio.md").read_text(
            encoding="utf-8"))
    return adapt_document(doc)


def _plan(pkg, durations):
    n_lines = sum(len(sc["lines"]) for sc in pkg["scenes"])
    timeline = [{"line_index": i + 1,
                 "duration": durations[i] if i < len(durations)
                 else 0.65}
                for i in range(n_lines)]
    return plan_shots(pkg, timeline)


class TestDirectiveConsumption(unittest.TestCase):
    def test_ep1_all_17_directives_consumed(self):
        pkg = _package("hitler_ep01_munich_1914")
        shots = _plan(pkg, [0.65] * 9)
        declared = {d["shot_id"] for d in pkg["shot_directives"]}
        consumed = Counter(s.get("directive_shot_id") for s in shots
                           if s.get("directive_shot_id"))
        self.assertEqual(len(declared), 17)
        self.assertEqual(set(consumed), declared)
        # Scene-level directives shape exactly one shot each.
        for did in ("SC01_SH02", "SC01_SH03", "SC03_SH02", "SC03_SH03",
                    "SC05_SH02", "SC06_SH02", "SC06_SH03", "SC06_SH04"):
            self.assertEqual(consumed[did], 1, did)
        self.assertEqual(len(shots), 21)  # 23 before the A2
        # phrase-aware cue fix + head_tilt wiring (2026-11-12): the
        # SC01 lead distribution merged (bend_pick/take lead shots
        # gone; walk/head_tilt/stop/take_out/open/look/put_away) and
        # two default lead shots disappeared. All 17 directives still
        # consumed exactly as asserted above; total duration preserved.

    def test_zeus_all_41_directives_consumed(self):
        pkg = _package("zeus_ep01_fall_of_cronus")
        shots = _plan(pkg, [0.65] * 40)
        declared = {d["shot_id"] for d in pkg["shot_directives"]}
        consumed = {s.get("directive_shot_id") for s in shots
                    if s.get("directive_shot_id")}
        self.assertEqual(len(declared), 41)
        self.assertEqual(consumed, declared)
        self.assertEqual(len(shots), 64)  # 63 before the A2
        # phrase-aware cue fix + head_tilt wiring (2026-11-12): one
        # extra default lead segment from the new cue distribution.
        # All 41 directives still consumed exactly once, every
        # directive shot's type matches its directive, and the total
        # duration is preserved (verified by probe).

    def test_total_duration_preserved(self):
        for name, n in (("hitler_ep01_munich_1914", 9),
                        ("zeus_ep01_fall_of_cronus", 40)):
            pkg = _package(name)
            shots = _plan(pkg, [0.65] * n)
            leads = sum(float(sc.get("action_lead_sec") or 0)
                        for sc in pkg["scenes"]
                        if float(sc.get("action_lead_sec") or 0) > 0.3)
            card = 3.0 if "hitler" in name else 4.0
            expected = round(n * 1.15 + leads + card, 2)
            self.assertAlmostEqual(
                sum(s["duration"] for s in shots), expected, places=2)

    def test_test_c_indices_stable(self):
        # The TEST C proof addresses shots by plan index. The indices
        # shifted by the A2 phrase-aware cue fix + head_tilt wiring
        # (2026-11-12): two fewer lead shots before scene 4, so the
        # SC04 directive sequence (SRS -> OTS -> reaction) moved from
        # 13-15 to 11-13. The sequence itself and the anchor shots
        # (0/4/10) are unchanged; re-pin the measured positions.
        pkg = _package("hitler_ep01_munich_1914")
        shots = _plan(pkg, [0.65] * 9)
        want = {0: "close_up", 4: "establishing", 10: "medium",
                11: "shot_reverse_shot", 12: "over_the_shoulder",
                13: "reaction"}
        for idx, st in want.items():
            self.assertEqual(shots[idx]["shot_type"], st, idx)


class TestLineSplitting(unittest.TestCase):
    def _line_shots(self, voice):
        pkg = _package("hitler_ep01_munich_1914")
        shots = _plan(pkg, [voice] + [0.65] * 8)
        return [s for s in shots if s.get("line_index") == 1]

    def test_12s_line_splits_into_4(self):
        segs = self._line_shots(12.0)
        self.assertEqual(len(segs), 4)
        self.assertEqual([s["segment_count"] for s in segs], [4] * 4)
        self.assertEqual([s["segment_index"] for s in segs],
                         [0, 1, 2, 3])
        self.assertEqual([s["voice_duration"] for s in segs],
                         [3.0, 3.0, 3.0, 3.0])
        self.assertEqual([s["voice_offset_sec"] for s in segs],
                         [0.0, 3.0, 6.0, 9.0])
        self.assertAlmostEqual(sum(s["duration"] for s in segs), 12.35)
        # The beat lands only on the last segment.
        self.assertEqual(
            [s["duration_breakdown"]["beat_sec"] for s in segs],
            [0.0, 0.0, 0.0, 0.35])
        # The directive type anchors the first segment; the rest
        # progress (visual variety, no repeats in a row).
        self.assertEqual(segs[0]["shot_type"], "establishing")
        self.assertEqual(segs[0]["shot_type_source"], "directive")
        types = [s["shot_type"] for s in segs]
        for a, b in zip(types, types[1:]):
            self.assertNotEqual(a, b)

    def test_phrases_partition_exactly_once(self):
        pkg = _package("hitler_ep01_munich_1914")
        full = pkg["scenes"][0]["lines"][0]["text"]
        segs = self._line_shots(12.0)
        joined = []
        for s in segs:
            joined.extend(split_subtitle(s["text"]) if s["text"] else [])
        self.assertEqual(joined, split_subtitle(full))

    def test_split_thresholds(self):
        self.assertEqual(len(self._line_shots(6.0)), 1)
        self.assertEqual(len(self._line_shots(6.2)), 2)
        self.assertEqual(len(self._line_shots(7.0)), 2)
        self.assertEqual(len(self._line_shots(11.0)), 4)

    def test_split_segments_render(self):
        # Renderer compatibility: split segments render as stills
        # (no crash, one frozen crop each, subtitles per segment).
        import tempfile
        from ai_clip_studio.product_renderer import _render_shot
        pkg = _package("hitler_ep01_munich_1914")
        shots = _plan(pkg, [12.0] + [0.65] * 8)
        segs = [s for s in shots if s.get("line_index") == 1]
        self.assertEqual(len(segs), 4)
        for i, shot in enumerate(segs):
            shot = dict(shot)
            shot["index"] = i
            rep = _render_shot({"shot": shot, "package": pkg,
                                "out_dir": tempfile.mkdtemp(),
                                "still_only": True})
            self.assertTrue(rep["crop_frozen"])
            self.assertEqual(rep["shot_type"], shot["shot_type"])


class TestPolicyRecords(unittest.TestCase):
    def test_pairing_warning_on_close_up_walk(self):
        pkg = _package("hitler_ep01_munich_1914")
        shots = _plan(pkg, [0.65] * 9)
        self.assertIn("close_up", shots[0]["pairing_warning"])
        self.assertIn("walk", shots[0]["pairing_warning"])
        # A medium lead shot on the same walk carries no warning.
        self.assertIsNone(shots[11]["pairing_warning"])

    def test_duration_warning_and_justification(self):
        pkg = _package("hitler_ep01_munich_1914")
        # 5.8 s voice + beat = 6.15 s shot: warns (medium line 3).
        shots = _plan(pkg, [0.65, 0.65, 5.8] + [0.65] * 6)
        line3 = [s for s in shots if s.get("line_index") == 3][0]
        self.assertIsNotNone(line3["duration_warning"])
        # An establishing shot over 6 s is justified (reveal).
        shots = _plan(pkg, [5.8] + [0.65] * 8)
        line1 = [s for s in shots if s.get("line_index") == 1][0]
        self.assertEqual(line1["shot_type"], "establishing")
        self.assertIsNone(line1["duration_warning"])

    def test_hook_and_reveal(self):
        pkg = _package("hitler_ep01_munich_1914")
        shots = _plan(pkg, [0.65] * 9)
        self.assertTrue(shots[0]["is_hook_shot"])
        self.assertEqual(shots[0]["hook_type"], "character_reaction")
        self.assertIsNone(shots[0]["hook_warning"])
        reveals = [s for s in shots if s["is_reveal_shot"]]
        self.assertEqual(len(reveals), 1)
        self.assertEqual(reveals[0]["line_index"], 9)
        self.assertEqual(reveals[0]["reveal_type"], "twist")
        # Zeus opens on a medium lead shot: hook warning, no forcing.
        pkg = _package("zeus_ep01_fall_of_cronus")
        shots = _plan(pkg, [0.65] * 40)
        self.assertIsNone(shots[0]["hook_type"])
        self.assertIsNotNone(shots[0]["hook_warning"])
        reveals = [s for s in shots if s["is_reveal_shot"]]
        self.assertEqual(len(reveals), 1)
        self.assertEqual(reveals[0]["line_index"], 40)

    def test_reveal_lands_on_last_segment_of_split_twist(self):
        pkg = _package("hitler_ep01_munich_1914")
        shots = _plan(pkg, [0.65] * 8 + [12.0])
        segs = [s for s in shots if s.get("line_index") == 9]
        self.assertEqual(len(segs), 4)
        self.assertEqual([s["is_reveal_shot"] for s in segs],
                         [False, False, False, True])

    def test_repeated_framing_flags_identical_pair(self):
        pkg = _package("hitler_ep01_munich_1914")
        shots = _plan(pkg, [0.65] * 9)
        # SC06_SH03 + SC06_SH04: consecutive close_ups, same
        # viewpoint AND same crop scale — the cut changes nothing.
        by_id = {s.get("directive_shot_id"): s for s in shots}
        warn = by_id["SC06_SH04"]["repeated_framing_warning"]
        self.assertIn("changes nothing", warn)
        # SC04_SH01 (new scene/location) is NOT flagged.
        self.assertIsNone(
            by_id["SC04_SH01"]["repeated_framing_warning"])

    def test_camera_mode_intent_vs_execution(self):
        pkg = _package("hitler_ep01_munich_1914")
        shots = _plan(pkg, [0.65] * 9)
        by_id = {s.get("directive_shot_id"): s for s in shots}
        tracking = by_id["SC01_SH01"]
        self.assertEqual(tracking["camera_movement"], "TRACKING")
        self.assertEqual(tracking["camera_mode"], "scripted_tracking")
        self.assertEqual(tracking["camera_mode_execution"], "static")
        self.assertEqual(tracking["camera_mode_source"],
                         "directive:SC01_SH01")
        self.assertIn("§5.3", tracking["camera_mode_note"])
        dolly = by_id["SC02_SH01"]
        self.assertEqual(dolly["camera_mode"], "scripted_dolly")
        static = by_id["SC04_SH01"]
        self.assertEqual(static["camera_mode"], "static_anchored")
        self.assertIsNone(static["camera_mode_note"])

    def test_cut_boundaries_and_locomotion_direction(self):
        pkg = _package("hitler_ep01_munich_1914")
        shots = _plan(pkg, [0.65] * 9)
        self.assertFalse(shots[0]["cut_before"])
        self.assertTrue(all(s["cut_before"] for s in shots[1:]))
        self.assertIn(shots[0]["locomotion_direction"], (-1, 1))
        self.assertIsNone(shots[4]["locomotion_direction"])

    def test_duplicate_directive_first_wins_and_warns(self):
        pkg = _package("hitler_ep01_munich_1914")
        dup = dict(pkg["shot_directives"][0])
        dup["shot_id"] = "SC01_SH01_DUP"
        dup["shot_type"] = "reaction"
        pkg["shot_directives"] = [pkg["shot_directives"][0], dup] \
            + pkg["shot_directives"][1:]
        shots = _plan(pkg, [0.65] * 9)
        line1 = [s for s in shots if s.get("line_index") == 1][0]
        self.assertEqual(line1["shot_type"], "establishing")
        self.assertIn("SC01_SH01_DUP",
                      line1["directive_collision_warning"])


if __name__ == "__main__":
    unittest.main()
