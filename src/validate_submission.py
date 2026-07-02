"""
validate_submission.py — Verify the final CSV format and constraints.
"""

import sys
import csv

def validate_submission(csv_path: str) -> bool:
    print(f"Validating {csv_path}...")
    
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
    except Exception as e:
        print(f"[FAIL] Failed to read CSV: {e}")
        return False
        
    expected_cols = {"candidate_id", "rank", "score", "reasoning"}
    if not reader:
        print("[FAIL] CSV is empty")
        return False
        
    actual_cols = set(reader[0].keys())
    if actual_cols != expected_cols:
        print(f"[FAIL] Column mismatch.\nExpected: {expected_cols}\nActual: {actual_cols}")
        return False

    if len(reader) != 100:
        print(f"[FAIL] Expected 100 rows, found {len(reader)}")
        return False
        
    seen_ids = set()
    prev_score = float('inf')
    
    for i, row in enumerate(reader):
        rank = int(row["rank"])
        if rank != i + 1:
            print(f"[FAIL] Row {i+1} has incorrect rank {rank}")
            return False
            
        score = float(row["score"])
        if score > prev_score:
            print(f"[FAIL] Scores not in descending order at rank {rank} (score {score} > previous {prev_score})")
            return False
        prev_score = score
        
        cid = row["candidate_id"]
        if cid in seen_ids:
            print(f"[FAIL] Duplicate candidate_id found: {cid}")
            return False
        seen_ids.add(cid)
        
        if not row["reasoning"].strip():
            print(f"[FAIL] Missing reasoning text at rank {rank}")
            return False

    print("[SUCCESS] Validation passed! The submission format is correct.")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_submission.py <path_to_submission.csv>")
        sys.exit(1)
    
    success = validate_submission(sys.argv[1])
    sys.exit(0 if success else 1)
