# CandidateRank-AI

Rule-based, 100% deterministic, high-performance candidate ranking system for the Redrob Hackathon.

## System Requirements
* Python 3.10+
* No external ML libraries or frameworks required (uses standard library only)
* CPU only (processes 100K candidates in < 20 seconds)

## Setup and Execution

1. **Place the Data:** Ensure `candidates.jsonl` is located in the `data/` directory.

2. **Run the Pipeline:**
   ```bash
   python src/rank.py --candidates data/candidates.jsonl --out output/submission.csv
   ```
   Add `--verbose` to see real-time honeypot exclusion logs.

3. **Validate the Output:**
   ```bash
   python src/validate_submission.py output/submission.csv
   ```

4. **Calibrate Sub-weights (Optional):**
   Run the calibration script to test different sub-weight combinations against a validation dataset:
   ```bash
   python src/calibrate.py data/candidates.jsonl
   ```

## Design Decisions
- **Honeypots Hard-Gated:** Run immediately at the start; requires 2+ corroborating signals.
- **Experience Scoring:** Uses a Gaussian curve centered around 7 years of experience.
- **Behavioral Multiplier:** Applied after base scoring to heavily penalize "ghost" profiles, regardless of technical ability.
- **Performance:** Relies on pre-compiled combined regex patterns and LRU caching for string normalization and fuzzy matching, achieving ~160µs per candidate.
