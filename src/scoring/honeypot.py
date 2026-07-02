"""
scoring/honeypot.py — Hard-gate honeypot detection.

All checks are fully rule-based and deterministic.
Honeypot candidates are EXCLUDED entirely (score = -inf) before any
weighted scoring runs. Two or more corroborating signals are required
to avoid false positives from data entry errors.

Zero LLM calls — all logic is explicit conditional/arithmetic reasoning
so every exclusion is auditable and defensible in a live review.
"""

from datetime import datetime
from typing import List, Optional

from scoring.config import (
    HONEYPOT_MIN_SIGNALS,
    HONEYPOT_HARD_SCORE,
    HONEYPOT_DURATION_TOLERANCE,
    HONEYPOT_INFLATION_THRESHOLD,
    HONEYPOT_EXPERT_MIN_MONTHS,
    CAREER_KEYWORDS,
)
from utils.dates import months_between
from utils.text import title_tier, keyword_hits


# ---------------------------------------------------------------------------
# Individual checks — each returns True (flagged) or a list if relevant
# ---------------------------------------------------------------------------

def check_duration_mismatch(candidate: dict, ref_today: Optional[datetime] = None) -> bool:
    """
    Flag True if any career_history entry has a computed duration that
    disagrees with the declared duration_months by more than
    HONEYPOT_DURATION_TOLERANCE months.
    """
    if ref_today is None:
        ref_today = datetime.now()

    history = candidate.get("career_history") or []
    for entry in history:
        start    = entry.get("start_date")
        end      = entry.get("end_date")
        declared = entry.get("duration_months")

        if declared is None or start is None:
            continue  # missing data → neutral, not a flag

        try:
            declared_f = float(declared)
        except (TypeError, ValueError):
            continue

        computed = months_between(start, end, ref_today)
        if computed is None:
            continue

        if abs(computed - declared_f) > HONEYPOT_DURATION_TOLERANCE:
            return True

    return False


def check_experience_inflation(candidate: dict, ref_today: Optional[datetime] = None) -> bool:
    """
    Flag True if the sum of all career_history durations exceeds the
    declared years_of_experience by more than HONEYPOT_INFLATION_THRESHOLD months.

    Guards against profiles where someone declares 3 years experience but
    lists jobs totalling 7+ years.
    """
    if ref_today is None:
        ref_today = datetime.now()

    profile = candidate.get("profile", {})
    declared_years = profile.get("years_of_experience")
    if declared_years is None:
        declared_years = candidate.get("years_of_experience")

    if declared_years is None:
        return False  # no declared total → can't compare

    try:
        declared_months = float(declared_years) * 12
    except (TypeError, ValueError):
        return False

    history = candidate.get("career_history") or []
    total_months = 0.0
    for entry in history:
        dm = entry.get("duration_months")
        if dm is not None:
            try:
                total_months += float(dm)
                continue
            except (TypeError, ValueError):
                pass
        # Fall back to computing from dates
        computed = months_between(entry.get("start_date"), entry.get("end_date"), ref_today)
        if computed is not None:
            total_months += computed

    # Declared is significantly LESS than what the history actually shows
    # (i.e., they under-declared to hit a target band — or the reverse: over-declared)
    if total_months - declared_months > HONEYPOT_INFLATION_THRESHOLD:
        return True

    return False


def check_impossible_skills(candidate: dict) -> List[str]:
    """
    Return a list of skill names where proficiency == "expert" but
    duration_months < HONEYPOT_EXPERT_MIN_MONTHS.
    An expert who used a skill for less than 3 months is logically impossible.
    """
    skills = candidate.get("skills") or []
    flagged = []
    for skill in skills:
        proficiency = (skill.get("proficiency") or "").lower().strip()
        if proficiency != "expert":
            continue
        dm = skill.get("duration_months")
        if dm is None:
            continue
        try:
            dm_f = float(dm)
        except (TypeError, ValueError):
            continue
        if dm_f < HONEYPOT_EXPERT_MIN_MONTHS:
            flagged.append(skill.get("name") or skill.get("skill_name") or "unknown_skill")
    return flagged


def check_title_description_mismatch(candidate: dict) -> bool:
    """
    Flag True if the current title is LOW relevance (marketing, HR, etc.)
    BUT the most recent job description is stuffed with technical AI keywords.
    This catches the classic keyword-stuffer honeypot pattern.
    """
    profile = candidate.get("profile", {})
    current_title = profile.get("current_title")
    if current_title is None:
        current_title = candidate.get("current_title") or candidate.get("title") or ""
        
    tier = title_tier(current_title)

    if tier > 0.0:
        # Title is technical or unknown — not a mismatch
        return False

    # Title is LOW relevance — check if description is suspiciously technical
    history = candidate.get("career_history") or []
    if not history:
        return False

    # Use the most recent entry (first in list assumed to be most recent)
    latest_desc = history[0].get("description") or ""
    hits = keyword_hits(latest_desc, CAREER_KEYWORDS)

    # 3+ AI-domain keyword hits in a non-technical role = likely stuffed
    return len(hits) >= 3


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

def honeypot_signals(candidate: dict, ref_today: Optional[datetime] = None) -> List[str]:
    """
    Run all honeypot checks and return a list of triggered signal names.
    Empty list = clean profile.
    """
    if ref_today is None:
        ref_today = datetime.now()

    signals = []

    if check_duration_mismatch(candidate, ref_today):
        signals.append("duration_mismatch")

    if check_experience_inflation(candidate, ref_today):
        signals.append("experience_inflation")

    impossible = check_impossible_skills(candidate)
    if impossible:
        signals.append(f"impossible_skills({','.join(impossible[:3])})")

    if check_title_description_mismatch(candidate):
        signals.append("title_description_mismatch")

    # CHECK A: Impossible salary range — min > max
    redrob = candidate.get("redrob_signals", {})
    sal = redrob.get("expected_salary_range_inr_lpa", {})
    sal_min = sal.get("min", 0) or 0
    sal_max = sal.get("max", 0) or 0
    if sal_min > 0 and sal_max > 0 and sal_min > sal_max:
        signals.append("salary_min_gt_max")

    # CHECK B: Career date math doesn't match duration_months (tolerance 14 months)
    for role in candidate.get("career_history", []):
        start  = role.get("start_date")
        end    = role.get("end_date")
        stated = role.get("duration_months")
        if start and end and stated is not None:
            try:
                s = datetime.strptime(start, "%Y-%m-%d")
                e = datetime.strptime(end,   "%Y-%m-%d")
                actual = (e.year - s.year) * 12 + (e.month - s.month)
                if abs(actual - int(stated)) > 14:
                    signals.append(f"date_math_mismatch:{role.get('company', '?')}")
                    break  # one mismatch is enough
            except (ValueError, TypeError):
                pass

    return signals


def is_honeypot(candidate: dict, ref_today: Optional[datetime] = None) -> bool:
    """
    Return True iff the candidate triggers >= HONEYPOT_MIN_SIGNALS checks.
    Hard gate — callers should assign score = HONEYPOT_HARD_SCORE and skip ranking.
    """
    return len(honeypot_signals(candidate, ref_today)) >= HONEYPOT_MIN_SIGNALS
