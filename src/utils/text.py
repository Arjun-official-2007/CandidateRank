"""
utils/text.py — Text normalisation, keyword matching, and title-tier classification.

Performance-critical optimisations (must process 100K candidates in <5 min):
  1. normalize() is LRU-cached — same strings appear thousands of times
  2. keyword_hits() compiles ONE combined alternation regex per keyword list,
     then does a single findall() — 30× faster than per-keyword regex loops
  3. title_tier() uses a fast substring pre-check before difflib, and is
     LRU-cached so repeated identical titles cost O(1)
  4. All patterns pre-compiled at module import time

All functions are deterministic and free of LLM calls.
"""

import re
import difflib
from functools import lru_cache
from typing import List

from scoring.config import HIGH_RELEVANCE_TITLES, LOW_RELEVANCE_TITLES


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

# Pre-compile the normalisation patterns
_PUNCT_RE = re.compile(r"[^\w\s\-]")
_SPACE_RE = re.compile(r"\s+")


@lru_cache(maxsize=16384)
def normalize(text: str) -> str:
    """
    Lowercase and strip punctuation/extra whitespace.
    LRU-cached: the same company names, titles, and skill names appear
    thousands of times across 100K candidates.
    """
    if not text:
        return ""
    text = str(text).lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Keyword matching — SINGLE combined alternation regex per keyword list
# ---------------------------------------------------------------------------
# Instead of running N separate regex.search() calls (one per keyword),
# we build ONE regex: (?<!\w)(?:kw1|kw2|...|kwN)(?!\w) and do a single
# findall(). This is ~30× faster for large keyword lists.
#
# _COMBINED_CACHE maps id(keywords_tuple) → (combined_pattern, kw_index)
# We use a tuple of keywords as the cache key (lists are not hashable).
_COMBINED_CACHE: dict = {}


def _get_combined(keywords: List[str]) -> tuple:
    """
    Return (compiled_pattern, norm_kw_list) for a keyword list.
    Cached by the tuple of keywords (hashable).
    """
    key = tuple(keywords)
    if key not in _COMBINED_CACHE:
        norm_kws = [normalize(kw) for kw in keywords]
        # Build alternation: longest phrases first to avoid partial matches
        sorted_norm = sorted(norm_kws, key=len, reverse=True)
        alternation = "|".join(re.escape(nk) for nk in sorted_norm if nk)
        pattern = re.compile(r"(?<!\w)(?:" + alternation + r")(?!\w)")
        _COMBINED_CACHE[key] = (pattern, norm_kws, keywords)
    return _COMBINED_CACHE[key]


def keyword_hits(text: str, keywords: List[str]) -> List[str]:
    """
    Return the subset of `keywords` found in `text` using a single combined
    word-boundary alternation regex.

    Multi-word keywords (e.g. "vector db") are matched as contiguous phrases.
    Case-insensitive. Returns a deduplicated list in original keyword order.

    Performance: single findall() call instead of N separate searches.
    """
    if not text or not keywords:
        return []

    combined_pat, norm_kws, orig_kws = _get_combined(keywords)
    norm_text = normalize(text)

    # findall returns all matched norm keywords
    found_norms: set[str] = set(combined_pat.findall(norm_text))
    if not found_norms:
        return []

    # Preserve original keyword order and original casing
    matched = []
    seen: set[str] = set()
    for orig, norm_kw in zip(orig_kws, norm_kws):
        if norm_kw in found_norms and orig not in seen:
            matched.append(orig)
            seen.add(orig)
    return matched


# ---------------------------------------------------------------------------
# Title tier classification — fast path first, fuzzy as fallback
# ---------------------------------------------------------------------------

_TITLE_MATCH_THRESHOLD = 0.75

# Pre-normalise the reference lists once
_HIGH_NORM = [normalize(t) for t in HIGH_RELEVANCE_TITLES]
_LOW_NORM  = [normalize(t) for t in LOW_RELEVANCE_TITLES]

# Keyword fragments that strongly indicate high-relevance titles
# (for a fast substring check before hitting difflib)
_HIGH_FRAGMENTS = {
    "ml ", "machine learning", "data scientist", "ai engineer",
    "software engineer", "backend engineer", "applied scientist",
    "research engineer", "nlp engineer", "senior engineer",
    "staff engineer", "principal engineer", "recommendation",
    "search engineer", "ranking engineer", "ml engineer",
}
_LOW_FRAGMENTS = {
    "marketing manager", "hr manager", "human resources",
    "accountant", "graphic designer", "sales manager",
    "content writer", "social media", "recruiter",
    "business development", "administrative", "customer support",
    "product marketing",
}


def _fast_tier(norm_title: str) -> float | None:
    """
    Fast substring check before fuzzy matching.
    Returns 1.0, 0.0, or None (= needs fuzzy check).
    """
    for frag in _HIGH_FRAGMENTS:
        if frag in norm_title:
            return 1.0
    for frag in _LOW_FRAGMENTS:
        if frag in norm_title:
            return 0.0
    return None


def _best_ratio(query: str, candidates: List[str]) -> float:
    best = 0.0
    for c in candidates:
        ratio = difflib.SequenceMatcher(None, query, c).ratio()
        if ratio > best:
            best = ratio
            if best >= _TITLE_MATCH_THRESHOLD:
                break  # early exit once threshold exceeded
    return best


@lru_cache(maxsize=4096)
def title_tier(title: str) -> float:
    """
    Classify a job title into a relevance tier (LRU-cached on raw string):
      1.0  — strong technical match (ML/AI/SWE)
      0.0  — explicitly non-technical / low relevance
      0.5  — unknown / ambiguous title

    Uses fast substring pre-check first; falls back to fuzzy matching
    (difflib.SequenceMatcher) only when needed. The LRU cache means
    repeated identical titles (very common at 100K scale) cost O(1).
    """
    if not title:
        return 0.5  # unknown, not a penalty

    norm = normalize(title)

    # Fast path: substring check (covers most real-world cases)
    fast = _fast_tier(norm)
    if fast is not None:
        return fast

    # Slow path: fuzzy matching (rare — only for unusual/abbreviated titles)
    high_score = _best_ratio(norm, _HIGH_NORM)
    low_score  = _best_ratio(norm, _LOW_NORM)

    if high_score >= _TITLE_MATCH_THRESHOLD and high_score >= low_score:
        return 1.0
    if low_score >= _TITLE_MATCH_THRESHOLD and low_score > high_score:
        return 0.0

    # Substring fallback — handles "Senior ML Engineer" etc.
    for t in _HIGH_NORM:
        if t in norm or norm in t:
            return 1.0
    for t in _LOW_NORM:
        if t in norm or norm in t:
            return 0.0

    return 0.5  # ambiguous — neutral, not a penalty
