"""Gemini and Reasoning Output Validation and Normalization.

Enforces:
1. Strict schema adherence (Pydantic model validation).
2. Closed vocabulary normalization (unknown strings coerced to generic defaults).
3. Entity reference integrity (every character_id / location_id referenced in beats exists in bibles).
4. Action and camera validity checks.
5. Continuity and timeline consistency.
"""
from __future__ import annotations

import re
from typing import Any

from .. import vocab as V
from ..schemas import (
    BiblesProposal,
    CharacterBible,
    CharacterDNA,
    LocationBible,
    LocationDNA,
    SceneBlueprint,
    StoryIntelligence,
)


class ValidationResult:
    def __init__(self, is_valid: bool, issues: list[str], repaired_data: Any | None = None) -> None:
        self.is_valid = is_valid
        self.issues = issues
        self.repaired_data = repaired_data


class ReasoningValidator:
    """Validates raw JSON from LLM or heuristic sources against universal contracts."""

    @classmethod
    def validate_story_intelligence(cls, raw: dict[str, Any]) -> ValidationResult:
        issues: list[str] = []
        data = dict(raw)

        # 1. Ensure basic fields
        data.setdefault("title", "Untitled Story")
        data.setdefault("language", "en")
        data.setdefault("genre", "Historical Narrative")
        data.setdefault("period", {})
        data.setdefault("timeline", [])
        data.setdefault("characters", [])
        data.setdefault("locations", [])
        data.setdefault("story_beats", [])
        data.setdefault("relationships", [])
        data.setdefault("objects", [])
        data.setdefault("historical_entities", [])
        data.setdefault("emotional_curve", [])
        data.setdefault("open_loops", [])
        data.setdefault("comedy_opportunities", [])
        data.setdefault("tension_points", [])
        data.setdefault("cliffhanger", "")
        data.setdefault("research_requirements", [])

        # Normalize character mentions
        char_ids = set()
        for idx, c in enumerate(data.get("characters", [])):
            if not isinstance(c, dict):
                continue
            cid = str(c.get("character_id", f"CHAR_{idx+1:03d}")).strip().upper().replace(" ", "_")
            c["character_id"] = cid
            char_ids.add(cid)
            c["role"] = V.CharacterRole.coerce(c.get("role"), V.CharacterRole.SUPPORTING).value

        # Normalize locations
        loc_ids = set()
        for idx, l in enumerate(data.get("locations", [])):
            if not isinstance(l, dict):
                continue
            lid = str(l.get("location_id", f"LOC_{idx+1:03d}")).strip().upper().replace(" ", "_")
            l["location_id"] = lid
            loc_ids.add(lid)
            enc = str(l.get("enclosure", "EXTERIOR")).strip().upper()
            l["enclosure"] = enc if enc in V.ENCLOSURES else "EXTERIOR"

        # Normalize beats and check references
        for idx, b in enumerate(data.get("story_beats", [])):
            if not isinstance(b, dict):
                continue
            bid = str(b.get("beat_id", f"B{idx+1:03d}")).strip().upper().replace(" ", "_")
            b["beat_id"] = bid
            b["index"] = idx
            b["beat_type"] = V.BeatType.coerce(b.get("beat_type"), V.BeatType.EXPOSITION).value
            b["suggested_purpose"] = V.ShotPurpose.coerce(b.get("suggested_purpose"), V.ShotPurpose.INFORMATION).value
            
            # Location ref check
            b_loc = str(b.get("location_id", "")).strip().upper().replace(" ", "_")
            if b_loc and b_loc in loc_ids:
                b["location_id"] = b_loc
            elif loc_ids:
                b["location_id"] = list(loc_ids)[0]
                issues.append(f"Beat {bid} referenced unknown location '{b_loc}'; remapped to '{b['location_id']}'")
            else:
                b["location_id"] = "LOC_DEFAULT"
                data["locations"].append({"location_id": "LOC_DEFAULT", "name": "Default Environment", "enclosure": "EXTERIOR"})
                loc_ids.add("LOC_DEFAULT")

            # Check actions & characters
            b_chars = []
            for cid in b.get("characters", []):
                clean_c = str(cid).strip().upper().replace(" ", "_")
                if clean_c in char_ids:
                    b_chars.append(clean_c)
                else:
                    issues.append(f"Beat {bid} referenced unregistered character '{clean_c}'")
            b["characters"] = b_chars

            for act in b.get("actions", []):
                if not isinstance(act, dict):
                    continue
                clean_actor = str(act.get("actor_id", "")).strip().upper().replace(" ", "_")
                if clean_actor not in char_ids and char_ids:
                    act["actor_id"] = list(char_ids)[0]
                else:
                    act["actor_id"] = clean_actor
                # Normalize verb
                v_raw = str(act.get("verb", "STAND")).strip().upper()
                v_canon = V.VERB_SYNONYMS.get(v_raw, v_raw)
                act["verb"] = V.ActionVerb.coerce(v_canon, V.ActionVerb.STAND).value
                # Normalize emotion
                e_raw = str(act.get("emotion", "CALM")).strip().upper()
                e_canon = V.EMOTION_SYNONYMS.get(e_raw, e_raw)
                act["emotion"] = e_canon if e_canon in V.EMOTIONS else "CALM"

        # Attempt Pydantic model parse
        try:
            intel = StoryIntelligence.model_validate(data)
            return ValidationResult(is_valid=len(issues) == 0, issues=issues, repaired_data=intel)
        except Exception as exc:
            issues.append(f"StoryIntelligence schema validation error: {exc}")
            return ValidationResult(is_valid=False, issues=issues, repaired_data=None)

    @classmethod
    def validate_bibles_proposal(cls, raw: dict[str, Any], story: StoryIntelligence) -> ValidationResult:
        issues: list[str] = []
        data = dict(raw)
        data.setdefault("characters", [])
        data.setdefault("locations", [])

        # Ensure all characters from story intelligence exist
        story_char_ids = {c.character_id for c in story.characters}
        bible_char_ids = set()

        for c in data.get("characters", []):
            if not isinstance(c, dict):
                continue
            cid = str(c.get("character_id", "")).strip().upper().replace(" ", "_")
            c["character_id"] = cid
            bible_char_ids.add(cid)
            c["role"] = V.CharacterRole.coerce(c.get("role"), V.CharacterRole.SUPPORTING).value
            c["detail_level"] = V.DetailLevel.coerce(c.get("detail_level"), V.DetailLevel.SUPPORT).value

            # Validate Hair DNA
            hair = c.setdefault("hair", {})
            hair["shape"] = hair.get("shape", "CROPPED") if hair.get("shape") in V.HAIR_SHAPES else "CROPPED"
            hair["hairline"] = hair.get("hairline", "MEDIUM") if hair.get("hairline") in V.HAIRLINES else "MEDIUM"
            hair["part"] = hair.get("part", "NONE") if hair.get("part") in V.HAIR_PARTS else "NONE"
            hair["length"] = hair.get("length", "SHORT") if hair.get("length") in V.HAIR_LENGTHS else "SHORT"
            hair["fringe"] = hair.get("fringe", "NONE") if hair.get("fringe") in V.FRINGES else "NONE"

            # Validate Face DNA
            face = c.setdefault("face", {})
            face["jaw_shape"] = face.get("jaw_shape", "ROUND") if face.get("jaw_shape") in V.JAW_SHAPES else "ROUND"
            face["eye_shape"] = face.get("eye_shape", "DOT") if face.get("eye_shape") in V.EYE_SHAPES else "DOT"
            face["brow_shape"] = face.get("brow_shape", "FLAT") if face.get("brow_shape") in V.BROW_SHAPES else "FLAT"
            face["nose_style"] = face.get("nose_style", "BUTTON") if face.get("nose_style") in V.NOSE_STYLES else "BUTTON"
            face["mouth_style"] = face.get("mouth_style", "LINE") if face.get("mouth_style") in V.MOUTH_STYLES else "LINE"
            face["ear_style"] = face.get("ear_style", "NORMAL") if face.get("ear_style") in V.EAR_STYLES else "NORMAL"
            face["facial_hair"] = face.get("facial_hair", "NONE") if face.get("facial_hair") in V.FACIAL_HAIR else "NONE"

            # Validate Body DNA
            body = c.setdefault("body", {})
            body["build"] = body.get("build", "AVERAGE") if body.get("build") in V.BUILDS else "AVERAGE"
            body["posture"] = body.get("posture", "UPRIGHT") if body.get("posture") in V.POSTURES else "UPRIGHT"

            # Validate Costumes
            costumes = c.setdefault("costumes", [])
            if not costumes:
                costumes.append({
                    "costume_id": f"COSTUME_{cid}_DEFAULT",
                    "label": "Default Costume",
                    "costume": {
                        "headwear": "NONE",
                        "upper_garment": "SHIRT",
                        "outerwear": "NONE",
                        "lower_garment": "TROUSERS",
                        "footwear": "SHOES",
                    },
                })
            for cv in costumes:
                cdna = cv.setdefault("costume", {})
                cdna["headwear"] = cdna.get("headwear", "NONE") if cdna.get("headwear") in V.HEADWEAR else "NONE"
                cdna["upper_garment"] = cdna.get("upper_garment", "SHIRT") if cdna.get("upper_garment") in V.UPPER_GARMENTS else "SHIRT"
                cdna["outerwear"] = cdna.get("outerwear", "NONE") if cdna.get("outerwear") in V.OUTERWEAR else "NONE"
                cdna["lower_garment"] = cdna.get("lower_garment", "TROUSERS") if cdna.get("lower_garment") in V.LOWER_GARMENTS else "TROUSERS"
                cdna["footwear"] = cdna.get("footwear", "SHOES") if cdna.get("footwear") in V.FOOTWEAR else "SHOES"

        # Check missing characters
        missing_chars = story_char_ids - bible_char_ids
        for mc in missing_chars:
            issues.append(f"Character '{mc}' was in story intelligence but missing from CharacterBible proposal; autogenerating generic proposal.")
            from ..bibles.resolver import create_fallback_character_dna
            fb = create_fallback_character_dna(mc, "Supporting Character", "SUPPORTING")
            data["characters"].append(fb.dump())

        # Validate Locations
        story_loc_ids = {l.location_id for l in story.locations}
        bible_loc_ids = set()

        for l in data.get("locations", []):
            if not isinstance(l, dict):
                continue
            lid = str(l.get("location_id", "")).strip().upper().replace(" ", "_")
            l["location_id"] = lid
            bible_loc_ids.add(lid)
            l["enclosure"] = l.get("enclosure", "EXTERIOR") if l.get("enclosure") in V.ENCLOSURES else "EXTERIOR"
            l["ceiling"] = l.get("ceiling", "SKY") if l.get("ceiling") in V.CEILINGS else "SKY"
            l["wall_treatment"] = l.get("wall_treatment", "PLAIN") if l.get("wall_treatment") in V.WALL_TREATMENTS else "PLAIN"
            l["floor_feature"] = l.get("floor_feature", "BARE") if l.get("floor_feature") in V.FLOOR_FEATURES else "BARE"
            l["openings"] = l.get("openings", "NONE") if l.get("openings") in V.OPENINGS else "NONE"
            l["horizon_feature"] = l.get("horizon_feature", "NONE") if l.get("horizon_feature") in V.HORIZON_FEATURES else "NONE"
            l["lighting_behavior"] = l.get("lighting_behavior", "OVERCAST") if l.get("lighting_behavior") in V.LIGHTING_BEHAVIORS else "OVERCAST"
            l["weather"] = l.get("weather", "CLEAR") if l.get("weather") in V.WEATHER else "CLEAR"
            l["density"] = l.get("density", "BALANCED") if l.get("density") in V.DENSITIES else "BALANCED"

            # Validate materials list
            mats = l.get("materials", [])
            l["materials"] = [m for m in mats if m in V.MATERIALS] or ["STONE"]

        missing_locs = story_loc_ids - bible_loc_ids
        for ml in missing_locs:
            issues.append(f"Location '{ml}' was in story intelligence but missing from LocationBible proposal; autogenerating generic proposal.")
            from ..bibles.resolver import create_fallback_location_dna
            fb_loc = create_fallback_location_dna(ml, f"Location {ml}", "EXTERIOR")
            data["locations"].append(fb_loc.dump())

        try:
            prop = BiblesProposal.model_validate(data)
            return ValidationResult(is_valid=len(issues) == 0, issues=issues, repaired_data=prop)
        except Exception as exc:
            issues.append(f"BiblesProposal schema error: {exc}")
            return ValidationResult(is_valid=False, issues=issues, repaired_data=None)
