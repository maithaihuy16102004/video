"""Stage 4: Retention Director.

Re-rhythms narration beats into cinematic pacing segments:
  HOOK -> SETUP -> QUESTION -> ESCALATION -> PAYOFF -> NEW_QUESTION -> CONFLICT
  -> REACTION -> RESOLUTION -> CLIFFHANGER

Ensures that a 15-second spoken section is broken into multiple dynamic shots
(e.g., 3.0s, 2.5s, 4.0s, 1.5s, 4.0s) rather than one static 15-second zoom.
"""
from __future__ import annotations

import math
from typing import Any

from ..schemas.plan import RetentionRole, RetentionSegment
from ..schemas.script import Beat, ScriptAnalysis


def plan_retention_segments(
    analysis: ScriptAnalysis,
    target_duration_sec: float | None = None,
    min_shot_sec: float = 1.2,
    max_shot_sec: float = 5.5,
) -> list[RetentionSegment]:
    """Partitions script beats into retention arc segments with variable shot pacing."""
    beats = analysis.beats
    total_beats = len(beats)
    if total_beats == 0:
        return []

    segments: list[RetentionSegment] = []
    # Retention pattern mapping
    roles_order = [
        RetentionRole.HOOK,
        RetentionRole.SETUP,
        RetentionRole.QUESTION,
        RetentionRole.ESCALATION,
        RetentionRole.PAYOFF,
        RetentionRole.NEW_QUESTION,
        RetentionRole.CONFLICT,
        RetentionRole.REACTION,
        RetentionRole.RESOLUTION,
        RetentionRole.CLIFFHANGER,
    ]

    # Cluster beats into segments
    cluster_size = max(1, math.ceil(total_beats / len(roles_order)))
    for s_idx in range(0, total_beats, cluster_size):
        sub_beats = beats[s_idx : s_idx + cluster_size]
        role_idx = min(len(roles_order) - 1, len(segments))
        # If it's the very last segment, make sure it's CLIFFHANGER or RESOLUTION
        if s_idx + cluster_size >= total_beats:
            role = RetentionRole.CLIFFHANGER
        else:
            role = roles_order[role_idx]

        dur_sum = sum(b.est_duration_sec for b in sub_beats)
        beat_ids = [b.beat_id for b in sub_beats]

        # Break segment duration into dynamic sub-shot durations
        # e.g., mix of 2.0s, 3.5s, 1.8s, 4.0s
        shot_durs: list[float] = []
        rem = dur_sum
        step = 0
        while rem > 0.0:
            if rem <= max_shot_sec:
                shot_durs.append(round(rem, 2))
                break
            # Vary pacing according to role
            if role in (RetentionRole.HOOK, RetentionRole.PAYOFF, RetentionRole.CONFLICT):
                target_shot = 2.0 + (step % 3) * 0.8  # fast 2.0, 2.8, 3.6
            elif role in (RetentionRole.SETUP, RetentionRole.RESOLUTION):
                target_shot = 3.5 + (step % 2) * 1.0  # steady 3.5, 4.5
            else:
                target_shot = 2.5 + (step % 4) * 0.7  # dynamic

            chosen = min(rem - min_shot_sec, max(min_shot_sec, target_shot))
            shot_durs.append(round(chosen, 2))
            rem -= chosen
            step += 1

        segments.append(RetentionSegment(
            segment_id=f"RET_{len(segments) + 1:02d}",
            role=role,
            beat_ids=beat_ids,
            target_duration_sec=round(dur_sum, 2),
            shot_durations=shot_durs,
            intensity=0.8 if role in (RetentionRole.HOOK, RetentionRole.CONFLICT, RetentionRole.CLIFFHANGER) else 0.45,
            reason=f"Pacing for {role.value} arc across beats {beat_ids}",
        ))

    return segments
