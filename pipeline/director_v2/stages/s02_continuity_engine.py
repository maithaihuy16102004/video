"""Stage 2: Historical & Continuity Engine.

Analyzes timeline progression across beats, character continuity states
(costume/injury/era), and historical location evolutions.
"""
from __future__ import annotations

import re
from typing import Any

from ..schemas.bible import CharacterState, TimelineEvent
from ..schemas.script import Beat, ScriptAnalysis


def build_continuity_timeline(analysis: ScriptAnalysis) -> tuple[list[TimelineEvent], list[str]]:
    """Builds ordered historical timeline events and continuity constraints."""
    events: list[TimelineEvent] = []
    constraints: list[str] = []

    last_year = None
    for b in analysis.beats:
        if b.year:
            if last_year and b.year < last_year:
                # Flashback or out of order
                events.append(TimelineEvent(
                    beat_index=b.index,
                    year=b.year,
                    event=f"Flashback to {b.year} in {b.location_name or 'unspecified location'}",
                    flashback=True,
                ))
                constraints.append(f"Beat {b.beat_id}: Flashback to {b.year} - costume and setting must reflect earlier era.")
            else:
                events.append(TimelineEvent(
                    beat_index=b.index,
                    year=b.year,
                    event=f"Event in {b.year}: {b.story_beat} at {b.location_name or 'location'}",
                    flashback=False,
                ))
            last_year = b.year

    return events, constraints


def infer_character_states(char_name: str, beats: list[Beat]) -> list[CharacterState]:
    """Infers character state progression (costume/injury/era) across script beats."""
    states: list[CharacterState] = []
    current_state_label = "INITIAL"
    current_costume = "COSTUME_CIVILIAN"
    current_injury = "NONE"
    start_beat = 0

    c_low = char_name.lower()
    for idx, b in enumerate(beats):
        t_low = b.text.lower()
        yr = b.year

        # Check for state changes based on narrative context
        new_costume = current_costume
        new_injury = current_injury
        new_label = current_state_label

        if any(k in t_low for k in ("gia nhập quân", "quân đội", "lính", "chiến hào", "enlist", "soldier", "uniform")):
            new_costume = "COSTUME_MILITARY"
            new_label = "SOLDIER"
        elif any(k in t_low for k in ("bệnh viện", "bị thương", "khí độc", "mù", "hospital", "wounded", "blind")):
            new_costume = "COSTUME_HOSPITAL"
            new_injury = "TEMPORARY_BLINDNESS" if "khí độc" in t_low or "mù" in t_low else "WOUNDED"
            new_label = "HOSPITAL_PATIENT"
        elif any(k in t_low for k in ("xuất viện", "hậu chiến", "chính khách", "đảng", "chính trị", "politics", "party", "statesman", "civilian")):
            new_costume = "COSTUME_POLITICAL"
            new_injury = "NONE"
            new_label = "POLITICAL_ACTIVIST"

        if (new_label != current_state_label) and idx > start_beat:
            states.append(CharacterState(
                state_id=f"STATE_{len(states) + 1:02d}",
                label=current_state_label,
                beat_from=start_beat,
                beat_to=idx - 1,
                costume_id=current_costume,
                injury=current_injury,
            ))
            current_state_label = new_label
            current_costume = new_costume
            current_injury = new_injury
            start_beat = idx

    # Final state
    states.append(CharacterState(
        state_id=f"STATE_{len(states) + 1:02d}",
        label=current_state_label,
        beat_from=start_beat,
        beat_to=len(beats) - 1,
        costume_id=current_costume,
        injury=current_injury,
    ))
    return states
