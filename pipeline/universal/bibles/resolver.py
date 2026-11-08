"""Bible resolvers, age/costume resolution, and persistent voice registry.

Given a CharacterDNA and a specific (year, location_id, context), resolves the exact
visual variant, costume, hair, and face to be rendered on stage.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from ..schemas import (
    BodyDNA,
    CharacterBible,
    CharacterDNA,
    CharacterVariant,
    CostumeDNA,
    CostumeVariant,
    FaceDNA,
    HairStyleDNA,
    LocationBible,
    LocationDNA,
    PerformanceDNA,
    PropSpec,
    ResolvedCharacter,
)


def create_fallback_character_dna(
    character_id: str,
    name: str = "Unknown Character",
    role: str = "SUPPORTING",
) -> CharacterDNA:
    """Generates a generic, safe CharacterDNA when an unknown character appears in a script."""
    # Deterministically vary hair / face by character_id hash
    h = int(hashlib.md5(character_id.encode("utf-8")).hexdigest(), 16)
    hair_shapes = ["CROPPED", "SWEPT_SIDE", "MESSY", "WAVY", "FLAT_COMB"]
    chosen_hair = hair_shapes[h % len(hair_shapes)]

    return CharacterDNA(
        character_id=character_id,
        name=name,
        role=role,
        detail_level="HERO" if role == "PROTAGONIST" else "SUPPORT",
        on_screen=True,
        visual_identity=f"Generic fallback identity for {name}",
        hair=HairStyleDNA(
            shape=chosen_hair,
            hairline="MEDIUM",
            part="NONE",
            length="SHORT",
            volume=0.5,
            roughness=0.3,
            color="#2a2420",
        ),
        face=FaceDNA(
            head_width=1.0,
            head_height=1.0,
            jaw_shape="ROUND",
            eye_shape="DOT",
            brow_shape="FLAT",
            nose_style="BUTTON",
            mouth_style="LINE",
            ear_style="NORMAL",
            facial_hair="NONE",
            skin_tone="#ead6be",
        ),
        body=BodyDNA(
            height=1.0,
            build="AVERAGE",
            shoulder_width=1.0,
            posture="UPRIGHT",
        ),
        costumes=[
            CostumeVariant(
                costume_id=f"COSTUME_{character_id}_DEFAULT",
                label="Generic Period Costume",
                costume=CostumeDNA(
                    headwear="NONE",
                    upper_garment="SHIRT",
                    outerwear="NONE",
                    lower_garment="TROUSERS",
                    footwear="SHOES",
                    palette={"primary": "#484e58", "secondary": "#282c32", "accent": "#a68852", "trim": "#181a1c"},
                ),
            )
        ],
        variants=[],
        performance=PerformanceDNA(),
        voice_id=f"voice_generic_{(h % 5) + 1:02d}",
        historical_confidence="UNCERTAIN",
        proposal_source="FALLBACK_PROPOSAL",
    )


def create_fallback_location_dna(
    location_id: str,
    name: str = "Unknown Location",
    enclosure: str = "EXTERIOR",
) -> LocationDNA:
    """Generates a generic, safe LocationDNA when an unknown location appears in a script."""
    is_interior = enclosure.upper() == "INTERIOR"
    return LocationDNA(
        location_id=location_id,
        name=name,
        enclosure=enclosure,
        ceiling="FLAT" if is_interior else "SKY",
        wall_treatment="PLAIN",
        floor_feature="PLANKS" if is_interior else "BARE",
        openings="WINDOWS_SMALL" if is_interior else "NONE",
        horizon_feature="NONE" if is_interior else "HILLS",
        materials=["WOOD", "PLASTER"] if is_interior else ["STONE", "EARTH"],
        palette={
            "sky_top": "#5b6d82" if is_interior else "#8aa2ba",
            "sky_bottom": "#3a4450" if is_interior else "#cbd6e0",
            "wall": "#92897e" if is_interior else "#8c8276",
            "floor": "#4c4234" if is_interior else "#5a5046",
            "accent": "#b88a44",
            "shadow": "#18181a",
        },
        lighting_behavior="WARM_POOLS" if is_interior else "OVERCAST",
        weather="CLEAR",
        atmosphere=["HAZE"] if is_interior else [],
        wear=0.3,
        density="BALANCED",
        props=[
            PropSpec(semantic="Generic wooden table", category="TABLE", role="DRESSING", materials=["WOOD"], count=1, affordances=["LEAN", "PLACE"]),
            PropSpec(semantic="Generic sitting bench", category="BENCH", role="DRESSING", materials=["WOOD"], count=1, affordances=["SIT"]),
        ],
        foreground_vocabulary=[
            PropSpec(semantic="Foreground framing post", category="POST", role="FOREGROUND", materials=["WOOD"]),
        ],
        background_activity=["DISTANT_FIGURES"],
        historical_confidence="UNCERTAIN",
        proposal_source="FALLBACK_PROPOSAL",
    )


class VoiceRegistry:
    """Persistent mapping of CHARACTER_ID -> VOICE_ID."""

    def __init__(self) -> None:
        self._registry: dict[str, str] = {}
        # Generic pool of voice identifiers
        self._voice_pool = [
            "voice_narrator_baritone",
            "voice_hero_tenor",
            "voice_officer_crisp",
            "voice_soldier_rough",
            "voice_companion_warm",
            "voice_scholar_quiet",
            "voice_worker_deep",
        ]
        self._counter = 0

    def register_character(self, character: CharacterDNA) -> str:
        cid = character.character_id
        if cid in self._registry:
            return self._registry[cid]

        if character.voice_id:
            vid = character.voice_id
        elif character.is_narrator:
            vid = "voice_narrator_baritone"
        else:
            vid = self._voice_pool[self._counter % len(self._voice_pool)]
            self._counter += 1

        self._registry[cid] = vid
        return vid

    def get_voice(self, character_id: str) -> str:
        return self._registry.get(character_id, "voice_generic_default")

    def to_dict(self) -> dict[str, str]:
        return dict(self._registry)


class CharacterResolver:
    """Resolves character visual state (age, hair, costume, condition) for a specific shot."""

    @classmethod
    def resolve_for_shot(
        cls,
        character: CharacterDNA,
        year: Optional[int] = None,
        location_id: Optional[str] = None,
        context: Optional[str] = None,
    ) -> ResolvedCharacter:
        # 1. Resolve Age Variant
        chosen_variant: Optional[CharacterVariant] = None
        if year is not None and character.variants:
            for v in character.variants:
                yf = v.year_from if v.year_from is not None else -999999
                yt = v.year_to if v.year_to is not None else 999999
                if yf <= year <= yt:
                    chosen_variant = v
                    break

        # Compute age
        calc_age: Optional[int] = None
        if year is not None and character.birth_year is not None:
            calc_age = max(0, year - character.birth_year)
        elif chosen_variant and chosen_variant.age is not None:
            calc_age = chosen_variant.age

        # Resolve Hair / Face / Body / Conditions
        hair = chosen_variant.hair if (chosen_variant and chosen_variant.hair) else character.hair
        face = chosen_variant.face if (chosen_variant and chosen_variant.face) else character.face
        body = chosen_variant.body if (chosen_variant and chosen_variant.body) else character.body
        conditions = list(chosen_variant.conditions) if chosen_variant else []

        # 2. Resolve Costume Variant
        chosen_costume_variant: Optional[CostumeVariant] = None
        if chosen_variant and chosen_variant.default_costume_id:
            chosen_costume_variant = next((c for c in character.costumes if c.costume_id == chosen_variant.default_costume_id), None)

        if not chosen_costume_variant and character.costumes:
            # Score costumes by matching year, location, context
            best_score = -1
            best_c = character.costumes[0]
            for c in character.costumes:
                score = 0
                if year is not None:
                    yf = c.year_from if c.year_from is not None else -999999
                    yt = c.year_to if c.year_to is not None else 999999
                    if yf <= year <= yt:
                        score += 3
                if location_id and c.location_ids and location_id in c.location_ids:
                    score += 5
                if context and c.contexts and context.upper() in [cx.upper() for cx in c.contexts]:
                    score += 4
                if score > best_score:
                    best_score = score
                    best_c = c
            chosen_costume_variant = best_c

        costume_dna = chosen_costume_variant.costume if chosen_costume_variant else (
            character.costumes[0].costume if character.costumes else CostumeDNA()
        )
        costume_id = chosen_costume_variant.costume_id if chosen_costume_variant else "COSTUME_DEFAULT"
        variant_id = chosen_variant.variant_id if chosen_variant else "VARIANT_DEFAULT"

        return ResolvedCharacter(
            character_id=character.character_id,
            variant_id=variant_id,
            costume_id=costume_id,
            age=calc_age,
            hair=hair,
            face=face,
            body=body,
            costume=costume_dna,
            conditions=conditions,
            performance=character.performance,
        )
