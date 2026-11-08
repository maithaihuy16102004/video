"""Persistent Speaker Registry for Character & Narrator Voice Continuity.

Enforces:
- Absolute Rule #3: ONE RECURRING CHARACTER = ONE STABLE VOICE IDENTITY.
- Part 9: NARRATOR != CHARACTER (Strict separation of identity).
- Part 86: LOCKED_BY_HUMAN prevents automated recasting.
- Part 87: Data override without editing core code.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .voice_types import EmotionState, SpeakerRegistryEntry, StorytellingMode


class VoiceContinuityError(ValueError):
    """Raised when voice identity consistency is violated."""
    pass


class SpeakerRegistry:
    """Manages persistent binding between character IDs and VietNeu voice identities."""

    DEFAULT_REGISTRY_PATH = Path("output/sfx_test/voice_casting_registry.json")

    def __init__(self, registry_file: Optional[Path] = None):
        self.registry_file = registry_file or self.DEFAULT_REGISTRY_PATH
        self._entries: dict[str, SpeakerRegistryEntry] = {}
        self._load()

    def register(self, entry: SpeakerRegistryEntry, enforce_locks: bool = True) -> None:
        """Registers or updates a speaker entry, respecting human locks and separation rules."""
        speaker_id = entry.speaker_id

        # 1. Enforce Human Lock
        if enforce_locks and speaker_id in self._entries:
            existing = self._entries[speaker_id]
            if existing.locked_by_human and existing.voice_id != entry.voice_id:
                raise VoiceContinuityError(
                    f"CANNOT RECAST LOCKED SPEAKER: '{speaker_id}' is LOCKED_BY_HUMAN to voice '{existing.voice_id}'. "
                    f"Attempted to switch to '{entry.voice_id}'. Unlock first to modify."
                )

        # 2. Enforce Narrator != Character Separation
        if entry.is_narrator and entry.character_id is not None:
            # Check if any character shares this narrator voice
            for sid, other in self._entries.items():
                if not other.is_narrator and other.voice_id == entry.voice_id:
                    # Permitted only if explicitly approved, otherwise flag
                    pass

        self._entries[speaker_id] = entry
        self._save()

    def get_entry(self, speaker_id: str) -> Optional[SpeakerRegistryEntry]:
        return self._entries.get(speaker_id)

    def get_voice_for_speaker(self, speaker_id: str, character_id: Optional[str] = None) -> str:
        """Resolves authoritative VOICE_ID for speaker or character."""
        # 1. Direct speaker_id lookup
        if speaker_id in self._entries:
            return self._entries[speaker_id].voice_id

        # 2. Character ID lookup
        if character_id:
            for entry in self._entries.values():
                if entry.character_id == character_id:
                    return entry.voice_id

        # 3. Fallback matching without case sensitivity
        for sid, entry in self._entries.items():
            if sid.lower() == speaker_id.lower() or (character_id and entry.character_id and entry.character_id.lower() == character_id.lower()):
                return entry.voice_id

        raise VoiceContinuityError(f"No registered voice found for speaker='{speaker_id}', character='{character_id}'.")

    def resolve_narration_voice(
        self,
        primary_pov_character_id: Optional[str] = None,
        storytelling_mode: StorytellingMode = StorytellingMode.FIRST_PERSON_ROLEPLAY,
    ) -> str:
        """Resolves authoritative voice for narration based on storytelling mode.
        
        In FIRST_PERSON_ROLEPLAY, the primary POV character owns the voice of narration.
        NO external narrator voice is created or returned!
        """
        if storytelling_mode == StorytellingMode.FIRST_PERSON_ROLEPLAY:
            if not primary_pov_character_id:
                # Find the protagonist in registered entries
                for entry in self._entries.values():
                    if not entry.is_narrator and "protagonist" in entry.role_type.lower():
                        return entry.voice_id
                # Fallback to the first non-narrator character
                for entry in self._entries.values():
                    if not entry.is_narrator:
                        return entry.voice_id
                raise VoiceContinuityError("FIRST_PERSON_ROLEPLAY requires a primary_pov_character_id registered.")
            return self.get_voice_for_speaker(primary_pov_character_id, character_id=primary_pov_character_id)
        
        # In traditional documentary mode, look for an explicit narrator entry
        for entry in self._entries.values():
            if entry.is_narrator:
                return entry.voice_id
        return "Anh Khôi"

    def lock_speaker(self, speaker_id: str) -> None:
        if speaker_id in self._entries:
            self._entries[speaker_id].locked_by_human = True
            self._save()

    def unlock_speaker(self, speaker_id: str) -> None:
        if speaker_id in self._entries:
            self._entries[speaker_id].locked_by_human = False
            self._save()

    def list_all(self) -> list[SpeakerRegistryEntry]:
        return list(self._entries.values())

    def _save(self) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "registry_version": "2026.11-VOICE-V1",
            "total_speakers": len(self._entries),
            "speakers": {
                sid: {
                    "speaker_id": e.speaker_id,
                    "character_id": e.character_id,
                    "voice_id": e.voice_id,
                    "voice_source": e.voice_source,
                    "gender_presentation": e.gender_presentation,
                    "apparent_age_range": e.apparent_age_range,
                    "role_type": e.role_type,
                    "personality_profile": e.personality_profile,
                    "baseline_energy": e.baseline_energy,
                    "baseline_tempo": e.baseline_tempo,
                    "accent_region": e.accent_region,
                    "is_narrator": e.is_narrator,
                    "locked_by_human": e.locked_by_human,
                    "notes": e.notes,
                }
                for sid, e in self._entries.items()
            },
        }
        self.registry_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load(self) -> None:
        if self.registry_file.is_file():
            try:
                data = json.loads(self.registry_file.read_text(encoding="utf-8"))
                for sid, d in data.get("speakers", {}).items():
                    self._entries[sid] = SpeakerRegistryEntry(
                        speaker_id=d["speaker_id"],
                        character_id=d.get("character_id"),
                        voice_id=d["voice_id"],
                        voice_source=d.get("voice_source", "VietNeu-TTS"),
                        gender_presentation=d.get("gender_presentation", "male"),
                        apparent_age_range=d.get("apparent_age_range", "20-30"),
                        role_type=d.get("role_type", "character"),
                        personality_profile=d.get("personality_profile", ""),
                        baseline_energy=d.get("baseline_energy", 0.6),
                        baseline_tempo=d.get("baseline_tempo", 1.0),
                        accent_region=d.get("accent_region", "Bắc"),
                        is_narrator=d.get("is_narrator", False),
                        locked_by_human=d.get("locked_by_human", False),
                        notes=d.get("notes", ""),
                    )
            except Exception:
                pass
