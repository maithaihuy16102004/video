"""Voice Performance Planner.

Enforces Parts 17, 18, 19:
- Plans per-line delivery intent, emotion, energy, and pauses.
- Enforces absolute axiom: VOICE_ID != EMOTION (Same voice performs different emotions).
- Maintains performance continuity across adjacent dialogue turns.
"""
from __future__ import annotations

from typing import Any, Optional

from .voice_types import DeliveryStyle, EmotionState, SpokenLine, VoicePerformancePlan


class VoicePerformancePlanner:
    """Plans performance nuance for individual dialogue and narration lines."""

    def plan_line_performance(
        self,
        line: SpokenLine,
        context_before: str = "",
        context_after: str = "",
    ) -> VoicePerformancePlan:
        """Derives a VoicePerformancePlan from the spoken line context and emotion."""
        text_lower = line.exact_spoken_text.lower()
        emotion = line.emotion

        # Emotion inference from text cues if not explicitly tagged
        if emotion == EmotionState.NEUTRAL:
            if any(w in text_lower for w in ["chưa có gì", "mù mịt", "chẳng có bao nhiêu"]):
                emotion = EmotionState.DRY_COMEDY
            elif any(w in text_lower for w in ["không hề", "không một chút nào", "spoiler"]):
                emotion = EmotionState.DRY_COMEDY
            elif any(w in text_lower for w in ["chiến tranh", "bùng nổ", "lao vào"]):
                emotion = EmotionState.SERIOUS
            elif "?" in line.exact_spoken_text:
                emotion = EmotionState.SURPRISED
            else:
                emotion = EmotionState.CALM

        # Delivery style mapping
        if line.line_type.value == "NARRATION":
            style = DeliveryStyle.STORYTELLING if emotion != EmotionState.DRY_COMEDY else DeliveryStyle.DEADPAN
        else:
            style = DeliveryStyle.NATURAL

        # Pause profile planning
        if "?" in line.exact_spoken_text:
            pause_profile = "inquisitive_pause"
        elif "..." in line.exact_spoken_text:
            pause_profile = "hesitant_breath_pause"
        elif any(w in text_lower for w in ["không hề", "không một chút nào"]):
            pause_profile = "dramatic_punchline_hold"
        else:
            pause_profile = "natural_sentence_end"

        # Energy calculation (0.0 to 1.0)
        if emotion in (EmotionState.ANGRY, EmotionState.TENSE):
            energy = 0.85
        elif emotion in (EmotionState.EXHAUSTED, EmotionState.SAD):
            energy = 0.35
        elif emotion == EmotionState.DRY_COMEDY:
            energy = 0.50
        else:
            energy = 0.60

        return VoicePerformancePlan(
            script_line_id=line.script_line_id,
            speaker_id=line.speaker_id,
            emotion=emotion,
            emotion_intensity=0.75,
            intent=f"Deliver line as {emotion.value} in {style.value} cadence",
            energy=energy,
            pause_profile=pause_profile,
            emphasis_targets=[],
            delivery_style=style,
            context_before=context_before[:60],
            context_after=context_after[:60],
        )
