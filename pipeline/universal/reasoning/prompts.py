"""Prompt builders for the reasoning stages.  Prompts describe generic schemas + closed vocabularies.

No story content is embedded here; the script / story intelligence is passed in at runtime.
"""
from __future__ import annotations

import json

from .. import vocab as V
from ..config import PipelineConfig

STORY_SYSTEM = (
    "You are the SCRIPT INTELLIGENCE module of a universal script-to-cinematic-stickman-video system. "
    "You analyse ANY script (any country, century, genre, language) and return ONLY strict JSON. "
    "You never paint frames; you produce structured reasoning. Separate verified historical fact from "
    "dramatic reconstruction. Use the closed vocabularies exactly. IDs must be UPPER_SNAKE_CASE ASCII."
)

BIBLE_SYSTEM = (
    "You are the CHARACTER and LOCATION BIBLE designer of a universal illustrated-stickman video system. "
    "Characters are drawn as ILLUSTRATED STICKMEN: large illustrated head, recognisable hair silhouette, "
    "simple expressive face, simple clothing mass, thin stick limbs. Identity must come from DATA: hair, face, "
    "costume, body proportion, palette. Locations are rendered by a generic world engine from LocationDNA. "
    "Return ONLY strict JSON using the closed vocabularies exactly. Colours are #rrggbb hex."
)


def _v(name: str, values: list[str]) -> str:
    return f"{name}: {'|'.join(values)}"


def story_prompt(script: str, config: PipelineConfig) -> str:
    vocab = "\n".join([
        _v("role", V.CharacterRole.values()),
        _v("beat_type", V.BeatType.values()),
        _v("suggested_purpose", V.ShotPurpose.values()),
        _v("verb", V.ActionVerb.values()),
        _v("emotion", V.EMOTIONS),
        _v("enclosure", V.ENCLOSURES),
        _v("confidence", V.HistoricalConfidence.values()),
        _v("research category", V.ResearchCategory.values()),
        _v("object category", V.PROP_CATEGORIES),
        _v("comedy", ["NONE", "SETUP", "PAYOFF"]),
    ])
    schema = {
        "title": "str", "language": "ISO code", "genre": "str",
        "period": {"start_year": "int|null", "end_year": "int|null"},
        "timeline": [{"event_id": "E01", "year": "int|null", "month": "int|null", "description": "str",
                      "location_id": "LOC_ID|null", "confidence": "confidence"}],
        "characters": [{"character_id": "ID", "name": "display name", "role": "role", "aliases": ["speaker labels used in script"],
                        "is_narrator": "bool", "on_screen": "bool (false for pure off-screen narrator)", "speaking": "bool",
                        "historical_person": "bool", "birth_year": "int|null", "description": "visual+role summary"}],
        "locations": [{"location_id": "ID", "name": "str", "year": "int|null", "region": "str",
                       "description": "physical description", "enclosure": "enclosure"}],
        "story_beats": [{"beat_id": "B001", "index": 0, "text": "exact script text of beat", "speaker_id": "ID|null",
                         "is_dialogue": "bool", "location_id": "ID", "year": "int|null", "characters": ["IDs physically present"],
                         "actions": [{"actor_id": "ID", "verb": "verb", "target": "character ID or object semantic|null", "emotion": "emotion"}],
                         "beat_type": "beat_type", "suggested_purpose": "suggested_purpose", "emotional_intensity": "0..1",
                         "tension": "0..1", "new_information": "bool", "comedy": "comedy", "opens_loops": ["L1"],
                         "closes_loops": [], "objects": ["object semantics visible"], "visual_opportunities": ["short phrases"],
                         "weather": "str|null", "est_duration_sec": "float (spoken length)"}],
        "relationships": [{"a": "ID", "b": "ID", "type": "str"}],
        "objects": [{"object_id": "ID", "semantic": "e.g. 'wooden field telephone, 1910s'", "category": "object category",
                     "materials": ["WOOD"], "period_year": "int|null"}],
        "historical_entities": [{"entity": "str", "category": "research category", "year": "int|null", "claim": "str",
                                 "confidence": "confidence", "needs_verification": "bool"}],
        "emotional_curve": ["float per beat 0..1"],
        "open_loops": [{"loop_id": "L1", "question": "str", "opened_beat": "B..", "closed_beat": "B..|null"}],
        "comedy_opportunities": ["str"], "tension_points": ["str"], "cliffhanger": "str",
        "research_requirements": [{"item": "str", "category": "research category", "question": "str", "confidence": "confidence"}],
    }
    mode = config.storytelling_mode
    return (
        f"STORYTELLING MODE: {mode}. Comedy level 0..1: {config.comedy_level}.\n"
        "Every script line must belong to exactly one beat (split long narration into beats of 1-2 sentences). "
        "Every character_id / location_id referenced in beats must be declared. Narrators that never appear "
        "physically: on_screen=false. Characters physically present in a beat go in beat.characters.\n"
        f"CLOSED VOCABULARIES:\n{vocab}\n\nJSON SCHEMA (shape):\n{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"SCRIPT:\n<<<\n{script}\n>>>"
    )


def bible_prompt(story_json: dict, config: PipelineConfig) -> str:
    vocab = "\n".join([
        _v("hair.shape", V.HAIR_SHAPES), _v("hair.hairline", V.HAIRLINES), _v("hair.part", V.HAIR_PARTS),
        _v("hair.length", V.HAIR_LENGTHS), _v("hair.fringe", V.FRINGES),
        _v("face.jaw_shape", V.JAW_SHAPES), _v("face.eye_shape", V.EYE_SHAPES), _v("face.brow_shape", V.BROW_SHAPES),
        _v("face.nose_style", V.NOSE_STYLES), _v("face.mouth_style", V.MOUTH_STYLES), _v("face.ear_style", V.EAR_STYLES),
        _v("face.facial_hair", V.FACIAL_HAIR), _v("face.distinctive_anchors[]", V.FACE_ANCHORS),
        _v("body.build", V.BUILDS), _v("body.posture", V.POSTURES), _v("variant.conditions[]", V.CONDITIONS),
        _v("costume.headwear", V.HEADWEAR), _v("costume.upper_garment", V.UPPER_GARMENTS),
        _v("costume.outerwear", V.OUTERWEAR), _v("costume.lower_garment", V.LOWER_GARMENTS),
        _v("costume.footwear", V.FOOTWEAR), _v("costume.equipment[]", V.EQUIPMENT),
        _v("costume.accessories[]", V.ACCESSORIES), _v("costume.condition", V.COSTUME_CONDITIONS),
        _v("detail_level", V.DetailLevel.values()), _v("confidence", V.HistoricalConfidence.values()),
        _v("location.enclosure", V.ENCLOSURES), _v("location.ceiling", V.CEILINGS),
        _v("location.wall_treatment", V.WALL_TREATMENTS), _v("location.floor_feature", V.FLOOR_FEATURES),
        _v("location.openings", V.OPENINGS), _v("location.horizon_feature", V.HORIZON_FEATURES),
        _v("location.lighting_behavior", V.LIGHTING_BEHAVIORS), _v("location.weather", V.WEATHER),
        _v("location.atmosphere[]", V.ATMOSPHERE_FX), _v("materials[]", V.MATERIALS), _v("density", V.DENSITIES),
        _v("prop.role", V.PROP_ROLES), _v("prop.category", V.PROP_CATEGORIES),
        _v("location.background_activity[]", V.BACKGROUND_ACTIVITY),
    ])
    schema = {
        "characters": [{
            "character_id": "same ID as story", "name": "str", "role": "role", "detail_level": "detail_level",
            "on_screen": "bool", "is_narrator": "bool", "historical_person": "bool", "birth_year": "int|null",
            "visual_identity": "one-line silhouette summary",
            "hair": {"shape": "", "hairline": "", "part": "", "length": "", "fringe": "", "volume": "0..1",
                     "roughness": "0..1", "strand_clusters": "0..10", "color": "#hex"},
            "face": {"head_width": "0.85..1.2", "head_height": "0.85..1.25", "jaw_shape": "", "eye_spacing": "0.8..1.2",
                     "eye_shape": "", "brow_shape": "", "nose_style": "", "mouth_style": "", "ear_style": "",
                     "facial_hair": "", "facial_hair_color": "#hex|null", "skin_tone": "#hex", "distinctive_anchors": []},
            "body": {"height": "0.85..1.15", "build": "", "shoulder_width": "0.8..1.25", "posture": "", "head_scale": "0.9..1.15"},
            "costumes": [{"costume_id": "ID", "label": "str", "year_from": "int|null", "year_to": "int|null",
                          "location_ids": ["LOC IDs where worn"], "contexts": ["MILITARY|CIVILIAN|HOSPITAL|FORMAL|WORK|RAIN|..."],
                          "costume": {"headwear": "", "upper_garment": "", "outerwear": "", "lower_garment": "", "footwear": "",
                                      "equipment": [], "accessories": [], "insignia": ["free text"], "condition": "",
                                      "palette": {"primary": "#hex", "secondary": "#hex", "accent": "#hex", "trim": "#hex"}},
                          "historical_confidence": "confidence"}],
            "variants": [{"variant_id": "ID", "year_from": "int|null", "year_to": "int|null", "age": "int|null",
                          "hair": "partial hair or null", "face": "partial face or null", "body": "partial body or null",
                          "conditions": [], "default_costume_id": "costume_id|null"}],
            "performance": {"gesture_scale": "0.5..1.5", "posture_bias": "-0.3..0.3", "movement_energy": "0.5..1.5",
                            "reaction_scale": "0.5..1.5", "confidence_bias": "-0.5..0.5"},
            "continuity_rules": ["str"], "historical_confidence": "confidence"}],
        "locations": [{
            "location_id": "same ID as story", "name": "str", "period_from": "int|null", "period_to": "int|null",
            "region": "str", "architecture": "free text style", "enclosure": "", "ceiling": "", "wall_treatment": "",
            "floor_feature": "", "openings": "", "horizon_feature": "", "materials": [],
            "palette": {"sky_top": "#hex", "sky_bottom": "#hex", "wall": "#hex", "floor": "#hex", "accent": "#hex", "shadow": "#hex"},
            "lighting_behavior": "", "weather": "", "atmosphere": [], "wear": "0..1", "density": "",
            "props": [{"semantic": "specific period-correct description", "category": "", "role": "", "materials": [], "count": "1..4",
                       "affordances": ["verbs it supports e.g. LIE, SIT, LEAN, OPERATE, GRIP, CARRY, PUSH, READ"]}],
            "foreground_vocabulary": [{"semantic": "", "category": "", "role": "FOREGROUND", "materials": []}],
            "background_activity": [], "historical_constraints": ["str"], "historical_confidence": "confidence"}],
    }
    return (
        "Design bibles for EVERY character and EVERY location of this story intelligence. Recurring characters need "
        "distinctive, readable silhouettes (hair + headwear + costume mass). If a character appears at different dates/ages "
        "or states (injured, older), add variants with year ranges. Costumes must be period/role/context correct. "
        "Location props: 4-8 period-correct semantic props with categories; include those needed by beat actions.\n"
        f"CLOSED VOCABULARIES:\n{vocab}\n\nJSON SCHEMA (shape):\n{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"STORY INTELLIGENCE:\n{json.dumps(story_json, ensure_ascii=False)}"
    )


def repair_prompt(original_prompt: str, issues: list[str]) -> str:
    return (original_prompt + "\n\nYOUR PREVIOUS JSON FAILED VALIDATION. Fix ALL issues and return the full corrected JSON:\n- "
            + "\n- ".join(issues[:40]))
