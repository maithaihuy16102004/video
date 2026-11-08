"""Sequence Director and Sequence Planning Engine.

Architecture:
- Sits above shot selection: StoryBeat -> SequencePlan -> ShotOpportunities -> Approved Shots.
- Defines dramatic progression: Start State -> Development -> Turn/Reveal -> End State.
- Disallows sentence-to-shot 1:1 translation.
- Mandates explicit semantic story purposes for all shots.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pipeline.universal.story_first_reset.story_world import StoryBeat, StoryWorldModel


@dataclass
class PlannedShot:
    shot_id: str
    shot_number: int
    duration_sec: float
    start_time_sec: float
    end_time_sec: float
    semantic_purpose: str  # ESTABLISH_GEOGRAPHY, REVEAL_CHARACTER, SHOW_ACTION, SHOW_OBJECT_INFORMATION, REACTION, POWER_RELATIONSHIP, ISOLATION, DANGER, CAUSE, CONSEQUENCE, TRANSITION
    story_reason: str  # Why this shot MUST exist in the story
    camera_viewpoint: str  # e.g., WIDE_ESTABLISHING, MEDIUM_TWO_SHOT, CLOSE_UP_HERO, OVER_SHOULDER_LEDGER
    framing_composition: str
    active_characters: list[dict[str, Any]]
    environmental_state: dict[str, Any]
    information_gained: str
    physical_action: str
    what_changes_from_previous: str


@dataclass
class SequencePlan:
    sequence_id: str
    title: str
    total_duration_sec: float
    target_section: str
    sequence_purpose: str
    start_state: str
    development: str
    turn_reveal: str
    end_state: str
    key_physical_event: str
    character_objective: str
    obstacle: str
    important_object: str
    information_progression: list[str]
    spatial_progression: list[str]
    planned_shots: list[PlannedShot]

    @classmethod
    def create_for_hook_section(cls, world: StoryWorldModel, beats: list[StoryBeat]) -> SequencePlan:
        """Constructs an integrated SequencePlan for the 35-second Munich 1914 Hook."""

        # 5 precisely choreographed cinematic shots spanning the 34.5s sequence
        shots = [
            # SHOT 1: ISOLATION IN THE METROPOLIS (0.0s - 7.5s)
            PlannedShot(
                shot_id="EP01_SH01",
                shot_number=1,
                duration_sec=7.5,
                start_time_sec=0.0,
                end_time_sec=7.5,
                semantic_purpose="ISOLATION",
                story_reason="Establish the protagonist's profound insignificance, poverty, and isolation against the grand scale of neoclassical Munich before the war cataclysm.",
                camera_viewpoint="WIDE_ESTABLISHING",
                framing_composition="Neoclassical facade flanking left; Feldherrnhalle triple arches visible in deep background; protagonist small in lower-left third; indifferent citizens walking past in right two-thirds.",
                active_characters=[
                    {
                        "character_id": "PROTAGONIST_HITLER",
                        "costume": "1914_CIVILIAN",
                        "position_norm": (0.32, 0.68),
                        "scale": 0.95,
                        "facing": "RIGHT",
                        "action": "Standing hunched, clutching unsold watercolor postcards to chest, watching oblivious crowd",
                        "eyeline": "DOWNWARD_SLIGHTLY_FORWARD",
                    }
                ],
                environmental_state={
                    "location_id": "LOC_001_ODEONSPLATZ",
                    "lighting": "WARM_LATE_SUMMER_AFTERNOON_HAZE",
                    "weather": "CALM_PEACEFUL_CIVILIAN",
                    "color_tone": "NEUTRAL_EARTHY_OCHRE",
                },
                information_gained="Hitler in August 1914 was an obscure, threadbare postcard painter without career, money, or social status.",
                physical_action="Protagonist clutches art portfolio; passersby cross the frame ignoring him.",
                what_changes_from_previous="START OF SEQUENCE: Establishes initial baseline of civilian insignificance.",
            ),

            # SHOT 2: GEOPOLITICAL COLLISION & MOBILIZATION (7.5s - 14.5s)
            PlannedShot(
                shot_id="EP01_SH02",
                shot_number=2,
                duration_sec=7.0,
                start_time_sec=7.5,
                end_time_sec=14.5,
                semantic_purpose="CAUSE",
                story_reason="Show the sudden eruption of mass mobilization that shatters the protagonist's static civilian drift and pulls him into collective madness.",
                camera_viewpoint="MEDIUM_WIDE_ACTION",
                framing_composition="Close-to-mid shot centered on the massive limestone wall; a civilian official slaps the Imperial Allgemeine Mobilmachung proclamation onto the stone as enthusiastic young men surge forward waving newspapers.",
                active_characters=[
                    {
                        "character_id": "PROTAGONIST_HITLER",
                        "costume": "1914_CIVILIAN",
                        "position_norm": (0.24, 0.64),
                        "scale": 1.15,
                        "facing": "RIGHT",
                        "action": "Turned around in shock, staring up at the newly posted proclamation banner",
                        "eyeline": "HIGH_RIGHT_UPWARD",
                    },
                    {
                        "character_id": "BAVARIAN_RECRUIT_SOLDIER",
                        "costume": "1914_CIVILIAN",
                        "position_norm": (0.68, 0.62),
                        "scale": 1.20,
                        "facing": "LEFT",
                        "action": "Cheering enthusiastically, brandishing war extra newspaper in fist",
                        "eyeline": "HIGH_CENTER",
                    }
                ],
                environmental_state={
                    "location_id": "LOC_001_ODEONSPLATZ",
                    "lighting": "HIGH_CONTRAST_SUN_RAKING_STONE",
                    "weather": "TURBULENT_WIND_BLOWING_POSTERS",
                    "color_tone": "GOLDEN_CREAM_WITH_BLACK_INK_ACCENTS",
                },
                information_gained="World War I erupts; European youth greet the declaration of war with ecstatic patriotic euphoria.",
                physical_action="Crowd surges; black ink mobilization decree posted; newspapers waved in air.",
                what_changes_from_previous="SPATIAL & EMOTIONAL REVERSAL: Quiet personal loneliness is violently overtaken by dynamic collective crowd surge.",
            ),

            # SHOT 3: THE ENLISTMENT LEDGER (14.5s - 23.0s)
            PlannedShot(
                shot_id="EP01_SH03",
                shot_number=3,
                duration_sec=8.5,
                start_time_sec=14.5,
                end_time_sec=23.0,
                semantic_purpose="SHOW_ACTION",
                story_reason="Depict the irrevocable personal decision: an Austrian citizen voluntarily pledging his life to the Kingdom of Bavaria.",
                camera_viewpoint="MEDIUM_TWO_SHOT_INTERACTION",
                framing_composition="Under the heavy shaded vaulted arch of the recruitment station; enlistment clerk seated at oak table with registry ledger; Hitler standing with pen poised, addressing the recruit beside him.",
                active_characters=[
                    {
                        "character_id": "PROTAGONIST_HITLER",
                        "costume": "1914_CIVILIAN",
                        "position_norm": (0.42, 0.58),
                        "scale": 1.35,
                        "facing": "RIGHT",
                        "action": "Holding steel dip pen over open military ledger, turning head to speak to recruit beside him",
                        "eyeline": "DIRECT_AT_FELLOW_RECRUIT",
                    },
                    {
                        "character_id": "BAVARIAN_RECRUIT_SOLDIER",
                        "costume": "1914_RECRUIT",
                        "position_norm": (0.75, 0.60),
                        "scale": 1.30,
                        "facing": "LEFT",
                        "action": "Already wearing recruit cockade cap, leaning in to respond with casual confidence",
                        "eyeline": "DIRECT_AT_HITLER",
                    },
                    {
                        "character_id": "ENLISTMENT_OFFICER",
                        "costume": "1914_OFFICER",
                        "position_norm": (0.16, 0.62),
                        "scale": 1.25,
                        "facing": "RIGHT",
                        "action": "Seated at desk stamping papers and pointing to signature line",
                        "eyeline": "DOWN_AT_LEDGER",
                    }
                ],
                environmental_state={
                    "location_id": "LOC_001_ODEONSPLATZ",
                    "lighting": "DEEP_ARCH_SHADOWS_WITH_RAKING_TABLE_HIGHLIGHT",
                    "weather": "ENCLOSED_COURTYARD_CALM",
                    "color_tone": "RICH_AMBER_WOOD_AND_DEEP_PRUSSIAN_BLUE",
                },
                information_gained="Hitler joins the Bavarian 16th Reserve Infantry Regiment; he asks naive questions about everyone fighting.",
                physical_action="Protagonist puts pen to paper; verbal exchange between recruit and drifter.",
                what_changes_from_previous="INSTITUTIONAL ENCLOSURE: We move from the open public square into the focused administrative space of the recruitment desk.",
            ),

            # SHOT 4: THE CHRISTMAS MYTH DIALOGUE (23.0s - 29.5s)
            PlannedShot(
                shot_id="EP01_SH04",
                shot_number=4,
                duration_sec=6.5,
                start_time_sec=23.0,
                end_time_sec=29.5,
                semantic_purpose="REACTION",
                story_reason="Highlight the universal historical myth ('home before Christmas') shared between naive soldiers about to march into the slaughterhouse.",
                camera_viewpoint="OVER_SHOULDER_CLOSE_INTERACTION",
                framing_composition="Over the shoulder of the Bavarian recruit looking into Hitler's face; Hitler now wearing recruit Feldmütze, eyes wide with earnest, naive expectation.",
                active_characters=[
                    {
                        "character_id": "PROTAGONIST_HITLER",
                        "costume": "1914_RECRUIT",
                        "position_norm": (0.58, 0.52),
                        "scale": 1.65,
                        "facing": "LEFT",
                        "action": "Earnest facial expression, leaning forward inquiring: 'Nghe nói chiến tranh sẽ kết thúc trước Giáng sinh?'",
                        "eyeline": "FOCUSED_ON_SOLDIER_EYES",
                    },
                    {
                        "character_id": "BAVARIAN_RECRUIT_SOLDIER",
                        "costume": "1914_RECRUIT",
                        "position_norm": (0.18, 0.55),
                        "scale": 1.70,
                        "facing": "RIGHT",
                        "action": "Foreground shoulder/profile, shrugging with comfortable nonchalance",
                        "eyeline": "AT_HITLER",
                    }
                ],
                environmental_state={
                    "location_id": "LOC_001_ODEONSPLATZ",
                    "lighting": "WARM_LATE_SUN_GLINTING_ON_BRASS_BUTTONS",
                    "weather": "CLEAR_SUMMER_EVENING",
                    "color_tone": "WARM_FELDGRAU_AND_SKIN_TONES",
                },
                information_gained="Soldiers genuinely believed the war would be a brief, glorious adventure over in four months.",
                physical_action="Hitler's posture straightens into recruit stance; spoken dialogue exchange on the Christmas myth.",
                what_changes_from_previous="INTIMACY & IDENTITY SHIFT: Protagonist is now visibly transformed from shabby civilian into uniformed recruit.",
            ),

            # SHOT 5: THE HISTORICAL HAMMER / SPOILER (29.5s - 34.5s)
            PlannedShot(
                shot_id="EP01_SH05",
                shot_number=5,
                duration_sec=5.0,
                start_time_sec=29.5,
                end_time_sec=34.5,
                semantic_purpose="CONSEQUENCE",
                story_reason="Deliver the definitive deconstructive punchline of the hook: shatter the Christmas myth with the stark, chilling reality of the four-year meat grinder.",
                camera_viewpoint="DIRECT_MEDIUM_HERO_FACING",
                framing_composition="Protagonist centered in uniform looking directly down the camera lens with frozen smile; behind him, the warm Odeonsplatz background drains of sunlight into ominous cold slate grey.",
                active_characters=[
                    {
                        "character_id": "PROTAGONIST_HITLER",
                        "costume": "1914_RECRUIT",
                        "position_norm": (0.50, 0.54),
                        "scale": 1.55,
                        "facing": "FRONT",
                        "action": "Frozen recruit posture, faint naive smile slowly stiffening as the protagonist delivers the retrospective reflection",
                        "eyeline": "DIRECT_AT_LENS_VIEWER",
                    }
                ],
                environmental_state={
                    "location_id": "LOC_001_ODEONSPLATZ",
                    "lighting": "SUDDEN_COLD_SLATE_DESATURATION",
                    "weather": "FOREBODING_SHADOW_FALLING_ACROSS_SQUARE",
                    "color_tone": "MUTED_CHARCOAL_AND_COLD_STEEL",
                },
                information_gained="The reality was 4 years of industrial horror; the hook ends by setting up the grim trench reality of Section 2.",
                physical_action="Protagonist stands rigid as visual tone darkens; protagonist delivers deadpan retrospective realization.",
                what_changes_from_previous="FOURTH-WALL TONAL PUNCTUATION: The warm conversational romance abruptly halts; the cold shadow of four years of death falls over the scene.",
            ),
        ]

        return cls(
            sequence_id="SEQ_01_MUNICH_1914_HOOK",
            title="The 1914 Hook: From Bohemian Drifter to Bavarian Recruit",
            total_duration_sec=34.5,
            target_section="SECTION_01_HOOK_MUNICH_1914",
            sequence_purpose="Dramatize how an aimless, impoverished 25-year-old drifter found identity and meaning by plunging into the catastrophic war euphoria of August 1914.",
            start_state="Protagonist is an isolated, broke civilian postcard painter ignored by the metropolis.",
            development="Mass war mobilization erupts, sweeping civilian apathy aside into collective patriotic mania.",
            turn_reveal="Hitler steps up to the recruitment table, voluntarily surrendering individuality to become an enlisted Bavarian infantryman.",
            end_state="Clothed in recruit Feldgrau with naive dreams of being home by Christmas, immediately subverted by protagonist's retrospective realization.",
            key_physical_event="Signing the regiment roster ledger with dip pen under the Feldherrnhalle loggia.",
            character_objective="Escape purposeless bohemian obscurity and find belonging in a grand historic mission.",
            obstacle="Austrian nationality (bypassed by petition) and the imminent meat grinder of industrial warfare.",
            important_object="The Bavarian 16th RIR Enlistment Ledger and the Mobilization Proclamation.",
            information_progression=[
                "1. Drifter has nothing to lose in 1914.",
                "2. War offers an unexpected escape hatch from personal failure.",
                "3. Munich explodes into euphoric war support.",
                "4. Enlistment gives him uniform and identity.",
                "5. The romantic expectation of quick victory was completely false.",
            ],
            spatial_progression=[
                "1. Wide public Odeonsplatz (Protagonist dwarfed).",
                "2. Dynamic crowd cluster around proclamation pillar.",
                "3. Sheltered administrative recruitment alcove.",
                "4. Intimate soldier-to-soldier over-shoulder exchange.",
                "5. Direct-to-camera psychological confrontational close-up.",
            ],
            planned_shots=shots,
        )
