import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from viral_strategy import build_variant_matrix, score_hook, validate_research_brief


class ViralStrategyTests(unittest.TestCase):
    def test_hook_requires_evidence_and_honesty(self):
        score = score_hook(specificity=5, novelty=4, audience_relevance=4, evidence_strength=2, visualizability=5, honesty=5)
        self.assertFalse(score.passes)

    def test_research_brief_requires_three_sourced_proofs(self):
        brief = {"audience_job": "learn", "pain_or_tension": "slow", "novel_claim": "claim", "share_trigger": "share", "save_trigger": "steps", "format_family": "process_reveal", "proof_items": []}
        self.assertTrue(any("3 bằng chứng" in error for error in validate_research_brief(brief)))

    def test_variant_matrix_is_bounded(self):
        matrix = build_variant_matrix(["a", "b", "c"])
        self.assertEqual(len(matrix), 6)
        self.assertEqual(len({item["id"] for item in matrix}), 6)


if __name__ == "__main__":
    unittest.main()
