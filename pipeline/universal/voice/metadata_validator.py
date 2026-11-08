"""Metadata Validator for TTS Input.

Enforces Absolute Rule #2:
TTS MUST SPEAK APPROVED SCRIPT TEXT.
It must NOT invent or speak:
- scene descriptions
- director instructions
- metadata
- Gemini reasoning
- character descriptions
- location descriptions
- debug information.

IF DETECTED: FAIL BEFORE SYNTHESIS.
"""
from __future__ import annotations

import re
from typing import Any, Optional


class MetadataInjectionError(ValueError):
    """Raised when metadata, camera cues, or reasoning text is passed to TTS."""
    pass


class MetadataValidator:
    """Scans text for forbidden metadata, stage directions, and debug tokens."""

    FORBIDDEN_PATTERNS = [
        # Stage & Scene markers
        (r"\[(?:HOOK|SCENE|CẢNH|EXT|INT|LOCATION|ĐỊA ĐIỂM)[^\]]*\]", "Scene / Location metadata header"),
        (r"\[(?:CLOSE UP|WIDE|MEDIUM|PAN|ZOOM|TRACKING|CAMERA)[^\]]*\]", "Camera movement instruction"),
        (r"\b(?:CLOSE[- ]UP|WIDE[- ]SHOT|EXTREME WIDE|ESTABLISHING SHOT)\b", "Camera shot syntax"),
        # Pipeline & Engine internal metadata
        (r"\b(?:CharacterDNA|LocationDNA|StoryWorld|SceneEventGraph|RenderSpec)\b", "Pipeline internal class name"),
        (r"\b(?:GEMINI|LLM|REASONING|PROMPT|SYSTEM PROMPT|DIRECTOR NOTES)\b", "Director reasoning metadata"),
        # Data formats
        (r"\{\s*\"[a-zA-Z0-9_-]+\"\s*:", "JSON structure"),
        (r"\[\s*\"[a-zA-Z0-9_-]+\"\s*,", "JSON array"),
        (r"<[a-zA-Z0-9_-]+>[^<]*</[a-zA-Z0-9_-]+>", "XML / HTML tag"),
        # Debug tokens
        (r"\b(?:DEBUG|TRACE|AUDIT|LOG|FIXME|TODO)\s*:", "Debug log marker"),
    ]

    @classmethod
    def validate_for_synthesis(cls, text: str) -> None:
        """Validates that text contains strictly spoken dialogue/narration without metadata."""
        if not text or not text.strip():
            raise MetadataInjectionError("TTS input text cannot be empty.")

        for pattern, desc in cls.FORBIDDEN_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                offending_snippet = match.group(0)
                raise MetadataInjectionError(
                    f"FORBIDDEN METADATA DETECTED IN TTS INPUT: '{offending_snippet}' ({desc}). "
                    f"Full input was: '{text[:80]}...'. TTS must speak approved script text only!"
                )

    @classmethod
    def clean_dialogue_line(cls, raw_line: str) -> str:
        """Strips speaker prefixes like 'HITLER:' or 'NGƯỜI DẪN:' to isolate spoken words."""
        cleaned = re.sub(r"^[A-ZÀ-ỸĐ0-9\s_-]{1,35}:\s*", "", raw_line.strip())
        # Remove surrounding quotes if present
        cleaned = cleaned.strip('“”"\'')
        return cleaned.strip()
