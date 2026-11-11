"""Immutable ProductionRequest + hash chain (Master Prompt §1, §10).

Every submission creates one immutable ProductionRequest. All later
stages (analysis, storyboard, preflight, render, manifest) must
reference the same request ID and the same script hash:

    editor_hash == analysis_hash == storyboard_hash
                == preflight_hash == render_job_hash == output_manifest_hash

A render request whose hash does not match is rejected — never render
a cached unrelated story, never report success on a hidden sample.

Upstream status (see AUDIT.md): V5.1 already hashes the script
(`pipeline/universal/v5_story_director.py:101-102`, sha256 truncated
to 16 hex chars) and carries `script_hash` in the story-world schema
(`pipeline/universal/story_intelligence/schemas.py:15`), but there is
no single immutable request object and no chain check across stages.
This module supplies both, using the full 64-char sha256.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any

STAGES = (
    "editor",
    "analysis",
    "storyboard",
    "preflight",
    "render_job",
    "output_manifest",
)


class HashChainError(ValueError):
    """Raised when a stage hash does not match the script hash."""


def compute_script_hash(script_text: str) -> str:
    """Full sha256 of the normalized script (strip, NFC-normalized)."""
    import unicodedata

    normalized = unicodedata.normalize("NFC", script_text.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProductionRequest:
    """One immutable submission. Created once, never edited.

    If the script changes, create a new ProductionRequest — the old
    one's approvals are invalidated by construction.
    """

    script_text: str
    language: str = "vi-VN"
    aspect_ratio: str = "16:9"
    visual_style: str = "Premium Stickman Cinematic B"
    request_id: str = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    script_hash: str = field(init=False)
    # stage -> hash recorded at that stage (mutable bookkeeping kept
    # outside the frozen dataclass via object.__setattr__ on a dict)
    _stage_hashes: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "script_hash", compute_script_hash(self.script_text))
        # The editor stage is the source of truth.
        self._stage_hashes["editor"] = self.script_hash

    def record_stage(self, stage: str, script_hash: str) -> None:
        """Record the hash a stage claims to have worked on."""
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage!r}, expected one of {STAGES}")
        self._stage_hashes[stage] = script_hash

    def stage_hash(self, stage: str) -> str | None:
        return self._stage_hashes.get(stage)

    def verify_chain(self) -> list[str]:
        """Return a list of chain mismatches (empty = chain intact)."""
        problems: list[str] = []
        for stage in STAGES:
            recorded = self._stage_hashes.get(stage)
            if recorded is None:
                problems.append(f"{stage}: no hash recorded yet")
            elif recorded != self.script_hash:
                problems.append(
                    f"{stage}: hash {recorded[:12]}… != script hash "
                    f"{self.script_hash[:12]}… — script changed, approvals invalid"
                )
        return problems

    def require_hash_match(self, stage: str, script_hash: str) -> None:
        """Render guard: reject any job whose hash does not match."""
        if script_hash != self.script_hash:
            raise HashChainError(
                f"Refusing {stage}: script hash {script_hash[:12]}… does not "
                f"match request {self.request_id} "
                f"({self.script_hash[:12]}…). The script changed since "
                "approval — re-run analysis and preflight first."
            )
        self.record_stage(stage, script_hash)

    def manifest(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "script_hash": self.script_hash,
            "language": self.language,
            "aspect_ratio": self.aspect_ratio,
            "visual_style": self.visual_style,
            "stage_hashes": dict(self._stage_hashes),
            "chain_ok": not self.verify_chain(),
        }
