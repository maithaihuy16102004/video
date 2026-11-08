"""Universal First-Person Historical Roleplay Script Compiler & POV Knowledge Validator.

Architectural Principles:
1. THIS PROJECT IS NOT A NARRATOR-LED DOCUMENTARY.
2. FIRST-PERSON HISTORICAL ROLEPLAY STORYTELLING: The MAIN CHARACTER tells their own story ("I / ME / MY").
3. NO DEFAULT EXTERNAL NARRATOR: MAIN CHARACTER = PROTAGONIST + PRIMARY STORYTELLER + PRIMARY VOICE.
4. STORY POV != CAMERA POV: The camera is free to leave the protagonist (framing wide shots, maps,
   documents, objects, battlefields, or other characters); their voice continues.
5. RETROSPECTIVE VS IMMEDIATE KNOWLEDGE:
   - IMMEDIATE: What the character experienced/observed at that moment.
   - RETROSPECTIVE: Later knowledge framed naturally ("Về sau tôi mới hiểu...").
   - POV_KNOWLEDGE_GAP: Flagged if character claims impossible knowledge; never silently switch to narrator.
6. ZERO SPEEDUP: speed_ratio == 1.0 strictly.
7. UNIVERSAL & EXTENSIBLE: Works for any protagonist (Hitler, Napoleon, Tesla, Caesar) with zero core-code edits.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .voice_types import (
    DeliveryStyle,
    EmotionState,
    LineType,
    POVCharacterState,
    POVKnowledgeType,
    ProvenanceType,
    SpokenLine,
    StorytellingMode,
)


@dataclass
class POVValidationIssue:
    script_line_id: str
    issue_type: str            # "POV_KNOWLEDGE_GAP", "THIRD_PERSON_LEAKAGE", "PRONOUN_OVERUSE", "NARRATOR_INTRUSION"
    severity: str              # "ERROR", "WARNING", "INFO"
    line_text: str
    explanation: str
    suggested_fix: str


@dataclass
class FirstPersonCompilationResult:
    storytelling_mode: StorytellingMode
    primary_pov_character_id: str
    total_lines: int
    protagonist_narration_lines: int
    protagonist_dialogue_lines: int
    supporting_dialogue_lines: int
    external_narrator_lines: int       # MUST BE 0 IN FIRST_PERSON_ROLEPLAY
    retrospective_lines: int
    immediate_lines: int
    compiled_lines: list[SpokenLine]
    pov_state: POVCharacterState
    validation_issues: list[POVValidationIssue] = field(default_factory=list)
    has_knowledge_gap: bool = False
    is_valid: bool = True


class POVKnowledgeValidator:
    """Validates epistemic plausibility of what the first-person protagonist narrates."""

    # Patterns indicating retrospective historical knowledge
    RETROSPECTIVE_MARKERS = [
        r"\bvề sau\b", r"\bsau này\b", r"\bmãi sau\b", r"\blúc đó tôi chưa biết\b",
        r"\blúc ấy tôi đâu ngờ\b", r"\bngười ta sau này mới hiểu\b", r"\blịch sử sau này\b",
        r"\btôi cứ nghĩ\b", r"\btôi đâu biết\b", r"\bvề sau tôi mới hiểu\b",
        r"\bnhìn lại\b", r"\blời nói dối\b", r"\bcuối cùng thì\b"
    ]

    # Patterns indicating impossible omniscient knowledge at the moment
    OMNISCIENT_LEAKAGE_MARKERS = [
        r"\btrong đầu (?:ông|hắn|anh) ta đang nghĩ\b",
        r"\bở một nơi xa xôi không ai biết\b",
        r"\btại tổng hành dinh bí mật\b"
    ]

    # Third person narrator intrusion patterns
    THIRD_PERSON_INTRUSION_MARKERS = [
        r"\bngười dẫn\b", r"\bngười dẫn chuyện\b", r"\bnarrator\b",
        r"\bhãy tưởng tượng bạn\b", r"\bbạn có biết\b", r"\bnhư chúng ta đã biết\b"
    ]

    @classmethod
    def validate_line_knowledge(
        cls,
        text: str,
        speaker_id: str,
        primary_pov_character_id: str,
        is_dialogue: bool = False,
    ) -> tuple[POVKnowledgeType, Optional[POVValidationIssue]]:
        """Classifies knowledge type and checks for epistemic gaps or third-person leakage."""
        text_lower = text.lower()

        # If it's dialogue, it's direct spoken interaction
        if is_dialogue:
            return POVKnowledgeType.DIRECT_EXPERIENCE, None

        # Check for third-person narrator intrusion
        for pat in cls.THIRD_PERSON_INTRUSION_MARKERS:
            if re.search(pat, text_lower):
                issue = POVValidationIssue(
                    script_line_id="",
                    issue_type="THIRD_PERSON_LEAKAGE",
                    severity="ERROR",
                    line_text=text,
                    explanation=f"Line contains documentary/external narrator phrasing matching '{pat}'.",
                    suggested_fix="Reframe from the first-person protagonist perspective ('tôi')."
                )
                return POVKnowledgeType.UNCERTAIN_RECONSTRUCTION, issue

        # Check for retrospective knowledge framing
        is_retrospective = any(re.search(pat, text_lower) for pat in cls.RETROSPECTIVE_MARKERS)

        # Check for omniscient knowledge gap (impossible knowledge without retrospective framing)
        has_omniscient = any(re.search(pat, text_lower) for pat in cls.OMNISCIENT_LEAKAGE_MARKERS)
        if has_omniscient and not is_retrospective:
            issue = POVValidationIssue(
                script_line_id="",
                issue_type="POV_KNOWLEDGE_GAP",
                severity="ERROR",
                line_text=text,
                explanation="Protagonist claims omniscient knowledge without retrospective narrative framing.",
                suggested_fix="Frame with retrospective phrasing ('Về sau tôi mới biết...') or restrict to protagonist observation."
            )
            return POVKnowledgeType.UNCERTAIN_RECONSTRUCTION, issue

        if is_retrospective:
            return POVKnowledgeType.RETROSPECTIVE_CONTEXT, None

        # Check for observation / inner thought / action
        if any(w in text_lower for w in ["tôi nhìn", "tôi thấy", "trước mắt tôi", "trông thấy"]):
            return POVKnowledgeType.OBSERVATION, None
        if any(w in text_lower for w in ["tôi nghĩ", "tôi cảm thấy", "trong lòng tôi", "tự hỏi"]):
            return POVKnowledgeType.INNER_THOUGHT, None
        if any(w in text_lower for w in ["tôi bước", "tôi đi", "tôi nộp đơn", "tôi cầm", "gia nhập"]):
            return POVKnowledgeType.ACTION, None

        return POVKnowledgeType.DIRECT_EXPERIENCE, None


class FirstPersonScriptCompiler:
    """Universal compiler converting story scripts into canonical First-Person Roleplay SpokenLines."""

    def __init__(self, default_mode: StorytellingMode = StorytellingMode.FIRST_PERSON_ROLEPLAY):
        self.default_mode = default_mode
        self.validator = POVKnowledgeValidator()

    def resolve_primary_pov_character(
        self,
        raw_script_metadata: dict[str, Any],
        characters: list[dict[str, Any]],
    ) -> str:
        """Dynamically identifies the primary POV character from story metadata without hardcoding."""
        # 1. Check explicit configuration
        if "primary_pov_character_id" in raw_script_metadata and raw_script_metadata["primary_pov_character_id"]:
            return raw_script_metadata["primary_pov_character_id"]

        # 2. Check character roles for protagonist
        for c in characters:
            role = str(c.get("role", "")).lower()
            role_type = str(c.get("role_type", "")).lower()
            if any(k in role or k in role_type for k in ["protagonist", "chính", "lead", "storyteller", "tôi"]):
                return c.get("character_id") or c.get("id")

        # 3. Fallback to first non-narrator character
        for c in characters:
            cid = c.get("character_id") or c.get("id") or ""
            if "narrator" not in cid.lower():
                return cid

        return "protagonist_char"

    def compile(
        self,
        raw_lines: list[dict[str, Any]],
        primary_pov_character_id: str,
        storytelling_mode: StorytellingMode = StorytellingMode.FIRST_PERSON_ROLEPLAY,
        pov_state: Optional[POVCharacterState] = None,
    ) -> FirstPersonCompilationResult:
        """Compiles raw script lines into First-Person SpokenLine representations."""
        compiled_lines: list[SpokenLine] = []
        issues: list[POVValidationIssue] = []

        if pov_state is None:
            pov_state = POVCharacterState(
                primary_pov_character_id=primary_pov_character_id,
                storytelling_mode=storytelling_mode,
            )

        protagonist_narration = 0
        protagonist_dialogue = 0
        supporting_dialogue = 0
        external_narrator = 0
        retrospective_count = 0
        immediate_count = 0

        for idx, line_dict in enumerate(raw_lines, start=1):
            line_id = line_dict.get("script_line_id", f"LINE_{idx:03d}")
            raw_speaker = str(line_dict.get("speaker_id") or line_dict.get("speaker", "")).strip()
            raw_text = str(line_dict.get("exact_text") or line_dict.get("text", "")).strip()
            is_dialogue = bool(line_dict.get("is_dialogue", False))
            char_id = line_dict.get("character_id")

            # Camera suggestions to prove STORY POV != CAMERA POV
            shot_suggestion = line_dict.get("camera_shot_suggestion") or self._suggest_camera_shot(line_dict, idx)
            camera_is_pov = bool(line_dict.get("camera_is_pov", False))

            # Roleplay Compilation Logic
            if storytelling_mode == StorytellingMode.FIRST_PERSON_ROLEPLAY:
                # If the line was originally marked "NARRATOR" or "NGƯỜI DẪN", RE-ASSIGN TO PROTAGONIST!
                if raw_speaker.upper() in ["NARRATOR", "NGƯỜI DẪN", "SPEAKER_NARRATOR", "VOICEOVER"]:
                    speaker_id = primary_pov_character_id
                    assigned_char_id = primary_pov_character_id
                    line_type = LineType.NARRATION
                    protagonist_narration += 1
                elif raw_speaker == primary_pov_character_id or char_id == primary_pov_character_id:
                    speaker_id = primary_pov_character_id
                    assigned_char_id = primary_pov_character_id
                    if is_dialogue:
                        line_type = LineType.DIALOGUE
                        protagonist_dialogue += 1
                    else:
                        line_type = LineType.NARRATION
                        protagonist_narration += 1
                else:
                    # Supporting character speaking dialogue
                    speaker_id = raw_speaker
                    assigned_char_id = char_id or raw_speaker
                    line_type = LineType.DIALOGUE if is_dialogue else LineType.NARRATION
                    if is_dialogue:
                        supporting_dialogue += 1
                    else:
                        # In FIRST_PERSON_ROLEPLAY, non-protagonists DO NOT narrate!
                        # If a non-protagonist is attempting to narrate, flag as issue
                        issues.append(POVValidationIssue(
                            script_line_id=line_id,
                            issue_type="NARRATOR_INTRUSION",
                            severity="ERROR",
                            line_text=raw_text,
                            explanation=f"Supporting character '{speaker_id}' cannot narrate in FIRST_PERSON_ROLEPLAY mode.",
                            suggested_fix=f"Reassign narration to '{primary_pov_character_id}' or make line dialogue."
                        ))
                        external_narrator += 1
            else:
                # Documentary or Third-Person mode
                speaker_id = raw_speaker
                assigned_char_id = char_id
                line_type = LineType.DIALOGUE if is_dialogue else LineType.NARRATION
                if line_type == LineType.NARRATION:
                    external_narrator += 1
                elif speaker_id == primary_pov_character_id:
                    protagonist_dialogue += 1
                else:
                    supporting_dialogue += 1

            # Epistemic & Knowledge Validation
            k_type, issue = self.validator.validate_line_knowledge(
                text=raw_text,
                speaker_id=speaker_id,
                primary_pov_character_id=primary_pov_character_id,
                is_dialogue=(line_type == LineType.DIALOGUE),
            )
            if issue:
                issue.script_line_id = line_id
                issues.append(issue)

            if k_type in [POVKnowledgeType.RETROSPECTIVE_CONTEXT, POVKnowledgeType.LATER_KNOWLEDGE]:
                retrospective_count += 1
            else:
                immediate_count += 1

            spoken_line = SpokenLine(
                script_line_id=line_id,
                speaker_id=speaker_id,
                character_id=assigned_char_id,
                exact_spoken_text=raw_text,
                line_type=line_type,
                tone=line_dict.get("tone", "NEUTRAL"),
                emotion=EmotionState(line_dict.get("emotion", "NEUTRAL")),
                story_beat_id=line_dict.get("story_beat_id"),
                line_number=idx,
                pov_character_id=primary_pov_character_id,
                knowledge_type=k_type,
                provenance=ProvenanceType(line_dict.get("provenance", "CONTEXT_SUPPORTED")),
                camera_shot_suggestion=shot_suggestion,
                camera_is_pov=camera_is_pov,
                metadata={
                    "historical_fact_grounding": line_dict.get("historical_fact_grounding", ""),
                    "script_phrasing_nature": line_dict.get("script_phrasing_nature", ""),
                    **line_dict.get("metadata", {}),
                },
            )
            compiled_lines.append(spoken_line)

        # Critical Validation: In FIRST_PERSON_ROLEPLAY, external narrator lines must be 0
        has_external_leakage = (storytelling_mode == StorytellingMode.FIRST_PERSON_ROLEPLAY and external_narrator > 0)
        has_gaps = any(iss.issue_type == "POV_KNOWLEDGE_GAP" for iss in issues)

        is_valid = (not has_external_leakage) and (not has_gaps)

        return FirstPersonCompilationResult(
            storytelling_mode=storytelling_mode,
            primary_pov_character_id=primary_pov_character_id,
            total_lines=len(compiled_lines),
            protagonist_narration_lines=protagonist_narration,
            protagonist_dialogue_lines=protagonist_dialogue,
            supporting_dialogue_lines=supporting_dialogue,
            external_narrator_lines=external_narrator,
            retrospective_lines=retrospective_count,
            immediate_lines=immediate_count,
            compiled_lines=compiled_lines,
            pov_state=pov_state,
            validation_issues=issues,
            has_knowledge_gap=has_gaps,
            is_valid=is_valid,
        )

    def _suggest_camera_shot(self, line_dict: dict[str, Any], idx: int) -> str:
        """Derives a cinematic camera shot that reinforces STORY POV != CAMERA POV."""
        text = str(line_dict.get("exact_text", "")).lower()
        if any(w in text for w in ["bản đồ", "châu âu", "mặt trận", "địa lý", "biên chế"]):
            return "HISTORICAL_MAP_OVERVIEW"
        if any(w in text for w in ["tiền", "ví", "giấy tờ", "hồ sơ", "đơn gia nhập"]):
            return "OBJECT_INSERT_CLOSEUP"
        if any(w in text for w in ["thành phố", "munich", "đường phố", "bùn lầy", "chiến hào"]):
            return "WIDE_ENVIRONMENTAL_ESTABLISHING"
        if line_dict.get("is_dialogue"):
            return "OVER_THE_SHOULDER_DIALOGUE"
        return "MEDIUM_PROFILE_TRACKING"
