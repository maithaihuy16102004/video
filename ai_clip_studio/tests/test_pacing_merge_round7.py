"""Round-7 pacing merge tests.

The pacing merge (_merge_short_shots) collapses short (< 2.5 s)
synthesized shots into their predecessor when the pair shares
scene/location/cast/speaker/kind and the total stays <= 6.5 s,
so the cut rhythm approaches the reference ~5-6 s per shot
without dropping or duplicating any line. Dialogue, directive
shots, inserts, and segments of one line never merge.
"""

import unittest

from ai_clip_studio.product_renderer import _merge_short_shots


def _shot(duration, shot_type="medium", directive=None, scene=1,
          loc="LOC_A", visible=("Linh", "Be Nam"), speaker="Linh",
          kind="narration", line_index=1, event_ids=(),
          cues=(), beat=0.0, voice=None):
    return {
        "scene": scene, "kind": kind, "speaker": speaker,
        "text": f"line {line_index}", "line_index": line_index,
        "duration": duration,
        "duration_breakdown": {
            "voice_sec": duration if voice is None else voice,
            "beat_sec": beat, "action_lead_sec": 0.0,
            "total_sec": duration},
        "voice_duration": duration if voice is None else voice,
        "visible": list(visible), "shot_type": shot_type,
        "v1_location": {"location_id": loc},
        "event_ids": list(event_ids),
        "action_cues": list(cues), "scene_cues": list(cues),
        "dropped_cues": [],
        **({"directive_shot_id": directive} if directive else {}),
    }


class TestPacingMerge(unittest.TestCase):
    def test_merges_short_synth_into_predecessor(self):
        shots = [_shot(3.0, line_index=1, event_ids=["e1"],
                       cues=["walk"], beat=0.35),
                 _shot(1.4, line_index=2, event_ids=["e2"],
                       cues=["look"])]
        out = _merge_short_shots(shots)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["duration"], 4.4)
        self.assertEqual(out[0]["pacing_merge"], [1.4])
        self.assertEqual(out[0]["event_ids"], ["e1", "e2"])
        self.assertEqual(out[0]["action_cues"], ["walk", "look"])
        self.assertEqual(
            out[0]["duration_breakdown"]["voice_sec"], 4.4)
        self.assertEqual(
            out[0]["duration_breakdown"]["total_sec"], 4.4)
        # The input list is untouched.
        self.assertEqual(len(shots), 2)
        self.assertNotIn("pacing_merge", shots[0])

    def test_merges_a_chain_within_the_cap(self):
        shots = [_shot(2.0, line_index=1),
                 _shot(1.2, line_index=None),
                 _shot(1.2, line_index=None),
                 _shot(1.8, line_index=None)]
        out = _merge_short_shots(shots)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["duration"], 6.2)
        self.assertEqual(out[0]["pacing_merge"], [1.2, 1.2, 1.8])

    def test_total_over_cap_stops_the_chain(self):
        shots = [_shot(5.0, line_index=1),
                 _shot(1.8, line_index=2)]
        out = _merge_short_shots(shots)
        self.assertEqual(len(out), 2)

    def test_short_threshold_is_exclusive(self):
        shots = [_shot(2.0, line_index=1),
                 _shot(2.5, line_index=2)]
        self.assertEqual(len(_merge_short_shots(shots)), 2)

    def test_directive_short_never_merges(self):
        shots = [_shot(3.0, line_index=1),
                 _shot(1.2, directive="SC01_SH02", line_index=2)]
        self.assertEqual(len(_merge_short_shots(shots)), 2)

    def test_insert_never_merges_either_side(self):
        shots = [_shot(3.0, shot_type="object_insert",
                       line_index=1),
                 _shot(1.2, line_index=2)]
        self.assertEqual(len(_merge_short_shots(shots)), 2)
        shots = [_shot(3.0, line_index=1),
                 _shot(1.0, shot_type="object_insert",
                       line_index=2)]
        self.assertEqual(len(_merge_short_shots(shots)), 2)

    def test_segments_of_one_line_keep_progression(self):
        shots = [_shot(3.0, line_index=5),
                 _shot(1.4, line_index=5)]
        self.assertEqual(len(_merge_short_shots(shots)), 2)

    def test_dialogue_cuts_are_kept(self):
        shots = [_shot(3.0, speaker="Linh", kind="narration",
                       line_index=1),
                 _shot(1.4, speaker="Ong Ba", kind="narration",
                       line_index=2)]
        self.assertEqual(len(_merge_short_shots(shots)), 2)
        shots = [_shot(3.0, speaker="Linh", kind="narration",
                       line_index=1),
                 _shot(1.4, speaker="Linh", kind="dialogue",
                       line_index=2)]
        self.assertEqual(len(_merge_short_shots(shots)), 2)

    def test_scene_location_and_cast_must_match(self):
        base = dict(duration=3.0, line_index=1)
        for kw in ({"scene": 2}, {"loc": "LOC_B"},
                   {"visible": ("Linh",)}):
            shots = [_shot(**base),
                     _shot(1.2, line_index=2, **kw)]
            self.assertEqual(len(_merge_short_shots(shots)), 2,
                             kw)

    def test_lead_shots_with_no_line_index_merge(self):
        # Action leads carry line_index None; they are distinct
        # beats, not segments of one line.
        shots = [_shot(1.92, line_index=None,
                       directive="SC01_SH02"),
                 _shot(1.44, line_index=None),
                 _shot(1.44, line_index=None)]
        out = _merge_short_shots(shots)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["duration"], 4.8)

    def test_reveal_flag_survives_the_merge(self):
        shots = [_shot(3.0, line_index=1),
                 _shot(1.4, line_index=2)]
        shots[1]["is_reveal_shot"] = True
        shots[1]["reveal_type"] = "twist"
        out = _merge_short_shots(shots)
        self.assertTrue(out[0]["is_reveal_shot"])
        self.assertEqual(out[0]["reveal_type"], "twist")


if __name__ == "__main__":
    unittest.main()
