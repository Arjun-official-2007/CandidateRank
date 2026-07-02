"""
scoring/skills.py — Skill coverage and quality scoring.

Evaluates must-have coverage, nice-to-have coverage, and verified
assessment scores. Suspicious skills (expert + <6 months) are excluded
from the coverage counts to avoid rewarding keyword stuffing.

Returns (score, evidence_dict) for full auditability.
Zero LLM calls.
"""

from typing import List, Dict, Tuple, Any, Optional

from scoring.config import (
    MUST_HAVE_SKILLS,
    NICE_TO_HAVE_SKILLS,
    NEUTRAL_SCORE,
)
from utils.text import normalize, keyword_hits


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SUSPICIOUS_EXPERT_MIN_MONTHS = 6  # stricter threshold for scoring (honeypot uses 3)


def is_suspicious_skill(skill: dict) -> bool:
    """
    Return True if a skill entry is likely fabricated:
    proficiency == "expert" but duration_months < 6 months.
    """
    proficiency = (skill.get("proficiency") or "").lower().strip()
    if proficiency != "expert":
        return False
    dm = skill.get("duration_months")
    if dm is None:
        return False
    try:
        return float(dm) < _SUSPICIOUS_EXPERT_MIN_MONTHS
    except (TypeError, ValueError):
        return False


def _skill_names(skills: List[dict], exclude_suspicious: bool = True) -> List[str]:
    """
    Extract normalised skill names from the skill list.
    Optionally filter out suspicious (fabricated expert) entries.
    """
    names = []
    for skill in skills:
        if exclude_suspicious and is_suspicious_skill(skill):
            continue
        name = skill.get("name") or skill.get("skill_name") or ""
        if name:
            names.append(normalize(name))
    return names


def _match_taxonomy(skill_names: List[str], taxonomy: List[str]) -> List[str]:
    """
    Return taxonomy entries that have at least one skill_name match.
    Matching: check if the normalised taxonomy term appears as a substring
    of any skill name, or vice versa. Keyword_hits on the joined string
    handles multi-word terms like "vector db".
    """
    skill_blob = " ".join(skill_names)
    return keyword_hits(skill_blob, taxonomy)


# ---------------------------------------------------------------------------
# Coverage scorers
# ---------------------------------------------------------------------------

def must_have_coverage(skills: List[dict]) -> Tuple[float, List[str], List[str]]:
    """
    Fraction of MUST_HAVE_SKILLS present in the candidate's non-suspicious skills.
    Returns (score, matched_skills, suspicious_skills).
    """
    skill_names  = _skill_names(skills, exclude_suspicious=True)
    suspicious   = [
        s.get("name") or s.get("skill_name") or "?"
        for s in skills if is_suspicious_skill(s)
    ]
    matched = _match_taxonomy(skill_names, MUST_HAVE_SKILLS)
    score   = len(matched) / max(len(MUST_HAVE_SKILLS), 1)
    return min(score, 1.0), matched, suspicious


def nice_to_have_coverage(skills: List[dict]) -> Tuple[float, List[str]]:
    """
    Fraction of NICE_TO_HAVE_SKILLS present in the candidate's non-suspicious skills.
    Returns (score, matched_skills).
    """
    skill_names = _skill_names(skills, exclude_suspicious=True)
    matched     = _match_taxonomy(skill_names, NICE_TO_HAVE_SKILLS)
    score       = len(matched) / max(len(NICE_TO_HAVE_SKILLS), 1)
    return min(score, 1.0), matched


def assessment_bonus(skill_assessment_scores: Optional[Dict]) -> float:
    """
    Normalise skill assessment scores (0–100) to a [0, 1] bonus.
    Returns 0 if no assessments are present.
    None-safe.
    """
    if not skill_assessment_scores:
        return 0.0
    try:
        values = [float(v) for v in skill_assessment_scores.values() if v is not None]
        if not values:
            return 0.0
        return min(sum(values) / len(values) / 100.0, 1.0)
    except (TypeError, ValueError, AttributeError):
        return 0.0


def skill_depth_multiplier(skills: list) -> float:
    """
    Multiplier based on average duration_months of non-suspicious skills:
      avg >= 36 months -> 1.2  (deep expertise)
      avg >= 24 months -> 1.1
      avg >= 12 months -> 1.0  (neutral)
      avg <  12 months -> 0.9  (shallow)
      no data          -> 1.0  (neutral)
    """
    durations = []
    for s in skills:
        if is_suspicious_skill(s):
            continue
        dm = s.get("duration_months")
        if dm is not None:
            try:
                durations.append(float(dm))
            except (TypeError, ValueError):
                pass
    if not durations:
        return 1.0
    avg = sum(durations) / len(durations)
    if avg >= 36:
        return 1.2
    if avg >= 24:
        return 1.1
    if avg >= 12:
        return 1.0
    return 0.9


# ---------------------------------------------------------------------------
# Main skills scorer
# ---------------------------------------------------------------------------

def skills_score(candidate: dict) -> Tuple[float, Dict[str, Any]]:
    """
    Compute composite skills score:
        0.7 * must_have_coverage + 0.2 * nice_to_have_coverage + 0.1 * assessment_bonus

    Returns (score ∈ [0, 1], evidence_dict).
    Missing skills list → NEUTRAL_SCORE.
    """
    skills = candidate.get("skills")

    if not skills:
        return NEUTRAL_SCORE, {}

    signals = candidate.get("redrob_signals", {})
    assessments = signals.get("skill_assessment_scores")
    if assessments is None:
        assessments = candidate.get("skill_assessment_scores") or candidate.get("assessments")

    must_score,  must_matched,  suspicious = must_have_coverage(skills)
    nice_score,  nice_matched              = nice_to_have_coverage(skills)
    assess_score                           = assessment_bonus(assessments)

    score = (
        0.7 * must_score
        + 0.2 * nice_score
        + 0.1 * assess_score
    )
    score *= skill_depth_multiplier(skills)  # boost deep expertise, penalise shallow
    score = max(0.0, min(1.0, score))
    missing = [skill for skill in MUST_HAVE_SKILLS if skill not in must_matched]
    evidence = {
        "must_have_matched":    must_matched,
        "must_have_missing":    missing,
        "nice_to_have_matched": nice_matched,
        "suspicious_skills":    suspicious,
        "must_have_score":      round(must_score, 3),
        "nice_to_have_score":   round(nice_score, 3),
        "assessment_bonus":     round(assess_score, 3),
        "missing_data":         False,
    }
    return round(max(0.0, min(1.0, score)), 4), evidence
