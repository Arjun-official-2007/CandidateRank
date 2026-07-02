"""
utils/io.py — Streaming JSONL reader and CSV submission writer.
Designed for memory-efficient processing of up to 100K candidate records.
"""

import json
import csv
from typing import Iterator, List, Dict, Any


def stream_candidates(path: str) -> Iterator[Dict[str, Any]]:
    """
    Generator that yields one candidate dict per line from a JSONL file.
    Skips blank lines and malformed JSON lines (logs a warning to stderr).
    Never loads the entire file into memory.
    """
    import sys
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line_no, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as exc:
                print(
                    f"[WARN] Skipping malformed JSON on line {line_no}: {exc}",
                    file=sys.stderr,
                )


def write_submission(path: str, rows: List[Dict[str, Any]]) -> None:
    """
    Write ranked candidate rows to a CSV file.
    Expected columns: candidate_id, rank, score, reasoning.
    """
    fieldnames = ["candidate_id", "rank", "score", "reasoning"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
