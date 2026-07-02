"""
scoring/career.py — Career trajectory scoring.

Evaluates title quality, description keyword depth, consulting-only flag,
and job-hopper tenure patterns. Returns (score, evidence_dict) tuples so
every decision is auditable and can feed into reasoning text generation.

Zero LLM calls — all scoring is rule-based keyword matching and arithmetic.
"""

from typing import List, Dict, Tuple, Any

from scoring.config import (
    CAREER_KEYWORDS,
    CONSULTING_FIRMS,
    WEIGHTS,
    NEUTRAL_SCORE,
    JOB_HOPPER_AVG_TENURE_MONTHS,
    JOB_HOPPER_MIN_JOBS,
    JOB_HOPPER_PENALTY_FACTOR,
    CONSULTING_PENALTY_FACTOR,
    PRODUCT_COMPANY_BONUS,
)
from utils.text import normalize, keyword_hits, title_tier
from utils.dates import months_between
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Sub-scorers
# ---------------------------------------------------------------------------

def score_title(current_title: str) -> float:
    """
    Return a [0.0, 1.0] score for the job title.
    Delegates to utils.text.title_tier:
      1.0 = high-relevance technical title
      0.5 = unknown/ambiguous (neutral, not a penalty)
      0.0 = explicitly non-technical
    """
    return title_tier(current_title or "")


def score_description_keywords(career_history: List[dict]) -> Tuple[float, List[str]]:
    """
    Aggregate keyword_hits across all career history descriptions.
    Score = count of DISTINCT keyword types found / len(CAREER_KEYWORDS), capped at 1.0.
    Returns (score, matched_keywords).
    """
    if not career_history:
        return NEUTRAL_SCORE, []

    all_text = " ".join(
        (entry.get("description") or "") for entry in career_history
    )

    hits = keyword_hits(all_text, CAREER_KEYWORDS)
    distinct_hits = list(dict.fromkeys(hits))  # deduplicate, preserve order

    score = min(len(distinct_hits) / max(len(CAREER_KEYWORDS), 1), 1.0)
    return score, distinct_hits


def is_consulting_only(career_history: List[dict]) -> bool:
    """
    Return True if every entry in career_history is at a known consulting firm.
    A single non-consulting role is enough to return False.
    """
    if not career_history:
        return False

    for entry in career_history:
        company = normalize(entry.get("company") or entry.get("company_name") or "")
        # Check exact membership and substring match for variations
        matched = False
        for firm in CONSULTING_FIRMS:
            if company and (firm in company or company in firm):
                matched = True
                break
        if not matched:
            return False

    return True


# Industries that indicate a product company (as opposed to consulting/services)
PRODUCT_INDUSTRIES = {
    "software", "saas", "ai", "ai/ml", "fintech",
    "e-commerce", "ecommerce", "food delivery",
    "transportation", "edtech", "healthtech",
    "media", "gaming", "marketplace",
}


def product_company_bonus(career_history: List[dict]) -> float:
    """
    Return PRODUCT_COMPANY_BONUS (0.15) if the candidate has any product
    company experience, determined by the industry field of each
    career_history entry. Returns 0.0 if no product company found.
    """
    if not career_history:
        return 0.0
    for role in career_history:
        industry = (role.get("industry") or "").lower().strip()
        if any(pi in industry for pi in PRODUCT_INDUSTRIES):
            return PRODUCT_COMPANY_BONUS
    return 0.0


def job_hopper_penalty(
    career_history: List[dict],
    ref_today: Optional[datetime] = None,
) -> float:
    """
    Return a penalty factor if the candidate shows job-hopper patterns:
      - num_jobs >= JOB_HOPPER_MIN_JOBS (4+)
      - avg_tenure < JOB_HOPPER_AVG_TENURE_MONTHS (18 months / 1.5 years)

    Returns JOB_HOPPER_PENALTY_FACTOR (0.6) if both conditions met, else 1.0.
    """
    if not career_history:
        return 1.0

    if ref_today is None:
        ref_today = datetime.now()

    valid_entries = []
    for entry in career_history:
        dm = entry.get("duration_months")
        if dm is not None:
            try:
                valid_entries.append(float(dm))
                continue
            except (TypeError, ValueError):
                pass
        
        # Fallback to calculating from start_date/end_date if duration_months is missing
        start = entry.get("start_date")
        end = entry.get("end_date")
        if start:
            computed = months_between(start, end, ref_today)
            if computed is not None:
                valid_entries.append(computed)

    if len(valid_entries) < JOB_HOPPER_MIN_JOBS:
        return 1.0

    avg_tenure = sum(valid_entries) / len(valid_entries)
    if avg_tenure < JOB_HOPPER_AVG_TENURE_MONTHS:
        return JOB_HOPPER_PENALTY_FACTOR

    return 1.0


# ---------------------------------------------------------------------------
# Main career scorer
# ---------------------------------------------------------------------------

def career_score(
    candidate: dict,
    ref_today: Optional[datetime] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Compute the overall career score for a candidate.

    Formula:
        raw = 0.4 * score_title + 0.6 * score_description_keywords
        raw *= job_hopper_penalty
        if consulting_only: raw *= CONSULTING_PENALTY_FACTOR

    Returns (score ∈ [0, 1], evidence_dict).
    """
    if ref_today is None:
        ref_today = datetime.now()

    history      = candidate.get("career_history") or []
    profile      = candidate.get("profile", {})
    
    current_title = (
        profile.get("current_title")
        or candidate.get("title")
        or (history[0].get("title") if history else "")
        or ""
    )
    current_company = (
        profile.get("current_company")
        or (history[0].get("company") or history[0].get("company_name") if history else "")
        or ""
    )

    title_score               = score_title(current_title)
    desc_score, matched_kws   = score_description_keywords(history)
    consulting_flag           = is_consulting_only(history)
    hopper_factor             = job_hopper_penalty(history, ref_today)

    raw = 0.4 * title_score + 0.6 * desc_score
    raw *= hopper_factor
    if consulting_flag:
        raw *= CONSULTING_PENALTY_FACTOR
    raw += product_company_bonus(history)  # reward product company experience

    # Clamp to [0, 1]
    score = max(0.0, min(1.0, raw))

    evidence = {
        "current_title":    current_title,
        "current_company":  current_company,
        "title_tier":       title_score,
        "desc_kw_score":    round(desc_score, 3),
        "matched_keywords": matched_kws[:10],   # top-10 for reasoning text
        "consulting_only":  consulting_flag,
        "hopper_penalty":   hopper_factor < 1.0,
        "num_jobs":         len(history),
    }
    return round(score, 4), evidence
