"""
tests/test_career.py — Unit tests for career scoring module.

Validates:
  - title scoring for high/low/unknown titles
  - description keyword matching (distinct count / normalisation)
  - consulting-only detection
  - job-hopper penalty
  - null safety across all functions
  - full pipeline integration on fixtures
"""

import sys
import os
import json
import unittest

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from scoring.career import (
    score_title,
    score_description_keywords,
    is_consulting_only,
    job_hopper_penalty,
    career_score,
)
from scoring.config import NEUTRAL_SCORE, JOB_HOPPER_PENALTY_FACTOR

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "sample_candidates.jsonl")


def load_fixture(candidate_id: str) -> dict:
    with open(_FIXTURES, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                cand = json.loads(line)
                if cand.get("candidate_id") == candidate_id:
                    return cand
            except json.JSONDecodeError:
                pass
    raise ValueError(f"candidate_id={candidate_id} not found")


# ---------------------------------------------------------------------------
# Title scoring
# ---------------------------------------------------------------------------

class TestScoreTitle(unittest.TestCase):

    def test_ml_engineer_high(self):
        self.assertEqual(score_title("ML Engineer"), 1.0)

    def test_data_scientist_high(self):
        self.assertEqual(score_title("Data Scientist"), 1.0)

    def test_marketing_manager_low(self):
        self.assertEqual(score_title("Marketing Manager"), 0.0)

    def test_hr_manager_low(self):
        self.assertEqual(score_title("HR Manager"), 0.0)

    def test_empty_title_neutral(self):
        self.assertEqual(score_title(""), 0.5)

    def test_none_title_neutral(self):
        self.assertEqual(score_title(None), 0.5)

    def test_unknown_title_neutral(self):
        # Something totally unrelated should return 0.5 (unknown), not 0.0
        score = score_title("Scuba Diving Instructor")
        self.assertEqual(score, 0.5)


# ---------------------------------------------------------------------------
# Description keyword scoring
# ---------------------------------------------------------------------------

class TestScoreDescriptionKeywords(unittest.TestCase):

    def test_rich_description_scores_high(self):
        history = [{
            "description": (
                "Built embedding pipeline for ranking and retrieval. "
                "Deployed vector db using FAISS for semantic search in production."
            )
        }]
        score, hits = score_description_keywords(history)
        self.assertGreater(score, 0.3)
        self.assertIn("embedding", hits)

    def test_empty_history_returns_neutral(self):
        score, hits = score_description_keywords([])
        self.assertEqual(score, NEUTRAL_SCORE)
        self.assertEqual(hits, [])

    def test_none_history_returns_neutral(self):
        score, hits = score_description_keywords(None)
        self.assertEqual(score, NEUTRAL_SCORE)

    def test_no_keywords_scores_low(self):
        history = [{"description": "Managed office supplies and HR operations."}]
        score, hits = score_description_keywords(history)
        self.assertEqual(score, 0.0)
        self.assertEqual(hits, [])

    def test_duplicate_keywords_not_double_counted(self):
        """
        Same keyword appearing twice in the joined blob should only count once.
        We verify this by checking the returned hits list contains no duplicates.
        """
        history = [
            {"description": "built embedding systems"},
            {"description": "improved embedding pipeline"},
        ]
        score, hits = score_description_keywords(history)
        # "embedding" and "embeddings" may both appear but should each appear at most once
        self.assertEqual(len(hits), len(set(hits)), "Duplicate keywords in hits list!")
        # Score should be > 0 since embedding keyword was found
        self.assertGreater(score, 0.0)


# ---------------------------------------------------------------------------
# Consulting-only detection
# ---------------------------------------------------------------------------

class TestIsConsultingOnly(unittest.TestCase):

    def test_all_consulting(self):
        history = [
            {"company": "TCS"},
            {"company": "Infosys"},
        ]
        self.assertTrue(is_consulting_only(history))

    def test_mixed(self):
        history = [
            {"company": "TCS"},
            {"company": "Swiggy"},
        ]
        self.assertFalse(is_consulting_only(history))

    def test_product_company_only(self):
        history = [{"company": "Razorpay"}, {"company": "PhonePe"}]
        self.assertFalse(is_consulting_only(history))

    def test_empty_history(self):
        self.assertFalse(is_consulting_only([]))

    def test_none_history(self):
        self.assertFalse(is_consulting_only(None))


# ---------------------------------------------------------------------------
# Job-hopper penalty
# ---------------------------------------------------------------------------

class TestJobHopperPenalty(unittest.TestCase):

    def test_hopper_gets_penalty(self):
        """5 jobs at 12 months each = avg 12mo < 14mo threshold → penalty."""
        history = [{"duration_months": 12}] * 5
        self.assertEqual(job_hopper_penalty(history), JOB_HOPPER_PENALTY_FACTOR)

    def test_stable_career_no_penalty(self):
        """2 jobs at 36 months each → avg 36mo → no penalty."""
        history = [{"duration_months": 36}] * 2
        self.assertEqual(job_hopper_penalty(history), 1.0)

    def test_few_jobs_no_penalty(self):
        """Only 2 jobs regardless of tenure → not enough for hopper flag."""
        history = [{"duration_months": 10}, {"duration_months": 10}]
        self.assertEqual(job_hopper_penalty(history), 1.0)

    def test_empty_history(self):
        self.assertEqual(job_hopper_penalty([]), 1.0)


# ---------------------------------------------------------------------------
# Full career_score integration
# ---------------------------------------------------------------------------

class TestCareerScore(unittest.TestCase):

    def test_strong_candidate_scores_high(self):
        cand = load_fixture("STRONG_001")
        score, ev = career_score(cand)
        self.assertGreater(score, 0.4, f"Expected >0.4, got {score}")

    def test_consulting_candidate_penalised(self):
        cand = load_fixture("CONSULTING_001")
        score, ev = career_score(cand)
        self.assertTrue(ev["consulting_only"])
        # Consulting penalty applies ×0.2, score should be low
        self.assertLess(score, 0.3)

    def test_hopper_penalised(self):
        cand = load_fixture("HOPPER_001")
        score, ev = career_score(cand)
        self.assertTrue(ev["hopper_penalty"])

    def test_null_candidate_no_crash(self):
        cand = load_fixture("EDGE_NULLS")
        try:
            score, ev = career_score(cand)
        except Exception as e:
            self.fail(f"career_score raised {type(e).__name__}: {e}")
        # Should return some valid float
        self.assertIsInstance(score, float)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_evidence_keys_present(self):
        cand = load_fixture("STRONG_001")
        _, ev = career_score(cand)
        for key in ["current_title", "matched_keywords", "consulting_only", "hopper_penalty"]:
            self.assertIn(key, ev)


class TestFullPipeline(unittest.TestCase):
    """Run the complete pipeline on all fixtures and check output structure."""

    def _get_all_fixtures(self):
        candidates = []
        with open(_FIXTURES, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        candidates.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return candidates

    def test_pipeline_no_crash_on_any_fixture(self):
        """Every fixture candidate should survive the full career_score pipeline."""
        for cand in self._get_all_fixtures():
            try:
                score, ev = career_score(cand)
                self.assertIsInstance(score, float)
            except Exception as e:
                cid = cand.get("candidate_id", "?")
                self.fail(f"career_score crashed on {cid}: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
