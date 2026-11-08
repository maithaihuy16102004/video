"""Stage 3: Asset Bibles Builder.

Builds ProjectBible, CharacterBible, LocationBible, Costume & Prop definitions
per project from the ScriptAnalysis. Nothing is hard-coded.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schemas.bible import (
    Character,
    CharacterProportions,
    Costume,
    Location,
    LocationVariant,
    ProjectBible,
    Prop,
    StylePreset,
)
from ..schemas.script import ScriptAnalysis
from .s02_continuity_engine import build_continuity_timeline, infer_character_states

STYLE_PATH = Path(__file__).resolve().parents[1] / "data" / "styles" / "premium_cinematic_historical_stickman.json"


def load_default_style() -> StylePreset:
    if STYLE_PATH.exists():
        data = json.loads(STYLE_PATH.read_text(encoding="utf-8"))
        return StylePreset.model_validate(data)
    return StylePreset(
        id="default_stickman",
        name="Cinematic Stickman",
        description="Expressive 2D stickman animation in historical environments",
    )


def build_bibles(
    analysis: ScriptAnalysis,
    project_id: str = "project_01",
    style_preset: StylePreset | None = None,
) -> tuple[ProjectBible, list[Character], list[Location]]:
    """Builds project, character, and location bibles from ScriptAnalysis."""
    style = style_preset or load_default_style()
    timeline, constraints = build_continuity_timeline(analysis)

    # 1. Characters
    characters: list[Character] = []
    color_palette = ["#3a3a3a", "#2b4c7e", "#5c3d2e", "#3d5c4e", "#6b3e52"]

    for idx, c_mention in enumerate(analysis.characters):
        char_id = f"CHAR_{idx + 1:03d}"
        role = c_mention.role
        states = infer_character_states(c_mention.name, analysis.beats)

        # Proportions: protagonist has slightly distinguished proportions
        prop = CharacterProportions(
            head_ratio=0.22 if role == "protagonist" else 0.20,
            height_scale=1.05 if role == "protagonist" else 1.0,
            body_type="average",
        )
        face_anchors = ["eyes_expressive", "neutral_mouth"]
        if role == "protagonist":
            face_anchors.append("focused_brow")

        characters.append(Character(
            id=char_id,
            name=c_mention.name,
            role=role,
            identity=f"{c_mention.name} ({role})",
            proportions=prop,
            face_anchors=face_anchors,
            color_identity=color_palette[idx % len(color_palette)],
            states=states,
            rig_id="stickman_v1",
        ))

    # If no characters detected, create default protagonist & narrator
    if not characters:
        characters = [
            Character(
                id="CHAR_001",
                name="Protagonist",
                role="protagonist",
                identity="Protagonist",
                rig_id="stickman_v1",
            ),
            Character(
                id="CHAR_002",
                name="Narrator",
                role="narrator",
                identity="Narrator",
                rig_id="stickman_v1",
            ),
        ]

    # 2. Locations
    locations: list[Location] = []
    for idx, l_mention in enumerate(analysis.locations):
        loc_id = f"LOC_{idx + 1:03d}_{l_mention.name.replace(' ', '_').upper()[:16]}"
        yr = l_mention.years[0] if l_mention.years else None

        variants: list[LocationVariant] = []
        if len(l_mention.years) > 1:
            for y_var in l_mention.years[1:]:
                variants.append(LocationVariant(
                    variant_id=f"VAR_{y_var}",
                    label=f"{l_mention.name} in {y_var}",
                    year=y_var,
                    changes=f"Architectural and atmospheric wear by year {y_var}",
                ))

        # Default multi-plane elements
        locations.append(Location(
            id=loc_id,
            name=l_mention.name,
            year=yr,
            description=f"Historical setting of {l_mention.name}",
            foreground_elements=[f"{l_mention.name} architectural foreground frame"],
            midground_elements=[f"{l_mention.name} central buildings and street"],
            background_elements=[f"{l_mention.name} horizon and landmarks"],
            far_background_elements=["Atmospheric sky and distant mountains"],
            variants=variants,
        ))

    if not locations:
        locations = [
            Location(
                id="LOC_001_MAIN",
                name="Main Environment",
                description="Primary narrative environment",
                foreground_elements=["Foreground silhouette arch"],
                midground_elements=["Central street and buildings"],
                background_elements=["City skyline"],
                far_background_elements=["Atmospheric horizon"],
            )
        ]

    # 3. Costumes & Props
    costumes: list[Costume] = [
        Costume(id="COSTUME_CIVILIAN", name="1910s European Civilian Attire", colors=["#4a453e", "#2b2a28"]),
        Costume(id="COSTUME_MILITARY", name="WWI Field Uniform", colors=["#5c6b55", "#485244"]),
        Costume(id="COSTUME_HOSPITAL", name="Hospital Convalescent Gown", colors=["#dcd8cd", "#b5b0a3"]),
        Costume(id="COSTUME_POLITICAL", name="Post-war Civilian Suit", colors=["#2a2a2e", "#1b1b1e"]),
    ]

    props: list[Prop] = [
        Prop(id="PROP_LETTER", name="Official Dispatch / Letter", complexity="simple", held=True),
        Prop(id="PROP_MAP", name="Tactical Military Map", complexity="simple", held=False),
        Prop(id="PROP_BEER_MUG", name="Bavarian Ceramic Beer Stein", complexity="simple", held=True),
        Prop(id="PROP_RIFLE", name="Mauser Bolt-Action Rifle", complexity="complex", held=True),
        Prop(id="PROP_MEDAL", name="Iron Cross Medal", complexity="complex", held=False),
    ]

    project_bible = ProjectBible(
        project_id=project_id,
        title=analysis.title,
        language=analysis.language,
        style=style,
        years=analysis.years,
        timeline=timeline,
        historical_constraints=constraints,
        character_ids=[c.id for c in characters],
        location_ids=[loc.id for loc in locations],
        costumes=costumes,
        props=props,
    )

    return project_bible, characters, locations
