"""
scoring/behavioral.py — Behavioral availability multiplier.

This module produces a MULTIPLIER (not an additive score) in the range
BEHAVIORAL_MULTIPLIER_RANGE = (0.2, 1.3), applied after the weighted
base score is computed. 

Design rationale: a candidate with a perfect on-paper profile but a 5%
recruiter response rate must be pushed DOWN significantly, not just
slightly penalised. The multiplier architecture achieves this — a 0.2×
multiplier collapses even a perfect base score by 80%.

All functions are null-safe: None → NEUTRAL_SCORE. Zero LLM calls.
"""

from datetime import datetime
from typing import Dict, Tuple, Any, Optional

from scoring.config import BEHAVIORAL_MULTIPLIER_RANGE, NEUTRAL_SCORE, BEHAVIORAL_SIGNAL_WEIGHTS
from utils.dates import days_since


# ---------------------------------------------------------------------------
# Individual behavioral sub-scorers
# ---------------------------------------------------------------------------

def response_rate_score(rate: Optional[float]) -> float:
    """
    Score based on recruiter response rate.
    Linear mapping: rate of 0.0 -> 0.0, rate of 1.0 -> 1.0.
    None -> NEUTRAL_SCORE (0.6).
    """
    if rate is None:
        return NEUTRAL_SCORE
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return NEUTRAL_SCORE
    return min(max(r, 0.0), 1.0)


def recency_score(last_active_date: Optional[str], ref_today: datetime) -> float:
    """
    Score based on how recently the candidate was active:
      <=14 days   → 1.0 (highly active recently)
      >=180 days  → 0.1 (inactive/cold)
      Linear interpolation between, clamped [0.1, 1.0].
      None       → NEUTRAL_SCORE (0.6)
    """
    days = days_since(last_active_date, ref_today)
    if days is None:
        return NEUTRAL_SCORE

    if days <= 14:
        return 1.0
    if days >= 180:
        return 0.1
    score = 1.0 - (days - 14) / (180 - 14) * (1.0 - 0.1)
    return min(max(score, 0.1), 1.0)


def interview_score(rate: Optional[float]) -> float:
    """
    Score based on interview acceptance/completion rate.
    Linear mapping: rate of 0.0 -> 0.0, rate of 1.0 -> 1.0.
    None -> NEUTRAL_SCORE (0.6).
    """
    if rate is None:
        return NEUTRAL_SCORE
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return NEUTRAL_SCORE
    return min(max(r, 0.0), 1.0)


def profile_score(completeness: Optional[float]) -> float:
    """
    Score based on profile completeness (0–100 scale).
    Linear mapping: completeness of 0.0 -> 0.0, completeness of 100.0 -> 1.0.
    None -> NEUTRAL_SCORE (0.6).
    """
    if completeness is None:
        return NEUTRAL_SCORE
    try:
        c = float(completeness)
    except (TypeError, ValueError):
        return NEUTRAL_SCORE
    return min(max(c / 100.0, 0.0), 1.0)


def github_score(activity: Optional[float]) -> float:
    """
    Score based on GitHub activity metric (arbitrary scale, 40 = excellent):
      <=0  → 0.0 (no activity or disconnected)
      >=40 → 1.0
      else → activity / 40.0
      None → NEUTRAL_SCORE (0.6)
    """
    if activity is None:
        return NEUTRAL_SCORE
    try:
        a = float(activity)
    except (TypeError, ValueError):
        return NEUTRAL_SCORE
    if a <= 0:
        return 0.0
    return min(a / 40.0, 1.0)


def trust_score(
    verified_email: Optional[bool],
    verified_phone: Optional[bool],
    linkedin_connected: Optional[bool],
) -> float:
    """
    Pure identity verification trust score:
    Normalises the 3 verification flags to a [0.0, 1.0] scale.
    If all verifications are missing/None, return NEUTRAL_SCORE.
    """
    if verified_email is None and verified_phone is None and linkedin_connected is None:
        return NEUTRAL_SCORE

    count = 0
    if verified_email is True:
        count += 1
    if verified_phone is True:
        count += 1
    if linkedin_connected is True:
        count += 1
    return count / 3.0


# ---------------------------------------------------------------------------
# Main behavioral multiplier
# ---------------------------------------------------------------------------

def behavioral_multiplier(
    candidate: dict,
    ref_today: datetime,
) -> Tuple[float, Dict[str, Any]]:
    """
    Compute the behavioral availability multiplier.

    Steps:
    1. Score each behavioral dimension with specified weights from BEHAVIORAL_SIGNAL_WEIGHTS:
       response_rate (0.30), recency (0.25), interview_rate (0.15),
       github (0.15), profile_completeness (0.10), trust_score (0.05)
    2. Compute weighted average
    3. Linearly remap [0, 1] → BEHAVIORAL_MULTIPLIER_RANGE (0.2, 1.3)

    Returns (multiplier ∈ [0.2, 1.3], evidence_dict).
    """
    signals = candidate.get("redrob_signals", {})
    
    # Extract fields with fallback to root for backward compatibility using explicit is not None
    response_rate = signals.get("recruiter_response_rate") if signals.get("recruiter_response_rate") is not None else candidate.get("response_rate")
    
    last_active = signals.get("last_active_date") if signals.get("last_active_date") is not None else (
        candidate.get("last_active_date") or candidate.get("last_active") or candidate.get("last_login")
    )
    
    interview_rate = signals.get("interview_completion_rate") if signals.get("interview_completion_rate") is not None else (
        candidate.get("interview_acceptance_rate") or candidate.get("interview_rate")
    )
    
    completeness = signals.get("profile_completeness_score") if signals.get("profile_completeness_score") is not None else (
        candidate.get("profile_completeness") or candidate.get("profile_score")
    )
    
    gh_activity = signals.get("github_activity_score") if signals.get("github_activity_score") is not None else (
        candidate.get("github_activity") or candidate.get("github_contributions")
    )
    
    verified_email = signals.get("verified_email") if signals.get("verified_email") is not None else candidate.get("verified_email")
    verified_phone = signals.get("verified_phone") if signals.get("verified_phone") is not None else candidate.get("verified_phone")
    linkedin = signals.get("linkedin_connected") if signals.get("linkedin_connected") is not None else (
        candidate.get("linkedin_connected") or candidate.get("linkedin_verified")
    )

    # Individual sub-scores
    rr_s   = response_rate_score(response_rate)
    rec_s  = recency_score(last_active, ref_today)
    int_s  = interview_score(interview_rate)
    prof_s = profile_score(completeness)
    gh_s   = github_score(gh_activity)
    ts     = trust_score(verified_email, verified_phone, linkedin)

    # Weighted average of the 6 behavioral signals (weights from BEHAVIORAL_SIGNAL_WEIGHTS)
    w = BEHAVIORAL_SIGNAL_WEIGHTS
    avg = (
        w["recruiter_response_rate"]   * rr_s   +  # 0.30 — JD explicit signal
        w["recency"]                   * rec_s  +  # 0.25 — JD explicit signal
        w["interview_completion_rate"] * int_s  +  # 0.15
        w["github_activity"]           * gh_s   +  # 0.15 — critical for Senior AI Engineer
        w["profile_completeness"]      * prof_s +  # 0.10
        w["trust"]                     * ts        # 0.05
    )

    # Remap [0, 1] → [BEHAVIORAL_MULTIPLIER_RANGE[0], BEHAVIORAL_MULTIPLIER_RANGE[1]]
    lo, hi = BEHAVIORAL_MULTIPLIER_RANGE
    multiplier = lo + avg * (hi - lo)

    days_since_active = days_since(last_active, ref_today)

    evidence = {
        "response_rate_score":  round(rr_s, 3),
        "recency_score":        round(rec_s, 3),
        "interview_score":      round(int_s, 3),
        "profile_score":        round(prof_s, 3),
        "github_score":         round(gh_s, 3),
        "trust_score":          round(ts, 3),
        "behavioral_avg":       round(avg, 3),
        "multiplier":           round(multiplier, 4),
        # Raw field values for reasoning text
        "response_rate":        response_rate,
        "last_active":          last_active,
        "days_since_active":    days_since_active,
        "interview_rate":       interview_rate,
        "profile_completeness": completeness,
        "github_activity":      gh_activity,
    }
    return round(multiplier, 4), evidence

