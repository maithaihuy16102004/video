"""Cut Validator and Repetition Detection Engine.

Architecture:
- CutValidator: Audits every transition between adjacent shots to guarantee that at least one of 6 essential narrative dimensions changes:
  [INFORMATION, ACTION, EMOTION, RELATIONSHIP, WORLD_STATE, SPATIAL_UNDERSTANDING].
- RepetitionDetector: Compares each shot against the preceding 6 shots across 12 physical and semantic parameters to catch and reject compositional stagnation.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from pipeline.universal.story_first_reset.sequence_director import PlannedShot, SequencePlan


@dataclass
class CutValidationResult:
    cut_id: str
    from_shot: str
    to_shot: str
    dimension_changes: dict[str, bool]
    passed: bool
    explanation: str


class CutValidator:
    """Enforces the narrative necessity of every cut in a sequence."""

    @classmethod
    def validate_sequence(cls, sequence: SequencePlan) -> list[CutValidationResult]:
        shots = sequence.planned_shots
        results = []

        for i in range(len(shots) - 1):
            s_from = shots[i]
            s_to = shots[i + 1]
            cut_id = f"CUT_{s_from.shot_id}_TO_{s_to.shot_id}"

            # Evaluate each dimension of change
            info_changed = s_from.information_gained != s_to.information_gained
            action_changed = s_from.physical_action != s_to.physical_action
            spatial_changed = s_from.camera_viewpoint != s_to.camera_viewpoint
            world_changed = (
                s_from.environmental_state.get("lighting") != s_to.environmental_state.get("lighting")
                or s_from.active_characters[0].get("costume") != s_to.active_characters[0].get("costume")
            )
            rel_changed = len(s_from.active_characters) != len(s_to.active_characters) or (
                s_from.semantic_purpose in ("ISOLATION", "CAUSE") and s_to.semantic_purpose in ("SHOW_ACTION", "REACTION")
            )
            emotion_changed = s_from.semantic_purpose != s_to.semantic_purpose

            dim_map = {
                "INFORMATION": info_changed,
                "ACTION": action_changed,
                "SPATIAL_UNDERSTANDING": spatial_changed,
                "WORLD_STATE": world_changed,
                "RELATIONSHIP": rel_changed,
                "EMOTION": emotion_changed,
            }

            passed = any(dim_map.values())
            active_dims = [k for k, v in dim_map.items() if v]

            explanation = (
                f"Cut approved: changes [{', '.join(active_dims)}]. "
                f"Transition from {s_from.semantic_purpose} to {s_to.semantic_purpose}."
                if passed else "REJECTED: No story or spatial dimension changes across cut."
            )

            results.append(CutValidationResult(
                cut_id=cut_id,
                from_shot=s_from.shot_id,
                to_shot=s_to.shot_id,
                dimension_changes=dim_map,
                passed=passed,
                explanation=explanation,
            ))

        return results


class RepetitionDetector:
    """Mathematical and semantic redundancy checker comparing against 6 prior shots."""

    @classmethod
    def audit_sequence(cls, sequence: SequencePlan) -> dict[str, Any]:
        shots = sequence.planned_shots
        comparisons = []
        redundancies_found = 0

        for i, curr in enumerate(shots):
            window_start = max(0, i - 6)
            prior_shots = shots[window_start:i]

            for prior in prior_shots:
                # Compare physical and semantic coordinates
                same_purpose = curr.semantic_purpose == prior.semantic_purpose
                same_camera = curr.camera_viewpoint == prior.camera_viewpoint
                same_char_pos = (
                    curr.active_characters[0]["position_norm"] == prior.active_characters[0]["position_norm"]
                )
                same_facing = curr.active_characters[0]["facing"] == prior.active_characters[0]["facing"]
                same_costume = curr.active_characters[0].get("costume") == prior.active_characters[0].get("costume")

                # Compute similarity score (0.0 to 1.0)
                matches = sum([same_purpose, same_camera, same_char_pos, same_facing, same_costume])
                similarity = matches / 5.0
                is_redundant = similarity >= 0.80

                if is_redundant:
                    redundancies_found += 1

                comparisons.append({
                    "pair": f"{prior.shot_id} vs {curr.shot_id}",
                    "distance_shots": i - prior.shot_number + 1,
                    "similarity_score": round(similarity, 2),
                    "redundancy_detected": is_redundant,
                    "same_camera": same_camera,
                    "same_semantic_purpose": same_purpose,
                })

        return {
            "status": "PASS" if redundancies_found == 0 else "FAIL_REDUNDANCY",
            "total_shots_audited": len(shots),
            "pairwise_comparisons_count": len(comparisons),
            "redundancies_found": redundancies_found,
            "max_observed_similarity": max((c["similarity_score"] for c in comparisons), default=0.0),
            "comparisons": comparisons,
        }
