"""Stage 1: Script Analyzer.

Transforms raw pasted script into structured ScriptAnalysis:
  - Beats (1+ sentences, duration, historical importance, emotion, tone)
  - Character mentions & roles
  - Location mentions & years
"""
from __future__ import annotations

from ..llm.heuristic_text import HeuristicTextProvider
from ..llm.text_provider import TextProvider
from ..schemas.script import ScriptAnalysis


def analyze_script(script_text: str, provider: TextProvider | None = None) -> ScriptAnalysis:
    if provider is None or isinstance(provider, HeuristicTextProvider):
        # Heuristic analyzer handles arbitrary format reliably
        return HeuristicTextProvider().generate_structured(
            ScriptAnalysis,
            system_instruction="",
            prompt=script_text,
        )

    system_inst = (
        "You are an expert Script Analyzer for historical cinematic animation. "
        "Analyze the provided script into distinct narrative beats, characters, locations, and time periods. "
        "Return valid JSON conforming to the requested schema."
    )
    prompt = f"Analyze the following script into structured narrative beats:\n\n{script_text}"
    try:
        return provider.generate_structured(ScriptAnalysis, system_inst, prompt)
    except Exception:
        # Graceful fallback to heuristic if LLM schema validation fails
        return HeuristicTextProvider().generate_structured(ScriptAnalysis, "", script_text)
