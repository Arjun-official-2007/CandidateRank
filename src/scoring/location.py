"""
scoring/location.py — Location fit and notice-period scoring.

Scores geographic proximity to India hiring hubs and notice-period length.
All fields are null-safe: missing data returns NEUTRAL_SCORE, never a penalty.

Returns (score, evidence_dict). Zero LLM calls.
"""

from typing import Dict, Tuple, Any, Optional

from scoring.config import INDIA_HUBS, NEUTRAL_SCORE
from utils.text import normalize


# ---------------------------------------------------------------------------
# Location scorer
# ---------------------------------------------------------------------------

def location_score(city: str, country: str, relocate: Optional[bool]) -> float:
    """
    1.0  — city is in INDIA_HUBS (exact hub match)
    0.8  — city is in India but not a top hub, OR city unknown but country = India
    0.7  — country = India and willing_to_relocate
    0.4  — outside India but willing_to_relocate
    0.2  — outside India and not willing to relocate
    NEUTRAL_SCORE — fields are missing (no penalty for absent geo data)
    """
    city     = normalize(city)
    country  = normalize(country)

    # Hub match — highest signal
    for hub in INDIA_HUBS:
        if city and (hub in city or city in hub):
            return 1.0

    # India without a top-hub city
    in_india = "india" in country or "india" in city
    if in_india:
        if city:  # city specified but not a hub
            return 0.8
        # Country = India, city unknown
        if relocate is True:
            return 0.7
        if relocate is False:
            return 0.5
        return 0.6  # neutral if relocate is None/unspecified

    # Outside India
    if relocate is True:
        return 0.4

    if relocate is False:
        return 0.2

    # No geo data available
    return NEUTRAL_SCORE


# ---------------------------------------------------------------------------
# Notice period scorer
# ---------------------------------------------------------------------------

def notice_period_score(days: Optional[int]) -> float:
    """
    Score based on notice period length:
      <30 days  → 1.0 (immediately or very soon available)
      30-60     → 0.6
      60-90     → 0.3
      >90       → 0.1 (quarter-year notice is a significant hiring friction)
      None      → NEUTRAL_SCORE
    """
    if days is None:
        return NEUTRAL_SCORE
    try:
        d = int(days)
    except (TypeError, ValueError):
        return NEUTRAL_SCORE

    if d < 30:
        return 1.0
    if d < 60:
        return 0.6
    if d < 90:
        return 0.3
    return 0.1


# ---------------------------------------------------------------------------
# Main logistics scorer
# ---------------------------------------------------------------------------

def logistics_score(candidate: dict) -> Tuple[float, Dict[str, Any]]:
    """
    Weighted combination of location and notice-period scores.
        0.7 * location_score + 0.3 * notice_period_score

    Notice period field lookup: tries 'notice_period_days', 'notice_period',
    and converts string representations like "30 days" → 30.

    Returns (score ∈ [0, 1], evidence_dict).
    """
    # Extract notice period in days (handle string values like "30 days")
    profile = candidate.get("profile", {})
    signals = candidate.get("redrob_signals", {})

    city    = str(profile.get("city") or profile.get("location") or candidate.get("city") or "").lower()
    country = str(profile.get("country") or candidate.get("country") or "").lower()
    
    will_reloc_val = signals.get("willing_to_relocate")
    if will_reloc_val is None:
        will_reloc_val = candidate.get("willing_to_relocate") # fallback
    will_relocate = bool(will_reloc_val) if will_reloc_val is not None else None
    
    raw_notice = signals.get("notice_period_days")
    if raw_notice is None:
        raw_notice = candidate.get("notice_period_days")
        if raw_notice is None:
            raw_notice = candidate.get("notice_period")

    notice_days: Optional[int] = None
    if raw_notice is not None:
        import re
        m = re.search(r"\d+", str(raw_notice))
        if m:
            try:
                notice_days = int(m.group(0))
            except ValueError:
                pass
    loc_s = location_score(city, country, will_relocate)
    notice_s = notice_period_score(notice_days)

    score = 0.7 * loc_s + 0.3 * notice_s

    evidence = {
        "city":           city,
        "country":        country,
        "willing_relocate": will_relocate,
        "notice_days":    notice_days,
        "location_score": round(loc_s, 3),
        "notice_score":   round(notice_s, 3),
    }
    return round(max(0.0, min(1.0, score)), 4), evidence
