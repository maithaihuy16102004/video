"""Voice-Led Timeline Planner.

Enforces Absolute Rule #1 and Parts 26-32:
- VOICE DEFINES REQUIRED SPEAKING TIME.
- VIDEO TIMELINE ADAPTS TO NATURAL SPEECH (NOT THE OTHER WAY AROUND).
- NEVER ACCELERATE OR TIME-STRETCH VOICE TO FIT SHOT SLOTS.
- Shot boundaries expand to fit natural audio duration plus breathing room.
"""
from __future__ import annotations

from typing import Any, Optional

from .voice_types import AudioTimeline, AudioValidationResult, SpokenLine, TimelineSpeechSlot


class VoiceLedTimelinePlanner:
    """Plans video and audio timeline where native speech duration is the authoritative master."""

    DEFAULT_BREATHING_ROOM = 0.35  # Natural pause between dialogue turns

    def build_timeline(
        self,
        timeline_id: str,
        lines: list[SpokenLine],
        validation_results: dict[str, AudioValidationResult],
    ) -> AudioTimeline:
        """Constructs an authoritative AudioTimeline from native generated speech durations."""
        slots: list[TimelineSpeechSlot] = []
        current_time = 0.0

        for idx, line in enumerate(lines):
            val = validation_results.get(line.script_line_id)
            if not val:
                continue

            native_dur = val.native_duration_seconds
            slot_id = f"slot_{idx+1:03d}_{line.script_line_id}"

            # Natural breathing room after sentence or turn
            # Punctuation / pause profile determines breathing gap
            is_dialogue_switch = (idx + 1 < len(lines) and lines[idx + 1].speaker_id != line.speaker_id)
            is_dramatic_end = any(w in line.exact_spoken_text for w in ["Không hề.", "Không một chút nào.", "bùng nổ."])

            if is_dramatic_end:
                breathing_gap = 0.75
            elif is_dialogue_switch:
                breathing_gap = 0.45
            else:
                breathing_gap = self.DEFAULT_BREATHING_ROOM

            start_t = current_time
            end_t = start_t + native_dur

            # Visual slot must be at least as long as native speech + breathing gap
            visual_dur = native_dur + breathing_gap

            slot = TimelineSpeechSlot(
                slot_id=slot_id,
                script_line_id=line.script_line_id,
                speaker_id=line.speaker_id,
                voice_id=line.metadata.get("voice_id", "default"),
                start_time_seconds=round(start_t, 3),
                native_duration_seconds=round(native_dur, 3),
                end_time_seconds=round(end_t, 3),
                allocated_visual_duration_seconds=round(visual_dur, 3),
                visual_expanded=True,  # Visual edit adapted to fit speech
                breathing_room_seconds=round(breathing_gap, 3),
            )
            slots.append(slot)
            current_time = end_t + breathing_gap

        return AudioTimeline(
            timeline_id=timeline_id,
            slots=slots,
            total_duration_seconds=round(current_time, 3),
        )
