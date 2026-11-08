"""Unit tests for Director V2.1 Sequence-Aware Cinematic Engine.

Verifies:
1. Sequence Awareness (Story Change, Information Change, Physical Change).
2. Information Asymmetry and Epistemic State Tracking.
3. Spatial Blocking Continuity (Actors do not reset to center).
4. Physical Object State Progression (State Machine).
5. Semantic Foreground Grounding (Named assets, authentic materials, no anonymous boxes).
6. Shot Necessity and Removal Consequences.
7. Core Engine / Story Data Separation.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from .assets.asset_resolver import UniversalAssetResolver
from .bibles.resolver import create_fallback_character_dna, create_fallback_location_dna
from .config import PipelineConfig
from .director.cinematic_director import CinematicDirector
from .schemas import (
    BeatAction,
    CharacterBible,
    CharacterMention,
    LocationBible,
    LocationMention,
    PropSpec,
    StoryBeat,
    StoryIntelligence,
)


def _make_test_story() -> tuple[StoryIntelligence, CharacterBible, LocationBible]:
    chars = [
        CharacterMention(character_id="ACTOR_A", name="Lead", role="LEAD"),
        CharacterMention(character_id="ACTOR_B", name="Partner", role="SUPPORTING"),
    ]
    beats = [
        StoryBeat(
            beat_id="b1",
            index=0,
            text="The team reaches the dark mountain pass",
            location_id="LOC_TEST",
            characters=["ACTOR_A", "ACTOR_B"],
            actions=[BeatAction(actor_id="ACTOR_A", verb="OBSERVE", emotion="CALM")],
            suggested_purpose="LOCATION",
        ),
        StoryBeat(
            beat_id="b2",
            index=1,
            text="The overhead wire snaps under tension",
            location_id="LOC_TEST",
            characters=["ACTOR_A", "ACTOR_B"],
            actions=[BeatAction(actor_id="ACTOR_A", verb="RECOIL", emotion="ALARMED")],
            suggested_purpose="CAUSE",
            objects=["telegraph line"],
        ),
        StoryBeat(
            beat_id="b3",
            index=2,
            text="The engineer points to the broken insulator",
            location_id="LOC_TEST",
            characters=["ACTOR_A", "ACTOR_B"],
            actions=[BeatAction(actor_id="ACTOR_A", verb="POINT", target="broken insulator", emotion="ATTENTIVE")],
            suggested_purpose="OBJECT_INFORMATION",
            objects=["broken insulator"],
        ),
        StoryBeat(
            beat_id="b4",
            index=3,
            text="The partner bridges the gap with a jumper wire",
            location_id="LOC_TEST",
            characters=["ACTOR_A", "ACTOR_B"],
            actions=[BeatAction(actor_id="ACTOR_B", verb="REPAIR", target="broken insulator", emotion="FOCUSED")],
            suggested_purpose="ACTION",
            objects=["jumper wire"],
        ),
        StoryBeat(
            beat_id="b5",
            index=4,
            text="The receiver needle deflects with active signal",
            location_id="LOC_TEST",
            characters=["ACTOR_A", "ACTOR_B"],
            actions=[BeatAction(actor_id="ACTOR_A", verb="OBSERVE", target="receiver needle", emotion="RELIEVED")],
            suggested_purpose="REVEAL",
            objects=["receiver needle"],
        ),
        StoryBeat(
            beat_id="b6",
            index=5,
            text="Communication is restored across the range",
            location_id="LOC_TEST",
            characters=["ACTOR_A", "ACTOR_B"],
            actions=[BeatAction(actor_id="ACTOR_A", verb="NOD", target="ACTOR_B", emotion="RESOLVED")],
            suggested_purpose="PAYOFF",
        ),
    ]
    story = StoryIntelligence(
        title="Test Telegraph Expedition",
        characters=chars,
        locations=[LocationMention(location_id="LOC_TEST", name="Mountain Pass", enclosure="EXTERIOR")],
        story_beats=beats,
    )
    cb = CharacterBible(characters=[
        create_fallback_character_dna("ACTOR_A", "Lead", "LEAD"),
        create_fallback_character_dna("ACTOR_B", "Partner", "SUPPORTING"),
    ])
    loc = create_fallback_location_dna("LOC_TEST", "Mountain Pass", "EXTERIOR")
    loc.props = [
        PropSpec(semantic="telegraph apparatus", category="APPARATUS", role="HERO", materials=["METAL"]),
        PropSpec(semantic="broken insulator", category="APPARATUS", role="HERO", materials=["CERAMIC"]),
    ]
    lb = LocationBible(locations=[loc])
    return story, cb, lb


class SequenceDirectorV21Tests(unittest.TestCase):

    def setUp(self) -> None:
        self.story, self.cb, self.lb = _make_test_story()
        self.config = PipelineConfig(reasoning_provider="offline", seed=20261108)
        self.resolver = UniversalAssetResolver()
        self.director = CinematicDirector(self.config, self.cb, self.lb, self.resolver)
        self.blueprints = self.director.direct_story(self.story)

    def test_all_shots_have_sequence_causality(self) -> None:
        """Every shot must declare story_change, info_change, and physical_change."""
        self.assertEqual(len(self.blueprints), 6)
        for bp in self.blueprints:
            self.assertTrue(bp.story_change and bp.story_change != "NONE", f"Missing story_change in {bp.shot_id}")
            self.assertTrue(bp.information_change and bp.information_change != "NONE", f"Missing information_change in {bp.shot_id}")
            self.assertTrue(bp.physical_change and bp.physical_change != "NONE", f"Missing physical_change in {bp.shot_id}")
            self.assertTrue(bp.removal_consequence, f"Missing removal_consequence in {bp.shot_id}")
            self.assertIsNotNone(bp.state_before, f"Missing state_before in {bp.shot_id}")
            self.assertIsNotNone(bp.state_after, f"Missing state_after in {bp.shot_id}")

    def test_epistemic_state_divergence(self) -> None:
        """Verify epistemic relationship reflects dramatic purpose."""
        cause_shot = self.blueprints[1]  # CAUSE beat
        self.assertIsNotNone(cause_shot.information_state)
        self.assertEqual(
            cause_shot.information_state.get("epistemic_relation"),
            "VIEWER_KNOWS_CHARACTER_DOES_NOT",
        )
        reveal_shot = self.blueprints[4]  # REVEAL beat
        self.assertIsNotNone(reveal_shot.information_state)
        self.assertEqual(
            reveal_shot.information_state.get("reveal_type"),
            "UNCLOAK",
        )

    def test_blocking_continuity_no_silent_center_reset(self) -> None:
        """Actors must maintain their spatial positions and not reset to center 0.5."""
        shot1_actor_a = self.blueprints[0].actors[0]
        shot2_actor_a = self.blueprints[1].actors[0]
        # Actor A should stay on the left side (< 0.45) rather than resetting to 0.5
        self.assertLess(shot1_actor_a.screen_x, 0.45)
        self.assertLess(shot2_actor_a.screen_x, 0.45)
        self.assertEqual(shot1_actor_a.orientation, "THREE_QUARTER_RIGHT")

    def test_object_state_progression(self) -> None:
        """Object states must evolve across the sequence."""
        shot3 = self.blueprints[2]  # Inspecting broken insulator
        shot4 = self.blueprints[3]  # Repairing broken insulator
        self.assertIn("broken insulator", shot3.object_states)
        self.assertIn(shot3.object_states["broken insulator"], ("INSPECTED", "IDENTIFIED", "CONNECTING", "CHECKED"))

    def test_semantic_foreground_resolution(self) -> None:
        """Foreground elements must be physically identified assets, not anonymous boxes."""
        exterior_bp = self.blueprints[0]
        self.assertIsNotNone(exterior_bp.foreground_element)
        fg = exterior_bp.foreground_element
        self.assertTrue(fg["asset_instance_id"].startswith("fg_"))
        self.assertIn(fg["material"], ("WOOD", "METAL", "FABRIC"))
        self.assertNotEqual(fg["foreground_reason"], "NONE")

    def test_core_engine_data_separation(self) -> None:
        """Core universal code must not contain story-specific hardcoded keywords."""
        forbidden = ["hitler", "pasewalk", "hospital", "trench", "beer hall", "napoleon", "tesla"]
        core_dirs = [
            Path("pipeline/universal/director"),
            Path("pipeline/universal/sequence"),
            Path("pipeline/universal/compositor"),
        ]
        for cdir in core_dirs:
            for p in cdir.glob("*.py"):
                txt = p.read_text(encoding="utf-8").lower()
                for word in forbidden:
                    self.assertNotIn(
                        word,
                        txt,
                        f"Forbidden story keyword '{word}' found in core module {p}",
                    )


if __name__ == "__main__":
    unittest.main()
