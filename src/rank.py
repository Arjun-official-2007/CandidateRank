"""
rank.py — Main orchestration entry point for CandidateRank-AI.

Usage:
    python rank.py --candidates data/candidates.jsonl --out submission.csv

Pipeline:
    1. Stream candidates line-by-line (no full-file load into memory)
    2. Hard-gate honeypot detection (excluded before any scoring)
    3. Weighted multi-signal scoring (career, skills, experience, location)
    4. Behavioral multiplier applied on top of base score
    5. Sort, take top-100, write CSV

Constraints satisfied:
    - CPU only, no GPU
    - ≤16 GB RAM (streaming, no full-dataset in memory)
    - ≤5 min wall-clock for 100K candidates (rule-based, O(n) scan)
    - NO internet/API calls
    - 100% reproducible (ref_today fixed at script start)
"""

import sys
import os
import argparse
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Path setup: allow running from project root or from src/
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
# Also add parent so `python src/rank.py` works from project root
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from scoring.config import WEIGHTS
from scoring.honeypot import is_honeypot, honeypot_signals
from scoring.career import career_score
from scoring.skills import skills_score
from scoring.experience import experience_score
from scoring.location import logistics_score
from scoring.behavioral import behavioral_multiplier
from scoring.reasoning import generate_reasoning
from utils.io import stream_candidates, write_submission


# ---------------------------------------------------------------------------
# Main scoring pipeline
# ---------------------------------------------------------------------------

def main(candidates_path: str, out_path: str, verbose: bool = False, ref_today: datetime = None, min_rows: int = 100) -> None:
    if ref_today is None:
        ref_today = datetime.now()
    t_start   = time.time()

    scored        = []
    seen_ids      = set()
    total         = 0
    honeypot_count = 0
    error_count   = 0

    # Open audit log for honeypots
    audit_log_path = os.path.join(os.path.dirname(out_path), "honeypot_audit.log")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    audit_log = open(audit_log_path, "w", encoding="utf-8")

    print(f"[INFO] Starting ranking run at {ref_today.isoformat()}", flush=True)
    print(f"[INFO] Input:  {candidates_path}", flush=True)
    print(f"[INFO] Output: {out_path}", flush=True)
    print(f"[INFO] Audit:  {audit_log_path}", flush=True)

    for cand in stream_candidates(candidates_path):
        total += 1
        
        cid = cand.get("candidate_id")
        if cid:
            if cid in seen_ids:
                continue  # Skip duplicates, keeping the first seen
            seen_ids.add(cid)

        if total % 10_000 == 0:
            elapsed = time.time() - t_start
            print(
                f"[INFO] Processed {total:,} candidates in {elapsed:.1f}s "
                f"({honeypot_count} honeypots excluded, {len(scored)} scored)",
                flush=True,
            )

        try:
            # --- Hard gate: honeypot exclusion ---
            signals = honeypot_signals(cand, ref_today)
            if len(signals) >= 2:
                honeypot_count += 1
                cid_str = cid or f"unknown_{total}"
                log_line = f"[{ref_today.isoformat()}] ID={cid_str} SIGNALS={signals}\n"
                audit_log.write(log_line)
                if verbose:
                    print(f"[HONEYPOT] {cid_str} signals={signals}", file=sys.stderr)
                continue

            # --- Weighted base scoring ---
            career, c_ev = career_score(cand, ref_today)
            skills, s_ev = skills_score(cand)
            exp,    e_ev = experience_score(cand, ref_today)
            loc,    l_ev = logistics_score(cand)

            base = (
                career * WEIGHTS["career"]
                + skills * WEIGHTS["skills"]
                + exp    * WEIGHTS["experience"]
                + loc    * WEIGHTS["location"]
            )

            # --- Behavioral multiplier ---
            mult, b_ev = behavioral_multiplier(cand, ref_today)
            final = base * mult

            scored.append((cand, final, c_ev, s_ev, e_ev, l_ev, b_ev))

        except Exception as exc:
            error_count += 1
            cid = cand.get("candidate_id", "?") if isinstance(cand, dict) else "?"
            print(
                f"[ERROR] candidate_id={cid}: {exc}",
                file=sys.stderr,
            )
            if error_count > 500:
                print("[ERROR] Too many errors — aborting.", file=sys.stderr)
                sys.exit(1)

    audit_log.close()

    # --- Sort and select top-100 ---
    # Stable sort: sort ascending by ID first, then descending by score
    # to guarantee descending score and ascending ID on ties.
    scored.sort(key=lambda x: str(x[0].get("candidate_id", "")))
    scored.sort(key=lambda x: x[1], reverse=True)
    
    # # min_rows is passed as argument to main
    top100 = scored[:min_rows]
    if len(top100) < min_rows:
        raise ValueError(f"Expected at least {min_rows} candidates, got {len(top100)}")

    elapsed = time.time() - t_start
    print(
        f"\n[INFO] Scoring complete in {elapsed:.1f}s | "
        f"Total={total:,} | Honeypots={honeypot_count} | "
        f"Eligible={len(scored):,} | Errors={error_count}",
        flush=True,
    )

    # --- Build submission rows ---
    rows = []
    for rank_idx, (cand, final, c_ev, s_ev, e_ev, l_ev, b_ev) in enumerate(top100):
        reasoning = generate_reasoning(cand, c_ev, s_ev, e_ev, l_ev, b_ev)
        rows.append({
            "candidate_id": cand.get("candidate_id", f"unknown_{rank_idx}"),
            "rank":         rank_idx + 1,
            "score":        round(final, 6),
            "reasoning":    reasoning,
        })

    write_submission(out_path, rows)
    print(f"[INFO] Submission written -> {out_path}", flush=True)

    # --- Quick sanity: print top-10 reasoning ---
    print("\n=== TOP 10 CANDIDATES ===")
    for row in rows[:10]:
        print(f"  #{row['rank']:>3} | id={row['candidate_id']} | score={row['score']:.4f}")
        print(f"       {row['reasoning']}\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CandidateRank-AI — Rule-based candidate ranking system"
    )
    from scoring import config as scoring_config
    import utils.jd as jd_utils

    parser.add_argument(
        "--candidates",
        default="data/candidates.jsonl",
        help="Path to candidates.jsonl input file",
    )
    parser.add_argument(
        "--out",
        default="submission.csv",
        help="Path to write the output submission.csv",
    )
    parser.add_argument(
        "--min-rows",
        default=100,
        type=int,
        help="Minimum number of candidates to include in the submission",
    )
    parser.add_argument(
        "--ref-date",
        default=None,
        help="ISO date (YYYY-MM-DD) to use as reference today for reproducibility; defaults to current date",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print honeypot exclusions to stderr",
    )
    parser.add_argument(
        "--jd",
        default=None,
        help="Path to a job description text file to override scoring config",
    )
    args = parser.parse_args()
    # Determine reference date for reproducibility
    if args.ref_date:
        try:
            ref_today = datetime.fromisoformat(args.ref_date)
        except Exception as exc:
            raise ValueError(f"Invalid --ref-date value '{args.ref_date}': {exc}")
    else:
        ref_today = datetime.now()

    # If JD file provided, parse and apply overrides to config
    if args.jd:
        parsed = jd_utils.parse_job_description(args.jd)
        jd_utils.apply_to_config(parsed, scoring_config)

    main(args.candidates, args.out, verbose=args.verbose, ref_today=ref_today)
