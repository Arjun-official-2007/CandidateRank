# scoring/reasoning.py — Human‑readable reasoning generation.
"""
Provides a concise, evidence‑backed prose justification for each candidate. The output varies tone based on ranking tier (top‑10, top‑30, others).
"""

from typing import Dict, Any


def _tone_prefix(rank: int) -> str:
    """Return a short prefix based on ranking tier for tone variation."""
    if rank <= 10:
        return "🔥 Strong candidate:"  # enthusiastic for top‑10
    if rank <= 30:
        return "👍 Good fit:"  # positive for top‑30
    return "Candidate:"  # neutral otherwise


def generate_reasoning(
    candidate: dict,
    career_ev:  Dict[str, Any],
    skills_ev:  Dict[str, Any],
    exp_ev:     Dict[str, Any],
    loc_ev:     Dict[str, Any],
    behav_ev:   Dict[str, Any],
) -> str:
    """Generate a concise, human‑readable justification.

    Example output:
        "7.2 years total experience (7.1 years ML) as a Senior Machine Learning Engineer
        at Zomato in Noida, India. Skills include embeddings, retrieval, deep learning.
        Notice period: 15 days. Response rate: 61%. Last active 50 days ago."
    """
    parts = []
    # Experience
    yr = exp_ev.get("declared_years")
    ml_yr = exp_ev.get("ml_specific_years")
    if yr is not None:
        if ml_yr:
            parts.append(f"{yr:.1f} years total ({ml_yr:.1f} years ML)")
        else:
            parts.append(f"{yr:.1f} years total")
    else:
        parts.append("experience unknown")
    # Title & company
    title = career_ev.get("current_title") or "a candidate"
    company = career_ev.get("current_company")
    if company:
        parts.append(f"{title} at {company}")
    else:
        parts.append(title)
    # Location
    city = loc_ev.get("city")
    country = loc_ev.get("country")
    if city or country:
        location = ", ".join(filter(None, [city, country]))
        parts.append(f"located in {location}")
    # Notice period
    notice = loc_ev.get("notice_days")
    if notice is not None:
        parts.append(f"notice period: {notice} days")
    # Skills (top 4)
    must = skills_ev.get("must_have_matched") or []
    nice = skills_ev.get("nice_to_have_matched") or []
    skill_list = list(must)[:4]
    if nice:
        skill_list.append("+" + ", ".join(nice[:2]))
    if skill_list:
        parts.append(f"skills: {', '.join(skill_list)}")
    # Behavioral signals
    rr = behav_ev.get("response_rate")
    if rr is not None:
        try:
            rr_pct = int(float(rr) * 100)
            parts.append(f"response rate: {rr_pct}%")
        except Exception:
            pass
    days_active = behav_ev.get("days_since_active")
    if days_active is not None:
        parts.append(f"last active {days_active} days ago")
    # Combine into a single sentence
    reasoning = ". ".join(parts) + "."
    # Optionally prepend tone prefix based on ranking (if needed by caller)
    return reasoning
