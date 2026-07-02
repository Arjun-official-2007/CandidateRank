# CandidateRank-AI — Automated ML Candidate Ranking

Rule-based, 100% deterministic candidate ranking for large-scale ML hiring pipelines. No LLM calls, no GPU, no SDK instrumentation.

Drop in a `candidates.jsonl`, run one command, get a ranked `submission.csv` in under 2 minutes for 100K profiles.

**Live sandbox:** [candidaterank-arjun.streamlit.app](https://candidaterank-arjun.streamlit.app/) — try it on the bundled sample data (≤100 candidates) without installing anything.

---

## The Problem

Hiring pipelines for ML roles produce thousands of applicants. Manual review is slow. LLM-based rankers are non-deterministic, expensive, and a black box — every rerun can change the order for the same inputs.

CandidateRank-AI is fully auditable:  
every score is a deterministic arithmetic formula, every exclusion is logged, and every ranking decision can be traced to a specific rule in the codebase.

---

## How It Works

```
candidates.jsonl
       │
       ▼
┌─────────────────────┐
│  Honeypot Gate      │  ← Hard exclusion (2+ signals required)
└─────────────────────┘
       │ clean candidates only
       ▼
┌─────────────────────┐
│  Base Score         │  career × 0.30
│  (weighted sum)     │  skills × 0.20
│                     │  experience × 0.15
│                     │  location × 0.10
└─────────────────────┘
       │
       ▼
┌─────────────────────┐
│  Behavioral         │  multiplier ∈ [0.2, 1.3]
│  Multiplier         │  (collapses ghost profiles regardless of base)
└─────────────────────┘
       │
       ▼
  final_score = base × multiplier
       │
       ▼
  Sort → Top 100 → submission.csv + reasoning text
```

1. **Stream** `candidates.jsonl` line-by-line — constant memory, no full-file load
2. **Hard-gate** honeypots before any scoring (requires 2+ corroborating signals)
3. **Score** four independent dimensions with pre-compiled regex and LRU-cached normalisation
4. **Multiply** by the behavioural availability signal
5. **Sort**, select top-100, write `output/submission.csv` with a plain-English reasoning string per candidate

---

## Honeypot Detection

Honeypots are excluded **before any scoring runs**. Two or more of the following signals are required to avoid false positives from data-entry noise:

| Signal | What it checks |
|--------|---------------|
| `duration_mismatch` | Computed date range disagrees with declared `duration_months` by > 6 months |
| `experience_inflation` | Sum of all career history durations exceeds declared `years_of_experience` by > 36 months |
| `impossible_skills` | Proficiency = `"expert"` but skill used for < 3 months |
| `title_description_mismatch` | Non-technical title (HR, Marketing) but description stuffed with 3+ ML keywords |
| `salary_min_gt_max` | `expected_salary_range_inr_lpa.min > max` — impossible range |
| `date_math_mismatch` | `start_date` → `end_date` arithmetic contradicts `duration_months` by > 14 months |

Every exclusion is written to `output/honeypot_audit.log` with timestamp, candidate ID, and triggered signals.

---

## Scoring Dimensions

### Career (weight 0.30)
```
raw = 0.4 × title_tier + 0.6 × description_keyword_score
raw ×= job_hopper_penalty       (< 18 months avg tenure across 4+ jobs → 0.6×)
raw ×= consulting_penalty       (all roles at known consulting firms → 0.5×)
raw += product_company_bonus    (any product-company role → +0.15)
```

`title_tier` uses a fast substring pre-check → fuzzy SequenceMatcher fallback.  
The `"ml"` fragment is matched with word-boundary logic to avoid false positives on "UML", "HTML", "AML".

### Skills (weight 0.20)
```
score = 0.7 × must_have_coverage
      + 0.2 × nice_to_have_coverage
      + 0.1 × assessment_bonus
score ×= skill_depth_multiplier   (avg duration: ≥36m→1.2×, ≥24m→1.1×, <12m→0.9×)
```
Suspicious skills (`proficiency=expert`, `duration_months < 6`) are silently excluded from all coverage counts.

### Experience (weight 0.15)
```
band_score = exp(-(years - 7.0)² / (2 × 2.5²))   ← Gaussian, target = 7 years
ml_years   = Σ duration of roles whose description hits ≥1 CAREER_KEYWORD
score      = 0.6 × band_score + 0.4 × min(ml_years / 5, 1.0)
```
`EXPERIENCE_TARGET_YEARS` is overridable at runtime via `--jd` without redeploying.

### Location / Logistics (weight 0.10)
```
score = 0.7 × location_score + 0.3 × notice_period_score
```

| Location | Score |
|----------|-------|
| Top India hub (Bangalore, Hyderabad, Pune, …) | 1.0 |
| India, non-hub city | 0.8 |
| India, city unknown, willing to relocate | 0.7 |
| Outside India, willing to relocate | 0.4 |
| Outside India, not willing to relocate | 0.2 |

| Notice period | Score |
|---------------|-------|
| < 30 days | 1.0 |
| 30 – 60 days | 0.6 |
| 60 – 90 days | 0.3 |
| > 90 days | 0.1 |

### Behavioral Multiplier (applied on top)
```
avg = 0.30 × response_rate
    + 0.25 × recency
    + 0.15 × interview_completion_rate
    + 0.15 × github_activity
    + 0.10 × profile_completeness
    + 0.05 × trust (email + phone + LinkedIn verified)

multiplier = 0.2 + avg × 1.1    ∈ [0.2, 1.3]
```
A 0.2× multiplier collapses even a perfect base score by 80%. Ghost profiles — high paper score, 5% response rate — can never reach the top.

---

## Reasoning Text

Every top-100 candidate gets a one-line plain-English reasoning string written into `submission.csv`. Ten style templates are applied deterministically based on `candidate_id`, so no two adjacent rows read identically.

Example outputs:
```
Based in bangalore, karnataka, india, this candidate has 7.2 years of total
experience (7.1 years in ML) and works as Senior ML Engineer at Razorpay.
Possesses skills in embeddings, python, retrieval, +rag, pytorch.
Response rate is 91% and notice period is 30 days (active 22 days ago).

Key expertise in nlp, search, machine learning, +transformers, faiss backed
by 6.4 years of total experience (6.3 years in ML). Currently based in pune,
maharashtra, india as AI Engineer at Sarvam AI. Shows 78% responsiveness
with activity 18 days ago. Available with a 45 days notice.
```

---

## Quick Start

### Requirements
- Python 3.10+
- Standard library only — no pip installs needed for the core pipeline
- CPU only

### Run
```bash
# Clone and enter the project
git clone https://github.com/Arjun-official-2007/CandidateRank.git
cd CandidateRank-AI

# Place candidates data
cp /path/to/candidates.jsonl data/candidates.jsonl

# Run the ranking pipeline
python src/rank.py

# Output is at:
#   output/submission.csv      ← top 100 ranked candidates
#   output/honeypot_audit.log  ← excluded profiles with signals
```

### CLI Options
```bash
python src/rank.py \
  --candidates data/candidates.jsonl \   # input file (default: data/candidates.jsonl)
  --out output/submission.csv \          # output path (default: output/submission.csv)
  --min-rows 100 \                       # minimum candidates required (default: 100)
  --ref-date 2026-07-01 \               # fix reference date for reproducibility
  --jd path/to/job_description.txt \    # override skill taxonomy from JD file
  --verbose                             # print honeypot exclusions to stderr
```

### Validate Output
```bash
python src/validate_submission.py output/submission.csv
# [SUCCESS] Validation passed! The submission format is correct.
```

### Run Tests
```bash
python -m pytest src/tests/ -v
# 280 passed in ~1s
```

### JD Override (Optional)
Create a plain-text file with any of the following sections and pass it via `--jd`:
```
REQUIRED SKILLS: embeddings, vector db, python, ranking, retrieval
NICE TO HAVE SKILLS: rag, lora, faiss, pytorch
RELEVANT TITLES: ml engineer, ai engineer, search engineer
TARGET EXPERIENCE: 5 years
```
The pipeline will use your custom taxonomy and target experience band — no code changes needed.

---

## Performance

| Metric | Value |
|--------|-------|
| Candidates processed | 100,000 |
| Wall-clock time | ~97 seconds |
| Memory usage | ~150 MB |
| Errors | 0 |
| Honeypots excluded | 873 |
| Hardware | Standard CPU — no GPU |

Performance is achieved via:
- **LRU-cached normalisation** — `normalize()` is cached on raw strings; same company names/titles appear thousands of times across 100K candidates
- **Combined alternation regex** — `keyword_hits()` compiles ONE `(?<!\\w)(?:kw1|kw2|...|kwN)(?!\\w)` pattern per keyword list, ~30× faster than N separate searches
- **Streaming I/O** — `stream_candidates()` yields records one-by-one; peak memory is independent of dataset size
- **Fast title-tier pre-check** — substring set lookup before falling back to difflib fuzzy matching; LRU-cached so repeated titles cost O(1)

---

## Project Structure

```
CandidateRank-AI/
├── data/
│   └── candidates.jsonl          ← input (not committed)
├── output/
│   ├── submission.csv            ← ranked top-100 output
│   └── honeypot_audit.log        ← excluded profiles + signals
├── src/
│   ├── rank.py                   ← main pipeline entry point
│   ├── validate_submission.py    ← output format checker
│   ├── calibrate.py              ← weight calibration utility
│   ├── verify_health.py          ← end-to-end health check script
│   ├── scoring/
│   │   ├── config.py             ← all constants and weights (single source of truth)
│   │   ├── honeypot.py           ← hard-gate exclusion checks
│   │   ├── career.py             ← title tier, keyword depth, consulting/hopper penalties
│   │   ├── skills.py             ← must-have/nice-to-have coverage, assessment bonus
│   │   ├── experience.py         ← Gaussian band score + ML-specific years
│   │   ├── location.py           ← location fit + notice period
│   │   ├── behavioral.py         ← availability multiplier
│   │   └── reasoning.py          ← 10-template plain-English reasoning generator
│   ├── utils/
│   │   ├── text.py               ← normalize, keyword_hits, title_tier (LRU-cached)
│   │   ├── io.py                 ← stream_candidates, write_submission
│   │   ├── dates.py              ← months_between, days_since
│   │   └── jd.py                 ← job description parser + config override
│   └── tests/
│       ├── test_career.py
│       ├── test_expansion.py     ← 200+ parametrised edge-case tests
│       └── test_honeypot.py
├── submission_metadata.yaml
└── requirements.txt
```

---

## Architecture Decisions

**Rule-based over LLM-based** — Every scoring decision is an explicit arithmetic formula or regex match. Runs are 100% reproducible: same input + same `--ref-date` = identical `submission.csv`, guaranteed.

**Hard-gate honeypots first** — Excluding bad-faith profiles before scoring avoids polluting percentile calculations. Two-signal threshold prevents false positives from data-entry errors.

**Multiplier architecture for behavioral signals** — Additive scoring lets a ghost profile (5% response rate) still rank high if their tech skills are strong. A multiplicative gate collapses the final score regardless of base, matching the spec intent.

**Dynamic config for JD overrides** — `scoring/experience.py` imports `scoring.config as cfg` and reads `cfg.EXPERIENCE_TARGET_YEARS` at call time rather than at import time, so `--jd` overrides propagate without reloading modules.

**Word-boundary ML matching** — The `"ml "` title fragment is matched only as a standalone word (`startswith("ml ")` or `" ml " in title`), preventing false positives on "UML Architect", "HTML Developer", "AML Compliance Manager".

**Null-safe everywhere** — Every scorer returns `NEUTRAL_SCORE` (0.6) for missing fields. Absence of data is never a penalty — only explicit negative signals penalise.

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python 3.11 | Standard library covers all needs; no pip for core pipeline |
| Regex | `re` (pre-compiled combined alternation) | 30× faster than per-keyword loops at 100K scale |
| Fuzzy matching | `difflib.SequenceMatcher` | Zero dependency; only used as fallback after fast pre-check |
| Caching | `functools.lru_cache` | O(1) repeated title/keyword lookups across 100K candidates |
| I/O | Streaming JSONL + `csv.DictWriter` | Constant memory regardless of input size |
| Testing | `pytest` (280 tests) | Parametrised edge-case coverage across all scoring modules |

---

## Team

**EPOCHZERO**  
Submission date: 2026-07-02  
Reproducibility: 100% deterministic — no randomness anywhere in the pipeline.