"""Deterministic rule-based / heuristic text analyzer for offline execution & testing.

Parses arbitrary scripts (Vietnamese or English) into structured schemas without API calls.
"""
from __future__ import annotations

import re
from typing import Any, Type, TypeVar
from pydantic import BaseModel

from ..schemas.bible import ProjectBible, StylePreset
from ..schemas.plan import (
    BodyOrientation,
    CameraHeight,
    CameraMotion,
    LightDirection,
    PerspectiveType,
    RetentionRole,
    ScenePlan,
    Shot,
    ShotPlan,
    ShotPurpose,
    ShotType,
    Transition,
)
from ..schemas.script import Beat, CharacterMention, DialogueLine, LocationMention, ScriptAnalysis

T = TypeVar("T", bound=BaseModel)


class HeuristicTextProvider:
    """Offline heuristic generator implementing TextProvider protocol."""

    def generate_structured(
        self,
        schema: Type[T],
        system_instruction: str,
        prompt: str,
        temperature: float = 0.2,
    ) -> T:
        # Heuristic dispatch based on requested target schema
        if schema is ScriptAnalysis:
            return self._analyze_script(prompt)  # type: ignore
        raise NotImplementedError(f"HeuristicTextProvider does not directly build {schema.__name__}")

    def _analyze_script(self, text: str) -> ScriptAnalysis:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        beats: list[Beat] = []
        chars_found: dict[str, CharacterMention] = {}
        locs_found: dict[str, LocationMention] = {}
        all_years: list[int] = []

        current_speaker: str | None = None
        current_location: str = "Unknown Location"
        current_year: int | None = None

        beat_idx = 0
        buf: list[str] = []

        def flush_buffer():
            nonlocal beat_idx, buf
            if not buf:
                return
            b_text = " ".join(buf).strip()
            buf = []
            if not b_text:
                return

            # Extract years from beat text
            yr_match = re.findall(r"\b(18\d\d|19\d\d|20\d\d)\b", b_text)
            yr = int(yr_match[0]) if yr_match else current_year
            if yr and yr not in all_years:
                all_years.append(yr)

            # Heuristic story beat
            low = b_text.lower()
            story_beat = "exposition"
            if beat_idx == 0 or "hãy tưởng tượng" in low or "imagine" in low:
                story_beat = "arrival"
            elif any(k in low for k in ("spoiler", "tuyệt vời", "không hề", "ironic")):
                story_beat = "payoff"
            elif any(k in low for k in ("bắn", "pháo", "nổ", "chiến tranh", "tấn công", "attack")):
                story_beat = "conflict"
            elif any(k in low for k in ("bị thương", "khí độc", "thất bại", "wounded", "hospital")):
                story_beat = "reaction"
            elif any(k in low for k in ("tập tiếp theo", "tập 2", "to be continued")):
                story_beat = "cliffhanger"

            duration = max(1.8, min(8.0, len(b_text.split()) / 2.6))
            beat = Beat(
                beat_id=f"BEAT_{beat_idx + 1:03d}",
                index=beat_idx,
                text=b_text,
                year=yr,
                location_name=current_location,
                story_beat=story_beat,
                est_duration_sec=round(duration, 2),
            )
            beats.append(beat)
            beat_idx += 1

        for line in lines:
            # Check for header [SCENE / HOOK / LOCATION, YEAR]
            m_header = re.match(r"^\[(.*?)\]$", line)
            if m_header:
                flush_buffer()
                header_text = m_header.group(1)
                # Look for year in header
                y_m = re.search(r"\b(18\d\d|19\d\d|20\d\d)\b", header_text)
                if y_m:
                    current_year = int(y_m.group(1))
                    if current_year not in all_years:
                        all_years.append(current_year)
                # Clean location name
                clean_loc = re.sub(r"^(CẢNH|SCENE|HOOK|COLD OPEN)\s*[-–—:]*\s*", "", header_text, flags=re.I)
                clean_loc = re.sub(r"[-–—,]\s*(18\d\d|19\d\d|20\d\d).*", "", clean_loc).strip()
                if clean_loc:
                    current_location = clean_loc
                    if clean_loc not in locs_found:
                        locs_found[clean_loc] = LocationMention(
                            name=clean_loc,
                            years=[current_year] if current_year else [],
                            first_beat=beat_idx,
                        )
                continue

            # Check for SPEAKER:
            m_spk = re.match(r"^([A-ZÀ-Ỹ0-9\s_]{2,30}):\s*(.*)$", line)
            if m_spk:
                flush_buffer()
                spk_name = m_spk.group(1).strip()
                dialogue_text = m_spk.group(2).strip()
                current_speaker = spk_name
                if spk_name not in chars_found:
                    role = "protagonist" if any(k in spk_name.lower() for k in ("protagonist", "main", "lead", "chính")) or len(chars_found) == 0 else "supporting"
                    if "người dẫn" in spk_name.lower() or "narrator" in spk_name.lower():
                        role = "narrator"
                    chars_found[spk_name] = CharacterMention(
                        name=spk_name,
                        role=role,
                        first_beat=beat_idx,
                    )
                if dialogue_text:
                    buf.append(dialogue_text)
                    flush_buffer()
                continue

            # Normal narration or dialogue continuation
            buf.append(line)
            # Break buffer into beats on strong sentence endings or size
            if len(" ".join(buf).split()) >= 18 or line.endswith((".", "!", "?")):
                flush_buffer()

        flush_buffer()

        if not beats:
            # Fallback if empty
            beats.append(Beat(
                beat_id="BEAT_001",
                index=0,
                text="Opening beat",
                est_duration_sec=3.0,
            ))

        total_dur = sum(b.est_duration_sec for b in beats)
        return ScriptAnalysis(
            title="Episode",
            language="vi" if any(ord(c) > 127 for c in text) else "en",
            beats=beats,
            characters=list(chars_found.values()),
            locations=list(locs_found.values()),
            years=sorted(all_years),
            total_est_duration_sec=round(total_dur, 2),
        )
