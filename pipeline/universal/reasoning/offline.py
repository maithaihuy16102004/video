"""Deterministic rule-based / heuristic reasoning provider for offline execution & testing.

Parses arbitrary scripts (Vietnamese or English or others) into structured StoryIntelligence
and produces valid generic CharacterBible and LocationBible proposals without API calls.
"""
from __future__ import annotations

import re
from typing import Any

from .. import vocab as V
from ..schemas import (
    BeatAction,
    CharacterDNA,
    CharacterMention,
    CostumeDNA,
    CostumeVariant,
    FaceDNA,
    HairStyleDNA,
    HistoricalEntity,
    LocationDNA,
    LocationMention,
    Period,
    PropSpec,
    StoryBeat,
    StoryIntelligence,
    StoryObject,
)


class OfflineReasoningProvider:
    name = "offline"
    model = "heuristic-v1"

    def complete_json(self, stage: str, system: str, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        if stage == "story_intelligence":
            return self._analyze_script_offline(prompt, context)
        elif stage == "bibles":
            return self._generate_bibles_offline(prompt, context)
        else:
            raise NotImplementedError(f"Offline provider cannot handle stage {stage}")

    def _analyze_script_offline(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        # Extract script text from prompt
        match = re.search(r"SCRIPT:\s*<<<\s*(.*?)\s*>>>", prompt, re.DOTALL)
        text = match.group(1) if match else prompt

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        beats: list[dict[str, Any]] = []
        chars_found: dict[str, dict[str, Any]] = {}
        locs_found: dict[str, dict[str, Any]] = {}
        all_years: list[int] = []

        current_location_id = "LOC_DEFAULT"
        current_location_name = "Default Location"
        current_year: int | None = None

        beat_idx = 0
        buf: list[str] = []
        current_speaker: str | None = None

        def clean_id(name: str, prefix: str = "ID") -> str:
            slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
            return f"{prefix}_{slug}" if slug else f"{prefix}_{beat_idx+1:03d}"

        def flush_buf():
            nonlocal beat_idx, buf, current_speaker
            if not buf:
                return
            b_text = " ".join(buf).strip()
            buf = []
            if not b_text:
                return

            yr_match = re.findall(r"\b(1[6-9]\d\d|20\d\d)\b", b_text)
            yr = int(yr_match[0]) if yr_match else current_year
            if yr and yr not in all_years:
                all_years.append(yr)

            low = b_text.lower()
            btype = "EXPOSITION"
            purpose = "INFORMATION"
            verb = "STAND"
            emotion = "CALM"

            if beat_idx == 0 or "tưởng tượng" in low or "imagine" in low or "cold open" in low:
                btype = "HOOK"
                purpose = "LOCATION"
                verb = "LOOK"
                emotion = "ATTENTIVE"
            elif any(k in low for k in ("spoiler", "tuyệt vời", "ironic", "payoff", "kết quả")):
                btype = "PAYOFF"
                purpose = "REACTION"
                verb = "SPEAK"
                emotion = "AMUSED"
            elif any(k in low for k in ("bắn", "pháo", "nổ", "chiến tranh", "tấn công", "attack", "conflict", "fight")):
                btype = "CONFLICT"
                purpose = "ACTION"
                verb = "DUCK"
                emotion = "AFRAID"
            elif any(k in low for k in ("bị thương", "khí độc", "thất bại", "wounded", "hospital", "bệnh viện")):
                btype = "REVERSAL"
                purpose = "EMOTION"
                verb = "LIE"
                emotion = "EXHAUSTED"
            elif any(k in low for k in ("thí nghiệm", "máy móc", "tia lửa", "ghi chép", "laboratory", "machine", "spark", "note")):
                btype = "SETUP"
                purpose = "ACTION"
                verb = "OPERATE" if "máy" in low or "machine" in low else "WRITE"
                emotion = "ATTENTIVE"
            elif any(k in low for k in ("tập tiếp theo", "tập 2", "to be continued", "cliffhanger", "ý kiến")):
                btype = "CLIFFHANGER"
                purpose = "REVEAL"
                verb = "GESTURE"
                emotion = "DETERMINED"

            # Detect actors present
            active_chars = []
            if current_speaker and current_speaker in chars_found:
                active_chars.append(chars_found[current_speaker]["character_id"])
            for cname, cdata in chars_found.items():
                cid = cdata["character_id"]
                if (cname.lower() in low or cid.lower() in low) and cid not in active_chars:
                    active_chars.append(cid)

            actions = []
            for cid in active_chars:
                actions.append({
                    "actor_id": cid,
                    "verb": verb,
                    "target": None,
                    "emotion": emotion,
                })

            dur = max(2.0, min(8.0, len(b_text.split()) / 2.6))
            beat_id = f"B{beat_idx+1:03d}"
            beats.append({
                "beat_id": beat_id,
                "index": beat_idx,
                "text": b_text,
                "speaker_id": chars_found[current_speaker]["character_id"] if current_speaker in chars_found else None,
                "is_dialogue": current_speaker is not None,
                "location_id": current_location_id,
                "year": yr,
                "characters": active_chars,
                "actions": actions,
                "beat_type": btype,
                "suggested_purpose": purpose,
                "emotional_intensity": 0.5,
                "tension": 0.4,
                "new_information": True,
                "comedy": "NONE",
                "opens_loops": [],
                "closes_loops": [],
                "objects": [],
                "visual_opportunities": [],
                "weather": None,
                "est_duration_sec": round(dur, 2),
            })
            beat_idx += 1
            current_speaker = None

        for line in lines:
            # Header check: [SCENE / LOCATION, YEAR]
            m_header = re.match(r"^\[(.*?)\]$", line)
            if m_header:
                flush_buf()
                h_text = m_header.group(1).strip()
                # Find year
                y_m = re.search(r"\b(1[6-9]\d\d|20\d\d)\b", h_text)
                if y_m:
                    current_year = int(y_m.group(1))
                    if current_year not in all_years:
                        all_years.append(current_year)
                # Clean location name
                clean_loc = re.sub(r"^(CẢNH|SCENE|HOOK|COLD OPEN)\s*[-–—:]*\s*", "", h_text, flags=re.I)
                clean_loc = re.sub(r"[-–—,]\s*(1[6-9]\d\d|20\d\d).*", "", clean_loc).strip()
                if clean_loc:
                    loc_id = clean_id(clean_loc, "LOC")
                    current_location_id = loc_id
                    current_location_name = clean_loc
                    if loc_id not in locs_found:
                        locs_found[loc_id] = {
                            "location_id": loc_id,
                            "name": clean_loc,
                            "year": current_year,
                            "region": "Historical Context",
                            "description": f"Location: {clean_loc}",
                            "enclosure": "INTERIOR" if any(k in clean_loc.lower() for k in ("hall", "ward", "hospital", "lab", "room", "quán", "nhà", "phòng")) else "EXTERIOR",
                        }
                continue

            # Speaker check: SPEAKER: Text
            m_spk = re.match(r"^([A-ZÀ-Ỹ0-9\s_]{2,35}):\s*(.*)$", line)
            if m_spk:
                flush_buf()
                spk_raw = m_spk.group(1).strip()
                dia_text = m_spk.group(2).strip()
                cid = clean_id(spk_raw, "CHAR")
                is_narrator = any(k in spk_raw.lower() for k in ("người dẫn", "narrator", "voiceover", "vo"))
                if is_narrator:
                    # Under FIRST_PERSON_ROLEPLAY axiom: protagonist owns narration
                    spk_raw = "Protagonist"
                    cid = "CHAR_PROTAGONIST"
                    is_narrator = False
                if spk_raw not in chars_found:
                    chars_found[spk_raw] = {
                        "character_id": cid,
                        "name": spk_raw,
                        "role": "NARRATOR" if is_narrator else ("PROTAGONIST" if len(chars_found) <= 1 else "SUPPORTING"),
                        "aliases": [spk_raw],
                        "is_narrator": is_narrator,
                        "on_screen": not is_narrator,
                        "speaking": True,
                        "historical_person": not is_narrator,
                        "birth_year": None,
                        "description": f"Character: {spk_raw}",
                    }
                current_speaker = spk_raw
                if dia_text:
                    buf.append(dia_text)
                    flush_buf()
                continue

            buf.append(line)
            if len(" ".join(buf).split()) >= 20 or line.endswith((".", "!", "?")):
                flush_buf()

        flush_buf()

        if not beats:
            beats.append({
                "beat_id": "B001",
                "index": 0,
                "text": "Opening narration",
                "speaker_id": None,
                "is_dialogue": False,
                "location_id": current_location_id,
                "year": current_year,
                "characters": [],
                "actions": [],
                "beat_type": "EXPOSITION",
                "suggested_purpose": "LOCATION",
                "emotional_intensity": 0.3,
                "tension": 0.2,
                "new_information": True,
                "comedy": "NONE",
                "opens_loops": [],
                "closes_loops": [],
                "objects": [],
                "visual_opportunities": [],
                "weather": None,
                "est_duration_sec": 3.0,
            })

        if not locs_found:
            locs_found["LOC_DEFAULT"] = {
                "location_id": "LOC_DEFAULT",
                "name": "Primary Scene Location",
                "year": current_year,
                "region": "General",
                "description": "Primary environment",
                "enclosure": "EXTERIOR",
            }

        # Make sure every character mentioned in beats exists
        chars_list = list(chars_found.values())
        if not chars_list:
            chars_list.append({
                "character_id": "CHAR_PROTAGONIST",
                "name": "Protagonist",
                "role": "PROTAGONIST",
                "aliases": [],
                "is_narrator": False,
                "on_screen": True,
                "speaking": False,
                "historical_person": False,
                "birth_year": None,
                "description": "Main character",
            })

        start_yr = min(all_years) if all_years else None
        end_yr = max(all_years) if all_years else None

        return {
            "title": "Story Intelligence",
            "language": "vi" if any(ord(c) > 127 for c in text) else "en",
            "genre": "Historical Narrative",
            "period": {"start_year": start_yr, "end_year": end_yr},
            "timeline": [{"event_id": f"E{i+1:02d}", "year": y, "month": None, "description": f"Year {y}", "location_id": None, "confidence": "PLAUSIBLE_RECONSTRUCTION"} for i, y in enumerate(sorted(all_years))],
            "characters": chars_list,
            "locations": list(locs_found.values()),
            "story_beats": beats,
            "relationships": [],
            "objects": [],
            "historical_entities": [],
            "emotional_curve": [b["emotional_intensity"] for b in beats],
            "open_loops": [],
            "comedy_opportunities": [],
            "tension_points": [],
            "cliffhanger": "",
            "research_requirements": [],
            "reasoning_source": "OFFLINE_HEURISTIC",
        }

    def _generate_bibles_offline(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        # Generate generic bibles matching the characters and locations in story intelligence
        story_intel = context.get("story_intelligence")
        if not story_intel:
            # Fallback parse from prompt
            return {"characters": [], "locations": []}

        characters_out = []
        for c in story_intel.characters:
            cid = c.character_id
            name = c.name
            role = c.role
            is_hero = role == "PROTAGONIST"

            # Hair parameters
            hair = {
                "shape": "SWEPT_SIDE" if is_hero else "CROPPED",
                "hairline": "MEDIUM",
                "part": "LEFT" if is_hero else "NONE",
                "length": "SHORT",
                "fringe": "SIDE_SWEEP" if is_hero else "NONE",
                "volume": 0.6 if is_hero else 0.4,
                "roughness": 0.3,
                "strand_clusters": 5 if is_hero else 3,
                "color": "#2c221a",
            }

            face = {
                "head_width": 1.0,
                "head_height": 1.05 if is_hero else 1.0,
                "jaw_shape": "SQUARE" if is_hero else "ROUND",
                "eye_spacing": 1.0,
                "eye_shape": "DOT",
                "brow_shape": "ARCHED" if is_hero else "FLAT",
                "nose_style": "POINTED" if is_hero else "BUTTON",
                "mouth_style": "LINE",
                "ear_style": "NORMAL",
                "facial_hair": "NONE",
                "facial_hair_color": None,
                "skin_tone": "#eed8be",
                "distinctive_anchors": [],
            }

            body = {
                "height": 1.05 if is_hero else 1.0,
                "build": "AVERAGE",
                "shoulder_width": 1.0,
                "posture": "UPRIGHT",
                "head_scale": 1.0,
            }

            costume_default = {
                "costume_id": f"COSTUME_{cid}_DEFAULT",
                "label": "Standard Period Garment",
                "year_from": None,
                "year_to": None,
                "location_ids": [],
                "contexts": ["DEFAULT"],
                "costume": {
                    "headwear": "NONE",
                    "upper_garment": "JACKET" if is_hero else "SHIRT",
                    "outerwear": "NONE",
                    "lower_garment": "TROUSERS",
                    "footwear": "SHOES",
                    "equipment": [],
                    "accessories": [],
                    "insignia": [],
                    "condition": "CLEAN",
                    "palette": {
                        "primary": "#3a4454" if is_hero else "#50545a",
                        "secondary": "#22262e",
                        "accent": "#b88a44",
                        "trim": "#111418",
                    },
                },
                "historical_confidence": "PLAUSIBLE_RECONSTRUCTION",
            }

            characters_out.append({
                "character_id": cid,
                "name": name,
                "role": role,
                "detail_level": "HERO" if is_hero else "SUPPORT",
                "on_screen": c.on_screen,
                "is_narrator": c.is_narrator,
                "historical_person": c.historical_person,
                "birth_year": c.birth_year,
                "visual_identity": f"Distinctive silhouette for {name}",
                "hair": hair,
                "face": face,
                "body": body,
                "costumes": [costume_default],
                "variants": [],
                "performance": {
                    "gesture_scale": 1.2 if is_hero else 1.0,
                    "posture_bias": 0.1 if is_hero else 0.0,
                    "movement_energy": 1.1 if is_hero else 1.0,
                    "reaction_scale": 1.1 if is_hero else 1.0,
                    "confidence_bias": 0.2 if is_hero else 0.0,
                },
                "continuity_rules": [],
                "historical_confidence": "PLAUSIBLE_RECONSTRUCTION",
                "proposal_source": "OFFLINE_HEURISTIC",
            })

        locations_out = []
        for loc in story_intel.locations:
            lid = loc.location_id
            name = loc.name
            is_interior = loc.enclosure == "INTERIOR" or any(k in name.lower() for k in ("hall", "room", "ward", "lab", "quán", "nhà", "phòng"))

            locations_out.append({
                "location_id": lid,
                "name": name,
                "period_from": None,
                "period_to": None,
                "region": loc.region or "European",
                "architecture": "Historical Period Architecture",
                "enclosure": "INTERIOR" if is_interior else "EXTERIOR",
                "ceiling": "BEAMED" if is_interior else "SKY",
                "wall_treatment": "WAINSCOT" if is_interior else "PLAIN",
                "floor_feature": "PLANKS" if is_interior else "COBBLES",
                "openings": "WINDOWS_TALL" if is_interior else "NONE",
                "horizon_feature": "NONE" if is_interior else "CITY_SKYLINE",
                "materials": ["WOOD", "PLASTER", "GLASS"] if is_interior else ["STONE", "BRICK", "EARTH"],
                "palette": {
                    "sky_top": "#42566c" if is_interior else "#7a9cb8",
                    "sky_bottom": "#2d3540" if is_interior else "#c4d2de",
                    "wall": "#8c7e6c" if is_interior else "#9e9488",
                    "floor": "#4a3c2c" if is_interior else "#544e46",
                    "accent": "#c69248",
                    "shadow": "#1b1916",
                },
                "lighting_behavior": "WARM_POOLS" if is_interior else "OVERCAST",
                "weather": "CLEAR",
                "atmosphere": ["HAZE"] if is_interior else [],
                "wear": 0.35,
                "density": "BALANCED",
                "props": [
                    {"semantic": "Period wooden table", "category": "TABLE", "role": "DRESSING", "materials": ["WOOD"], "count": 1, "affordances": ["LEAN", "PLACE"]},
                    {"semantic": "Seating bench or chairs", "category": "BENCH", "role": "DRESSING", "materials": ["WOOD"], "count": 2, "affordances": ["SIT"]},
                    {"semantic": "Wall-mounted lighting", "category": "LAMP", "role": "WALL", "materials": ["METAL", "GLASS"], "count": 2, "affordances": []},
                ],
                "foreground_vocabulary": [
                    {"semantic": "Foreground edge framing structure", "category": "POST", "role": "FOREGROUND", "materials": ["WOOD"]},
                ],
                "background_activity": ["DISTANT_FIGURES"],
                "historical_constraints": [],
                "reusable_masters": [],
                "historical_confidence": "PLAUSIBLE_RECONSTRUCTION",
                "proposal_source": "OFFLINE_HEURISTIC",
            })

        return {"characters": characters_out, "locations": locations_out}
