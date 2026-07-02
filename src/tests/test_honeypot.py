"""
tests/test_honeypot.py — Unit tests for honeypot detection.

Validates:
  - 0 false negatives on honeypot profiles
  - 0 false exclusions on strong profiles
  - Each individual check behaves correctly
  - All-null edge case doesn't crash or incorrectly flag
"""

import sys
import os
import json
import unittest
from datetime import datetime

# Allow import from src/
_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from scoring.honeypot import (
    check_duration_mismatch,
    check_experience_inflation,
    check_impossible_skills,
    check_title_description_mismatch,
    honeypot_signals,
    is_honeypot,
)

# ---------------------------------------------------------------------------
# Fixtures path
# ---------------------------------------------------------------------------
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
    raise ValueError(f"candidate_id={candidate_id} not found in fixtures")


REF_TODAY = datetime(2026, 7, 1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHoneypotChecks(unittest.TestCase):

    # ---- Individual check: duration mismatch ----

    def test_duration_mismatch_detects_discrepancy(self):
        """A candidate with a 30-month gap between declared and actual duration."""
        cand = {
            "career_history": [{
                "start_date": "2020-01",
                "end_date": "2022-01",
                "duration_months": 6,   # actual ≈ 24 months, declared 6 → diff=18 > 6
            }]
        }
        self.assertTrue(check_duration_mismatch(cand, REF_TODAY))

    def test_duration_mismatch_passes_accurate(self):
        """Accurate duration declaration should not flag."""
        cand = {
            "career_history": [{
                "start_date": "2020-01",
                "end_date": "2022-01",
                "duration_months": 24,
            }]
        }
        self.assertFalse(check_duration_mismatch(cand, REF_TODAY))

    def test_duration_mismatch_missing_fields(self):
        """Missing start_date or duration_months → no flag (null-safe)."""
        cand = {"career_history": [{"end_date": "2022-01"}]}
        self.assertFalse(check_duration_mismatch(cand, REF_TODAY))

    # ---- Individual check: experience inflation ----

    def test_experience_inflation_detects_over_claim(self):
        """Career history totals 120mo but declared is 1yr → inflation > 36mo."""
        cand = {
            "years_of_experience": 1,
            "career_history": [
                {"duration_months": 60},
                {"duration_months": 60},
            ]
        }
        self.assertTrue(check_experience_inflation(cand, REF_TODAY))

    def test_experience_inflation_passes_normal(self):
        """Declared 7 years with 72 months history → no flag."""
        cand = {
            "years_of_experience": 7,
            "career_history": [
                {"duration_months": 48},
                {"duration_months": 24},
            ]
        }
        self.assertFalse(check_experience_inflation(cand, REF_TODAY))

    def test_experience_inflation_missing_declared(self):
        """No declared years → can't compare, don't flag."""
        cand = {"career_history": [{"duration_months": 120}]}
        self.assertFalse(check_experience_inflation(cand, REF_TODAY))

    # ---- Individual check: impossible skills ----

    def test_impossible_skills_expert_short(self):
        """Expert with 2 months → flagged."""
        cand = {"skills": [{"name": "NLP", "proficiency": "expert", "duration_months": 2}]}
        flagged = check_impossible_skills(cand)
        self.assertIn("NLP", flagged)

    def test_impossible_skills_expert_long(self):
        """Expert with 48 months → not flagged."""
        cand = {"skills": [{"name": "NLP", "proficiency": "expert", "duration_months": 48}]}
        self.assertEqual(check_impossible_skills(cand), [])

    def test_impossible_skills_non_expert_short(self):
        """Non-expert with 1 month → not flagged."""
        cand = {"skills": [{"name": "NLP", "proficiency": "intermediate", "duration_months": 1}]}
        self.assertEqual(check_impossible_skills(cand), [])

    # ---- Individual check: title/description mismatch ----

    def test_title_description_mismatch_keyword_stuffer(self):
        """Marketing Manager with 5 AI keywords → flagged."""
        cand = {
            "current_title": "Marketing Manager",
            "career_history": [{
                "description": "Led NLP embedding ranking retrieval pipeline production deployment"
            }]
        }
        self.assertTrue(check_title_description_mismatch(cand))

    def test_title_description_mismatch_technical_title(self):
        """ML Engineer with AI keywords → NOT flagged (title is technical)."""
        cand = {
            "current_title": "ML Engineer",
            "career_history": [{
                "description": "Led NLP embedding ranking retrieval pipeline"
            }]
        }
        self.assertFalse(check_title_description_mismatch(cand))

    def test_title_description_mismatch_nontechnical_clean(self):
        """HR Manager with no AI keywords → NOT flagged (no keyword stuffing)."""
        cand = {
            "current_title": "HR Manager",
            "career_history": [{
                "description": "Managed hiring and onboarding processes."
            }]
        }
        self.assertFalse(check_title_description_mismatch(cand))

    # ---- Full honeypot signal aggregation ----

    def test_honeypot_001_keyword_stuffer(self):
        """HONEYPOT_001 = Marketing Manager with expert AI skills (duration=1-2mo)."""
        cand = load_fixture("HONEYPOT_001")
        signals = honeypot_signals(cand, REF_TODAY)
        self.assertGreaterEqual(len(signals), 2,
            f"Expected ≥2 signals, got {signals}")
        self.assertTrue(is_honeypot(cand, REF_TODAY))

    def test_honeypot_002_hr_keyword_stuffer(self):
        """HONEYPOT_002 = HR Manager with expert AI skills."""
        cand = load_fixture("HONEYPOT_002")
        self.assertTrue(is_honeypot(cand, REF_TODAY),
            f"Signals: {honeypot_signals(cand, REF_TODAY)}")

    def test_strong_001_not_honeypot(self):
        """STRONG_001 = legitimate ML Engineer — must NOT be excluded."""
        cand = load_fixture("STRONG_001")
        self.assertFalse(is_honeypot(cand, REF_TODAY),
            f"False positive! Signals: {honeypot_signals(cand, REF_TODAY)}")

    def test_strong_002_not_honeypot(self):
        """STRONG_002 = legitimate Applied Scientist — must NOT be excluded."""
        cand = load_fixture("STRONG_002")
        self.assertFalse(is_honeypot(cand, REF_TODAY),
            f"False positive! Signals: {honeypot_signals(cand, REF_TODAY)}")

    def test_strong_003_not_honeypot(self):
        """STRONG_003 = Senior ML Engineer — must NOT be excluded."""
        cand = load_fixture("STRONG_003")
        self.assertFalse(is_honeypot(cand, REF_TODAY),
            f"False positive! Signals: {honeypot_signals(cand, REF_TODAY)}")

    def test_strong_004_not_honeypot(self):
        """STRONG_004 = Research Engineer — must NOT be excluded."""
        cand = load_fixture("STRONG_004")
        self.assertFalse(is_honeypot(cand, REF_TODAY),
            f"False positive! Signals: {honeypot_signals(cand, REF_TODAY)}")

    def test_edge_nulls_not_honeypot(self):
        """All-null candidate — should NOT crash and should NOT be excluded."""
        cand = load_fixture("EDGE_NULLS")
        # Should not raise any exception
        try:
            result = is_honeypot(cand, REF_TODAY)
        except Exception as e:
            self.fail(f"is_honeypot raised {type(e).__name__}: {e}")
        # Null profiles shouldn't be falsely flagged
        self.assertFalse(result,
            f"Null candidate incorrectly flagged as honeypot: {honeypot_signals(cand, REF_TODAY)}")

    def test_ghost_not_honeypot(self):
        """Ghost profile (inactive) → should NOT be a honeypot (just behavioral penalty)."""
        cand = load_fixture("GHOST_001")
        self.assertFalse(is_honeypot(cand, REF_TODAY),
            f"Ghost incorrectly flagged: {honeypot_signals(cand, REF_TODAY)}")


class TestHoneypotNullSafety(unittest.TestCase):
    """Verify all honeypot functions handle None/missing inputs gracefully."""

    def test_check_duration_empty_history(self):
        self.assertFalse(check_duration_mismatch({}, REF_TODAY))
        self.assertFalse(check_duration_mismatch({"career_history": []}, REF_TODAY))
        self.assertFalse(check_duration_mismatch({"career_history": None}, REF_TODAY))

    def test_check_impossible_skills_empty(self):
        self.assertEqual(check_impossible_skills({}), [])
        self.assertEqual(check_impossible_skills({"skills": None}), [])
        self.assertEqual(check_impossible_skills({"skills": []}), [])

    def test_check_inflation_empty(self):
        self.assertFalse(check_experience_inflation({}, REF_TODAY))

    def test_check_title_mismatch_empty(self):
        self.assertFalse(check_title_description_mismatch({}))
        self.assertFalse(check_title_description_mismatch({"current_title": ""}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
