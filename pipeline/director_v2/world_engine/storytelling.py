"""Environmental Storytelling Engine.

Injects narrative history, recent action, and occupation into the visual world:
- Object states: OPEN, MOVED, USED, DAMAGED, WET, DIRTY, SCATTERED, TILTED, PARTIAL.
- Storytelling props that answer:
  * What just happened? (e.g. recent bombardment -> fresh crater, smoke, spent casings)
  * What is happening? (e.g. medical recovery -> medicine bottles, unrolled bandages, fever chart)
  * What is about to happen? (e.g. mobilization rally -> scattered broadsheets, banners)
- Density Guard: Baseline locked at BALANCED. Never clutters the frame with purposeless junk.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
import cairo

from ..scene_builder.blueprint import SceneBlueprint


class StoryState(str, Enum):
    OPEN = "OPEN"
    MOVED = "MOVED"
    USED = "USED"
    DAMAGED = "DAMAGED"
    WET = "WET"
    DIRTY = "DIRTY"
    SCATTERED = "SCATTERED"
    TILTED = "TILTED"
    PARTIAL = "PARTIAL"


@dataclass
class NarrativePropModifier:
    prop_id: str
    states: list[StoryState]
    tilt_angle_rad: float = 0.0
    wear_factor: float = 0.5
    narrative_reason: str = ""


class EnvironmentalStorytelling:
    """Derives narrative prop states and placement from SceneBlueprint."""

    @staticmethod
    def resolve_prop_modifiers(bp: SceneBlueprint) -> list[NarrativePropModifier]:
        """Resolves 2-4 purposeful storytelling prop modifications based on story purpose."""
        purpose = bp.story.purpose.lower()
        event = bp.history.event_context.lower()
        mods: list[NarrativePropModifier] = []

        if "somme" in event or "trench" in event or "bombard" in purpose:
            mods.append(NarrativePropModifier(
                prop_id="trench_timber_revetment",
                states=[StoryState.DAMAGED, StoryState.WET],
                wear_factor=0.85,
                narrative_reason="Artillery concussion splintering timbers and autumn rain soaking wood.",
            ))
            mods.append(NarrativePropModifier(
                prop_id="spent_brass_cartridge_casings",
                states=[StoryState.SCATTERED, StoryState.USED],
                wear_factor=0.70,
                narrative_reason="Recent machine-gun and rifle defensive fire.",
            ))
            mods.append(NarrativePropModifier(
                prop_id="ammo_crate_stack",
                states=[StoryState.OPEN, StoryState.TILTED],
                tilt_angle_rad=0.06,
                wear_factor=0.60,
                narrative_reason="Crates hastily opened during bombardment.",
            ))
        elif "hospital" in event or "pasewalk" in event or "convalesc" in purpose:
            mods.append(NarrativePropModifier(
                prop_id="cast_iron_hospital_bed",
                states=[StoryState.USED, StoryState.OPEN],
                wear_factor=0.40,
                narrative_reason="Patient convalescing, blanket folded back.",
            ))
            mods.append(NarrativePropModifier(
                prop_id="apothecary_carbolic_bottles",
                states=[StoryState.OPEN, StoryState.USED],
                wear_factor=0.30,
                narrative_reason="Antiseptic treatment in active progress.",
            ))
            mods.append(NarrativePropModifier(
                prop_id="medical_chart_clipboard",
                states=[StoryState.USED],
                wear_factor=0.25,
                narrative_reason="Fever chart marked with recent clinical measurements.",
            ))
        elif "beer" in event or "tavern" in event or "agitat" in purpose:
            mods.append(NarrativePropModifier(
                prop_id="earthenware_keferloher_steins",
                states=[StoryState.USED, StoryState.WET],
                wear_factor=0.50,
                narrative_reason="Half-emptied beer with foam rings on table.",
            ))
            mods.append(NarrativePropModifier(
                prop_id="heavy_oak_tavern_table",
                states=[StoryState.USED, StoryState.WET],
                wear_factor=0.55,
                narrative_reason="Stained tabletop from heated political discussions.",
            ))
            mods.append(NarrativePropModifier(
                prop_id="hanging_brass_chandelier",
                states=[StoryState.USED],
                wear_factor=0.40,
                narrative_reason="Smoking wick and warm candlelight glow.",
            ))
        else:
            # European Street / Odeonsplatz mobilization
            mods.append(NarrativePropModifier(
                prop_id="scattered_news_broadsheets",
                states=[StoryState.SCATTERED, StoryState.USED, StoryState.TILTED],
                tilt_angle_rad=0.15,
                wear_factor=0.35,
                narrative_reason="War mobilization extra editions dropped by eager crowds.",
            ))
            mods.append(NarrativePropModifier(
                prop_id="rally_civic_banners",
                states=[StoryState.USED, StoryState.MOVED],
                tilt_angle_rad=0.08,
                wear_factor=0.30,
                narrative_reason="Flags fluttering in morning breeze.",
            ))

        return mods
