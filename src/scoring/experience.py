"""
scoring/experience.py — Experience depth and relevance scoring.

Combines declared years_of_experience (band lookup) with computed
ML-specific years derived from career description keyword matching.
Missing fields default to neutral, never penalized.

Returns (score, evidence_dict). Zero LLM calls.
"""

from typing import Dict, Tuple, Any, Optional
from datetime import datetime
import math

from scoring.config import EXPERIENCE_TARGET_YEARS, EXPERIENCE_STD_DEV, CAREER_KEYWORDS, NEUTRAL_SCORE
from utils.dates import months_between
from utils.text import keyword_hits


# ---------------------------------------------------------------------------
# Experience band lookup
# ---------------------------------------------------------------------------

def experience_band_score(years: Optional[float]) -> float:
    """
    Map total years_of_experience to a relevance score via a Gaussian curve.
    Formula: e^(-(years - target)^2 / (2 * std_dev^2))
    Returns min of 0.2 if the score is too low.
    """
    if years is None:
        return NEUTRAL_SCORE

    try:
        y = float(years)
    except (TypeError, ValueError):
        return NEUTRAL_SCORE

    # Gaussian curve scoring
    exponent = -((y - EXPERIENCE_TARGET_YEARS) ** 2) / (2 * (EXPERIENCE_STD_DEV ** 2))
    return math.exp(exponent)


# ---------------------------------------------------------------------------
# ML-specific experience extraction
# ---------------------------------------------------------------------------

def ml_specific_years(
    career_history: list,
    ref_today: Optional[datetime] = None,
) -> float:
    """
    Sum duration_months/12 for career_history entries whose description
    contains at least one CAREER_KEYWORD.

    Falls back to declared duration_months if start/end dates are unavailable.
    Returns 0.0 if no matching entries found.
    """
    if ref_today is None:
        ref_today = datetime.now()

    total = 0.0
    for entry in career_history:
        desc = entry.get("description") or ""
        if not keyword_hits(desc, CAREER_KEYWORDS):
            continue  # not an ML role

        # Prefer date-computed duration, fall back to declared
        start = entry.get("start_date")
        end   = entry.get("end_date")
        dm    = entry.get("duration_months")

        computed = months_between(start, end, ref_today) if start else None

        if computed is not None:
            total += computed / 12.0
        elif dm is not None:
            try:
                total += float(dm) / 12.0
            except (TypeError, ValueError):
                pass

    return round(total, 2)


# ---------------------------------------------------------------------------
# Main experience scorer
# ---------------------------------------------------------------------------

def experience_score(
    candidate: dict,
    ref_today: Optional[datetime] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Composite experience score:
        0.6 * experience_band_score(declared years)
        + 0.4 * min(ml_specific_years / 5, 1.0)

    Rationale: declared years gives the big-picture band; ML-specific years
    rewards depth in the actual domain (target is 4-5 years = 0.8-1.0 of
    the 5-year normaliser).

    Returns (score ∈ [0, 1], evidence_dict).
    """
    if ref_today is None:
        ref_today = datetime.now()

    history = candidate.get("career_history") or []
    
    profile = candidate.get("profile", {})
    declared_years = profile.get("years_of_experience")
    if declared_years is None:
        declared_years = candidate.get("years_of_experience")

    band_s   = experience_band_score(declared_years)
    ml_years = ml_specific_years(history, ref_today)
    ml_s     = min(ml_years / 5.0, 1.0)

    score = 0.6 * band_s + 0.4 * ml_s

    evidence = {
        "declared_years":     declared_years,
        "experience_band":    round(band_s, 3),
        "ml_specific_years":  ml_years,
        "ml_score":           round(ml_s, 3),
    }
    return round(max(0.0, min(1.0, score)), 4), evidence
