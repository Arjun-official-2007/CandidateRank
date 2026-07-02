"""
calibrate.py — Weight calibration tool for CandidateRank-AI.

Runs the ranking pipeline multiple times on a validation dataset using
a grid search over sub-weights (e.g. title vs description importance).
"""

import sys
import os
import time
from datetime import datetime
import itertools

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from scoring import config
from utils.io import stream_candidates

# Save the original score functions so we can mock them during calibration
import scoring.career
import scoring.skills

_original_career_score = scoring.career.career_score
_original_skills_score = scoring.skills.skills_score

def mock_career_score(title_wt: float, desc_wt: float, ref_today: datetime):
    def _mocked(cand: dict, ref_t = None):
        r_today = ref_t if ref_t is not None else ref_today
        history      = cand.get("career_history") or []
        profile      = cand.get("profile", {})
        
        current_title = (
            profile.get("current_title")
            or cand.get("title")
            or (history[0].get("title") if history else "")
            or ""
        )
        current_company = (
            profile.get("current_company")
            or (history[0].get("company") or history[0].get("company_name") if history else "")
            or ""
        )

        title_score = scoring.career.score_title(current_title)
        desc_score, matched_kws = scoring.career.score_description_keywords(history)
        consulting_flag = scoring.career.is_consulting_only(history)
        hopper_factor = scoring.career.job_hopper_penalty(history, r_today)

        raw = title_wt * title_score + desc_wt * desc_score
        raw *= hopper_factor
        if consulting_flag:
            raw *= config.CONSULTING_PENALTY_FACTOR

        score = max(0.0, min(1.0, raw))
        return round(score, 4), {}
    return _mocked

def mock_skills_score(must_wt: float, nice_wt: float, assess_wt: float):
    def _mocked(cand: dict):
        skills = cand.get("skills")
        if not skills:
            return config.NEUTRAL_SCORE, {}

        must_s, _, _ = scoring.skills.must_have_coverage(skills)
        nice_s, _    = scoring.skills.nice_to_have_coverage(skills)
        
        signals = cand.get("redrob_signals", {})
        assessments = signals.get("skill_assessment_scores")
        if assessments is None:
            assessments = cand.get("skill_assessment_scores") or cand.get("assessments")
            
        assess_s     = scoring.skills.assessment_bonus(assessments)

        score = (must_wt * must_s) + (nice_wt * nice_s) + (assess_wt * assess_s)
        return round(max(0.0, min(1.0, score)), 4), {}
    return _mocked

def calibrate_weights(candidates_path: str):
    ref_today = datetime.now()
    
    print(f"Loading validation set from {candidates_path}...")
    candidates = list(stream_candidates(candidates_path))
    
    # Weight grids
    career_weights = [(0.3, 0.7), (0.4, 0.6), (0.5, 0.5)] # (title, desc)
    skills_weights = [(0.6, 0.3, 0.1), (0.7, 0.2, 0.1), (0.8, 0.1, 0.1)] # (must, nice, assess)
    
    results = []
    
    print(f"Testing {len(career_weights) * len(skills_weights)} weight combinations...")
    
    for c_wts, s_wts in itertools.product(career_weights, skills_weights):
        # Override the scoring functions
        scoring.career.career_score = mock_career_score(*c_wts, ref_today)
        scoring.skills.skills_score = mock_skills_score(*s_wts)
        
        scored = []
        for cand in candidates:
            # Skip honeypot logic for speed, just do base scoring
            c_score, _ = scoring.career.career_score(cand, ref_today)
            s_score, _ = scoring.skills.skills_score(cand)
            from scoring.experience import experience_score
            e_score, _ = experience_score(cand, ref_today)
            from scoring.location import logistics_score
            l_score, _ = logistics_score(cand)
            
            base = (
                c_score * config.WEIGHTS["career"]
                + s_score * config.WEIGHTS["skills"]
                + e_score * config.WEIGHTS["experience"]
                + l_score * config.WEIGHTS["location"]
            )
            
            from scoring.behavioral import behavioral_multiplier
            mult, _ = behavioral_multiplier(cand, ref_today)
            final = base * mult
            scored.append((final, cand.get("candidate_id")))
        
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        top_ids = [s[1] for s in scored[:3]]
        
        results.append({
            "career_weights": f"title={c_wts[0]},desc={c_wts[1]}",
            "skills_weights": f"must={s_wts[0]},nice={s_wts[1]},assess={s_wts[2]}",
            "top_3_candidates": top_ids
        })

    # Restore originals
    scoring.career.career_score = _original_career_score
    scoring.skills.skills_score = _original_skills_score

    print("\n=== CALIBRATION RESULTS ===")
    for r in results:
        print(f"Career: {r['career_weights']:<20} | Skills: {r['skills_weights']:<30} | Top 3: {r['top_3_candidates']}")

if __name__ == "__main__":
    calibrate_weights("data/candidates.jsonl" if not sys.argv[1:] else sys.argv[1])
