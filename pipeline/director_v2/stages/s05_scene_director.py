"""Stage 5: Scene Director.

Organizes retention segments and script beats into cohesive continuous Scenes.
A Scene defines:
  - Location ID & Year
  - Character cast present
  - Continuous screen direction (180-degree rule)
  - Start time & duration
"""
from __future__ import annotations

from typing import Any

from ..schemas.bible import Location, ProjectBible
from ..schemas.plan import RetentionRole, RetentionSegment, Scene, ScenePlan
from ..schemas.script import Beat, ScriptAnalysis


def direct_scenes(
    analysis: ScriptAnalysis,
    retention_segments: list[RetentionSegment],
    bible: ProjectBible,
    locations: list[Location],
) -> ScenePlan:
    """Combines beats and retention segments into continuous Scenes."""
    scenes: list[Scene] = []
    beat_map: dict[str, Beat] = {b.beat_id: b for b in analysis.beats}
    loc_name_to_id: dict[str, str] = {loc.name: loc.id for loc in locations}
    default_loc_id = locations[0].id if locations else "LOC_001_MAIN"

    elapsed = 0.0
    for idx, seg in enumerate(retention_segments):
        # Determine dominant location and characters for this segment
        seg_beats = [beat_map[bid] for bid in seg.beat_ids if bid in beat_map]
        loc_id = default_loc_id
        year = None
        characters_present: set[str] = set()
        narrations: list[str] = []

        for b in seg_beats:
            if b.location_name and b.location_name in loc_name_to_id:
                loc_id = loc_name_to_id[b.location_name]
            if b.year:
                year = b.year
            characters_present.update(b.characters)
            narrations.append(b.text)

        dur = seg.target_duration_sec
        direction = "LEFT_TO_RIGHT" if idx % 2 == 0 else "RIGHT_TO_LEFT"

        scenes.append(Scene(
            scene_id=f"SCENE_{idx + 1:03d}",
            index=idx,
            location_id=loc_id,
            year=year,
            beat_ids=seg.beat_ids,
            retention_roles=[seg.role],
            narration=" ".join(narrations),
            summary=f"{seg.role.value} scene at {loc_id}",
            emotional_tone="tense" if seg.role in (RetentionRole.CONFLICT, RetentionRole.CLIFFHANGER) else "neutral",
            character_ids=list(characters_present) or bible.character_ids[:2],
            start_sec=round(elapsed, 2),
            duration_sec=round(dur, 2),
            screen_direction=direction,
        ))
        elapsed += dur

    return ScenePlan(
        retention=retention_segments,
        scenes=scenes,
        total_duration_sec=round(elapsed, 2),
    )
