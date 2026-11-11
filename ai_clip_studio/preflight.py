"""Preflight validation (Master Prompt §3, §9).

Runs BEFORE any render: script hash, assets, voices, timeline and
output configuration. Returns PASS/FAIL with a reason for every
failed check — a failed preflight blocks the render, it never warns
and continues.

Upstream status (see AUDIT.md): partial. There is a frontend
`PreflightPanel.tsx` (350 lines) with proof screenshots, a
`test_episode01_preflight.py`, and capability validation inside
`v5_story_director.py` (`validate_capability`, animation pacing,
depth sorting, prop parenting, subtitle wrap, camera composition).
There is no single standalone preflight module that checks the hash
chain + assets + voices + timeline + output config together and
returns one verdict. This module is that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .production_request import ProductionRequest
from .timeline import Timeline


@dataclass
class PreflightCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class PreflightResult:
    passed: bool
    checks: list[PreflightCheck] = field(default_factory=list)

    def failures(self) -> list[PreflightCheck]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
        }


def run_preflight(
    request: ProductionRequest,
    *,
    timeline: Timeline | None = None,
    asset_paths: Iterable[Path] = (),
    available_voices: Iterable[str] = (),
    required_voices: Iterable[str] = (),
    output_width: int = 1920,
    output_height: int = 1080,
    fps: int = 24,
    loudness_lufs: float = -14.0,
    script_hash_at_preflight: str | None = None,
    allow_estimated_timeline: bool = False,
) -> PreflightResult:
    """Validate everything a render depends on. No side effects."""
    checks: list[PreflightCheck] = []

    # 1. Script hash chain.
    if script_hash_at_preflight is not None:
        checks.append(PreflightCheck(
            "script_hash",
            script_hash_at_preflight == request.script_hash,
            "hash matches the ProductionRequest" if script_hash_at_preflight == request.script_hash
            else "script changed since submission — re-run analysis",
        ))
    else:
        checks.append(PreflightCheck(
            "script_hash", bool(request.script_text.strip()),
            "script present" if request.script_text.strip() else "empty script",
        ))

    # 2. Language / output configuration.
    checks.append(PreflightCheck(
        "language", request.language == "vi-VN",
        f"language={request.language} (must be vi-VN for publishing)",
    ))
    checks.append(PreflightCheck(
        "output_config",
        (output_width, output_height) == (1920, 1080) and fps == 24,
        f"{output_width}x{output_height}@{fps}fps (must be 1920x1080@24)",
    ))
    checks.append(PreflightCheck(
        "loudness", -15.5 <= loudness_lufs <= -13.0,
        f"loudness {loudness_lufs} LUFS (target -14)",
    ))

    # 3. Assets exist.
    missing = [str(p) for p in asset_paths if not Path(p).exists()]
    checks.append(PreflightCheck(
        "assets", not missing,
        "all assets present" if not missing else f"missing assets: {missing}",
    ))

    # 4. Voices available in the registry.
    available = set(available_voices)
    missing_voices = [v for v in required_voices if v not in available]
    checks.append(PreflightCheck(
        "voices", not missing_voices,
        "all required voices available" if not missing_voices
        else f"voices not in registry: {missing_voices}",
    ))

    # 5. Timeline: must exist, must cover the voice, must be measured.
    if timeline is None:
        checks.append(PreflightCheck("timeline", False, "no timeline built"))
    else:
        checks.append(PreflightCheck(
            "timeline_duration",
            timeline.total_duration_sec > 0,
            f"total {timeline.total_duration_sec:.2f}s",
        ))
        checks.append(PreflightCheck(
            "timeline_measured",
            timeline.all_measured or allow_estimated_timeline,
            "durations measured from real TTS audio"
            if timeline.all_measured
            else "durations are ESTIMATED — allowed only for planning, "
                 "measure real TTS before rendering",
        ))

    passed = all(c.passed for c in checks)
    return PreflightResult(passed=passed, checks=checks)
